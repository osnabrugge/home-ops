import contextlib
import fcntl
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import nas01_smart_report as report


def ata(failed=False, serial="test-serial"):
    return {
        "model_name": "test-model",
        "serial_number": serial,
        "power_on_time": {"hours": 100},
        "ata_smart_self_test_log": {
            "standard": {"table": [{"status": {"passed": not failed}, "lifetime_hours": 90}]},
        },
    }


class SmartReportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="nas01-smart-test-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.sys = self.work / "sys"
        self.dev = self.work / "dev"
        self.ids = self.dev / "disk/by-id"
        self.sys.mkdir()
        self.ids.mkdir(parents=True)
        self.out = self.work / "smart.prom"
        self.lock = self.work / "report.lock"
        for name, value in (
            ("SYS_BLOCK", self.sys), ("DEV", self.dev), ("BY_ID", self.ids),
            ("OUT", self.out), ("LOCK", self.lock),
        ):
            patcher = patch.object(report, name, value)
            self.addCleanup(patcher.stop)
            patcher.start()

    def disk(self, name, rotational=1, size=100, alias=None):
        disk = self.sys / name
        (disk / "queue").mkdir(parents=True)
        (disk / "queue/rotational").write_text(str(rotational))
        (disk / "size").write_text(str(size))
        (self.dev / name).touch()
        if alias is not None:
            (self.ids / alias).symlink_to(self.dev / name)

    def run_report(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as errors:
            code = report.main()
        return code, self.out.read_text(), errors.getvalue()

    def test_discovers_all_twenty_two_hdds_not_first_twelve(self):
        for index in range(22):
            self.disk("sd" + chr(97 + index), alias=f"wwn-{index:02}")
        self.disk("sdw", rotational=0, alias="ata-ssd")
        self.disk("sdx", size=0, alias="scsi-udisk")
        self.disk("nvme0n1", rotational=0, alias="scsi-nvme")
        devices = report.discover_devices()
        self.assertEqual(len(devices), 22)
        self.assertEqual(devices[-1], ("sdv", self.ids / "wwn-21"))
        with patch.object(report, "smart", side_effect=lambda identity, fd: ata(serial=identity.name)):
            code, output, errors = self.run_report()
        self.assertEqual(code, 0, errors)
        self.assertEqual(output.count("\nnas01_smart_selftest_probe_success{"), 22)
        self.assertEqual(output.count("\nnas01_smart_selftest_failed{"), 22)
        self.assertIn("nas01_smart_selftest_report_success 1\n", output)

    def test_prefers_whole_disk_wwn_and_rejects_partition_aliases(self):
        self.disk("sda", alias="ata-disk")
        (self.ids / "wwn-disk").symlink_to(self.dev / "sda")
        (self.ids / "wwn-disk-part1").symlink_to(self.dev / "sda")
        self.assertEqual(report.discover_devices(), [("sda", self.ids / "wwn-disk")])

    def test_missing_stable_identity_is_explicit_failure(self):
        self.disk("sda")
        code, output, errors = self.run_report()
        self.assertEqual(code, 1)
        self.assertIn("No stable whole-disk identity", errors)
        self.assertIn("nas01_smart_selftest_report_success 0\n", output)
        self.assertNotIn("nas01_smart_selftest_report_timestamp_seconds", output)

    def test_no_disks_is_not_success(self):
        code, output, errors = self.run_report()
        self.assertEqual(code, 1)
        self.assertIn("No identifiable", errors)
        self.assertIn("nas01_smart_selftest_report_success 0\n", output)

    def test_preserves_real_failure_when_smartctl_exit_status_is_152(self):
        process = Mock(returncode=152)
        process.communicate.return_value = (json.dumps(ata(True)).encode(), b"")
        with patch.object(report.subprocess, "Popen", return_value=process) as launch:
            result = report.smart(self.ids / "wwn-disk", 7)
        self.assertEqual(report.newest_entry(result), (True, 90))
        self.assertEqual(launch.call_args.kwargs["pass_fds"], (7,))
        self.assertEqual(launch.call_args.args[0][-3:], ["-d", "auto", str(self.ids / "wwn-disk")])
        self.assertNotIn("-t", launch.call_args.args[0])

    def test_read_error_bits_and_invalid_json_are_explicit(self):
        for code, output in ((2, b"{}"), (4, b"{}"), (0, b"not json"), (0, b"[]")):
            with self.subTest(code=code, output=output):
                process = Mock(returncode=code)
                process.communicate.return_value = (output, b"read failed")
                with patch.object(report.subprocess, "Popen", return_value=process):
                    with self.assertRaises(ValueError):
                        report.smart(self.ids / "wwn-disk", 7)

    def test_timeout_kills_and_reaps_with_another_bounded_wait(self):
        process = Mock()
        process.communicate.side_effect = [
            subprocess.TimeoutExpired("smartctl", report.PROBE_TIMEOUT), (b"", b""),
        ]
        with patch.object(report.subprocess, "Popen", return_value=process):
            with self.assertRaisesRegex(report.ProbeTimeout, "exceeded"):
                report.smart(self.ids / "wwn-disk", 7)
        process.kill.assert_called_once_with()
        self.assertEqual(
            [call.kwargs["timeout"] for call in process.communicate.call_args_list],
            [report.PROBE_TIMEOUT, report.REAP_TIMEOUT],
        )

    def test_original_read_budget_allows_native_sixty_second_command_timeout(self):
        process = Mock(returncode=0)

        def communicate(*, timeout):
            if timeout < 60:
                raise subprocess.TimeoutExpired("smartctl", timeout)
            return json.dumps(ata()).encode(), b""

        process.communicate.side_effect = communicate
        with patch.object(report.subprocess, "Popen", return_value=process):
            data = report.smart(self.ids / "wwn-disk", 7)
        self.assertEqual(report.PROBE_TIMEOUT, 180)
        self.assertEqual(report.newest_entry(data), (False, 90))
        process.kill.assert_not_called()

    def test_reaped_timeout_also_stops_remaining_probes(self):
        self.disk("sda", alias="wwn-a")
        self.disk("sdb", alias="wwn-b")
        with patch.object(report, "smart", side_effect=report.ProbeTimeout("read timeout")) as probe:
            code, output, errors = self.run_report()
        self.assertEqual(code, 1)
        probe.assert_called_once()
        self.assertIn("previous SMART probe exceeded its deadline", errors)
        self.assertIn("nas01_smart_selftest_report_success 0\n", output)

    def test_unreapable_child_stops_further_probes_and_retains_failed_snapshot(self):
        self.disk("sda", alias="wwn-a")
        self.disk("sdb", alias="wwn-b")
        old = 'nas01_smart_selftest_failed{device="sda",model="old",serial="old"} 1\n'
        old += "nas01_smart_selftest_report_timestamp_seconds 123\n"
        self.out.write_text(old)
        with patch.object(report, "smart", side_effect=report.BlockedProbe("blocked")) as probe:
            code, output, errors = self.run_report()
        self.assertEqual(code, 1)
        probe.assert_called_once()
        self.assertIn("Not probing", errors)
        self.assertIn(old, output)
        self.assertEqual(output.count("\nnas01_smart_selftest_probe_success{"), 2)
        self.assertIn("nas01_smart_selftest_report_success 0\n", output)

    def test_unreapable_timeout_never_performs_unbounded_wait(self):
        process = Mock(pid=123)
        process.communicate.side_effect = [
            subprocess.TimeoutExpired("smartctl", report.PROBE_TIMEOUT),
            subprocess.TimeoutExpired("smartctl", report.REAP_TIMEOUT),
        ]
        with patch.object(report.subprocess, "Popen", return_value=process):
            with self.assertRaisesRegex(report.BlockedProbe, "PID 123"):
                report.smart(self.ids / "wwn-disk", 7)
        process.wait.assert_not_called()

    def test_failure_does_not_advance_timestamp_or_remove_existing_hardware_alarm(self):
        self.disk("sda", alias="wwn-a")
        self.out.write_text(
            'nas01_smart_selftest_failed{device="sda",model="old",serial="old"} 1\n'
            "nas01_smart_selftest_report_timestamp_seconds 123\n"
            "nas01_smart_selftest_report_success 1\n"
        )
        with patch.object(report, "smart", side_effect=ValueError("read failed")):
            code, output, errors = self.run_report()
        self.assertEqual(code, 1)
        self.assertIn("read failed", errors)
        self.assertIn('serial="old"} 1\n', output)
        self.assertIn("report_timestamp_seconds 123\n", output)
        self.assertEqual(output.count("\nnas01_smart_selftest_report_success "), 1)
        self.assertIn("nas01_smart_selftest_report_success 0\n", output)

    def test_empty_selftest_log_is_available_zero_not_a_fabricated_pass(self):
        self.disk("sda", alias="wwn-a")
        data = ata()
        del data["ata_smart_self_test_log"]
        with patch.object(report, "smart", return_value=data):
            code, output, errors = self.run_report()
        self.assertEqual(code, 0, errors)
        self.assertIn('nas01_smart_selftest_available{device="sda",identity="wwn-a"} 0\n', output)
        self.assertNotIn("\nnas01_smart_selftest_failed{", output)

    def test_sas_result_and_power_on_age_are_preserved(self):
        self.disk("sda", alias="wwn-a")
        data = {
            "scsi_model_name": "SAS model", "serial_number": "SAS serial",
            "power_on_time": {"hours": 100},
            "scsi_self_test_0": {"result": {"value": 0}, "power_on_time": {"hours": 90}},
        }
        with patch.object(report, "smart", return_value=data):
            code, output, errors = self.run_report()
        self.assertEqual(code, 0, errors)
        self.assertIn('serial="SAS serial"} 0\n', output)
        self.assertIn('serial="SAS serial"} 10\n', output)

    def test_incomplete_ata_tests_do_not_hide_previous_completed_failure(self):
        for value in (17, 35, 249):
            with self.subTest(value=value):
                data = ata(True)
                data["ata_smart_self_test_log"]["standard"]["table"].insert(
                    0, {"status": {"value": value}, "lifetime_hours": 95},
                )
                with contextlib.redirect_stderr(io.StringIO()) as errors:
                    self.assertEqual(report.newest_entry(data), (True, 90))
                self.assertIn("Ignoring incomplete", errors.getvalue())

    def test_incomplete_only_test_log_is_not_a_pass_or_hardware_failure(self):
        data = {"ata_smart_self_test_log": {"standard": {"table": [
            {"status": {"value": 17}, "lifetime_hours": 95},
        ]}}}
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertIsNone(report.newest_entry(data))

    def test_sas_aborted_entry_uses_the_previous_completed_test(self):
        data = {
            "scsi_self_test_0": {"result": {"value": 1}, "power_on_time": {"hours": 95}},
            "scsi_self_test_1": {"result": {"value": 7}, "power_on_time": {"hours": 90}},
        }
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(report.newest_entry(data), (True, 90))

    def test_completed_ata_status_without_boolean_is_decoded_not_guessed(self):
        for value, failed in ((0, False), (73, True)):
            with self.subTest(value=value):
                data = {"ata_smart_self_test_log": {"standard": {"table": [
                    {"status": {"value": value}, "lifetime_hours": 90},
                ]}}}
                self.assertEqual(report.newest_entry(data), (failed, 90))
        with self.assertRaises(ValueError):
            report.newest_entry({"ata_smart_self_test_log": {"standard": {
                "table": [{"status": {}, "lifetime_hours": 90}],
            }}})

    def test_invalid_labels_and_lifetime_are_not_silent_success(self):
        self.disk("sda", alias="wwn-a")
        for change in (
            {"serial_number": None}, {"model_name": None},
            {"power_on_time": {"hours": 5}},
        ):
            with self.subTest(change=change):
                data = ata()
                data.update(change)
                with patch.object(report, "smart", return_value=data):
                    code, output, errors = self.run_report()
                self.assertEqual(code, 1)
                self.assertIn("SMART read failed", errors)
                self.assertIn("nas01_smart_selftest_report_success 0\n", output)

    def test_labels_escape_prometheus_quotes_backslashes_and_newlines(self):
        self.assertEqual(report.labels(model='a"b\\c\nd'), 'model="a\\"b\\\\c\\nd"')

    def test_inherited_child_lock_prevents_another_collection(self):
        self.lock.touch()
        with self.lock.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            child = subprocess.Popen(
                [sys.executable, "-c", "import sys; sys.stdin.buffer.read(1)"],
                stdin=subprocess.PIPE, pass_fds=(lock.fileno(),),
            )
        try:
            with self.lock.open("a") as another:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(another, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with contextlib.redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(report.main(), 1)
            self.assertIn("refusing more probes", errors.getvalue())
            child.communicate(input=b"x", timeout=3)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()
