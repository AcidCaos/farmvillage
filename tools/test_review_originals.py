"""Synthetic tests for tools/review-originals.py. No network, no private input, no game files."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("review_originals_under_test", ROOT / "tools/review-originals.py")
review = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = review
spec.loader.exec_module(review)


def world(*names):
    return {"compare": "any", "requirement": [{"name": n, "className": "World"} for n in names]}


def decoration(code, *worlds, **fields):
    item = {"code": code, "name": "deco" + code, "type": "decoration", "cash": "5", "requirements": world(*worlds)}
    item.update(fields)
    return item


class PinTests(unittest.TestCase):
    def test_git_blob_matches_known_vectors(self):
        self.assertEqual(review.git_blob(b""), "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391")
        self.assertEqual(review.git_blob(b"hello\n"), "ce013625030ba8dba906f756967f9e9ca394464a")

    def test_verify_originals_accepts_exact_files_and_names_every_problem(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "a.bin").write_bytes(b"hello\n")
            (directory / "b.bin").write_bytes(b"tampered")
            (directory / "real.bin").write_bytes(b"x")
            (directory / "link.bin").symlink_to(directory / "real.bin")
            pins = {"files": [{"path": "a.bin", "bytes": 6, "gitBlob": review.git_blob(b"hello\n")},
                              {"path": "b.bin", "bytes": 6, "gitBlob": review.git_blob(b"hello\n")},
                              {"path": "missing.bin", "bytes": 1, "gitBlob": "0" * 40},
                              {"path": "link.bin", "bytes": 1, "gitBlob": review.git_blob(b"x")}]}
            self.assertEqual(review.verify_originals(directory, {"files": pins["files"][:1]}), [])
            self.assertEqual(review.verify_originals(directory, pins),
                             ["does not match its pin: b.bin", "missing: missing.bin", "missing: link.bin"])

    def test_the_real_pin_file_lists_44_relative_paths_that_stay_inside_the_folder(self):
        pins = review.load_pins()
        self.assertEqual(len(pins["files"]), 44)
        for entry in pins["files"]:
            path = Path(entry["path"])
            self.assertFalse(path.is_absolute() or ".." in path.parts, entry["path"])

    def test_fetch_refuses_a_used_folder_and_a_path_that_escapes(self):
        with tempfile.TemporaryDirectory() as temporary:
            used = Path(temporary) / "used"
            used.mkdir()
            (used / "keep").write_text("x")
            with self.assertRaises(review.ReviewError):
                review.fetch_originals(used, {"revision": "r", "files": []})
            for bad in ("../escape.bin", "/abs.bin"):
                with self.subTest(bad):
                    with self.assertRaises(review.ReviewError):
                        review.fetch_originals(Path(temporary) / "new", {"revision": "r", "files": [{"path": bad}]})
                    self.assertFalse((Path(temporary) / "escape.bin").exists())

    def test_results_are_refused_inside_the_checkout_and_main_stops_before_writing(self):
        with self.assertRaises(review.ReviewError):
            review.check_output_dir(ROOT / "anything")
        with self.assertRaises(review.ReviewError):
            review.check_output_dir(ROOT)
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(review.check_output_dir(Path(temporary) / "out"), (Path(temporary) / "out").resolve())
            target = ROOT / "tools" / "never-created-by-test"
            self.assertEqual(review.main(["--originals", temporary, "--out", str(target)]), 1)
            self.assertFalse(target.exists())


class ScreenTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            decoration("a", "hlights"),                                          # plain candidate
            decoration("b", "hlights", "htown"),                                 # already a Mistletoe item
            decoration("c", "hlights", requiredQuest="q1"),                      # a gate field blocks it
            decoration("d", "hlights", license="L"),                             # a gate field blocks it
            decoration("e", "hlights", purchasePrereqs=""),                      # an empty field does not block
            decoration("f", "hlights", prereqs=None),                            # None does not block
            {"code": "g", "name": "g", "type": "building", "className": "Special", "cash": "9",
             "requirements": world("hlights")},                                   # not an ordinary class
            decoration("h", "hlights", requirements={"requirement": [{"name": "hlights", "className": "World"},
                                                                    {"name": "q", "className": "Quest"}]}),  # foreign requirement
            decoration("i", "hlights", cash=None),                                # no own price
            decoration("j", "glen"),                                              # another world
            decoration("k"),                                                      # no world at all
            "not a record",
        ]

    def test_associated_means_the_requirements_name_the_world(self):
        rows, funnel = review.screen_world([r for r in self.records if isinstance(r, dict)], "hlights")
        self.assertEqual([r["code"] for r in rows], list("abcdefghi"))
        self.assertEqual(funnel["associated"], 9)

    def test_funnel_counts_each_stage_and_the_destination_split(self):
        rows, funnel = review.screen_world([r for r in self.records if isinstance(r, dict)], "hlights")
        self.assertEqual(funnel["ordinary_class"], 8)          # all but the special building
        self.assertEqual(funnel["ordinary_and_gate_free"], 6)  # a, b, e, f, h, i
        self.assertEqual(funnel["candidates"], 5)              # h has a foreign requirement
        self.assertEqual(funnel["candidates_already_in"]["htown"], 1)
        self.assertEqual(funnel["candidates_not_yet_in"]["htown"], 4)
        self.assertEqual(funnel["candidates_already_in"]["storybook"], 0)
        self.assertEqual(funnel["candidates_without_own_price"], 1)
        by_code = {r["code"]: r for r in rows}
        self.assertEqual(by_code["c"]["blocking_fields"], "requiredQuest")
        self.assertTrue(by_code["b"]["in_htown"] and not by_code["a"]["in_htown"])
        self.assertFalse(by_code["i"]["has_own_price"])
        self.assertTrue(by_code["h"]["foreign_requirement"])

    def test_date_windows_and_unbuyable_flags_are_counted_among_candidates_only(self):
        records = [decoration("a", "hlights", limitedStart="12/01/2011"),
                   decoration("b", "hlights", limitedEnd="01/06/2012", buyable="false"),
                   decoration("c", "hlights", buyable="true"),
                   decoration("d", "hlights", requiredQuest="q", limitedStart="12/01/2011", buyable="false")]  # blocked: not counted
        _, funnel = review.screen_world(records, "hlights")
        self.assertEqual(funnel["candidates"], 3)
        self.assertEqual(funnel["candidates_with_date_window"], 2)
        self.assertEqual(funnel["candidates_marked_not_buyable"], 1)

    def test_the_screen_uses_the_heritage_definitions_and_never_mutates_records(self):
        import copy
        records = [r for r in self.records if isinstance(r, dict)]
        snapshot = copy.deepcopy(records)
        review.screen_world(records, "hlights")
        self.assertEqual(records, snapshot)
        self.assertEqual(Path(review.hp.__file__).resolve(), ROOT / "FarmVillage/heritage_pricing.py", "definitions must come from the repo's own module")
        self.assertEqual(review.blocking_fields({"requiredMastery": "m", "experiment": ""}), ["requiredMastery"])


CRAFTING = b"""<crafting><recipes>
<CraftingRecipe id="r1"><name>one</name><craft>xhdcrafttype</craft><SkillLevelRequired>1</SkillLevelRequired>
 <InitialRecipeLevel>1</InitialRecipeLevel><Reward><OnMake recipeXp="1" playerXp="50"/><OnFinish itemCode="r1" sellQty="2" giftQty="1"/></Reward>
 <Ingredients><Ingredient itemCode="b1" quantityRequired="3"/><Ingredient itemCode="zz" quantityRequired="1"/></Ingredients>
 <Mastery sign="s1"/><MinutesToCook>360</MinutesToCook><RushCostCoins>-1</RushCostCoins><RushCostCash>5</RushCostCash><Deprecated>0</Deprecated></CraftingRecipe>
<CraftingRecipe id="r2"><name>two</name><craft>xhdcrafttype</craft><limitedStart>12/01/2011</limitedStart><limitedEnd>01/06/2012</limitedEnd>
 <Ingredients><Ingredient itemCode="b1" quantityRequired="1"/></Ingredients><MinutesToCook>60</MinutesToCook><Deprecated>1</Deprecated></CraftingRecipe>
<CraftingRecipe id="o1"><name>other</name><craft>otherskill</craft><Ingredients><Ingredient itemCode="x" quantityRequired="1"/></Ingredients></CraftingRecipe>
</recipes></crafting>"""


class RecipeTests(unittest.TestCase):
    def test_only_the_requested_craft_type_is_listed_with_names_windows_and_flags(self):
        rows = review.recipe_rows(CRAFTING, {"b1": "bushelone"}, admitted={"r1"})
        self.assertEqual([r["id"] for r in rows], ["r1", "r2"])
        one, two = rows
        self.assertEqual(one["ingredients"], "bushelone x3; zz x1", "an unknown code falls back to the code")
        self.assertEqual((one["sell_qty"], one["gift_qty"], one["player_xp"], one["mastery_sign"]), ("2", "1", "50", "s1"))
        self.assertEqual((one["minutes_to_cook"], one["rush_coins"], one["rush_cash"]), ("360", "-1", "5"))
        self.assertTrue(one["in_repo_set"] and not two["in_repo_set"])
        self.assertFalse(one["windowed"])
        self.assertTrue(two["windowed"])
        self.assertEqual((two["limited_start"], two["limited_end"], two["deprecated"]), ("12/01/2011", "01/06/2012", "1"))

    def test_related_item_codes_and_window_check(self):
        codes = review.recipe_item_codes(CRAFTING)
        self.assertEqual(codes, {"r1", "r2", "b1", "zz"})
        records = [{"code": "r1"}, {"code": "r2", "limitedStart": "12/01/2011"}, {"code": "b1", "limitedEnd": ""}]
        result = review.windowed_items(records, codes)
        self.assertEqual(result, {"checked": 4, "not_in_catalogue": ["zz"], "windowed": ["r2"]})

    def test_the_repo_recipe_set_is_read_from_source_without_importing_the_game(self):
        codes = review.repo_recipe_codes()
        self.assertEqual(len(codes), 17)
        self.assertIn("8WE", codes)
        with self.assertRaises(review.ReviewError):
            review.repo_recipe_codes("no-such-craft")


if __name__ == "__main__":
    unittest.main()
