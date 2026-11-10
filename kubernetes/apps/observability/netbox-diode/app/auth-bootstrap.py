import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request


CLIENTS = (
    ("DIODE_INGEST", "diode:ingest"),
    ("DIODE_TO_NETBOX", "netbox:read netbox:write"),
    ("NETBOX_TO_DIODE", "diode:read diode:write"),
)


class BootstrapError(RuntimeError):
    pass


class RequestFailure(BootstrapError):
    def __init__(self, method, url, status):
        self.status = status
        super().__init__(f"{method} {urllib.parse.urlsplit(url).path}: HTTP {status}")


def request_json(url, method="GET", data=None, form=False):
    headers = {"Accept": "application/json"}
    body = None
    if data is not None:
        body = (
            urllib.parse.urlencode(data).encode()
            if form
            else json.dumps(data).encode()
        )
        headers["Content-Type"] = (
            "application/x-www-form-urlencoded" if form else "application/json"
        )
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read(65537)
    except urllib.error.HTTPError as error:
        raise RequestFailure(method, url, error.code) from None
    except urllib.error.URLError:
        raise BootstrapError("OAuth service connection failed") from None
    if len(raw) > 65536:
        raise BootstrapError("OAuth response exceeded its size limit")
    try:
        result = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise BootstrapError("OAuth service returned invalid JSON") from None
    if not isinstance(result, dict):
        raise BootstrapError("OAuth service returned a non-object response")
    return result


def ensure_client(admin_url, token_url, client_id, client_secret, scope):
    if not client_id or len(client_secret) < 16:
        raise BootstrapError("Client ID is missing or its secret is too short")
    client_url = f"{admin_url.rstrip('/')}/clients/{urllib.parse.quote(client_id, safe='')}"
    created = False
    try:
        client = request_json(client_url)
    except RequestFailure as error:
        if error.status != 404:
            raise
        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_types": ["client_credentials"],
            "response_types": ["token"],
            "scope": scope,
            "token_endpoint_auth_method": "client_secret_post",
        }
        try:
            client = request_json(f"{admin_url.rstrip('/')}/clients", "POST", payload)
            created = True
        except RequestFailure as conflict:
            if conflict.status != 409:
                raise
            client = request_json(client_url)

    expected = {
        "client_id": client_id,
        "grant_types": ["client_credentials"],
        "response_types": ["token"],
        "token_endpoint_auth_method": "client_secret_post",
    }
    for field, value in expected.items():
        if client.get(field) != value:
            raise BootstrapError(f"Existing OAuth client has unexpected {field}")
    actual_scope = client.get("scope")
    if not isinstance(actual_scope, str) or set(actual_scope.split()) != set(scope.split()):
        raise BootstrapError("Existing OAuth client has unexpected scopes")

    token = request_json(
        token_url,
        "POST",
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": scope,
        },
        form=True,
    )
    token_scope = token.get("scope")
    if (
        not isinstance(token.get("access_token"), str)
        or not token["access_token"]
        or not isinstance(token.get("token_type"), str)
        or token["token_type"].lower() != "bearer"
        or type(token.get("expires_in")) is not int
        or token["expires_in"] <= 0
        or not isinstance(token_scope, str)
        or set(token_scope.split()) != set(scope.split())
    ):
        raise BootstrapError("OAuth client did not receive a valid scoped token")
    return "created" if created else "verified"


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        admin_url = os.environ["HYDRA_ADMIN_URL"]
        token_url = os.environ["HYDRA_TOKEN_URL"]
        clients = [
            (prefix, os.environ[f"{prefix}_CLIENT_ID"], os.environ[f"{prefix}_CLIENT_SECRET"], scope)
            for prefix, scope in CLIENTS
        ]
        if len({client[1] for client in clients}) != len(clients):
            raise BootstrapError("OAuth roles must use distinct client IDs")
        if any(not client_id or len(secret) < 16 for _, client_id, secret, _ in clients):
            raise BootstrapError("Client ID is missing or its secret is too short")
        for prefix, client_id, secret, scope in clients:
            action = ensure_client(admin_url, token_url, client_id, secret, scope)
            logging.info("%s client %s; scoped token verified", prefix, action)
    except (BootstrapError, KeyError) as error:
        logging.error("Diode OAuth bootstrap failed: %s", error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
