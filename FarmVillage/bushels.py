"""Home crop bushels and the original simplified Bushel Report envelope.

The client proves the cadence/presentation; it does not contain the original
server's overflow policy. This local implementation carries fractional/blocked
harvest credit forward and spends it only for bushels actually deposited. It
never shares rewards or opens a social market stall.
"""
import copy
from functools import lru_cache
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import zlib

from bundle import XML_DIR
from game_settings import get_farming_int
import items
import peaceful
import storage

COUNTERS_KEY = "seedHarvestCountsSinceLastBushelDrop"
PENDING_KEY = "_bushelResponse"
NON_STALL_SUBTYPES = frozenset(("animal", "tree", "lab", "unsharable", "village"))
_MAX_INTEGER = 9_007_199_254_740_991


def _whole(value, label, *, minimum=0):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or int(value) != value or not minimum <= value <= _MAX_INTEGER):
        raise ValueError(label + " must be a supported whole number.")
    return int(value)


def _catalog_integer(value, label, *, minimum=0):
    if isinstance(value, str):
        try:
            value = int(value)
        except ValueError:
            pass
    return _whole(value, label, minimum=minimum)


@lru_cache(maxsize=1)
def _default_capacity():
    root = ET.fromstring(zlib.decompress((Path(XML_DIR) / "gz/v855098/crafting.xml.gz").read_bytes()))
    return _catalog_integer(root.findtext("featureConfig/globalInventoryBushelCapacity"),
                            "Archived bushel capacity", minimum=1)


def _counters(save):
    counters = save.get(COUNTERS_KEY, {})
    if not isinstance(counters, dict) or any(not isinstance(code, str) for code in counters):
        raise ValueError("The saved seed harvest counters are malformed.")
    for value in counters.values():
        _whole(value, "Saved seed harvest count")
    return counters


def initialize(save):
    """TInitUser reads this top-level map, including counts for inactive seeds."""
    counters = _counters(save)
    save.setdefault(COUNTERS_KEY, copy.deepcopy(counters))
    save.pop(PENDING_KEY, None)
    save.pop(STALL_REQUESTS_KEY, None)
    save.pop(STALL_PLACEMENTS_KEY, None)


def is_stall_bushel(item):
    return (isinstance(item, dict) and item.get("type") == "bushel"
            and item.get("className") == "CBushel"
            and item.get("subtype") not in NON_STALL_SUBTYPES)


def _inventory(save):
    state = save.get("craftingState", {})
    if not isinstance(state, dict):
        raise ValueError("The saved crafting state is malformed.")
    inventory = state.get("craftingItems", [])
    if not isinstance(inventory, list):
        raise ValueError("The saved bushel inventory is malformed.")
    total, seen = 0, set()
    for row in inventory:
        if not isinstance(row, dict) or not isinstance(row.get("itemCode"), str):
            raise ValueError("The saved bushel stack is malformed.")
        code = row["itemCode"]
        quantity = _whole(row.get("quantity"), "Saved bushel quantity")
        item = items.get_item_by_code(code)
        if item is None:
            raise ValueError("An imported bushel stack is not in the recovered catalog.")
        if is_stall_bushel(item):
            if code in seen:
                raise ValueError("Duplicate saved bushel stacks require review.")
            seen.add(code)
            total += quantity
    capacity = max(_default_capacity(), _whole(state.get("maxCapacity", 0), "Saved bushel capacity"))
    return inventory, total, capacity


def _guard_multipliers(save, plot):
    if plot.get("isSuperPlot") or plot.get("harvestYieldMultiplier", 1) != 1:
        raise ValueError("This plot's bushel harvest multiplier is not restored.")
    hot = save.get("flashHotParams", {})
    if not isinstance(hot, dict):
        raise ValueError("The saved bushel configuration is malformed.")
    # Home has no archived expansion-scale override. A future served boost
    # requires its dated eligibility to be recovered before changing awards.
    if any(str(name).startswith("FARM_") and "BUSHEL_BOOST" in str(name)
           and value not in (None, 0, "0", "", 1, "1") for name, value in hot.items()):
        raise ValueError("This imported Home bushel boost is not restored.")
    buffs = save["userInfo"]["player"].get("buffs", {})
    if not isinstance(buffs, dict):
        raise ValueError("The saved bushel gain buffs are malformed.")
    for name in buffs:
        item = items.get_item_by_name(name)
        if item is None or item.get("subtype") in ("bushel_gain", "harvest_gain"):
            raise ValueError("This imported bushel gain buff is not restored.")
    return hot


def _threshold(save, seed, hot):
    k = _catalog_integer(hot.get("KBUSHEL_MULTIPLIER_TMPRT", 50), "Bushel report multiplier", minimum=1)
    mastery = save["userInfo"]["player"].get("mastery", {})
    if not isinstance(mastery, dict):
        raise ValueError("The saved crop mastery is malformed.")
    value = mastery.get(seed["code"])
    # Imported clients can carry -1 as the unmastered placeholder. The original
    # adder adds one to that zero-based value, so it contributes no stars.
    stars = 0 if value is None else _catalog_integer(value, "Saved crop mastery", minimum=-1) + 1
    if stars > 3:
        raise ValueError("The imported crop mastery is outside the recovered ladder.")
    super_crop = seed.get("superCrop") in (True, "true")
    bonus = stars + (get_farming_int("bushelSuperCropBonus", 3) if super_crop else 0)
    threshold = int(k / (1 + bonus))
    if threshold < 1:
        raise ValueError("The bushel report threshold must remain positive.")
    return threshold


def _free_stall_inventory(save):
    player = save["userInfo"]["player"]
    flags = player.get("seenFlags", {})
    if not isinstance(flags, dict):
        raise ValueError("The saved first-stall seen flags are malformed.")
    if flags.get("FirstMarketStall"):
        return None
    for obj in save.get("world", {}).get("objectsArray", []):
        item = items.get_item_by_name(obj.get("itemName"))
        if item and item.get("className") == "MarketStallBuilding" and not obj.get("deleted"):
            return None
    data = player.get("storageData", {})
    if not isinstance(data, dict) or not isinstance(data.get(str(storage.GIFTBOX_ID), {}), dict):
        raise ValueError("The saved gift box is malformed.")
    gifts = data.get(str(storage.GIFTBOX_ID), {})
    for code, entry in gifts.items():
        if (not isinstance(entry, list) or len(entry) < 3
                or not isinstance(entry[1], list) or not isinstance(entry[2], list)):
            raise ValueError("An imported gift entry is malformed.")
        quantity = _whole(entry[0], "Saved gift quantity")
        item = items.get_item_by_code(code.split(":", 1)[0])
        if quantity and item and item.get("className") == "MarketStallBuilding":
            return None
    stall = items.get_item_by_name("marketstall")
    if not stall or stall.get("className") != "MarketStallBuilding":
        raise ValueError("The first Market Stall gift is absent from the catalog.")
    # Prepare the separate gift ledger first; a failed deposit cannot partially
    # consume a harvest counter or change the bushel inventory.
    detached = {"userInfo": {**save["userInfo"], "player": {**player, "storageData": copy.deepcopy(data)}}}
    storage.store_deposit_item_by_name(detached, "marketstall", group=storage.GIFTBOX_ID)
    return detached["userInfo"]["player"]["storageData"]


def harvest(save, seed, plot, *, now):
    """Mirror one validated owned harvest before its mastery count advances."""
    if (save["userInfo"].get("currentWorldType") or "farm") != "farm":
        return
    if not isinstance(seed, dict) or seed.get("type") != "seed":
        return
    bushel = items.get_item_by_code(seed.get("bushelItemCode"))
    if not is_stall_bushel(bushel):
        return
    objects = save.get("world", {}).get("objectsArray", [])
    harvestable = ("planted", "grown", "withered") if peaceful.enabled(save) else ("planted", "grown")
    if (not isinstance(plot, dict) or plot not in objects or plot.get("className") != "Plot"
            or plot.get("state") not in harvestable or plot.get("deleted")
            or plot.get("itemName") != seed.get("name")
            or sum(obj.get("id") == plot.get("id") for obj in objects) != 1):
        raise ValueError("Bushel harvests require one owned planted crop.")
    grow = peaceful.grow_seconds(seed)
    planted = plot.get("plantTime")
    if (grow is None or type(planted) not in (int, float) or not math.isfinite(planted)
            or now - planted / 1000 < grow - 1):
        raise ValueError("This crop has not finished growing for a bushel harvest.")
    hot = _guard_multipliers(save, plot)
    threshold = _threshold(save, seed, hot)
    counters = dict(_counters(save))
    count = _whole(counters.get(seed["code"], 0) + 1, "Awarded seed harvest count")
    inventory, used, capacity = _inventory(save)
    award = min(count // threshold, max(0, capacity - used))
    new_inventory = copy.deepcopy(inventory)
    gifts = None
    records = []
    if award:
        matches = [row for row in new_inventory if row["itemCode"] == bushel["code"]]
        if matches:
            matches[0]["quantity"] += award
        else:
            new_inventory.append({"itemCode": bushel["code"], "quantity": award, "price": None})
        gifts = _free_stall_inventory(save)
        count -= award * threshold
        records.append({"foundBushel": {"bushelCode": bushel["code"],
            "bushelsAddedToInventory": award, "bushelsAddedToSharedReward": 0,
            "bushelAddedToStall": False}})
    counters[seed["code"]] = count
    pending = copy.deepcopy(save.get(PENDING_KEY, {"records": [], "counts": {}}))
    if (not isinstance(pending, dict) or not isinstance(pending.get("records"), list)
            or not isinstance(pending.get("counts"), dict)):
        raise ValueError("The pending bushel report is malformed.")
    pending["records"].extend(records)
    pending["counts"][seed["code"]] = count
    save[COUNTERS_KEY] = counters
    state = save.setdefault("craftingState", {})
    state.update(craftingItems=new_inventory, maxCapacity=capacity)
    if gifts is not None:
        save["userInfo"]["player"]["storageData"] = gifts
    save[PENDING_KEY] = pending


def take_metadata(save):
    """Drain one command's award route; no data.foundBushel duplicate exists."""
    pending = save.pop(PENDING_KEY, None)
    if not pending:
        return {}
    result = {str(index): copy.deepcopy(row) for index, row in enumerate(pending["records"])}
    result["length"] = len(pending["records"])
    result["newHarvestQuantities"] = [{"itemCode": code, "quantity": count}
        for code, count in pending["counts"].items()]
    return {"bushelReport": {"dropTypeFuncResult": result}}


# Local owned stall configuration is distinct from neighbour offers/rewards.
STALL_METHODS = frozenset(('CraftingService.onReconfigureStall', 'CraftingService.onCloseStall'))
STALL_REQUESTS_KEY = '_marketStallRequests'
STALL_PLACEMENTS_KEY = '_marketStallPlacements'
_STALL_FIELDS = ('itemName', 'className', 'state', 'plantTime', 'isFullyBuilt',
                 'expansionLevel', 'expansionParts', 'contents', 'capacity',
                 'currentBushelItemCode', 'dateClosed', 'isConfigured')
_STALL_ACTIONS = frozenset(('place', 'move', 'store', 'sell', 'clear', 'getStorageInfo', 'neighborAct'))


def _is_stall(item):
    return isinstance(item, dict) and item.get('className') == 'MarketStallBuilding'


def _stall_home(save):
    import world_travel
    if world_travel.guard_active_world(save) != 'farm':
        raise ValueError('Owned Market Stall configuration is restored on Home only.')


def preserve_stall_fields(stored, incoming, *, action):
    """Ordinary snapshots never write an owned stall's configuration or clock."""
    old = items.get_item_by_name((stored or {}).get('itemName'))
    new = items.get_item_by_name(incoming.get('itemName'))
    if not (_is_stall(old) or _is_stall(new)):
        return incoming
    if action not in _STALL_ACTIONS:
        raise ValueError('This world action is not supported for the Market Stall.')
    if stored and not _is_stall(old):
        raise ValueError('A Market Stall snapshot cannot replace another saved object.')
    result = copy.deepcopy(incoming)
    if stored:
        for field in _STALL_FIELDS:
            if field in stored:
                result[field] = copy.deepcopy(stored[field])
            else:
                result.pop(field, None)
    return result


def initialize_stall_placement(snapshot):
    item = items.get_item_by_name(snapshot.get('itemName'))
    if not _is_stall(item):
        return snapshot
    result = copy.deepcopy(snapshot)
    result.update(className='MarketStallBuilding', state='built', isFullyBuilt=True,
                  currentBushelItemCode=None, dateClosed=0, isConfigured=False,
                  expansionLevel=_catalog_integer(item.get('storageSize', '0'), 'Initial stall storage level'),
                  capacity=_catalog_integer(item.get('capacity', '0'), 'Initial stall capacity'),
                  expansionParts={}, contents=[])
    return result


def _stall_placements(save):
    placements = save.get(STALL_PLACEMENTS_KEY, [])
    if (not isinstance(placements, list) or any(not isinstance(row, dict) or set(row) != {'id', 'itemName'}
            for row in placements)):
        raise ValueError('The saved pending Market Stall placements are malformed.')
    ids = [_whole(row['id'], 'Pending Market Stall ID', minimum=1) for row in placements]
    if len(set(ids)) != len(ids):
        raise ValueError('The saved pending Market Stall placements are ambiguous.')
    return placements


def _stall_count(save, fallback):
    state = save.get('craftingState', {})
    if not isinstance(state, dict):
        raise ValueError('The saved crafting state is malformed.')
    return _whole(state.get('currentMarketStallCount', fallback), 'Saved placed Market Stall count')


def _owned_stalls(save):
    objects = save.get('world', {}).get('objectsArray', [])
    return [obj for obj in objects if not obj.get('deleted')
            and _is_stall(items.get_item_by_name(obj.get('itemName')))]


def finish_stall_placement(save, snapshot, *, now=None):
    """Call once after inserting a new owned stall, after the placement retry gate."""
    if not _is_stall(items.get_item_by_name(snapshot.get('itemName'))):
        return
    _stall_home(save)
    ident = _whole(snapshot.get('id'), 'Placed Market Stall ID', minimum=1)
    owned = _owned_stalls(save)
    matches = [obj for obj in owned if obj.get('id') == ident]
    if len(matches) != 1 or matches[0].get('itemName') != snapshot.get('itemName'):
        raise ValueError('The newly placed Market Stall is missing or ambiguous.')
    placements = copy.deepcopy(_stall_placements(save))
    if any(row['id'] == ident for row in placements):
        return
    if len(placements) >= 256:
        raise ValueError('Reload before placing more unconfigured Market Stalls.')
    count = _whole(_stall_count(save, len(owned) - 1) + 1, 'Placed Market Stall count')
    placements.append({'id': ident, 'itemName': snapshot['itemName']})
    save.setdefault('craftingState', {})['currentMarketStallCount'] = count
    save[STALL_PLACEMENTS_KEY] = placements


def finish_stall_removal(save, stored):
    """Call only after an existing stall was actually removed by sell/clear/store."""
    if not stored or not _is_stall(items.get_item_by_name(stored.get('itemName'))):
        return
    _stall_home(save)
    if any(obj.get('id') == stored.get('id') for obj in _owned_stalls(save)):
        raise ValueError('The Market Stall has not been removed from this farm.')
    placements = [copy.deepcopy(row) for row in _stall_placements(save) if row['id'] != stored['id']]
    # Preserve imported counters rather than reconstructing them from a partial
    # world. Never make a legacy zero counter negative on the local server.
    count = max(0, _stall_count(save, len(_owned_stalls(save)) + 1) - 1)
    save.setdefault('craftingState', {})['currentMarketStallCount'] = count
    save[STALL_PLACEMENTS_KEY] = placements


def _configuration_target(save, ident):
    import world_travel
    if ident == -1:
        pending = _stall_placements(save)
        eligible = [obj for obj in _owned_stalls(save) if obj.get('isConfigured') is not True
                    and any(row['id'] == obj.get('id') and row['itemName'] == obj.get('itemName') for row in pending)]
        if len(eligible) != 1:
            raise ValueError('Initial configuration requires one newly placed unconfigured Market Stall.')
        ident = eligible[0]['id']
    else:
        ident = _whole(ident, 'Market Stall object ID', minimum=1)
    world_travel.guard_action_object(save, ident)
    matches = [obj for obj in save['world']['objectsArray'] if obj.get('id') == ident]
    if (len(matches) != 1 or matches[0].get('deleted') or matches[0].get('className') != 'MarketStallBuilding'
            or not _is_stall(items.get_item_by_name(matches[0].get('itemName')))):
        raise ValueError('Configuration requires one owned Market Stall with a unique ID.')
    return matches[0]


def _configure_stall(save, ident, code, now):
    bushel = items.get_item_by_code(code) if isinstance(code, str) else None
    seed = items.get_item_by_code((bushel or {}).get('crop'))
    if (not is_stall_bushel(bushel) or not seed or seed.get('type') != 'seed'
            or seed.get('bushelItemCode') != code):
        raise ValueError('Choose an original ordinary crop bushel for this stall.')
    inventory, _, _ = _inventory(save)
    if not any(row['itemCode'] == code and row['quantity'] > 0 for row in inventory):
        raise ValueError('This farm does not own a bushel of the selected crop.')
    obj = _configuration_target(save, ident)
    mastery = save['userInfo']['player'].get('mastery', {})
    if not isinstance(mastery, dict):
        raise ValueError('The saved crop mastery is malformed.')
    index = mastery.get(seed['code'])
    stars = 0 if index is None else _catalog_integer(index, 'Saved crop mastery', minimum=-1) + 1
    if stars > 3:
        raise ValueError('The saved crop mastery is outside the recovered ladder.')
    # CraftingConstants23074 and getEstimatedStallClosureTime5832. This is only
    # the map offering's display expiry, never a gain buff or a shared reward.
    obj.update(currentBushelItemCode=code, isConfigured=True,
               dateClosed=now + 86400 + math.floor(stars * 0.333))
    save[STALL_PLACEMENTS_KEY] = [row for row in _stall_placements(save) if row['id'] != obj['id']]
    return {}


def dispatch_stall(save, method, params, *, request_id=None, now):
    """Persist configuration/close with independent, bounded transport receipts."""
    import json
    _stall_home(save)
    expected = {'CraftingService.onReconfigureStall': 2, 'CraftingService.onCloseStall': 1}
    if (method not in expected or not isinstance(params, (list, tuple))
            or len(params) != expected[method]):
        raise ValueError('This Market Stall command has invalid parameters.')
    now = _whole(now, 'Market Stall action time', minimum=1)
    key = str(_whole(request_id, 'Market Stall request sequence')) if request_id is not None else None
    signature = json.dumps([method, list(params)], sort_keys=True, allow_nan=False)
    history = save.get(STALL_REQUESTS_KEY, {})
    if not isinstance(history, dict) or not isinstance(history.get('receipts', {}), dict):
        raise ValueError('The saved Market Stall retry history is malformed.')
    receipts = history.get('receipts', {})
    receipt = receipts.get(key)
    if key is not None and receipt is not None:
        if not isinstance(receipt, dict) or receipt.get('signature') != signature or not isinstance(receipt.get('result'), dict):
            raise ValueError('A Market Stall sequence was reused for a different command.')
        return copy.deepcopy(receipt['result'])
    highest = _whole(history.get('highestSequence', -1), 'Saved Market Stall request sequence', minimum=-1)
    if key is not None and int(key) <= highest:
        raise ValueError('This Market Stall request is older than the retained retry history.')
    working = copy.deepcopy(save)
    if method == 'CraftingService.onReconfigureStall':
        ident = _whole(params[0], 'Market Stall object ID', minimum=-1)
        result = _configure_stall(working, ident, params[1], now)
    else:
        obj = _configuration_target(working, _whole(params[0], 'Market Stall object ID', minimum=1))
        obj.update(currentBushelItemCode=None, dateClosed=0, isConfigured=False)
        result = {'success': True}
    if key is not None:
        history = working.setdefault(STALL_REQUESTS_KEY, {})
        receipts = history.setdefault('receipts', {})
        receipts[key] = {'signature': signature, 'result': copy.deepcopy(result)}
        history['highestSequence'] = int(key)
        while len(receipts) > 256:
            del receipts[next(iter(receipts))]
    save.clear()
    save.update(working)
    return result
