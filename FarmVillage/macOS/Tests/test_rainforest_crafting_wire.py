"""Integrated Herbal Hut placement/production over original signed AMF.

These synthetic gateway tests verify service integration. Prepared-client
upgrade controls and graphics acceptance are graded independently.
"""
from contextlib import redirect_stdout
import base64
import copy
import io
import json
import os
from pathlib import Path
import sys
import shutil
import subprocess
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import crafting
import creative_worlds
import engine
import items
import themed_worlds
import world_travel


NOW = 1800000000
CRAFT = "xrfcrafttype"
WORLD = "rainforest"
NAME = "xrfcraftingcottage"


class RainforestCraftingWireTests(unittest.TestCase):
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

    @property
    def skill(self):
        return next(row for row in self.save["craftingState"]["craftingSkillState"]["craftTypes"]
                    if row["type"] == CRAFT)

    def persist(self):
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")

    def prepare(self, *, place=True):
        self.path = self.write_fixture()
        self.save["world"]["objectsArray"] = []
        self.save["userInfo"]["player"].update(xp=100015, gold=2_500_000, cash=1000,
            energy=5, storageData={}, seenFlags={"placeCottage": True, "craftTutDone": True})
        self.save["questState"] = {"active": {}, "completed": [], "retired": [], "replayed": {}}
        self.save["craftingState"] = {"craftingItems": [], "craftingSkillState": {
            "recipeStates": [], "craftTypes": []}, "imported": {"keep": [1, 2]}}
        creative_worlds.create(self.save, WORLD, "allAccess", now=NOW)
        world_travel.switch(self.save, WORLD, now=NOW)
        self.sequence = 0
        self.persist()
        if not place:
            return
        snapshot = {"id": 64001, "itemName": NAME, "className": "CraftingCottageBuilding",
            "state": "built", "isFullyBuilt": True, "position": {"x": 10, "y": 10, "z": 0}}
        gold = self.save["userInfo"]["player"]["gold"]
        self.send("WorldService.performAction", ["place", snapshot, []])
        self.assertEqual(self.save["userInfo"]["player"]["gold"], gold - 100000)
        self.assertEqual(self.save["craftingState"]["recipeQueue"][CRAFT], [])

    def send(self, method, params=(), *, now=NOW, sequence=None, error=0):
        self.sequence += 1
        if sequence is None:
            sequence = self.sequence
        self.sequence = max(self.sequence, sequence)
        with mock.patch.object(crafting, "timestamp_now", return_value=now), \
                mock.patch.object(self.server.commands, "timestamp_now", return_value=now), \
                mock.patch.object(self.server, "timestamp_now", return_value=now), \
                mock.patch.object(engine, "timestamp_now", return_value=now):
            response = self.gateway([self.command(method, params, sequence)])
        return fixtures.gateway_results(self, response, [error])[0]["data"]

    def purchase(self, code):
        cash = self.save["userInfo"]["player"]["cash"]
        total = 0
        for ingredient, quantity in crafting._ingredients(crafting._recipe(code)).items():
            item = items.get_item_by_code(ingredient)
            price = engine.catalog_price(item, "cash") or 1
            total += (price if price > 0 else 1) * quantity
            self.send("FarmService.onPurchaseBushel", [ingredient, code, quantity])
        self.assertEqual(self.save["userInfo"]["player"]["cash"], cash - total)

    def reject_unchanged(self, method, params, **kwargs):
        memory, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.send(method, params, error=29, **kwargs)
        self.assertEqual(self.save, memory)
        self.assertEqual(self.path.read_bytes(), disk)

    def test_signed_place_begin_world_roundtrip_paid_rush_claim_fuel_and_reload(self):
        self.prepare()
        self.purchase("r34")
        started = self.send("CraftingService.onBeginRecipe", ["r34", 0])
        self.assertEqual((started["worldType"], started["start_ts"], started["finish_ts"]),
                         (WORLD, NOW, NOW + 21600))
        queue = copy.deepcopy(self.save["craftingState"]["recipeQueue"][CRAFT])
        world_travel.switch(self.save, "farm", now=NOW + 1)
        world_travel.switch(self.save, WORLD, now=NOW + 2)
        self.assertEqual(self.save["craftingState"]["recipeQueue"][CRAFT], queue)
        self.persist()
        cash = self.save["userInfo"]["player"]["cash"]
        self.assertEqual(self.send("CraftingService.onRushRecipe", ["r34", NOW, False, 0],
                                   now=NOW + 3, sequence=40), {})
        self.assertEqual(self.save["userInfo"]["player"]["cash"], cash - 5)
        self.assertEqual(self.save["userInfo"]["player"]["storageData"].get("-7", {}), {})
        accepted = copy.deepcopy(self.save)
        self.send("CraftingService.onRushRecipe", ["r34", NOW, False, 0], now=NOW + 4, sequence=40)
        self.assertEqual(self.save, accepted)
        claimed = self.send("CraftingService.onClaimFinishedRecipes", ["r34", 0], now=NOW + 5)
        self.assertEqual(claimed, [{"recipeId": "r34", "start_ts": NOW, "quantity": 2,
            "productItemCode": "r34", "numGiftProducts": 1, "recipeLevel": 1}])
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-7"]["r34:1"][0], 1)
        accepted = copy.deepcopy(self.save)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.save, accepted)
        use_sequence = self.sequence + 1
        self.send("CraftingService.onUseCraftedGood", ["r34:1"], now=NOW + 6, sequence=use_sequence)
        self.assertEqual(self.save["userInfo"]["player"]["energy"], 35)
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-7"], {})
        self.assertEqual(self.save["craftingState"]["recipeQueue"][CRAFT], [])
        accepted = copy.deepcopy(self.save)
        self.send("CraftingService.onUseCraftedGood", ["r34:1"], now=NOW + 7, sequence=use_sequence)
        self.assertEqual(self.save, accepted)
        self.assertEqual(json.loads(self.path.read_text()), accepted)

    def test_queue_full_clock_claim_and_replay_survive_two_fresh_server_processes(self):
        self.prepare()
        self.purchase("r34")
        started = self.send("CraftingService.onBeginRecipe", ["r34", 0])
        self.assertEqual(started["finish_ts"], NOW+21600)
        saved = json.loads(self.path.read_text())
        self.assertEqual(saved["craftingState"]["recipeQueue"][CRAFT][0]["finish_ts"], NOW+21600)
        payload = self.gateway_payload([self.command("CraftingService.onClaimFinishedRecipes", ["r34", 0], 501)])
        shutil.copytree(self.bundle.CACHE_DIR, self.saves.parent/"cache", dirs_exist_ok=True)
        program = '''import base64,sys
from unittest import mock
import assets
with mock.patch.object(assets,"check_assets"), mock.patch.object(sys,"argv",["server.py"]):
 import server
now=1800021600
with mock.patch("crafting.timestamp_now",return_value=now), mock.patch("server.timestamp_now",return_value=now), mock.patch("commands.timestamp_now",return_value=now), mock.patch("engine.timestamp_now",return_value=now):
 response=server.app.test_client().post("/flashservices/gateway.php",data=base64.b64decode(sys.argv[1]),content_type="application/x-amf")
print("RESTART_RESPONSE:"+base64.b64encode(response.data).decode())
'''
        env = {**os.environ, "FARMVILLAGE_DATA_DIR":str(self.saves.parent), "PYTHONDONTWRITEBYTECODE":"1"}
        accepted = None
        for _ in range(2):
            child = subprocess.run([sys.executable,"-B","-c",program,base64.b64encode(payload).decode()],
                cwd=fixtures.ROOT,env=env,capture_output=True,text=True,timeout=90)
            self.assertEqual(child.returncode,0,child.stderr+child.stdout[-1000:])
            record = next(row for row in child.stdout.splitlines() if row.startswith("RESTART_RESPONSE:"))
            from pyamf import remoting
            result = remoting.decode(base64.b64decode(record.split(":",1)[1])).bodies[0][1].body["data"][0]
            self.assertEqual(result["errorType"],0,result)
            current = json.loads(self.path.read_text())
            if accepted is None:
                accepted = current
                self.assertEqual(current["craftingState"]["recipeQueue"][CRAFT],[])
                self.assertEqual(current["userInfo"]["player"]["storageData"]["-7"]["r34:1"][0],1)
            self.assertEqual(current,accepted)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.save,accepted)

    def test_signed_skill_routes_new_recipe_and_imported_wrong_world_queue_refusal(self):
        self.prepare()
        # Earned craft XP is an explicit synthetic precondition. Both paid
        # skill commands still use the original wire contract and callbacks.
        self.skill.update(xp=6, exp=6)
        self.persist()
        gold = self.save["userInfo"]["player"]["gold"]
        self.assertEqual(self.send("CraftingService.onBuyCraftUpgrade", [CRAFT, False]),
                         {"rewardLink": None})
        self.assertEqual(self.save["userInfo"]["player"]["gold"], gold - 50000)
        self.assertEqual((self.skill["level"], self.skill["exp"]), (2, 0))
        cash = self.save["userInfo"]["player"]["cash"]
        self.send("CraftingService.onBuyCraftUpgrade", [CRAFT, True])
        self.assertEqual(self.save["userInfo"]["player"]["cash"], cash - 25)
        self.assertEqual((self.skill["level"], self.skill["exp"]), (3, 0))
        self.purchase("r95")
        self.send("CraftingService.onBeginRecipe", ["r95", 0])
        self.save["craftingState"]["recipeQueue"][CRAFT][0]["worldType"] = "farm"
        self.persist()
        self.reject_unchanged("CraftingService.onRushRecipe", ["r95", NOW, False, 0], now=NOW + 1)
        self.reject_unchanged("CraftingService.onClaimFinishedRecipes", ["r95", 0], now=NOW + 21600)
        self.save["craftingState"]["recipeQueue"][CRAFT][0]["worldType"] = WORLD
        self.persist()
        self.send("CraftingService.onRushRecipe", ["r95", NOW, False, 0], now=NOW + 2)
        result = self.send("CraftingService.onClaimFinishedRecipes", ["r95", 0], now=NOW + 3)
        self.assertEqual((result[0]["productItemCode"], result[0]["recipeLevel"], result[0]["quantity"]),
                         ("r95", 3, 3))
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-7"]["r95:3"][0], 1)

    def assert_unowned_preview(self, state):
        # Served maximumSlots (22573) dereferences getCraftTypeState(...).level
        # at offset63, even while its new cottage is only a placement preview.
        skills = state["craftingSkillState"]
        self.assertEqual(skills["craftTypes"], [{"type": CRAFT, "level": 1, "xp": 0, "exp": 0}])
        self.assertEqual(skills["recipeStates"], [])
        self.assertEqual(state["recipeQueue"], {})
        self.assertEqual(state["craftingPublicInventory"]["publicGoods"], {})
        self.assertEqual(state["craftingItems"], [])
        level = next(row for row in crafting._catalog()[0].find("craftTypeLevels")
                     if row.get("num") == str(skills["craftTypes"][0]["level"]))
        self.assertEqual((level.get("xp"), level.get("gold"), level.get("cash"), level.get("recipeSlots")),
                         ("0", "0", "0", "2"))

    def test_unowned_preview_skill_is_serialized_by_actual_init_and_world_load_once(self):
        self.prepare(place=False)
        initialized = self.send("UserService.initUser", ["Preview fixture", 0, True, None])
        self.assert_unowned_preview(initialized["craftingState"])
        self.assertEqual(initialized["world"]["objectsArray"], [])
        for destination in ("farm", WORLD, "farm", WORLD):
            loaded = self.send("WorldService.loadOwnWorld", [destination, True])
            self.assert_unowned_preview(loaded["craftingState"])
            self.assertEqual(loaded["world"]["objectsArray"], [])
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        initialized = self.send("UserService.initUser", ["Preview fixture", 0, True, None])
        self.assert_unowned_preview(initialized["craftingState"])

    def test_preview_bootstrap_grants_nothing_and_all_unowned_services_still_refuse(self):
        self.prepare(place=False)
        before_player, before_world = copy.deepcopy(self.save["userInfo"]["player"]), copy.deepcopy(self.save["world"])
        crafting.initialize(self.save)
        self.assert_unowned_preview(self.save["craftingState"])
        self.assertEqual(self.save["userInfo"]["player"], before_player)
        self.assertEqual(self.save["world"], before_world)
        item = items.get_item_by_name(NAME)
        self.assertEqual(crafting.purchase_catalog_item(self.save, item)["cost"], "100000")
        self.persist()
        for method, params in (
                ("FarmService.onPurchaseBushel", ["qvu", "r34", 3]),
                ("CraftingService.onBeginRecipe", ["r34", 0]),
                ("CraftingService.onRushRecipe", ["r34", NOW, False, 0]),
                ("CraftingService.onClaimFinishedRecipes", ["r34", 0]),
                ("CraftingService.onBuyCraftUpgrade", [CRAFT, True]),
                ("CraftingService.onClaimFreeCottage", ["ZPR"])):
            self.reject_unchanged(method, params)

    def test_preview_scope_preserves_home_and_imported_regional_progress(self):
        self.prepare(place=False)
        original = copy.deepcopy(self.save)
        for destination in ("farm", "england", "htown", "australia"):
            self.save.clear(); self.save.update(copy.deepcopy(original))
            self.save["userInfo"]["currentWorldType"] = destination
            crafting.initialize(self.save)
            self.assertNotIn(CRAFT, [row["type"] for row in self.save["craftingState"]["craftingSkillState"]["craftTypes"]])
        self.save.clear(); self.save.update(copy.deepcopy(original))
        with mock.patch.object(themed_worlds, "ACTIVE_WORLDS", frozenset()):
            crafting.initialize(self.save)
        self.assertEqual(self.save["craftingState"]["craftingSkillState"]["craftTypes"], [])
        imported = [{"type": CRAFT, "level": 3, "xp": 7, "exp": 7, "opaque": {"keep": [1]}},
                    {"type": "unknown-import", "level": 99, "exp": "opaque", "retain": True}]
        self.save["craftingState"]["craftingSkillState"]["craftTypes"] = copy.deepcopy(imported)
        crafting.initialize(self.save)
        self.assertEqual(self.save["craftingState"]["craftingSkillState"]["craftTypes"], imported)
        self.assertEqual(self.save["craftingState"]["craftingSkillState"]["recipeStates"], [])

    def test_invalid_or_duplicate_regional_preview_state_rejects_without_clobbering(self):
        self.prepare(place=False)
        original = copy.deepcopy(self.save)
        for rows in (
                [{"type": CRAFT, "level": level, "xp": 0, "exp": 0}] for level in (0, 6, True)):
            self.save.clear(); self.save.update(copy.deepcopy(original))
            self.save["craftingState"]["craftingSkillState"]["craftTypes"] = rows
            before = copy.deepcopy(self.save)
            with self.assertRaises(ValueError):
                crafting.initialize(self.save)
            self.assertEqual(self.save, before)
        for rows in (
                [{"type": CRAFT, "level": 1, "xp": -1, "exp": 0}],
                [{"type": CRAFT, "level": 1, "xp": 0, "exp": False}],
                [{"type": CRAFT, "level": 1, "xp": 0, "exp": 0}] * 2):
            self.save.clear(); self.save.update(copy.deepcopy(original))
            self.save["craftingState"]["craftingSkillState"]["craftTypes"] = rows
            before = copy.deepcopy(self.save)
            with self.assertRaises(ValueError):
                crafting.initialize(self.save)
            self.assertEqual(self.save, before)

    def test_preexisting_preview_does_not_skip_paid_placement_or_repeat_onboarding(self):
        self.prepare(place=False)
        self.save["userInfo"]["player"]["seenFlags"] = {}
        crafting.initialize(self.save)
        self.assert_unowned_preview(self.save["craftingState"])
        self.persist()
        gold, cash = (self.save["userInfo"]["player"][key] for key in ("gold", "cash"))
        snapshot = {"id": 64001, "itemName": NAME, "className": "CraftingCottageBuilding",
            "state": "built", "isFullyBuilt": True, "craftLevel": 5,
            "position": {"x": 10, "y": 10, "z": 0}}
        self.send("WorldService.performAction", ["place", snapshot, []])
        self.assertEqual(self.save["userInfo"]["player"]["gold"], gold - 100000)
        self.assertEqual(self.save["userInfo"]["player"]["cash"], cash)
        self.assertEqual((self.skill["level"], self.skill["xp"], self.skill["exp"]), (1, 0, 0))
        state = self.save["craftingState"]
        queue, ingredients = copy.deepcopy(state["recipeQueue"][CRAFT]), copy.deepcopy(state["craftingItems"])
        self.assertEqual([(row["id"], row["start_ts"], row["finish_ts"], row["worldType"])
                          for row in queue], [("r34", 1, NOW + 5, WORLD)])
        self.assertEqual({row["itemCode"]: row["quantity"] for row in ingredients},
                         crafting._ingredients(crafting._recipe("r34")))
        self.assertEqual(sum(row["m_isUnlocked"] for row in state["craftingSkillState"]["recipeStates"]), 4)
        player = copy.deepcopy(self.save["userInfo"]["player"])
        self.send("WorldService.performAction", ["place", snapshot, []])
        self.assertEqual(self.save["userInfo"]["player"], player)
        for destination in ("farm", WORLD):
            self.send("WorldService.loadOwnWorld", [destination, True])
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.send("UserService.initUser", ["Owned preview fixture", 0, True, None])
        self.assertEqual(self.save["craftingState"]["recipeQueue"][CRAFT], queue)
        self.assertEqual(self.save["craftingState"]["craftingItems"], ingredients)

    def test_owned_cottage_level_migration_still_uses_the_saved_building(self):
        self.prepare()
        self.save["craftingState"]["craftingSkillState"]["craftTypes"] = []
        self.save["world"]["objectsArray"][0]["craftLevel"] = 4
        crafting.initialize(self.save)
        self.assertEqual((self.skill["level"], self.skill["xp"], self.skill["exp"]), (4, 0, 0))


    def test_all_21_authored_recipe_costs_clocks_outputs_and_initial_levels(self):
        expected = {
            'r34': (1, 1, 2, [('qvu', 3), ('q1a', 3), ('qyr', 3)]),
            'jxat': (2, 1, 4, [('qru', 3), ('q5i', 3), ('qv0', 3)]),
            'r7a': (1, 1, 2, [('qyi', 2), ('q56', 3), ('q1f', 3)]),
            'sea': (1, 1, 2, [('qru', 3), ('q1b', 3), ('q3w', 3)]),
            'sgc': (1, 1, 3, [('q56', 3), ('q3p', 3), ('qyi', 3)]),
            'r95': (2, 3, 3, [('qru', 3), ('q5i', 3), ('qyr', 3)]),
            'sd7': (2, 3, 3, [('q1b', 3), ('q0j', 3), ('qtz', 3)]),
            'r3c': (2, 3, 3, [('q2v', 3), ('q3w', 3), ('qvu', 3)]),
            'sgw': (2, 3, 3, [('q26', 3), ('q1f', 3), ('q1a', 2)]),
            'r9t': (3, 6, 3, [('q0j', 3), ('q3w', 3), ('qvu', 3)]),
            'sg3': (3, 6, 4, [('q1b', 3), ('q2v', 3), ('q3w', 3)]),
            'sfs': (3, 6, 4, [('qru', 3), ('qyi', 3), ('q5i', 3)]),
            'sey': (3, 6, 4, [('q0j', 3), ('q36', 3), ('q3w', 3)]),
            'r0q': (4, 6, 4, [('qru', 3), ('qvu', 3), ('qtz', 3)]),
            'sf1': (4, 9, 4, [('q2v', 3), ('qvu', 3), ('q2z', 3)]),
            'sdk': (4, 9, 4, [('q2z', 3), ('q4w', 3), ('q26', 3)]),
            'sec': (4, 9, 4, [('q2z', 3), ('q2v', 3), ('q4x', 3)]),
            'sfu': (5, 9, 4, [('qyi', 3), ('q2z', 3), ('q4x', 3)]),
            'sen': (5, 12, 4, [('q4w', 3), ('q3p', 3), ('q36', 3)]),
            'se5': (5, 12, 4, [('qru', 3), ('qv0', 2), ('q26', 3)]),
            'sbf': (5, 12, 4, [('q2z', 3), ('qv0', 2), ('q4w', 3)]),
        }
        codes = set(expected)
        self.assertEqual(crafting.REGIONAL_RECIPES[CRAFT], frozenset(codes))
        root = crafting._catalog()[0]
        self.assertEqual({row.get("id") for row in root.find("recipes")
                          if row.findtext("craft") == CRAFT}, codes)
        craft = root.find("craftSkills/craftSkill[@id='xrfcrafttype']")
        self.assertEqual(craft.findtext("recipeQueueClass"), "CraftingRecipeQueueManager")
        self.assertEqual(craft.find("cottageBuilding").get("name"), NAME)
        self.assertIsNone(craft.find("recipeLevels"))
        for code in sorted(codes):
            with self.subTest(code=code):
                self.prepare()
                # Skill 5 is a synthetic precondition for recipe coverage.
                self.skill["level"] = 5
                crafting.initialize(self.save)
                self.persist()
                recipe = crafting._recipe(code)
                skill, initial, sell, ingredients = expected[code]
                self.assertEqual((int(recipe.findtext("SkillLevelRequired")),
                                  int(recipe.findtext("InitialRecipeLevel")),
                                  int(recipe.find("Reward/OnFinish").get("sellQty")),
                                  list(crafting._ingredients(recipe).items())),
                                 (skill, initial, sell, ingredients))
                self.assertEqual(recipe.find("Reward/OnFinish").get("giftQty"), "1")
                self.assertEqual((recipe.findtext("MinutesToCook"), recipe.findtext("RushCostCoins"),
                                  recipe.findtext("RushCostCash")), ("360", "-1", "5"))
                self.assertEqual((recipe.findtext("Deprecated"), recipe.find("prereqs")), ("0", None))
                self.assertEqual(recipe.find("Reward/OnFinish").get("itemCode"), code)
                for ingredient in crafting._ingredients(recipe):
                    item = items.get_item_by_code(ingredient)
                    self.assertEqual((item["type"], item["className"]), ("bushel", "CBushel"))
                self.purchase(code)
                before_xp = self.save["userInfo"]["player"]["xp"]
                record = self.send("CraftingService.onBeginRecipe", [code, 0])
                self.assertEqual((record["worldType"], record["start_ts"], record["finish_ts"]),
                                 (WORLD, NOW, NOW + 21600))
                self.assertEqual(record["recipeInitialRecipeLevel"], int(recipe.findtext("InitialRecipeLevel")))
                self.assertEqual(self.save["userInfo"]["player"]["xp"], before_xp + 50)
                self.assertTrue(all(row["quantity"] == 0 for row in self.save["craftingState"]["craftingItems"]))
                self.reject_unchanged("CraftingService.onClaimFinishedRecipes", [code, 0], now=NOW + 21599)
                result = self.send("CraftingService.onClaimFinishedRecipes", [code, 0], now=NOW + 21600)
                reward = recipe.find("Reward/OnFinish")
                self.assertEqual(result, [{"recipeId": code, "start_ts": NOW,
                    "quantity": int(reward.get("sellQty")), "productItemCode": code,
                    "numGiftProducts": int(reward.get("giftQty")), "recipeLevel": record["recipeLevel"]}])
                accepted = copy.deepcopy(self.save)
                self.assertEqual(self.send("CraftingService.onClaimFinishedRecipes", [code, 0], now=NOW + 21601), [])
                self.assertEqual(self.save["userInfo"]["player"], accepted["userInfo"]["player"])
                key = f"{code}:{record['recipeLevel']}"
                fuel = next(int(row.get("fuel")) for row in root.find("recipeLevels")
                            if row.get("num") == str(record["recipeLevel"]))
                energy = self.save["userInfo"]["player"]["energy"]
                self.send("CraftingService.onUseCraftedGood", [key], now=NOW + 21602)
                self.assertEqual(self.save["userInfo"]["player"]["energy"], energy + fuel)
                self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-7"], {})

    def test_all_four_original_upgrade_prices_oven_slots_and_authored_unlocks(self):
        for rush in (False, True):
            self.prepare()
            # Earned craft XP is a seeded precondition, not a claimed play result.
            self.skill.update(exp=200 if not rush else 0, xp=200 if not rush else 0)
            self.persist()
            for level, required, coins, cash, slots in (
                    (2, 6, 50000, 15, 3), (3, 18, 100000, 25, 4),
                    (4, 27, 400000, 40, 5), (5, 36, 1000000, 60, 6)):
                before = copy.deepcopy(self.save["userInfo"]["player"])
                experience = self.skill["exp"]
                self.assertEqual(self.send("CraftingService.onBuyCraftUpgrade", [CRAFT, rush]),
                                 {"rewardLink": None})
                player = self.save["userInfo"]["player"]
                self.assertEqual(player["gold"], before["gold"] - (0 if rush else coins))
                self.assertEqual(player["cash"], before["cash"] - (cash if rush else 0))
                self.assertEqual((self.skill["level"], self.skill["exp"]),
                                 (level, max(0, experience - required)))
                self.assertEqual(crafting._oven_capacity(self.skill), slots)
                for state in self.save["craftingState"]["craftingSkillState"]["recipeStates"]:
                    recipe = crafting._recipe(state["m_type"])
                    self.assertEqual(state["m_isUnlocked"], int(recipe.findtext("SkillLevelRequired")) <= level)
                    self.assertEqual(state["m_level"], int(recipe.findtext("InitialRecipeLevel")))
            self.reject_unchanged("CraftingService.onBuyCraftUpgrade", [CRAFT, rush])

    def test_signed_wrong_world_locked_recipe_wallet_and_currency_fail_atomically(self):
        self.prepare()
        self.reject_unchanged("CraftingService.onBeginRecipe", ["r95", 0])
        self.reject_unchanged("CraftingService.onBuyCraftUpgrade", [CRAFT, False])
        self.save["userInfo"]["player"]["cash"] = 2
        self.persist()
        self.reject_unchanged("FarmService.onPurchaseBushel", ["qvu", "r34", 3])
        self.save["userInfo"]["player"]["cash"] = 1000
        self.persist()
        self.purchase("r34")
        self.send("CraftingService.onBeginRecipe", ["r34", 0])
        self.reject_unchanged("CraftingService.onRushRecipe", ["r34", NOW, True, 0], now=NOW + 1)
        world_travel.switch(self.save, "farm", now=NOW + 2)
        self.persist()
        for method, params in (("CraftingService.onRushRecipe", ["r34", NOW, False, 0]),
                               ("CraftingService.onClaimFinishedRecipes", ["r34", 0]),
                               ("CraftingService.onBuyCraftUpgrade", [CRAFT, True])):
            self.reject_unchanged(method, params, now=NOW + 21600)

    def test_jungle_craftshop_is_separate_authored_queue_and_cannot_be_faked_as_cottage(self):
        self.prepare()
        craft = crafting._catalog()[0].find("craftSkills/craftSkill[@id='craftshop']")
        self.assertEqual(craft.get("version"), "2")
        self.assertEqual(craft.findtext("recipeQueueClass"), "CraftshopRecipeQueueManager")
        self.assertIn("xrfcraftingworkshop_finished", [row.get("name") for row in craft.findall("cottageBuilding")])
        self.assertNotIn("craftshop", crafting.COTTAGES)
        self.reject_unchanged("CraftingService.onBeginRecipe", [craft.findtext("defaultRecipe"), 0])
        for name in ("xrfcraftingworkshop", "xrfcraftingworkshop_finished"):
            self.assertFalse(crafting.regional_cottage(WORLD, name, items.get_item_by_name(name)["className"]))


if __name__ == "__main__":
    unittest.main()
