"""Paid cottage progression and exact recipe rushes over original signed AMF."""
from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures  # Synthetic writable paths precede product imports.
import crafting


class CraftingProgressionWireTests(unittest.TestCase):
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
    def craft(self):
        return next(row for row in self.save["craftingState"]["craftingSkillState"]["craftTypes"]
                    if row["type"] == "bakery")

    def persist(self):
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")

    def prepare(self, *, experience=6):
        self.path = self.write_fixture()
        self.save["userInfo"]["currentWorldType"] = "farm"
        self.save["userInfo"]["player"].update(xp=100015, gold=2_000_000, cash=200,
                                               energy=5, storageData={})
        self.save["world"]["objectsArray"] = [{
            "id": 600, "itemName": "craftingbakery", "className": "CraftingCottageBuilding",
            "state": "built", "isFullyBuilt": True, "craftLevel": 1,
            "position": {"x": 10, "y": 10, "z": 0}, "imported": {"retain": [1, 2]},
        }]
        self.save["craftingState"] = {"craftingItems": [], "craftingSkillState": {
            "recipeStates": [], "craftTypes": []}, "imported": {"retain": True}}
        crafting.start_session(self.save)
        self.craft.update(xp=experience, exp=experience, imported={"keep": 3})
        self.sequence = 0
        self.persist()

    def send(self, method, params=(), *, now=1000, sequence=None, reject=False):
        self.sequence += 1
        if sequence is not None:
            self.sequence = max(self.sequence, sequence)
        command = self.command(method, params, self.sequence if sequence is None else sequence)
        with mock.patch.object(crafting, "timestamp_now", return_value=now), \
                mock.patch.object(self.server.commands, "timestamp_now", return_value=now):
            response = self.gateway([command])
        return fixtures.gateway_results(self, response, [29 if reject else 0])[0]

    def reject_unchanged(self, method, params=(), **kwargs):
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        result = self.send(method, params, reject=True, **kwargs)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)
        return result

    def purchase(self, code, *, quantity=1, now=1000):
        for ingredient, amount in crafting._ingredients(crafting._recipe(code)).items():
            self.send("FarmService.onPurchaseBushel", [ingredient, code, amount * quantity], now=now)

    def queue(self, *, two=False):
        self.prepare(experience=8)
        self.send("CraftingService.onBuyCraftUpgrade", ["bakery", False])
        self.purchase("b3", quantity=2 if two else 1)
        first = self.send("CraftingService.onBeginRecipe", ["b3", 0], now=1000)["data"]
        if two:
            second = self.send("CraftingService.onBeginRecipe", ["b3", 1], now=1010)["data"]
            return first, second
        return first

    def test_coin_upgrade_callback_skill_spend_new_recipe_and_reload(self):
        self.prepare(experience=8)
        result = self.send("CraftingService.onBuyCraftUpgrade", ["bakery", False], sequence=40)
        self.assertEqual(result["data"], {"rewardLink": None})
        self.assertEqual(self.save["userInfo"]["player"]["gold"], 1_950_000)
        self.assertEqual(self.save["userInfo"]["player"]["cash"], 200)
        self.assertEqual((self.craft["level"], self.craft["exp"], self.craft["xp"]), (2, 2, 2))
        self.assertEqual(self.craft["imported"], {"keep": 3})
        states = {row["m_type"]: row for row in self.save["craftingState"]["craftingSkillState"]["recipeStates"]}
        self.assertTrue(states["b3"]["m_isUnlocked"])
        self.assertEqual(states["b3"]["m_level"], 3)
        self.assertFalse(states["b8"]["m_isUnlocked"])
        self.assertEqual(self.save["world"]["objectsArray"][0]["craftLevel"], 2)
        self.assertEqual(crafting._oven_capacity(self.craft), 3)
        accepted = copy.deepcopy(self.save)
        disk = self.path.read_bytes()
        self.assertEqual(self.send("CraftingService.onBuyCraftUpgrade", ["bakery", False],
                                  sequence=40, now=1001)["data"], {"rewardLink": None})
        self.assertEqual(self.save, accepted)
        self.assertEqual(self.path.read_bytes(), disk)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.save, accepted)
        self.reject_unchanged("CraftingService.onBuyCraftUpgrade", ["bakery", True], sequence=40)

    def test_cash_bypass_and_all_original_level_prices_do_not_auto_level(self):
        self.prepare(experience=0)
        cash = 200
        for level, price, slots in ((2, 15, 3), (3, 25, 4), (4, 40, 5), (5, 60, 6)):
            with self.subTest(level=level):
                self.send("CraftingService.onBuyCraftUpgrade", ["bakery", True])
                cash -= price
                self.assertEqual(self.save["userInfo"]["player"]["cash"], cash)
                self.assertEqual(self.save["userInfo"]["player"]["gold"], 2_000_000)
                self.assertEqual((self.craft["level"], self.craft["exp"], self.craft["xp"]), (level, 0, 0))
                self.assertEqual(crafting._oven_capacity(self.craft), slots)
        self.reject_unchanged("CraftingService.onBuyCraftUpgrade", ["bakery", True])
        self.assertTrue(all(row["m_isUnlocked"] for row in
            self.save["craftingState"]["craftingSkillState"]["recipeStates"]
            if row["m_type"] in crafting.RECIPES_BY_CRAFT["bakery"]))

    def test_upgrade_forgery_missing_context_funds_and_xp_are_atomic(self):
        self.prepare(experience=5)
        for params in ([], ["bakery"], ["bakery", False, 5], ["bakery", 0],
                       ["bakery", 1], ["bakery", "false"], ["bakery", None],
                       ["craftshop", True], [["bakery"], True], ["bakery", False]):
            with self.subTest(params=params):
                self.reject_unchanged("CraftingService.onBuyCraftUpgrade", params)
        self.save["userInfo"]["player"]["cash"] = 14
        self.persist()
        self.reject_unchanged("CraftingService.onBuyCraftUpgrade", ["bakery", True])
        self.craft.update(xp=6, exp=6)
        self.save["userInfo"]["player"]["gold"] = 49_999
        self.persist()
        self.reject_unchanged("CraftingService.onBuyCraftUpgrade", ["bakery", False])
        self.save["world"]["objectsArray"][0]["isFullyBuilt"] = False
        self.persist()
        self.reject_unchanged("CraftingService.onBuyCraftUpgrade", ["bakery", True])

    def test_rush_readies_only_exact_saved_oven_then_claims_once(self):
        first, second = self.queue(two=True)
        self.assertEqual(first["ovenSlot"], 0)
        self.assertEqual(second["ovenSlot"], 1)
        cash = self.save["userInfo"]["player"]["cash"]
        second_before = copy.deepcopy(self.save["craftingState"]["recipeQueue"]["bakery"][1])
        result = self.send("CraftingService.onRushRecipe", ["b3", 1000, False, 0], now=1020, sequence=60)
        # Transaction.onAmfComplete invokes the rush callback only for a
        # non-null data object; that callback immediately queues the claim.
        self.assertEqual(result["data"], {})
        self.assertEqual(self.save["userInfo"]["player"]["cash"], cash - 5)
        self.assertEqual(self.save["userInfo"]["player"]["storageData"], {})
        self.assertEqual(self.save["craftingState"]["craftingPublicInventory"]["publicGoods"]["bakery"], {})
        queue = self.save["craftingState"]["recipeQueue"]["bakery"]
        self.assertEqual(queue[0]["finish_ts"], 700)
        self.assertEqual(queue[1], second_before)
        before = copy.deepcopy(self.save)
        self.send("CraftingService.onRushRecipe", ["b3", 1000, False, 0], now=1021, sequence=60)
        self.assertEqual(self.save, before)
        self.reject_unchanged("CraftingService.onRushRecipe", ["b3", 1000, False, 0], now=1021)
        self.reject_unchanged("CraftingService.onRushRecipe", ["b3", 1010, False, 1], now=1021, sequence=60)
        claim = self.send("CraftingService.onClaimFinishedRecipes", ["b3", 0], now=1022, sequence=61)["data"]
        # Two starts cross recipe level 3's two-XP boundary. The original
        # claim uses the current recipe level, even for the first oven.
        self.assertEqual(claim, [{"recipeId": "b3", "start_ts": 1000, "quantity": 3,
            "productItemCode": "b3", "numGiftProducts": 1, "recipeLevel": 4}])
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-7"], {"b3:4": [1, [], []]})
        self.assertEqual(self.save["craftingState"]["craftingPublicInventory"]["publicGoods"]["bakery"]["b3"]["qty"], 3)
        self.assertEqual(self.save["craftingState"]["recipeQueue"]["bakery"], [second_before])
        accepted = copy.deepcopy(self.save)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.send("CraftingService.onClaimFinishedRecipes", ["b3", 0], now=1023, sequence=61)
        self.send("CraftingService.onRushRecipe", ["b3", 1000, False, 0], now=1023, sequence=60)
        self.assertEqual(self.save, accepted)
        self.assertEqual(json.loads(self.path.read_text()), accepted)

    def test_rush_bad_identity_currency_and_parameter_packets_never_charge(self):
        self.queue()
        for params in ([], ["b3", 1000, False], ["b3", 1000, False, 0, 5],
                       ["b3", 1000, 0, 0], ["b3", 1000, "false", 0], ["b3", 1000, None, 0],
                       ["b3", 1000, True, 0], ["b3", 1001, False, 0],
                       ["b3", 999, False, 0], ["b3", True, False, 0],
                       ["b3", 1000, False, 1], ["b3", 1000, False, True],
                       ["b3", 1000, False, 3], ["b3", 1000, False, 0.5],
                       ["b4", 1000, False, 0], ["b8", 1000, False, 0]):
            with self.subTest(params=params):
                self.reject_unchanged("CraftingService.onRushRecipe", params, now=1000)
        self.save["userInfo"]["player"]["cash"] = 4
        self.persist()
        self.reject_unchanged("CraftingService.onRushRecipe", ["b3", 1000, False, 0], now=1001)
        self.reject_unchanged("CraftingService.onRushRecipeWithTime", ["b3", 1000, False, 0], now=1001)

    def test_mixed_batch_failure_keeps_neighbors_and_valid_rush_claim_durable(self):
        first = self.queue()
        cash = self.save["userInfo"]["player"]["cash"]
        commands = [self.command("UserService.setSeenFlag", ["beforeCraftRush"], 80),
            self.command("CraftingService.onRushRecipe", ["b3", 1000, True, 0], 81),
            self.command("CraftingService.onRushRecipe", ["b3", 1000, False, 0], 82),
            self.command("CraftingService.onClaimFinishedRecipes", ["b3", 0], 83),
            self.command("UserService.setSeenFlag", ["afterCraftRush"], 84)]
        with mock.patch.object(crafting, "timestamp_now", return_value=1020):
            results = fixtures.gateway_results(self, self.gateway(commands), [0, 29, 0, 0, 0])
        self.assertEqual(results[3]["data"][0]["start_ts"], first["start_ts"])
        self.assertEqual(self.save["userInfo"]["player"]["cash"], cash - 5)
        self.assertTrue(self.save["userInfo"]["player"]["seenFlags"]["beforeCraftRush"])
        self.assertTrue(self.save["userInfo"]["player"]["seenFlags"]["afterCraftRush"])
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-7"]["b3:3"][0], 1)
        self.assertEqual(self.save["craftingState"]["recipeQueue"]["bakery"], [])
        self.assertNotIn("81", self.save["craftingState"]["localCraftingRequests"])
        persisted = json.loads(self.path.read_text())
        self.assertEqual(persisted["craftingState"], self.save["craftingState"])
        self.assertEqual(persisted["userInfo"]["player"]["cash"], cash - 5)

    def test_evicted_paid_upgrade_request_cannot_buy_next_level_after_256_signed_actions(self):
        self.prepare(experience=0)
        self.send("CraftingService.onBuyCraftUpgrade", ["bakery", True], sequence=1)
        commands = [self.command("CraftingService.onMarkCottageHistorySeen", ["bakery"], sequence)
                    for sequence in range(2, 258)]
        with mock.patch.object(crafting, "timestamp_now", return_value=1001):
            fixtures.gateway_results(self, self.gateway(commands), [0] * len(commands))
        state = self.save["craftingState"]
        self.assertEqual(len(state["localCraftingRequests"]), 256)
        self.assertNotIn("1", state["localCraftingRequests"])
        self.assertEqual(state["localCraftingHighestSequence"], 257)
        self.assertEqual((self.craft["level"], self.save["userInfo"]["player"]["cash"]), (2, 185))
        self.reject_unchanged("CraftingService.onBuyCraftUpgrade", ["bakery", True], sequence=1)
        accepted = copy.deepcopy(self.save)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.reject_unchanged("CraftingService.onBuyCraftUpgrade", ["bakery", True], sequence=1)
        self.assertEqual(self.save, accepted)


if __name__ == "__main__":
    unittest.main()
