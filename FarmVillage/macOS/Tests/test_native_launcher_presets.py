"""Native creation styles follow the owned runtime's accepted preset availability.

These checks use the existing temporary journal fixture; no game server socket,
application profile, browser or native application is opened.
"""
import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_native_launcher as fixtures


class NativeLauncherPresetTests(unittest.TestCase):
    setUp = fixtures.NativeLauncherTests.setUp

    def october(self, available):
        self.player.october_village = SimpleNamespace(
            AVAILABLE=available, PRESET="quintessential_october",
            DISPLAY_NAME="Quintessential October")

    def presets(self, headers=None):
        return self.client.get("/launcher/presets", headers=self.headers if headers is None else headers)

    def test_style_discovery_requires_the_owned_token_without_reading_farms(self):
        with mock.patch.object(self.player, "all_saves_uids", side_effect=AssertionError("Unexpected save access")):
            for token in ("", "another-session", "caf\u00e9"):
                with self.subTest(token=token):
                    self.assertEqual(self.presets({"X-FarmVillage-Token": token}).status_code, 403)
            response = self.presets()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"presets": [{"id": "classic", "name": "Classic farm"}]})
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertFalse((self.root / "saves").exists())

    def test_october_is_advertised_only_while_the_canonical_module_admits_it(self):
        self.october(False)
        self.assertEqual([p["id"] for p in self.presets().get_json()["presets"]], ["classic"])
        self.player.october_village.AVAILABLE = True
        self.assertEqual(self.presets().get_json()["presets"], [
            {"id": "classic", "name": "Classic farm"},
            {"id": "quintessential_october", "name": "Quintessential October"}])
        self.player.october_village.AVAILABLE = False
        self.assertEqual([p["id"] for p in self.presets().get_json()["presets"]], ["classic"])
        self.assertFalse(self.player.farms)

    def test_default_and_explicit_classic_keep_the_original_name_only_call(self):
        with mock.patch.object(self.player, "new_village", wraps=self.player.new_village) as create:
            for payload in ({"name": "First"}, {"name": "Second", "preset": "classic"}):
                with self.subTest(payload=payload):
                    response = self.client.post("/launcher/create", json=payload, headers=self.headers)
                    self.assertEqual(response.status_code, 200)
                    create.assert_called_with(name=payload["name"])
        self.assertEqual(len(self.player.farms), 2)

    def test_unavailable_unknown_and_malformed_presets_preserve_existing_farms(self):
        self.october(False)
        self.assertEqual(self.client.post("/launcher/create", json={"name": "Keep"}, headers=self.headers).status_code, 200)
        before = copy.deepcopy(self.player.farms)
        files = {path: path.read_bytes() for path in (self.root / "saves").rglob("*") if path.is_file()}
        for preset in (None, False, 0, [], {}, "unknown", "quintessential_october"):
            with self.subTest(preset=preset), mock.patch.object(self.player, "new_village") as create:
                response = self.client.post("/launcher/create", json={"name": "Refused", "preset": preset}, headers=self.headers)
                self.assertEqual(response.status_code, 400)
                create.assert_not_called()
                self.assertEqual(self.player.farms, before)
                self.assertEqual({path: path.read_bytes() for path in (self.root / "saves").rglob("*") if path.is_file()}, files)

    def test_accepted_october_is_forwarded_without_changing_classic_or_import_state(self):
        self.october(True)
        create_classic = self.player.new_village
        selected = []

        def create(name, *, preset):
            selected.append(preset)
            return create_classic(name)

        with mock.patch.object(self.player, "new_village", side_effect=create):
            response = self.client.post("/launcher/create", json={
                "name": "October", "preset": "quintessential_october"}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(selected, ["quintessential_october"])
        self.assertEqual(response.get_json()["farm"]["name"], "October")
        self.assertTrue(response.get_json()["committed"])
        self.assertEqual(len(self.player.farms), 1)

    def test_accepted_preset_keeps_postcommit_durability_warning_contract(self):
        self.october(True)
        self.player.create_error = "committed"
        create_classic = self.player.new_village
        with mock.patch.object(self.player, "new_village", side_effect=lambda name, preset: create_classic(name)):
            response = self.client.post("/launcher/create", json={
                "name": "Saved once", "preset": "quintessential_october"}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        value = response.get_json()
        self.assertTrue(value["committed"])
        self.assertFalse(value["durabilityConfirmed"])
        self.assertIn("Do not create it again", value["warning"])
        self.assertEqual(len(self.player.farms), 1)


if __name__ == "__main__":
    unittest.main()
