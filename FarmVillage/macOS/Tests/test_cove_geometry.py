"""Cove geometry boundaries and original out-of-object plot flags."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence
import cove_rules
from test_cove_rules import save_with_plots


class CoveGeometryTests(unittest.TestCase):
    def test_original_serialized_special_flags_cannot_bypass_plot_guard(self):
        # BitFlagsById first group bits 0/1/2 encode the original flags 1/2/3.
        for flags in (1, 2, 4, 7, 0x8000):
            world = save_with_plots(1)["world"]
            world["serializedExtraItemFlags"] = [[(1 << 16) | flags]]
            before = copy.deepcopy(world)
            with self.subTest(flags=flags), self.assertRaisesRegex(ValueError, "flags are not restored"):
                cove_rules.guard_snapshot(world)
            self.assertEqual(world, before)
        world = save_with_plots(1)["world"]
        world["serializedExtraItemFlags"] = [[], [(1 << 16) | 1]]
        with self.assertRaisesRegex(ValueError, "flags are not restored"):
            cove_rules.guard_snapshot(world)

    def test_original_empty_serialized_groups_do_not_change_ordinary_plot_count(self):
        for serial in (None, [], [[]], [[], []], [[1 << 16]], [[0xffff0000]]):
            world = save_with_plots(35)["world"]
            world["serializedExtraItemFlags"] = serial
            before = copy.deepcopy(world)
            self.assertEqual(cove_rules.guard_snapshot(world), 35)
            self.assertEqual(world, before)

    def test_malformed_imported_flags_are_preserved_for_recovery(self):
        for serial in ({}, "", [None], [1], [[True]], [[-1]], [[0x100000000]], [[1.5]], [["65537"]]):
            world = save_with_plots(0)["world"]
            world["serializedExtraItemFlags"] = serial
            before = copy.deepcopy(world)
            with self.subTest(serial=serial), self.assertRaisesRegex(ValueError, "invalid"):
                cove_rules.guard_snapshot(world)
            self.assertEqual(world, before)

    def test_known_theme_does_not_make_a_supplied_terrain_array_buildable(self):
        world = save_with_plots(0)["world"]
        world["terrain"] = [0] * 625
        before = copy.deepcopy(world)
        with self.assertRaisesRegex(ValueError, "terrain"):
            cove_rules.guard_snapshot(world)
        self.assertEqual(world, before)
        # Named sets use the original default-land ancestor chain only.
        for terrain in ("default", "land", "amphibious", "plowable", "all"):
            cove_rules.guard_land_terrain({"terrainSet": {"terrain": {"name": terrain}}})
        for terrain in ("water", "shoreline", "terrace"):
            with self.assertRaisesRegex(ValueError, "terrain unavailable"):
                cove_rules.guard_land_terrain({"terrainSet": {"terrain": {"name": terrain}}})

    def test_exact_restaurant_identity_is_the_only_cottage_exception(self):
        item = {"name": "xcovecraftingcottage", "code": "^2", "type": "building",
                "className": "CraftingCottageBuilding", "craftType": "restaurant"}
        cove_rules.guard_special_item(item)
        world = save_with_plots(0)["world"]
        cottage = {"id": 1, "itemName": "xcovecraftingcottage", "className": "CraftingCottageBuilding"}
        world["objectsArray"].append(cottage)
        self.assertEqual(cove_rules.guard_snapshot(world), 0)
        for changes in ({"name": "xhdcraftingcottage"}, {"code": "other"}, {"craftType": "bakery"},
                        {"features": {"feature": {"name": "harvester"}}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                cove_rules.guard_special_item({**item, **changes})
        world["objectsArray"].append({**cottage, "id": 2})
        with self.assertRaisesRegex(ValueError, "limit"):
            cove_rules.guard_snapshot(world)
        world["objectsArray"] = [{**cottage, "itemName": "craftingbakery"}]
        with self.assertRaisesRegex(ValueError, "unsupported cottage"):
            cove_rules.guard_snapshot(world)


if __name__ == "__main__":
    unittest.main()
