"""Pure original-source checks for the October canvas HUD projection."""
import copy
import hashlib
from pathlib import Path
import sys
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence  # Establish disposable roots before product imports.
import october_presentation as presentation


# Audited ExportAssets/SymbolClass names from the SHA-pinned original England
# SWF, not names inferred from its XML (which has three nonexistent zcache names).
ORIGINAL_WOOD_SKIN_EXPORTS = frozenset("""
arrowLine_down_england arrowLine_normal_england arrowLine_over_england
doubleArrow_down_england doubleArrow_normal_england doubleArrow_over_england
friendBar_normal_england friendBar_over_england
singleArrow_down_england singleArrow_normal_england singleArrow_over_england
camera_down_england camera_normal_england camera_over_england
friendBar_chat_normal_england friendBar_chat_over_england
fullScreen_down_england fullScreen_over_england fullScreen_normal_england
music_down_england music_over_england music_normal_england
optionsBackground_england
sfx_down_england sfx_over_england sfx_normal_england
neighborBackground_england
graphics_down_england graphics_over_england graphics_normal_england
zcache_down_farm zcache_normal_farm zcache_over_farm
zoomIn_down_england zoomIn_over_england zoomIn_normal_england
zoomOut_down_england zoomOut_over_england zoomOut_normal_england
messageSign_down_england messageSign_normal_england messageSign_over_england
""".split())


def structure(node):
    """Ignore XML formatting; retain every tag, attribute, value and child order."""
    return (node.tag, dict(node.attrib), (node.text or "").strip(),
            tuple(structure(child) for child in node))


class OctoberPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (ROOT / presentation.WORLD_SETTINGS_SOURCE).read_bytes()

    def parsed(self, raw=None):
        return ET.fromstring(zlib.decompress(self.raw if raw is None else raw))

    def project_modified(self, root):
        raw = zlib.compress(ET.tostring(root, encoding="utf-8"))
        # Exercise the structural fences independently of the source hash pin.
        with mock.patch.object(presentation, "WORLD_SETTINGS_SHA256", hashlib.sha256(raw).hexdigest()):
            return presentation.world_settings_payload(raw, active=True)

    def test_inactive_response_is_the_exact_original_without_parsing(self):
        self.assertIs(presentation.world_settings_payload(self.raw), self.raw)
        self.assertEqual(presentation.world_settings_payload(b"opaque older source"), b"opaque older source")

    def test_original_source_and_borrowed_skin_contracts_are_pinned(self):
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), presentation.WORLD_SETTINGS_SHA256)
        self.assertEqual(presentation.HUD_DONOR_WORLD, "england")
        self.assertEqual(presentation.HUD_ASSET_PATH, "assets/hud/hudSkin_Eng.swf")
        self.assertEqual(presentation.HUD_ASSET_MANIFEST_HASH, "9d85543951222254223bd86b7263e603")
        self.assertEqual(presentation.HUD_ASSET_SHA256,
                         "51b8be340f66cdd2a3a7b8d5da43fcfc350c231e894a771ff7c1f58dd312bd22")

    def test_only_home_hud_assets_change_and_every_world_rule_stays_original(self):
        original = self.parsed()
        before = structure(original)
        projected = self.parsed(presentation.world_settings_payload(self.raw, active=True))
        home_path = "world[@name='farm']/hudSkinConfig"
        home = projected.find(home_path)
        replacement = home.find("hudAssets")
        self.assertEqual(replacement.attrib, {"path": presentation.HUD_ASSET_PATH})
        home.remove(replacement)
        original_home = original.find(home_path)
        old_skin = original_home.find("hudAssets")
        home.insert(list(original_home).index(old_skin), copy.deepcopy(old_skin))
        self.assertEqual(structure(projected), before)
        self.assertEqual(structure(original), before)
        self.assertEqual((ROOT / presentation.WORLD_SETTINGS_SOURCE).read_bytes(), self.raw)

    def test_donor_keeps_borders_and_uses_all_42_actual_original_skin_exports(self):
        original = self.parsed()
        donor = copy.deepcopy(original.find("world[@name='england']/hudSkinConfig/hudAssets"))
        for state in ("normal", "over", "down"):
            donor.find("zCacheButton/" + state).text = "zcache_" + state + "_farm"
        projected = self.parsed(presentation.world_settings_payload(self.raw, active=True))
        home_skin = projected.find("world[@name='farm']/hudSkinConfig/hudAssets")
        self.assertEqual(structure(home_skin), structure(donor))
        names = [node.text.strip() for node in home_skin.iter()
                 if not list(node) and node.text and node.text.strip()]
        self.assertEqual(len(names), 42)
        self.assertEqual(frozenset(names), ORIGINAL_WOOD_SKIN_EXPORTS)
        self.assertEqual(home_skin.findtext("friendBarSlotBackground/border"),
                         "friendBar_chat_normal_england")
        self.assertEqual(home_skin.findtext("friendBarSlotBackground/borderOver"),
                         "friendBar_chat_over_england")
        for state in ("normal", "over", "down"):
            self.assertEqual(home_skin.findtext("zCacheButton/" + state), "zcache_" + state + "_farm")
            self.assertNotIn("zcache_" + state + "_england", names)

    def test_output_is_deterministic_and_does_not_contaminate_inactive_responses(self):
        first = presentation.world_settings_payload(self.raw, active=True)
        self.assertEqual(first, presentation.world_settings_payload(self.raw, active=True))
        self.assertEqual(presentation.world_settings_payload(self.raw, active=False), self.raw)

    def test_changed_or_malformed_sources_fail_closed(self):
        for raw in (b"", b"not compressed", self.raw[:-1], zlib.compress(b"<worlds>")):
            with self.subTest(raw=raw[:20]), self.assertRaises(ValueError):
                presentation.world_settings_payload(raw, active=True)
        malformed = zlib.compress(b"<worlds>")
        with mock.patch.object(presentation, "WORLD_SETTINGS_SHA256", hashlib.sha256(malformed).hexdigest()):
            with self.assertRaisesRegex(ValueError, "malformed"):
                presentation.world_settings_payload(malformed, active=True)

    def test_changed_world_or_hud_schema_and_linkages_fail_closed(self):
        changes = (
            lambda root: setattr(root, "tag", "unreviewed_worlds"),
            lambda root: root.append(copy.deepcopy(root.find("world[@name='farm']"))),
            lambda root: root.remove(root.find("world[@name='england']")),
            lambda root: root.find("world[@name='farm']/hudSkinConfig/hudAssets").set("path", "other.swf"),
            lambda root: root.find("world[@name='england']/hudSkinConfig/hudAssets").set("path", "other.swf"),
            lambda root: root.find("world[@name='england']/hudSkinConfig/hudAssets").set("neighborBarOffsetY", "-4"),
            lambda root: setattr(root.find("world[@name='england']/hudSkinConfig/hudAssets/zoomInButton/normal"), "text", "wrong_class"),
            lambda root: setattr(root.find("world[@name='england']/hudSkinConfig/hudAssets/zCacheButton/normal"), "text", "zcache_normal_farm"),
            lambda root: root.find("world[@name='england']/hudSkinConfig/hudAssets").append(ET.Element("currencyMeter")),
            lambda root: root.find("world[@name='england']/hudSkinConfig/hudAssets/friendBarSlotBackground").append(ET.Element("border")),
            lambda root: root.find("world[@name='england']/hudSkinConfig/hudAssets/friendBarSlotBackground").remove(
                root.find("world[@name='england']/hudSkinConfig/hudAssets/friendBarSlotBackground/borderOver")),
        )
        for change in changes:
            with self.subTest(change=change):
                root = self.parsed()
                change(root)
                with self.assertRaises(ValueError):
                    self.project_modified(root)

    def test_flag_and_input_types_cannot_enable_projection_implicitly(self):
        for flag in (1, "true", None, [], {}):
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                presentation.world_settings_payload(self.raw, active=flag)
        with self.assertRaises(ValueError):
            presentation.world_settings_payload("compressed bytes required", active=True)


if __name__ == "__main__":
    unittest.main()
