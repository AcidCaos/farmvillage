"""All original level boundaries, exercised through real saved farm actions.

This audits XP/reward progression. It does not certify every catalog feature or
represent a browser playthrough of one hundred levels.
"""
from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import constants
import engine
import game_settings


class LevelProgressionMatrixTests(unittest.TestCase):
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    @classmethod
    def setUpClass(cls):
        fixtures.RuntimeFixtureTests.setUpClass.__func__(cls)
        root = Path(__file__).resolve().parents[2]
        settings = ET.fromstring(zlib.decompress(
            (root / "xml/gz/v855098/gameSettings.xml.gz").read_bytes()))
        cls.thresholds = {int(row.get("num")): int(row.get("requiredXP"))
                          for row in settings.find("levels")}

    def test_every_archived_level_boundary_1_through_100(self):
        self.assertTrue(set(range(1, 101)).issubset(self.thresholds))
        for level in range(1, 101):
            with self.subTest(level=level):
                threshold = self.thresholds[level]
                self.assertEqual(game_settings.level_to_xp(level), threshold)
                self.assertEqual(game_settings.xp_to_level(threshold), level)
                if level > 1:
                    self.assertEqual(game_settings.xp_to_level(threshold - 1), level - 1)
                if level < 100:
                    self.assertEqual(game_settings.xp_to_level(self.thresholds[level + 1] - 1), level)

    def test_all_99_level_ups_charge_plow_once_award_once_and_survive_reload(self):
        path = self.write_fixture()
        for level in range(2, 101):
            with self.subTest(level=level), redirect_stdout(io.StringIO()):
                save = self.player.session("fixture-farmer")
                save["world"]["objectsArray"] = []
                save["userInfo"]["player"].update(
                    xp=self.thresholds[level] - 1, gold=1000, cash=10)
                self.player.save_session("fixture-farmer")
                plot = {"id": constants.TEMP_ID_START, "className": "Plot",
                        "itemName": None, "state": "plowed", "plantTime": 0,
                        "position": {"x": 10, "y": 10, "z": 0}}
                action = self.command("WorldService.performAction",
                                      ["plow", copy.deepcopy(plot), []], level * 2)
                fixtures.gateway_results(self, self.gateway([action]), [0])
                saved = json.loads(path.read_text())
                expected = (self.thresholds[level], 985, 11)
                self.assertEqual(tuple(saved["userInfo"]["player"][key]
                                       for key in ("xp", "gold", "cash")), expected)
                before = path.read_bytes()
                fixtures.gateway_results(self, self.gateway([action]), [0])
                self.assertEqual(path.read_bytes(), before)
                self.player.load_saves()
                reloaded = self.player.session("fixture-farmer")
                self.assertEqual(tuple(reloaded["userInfo"]["player"][key]
                                       for key in ("xp", "gold", "cash")), expected)
                self.assertEqual(game_settings.xp_to_level(
                    reloaded["userInfo"]["player"]["xp"]), level)

    def test_crossing_many_levels_pays_every_reward_and_reopening_does_not_pay_again(self):
        path = self.write_fixture()
        save = self.player.session("fixture-farmer")
        save["userInfo"]["player"].update(xp=self.thresholds[1], cash=5)
        with redirect_stdout(io.StringIO()):
            engine.apply_xp_increment(save, self.thresholds[100] - self.thresholds[1])
            self.player.save_session("fixture-farmer")
            self.player.load_saves()
        self.assertEqual(self.player.session("fixture-farmer")["userInfo"]["player"]["cash"], 104)
        fixtures.gateway_results(self, self.gateway([
            self.command("UserService.initUser", ["Level matrix", 0, True, None])]), [0])
        self.assertEqual(json.loads(path.read_text())["userInfo"]["player"]["cash"], 104)


if __name__ == "__main__":
    unittest.main()
