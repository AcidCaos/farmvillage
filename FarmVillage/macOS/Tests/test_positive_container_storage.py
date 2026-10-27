"""Original positive FeatureBuilding filters and current-stage capacities."""
from contextlib import redirect_stdout
import copy
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import items
import storage
import world_travel

CLASSES = {"gnomegarden", "xas_gnomegarden", "masterybillboardanimal", "masterybillboardcrop",
           "masterybillboardgardenflower", "masterybillboardrecipe", "masterybillboardtree"}


class PositiveContainerStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if items._cached_items is None:
            with redirect_stdout(io.StringIO()):
                items.load_items()
        cls.catalog = items.get_items()
        cls.gnome = next(row for row in cls.catalog if row.get("className") == "Gnome"
                         and row["name"] not in ("gnomesprinkler", "gnome_magician", "gnome_robo"))
        cls.signs = {}
        for name, kind in storage._mastery_sign_sources().items():
            sign = items.get_item_by_name(name)
            if sign and kind in ("animal", "seed", "bloom", "tree"):
                cls.signs.setdefault(kind, sign)
        signs, _ = storage._recipe_mastery_signs()
        cls.signs["recipe"] = next(items.get_item_by_code(code) for code in sorted(signs) if items.get_item_by_code(code))

    def setUp(self):
        self.save = {"world": {"objectsArray": []}, "userInfo": {"currentWorldType": "farm",
            "player": {"gold": 2_000_000, "cash": 1000, "xp": 100015, "storageData": {
                "-1": {}, "-2": {"HB": [4, ["old sender"], [{"home": "keep"}]]},
                "-8": {"HB": [7, [], [{"england": "keep"}]]}},
                "storageMetadata": {"opaque": {"keep": [1, 2]}}}}}
        self.owner("gnomegarden_finished")

    def owner(self, name, level=None):
        item = items.get_item_by_name(name)
        if level is None:
            level = storage.feature_container_initial_level(item)
        obj = {"id": 600, "itemName": name, "className": "FeatureBuilding", "state": "built",
               "isFullyBuilt": True, "expansionLevel": level, "expansionParts": {"opaque": {"keep": [1]}},
               "capacity": storage._feature_capacity({"expansionLevel": level}, item),
               "plantTime": 1800000000, "contents": [], "position": {"x": 10, "y": 10},
               "imported": {"keep": [2]}, "featureProps": {"opaque": {"keep": [3]}}}
        self.save["world"]["objectsArray"] = [obj]
        self.save["userInfo"]["player"]["storageData"].pop("600", None)
        return obj

    @property
    def obj(self):
        return self.save["world"]["objectsArray"][0]

    def gift(self, item, quantity=1):
        self.save["userInfo"]["player"]["storageData"]["-1"][item["code"]] = [quantity, ["sender"], []]

    def call(self, item, **options):
        with redirect_stdout(io.StringIO()):
            storage.store_world_item(self.save, copy.deepcopy(self.obj),
                {"storedItemName": item["name"], "isGift": True, **options})

    def reject(self, item, snapshot=None, **options):
        before = copy.deepcopy(self.save)
        with redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
            storage.store_world_item(self.save, copy.deepcopy(self.obj) if snapshot is None else snapshot,
                {"storedItemName": item["name"], "isGift": True, **options})
        self.assertEqual(self.save, before)

    def test_exact_71_catalog_variants_and_all_authored_current_capacities(self):
        expected = [row for row in self.catalog if (row.get("storageType") or {}).get("itemClass") in CLASSES]
        actual = [row for row in self.catalog if storage.feature_container_class(row)]
        self.assertEqual([row["code"] for row in actual], [row["code"] for row in expected])
        self.assertEqual(len(actual), 71)
        expandable = 0
        for item in actual:
            self.assertEqual(storage.feature_container_class(item), item["storageType"]["itemClass"])
            self.assertEqual(storage._feature_capacity({}, item), int(item["capacity"]))
            expand = next(row for row in storage._list(item["features"]["feature"]) if row.get("className") == "ExpandFManager")
            stages = storage._list(expand.get("upgrade"))
            expandable += bool(stages)
            for stage in stages:
                self.assertEqual(storage._feature_capacity({"expansionLevel": int(stage["level"])}, item), int(stage["capacity"]))
            with self.assertRaises(ValueError):
                storage._feature_capacity({"expansionLevel": 999}, item)
        self.assertEqual(expandable, 66)
        for name in ("nurserybarn_finished", "pigpenv2_finished", "herbgarden", "bldg_holidaygivingtree", "orchard_finished"):
            self.assertIsNone(storage.feature_container_class(items.get_item_by_name(name)))

    def test_gnome_exact_classes_and_named_exceptions_accept_but_subclasses_and_parts_do_not(self):
        examples = [self.gnome, next(row for row in self.catalog if row.get("className") == "CraftRewardGnome")]
        examples += [items.get_item_by_name(name) for name in ("gnomesprinkler", "gnome_magician", "gnome_robo")]
        for item in examples:
            self.owner("gnomegarden_finished")
            self.gift(item)
            self.call(item)
            self.assertEqual(self.obj["contents"], [{"itemCode": item["code"], "numItem": 1}])
        self.assertFalse(storage._feature_accepts("gnomegarden", {**self.gnome, "className": "DerivedGnome"}))
        for item in (items.get_item_by_name("cow"), items.get_item_by_name("part_toadstool")):
            self.gift(item)
            self.reject(item)
        self.owner("xas_gnomegarden_finished")
        self.gift(self.gnome)
        self.call(self.gnome)
        self.assertEqual(self.obj["contents"][0]["numItem"], 1)

    def test_mastery_types_recipe_indexes_and_derived_heritage_signs(self):
        for kind, suffix in {"animal": "animal", "seed": "crop", "bloom": "gardenflower", "recipe": "recipe", "tree": "tree"}.items():
            item = self.signs[kind]
            for ending in ("finished", "finishedcash"):
                self.owner(f"masterybillboard{suffix}_{ending}")
                self.gift(item)
                self.call(item)
                self.assertEqual(self.obj["contents"], [{"itemCode": item["code"], "numItem": 1}])
                self.assertEqual(self.obj["capacity"], 5000 if ending == "finishedcash" else 10)
                self.assertEqual(self.obj["expansionLevel"], 6 if ending == "finishedcash" else 1)
            self.assertFalse(storage._feature_accepts(f"masterybillboard{suffix}", self.gnome))
        self.assertFalse(storage._feature_accepts("masterybillboardcrop", self.signs["animal"]))
        derived = next(row for row in self.catalog if row["code"].startswith("fvlocal_mastery_"))
        self.assertTrue(storage._feature_accepts("masterybillboardcrop", derived))
        _, cms = storage._recipe_mastery_signs()
        recipe = next(name for name in sorted(cms) if "_" not in name)
        for name in ("master" + recipe, "mastersign_" + recipe):
            self.assertTrue(storage._feature_accepts("masterybillboardrecipe", {"name": name, "code": "test-only"}))
        self.assertFalse(storage._feature_accepts("masterybillboardrecipe", {"name": "mastermissing_original_recipe", "code": "test-only"}))

    def test_target_progress_contents_and_ledger_metadata_survive_gift_inventory_and_world_store(self):
        self.owner("gnomegarden_finished", 2)
        self.obj["contents"] = [{"itemCode": self.gnome["code"], "numItem": 2, "opaque": {"keep": [1]}}]
        self.save["userInfo"]["player"]["storageData"]["600"] = {self.gnome["code"]: [2, ["old sender"], [{"old unit": "keep"}]]}
        self.gift(self.gnome)
        self.save["userInfo"]["player"]["storageData"]["-1"][self.gnome["code"]][2] = [{"new unit": "keep"}]
        original = copy.deepcopy(self.obj)
        meta = copy.deepcopy(self.save["userInfo"]["player"]["storageMetadata"])
        snapshot = {**self.obj, "contents": [], "expansionLevel": 999, "capacity": 9999, "expansionParts": {},
                    "plantTime": 0, "imported": {}, "featureProps": {}, "forged": True}
        with redirect_stdout(io.StringIO()):
            storage.store_world_item(self.save, snapshot, {"storedItemName": self.gnome["name"], "isGift": True, "metadata": {"forged unit": "refused"}})
        self.assertEqual({k: v for k, v in self.obj.items() if k != "contents"}, {k: v for k, v in original.items() if k != "contents"})
        self.assertEqual(self.obj["contents"], [{"itemCode": self.gnome["code"], "numItem": 3, "opaque": {"keep": [1]}}])
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["600"][self.gnome["code"]], [3, ["old sender", "sender"], [{"old unit": "keep"}, {"new unit": "keep"}]])
        self.assertEqual(self.save["userInfo"]["player"]["storageMetadata"], meta)
        self.save["userInfo"]["player"]["storageData"]["-2"][self.gnome["code"]] = [1, [], []]
        self.call(self.gnome, isGift=False, cameFromLocation=-2)
        self.assertNotIn(self.gnome["code"], self.save["userInfo"]["player"]["storageData"]["-2"])
        self.save["world"]["objectsArray"].append({"id": 700, "itemName": self.gnome["name"], "className": "Gnome"})
        self.call(self.gnome, isGift=False, resource=700)
        self.assertEqual((len(self.save["world"]["objectsArray"]), self.obj["contents"][0]["numItem"]), (1, 5))

    def test_filter_and_overflow_refuse_before_gift_inventory_world_or_market_mutation(self):
        cow = items.get_item_by_name("cow")
        self.gift(cow)
        self.save["userInfo"]["player"]["storageData"]["-2"][cow["code"]] = [1, [], []]
        self.save["world"]["objectsArray"].append({"id": 700, "itemName": "cow", "className": "Animal"})
        for options in ({}, {"isGift": False, "cameFromLocation": -2}, {"isGift": False, "resource": 700}, {"isGift": False, "resource": 0}):
            self.reject(cow, **options)
        self.gift(self.gnome, 20)
        self.obj["contents"] = [{"itemCode": self.gnome["code"], "numItem": 10}]
        self.reject(self.gnome, snapshot={**self.obj, "capacity": 99999, "expansionLevel": 6})
        self.obj["contents"][0]["numItem"] = 9
        self.reject(self.gnome, numToStore=2)
        self.call(self.gnome)
        self.assertEqual(self.obj["contents"][0]["numItem"], 10)

    def test_bad_owners_worlds_identity_levels_and_ledgers_refuse_atomically(self):
        self.gift(self.gnome)
        base = copy.deepcopy(self.save)
        for changes in ({"isFullyBuilt": False}, {"isFullyBuilt": 1}, {"state": "construction"}, {"deleted": True},
                        {"className": "StorageBuilding"}, {"expansionLevel": 0}, {"expansionLevel": True},
                        {"expansionLevel": 7}, {"contents": {"not": "an array"}}):
            self.save = copy.deepcopy(base)
            self.obj.update(changes)
            self.reject(self.gnome)
        self.save = copy.deepcopy(base)
        self.save["world"]["objectsArray"].append(copy.deepcopy(self.obj))
        self.reject(self.gnome)
        self.save = copy.deepcopy(base)
        for field, value in (("id", 601), ("itemName", "masterybillboardcrop_finished"), ("className", "StorageBuilding")):
            self.reject(self.gnome, snapshot={**self.obj, field: value})
        for target in (600.5, True):
            self.reject(self.gnome, target=target)
        self.save["userInfo"]["player"]["storageData"]["600"] = {self.gnome["code"]: [2, [], []]}
        self.reject(self.gnome)
        self.save = copy.deepcopy(base)
        self.save["userInfo"]["currentWorldType"] = "unknown-world"
        self.reject(self.gnome)
        self.save = copy.deepcopy(base)
        snapshot = copy.deepcopy(self.obj)
        self.save["world"]["objectsArray"] = []
        self.reject(self.gnome, snapshot=snapshot)

    def test_foreign_fractional_or_orphaned_sources_cannot_supply_a_new_container(self):
        self.gift(self.gnome)
        self.save["userInfo"]["player"]["storageData"].update({
            "-8": {self.gnome["code"]: [1, [], []]}, "700": {self.gnome["code"]: [1, [], []]}})
        for options in ({"cameFromLocation": -8}, {"cameFromLocation": -1.5},
                        {"origin": True}, {"origin": 700.5}, {"cameFromLocation": 700},
                        {"resource": 700.5}):
            self.reject(self.gnome, isGift=False, **options)
        self.save["userInfo"]["worldSummaryData"] = {"farm": {"storageId": -8}}
        self.reject(self.gnome, isGift=False, cameFromLocation=-8)
        self.save["userInfo"].pop("worldSummaryData")
        with mock.patch.object(world_travel, "guard_action_object", side_effect=ValueError("inactive collision")) as guard:
            self.reject(self.gnome)
        guard.assert_called_once_with(unittest.mock.ANY, 600)

    def test_positive_source_requires_owned_complete_identity_but_allows_overflow_recovery(self):
        cow = items.get_item_by_name("cow")
        self.obj["contents"] = [{"itemCode": cow["code"], "numItem": 11, "opaque": {"keep": True}}]
        before = copy.deepcopy(self.save)
        for changes in ({"isFullyBuilt": False}, {"className": "StorageBuilding"}):
            self.save = copy.deepcopy(before)
            self.obj.update(changes)
            invalid = copy.deepcopy(self.save)
            with self.assertRaises(ValueError):
                storage.withdraw_for_placement(self.save, "cow", [{"isStorageWithdrawal": 600}])
            self.assertEqual(self.save, invalid)
        self.save = copy.deepcopy(before)
        self.save["world"]["objectsArray"].append(copy.deepcopy(self.obj))
        with self.assertRaises(ValueError):
            storage.withdraw_for_placement(self.save, "cow", [{"isStorageWithdrawal": 600}])
        self.save = copy.deepcopy(before)
        with redirect_stdout(io.StringIO()):
            self.assertTrue(storage.withdraw_for_placement(self.save, "cow", [{"isStorageWithdrawal": 600}]))
        self.assertEqual(self.obj["contents"], [{"itemCode": cow["code"], "numItem": 10, "opaque": {"keep": True}}])

    def test_fractional_positive_withdrawal_id_cannot_alias_the_owned_container(self):
        self.obj["contents"] = [{"itemCode": self.gnome["code"], "numItem": 1}]
        before = copy.deepcopy(self.save)
        with redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
            storage.withdraw_for_placement(self.save, self.gnome["name"], [{"isStorageWithdrawal": 600.5}])
        self.assertEqual(self.save, before)


class PositiveContainerWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    fixture = fixtures.RuntimeFixtureTests.fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    @property
    def save(self):
        return self.player.session("fixture-farmer")

    def prepare(self):
        self.path = self.write_fixture()
        self.gnome = next(row for row in items.get_items() if row.get("className") == "Gnome")
        self.save["userInfo"]["player"].update(xp=100015, gold=2_000_000, cash=1000, storageData={
            "-1": {self.gnome["code"]: [2, ["friend"], []]}, "-2": {"HB": [4, [], [{"keep": True}]]}})
        self.save["world"]["objectsArray"] = [{"id": 600, "itemName": "gnomegarden_finished",
            "className": "FeatureBuilding", "state": "built", "isFullyBuilt": True,
            "expansionLevel": 1, "capacity": 10, "expansionParts": {"opaque": {"keep": [1]}},
            "plantTime": 1800000000, "contents": [], "position": {"x": 10, "y": 10, "z": 0}}]
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")

    def send(self, item, sequence=1, error=0):
        snapshot = copy.deepcopy(self.save["world"]["objectsArray"][0])
        snapshot.update(contents=[], expansionLevel=6, capacity=5000, expansionParts={}, plantTime=0)
        with redirect_stdout(io.StringIO()):
            result = self.gateway([self.command("WorldService.performAction", ["store", snapshot,
                [{"storedItemName": item["name"], "isGift": True}]], sequence)])
        return fixtures.gateway_results(self, result, [error])[0]["data"]

    def test_signed_store_withdrawal_and_reload_preserve_owner_and_negative_inventories(self):
        self.prepare()
        before = copy.deepcopy(self.save["world"]["objectsArray"][0])
        home = copy.deepcopy(self.save["userInfo"]["player"]["storageData"]["-2"])
        self.assertEqual(self.send(self.gnome), {"id": 600})
        obj = self.save["world"]["objectsArray"][0]
        self.assertEqual({k: v for k, v in obj.items() if k != "contents"}, {k: v for k, v in before.items() if k != "contents"})
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-2"], home)
        accepted = copy.deepcopy(self.save)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.save, accepted)
        with redirect_stdout(io.StringIO()):
            self.assertTrue(storage.withdraw_for_placement(self.save, self.gnome["name"], [{"isStorageWithdrawal": 600}]))
        self.assertEqual(self.save["world"]["objectsArray"][0]["contents"], [])
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-2"], home)

    def test_signed_incompatible_and_overflow_requests_preserve_disk_and_memory(self):
        self.prepare()
        cow = items.get_item_by_name("cow")
        self.save["userInfo"]["player"]["storageData"]["-1"][cow["code"]] = [1, [], []]
        for item, full in ((cow, False), (self.gnome, True)):
            if full:
                self.save["world"]["objectsArray"][0]["contents"] = [{"itemCode": self.gnome["code"], "numItem": 10}]
            with redirect_stdout(io.StringIO()):
                self.player.save_session("fixture-farmer")
            memory, disk = copy.deepcopy(self.save), self.path.read_bytes()
            self.send(item, sequence=2 if full else 1, error=29)
            self.assertEqual(self.save, memory)
            self.assertEqual(self.path.read_bytes(), disk)


if __name__ == "__main__":
    unittest.main()
