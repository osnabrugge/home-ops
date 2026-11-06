import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import uuid

import nas01_migration as migration


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.work = Path.cwd() / (".nas01-migration-test-" + uuid.uuid4().hex)
        self.work.mkdir(mode=0o700)
        self.addCleanup(shutil.rmtree, self.work)
        self.source = self.work / "source"
        self.source.mkdir()
        (self.source / "downloads").mkdir()
        (self.source / "media").mkdir()
        (self.source / "empty").mkdir()
        (self.source / "downloads" / "payload").write_bytes(b"synthetic data" * 1000)
        os.link(self.source / "downloads" / "payload", self.source / "media" / "linked")
        (self.source / "media" / "independent").write_bytes(b"other" * 1000)
        (self.source / "media" / "line\nbreak").write_bytes(b"newline safe")
        (self.source / "media" / "shortcut").symlink_to("independent")

    def test_default_is_capacity_without_processes(self):
        with patch.object(migration.subprocess, "run") as process:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(migration.main([]), 0)
        process.assert_not_called()
        self.assertIn("READ_ONLY_ESTIMATE", output.getvalue())

    def test_capacity_counts_stranded_space_not_just_parity(self):
        layouts = migration.capacity()["layouts"]
        donor = layouts["donor_8wide_raidz2"]
        self.assertEqual(donor["raw_tb"] - donor["parity_tb"] - donor["stranded_tb"], 72)
        self.assertEqual(layouts["final_donor8_plus_4x8_raidz2"]["nominal_usable_tb"], 88)

    def test_capacity_uses_eleven_detected_loaners_and_distinct_expansion_cases(self):
        result = migration.capacity()
        layouts = result["layouts"]
        self.assertEqual(result["detected_loaner_disks"], 11)
        expected = {
            "loaner_11x4_raidz1": 40,
            "loaner_11x4_raidz2": 36,
            "smb_17wide_raidz1_expanded": 64,
            "smb_17wide_raidz2_recreated": 60,
            "donor_two_4wide_raidz1": 96,
        }
        for name, usable_tb in expected.items():
            with self.subTest(layout=name):
                self.assertEqual(layouts[name]["nominal_usable_tb"], usable_tb)
                self.assertAlmostEqual(layouts[name]["nominal_usable_tib"], usable_tb * 10**12 / 2**40)
                self.assertAlmostEqual(layouts[name]["nominal_80_percent_tb"], usable_tb * 0.8)
        self.assertEqual(layouts["loaner_11x4_raidz2"]["nominal_80_percent_tb"], 28.8)
        self.assertLess(
            layouts["loaner_11x4_raidz1"]["nominal_80_percent_tb"] * 10**12,
            result["source_bytes"]["data"],
        )

    def test_budget_reserves_headroom_and_production_growth(self):
        result = migration.additional_budget(100, 900, 50)
        self.assertEqual(result["additional_budget_bytes"], 650)
        self.assertEqual(migration.additional_budget(900, 100)["additional_budget_bytes"], 0)
        with self.assertRaises(ValueError):
            migration.additional_budget(100, 900, headroom_percent=5)

    def test_shards_keep_groups_closed_and_cover_each_file_once(self):
        budgets = {"loaner": 30000, "smb": 22000, "flash": 22000}
        summary, lists = migration.shard_plan(str(self.source), budgets)
        self.assertEqual(summary["hardlink_groups"], 1)
        shard = next(paths for paths in lists.values() if "downloads/payload" in paths)
        self.assertIn("media/linked", shard)
        all_files = [path for paths in lists.values() for path in paths
                     if path not in ("downloads", "media", "empty")]
        self.assertEqual(len(all_files), len(set(all_files)))
        self.assertEqual(len(all_files), 5)
        self.assertEqual(migration.shard_plan(str(self.source), budgets), (summary, lists))
        for paths in lists.values():
            self.assertIn("empty", paths)
        self.assertTrue(all(item["remaining_bytes"] >= 0 for item in summary["shards"].values()))

    def test_insufficient_budget_refuses_instead_of_splitting_hardlinks(self):
        with self.assertRaisesRegex(ValueError, "do not fit"):
            migration.shard_plan(str(self.source), {"one": 25000})

    def test_external_hardlink_refuses(self):
        os.link(self.source / "media" / "independent", self.work / "outside")
        with self.assertRaisesRegex(ValueError, "hardlinks leave"):
            migration.scan([str(self.source)])

    def test_special_files_refuse(self):
        os.mkfifo(self.source / "socket-like-fifo")
        with self.assertRaisesRegex(ValueError, "special file"):
            migration.scan([str(self.source)])

    def test_snapshot_containers_are_not_silently_counted_as_payload(self):
        (self.source / "#snapshot").mkdir()
        with self.assertRaisesRegex(ValueError, "snapshot container"):
            migration.scan([str(self.source)])

    def test_root_symlink_refuses(self):
        link = self.work / "source-link"
        link.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, "non-symlink"):
            migration.scan([str(link)])

    def test_child_filesystem_boundary_refuses(self):
        real_scan = migration.os.scandir

        class FakeChild:
            name = "foreign"
            path = str(self.source / "foreign")

            def stat(child, follow_symlinks=False):
                values = list(self.source.stat())
                values[2] += 1
                return os.stat_result(values)

        class FakeIterator:
            def __enter__(self):
                return [FakeChild()]

            def __exit__(self, *args):
                return False

        with patch.object(migration.os, "scandir", return_value=FakeIterator()):
            with self.assertRaisesRegex(ValueError, "filesystem boundary"):
                migration.scan([str(self.source)])
        self.assertIs(migration.os.scandir, real_scan)

    def test_fingerprint_detects_content_change_even_when_metadata_is_restored(self):
        before = migration.fingerprint([str(self.source)], True)
        file = self.source / "media" / "independent"
        previous = file.stat()
        file.write_bytes(b"OTHER" * 1000)
        os.utime(file, ns=(previous.st_atime_ns, previous.st_mtime_ns))
        after = migration.fingerprint([str(self.source)], True)
        self.assertEqual(before["metadata_sha256"], after["metadata_sha256"])
        self.assertNotEqual(before["content_sha256"], after["content_sha256"])

    def test_unlinked_copy_has_different_topology_even_with_identical_data(self):
        before = migration.fingerprint([str(self.source)], True)
        link = self.source / "media" / "linked"
        content = link.read_bytes()
        link.unlink()
        link.write_bytes(content)
        after = migration.fingerprint([str(self.source)], True)
        self.assertEqual(before["content_sha256"], after["content_sha256"])
        self.assertNotEqual(before["hardlinks_sha256"], after["hardlinks_sha256"])
        self.assertGreater(after["unique_file_bytes"], before["unique_file_bytes"])

    def test_combined_staging_fingerprint_matches_source(self):
        first, second = self.work / "first", self.work / "second"
        first.mkdir()
        second.mkdir()
        roots = [first, second]
        entries, groups, _ = migration.scan([str(self.source)])
        for root in roots:
            for relative, item in entries.items():
                if item["kind"] == "directory":
                    (root / relative).mkdir(parents=True, exist_ok=True)
        for index, group in enumerate(groups):
            root = roots[index % 2]
            representative = root / group[0]["path"]
            shutil.copy2(group[0]["absolute"], representative)
            for member in group[1:]:
                os.link(representative, root / member["path"])
        for item in entries.values():
            if item["kind"] == "symlink":
                destination = first / item["path"]
                destination.symlink_to(item["link"])
                os.utime(destination, ns=(item["stat"].st_atime_ns, item["stat"].st_mtime_ns),
                         follow_symlinks=False)
        for root in roots:
            for relative, item in entries.items():
                if item["kind"] == "directory":
                    shutil.copystat(item["absolute"], root / relative)
        expected = migration.fingerprint([str(self.source)], True)
        actual = migration.fingerprint([str(root) for root in roots], True)
        for field in ("metadata_sha256", "hardlinks_sha256", "content_sha256", "unique_file_bytes"):
            self.assertEqual(expected[field], actual[field], field)

    def test_overlapping_regular_paths_refuse(self):
        with self.assertRaisesRegex(ValueError, "overlapping"):
            migration.scan([str(self.source), str(self.source)])

    def test_checksum_rejects_source_drift(self):
        entries, _, _ = migration.scan([str(self.source)])
        item = entries["media/independent"]
        Path(item["absolute"]).write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "source changed"):
            migration.content_hash(item)

    def test_rsync_is_only_a_dry_run_plan_with_no_recursive_shard_leak(self):
        with patch.object(migration.subprocess, "run") as process:
            result = migration.rsync_plan("reader@nas02.in.homeops.ca:/volume1/data",
                                          "/mnt/smb/nas02-stage-data", True, True)
        process.assert_not_called()
        arguments = result["argv"]
        self.assertIn("--dry-run", arguments)
        self.assertIn("--no-recursive", arguments)
        self.assertIn("--from0", arguments)
        self.assertIn("--files-from=-", arguments)
        self.assertIn("--checksum", arguments)
        self.assertFalse(any(flag.startswith(("--delete", "--remove", "--inplace")) for flag in arguments))

    def test_production_and_traversal_destinations_refuse(self):
        for destination in ("/", "/mnt/backups/stage", "/mnt/local/stage", "/mnt/smb/home",
                            "/mnt/smb/home/anything", "/mnt/smb/../local/stage",
                            "host:/mnt/stage/data", "/mnt/smb", "/mnt/nfs/netboot",
                            "/mnt/nfs/media", "/mnt/loan/data/nested"):
            with self.subTest(destination=destination):
                with self.assertRaises(ValueError):
                    migration.rsync_plan("/mnt/loan/data", destination)

    def test_reviewed_snapshot_source_is_supported(self):
        result = migration.rsync_plan("reader@nas02:/volume1/data/.snapshot/GMT-2026.11.02",
                                      "/mnt/loan/nas02-stage-data", True)
        self.assertIn("--dry-run", result["argv"])
        for suffix in ("..", ".", "../outside", "snapshot/../../outside"):
            with self.assertRaises(ValueError):
                migration.rsync_plan("reader@nas02:/volume1/data/.snapshot/" + suffix,
                                      "/mnt/loan/nas02-stage-data")

    def test_existing_source_sudo_is_an_explicit_render_only_option(self):
        result = migration.rsync_plan("operator@nas02:/volume1/data", "/mnt/loan/data",
                                      source_sudo=True)
        self.assertIn("--rsync-path=sudo -n /usr/bin/rsync", result["argv"])
        self.assertIn("--dry-run", result["argv"])
        with self.assertRaises(ValueError):
            migration.rsync_plan("/mnt/loan/data", "/mnt/bulk/data", source_sudo=True)

    def test_endpoint_injection_refuses(self):
        for source in ("-oProxyCommand=bad:/volume1/data", "host:/etc",
                       "host;bad:/volume1/data", "host:/volume1/data\nbad",
                       "-oOption@host:/volume1/data"):
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    migration.rsync_plan(source, "/mnt/loan/data")

    def test_preflight_has_no_execution_by_default(self):
        with patch.object(migration.subprocess, "run") as process:
            result = migration.preflight("nas01", "reader@nas01")
        process.assert_not_called()
        self.assertFalse(result["execute"])
        self.assertTrue(all(command[0] == "ssh" for command in result["read_only_commands"]))

    def test_preflight_execution_is_only_fixed_readonly_inventory(self):
        completed = migration.subprocess.CompletedProcess([], 0, "inventory", "")
        with patch.object(migration.subprocess, "run", return_value=completed) as process:
            result = migration.preflight("nas02", "reader@nas02", True)
        self.assertFalse(result["migration_approved"])
        self.assertEqual(process.call_count, len(migration.PREFLIGHT["nas02"]))
        for call in process.call_args_list:
            self.assertNotIn("shell", call.kwargs)

    def test_preflight_failure_stops_instead_of_claiming_success(self):
        completed = migration.subprocess.CompletedProcess([], 1, "", "permission denied")
        with patch.object(migration.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(ValueError, "preflight failed"):
                migration.preflight("nas02", "reader@nas02", True)

    def test_nul_stream_supports_newlines_and_refuses_a_stale_signature(self):
        budgets = {"loan": 100000}
        summary, _ = migration.shard_plan(str(self.source), budgets)
        output = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        arguments = ["shards", "--root", str(self.source), "--budget", "loan=100000",
                     "--files-for", "loan", "--expect-signature", summary["scan_signature"]]
        with patch.object(migration.sys, "stdout", output):
            self.assertEqual(migration.main(arguments), 0)
        self.assertIn(b"./media/line\nbreak\0", output.buffer.getvalue())
        (self.source / "new").write_bytes(b"new")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(migration.main(arguments), 2)

    def test_nul_stream_requires_frozen_signature(self):
        with contextlib.redirect_stderr(io.StringIO()):
            result = migration.main(["shards", "--root", str(self.source),
                                     "--budget", "loan=100000", "--files-for", "loan"])
        self.assertEqual(result, 2)

    def test_metadata_only_is_not_a_verification_pass(self):
        baseline = self.work / "baseline.json"
        baseline.write_text(json.dumps(migration.fingerprint([str(self.source)])))
        with contextlib.redirect_stderr(io.StringIO()):
            result = migration.main(["verify", "--root", str(self.source),
                                     "--baseline", str(baseline)])
        self.assertEqual(result, 2)

    def test_verified_fingerprint_exits_success_then_refuses_content_mismatch(self):
        baseline = self.work / "baseline.json"
        baseline.write_text(json.dumps(migration.fingerprint([str(self.source)], True)))
        arguments = ["verify", "--root", str(self.source), "--checksum", "--baseline", str(baseline)]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(migration.main(arguments), 0)
        (self.source / "media" / "independent").write_bytes(b"changed")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(migration.main(arguments), 1)

    def test_budget_parser_rejects_ambiguous_values(self):
        for values in ([], ["loan=-1"], ["loan=1", "loan=2"], ["a/b=2"], ["loan=1.5"]):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    migration.parse_budgets(values)


if __name__ == "__main__":
    unittest.main()
