"""Round-3 quest regressions: a skip the server does not keep is not charged, a skip only touches a live unfinished task
of an active quest, and getMasteryLevelByCode progress comes from the crop's saved mastery level, so it survives a
login and a quest is still only paid once.

Everything runs on small in-memory quest definitions and saves, never on the recovered catalog cache.
"""

from contextlib import ExitStack, redirect_stdout
import ast
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence  # noqa: F401,E402  Loads first so FARMVILLAGE_DATA_DIR is set before product modules resolve paths.

import progression
import quests

MASTERY = "getMasteryLevelByCode"


def task(action, *, total=1, cash=0, type_=None, level=0):
    return {"action": action, "type": type_, "total": total, "cashValue": cash, "level": level}


def quest(name, tasks, *, icon="assets/quest.png", coins=0):
    rewards = [{"type": "coins", "value": str(coins), "quantity": 1}] if coins else []
    return {"name": name, "memStoreId": None, "category": None, "priority": 0, "ignoreSlotLimit": False,
            "icon": icon, "prereqs": [], "tasks": list(tasks), "rewards": rewards, "children": []}


def new_save(mastery=None):
    return {
        "userInfo": {"currentWorldType": "farm", "firstDayTimestamp": 0,
                     "player": {"cash": 500, "gold": 100, "xp": 0, "mastery": dict(mastery or {}),
                                "masteryCounters": {}, "achievements": {}, "achCounters": {}}},
        "world": {"objectsArray": []},
        "questState": {"active": {}, "completed": [], "retired": [], "replayed": {}},
    }


class QuestFixture(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.catalog = {}
        self.stack.enter_context(mock.patch.object(quests, "_cached_quests", self.catalog))
        self.stack.enter_context(mock.patch.object(quests, "_replayable_chains", {}))
        self.stack.enter_context(mock.patch.object(quests, "_startable_quests", []))
        self.stack.enter_context(mock.patch.object(quests, "_max_active_replayable_quests", 0))
        self.save = new_save()

    def define(self, *definitions):
        for definition in definitions:
            self.catalog[definition["name"]] = definition

    def activate(self, name, progress=None):
        tasks = self.catalog[name]["tasks"]
        self.save["questState"]["active"][name] = {
            "progress": list(progress) if progress is not None else [0 for _ in tasks],
            "new": quests.NON_NEW_QUEST,
        }

    def progress_of(self, name):
        entry = next(e for e in quests.quest_component(self.save) if e["name"] == name)
        return entry["progress"]

    @property
    def cash(self):
        return self.save["userInfo"]["player"]["cash"]

    @property
    def gold(self):
        return self.save["userInfo"]["player"]["gold"]


class SkipChargeTests(QuestFixture):
    def setUp(self):
        super().setUp()
        self.define(quest("paid", [task("plowPlot", total=5, cash=20), task("harvestByCode", total=2, cash=30)]))
        self.activate("paid")

    def test_paid_skip_charges_the_task_price_and_finishes_the_task(self):
        quests.skip_task(self.save, "paid", 0)
        self.assertEqual(self.cash, 480)
        self.assertEqual(self.save["questState"]["active"]["paid"]["progress"], [5, 0])

    def test_uncharged_skip_finishes_the_task_and_keeps_the_cash(self):
        quests.skip_task(self.save, "paid", 0, charge_cash=False)
        self.assertEqual(self.cash, 500)
        self.assertEqual(self.save["questState"]["active"]["paid"]["progress"], [5, 0])

    def test_quest_without_an_icon_is_priced_at_nothing(self):
        self.define(quest("iconless", [task("plowPlot", total=3, cash=20)], icon="none"))
        self.activate("iconless")
        quests.skip_task(self.save, "iconless", 0)
        self.assertEqual(self.cash, 500)
        self.assertEqual(self.save["questState"]["active"]["iconless"]["progress"], [3])


class SkipGuardTests(QuestFixture):
    def setUp(self):
        super().setUp()
        self.define(quest("paid", [task("plowPlot", total=5, cash=20), task("harvestByCode", total=2, cash=30)]))

    def test_quest_that_is_not_active_is_neither_charged_nor_changed(self):
        quests.skip_task(self.save, "paid", 0)
        self.assertEqual(self.cash, 500)
        self.assertEqual(self.save["questState"]["active"], {})

    def test_task_already_done_is_not_charged_again(self):
        self.activate("paid", progress=[5, 0])
        quests.skip_task(self.save, "paid", 0)
        self.assertEqual(self.cash, 500)
        self.assertEqual(self.save["questState"]["active"]["paid"]["progress"], [5, 0])

    def test_negative_index_does_not_wrap_to_the_last_task(self):
        self.activate("paid")
        quests.skip_task(self.save, "paid", -1)
        self.assertEqual(self.cash, 500)
        self.assertEqual(self.save["questState"]["active"]["paid"]["progress"], [0, 0])

    def test_index_past_the_last_task_is_ignored(self):
        self.activate("paid")
        quests.skip_task(self.save, "paid", 2)
        self.assertEqual(self.cash, 500)
        self.assertEqual(self.save["questState"]["active"]["paid"]["progress"], [0, 0])

    def test_values_that_are_not_a_whole_index_are_ignored(self):
        self.activate("paid")
        for index in (None, True, "1", 1.5, float("nan"), float("inf"), -1.0):
            with self.subTest(index=index):
                quests.skip_task(self.save, "paid", index)
                self.assertEqual(self.cash, 500)
                self.assertEqual(self.save["questState"]["active"]["paid"]["progress"], [0, 0])

    def test_whole_float_index_names_its_task(self):
        self.activate("paid")
        quests.skip_task(self.save, "paid", 1.0)
        self.assertEqual(self.cash, 470)
        self.assertEqual(self.save["questState"]["active"]["paid"]["progress"], [0, 2])

    def test_mastery_already_reached_counts_as_done_and_is_not_charged(self):
        self.define(quest("chain", [task(MASTERY, cash=20, type_="SB", level=3)]))
        self.activate("chain")
        self.save["userInfo"]["player"]["mastery"] = {"SB": 2}
        quests.skip_task(self.save, "chain", 0)
        self.assertEqual(self.cash, 500)
        self.assertEqual(self.save["questState"]["active"]["chain"]["progress"], [1])


class ServerRouteTests(unittest.TestCase):
    """server.py cannot be imported here (it loads the whole catalog), so its gateway branches are read directly."""

    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse((ROOT / "server.py").read_text(encoding="utf-8"))

    def branch(self, function_name):
        for node in ast.walk(self.tree):
            if not (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)):
                continue
            names = {elt.value for comp in node.test.comparators if isinstance(comp, ast.Tuple)
                     for elt in comp.elts if isinstance(elt, ast.Constant)}
            if function_name in names:
                return node
        self.fail(f"server.py has no gateway branch for {function_name}")

    def calls(self, node):
        found = []
        for statement in node.body:
            for inner in ast.walk(statement):
                if isinstance(inner, ast.Call):
                    found.append((ast.unparse(inner.func), {kw.arg: kw.value for kw in inner.keywords}))
        return found

    def test_the_four_client_only_skips_are_one_uncharged_branch(self):
        free = ("FarmQuestService.skipConstructionBuildingTask", "FarmQuestService.skipExpandStorageBuildingTask",
                "FarmQuestService.skipRewardCreditsTask", "FarmQuestService.skipGetBushelsTask")
        first = self.branch(free[0])
        for name in free[1:]:
            self.assertIs(self.branch(name), first, name)
        calls = self.calls(first)
        self.assertNotIn("commands.skip_quest_task", [func for func, _ in calls])
        uncharged = [kwargs for func, kwargs in calls if func == "quests.skip_task"]
        self.assertEqual(len(uncharged), 1)
        self.assertIn("charge_cash", uncharged[0])
        self.assertIs(uncharged[0]["charge_cash"].value, False)

    def test_plain_and_friend_set_skips_keep_their_charge(self):
        for name in ("FarmQuestService.skipTask", "FarmQuestService.skipCompleteFriendSetTask"):
            with self.subTest(name=name):
                funcs = [func for func, _ in self.calls(self.branch(name))]
                self.assertIn("commands.skip_quest_task", funcs)
                self.assertNotIn("quests.skip_task", funcs)


class MasteryDecodeTests(unittest.TestCase):
    XML = """<?xml version="1.0"?>
<questSettings>
  <quest name="crop_quest" priority="2">
    <tasks>
      <task action="getMasteryLevelByCode" type="SB" level="3" cashValue="20" total="1"/>
      <task action="plowPlot" total="5"/>
    </tasks>
    <rewards>
      <reward type="coins" value="100"/>
    </rewards>
  </quest>
</questSettings>"""

    def test_mastery_task_keeps_its_level_and_other_tasks_have_none(self):
        decoded = quests._decode_quests(zlib.compress(self.XML.encode("utf-8")))
        mastery, plow = decoded["quests"]["crop_quest"]["tasks"]
        self.assertEqual(mastery, {"action": MASTERY, "type": "SB", "total": 1, "cashValue": 20, "level": 3})
        self.assertEqual(plow["level"], 0)
        self.assertTrue(quests._valid_quests_cache(decoded))

    def test_cache_entries_without_a_level_are_rebuilt(self):
        decoded = quests._decode_quests(zlib.compress(self.XML.encode("utf-8")))
        self.assertEqual(decoded["version"], quests.CACHE_VERSION)
        stale = copy.deepcopy(decoded)
        del stale["quests"]["crop_quest"]["tasks"][0]["level"]
        self.assertFalse(quests._valid_quests_cache(stale))


class MasteryLevelTests(unittest.TestCase):
    def test_level_is_one_based_over_the_stored_zero_based_index(self):
        cases = (
            ({"SB": -1}, 0),
            ({}, 0),
            ({"SB": None}, 0),
            ({"SB": 0}, 1),
            ({"SB": 1}, 2),
            ({"SB": 2}, 3),
        )
        for mastery, expected in cases:
            with self.subTest(mastery=mastery):
                self.assertEqual(progression.mastery_level(new_save(mastery), "SB"), expected)

    def test_missing_or_malformed_mastery_map_counts_as_nothing_earned(self):
        save = new_save()
        save["userInfo"]["player"]["mastery"] = None
        self.assertEqual(progression.mastery_level(save, "SB"), 0)
        del save["userInfo"]["player"]["mastery"]
        self.assertEqual(progression.mastery_level(save, "SB"), 0)


class DerivedMasteryTests(QuestFixture):
    def setUp(self):
        super().setUp()
        self.define(quest("chain", [task(MASTERY, cash=20, type_="SB", level=3)], coins=100))

    def test_progress_follows_the_saved_level(self):
        self.activate("chain")
        self.save["userInfo"]["player"]["mastery"] = {"SB": 1}
        self.assertEqual(self.progress_of("chain"), [0])
        self.save["userInfo"]["player"]["mastery"] = {"SB": 2}
        self.assertEqual(self.progress_of("chain"), [1])

    def test_saved_level_restores_progress_when_the_session_starts_again(self):
        self.activate("chain")
        self.save["userInfo"]["player"]["mastery"] = {"SB": 2}
        login = json.loads(json.dumps(self.save))
        quests.start_session(login)
        self.assertEqual(login["questState"]["active"]["chain"]["progress"], [1])

    def test_reaching_the_level_does_not_finish_or_pay_the_quest_by_itself(self):
        self.activate("chain")
        self.save["userInfo"]["player"]["mastery"] = {"SB": 2}
        quests.quest_component(self.save)
        quests.refresh_active_quests(self.save)
        self.assertEqual(self.gold, 100)
        self.assertEqual(self.save["questState"]["completed"], [])
        self.assertIn("chain", self.save["questState"]["active"])

    def test_completion_pays_the_rewards_exactly_once(self):
        self.activate("chain")
        self.save["userInfo"]["player"]["mastery"] = {"SB": 2}
        quests.quest_component(self.save)
        quests.update_recently_completed_quests(self.save, "chain", False)
        quests.update_recently_completed_quests(self.save, "chain", False)
        quests.quest_component(self.save)
        quests.refresh_active_quests(self.save)
        self.assertEqual(self.gold, 200)
        self.assertEqual(self.save["questState"]["completed"], ["chain"])
        self.assertNotIn("chain", self.save["questState"]["active"])

    def test_progress_already_recorded_is_never_lowered(self):
        self.activate("chain", progress=[1])
        self.save["userInfo"]["player"]["mastery"] = {}
        self.assertEqual(self.progress_of("chain"), [1])

    def test_level_zero_mastery_task_is_never_derived(self):
        self.define(quest("zero", [task(MASTERY, cash=20, type_="SB", level=0)]))
        self.activate("zero")
        self.save["userInfo"]["player"]["mastery"] = {"SB": 2}
        self.assertEqual(self.progress_of("zero"), [0])

    def test_mastery_only_quest_counts_as_movable_for_handout_order(self):
        self.define(quest("feature", [task("completeFeatureCraftingNPC", total=1)]))
        self.assertEqual(quests._assignment_order("chain")[1], 0)
        self.assertEqual(quests._assignment_order("feature")[1], 1)


if __name__ == "__main__":
    unittest.main()
