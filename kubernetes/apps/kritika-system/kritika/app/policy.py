"""Fail-closed, single-model OpenRouter and signed, public-repository webhook gate."""

import hashlib
import hmac
import json
import os
import threading
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, HTTPServer


MODEL = "cohere/north-mini-code:free"
REPOSITORY = "osnabrugge/home-ops"
API = "https://openrouter.ai/api/v1"
MAX_BODY = 128 * 1024
MAX_REPLY = 4 * 1024 * 1024
MAX_OUTPUT = 2048
FIELDS = {
    "model", "messages", "tools", "tool_choice", "parallel_tool_calls",
    "temperature", "top_p", "top_k", "min_p", "seed", "stop",
    "frequency_penalty", "presence_penalty", "max_tokens",
    "max_completion_tokens", "response_format", "reasoning",
    "include_reasoning", "stream", "usage", "cache_control",
}
EVENTS = {
    "pull_request", "pull_request_review", "pull_request_review_comment",
    "issue_comment", "push", "repository",
}


class Refused(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message


def zero(value):
    try:
        number = Decimal(str(value))
        return number.is_finite() and number == 0
    except InvalidOperation:
        return False


def approved_model(catalogue):
    if not isinstance(catalogue, dict) or not isinstance(catalogue.get("data"), list):
        raise Refused(503, "Invalid live model catalogue")
    model = next(
        (m for m in catalogue["data"] if isinstance(m, dict) and m.get("id") == MODEL),
        None,
    )
    if model is None:
        raise Refused(503, "The explicit free model is not in the live catalogue")
    prices = model.get("pricing", {})
    if not isinstance(prices, dict) or not {"prompt", "completion"} <= prices.keys() or not all(
        zero(p) for p in prices.values()
    ):
        raise Refused(503, "The explicit model is not currently entirely zero-priced")
    if not {"tools", "tool_choice", "max_tokens"} <= set(
        model.get("supported_parameters", [])
    ) or model.get("context_length", 0) < 32768:
        raise Refused(503, "The free model no longer meets the pilot's tool/context requirements")
    return model


def completion(payload):
    if not isinstance(payload, dict) or payload.get("model") != MODEL:
        raise Refused(403, "Only the explicit approved :free model is permitted")
    if set(payload) - FIELDS:
        raise Refused(403, "Fallbacks, aliases, routing overrides and unknown fields are forbidden")
    if payload.get("stream", False) is not False:
        raise Refused(400, "Streaming is disabled so zero-cost usage can be checked")
    if not isinstance(payload.get("messages"), list) or not payload["messages"]:
        raise Refused(400, "A nonempty messages array is required")
    out = dict(payload)
    requested = out.pop("max_completion_tokens", out.get("max_tokens", MAX_OUTPUT))
    if not isinstance(requested, int) or isinstance(requested, bool) or requested < 1:
        raise Refused(400, "Invalid output token bound")
    out["max_tokens"] = min(requested, MAX_OUTPUT)
    out.pop("cache_control", None)
    out["usage"] = {"include": True}
    out["provider"] = {
        "allow_fallbacks": False,
        "require_parameters": True,
        "max_price": {"prompt": 0, "completion": 0},
    }
    return out


def approved_hook(body, headers, secret):
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(headers.get("X-Hub-Signature-256", ""), expected):
        raise Refused(401, "A valid GitHub SHA-256 signature is required")
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise Refused(400, "Invalid JSON") from None
    if not isinstance(payload, dict):
        raise Refused(400, "Expected a webhook object")
    event = headers.get("X-GitHub-Event", "")
    if event == "ping":
        return
    repo = payload.get("repository") or {}
    if not isinstance(repo, dict) or not isinstance(repo.get("owner", {}), dict):
        raise Refused(400, "Invalid repository object")
    owner = repo.get("owner", {})
    if (
        event not in EVENTS
        or repo.get("full_name") != REPOSITORY
        or owner.get("login") != "osnabrugge"
        or repo.get("private") is not False
        or repo.get("visibility", "public") != "public"
    ):
        raise Refused(403, "Only signed events for the approved public repository are accepted")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def request_json(url, *, data=None, headers=None, timeout=15):
    request = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with OPENER.open(request, timeout=timeout) as response:
            raw = response.read(MAX_REPLY + 1)
            if len(raw) > MAX_REPLY:
                raise Refused(502, "Upstream reply exceeds the pilot bound")
            return response.status, raw
    except urllib.error.HTTPError as error:
        raise Refused(error.code if error.code in (429, 503) else 502,
                      "The approved upstream refused the request; no fallback attempted") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise Refused(503, "The approved upstream is unavailable; no fallback attempted") from None


def catalogue():
    _, raw = request_json(API + "/models")
    try:
        return approved_model(json.loads(raw))
    except (ValueError, KeyError, TypeError):
        raise Refused(503, "Invalid live model catalogue") from None


class Handler(BaseHTTPRequestHandler):
    server_version = "kritika-policy"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *args):
        pass

    def send(self, status, body):
        raw = json.dumps(body, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def fail(self, error):
        self.send(error.status, {"error": {"message": error.message}})

    def authorized(self):
        expected = "Bearer " + self.server.gateway_key
        if not hmac.compare_digest(self.headers.get("Authorization", ""), expected):
            raise Refused(401, "A local gateway credential is required")

    def body(self):
        lengths = self.headers.get_all("Content-Length", [])
        if self.headers.get("Transfer-Encoding") or len(lengths) != 1:
            raise Refused(400, "Exactly one Content-Length is required")
        try:
            length = int(lengths[0])
        except ValueError:
            raise Refused(400, "Invalid Content-Length") from None
        if length < 1 or length > MAX_BODY:
            raise Refused(413, "Request exceeds the pilot bound")
        body = self.rfile.read(length)
        if len(body) != length:
            raise Refused(400, "Incomplete request")
        return body

    def do_GET(self):
        try:
            if self.path == "/healthz":
                self.send(200, {"status": "ok"})
            elif self.server.kind == "models" and self.path == "/v1/models":
                self.authorized()
                self.send(200, {"object": "list", "data": [catalogue()]})
            else:
                raise Refused(404, "Not found")
        except Refused as error:
            self.fail(error)

    def do_POST(self):
        try:
            if self.server.kind == "hooks" and self.path == "/hooks/github":
                body = self.body()
                approved_hook(body, self.headers, self.server.webhook_secret)
                headers = {
                    name: self.headers[name]
                    for name in ("X-Hub-Signature-256", "X-GitHub-Event", "X-GitHub-Delivery")
                    if name in self.headers
                }
                headers["Content-Type"] = "application/json"
                request_json(
                    "http://kritika-api-direct:8080/hooks/github", data=body, headers=headers
                )
                self.send(202, {"accepted": True})
            elif self.server.kind == "models" and self.path == "/v1/chat/completions":
                self.authorized()
                payload = completion(json.loads(self.body()))
                catalogue()
                status, raw = request_json(
                    API + "/chat/completions",
                    data=json.dumps(payload).encode(),
                    headers={
                        "Authorization": "Bearer " + self.server.openrouter_key,
                        "Content-Type": "application/json",
                    },
                    timeout=120,
                )
                reply = json.loads(raw)
                if (
                    reply.get("model") != MODEL
                    or not zero(reply.get("usage", {}).get("cost"))
                ):
                    raise Refused(502, "Upstream did not attest the approved model at zero cost")
                self.send(status, reply)
            else:
                raise Refused(404, "Not found")
        except Refused as error:
            self.fail(error)
        except (ValueError, UnicodeDecodeError, KeyError, TypeError, AttributeError):
            self.fail(Refused(400, "Invalid JSON or upstream response"))


def main():
    settings = {
        "gateway_key": os.environ["KRITIKA_GATEWAY_KEY"],
        "webhook_secret": os.environ["GITHUB_WEBHOOK_SECRET"],
        "openrouter_key": os.environ["OPENROUTER_API_KEY"],
    }
    if not all(settings.values()):
        raise RuntimeError("The three required credentials must be nonempty")
    servers = []
    for port, kind in ((8080, "models"), (8081, "hooks")):
        server = HTTPServer(("0.0.0.0", port), Handler)
        server.kind = kind
        for key, value in settings.items():
            setattr(server, key, value)
        servers.append(server)
    threading.Thread(target=servers[1].serve_forever, daemon=True).start()
    print("Explicit free-model and signed public-repository gates listening", flush=True)
    servers[0].serve_forever()


if __name__ == "__main__":
    main()
