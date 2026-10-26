"""Live God Barn farming actions on detached saves, using recovered game rules.

No player/session module, save file write, device-clock change, random breeding
odds or background loop is used. apply() returns a new save for the existing
God Barn revision/snapshot transaction to commit. now is Unix seconds.
"""
import copy
from functools import lru_cache
import math
from pathlib import Path
import time
import zlib

import pyamf
import engine
import items
import peaceful
import progression
import quests
from bundle import XML_DIR

OPERATION_FIELDS = {
    "bulk_harvest": {"target"},
    "building": {"buildingId", "action", "objectId", "itemCode", "source", "quantity"},
}
_KINDS = {"HorseStableBuilding": "stable", "HorseStableBuildingFinished": "stable", "OrchardBuilding": "orchard",
          "OrchardConstructionBuilding": "orchard"}
_GROUPS = {"giftbox": -1, "storage": -2}


def _groups(save):
    import storage
    return {**_GROUPS, "storage": storage.active_inventory_id(save)}


def _integer(value, label, minimum=1, maximum=2_147_483_647):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or int(value) != value or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be a whole number from {minimum} to {maximum}.")
    return int(value)


def _now(value):
    value = time.time() if value is None else value
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("The farming clock must be finite Unix seconds.")
    return value


def _objects(save):
    objects = save["world"]["objectsArray"]
    if not isinstance(objects, list) or not isinstance(save["userInfo"]["player"], dict):
        raise ValueError("This farm does not have a supported world/player.")
    ids = [obj.get("id") for obj in objects if isinstance(obj, dict)]
    if len(ids) != len(objects) or len(set(ids)) != len(ids):
        raise ValueError("Farm object IDs must be unique.")
    return objects


def _true(value):
    return value is True or value == "true"


@lru_cache(maxsize=1)
def _storage_config():
    raw = zlib.decompress((Path(XML_DIR) / "gz/v855098/storageConfig.amf.gz").read_bytes())
    records = pyamf.get_decoder(pyamf.AMF3, raw).readElement()["storage"]["StorageBuilding"]
    return {record["name"]: record for record in records}


def _list(value):
    return value if isinstance(value, list) else ([] if value is None else [value])


def _kind(obj):
    item = items.get_item_by_name(obj.get("itemName"))
    if item and item.get("className") == "HorseStableBuildingFinished" and item.get("name") != "xukhorsestable_finished":
        return None, None
    return (_KINDS.get(item.get("className") or obj.get("className")), item) if item else (None, None)


def _built(obj, item):
    if obj.get("isFullyBuilt") is False or obj.get("state") in ("construction", "constructing"):
        return False
    if item.get("finishedName") or item.get("className") == "OrchardConstructionBuilding":
        return False
    if item.get("className") == "HorseStableBuilding":
        # The recovered stable constructor starts incomplete. A bare timer by
        # itself cannot substitute for the explicit completion flag.
        return obj.get("isFullyBuilt") is True
    return True


def _capacity(obj, item, kind):
    base = int(item.get("capacity") or 0)
    if kind == "stable":
        level = obj.get("expansionLevel", item.get("storageSize", 1))
        level = int(level) if str(level).isdigit() else 1
        return max(base, {1: 20, 2: 25, 3: 30, 4: 35, 5: 40}.get(level, base))
    finished = items.get_item_by_name(item.get("finishedName")) if item.get("finishedName") else item
    return int((finished or {}).get("capacity") or base)


def _contains_keyword(value, keyword):
    if isinstance(value, str):
        return keyword in value.replace(",", " ").split()
    if isinstance(value, dict):
        return any((key == keyword and _true(val)) or _contains_keyword(val, keyword) for key, val in value.items())
    return any(_contains_keyword(val, keyword) for val in value) if isinstance(value, list) else False


def _accepted(building_item, kind, candidate):
    if not candidate:
        return False
    config = _storage_config()["horses" if kind == "stable" else "orchard"]
    if kind == "stable":
        return candidate.get("type") == "animal" and candidate["name"] in config.get("itemName", [])
    denied = config.get("denyKeyword")
    return (candidate.get("type") == "tree" and not (denied and
            (_contains_keyword(candidate.get("keywords"), denied) or _contains_keyword(candidate.get("keyword"), denied) or _true(candidate.get(denied)))))


def _entry(value):
    if (not isinstance(value, list) or len(value) < 3 or not isinstance(value[1], list) or not isinstance(value[2], list)):
        raise ValueError("Inventory metadata must contain quantity, sender IDs and extra data.")
    _integer(value[0], "Stored quantity", minimum=0)
    return value


def _content_rows(save, obj):
    rows = obj.get("contents", [])
    if not isinstance(rows, list):
        raise ValueError("Building contents must be an array.")
    result = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("itemCode"), str) or row["itemCode"] in seen:
            raise ValueError("Building content codes must be unique.")
        _integer(row.get("numItem"), "Contained quantity", minimum=0)
        seen.add(row["itemCode"])
        result.append(copy.deepcopy(row))
    ledger = save["userInfo"]["player"].get("storageData", {}).get(str(obj["id"]))
    if isinstance(ledger, dict):
        # Positive storage IDs are also server-owned. Recover a legacy empty
        # snapshot from this ledger instead of silently deleting its occupants.
        for code, entry in ledger.items():
            _entry(entry)
            if code not in seen and entry[0] > 0:
                result.append({"itemCode": code, "numItem": entry[0]})
            elif code in seen and next(r["numItem"] for r in result if r["itemCode"] == code) != entry[0]:
                raise ValueError("Building contents and inventory disagree; restore a consistent snapshot first.")
    return result


def _ledger(save, obj):
    rows = _content_rows(save, obj)
    obj["contents"] = rows
    data = save["userInfo"]["player"].setdefault("storageData", {})
    ledger = data.setdefault(str(obj["id"]), {})
    for row in rows:
        ledger.setdefault(row["itemCode"], [row["numItem"], [], []])
    return ledger


def _ready(obj, item, now):
    grow = peaceful.grow_seconds(item)
    planted = obj.get("plantTime")
    if (grow is None or isinstance(planted, bool) or not isinstance(planted, (int, float)) or not math.isfinite(planted)):
        return False
    return obj.get("state") in ("grown", "ripe") or now - planted / 1000 >= grow


def _resource(obj, target, now):
    item = items.get_item_by_name(obj.get("itemName"))
    if obj.get("deleted") or not item or item.get("type") != target or peaceful.grow_seconds(item) is None:
        return None
    if (obj.get("className") in _KINDS or item.get("className") == "CashGrowableBaby"
            or obj.get("state") in ("construction", "withered", "fallow", "plowed")):
        return None
    return item


def _parts(item, kind):
    storage_type = (item.get("storageType") or {}).get("itemClass")
    config = _storage_config().get(storage_type or ("horses" if kind == "stable" else "orchard_construct"), {})
    return [{"name": row["value"], "code": (items.get_item_by_name(row["value"]) or {}).get("code"),
             "needed": int(row["need"])} for row in _list(config.get("itemName"))
            if isinstance(row, dict) and _true(row.get("part"))]


def _offspring(save, rows, kind):
    parents = [items.get_item_by_code(row["itemCode"]) for row in rows if row["numItem"] > 0]
    if kind == "stable" and not (any(_true((item or {}).get("stallion")) for item in parents)
            or save["userInfo"]["player"].get("actionCounts", {}).get("hasWanderingStallion") == 1):
        return []
    choices = {}
    for item in parents:
        if not item:
            continue
        if kind == "orchard":
            child = items.get_item_by_code(item.get("nextLevel")) if item.get("nextLevel") else None
            if child and child.get("type") != "tree":
                child = None
        else:
            relation = item.get("foal") or item.get("baby")
            child = items.get_item_by_name(relation) or items.get_item_by_code(relation) if relation else None
            if child and child.get("type") != "animal":
                child = None
        if child and child.get("code") not in (None, "", "XX"):
            choices.setdefault(child["code"], {"code": child["code"], "itemName": child["name"], "name": child.get("displayName") or child["name"]})
    return list(choices.values())


def inspect(save, now=None):
    now = _now(now)
    objects = _objects(save)
    result = {"bulk": {}, "buildings": [], "warnings": []}
    for target, item_type in (("animals", "animal"), ("trees", "tree")):
        total = [obj for obj in objects if _resource(obj, item_type, now)]
        ready = [obj["id"] for obj in total if _ready(obj, items.get_item_by_name(obj["itemName"]), now)]
        result["bulk"][target] = {"total": len(total), "ready": len(ready), "ids": ready}
    for obj in objects:
        kind, item = _kind(obj)
        if not kind or obj.get("deleted"):
            continue
        try:
            rows = _content_rows(save, obj)
            built = _built(obj, item)
            count = sum(row["numItem"] for row in rows)
            if any(row["numItem"] > 0 and not _accepted(item, kind, items.get_item_by_code(row["itemCode"])) for row in rows):
                result["warnings"].append(f"Building {obj['id']} contains unsupported occupants; unload them before harvesting.")
            world = [{"id": candidate["id"], "name": candidate["itemName"], "code": definition["code"]}
                     for candidate in objects if candidate["id"] != obj["id"] and not candidate.get("deleted")
                     and (definition := items.get_item_by_name(candidate.get("itemName"))) and _accepted(item, kind, definition)]
            inventory = []
            for source, group in _groups(save).items():
                for code, value in save["userInfo"]["player"].get("storageData", {}).get(str(group), {}).items():
                    definition = items.get_item_by_code(code)
                    if _entry(value)[0] > 0 and _accepted(item, kind, definition):
                        inventory.append({"source": source, "code": code, "name": definition["name"], "quantity": value[0]})
            result["buildings"].append({"id": obj["id"], "itemName": item["name"], "name": item.get("displayName") or item["name"],
                "kind": kind, "built": built, "capacity": _capacity(obj, item, kind), "count": count,
                "ready": built and count > 0 and _ready(obj, item, now),
                "growSeconds": peaceful.grow_seconds(item), "contents": [{**row, "quantity": row["numItem"],
                    "itemName": (items.get_item_by_code(row["itemCode"]) or {}).get("name"),
                    "name": (items.get_item_by_code(row["itemCode"]) or {}).get("name", row["itemCode"])} for row in rows if row["numItem"] > 0],
                "loadableWorld": world, "loadableInventory": inventory, "offspring": _offspring(save, rows, kind), "parts": _parts(item, kind)})
        except (ValueError, TypeError, KeyError) as error:
            result["warnings"].append(f"Building {obj['id']}: {error}")
    return result


def _harvest_item(save, item, obj, count=1):
    coins = max(0, int(item.get("coinYield") or 0)) * count
    engine.apply_coins_diff(save, coins)
    if isinstance(save.get("questState"), dict):
        quests.record_action(save, "harvestByCode", item["code"], count)
    progression.record_coins(save, earned=coins)
    for _ in range(count):
        progression.record_harvest(save, item, obj)
    return coins


def _transfer(save, code, quantity, origin, destination):
    data = save["userInfo"]["player"].setdefault("storageData", {})
    source = data.get(str(origin), {}).get(code)
    if source is None or _entry(source)[0] < quantity:
        raise ValueError("There are not enough items in the selected source.")
    target = data.get(str(destination), {})
    if code in target:
        _integer(_entry(target[code])[0] + quantity, "Destination quantity", minimum=0)
    moved = copy.deepcopy(source)
    remaining = source[0] - quantity
    sender_count = len(source[1]) if not remaining else min(1, len(source[1]))
    moved[0], moved[1], moved[2] = quantity, source[1][:sender_count], source[2][:quantity]
    source[0] = remaining
    del source[1][:sender_count]
    del source[2][:quantity]
    if not remaining:
        del data[str(origin)][code]
    target = data.setdefault(str(destination), {})
    if code not in target:
        target[code] = moved
    else:
        row = _entry(target[code]); row[0] += quantity; row[1].extend(moved[1]); row[2].extend(moved[2])
    return moved


def _set_count(obj, code, quantity):
    row = next((row for row in obj["contents"] if row["itemCode"] == code), None)
    if row is None:
        row = {"itemCode": code, "numItem": 0}; obj["contents"].append(row)
    row["numItem"] = quantity
    return row


def _building_harvest(save, obj, item, kind, now):
    rows = _content_rows(save, obj)
    positive = [row for row in rows if row["numItem"] > 0]
    if not _built(obj, item) or not positive or not _ready(obj, item, now):
        raise ValueError("This completed building is not ready to harvest.")
    if sum(row["numItem"] for row in positive) > _capacity(obj, item, kind):
        raise ValueError("This building exceeds its original capacity; unload excess occupants before harvesting.")
    for row in positive:
        if not _accepted(item, kind, items.get_item_by_code(row["itemCode"])):
            raise ValueError("The building contains an unsupported occupant; unload it before harvesting.")
    total = sum(_harvest_item(save, items.get_item_by_code(row["itemCode"]), obj, row["numItem"]) for row in positive)
    # HarvestableStorageBuilding also carries a possible mastery track of its own.
    progression.record_harvest(save, item, obj)
    obj.update(state="bare", plantTime=math.floor(now * 1000))
    return total


def _validate_rewards(save):
    player = save["userInfo"]["player"]
    for field in ("gold", "xp", "cash"):
        _integer(player.get(field, 0), f"Resulting {field}", minimum=0)


def harvest_for_game(save, obj, now=None):
    """Handle original client building harvests in place; retries never pay twice.

    Returns False for unrelated objects. Unlike detached Barn previews this keeps
    the ordinary transient goal response for the current AMF transaction.
    """
    kind, item = _kind(obj)
    if not kind:
        return False
    now = _now(now)
    rows = _content_rows(save, obj)
    if _built(obj, item) and any(row["numItem"] > 0 for row in rows) and _ready(obj, item, now):
        _building_harvest(save, obj, item, kind, now)
        _validate_rewards(save)
    return True


def apply(save, operation, now=None):
    now = _now(now)
    if not isinstance(operation, dict) or operation.get("type") not in OPERATION_FIELDS:
        raise ValueError("Choose a supported live farming operation.")
    if operation.keys() - OPERATION_FIELDS[operation["type"]] - {"type"}:
        raise ValueError("The farming operation contains unexpected fields.")
    result = copy.deepcopy(save)
    objects = _objects(result)
    warnings = ["No collection-drop probabilities or bonus multipliers are invented."]
    pending = copy.deepcopy(result.get("_progressionResponse"))
    if operation["type"] == "bulk_harvest":
        target = operation.get("target")
        if target not in ("animals", "trees"):
            raise ValueError("Choose animals or trees for bulk harvesting.")
        selected = [(obj, _resource(obj, target[:-1] if target == "trees" else "animal", now)) for obj in objects]
        selected = [(obj, item) for obj, item in selected if item and _ready(obj, item, now)]
        total = 0
        for obj, item in selected:
            total += _harvest_item(result, item, obj)
            obj.update(state="bare", plantTime=math.floor(now * 1000))
        summary = f"Harvested {len(selected)} ready {target} for {total} base coins; normal ribbon/mastery rewards included."
    else:
        ident = _integer(operation.get("buildingId"), "Building ID", minimum=0)
        obj = next((obj for obj in objects if obj["id"] == ident and not obj.get("deleted")), None)
        kind, item = _kind(obj or {})
        if not kind:
            raise ValueError("Choose an existing Horse Stable or Orchard.")
        action = operation.get("action")
        if action == "complete":
            if _built(obj, item):
                raise ValueError("This building is already complete.")
            _ledger(result, obj)
            part_codes = {row["code"] for row in _parts(item, kind)}
            for row in obj["contents"]:
                if row["itemCode"] in part_codes:
                    row["numItem"] = 0
                    result["userInfo"]["player"]["storageData"][str(ident)].pop(row["itemCode"], None)
            if item.get("finishedName"):
                finished = items.get_item_by_name(item["finishedName"])
                if not finished:
                    raise ValueError("The completed building definition is missing.")
                obj.update(itemName=finished["name"], className=finished["className"])
            obj.update(isFullyBuilt=True, state="built")
            obj.setdefault("expansionParts", {})
            summary = "Completed construction as a God Barn cheat; no parts or currency charged."
        elif action in ("harvest", "offspring"):
            choices = _offspring(result, _content_rows(result, obj), kind)
            child_code = operation.get("itemCode")
            if action == "offspring" and child_code not in {row["code"] for row in choices}:
                raise ValueError("Choose offspring supported by these parents and a contained/wandering stallion where required.")
            coins = _building_harvest(result, obj, item, kind, now)
            summary = f"Harvested the {kind} for {coins} base coins; normal occupant mastery/ribbons included."
            if action == "offspring":
                child = items.get_item_by_code(child_code)
                import storage
                existing = result["userInfo"]["player"].get("storageData", {}).get(str(storage.GIFTBOX_ID), {}).get(child_code)
                if existing is not None:
                    _integer(_entry(existing)[0] + 1, "Offspring Gift Box quantity", minimum=0)
                storage.store_deposit_item_by_name(result, child["name"], 1, storage.GIFTBOX_ID)
                if kind == "stable":
                    result["userInfo"]["player"].get("actionCounts", {}).update(hasWanderingStallion=0)
                summary += f" Chose {child['name']} for the Gift Box as a deterministic God Barn cheat."
                warnings.append("Offspring selection is guaranteed by this cheat, not a recovered random chance.")
        elif action == "load":
            if not _built(obj, item):
                raise ValueError("Complete construction before loading occupants.")
            ledger = _ledger(result, obj)
            count = sum(row["numItem"] for row in obj["contents"])
            resource = None
            if operation.get("objectId") is not None:
                source_id = _integer(operation["objectId"], "Resource ID", minimum=0)
                resource = next((row for row in objects if row["id"] == source_id and not row.get("deleted")), None)
                candidate = items.get_item_by_name((resource or {}).get("itemName"))
                quantity = 1
            else:
                quantity = _integer(operation.get("quantity", 1), "Quantity", maximum=100000)
                candidate = items.get_item_by_code(operation.get("itemCode"))
            if not candidate or not _accepted(item, kind, candidate):
                raise ValueError("That item is not allowed by this building's original storage rules.")
            if count + quantity > _capacity(obj, item, kind):
                raise ValueError("This building has no capacity for that many occupants.")
            if operation.get("objectId") is not None and resource is None:
                raise ValueError("The selected farm resource is missing.")
            code = candidate["code"]
            incoming_time = math.floor(now * 1000)
            if resource is not None:
                entry = ledger.setdefault(code, [0, [], []]); _entry(entry)
                entry[0] = _integer(entry[0] + 1, "Contained quantity", minimum=0)
                entry[2].append({"godBarnStoredObject": copy.deepcopy(resource)})
                incoming_time = resource.get("plantTime", incoming_time)
                objects.remove(resource)
            else:
                group = _groups(result).get(operation.get("source", "giftbox"))
                if group is None:
                    raise ValueError("Choose Gift Box or storage as the source.")
                moved = _transfer(result, code, quantity, group, ident)
                if moved[2] and isinstance(moved[2][0], dict):
                    metadata = moved[2][0]
                    incoming_time = metadata.get("godBarnStoredObject", metadata).get("plantTime", incoming_time)
            _set_count(obj, code, ledger[code][0])
            if kind == "stable":
                obj.update(state="bare", plantTime=incoming_time)
            elif count == 0:
                obj.update(state="bare", plantTime=math.floor(now * 1000))
            elif _true(item.get("stuffingPrevention")):
                if item.get("stuffingPreventionPrereq"):
                    raise ValueError("This Orchard has a conditional stuffing-prevention rule; its prerequisite cannot be resolved by this tool.")
                grow = peaceful.grow_seconds(item)
                delay_ms = math.floor(grow * 1000 * 0.04 + 0.5)
                base = math.floor(now * 1000) - grow * 1000 if _ready(obj, item, now) else obj["plantTime"]
                obj.update(state="bare", plantTime=min(math.floor(now * 1000), base + delay_ms))
            summary = f"Loaded {quantity} {candidate['name']} into the {kind}; source quantity removed exactly once."
        elif action == "unload":
            quantity = _integer(operation.get("quantity", 1), "Quantity", maximum=100000)
            ledger = _ledger(result, obj)
            code = operation.get("itemCode")
            if not isinstance(code, str) or code not in ledger:
                raise ValueError("Choose an item contained in this building.")
            _transfer(result, code, quantity, ident, -1)
            _set_count(obj, code, ledger.get(code, [0])[0])
            if not any(row["numItem"] > 0 for row in obj["contents"]):
                obj["state"] = "built"
            summary = f"Unloaded {quantity} {code} into the Gift Box with inventory metadata preserved."
        else:
            raise ValueError("Choose complete, load, unload, harvest or offspring.")
    if pending is None:
        result.pop("_progressionResponse", None)
    else:
        result["_progressionResponse"] = pending
    _validate_rewards(result)
    return {"save": result, "summary": summary, "warnings": warnings}
