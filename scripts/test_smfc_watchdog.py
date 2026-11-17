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
            "fan_mode": {"control_held": True, "age_s": 1},
            "fan_controllers": [
                {"type": "cpu", "enabled": True, "device_count": 2},
                {"type": "hd", "enabled": True, "device_count": 2, "devices": [{}, {}]},
                {"type": "nvme", "enabled": True, "device_count": 1, "devices": [{}]},
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


if __name__ == "__main__":
    unittest.main()
