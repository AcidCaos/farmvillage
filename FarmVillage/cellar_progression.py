"""Original InventoryCellar credits, capacity and finite redeem catalogue.

Only the authored shovel_item_01 and five explicit redeem rows are handled.
Social requests, thank-you loot and old inventory-upgrade campaigns stay closed.
The received counter determines capacity; redemption spends current only.
"""
import copy
from functools import lru_cache
import json
import math

import items
import world_travel

WORLDS = frozenset(("farm", "england", "meadows", "fisherman"))
REQUESTS = "_cellarProgressionRequests"


def whole(value):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or value != int(value) or not 0 <= value <= 2147483647):
        raise ValueError("The cellar counter or sequence is invalid.")
    return int(value)


@lru_cache(maxsize=1)
def contract():
    from cove_rules import _xml
    building = _xml("gameSettings.xml.gz").find(".//building[@name='InventoryCellar']")
    levels = [{"creditsNeeded": str(n), "imageBuildState": str(1 if n < 800 else 2)}
              for n in (200, 400, 600, 800, 1000)]
    rewards = {"mole": 20, "crystalrock": 40, "sheep_mine": 60,
               "gnomecaveman": 120, "tractorvintage": 200}
    part = items.get_item_by_name("shovel_item_01")
    if (building is None or building.attrib != {"name": "InventoryCellar", "meterMaxCredits": "1250"}
            or [dict(n.attrib) for n in building.findall("level")] != levels
            or [dict(n.attrib) for n in building.findall("redeemItem")] != [
                {"name": name, "creditCost": str(cost)} for name, cost in rewards.items()]
            or not part or any(part.get(k) != v for k, v in {
                "code": "v1", "basketClass": "InventoryCellar", "className": "BuildingPart",
                "count": "2", "cash": "1", "buyXp": "0", "market": "cash",
                "requiredLevel": "5", "buyable": "true"}.items())):
        raise ValueError("The recovered cellar progression requires a new audit.")
    return rewards


def record(save, world=None):
    world = world or save["userInfo"]["currentWorldType"]
    ledger = save["userInfo"]["player"].get("featureCredits")
    if ledger is None:
        return {"current": 0, "received": 0}
    if not isinstance(ledger, dict) or not isinstance(ledger.get(world, {}), dict):
        raise ValueError("The imported cellar credit ledger is invalid.")
    row = ledger.get(world, {}).get("InventoryCellar", {"current": 0, "received": 0})
    if not isinstance(row, dict):
        raise ValueError("The imported cellar credit record is invalid.")
    current, received = whole(row.get("current")), whole(row.get("received"))
    if current > received:
        raise ValueError("The imported cellar credit balance exceeds its received count.")
    return {**row, "current": current, "received": received}


def capacity(save, obj, item):
    contract()
    if sum(o.get("className") == "InventoryCellar" and o.get("itemName") == "hatchstorage"
           and not o.get("deleted") for o in save["world"]["objectsArray"]) != 1:
        raise ValueError("The authored cellar limit is one; ambiguous imported cellars grant no slots.")
    if (obj.get("className") != "InventoryCellar" or obj.get("itemName") != "hatchstorage"
            or item.get("name") != "hatchstorage" or item.get("capacity") != "1250" or item.get("limit") != "1"
            # StorageBuilding maps lifecycle 'built' through CreditsBuilding's
            # received-credit suffix. Older local saves used image keys here;
            # retain their accounting eligibility without inventing capacity.
            or obj.get("state") not in ("built", "built_0", "built_1", "built_2")
            or obj.get("isFullyBuilt", True) is not True):
        raise ValueError("The imported cellar identity or build state is invalid.")
    return min(1250, record(save)["received"])


def client_world(save):
    """Project old local cellar image keys as the authored built lifecycle.

    This is an initUser response copy, never a migration of imported state.
    Accounting, ownership and catalogue guards must all accept the saved cellar
    before it receives the original StorageBuilding image-state mapping.
    """
    world = save["world"]
    try:
        if world_travel.guard_active_world(save) not in WORLDS:
            return world
        objects = world["objectsArray"]
        legacy = [obj for obj in objects if obj.get("className") == "InventoryCellar"
            and obj.get("itemName") == "hatchstorage" and not obj.get("deleted")
            and obj.get("state") in ("built_0", "built_1", "built_2")]
        if len(legacy) != 1 or whole(legacy[0].get("id")) == 0:
            return world
        obj = legacy[0]
        world_travel.guard_action_object(save, obj["id"])
        capacity(save, obj, items.get_item_by_name("hatchstorage"))
    except ValueError:
        return world
    return {**world, "objectsArray": [
        {**entry, "state": "built"} if entry is obj else entry for entry in objects]}


def is_request(save, action, snapshot):
    if action not in ("store", "buyRedeemItem", "redeemItem"):
        return False
    return snapshot.get("className") == "InventoryCellar" or any(
        obj.get("id") == snapshot.get("id") and obj.get("className") == "InventoryCellar"
        for obj in save["world"]["objectsArray"])


def _request_params(action, params):
    import storage
    if action == "store":
        return [storage.world_action_options(params)]
    arguments = 3 if action == "redeemItem" else 2
    if isinstance(params, dict):
        entries = {}
        for key, value in params.items():
            if type(key) is int and 0 <= key <= arguments:
                index = key
            elif type(key) is str and key in tuple(str(n) for n in range(arguments + 1)):
                index = int(key)
            else:
                raise ValueError("Cellar redeem arguments need consecutive positional indices.")
            if index in entries:
                raise ValueError("Cellar redeem arguments have duplicate positional indices.")
            entries[index] = value
        if set(entries) != set(range(len(entries))):
            raise ValueError("Cellar redeem arguments need consecutive positional indices.")
        params = [entries[index] for index in range(len(entries))]
    if not isinstance(params, (list, tuple)):
        raise ValueError("Cellar redemption requires its original positional arguments.")
    params = list(params)
    if (params and isinstance(params[-1], dict) and set(params[-1]) == {"firstWA"}
            and params[-1]["firstWA"] is True):
        params = params[:-1]
    if len(params) != arguments:
        raise ValueError("Cellar redemption requires its original positional arguments.")
    return params


def _perform(save, action, snapshot, params):
    world = world_travel.guard_active_world(save)
    if world not in WORLDS:
        raise ValueError("Cellar progression is not restored in this world.")
    rewards = contract()
    if whole(snapshot.get("id")) == 0:
        raise ValueError("Cellar progression requires a durable owned identity.")
    world_travel.guard_action_object(save, snapshot.get("id"))
    owned = [o for o in save["world"]["objectsArray"] if o.get("id") == snapshot.get("id")]
    if len(owned) != 1:
        raise ValueError("Cellar progression requires one owned cellar.")
    obj = owned[0]
    if any(snapshot.get(k) != obj.get(k) for k in ("itemName", "className", "position")):
        raise ValueError("Cellar progression must retain its owned identity and position.")
    capacity(save, obj, items.get_item_by_name("hatchstorage"))
    row = record(save)
    import storage
    if action == "store":
        options = storage.world_action_options(params)
        if options.get("storedItemName") != "shovel_item_01":
            raise ValueError("Only the recovered cellar shovel grants cellar credits.")
        part = items.get_item_by_name("shovel_item_01")
        if options.get("storedItemCode", "v1") != "v1" or options.get("target", obj["id"]) != obj["id"]:
            raise ValueError("The cellar shovel target or code does not match.")
        quantity = whole(storage.positive_quantity(options.get("numToStore", 1)))
        whole(row["current"] + 2 * quantity)
        whole(row["received"] + 2 * quantity)
        source = options.get("cameFromLocation") or options.get("origin") or 0
        if (options.get("cameFromLocation") and options.get("origin")
                and options["cameFromLocation"] != options["origin"]):
            raise ValueError("The cellar shovel source is ambiguous.")
        if options.get("resource") not in (None, 0, -1) and not options.get("isGift") and not source:
            raise ValueError("The cellar shovel source is not a market purchase.")
        if options.get("isGift"):
            selector = storage.validate_consumption_source(save, part, storage.GIFTBOX_ID, quantity,
                                                            options.get("giftMetadataIndex", -1))
            storage._require_withdrawal(save, part, quantity, storage.GIFTBOX_ID,
                                        selector)
        elif source:
            storage.validate_consumption_source(save, part, source, quantity)
            storage._require_withdrawal(save, part, quantity, storage._storage_group(source))
        else:
            # The original FeatureCreditItem Market sends an empty currency;
            # its authored catalogue market is still cash, at one per bundle.
            if options.get("currency", "cash") not in (None, "", "cash"):
                raise ValueError("Cellar shovels cost one Farm Cash each.")
            from game_settings import xp_to_level
            from engine import apply_cash_diff
            cash = save["userInfo"]["player"].get("cash")
            if ((xp_to_level(save["userInfo"]["player"]["xp"]) or 0) < 5
                    or type(cash) not in (int, float) or not math.isfinite(cash) or cash < quantity):
                raise ValueError("The original shovel purchase requires level five and one Farm Cash per unit.")
            apply_cash_diff(save, -quantity)
        row["current"] = whole(row["current"] + 2 * quantity)
        row["received"] = whole(row["received"] + 2 * quantity)
    else:
        if (not isinstance(params, list) or not params or not isinstance(params[0], str) or params[0] not in rewards
                or params[-1] is not False):
            raise ValueError("The cellar redeem item or avatar flag is unsupported.")
        name = params[0]
        # Original CreditsBuilding sends redeemItem(name, cost, avatar).
        # The echoed price must match the immutable catalogue, never define it.
        if action == "redeemItem" and whole(params[1]) != rewards[name]:
            raise ValueError("The cellar redeem price does not match its authored cost.")
        if row["current"] < rewards[name]:
            raise ValueError("Not enough cellar credits for this reward.")
        row["current"] -= rewards[name]
        storage.store_deposit_item_by_name(save, name, 1, storage.GIFTBOX_ID)
    player = save["userInfo"]["player"]
    if player.get("featureCredits") is None:
        player["featureCredits"] = {}
    player["featureCredits"].setdefault(world, {})["InventoryCellar"] = row
    obj["state"] = "built"
    return obj["id"]


def perform(save, action, snapshot, params, *, request_id=None, sequence_id=None):
    """Detached update plus persistent sequence receipts: no retry charges."""
    import pyamf
    if sequence_id is not None:
        state = save.get("_meadowsStorage", {})
        if (not isinstance(sequence_id, str) or not sequence_id or len(sequence_id) > 128
                or not isinstance(state, dict) or sequence_id != state.get("sessionID")):
            raise ValueError("This cellar sequenceID is stale or unknown.")
    params = _request_params(action, params)
    def encode(v):
        if isinstance(v, pyamf.UndefinedType):
            return None
        raise ValueError("Unsupported cellar request value.")
    signature = json.dumps([save["userInfo"]["currentWorldType"], action, snapshot, params],
                           sort_keys=True, default=encode)
    key = str(whole(request_id)) if request_id is not None else None
    history = save.get(REQUESTS, {})
    if not isinstance(history, dict) or not isinstance(history.get("receipts", {}), dict):
        raise ValueError("The saved cellar retry history is invalid.")
    receipt = history.get("receipts", {}).get(key)
    if key is not None and receipt is not None:
        if not isinstance(receipt, dict) or receipt.get("signature") != signature:
            raise ValueError("A cellar sequence was reused for a different request.")
        return receipt["id"]
    if key is not None and int(key) <= history.get("highestSequence", -1):
        raise ValueError("This cellar request is older than retained retry history.")
    working = copy.deepcopy(save)
    result = _perform(working, action, snapshot, params)
    if key is not None:
        history = working.setdefault(REQUESTS, {})
        receipts = history.setdefault("receipts", {})
        receipts[key] = {"signature": signature, "id": result}
        history["highestSequence"] = int(key)
        while len(receipts) > 256:
            del receipts[next(iter(receipts))]
    save.clear(); save.update(working)
    return result
