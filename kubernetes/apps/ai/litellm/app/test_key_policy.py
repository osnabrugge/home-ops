import copy
import unittest
from unittest.mock import patch

from key_policy import POLICY, main, policy_matches


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


if __name__ == "__main__":
    unittest.main()
