"""Original quest score ladders, durable rewards and report replay boundaries."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_minion_round3_quests import QuestFixture, quest, task
import test_persistence as fixtures
import quests
import world_scores


class WorldScoreTests(QuestFixture):
    def setUp(self):
        super().setUp()
        self.stack.enter_context(mock.patch.object(world_scores, "_experiments", return_value={
            "fv_candy": 1, "fv_hallow": 1, "fv_xsa_master": 1, "fv_hawaii_coconuts_tuning": 0}))
        self.stack.enter_context(mock.patch.object(world_scores, "xp_to_level", return_value=15))

    def test_archive_contains_both_avalon_tracks_and_original_thresholds(self):
        tracks = world_scores._archive()[0]
        self.assertEqual(len(tracks), 65)  # 64 files/groups, Avalon contains two units.
        self.assertEqual(int(tracks["candyPoints"]["levels"][2]["required"]), 10)
        self.assertIn("avalon2Points", tracks)
        self.assertEqual(int(tracks["toylandPoints"]["levels"][149]["required"]), 136625)

    def test_missing_score_does_not_unlock_when_read_for_a_task(self):
        self.define(quest("level", [task("reachWorldScoreLevel", type_="candyPoints", level=2)]))
        self.activate("level")
        self.assertEqual(self.progress_of("level"), [0])
        self.assertNotIn("worldScores", self.save["userInfo"]["player"])

    def test_derived_level_progress_survives_reload_and_cannot_be_forged(self):
        self.define(quest("level", [task("reachWorldScoreLevel", type_="candyPoints", level=2)]))
        self.activate("level")
        world_scores.add_score(self.save, "candyPoints", 10)
        self.save = json.loads(json.dumps(self.save))
        self.assertEqual(self.progress_of("level"), [1])
        with self.assertRaises(ValueError):
            quests.increment_generic_farm_task(self.save, "reachWorldScoreLevel")

    def test_below_threshold_and_other_unit_leave_task_unfinished(self):
        self.define(quest("level", [task("reachWorldScoreLevel", type_="candyPoints", level=2)]))
        self.activate("level")
        self.save["userInfo"]["player"]["worldScores"] = {
            "candyPoints": {"score": 9, "level": 1}, "spook": {"score": 30, "level": 3}}
        self.assertEqual(self.progress_of("level"), [0])

    def test_exact_threshold_returns_actual_and_display_rewards_without_doubling(self):
        rewards = world_scores.add_score(self.save, "treasurePoints", 10)
        self.assertEqual(self.save["userInfo"]["player"]["worldScores"]["treasurePoints"],
                         {"score": 10, "level": 2})
        self.assertEqual([r["type"] for r in rewards], ["display_only", "item_grant"])
        self.assertEqual(rewards[0]["value"], rewards[1]["value"])

    def test_multi_level_grant_returns_each_crossed_level_once(self):
        expected = []
        for level in (2, 3, 4):
            expected.extend(world_scores._list(world_scores._level_data("candyPoints", level)["rewards"]["reward"]))
        rewards = world_scores.add_score(self.save, "candyPoints", 65)
        self.assertEqual([r["value"] for r in rewards], [r["value"] for r in expected])
        self.assertEqual(world_scores.world_level(self.save, "candyPoints"), 4)
        self.assertEqual(world_scores.add_score(self.save, "candyPoints", 0), [])

    def test_quest_completion_and_level_reports_cannot_award_twice(self):
        definition = quest("score", [task("plowPlot")])
        definition["rewards"] = [{"type": "world_score", "unit": "treasurePoints", "value": "10", "quantity": 99}]
        self.define(definition)
        self.activate("score", [1])
        with mock.patch.object(quests, "get_item_by_code", return_value={"name": "ladder-prize"}), \
                mock.patch.object(quests.storage, "store_deposit_item_by_name") as gift:
            self.assertTrue(quests.complete_quest(self.save, "score"))
            self.assertFalse(quests.complete_quest(self.save, "score"))
            saved = copy.deepcopy(self.save)
            world_scores.acknowledge_level_up("treasurePoints")
            world_scores.acknowledge_level_up("treasurePoints")
            self.assertEqual(self.save, saved)
            self.assertEqual(gift.call_count, 1)
            self.assertEqual(gift.call_args.args[2], 1)
        self.assertEqual(self.save["userInfo"]["player"]["worldScores"]["treasurePoints"]["score"], 10)

    def test_imported_extra_fields_and_other_score_tracks_are_preserved(self):
        self.save["userInfo"]["player"]["worldScores"] = {
            "candyPoints": {"score": 9, "level": 1, "unknown": ["keep"]},
            "zen": {"score": 25, "level": 3}}
        world_scores.add_score(self.save, "candyPoints", 1)
        self.assertEqual(self.save["userInfo"]["player"]["worldScores"]["candyPoints"]["unknown"], ["keep"])
        self.assertEqual(self.save["userInfo"]["player"]["worldScores"]["zen"], {"score": 25, "level": 3})

    def test_disabled_experiment_or_low_level_does_not_grant_like_the_client(self):
        before = copy.deepcopy(self.save)
        with mock.patch.object(world_scores, "_experiments", return_value={}):
            self.assertEqual(world_scores.add_score(self.save, "candyPoints", 10), [])
        with mock.patch.object(world_scores, "xp_to_level", return_value=14):
            self.assertEqual(world_scores.add_score(self.save, "candyPoints", 10), [])
        self.assertEqual(before, self.save)

    def test_original_polynomial_and_default_rewards_after_explicit_ladder(self):
        self.assertEqual(world_scores._level_data("spook", 31)["required"], 8119)
        row = world_scores._level_data("candyPoints", 51)
        self.assertEqual(row["required"], 48193)
        self.save["userInfo"]["player"]["worldScores"] = {"candyPoints": {"score": 33565, "level": 50}}
        rewards = world_scores.add_score(self.save, "candyPoints", row["required"] - 33565)
        self.assertEqual(world_scores.world_level(self.save, "candyPoints"), 51)
        self.assertEqual(next(r["value"] for r in rewards if r["type"] == "coins"), "5000")

    def test_unknown_unit_and_bad_amount_fail_before_mutation(self):
        before = copy.deepcopy(self.save)
        for unit, amount in (("unknown", 10), ("candyPoints", -1), ("candyPoints", True),
                             ("candyPoints", float("nan")), ("candyPoints", 1.25)):
            with self.subTest(unit=unit, amount=amount), self.assertRaises(ValueError):
                world_scores.add_score(self.save, unit, amount)
            self.assertEqual(before, self.save)
        with self.assertRaises(ValueError):
            world_scores.acknowledge_level_up({"unit": "candyPoints", "score": 1000})

    def test_imported_gain_buff_is_rejected_instead_of_silently_ignoring_it(self):
        self.save["userInfo"]["player"]["buffs"] = {"test-buff": 1}
        with mock.patch.object(world_scores, "get_item_by_name", return_value={
                "className": "BPermanentTypeGain", "subtype": "candyPoints_gain"}):
            with self.assertRaisesRegex(ValueError, "buff"):
                world_scores.add_score(self.save, "candyPoints", 10)

    def test_content_license_map_persists_without_unlocking_travel(self):
        self.save["userInfo"]["unlockedWorldTypes"] = ["farm"]
        world_scores.add_content_license(self.save, "farm", "world")
        world_scores.add_content_license(self.save, "hawaii", "world")
        world_scores.add_content_license(self.save, "hawaii", "world")
        reloaded = json.loads(json.dumps(self.save))
        self.assertEqual(reloaded["userInfo"]["unlockedWorldContentLicenses"],
                         {"farm": {"world": True}, "hawaii": {"world": True}})
        self.assertEqual(reloaded["userInfo"]["unlockedWorldTypes"], ["farm"])

    def test_world_currency_default_tuning_preserves_other_balances(self):
        self.save["userInfo"]["player"]["worldCurrencies"] = {
            "coconuts": {"total": 7, "purchased": 3}, "jade": {"total": 100}}
        quests._grant_rewards(self.save, {"name": "currency", "rewards": [{
            "type": "world_currency", "unit": "coconuts", "value": "20000", "quantity": 7}]})
        self.assertEqual(self.save["userInfo"]["player"]["worldCurrencies"], {
            "coconuts": {"total": 20007, "purchased": 3}, "jade": {"total": 100}})

    def test_world_currency_uses_served_original_inflow_variant(self):
        with mock.patch.object(world_scores, "_experiments", return_value={"fv_hawaii_coconuts_tuning": 1}):
            world_scores.add_currency(self.save, "coconuts", 100)
        self.assertEqual(self.save["userInfo"]["player"]["worldCurrencies"]["coconuts"]["total"], 85)

    def test_quest_cache_keeps_reward_unit_and_license_type(self):
        raw = b'''<questSettings><quest name="q"><tasks>
            <task action="reachWorldScoreLevel" type="spook" level="2" total="1"/>
            </tasks><rewards><reward type="world_score" value="10" unit="spook"/>
            <reward type="world_content_license" value="farm" licenseType="world"/>
            </rewards></quest></questSettings>'''
        decoded = quests._decode_quests(zlib.compress(raw))
        rewards = decoded["quests"]["q"]["rewards"]
        self.assertEqual(rewards[0]["unit"], "spook")
        self.assertEqual(rewards[1]["licenseType"], "world")
        self.assertTrue(quests._valid_quests_cache(decoded))
        del rewards[0]["unit"]
        self.assertFalse(quests._valid_quests_cache(decoded))


class WorldScoreWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    def setUp(self):
        fixtures.RuntimeFixtureTests.setUp(self)
        self.path = self.write_fixture()
        self.save = self.player.session("fixture-farmer")
        self.catalog = {}
        for name, value in (("_cached_quests", self.catalog), ("_startable_quests", []),
                            ("_replayable_chains", {}), ("_max_active_replayable_quests", 0)):
            patcher = mock.patch.object(quests, name, value)
            patcher.start(); self.addCleanup(patcher.stop)
        self.save["questState"] = {"active": {}, "completed": [], "retired": [], "replayed": {}}
        patcher = mock.patch.object(world_scores, "_experiments", return_value={"fv_xsa_master": 1})
        patcher.start(); self.addCleanup(patcher.stop)
        patcher = mock.patch.object(world_scores, "xp_to_level", return_value=15)
        patcher.start(); self.addCleanup(patcher.stop)

    def activate(self, name="score", unit="treasurePoints"):
        definition = quest(name, [task("plowPlot")])
        definition["rewards"] = [
            {"type": "coins", "value": "100", "quantity": 1},
            {"type": "world_score", "unit": unit, "value": "10", "quantity": 1},
            {"type": "world_currency", "unit": "coconuts", "value": "10000", "quantity": 1},
            {"type": "world_content_license", "value": "farm", "licenseType": "world", "quantity": 1},
        ]
        self.catalog[name] = definition
        self.save["questState"]["active"][name] = {"progress": [1], "new": 0}
        self.player.save_session("fixture-farmer")

    def test_completion_early_callback_retry_and_reload_have_one_durable_grant(self):
        self.activate()
        original_coins = self.save["userInfo"]["player"]["gold"]
        prize = world_scores._level_data("treasurePoints", 2)["rewards"]["reward"][1]
        result = self.gateway([
            self.command("UserService.updateWorldScoreLevelUp", ["treasurePoints"]),
            self.command("FarmQuestService.updateRecentlyCompletedQuests", ["score", False], 2),
            self.command("UserService.updateWorldScoreLevelUp", ["treasurePoints"], 3),
        ])
        fixtures.gateway_results(self, result, [0, 0, 0])
        saved = json.loads(self.path.read_text())
        player = saved["userInfo"]["player"]
        self.assertEqual(player["gold"], original_coins + 100)
        self.assertEqual(player["worldScores"]["treasurePoints"], {"score": 10, "level": 2})
        self.assertEqual(player["worldCurrencies"]["coconuts"]["total"], 10000)
        self.assertEqual(player["storageData"]["-1"][prize["value"]][0], 1)
        self.assertEqual(saved["userInfo"]["unlockedWorldContentLicenses"]["farm"], {"world": True})
        result = self.gateway([
            self.command("FarmQuestService.updateRecentlyCompletedQuests", ["score", False]),
            self.command("UserService.updateWorldScoreLevelUp", ["treasurePoints"], 2),
        ])
        fixtures.gateway_results(self, result, [0, 0])
        self.assertEqual(json.loads(self.path.read_text()), saved)
        self.player.load_saves()
        init = self.gateway([self.command("UserService.initUser", ["QA", 0, True, {}])])
        data = fixtures.gateway_results(self, init, [0])[0]["data"]
        self.assertEqual(data["userInfo"]["player"]["worldScores"]["treasurePoints"]["score"], 10)
        self.assertEqual(data["userInfo"]["player"]["worldCurrencies"]["coconuts"]["total"], 10000)
        self.assertTrue(data["userInfo"]["unlockedWorldContentLicenses"]["farm"]["world"])

    def test_invalid_score_reward_rolls_back_coins_and_quest_retirement(self):
        self.activate(unit="not-an-archived-score")
        before = self.path.read_bytes()
        result = self.gateway([self.command("FarmQuestService.updateRecentlyCompletedQuests", ["score", False])])
        fixtures.gateway_results(self, result, [29])
        self.assertEqual(self.path.read_bytes(), before)
        saved = self.player.session("fixture-farmer")
        self.assertIn("score", saved["questState"]["active"])
        self.assertNotIn("score", saved["questState"]["completed"])

    def test_forged_level_report_cannot_accept_amount_or_mutate_any_ledger(self):
        self.activate()
        before = self.path.read_bytes()
        result = self.gateway([
            self.command("UserService.updateWorldScoreLevelUp", ["treasurePoints", 999999]),
            self.command("UserService.updateWorldScoreLevelUp", ["unknown"], 2),
        ])
        fixtures.gateway_results(self, result, [29, 29])
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
