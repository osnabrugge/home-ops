#!/usr/bin/env python3
"""Fixture/protocol tests. No real Kubernetes, SSH or shutdown command is run."""

import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import socketserver
import stat
import subprocess
import threading
import unittest
from unittest import mock
import uuid


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ups_shutdown", ROOT / "scripts/ups_shutdown.py")
ups = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ups)
EXAMPLE = ROOT / "infrastructure/power/ups-policy.example.json"


def policy():
    return json.loads(EXAMPLE.read_text())


def telemetry(first="OL", second="OL", runtime=900):
    return {name: {"status": status.split(), "runtime": runtime}
            for name, status in zip(ups.UPS_NAMES, (first, second))}


class MemoryJournal:
    def __init__(self, _path=None):
        self.data = {"phase": "idle", "boot": "test"}
        self.mutex = threading.RLock()
        self.saves = 0

    def save(self):
        self.saves += 1

    def close(self):
        pass


def obj(kind, name, namespace="default", **spec):
    return {"apiVersion": "apps/v1" if kind in {"Deployment", "StatefulSet"} else "v1",
            "kind": kind, "metadata": {"name": name, "namespace": namespace}, "spec": spec}


class FakeRunner:
    def __init__(self):
        self.calls = []
        self.flags = ""
        self.fail_talos = None
        self.snapshot_failed = False
        self.pods = []
        self.objects = [
            obj("Deployment", "kustomize-controller", "flux-system", replicas=1),
            obj("Deployment", "helm-controller", "flux-system", replicas=1),
            obj("Deployment", "web", replicas=2),
            obj("StatefulSet", "cache", replicas=3),
            obj("Deployment", "cloudnative-pg", "database", replicas=2),
            obj("CronJob", "already-paused", suspend=True),
            obj("Job", "in-flight", suspend=False),
            obj("Cluster", "postgres16", "database", instances=3),
        ]
        for resource in self.objects:
            if resource["kind"] in {"Deployment", "StatefulSet"}:
                resource["status"] = {"readyReplicas": resource["spec"]["replicas"]}
            elif resource["kind"] == "Cluster":
                resource["status"] = {"readyInstances": resource["spec"]["instances"]}
        self.nodes = [{"apiVersion": "v1", "kind": "Node", "metadata": {"name": name},
                       "status": {"conditions": [{"type": "Ready", "status": "True"}]}}
                      for name in sorted(ups.NODE_NAMES)]

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if kwargs.get("shell"):
            raise AssertionError("a shell must never execute actuator commands")
        result = {}
        if "get" in argv and any("deployments,statefulsets" in arg for arg in argv):
            if self.snapshot_failed:
                raise subprocess.CalledProcessError(1, argv)
            result = {"items": self.nodes + self.objects}
        elif "get" in argv and "nodes" in argv:
            result = {"items": self.nodes}
        elif "get" in argv and "pods" in argv:
            result = {"items": self.pods}
        elif "ceph" in argv:
            if "dump" in argv:
                result = {"flags": self.flags}
            elif "unset" in argv:
                self.flags = self.flags.replace("noout", "")
            elif "set" in argv:
                self.flags += ",noout"
            elif "status" in argv:
                result = {
                    "health": {"status": "HEALTH_WARN" if "noout" in self.flags else "HEALTH_OK"},
                    "osdmap": {"num_osds": 6, "num_up_osds": 6, "num_in_osds": 6},
                    "pgmap": {"num_pgs": 265,
                              "pgs_by_state": [{"state_name": "active+clean", "count": 265}]},
                }
        elif "shutdown" in argv and self.fail_talos in argv:
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
        return subprocess.CompletedProcess(argv, 0, json.dumps(result), "")


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.config, self.state = policy(), {}

    def decide(self, values, now):
        return ups.decision(self.config, self.state, values, now)

    def test_examples_are_bounded_and_infrastructure_excluded(self):
        ups.validate_config(self.config)
        self.config["quiesce_namespaces"].append("rook-ceph")
        with self.assertRaises(ValueError):
            ups.validate_config(self.config)

    def test_online_and_replace_battery_do_not_trigger(self):
        self.assertIsNone(self.decide(telemetry("OL RB", "OL RB"), 0))
        self.assertIsNone(self.decide(telemetry("OL RB", "OL RB"), 10000))

    def test_any_feed_battery_is_enough_after_short_grace(self):
        for pair in (("OB", "OL"), ("OL", "OB"), ("OB", "OB")):
            self.state = {}
            self.assertIsNone(self.decide(telemetry(*pair), 0))
            self.assertIsNone(self.decide(telemetry(*pair), 59))
            self.assertEqual(self.decide(telemetry(*pair), 60), "on-battery-timeout")

    def test_minimum_runtime_across_both_feeds_not_average(self):
        values = telemetry("OB", "OL")
        values["ups02"]["runtime"] = 479
        self.assertEqual(self.decide(values, 0), "runtime-budget")

    def test_critical_status_bypasses_grace_and_missing_runtime(self):
        for status in ("OB LB", "OL FSD", "OFF"):
            values = telemetry(status, "OL")
            values["ups01"]["runtime"] = None
            self.assertEqual(self.decide(values, 0), "ups-critical")

    def test_missing_one_or_both_feeds_is_bounded_even_while_online(self):
        for names in (("ups01",), ups.UPS_NAMES):
            self.state = {}
            values = telemetry()
            for name in names:
                values[name] = {"status": [], "runtime": None}
            self.assertIsNone(self.decide(values, 0))
            self.assertIsNone(self.decide(values, 44))
            self.assertEqual(self.decide(values, 45), "telemetry-timeout")

    def test_synology_rb_only_is_unknown_not_inferred_online(self):
        values = telemetry("RB", "OL")
        self.assertIsNone(self.decide(values, 0))
        self.assertEqual(self.decide(values, 45), "telemetry-timeout")

    def test_short_blip_is_cleared_after_stable_restore(self):
        self.assertIsNone(self.decide(telemetry("OB", "OL"), 0))
        self.assertIsNone(self.decide(telemetry(), 5))
        self.assertIsNone(self.decide(telemetry(), 35))
        self.assertNotIn("battery_since", self.state["timers"])
        self.assertIsNone(self.decide(telemetry("OB", "OL"), 100))
        self.assertIsNone(self.decide(telemetry("OB", "OL"), 159))

    def test_short_false_restore_does_not_reset_outage_timer(self):
        self.decide(telemetry("OB", "OL"), 0)
        self.decide(telemetry(), 40)
        self.assertEqual(self.decide(telemetry("OB", "OL"), 60), "on-battery-timeout")


class ProtocolTests(unittest.TestCase):
    def query(self, status=b'VAR ups01 ups.status "OL RB"\n',
              runtime=b'VAR ups01 battery.runtime "900"\n'):
        commands = []

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                for response in (status, runtime):
                    request = self.rfile.readline()
                    if not request:
                        return
                    commands.append(request)
                    self.wfile.write(response)
                    self.wfile.flush()

        with socketserver.TCPServer(("127.0.0.1", 0), Handler) as server:
            thread = threading.Thread(target=server.serve_forever,
                                      kwargs={"poll_interval": 0.01}, daemon=True)
            thread.start()
            try:
                result = ups.nut_sample("127.0.0.1", server.server_address[1], "ups01")
            finally:
                server.shutdown()
                thread.join(timeout=1)
        self.assertTrue(all(command.startswith(b"GET VAR ups01 ") for command in commands))
        return result

    def test_supported_get_reply_and_seconds(self):
        self.assertEqual(self.query(), {"status": ["OL", "RB"], "runtime": 900.0})

    def test_server_reports_stale_data(self):
        self.assertEqual(self.query(status=b"ERR DATA-STALE\n"),
                         {"status": [], "runtime": None})

    def test_wrong_device_or_contradictory_status_is_rejected(self):
        for status in (b'VAR wrong ups.status "OL"\n', b'VAR ups01 ups.status "OL OB"\n',
                       b'VAR ups01 ups.status "RB"\n'):
            self.assertEqual(self.query(status=status)["status"], [])

    def test_critical_status_survives_runtime_failure(self):
        for runtime in (b"ERR VAR-NOT-SUPPORTED\n", b'VAR ups01 battery.runtime "nan"\n',
                        b'VAR ups01 battery.runtime "-1"\n'):
            self.assertEqual(self.query(status=b'VAR ups01 ups.status "OB LB"\n', runtime=runtime),
                             {"status": ["OB", "LB"], "runtime": None})

    def test_untrusted_text_and_oversize_reply_never_become_commands(self):
        for status in (b'VAR ups01 ups.status "OL;$(not-a-command)"\n', b"x" * 4097 + b"\n"):
            self.assertEqual(self.query(status=status)["status"], [])


class SequenceTests(unittest.TestCase):
    def setUp(self):
        self.config = policy()
        self.config["finalizers"].update(nas02_ssh_target="sean-admin@192.168.42.10",
                                         pve01_ssh_target="sean-admin@192.168.99.40")
        self.journal, self.runner = MemoryJournal(), FakeRunner()
        self.sequence = ups.Sequencer(self.config, self.journal, lambda: None,
                                      run=self.runner, clock=lambda: 0)

    def test_ordered_real_argv_with_fake_actuators(self):
        self.sequence.shutdown()
        self.assertEqual(self.journal.data["phase"], "shutdown-requested")
        commands = [args for args, _ in self.runner.calls]
        talos = [args for args in commands if "shutdown" in args]
        self.assertEqual(len(talos), 6)
        self.assertEqual({args[args.index("--nodes") + 1] for args in talos[:3]}, set(ups.WORKERS))
        self.assertEqual({args[args.index("--nodes") + 1] for args in talos[3:]}, set(ups.CONTROL_PLANES))
        for args in talos:
            self.assertEqual(args[args.index("--nodes") + 1], args[args.index("--endpoints") + 1])
            self.assertIn("--wait", args)
            self.assertIn("--force", args)
        self.assertTrue(self.journal.data["noout_owned"])
        self.assertTrue(self.journal.data["quiesced"])
        self.assertIn("/usr/syno/sbin/synopoweroff", commands[-3][-1])
        self.assertIn("+1", commands[-2][-1])
        self.assertEqual(commands[-1][-2:], ["UPS runtime budget", '{"delay":5}'])
        self.assertLess(commands.index(talos[-1]), len(commands) - 3)

    def test_unconfirmed_worker_is_never_replayed_and_blocks_storage(self):
        self.runner.fail_talos = ups.WORKERS[0]
        self.sequence.shutdown()
        self.assertEqual(self.journal.data["phase"], "incomplete")
        self.assertFalse(any(args[0] == "/usr/bin/ssh" for args, _ in self.runner.calls))
        before = len([args for args, _ in self.runner.calls if "shutdown" in args])
        self.sequence.shutdown()
        after = len([args for args, _ in self.runner.calls if "shutdown" in args])
        self.assertEqual(before, after)
        self.assertEqual(self.journal.data["shutdown_deadline"], 360)

    def test_unreachable_kubernetes_still_uses_direct_talos_not_storage(self):
        self.runner.snapshot_failed = True
        self.sequence.shutdown()
        self.assertEqual(len([args for args, _ in self.runner.calls if "shutdown" in args]), 6)
        self.assertFalse(any(args[0] == "/usr/bin/ssh" for args, _ in self.runner.calls))
        self.assertTrue(self.journal.data["snapshot_unconfirmed"])

    def test_unexpected_member_blocks_storage_finalizers(self):
        self.runner.nodes.append(obj("Node", "unreviewed-node"))
        self.sequence.shutdown()
        self.assertTrue(self.journal.data["snapshot_unconfirmed"])
        self.assertFalse(any(args[0] == "/usr/bin/ssh" for args, _ in self.runner.calls))

    def test_started_power_command_is_ambiguous_never_reissued(self):
        self.journal.data["actions"] = {"talos-" + ups.WORKERS[0]: "started"}
        self.assertFalse(self.sequence.action("talos-" + ups.WORKERS[0], ["never-run"], 50))
        self.assertEqual(self.runner.calls, [])

    def test_idempotent_cleanup_can_be_retried_after_transient_error(self):
        self.journal.data["actions"] = {"recover-noout": "unconfirmed"}
        self.assertTrue(self.sequence.action("recover-noout", ["safe-idempotent-fake"], 50))
        self.assertEqual(len(self.runner.calls), 1)

    def test_exhausted_budget_sends_nothing(self):
        self.assertFalse(self.sequence.action("talos-test", ["never-run"], 0))
        self.assertEqual(self.runner.calls, [])
        self.assertFalse(self.sequence.final_hosts(149))
        self.assertEqual(self.runner.calls, [])

    def test_revoked_approval_sends_nothing(self):
        self.sequence.gate = mock.Mock(side_effect=ValueError("revoked"))
        with self.assertRaises(ValueError):
            self.sequence.action("talos-test", ["never-run"], 100)
        self.assertEqual(self.runner.calls, [])

    def test_recovery_clears_only_owned_noout_and_restores_flux_last(self):
        self.sequence.shutdown()
        clock = [0]
        self.sequence.clock = lambda: clock[0]
        with mock.patch.object(ups, "samples", return_value=telemetry()), \
             mock.patch.object(ups.STOP, "wait", side_effect=lambda n: clock.__setitem__(0, clock[0] + n)):
            self.sequence.recover()
        self.assertEqual(self.journal.data["phase"], "idle")
        self.assertNotIn("noout", self.runner.flags)
        restores = [json.loads(kwargs["input"])["items"][0]
                    for args, kwargs in self.runner.calls
                    if kwargs.get("input") and len(json.loads(kwargs["input"])["items"]) == 1]
        self.assertEqual({x["metadata"]["name"] for x in restores[-2:]},
                         {"kustomize-controller", "helm-controller"})
        self.assertNotIn("cloudnative-pg", [x["metadata"]["name"] for x in self.journal.data.get("snapshot", [])])

    def test_preexisting_noout_is_not_owned(self):
        self.runner.flags = "noout,sortbitwise"
        self.sequence.snapshot()
        self.assertFalse(self.journal.data["noout_owned"])


class PersistenceAndGuardTests(unittest.TestCase):
    def setUp(self):
        self.directory = ROOT / "infrastructure/power" / (".ups-test-state-" + uuid.uuid4().hex)
        self.directory.mkdir(mode=0o700)

    def tearDown(self):
        shutil.rmtree(self.directory)

    def test_durable_journal_lock_mode_and_host_reboot_latch(self):
        path = self.directory / "state.json"
        journal = ups.Journal(path, boot="first")
        journal.data.update(phase="shutdown", actions={"talos-node": "started"},
                            timers={"battery_since": 10})
        journal.save()
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        with self.assertRaises(BlockingIOError):
            ups.Journal(path, boot="first")
        journal.close()
        journal = ups.Journal(path, boot="first")
        self.assertEqual(journal.data["actions"]["talos-node"], "started")
        journal.close()
        journal = ups.Journal(path, boot="second")
        self.assertEqual(journal.data["phase"], "incomplete")
        self.assertEqual(journal.data["timers"], {})
        journal.close()

    def test_empty_or_mismatched_approval_never_arms(self):
        approval = self.directory / "approval"
        approval.write_text("wrong")
        approval.chmod(0o600)
        info = type("Info", (), {"st_uid": 0, "st_mode": stat.S_IFREG | 0o600})()
        with mock.patch.object(ups.os, "geteuid", return_value=0), \
             mock.patch.object(ups.Path, "stat", return_value=info):
            with self.assertRaisesRegex(ValueError, "exact policy"):
                ups.check_approval(policy(), EXAMPLE.read_bytes(), approval)

    def test_native_unbounded_shutdown_is_a_hard_arm_gate(self):
        config = policy()
        config["finalizers"].update(nas02_ssh_target="sean-admin@192.168.42.10",
                                    pve01_ssh_target="sean-admin@192.168.99.40")
        raw = json.dumps(config).encode()
        approval = self.directory / "approval"
        approval.write_text(hashlib.sha256(raw).hexdigest())
        approval.chmod(0o600)
        info = type("Info", (), {"st_uid": 0, "st_mode": stat.S_IFREG | 0o600})()
        with mock.patch.object(ups.os, "geteuid", return_value=0), \
             mock.patch.object(ups.Path, "stat", return_value=info):
            with self.assertRaisesRegex(ValueError, "bounds"):
                ups.check_approval(config, raw, approval)

    def test_default_once_mode_never_calls_an_actuator(self):
        with mock.patch.object(ups, "Journal", MemoryJournal), \
             mock.patch.object(ups, "samples", return_value=telemetry("OB LB", "OB LB")), \
             mock.patch.object(ups.Sequencer, "shutdown") as shutdown, \
             contextlib.redirect_stdout(io.StringIO()):
            ups.main(["watch", "--config", str(EXAMPLE), "--state", "unused", "--once"])
        shutdown.assert_not_called()

    def test_execute_without_approval_is_rejected_before_observing(self):
        with mock.patch.object(ups, "samples") as read, \
             contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            ups.main(["watch", "--config", str(EXAMPLE), "--state", "unused", "--once", "--execute"])
        read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
