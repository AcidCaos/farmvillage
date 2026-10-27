"""Authoritative level/cottage purchase gates; real catalogs, temporary farms."""
from contextlib import redirect_stdout
from datetime import datetime, timezone
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import client_catalog
import crafting
import creative_worlds
import game_settings
import items
import progression
import quests
import storage
import world_travel


class MarketAvailabilityTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    def prepare(self, world="farm", level=1):
        self.path = self.write_fixture()
        self.save = self.player.session("fixture-farmer")
        self.save["userInfo"]["player"].update(xp=game_settings.level_to_xp(15), gold=10000, cash=1000)
        if world == "england":
            world_travel.switch(self.save, "england", True, now=1800000000)
        self.save["world"]["objectsArray"] = [{
            "id": 900, "itemName": "barn", "className": "StorageBuilding", "state": "built",
            "contents": [], "position": {"x": 15, "y": 15, "z": 0}}]
        self.save["userInfo"]["player"]["xp"] = game_settings.level_to_xp(level)
        self.group = storage.active_inventory_id(self.save)
        self.save["userInfo"]["player"]["storageData"][str(self.group)] = {}
        # Settle world-unlock quest rewards before measuring the purchase.
        # England's already-earned access reward is independent of this item.
        with redirect_stdout(io.StringIO()):
            progression.refresh_owned(self.save)
            quests.refresh_active_quests(self.save)
        self.save["userInfo"]["player"].update(xp=game_settings.level_to_xp(level), gold=10000, cash=1000)
        self.persist()

    def persist(self):
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")

    @staticmethod
    def snapshot(name="bushhorse", ident=64001):
        item = items.get_item_by_name(name)
        return {"id": ident, "className": item["className"], "itemName": name,
                "state": "static" if item["type"] == "decoration" else "built",
                "position": {"x": 5, "y": 5, "z": 0}}

    def request(self, action, name="bushhorse", *, sequence=1, options=None):
        if action == "store":
            obj = {"id": self.group, "className": "StorageBuilding"}
            options = options or {"storedItemName": name, "target": self.group, "resource": 0, "origin": 0}
        else:
            obj = self.snapshot(name)
        return self.command("WorldService.performAction", [action, obj, [options] if options else []], sequence)

    def rejected(self, request):
        before = self.path.read_bytes()
        memory = copy.deepcopy(self.player.session("fixture-farmer"))
        results = fixtures.gateway_results(self, self.gateway([request]), [29])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.player.session("fixture-farmer"), memory)
        return results[0]

    def test_below_original_level_rejects_placement_and_inventory_before_payment_in_home_and_england(self):
        item = items.get_item_by_name("bushhorse")
        self.assertEqual((item["code"], item["requiredLevel"], item["cost"]), ("7T", "6", "100"))
        for world in ("farm", "england"):
            for action in ("place", "store"):
                with self.subTest(world=world, action=action):
                    self.prepare(world, level=5)
                    self.assertIn("level is too low", self.rejected(self.request(action))["errorData"])

    def test_original_threshold_allows_both_purchase_paths_and_survives_reload(self):
        for world in ("farm", "england"):
            for action in ("place", "store"):
                with self.subTest(world=world, action=action):
                    self.prepare(world, level=6)
                    before = copy.deepcopy(self.save["userInfo"]["player"])
                    request = self.request(action)
                    fixtures.gateway_results(self, self.gateway([request]), [0])
                    saved = json.loads(self.path.read_text())
                    self.assertEqual(saved["userInfo"]["player"]["gold"], before["gold"] - 100)
                    if action == "place":
                        once = self.path.read_bytes()
                        fixtures.gateway_results(self, self.gateway([request]), [0])
                        self.assertEqual(self.path.read_bytes(), once)
                    with redirect_stdout(io.StringIO()):
                        self.player.load_saves()
                    reloaded = self.player.session("fixture-farmer")
                    self.assertEqual(reloaded["userInfo"]["player"]["gold"], before["gold"] - 100)
                    if action == "place":
                        self.assertEqual(sum(o.get("itemName") == "bushhorse" for o in reloaded["world"]["objectsArray"]), 1)
                    else:
                        self.assertEqual(reloaded["userInfo"]["player"]["storageData"][str(self.group)]["7T"][0], 1)

    def test_below_level_gifts_owned_inventory_and_moves_remain_available_without_purchase(self):
        for origin in ("gift", "inventory", "owned"):
            with self.subTest(origin=origin):
                self.prepare(level=1)
                snapshot = self.snapshot()
                if origin == "owned":
                    self.save["world"]["objectsArray"].append(dict(snapshot, id=901, imported={"keep": [1, 2]}))
                    snapshot.update(id=901, position={"x": 6, "y": 6, "z": 0})
                    action, options = "move", []
                else:
                    group = -1 if origin == "gift" else self.group
                    self.save["userInfo"]["player"]["storageData"][str(group)] = {"7T": [1, [], []]}
                    action = "place"
                    options = [{"isGift": True}] if origin == "gift" else [{"isInventoryWithdrawal": True}]
                self.persist()
                coins = self.save["userInfo"]["player"]["gold"]
                request = self.command("WorldService.performAction", [action, snapshot, options])
                fixtures.gateway_results(self, self.gateway([request]), [0])
                saved = json.loads(self.path.read_text())
                self.assertEqual(saved["userInfo"]["player"]["gold"], coins)
                owned = next(o for o in saved["world"]["objectsArray"] if o.get("itemName") == "bushhorse")
                if origin == "owned":
                    self.assertEqual(owned["imported"], {"keep": [1, 2]})

    def test_unsupported_cottage_purchase_rejects_both_wire_paths_without_rewards_or_storage(self):
        for world in ("farm", "england"):
            for action in ("place", "store"):
                with self.subTest(world=world, action=action):
                    self.prepare(world, level=100)
                    self.rejected(self.request(action, "xaf_herbalinn"))

    def test_every_unsupported_cottage_has_matching_presentation_and_authoritative_purchase_policy(self):
        self.prepare(level=100)
        cottages = [row for row in items.get_items() if row.get("className") == "CraftingCottageBuilding"]
        unsupported = [row for row in cottages if row["name"] not in crafting.COTTAGES.values()]
        self.assertEqual((len(cottages), len(unsupported)), (70, 63))
        before = copy.deepcopy(self.save)
        for item in unsupported:
            with self.subTest(item=item["name"]):
                self.assertTrue(client_catalog._unsupported_cottage(item))
                with self.assertRaisesRegex(ValueError, "production is not restored"):
                    creative_worlds.guard_market_purchase(self.save, item)
        self.assertEqual(self.save, before)
        self.assertTrue(all(not client_catalog._unsupported_cottage(items.get_item_by_name(name))
                            for name in crafting.COTTAGES.values()))

    def test_unaccepted_cottage_owned_and_gift_records_are_preserved(self):
        self.prepare(level=100)
        obj = self.snapshot("xaf_herbalinn", ident=901)
        obj["importedProduction"] = {"retain": ["unknown", 7]}
        self.save["world"]["objectsArray"].append(copy.deepcopy(obj))
        self.save["userInfo"]["player"]["storageData"]["-1"] = {"0iux": [2, ["friend"], [{"retain": True}]]}
        self.persist()
        before_gifts = copy.deepcopy(self.save["userInfo"]["player"]["storageData"]["-1"])
        obj["position"] = {"x": 6, "y": 6, "z": 0}
        request = self.command("WorldService.performAction", ["move", obj, []])
        fixtures.gateway_results(self, self.gateway([request]), [0])
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        saved = self.player.session("fixture-farmer")
        self.assertEqual(saved["userInfo"]["player"]["storageData"]["-1"], before_gifts)
        self.assertEqual(next(o for o in saved["world"]["objectsArray"] if o.get("id") == 901)["importedProduction"],
                         {"retain": ["unknown", 7]})

    def test_cottage_purchase_preflight_uses_original_selected_tier_price(self):
        self.prepare(level=25)
        item = items.get_item_by_name("craftingwinery")
        resolved = crafting.purchase_catalog_item(self.save, item)
        self.assertIsNot(resolved, item)
        self.assertIn("cost", resolved)
        coins = self.save["userInfo"]["player"]["gold"]
        with mock.patch.object(crafting, "purchase_catalog_item", wraps=crafting.purchase_catalog_item) as resolve:
            creative_worlds.guard_market_purchase(self.save, item)
            resolve.assert_called_once_with(self.save, item)
        self.assertEqual(self.save["userInfo"]["player"]["gold"], coins)

    def test_bulk_cottage_inventory_purchase_rejects_before_charging_or_adding_any_tier(self):
        self.prepare(level=100)
        for name in crafting.HOME_COTTAGES.values():
            with self.subTest(cottage=name):
                options = {"storedItemName": name, "target": self.group, "resource": 0,
                           "origin": 0, "numToStore": 2}
                self.assertIn("one at a time", self.rejected(self.request("store", name, options=options))["errorData"])

    def test_conflicting_original_level_arrays_reject_both_purchase_paths_but_repeated_levels_pass(self):
        self.prepare(level=100)
        for action in ("place", "store"):
            with self.subTest(action=action):
                self.assertIn("conflicting catalog", self.rejected(self.request(action, "sheep_shaggy_lamb"))["errorData"])
        item = items.get_item_by_name("porchswing")
        self.assertEqual(item["requiredLevel"], ["1", "1"])
        self.assertEqual(client_catalog.purchase_required_level(item), 1)
        self.save["userInfo"]["player"]["gold"] = 50000
        creative_worlds.guard_market_purchase(self.save, item)

    def test_real_agave_plant_packet_accepts_repeated_level_during_its_original_offer(self):
        self.prepare(level=1)
        item = items.get_item_by_name("agave")
        self.assertEqual((item["requiredLevel"], item["cost"], item["plantXp"]), (["1", "1"], "120", "1"))
        # This archived seed's offer expired in September 2012. Exercise its
        # real date gate at an original valid server date, without changing
        # catalog fields or skipping purchase rules.
        now = int(datetime(2012, 9, 1, 12, tzinfo=timezone.utc).timestamp())
        plot = {"id": 901, "className": "Plot", "itemName": None, "state": "plowed",
                "plantTime": 0, "position": {"x": 5, "y": 5, "z": 0}}
        self.save["world"]["objectsArray"].append(copy.deepcopy(plot))
        self.persist()
        coins = self.save["userInfo"]["player"]["gold"]
        crop = dict(plot, itemName="agave", state="planted", plantTime=1)
        request = self.command("WorldService.performAction", ["place", crop, []])
        creative_worlds._guard_item_access(self.save, item, neighbor_count=0, world_type="meadows")
        with mock.patch("commands.timestamp_now", return_value=now), mock.patch("engine.timestamp_now", return_value=now):
            fixtures.gateway_results(self, self.gateway([request]), [0])
            once = self.path.read_bytes()
            fixtures.gateway_results(self, self.gateway([request]), [0])
            self.assertEqual(self.path.read_bytes(), once)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        saved = self.player.session("fixture-farmer")
        self.assertEqual(saved["userInfo"]["player"]["gold"], coins - 120)
        self.assertEqual(saved["userInfo"]["player"]["xp"], 1)
        planted = next(o for o in saved["world"]["objectsArray"] if o["id"] == 901)
        self.assertEqual((planted["itemName"], planted["state"], planted["plantTime"]),
                         ("agave", "planted", now * 1000))


if __name__ == "__main__":
    unittest.main()
