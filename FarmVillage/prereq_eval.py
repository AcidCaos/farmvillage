"""Pure three-valued prerequisite evaluation (Wave 3 lanes F03 and M02).

Every check answers YES, NO or UNKNOWN (cannot tell). Only YES grants; NO and UNKNOWN both
deny, so "unknown remains false" holds at the door, while UNKNOWN keeps its meaning inside a
tree: a known YES still satisfies an OR, a known NO still fails an AND, and a mystery can
never become a YES, even if a rule is later negated.

    AND: any NO -> NO; else any UNKNOWN -> UNKNOWN; else YES
    OR:  any YES -> YES; else any UNKNOWN -> UNKNOWN; else NO
    empty group -> UNKNOWN (an empty group is a data oddity, not a permission)

The module is pure. It reads nothing, writes nothing, never looks at a clock and never mutates
its arguments. Trusted state arrives in an explicit `facts` mapping:

    player_level, coins, cash, account_age_days   numbers (not booleans)
    world                                        the current world type
    completed_quests, seen_flags, owned_codes,
    placed_codes                                 collections of strings
    experiments, eos                             mappings of name -> integer variant
    server_time                                  a naive datetime in the original server's wall clock

A missing or malformed fact makes its check UNKNOWN; it is never guessed.

Nodes may be ElementTree elements (`attrib`, children) or mappings with a "children" list.
Every authored attribute is read: an attribute a check does not recognise makes it UNKNOWN
instead of being ignored. Named `prereq_check` references resolve through a caller-supplied
mapping, with cycle detection, a depth cap and a node-count cap, each answering UNKNOWN.

What is deliberately NOT decided, because its original contract is not recovered:
`feature_option` and `building_level` answer UNKNOWN with a reason. Nothing here activates a
quest, world or campaign, and nothing calls this module yet: tools/test_prerequisite_dispositions.py
pins how the four older evaluators behave, and tools/test_prereq_eval.py lists every intended
difference from them.

UNVERIFIED: the name of the attribute that carries a comparison operator in the original data.
`OPERATOR_ATTRIBUTE` is a guess because the original configuration is a private input that was
not available when this was written (UNRUN). If the real name differs, those checks fail safe:
the unrecognised attribute makes them UNKNOWN.
"""
from __future__ import annotations

import datetime
import enum
import math
import operator as _operator
from collections.abc import Collection, Mapping
from dataclasses import dataclass


class Verdict(enum.Enum):
    YES = "yes"
    NO = "no"
    UNKNOWN = "cannot-tell"


@dataclass(frozen=True)
class Result:
    verdict: Verdict
    reasons: tuple = ()

    @property
    def granted(self) -> bool:
        return self.verdict is Verdict.YES


DEFAULT_MAX_DEPTH = 32
DEFAULT_MAX_NODES = 10_000
MAX_REASONS = 8
OPERATOR_ATTRIBUTE = "operator"  # UNVERIFIED against the original data; see the module docstring.
OPERATORS = {"gte": _operator.ge, "lte": _operator.le, "gt": _operator.gt,
             "lt": _operator.lt, "eq": _operator.eq, "ne": _operator.ne}

# kind -> (fact name, default operator). These are the numeric checks that may carry an operator.
NUMERIC = {"level_min": ("player_level", "gte"), "level_max": ("player_level", "lte"), "coins": ("coins", "gte"),
           "cash": ("cash", "gte"), "acct_age_days_min": ("account_age_days", "gte")}
# kind -> fact name holding a collection of strings, and whether presence is YES
MEMBERSHIP = {"quest_complete": ("completed_quests", True), "tracked_quest_complete": ("completed_quests", True),
              "has_seen_flag": ("seen_flags", True), "has_item": ("owned_codes", True),
              "not_placed_item": ("placed_codes", False)}
VARIANT_TABLES = {"experiment": "experiments", "eos": "eos"}
UNRECOVERED = ("feature_option", "building_level")
SUPPORTED_LEAVES = tuple(sorted({*NUMERIC, *MEMBERSHIP, *VARIANT_TABLES, "location", "start_time", "end_time"}))
BASE_ATTRIBUTES = {"name", "type", "value"}

_YES, _NO = Result(Verdict.YES), Result(Verdict.NO)


def _unknown(*reasons: str) -> Result:
    return Result(Verdict.UNKNOWN, tuple(reasons[:MAX_REASONS]))


def _attributes(node):
    if isinstance(node, Mapping):
        return {key: value for key, value in node.items() if key != "children"}
    return dict(node.attrib)


def _children(node):
    if isinstance(node, Mapping):
        return list(node.get("children") or ())
    return list(node)


def _is_node(node) -> bool:
    # ElementTree elements iterate through the sequence protocol and may have no __iter__ attribute.
    return isinstance(node, Mapping) or (hasattr(node, "attrib") and hasattr(node, "tag"))


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _integer(text):
    try:
        return int(str(text).strip())
    except (TypeError, ValueError):
        return None


def _collection(value):
    return isinstance(value, Collection) and not isinstance(value, (str, bytes)) and all(isinstance(item, str) for item in value)


def _boundary(text):
    for pattern in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y"):
        try:
            return datetime.datetime.strptime(str(text).strip(), pattern)
        except ValueError:
            continue
    return None


def _combine(results, every: bool) -> Result:
    decisive = Verdict.NO if every else Verdict.YES
    if any(result.verdict is decisive for result in results):
        return _NO if every else _YES
    unknown = [result for result in results if result.verdict is Verdict.UNKNOWN]
    if unknown:
        reasons = []
        for result in unknown:
            for reason in result.reasons:
                if reason not in reasons:
                    reasons.append(reason)
        return _unknown(*reasons)
    return _YES if every else _NO


def _leaf(kind, attributes, facts, ignore_end_time) -> Result:
    allowed = set(BASE_ATTRIBUTES)
    if kind in NUMERIC:
        allowed.add(OPERATOR_ATTRIBUTE)
    if kind in VARIANT_TABLES:
        allowed.add("variant")
    extra = sorted(set(attributes) - allowed)
    if extra:
        return _unknown("unknown-attribute:" + ",".join(extra))
    if kind == "end_time" and ignore_end_time:
        return _YES
    value = attributes.get("value")
    if value is None:
        return _unknown("missing-value:" + kind)

    if kind in NUMERIC:
        fact_name, default = NUMERIC[kind]
        name = attributes.get(OPERATOR_ATTRIBUTE, default)
        if name not in OPERATORS:
            return _unknown("unknown-operator:" + str(name))
        threshold, fact = _integer(value), facts.get(fact_name)
        if threshold is None:
            return _unknown("bad-value:" + kind)
        if not _is_number(fact):
            return _unknown("missing-fact:" + fact_name)
        return _YES if OPERATORS[name](fact, threshold) else _NO

    if kind in MEMBERSHIP:
        fact_name, present_is_yes = MEMBERSHIP[kind]
        fact = facts.get(fact_name)
        if not _collection(fact):
            return _unknown("missing-fact:" + fact_name)
        return _YES if (str(value) in fact) == present_is_yes else _NO

    if kind == "location":
        world = facts.get("world")
        if not isinstance(world, str):
            return _unknown("missing-fact:world")
        return _YES if world == str(value) else _NO

    if kind in VARIANT_TABLES:
        table_name = VARIANT_TABLES[kind]
        table, variant = facts.get(table_name), _integer(attributes.get("variant"))
        if not isinstance(table, Mapping):
            return _unknown("missing-fact:" + table_name)
        if variant is None:
            return _unknown("missing-variant:" + kind)
        actual = table.get(str(value))
        if actual is None:
            return _NO
        if type(actual) is not int:
            return _unknown("bad-fact:" + table_name)
        return _YES if actual == variant else _NO

    if kind in ("start_time", "end_time"):
        now, edge = facts.get("server_time"), _boundary(value)
        if not isinstance(now, datetime.datetime) or now.tzinfo is not None:
            return _unknown("missing-fact:server_time")
        if edge is None:
            return _unknown("bad-value:" + kind)
        return _YES if (now >= edge if kind == "start_time" else now <= edge) else _NO

    if kind in UNRECOVERED:
        return _unknown("no-recovered-contract:" + kind)
    return _unknown("unsupported-type:" + str(kind))


def _run(node, facts, nodes, ignore_end_time, max_depth, max_nodes, entry_path=()) -> Result:
    if not isinstance(facts, Mapping):
        raise ValueError("Prerequisite facts must be a mapping.")
    if nodes is not None and not isinstance(nodes, Mapping):
        raise ValueError("Named prerequisites must be a mapping.")
    visited = [0]

    def walk(current, depth, path) -> Result:
        visited[0] += 1
        if visited[0] > max_nodes:
            return _unknown("size-cap")
        if depth > max_depth:
            return _unknown("depth-cap")
        if not _is_node(current):
            return _unknown("malformed-node")
        attributes = _attributes(current)
        kind = attributes.get("type")
        if kind in ("AND", "OR"):
            extra = sorted(set(attributes) - {"name", "type"})
            if extra:
                return _unknown("unknown-attribute:" + ",".join(extra))
            kids = _children(current)
            if not kids:
                return _unknown("empty-group")
            return _combine([walk(kid, depth + 1, path) for kid in kids], kind == "AND")
        if kind == "prereq_check":
            extra = sorted(set(attributes) - BASE_ATTRIBUTES)
            reference = attributes.get("value")
            if extra:
                return _unknown("unknown-attribute:" + ",".join(extra))
            if not isinstance(reference, str) or nodes is None or reference not in nodes:
                return _unknown("unresolved:" + str(reference))
            if reference in path:
                return _unknown("cycle:" + reference)
            return walk(nodes[reference], depth + 1, path + (reference,))
        if _children(current):
            return _unknown("leaf-has-children:" + str(kind))
        return _leaf(kind, attributes, facts, ignore_end_time)

    return walk(node, 0, tuple(entry_path))


def evaluate(node, facts, *, nodes=None, ignore_end_time=False, max_depth=DEFAULT_MAX_DEPTH, max_nodes=DEFAULT_MAX_NODES) -> Result:
    """Evaluate one prerequisite node. `ignore_end_time` is the caller's explicit policy."""
    return _run(node, facts, nodes, ignore_end_time, max_depth, max_nodes)


def evaluate_named(name, nodes, facts, *, ignore_end_time=False, max_depth=DEFAULT_MAX_DEPTH, max_nodes=DEFAULT_MAX_NODES) -> Result:
    """Evaluate the named prerequisite `name` from `nodes`; an unknown name is UNKNOWN."""
    if not isinstance(facts, Mapping):
        raise ValueError("Prerequisite facts must be a mapping.")
    if not isinstance(nodes, Mapping):
        raise ValueError("Named prerequisites must be a mapping.")
    if not isinstance(name, str) or name not in nodes:
        return _unknown("unresolved:" + str(name))
    return _run(nodes[name], facts, nodes, ignore_end_time, max_depth, max_nodes, entry_path=(name,))


def evaluate_all(prereqs, facts, *, nodes=None, ignore_end_time=False, max_depth=DEFAULT_MAX_DEPTH, max_nodes=DEFAULT_MAX_NODES) -> Result:
    """A flat list of prerequisites that must all hold, as a quest carries them.

    An empty list means the quest has no prerequisites, which is YES. An explicit empty group
    inside a tree is different and stays UNKNOWN.
    """
    if not isinstance(facts, Mapping):
        raise ValueError("Prerequisite facts must be a mapping.")
    if not prereqs:
        return _YES
    return _run({"type": "AND", "children": list(prereqs)}, facts, nodes, ignore_end_time, max_depth, max_nodes)
