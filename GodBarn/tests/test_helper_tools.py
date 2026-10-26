"""Recovered helpers only alter selected detached counters or task progress."""

import copy
import importlib.util
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from engine import CheatEngine, MAX_BALANCE
from helper_tools import COLLECTION_LABELS, collection_display_name
from test_engine import CATALOG, RULES, NOW, farm


ROOT = Path(__file__).resolve().parents[1]
DEFINITIONS = {
    "collections": [
        {"name": "grains", "code": "C001", "type": "permanent", "displayName": "Grains Collection",
         "items": [{"code": "SB", "rarity": "common"}, {"code": "EP", "rarity": "uncommon"},
                   {"code": "CW", "rarity": "rare"}]},
        {"name": "berries", "code": "C001", "type": "permanent", "displayName": "Berries Collection",
         "items": [{"code": "HB", "rarity": "common", "numneeded": 7}]},
        {"name": "holiday", "code": "LE01", "type": "LE", "displayName": "Holiday Collection",
         "items": [{"code": "SB", "numneeded": 7}, {"code": "CW", "numneeded": 9}]},
        {"name": "lucky", "code": "C020", "type": "slotmachine", "items": [{"code": "EP", "rarity": "common"}]},
        {"name": "turtles", "type": "breeding", "items": [{"tint": "maroon"}]},
        {"name": "fish", "type": "fishing", "items": [{"name": "carp"}]},
    ],
    "quests": [
        {"name": "quest_one", "displayName": "One for the farm", "description": "A recovered quest.",
         "tasks": [{"action": "harvestByCode", "type": "SB", "total": 8, "displayName": "Harvest 8 Strawberries"},
                   {"action": "viewDialog", "total": 1}]},
        {"name": "quest_two", "tasks": [{"action": "getMasteryLevelByCode", "type": "SB", "level": 3, "total": 1}]},
    ], "source": {"test": "recovered fixture"},
}


def helper_farm():
    save = farm()
    save["userInfo"]["player"].update(collectionCounters={"SB": 1, "CW": 9, "unknown": 23},
                                      collectionLevels={"grains": 1},
                                      storedCollections={"future": {"keep": True}})
    save["questState"] = {"active": {"quest_one": {"progress": [3, 0], "new": 1, "future": [2]},
                                    "quest_two": {"progress": [0], "new": 0}},
                          "completed": ["previous"], "retired": ["retired"],
                          "replayed": {"chain": {"count": 2, "lastCompleted": 45}}}
    return save


class HelperToolsTests(unittest.TestCase):
    def setUp(self):
        self.engine = CheatEngine(CATALOG, RULES, helpers=DEFINITIONS)
        self.save = helper_farm()

    def page(self, **query):
        return self.engine.helpers_page(self.save, **query)

    def row(self, kind, name):
        return next(row for row in self.page(kind=kind, limit=100, include_unsupported=True)["items"] if row["name"] == name)

    def fill(self, name="grains", save=None):
        return self.engine.apply(self.save if save is None else save,
                                 {"type": "collection", "name": name, "action": "fill"}, NOW)

    def finish(self, task=0, name="quest_one", save=None):
        return self.engine.apply(self.save if save is None else save,
                                 {"type": "quest", "name": name, "task": task}, NOW)

    def test_permanent_requirements_follow_rarity_and_named_level_without_config_cap(self):
        row = self.row("collection", "grains")
        self.assertEqual([item["required"] for item in row["items"]], [6, 4, 2])
        self.assertEqual([item["missing"] for item in row["items"]], [5, 4, 0])
        self.save["userInfo"]["player"]["collectionLevels"]["grains"] = 4
        self.assertEqual(self.row("collection", "grains")["items"][0]["required"], 15)
        # Historical grains/berries share a collection code, but the level is
        # keyed by collection name and explicit numneeded overrides rarity.
        self.assertEqual(self.row("collection", "berries")["items"][0]["required"], 7)

    def test_fill_tops_up_only_missing_counters_and_preserves_reward_ledgers(self):
        before = copy.deepcopy(self.save)
        result = self.fill()
        self.assertEqual(self.save, before)
        after = result["save"]["userInfo"]["player"]
        self.assertEqual(after["collectionCounters"], {"SB": 6, "EP": 4, "CW": 9, "unknown": 23})
        expected = copy.deepcopy(before)
        expected["userInfo"]["player"]["collectionCounters"] = after["collectionCounters"]
        self.assertEqual(result["save"], expected)
        self.assertEqual({row["path"] for row in result["changes"]},
                         {"/userInfo/player/collectionCounters/SB", "/userInfo/player/collectionCounters/EP"})
        self.assertEqual(self.fill(save=result["save"])["changes"], [])

    def test_limited_and_slotmachine_use_positive_membership(self):
        row = self.row("collection", "holiday")
        self.assertEqual([item["required"] for item in row["items"]], [1, 1])
        self.assertTrue(row["completed"])
        self.assertEqual(self.fill("holiday")["changes"], [])
        result = self.fill("lucky")
        self.assertEqual(result["save"]["userInfo"]["player"]["collectionCounters"]["EP"], 1)

    def test_nonpermanent_claimed_marker_uses_presence_even_for_false_or_zero(self):
        for value in (False, 0, None, {}):
            with self.subTest(value=value):
                self.save["userInfo"]["player"]["storedCollections"]["LE01"] = value
                row = self.row("collection", "holiday")
                self.assertTrue(row["claimed"])
                self.assertTrue(row["completed"])
                self.assertFalse(row["supported"])
                with self.assertRaisesRegex(ValueError, "already recorded"):
                    self.fill("holiday")
        self.save["userInfo"]["player"]["storedCollections"]["C001"] = True
        self.assertTrue(self.row("collection", "grains")["supported"])

    def test_null_or_absent_collection_fields_create_only_counters(self):
        player = self.save["userInfo"]["player"]
        for key in ("collectionCounters", "collectionLevels", "storedCollections"):
            player[key] = None
        result = self.fill()["save"]["userInfo"]["player"]
        self.assertEqual(result["collectionCounters"], {"SB": 3, "EP": 2, "CW": 1})
        self.assertIsNone(result["collectionLevels"])
        self.assertIsNone(result["storedCollections"])

    def test_unknown_and_feature_collections_cannot_change_save(self):
        before = copy.deepcopy(self.save)
        for name in ("unknown", "fish", "turtles"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.fill(name)
        self.assertEqual(self.save, before)
        self.assertFalse(self.row("collection", "fish")["supported"])

    def test_malformed_collection_state_is_read_only_without_normalization(self):
        for key, value in (("collectionCounters", []), ("collectionCounters", {"SB": "3"}),
                           ("collectionCounters", {"SB": True}), ("collectionCounters", {"SB": -1}),
                           ("collectionCounters", {"SB": MAX_BALANCE + 1}),
                           ("collectionLevels", []), ("collectionLevels", {"grains": -1})):
            with self.subTest(key=key, value=value):
                self.save = helper_farm()
                self.save["userInfo"]["player"][key] = value
                before = copy.deepcopy(self.save)
                self.assertFalse(self.row("collection", "grains")["supported"])
                with self.assertRaises(ValueError): self.fill()
                self.assertEqual(self.save, before)

    def test_task_completion_uses_exact_index_and_keeps_active_rewards_and_other_quests(self):
        before = copy.deepcopy(self.save)
        result = self.finish()
        expected = copy.deepcopy(before)
        expected["questState"]["active"]["quest_one"]["progress"][0] = 8
        self.assertEqual(result["save"], expected)
        self.assertEqual(self.save, before)
        self.assertEqual(result["changes"], [{"path": "/questState/active/quest_one/progress/0", "before": 3, "after": 8}])
        self.assertTrue(any("no quest rewards" in warning for warning in result["warnings"]))
        self.assertEqual(self.finish(save=result["save"])["changes"], [])
        completed = self.finish(1, save=result["save"])["save"]
        self.assertIn("quest_one", completed["questState"]["active"])
        self.assertNotIn("quest_one", completed["questState"]["completed"])
        row = self.engine.helpers_page(completed, kind="quest", status="complete")["items"][0]
        self.assertEqual(row["status"], "active")
        self.assertIn("claim", row["reason"])

    def test_already_overcomplete_quest_counter_is_preserved(self):
        self.save["questState"]["active"]["quest_one"]["progress"][0] = 99
        self.assertEqual(self.finish()["changes"], [])

    def test_invalid_indexes_and_inactive_or_unknown_quests_are_rejected(self):
        for task in (-1, True, 0.5, "0", None, 2, float("nan"), float("inf")):
            with self.subTest(task=task), self.assertRaises(ValueError): self.finish(task)
        for name in ("previous", "retired", "unknown"):
            with self.subTest(name=name), self.assertRaises(ValueError): self.finish(name=name)
        self.save["questState"]["active"]["unknown"] = {"progress": [3], "new": 1, "future": 9}
        self.assertFalse(self.row("quest", "unknown")["supported"])
        with self.assertRaisesRegex(ValueError, "no recovered definition"): self.finish(name="unknown")

    def test_malformed_quest_progress_never_gets_padded_or_erased(self):
        for state in (None, {}, {"progress": []}, {"progress": [1]}, {"progress": [1, 2, 3]},
                      {"progress": [-1, 0]}, {"progress": ["1", 0]}, {"progress": [False, 0]}):
            with self.subTest(state=state):
                self.save = helper_farm()
                self.save["questState"]["active"]["quest_one"] = state
                before = copy.deepcopy(self.save)
                self.assertFalse(self.row("quest", "quest_one")["supported"])
                with self.assertRaises(ValueError): self.finish()
                self.assertEqual(self.save, before)

    def test_save_derived_mastery_counts_as_complete_without_writing_during_inspection(self):
        self.save["userInfo"]["player"]["mastery"] = {"SB": 2}
        before = copy.deepcopy(self.save)
        self.assertTrue(self.row("quest", "quest_two")["completed"])
        self.assertEqual(self.finish(name="quest_two")["changes"], [])
        self.assertEqual(self.save, before)

    def test_search_status_paging_are_read_only_and_results_detached(self):
        before = copy.deepcopy(self.save)
        page = self.page(kind="quest", q="strawberries", limit=1, page=4)
        self.assertEqual((page["total"], page["page"], page["pages"]), (1, 1, 1))
        self.assertEqual(page["totals"]["quests"], 2)
        page["items"][0]["tasks"][0]["count"] = 999
        page["source"]["test"] = "changed"
        self.assertEqual(self.row("quest", "quest_one")["tasks"][0]["count"], 3)
        self.assertEqual(self.page()["source"], DEFINITIONS["source"])
        self.assertEqual(self.save, before)
        self.assertEqual(self.page(kind="collection", status="complete")["total"], 1)

    def test_need_counts_exclude_read_only_and_claimed_sets(self):
        self.save["userInfo"]["player"]["storedCollections"]["LE01"] = True
        totals = self.page(kind="collection", include_unsupported=True)["totals"]
        self.assertEqual(totals["supportedIncomplete"], 3)
        self.assertEqual(totals["readonlyIncomplete"], 2)
        self.assertEqual(totals["unsupported"], 3)
        self.assertEqual(totals["complete"], 1)
        self.assertEqual(totals["incomplete"], 5)
        # These totals describe the selected kind before search/status filters.
        self.assertEqual(self.page(kind="collection", q="grains", status="incomplete", include_unsupported=True)["totals"], totals)

    def test_unlocalized_task_labels_never_expose_unknown_identifiers_and_preserve_fields(self):
        definitions = copy.deepcopy(DEFINITIONS)
        definitions["quests"][0]["tasks"] = [
            {"action": "viewSeenFlag", "type": "hollybrightpark_Tutorial", "total": 1},
            {"action": "viewseenflag", "type": "farm_Clubs", "total": 1},
            {"action": "inspectFarmInventory", "type": "goldenTree_collection", "total": 2},
        ]
        engine = CheatEngine(CATALOG, RULES, helpers=definitions)
        self.save["questState"]["active"]["quest_one"]["progress"] = [0, 0, 0]
        row = next(row for row in engine.helpers_page(self.save, kind="quest")["items"] if row["name"] == "quest_one")
        self.assertEqual([task["displayName"] for task in row["tasks"]],
                         ["View the quest dialog", "View the quest dialog", "Complete this quest task"])
        self.assertEqual(row["tasks"][0]["action"], "viewSeenFlag")
        self.assertEqual(row["tasks"][0]["type"], "hollybrightpark_Tutorial")

    def test_hidden_trackers_and_unsupported_collection_types_do_not_clutter_pages(self):
        self.engine.helpers.quests["quest_two"]["icon"] = "none"
        before = copy.deepcopy(self.save)
        page = self.page()
        self.assertEqual(page["totals"]["hiddenQuests"], 1)
        self.assertEqual(page["totals"]["hiddenCollections"], 2)
        self.assertEqual(page["counts"], {"collection": 4, "quest": 1})
        self.assertNotIn("quest_two", {row["name"] for row in page["items"]})
        self.assertNotIn("fish", {row["name"] for row in page["items"]})
        self.assertEqual(self.page(kind="quest", include_background=True)["total"], 2)
        self.assertEqual(self.save, before)
        # The original quest is still addressable by its real active name.
        self.assertEqual(self.finish(name="quest_two")["save"]["questState"]["active"]["quest_two"]["progress"], [1])

    def test_named_story_introductions_with_no_hud_icon_remain_visible(self):
        definition = self.engine.helpers.quests["quest_one"]
        definition.update(icon="none", hasLocalizedTitle=True, category="story", ignoreSlotLimit=False,
                          image="/static/assets/helper-art/portrait.png")
        page = self.page(kind="quest")
        self.assertIn("quest_one", {row["name"] for row in page["items"]})
        self.assertEqual(self.row("quest", "quest_one")["image"], "/static/assets/helper-art/portrait.png")
        # A deliberately invisible tracker is hidden even if a shared title
        # happens to be available in its frontend text bundle.
        definition.update(ignoreSlotLimit=True, rewardView="none")
        self.assertNotIn("quest_one", {row["name"] for row in self.page(kind="quest")["items"]})

    def test_exact_artwork_passes_through_to_collection_and_quest_rows(self):
        self.engine.helpers.collections["grains"]["image"] = "/static/assets/helper-art/grains.png"
        self.engine.helpers.quests["quest_one"]["image"] = "/static/assets/helper-art/quest.png"
        self.assertEqual(self.row("collection", "grains")["image"], "/static/assets/helper-art/grains.png")
        self.assertEqual(self.row("quest", "quest_one")["image"], "/static/assets/helper-art/quest.png")

    def test_limited_set_labels_are_distinct_and_never_show_machine_names(self):
        self.assertEqual(len(COLLECTION_LABELS), 19)
        self.assertEqual(len(set(COLLECTION_LABELS.values())), 19)
        for name, expected in COLLECTION_LABELS.items():
            self.assertEqual(collection_display_name(name, "Collection"), expected)
            definition = {"name": name, "displayName": "Collection", "type": "LE", "items": [{"code": "SB"}]}
            row = self.engine.helpers._collection_row(self.save, definition)
            self.assertEqual(row["displayName"], expected)
            self.assertNotIn("leset", row["displayName"])
            self.assertNotIn("_", row["displayName"])
        self.assertEqual(collection_display_name("leset_vineyard_collection", "Original localized title"), "Original localized title")

    def test_invalid_query_and_unexpected_operation_fields_reject(self):
        for query in ({"kind": "inventory"}, {"status": "started"}, {"q": False}, {"q": "a" * 201},
                      {"page": 0}, {"limit": 101}, {"limit": True}):
            with self.subTest(query=query), self.assertRaises(ValueError): self.page(**query)
        for op in ({"type": "collection", "name": "grains", "action": "claim"},
                   {"type": "collection", "name": "grains", "action": "fill", "quantity": 9},
                   {"type": "quest", "name": "quest_one", "task": 0, "claim": True}):
            with self.subTest(op=op), self.assertRaises(ValueError): self.engine.apply(self.save, op, NOW)

    def test_missing_metadata_and_quest_state_is_empty_and_safe(self):
        engine = CheatEngine(CATALOG, RULES)
        self.assertFalse(engine.helpers_page(farm())["available"])
        self.assertEqual(engine.helpers_page(farm())["items"], [])
        self.save["questState"]["active"] = []
        self.assertIn("malformed", self.page(kind="quest")["reason"])


class HelperPreparationTests(unittest.TestCase):
    def preparation_module(self):
        spec = importlib.util.spec_from_file_location("helper_preparation", ROOT / "scripts/prepare_helpers.py")
        module = importlib.util.module_from_spec(spec)
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)
        return module

    def test_artwork_uses_only_declared_exact_rasters_and_keeps_provenance(self):
        from test_catalog_recovery import png
        module = self.preparation_module()
        with tempfile.TemporaryDirectory() as folder:
            source, root = Path(folder) / "original", Path(folder) / "barn"
            root.mkdir()
            payload = png((50, 100, 150, 255))
            digest = hashlib.md5(payload).hexdigest()
            original = source / "LocalData/assets/newsfeed" / (digest + ".png")
            original.parent.mkdir(parents=True)
            original.write_bytes(payload)
            metadata = {"source": {}, "collections": [], "quests": [
                {"name": "test", "imageCandidates": ["assets/newsfeed/missing.png", "assets/newsfeed/exact.png"]},
                {"name": "unknown", "imageCandidates": ["assets/newsfeed/similar.png"]}]}
            module.copy_artwork(source, metadata, root, manifests=[("master", {"newsfeed": {"exact.png": digest}})])
            row = metadata["quests"][0]
            self.assertEqual((root / row["image"].lstrip("/")).read_bytes(), payload)
            self.assertEqual(row["imageLogical"], "assets/newsfeed/exact.png")
            self.assertEqual(metadata["assets"][0]["sourceSha256"], hashlib.sha256(payload).hexdigest())
            self.assertEqual(metadata["assets"][0]["sourcePath"], original.relative_to(source).as_posix())
            self.assertIsNone(metadata["quests"][1]["image"])
            self.assertEqual(original.read_bytes(), payload)
            # A missing file selected by the delta manifest must not silently
            # fall back to a different master revision of the same logical URL.
            missing_hash = "a" * 32
            module.copy_artwork(source, metadata, root, manifests=[
                ("delta", {"newsfeed": {"exact.png": missing_hash}}),
                ("master", {"newsfeed": {"exact.png": digest}})])
            self.assertIsNone(metadata["quests"][0]["image"])

    def test_recovery_reads_archived_inputs_only_and_emits_original_labels(self):
        module = self.preparation_module()
        source = ROOT.parent / "FarmVillage"
        if not (source / "xml/gz/v855098/collections.xml.gz").is_file():
            self.skipTest("Original read-only metadata is unavailable.")
        touched = []
        original_read = Path.read_bytes
        def read(path):
            touched.append(path.relative_to(source).as_posix())
            return original_read(path)
        with patch.object(Path, "read_bytes", read):
            result = module.recover(source)
        self.assertEqual(set(touched), {"xml/gz/v855098/collections.xml.gz",
                                        "xml/gz/v855098/questSettings_0.xml.gz", "xml/gz/v855098/en_US.swf"})
        self.assertEqual((len(result["collections"]), len(result["quests"])), (81, 3233))
        grains = next(row for row in result["collections"] if row["name"] == "grains")
        self.assertEqual(grains["displayName"], "Grains Collection")
        limited = [row for row in result["collections"] if row["type"] == "LE"]
        self.assertEqual({row["displayName"] for row in limited}, set(COLLECTION_LABELS.values()))
        quest = next(row for row in result["quests"] if row["name"] == "Aam-01-001")
        self.assertEqual(quest["displayName"], "Endangered Species Day!: Part 1")
        self.assertEqual(quest["tasks"][2]["displayName"], "Craft 3 Seaweed Soaps")
        self.assertEqual(len(result["source"]["collectionsSha256"]), 64)


if __name__ == "__main__":
    unittest.main()
