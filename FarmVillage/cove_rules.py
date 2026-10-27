"""Recovered Lighthouse Cove rules, without activating or creating a farm.

The source for the terrain and plot limits is the preserved XML plus the
original FarmGameWorld, WorldManager and ExpansionPlotLimits client methods.
Ordinary ground farming keeps the recovered plot caps. The exact Cove Port
and restaurant are admitted through their own durable service contracts.
Unknown terrain maps and specialized plot economies remain unavailable.
"""
import copy
from datetime import datetime, timezone
from functools import lru_cache
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import zlib

from bundle import XML_DIR

WORLD = "fisherman"
STORAGE_ID = -9  # WorldManager.FISHERMAN_INVENTORY_ID, original signed byte.
_WIDTHS = tuple(range(50, 243, 8))
_PLOT_CAPS = (35, 45, 60, 75, 95, 115, 140, 165, 195, 225, 255, 315,
              375, 435, 515, 595, 675, 755, 835, 915, 995, 1075, 1155,
              1240, 1325)
_BASIC_CLASSES = frozenset((None, "Animal", "Tree", "Building", "Decoration",
    "RotateableDecoration", "MaskedDecoration", "GateDecoration",
    "StorageBuilding", "InventoryCellar"))
_BASIC_TYPES = frozenset(("seed", "animal", "tree", "building", "decoration"))
_SPECIAL_PLOT_FLAGS = ("isJumbo", "isBigPlot", "isProduceItem", "isSuperPlot")
_STORAGE_WORLDS = ("garden", "england", WORLD, "farm", "village", "meadows")


def _xml(name):
    return ET.fromstring(zlib.decompress(Path(XML_DIR, "gz/v855098", name).read_bytes()))


def _integer(value):
    return (type(value) in (int, float) and math.isfinite(value)
            and value == int(value))


@lru_cache(maxsize=1)
def _archive_contract():
    settings, cms, yimfs = (_xml(name) for name in
        ("gameSettings.xml.gz", "gameSettingsCMS.xml.gz", "yimf.xml.gz"))
    expansion = settings.find("expansions/expansion[@name='fisherman']")
    if (expansion is None or expansion.attrib != {"name": WORLD}
            or expansion.find("worldRequirementOverride") is not None
            or expansion.find("startingFarm") is not None):
        raise ValueError("Lighthouse Cove's recovered world rules are unavailable.")
    expected_reward = [{"type": "world_unlock", "value": WORLD}]
    for access_name in ("generalAccess", "allAccess"):
        access = expansion.find(access_name)
        prereq_name = "fv_fisherman_" + ("general_access" if access_name == "generalAccess"
                                         else "all_access")
        if (access is None or access.attrib
                or [dict(e.attrib) for e in access.findall("prereqs/prereq")] !=
                    [{"type": "prereq_check", "value": prereq_name}]
                or [dict(e.attrib) for e in access.findall("rewards/reward")] != expected_reward):
            raise ValueError("Lighthouse Cove's recovered free access is unavailable.")
    expected_prereqs = {
        "fv_fisherman_all_access": [{"type": "prereq_check", "value": "fv_fisherman_general_access"}],
        "fv_fisherman_general_access": [
            {"type": "level_min", "value": "15"},
            {"type": "has_not_unlocked_world", "value": WORLD},
            {"type": "start_time", "value": "9/19/2011"}],
    }
    for name, children in expected_prereqs.items():
        prereq = cms.find(".//prereq[@name='%s']" % name)
        if (prereq is None or prereq.get("type") != "AND"
                or [dict(e.attrib) for e in prereq] != children):
            raise ValueError("Lighthouse Cove's recovered access prerequisites are unavailable.")
    farming_size = cms.find("farming/farmingEntry[@key='farmSize']")
    if farming_size is None or farming_size.get("value") != "50":
        raise ValueError("Lighthouse Cove's recovered initial farm size is unavailable.")
    limits = expansion.find("plotLimits")
    expected_limits = [{"squares": str(width), "plots": str(cap)}
                       for width, cap in zip(_WIDTHS, _PLOT_CAPS)]
    if (limits is None or len(limits) != len(expected_limits)
            or any(node.tag != "plotLimit" or len(node) for node in limits)
            or [dict(node.attrib) for node in limits] != expected_limits):
        raise ValueError("Lighthouse Cove's recovered plot limits are unavailable.")
    # The archive has additions for Winter Wonderland, Hawaii and other worlds,
    # but none for Cove. Do not inherit another world's objects or Home grants.
    if settings.findall("farmExpansions/world[@name='fisherman']"):
        raise ValueError("Lighthouse Cove expansion-added objects require a new audit.")
    theme = yimfs.find("yimf[@type='fisherman']")
    expected_theme = {
        "weights": "5,10,20,25,30,35,40,45,50,51,56,61,66,71,76,81",
        "bgColor": "0xFF6E8422", "outlineColor": "0x617519",
        "expansionColor": "0x3A6F29", "tileClass": "cove",
        "backgroundPath": "assets/Environment/xcove_themeBackground_",
        "horizon": "assets/Environment/xcove_theme.swf", "skyColor": "0xFF6F65C8",
    }
    if (theme is None or theme.attrib != {"type": WORLD}
            or {e.tag: (e.text or "").strip() for e in theme} != expected_theme
            or len(theme) != len(expected_theme)):
        raise ValueError("Lighthouse Cove's recovered terrain is unavailable.")
    if expansion.findtext("shippingLicenseItemName") != "pkg_fishermanXfer":
        raise ValueError("Lighthouse Cove's recovered shipping rule is unavailable.")
    return {"worldType": WORLD, "minimumLevel": 15, "accessType": "allAccess",
            "cashCost": 0, "coinCost": 0, "rewards": expected_reward,
            "startTime": int(datetime(2011, 9, 19, tzinfo=timezone.utc).timestamp()),
            "initialSize": 50, "tileSet": WORLD, "storageId": STORAGE_ID,
            "currency": "coins", "score": None, "score2": None,
            "plotLimits": dict(zip(_WIDTHS, _PLOT_CAPS)),
            "theme": expected_theme, "shippingLicenseItemName": "pkg_fishermanXfer",
            "expansionAddedObjects": ()}


def recovered_rules():
    """Return an independent copy of the checked original rule contract."""
    return copy.deepcopy(_archive_contract())


@lru_cache(maxsize=1)
def _storage_market_worlds():
    """The original cellar market gate is an OR of exact current locations."""
    prereq = _xml("gameSettingsCMS.xml.gz").find(".//prereq[@name='storage_world_locks']")
    if (prereq is None or prereq.attrib != {"name": "storage_world_locks", "type": "OR"}
            or any(node.tag != "prereq" or len(node) for node in prereq)
            or [dict(node.attrib) for node in prereq] != [
                {"type": "location", "value": name} for name in _STORAGE_WORLDS]):
        raise ValueError("The recovered cellar market prerequisite is unavailable.")
    return frozenset(_STORAGE_WORLDS)


def allows_cellar_market_prerequisite(item, world_type):
    """Restore only hatchstorage's checked storage_world_locks predicate.

    This does not waive level, price, quantity, world requirements or the
    one-cellar limit; the ordinary purchase/placement guards still own them.
    Other items and unrecognized prerequisite names retain the closed gate.
    """
    if item.get("name") != "hatchstorage" or item.get("marketPrereqs") != "storage_world_locks":
        return False
    expected = {"name": "hatchstorage", "code": "v0", "type": "building",
        "className": "InventoryCellar", "requiredLevel": "16", "cost": "1",
        "capacity": "1250", "limit": "1", "storageSize": "1", "disallowDelete": "1",
        "marketPrereqs": "storage_world_locks", "buyable": "true", "placeable": "true",
        "giftable": "false", "storageType": {"additionalItemClass": "hatchstorage", "itemClass": "Inventory"},
        "requirements": [{"compare": "any"}, {"requirement": [
            {"name": name, "className": "World"} for name in _STORAGE_WORLDS]}]}
    if (any(item.get(key) != value for key, value in expected.items())
            or item.get("market") is not None or item.get("cash") is not None):
        raise ValueError("The recovered cellar catalog rules are unavailable.")
    return world_type in _storage_market_worlds()


def plot_limit(width):
    """Use an exact width key, as ExpansionPlotLimits.getPlotLimitByTerrainCode.

    Unlike the original client's zero result for an unknown width, unsupported
    imported dimensions are rejected before any server mutation can proceed.
    """
    if not _integer(width) or width not in _archive_contract()["plotLimits"]:
        raise ValueError("That Lighthouse Cove size has no recovered plot limit.")
    return _archive_contract()["plotLimits"][int(width)]


def expansion_added_objects(width):
    plot_limit(width)
    return ()


def _guard_serialized_plot_flags(world):
    """Keep unsupported original extra-item systems out of ordinary Cove play.

    FarmGameWorld.loadObject reads serializedExtraItemFlags, not per-object
    isSuperPlot. BitFlagsById packs each uint as (id << 16) | flags, in arrays
    of sixteen-flag groups. Group zero includes organic fertilizer/jumbo (1),
    ignore-smart-buildable-requirements (2), and super plot (3). None has a
    recovered durable Cove transaction. Preserve imported data and refuse it;
    never clear these bits to make a snapshot appear ordinary.
    """
    serial = world.get("serializedExtraItemFlags")
    if serial is None:
        return
    if not isinstance(serial, list):
        raise ValueError("Lighthouse Cove's extra-item flag snapshot is invalid.")
    for group in serial:
        if not isinstance(group, list):
            raise ValueError("Lighthouse Cove's extra-item flag snapshot is invalid.")
        for packed in group:
            if not _integer(packed) or not 0 <= packed <= 0xffffffff:
                raise ValueError("Lighthouse Cove's extra-item flag snapshot is invalid.")
            if int(packed) & 0xffff:
                raise ValueError("Specialized Lighthouse Cove plot and buildability flags are not restored.")


def _restored_cottage(item):
    return (isinstance(item, dict) and item.get("name") == "xcovecraftingcottage"
            and item.get("code") == "^2" and item.get("type") == "building"
            and item.get("className") == "CraftingCottageBuilding"
            and item.get("craftType") == "restaurant" and not item.get("features"))


def guard_snapshot(world):
    """Check a Cove snapshot before accepting travel or a farm operation."""
    if (not isinstance(world, dict) or world.get("tileSet") != WORLD
            or world.get("terrain") or world.get("sizeX") != world.get("sizeY")
            or not isinstance(world.get("objectsArray"), list)):
        raise ValueError("Lighthouse Cove requires its original ordinary-ground terrain.")
    maximum = plot_limit(world.get("sizeX"))
    _guard_serialized_plot_flags(world)
    count = 0
    special_counts = {}
    for obj in world["objectsArray"]:
        if not isinstance(obj, dict):
            raise ValueError("The Lighthouse Cove object snapshot is invalid.")
        class_name = obj.get("className")
        if class_name == "FishermansCoveBuilding":
            if obj.get("itemName") != "fishermanscove":
                raise ValueError("The Lighthouse Cove snapshot contains an unsupported Port.")
            import cove_port
            cove_port.guard_snapshot(obj)
        elif class_name == "CraftingCottageBuilding":
            if obj.get("itemName") != "xcovecraftingcottage":
                raise ValueError("The Lighthouse Cove snapshot contains an unsupported cottage.")
        elif class_name not in _BASIC_CLASSES | {"Plot"}:
            raise ValueError("The Lighthouse Cove snapshot contains an unsupported special object.")
        if class_name in ("FishermansCoveBuilding", "CraftingCottageBuilding"):
            special_counts[class_name] = special_counts.get(class_name, 0) + 1
            if special_counts[class_name] > 1:
                raise ValueError("Lighthouse Cove exceeds its recovered special-building limit.")
        if obj.get("className") == "Plot":
            if any(obj.get(flag) for flag in _SPECIAL_PLOT_FLAGS):
                raise ValueError("Specialized Lighthouse Cove plots are not restored.")
            count += 1
    if count > maximum:
        raise ValueError("Lighthouse Cove exceeds its recovered plot limit.")
    return count


def guard_plot_cap(save, action, snapshot):
    """Count every plot state and reject newly forged plots before charging."""
    if save["userInfo"].get("currentWorldType") != WORLD:
        return
    count = guard_snapshot(save["world"])
    if action not in ("plow", "place", "move"):
        return
    world = save["world"]
    existing = next((obj for obj in world["objectsArray"]
        if obj.get("id") == snapshot.get("id")
        or (snapshot.get("id") is not None and obj.get("tempId") == snapshot.get("id"))), None)
    if existing is not None and existing.get("className") == "Plot" and snapshot.get("className") != "Plot":
        raise ValueError("A Lighthouse Cove plot cannot change its object class.")
    if snapshot.get("className") != "Plot":
        if action == "plow":
            raise ValueError("Plowing must produce an ordinary Lighthouse Cove plot.")
        return
    if any(snapshot.get(flag) for flag in _SPECIAL_PLOT_FLAGS):
        raise ValueError("Specialized Lighthouse Cove plots are not restored.")
    if existing is not None and existing.get("className") != "Plot":
        raise ValueError("A Lighthouse Cove object cannot be replaced by a plot.")
    if existing is None:
        if action == "move":
            raise ValueError("Moving a Lighthouse Cove plot requires its saved object.")
        if count >= plot_limit(world["sizeX"]):
            raise ValueError("Lighthouse Cove has reached its recovered plot limit.")


def guard_special_item(item):
    """Admit basic items and only exact independently restored Cove features."""
    if _restored_cottage(item):
        return
    if isinstance(item, dict) and item.get("name") == "fishermanscove":
        import cove_port
        if cove_port.is_port(item):
            return
    if (not isinstance(item, dict) or item.get("type") not in _BASIC_TYPES
            or item.get("className") not in _BASIC_CLASSES
            or item.get("features")):
        raise ValueError("This Lighthouse Cove feature, crafting or special item is not restored.")


def guard_plow_snapshot(snapshot, existing):
    """Accept the original client's retained crop only on its saved fallow plot.

    Plot.executePlow retains itemName. Ordinary growth retains plantTime;
    the original Instant Grow/harvest path instead sends a cleared clock (0).
    Both are inert on a fallow plot; planting starts a new server-owned clock.
    A plowed retry retains the same fields too. This exception
    cannot create a crop-bearing plot or replace/move an existing crop.
    """
    if snapshot.get("className") != "Plot" or snapshot.get("state") != "plowed":
        raise ValueError("Plowing must produce an ordinary empty Lighthouse Cove plot.")
    if snapshot.get("itemName") is None:
        return
    if (existing is None or existing.get("className") != "Plot"
            or existing.get("state") not in ("fallow", "plowed")
            or any(snapshot.get(key) != existing.get(key)
                   for key in ("itemName", "position"))
            or not (snapshot.get("plantTime") == existing.get("plantTime")
                    or (type(snapshot.get("plantTime")) in (int, float)
                        and snapshot["plantTime"] == 0))):
        raise ValueError("Re-plowing must retain the saved Lighthouse Cove fallow plot.")


@lru_cache(maxsize=1)
def _land_terrain_names():
    terrain = _xml("gameSettings.xml.gz").find("terrains")
    if terrain is None:
        raise ValueError("The recovered terrain rules are unavailable.")
    primary = {e.get("code"): e.get("name") for e in terrain.findall("primaryTerrains/terrain")}
    if primary.get("0") != "default" or primary.get("1") != "land":
        raise ValueError("The recovered ground terrain is unavailable.")
    # TerrainUtil.getTerrainCode returns DEFAULT_TERRAIN_CODE (0) for YimfMap.
    # Include its ancestors: land -> default, then amphibious/plowable/all.
    names = {"default"}
    hierarchy = terrain.findall("terrainHierarchy/terrain")
    while True:
        parents = {e.get("name") for e in hierarchy
                   if any(child.get("name") in names for child in e.findall("terrain"))}
        if parents <= names:
            return frozenset(names)
        names.update(parents)


def guard_land_terrain(item):
    """Resolve original named terrain sets; Cove has no invented water map."""
    def nodes(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from nodes(child)
        elif isinstance(value, list):
            for child in value:
                yield from nodes(child)
    names = {e["name"] for e in nodes(item.get("terrainSet")) if "name" in e}
    if names and not names.intersection(_land_terrain_names()):
        raise ValueError("This item requires terrain unavailable in Lighthouse Cove.")
