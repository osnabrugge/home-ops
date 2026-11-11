import http.client
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile

CONFIG = Path("/etc/proxmox-datacenter-manager")
RECOVERY = "recovery@pdm"


def atomic_write(path, content, mode=0o640, group=33):
    if path.is_symlink():
        raise RuntimeError(f"Refusing a symlink at {path}")
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".bootstrap-")
    try:
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), mode)
            os.fchown(stream.fileno(), 0, group)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_settings():
    settings = json.loads(Path("/bootstrap/settings.json").read_text())
    for key in ("recovery_password", "oidc_client_secret"):
        if not isinstance(settings[key], str) or len(settings[key]) < 32:
            raise RuntimeError(f"Missing or insufficient {key}")
    if not re.fullmatch(r"[a-zA-Z0-9._-]+@authentik", settings["oidc_admin"]):
        raise RuntimeError("Invalid OIDC administrator identifier")
    endpoints = {
        "pve01": ["pve01.in.homeops.ca:8006"],
        "pve02": ["pve02.in.homeops.ca:8006"],
    }
    for remote in settings["remotes"]:
        if remote["id"] not in endpoints or remote["nodes"] != endpoints[remote["id"]]:
            raise RuntimeError("Unapproved remote; review its endpoint and permissions first")
        if set(remote) != {"type", "id", "nodes", "authid", "token", "web-url"}:
            raise RuntimeError("Unexpected remote fields; token creation is forbidden")
        if remote["type"] != "pve" or "!" not in remote["authid"] or not remote["token"]:
            raise RuntimeError("A pre-existing read-only API token is required")
    return settings


def initialize(settings):
    for path, owner, mode in [
        (CONFIG, 0, 0o1770),
        (Path("/run/proxmox-datacenter-manager"), 0, 0o1770),
        (Path("/var/log/proxmox-datacenter-manager"), 0, 0o755),
        (Path("/var/lib/proxmox-datacenter-manager"), 33, 0o755),
        (Path("/var/cache/proxmox-datacenter-manager"), 33, 0o755),
    ]:
        if path.is_symlink():
            raise RuntimeError(f"Refusing a symlink at {path}")
        path.mkdir(parents=True, exist_ok=True)
        os.chown(path, owner, 33)
        os.chmod(path, mode)
    subprocess.run(
        ["/usr/libexec/proxmox/proxmox-datacenter-privileged-api", "setup"],
        check=True,
    )
    users = CONFIG / "access/user.cfg"
    shadow = CONFIG / "access/shadow.json"
    acl = CONFIG / "access/acl.cfg"
    if not users.exists() and not shadow.exists() and not acl.exists():
        encrypted = subprocess.check_output(
            ["openssl", "passwd", "-6", "-stdin"],
            input=settings["recovery_password"].encode(),
        ).decode().strip()
        atomic_write(shadow, json.dumps({"recovery": encrypted}), 0o600, 0)
        atomic_write(users, f"user: {RECOVERY}\n\tenable true\n\n")
        atomic_write(
            acl,
            f"acl:1:/:{RECOVERY}:Administrator\n"
            f"acl:1:/:{settings['oidc_admin']}:Administrator\n",
        )
    elif not all(path.is_file() and not path.is_symlink() for path in (users, shadow, acl)):
        raise RuntimeError("Incomplete existing identity state; refusing to reset it")
    for source, target in [("tls.crt", "api.pem"), ("tls.key", "api.key")]:
        atomic_write(CONFIG / "auth" / target, (Path("/certificate") / source).read_text())
    print("Native setup complete; existing identities, keys and passwords preserved", flush=True)


class API:
    def __init__(self):
        self.headers = {"Content-Type": "application/json"}

    def request(self, method, path, body=None):
        connection = http.client.HTTPConnection("localhost", timeout=60)
        connection.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.sock.settimeout(60)
        connection.sock.connect("/run/proxmox-datacenter-manager/priv.sock")
        try:
            connection.request(
                method, "/api2/json/" + path,
                body=None if body is None else json.dumps(body),
                headers=self.headers,
            )
            response = connection.getresponse()
            payload = response.read()
            if response.status != 200:
                raise RuntimeError(f"PDM {method} {path} failed with HTTP {response.status}")
            result = json.loads(payload)
            cookie = response.getheader("Set-Cookie")
            if cookie:
                self.headers["Cookie"] = cookie.split(";", 1)[0]
            if result.get("success") is False:
                raise RuntimeError(f"PDM {method} {path} rejected the request")
            return result["data"]
        finally:
            connection.close()

    def login(self, password):
        data = self.request("POST", "access/ticket", {"username": RECOVERY, "password": password})
        if "Cookie" not in self.headers or data["username"] != RECOVERY:
            raise RuntimeError("Native authentication did not establish the expected session")
        self.headers["CSRFPreventionToken"] = data["CSRFPreventionToken"]


def configure(settings):
    api = API()
    api.login(settings["recovery_password"])
    desired = {
        "realm": "authentik",
        "issuer-url": "https://authentik.homeops.ca/application/o/pdm/",
        "client-id": "pdm",
        "client-key": settings["oidc_client_secret"],
        "username-claim": "preferred_username",
        "autocreate": True,
        "default": True,
        "scopes": "email profile",
    }
    realms = api.request("GET", "config/access/openid")
    existing = next((realm for realm in realms if realm["realm"] == "authentik"), None)
    if existing is None:
        api.request("POST", "config/access/openid", desired)
    elif any(existing.get(key) != value for key, value in desired.items()):
        raise RuntimeError("Existing OIDC realm differs from its declared policy; refusing to overwrite")
    remotes = api.request("GET", "remotes/remote")
    for remote in settings["remotes"]:
        existing = next((item for item in remotes if item["id"] == remote["id"]), None)
        if existing is None:
            api.request("POST", "remotes/remote", remote)
        elif any(existing.get(key) != value for key, value in remote.items() if key != "token"):
            raise RuntimeError("Existing remote differs from its declared policy; refusing to overwrite")
    print(json.dumps({"oidc_realm": "authentik", "remotes": [r["id"] for r in settings["remotes"]]}), flush=True)


if __name__ == "__main__":
    settings = load_settings()
    if sys.argv[1:] == ["initialize"]:
        initialize(settings)
    elif sys.argv[1:] == ["configure"]:
        configure(settings)
    else:
        raise RuntimeError("Expected initialize or configure")
