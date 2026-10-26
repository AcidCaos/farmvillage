"""Restored English Countryside Stage 1 contracts; disposable saves only.

The original IDs and observed objectives are deliberate assertions here. All
catalog writes and runtime paths remain isolated by test_persistence.
"""
from contextlib import ExitStack, redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence  # Resolve writable paths before product imports.
from test_minion_round3_quests import new_save, quest, task
import england_progression
import quests
import storage


IDS = tuple(f"england-02-{suffix}" for suffix in ("001", "002", "003", "004", "005", "007"))
OBJECTIVES = (
    (("useItemByCode", "kf", 6), ("plowPlot", "", 10)),
    (("completeConstructionBuildingByCode", "ko", 1), ("harvestByCode", "qe", 25)),
    (("buyItemByCode", "ct", 1), ("visitNeighbor", "", 6), ("simpleAction", "viewQuestMap", 1)),
    (("completeConstructionBuildingByCode", "ct", 1), ("buyItemByCode", "vj", 8), ("expandFarm", "xukfarm14", 1)),
    (("buyItemByCode", "SH", 1),),
    (("buyItemByCode", "cy", 1), ("completeConstructionBuildingByCode", "cy", 1)),
)


class EnglandProgressionTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.stack.enter_context(mock.patch.object(england_progression, "STORY_ENABLED", True))
        self.catalog = copy.deepcopy(england_progression.quest_definitions())
        self.stack.enter_context(mock.patch.object(quests, "_cached_quests", self.catalog))
        self.stack.enter_context(mock.patch.object(quests, "_replayable_chains", {}))
        self.stack.enter_context(mock.patch.object(quests, "_max_active_replayable_quests", 0))
        self.stack.enter_context(mock.patch.object(quests, "_item_categories", {}))
        self.stack.enter_context(mock.patch.object(quests, "_player_level", return_value=20))
        self.stack.enter_context(mock.patch("engine.xp_to_level", return_value=20))
        self.stack.enter_context(mock.patch("engine.level_to_xp", return_value=100000))
        self.stack.enter_context(mock.patch("engine.get_farming_int", return_value=250))
        self.stack.enter_context(mock.patch.object(quests, "get_item_by_code", side_effect=lambda code: {
            "name": f"item_{code}", "code": code,
        }))
        self.stack.enter_context(mock.patch.object(quests, "get_item_by_name", side_effect=lambda name: {
            "name": name, "squares": "58",
        }))
        self.deposits = self.stack.enter_context(mock.patch.object(
            storage, "store_deposit_item_by_name", side_effect=self.deposit))
        self.reindex()
        self.save = new_save()
        self.save["userInfo"]["currentWorldType"] = "england"
        self.save["userInfo"]["player"]["seenFlags"] = {}
        self.save["testGiftbox"] = {}

    def reindex(self):
        self.stack.enter_context(mock.patch.object(quests, "_startable_quests", sorted(
            (name for name, definition in self.catalog.items() if quests._quest_is_startable(definition)),
            key=quests._assignment_order)))

    def deposit(self, save, name, amount=1, *, group=storage.HOME_INVENTORY_ID, **_):
        self.assertEqual(group, storage.GIFTBOX_ID)
        gifts = save.setdefault("testGiftbox", {})
        gifts[name] = gifts.get(name, 0) + amount
        return True

    def activate(self, name, progress=None):
        self.save["questState"]["active"][name] = {
            "progress": list(progress) if progress is not None else [0] * len(self.catalog[name]["tasks"]),
            "new": quests.NEW_QUEST,
        }

    def selected_active(self):
        return set(self.save["questState"]["active"]) & set(IDS)

    def progress(self, name):
        return self.save["questState"]["active"][name]["progress"]

    def finish_actions(self, index):
        for action, code, total in OBJECTIVES[index]:
            quests.record_action(self.save, action, code or None, total)

    def claim(self, name):
        return quests.update_recently_completed_quests(self.save, name, False)

    def test_six_original_ids_and_observed_objectives_are_the_complete_selected_chapter(self):
        self.assertEqual(set(self.catalog), set(IDS))
        self.assertNotIn("england-02-006", self.catalog)
        for index, name in enumerate(IDS):
            definition = self.catalog[name]
            actual = tuple((t["action"], t["type"] or "", t["total"]) for t in definition["tasks"])
            self.assertEqual(actual, OBJECTIVES[index], name)
            self.assertEqual(definition["restoredWorld"], "england")
            self.assertEqual(definition["children"], [IDS[index + 1]] if index + 1 < len(IDS) else [])

    def test_arrival_starts_only_first_quest_and_home_does_not_start_the_chapter(self):
        self.save["userInfo"]["currentWorldType"] = "farm"
        quests.refresh_active_quests(self.save)
        self.assertEqual(self.selected_active(), set())
        self.save["userInfo"]["currentWorldType"] = "england"
        quests.refresh_active_quests(self.save)
        self.assertEqual(self.selected_active(), {IDS[0]})

    def test_partial_action_progress_survives_reload_and_wrong_world_or_item_does_not_count(self):
        quests.refresh_active_quests(self.save)
        quests.record_action(self.save, "useItemByCode", "wrong", 6)
        quests.record_action(self.save, "useItemByCode", "kf", 2)
        quests.record_action(self.save, "plowPlot", amount=3)
        self.save = json.loads(json.dumps(self.save))
        self.assertEqual(self.progress(IDS[0]), [2, 3])
        self.save["userInfo"]["currentWorldType"] = "farm"
        before = copy.deepcopy(self.save)
        quests.record_action(self.save, "useItemByCode", "kf", 6)
        quests.record_action(self.save, "plowPlot", amount=10)
        self.assertEqual(self.save, before)
        self.save["userInfo"]["currentWorldType"] = "england"
        quests.record_action(self.save, "useItemByCode", "kf", 20)
        quests.record_action(self.save, "plowPlot", amount=20)
        self.assertEqual(self.progress(IDS[0]), [6, 10])

    def test_premature_or_malformed_claim_and_paid_skips_cannot_grant_or_charge(self):
        quests.refresh_active_quests(self.save)
        before = copy.deepcopy(self.save)
        self.assertFalse(quests.complete_quest(self.save, IDS[0]))
        self.assertEqual(self.claim(IDS[0]), {"friendReward": None})
        self.assertEqual(self.save, before)
        for operation in (
            lambda: quests.skip_task(self.save, IDS[0], 0),
            lambda: quests.skip_entire_quest(self.save, IDS[0]),
        ):
            with self.assertRaises(ValueError):
                operation()
            self.assertEqual(self.save, before)
        for progress in ([6], [6, True], [6, float("nan")], [6, "10"]):
            self.save["questState"]["active"][IDS[0]]["progress"] = progress
            before = copy.deepcopy(self.save)
            with self.subTest(progress=progress):
                self.assertFalse(quests.complete_quest(self.save, IDS[0]))
                self.claim(IDS[0])
            # NaN is intentionally not equal to itself; identity-free fields
            # still prove the failed claim did not pay or advance the chain.
            self.assertEqual(self.save["userInfo"], before["userInfo"])
            self.assertEqual(self.save["questState"]["completed"], [])
            self.assertEqual(self.selected_active(), {IDS[0]})

    def test_generic_callbacks_cannot_forge_selected_construction_visits_or_expansion(self):
        for index in (1, 2, 3, 5):
            name = IDS[index]
            self.save["questState"]["active"] = {}
            self.activate(name)
            before = copy.deepcopy(self.progress(name))
            for action, _, _ in OBJECTIVES[index]:
                try:
                    quests.increment_generic_farm_task(self.save, action)
                except ValueError:
                    pass
            self.assertEqual(self.progress(name), before, name)

    def test_later_link_cannot_complete_before_its_predecessor(self):
        self.activate(IDS[-1], [1, 1])
        before = copy.deepcopy(self.save)
        self.assertFalse(quests.complete_quest(self.save, IDS[-1]))
        self.assertEqual(self.save, before)

    def test_global_story_budget_does_not_starve_england_and_unscoped_progress_stays_global(self):
        for index in range(quests.MAX_ACTIVE_QUESTS):
            name = f"global-{index}"
            self.catalog[name] = quest(name, [task("plowPlot", total=2)])
            self.activate(name)
        quests.refresh_active_quests(self.save)
        self.assertEqual(self.selected_active(), {IDS[0]})
        quests.record_action(self.save, "plowPlot")
        for index in range(quests.MAX_ACTIVE_QUESTS):
            self.assertEqual(self.progress(f"global-{index}"), [1])
        self.save["userInfo"]["currentWorldType"] = "farm"
        quests.record_action(self.save, "plowPlot")
        for index in range(quests.MAX_ACTIVE_QUESTS):
            self.assertEqual(self.progress(f"global-{index}"), [2])
        self.assertEqual(self.progress(IDS[0]), [0, 1])

    def test_all_six_quests_advance_in_order_and_pay_once_across_reload(self):
        quests.refresh_active_quests(self.save)
        for index, name in enumerate(IDS):
            self.assertEqual(self.selected_active(), {name})
            self.finish_actions(index)
            self.assertEqual(self.claim(name), {"friendReward": None})
            self.save = json.loads(json.dumps(self.save))
            before = copy.deepcopy(self.save)
            self.claim(name)
            self.assertEqual(self.save, before, f"duplicate reward for {name}")
            self.assertEqual(self.save["questState"]["completed"], list(IDS[:index + 1]))
        self.assertEqual(self.selected_active(), set())
        self.assertEqual(self.save["userInfo"]["player"]["gold"], 9600)
        self.assertEqual(self.save["userInfo"]["player"]["xp"], 1150)
        for code, amount in (("kw", 1), ("CC", 1), ("ng", 1), ("gk", 5), ("2n", 1), ("nh", 1)):
            self.assertEqual(self.save["testGiftbox"].get(f"item_{code}"), amount)

    def test_worldload_tombstones_hide_offworld_story_but_preserve_global_quests_and_save(self):
        home = quest("home-story", [task("plowPlot", total=2)])
        home["prereqs"] = [{"type": "location", "value": "farm"}]
        self.catalog[home["name"]] = home
        self.catalog["global"] = quest("global", [task("plowPlot", total=2)])
        self.activate(IDS[0], [2, 3])
        self.activate("home-story", [1])
        self.activate("global", [1])
        before = copy.deepcopy(self.save["questState"])
        england = {entry["name"]: entry for entry in quests.quest_component(self.save, include_removed=True)}
        self.assertFalse(england[IDS[0]]["complete"])
        self.assertEqual(england["home-story"], {"name": "home-story", "removed": True})
        self.assertNotIn("removed", england["global"])
        self.save["userInfo"]["currentWorldType"] = "farm"
        home = {entry["name"]: entry for entry in quests.quest_component(self.save, include_removed=True)}
        self.assertEqual(home[IDS[0]], {"name": IDS[0], "removed": True})
        self.assertNotIn("removed", home["global"])
        self.assertEqual(home["home-story"]["progress"], [1])
        self.assertEqual(self.save["questState"], before)


if __name__ == "__main__":
    unittest.main()
