import importlib.util
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch


path = Path(__file__).resolve().parents[1] / "kubernetes/apps/observability/alert-triage/app/triage.py"
spec = importlib.util.spec_from_file_location("alert_triage", path)
triage = importlib.util.module_from_spec(spec)
with patch.dict("os.environ", {
    "ALERTMANAGER_URL": "http://alertmanager",
    "GITHUB_REPOSITORY": "owner/repo",
    "GITHUB_TOKEN": "test-token",
}):
    spec.loader.exec_module(triage)


def alert(name, instance):
    return {"labels": {"alertname": name, "instance": instance, "severity": "critical"}}


class AlertTriageTests(unittest.TestCase):
    def test_group_fingerprint_does_not_depend_on_instance_order(self):
        first = alert("LanProbeFailed", "ups")
        second = alert("LanProbeFailed", "pdu")
        self.assertEqual(
            triage.build_issue("LanProbeFailed", [first, second], [])[0],
            triage.build_issue("LanProbeFailed", [second, first], [])[0],
        )

    def test_lists_all_open_issues_without_relying_on_labels(self):
        pages = [[{"title": "unrelated"}] * 100 for _ in range(10)]
        pages.append([
            {"title": "[alert] LanProbeFailed — 3 firing", "body": ""},
            {"title": "[alert] TargetDown", "body": "<!-- alert-triage-fingerprint:abcdef -->"},
            {"title": "[alert] Fake", "pull_request": {}},
            {"title": "[alert] LanProbeFailed-extra"},
        ])
        with patch.object(triage, "http", side_effect=pages) as http:
            names, fingerprints = triage.existing_issues()
        self.assertEqual(names, {"LanProbeFailed", "LanProbeFailed-extra", "TargetDown"})
        self.assertEqual(fingerprints, {"abcdef"})
        self.assertEqual(http.call_count, 11)
        self.assertNotIn("labels=", http.call_args.args[0])

    def test_existing_unlabeled_issue_prevents_creation_after_instances_change(self):
        alerts = [alert("LanProbeFailed", "new"), alert("LanProbeFailed", "ups")]
        existing = [{"title": "[alert] LanProbeFailed — 3 firing", "body": ""}]
        with patch.object(triage, "fetch_alerts", return_value=alerts), \
             patch.object(triage, "eligible", return_value=True), \
             patch.object(triage, "http", return_value=existing) as http:
            self.assertEqual(triage.main(), 0)
        self.assertEqual(http.call_count, 1)

    def test_legacy_marker_prevents_creation_when_title_was_changed(self):
        alerts = [alert("LanProbeFailed", "new"), alert("LanProbeFailed", "ups")]
        legacy = triage.fingerprint("LanProbeFailed", alerts[1]["labels"])
        existing = [{"title": "Renamed issue", "body": f"<!-- {triage.MARKER}:{legacy} -->"}]
        with patch.object(triage, "fetch_alerts", return_value=alerts), \
             patch.object(triage, "eligible", return_value=True), \
             patch.object(triage, "http", return_value=existing) as http:
            self.assertEqual(triage.main(), 0)
        self.assertEqual(http.call_count, 1)

    def test_renamed_legacy_issue_with_replaced_instances_is_still_tracked(self):
        alerts = [alert("LanProbeFailed", "new")]
        legacy = triage.fingerprint("LanProbeFailed", alert("LanProbeFailed", "old")["labels"])
        existing = [{
            "title": "Renamed issue",
            "body": f"## `LanProbeFailed`\n\n<!-- {triage.MARKER}:{legacy} -->",
        }]
        with patch.object(triage, "fetch_alerts", return_value=alerts), \
             patch.object(triage, "eligible", return_value=True), \
             patch.object(triage, "http", return_value=existing) as http:
            self.assertEqual(triage.main(), 0)
        self.assertEqual(http.call_count, 1)

    def test_new_alert_is_filed_and_list_failure_fails_closed(self):
        alerts = [alert("LanProbeFailed", "ups")]
        with patch.object(triage, "fetch_alerts", return_value=alerts), \
             patch.object(triage, "eligible", return_value=True), \
             patch.object(triage, "ASSIGNEE", ""), \
             patch.object(triage, "DRY_RUN", False), \
             patch.object(triage, "http", side_effect=[[], {"number": 123}]) as http:
            self.assertEqual(triage.main(), 0)
            self.assertEqual(http.call_count, 2)
            self.assertEqual(http.call_args.kwargs["method"], "POST")
        error = urllib.error.HTTPError("url", 403, "forbidden", {}, None)
        with patch.object(triage, "fetch_alerts", return_value=alerts), \
             patch.object(triage, "eligible", return_value=True), \
             patch.object(triage, "http", side_effect=error) as http:
            self.assertEqual(triage.main(), 1)
            self.assertEqual(http.call_count, 1)
        with patch.object(triage, "fetch_alerts", return_value=alerts), \
             patch.object(triage, "eligible", return_value=True), \
             patch.object(triage, "http", return_value=None) as http:
            self.assertEqual(triage.main(), 1)
            self.assertEqual(http.call_count, 1)


if __name__ == "__main__":
    unittest.main()
