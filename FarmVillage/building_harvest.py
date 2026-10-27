"""Original deterministic Herb Garden harvests and their usable seed inventory.

SeedDispenserManager57599 selects the first unmastered CMS herb. Its harvest
manager45395 grants seed units before the ordinary THarvest request, using the
building's saved level. This module reproduces that deterministic choice and
the original coin fallback. Server-only LootService tables are not inferred.
"""
import copy
from functools import lru_cache
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zlib

from bundle import TEMPLATES_DIR, XML_DIR
import engine
from game_settings import get_farming_int
import items
import peaceful
import storage
import world_travel

HERBS = ("thaibasil", "thyme", "rosemary", "marjoram", "parsley", "frenchtarragon",
         "oregano", "sorrel", "shiso", "cilantro")
REQUESTS_KEY = "_buildingHarvestRequests"


def _whole(value, label, minimum=0, maximum=2_147_483_647):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or (isinstance(value, float) and not math.isfinite(value))
            or int(value) != value or not minimum <= value <= maximum):
        raise ValueError(f"{label} must be a whole number from {minimum} to {maximum}.")
    return int(value)


def _list(value):
    return value if isinstance(value, list) else [] if value is None else [value]


@lru_cache(maxsize=1)
def _configuration():
    root = ET.fromstring(zlib.decompress((Path(XML_DIR) / "gz/v855098/gameSettingsCMS.xml.gz").read_bytes()))
    feature = root.find(".//featureConfig/feature[@name='herbgarden']")
    if feature is None or tuple(seed.get("name") for seed in feature.findall("seed")) != HERBS:
        raise ValueError("The original Herb Garden seed sequence requires review.")
    seeds = []
    for seed in feature.findall("seed"):
        prereqs = seed.findall("prereqs/prereq")
        if (len(prereqs) != 1 or prereqs[0].attrib != {
                "type": "experiment", "value": "fv_herbgarden", "variant": "3,4"}):
            raise ValueError("The Herb Garden seed prerequisites require review.")
        seeds.append(seed.get("name"))
    levels = {int(row.get("level")): row.get("name") for row in feature.findall("seedPackageSizeKey")}
    if levels != {1: "CSeedPackageSize", 2: "CSeedPackageSize_100", 3: "CSeedPackageSize_200",
                  4: "CSeedPackageSize_400", 5: "CSeedPackageSize_600", 6: "CSeedPackageSize_900"}:
        raise ValueError("The Herb Garden package-size progression requires review.")
    return tuple(seeds), levels


def _variant():
    # Server configuration, never a player-provided experiment override.
    text = Path(TEMPLATES_DIR, "play.html").read_text(encoding="utf-8")
    match = re.search(r'"fv_herbgarden"\s*:\s*(-?\d+)', text)
    return int(match.group(1)) if match else 0


def manages(item):
    return bool(item and item.get("name") == "herbgarden" and item.get("className") == "FeatureBuilding")


def initialize_placement(snapshot, *, now):
    """A newly placed garden cannot import an already grown client clock."""
    if not manages(items.get_item_by_name(snapshot.get("itemName"))):
        return snapshot
    result = copy.deepcopy(snapshot)
    result.update(className="FeatureBuilding", isFullyBuilt=True, state="bare",
                  expansionLevel=1, expansionParts={}, capacity=0, contents=[],
                  plantTime=_whole(now, "Herb Garden placement time", 1) * 1000)
    return result


def preserve_fields(stored, incoming, *, action=None):
    old = items.get_item_by_name((stored or {}).get("itemName"))
    new = items.get_item_by_name(incoming.get("itemName"))
    if stored and not manages(old) and manages(new):
        raise ValueError("An Herb Garden snapshot cannot replace a different saved object.")
    result = copy.deepcopy(incoming)
    if manages(old):
        # Paid readiness and harvest mutate the owned object directly. Every
        # ordinary snapshot must retain these fields, including clearWithered.
        fields = ["itemName", "className", "isFullyBuilt", "expansionLevel", "expansionParts", "capacity", "contents",
                  "state", "plantTime", "buildTime"]
        for field in fields:
            if field in stored:
                result[field] = copy.deepcopy(stored[field])
            else:
                result.pop(field, None)
    return result


def guard_action(action, stored, incoming):
    """Generic Plot actions cannot create or reset an Herb Garden."""
    if not (manages(items.get_item_by_name((stored or {}).get("itemName")))
            or manages(items.get_item_by_name((incoming or {}).get("itemName")))):
        return
    if action not in ("place", "move", "store", "sell", "clear", "harvest", "getStorageInfo", "neighborAct"):
        raise ValueError("This world action is not supported for the Herb Garden.")


def _context(save, obj, now):
    world_travel.guard_active_world(save)
    now = _whole(now, "Herb Garden harvest time", 1)
    ident = _whole(obj.get("id"), "Herb Garden object ID")
    world_travel.guard_action_object(save, ident)
    objects = save.get("world", {}).get("objectsArray", [])
    matches = [row for row in objects if row.get("id") == ident and not row.get("deleted")]
    if len(matches) != 1 or matches[0] is not obj:
        raise ValueError("Harvesting requires one owned Herb Garden with a unique ID.")
    item = items.get_item_by_name(obj.get("itemName"))
    if (not manages(item) or obj.get("className") != item["className"]
            or obj.get("isFullyBuilt") is False
            or obj.get("state") not in ("bare", "built", "grown", "busy")):
        raise ValueError("Harvesting requires a completed saved Herb Garden.")
    harvester = [row for row in _list((item.get("features") or {}).get("feature"))
                 if row.get("className") == "SeedDispenserHarvestFManager"]
    if (len(harvester) != 1 or harvester[0].get("rewardType") != "SeedDispenserRewardGenerator"
            or harvester[0].get("rewardMultiplier") != "oneFixed"):
        raise ValueError("The Herb Garden's original harvest contract is unavailable.")
    if _variant() not in (3, 4):
        raise ValueError("The original Herb Garden experiment is not enabled.")
    level = _whole(obj.get("expansionLevel", 1), "Saved Herb Garden level", 1, 6)
    grow = peaceful.grow_seconds(item)
    planted = obj.get("plantTime")
    if (grow is None or isinstance(planted, bool) or not isinstance(planted, (int, float))
            or (isinstance(planted, float) and not math.isfinite(planted))
            or planted < 0 or planted > now * 1000):
        raise ValueError("The saved Herb Garden growth clock is invalid.")
    return item, harvester[0], level, grow, now


def _package(seed):
    item = items.get_item_by_name(seed) if isinstance(seed, str) else seed
    if not item or item.get("name") not in HERBS or item.get("type") != "seed":
        return None
    package = items.get_item_by_name(item.get("seedpackage"))
    if (not package or package.get("name") != item["name"] + "_seedpackage"
            or package.get("className") != "CSeedPackage" or package.get("seed") != item["name"]):
        raise ValueError("The original herb seed-package definition is unavailable.")
    return package


def _entry(save, package):
    inventories = save["userInfo"]["player"].get("storageData")
    if not isinstance(inventories, dict) or not isinstance(inventories.get("-1", {}), dict):
        raise ValueError("The saved Herb Garden seed inventory is invalid.")
    entry = inventories.get("-1", {}).get(package["code"])
    if entry is not None:
        if not isinstance(entry, list) or len(entry) < 3 or not isinstance(entry[1], list) or not isinstance(entry[2], list):
            raise ValueError("The saved herb seeds have invalid inventory metadata.")
        _whole(entry[0], "Stored herb seed quantity")
    return entry


def _reward(save, level, harvester):
    seeds, levels = _configuration()
    mastery = save["userInfo"]["player"].get("mastery", {})
    if not isinstance(mastery, dict):
        raise ValueError("The saved herb mastery state is invalid.")
    for name in seeds:
        seed = items.get_item_by_name(name)
        if not seed or seed.get("mastery") != "true" or seed.get("masteryTarget"):
            raise ValueError("The original herb mastery definition requires review.")
        stars = _list(seed.get("masteryLevel"))
        if len(stars) != 3:
            raise ValueError("The original herb mastery tiers require review.")
        earned = _whole(mastery.get(seed["code"], -1), "Saved herb mastery level", -1)
        if earned < len(stars) - 1:
            package = _package(seed)
            quantity = _whole(get_farming_int(levels[level], -1), "Herb Garden seed-package size", 1)
            entry = _entry(save, package)
            _whole((entry[0] if entry else 0) + quantity, "Resulting herb seed inventory", 1)
            return package, quantity, 0
    coins = harvester.get("limitedCoinYield")
    if not isinstance(coins, str) or not coins.isdigit():
        raise ValueError("The original mastered Herb Garden coin reward is unavailable.")
    return None, 0, _whole(int(coins), "Mastered Herb Garden coin reward", 1)


def ready_now(save, obj, *, now):
    """Validate a functional harvest, ready its timer, and return the cash price.

    The paid_buildings detached transaction charges after this validation.
    No reward is granted here; the original follow-up harvest owns it.
    """
    item, harvester, level, grow, now = _context(save, obj, now)
    _reward(save, level, harvester)
    if now - obj["plantTime"] / 1000 >= grow - 1:
        raise ValueError("This Herb Garden is already ready to harvest.")
    price = _whole(get_farming_int(item["name"] + "HarvestReadyNowCashPrice", -1),
                   "Herb Garden instant-harvest price", 1)
    obj.update(state="grown", plantTime=math.floor((now - grow) * 1000))
    return price


def harvest(save, stored, *, now, request_id=None):
    """Return None for unrelated objects, 1 for a reward and 0 for a retry."""
    item = items.get_item_by_name(stored.get("itemName"))
    if not manages(item):
        if item and get_farming_int(item["name"] + "HarvestReadyNowCashPrice", -1) > 0:
            raise ValueError("This building's original harvest loot table is not available locally.")
        return None
    detached = copy.deepcopy(save)
    matches = [row for row in detached["world"]["objectsArray"] if row.get("id") == stored.get("id")]
    if len(matches) != 1:
        raise ValueError("The harvested Herb Garden ID is missing or ambiguous.")
    obj = matches[0]
    _, harvester, level, grow, now = _context(detached, obj, now)
    key = str(_whole(request_id, "Herb Garden harvest request sequence")) if request_id is not None else None
    history = detached.get(REQUESTS_KEY, {})
    if not isinstance(history, dict):
        raise ValueError("The Herb Garden harvest retry history is invalid.")
    receipt = history.get(key)
    if key is not None and receipt is not None:
        if receipt != {"id": obj["id"], "plantTime": obj["plantTime"]}:
            raise ValueError("An Herb Garden harvest sequence was reused for another action.")
        return 0
    if now - obj["plantTime"] / 1000 < grow - 1:
        raise ValueError("This Herb Garden has not finished growing.")
    package, quantity, coins = _reward(detached, level, harvester)
    if package:
        storage.store_deposit_item_by_name(detached, package["name"], quantity, storage.GIFTBOX_ID)
    else:
        engine.apply_coins_diff(detached, coins)
    obj.update(state="bare", plantTime=now * 1000)
    if key is not None:
        history[key] = {"id": obj["id"], "plantTime": obj["plantTime"]}
        if len(history) > 2048:
            raise ValueError("Reload the farm before recording more Herb Garden harvests.")
        detached[REQUESTS_KEY] = history
    save.clear(); save.update(detached)
    return 1


def has_seed(save, seed):
    package = _package(seed)
    if package is None:
        return False
    entry = _entry(save, package)
    return bool(entry and entry[0] > 0)


def withdraw_seed_for_placement(save, seed, snapshot, params):
    """Plot.plant21806 automatically uses one saved seed before buying it."""
    if snapshot.get("className") != "Plot" or snapshot.get("state") != "planted":
        return None
    options = storage._given_options(params[0] if params else {})
    if any(options.get(key) for key in ("isGift", "isStorageWithdrawal", "isInventoryWithdrawal")):
        return None
    if not has_seed(save, seed):
        return None
    package = _package(seed)
    world_travel.guard_active_world(save)
    entry = _entry(save, package)
    # Player.useSeed3959 calls StorageItem.adjustQuantity, without the gift
    # sender shift performed by removeGift. Seed units keep imported senders.
    if entry[0] == 1:
        del save["userInfo"]["player"]["storageData"]["-1"][package["code"]]
    else:
        storage._adjust_quantity(entry, -1)
    return True


def start_session(save):
    save.pop(REQUESTS_KEY, None)
