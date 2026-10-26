"""Bounded additional farms; no story unlocks or rule-free creative mode.

Meadows' archived earlyAccess/cash60 option is retained:
level 15, 60 Farm Cash, one item 66e and world unlock, without a shipping
license. Original populated starts were not recovered, so the empty layout
is explicitly local. Meadows originally uses grass_theme/Home HUD assets;
the original MeadowsWorldInit and travel label still follow currentWorldType.

Lighthouse Cove retains its free general/all-access unlock and original
fisherman theme, exact plot caps and expansion rules. Its unrecovered starter
is also explicitly empty; ports, shipping and special features stay closed.
"""
import copy
from datetime import datetime, timezone
from functools import lru_cache
import math
from pathlib import Path
import re
import uuid
import xml.etree.ElementTree as ET
import zlib

from bundle import XML_DIR
from game_settings import CONFIG_CMS_XML, CONFIG_XML, get_farming_int, xp_to_level
import world_travel
import cove_rules

WORLD = "meadows"
ACCESS_OPTION = "cash60"
ACCESS_MARKER = "_additionalFarmAccess"
STATUS_LABEL = "Build & decorate • Story not restored"
# Only exact Meadows land gates are enabled; story and score are separate.
from meadows_rules import EXPANSION_EXPERIMENTS
COVE_EXPANSION_EXPERIMENTS = {"fv_fisherman_farm" + str(size): 1
                             for size in (14, 16, 18, 26, 28, 30, 32, 34)}


@lru_cache(maxsize=1)
def recovered_rules():
    """Fail closed when the shipped archive no longer matches our contract."""
    settings = ET.fromstring(zlib.decompress(Path(CONFIG_XML).read_bytes()))
    cms = ET.fromstring(zlib.decompress(Path(CONFIG_CMS_XML).read_bytes()))
    expansion = settings.find("expansions/expansion[@name='meadows']")
    if (expansion is None or expansion.findtext("worldRequirementOverride") != "farm"
            or expansion.get("currency") or expansion.get("score")
            or expansion.find("plotLimits") is not None
            or expansion.find("allAccess") is not None
            or settings.findall("farmExpansions/world[@name='meadows']")):
        raise ValueError("Sunflower Meadows' recovered rules are unavailable.")
    access = expansion.find("access[@type='earlyAccess']")
    if access is None or [(e.get("type"), e.get("value")) for e in access.findall("prereqs/prereq")] != [("prereq_check", "fv_xmw_access")]:
        raise ValueError("Sunflower Meadows' recovered access is unavailable.")
    option = access.find("options/option[@id='cash60']")
    if option is None or option.get("currency") != "cash" or option.get("amount") != "60":
        raise ValueError("Sunflower Meadows' recovered price is unavailable.")
    rewards = [dict(e.attrib) for e in option.findall("rewards/reward")]
    if rewards != [{"type": "item_grant", "value": "66e", "quantity": "1"},
                   {"type": "world_unlock", "value": "meadows"}]:
        raise ValueError("Sunflower Meadows' recovered rewards are unavailable.")
    prereq = cms.find(".//prereq[@name='fv_xmw_access']")
    expected = [("level_min", "15", None), ("experiment", "fv_meadows_activate", "3"),
                ("start_time", "10/08/2012", None)]
    if (prereq is None or prereq.get("type") != "AND"
            or [(e.get("type"), e.get("value"), e.get("variant")) for e in prereq] != expected):
        raise ValueError("Sunflower Meadows' recovered prerequisites are unavailable.")
    yimf = ET.fromstring(zlib.decompress(Path(XML_DIR, "gz/v855098/yimf.xml.gz").read_bytes()))
    if yimf.find("yimf[@type='grass_theme']") is None:
        raise ValueError("Sunflower Meadows' original grass terrain is unavailable.")
    return {"minimumLevel": 15, "cashCost": 60, "rewardCode": "66e",
            "startTime": int(datetime(2012, 10, 8, tzinfo=timezone.utc).timestamp())
                + (get_farming_int("globalServerUTCOffsetHours", 4) + 1) * 3600,
            "tileSet": "grass_theme", "storageId": -16}


def candidates(save=None):
    import themed_worlds  # imports this module; keep the import lazy
    rules = recovered_rules()
    cove = cove_rules.recovered_rules()
    # Verify the world-specific guard contract before exposing the unlock.
    cove_rules.guard_snapshot({"tileSet": cove["tileSet"], "sizeX": cove["initialSize"],
        "sizeY": cove["initialSize"], "objectsArray": []})
    def owned(world):
        if save is None:
            return False
        return (save["userInfo"].get("currentWorldType") == world
                or world in save.get(world_travel.STATE_KEY, {}).get("inactive", {}))
    return [{"worldType": WORLD, "name": "Sunflower Meadows", "label": STATUS_LABEL,
             "option": ACCESS_OPTION, "cashCost": rules["cashCost"],
             "minimumLevel": rules["minimumLevel"], "owned": owned(WORLD),
             "reward": "Includes one Spooky Lantern Tree for your gift box.",
             "starter": "Empty local layout; original populated starter not recovered.",
             "shipping": "Separate inventory; shipping license not included."},
            {"worldType": cove_rules.WORLD, "name": "Lighthouse Cove", "label": STATUS_LABEL,
             "option": cove["accessType"], "cashCost": 0,
             "minimumLevel": cove["minimumLevel"], "owned": owned(cove_rules.WORLD),
             "reward": "Free access. Starts with a limit of 35 ordinary plots.",
             "starter": "Empty local layout; original populated starter not recovered.",
             "shipping": "Separate inventory. Ports, crafting, shipping and story are not restored."}] + [
            {"worldType": key, "name": themed_worlds.SPECS[key]["name"], "label": STATUS_LABEL,
             "option": "allAccess", "cashCost": 0, "minimumLevel": themed_worlds.MINIMUM_LEVEL,
             "owned": owned(key),
             "reward": "Free access. Themed farming and decorating; quests and world scores are not restored.",
             "starter": (f"Empty local layout. We chose the archived {themed_worlds.SPECS[key]['name']} theme; the original starting layout was not recovered."
                         if themed_worlds.SPECS[key].get("localThemeChoice") else
                         "Empty local layout; original populated starter not recovered."),
             "shipping": "Separate inventory; shipping license not included."}
            for key in sorted(themed_worlds.active_worlds())]


def create(save, world_type, option=ACCESS_OPTION, *, now):
    """Add one farm through its recovered access without changing active worlds.

    Detached validation precedes publication. Repeat purchases reuse the
    durable snapshot without another charge/reward, including after reload.
    A summary/unlock/imported inventory without its snapshot is never reset.
    """
    import themed_worlds
    if world_type in themed_worlds.active_worlds():
        return themed_worlds.create(save, world_type, option, now=now)
    if world_type == cove_rules.WORLD:
        return _create_cove(save, option, now=now)
    if world_type != WORLD or option != ACCESS_OPTION:
        raise ValueError("Only Sunflower Meadows' recovered 60 Farm Cash option is available.")
    rules = recovered_rules()
    world_travel.validate(save)
    user = save["userInfo"]
    active = user.get("currentWorldType") or "farm"
    if active not in world_travel.supported_worlds():
        raise ValueError("The imported active world cannot be replaced.")
    old_state = save.get(world_travel.STATE_KEY)
    if active == WORLD or (old_state and WORLD in old_state["inactive"]):
        return False
    summaries = user["worldSummaryData"]
    unlocked = user.get("unlockedWorldTypes", [])
    if not isinstance(unlocked, list) or not all(isinstance(name, str) for name in unlocked):
        raise ValueError("The imported world unlock state is invalid.")
    if (WORLD in summaries or WORLD in unlocked
            or user["player"]["storageData"].get(str(rules["storageId"]))):
        raise ValueError("The requested world snapshot is missing; it cannot be recreated safely.")
    if (xp_to_level(user["player"]["xp"]) or 0) < rules["minimumLevel"]:
        raise ValueError("Sunflower Meadows requires player level 15.")
    import meadows_rules
    meadows_rules.guard_item_experiment({"experimentGate": "fv_meadows_activate",
                                        "experimentVariant": "3"})
    if now < rules["startTime"]:
        raise ValueError("Sunflower Meadows' recovered access date has not arrived.")
    cash = user["player"]["cash"]
    if type(cash) not in (int, float) or not math.isfinite(cash) or cash < rules["cashCost"]:
        raise ValueError("Sunflower Meadows requires 60 Farm Cash.")
    from items import get_item_by_code
    import storage
    reward = get_item_by_code(rules["rewardCode"])
    if reward is None or reward.get("name") != "spookylanterntree":
        raise ValueError("Sunflower Meadows' original entry reward is unavailable.")
    size = get_farming_int("farmSize")
    if size != 50:
        raise ValueError("Sunflower Meadows' recovered initial farm size is unavailable.")
    state = copy.deepcopy(old_state)
    if state is None:
        next_id = max(world_travel._reserved_ids(save), default=0) + 1
        if next_id > world_travel.MAX_OBJECT_ID + 1:
            raise ValueError("An imported storage ID exceeds the supported object ID range.")
        state = {"version": 1, "inactive": {}, "nextObjectId": next_id}
    state["inactive"][WORLD] = {"id": 2, "uid": str(uuid.uuid4()),
        "sizeX": size, "sizeY": size, "objectsArray": [], "messageManager": [],
        "tileSet": rules["tileSet"], "localStarter": "empty-meadows-v1"}
    new_user = copy.deepcopy(user)
    new_user["worldSummaryData"][WORLD] = {"firstLoaded": now, "lastLoaded": now,
                                           "storageId": rules["storageId"]}
    new_user["unlockedWorldTypes"] = list(dict.fromkeys([*unlocked, "farm", WORLD]))
    new_user["player"]["storageData"].setdefault(str(rules["storageId"]), {})
    new_user["player"]["cash"] = cash - rules["cashCost"]
    working = {**save, "userInfo": new_user, world_travel.STATE_KEY: state}
    working[ACCESS_MARKER] = {**copy.deepcopy(save.get(ACCESS_MARKER, {})),
        WORLD: {"version": 1, "option": ACCESS_OPTION, "purchasedAt": now,
                "cashPaid": rules["cashCost"], "rewardCode": rules["rewardCode"],
                "storyRestored": False}}
    storage.store_deposit_item_by_name(working, reward["name"], group=storage.GIFTBOX_ID)
    world_travel.validate(working)
    save["userInfo"] = new_user
    save[world_travel.STATE_KEY] = state
    save[ACCESS_MARKER] = working[ACCESS_MARKER]
    return True


def _create_cove(save, option, *, now):
    """Unlock only the recovered free Cove option, preserving the active farm."""
    if option not in ("generalAccess", "allAccess"):
        raise ValueError("Only Lighthouse Cove's recovered free access is available.")
    rules = cove_rules.recovered_rules()
    world_travel.validate(save)
    user = save["userInfo"]
    active = user.get("currentWorldType") or "farm"
    if active not in world_travel.supported_worlds():
        raise ValueError("The imported active world cannot be replaced.")
    old_state = save.get(world_travel.STATE_KEY)
    if active == cove_rules.WORLD or (old_state and cove_rules.WORLD in old_state["inactive"]):
        return False
    unlocked = user.get("unlockedWorldTypes", [])
    if not isinstance(unlocked, list) or not all(isinstance(name, str) for name in unlocked):
        raise ValueError("The imported world unlock state is invalid.")
    if (cove_rules.WORLD in user["worldSummaryData"] or cove_rules.WORLD in unlocked
            or user["player"]["storageData"].get(str(rules["storageId"]))):
        raise ValueError("The requested world snapshot is missing; it cannot be recreated safely.")
    if (xp_to_level(user["player"]["xp"]) or 0) < rules["minimumLevel"]:
        raise ValueError("Lighthouse Cove requires player level 15.")
    if now < rules["startTime"]:
        raise ValueError("Lighthouse Cove's recovered access date has not arrived.")
    state = copy.deepcopy(old_state)
    if state is None:
        next_id = max(world_travel._reserved_ids(save), default=0) + 1
        if next_id > world_travel.MAX_OBJECT_ID + 1:
            raise ValueError("An imported storage ID exceeds the supported object ID range.")
        state = {"version": 1, "inactive": {}, "nextObjectId": next_id}
    size = rules["initialSize"]
    state["inactive"][cove_rules.WORLD] = {"id": 2, "uid": str(uuid.uuid4()),
        "sizeX": size, "sizeY": size, "objectsArray": [], "messageManager": [],
        "tileSet": rules["tileSet"], "localStarter": "empty-fisherman-v1"}
    new_user = copy.deepcopy(user)
    new_user["worldSummaryData"][cove_rules.WORLD] = {"firstLoaded": now,
        "lastLoaded": now, "storageId": rules["storageId"]}
    new_user["unlockedWorldTypes"] = list(dict.fromkeys([*unlocked, "farm", cove_rules.WORLD]))
    new_user["player"]["storageData"].setdefault(str(rules["storageId"]), {})
    marker = {**copy.deepcopy(save.get(ACCESS_MARKER, {})), cove_rules.WORLD:
        {"version": 1, "option": option, "purchasedAt": now, "cashPaid": 0,
         "storyRestored": False}}
    working = {**save, "userInfo": new_user, world_travel.STATE_KEY: state,
               ACCESS_MARKER: marker}
    world_travel.validate(working)
    save["userInfo"] = new_user
    save[world_travel.STATE_KEY] = state
    save[ACCESS_MARKER] = marker
    return True


def _nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _nodes(child)


def world_requirement_matches(item, world_type):
    """Original WorldRequirement.check honors Meadows' non-strict Home alias."""
    raw = item.get("requirements")
    requirements = [e for e in _nodes(raw) if e.get("className") == "World"]
    if not requirements:
        return True
    results = [e.get("name") == world_type or (world_type == WORLD
               and e.get("strict") not in (True, "true") and e.get("name") == "farm")
               for e in requirements]
    compare = next((e.get("compare") for e in _nodes(raw) if e.get("compare")), "all")
    return any(results) if compare == "any" else all(results)


def _guard_item_access(save, item, *, neighbor_count, quantity=1, existing=None,
                       world_type=WORLD):
    if item is None:
        raise ValueError("This item is not in the recovered catalog.")
    if not world_requirement_matches(item, world_type):
        raise ValueError("That item cannot be used on the current additional farm.")
    if any(e.get("className") not in (None, "World") for e in _nodes(item.get("requirements"))):
        raise ValueError("This item's special requirements are not restored for additional farms.")
    from client_catalog import purchase_required_level
    if (xp_to_level(save["userInfo"]["player"]["xp"]) or 0) < purchase_required_level(item):
        raise ValueError("The player's level is too low for this item.")
    if neighbor_count < int(item.get("minNeighbors") or 0):
        raise ValueError("This item requires more neighbors.")
    limit = int(item.get("limit") or 0)
    if limit and quantity + sum(obj is not existing and obj.get("itemName") == item["name"]
                                for obj in save["world"]["objectsArray"]) > limit:
        raise ValueError("This farm already owns the maximum number of that item.")
    if item.get("type") not in ("seed", "tree", "animal", "building", "decoration", "vehicle"):
        raise ValueError("This item's world mechanics are not restored for additional farms.")


def _purchase_currency(item, currency):
    # A missing market is the original ordinary coin market. A named world
    # currency must never inherit the generic engine's fallback coin balance.
    expected = item.get("market") or "coins"
    if expected not in ("cash", "coins"):
        raise ValueError("This item's purchase currency is not supported in Sunflower Meadows.")
    currency = currency or expected
    if currency == "gold":
        currency = "coins"
    if currency != expected:
        raise ValueError("The purchase currency does not match this item's recovered price.")
    return currency


def _guard_purchase_dates(item, *, now=None):
    """Honor the original FarmItem date window for every ordinary market."""
    from engine import timestamp_now
    if now is None:
        now = timestamp_now()
    # FarmItem.checkDateGateXML/Data compares synchronizedDateToNumber with
    # serverTime: start < now and end > now. FarmGameUtil parses US calendar
    # dates as UTC and adds one hour to the configured offset when isDST=0,
    # which is the flag our gateway serves. A historical start (including the
    # Unix epoch) is an open window, not evidence of an unsupported promotion.
    offset = (get_farming_int("globalServerUTCOffsetHours", 4) + 1) * 3600
    for key in ("limitedStart", "limitedEnd"):
        if key not in item:
            continue
        value = item[key]
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}", value):
            raise ValueError("This item's recovered purchase date is invalid.")
        try:
            boundary = datetime.strptime(value, "%m/%d/%Y").replace(tzinfo=timezone.utc).timestamp() + offset
        except ValueError:
            raise ValueError("This item's recovered purchase date is invalid.") from None
        if key == "limitedStart" and now <= boundary:
            raise ValueError("This item's purchase start date has not arrived.")
        if key == "limitedEnd" and now >= boundary:
            raise ValueError("This item's purchase end date has passed.")


def guard_market_purchase(save, item, currency=None, *, quantity=1, neighbor_count=None,
                          existing=None):
    """Gate placement and source-less market-to-storage before either can pay."""
    current = world_travel.guard_active_world(save)
    import crafting
    if isinstance(item, dict) and item.get("className") == "CraftingCottageBuilding":
        if item.get("name") not in crafting.COTTAGES.values():
            raise ValueError("This crafting cottage's production is not restored for purchase.")
        if type(quantity) is not int or quantity != 1:
            raise ValueError("A crafting cottage must be purchased one at a time.")
    import themed_worlds
    if current in themed_worlds.active_worlds():
        if neighbor_count is None:
            from player import neighbor_uids
            neighbor_count = len(neighbor_uids(save["userInfo"]["player"]["userId"]))
        themed_worlds.guard_purchase(save, item, currency, quantity=quantity,
                                     neighbor_count=neighbor_count, existing=existing)
        return
    if current in ("farm", "england", WORLD, cove_rules.WORLD):
        if not isinstance(item, dict):
            raise ValueError("This item is not in the recovered catalog.")
        _guard_purchase_dates(item)
    if current not in (WORLD, cove_rules.WORLD):
        if current in ("farm", "england"):
            # Home placement and direct inventory purchases share this gate.
            # A gift or owned-object transfer never reaches the purchase path.
            # Tiered cottages expose their selected original tier's level and
            # price, rather than the unpriced parent catalog record.
            import heritage_pricing
            if current != "farm" and heritage_pricing.is_overlaid(item):
                raise ValueError("This Home Farm item is not sold on this farm.")
            if (current == "farm" and isinstance(item, dict) and item.get("type") == "seed"
                    and not world_requirement_matches(item, "farm")):
                # A crop from another world is never sold on Home, so no inventory purchase pays for it.
                raise ValueError(heritage_pricing.crop_refusal(item) or "This crop cannot be bought on this farm.")
            item = crafting.purchase_catalog_item(save, item)
            from client_catalog import purchase_required_level
            if (xp_to_level(save["userInfo"]["player"]["xp"]) or 0) < purchase_required_level(item):
                raise ValueError("The player's level is too low for this item.")
            # Inventory purchases use the same catalog price as placement.
            # An absent cash price cannot turn an ordinary coin item free;
            # preflight the whole quantity before a direct storage call pays.
            from engine import catalog_price
            currency = _purchase_currency(item, currency)
            cost = catalog_price(item, "cash" if currency == "cash" else "cost")
            if cost is None or cost < 0:
                raise ValueError("This item's recovered price is unavailable.")
            balance = save["userInfo"]["player"]["cash" if currency == "cash" else "gold"]
            if (type(balance) not in (int, float) or not math.isfinite(balance)
                    or balance < cost * quantity):
                raise ValueError("Not enough currency for this inventory purchase.")
        return
    if current == cove_rules.WORLD:
        item = crafting.purchase_catalog_item(save, item)
        cove_rules.guard_snapshot(save["world"])
        cove_rules.guard_special_item(item)
        cove_rules.guard_land_terrain(item)
    from engine import catalog_price
    if neighbor_count is None:
        from player import neighbor_uids
        neighbor_count = len(neighbor_uids(save["userInfo"]["player"]["userId"]))
    _guard_item_access(save, item, neighbor_count=neighbor_count, quantity=quantity,
                       existing=existing, world_type=current)
    currency = _purchase_currency(item, currency)
    if item.get("buyable") in (False, "false"):
        raise ValueError("This item is not available for purchase.")
    if (any(item.get(key) for key in ("purchasePrereqs", "prereqs", "requiredMastery",
            "requiredQuest", "license", "experiment", "gateCode"))
            or (item.get("unlock") not in (None, "", "neighbor")
                and not (current == cove_rules.WORLD and item.get("unlock") == "instance_tiered"
                         and cove_rules._restored_cottage(item)))
            or (current != WORLD and item.get("experimentGate"))
            or (item.get("marketPrereqs")
                and not cove_rules.allows_cellar_market_prerequisite(item, current))):
        raise ValueError("This item's special purchase prerequisites are not restored.")
    if current == WORLD:
        import meadows_rules
        meadows_rules.guard_item_experiment(item)
    cost = catalog_price(item, "cash" if currency == "cash" else "cost")
    if cost is None or cost < 0:
        raise ValueError("This item's recovered price is unavailable.")
    balance = save["userInfo"]["player"]["cash" if currency == "cash" else "gold"]
    if (type(balance) not in (int, float) or not math.isfinite(balance)
            or balance < cost * quantity):
        raise ValueError("Not enough currency for this Sunflower Meadows purchase.")


@lru_cache(maxsize=1)
def _land_terrain_names():
    settings = ET.fromstring(zlib.decompress(Path(CONFIG_XML).read_bytes()))
    terrains = settings.find("terrains")
    if terrains is None:
        raise ValueError("The recovered terrain rules are unavailable.")
    names = {node.get("name") for node in terrains.findall("primaryTerrains/terrain")
             if node.get("code") == "1"}
    if names != {"land"}:
        raise ValueError("The recovered land terrain code is unavailable.")
    hierarchy = terrains.findall("terrainHierarchy/terrain")
    while True:
        parents = {node.get("name") for node in hierarchy
                   if any(child.get("name") in names for child in node.findall("terrain"))}
        if parents <= names:
            return frozenset(names)
        names.update(parents)


def _guard_land_terrain(item):
    # FarmItem.getTerrainSetCodes defaults to LAND_TERRAIN_CODE. Explicit
    # terrain sets are resolved through the original settings, not world names.
    terrains = [node["name"] for node in _nodes(item.get("terrainSet")) if "name" in node]
    if terrains and not set(terrains).intersection(_land_terrain_names()):
        raise ValueError("This item requires terrain unavailable in Sunflower Meadows.")


def _placement_retry(existing, snapshot, item):
    if existing is None or any(existing.get(key) != snapshot.get(key)
                               for key in ("className", "itemName", "position")):
        return False
    return (existing.get("tempId") == snapshot.get("id")
            and existing.get("state") == snapshot.get("state")) or (
        item.get("type") == "seed" and snapshot.get("state") == "planted"
        and existing.get("className") == "Plot" and existing.get("state") in ("planted", "grown"))


def guard_action(save, action, snapshot, params, *, neighbor_count=0):
    """Apply each additional farm's own rules before shared action mutations."""
    import themed_worlds
    if save["userInfo"].get("currentWorldType") in themed_worlds.active_worlds():
        themed_worlds.guard_action(save, action, snapshot, params, neighbor_count=neighbor_count)
        return
    if save["userInfo"].get("currentWorldType") == cove_rules.WORLD:
        _guard_cove_action(save, action, snapshot, params, neighbor_count=neighbor_count)
        return
    if save["userInfo"].get("currentWorldType") != WORLD or action not in ("plow", "place", "move"):
        return
    from items import get_item_by_name
    world = save["world"]
    item = get_item_by_name(snapshot.get("itemName")) if snapshot.get("itemName") else None
    existing = next((obj for obj in world["objectsArray"]
                     if obj["id"] == snapshot.get("id")
                     or obj.get("tempId") == snapshot.get("id")), None)
    if action in ("plow", "place"):
        import meadows_rules
        meadows_rules.guard_new_object(save, snapshot, existing)
    if action == "plow":
        # Plot.executePlow retains the harvested crop's name and timer in all
        # ordinary worlds. Only a saved fallow/plowed plot may retain them.
        cove_rules.guard_plow_snapshot(snapshot, existing)
        if existing is not None and existing.get("className") != "Plot":
            raise ValueError("Plowing cannot replace an existing Meadows object.")
        if existing is None or existing.get("state") != "plowed":
            balance = save["userInfo"]["player"]["gold"]
            if (type(balance) not in (int, float) or not math.isfinite(balance)
                    or balance < get_farming_int("plowCost", 15)):
                raise ValueError("Not enough coins to plow in Sunflower Meadows.")
    if action == "move" and (existing is None or any(
            existing.get(key) != snapshot.get(key) for key in ("className", "itemName"))):
        raise ValueError("Moving a Meadows object cannot change its identity.")
    if action == "place":
        _guard_item_access(save, item, neighbor_count=neighbor_count, existing=existing)
        if (item.get("type") == "seed") != (snapshot.get("className") == "Plot"):
            raise ValueError("A planted crop must retain its original Plot class.")
        if item.get("placeable") in (False, "false"):
            raise ValueError("This catalog item cannot be placed on the farm.")
        expected = item.get("className") or {"seed": "Plot", "animal": "Animal",
            "tree": "Tree", "building": "Building", "decoration": "Decoration"}.get(item.get("type"))
        if snapshot.get("className") != expected:
            raise ValueError("A Meadows item must retain its recovered object class.")
        if existing is not None and item.get("type") != "seed" and not _placement_retry(existing, snapshot, item):
            raise ValueError("A Meadows placement cannot replace an existing object; use Move.")
        _guard_land_terrain(item)
        from storage import _given_options
        options = _given_options(params[0] if params and isinstance(params[0], dict) else {})
        withdrawal = bool(options.get("isGift") or options.get("isInventoryWithdrawal")
                          or options.get("isStorageWithdrawal"))
        if not withdrawal and not _placement_retry(existing, snapshot, item):
            guard_market_purchase(save, item, options.get("currency"),
                                  neighbor_count=neighbor_count, existing=existing)
    position = snapshot.get("position")
    if not isinstance(position, dict):
        raise ValueError("A Meadows placement requires a position.")
    for coordinate, dimension in (("x", "sizeX"), ("y", "sizeY")):
        value = position.get(coordinate)
        # Plot owns the cultivated ground footprint even when its catalog seed
        # reports a smaller icon/resource size.
        size = int((item or {}).get(dimension) or 1)
        if snapshot.get("className") == "Plot":
            size = max(4, size)
        if (not world_travel._integer(value) or value < 0
                or value + size > world[dimension]):
            raise ValueError("The placement is outside the current Sunflower Meadows land.")
    if position.get("z", 0) != 0:
        raise ValueError("Sunflower Meadows placements require ordinary ground terrain.")


def _guard_cove_action(save, action, snapshot, params, *, neighbor_count):
    """Fence every Cove object action before shared handlers can mutate it."""
    from items import get_item_by_name
    cove_rules.guard_plot_cap(save, action, snapshot)
    if any(snapshot.get(flag) for flag in ("isJumbo", "isBigPlot", "isProduceItem", "isSuperPlot")):
        raise ValueError("Specialized Lighthouse Cove plots are not restored.")
    if action not in ("plow", "place", "move", "harvest", "clear",
                       "sell", "store", "getStorageInfo"):
        raise ValueError("This Lighthouse Cove feature action is not restored.")
    # Original market-to-inventory calls address the inventory itself. The
    # storage handler validates the item, source, quantity and price separately.
    if (action == "store" and snapshot.get("id") == cove_rules.STORAGE_ID
            and snapshot.get("className") == "StorageBuilding"
            and snapshot.get("itemName") is None):
        return
    world = save["world"]
    existing = next((obj for obj in world["objectsArray"]
        if obj.get("id") == snapshot.get("id")
        or (snapshot.get("id") is not None and obj.get("tempId") == snapshot.get("id"))), None)
    if action not in ("plow", "place") and existing is None:
        raise ValueError("A Lighthouse Cove action requires its saved object.")
    if existing is not None and existing.get("itemName"):
        saved_item = get_item_by_name(existing["itemName"])
        cove_rules.guard_special_item(saved_item)
        cove_rules.guard_land_terrain(saved_item)
        _guard_cove_item_class(saved_item, existing)
        if not world_requirement_matches(saved_item, cove_rules.WORLD):
            raise ValueError("That saved item cannot be used in Lighthouse Cove.")
    if action not in ("place", "plow") and any(
            existing.get(key) != snapshot.get(key) for key in ("className", "itemName")):
        raise ValueError("A Lighthouse Cove action cannot change its saved object's identity.")
    if (action not in ("place", "plow", "move") and "position" in snapshot
            and snapshot["position"] != existing.get("position")):
        raise ValueError("Only moving can change a Lighthouse Cove object's position.")
    if action == "clear" and existing.get("className") == "Plot":
        balance = save["userInfo"]["player"]["gold"]
        if (type(balance) not in (int, float) or not math.isfinite(balance)
                or balance < get_farming_int("plowCost", 15)):
            raise ValueError("Not enough coins to clear a Lighthouse Cove plot.")
    item = get_item_by_name(snapshot.get("itemName")) if snapshot.get("itemName") else None
    if snapshot.get("className") == "Plot" and item is None:
        if action == "place":
            raise ValueError("Planting in Lighthouse Cove requires a recovered crop.")
    else:
        cove_rules.guard_special_item(item)
        cove_rules.guard_land_terrain(item)
        _guard_cove_item_class(item, snapshot)
        if not world_requirement_matches(item, cove_rules.WORLD):
            raise ValueError("That item cannot be used in Lighthouse Cove.")
    if action not in ("plow", "place", "move"):
        return
    if action == "plow":
        cove_rules.guard_plow_snapshot(snapshot, existing)
        if existing is None or existing.get("state") != "plowed":
            balance = save["userInfo"]["player"]["gold"]
            if (type(balance) not in (int, float) or not math.isfinite(balance)
                    or balance < get_farming_int("plowCost", 15)):
                raise ValueError("Not enough coins to plow in Lighthouse Cove.")
    if action == "place":
        _guard_item_access(save, item, neighbor_count=neighbor_count,
                           existing=existing, world_type=cove_rules.WORLD)
        if (item.get("type") == "seed") != (snapshot.get("className") == "Plot"):
            raise ValueError("A Lighthouse Cove crop must retain its original Plot class.")
        if snapshot.get("className") not in ("Plot", "Animal", "Tree", "Building", "Decoration",
                "RotateableDecoration", "MaskedDecoration", "GateDecoration", "StorageBuilding", "InventoryCellar",
                "CraftingCottageBuilding"):
            raise ValueError("This Lighthouse Cove object class is not restored.")
        if item.get("placeable") in (False, "false"):
            raise ValueError("This catalog item cannot be placed on the farm.")
        from storage import _given_options
        options = _given_options(params[0] if params and isinstance(params[0], dict) else {})
        retry = _placement_retry(existing, snapshot, item)
        if not retry and not (options.get("isGift") or options.get("isInventoryWithdrawal")
                              or options.get("isStorageWithdrawal")):
            guard_market_purchase(save, item, options.get("currency"),
                                  neighbor_count=neighbor_count, existing=existing)
    position = snapshot.get("position")
    if not isinstance(position, dict):
        raise ValueError("A Lighthouse Cove placement requires a position.")
    for coordinate, dimension in (("x", "sizeX"), ("y", "sizeY")):
        value = position.get(coordinate)
        size = int((item or {}).get(dimension) or 1)
        if snapshot.get("className") == "Plot":
            size = max(4, size)
        if not world_travel._integer(value) or value < 0 or value + size > world[dimension]:
            raise ValueError("The placement is outside the current Lighthouse Cove land.")
    if position.get("z", 0) != 0:
        raise ValueError("Lighthouse Cove placements require ordinary ground terrain.")


def _guard_cove_item_class(item, snapshot):
    expected = item.get("className") or {"seed": "Plot", "animal": "Animal", "tree": "Tree",
        "building": "Building", "decoration": "Decoration"}.get(item.get("type"))
    if snapshot.get("className") != expected:
        raise ValueError("A Lighthouse Cove item must retain its recovered object class.")


def _guard_expansion_prerequisites(item):
    if (any(e.get("className") not in (None, "World") for e in _nodes(item.get("requirements")))
            or any(item.get(key) for key in ("purchasePrereqs", "prereqs", "requiredMastery",
                "requiredQuest", "license", "marketPrereqs", "gateCode", "experiment",
                "limitedStart", "limitedEnd"))
            or item.get("unlock") not in (None, "", "neighbor")
            or item.get("experimentVariant") not in (None, "", 1, "1")):
        raise ValueError("This expansion's special prerequisites are not restored.")


def expand_farm(save, item, currency, *, neighbor_count=0):
    """Handle each additional farm's next-size expansion; return False elsewhere."""
    world_travel.guard_active_world(save)
    import themed_worlds
    if save["userInfo"].get("currentWorldType") in themed_worlds.active_worlds():
        return themed_worlds.expand(save, item, currency, neighbor_count=neighbor_count)
    if save["userInfo"].get("currentWorldType") == cove_rules.WORLD:
        return _expand_cove(save, item, currency, neighbor_count=neighbor_count)
    if save["userInfo"].get("currentWorldType") != WORLD:
        return False
    import meadows_rules
    from engine import catalog_price
    if (not isinstance(item, dict) or item.get("subtype") != "expand_farm"
            or not item.get("name", "").startswith("xmwfarm")
            or not world_requirement_matches(item, WORLD)):
        raise ValueError("Sunflower Meadows requires its own recovered land expansions.")
    _guard_expansion_prerequisites(item)
    squares = meadows_rules.expansion_contract(item)
    current = save["world"]["sizeX"]
    if current not in meadows_rules.WIDTHS or save["world"]["sizeY"] != current:
        raise ValueError("The imported Meadows land size requires recovery before expansion.")
    if squares == current == save["world"]["sizeY"]:
        return True
    next_size = next((value for value in meadows_rules.WIDTHS if value > current), None)
    if squares != next_size or save["world"]["sizeY"] != current:
        raise ValueError("Buy Sunflower Meadows land expansions in their original order.")
    gate = item.get("experimentGate")
    if gate and (EXPANSION_EXPERIMENTS.get(gate, 0) != 1
                 or not meadows_rules.experiment_enabled(gate)):
        raise ValueError("That Sunflower Meadows expansion's experiment is not enabled.")
    if item.get("buyable") in (False, "false"):
        raise ValueError("That Sunflower Meadows expansion is not available for purchase.")
    if (xp_to_level(save["userInfo"]["player"]["xp"]) or 0) < int(item.get("requiredLevel") or 1):
        raise ValueError("The player's level is too low for this expansion.")
    if neighbor_count < int(item.get("minNeighbors") or 0):
        raise ValueError("This expansion requires more neighbors.")
    currency = _purchase_currency(item, currency)
    # ChangeFarmItem.saleCash hard-codes 1 for expand_farm; match TExpandFarm.
    cost = 1 if currency == "cash" else catalog_price(item, "cost")
    if cost is None or cost < 0:
        raise ValueError("The recovered expansion price is unavailable.")
    balance_key = "cash" if currency == "cash" else "gold"
    player = save["userInfo"]["player"]
    balance = player[balance_key]
    if (type(balance) not in (int, float) or not math.isfinite(balance) or balance < cost):
        raise ValueError("Not enough currency for this Sunflower Meadows expansion.")
    player[balance_key] -= cost
    save["world"]["sizeX"] = squares
    save["world"]["sizeY"] = squares
    return True


def _expand_cove(save, item, currency, *, neighbor_count):
    from engine import catalog_price
    cove_rules.guard_snapshot(save["world"])
    if (not isinstance(item, dict) or item.get("subtype") != "expand_farm"
            or not item.get("name", "").startswith("xlcfarm")
            or not world_requirement_matches(item, cove_rules.WORLD)):
        raise ValueError("Lighthouse Cove requires its own recovered land expansions.")
    _guard_expansion_prerequisites(item)
    current = save["world"]["sizeX"]
    squares = int(item.get("squares") or 0)
    cove_rules.plot_limit(squares)
    if squares == current:
        return True
    sizes = sorted(cove_rules.recovered_rules()["plotLimits"])
    if squares != next((width for width in sizes if width > current), None):
        raise ValueError("Buy Lighthouse Cove land expansions in their original order.")
    gate = item.get("experimentGate")
    if gate and COVE_EXPANSION_EXPERIMENTS.get(gate, 0) != 1:
        raise ValueError("That Lighthouse Cove expansion's experiment is not enabled.")
    if item.get("buyable") in (False, "false"):
        raise ValueError("That Lighthouse Cove expansion is not available for purchase.")
    if (xp_to_level(save["userInfo"]["player"]["xp"]) or 0) < int(item.get("requiredLevel") or 1):
        raise ValueError("The player's level is too low for this expansion.")
    if neighbor_count < int(item.get("minNeighbors") or 0):
        raise ValueError("This expansion requires more neighbors.")
    currency = _purchase_currency(item, currency)
    # ChangeFarmItem.saleCash is 1 for expand_farm, including Cove variants.
    cost = 1 if currency == "cash" else catalog_price(item, "cost")
    player = save["userInfo"]["player"]
    balance_key = "cash" if currency == "cash" else "gold"
    balance = player[balance_key]
    if (cost is None or cost < 0 or type(balance) not in (int, float)
            or not math.isfinite(balance) or balance < cost):
        raise ValueError("Not enough currency for this Lighthouse Cove expansion.")
    additions = cove_rules.expansion_added_objects(squares)
    if additions:
        raise ValueError("Lighthouse Cove's expansion-added objects are not restored.")
    player[balance_key] -= cost
    save["world"]["sizeX"] = save["world"]["sizeY"] = squares
    return True
