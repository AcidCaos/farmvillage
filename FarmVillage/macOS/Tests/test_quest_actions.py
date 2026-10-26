"""Recovered quest categories and actual successful world-action progress."""
from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
from test_minion_round3_quests import QuestFixture, quest, task
import test_construction_wire as construction_wire
import quests


class CatalogActionTests(QuestFixture):
    def setUp(self):
        super().setUp()
        self.stack.enter_context(mock.patch.object(quests, "_item_categories", {
            "redFruit": {"SB", "CB"}, "buildings": {"SITE"},
        }))
        self.define(quest("harvest", [
            task("harvestByCategory", type_="redFruit", total=2),
            {**task("harvestBySubtype", type_="seed", total=3), "subtype": "fruit"},
            {**task("harvestBySubtype", type_="seed", total=3), "subtype": "vegetable"},
            task("harvestByCategory", type_="missing", total=1),
        ]))
        self.activate("harvest")

    def test_category_and_subtype_match_separately_and_cap_at_total(self):
        item = {"code": "SB", "type": "seed", "subtype": "fruit"}
        for _ in range(4):
            quests.record_item_action(self.save, "harvest", item)
        self.assertEqual(self.progress_of("harvest"), [2, 3, 0, 0])

    def test_wrong_item_type_and_case_cannot_match_a_subtype_or_category(self):
        quests.record_item_action(self.save, "harvest", {"code": "sb", "type": "tree", "subtype": "fruit"})
        self.assertEqual(self.progress_of("harvest"), [0, 0, 0, 0])

    def test_unrelated_actions_and_nonpositive_counts_do_not_advance(self):
        item = {"code": "SB", "type": "seed", "subtype": "fruit"}
        for action, count in (("buy", 1), ("harvest", 0), ("harvest", -1), ("harvest", True)):
            quests.record_item_action(self.save, action, item, count)
        self.assertEqual(self.progress_of("harvest"), [0, 0, 0, 0])

    def test_progress_survives_json_reload_without_becoming_a_derived_count(self):
        quests.record_item_action(self.save, "harvest", {"code": "SB", "type": "seed", "subtype": "fruit"})
        self.save = json.loads(json.dumps(self.save))
        self.assertEqual(self.progress_of("harvest"), [1, 1, 0, 0])

    def test_generic_report_cannot_forge_authoritative_quest_progress(self):
        for action in quests.TRACKED_TASK_ACTIONS + quests.DERIVED_TASK_ACTIONS:
            with self.subTest(action=action), self.assertRaises(ValueError):
                quests.increment_generic_farm_task(self.save, action)
        self.assertEqual(self.progress_of("harvest"), [0, 0, 0, 0])

    def test_typed_action_requires_the_matching_item(self):
        self.define(quest("typed", [task("harvestByCode", type_="SB", total=1)]))
        self.activate("typed")
        quests.record_action(self.save, "harvestByCode")
        self.assertEqual(self.progress_of("typed"), [0])

    def test_completed_purchase_counts_but_unfinished_site_purchase_does_not(self):
        self.define(quest("purchase", [task("buyItemByCategory", type_="buildings", total=2),
            task("completeConstructionBuildingOrBuyCompleteItemByCategory", type_="buildings", total=2)]))
        self.activate("purchase")
        quests.record_item_action(self.save, "buy", {"code": "SITE", "finishedName": "completed"},
                                  placed_object={"itemName": "site", "state": "construction"})
        self.assertEqual(self.progress_of("purchase"), [1, 0])
        quests.record_item_action(self.save, "buy", {"code": "SITE"},
                                  placed_object={"itemName": "completed", "state": "built"})
        self.assertEqual(self.progress_of("purchase"), [2, 1])

    def test_same_name_incomplete_stable_cannot_earn_completion_credit(self):
        import construction
        item = {"name": "horsestablewhite", "code": "K0", "className": "HorseStableBuilding",
                "storageType": {"itemClass": "horses"}}
        quests._item_categories["buildings"] = {item["code"]}
        self.define(quest("purchase", [task("buyItemByCategory", type_="buildings", total=2),
            task("completeConstructionBuildingOrBuyCompleteItemByCategory", type_="buildings", total=2)]))
        self.activate("purchase")
        with mock.patch.object(construction.items, "get_item_by_name", return_value=item):
            quests.record_item_action(self.save, "buy", item,
                                      placed_object={"itemName": item["name"], "isFullyBuilt": False})
        self.assertEqual(self.progress_of("purchase"), [1, 0])


class CategoryDecodeTests(unittest.TestCase):
    def test_category_references_and_subtype_survive_cache_decode(self):
        xml = b'''<questSettings><categories>
          <category name="fruit"><item code="SB"/><reference name="more"/></category>
          <category name="more"><item code="CB"/><reference name="fruit"/></category>
          <category name="unknown"><reference name="absent"/></category>
          </categories><quest name="q"><tasks>
          <task action="harvestBySubtype" type="seed" subtype="fruit" total="3"/>
          </tasks></quest></questSettings>'''
        decoded = quests._decode_quests(zlib.compress(xml))
        self.assertEqual(decoded["itemCategories"], {"fruit": ["CB", "SB"], "more": ["CB", "SB"], "unknown": []})
        self.assertEqual(decoded["quests"]["q"]["tasks"][0]["subtype"], "fruit")
        self.assertTrue(quests._valid_quests_cache(decoded))
        del decoded["itemCategories"]
        self.assertFalse(quests._valid_quests_cache(decoded))

    def test_archived_category_has_real_codes_and_subtype_tasks(self):
        decoded = quests._decode_quests(Path(quests.QUESTS_XML).read_bytes())
        self.assertEqual(decoded["itemCategories"]["allJackOLily"], ["nr8"])
        self.assertIn("0d", decoded["itemCategories"]["orchard"])
        self.assertEqual(next(t for t in decoded["quests"]["dakota-01-002"]["tasks"] if t["action"] == "harvestBySubtype")["subtype"], "fruit")


class ConstructionQuestWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway
    prepare = construction_wire.ConstructionWireTests.prepare
    def send(self, action, obj, options=None, *, sequence=None):
        if sequence is None:
            sequence = getattr(self, "_quest_sequence", 0) + 1
        self._quest_sequence = max(getattr(self, "_quest_sequence", 0), sequence)
        response = self.gateway([self.command("WorldService.performAction", [action, obj, [options or {}]], sequence)])
        return fixtures.gateway_results(self, response, [0])[0]["data"]
    snapshot = staticmethod(construction_wire.ConstructionWireTests.snapshot)
    gift = staticmethod(construction_wire.ConstructionWireTests.gift)
    persist = construction_wire.ConstructionWireTests.persist

    def setUp(self):
        fixtures.RuntimeFixtureTests.setUp(self)
        self.path, self.save, self.obj = self.prepare()
        self.quest_catalog = {}
        for key, value in (("_cached_quests", self.quest_catalog), ("_startable_quests", []),
                           ("_item_categories", {"turkeys": {"KX"}})):
            patcher = mock.patch.object(quests, key, value)
            patcher.start(); self.addCleanup(patcher.stop)
        self.save["questState"] = {"active": {}, "completed": [], "retired": [], "replayed": {}}

    def activate(self, tasks, reward=0):
        self.quest_catalog["build"] = quest("build", tasks, coins=reward)
        self.save["questState"]["active"]["build"] = {"progress": [0] * len(tasks), "new": 0}

    def progress(self):
        return self.player.session("fixture-farmer")["questState"]["active"]["build"]["progress"]

    def test_final_material_counts_once_despite_rejected_followup_in_batch(self):
        from items import get_item_by_name
        quests._item_categories["turkeys"] = {get_item_by_name("turkeyroost")["code"]}
        self.activate([task("completeConstructionBuildingByCategory", type_="turkeys", total=2),
                       task("completeConstructionBuildingOrBuyCompleteItemByCategory", type_="turkeys", total=2)])
        self.obj["contents"] = [{"itemCode": c, "numItem": n} for c, n in [("K1", 9), ("K4", 10), ("K5", 10)]]
        self.gift(self.save, "brick", 2); self.persist()
        raw = self.snapshot(self.obj); before = self.path.read_bytes()
        response = self.gateway([
            self.command("WorldService.performAction", ["store", raw, [{"storedItemName": "brick", "isGift": True}]]),
            self.command("WorldService.performAction", ["use", {"id": 999, "itemName": "cow"}, []], 2),
        ])
        fixtures.gateway_results(self, response, [0, 29])
        self.assertEqual(self.progress(), [1, 1])
        self.send("store", raw, {"storedItemName": "brick", "isGift": True}, sequence=1)
        self.assertEqual(self.progress(), [1, 1])
        self.send("store", raw, {"storedItemName": "brick", "isGift": True}, sequence=1)
        self.assertEqual(self.progress(), [1, 1])
        with redirect_stdout(io.StringIO()): self.player.load_saves()
        self.assertEqual(self.progress(), [1, 1])

    def test_partial_material_does_not_claim_completion(self):
        from items import get_item_by_name
        quests._item_categories["turkeys"] = {get_item_by_name("turkeyroost")["code"]}
        self.activate([task("completeConstructionBuildingByCategory", type_="turkeys")])
        self.gift(self.save, "brick")
        self.send("store", self.snapshot(self.obj), {"storedItemName": "brick", "isGift": True})
        self.assertEqual(self.progress(), [0])

    def test_real_harvest_updates_category_and_subtype_once_through_gateway(self):
        from items import get_item_by_name
        crop = get_item_by_name("strawberry")
        quests._item_categories["fruit"] = {crop["code"]}
        self.activate([task("harvestByCategory", type_="fruit", total=2),
                       {**task("harvestBySubtype", type_="seed", total=2), "subtype": crop["subtype"]}])
        plot = {"id": 42, "className": "Plot", "itemName": "strawberry", "state": "grown",
                "plantTime": 1000, "position": {"x": 2, "y": 2, "z": 0}}
        self.save["world"]["objectsArray"] = [plot]
        raw = {**plot, "state": "fallow", "plantTime": 0}
        self.send("harvest", raw, sequence=1)
        self.assertEqual(self.progress(), [1, 1])
        self.send("harvest", raw, sequence=1)
        self.assertEqual(self.progress(), [1, 1])
        with redirect_stdout(io.StringIO()): self.player.load_saves()
        self.assertEqual(self.progress(), [1, 1])

    def test_harvest_snapshot_cannot_change_item_for_rewards_or_quest_progress(self):
        from items import get_item_by_name
        straw, wheat = get_item_by_name("strawberry"), get_item_by_name("wheat")
        quests._item_categories["fruit"] = {straw["code"]}
        quests._item_categories["grain"] = {wheat["code"]}
        self.activate([task("harvestByCategory", type_="fruit", total=2),
                       task("harvestByCategory", type_="grain", total=2)])
        plot = {"id": 42, "className": "Plot", "itemName": "strawberry", "state": "grown",
                "plantTime": 1000, "position": {"x": 2, "y": 2, "z": 0}}
        self.save["world"]["objectsArray"] = [plot]
        self.send("harvest", {**plot, "itemName": "wheat", "state": "fallow", "plantTime": 0})
        self.assertEqual(self.progress(), [1, 0])
        saved = self.player.session("fixture-farmer")["world"]["objectsArray"][0]
        self.assertEqual(saved["itemName"], "strawberry")

    def test_expansion_counts_exact_level_and_not_legacy_construction(self):
        from items import get_item_by_name
        self.path, self.save, self.obj = self.prepare("turkeyroost_finished", built=True,
            expansionLevel=1.0, expansionParts={"K1": 14, "K4": 15, "K5": 15})
        del self.obj["isFullyBuilt"]  # Imported finished items need no explicit flag.
        code = get_item_by_name("turkeyroost_finished")["code"]
        quests._item_categories["turkeys"] = {code}
        self.activate([task("expandStorageBuildingToLevelByCode", type_=code, level=2),
                       task("expandStorageBuildingToLevelByCode", type_=code, level=3),
                       task("completeConstructionBuildingByCategory", type_="turkeys")])
        self.gift(self.save, "brick")
        self.send("store", self.snapshot(self.obj), {"storedItemName": "brick", "isGift": True})
        self.assertEqual(self.progress(), [1, 0, 0])

    def test_gift_placement_counts_purchase_but_inventory_withdrawal_does_not(self):
        from items import get_item_by_name
        cow = get_item_by_name("cow")
        quests._item_categories["animals"] = {cow["code"]}
        self.activate([task("buyItemByCode", type_=cow["code"], total=3),
                       task("buyItemByCategory", type_="animals", total=3)])
        self.gift(self.save, "cow", 1)
        self.save["userInfo"]["player"]["storageData"]["-2"] = {cow["code"]: [1, [], []]}
        gold = self.save["userInfo"]["player"]["gold"]
        raw = {"id": 63001, "itemName": "cow", "className": "Animal",
               "state": "bare", "position": {"x": 2, "y": 3, "z": 0}}
        self.send("place", raw, {"isGift": True}, sequence=1)
        self.assertEqual(self.progress(), [1, 1])
        self.send("place", raw, {"isGift": True}, sequence=1)
        self.assertEqual(self.progress(), [1, 1])
        raw["id"] += 1; raw["position"]["x"] += 2
        self.send("place", raw, {"isInventoryWithdrawal": True})
        self.assertEqual(self.progress(), [1, 1])
        self.assertEqual(self.player.session("fixture-farmer")["userInfo"]["player"]["gold"], gold)


if __name__ == "__main__":
    unittest.main()
