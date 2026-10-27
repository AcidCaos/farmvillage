"""Dormant imported farms remain readable while generic mutations fail closed."""
import copy
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import commands
import creative_worlds
import items
import pets
import storage
import themed_worlds
import world_travel


class ImportedWorldMutationTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    dormant = ("toyland", "sleepyhollow", "australia", "fforest", "htown", "unrecovered-feature-map")

    def setUp(self):
        fixtures.RuntimeFixtureTests.setUp(self)
        # Exercise the dormant-import boundary explicitly. These five reviewed
        # contracts are now active in production; activation tests cover that
        # separate path without turning this refusal fixture into a live farm.
        dormant_roster = themed_worlds.ACTIVE_WORLDS.difference(self.dormant)
        inactive = mock.patch.object(themed_worlds, "ACTIVE_WORLDS", dormant_roster)
        inactive.start()
        self.addCleanup(inactive.stop)

    def imported(self, world):
        self.path = self.write_fixture()
        save = self.player.session("fixture-farmer")
        save.pop(world_travel.STATE_KEY, None)
        save["userInfo"]["currentWorldType"] = world
        save["userInfo"]["worldSummaryData"][world] = {
            "storageId": themed_worlds.SPECS.get(world, {}).get("storageId", -200),
            "originalSummary": {"preserve": [world]}}
        save["world"]["originalWorld"] = {"preserve": [world]}
        save["opaqueFeatureData"] = {"preserve": [world]}
        save["userInfo"]["player"]["storageData"]["-2"] = {"HB": [2, [], []]}
        save["userInfo"]["player"]["storageData"]["-1"] = {"HB": [2, [], []]}
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")
        return save

    @staticmethod
    def plow(**changes):
        return {"id": 63000, "tempId": -1, "className": "Plot", "state": "plowed",
                "itemName": None, "position": {"x": 4, "y": 4, "z": 0}, **changes}

    def test_all_dormant_and_unknown_imports_refuse_direct_farming_purchases_inventory_and_equipment(self):
        bale = items.get_item_by_name("haybale")
        package = next(iter(pets.FOOD_PACKAGES))
        for world in self.dormant:
            save = self.imported(world)
            before, disk = copy.deepcopy(save), self.path.read_bytes()
            calls = (
                lambda: commands.world_perform_action("fixture-farmer", "plow", self.plow(), []),
                lambda: commands.world_perform_action("fixture-farmer", "store", {"id": -2, "itemName": "haybale"}, [{"storedItemName": "haybale", "target": -2}]),
                lambda: commands.equipment_use("fixture-farmer", "plow", [self.plow()], "", {}),
                lambda: commands.equipment_use("fixture-farmer", "combine", [], "", {}),
                lambda: commands.equipment_use("fixture-farmer", "plotRemove", [], "", {}),
                lambda: commands.buy_consumable_package("fixture-farmer", package),
                lambda: commands.expand_farm("fixture-farmer", "farm14", "coins"),
                lambda: commands.buy_avatar_item("fixture-farmer", "unknown-item"),
                lambda: creative_worlds.guard_market_purchase(save, bale, "coins"),
                lambda: storage.store_deposit_item_by_name(save, "haybale", 1, -2),
                lambda: storage.store_withdraw_item_by_code(save, "HB", 1, -2),
                lambda: storage.withdraw_for_placement(save, "haybale", [{"isInventoryWithdrawal": True}]),
                lambda: storage.store_world_item(save, {"id": -2, "itemName": "haybale"}, {"storedItemName": "haybale", "target": -2}),
                lambda: storage.active_inventory_id(save),
                lambda: world_travel.guard_action_object(save, 63000),
                lambda: world_travel.guard_new_object_id(save, "plow", 63000),
                lambda: world_travel.guard_placement(save, self.plow()),
            )
            for index, call in enumerate(calls):
                with self.subTest(world=world, entry=index), self.assertRaisesRegex(ValueError, "imported active world is not supported"):
                    call()
                self.assertEqual(save, before)
                self.assertEqual(self.path.read_bytes(), disk)

    def test_gateway_refuses_paid_and_inventory_entries_without_touching_imported_save(self):
        package = next(iter(pets.FOOD_PACKAGES))
        for world in self.dormant:
            with self.subTest(world=world):
                save = self.imported(world)
                before, disk = copy.deepcopy(save), self.path.read_bytes()
                calls = [
                    self.command("WorldService.performAction", ["plow", self.plow(), []]),
                    self.command("WorldService.performAction", ["store", {"id": -2, "itemName": "haybale"}, [{"storedItemName": "haybale", "target": -2}]]),
                    self.command("EquipmentWorldService.onUseEquipment", ["plow", {}, [self.plow()], ""]),
                    self.command("FarmService.buyConsumablePackage", [package]),
                ]
                response = self.gateway(calls)
                fixtures.gateway_results(self, response, [29] * len(calls))
                self.assertEqual(save, before)
                self.assertEqual(self.path.read_bytes(), disk)
                with redirect_stdout(io.StringIO()):
                    self.player.load_saves()
                reloaded = self.player.session("fixture-farmer")
                self.assertIsNotNone(reloaded)
                self.assertEqual(reloaded["userInfo"]["currentWorldType"], world)
                self.assertEqual(reloaded["opaqueFeatureData"], before["opaqueFeatureData"])
                self.assertNotIn(world_travel.STATE_KEY, reloaded)
                self.assertEqual(self.path.read_bytes(), disk)

    def test_explicit_nonhome_payload_cannot_fall_back_to_legacy_home(self):
        for field in ("worldType", "currentWorldType"):
            self.path = self.write_fixture()
            save = self.player.session("fixture-farmer")
            save.pop(world_travel.STATE_KEY, None)
            before, disk = copy.deepcopy(save), self.path.read_bytes()
            for world in self.dormant:
                for snapshot, params in ((self.plow(**{field: world}), []),
                                         (self.plow(), [{field: world}])):
                    with self.subTest(field=field, world=world), self.assertRaisesRegex(ValueError, "world does not match"):
                        commands.world_perform_action("fixture-farmer", "plow", snapshot, params)
                    self.assertEqual(save, before)
                    self.assertEqual(self.path.read_bytes(), disk)


if __name__ == "__main__":
    unittest.main()
