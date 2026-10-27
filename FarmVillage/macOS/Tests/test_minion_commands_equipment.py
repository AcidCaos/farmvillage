"""A vehicle combine charges a plot it invented in the same pass as it charges a plot the farm already had."""

from contextlib import ExitStack, redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence  # noqa: F401,E402  Loads first so FARMVILLAGE_DATA_DIR is set before product modules resolve paths.

import commands
import engine
import constants
import game_settings
import items

PLOW_COST = 15
PLOW_XP = 1
SEED_COST = 10
SEED_XP = 1


class CombineChargeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = game_settings._decode_game_settings((ROOT / "xml/gz/v855098/gameSettings.xml.gz").read_bytes())
        cls.initial = json.loads((ROOT / "villages/initial.json").read_text())
        cls.catalog = [
            {"name": "strawberry", "code": "SB", "type": "seed", "subtype": "fruit", "cost": str(SEED_COST),
             "growTime": "0.174", "coinYield": "35", "plantXp": str(SEED_XP), "mastery": "true", "masteryYield": "1",
             "masteryLevel": [{"count": "500", "xp": "25", "coins": "500"}]},
        ]

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for module, key, value in (
            (game_settings, "_cached_game_settings", self.settings),
            (game_settings, "_cached_farming", {}),
            (game_settings, "_xp_level_map", None),
            (game_settings, "_level_xp_map", None),
            (items, "_cached_items", {"settings": {"items": {"item": self.catalog}}}),
        ):
            self.stack.enter_context(mock.patch.object(module, key, value))
        game_settings._xp_level_map_init()
        self.save = copy.deepcopy(self.initial)
        self.save["world"]["objectsArray"] = []
        self.player = self.save["userInfo"]["player"]
        self.player.update(gold=100000, xp=0, cash=0, achievements={}, achCounters={}, mastery={},
                           masteryCounters={}, storageData={})
        self.stack.enter_context(mock.patch.object(commands, "session", return_value=self.save))
        self.stack.enter_context(mock.patch.object(commands.quests, "record_action"))
        self.stack.enter_context(redirect_stdout(io.StringIO()))

    def fallow_plot(self, ident=1):
        return {"id": ident, "className": "Plot", "itemName": None, "state": "fallow",
                "position": {"x": 0, "y": 0, "z": 0}, "plantTime": 0, "isJumbo": False, "isBigPlot": False}

    def invented_plot(self, state):
        return {"id": constants.TEMP_ID_START, "className": "Plot", "state": state,
                "itemName": "strawberry" if state == "planted" else None,
                "position": {"x": 3, "y": 0, "z": 3}, "plantTime": 1_000_000}

    def combine(self, entries):
        before = (self.player["gold"], self.player["xp"])
        responses = commands.equipment_use("test", "combine", entries, "strawberry", {})
        return responses, (self.player["gold"] - before[0], self.player["xp"] - before[1])

    def test_planting_a_stored_fallow_plot_costs_plow_and_seed(self):
        self.save["world"]["objectsArray"] = [self.fallow_plot()]
        _, (gold, xp) = self.combine([{"id": 1}])
        self.assertEqual(gold, -(PLOW_COST + SEED_COST))
        self.assertEqual(xp, PLOW_XP + SEED_XP)

    def test_planting_an_invented_plot_costs_the_same_plow_and_seed_as_a_stored_one(self):
        responses, (gold, xp) = self.combine([self.invented_plot("planted")])
        self.assertEqual(gold, -(PLOW_COST + SEED_COST))
        self.assertEqual(xp, PLOW_XP + SEED_XP)

    def test_invented_plot_is_stored_once_under_a_permanent_id_in_its_final_state(self):
        responses, _ = self.combine([self.invented_plot("planted")])
        stored = self.save["world"]["objectsArray"]
        self.assertEqual(len(stored), 1)
        self.assertFalse(engine.world_object_id_is_temporary(stored[0]["id"]))
        self.assertEqual((stored[0]["state"], stored[0]["itemName"]), ("planted", "strawberry"))
        self.assertEqual(responses["plow"]["data"][0]["data"]["id"], stored[0]["id"])
        self.assertEqual(responses["place"]["data"][0]["data"]["id"], stored[0]["id"])

    def test_invented_plot_that_was_only_plowed_costs_plow_and_is_not_planted(self):
        responses, (gold, xp) = self.combine([self.invented_plot("plowed")])
        self.assertEqual(gold, -PLOW_COST)
        self.assertEqual(xp, PLOW_XP)
        self.assertEqual([obj["state"] for obj in self.save["world"]["objectsArray"]], ["plowed"])
        self.assertIsNone(responses["place"]["data"][0])


if __name__ == "__main__":
    unittest.main()
