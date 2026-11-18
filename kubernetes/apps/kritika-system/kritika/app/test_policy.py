import copy
import hashlib
import hmac
import http.client
import json
import threading
import unittest
from unittest.mock import patch

import policy


FREE = {
    "id": policy.MODEL,
    "pricing": {"prompt": "0", "completion": "0"},
    "supported_parameters": ["tools", "tool_choice", "max_tokens"],
    "context_length": 256000,
}


class ModelPolicyTests(unittest.TestCase):
    def test_only_exact_current_zero_priced_tool_model(self):
        self.assertEqual(policy.approved_model({"data": [FREE]}), FREE)
        for price in ("0.1", "-0.1", "NaN", "Infinity", None):
            with self.subTest(price=price):
                entry = copy.deepcopy(FREE)
                entry["pricing"]["request"] = price
                with self.assertRaises(policy.Refused):
                    policy.approved_model({"data": [entry]})
        for entry in (
            {**FREE, "id": policy.MODEL.removesuffix(":free")},
            {**FREE, "pricing": {}},
            {**FREE, "supported_parameters": []},
            {**FREE, "context_length": 8000},
        ):
            with self.subTest(entry=entry), self.assertRaises(policy.Refused):
                policy.approved_model({"data": [entry]})

    def test_no_alias_paid_router_fallback_or_provider_override(self):
        base = {"model": policy.MODEL, "messages": [{"role": "user", "content": "fixture"}]}
        for model in ("openrouter/auto", "~cohere-latest", "cohere/paid", [policy.MODEL], None):
            with self.subTest(model=model), self.assertRaises(policy.Refused):
                policy.completion({**base, "model": model})
        for extra in (
            {"models": [policy.MODEL, "paid/model"]},
            {"provider": {"allow_fallbacks": True}},
            {"route": "fallback"},
            {"plugins": [{"id": "web"}]},
            {"stream": True},
            {"max_tokens": 0},
            {"max_tokens": True},
        ):
            with self.subTest(extra=extra), self.assertRaises(policy.Refused):
                policy.completion({**base, **extra})

    def test_output_bound_and_provider_zero_price_are_unconditional(self):
        out = policy.completion({
            "model": policy.MODEL, "messages": [{}], "max_tokens": 16384,
            "cache_control": {"type": "ephemeral"},
        })
        self.assertEqual(out["max_tokens"], policy.MAX_OUTPUT)
        self.assertNotIn("cache_control", out)
        self.assertEqual(out["provider"], {
            "allow_fallbacks": False, "require_parameters": True,
            "max_price": {"prompt": 0, "completion": 0},
        })


class HTTPPolicyTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.catalogue = {"data": [copy.deepcopy(FREE), {"id": "paid/model"}]}
        self.reply = {"model": policy.MODEL, "choices": [], "usage": {"cost": 0}}
        self.mock = patch("policy.request_json", side_effect=self.upstream)
        self.mock.start()
        self.servers = []
        self.threads = []
        for kind in ("models", "hooks"):
            server = policy.HTTPServer(("127.0.0.1", 0), policy.Handler)
            server.kind = kind
            server.gateway_key = "synthetic-gateway-key"
            server.webhook_secret = "synthetic-webhook-key"
            server.openrouter_key = "synthetic-provider-key"
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            self.servers.append(server)
            self.threads.append(thread)

    def tearDown(self):
        for server, thread in zip(self.servers, self.threads):
            server.shutdown()
            server.server_close()
            thread.join()
        self.mock.stop()

    def upstream(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.endswith("/hooks/github"):
            return 204, b""
        value = self.catalogue if url.endswith("/models") else self.reply
        return 200, json.dumps(value).encode()

    def request(self, port, path, body=None, headers=None, method=None):
        connection = http.client.HTTPConnection(*self.servers[port].server_address, timeout=5)
        headers = headers or {}
        if body is not None and not isinstance(body, bytes):
            body = json.dumps(body).encode()
        connection.request(method or ("POST" if body is not None else "GET"), path, body, headers)
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        connection.close()
        return result

    def model(self, **overrides):
        return self.request(
            0, "/v1/chat/completions",
            {"model": policy.MODEL, "messages": [{"role": "user", "content": "public synthetic fixture"}],
             **overrides},
            {"Authorization": "Bearer synthetic-gateway-key"},
        )

    def review_tools(self):
        return [
            {"type": "function", "function": {
                "name": "read_file", "parameters": {"type": "object"},
            }},
            {"type": "function", "function": {
                "name": "submit_review", "parameters": {
                    "type": "object", "required": ["summary", "findings"],
                    "properties": {"summary": {"type": "object"}, "findings": {"type": "array"}},
                },
            }},
        ]

    def hook(self, payload, event="ping", valid=True):
        body = json.dumps(payload).encode()
        signature = hmac.new(b"synthetic-webhook-key", body, hashlib.sha256).hexdigest()
        return self.request(
            1, "/hooks/github", body,
            {"X-GitHub-Event": event,
             "X-Hub-Signature-256": "sha256=" + (signature if valid else "invalid")},
        )

    def test_anonymous_and_embeddings_never_reach_provider(self):
        self.assertEqual(self.request(0, "/v1/models")[0], 401)
        self.assertEqual(self.request(0, "/v1/embeddings", {"model": policy.MODEL})[0], 404)
        self.assertEqual(self.calls, [])

    def test_filtered_catalogue_and_authorized_free_completion(self):
        status, response = self.request(
            0, "/v1/models", headers={"Authorization": "Bearer synthetic-gateway-key"}
        )
        self.assertEqual(status, 200)
        self.assertEqual([m["id"] for m in response["data"]], [policy.MODEL])
        self.assertEqual(self.model(max_tokens=16384)[0], 200)
        outgoing = json.loads(self.calls[-1][1]["data"])
        self.assertEqual(outgoing["max_tokens"], policy.MAX_OUTPUT)
        self.assertEqual(outgoing["provider"]["max_price"], {"prompt": 0, "completion": 0})

    def test_empty_tool_results_keep_their_identity_and_do_not_mutate_input(self):
        for empty in ({"content": ""}, {"content": None}, {}):
            messages = [
                {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "grep_fixture", "type": "function", "function": {
                        "name": "grep", "arguments": '{"pattern":"no-match"}',
                    }},
                    {"id": "other_fixture", "type": "function", "function": {
                        "name": "grep", "arguments": '{"pattern":"match"}',
                    }},
                ]},
                {"role": "tool", "tool_call_id": "grep_fixture", **empty},
                {"role": "tool", "tool_call_id": "other_fixture", "content": "actual output"},
                {"role": "user", "content": ""},
            ]
            original = copy.deepcopy(messages)
            with self.subTest(empty=empty):
                policy.completion({"model": policy.MODEL, "messages": messages})
                self.assertEqual(messages, original)
                self.assertEqual(self.model(messages=messages)[0], 200)
                outgoing = json.loads(self.calls[-1][1]["data"])
                self.assertIn("no output", outgoing["messages"][1]["content"])
                self.assertEqual(outgoing["messages"][1]["tool_call_id"], "grep_fixture")
                self.assertEqual(outgoing["messages"][0], original[0])
                self.assertEqual(outgoing["messages"][2:], original[2:])

    def test_paid_fallback_and_repriced_model_fail_before_inference(self):
        self.assertEqual(self.model(model="paid/model")[0], 403)
        self.assertEqual(self.model(models=[policy.MODEL, "paid/model"])[0], 403)
        self.assertEqual(self.calls, [])
        self.catalogue["data"][0]["pricing"]["prompt"] = "0.01"
        self.assertEqual(self.model()[0], 503)
        self.assertTrue(all(call[0].endswith("/models") for call in self.calls))

    def test_missing_cost_nonzero_cost_and_changed_model_are_not_accepted(self):
        for reply in (
            {"model": policy.MODEL, "usage": {}},
            {"model": policy.MODEL, "usage": {"cost": 0.1}},
            {"model": "paid/model", "usage": {"cost": 0}},
        ):
            self.reply = reply
            with self.subTest(reply=reply):
                self.assertEqual(self.model()[0], 502)

    def test_native_forced_submission_is_visibly_incomplete_not_a_clean_review(self):
        submitted = {
            "summary": {"headline": "Synthetic change", "take": "- Changes a fixture.", "praise": []},
            "findings": [{"title": "Preserve the model's finding"}],
        }
        self.reply["choices"] = [{"message": {"tool_calls": [{
            "id": "submit_fixture", "type": "function",
            "function": {"name": "submit_review", "arguments": json.dumps(submitted)},
        }]}}]
        self.assertEqual(self.model()[1], self.reply)
        messages = [{"role": "user", "content":
                     "Call submit_review now with what you have, and call nothing else."}]
        status, response = self.model(messages=messages, tools=self.review_tools())
        self.assertEqual(status, 200)
        call = response["choices"][0]["message"]["tool_calls"][0]
        result = json.loads(call["function"]["arguments"])
        self.assertIn("Pilot limit notice", result["summary"]["take"])
        self.assertIn("incomplete", result["summary"]["take"])
        self.assertTrue(result["summary"]["take"].startswith(submitted["summary"]["take"]))
        self.assertEqual(result["findings"], submitted["findings"])
        self.assertEqual(call["id"], "submit_fixture")
        self.reply["usage"]["cost"] = 0.1
        self.assertEqual(self.model(messages=messages, tools=self.review_tools())[0], 502)

    def test_native_wrap_up_advertises_only_existing_submit_schema_with_required_choice(self):
        tools = self.review_tools()
        original = copy.deepcopy(tools)
        self.assertEqual(self.model(tools=tools, tool_choice="auto")[0], 200)
        ordinary = json.loads(self.calls[-1][1]["data"])
        self.assertEqual(ordinary["tools"], tools)
        self.assertEqual(ordinary["tool_choice"], "auto")
        self.assertEqual(self.model(
            tools=tools, tool_choice="auto",
            messages=[{"role": "user", "content": policy.SUBMIT_NOW}],
        )[0], 200)
        forced = json.loads(self.calls[-1][1]["data"])
        self.assertEqual(forced["tools"], [tools[1]])
        self.assertEqual(forced["tool_choice"], "required")
        self.assertEqual(forced["provider"]["max_price"], {"prompt": 0, "completion": 0})
        self.assertEqual(tools, original)

    def test_native_wrap_up_without_one_existing_submit_definition_fails_before_upstream(self):
        tools = self.review_tools()
        for definitions in ([], tools[:1], [tools[1], tools[1]]):
            with self.subTest(definitions=definitions):
                self.calls.clear()
                self.assertEqual(self.model(
                    tools=definitions,
                    messages=[{"role": "user", "content": policy.SUBMIT_NOW}],
                )[0], 400)
                self.assertEqual(self.calls, [])

    def test_forced_review_notice_never_repairs_invalid_submission_arguments(self):
        for arguments in ("not json", "null", '{"summary":{"take":null}}'):
            self.reply["choices"] = [{"message": {"tool_calls": [{
                "function": {"name": "submit_review", "arguments": arguments},
            }]}}]
            with self.subTest(arguments=arguments):
                self.assertEqual(self.model(messages=[{"role": "user", "content":
                    "Call submit_review now with what you have, and call nothing else."}],
                    tools=self.review_tools())[1],
                    self.reply)

    def test_signed_ping_is_forwarded_unsigned_or_invalid_is_not(self):
        self.assertEqual(self.hook({}, valid=False)[0], 401)
        self.assertEqual(self.calls, [])
        status, response = self.hook({})
        self.assertEqual(status, 202)
        self.assertTrue(response["accepted"])
        self.assertEqual(self.calls[0][0], "http://kritika-api-direct:8080/hooks/github")

    def test_public_repository_allowlist_and_private_rejection(self):
        repo = {
            "full_name": policy.REPOSITORY, "private": False,
            "visibility": "public", "owner": {"login": "osnabrugge"},
        }
        for payload in (
            {"repository": {**repo, "full_name": "osnabrugge/other"}},
            {"repository": {**repo, "private": True}},
            {"repository": {**repo, "visibility": "private"}},
            {"repository": []},
        ):
            with self.subTest(payload=payload):
                self.assertIn(self.hook(payload, "pull_request")[0], (400, 403))
        self.assertEqual(self.calls, [])
        self.assertEqual(self.hook({"repository": repo}, "pull_request")[0], 202)

    def test_public_listener_has_no_dashboard_api_or_model_route(self):
        for path in ("/", "/api/v1/meta", "/v1/models", "/hooks/github"):
            self.assertEqual(self.request(1, path)[0], 404)
        self.assertEqual(self.request(1, "/v1/chat/completions", {"model": policy.MODEL})[0], 404)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
