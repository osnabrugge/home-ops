import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "smfc_watchdog",
    Path(__file__).resolve().parents[1] / "infrastructure/nas01/smfc/watchdog.py",
)
watchdog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watchdog)


class FanWatchdogTests(unittest.TestCase):
    def snapshot(self):
        return {
            "generated_at": 100,
            "start_time": 50,
            "fan_mode": {"id": 1, "control_held": True, "age_s": 1},
            "fan_controllers": [
                {
                    "type": kind, "enabled": True, "device_count": count,
                    "devices": [{"temp_c": temperature, "read_errors": 0} for _ in range(count)],
                    "ipmi_zones": [0, 1], "polling": polling,
                    "last_level_pct": level, "temp_max_c": maximum,
                }
                for kind, count, temperature, level, polling, maximum in (
                    ("cpu", 2, 30, 50, 2, 80),
                    ("hd", 2, 45, 70, 15, 60),
                    ("nvme", 1, 40, 50, 5, 70),
                    ("const", 0, 0, 50, 10, 0),
                )
            ],
            "zones": {"0": {"applied_level_pct": 70}, "1": {"applied_level_pct": 70}},
        }

    def test_complete_live_control_is_accepted(self):
        watchdog.validate_snapshot(self.snapshot(), {"hd": 2, "nvme": 1}, 101)

    def test_live_exporter_does_not_hide_a_stalled_controller(self):
        state = self.snapshot()
        state["fan_mode"]["age_s"] = 61
        with self.assertRaisesRegex(ValueError, "heartbeat"):
            watchdog.validate_snapshot(state, {"hd": 2, "nvme": 1}, 101)

    def test_missing_disk_is_not_healthy(self):
        state = self.snapshot()
        state["fan_controllers"][1]["device_count"] = 1
        with self.assertRaisesRegex(ValueError, "inventory"):
            watchdog.validate_snapshot(state, {"hd": 2, "nvme": 1}, 101)

    def test_stale_snapshot_or_uncontrolled_zone_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "timestamp"):
            watchdog.validate_snapshot(self.snapshot(), {"hd": 2, "nvme": 1}, 116)
        state = self.snapshot()
        state["zones"]["1"]["applied_level_pct"] = 20
        with self.assertRaisesRegex(ValueError, "zone 1"):
            watchdog.validate_snapshot(state, {"hd": 2, "nvme": 1}, 101)

    @patch.object(watchdog.subprocess, "run")
    def test_fail_safe_sets_full_mode_and_both_zones(self, run):
        watchdog.fail_high()
        self.assertEqual(
            [call.args[0][-2:] for call in run.call_args_list],
            [["0x01", "0x01"], ["0x00", "0x64"], ["0x01", "0x64"]],
        )
        self.assertTrue(all(call.kwargs["check"] for call in run.call_args_list))

    @patch.object(watchdog.subprocess, "run")
    def test_one_failed_zone_does_not_skip_the_other(self, run):
        run.side_effect = [
            None,
            watchdog.subprocess.CalledProcessError(1, ["ipmitool"]),
            None,
        ]
        with self.assertRaises(RuntimeError):
            watchdog.fail_high()
        self.assertEqual(run.call_count, 3)

    @patch.object(watchdog, "restore_levels")
    @patch.object(watchdog.time, "monotonic", side_effect=[0, 20, 30])
    def test_fail_safe_is_released_only_after_two_complete_sensor_cycles(self, monotonic, restore):
        recovery = watchdog.Recovery()
        recovery.active = True
        state = self.snapshot()
        for _ in range(2):
            recovery.observe(state, {"hd": 2, "nvme": 1}, 101)
        restore.assert_not_called()
        recovery.observe(state, {"hd": 2, "nvme": 1}, 101)
        restore.assert_called_once_with({"hd": 2, "nvme": 1}, 50)
        self.assertFalse(recovery.active)

    @patch.object(watchdog, "restore_levels")
    @patch.object(watchdog.time, "monotonic", side_effect=[0, 30, 40])
    def test_restarted_controller_must_complete_a_new_recovery_window(self, monotonic, restore):
        recovery = watchdog.Recovery()
        recovery.active = True
        state = self.snapshot()
        recovery.observe(state, {"hd": 2, "nvme": 1}, 101)
        state["start_time"] = 60
        recovery.observe(state, {"hd": 2, "nvme": 1}, 101)
        recovery.observe(state, {"hd": 2, "nvme": 1}, 101)
        restore.assert_not_called()

    @patch.object(watchdog, "restore_levels")
    @patch.object(watchdog.time, "monotonic", side_effect=[0, 30, 40])
    def test_cached_sensor_error_resets_the_recovery_window(self, monotonic, restore):
        recovery = watchdog.Recovery()
        recovery.active = True
        state = self.snapshot()
        recovery.observe(state, {"hd": 2, "nvme": 1}, 101)
        state["fan_controllers"][1]["devices"][0]["read_errors"] = 1
        with self.assertRaisesRegex(ValueError, "uncached"):
            recovery.observe(state, {"hd": 2, "nvme": 1}, 101)
        state["fan_controllers"][1]["devices"][0]["read_errors"] = 0
        recovery.observe(state, {"hd": 2, "nvme": 1}, 101)
        recovery.observe(state, {"hd": 2, "nvme": 1}, 101)
        restore.assert_not_called()

    def test_recovery_rejects_missing_cpu_invalid_temperature_and_unsafe_demand(self):
        for fault in ("missing-cpu", "nan", "too-hot", "mismatched-zone"):
            with self.subTest(fault=fault):
                state = self.snapshot()
                if fault == "missing-cpu":
                    state["fan_controllers"][0]["devices"].pop()
                elif fault == "nan":
                    state["fan_controllers"][1]["devices"][0]["temp_c"] = float("nan")
                elif fault == "too-hot":
                    state["fan_controllers"][1]["devices"][0]["temp_c"] = 61
                else:
                    state["zones"]["1"]["applied_level_pct"] = 50
                with self.assertRaises(ValueError):
                    watchdog.recovery_levels(state, {"hd": 2, "nvme": 1}, 101)

    @patch.object(watchdog.time, "time", return_value=101)
    @patch.object(watchdog, "read_snapshot")
    @patch.object(watchdog, "read_level", side_effect=[100, 70, 70, 70])
    @patch.object(watchdog.subprocess, "run")
    def test_latched_physical_fan_is_restored_without_restarting_smfc(self, run, read, snapshot, now):
        snapshot.return_value = self.snapshot()
        self.assertEqual(watchdog.restore_levels({"hd": 2, "nvme": 1}, 50), {"0": 70, "1": 70})
        run.assert_called_once()
        self.assertEqual(
            run.call_args.args[0],
            ["ipmitool", "raw", "0x30", "0x70", "0x66", "0x01", "0", "0x46"],
        )

    @patch.object(watchdog.time, "time", return_value=101)
    @patch.object(watchdog, "read_snapshot")
    @patch.object(watchdog, "read_level", side_effect=[100, 100])
    @patch.object(watchdog.subprocess, "run")
    def test_failed_physical_readback_keeps_recovery_failed(self, run, read, snapshot, now):
        snapshot.return_value = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, "did not match"):
            watchdog.restore_levels({"hd": 2, "nvme": 1}, 50)

    @patch.object(watchdog.time, "time", return_value=101)
    @patch.object(watchdog, "read_snapshot")
    @patch.object(watchdog, "read_level", return_value=100)
    @patch.object(watchdog.subprocess, "run")
    def test_controller_restart_before_write_cannot_lower_fans(self, run, read, snapshot, now):
        snapshot.return_value = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, "restarted"):
            watchdog.restore_levels({"hd": 2, "nvme": 1}, 49)
        run.assert_not_called()

    @patch.object(watchdog.time, "time", return_value=101)
    @patch.object(watchdog, "read_snapshot")
    @patch.object(watchdog, "read_level", side_effect=[100, 70, 100])
    @patch.object(watchdog.subprocess, "run")
    def test_partial_recovery_failure_is_escalated_to_the_fail_safe_handler(self, run, read, snapshot, now):
        snapshot.side_effect = [self.snapshot(), OSError("controller unavailable")]
        with self.assertRaisesRegex(RuntimeError, "controller unavailable"):
            watchdog.restore_levels({"hd": 2, "nvme": 1}, 50)
        run.assert_called_once()

    @patch.object(watchdog.time, "time", return_value=101)
    @patch.object(watchdog, "read_snapshot")
    @patch.object(watchdog, "read_level", side_effect=[70, 70, 70, 70])
    @patch.object(watchdog.subprocess, "run")
    def test_matching_physical_duties_require_no_writes(self, run, read, snapshot, now):
        snapshot.return_value = self.snapshot()
        watchdog.restore_levels({"hd": 2, "nvme": 1}, 50)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
