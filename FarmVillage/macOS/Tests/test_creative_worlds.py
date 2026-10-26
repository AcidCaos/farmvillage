"""Additional-farm rule and durability checks using disposable saves only."""
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures  # Redirect every writable path before product imports.
import creative_worlds
import world_travel


NOW = 1800000000


class AdditionalFarmTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    def prepare(self, *, level=15, cash=60):
        from game_settings import level_to_xp
        self.path = self.write_fixture()
        save = self.player.session("fixture-farmer")
        save["userInfo"]["player"].update(xp=level_to_xp(level), cash=cash)
        save["unknownImportedWorlds"] = {"hawaii": {"preserved": [1, 2]}}
        return save

    def create(self, save, **options):
        with redirect_stdout(io.StringIO()):
            return creative_worlds.create(save, "meadows", now=NOW, **options)

    @staticmethod
    def seed_inventory_storage(save):
        # Meadows' empty local starter grants no ordinary inventory slots.
        save["world"]["objectsArray"].append({"id": world_travel.next_object_id(save),
            "className": "StorageBuilding", "itemName": "toolshedpink", "state": "built", "contents": [],
            "position": {"x": 4, "y": 4, "z": 0}})
        import progression
        progression.refresh_owned(save)
        progression.take_response(save)

    def test_archive_contract_is_exact_paid_option_without_shipping_or_plot_cap(self):
        rules = creative_worlds.recovered_rules()
        self.assertEqual((rules["minimumLevel"], rules["cashCost"], rules["rewardCode"],
                          rules["storageId"], rules["tileSet"]), (15, 60, "66e", -16, "grass_theme"))
        import themed_worlds
        with mock.patch.object(themed_worlds, "ACTIVE_WORLDS", frozenset()):
            self.assertEqual([row["worldType"] for row in creative_worlds.candidates()], ["meadows", "fisherman"])
        self.assertEqual([row["worldType"] for row in creative_worlds.candidates()][:2], ["meadows", "fisherman"])
        save = self.prepare()
        before_user = copy.deepcopy(save["userInfo"])
        before_home = copy.deepcopy(save["world"])
        self.assertTrue(self.create(save))
        self.assertEqual(save["userInfo"]["currentWorldType"], "farm")
        self.assertEqual(save["world"], before_home)
        self.assertEqual(save["userInfo"]["player"]["cash"], 0)
        self.assertEqual(save["userInfo"]["player"]["gold"], before_user["player"]["gold"])
        self.assertEqual(save["userInfo"]["player"]["xp"], before_user["player"]["xp"])
        self.assertEqual(save["userInfo"]["player"]["storageData"]["-1"]["66e"], [1, [], []])
        self.assertEqual(save["userInfo"]["worldSummaryData"]["meadows"]["storageId"], -16)
        self.assertEqual(save["userInfo"]["player"]["seenFlags"], before_user["player"]["seenFlags"])
        self.assertEqual(save["unknownImportedWorlds"], {"hawaii": {"preserved": [1, 2]}})
        target = save[world_travel.STATE_KEY]["inactive"]["meadows"]
        self.assertEqual((target["sizeX"], target["sizeY"], target["tileSet"]), (50, 50, "grass_theme"))
        self.assertEqual(target["localStarter"], "empty-meadows-v1")

    def test_rejections_never_charge_unlock_or_mutate(self):
        for level, cash in ((14, 60), (15, 59), (15, float("nan")), (15, True)):
            with self.subTest(level=level, cash=cash):
                save = self.prepare(level=level, cash=cash)
                before = copy.deepcopy(save)
                with self.assertRaises(ValueError):
                    self.create(save)
                # NaN is unequal to its own deepcopy; all other fields must
                # still be byte-for-byte stable in a JSON representation.
                self.assertEqual(json.dumps(save, sort_keys=True), json.dumps(before, sort_keys=True))
        save = self.prepare()
        before = copy.deepcopy(save)
        for world, option in (("winterwonderland", "cash60"), ("fisherman", "cash60"),
                              ("hawaii", "cash60"), ("meadows", "cash199"),
                              ("meadows", "coins200000000")):
            with self.subTest(world=world, option=option), self.assertRaises(ValueError):
                creative_worlds.create(save, world, option, now=NOW)
            self.assertEqual(save, before)
        with self.assertRaisesRegex(ValueError, "date"):
            creative_worlds.create(save, "meadows", now=1)
        self.assertEqual(save, before)

    def test_existing_imported_missing_snapshot_is_never_overwritten(self):
        for missing in ("summary", "unlock", "inventory"):
            with self.subTest(missing=missing):
                save = self.prepare()
                if missing == "summary":
                    save["userInfo"]["worldSummaryData"]["meadows"] = {"storageId": -16, "imported": True}
                elif missing == "unlock":
                    save["userInfo"].setdefault("unlockedWorldTypes", ["farm"]).append("meadows")
                else:
                    save["userInfo"]["player"]["storageData"]["-16"] = {"HB": [2, [], []]}
                before = copy.deepcopy(save)
                with self.assertRaisesRegex(ValueError, "snapshot is missing"):
                    self.create(save)
                self.assertEqual(save, before)

    def test_repeat_purchase_reload_and_travel_preserve_all_worlds(self):
        save = self.prepare(cash=120)
        world_travel.switch(save, "england", True, now=NOW)
        england = copy.deepcopy(save["world"])
        home = copy.deepcopy(world_travel.home_world(save))
        self.create(save)
        first = copy.deepcopy(save)
        self.assertFalse(self.create(save))
        self.assertEqual(save, first)
        world_travel.switch(save, "meadows", now=NOW + 1)
        uid = save["world"]["uid"]
        save["world"]["localDecorationMarker"] = {"keep": True}
        save["userInfo"]["player"]["storageData"]["-16"] = {"HB": [2, [], []]}
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")
            self.player.load_saves()
        save = self.player.session("fixture-farmer")
        self.assertFalse(self.create(save))
        self.assertEqual(save["world"]["uid"], uid)
        self.assertEqual(save["userInfo"]["player"]["cash"], 60)
        self.assertEqual(save["userInfo"]["player"]["storageData"]["-1"]["66e"][0], 1)
        world_travel.switch(save, "england", True, now=NOW + 2)
        self.assertEqual(save["world"], england)
        self.assertEqual(world_travel.home_world(save), home)
        world_travel.switch(save, "meadows", True, now=NOW + 3)
        self.assertEqual(save["world"]["localDecorationMarker"], {"keep": True})
        self.assertEqual(save["userInfo"]["player"]["storageData"]["-16"], {"HB": [2, [], []]})

    def test_direct_world_creation_cannot_bypass_price(self):
        save = self.prepare()
        before = copy.deepcopy(save)
        with self.assertRaisesRegex(ValueError, "Purchase Sunflower Meadows"):
            world_travel.switch(save, "meadows", True, now=NOW)
        self.assertEqual(save, before)

    def test_world_requirements_honor_original_strict_home_override(self):
        check = creative_worlds.world_requirement_matches
        def item(*requirements, compare="all"):
            return {"requirements": {"compare": compare, "requirement": list(requirements)}}
        home = {"className": "World", "name": "farm"}
        meadow = {"className": "World", "name": "meadows"}
        england = {"className": "World", "name": "england"}
        self.assertTrue(check(item(home), "meadows"))
        self.assertTrue(check(item(meadow), "meadows"))
        self.assertFalse(check(item({**home, "strict": "true"}), "meadows"))
        self.assertFalse(check(item(england), "meadows"))
        self.assertTrue(check(item(england, meadow, compare="any"), "meadows"))
        self.assertFalse(check(item(england, meadow), "meadows"))

    def test_meadows_actions_require_valid_world_currency_level_and_land(self):
        from items import get_item_by_name
        save = self.prepare(cash=100)
        self.create(save)
        world_travel.switch(save, "meadows", now=NOW)
        snapshot = {"id": 64001, "className": "Decoration", "itemName": "haybale",
                    "state": "static", "position": {"x": 10, "y": 10, "z": 0}}
        creative_worlds.guard_action(save, "place", snapshot, [])
        before = copy.deepcopy(save)
        bad_items = [dict(get_item_by_name("haybale"), requirements={"requirement":
                       {"className": "World", "name": "england"}}),
                     dict(get_item_by_name("haybale"), requiredLevel="999"),
                     dict(get_item_by_name("haybale"), requirements={"requirement":
                       {"className": "WorldLicense", "name": "england"}})]
        for item in bad_items:
            with mock.patch("items.get_item_by_name", return_value=item), self.assertRaises(ValueError):
                creative_worlds.guard_action(save, "place", snapshot, [])
        with self.assertRaisesRegex(ValueError, "currency"):
            creative_worlds.guard_action(save, "place", snapshot, [{"currency": "jade"}])
        for position in ({"x": -1, "y": 0}, {"x": 50, "y": 1}, {"x": 0, "y": 49},
                         {"x": 2, "y": 2, "z": 1}):
            with self.subTest(position=position), self.assertRaises(ValueError):
                creative_worlds.guard_action(save, "plow", {**snapshot, "itemName": None,
                    "className": "Plot", "position": position}, [])
        self.assertEqual(save, before)

    def test_expansions_keep_original_world_order_price_neighbors_and_balances(self):
        from items import get_item_by_name
        save = self.prepare()
        self.create(save)
        world_travel.switch(save, "meadows", now=NOW)
        before = copy.deepcopy(save)
        for name, currency in (("farm14", "coins"), ("xmwfarm16", "coins"),
                               ("xmwfarm14", "cash"), ("xmwfarm14_cash", "cash")):
            with self.subTest(name=name, currency=currency), self.assertRaises(ValueError):
                creative_worlds.expand_farm(save, get_item_by_name(name), currency)
            self.assertEqual(save, before)
        save["userInfo"]["player"]["gold"] = 500000
        self.assertTrue(creative_worlds.expand_farm(save, get_item_by_name("xmwfarm14"), "coins"))
        self.assertEqual((save["world"]["sizeX"], save["world"]["sizeY"]), (58, 58))
        self.assertEqual(save["userInfo"]["player"]["gold"], 0)
        repeated = copy.deepcopy(save)
        self.assertTrue(creative_worlds.expand_farm(save, get_item_by_name("xmwfarm14"), "coins"))
        self.assertEqual(save, repeated)
        save["world"].update(sizeX=106, sizeY=106)
        save["userInfo"]["player"]["gold"] = 4000000
        before = copy.deepcopy(save)
        with self.assertRaisesRegex(ValueError, "neighbors"):
            creative_worlds.expand_farm(save, get_item_by_name("xmwfarm28"), "coins", neighbor_count=44)
        self.assertEqual(save, before)
        creative_worlds.expand_farm(save, get_item_by_name("xmwfarm28"), "coins", neighbor_count=45)
        self.assertEqual(save["world"]["sizeX"], 114)

    def test_cash_expansion_uses_served_experiment_and_original_client_price(self):
        from items import get_item_by_name
        save = self.prepare(cash=62)
        self.create(save)
        world_travel.switch(save, "meadows", now=NOW)
        gold = save["userInfo"]["player"]["gold"]
        item = get_item_by_name("xmwfarm14_cash")
        self.assertEqual((item["archived"], item["experimentGate"]),
                         ("yes", "fv_meadows_1436FC"))
        self.assertTrue(creative_worlds.expand_farm(save, item, "cash"))
        self.assertEqual(save["world"]["sizeX"], 58)
        self.assertEqual(save["userInfo"]["player"]["cash"], 1)
        self.assertEqual(save["userInfo"]["player"]["gold"], gold)
        for name, size, currency in (("xmwfarm38", 146, "coins"),
                                      ("xmwfarm38_cash", 146, "cash"),
                                      ("xmwfarm46_cash", 178, "cash")):
            save["world"].update(sizeX=size, sizeY=size)
            save["userInfo"]["player"].update(gold=8000000, cash=1)
            before = copy.deepcopy(save)
            with self.subTest(name=name):
                creative_worlds.expand_farm(save, get_item_by_name(name), currency)
                self.assertEqual(save["world"]["sizeX"], size + 8)
                balance = "gold" if currency == "coins" else "cash"
                cost = 8000000 if currency == "coins" else 1
                self.assertEqual(save["userInfo"]["player"][balance], before["userInfo"]["player"][balance] - cost)

    def test_plot_footprint_and_original_terrain_sets_gate_placements(self):
        from items import get_item_by_name
        save = self.prepare()
        self.create(save)
        world_travel.switch(save, "meadows", now=NOW)
        crop = {"id": 64001, "className": "Plot", "itemName": "strawberry",
                "state": "planted", "position": {"x": 46, "y": 46, "z": 0}}
        # Ground belongs to Plot, independent of the seed/resource footprint.
        tiny_seed = dict(get_item_by_name("strawberry"), sizeX="1", sizeY="1")
        with mock.patch("items.get_item_by_name", return_value=tiny_seed):
            creative_worlds.guard_action(save, "place", crop, [])
            with self.assertRaisesRegex(ValueError, "Plot class"):
                creative_worlds.guard_action(save, "place", {**crop, "className": "Decoration"}, [])
            for position in ({"x": 47, "y": 0}, {"x": 0, "y": 47}):
                with self.subTest(position=position), self.assertRaisesRegex(ValueError, "outside"):
                    creative_worlds.guard_action(save, "place", {**crop, "position": position}, [])
        before = copy.deepcopy(save)
        for name in ("oyster", "kelp"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "terrain"):
                creative_worlds.guard_action(save, "place", {**crop, "itemName": name}, [])
        amphibious = dict(tiny_seed, terrainSet={"terrain": {"name": "amphibious"}})
        with mock.patch("items.get_item_by_name", return_value=amphibious):
            creative_worlds.guard_action(save, "place", crop, [])
        self.assertEqual(save, before)

    def test_recovered_purchase_prerequisites_and_special_currencies_fail_closed(self):
        from items import get_item_by_name
        save = self.prepare(cash=120)
        self.create(save)
        world_travel.switch(save, "meadows", now=NOW)
        before = copy.deepcopy(save)
        for name in ("airballoontree", "adobebench", "africanhornedcucumber", "adventurerscamp",
                     "1960stvset"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                creative_worlds.guard_market_purchase(save, get_item_by_name(name), neighbor_count=0)
            self.assertEqual(save, before)
        hay = get_item_by_name("haybale")
        for key in ("license", "marketPrereqs", "experimentGate", "experiment",
                    "requiredMastery", "requiredQuest", "purchasePrereqs", "prereqs"):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "prerequisites"):
                creative_worlds.guard_market_purchase(save, dict(hay, **{key: "unrestored"}),
                                                      neighbor_count=0)
        for market in ("berry", "villageCoins", "jade"):
            with self.subTest(market=market), self.assertRaisesRegex(ValueError, "currency"):
                creative_worlds.guard_market_purchase(save, dict(hay, market=market),
                                                      neighbor_count=0)
        snapshot = {"id": 64001, "className": "Building", "itemName": "part_claypot",
                    "state": "static", "position": {"x": 10, "y": 10}}
        with self.assertRaisesRegex(ValueError, "cannot be placed"):
            creative_worlds.guard_action(save, "place", snapshot, [{"isGift": True}])
        self.assertEqual(save, before)

    def test_market_to_storage_purchase_checks_rules_before_payment_or_deposit(self):
        import storage
        from items import get_item_by_name
        save = self.prepare(cash=120)
        self.create(save)
        world_travel.switch(save, "meadows", now=NOW)
        self.seed_inventory_storage(save)
        snapshot = {"id": -16, "className": "StorageBuilding"}
        before = copy.deepcopy(save)
        hay = get_item_by_name("haybale")
        bad_items = [get_item_by_name(name) for name in
                     ("asterhotpink", "airballoontree", "africanhornedcucumber", "adventurerscamp")]
        bad_items += [dict(hay, requiredLevel="999"), dict(hay, buyable="false"),
                      dict(hay, minNeighbors="999"), dict(hay, market="villageCoins")]
        catalog_lookup = storage.get_item_by_name
        for item in bad_items:
            with self.subTest(name=item["name"], item=item), mock.patch(
                    "storage.get_item_by_name", side_effect=lambda name: item if name == item["name"]
                    else catalog_lookup(name)), self.assertRaises(ValueError):
                storage.store_world_item(save, snapshot, {"storedItemName": item["name"],
                    "target": -16, "origin": 0, "resource": 0, "numToStore": 1})
            self.assertEqual(save, before)
        # Preflight the full quantity; a failed direct call cannot charge one
        # unit before finding that the rest of the purchase is unaffordable.
        save["userInfo"]["player"]["gold"] = 100
        before = copy.deepcopy(save)
        with self.assertRaisesRegex(ValueError, "Not enough currency"):
            storage.store_world_item(save, snapshot, {"storedItemName": "haybale",
                "target": -16, "origin": 0, "resource": 0, "numToStore": 2})
        self.assertEqual(save, before)
        with redirect_stdout(io.StringIO()):
            storage.store_world_item(save, snapshot, {"storedItemName": "haybale",
                "target": -16, "origin": 0, "resource": 0})
        self.assertEqual(save["userInfo"]["player"]["gold"], 0)
        self.assertEqual(save["userInfo"]["player"]["storageData"]["-16"][hay["code"]][0], 1)

    def test_inventories_and_ids_stay_separate_across_three_worlds(self):
        import storage
        save = self.prepare()
        home_id = world_travel.next_object_id(save)
        save["world"]["objectsArray"].append({"id": home_id, "className": "Decoration"})
        world_travel.switch(save, "england", True, now=NOW)
        england_id = world_travel.next_object_id(save)
        save["world"]["objectsArray"].append({"id": england_id, "className": "Decoration"})
        self.create(save)
        world_travel.switch(save, "meadows", now=NOW)
        meadow_id = world_travel.next_object_id(save)
        self.assertEqual(len({home_id, england_id, meadow_id}), 3)
        for inactive in (-2, -8):
            with self.assertRaisesRegex(ValueError, "shipping"):
                storage._ensure_building_storage(save, inactive)
        storage._ensure_building_storage(save, -16)
        with self.assertRaisesRegex(ValueError, "home farm only"):
            world_travel.guard_placement(save, {"className": "CraftingCottageBuilding"})

    def test_gateway_decorate_store_reload_and_return_keep_the_selected_farm(self):
        from items import get_item_by_name
        from pyamf import remoting
        save = self.prepare(cash=120)
        home = copy.deepcopy(save["world"])
        self.create(save)
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")
        sequence = 0
        def send(name, params):
            nonlocal sequence
            sequence += 1
            response = self.gateway([self.command(name, params, sequence=sequence)])
            self.assertEqual(response.status_code, 200, response.data[:300])
            return remoting.decode(response.data).bodies[0][1].body["data"][0]["data"]
        send("WorldService.loadOwnWorld", ["meadows", False])
        send("WorldService.performAction", ["place", {"id": 64003,
            "className": "StorageBuilding", "itemName": "toolshedpink", "state": "built",
            "position": {"x": 4, "y": 4, "z": 0}}, []])
        snapshot = {"id": 64001, "className": "Decoration", "itemName": "haybale",
                    "state": "static", "position": {"x": 10, "y": 10, "z": 0}}
        send("WorldService.performAction", ["place", snapshot, []])
        save = self.player.session("fixture-farmer")
        placed = copy.deepcopy(next(obj for obj in save["world"]["objectsArray"] if obj["itemName"] == "haybale"))
        placed["position"] = {"x": 12, "y": 12, "z": 0}
        send("WorldService.performAction", ["move", placed, []])
        item = get_item_by_name("haybale")
        options = {"origin": "0", "cameFromLocation": 0, "resource": placed["id"],
                   "isGift": False, "isStorageWithdrawal": 0,
                   "code": item["code"], "storedItemCode": item["code"],
                   "storedItemName": "haybale", "storedClassName": "Decoration", "target": -16}
        send("WorldService.performAction", ["store", placed, [options]])
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        returned = send("WorldService.loadOwnWorld", ["meadows", True])
        self.assertEqual(returned["user"]["currentWorldType"], "meadows")
        self.assertEqual([obj["itemName"] for obj in returned["world"]["objectsArray"]], ["toolshedpink"])
        self.assertEqual(returned["user"]["player"]["storageData"]["-16"][item["code"]], [1, [], []])
        snapshot["id"] = 64002
        send("WorldService.performAction", ["place", snapshot,
            [{"isInventoryWithdrawal": True, "isStorageWithdrawal": -16}]])
        meadow = copy.deepcopy(self.player.session("fixture-farmer")["world"])
        self.assertEqual(sorted(obj["itemName"] for obj in meadow["objectsArray"]), ["haybale", "toolshedpink"])
        restored = next(obj for obj in meadow["objectsArray"] if obj["itemName"] == "haybale")
        self.assertNotEqual(restored["id"], placed["id"])
        # Travel retires client temporary-ID mappings in every owned snapshot.
        for obj in meadow["objectsArray"]:
            obj.pop("tempId", None)
        self.assertEqual(send("WorldService.loadOwnWorld", ["farm"])["world"], home)
        self.assertEqual(send("WorldService.loadOwnWorld", ["meadows"])["world"], meadow)

    def test_gateway_cannot_plant_another_world_crop_or_skip_an_expansion(self):
        save = self.prepare(cash=120)
        self.create(save)
        world_travel.switch(save, "meadows", now=NOW)
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")
        original = self.path.read_bytes()
        crop = {"id": 64001, "className": "Plot", "itemName": "asterhotpink",
                "state": "planted", "position": {"x": 10, "y": 10, "z": 0}}
        for name, params in (("WorldService.performAction", ["place", crop, []]),
                             ("FarmService.expandFarm", ["xmwfarm16", "coins"])):
            with self.subTest(name=name):
                response = self.gateway([self.command(name, params)])
                fixtures.assert_gateway_rejected(self, response)
                self.assertEqual(self.path.read_bytes(), original)

    def test_gateway_storage_purchase_and_terrain_rejections_preserve_disk_and_memory(self):
        save = self.prepare(cash=120)
        self.create(save)
        world_travel.switch(save, "meadows", now=NOW)
        self.seed_inventory_storage(save)
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")
        original = self.path.read_bytes()
        before = copy.deepcopy(save)
        store = {"id": -16, "className": "StorageBuilding"}
        requests = [self.command("WorldService.performAction", ["store", store,
                    [{"storedItemName": name, "target": -16, "origin": 0, "resource": 0}]])
                    for name in ("asterhotpink", "airballoontree", "africanhornedcucumber")]
        requests.append(self.command("WorldService.performAction", ["place",
            {"id": 64001, "className": "Plot", "itemName": "oyster", "state": "planted",
             "position": {"x": 10, "y": 10, "z": 0}}, []]))
        for request in requests:
            with self.subTest(request=request):
                response = self.gateway([request])
                fixtures.assert_gateway_rejected(self, response)
                self.assertEqual(self.path.read_bytes(), original)
                self.assertEqual(self.player.session("fixture-farmer"), before)


if __name__ == "__main__":
    unittest.main()
