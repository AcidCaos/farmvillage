"""Exact derived Glen pixie removal, portable before world activation."""
import copy
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]
import test_persistence as fixtures  # Synthetic paths before bundle imports.
import items
import themed_market_presentation as policy
import themed_worlds as tw

EXPECTED_SEED_CODES = {
    "ambrosiatulip": "aur", "boggartbulb": "UhP", "butterflyrose": "qJ0",
    "darkdahlia": "avJ", "dreamcotton": "avE", "elfintea": "auj",
    "fairyfoxglove": "dug", "goblinvine": "avF", "gossamerivy": "avA",
    "honeymelon": "avk", "nectarkin": "al1", "pixieberry": "atH",
}
REVIEWED_GLEN_SPEC = {
    "name": "Enchanted Glen", "prefix": "xeg", "storageId": -18,
    "xmlStorageId": None, "xmlPrefix": None, "xmlTheme": None,
    "theme": "glen_theme", "localThemeChoice": True,
    "landGatePrefixes": ("fv_glen_farm", "fv_xeg_farm"),
}


class GlenHarvestScoreProjectionTests(unittest.TestCase):
    # Reuse setup only; do not inherit unrelated persistence test methods.
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)

    @staticmethod
    def seed(name="ambrosiatulip"):
        return copy.deepcopy(items.get_item_by_name(name))

    def test_exact_twelve_raw_records_and_original_reward_shapes(self):
        raw = policy._raw_items()
        selected = [row for row in raw if row.get("name") in EXPECTED_SEED_CODES]
        self.assertEqual(len(selected), 12)
        self.assertEqual({row["name"]: row["code"] for row in selected}, EXPECTED_SEED_CODES)
        self.assertEqual(policy.GLEN_SCORE_SEEDS, frozenset(EXPECTED_SEED_CODES))
        for row in selected:
            with self.subTest(seed=row["name"]):
                self.assertEqual(row["type"], "seed")
                self.assertEqual(row["requirements"], {"compare": "any", "requirement":
                                 {"className": "World", "name": "glen"}})
                self.assertEqual(row["harvestYield"], {"className": "QuestRewardHarvestYield",
                    "type": "world_score", "unit": "pixie", "value": "2",
                    "class": row["name"], "phylum": "harvest"})
                self.assertEqual(items.get_item_by_name(row["name"]), row)

    def test_only_harvest_yield_is_removed_from_copied_records(self):
        source = Path(items.ITEMS_AMF)
        source_before = source.read_bytes()
        server_before = {name: copy.deepcopy(items.get_item_by_name(name)) for name in EXPECTED_SEED_CODES}
        specs_before = copy.deepcopy(tw.SPECS)
        with mock.patch.dict(tw.SPECS, {"glen": copy.deepcopy(REVIEWED_GLEN_SPEC)}):
            for name, original in server_before.items():
                with self.subTest(seed=name):
                    row = self.seed(name)
                    expected = copy.deepcopy(original)
                    expected.pop("harvestYield")
                    projected = policy._without_glen_harvest_score(row)
                    self.assertEqual(projected, expected)
                    self.assertEqual(row, original)
                    self.assertIsNot(projected, row)
                    # Deep copying protects retained nested images/mastery data.
                    projected["image"][0]["url"] = "derived-only"
                    self.assertEqual(row, original)
        self.assertEqual(tw.SPECS, specs_before)
        self.assertEqual({name: items.get_item_by_name(name) for name in EXPECTED_SEED_CODES}, server_before)
        self.assertEqual(source.read_bytes(), source_before)

    def test_projection_is_idempotent_and_missing_reward_keeps_object_identity(self):
        with mock.patch.dict(tw.SPECS, {"glen": copy.deepcopy(REVIEWED_GLEN_SPEC)}):
            for name in EXPECTED_SEED_CODES:
                with self.subTest(seed=name):
                    row = self.seed(name)
                    row.pop("harvestYield")
                    before = copy.deepcopy(row)
                    self.assertIs(policy._without_glen_harvest_score(row), row)
                    self.assertEqual(row, before)
                    projected = policy._without_glen_harvest_score(self.seed(name))
                    self.assertIs(policy._without_glen_harvest_score(projected), projected)

    def test_every_reward_field_drift_and_extra_fields_fail_without_mutation(self):
        with mock.patch.dict(tw.SPECS, {"glen": copy.deepcopy(REVIEWED_GLEN_SPEC)}):
            for name in EXPECTED_SEED_CODES:
                for key in ("className", "type", "unit", "value", "class", "phylum", "extra"):
                    with self.subTest(seed=name, field=key):
                        row = self.seed(name)
                        row["harvestYield"][key] = "unreviewed"
                        before = copy.deepcopy(row)
                        with self.assertRaisesRegex(ValueError, "harvest-score reward"):
                            policy._without_glen_harvest_score(row)
                        self.assertEqual(row, before)

    def test_missing_reward_fields_and_nonmapping_rewards_fail_without_mutation(self):
        with mock.patch.dict(tw.SPECS, {"glen": copy.deepcopy(REVIEWED_GLEN_SPEC)}):
            row = self.seed()
            reward = row["harvestYield"]
            malformed = [None, [], [reward], "pixie", 2, {}]
            malformed += [{key: value for key, value in reward.items() if key != missing} for missing in reward]
            for value in malformed:
                with self.subTest(reward=value):
                    candidate = dict(row, harvestYield=copy.deepcopy(value))
                    before = copy.deepcopy(candidate)
                    with self.assertRaisesRegex(ValueError, "harvest-score reward"):
                        policy._without_glen_harvest_score(candidate)
                    self.assertEqual(candidate, before)

    def test_wrong_type_and_mixed_world_owners_fail_without_mutation(self):
        with mock.patch.dict(tw.SPECS, {"glen": copy.deepcopy(REVIEWED_GLEN_SPEC)}):
            mixed = {"compare": "any", "requirement": [
                {"className": "World", "name": "glen"}, {"className": "World", "name": "farm"}]}
            for changes in ({"type": "tree"}, {"type": None}, {"requirements": mixed}):
                with self.subTest(changes=changes):
                    row = dict(self.seed(), **copy.deepcopy(changes))
                    before = copy.deepcopy(row)
                    with self.assertRaisesRegex(ValueError, "harvest-score owner"):
                        policy._without_glen_harvest_score(row)
                    self.assertEqual(row, before)

    def test_home_other_worlds_and_unknown_seed_names_keep_all_rewards(self):
        with mock.patch.dict(tw.SPECS, {"glen": copy.deepcopy(REVIEWED_GLEN_SPEC)}):
            rows = [copy.deepcopy(items.get_item_by_name("strawberry")),
                    dict(self.seed(), name="unreviewed-glen-seed")]
            for world in ("farm", "rainforest", "atlantis"):
                rows.append(dict(self.seed(), requirements={"requirement": {"className": "World", "name": world}}))
            for row in rows:
                with self.subTest(name=row["name"], requirements=row.get("requirements")):
                    row["harvestYield"] = {"type": "world_score", "unit": "pixie", "preserve": [1]}
                    before = copy.deepcopy(row)
                    self.assertIs(policy._without_glen_harvest_score(row), row)
                    self.assertEqual(row, before)

    def test_absent_glen_spec_is_a_noop_even_for_malformed_reward(self):
        specs_before = copy.deepcopy(tw.SPECS)
        without_glen = {name: spec for name, spec in tw.SPECS.items() if name != "glen"}
        with mock.patch.dict(tw.SPECS, without_glen, clear=True):
            self.assertNotIn("glen", tw.SPECS)
            for name in EXPECTED_SEED_CODES:
                for value in (self.seed(name)["harvestYield"], {"malformed": True}):
                    with self.subTest(seed=name, reward=value):
                        row = dict(self.seed(name), harvestYield=copy.deepcopy(value))
                        before = copy.deepcopy(row)
                        self.assertIs(policy._without_glen_harvest_score(row), row)
                        self.assertEqual(row, before)
        self.assertEqual(tw.SPECS, specs_before)


if __name__ == "__main__":
    unittest.main()
