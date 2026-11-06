#!/usr/bin/env python3
"""Read-only NAS02 migration planning; never creates pools or runs transfers."""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys


SOURCE_BYTES = {
    "data": 44942121472000,
    "homes": 16641964244992,
    "docker": 42891108352,
}
PREFLIGHT = {
    "nas01": [
        ["sudo", "-n", "zpool", "status", "-x"],
        ["sudo", "-n", "zpool", "status", "-LP"],
        ["sudo", "-n", "zfs", "list", "-Hp", "-o",
         "name,used,avail,mountpoint", "nfs", "smb", "local", "backups"],
        ["sudo", "-n", "lsblk", "--json", "--bytes", "--output",
         "NAME,TYPE,SIZE,FSTYPE,MOUNTPOINTS"],
        ["rsync", "--version"],
    ],
    "nas02": [
        ["sudo", "-n", "df", "-k", "/volume1", "/volume2"],
        ["sudo", "-n", "/usr/bin/rsync", "--version"],
        ["python3", "--version"],
    ],
}


def digest_records(records):
    digest = hashlib.sha256()
    for record in records:
        encoded = json.dumps(record, ensure_ascii=True, separators=(",", ":")).encode()
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def scan(roots):
    entries, groups, freshness = {}, {}, []
    for index, value in enumerate(roots):
        root = Path(value)
        if not root.is_absolute() or root.is_symlink() or not root.is_dir():
            raise ValueError("each root must be an absolute, non-symlink directory")
        if root.resolve() in (Path("/"), Path("/proc"), Path("/sys"), Path("/dev")):
            raise ValueError("refusing a system root")
        root_stat = root.stat()
        pending = [root]
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as children:
                children = sorted(children, key=lambda child: os.fsencode(child.name))
            for child in children:
                if child.name in (".snapshot", "#snapshot", "@sharesnap"):
                    raise ValueError("snapshot container encountered; select one reviewed snapshot root")
                info = child.stat(follow_symlinks=False)
                relative = Path(child.path).relative_to(root).as_posix()
                if info.st_dev != root_stat.st_dev:
                    raise ValueError("filesystem boundary encountered; inventory separate datasets")
                if stat.S_ISDIR(info.st_mode):
                    kind = "directory"
                    pending.append(Path(child.path))
                elif stat.S_ISREG(info.st_mode):
                    kind = "file"
                elif stat.S_ISLNK(info.st_mode):
                    kind = "symlink"
                else:
                    raise ValueError("special file encountered; review scope before migrating")
                item = {
                    "path": relative, "absolute": child.path, "stat": info, "kind": kind,
                    "link": os.readlink(child.path) if kind == "symlink" else None,
                }
                previous = entries.get(relative)
                if previous:
                    if kind != "directory" or metadata(previous) != metadata(item):
                        raise ValueError("overlapping or conflicting paths in staging roots")
                else:
                    entries[relative] = item
                freshness.append((index, relative, info.st_dev, info.st_ino,
                                  info.st_size, info.st_mtime_ns, info.st_ctime_ns))
                if kind == "file":
                    key = (index, info.st_dev, info.st_ino)
                    groups.setdefault(key, []).append(item)
    for members in groups.values():
        if any(member["stat"].st_nlink != len(members) for member in members):
            raise ValueError("hardlinks leave a scanned root, or files changed during scanning")
    return entries, list(groups.values()), digest_records(sorted(freshness))


def metadata(item):
    info = item["stat"]
    return (item["path"], item["kind"], stat.S_IMODE(info.st_mode),
            info.st_uid, info.st_gid, info.st_mtime_ns // 1000000000,
            info.st_size if item["kind"] == "file" else item["link"])


def content_hash(item):
    before = item["stat"]
    descriptor = os.open(item["absolute"], os.O_RDONLY | os.O_NOFOLLOW)
    try:
        digest = hashlib.sha256()
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if any(getattr(before, field) != getattr(after, field) for field in fields):
        raise ValueError("source changed while checksumming; use a frozen read-only source")
    return digest.hexdigest()


def fingerprint(roots, checksum=False):
    entries, groups, signature = scan(roots)
    links = sorted(sorted(item["path"] for item in group) for group in groups)
    contents = []
    if checksum:
        for group in groups:
            checksum_value = content_hash(group[0])
            contents.extend((item["path"], checksum_value) for item in group)
    return {
        "format": 1,
        "files": sum(len(group) for group in groups),
        "directories": sum(item["kind"] == "directory" for item in entries.values()),
        "symlinks": sum(item["kind"] == "symlink" for item in entries.values()),
        "unique_file_bytes": sum(group[0]["stat"].st_size for group in groups),
        "hardlink_groups": sum(len(group) > 1 for group in groups),
        "metadata_sha256": digest_records(sorted(metadata(item) for item in entries.values())),
        "hardlinks_sha256": digest_records(links),
        "content_sha256": digest_records(sorted(contents)) if checksum else None,
        "scan_signature": signature,
        "acl_semantics": "NOT_VERIFIED: Synology ACL to NFSv4 requires a separate identity/ACL test",
        "source_consistency": "operator must freeze writers or use read-only snapshots",
    }


def parse_budgets(values):
    budgets = {}
    for value in values:
        name, separator, amount = value.partition("=")
        if not separator or not re.fullmatch(r"[a-z][a-z0-9_-]*", name):
            raise ValueError("budget must be name=BYTES with an opaque lowercase name")
        if name in budgets or not amount.isdecimal() or int(amount) <= 0:
            raise ValueError("budgets must be unique positive integer byte amounts")
        budgets[name] = int(amount)
    if not budgets:
        raise ValueError("pass measured additional budgets after headroom and production growth reserve")
    return budgets


def shard_plan(root, budgets, overhead_percent=3):
    entries, groups, signature = scan([root])
    remaining = dict(budgets)
    assigned = {name: [] for name in budgets}
    directories = sorted(item["path"] for item in entries.values()
                         if item["kind"] == "directory")
    directory_charge = len(directories) * 4096
    for name in remaining:
        remaining[name] -= directory_charge
        if remaining[name] < 0:
            raise ValueError("budget cannot hold conservative directory metadata")
    units = []
    for group in groups:
        size = max(group[0]["stat"].st_size, 4096)
        units.append(((size * (100 + overhead_percent) + 99) // 100,
                      sorted(item["path"] for item in group)))
    for item in entries.values():
        if item["kind"] == "symlink":
            units.append((4096, [item["path"]]))
    units.sort(key=lambda unit: (-unit[0], unit[1]))
    order = sorted(budgets, key=lambda name: (-budgets[name], name))
    for charge, paths in units:
        destination = next((name for name in order if remaining[name] >= charge), None)
        if destination is None:
            raise ValueError("hardlink-closed groups do not fit measured budgets; do not copy")
        remaining[destination] -= charge
        assigned[destination].extend(paths)
    lists = {name: sorted(directories + paths) for name, paths in assigned.items()}
    return {
        "scan_signature": signature,
        "unique_file_bytes": sum(group[0]["stat"].st_size for group in groups),
        "hardlink_groups": sum(len(group) > 1 for group in groups),
        "overhead_percent": overhead_percent,
        "shards": {name: {"budget_bytes": budgets[name],
                          "charged_bytes": budgets[name] - remaining[name],
                          "remaining_bytes": remaining[name],
                          "non_directory_entries": len(assigned[name])}
                   for name in budgets},
        "source_consistency": "frozen source required; no file lists saved by this tool",
    }, lists


def local_destination(value):
    path = Path(value)
    if (not path.is_absolute() or ".." in path.parts or len(path.parts) < 4
            or path.parts[1] != "mnt" or ":" in value
            or path.parts[2] in ("local", "backups", "boot-pool")
            or path == Path("/mnt/smb/home") or Path("/mnt/smb/home") in path.parents
            or path in (Path("/mnt/nfs/media"), Path("/mnt/nfs/netboot"))):
        raise ValueError("destination must be an explicit non-production /mnt/POOL/DATASET path")
    if path.resolve() != path:
        raise ValueError("refusing a symlink destination")
    return value.rstrip("/") + "/"


def ssh_target(value):
    if not re.fullmatch(r"(?:[a-zA-Z0-9_][a-zA-Z0-9_.-]*@)?"
                        r"[a-zA-Z0-9][a-zA-Z0-9.-]*", value):
        raise ValueError("SSH target must be an ordinary host or user@host, not options")
    return value


def rsync_plan(source, destination, sharded=False, checksum=False, posix_acls=False,
               source_sudo=False):
    if any(character in source + destination for character in ("\0", "\n", "\r")):
        raise ValueError("invalid endpoint")
    if ":" in source:
        host, path = source.split(":", 1)
        ssh_target(host)
        if not re.fullmatch(r"/volume1/(?:data|homes|docker)"
                            r"(?:/\.snapshot/(?!\.\.?/|\.{1,2}$)[a-zA-Z0-9_.-]+)?/?", path):
            raise ValueError("remote source must be a reviewed NAS02 share root")
    else:
        path = source
        if not path.startswith("/mnt/") or ".." in Path(path).parts or len(Path(path).parts) < 4:
            raise ValueError("local source must be an explicit /mnt/POOL/DATASET path")
        source_path, destination_path = Path(path), Path(destination)
        if (source_path == destination_path or source_path in destination_path.parents
                or destination_path in source_path.parents):
            raise ValueError("source and destination overlap")
    command = ["rsync", "-aHXS", "--numeric-ids", "--protect-args",
               "--dry-run", "--itemize-changes", "--stats"]
    if posix_acls:
        command.append("--acls")
    if checksum:
        command.append("--checksum")
    if sharded:
        command.extend(["--from0", "--files-from=-", "--no-recursive", "--dirs"])
    if ":" in source:
        command.extend(["-e", "ssh -T -o BatchMode=yes -o ConnectTimeout=10"])
        if source_sudo:
            command.append("--rsync-path=sudo -n /usr/bin/rsync")
    elif source_sudo:
        raise ValueError("--source-sudo only applies to an already authorized remote operator")
    command.extend(["--", source.rstrip("/") + "/", local_destination(destination)])
    return {
        "execute": False, "argv": command, "shell": shlex.join(command),
        "hardlinks": "one complete hardlink-closed list per staging filesystem" if sharded
                     else "entire tree, one destination filesystem",
        "acl_semantics": "NOT_VERIFIED; --acls is only for a separately tested POSIX ACL path",
        "warning": "RUN ON NAS01; dry-run only. No deletion, mount, share or pool actions are implemented.",
    }


def capacity():
    vdevs = {
        "current_nfs": (32, 8, 0),
        "current_smb": (24, 4, 0),
        "loaner_11x4_raidz1": (44, 4, 0),
        "loaner_11x4_raidz2": (44, 8, 0),
        "loaner_12x4_raidz2": (48, 8, 0),
        "smb_17wide_raidz1_expanded": (68, 4, 0),
        "smb_17wide_raidz2_recreated": (68, 8, 0),
        "donor_two_4wide_raidz1": (128, 32, 0),
        "donor_8wide_raidz2": (128, 24, 32),
        "final_donor8_plus_4x8_raidz2": (160, 40, 32),
        "final_three_4wide_raidz2": (160, 80, 0),
    }
    return {
        "mode": "READ_ONLY_ESTIMATE_NOT_A_CAPACITY_APPROVAL",
        "measurement_date": "2026-11-06",
        "source_measurement_date": "2026-11-02",
        "detected_loaner_disks": 11,
        "source_bytes": SOURCE_BYTES,
        "source_total_bytes": sum(SOURCE_BYTES.values()),
        "source_total_tib": sum(SOURCE_BYTES.values()) / 2**40,
        "three_percent_allowance_bytes": math.ceil(sum(SOURCE_BYTES.values()) * 1.03),
        "layouts": {
            name: {"raw_tb": raw, "parity_tb": parity, "stranded_tb": stranded,
                   "nominal_usable_tb": raw - parity - stranded,
                   "nominal_usable_tib": (raw - parity - stranded) * 10**12 / 2**40,
                   "nominal_80_percent_tb": (raw - parity - stranded) * 0.8}
            for name, (raw, parity, stranded) in vdevs.items()
        },
        "gates": [
            "du physical bytes are not a logical-byte inventory; scan frozen source before sizing",
            "measure dataset available, quotas, snapshots, ZFS overhead and 20% headroom",
            "reserve ongoing production growth; never consume local/backups as staging",
            "verify physical bays, power, HBA, SMART, independent critical-data backup and ABB recovery",
            "all loans form a disposable staging pool, not permanent vdevs",
            "17-wide comparisons do not authorize growing production SMB; RAIDZ cannot shrink or change parity",
        ],
    }


def additional_budget(used, available, growth_reserve=0, headroom_percent=20):
    if min(used, available, growth_reserve) < 0 or not 20 <= headroom_percent < 100:
        raise ValueError("nonnegative bytes and at least 20 percent headroom are required")
    budget = (used + available) * (100 - headroom_percent) // 100 - used - growth_reserve
    return {
        "additional_budget_bytes": max(0, budget),
        "used_bytes": used, "available_bytes": available,
        "growth_reserve_bytes": growth_reserve, "headroom_percent": headroom_percent,
        "warning": "use fresh destination dataset/root measurements; pool raw SIZE/FREE is not payload capacity",
    }


def preflight(host, target=None, run=False):
    commands = PREFLIGHT[host]
    if target:
        target = ssh_target(target)
        commands = [["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                     target, shlex.join(command)] for command in commands]
    if not run:
        return {"execute": False, "read_only_commands": commands,
                "note": "--run executes only this fixed inventory/version allowlist; never a transfer"}
    results = []
    for command in commands:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
        results.append({"argv": command, "returncode": result.returncode,
                        "stdout": result.stdout, "stderr": result.stderr})
    if any(result["returncode"] for result in results):
        raise ValueError("read-only preflight failed: " + json.dumps(results))
    return {"read_only_results": results, "migration_approved": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("capacity")
    budget = commands.add_parser("budget")
    budget.add_argument("--used-bytes", type=int, required=True)
    budget.add_argument("--available-bytes", type=int, required=True)
    budget.add_argument("--growth-reserve-bytes", type=int, default=0)
    budget.add_argument("--headroom-percent", type=int, default=20)
    probe = commands.add_parser("preflight")
    probe.add_argument("--host", choices=PREFLIGHT, required=True)
    probe.add_argument("--ssh")
    probe.add_argument("--run", action="store_true")
    transfer = commands.add_parser("rsync-plan")
    transfer.add_argument("--source", required=True)
    transfer.add_argument("--destination", required=True)
    transfer.add_argument("--sharded", action="store_true")
    transfer.add_argument("--checksum", action="store_true")
    transfer.add_argument("--posix-acls-tested", action="store_true")
    transfer.add_argument("--source-sudo", action="store_true")
    shards = commands.add_parser("shards")
    shards.add_argument("--root", required=True)
    shards.add_argument("--budget", action="append", default=[])
    shards.add_argument("--overhead-percent", type=int, default=3, choices=range(3, 101))
    shards.add_argument("--files-for")
    shards.add_argument("--expect-signature")
    for name in ("fingerprint", "verify"):
        comparison = commands.add_parser(name)
        comparison.add_argument("--root", action="append", required=True)
        comparison.add_argument("--checksum", action="store_true")
        if name == "verify":
            comparison.add_argument("--baseline", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command in (None, "capacity"):
            result = capacity()
        elif args.command == "budget":
            result = additional_budget(args.used_bytes, args.available_bytes,
                                       args.growth_reserve_bytes, args.headroom_percent)
        elif args.command == "preflight":
            result = preflight(args.host, args.ssh, args.run)
        elif args.command == "rsync-plan":
            result = rsync_plan(args.source, args.destination, args.sharded,
                                args.checksum, args.posix_acls_tested, args.source_sudo)
        elif args.command == "shards":
            result, lists = shard_plan(args.root, parse_budgets(args.budget), args.overhead_percent)
            if args.files_for is not None:
                if not args.expect_signature or args.expect_signature != result["scan_signature"]:
                    raise ValueError("a matching frozen-source --expect-signature is required")
                if args.files_for not in lists:
                    raise ValueError("unknown shard name")
                for path in lists[args.files_for]:
                    sys.stdout.buffer.write(os.fsencode("./" + path) + b"\0")
                return 0
        else:
            result = fingerprint(args.root, args.checksum)
            if args.command == "verify":
                with open(args.baseline, encoding="utf-8") as stream:
                    baseline = json.load(stream)
                fields = ("format", "files", "directories", "symlinks", "unique_file_bytes",
                          "metadata_sha256", "hardlinks_sha256", "content_sha256")
                if not args.checksum or not baseline.get("content_sha256"):
                    raise ValueError("verify requires --checksum and a checksummed baseline")
                mismatched = [field for field in fields if baseline.get(field) != result[field]]
                result["matches_baseline"] = not mismatched
                result["mismatched_fields"] = mismatched
                print(json.dumps(result, indent=2))
                return 1 if mismatched else 0
        print(json.dumps(result, indent=2))
        return 0
    except OSError as error:
        print("STOP: filesystem/command operation failed (errno "
              + str(error.errno) + "); inspect the failing path privately", file=sys.stderr)
        return 2
    except (ValueError, subprocess.SubprocessError) as error:
        print("STOP: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
