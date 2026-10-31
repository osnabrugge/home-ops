import unittest

from worker import validate_report, validate_tool


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
        for up, status, result in [(1, 200, "NO_ACTIVE_FAILURE"), (0, 500, "ESCALATED"), (1, 500, "ESCALATED"), (0, 200, "ESCALATED")]:
            validate_report({"status": result, "summary": "Observed evidence", "actions_taken": []}, {"up": up, "http_status": status})

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


if __name__ == "__main__":
    unittest.main()
