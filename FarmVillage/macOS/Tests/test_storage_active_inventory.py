"""Inventory routing for supported farms with legacy or incomplete summaries."""
import copy
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence  # Own a temporary data root before product imports.
import items
import storage
import themed_worlds

INVENTORIES = {"farm": -2, "england": -8, "fisherman": -9, "meadows": -16,
               "rainforest": -26, "mediterranean": -29, "storybook": -32,
               "candy": -23, "oasis": -31, "oz": -28, "toyland": -34,
               "sleepyhollow": -33, "australia": -21, "fforest": -24, "htown": -15}
NEW_INVENTORIES = {"hlights": -25, "atlantis": -19, "glen": -18}


class ActiveInventoryTests(unittest.TestCase):
    def save(self, world, **extra):
        return {"userInfo": {"currentWorldType": world, "player": {}, **extra}}

    def test_missing_legacy_summary_uses_every_supported_worlds_original_inventory(self):
        # Imported active farms may predate our travel namespace and lack a
        # summary entry. Every activated farm still has its own original ID.
        with mock.patch.object(themed_worlds, "ACTIVE_WORLDS", set(themed_worlds.SPECS)):
            for world, ident in INVENTORIES.items():
                for summary in (None, {}, {world: {"imported": [1, 2]}}):
                    with self.subTest(world=world, summary=summary):
                        save = self.save(world)
                        if summary is not None:
                            save["userInfo"]["worldSummaryData"] = copy.deepcopy(summary)
                        before = copy.deepcopy(save)
                        self.assertEqual(storage.active_inventory_id(save), ident)
                        self.assertEqual(save, before)

    def test_explicit_imported_summary_remains_authoritative_and_unchanged(self):
        save = self.save("rainforest", worldSummaryData={
            "rainforest": {"storageId": -26, "imported": {"keep": True}},
            "farm": {"storageId": -2}})
        before = copy.deepcopy(save)
        self.assertEqual(storage.active_inventory_id(save), -26)
        self.assertEqual(save, before)

    def test_newly_activated_worlds_use_their_own_contract_without_another_storage_patch(self):
        recovered = {world: {"storageId": ident} for world, ident in NEW_INVENTORIES.items()}
        with mock.patch.dict(themed_worlds.SPECS, recovered), mock.patch.object(
                themed_worlds, "ACTIVE_WORLDS", set(recovered)):
            for world, spec in recovered.items():
                with self.subTest(world=world):
                    self.assertEqual(storage.active_inventory_id(self.save(world)), spec["storageId"])

    def test_inventory_withdrawal_without_summary_consumes_only_active_worlds_item(self):
        item = {"name": "haybale", "code": "HB", "className": "Decoration", "type": "decoration"}
        save = self.save("rainforest")
        save["world"] = {"objectsArray": []}
        save["userInfo"]["player"]["storageData"] = {
            "-26": {"HB": [2, ["friend"], [{"unit": 1}, {"unit": 2}]]},
            "-2": {"HB": [10, [], [{"home": "keep"}]]}}
        home = copy.deepcopy(save["userInfo"]["player"]["storageData"]["-2"])
        with mock.patch.object(storage, "get_item_by_name", return_value=item), mock.patch.object(
                storage, "get_item_by_code", return_value=item):
            self.assertTrue(storage.withdraw_for_placement(save, "haybale", [{"isInventoryWithdrawal": True}]))
        self.assertEqual(save["userInfo"]["player"]["storageData"]["-26"]["HB"],
                         [1, [], [{"unit": 2}]])
        self.assertEqual(save["userInfo"]["player"]["storageData"]["-2"], home)

    def test_disabled_and_unknown_worlds_never_receive_an_inventory_fallback(self):
        with mock.patch.object(themed_worlds, "ACTIVE_WORLDS", set()):
            for world in ("rainforest", "unknown-import", 1):
                with self.subTest(world=world), self.assertRaises(ValueError):
                    storage.active_inventory_id(self.save(world))

    def test_original_empty_home_labels_keep_the_home_inventory(self):
        for world in (None, "", "farm"):
            with self.subTest(world=world):
                self.assertEqual(storage.active_inventory_id(self.save(world)), -2)


class NewWorldInventoryCapacityTests(unittest.TestCase):
    catalog = [{"name": "haybale", "code": "HB", "className": "Decoration", "type": "decoration"},
               {"name": "toolshedpink", "code": "S1", "className": "StorageBuilding", "type": "building",
                "storageType": {"itemClass": "Inventory"}, "capacity": "15",
                "image": {"name": "built_0"}}]

    def setUp(self):
        self.specs = {world: {"storageId": ident} for world, ident in NEW_INVENTORIES.items()}
        patchers = [mock.patch.dict(themed_worlds.SPECS, self.specs),
                    mock.patch.object(themed_worlds, "ACTIVE_WORLDS", set(self.specs)),
                    mock.patch.object(items, "_cached_items", {"settings": {"items": {"item": self.catalog}}})]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def save(self, world, *, sheds=0):
        return {"world": {"objectsArray": [self.shed(100 + n) for n in range(sheds)]},
                "userInfo": {"currentWorldType": world,
                             "player": {"gold": 1234, "cash": 50, "storageData": {
                                 str(NEW_INVENTORIES[world]): {}, "-2": {"HB": [7, [], [{"home": "keep"}]]}}}}}

    def shed(self, ident):
        return {"id": ident, "itemName": "toolshedpink", "className": "StorageBuilding", "state": "built"}

    def test_recovered_new_inventory_ceilings_do_not_grant_slots_and_clamp_owned_capacity(self):
        for world, ident in NEW_INVENTORIES.items():
            with self.subTest(world=world):
                self.assertEqual(storage._inventory_limits()[ident], 1250)
                save = self.save(world)
                before = copy.deepcopy(save)
                with self.assertRaisesRegex(ValueError, "storage space"):
                    storage._guard_inventory_deposit(save, ident, 1)
                self.assertEqual(save, before)
                save["world"]["objectsArray"] = [self.shed(100)]
                storage._guard_inventory_deposit(save, ident, 15)
                with self.assertRaisesRegex(ValueError, "storage space"):
                    storage._guard_inventory_deposit(save, ident, 16)
                save["world"]["objectsArray"] = [self.shed(100 + n) for n in range(84)]
                storage._guard_inventory_deposit(save, ident, 1250)
                with self.assertRaisesRegex(ValueError, "storage space"):
                    storage._guard_inventory_deposit(save, ident, 1251)

    def test_store_and_withdraw_each_new_world_keep_balances_metadata_and_home_inventory(self):
        for world, ident in NEW_INVENTORIES.items():
            with self.subTest(world=world):
                save = self.save(world, sheds=1)
                obj = {"id": 900, "itemName": "haybale", "className": "Decoration", "state": "static"}
                save["world"]["objectsArray"].append(obj)
                original = copy.deepcopy(save)
                storage.store_world_item(save, obj, {"target": ident, "storedItemName": "haybale",
                                                     "resource": 900, "metadata": {"unit": "keep"}})
                self.assertEqual(save["world"]["objectsArray"], [self.shed(100)])
                self.assertEqual(save["userInfo"]["player"]["storageData"][str(ident)]["HB"],
                                 [1, [], [{"unit": "keep"}]])
                self.assertTrue(storage.withdraw_for_placement(save, "haybale", [{"isInventoryWithdrawal": True}]))
                self.assertEqual(save["userInfo"]["player"]["storageData"][str(ident)], {})
                self.assertEqual(save["userInfo"], original["userInfo"])

    def test_foreign_summary_cannot_route_capacity_into_an_unactivated_inventory(self):
        save = self.save("hlights", sheds=1)
        save["userInfo"]["worldSummaryData"] = {"hlights": {"storageId": -35}}
        before = copy.deepcopy(save)
        # Avalon has a recovered ceiling, but that never activates its ledger
        # or overrides Holiday Lights' source-backed -25 inventory contract.
        self.assertIn(-35, storage._inventory_limits())
        with self.assertRaisesRegex(ValueError, "active farm inventory"):
            storage._guard_inventory_deposit(save, -35, 1)
        self.assertEqual(save, before)


if __name__ == "__main__":
    unittest.main()
