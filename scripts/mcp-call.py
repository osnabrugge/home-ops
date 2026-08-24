#!/usr/bin/env python3
"""Minimal streamable-HTTP MCP client for poking toolhive endpoints from the CLI."""
import json
import sys
import urllib.request

URL = sys.argv[1]
METHOD = sys.argv[2] if len(sys.argv) > 2 else "tools/list"
PARAMS = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
SESSION = {"id": None}


def rpc(method, params, notify=False):
    body = {"jsonrpc": "2.0", "method": method, "params": params}
    if not notify:
        body["id"] = 1
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **({"Mcp-Session-Id": SESSION["id"]} if SESSION["id"] else {}),
            "MCP-Protocol-Version": "2024-11-05",
        },
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        if not SESSION["id"]:
            SESSION["id"] = r.headers.get("Mcp-Session-Id")
        if notify:
            return None
        # The proxy answers as SSE and holds the stream open, so read line by
        # line and return on the first event instead of waiting for EOF.
        if "text/event-stream" in (r.headers.get("Content-Type") or ""):
            for raw_line in r:
                line = raw_line.decode().strip()
                if line.startswith("data:"):
                    return json.loads(line[5:].strip())
            return None
        body_text = r.read().decode()
    return json.loads(body_text) if body_text.strip() else None


rpc("initialize", {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "cli", "version": "1"},
})
rpc("notifications/initialized", {}, notify=True)
print(json.dumps(rpc(METHOD, PARAMS), indent=2)[:6000])
