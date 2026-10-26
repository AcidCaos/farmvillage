"""Recovered progression rewards stay exactly-once on detached preview saves."""
import copy
import unittest
from engine import CheatEngine, MAX_BALANCE
from test_engine import CATALOG, RULES, NOW, farm

TRACKS = [{"count": 10, "xp": 15, "coins": 100, "gift": "cow"},
          {"count": 25, "xp": 15, "coins": 200, "gift": "cow"},
          {"count": 50, "xp": 40, "coins": 300, "gift": "missing"}]
CATALOG_WITH_MASTERY = CATALOG + [{"name": "apple", "code": "AP", "type": "tree", "mastery": "true",
                                  "masteryLevel": TRACKS, "displayName": "Apple tree"}]
DEFINITIONS = {"ribbons": [{"name": "harvestanimals", "code": "A1", "displayName": "Animal whisperer", "levels": TRACKS},
                           {"name": "boughtbuildings", "code": "A2", "counterSource": "ownership", "levels": TRACKS}]}

class ProgressionToolsTests(unittest.TestCase):
    def setUp(self):
        self.engine = CheatEngine(CATALOG_WITH_MASTERY, RULES, progression=DEFINITIONS)
        self.tools = self.engine.progression
        self.save = farm()

    def advance(self, save=None, kind="mastery", code="AP", count=25):
        return self.engine.apply(self.save if save is None else save,
                                 {"type": "progression", "kind": kind, "code": code, "count": count}, NOW)

    def test_skipped_tiers_pay_original_rewards_once_with_level_cash_and_gift_metadata(self):
        original = copy.deepcopy(self.save)
        result = self.advance(); player = result["save"]["userInfo"]["player"]
        self.assertEqual((player["gold"], player["xp"], player["cash"]), (500, 30, 7))
        self.assertEqual(player["mastery"], {"AP": 1}); self.assertEqual(player["masteryCounters"], {"AP": 25})
        self.assertEqual(player["storageData"]["-1"]["CW"], [4, ["friend-1"], [{"color": "blue"}]])
        self.assertEqual(self.save, original)
        self.assertEqual(self.advance(result["save"])["changes"], [])

    def test_earned_imported_ledger_prevents_repeat_when_counter_is_lower(self):
        player = self.save["userInfo"]["player"]; player.update(mastery={"AP": 1}, masteryCounters={"AP": 0})
        after = self.advance()["save"]["userInfo"]["player"]
        self.assertEqual((after["gold"], after["xp"], after["cash"]), (200, 0, 5))
        self.assertEqual(after["storageData"], player["storageData"])

    def test_restore_previous_snapshot_restores_its_reward_ledger(self):
        first = self.advance()["save"]
        self.assertEqual(self.advance(copy.deepcopy(self.save))["save"], first)
        self.assertEqual(self.advance(first)["changes"], [])

    def test_backward_and_ownership_controls_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "only advance"): self.advance(self.advance()["save"], count=24)
        with self.assertRaisesRegex(ValueError, "ownership"): self.advance(kind="ribbon", code="A2")

    def test_malformed_nonempty_maps_stay_read_only_and_intact(self):
        for key, value in [("mastery", ["future-ledger"]), ("masteryCounters", "future-count-format")]:
            with self.subTest(key=key):
                save = farm(); save["userInfo"]["player"][key] = value
                self.assertFalse(self.tools.page(save, kind="mastery")["items"][0]["supported"])
                with self.assertRaisesRegex(ValueError, "Imported progress"): self.advance(save)
                self.assertEqual(save["userInfo"]["player"][key], value)

    def test_selected_kind_does_not_erase_other_maps_or_unique_records(self):
        self.save["userInfo"]["player"].update(achievements=["future-ledger"], achCounters="future-counts")
        self.save["progressionState"] = {"unique": {"animals": ["CW"]}, "future": [3]}
        result = self.advance()["save"]
        self.assertEqual(result["progressionState"], self.save["progressionState"])
        self.assertEqual(result["userInfo"]["player"]["achievements"], ["future-ledger"])
        self.assertEqual(result["userInfo"]["player"]["achCounters"], "future-counts")

    def test_missing_and_placeholder_rewards_never_create_invalid_inventory(self):
        result = self.advance(count=50)
        self.assertEqual(result["save"]["userInfo"]["player"]["mastery"]["AP"], 2)
        self.assertTrue(any("absent" in warning for warning in result["warnings"]))
        self.assertNotIn("missing", result["save"]["userInfo"]["player"]["storageData"]["-1"])
        catalog = CATALOG + [{"name": "invalidgifttrack", "code": "GT", "masteryLevel": [{"count": 1, "gift": "placeholder"}]}]
        after = CheatEngine(catalog, RULES).apply(self.save, {"type": "progression", "kind": "mastery", "code": "GT", "count": 1}, NOW)
        self.assertNotIn("XX", after["save"]["userInfo"]["player"]["storageData"]["-1"])

    def test_combined_gift_overflow_rejects_before_any_mutation(self):
        self.save["userInfo"]["player"]["storageData"]["-1"]["CW"][0] = MAX_BALANCE - 1
        original = copy.deepcopy(self.save)
        with self.assertRaisesRegex(ValueError, "Gift Box quantity"):
            self.tools.advance(self.save, {"kind": "mastery", "code": "AP", "count": 25}, self.engine, NOW, [])
        self.assertEqual(self.save, original)

    def test_balance_overflow_is_never_silently_truncated(self):
        for field in ("gold", "xp", "cash"):
            with self.subTest(field=field):
                save = farm(); save["userInfo"]["player"][field] = MAX_BALANCE
                with self.assertRaisesRegex(ValueError, "Flash balance limit"): self.advance(save)

    def test_paging_search_status_and_rows_are_detached(self):
        save = self.advance()["save"]; result = self.tools.page(save, q="apple", status="started", limit=1)
        self.assertEqual(result["total"], 1); self.assertEqual(result["items"][0]["earnedTier"], 2)
        result["items"][0]["tiers"][0]["count"] = 999
        self.assertEqual(self.tools.page(save, q="apple")["items"][0]["tiers"][0]["count"], 10)
        self.assertEqual(self.tools.page(save, status="available")["total"], 2)
        self.assertEqual(self.tools.totals(save)["mastery"]["earnedTiers"], 2)

    def test_bad_control_counts_and_out_of_range_imports_are_rejected(self):
        for count in [True, -1, 1.5, float("inf"), "25", MAX_BALANCE + 1]:
            with self.subTest(count=count), self.assertRaises(ValueError): self.advance(count=count)
        self.save["userInfo"]["player"]["mastery"] = {"AP": 99}
        self.assertFalse(self.tools.page(self.save, kind="mastery")["items"][0]["supported"])
        self.assertEqual(self.tools.totals(self.save)["mastery"]["earnedTiers"], 0)

    def test_ribbon_artwork_stays_with_its_category_and_colored_tier(self):
        definitions = copy.deepcopy(DEFINITIONS)
        definitions['ribbons'][0]['image'] = '/static/assets/progression/category.png'
        definitions['ribbons'][0]['levels'][0]['image'] = '/static/assets/progression/yellow.png'
        tools = CheatEngine(CATALOG_WITH_MASTERY, RULES, progression=definitions).progression
        row = tools.page(self.save, kind='ribbon', q='Animal whisperer')['items'][0]
        self.assertEqual(row['image'], '/static/assets/progression/category.png')
        self.assertEqual(row['tiers'][0]['image'], '/static/assets/progression/yellow.png')
        self.assertEqual(row['nextTier']['image'], row['tiers'][0]['image'])

if __name__ == "__main__": unittest.main()
