"""Shared Home/England/Meadows accounting; all saves and clocks are disposable."""
import copy
from contextlib import redirect_stdout
import io
import math
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import creative_worlds
import peaceful
import world_travel

NOW = 1800000000
WORLDS = ("farm", "england", "meadows")
EXPANSIONS = {"farm": "farm14", "england": "xukfarm14", "meadows": "xmwfarm14"}


class EnabledFarmRegressionTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    @property
    def save(self):
        return self.player.session("fixture-farmer")

    def prepare(self):
        from game_settings import level_to_xp
        self.path = self.write_fixture()
        self.save["world"]["objectsArray"] = []
        self.save["userInfo"]["player"].update(xp=level_to_xp(15), gold=1000000, cash=120)
        self.save["craftingState"]["unknownQueue"] = [{"retain": "bakery"}]
        with redirect_stdout(io.StringIO()):
            world_travel.switch(self.save, "england", True, now=NOW)
            creative_worlds.create(self.save, "meadows", now=NOW)
            world_travel.switch(self.save, "farm", now=NOW)
        self.persist()

    def persist(self):
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")

    def reload(self):
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()

    def send(self, name, params, *, now=NOW):
        self._gateway_sequence = getattr(self, "_gateway_sequence", 0) + 1
        with mock.patch("commands.timestamp_now", return_value=now), mock.patch("engine.timestamp_now", return_value=now):
            response = self.gateway([self.command(name, params, sequence=self._gateway_sequence)])
        self.assertEqual(response.status_code, 200, response.data[:300])
        from pyamf import remoting
        return remoting.decode(response.data).bodies[0][1].body["data"][0]["data"]

    def select(self, world, *, now=NOW):
        self.send("WorldService.loadOwnWorld", [world], now=now)

    def action(self, action, snapshot, options=(), *, now=NOW):
        return self.send("WorldService.performAction", [action, snapshot, list(options)], now=now)

    def seed_inventory_storage(self):
        # These tests start with empty local layouts. Ordinary inventory
        # requires an actual built storage contributor on each active farm.
        obj = {"id": world_travel.next_object_id(self.save), "className": "StorageBuilding",
               "itemName": "toolshedpink", "state": "built", "contents": [],
               "position": {"x": 4, "y": 4, "z": 0}}
        self.save["world"]["objectsArray"].append(obj)
        # Settle the real ownership ribbon during fixture setup; a later
        # market deposit must not inherit rewards for these seeded buildings.
        import progression
        progression.refresh_owned(self.save)
        progression.take_response(self.save)
        return obj

    def rejected(self, name, params, *, now=NOW):
        self._gateway_sequence = getattr(self, "_gateway_sequence", 0) + 1
        self.persist()
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        with mock.patch("commands.timestamp_now", return_value=now), mock.patch("engine.timestamp_now", return_value=now):
            response = self.gateway([self.command(name, params, sequence=self._gateway_sequence)])
        fixtures.assert_gateway_rejected(self, response)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)

    @staticmethod
    def balances(save):
        return {k: save["userInfo"]["player"][k] for k in ("gold", "cash", "xp")}

    def plant(self):
        plot = {"id": 64001, "className": "Plot", "itemName": None, "state": "plowed",
                "position": {"x": 4, "y": 4, "z": 0}, "plantTime": 0}
        ident = self.action("plow", plot)["id"]
        plot.update(id=ident, itemName="strawberry", state="planted", plantTime=1)
        self.action("place", plot)
        return copy.deepcopy(next(obj for obj in self.save["world"]["objectsArray"] if obj["id"] == ident))

    def test_crop_cost_timer_yield_retry_reload_and_world_isolation(self):
        from items import get_item_by_name
        item = get_item_by_name("strawberry")
        self.prepare()
        for world in WORLDS:
            with self.subTest(world=world):
                self.select(world)
                inactive = copy.deepcopy(self.save[world_travel.STATE_KEY]["inactive"])
                before = self.balances(self.save)
                crop = self.plant()
                self.assertEqual(crop["plantTime"], NOW * 1000)
                self.assertEqual(self.balances(self.save), dict(before,
                    gold=before["gold"] - 15 - int(item["cost"]), xp=before["xp"] + 1 + int(item["plantXp"])))
                paid = self.balances(self.save)
                self.action("place", dict(crop, plantTime=1))
                self.assertEqual(self.balances(self.save), paid)
                # A move cannot backdate the timer or assert readiness.
                self.action("move", dict(crop, plantTime=1, state="grown"))
                self.assertEqual(self.save["world"]["objectsArray"][0]["plantTime"], NOW * 1000)
                harvest = dict(crop, state="fallow", plantTime=1)
                self.rejected("WorldService.performAction", ["harvest", harvest, []], now=NOW + 1)
                self.reload()
                ready = NOW + math.ceil(peaceful.grow_seconds(item))
                gold = self.save["userInfo"]["player"]["gold"]
                self.action("harvest", harvest, now=ready)
                self.action("harvest", harvest, now=ready)
                self.assertEqual(self.save["userInfo"]["player"]["gold"], gold + int(item["coinYield"]))
                self.assertEqual(self.save["world"]["objectsArray"][0]["state"], "fallow")
                self.assertEqual(self.save[world_travel.STATE_KEY]["inactive"], inactive)
                self.assertEqual(self.save["craftingState"]["unknownQueue"], [{"retain": "bakery"}])

    def test_crop_currency_world_and_insufficient_funds_fail_atomically(self):
        self.prepare()
        for world in WORLDS:
            self.select(world)
            empty = {"id": 64001, "className": "Plot", "itemName": None, "state": "plowed",
                     "plantTime": 0, "position": {"x": 4, "y": 4, "z": 0}}
            ident = self.action("plow", empty)["id"]
            crop = {"id": ident, "className": "Plot", "itemName": "strawberry", "state": "planted",
                    "plantTime": 1, "position": {"x": 4, "y": 4, "z": 0}}
            for currency in ("cash", "jade"):
                with self.subTest(world=world, currency=currency):
                    self.rejected("WorldService.performAction", ["place", crop, [{"currency": currency}]])
            self.save["userInfo"]["player"]["gold"] = 0
            self.rejected("WorldService.performAction", ["place", crop, []])
            self.save["userInfo"]["player"]["gold"] = 1000000
            from items import get_item_by_name
            item = dict(get_item_by_name("strawberry"), requirements={"requirement":
                {"className": "World", "name": "hawaii"}})
            with mock.patch("commands.get_item_by_name", return_value=item), mock.patch("items.get_item_by_name", return_value=item):
                self.rejected("WorldService.performAction", ["place", crop, []])

    def test_offline_growth_preserves_real_timers_on_all_owned_farms(self):
        self.prepare()
        for world in WORLDS:
            self.select(world)
            self.plant()
        before = self.balances(self.save)
        self.reload()
        for world in WORLDS:
            self.select(world, now=NOW + 90 * 86400)
            crop = self.save["world"]["objectsArray"][0]
            self.assertEqual((crop["state"], crop["plantTime"]), ("grown", NOW * 1000))
            self.assertFalse(self.save["witherOn"][world])
        self.assertEqual(self.balances(self.save), before)

    def test_harvest_rejects_invalid_saved_timers_and_unrevived_withered_crops(self):
        self.prepare()
        for world in WORLDS:
            self.select(world)
            crop = self.plant()
            for planted in (True, None, NOW * 1000 + 100000):
                self.save["world"]["objectsArray"][0]["plantTime"] = planted
                self.rejected("WorldService.performAction", ["harvest", dict(crop, state="fallow", plantTime=1), []])
            self.save["world"]["objectsArray"][0].update(plantTime=1, state="withered")
            self.save.setdefault("peacefulMode", {})["enabled"] = False
            self.rejected("WorldService.performAction", ["harvest", dict(crop, state="fallow", plantTime=1), []])
            self.save["peacefulMode"]["enabled"] = True

    def test_world_expansions_charge_exact_coins_once_and_keep_other_worlds(self):
        self.prepare()
        for world, cost in (("farm", 10000), ("england", 25000), ("meadows", 500000)):
            with self.subTest(world=world):
                self.select(world)
                before, inactive = self.balances(self.save), copy.deepcopy(self.save[world_travel.STATE_KEY]["inactive"])
                with mock.patch("commands.neighbor_uids", return_value=list(range(8))):
                    self.send("FarmService.expandFarm", [EXPANSIONS[world], "coins"])
                    self.send("FarmService.expandFarm", [EXPANSIONS[world], "coins"])
                self.assertEqual(self.balances(self.save), dict(before, gold=before["gold"] - cost))
                self.assertEqual((self.save["world"]["sizeX"], self.save["world"]["sizeY"]), (58, 58))
                self.assertEqual(self.save[world_travel.STATE_KEY]["inactive"], inactive)
        self.reload()
        for world in WORLDS:
            self.select(world)
            self.assertEqual(self.save["world"]["sizeX"], 58)

    def test_cash_expansions_keep_original_one_cash_price_on_all_farms(self):
        self.prepare()
        for world in WORLDS:
            self.select(world)
            before = self.balances(self.save)
            self.send("FarmService.expandFarm", [EXPANSIONS[world] + "_cash", "cash"])
            self.send("FarmService.expandFarm", [EXPANSIONS[world] + "_cash", "cash"])
            self.assertEqual(self.balances(self.save), dict(before, cash=before["cash"] - 1))
            self.assertEqual(self.save["world"]["sizeX"], 58)

    def test_expansion_world_currency_order_funds_and_catalog_gates_fail_atomically(self):
        from items import get_item_by_name
        self.prepare()
        for world in WORLDS:
            self.select(world)
            own = EXPANSIONS[world]
            wrong = "farm14" if world != "farm" else "xukfarm14"
            for name, currency in ((wrong, "coins"), (own, "jade"), (own, "cash"),
                                   (own + "_cash", "coins"), (own.replace("14", "16"), "coins")):
                with self.subTest(world=world, name=name, currency=currency):
                    self.rejected("FarmService.expandFarm", [name, currency])
            self.save["userInfo"]["player"].update(gold=0, cash=0)
            with mock.patch("commands.neighbor_uids", return_value=list(range(8))):
                self.rejected("FarmService.expandFarm", [own, "coins"])
                self.rejected("FarmService.expandFarm", [own + "_cash", "cash"])
            self.save["userInfo"]["player"].update(gold=1000000, cash=60)
            for change in ({"experimentGate": "unrestored"}, {"requiredLevel": "999"},
                           {"minNeighbors": "999"}, {"buyable": "false"}):
                item = dict(get_item_by_name(own), **change)
                with self.subTest(world=world, change=change), mock.patch("commands.get_item_by_name", return_value=item):
                    self.rejected("FarmService.expandFarm", [own, "coins"])

    def test_storage_roundtrip_and_foreign_inventory_rejection_across_three_farms(self):
        from items import get_item_by_name
        self.prepare()
        item = get_item_by_name("haybale")
        for world in WORLDS:
            self.select(world)
            self.seed_inventory_storage()
            inventory = world_travel.SUPPORTED_WORLDS[world]
            snap = {"id": 64001, "className": "Decoration", "itemName": "haybale", "state": "static",
                    "position": {"x": 10, "y": 10, "z": 0}}
            ident = self.action("place", snap)["id"]
            placed = copy.deepcopy(next(obj for obj in self.save["world"]["objectsArray"] if obj["id"] == ident))
            before = self.balances(self.save)
            self.action("store", placed, [{"resource": ident, "target": inventory,
                "storedItemName": "haybale", "origin": 0, "cameFromLocation": 0}])
            self.assertEqual(self.save["userInfo"]["player"]["storageData"][str(inventory)][item["code"]][0], 1)
            self.select(WORLDS[(WORLDS.index(world) + 1) % 3])
            self.reload()
            self.rejected("WorldService.performAction", ["place", dict(snap, id=64002),
                [{"isInventoryWithdrawal": True, "isStorageWithdrawal": inventory}]])
            self.select(world)
            self.action("place", dict(snap, id=64002),
                [{"isInventoryWithdrawal": True, "isStorageWithdrawal": inventory}])
            self.assertNotIn(item["code"], self.save["userInfo"]["player"]["storageData"][str(inventory)])
            self.assertEqual(self.balances(self.save), before)
            self.assertEqual(sorted(obj["itemName"] for obj in self.save["world"]["objectsArray"]),
                             ["haybale", "toolshedpink"])

    def test_unknown_home_and_england_expansion_prerequisites_fail_before_charge(self):
        import commands
        from items import get_item_by_name
        self.prepare()
        for world in ("farm", "england"):
            self.select(world)
            for change in ({"purchasePrereqs": "unknown"}, {"gateCode": "I001"},
                           {"unlock": "unrestored"}, {"requirements": {"requirement":
                               [{"className": "World", "name": world}, {"className": "WorldLicense", "name": world}]}}):
                item = dict(get_item_by_name(EXPANSIONS[world]), **change)
                before = copy.deepcopy(self.save)
                with self.subTest(world=world, change=change), mock.patch("commands.get_item_by_name", return_value=item), \
                        mock.patch("commands.neighbor_uids", return_value=list(range(8))):
                    with self.assertRaisesRegex(ValueError, "additional unlock requirements"):
                        commands.expand_farm("fixture-farmer", item["name"], "coins")
                self.assertEqual(self.save, before)

    def test_market_inventory_wire_uses_negative_container_ids_on_all_farms(self):
        from items import get_item_by_name
        self.prepare()
        item = get_item_by_name("haybale")
        for world in WORLDS:
            self.select(world)
            self.seed_inventory_storage()
            inventory = world_travel.SUPPORTED_WORLDS[world]
            snapshot = {"id": inventory, "className": "StorageBuilding"}
            options = {"storedItemName": "haybale", "target": inventory, "origin": 0, "resource": 0, "numToStore": 2}
            before = self.balances(self.save)
            objects = copy.deepcopy(self.save["world"]["objectsArray"])
            self.action("store", snapshot, [options])
            self.assertEqual(self.balances(self.save), dict(before, gold=before["gold"] - 2 * int(item["cost"])))
            self.assertEqual(self.save["world"]["objectsArray"], objects)
            self.assertEqual(self.save["userInfo"]["player"]["storageData"][str(inventory)][item["code"]][0], 2)
            for currency in ("cash", "jade"):
                self.rejected("WorldService.performAction", ["store", snapshot, [dict(options, currency=currency)]])

    def test_market_inventory_full_quantity_preflight_is_atomic_without_gateway(self):
        import storage
        self.prepare()
        for world in WORLDS:
            self.select(world)
            self.seed_inventory_storage()
            inventory = world_travel.SUPPORTED_WORLDS[world]
            self.save["userInfo"]["player"]["gold"] = 100
            before = copy.deepcopy(self.save)
            with self.subTest(world=world), self.assertRaisesRegex(ValueError, "Not enough currency"):
                storage.store_world_item(self.save, {"id": inventory, "className": "StorageBuilding"},
                    {"storedItemName": "haybale", "target": inventory, "origin": 0, "resource": 0, "numToStore": 2})
            self.assertEqual(self.save, before)

    def test_market_placement_cannot_use_an_absent_price_in_another_currency(self):
        self.prepare()
        for world in WORLDS:
            self.select(world)
            snapshot = {"id": 64001, "className": "Decoration", "itemName": "haybale", "state": "static",
                        "position": {"x": 10, "y": 10, "z": 0}}
            for currency in ("cash", "jade"):
                self.rejected("WorldService.performAction", ["place", snapshot, [{"currency": currency}]])

    def test_equipment_plot_removal_checks_identity_world_and_full_cost_before_mutation(self):
        self.prepare()
        for world in WORLDS:
            self.select(world)
            plot = {"id": 64001, "className": "Plot", "itemName": None, "state": "plowed",
                    "position": {"x": 4, "y": 4, "z": 0}, "plantTime": 0}
            ident = self.action("plow", plot)["id"]
            self.save["userInfo"]["player"]["gold"] = 0
            self.rejected("EquipmentWorldService.onUseEquipment", ["plotRemove", {}, [{"id": ident}], None])
            self.save["userInfo"]["player"]["gold"] = 1000
            self.rejected("EquipmentWorldService.onUseEquipment", ["plotRemove", {},
                [{"id": ident, "worldType": "hawaii"}], None])
            deco = {"id": 64002, "className": "Decoration", "itemName": "haybale", "state": "static",
                    "position": {"x": 10, "y": 10, "z": 0}}
            deco_id = self.action("place", deco)["id"]
            self.rejected("EquipmentWorldService.onUseEquipment", ["plotRemove", {}, [{"id": deco_id}], None])
            before = self.balances(self.save)
            self.send("EquipmentWorldService.onUseEquipment", ["plotRemove", {}, [{"id": ident}], None])
            self.send("EquipmentWorldService.onUseEquipment", ["plotRemove", {}, [{"id": ident}], None])
            self.assertEqual(self.balances(self.save), dict(before, gold=before["gold"] - 15))
            self.assertEqual([obj["id"] for obj in self.save["world"]["objectsArray"]], [deco_id])

    def test_seed_placement_requires_paid_plowed_ground_and_cannot_skip_replowing(self):
        self.prepare()
        for world in WORLDS:
            self.select(world)
            self.save["userInfo"]["player"]["gold"] = 10
            crop = {"id": 64001, "className": "Plot", "itemName": "strawberry", "state": "planted",
                    "plantTime": 0, "position": {"x": 4, "y": 4, "z": 0}}
            self.rejected("WorldService.performAction", ["place", crop, []])
            self.save["userInfo"]["player"]["gold"] = 100
            ident = self.action("plow", dict(crop, itemName=None, state="plowed"))["id"]
            self.save["world"]["objectsArray"][0]["state"] = "fallow"
            self.rejected("WorldService.performAction", ["place", dict(crop, id=ident), []])

    def test_animal_and_tree_moves_preserve_cooldowns_and_cannot_repeat_rewards(self):
        self.prepare()
        for world in WORLDS:
            self.select(world)
            for name, kind in (("cow", "Animal"), ("apple", "Tree")):
                ident = world_travel.next_object_id(self.save)
                obj = {"id": ident, "itemName": name, "className": kind, "state": "bare",
                       "plantTime": NOW * 1000, "position": {"x": 4, "y": 4, "z": 0}}
                self.save["world"]["objectsArray"].append(obj)
                before = self.balances(self.save)
                for attempt in range(2):
                    self.action("move", dict(obj, plantTime=0, state="grown"))
                    self.action("harvest", dict(obj, state="grown", plantTime=0))
                    stored = next(row for row in self.save["world"]["objectsArray"] if row["id"] == ident)
                    self.assertEqual((stored["state"], stored["plantTime"]), ("bare", NOW * 1000))
                self.assertEqual(self.balances(self.save), before)

    def test_expansion_gates_match_both_served_clients_and_england_story_stays_off(self):
        import commands
        import england_progression
        self.assertFalse(england_progression.STORY_ENABLED)
        for name in ("play.html", "ruffle.html"):
            source = (fixtures.ROOT / "templates" / name).read_text()
            for gate in commands._LAND_EXPANSION_EXPERIMENTS:
                self.assertRegex(source, '"' + gate + '":\\s*1\\s*,')


if __name__ == "__main__":
    unittest.main()
