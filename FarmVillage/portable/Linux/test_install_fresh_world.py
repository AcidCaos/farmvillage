"""Fresh-world validation, backups, rollback, and verified stopping on disposable data."""

from contextlib import contextmanager
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import sys
import tarfile
import tempfile
import unittest
from unittest import mock


spec = importlib.util.spec_from_file_location("install_fresh_world", Path(__file__).with_name("install-fresh-world.py"))
installer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = installer
spec.loader.exec_module(installer)


class NoService:
    def stop_if_owned(self):
        return False


class FreshWorldTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="farmvillage-fresh-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.hosting = self.root / "hosting"
        self.hosting.mkdir()
        self.data = self.root / "data"
        self.data.mkdir()
        self.before = {
            "saves/old-player.save.json": b'{"old":"player"}\n',
            "saves/old-starter.save.json": b'{"old":"starter"}\n',
            "god-barn/snapshots/old.json": b'{"snapshot":"keep"}\n',
            "neighborhood/old.json": b'{"old":"neighborhood"}\n',
            "assets/huge.swf": b"ASSETS MUST STAY HERE",
            ".lan-server/session.secret": b"s" * 32,
            ".lan-server/password.hash": b"PASSWORD MUST NOT CHANGE",
        }
        for name, contents in self.before.items():
            target = self.data / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(contents)
        self.ids = ["player"] + [f"neighbor{number}" for number in range(1, 6)]
        saves = {uid: json.dumps({"userInfo": {"player": {"userId": uid, "xp": 0}},
                                 "world": {"objectsArray": []}}).encode() for uid in self.ids}
        self.manifest = {"schemaVersion": 1, "updateId": "bifrost-fresh-neighborhood-20261021-v1",
                         "playerUid": self.ids[0], "residents": [
                             {"uid": uid, "name": f"Resident {uid}", "theme": "Test garden"} for uid in self.ids[1:]],
                         "saveFiles": {uid: f"{uid}.save.json" for uid in self.ids},
                         "saveSha256": {f"{uid}.save.json": hashlib.sha256(contents).hexdigest() for uid, contents in saves.items()}}
        self.files = {f"world/saves/{uid}.save.json": contents for uid, contents in saves.items()}
        self.files["world/neighborhood/manifest.json"] = json.dumps(self.manifest).encode()
        self.files["world/neighborhood/templates/initial.json"] = b'{"template":"original"}\n'
        self.manifest["initialTemplateSha256"] = hashlib.sha256(self.files["world/neighborhood/templates/initial.json"]).hexdigest()
        self.files["world/neighborhood/manifest.json"] = json.dumps(self.manifest).encode()
        self.archive = self.make_archive(self.files)

    def make_archive(self, files, *, special=None):
        destination = self.root / "fresh.tar.gz"
        with tarfile.open(destination, "w:gz") as output:
            for name, contents in files.items():
                item = tarfile.TarInfo(name)
                item.size = len(contents)
                output.addfile(item, io.BytesIO(contents))
            if special is not None:
                output.addfile(special)
        return destination

    @contextmanager
    def quiet_lock(self, data, hosting):
        with installer.world_lock(data, hosting, service=NoService()) as state:
            yield state

    def install(self, *, start_service=None):
        return installer.install_world(self.archive, self.data, self.hosting,
                                       locker=self.quiet_lock, start_service=start_service or (lambda: None))

    def test_fresh_install_keeps_assets_credentials_and_archives_original_world(self):
        starts = []

        def start_service():
            # Installation must release the ownership lock before service init.
            with self.quiet_lock(self.data, self.hosting):
                starts.append(True)

        result = self.install(start_service=start_service)
        self.assertTrue(result["applied"])
        self.assertEqual(starts, [True])
        self.assertEqual(sorted(path.name for path in (self.data / "saves").iterdir()),
                         sorted(f"{uid}.save.json" for uid in self.ids))
        self.assertEqual(list((self.data / "god-barn").iterdir()), [])
        self.assertEqual((self.data / "neighborhood/templates/initial.json").read_bytes(), b'{"template":"original"}\n')
        for name in ("assets/huge.swf", ".lan-server/session.secret", ".lan-server/password.hash"):
            self.assertEqual((self.data / name).read_bytes(), self.before[name])
        backup = result["backup"]
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((backup / "farm-data.tar.gz").stat().st_mode), 0o600)
        with tarfile.open(backup / "farm-data.tar.gz") as source:
            names = set(source.getnames())
            self.assertFalse(any(name.startswith(("assets", ".lan-server")) for name in names))
            for name, contents in self.before.items():
                if name.startswith(("saves/", "god-barn/", "neighborhood/")):
                    self.assertEqual(source.extractfile(name).read(), contents)
                    self.assertEqual((backup / "previous-directories" / name).read_bytes(), contents)

    def test_repeating_same_update_preserves_new_progress_and_retries_service(self):
        calls = []

        def failed_service():
            calls.append("first")
            raise RuntimeError("synthetic service setup failure")

        output = io.StringIO()
        with mock.patch.object(sys, "stderr", output):
            with self.assertRaisesRegex(RuntimeError, "synthetic"):
                self.install(start_service=failed_service)
        self.assertIn("backup remains at", output.getvalue())
        self.assertIn("without resetting progress", output.getvalue())
        player = self.data / "saves/player.save.json"
        player.write_bytes(b"NEW PROGRESS MUST SURVIVE")
        result = self.install(start_service=lambda: calls.append("second"))
        self.assertFalse(result["applied"])
        self.assertEqual(player.read_bytes(), b"NEW PROGRESS MUST SURVIVE")
        self.assertEqual(calls, ["first", "second"])
        self.assertEqual(len(list((self.root / "backups").glob("pre-fresh-world-*"))), 1)

    def test_failed_directory_swap_rolls_back_every_original(self):
        real_rename = os.rename
        failed = []

        def rename(source, destination):
            if (Path(source).name == "neighborhood" and Path(source).parent.name.startswith(".fresh-world-stage-") and not failed):
                failed.append(True)
                raise OSError("synthetic rename failure")
            return real_rename(source, destination)

        with mock.patch.object(installer.os, "rename", side_effect=rename):
            with self.assertRaisesRegex(OSError, "synthetic"):
                self.install()
        for name, contents in self.before.items():
            self.assertEqual((self.data / name).read_bytes(), contents)
        self.assertFalse((self.data / ".lan-server" / installer.APPLIED_MARKER).exists())
        self.assertEqual(len(list((self.root / "backups").glob("*/farm-data.tar.gz"))), 1)

    def test_failed_marker_write_rolls_back_world_before_starting(self):
        starts = []
        with mock.patch.object(installer, "atomic_marker", side_effect=OSError("marker write failed")):
            with self.assertRaisesRegex(OSError, "marker write"):
                self.install(start_service=lambda: starts.append(True))
        self.assertEqual(starts, [])
        for name, contents in self.before.items():
            self.assertEqual((self.data / name).read_bytes(), contents)

    def test_bad_inventory_link_or_identity_fails_before_stopping_or_modifying(self):
        symlink = tarfile.TarInfo("world/saves/evil.save.json")
        symlink.type = tarfile.SYMTYPE
        symlink.linkname = "/etc/passwd"
        duplicate = tarfile.TarInfo("world/saves/player.save.json")
        duplicate.size = 0
        for variant in ("extra", "missing", "traversal", "symlink", "duplicate", "identity", "digest", "template-digest"):
            with self.subTest(variant=variant):
                files = dict(self.files)
                special = None
                if variant == "extra": files["world/assets/asset.swf"] = b"no"
                if variant == "missing": del files["world/saves/neighbor1.save.json"]
                if variant == "traversal": files["world/../escape"] = b"no"
                if variant == "symlink": special = symlink
                if variant == "duplicate": special = duplicate
                if variant == "identity": files["world/saves/player.save.json"] = files["world/saves/neighbor1.save.json"]
                if variant == "digest": files["world/saves/player.save.json"] += b" "
                if variant == "template-digest": files["world/neighborhood/templates/initial.json"] += b" "
                self.make_archive(files, special=special)
                with mock.patch.object(installer, "world_lock", side_effect=AssertionError("should not stop")):
                    with self.assertRaises(ValueError):
                        self.install()
                self.assertFalse((self.root / "backups").exists())
                self.assertEqual((self.data / "saves/old-player.save.json").read_bytes(), self.before["saves/old-player.save.json"])

    def test_optional_internal_checksums_require_full_correct_inventory(self):
        files = dict(self.files)
        files["SHA256SUMS"] = "".join(f"{hashlib.sha256(contents).hexdigest()}  {name}\n"
                                       for name, contents in sorted(files.items())).encode()
        self.make_archive(files)
        self.assertEqual(installer.validate_archive(self.archive).update_id, self.manifest["updateId"])
        files["SHA256SUMS"] = b"0" * 64 + b"  world/neighborhood/manifest.json\n"
        self.make_archive(files)
        with self.assertRaisesRegex(ValueError, "checksum"):
            installer.validate_archive(self.archive)

    def test_sudo_invocation_is_rejected_before_world_changes(self):
        output = io.StringIO()
        with mock.patch.object(installer.os, "getuid", return_value=0), mock.patch.object(sys, "stderr", output):
            result = installer.main(["--archive", str(self.archive), "--data-dir", str(self.data)])
        self.assertEqual(result, 1)
        self.assertIn("without sudo", output.getvalue())
        self.assertFalse((self.root / "backups").exists())
        self.assertEqual((self.data / "saves/old-player.save.json").read_bytes(), self.before["saves/old-player.save.json"])

    def test_verified_owner_accepts_equal_argument_and_rejects_other_process_or_data(self):
        process = self.root / "proc/123456"
        process.mkdir(parents=True)
        command = [sys.executable, "-B", "-u", str(self.hosting / "server_runner.py"), f"--data-dir={self.data}"]
        process.joinpath("cmdline").write_bytes(("\0".join(command) + "\0").encode())
        installer.verify_owner(123456, self.hosting, self.data, proc_root=process.parent)
        command[-1] = f"--data-dir={self.root / 'other'}"
        process.joinpath("cmdline").write_bytes(("\0".join(command) + "\0").encode())
        with self.assertRaisesRegex(RuntimeError, "data folder"):
            installer.verify_owner(123456, self.hosting, self.data, proc_root=process.parent)
        command = [sys.executable, "-c", "unrelated_code", str(self.hosting / "server_runner.py"), "--data-dir", str(self.data)]
        process.joinpath("cmdline").write_bytes(("\0".join(command) + "\0").encode())
        with self.assertRaisesRegex(RuntimeError, "expected LAN runner"):
            installer.verify_owner(123456, self.hosting, self.data, proc_root=process.parent)

    def test_active_lock_stops_only_verified_owner_then_waits_for_release(self):
        lock = self.data / ".lan-server/owner.lock"
        lock.write_bytes(b"123456\n")
        descriptor = os.open(lock, os.O_RDWR)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        events = []

        def inspect(pid, hosting, data):
            events.append(("verified", pid))

        def interrupt(pid, hosting, data):
            events.append(("interrupted", pid))
            fcntl.flock(descriptor, fcntl.LOCK_UN)

        try:
            with installer.world_lock(self.data, self.hosting, service=NoService(), inspector=inspect, interrupt=interrupt, timeout=1):
                events.append(("acquired", None))
        finally:
            os.close(descriptor)
        self.assertEqual(events, [("verified", 123456), ("interrupted", 123456), ("acquired", None)])
        self.assertEqual(lock.read_bytes(), b"123456\n")

    def test_unknown_owner_is_not_signaled_and_timeout_never_force_kills(self):
        lock = self.data / ".lan-server/owner.lock"
        lock.write_bytes(b"123456\n")
        descriptor = os.open(lock, os.O_RDWR)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        signal_calls = []
        try:
            def unknown(*arguments):
                raise RuntimeError("unknown owner")
            with self.assertRaisesRegex(RuntimeError, "unknown owner"):
                with installer.world_lock(self.data, self.hosting, service=NoService(), inspector=unknown,
                                          interrupt=lambda *args: signal_calls.append(args)):
                    pass
            self.assertEqual(signal_calls, [])
            with self.assertRaisesRegex(RuntimeError, "still finishing requests"):
                with installer.world_lock(self.data, self.hosting, service=NoService(), inspector=lambda *args: None,
                                          interrupt=lambda *args: signal_calls.append(args), timeout=0.01):
                    pass
            self.assertEqual(len(signal_calls), 1)
            self.assertEqual(lock.read_bytes(), b"123456\n")
        finally:
            os.close(descriptor)

    def test_owned_service_is_used_instead_of_interrupting_foreground_pid(self):
        lock = self.data / ".lan-server/owner.lock"
        lock.write_bytes(b"123456\n")
        descriptor = os.open(lock, os.O_RDWR)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        service = mock.Mock()
        service.stop_if_owned.side_effect = lambda: (fcntl.flock(descriptor, fcntl.LOCK_UN) is None)
        try:
            with installer.world_lock(self.data, self.hosting, service=service, inspector=lambda *args: None,
                                      interrupt=lambda *args: self.fail("Should stop the owned service instead.")):
                pass
        finally:
            os.close(descriptor)
        service.stop_if_owned.assert_called_once()


if __name__ == "__main__":
    unittest.main()
