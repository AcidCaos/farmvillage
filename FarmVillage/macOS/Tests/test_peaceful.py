"""Real catalog/AMF checks for persistent ripe-and-waiting crops."""

import copy
import json
from pathlib import Path
from contextlib import redirect_stdout
import io
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import peaceful


class PeacefulTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.RuntimeFixtureTests.setUpClass()

    def setUp(self):
        self.save = copy.deepcopy(fixtures.RuntimeFixtureTests.initial)
        import items
        self.item = items.get_item_by_name("strawberry")
        self.now = 2_000_000_000
        self.grow = peaceful.grow_seconds(self.item)

    def plot(self, age, state="planted"):
        obj = {"className": "Plot", "id": 99, "itemName": "strawberry", "state": state,
               "plantTime": (self.now - age) * 1000, "position": {"x": 0, "y": 0, "z": 0}}
        self.save["world"]["objectsArray"] = [obj]
        return obj

    def test_new_crop_keeps_real_growth_timer(self):
        obj = self.plot(self.grow / 2)
        original = obj["plantTime"]
        peaceful.refresh(self.save, self.now)
        self.assertEqual(obj["state"], "planted")
        self.assertEqual(obj["plantTime"], original)
        self.assertFalse(self.save["witherOn"]["farm"])

    def test_months_away_mature_without_withering_or_rebasing(self):
        obj = self.plot(90 * 86400)
        original = obj["plantTime"]
        peaceful.refresh(self.save, self.now)
        self.assertEqual(obj["state"], "grown")
        self.assertEqual(obj["plantTime"], original)
        restarted = json.loads(json.dumps(self.save))
        peaceful.refresh(restarted, self.now + 365 * 86400)
        self.assertEqual(restarted["world"]["objectsArray"][0]["state"], "grown")
        self.assertEqual(restarted["peacefulMode"]["policy"], "ripe_and_waiting")

    def test_existing_withered_crop_revives_and_ripe_stays_ripe(self):
        obj = self.plot(20 * self.grow, "withered")
        peaceful.refresh(self.save, self.now)
        self.assertEqual(obj["state"], "grown")
        self.assertFalse(peaceful.refresh(self.save, self.now + self.grow * 100))

    def test_fallow_empty_and_unknown_items_are_preserved(self):
        obj = self.plot(100 * self.grow, "fallow")
        other = dict(obj, id=100, state="withered", itemName="unknown_future_crop")
        self.save["world"]["objectsArray"].append(other)
        originals = copy.deepcopy(self.save["world"]["objectsArray"])
        peaceful.refresh(self.save, self.now)
        self.assertEqual(self.save["world"]["objectsArray"], originals)

    def test_turning_off_restores_policy_and_gives_ripe_crop_full_window(self):
        self.save["witherOn"] = {"farm": True, "england": False}
        obj = self.plot(90 * 86400)
        peaceful.refresh(self.save, self.now)
        peaceful.set_enabled(self.save, False, self.now)
        self.assertFalse(peaceful.enabled(self.save))
        self.assertEqual(self.save["witherOn"], {"farm": True, "england": False})
        self.assertEqual(obj["plantTime"], (self.now - self.grow) * 1000)
        self.assertFalse(peaceful.refresh(self.save, self.now + 86400))
        peaceful.set_enabled(self.save, True, self.now + 86400)
        self.assertFalse(self.save["witherOn"]["farm"])

    def test_nonboolean_toggle_rejected(self):
        for value in (0, 1, "false", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                peaceful.set_enabled(self.save, value, self.now)

    def test_repeated_off_toggle_preserves_original_world_flags_and_timestamps(self):
        self.save["witherOn"] = {"farm": True, "england": False, "unknown_world": True}
        obj = self.plot(90 * 86400)
        obj["futureMetadata"] = {"preserve": [1, 2, 3]}
        peaceful.set_enabled(self.save, True, self.now)
        self.save["peacefulMode"]["unknownSetting"] = "keep me"
        peaceful.set_enabled(self.save, False, self.now)
        snapshot = copy.deepcopy(self.save)
        peaceful.set_enabled(self.save, False, self.now + 86400)
        self.assertEqual(self.save, snapshot)
        self.assertEqual(self.save["witherOn"], {"farm": True, "england": False, "unknown_world": True})

    def test_off_on_cycles_restore_latest_world_flags_and_preserve_unknown_fields(self):
        self.save["witherOn"] = {"farm": True, "england": False}
        obj = self.plot(self.grow / 2)
        obj["futureMetadata"] = {"preserve": True}
        plant_time = obj["plantTime"]
        peaceful.set_enabled(self.save, True, self.now)
        peaceful.set_enabled(self.save, False, self.now)
        self.save["witherOn"]["future_world"] = True
        peaceful.set_enabled(self.save, True, self.now)
        peaceful.set_enabled(self.save, False, self.now)
        self.assertEqual(self.save["witherOn"], {"farm": True, "england": False, "future_world": True})
        self.assertEqual(obj["plantTime"], plant_time)
        self.assertEqual(obj["futureMetadata"], {"preserve": True})


class PeacefulGatewayTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    def test_login_reload_uses_real_client_controls_and_saved_state(self):
        path = self.write_fixture()
        save = self.player.session("fixture-farmer")
        plot = next(obj for obj in save["world"]["objectsArray"] if obj.get("className") == "Plot")
        plot.update(itemName="strawberry", state="withered", plantTime=1000)
        response = self.gateway([self.command("UserService.initUser", ["Farmer", 0, True, True])])
        self.assertEqual(response.status_code, 200)
        persisted = json.loads(path.read_text())
        self.assertEqual(next(obj for obj in persisted["world"]["objectsArray"] if obj["id"] == plot["id"])["state"], "grown")
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        with self.client.session_transaction() as browser:
            browser["UID"] = "fixture-farmer"
        html = self.client.get("/ruffle.html").get_data(as_text=True)
        self.assertIn("&disallowWither=1", html)
        self.assertFalse(self.player.session("fixture-farmer")["witherOn"]["farm"])
