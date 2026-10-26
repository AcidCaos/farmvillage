"""Prerequisite evaluators: what exists, what is missing, and the behaviour pinned today.

Wave 3 lanes F03 and M02 ask for a typed prerequisite evaluator: operators, nested AND and OR,
named `prereq_check` resolution with cycle and depth limits, trusted state, and unknown meaning
false. A re-audit found that evaluators already exist, in four divergent forms, so no new module
was written. This file records the disposition and pins each form's behaviour with synthetic
data, so a later consolidation cannot change any of it by accident. No private input is used.

Disposition (all in FarmVillage/):

| Form | Input | Structure | Unknown |
| --- | --- | --- | --- |
| quests._prereq_met | a save and a completed list | flat list, 11 types | false |
| maple_contracts.prerequisite_status | an explicit facts mapping | nested AND/OR, named, cycle-safe | closes the whole tree |
| world_scores._prereq_met | a save and server experiments | one AND/OR level of leaves, named, cycle-safe | false, siblings unaffected |
| themed_worlds._prereq_leaves | XML only | flattens to leaves, raises on cycles | not an evaluator |

Gaps against Wave 3 (each is pinned below; closing one makes its test fail so the table is updated):

G1  No form evaluates a comparison operator such as `lte`. maple_contracts refuses a leaf that
    carries one (safe). world_scores and quests ignore it and apply their fixed comparison (a hazard
    if such a leaf is reachable; that needs the private CMS: UNRUN). The Cove level-10 `lte` named in
    Wave 3 was not found in the tracked source: UNRUN.
G2  `feature_option` and `building_level` are decided by no form.
G3  No numeric depth limit. Cycles are guarded; a very deep tree or chain raises RecursionError
    in maple_contracts and world_scores instead of returning a refusal.
G4  quests._decode_quests keeps only `type` and `value` of each prerequisite, so other authored
    attributes are lost. Wave 3 asks to preserve them and bump CACHE_VERSION before new predicates.
G5  Semantics diverge between forms: an empty AND is false in maple_contracts but true in
    world_scores; an OR with one true leaf and one unknown leaf is true in world_scores but false
    in maple_contracts; a nested AND inside an AND is false in world_scores but evaluated in
    maple_contracts.
G6  end_time is always true in quests: a deliberate, documented policy (most quests have expired
    windows and enforcing them would hide every quest), not a defect. It differs from
    maple_contracts, which is inclusive. Any consolidation must keep this per caller.
G7  Trusted state is passed three different ways (a save, a facts mapping, server experiments).

The decisions a consolidation needs from the owner are the unknown policy (G5) and the end_time
policy (G6). Nothing here activates a quest, world or campaign.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FARM = ROOT / "FarmVillage"

DRIVER = r'''
import datetime, json, sys, zlib
from unittest import mock
import xml.etree.ElementTree as ET
sys.path.insert(0, sys.argv[1])
import maple_contracts, quests, themed_worlds, world_scores

NOW = 1700000000
quests.timestamp_now = lambda: NOW
quests.xp_to_level = lambda xp: xp
world_scores.xp_to_level = lambda xp: xp

CMS = """<cms>
 <prereq name="and_true" type="AND"><prereq type="level_min" value="5"/><prereq type="quest_complete" value="q1"/></prereq>
 <prereq name="and_false" type="AND"><prereq type="level_min" value="6"/><prereq type="quest_complete" value="q1"/></prereq>
 <prereq name="and_true_plus_unknown" type="AND"><prereq type="level_min" value="5"/><prereq type="feature_option" value="x"/></prereq>
 <prereq name="or_one_true" type="OR"><prereq type="level_min" value="99"/><prereq type="quest_complete" value="q1"/></prereq>
 <prereq name="or_true_plus_unknown" type="OR"><prereq type="quest_complete" value="q1"/><prereq type="feature_option" value="x"/></prereq>
 <prereq name="or_level_plus_unknown" type="OR"><prereq type="level_min" value="5"/><prereq type="feature_option" value="x"/></prereq>
 <prereq name="and_level_experiment" type="AND"><prereq type="level_min" value="5"/><prereq type="experiment" value="fv_e" variant="2"/></prereq>
 <prereq name="empty_and" type="AND"/>
 <prereq name="empty_or" type="OR"/>
 <prereq name="cycle_a" type="AND"><prereq type="prereq_check" value="cycle_b"/></prereq>
 <prereq name="cycle_b" type="AND"><prereq type="prereq_check" value="cycle_a"/></prereq>
 <prereq name="refers_missing" type="AND"><prereq type="prereq_check" value="nowhere"/></prereq>
 <prereq name="nested_and" type="OR"><prereq type="AND"><prereq type="level_min" value="5"/></prereq></prereq>
 <prereq name="operator_leaf" type="AND"><prereq type="level_min" value="5" operator="lte"/></prereq>
 <prereq name="feature_leaf" type="AND"><prereq type="feature_option" value="f"/></prereq>
 <prereq name="building_leaf" type="AND"><prereq type="building_level" value="b"/></prereq>
 <prereq name="chain_ok" type="AND"><prereq type="prereq_check" value="and_true"/></prereq>
 <prereq name="end_leaf" type="AND"><prereq type="end_time" value="01/02/2020"/></prereq>
 <prereq name="start_leaf" type="AND"><prereq type="start_time" value="01/02/2020"/></prereq>
 <prereq name="experiment_leaf" type="AND"><prereq type="experiment" value="fv_e" variant="2"/></prereq>
 <prereq name="experiment_default" type="AND"><prereq type="experiment" value="fv_e"/></prereq>
 <prereq name="named_leaf" type="level_min" value="5"/>
</cms>"""
ROOT_XML = ET.fromstring(CMS)
NAMED = {p.get("name"): p for p in ROOT_XML.iter("prereq") if p.get("name")}
BOUNDARY = datetime.datetime(2020, 1, 2)

def save(level=5, gold=100, cash=3, world="farm", seen=(), first_day=NOW - 3 * 86400):
    return {"userInfo": {"currentWorldType": world, "firstDayTimestamp": first_day,
                         "player": {"xp": level, "gold": gold, "cash": cash, "seenFlags": {k: True for k in seen}}}}

def guarded(function):
    try:
        return function()
    except RecursionError:
        return "EXC:RecursionError"
    except Exception as error:
        return "EXC:" + type(error).__name__

out = {"quests": {}, "maple": {}, "scores": {}, "leaves": {}, "agree": {}}

# ---- quests: flat evaluator
def qm(kind, value, completed=(), **kw):
    return guarded(lambda: quests._prereq_met(save(**kw), {"type": kind, "value": value}, list(completed)))
Q = out["quests"]
Q.update({
    "level_min below/equal": [qm("level_min", "6"), qm("level_min", "5")],
    "level_max equal/above": [qm("level_max", "5"), qm("level_max", "4")],
    "coins equal/above": [qm("coins", "100"), qm("coins", "101")],
    "cash equal/above": [qm("cash", "3"), qm("cash", "4")],
    "quest_complete yes/no": [qm("quest_complete", "a", ["a"]), qm("quest_complete", "a", ["b"])],
    "tracked_quest_complete yes/no": [qm("tracked_quest_complete", "a", ["a"]), qm("tracked_quest_complete", "a", [])],
    "location match/other": [qm("location", "farm"), qm("location", "england")],
    "has_seen_flag yes/no": [qm("has_seen_flag", "f", seen=("f",)), qm("has_seen_flag", "f")],
    "acct_age_days_min met/short": [qm("acct_age_days_min", "3"), qm("acct_age_days_min", "4")],
    "start_time past/future/malformed": [qm("start_time", "01/01/2000"), qm("start_time", "01/01/2999"), qm("start_time", "garbage")],
    "end_time is never enforced": [qm("end_time", "01/01/2000"), qm("end_time", "garbage")],
    "undecidable types are false": [qm(kind, "x") for kind in ("prereq_check", "feature_option", "building_level", "experiment", "made_up")],
    "supported types": list(quests.SUPPORTED_PREREQS),
})
xml = ('<questSettings><quest name="q" memStoreId="1"><prereqs><prereq type="level_min" value="10" operator="lte" variant="2"/>'
       '</prereqs></quest></questSettings>')
decoded = quests._decode_quests(zlib.compress(xml.encode()))
Q["decoder keeps only type and value"] = decoded["quests"]["q"]["prereqs"]

# ---- maple_contracts: facts-based, nested, conservative
def maple(name, **facts):
    base = {"world": "farm", "player_level": 5, "completed_quests": {"q1"}, "server_time": BOUNDARY, "experiments": {"fv_e": 2}}
    base.update(facts)
    def run():
        with mock.patch.object(maple_contracts, "_sources", lambda: (None, None, NAMED, None)):
            result = maple_contracts.prerequisite_status(name, base)
        return [result["met"], result["supported"]]
    return guarded(run)
M = out["maple"]
for name in ("and_true", "and_false", "and_true_plus_unknown", "or_one_true", "or_true_plus_unknown", "or_level_plus_unknown",
             "and_level_experiment", "empty_and", "empty_or", "cycle_a", "refers_missing", "nested_and", "operator_leaf",
             "feature_leaf", "building_leaf", "chain_ok", "named_leaf", "experiment_leaf"):
    M[name] = maple(name)
M["experiment_leaf wrong variant"] = maple("experiment_leaf", experiments={"fv_e": 1})
M["end_leaf equal/after"] = [maple("end_leaf"), maple("end_leaf", server_time=BOUNDARY + datetime.timedelta(seconds=1))]
M["start_leaf equal/before"] = [maple("start_leaf"), maple("start_leaf", server_time=BOUNDARY - datetime.timedelta(seconds=1))]
M["facts must be a mapping"] = guarded(lambda: maple_contracts.prerequisite_status("and_true", []))
deep = ET.Element("prereq", {"name": "deep", "type": "AND"})
cursor = deep
for _ in range(3000):
    cursor = ET.SubElement(cursor, "prereq", {"type": "AND"})
ET.SubElement(cursor, "prereq", {"type": "level_min", "value": "5"})
def deep_run():
    with mock.patch.object(maple_contracts, "_sources", lambda: (None, None, {"deep": deep}, None)):
        return maple_contracts.prerequisite_status("deep", {"player_level": 5})["met"]
M["3000 nested groups"] = guarded(deep_run)

# ---- world_scores: save-based, one level of leaves
def scores(name, level=5, experiments=None, nodes=None):
    experiments = {"fv_e": 2} if experiments is None else experiments
    def run():
        with mock.patch.object(world_scores, "_archive", lambda: (None, nodes or NAMED, None)):
            return world_scores._prereq_met(save(level=level), name, experiments)
    return guarded(run)
S = out["scores"]
for name in ("and_true", "and_false", "and_true_plus_unknown", "or_one_true", "or_true_plus_unknown", "or_level_plus_unknown",
             "and_level_experiment", "empty_and", "empty_or", "cycle_a", "refers_missing", "nested_and", "feature_leaf",
             "building_leaf", "chain_ok", "named_leaf", "experiment_leaf"):
    S[name] = scores(name)
S["operator_leaf at level 9 ignores the operator"] = scores("operator_leaf", level=9)
S["experiment_default variant is 1"] = [scores("experiment_default", experiments={"fv_e": 1}), scores("experiment_default", experiments={"fv_e": 2})]
chain = {"L%d" % i: ET.fromstring('<prereq name="L%d" type="AND"><prereq type="prereq_check" value="L%d"/></prereq>' % (i, i + 1)) for i in range(3000)}
S["3000 chained names"] = scores("L0", nodes=chain)

# ---- themed_worlds: leaf flattening only
def leaves(name):
    return guarded(lambda: [list(item) for item in themed_worlds._prereq_leaves(ROOT_XML, name)])
L = out["leaves"]
for name in ("and_true", "or_true_plus_unknown", "chain_ok", "nested_and", "cycle_a", "refers_missing"):
    L[name] = leaves(name)

# ---- the shared leaf must agree across forms
AGREE = ET.fromstring('<prereq name="agree" type="AND"><prereq type="level_min" value="5"/></prereq>')
for level in (4, 5, 6):
    out["agree"]["level_min 5 at level %d" % level] = [
        qm("level_min", "5", level=level),
        maple("named_leaf", player_level=level)[0],
        scores("agree", level=level, nodes={"agree": AGREE})]
print(json.dumps(out, sort_keys=True))
'''

T, F = True, False
EXPECTED = {
    "quests": {
        "level_min below/equal": [F, T], "level_max equal/above": [T, F], "coins equal/above": [T, F], "cash equal/above": [T, F],
        "quest_complete yes/no": [T, F], "tracked_quest_complete yes/no": [T, F], "location match/other": [T, F],
        "has_seen_flag yes/no": [T, F], "acct_age_days_min met/short": [T, F],
        "start_time past/future/malformed": [T, F, F],
        "end_time is never enforced": [T, T],
        "undecidable types are false": [F, F, F, F, F],
        "supported types": ["start_time", "end_time", "level_min", "level_max", "quest_complete", "tracked_quest_complete",
                            "location", "has_seen_flag", "acct_age_days_min", "coins", "cash"],
        "decoder keeps only type and value": [{"type": "level_min", "value": "10"}],
    },
    "maple": {
        "and_true": [T, T], "and_false": [F, T], "and_true_plus_unknown": [F, F], "or_one_true": [T, T],
        "or_true_plus_unknown": [F, F], "or_level_plus_unknown": [F, F], "and_level_experiment": [T, T], "empty_and": [F, T], "empty_or": [F, T], "cycle_a": [F, F], "refers_missing": [F, F],
        "nested_and": [T, T], "operator_leaf": [F, F], "feature_leaf": [F, F], "building_leaf": [F, F], "chain_ok": [T, T],
        "named_leaf": [T, T], "experiment_leaf": [T, T], "experiment_leaf wrong variant": [F, T],
        "end_leaf equal/after": [[T, T], [F, T]], "start_leaf equal/before": [[T, T], [F, T]],
        "facts must be a mapping": "EXC:ValueError", "3000 nested groups": "EXC:RecursionError",
    },
    "scores": {
        "and_true": F, "and_false": F, "and_true_plus_unknown": F, "or_one_true": F, "or_true_plus_unknown": F,
        "or_level_plus_unknown": T, "and_level_experiment": T, "empty_and": T, "empty_or": F, "cycle_a": F, "refers_missing": F, "nested_and": F, "feature_leaf": F,
        "building_leaf": F, "chain_ok": F, "named_leaf": F, "experiment_leaf": T,
        "operator_leaf at level 9 ignores the operator": T,
        "experiment_default variant is 1": [T, F],
        "3000 chained names": "EXC:RecursionError",
    },
    "leaves": {
        "and_true": [["level_min", "5", None], ["quest_complete", "q1", None]],
        "or_true_plus_unknown": [["quest_complete", "q1", None], ["feature_option", "x", None]],
        "chain_ok": [["level_min", "5", None], ["quest_complete", "q1", None]],
        "nested_and": [["AND", None, None]],
        "cycle_a": "EXC:ValueError", "refers_missing": "EXC:ValueError",
    },
}


class PrerequisiteDispositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # A separate interpreter keeps the game modules and sys.path out of this test process.
        with tempfile.TemporaryDirectory(prefix="fv-prereq-") as home:
            done = subprocess.run([sys.executable, "-I", "-B", "-c", DRIVER, str(FARM)], cwd=home, capture_output=True, text=True,
                                  env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": home}, timeout=180)
        if done.returncode != 0:
            raise AssertionError("The evaluator driver failed:\n" + done.stderr[-1500:])
        cls.observed = json.loads(done.stdout.strip().splitlines()[-1])

    def compare(self, group):
        expected, observed = EXPECTED[group], self.observed[group]
        self.assertEqual(set(observed), set(expected), "cases added or removed in " + group)
        for case in sorted(expected):
            with self.subTest(group + ": " + case):
                self.assertEqual(observed[case], expected[case])

    def test_flat_quest_evaluator(self):
        self.compare("quests")

    def test_maple_nested_conservative_evaluator(self):
        self.compare("maple")

    def test_world_scores_one_level_evaluator(self):
        self.compare("scores")

    def test_theme_world_leaf_flattening(self):
        self.compare("leaves")

    def test_the_shared_level_leaf_agrees_across_forms(self):
        for level, want in ((4, False), (5, True), (6, True)):
            with self.subTest(level=level):
                self.assertEqual(self.observed["agree"]["level_min 5 at level %d" % level], [want, want, want])

    def test_gaps_are_still_open_so_the_table_is_current(self):
        """Fails when a gap is closed: update the docstring table, then these expectations."""
        maple, scores, quests_ = self.observed["maple"], self.observed["scores"], self.observed["quests"]
        self.assertEqual(maple["operator_leaf"], [False, False], "G1: maple refuses an operator leaf")
        self.assertTrue(scores["operator_leaf at level 9 ignores the operator"], "G1: world_scores ignores the operator")
        self.assertEqual((maple["feature_leaf"], maple["building_leaf"], scores["feature_leaf"], scores["building_leaf"]),
                         ([False, False], [False, False], False, False), "G2")
        self.assertEqual((maple["3000 nested groups"], scores["3000 chained names"]), ("EXC:RecursionError",) * 2, "G3")
        self.assertEqual(quests_["decoder keeps only type and value"], [{"type": "level_min", "value": "10"}], "G4")
        self.assertNotEqual(maple["empty_and"][0], scores["empty_and"], "G5 empty AND")
        self.assertEqual((maple["or_level_plus_unknown"][0], scores["or_level_plus_unknown"]), (False, True), "G5 OR with an unknown leaf")
        self.assertEqual(quests_["end_time is never enforced"], [True, True], "G6")


class SourceMarkersStillExist(unittest.TestCase):
    """The table above cites these; if one moves the table needs a second look."""

    def text(self, relative):
        return (FARM / relative).read_text(encoding="utf-8")

    def test_quests(self):
        text = self.text("quests.py")
        for marker in ("def _prereq_met(", "SUPPORTED_PREREQS = (", "return True  # never enforced", "CACHE_VERSION:int",
                       '{"type": p.get("@type"), "value": p.get("@value")}', "# end_time is decoded but deliberately never enforced."):
            self.assertIn(marker, text)

    def test_other_forms(self):
        self.assertIn("def prerequisite_status(", self.text("maple_contracts.py"))
        self.assertIn("never becomes eligible via an OR", self.text("maple_contracts.py"))
        self.assertIn("def _prereq_met(", self.text("world_scores.py"))
        self.assertIn("deliberately not guessed", self.text("world_scores.py"))
        self.assertIn("def _prereq_leaves(", self.text("themed_worlds.py"))


if __name__ == "__main__":
    unittest.main()
