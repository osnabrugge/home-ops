import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import struct
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location("pi_lab", Path(__file__).with_name("lab.py"))
lab = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lab)


class LabSafetyTests(unittest.TestCase):
    def setUp(self):
        self.state = Path(__file__).parent / ".state" / f"tests-{os.getpid()}"
        self.state.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.state)
        self.patch = mock.patch.object(lab, "STATE", self.state)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.data = {
            name: {"ip": ip, "mac": f"02:00:00:00:00:{index:02x}"}
            for index, (name, ip) in enumerate(lab.ADDRESSES.items(), 1)
        }

    def write_inventory(self):
        (self.state / "inventory.json").write_text(json.dumps(self.data))

    def report(self):
        return {"time": time.time(), "disks": {"blockdevices": [{
            "name": "sda", "type": "disk", "path": "/dev/sda", "serial": "VERIFIED-SSD",
            "tran": "usb", "size": 240057409536, "mountpoints": [None],
            "signatures": {"status": 0, "stdout": '{"signatures":[]}'},
        }]}}

    def test_scope_accepts_only_four_reserved_pis(self):
        self.write_inventory()
        self.assertEqual(len(lab.inventory()), 4)
        self.data["pi01"]["ip"] = "192.168.42.51"
        self.write_inventory()
        with self.assertRaisesRegex(ValueError, "outside"):
            lab.inventory()

    def test_extra_node_is_rejected(self):
        self.data["k8s01"] = {"ip": "192.168.42.51", "mac": "02:00:00:00:00:05"}
        self.write_inventory()
        with self.assertRaisesRegex(ValueError, "exactly"):
            lab.inventory()

    def test_duplicate_mac_is_rejected(self):
        self.data["pi02"]["mac"] = self.data["pi01"]["mac"]
        self.write_inventory()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            lab.inventory()

    def test_scoped_prefixes(self):
        self.assertEqual(lab.prefixes({
            "mac": "02:00:00:00:00:01", "serial": "0000000012345678",
        }), ["02-00-00-00-00-01", "12345678"])
        self.assertEqual(lab.prefixes(self.data["pi01"]), ["02-00-00-00-00-01"])

    def test_firmware_archive_traversal_is_rejected(self):
        self.assertIsNone(lab.firmware_member("other/file"))
        self.assertEqual(str(lab.firmware_member(
            "artifacts/arm64/firmware/boot/start4.elf"
        )), "start4.elf")
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            lab.firmware_member("artifacts/arm64/firmware/boot/../../secrets")

    def test_only_exact_verified_blank_usb_disk_is_eligible(self):
        report = self.report()
        self.assertEqual(lab.blank_usb_disk(report, "VERIFIED-SSD")["name"], "sda")
        for serial in ("", "GUESSED-SSD"):
            with self.assertRaises(ValueError):
                lab.blank_usb_disk(report, serial)

    def test_mounted_partitioned_sata_and_wrong_capacity_are_rejected(self):
        for change in (
            {"children": [{"name": "sda1"}]}, {"mountpoints": ["/"]},
            {"fstype": "ext4"}, {"pttype": "gpt"}, {"tran": "sata"}, {"size": 1_000_000_000_000},
            {"signatures": {"status": 1, "stdout": ""}},
            {"signatures": {"status": 0, "stdout": '{"signatures":[{"type":"gpt"}]}'}},
        ):
            with self.subTest(change=change):
                report = self.report()
                report["disks"]["blockdevices"][0].update(change)
                with self.assertRaises(ValueError):
                    lab.blank_usb_disk(report, "VERIFIED-SSD")

    def test_old_disk_evidence_is_rejected(self):
        report = self.report()
        report["time"] -= 3601
        with self.assertRaisesRegex(ValueError, "Re-inspect"):
            lab.blank_usb_disk(report, "VERIFIED-SSD")

    def test_duplicate_disk_serial_is_rejected(self):
        report = self.report()
        report["disks"]["blockdevices"].append(copy.deepcopy(report["disks"]["blockdevices"][0]))
        with self.assertRaisesRegex(ValueError, "one inspected"):
            lab.blank_usb_disk(report, "VERIFIED-SSD")

    def test_tampered_asset_is_rejected(self):
        directory = self.state / "boot"
        directory.mkdir()
        (directory / "config.txt").write_text("original")
        lab.save_json(self.state / "assets.json", {
            "talos": lab.VERSION, "schematic": lab.SCHEMATIC, "overlay": lab.OVERLAY,
            "files": {"config.txt": lab.digest(directory / "config.txt")},
        })
        lab.verify_local_assets()
        (directory / "config.txt").write_text("changed")
        with self.assertRaisesRegex(ValueError, "checksum"):
            lab.verify_local_assets()

    def test_native_kernel_rejects_plain_efi_and_truncated_zboot(self):
        source, target = self.state / "efi", self.state / "native"
        source.write_bytes(b"MZ" + bytes(126))
        with self.assertRaisesRegex(ValueError, "native"):
            lab.native_kernel(source, target)
        header = bytearray(64)
        header[:8] = b"MZ\0\0zimg"
        header[24:28] = b"zstd"
        struct.pack_into("<II", header, 8, 1024, 4096)
        source.write_bytes(header)
        with self.assertRaisesRegex(ValueError, "truncated"):
            lab.native_kernel(source, target)

    def test_native_kernel_accepts_real_arm64_header(self):
        source, target = self.state / "raw", self.state / "native"
        header = bytearray(128)
        header[56:60] = b"ARM\x64"
        source.write_bytes(header)
        lab.native_kernel(source, target)
        self.assertEqual(source.read_bytes(), target.read_bytes())

    def test_existing_board_boot_directory_prevents_all_uploads(self):
        self.write_inventory()
        with (
            mock.patch.object(lab, "verify_local_assets", return_value={"files": {}}),
            mock.patch.object(lab, "run", side_effect=[
                subprocess.CompletedProcess([], 0, stdout="1000"),
                subprocess.CompletedProcess([], 0, stdout="1000"),
                subprocess.CalledProcessError(1, ["test"]),
            ]),
            mock.patch.object(subprocess, "Popen") as upload,
        ):
            with self.assertRaises(subprocess.CalledProcessError):
                lab.stage()
            upload.assert_not_called()

    def test_scoped_inspection_keeps_strict_key_checking(self):
        self.write_inventory()
        known_hosts = self.state / "known_hosts"
        known_hosts.write_text("independently verified test fixture")
        report = {
            "hostname": "pi04", "model": "Raspberry Pi 4 Model B Rev 1.5",
            "serial": "1000000012345678", "links": [{"address": self.data["pi04"]["mac"]}],
        }
        with mock.patch.object(lab, "run", return_value=subprocess.CompletedProcess(
            [], 0, stdout=json.dumps(report),
        )) as ssh:
            lab.inspect_node("pi04", "known-user", known_hosts)
            arguments = ssh.call_args.args[0]
            self.assertIn(f"UserKnownHostsFile={known_hosts.resolve()}", arguments)
            self.assertIn("StrictHostKeyChecking=yes", arguments)
            self.assertIn("UpdateHostKeys=no", arguments)
            self.assertIn("ForwardAgent=no", arguments)
        with self.assertRaisesRegex(ValueError, "missing or empty"):
            lab.inspect_node("pi04", "known-user", self.state / "nonexistent")

    @unittest.skipUnless(shutil.which("talosctl"), "talosctl is required for config integration")
    def test_actual_talos_templates_and_exact_serial_patch_validate(self):
        lab.configs()
        self.write_inventory()
        self.data["pi01"]["serial"] = "0000000012345678"
        self.data["pi04"]["serial"] = "0000000087654321"
        self.write_inventory()
        for node in ("pi01", "pi04"):
            report = self.report()
            report.update(hostname=node, serial=self.data[node]["serial"])
            lab.save_json(self.state / "nodes" / f"{node}.json", report)
            lab.configure_node(node, "VERIFIED-SSD")
            text = (self.state / "talos" / f"{node}.yaml").read_text()
            self.assertIn('disk.serial == "VERIFIED-SSD"', text)
            self.assertNotIn("/dev/LAB_DISK_NOT_VERIFIED", text)
            self.assertNotIn("kind: DiscoveryServiceConfig", text)
            self.assertIn("10.142.0.0/16", text)
            self.assertIn("10.143.0.0/16", text)


if __name__ == "__main__":
    unittest.main()
