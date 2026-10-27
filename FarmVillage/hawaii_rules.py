"""Dormant Hawaiian Paradise contracts recovered from the original archives.

All public functions are read-only. These checks cover individual rule slices;
they do not authorize a purchase, create terrain, unlock a farm/currency, grant
objects, or activate travel. Counts and experiments must come from the server.
"""
import copy
from functools import lru_cache
import hashlib
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zlib

import pyamf

from bundle import XML_DIR

WORLD = "hawaii"
CURRENCY = "coconuts"
STORAGE_ID = -11  # WorldManager.HAWAII_INVENTORY_ID, signed pushbyte 245.
_MAX_SAFE_INTEGER = 9_007_199_254_740_991
_SOURCE_HASHES = {
    "xml/gz/v855098/gameSettings.xml.gz": "c1fa55f130c4942ea978b07168b37285389d36e30fce30fc30647deff5e5e11b",
    "xml/gz/v855098/gameSettingsCMS.xml.gz": "2153a81311632e5697b6e10fb40be729bbd87ed1719554bc7fdf0ef8934fb43d",
    "xml/gz/v855098/worldSettings.xml.gz": "769db5f72b5586b036792332c9c9c89dac43ca6ae2fc6f5ddb761d829d1c014e",
    "xml/gz/v855098/yimf.xml.gz": "6a4756dcdc6f701628a51e2b1e1c6e26467735df5011c758b272241669af9065",
    "xml/gz/v855038/items_opt.amf": "14987fd4c07f9de35ff5092aeab58584802fd7fbeca1131ad1a5e3eee381a4d7",
    "embeds/Flash/v855097-855094/FarmGame.swf": "1edea7cbecefcb1e1233da207164942f0088a83b87afc9254850f5fcde5034ae",
}


def _whole(value, label):
    if (type(value) not in (int, float)
            or not 0 <= value <= _MAX_SAFE_INTEGER
            or (type(value) is float and not math.isfinite(value))
            or value != int(value)):
        raise ValueError(label + " must be a supported nonnegative whole number.")
    return int(value)


def _source(name):
    raw = (Path(XML_DIR).parent / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != _SOURCE_HASHES[name]:
        raise ValueError("Hawaiian Paradise's archived rules changed and require review.")
    return raw


def _xml(name):
    return ET.fromstring(zlib.decompress(_source("xml/gz/v855098/" + name + ".xml.gz")))


def _tree(node):
    return {"tag": node.tag, "attributes": dict(node.attrib),
            "children": [_tree(child) for child in node]}


def _list(value):
    return value if isinstance(value, list) else ([] if value is None else [value])


@lru_cache(maxsize=1)
def _archive():
    # The SWF pins the interpreted constants, currency layout and client parser
    # semantics documented in HAWAII_RULES.md; no SWF execution occurs here.
    _source("embeds/Flash/v855097-855094/FarmGame.swf")
    settings, cms, worlds, yimfs = (_xml(name) for name in
        ("gameSettings", "gameSettingsCMS", "worldSettings", "yimf"))
    expansion = settings.find("expansions/expansion[@name='hawaii']")
    currency = settings.find(".//currency[@name='coconuts']")
    definitions = []
    effective = {}
    for node in settings.findall("farmExpansions/world[@name='hawaii']/farmExpansionAddedItems/addedItems"):
        width = int(node.get("squares"))
        objects = [dict(item.attrib) for item in node]
        definitions.append({"width": width, "objects": objects})
        # FarmGameSettingsManager.getFarmExpansionData method3253 resets the
        # array for each squares key before pushing that row's objects.
        effective[width] = [{"code": obj["code"], "state": obj["state"],
            "position": {axis: int(obj[axis]) for axis in ("x", "y", "z")}}
            for obj in objects]
    limits = {int(node.get("squares")): {
        terrain.get("name"): int(terrain.get("plots"))
        for terrain in node.findall("terrains/terrain")}
        for node in expansion.findall("plotLimits/plotLimit")}
    mappings = {terrain.text.strip(): node.get("name")
        for node in expansion.findall("plotLimits/limitMapping/limitMap")
        for terrain in node.findall("terrains/terrain")}
    access_names = ("earlyAccess", "generalAccess", "allAccess")
    prerequisite_names = ("fv_xhi_shared", "fv_xhi_access_shared", "fv_xhi_early_access",
        "fv_xhi_general_access", "fv_xhi_all_access", "hawaiiParadiseXfer_visible")
    tuning = currency.find("inflow/tuningTest")
    theme = yimfs.find("yimf[@type='hawaii']")
    return {"worldType": WORLD, "currency": CURRENCY, "storageId": STORAGE_ID,
        "sourceHashes": dict(_SOURCE_HASHES), "minimumXP": int(
            settings.find("levels/level[@num='15']").get("requiredXP")),
        "farming": dict(expansion.find("farming").attrib),
        "access": {name: _tree(expansion.find(name)) for name in access_names},
        "prerequisites": {name: _tree(cms.find(".//prereq[@name='%s']" % name))
                          for name in prerequisite_names},
        "currencyRules": {"definition": _tree(currency),
            "inflowExperiment": tuning.get("experimentName"),
            "displayVariant": int(tuning.get("displayVariant")),
            "inflowMultipliers": {int(node.get("number")): node.get("multiplier") for node in tuning},
            "buffs": [node.text.strip() for node in currency.findall("buffs/buff")]},
        "plotLimits": limits, "plotGroupByTerrain": mappings,
        "primaryTerrains": {node.get("name"): int(node.get("code"))
            for node in settings.findall("terrains/primaryTerrains/terrain")},
        "terrainHierarchy": _tree(settings.find("terrains/terrainHierarchy")),
        "theme": {node.tag: (node.text or "").strip() for node in theme},
        "worldSettings": _tree(worlds.find("world[@name='hawaii']")),
        "shippingLicenseItemName": expansion.findtext("shippingLicenseItemName"),
        "expansionAddedDefinitions": definitions,
        "clientExpansionAddedObjects": effective,
        "startingFarm": None if expansion.find("startingFarm") is None
                        else _tree(expansion.find("startingFarm"))}


def recovered_rules():
    """Return independent original-source evidence, not a playable-world offer."""
    return copy.deepcopy(_archive())


def plot_limit(width, terrain):
    """Exact independent caps for default/land (ground) and water terrain."""
    width = _whole(width, "Hawaiian farm width")
    rules = _archive()
    if width not in rules["plotLimits"]:
        raise ValueError("That Hawaiian farm size has no recovered plot limit.")
    if not isinstance(terrain, str) or terrain not in rules["plotGroupByTerrain"]:
        raise ValueError("That terrain has no Hawaiian plot-limit mapping.")
    return rules["plotLimits"][width][rules["plotGroupByTerrain"][terrain]]


def guard_plot_counts(width, *, ground, water):
    """Check authoritative resulting counts; this never resolves a coastline."""
    for terrain, count in (("land", ground), ("water", water)):
        count = _whole(count, "Hawaiian " + terrain + " plot count")
        if count > plot_limit(width, terrain):
            raise ValueError("Hawaiian Paradise's " + terrain + " plot limit is exceeded.")


def guard_all_access(*, xp, experiments, already_unlocked):
    """Check the original timeless allAccess predicate only, without rewards."""
    xp = _whole(xp, "Player XP")
    if type(already_unlocked) is not bool:
        raise ValueError("The server must establish Hawaiian world ownership.")
    if already_unlocked:
        raise ValueError("Hawaiian Paradise has already been unlocked.")
    if xp < _archive()["minimumXP"]:
        raise ValueError("Hawaiian Paradise requires player level15.")
    if (not isinstance(experiments, dict) or any(
            type(experiments.get(name)) is not int or experiments[name] != 1
            for name in ("fv_hawaii", "fv_hawaii_for_all"))):
        raise ValueError("Hawaiian Paradise's original access experiments are required.")


def coconut_balance(save):
    """Read total, preserve earned/purchased metadata; missing stays locked.

    This bounded reader supports exact nonnegative JavaScript-safe integers.
    Unsupported imported values are preserved by rejecting, never coercing.
    """
    _archive()
    if not isinstance(save, dict) or not isinstance(save.get("userInfo", {}), dict):
        raise ValueError("The imported player currency state is invalid.")
    player = save.get("userInfo", {}).get("player", {})
    if not isinstance(player, dict):
        raise ValueError("The imported player currency state is invalid.")
    currencies = player.get("worldCurrencies")
    if currencies is None:
        return None
    if not isinstance(currencies, dict):
        raise ValueError("The imported world currency record is invalid.")
    if CURRENCY not in currencies:
        return None
    record = currencies[CURRENCY]
    if not isinstance(record, dict) or "total" not in record:
        raise ValueError("The imported coconut balance record is invalid.")
    return _whole(record["total"], "Imported coconut total")


def guard_coconut_affordability(save, amount):
    """Balance check only: no debit, grant, price choice or action approval."""
    amount = _whole(amount, "Coconut cost")
    balance = coconut_balance(save)
    if balance is None:
        raise ValueError("The imported coconut currency has not been unlocked.")
    if balance < amount:
        raise ValueError("There are not enough coconuts.")


@lru_cache(maxsize=1)
def _catalog():
    raw = _source("xml/gz/v855038/items_opt.amf")
    catalog = pyamf.get_decoder(pyamf.AMF3, zlib.decompress(raw)).readElement()
    by_name = {}
    grant_codes = {obj["code"] for row in _archive()["expansionAddedDefinitions"] for obj in row["objects"]}
    grant_codes.add("1uH")  # Original early-access seahorse_princess reward.
    for item in catalog["settings"]["items"]["item"]:
        requirement = item.get("requirements", {})
        world_gated = any(node.get("className") == "World" and node.get("name") == WORLD
                          for node in _list(requirement.get("requirement"))) if isinstance(requirement, dict) else False
        harvest = item.get("harvestYield", {})
        if (world_gated or item.get("market") == CURRENCY
                or isinstance(harvest, dict) and harvest.get("type") == CURRENCY
                or item.get("code") in grant_codes
                or item.get("name") in ("pkg_hawaiiXfer", "consume_hawaiiXfer")):
            by_name.setdefault(item["name"], item)
    return by_name


def item_rules(item_name):
    """Raw relevant catalog row, retaining every currency, terrain and gate."""
    if not isinstance(item_name, str) or item_name not in _catalog():
        raise ValueError("That item has no recovered Hawaiian catalog contract.")
    return copy.deepcopy(_catalog()[item_name])


def item_terrain_codes(item_name):
    """Original FarmItem.getTerrainSetCodes for the recovered land/water slice.

    Code1 is the original absent-terrainSet fallback. This reader does not infer
    terrain at any coordinate or certify a terrain map/placement operation.
    """
    item = item_rules(item_name)
    terrain_set = item.get("terrainSet")
    if terrain_set is None:
        return (1,)
    if terrain_set == {"terrain": {"name": "water"}}:
        return (_archive()["primaryTerrains"]["water"],)
    raise ValueError("That item's terrain set needs its own original-source review.")


def client_expansion_grants(width):
    """Exact client parser result; duplicate width keys use the last row.

    An absent row returns an empty list. This describes configured additions
    only; it does not synthesize an absent starter, terrain, grant or object ID.
    """
    plot_limit(width, "land")
    return copy.deepcopy(_archive()["clientExpansionAddedObjects"].get(int(width), []))


def land_rules(item_name):
    """Keep raw price/gates plus client saleCash and effective grant evidence."""
    if not isinstance(item_name, str) or not re.fullmatch(r"xhifarm\d+(?:_cash)?", item_name):
        raise ValueError("That Hawaiian land offer is unknown.")
    item = item_rules(item_name)
    if item.get("subtype") != "expand_farm":
        raise ValueError("That item is not a Hawaiian land offer.")
    width = int(item["squares"])
    return {"catalog": item, "width": width, "clientSaleCash": 1,
        "plotLimits": copy.deepcopy(_archive()["plotLimits"][width]),
        "addedDefinitionCount": sum(row["width"] == width
            for row in _archive()["expansionAddedDefinitions"]),
        "clientAddedObjects": client_expansion_grants(width)}


def guard_transaction(*_args, **_kwargs):
    raise ValueError("Hawaiian currency transactions, purchases, grants and travel are not restored.")
