"""Dormant Haunted Hollow terrain, plot and item policy; no world activation.

These are read-only preflights, not an unlock, starter, purchase, placement or
expansion service. Ordinary-ground support is conditional on an imported
snapshot actually lacking a terrain map. No original populated starter or
buildable-boundary map has been recovered. Unsupported imports are preserved.
"""
import copy
from functools import lru_cache
import hashlib
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import zlib

from bundle import XML_DIR
import hallow_rules

WORLD = "hallow"
THEME = "hallow_theme"
_MAX_INTEGER = 2_147_483_647
_SOURCE_HASHES = {
    "gameSettings.xml.gz": "c1fa55f130c4942ea978b07168b37285389d36e30fce30fc30647deff5e5e11b",
    "gameSettingsCMS.xml.gz": "2153a81311632e5697b6e10fb40be729bbd87ed1719554bc7fdf0ef8934fb43d",
    "yimf.xml.gz": "6a4756dcdc6f701628a51e2b1e1c6e26467735df5011c758b272241669af9065",
    "terrain.xml.gz": "521130a19bc9dd8b9e05f31db11ba51debf2e4bd48d076cd769d84506cea6318",
}
_BASIC_CLASSES = {
    "seed": frozenset((None,)),
    "animal": frozenset((None, "Animal")),
    "tree": frozenset((None, "Tree")),
    "building": frozenset((None, "Building")),
    "decoration": frozenset((None, "Decoration", "RotateableDecoration",
                              "MaskedDecoration", "GateDecoration")),
}
_DEFAULT_CLASSES = {"seed": "Plot", "animal": "Animal", "tree": "Tree",
                    "building": "Building", "decoration": "Decoration"}
_SPECIAL_PLOT_FLAGS = ("isJumbo", "isBigPlot", "isProduceItem", "isSuperPlot")


def _integer(value, label, *, minimum=1):
    if (type(value) not in (int, float) or not minimum <= value <= _MAX_INTEGER
            or (type(value) is float and not math.isfinite(value)) or value != int(value)):
        raise ValueError(label + " must be a supported whole number.")
    return int(value)


def _xml(name):
    raw = Path(XML_DIR, "gz/v855098", name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != _SOURCE_HASHES[name]:
        raise ValueError("Haunted Hollow's archived world rules changed and require review.")
    return ET.fromstring(zlib.decompress(raw))


@lru_cache(maxsize=1)
def _contract():
    settings, cms, yimfs, terrain = (_xml(name) for name in _SOURCE_HASHES)
    expansion = settings.find("expansions/expansion[@name='hallow']")
    if (expansion is None or expansion.attrib != {
            "name": WORLD, "score": "spook", "scoreFile": "worldScoreSpook.xml"}
            or any(expansion.find(name) is not None for name in
                   ("plotLimits", "worldRequirementOverride", "startingFarm"))):
        raise ValueError("Haunted Hollow's recovered world contract is unavailable.")
    farming = {e.get("key"): e.get("value") for e in cms.findall("farming/farmingEntry")}
    theme = yimfs.find("yimf[@type='hallow_theme']")
    theme_data = {e.tag: (e.text or "").strip() for e in theme}
    if (farming.get("maxNumObjects") != "5500" or theme_data != {
            "weights": "18,36,54,55,56,57,58,59", "bgColor": "0xFF626289",
            "outlineColor": "0x5d6088", "tileClass": "grass",
            "horizon": "assets/Environment/xhw_theme.swf",
            "backgroundPath": "assets/Environment/xhw_themeBackground_",
            "skyColor": "0xFF403A5B", "drawOutline": "true"}):
        raise ValueError("Haunted Hollow's recovered theme or object limit is unavailable.")
    primary = {e.get("code"): e.get("name") for e in
               settings.findall("terrains/primaryTerrains/terrain")}
    if (primary.get("0") != "default" or primary.get("1") != "land"
            or terrain.find("terrain[@code='0']").get("name") != "default"):
        raise ValueError("Haunted Hollow's recovered default terrain is unavailable.")
    # TerrainUtil9332 returns code0 for YimfMap. Expand named ancestors;
    # this says nothing about a supplied InvisibleTerrainMap's geometry.
    names = {"default"}
    hierarchy = settings.findall("terrains/terrainHierarchy/terrain")
    while True:
        parents = {e.get("name") for e in hierarchy
                   if any(child.get("name") in names for child in e)}
        if parents <= names:
            break
        names.update(parents)
    overrides = {e.get("name"): e.findtext("worldRequirementOverride") or e.get("name")
                 for e in settings.findall("expansions/expansion")}
    return {"theme": theme_data, "defaultMaxNumObjects": int(farming["maxNumObjects"]),
            "groundTerrainNames": frozenset(names), "worldRequirementOverrides": overrides}


def _item(item_name):
    # Reuse the existing once-decoded, hash-checked original AMF index. Never
    # use the market overlay or trust a client-supplied class/requirements dict.
    item = hallow_rules._archive()["items"].get(item_name) if isinstance(item_name, str) else None
    if item is None:
        raise ValueError("The original Haunted Hollow item is unknown.")
    return item


def recovered_rules():
    """Detached evidence, including explicitly unknown starter/geometry state."""
    data = _contract()
    return copy.deepcopy({"worldType": WORLD, "themeType": THEME, "theme": data["theme"],
        "sourceHashes": _SOURCE_HASHES, "catalogSourceHashes": hallow_rules.recovered_rules()["sourceHashes"],
        "worldRequirementType": WORLD, "worldSpecificPlotLimits": None,
        "defaultMaxNumObjects": data["defaultMaxNumObjects"],
        "savedMaxNumObjectsOverride": True, "groundTerrainCodeWithoutMap": 0,
        "groundTerrainNamesWithoutMap": sorted(data["groundTerrainNames"]),
        "originalStarterRecovered": False, "originalTerrainMapRecovered": False,
        "basicClasses": {kind: sorted(values, key=lambda value: value or "")
                         for kind, values in _BASIC_CLASSES.items()},
        "firstExpansionAdditions": expansion_added_objects(58)})


def plot_limit(world):
    """WorldManager2680: saved maxNumObjects, else CMS5500; no size table.

    Invalid explicit overrides are held for review rather than coerced or
    repaired. This helper does not certify physical room for that many plots.
    """
    default = _contract()["defaultMaxNumObjects"]
    if not isinstance(world, dict):
        raise ValueError("The imported Haunted Hollow world is invalid.")
    value = world.get("maxNumObjects")
    return default if value is None else _integer(value, "Imported object limit")


def guard_item_world(item_name, world_type=WORLD):
    """Evaluate original World alternatives; licenses/special predicates closed.

    This is an exclusivity check only. It never grants access or substitutes
    for XP, Spook, dates, experiments, quest, purchase or inventory guards.
    """
    data = _contract()
    item = _item(item_name)
    if not isinstance(world_type, str) or not world_type:
        raise ValueError("A world is required for the item exclusivity check.")
    groups = item.get("requirements", {})
    groups = groups if isinstance(groups, list) else [groups]
    compare, requirements = "all", []
    for group in groups:
        if not isinstance(group, dict) or set(group) - {"compare", "requirement"}:
            raise ValueError("That item's original requirements are not restored.")
        if "compare" in group:
            compare = group["compare"]
        children = group.get("requirement", [])
        requirements.extend(children if isinstance(children, list) else [children])
    if compare not in ("all", "any"):
        raise ValueError("That item's original requirement comparison is not restored.")
    if not requirements:
        return
    results, unsupported = [], False
    effective = data["worldRequirementOverrides"].get(world_type, world_type)
    for requirement in requirements:
        if (not isinstance(requirement, dict) or requirement.get("className") != "World"
                or set(requirement) - {"className", "name", "strict"}
                or requirement.get("strict", "false") not in ("true", "false")):
            results.append(False)
            unsupported = True
            continue
        wanted = requirement.get("name")
        results.append(wanted == world_type or
            (requirement.get("strict") != "true" and wanted == effective))
    if (any(results) if compare == "any" else all(results)):
        return
    if unsupported:
        raise ValueError("That item's license or special world requirements are not restored.")
    raise ValueError("This item requires another original world.")


def guard_land_terrain(item_name):
    """Only for a snapshot already verified to use the no-map Yimf branch."""
    terrains = _item(item_name).get("terrainSet")
    if terrains is None:
        return
    if not isinstance(terrains, dict) or set(terrains) != {"terrain"}:
        raise ValueError("That item's original terrain requirement is not restored.")
    rows = terrains["terrain"]
    rows = rows if isinstance(rows, list) else [rows]
    if (not rows or any(not isinstance(e, dict) or set(e) != {"name"}
                        for e in rows)):
        raise ValueError("That item's original terrain requirement is not restored.")
    if not any(e["name"] in _contract()["groundTerrainNames"] for e in rows):
        raise ValueError("This item requires terrain outside the supported Haunted Hollow ground.")


def guard_basic_item(item_name):
    """Bounded class support, not a claim that other original classes are optional."""
    item = _item(item_name)
    if (item.get("type") not in _BASIC_CLASSES
            or item.get("className") not in _BASIC_CLASSES.get(item.get("type"), ())
            or any(item.get(key) for key in ("features", "storageType", "construction",
                                             "crafting", "produceItem", *_SPECIAL_PLOT_FLAGS))):
        raise ValueError("This Haunted Hollow special item or building is not restored.")


def _recovered_plans(width):
    """Every recovered mandatory plan for a size no larger than width."""
    return [plan for planned_width in sorted(hallow_rules._archive()["added"])
            if planned_width <= width for plan in hallow_rules._expansion_plans(planned_width)]


def _exact_expansion_plan(obj, plans):
    """Recovered plan this object equals exactly.

    Equality is over the full persisted dict (exact keys, types and values), so
    extra, missing or altered fields never match.
    """
    object_id = obj.get("id")
    if type(object_id) is not int or not isinstance(obj.get("itemName"), str):
        return None
    for plan in plans:
        if obj == hallow_rules._persisted_object(object_id, plan):
            return plan
    return None


def guard_snapshot(world):
    """Read-only preflight for the bounded ordinary snapshot branch.

    Supplied terrain, unknown sizes/themes and special systems stay preserved
    but unavailable. Only exact recovered expansion objects (same full persisted
    shape, at their recovered next-width coordinates, not overlapping each other)
    are admitted among the otherwise restricted treasure and aviary classes. A
    successful check is not evidence of original shoreline, scenery collision or
    a recovered populated starter.
    """
    if (not isinstance(world, dict) or world.get("tileSet") != THEME
            or world.get("terrain") is not None
            or not isinstance(world.get("objectsArray"), list)):
        raise ValueError("Haunted Hollow's imported theme or terrain map is not supported.")
    width = _integer(world.get("sizeX"), "Imported farm width")
    height = _integer(world.get("sizeY"), "Imported farm height")
    widths = {int(item["squares"]) for item in hallow_rules._archive()["land"].values()}
    if width != height or width not in widths:
        raise ValueError("That Haunted Hollow size needs an original snapshot audit.")
    count = 0
    admitted = []
    plans = _recovered_plans(width)
    for obj in world["objectsArray"]:
        if not isinstance(obj, dict):
            raise ValueError("The imported Haunted Hollow object is invalid.")
        plan = _exact_expansion_plan(obj, plans)
        if plan is not None:
            rect = (obj["position"]["x"], obj["position"]["y"], plan["sizeX"], plan["sizeY"])
            if any(hallow_rules._overlaps(rect, other) for other in admitted):
                raise ValueError("Haunted Hollow's mandatory expansion objects overlap; "
                                 "the original placement is not restored.")
            admitted.append(rect)
            continue
        if obj.get("className") == "Plot":
            if any(obj.get(flag) for flag in _SPECIAL_PLOT_FLAGS):
                raise ValueError("Specialized Haunted Hollow plots are not restored.")
            count += 1
            if obj.get("itemName") is None:
                continue
            item = _item(obj["itemName"])
            if item.get("type") != "seed":
                raise ValueError("An ordinary Haunted Hollow plot requires a crop.")
        else:
            item = _item(obj.get("itemName"))
            expected = item.get("className") or _DEFAULT_CLASSES.get(item.get("type"))
            if obj.get("className") != expected:
                raise ValueError("The imported Haunted Hollow object class disagrees with its catalog item.")
        guard_basic_item(item["name"])
        guard_item_world(item["name"])
        guard_land_terrain(item["name"])
    if count > plot_limit(world):
        raise ValueError("Haunted Hollow exceeds its recovered plot limit.")
    return count


def guard_plot_transition(world, action, snapshot):
    """Preflight plot count/identity; authoritative action services own mutation."""
    count = guard_snapshot(world)
    if action not in ("plow", "place", "move") or not isinstance(snapshot, dict):
        raise ValueError("That Haunted Hollow plot transition is not supported.")
    identifier = snapshot.get("id")
    existing = next((obj for obj in world["objectsArray"] if identifier is not None
                     and (obj.get("id") == identifier or obj.get("tempId") == identifier)), None)
    if existing is not None and (existing.get("className") == "Plot") != (snapshot.get("className") == "Plot"):
        raise ValueError("A Haunted Hollow plot cannot replace or become another object class.")
    if snapshot.get("className") != "Plot":
        if action == "plow":
            raise ValueError("Plowing requires an ordinary Haunted Hollow plot.")
        return
    if any(snapshot.get(flag) for flag in _SPECIAL_PLOT_FLAGS):
        raise ValueError("Specialized Haunted Hollow plots are not restored.")
    if existing is None:
        if action == "move":
            raise ValueError("Moving a Haunted Hollow plot requires its saved object.")
        if count >= plot_limit(world):
            raise ValueError("Haunted Hollow has reached its recovered plot limit.")


def expansion_added_objects(width):
    """Exact archived plans, not grants or proof of a complete expansion service.

    Coordinates are raw config coordinates. No guessed expansion transform,
    initial aviary contents, construction progress or completion reward.
    """
    width = _integer(width, "Expansion width")
    archive = hallow_rules._archive()
    if width not in {int(item["squares"]) for item in archive["land"].values()}:
        raise ValueError("That Haunted Hollow expansion size is unknown.")
    result = []
    for node in archive["added"].get(width, []):
        item = archive["codes"].get(node["code"])
        if item is None or item.get("className") not in (
                "FixedTreasureConstructionBuilding", "FeatureBuilding"):
            raise ValueError("The mandatory Haunted Hollow expansion objects need review.")
        result.append({**node, "itemName": item["name"], "className": item["className"],
            "sizeX": int(item["sizeX"]), "sizeY": int(item["sizeY"]),
            "buildingName": item["buildingName"],
            "itemRules": {key: item[key] for key in ("buyable", "capacity",
                "initialExpansionLevel", "contentItemClassName", "defaultItem",
                "matsNeeded", "finishedReward", "storageType", "experimentGate") if key in item},
            "restored": False})
    return copy.deepcopy(result)
