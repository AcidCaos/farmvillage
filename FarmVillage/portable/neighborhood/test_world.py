"""Geometry and archive contracts for the detached authored neighbourhood."""

import copy
import importlib.util
import json
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest


spec = importlib.util.spec_from_file_location("build_world", Path(__file__).with_name("build_world.py"))
world = importlib.util.module_from_spec(spec)
spec.loader.exec_module(world)


class WorldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.initial, cls.initial_bytes, cls.catalog = world.load_inputs()
        cls.layouts = world.grand_layouts(cls.catalog)

    def test_all_five_farms_have_legal_ground_and_visual_reservations(self):
        self.assertEqual(set(self.layouts), {resident["key"] for resident in world.RESIDENTS})
        for key, layout in self.layouts.items():
            with self.subTest(resident=key):
                self.assertTrue(200 <= len(layout.objects) <= 400)
                self.assertEqual(layout.size, 90)
                self.assertEqual(world.validate_layout(layout.objects, self.catalog, size=90)["overlaps"], 0)
                self.assertEqual(world.validate_layout(layout.objects, self.catalog, size=90, visual=False)["overlaps"], 0)

    def test_collision_checker_catches_duplicates_bad_z_bounds_and_real_overlap(self):
        original = self.layouts["poppy"].objects
        bad = copy.deepcopy(original)
        bad.append(copy.deepcopy(bad[0]))
        with self.assertRaisesRegex(ValueError, "duplicate.*ID.*overlap"):
            world.validate_layout(bad, self.catalog, size=90)
        for axis, value, expected in (("z", 2, "ground position"), ("x", -20, "out of bounds")):
            bad = copy.deepcopy(original)
            bad[0]["position"][axis] = value
            with self.assertRaisesRegex(ValueError, expected):
                world.validate_layout(bad, self.catalog, size=90)

    def test_missing_tree_dimensions_and_rotation_follow_recovered_client_rules(self):
        self.assertEqual(world.item_size({}, "static"), (1, 1))
        self.assertEqual(world.item_size({"sizeX": "0", "sizeY": "0"}, "static"), (1, 1))
        self.assertEqual(world.item_size(self.catalog["fencewhite"], "vertical"), (1, 5))
        tree = next(obj for obj in self.layouts["poppy"].objects if obj["className"] == "Tree")
        self.assertEqual(tree["state"], "ripe")
        box = world.footprint(tree, self.catalog, visual=True)
        self.assertGreaterEqual(box[2] - box[0], 5)
        self.assertGreaterEqual(box[3] - box[1], 5)

    def test_default_avatar_spawn_is_clear_on_every_resident_farm(self):
        for key, layout in self.layouts.items():
            for obj in layout.objects:
                self.assertFalse(world.boxes_intersect((44, 44, 46, 46), world.footprint(obj, self.catalog, visual=True)),
                                 f"{key}: {obj['itemName']} obstructs the default avatar spawn")

    def test_themed_farms_are_distinct_and_hanks_corral_has_a_visitor_gate(self):
        items = {key: [obj["itemName"] for obj in layout.objects] for key, layout in self.layouts.items()}
        self.assertIn("sunflowers", items["poppy"])
        self.assertIn("dogwoodtreepink", items["poppy"])
        self.assertIn("honeybeesflowerpatch", items["poppy"])
        self.assertGreater(sum(obj["className"] == "Plot" for obj in self.layouts["hank"].objects), 160)
        self.assertGreater(sum(obj["className"] == "Animal" for obj in self.layouts["mabel"].objects), 60)
        self.assertIn("pumpkin", items["hazel"])
        self.assertGreaterEqual(sum(obj["className"] == "Plot" for obj in self.layouts["ben"].objects), 40)
        blocked = {(obj["position"]["x"], obj["position"]["y"])
                   for obj in self.layouts["hank"].objects if obj["itemName"] == "haybale"}
        reached, todo = set(), [(45, 45)]
        while todo:
            point = todo.pop()
            if point in reached or point in blocked: continue
            x, y = point
            if not 0 <= x < 90 or not 0 <= y < 90: continue
            reached.add(point)
            todo.extend([(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)])
        self.assertEqual(len(blocked), 22)
        self.assertNotIn((48, 45), blocked)
        self.assertNotIn((48, 46), blocked)
        self.assertIn((2, 2), reached)

    def test_passable_original_paths_and_estate_wing_reachability(self):
        for key, layout in self.layouts.items():
            self.assertFalse(any(obj["itemName"] == "stonepath" for obj in layout.objects))
            paths = [obj for obj in layout.objects if obj["className"] == "MaskedDecoration"]
            self.assertGreater(len(paths), 50)
            for obj in paths:
                self.assertEqual(self.catalog[obj["itemName"]]["collision"], {"r": ["HH", "HH"]})
            result = world.walkability(layout, self.catalog)
            self.assertEqual(result["defaultSpawn"], [45, 45])
            self.assertTrue(result["allFourEstateCornersReachable"])

    def test_residents_are_exact_level70_ultrarich_and_use_original_expansion(self):
        self.assertEqual(world.resident_xp(), 433000)
        self.assertEqual(self.catalog["farm22"]["squares"], "90")
        for resident in world.RESIDENTS:
            key = resident["key"]
            save = world.make_save(self.initial, key, resident["name"], 1792612800,
                                   catalog=self.catalog, layout=self.layouts[key], gender=resident["gender"])
            self.assertEqual([save["userInfo"]["player"][field] for field in ("xp", "gold", "cash")], [433000, 20000000, 100000])
            self.assertTrue(433000 <= save["userInfo"]["player"]["xp"] < 443500)
            self.assertEqual([save["world"][field] for field in ("sizeX", "sizeY")], [90, 90])

    def test_fresh_player_preserves_original_seven_object_tutorial_and_balances(self):
        save = world.make_save(self.initial, "player", "Farmer", 1792612800, catalog=self.catalog)
        self.assertEqual(len(save["world"]["objectsArray"]), 7)
        self.assertEqual([save["userInfo"]["player"][key] for key in ("xp", "gold", "cash")], [0, 200, 5])
        self.assertTrue(save["userInfo"]["is_new"])
        self.assertEqual(save["flashHotParams"]["ZYNGA_USER_ID"], save["userInfo"]["player"]["userId"])
        self.assertEqual(self.initial["userInfo"]["player"]["userId"], None)
        self.assertIsNone(save["userInfo"]["avatar"])

    def test_resident_avatars_have_complete_distinct_authored_appearance_kits(self):
        appearances = []
        for resident in world.RESIDENTS:
            save = world.make_save(self.initial, resident["key"], resident["name"], 1792612800,
                                   catalog=self.catalog, layout=self.layouts[resident["key"]], gender=resident["gender"])
            avatar = save["userInfo"]["avatar"]
            self.assertEqual(avatar["gender"], resident["gender"])
            self.assertEqual(save["userInfo"]["attr"]["profilePic"], world.PROFILE_ICONS[resident["key"]])
            image = (world.ROOT / "LocalData" / save["userInfo"]["attr"]["profilePic"].removeprefix("/")).read_bytes()
            self.assertTrue(image.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(struct.unpack(">II", image[16:24]), (48, 48))
            self.assertTrue({"body", "face", "hair", "eyes", "shirt", "pants", "shoes"} <= avatar["items"].keys())
            self.assertEqual(set(save["avatarState"]["unlocked"]), {entry["itemId"] for entry in avatar["items"].values()})
            appearances.append(json.dumps(avatar, sort_keys=True))
        self.assertEqual(len(set(appearances)), 5)

    def test_archive_contains_only_six_saves_manifest_and_exact_accepted_initial(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            manifest = world.build(output, now=1792612800)
            self.assertEqual(len(manifest["saveFiles"]), 6)
            self.assertEqual(len(set(manifest["saveFiles"])), 6)
            self.assertEqual((output / "world/neighborhood/templates/initial.json").read_bytes(), self.initial_bytes)
            archive_path = output / "farmvillage-fresh-world.tar.gz"
            with tarfile.open(archive_path) as archive:
                self.assertEqual(len(archive.getmembers()), 8)
                self.assertTrue(all(member.isfile() and member.name.startswith("world/") for member in archive))
            for uid, filename in manifest["saveFiles"].items():
                path = output / "world/saves" / filename
                self.assertEqual(world.sha(path.read_bytes()), manifest["saveSha256"][filename])
                self.assertEqual(json.loads(path.read_text())["userInfo"]["player"]["userId"], uid)
            with self.assertRaisesRegex(ValueError, "already exists"):
                world.build(output, now=1792612800)


if __name__ == "__main__":
    unittest.main()
