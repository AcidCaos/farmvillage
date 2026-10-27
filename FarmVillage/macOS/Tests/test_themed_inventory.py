"""Themed farms acquire ordinary global storage and retain separate ledgers."""
import copy
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import test_cove_cellar as cellar
import test_inventory_capacity as capacity
import creative_worlds
import game_settings
import items
import storage
import themed_worlds as tw
import world_travel

NOW = 1800000000
DECORATIONS = {"toyland": "xtl_bobbleflowerstand", "sleepyhollow": "xsh_direpumpkin",
               "australia": "farmerbollard", "fforest": "pristinekingdomgate",
               "htown": "xhdpresentbox"}


class ThemedInventoryTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway
    save = cellar.CoveCellarTests.save
    persist = cellar.CoveCellarTests.persist
    send = cellar.CoveCellarTests.send
    rejected = cellar.CoveCellarTests.rejected
    shed = staticmethod(capacity.InventoryCapacityTests.shed)

    def prepare(self, world):
        if world in {"glen", "hlights"}:
            import test_themed_worlds as common
            experiments = mock.patch.object(tw, "served_experiments", return_value=common.dormant_experiments())
            experiments.start()
            self.addCleanup(experiments.stop)
        self.path = self.write_fixture()
        self.save["world"]["objectsArray"] = []
        self.save["userInfo"]["player"].update(xp=game_settings.level_to_xp(15),
                                                 gold=10_000_000, cash=1000)
        creative_worlds.create(self.save, world, "allAccess", now=NOW)
        world_travel.switch(self.save, world, now=NOW)
        self.group = storage.active_inventory_id(self.save)
        self.home_ledger = copy.deepcopy(self.save["userInfo"]["player"]["storageData"]["-2"])
        self.persist()

    def test_all_eleven_themed_entities_inherit_original_ceiling_without_granting_slots(self):
        for world in tw.SPECS:
            with self.subTest(world=world), mock.patch.object(tw, "ACTIVE_WORLDS", {world}):
                self.prepare(world)
                self.assertEqual(storage._inventory_limits()[self.group], 1250)
                before = copy.deepcopy(self.save)
                with self.assertRaisesRegex(ValueError, "storage space"):
                    storage._guard_inventory_deposit(self.save, self.group, 1)
                self.assertEqual(self.save, before)
                self.save["world"]["objectsArray"] = [self.shed(900, capacity=999999)]
                storage._guard_inventory_deposit(self.save, self.group, 15)
                with self.assertRaisesRegex(ValueError, "storage space"):
                    storage._guard_inventory_deposit(self.save, self.group, 16)
                self.save["world"]["objectsArray"] = [self.shed(900 + n) for n in range(84)]
                storage._guard_inventory_deposit(self.save, self.group, 1250)
                with self.assertRaisesRegex(ValueError, "storage space"):
                    storage._guard_inventory_deposit(self.save, self.group, 1251)

    def test_global_admission_only_includes_unrestricted_ordinary_inventory_buildings(self):
        for world in tw.SPECS:
            admitted = tw.catalog_rules(world)["items"]
            self.assertEqual(admitted["toolshedpink"]["price"], {"currency": "cash", "amount": 22})
            for name in admitted:
                item = items.get_item_by_name(name)
                if any(node.get("className") == "World" and node.get("name") == world
                       for node in creative_worlds._nodes(item.get("requirements"))):
                    continue
                if (tw._world_feature(item, world) or {}).get("worldless"):
                    self.assertEqual((world, name, item["code"]), ("rainforest", "xrforchard_finished", "ruh"))
                    self.assertEqual(item["className"], "OrchardFeatureBuilding")
                    continue
                self.assertEqual((item.get("type"), item.get("className")), ("building", "StorageBuilding"))
                self.assertEqual(item["storageType"]["itemClass"], "Inventory")
                self.assertIn(item.get("requirements"), tw.NONE_VALUES)
                self.assertEqual(tw._reasons(item, world), [])
            self.assertNotIn("haybale", admitted)
            self.assertNotIn("hatchstorage", admitted)
            self.assertNotIn("toolshedpink2", admitted)

    def test_five_candidate_gateway_purchase_store_withdraw_reload_and_travel(self):
        for world, name in DECORATIONS.items():
            with self.subTest(world=world), mock.patch.object(tw, "ACTIVE_WORLDS", {world}):
                self.prepare(world)
                initial_cash = self.save["userInfo"]["player"]["cash"]
                shed_id = self.send("place", self.shed())["id"]
                self.assertEqual(self.save["userInfo"]["player"]["cash"], initial_cash - 22)
                self.send("place", self.shed())
                self.assertEqual(self.save["userInfo"]["player"]["cash"], initial_cash - 22)
                item = items.get_item_by_name(name)
                snapshot = {"id": 64002, "className": item.get("className") or "Decoration",
                            "itemName": name, "state": "static", "direction": 0,
                            "position": {"x": 20, "y": 20, "z": 0}}
                ident = self.send("place", snapshot)["id"]
                saved = copy.deepcopy(next(obj for obj in self.save["world"]["objectsArray"] if obj["id"] == ident))
                self.send("store", saved, [{"storedItemName": name, "target": self.group,
                                            "origin": 0, "resource": ident}])
                self.assertFalse(any(obj["id"] == ident for obj in self.save["world"]["objectsArray"]))
                self.assertEqual(self.save["userInfo"]["player"]["storageData"][str(self.group)][item["code"]], [1, [], []])
                with redirect_stdout(io.StringIO()):
                    self.player.load_saves()
                world_travel.switch(self.save, "farm", now=NOW)
                world_travel.switch(self.save, world, now=NOW)
                self.assertEqual(self.save["userInfo"]["player"]["storageData"][str(self.group)][item["code"]], [1, [], []])
                self.assertEqual(next(obj for obj in self.save["world"]["objectsArray"] if obj["id"] == shed_id)["itemName"], "toolshedpink")
                self.persist()
                withdrawal = dict(saved, id=64003, position={"x": 25, "y": 25, "z": 0})
                balances = (self.save["userInfo"]["player"]["gold"], self.save["userInfo"]["player"]["cash"])
                self.send("place", withdrawal, [{"isInventoryWithdrawal": True, "cameFromLocation": self.group}])
                self.assertNotIn(item["code"], self.save["userInfo"]["player"]["storageData"][str(self.group)])
                self.assertEqual((self.save["userInfo"]["player"]["gold"], self.save["userInfo"]["player"]["cash"]), balances)
                self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-2"], self.home_ledger)


if __name__ == "__main__":
    unittest.main()
