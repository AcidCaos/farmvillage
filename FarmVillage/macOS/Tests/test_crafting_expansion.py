"""Mistletoe service mechanics; regional purchase/UI acceptance is external.

The copied, prepared v855097 client retains the classic TBeginRecipe (23016),
TCraftBuyUpgrade (22729), TBuyRecipeRush (22204), and claim (22559) contracts.
The archive has 2,945 CraftingRecipe rows plus a stray Mastery child, 2,939
distinct recipe IDs, and 86 craft types; the often-quoted 2,946/87 counts also
include that stray child. No broad XML admission follows from those counts.
All farms below are generated from villages/initial.json under test_persistence.
"""
from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import crafting
import items
import themed_worlds


CRAFT = "xhdcrafttype"
WORLD = "htown"
NAME = "xhdcraftingcottage"
CODES = {"8WE", "8WC", "8WA", "ccL", "8WG", "8Wy", "8Ww", "8Ws", "8Wo",
         "8Wm", "caC", "8Wk", "8Wi", "8Wg", "8Wu", "8We", "8Wq"}


class CraftingExpansionTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    def prepare(self, *, level=1, experience=0):
        self.save = self.fixture()
        self.save["userInfo"].update(currentWorldType=WORLD)
        self.save["userInfo"]["player"].update(
            xp=100015, gold=6_000_000, cash=10000, energy=5, storageData={},
            seenFlags={"placeCottage": True})
        self.save["world"].update(sizeX=50, sizeY=50, tileSet="htown_theme", objectsArray=[{
            "id": 600, "itemName": NAME, "className": "CraftingCottageBuilding",
            "state": "built", "isFullyBuilt": True, "craftLevel": level,
            "position": {"x": 10, "y": 10, "z": 0}, "imported": {"keep": [1]}}])
        self.save["craftingState"] = {"craftingItems": [], "craftingSkillState": {
            "recipeStates": [], "craftTypes": []}, "imported": {"keep": True}}
        crafting.start_session(self.save)
        self.skill.update(exp=experience, xp=experience, imported={"keep": 2})
        self.sequence = 0

    @property
    def skill(self):
        return next(x for x in self.save["craftingState"]["craftingSkillState"]["craftTypes"]
                    if x["type"] == CRAFT)

    def call(self, method, params=(), *, now=1000, sequence=None):
        self.sequence += 1
        if sequence is None:
            sequence = self.sequence
        self.sequence = max(sequence, self.sequence)
        with redirect_stdout(io.StringIO()):
            return crafting.dispatch(self.save, method, params, now=now, request_id=sequence)

    def reject(self, method, params=(), **kwargs):
        before = copy.deepcopy(self.save)
        with self.assertRaises(ValueError):
            self.call(method, params, **kwargs)
        self.assertEqual(self.save, before)

    def buy_ingredients(self, code):
        for ingredient, quantity in crafting._ingredients(crafting._recipe(code)).items():
            self.call("FarmService.onPurchaseBushel", [ingredient, code, quantity])

    def test_exact_archived_family_ingredients_products_and_global_ladders(self):
        root = crafting._catalog()[0]
        skill = root.find(f"craftSkills/craftSkill[@id='{CRAFT}']")
        self.assertEqual(skill.findtext("recipeQueueClass"), "CraftingRecipeQueueManager")
        self.assertIsNone(skill.find("recipeLevels"))
        self.assertIsNone(skill.find("craftTypeLevels"))
        self.assertEqual(crafting.REGIONAL_RECIPES[CRAFT], frozenset(CODES))
        self.assertEqual(len(crafting.RECIPES), 167)
        self.assertEqual({x.get("id") for x in root.find("recipes")
                          if x.findtext("craft") == CRAFT}, CODES)
        for code in CODES:
            recipe = crafting._recipe(code)
            self.assertEqual(recipe.findtext("Deprecated"), "0")
            for field in ("prereqs", "limitedStart", "limitedEnd", "recipeLevels"):
                self.assertIsNone(recipe.find(field))
            self.assertEqual(recipe.findtext("InitialRecipeLevel"),
                {"1": "1", "2": "3", "3": "6", "4": "9", "5": "12"}[
                    recipe.findtext("SkillLevelRequired")])
            self.assertEqual((recipe.findtext("MinutesToCook"), recipe.findtext("RushCostCash"),
                              recipe.findtext("RushCostCoins")), ("360", "5", "-1"))
            self.assertEqual(recipe.find("Reward/OnFinish").get("itemCode"), code)
            product = items.get_item_by_code(code)
            self.assertEqual((product["type"], product["className"]), ("crafted", "CCrafted"))
            for ingredient in crafting._ingredients(recipe):
                item = items.get_item_by_code(ingredient)
                self.assertEqual((item["type"], item["className"]), ("bushel", "CBushel"))

    def test_all_seventeen_original_purchase_begin_rush_claim_and_fuel_contracts(self):
        for code in sorted(CODES):
            with self.subTest(code=code):
                self.prepare(level=5)
                recipe = crafting._recipe(code)
                self.buy_ingredients(code)
                record = self.call("CraftingService.onBeginRecipe", [code, 0])
                self.assertEqual(record["worldType"], WORLD)
                self.assertEqual(record["finish_ts"], 22600)
                self.assertEqual(record["recipe"], crafting._php_xml(recipe))
                cash = self.save["userInfo"]["player"]["cash"]
                self.assertEqual(self.call("CraftingService.onRushRecipe", [code, 1000, False, 0],
                                           now=1001), {})
                self.assertEqual(self.save["userInfo"]["player"]["cash"], cash - 5)
                self.assertEqual(self.save["userInfo"]["player"]["storageData"], {})
                result = self.call("CraftingService.onClaimFinishedRecipes", [code, 0], now=1002)
                reward = recipe.find("Reward/OnFinish")
                self.assertEqual(result[0]["quantity"], int(reward.get("sellQty")))
                self.assertEqual(result[0]["productItemCode"], code)
                level = result[0]["recipeLevel"]
                fuel = next(int(x.get("fuel")) for x in crafting._catalog()[0].find("recipeLevels")
                            if x.get("num") == str(level))
                self.call("CraftingService.onUseCraftedGood", [f"{code}:{level}"], now=1003)
                self.assertEqual(self.save["userInfo"]["player"]["energy"], 5 + fuel)
                self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-7"], {})

    def test_coin_skill_ladder_and_cash_bypass_unlock_authored_initial_levels(self):
        for rush in (False, True):
            self.prepare(experience=200 if not rush else 0)
            for level, required, coins, cash, slots in (
                    (2, 6, 50000, 15, 3), (3, 18, 100000, 25, 4),
                    (4, 27, 400000, 40, 5), (5, 36, 1000000, 60, 6)):
                before = copy.deepcopy(self.save["userInfo"]["player"])
                old_xp = self.skill["exp"]
                self.assertEqual(self.call("CraftingService.onBuyCraftUpgrade", [CRAFT, rush]),
                                 {"rewardLink": None})
                player = self.save["userInfo"]["player"]
                self.assertEqual(player["gold"], before["gold"] - (0 if rush else coins))
                self.assertEqual(player["cash"], before["cash"] - (cash if rush else 0))
                self.assertEqual((self.skill["level"], self.skill["exp"]),
                                 (level, max(0, old_xp - required)))
                self.assertEqual(crafting._oven_capacity(self.skill), slots)
                self.assertEqual(self.skill["imported"], {"keep": 2})
                for state in self.save["craftingState"]["craftingSkillState"]["recipeStates"]:
                    recipe = crafting._recipe(state["m_type"])
                    self.assertEqual(state["m_isUnlocked"], int(recipe.findtext("SkillLevelRequired")) <= level)
                    self.assertEqual(state["m_level"], int(recipe.findtext("InitialRecipeLevel")))
            self.reject("CraftingService.onBuyCraftUpgrade", [CRAFT, rush])

    def test_wrong_world_inactive_world_locked_recipe_and_coin_rush_never_mutate(self):
        self.prepare()
        self.reject("CraftingService.onBeginRecipe", ["8WG", 0])
        self.reject("CraftingService.onBuyCraftUpgrade", [CRAFT, False])
        self.buy_ingredients("8WE")
        self.call("CraftingService.onBeginRecipe", ["8WE", 0])
        self.reject("CraftingService.onRushRecipe", ["8WE", 1000, True, 0], now=1001)
        for world in ("farm", "england", "australia", "rainforest"):
            self.save["userInfo"]["currentWorldType"] = world
            self.reject("CraftingService.onBuyCraftUpgrade", [CRAFT, True])
            self.reject("CraftingService.onBeginRecipe", ["8WE", 0])
            self.reject("CraftingService.onClaimFinishedRecipes", ["8WE", 0], now=22600)
            self.reject("CraftingService.onRushRecipe", ["8WE", 1000, False, 0], now=1001)
        self.save["userInfo"]["currentWorldType"] = WORLD
        with mock.patch.object(themed_worlds, "ACTIVE_WORLDS", frozenset()):
            self.reject("CraftingService.onBuyCraftUpgrade", [CRAFT, True])

    def test_imported_wrong_world_or_missing_queue_identity_cannot_rush_or_claim(self):
        self.prepare()
        self.buy_ingredients("8WE")
        self.call("CraftingService.onBeginRecipe", ["8WE", 0])
        accepted = copy.deepcopy(self.save)
        for wrong_world in ("farm", "england", "rainforest", None, 0, {}, []):
            self.save = copy.deepcopy(accepted)
            self.save["craftingState"]["recipeQueue"][CRAFT][0]["worldType"] = wrong_world
            self.reject("CraftingService.onRushRecipe", ["8WE", 1000, False, 0], now=1001)
            self.reject("CraftingService.onClaimFinishedRecipes", ["8WE", 0], now=22600)
            self.reject("CraftingService.onBuyCraftUpgrade", [CRAFT, True], now=1001)
        self.save = copy.deepcopy(accepted)
        del self.save["craftingState"]["recipeQueue"][CRAFT][0]["worldType"]
        self.reject("CraftingService.onRushRecipe", ["8WE", 1000, False, 0], now=1001)
        self.reject("CraftingService.onClaimFinishedRecipes", ["8WE", 0], now=22600)

    def test_home_cottage_import_on_england_cannot_share_home_production(self):
        self.prepare()
        self.save["userInfo"]["currentWorldType"] = "england"
        self.save["world"]["objectsArray"][0]["itemName"] = "craftingbakery"
        self.save["craftingState"] = {"craftingItems": [], "craftingSkillState": {
            "recipeStates": [], "craftTypes": []}}
        original = copy.deepcopy(self.save["world"]["objectsArray"])
        crafting.start_session(self.save)
        self.assertEqual(self.save["craftingState"]["craftingSkillState"]["recipeStates"], [])
        for method, params in (("FarmService.onPurchaseBushel", ["pu", "b0", 1]),
                               ("CraftingService.onBeginRecipe", ["b0", 0]),
                               ("CraftingService.onClaimFinishedRecipes", ["b0", 0]),
                               ("CraftingService.onRushRecipe", ["b0", 1000, False, 0])):
            self.reject(method, params)
        self.assertEqual(self.save["world"]["objectsArray"], original)

    def test_catalog_preview_and_owned_tiers_preserve_original_item(self):
        self.prepare()
        item = items.get_item_by_name(NAME)
        original = copy.deepcopy(item)
        self.save["world"]["objectsArray"] = []
        preview = crafting.regional_catalog_item(item, WORLD)
        self.assertEqual((preview["market"], preview["cost"], preview["buyXp"],
                          preview["requiredLevel"]), ("coins", "100000", "1000", "15"))
        self.assertEqual(crafting.purchase_catalog_item(self.save, item), preview)
        self.save["userInfo"]["player"]["storageData"]["-1"] = {"LA": [1, [], []]}
        second = crafting.purchase_catalog_item(self.save, item)
        self.assertEqual((second["market"], second["cash"]), ("cash", "80"))
        self.assertEqual(item, original)
        self.assertTrue(crafting.regional_cottage(WORLD, NAME))
        for world, name, cls in (("farm", NAME, "CraftingCottageBuilding"),
                                 (WORLD, "xrfcraftingcottage", "CraftingCottageBuilding"),
                                 (WORLD, NAME, "Building")):
            self.assertFalse(crafting.regional_cottage(world, name, cls))

    def test_exact_rush_identity_retry_and_json_reload_preserve_other_oven(self):
        self.prepare()
        for _ in range(2):
            self.buy_ingredients("8WE")
        self.call("CraftingService.onBeginRecipe", ["8WE", 0])
        other = self.call("CraftingService.onBeginRecipe", ["8WE", 1], now=1001)
        self.reject("CraftingService.onRushRecipe", ["8WE", 1000, False, 1], now=1002)
        self.call("CraftingService.onRushRecipe", ["8WE", 1000, False, 0], now=1002, sequence=90)
        accepted = copy.deepcopy(self.save)
        self.save = json.loads(json.dumps(self.save))
        self.call("CraftingService.onRushRecipe", ["8WE", 1000, False, 0], now=1003, sequence=90)
        self.assertEqual(self.save, accepted)
        self.assertEqual(self.save["craftingState"]["recipeQueue"][CRAFT][1], other)
        self.call("CraftingService.onClaimFinishedRecipes", ["8WE", 0], now=1004)
        self.assertEqual(self.save["craftingState"]["recipeQueue"][CRAFT], [other])

    def test_placement_and_imported_production_are_protected_without_granting_free_cottage(self):
        self.prepare()
        cottage = self.save["world"]["objectsArray"][0]
        snapshot = copy.deepcopy(cottage)
        snapshot.update(recipeQueue=[{"forged": True}], craftLevel=5)
        protected = crafting.preserve_fields(cottage, snapshot)
        self.assertEqual(protected["recipeQueue"], cottage["recipeQueue"])
        self.assertEqual(protected["craftLevel"], 1)
        self.reject("CraftingService.onClaimFreeCottage", ["7la"])
        self.call("CraftingService.onMarkCottageHistorySeen", [CRAFT])
        self.assertEqual(self.save["world"]["objectsArray"][0]["historyLastViewedTS"], 1000)
        self.save["world"]["objectsArray"] = []
        fresh = crafting.initialize_placement(snapshot)
        crafting.guard_action(self.save, "place", fresh)
        self.save["world"]["objectsArray"].append(fresh)
        crafting.finish_placement(self.save, fresh, now=1000)
        self.assertEqual(self.save["craftingState"]["recipeQueue"][CRAFT], [])
        self.assertEqual(fresh["foundingTS"], 1000)

    def test_original_recipe_bytes_and_real_prerequisite_gates_are_retained(self):
        source = Path(crafting.XML_DIR, "gz/v855098/crafting.xml.gz")
        raw = source.read_bytes()
        original = ET.fromstring(zlib.decompress(raw))
        projected = ET.fromstring(zlib.decompress(crafting.client_payload()))
        for code in CODES:
            path = f"recipes/CraftingRecipe[@id='{code}']"
            self.assertEqual(ET.tostring(original.find(path)), ET.tostring(projected.find(path)))
        for code in ("1Tn", "7LH", "fsh", "K1"):
            with self.assertRaises(ValueError):
                crafting._recipe(code)
        self.assertEqual(source.read_bytes(), raw)

    def test_first_regional_placement_keeps_original_onboarding_world_and_runs_once(self):
        self.prepare()
        self.save["userInfo"]["player"]["seenFlags"] = {}
        self.save["world"]["objectsArray"] = []
        self.save["craftingState"] = {"craftingItems": [], "craftingSkillState": {
            "recipeStates": [], "craftTypes": []}}
        cottage = crafting.initialize_placement({
            "id": 610, "itemName": NAME, "className": "CraftingCottageBuilding",
            "state": "built", "isFullyBuilt": True, "position": {"x": 10, "y": 10, "z": 0}})
        crafting.guard_action(self.save, "place", cottage)
        self.save["world"]["objectsArray"].append(cottage)
        crafting.finish_placement(self.save, cottage, now=1000)
        queue = self.save["craftingState"]["recipeQueue"][CRAFT]
        self.assertEqual(len(queue), 1)
        self.assertEqual((queue[0]["id"], queue[0]["worldType"], queue[0]["start_ts"],
                          queue[0]["finish_ts"]), ("8WE", WORLD, 1, 1005))
        accepted = copy.deepcopy(self.save)
        crafting.finish_placement(self.save, cottage, now=1001)
        self.assertEqual(self.save, accepted)
        self.call("CraftingService.onClaimFinishedRecipes", ["8WE", 0], now=1005)
        # onCraftedGoodUsed (34567) explicitly restricts the free-tractor
        # tutorial branch to WORLD_ID_HOME; regional goods do not reopen it.
        self.reject("CraftingService.onCompleteCottageTutorial", now=1006)
        self.call("CraftingService.onUseCraftedGood", ["8WE:1"], now=1007)
        self.assertEqual(self.save["userInfo"]["player"]["energy"], 35)

    def test_authored_regional_goods_can_be_used_from_global_inventory_on_other_farms(self):
        # postLoadComplete (34561) iterates allCraftedGoods, and
        # onCraftedGoodUsed (34567, offsets353..589) sends TUseCraftedGood
        # and adds getFuelRewardForGood without testing the recipe's world.
        for world in ("farm", "england", "rainforest"):
            self.prepare()
            self.save["userInfo"]["currentWorldType"] = world
            self.save["world"]["objectsArray"] = [{
                "id": 700, "itemName": "tractor", "className": "Tractor",
                "position": {"x": 10, "y": 10, "z": 0}}]
            self.save["userInfo"]["player"]["storageData"] = {"-7": {"8WE:1": [1, [], []]}}
            self.call("CraftingService.onUseCraftedGood", ["8WE:1"])
            self.assertEqual(self.save["userInfo"]["player"]["energy"], 35)
            self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-7"], {})


if __name__ == "__main__":
    unittest.main()
