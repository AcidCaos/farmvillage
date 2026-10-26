"""Offline storage and Flask integration checks; all writable data is temporary.

Run with the runtime dependencies installed:
    python -m unittest discover -s macOS/Tests -p test_persistence.py -v
No game archives, browsers, application data, or external network are used.
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
import atexit
import base64
import copy
from datetime import datetime
import gzip
import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
if "bundle" in sys.modules:
    # bundle resolves CACHE_DIR and SAVES_DIR once, at its first import. Loading it
    # before this harness would send test saves and caches into the project root.
    raise ImportError("Import test_persistence before any module that loads bundle.")
_runtime_data = tempfile.TemporaryDirectory(prefix="farmvillage-persistence-tests-")
atexit.register(_runtime_data.cleanup)
os.environ["FARMVILLAGE_DATA_DIR"] = _runtime_data.name
os.environ["FARMVILLAGE_NATIVE"] = "1"
os.environ["FARMVILLAGE_INSTANCE_TOKEN"] = "test-instance"

import persistence


class AtomicStorageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="farmvillage-atomic-")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "save.json"
        persistence.atomic_json(self.path, {"previous": True})

    def test_failed_serialization_keeps_original_and_removes_temporary(self):
        original = self.path.read_bytes()
        with self.assertRaises(ValueError):
            persistence.atomic_json(self.path, {"bad": float("nan")})
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_failed_replacement_keeps_original_and_removes_temporary(self):
        original = self.path.read_bytes()
        with mock.patch("persistence.os.replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                persistence.atomic_json(self.path, {"new": True})
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_concurrent_writers_only_publish_complete_json(self):
        def write(index):
            persistence.atomic_json(self.path, {"index": index, "body": str(index) * 10000})
            observed = persistence.read_json(self.path)
            self.assertEqual(observed["body"], str(observed["index"]) * 10000)
        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(write, range(30)))
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_nonfinite_json_input_is_rejected(self):
        for value in ("NaN", "Infinity", "-Infinity", "1e999", "-1e999"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                persistence.decode_json('{"value":' + value + '}')


class CacheIdentityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="farmvillage-cache-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.cache = self.root / "cache.json"
        self.source = self.root / "source.xml"
        self.decoder = self.root / "decoder.py"
        self.source.write_bytes(b"first")
        self.decoder.write_text("decoder-one", encoding="utf-8")
        self.build = mock.Mock(side_effect=lambda data: {"value": data.decode("ascii")})

    def load(self, schema=1):
        with redirect_stdout(io.StringIO()):
            return persistence.load_catalog_cache(
                self.cache, source=self.source, decoder=self.decoder, schema=schema,
                build=self.build,
                validate=lambda value: isinstance(value, dict) and isinstance(value.get("value"), str),
            )

    def test_unchanged_catalog_reuses_valid_cache(self):
        self.assertEqual(self.load(), {"value": "first"})
        self.assertEqual(self.load(), {"value": "first"})
        self.assertEqual(self.build.call_count, 1)

    def test_source_decoder_schema_and_dependencies_invalidate_cache(self):
        self.load()
        self.source.write_bytes(b"second")
        self.assertEqual(self.load(), {"value": "second"})
        self.decoder.write_text("decoder-two", encoding="utf-8")
        self.load()
        self.load(schema=2)
        (self.root / "requirements.txt").write_text("changed==1", encoding="utf-8")
        self.load(schema=2)
        self.assertEqual(self.build.call_count, 5)

    def test_truncated_legacy_wrong_shape_and_modified_data_rebuild(self):
        self.load()
        good = self.cache.read_bytes()
        tampered = json.loads(good)
        tampered["data"]["value"] = "tampered"
        wrong_shape = json.loads(good)
        wrong_shape["data"] = []
        for broken in (b'{"unfinished":', b'\xff', b'{"value":"legacy"}',
                       json.dumps(tampered).encode(), json.dumps(wrong_shape).encode()):
            with self.subTest(broken=broken):
                self.cache.write_bytes(broken)
                self.assertEqual(self.load(), {"value": "first"})
        self.assertEqual(self.build.call_count, 6)


class MultiFarmJournalTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="farmvillage-journal-")
        self.addCleanup(self.directory.cleanup)
        self.saves = Path(self.directory.name)
        self.first = self.saves / "first.json"
        self.second = self.saves / "second.json"
        persistence.atomic_json(self.first, {"old": "first"})
        persistence.atomic_json(self.second, {"old": "second"})
        self.originals = [self.first.read_bytes(), self.second.read_bytes()]
        self.updates = {self.first: {"new": "first"}, self.second: {"new": "second"}}

    def test_successful_batch_commits_all_farms_and_cleans_journal(self):
        persistence.commit_json_batch(self.saves, self.updates)
        self.assertEqual(persistence.read_json(self.first), {"new": "first"})
        self.assertEqual(persistence.read_json(self.second), {"new": "second"})
        self.assertEqual(list((self.saves / ".save-transactions").iterdir()), [])

    def test_installed_single_save_sync_failure_rolls_back_original(self):
        actual_sync = persistence._sync_directory
        failed = False
        def sync(directory):
            nonlocal failed
            if Path(directory) == self.saves and self.first.read_bytes() != self.originals[0] and not failed:
                failed = True
                raise OSError("directory sync failed after replacement")
            return actual_sync(directory)
        with mock.patch("persistence._sync_directory", side_effect=sync):
            with self.assertRaises(persistence.AtomicWriteInstalledError):
                persistence.commit_json_batch(self.saves, {self.first: {"new": "single"}})
        self.assertTrue(failed)
        self.assertEqual(self.first.read_bytes(), self.originals[0])

    def test_published_commit_sync_failure_reports_committed_state(self):
        actual_sync = persistence._sync_directory
        failed = False
        def sync(directory):
            nonlocal failed
            manifest = Path(directory) / "manifest.json"
            if manifest.exists() and persistence.read_json(manifest)["state"] == "committed" and not failed:
                failed = True
                raise OSError("commit directory sync failed")
            return actual_sync(directory)
        with mock.patch("persistence._sync_directory", side_effect=sync):
            with self.assertRaisesRegex(persistence.CommittedSaveError, "were committed"):
                persistence.commit_json_batch(self.saves, self.updates)
        self.assertTrue(failed)
        self.assertEqual(persistence.read_json(self.first), {"new": "first"})
        self.assertEqual(persistence.read_json(self.second), {"new": "second"})
        persistence.recover_json_transactions(self.saves)
        self.assertEqual(persistence.read_json(self.first), {"new": "first"})

    def test_cleanup_failure_is_retried_without_reverting_committed_farms(self):
        with mock.patch("persistence.shutil.rmtree", side_effect=OSError("cleanup interrupted")):
            with redirect_stdout(io.StringIO()):
                persistence.commit_json_batch(self.saves, self.updates)
        self.assertEqual(len(list((self.saves / ".save-transactions").iterdir())), 1)
        persistence.recover_json_transactions(self.saves)
        self.assertEqual(persistence.read_json(self.first), {"new": "first"})
        self.assertEqual(list((self.saves / ".save-transactions").iterdir()), [])

    def test_symbolic_link_destination_or_journal_never_gets_followed(self):
        outside = self.saves / "outside.json"
        persistence.atomic_json(outside, {"outside": "unchanged"})
        self.first.unlink()
        self.first.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "symbolic link"):
            persistence.commit_json_batch(self.saves, self.updates)
        self.assertEqual(persistence.read_json(outside), {"outside": "unchanged"})
        self.first.unlink()
        self.first.write_bytes(self.originals[0])
        other = self.saves / "other-directory"
        other.mkdir()
        (self.saves / ".save-transactions").symlink_to(other, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "recovery directory is unsafe"):
            persistence.commit_json_batch(self.saves, self.updates)
        self.assertEqual(list(other.iterdir()), [])

    def test_second_replace_failure_restores_all_original_bytes(self):
        actual_replace = os.replace
        failed = False
        def replace(source, destination):
            nonlocal failed
            if Path(destination) == self.second and not failed:
                failed = True
                raise OSError("second farm disk failure")
            return actual_replace(source, destination)
        with mock.patch("persistence.os.replace", side_effect=replace), self.assertRaises(OSError):
            persistence.commit_json_batch(self.saves, self.updates)
        self.assertTrue(failed)
        self.assertEqual([self.first.read_bytes(), self.second.read_bytes()], self.originals)

    def test_process_exit_between_farms_is_recovered_on_restart(self):
        # Exit without Python cleanup after the first real replacement, proving
        # on-disk recovery rather than relying on exception handlers to run.
        program = '''
import os
from pathlib import Path
import sys
import persistence
saves = Path(sys.argv[1])
actual_replace = os.replace
def replace(source, destination):
    if Path(destination) == saves / "second.json":
        os._exit(71)
    return actual_replace(source, destination)
persistence.os.replace = replace
persistence.commit_json_batch(saves, {saves / "first.json": {"new": "first"}, saves / "second.json": {"new": "second"}})
'''
        result = subprocess.run([sys.executable, "-c", program, str(self.saves)], cwd=ROOT,
                                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                                capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 71, result.stderr)
        self.assertEqual(persistence.read_json(self.first), {"new": "first"})
        persistence.recover_json_transactions(self.saves)
        self.assertEqual([self.first.read_bytes(), self.second.read_bytes()], self.originals)
        # Recovery is safe to repeat after the rollback completed.
        persistence.recover_json_transactions(self.saves)

    def test_failed_recovery_preserves_backups_and_blocks_more_writes(self):
        actual_replace = os.replace
        def fail_targets(source, destination):
            if Path(destination) == self.second:
                raise OSError("persistent disk failure")
            return actual_replace(source, destination)
        with mock.patch("persistence.os.replace", side_effect=fail_targets):
            with self.assertRaises(OSError):
                persistence.commit_json_batch(self.saves, self.updates)
            journals = list((self.saves / ".save-transactions").iterdir())
            self.assertEqual(len(journals), 1)
            self.assertEqual((journals[0] / "0.original").read_bytes(), self.originals[0])
            with self.assertRaisesRegex(RuntimeError, "recovery is incomplete"):
                persistence.commit_json_batch(self.saves, {self.first: {"must": "block"}})
        persistence.recover_json_transactions(self.saves)
        self.assertEqual([self.first.read_bytes(), self.second.read_bytes()], self.originals)

    def test_corrupted_backup_blocks_recovery_without_replacing_any_farm(self):
        actual_replace = os.replace
        failed = False
        def replace(source, destination):
            nonlocal failed
            if Path(destination) == self.second and not failed:
                failed = True
                raise OSError("disk failure")
            return actual_replace(source, destination)
        with mock.patch("persistence.os.replace", side_effect=replace):
            with mock.patch("persistence._recover_transaction", side_effect=OSError("recovery unavailable")):
                with self.assertRaises(OSError):
                    persistence.commit_json_batch(self.saves, self.updates)
        journal = next((self.saves / ".save-transactions").iterdir())
        (journal / "1.original").write_bytes(b"corrupted")
        before = [self.first.read_bytes(), self.second.read_bytes()]
        with self.assertRaisesRegex(RuntimeError, "recovery copy is damaged"):
            persistence.recover_json_transactions(self.saves)
        self.assertEqual([self.first.read_bytes(), self.second.read_bytes()], before)


def gateway_results(case, response, errors=None):
    """Assert the actual wire result, including visible per-command rejection."""
    from pyamf import remoting
    case.assertEqual(response.status_code, 200, response.data[:300])
    body = remoting.decode(response.data).bodies[0][1].body
    case.assertEqual(body["errorType"], 0)
    results = body["data"]
    if errors is not None:
        case.assertEqual([result["errorType"] for result in results], errors)
    for result in results:
        if result["errorType"]:
            case.assertEqual(result["errorType"], 29)
            case.assertIsNone(result["data"])
            case.assertIsInstance(result["errorData"], str)
            case.assertTrue(result["errorData"])
    return results


def assert_gateway_rejected(case, response):
    results = gateway_results(case, response)
    case.assertTrue(results)
    case.assertTrue(all(result["errorType"] == 29 for result in results))


def assert_gateway_status(case, response, expected):
    if expected == 400:
        assert_gateway_rejected(case, response)
    else:
        case.assertEqual(expected, 200)
        results = gateway_results(case, response)
        case.assertTrue(all(result["errorType"] == 0 for result in results))


class RuntimeFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Import the real server and real bundled catalogs, bypassing only the
        # multi-gigabyte optional artwork download. No server socket is opened.
        import assets
        with mock.patch.object(assets, "check_assets"), mock.patch.object(sys, "argv", ["server.py"]):
            with redirect_stdout(io.StringIO()):
                cls.server = importlib.import_module("server")
        cls.server.app.secret_key = "test-only-key"
        cls.server.app.template_folder = str(ROOT / "templates")
        cls.server.app.config.update(TESTING=True)
        import player
        import bundle
        import game_settings
        import items
        import quests
        import avatar
        cls.player = player
        cls.bundle = bundle
        cls.catalogs = (game_settings, items, quests, avatar)
        cls.initial = json.loads((ROOT / "villages" / "initial.json").read_text())

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="farmvillage-saves-")
        self.addCleanup(self.directory.cleanup)
        self.saves = Path(self.directory.name) / "saves"
        self.saves.mkdir()
        patcher = mock.patch.object(self.player, "SAVES_DIR", str(self.saves))
        patcher.start()
        self.addCleanup(patcher.stop)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.client = self.server.app.test_client()

    def fixture(self, uid="fixture-farmer"):
        result = copy.deepcopy(self.initial)
        result["userInfo"]["player"]["userId"] = uid
        result["flashHotParams"]["ZYNGA_USER_ID"] = uid
        result["userInfo"]["firstDayTimestamp"] = 1
        return result

    def write_fixture(self, filename="custom-export.json", uid="fixture-farmer"):
        path = self.saves / filename
        persistence.atomic_json(path, self.fixture(uid))
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        return path

    @staticmethod
    def command(name, params=(), sequence=1):
        import pyamf
        return pyamf.ASObject(functionName=name, params=list(params), sequence=sequence)

    def gateway_payload(self, requests, uid="fixture-farmer", transport_metadata=()):
        import pyamf
        from pyamf import remoting
        envelope = remoting.Envelope(pyamf.AMF0)
        envelope["/1"] = remoting.Request("FarmService", body=[{"uid": uid}, requests, *transport_metadata])
        return remoting.encode(envelope).getvalue()

    def gateway(self, requests, uid="fixture-farmer", client=None):
        payload = self.gateway_payload(requests, uid)
        if client is not None:
            # stdout redirection is process-wide; the concurrent test owns one
            # outer redirect instead of racing per-thread redirects.
            return client.post("/flashservices/gateway.php", data=payload,
                               content_type="application/x-amf")
        with redirect_stdout(io.StringIO()):
            return self.client.post("/flashservices/gateway.php", data=payload,
                                    content_type="application/x-amf")

    def test_actual_catalogs_load_and_corrupted_cache_rebuilds(self):
        game_settings, items, quests, avatar = self.catalogs
        self.assertGreater(len(items.get_items()), 1000)
        self.assertGreater(len(quests.get_quests()), 1000)
        self.assertGreater(len(avatar._cached_items), 900)
        self.assertEqual(game_settings.xp_to_level(0), 1)
        for module, name, loader in (
            (game_settings, "CACHE_CONFIG_JSON", game_settings.load_game_settings),
            (items, "CACHE_ITEMS_JSON", items.load_items),
            (quests, "CACHE_QUESTS_JSON", quests.load_quests),
            (avatar, "CACHE_AVATAR_JSON", avatar.load_avatar),
        ):
            with self.subTest(module=module.__name__):
                cache = Path(getattr(module, name))
                cache.write_bytes(b'{"truncated":')
                with redirect_stdout(io.StringIO()):
                    loader()
                self.assertIn("data_sha256", persistence.read_json(cache))

    def test_migration_retains_import_filename_and_original_backup(self):
        path = self.saves / "custom-export.json"
        persistence.atomic_json(path, self.fixture())
        original = path.read_bytes()
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        backups = list((self.saves / ".migration-backups").iterdir())
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.player.session("fixture-farmer")["userInfo"]["attr"]["name"] = "Updated Farmer"
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")
        self.assertEqual(persistence.read_json(path)["userInfo"]["attr"]["name"], "Updated Farmer")
        self.assertEqual(list(self.saves.glob("*.json")), [path])

    def test_failed_migration_preserves_original_and_never_publishes_partial_state(self):
        path = self.saves / "broken-migration.json"
        persistence.atomic_json(path, self.fixture())
        original = path.read_bytes()
        def fail(save):
            save["userInfo"]["attr"]["name"] = "must not escape"
            raise ValueError("migration failure")
        with mock.patch.object(self.player, "migrate_loaded_save", side_effect=fail):
            with redirect_stdout(io.StringIO()):
                self.player.load_saves()
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.player.all_saves_uids(), [])

    def test_failed_migration_write_keeps_original_and_backup(self):
        path = self.saves / "disk-failure.json"
        persistence.atomic_json(path, self.fixture())
        original = path.read_bytes()
        with mock.patch.object(self.player, "commit_json_batch", side_effect=OSError("disk full")):
            with redirect_stdout(io.StringIO()):
                self.player.load_saves()
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.player.all_saves_uids(), [])
        backups = list((self.saves / ".migration-backups").iterdir())
        self.assertEqual([backup.read_bytes() for backup in backups], [original])

    def test_migration_backup_parent_symlink_never_writes_outside_saves(self):
        path = self.saves / "legacy-export.json"
        persistence.atomic_json(path, self.fixture())
        original = path.read_bytes()
        external = Path(self.directory.name) / "external-sentinel-directory"
        external.mkdir()
        sentinel = external / "sentinel.txt"
        sentinel.write_bytes(b"external data must remain unchanged")
        backup_directory = self.saves / ".migration-backups"
        backup_directory.symlink_to(external, target_is_directory=True)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.player.all_saves_uids(), [])
        self.assertTrue(backup_directory.is_symlink())
        self.assertEqual(list(external.iterdir()), [sentinel])
        self.assertEqual(sentinel.read_bytes(), b"external data must remain unchanged")

    def test_migration_backup_non_directory_parent_preserves_import(self):
        path = self.saves / "legacy-export.json"
        persistence.atomic_json(path, self.fixture())
        original = path.read_bytes()
        backup_parent = self.saves / ".migration-backups"
        backup_parent.write_bytes(b"existing non-directory sentinel")
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(backup_parent.read_bytes(), b"existing non-directory sentinel")
        self.assertEqual(self.player.all_saves_uids(), [])

    def test_invalid_files_duplicates_and_symlinks_are_skipped(self):
        self.write_fixture()
        persistence.atomic_json(self.saves / "duplicate.json", self.fixture())
        persistence.atomic_json(self.saves / ".hidden.json", self.fixture("hidden"))
        persistence.atomic_json(self.saves / "old.backup.json", self.fixture("backup"))
        (self.saves / "unrelated.json").write_text("{}")
        (self.saves / "bad.json").write_text("{broken")
        (self.saves / "backup-folder").mkdir()
        outside = Path(self.directory.name) / "outside.json"
        persistence.atomic_json(outside, self.fixture("linked"))
        (self.saves / "linked.json").symlink_to(outside)
        (self.saves / "only-one.json").write_text(json.dumps(self.fixture("valid")))
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.player.all_saves_uids(), ["valid"])
        self.assertTrue((self.saves / "linked.json").is_symlink())

    def test_malformed_core_imports_are_skipped_without_modifying_sources(self):
        self.write_fixture(uid="valid-control")
        mutations = (
            lambda save: save.update(questState={"active": [], "completed": [], "retired": [], "replayed": {}}),
            lambda save: save["userInfo"]["player"].update(gold="200"),
            lambda save: save["userInfo"]["player"].update(actionCounts=[]),
            lambda save: save.update(avatarState={}),
            lambda save: save["userInfo"]["player"].update(storageData={"-1": {"bad": ["quantity", [], []]}}),
        )
        originals = {}
        for index, mutate in enumerate(mutations):
            save = self.fixture(f"malformed-{index}")
            mutate(save)
            path = self.saves / f"malformed-{index}.json"
            persistence.atomic_json(path, save)
            originals[path] = path.read_bytes()
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.player.all_saves_uids(), ["valid-control"])
        for path, original in originals.items():
            self.assertEqual(path.read_bytes(), original)

    def test_malformed_optional_profile_picture_does_not_break_selector(self):
        save = self.fixture()
        save["userInfo"]["attr"]["profilePic"] = {"bad": "shape"}
        persistence.atomic_json(self.saves / "bad-picture.json", save)
        with redirect_stdout(io.StringIO()):
            response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.player.profile_pic("fixture-farmer"), "")

    def test_login_actual_init_postinit_and_save_reload_round_trip(self):
        path = self.write_fixture()
        with redirect_stdout(io.StringIO()):
            login = self.client.post("/", data={"UID": "fixture-farmer"})
        self.assertEqual(login.location, "/ruffle.html")
        page = self.client.get("/ruffle.html")
        self.assertEqual(page.status_code, 200)
        self.assertIn(f'src="{self.server.RUFFLE_PUBLIC_PATH}ruffle.js"'.encode(), page.data)
        response = self.gateway([
            self.command("UserService.initUser", ["Farmer", 0, True, {}], 1),
            self.command("UserService.postInit", [], 2),
            self.command("UserService.incrementActionCount", ["audit-round-trip"], 3),
        ])
        self.assertEqual(response.status_code, 200, response.data[:300])
        from pyamf import remoting
        decoded = remoting.decode(response.data)
        result = decoded.bodies[0][1].body
        self.assertEqual(len(result["data"]), 3)
        self.assertEqual(result["data"][0]["data"]["userInfo"]["player"]["userId"], "fixture-farmer")
        self.assertIn("avatarState", result["data"][1]["data"])
        self.assertIn("QuestComponent", result["data"][0]["metadata"])
        self.assertEqual(persistence.read_json(path)["userInfo"]["player"]["actionCounts"]["audit-round-trip"], 1)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.player.session("fixture-farmer")["userInfo"]["player"]["actionCounts"]["audit-round-trip"], 1)

    def test_native_health_and_unknown_village_gateway(self):
        self.assertEqual(self.client.get("/health").json["wrapper_token"], "test-instance")
        self.assertEqual(self.gateway([], uid="missing").status_code, 403)

    def test_masterysign_fallback_is_a_complete_amf3_object_after_http_gzip(self):
        import pyamf
        response = self.client.get("/masterysigns/v1/masterysign_items.amf.gz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/x-amf")
        self.assertEqual(response.headers.get("Content-Encoding"), "gzip")
        # Match the bytes exposed to the Flash URLLoader after HTTP decoding.
        payload = gzip.decompress(response.data)
        self.assertTrue(payload)
        self.assertEqual(payload[0], 0x0A)  # AMF3 Object, rather than an empty body.
        decoder = pyamf.get_decoder(pyamf.AMF3, payload)
        self.assertEqual(decoder.readElement(), {})
        self.assertEqual(decoder.stream.tell(), len(payload))

    def test_new_village_is_migrated_persisted_and_selected(self):
        # Creation is a POST from the name form; GET only shows the form (see test_minion_browser_qol).
        with redirect_stdout(io.StringIO()):
            response = self.client.post("/new.html", data={"name": "Pat"})
        self.assertEqual(response.location, "/ruffle.html")
        uids = self.player.all_saves_uids()
        self.assertEqual(len(uids), 1)
        self.assertEqual(len(list(self.saves.glob("*.json"))), 1)
        with self.client.session_transaction() as session:
            self.assertEqual(session["UID"], uids[0])
        saved = persistence.read_json(next(self.saves.glob("*.json")))
        self.assertEqual(saved["version"], "0.01a")
        self.assertEqual(saved["userInfo"]["player"]["userId"], uids[0])
        self.assertEqual(saved["userInfo"]["attr"]["name"], "Pat")
        self.assertEqual(saved["world"]["sizeX"], 50)

    def test_gateway_accepts_amf_associative_request_and_parameter_arrays(self):
        self.write_fixture()
        command = self.command("UserService.incrementActionCount")
        command["params"] = {"0": "associative"}
        response = self.gateway({"0": command})
        self.assertEqual(response.status_code, 200, response.data[:300])
        self.assertEqual(self.player.session("fixture-farmer")["userInfo"]["player"]["actionCounts"]["associative"], 1)

    def test_gateway_accepts_client_transport_metadata_after_required_fields(self):
        self.write_fixture()
        payload = self.gateway_payload(
            [self.command("UserService.incrementActionCount", ["extended-transport"])],
            transport_metadata=({"client": "FarmGame", "sequenceId": "0"}, 1),
        )
        with redirect_stdout(io.StringIO()):
            response = self.client.post("/flashservices/gateway.php", data=payload,
                                        content_type="application/x-amf")
        self.assertEqual(response.status_code, 200, response.data[:300])
        self.assertEqual(self.player.session("fixture-farmer")["userInfo"]["player"]["actionCounts"]["extended-transport"], 1)

    def test_actual_farmgame_captured_init_request_remains_compatible(self):
        self.write_fixture()
        fixture = json.loads((Path(__file__).parent / "Fixtures" / "farmgame_init_request.json").read_text())
        payload = base64.b64decode(fixture["base64"])
        from pyamf import remoting
        decoded = remoting.decode(payload)
        self.assertEqual(decoded.bodies[0][1].target, "FlashService.dispatchBatch")
        self.assertEqual(len(decoded.bodies[0][1].body), 3)
        self.assertIsInstance(decoded.bodies[0][1].body[1], dict)
        with redirect_stdout(io.StringIO()):
            response = self.client.post("/flashservices/gateway.php", data=payload,
                                        content_type="application/x-amf")
        self.assertEqual(response.status_code, 200, response.data[:300])
        result = remoting.decode(response.data).bodies[0][1].body["data"][0]["data"]
        self.assertEqual(result["userInfo"]["player"]["userId"], "fixture-farmer")

    def test_gateway_rejects_invalid_shapes_before_running_any_commands(self):
        path = self.write_fixture()
        original = path.read_bytes()
        valid = self.command("UserService.incrementActionCount", ["must-not-run"])
        for bad in (None, {}, {"params": []}, {"functionName": 10, "params": [], "sequence": 2},
                    {"functionName": "unknown", "params": "not-array", "sequence": 2}):
            with self.subTest(bad=bad):
                self.assertEqual(self.gateway([valid, bad]).status_code, 400)
        self.assertNotIn("must-not-run", self.player.session("fixture-farmer")["userInfo"]["player"]["actionCounts"])
        self.assertEqual(path.read_bytes(), original)

    def test_gateway_rejects_malformed_amf_without_mutation(self):
        path = self.write_fixture()
        original = path.read_bytes()
        for payload in (b"", b"not-amf", b"\x00\x00\x00\x00\x00\x00"):
            with self.subTest(payload=payload):
                with redirect_stdout(io.StringIO()):
                    response = self.client.post("/flashservices/gateway.php", data=payload)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(path.read_bytes(), original)

    def test_gateway_rejection_keeps_valid_calls_before_and_after_it(self):
        path = self.write_fixture()
        response = self.gateway([
            self.command("UserService.incrementActionCount", ["before-rejection"], 1),
            self.command("UserService.setActionCount", ["bad-integer", "not-a-number"], 2),
            self.command("UserService.incrementActionCount", ["after-rejection"], 3),
        ])
        results = gateway_results(self, response, [0, 29, 0])
        self.assertEqual([result["sequenceNumber"] for result in results], [1, 2, 3])
        counts = persistence.read_json(path)["userInfo"]["player"]["actionCounts"]
        self.assertEqual(counts["before-rejection"], 1)
        self.assertEqual(counts["after-rejection"], 1)
        self.assertNotIn("bad-integer", counts)
        self.assertEqual(self.player.session("fixture-farmer"), persistence.read_json(path))

    def test_snapshot_save_validation_rejects_only_its_call_in_mixed_batch(self):
        # These packets reach the real plow implementation and mutate gold,
        # XP, objects and progression before persistence notices the bad data.
        for malformed in ({"className": None}, {"clientPayload": float("nan")},
                          {"clientPayload": datetime(2026, 10, 23)}):
            with self.subTest(malformed=malformed):
                path = self.write_fixture()
                expected = copy.deepcopy(self.player.session("fixture-farmer"))
                snapshot = {"id": 999, "className": "Plot", "itemName": None,
                    "state": "plowed", "plantTime": 0, "position": {"x": 0, "y": 0, "z": 0},
                    **malformed}
                response = self.gateway([
                    self.command("UserService.incrementActionCount", ["before-rejection"], 1),
                    self.command("WorldService.performAction", ["plow", snapshot, []], 2),
                    self.command("UserService.incrementActionCount", ["after-rejection"], 3),
                ])
                gateway_results(self, response, [0, 29, 0])
                expected["userInfo"]["player"]["actionCounts"].update({"before-rejection": 1, "after-rejection": 1})
                self.assertEqual(self.player.session("fixture-farmer"), expected)
                self.assertEqual(persistence.read_json(path), expected)

    def test_neighbor_serialization_validation_occurs_after_its_last_mutation(self):
        first = self.write_fixture()
        second = self.write_fixture("neighbor-export.json", "neighbor")
        expected = copy.deepcopy(self.player.session("fixture-farmer"))
        original_neighbor = second.read_bytes()
        def corrupt_after_stage(uid, host, action, snapshot):
            self.player.save_session(host)
            self.player.session(host)["world"]["objectsArray"][0]["clientPayload"] = float("nan")
        obj = copy.deepcopy(self.player.session("neighbor")["world"]["objectsArray"][0])
        with mock.patch.object(self.server.commands, "neighbor_act", side_effect=corrupt_after_stage):
            response = self.gateway([
                self.command("UserService.incrementActionCount", ["before-rejection"], 1),
                self.command("WorldService.performAction", ["neighborAct", obj,
                    [{"hostId": "neighbor", "actionType": "plow"}]], 2),
                self.command("UserService.incrementActionCount", ["after-rejection"], 3),
            ])
        gateway_results(self, response, [0, 29, 0])
        expected["userInfo"]["player"]["actionCounts"].update({"before-rejection": 1, "after-rejection": 1})
        self.assertEqual(persistence.read_json(first), expected)
        self.assertEqual(second.read_bytes(), original_neighbor)
        self.assertEqual(self.player.session("neighbor"), persistence.read_json(second))

    def test_rejected_neighbor_call_restores_both_farms_and_pending_writes(self):
        first = self.write_fixture()
        second = self.write_fixture("neighbor-export.json", "neighbor")
        original_neighbor = second.read_bytes()
        before = copy.deepcopy(self.player.session("fixture-farmer"))
        def fail_neighbor(uid, host, action, snapshot):
            self.player.session(uid)["userInfo"]["player"]["gold"] -= 100
            self.player.session(host)["world"]["objectsArray"][0]["partialNeighborMutation"] = True
            self.player.save_session(host)
            raise ValueError("Rejected after updating both farms")
        obj = copy.deepcopy(self.player.session("neighbor")["world"]["objectsArray"][0])
        with mock.patch.object(self.server.commands, "neighbor_act", side_effect=fail_neighbor):
            response = self.gateway([
                self.command("UserService.incrementActionCount", ["before-rejection"], 1),
                self.command("WorldService.performAction", ["neighborAct", obj,
                    [{"hostId": "neighbor", "actionType": "plow"}]], 2),
                self.command("UserService.incrementActionCount", ["after-rejection"], 3),
            ])
        gateway_results(self, response, [0, 29, 0])
        before["userInfo"]["player"]["actionCounts"].update({"before-rejection": 1, "after-rejection": 1})
        self.assertEqual(persistence.read_json(first), before)
        self.assertEqual(self.player.session("fixture-farmer"), before)
        self.assertEqual(second.read_bytes(), original_neighbor)
        self.assertEqual(self.player.session("neighbor"), persistence.read_json(second))

    def test_retry_of_mixed_batch_charges_successful_plows_once(self):
        import constants
        path = self.write_fixture()
        save = self.player.session("fixture-farmer")
        save["world"]["objectsArray"] = []
        gold = save["userInfo"]["player"]["gold"]
        xp = save["userInfo"]["player"]["xp"]
        def plow(temporary, position, sequence):
            return self.command("WorldService.performAction", ["plow", {
                "id": temporary, "className": "Plot", "itemName": None,
                "state": "plowed", "plantTime": 0,
                "position": {"x": position, "y": 0, "z": 0}}, []], sequence)
        requests = [plow(constants.TEMP_ID_START, 0, 1),
                    self.command("UserService.setActionCount", ["bad", "not-a-number"], 2),
                    plow(constants.TEMP_ID_START + 1, 4, 3)]
        first = gateway_results(self, self.gateway(requests), [0, 29, 0])
        retry = gateway_results(self, self.gateway(requests), [0, 29, 0])
        self.assertEqual([result.get("id") for result in first], [result.get("id") for result in retry])
        saved = persistence.read_json(path)
        self.assertEqual(len(saved["world"]["objectsArray"]), 2)
        self.assertEqual(saved["userInfo"]["player"]["gold"], gold - 30)
        self.assertEqual(saved["userInfo"]["player"]["xp"], xp + 2)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.player.session("fixture-farmer"), saved)

    def test_accepted_result_does_not_leak_following_rejected_mutations(self):
        self.write_fixture()
        def fail_count(uid, action, value):
            self.player.session(uid)["userInfo"]["player"]["gold"] = -999
            raise ValueError("Rejected after mutating player")
        with mock.patch.object(self.server.commands, "init_user", side_effect=self.player.session), \
                mock.patch.object(self.server.commands, "set_action_count", side_effect=fail_count):
            response = self.gateway([
                self.command("UserService.initUser", ["QA", 0, True, None], 1),
                self.command("UserService.setActionCount", ["bad", 1], 2),
            ])
        results = gateway_results(self, response, [0, 29])
        self.assertEqual(results[0]["data"]["userInfo"]["player"]["gold"],
                         self.player.session("fixture-farmer")["userInfo"]["player"]["gold"])
        self.assertNotEqual(results[0]["data"]["userInfo"]["player"]["gold"], -999)

    def test_failed_gateway_save_restores_in_memory_farm(self):
        path = self.write_fixture()
        original = path.read_bytes()
        with mock.patch.object(self.server, "save_session", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.gateway([self.command("UserService.incrementActionCount", ["must-roll-back"])])
        self.assertNotIn("must-roll-back", self.player.session("fixture-farmer")["userInfo"]["player"]["actionCounts"])
        self.assertEqual(path.read_bytes(), original)

    def fail_commit_sync_once(self):
        actual_sync = persistence._sync_directory
        failed = False
        def sync(directory):
            nonlocal failed
            manifest = Path(directory) / "manifest.json"
            if manifest.exists() and persistence.read_json(manifest)["state"] == "committed" and not failed:
                failed = True
                raise OSError("commit directory sync failed")
            return actual_sync(directory)
        return mock.patch("persistence._sync_directory", side_effect=sync)

    def test_gateway_post_commit_failure_keeps_memory_matching_disk(self):
        path = self.write_fixture()
        with self.fail_commit_sync_once():
            with self.assertRaises(persistence.CommittedSaveError):
                self.gateway([self.command("UserService.incrementActionCount", ["committed"])])
        self.assertEqual(self.player.session("fixture-farmer")["userInfo"]["player"]["actionCounts"]["committed"], 1)
        self.assertEqual(persistence.read_json(path)["userInfo"]["player"]["actionCounts"]["committed"], 1)

    def test_new_village_post_commit_failure_keeps_persisted_registry_entry(self):
        with self.fail_commit_sync_once(), redirect_stdout(io.StringIO()):
            with self.assertRaises(persistence.CommittedSaveError):
                self.player.new_village()
        uids = self.player.all_saves_uids()
        self.assertEqual(len(uids), 1)
        self.assertEqual(persistence.read_json(next(self.saves.glob("*.json")))["userInfo"]["player"]["userId"], uids[0])

    def test_rejection_after_neighbor_action_keeps_both_farms_committed(self):
        first = self.write_fixture()
        second = self.write_fixture("neighbor-export.json", "neighbor")
        gold_before = self.player.session("fixture-farmer")["userInfo"]["player"]["gold"]
        # Exercise the real neighbor gateway branch, which saves the host
        # within the visitor's batch, before the following command fails.
        obj = copy.deepcopy(self.player.session("neighbor")["world"]["objectsArray"][0])
        obj["auditMarker"] = "committed"
        response = self.gateway([
            self.command("WorldService.performAction", ["neighborAct", obj, [{"hostId": "neighbor", "actionType": "plow"}]], 1),
            self.command("UserService.setActionCount", ["bad", "not-an-integer"], 2),
        ])
        gateway_results(self, response, [0, 29])
        self.assertEqual(persistence.read_json(second)["world"]["objectsArray"][0]["auditMarker"], "committed")
        self.assertGreater(persistence.read_json(first)["userInfo"]["player"]["gold"], gold_before)

    def test_neighbor_batch_commits_both_farms(self):
        first = self.write_fixture()
        second = self.write_fixture("neighbor-export.json", "neighbor")
        gold_before = self.player.session("fixture-farmer")["userInfo"]["player"]["gold"]
        obj = copy.deepcopy(self.player.session("neighbor")["world"]["objectsArray"][0])
        obj["auditMarker"] = "committed"
        response = self.gateway([
            self.command("WorldService.performAction", ["neighborAct", obj, [{"hostId": "neighbor", "actionType": "plow"}]]),
        ])
        self.assertEqual(response.status_code, 200, response.data[:300])
        self.assertEqual(persistence.read_json(second)["world"]["objectsArray"][0]["auditMarker"], "committed")
        self.assertGreater(persistence.read_json(first)["userInfo"]["player"]["gold"], gold_before)

    def test_failed_response_encoding_never_commits_farm(self):
        from pyamf import remoting
        path = self.write_fixture()
        original = path.read_bytes()
        actual_encode = remoting.encode
        def fail_response(envelope, *args, **kwargs):
            if isinstance(envelope.bodies[0][1], remoting.Response):
                raise ValueError("response cannot be encoded")
            return actual_encode(envelope, *args, **kwargs)
        with mock.patch.object(self.server.remoting, "encode", side_effect=fail_response):
            response = self.gateway([self.command("UserService.incrementActionCount", ["must-roll-back"])])
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("must-roll-back", self.player.session("fixture-farmer")["userInfo"]["player"]["actionCounts"])
        self.assertEqual(path.read_bytes(), original)

    def test_concurrent_gateway_requests_do_not_lose_updates(self):
        path = self.write_fixture()
        # Each actual game client encodes independently in its own runtime.
        # PyAMF's shared optional-XML import initialization is not thread safe;
        # prepare bytes first, then exercise real concurrent Flask requests.
        payloads = [self.gateway_payload([self.command("UserService.incrementActionCount", ["parallel"], index)])
                    for index in range(30)]
        def increment(index):
            client = self.server.app.test_client()
            return client.post("/flashservices/gateway.php", data=payloads[index],
                               content_type="application/x-amf").status_code
        with redirect_stdout(io.StringIO()):
            with ThreadPoolExecutor(max_workers=8) as executor:
                statuses = list(executor.map(increment, range(30)))
        self.assertEqual(statuses, [200] * 30)
        self.assertEqual(persistence.read_json(path)["userInfo"]["player"]["actionCounts"]["parallel"], 30)


if __name__ == "__main__":
    unittest.main()
