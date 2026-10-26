"""Disposable offline policy proofs; no Haunted Hollow activation or saves."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence  # Isolate writable paths before any product import.
import hallow_rules
import hallow_world_rules as hallow


def world(*objects, limit=None, width=50):
    result = {"sizeX": width, "sizeY": width, "tileSet": "hallow_theme",
              "objectsArray": list(objects), "opaqueImport": {"keep": [1, 2]}}
    if limit is not None:
        result["maxNumObjects"] = limit
    return result


def plot(identifier=1, state="plowed", **fields):
    return {"id": identifier, "className": "Plot", "state": state, **fields}


def mandatory(identifier, class_name, item_name, position, state):
    """Literal client-written shape of a recovered expansion object."""
    x, y = position
    return {"id": identifier, "className": class_name, "itemName": item_name,
            "position": {"x": x, "y": y, "z": 0}, "state": state, "deleted": False,
            "direction": 0, "components": {}, "instanceDataStoreKey": None,
            "plantTime": None, "buildTime": 0, "contents": []}


FIRST_EXPANSION = [
    mandatory(2, "FixedTreasureConstructionBuilding", "xhw_treasure1_s", (5, 44), "construct_0"),
    mandatory(3, "FixedTreasureConstructionBuilding", "xhw_treasure1_l", (24, 5), "construct_0"),
    mandatory(4, "FixedTreasureConstructionBuilding", "xhw_treasure1_xl", (4, 16), "construct_0"),
    mandatory(5, "FeatureBuilding", "animal_breeding_xhwaviary_finished", (40, 0), "built_0"),
]


class HauntedHollowWorldRulesTests(unittest.TestCase):
    def test_original_theme_is_distinct_from_world_key_and_has_no_plot_table(self):
        rules = hallow.recovered_rules()
        self.assertEqual((rules["worldType"], rules["themeType"], rules["worldRequirementType"]),
                         ("hallow", "hallow_theme", "hallow"))
        self.assertEqual(rules["theme"]["tileClass"], "grass")
        self.assertEqual(rules["theme"]["horizon"], "assets/Environment/xhw_theme.swf")
        self.assertEqual(rules["theme"]["backgroundPath"], "assets/Environment/xhw_themeBackground_")
        self.assertIsNone(rules["worldSpecificPlotLimits"])
        self.assertEqual(rules["defaultMaxNumObjects"], 5500)
        self.assertEqual(rules["groundTerrainNamesWithoutMap"],
                         ["all", "amphibious", "default", "land", "plowable"])
        self.assertFalse(rules["originalStarterRecovered"])
        self.assertFalse(rules["originalTerrainMapRecovered"])
        rules["theme"]["tileClass"] = "water"
        rules["firstExpansionAdditions"].clear()
        self.assertEqual(len(hallow.recovered_rules()["firstExpansionAdditions"]), 4)
        self.assertEqual(hallow.recovered_rules()["theme"]["tileClass"], "grass")

    def test_plot_limit_uses_imported_override_not_cove_width_caps(self):
        for width in (50, 58, 202):
            self.assertEqual(hallow.plot_limit(world(width=width)), 5500)
            self.assertEqual(hallow.plot_limit(world(width=width, limit=9)), 9)
        for invalid in (0, False, -1, "9", 1.5, float("nan"), float("inf"), 10 ** 1000):
            imported = world(limit=invalid)
            before = copy.deepcopy(imported)
            with self.subTest(invalid=str(invalid)[:30]), self.assertRaises(ValueError):
                hallow.plot_limit(imported)
            self.assertEqual(list(imported), list(before))
            self.assertIs(imported["maxNumObjects"], invalid)

    def test_every_plot_state_counts_and_existing_retry_can_stay_at_limit(self):
        for state in ("plowed", "planted", "grown", "withered", "fallow"):
            imported = world(plot(state=state, tempId=-10), limit=1)
            before = copy.deepcopy(imported)
            self.assertEqual(hallow.guard_snapshot(imported), 1)
            for identifier in (1, -10):
                hallow.guard_plot_transition(imported, "plow", plot(identifier))
                hallow.guard_plot_transition(imported, "move", plot(identifier))
            with self.assertRaisesRegex(ValueError, "reached"):
                hallow.guard_plot_transition(imported, "place", plot(2))
            self.assertEqual(imported, before)
        self.assertEqual(hallow.guard_snapshot(world(plot(), limit=2)), 1)
        hallow.guard_plot_transition(world(plot(), limit=2), "plow", plot(2))
        with self.assertRaisesRegex(ValueError, "exceeds"):
            hallow.guard_snapshot(world(plot(), plot(2), limit=1))

    def test_unknown_or_mapped_terrain_is_preserved_and_not_assumed_land(self):
        cases = []
        for value in ([], [0], [1, 2], "", False, 0, {"mask": "unknown"}):
            imported = world()
            imported["terrain"] = value
            cases.append(imported)
        for theme in ("hallow", "grass", "fisherman", None):
            imported = world()
            imported["tileSet"] = theme
            cases.append(imported)
        for width in (49, 51, 210, True, float("inf")):
            cases.append(world(width=width))
        imported = world()
        imported["sizeY"] = 58
        cases.append(imported)
        for imported in cases:
            before = copy.deepcopy(imported)
            with self.subTest(imported=imported), self.assertRaises(ValueError):
                hallow.guard_snapshot(imported)
            self.assertEqual(imported, before)
        imported = world()
        imported["terrain"] = None
        self.assertEqual(hallow.guard_snapshot(imported), 0)

    def test_special_plot_flags_and_class_changes_cannot_bypass_preflight(self):
        for flag in hallow._SPECIAL_PLOT_FLAGS:
            with self.subTest(flag=flag), self.assertRaisesRegex(ValueError, "Specialized"):
                hallow.guard_snapshot(world(plot(**{flag: True})))
            with self.subTest(flag=flag), self.assertRaisesRegex(ValueError, "Specialized"):
                hallow.guard_plot_transition(world(), "plow", plot(**{flag: True}))
        with self.assertRaisesRegex(ValueError, "replace"):
            hallow.guard_plot_transition(world(plot()), "move", {"id": 1, "className": "Decoration"})
        building = {"id": 1, "className": "Building", "itemName": "hauntedhotel"}
        with self.assertRaisesRegex(ValueError, "replace"):
            hallow.guard_plot_transition(world(building), "place", plot())
        with self.assertRaisesRegex(ValueError, "saved object"):
            hallow.guard_plot_transition(world(), "move", plot())
        with self.assertRaisesRegex(ValueError, "ordinary"):
            hallow.guard_plot_transition(world(), "plow", {"className": "Building"})

    def test_original_world_requirements_apply_in_both_directions(self):
        for name in ("jackolantern2", "spectrestrawberries", "garlic2", "hauntedhotel"):
            hallow.guard_item_world(name)
            for other in ("farm", "england", "fisherman", "meadows"):
                with self.subTest(name=name, other=other), self.assertRaisesRegex(ValueError, "another original world"):
                    hallow.guard_item_world(name, other)
        # Unrestricted items remain eligible in Hallow; Farm+license+Cove
        # alternatives do not silently grant a shipping license in Hallow.
        hallow.guard_item_world("strawberry")
        hallow.guard_item_world("ghostchili", "farm")
        hallow.guard_item_world("ghostchili", "fisherman")
        with self.assertRaisesRegex(ValueError, "license or special"):
            hallow.guard_item_world("ghostchili")
        with self.assertRaises(ValueError):
            hallow.guard_item_world("poisonflowertree")

    def test_basic_class_policy_does_not_waive_spook_or_other_purchase_gates(self):
        for name in ("strawberry", "garlic2", "hauntedhotel", "witcheshut"):
            hallow.guard_basic_item(name)
        self.assertEqual(hallow_rules.item_level_requirement("garlic2"), 2)
        imported = {"userInfo": {"player": {}}}
        before = copy.deepcopy(imported)
        with self.assertRaisesRegex(ValueError, "Spook level 2"):
            hallow_rules.guard_item_level(imported, "garlic2")
        self.assertEqual(imported, before)
        hallow.guard_basic_item("xhw_hauntedinn")
        with self.assertRaisesRegex(ValueError, "quest or special"):
            hallow_rules.item_level_requirement("xhw_hauntedinn")
        for name in ("animal_breeding_xhwaviary_finished", "xhw_treasure1_s",
                     "xhw_treasure1_m", "xhw_treasure1_l", "xhw_treasure1_xl",
                     "hatchstorage", "xhwfarm14"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "not restored"):
                hallow.guard_basic_item(name)
        for value in ("missing", {"name": "garlic2", "className": "Decoration"}, None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "unknown"):
                hallow.guard_basic_item(value)

    def test_catalog_identity_blocks_feature_building_packet_spoofing(self):
        for class_name in ("FeatureBuilding", "Building", "Decoration", None):
            imported = world({"id": 1, "itemName": "animal_breeding_xhwaviary_finished",
                              "className": class_name})
            before = copy.deepcopy(imported)
            with self.subTest(class_name=class_name), self.assertRaises(ValueError):
                hallow.guard_snapshot(imported)
            self.assertEqual(imported, before)
        self.assertEqual(hallow.guard_snapshot(world(
            {"className": "Building", "itemName": "hauntedhotel"})), 0)
        self.assertEqual(hallow.guard_snapshot(world(
            plot(itemName="spectrestrawberries", state="grown"))), 1)
        with self.assertRaises(ValueError):
            hallow.guard_snapshot(world(plot(itemName="hauntedhotel")))
        with self.assertRaises(ValueError):
            hallow.guard_snapshot(world(plot(itemName="poisonflowertree")))

    def test_terrain_sets_are_original_named_ancestors_not_water_invented_from_art(self):
        hallow.guard_land_terrain("strawberry")
        hallow.guard_land_terrain("duck_crazyclown")  # amphibious includes default/land.
        with self.assertRaisesRegex(ValueError, "terrain outside"):
            hallow.guard_land_terrain("dolphin_xha_treatonly")

    def test_first_expansion_requires_three_treasures_and_finished_aviary(self):
        added = hallow.expansion_added_objects(58)
        self.assertEqual([(e["code"], e["itemName"], e["x"], e["y"], e["z"], e["state"])
                          for e in added], [
            ("7Ec", "xhw_treasure1_s", "5", "44", "0", "construct_0"),
            ("7DI", "xhw_treasure1_l", "24", "5", "0", "construct_0"),
            ("7D0", "xhw_treasure1_xl", "4", "16", "0", "construct_0"),
            ("7IZ", "animal_breeding_xhwaviary_finished", "40", "0", "0", "built_0")])
        self.assertEqual([(e["sizeX"], e["sizeY"]) for e in added], [(1, 1), (3, 3), (4, 4), (8, 6)])
        self.assertEqual([e["className"] for e in added],
                         ["FixedTreasureConstructionBuilding"] * 3 + ["FeatureBuilding"])
        self.assertEqual([e["itemRules"]["matsNeeded"] for e in added], ["10", "28", "42", "30"])
        self.assertEqual(added[-1]["itemRules"]["capacity"], "20")
        self.assertEqual(added[-1]["itemRules"]["initialExpansionLevel"], "1")
        self.assertEqual(added[-1]["itemRules"]["defaultItem"],
                         {"name": "seagull", "amount": "1", "render": "true"})
        self.assertTrue(all(e["restored"] is False for e in added))
        self.assertEqual(hallow.expansion_added_objects(50), [])
        self.assertEqual(hallow.expansion_added_objects(154), [])
        self.assertIn("xhw_treasure1_m", [e["itemName"] for e in hallow.expansion_added_objects(66)])
        added[0]["x"] = "0"
        self.assertEqual(hallow.expansion_added_objects(58)[0]["x"], "5")
        for width in (51, True, "58"):
            with self.subTest(width=width), self.assertRaises(ValueError):
                hallow.expansion_added_objects(width)
        with self.assertRaisesRegex(ValueError, "not restored"):
            hallow_rules.guard_land_purchase({}, "xhwfarm14")

    def test_guard_admits_only_exact_recovered_first_expansion_objects(self):
        self.assertEqual(hallow.guard_snapshot(world(*FIRST_EXPANSION, width=58)), 0)
        self.assertEqual(hallow.guard_snapshot(world(*FIRST_EXPANSION, width=66)), 0)
        with self.assertRaisesRegex(ValueError, "overlap"):
            hallow.guard_snapshot(world(*FIRST_EXPANSION, mandatory(
                6, "FixedTreasureConstructionBuilding", "xhw_treasure1_l", (38, 5), "construct_0"),
                width=66))

    def test_guard_rejects_any_inexact_treasure_or_aviary_without_mutation(self):
        first, rest = FIRST_EXPANSION[0], FIRST_EXPANSION[1:]
        cases = {
            "extra key": [dict(first, tempId=-5), *rest],
            "missing key": [{k: v for k, v in first.items() if k != "contents"}, *rest],
            "shifted position": [dict(first, position={"x": 6, "y": 44, "z": 0}), *rest],
            "wrong state": [dict(first, state="built"), *rest],
            "deleted": [dict(first, deleted=True), *rest],
            "components": [dict(first, components={"x": {}}), *rest],
            "string id": [dict(first, id="2"), *rest],
            "aviary class": [dict(FIRST_EXPANSION[3], className="Building"), *FIRST_EXPANSION[:3]],
            "unplanned 66 treasure at 58": [*FIRST_EXPANSION, mandatory(
                6, "FixedTreasureConstructionBuilding", "xhw_treasure1_m", (5, 30), "construct_0")],
            "duplicate": [*FIRST_EXPANSION, mandatory(
                6, "FixedTreasureConstructionBuilding", "xhw_treasure1_s", (5, 44), "construct_0")],
        }
        for label, objects in cases.items():
            imported = world(*objects, width=58)
            before = copy.deepcopy(imported)
            with self.subTest(case=label), self.assertRaises(ValueError):
                hallow.guard_snapshot(imported)
            self.assertEqual(imported, before)

    def test_source_drift_fails_closed_before_contract_interpretation(self):
        with tempfile.TemporaryDirectory(prefix="hallow-world-source-") as directory:
            path = Path(directory, "gz/v855098")
            path.mkdir(parents=True)
            original = Path(hallow.XML_DIR, "gz/v855098/gameSettings.xml.gz").read_bytes()
            Path(path, "gameSettings.xml.gz").write_bytes(original + b"changed")
            with patch.object(hallow, "XML_DIR", directory), self.assertRaisesRegex(ValueError, "changed"):
                hallow._xml("gameSettings.xml.gz")


if __name__ == "__main__":
    unittest.main()
