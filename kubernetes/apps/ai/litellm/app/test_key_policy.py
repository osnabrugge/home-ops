import copy
import unittest

from key_policy import POLICY, policy_matches


class KeyPolicyTests(unittest.TestCase):
    def test_exact_policy_and_null_optional_fields(self):
        info = copy.deepcopy(POLICY)
        self.assertTrue(policy_matches(info))
        info["object_permission"]["vector_stores"] = None
        info["object_permission"]["agents"] = []
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


if __name__ == "__main__":
    unittest.main()
