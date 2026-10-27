"""Recovered Home cottage onboarding over real AMF and archived catalogs."""
from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures  # Resolve temporary runtime paths first.
import crafting
import items


class CottageLifecycleTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    def prepare(self):
        self.path = self.write_fixture()
        save = self.player.session("fixture-farmer")
        save["world"]["objectsArray"] = []
        save["userInfo"]["currentWorldType"] = "farm"
        save["userInfo"]["player"].update(xp=100015, gold=1000000, cash=100,
            energy=5, storageData={}, seenFlags={"importedFlag": True})
        save["craftingState"] = {"craftingItems": [], "maxCapacity": 5,
            "craftingSkillState": {"recipeStates": [], "craftTypes": []},
            "importedState": {"preserve": [1, 2]}}
        with redirect_stdout(io.StringIO()):
            crafting.start_session(save)
            self.player.save_session("fixture-farmer")
        self.sequence = 0
        return save

    @property
    def save(self):
        return self.player.session("fixture-farmer")

    def send(self, method, params=(), *, now=1000, reject=False, sequence=None):
        from pyamf import remoting
        self.sequence += 1
        with mock.patch.object(crafting, "timestamp_now", return_value=now), \
                mock.patch.object(self.server.commands, "timestamp_now", return_value=now):
            response = self.gateway([self.command(method, params,
                sequence=self.sequence if sequence is None else sequence)])
        fixtures.assert_gateway_status(self, response, 400 if reject else 200)
        results = remoting.decode(response.data).bodies[0][1].body["data"]
        return results[0]["data"]

    def reject_unchanged(self, method, params=(), **kw):
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.send(method, params, reject=True, **kw)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)

    @staticmethod
    def snapshot(name="craftingwinery", ident=63001):
        return {"id": ident, "itemName": name, "className": "CraftingCottageBuilding",
            "state": "built", "isFullyBuilt": True, "position": {"x": 10, "y": 10, "z": 0},
            "contents": {},
            "recipeQueue": [{"forged": True}], "finishedRecipes": {"w0": {"qty": 900}},
            "craftLevel": 5, "foundingTS": 1, "historyXPGain": 999}

    def claim_and_place(self, craft="winery", *, seen_before_place=False):
        name = crafting.COTTAGES[craft]
        code = items.get_item_by_name(name)["code"]
        self.send("CraftingService.onClaimFreeCottage", [code])
        if seen_before_place:
            self.send("UserService.setSeenFlag", ["placeCottage"])
        snapshot = self.snapshot(name)
        result = self.send("WorldService.performAction", ["place", snapshot, [{"isGift": True}]])
        return result["id"]

    def test_original_winery_and_spa_contracts(self):
        self.prepare()
        for craft, name, code, ingredients in (
                ("winery", "craftingwinery", "w0", {"rc": 5, "ci": 3}),
                ("perfumery", "craftingspa", "p0", {"pu": 3, "ci": 3, "sf": 1})):
            with self.subTest(craft=craft):
                self.assertEqual(crafting.COTTAGES[craft], name)
                recipe = crafting._recipe(code)
                self.assertEqual(crafting._ingredients(recipe), ingredients)
                self.assertEqual(recipe.findtext("MinutesToCook"), "360")
                self.assertEqual(recipe.find("Reward/OnMake").attrib,
                                 {"recipeXp": "1", "playerXp": "50"})

    def test_free_choice_is_durable_once_only_and_does_not_charge(self):
        self.prepare()
        balance = {key: self.save["userInfo"]["player"][key] for key in ("gold", "cash", "xp")}
        self.assertEqual(self.send("CraftingService.onClaimFreeCottage", ["L9"], sequence=10), {})
        self.assertEqual(self.send("CraftingService.onClaimFreeCottage", ["L9"], sequence=10), {})
        self.send("CraftingService.onClaimFreeCottage", ["L9"], sequence=11)
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-1"], {"L9": [1, [], []]})
        self.assertTrue(self.save["userInfo"]["player"]["seenFlags"]["UnlockedCottage"])
        self.reject_unchanged("CraftingService.onClaimFreeCottage", ["LA"], sequence=12)
        self.reject_unchanged("CraftingService.onClaimFreeCottage", ["LA"], sequence=10)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
            crafting.start_session(self.save)
        self.send("CraftingService.onClaimFreeCottage", ["L9"], sequence=10)
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-1"]["L9"][0], 1)
        self.assertEqual({key: self.save["userInfo"]["player"][key] for key in balance}, balance)
        self.assertTrue(self.save["userInfo"]["player"]["seenFlags"]["importedFlag"])

    def test_claim_rejects_wrong_world_level_item_and_capacity_atomically(self):
        self.prepare()
        for params in ([], ["L9", "extra"], [True], [[]], ["cow"], ["jm"]):
            self.reject_unchanged("CraftingService.onClaimFreeCottage", params)
        self.save["userInfo"]["currentWorldType"] = "england"
        self.reject_unchanged("CraftingService.onClaimFreeCottage", ["L9"])
        self.save["userInfo"]["currentWorldType"] = "farm"
        self.save["userInfo"]["player"]["xp"] = 0
        self.reject_unchanged("CraftingService.onClaimFreeCottage", ["L9"])
        self.save["userInfo"]["player"]["xp"] = 100015
        self.save["userInfo"]["player"]["storageData"] = {"-1": {"chicken": [2147483647, [], []]}}
        self.reject_unchanged("CraftingService.onClaimFreeCottage", ["L9"])

    def test_free_winery_placement_onboarding_claim_and_reload(self):
        self.prepare()
        ident = self.claim_and_place(seen_before_place=True)
        cottage = self.save["world"]["objectsArray"][0]
        self.assertEqual(cottage["id"], ident)
        self.assertEqual(cottage["craftLevel"], 1)
        self.assertEqual(cottage["foundingTS"], 1000)
        self.assertNotIn("historyXPGain", cottage)
        self.assertEqual(cottage["finishedRecipes"], {})
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-1"], {})
        bonus = copy.deepcopy(cottage["recipeQueue"][0])
        self.assertEqual((bonus["id"], bonus["start_ts"], bonus["finish_ts"]), ("w0", 1, 1005))
        self.assertEqual(bonus["recipe"]["MinutesToCook"], "0.1")
        self.assertEqual({row["itemCode"]: row["quantity"] for row in self.save["craftingState"]["craftingItems"]},
                         {"rc": 5, "ci": 3})
        self.reject_unchanged("CraftingService.onClaimFinishedRecipes", ["w0", -1], now=1004)
        # The original placement can retry with its temporary ID and stale client fields.
        self.send("WorldService.performAction", ["place", self.snapshot(), [{"isGift": True}]], now=1001)
        self.assertEqual(self.save["world"]["objectsArray"][0]["recipeQueue"], [bonus])
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
            crafting.start_session(self.save)
        self.assertEqual(self.save["world"]["objectsArray"][0]["recipeQueue"], [bonus])
        result = self.send("CraftingService.onClaimFinishedRecipes", ["w0", -1], now=1005)
        self.assertEqual(result[0]["recipeId"], "w0")
        self.assertEqual(result[0]["start_ts"], 1)
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-7"], {"w0:1": [1, [], []]})
        # Paid production after onboarding uses the unmodified six-hour catalog clock.
        self.send("CraftingService.onBeginRecipe", ["w0", -1], now=1006)
        queued = self.save["world"]["objectsArray"][0]["recipeQueue"][0]
        self.assertEqual((queued["start_ts"], queued["finish_ts"]), (1006, 22606))
        self.assertEqual(self.save["userInfo"]["player"]["xp"], 100065)

    def test_spa_uses_same_original_onboarding_and_production_contract(self):
        self.prepare()
        self.claim_and_place("perfumery")
        bonus = self.save["world"]["objectsArray"][0]["recipeQueue"][0]
        self.assertEqual(bonus["id"], "p0")
        self.send("CraftingService.onClaimFinishedRecipes", ["p0", -1], now=1005)
        self.send("CraftingService.onBeginRecipe", ["p0", -1], now=1006)
        self.assertEqual(self.save["world"]["objectsArray"][0]["recipeQueue"][0]["finish_ts"], 22606)

    def test_first_market_placement_keeps_onboarding_when_seen_rpc_arrives_first(self):
        self.prepare()
        self.send("UserService.setSeenFlag", ["placeCottage"])
        result = self.send("WorldService.performAction", ["place", self.snapshot(), [{"currency": "coins"}]])
        self.assertEqual(result["id"], self.save["world"]["objectsArray"][0]["id"])
        self.assertEqual(self.save["world"]["objectsArray"][0]["recipeQueue"][0]["finish_ts"], 1005)
        self.assertEqual(self.save["userInfo"]["player"]["gold"], 1000000)
        self.assertEqual(self.save["userInfo"]["player"]["xp"], 100015)

    def test_next_cottage_market_tier_charges_once_without_repeating_onboarding(self):
        self.prepare()
        self.claim_and_place("bakery")
        before_items = copy.deepcopy(self.save["craftingState"]["craftingItems"])
        bakery_queue = copy.deepcopy(self.save["world"]["objectsArray"][0]["recipeQueue"])
        pub = self.snapshot("xukcraftingpub", ident=63002)
        charges = []
        actual_charge = self.server.commands.engine.apply_item_cost
        def charge(save, item, *args, **kw):
            before = save["userInfo"]["player"]["gold"]
            actual_charge(save, item, *args, **kw)
            charges.append(before - save["userInfo"]["player"]["gold"])
        with mock.patch.object(self.server.commands.engine, "apply_item_cost", side_effect=charge):
            result = self.send("WorldService.performAction", ["place", pub, [{"currency": "coins"}]])
        self.assertEqual(charges, [10000])
        # Placement can earn an independent ribbon reward. The purchase debit
        # is observed separately so that reward cannot conceal a wrong charge.
        self.assertGreaterEqual(self.save["userInfo"]["player"]["xp"], 101015)
        after = {key: self.save["userInfo"]["player"][key] for key in ("gold", "cash", "xp")}
        self.assertEqual(self.save["craftingState"]["craftingItems"], before_items)
        self.assertEqual(self.save["world"]["objectsArray"][0]["recipeQueue"], bakery_queue)
        self.assertEqual(self.save["world"]["objectsArray"][1]["recipeQueue"], [])
        self.send("WorldService.performAction", ["place", self.snapshot("xukcraftingpub", ident=63002),
            [{"currency": "coins"}]], now=1001)
        self.assertEqual(len(self.save["world"]["objectsArray"]), 2)
        self.assertEqual({key: self.save["userInfo"]["player"][key] for key in after}, after)
        self.assertEqual(self.save["world"]["objectsArray"][1]["id"], result["id"])

    def test_cottage_price_view_counts_gifts_and_leaves_archived_catalog_untouched(self):
        self.prepare()
        pub = items.get_item_by_name("xukcraftingpub")
        original = copy.deepcopy(pub)
        self.assertEqual(crafting.purchase_catalog_item(self.save, pub)["cost"], "1000")
        self.send("CraftingService.onClaimFreeCottage", ["L9"])
        self.assertEqual(crafting.purchase_catalog_item(self.save, pub)["cost"], "10000")
        self.assertEqual(pub, original)
        self.assertEqual(crafting.purchase_catalog_item(self.save, items.get_item_by_name("craftingspa"))["cost"], "0")

    def test_history_and_startup_reads_do_not_replace_production(self):
        self.prepare()
        ident = self.claim_and_place()
        cottage = self.save["world"]["objectsArray"][0]
        history = [{"timestamp": 900, "coins": 1000, "imported": "keep"}]
        cottage.update(transactionHistory=history, historyXPGain=5)
        before_queue = copy.deepcopy(cottage["recipeQueue"])
        self.assertEqual(self.send("CraftingService.onMarkCottageHistorySeen", ["winery"], now=1003), {"responseCode": 0})
        cottage = self.save["world"]["objectsArray"][0]
        self.assertEqual(cottage["transactionHistory"], history)
        self.assertEqual(cottage["historyLastViewedTS"], 1003)
        self.assertEqual(cottage["historyXPGain"], 0)
        snapshot = self.snapshot(ident=ident)
        before = copy.deepcopy(self.save)
        self.send("WorldService.performAction", ["getStorageInfo", snapshot, [{}]])
        self.assertEqual(self.save, before)
        self.send("WorldService.performAction", ["move", dict(snapshot, position={"x": 15, "y": 15, "z": 0}), []])
        cottage = self.save["world"]["objectsArray"][0]
        self.assertEqual(cottage["recipeQueue"], before_queue)
        self.assertEqual(cottage["historyLastViewedTS"], 1003)
        self.reject_unchanged("CraftingService.onMarkCottageHistorySeen", ["bakery"])
        self.reject_unchanged("WorldService.performAction", ["sell", snapshot, []])

    def test_tutorial_tractor_requires_goods_and_grants_once_across_sessions(self):
        self.prepare()
        self.reject_unchanged("CraftingService.onCompleteCottageTutorial")
        self.claim_and_place()
        self.reject_unchanged("CraftingService.onCompleteCottageTutorial")
        self.send("CraftingService.onClaimFinishedRecipes", ["w0", -1], now=1005)
        self.send("CraftingService.onCompleteCottageTutorial", now=1005, sequence=20)
        self.send("CraftingService.onCompleteCottageTutorial", now=1005, sequence=20)
        tractor_code = items.get_item_by_name("tractor")["code"]
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-1"][tractor_code], [1, [], []])
        # Original tutorial branch awards a tractor without consuming the good or fuel.
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-7"]["w0:1"][0], 1)
        self.assertEqual(self.save["userInfo"]["player"]["energy"], 5)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
            crafting.start_session(self.save)
        self.send("CraftingService.onCompleteCottageTutorial", now=1006, sequence=21)
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-1"][tractor_code][0], 1)
        self.reject_unchanged("CraftingService.onCompleteCottageTutorial", ["extra"])

    def test_tutorial_does_not_award_a_tractor_to_a_farm_with_equipment(self):
        self.prepare()
        self.claim_and_place()
        self.send("CraftingService.onClaimFinishedRecipes", ["w0", -1], now=1005)
        self.save["world"]["objectsArray"].append({"id": 20, "itemName": "tractor", "className": "Tractor"})
        self.reject_unchanged("CraftingService.onCompleteCottageTutorial")

    def test_imported_winery_keeps_existing_queue_and_gets_no_onboarding(self):
        self.prepare()
        cottage = self.snapshot(ident=600)
        cottage.update(recipeQueue=[{"id": "w0", "start_ts": 123, "finish_ts": 21723, "ovenSlot": 0}],
                       finishedRecipes={}, craftLevel=1)
        self.save["world"]["objectsArray"] = [cottage]
        original = copy.deepcopy(cottage["recipeQueue"])
        crafting.start_session(self.save)
        crafting.initialize(self.save)
        self.assertEqual(self.save["world"]["objectsArray"][0]["recipeQueue"], original)
        self.assertEqual(self.save["craftingState"]["craftingItems"], [])
        self.assertNotIn("localCottageOnboardingGranted", self.save["craftingState"])
        self.assertTrue(any(r["m_type"] == "w0" and r["m_isUnlocked"]
                            for r in self.save["craftingState"]["craftingSkillState"]["recipeStates"]))

    def test_all_home_cottage_contents_remain_amf_arrays_after_claim_move_and_reload(self):
        for craft, code in (("bakery", "b0"), ("winery", "w0"), ("perfumery", "p0")):
            with self.subTest(craft=craft):
                self.prepare()
                ident = self.claim_and_place(craft)
                cottage = self.save["world"]["objectsArray"][0]
                self.assertIsInstance(cottage["contents"], list)
                # Keep a normal six-hour recipe while claiming the independent
                # first-placement bonus, matching the browser-discovered farm.
                self.send("CraftingService.onBeginRecipe", [code, 1], now=1001)
                timer = copy.deepcopy(self.save["world"]["objectsArray"][0]["recipeQueue"][1])
                self.send("CraftingService.onClaimFinishedRecipes", [code, 0], now=1005)
                self.send("WorldService.performAction", ["move",
                    self.snapshot(crafting.COTTAGES[craft], ident), []], now=1005)
                goods = copy.deepcopy(self.save["userInfo"]["player"]["storageData"])
                with redirect_stdout(io.StringIO()):
                    self.player.load_saves()
                # Exercise the real AMF serializer after persistent reload.
                result = self.send("UserService.initUser", ["Cottage reload fixture", 0, True, None], now=1006)
                loaded = next(o for o in result["world"]["objectsArray"] if o["id"] == ident)
                self.assertIsInstance(loaded["contents"], list)
                self.assertEqual(loaded["contents"], [])
                self.assertIsInstance(loaded["recipeQueue"], list)
                self.assertEqual(loaded["recipeQueue"], [timer])
                self.assertIsInstance(loaded["finishedRecipes"], dict)
                self.assertEqual(loaded["finishedRecipes"][code]["qty"], 2)
                self.assertEqual(self.save["userInfo"]["player"]["storageData"], goods)
                disk = json.loads(self.path.read_text())
                self.assertEqual(disk["world"]["objectsArray"][0]["contents"], [])

    def test_empty_contents_repair_preserves_nonempty_imported_rows_and_production(self):
        self.prepare()
        self.claim_and_place()
        cottage = self.save["world"]["objectsArray"][0]
        queue = copy.deepcopy(cottage["recipeQueue"])
        cottage["contents"] = {}
        crafting.initialize(self.save)
        self.assertEqual(self.save["world"]["objectsArray"][0]["contents"], [])
        self.assertEqual(self.save["world"]["objectsArray"][0]["recipeQueue"], queue)
        for contents in ([{"itemName": "imported", "numItem": 2, "metadata": {"keep": True}}],
                         {"imported-specialized-row": {"keep": True}}):
            self.save["world"]["objectsArray"][0]["contents"] = copy.deepcopy(contents)
            crafting.initialize(self.save)
            self.assertEqual(self.save["world"]["objectsArray"][0]["contents"], contents)
            self.assertEqual(self.save["world"]["objectsArray"][0]["recipeQueue"], queue)


if __name__ == "__main__":
    unittest.main()
