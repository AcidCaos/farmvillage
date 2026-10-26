"""Native launcher API checks using real journals and exclusively temporary farms."""

import copy
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "macOS/Runtime"))

from flask import Flask
from native_launcher import register_launcher
from persistence import CommittedSaveError, commit_json_batch, decode_json


def farm(uid="imported-farm", name="Imported farmer"):
    return {"userInfo": {"player": {"userId": uid, "gold": 200, "xp": 0},
                         "attr": {"name": name}}, "world": {"objectsArray": []},
            "unknown": {"preserve": [1, "original", True]}}


class FixturePlayer:
    """The adapter's player contract, retaining real filesystem transactions."""
    def __init__(self, root):
        self.saves = root / "saves"
        self.farms = {}
        self.static_uids = {"static-neighbor"}
        self.create_error = None
        self.migrate_identity = False

    def all_saves_uids(self):
        return list(self.farms)

    def all_uids(self):
        return list(self.static_uids) + self.all_saves_uids()

    def save_info(self, uid):
        save = self.farms[uid]
        return {"uid": uid, "name": save["userInfo"]["attr"]["name"], "xp": 0}

    def _validate_save(self, value, ready=False):
        if not isinstance(value, dict):
            raise ValueError("The save is not an object.")
        uid = value.get("userInfo", {}).get("player", {}).get("userId")
        if not isinstance(uid, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", uid):
            raise ValueError("The village UID is invalid.")
        if not isinstance(value.get("world", {}).get("objectsArray"), list):
            raise ValueError("The world is missing.")
        if ready and value.get("migration") != "ready":
            raise ValueError("The farm is not ready.")
        return uid

    def migrate_loaded_save(self, value):
        value["migration"] = "ready"
        if self.migrate_identity:
            value["userInfo"]["player"]["userId"] = "changed-identity"

    def _save_contents(self, value):
        return copy.deepcopy(value)

    def load_saves(self):
        self.farms = {}
        for file in self.saves.glob("*.save.json"):
            self.farms[self._validate_save(decode_json(file.read_bytes()), ready=True)] = decode_json(file.read_bytes())

    def new_village(self, name):
        if self.create_error == "before":
            raise OSError("Simulated precommit failure")
        uid = str(uuid.uuid4())
        save = farm(uid, name.strip())
        self.migrate_loaded_save(save)
        commit_json_batch(self.saves, {self.saves / (uid + ".save.json"): save}, indent=4)
        self.farms[uid] = save
        if self.create_error == "committed":
            raise CommittedSaveError("Simulated postcommit durability failure")
        return uid


class NativeLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="farmvillage-launcher-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.player = FixturePlayer(self.root)
        self.app = Flask("native_launcher_tests")
        self.app.config.update(TESTING=True)
        self.app.logger.disabled = True
        with mock.patch.dict(os.environ, {"FARMVILLAGE_INSTANCE_TOKEN": "owned-audit-token"}):
            register_launcher(self.app, player_module=self.player, bundle_module=SimpleNamespace(DATA_DIR=str(self.root)))
        self.client = self.app.test_client()
        self.headers = {"X-FarmVillage-Token": "owned-audit-token"}

    def import_save(self, value=None, raw=None, headers=None):
        return self.client.post("/launcher/import", data=raw if raw is not None else json.dumps(value or farm()),
                                headers=self.headers if headers is None else headers, content_type="application/json")

    def test_create_requires_exact_owned_token_and_rejects_nonascii_without_error(self):
        for token in ("", "another-session", "caf\u00e9"):
            response = self.client.post("/launcher/create", json={"name": "Farmer"}, headers={"X-FarmVillage-Token": token})
            self.assertEqual(response.status_code, 403)
        self.assertFalse(self.player.farms)
        self.assertFalse((self.root / "saves").exists())

    def test_create_validates_name_and_request_size_before_writing(self):
        for name in (None, "", "  ", "x" * 81, 42):
            response = self.client.post("/launcher/create", json={"name": name}, headers=self.headers)
            self.assertEqual(response.status_code, 400)
        response = self.client.post("/launcher/create", data=b"x" * 4097, headers=self.headers, content_type="application/json")
        self.assertEqual(response.status_code, 413)
        self.assertFalse(self.player.farms)

    def test_create_commits_selected_name_and_preserves_existing_farm(self):
        previous = self.client.post("/launcher/create", json={"name": "First"}, headers=self.headers).get_json()
        previous_save = copy.deepcopy(self.player.farms[previous["uid"]])
        response = self.client.post("/launcher/create", json={"name": "  Second  "}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertTrue(result["committed"])
        self.assertTrue(result["durabilityConfirmed"])
        self.assertEqual(result["farm"]["name"], "Second")
        self.assertEqual(self.player.farms[previous["uid"]], previous_save)
        self.assertEqual(len(list((self.root / "saves").glob("*.save.json"))), 2)

    def test_create_committed_durability_error_returns_actual_uid_and_warning(self):
        self.player.create_error = "committed"
        response = self.client.post("/launcher/create", json={"name": "Saved once"}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertEqual(result["uid"], self.player.all_saves_uids()[0])
        self.assertTrue(result["committed"])
        self.assertFalse(result["durabilityConfirmed"])
        self.assertIn("Do not create it again", result["warning"])
        self.assertEqual(len(self.player.farms), 1)

    def test_precommit_create_failure_never_reports_success(self):
        self.player.create_error = "before"
        response = self.client.post("/launcher/create", json={"name": "No save"}, headers=self.headers)
        self.assertEqual(response.status_code, 500)
        self.assertFalse(self.player.farms)

    def test_import_migrates_detached_copy_and_keeps_exact_original_backup(self):
        original = b' {"unknown":{"keep":true},"userInfo":{"player":{"userId":"imported-farm","gold":200,"xp":0},"attr":{"name":"Original"}},"world":{"objectsArray":[]}}\n'
        response = self.import_save(raw=original)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        result = response.get_json()
        self.assertEqual(result["uid"], "imported-farm")
        self.assertTrue(result["durabilityConfirmed"])
        saved = decode_json((self.root / "saves/imported-farm.save.json").read_bytes())
        self.assertEqual(saved["migration"], "ready")
        self.assertEqual(saved["unknown"], {"keep": True})
        backups = list((self.root / "saves/.import-backups").glob("*.original"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)

    def test_import_rejects_existing_saved_or_static_identity(self):
        self.assertEqual(self.import_save().status_code, 200)
        original = (self.root / "saves/imported-farm.save.json").read_bytes()
        for uid in ("imported-farm", "static-neighbor"):
            response = self.import_save(farm(uid))
            self.assertEqual(response.status_code, 409)
        self.assertEqual((self.root / "saves/imported-farm.save.json").read_bytes(), original)
        self.assertEqual(len(list((self.root / "saves/.import-backups").glob("*.original"))), 1)

    def test_import_detects_duplicate_legacy_filenames_outside_registry(self):
        saves = self.root / "saves"
        saves.mkdir()
        for name in ("legacy-one.json", "legacy-two.json"):
            (saves / name).write_text(json.dumps(farm()))
        before = {path.name: path.read_bytes() for path in saves.iterdir()}
        self.assertEqual(self.import_save().status_code, 409)
        self.assertEqual({path.name: path.read_bytes() for path in saves.iterdir()}, before)

    def test_import_ignores_nonfarm_backup_files_consistently_with_game_loader(self):
        saves = self.root / "saves"
        saves.mkdir()
        for ending in ("bak", "backup", "tmp"):
            (saves / ("old." + ending + ".json")).write_text(json.dumps(farm()))
        self.assertEqual(self.import_save().status_code, 200)

    def test_import_invalid_json_nonfinite_identity_and_schema_never_write(self):
        for raw in (b"not json", b"[]", b'{"x":NaN}', json.dumps(farm("../escape")).encode(), b'{"userInfo":{}}'):
            response = self.import_save(raw=raw)
            self.assertEqual(response.status_code, 400)
        self.assertFalse((self.root / "saves").exists())

    def test_import_migration_cannot_change_identity(self):
        self.player.migrate_identity = True
        self.assertEqual(self.import_save().status_code, 400)
        self.assertFalse((self.root / "saves/.import-backups").exists())
        self.assertFalse(list((self.root / "saves").glob("*.save.json")))

    def test_import_rejects_symlinked_backups_without_external_writes(self):
        with tempfile.TemporaryDirectory(prefix="farmvillage-launcher-outside-") as outside:
            saves = self.root / "saves"
            saves.mkdir()
            (saves / ".import-backups").symlink_to(outside, target_is_directory=True)
            self.assertEqual(self.import_save().status_code, 400)
            self.assertEqual(list(Path(outside).iterdir()), [])
            self.assertFalse(list(saves.glob("*.save.json")))

    def test_import_body_limit_and_auth_fail_before_filesystem_changes(self):
        response = self.import_save(headers={"X-FarmVillage-Token": "wrong-session"})
        self.assertEqual(response.status_code, 403)
        response = self.client.post("/launcher/import", data=b"{}", content_type="application/json",
                                    headers=self.headers,
                                    environ_overrides={"CONTENT_LENGTH": str(64 * 1024 * 1024 + 1)})
        self.assertEqual(response.status_code, 413)
        self.assertFalse((self.root / "saves").exists())

    def test_failed_import_commit_preserves_exact_backup_and_no_partial_farm(self):
        original = json.dumps(farm()).encode()
        replace = os.replace
        def fail_farm_publication(source, destination):
            if Path(destination).name == "imported-farm.save.json":
                raise OSError("Simulated farm publication failure")
            return replace(source, destination)
        with mock.patch("persistence.os.replace", side_effect=fail_farm_publication):
            response = self.import_save(raw=original)
        self.assertEqual(response.status_code, 500)
        self.assertFalse(self.player.farms)
        self.assertFalse((self.root / "saves/imported-farm.save.json").exists())
        backups = list((self.root / "saves/.import-backups").glob("*.original"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
