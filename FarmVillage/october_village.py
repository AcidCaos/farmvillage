"""An authored October starter for a newly created Home village.

This module has no game imports, filesystem access, or persistence side effects.
The only caller is player.new_village, before migration, registry publication or
the first save. It is deliberately not an editor for existing/imported farms.
Original Maple access, sections, production and Innovation rules stay dormant.
"""
from __future__ import annotations

import copy
import math


PRESET = "quintessential_october"
DISPLAY_NAME = "Quintessential October"
DESCRIPTION = "Quintessential October brings an autumn landscape, maple groves and pumpkin paths, with room to farm."
AVAILABLE = True  # Original autumn surroundings and wood HUD verified in the client.
STATE_KEY = "_quintessentialOctober"
VERSION = 2
THEME = "autumngrass_theme"
CATALOG_SOURCE = "xml/gz/v855038/items_opt.amf"
CATALOG_SHA256 = "14987fd4c07f9de35ff5092aeab58584802fd7fbeca1131ad1a5e3eee381a4d7"

# Each record pins the original catalog identity, footprint, class and renderer
# asset. The layout and these cross-world starter grants are authored choices,
# not a reconstruction of an original Amsterdam, Spook O Ween or Maple map.
def _decoration(code, donor, width, height, *, rotate=True, image=None):
    return {"code": code, "donorWorld": donor,
            "type": "decoration",
            "className": "RotateableDecoration" if rotate else "Decoration",
            "footprint": (width, height), "sourceTerrain": None,
            **({"image": image} if image else {})}


def _tree(code, donor, name):
    return {"code": code, "donorWorld": donor, "type": "tree", "className": "Tree",
            "footprint": (1, 1), "sourceTerrain": None, "growTime": 2, "coinYield": 150,
            "image": ("mature", "assets/trees/" + name + ".swf"),
            "bareImage": ("bare", "assets/trees/" + name + ".swf")}


PALETTE = {
    "giantmapleshadetree": _tree("lfm", "farm", "giantmapleshadetree"),
    "giantxcd_goldenmapletree": _tree("2nop", "canada", "giantxcd_goldenmapletree"),
    "autumnshadetree": _tree("ppl", "farm", "autumnshadetree"),
    "xdm_luxurygardengazebo": _decoration("2myo", "amsterdam", 6, 6),
    "xdm_dutchstatuefountain": _decoration("2n4b", "amsterdam", 4, 4, rotate=False),
    "autumntreeswing": _decoration("0yqd", "farm", 3, 4),
    "pumpkinpatch": _decoration("069i", "farm", 2, 2),
    "pumpkinstack": _decoration("2d84", "spooky", 2, 2),
    "jackolanterns": _decoration("X5", "spooky", 2, 2, rotate=False,
        image=("static", "assets/decorations/spooky_jackolanterns.swf")),
    "autumnleafcandle": _decoration("1jzu", "farm", 2, 2, rotate=False),
    "autumnfence": _decoration("0jfg", "farm", 5, 1),
    "xcd_autumnleaveslamp": _decoration("2o3m", "canada", 1, 1, rotate=False),
    "xhf_hauntedlantern": _decoration("2dwk", "spooky", 2, 2, rotate=False),
}
for _name, _record in PALETTE.items():
    _record.setdefault("image", ("horizontal" if _record["className"] == "RotateableDecoration" else "static",
                                  "assets/decorations/" + _name + ".swf"))

# Dense red/gold groves are the main scene. Their genuine original tree art has
# ordinary brown trunks, unlike the magical blue-trunk Canadian Maple variant.
# Catalog footprints remain disjoint; the wider spacing permits large canopies.
# Water-only assets, mastery signs and special production classes are excluded.
LAYOUT = (
    ("giantmapleshadetree", 2, 2, "western-maple-wood"),
    ("giantxcd_goldenmapletree", 8, 2, "western-maple-wood"),
    ("autumnshadetree", 12, 5, "western-maple-wood"),
    ("giantmapleshadetree", 3, 9, "western-maple-wood"),
    ("giantxcd_goldenmapletree", 9, 10, "western-maple-wood"),
    ("giantmapleshadetree", 2, 16, "western-maple-wood"),
    ("giantxcd_goldenmapletree", 8, 17, "western-maple-wood"),
    ("autumnshadetree", 12, 21, "western-maple-wood"),
    ("giantmapleshadetree", 2, 24, "western-maple-wood"),
    ("giantxcd_goldenmapletree", 8, 25, "western-maple-wood"),
    ("giantmapleshadetree", 2, 31, "western-maple-wood"),
    ("giantxcd_goldenmapletree", 9, 33, "western-maple-wood"),
    ("giantmapleshadetree", 3, 40, "western-maple-wood"),
    ("giantxcd_goldenmapletree", 10, 42, "western-maple-wood"),
    ("giantmapleshadetree", 40, 2, "eastern-maple-wood"),
    ("giantxcd_goldenmapletree", 47, 3, "eastern-maple-wood"),
    ("giantmapleshadetree", 41, 9, "eastern-maple-wood"),
    ("giantxcd_goldenmapletree", 47, 11, "eastern-maple-wood"),
    ("autumnshadetree", 40, 16, "eastern-maple-wood"),
    ("giantmapleshadetree", 47, 18, "eastern-maple-wood"),
    ("giantxcd_goldenmapletree", 40, 24, "eastern-maple-wood"),
    ("giantmapleshadetree", 47, 26, "eastern-maple-wood"),
    ("giantxcd_goldenmapletree", 40, 31, "eastern-maple-wood"),
    ("autumnshadetree", 47, 34, "eastern-maple-wood"),
    ("giantmapleshadetree", 40, 41, "eastern-maple-wood"),
    ("giantxcd_goldenmapletree", 47, 43, "eastern-maple-wood"),
    ("giantmapleshadetree", 18, 40, "southern-maple-clearing"),
    ("giantmapleshadetree", 28, 43, "southern-maple-clearing"),
    ("xdm_luxurygardengazebo", 17, 27, "woodland-courtyard"),
    ("xdm_dutchstatuefountain", 27, 36, "woodland-courtyard"),
    ("autumntreeswing", 6, 35, "western-maple-wood"),
    ("autumntreeswing", 41, 36, "eastern-maple-wood"),
    ("pumpkinpatch", 4, 4, "pumpkin-trail"),
    ("pumpkinpatch", 10, 12, "pumpkin-trail"),
    ("pumpkinpatch", 3, 27, "pumpkin-trail"),
    ("pumpkinpatch", 43, 5, "pumpkin-trail"),
    ("pumpkinpatch", 43, 20, "pumpkin-trail"),
    ("pumpkinpatch", 42, 44, "pumpkin-trail"),
    ("pumpkinstack", 10, 28, "pumpkin-trail"),
    ("pumpkinstack", 38, 12, "pumpkin-trail"),
    ("pumpkinstack", 19, 44, "pumpkin-trail"),
    ("pumpkinstack", 32, 37, "pumpkin-trail"),
    ("jackolanterns", 11, 7, "lantern-trail"),
    ("jackolanterns", 11, 18, "lantern-trail"),
    ("jackolanterns", 38, 27, "lantern-trail"),
    ("jackolanterns", 32, 44, "lantern-trail"),
    ("autumnleafcandle", 18, 36, "lantern-trail"),
    ("autumnleafcandle", 34, 36, "lantern-trail"),
    ("xcd_autumnleaveslamp", 13, 12, "lantern-trail"),
    ("xcd_autumnleaveslamp", 38, 33, "lantern-trail"),
    ("xhf_hauntedlantern", 6, 20, "lantern-trail"),
    ("xhf_hauntedlantern", 44, 29, "lantern-trail"),
    ("autumnfence", 3, 45, "woodland-edge"),
    ("autumnfence", 40, 46, "woodland-edge"),
)

FARMING_AREA = {"x": 16, "y": 0, "sizeX": 20, "sizeY": 24}
WALKWAYS = ((14, 0, 2, 50), (36, 0, 2, 50), (14, 33, 24, 2))
_STARTER = (
    (1, "StorageBuilding", "barn", 25, 25, "built"),
    (2, "Plot", None, 27, 13, "fallow"),
    (3, "Plot", None, 27, 9, "fallow"),
    (4, "Plot", "eggplant", 19, 9, "grown"),
    (5, "Plot", "eggplant", 19, 13, "grown"),
    (6, "Plot", None, 23, 9, "plowed"),
    (7, "Plot", None, 23, 13, "plowed"),
)
_CLASSES = {"decoration": frozenset((None, "Decoration", "RotateableDecoration")),
            "tree": frozenset((None, "Tree"))}
_FEATURE_FIELDS = ("features", "construction", "storageType", "crafting",
                   "produceItem", "action", "harvestEvent", "terrainSet", "requirements")


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _fresh_starter(save):
    """Fail closed unless this is the detached, pre-migration new template.

    Freshness of provenance is enforced by the sole new_village caller. These
    structural checks additionally prevent accidental use on ordinary loaded
    saves, another world, changed starter objects, or an already authored farm.
    """
    error = "The October preset can only be used while creating a new village."
    if not isinstance(save, dict) or save.get("version") is not None or STATE_KEY in save:
        raise ValueError(error)
    if "_ownedWorldTravel" in save:
        raise ValueError(error)
    user, world = save.get("userInfo"), save.get("world")
    if not isinstance(user, dict) or not isinstance(world, dict):
        raise ValueError(error)
    if (user.get("currentWorldType") != "farm" or user.get("is_new") is not True
            or user.get("firstDay") is not True or world.get("id") != 1
            or world.get("sizeX") != 50 or world.get("sizeY") != 50
            or world.get("tileSet") not in (None, "grass_theme")):
        raise ValueError(error)
    player = user.get("player")
    summaries = user.get("worldSummaryData")
    if (not isinstance(player, dict) or not isinstance(player.get("userId"), str)
            or not player["userId"] or not isinstance(world.get("uid"), str)
            or not world["uid"] or not isinstance(summaries, dict)
            or set(summaries) != {"farm"} or not isinstance(summaries["farm"], dict)):
        raise ValueError(error)
    stamp = user.get("firstDayTimestamp")
    summary = summaries["farm"]
    if (not _number(stamp) or stamp <= 0 or summary.get("storageId") != -2
            or summary.get("firstLoaded") != stamp or summary.get("lastLoaded") != stamp):
        raise ValueError(error)
    objects = world.get("objectsArray")
    if not isinstance(objects, list) or len(objects) != len(_STARTER):
        raise ValueError(error)
    for obj, expected in zip(objects, _STARTER):
        if not isinstance(obj, dict) or not isinstance(obj.get("position"), dict):
            raise ValueError(error)
        position = obj["position"]
        actual = (obj.get("id"), obj.get("className"), obj.get("itemName"),
                  position.get("x"), position.get("y"), obj.get("state"))
        if actual != expected or obj.get("deleted") is True or position.get("z", 0) != 0:
            raise ValueError(error)
    return objects


def _dimension(item, key):
    value = item.get(key)
    if isinstance(value, str) and value.isdecimal():
        value = int(value)
    if type(value) is not int or not 1 <= value <= 50:
        raise ValueError("An October catalog footprint is unavailable.")
    return value


def _images(item):
    values = item.get("image", [])
    if isinstance(values, dict):
        values = [values]
    if not isinstance(values, list):
        return ()
    return tuple((value.get("name"), value.get("url"))
                 for value in values if isinstance(value, dict))


def _palette_item(name, catalog_lookup):
    expected = PALETTE[name]
    item = catalog_lookup(name)
    if (not isinstance(item, dict) or item.get("name") != name
            or item.get("code") != expected["code"]
            or item.get("type") != expected["type"]
            or item.get("className") not in _CLASSES[expected["type"]]
            or (item.get("className") or ("Tree" if expected["type"] == "tree" else "Decoration")) != expected["className"]
            or item.get("placeable") not in (True, "true")
            or any(item.get(field) for field in _FEATURE_FIELDS)
            or (_dimension(item, "sizeX"), _dimension(item, "sizeY")) != expected["footprint"]
            or expected["image"] not in _images(item)):
        raise ValueError("An original October item is unavailable: " + name)
    if expected["type"] == "tree":
        if (item.get("growTime") not in (2, "2") or item.get("coinYield") not in (150, "150")
                or expected["bareImage"] not in _images(item)):
            raise ValueError("An October tree's original growth or yield is unavailable: " + name)
    elif item.get("growTime"):
        raise ValueError("An October decoration cannot acquire a production timer: " + name)
    return item


def _overlaps(first, second):
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def apply_new_preset(save, *, catalog_lookup, growth_seconds=None):
    """Return a decorated deep copy; preserve the input even on any failure.

    No money, XP, inventory, starter timer, player identity or existing object
    is changed. Added trees and decorations are part of the authored starter;
    they are not recorded as original quests, purchases or Maple rewards. New
    ripe trees use the original runtime growth conversion, supplied by the
    caller, just like the base template's original ripe eggplants.
    """
    original_objects = _fresh_starter(save)
    if not callable(catalog_lookup):
        raise ValueError("The original decoration catalog is required.")
    palette = {name: _palette_item(name, catalog_lookup) for name in PALETTE}
    if not palette or not LAYOUT:
        raise ValueError("The authored October starter is unavailable.")
    tree_durations = {}
    for name, item in palette.items():
        if PALETTE[name]["type"] != "tree":
            continue
        if not callable(growth_seconds):
            raise ValueError("The original runtime tree growth conversion is required.")
        duration = growth_seconds(item)
        if (not _number(duration) or duration <= 0
                or duration >= save["userInfo"]["firstDayTimestamp"]):
            raise ValueError("The original runtime tree growth duration is invalid.")
        tree_durations[name] = duration
    occupied = []
    for obj in original_objects:
        position = obj["position"]
        item = catalog_lookup(obj["itemName"]) if obj.get("itemName") else None
        if obj["className"] == "Plot":
            width = height = 4
        elif isinstance(item, dict):
            width, height = _dimension(item, "sizeX"), _dimension(item, "sizeY")
        else:
            raise ValueError("The original starter building footprint is unavailable.")
        occupied.append((position["x"], position["y"], width, height))
    farming = (FARMING_AREA["x"], FARMING_AREA["y"],
               FARMING_AREA["sizeX"], FARMING_AREA["sizeY"])
    # Positive storage ledgers can reserve object IDs even without a visible
    # object. Never give one of those IDs to an added decoration.
    reserved = [obj["id"] for obj in original_objects]
    storage = save["userInfo"]["player"].get("storageData")
    if not isinstance(storage, dict):
        raise ValueError("The new village inventory is invalid.")
    for key in storage:
        try:
            value = int(key)
        except (TypeError, ValueError):
            continue
        if value > 0:
            reserved.append(value)
    next_id = max(reserved, default=0) + 1
    additions, provenance = [], []
    for name, x, y, region in LAYOUT:
        record = PALETTE[name]
        width, height = record["footprint"]
        rectangle = (x, y, width, height)
        if (type(x) is not int or type(y) is not int or x < 0 or y < 0
                or x + width > 50 or y + height > 50
                or _overlaps(rectangle, farming)
                or any(_overlaps(rectangle, walkway) for walkway in WALKWAYS)
                or any(_overlaps(rectangle, other) for other in occupied)):
            raise ValueError("The authored October layout has an overlapping or out-of-bounds object.")
        if 63000 <= next_id <= 65500:
            next_id = 65501
        if next_id > 2_147_483_647:
            raise ValueError("The new village has no available decoration IDs.")
        added = {"id": next_id, "className": record["className"],
            "itemName": name, "position": {"x": x, "y": y, "z": 0},
            "state": "ripe" if record["type"] == "tree" else record["image"][0],
            "direction": 0, "deleted": False, "components": {}, "instanceDataStoreKey": None}
        if record["type"] == "tree":
            added["plantTime"] = math.floor((save["userInfo"]["firstDayTimestamp"] - tree_durations[name]) * 1000)
        additions.append(added)
        origin = {"objectId": next_id, "itemName": name,
            "itemCode": record["code"], "donorWorld": record["donorWorld"],
            "donorEvidence": "original catalog identity and images; thematic grouping is authored",
            "originalType": record["type"],
            "region": region, "assetStatus": "borrowed", "placementStatus": "authored",
            "originalTerrain": record["sourceTerrain"],
            "starterGrantStatus": "authored; original purchase requirements are not a starter unlock",
            "footprint": {"sizeX": width, "sizeY": height},
            "image": {"name": record["image"][0], "url": record["image"][1]}}
        if record["type"] == "tree":
            origin.update(originalGrowDays=record["growTime"], originalCoinYield=record["coinYield"],
                          normalGrowthSeconds=tree_durations[name], initialState="authored ripe starter")
        provenance.append(origin)
        occupied.append(rectangle)
        next_id += 1
    result = copy.deepcopy(save)
    result["world"]["tileSet"] = THEME
    result["world"]["objectsArray"].extend(additions)
    result[STATE_KEY] = {"version": VERSION, "preset": PRESET,
        "compositionStatus": "authored", "originalMapRestored": False,
        "originalMapleMechanicsActivated": False,
        "catalogSource": {"path": CATALOG_SOURCE, "sha256": CATALOG_SHA256},
        "theme": {"tileSet": THEME,
            "status": "borrowed original autumn ground, horizon and surroundings",
            "hudArtwork": "borrowed original England wood controls"},
        "farmingArea": copy.deepcopy(FARMING_AREA), "walkways": [list(row) for row in WALKWAYS],
        "objects": provenance}
    return result
