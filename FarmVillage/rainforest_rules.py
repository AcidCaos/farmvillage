"""Checked Fields of El Dorado artifact and land-recovery contracts.

This is an evidence/admission module, not another construction engine.  The
existing finite engine does not manage FixedTreasureConstructionBuilding: its
server-selected finishedName/gift response is absent from the archive.  Land
that must add those objects stays closed before any charge.  In particular,
the catalog's finishedReward material is not a recovered completion loot pool.
"""
import copy
from functools import lru_cache
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET
import zlib

from bundle import XML_DIR
import construction
import items

WORLD = "rainforest"
ARTIFACT_CLASS = "FixedTreasureConstructionBuilding"
ARTIFACTS = {
    "xrf_treasure_s": ("WTB", 2, "part_minimattock", 10),
    "xrf_treasure_m": ("Zp5", 3, "part_minimattock", 22),
    "xrf_treasure_l": ("XDh", 4, "part_handbrush", 28),
    "xrf_treasure_xl": ("VyY", 5, "part_handbrush", 42),
}
_COIN_COSTS = (10000, 25000, 50000, 75000, 1000000, 1500000, 2000000,
               3000000, 4500000, 5000000, 5500000, 6000000, 12000000,
               15000000, 18000000, 20000000, 22000000, 24000000, 26000000)
_CATALOG_CASH = (20, 30, 40, 60, 80, 100, 120, 150, 180, 200, 220, 250,
                 280, 300, 320, 350, 360, 370, 380)
_ADDED_COUNTS = (3, 5, 4, 4, 4, 4, 3, 3, 2, 3, 1, 1)
GROWTH_BLOCKER = ("Rainforest land growth requires its mandatory artifacts' genuine "
    "completion reward/transform response and durable construction-state contract; "
    "these are not recovered.")
ARTIFACT_BLOCKER = ("Rainforest artifact clearing requires the genuine completion "
    "reward/transform response; the material requirement is not a reward table.")


@lru_cache(maxsize=1)
def _archive():
    if getattr(items, "_cached_items", None) is None:
        items.load_items()
    settings_path = Path(XML_DIR, "gz/v855098/gameSettings.xml.gz")
    settings = ET.fromstring(zlib.decompress(settings_path.read_bytes()))
    artifact_rules = {}
    for name, (code, size, part, count) in ARTIFACTS.items():
        item = items.get_item_by_name(name)
        expected = {"name": name, "code": code, "className": ARTIFACT_CLASS,
            "type": "building", "sizeX": str(size), "sizeY": str(size),
            "matsNeeded": str(count), "finishedReward": part,
            "storageType": {"itemClass": name}, "buyable": "false",
            "placeable": "true", "experimentGate": "fv_rainforest"}
        config = construction._storage_config().get(name)
        if (not item or any(item.get(k) != value for k, value in expected.items())
                or item.get("finishedName") or item.get("growTime")
                or config != {"name": name, "itemName": {"part": "true",
                    "need": str(count), "value": part}, "metadata": {
                    "type": "indexed", "storableValue": {
                        "type": "int", "name": "amount", "index": "0"}}}):
            raise ValueError("The rainforest artifact contract needs a new source audit.")
        artifact_rules[name] = {"name": name, "code": code, "className": ARTIFACT_CLASS,
            "sizeX": size, "sizeY": size, "material": part, "materialCount": count,
            "authoredStates": ["construct_0", "construct_1", "construct_2"],
            "completionItem": None, "completionGift": None, "clockSeconds": None,
            "status": "RECOVERY_BLOCKED"}
    additions = {}
    node = settings.find("farmExpansions/world[@name='rainforest']/farmExpansionAddedItems")
    if node is None:
        raise ValueError("The rainforest mandatory expansion additions are unavailable.")
    code_to_name = {value[0]: name for name, value in ARTIFACTS.items()}
    for group in node.findall("addedItems"):
        width = int(group.get("squares"))
        plans = []
        for row in group.findall("addedItem"):
            if (set(row.attrib) != {"code", "x", "y", "z", "state"}
                    or row.get("code") not in code_to_name or row.get("z") != "0"
                    or row.get("state") != "construct_0"):
                raise ValueError("A mandatory rainforest artifact needs a new source audit.")
            name = code_to_name[row.get("code")]
            plan = {"itemName": name, "className": ARTIFACT_CLASS,
                    "position": {key: int(row.get(key)) for key in ("x", "y", "z")},
                    "state": row.get("state"), "sizeX": artifact_rules[name]["sizeX"],
                    "sizeY": artifact_rules[name]["sizeY"]}
            if any(plan["position"][axis] < 0 or
                   plan["position"][axis] + plan[dimension] > width
                   for axis, dimension in (("x", "sizeX"), ("y", "sizeY"))):
                raise ValueError("A mandatory rainforest artifact falls outside its authored width.")
            plans.append(plan)
        additions[width] = plans
    if (tuple(sorted(additions)) != tuple(range(58, 147, 8)) or
            tuple(len(additions[w]) for w in sorted(additions)) != _ADDED_COUNTS):
        raise ValueError("The rainforest expansion-added artifact ladder changed.")
    offers = {}
    for index, (coin_cost, raw_cash) in enumerate(zip(_COIN_COSTS, _CATALOG_CASH)):
        tier = 14 + index * 2
        width = 58 + index * 8
        for suffix, currency, raw_cost in (("", "coins", coin_cost), ("_cash", "cash", raw_cash)):
            name = f"xrffarm{tier}{suffix}"
            item = items.get_item_by_name(name)
            if (not item or item.get("squares") != str(width)
                    or item.get("market") != currency
                    or item.get("cost" if currency == "coins" else "cash") != str(raw_cost)
                    or item.get("requiredLevel") != "1" or item.get("minNeighbors") is not None):
                raise ValueError("The rainforest land prices need a new source audit.")
            offers[name] = {"name": name, "width": width, "currency": currency,
                "catalogAmount": raw_cost, "transactionAmount": coin_cost if currency == "coins" else 1,
                "minimumLevel": 1, "minimumNeighbors": 0,
                "experimentGate": item.get("experimentGate"),
                "mandatoryAdditions": len(additions.get(width, []))}
    return {"worldType": WORLD, "artifacts": artifact_rules, "landOffers": offers,
            "expansionAdditions": additions, "growthStatus": "RECOVERY_BLOCKED",
            "growthBlocker": GROWTH_BLOCKER,
            "sourceSHA256": {str(path.relative_to(XML_DIR)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (settings_path, Path(items.ITEMS_AMF),
                             Path(XML_DIR, "gz/v855098/storageConfig.amf.gz"))}}


def recovered_growth_contract():
    """Return independent checked costs/materials/additions without authorizing growth."""
    return copy.deepcopy(_archive())


def guard_land_growth(item):
    """Refuse a rainforest expansion before charging or enlarging the farm."""
    name = item.get("name") if isinstance(item, dict) else item
    if name not in _archive()["landOffers"]:
        raise ValueError("That item is not a recovered rainforest land expansion.")
    raise ValueError(GROWTH_BLOCKER)


def guard_artifact_action(item_name):
    """Keep imported artifacts intact until their server result is recovered."""
    if item_name not in _archive()["artifacts"]:
        raise ValueError("That item is not a recovered rainforest artifact.")
    raise ValueError(ARTIFACT_BLOCKER)
