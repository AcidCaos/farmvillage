"""Every ordinary skill-one cottage recipe against the archived source data."""
from contextlib import redirect_stdout
import copy
from datetime import datetime, timezone
import io
from pathlib import Path
import sys
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import crafting
import engine
import items
import test_cottage_lifecycle as lifecycle


EXPECTED_CODES = {
    "bakery": {"b0", "b1", "b2", "@c", "8yY", "8z6", "0fY", "0w4", "02y", "v7", "tk", "@v", "f(", "P)", "0Wk"},
    "winery": {"0hu", "w0", "w1", "w2", "@*", "8zz", "0w0", "02x", "v8", "tl", "@w", "j(", "M)", "0Wm"},
    "perfumery": {"p0", "p1", "p2", "^m", "0gC", "0xc", "02w", "o12", "v9", "tm", "@x", "g(", "N)", "0Wn"},
    "pub": {"ln", "lq", "@@", "lj", "0gW", "mn5", "@y", "h(", "O)", "o2kt"},
}
LONG_CLOCKS = {"@v": 480, "@w": 480, "@x": 480, "@y": 720}
SELL_QUANTITIES = {"8z6": 3, "v7": 3, "tk": 3, "0Wk": 1,
                   "8zz": 3, "v8": 3, "tl": 3, "0Wm": 1,
                   "o12": 3, "v9": 3, "tm": 3, "0Wn": 1,
                   "mn5": 3, "o2kt": 4}
MATERIAL_USE_REWARDS = {"@v": (18, "K1"), "@w": (18, "K4"),
                        "@x": (18, "K5"), "@y": (12, "gk")}


class CottageRecipeTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    prepare = lifecycle.CottageLifecycleTests.prepare
    save = lifecycle.CottageLifecycleTests.save

    def recipe_farm(self, craft):
        self.prepare()
        self.save["world"]["objectsArray"] = [{"id": 600,
            "itemName": crafting.COTTAGES[craft], "className": "CraftingCottageBuilding",
            "state": "built", "isFullyBuilt": True, "position": {"x": 10, "y": 10, "z": 0}}]
        self.save["userInfo"]["player"]["cash"] = 10000
        self.save["userInfo"]["player"]["seenFlags"]["placeCottage"] = True
        crafting.start_session(self.save)

    def call(self, method, params, now):
        self.sequence += 1
        with redirect_stdout(io.StringIO()):
            return crafting.dispatch(self.save, method, params, now=now, request_id=self.sequence)

    def purchase(self, recipe, now):
        cost = 0
        for code, amount in crafting._ingredients(recipe).items():
            item = items.get_item_by_code(code)
            self.assertEqual(item["type"], "bushel")
            price = engine.catalog_price(item, "cash") or 1
            price = price if price > 0 else 1
            cost += price * amount
            self.call("FarmService.onPurchaseBushel", [code, recipe.get("id"), amount], now)
        return cost

    def test_named_allowlist_matches_every_original_ordinary_level_one_contract(self):
        self.assertEqual(crafting.LEVEL_ONE_RECIPES, EXPECTED_CODES)
        source = crafting._catalog()[0]
        ordinary = [r for r in source.find("recipes") if r.findtext("craft") in crafting.HOME_COTTAGES
                    and r.findtext("SkillLevelRequired") == "1" and r.findtext("Deprecated") == "0"
                    and r.find("prereqs") is None and r.find("Reward/OnFinish").get("itemCode") == r.get("id")]
        self.assertEqual({r.get("id") for r in ordinary}, frozenset().union(*crafting.LEVEL_ONE_RECIPES.values()))
        self.assertEqual(len(ordinary), 53)
        self.assertEqual(sum(r.find("limitedStart") is None and r.find("limitedEnd") is None
                             for r in ordinary), 32)
        for recipe in ordinary:
            code = recipe.get("id")
            with self.subTest(recipe=code):
                self.assertEqual(recipe.findtext("InitialRecipeLevel"), "1")
                self.assertEqual(int(recipe.findtext("MinutesToCook")), LONG_CLOCKS.get(code, 360))
                self.assertEqual(recipe.find("Reward/OnMake").attrib, {"recipeXp": "1", "playerXp": "50"})
                self.assertEqual(recipe.find("Reward/OnFinish").attrib,
                    {"itemCode": code, "sellQty": str(SELL_QUANTITIES.get(code, 2)), "giftQty": "1"})

    def test_every_supported_recipe_pays_exact_catalog_bushels_cooks_claims_and_uses_fuel(self):
        for craft, codes in EXPECTED_CODES.items():
            for code in sorted(codes):
                with self.subTest(craft=craft, recipe=code):
                    self.recipe_farm(craft)
                    recipe = crafting._recipe(code)
                    start = recipe.findtext("limitedStart")
                    # Seasonal contracts are tested inside their original date
                    # window, not reopened in the present-day client.
                    now = (int(datetime.strptime(start, "%m/%d/%Y").replace(tzinfo=timezone.utc).timestamp()) + 86400
                           if start else 1000)
                    xp = self.save["userInfo"]["player"]["xp"]
                    cash = self.save["userInfo"]["player"]["cash"]
                    cost = self.purchase(recipe, now)
                    self.assertEqual(self.save["userInfo"]["player"]["cash"], cash - cost)
                    queued = self.call("CraftingService.onBeginRecipe", [code, -1], now)
                    self.assertEqual(queued["recipe"], crafting._php_xml(recipe))
                    self.assertEqual(queued["start_ts"], now)
                    self.assertEqual(queued["finish_ts"], now + LONG_CLOCKS.get(code, 360) * 60)
                    self.assertEqual(self.save["userInfo"]["player"]["xp"], xp + 50)
                    self.assertTrue(all(row["quantity"] == 0 for row in self.save["craftingState"]["craftingItems"]))
                    before = copy.deepcopy(self.save)
                    with self.assertRaises(ValueError):
                        self.call("CraftingService.onClaimFinishedRecipes", [code, -1], queued["finish_ts"] - 1)
                    self.assertEqual(self.save, before)
                    result = self.call("CraftingService.onClaimFinishedRecipes", [code, -1], queued["finish_ts"])
                    self.assertEqual(result, [{"recipeId": code, "start_ts": now,
                        "quantity": SELL_QUANTITIES.get(code, 2), "productItemCode": code,
                        "numGiftProducts": 1, "recipeLevel": 1}])
                    self.assertEqual(self.save["craftingState"]["recipeQueue"][craft], [])
                    goods = self.save["craftingState"]["craftingPublicInventory"]["publicGoods"][craft][code]
                    self.assertEqual(goods, {"id": code, "qty": SELL_QUANTITIES.get(code, 2), "price": 1000})
                    self.call("CraftingService.onUseCraftedGood", [code + ":1"], queued["finish_ts"])
                    self.assertEqual(self.save["userInfo"]["player"]["energy"],
                                     5 + MATERIAL_USE_REWARDS.get(code, (30, None))[0])
                    if code in MATERIAL_USE_REWARDS:
                        gift_code = MATERIAL_USE_REWARDS[code][1]
                        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-1"][gift_code], [1, [], []])
                    self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-7"], {})

    def test_expired_seasonal_begins_and_ingredient_purchases_reject_but_existing_goods_survive(self):
        self.recipe_farm("winery")
        recipe = crafting._recipe("@w")
        historical = int(datetime(2011, 4, 22, tzinfo=timezone.utc).timestamp())
        self.purchase(recipe, historical)
        queued = self.call("CraftingService.onBeginRecipe", ["@w", -1], historical)
        current = int(datetime(2026, 10, 23, tzinfo=timezone.utc).timestamp())
        for method, params in (("CraftingService.onBeginRecipe", ["@w", -1]),
                               ("FarmService.onPurchaseBushel", ["dl", "@w", 5])):
            before = copy.deepcopy(self.save)
            with self.assertRaises(ValueError):
                self.call(method, params, current)
            self.assertEqual(self.save, before)
        self.assertEqual(self.save["world"]["objectsArray"][0]["recipeQueue"], [queued])
        self.call("CraftingService.onClaimFinishedRecipes", ["@w", -1], current)
        self.call("CraftingService.onUseCraftedGood", ["@w:1"], current)
        self.assertEqual(self.save["userInfo"]["player"]["energy"], 23)
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-1"]["K4"], [1, [], []])

    def test_material_goods_use_exact_original_multiplier_gift_and_retry_identity(self):
        # At recipe level two the base is 35 fuel, not the level-one 30.
        # Expected results are independent fixed original-client outcomes.
        for code, craft, expected_fuel, gift in (("@v", "bakery", 21, "K1"),
                ("@w", "winery", 21, "K4"), ("@x", "perfumery", 21, "K5"),
                ("@y", "pub", 14, "gk")):
            with self.subTest(recipe=code):
                self.recipe_farm(craft)
                self.save["userInfo"]["player"]["storageData"]["-7"] = {code + ":2": [1, [], []]}
                with redirect_stdout(io.StringIO()):
                    crafting.dispatch(self.save, "CraftingService.onUseCraftedGood", [code + ":2"],
                                      now=1000, request_id=500)
                self.assertEqual(self.save["userInfo"]["player"]["energy"], 5 + expected_fuel)
                self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-1"][gift], [1, [], []])
                self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-7"], {})
                before = copy.deepcopy(self.save)
                crafting.dispatch(self.save, "CraftingService.onUseCraftedGood", [code + ":2"],
                                  now=1001, request_id=500)
                self.assertEqual(self.save, before)
                with self.assertRaises(ValueError):
                    crafting.dispatch(self.save, "CraftingService.onUseCraftedGood", [code + ":2"],
                                      now=1001, request_id=501)
                self.assertEqual(self.save, before)

    def test_material_use_failure_never_consumes_good_grants_item_or_adds_fuel(self):
        self.recipe_farm("winery")
        self.save["userInfo"]["player"]["storageData"]["-7"] = {"@w:1": [1, [], []]}
        before = copy.deepcopy(self.save)
        with mock.patch.object(crafting.storage, "store_deposit_item_by_name", side_effect=ValueError("gift failure")):
            with self.assertRaisesRegex(ValueError, "gift failure"):
                self.call("CraftingService.onUseCraftedGood", ["@w:1"], 1000)
        self.assertEqual(self.save, before)
        self.save["userInfo"]["player"]["storageData"]["-1"] = {"T1": [2147483647, [], []]}
        before = copy.deepcopy(self.save)
        with self.assertRaisesRegex(ValueError, "gift box is full"):
            self.call("CraftingService.onUseCraftedGood", ["@w:1"], 1000)
        self.assertEqual(self.save, before)

    def test_fractional_material_fuel_survives_disk_reload_and_the_next_use(self):
        self.recipe_farm("winery")
        self.save["userInfo"]["player"]["storageData"]["-7"] = {
            "@w:21": [1, [], []], "@w:22": [1, [], []]}
        # Original base fuel is 129 and 133 at levels 21 and 22. Their
        # 0.6 factor yields 77.4 and 79.8, without rounding to whole fuel.
        self.call("CraftingService.onUseCraftedGood", ["@w:21"], 1000)
        first_energy = self.save["userInfo"]["player"]["energy"]
        self.assertAlmostEqual(first_energy, 82.4, places=12)
        self.assertNotEqual(first_energy, int(first_energy))
        with redirect_stdout(io.StringIO()):
            with self.player.village_transaction("fixture-farmer"):
                self.player.save_session("fixture-farmer")
            self.player.load_saves()
            crafting.start_session(self.save)
        self.assertEqual(self.save["userInfo"]["player"]["energy"], first_energy)
        self.call("CraftingService.onUseCraftedGood", ["@w:22"], 1001)
        self.assertAlmostEqual(self.save["userInfo"]["player"]["energy"], 162.2, places=12)
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-1"]["K4"], [2, [], []])
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-7"], {})

    def test_served_projection_retains_all_definitions_and_locks_only_unrestored_goods(self):
        source_path = Path(crafting.XML_DIR) / "gz/v855098/crafting.xml.gz"
        original_bytes = source_path.read_bytes()
        original = ET.fromstring(zlib.decompress(original_bytes))
        projected = ET.fromstring(zlib.decompress(crafting.client_payload()))
        response = self.client.get("/xml/gz/v855098/crafting.xml.gz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.data, crafting.client_payload())
        original_recipes = list(original.find("recipes"))
        projected_recipes = list(projected.find("recipes"))
        self.assertEqual([r.get("id") for r in projected_recipes], [r.get("id") for r in original_recipes])
        for old, new in zip(original_recipes, projected_recipes):
            code = old.get("id")
            if old.findtext("craft") in crafting.COTTAGES and code not in crafting.RECIPES:
                self.assertEqual(new.findtext("ComingSoon"), "1")
                field = new.find("ComingSoon")
                if old.find("ComingSoon") is None:
                    new.remove(field)
                else:
                    field.text = old.findtext("ComingSoon")
            self.assertEqual(ET.tostring(new), ET.tostring(old), code)
        self.assertEqual(source_path.read_bytes(), original_bytes)
        for code in ("7L1", "fq0", "fsh"):
            with self.assertRaises(ValueError):
                crafting._recipe(code)

    def test_restored_level_one_unlock_migration_keeps_experience_and_existing_timers(self):
        self.recipe_farm("winery")
        row = next(r for r in self.save["craftingState"]["craftingSkillState"]["recipeStates"] if r["m_type"] == "w1")
        row.update(m_isUnlocked=False, m_level=4, m_experience=7, imported={"keep": True})
        queue = [{"id": "w0", "start_ts": 123, "finish_ts": 21723, "ovenSlot": 0}]
        self.save["craftingState"]["recipeQueue"]["winery"] = copy.deepcopy(queue)
        crafting.initialize(self.save)
        actual = next(r for r in self.save["craftingState"]["craftingSkillState"]["recipeStates"] if r["m_type"] == "w1")
        self.assertEqual(actual, dict(row, m_isUnlocked=True))
        self.assertEqual(self.save["world"]["objectsArray"][0]["recipeQueue"], queue)


if __name__ == "__main__":
    unittest.main()
