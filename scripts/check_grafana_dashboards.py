import argparse
from http.client import HTTPException
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


FETCH_TIMEOUT = 30
MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024


def dashboard_urls(content: str, source: str) -> set[str]:
    documents = subprocess.check_output(
        ["yq", "-o=json", "-I=0", ".", "-"], input=content, text=True
    )
    urls = set()
    for line in documents.splitlines():
        document = json.loads(line)
        if document is None:
            continue
        if not isinstance(document, dict):
            raise ValueError(f"{source}: expected a manifest object")
        if document.get("kind") != "GrafanaDashboard":
            continue
        spec = document.get("spec")
        if not isinstance(spec, dict):
            raise ValueError(f"{source}: GrafanaDashboard spec must be an object")
        if "url" not in spec:
            continue
        url = spec["url"]
        if not isinstance(url, str) or not url.strip():
            raise ValueError(f"{source}: GrafanaDashboard spec.url must be a nonempty string")
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError(f"{source}: GrafanaDashboard spec.url must be an HTTP(S) URL")
        urls.add(url)
    return urls


def changed_dashboard_urls(base_ref: str) -> set[str]:
    changes = subprocess.check_output(
        ["git", "diff", "--name-status", "--diff-filter=AM", "--no-renames", "-z",
         base_ref, "--", "kubernetes/**/*.yaml", "kubernetes/**/*.yml"],
        text=True,
    )
    if not changes:
        return set()
    entries = changes.rstrip("\0").split("\0")
    urls = set()
    for index in range(0, len(entries), 2):
        status, path = entries[index:index + 2]
        current = dashboard_urls(Path(path).read_text(), path)
        previous = set()
        if status != "A":
            source = f"{base_ref}:{path}"
            content = subprocess.check_output(["git", "show", source], text=True)
            previous = dashboard_urls(content, source)
        urls.update(current - previous)
    return urls


def reject_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}")


def fetch_dashboard(url: str) -> tuple[str, int]:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=FETCH_TIMEOUT) as response:
        content = response.read(MAX_DOWNLOAD_BYTES + 1)
    if len(content) > MAX_DOWNLOAD_BYTES:
        raise ValueError("Dashboard download exceeds 10 MiB")
    dashboard = json.loads(content, parse_constant=reject_constant)
    if not isinstance(dashboard, dict):
        raise ValueError("Dashboard JSON must be an object")
    title = dashboard.get("title")
    panels = dashboard.get("panels")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Dashboard JSON must have a nonempty title")
    if not isinstance(panels, list) or not all(isinstance(panel, dict) for panel in panels):
        raise ValueError("Dashboard JSON must have a panels array of objects")
    return title, len(panels)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch and parse added or changed GrafanaDashboard URLs."
    )
    parser.add_argument("--base-ref", help="Compare changed manifests against this Git ref")
    parser.add_argument("manifests", nargs="*", type=Path)
    args = parser.parse_args()
    if bool(args.base_ref) == bool(args.manifests):
        parser.error("provide either --base-ref or one or more manifest paths")
    if args.base_ref:
        urls = changed_dashboard_urls(args.base_ref)
    else:
        urls = set()
        for path in args.manifests:
            urls.update(dashboard_urls(path.read_text(), str(path)))
    if not urls:
        print("No added or changed GrafanaDashboard download URLs.")
    for url in sorted(urls):
        print(f"Checking {url}", flush=True)
        title, panels = fetch_dashboard(url)
        print(f"Valid dashboard: {title!r}, {panels} top-level panels")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, HTTPException, subprocess.CalledProcessError) as error:
        print(f"Grafana dashboard check failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
