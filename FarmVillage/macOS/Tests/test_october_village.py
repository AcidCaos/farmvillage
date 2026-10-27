"""Authored new-village preset checks; no real saves, artwork or server socket."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures  # Redirect writable paths before product imports.
import october_village as october


def fresh_save():
    save = json.loads((fixtures.ROOT / "villages" / "initial.json").read_text())
    save["userInfo"]["player"]["userId"] = "new-october-farmer"
    save["flashHotParams"]["ZYNGA_USER_ID"] = "new-october-farmer"
    save["world"]["uid"] = "new-world-identity"
    stamp = 1_800_000_000
    save["userInfo"]["firstDayTimestamp"] = stamp
    save["userInfo"]["worldSummaryData"]["farm"].update(firstLoaded=stamp, lastLoaded=stamp)
    for obj in save["world"]["objectsArray"]:
        if obj["className"] == "Plot" and obj["state"] == "grown":
            obj["plantTime"] = 1_799_917_200_000
    return save


def catalog_fixture():
    records = {"barn": {"name": "barn", "sizeX": "8", "sizeY": "6"}}
    for name, original in october.PALETTE.items():
        records[name] = {"name": name, "code": original["code"],
            "type": original["type"], "placeable": "true",
            "sizeX": str(original["footprint"][0]), "sizeY": str(original["footprint"][1]),
            "image": [{"name": original["image"][0], "url": original["image"][1]}]}
        if original["type"] == "tree":
            records[name].update(growTime="2", coinYield="150")
            records[name]["image"].append({"name": original["bareImage"][0], "url": original["bareImage"][1]})
        elif original["className"] != "Decoration":
            records[name]["className"] = original["className"]
    return records


class OctoberStarterTests(unittest.TestCase):
    def setUp(self):
        self.save = fresh_save()
        self.catalog = catalog_fixture()

    def apply(self, save=None, catalog=None):
        return october.apply_new_preset(self.save if save is None else save,
            catalog_lookup=(self.catalog if catalog is None else catalog).get,
            growth_seconds=lambda item: float(item["growTime"]) * 82800)

    def test_authored_starter_keeps_all_original_player_fields_objects_and_clocks(self):
        self.save["unknownImportedField"] = {"retained": [1, {"opaque": True}]}
        self.save["world"]["unknownTimer"] = {"start": 123456, "duration": 98765}
        before = copy.deepcopy(self.save)
        result = self.apply()
        self.assertEqual(self.save, before)
        self.assertEqual(result["userInfo"], before["userInfo"])
        self.assertEqual(result["flashHotParams"], before["flashHotParams"])
        self.assertEqual(result["unknownImportedField"], before["unknownImportedField"])
        self.assertEqual(result["world"]["objectsArray"][:7], before["world"]["objectsArray"])
        self.assertEqual(result["world"]["unknownTimer"], before["world"]["unknownTimer"])
        self.assertEqual(result["world"]["uid"], "new-world-identity")
        self.assertEqual(result["world"]["tileSet"], "autumngrass_theme")
        self.assertEqual((result["userInfo"]["player"]["gold"],
                          result["userInfo"]["player"]["cash"],
                          result["userInfo"]["player"]["xp"]), (200, 5, 0))
        self.assertEqual(len(result["world"]["objectsArray"]), 61)

    def test_result_is_fully_detached_and_provenance_does_not_pollute_client_objects(self):
        result = self.apply()
        result["userInfo"]["player"]["storageData"]["-2"]["SB"][0] = 999
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-2"]["SB"][0], 2)
        marker = result[october.STATE_KEY]
        self.assertEqual(marker["compositionStatus"], "authored")
        self.assertFalse(marker["originalMapRestored"])
        self.assertFalse(marker["originalMapleMechanicsActivated"])
        self.assertEqual(marker["catalogSource"]["sha256"], october.CATALOG_SHA256)
        self.assertEqual({row["donorWorld"] for row in marker["objects"]},
                         {"amsterdam", "spooky", "canada", "farm"})
        objects = result["world"]["objectsArray"][7:]
        self.assertEqual([row["objectId"] for row in marker["objects"]], [o["id"] for o in objects])
        self.assertTrue(all(row["assetStatus"] == "borrowed" and row["placementStatus"] == "authored"
                            for row in marker["objects"]))
        for obj in objects:
            self.assertEqual(set(obj), {"id", "className", "itemName", "position", "state",
                                       "direction", "deleted", "components", "instanceDataStoreKey"}
                             | ({"plantTime"} if obj["className"] == "Tree" else set()))
            # Original Decoration renders its saved image state; "built"
            # leaves only a shadow. RotateableDecoration starts horizontal.
            expected_state = ("ripe" if obj["className"] == "Tree" else
                              "horizontal" if obj["className"] == "RotateableDecoration" else "static")
            self.assertEqual(obj["state"], expected_state)
            self.assertIn(october.PALETTE[obj["itemName"]]["image"],
                          [(row["name"], row["url"])
                           for row in self.catalog[obj["itemName"]]["image"]])

    def test_added_ids_are_stable_and_skip_reserved_inventory_and_temporary_ids(self):
        first, second = self.apply(), self.apply()
        self.assertEqual(first, second)
        self.assertEqual([o["id"] for o in first["world"]["objectsArray"]], list(range(1, 62)))
        self.save["userInfo"]["player"]["storageData"]["100"] = {"opaque": [3, [], []]}
        self.assertEqual(self.apply()["world"]["objectsArray"][7]["id"], 101)
        self.save["userInfo"]["player"]["storageData"]["62999"] = {}
        self.assertEqual(self.apply()["world"]["objectsArray"][7]["id"], 65501)

    def test_no_available_id_rejects_without_mutation(self):
        self.save["userInfo"]["player"]["storageData"]["2147483647"] = {}
        before = copy.deepcopy(self.save)
        with self.assertRaisesRegex(ValueError, "available decoration IDs"):
            self.apply()
        self.assertEqual(self.save, before)

    def test_farming_area_and_all_footprints_are_clear_in_bounds_and_disjoint(self):
        result = self.apply()
        rectangles = [(25, 25, 8, 6), (27, 13, 4, 4), (27, 9, 4, 4),
                      (19, 9, 4, 4), (19, 13, 4, 4), (23, 9, 4, 4), (23, 13, 4, 4)]
        for obj, record in zip(result["world"]["objectsArray"][7:], result[october.STATE_KEY]["objects"]):
            x, y = obj["position"]["x"], obj["position"]["y"]
            width, height = record["footprint"]["sizeX"], record["footprint"]["sizeY"]
            self.assertTrue(0 <= x < x + width <= 50 and 0 <= y < y + height <= 50)
            # Independent closed-open rectangle comparison against every old
            # object and the reserved 20×24 farming area.
            for bx, by, bw, bh in [*rectangles, (16, 0, 20, 24), *october.WALKWAYS]:
                self.assertTrue(x + width <= bx or bx + bw <= x or y + height <= by or by + bh <= y)
            rectangles.append((x, y, width, height))

    def test_repeat_after_play_never_resets_state(self):
        result = self.apply()
        result["userInfo"]["player"]["gold"] = 987654
        result["world"]["objectsArray"][-1]["position"]["x"] = 47
        restored = json.loads(json.dumps(result))
        before = copy.deepcopy(restored)
        with self.assertRaisesRegex(ValueError, "creating a new village"):
            self.apply(restored)
        self.assertEqual(restored, before)

    def test_autumn_woodland_contains_real_maple_groves_and_original_tree_growth_clocks(self):
        result = self.apply()
        added = result["world"]["objectsArray"][7:]
        trees = [obj for obj in added if obj["className"] == "Tree"]
        self.assertEqual(len(trees), 28)
        self.assertEqual(sum("maple" in obj["itemName"] for obj in trees), 24)
        self.assertEqual(sum(obj["className"] != "Tree" for obj in added), 26)
        for tree in trees:
            self.assertEqual(tree["state"], "ripe")
            self.assertEqual(tree["plantTime"], (1_800_000_000 - 2 * 82800) * 1000)
        # The original seven objects and their crop clocks are not part of the
        # authored ready-tree initialization.
        self.assertEqual(result["world"]["objectsArray"][:7], self.save["world"]["objectsArray"])

    def test_tree_runtime_conversion_is_required_and_invalid_durations_fail_without_mutation(self):
        for conversion in (None, lambda item: 0, lambda item: float("nan"), lambda item: -1):
            before = copy.deepcopy(self.save)
            with self.subTest(conversion=conversion), self.assertRaises(ValueError):
                october.apply_new_preset(self.save, catalog_lookup=self.catalog.get, growth_seconds=conversion)
            self.assertEqual(self.save, before)
        name = "giantmapleshadetree"
        for field, value in (("growTime", "1"), ("coinYield", "151"), ("className", "Animal")):
            catalog = copy.deepcopy(self.catalog)
            catalog[name][field] = value
            before = copy.deepcopy(self.save)
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.apply(catalog=catalog)
            self.assertEqual(self.save, before)

    def test_loaded_import_another_world_or_altered_starter_is_refused(self):
        changes = (
            lambda s: s.update(version="2026.10"),
            lambda s: s["userInfo"].update(is_new=False),
            lambda s: s["userInfo"].update(firstDay=False),
            lambda s: s["userInfo"].update(currentWorldType="canada"),
            lambda s: s["world"].update(sizeX=58),
            lambda s: s["world"]["objectsArray"][1].update(state="planted"),
            lambda s: s["world"]["objectsArray"][0]["position"].update(x=24),
            lambda s: s["world"]["objectsArray"].append({"id": 88}),
            lambda s: s.update(_ownedWorldTravel={"version": 1, "inactive": {}}),
            lambda s: s["userInfo"]["worldSummaryData"]["farm"].update(lastLoaded=1_800_000_001),
        )
        for change in changes:
            with self.subTest(change=change):
                save = fresh_save()
                change(save)
                before = copy.deepcopy(save)
                with self.assertRaisesRegex(ValueError, "creating a new village"):
                    self.apply(save)
                self.assertEqual(save, before)

    def test_missing_changed_feature_or_water_catalog_item_fails_atomically(self):
        name = "xdm_luxurygardengazebo"
        changes = (
            lambda c: c.pop(name),
            lambda c: c[name].update(code="different-original"),
            lambda c: c[name].update(className="LootableFixedFeatureBuilding"),
            lambda c: c[name].update(type="building"),
            lambda c: c[name].update(sizeX="7"),
            lambda c: c[name].update(image=[]),
            lambda c: c[name].update(features={"feature": {"name": "unrestored"}}),
            lambda c: c[name].update(growTime="1"),
            lambda c: c[name].update(action="harvest"),
            lambda c: c[name].update(terrainSet={"terrain": {"name": "water"}}),
            lambda c: c[name].update(requirements={"requirement": {"className": "World", "name": "canada"}}),
        )
        for change in changes:
            with self.subTest(change=change):
                catalog = copy.deepcopy(self.catalog)
                change(catalog)
                before = copy.deepcopy(self.save)
                with self.assertRaises(ValueError):
                    self.apply(catalog=catalog)
                self.assertEqual(self.save, before)

    def test_invalid_authored_geometry_never_partially_decorates_input(self):
        name = "xdm_luxurygardengazebo"
        for x, y in ((-1, 0), (49, 49), (19, 9), (25, 25), (16, 0), (14, 25), (36, 32)):
            before = copy.deepcopy(self.save)
            layout = (*october.LAYOUT, (name, x, y, "invalid-test"))
            with self.subTest(x=x, y=y), mock.patch.object(october, "LAYOUT", layout):
                with self.assertRaisesRegex(ValueError, "overlapping or out-of-bounds"):
                    self.apply()
            self.assertEqual(self.save, before)


class OctoberOriginalCatalogTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)

    def test_entire_palette_matches_actual_original_catalog_without_feature_or_terrain_adapters(self):
        items = self.catalogs[1]
        original = {name: copy.deepcopy(items.get_item_by_name(name)) for name in october.PALETTE}
        settings = self.catalogs[0]
        result = october.apply_new_preset(fresh_save(), catalog_lookup=items.get_item_by_name,
            growth_seconds=lambda item: float(item["growTime"])
                * settings.get_farming_number("inGameDaySeconds")
                * settings.get_farming_number("growMultiplier", 1.0))
        self.assertEqual(len(result["world"]["objectsArray"]), 61)
        for name, record in original.items():
            with self.subTest(name=name):
                self.assertEqual(record, items.get_item_by_name(name))
                self.assertFalse(record.get("terrainSet"))
                self.assertFalse(record.get("features"))
                self.assertFalse(record.get("requirements"))
                self.assertEqual(record["type"], october.PALETTE[name]["type"])
                if record["type"] == "tree":
                    self.assertEqual((record["growTime"], record["coinYield"]), ("2", "150"))
        self.assertEqual(original["xdm_luxurygardengazebo"]["code"], "2myo")
        self.assertEqual(original["giantmapleshadetree"]["code"], "lfm")
        self.assertEqual(original["giantxcd_goldenmapletree"]["code"], "2nop")
        self.assertEqual(original["pumpkinstack"]["code"], "2d84")


if __name__ == "__main__":
    unittest.main()
