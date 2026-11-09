#!/usr/bin/env python3
"""Read NAS01 HDD self-test logs and publish node-exporter textfile metrics."""

import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

SYS_BLOCK = Path("/sys/block")
DEV = Path("/dev")
BY_ID = DEV / "disk/by-id"
OUT = Path("/mnt/local/scripts/textfile/smart_selftest.prom")
LOCK = Path("/run/lock/nas01-smart-report.lock")
PROBE_TIMEOUT = 15
REAP_TIMEOUT = 3
STATUS_METRICS = (
    "nas01_smart_selftest_probe_success",
    "nas01_smart_selftest_available",
    "nas01_smart_selftest_report_success",
)


class BlockedProbe(RuntimeError):
    pass


def discover_devices():
    aliases = {}
    for link in BY_ID.iterdir():
        if not link.name.startswith(("wwn-", "ata-", "scsi-")):
            continue
        if re.search(r"-part\d+$", link.name):
            continue
        target = link.resolve()
        if target.parent == DEV:
            aliases.setdefault(target.name, []).append(link)

    devices = []
    for disk in sorted(SYS_BLOCK.glob("sd*")):
        rotational = (disk / "queue/rotational").read_text().strip()
        size = int((disk / "size").read_text().strip())
        if rotational not in ("0", "1") or size < 0:
            raise ValueError(f"Invalid disk metadata for {disk.name}")
        if rotational != "1" or size == 0:
            continue
        options = aliases.get(disk.name, [])
        if not options:
            raise ValueError(f"No stable whole-disk identity for {disk.name}")
        identity = min(options, key=lambda p: (not p.name.startswith("wwn-"), p.name))
        devices.append((disk.name, identity))
    if not devices:
        raise ValueError("No identifiable nonzero-capacity rotational disks")
    return devices


def smart(identity, lock_fd):
    # The child retains the lock if uninterruptible I/O outlives this reporter.
    process = subprocess.Popen(
        ["smartctl", "-a", "-j", "-d", "auto", str(identity)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        pass_fds=(lock_fd,),
    )
    try:
        output, errors = process.communicate(timeout=PROBE_TIMEOUT)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        try:
            process.communicate(timeout=REAP_TIMEOUT)
        except subprocess.TimeoutExpired as error:
            raise BlockedProbe(
                f"{identity}: smartctl PID {process.pid} did not exit after SIGKILL; "
                "stopping further probes; controller recovery may be required"
            ) from error
        raise ValueError(f"{identity}: SMART read exceeded {PROBE_TIMEOUT}s")
    if process.returncode < 0 or process.returncode & 7:
        detail = errors.decode(errors="replace").strip()[:300]
        raise ValueError(f"{identity}: smartctl read failed ({process.returncode}): {detail}")
    data = json.loads(output)
    if not isinstance(data, dict):
        raise ValueError(f"{identity}: SMART response is not an object")
    return data


def newest_entry(data):
    if "scsi_self_test_0" in data:
        for index in range(20):
            scsi = data.get(f"scsi_self_test_{index}")
            if scsi is None:
                continue
            code = scsi["result"]["value"]
            if not isinstance(code, int) or not 0 <= code <= 15:
                raise ValueError("Invalid SCSI self-test result")
            if code in (1, 2, 15):
                print(f"Ignoring incomplete SCSI self-test result {code}", file=sys.stderr)
                continue
            return code != 0, scsi.get("power_on_time", {}).get("hours")
        return None
    table = data.get("ata_smart_self_test_log", {}).get("standard", {}).get("table", [])
    for entry in table:
        status = entry["status"]
        value = status.get("value")
        if value is not None:
            if not isinstance(value, int) or not 0 <= value <= 255:
                raise ValueError("Invalid ATA self-test status")
            # The high nibble marks aborted, reset-interrupted and in-progress tests.
            if value >> 4 in (1, 2, 15):
                print(f"Ignoring incomplete ATA self-test status {value}", file=sys.stderr)
                continue
        passed = status.get("passed")
        if not isinstance(passed, bool):
            if value is None or value >> 4 not in (0, 3, 4, 5, 6, 7, 8, 9):
                raise ValueError("Invalid ATA self-test result")
            passed = value >> 4 == 0
        return not passed, entry.get("lifetime_hours")
    return None


def labels(**values):
    escaped = []
    for key, value in values.items():
        if not isinstance(value, str) or not value:
            raise ValueError(f"Missing or invalid {key} label")
        value = value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
        escaped.append(f'{key}="{value}"')
    return ",".join(escaped)


def previous_snapshot():
    try:
        previous = OUT.read_text().splitlines()
    except FileNotFoundError:
        print("No previous complete SMART snapshot is available", file=sys.stderr)
        return []
    return [
        line for line in previous
        if not any(
            line.startswith((name + " ", name + "{", "# HELP " + name + " ", "# TYPE " + name + " "))
            for name in STATUS_METRICS
        )
    ]


def publish(lines):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".smart_selftest.", dir=OUT.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write("\n".join(lines) + "\n")
        os.chmod(temporary, 0o644)
        os.replace(temporary, OUT)
    finally:
        Path(temporary).unlink(missing_ok=True)


def collect(lock_fd):
    lines = [
        "# HELP nas01_smart_selftest_failed Most recent completed SMART self-test failed (1) or passed (0).",
        "# TYPE nas01_smart_selftest_failed gauge",
        "# HELP nas01_smart_selftest_age_hours Drive power-on hours since the most recent self-test.",
        "# TYPE nas01_smart_selftest_age_hours gauge",
    ]
    status = [
        "# HELP nas01_smart_selftest_probe_success Current disk log read and parsing succeeded.",
        "# TYPE nas01_smart_selftest_probe_success gauge",
        "# HELP nas01_smart_selftest_available A completed self-test entry exists on this disk.",
        "# TYPE nas01_smart_selftest_available gauge",
        "# HELP nas01_smart_selftest_report_success All discovered HDD log reads succeeded.",
        "# TYPE nas01_smart_selftest_report_success gauge",
    ]
    success = True
    blocked = False
    completed = 0
    try:
        devices = discover_devices()
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Disk discovery failed: {error}", file=sys.stderr)
        devices = []
        success = False
    for name, identity in devices:
        probe_labels = labels(device=name, identity=identity.name)
        probe_success = False
        if blocked:
            print(f"Not probing {identity}: previous SMART child is blocked", file=sys.stderr)
        else:
            try:
                data = smart(identity, lock_fd)
                model = data.get("model_name") or data.get("scsi_model_name")
                disk_labels = labels(device=name, model=model, serial=data.get("serial_number"))
                now = data.get("power_on_time", {}).get("hours")
                if not isinstance(now, int) or now < 0:
                    raise ValueError("Missing or invalid drive power-on hours")
                entry = newest_entry(data)
                if entry is not None:
                    failed, when = entry
                    if when is not None and (not isinstance(when, int) or not 0 <= when <= now):
                        raise ValueError("Invalid self-test lifetime")
                    lines.append(f"nas01_smart_selftest_failed{{{disk_labels}}} {int(failed)}")
                    if when is not None:
                        lines.append(f"nas01_smart_selftest_age_hours{{{disk_labels}}} {now - when}")
                status.append(f"nas01_smart_selftest_available{{{probe_labels}}} {int(entry is not None)}")
                probe_success = True
                completed += 1
            except BlockedProbe as error:
                blocked = True
                print(error, file=sys.stderr)
            except (OSError, ValueError, KeyError, TypeError) as error:
                print(f"SMART read failed for {identity}: {error}", file=sys.stderr)
        success = success and probe_success
        status.append(f"nas01_smart_selftest_probe_success{{{probe_labels}}} {int(probe_success)}")
    if success:
        lines.extend([
            "# HELP nas01_smart_selftest_report_timestamp_seconds Last complete successful collection.",
            "# TYPE nas01_smart_selftest_report_timestamp_seconds gauge",
            f"nas01_smart_selftest_report_timestamp_seconds {int(time.time())}",
        ])
    else:
        lines = previous_snapshot()
    status.append(f"nas01_smart_selftest_report_success {int(success)}")
    publish(lines + status)
    print(f"SMART collection: {completed}/{len(devices)} disks read; success={success}")
    return 0 if success else 1


def main():
    try:
        with LOCK.open("a") as lock:
            os.fchmod(lock.fileno(), 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return collect(lock.fileno())
    except BlockingIOError:
        print("SMART reporter or its child still holds the lock; refusing more probes", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"SMART reporter filesystem/process error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
