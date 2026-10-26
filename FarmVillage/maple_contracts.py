"""Dormant, read-only Maple Frontier archive contracts.

No dispatch registration, activation, farm creation or save mutation lives here.
Preflight checks describe supplied facts; they never authorize or acknowledge a
transaction. Missing starter/terrain/location tables still block original play.
"""
import copy
from datetime import datetime
from functools import lru_cache
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET
import zlib

ROOT = Path(__file__).resolve().parent
WORKSHOP_CRAFT = "xcdcrafttype"
WORKSHOP_ITEM = "xcd_craftingcottage"
WORKSHOP_CODE = "2o9n"
UPGRADE_CODES = frozenset(("2nnz", "2nj7"))


def _integer(value, label, minimum=0, maximum=2_147_483_647):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer from {minimum} to {maximum}.")
    return value


def _xml(name):
    return ET.fromstring(zlib.decompress((ROOT / "xml/gz/v855098" / name).read_bytes()))


def _node(element):
    if element is None:
        return None
    result = {"tag": element.tag, "attributes": dict(element.attrib)}
    if element.text and element.text.strip():
        result["text"] = element.text.strip()
    if len(element):
        result["children"] = [_node(child) for child in element]
    return result


@lru_cache(maxsize=1)
def _catalog():
    # Decode the complete original catalog, not the explicit-World subset: Lodge,
    # token, Hillside Stable and museum records omit that World requirement.
    import pyamf
    raw = zlib.decompress((ROOT / "xml/gz/v855038/items_opt.amf").read_bytes())
    catalog = pyamf.get_decoder(pyamf.AMF3, raw).readElement()["settings"]["items"]["item"]
    codes, duplicates = {}, []
    for item in catalog:
        if item["code"] in codes:
            duplicates.append({"code": item["code"], "identical": item == codes[item["code"]],
                               "firstName": codes[item["code"]]["name"], "nextName": item["name"]})
        codes.setdefault(item["code"], item)
    return codes, duplicates, len(catalog)


@lru_cache(maxsize=1)
def _sources():
    codes, duplicates, _ = _catalog()
    crafting = _xml("crafting.xml.gz")
    recipes = {}
    for recipe in crafting.find("recipes"):
        if recipe.findtext("craft") != WORKSHOP_CRAFT:
            continue
        code = recipe.get("id")
        if code in recipes and ET.tostring(recipe) != ET.tostring(recipes[code]):
            raise ValueError("Conflicting original Maple recipe identities require review.")
        recipes.setdefault(code, recipe)
    targets = UPGRADE_CODES | {WORKSHOP_CODE} | set(recipes) | {
        c for c, i in codes.items() if i["name"].startswith("xcd_rubbletreasure")}
    if any(not d["identical"] and d["code"] in targets for d in duplicates):
        raise ValueError("Conflicting original Maple catalog identities require review.")
    cms = _xml("gameSettingsCMS.xml.gz")
    prereqs = {p.get("name"): p for p in cms.iter("prereq") if p.get("name")}
    quests = {q.get("name"): q for q in _xml("questSettings_0.xml.gz").iter("quest")
              if q.get("name", "").startswith("xcd_rubbletreasure")}
    return codes, recipes, prereqs, quests


def catalog_identity_audit():
    """Expose duplicate-code evidence instead of silently masking conflicts."""
    _sources()  # Refuse a conflict affecting this module's target identities.
    codes, duplicates, count = _catalog()
    targets = UPGRADE_CODES | {WORKSHOP_CODE} | set(workshop_recipes())
    return {"catalogRecords": count, "uniqueCodes": len(codes),
            "duplicateRows": copy.deepcopy(duplicates),
            "targetCodes": sorted(targets),
            "targetDuplicateRows": copy.deepcopy([d for d in duplicates if d["code"] in targets])}


def source_hashes():
    files = ("xml/gz/v855038/items_opt.amf", "xml/gz/v855098/crafting.xml.gz",
             "xml/gz/v855098/gameSettingsCMS.xml.gz", "xml/gz/v855098/questSettings_0.xml.gz",
             "xml/gz/v855098/worldScore.amf.gz")
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files}


def workshop_recipes():
    """Every original Workshop recipe, including locked skill levels 2–5."""
    return tuple(_sources()[1])


@lru_cache(maxsize=1)
def _world_score():
    import pyamf
    raw = zlib.decompress((ROOT / "xml/gz/v855098/worldScore.amf.gz").read_bytes())
    score = pyamf.get_decoder(pyamf.AMF3, raw).readElement()["worldScoreCanada"]["scores"]["score"]
    levels = score["level"]
    if (len(levels) != 151 or [int(x["num"]) for x in levels] != list(range(151))
            or [int(x["required"]) for x in levels] != sorted({int(x["required"]) for x in levels})
            or score["id"] != "canadaPoints" or len(score["task"]) != 18):
        raise ValueError("The original Maple world-score contract changed.")
    return score


def world_score_contract():
    """151 original thresholds, default level, task rules and unmerged rewards.

    display_only remains a UI row. Returning a reward contract never grants it,
    and this module never combines display rows with actual item_grant rows.
    """
    return copy.deepcopy(_world_score())


def world_score_at_points(points):
    """Resolve a supplied Maple score without XP/currency/reward mutation."""
    _integer(points, "Maple score")
    levels = _world_score()["level"]
    current = max((row for row in levels if int(row["required"]) <= points),
                  key=lambda row: int(row["num"]))
    level = int(current["num"])
    next_row = levels[level + 1] if level < 150 else None
    return {"unit": "canadaPoints", "points": points, "level": level,
            "required": int(current["required"]),
            "nextRequired": int(next_row["required"]) if next_row else None,
            "levelContract": copy.deepcopy(current), "awardsApplied": False}


def workshop_recipe(code):
    if not isinstance(code, str) or code not in _sources()[1]:
        raise ValueError("This is not an original Maple Workshop recipe.")
    recipe = _sources()[1][code]
    return {
        "code": code, "name": recipe.findtext("name"), "craft": WORKSHOP_CRAFT,
        "skillLevelRequired": int(recipe.findtext("SkillLevelRequired")),
        "initialRecipeLevel": int(recipe.findtext("InitialRecipeLevel")),
        "minutesToCook": int(recipe.findtext("MinutesToCook")),
        "ingredients": [dict(i.attrib) for i in recipe.findall("Ingredients/Ingredient")],
        "rewards": _node(recipe.find("Reward")),
        "mastery": _node(recipe.find("Mastery")),
        "rushCostCoins": int(recipe.findtext("RushCostCoins")),
        "rushCostCash": int(recipe.findtext("RushCostCash")),
        "raw": _node(recipe),
    }


def workshop_preflight(code, *, world, player_level, craft_level, experiments,
                       cottage_present, recipe_unlocked):
    """Check contract facts only; no queue, inventory, charge or success packet."""
    recipe = workshop_recipe(code)
    _integer(player_level, "Player level")
    _integer(craft_level, "Craft skill level", 1, 5)
    if world != "canada":
        raise ValueError("Maple Workshop requires Canada world context.")
    if not isinstance(experiments, dict) or type(experiments.get("fv_xcd_master")) is not int or experiments["fv_xcd_master"] != 1:
        raise ValueError("Maple's original experiment gate is closed.")
    if player_level < int(_sources()[0][WORKSHOP_CODE]["requiredLevel"]):
        raise ValueError("Maple Workshop requires player level 15.")
    if cottage_present is not True:
        raise ValueError("The original Maple Workshop must be present.")
    if recipe_unlocked is not True or craft_level < recipe["skillLevelRequired"]:
        raise ValueError("This Maple Workshop recipe is locked.")
    raw = _sources()[1][code]
    if raw.findtext("Deprecated") != "0" or raw.findtext("ComingSoon", "0") != "0" or raw.find("prereqs") is not None or raw.find("limitedStart") is not None or raw.find("limitedEnd") is not None:
        raise ValueError("This recipe has unsupported availability requirements.")
    return recipe


def upgrade_requirements(code, target_level):
    """Exact declared stage and parts; never reinterpret inconsistent totals."""
    if not isinstance(code, str) or code not in UPGRADE_CODES:
        raise ValueError("Only Summerwood Lodge and Valley Observatory are covered.")
    _integer(target_level, "Target upgrade level", 2, 31 if code == "2nnz" else 10)
    item = _sources()[0][code]
    features = item["features"]["feature"]
    features = features if isinstance(features, list) else [features]
    expand = next(f for f in features if f.get("name") == "expand")
    stage = next(s for s in expand["upgrade"] if s["level"] == str(target_level))
    parts = stage["part"] if isinstance(stage["part"], list) else [stage["part"]]
    total = sum(int(p["need"]) for p in parts)
    return {"code": code, "itemName": item["name"], "targetLevel": target_level,
            "declaredMatsNeeded": int(stage["matsNeeded"]), "stagePartTotal": total,
            "declaredMatchesStageParts": total == int(stage["matsNeeded"]),
            "initialExpansionLevel": item.get("initialExpansionLevel"),
            "rawStage": copy.deepcopy(stage),
            "itemRequirements": copy.deepcopy(item.get("requirements")),
            "experimentGate": copy.deepcopy(item.get("experimentGate"))}


def prerequisite(name):
    if not isinstance(name, str) or name not in _sources()[2]:
        raise ValueError("The original prerequisite is unknown.")
    return _node(_sources()[2][name])


def prerequisite_status(name, facts):
    """Evaluate a bounded source tree; unknown/malformed/missing facts close it.

    `server_time` is an explicitly supplied naive original-server wall clock.
    This helper does not guess the archive's timezone or source facts from saves.
    eos and experiment facts remain distinct. No caller should use this result
    alone to perform an operation whose transaction contract is unrecovered.
    """
    if not isinstance(facts, dict):
        raise ValueError("Prerequisite facts must be a mapping.")
    def check(node, seen=()):
        attrs = dict(node.attrib)
        kind, value = attrs.get("type"), attrs.get("value")
        children = []
        supported = True
        met = False
        if kind in ("AND", "OR"):
            children = [check(c, seen) for c in node]
            # Missing/unsupported evidence never becomes eligible via an OR.
            supported = all(c["supported"] for c in children)
            met = bool(children) and supported and (all(c["met"] for c in children) if kind == "AND" else any(c["met"] for c in children))
        elif kind == "prereq_check":
            if value in seen or value not in _sources()[2]:
                supported = False
            else:
                children = [check(_sources()[2][value], seen + (value,))]
                met, supported = children[0]["met"], children[0]["supported"]
        elif kind == "location":
            met = isinstance(facts.get("world"), str) and facts["world"] == value
        elif kind == "level_min":
            level = facts.get("player_level")
            met = type(level) is int and level >= int(value)
        elif kind in ("experiment", "eos"):
            table = facts.get({"experiment": "experiments", "eos": "eos"}[kind], {})
            actual = table.get(value) if isinstance(table, dict) else None
            met = type(actual) is int and actual == int(attrs["variant"])
        elif kind in ("start_time", "end_time"):
            now = facts.get("server_time")
            try:
                boundary = datetime.strptime(value, "%m/%d/%Y")
            except (TypeError, ValueError):
                supported = False
            else:
                if type(now) is datetime and now.tzinfo is None:
                    # Original PrerequisiteUtility.isPrerequisiteMet method10286
                    # defaults to >= for start and <= for end (inclusive instant).
                    met = now >= boundary if kind == "start_time" else now <= boundary
        elif kind in ("quest_complete", "has_item", "not_placed_item"):
            field = {"quest_complete": "completed_quests", "has_item": "owned_codes", "not_placed_item": "placed_codes"}[kind]
            supplied = facts.get(field)
            if isinstance(supplied, (set, frozenset, list, tuple)) and all(isinstance(x, str) for x in supplied):
                met = value not in supplied if kind == "not_placed_item" else value in supplied
        else:
            supported = False
        # Original leaves can override comparison operators and carry quantity,
        # context or metadata. The bounded evaluator must not silently ignore
        # those requirements, even when its basic type/value check passes.
        allowed = {"name", "type", "value"}
        if kind in ("experiment", "eos"):
            allowed.add("variant")
        if set(attrs) - allowed:
            supported = False
        result = {"attributes": attrs, "met": bool(met and supported), "supported": supported}
        if children:
            result["children"] = children
        return result
    node = _sources()[2].get(name) if isinstance(name, str) else None
    if node is None:
        raise ValueError("The original prerequisite is unknown.")
    return check(node, (name,))


def section_prerequisites(code):
    """Exact section gates plus quest tasks; replacement geometry is unavailable."""
    item = _sources()[0].get(code) if isinstance(code, str) else None
    if not item or item.get("className") not in ("MultiRewardTreasureConstructionBuilding", "MultiRewardTreasurePayerConstructionBuilding") or not item["name"].startswith("xcd_rubbletreasure"):
        raise ValueError("This is not an original Maple land section.")
    name = item["name"]
    hover = item.get("hoverContextMenu", {}).get("prereqName")
    quest = _sources()[3].get(name + "-01-001")
    return {"code": code, "name": name, "hoverPrerequisite": prerequisite(hover) if hover else None,
            "marketPrerequisite": prerequisite(item["marketPrereqs"]) if item.get("marketPrereqs") else None,
            "quest": _node(quest), "cash": item.get("cash"),
            "locationTable": item.get("transformByLocationTable"),
            "completionSupported": False,
            "blocker": "Original location transformation rows and server finishedItems are missing."}
