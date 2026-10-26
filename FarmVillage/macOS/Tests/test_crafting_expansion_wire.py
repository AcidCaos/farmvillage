"""Integrated Mistletoe placement/production over original signed AMF.

These synthetic gateway tests verify service integration, not the still-gated
regional skill-upgrade controls in the original prepared client.
"""
from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
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
CRAFT = "xhdcrafttype"
WORLD = "htown"
NAME = "xhdcraftingcottage"


class CraftingExpansionWireTests(unittest.TestCase):
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
        self.purchase("8WE")
        started = self.send("CraftingService.onBeginRecipe", ["8WE", 0])
        self.assertEqual((started["worldType"], started["start_ts"], started["finish_ts"]),
                         (WORLD, NOW, NOW + 21600))
        queue = copy.deepcopy(self.save["craftingState"]["recipeQueue"][CRAFT])
        world_travel.switch(self.save, "farm", now=NOW + 1)
        world_travel.switch(self.save, WORLD, now=NOW + 2)
        self.assertEqual(self.save["craftingState"]["recipeQueue"][CRAFT], queue)
        self.persist()
        cash = self.save["userInfo"]["player"]["cash"]
        self.assertEqual(self.send("CraftingService.onRushRecipe", ["8WE", NOW, False, 0],
                                   now=NOW + 3, sequence=40), {})
        self.assertEqual(self.save["userInfo"]["player"]["cash"], cash - 5)
        self.assertEqual(self.save["userInfo"]["player"]["storageData"].get("-7", {}), {})
        accepted = copy.deepcopy(self.save)
        self.send("CraftingService.onRushRecipe", ["8WE", NOW, False, 0], now=NOW + 4, sequence=40)
        self.assertEqual(self.save, accepted)
        claimed = self.send("CraftingService.onClaimFinishedRecipes", ["8WE", 0], now=NOW + 5)
        self.assertEqual(claimed, [{"recipeId": "8WE", "start_ts": NOW, "quantity": 2,
            "productItemCode": "8WE", "numGiftProducts": 1, "recipeLevel": 1}])
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-7"]["8WE:1"][0], 1)
        accepted = copy.deepcopy(self.save)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.save, accepted)
        use_sequence = self.sequence + 1
        self.send("CraftingService.onUseCraftedGood", ["8WE:1"], now=NOW + 6, sequence=use_sequence)
        self.assertEqual(self.save["userInfo"]["player"]["energy"], 35)
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-7"], {})
        self.assertEqual(self.save["craftingState"]["recipeQueue"][CRAFT], [])
        accepted = copy.deepcopy(self.save)
        self.send("CraftingService.onUseCraftedGood", ["8WE:1"], now=NOW + 7, sequence=use_sequence)
        self.assertEqual(self.save, accepted)
        self.assertEqual(json.loads(self.path.read_text()), accepted)

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
        self.purchase("8WG")
        self.send("CraftingService.onBeginRecipe", ["8WG", 0])
        self.save["craftingState"]["recipeQueue"][CRAFT][0]["worldType"] = "farm"
        self.persist()
        self.reject_unchanged("CraftingService.onRushRecipe", ["8WG", NOW, False, 0], now=NOW + 1)
        self.reject_unchanged("CraftingService.onClaimFinishedRecipes", ["8WG", 0], now=NOW + 21600)
        self.save["craftingState"]["recipeQueue"][CRAFT][0]["worldType"] = WORLD
        self.persist()
        self.send("CraftingService.onRushRecipe", ["8WG", NOW, False, 0], now=NOW + 2)
        result = self.send("CraftingService.onClaimFinishedRecipes", ["8WG", 0], now=NOW + 3)
        self.assertEqual((result[0]["productItemCode"], result[0]["recipeLevel"], result[0]["quantity"]),
                         ("8WG", 3, 3))
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-7"]["8WG:3"][0], 1)

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
                ("FarmService.onPurchaseBushel", ["8PV", "8WE", 3]),
                ("CraftingService.onBeginRecipe", ["8WE", 0]),
                ("CraftingService.onRushRecipe", ["8WE", NOW, False, 0]),
                ("CraftingService.onClaimFinishedRecipes", ["8WE", 0]),
                ("CraftingService.onBuyCraftUpgrade", [CRAFT, True]),
                ("CraftingService.onClaimFreeCottage", ["7la"])):
            self.reject_unchanged(method, params)

    def test_preview_scope_preserves_home_and_imported_regional_progress(self):
        self.prepare(place=False)
        original = copy.deepcopy(self.save)
        for destination in ("farm", "england", "rainforest", "australia"):
            self.save.clear(); self.save.update(copy.deepcopy(original))
            self.save["userInfo"]["currentWorldType"] = destination
            crafting.initialize(self.save)
            preview_craft = {"england": "pub", "rainforest": "xrfcrafttype"}.get(destination)
            self.assertEqual(self.save["craftingState"]["craftingSkillState"]["craftTypes"],
                             [{"type": preview_craft, "level": 1, "xp": 0, "exp": 0}] if preview_craft else [])
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
                          for row in queue], [("8WE", 1, NOW + 5, WORLD)])
        self.assertEqual({row["itemCode"]: row["quantity"] for row in ingredients},
                         crafting._ingredients(crafting._recipe("8WE")))
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


if __name__ == "__main__":
    unittest.main()
