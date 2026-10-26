"""Offline regressions for ribbons/mastery using the original award catalog."""

from contextlib import ExitStack, redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence  # noqa: F401  Loads first so FARMVILLAGE_DATA_DIR is set before product modules resolve paths.

import commands
import game_settings
import items
import peaceful
import progression
import version


class ProgressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The authoritative, archived thresholds/rewards, not test substitutes.
        cls.settings = game_settings._decode_game_settings((ROOT / "xml/gz/v855098/gameSettings.xml.gz").read_bytes())
        cls.initial = json.loads((ROOT / "villages/initial.json").read_text())
        cls.catalog = [
            {"name": "strawberry", "code": "SB", "type": "seed", "subtype": "fruit", "cost": "10",
             "coinYield": "35", "plantXp": "1", "growTime": "0.174", "mastery": "true", "masteryYield": "1",
             "masteryLevel": [{"count": "500", "xp": "25", "coins": "500"},
                               {"count": "1500", "xp": "75", "coins": "1500"},
                               {"count": "5250", "xp": "250", "coins": "5000", "gift": "masterstrawberries"}]},
            {"name": "cow", "code": "CW", "type": "animal", "coinYield": "6", "mastery": "true", "masteryYield": "1",
             "masteryLevel": [{"count": "5", "xp": "25", "coins": "500"},
                               {"count": "13", "xp": "75", "coins": "1500"},
                               {"count": "30", "xp": "250", "coins": "5000", "gift": "mastercow"}]},
            {"name": "resttent", "code": "RT", "type": "building", "cost": "1000"},
            {"name": "haybale", "code": "HB", "type": "decoration", "subtype": "haybale", "cost": "100"},
            {"name": "mastercow", "code": "MC", "type": "decoration"},
            {"name": "masterstrawberries", "code": "MS", "type": "decoration"},
        ]

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for module, key, value in (
            (game_settings, "_cached_game_settings", self.settings),
            (game_settings, "_cached_farming", {}),
            (game_settings, "_xp_level_map", None),
            (game_settings, "_level_xp_map", None),
            (items, "_cached_items", {"settings": {"items": {"item": self.catalog}}}),
        ):
            self.stack.enter_context(mock.patch.object(module, key, value))
        game_settings._xp_level_map_init()
        self.save = copy.deepcopy(self.initial)
        self.save["world"]["objectsArray"] = []
        self.player = self.save["userInfo"]["player"]
        self.player.update(gold=100000, xp=0, cash=0, achievements=[], achCounters=None, mastery={}, masteryCounters={}, storageData={})
        self.stack.enter_context(mock.patch.object(commands, "session", return_value=self.save))
        self.now = 2_000_000_000
        self.stack.enter_context(mock.patch.object(commands, "timestamp_now", return_value=self.now))
        self.stack.enter_context(mock.patch.object(commands.quests, "record_action"))
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        progression.ensure_state(self.save)

    def item(self, name):
        return items.get_item_by_name(name)

    def plot(self, ident=1):
        # Explicitly ripe under the real catalog growth rule; these tests
        # exercise award delivery and retry accounting after legal harvests.
        planted = (self.now - peaceful.grow_seconds(self.item("strawberry")) - 1) * 1000
        return {"id": ident, "className": "Plot", "itemName": "strawberry", "state": "grown", "plantTime": planted}

    def test_original_catalog_ribbon_awards_once_and_uses_client_goal_shape(self):
        self.player["achCounters"]["A005"] = 29
        gold, xp = self.player["gold"], self.player["xp"]
        progression.record_harvest(self.save, self.item("strawberry"))
        response = progression.take_response(self.save)
        self.assertEqual(self.player["achievements"]["A005"], 0)
        self.assertEqual(self.player["gold"], gold + 500)
        self.assertEqual(self.player["xp"], xp + 25)
        self.assertIn({"type": "Achievement", "code": "A005", "difficulty": 0, "link": "", "updateHud": True}, response["goals"])
        self.assertIn({"type": "Achievement", "code": "A005", "count": 30}, response["goalCounters"])
        progression.set_ribbon_count(self.save, "harvestcrops", 30)
        self.assertEqual(progression.take_response(self.save), {})
        self.assertEqual(self.player["gold"], gold + 500)

    def test_crossing_all_ribbon_tiers_pays_each_original_reward_once(self):
        gold = self.player["gold"]
        progression.set_ribbon_count(self.save, "harvestcrops", 25000)
        goals = progression.take_response(self.save)["goals"]
        self.assertEqual([goal["difficulty"] for goal in goals], [0, 1, 2, 3])
        self.assertEqual(self.player["gold"], gold + 18000)
        self.assertEqual(self.player["xp"], 425)
        progression.set_ribbon_count(self.save, "harvestcrops", 25001)
        self.assertNotIn("goals", progression.take_response(self.save))

    def test_mastery_uses_cumulative_harvest_counts_and_final_gift(self):
        self.player["masteryCounters"]["CW"] = 4
        progression.record_harvest(self.save, self.item("cow"))
        response = progression.take_response(self.save)
        self.assertEqual(self.player["mastery"]["CW"], 0)
        self.assertIn({"type": "Mastery", "code": "CW", "count": 5}, response["goalCounters"])
        self.player["masteryCounters"]["CW"] = 29
        progression.record_harvest(self.save, self.item("cow"))
        goals = [goal for goal in progression.take_response(self.save)["goals"] if goal["type"] == "Mastery"]
        self.assertEqual([goal["difficulty"] for goal in goals], [1, 2])
        self.assertEqual(self.player["storageData"]["-1"]["MC"], [1, [], []])
        progression.record_harvest(self.save, self.item("cow"))
        self.assertEqual(self.player["storageData"]["-1"]["MC"][0], 1)

    def test_unique_gifts_and_harvest_types_do_not_count_the_same_item_twice(self):
        for _ in range(3):
            progression.record_gift(self.save, self.item("cow"))
            progression.record_harvest(self.save, self.item("strawberry"))
        self.assertEqual(self.player["achCounters"]["A015"], 1)
        self.assertEqual(self.player["achCounters"]["A012"], 1)
        self.assertEqual(self.player["achCounters"]["A005"], 3)

    def test_ribbon_gift_and_coin_reward_are_persisted_together(self):
        progression.record_coins(self.save, earned=750, spent=2500)
        self.assertEqual(self.player["storageData"]["-1"]["HB"][0], 1)
        self.assertEqual(self.player["storageData"]["-1"]["RT"][0], 1)
        progression.take_response(self.save)
        restored = json.loads(json.dumps(self.save))
        before = copy.deepcopy(restored["userInfo"]["player"])
        progression.record_coins(restored)
        self.assertEqual(progression.take_response(restored), {})
        self.assertEqual(restored["userInfo"]["player"], before)

    def test_owned_ribbon_counts_follow_real_world_and_removal_keeps_earned_level(self):
        self.save["world"]["objectsArray"] = [
            {"id": n, "className": "Building", "itemName": "resttent"} for n in (1, 2)]
        progression.refresh_owned(self.save)
        self.assertEqual(self.player["achCounters"]["A008"], 2)
        self.assertEqual(self.player["achievements"]["A008"], 0)
        self.assertEqual(self.player["stats"]["buildings"], 2)
        progression.take_response(self.save)
        self.save["world"]["objectsArray"].pop()
        progression.refresh_owned(self.save)
        self.assertEqual(self.player["achCounters"]["A008"], 1)
        self.assertEqual(self.player["achievements"]["A008"], 0)
        self.assertNotIn("goals", progression.take_response(self.save))

    def test_world_harvest_retry_does_not_duplicate_income_progress_or_rewards(self):
        plot = self.plot()
        self.save["world"]["objectsArray"].append(plot)
        self.player["achCounters"]["A005"] = 29
        snapshot = {**plot, "state": "fallow"}
        gold = self.player["gold"]
        commands.world_perform_action("test", "harvest", snapshot, [])
        first = commands.progression_response("test")
        commands.world_perform_action("test", "harvest", snapshot, [])
        self.assertEqual(commands.progression_response("test"), {})
        self.assertEqual(self.player["gold"], gold + 35 + 500)
        self.assertEqual(self.player["achCounters"]["A005"], 30)
        self.assertEqual(self.player["achCounters"]["A003"], 35)
        self.assertEqual(len(first["goals"]), 1)

    def test_equipment_puts_goals_and_counters_on_each_client_subresponse(self):
        self.save["world"]["objectsArray"] = [self.plot(1), self.plot(2)]
        self.player["achCounters"]["A005"] = 29
        responses = commands.equipment_use("test", "harvest", [{"id": 1}, {"id": 2}], "strawberry", {})
        self.assertEqual(responses[0]["goals"][0]["code"], "A005")
        self.assertNotIn("goals", responses[1])
        for response, count in zip(responses, (30, 31)):
            self.assertEqual(response["errorType"], 0)
            self.assertIn({"type": "Achievement", "code": "A005", "count": count}, response["goalCounters"])
            self.assertNotIn("_progressionResponse", response["data"])
        self.assertEqual(commands.progression_response("test"), {})

    def test_daily_stats_telemetry_does_not_count_a_harvest_again(self):
        progression.record_harvest(self.save, self.item("strawberry"))
        progression.take_response(self.save)
        commands.increment_daily_counter("test", "DailyStats", "crop", "harvest", 1, "2026-10-21")
        self.assertEqual(self.player["achCounters"]["A005"], 1)
        self.assertEqual(self.save["dailyStats"]["DailyStats:crop:harvest:2026-10-21"], 1)
        self.assertEqual(commands.progression_response("test"), {})

    def test_migration_preserves_legitimate_all_one_mastery_maps(self):
        self.player["mastery"] = {"CW": 1}
        self.player["masteryCounters"] = {"SB": 1}
        version.migrate_loaded_save(self.save)
        self.assertEqual(self.player["mastery"], {"CW": 1})
        self.assertEqual(self.player["masteryCounters"], {"SB": 1})
        self.assertIsInstance(self.player["achievements"], dict)
        self.assertIsInstance(self.player["achCounters"], dict)

    def test_save_snapshot_keeps_progress_but_excludes_transient_notifications(self):
        import player
        progression.set_ribbon_count(self.save, "harvestcrops", 30)
        snapshot = player._save_contents(self.save)
        self.assertNotIn("_progressionResponse", snapshot)
        self.assertEqual(snapshot["userInfo"]["player"]["achievements"]["A005"], 0)
        self.assertEqual(snapshot["userInfo"]["player"]["achCounters"]["A005"], 30)
        self.assertIn("_progressionResponse", self.save)

    def test_init_snapshot_does_not_alias_pending_goals_into_two_amf_locations(self):
        # Ruffle cannot decode a reference to an AMF object which itself was
        # encoded as a reference. Embedding the transient queue in init data
        # and then reusing its goal objects in the envelope creates that case.
        with mock.patch.object(commands.quests, "start_session"), \
             mock.patch.object(commands, "neighbor_uids", return_value=[]), \
             mock.patch.object(commands, "neighbor_metadata", return_value=[]):
            data = commands.init_user("test")
        response = commands.progression_response("test")
        self.assertNotIn("_progressionResponse", data)
        self.assertIn("goalCounters", response)

        def container_ids(value):
            if isinstance(value, dict):
                return {id(value)}.union(*(container_ids(v) for v in value.values()))
            if isinstance(value, list):
                return {id(value)}.union(*(container_ids(v) for v in value))
            return set()

        self.assertFalse(container_ids(data) & container_ids(response))
        import pyamf
        encoded = pyamf.encode({"data": data, **response}, encoding=pyamf.AMF0).getvalue()
        decoded = next(pyamf.decode(encoded, encoding=pyamf.AMF0))
        self.assertNotIn("_progressionResponse", decoded["data"])
        self.assertTrue(all(counter["type"] == "Achievement" for counter in decoded["goalCounters"]))


if __name__ == "__main__":
    unittest.main()
