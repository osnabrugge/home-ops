#!/usr/bin/env python3
"""Off-cluster NUT observer and explicitly armed, bounded outage sequencer."""

import argparse
import concurrent.futures
import fcntl
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import shlex
import socket
import stat
import subprocess
import threading
import time


UPS_NAMES = ("ups01", "ups02")
WORKERS = ("192.168.42.54", "192.168.42.55", "192.168.42.56")
CONTROL_PLANES = ("192.168.42.51", "192.168.42.52", "192.168.42.53")
NODE_NAMES = {f"k8s{i:02}" for i in range(1, 7)}
STOP = threading.Event()


def nut_sample(host, port, name):
    """Only GET VAR is implemented; NUT rejects stale driver data itself."""
    status = []
    try:
        values = {}
        with socket.create_connection((host, port), timeout=2) as connection:
            connection.settimeout(2)
            with connection.makefile("rb") as stream:
                for variable in ("ups.status", "battery.runtime"):
                    connection.sendall(f"GET VAR {name} {variable}\n".encode("ascii"))
                    line = stream.readline(4097)
                    if len(line) > 4096 or not line.endswith(b"\n"):
                        raise ValueError("invalid NUT reply")
                    fields = shlex.split(line.decode("ascii"))
                    if len(fields) != 4 or fields[:3] != ["VAR", name, variable]:
                        raise ValueError("unavailable NUT variable")
                    values[variable] = fields[3]
                    if variable == "ups.status":
                        candidate = values[variable].split()
                        if not candidate or not all(re.fullmatch(r"[A-Z]+", x) for x in candidate):
                            raise ValueError("invalid NUT status")
                        if {"OL", "OB"} <= set(candidate):
                            raise ValueError("contradictory NUT status")
                        if not set(candidate) & {"OL", "OB", "OFF", "FSD"}:
                            raise ValueError("unknown NUT power state")
                        status = candidate
        runtime = float(values["battery.runtime"])
        if not math.isfinite(runtime) or not 0 <= runtime <= 604800:
            raise ValueError("invalid NUT runtime")
        return {"status": status, "runtime": runtime}
    except (OSError, ValueError, UnicodeError):
        return {"status": status, "runtime": None}


def samples(config):
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = {name: pool.submit(nut_sample, config["nut_host"], config["nut_port"], name)
                   for name in UPS_NAMES}
        return {name: future.result() for name, future in futures.items()}


def decision(config, state, telemetry, now):
    """Conservative ANY-feed policy; recovery requires both feeds fresh/online."""
    timers = state.setdefault("timers", {})
    missing = timers.setdefault("missing", {})
    online = True
    battery = False
    runtimes = []
    for name in UPS_NAMES:
        sample = telemetry.get(name, {})
        status = set(sample.get("status", []))
        runtime = sample.get("runtime")
        valid = bool(status & {"OL", "OB", "OFF", "FSD"}) and runtime is not None
        online &= valid and "OL" in status and not status & {"OB", "OFF", "FSD"}
        battery |= "OB" in status
        if "FSD" in status or "OFF" in status or {"OB", "LB"} <= status:
            return "ups-critical"
        if valid:
            missing.pop(name, None)
            runtimes.append(runtime)
        else:
            missing.setdefault(name, now)
    if online:
        timers.setdefault("online_since", now)
        if now - timers["online_since"] >= config["restore_seconds"]:
            timers.pop("battery_since", None)
    else:
        timers.pop("online_since", None)
    if battery:
        timers.setdefault("battery_since", now)
        if runtimes and min(runtimes) <= (
                config["shutdown_budget_seconds"] + config["reserve_seconds"]):
            return "runtime-budget"
    if any(now - started >= config["communications_seconds"] for started in missing.values()):
        return "telemetry-timeout"
    if not online and "battery_since" in timers:
        if now - timers["battery_since"] >= config["on_battery_seconds"]:
            return "on-battery-timeout"
    return None


def validate_config(config):
    if not ipaddress.ip_address(config["nut_host"]).is_loopback:
        raise ValueError("NUT must use the off-cluster host's loopback listener")
    bounds = {
        "nut_port": (1024, 65535), "poll_seconds": (1, 5),
        "on_battery_seconds": (5, 60), "communications_seconds": (15, 60),
        "restore_seconds": (10, 60), "shutdown_budget_seconds": (240, 360),
        "reserve_seconds": (120, 300), "quiesce_seconds": (30, 90),
        "worker_seconds": (30, 90), "control_plane_seconds": (30, 75),
    }
    for key, (low, high) in bounds.items():
        value = config[key]
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f"{key} must be an integer in {low}..{high}")
    if sum(config[key] for key in ("quiesce_seconds", "worker_seconds",
                                   "control_plane_seconds")) + 180 > config["shutdown_budget_seconds"]:
        raise ValueError("stage limits must leave 30s for inventory/noout and 150s for final hosts")
    forbidden = {"rook-ceph", "flux-system", "kube-system", "network"}
    if forbidden & set(config["quiesce_namespaces"]):
        raise ValueError("storage, API and network infrastructure must remain up")
    if not all(re.fullmatch(r"[a-z0-9][a-z0-9-]*", ns) for ns in config["quiesce_namespaces"]):
        raise ValueError("invalid quiesce namespace")


class Journal:
    def __init__(self, path, boot=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = self.path.with_suffix(".lock").open("a")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock.close()
            raise
        self.mutex = threading.RLock()
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {"phase": "idle"}
        boot = boot or Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        if self.data.get("boot") != boot:
            self.data["timers"] = {}
            self.data["boot"] = boot
            if self.data["phase"] == "shutdown":
                self.data["phase"] = "incomplete"
                self.data["recovery_required"] = "sequencer-host-rebooted"
        self.save()

    def save(self):
        with self.mutex:
            pending = self.path.with_suffix(".next")
            descriptor = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "w") as stream:
                json.dump(self.data, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(pending, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)

    def close(self):
        self.lock.close()


def check_approval(config, raw_config, arm_path):
    if os.geteuid() != 0:
        raise ValueError("actuation requires the reviewed root-run host service")
    info = Path(arm_path).stat()
    if info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError("approval must be a root-owned mode-0600 file")
    if Path(arm_path).read_text().strip() != hashlib.sha256(raw_config).hexdigest():
        raise ValueError("approval does not match the exact policy file")
    finalizers = config["finalizers"]
    for key, ip in (("nas02_ssh_target", "192.168.42.10"),
                    ("pve01_ssh_target", "192.168.99.41"),
                    ("pve02_ssh_target", "192.168.99.42")):
        if not re.fullmatch(r"[a-z_][a-z0-9_-]*@" + re.escape(ip),
                            finalizers.get(key) or ""):
            raise ValueError(f"{key} must be an existing reviewed identity at {ip}")
    if finalizers.get("nas02_shutdown_api") != "synology":
        raise ValueError("NAS02 must use its verified Synology native shutdown mechanism")
    if finalizers.get("native_shutdown_bounds_reviewed") is not True:
        raise ValueError("native NAS/PVE shutdown bounds still require scoped host approval")
    for key in ("kubeconfig", "talosconfig", "kubectl", "talosctl"):
        if "APPROVED" in config[key] or not Path(config[key]).is_file():
            raise ValueError(f"{key} is not provisioned")


def resource_list(resources):
    return json.dumps({"apiVersion": "v1", "kind": "List", "items": resources})


def reference(resource):
    return {key: resource[key] for key in ("apiVersion", "kind", "metadata")}


class Sequencer:
    def __init__(self, config, journal, gate, run=subprocess.run, clock=time.monotonic):
        self.config, self.journal, self.gate = config, journal, gate
        self.run, self.clock = run, clock

    def kube(self, *args):
        return [self.config["kubectl"], "--kubeconfig", self.config["kubeconfig"],
                "--request-timeout=8s", *args]

    def ceph(self, *args):
        return self.kube("-n", "rook-ceph", "exec", "deploy/rook-ceph-tools",
                         "--", "ceph", *args)

    def read(self, argv, timeout=10, deadline=None):
        if deadline is not None:
            timeout = min(timeout, deadline - self.clock())
            if timeout <= 0:
                raise subprocess.TimeoutExpired(argv, 0)
        result = self.run(argv, capture_output=True, text=True, timeout=timeout, check=True)
        return json.loads(result.stdout)

    def action(self, name, argv, deadline, payload=None):
        with self.journal.mutex:
            actions = self.journal.data.setdefault("actions", {})
            if name in actions:
                if actions[name] == "done":
                    return True
                if name.startswith(("talos-", "nas01-", "nas02-", "pve01-")):
                    return False
            self.gate()
            remaining = deadline - self.clock()
            if remaining <= 0:
                actions[name] = "budget-exhausted"
                self.journal.save()
                return False
            # Persist BEFORE sending: a timeout/restart must never replay a shutdown.
            actions[name] = "started"
            self.journal.save()
        try:
            result = self.run(argv, input=payload, capture_output=True, text=True,
                              timeout=remaining, check=False)
            outcome = "done" if result.returncode == 0 else "failed"
        except (OSError, subprocess.SubprocessError):
            outcome = "unconfirmed"
        with self.journal.mutex:
            actions[name] = outcome
            self.journal.save()
        return outcome == "done"

    def snapshot(self):
        objects = self.read(self.kube("get",
            "nodes,deployments,statefulsets,cronjobs,jobs,clusters.postgresql.cnpg.io",
            "-A", "-o", "json"))["items"]
        if {obj["metadata"]["name"] for obj in objects if obj["kind"] == "Node"} != NODE_NAMES:
            raise ValueError("node membership differs from the six reviewed Talos targets")
        selected = []
        for obj in objects:
            if obj["kind"] == "Node":
                continue
            ns, name, kind = obj["metadata"]["namespace"], obj["metadata"]["name"], obj["kind"]
            flux = ns == "flux-system" and name in {"kustomize-controller", "helm-controller"}
            if not flux and ns not in self.config["quiesce_namespaces"]:
                continue
            if ns == "database" and name == "cloudnative-pg":
                continue
            entry = {"apiVersion": obj["apiVersion"], "kind": kind,
                     "metadata": {"name": name, "namespace": ns}}
            if kind in {"Deployment", "StatefulSet"}:
                entry["replicas"] = obj["spec"].get("replicas", 1)
            elif kind in {"Job", "CronJob"}:
                entry["suspend"] = obj["spec"].get("suspend")
            elif kind == "Cluster":
                entry["hibernation"] = obj["metadata"].get("annotations", {}).get("cnpg.io/hibernation")
            else:
                continue
            selected.append(entry)
        flags = self.read(self.ceph("osd", "dump", "-f", "json"))["flags"]
        self.journal.data.update(snapshot=selected, noout_owned="noout" not in flags.split(","))
        self.journal.save()

    def wait_quiet(self, deadline, databases=False):
        snapshot = self.journal.data["snapshot"]
        namespaces = set(self.config["quiesce_namespaces"])
        clusters = {(x["metadata"]["namespace"], x["metadata"]["name"])
                    for x in snapshot if x["kind"] == "Cluster"}
        while self.clock() < deadline:
            pods = self.read(self.kube("get", "pods", "-A", "-o", "json"), deadline=deadline)["items"]
            pending = []
            for pod in pods:
                meta = pod["metadata"]
                if meta["namespace"] not in namespaces or pod["status"].get("phase") in {"Succeeded", "Failed"}:
                    continue
                if any(x["kind"] == "DaemonSet" for x in meta.get("ownerReferences", [])):
                    continue
                if meta["namespace"] == "database" and meta["name"].startswith("cloudnative-pg-"):
                    continue
                is_database = (meta["namespace"], meta.get("labels", {}).get("cnpg.io/cluster")) in clusters
                if databases or not is_database:
                    pending.append(meta["name"])
            if not pending:
                return True
            STOP.wait(min(1, max(0, deadline - self.clock())))
        return False

    def quiesce(self, deadline):
        snapshot = self.journal.data["snapshot"]
        flux = [reference(x) for x in snapshot if x["metadata"]["namespace"] == "flux-system"]
        if not self.action("pause-flux", self.kube("scale", "-f", "-", "--replicas=0"),
                           deadline, resource_list(flux)):
            return False
        batch = [reference(x) for x in snapshot if x["kind"] in {"Job", "CronJob"}]
        if batch and not self.action("pause-jobs", self.kube("patch", "-f", "-", "--type=merge",
                "-p", '{"spec":{"suspend":true}}'), deadline, resource_list(batch)):
            return False
        workloads = [x for x in snapshot if x["kind"] in {"Deployment", "StatefulSet"}
                     and x["metadata"]["namespace"] != "flux-system"]
        workloads.sort(key=lambda x: (x["kind"] != "Deployment",
                                      "operator" not in x["metadata"]["name"]))
        if workloads and not self.action("quiesce-apps",
                self.kube("scale", "-f", "-", "--replicas=0"), deadline,
                resource_list([reference(x) for x in workloads])):
            return False
        if not self.wait_quiet(deadline):
            return False
        clusters = [reference(x) for x in snapshot if x["kind"] == "Cluster"]
        if clusters and not self.action("hibernate-cnpg", self.kube("annotate", "-f", "-",
                "--overwrite", "cnpg.io/hibernation=on"), deadline, resource_list(clusters)):
            return False
        return self.wait_quiet(deadline, databases=True)

    def talos_stage(self, nodes, deadline):
        def shutdown(ip):
            return self.action("talos-" + ip,
                [self.config["talosctl"], "--talosconfig", self.config["talosconfig"],
                 "--endpoints", ip, "--nodes", ip, "shutdown", "--force", "--wait",
                 "--timeout", f"{max(1, int(deadline - self.clock()))}s"], deadline)
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            return all(list(pool.map(shutdown, nodes)))

    def ssh(self, target, command):
        return ["/usr/bin/ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                "-o", "ConnectTimeout=5", target, shlex.join(command)]

    def final_hosts(self, deadline):
        if deadline - self.clock() < 150:
            self.journal.data["finalizers_blocked"] = "insufficient-native-shutdown-budget"
            self.journal.save()
            return False
        finalizers = self.config["finalizers"]
        if not self.action("nas02-shutdown-request",
                self.ssh(finalizers["nas02_ssh_target"],
                         ["sudo", "-n", "/usr/syno/sbin/synopoweroff"]), deadline):
            return False
        # pve01 hosts routing: schedule it last, allowing NAS01's local shutdown.
        if not self.action("pve01-scheduled-shutdown",
                self.ssh(finalizers["pve01_ssh_target"],
                         ["sudo", "-n", "/usr/sbin/shutdown", "-h", "+1", "UPS runtime budget"]),
                deadline):
            return False
        return self.action("nas01-shutdown-request",
            [finalizers["nas01_midclt"], "call", "system.shutdown",
             "UPS runtime budget", '{"delay":5}'], deadline)

    def shutdown(self):
        self.gate()
        deadline = self.journal.data.setdefault(
            "shutdown_deadline", self.clock() + self.config["shutdown_budget_seconds"])
        self.journal.data["phase"] = "shutdown"
        self.journal.save()
        try:
            noout, quiet = False, False
            if "snapshot" not in self.journal.data:
                try:
                    self.snapshot()
                except (OSError, ValueError, KeyError, subprocess.SubprocessError):
                    self.journal.data["snapshot_unconfirmed"] = True
                    self.journal.save()
            if "snapshot" in self.journal.data:
                noout = self.action("ceph-noout", self.ceph("osd", "set", "noout"),
                                    min(deadline, self.clock() + 10))
                try:
                    quiet = self.quiesce(min(deadline, self.clock() + self.config["quiesce_seconds"]))
                except (OSError, KeyError, subprocess.SubprocessError, json.JSONDecodeError):
                    quiet = False
            # A broken Kubernetes API must not prevent direct, graceful Talos OS
            # shutdown. Storage finalizers remain prohibited if quiesce is unknown.
            workers = self.talos_stage(WORKERS, min(deadline, self.clock() + self.config["worker_seconds"]))
            control_planes = self.talos_stage(CONTROL_PLANES,
                min(deadline, self.clock() + self.config["control_plane_seconds"]))
            hosts = False
            if noout and quiet and workers and control_planes:
                hosts = self.final_hosts(deadline)
            self.journal.data["phase"] = "shutdown-requested" if hosts else "incomplete"
            self.journal.data["quiesced"] = quiet
        except (OSError, ValueError, KeyError, subprocess.SubprocessError):
            self.journal.data["phase"] = "incomplete"
        self.journal.save()

    def recover(self):
        self.gate()
        if self.journal.data.get("phase") not in {"shutdown", "shutdown-requested", "incomplete"}:
            raise ValueError("no outage journal to recover")
        deadline = self.clock() + self.config["shutdown_budget_seconds"]
        start = self.clock()
        while self.clock() - start < self.config["restore_seconds"]:
            telemetry = samples(self.config)
            if not all("OL" in s["status"] and not set(s["status"]) & {"OB", "OFF", "FSD"}
                       and s["runtime"] is not None for s in telemetry.values()):
                raise ValueError("both UPS feeds must remain fresh and online before recovery")
            STOP.wait(1)
        nodes = self.read(self.kube("get", "nodes", "-o", "json"))["items"]
        ready = {node["metadata"]["name"] for node in nodes
                 if any(c["type"] == "Ready" and c["status"] == "True"
                        for c in node["status"].get("conditions", []))}
        if ready != NODE_NAMES or {node["metadata"]["name"] for node in nodes} != NODE_NAMES:
            raise ValueError("all six Talos nodes must be Ready before recovery")
        health = self.read(self.ceph("status", "-f", "json"))
        osds, pgs = health["osdmap"], health["pgmap"]
        if not (osds["num_osds"] == osds["num_up_osds"] == osds["num_in_osds"] > 0
                and pgs["num_pgs"] > 0 and all(
                    {"active", "clean"} <= set(pg["state_name"].split("+"))
                    for pg in pgs["pgs_by_state"])):
            raise ValueError("Ceph must have all OSDs up/in and every PG active+clean")
        if self.journal.data.get("noout_owned"):
            if not self.action("recover-noout", self.ceph("osd", "unset", "noout"), deadline):
                raise ValueError("noout cleanup was not confirmed; inspect before retrying")
        if self.read(self.ceph("status", "-f", "json"))["health"]["status"] != "HEALTH_OK":
            raise ValueError("Ceph must be HEALTH_OK before restoring data workloads")
        snapshot = self.journal.data.get("snapshot", [])
        def priority(obj):
            if obj["metadata"]["namespace"] == "flux-system":
                return 4
            if obj["kind"] == "Cluster" or obj["metadata"]["namespace"] == "database":
                return 0
            return 2 if obj["kind"] in {"Job", "CronJob"} else 1
        ordered = sorted(snapshot, key=priority)
        databases_checked = False
        for index, obj in enumerate(ordered):
            if priority(obj) > 0 and not databases_checked:
                self.wait_databases(snapshot, deadline)
                databases_checked = True
            ref, kind = reference(obj), obj["kind"]
            if kind in {"Deployment", "StatefulSet"}:
                args = ("scale", "-f", "-", f"--replicas={obj['replicas']}")
            elif kind == "Cluster":
                value = obj["hibernation"]
                annotation = "cnpg.io/hibernation-" if value is None else "cnpg.io/hibernation=" + value
                args = ("annotate", "-f", "-", "--overwrite", annotation)
            else:
                args = ("patch", "-f", "-", "--type=merge",
                        "-p", json.dumps({"spec": {"suspend": obj["suspend"]}}))
            if not self.action(f"restore-{index}", self.kube(*args), deadline, resource_list([ref])):
                raise ValueError("restoration incomplete; journal retained for inspection")
        previous = {"actions": self.journal.data.get("actions", {}), "phase": "recovered"}
        self.journal.data = {"phase": "idle", "boot": self.journal.data["boot"], "previous": previous}
        self.journal.save()

    def wait_databases(self, snapshot, deadline):
        expected = [x for x in snapshot if
                    (x["kind"] == "Cluster" and x["hibernation"] != "on")
                    or (x["metadata"]["namespace"] == "database"
                        and x["kind"] in {"Deployment", "StatefulSet"} and x["replicas"] > 0)]
        while self.clock() < deadline:
            current = self.read(self.kube("get",
                "deployments,statefulsets,clusters.postgresql.cnpg.io", "-A", "-o", "json"),
                deadline=deadline)["items"]
            lookup = {(x["kind"], x["metadata"].get("namespace"), x["metadata"]["name"]): x
                      for x in current}
            ready = True
            for obj in expected:
                live = lookup.get((obj["kind"], obj["metadata"]["namespace"], obj["metadata"]["name"]), {})
                if obj["kind"] == "Cluster":
                    wanted = live.get("spec", {}).get("instances", 0)
                    ready &= wanted > 0 and live.get("status", {}).get("readyInstances", 0) >= wanted
                else:
                    ready &= live.get("status", {}).get("readyReplicas", 0) >= obj["replicas"]
            if ready:
                return
            STOP.wait(min(1, max(0, deadline - self.clock())))
        raise ValueError("databases not ready; applications and Flux remain paused")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("watch", "recover"))
    parser.add_argument("--config", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--once", action="store_true", help="one read-only observation unless explicitly armed")
    parser.add_argument("--execute", action="store_true", help="requires separate reviewed root-owned approval")
    parser.add_argument("--approval", help="mode-0600 root-owned file containing the policy SHA256")
    args = parser.parse_args(argv)
    raw_config = Path(args.config).read_bytes()
    config = json.loads(raw_config)
    validate_config(config)
    if args.command == "recover" and not args.execute:
        parser.error("recovery changes infrastructure and requires --execute plus approval")
    if args.execute and not args.approval:
        parser.error("--execute requires --approval")

    def gate():
        check_approval(config, raw_config, args.approval)

    if args.execute:
        gate()
    journal = Journal(args.state)
    sequencer = Sequencer(config, journal, gate)
    try:
        if args.command == "recover":
            sequencer.recover()
            return
        while True:
            telemetry = samples(config)
            reason = decision(config, journal.data, telemetry, time.monotonic())
            journal.save()
            print(json.dumps({"telemetry": telemetry, "decision": reason,
                              "phase": journal.data["phase"], "execute": args.execute}), flush=True)
            if args.execute and journal.data["phase"] == "idle" and reason:
                sequencer.shutdown()
            elif args.execute and journal.data["phase"] == "shutdown":
                sequencer.shutdown()
            if args.once:
                return
            STOP.wait(config["poll_seconds"])
    finally:
        journal.close()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        # Never echo subprocess output or configuration/credential contents.
        print(json.dumps({"error": type(error).__name__, "status": "not-confirmed"}), flush=True)
        raise SystemExit(1) from None
