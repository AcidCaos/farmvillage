"""Lighthouse Cove access and shared-engine integration; disposable saves only."""
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
import cove_rules
import creative_worlds
import world_travel

NOW = 1800000000


class CoveTravelTests(unittest.TestCase):
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

    def prepare(self, *, level=15, cash=0):
        from game_settings import level_to_xp
        self.path = self.write_fixture()
        self.save["userInfo"]["player"].update(xp=level_to_xp(level), cash=cash, gold=1000000)
        self.save["unknownImportedWorlds"] = {"hawaii": {"keep": [1, 2]}}
        self.save["craftingState"]["unknownQueue"] = [{"keep": "home"}]
        self.persist()
        return self.save

    def persist(self):
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")

    def unlock(self, option="allAccess"):
        return creative_worlds.create(self.save, "fisherman", option, now=NOW)

    def select(self):
        self.unlock()
        world_travel.switch(self.save, "fisherman", now=NOW)
        self.persist()

    def send(self, name, params, *, now=NOW, expected=200, sequence=None):
        self._gateway_sequence = getattr(self, "_gateway_sequence", 0) + 1
        if sequence is None:
            sequence = self._gateway_sequence
        self._gateway_sequence = max(self._gateway_sequence, sequence)
        with mock.patch("server.timestamp_now", return_value=now), mock.patch(
                "commands.timestamp_now", return_value=now), mock.patch("engine.timestamp_now", return_value=now):
            response = self.gateway([self.command(name, params, sequence)])
        fixtures.assert_gateway_status(self, response, expected)
        if expected == 200:
            from pyamf import remoting
            return remoting.decode(response.data).bodies[0][1].body["data"][0]["data"]

    def rejected(self, name, params):
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.send(name, params, expected=400)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)

    @staticmethod
    def plot(ident=64001, **changes):
        return dict({"id": ident, "className": "Plot", "itemName": None,
            "state": "plowed", "position": {"x": 4, "y": 4, "z": 0}, "plantTime": 0}, **changes)

    def test_free_unlock_preserves_active_world_and_grants_nothing_else(self):
        self.prepare()
        before = copy.deepcopy(self.save)
        self.assertTrue(self.unlock("generalAccess"))
        self.assertEqual(self.save["world"], before["world"])
        self.assertEqual(self.save["userInfo"]["currentWorldType"], "farm")
        player = self.save["userInfo"]["player"]
        for key in ("gold", "cash", "xp", "seenFlags"):
            self.assertEqual(player[key], before["userInfo"]["player"][key])
        self.assertEqual(player["storageData"], dict(before["userInfo"]["player"]["storageData"], **{"-9": {}}))
        world = self.save[world_travel.STATE_KEY]["inactive"]["fisherman"]
        self.assertEqual((world["sizeX"], world["sizeY"], world["tileSet"]), (50, 50, "fisherman"))
        self.assertEqual((world["objectsArray"], world["localStarter"]), ([], "empty-fisherman-v1"))
        self.assertEqual(self.save["userInfo"]["worldSummaryData"]["fisherman"]["storageId"], -9)
        self.assertNotIn("rewardCode", self.save[creative_worlds.ACCESS_MARKER]["fisherman"])
        first = copy.deepcopy(self.save)
        self.assertFalse(self.unlock())
        self.assertEqual(self.save, first)

    def test_level_date_option_and_missing_import_snapshot_reject_unchanged(self):
        for failure in ("level", "date", "option", "summary", "unlock", "inventory"):
            with self.subTest(failure=failure):
                self.prepare(level=14 if failure == "level" else 15)
                if failure == "summary":
                    self.save["userInfo"]["worldSummaryData"]["fisherman"] = {"storageId": -9, "imported": True}
                if failure == "unlock":
                    self.save["userInfo"].setdefault("unlockedWorldTypes", ["farm"]).append("fisherman")
                if failure == "inventory":
                    self.save["userInfo"]["player"]["storageData"]["-9"] = {"HB": [1, [], []]}
                before = copy.deepcopy(self.save)
                with self.assertRaises(ValueError):
                    creative_worlds.create(self.save, "fisherman", "earlyAccess" if failure == "option"
                        else "allAccess", now=1 if failure == "date" else NOW)
                self.assertEqual(self.save, before)

    def test_candidate_and_page_disclose_free_option_without_meadows_rewards(self):
        self.prepare()
        row = next(row for row in creative_worlds.candidates(self.save) if row["worldType"] == "fisherman")
        self.assertEqual((row["option"], row["cashCost"], row["minimumLevel"]), ("allAccess", 0, 15))
        with self.client.session_transaction() as session:
            session["UID"] = "fixture-farmer"
        page = self.client.get("/farms").get_data(as_text=True)
        cove = page[page.index("<h2>Lighthouse Cove</h2>"):]
        self.assertIn('name="option" value="allAccess"', cove)
        self.assertIn("Add farm · Free", cove)
        self.assertIn("35 ordinary plots", cove)
        self.assertIn("original populated starter not recovered", cove)
        self.assertNotIn("Spooky Lantern Tree", cove)

    def test_http_free_unlock_csrf_retry_and_disk_failure_are_atomic(self):
        self.prepare()
        with self.client.session_transaction() as session:
            session["UID"] = "fixture-farmer"
        self.client.get("/farms")
        with self.client.session_transaction() as session:
            token = session["farms_token"]
        data = dict(token=token, action="purchase", world="fisherman", option="allAccess")
        disk, before = self.path.read_bytes(), copy.deepcopy(self.save)
        self.assertEqual(self.client.post("/farms", data=dict(data, token="wrong")).status_code, 400)
        self.assertEqual(self.path.read_bytes(), disk)
        with mock.patch.object(self.server, "save_session", side_effect=OSError("test disk full")):
            with self.assertRaises(OSError):
                self.client.post("/farms", data=data)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)
        self.assertEqual(self.client.post("/farms", data=data).location, "/farms")
        first = copy.deepcopy(self.save)
        self.assertEqual(self.client.post("/farms", data=data).location, "/farms")
        self.assertEqual(self.save, first)

    def test_original_access_gateway_and_reload_never_charge_or_switch(self):
        self.prepare()
        for option in ("allAccess", "generalAccess"):
            self.assertEqual(self.send("FishermansCoveService.unlockFishermanWorld", [option]), [])
            self.assertEqual(self.save["userInfo"]["currentWorldType"], "farm")
            self.assertEqual(self.save["userInfo"]["player"]["cash"], 0)
        for params in ([], ["earlyAccess"], ["allAccess", "cash55"], [False]):
            self.rejected("FishermansCoveService.unlockFishermanWorld", params)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        first = copy.deepcopy(self.save)
        self.assertFalse(self.unlock())
        self.assertEqual(self.save, first)

    def test_four_world_travel_and_inventory_preserve_imports(self):
        self.prepare(cash=60)
        home = copy.deepcopy(self.save["world"])
        world_travel.switch(self.save, "england", True, now=NOW)
        england = copy.deepcopy(self.save["world"])
        creative_worlds.create(self.save, "meadows", now=NOW)
        self.unlock()
        self.assertEqual(self.save["userInfo"]["currentWorldType"], "england")
        returned = self.send("WorldService.loadOwnWorld", ["fisherman"])
        self.assertEqual(returned["user"]["currentWorldType"], "fisherman")
        self.assertEqual(returned["world"]["tileSet"], "fisherman")
        self.save["world"]["importedMarker"] = {"keep": [7]}
        self.save["userInfo"]["player"]["storageData"]["-9"] = {"HB": [2, [], []]}
        self.persist()
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        import storage
        for group in (-2, -8, -16):
            with self.assertRaisesRegex(ValueError, "shipping"):
                storage._ensure_building_storage(self.save, group)
        self.assertEqual(self.send("WorldService.loadOwnWorld", ["england"])["world"], england)
        self.assertEqual(self.send("WorldService.loadOwnWorld", ["farm"])["world"], home)
        self.assertEqual(self.send("WorldService.loadOwnWorld", ["fisherman"])["world"]["importedMarker"], {"keep": [7]})
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-9"], {"HB": [2, [], []]})
        self.assertEqual(self.save["unknownImportedWorlds"], {"hawaii": {"keep": [1, 2]}})
        self.assertEqual(self.save["craftingState"]["unknownQueue"], [{"keep": "home"}])

    def test_direct_creation_seasons_and_unsupported_services_fail_closed(self):
        self.prepare()
        self.rejected("WorldService.loadOwnWorld", ["fisherman", True])
        self.select()
        for name, params in (("WorldService.loadOwnWorld", ["farm", False, True]),
                ("WorldService.loadOwnWorld", ["farm", False, False, True]),
                ("FishermansCoveService.upgradePort", []),
                ("CraftingService.onUseCraftedGood", ["b0"])):
            self.rejected(name, params)

    def test_exact_initial_plot_cap_counts_all_states_and_retry_is_free(self):
        self.prepare()
        self.select()
        self.save["world"]["objectsArray"] = [self.plot(1000 + i,
            state=("fallow", "planted", "grown", "plowed")[i % 4]) for i in range(34)]
        self.persist()
        ident = self.send("WorldService.performAction", ["plow", self.plot(), []], sequence=201)["id"]
        balances = copy.deepcopy(self.save["userInfo"]["player"])
        self.send("WorldService.performAction", ["plow", self.plot(), []], sequence=201)
        self.assertEqual(self.save["userInfo"]["player"], balances)
        self.assertEqual(len(self.save["world"]["objectsArray"]), 35)
        self.rejected("WorldService.performAction", ["plow", self.plot(64002), []])
        self.assertIn(ident, [obj["id"] for obj in self.save["world"]["objectsArray"]])

    def test_original_fallow_replow_retains_crop_charges_once_and_survives_reload(self):
        self.prepare()
        self.select()
        saved = self.plot(626, itemName="whiteanthuriums", state="fallow",
            plantTime=1792709859000, position={"x": 21, "y": 22, "z": 0},
            importedMarker={"keep": [7]})
        self.save["world"]["objectsArray"] = [saved] + [self.plot(1000 + i) for i in range(34)]
        self.persist()
        # Exact original Plot.executePlow shape from the failed browser request.
        snapshot = dict(saved, state="plowed", tempId=float("nan"), isProduceItem=False,
            isJumbo=False, isBigPlot=False, instanceDataStoreKey=None, deleted=False,
            components={}, direction=0)
        snapshot.pop("importedMarker")
        player = self.save["userInfo"]["player"]
        gold, xp = player["gold"], player["xp"]
        self.assertEqual(self.send("WorldService.performAction", ["plow", snapshot, []])["id"], 626)
        self.assertEqual((player["gold"], player["xp"]), (gold - 15, xp + 1))
        plowed = self.save["world"]["objectsArray"][0]
        self.assertEqual((plowed["state"], plowed["itemName"], plowed["plantTime"]),
                         ("plowed", "whiteanthuriums", 1792709859000))
        self.assertEqual(plowed["importedMarker"], {"keep": [7]})
        self.assertEqual(len(self.save["world"]["objectsArray"]), 35)
        once = copy.deepcopy(self.save)
        self.send("WorldService.performAction", ["plow", snapshot, []])
        self.assertEqual(self.save, once)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        reloaded = copy.deepcopy(self.save)
        self.send("WorldService.performAction", ["plow", snapshot, []])
        self.assertEqual(self.save, reloaded)

    def test_original_zero_clock_replow_after_instant_grow_is_accepted(self):
        # Exact packet captured from the original client on 2026-10-22
        # (instantgrow-browser-server.log): after Instant Grow and harvest the
        # Plot keeps itemName but clears plantTime to 0.
        self.prepare()
        self.select()
        saved = self.plot(626, itemName="blackberriesdarrow", state="fallow",
            plantTime=1792709859000, position={"x": 21, "y": 22, "z": 0})
        self.save["world"]["objectsArray"] = [saved] + [self.plot(1000 + i) for i in range(34)]
        self.persist()
        snapshot = dict(saved, state="plowed", plantTime=0, tempId=float("nan"),
            isProduceItem=False, isJumbo=False, isBigPlot=False,
            instanceDataStoreKey=None, deleted=False, components={}, direction=0)
        player = self.save["userInfo"]["player"]
        gold, xp = player["gold"], player["xp"]
        self.assertEqual(self.send("WorldService.performAction", ["plow", snapshot, []])["id"], 626)
        self.assertEqual((player["gold"], player["xp"]), (gold - 15, xp + 1))
        plowed = self.save["world"]["objectsArray"][0]
        self.assertEqual((plowed["state"], plowed["itemName"], plowed["position"]),
                         ("plowed", "blackberriesdarrow", {"x": 21, "y": 22, "z": 0}))
        self.assertEqual(len(self.save["world"]["objectsArray"]), 35)
        once = copy.deepcopy(self.save)
        self.send("WorldService.performAction", ["plow", snapshot, []])
        self.assertEqual(self.save, once)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        reloaded = copy.deepcopy(self.save)
        self.send("WorldService.performAction", ["plow", snapshot, []])
        self.assertEqual(self.save, reloaded)

    def test_replow_cannot_forge_crop_clock_position_special_plot_or_live_crop(self):
        self.prepare()
        self.select()
        saved = self.plot(626, itemName="whiteanthuriums", state="fallow", plantTime=123000)
        self.save["world"]["objectsArray"] = [saved]
        self.persist()
        incoming = dict(saved, state="plowed")
        # plantTime=0 is legitimate (original client after Instant Grow + harvest);
        # see test_original_zero_clock_replow_after_instant_grow_is_accepted.
        # Any other clock that differs from the saved one is forged.
        for changes in ({"id": 627}, {"itemName": "strawberry"},
                        {"plantTime": 1}, {"plantTime": 124000}, {"plantTime": -1},
                        {"plantTime": "0"}, {"plantTime": None}, {"plantTime": False},
                        {"plantTime": float("nan")},
                        {"className": "Building"}, {"isSuperPlot": True},
                        {"position": {"x": 8, "y": 4, "z": 0}}, {"state": "planted"}):
            with self.subTest(changes=changes):
                self.rejected("WorldService.performAction", ["plow", dict(incoming, **changes), []])
        for state in ("planted", "grown"):
            self.save["world"]["objectsArray"][0]["state"] = state
            self.persist()
            with self.subTest(saved_state=state):
                self.rejected("WorldService.performAction", ["plow", incoming, []])
        self.save["world"]["objectsArray"][0]["state"] = "fallow"
        self.save["userInfo"]["player"]["gold"] = 14
        self.persist()
        self.rejected("WorldService.performAction", ["plow", incoming, []])

    def test_coin_and_cash_expansions_use_next_width_and_exact_caps(self):
        from items import get_item_by_name
        for currency, item_name, cost in (("coins", "xlcfarm14", 25000), ("cash", "xlcfarm14_cash", 1)):
            with self.subTest(currency=currency):
                self.prepare(cash=2)
                self.select()
                player = self.save["userInfo"]["player"]
                key = "cash" if currency == "cash" else "gold"
                before = player[key]
                item = get_item_by_name(item_name)
                creative_worlds.expand_farm(self.save, item, currency)
                self.assertEqual((self.save["world"]["sizeX"], cove_rules.plot_limit(self.save["world"]["sizeX"])), (58, 45))
                self.assertEqual(player[key], before - cost)
                self.assertEqual(self.save["world"]["objectsArray"], [])
                creative_worlds.expand_farm(self.save, item, currency)
                self.assertEqual(player[key], before - cost)

    def test_expansion_world_currency_order_and_special_prereqs_reject_atomically(self):
        self.prepare(cash=100)
        self.select()
        for name, currency in (("farm14", "coins"), ("xmwfarm14", "coins"),
                ("xlcfarm16", "coins"), ("xlcfarm14", "cash"), ("xlcfarm14_cash", "coins")):
            self.rejected("FarmService.expandFarm", [name, currency])
        from items import get_item_by_name
        item = get_item_by_name("xlcfarm14")
        for field in ("gateCode", "limitedStart", "requiredQuest", "purchasePrereqs"):
            before = copy.deepcopy(self.save)
            with self.assertRaises(ValueError):
                creative_worlds.expand_farm(self.save, dict(item, **{field: "unrestored"}), "coins")
            self.assertEqual(self.save, before)

    def test_basic_crop_uses_original_currency_server_timer_and_maturity(self):
        import peaceful
        from items import get_item_by_name
        self.prepare()
        self.select()
        ident = self.send("WorldService.performAction", ["plow", self.plot(), []])["id"]
        crop = self.plot(ident, itemName="strawberry", state="planted", plantTime=1)
        self.send("WorldService.performAction", ["place", crop, []])
        saved = self.save["world"]["objectsArray"][0]
        self.assertEqual(saved["plantTime"], NOW * 1000)
        self.rejected("WorldService.performAction", ["harvest", dict(crop, state="fallow"), []])
        self.rejected("WorldService.performAction", ["harvest", dict(crop, state="fallow", isSuperPlot=True), []])
        self.rejected("WorldService.performAction", ["harvest", dict(crop, state="fallow",
            position={"x": 999, "y": 4, "z": 0}), []])
        ready = NOW + math.ceil(peaceful.grow_seconds(get_item_by_name("strawberry")))
        gold = self.save["userInfo"]["player"]["gold"]
        self.send("WorldService.performAction", ["harvest", dict(crop, state="fallow"), []], now=ready)
        self.assertEqual(self.save["userInfo"]["player"]["gold"], gold + int(get_item_by_name("strawberry")["coinYield"]))

    def test_wrong_world_terrain_special_items_and_plot_flags_never_mutate(self):
        self.prepare()
        self.select()
        for name in ("asterhotpink", "oyster", "craftingbakery", "lighthouse", "pkg_fishermanXfer"):
            snapshot = self.plot(itemName=name, state="planted")
            self.rejected("WorldService.performAction", ["place", snapshot, []])
        for snapshot in (self.plot(isJumbo=True), self.plot(position={"x": 48, "y": 4, "z": 0}),
                         self.plot(position={"x": 4, "y": 4, "z": 1})):
            self.rejected("WorldService.performAction", ["plow", snapshot, []])

    def test_market_to_cove_inventory_is_supported_and_special_currency_rejected(self):
        from items import get_item_by_name
        self.prepare(cash=22)
        self.select()
        self.send("WorldService.performAction", ["place", {"id": 64001,
            "className": "StorageBuilding", "itemName": "toolshedpink", "state": "built",
            "position": {"x": 4, "y": 4, "z": 0}}, []])
        snapshot = {"id": -9, "className": "StorageBuilding"}
        options = {"storedItemName": "haybale", "target": -9, "origin": 0, "resource": 0}
        self.send("WorldService.performAction", ["store", snapshot, [options]])
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-9"][get_item_by_name("haybale")["code"]][0], 1)
        for changes in ({"currency": "jade"}, {"storedItemName": "oyster"}, {"target": -2}):
            self.rejected("WorldService.performAction", ["store", snapshot, [dict(options, **changes)]])

    def test_basic_decoration_place_move_store_and_reload_keep_cove_inventory(self):
        from items import get_item_by_name
        self.prepare(cash=22)
        self.select()
        self.send("WorldService.performAction", ["place", {"id": 64002,
            "className": "StorageBuilding", "itemName": "toolshedpink", "state": "built",
            "position": {"x": 4, "y": 4, "z": 0}}, []])
        snapshot = {"id": 64001, "className": "Decoration", "itemName": "haybale",
            "state": "static", "position": {"x": 8, "y": 8, "z": 0}}
        ident = self.send("WorldService.performAction", ["place", snapshot, []])["id"]
        saved = copy.deepcopy(next(obj for obj in self.save["world"]["objectsArray"] if obj["id"] == ident))
        self.rejected("WorldService.performAction", ["place", dict(snapshot, id=64002, className="Animal"), []])
        saved["position"] = {"x": 12, "y": 12, "z": 0}
        self.send("WorldService.performAction", ["move", saved, []])
        item = get_item_by_name("haybale")
        options = {"origin": 0, "resource": ident, "target": -9,
            "storedItemName": "haybale", "storedItemCode": item["code"], "storedClassName": "Decoration"}
        self.send("WorldService.performAction", ["store", saved, [options]])
        self.assertEqual([obj["itemName"] for obj in self.save["world"]["objectsArray"]], ["toolshedpink"])
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.save["userInfo"]["currentWorldType"], "fisherman")
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-9"][item["code"]], [1, [], []])

    def test_invalid_cove_snapshot_refuses_travel_without_replacing_it(self):
        self.prepare()
        self.unlock()
        self.persist()
        target = self.save[world_travel.STATE_KEY]["inactive"]["fisherman"]
        for changes in ({"tileSet": "grass_theme"}, {"sizeX": 51, "sizeY": 51},
                        {"terrain": {"water": True}}, {"objectsArray": [{"id": 1000, "className": "FishermanPort"}]}):
            original = copy.deepcopy(target)
            target.update(changes)
            before = copy.deepcopy(self.save)
            with self.assertRaises(ValueError):
                world_travel.switch(self.save, "fisherman", now=NOW)
            self.assertEqual(self.save, before)
            target.clear()
            target.update(original)


if __name__ == "__main__":
    unittest.main()
