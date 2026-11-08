import contextlib
import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from worker import run, scrape_status, validate_report, validate_tool


class WorkerGuardTests(unittest.TestCase):
    def test_allowed_evidence_tools(self):
        validate_tool("smartctl_scrape_status", {})
        validate_tool("kubesearch_search_releases", {"query": "smartctl-exporter", "limit": 1})

    def test_unauthorized_tools_and_arguments_fail(self):
        cases = [
            ("kubectl_delete", {"namespace": "rook-ceph"}),
            ("repo_cleanup", {}),
            ("smartctl_scrape_status", {"host": "other"}),
            ("kubesearch_search_releases", {"query": "other", "limit": 1}),
            ("kubesearch_search_releases", {"query": "smartctl-exporter", "limit": 100}),
        ]
        for name, arguments in cases:
            with self.subTest(name=name, arguments=arguments), self.assertRaises(RuntimeError):
                validate_tool(name, arguments)

    def test_health_requires_both_proofs(self):
        for up, status, result in [(1, 200, "NO_ACTIVE_FAILURE"), (0, 500, "ESCALATED"), (1, 500, "ESCALATED"), (0, 200, "ESCALATED"), (1, None, "ESCALATED"), (0, None, "ESCALATED")]:
            validate_report({"status": result, "summary": "Observed evidence", "actions_taken": []}, {"up": up, "http_status": status})

    def test_transport_failure_is_evidence_not_a_crash_or_success(self):
        sample = {"status": "success", "data": {"result": [{"value": [0, "0"]}]}}
        for error in [TimeoutError("timed out"), urllib.error.URLError(TimeoutError("timed out")), ConnectionResetError("reset")]:
            with self.subTest(error=error), patch("worker.json_request", return_value=sample), patch("worker.urllib.request.urlopen", side_effect=error):
                evidence = scrape_status("http://example.invalid")
                self.assertEqual(evidence["up"], 0)
                self.assertIsNone(evidence["http_status"])
                self.assertEqual(evidence["unregistered_descriptor_errors"], 0)
                self.assertEqual(evidence["transport_error"], type(getattr(error, "reason", error)).__name__)
                validate_report({"status": "ESCALATED", "summary": "The scrape could not be reached", "actions_taken": []}, evidence)

    def test_missing_authoritative_sample_still_fails_closed(self):
        sample = {"status": "success", "data": {"result": []}}
        with patch("worker.json_request", return_value=sample), patch("worker.urllib.request.urlopen") as request:
            with self.assertRaisesRegex(RuntimeError, "No authoritative"):
                scrape_status("http://example.invalid")
            request.assert_not_called()

    def test_false_success_invented_actions_and_missing_fields_fail(self):
        reports = [
            {"status": "NO_ACTIVE_FAILURE", "summary": "Fine", "actions_taken": []},
            {"status": "ESCALATED", "summary": "Fixed", "actions_taken": ["restarted"]},
            {"status": "ESCALATED", "summary": "", "actions_taken": []},
            {"status": "ESCALATED", "actions_taken": []},
        ]
        for report in reports:
            with self.subTest(report=report), self.assertRaises(RuntimeError):
                validate_report(report, {"up": 0, "http_status": 500})

    def test_fixed_evidence_precedes_model_and_has_no_model_tools(self):
        evidence = {"up": 1, "http_status": 200, "unregistered_descriptor_errors": 0}
        community = {"query": "smartctl-exporter", "total_matches": 1, "has_more": False, "results": []}
        response = {"choices": [{"message": {"content": json.dumps({
            "status": "NO_ACTIVE_FAILURE", "summary": "Current checks pass", "actions_taken": [],
        })}}]}
        env = {"LITELLM_BASE_URL": "http://example.invalid", "LITELLM_API_KEY": "test", "PROMETHEUS_URL": "http://example.invalid"}
        output = io.StringIO()
        with patch.dict("os.environ", env), patch("worker.MCP") as mcp, patch("worker.scrape_status", return_value=evidence), patch("worker.json_request", return_value=response) as request, contextlib.redirect_stdout(output):
            mcp.return_value.initialize.return_value = "kubesearch_search_releases"
            mcp.return_value.request.return_value = {"structuredContent": community}
            run()
            self.assertNotIn("tools", request.call_args.args[1])
            schema = request.call_args.args[1]["response_format"]["json_schema"]["schema"]
            self.assertEqual(schema["properties"]["status"]["enum"], ["NO_ACTIVE_FAILURE"])
            self.assertEqual(schema["properties"]["actions_taken"]["maxItems"], 0)
            mcp.return_value.request.assert_called_once_with("tools/call", {
                "name": "kubesearch_search_releases", "arguments": {"query": "smartctl-exporter", "limit": 1},
            })
        self.assertEqual(json.loads(output.getvalue())["workflow_mode"], "fixed-scope-evidence")

    def test_evidence_failure_stops_before_model(self):
        env = {"LITELLM_BASE_URL": "http://example.invalid", "LITELLM_API_KEY": "test", "PROMETHEUS_URL": "http://example.invalid"}
        with patch.dict("os.environ", env), patch("worker.MCP"), patch("worker.scrape_status", side_effect=RuntimeError("No sample")), patch("worker.json_request") as request:
            with self.assertRaisesRegex(RuntimeError, "No sample"):
                run()
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
