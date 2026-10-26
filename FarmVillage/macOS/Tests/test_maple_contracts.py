"""Dormant Maple contracts: source fidelity and refusals, no farm acceptance."""
import copy
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence  # Isolated writable paths must precede product imports.
import maple_contracts as maple


class MapleContractTests(unittest.TestCase):
    def facts(self):
        return {"world": "canada", "player_level": 15,
                "experiments": {"fv_xcd_master": 1}, "craft_level": 5,
                "cottage_present": True, "recipe_unlocked": True}

    def test_all_twenty_one_workshop_recipes_and_skill_gates(self):
        expected = {
            1: {"2o74", "2o9z", "2obb", "2ob3", "2o5s", "2o7l", "2o7n", "2o7a", "2oa7", "2noj"},
            2: {"2obe", "2o5p", "2o5t", "2o4p"},
            3: {"2o94", "2ob8", "2oa4"},
            4: {"2o9o", "2o4f"}, 5: {"2o7z", "2o0x"}}
        self.assertEqual(set(maple.workshop_recipes()), set().union(*expected.values()))
        self.assertEqual(len(maple.workshop_recipes()), 21)
        for required, codes in expected.items():
            for code in codes:
                with self.subTest(code=code):
                    row = maple.workshop_recipe(code)
                    self.assertEqual(row["skillLevelRequired"], required)
                    self.assertEqual(row["craft"], "xcdcrafttype")
                    self.assertEqual(row["rushCostCash"], 5)
                    self.assertEqual(row["rushCostCoins"], -1)
                    facts = self.facts(); facts["craft_level"] = required
                    maple.workshop_preflight(code, **facts)
                    if required > 1:
                        facts["craft_level"] -= 1
                        with self.assertRaisesRegex(ValueError, "locked"):
                            maple.workshop_preflight(code, **facts)

    def test_complete_catalog_target_identity_duplicates_are_visible(self):
        audit = maple.catalog_identity_audit()
        self.assertEqual(audit["catalogRecords"], 111206)
        self.assertEqual(audit["targetDuplicateRows"], [])
        self.assertEqual(len(audit["targetCodes"]), 24)

    def test_conflicting_original_target_code_is_refused(self):
        codes, duplicates, count = maple._catalog()
        with patch.object(maple, "_catalog", return_value=(codes, duplicates + [
                {"code": "2nnz", "identical": False, "firstName": "lodge", "nextName": "other"}], count)):
            maple._sources.cache_clear()
            try:
                with self.assertRaisesRegex(ValueError, "Conflicting original Maple"):
                    maple.workshop_recipes()
            finally:
                maple._sources.cache_clear()

    def test_conflicting_original_recipe_xml_identity_is_refused(self):
        root = maple._xml("crafting.xml.gz")
        recipes = root.find("recipes")
        recipe = next(r for r in recipes if r.get("id") == "2o74")
        duplicate = copy.deepcopy(recipe)
        duplicate.find("MinutesToCook").text = "0"
        recipes.append(duplicate)
        original = maple._xml
        with patch.object(maple, "_xml", side_effect=lambda name: root if name == "crafting.xml.gz" else original(name)):
            maple._sources.cache_clear()
            try:
                with self.assertRaisesRegex(ValueError, "Conflicting original Maple recipe"):
                    maple.workshop_recipes()
            finally:
                maple._sources.cache_clear()

    def test_every_score_threshold_predecessor_and_following_point(self):
        score = maple.world_score_contract()
        self.assertEqual(score["id"], "canadaPoints")
        self.assertEqual(score["prereq"], "fv_xcd_shared")
        self.assertEqual(len(score["level"]), 151)
        self.assertEqual(len(score["task"]), 18)
        for row in score["level"]:
            level, threshold = int(row["num"]), int(row["required"])
            with self.subTest(level=level):
                at = maple.world_score_at_points(threshold)
                self.assertEqual(at["level"], level)
                self.assertEqual(at["levelContract"], row)
                self.assertFalse(at["awardsApplied"])
                if threshold:
                    self.assertEqual(maple.world_score_at_points(threshold - 1)["level"], level - 1)
                expected_next = max(int(x["num"]) for x in score["level"] if int(x["required"]) <= threshold + 1)
                self.assertEqual(maple.world_score_at_points(threshold + 1)["level"], expected_next)
        self.assertEqual(maple.world_score_at_points(136625)["level"], 150)
        self.assertIsNone(maple.world_score_at_points(2_147_483_647)["nextRequired"])

    def test_score_display_rows_default_rewards_and_tasks_never_grant(self):
        score = maple.world_score_contract()
        self.assertEqual(score["defaultLevel"]["rewards"]["reward"], [
            {"type": "coins", "value": "5000"},
            {"type": "display_only", "quantity": "1", "value": "uh5"}])
        rows = maple.world_score_at_points(10)["levelContract"]["rewards"]["reward"]
        self.assertEqual([r["type"] for r in rows], ["display_only", "item_grant"])
        self.assertEqual(score["task"][0]["action"], "useInstantGrow")
        self.assertEqual(score["task"][0]["total"], "20")
        self.assertEqual(score["task"][0]["rewards"]["reward"]["value"], "4")
        self.assertEqual([t["rewards"]["reward"]["value"] for t in score["task"] if t["type"] == "2nj7"],
                         ["100", "200", "300", "400", "500", "700", "1000", "1250", "1500"])
        score["defaultLevel"]["rewards"]["reward"][0]["value"] = "0"
        rows.clear()
        self.assertEqual(maple.world_score_contract()["defaultLevel"]["rewards"]["reward"][0]["value"], "5000")
        self.assertEqual(len(maple.world_score_at_points(10)["levelContract"]["rewards"]["reward"]), 2)
        for points in (True, -1, "10", None, 1.5, float("inf"), 2_147_483_648):
            with self.subTest(points=points), self.assertRaises(ValueError):
                maple.world_score_at_points(points)

    def test_first_recipe_exact_bushels_timer_rewards_and_mastery(self):
        row = maple.workshop_recipe("2o74")
        self.assertEqual(row["minutesToCook"], 120)
        self.assertEqual(row["initialRecipeLevel"], 1)
        self.assertEqual(row["ingredients"], [
            {"itemCode": "2nh6", "quantityRequired": "3"},
            {"itemCode": "2nhd", "quantityRequired": "3"},
            {"itemCode": "2nkl", "quantityRequired": "3"}])
        self.assertEqual(row["rewards"]["children"][0]["attributes"], {"recipeXp": "1", "playerXp": "50"})
        self.assertEqual(row["rewards"]["children"][1]["attributes"], {"itemCode": "2o74", "sellQty": "2", "giftQty": "1"})
        self.assertEqual([x["attributes"]["count"] for x in row["mastery"]["children"]], ["10", "20", "30", "40", "50"])

    def test_preflight_requires_every_client_fact_without_mutation(self):
        facts = self.facts(); before = copy.deepcopy(facts)
        maple.workshop_preflight("2o74", **facts)
        self.assertEqual(facts, before)
        invalid = {"world": ("farm", None, "CANADA"), "player_level": (14, True, "15", -1),
                   "experiments": ({}, {"fv_xcd_master": True}, {"fv_xcd_master": 0}, None),
                   "craft_level": (0, 6, True, "1"), "cottage_present": (False, None, 1),
                   "recipe_unlocked": (False, None, 1)}
        for field, values in invalid.items():
            for value in values:
                bad = self.facts(); bad[field] = value; before = copy.deepcopy(bad)
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    maple.workshop_preflight("2o74", **bad)
                self.assertEqual(bad, before)

    def test_workshop_never_accepts_craftshop_component_or_unknown_recipe(self):
        for code in ("2npba", "part_xcd_canadianrooftile", "b0", "2o9n", "", None, [], True):
            with self.subTest(code=code), self.assertRaises(ValueError):
                maple.workshop_recipe(code)

    def test_unsupported_or_deprecated_recipe_gate_stays_closed(self):
        import xml.etree.ElementTree as ET
        sources = maple._sources()
        for extra in ("<ComingSoon>1</ComingSoon>", "<prereqs><prereq type='unsupported'/></prereqs>", "<limitedEnd>08/24/2020</limitedEnd>"):
            changed = copy.deepcopy(sources[1]); changed["2o74"].append(ET.fromstring(extra))
            with patch.object(maple, "_sources", return_value=(sources[0], changed, sources[2], sources[3])):
                with self.assertRaisesRegex(ValueError, "unsupported availability"):
                    maple.workshop_preflight("2o74", **self.facts())

    def test_lodge_has_initial_level_one_thirty_upgrades_and_exact_tokens(self):
        needs = (1, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 15, 19, 21, 22,
                 25, 27, 30, 35, 38, 43, 46, 50, 55, 60, 65, 75, 85, 90, 95)
        for level, need in enumerate(needs, 2):
            with self.subTest(level=level):
                row = maple.upgrade_requirements("2nnz", level)
                self.assertEqual(row["initialExpansionLevel"], "1")
                self.assertIsNone(row["itemRequirements"])
                self.assertEqual(row["rawStage"]["part"], {"name": "hb_part_xcd_mapletoken", "need": str(need)})
                self.assertEqual(row["declaredMatsNeeded"], need)
                self.assertTrue(row["declaredMatchesStageParts"])
        self.assertEqual(maple.upgrade_requirements("2nnz", 31)["rawStage"]["award"]["name"], "pkg_summerwoodlodge_finish")

    def test_observatory_preserves_original_inconsistent_totals(self):
        # Read the independently specified original stage rows, not a synthesized
        # cumulative progression or an adjusted declared material total.
        rows = [maple.upgrade_requirements("2nj7", level) for level in range(2, 11)]
        self.assertEqual(rows[0]["declaredMatsNeeded"], 9)
        self.assertEqual(rows[1]["declaredMatsNeeded"], 23)
        self.assertEqual(rows[1]["stagePartTotal"], 14)
        self.assertFalse(rows[1]["declaredMatchesStageParts"])
        self.assertEqual(rows[-1]["stagePartTotal"], 94)
        self.assertEqual(rows[-1]["rawStage"]["rewardItem"], "moose_xcd_summerfarm")
        self.assertEqual(rows[0]["itemRequirements"]["requirement"], {"name": "canada", "className": "World"})

    def test_upgrade_unknown_identity_invalid_level_and_copies(self):
        for code, level in (("bldg_xcd_harvestbuildable", 2), ("2nnz", 1), ("2nnz", 32),
                            ("2nj7", 11), ("2nnz", True), ("2nj7", "2"), ([], 2)):
            with self.subTest(code=code, level=level), self.assertRaises(ValueError):
                maple.upgrade_requirements(code, level)
        row = maple.upgrade_requirements("2nnz", 2); row["rawStage"]["part"]["need"] = "0"
        self.assertEqual(maple.upgrade_requirements("2nnz", 2)["rawStage"]["part"]["need"], "1")

    def test_innovation_historical_end_closes_event_but_not_harvest_gate(self):
        facts = {"world": "canada", "player_level": 5, "server_time": datetime(2026, 10, 23)}
        before = copy.deepcopy(facts)
        self.assertFalse(maple.prerequisite_status("CanadaInnovation_innovation_enabled", facts)["met"])
        self.assertTrue(maple.prerequisite_status("CanadaInnovation_harvest_enabled", facts)["met"])
        facts["server_time"] = datetime(2020, 7, 20)
        self.assertTrue(maple.prerequisite_status("CanadaInnovation_innovation_enabled", facts)["met"])
        facts["server_time"] = datetime(2020, 8, 24)
        self.assertTrue(maple.prerequisite_status("CanadaInnovation_innovation_enabled", facts)["met"])
        facts["server_time"] = datetime(2020, 8, 24, 0, 0, 0, 1)
        self.assertFalse(maple.prerequisite_status("CanadaInnovation_innovation_enabled", facts)["met"])
        self.assertEqual(before["player_level"], facts["player_level"])

    def test_eos_is_separate_from_experiment_and_missing_facts_close(self):
        facts = {"world": "canada", "experiments": {"fv_xcd_beat": 2}}
        self.assertFalse(maple.prerequisite_status("beatcanadaExpansion", facts)["met"])
        facts["eos"] = {"fv_xcd_beat": 2}
        self.assertTrue(maple.prerequisite_status("beatcanadaExpansion", facts)["met"])
        for now in (None, "2026-10-23", datetime(2026, 10, 23, tzinfo=timezone.utc)):
            self.assertFalse(maple.prerequisite_status("CanadaInnovation_harvest_enabled", {"player_level": 5, "server_time": now})["met"])

    def test_unknown_leaf_never_passes(self):
        # Treasure feature_option leaf is intentionally outside bounded facts.
        row = maple.prerequisite_status("xcd_canadianplumtree_itemunlock", {})
        self.assertEqual((row["met"], row["supported"]), (False, False))
        for name in ("missing", None, []):
            with self.assertRaises(ValueError): maple.prerequisite(name)

    def test_unknown_comparison_or_quantity_metadata_never_weakens_gate(self):
        import xml.etree.ElementTree as ET
        sources = maple._sources()
        for attributes, facts in [
                ({"type": "start_time", "value": "07/20/2020", "op": "gt"},
                 {"server_time": datetime(2020, 7, 20)}),
                ({"type": "has_item", "value": "2nnz", "quantity": "2"},
                 {"owned_codes": ["2nnz"]})]:
            changed = dict(sources[2]); changed["test_gate"] = ET.Element("prereq", attributes)
            with patch.object(maple, "_sources", return_value=(sources[0], sources[1], changed, sources[3])):
                row = maple.prerequisite_status("test_gate", facts)
                self.assertEqual((row["met"], row["supported"]), (False, False))

    def test_section_requires_quest_not_score_or_date_alone(self):
        facts = {"world": "canada", "server_time": datetime(2026, 10, 23), "player_level": 100,
                 "completed_quests": [], "world_score_level": 999}
        self.assertFalse(maple.prerequisite_status("canada_Treasure2_Prereq", facts)["met"])
        facts["completed_quests"] = ["xcd_rubbletreasure2-01-001"]
        self.assertTrue(maple.prerequisite_status("canada_Treasure2_Prereq", facts)["met"])
        facts["world"] = "farm"
        self.assertFalse(maple.prerequisite_status("canada_Treasure2_Prereq", facts)["met"])

    def test_all_thirty_sections_and_both_building_tasks_retained(self):
        codes = ["o1cr", "eq0b", "nv70", "xxiw", "dsem", "lf53", "t9pb", "80f7", "vvmv",
                 "mxdz", "shf3", "amdj", "sa3h", "m6ym", "f331", "nohk", "vakf", "wq3g", "saog",
                 "50fc", "7qze", "yf9s", "f35k", "uukq", "dqis", "jooe", "cbfz", "o5en", "ywlj", "wxgh"]
        for code in codes:
            with self.subTest(code=code):
                row = maple.section_prerequisites(code)
                self.assertFalse(row["completionSupported"])
                self.assertTrue(row["locationTable"].endswith("_locations"))
        row = maple.section_prerequisites("eq0b")
        tasks = next(c for c in row["quest"]["children"] if c["tag"] == "tasks")["children"]
        self.assertEqual([c["attributes"] for c in tasks], [
            {"action": "expandStorageBuildingToLevelByCode", "type": "2nj7", "level": "2", "total": "1"},
            {"action": "expandStorageBuildingToLevelByCode", "type": "2nnz", "level": "6", "total": "1"},
            {"action": "reachWorldScoreLevel", "type": "canadaPoints", "level": "24", "total": "1"}])
        for code in ("2nnz", "unknown", None, []):
            with self.assertRaises(ValueError): maple.section_prerequisites(code)

    def test_owned_and_placed_facts_are_distinct_and_missing_is_closed(self):
        facts = {"owned_codes": ["o1cr"], "placed_codes": ["o1cr"]}
        self.assertTrue(maple.prerequisite_status("xcd_rubbletreasure1_placed", facts)["met"])
        self.assertFalse(maple.prerequisite_status("xcd_rubbletreasure1_unlocked", facts)["met"])
        self.assertFalse(maple.prerequisite_status("xcd_rubbletreasure1_unlocked", {})["met"])
        facts["placed_codes"] = []
        self.assertTrue(maple.prerequisite_status("xcd_rubbletreasure1_unlocked", facts)["met"])


if __name__ == "__main__":
    unittest.main()
