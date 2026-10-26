"""Maple's unavailable original backend must refuse mutations without save loss.

These are scripted Flask/AMF checks, not Maple gameplay/browser acceptance.
The synthetic imports deliberately retain opaque original fields and storage-75;
they do not claim to reconstruct the unavailable canadaStart.farm layout.
"""
import copy
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures  # Must precede every product import.
import crafting
from game_settings import level_to_xp
import world_travel


class MapleFrontierWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    def prepare(self, *, active="farm", owned_travel=False):
        self.path = self.write_fixture()
        save = self.player.session("fixture-farmer")
        # High synthetic funding proves refusal is not merely insufficient cash.
        save["userInfo"]["player"].update(gold=500000, cash=5000, xp=level_to_xp(15))
        if owned_travel:
            world_travel.unlock_england(save, "allAccess", now=1_800_000_000)
        user = save["userInfo"]
        user["currentWorldType"] = active
        user["worldSummaryData"]["canada"] = {
            "storageId": -75, "originalSummary": {"preserve": ["Maple", 75]}}
        user["player"]["storageData"]["-75"] = {"HB": [3, ["original-sender"], []]}
        save["opaqueImportedWorlds"] = {"canada": {
            "originalPayloadUnknown": True, "objectsArray": [
                {"id": 73001, "itemName": "xcd_rubbletreasure1",
                 "className": "MultiRewardTreasureConstructionBuilding",
                 "opaqueOriginalState": ["preserve", {"version": 5}]}]}}
        if active == "canada":
            save.pop(world_travel.STATE_KEY, None)
            save["world"]["originalMapleState"] = {"preserve": ["uninterpreted"]}
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")
        return save

    def reload(self):
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        return self.player.session("fixture-farmer")

    def rejected_unchanged(self, calls):
        save = self.player.session("fixture-farmer")
        before, disk = copy.deepcopy(save), self.path.read_bytes()
        result = fixtures.gateway_results(self, self.gateway(calls), [29] * len(calls))
        self.assertEqual(self.player.session("fixture-farmer"), before)
        self.assertEqual(self.path.read_bytes(), disk)
        self.assertEqual(self.reload(), before)
        self.assertEqual(self.path.read_bytes(), disk)
        return result

    @staticmethod
    def plot(**changes):
        return {"id": 64001, "tempId": -1, "className": "Plot", "itemName": None,
                "state": "plowed", "position": {"x": 4, "y": 4, "z": 0}, **changes}

    def test_original_unlock_access_types_and_replays_refuse_without_charge(self):
        self.prepare()
        # TExpansionWorldAccess.perform11715 sends accessType, optionally optionId.
        # No original starter/layout exists, so even a permitted allAccess gate
        # cannot authorize creating a replacement world.
        for params in (["allAccess"], ["earlyAccess"], ["generalAccess"],
                       ["allAccess", "original-option"]):
            with self.subTest(params=params):
                call = self.command("CanadaService.unlockCanadaWorld", params, sequence=71)
                self.rejected_unchanged([call, copy.deepcopy(call)])

    def test_malformed_unlock_calls_refuse_without_charge_or_import_replacement(self):
        self.prepare()
        for params in ([], [None], [False], [{}], [[]], ["unknownAccess"],
                       ["allAccess", None, "extra"]):
            with self.subTest(params=params):
                self.rejected_unchanged([
                    self.command("CanadaService.unlockCanadaWorld", params)])

    def test_unlock_refusal_keeps_accepted_neighboring_amf_calls_durable(self):
        save = self.prepare()
        before = copy.deepcopy(save)
        calls = [
            self.command("UserService.setSeenFlag", ["maple-before-control"], sequence=40),
            self.command("CanadaService.unlockCanadaWorld", ["allAccess"], sequence=41),
            self.command("UserService.setActionCount", ["maple-after-control", 9], sequence=42),
        ]
        fixtures.gateway_results(self, self.gateway(calls), [0, 29, 0])
        expected = copy.deepcopy(before)
        expected["userInfo"]["player"]["seenFlags"]["maple-before-control"] = True
        expected["userInfo"]["player"]["actionCounts"]["maple-after-control"] = 9
        self.assertEqual(self.reload(), expected)

    def test_imported_active_maple_refuses_farming_construction_crafting_and_travel(self):
        self.prepare(active="canada")
        plot = self.plot(worldType="canada")
        section = {"id": 73001, "itemName": "xcd_rubbletreasure1",
                   "className": "MultiRewardTreasureConstructionBuilding",
                   "worldType": "canada"}
        self.rejected_unchanged([
            self.command("WorldService.performAction", ["plow", plot, []]),
            self.command("WorldService.performAction", ["UnlockNow", section, []]),
            self.command("WorldService.performAction", ["TransformBuilding", section, []]),
            self.command("CraftingService.onBeginRecipe", ["not-a-supported-recipe", 0]),
            self.command("WorldService.loadOwnWorld", ["farm", False, False, False]),
            self.command("CanadaService.unlockCanadaWorld", ["allAccess"]),
        ])

    def test_maple_world_context_and_inventory_cannot_target_active_home(self):
        self.prepare(owned_travel=True)
        bale = {"id": 64002, "tempId": -1, "itemName": "haybale",
                "className": "Decoration", "position": {"x": 4, "y": 4, "z": 0}}
        self.rejected_unchanged([
            self.command("WorldService.performAction", ["plow", self.plot(worldType="canada"), []]),
            self.command("WorldService.performAction", ["plow", self.plot(), [{"currentWorldType": "canada"}]]),
            self.command("WorldService.performAction", ["place", bale, [{"isStorageWithdrawal": -75}]]),
            self.command("WorldService.performAction", ["store", {"id": -75, "itemName": "haybale"},
                         [{"storedItemName": "haybale", "target": -75}]]),
            self.command("WorldService.loadOwnWorld", ["canada", False, False, False]),
        ])

    def prepare_cottage(self, active):
        save = self.prepare(active=active)
        # A legacy import can contain a valid cottage from another world. The
        # ordinary recipe itself and all ingredients are valid; its current
        # world must still prevent mutation of the globally keyed craft state.
        save["world"]["objectsArray"] = [{
            "id": 73002, "itemName": "craftingbakery", "className": "CraftingCottageBuilding",
            "state": "built", "isFullyBuilt": True,
            "position": {"x": 4, "y": 4, "z": 0}, "originalImportedField": ["keep"]}]
        save["craftingState"] = {
            "craftingItems": [{"itemCode": "pu", "quantity": 4}, {"itemCode": "wh", "quantity": 4}],
            "maxCapacity": 400, "craftingSkillState": {"recipeStates": []}}
        with redirect_stdout(io.StringIO()):
            crafting.start_session(save)
            self.player.save_session("fixture-farmer")
        return save

    def test_valid_home_recipe_in_imported_maple_refuses_without_consuming_bushels(self):
        self.prepare_cottage("canada")
        self.rejected_unchanged([
            self.command("CraftingService.onBeginRecipe", ["b0", -1], sequence=91)])

    def test_valid_home_recipe_preserves_inactive_maple_without_a_global_crafting_gate(self):
        before = copy.deepcopy(self.prepare_cottage("farm"))
        result = fixtures.gateway_results(self, self.gateway([
            self.command("CraftingService.onBeginRecipe", ["b0", -1], sequence=92)]), [0])
        self.assertEqual(result[0]["data"]["id"], "b0")
        after = self.reload()
        self.assertEqual(len(after["craftingState"]["recipeQueue"]["bakery"]), 1)
        self.assertEqual(after["craftingState"]["craftingItems"],
                         [{"itemCode": "pu", "quantity": 0}, {"itemCode": "wh", "quantity": 0}])
        self.assertEqual(after["opaqueImportedWorlds"], before["opaqueImportedWorlds"])
        self.assertEqual(after["userInfo"]["worldSummaryData"]["canada"],
                         before["userInfo"]["worldSummaryData"]["canada"])
        self.assertEqual(after["userInfo"]["player"]["storageData"]["-75"],
                         before["userInfo"]["player"]["storageData"]["-75"])

    def test_retired_event_startup_compatibility_is_preserved(self):
        before = copy.deepcopy(self.prepare())
        fixtures.gateway_results(self, self.gateway([
            self.command("CanadaInnovationService.startQuest", ["CanadaInnovation"], sequence=111),
            self.command("CanadaInnovationService.featureEnd", ["CanadaInnovation"], sequence=112)]), [0, 0])
        expected = copy.deepcopy(before)
        expected["userInfo"]["featureOptions"].setdefault("CanadaInnovation", {})["forceGranted"] = 1
        self.assertEqual(self.reload(), expected)

    def test_original_innovation_paid_sink_task_and_harvest_packets_refuse(self):
        self.prepare()
        # Original CanadaInnovationManager methods19947/19948/19943 send
        # featureName, taskIndex; method19980 sends featureName, buildingType.
        # These callbacks deduct gold/bushels, change tasks or grant a gift.
        for method, params in (
                ("sinkGold", ["CanadaInnovation", 0]),
                ("sinkBushel", ["CanadaInnovation", 0]),
                ("getNewTask", ["CanadaInnovation", 0]),
                ("harvestDecos", ["CanadaInnovation", "novice"])):
            with self.subTest(method=method):
                call = self.command("CanadaInnovationService." + method, params, sequence=103)
                self.rejected_unchanged([call, copy.deepcopy(call)])

    def test_each_recovered_innovation_mutation_refuses_even_without_backend_state(self):
        self.prepare()
        # All25 non-startup mutation senders recovered from the original
        # CanadaInnovationManager. This is independent of the production set:
        # a newly omitted endpoint would silently acknowledge and fail here.
        methods = (
            "addNormalCandiesToStation", "dumpTask", "getNewTask",
            "grantPointForNormalCandies", "grantPointForSpecialCandies", "grantRedeemPoints",
            "harvestDecos", "makeSpecialCandy", "collectSpecialCandy", "skipKidWaitTime",
            "stationBuyBT", "tryBuyBT", "redeemRewardPoints", "resetDataAndSetNewWeek",
            "resetSlot", "setNewTaskLayer", "addInventoryTileUnlockCount",
            "updateTileUnlockCount", "sinkBushel", "sinkGold", "skipDumpedTask", "skipTask",
            "startNewDay", "updateKidsStatusByKidWithRetuenTime", "updateKidWaitTimer")
        self.assertEqual(len(methods), 25)
        for method in methods:
            with self.subTest(method=method):
                # Every original packet starts with featureName. Missing
                # remaining arguments must be refused as well, never acked.
                self.rejected_unchanged([self.command(
                    "CanadaInnovationService." + method, ["CanadaInnovation"], sequence=121)])

    def test_inactive_maple_data_survives_home_actions_and_reload(self):
        save = self.prepare(owned_travel=True)
        before = copy.deepcopy(save)
        calls = [self.command("WorldService.performAction", ["plow", self.plot(), []]),
                 self.command("CanadaService.unlockCanadaWorld", ["earlyAccess"], sequence=2)]
        fixtures.gateway_results(self, self.gateway(calls), [0, 29])
        after = self.reload()
        self.assertEqual(after["opaqueImportedWorlds"], before["opaqueImportedWorlds"])
        self.assertEqual(after["userInfo"]["worldSummaryData"]["canada"],
                         before["userInfo"]["worldSummaryData"]["canada"])
        self.assertEqual(after["userInfo"]["player"]["storageData"]["-75"],
                         before["userInfo"]["player"]["storageData"]["-75"])
        self.assertEqual(after[world_travel.STATE_KEY]["inactive"],
                         before[world_travel.STATE_KEY]["inactive"])
        self.assertEqual(after["userInfo"]["player"]["gold"],
                         before["userInfo"]["player"]["gold"] - 15)
        self.assertEqual(len(after["world"]["objectsArray"]), len(before["world"]["objectsArray"]) + 1)


if __name__ == "__main__":
    unittest.main()
