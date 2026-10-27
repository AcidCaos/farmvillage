"""The existing prepared client already carries the England Pub UI contract.

Pin recovered catalog facts and execute the emitted upgrade predicate. No new
SWF patch is needed for W02; browser acceptance is recorded separately.
"""
import copy
from datetime import date
import hashlib
from pathlib import Path
import sys
import struct
import unittest
import xml.etree.ElementTree as ET
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence  # Select private writable paths before bundle imports.
from test_turbo_client_refusal import PATCH, ROOT, read_abcs
import test_rainforest_cottage_client_upgrades as upgrade_tests
import meadows_client
import client_catalog
import client_england
import crafting
import england_progression
import items
import pyamf


def decode(raw):
    return pyamf.get_decoder(pyamf.AMF3, zlib.decompress(raw)).readElement()


class EnglandPubCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = Path(items.ITEMS_AMF).read_bytes()
        source = decode(cls.raw)["settings"]["items"]["item"]
        cls.pub = next(row for row in source if row["name"] == "xukcraftingpub")

    def test_recovered_pub_identity_tiers_gate_and_world_requirements(self):
        pub = self.pub
        self.assertEqual((pub["code"], pub["className"], pub["craftType"], pub["limit"]),
                         ("jm", "CraftingCottageBuilding", "pub", "1"))
        self.assertEqual((pub["buyable"], pub["unlock"], pub["experimentGate"]),
                         ("true", "instance_tiered", "fv_britishinvasion"))
        self.assertEqual([(t["id"], t["cost"], t["market"], t["levelRequired"], t["buyXp"])
                         for t in pub["tiers"]["tier"]],
                         [("1", "1000", "coins", "20", "1000"),
                          ("2", "10000", "coins", "20", "1000"),
                          ("3", "100000", "coins", "20", "1000")])
        self.assertEqual(pub["requirements"], {"compare": "any", "requirement": [
            {"name": "england", "className": "World"},
            {"name": "england", "className": "WorldLicense"}]})
        page = (ROOT / "templates/play.html").read_text()
        self.assertIn('"fv_britishinvasion": 1', page)

    def test_served_catalog_preserves_pub_definition_and_recovered_source_bytes(self):
        before = copy.deepcopy(self.pub)
        served = client_catalog._generate(self.raw, date(2026, 10, 24))
        pub = next(row for row in decode(served)["settings"]["items"]["item"]
                   if row["name"] == "xukcraftingpub")
        self.assertEqual(pub, before)
        self.assertEqual(Path(items.ITEMS_AMF).read_bytes(), self.raw)
        self.assertEqual(self.pub, before)

    def test_campaign_remains_disabled_and_does_not_add_quest_or_map_payload(self):
        self.assertFalse(england_progression.STORY_ENABLED)
        raw = client_england.QUEST_SOURCE.read_bytes()
        self.assertEqual(client_england.quest_payload(), raw)
        self.assertEqual(client_england.cms_payload(), client_england.CMS_SOURCE.read_bytes())
        names = {q.get("name") for q in ET.fromstring(zlib.decompress(raw)).findall("quest")}
        self.assertFalse(names & set(england_progression.QUEST_NAMES))
        self.assertNotIn(england_progression.MAP_WRAPPER_NAME, names)


class EnglandPubPreparedClientTests(unittest.TestCase):
    predicate = upgrade_tests.RainforestCottageClientUpgradeTests.predicate
    execute_frame = upgrade_tests.RainforestCottageClientUpgradeTests.execute_frame

    @classmethod
    def setUpClass(cls):
        cls.original = (ROOT / "embeds/Flash/v855097-855094/FarmGame.swf").read_bytes()
        cls.prepared = meadows_client.patch_client_bytes(PATCH.patch_client_bytes(cls.original))
        cls.abc = read_abcs(zlib.decompress(cls.prepared[8:]))[0]
        historical_body = zlib.decompress(cls.original[8:])
        for edits in (PATCH.EDITS, PATCH.MARKET_EDITS, PATCH.TAB_EDITS,
                PATCH.SCRATCH_EDITS, PATCH.EMPTY_WORLD_EDITS, PATCH.COTTAGE_EDITS,
                PATCH.COTTAGE_UPGRADE_EDITS, PATCH.TURBO_EDITS, PATCH.STORAGE_EDITS,
                PATCH.INVITATION_EDITS, PATCH.VIP_EDITS, PATCH.MARKET_WALKTHROUGH_EDITS,
                PATCH.QUEST_CLOSE_EDITS, PATCH.IMAGE_ROW_EDITS, PATCH.INVENTORY_ART_EDITS,
                PATCH.MARKETSTALL_EXPANSION_EDITS, PATCH.WIDGET_STORAGE_EDITS,
                PATCH.REGIONAL_UPGRADE_EDITS, PATCH.OPTIONAL_BACKGROUND_EDITS):
            historical_body = PATCH._apply_edits(historical_body, edits)
        cls.historical = (cls.original[:4] + struct.pack("<I", len(historical_body) + 8)
                          + zlib.compress(historical_body, 9))
        cls.historical_abc = read_abcs(historical_body)[0]

    def test_complete_interim_artifact_keeps_the_existing_england_pub_contract(self):
        self.assertEqual(hashlib.sha256(self.prepared).hexdigest(),
                         "cbed503844c54623a3ed7a2ae956724eaa806bc9d1ab3e09895fe60503996dc4")
        self.assertEqual(hashlib.sha256(zlib.decompress(self.prepared[8:])).hexdigest(),
                         "8f34e1533a4949e411bf75706e3010b74a3e805f1d7f02f10bc799295baa4066")
        self.assertEqual(meadows_client.patch_client_bytes(self.prepared), self.prepared)

    def test_historical_prepared_stage_remains_pinned_and_upgrades_without_changing_pub(self):
        self.assertEqual(hashlib.sha256(self.historical).hexdigest(),
                         "b5a8949100498151eeeadb561ad01c7a87778c2c4db6f8b2cdc129f642dd29d3")
        self.assertEqual(hashlib.sha256(zlib.decompress(self.historical[8:])).hexdigest(),
                         "2200ebcdc58dfa2061ffaf20e58f8c83b1868449a6b8bae8f81395c27a0454c6")
        self.assertEqual(meadows_client.patch_client_bytes(PATCH.patch_client_bytes(self.historical)), self.prepared)
        for craft in ("bakery", "winery", "perfumery", "pub", "xhdcrafttype"):
            self.assertTrue(self.predicate(self.historical_abc, craft))
            self.assertTrue(self.predicate(self.abc, craft))

    def test_actual_pub_upgrade_predicate_preserves_coin_cash_cap_and_prereq_paths(self):
        self.assertTrue(self.predicate(self.abc, "pub"))
        for value in ("Pub", "pub ", "xukcraftingpub", "england", "Xrfcrafttype", None):
            self.assertFalse(self.predicate(self.abc, value))
        code = self.abc.bodies[34693]
        for remaining, cap, prereq in ((6, False, False), (0, False, False),
                                       (0, True, False), (0, False, True)):
            frame, _ = self.execute_frame(code, remaining, max_level=cap,
                                          prereq=prereq, supported=True)
            self.assertEqual(frame["coin"]["visible"], not cap and remaining <= 0)
            self.assertEqual(frame["cash"]["visible"], not cap and remaining > 0)


if __name__ == "__main__":
    unittest.main()
