"""Durable mirrors of authored irrigation rewards and the two recovered wells.

Generic UserRewardUtil irrigation rewards add their exact value without a cap.
WaterHarvestFManager separately refuses an entire well harvest above 2000.
Only owned server timers and expansion levels select a well's water reward.
"""
import copy
import math

import engine
import items
import peaceful

WELLS = frozenset(("bldg_irrigationwell", "bldg_irrigationwell_8hr"))
ACTION = "waterPlots"
MAX_WATER = 2000
REQUESTS_KEY = "_irrigationWellHarvestRequests"
_MAX_INTEGER = 9_007_199_254_740_991
_PRESERVED_FIELDS = ("itemName", "className", "isFullyBuilt", "state", "plantTime",
                     "expansionLevel", "expansionParts", "contents", "capacity")


def _whole(value, label, minimum=0):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or int(value) != value or not minimum <= value <= _MAX_INTEGER):
        raise ValueError(label + " must be a supported whole number.")
    return int(value)


def _catalog_integer(value, label, minimum=0):
    if isinstance(value, str):
        try:
            value = int(value)
        except ValueError:
            pass
    return _whole(value, label, minimum)


def _list(value):
    return value if isinstance(value, list) else ([] if value is None else [value])


def manages(item):
    return isinstance(item, dict) and item.get("name") in WELLS


def start_session(save):
    save[REQUESTS_KEY] = {}


def grant(save, action_type, amount):
    """UserRewardUtil's exact authored reward; the generic branch has no cap."""
    if action_type != ACTION:
        raise ValueError("Only the recovered crop-water reward is restored.")
    amount = _whole(amount, "Irrigation reward")
    engine.add_water(save, action_type, amount)


def _harvester(item):
    rows = [row for row in _list((item.get("features") or {}).get("feature"))
            if isinstance(row, dict) and row.get("name") == "harvester"
            and row.get("className") == "WaterHarvestFManager"]
    if len(rows) != 1 or rows[0].get("rewardMultiplierOverride") != "1":
        raise ValueError("The well's archived harvest contract requires review.")
    return rows[0]


def initialize_placement(snapshot, *, now):
    """SimpleHarvestableResource starts new objects at the current world time."""
    item = items.get_item_by_name(snapshot.get("itemName"))
    if not manages(item):
        return snapshot
    _harvester(item)
    if item.get("className") != "FeatureBuilding":
        raise ValueError("The well's archived class requires review.")
    now = _whole(now, "Well placement time", 1)
    result = copy.deepcopy(snapshot)
    result.update(className="FeatureBuilding", expansionLevel=_catalog_integer(
        item.get("initialExpansionLevel"), "Initial well expansion", 1),
        isFullyBuilt=True, state="bare", plantTime=now * 1000,
        expansionParts={}, contents=[], capacity=_catalog_integer(item.get("capacity", "0"), "Well capacity"))
    return result


def preserve_fields(stored, incoming):
    """A move/store/harvest snapshot cannot rewrite saved well progress."""
    result = copy.deepcopy(incoming)
    if stored and manages(items.get_item_by_name(stored.get("itemName"))):
        for name in _PRESERVED_FIELDS:
            if name in stored:
                result[name] = copy.deepcopy(stored[name])
            else:
                result.pop(name, None)
    elif stored and manages(items.get_item_by_name(incoming.get("itemName"))):
        raise ValueError("A well snapshot cannot replace another farm object.")
    return result


def reward_for_level(item, level):
    """WaterHarvestFManager's authored table is keyed by expand.storageLevel."""
    harvester = _harvester(item)
    result = []
    for row in _list(harvester.get("rewards")):
        if not isinstance(row, dict):
            raise ValueError("The well's reward row is malformed.")
        prerequisites = _list((row.get("prereqs") or {}).get("prereq"))
        if len(prerequisites) != 1 or not isinstance(prerequisites[0], dict):
            raise ValueError("The well's reward prerequisite requires review.")
        requirement = prerequisites[0]
        if (requirement.get("contextBackend") != "expansionLevel"
                or requirement.get("context") != "expand.storageLevel"
                or requirement.get("type") != "compare"):
            raise ValueError("The well's reward prerequisite is not restored.")
        if _catalog_integer(requirement.get("value"), "Well reward level", 1) != level:
            continue
        rewards = _list(row.get("reward"))
        if (len(rewards) != 1 or not isinstance(rewards[0], dict)
                or rewards[0].get("type") != "irrigation" or rewards[0].get("actionType") != ACTION):
            raise ValueError("The well's authored reward is not supported.")
        result.append(_catalog_integer(rewards[0].get("value"), "Well water reward", 1))
    if len(result) != 1:
        raise ValueError("This well has no unique recovered reward for its saved expansion level.")
    return result[0]


def harvest(save, stored, *, now, request_id=None):
    """Return None for another item, water amount for a grant, 0 for a replay."""
    item = items.get_item_by_name(stored.get("itemName"))
    if not manages(item):
        return None
    import world_travel
    world_travel.guard_active_world(save)
    now = _whole(now, "Well harvest time", 1)
    ident = _whole(stored.get("id"), "Well object ID", 1)
    objects = save.get("world", {}).get("objectsArray", [])
    if (stored not in objects or sum(obj.get("id") == ident for obj in objects) != 1
            or stored.get("className") != "FeatureBuilding"
            or stored.get("deleted") or stored.get("isFullyBuilt") is False
            or stored.get("state") not in ("bare", "grown", "built", "busy")):
        raise ValueError("Well harvesting requires one completed owned well.")
    world_travel.guard_action_object(save, ident)
    level = _whole(stored.get("expansionLevel", _catalog_integer(item.get("initialExpansionLevel"),
        "Initial well expansion", 1)), "Saved well expansion level", 1)
    amount = reward_for_level(item, level)
    requests = save.get(REQUESTS_KEY, {})
    if not isinstance(requests, dict):
        raise ValueError("The saved well harvest receipts are malformed.")
    request_key = None
    if request_id is not None:
        request_key = str(_whole(request_id, "Well harvest request sequence"))
        previous = requests.get(request_key)
        if previous is not None:
            if (not isinstance(previous, dict) or previous.get("id") != ident
                    or previous.get("itemName") != item["name"]
                    or previous.get("plantTime") != stored.get("plantTime")):
                raise ValueError("This well harvest sequence was already used by a different action.")
            return 0
    grow = peaceful.grow_seconds(item)
    planted = stored.get("plantTime")
    if (grow is None or type(planted) not in (int, float) or not math.isfinite(planted)
            or planted < 0 or now - planted / 1000 < grow - 1):
        raise ValueError("This well has not finished refilling.")
    if not engine.has_water_store(save, ACTION):
        raise ValueError("This farm has no configured crop-water store.")
    current = engine.get_water_amount(save, ACTION)
    if current + amount > MAX_WATER:
        raise ValueError("Use some irrigation water before harvesting this whole well reward.")
    # Validate receipts and balances before any change; the caller's existing
    # savepoint commits the timer and credit together with normal quest events.
    if request_key is not None and len(requests) >= 2048:
        raise ValueError("Reload the farm before recording more well harvest requests.")
    grant(save, ACTION, amount)
    stored.update(state="bare", plantTime=now * 1000)
    if request_key is not None:
        save.setdefault(REQUESTS_KEY, {})[request_key] = {
            "id": ident, "itemName": item["name"], "plantTime": now * 1000}
    return amount
