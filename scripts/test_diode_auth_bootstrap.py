import base64
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch


MODULE = Path(__file__).resolve().parents[1] / "kubernetes/apps/observability/netbox-diode/app/auth-bootstrap.py"
SPEC = importlib.util.spec_from_file_location("diode_auth_bootstrap", MODULE)
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)

ADMIN = "http://hydra.invalid:4445"
TOKEN_URL = "http://hydra.invalid:4444/oauth2/token"
CLIENT_ID = "fixture-client"
SECRET = "fixture-secret-not-a-real-credential"
SCOPE = "diode:ingest"


def client(**overrides):
    return {
        "client_id": CLIENT_ID,
        "grant_types": ["client_credentials"],
        "response_types": ["token"],
        "scope": SCOPE,
        "token_endpoint_auth_method": "client_secret_post",
        **overrides,
    }


def jwt(claims):
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"fixture.{payload}.signature"


def token(**overrides):
    return {
        "access_token": jwt({"scope": SCOPE}),
        "token_type": "bearer",
        "expires_in": 3600,
        "scope": SCOPE,
        **overrides,
    }


class DiodeAuthBootstrapTests(unittest.TestCase):
    def ensure(self):
        return bootstrap.ensure_client(ADMIN, TOKEN_URL, CLIENT_ID, SECRET, SCOPE)

    def test_creates_missing_client_and_verifies_credentials(self):
        missing = bootstrap.RequestFailure("GET", ADMIN, 404)
        with patch.object(bootstrap, "request_json", side_effect=[missing, client(), token()]) as request:
            self.assertEqual(self.ensure(), "created")
        payload = request.call_args_list[1].args[2]
        self.assertEqual(payload["client_secret"], SECRET)
        self.assertEqual(payload["scope"], SCOPE)
        self.assertTrue(request.call_args_list[-1].kwargs["form"])

    def test_existing_client_is_not_updated(self):
        with patch.object(bootstrap, "request_json", side_effect=[client(), token()]) as request:
            self.assertEqual(self.ensure(), "verified")
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args_list[-1].args[0], TOKEN_URL)

    def test_get_failure_is_not_mistaken_for_missing_client(self):
        for status in (401, 403, 500):
            with self.subTest(status=status), patch.object(
                bootstrap, "request_json", side_effect=bootstrap.RequestFailure("GET", ADMIN, status)
            ) as request:
                with self.assertRaises(bootstrap.RequestFailure):
                    self.ensure()
                self.assertEqual(request.call_count, 1)

    def test_concurrent_create_is_verified_without_overwriting(self):
        responses = [
            bootstrap.RequestFailure("GET", ADMIN, 404),
            bootstrap.RequestFailure("POST", ADMIN, 409),
            client(),
            token(),
        ]
        with patch.object(bootstrap, "request_json", side_effect=responses) as request:
            self.assertEqual(self.ensure(), "verified")
        self.assertEqual([call.args[1] if len(call.args) > 1 else "GET" for call in request.call_args_list],
                         ["GET", "POST", "GET", "POST"])

    def test_scope_or_grant_drift_fails_without_repairing_it(self):
        for fields in (
            {"scope": "diode:ingest netbox:write"},
            {"grant_types": ["client_credentials", "password"]},
            {"token_endpoint_auth_method": "client_secret_basic"},
            {"client_id": "other-client"},
        ):
            with self.subTest(fields=fields), patch.object(
                bootstrap, "request_json", return_value=client(**fields)
            ) as request:
                with self.assertRaises(bootstrap.BootstrapError):
                    self.ensure()
                self.assertEqual(request.call_count, 1)

    def test_invalid_secret_is_not_rotated_or_printed(self):
        failure = bootstrap.RequestFailure("POST", TOKEN_URL, 401)
        with patch.object(bootstrap, "request_json", side_effect=[client(), failure]) as request:
            with self.assertRaises(bootstrap.BootstrapError) as error:
                self.ensure()
        self.assertNotIn(SECRET, str(error.exception))
        self.assertEqual(request.call_count, 2)

    def test_invalid_token_response_is_not_success(self):
        for fields in (
            {"access_token": ""},
            {"expires_in": 0},
            {"expires_in": True},
            {"token_type": "basic"},
            {"scope": "netbox:write"},
        ):
            with self.subTest(fields=fields), patch.object(
                bootstrap, "request_json", side_effect=[client(), token(**fields)]
            ):
                with self.assertRaises(bootstrap.BootstrapError):
                    self.ensure()

    def test_short_secret_fails_before_any_request(self):
        with patch.object(bootstrap, "request_json") as request:
            with self.assertRaises(bootstrap.BootstrapError):
                bootstrap.ensure_client(ADMIN, TOKEN_URL, CLIENT_ID, "short", SCOPE)
            request.assert_not_called()

    def test_jwt_scope_format_must_match_diode_not_just_token_response(self):
        for value in (jwt({"scp": [SCOPE]}), jwt({"scope": "netbox:write"}), "invalid-jwt"):
            with self.subTest(value=value), patch.object(
                bootstrap, "request_json", side_effect=[client(), token(access_token=value)]
            ):
                with self.assertRaises(bootstrap.BootstrapError):
                    self.ensure()


if __name__ == "__main__":
    unittest.main()
