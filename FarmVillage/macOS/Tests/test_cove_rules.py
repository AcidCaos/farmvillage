"""Read-only contract and forged-action tests for the next Cove farming slice."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence  # Establish disposable writable paths before bundle imports.
import cove_rules


def plot(index, state="plowed"):
    return {"id": index, "className": "Plot", "state": state,
            "itemName": None, "position": {"x": 0, "y": 0, "z": 0}}


def save_with_plots(number, *, width=50):
    return {"userInfo": {"currentWorldType": "fisherman"},
            "world": {"sizeX": width, "sizeY": width, "tileSet": "fisherman",
                      "objectsArray": [plot(i + 1) for i in range(number)]}}


class CoveRulesTests(unittest.TestCase):
    def test_preserved_access_has_no_early_access_charge_or_grant(self):
        rules = cove_rules.recovered_rules()
        self.assertEqual((rules["minimumLevel"], rules["initialSize"], rules["storageId"]),
                         (15, 50, -9))
        self.assertEqual((rules["cashCost"], rules["coinCost"]), (0, 0))
        self.assertEqual(rules["rewards"], [{"type": "world_unlock", "value": "fisherman"}])
        self.assertEqual(rules["startTime"], 1316390400)
        self.assertEqual((rules["currency"], rules["score"], rules["score2"]), ("coins", None, None))
        rules["plotLimits"][50] = 999
        self.assertEqual(cove_rules.plot_limit(50), 35)

    def test_exact_plot_limits_and_expansion_added_objects(self):
        self.assertEqual((cove_rules.plot_limit(50), cove_rules.plot_limit(58),
                          cove_rules.plot_limit(202), cove_rules.plot_limit(242)),
                         (35, 45, 915, 1325))
        for width in cove_rules.recovered_rules()["plotLimits"]:
            self.assertEqual(cove_rules.expansion_added_objects(width), ())
        for width in (None, False, 49, 51, 58.5, 250, "50"):
            with self.subTest(width=width), self.assertRaises(ValueError):
                cove_rules.plot_limit(width)

    def test_new_plot_cap_counts_every_state_and_allows_existing_plot_retry(self):
        save = save_with_plots(35)
        for index, item in enumerate(save["world"]["objectsArray"]):
            item["state"] = ("plowed", "fallow", "planted", "grown", "withered")[index % 5]
        before = copy.deepcopy(save)
        for action in ("plow", "place"):
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, "plot limit"):
                cove_rules.guard_plot_cap(save, action, plot(999))
        cove_rules.guard_plot_cap(save, "plow", plot(1))
        cove_rules.guard_plot_cap(save, "place", plot(1, "planted"))
        cove_rules.guard_plot_cap(save, "move", plot(1))
        self.assertEqual(save, before)

    def test_last_plot_and_expansion_raise_cap(self):
        save = save_with_plots(34)
        cove_rules.guard_plot_cap(save, "plow", plot(999))
        save = save_with_plots(44, width=58)
        cove_rules.guard_plot_cap(save, "place", plot(999, "planted"))
        save["world"]["objectsArray"].append(plot(100))
        with self.assertRaises(ValueError):
            cove_rules.guard_plot_cap(save, "place", plot(999, "planted"))

    def test_temporary_id_retries_do_not_consume_another_plot(self):
        save = save_with_plots(35)
        save["world"]["objectsArray"][0]["tempId"] = 98765
        cove_rules.guard_plot_cap(save, "plow", plot(98765))
        with self.assertRaises(ValueError):
            cove_rules.guard_plot_cap(save, "move", plot(999))

    def test_replow_retains_only_the_saved_fallow_crop_and_clock(self):
        saved = dict(plot(626, "fallow"), itemName="whiteanthuriums", plantTime=1792709859000)
        incoming = dict(saved, state="plowed")
        before = copy.deepcopy(saved)
        cove_rules.guard_plow_snapshot(incoming, saved)
        cove_rules.guard_plow_snapshot(incoming, incoming)
        cove_rules.guard_plow_snapshot(dict(incoming, plantTime=0), saved)
        cove_rules.guard_plow_snapshot(plot(999), None)
        for existing in (None, dict(saved, state="planted"), dict(saved, state="grown"),
                         dict(saved, className="Building")):
            with self.subTest(existing=existing), self.assertRaises(ValueError):
                cove_rules.guard_plow_snapshot(incoming, existing)
        for change in ({"itemName": "strawberry"}, {"plantTime": 1},
                       {"position": {"x": 4, "y": 4, "z": 0}}, {"state": "fallow"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                cove_rules.guard_plow_snapshot(dict(incoming, **change), saved)
        self.assertEqual(saved, before)

    def test_forged_plot_class_changes_and_special_plot_flags_fail(self):
        save = save_with_plots(2)
        forged = {**plot(1), "className": "Building"}
        with self.assertRaisesRegex(ValueError, "object class"):
            cove_rules.guard_plot_cap(save, "place", forged)
        for flag in ("isJumbo", "isBigPlot", "isProduceItem", "isSuperPlot"):
            with self.subTest(flag=flag), self.assertRaisesRegex(ValueError, "Specialized"):
                cove_rules.guard_plot_cap(save, "plow", {**plot(999), flag: True})
        save["world"]["objectsArray"].append({"id": 99, "className": "Building"})
        with self.assertRaisesRegex(ValueError, "replaced"):
            cove_rules.guard_plot_cap(save, "place", plot(99))

    def test_invalid_imported_terrain_and_size_preserve_snapshot(self):
        mutations = [
            {"tileSet": "grass_theme"}, {"terrain": [1] * 625},
            {"sizeX": 58, "sizeY": 50}, {"sizeX": 51, "sizeY": 51},
            {"objectsArray": [plot(i) for i in range(36)]},
            {"objectsArray": [{"id": 1, "className": "FishermansCoveBuilding"}]},
        ]
        for mutation in mutations:
            world = {**save_with_plots(0)["world"], **mutation}
            before = copy.deepcopy(world)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                cove_rules.guard_snapshot(world)
            self.assertEqual(world, before)

    def test_basic_items_and_ground_terrain_are_explicitly_bounded(self):
        for item in ({"type": "seed"}, {"type": "animal"},
                     {"type": "tree"}, {"type": "decoration", "className": "RotateableDecoration"},
                     {"type": "building", "className": "StorageBuilding"}):
            cove_rules.guard_special_item(item)
            cove_rules.guard_land_terrain(item)
        for item in ({"type": "vehicle", "className": "Combine"},
                     {"type": "building", "className": "FishermansCoveBuilding"},
                     {"type": "building", "className": "CraftingCottageBuilding"},
                     {"type": "building", "features": {"feature": {"name": "harvester"}}}):
            with self.subTest(item=item), self.assertRaises(ValueError):
                cove_rules.guard_special_item(item)
        for name in ("default", "land"):
            cove_rules.guard_land_terrain({"terrainSet": {"terrain": {"name": name}}})
        for name in ("water", "shoreline", "terrace", "unknown"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                cove_rules.guard_land_terrain({"terrainSet": {"terrain": {"name": name}}})

    def test_archive_changes_fail_closed(self):
        original = cove_rules._xml
        mutations = (
            ("gameSettings.xml.gz", "expansions/expansion[@name='fisherman']/allAccess", "cashCost", "1"),
            ("gameSettings.xml.gz", "expansions/expansion[@name='fisherman']/plotLimits/plotLimit", "plots", "500"),
            ("gameSettingsCMS.xml.gz", ".//prereq[@name='fv_fisherman_general_access']/prereq", "value", "1"),
            ("yimf.xml.gz", "yimf[@type='fisherman']", "type", "grass_theme"),
        )
        try:
            for filename, xpath, key, value in mutations:
                def changed(name):
                    root = original(name)
                    if name == filename:
                        root.find(xpath).set(key, value)
                    return root
                cove_rules._archive_contract.cache_clear()
                with self.subTest(filename=filename, xpath=xpath), patch.object(cove_rules, "_xml", changed):
                    with self.assertRaises(ValueError):
                        cove_rules.recovered_rules()
        finally:
            cove_rules._archive_contract.cache_clear()

    def test_other_worlds_are_not_modified_by_cove_cap_guard(self):
        save = save_with_plots(100)
        save["userInfo"]["currentWorldType"] = "farm"
        before = copy.deepcopy(save)
        cove_rules.guard_plot_cap(save, "plow", plot(999))
        self.assertEqual(save, before)


if __name__ == "__main__":
    unittest.main()
