"""Derived England client contracts without archive, server or save mutation."""
import copy
from pathlib import Path
import sys
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence  # Resolve temporary writable paths first.
import pyamf
import client_england
import england_progression
import quests


def decode_amf(raw):
    return pyamf.get_decoder(pyamf.AMF3, zlib.decompress(raw)).readElement()


class EnglandClientPayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        enabled = mock.patch.object(england_progression, "STORY_ENABLED", True)
        enabled.start()
        cls.addClassCleanup(enabled.stop)
        cls.quest_source = client_england.QUEST_SOURCE.read_bytes()
        cls.quest_result = client_england.quest_payload(cls.quest_source)
        cls.source_root = ET.fromstring(zlib.decompress(cls.quest_source))
        cls.result_root = ET.fromstring(zlib.decompress(cls.quest_result))

    def test_original_catalog_survives_and_each_story_quest_matches_the_server(self):
        originals = {q.get("name"): q for q in self.source_root.findall("quest")}
        derived = {q.get("name"): q for q in self.result_root.findall("quest")}
        self.assertEqual(set(derived) - set(originals),
                         set(england_progression.QUEST_NAMES) | {client_england.MAP_WRAPPER_NAME})
        for name, original in originals.items():
            self.assertEqual(ET.tostring(derived[name]), ET.tostring(original), name)
        decoded = quests._decode_quests(self.quest_result)["quests"]
        for name, canonical in england_progression.quest_definitions().items():
            for field in ("memStoreId", "category", "priority", "prereqs", "tasks", "rewards", "children"):
                self.assertEqual(decoded[name][field], canonical[field], f"{name}.{field}")
            self.assertEqual(derived[name].findtext("frontend/textBundle"), name)

    def test_selected_quests_have_usable_icons_and_all_paid_skips_and_retirement_disabled(self):
        for node in self.result_root.findall("quest"):
            if node.get("name") not in england_progression.QUEST_NAMES:
                continue
            self.assertEqual(node.get("skip"), "false")
            self.assertEqual(node.get("kill"), "false")
            self.assertEqual(node.get("replay"), "false")
            self.assertTrue(node.findtext("frontend/icon").startswith("assets/"))
            self.assertEqual(node.findtext("frontend/avatarHeadImage"), client_england.HEAD_IMAGE)
            self.assertTrue(all(task.get("cashValue") == "0" for task in node.findall("tasks/task")))
        self.assertEqual(client_england.QUEST_SOURCE.read_bytes(), self.quest_source)

    def test_map_wrapper_only_presents_original_ui_and_has_no_story_or_reward_effect(self):
        wrapper = next(q for q in self.result_root.findall("quest")
                       if q.get("name") == client_england.MAP_WRAPPER_NAME)
        self.assertEqual(wrapper.findtext("frontend/icon"), "none")
        self.assertEqual(wrapper.findtext("frontend/rewardView"), "questMap")
        self.assertEqual(wrapper.get("ignoreSlotLimit"), "true")
        self.assertEqual([t.get("action") for t in wrapper.findall("tasks/task")], ["viewDialog"])
        self.assertEqual(wrapper.findall("rewards/reward"), [])
        self.assertEqual(wrapper.findall("children/child"), [])
        self.assertNotIn(client_england.MAP_WRAPPER_NAME, england_progression.quest_definitions())
        self.assertEqual(client_england.MAP_WRAPPER_NAME, england_progression.MAP_WRAPPER_NAME)

    def test_overlay_is_idempotent_and_keeps_original_task_dispatch(self):
        self.assertEqual(client_england.quest_payload(self.quest_result), self.quest_result)
        self.assertEqual(ET.tostring(self.result_root.find("taskTypes")),
                         ET.tostring(self.source_root.find("taskTypes")))
        self.assertEqual(ET.tostring(self.result_root.find("categories")),
                         ET.tostring(self.source_root.find("categories")))

    def test_selected_frontend_art_is_in_the_original_asset_index(self):
        root = Path(__file__).resolve().parents[2]
        index = decode_amf((root / "assethash/v9/assethash.master.amf.gz").read_bytes())
        for logical in (client_england.HEAD_IMAGE, client_england.BODY_IMAGE,
                        client_england.PEN_ICON, client_england.POSTCARD_ICON,
                        client_england.COMBINE_ICON, client_england.MAP_ASSET):
            _, category, path = logical.split("/", 2)
            self.assertTrue(index.get(category, {}).get(path), logical)


class EnglandConstructionPayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = client_england.STORAGE_SOURCE.read_bytes()
        cls.source = decode_amf(cls.raw)
        cls.result = decode_amf(client_england.storage_payload(cls.raw))

    def test_only_initial_sheep_pen_material_counts_change_in_the_client_copy(self):
        expected = copy.deepcopy(self.source)
        found = set()
        for record in expected["storage"]["StorageBuilding"]:
            if record.get("name") not in ("xuk_sheep_pen_construct", "xuk_sheep_pen"):
                continue
            found.add(record["name"])
            for row in record["itemName"]:
                if row.get("part") == "true" and row.get("value") in england_progression.SHEEP_PEN_INITIAL_MATERIALS:
                    row["need"] = str(england_progression.SHEEP_PEN_INITIAL_MATERIALS[row["value"]])
        self.assertEqual(len(found), 2)
        self.assertEqual(self.result, expected)
        self.assertEqual(client_england.STORAGE_SOURCE.read_bytes(), self.raw)

    def test_missing_material_filter_rejects_instead_of_shipping_a_partial_contract(self):
        malformed = copy.deepcopy(self.source)
        records = malformed["storage"]["StorageBuilding"]
        record = next(r for r in records if r.get("name") == "xuk_sheep_pen_construct")
        record["itemName"].pop()
        raw = zlib.compress(pyamf.encode(malformed, encoding=pyamf.AMF3).getvalue())
        with self.assertRaisesRegex(ValueError, "incomplete"):
            client_england.storage_payload(raw)

    def test_map_location_setting_keeps_the_rest_of_the_cms_catalog(self):
        raw = client_england.CMS_SOURCE.read_bytes()
        expected = ET.fromstring(zlib.decompress(raw))
        with mock.patch.object(england_progression, "STORY_ENABLED", True):
            derived = ET.fromstring(zlib.decompress(client_england.cms_payload(raw)))
        farming = expected.find("farming")
        matches = [n for n in farming.findall("farmingEntry")
                   if n.get("key") == "england_questMap_maxLocation"]
        entry = matches[0] if matches else ET.SubElement(farming, "farmingEntry", {
            "key": "england_questMap_maxLocation"})
        entry.set("value", "1")
        self.assertEqual(ET.tostring(derived), ET.tostring(expected))
        self.assertEqual(client_england.CMS_SOURCE.read_bytes(), raw)


class DisabledEnglandStoryTests(unittest.TestCase):
    def test_story_is_disabled_and_both_client_story_sources_remain_exact_archives(self):
        self.assertFalse(england_progression.STORY_ENABLED)
        for source, payload in ((client_england.QUEST_SOURCE, client_england.quest_payload),
                                (client_england.CMS_SOURCE, client_england.cms_payload)):
            raw = source.read_bytes()
            self.assertEqual(payload(raw), raw)
            self.assertEqual(payload(source), raw)

    def test_loading_archive_does_not_activate_story_definitions(self):
        cached = {"quests": {}, "replayableChains": {}, "maxActiveReplayableQuests": 0, "itemCategories": {}}
        with mock.patch.object(quests, "_load_quests_cache", return_value=cached), \
                mock.patch.object(quests, "_cached_quests"), \
                mock.patch.object(quests, "_replayable_chains"), \
                mock.patch.object(quests, "_max_active_replayable_quests"), \
                mock.patch.object(quests, "_item_categories"), \
                mock.patch.object(quests, "_startable_quests"):
            quests.load_quests()
            self.assertEqual(quests.get_quests(), {})
            self.assertIsNone(quests.get_quest_by_name(england_progression.MAP_WRAPPER_NAME))


if __name__ == "__main__":
    unittest.main()
