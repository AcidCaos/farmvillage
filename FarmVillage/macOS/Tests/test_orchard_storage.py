"""Original Feature Orchard storage, using only synthetic saves and AMF calls."""
from contextlib import redirect_stdout
import copy
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import engine
import items
import storage

NOW = 1_800_000_000


class OrchardStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if items._cached_items is None:
            with redirect_stdout(io.StringIO()):
                items.load_items()
        cls.tree = items.get_item_by_name("cherry")
        cls.catalog = items.get_items()

    def setUp(self):
        self.save = {"world": {"objectsArray": []}, "userInfo": {"currentWorldType": "farm",
            "player": {"gold": 2_000_000, "cash": 1000, "xp": 100015, "storageData": {
                "-1": {}, "-2": {}, "-8": {"HB": [7, [], [{"foreign": "keep"}]]}},
                "storageMetadata": {"opaque": {"keep": [1, 2]}}}}}
        self.owner()

    @property
    def obj(self):
        return self.save["world"]["objectsArray"][0]

    def owner(self, name="orchard_featurebuilding_finished", level=1, **changes):
        item = items.get_item_by_name(name)
        obj = {"id": 600, "itemName": name, "className": "OrchardFeatureBuilding", "state": "bare",
            "expansionLevel": level, "capacity": 99999, "expansionParts": {"opaque": {"keep": [1]}},
            "contents": [], "plantTime": NOW * 1000 - 1000, "itemOrder": [],
            "position": {"x": 10, "y": 10, "z": 0}, "storageMetadata": {"opaque": {"keep": [2]}},
            "imported": {"keep": [3]}, **changes}
        self.save["world"]["objectsArray"] = [obj]
        self.save["userInfo"]["player"]["storageData"].pop("600", None)
        self.assertEqual(storage.orchard_container_class(item), "orchard")
        return obj

    def gift(self, item=None, quantity=1, metadata=None):
        item = item or self.tree
        self.save["userInfo"]["player"]["storageData"]["-1"][item["code"]] = [
            quantity, ["friend"], copy.deepcopy(metadata or [])]

    def call(self, item=None, snapshot=None, **options):
        item = item or self.tree
        with redirect_stdout(io.StringIO()), mock.patch.object(engine, "timestamp_now", return_value=NOW):
            storage.store_world_item(self.save, copy.deepcopy(self.obj) if snapshot is None else snapshot,
                {"storedItemName": item["name"], "isGift": True, **options})

    def reject(self, item=None, snapshot=None, **options):
        before = copy.deepcopy(self.save)
        with self.assertRaises(ValueError):
            self.call(item, snapshot, **options)
        self.assertEqual(self.save, before)

    def test_exact_67_family_and_authored_current_capacities_keep_71_api_unchanged(self):
        rows = [item for item in self.catalog if storage.orchard_container_class(item)]
        self.assertEqual(len(rows), 67)
        self.assertEqual(sum(bool(storage.feature_container_class(item)) for item in self.catalog), 71)
        for item in rows:
            self.assertEqual(storage.orchard_capacity({}, item), int(item["capacity"]))
            expand = next(row for row in storage._list(item["features"]["feature"])
                          if row["className"] == "ExpandFManager")
            for stage in storage._list(expand["upgrade"]):
                self.assertEqual(storage.orchard_capacity({"expansionLevel": int(stage["level"]), "capacity": 99999},
                                                         item), int(stage["capacity"]))
            for level in (0, True, 4, 999):
                with self.assertRaises(ValueError):
                    storage.orchard_capacity({"expansionLevel": level}, item)
        for name in ("orchard", "orchard_finished", "xuk_sheep_pen_finished", "gnomegarden_finished"):
            self.assertIsNone(storage.orchard_container_class(items.get_item_by_name(name)))
        changed = copy.deepcopy(rows[0])
        changed["features"]["feature"].append({"name": "hidden", "className": "WitherManager"})
        self.assertIsNone(storage.orchard_container_class(changed))

    def test_tree_subclass_and_exact_no_orchard_keyword_filter(self):
        self.assertTrue(storage.orchard_accepts(self.tree))
        sapling = next(item for item in self.catalog if item.get("className") == "MystreeSapling")
        self.assertTrue(storage.orchard_accepts({**sapling, "keyword": []}))
        self.assertFalse(storage.orchard_accepts(sapling))
        denied = [item for item in self.catalog if item.get("type") == "tree"
                  and "noOrchard" in storage._list(item.get("keyword"))]
        self.assertEqual(len(denied), 3)
        for item in [*denied, items.get_item_by_name("cow"), items.get_item_by_name("part_pot"),
                     {**self.tree, "className": "UnrecoveredTreeSubclass"}]:
            self.assertFalse(storage.orchard_accepts(item))
        self.assertTrue(storage.orchard_accepts({**self.tree, "keyword": "notnoOrchard"}))

    def test_missing_completion_flag_bare_and_ripe_loads_preserve_clock_and_metadata(self):
        for state, planted in (("bare", NOW * 1000 - 1000), ("ripe", 1000)):
            self.owner(state=state, plantTime=planted)
            self.gift(metadata=[{"authoritative unit": [1]}])
            original = copy.deepcopy(self.obj)
            snapshot = {**self.obj, "capacity": 5000, "expansionLevel": 999, "plantTime": 0,
                        "contents": [], "storageMetadata": {}, "itemOrder": ["forged"], "imported": {}}
            self.call(snapshot=snapshot, metadata={"forged unit": True})
            expected = {**original, "state": state, "itemOrder": [self.tree["code"]],
                        "contents": [{"itemCode": self.tree["code"], "numItem": 1}]}
            self.assertEqual(self.obj, expected)
            self.assertEqual(self.save["userInfo"]["player"]["storageData"]["600"][self.tree["code"]],
                             [1, ["friend"], [{"authoritative unit": [1]}]])
            self.assertNotIn(self.tree["code"], self.save["userInfo"]["player"]["storageData"]["-1"])

    def test_gift_inventory_world_and_market_deposits_derive_capacity_before_source_mutation(self):
        self.gift(quantity=2)
        self.obj["contents"] = [{"itemCode": self.tree["code"], "numItem": 19, "opaque": "keep"}]
        self.save["userInfo"]["player"]["storageData"]["-2"][self.tree["code"]] = [1, [], []]
        self.save["world"]["objectsArray"].append({"id": 700, "itemName": self.tree["name"],
            "className": "Tree", "plantTime": 0})
        for options in ({"numToStore": 2}, {"isGift": False, "origin": -2, "numToStore": 2},
                        {"isGift": False, "resource": 700, "numToStore": 2},
                        {"isGift": False, "numToStore": 2}):
            self.reject(**options)
        clock = self.obj["plantTime"]
        self.call(isGift=False, resource=700)
        self.assertEqual(len(self.save["world"]["objectsArray"]), 1)
        self.assertEqual(self.obj["contents"], [{"itemCode": self.tree["code"], "numItem": 20, "opaque": "keep"}])
        self.assertEqual(self.obj["plantTime"], clock)
        self.reject(isGift=False, origin=-2)
        self.reject()

    def test_empty_source_metadata_cannot_be_replaced_by_forged_transaction_metadata(self):
        for options in ({}, {"isGift": False, "origin": -2}, {"isGift": False, "resource": 700}):
            self.owner()
            self.gift()
            self.save["userInfo"]["player"]["storageData"]["-2"][self.tree["code"]] = [1, [], []]
            self.save["world"]["objectsArray"].append({"id": 700, "itemName": self.tree["name"],
                "className": "Tree", "plantTime": 0})
            self.call(metadata={"forged unit": True}, **options)
            self.assertEqual(self.save["userInfo"]["player"]["storageData"]["600"][self.tree["code"]][2], [])

    def test_sparse_gift_and_inventory_metadata_moves_only_when_removed_from_source(self):
        for origin, options in (("-1", {}), ("-2", {"isGift": False, "origin": -2})):
            self.owner()
            metadata = {"sparse imported unit": [1, 2]}
            data = self.save["userInfo"]["player"]["storageData"]
            data[origin][self.tree["code"]] = [10, ["friend"], [copy.deepcopy(metadata)]]
            self.call(**options)
            data = self.save["userInfo"]["player"]["storageData"]
            self.assertEqual(data[origin][self.tree["code"]][0], 9)
            self.assertEqual(data[origin][self.tree["code"]][2], [metadata])
            self.assertEqual(data["600"][self.tree["code"]], [1, ["friend"], []])
            self.call(numToStore=9, **options)
            data = self.save["userInfo"]["player"]["storageData"]
            self.assertNotIn(self.tree["code"], data[origin])
            self.assertEqual(data["600"][self.tree["code"]], [10, ["friend"], [metadata]])

    def test_region_level_two_and_shared_target_level_three_use_30_and_40_slots(self):
        for name, level, capacity in (("xah_orchard_finished", 2, 30),
                                      ("superorchard_featurebuilding", 3, 40)):
            self.owner(name, level, plantTime=1000)
            self.gift(quantity=capacity + 1)
            self.call(numToStore=capacity)
            self.assertEqual(self.obj["contents"], [{"itemCode": self.tree["code"], "numItem": capacity}])
            self.assertEqual(self.obj["state"], "ripe")
            self.reject()

    def test_wrong_filter_bad_owners_clocks_sources_and_ledgers_refuse_atomically(self):
        self.gift()
        base = copy.deepcopy(self.save)
        for changes in ({"isFullyBuilt": False}, {"isFullyBuilt": 1}, {"state": "construction"},
                        {"state": "unknown"}, {"deleted": True}, {"className": "StorageBuilding"},
                        {"expansionLevel": 4}, {"plantTime": True}, {"plantTime": NOW * 1000 + 1},
                        {"itemOrder": {"not": "an array"}}):
            self.save = copy.deepcopy(base)
            self.obj.update(changes)
            self.reject()
        self.save = copy.deepcopy(base)
        self.save["world"]["objectsArray"].append(copy.deepcopy(self.obj))
        self.reject()
        self.save = copy.deepcopy(base)
        for options in ({"target": 600.5}, {"resource": 700.5}, {"isGift": False, "origin": -8},
                        {"giftMetadataIndex": True}, {"giftMetadataIndex": 0.5}):
            self.reject(**options)
        self.save["userInfo"]["player"]["storageData"]["600"] = {self.tree["code"]: [1, [], []]}
        self.reject()
        self.save = copy.deepcopy(base)
        cow = items.get_item_by_name("cow")
        self.gift(cow)
        self.reject(cow)

    def test_hawaii_stuffing_rule_does_not_run_on_other_owned_farms(self):
        self.owner("xukorchard_featurebuilding_finished", plantTime=1000)
        self.gift(quantity=2)
        self.call(numToStore=2)
        self.assertEqual((self.obj["plantTime"], self.obj["state"]), (1000, "ripe"))

    def test_overflow_and_incompatible_imports_remain_withdrawable_without_losing_other_data(self):
        cow = items.get_item_by_name("cow")
        self.obj.update(state="ripe", itemOrder=[cow["code"], self.tree["code"]],
                        contents=[{"itemCode": cow["code"], "numItem": 50, "opaque": {"keep": True}}])
        original_meta = copy.deepcopy(self.obj["storageMetadata"])
        with redirect_stdout(io.StringIO()):
            self.assertTrue(storage.withdraw_for_placement(self.save, "cow", [{"isStorageWithdrawal": 600}]))
        self.assertEqual(self.obj["contents"], [{"itemCode": cow["code"], "numItem": 49, "opaque": {"keep": True}}])
        self.assertEqual(self.obj["itemOrder"], [self.tree["code"]])
        self.assertEqual(self.obj["storageMetadata"], original_meta)
        before = copy.deepcopy(self.save)
        with self.assertRaises(ValueError):
            storage.withdraw_for_placement(self.save, "cow", [{"isStorageWithdrawal": 600.5}])
        self.assertEqual(self.save, before)


class OrchardStorageWireTests(unittest.TestCase):
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
        self.tree = items.get_item_by_name("cherry")
        self.save["userInfo"]["player"].update(xp=100015, gold=2_000_000, cash=1000, storageData={
            "-1": {self.tree["code"]: [2, ["friend"], [{"tree unit": "keep"}]]},
            "-2": {"HB": [4, [], [{"negative inventory": "keep"}]]}})
        self.save["world"]["objectsArray"] = [{"id": 600, "itemName": "orchard_featurebuilding_finished",
            "className": "OrchardFeatureBuilding", "state": "bare", "expansionLevel": 1,
            "capacity": 20, "expansionParts": {"opaque": {"keep": [1]}}, "itemOrder": [],
            "plantTime": NOW * 1000 - 1000, "storageMetadata": {"opaque": {"keep": [2]}},
            "contents": [], "position": {"x": 10, "y": 10, "z": 0}}]
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")

    def send(self, item, sequence=1, error=0):
        snapshot = copy.deepcopy(self.save["world"]["objectsArray"][0])
        snapshot.update(contents=[], expansionLevel=999, capacity=5000, expansionParts={}, plantTime=0,
                        storageMetadata={}, itemOrder=["forged"])
        with redirect_stdout(io.StringIO()), mock.patch.object(engine, "timestamp_now", return_value=NOW):
            result = self.gateway([self.command("WorldService.performAction", ["store", snapshot,
                [{"storedItemName": item["name"], "isGift": True}]], sequence)])
        return fixtures.gateway_results(self, result, [error])[0]["data"]

    def test_signed_amf_store_reload_and_refused_overflow_preserve_durable_owner_and_gift(self):
        self.prepare()
        before = copy.deepcopy(self.save["world"]["objectsArray"][0])
        negative = copy.deepcopy(self.save["userInfo"]["player"]["storageData"]["-2"])
        self.assertEqual(self.send(self.tree), {"id": 600})
        obj = self.save["world"]["objectsArray"][0]
        self.assertEqual(obj["plantTime"], before["plantTime"])
        self.assertEqual(obj["storageMetadata"], before["storageMetadata"])
        self.assertEqual(obj["itemOrder"], [self.tree["code"]])
        self.assertEqual(obj["contents"], [{"itemCode": self.tree["code"], "numItem": 1}])
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-2"], negative)
        accepted = copy.deepcopy(self.save)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.save, accepted)
        self.save["world"]["objectsArray"][0]["contents"][0]["numItem"] = 20
        self.save["userInfo"]["player"]["storageData"]["600"][self.tree["code"]][0] = 20
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")
        memory, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.send(self.tree, sequence=2, error=29)
        self.assertEqual(self.save, memory)
        self.assertEqual(self.path.read_bytes(), disk)


if __name__ == "__main__":
    unittest.main()
