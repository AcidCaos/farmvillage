"""Original crafting against archived catalogs; all saves/caches are temporary."""
from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures  # Must resolve writable product paths first.
import crafting
import persistence


class CraftingTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture

    def prepare(self, craft="bakery"):
        self.path = self.write_fixture()
        self.save = self.player.session("fixture-farmer")
        self.save["world"]["objectsArray"] = [{"id": 600, "itemName": crafting.COTTAGES[craft],
            "className": "CraftingCottageBuilding", "state": "built", "isFullyBuilt": True,
            "position": {"x": 10, "y": 10, "z": 0}, "imported": {"preserve": [1, 2]}}]
        self.save["craftingState"] = {"craftingItems": [], "maxCapacity": 5,
            "calendarDate": 11, "nextCalendarDate": 12, "importedState": {"keep": True},
            "craftingSkillState": {"recipeStates": [], "importedSkill": [3]}}
        self.save["userInfo"]["player"].update(cash=100, energy=5, storageData={})
        with redirect_stdout(io.StringIO()):
            crafting.start_session(self.save)
            self.player.save_session("fixture-farmer")
        self.sequence = 0
        return self.save

    def call(self, method, params, now=1000, sequence=None):
        if sequence is None:
            self.sequence += 1
            sequence = self.sequence
        self.sequence = max(self.sequence, sequence)
        with redirect_stdout(io.StringIO()):
            return crafting.dispatch(self.save, method, params, now=now, request_id=sequence)

    def purchase(self, code="b0", count=1):
        for ingredient, amount in crafting._ingredients(crafting._recipe(code)).items():
            self.call("FarmService.onPurchaseBushel", [ingredient, code, amount * count])

    def begin(self, code="b0", now=1000):
        return self.call("CraftingService.onBeginRecipe", [code, -1], now)

    def claim(self, code="b0", now=22600):
        return self.call("CraftingService.onClaimFinishedRecipes", [code, -1], now)

    def assert_rejected_without_mutation(self, method, params, **kw):
        before = copy.deepcopy(self.save)
        with self.assertRaises(ValueError):
            self.call(method, params, **kw)
        self.assertEqual(self.save, before)

    def test_archived_catalog_and_wire_schema_are_authoritative(self):
        self.prepare()
        self.assertEqual(crafting._ingredients(crafting._recipe("b0")), {"pu": 4, "wh": 4})
        self.assertEqual(crafting._ingredients(crafting._recipe("lq")), {"kc": 4, "np": 4})
        self.assertEqual(crafting._ingredients(crafting._recipe("lj")), {"yy": 3, "np": 2, "qc": 2})
        self.purchase()
        record = self.begin()
        self.assertEqual((record["id"], record["start_ts"], record["finish_ts"], record["ovenSlot"]), ("b0", 1000, 22600, 0))
        self.assertEqual(record["recipe"]["name"], "pumpkinbread")
        self.assertEqual(record["recipe"]["Reward"]["OnFinish"]["@attributes"],
                         {"itemCode": "b0", "sellQty": "2", "giftQty": "1"})
        self.assertEqual(record["recipe"]["Ingredients"]["Ingredient"][0]["@attributes"],
                         {"itemCode": "pu", "quantityRequired": "4"})

    def test_dialog_recipe_states_include_locked_catalog_goods_without_enabling_production(self):
        for craft in crafting.HOME_COTTAGES:
            with self.subTest(craft=craft):
                self.prepare(craft)
                rows = self.save["craftingState"]["craftingSkillState"]["recipeStates"]
                states = {row["m_type"]: row for row in rows}
                catalog = [r for r in crafting._catalog()[0].find("recipes")
                           if r.findtext("craft") == craft and r.findtext("Deprecated") == "0"]
                self.assertEqual(set(states), {r.get("id") for r in catalog})
                for recipe in catalog:
                    code = recipe.get("id")
                    self.assertEqual(states[code], {"m_type": code,
                        "m_level": int(recipe.findtext("InitialRecipeLevel")),
                        "m_experience": 0, "m_isUnlocked": code in crafting.RECIPES
                        and int(recipe.findtext("SkillLevelRequired")) <= 1})
                unsupported = next(code for code in states if not states[code]["m_isUnlocked"])
                self.assert_rejected_without_mutation("CraftingService.onBeginRecipe", [unsupported, -1])
                states[unsupported]["importedState"] = {"keep": True}
                states[unsupported]["m_experience"] = 7
                before = copy.deepcopy(rows)
                crafting.initialize(self.save)
                self.assertEqual(self.save["craftingState"]["craftingSkillState"]["recipeStates"], before)

    def test_legacy_bushel_capacity_matches_client_and_preserves_inventory_and_saved_upgrades(self):
        self.prepare()
        state = self.save["craftingState"]
        legacy = [{"itemCode": "sb", "quantity": 2, "imported": [1]},
                  {"itemCode": "sb", "quantity": 2, "imported": [2]}]
        state.update(maxCapacity=5, craftingItems=copy.deepcopy(legacy))
        crafting.initialize(self.save)
        state = self.save["craftingState"]
        self.assertEqual(state["maxCapacity"], 400)
        self.assertEqual(state["craftingItems"], legacy)
        self.purchase()
        state = self.save["craftingState"]
        self.assertEqual(sum(row["quantity"] for row in state["craftingItems"]), 12)
        state["craftingItems"].append({"itemCode": "wh", "quantity": 388})
        self.assert_rejected_without_mutation("FarmService.onPurchaseBushel", ["pu", "b0", 1])
        state["maxCapacity"] = 450
        crafting.initialize(self.save)
        self.assertEqual(self.save["craftingState"]["maxCapacity"], 450)
        self.call("FarmService.onPurchaseBushel", ["pu", "b0", 1])
        self.assertEqual(sum(row["quantity"] for row in self.save["craftingState"]["craftingItems"]), 401)

    def test_paid_acquisition_cooking_claim_use_and_reload(self):
        self.prepare()
        xp = self.save["userInfo"]["player"]["xp"]
        self.purchase()
        self.assertEqual(self.save["userInfo"]["player"]["cash"], 92)
        self.begin()
        self.assertEqual(self.save["userInfo"]["player"]["xp"], xp + 50)
        self.assertEqual([r["quantity"] for r in self.save["craftingState"]["craftingItems"]], [0, 0])
        with redirect_stdout(io.StringIO()):
            with self.player.village_transaction("fixture-farmer"):
                self.player.save_session("fixture-farmer")
            self.player.load_saves()
        self.save = self.player.session("fixture-farmer")
        self.assertEqual(self.save["world"]["objectsArray"][0]["recipeQueue"][0]["start_ts"], 1000)
        result = self.claim()
        self.assertEqual(result, [{"recipeId": "b0", "start_ts": 1000, "quantity": 2,
                                  "productItemCode": "b0", "numGiftProducts": 1, "recipeLevel": 1}])
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-7"], {"b0:1": [1, [], []]})
        self.assertEqual(self.save["craftingState"]["craftingPublicInventory"]["publicGoods"]["bakery"]["b0"],
                         {"id": "b0", "qty": 2, "price": 1000})
        self.call("CraftingService.onUseCraftedGood", ["b0:1"])
        self.assertEqual(self.save["userInfo"]["player"]["energy"], 35)
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-7"], {})
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")
            self.player.load_saves()
        self.assertEqual(self.player.session("fixture-farmer")["userInfo"]["player"]["energy"], 35)

    def test_begin_and_purchase_retries_do_not_charge_or_award_twice(self):
        self.prepare()
        self.call("FarmService.onPurchaseBushel", ["pu", "b0", 8], sequence=10)
        self.call("FarmService.onPurchaseBushel", ["wh", "b0", 8], sequence=11)
        first = self.call("CraftingService.onBeginRecipe", ["b0", -1], sequence=12)
        before = copy.deepcopy(self.save)
        self.assertEqual(self.call("CraftingService.onBeginRecipe", ["b0", -1], now=2000, sequence=12), first)
        self.call("FarmService.onPurchaseBushel", ["pu", "b0", 8], sequence=10)
        self.assertEqual(self.save, before)
        self.assert_rejected_without_mutation("FarmService.onPurchaseBushel", ["wh", "b0", 4], sequence=12)

    def test_distinct_begin_sequences_can_queue_the_same_recipe(self):
        self.prepare(); self.purchase(count=2)
        self.begin(now=1000); self.begin(now=1010)
        queue = self.save["craftingState"]["recipeQueue"]["bakery"]
        self.assertEqual([r["start_ts"] for r in queue], [1000, 1010])
        result = self.claim(now=22600)
        self.assertEqual([r["start_ts"] for r in result], [1000])
        self.assertEqual([r["start_ts"] for r in self.save["craftingState"]["recipeQueue"]["bakery"]], [1010])
        self.assertEqual(self.claim(now=22610)[0]["start_ts"], 1010)
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-7"]["b0:2"][0], 2)

    def test_explicit_ovens_and_legacy_auto_slots_respect_occupancy_and_exact_claim(self):
        self.prepare(); self.purchase(count=3)
        first = self.call("CraftingService.onBeginRecipe", ["b0", 0], now=1000)
        self.assertEqual(first["ovenSlot"], 0)
        for slot in (0, 2, -2, True, 0.5, float("nan")):
            self.assert_rejected_without_mutation("CraftingService.onBeginRecipe", ["b0", slot], now=1001)
        # Preserve the original client's first-empty mapping for imported queues.
        self.save["craftingState"]["recipeQueue"]["bakery"][0]["ovenSlot"] = -1
        second = self.call("CraftingService.onBeginRecipe", ["b0", -1], now=1001)
        self.assertEqual(second["ovenSlot"], 1)
        queue = self.save["craftingState"]["recipeQueue"]["bakery"]
        self.assertEqual([row["ovenSlot"] for row in queue], [0, 1])
        claimed = self.call("CraftingService.onClaimFinishedRecipes", ["b0", 0], now=22600)
        self.assertEqual([row["start_ts"] for row in claimed], [1000])
        self.assertEqual(self.save["craftingState"]["recipeQueue"]["bakery"][0]["ovenSlot"], 1)
        self.assert_rejected_without_mutation("CraftingService.onClaimFinishedRecipes", ["b0", 1], now=22600)
        self.assertEqual(len(self.call("CraftingService.onClaimFinishedRecipes", ["b0", 1], now=22601)), 1)

    def test_early_claim_and_missing_resources_never_mutate(self):
        self.prepare()
        self.assert_rejected_without_mutation("CraftingService.onBeginRecipe", ["b0", -1])
        self.purchase(); self.begin()
        self.assert_rejected_without_mutation("CraftingService.onClaimFinishedRecipes", ["b0", -1], now=22599)

    def test_queue_capacity_is_catalog_slots_and_no_charge_on_full(self):
        self.prepare(); self.purchase(count=3)
        self.begin(); self.begin(now=1001)
        self.assert_rejected_without_mutation("CraftingService.onBeginRecipe", ["b0", -1], now=1002)

    def test_distinct_same_second_start_is_rejected_before_consumption(self):
        self.prepare(); self.purchase(count=2); self.begin()
        self.assert_rejected_without_mutation("CraftingService.onBeginRecipe", ["b0", -1])

    def test_claim_retry_and_use_retry_are_durable(self):
        self.prepare(); self.purchase(); self.begin()
        first = self.call("CraftingService.onClaimFinishedRecipes", ["b0", -1], now=22600, sequence=20)
        self.call("CraftingService.onUseCraftedGood", ["b0:1"], sequence=21)
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer"); self.player.load_saves()
        self.save = self.player.session("fixture-farmer")
        before = copy.deepcopy(self.save)
        self.assertEqual(self.call("CraftingService.onClaimFinishedRecipes", ["b0", -1], now=22601, sequence=20), first)
        self.call("CraftingService.onUseCraftedGood", ["b0:1"], sequence=21)
        self.assertEqual(self.save, before)
        self.assertEqual(self.claim(), [])
        self.assert_rejected_without_mutation("CraftingService.onUseCraftedGood", ["b0:1"])

    def test_new_session_reuses_sequences_but_preserves_unfinished_goods(self):
        self.prepare(); self.purchase(); self.begin()
        queue = copy.deepcopy(self.save["craftingState"]["recipeQueue"])
        crafting.start_session(self.save)
        self.assertEqual(self.save["craftingState"]["recipeQueue"], queue)
        self.call("FarmService.onPurchaseBushel", ["pu", "b0", 1], sequence=1)
        self.assertEqual(self.save["craftingState"]["craftingItems"][0]["quantity"], 1)

    def test_unplaced_incomplete_locked_and_nonclassic_ovens_reject(self):
        self.prepare()
        self.assert_rejected_without_mutation("CraftingService.onBeginRecipe", ["lq", -1])
        self.save["world"]["objectsArray"][0]["isFullyBuilt"] = False
        self.assert_rejected_without_mutation("FarmService.onPurchaseBushel", ["pu", "b0", 4])
        self.save["world"]["objectsArray"][0]["isFullyBuilt"] = True
        self.save["craftingState"]["craftingSkillState"]["recipeStates"][0]["m_isUnlocked"] = False
        self.assert_rejected_without_mutation("CraftingService.onBeginRecipe", ["b0", -1])
        self.assert_rejected_without_mutation("CraftingService.onBeginRecipe", ["b0", 2])

    def test_bad_quantities_wrong_ingredient_and_insufficient_cash_reject(self):
        self.prepare()
        for quantity in (True, 0, -1, 0.5, "4", float("nan"), float("inf"), 401):
            self.assert_rejected_without_mutation("FarmService.onPurchaseBushel", ["pu", "b0", quantity])
        self.assert_rejected_without_mutation("FarmService.onPurchaseBushel", ["kc", "b0", 1])
        self.save["userInfo"]["player"]["cash"] = 0
        self.assert_rejected_without_mutation("FarmService.onPurchaseBushel", ["pu", "b0", 1])

    def test_global_capacity_and_invalid_saved_quantities_reject(self):
        self.prepare()
        self.save["craftingState"]["craftingItems"] = [{"itemCode": "pu", "quantity": 400, "price": None}]
        self.assert_rejected_without_mutation("FarmService.onPurchaseBushel", ["pu", "b0", 1])
        self.save["craftingState"]["craftingItems"][0]["quantity"] = -1
        self.assert_rejected_without_mutation("FarmService.onPurchaseBushel", ["pu", "b0", 1])

    def test_unknown_branches_and_forged_good_keys_fail_closed(self):
        self.prepare()
        for method, params in (("CraftingService.onCancelRecipe", ["b0", -1]),
                               ("CraftingService.onBeginRecipe", ["2pvla", -1]),
                               ("CraftingService.onUseCraftedGood", ["b0:0"]),
                               ("CraftingService.onUseCraftedGood", ["b0:01"]),
                               ("CraftingService.onUseCraftedGood", ["b0:1:2"]),
                               ("CraftingService.onUseCraftedGood", ["b0:100000"])):
            self.assert_rejected_without_mutation(method, params)

    def test_imported_metadata_and_progress_survive_ordinary_snapshots(self):
        self.prepare(); self.purchase()
        self.save["craftingState"]["craftingItems"][0]["custom"] = {"sender": "original"}
        self.begin()
        cottage = self.save["world"]["objectsArray"][0]
        forged = {"id": 600, "itemName": "cow", "className": "Animal", "recipeQueue": [],
                  "finishedRecipes": {"b0": {"qty": 999}}, "position": {"x": 11}}
        merged = crafting.preserve_fields(cottage, forged)
        self.assertEqual(merged["recipeQueue"], cottage["recipeQueue"])
        self.assertEqual(merged["finishedRecipes"], cottage["finishedRecipes"])
        self.assertEqual(merged["itemName"], "craftingbakery")
        self.assertEqual(merged["position"], {"x": 11})
        self.assertEqual(self.save["craftingState"]["craftingItems"][0]["custom"], {"sender": "original"})
        self.assertEqual(self.save["craftingState"]["importedState"], {"keep": True})
        self.assertEqual(self.save["craftingState"]["craftingSkillState"]["importedSkill"], [3])
        self.assertEqual(cottage["imported"], {"preserve": [1, 2]})

    def test_pub_starter_recipes_consume_catalog_bushels(self):
        self.prepare("pub")
        from game_settings import xp_to_level
        old_level = xp_to_level(self.save["userInfo"]["player"]["xp"])
        for code in ("lq", "lj"):
            self.purchase(code)
            self.begin(code)
            self.assertEqual(self.claim(code)[0]["productItemCode"], code)
        level_rewards = xp_to_level(self.save["userInfo"]["player"]["xp"]) - old_level
        self.assertEqual(self.save["userInfo"]["player"]["cash"], 85 + level_rewards)

    def test_cottage_identity_and_alternate_actions_are_protected(self):
        self.prepare(); self.purchase(); self.begin()
        cottage = self.save["world"]["objectsArray"][0]
        for action in ("plow", "clearWithered", "harvest", "sell", "clear", "stash"):
            with self.assertRaises(ValueError):
                crafting.guard_action(self.save, action, cottage)
        crafting.guard_action(self.save, "move", cottage)
        cottage["className"] = "Animal"
        self.assert_rejected_without_mutation("CraftingService.onBeginRecipe", ["b0", -1], now=1001)

    def test_quest_catalog_records_claim_once_not_begin_or_retry(self):
        import quests
        from test_minion_round3_quests import quest, task
        self.prepare()
        definition = quest("craft", [task("makeRecipeAny", total=5),
            task("makeRecipeByCode", type_="b0", total=5),
            task("makeRecipeByCategory", type_="bread", total=5),
            task("makeRecipeByCode", type_="lq", total=5)])
        with mock.patch.object(quests, "_cached_quests", {"craft": definition}), mock.patch.object(quests, "_item_categories", {"bread": {"b0"}}):
            self.save["questState"] = {"active": {"craft": {"progress": [0, 0, 0, 0], "new": 0}}, "completed": [], "retired": [], "replayed": {}}
            self.purchase(count=2); self.begin(now=1000); self.begin(now=1001)
            self.assertEqual(self.save["questState"]["active"]["craft"]["progress"], [0, 0, 0, 0])
            result = self.call("CraftingService.onClaimFinishedRecipes", ["b0", -1], now=22601, sequence=20)
            self.assertEqual(len(result), 2)
            self.assertEqual(self.save["questState"]["active"]["craft"]["progress"], [1, 1, 1, 0])
            self.call("CraftingService.onClaimFinishedRecipes", ["b0", -1], now=22601, sequence=20)
            self.claim(now=22601)
            self.assertEqual(self.save["questState"]["active"]["craft"]["progress"], [1, 1, 1, 0])

    def test_disk_commit_failure_restores_ingredients_xp_queue_and_receipt(self):
        self.prepare(); self.purchase()
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")
        before = copy.deepcopy(self.save)
        disk = self.path.read_bytes()
        with mock.patch.object(self.player, "commit_json_batch", side_effect=OSError("test disk failure")):
            with self.assertRaises(OSError), redirect_stdout(io.StringIO()):
                with self.player.village_transaction("fixture-farmer"):
                    self.begin()
                    self.player.save_session("fixture-farmer")
        self.assertEqual(self.player.session("fixture-farmer"), before)
        self.assertEqual(self.path.read_bytes(), disk)


class CraftingWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway
    prepare = CraftingTests.prepare

    def send(self, requests, now=1000, status=200):
        from pyamf import remoting
        with mock.patch.object(crafting, "timestamp_now", return_value=now):
            response = self.gateway(requests)
        fixtures.assert_gateway_status(self, response, status)
        if status == 200:
            return remoting.decode(response.data).bodies[0][1].body["data"]

    def acquire_and_begin(self):
        return self.send([
            self.command("FarmService.onPurchaseBushel", ["pu", "b0", 4], sequence=1),
            self.command("FarmService.onPurchaseBushel", ["wh", "b0", 4], sequence=2),
            self.command("CraftingService.onBeginRecipe", ["b0", -1], sequence=3)])

    def test_actual_amf_paid_start_claim_fuel_and_disk_reload(self):
        self.prepare()
        result = self.acquire_and_begin()
        self.assertEqual(result[2]["data"]["start_ts"], 1000)
        self.assertEqual(result[2]["data"]["recipe"]["craft"], "bakery")
        self.assertEqual(json.loads(self.path.read_text())["craftingState"]["recipeQueue"]["bakery"][0]["finish_ts"], 22600)
        claimed = self.send([self.command("CraftingService.onClaimFinishedRecipes", ["b0", -1], sequence=4)], now=22600)
        self.assertEqual(claimed[0]["data"][0]["start_ts"], 1000)
        self.assertEqual(claimed[0]["data"][0]["numGiftProducts"], 1)
        self.send([self.command("CraftingService.onUseCraftedGood", ["b0:1"], sequence=5)], now=22600)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        reloaded = self.player.session("fixture-farmer")
        self.assertEqual(reloaded["userInfo"]["player"]["energy"], 35)
        self.assertEqual(reloaded["craftingState"]["recipeQueue"]["bakery"], [])
        self.assertEqual(reloaded["userInfo"]["player"]["storageData"]["-7"], {})

    def test_actual_browser_first_oven_packet_persists_and_rejects_occupied_slot(self):
        self.prepare()
        result = self.send([
            self.command("FarmService.onPurchaseBushel", ["pu", "b0", 8], sequence=1),
            self.command("FarmService.onPurchaseBushel", ["wh", "b0", 8], sequence=2),
            self.command("CraftingService.onBeginRecipe", ["b0", 0], sequence=3)])
        self.assertEqual(result[2]["data"]["ovenSlot"], 0)
        self.assertEqual(json.loads(self.path.read_text())["craftingState"]["recipeQueue"]["bakery"][0]["ovenSlot"], 0)
        disk = self.path.read_bytes()
        self.send([self.command("CraftingService.onBeginRecipe", ["b0", 0], sequence=4)], now=1001, status=400)
        self.send([self.command("CraftingService.onBeginRecipe", ["b0", 2], sequence=5)], now=1001, status=400)
        self.assertEqual(self.path.read_bytes(), disk)
        result = self.send([self.command("CraftingService.onClaimFinishedRecipes", ["b0", 0], sequence=6)], now=22600)
        self.assertEqual(result[0]["data"][0]["start_ts"], 1000)

    def test_actual_amf_init_provides_locked_recipe_states_for_dialog(self):
        self.prepare()
        result = self.send([self.command("UserService.initUser", ["Crafting fixture", 0, True, None], sequence=1)])
        self.assertEqual(result[0]["data"]["craftingState"]["maxCapacity"], 400)
        states = {row["m_type"]: row for row in result[0]["data"]["craftingState"]["craftingSkillState"]["recipeStates"]}
        self.assertTrue(states["b0"]["m_isUnlocked"])
        self.assertTrue(states["b1"]["m_isUnlocked"])
        self.assertFalse(states["b3"]["m_isUnlocked"])
        self.assertEqual((states["b3"]["m_level"], states["b3"]["m_experience"]), (3, 0))
        disk = self.path.read_bytes()
        self.send([self.command("CraftingService.onBeginRecipe", ["b3", -1], sequence=2)], status=400)
        self.assertEqual(self.path.read_bytes(), disk)

    def test_actual_amf_retry_early_claim_keeps_paid_recipe_in_batch(self):
        self.prepare()
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        response = self.gateway([
            self.command("FarmService.onPurchaseBushel", ["pu", "b0", 4], sequence=1),
            self.command("FarmService.onPurchaseBushel", ["wh", "b0", 4], sequence=2),
            self.command("CraftingService.onBeginRecipe", ["b0", -1], sequence=3),
            self.command("CraftingService.onClaimFinishedRecipes", ["b0", -1], sequence=4)])
        fixtures.gateway_results(self, response, [0, 0, 0, 29])
        self.assertEqual(len(self.player.session("fixture-farmer")["craftingState"]["recipeQueue"]["bakery"]), 1)
        self.save = self.player.session("fixture-farmer")
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.send([self.command("CraftingService.onBeginRecipe", ["b0", -1], sequence=3)], now=2000)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)

    def test_actual_amf_snapshot_and_alternate_world_actions_cannot_erase_queue(self):
        self.prepare(); self.acquire_and_begin()
        saved = copy.deepcopy(self.save["world"]["objectsArray"][0])
        snapshot = {"id": 600, "itemName": "craftingbakery", "className": "CraftingCottageBuilding",
                    "recipeQueue": [], "finishedRecipes": {}, "position": {"x": 11, "y": 10, "z": 0}, "state": "built"}
        self.send([self.command("WorldService.performAction", ["move", snapshot, []], sequence=10)])
        self.assertEqual(self.save["world"]["objectsArray"][0]["recipeQueue"], saved["recipeQueue"])
        disk = self.path.read_bytes()
        self.send([self.command("WorldService.performAction", ["plow", snapshot, []], sequence=11)], status=400)
        self.assertEqual(self.path.read_bytes(), disk)

    def test_actual_amf_cottage_startup_storage_info_is_read_only(self):
        self.prepare(); self.acquire_and_begin()
        saved = copy.deepcopy(self.save["world"]["objectsArray"][0])
        before = copy.deepcopy(self.player.session("fixture-farmer"))
        snapshot = {"id": 600, "itemName": "craftingbakery", "className": "CraftingCottageBuilding",
                    "recipeQueue": [], "finishedRecipes": {"b0": {"qty": 999}},
                    "position": {"x": 40, "y": 40, "z": 0}, "state": "built"}
        result = self.send([self.command("WorldService.performAction", ["getStorageInfo", snapshot, [{}]], sequence=9)])
        self.assertEqual(result[0]["data"]["id"], 600)
        self.assertIsNone(result[0]["data"].get("helperURL"))
        self.assertEqual(self.player.session("fixture-farmer"), before)
        self.assertEqual(self.player.session("fixture-farmer")["world"]["objectsArray"][0], saved)
        self.send([self.command("WorldService.performAction", ["getStorageInfo", dict(snapshot, id=999), [{}]], sequence=10)], status=400)
        self.send([self.command("WorldService.performAction", ["getStorageInfo",
            dict(snapshot, itemName="cow", className="Animal"), [{}]], sequence=11)], status=400)
        self.assertEqual(self.player.session("fixture-farmer"), before)

    def test_actual_amf_unsupported_mutation_and_missing_goods_are_not_success(self):
        self.prepare()
        disk = self.path.read_bytes()
        for method, params in (("CraftingService.onCancelRecipe", ["b0", -1]),
                               ("CraftingService.onUseCraftedGood", ["b0:1"]),
                               ("CraftingService.onBeginRecipe", ["2pvla", -1])):
            self.send([self.command(method, params)], status=400)
            self.assertEqual(self.path.read_bytes(), disk)


if __name__ == "__main__":
    unittest.main()
