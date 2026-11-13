import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class PduMappingSafetyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        scripts = root / "scripts"
        scripts.mkdir()
        self.script = scripts / "infra-pdu.sh"
        shutil.copy2(Path(__file__).with_name("infra-pdu.sh"), self.script)
        binaries = root / "bin"
        binaries.mkdir()
        helpers = {
            "snmpget": 'printf "INTEGER: 1\\n"\n',
            "snmpset": 'printf "%s\\n" "$*" >> "$TEST_WRITES"\n',
            "gum": "exit 0\n",
        }
        for name, body in helpers.items():
            path = binaries / name
            path.write_text("#!/bin/sh\n" + body)
            path.chmod(0o700)
        self.writes = root / "writes"
        self.env = os.environ | {
            "PATH": str(binaries) + os.pathsep + os.environ["PATH"],
            "PDU_COMMUNITY": "test-community",
            "TEST_WRITES": str(self.writes),
        }

    def run_pdu(self, command, node):
        return subprocess.run(
            ["bash", str(self.script), command, node],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=5,
        )

    def test_unverified_nodes_cannot_receive_any_power_command(self):
        for node in ("k8s04", "k8s06"):
            for command in ("on", "off", "reboot"):
                with self.subTest(node=node, command=command):
                    result = self.run_pdu(command, node)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("unverified", result.stderr)
                    self.assertNotIn("command sent", result.stdout)
        self.assertFalse(self.writes.exists())

    def test_unverified_nodes_remain_readable_without_power_writes(self):
        for node in ("k8s04", "k8s06"):
            with self.subTest(node=node):
                result = self.run_pdu("status", node)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("ON", result.stdout)
        self.assertFalse(self.writes.exists())

    def test_unaffected_node_keeps_its_original_single_write(self):
        result = self.run_pdu("on", "k8s05")
        self.assertEqual(result.returncode, 0, result.stderr)
        writes = self.writes.read_text().splitlines()
        self.assertEqual(len(writes), 1)
        self.assertIn("192.168.99.16", writes[0])
        self.assertIn(".1.3.6.1.4.1.3808.1.1.3.3.3.1.1.4.2 integer 1", writes[0])


if __name__ == "__main__":
    unittest.main()
