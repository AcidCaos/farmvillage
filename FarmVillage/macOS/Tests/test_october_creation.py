"""October's normal creation flow, using only disposable profiles."""
import copy
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures  # Own data roots before any product import.
import october_village


class OctoberCreationTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture

    def post(self, **fields):
        with redirect_stdout(io.StringIO()):
            return self.client.post("/new.html", data={"name": "October QA", **fields})

    def test_choice_is_hidden_until_scene_acceptance_and_get_creates_nothing(self):
        with mock.patch.object(october_village, "AVAILABLE", False):
            response = self.client.get("/new.html")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('id="preset"', response.get_data(as_text=True))
        self.assertEqual(self.player.all_saves_uids(), [])
        with mock.patch.object(october_village, "AVAILABLE", True):
            response = self.client.get("/new.html")
        self.assertIn('value="quintessential_october"', response.get_data(as_text=True))
        self.assertEqual(self.player.all_saves_uids(), [])

    def test_unavailable_and_unknown_presets_preserve_existing_farm_and_selection(self):
        path = self.write_fixture()
        before = path.read_bytes()
        with self.client.session_transaction() as session:
            session["UID"] = "fixture-farmer"
        with mock.patch.object(october_village, "AVAILABLE", False):
            for preset in (october_village.PRESET, "unrecognized"):
                self.assertEqual(self.post(preset=preset).status_code, 400)
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(self.player.all_saves_uids(), ["fixture-farmer"])
                with self.client.session_transaction() as session:
                    self.assertEqual(session["UID"], "fixture-farmer")

    def test_new_preset_uses_normal_save_and_keeps_original_starter_and_balances(self):
        with mock.patch.object(october_village, "AVAILABLE", True), \
                mock.patch.object(self.player, "timestamp_now", return_value=1800000000):
            classic_response = self.post(name="Classic QA")
            classic_uid = self.player.all_saves_uids()[0]
            classic = copy.deepcopy(self.player.session(classic_uid))
            response = self.post(preset=october_village.PRESET)
        self.assertEqual(classic_response.status_code, 302)
        self.assertEqual(response.location, "/ruffle.html")
        with self.client.session_transaction() as session:
            uid = session["UID"]
        self.assertNotEqual(uid, classic_uid)
        saved = self.player.session(uid)
        self.assertEqual(saved["userInfo"]["currentWorldType"], "farm")
        self.assertEqual((saved["world"]["sizeX"], saved["world"]["sizeY"]), (50, 50))
        for key in ("gold", "cash", "xp", "energy", "storageData"):
            self.assertEqual(saved["userInfo"]["player"][key], classic["userInfo"]["player"][key])
        old_objects = {obj["id"]: obj for obj in classic["world"]["objectsArray"]}
        new_objects = {obj["id"]: obj for obj in saved["world"]["objectsArray"]}
        for identity, obj in old_objects.items():
            self.assertEqual(new_objects[identity], obj)
        self.assertGreater(len(new_objects), len(old_objects))
        self.assertIn(october_village.STATE_KEY, saved)
        self.assertEqual(self.player.session(classic_uid), classic)

    def test_reload_keeps_authored_scene_and_earned_changes_without_reapplying_starter(self):
        with mock.patch.object(october_village, "AVAILABLE", True):
            self.assertEqual(self.post(preset=october_village.PRESET).status_code, 302)
        uid = self.player.all_saves_uids()[0]
        saved = self.player.session(uid)
        saved["userInfo"]["player"]["gold"] += 123
        decoration = next(obj for obj in saved["world"]["objectsArray"] if obj["id"] > 7)
        decoration["position"]["x"] += 1
        with redirect_stdout(io.StringIO()):
            self.player.save_session(uid)
        before = copy.deepcopy(self.player.session(uid))
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.player.session(uid), before)

    def test_private_provenance_is_saved_but_not_sent_in_init_response(self):
        with mock.patch.object(october_village, "AVAILABLE", True):
            self.assertEqual(self.post(preset=october_village.PRESET).status_code, 302)
        uid = self.player.all_saves_uids()[0]
        import commands
        with redirect_stdout(io.StringIO()):
            response = commands.init_user(uid)
        self.assertNotIn(october_village.STATE_KEY, response)
        self.assertIn(october_village.STATE_KEY, self.player.session(uid))

    def test_classic_creation_keeps_the_existing_default(self):
        response = self.post()
        self.assertEqual(response.status_code, 302)
        saved = self.player.session(self.player.all_saves_uids()[0])
        self.assertNotIn(october_village.STATE_KEY, saved)
        self.assertEqual(len(saved["world"]["objectsArray"]), 7)
