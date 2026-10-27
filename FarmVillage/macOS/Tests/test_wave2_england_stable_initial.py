"""Original English km stable initial-site and complete inline tier acceptance.

Every farm, gift and material is synthetic; imported clocks are preconditions.
"""
from contextlib import redirect_stdout
import copy
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import test_wave2_england_depth as depth
import construction
import items
import peaceful
import storage
import world_travel

NOW = 1_800_000_000


class EnglandOriginalStableWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway
    save = depth.EnglandDepthWireTests.save
    obj = depth.EnglandDepthWireTests.obj
    persist = depth.EnglandDepthWireTests.persist
    snapshot = depth.EnglandDepthWireTests.snapshot
    send = depth.EnglandDepthWireTests.send
    reject_unchanged = depth.EnglandDepthWireTests.reject_unchanged
    rpc = depth.EnglandDepthWireTests.rpc
    assert_home = depth.EnglandDepthWireTests.assert_home

    def prepare(self, **extra):
        depth.EnglandDepthWireTests.prepare(self, "xukhorsestable", **extra)
        self.assertEqual(items.get_item_by_name("xukhorsestable")["code"], "km")

    def place_site(self):
        self.prepare()
        self.save["world"]["objectsArray"] = []
        self.save["userInfo"]["player"]["storageData"]["-1"] = {"km": [1, [], []]}
        self.persist()
        raw = {"id": 64000, "itemName": "xukhorsestable", "className": "HorseStableBuilding",
            "position": {"x": 10, "y": 11, "z": 0}, "state": "built", "isFullyBuilt": True,
            "plantTime": NOW * 1000, "contents": [], "expansionParts": {"K1": 50},
            "expansionLevel": 5, "capacity": 999, "importedBuilding": {"keep": [1, 2]}}
        self.send("place", raw, {"isGift": True})
        self.assertEqual((self.obj["state"], self.obj["isFullyBuilt"], self.obj["expansionLevel"]),
                         ("construction", False, 1))
        self.assertEqual(self.obj["contents"], [{"itemCode": "K1", "numItem": 1}])
        self.assertEqual(self.obj["expansionParts"], {})
        return self.snapshot()

    def test_original_km_initial_fifty_materials_complete_on_england_without_home_charge(self):
        self.place_site()
        needs = construction._initial_requirements(items.get_item_by_name("xukhorsestable"))
        self.assertEqual(sum(count for _, count in needs.values()), 50)
        self.assertEqual(len(needs), 5)
        for code, (material, required) in needs.items():
            missing = required - (code == "K1")
            self.save["userInfo"]["player"]["storageData"].setdefault("-1", {})[code] = [missing, [], []]
            self.persist()
            self.send("store", options={"storedItemName": material["name"], "isGift": True, "numToStore": missing})
        self.assertEqual((self.obj["itemName"], self.obj["className"], self.obj["isFullyBuilt"], self.obj["state"]),
                         ("xukhorsestable", "HorseStableBuilding", True, "built"))
        self.assertEqual(storage._container_capacity(self.obj, items.get_item_by_name("xukhorsestable")), 20)
        self.assertTrue(all(row["numItem"] == 0 for row in self.obj["contents"]))
        self.assertEqual(self.save["userInfo"]["player"]["cash"], 2500)
        self.assertEqual(self.obj["plantTime"], NOW * 1000)
        self.assert_home()
        accepted = copy.deepcopy(self.save)
        # Login/reload intentionally discards a prior Flash session's temporary
        # placement aliases while retaining the allocated owned object IDs.
        for obj in accepted["world"]["objectsArray"]:
            obj.pop("tempId", None)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.save, accepted)

    def test_original_km_paid_initial_completion_costs_exact_missing_fortynine_and_retries(self):
        raw = self.place_site()
        self.save["userInfo"]["player"]["cash"] = 48
        self.persist()
        self.reject_unchanged("CompleteNow", raw)
        self.save["userInfo"]["player"]["cash"] = 49
        self.persist()
        result = self.send("CompleteNow", raw, sequence=40)
        self.assertEqual(self.save["userInfo"]["player"]["cash"], 0)
        self.assertTrue(self.obj["isFullyBuilt"])
        self.assertEqual(self.obj["itemName"], "xukhorsestable")
        accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.assertEqual(self.send("CompleteNow", raw, sequence=40), result)
        self.assertEqual(self.save, accepted)
        self.assertEqual(self.path.read_bytes(), disk)
        self.assert_home()

    def test_original_km_all_four_inline_upgrades_occupants_and_full_harvest_cooldown(self):
        horse = items.get_item_by_name("horse_black")
        code = horse["code"]
        self.prepare(contents=[{"itemCode": code, "numItem": 1}],
            storageMetadata={"retained": {"name": "Imported Hazel", "DNA": [1, 2]}})
        original = copy.deepcopy(self.obj)
        self.save["userInfo"]["player"]["storageData"]["600"] = {
            code: [1, [], [{"name": "Imported Hazel", "DNA": [1, 2]}]]}
        self.persist()
        for level, capacity in ((2, 25), (3, 30), (4, 35), (5, 40)):
            self.send("CompleteNow")
            self.assertEqual((self.obj["expansionLevel"], self.obj["capacity"]), (level, capacity))
            for field in ("contents", "plantTime", "storageMetadata", "position", "importedBuilding"):
                self.assertEqual(self.obj[field], original[field])
        self.assertEqual(self.save["userInfo"]["player"]["cash"], 2300)
        self.reject_unchanged("CompleteNow")
        self.save["userInfo"]["player"]["storageData"]["-1"] = {code: [1, [], [{"name": "Second horse"}]], "CW": [1, [], []]}
        self.persist()
        self.reject_unchanged("store", options={"storedItemName": "cow", "isGift": True})
        self.send("store", options={"storedItemName": "horse_black", "isGift": True})
        self.assertEqual(self.obj["contents"][0]["numItem"], 2)
        gold = self.save["userInfo"]["player"]["gold"]
        raw = self.snapshot()
        with mock.patch.object(self.server.commands, "timestamp_now", return_value=NOW):
            self.send("harvest", raw, sequence=60)
        self.assertEqual(self.save["userInfo"]["player"]["gold"], gold + 2 * int(horse["coinYield"]))
        self.assertEqual(self.obj["plantTime"], NOW * 1000)
        accepted = copy.deepcopy(self.save)
        grow = peaceful.grow_seconds(items.get_item_by_name("xukhorsestable"))
        with mock.patch.object(self.server.commands, "timestamp_now", return_value=NOW + grow - 2):
            self.send("harvest", raw, sequence=61)
        self.assertEqual(self.save, accepted)
        self.assert_home()

    def test_empty_object_classic_contents_init_projection_is_safe_in_both_owned_worlds(self):
        names = ("xukhorsestable", "xukhorsestable_finished", "nurserybarn_finished",
                 "nurserybarn_finished_complete", "pigpen_finished", "pigpenv2_finished")
        for name in names:
            with self.subTest(name=name):
                depth.EnglandDepthWireTests.prepare(self, name, contents={})
                original = copy.deepcopy(self.obj)
                inactive = {**copy.deepcopy(original), "id": 701}
                self.save[world_travel.STATE_KEY]["inactive"]["farm"]["objectsArray"].append(inactive)
                self.persist()
                initialized = self.rpc("UserService.initUser", ["Synthetic import recovery", 0, True, None])
                self.assertEqual(initialized["world"]["objectsArray"][0]["contents"], [])
                self.assertEqual(self.obj["contents"], [])
                self.assertEqual(self.save[world_travel.STATE_KEY]["inactive"]["farm"]["objectsArray"][-1]["contents"], [])
                for field in ("itemName", "className", "plantTime", "position", "importedBuilding"):
                    self.assertEqual(self.obj[field], original[field])


if __name__ == "__main__":
    unittest.main()
