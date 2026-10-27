"""Detached, deterministic cheats for FarmVillage save *copies*.

This module deliberately has no imports from the game and performs no filesystem
or network access. The caller owns copying, persistence, snapshots and export.
"""

from __future__ import annotations

import copy
import math
import time

try:
    from .progression_tools import ProgressionTools
    from .helper_tools import HelperTools
except ImportError:
    from progression_tools import ProgressionTools
    from helper_tools import HelperTools


MAX_BALANCE = 2_147_483_647
GRANTABLE_TYPES = frozenset({"animal", "decoration", "tree", "building", "vehicle", "seed", "fuel", "turbo"})


def grant_refusal(item):
    """Return why ordinary inventory grants refuse this catalog record, or None."""
    code = item.get("code")
    if item.get("type") not in GRANTABLE_TYPES:
        return f'Category "{item.get("type") or "unknown"}" is not supported for gifts yet.'
    if not isinstance(code, str) or not code or code == "XX" or ":" in code or len(code) > 128:
        return "This record has no usable item code, so God Barn cannot gift it."
    return None


def _number(value, label, *, minimum=None):
    try:
        finite = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(f"{label} must be a finite number.")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} must be at least {minimum}.")
    return value


def _integer(value, label, *, minimum=None, maximum=None):
    value = _number(value, label, minimum=minimum)
    if value != int(value):
        raise ValueError(f"{label} must be a whole number.")
    if maximum is not None and value > maximum:
        raise ValueError(f"{label} must be at most {maximum}.")
    return int(value)


def _pointer(key):
    return str(key).replace("~", "~0").replace("/", "~1")


def _changes(before, after, path=""):
    """Leaf changes with JSON-pointer paths, suitable for a human preview."""
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(before.keys() | after.keys()):
            child = f"{path}/{_pointer(key)}"
            if key not in before:
                result.append({"path": child, "before": None, "after": copy.deepcopy(after[key])})
            elif key not in after:
                result.append({"path": child, "before": copy.deepcopy(before[key]), "after": None})
            else:
                result.extend(_changes(before[key], after[key], child))
        return result
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        return [change for i, (a, b) in enumerate(zip(before, after)) for change in _changes(a, b, f"{path}/{i}")]
    if before != after or type(before) is not type(after):
        return [{"path": path, "before": copy.deepcopy(before), "after": copy.deepcopy(after)}]
    return []


class CheatEngine:
    """Apply supported operations to a deep copy; never mutate the input save."""

    def __init__(self, catalog, rules, progression=None, farming_module=None, helpers=None):
        if not isinstance(catalog, list) or not all(isinstance(item, dict) for item in catalog):
            raise ValueError("The item catalog must be a list of objects.")
        if not isinstance(rules, dict):
            raise ValueError("The farming rules must be an object.")
        # The game's name lookup returns the first catalog match. Two historic
        # entries have duplicate names; use the same resolution for save parity.
        self.catalog = {}
        for item in catalog:
            if isinstance(item.get("name"), str):
                self.catalog.setdefault(item["name"], copy.deepcopy({key: value for key, value in item.items() if key != "archive"}))
        self.catalog_by_code = {}
        for item in self.catalog.values():
            if isinstance(item.get("code"), str) and item["code"] != "XX":
                self.catalog_by_code.setdefault(item["code"], item)
        entries = rules.get("levels")
        if not isinstance(entries, list) or not entries:
            raise ValueError("The rules need XP level thresholds.")
        self.levels = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("Each level threshold must be an object.")
            self.levels.append((_integer(entry.get("level"), "Level", minimum=1), _integer(entry.get("xp"), "Level XP", minimum=0, maximum=MAX_BALANCE)))
        self.levels.sort()
        if (self.levels[0] != (1, 0) or len(set(level for level, _ in self.levels)) != len(self.levels)
                or any(b[1] <= a[1] for a, b in zip(self.levels, self.levels[1:]))):
            raise ValueError("XP thresholds must start at level 1 / 0 XP and increase uniquely.")
        self.level_xp = dict(self.levels)
        self.higher_begin = _integer(rules.get("higherLevelBegin", 101 if self.levels[-1][0] == 100 else 0), "Higher-level beginning", minimum=0)
        self.higher_xp = _integer(rules.get("higherLevelXp", 1500000), "Higher-level XP", minimum=0)
        self.higher_step = _integer(rules.get("higherLevelStep", 100000), "Higher-level XP step", minimum=1)
        self.cash_level_cap = _integer(rules.get("highestLevelForFCReward", 250), "Level cash reward cap", minimum=0)
        self.day_seconds = _number(rules.get("inGameDaySeconds"), "In-game day seconds", minimum=1)
        self.grow_multiplier = _number(rules.get("growMultiplier", 1), "Grow multiplier", minimum=0.000001)
        self.wither_multiplier = _number(rules.get("witherMultiplier", 2.2), "Wither multiplier", minimum=1.000001)
        self.expansion_sizes = set()
        for item in self.catalog.values():
            if item.get("subtype") == "expand_farm":
                try:
                    size = float(item.get("squares"))
                    if math.isfinite(size) and size > 0 and size.is_integer():
                        self.expansion_sizes.add(int(size))
                except (TypeError, ValueError, OverflowError):
                    continue
        self.progression = ProgressionTools(self.catalog, progression)
        self.helpers = HelperTools(self.catalog, helpers)
        self.farming_module = farming_module

    def validate_save(self, save):
        if not isinstance(save, dict):
            raise ValueError("A save must be a JSON object.")
        user = save.get("userInfo")
        player = user.get("player") if isinstance(user, dict) else None
        world = save.get("world")
        if not isinstance(player, dict) or not isinstance(world, dict):
            raise ValueError("The save must contain userInfo.player and world objects.")
        uid = player.get("userId")
        if isinstance(uid, bool) or not isinstance(uid, (str, int)) or not str(uid).strip():
            raise ValueError("The copied save must have its original player UID.")
        for field in ("gold", "cash", "xp", "energy"):
            _integer(player.get(field), f"Player {field}", minimum=0)
        if "energyMax" in player:
            _integer(player["energyMax"], "Maximum energy", minimum=0)
        if "energyManager" in player:
            manager = player["energyManager"]
            if not isinstance(manager, dict):
                raise ValueError("player.energyManager must be an object.")
            if "turboChargers" in manager:
                _integer(manager["turboChargers"], "Turbo chargers", minimum=0)
        if "storageData" in player:
            if not isinstance(player["storageData"], dict):
                raise ValueError("player.storageData must be an object.")
            for inventory in player["storageData"].values():
                if not isinstance(inventory, dict):
                    raise ValueError("Every storage inventory must be an object.")
                for entry in inventory.values():
                    if (not isinstance(entry, list) or len(entry) != 3 or not isinstance(entry[1], list)
                            or not isinstance(entry[2], list)):
                        raise ValueError("Inventory metadata must be [quantity, sender IDs, extra data].")
                    _integer(entry[0], "Stored quantity", minimum=0)
        for field in ("sizeX", "sizeY"):
            _integer(world.get(field), f"World {field}", minimum=1)
        objects = world.get("objectsArray")
        if not isinstance(objects, list):
            raise ValueError("The save must contain world.objectsArray.")
        ids = set()
        for obj in objects:
            if not isinstance(obj, dict) or not isinstance(obj.get("className"), str):
                raise ValueError("Every world object must have a className.")
            object_id = _integer(obj.get("id"), "World object ID", minimum=0)
            if object_id in ids:
                raise ValueError("The save has duplicate world object IDs.")
            ids.add(object_id)

    def level_for_xp(self, xp):
        xp = _integer(xp, "XP", minimum=0)
        if self.higher_begin and xp >= self.higher_xp:
            return self.higher_begin + (xp - self.higher_xp) // self.higher_step
        return next(level for level, threshold in reversed(self.levels) if xp >= threshold)

    def _now(self, now):
        return _number(time.time() if now is None else now, "Current time", minimum=0)

    def crop_status(self, plot, now=None, *, peaceful=False):
        now = self._now(now)
        empty = {"eligible": False, "phase": "empty", "growSeconds": 0, "elapsedSeconds": 0, "progress": 0}
        if not isinstance(plot, dict) or plot.get("className") != "Plot" or plot.get("deleted"):
            return dict(empty, phase="unsupported")
        if not plot.get("itemName") or plot.get("state") in ("fallow", "plowed"):
            return empty
        item = self.catalog.get(plot.get("itemName"))
        if not item or item.get("type") != "seed" or plot.get("state") not in ("planted", "grown", "withered"):
            return dict(empty, phase="unsupported")
        try:
            days = float(item.get("growTime"))
            planted = _number(plot.get("plantTime"), "Crop plantTime")
            grow = days * self.day_seconds * self.grow_multiplier
            if not math.isfinite(grow) or grow <= 0:
                return dict(empty, phase="unsupported")
        except (TypeError, ValueError, OverflowError):
            return dict(empty, phase="unsupported")
        elapsed = max(0, now - planted / 1000)
        phase = "withered" if elapsed >= grow * self.wither_multiplier else "grown" if elapsed >= grow else "planted"
        if plot.get("state") == "withered":
            phase = "withered"
        if peaceful and (phase == "withered" or plot.get("state") == "grown"):
            phase = "grown"
        return {"eligible": True, "phase": phase, "growSeconds": grow, "elapsedSeconds": elapsed,
                "progress": min(1, elapsed / grow)}

    def summarize(self, save, now=None):
        self.validate_save(save)
        now = self._now(now)
        user, world = save["userInfo"], save["world"]
        player = user["player"]
        storage = player.get("storageData", {})
        count = 0
        if isinstance(storage, dict):
            for inventory in storage.values():
                if isinstance(inventory, dict):
                    for entry in inventory.values():
                        if (isinstance(entry, list) and entry and isinstance(entry[0], (int, float))
                                and not isinstance(entry[0], bool) and math.isfinite(entry[0])):
                            count += max(0, int(entry[0]))
        attrs = user.get("attr") if isinstance(user.get("attr"), dict) else {}
        return {"uid": player["userId"], "name": attrs.get("name", "Farmer"),
                **{key: player[key] for key in ("gold", "cash", "xp", "energy")},
                "energyMax": player.get("energyMax", 50), "level": self.level_for_xp(player["xp"]),
                "turboChargers": player.get("energyManager", {}).get("turboChargers", 0),
                "sizeX": world["sizeX"], "sizeY": world["sizeY"], "inventoryCount": count,
                "objectCount": len(world["objectsArray"]),
                "progression": self.progression.totals(save),
                "capabilities": {"farming": self.farming_module is not None},
                "plots": [{"id": obj["id"], "itemName": obj.get("itemName"), "state": obj.get("state"),
                           **self.crop_status(obj, now, peaceful=save.get("peacefulMode", {}).get("enabled") is True)}
                          for obj in world["objectsArray"] if obj["className"] == "Plot"]}

    def apply(self, save, operation, now=None):
        self.validate_save(save)
        now = self._now(now)
        if not isinstance(operation, dict) or not isinstance(operation.get("type"), str):
            raise ValueError("An operation needs a type.")
        schemas = {"balance": {"field", "mode", "amount"}, "level": {"level"},
                   "crops": {"action", "ids", "hours", "protect"}, "grant": {"item", "quantity", "group"},
                   "expand": {"size"}, "preset": {"name"}, "peaceful": {"enabled"},
                   "progression": {"kind", "code", "count"},
                   "collection": {"name", "action"}, "quest": {"name", "task"}}
        if self.farming_module is not None:
            schemas.update(self.farming_module.OPERATION_FIELDS)
        kind = operation["type"]
        if kind not in schemas:
            raise ValueError(f"Unsupported cheat operation: {kind}.")
        unexpected = operation.keys() - schemas[kind] - {"type"}
        if unexpected:
            raise ValueError(f"Unexpected operation field: {sorted(unexpected)[0]}.")
        result = copy.deepcopy(save)
        warnings = []
        summary = getattr(self, f"_{kind}")(result, operation, now, warnings)
        if result.get("peacefulMode", {}).get("enabled") is True:
            self._refresh_peaceful(result, now)
        self.validate_save(result)
        return {"save": result, "changes": _changes(save, result), "summary": summary, "warnings": warnings}

    def progression_page(self, save, **query):
        self.validate_save(save)
        return self.progression.page(save, **query)

    def helpers_page(self, save, **query):
        self.validate_save(save)
        return self.helpers.page(save, **query)

    def _collection(self, save, op, now, warnings):
        return self.helpers.fill_collection(save, op, warnings)

    def _quest(self, save, op, now, warnings):
        return self.helpers.finish_quest_task(save, op, warnings)

    def farming_status(self, save, now=None):
        self.validate_save(save)
        if self.farming_module is None:
            return {"available": False, "supported": False, "reason": "Harvest and special-building tools use the live game's recovered rules. Open God Barn from the game to use them.", "buildings": []}
        result = self.farming_module.inspect(copy.deepcopy(save), now=self._now(now))
        for building in result.get("buildings", []):
            item = self.catalog.get(building.get("itemName"), {})
            building.update(displayName=item.get("displayName") or building.get("itemName"), image=item.get("image"))
            for key in ("contents", "loadableWorld", "loadableInventory", "offspring"):
                for entry in building.get(key, []):
                    item = (self.catalog.get(entry.get("name") or entry.get("itemName"))
                            or self.catalog_by_code.get(entry.get("code") or entry.get("itemCode"), {}))
                    entry.update(displayName=item.get("displayName") or item.get("name") or entry.get("name"), image=item.get("image"))
        return {**result, "available": True, "supported": True}

    def _progression(self, save, op, now, warnings):
        return self.progression.advance(save, op, self, now, warnings)

    def _farming_action(self, save, op, now, warnings):
        if self.farming_module is None:
            raise ValueError("Open the live God Barn to use these farming tools.")
        result = self.farming_module.apply(save, op, now=now)
        if result.get("save") is not save:
            replacement = result["save"]
            self.validate_save(replacement)
            save.clear()
            save.update(replacement)
        warnings.extend(result.get("warnings", []))
        return result["summary"]

    _bulk_harvest = _farming_action
    _building = _farming_action

    def _bounded(self, value, field, warnings):
        if value > MAX_BALANCE:
            warnings.append(f"{field} capped at {MAX_BALANCE:,}, the Flash integer limit.")
        return int(min(MAX_BALANCE, max(0, value)))

    def _refresh_peaceful(self, save, now):
        mode = save.setdefault("peacefulMode", {})
        mode.update(enabled=True, policy="ripe_and_waiting")
        wither = save.get("witherOn", {"farm": True})
        if not isinstance(wither, dict):
            wither = {"farm": bool(wither)}
        mode.setdefault("originalWitherOn", copy.deepcopy(wither))
        save["witherOn"] = {**{key: False for key in wither}, "farm": False}
        for obj in save["world"]["objectsArray"]:
            status = self.crop_status(obj, now, peaceful=True)
            if status["eligible"] and status["phase"] == "grown":
                obj["state"] = "grown"

    def _peaceful(self, save, op, now, warnings):
        value = op.get("enabled")
        if not isinstance(value, bool):
            raise ValueError("Peaceful mode must be on or off.")
        mode = save.setdefault("peacefulMode", {})
        was_enabled = mode.get("enabled") is True
        if value:
            self._refresh_peaceful(save, now)
            return "Peaceful mode on: crops grow normally and stay ripe until you harvest."
        if was_enabled:
            self._refresh_peaceful(save, now)
        mode.update(enabled=False, policy="ripe_and_waiting")
        save["witherOn"] = copy.deepcopy(mode.pop("originalWitherOn", save.get("witherOn", {"farm": True})))
        if was_enabled:
            for obj in save["world"]["objectsArray"]:
                status = self.crop_status(obj, now, peaceful=True)
                if status["eligible"] and obj.get("state") == "grown":
                    obj["plantTime"] = math.floor((now - status["growSeconds"]) * 1000)
        warnings.append("Normal crop withering resumes after returning to a fresh game view. Ripe crops receive a full harvest window.")
        return "Peaceful mode off: ordinary crop timers restored."

    def _balance(self, save, op, now, warnings):
        field, mode = op.get("field"), op.get("mode")
        if field not in ("gold", "cash", "xp", "energy", "turboChargers"):
            raise ValueError("Choose gold, cash, xp, energy, or turboChargers.")
        if mode not in ("add", "set", "multiply"):
            raise ValueError("Balance mode must be add, set, or multiply.")
        amount = _number(op.get("amount"), "Amount")
        if mode != "add" and amount < 0:
            raise ValueError("Set amounts and multipliers cannot be negative.")
        if mode != "multiply":
            _integer(amount, "Amount")
        player = save["userInfo"]["player"]
        if field == "turboChargers":
            if "energyManager" not in player:
                player["energyManager"] = {}
            if not isinstance(player["energyManager"], dict):
                raise ValueError("player.energyManager must be an object.")
            target = player["energyManager"]
            before = _integer(target.get(field, 0), "Turbo chargers", minimum=0)
        else:
            target, before = player, player[field]
        calculated = before + amount if mode == "add" else before * amount if mode == "multiply" else amount
        after = self._bounded(calculated, field, warnings)
        target[field] = after
        if field == "xp":
            gained = max(0, min(self.level_for_xp(after), self.cash_level_cap)
                         - min(self.level_for_xp(before), self.cash_level_cap))
            if gained:
                player["cash"] = self._bounded(player["cash"] + gained, "cash", warnings)
                warnings.append(f"Awarded {gained:,} Farm Cash for {gained:,} levels gained.")
        label = {"gold": "Coins", "cash": "Farm Cash", "xp": "XP", "energy": "Energy", "turboChargers": "Turbo charges"}[field]
        return f"{label}: {before:,} → {after:,}."

    def _level(self, save, op, now, warnings):
        level = _integer(op.get("level"), "Target level", minimum=1)
        if level not in self.level_xp and self.higher_begin and level >= self.higher_begin:
            target = self.higher_xp + (level - self.higher_begin) * self.higher_step
            if target > MAX_BALANCE:
                raise ValueError("This level exceeds the Flash XP limit.")
            return self._balance(save, {"field": "xp", "mode": "set", "amount": target}, now, warnings)
        if level not in self.level_xp:
            raise ValueError("That level is not in the original game's XP table.")
        self._balance(save, {"field": "xp", "mode": "set", "amount": self.level_xp[level]}, now, warnings)
        return f"Set XP to {self.level_xp[level]:,}, the start of level {level:,}."

    def _crops(self, save, op, now, warnings):
        action = op.get("action")
        if action not in ("ripen", "unwither", "advance", "fertilize"):
            raise ValueError("Crop action must be ripen, unwither, advance, or fertilize.")
        ids = op.get("ids")
        if ids is not None and ids != "all" and not isinstance(ids, list):
            raise ValueError("Crop IDs must be a list or all.")
        requested = None
        if isinstance(ids, list):
            requested = [_integer(value, "Crop ID", minimum=0) for value in ids]
            if len(requested) != len(set(requested)):
                raise ValueError("Choose each crop ID only once.")
        protect = op.get("protect", True)
        if not isinstance(protect, bool):
            raise ValueError("Harvest protection must be true or false.")
        hours = _number(op.get("hours", 0), "Hours", minimum=0)
        if action == "advance" and (hours <= 0 or hours > 87600):
            raise ValueError("Advance time must be more than 0 and at most 87,600 hours.")
        objects = save["world"]["objectsArray"]
        if requested is not None:
            lookup = {obj["id"]: obj for obj in objects}
            if any(value not in lookup for value in requested):
                raise ValueError("One or more selected crop IDs do not exist in this copied save.")
            if any(not self.crop_status(lookup[value], now)["eligible"] for value in requested):
                raise ValueError("Selected IDs must refer to planted crops with known growth data.")
        count = 0
        skipped_withered = 0
        for obj in objects:
            if requested is not None and obj["id"] not in requested:
                continue
            status = self.crop_status(obj, now, peaceful=save.get("peacefulMode", {}).get("enabled") is True)
            if not status["eligible"]:
                continue
            grow = status["growSeconds"]
            if action == "unwither" and status["phase"] != "withered":
                continue
            if action in ("advance", "fertilize") and status["phase"] == "withered":
                skipped_withered += 1
                continue
            if action in ("ripen", "unwither"):
                obj["plantTime"], obj["state"] = math.floor((now - grow) * 1000), "grown"
            elif action == "fertilize":
                if obj.get("isJumbo") is True:
                    continue
                obj["isJumbo"] = True
            else:
                elapsed = status["elapsedSeconds"] + hours * 3600
                if protect:
                    elapsed = min(elapsed, grow)
                obj["plantTime"] = math.floor((now - elapsed) * 1000)
                peaceful = save.get("peacefulMode", {}).get("enabled") is True
                obj["state"] = "withered" if not peaceful and elapsed >= grow * self.wither_multiplier else "grown" if elapsed >= grow else "planted"
            count += 1
        if skipped_withered:
            warnings.append(f"Skipped {skipped_withered:,} withered crops; use Revive first.")
        if action == "advance" and not protect and save.get("peacefulMode", {}).get("enabled") is not True:
            warnings.append("Harvest protection was off; crops advanced past their wither timer may be withered.")
        if action in ("ripen", "unwither") or (action == "advance" and protect):
            warnings.append("Crop changes use this preview's timestamp. Crops keep growing; Peaceful mode keeps ripe harvests waiting.")
        verb = {"ripen": "Ripened", "unwither": "Revived", "advance": "Advanced", "fertilize": "Fertilized"}[action]
        return f"{verb} {count:,} crop{'s' if count != 1 else ''}" + (f" by {hours:g} hours." if action == "advance" else ".")

    def _grant(self, save, op, now, warnings):
        name = op.get("item")
        if not isinstance(name, str) or name not in self.catalog:
            raise ValueError("Choose an item from the copied item catalog.")
        item = self.catalog[name]
        refusal = grant_refusal(item)
        if refusal:
            raise ValueError(refusal)
        code = item.get("code")
        quantity = _integer(op.get("quantity"), "Quantity", minimum=1, maximum=100000)
        group = op.get("group", "giftbox")
        if group not in ("giftbox", "storage"):
            raise ValueError("Inventory group must be giftbox or storage.")
        player = save["userInfo"]["player"]
        storage = player.setdefault("storageData", {})
        if not isinstance(storage, dict):
            raise ValueError("player.storageData must be an object.")
        inventory = storage.setdefault("-1" if group == "giftbox" else "-2", {})
        if not isinstance(inventory, dict):
            raise ValueError("The target inventory must be an object.")
        entry = inventory.get(code)
        if entry is None:
            inventory[code] = [quantity, [], []]
        else:
            if (not isinstance(entry, list) or len(entry) != 3 or not isinstance(entry[1], list)
                    or not isinstance(entry[2], list)):
                raise ValueError("The existing item's inventory metadata is malformed.")
            current = _integer(entry[0], "Stored quantity", minimum=0)
            entry[0] = self._bounded(current + quantity, "Stored quantity", warnings)
        label = item.get("displayName") or name.replace("_", " ").title()
        warnings.append("An inventory grant does not bypass item placement, world, or special-feature requirements.")
        return f"Added {quantity:,} × {label} to {'the Gift Box' if group == 'giftbox' else 'home storage'}."

    def _expand(self, save, op, now, warnings):
        size = _integer(op.get("size"), "Farm size", minimum=1)
        if size not in self.expansion_sizes:
            raise ValueError("Choose an expansion size present in the original item catalog.")
        world = save["world"]
        if size < max(world["sizeX"], world["sizeY"]):
            raise ValueError("Land expansion cannot shrink a farm.")
        world["sizeX"], world["sizeY"] = size, size
        return f"Expanded the copied farm to {size} × {size} squares."

    def _preset(self, save, op, now, warnings):
        name = op.get("name")
        player = save["userInfo"]["player"]
        if name == "millionaire":
            for field, target in (("gold", 1000000), ("cash", 1000)):
                self._balance(save, {"field": field, "mode": "set", "amount": max(player[field], target)}, now, warnings)
            return "Millionaire: at least 1,000,000 coins and 1,000 Farm Cash."
        if name == "gentle":
            energy_max = _integer(player.get("energyMax", 50), "Maximum energy", minimum=0)
            self._balance(save, {"field": "energy", "mode": "set", "amount": max(player["energy"], energy_max)}, now, warnings)
            self._balance(save, {"field": "turboChargers", "mode": "add", "amount": 100}, now, warnings)
            self._crops(save, {"action": "ripen"}, now, warnings)
            return "Gentle Farmer: energy refilled, 100 turbo charges added, and planted crops ready."
        if name == "collector":
            favorites = ["cow", "chicken", "sheep", "apple", "cherry", "orange", "haybale", "barn", "tractor", "strawberry", "eggplant"]
            count = 0
            for item in favorites:
                if item in self.catalog:
                    self._grant(save, {"item": item, "quantity": 5, "group": "giftbox"}, now, warnings)
                    count += 1
            if not count:
                raise ValueError("The catalog has none of the Collector preset's classic items.")
            warnings[:] = list(dict.fromkeys(warnings))
            return f"Collector: five each of {count} classic farm items added to the Gift Box."
        raise ValueError("Choose the millionaire, gentle, or collector preset.")
