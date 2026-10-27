"""Individually approved decorations from a retired world, admitted to one active world.

The retired world stays retired. This module never activates it, never offers travel to it and never
touches its special systems. It names exact (code, name) pairs, so a new or changed catalog record is
refused until someone reviews it. For an approved item, and only in its destination world, it waives
two checks and nothing else:

- the World requirement, because the record names the retired world; and
- the retired world's own master experiment gate, which the served client configuration turns off.

Level, date window, price, class, buyable flag, unlock and every other gate still apply through the
destination world's ordinary rules in themed_worlds. The waived gate follows how heritage_pricing
already rehomes ordinary decorations from inactive worlds (it drops their experiment gate).

Decision record: docs/briefs/WORLD_ROSTER_AND_REPURPOSING.md (27 October 2026). Adding a code here is a
reviewed change that needs the world owner's and the integration reviewer's approval for that item.
"""

APPROVED = {
    "htown": {
        "source": "hlights",
        "waivedGate": "fv_hlights",
        "items": {
            "o8q": "xhl_glowingflowerbox",
            "puh": "xhl_holidaylamppost",
            "pmx": "xhl_twistylamppost",
            "prk": "xhl_lightedbench",
            "p1p": "xhl_hollybrightgreetings",
            "pv5": "xhl_puppysnowpile",
            "pze": "xhl_hollybrightlane",
            "o7m": "xhl_hollybrightpath",
        },
    },
}


def _nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _nodes(child)


def _gates(item):
    gate = item.get("experimentGate")
    if gate in (None, "", 0, False, [], {}):
        return []
    return [str(g) for g in (gate if isinstance(gate, list) else [gate])]


def destinations():
    return frozenset(APPROVED)


def allows(item, world_type):
    """True only for an approved record, unchanged, in its approved destination world."""
    entry = APPROVED.get(world_type)
    if entry is None or not isinstance(item, dict):
        return False
    if entry["items"].get(item.get("code")) != item.get("name"):
        return False
    nodes = [node for node in _nodes(item.get("requirements")) if "className" in node]
    if {node.get("name") for node in nodes if node.get("className") == "World"} != {entry["source"]}:
        return False
    if any(node.get("className") != "World" for node in nodes):
        return False
    return all(gate == entry["waivedGate"] for gate in _gates(item))


def waived_gates(item, world_type):
    """The gates to ignore for this item here: the source world's master gate, or none."""
    return frozenset((APPROVED[world_type]["waivedGate"],)) if allows(item, world_type) else frozenset()
