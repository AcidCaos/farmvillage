"""Exact England shipping entitlement and two-inventory transfer admission.

ShippingLicenseSlot53252 buys pkg_englandXfer through TBuyConsumables15488.
The archived useOnBuy CRewardConsumable grants two world_content_license
rewards. WorldManager2735 and StorageWindow12220 require the source and active
world's ``world`` license. No other destination or reward family is inferred.
Only the caller's village transaction writes files; direct calls are atomic.
"""
import copy
from functools import lru_cache
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import zlib

from bundle import XML_DIR
import engine
import items
import world_travel

PACKAGE = "pkg_englandXfer"
CONSUMABLE = "consume_englandXfer"
REQUESTS_KEY = "_englandShippingRequests"
TRANSFER_REQUESTS_KEY = "_englandShippingTransferRequests"
# Deliberate restored cohort, mirrored only by fv_ECstoragetransfer_market=1.
ENABLE_PURCHASE = True
INVENTORIES = {"farm": -2, "england": -8}


def _whole(value, label, minimum=0):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or int(value) != value
            or not minimum <= value <= 2_147_483_647):
        raise ValueError(f"{label} must be a whole number.")
    return int(value)


def _list(value):
    return value if isinstance(value, list) else [] if value is None else [value]


@lru_cache(maxsize=1)
def _prerequisite_contract():
    root = ET.fromstring(zlib.decompress(
        Path(XML_DIR, "gz/v855098/gameSettingsCMS.xml.gz").read_bytes()))
    nodes = root.findall(".//prereq[@name='englandXfer_visible']")
    expected = [
        {"type": "no_world_license", "value": "england", "licenseType": "world"},
        {"type": "experiment", "value": "fv_ECstoragetransfer_market", "variant": "1"},
        {"type": "has_unlocked_world", "value": "england"},
    ]
    if (len(nodes) != 1 or nodes[0].attrib != {"name": "englandXfer_visible", "type": "AND"}
            or [child.attrib for child in nodes[0]] != expected
            or any(len(child) for child in nodes[0])):
        raise ValueError("England's original shipping prerequisites require review.")


def _catalog_contract():
    _prerequisite_contract()
    package = items.get_item_by_name(PACKAGE)
    leaf = items.get_item_by_name(CONSUMABLE)
    expected_package = {"name": PACKAGE, "market": "cash", "cash": "75",
        "marketPrereqs": "englandXfer_visible", "buyable": "true",
        "itemPackage": {"amount": "1", "value": CONSUMABLE}}
    expected_leaf = {"name": CONSUMABLE, "code": "0Ee", "className": "CRewardConsumable",
        "useOnBuy": "true", "type": "consumable"}
    rewards = [{"type": "world_content_license", "licenseType": "world", "value": world}
               for world in ("england", "farm")]
    if (not isinstance(package, dict) or not isinstance(leaf, dict)
            or any(package.get(k) != value for k, value in expected_package.items())
            or any(leaf.get(k) != value for k, value in expected_leaf.items())
            or _list((leaf.get("rewards") or {}).get("reward")) != rewards):
        raise ValueError("England's original shipping package requires review.")
    return 75


def _licenses(save):
    ledger = save["userInfo"].get("unlockedWorldContentLicenses", {})
    if not isinstance(ledger, dict):
        raise ValueError("The imported world shipping licenses are malformed.")
    for world in INVENTORIES:
        if world in ledger and not isinstance(ledger[world], dict):
            raise ValueError("The imported world shipping license is malformed.")
    return ledger


def _licensed(ledger, world):
    # WorldManager.hasWorldContentLicense tests non-null, not truthiness. This
    # is saved entitlement data, never a caller-supplied license assertion.
    return ledger.get(world, {}).get("world") is not None


def _owned_pair(save):
    active = world_travel.guard_active_world(save)
    if active not in INVENTORIES:
        raise ValueError("England shipping is supported from Home and England only.")
    state = save.get(world_travel.STATE_KEY)
    if not isinstance(state, dict):
        raise ValueError("England shipping requires retained Home and England snapshots.")
    world_travel.validate(save)
    if not set(INVENTORIES) <= {active, *state["inactive"]}:
        raise ValueError("England shipping requires both owned worlds.")
    return active


def guard_transfer(save, source_group, destination_group=None):
    """Admit Home/England inventory withdrawal only with both saved licenses.

    Return False when no world shipping is involved. Positive destinations are
    current-world buildings whose ownership/filter/capacity is checked by the
    storage engine. Unknown foreign inventories remain refused.
    """
    source_group = _whole(source_group, "Shipping source inventory", minimum=-2_147_483_648)
    if destination_group is not None:
        destination_group = _whole(destination_group, "Shipping destination inventory", minimum=-2_147_483_648)
    active = world_travel.guard_active_world(save)
    active_inventory = world_travel.supported_worlds()[active]
    if source_group > 0 or source_group in (-1, -6, active_inventory):
        return False
    source_world = next((world for world, group in INVENTORIES.items() if group == source_group), None)
    if source_world is None or active not in INVENTORIES:
        raise ValueError("This world's shipping contract is not restored.")
    _owned_pair(save)
    if destination_group is not None and destination_group <= 0 and destination_group != active_inventory:
        raise ValueError("Shipping can only enter the active world's inventory.")
    ledger = _licenses(save)
    if not all(_licensed(ledger, world) for world in (source_world, active)):
        raise ValueError("Shipping requires the source and destination world's original licenses.")
    return True


def buy_package(save, package_name, *, request_id=None):
    """Charge75FC once and immediately grant the two original entitlements."""
    if package_name != PACKAGE:
        raise ValueError("This is not England's original shipping package.")
    key = str(_whole(request_id, "Shipping request sequence")) if request_id is not None else None
    history = save.get(REQUESTS_KEY, {})
    if not isinstance(history, dict) or not isinstance(history.get("receipts", {}), dict):
        raise ValueError("The saved shipping retry history is malformed.")
    receipts = history.get("receipts", {})
    if key is not None and key in receipts:
        if receipts[key] != {"package": PACKAGE, "result": {}}:
            raise ValueError("A shipping sequence was reused for a different command.")
        _owned_pair(save)
        saved_licenses = _licenses(save)
        if not all(_licensed(saved_licenses, world) for world in INVENTORIES):
            raise ValueError("The saved shipping receipt disagrees with its original entitlements; recover the imported record before retrying.")
        return {}
    highest = _whole(history.get("highestSequence", -1), "Saved shipping sequence", minimum=-1)
    if key is not None and int(key) <= highest:
        raise ValueError("This shipping request predates the retained retry history.")
    _owned_pair(save)
    ledger = _licenses(save)
    # The original no_world_license England prerequisite prevents repeated
    # purchases. A retry after login, eviction or an imported entitlement also
    # cannot charge again or silently repair a different imported license.
    if _licensed(ledger, "england"):
        if not _licensed(ledger, "farm"):
            raise ValueError("The imported England shipping entitlement is missing its Home license; recover the original pair before shipping.")
        return {}
    if not ENABLE_PURCHASE:
        raise ValueError("England's shipping purchase cohort is not enabled.")
    cost = _catalog_contract()
    cash = save["userInfo"]["player"].get("cash")
    if (isinstance(cash, bool) or not isinstance(cash, (int, float))
            or not math.isfinite(cash) or cash < cost):
        raise ValueError("Not enough Farm Cash for England's shipping license.")
    working = copy.deepcopy(save)
    engine.apply_cash_diff(working, -cost)
    licenses = working["userInfo"].setdefault("unlockedWorldContentLicenses", {})
    for world in ("england", "farm"):
        licenses.setdefault(world, {})["world"] = True
    if key is not None:
        history = working.setdefault(REQUESTS_KEY, {})
        history.setdefault("receipts", {})[key] = {"package": PACKAGE, "result": {}}
        history["highestSequence"] = int(key)
        while len(history["receipts"]) > 256:
            del history["receipts"][next(iter(history["receipts"]))]
    save.clear()
    save.update(working)
    return {}


def start_session(save):
    save.pop(REQUESTS_KEY, None)
    save.pop(TRANSFER_REQUESTS_KEY, None)


def is_transfer_request(save, action, snapshot, params):
    if action not in ("place", "store") or not isinstance(params, (list, tuple)) or not params:
        return False
    options = params[0]
    if not isinstance(options, dict):
        return False
    # Use exactly the storage parser's null/undefined and signed-ID semantics.
    # Otherwise a numeric text source bypasses the retry wrapper while storage
    # still withdraws from the foreign inventory, and undefined isGift looks
    # truthy here even though storage removes it.
    import storage
    options = storage._given_options(options)
    if options.get("isGift"):
        return False
    world = world_travel.guard_active_world(save)
    if world not in INVENTORIES:
        return False
    active = world_travel.supported_worlds()[world]
    fields = ("isStorageWithdrawal",) if action == "place" else ("cameFromLocation", "origin")
    sources = [storage._storage_group(options[field]) for field in fields if field in options]
    return any(source in INVENTORIES.values() and source != active for source in sources)


def dispatch_world(save, action, snapshot, params, request_id, callback):
    """Retain the original signed transfer result across retry and reload."""
    import pyamf
    def encode(value):
        if isinstance(value, pyamf.UndefinedType):
            return None
        raise ValueError("The shipping request contains an unsupported value.")
    sequence = _whole(request_id, "Shipping transfer sequence")
    signed_snapshot = copy.deepcopy(snapshot)
    # TWorldState legitimately serializes absent MapResource time/temp fields
    # as NaN. commands normalizes these exact fields after this wrapper; use
    # the same semantic spelling for its signature without altering the RPC.
    for field in ("tempId", "plantTime", "buildTime"):
        value = signed_snapshot.get(field)
        if isinstance(value, float) and math.isnan(value):
            signed_snapshot[field] = None
    signature = json.dumps([save["userInfo"].get("currentWorldType") or "farm",
        action, signed_snapshot, params], sort_keys=True, default=encode, allow_nan=False)
    history = save.get(TRANSFER_REQUESTS_KEY, {})
    if not isinstance(history, dict) or not isinstance(history.get("receipts", {}), dict):
        raise ValueError("The saved shipping transfer history is malformed.")
    receipts = history.get("receipts", {})
    key = str(sequence)
    if key in receipts:
        receipt = receipts[key]
        if (not isinstance(receipt, dict) or receipt.get("signature") != signature
                or "result" not in receipt):
            raise ValueError("A shipping sequence was reused for a different transfer.")
        return _whole(receipt["result"], "Saved shipping transfer result", minimum=-2_147_483_648)
    if sequence <= _whole(history.get("highestSequence", -1), "Saved shipping transfer sequence", minimum=-1):
        raise ValueError("This shipping transfer predates the retained retry history.")
    before = copy.deepcopy(save)
    try:
        result = callback()
        history = save.setdefault(TRANSFER_REQUESTS_KEY, {})
        history.setdefault("receipts", {})[key] = {"signature": signature, "result": copy.deepcopy(result)}
        history["highestSequence"] = sequence
        while len(history["receipts"]) > 256:
            del history["receipts"][next(iter(history["receipts"]))]
        return result
    except BaseException:
        save.clear()
        save.update(before)
        raise


def client_licenses(save):
    """Give WorldManager an empty-map default without rewriting imported data."""
    value = save.get("userInfo", {}).get("unlockedWorldContentLicenses")
    return copy.deepcopy(value) if isinstance(value, dict) else {}
