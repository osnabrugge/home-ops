import copy
import io
import unittest
import urllib.error
from unittest.mock import MagicMock, call, patch

from key_policy import POLICY, main, policy_matches, request


class KeyPolicyTests(unittest.TestCase):
    def test_exact_policy_and_null_optional_fields(self):
        info = copy.deepcopy(POLICY)
        self.assertTrue(policy_matches(info))
        info["object_permission"]["vector_stores"] = None
        info["object_permission"]["agents"] = []
        info["object_permission"]["object_permission_id"] = "native-row-id"
        self.assertTrue(policy_matches(info))

    def test_extra_grants_fail(self):
        info = copy.deepcopy(POLICY)
        info["object_permission"]["agents"] = ["unapproved"]
        self.assertFalse(policy_matches(info))
        info = copy.deepcopy(POLICY)
        info["object_permission"]["mcp_tool_permissions"]["kubesearch"].append("repo_cleanup")
        self.assertFalse(policy_matches(info))

    def test_model_route_and_rate_drift_fail(self):
        for field, value in [
            ("models", ["all-proxy-models"]),
            ("allowed_routes", []),
            ("rpm_limit", 100),
            ("object_permission", None),
        ]:
            with self.subTest(field=field):
                info = copy.deepcopy(POLICY)
                info[field] = value
                self.assertFalse(policy_matches(info))

    def test_revoked_key_is_not_reenabled(self):
        info = {**copy.deepcopy(POLICY), "blocked": True}
        env = {"LITELLM_BASE_URL": "http://example.invalid", "LITELLM_MASTER_KEY": "test", "TRIAGE_API_KEY": "test"}
        with patch.dict("os.environ", env), patch("key_policy.request", return_value={"info": info}) as request:
            with self.assertRaisesRegex(RuntimeError, "blocked"):
                main()
            self.assertEqual(request.call_count, 1)

    def test_transient_lookup_failure_is_retried(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"info": {}}'
        for error in (
            urllib.error.URLError(ConnectionRefusedError()),
            urllib.error.HTTPError("http://example.invalid", 503, "Unavailable", {}, io.BytesIO()),
            TimeoutError(),
        ):
            with self.subTest(error=type(error).__name__):
                with patch("key_policy.urllib.request.urlopen", side_effect=[error, response]) as open_url:
                    with patch("key_policy.time.sleep") as pause:
                        self.assertEqual(request("http://example.invalid", "test", "/key/info"), {"info": {}})
                self.assertEqual(open_url.call_count, 2)
                pause.assert_called_once_with(2)

    def test_lookup_retries_are_bounded(self):
        with patch("key_policy.urllib.request.urlopen", side_effect=urllib.error.URLError("unavailable")) as open_url:
            with patch("key_policy.time.sleep") as pause:
                with self.assertRaises(urllib.error.URLError):
                    request("http://example.invalid", "test", "/key/info")
        self.assertEqual(open_url.call_count, 4)
        self.assertEqual(pause.call_args_list, [call(2), call(4), call(8)])

    def test_auth_and_missing_key_errors_are_not_retried(self):
        for status in (400, 401, 403, 404):
            with self.subTest(status=status):
                error = urllib.error.HTTPError("http://example.invalid", status, "Rejected", {}, io.BytesIO())
                self.addCleanup(error.close)
                with patch("key_policy.urllib.request.urlopen", side_effect=error) as open_url:
                    with patch("key_policy.time.sleep") as pause:
                        with self.assertRaises(urllib.error.HTTPError):
                            request("http://example.invalid", "test", "/key/info")
                open_url.assert_called_once()
                pause.assert_not_called()

    def test_key_mutations_are_not_retried(self):
        for path in ("/key/generate", "/key/update"):
            with self.subTest(path=path):
                with patch("key_policy.urllib.request.urlopen", side_effect=urllib.error.URLError("unavailable")) as open_url:
                    with patch("key_policy.time.sleep") as pause:
                        with self.assertRaises(urllib.error.URLError):
                            request("http://example.invalid", "test", path, {"key": "test"})
                open_url.assert_called_once()
                pause.assert_not_called()


if __name__ == "__main__":
    unittest.main()
