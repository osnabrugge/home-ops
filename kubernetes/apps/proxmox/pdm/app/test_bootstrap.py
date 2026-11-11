import copy
import json
import unittest
from unittest.mock import patch

from bootstrap import API, configure, load_settings


class BootstrapTests(unittest.TestCase):
    def settings(self):
        return {
            "recovery_password": "a" * 48,
            "oidc_client_secret": "b" * 48,
            "oidc_admin": "owner@authentik",
            "remotes": [{
                "type": "pve", "id": "pve02", "nodes": ["pve02.in.homeops.ca:8006"],
                "authid": "reader@pve!audit", "token": "test-token",
                "web-url": "https://pve02.in.homeops.ca:8006",
            }],
        }

    def test_unapproved_remotes_and_token_creation_are_rejected(self):
        for field, value in [
            ("id", "other"), ("nodes", ["other:8006"]),
            ("create-token", "new-token"), ("authid", "root@pam"),
        ]:
            settings = self.settings()
            settings["remotes"][0][field] = value
            with self.subTest(field=field), patch("bootstrap.Path.read_text", return_value=json.dumps(settings)):
                with self.assertRaises(RuntimeError):
                    load_settings()

    def test_native_cookie_is_taken_from_header_not_ticket_info(self):
        with patch("bootstrap.http.client.HTTPConnection") as factory, patch("bootstrap.socket.socket"):
            response = factory.return_value.getresponse.return_value
            response.status = 200
            response.read.return_value = json.dumps({
                "data": {"ticket-info": "not-a-session-ticket"},
            }).encode()
            response.getheader.return_value = "PDMAuthCookie=signed-cookie; Secure; HttpOnly"
            api = API()
            api.request("POST", "access/ticket", {})
            self.assertEqual(api.headers["Cookie"], "PDMAuthCookie=signed-cookie")

    def test_existing_host_identity_must_match_its_reviewed_endpoint(self):
        settings = self.settings()
        remote = settings["remotes"][0]
        remote.update(id="pve01", nodes=["pve01.in.homeops.ca:8006"])
        with patch("bootstrap.Path.read_text", return_value=json.dumps(settings)):
            self.assertEqual(load_settings()["remotes"][0]["id"], "pve01")
        remote["nodes"] = ["pve02.in.homeops.ca:8006"]
        with patch("bootstrap.Path.read_text", return_value=json.dumps(settings)):
            with self.assertRaisesRegex(RuntimeError, "Unapproved remote"):
                load_settings()

    def test_native_errors_do_not_disclose_response_credentials(self):
        with patch("bootstrap.http.client.HTTPConnection") as factory, patch("bootstrap.socket.socket"):
            response = factory.return_value.getresponse.return_value
            response.status = 401
            response.read.return_value = b"secret-token-from-upstream"
            with self.assertRaisesRegex(RuntimeError, r"failed with HTTP 401") as error:
                API().request("POST", "access/ticket", {"password": "secret-password"})
            self.assertNotIn("secret", str(error.exception))

    def test_existing_oidc_drift_is_not_overwritten(self):
        with patch("bootstrap.API") as factory:
            api = factory.return_value
            api.request.return_value = [{"realm": "authentik", "issuer-url": "https://other.invalid"}]
            with self.assertRaisesRegex(RuntimeError, "refusing to overwrite"):
                configure(copy.deepcopy(self.settings()))
            api.request.assert_called_once_with("GET", "config/access/openid")


if __name__ == "__main__":
    unittest.main()
