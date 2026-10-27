"""Rolling farm backups: creation before overwrite, throttling, pruning, failure isolation, and listing.

Every writable file lives in a temporary data directory; the backup clock is mocked.
    python -m unittest discover -s macOS/Tests -p test_minion_backups.py -v
"""

from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import atexit
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
_runtime_data = tempfile.TemporaryDirectory(prefix="farmvillage-backup-tests-")
atexit.register(_runtime_data.cleanup)
os.environ["FARMVILLAGE_DATA_DIR"] = _runtime_data.name
os.environ["FARMVILLAGE_NATIVE"] = "1"
os.environ["FARMVILLAGE_INSTANCE_TOKEN"] = "test-instance"

import items  # noqa: E402
import persistence  # noqa: E402
import player  # noqa: E402

START = datetime(2026, 10, 21, 12, 0, 0, tzinfo=timezone.utc)


class FarmBackupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="farmvillage-backups-")
        self.addCleanup(self.directory.cleanup)
        self.saves = Path(self.directory.name) / "saves"
        self.saves.mkdir()
        self.now = START
        # Backup behaviour does not depend on item data, so the catalog is empty here:
        # migration treats unknown items as having no expansion parts, and the starter
        # village's grown plots only need a grow time.
        for patcher in (
            mock.patch.object(player, "SAVES_DIR", str(self.saves)),
            mock.patch.object(persistence, "_backup_clock", side_effect=lambda: self.now),
            mock.patch.object(items, "_cached_items", {"settings": {"items": {"item": []}}}),
            mock.patch.object(player, "get_item_by_name", return_value={"growTime": "1"}),
            mock.patch.object(player, "get_farming_number", return_value=1.0),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        with redirect_stdout(io.StringIO()):
            player.load_saves()

    # Helpers

    def farm_path(self, uid):
        return self.saves / f"{uid}.save.json"

    def backups(self, uid):
        folder = self.saves / ".backups" / uid
        return sorted(folder.iterdir()) if folder.exists() else []

    def labels(self, uid):
        return [json.loads(path.read_bytes())["label"] for path in self.backups(uid)]

    def new_farm(self):
        with redirect_stdout(io.StringIO()):
            return player.new_village("Backup Farmer")

    def save_name(self, uid, name):
        player.session(uid)["userInfo"]["attr"]["name"] = name
        with redirect_stdout(io.StringIO()):
            player.save_session(uid)

    def name_on_disk(self, uid):
        return persistence.read_json(self.farm_path(uid))["userInfo"]["attr"]["name"]

    def advance(self, **delta):
        self.now += timedelta(**delta)

    def seed_backup(self, uid, when, label):
        self.now = when
        persistence.backup_farm_before_overwrite(self.saves, uid, json.dumps({"label": label}).encode())

    # Creation

    def test_overwrite_keeps_the_displaced_bytes_as_a_backup(self):
        uid = self.new_farm()
        before = self.farm_path(uid).read_bytes()
        self.assertEqual(self.backups(uid), [])  # a first write displaces nothing
        self.save_name(uid, "Second Name")
        backups = self.backups(uid)
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), before)
        self.assertEqual(self.name_on_disk(uid), "Second Name")

    def test_identical_rewrite_is_not_backed_up(self):
        uid = self.new_farm()
        self.save_name(uid, "Backup Farmer")  # same bytes: nothing is displaced
        self.assertEqual(self.backups(uid), [])

    def test_each_farm_has_its_own_throttle_inside_one_transaction(self):
        first = self.new_farm()
        second = self.new_farm()
        with redirect_stdout(io.StringIO()):
            with player.village_transaction(first):
                player.session(first)["userInfo"]["attr"]["name"] = "Changed One"
                player.save_session(first)
                player.session(second)["userInfo"]["attr"]["name"] = "Changed Two"
                player.save_session(second)
        self.assertEqual(len(self.backups(first)), 1)
        self.assertEqual(len(self.backups(second)), 1)

    def test_migration_rewrite_keeps_the_imported_bytes_as_a_backup(self):
        uid = "legacy-farmer"
        fixture = json.loads((ROOT / "villages" / "initial.json").read_text())
        fixture["userInfo"]["player"]["userId"] = uid
        fixture["flashHotParams"]["ZYNGA_USER_ID"] = uid
        fixture["userInfo"]["firstDayTimestamp"] = 1
        path = self.saves / "imported.json"
        persistence.atomic_json(path, fixture)
        original = path.read_bytes()
        with redirect_stdout(io.StringIO()):
            player.load_saves()
        self.assertEqual(player.all_saves_uids(), [uid])
        backups = self.backups(uid)
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)

    def test_commits_without_farm_uids_keep_no_backups(self):
        path = self.saves / "plain.save.json"
        persistence.commit_json_batch(self.saves, {path: {"v": 1}})
        persistence.commit_json_batch(self.saves, {path: {"v": 2}})
        self.assertFalse((self.saves / ".backups").exists())

    # Throttling

    def test_backups_are_throttled_to_one_per_farm_per_ten_minutes(self):
        uid = self.new_farm()
        self.save_name(uid, "First")  # displaces the new farm: backed up
        self.assertEqual(len(self.backups(uid)), 1)
        self.advance(minutes=5)
        self.save_name(uid, "Second")  # 5 minutes after the newest backup: throttled
        self.assertEqual(len(self.backups(uid)), 1)
        self.advance(minutes=4, seconds=59)
        self.save_name(uid, "Third")  # 9:59 after the newest backup: throttled
        self.assertEqual(len(self.backups(uid)), 1)
        self.advance(seconds=1)
        self.save_name(uid, "Fourth")  # exactly 10:00 after the newest backup: backed up
        backups = self.backups(uid)
        self.assertEqual(len(backups), 2)
        self.assertEqual(json.loads(backups[-1].read_bytes())["userInfo"]["attr"]["name"], "Third")

    def test_a_clock_moved_backwards_does_not_suppress_backups(self):
        uid = self.new_farm()
        self.save_name(uid, "First")
        self.advance(hours=-2)
        self.save_name(uid, "Second")
        self.assertEqual(len(self.backups(uid)), 2)

    # Pruning

    def test_keeps_only_the_newest_twenty_backups(self):
        uid = self.new_farm()
        for index in range(25):
            self.save_name(uid, f"Name {index}")
            self.advance(minutes=11)
        backups = self.backups(uid)
        self.assertEqual(len(backups), 20)
        names = [json.loads(path.read_bytes())["userInfo"]["attr"]["name"] for path in backups]
        # Backup k holds the bytes displaced by save k: "Backup Farmer", "Name 0" ... "Name 23".
        self.assertEqual(names[0], "Name 4")
        self.assertEqual(names[-1], "Name 23")

    def test_pruning_keeps_the_newest_backup_of_each_recent_day(self):
        uid = self.new_farm()
        self.seed_backup(uid, START - timedelta(days=3), "three days ago")
        self.seed_backup(uid, START - timedelta(days=2), "two days ago")
        for index in range(22):
            self.seed_backup(uid, START + timedelta(minutes=11 * index), f"today {index}")
        labels = self.labels(uid)
        self.assertEqual(len(labels), 20)
        self.assertIn("three days ago", labels)
        self.assertIn("two days ago", labels)
        self.assertEqual(labels[-1], "today 21")

    def test_a_backup_older_than_a_week_is_pruned_once_twenty_newer_ones_exist(self):
        uid = self.new_farm()
        self.seed_backup(uid, START - timedelta(days=10), "ten days ago")
        for index in range(20):
            self.seed_backup(uid, START + timedelta(minutes=11 * index), f"today {index}")
        labels = self.labels(uid)
        self.assertEqual(len(labels), 20)
        self.assertNotIn("ten days ago", labels)

    # Failure isolation

    def test_a_blocked_backup_folder_never_fails_the_save(self):
        uid = self.new_farm()
        (self.saves / ".backups").write_bytes(b"not a folder")
        output = io.StringIO()
        with redirect_stdout(output):
            player.session(uid)["userInfo"]["attr"]["name"] = "Still Saved"
            player.save_session(uid)
        self.assertEqual(self.name_on_disk(uid), "Still Saved")
        self.assertIn("Farm backup skipped", output.getvalue())

    def test_a_failed_backup_write_never_fails_the_save(self):
        uid = self.new_farm()
        real_atomic_bytes = persistence.atomic_bytes

        def fail_backup_writes(path, contents):
            if ".backups" in Path(path).parts:
                raise OSError("disk full")
            return real_atomic_bytes(path, contents)

        output = io.StringIO()
        with mock.patch.object(persistence, "atomic_bytes", side_effect=fail_backup_writes), redirect_stdout(output):
            player.session(uid)["userInfo"]["attr"]["name"] = "Still Saved"
            player.save_session(uid)
        self.assertEqual(self.name_on_disk(uid), "Still Saved")
        self.assertEqual(self.backups(uid), [])
        self.assertIn("disk full", output.getvalue())

    # Listing, recovery, and permissions

    def test_backups_are_never_loaded_as_farms_or_journal_entries(self):
        uid = self.new_farm()
        self.save_name(uid, "Second")
        backup = self.backups(uid)[0]
        output = io.StringIO()
        with redirect_stdout(output):
            player.load_saves()
            persistence.recover_json_transactions(self.saves)
        # A backup copy carries the same UID, so listing it would report a duplicate and drop the farm.
        self.assertEqual(player.all_saves_uids(), [uid])
        self.assertNotIn("duplicate", output.getvalue())
        self.assertTrue(backup.exists())

    @unittest.skipIf(os.name == "nt", "POSIX file modes")
    def test_backups_and_their_folders_are_owner_only(self):
        uid = self.new_farm()
        self.save_name(uid, "Second")
        self.assertEqual(stat.S_IMODE(self.backups(uid)[0].stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((self.saves / ".backups").stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.saves / ".backups" / uid).stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.farm_path(uid).stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
