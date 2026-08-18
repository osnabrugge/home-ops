#!/usr/bin/env python3
"""Alert triage: turn persistently-firing Alertmanager alerts into GitHub issues.

Design notes:
  * Pure stdlib (no pip install at runtime, no supply-chain surface).
  * Idempotent: every issue carries a hidden fingerprint marker, and we refuse to
    open a second issue for a fingerprint that already has an open issue.
  * Conservative: only alerts firing longer than MIN_FIRING_MINUTES are eligible,
    so transient blips never create issues.
  * Fails soft: a GitHub API error for one alert never aborts the whole run.
"""

import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

ALERTMANAGER = os.environ["ALERTMANAGER_URL"].rstrip("/")
REPO = os.environ["GITHUB_REPOSITORY"]
TOKEN = os.environ["GITHUB_TOKEN"]
ASSIGNEE = os.environ.get("COPILOT_ASSIGNEE", "copilot-swe-agent")
MIN_FIRING_MINUTES = int(os.environ.get("MIN_FIRING_MINUTES", "60"))
MAX_NEW_ISSUES = int(os.environ.get("MAX_NEW_ISSUES", "3"))
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"
SEVERITIES = {s.strip() for s in os.environ.get("SEVERITIES", "critical,warning").split(",") if s.strip()}
IGNORE = {a.strip() for a in os.environ.get("IGNORE_ALERTS", "").split(",") if a.strip()}
MAX_AFFECTED = int(os.environ.get("MAX_AFFECTED", "15"))
MAX_RELATED = int(os.environ.get("MAX_RELATED_ALERT_GROUPS", "8"))
MAX_GENERATORS = int(os.environ.get("MAX_GENERATOR_URLS", "5"))

MARKER = "alert-triage-fingerprint"
LABEL = "alert-triage"
API = "https://api.github.com"


def http(url, method="GET", body=None, headers=None, token=False):
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Accept": "application/json", "User-Agent": "alert-triage"}
    if token:
        # GitHub-specific headers; Alertmanager rejects the vnd.github Accept type.
        hdrs["Accept"] = "application/vnd.github+json"
        hdrs["Authorization"] = f"Bearer {TOKEN}"
        hdrs["X-GitHub-Api-Version"] = "2022-11-28"
    if data:
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else None


def fingerprint(alertname, labels):
    """Stable identity for an alert group: name + the labels that localise it."""
    keys = ("namespace", "instance", "node", "pod", "job", "persistentvolumeclaim")
    parts = [alertname] + [f"{k}={labels[k]}" for k in keys if labels.get(k)]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def fetch_alerts():
    url = f"{ALERTMANAGER}/api/v2/alerts?active=true&silenced=false&inhibited=false"
    return http(url)


def parse_alert_time(value):
    try:
        ts = re.sub(r"\.\d+", "", value).replace("Z", "+00:00")
        return datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


def eligible(alert):
    labels = alert.get("labels", {})
    name = labels.get("alertname", "")
    if not name or name in IGNORE:
        return False
    if SEVERITIES and labels.get("severity") not in SEVERITIES:
        return False
    if alert.get("status", {}).get("state") != "active":
        return False
    began = parse_alert_time(alert.get("startsAt", ""))
    if not began:
        return False
    age = datetime.now(timezone.utc) - began
    return age >= timedelta(minutes=MIN_FIRING_MINUTES)


def existing_fingerprints():
    """All fingerprints that already have an OPEN triage issue."""
    seen = set()
    page = 1
    while page <= 10:
        q = urllib.parse.urlencode({"state": "open", "labels": LABEL, "per_page": 100, "page": page})
        issues = http(f"{API}/repos/{REPO}/issues?{q}", token=True) or []
        if not issues:
            break
        for issue in issues:
            for m in re.findall(rf"{MARKER}:([0-9a-f]+)", issue.get("body") or ""):
                seen.add(m)
        page += 1
    return seen


def triage_steps(alertname, labels):
    lower = alertname.lower()
    common = [
        "Prove scope first: identify exactly which nodes/pods/instances are affected from this issue's evidence.",
        "Collect timeline proof from Kubernetes Events and pod logs (`read-only file system`, I/O errors, remount messages).",
        "Correlate with Ceph state before any intervention (`ceph status`, `ceph health detail`, `ceph osd perf`).",
        "Only if storage/network evidence remains ambiguous, then request a focused physical check for the specific port/path.",
    ]
    if "ceph" in lower or "rbd" in lower or labels.get("persistentvolumeclaim"):
        return common + [
            "If Ceph is healthy but pods are still RO, check blocklist (`ceph osd blocklist ls`) and map impacted clients before restarting pods.",
        ]
    if "node" in lower or labels.get("node"):
        return common + [
            "Check node readiness transitions and kubelet logs around the incident window before proposing hardware action.",
        ]
    return common


def related_alert_groups(name, alerts, all_alerts):
    related = {}
    selectors = {}
    for key in ("namespace", "node", "pod", "instance", "job", "persistentvolumeclaim"):
        values = sorted({a.get("labels", {}).get(key) for a in alerts if a.get("labels", {}).get(key)})
        if values:
            selectors[key] = values
    for alert in all_alerts:
        labels = alert.get("labels", {})
        other = labels.get("alertname")
        if not other or other == name:
            continue
        for key, values in selectors.items():
            if labels.get(key) in values:
                related.setdefault(other, set()).add(f"{key}={labels[key]}")
    ordered = sorted(related.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    return ordered[:MAX_RELATED]


def firing_window(alerts):
    parsed = [parse_alert_time(a.get("startsAt")) for a in alerts]
    times = sorted(t for t in parsed if t is not None)
    if not times:
        return "unknown", "unknown"
    return times[0].isoformat(), times[-1].isoformat()


def build_issue(name, alerts, all_alerts):
    labels = alerts[0].get("labels", {})
    ann = alerts[0].get("annotations", {})
    fp = fingerprint(name, labels)
    severity = labels.get("severity", "unknown")
    oldest, newest = firing_window(alerts)

    where = " ".join(
        f"`{k}={labels[k]}`" for k in ("namespace", "node", "pod", "instance", "job") if labels.get(k)
    )
    lines = [
        f"## `{name}`",
        "",
        f"**Severity:** {severity}  ",
        f"**Firing instances:** {len(alerts)}  ",
        f"**Oldest firing since:** {oldest}  ",
        f"**Newest firing since:** {newest}  ",
        f"**Scope:** {where or 'cluster-wide'}",
        "",
    ]
    if ann.get("summary"):
        lines += ["### Summary", ann["summary"], ""]
    if ann.get("description"):
        lines += ["### Description", ann["description"], ""]
    if ann.get("runbook_url"):
        lines += [f"**Runbook:** {ann['runbook_url']}", ""]

    lines += ["### Evidence snapshot (from Alertmanager payload)", ""]
    for key in ("namespace", "node", "pod", "instance", "job", "persistentvolumeclaim"):
        vals = sorted({a.get("labels", {}).get(key) for a in alerts if a.get("labels", {}).get(key)})
        if vals:
            rendered = ", ".join(f"`{v}`" for v in vals[:8])
            extra = f" (+{len(vals) - 8} more)" if len(vals) > 8 else ""
            lines.append(f"- **{key}:** {rendered}{extra}")
    generators = sorted({a.get("generatorURL") for a in alerts if a.get("generatorURL")})
    if generators:
        lines += ["", "#### Source queries / generators", ""]
        for url in generators[:MAX_GENERATORS]:
            lines.append(f"- {url}")
        if len(generators) > MAX_GENERATORS:
            lines.append(f"- …and {len(generators) - MAX_GENERATORS} more")

    related = related_alert_groups(name, alerts, all_alerts)
    if related:
        lines += ["", "#### Correlated active alert groups", ""]
        for alertname, matches in related:
            hits = ", ".join(f"`{m}`" for m in sorted(matches))
            lines.append(f"- `{alertname}` via {hits}")

    lines += ["### Affected instances", ""]
    for a in alerts[:MAX_AFFECTED]:
        al = a.get("labels", {})
        ident = al.get("pod") or al.get("instance") or al.get("node") or al.get("namespace") or "—"
        lines.append(f"- `{ident}`")
    if len(alerts) > MAX_AFFECTED:
        lines.append(f"- …and {len(alerts) - MAX_AFFECTED} more")

    lines += [
        "",
        "### Required troubleshooting sequence (before hardware assumptions)",
        "",
    ]
    for idx, step in enumerate(triage_steps(name, labels), start=1):
        lines.append(f"{idx}. {step}")

    lines += [
        "",
        "### Resolution path",
        "",
        "1. Determine the **root cause** with evidence in this issue — do not just silence the alert.",
        "2. If the fix is GitOps, open a PR against `main` under `kubernetes/`.",
        "3. If physical/manual action is required, provide exact validated steps and why software-only triage was insufficient.",
        "4. If this alert is noise, propose a tuning PR for the alert rule itself.",
        "",
        "> Cluster is Flux-reconciled: changes must be committed to `main`, not applied live.",
        "",
        f"<!-- {MARKER}:{fp} -->",
        "_Filed automatically by the `alert-triage` CronJob._",
    ]
    title = f"[alert] {name}" + (f" — {len(alerts)} firing" if len(alerts) > 1 else "")
    return fp, title, "\n".join(lines), severity


def main():
    try:
        alerts = fetch_alerts()
    except (urllib.error.URLError, OSError) as exc:
        print(f"FATAL: cannot reach Alertmanager: {exc}", file=sys.stderr)
        return 1

    active = [a for a in alerts if eligible(a)]
    grouped = {}
    for a in active:
        grouped.setdefault(a["labels"]["alertname"], []).append(a)

    print(f"alertmanager: {len(alerts)} active, {len(active)} eligible, {len(grouped)} groups")

    if not grouped:
        print("nothing to file")
        return 0

    try:
        known = existing_fingerprints()
    except urllib.error.HTTPError as exc:
        print(f"FATAL: cannot list issues: {exc.code}", file=sys.stderr)
        return 1
    print(f"github: {len(known)} fingerprints already tracked")

    filed = 0
    for name, group in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
        if filed >= MAX_NEW_ISSUES:
            print(f"reached MAX_NEW_ISSUES={MAX_NEW_ISSUES}; deferring the rest to the next run")
            break
        fp, title, body, severity = build_issue(name, group, active)
        if fp in known:
            print(f"skip  {name} (already tracked, fp={fp})")
            continue
        if DRY_RUN:
            print(f"DRY   would file: {title} (fp={fp})")
            filed += 1
            continue
        payload = {"title": title, "body": body, "labels": [LABEL, f"severity:{severity}"]}
        try:
            issue = http(f"{API}/repos/{REPO}/issues", method="POST", body=payload, token=True)
        except urllib.error.HTTPError as exc:
            print(f"ERROR filing {name}: {exc.code} {exc.reason}", file=sys.stderr)
            continue
        num = issue["number"]
        print(f"filed #{num}: {title}")
        filed += 1

        if ASSIGNEE:
            try:
                http(
                    f"{API}/repos/{REPO}/issues/{num}/assignees",
                    method="POST",
                    body={"assignees": [ASSIGNEE]},
                    token=True,
                )
                print(f"      assigned #{num} -> {ASSIGNEE}")
            except urllib.error.HTTPError as exc:
                # Copilot agent may not be enabled on the repo; not fatal.
                print(f"      could not assign #{num} to {ASSIGNEE}: {exc.code}", file=sys.stderr)

    print(f"done: {filed} issue(s) filed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
