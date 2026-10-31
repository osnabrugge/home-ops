import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request

POLICY = {
    "key_alias": "home-ops-readonly-triage",
    "models": ["local-triage"],
    "max_parallel_requests": 1,
    "rpm_limit": 6,
    "tpm_limit": 8192,
    "allowed_routes": ["/v1/chat/completions", "/v1/models", "/mcp", "/mcp/"],
    "object_permission": {
        "mcp_servers": ["kubesearch"],
        "mcp_tool_permissions": {"kubesearch": ["kubesearch_search_releases"]},
        "mcp_tool_search_enabled": False,
    },
}


def policy_matches(info):
    for field, value in POLICY.items():
        if field != "object_permission" and info.get(field) != value:
            return False
    actual = info.get("object_permission")
    if not isinstance(actual, dict):
        return False
    expected = POLICY["object_permission"]
    if any(actual.get(field) != value for field, value in expected.items()):
        return False
    return not any(
        value not in (None, [], {}, False)
        for field, value in actual.items()
        # The native API returns its row ID alongside the actual grants.
        if field not in expected and field != "object_permission_id"
    )


def request(base, master_key, path, body=None):
    req = urllib.request.Request(
        base + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={
            "Authorization": "Bearer " + master_key,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def main():
    base = os.environ["LITELLM_BASE_URL"].rstrip("/")
    master = os.environ["LITELLM_MASTER_KEY"]
    key = os.environ["TRIAGE_API_KEY"]
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    info_path = "/key/info?" + urllib.parse.urlencode({"key": key_hash})
    try:
        result = request(base, master, info_path)
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise RuntimeError(f"Key lookup failed with HTTP {error.code}") from None
        request(base, master, "/key/generate", {**POLICY, "key": key})
        result = request(base, master, info_path)
    info = result["info"]
    if info["key_alias"] != POLICY["key_alias"]:
        raise RuntimeError("Key ownership mismatch; refusing to overwrite")
    if info.get("blocked"):
        raise RuntimeError("Managed key is blocked; refusing to undo revocation")
    if not policy_matches(info):
        request(base, master, "/key/update", {**POLICY, "key": key})
        info = request(base, master, info_path)["info"]
    if not policy_matches(info):
        raise RuntimeError("Declared key restrictions did not persist")
    print(json.dumps({"status": "RECONCILED", "alias": POLICY["key_alias"], "policy_verified": True}))


if __name__ == "__main__":
    main()
