"""Round-3 command regressions: a destroyed building takes its contents with it, water and quest skips validate their
input, and plow costs, gift prices and irrigation action types are read from the same tables as the rest of the farm.
"""

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
import constants
import engine
import game_settings
import gifting
import items
import storage

CATALOG = [
    {"name": "stable", "code": "SA", "type": "building", "market": "coins", "cost": "100", "sellPrice": "40"},
    {"name": "horse", "code": "HR", "type": "animal", "market": "coins", "cost": "50"},
    {"name": "unicorn_wonderland", "code": "UW", "type": "decoration", "giftable": "true", "market": "cash",
     "cost": "100000", "cash": ["57", "57"]},
    {"name": "plainpresent", "code": "PP", "type": "decoration", "giftable": "true", "market": "cash",
     "cost": "1", "cash": "n"},
]


def plot(ident, state="fallow"):
    return {"id": ident, "className": "Plot", "itemName": None, "state": state,
            "position": {"x": 0, "y": 0, "z": 0}, "plantTime": 0, "isJumbo": False, "isBigPlot": False}


def stable(ident):
    return {"id": ident, "className": "Building", "itemName": "stable", "state": "static",
            "position": {"x": 0, "y": 0, "z": 0}}


class FarmFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = game_settings._decode_game_settings((ROOT / "xml/gz/v855098/gameSettings.xml.gz").read_bytes())
        cls.initial = json.loads((ROOT / "villages/initial.json").read_text())

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for module, key, value in (
            (game_settings, "_cached_game_settings", self.settings),
            (game_settings, "_cached_farming", {}),
            (game_settings, "_xp_level_map", None),
            (game_settings, "_level_xp_map", None),
            (items, "_cached_items", {"settings": {"items": {"item": CATALOG}}}),
        ):
            self.stack.enter_context(mock.patch.object(module, key, value))
        game_settings._xp_level_map_init()
        self.save = copy.deepcopy(self.initial)
        self.save["world"]["objectsArray"] = []
        self.player = self.save["userInfo"]["player"]
        self.player.update(gold=1000, xp=0, cash=500, achievements={}, achCounters={}, mastery={},
                           masteryCounters={}, storageData={})
        self.save["userInfo"]["featureOptions"]["irrigation"] = {
            "irrigation": {"waterPlots": {"farm": {"amount": 20}}}}
        self.stack.enter_context(mock.patch.object(commands, "session", return_value=self.save))
        self.stack.enter_context(mock.patch.object(commands.quests, "record_action"))
        self.stack.enter_context(redirect_stdout(io.StringIO()))


class DestroyedBuildingLedgerTests(FarmFixture):
    # storageData["<id>"] is the contents ledger of the world object with that id, and engine.get_new_world_object_id
    # hands a removed id to the next placement. A destroyed building's ledger must not outlive it.

    def test_selling_a_building_drops_its_contents_ledger_and_keeps_other_ledgers(self):
        self.save["world"]["objectsArray"] = [plot(4), stable(5), stable(3)]
        self.player["storageData"] = {"5": {"HR": [2, [], []]}, "3": {"HR": [1, [], []]}}
        commands.world_perform_action("test", "sell", stable(5), [])
        self.assertEqual([obj["id"] for obj in self.save["world"]["objectsArray"]], [4, 3])
        self.assertEqual(self.player["storageData"], {"3": {"HR": [1, [], []]}})

    def test_clearing_a_building_drops_its_contents_ledger(self):
        self.save["world"]["objectsArray"] = [stable(5)]
        self.player["storageData"] = {"5": {"HR": [2, [], []]}}
        commands.world_perform_action("test", "clear", stable(5), [])
        self.assertEqual(self.save["world"]["objectsArray"], [])
        self.assertEqual(self.player["storageData"], {})

    def test_a_building_placed_on_a_reused_id_does_not_inherit_the_old_contents(self):
        self.save["world"]["objectsArray"] = [plot(4), stable(5)]
        self.player["storageData"] = {"5": {"HR": [2, [], []]}}
        commands.world_perform_action("test", "sell", stable(5), [])
        placed = commands.world_perform_action("test", "place", stable(constants.TEMP_ID_START), [])
        self.assertEqual(placed, 5)
        self.assertFalse(storage.store_withdraw_item_by_code(self.save, "HR", 1, placed))
        self.assertNotIn(str(placed), self.player["storageData"])

    def test_a_vehicle_removing_a_plot_drops_any_ledger_left_on_its_id(self):
        self.save["world"]["objectsArray"] = [plot(4)]
        self.player["storageData"] = {"4": {"HR": [1, [], []]}}
        commands.equipment_use("test", "plotRemove", [{"id": 4}], None, {})
        self.assertEqual(self.save["world"]["objectsArray"], [])
        self.assertNotIn("4", self.player["storageData"])


class PlowCostTests(FarmFixture):
    def test_plow_charges_the_farming_plow_cost(self):
        with mock.patch.object(game_settings, "_cached_farming", {"plowCost": "40"}):
            commands.world_perform_action("test", "plow", plot(7), [])
        self.assertEqual(self.player["gold"], 960)

    def test_plow_defaults_to_fifteen_coins_without_a_setting(self):
        commands.world_perform_action("test", "plow", plot(7), [])
        self.assertEqual(self.player["gold"], 985)


class WaterPackageTests(FarmFixture):
    def amount(self):
        return self.save["userInfo"]["featureOptions"]["irrigation"]["irrigation"]["waterPlots"]["farm"]["amount"]

    def test_watering_without_a_held_package_grants_no_water(self):
        # A refused consume is an explicit error, so the client cannot treat it as a successful watering.
        with self.assertRaises(ValueError):
            commands.consume_water_packages("test", "waterPlots", 2)
        self.assertEqual(self.amount(), 20)
        self.assertEqual(self.player["storageData"], {})

    def test_watering_with_too_few_packages_grants_no_water_and_keeps_them(self):
        self.player["storageData"] = {"-1": {"3YG": [1, [], []]}}
        with self.assertRaises(ValueError):
            commands.consume_water_packages("test", "waterPlots", 2)
        self.assertEqual(self.amount(), 20)
        self.assertEqual(self.player["storageData"], {"-1": {"3YG": [1, [], []]}})

    def test_watering_with_held_packages_credits_water_and_spends_the_gifts(self):
        self.player["storageData"] = {"-1": {"3YG": [3, [], []]}}
        commands.consume_water_packages("test", "waterPlots", 2)
        self.assertEqual(self.amount(), 22)
        self.assertEqual(self.player["storageData"], {"-1": {"3YG": [1, [], []]}})


class IrrigationActionTypeTests(unittest.TestCase):
    def test_unknown_action_type_is_a_logged_no_op(self):
        save = {"userInfo": {"currentWorldType": "farm",
                             "featureOptions": {"irrigation": {"irrigation": {"waterPlots": {"farm": {"amount": 20}}}}}}}
        before = copy.deepcopy(save)
        out = io.StringIO()
        with redirect_stdout(out):
            engine.add_water(save, "waterTrees", 3)
        self.assertEqual(save, before)
        self.assertIn("waterTrees", out.getvalue())

    def test_missing_irrigation_feature_is_a_no_op(self):
        save = {"userInfo": {"currentWorldType": "farm", "featureOptions": {}}}
        with redirect_stdout(io.StringIO()):
            engine.add_water(save, "waterPlots", 3)
        self.assertEqual(save, {"userInfo": {"currentWorldType": "farm", "featureOptions": {}}})

    def test_known_action_type_still_adds_water(self):
        save = {"userInfo": {"currentWorldType": "farm",
                             "featureOptions": {"irrigation": {"irrigation": {"waterPlots": {"farm": {"amount": 20}}}}}}}
        with redirect_stdout(io.StringIO()):
            engine.add_water(save, "waterPlots", 3)
        self.assertEqual(save["userInfo"]["featureOptions"]["irrigation"]["irrigation"]["waterPlots"]["farm"]["amount"], 23)


class SkipQuestTaskTests(FarmFixture):
    def test_missing_or_non_integer_task_index_is_rejected_without_charge(self):
        for index in (None, -1, "2", True, 1.5, float("nan"), [1]):
            with self.subTest(index=index):
                with mock.patch.object(commands.quests, "skip_task") as skip:
                    commands.skip_quest_task("test", "SomeQuest", index)
                skip.assert_not_called()

    def test_whole_task_index_reaches_the_quest_module_as_an_int(self):
        for index in (0, 2, 2.0):
            with self.subTest(index=index):
                with mock.patch.object(commands.quests, "skip_task") as skip:
                    commands.skip_quest_task("test", "SomeQuest", index)
                skip.assert_called_once()
                self.assertIs(type(skip.call_args.args[2]), int)
                self.assertEqual(skip.call_args.args[2], int(index))


class GiftCashPriceTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.farms = {
            "sender": {"userInfo": {"player": {"cash": 500, "gold": 0, "xp": 0}}},
            "friend": {"userInfo": {"player": {"cash": 0, "gold": 0, "xp": 0}}},
            "friend2": {"userInfo": {"player": {"cash": 0, "gold": 0, "xp": 0}}},
        }
        self.stack.enter_context(mock.patch.object(items, "_cached_items", {"settings": {"items": {"item": CATALOG}}}))
        self.stack.enter_context(mock.patch.object(gifting.player, "session", side_effect=self.farms.get))
        self.stack.enter_context(mock.patch.object(gifting.player, "neighbor_uids", return_value=["friend", "friend2"]))
        self.stack.enter_context(mock.patch.object(gifting.player, "save_session"))

    def test_list_valued_cash_price_is_charged_per_recipient_from_its_first_entry(self):
        result = gifting.send("sender", "unicorn_wonderland", ["friend", "friend2"])
        self.assertEqual(result, {"complete": True, "numSent": 2, "totalCost": 114})
        self.assertEqual(self.farms["sender"]["userInfo"]["player"]["cash"], 386)

    def test_unreadable_cash_price_is_free_rather_than_an_error(self):
        result = gifting.send("sender", "plainpresent", ["friend"])
        self.assertEqual(result, {"complete": True, "numSent": 1, "totalCost": 0})
        self.assertEqual(self.farms["sender"]["userInfo"]["player"]["cash"], 500)


if __name__ == "__main__":
    unittest.main()
