"""Ripe-and-waiting crops, using the original client's no-withering controls.

Plant timestamps stay in real milliseconds. Growth, animals, trees and equipment
cooldowns continue normally; only crop withering is disabled. No device clock or
global game clock is changed.
"""

import copy
import math

POLICY = "ripe_and_waiting"


def enabled(save):
    mode = save.get("peacefulMode")
    return mode.get("enabled", True) is not False if isinstance(mode, dict) else True


def grow_seconds(item):
    from game_settings import get_farming_number
    try:
        seconds = (float(item["growTime"])
                   * get_farming_number("inGameDaySeconds", 82800)
                   * get_farming_number("growMultiplier", 1))
        return seconds if math.isfinite(seconds) and seconds > 0 else None
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def refresh(save, now=None):
    """Persist the policy and mature/revive known crops without moving timers."""
    if not enabled(save):
        return False
    from engine import timestamp_now
    from items import get_item_by_name
    now = timestamp_now() if now is None else now
    changed = False
    mode = save.get("peacefulMode")
    if not isinstance(mode, dict):
        mode = save["peacefulMode"] = {}
        changed = True
    for key, value in (("enabled", True), ("policy", POLICY)):
        if mode.get(key) != value:
            mode[key], changed = value, True
    wither = save.get("witherOn")
    if not isinstance(wither, dict):
        wither = {"farm": bool(wither) if wither is not None else True}
    if "originalWitherOn" not in mode:
        mode["originalWitherOn"], changed = copy.deepcopy(wither), True
    protected = {key: False for key in wither}
    protected["farm"] = False
    protected[save.get("userInfo", {}).get("currentWorldType") or "farm"] = False
    if save.get("witherOn") != protected:
        save["witherOn"], changed = protected, True
    for obj in save.get("world", {}).get("objectsArray", []):
        if (obj.get("className") != "Plot" or obj.get("deleted")
                or obj.get("state") not in ("planted", "grown", "withered")):
            continue
        item = get_item_by_name(obj.get("itemName"))
        if not item or item.get("type") != "seed":
            continue
        grow = grow_seconds(item)
        planted = obj.get("plantTime")
        if (grow is None or isinstance(planted, bool) or not isinstance(planted, (int, float))
                or not math.isfinite(planted)):
            continue
        if obj["state"] == "withered" or now - planted / 1000 >= grow:
            if obj["state"] != "grown":
                obj["state"], changed = "grown", True
    return changed


def set_enabled(save, value, now=None):
    if not isinstance(value, bool):
        raise ValueError("Peaceful mode must be on or off.")
    from engine import timestamp_now
    from items import get_item_by_name
    now = timestamp_now() if now is None else now
    if value:
        if not isinstance(save.get("peacefulMode"), dict):
            save["peacefulMode"] = {}
        save["peacefulMode"]["enabled"] = True
        refresh(save, now)
        return
    # Give already ripe crops a full ordinary harvest window when protection is
    # switched off; months spent protected must not wither them immediately.
    was_enabled = enabled(save)
    if was_enabled:
        refresh(save, now)
    mode = save.setdefault("peacefulMode", {})
    mode.update(enabled=False, policy=POLICY)
    save["witherOn"] = copy.deepcopy(mode.pop("originalWitherOn", save.get("witherOn", {"farm": True})))
    if was_enabled:
        for obj in save.get("world", {}).get("objectsArray", []):
            if obj.get("className") == "Plot" and obj.get("state") == "grown":
                item = get_item_by_name(obj.get("itemName"))
                grow = grow_seconds(item) if item else None
                if grow:
                    obj["plantTime"] = math.floor((now - grow) * 1000)
