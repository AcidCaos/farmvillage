"""Lighthouse Cove's exact, finite Port material ladder.

The nonbuyable Port belongs to an imported owned snapshot.  This module never
creates one for the disclosed empty local starter.  ExpandFManager's original
TStoreItem/CompleteNow actions own levels 2--11; the incoming optimistic stage
is never authoritative.  Its one-day HarvestRewardGenerator has no recovered
reward table and remains unavailable, including paid readiness.
"""
import copy
import json
import re
from pathlib import Path

import pyamf

from bundle import TEMPLATES_DIR
import construction
import engine
import items
import paid_buildings
import storage

NAME = "fishermanscove"
CLASS = "FishermansCoveBuilding"
PART_NAMES = ("stonepart", "logpart", "steelbeampart")
STAGE_COUNTS = (3, 5, 10, 15, 20, 25, 30, 40, 50, 60)
REQUESTS_KEY = "_covePortRequests"
RESPONSE_KEY = "_covePortResponse"
AWARDED_KEY = "_covePortUpgradeAwards"
_FIELDS = ("itemName", "className", "state", "expansionLevel", "expansionParts",
           "isFullyBuilt", "capacity", "contents", "itemOrder", "storageMetadata",
           "plantTime", "buildTime")
_ACTIONS = frozenset(("store", "CompleteNow", "ExpandWithCurrency", "GrantRetroactiveUpgrade"))


def is_port(item):
    return bool(isinstance(item, dict) and item.get("name") == NAME
                and item.get("code") == ".d" and item.get("className") == CLASS)


def _contract():
    item = items.get_item_by_name(NAME)
    expected = {"type": "building", "buyable": "false", "placeable": "true",
                "sellable": "false", "limit": "1", "capacity": "0", "storageSize": "1",
                "sizeX": "17", "sizeY": "25", "growTime": "1"}
    if not is_port(item) or any(item.get(k) != v for k, v in expected.items()):
        raise ValueError("The original Lighthouse Cove Port definition is unavailable.")
    features = item.get("features", {}).get("feature")
    if not isinstance(features, list) or len(features) != 5:
        raise ValueError("The original Lighthouse Cove Port components are unavailable.")
    expand = [r for r in features if r.get("className") == "ExpandFManager"]
    harvest = [r for r in features if r.get("className") == "HarvestFManager"]
    if (len(expand) != 1 or harvest != [{"name": "harvester", "className": "HarvestFManager",
            "growTime": "1", "rewardType": "HarvestRewardGenerator", "rewardMultiplier": "storageLevel"}]
            or expand[0].get("awardExperiment") != {"name": "fv_upgradeaward_fisherman", "activeVar": "1"}):
        raise ValueError("The original Lighthouse Cove Port progression is unavailable.")
    upgrades = []
    for level, count in enumerate(STAGE_COUNTS, 2):
        row = {"level": str(level), "capacity": "0", "matsNeeded": str(count * 3),
               "part": [{"name": name, "need": str(count)} for name in PART_NAMES]}
        if level == 11:
            row["award"] = {"name": "consume_fishermanXfer", "number": "1"}
        upgrades.append(row)
    if expand[0].get("upgrade") != upgrades:
        raise ValueError("The original Lighthouse Cove Port material ladder is unavailable.")
    for name, code in zip(PART_NAMES, ("0el", "0en", "0es")):
        part = items.get_item_by_name(name)
        if (not part or any(part.get(k) != v for k, v in {"code": code, "className": "BuildingPart",
                "market": "cash", "cash": "1", "cost": "100"}.items())):
            raise ValueError("The original Lighthouse Cove Port material prices are unavailable.")
    reward = items.get_item_by_name("consume_fishermanXfer")
    if (not reward or reward.get("code") != "06x" or reward.get("className") != "CRewardConsumable"
            or reward.get("rewards") != {"reward": {"type": "world_content_license",
                "licenseType": "world", "value": "fisherman"}}):
        raise ValueError("The original Lighthouse Cove Port completion award is unavailable.")
    return item, upgrades


def recovered_contract():
    item, upgrades = _contract()
    return {"itemName": NAME, "code": ".d", "className": CLASS,
            "buyable": False, "initialLevel": 1, "upgrades": copy.deepcopy(upgrades),
            "harvestSeconds": 86400, "harvestAvailable": False,
            "harvestBlocker": "HarvestRewardGenerator table and probabilities were not recovered."}


def guard_snapshot(obj):
    """Validate saved progression without rewriting imported metadata."""
    if not isinstance(obj, dict) or obj.get("itemName") != NAME or obj.get("className") != CLASS:
        raise ValueError("The saved Lighthouse Cove Port identity is invalid.")
    _contract()
    level = construction._integer(obj.get("expansionLevel", 1), "Saved Cove Port level", 1, 11)
    if obj.get("isFullyBuilt") is False or obj.get("state") in ("construction", "constructing"):
        raise ValueError("The imported Cove Port construction state is not recovered.")
    parts = obj.get("expansionParts", {})
    if not isinstance(parts, dict):
        raise ValueError("Saved Cove Port materials must be a map.")
    needed = STAGE_COUNTS[level - 1] if level < 11 else 0
    codes = {items.get_item_by_name(name)["code"] for name in PART_NAMES}
    for code, quantity in parts.items():
        if code not in codes or construction._integer(quantity, "Saved Cove Port materials") > needed:
            raise ValueError("Saved Cove Port materials exceed the authored stage.")
    if obj.get("capacity", 0) != 0 or obj.get("contents") not in (None, [], {}):
        raise ValueError("The original Cove Port has zero occupant capacity.")
    if obj.get("plantTime") is not None:
        construction._integer(obj["plantTime"], "Saved Cove Port clock", 0, 2**53 - 1)
    return level


def preserve_fields(stored, incoming):
    result = copy.deepcopy(incoming)
    if stored and (stored.get("className") == CLASS or stored.get("itemName") == NAME):
        guard_snapshot(stored)
        for field in _FIELDS:
            if field in stored:
                result[field] = copy.deepcopy(stored[field])
            else:
                result.pop(field, None)
    elif stored and (incoming.get("className") == CLASS or incoming.get("itemName") == NAME):
        raise ValueError("A Cove Port snapshot cannot replace another saved object.")
    return result


def guard_action(action, stored, incoming):
    if not any(isinstance(obj, dict) and (obj.get("className") == CLASS or obj.get("itemName") == NAME)
               for obj in (stored, incoming)):
        return
    if action in ("harvest", "HarvestReadyNow"):
        raise ValueError("The Lighthouse Cove Port's original harvest reward table is unavailable.")
    if action not in _ACTIONS | {"getStorageInfo", "neighborAct"}:
        raise ValueError("The original fixed Cove Port cannot use this world action.")


def _owned(save, snapshot):
    if save.get("userInfo", {}).get("currentWorldType") != "fisherman":
        raise ValueError("The Lighthouse Cove Port belongs to Lighthouse Cove.")
    ident = construction._integer(snapshot.get("id"), "Cove Port object ID", 1)
    matches = [obj for obj in save.get("world", {}).get("objectsArray", [])
               if isinstance(obj, dict) and obj.get("id") == ident and not obj.get("deleted")]
    if len(matches) != 1:
        raise ValueError("A Cove Port action requires one owned saved Port.")
    obj = matches[0]
    guard_snapshot(obj)
    if snapshot.get("itemName") != NAME or snapshot.get("className") != CLASS:
        raise ValueError("The incoming Cove Port identity does not match its saved Port.")
    return obj


def _award_enabled():
    values = []
    for name in ("play.html", "ruffle.html"):
        text = Path(TEMPLATES_DIR, name).read_text()
        found = re.findall(r'"fv_upgradeaward_fisherman"\s*:\s*(\d+)', text)
        if len(found) != 1:
            raise ValueError("The original Cove Port award cohort is unavailable.")
        values.append(int(found[0]))
    if values[0] != values[1]:
        raise ValueError("The Cove Port award cohorts disagree.")
    return values[0] == 1


def _award(save, obj):
    if not _award_enabled():
        return False
    history = save.setdefault(AWARDED_KEY, {})
    if not isinstance(history, dict):
        raise ValueError("The saved Cove Port award ledger is invalid.")
    key = str(obj["id"])
    if history.get(key):
        return False
    # CRewardConsumable extends Consumable, not AutoConsumable; Player.addGift
    # stores 06x in the Gift Box. Using it is a separate license transaction.
    storage.store_deposit_item_by_name(save, "consume_fishermanXfer", 1, storage.GIFTBOX_ID)
    history[key] = {"level": 11, "itemCode": "06x", "quantity": 1}
    save["userInfo"]["player"].setdefault("actionCounts", {})["upgradeaward_fishermanscove"] = 1
    return True


def _stage(obj):
    level = guard_snapshot(obj)
    if level == 11:
        raise ValueError("The Cove Port is already fully expanded.")
    needed = STAGE_COUNTS[level - 1]
    return level + 1, {items.get_item_by_name(name)["code"]:
                      (items.get_item_by_name(name), needed) for name in PART_NAMES}


def _finish(save, obj, level):
    obj.update(expansionLevel=level, expansionParts={}, capacity=0, state="built", isFullyBuilt=True)
    if level == 11:
        _award(save, obj)
    # ExpandFManager.onStoreComplete45053 consumes numeric COMPLETE=2 and
    # restores STATE_BUILT. An invented rewardLink would imply social rewards.
    return {"expansionRewardType": 2}


def _store(save, obj, options):
    level, requirements = _stage(obj)
    material = items.get_item_by_name(options.get("storedItemName"))
    if not material or material.get("code") not in requirements:
        raise ValueError("That material does not belong to this Cove Port stage.")
    code = material["code"]
    if options.get("storedItemCode", code) != code or options.get("target", obj["id"]) != obj["id"]:
        raise ValueError("The Cove Port material source or target is invalid.")
    quantity = construction._integer(options.get("numToStore", 1), "Cove Port material quantity", 1, 100000)
    parts = obj.setdefault("expansionParts", {})
    if parts.get(code, 0) + quantity > requirements[code][1]:
        raise ValueError("Those Cove Port materials exceed this stage's requirement.")
    construction._source(save, obj, material, quantity, options)
    parts[code] = parts.get(code, 0) + quantity
    if all(parts.get(code, 0) == needed for code, (_, needed) in requirements.items()):
        return _finish(save, obj, level)
    return {}


def _complete(save, obj, action, options):
    allowed = {"partName", "isGift", "currency"} if action == "CompleteNow" else set()
    if set(options) - allowed or options.get("currency", "cash") != "cash":
        raise ValueError("Unsupported Cove Port completion options.")
    if options.get("isGift", False) not in (False,):
        raise ValueError("Combined Cove Port gift completion has ambiguous material quantities.")
    level, requirements = _stage(obj)
    part_name = options.get("partName")
    if part_name is not None and not isinstance(part_name, str):
        raise ValueError("The Cove Port completion material name is invalid.")
    parts = obj.setdefault("expansionParts", {})
    selected = [code for code, (part, needed) in requirements.items()
                if (part_name is None or part["name"] == part_name) and parts.get(code, 0) < needed]
    if not selected:
        raise ValueError("There are no missing Cove Port materials for this completion request.")
    cost = sum(engine.catalog_price(requirements[code][0], "cash") *
               (requirements[code][1] - parts.get(code, 0)) for code in selected)
    paid_buildings._charge(save, {"cash": cost})
    for code in selected:
        parts[code] = requirements[code][1]
    if all(parts.get(code, 0) == needed for code, (_, needed) in requirements.items()):
        return _finish(save, obj, level)
    return {}


def perform(save, action, snapshot, params, *, request_id=None, sequence_id=None, now=None):
    """Return id+callback for a Port action, None for an unrelated object.

    Call before generic paid_buildings, unrestored action refusal, and snapshot
    merge. The gateway's ordinary detached transaction owns disk persistence.
    """
    if not isinstance(snapshot, dict):
        return None
    owned = next((obj for obj in save.get("world", {}).get("objectsArray", [])
                  if obj.get("id") == snapshot.get("id")), None)
    if not any(isinstance(obj, dict) and (obj.get("itemName") == NAME or obj.get("className") == CLASS)
               for obj in (owned, snapshot)):
        return None
    guard_action(action, owned, snapshot)
    if action not in _ACTIONS:
        return None
    if sequence_id is not None:
        state = save.get("_meadowsStorage", {})
        if (not isinstance(sequence_id, str) or not sequence_id or len(sequence_id) > 128
                or not isinstance(state, dict) or sequence_id != state.get("sessionID")):
            raise ValueError("This Cove Port sequenceID is stale or unknown.")
    options = paid_buildings._options(params)
    obj = _owned(save, snapshot)
    key = str(construction._integer(request_id, "Cove Port request sequence")) if request_id is not None else None
    # Reuse ordinary storage's optional-clock/temp-ID NaN and Undefined
    # normalization, while retaining the original action-specific receipt shape.
    signed = json.loads(storage._request_signature(save, snapshot, options))
    signed.insert(1, action)
    signature = json.dumps(signed, sort_keys=True, allow_nan=False)
    history = save.get(REQUESTS_KEY, {})
    if not isinstance(history, dict) or not isinstance(history.get("receipts", {}), dict):
        raise ValueError("The saved Cove Port request ledger is invalid.")
    if key is not None and key in history.get("receipts", {}):
        receipt = history["receipts"][key]
        if receipt.get("signature") != signature:
            raise ValueError("A Cove Port sequence was reused for another request.")
        response = copy.deepcopy(receipt["response"])
        save[RESPONSE_KEY] = copy.deepcopy(response)
        return response
    if key is not None and int(key) <= construction._integer(history.get("highestSequence", -1), "Saved Cove Port sequence", -1):
        raise ValueError("This Cove Port request is older than its retained history.")
    detached = copy.deepcopy(save)
    obj = _owned(detached, snapshot)
    if action == "store":
        response = _store(detached, obj, options)
    elif action == "GrantRetroactiveUpgrade":
        if options:
            raise ValueError("The retroactive Cove Port probe has no options.")
        response = {}
        # The original material dialog probes every owned finite level. Only
        # the saved final level qualifies for its existing once-only award.
        if guard_snapshot(obj) == 11:
            counts = detached["userInfo"]["player"].get("actionCounts", {})
            count = construction._integer(counts.get("upgradeaward_fishermanscove", 0), "Saved Cove Port award count")
            granted = not count and _award(detached, obj)
            if granted:
                response = {"upgradeAward": [{"itemName": "consume_fishermanXfer", "number": 1}]}
    else:
        response = _complete(detached, obj, action, options)
    response = {"id": obj["id"], **response}
    if key is not None:
        history = detached.setdefault(REQUESTS_KEY, {})
        receipts = history.setdefault("receipts", {})
        receipts[key] = {"signature": signature, "response": copy.deepcopy(response)}
        history["highestSequence"] = int(key)
        while len(receipts) > 256:
            del receipts[next(iter(receipts))]
    detached[RESPONSE_KEY] = copy.deepcopy(response)
    save.clear(); save.update(detached)
    return response


def take_response(save):
    return save.pop(RESPONSE_KEY, {})


def start_session(save):
    save.pop(REQUESTS_KEY, None)
    save.pop(RESPONSE_KEY, None)
