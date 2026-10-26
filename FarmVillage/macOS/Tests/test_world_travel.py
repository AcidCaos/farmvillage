"""Owned-world isolation and original travel wire calls; disposable saves only."""
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures  # Resolve all writable paths before product imports.
from pyamf import remoting
import world_travel


class WorldTravelTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    def prepare(self, level=15):
        from game_settings import level_to_xp
        self.path = self.write_fixture()
        save = self.player.session("fixture-farmer")
        save["userInfo"]["player"]["xp"] = level_to_xp(level)
        save["world"]["unknownImportedField"] = {"unchanged": ["home", 37]}
        save["unknownOtherWorlds"] = {"hawaii": {"uninterpreted": True}}
        save["craftingState"]["unknownQueue"] = ["preserve"]
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")
        return save

    def send(self, params, *, expected=200):
        response = self.gateway([self.command("WorldService.loadOwnWorld", params)])
        fixtures.assert_gateway_status(self, response, expected)
        if expected == 200:
            return remoting.decode(response.data).bodies[0][1].body["data"][0]["data"]

    def reload(self):
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        return self.player.session("fixture-farmer")

    def test_catalog_requirement_and_explicit_local_starter(self):
        save = self.prepare()
        before = copy.deepcopy(save["userInfo"]["player"])
        result = self.send(["england", True, False, False])
        self.assertEqual(world_travel.england_level_requirement(), 15)
        self.assertEqual(result["user"]["currentWorldType"], "england")
        self.assertEqual(result["world"]["localStarter"], "empty-england-v1")
        self.assertEqual((result["world"]["sizeX"], result["world"]["sizeY"]), (50, 50))
        self.assertEqual(result["world"]["objectsArray"], [])
        self.assertEqual(result["user"]["worldSummaryData"]["england"]["storageId"], -8)
        for key in ("gold", "cash", "xp"):
            self.assertEqual(result["user"]["player"][key], before[key])

    def test_rendered_clients_use_compatible_paged_travel_window_for_owned_worlds(self):
        self.prepare()
        with self.client.session_transaction() as session:
            session["UID"] = "fixture-farmer"
        # TravelNameDisplay enables the full window only for variants 2/3.
        # Sorting=0 selects the original asset with slots1_mc through slots4_mc
        # and paging; V4 (sorting=1) has only slots4_mc and breaks small farms.
        # Sasha<=1 copies owned world IDs instead of advertising static worlds
        # such as the unsupported Angler. See TRAVEL_WINDOW_RECOVERY.md.
        for route in ("/play.html", "/ruffle.html"):
            with self.subTest(route=route), mock.patch.object(
                    self.server, "NATIVE_WRAPPER", route == "/ruffle.html"):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                for flag, value in (("fv_xas_traveldialog", 2),
                                    ("fv_travel_window_sorting_preference", 0),
                                    ("fv_sasha_the_grocer", 1)):
                    self.assertRegex(html, r'"%s":\s*%d\s*,' % (flag, value))

    def test_original_all_access_gateway_unlocks_without_leaving_home(self):
        save = self.prepare()
        home = copy.deepcopy(save["world"])
        home_summary = copy.deepcopy(save["userInfo"]["worldSummaryData"]["farm"])
        balances = {k: save["userInfo"]["player"][k] for k in ("cash", "gold", "xp")}
        response = self.gateway([self.command("EnglandService.unlockEnglandWorld", ["allAccess"])])
        self.assertEqual(response.status_code, 200, response.data[:300])
        result = remoting.decode(response.data).bodies[0][1].body["data"][0]["data"]
        self.assertIsInstance(result, list)
        self.assertEqual(result, [])
        save = self.reload()
        self.assertEqual(save["userInfo"]["currentWorldType"], "farm")
        self.assertEqual(save["world"], home)
        self.assertEqual(save["userInfo"]["worldSummaryData"]["farm"], home_summary)
        self.assertIn("england", save["userInfo"]["unlockedWorldTypes"])
        self.assertEqual({k: save["userInfo"]["player"][k] for k in balances}, balances)
        england = copy.deepcopy(save[world_travel.STATE_KEY]["inactive"]["england"])
        self.assertEqual(england["localStarter"], "empty-england-v1")
        self.assertEqual(self.send(["england", False])["world"], england)

    def test_unlock_preserves_live_home_temp_ids_and_is_idempotent(self):
        save = self.prepare()
        save["world"]["objectsArray"][0]["tempId"] = 64001
        home = save["world"]
        before = copy.deepcopy(home)
        self.assertEqual(world_travel.unlock_england(save, "allAccess", now=100), [])
        self.assertIs(save["world"], home)
        self.assertEqual(home, before)
        unlocked = copy.deepcopy(save)
        self.assertEqual(world_travel.unlock_england(save, "allAccess", now=200), [])
        self.assertEqual(save, unlocked)
        world_travel.switch(save, "england", now=300)
        away = copy.deepcopy(save)
        self.assertEqual(world_travel.unlock_england(save, "allAccess", now=400), [])
        self.assertEqual(save, away)

    def test_unlock_from_another_owned_farm_keeps_that_farm_active(self):
        # Browser 2026-10-23: level 15 reached, then Lighthouse Cove opened first;
        # the load-time unlock was refused and the Cove client went out of sync.
        save = self.prepare()
        home = copy.deepcopy(save["world"])
        world_travel.unlock_fisherman(save, "generalAccess", now=1_800_000_050)
        world_travel.switch(save, "fisherman", now=1_800_000_060)
        cove = save["world"]
        cove_before = copy.deepcopy(cove)
        balances = {k: save["userInfo"]["player"][k] for k in ("cash", "gold", "xp")}
        self.assertEqual(world_travel.unlock_england(save, "allAccess", now=100), [])
        self.assertIs(save["world"], cove)
        self.assertEqual(cove, cove_before)
        self.assertEqual(save["userInfo"]["currentWorldType"], "fisherman")
        inactive = save[world_travel.STATE_KEY]["inactive"]
        self.assertEqual(inactive["farm"], home)
        self.assertEqual(inactive["england"]["localStarter"], "empty-england-v1")
        self.assertNotIn("fisherman", inactive)
        self.assertEqual({k: save["userInfo"]["player"][k] for k in balances}, balances)
        unlocked = copy.deepcopy(save)
        self.assertEqual(world_travel.unlock_england(save, "allAccess", now=200), [])
        self.assertEqual(save, unlocked)

    def test_imported_world_cannot_alias_owned_inventory_on_reload_or_travel(self):
        save = self.prepare()
        world_travel.unlock_england(save, "allAccess", now=1_800_000_000)
        for storage_id in (-8, "-8", " -8.000 ", "-8e0"):
            with self.subTest(storage_id=storage_id):
                save["userInfo"]["worldSummaryData"]["unrecovered-import"] = {
                    "storageId": storage_id, "importedState": ["preserve"]}
                before = copy.deepcopy(save)
                with self.assertRaisesRegex(ValueError, "shares this farm's inventory ID"):
                    world_travel.validate(save)
                with self.assertRaisesRegex(ValueError, "shares this farm's inventory ID"):
                    world_travel.switch(save, "england", now=1_800_000_001)
                self.assertEqual(save, before)

    def test_invalid_unlock_access_level_or_missing_snapshot_preserves_save(self):
        save = self.prepare(level=14)
        before = copy.deepcopy(save)
        for access in ("allAccess", "earlyAccess", None, {}, []):
            with self.subTest(access=access), self.assertRaises(ValueError):
                world_travel.unlock_england(save, access, now=100)
            self.assertEqual(save, before)
        save = self.prepare()
        save["userInfo"].setdefault("unlockedWorldTypes", ["farm"]).append("england")
        before = copy.deepcopy(save)
        with self.assertRaisesRegex(ValueError, "snapshot is missing"):
            world_travel.unlock_england(save, "allAccess", now=100)
        self.assertEqual(save, before)

    def test_switch_reload_return_preserves_worlds_and_unknown_imported_state(self):
        save = self.prepare()
        home = copy.deepcopy(save["world"])
        self.send(["england", True, False, False])
        save = self.player.session("fixture-farmer")
        save["world"]["unknownImportedField"] = {"england": [3, 4]}
        self.send(["farm", False, False, False])
        self.assertEqual(self.player.session("fixture-farmer")["world"], home)
        self.reload()
        self.send(["england", False, False, False])
        save = self.reload()
        self.assertEqual(save["world"]["unknownImportedField"], {"england": [3, 4]})
        self.assertEqual(world_travel.home_world(save), home)
        self.assertEqual(save["unknownOtherWorlds"], {"hawaii": {"uninterpreted": True}})
        self.assertEqual(save["craftingState"]["unknownQueue"], ["preserve"])

    def test_duplicate_create_reuses_world_without_grants_or_reset(self):
        self.prepare()
        self.send(["england", True, False, False])
        save = self.player.session("fixture-farmer")
        save["world"]["marker"] = 19
        uid = save["world"]["uid"]
        for _ in range(2):
            result = self.send(["england", True, False, False])
            self.assertEqual(result["world"]["uid"], uid)
            self.assertEqual(result["world"]["marker"], 19)
        self.send([""])
        result = self.send(["england", True, False, False])
        self.assertEqual(result["world"]["uid"], uid)
        self.assertEqual(result["world"]["marker"], 19)

    def test_level_locked_creation_rolls_back_without_changing_file(self):
        save = self.prepare(level=14)
        before = copy.deepcopy(save)
        original = self.path.read_bytes()
        self.send(["england", True, False, False], expected=400)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.player.session("fixture-farmer"), before)

    def test_missing_creation_opt_in_and_unsupported_worlds_reject(self):
        self.prepare()
        original = self.path.read_bytes()
        for params in (["england"], ["hawaii", True], ["fisherman", True],
                       ["../../farm", True], [None], [1], ["england", "yes"],
                       ["england", True, True], ["england", True, False, True]):
            with self.subTest(params=params):
                self.send(params, expected=400)
                self.assertEqual(self.path.read_bytes(), original)

    def test_existing_missing_world_is_never_replaced_with_empty_starter(self):
        save = self.prepare()
        save["userInfo"]["worldSummaryData"]["england"] = {"storageId": -8, "imported": True}
        before = copy.deepcopy(save)
        with self.assertRaisesRegex(ValueError, "snapshot is missing"):
            world_travel.switch(save, "england", True, now=100)
        self.assertEqual(save, before)

    def test_imported_unlock_without_snapshot_is_never_recreated(self):
        save = self.prepare()
        save["userInfo"]["unlockedWorldTypes"] = ["farm", "england", "hawaii"]
        before = copy.deepcopy(save)
        with self.assertRaisesRegex(ValueError, "snapshot is missing"):
            world_travel.switch(save, "england", True, now=100)
        self.assertEqual(save, before)

    def test_global_ids_include_inactive_worlds_orphan_ledgers_and_never_reuse(self):
        save = self.prepare()
        save["userInfo"]["player"]["storageData"]["62999"] = {}
        world_travel.switch(save, "england", True, now=100)
        ident = world_travel.next_object_id(save)
        self.assertEqual(ident, 65501)
        save["world"]["objectsArray"].append({"id": ident, "className": "Plot"})
        world_travel.switch(save, "farm", now=101)
        self.assertEqual(world_travel.next_object_id(save), ident + 1)
        world_travel.switch(save, "england", now=102)
        save["world"]["objectsArray"].clear()
        self.assertEqual(world_travel.next_object_id(save), ident + 2)

    def test_foreign_object_actions_reject_without_retargeting_home(self):
        save = self.prepare()
        snapshot = copy.deepcopy(save["world"]["objectsArray"][0])
        self.send(["england", True, False, False])
        original = self.path.read_bytes()
        for action in ("move", "sell", "clear", "plow", "store"):
            with self.subTest(action=action):
                response = self.gateway([self.command("WorldService.performAction", [action, snapshot, []])])
                fixtures.assert_gateway_rejected(self, response)
                self.assertEqual(self.path.read_bytes(), original)

    def test_plow_in_england_and_home_uses_distinct_ids_and_persists(self):
        self.prepare()
        self.send(["england", True, False, False])
        ids = []
        for name in ("england", "farm"):
            self.send([name])
            snapshot = {"id": 64001, "className": "Plot", "itemName": None,
                        "state": "plowed", "position": {"x": 10, "y": 10, "z": 0}}
            response = self.gateway([self.command("WorldService.performAction", ["plow", snapshot, []])])
            self.assertEqual(response.status_code, 200, response.data[:300])
            ids.append(remoting.decode(response.data).bodies[0][1].body["data"][0]["data"]["id"])
        self.assertNotEqual(*ids)
        save = self.reload()
        self.assertIn(ids[1], [obj["id"] for obj in save["world"]["objectsArray"]])
        self.assertEqual(save[world_travel.STATE_KEY]["inactive"]["england"]["objectsArray"][0]["id"], ids[0])

    def test_positive_inactive_building_storage_is_inaccessible(self):
        import storage
        save = self.prepare()
        building_id = save["world"]["objectsArray"][0]["id"]
        save["userInfo"]["player"]["storageData"][str(building_id)] = {"cow": [1, [], []]}
        world_travel.switch(save, "england", True, now=100)
        before = copy.deepcopy(save)
        with self.assertRaisesRegex(ValueError, "owned world"):
            storage._ensure_building_storage(save, building_id)
        self.assertEqual(save, before)

    def test_world_inventory_storage_groups_remain_separate(self):
        save = self.prepare()
        save["userInfo"]["player"]["storageData"]["-2"] = {"home-code": [2, [], []]}
        self.send(["england", True])
        save = self.player.session("fixture-farmer")
        save["userInfo"]["player"]["storageData"]["-8"] = {"england-code": [3, [], []]}
        self.send([""])
        save = self.reload()
        self.assertEqual(save["userInfo"]["player"]["storageData"]["-2"], {"home-code": [2, [], []]})
        self.assertEqual(save["userInfo"]["player"]["storageData"]["-8"], {"england-code": [3, [], []]})

    def test_original_inventory_store_and_use_survive_travel_and_reload(self):
        from items import get_item_by_name
        save = self.prepare()
        save["userInfo"]["player"]["cash"] = 22
        self.send(["england", True])
        response = self.gateway([self.command("WorldService.performAction", ["place",
            {"id": 64003, "className": "StorageBuilding", "itemName": "toolshedpink", "state": "built",
             "position": {"x": 4, "y": 4, "z": 0}}, []])])
        fixtures.assert_gateway_status(self, response, 200)
        item = get_item_by_name("haybale")
        snapshot = {"id": 64001, "className": "Decoration", "itemName": "haybale",
                    "state": "static", "position": {"x": 10, "y": 10, "z": 0}}
        response = self.gateway([self.command("WorldService.performAction", ["place", snapshot, []], sequence=2)])
        fixtures.assert_gateway_status(self, response, 200)
        save = self.player.session("fixture-farmer")
        placed = copy.deepcopy(next(obj for obj in save["world"]["objectsArray"] if obj.get("itemName") == "haybale"))
        original_id = placed["id"]
        balances = {k: save["userInfo"]["player"][k] for k in ("gold", "cash", "xp")}
        # MapResource.onAddToInventory queues TInventoryStore(resource, 0,
        # resource.getId(), false). Its save snapshot still describes the
        # placed decoration; its params name the active world's inventory.
        options = {"origin": "0", "cameFromLocation": 0, "resource": original_id,
                   "isGift": False, "isStorageWithdrawal": 0,
                   "code": item["code"], "storedItemCode": item["code"],
                   "storedItemName": "haybale", "storedClassName": "Decoration",
                   "target": -8, "currency": None, "metadata": None}
        response = self.gateway([self.command("WorldService.performAction", ["store", placed, [options]], sequence=3)])
        fixtures.assert_gateway_status(self, response, 200)
        save = self.reload()
        self.assertEqual([obj["itemName"] for obj in save["world"]["objectsArray"]], ["toolshedpink"])
        self.assertEqual(save["userInfo"]["player"]["storageData"]["-8"][item["code"]], [1, [], []])
        home = self.send(["farm", True])
        self.assertNotIn(item["code"], home["user"]["player"]["storageData"].get("-2", {}))
        self.reload()
        away = self.send(["england", True])
        self.assertEqual([obj["itemName"] for obj in away["world"]["objectsArray"]], ["toolshedpink"])
        self.assertEqual(away["user"]["player"]["storageData"]["-8"][item["code"]], [1, [], []])
        # BaseStorageSlot.onUseClick supplies the exact selected storage ID;
        # a withdrawal creates a fresh object without paying for it again.
        snapshot["id"] = 64002
        response = self.gateway([self.command("WorldService.performAction",
            ["place", snapshot, [{"isGift": False, "isInventoryWithdrawal": True,
                                  "isStorageWithdrawal": -8}]], sequence=4)])
        fixtures.assert_gateway_status(self, response, 200)
        save = self.reload()
        self.assertNotIn(item["code"], save["userInfo"]["player"]["storageData"]["-8"])
        self.assertEqual(len(save["world"]["objectsArray"]), 2)
        placed = next(obj for obj in save["world"]["objectsArray"] if obj["itemName"] == "haybale")
        self.assertGreater(placed["id"], original_id)
        self.assertEqual({k: save["userInfo"]["player"][k] for k in balances}, balances)

    def test_legacy_empty_storage_contents_repair_both_worlds_without_losing_imported_data(self):
        save = self.prepare()
        world_travel.switch(save, "england", True, now=100)
        home = world_travel.home_world(save)
        home["objectsArray"].append({"id": 701, "className": "StorageBuilding",
            "itemName": "toolshedpink", "contents": {}, "imported": {"keep": True}})
        save["world"]["objectsArray"] = [
            {"id": 702, "className": "StorageBuilding", "itemName": "toolshedpink", "contents": {}},
            {"id": 703, "className": "Decoration", "itemName": "haybale", "contents": {}},
            {"id": 704, "className": "StorageBuilding", "itemName": "toolshedpink", "contents": {"retain": 3}},
            {"id": 705, "className": "StorageBuilding", "itemName": "toolshedpink",
             "contents": [{"itemCode": "HB", "numItem": 2, "imported": "retain"}]},
        ]
        save["userInfo"]["player"]["storageData"].update({"701": {"HB": [1, ["sender"], ["metadata"]]},
                                                               "705": {"HB": [2, [], []]}})
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")
        original = self.path.read_bytes()
        response = self.gateway([self.command("UserService.initUser", ["Storage fixture", 0, True, None]),
                                 self.command("WorldService.loadOwnWorld", ["hawaii", True], 2)])
        fixtures.gateway_results(self, response, [0, 29])
        self.assertEqual(json.loads(self.path.read_text())["world"]["objectsArray"][0]["contents"], [])
        initialized = self.gateway([self.command("UserService.initUser", ["Storage fixture", 0, True, None])])
        self.assertEqual(initialized.status_code, 200, initialized.data[:300])
        loaded = remoting.decode(initialized.data).bodies[0][1].body["data"][0]["data"]
        self.assertEqual([obj["contents"] for obj in loaded["world"]["objectsArray"]],
                         [[], {}, {"retain": 3}, [{"itemCode": "HB", "numItem": 2, "imported": "retain"}]])
        save = self.reload()
        self.assertEqual(world_travel.home_world(save)["objectsArray"][-1]["contents"], [])
        self.assertEqual(world_travel.home_world(save)["objectsArray"][-1]["imported"], {"keep": True})
        self.assertEqual(save["userInfo"]["player"]["storageData"]["701"], {"HB": [1, ["sender"], ["metadata"]]})
        # A running client's empty-object move snapshot must not replace
        # populated storage rows or their imported metadata.
        response = self.gateway([self.command("WorldService.performAction", ["move",
            {"id": 705, "className": "StorageBuilding", "itemName": "toolshedpink", "contents": {},
             "position": {"x": 12, "y": 15, "z": 0}}, []])])
        self.assertEqual(response.status_code, 200, response.data[:300])
        self.assertEqual(self.reload()["world"]["objectsArray"][-1]["contents"],
                         [{"itemCode": "HB", "numItem": 2, "imported": "retain"}])

    def test_original_empty_or_omitted_storage_purchase_contents_reload_in_both_worlds(self):
        for destination in ("farm", "england"):
            for include_contents in (False, True):
                with self.subTest(destination=destination, include_contents=include_contents):
                    save = self.prepare()
                    save["userInfo"]["player"].update(cash=10000, gold=100000)
                    self.send(["england", True])
                    self.send([destination, True])
                    snapshot = {"id": 64001, "className": "StorageBuilding", "itemName": "toolshedpink",
                                "state": "built", "position": {"x": 12, "y": 15, "z": 0}}
                    if include_contents:
                        snapshot["contents"] = {}
                    response = self.gateway([self.command("WorldService.performAction", ["place", snapshot, []])])
                    self.assertEqual(response.status_code, 200, response.data[:300])
                    placed = next(obj for obj in self.reload()["world"]["objectsArray"]
                                  if obj.get("itemName") == "toolshedpink")
                    self.assertEqual(placed["contents"], [])
                    alternate = "farm" if destination == "england" else "england"
                    self.send([alternate, True])
                    returned = self.send([destination, True])
                    self.assertEqual(next(obj for obj in returned["world"]["objectsArray"]
                                          if obj["id"] == placed["id"])["contents"], [])
                    initialized = self.gateway([self.command("UserService.initUser", ["Storage fixture", 0, True, None])])
                    self.assertEqual(initialized.status_code, 200)
                    loaded = remoting.decode(initialized.data).bodies[0][1].body["data"][0]["data"]
                    self.assertEqual(next(obj for obj in loaded["world"]["objectsArray"]
                                          if obj["id"] == placed["id"])["contents"], [])

    def test_crafting_cottage_placement_in_england_is_rejected(self):
        save = self.prepare()
        world_travel.switch(save, "england", True, now=100)
        with self.assertRaisesRegex(ValueError, "home farm only"):
            world_travel.guard_placement(save, {"itemName": "craftingbakery", "className": "CraftingCottageBuilding"})

    def test_init_keeps_active_world_but_omits_server_snapshots(self):
        self.prepare()
        self.send(["england", True])
        response = self.gateway([self.command("UserService.initUser", ["Travel fixture", 0, True, None])])
        self.assertEqual(response.status_code, 200, response.data[:300])
        result = remoting.decode(response.data).bodies[0][1].body["data"][0]["data"]
        self.assertEqual(result["userInfo"]["currentWorldType"], "england")
        self.assertIn("england", result["userInfo"]["unlockedWorldTypes"])
        self.assertNotIn(world_travel.STATE_KEY, result)
        self.assertIn(world_travel.STATE_KEY, json.loads(self.path.read_text()))

    def test_temp_ids_removed_from_every_snapshot_on_save_and_login(self):
        save = self.prepare()
        world_travel.switch(save, "england", True, now=100)
        home = world_travel.home_world(save)
        home["objectsArray"][0]["tempId"] = 64000
        save["world"]["objectsArray"].append({"id": 200, "className": "Plot", "tempId": 64001})
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")
        disk = json.loads(self.path.read_text())
        self.assertTrue(all("tempId" not in obj for world in world_travel.worlds(disk) for obj in world["objectsArray"]))
        world_travel.clear_temporary_ids(save)
        self.assertTrue(all("tempId" not in obj for world in world_travel.worlds(save) for obj in world["objectsArray"]))

    def test_gateway_later_error_preserves_completed_switch(self):
        self.prepare()
        original = self.path.read_bytes()
        response = self.gateway([self.command("WorldService.loadOwnWorld", ["england", True]),
                                 self.command("WorldService.loadOwnWorld", ["hawaii", True], 2)])
        fixtures.gateway_results(self, response, [0, 29])
        self.assertEqual(json.loads(self.path.read_text())["userInfo"]["currentWorldType"], "england")
        self.assertEqual(self.player.session("fixture-farmer")["userInfo"]["currentWorldType"], "england")

    def test_save_failure_rolls_back_world_snapshot_and_current_type(self):
        self.prepare()
        original = self.path.read_bytes()
        with mock.patch.object(self.player, "commit_json_batch", side_effect=OSError("test disk failure")):
            with self.assertRaisesRegex(OSError, "test disk failure"):
                self.send(["england", True])
        self.assertEqual(self.path.read_bytes(), original)
        self.assertNotIn(world_travel.STATE_KEY, self.player.session("fixture-farmer"))

    def test_invalid_inactive_snapshot_rejects_save_without_losing_original(self):
        save = self.prepare()
        self.send(["england", True])
        save = self.player.session("fixture-farmer")
        original = self.path.read_bytes()
        save["world"]["objectsArray"].append(copy.deepcopy(world_travel.home_world(save)["objectsArray"][0]))
        with self.assertRaisesRegex(ValueError, "colliding"):
            self.player.save_session("fixture-farmer")
        self.assertEqual(self.path.read_bytes(), original)

    def test_neighbor_visit_and_help_still_target_home_while_owner_away(self):
        save = self.prepare()
        self.write_fixture("neighbor.json", "neighbor")
        host = self.player.session("neighbor")
        from game_settings import level_to_xp
        host["userInfo"]["player"]["xp"] = level_to_xp(15)
        world_travel.switch(host, "england", True, now=100)
        from commands import load_neighbor_world, neighbor_act
        result = load_neighbor_world("fixture-farmer", "neighbor")
        self.assertEqual(result["user"]["currentWorldType"], "farm")
        self.assertEqual(result["world"]["objectsArray"], world_travel.home_world(host)["objectsArray"])
        snapshot = copy.deepcopy(world_travel.home_world(host)["objectsArray"][1])
        snapshot["state"] = "plowed"
        with redirect_stdout(io.StringIO()):
            neighbor_act("fixture-farmer", "neighbor", "plow", snapshot)
        self.assertEqual(host["world"]["objectsArray"], [])
        self.assertEqual(world_travel.home_world(host)["objectsArray"][1]["state"], "plowed")
        self.assertEqual(json.loads((self.saves / "neighbor.json").read_text())["userInfo"]["currentWorldType"], "england")

    def test_explicit_world_mismatch_is_rejected_before_mutation(self):
        self.prepare()
        self.send(["england", True])
        original = self.path.read_bytes()
        snapshot = {"id": 64001, "className": "Plot", "itemName": None,
                    "state": "plowed", "position": {"x": 10, "y": 10, "z": 0}}
        for raw, params in (({**snapshot, "worldType": "farm"}, []),
                            (snapshot, [{"currentWorldType": "farm"}])):
            response = self.gateway([self.command("WorldService.performAction", ["plow", raw, params])])
            fixtures.assert_gateway_rejected(self, response)
            self.assertEqual(self.path.read_bytes(), original)

    def test_inactive_inventory_requires_shipping_support(self):
        import storage
        save = self.prepare()
        world_travel.switch(save, "england", True, now=100)
        with self.assertRaisesRegex(ValueError, "[Ss]hipping"):
            storage._ensure_building_storage(save, -2)
        storage._ensure_building_storage(save, -8)
        storage._ensure_building_storage(save, -1)

    def test_ownership_counts_include_home_after_travel(self):
        import progression
        save = self.prepare()
        progression.refresh_owned(save)
        buildings = save["userInfo"]["player"]["stats"]["buildings"]
        self.assertGreater(buildings, 0)
        world_travel.switch(save, "england", True, now=100)
        progression.refresh_owned(save)
        self.assertEqual(save["userInfo"]["player"]["stats"]["buildings"], buildings)

    def test_breeding_inventory_fallback_uses_active_world_and_preserves_dna(self):
        import breeding
        import items
        save = self.prepare()
        world_travel.switch(save, "england", True, now=100)
        name = "sheeppen_ram"
        item = items.get_item_by_name(name)
        dna = breeding._config()["variants"][name]
        packed = json.dumps(dna)
        save["userInfo"]["player"]["storageData"]["-8"][item["code"]] = [1, [], [packed]]
        snapshot = {"id": 200, "itemName": name, "className": "MutableAnimal"}
        self.assertTrue(breeding.withdraw_for_placement(save, name,
            [{"isInventoryWithdrawal": True, "metadata": packed}], snapshot, now=100))
        self.assertEqual(snapshot["mutableAnimalState"]["dna"], dna)
        self.assertNotIn(item["code"], save["userInfo"]["player"]["storageData"]["-8"])

    def test_specialized_sheep_inventory_cannot_withdraw_from_inactive_world(self):
        import breeding
        import items
        save = self.prepare()
        name = "sheeppen_ram"
        item = items.get_item_by_name(name)
        packed = json.dumps(breeding._config()["variants"][name])
        save["userInfo"]["player"]["storageData"].setdefault("-2", {})[item["code"]] = [1, [], [packed]]
        world_travel.switch(save, "england", True, now=100)
        before = copy.deepcopy(save)
        snapshot = {"id": 200, "itemName": name, "className": "MutableAnimal"}
        with self.assertRaisesRegex(ValueError, "[Ss]hipping"):
            breeding.withdraw_for_placement(save, name,
                [{"isStorageWithdrawal": -2, "metadata": packed}], snapshot, now=100)
        self.assertEqual(save, before)

    def test_peaceful_mode_sets_active_world_without_losing_original_policy(self):
        self.prepare()
        self.send(["england", True])
        save = self.player.session("fixture-farmer")
        self.assertIs(save["witherOn"]["england"], False)
        original = copy.deepcopy(save["peacefulMode"]["originalWitherOn"])
        self.send(["farm"])
        self.assertEqual(self.player.session("fixture-farmer")["peacefulMode"]["originalWitherOn"], original)


if __name__ == "__main__":
    unittest.main()
