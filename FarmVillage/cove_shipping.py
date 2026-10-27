"""Exact Cove shipping entitlement; no implicit licenses for other worlds.

ShippingLicenseSlot -> TBuyConsumables -> FarmService.buyConsumablePackage.
TBuyConsumables uses consume_fishermanXfer immediately (useOnBuy=true),
granting the original nested world-content license rather than a spare gift.
StorageWindow.isUseable requires BOTH source and current-world licenses.
"""
import copy
from functools import lru_cache
import math

import items
import world_travel

PACKAGE = "pkg_fishermanXfer"
CONSUMABLE = "consume_fishermanXfer"
REQUESTS = "_coveShippingRequests"


@lru_cache(maxsize=1)
def contract():
    from cove_rules import _xml
    package, consumable = items.get_item_by_name(PACKAGE), items.get_item_by_name(CONSUMABLE)
    expected = {"code": "XX", "cash": "75", "market": "cash", "buyXp": "0",
                "marketPrereqs": "fishermanXfer_visible", "buyable": "true",
                "itemPackage": {"amount": "1", "value": CONSUMABLE}}
    reward = {"type": "world_content_license", "licenseType": "world", "value": "fisherman"}
    prereq = _xml("gameSettingsCMS.xml.gz").find(".//prereq[@name='fishermanXfer_visible']")
    if (not package or any(package.get(k) != v for k, v in expected.items())
            or not consumable or consumable.get("code") != "06x"
            or consumable.get("className") != "CRewardConsumable"
            or consumable.get("useOnBuy") != "true"
            or consumable.get("rewards") != {"reward": reward}
            or prereq is None or prereq.get("type") != "AND"
            or [dict(n.attrib) for n in prereq] != [
                {"type": "no_world_license", "value": "fisherman", "licenseType": "world"},
                {"type": "has_unlocked_world", "value": "fisherman"}]):
        raise ValueError("The recovered Cove shipping license requires a new audit.")
    return {"cash": 75, "world": "fisherman", "licenseType": "world"}


def licensed(save, world):
    licenses = save["userInfo"].get("unlockedWorldContentLicenses", {})
    if not isinstance(licenses, dict) or not isinstance(licenses.get(world, {}), dict):
        raise ValueError("The imported world-content licenses are invalid.")
    return licenses.get(world, {}).get("world") is True


def guard_source(save, group):
    """Admit only Cove-involving transfers between existing owned inventories."""
    current = world_travel.guard_active_world(save)
    supported = world_travel.supported_worlds()
    sources = [name for name, ident in supported.items() if ident == group]
    if len(sources) != 1:
        raise ValueError("The shipping source is not an owned world inventory.")
    source = sources[0]
    if "fisherman" not in (current, source):
        raise ValueError("Transfers from another world's inventory require unsupported shipping licenses.")
    available = {current, *save.get(world_travel.STATE_KEY, {}).get("inactive", {})}
    summaries = save["userInfo"].get("worldSummaryData", {})
    if (source not in available or current not in available
            or summaries.get(source, {}).get("storageId") != group
            or not licensed(save, source) or not licensed(save, current)):
        raise ValueError("Transfers require owned source and destination farms and both original shipping licenses.")


def buy(save, *, request_id=None):
    world_travel.guard_active_world(save)
    spec = contract()
    if request_id is not None and (type(request_id) not in (int, float)
            or not math.isfinite(request_id) or request_id != int(request_id) or request_id < 0):
        raise ValueError("The shipping purchase sequence is invalid.")
    history = save.get(REQUESTS, {})
    if not isinstance(history, dict):
        raise ValueError("The saved shipping purchase history is invalid.")
    # This entitlement is permanent. A retry or a fresh sequence cannot pay twice.
    if licensed(save, "fisherman"):
        return {}
    if "fisherman" not in save["userInfo"].get("unlockedWorldTypes", []):
        raise ValueError("Unlock Lighthouse Cove before buying its shipping license.")
    owned = save["userInfo"].get("currentWorldType") == "fisherman" or "fisherman" in save.get(
        world_travel.STATE_KEY, {}).get("inactive", {})
    if not owned or save["userInfo"].get("worldSummaryData", {}).get("fisherman", {}).get("storageId") != -9:
        raise ValueError("The owned Cove snapshot is missing; no shipping license was charged.")
    cash = save["userInfo"]["player"].get("cash")
    if type(cash) not in (int, float) or not math.isfinite(cash) or cash < spec["cash"]:
        raise ValueError("Not enough cash for the original Cove shipping license.")
    from engine import apply_item_cost
    from world_scores import add_content_license
    working = copy.deepcopy(save)
    apply_item_cost(working, items.get_item_by_name(PACKAGE), currency="cash")
    add_content_license(working, spec["world"], spec["licenseType"])
    working[REQUESTS] = {"package": PACKAGE, "cashPaid": spec["cash"], "sequence": request_id}
    save.clear(); save.update(working)
    return {}


def consume(save, count, group):
    """Use a genuinely owned gift from a Port award or imported inventory."""
    contract()
    import storage
    from world_scores import add_content_license
    if count != 1 or type(count) not in (int, float):
        raise ValueError("A permanent Cove shipping license is used one at a time.")
    if licensed(save, "fisherman"):
        raise ValueError("The Cove shipping license is already owned; its gift was preserved.")
    working = copy.deepcopy(save)
    storage.validate_consumption_source(working, items.get_item_by_name(CONSUMABLE), group, 1)
    if not storage.store_withdraw_item_by_name(working, CONSUMABLE, 1, group):
        raise ValueError("The Cove shipping license gift is missing.")
    add_content_license(working, "fisherman", "world")
    save.clear(); save.update(working)


def use(save, snapshot, params, *, request_id=None):
    import json
    import storage
    world_travel.guard_active_world(save)
    if isinstance(params, list) and params and params[-1] == {"firstWA": True}:
        params = params[:-1]
    if (not isinstance(params, list) or len(params) != 1 or not isinstance(params[0], dict)
            or set(params[0]) != {"storageId", "itemCount"}):
        raise ValueError("The Cove license requires its original consume options.")
    key = str(storage._storage_group(request_id)) if request_id is not None else None
    signature = json.dumps([save["userInfo"]["currentWorldType"], snapshot, params], sort_keys=True)
    history = save.get("_coveShippingUse", {})
    if not isinstance(history, dict):
        raise ValueError("The Cove license use history is invalid.")
    if key is not None and key in history:
        if history[key] != signature:
            raise ValueError("A shipping use sequence was reused for another request.")
        return snapshot["id"]
    working = copy.deepcopy(save)
    consume(working, params[0]["itemCount"], storage._storage_group(params[0]["storageId"]))
    if key is not None:
        working.setdefault("_coveShippingUse", {})[key] = signature
    save.clear(); save.update(working)
    return snapshot["id"]


def transfer(save, snapshot, options, request_id, operation):
    """Atomic original inventory transfer; retain its exact signed retry."""
    import json
    import storage
    import pyamf
    options = storage._given_options(options)
    source = options.get("cameFromLocation") or options.get("origin") or 0
    source = storage._storage_group(source)
    current = storage.active_inventory_id(save)
    if source >= 0 or source in (storage.GIFTBOX_ID, storage.CONSUME_ID, current):
        return False
    guard_source(save, source)
    if options.get("isGift") or (options.get("origin") and options.get("cameFromLocation")
            and options["origin"] != options["cameFromLocation"]):
        raise ValueError("The shipping source is ambiguous.")
    target = storage._storage_group(options.get("target", snapshot.get("id")))
    if target != current:
        raise ValueError("Shipping can only deposit into the active farm inventory.")
    def encode(v):
        if isinstance(v, pyamf.UndefinedType):
            return None
        raise ValueError("Unsupported shipping request value.")
    signature = json.dumps([save["userInfo"]["currentWorldType"], snapshot, options],
                           sort_keys=True, default=encode)
    key = str(storage._storage_group(request_id)) if request_id is not None else None
    history_key = "_coveShippingTransfers"
    history = save.get(history_key, {})
    if not isinstance(history, dict) or not isinstance(history.get("receipts", {}), dict):
        raise ValueError("The saved shipping retry history is invalid.")
    if key is not None and key in history.get("receipts", {}):
        if history["receipts"][key] != signature:
            raise ValueError("A shipping sequence was reused for another request.")
        return True
    if key is not None and int(key) <= history.get("highestSequence", -1):
        raise ValueError("This shipping request is older than its retained history.")
    working = copy.deepcopy(save)
    operation(working, snapshot, options)
    if key is not None:
        history = working.setdefault(history_key, {})
        history.setdefault("receipts", {})[key] = signature
        history["highestSequence"] = int(key)
        while len(history["receipts"]) > 256:
            del history["receipts"][next(iter(history["receipts"]))]
    save.clear(); save.update(working)
    return True
