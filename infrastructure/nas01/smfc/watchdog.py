"""Independent fail-high guard for a stopped or stalled SMFC control loop."""

import configparser
import json
import logging
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
    while True:
        try:
            counts = expected_counts("/etc/smfc/smfc.conf")
            with urllib.request.urlopen("http://smfc:9099/snapshot", timeout=5) as response:
                snapshot = json.load(response)
            validate_snapshot(snapshot, counts, time.time())
        except (OSError, urllib.error.URLError, configparser.Error, ValueError, KeyError, TypeError) as error:
            LOG.error("SMFC health check failed: %s", error)
            if healthy or time.monotonic() >= startup_deadline:
                LOG.error("Setting both fan zones to 100%%")
                try:
                    fail_high()
                except RuntimeError as failure:
                    LOG.critical("Fan fail-safe command failed; retrying next check: %s", failure)
        else:
            if not healthy:
                LOG.info("SMFC control loop and complete disk inventory verified")
            healthy = True
        time.sleep(10)


if __name__ == "__main__":
    main()
