"""Independent fail-high guard for a stopped or stalled SMFC control loop."""

import configparser
import json
import logging
import math
import subprocess
import time
import urllib.error
import urllib.request


LOG = logging.getLogger("smfc-watchdog")


def expected_counts(path):
    config = configparser.ConfigParser()
    with open(path, encoding="utf-8") as stream:
        config.read_file(stream)
    return {
        "hd": len(config["HD"]["hd_names"].split()),
        "nvme": len(config["NVME"]["nvme_names"].split()),
    }


def validate_snapshot(snapshot, counts, now):
    if not 0 <= now - snapshot["generated_at"] <= 15:
        raise ValueError("SMFC snapshot timestamp is stale")
    mode = snapshot["fan_mode"]
    if mode["control_held"] is not True or not 0 <= mode["age_s"] <= 60:
        raise ValueError("SMFC control-loop heartbeat is stale or control was lost")
    controllers = {
        controller["type"]: controller
        for controller in snapshot["fan_controllers"]
        if controller["enabled"]
    }
    if controllers["cpu"]["device_count"] < 1:
        raise ValueError("SMFC has no CPU sensors")
    for kind, expected in counts.items():
        controller = controllers[kind]
        if expected < 1 or controller["device_count"] != expected:
            raise ValueError(f"SMFC {kind} inventory does not match the reviewed configuration")
        if len(controller["devices"]) != expected:
            raise ValueError(f"SMFC {kind} readings are incomplete")
    for zone in ("0", "1"):
        if not 50 <= snapshot["zones"][zone]["applied_level_pct"] <= 100:
            raise ValueError(f"SMFC zone {zone} is outside the commissioned range")


def recovery_levels(snapshot, counts, now):
    validate_snapshot(snapshot, counts, now)
    if snapshot["fan_mode"]["id"] != 1 or snapshot["fan_mode"]["age_s"] > 5:
        raise ValueError("SMFC recovery requires a fresh FULL-mode heartbeat")
    controllers = [controller for controller in snapshot["fan_controllers"] if controller["enabled"]]
    if len(controllers) != 4 or {controller["type"] for controller in controllers} != {
        "cpu", "hd", "nvme", "const"
    }:
        raise ValueError("SMFC recovery requires all four commissioned controllers")
    for controller in controllers:
        if set(controller["ipmi_zones"]) != {0, 1}:
            raise ValueError("SMFC recovery requires the commissioned shared zones")
        if controller["type"] == "const":
            continue
        expected = 2 if controller["type"] == "cpu" else counts[controller["type"]]
        if controller["device_count"] != expected or len(controller["devices"]) != expected:
            raise ValueError("SMFC recovery requires complete CPU and disk readings")
        for device in controller["devices"]:
            temperature = device["temp_c"]
            if (
                device["read_errors"] != 0
                or not math.isfinite(temperature)
                or not 0 < temperature < 150
            ):
                raise ValueError("SMFC recovery requires valid, uncached temperature readings")
            if temperature >= controller["temp_max_c"] and controller["last_level_pct"] != 100:
                raise ValueError("SMFC recovery demand does not protect a hot device")
    levels = {}
    for zone in ("0", "1"):
        level = max(controller["last_level_pct"] for controller in controllers)
        if type(level) is not int or not 50 <= level <= 100:
            raise ValueError("SMFC recovery demand is outside the commissioned range")
        if snapshot["zones"][zone]["applied_level_pct"] != level:
            raise ValueError("SMFC recovery demand is inconsistent with its controllers")
        levels[zone] = level
    return levels


def read_snapshot():
    with urllib.request.urlopen("http://smfc:9099/snapshot", timeout=5) as response:
        return json.load(response)


def read_level(zone):
    result = subprocess.run(
        ["ipmitool", "raw", "0x30", "0x70", "0x66", "0x00", zone],
        check=True, capture_output=True, text=True, timeout=8,
    )
    level = int(result.stdout.strip(), 16)
    if not 0 <= level <= 100:
        raise ValueError(f"Invalid physical fan duty for zone {zone}")
    return level


def restore_levels(counts, start_time):
    restored = {}
    try:
        for zone in ("0", "1"):
            current = read_level(zone)
            snapshot = read_snapshot()
            levels = recovery_levels(snapshot, counts, time.time())
            if snapshot["start_time"] != start_time:
                raise ValueError("SMFC restarted during recovery")
            target = levels[zone]
            if current < target:
                raise RuntimeError(f"Physical fan duty in zone {zone} is below native demand")
            if current > target:
                LOG.warning("Restoring zone %s from %s%% to verified SMFC demand %s%%", zone, current, target)
                subprocess.run(
                    ["ipmitool", "raw", "0x30", "0x70", "0x66", "0x01", zone, hex(target)],
                    check=True, capture_output=True, text=True, timeout=8,
                )
            if read_level(zone) != target:
                raise RuntimeError(f"Physical fan duty in zone {zone} did not match recovery demand")
            restored[zone] = target
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        raise RuntimeError(f"SMFC recovery could not be verified: {error}") from error
    return restored


class Recovery:
    def __init__(self):
        self.active = False
        self.reset()

    def reset(self):
        self.healthy_since = None
        self.start_time = None

    def observe(self, snapshot, counts, now):
        if not self.active:
            return
        try:
            recovery_levels(snapshot, counts, now)
            start_time = snapshot["start_time"]
            if not math.isfinite(start_time) or start_time <= 0:
                raise ValueError("SMFC recovery requires a valid process start time")
            polling = [controller["polling"] for controller in snapshot["fan_controllers"] if controller["enabled"]]
            if any(not math.isfinite(interval) or interval <= 0 for interval in polling):
                raise ValueError("SMFC recovery requires valid polling intervals")
            steady = time.monotonic()
            if self.start_time != start_time:
                self.start_time = start_time
                self.healthy_since = steady
            # Cover at least two complete cycles of the slowest sensor controller.
            if steady - self.healthy_since < max(30, 2 * max(polling)):
                return
            levels = restore_levels(counts, start_time)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError):
            self.reset()
            raise
        self.active = False
        self.reset()
        LOG.info("SMFC recovered; physical fan duties verified: %s", levels)


def fail_high():
    failures = []
    for command in (
        ["0x30", "0x45", "0x01", "0x01"],
        ["0x30", "0x70", "0x66", "0x01", "0x00", "0x64"],
        ["0x30", "0x70", "0x66", "0x01", "0x01", "0x64"],
    ):
        try:
            subprocess.run(["ipmitool", "raw", *command], check=True, timeout=8)
        except (OSError, subprocess.SubprocessError) as error:
            failures.append(str(error))
    if failures:
        raise RuntimeError("; ".join(failures))


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    startup_deadline = time.monotonic() + 120
    healthy = False
    recovery = Recovery()
    while True:
        try:
            counts = expected_counts("/etc/smfc/smfc.conf")
            snapshot = read_snapshot()
            validate_snapshot(snapshot, counts, time.time())
        except (OSError, urllib.error.URLError, configparser.Error, ValueError, KeyError, TypeError) as error:
            recovery.reset()
            LOG.error("SMFC health check failed: %s", error)
            if healthy or time.monotonic() >= startup_deadline:
                recovery.active = True
                LOG.error("Setting both fan zones to 100%")
                try:
                    fail_high()
                except RuntimeError as failure:
                    LOG.critical("Fan fail-safe command failed; retrying next check: %s", failure)
        else:
            if not healthy:
                LOG.info("SMFC control loop and complete disk inventory verified")
            healthy = True
            try:
                recovery.observe(snapshot, counts, time.time())
            except (OSError, ValueError, KeyError, TypeError) as error:
                LOG.warning("Keeping fail-safe recovery pending: %s", error)
            except (RuntimeError, subprocess.SubprocessError) as error:
                LOG.error("SMFC physical fan recovery failed: %s", error)
                try:
                    fail_high()
                except RuntimeError as failure:
                    LOG.critical("Fan fail-safe command failed; retrying next check: %s", failure)
        time.sleep(10)


if __name__ == "__main__":
    main()
