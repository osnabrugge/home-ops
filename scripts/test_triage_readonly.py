import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import triage_readonly as triage


class ReadonlyTriageTests(unittest.TestCase):
    def setUp(self):
        self.servers = set(triage.READ_TOOLS)

    def test_only_names_leave_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mcp.json"
            path.write_text(json.dumps({"mcpServers": {"radar": {"headers": {"token": "canary"}}}}))
            self.assertEqual(triage.configured_servers(path), {"radar"})

    def test_invalid_configuration_fails_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mcp.json"
            for configuration in ([], {}, {"mcpServers": []}):
                path.write_text(json.dumps(configuration))
                with self.assertRaises(ValueError):
                    triage.configured_servers(path)
            path.write_text("{")
            with self.assertRaises(json.JSONDecodeError):
                triage.configured_servers(path)

    def test_missing_server_is_not_a_fallback(self):
        with self.assertRaisesRegex(ValueError, "memory-service"):
            triage.make_command("TargetDown", {"radar", "codebase-memory-mcp"})

    def test_other_servers_are_disabled_without_argument_injection(self):
        command = triage.make_command("TargetDown", self.servers | {"kubectl", "--allow-all"})
        self.assertIn("--disable-mcp-server=kubectl", command)
        self.assertIn("--disable-mcp-server=--allow-all", command)
        self.assertNotIn("--allow-all", command)

    def test_availability_is_exactly_read_only(self):
        command = triage.make_command("TargetDown", self.servers)
        available = command[command.index("--available-tools") + 1:command.index("-p")]
        expected = [
            f"{server}-{tool}"
            for server, tools in triage.READ_TOOLS.items()
            for tool in tools
        ]
        self.assertEqual(available, expected)
        self.assertFalse(any(name in available for name in ("bash", "apply_patch", "task")))
        self.assertNotIn("radar-manage_rollout", available)
        grants = [command[index + 1] for index, value in enumerate(command) if value == "--allow-tool"]
        self.assertEqual(grants, [
            f"{server}({tool})"
            for server, tools in triage.READ_TOOLS.items()
            for tool in tools
        ])
        denials = [command[index + 1] for index, value in enumerate(command) if value == "--deny-tool"]
        self.assertEqual(denials, ["shell", "write"])

    def test_model_permissions_and_execution_are_bounded(self):
        command = triage.make_command("TargetDown", self.servers)
        self.assertEqual(command[:3], ["timeout", "--signal=TERM", "20m"])
        for forbidden in ("--model", "--allow-all", "--allow-all-tools", "--allow-all-paths", "--share-gist"):
            self.assertNotIn(forbidden, command)
        self.assertIn("--disable-builtin-mcps", command)
        self.assertIn("--sync-session=off", command)

    def test_target_is_prompt_data_not_cli_arguments(self):
        target = "TargetDown; --allow-all $(false)"
        command = triage.make_command(target, self.servers)
        self.assertEqual(command[-2], "-p")
        self.assertIn(target, command[-1])
        self.assertNotIn("--allow-all", command)

    def test_timeout_is_not_success(self):
        error = io.StringIO()
        with patch.object(triage.shutil, "which", return_value="/usr/bin/tool"), \
             patch.object(triage, "configured_servers", return_value=self.servers), \
             patch.object(triage.subprocess, "run") as run, \
             contextlib.redirect_stderr(error):
            run.return_value.returncode = 124
            self.assertEqual(triage.main(["TargetDown"]), 124)
        self.assertIn("unresolved", error.getvalue())


if __name__ == "__main__":
    unittest.main()
