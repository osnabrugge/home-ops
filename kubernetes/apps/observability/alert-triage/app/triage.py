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


def eligible(alert):
    labels = alert.get("labels", {})
    name = labels.get("alertname", "")
    if not name or name in IGNORE:
        return False
    if SEVERITIES and labels.get("severity") not in SEVERITIES:
        return False
    if alert.get("status", {}).get("state") != "active":
        return False
    started = alert.get("startsAt", "")
    try:
        # normalise the fractional-second precision Alertmanager emits
        ts = re.sub(r"\.\d+", "", started).replace("Z", "+00:00")
        began = datetime.fromisoformat(ts)
    except ValueError:
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


def build_issue(name, alerts):
    labels = alerts[0].get("labels", {})
    ann = alerts[0].get("annotations", {})
    fp = fingerprint(name, labels)
    severity = labels.get("severity", "unknown")

    where = " ".join(
        f"`{k}={labels[k]}`" for k in ("namespace", "node", "pod", "instance", "job") if labels.get(k)
    )
    lines = [
        f"## `{name}`",
        "",
        f"**Severity:** {severity}  ",
        f"**Firing instances:** {len(alerts)}  ",
        f"**Firing since:** {alerts[0].get('startsAt', 'unknown')}  ",
        f"**Scope:** {where or 'cluster-wide'}",
        "",
    ]
    if ann.get("summary"):
        lines += ["### Summary", ann["summary"], ""]
    if ann.get("description"):
        lines += ["### Description", ann["description"], ""]
    if ann.get("runbook_url"):
        lines += [f"**Runbook:** {ann['runbook_url']}", ""]

    lines += ["### Affected instances", ""]
    for a in alerts[:15]:
        al = a.get("labels", {})
        ident = al.get("pod") or al.get("instance") or al.get("node") or al.get("namespace") or "—"
        lines.append(f"- `{ident}`")
    if len(alerts) > 15:
        lines.append(f"- …and {len(alerts) - 15} more")

    lines += [
        "",
        "### Requested of the agent",
        "",
        "1. Determine the **root cause** — do not just silence the alert.",
        "2. If the fix is a GitOps change, open a PR against `main` under `kubernetes/`.",
        "3. If it needs physical/manual action, comment with the exact steps and close as `not planned`.",
        "4. If this alert is pure noise, propose a tuning PR for the alert rule itself.",
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
        fp, title, body, severity = build_issue(name, group)
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
