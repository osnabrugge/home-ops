import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from check_grafana_dashboards import changed_dashboard_urls, dashboard_urls, fetch_dashboard, main


URL = "https://grafana.com/api/dashboards/15757/revisions/46/download"
OLD_URL = "https://grafana.com/api/dashboards/15757/revisions/43/download"
ADDED_URL = "https://grafana.com/api/dashboards/15758/revisions/47/download"
UNCHANGED_URL = "https://grafana.com/api/dashboards/15761/revisions/21/download"


def manifest(url):
    return {"kind": "GrafanaDashboard", "spec": {"url": url}}


def documents(*values):
    return "\n".join(json.dumps(value) for value in values) + "\n"


class GrafanaDashboardTests(unittest.TestCase):
    def test_fetches_and_parses_a_dashboard_with_bounded_timeout(self):
        content = json.dumps({"title": "Kubernetes / Compute Resources / Cluster",
                              "panels": [{"type": "timeseries"}]}).encode()
        with patch("check_grafana_dashboards.urlopen", return_value=io.BytesIO(content)) as fetch:
            self.assertEqual(
                fetch_dashboard(URL), ("Kubernetes / Compute Resources / Cluster", 1)
            )
        self.assertEqual(fetch.call_args.args[0].full_url, URL)
        self.assertGreater(fetch.call_args.kwargs["timeout"], 0)
        self.assertLessEqual(fetch.call_args.kwargs["timeout"], 60)

    def test_rejects_malformed_or_non_dashboard_json(self):
        for content in (
            b"<html>upstream error</html>",
            b'{"message": "dashboard not found"}',
            b"[]",
            b'{"title": "", "panels": []}',
            b'{"title": "Error", "panels": {}}',
            b'{"title": "Error", "panels": [null]}',
            b'{"title": "Invalid JSON", "panels": [], "value": NaN}',
        ):
            with self.subTest(content=content):
                with patch("check_grafana_dashboards.urlopen", return_value=io.BytesIO(content)):
                    with self.assertRaises(ValueError):
                        fetch_dashboard(URL)

    def test_http_and_connection_failures_are_not_accepted(self):
        for error in (
            HTTPError(URL, 404, "Not Found", {}, None),
            URLError("connection refused"),
            TimeoutError("timed out"),
        ):
            with self.subTest(error=error):
                if isinstance(error, HTTPError):
                    self.addCleanup(error.close)
                with patch("check_grafana_dashboards.urlopen", side_effect=error):
                    with self.assertRaises(type(error)):
                        fetch_dashboard(URL)

    def test_selects_only_added_or_changed_urls_from_all_documents(self):
        changed = "kubernetes/apps/observability/test/app/grafanadashboard.yaml"
        added = "kubernetes/apps/observability/new/app/dashboard.yml"
        unrelated = "kubernetes/apps/observability/test/app/configmap.yaml"
        before = {
            changed: documents(manifest(OLD_URL), manifest(UNCHANGED_URL)),
            unrelated: documents({"kind": "ConfigMap",
                                  "spec": {"url": "https://example.com/old.json"}}),
        }
        after = {
            changed: documents(None, manifest(UNCHANGED_URL), manifest(URL), manifest(URL),
                               {"kind": "GrafanaDashboard", "spec": {"json": "{}"}}),
            added: documents(manifest(ADDED_URL)),
            unrelated: documents({"kind": "ConfigMap",
                                  "spec": {"url": "https://example.com/not-a-dashboard.json"}}),
        }

        def command_output(command, **kwargs):
            if command[:2] == ["git", "diff"]:
                return f"M\0{changed}\0A\0{added}\0M\0{unrelated}\0"
            if command[:2] == ["git", "show"]:
                return before[command[2].removeprefix("base:")]
            if command[0] == "yq":
                return kwargs["input"]
            self.fail(f"Unexpected command: {command}")

        with patch("check_grafana_dashboards.subprocess.check_output", side_effect=command_output):
            with patch.object(Path, "read_text", autospec=True,
                              side_effect=lambda path: after[str(path)]):
                self.assertEqual(changed_dashboard_urls("base"), {URL, ADDED_URL})

    def test_invalid_yaml_and_url_fields_do_not_silently_skip(self):
        for value in (
            {"kind": "GrafanaDashboard", "spec": None},
            manifest(None),
            manifest(""),
            manifest(42),
            manifest("file:///etc/passwd"),
        ):
            with self.subTest(value=value):
                with patch("check_grafana_dashboards.subprocess.check_output",
                           return_value=documents(value)):
                    with self.assertRaisesRegex(ValueError, "GrafanaDashboard spec"):
                        dashboard_urls("manifest", "test.yaml")
        with patch("check_grafana_dashboards.subprocess.check_output",
                   side_effect=subprocess.CalledProcessError(1, ["yq"])):
            with self.assertRaises(subprocess.CalledProcessError):
                dashboard_urls("invalid: [", "test.yaml")

    def test_cli_requires_an_explicit_selection(self):
        with patch("sys.argv", ["check_grafana_dashboards.py"]):
            with patch("sys.stderr", new_callable=io.StringIO):
                with self.assertRaises(SystemExit) as error:
                    main()
        self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
