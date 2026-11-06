#!/usr/bin/env python3
"""Prepare the four-Pi lab without changing production or selecting unknown disks."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import struct
import subprocess
import tarfile
import time

ROOT = Path(__file__).resolve().parent
STATE = ROOT / ".state"
KUBECONFIG = ROOT.parents[1] / "kubeconfig"
VERSION = "v1.14.5"
KUBERNETES_VERSION = "1.37.1"
SCHEMATIC = "ee21ef4a5ef808a9b7484cc0dda0f25075021691c8c09a276591eedb638ea1f9"
OVERLAY = (
    "ghcr.io/siderolabs/sbc-raspberrypi:v0.2.2"
    "@sha256:af82d9f97241fb66c5b660b03e9154fd54ba4560b58ed3b53765bb930d564167"
)
FACTORY = f"https://pxe.factory.talos.dev/image/{SCHEMATIC}/{VERSION}"
ADDRESSES = {f"pi0{i}": f"192.168.42.{20+i}" for i in range(1, 5)}
BOOT_SERVER = "192.168.69.131"


def run(args, **kwargs):
    return subprocess.run(
        [str(arg) for arg in args], check=True, text=True, **kwargs
    )


def private_state():
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    STATE.chmod(0o700)


def save_json(path, data):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open("w") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")
    path.chmod(0o600)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inventory():
    data = json.loads((STATE / "inventory.json").read_text())
    if set(data) != set(ADDRESSES):
        raise ValueError("Inventory must contain exactly pi01, pi02, pi03 and pi04")
    macs = set()
    for name, item in data.items():
        if item.get("ip") != ADDRESSES[name]:
            raise ValueError(f"{name}: address is outside the reserved lab scope")
        mac = item.get("mac", "").lower()
        if not re.fullmatch(r"[0-9a-f]{2}(:[0-9a-f]{2}){5}", mac) or mac in macs:
            raise ValueError(f"{name}: invalid or duplicate wired MAC")
        item["mac"] = mac
        macs.add(mac)
        serial = item.get("serial")
        if serial and not re.fullmatch(r"[0-9a-fA-F]{8,16}", serial):
            raise ValueError(f"{name}: invalid board serial")
    return data


def download(url, path):
    pending = path.with_suffix(path.suffix + ".part")
    try:
        run([
            "curl", "--fail", "--silent", "--show-error", "--location",
            "--max-time", "300", "--output", pending, url,
        ])
        if pending.stat().st_size < 1024:
            raise ValueError(f"Unexpectedly small boot artifact: {url}")
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)


def native_kernel(source, destination):
    image = source.read_bytes()
    if image[:8] == b"MZ\0\0zimg":
        offset, size = struct.unpack_from("<II", image, 8)
        if image[24:32].rstrip(b"\0") != b"zstd" or offset < 64 or offset + size > len(image):
            raise ValueError("Unsupported or truncated EFI zboot payload")
        # Linux's documented zboot header identifies the compressed native Image.
        with destination.open("wb") as stream:
            subprocess.run(
                ["zstd", "--decompress", "--stdout"], input=image[offset:offset+size],
                stdout=stream, check=True,
            )
    else:
        shutil.copyfile(source, destination)
    with destination.open("rb") as stream:
        if stream.read(64)[56:60] != b"ARM\x64":
            raise ValueError("Kernel is not a native uncompressed ARM64 Linux Image")


def firmware_member(name):
    prefix = "artifacts/arm64/firmware/boot/"
    if not name.startswith(prefix):
        return None
    relative = PurePosixPath(name[len(prefix):])
    if not relative.parts or relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Unsafe firmware archive path: {name}")
    return relative


def assets():
    private_state()
    directory = STATE / "boot"
    receipt = STATE / "assets.json"
    if receipt.exists():
        verify_local_assets()
        print(f"Verified cached {VERSION} native Pi boot assets")
        return
    directory.mkdir(mode=0o700, exist_ok=True)
    process = subprocess.Popen(
        ["crane", "export", OVERLAY, "-"], stdout=subprocess.PIPE
    )
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|*") as archive:
            for member in archive:
                relative = firmware_member(member.name)
                if relative is None or member.isdir():
                    continue
                if not member.isfile():
                    raise ValueError(f"Non-regular firmware archive member: {member.name}")
                destination = directory / str(relative)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target)
        if process.wait():
            raise RuntimeError("crane could not export the pinned Raspberry Pi overlay")
    finally:
        if process.poll() is None:
            process.terminate()
        process.stdout.close()
        process.wait()
    kernel_source = STATE / "kernel-arm64.efi"
    if not kernel_source.exists():
        download(f"{FACTORY}/kernel-arm64", kernel_source)
    native_kernel(kernel_source, directory / "kernel8.img")
    if not (directory / "initramfs-arm64.xz").exists():
        download(f"{FACTORY}/initramfs-arm64.xz", directory / "initramfs-arm64.xz")
    script = run([
        "curl", "--fail", "--silent", "--show-error", "--location", "--max-time", "90",
        f"https://factory.talos.dev/pxe/{SCHEMATIC}/{VERSION}/metal-arm64",
    ], capture_output=True).stdout
    kernel_line = next(line for line in script.splitlines() if line.startswith("kernel "))
    arguments = [
        arg for arg in shlex.split(kernel_line)[2:] if not arg.startswith("console=")
    ]
    if any(arg.startswith("talos.config=") for arg in arguments):
        raise ValueError("Network boot must not distribute a machine configuration")
    arguments += [
        "console=tty0", "console=ttyAMA0,115200",
        "sysctl.kernel.kexec_load_disabled=1", "talos.dashboard.disabled=1",
    ]
    (directory / "cmdline.txt").write_text(" ".join(arguments) + "\n")
    (directory / "config.txt").write_text(
        "arm_64bit=1\n"
        "kernel=kernel8.img\n"
        "initramfs initramfs-arm64.xz followkernel\n"
        "cmdline=cmdline.txt\n"
        "gpu_mem=32\n"
        "arm_boost=1\n"
        "enable_uart=1\n"
        "dtoverlay=disable-bt\n"
        "dtoverlay=disable-wifi\n"
    )
    for required in ("start4.elf", "fixup4.dat", "bcm2711-rpi-4-b.dtb"):
        if not (directory / required).is_file():
            raise ValueError(f"Missing Pi 4 firmware: {required}")
    files = {
        str(path.relative_to(directory)): digest(path)
        for path in sorted(directory.rglob("*")) if path.is_file()
    }
    save_json(receipt, {
        "talos": VERSION, "schematic": SCHEMATIC, "overlay": OVERLAY, "files": files,
    })
    print(f"Prepared {len(files)} firmware/kernel/initramfs files; no install config served")


def verify_local_assets():
    receipt = json.loads((STATE / "assets.json").read_text())
    if (receipt["talos"], receipt["schematic"], receipt["overlay"]) != (
        VERSION, SCHEMATIC, OVERLAY
    ):
        raise ValueError("Cached assets use a different pinned boot recipe")
    actual = {
        str(path.relative_to(STATE / "boot"))
        for path in (STATE / "boot").rglob("*") if path.is_file()
    }
    if actual != set(receipt["files"]):
        raise ValueError("Cached boot asset file inventory changed")
    for name, expected in receipt["files"].items():
        if digest(STATE / "boot" / name) != expected:
            raise ValueError(f"Boot asset checksum mismatch: {name}")
    return receipt


def prefixes(item):
    result = [item["mac"].replace(":", "-")]
    if item.get("serial"):
        result.append(item["serial"][-8:].lower())
    return result


def kubectl(*args):
    return ["kubectl", "--kubeconfig", str(KUBECONFIG), "-n", "network", *args]


def stage():
    data = inventory()
    receipt = verify_local_assets()
    uid = int(run(
        kubectl("exec", "deploy/netboot-xyz", "--", "id", "-u", "nbxyz"),
        capture_output=True,
    ).stdout.strip())
    gid = int(run(
        kubectl("exec", "deploy/netboot-xyz", "--", "id", "-g", "nbxyz"),
        capture_output=True,
    ).stdout.strip())
    all_prefixes = [prefix for item in data.values() for prefix in prefixes(item)]
    if len(all_prefixes) != len(set(all_prefixes)):
        raise ValueError("Duplicate board boot prefixes")
    # Never overwrite an existing boot policy, even for an allowlisted address.
    for prefix in all_prefixes:
        run(kubectl(
            "exec", "deploy/netboot-xyz", "--", "test", "!", "-e",
            f"/config/menus/{prefix}",
        ), capture_output=True)
    process = subprocess.Popen(
        kubectl("exec", "-i", "deploy/netboot-xyz", "--", "tar", "xf", "-", "-C", "/config/menus"),
        stdin=subprocess.PIPE,
    )
    try:
        with tarfile.open(fileobj=process.stdin, mode="w|") as archive:
            for prefix in all_prefixes:
                for name in receipt["files"]:
                    source = STATE / "boot" / name
                    info = archive.gettarinfo(str(source), arcname=f"{prefix}/{name}")
                    info.uid, info.gid = uid, gid
                    info.uname, info.gname = "nbxyz", "nbxyz"
                    info.mode = 0o644
                    with source.open("rb") as stream:
                        archive.addfile(info, stream)
        process.stdin.close()
        if process.wait():
            raise RuntimeError("Scoped boot asset upload failed")
    finally:
        if process.poll() is None:
            process.terminate()
        if not process.stdin.closed:
            process.stdin.close()
        process.wait()
    save_json(STATE / "staged.json", {
        "time": time.time(), "prefixes": all_prefixes, "files": receipt["files"],
    })
    print("Staged only allowlisted MAC/verified-serial directories; root boot policy unchanged")


def verify():
    data = inventory()
    receipt = verify_local_assets()
    for name, item in data.items():
        for prefix in prefixes(item):
            for filename in ("config.txt", "cmdline.txt", "start4.elf"):
                result = subprocess.run(
                    ["curl", "--fail", "--silent", "--show-error", "--max-time", "90",
                     "--tftp-blksize", "1468", f"tftp://{BOOT_SERVER}/{prefix}/{filename}"],
                    check=True, capture_output=True,
                )
                if hashlib.sha256(result.stdout).hexdigest() != receipt["files"][filename]:
                    raise ValueError(f"TFTP content mismatch: {name}/{filename}")
        print(f"{name}: routed TFTP firmware and maintenance-only config match local hashes")


def configs():
    private_state()
    directory = STATE / "talos"
    directory.mkdir(mode=0o700, exist_ok=True)
    secrets = directory / "secrets.yaml"
    if not secrets.exists():
        run(["talosctl", "gen", "secrets", "--output-file", secrets, "--talos-version", VERSION])
    secrets.chmod(0o600)
    templates = directory / "templates"
    if templates.exists():
        raise ValueError("Templates already exist; do not silently regenerate cluster identity/config")
    templates.mkdir(mode=0o700)
    patch = "\n---\n".join(json.dumps(doc) for doc in [
        {
            "apiVersion": "v1alpha1", "kind": "ResolverConfig",
            "nameservers": [{"address": "192.168.42.1"}],
        },
        {
            "apiVersion": "v1alpha1", "kind": "KubeNetworkConfig",
            "podSubnets": ["10.142.0.0/16"], "serviceSubnets": ["10.143.0.0/16"],
        },
    ])
    run([
        "talosctl", "gen", "config", "pi-playground", f"https://{ADDRESSES['pi01']}:6443",
        "--with-secrets", secrets, "--output-dir", templates,
        "--install-disk", "/dev/LAB_DISK_NOT_VERIFIED",
        "--install-image", f"factory.talos.dev/metal-installer/{SCHEMATIC}:{VERSION}",
        "--talos-version", VERSION, "--kubernetes-version", KUBERNETES_VERSION,
        "--dns-domain", "lab.cluster.local", "--with-cluster-discovery=false",
        "--config-patch", patch,
    ])
    for path in templates.iterdir():
        path.chmod(0o600)
    for kind in ("controlplane", "worker"):
        run(["talosctl", "validate", "--config", templates / f"{kind}.yaml", "--mode", "metal"])
    run([
        "talosctl", "--talosconfig", templates / "talosconfig", "config", "endpoints",
        ADDRESSES["pi01"], ADDRESSES["pi02"], ADDRESSES["pi03"],
    ])
    print("Standalone lab PKI/templates validated; impossible disk path intentionally blocks installation")


INSPECT = r"""
import json,pathlib,subprocess,socket,time
def command(*args):
    p=subprocess.run(args,capture_output=True,text=True)
    return {"status":p.returncode,"stdout":p.stdout.strip(),"stderr":p.stderr.strip()}
model=pathlib.Path("/proc/device-tree/model").read_text().rstrip("\0")
serial=pathlib.Path("/proc/device-tree/serial-number").read_text().rstrip("\0")
links=json.loads(subprocess.check_output(["ip","-j","link"],text=True))
disks=json.loads(subprocess.check_output(["lsblk","-J","-b","-o",
    "NAME,PATH,TYPE,SIZE,MODEL,SERIAL,TRAN,FSTYPE,PTTYPE,MOUNTPOINTS"],text=True))
for disk in disks["blockdevices"]:
    if disk.get("type")=="disk" and disk.get("tran")=="usb":
        disk["signatures"]=command("sudo","-n","wipefs","--json","--no-act",disk["path"])
print(json.dumps({"time":time.time(),"hostname":socket.gethostname(),"model":model,
    "serial":serial,"links":links,"disks":disks,"memory":pathlib.Path("/proc/meminfo").read_text(),
    "bootloader":command("vcgencmd","bootloader_version"),
    "bootconfig":command("vcgencmd","bootloader_config")}))
"""


def inspect_node(name, user, known_hosts=None):
    data = inventory()
    if not re.fullmatch(r"[a-z_][a-z0-9_-]*", user):
        raise ValueError("An explicitly known SSH username is required")
    trust_options = []
    if known_hosts is not None:
        known_hosts = Path(known_hosts)
        if not known_hosts.is_file() or not known_hosts.stat().st_size:
            raise ValueError("The independently verified private known_hosts file is missing or empty")
        trust_options = [
            "-o", f"UserKnownHostsFile={known_hosts.resolve()}",
            "-o", "HostKeyAlgorithms=ssh-ed25519", "-o", "UpdateHostKeys=no",
        ]
    try:
        result = run([
            "ssh", "-4", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "ForwardAgent=no", "-o", "ForwardX11=no", "-o", "ClearAllForwardings=yes",
            *trust_options, "-o", "ConnectTimeout=5", f"{user}@{name}",
            "python3 -c " + shlex.quote(INSPECT),
        ], capture_output=True)
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.stderr.strip() or "Read-only SSH inspection failed") from None
    report = json.loads(result.stdout)
    if report["hostname"] != name or "Raspberry Pi 4 Model B" not in report["model"]:
        raise ValueError("Connected board hostname/model does not match the authorized Pi")
    if data[name]["mac"] not in [link.get("address", "").lower() for link in report["links"]]:
        raise ValueError("Connected board does not have the recorded wired MAC")
    save_json(STATE / "nodes" / f"{name}.json", report)
    data[name]["serial"] = report["serial"]
    save_json(STATE / "inventory.json", data)
    print(f"{name}: verified board identity and read-only EEPROM/disk report stored privately")


def blank_usb_disk(report, serial):
    if time.time() - report["time"] > 3600 or report["time"] > time.time() + 60:
        raise ValueError("Re-inspect the board; disk evidence must be less than one hour old")
    found = [
        disk for disk in report["disks"]["blockdevices"]
        if disk.get("serial") == serial and serial
    ]
    if len(found) != 1:
        raise ValueError("The exact SSD serial must match one inspected disk")
    disk = found[0]
    if (
        disk.get("type") != "disk" or disk.get("tran") != "usb"
        or not 200_000_000_000 <= int(disk["size"]) <= 300_000_000_000
        or disk.get("children") or disk.get("fstype") or disk.get("pttype")
        or any(disk.get("mountpoints") or [])
    ):
        raise ValueError("SSD is not a blank, unmounted, unpartitioned 240 GB-class USB disk")
    evidence = disk.get("signatures", {})
    if evidence.get("status") != 0:
        raise ValueError("Read-only disk signature inspection was not successful")
    if json.loads(evidence["stdout"]).get("signatures") != []:
        raise ValueError("Disk has existing signatures; preserve it pending explicit data disposition")
    return disk


def configure_node(name, serial):
    data = inventory()
    report = json.loads((STATE / "nodes" / f"{name}.json").read_text())
    if report["hostname"] != name or report["serial"] != data[name].get("serial"):
        raise ValueError("Private board inventory no longer matches the inspection")
    disk = blank_usb_disk(report, serial)
    kind = "worker" if name == "pi04" else "controlplane"
    patches = "\n---\n".join(json.dumps(doc) for doc in [
        {
            "apiVersion": "v1alpha1", "kind": "UnattendedInstallConfig",
            "provisioning": {"diskSelector": {"match": f"disk.serial == {json.dumps(serial)}"}},
        },
        {
            "apiVersion": "v1alpha1", "kind": "HostnameConfig",
            "hostname": name,
        },
        {
            "apiVersion": "v1alpha1", "kind": "LinkAliasConfig", "name": "lab0",
            "selector": {"match": f"mac(link.permanent_addr) == {json.dumps(data[name]['mac'])}"},
        },
        {
            "apiVersion": "v1alpha1", "kind": "DHCPv4Config", "name": "lab0",
            "clientIdentifier": "mac",
        },
    ])
    destination = STATE / "talos" / f"{name}.yaml"
    if destination.exists():
        raise ValueError("Node config already exists; review changes rather than overwriting it")
    run([
        "talosctl", "machineconfig", "patch",
        STATE / "talos" / "templates" / f"{kind}.yaml",
        "--patch", json.dumps({
            "apiVersion": "v1alpha1", "kind": "HostnameConfig", "$patch": "delete",
        }),
        "--patch", patches, "--output", destination,
    ], capture_output=True)
    destination.chmod(0o600)
    run(["talosctl", "validate", "--config", destination, "--mode", "metal"])
    print(f"{name}: validated exact-serial USB SSD config; disk size {disk['size']} bytes")
    print("No config applied, no disk written, and pi04 bootstrap OS left intact")


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("assets", "stage", "verify", "configs"):
        sub.add_parser(name)
    inspect_parser = sub.add_parser("inspect")
    inspect_parser.add_argument("node", choices=ADDRESSES)
    inspect_parser.add_argument("--user", required=True)
    inspect_parser.add_argument("--known-hosts", type=Path)
    configure_parser = sub.add_parser("configure")
    configure_parser.add_argument("node", choices=ADDRESSES)
    configure_parser.add_argument("--disk-serial", required=True)
    args = parser.parse_args()
    if args.command == "inspect":
        inspect_node(args.node, args.user, args.known_hosts)
    elif args.command == "configure":
        configure_node(args.node, args.disk_serial)
    else:
        globals()[args.command]()


if __name__ == "__main__":
    main()
