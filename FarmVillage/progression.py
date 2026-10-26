"""Persistent ribbons and mastery, using the recovered client's goal protocol.

Definitions and rewards come from gameSettings.xml and the item catalog.  A
client notification is only produced when an actual server action changes a
counter or earns a level; reopening a window never grants another reward.
"""

import engine
from game_settings import get_game_settings
from items import get_item_by_code, get_item_by_name
import storage


def _list(value):
    return value if isinstance(value, list) else ([] if value is None else [value])


def ensure_state(save):
    """Repair old empty placeholders without erasing valid imported progress."""
    changed = False
    player = save["userInfo"]["player"]
    for key in ("achievements", "achCounters", "mastery", "masteryCounters"):
        if not isinstance(player.get(key), dict):
            player[key] = {}
            changed = True
    if not isinstance(save.get("progressionState"), dict):
        save["progressionState"] = {"unique": {}}
        changed = True
    if not isinstance(save["progressionState"].get("unique"), dict):
        save["progressionState"]["unique"] = {}
        changed = True
    return changed


def _definitions():
    return {a["@name"]: a for a in _list(get_game_settings().get("achievements", {}).get("achievement"))
            if a.get("@disabled") != "true"}


def _pending(save):
    return save.setdefault("_progressionResponse", {"goals": [], "goalCounters": {}})


def take_response(save):
    """Drain changes onto this command's TFarmTransaction response envelope."""
    pending = save.pop("_progressionResponse", None)
    if not pending:
        return {}
    result = {}
    if pending["goals"]:
        result["goals"] = pending["goals"]
    if pending["goalCounters"]:
        result["goalCounters"] = list(pending["goalCounters"].values())
    return result


def _reward(save, level, *, xml=False):
    prefix = "@" if xml else ""
    engine.apply_xp_increment(save, int(level.get(prefix + "xp") or 0))
    engine.apply_coins_diff(save, int(level.get(prefix + "coins") or 0))
    gift = level.get(prefix + "gift")
    if gift and get_item_by_name(gift) is not None:
        storage.store_deposit_item_by_name(save, gift, group=storage.GIFTBOX_ID)


def _set_counter(save, code, count, levels, *, kind="Achievement", xml=True):
    ensure_state(save)
    player = save["userInfo"]["player"]
    counter_key, level_key = (("achCounters", "achievements") if kind == "Achievement"
                              else ("masteryCounters", "mastery"))
    count = max(0, int(count))
    previous = player[counter_key].get(code)
    player[counter_key][code] = count
    if count != previous:
        _pending(save)["goalCounters"][kind + ":" + code] = {"type": kind, "code": code, "count": count}
    difficulty = int(player[level_key].get(code, -1))
    prefix = "@" if xml else ""
    for index, level in enumerate(_list(levels)):
        if index > difficulty and count >= int(level.get(prefix + "count") or 0):
            player[level_key][code] = index
            _reward(save, level, xml=xml)
            _pending(save)["goals"].append({
                "type": kind, "code": code, "difficulty": index,
                "link": "", "updateHud": True,
            })


def mastery_level(save, code):
    """Mastery levels a crop has earned: 0 before its first, then 1 to 3 as the client counts them.

    _set_counter stores the 0-based index of the highest level reached, the same 0-based star level that
    version.py documents from src/Classes/Mastery.as, so the level a quest names is that index plus one. A crop
    with no entry has earned nothing yet.
    """
    mastery = save["userInfo"]["player"].get("mastery")
    if not isinstance(mastery, dict):
        return 0
    try:
        return max(0, int(mastery.get(code, -1)) + 1)
    except (TypeError, ValueError):
        return 0


def set_ribbon_count(save, name, count):
    definition = _definitions().get(name)
    if definition is not None:
        _set_counter(save, definition["@code"], count, definition.get("level"))


def increment_ribbon(save, name, amount=1):
    ensure_state(save)
    definition = _definitions().get(name)
    if definition is not None:
        count = save["userInfo"]["player"]["achCounters"].get(definition["@code"], 0)
        set_ribbon_count(save, name, int(count) + int(amount))


def _record_unique(save, name, code):
    ensure_state(save)
    unique = save["progressionState"]["unique"]
    codes = unique.setdefault(name, [])
    if code not in codes:
        codes.append(code)
        # An imported counter can predate the list of known item codes. Preserve
        # it as the baseline rather than reducing an already earned ribbon.
        increment_ribbon(save, name)


def record_harvest(save, item, object_state=None):
    item_type = item.get("type")
    names = {"seed": ("harvestcrops", "harvestcroptype"),
             "tree": ("harvesttrees", "harvesttreetype"),
             "animal": ("harvestanimals", "harvestanimaltype")}
    if item_type in names:
        total, unique = names[item_type]
        increment_ribbon(save, total)
        _record_unique(save, unique, item["code"])
    if item_type == "seed":
        subtype = item.get("subtype")
        if subtype in ("flowers", "flower"):
            increment_ribbon(save, "harvestflowers")
        elif subtype in ("vegetable", "vegetables"):
            increment_ribbon(save, "vegetablevirtuoso")
        elif subtype == "fruit":
            increment_ribbon(save, "foremostfruitfarmer")
        if (object_state or {}).get("isJumbo"):
            increment_ribbon(save, "harvestfertilizedcrop")
    target = get_item_by_code(item.get("masteryTarget")) if item.get("masteryTarget") else item
    if target is None or str(target.get("mastery")).lower() != "true" or not target.get("masteryLevel"):
        return
    ensure_state(save)
    code = target["code"]
    amount = min(5, max(0, int(item.get("masteryYield") or 0)))
    if amount:
        count = int(save["userInfo"]["player"]["masteryCounters"].get(code, 0)) + amount
        _set_counter(save, code, count, target["masteryLevel"], kind="Mastery", xml=False)


def record_coins(save, *, earned=0, spent=0):
    # The action's base income/cost is counted, before ribbon rewards are paid.
    if earned > 0:
        increment_ribbon(save, "coinsearned", earned)
    if spent > 0:
        increment_ribbon(save, "coinsspent", spent)


def record_gift(save, item):
    _record_unique(save, "uniquegifts", item["code"])


def record_help(save, action_type):
    increment_ribbon(save, "helpfriends")
    if action_type == "fert":
        increment_ribbon(save, "fertilizecrop")


def refresh_owned(save, neighbor_count=None):
    """Ownership ribbons use the farm's real objects, including placed gifts."""
    from world_travel import worlds
    counts = {name: 0 for name in ("boughtbuildings", "boughtdecorations", "fencedin", "baledout",
                                  "placeflowerdecorations", "catlady", "gearhead")}
    for obj in (obj for world in worlds(save) for obj in world["objectsArray"]):
        item = get_item_by_name(obj.get("itemName")) if obj.get("itemName") else None
        if item is None:
            continue
        item_type, subtype = item.get("type"), item.get("subtype")
        if item_type == "building":
            counts["boughtbuildings"] += 1
        if item_type == "decoration":
            counts["boughtdecorations"] += 1
        if str(item.get("fence")).lower() == "true":
            counts["fencedin"] += 1
        if subtype == "haybale":
            counts["baledout"] += 1
        if subtype == "flowerdeco":
            counts["placeflowerdecorations"] += 1
        if item_type == "animal" and subtype == "cat":
            counts["catlady"] += 1
        if item_type == "vehicle":
            counts["gearhead"] += 1
    for name, count in counts.items():
        set_ribbon_count(save, name, count)
    stats = save["userInfo"]["player"].setdefault("stats", {})
    stats["buildings"] = counts["boughtbuildings"]
    if neighbor_count is not None:
        set_ribbon_count(save, "haveneighbors", neighbor_count)


def increment_daily_counter(save, group, category, action, amount, day):
    """DailyStats is separate telemetry; world actions already count ribbons."""
    amount = int(amount)
    if amount < 0 or amount > 100000:
        raise ValueError("Daily counter increments must be nonnegative and bounded.")
    fields = [str(value) for value in (group, category, action, day)]
    if any(len(value) > 80 for value in fields):
        raise ValueError("Daily counter identifiers are too long.")
    daily = save.setdefault("dailyStats", {})
    key = ":".join(fields)
    daily[key] = int(daily.get(key, 0)) + amount
