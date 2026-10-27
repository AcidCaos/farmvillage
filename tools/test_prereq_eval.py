"""Tests for FarmVillage/prereq_eval.py, the three-valued prerequisite evaluator.

Three groups: the logic itself (truth tables, caps, operators, facts), purity, and a parity
check against the four older evaluators whose behaviour tools/test_prerequisite_dispositions.py
pins. Parity compares only the outcome class (granted, denied or crash) on one shared set of
synthetic cases. Every difference must be listed in INTENDED below with its reason, and every
listed difference must really exist, so the list cannot go stale in either direction.
Synthetic data only; nothing here touches a game file, a quest, a world or a campaign.
"""
import ast
import copy
import datetime
import importlib.util
import itertools
from pathlib import Path
import re
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def load(relative, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses needs the module registered while it is executed
    spec.loader.exec_module(module)
    return module


PE = load("FarmVillage/prereq_eval.py", "prereq_eval_under_test")
OLD = load("tools/test_prerequisite_dispositions.py", "prereq_dispositions_pinned")
YES, NO, UNKNOWN = PE.Verdict.YES, PE.Verdict.NO, PE.Verdict.UNKNOWN
NOW = datetime.datetime(2020, 1, 2)
FACTS = {"player_level": 5, "coins": 100, "cash": 3, "account_age_days": 3, "world": "farm",
         "completed_quests": {"q1"}, "seen_flags": {"f"}, "owned_codes": {"c1"}, "placed_codes": {"p1"},
         "experiments": {"fv_e": 2}, "eos": {"e1": 1}, "server_time": NOW}


def leaf(kind, value=None, **attributes):
    node = ET.Element("prereq", {"type": kind, **attributes})
    if value is not None:
        node.set("value", value)
    return node


def group(kind, *kids, **attributes):
    node = ET.Element("prereq", {"type": kind, **attributes})
    node.extend(kids)
    return node


def verdict(node, facts=None, **keywords):
    return PE.evaluate(node, FACTS if facts is None else facts, **keywords).verdict


def known(which):
    """A leaf whose verdict is fixed by FACTS."""
    return {YES: leaf("location", "farm"), NO: leaf("location", "elsewhere"), UNKNOWN: leaf("feature_option", "x")}[which]


class LogicTests(unittest.TestCase):
    ORDER = {NO: 0, UNKNOWN: 1, YES: 2}

    def test_and_or_follow_the_three_valued_truth_tables_for_up_to_three_children(self):
        by_rank = {rank: which for which, rank in self.ORDER.items()}
        for size in (1, 2, 3):
            for combination in itertools.product((YES, NO, UNKNOWN), repeat=size):
                ranks = [self.ORDER[item] for item in combination]
                for kind, pick in (("AND", min), ("OR", max)):
                    with self.subTest(kind=kind, combination=[item.name for item in combination]):
                        node = group(kind, *[known(item) for item in combination])
                        self.assertEqual(verdict(node), by_rank[pick(ranks)])

    def test_only_yes_grants(self):
        for which, granted in ((YES, True), (NO, False), (UNKNOWN, False)):
            self.assertEqual(PE.evaluate(known(which), FACTS).granted, granted, which)

    def test_an_unknown_never_becomes_a_yes_and_never_hides_a_clear_answer(self):
        self.assertEqual(verdict(group("OR", known(UNKNOWN), known(YES))), YES)
        self.assertEqual(verdict(group("AND", known(UNKNOWN), known(NO))), NO)
        self.assertEqual(verdict(group("OR", known(UNKNOWN), known(NO))), UNKNOWN)
        self.assertEqual(verdict(group("AND", known(UNKNOWN), known(YES))), UNKNOWN)

    def test_empty_groups_are_unknown_but_an_empty_flat_list_means_no_prerequisites(self):
        for kind in ("AND", "OR"):
            result = PE.evaluate(group(kind), FACTS)
            self.assertEqual((result.verdict, result.reasons), (UNKNOWN, ("empty-group",)))
        self.assertTrue(PE.evaluate_all([], FACTS).granted)
        self.assertTrue(PE.evaluate_all(None, FACTS).granted)

    def test_unknown_results_carry_reasons_and_no_yes_or_no_does(self):
        self.assertEqual(PE.evaluate(known(UNKNOWN), FACTS).reasons, ("no-recovered-contract:feature_option",))
        self.assertEqual(PE.evaluate(known(YES), FACTS).reasons, ())
        self.assertEqual(PE.evaluate(known(NO), FACTS).reasons, ())
        merged = PE.evaluate(group("AND", leaf("feature_option", "x"), leaf("building_level", "y"), leaf("made_up", "z")), FACTS)
        self.assertEqual(merged.reasons, ("no-recovered-contract:feature_option", "no-recovered-contract:building_level", "unsupported-type:made_up"))

    def test_reasons_are_capped(self):
        many = group("AND", *[leaf("kind%d" % n, "x") for n in range(30)])
        self.assertEqual(len(PE.evaluate(many, FACTS).reasons), PE.MAX_REASONS)


class BoundsTests(unittest.TestCase):
    def nested(self, levels):
        node = leaf("level_min", "5")
        for _ in range(levels):
            node = group("AND", node)
        return node

    def test_depth_cap_boundary(self):
        self.assertEqual(verdict(self.nested(PE.DEFAULT_MAX_DEPTH)), YES)
        over = PE.evaluate(self.nested(PE.DEFAULT_MAX_DEPTH + 1), FACTS)
        self.assertEqual((over.verdict, over.reasons), (UNKNOWN, ("depth-cap",)))
        self.assertEqual(verdict(self.nested(3), max_depth=3), YES)
        self.assertEqual(verdict(self.nested(4), max_depth=3), UNKNOWN)

    def test_a_tree_far_deeper_than_python_can_recurse_is_refused_not_a_crash(self):
        self.assertEqual(verdict(self.nested(20000)), UNKNOWN)

    def test_size_cap(self):
        wide = group("OR", *[leaf("location", "elsewhere") for _ in range(50)])
        self.assertEqual(verdict(wide, max_nodes=100), NO)
        self.assertEqual(PE.evaluate(wide, FACTS, max_nodes=10).reasons, ("size-cap",))

    def test_a_shared_name_referenced_many_times_cannot_explode(self):
        names = {"base": group("AND", leaf("location", "farm"))}
        for level in range(1, 15):
            below = "base" if level == 1 else "n%d" % (level - 1)
            names["n%d" % level] = group("AND", leaf("prereq_check", below), leaf("prereq_check", below))
        result = PE.evaluate_named("n14", names, FACTS, max_depth=64, max_nodes=2000)
        self.assertEqual((result.verdict, result.reasons), (UNKNOWN, ("size-cap",)))

    def test_cycles_unresolved_names_and_chains(self):
        names = {"a": group("AND", leaf("prereq_check", "b")), "b": group("AND", leaf("prereq_check", "a")),
                 "self": group("AND", leaf("prereq_check", "self")), "ok": group("AND", leaf("prereq_check", "leaf")),
                 "leaf": leaf("level_min", "5"), "dangling": group("AND", leaf("prereq_check", "nowhere"))}
        for name, reason in (("a", "cycle:"), ("self", "cycle:self"), ("dangling", "unresolved:nowhere")):
            with self.subTest(name):
                result = PE.evaluate_named(name, names, FACTS)
                self.assertEqual(result.verdict, UNKNOWN)
                self.assertTrue(any(item.startswith(reason) for item in result.reasons), result.reasons)
        self.assertEqual(PE.evaluate_named("ok", names, FACTS).verdict, YES)
        self.assertEqual(PE.evaluate_named("missing", names, FACTS).reasons, ("unresolved:missing",))
        self.assertEqual(PE.evaluate(leaf("prereq_check", "ok"), FACTS).reasons, ("unresolved:ok",), "no name table was given")

    def test_a_long_chain_of_names_is_refused_not_a_crash(self):
        names = {"L%d" % n: group("AND", leaf("prereq_check", "L%d" % (n + 1))) for n in range(3000)}
        names["L3000"] = leaf("level_min", "5")
        result = PE.evaluate_named("L0", names, FACTS)
        self.assertEqual((result.verdict, result.reasons), (UNKNOWN, ("depth-cap",)))
        self.assertEqual(PE.evaluate_named("L2990", names, FACTS).verdict, YES)


class LeafTests(unittest.TestCase):
    def test_numeric_defaults_and_every_operator_at_the_boundary(self):
        self.assertEqual([verdict(leaf("level_min", value)) for value in ("4", "5", "6")], [YES, YES, NO])
        self.assertEqual([verdict(leaf("level_max", value)) for value in ("4", "5", "6")], [NO, YES, YES])
        for name, below, equal, above in (("gte", NO, YES, YES), ("lte", YES, YES, NO), ("gt", NO, NO, YES), ("lt", YES, NO, NO),
                                          ("eq", NO, YES, NO), ("ne", YES, NO, YES)):
            for fact, want in ((4, below), (5, equal), (6, above)):
                with self.subTest(operator=name, level=fact):
                    node = leaf("level_min", "5", **{PE.OPERATOR_ATTRIBUTE: name})
                    self.assertEqual(verdict(node, {**FACTS, "player_level": fact}), want)

    def test_other_numeric_leaves(self):
        self.assertEqual([verdict(leaf("coins", "100")), verdict(leaf("coins", "101"))], [YES, NO])
        self.assertEqual([verdict(leaf("cash", "3")), verdict(leaf("cash", "4"))], [YES, NO])
        self.assertEqual([verdict(leaf("acct_age_days_min", "3")), verdict(leaf("acct_age_days_min", "4"))], [YES, NO])
        self.assertEqual(verdict(leaf("coins", "100"), {**FACTS, "coins": 100.5}), YES)

    def test_unrecognised_operators_and_attributes_are_unknown_never_ignored(self):
        cases = [leaf("level_min", "5", **{PE.OPERATOR_ATTRIBUTE: "between"}), leaf("level_min", "5", flavour="x"),
                 leaf("quest_complete", "q1", **{PE.OPERATOR_ATTRIBUTE: "lte"}), leaf("location", "farm", variant="2"),
                 group("AND", leaf("location", "farm"), flavour="x")]
        for node in cases:
            with self.subTest(ET.tostring(node)[:50]):
                result = PE.evaluate(node, FACTS)
                self.assertEqual(result.verdict, UNKNOWN)
                self.assertTrue(result.reasons[0].startswith(("unknown-attribute", "unknown-operator")), result.reasons)

    def test_bad_values_and_missing_or_malformed_facts_are_unknown(self):
        self.assertEqual(PE.evaluate(leaf("level_min", "five"), FACTS).reasons, ("bad-value:level_min",))
        self.assertEqual(PE.evaluate(leaf("level_min"), FACTS).reasons, ("missing-value:level_min",))
        for broken in ({}, {"player_level": None}, {"player_level": "5"}, {"player_level": True}, {"player_level": float("nan")}):
            with self.subTest(broken):
                self.assertEqual(PE.evaluate(leaf("level_min", "5"), broken).reasons, ("missing-fact:player_level",))

    def test_membership_leaves(self):
        self.assertEqual([verdict(leaf("quest_complete", "q1")), verdict(leaf("quest_complete", "q2"))], [YES, NO])
        self.assertEqual(verdict(leaf("tracked_quest_complete", "q1")), YES)
        self.assertEqual([verdict(leaf("has_seen_flag", "f")), verdict(leaf("has_seen_flag", "g"))], [YES, NO])
        self.assertEqual([verdict(leaf("has_item", "c1")), verdict(leaf("has_item", "c2"))], [YES, NO])
        self.assertEqual([verdict(leaf("not_placed_item", "p1")), verdict(leaf("not_placed_item", "p2"))], [NO, YES])
        for bad in (None, "q1", 5, ["q1", 2]):
            with self.subTest(bad):
                self.assertEqual(verdict(leaf("quest_complete", "q1"), {**FACTS, "completed_quests": bad}), UNKNOWN)
        self.assertEqual(verdict(leaf("not_placed_item", "p2"), {k: v for k, v in FACTS.items() if k != "placed_codes"}), UNKNOWN,
                         "a missing fact must not turn a negative check into a yes")

    def test_location(self):
        self.assertEqual([verdict(leaf("location", "farm")), verdict(leaf("location", "england"))], [YES, NO])
        self.assertEqual(verdict(leaf("location", "farm"), {**FACTS, "world": None}), UNKNOWN)

    def test_experiment_and_eos_need_an_explicit_variant(self):
        self.assertEqual(verdict(leaf("experiment", "fv_e", variant="2")), YES)
        self.assertEqual(verdict(leaf("experiment", "fv_e", variant="1")), NO)
        self.assertEqual(verdict(leaf("experiment", "absent", variant="1")), NO)
        self.assertEqual(verdict(leaf("eos", "e1", variant="1")), YES)
        self.assertEqual(PE.evaluate(leaf("experiment", "fv_e"), FACTS).reasons, ("missing-variant:experiment",))
        self.assertEqual(verdict(leaf("experiment", "fv_e", variant="x")), UNKNOWN)
        self.assertEqual(verdict(leaf("experiment", "fv_e", variant="2"), {**FACTS, "experiments": None}), UNKNOWN)
        self.assertEqual(verdict(leaf("experiment", "fv_e", variant="2"), {**FACTS, "experiments": {"fv_e": "2"}}), UNKNOWN)

    def test_start_and_end_time_are_inclusive_and_need_a_naive_server_time(self):
        second = datetime.timedelta(seconds=1)
        for kind, equal, before, after in (("start_time", YES, NO, YES), ("end_time", YES, YES, NO)):
            with self.subTest(kind):
                node = leaf(kind, "01/02/2020")
                self.assertEqual(verdict(node), equal)
                self.assertEqual(verdict(node, {**FACTS, "server_time": NOW - second}), before)
                self.assertEqual(verdict(node, {**FACTS, "server_time": NOW + second}), after)
        timed = leaf("start_time", "01/02/2020 13:14:15")
        self.assertEqual(verdict(timed, {**FACTS, "server_time": datetime.datetime(2020, 1, 2, 13, 14, 15)}), YES)
        self.assertEqual(verdict(timed, {**FACTS, "server_time": datetime.datetime(2020, 1, 2, 13, 14, 14)}), NO)
        self.assertEqual(PE.evaluate(leaf("start_time", "garbage"), FACTS).reasons, ("bad-value:start_time",))
        for bad in (None, "2020-01-02", NOW.replace(tzinfo=datetime.timezone.utc)):
            with self.subTest(bad):
                self.assertEqual(PE.evaluate(leaf("end_time", "01/02/2020"), {**FACTS, "server_time": bad}).reasons, ("missing-fact:server_time",))

    def test_ignoring_end_time_is_an_explicit_caller_policy(self):
        past = leaf("end_time", "01/01/2000")
        self.assertEqual(verdict(past), NO)
        self.assertEqual(verdict(past, ignore_end_time=True), YES)
        self.assertEqual(verdict(leaf("end_time", "garbage"), ignore_end_time=True), YES)
        self.assertEqual(verdict(leaf("end_time", "garbage")), UNKNOWN, "without the policy a malformed date is unknown")
        self.assertEqual(verdict(leaf("start_time", "01/01/2999"), ignore_end_time=True), NO, "only end_time is ignored")

    def test_unrecovered_and_unknown_types_say_so(self):
        for kind in PE.UNRECOVERED:
            self.assertEqual(PE.evaluate(leaf(kind, "x"), FACTS).reasons, ("no-recovered-contract:" + kind,))
        self.assertEqual(PE.evaluate(leaf("made_up", "x"), FACTS).reasons, ("unsupported-type:made_up",))
        self.assertEqual(PE.evaluate(ET.Element("prereq", {"value": "x"}), FACTS).reasons, ("unsupported-type:None",))
        with_child = leaf("level_min", "5")
        with_child.append(leaf("level_min", "5"))
        self.assertEqual(PE.evaluate(with_child, FACTS).reasons, ("leaf-has-children:level_min",))

    def test_supported_leaves_are_exactly_the_decidable_ones(self):
        self.assertEqual(set(PE.SUPPORTED_LEAVES), {"level_min", "level_max", "coins", "cash", "acct_age_days_min", "quest_complete",
                         "tracked_quest_complete", "has_seen_flag", "has_item", "not_placed_item", "experiment", "eos", "location",
                         "start_time", "end_time"})
        self.assertFalse(set(PE.SUPPORTED_LEAVES) & set(PE.UNRECOVERED))


class FormsAndPurityTests(unittest.TestCase):
    def test_mapping_nodes_and_element_nodes_agree(self):
        as_dict = {"type": "OR", "children": [{"type": "level_min", "value": "99"},
                                              {"type": "AND", "children": [{"type": "level_min", "value": 5}, {"type": "location", "value": "farm"}]}]}
        as_tree = group("OR", leaf("level_min", "99"), group("AND", leaf("level_min", "5"), leaf("location", "farm")))
        self.assertEqual(verdict(as_dict), verdict(as_tree))
        self.assertEqual(verdict(as_tree), YES)

    def test_flat_lists_are_an_implicit_and(self):
        self.assertTrue(PE.evaluate_all([{"type": "level_min", "value": "5"}, {"type": "coins", "value": "100"}], FACTS).granted)
        self.assertEqual(PE.evaluate_all([{"type": "level_min", "value": "5"}, {"type": "coins", "value": "101"}], FACTS).verdict, NO)
        self.assertEqual(PE.evaluate_all([{"type": "level_min", "value": "5"}, {"type": "feature_option", "value": "x"}], FACTS).verdict, UNKNOWN)

    def test_malformed_nodes_are_unknown(self):
        for bad in ("level_min", 5, None, ["x"]):
            with self.subTest(bad):
                self.assertEqual(PE.evaluate(bad, FACTS).reasons, ("malformed-node",))
        self.assertEqual(PE.evaluate({"type": "AND", "children": ["oops"]}, FACTS).reasons, ("malformed-node",))

    def test_a_reference_never_answers_over_authored_children_it_would_ignore(self):
        names = {"ok": leaf("location", "farm")}
        for child in (known(NO), known(YES), known(UNKNOWN)):
            with self.subTest(child.attrib):
                element = leaf("prereq_check", "ok")
                element.append(child)
                mapping = {"type": "prereq_check", "value": "ok", "children": [{"type": "location", "value": "elsewhere"}]}
                for node in (element, mapping):
                    result = PE.evaluate(node, FACTS, nodes=names)
                    self.assertEqual((result.verdict, result.reasons), (UNKNOWN, ("leaf-has-children:prereq_check",)))
        self.assertEqual(verdict(leaf("prereq_check", "ok"), nodes=names), YES, "a childless reference still resolves")
        self.assertEqual(verdict(group("AND", known(YES), leaf("prereq_check", "ok")), nodes=names), YES)

    def test_malformed_mappings_are_unknown_never_an_exception(self):
        cases = {
            "type is a list": ({"type": ["location"], "value": "farm"}, "unsupported-type:list"),
            "type is a mapping": ({"type": {"a": 1}}, "unsupported-type:dict"),
            "type is a number": ({"type": 5}, "unsupported-type:int"),
            "type is missing": ({"value": "x"}, "unsupported-type:None"),
            "group children is a number": ({"type": "AND", "children": 5}, "malformed-children:AND"),
            "group children is a mapping": ({"type": "OR", "children": {"type": "location"}}, "malformed-children:OR"),
            "group children is a string": ({"type": "AND", "children": "location"}, "malformed-children:AND"),
            "leaf children is a number": ({"type": "location", "value": "farm", "children": 5}, "malformed-children:location"),
            "reference children is a number": ({"type": "prereq_check", "value": "n", "children": 5}, "malformed-children:prereq_check"),
            "operator is a list": ({"type": "level_min", "value": "1", PE.OPERATOR_ATTRIBUTE: ["gte"]}, "unknown-operator:['gte']"),
            "operator is a mapping": ({"type": "coins", "value": "1", PE.OPERATOR_ATTRIBUTE: {"gte": 1}}, "unknown-operator:{'gte': 1}"),
            "group has a non-string attribute": ({"type": "AND", 1: "x", "children": [{"type": "location", "value": "farm"}]}, "unknown-attribute:1"),
            "leaf has a non-string attribute": ({"type": "location", "value": "farm", 1: "x"}, "unknown-attribute:1"),
            "reference has a non-string attribute": ({"type": "prereq_check", "value": "n", None: "x"}, "unknown-attribute:None"),
        }
        for label, (node, reason) in cases.items():
            with self.subTest(label):
                result = PE.evaluate(node, FACTS, nodes={"n": known(YES)})
                self.assertEqual((result.verdict, result.reasons), (UNKNOWN, (reason,)))
        for falsy in (0, False, "", {}, None, 0.0, set()):
            for kind, extra in (("level_min", {"value": "1"}), ("location", {"value": "farm"}),
                                ("AND", {}), ("OR", {}), ("prereq_check", {"value": "n"})):
                with self.subTest(children=repr(falsy), kind=kind):
                    result = PE.evaluate({"type": kind, **extra, "children": falsy}, FACTS, nodes={"n": known(YES)})
                    self.assertEqual((result.verdict, result.reasons), (UNKNOWN, ("malformed-children:" + kind,)),
                                     "a present but malformed children value must never read as no children")
        self.assertEqual(verdict({"type": "level_min", "value": "1", "children": 0}), UNKNOWN, "the reported grant-by-malformed-input case")
        for absent_or_empty in ({}, {"children": []}, {"children": ()}):
            self.assertEqual(verdict({"type": "level_min", "value": "1", **absent_or_empty}), YES, "no children, or an empty list, is still a leaf")
        mixed = {"type": "AND", "z": 1, 2: 2, "children": [known(YES)]}
        self.assertEqual(PE.evaluate(mixed, FACTS).reasons, ("unknown-attribute:2,z",), "mixed key types are named in a stable order")
        self.assertEqual(verdict({"type": "AND", "children": []}), UNKNOWN)
        self.assertEqual(verdict({"type": "AND", "children": ()}), UNKNOWN, "an empty tuple is still an empty group")
        self.assertEqual(verdict({"type": "OR", "children": (known(YES), known(UNKNOWN))}), YES, "a tuple of children is accepted")
        self.assertEqual(verdict({"type": "location", "value": "farm", "children": []}), YES, "empty children is not content")

    def test_integers_of_any_size_are_numbers_but_other_non_finite_values_are_not(self):
        huge = 10 ** 400
        facts = {**FACTS, "coins": huge, "cash": -huge, "player_level": 10 ** 5000}
        self.assertEqual(verdict(leaf("coins", "100"), facts), YES)
        self.assertEqual(verdict(leaf("coins", "100", **{PE.OPERATOR_ATTRIBUTE: "lte"}), facts), NO)
        self.assertEqual(verdict(leaf("cash", "0"), facts), NO)
        self.assertEqual(verdict(leaf("level_min", "5"), facts), YES)
        for bad in (True, float("nan"), float("inf"), float("-inf"), "7", None, 1 + 2j):
            with self.subTest(repr(bad)):
                self.assertEqual(PE.evaluate(leaf("coins", "1"), {**FACTS, "coins": bad}).reasons, ("missing-fact:coins",))

    def test_facts_and_name_tables_must_be_mappings(self):
        for call in (lambda: PE.evaluate(known(YES), []), lambda: PE.evaluate_named("a", {}, []), lambda: PE.evaluate_all([known(YES)], None),
                     lambda: PE.evaluate(known(YES), FACTS, nodes=[]), lambda: PE.evaluate_named("a", [], FACTS)):
            with self.assertRaises(ValueError):
                call()

    def test_inputs_are_never_mutated_and_repeated_calls_agree(self):
        tree = group("OR", leaf("level_min", "5", **{PE.OPERATOR_ATTRIBUTE: "lte"}), leaf("experiment", "fv_e", variant="2"),
                     leaf("prereq_check", "n"))
        names = {"n": group("AND", leaf("location", "farm"))}
        facts = copy.deepcopy(FACTS)
        before = (ET.tostring(tree), ET.tostring(names["n"]), copy.deepcopy(facts))
        first = PE.evaluate(tree, facts, nodes=names)
        second = PE.evaluate(tree, facts, nodes=names)
        self.assertEqual((ET.tostring(tree), ET.tostring(names["n"]), facts), before)
        self.assertEqual(first, second)
        mapping = {"type": "AND", "children": [{"type": "level_min", "value": "5"}]}
        snapshot = copy.deepcopy(mapping)
        PE.evaluate(mapping, FACTS)
        self.assertEqual(mapping, snapshot)

    def test_the_module_is_pure_by_construction(self):
        tree = ast.parse((ROOT / "FarmVillage/prereq_eval.py").read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module)
        self.assertEqual(imported, {"__future__", "datetime", "enum", "math", "operator", "collections.abc", "dataclasses"})
        clock_and_io_attributes = {"now", "utcnow", "today", "fromtimestamp", "time", "write", "read", "mkdir", "environ", "getenv"}
        builtin_io_names = {"open", "print", "input", "exec", "eval", "__import__"}
        attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        self.assertFalse(attributes & clock_and_io_attributes, attributes & clock_and_io_attributes)
        self.assertFalse(names & builtin_io_names, names & builtin_io_names)
        self.assertFalse([node for node in ast.walk(tree) if isinstance(node, (ast.Global, ast.Nonlocal))])


# ---------------------------------------------------------------------------------------------
# Parity with the four older evaluators (pinned in tools/test_prerequisite_dispositions.py)
# ---------------------------------------------------------------------------------------------
INTENDED = {
    "maple/or_true_plus_unknown": ("denied", "granted", "G5: a known yes now satisfies an OR beside an unknown leaf; maple_contracts denied the whole tree"),
    "maple/or_level_plus_unknown": ("denied", "granted", "G5: same, with leaves every form knows"),
    "maple/operator_leaf": ("denied", "granted", "G1: an operator leaf is now evaluated; level 5 lte 5 holds"),
    "maple/3000 nested groups": ("crash", "denied", "G3: a very deep tree is refused (UNKNOWN) instead of raising RecursionError"),
    "scores/empty_and": ("granted", "denied", "G5: an empty AND was true in world_scores; it is now UNKNOWN"),
    "scores/nested_and": ("denied", "granted", "G5: a nested AND group is now evaluated; world_scores treated it as false"),
    "scores/named_leaf": ("denied", "granted", "G5: a named node that is itself a leaf is now evaluated; world_scores returned false"),
    "scores/operator_leaf at level 9": ("granted", "denied", "G1: world_scores ignored the operator and granted; level 9 lte 5 is false"),
    "scores/experiment_default variant is 1#0": ("granted", "denied", "an experiment leaf with no variant used to default to 1; the variant is now required, never guessed"),
    "scores/3000 chained names": ("crash", "denied", "G3: a very long name chain is refused instead of raising RecursionError"),
    "quests/end_time enforced by default": ("granted", "denied", "G6: end_time is enforced unless the caller passes ignore_end_time=True; quests will pass it"),
}

MAPLE_FACTS = {"world": "farm", "player_level": 5, "completed_quests": {"q1"}, "server_time": NOW, "experiments": {"fv_e": 2}}
SCORES_FACTS = {"player_level": 5, "experiments": {"fv_e": 2}}
QUEST_FACTS = {"player_level": 5, "coins": 100, "cash": 3, "world": "farm", "completed_quests": ["a"], "seen_flags": ["f"],
               "account_age_days": 3, "server_time": datetime.datetime(2023, 11, 14, 22, 13, 20)}
# case -> list of (leaf type, value, fact overrides). The older results are in OLD.EXPECTED["quests"].
QUEST_CASES = {
    "level_min below/equal": [("level_min", "6", {}), ("level_min", "5", {})],
    "level_max equal/above": [("level_max", "5", {}), ("level_max", "4", {})],
    "coins equal/above": [("coins", "100", {}), ("coins", "101", {})],
    "cash equal/above": [("cash", "3", {}), ("cash", "4", {})],
    "quest_complete yes/no": [("quest_complete", "a", {}), ("quest_complete", "a", {"completed_quests": ["b"]})],
    "tracked_quest_complete yes/no": [("tracked_quest_complete", "a", {}), ("tracked_quest_complete", "a", {"completed_quests": []})],
    "location match/other": [("location", "farm", {}), ("location", "england", {})],
    "has_seen_flag yes/no": [("has_seen_flag", "f", {}), ("has_seen_flag", "f", {"seen_flags": []})],
    "acct_age_days_min met/short": [("acct_age_days_min", "3", {}), ("acct_age_days_min", "4", {})],
    "start_time past/future/malformed": [("start_time", "01/01/2000", {}), ("start_time", "01/01/2999", {}), ("start_time", "garbage", {})],
    "undecidable types are false": [(kind, "x", {}) for kind in ("prereq_check", "feature_option", "building_level", "experiment", "made_up")],
}


def cls(granted):
    return "granted" if granted else "denied"


class ParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls_):
        pinned = OLD.EXPECTED
        cms = re.search(r'CMS = """(.*?)"""', OLD.DRIVER, re.S).group(1)
        named = {p.get("name"): p for p in ET.fromstring(cms).iter("prereq") if p.get("name")}
        cases = []

        def add(case, old, new):
            cases.append((case, old, new))

        def old_of(value):
            return "crash" if isinstance(value, str) and value.startswith("EXC:") else cls(value)

        # maple_contracts: [met, supported] per named prerequisite
        plain = [n for n in pinned["maple"] if n in named]
        for name in plain:
            add("maple/" + name, cls(pinned["maple"][name][0]), cls(PE.evaluate_named(name, named, MAPLE_FACTS).granted))
        add("maple/experiment_leaf wrong variant", cls(pinned["maple"]["experiment_leaf wrong variant"][0]),
            cls(PE.evaluate_named("experiment_leaf", named, {**MAPLE_FACTS, "experiments": {"fv_e": 1}}).granted))
        second = datetime.timedelta(seconds=1)
        for case, name, shifts in (("end_leaf equal/after", "end_leaf", (0, 1)), ("start_leaf equal/before", "start_leaf", (0, -1))):
            for index, shift in enumerate(shifts):
                facts = {**MAPLE_FACTS, "server_time": NOW + shift * second}
                add("maple/%s#%d" % (case, index), cls(pinned["maple"][case][index][0]), cls(PE.evaluate_named(name, named, facts).granted))
        deep = ET.Element("prereq", {"name": "deep", "type": "AND"})
        cursor = deep
        for _ in range(3000):
            cursor = ET.SubElement(cursor, "prereq", {"type": "AND"})
        ET.SubElement(cursor, "prereq", {"type": "level_min", "value": "5"})
        add("maple/3000 nested groups", old_of(pinned["maple"]["3000 nested groups"]), cls(PE.evaluate_named("deep", {"deep": deep}, MAPLE_FACTS).granted))

        # world_scores: a bool per named prerequisite
        for name in [n for n in pinned["scores"] if n in named]:
            add("scores/" + name, old_of(pinned["scores"][name]), cls(PE.evaluate_named(name, named, SCORES_FACTS).granted))
        add("scores/operator_leaf at level 9", old_of(pinned["scores"]["operator_leaf at level 9 ignores the operator"]),
            cls(PE.evaluate_named("operator_leaf", named, {**SCORES_FACTS, "player_level": 9}).granted))
        for index, variant in enumerate((1, 2)):
            add("scores/experiment_default variant is 1#%d" % index, cls(pinned["scores"]["experiment_default variant is 1"][index]),
                cls(PE.evaluate_named("experiment_default", named, {**SCORES_FACTS, "experiments": {"fv_e": variant}}).granted))
        chain = {"L%d" % n: ET.fromstring('<prereq name="L%d" type="AND"><prereq type="prereq_check" value="L%d"/></prereq>' % (n, n + 1))
                 for n in range(3000)}
        add("scores/3000 chained names", old_of(pinned["scores"]["3000 chained names"]), cls(PE.evaluate_named("L0", chain, SCORES_FACTS).granted))

        # quests: a flat list, one leaf at a time
        for case, calls in QUEST_CASES.items():
            old_values = pinned["quests"][case]
            for index, (kind, value, override) in enumerate(calls):
                new = PE.evaluate_all([{"type": kind, "value": value}], {**QUEST_FACTS, **override})
                add("quests/%s#%d" % (case, index), cls(old_values[index]), cls(new.granted))
        for index, value in enumerate(("01/01/2000", "garbage")):
            ignored = PE.evaluate_all([{"type": "end_time", "value": value}], QUEST_FACTS, ignore_end_time=True)
            add("quests/end_time never enforced#%d" % index, cls(pinned["quests"]["end_time is never enforced"][index]), cls(ignored.granted))
        enforced = PE.evaluate_all([{"type": "end_time", "value": "01/01/2000"}], QUEST_FACTS)
        add("quests/end_time enforced by default", cls(pinned["quests"]["end_time is never enforced"][0]), cls(enforced.granted))
        cls_.cases, cls_.pinned = cases, pinned

    def test_the_comparison_is_not_vacuous(self):
        groups = {case.split("/")[0] for case, _, _ in self.cases}
        self.assertEqual(groups, {"maple", "scores", "quests"})
        self.assertGreaterEqual(len(self.cases), 60)
        self.assertGreater(sum(1 for _, old, new in self.cases if old == new == "granted"), 10)
        self.assertGreater(sum(1 for _, old, new in self.cases if old == new == "denied"), 30)

    def test_every_difference_from_the_older_evaluators_is_intended_and_listed(self):
        differences = {case: (old, new) for case, old, new in self.cases if old != new}
        self.assertEqual(differences, {case: (old, new) for case, (old, new, _) in INTENDED.items()})

    def test_every_intended_difference_has_a_stated_reason(self):
        for case, (old, new, reason) in INTENDED.items():
            self.assertTrue(reason.strip(), case)
            self.assertNotEqual(old, new, case)

    def test_the_decidable_quest_types_are_all_supported(self):
        self.assertFalse(set(self.pinned["quests"]["supported types"]) - set(PE.SUPPORTED_LEAVES))

    def test_nothing_is_granted_that_an_older_evaluator_denied_except_where_listed(self):
        widened = {case for case, old, new in self.cases if old != "granted" and new == "granted"}
        self.assertEqual(widened, {case for case, (old, new, _) in INTENDED.items() if old != "granted" and new == "granted"})
        self.assertEqual(widened, {"maple/or_true_plus_unknown", "maple/or_level_plus_unknown", "maple/operator_leaf",
                                   "scores/nested_and", "scores/named_leaf"})


if __name__ == "__main__":
    unittest.main()
