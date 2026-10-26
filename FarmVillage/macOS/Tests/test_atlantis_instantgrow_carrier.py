"""Exact Atlantis temporary Instant Grow carrier, portable before activation."""
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]
import test_persistence as fixtures  # Synthetic paths before bundle imports.
import instant_growth
import items


class AtlantisInstantGrowCarrierTests(unittest.TestCase):
    # Reuse setup only; do not inherit unrelated persistence test methods.
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)

    @staticmethod
    def world_save(world="atlantis"):
        return {"userInfo": {"currentWorldType": world}}

    def test_original_catalog_and_world_settings_pin_the_submarine_visual(self):
        source = Path(items.ITEMS_AMF)
        before = source.read_bytes()
        rows = items._decode_items(before)["settings"]["items"]["item"]
        matches = [row for row in rows if row.get("name") == "xalsubmarine"]
        self.assertEqual(len(matches), 1)
        plane = matches[0]
        self.assertEqual((plane["code"], plane["className"], plane["experimentGate"]),
                         ("ht9", "Airplane", "fv_atlantis"))
        self.assertNotIn("requirements", plane)
        self.assertEqual(items.get_item_by_name("xalsubmarine"), plane)
        archived = instant_growth.cove_rules._xml("worldSettings.xml.gz")
        visual = archived.findall("world[@name='atlantis']/hudSkinConfig/instantGrowItemVisual")
        self.assertEqual([node.attrib for node in visual], [{"name": "xalsubmarine"}])
        self.assertEqual(source.read_bytes(), before)

    def test_original_submarine_is_allowed_without_mutating_save_or_catalog(self):
        save = self.world_save()
        plane = items.get_item_by_name("xalsubmarine")
        before = copy.deepcopy((save, plane))
        self.assertTrue(instant_growth._temporary_airplane_allowed(save, plane))
        self.assertEqual((save, plane), before)

    def test_submarine_is_rejected_in_every_other_original_world(self):
        plane = items.get_item_by_name("xalsubmarine")
        archived = instant_growth.cove_rules._xml("worldSettings.xml.gz")
        worlds = {node.get("name") for node in archived}
        self.assertIn("atlantis", worlds)
        for world in sorted(worlds - {"atlantis"}) + [None, "not-a-recovered-world"]:
            with self.subTest(world=world):
                save = self.world_save(world)
                before = copy.deepcopy((save, plane))
                self.assertFalse(instant_growth._temporary_airplane_allowed(save, plane))
                self.assertEqual((save, plane), before)

    def test_requirement_free_lookalikes_and_wrong_gates_are_rejected(self):
        plane = items.get_item_by_name("xalsubmarine")
        for changes in ({"name": "forgedsubmarine"}, {"name": "xcwbiplane"},
                        {"experimentGate": "fv_candy"}, {"experimentGate": ""},
                        {"experimentGate": None}):
            with self.subTest(changes=changes):
                candidate = dict(plane, **changes)
                before = copy.deepcopy(candidate)
                self.assertFalse(instant_growth._temporary_airplane_allowed(self.world_save(), candidate))
                self.assertEqual(candidate, before)

    def test_added_licence_or_world_requirements_do_not_receive_the_exception(self):
        plane = items.get_item_by_name("xalsubmarine")
        license_ = {"className": "WorldLicense", "name": "atlantis"}
        world = {"className": "World", "name": "atlantis"}
        for requirements in ({"requirement": license_}, {"requirement": [license_]},
                             {"requirement": world}, {"requirement": [world, license_]}):
            with self.subTest(requirements=requirements):
                candidate = dict(plane, requirements=copy.deepcopy(requirements))
                before = copy.deepcopy(candidate)
                self.assertFalse(instant_growth._temporary_airplane_allowed(self.world_save(), candidate))
                self.assertEqual(candidate, before)


if __name__ == "__main__":
    unittest.main()
