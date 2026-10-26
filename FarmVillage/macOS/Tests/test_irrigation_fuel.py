"""Watering and irrigation packages restored from the v855097 client (2026-10-23).

Watering charges the water ledger one unit per planted plot, halves each crop's remaining grow time (or ripens it
when the half is within IRRIGATION_MINUTES_TO_INSTAGROW), and the 3YG water gifts convert to water one for one.
Fuel stays unspent; its refusal guards are checked here as well.
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
import game_settings
import items
import storage

NOW = 1_000_000  # whole seconds, as timestamp_now() reports them
GROW_SECONDS = 4000  # growTime 4 * inGameDaySeconds 1000 * growMultiplier 1

CATALOG = [
    {"name": "testseed", "code": "TS1", "type": "seed", "market": "coins", "cost": "10", "growTime": "4"},
    {"name": "consume_irrigation_water", "code": "3YG", "type": "consumable", "className": "CRewardConsumable",
     "rewards": {"reward": {"type": "irrigation", "value": "1", "actionType": "waterPlots"}}},
    {"name": "consume_irrigation_water_100", "code": "Pcr", "type": "consumable", "className": "CRewardConsumable",
     "rewards": {"reward": {"type": "item_grant", "quantity": "100", "value": "3YG"}}},
    {"name": "pkg_consume_irrigation_water_100", "code": "z1e", "type": "change_farm", "market": "cash", "cash": "2",
     "itemPackage": {"amount": "1", "value": "consume_irrigation_water_100"}},
]


def plot(ident, state="planted", planted_s=NOW, **extra):
    obj = {"id": ident, "className": "Plot", "itemName": "testseed", "state": state,
           "position": {"x": 0, "y": 0, "z": 0}, "plantTime": planted_s * 1000,
           "isJumbo": False, "isBigPlot": False}
    obj.update(extra)
    return obj


def stable(ident):
    return {"id": ident, "className": "Building", "itemName": "stable", "state": "static",
            "position": {"x": 0, "y": 0, "z": 0}}


class IrrigationFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = game_settings._decode_game_settings((ROOT / "xml/gz/v855098/gameSettings.xml.gz").read_bytes())
        cls.initial = json.loads((ROOT / "villages/initial.json").read_text())

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for module, key, value in (
            (game_settings, "_cached_game_settings", self.settings),
            (game_settings, "_cached_farming", {"inGameDaySeconds": "1000", "growMultiplier": "1"}),
            (game_settings, "_xp_level_map", None),
            (game_settings, "_level_xp_map", None),
            (items, "_cached_items", {"settings": {"items": {"item": CATALOG}}}),
        ):
            self.stack.enter_context(mock.patch.object(module, key, value))
        game_settings._xp_level_map_init()
        self.save = copy.deepcopy(self.initial)
        self.save["world"]["objectsArray"] = []
        self.save["userInfo"]["currentWorldType"] = "farm"
        self.save["userInfo"]["featureOptions"]["irrigation"] = {
            "irrigation": {"waterPlots": {"farm": {"amount": 20}}}}
        self.player = self.save["userInfo"]["player"]
        self.player.update(gold=1000, cash=500, storageData={})
        self.stack.enter_context(mock.patch.object(commands, "session", return_value=self.save))
        self.stack.enter_context(mock.patch.object(commands, "timestamp_now", return_value=NOW))
        self.stack.enter_context(redirect_stdout(io.StringIO()))

    def water(self):
        return self.save["userInfo"]["featureOptions"]["irrigation"]["irrigation"]["waterPlots"]["farm"]["amount"]

    def set_water(self, amount):
        self.save["userInfo"]["featureOptions"]["irrigation"]["irrigation"]["waterPlots"]["farm"]["amount"] = amount

    def plot_by_id(self, ident):
        return next(obj for obj in self.save["world"]["objectsArray"] if obj["id"] == ident)

    def remaining_ms(self, ident):
        return GROW_SECONDS * 1000 - (NOW * 1000 - self.plot_by_id(ident)["plantTime"])

    def water_all(self, *ids):
        return commands.irrigation_action("test", "waterPlots", [{"id": ident} for ident in ids])


class WateringTests(IrrigationFixture):
    def test_watering_halves_the_remaining_grow_time_and_charges_one_unit(self):
        self.save["world"]["objectsArray"] = [plot(1, planted_s=NOW - 1000)]  # 3000 s of growth left
        self.water_all(1)
        self.assertEqual(self.water(), 19)
        self.assertAlmostEqual(self.remaining_ms(1), 1_500_000, delta=1)
        self.assertEqual(self.plot_by_id(1)["state"], "planted")

    def test_each_selected_plot_costs_one_unit_and_only_those_plots_change(self):
        self.save["world"]["objectsArray"] = [plot(1, planted_s=NOW), plot(2, planted_s=NOW - 100),
                                              plot(3, planted_s=NOW - 200), plot(4, planted_s=NOW - 300)]
        untouched = copy.deepcopy(self.plot_by_id(4))
        self.water_all(1, 2, 3)
        self.assertEqual(self.water(), 17)
        self.assertEqual(self.plot_by_id(4), untouched)

    def test_a_crop_whose_half_is_within_the_threshold_ripens_now(self):
        # 400 s left: the half is 200 s, which is not more than 15 minutes, so the crop is ripe at once.
        self.save["world"]["objectsArray"] = [plot(1, planted_s=NOW - 3600)]
        self.water_all(1)
        self.assertEqual(self.water(), 19)
        self.assertEqual(self.remaining_ms(1), 0)
        self.assertEqual(self.plot_by_id(1)["state"], "planted")

    def test_insufficient_water_is_refused_without_any_state_change(self):
        self.set_water(1)
        self.save["world"]["objectsArray"] = [plot(1, planted_s=NOW), plot(2, planted_s=NOW)]
        before = copy.deepcopy(self.save)
        with self.assertRaisesRegex(ValueError, "Not enough irrigation water"):
            self.water_all(1, 2)
        self.assertEqual(self.save, before)

    def test_missing_water_store_is_refused_without_any_state_change(self):
        self.save["userInfo"]["featureOptions"]["irrigation"] = {"irrigation": {}}
        self.save["world"]["objectsArray"] = [plot(1, planted_s=NOW)]
        before = copy.deepcopy(self.save)
        with self.assertRaises(ValueError):
            self.water_all(1)
        self.assertEqual(self.save, before)

    def test_unknown_unplanted_and_non_plot_objects_are_refused_without_change(self):
        cases = {
            "unknown id": ([plot(1)], 99),
            "fallow": ([plot(1, state="fallow")], 1),
            "withered": ([plot(1, state="withered")], 1),
            "already grown": ([plot(1, state="grown")], 1),
            "building": ([stable(1)], 1),
        }
        for name, (objects, ident) in cases.items():
            with self.subTest(case=name):
                self.save["world"]["objectsArray"] = objects
                before = copy.deepcopy(self.save)
                with self.assertRaises(ValueError):
                    self.water_all(ident)
                self.assertEqual(self.save, before)

    def test_malformed_action_and_ids_are_refused_without_change(self):
        self.save["world"]["objectsArray"] = [plot(1, planted_s=NOW)]
        before = copy.deepcopy(self.save)
        calls = [
            ("water", [{"id": 1}]),
            ("waterPlots", []),
            ("waterPlots", None),
            ("waterPlots", [{"id": 1}, {"id": 1}]),
            ("waterPlots", ["1"]),
            ("waterPlots", [{"id": True}]),
        ]
        for action, items_in in calls:
            with self.subTest(action=action, items=items_in):
                with self.assertRaises(ValueError):
                    commands.irrigation_action("test", action, items_in)
                self.assertEqual(self.save, before)

    def test_super_plots_cost_one_until_the_superplot_experiment_is_served(self):
        self.save["world"]["objectsArray"] = [plot(1, planted_s=NOW, isSuperPlot=True)]
        self.water_all(1)
        self.assertEqual(self.water(), 19)
        self.set_water(20)
        with mock.patch.object(commands, "_superplots_experiment_served", return_value=True):
            self.water_all(1)
        self.assertEqual(self.water(), 15)

    def test_plant_time_threshold_is_strict(self):
        grow_ms = 4_000_000
        # Half of 1_800_000 is exactly the threshold, which does not instagrow; one millisecond more does.
        ripe = commands._plant_time_after_watering(NOW * 1000 - (grow_ms - 1_800_000), grow_ms, NOW * 1000)
        self.assertEqual(ripe, NOW * 1000 - grow_ms)
        partial = commands._plant_time_after_watering(NOW * 1000 - (grow_ms - 1_800_002), grow_ms, NOW * 1000)
        self.assertAlmostEqual(grow_ms - (NOW * 1000 - partial), 900_001, delta=1e-6)


class IrrigationPackageTests(IrrigationFixture):
    def test_consuming_packages_credits_water_and_removes_the_gifts(self):
        self.player["storageData"] = {"-1": {"3YG": [3, [], []]}}
        commands.consume_water_packages("test", "waterPlots", 2)
        self.assertEqual(self.water(), 22)
        self.assertEqual(self.player["storageData"], {"-1": {"3YG": [1, [], []]}})

    def test_using_every_package_removes_the_gift_entry(self):
        self.player["storageData"] = {"-1": {"3YG": [2, [], []]}}
        commands.consume_water_packages("test", "waterPlots", 2)
        self.assertEqual(self.water(), 22)
        self.assertNotIn("3YG", self.player["storageData"]["-1"])

    def test_refused_package_use_changes_neither_the_gifts_nor_the_water(self):
        cases = [
            ("short gifts", {"-1": {"3YG": [1, [], []]}}, 20, "waterPlots", 2, "farm"),
            ("no gifts", {}, 20, "waterPlots", 1, "farm"),
            ("over the cap", {"-1": {"3YG": [5, [], []]}}, 1999, "waterPlots", 2, "farm"),
            ("off the home farm", {"-1": {"3YG": [5, [], []]}}, 20, "waterPlots", 2, "england"),
            ("other action", {"-1": {"3YG": [5, [], []]}}, 20, "waterTrees", 2, "farm"),
            ("zero", {"-1": {"3YG": [5, [], []]}}, 20, "waterPlots", 0, "farm"),
            ("negative", {"-1": {"3YG": [5, [], []]}}, 20, "waterPlots", -1, "farm"),
            ("fractional", {"-1": {"3YG": [5, [], []]}}, 20, "waterPlots", 1.5, "farm"),
            ("text", {"-1": {"3YG": [5, [], []]}}, 20, "waterPlots", "2", "farm"),
        ]
        for name, storage_data, water, action, amount, world in cases:
            with self.subTest(case=name):
                self.player["storageData"] = copy.deepcopy(storage_data)
                self.set_water(water)
                self.save["userInfo"]["currentWorldType"] = world
                before = copy.deepcopy(self.save)
                with self.assertRaises(ValueError):
                    commands.consume_water_packages("test", action, amount)
                self.assertEqual(self.save, before)
                self.save["userInfo"]["currentWorldType"] = "farm"

    def test_package_use_without_a_water_store_keeps_the_gifts(self):
        self.save["userInfo"]["featureOptions"]["irrigation"] = {"irrigation": {}}
        self.player["storageData"] = {"-1": {"3YG": [2, [], []]}}
        before = copy.deepcopy(self.save)
        with self.assertRaises(ValueError):
            commands.consume_water_packages("test", "waterPlots", 2)
        self.assertEqual(self.save, before)

    def test_water_can_be_filled_exactly_to_the_cap(self):
        self.set_water(1998)
        self.player["storageData"] = {"-1": {"3YG": [2, [], []]}}
        commands.consume_water_packages("test", "waterPlots", 2)
        self.assertEqual(self.water(), 2000)

    def test_irrigation_package_purchase_charges_cash_and_deposits_its_water_gift(self):
        commands.buy_consumable_package("test", "pkg_consume_irrigation_water_100", request_id=1)
        self.assertEqual(self.player["cash"], 498)
        self.assertEqual(self.player["storageData"]["-1"]["Pcr"][0], 1)

    def test_purchased_package_unpacks_to_water_gifts_that_credit_water(self):
        commands.buy_consumable_package("test", "pkg_consume_irrigation_water_100", request_id=1)
        storage.consume_by_name(self.save, "consume_irrigation_water_100", 1, storage.GIFTBOX_ID)
        self.assertEqual(self.player["storageData"]["-1"]["3YG"][0], 100)
        commands.consume_water_packages("test", "waterPlots", 100)
        self.assertEqual(self.water(), 120)
        self.assertNotIn("3YG", self.player["storageData"]["-1"])

    def test_the_water_gift_itself_is_still_refused_by_the_generic_consume_route(self):
        self.player["storageData"] = {"-1": {"3YG": [1, [], []]}}
        before = copy.deepcopy(self.save)
        with self.assertRaisesRegex(ValueError, "not supported yet"):
            storage.consume_by_name(self.save, "consume_irrigation_water", 1, storage.GIFTBOX_ID)
        self.assertEqual(self.save, before)


class FuelRefusalTests(unittest.TestCase):
    def test_fuel_and_turbo_purchases_stay_refused_until_their_energy_is_mirrored(self):
        # Fuel is not charged or refilled on this server; see the note above commands.equipment_use.
        self.assertIn("FarmService.buyFuel", commands.UNRESTORED_SERVICE_CALLS)
        self.assertIn("FarmService.buyTurboChargers", commands.UNRESTORED_SERVICE_CALLS)


if __name__ == "__main__":
    unittest.main()
