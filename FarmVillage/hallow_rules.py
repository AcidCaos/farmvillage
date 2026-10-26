"""Archived Haunted Hollow rules, a dormant score reducer and dormant lifecycle.

Nothing here activates travel or accepts gateway requests. The expansion hook
is for a future authoritative purchase service: its previous_world argument
must be the server's detached pre-transaction snapshot, never client data.
It does not buy land, waive prerequisites or expose a route. The allAccess
unlock and the expansion lifecycle below mutate only detached copies, commit
once on success, and are referenced by no runtime route; guard_land_purchase
stays closed and Hallow stays out of world_travel.SUPPORTED_WORLDS.
"""
import copy
from functools import lru_cache
import hashlib
import math
from pathlib import Path
import re
import uuid
import xml.etree.ElementTree as ET
import zlib

import pyamf

import constants
from bundle import XML_DIR
import world_travel

WORLD = "hallow"
SCORE = "spook"
STATE_KEY = "_hallowScoreAccounting"
WORLD_STATE_KEY = "_hallowWorldState"
STORAGE_ID = -14
THEME = "hallow_theme"
ACCESS_OPTION = "allAccess"
UNLOCK_SPOOK_POINTS = 1  # unlock_world_score unit=spook value=1 (allAccess reward).
_TREASURE_CLASS = "FixedTreasureConstructionBuilding"
_AVIARY_CLASS = "FeatureBuilding"
# Exact keys written by the original client's getSaveObject chain for these
# StorageBuilding descendants (SavedObject 1907, EngineObject 1911, PositionedObject
# 1925, WorldObject 1993, ItemInstance 2126, MapResource 6054, HarvestableResource
# 8342, Building 8443, StorageBuilding 11985). SavedObject also assigns tempId from
# m_tempId, but no sample save carries it (null is dropped), so it is not persisted here.
# The key set equals that of the StorageBuilding in LocalData/saves.
PERSISTED_FIELDS = frozenset({"buildTime", "className", "components", "contents", "deleted",
    "direction", "id", "instanceDataStoreKey", "itemName", "plantTime", "position", "state"})
_MAX_INTEGER = 2_147_483_647
_MAX_LEVEL = 999  # WorldScoreSettingsManager.getLevelForScore's original scan.
_SOURCE_HASHES = {
    "gz/v855098/gameSettings.xml.gz": "c1fa55f130c4942ea978b07168b37285389d36e30fce30fc30647deff5e5e11b",
    "gz/v855098/gameSettingsCMS.xml.gz": "2153a81311632e5697b6e10fb40be729bbd87ed1719554bc7fdf0ef8934fb43d",
    "gz/v855098/worldScore.amf.gz": "4a69109bc466f6881a0435d6f89f5089f6c99c9e801c6fc85cb75f0c9c2a5048",
    "gz/v855038/items_opt.amf": "14987fd4c07f9de35ff5092aeab58584802fd7fbeca1131ad1a5e3eee381a4d7",
}


def _integer(value, label, minimum=0, maximum=_MAX_INTEGER):
    if (type(value) not in (int, float) or not minimum <= value <= maximum
            or (type(value) is float and not math.isfinite(value)) or value != int(value)):
        raise ValueError(label + " must be a supported whole number.")
    return int(value)


def _list(value):
    return value if isinstance(value, list) else ([] if value is None else [value])


def _source(name):
    raw = Path(XML_DIR, name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != _SOURCE_HASHES[name]:
        raise ValueError("Haunted Hollow's archived rules changed and require review.")
    return zlib.decompress(raw)


@lru_cache(maxsize=1)
def _archive():
    settings = ET.fromstring(_source("gz/v855098/gameSettings.xml.gz"))
    cms = ET.fromstring(_source("gz/v855098/gameSettingsCMS.xml.gz"))
    scores = pyamf.get_decoder(pyamf.AMF3, _source("gz/v855098/worldScore.amf.gz")).readElement()
    catalog = pyamf.get_decoder(pyamf.AMF3, _source("gz/v855038/items_opt.amf")).readElement()
    by_name, by_code = {}, {}
    for item in catalog["settings"]["items"]["item"]:
        by_name.setdefault(item["name"], item)
        by_code.setdefault(item["code"], item)
    score = scores["worldScoreSpook"]["scores"]["score"]
    global_tasks = scores["worldScoreGlobal"]["scores"]["score"]["task"]
    global_tasks = [task for task in global_tasks if any(
        reward.get("type") == "world_score" and reward.get("unit") == SCORE
        for reward in _list(task.get("rewards", {}).get("reward")))]
    expansion = settings.find("expansions/expansion[@name='hallow']")
    added = settings.find("farmExpansions/world[@name='hallow']/farmExpansionAddedItems")
    return {
        "score": score, "globalTasks": global_tasks,
        "scoreMinimumXP": int(settings.find("levels/level[@num='15']").get("requiredXP")),
        "items": by_name, "codes": by_code,
        "land": {name: item for name, item in by_name.items()
                 if re.fullmatch(r"xhwfarm\d+(?:_cash)?", name)},
        "prerequisites": {node.get("name"): node for node in cms.findall(".//prereq[@name]")},
        "access": {node.tag: {"attributes": dict(node.attrib),
            "prerequisites": [dict(e.attrib) for e in node.findall("prereqs/prereq")],
            "rewards": [dict(e.attrib) for e in node.findall("rewards/reward")]}
            for node in expansion if node.tag in ("earlyAccess", "generalAccess", "allAccess")},
        "added": {int(node.get("squares")): [dict(e.attrib) for e in node]
                  for node in added},
    }


def recovered_rules():
    """Independent source-backed evidence; this is not an availability offer."""
    archive = _archive()
    return copy.deepcopy({"worldType": WORLD, "storageId": STORAGE_ID,
        "currency": "coins", "scoreUnit": SCORE, "spendableScore": False,
        "sourceHashes": _SOURCE_HASHES, "access": archive["access"],
        "scoreEligibility": {"minimumLevel": 15, "minimumXP": archive["scoreMinimumXP"],
                             "experiment": {"fv_hallow": 1}, "prerequisite": "fv_xhw_shared"},
        "levels": archive["score"]["level"], "defaultLevel": archive["score"]["defaultLevel"],
        "tasks": archive["score"]["task"], "globalTasks": archive["globalTasks"],
        "land": archive["land"], "expansionAddedObjects": archive["added"]})


def level_requirement(level):
    """Explicit level0..30 table, then original AS3 Math.round polynomial."""
    level = _integer(level, "Spook level", maximum=_MAX_LEVEL + 1)
    levels = _archive()["score"]["level"]
    for row in levels:
        if int(row["num"]) == level:
            return int(row["required"])
    # AS3 Math.round rounds positive half values upward; Python round uses ties
    # to even. Preserve the original floating-point expression and operation order.
    return math.floor(10.006 * level ** 2 - 48.818 * level + 16.945 + 0.5)


def level_for_score(score):
    score = _integer(score, "Spook score")
    if score >= level_requirement(_MAX_LEVEL + 1):
        raise ValueError("That imported Spook score exceeds the bounded level scan.")
    result = 0
    for level in range(1, _MAX_LEVEL + 1):
        if score < level_requirement(level):
            break
        result = level
    return result


def _score_record(save):
    player = save.get("userInfo", {}).get("player", {})
    scores = player.get("worldScores")
    if scores is None or (isinstance(scores, dict) and SCORE not in scores):
        return None
    if not isinstance(scores, dict) or not isinstance(scores[SCORE], dict):
        raise ValueError("The imported Haunted Hollow score is invalid.")
    record = scores[SCORE]
    score = _integer(record.get("score"), "Imported Spook score", minimum=1)
    level = _integer(record.get("level"), "Imported Spook level", minimum=1, maximum=_MAX_LEVEL)
    if level_for_score(score) != level:
        raise ValueError("The imported Spook score and level disagree; both were preserved.")
    return record


def world_level(save):
    """Original getWorldLevel returns -1 for a missing score, without a grant."""
    record = _score_record(save)
    return -1 if record is None else int(record["level"])


def meets_level_prerequisite(save, name):
    """Only the exact archived fv_spook_unlock_level_1..50 predicates."""
    match = re.fullmatch(r"fv_spook_unlock_level_(\d+)", name) if isinstance(name, str) else None
    node = _archive()["prerequisites"].get(name)
    if (not match or not 1 <= int(match[1]) <= 50 or node is None
            or node.attrib != {"name": name, "type": "AND"}
            or len(node) != 1 or node[0].tag != "prereq" or len(node[0])
            or node[0].attrib != {"type": "world_level_min", "value": SCORE,
                                  "quantity": match[1]}):
        raise ValueError("That Haunted Hollow prerequisite is not restored.")
    return world_level(save) >= int(match[1])


def item_level_requirement(item_name):
    """Return a catalog's known Spook gate; fail closed on other prerequisites."""
    item = _archive()["items"].get(item_name)
    if item is None:
        raise ValueError("The Haunted Hollow item is unknown.")
    name = item.get("purchasePrereqs")
    if not name:
        return None
    if not re.fullmatch(r"fv_spook_unlock_level_(?:[1-9]|[1-4]\d|50)", str(name)):
        raise ValueError("That item's quest or special purchase prerequisite is not restored.")
    # Validate the definition even without a player, keeping drift fail closed.
    meets_level_prerequisite({"userInfo": {"player": {}}}, name)
    return int(name.rsplit("_", 1)[1])


def guard_item_level(save, item_name):
    """Check the Spook slice only; never substitutes for other purchase guards."""
    requirement = item_level_requirement(item_name)
    if requirement is not None and world_level(save) < requirement:
        raise ValueError("This item requires Spook level " + str(requirement) + ".")


def land_rules(item_name):
    """Describe price, world/experiment gates and original added objects."""
    item = _archive()["land"].get(item_name)
    if item is None:
        raise ValueError("That Haunted Hollow land item is unknown.")
    width = int(item["squares"])
    canonical = item_name.removesuffix("_cash")
    task = next((task for task in _archive()["score"]["task"]
                 if task["action"] == "expandFarm" and task["type"] == canonical), None)
    return copy.deepcopy({"itemName": item_name, "width": width,
        "requiredLevel": int(item.get("requiredLevel", "1")),
        "world": WORLD, "experimentGate": item.get("experimentGate"),
        "market": item.get("market"), "coinCost": int(item.get("cost", "0")),
        # ChangeFarmItem.saleCash method11373, lines131–132, overrides raw
        # catalog cash with1 for every expand_farm item, including Hallow.
        "catalogCash": int(item.get("cash", "0")),
        "cashCost": 1 if item.get("market") == "cash" else 0,
        "archived": item.get("archived") == "yes",
        "buyable": item.get("buyable") == "true", "spookLevelRequirement": None,
        "scoreAward": int(task["rewards"]["reward"]["value"]) if task else 0,
        "addedObjects": _archive()["added"].get(width, [])})


def guard_land_purchase(*_args, **_kwargs):
    raise ValueError("Haunted Hollow land purchase, treasure grants and travel are not restored.")


def spend_score(*_args, **_kwargs):
    raise ValueError("Spook Points are a cumulative world score and cannot be spent.")


def _ledger(save):
    state = save.get(STATE_KEY)
    if STATE_KEY not in save:
        record = _score_record(save)
        return {"version": 1, "baselineScore": int(record["score"]), "expansions": {}}
    if (not isinstance(state, dict) or type(state.get("version")) is not int or state["version"] != 1
            or not isinstance(state.get("expansions"), dict)):
        raise ValueError("The Haunted Hollow score accounting state is invalid.")
    allowed = {task["type"] for task in _archive()["score"]["task"]
               if task["action"] == "expandFarm"}
    if not set(state["expansions"]) <= allowed:
        raise ValueError("The Haunted Hollow score receipt has no original event.")
    for name, receipt in state["expansions"].items():
        rule = land_rules(name)
        if (not isinstance(receipt, dict)
                or receipt != {"width": rule["width"], "points": rule["scoreAward"]}):
            raise ValueError("The Haunted Hollow expansion score receipt is invalid.")
    baseline = _integer(state.get("baselineScore"), "Imported Spook accounting baseline", minimum=1)
    if baseline + sum(receipt["points"] for receipt in state["expansions"].values()) > _score_record(save)["score"]:
        raise ValueError("The imported Spook receipts exceed the preserved score.")
    return copy.deepcopy(state)


def _guard_score_modifiers(save):
    # TInitUser copies player.buffs by item name; BPermanentTypeGain iterates
    # the names, not the stored quantities. The trophy/buff lifecycle is not
    # restored here, so presence must never silently receive the base rate.
    buffs = save["userInfo"]["player"].get("buffs", {})
    if not isinstance(buffs, dict):
        raise ValueError("The imported Haunted Hollow buff state is not supported.")
    for name in buffs:
        item = _archive()["items"].get(name)
        if item is None or (item.get("className") == "BPermanentTypeGain"
                            and item.get("subtype") in ("spook_gain", "coin_gain")):
            raise ValueError("Haunted Hollow's imported score-gain buff is not restored.")
    worlds = [save.get("world", {})]
    travel = save.get("_ownedWorldTravel")
    if isinstance(travel, dict) and isinstance(travel.get("inactive"), dict):
        worlds.extend(travel["inactive"].values())
    for world in worlds:
        if not isinstance(world, dict) or not isinstance(world.get("objectsArray", []), list):
            raise ValueError("The imported score-modifier object snapshot is invalid.")
        if any(isinstance(obj, dict)
                and obj.get("itemName") in ("xhwdoublesptrophy", "doublecoinstatue")
                for obj in world.get("objectsArray", [])):
            raise ValueError("Haunted Hollow's score-gain trophy is not restored.")


def _level_rewards(level):
    row = next((row for row in _archive()["score"]["level"] if int(row["num"]) == level), None)
    if row is None:
        row = _archive()["score"]["defaultLevel"]
    return _list(row.get("rewards", {}).get("reward"))


def _apply_level_rewards(player, old_level, new_level):
    grants, coins = {}, 0
    for level in range(old_level + 1, new_level + 1):
        for reward in _level_rewards(level):
            kind = reward["type"]
            if kind == "display_only":
                continue
            if kind == "coins":
                coins += int(reward["value"])
            elif kind == "item_grant" and reward["value"] in _archive()["codes"]:
                code = reward["value"]
                grants[code] = grants.get(code, 0) + int(reward.get("quantity", 1))
            else:
                raise ValueError("A Haunted Hollow level reward is not restored.")
    if coins:
        player["gold"] = _integer(player.get("gold"), "Imported coins") + coins
        _integer(player["gold"], "Rewarded coins")
    if grants:
        storage = player.get("storageData")
        if not isinstance(storage, dict) or ("-1" in storage and not isinstance(storage["-1"], dict)):
            raise ValueError("The imported gift storage is invalid.")
        gifts = storage.setdefault("-1", {})
        for code, count in grants.items():
            entry = gifts.get(code)
            if code not in gifts:
                gifts[code] = [count, [], []]
            else:
                if (not isinstance(entry, list) or len(entry) != 3
                        or not isinstance(entry[1], list) or not isinstance(entry[2], list)):
                    raise ValueError("The imported level-reward gift entry is invalid.")
                entry[0] = _integer(entry[0], "Imported gift count") + count
                _integer(entry[0], "Rewarded gift count")
    return {"coins": coins, "items": grants}


def record_verified_expansion(save, *, previous_world, item_name, score_experiments=None):
    """Account one server-validated land transaction on a detached save.

    The caller must first validate and perform the original purchase (world,
    level, experiment, funds, sequential size, terrain, treasure additions).
    Pass the *server's* pre-purchase world snapshot and its server-owned
    experiment assignments. fv_xhw_shared independently requires XP level15
    and fv_hallow variant1. No user receipt/amount/experiment proof is
    accepted: ownership is the finite original expansion name, so retries, cash
    aliases and fresh sessions cannot earn the same size twice. Unsupported
    task classes, score unlocks, consumables and retroactive rewards are absent.
    The caller persists the save with its existing atomic village transaction.
    """
    if save.get("userInfo", {}).get("currentWorldType") != WORLD:
        raise ValueError("Spook expansion accounting requires Haunted Hollow.")
    if (not isinstance(score_experiments, dict)
            or type(score_experiments.get("fv_hallow")) is not int
            or score_experiments["fv_hallow"] != 1
            or _integer(save["userInfo"]["player"].get("xp"), "Imported XP") < _archive()["scoreMinimumXP"]):
        raise ValueError("Spook scoring requires original level15 and server experiment fv_hallow variant1.")
    record = _score_record(save)
    if record is None:
        raise ValueError("Haunted Hollow's score has not been unlocked.")
    _guard_score_modifiers(save)
    rule = land_rules(item_name)
    canonical = item_name.removesuffix("_cash")
    if not rule["buyable"] or not rule["scoreAward"]:
        raise ValueError("That expansion has no recovered Spook earning task.")
    state = _ledger(save)
    after = save.get("world")
    if not isinstance(after, dict):
        raise ValueError("The imported Haunted Hollow world is invalid.")
    after_width = _integer(after.get("sizeX"), "Owned land width", minimum=50)
    if _integer(after.get("sizeY"), "Owned land height", minimum=50) != after_width:
        raise ValueError("The imported Haunted Hollow land is not square.")
    if any(receipt["width"] > after_width
           for receipt in state["expansions"].values()):
        raise ValueError("The imported Spook receipt exceeds the owned land size.")
    if canonical in state["expansions"]:
        return {"points": 0, "levels": [], "coins": 0, "items": {}}
    before = previous_world
    if (not isinstance(before, dict) or not isinstance(after, dict)
            or before.get("sizeX") != before.get("sizeY")
            or after.get("sizeX") != after.get("sizeY")
            or _integer(before.get("sizeX"), "Previous land width", minimum=50) != rule["width"] - 8
            or _integer(after.get("sizeX"), "Purchased land width", minimum=58) != rule["width"]):
        raise ValueError("The verified expansion must be the next original Haunted Hollow size.")
    new_score = _integer(record["score"] + rule["scoreAward"], "Awarded Spook score")
    old_level, new_level = int(record["level"]), level_for_score(new_score)
    working = copy.deepcopy(save)
    player = working["userInfo"]["player"]
    rewards = _apply_level_rewards(player, old_level, new_level)
    player["worldScores"][SCORE].update(score=new_score, level=new_level)
    state["expansions"][canonical] = {"width": rule["width"], "points": rule["scoreAward"]}
    working[STATE_KEY] = state
    save.clear()
    save.update(working)
    return {"points": rule["scoreAward"], "levels": list(range(old_level + 1, new_level + 1)), **rewards}


@lru_cache(maxsize=1)
def _access_contract():
    """Source-pinned allAccess rewards, prerequisite chain and initial farm size."""
    archive = _archive()
    access = archive["access"]["allAccess"]
    if (access["attributes"] != {}
            or access["prerequisites"] != [{"type": "prereq_check", "value": "fv_xhw_all_access"}]
            or access["rewards"] != [{"type": "world_unlock", "value": WORLD},
                                     {"type": "unlock_world_score", "unit": SCORE, "value": "1"}]):
        raise ValueError("Haunted Hollow's recovered all-access contract changed and requires review.")
    chain = {
        "fv_xhw_all_access": [{"type": "prereq_check", "value": "fv_xhw_access_shared"},
                              {"type": "experiment", "value": "fv_hallow_for_all", "variant": "1"}],
        "fv_xhw_access_shared": [{"type": "prereq_check", "value": "fv_xhw_shared"},
                                 {"type": "has_not_unlocked_world", "value": WORLD}],
        "fv_xhw_shared": [{"type": "level_min", "value": "15"},
                          {"type": "experiment", "value": "fv_hallow", "variant": "1"}],
    }
    for name, expected in chain.items():
        node = archive["prerequisites"].get(name)
        if (node is None or node.get("type") != "AND"
                or [dict(child.attrib) for child in node] != expected):
            raise ValueError("Haunted Hollow's recovered all-access prerequisites changed and require review.")
    cms = ET.fromstring(_source("gz/v855098/gameSettingsCMS.xml.gz"))
    farm_size = cms.find("farming/farmingEntry[@key='farmSize']")
    if farm_size is None or farm_size.get("value") != "50":
        raise ValueError("Haunted Hollow's recovered initial farm size changed and requires review.")
    return {"farmSize": 50, "minimumXP": archive["scoreMinimumXP"]}


def _require_experiments(experiments, names):
    if (not isinstance(experiments, dict)
            or any(type(experiments.get(name)) is not int or experiments[name] != 1 for name in names)):
        raise ValueError("Haunted Hollow requires the server's original variant1 experiment assignments.")


def _valid_snapshot(snapshot):
    return (isinstance(snapshot, dict) and type(snapshot.get("sizeX")) is int
            and snapshot.get("sizeY") == snapshot["sizeX"] and snapshot["sizeX"] >= 50
            and snapshot.get("tileSet") == THEME and snapshot.get("terrain") is None
            and isinstance(snapshot.get("objectsArray"), list))


def _access_state(save):
    """Return the durable allAccess state, None before unlock, or fail closed.

    Ownership is the conjunction of the world unlock, summary, -14 inventory,
    the Spook score and this durable state. Any partial subset is preserved and
    rejected rather than repaired or re-unlocked.
    """
    user = save["userInfo"]
    player = user["player"]
    unlocked = user.get("unlockedWorldTypes", [])
    summaries = user.get("worldSummaryData", {})
    storage = player.get("storageData", {})
    if not isinstance(unlocked, list) or not isinstance(summaries, dict) or not isinstance(storage, dict):
        raise ValueError("The imported Haunted Hollow ownership state is invalid.")
    state = save.get(WORLD_STATE_KEY)
    evidence = (WORLD in unlocked, summaries.get(WORLD) is not None,
                str(STORAGE_ID) in storage, state is not None)
    if not any(evidence):
        return None
    if not all(evidence):
        raise ValueError("The Haunted Hollow ownership record is partial; it was preserved unchanged.")
    if (not isinstance(state, dict) or state.get("version") != 1
            or state.get("option") != ACCESS_OPTION
            or type(state.get("unlockedAt")) is not int
            or not isinstance(state.get("inactive"), dict)
            or set(state["inactive"]) - {WORLD}
            or type(state.get("nextObjectId")) is not int
            or not 1 <= state["nextObjectId"] <= world_travel.MAX_OBJECT_ID + 1):
        raise ValueError("The Haunted Hollow durable access state is invalid; it was preserved unchanged.")
    summary = summaries[WORLD]
    if (not isinstance(summary, dict) or summary.get("storageId") != STORAGE_ID
            or not isinstance(storage[str(STORAGE_ID)], dict)):
        raise ValueError("The Haunted Hollow inventory or summary does not match its unlock.")
    if WORLD in state["inactive"] and not _valid_snapshot(state["inactive"][WORLD]):
        raise ValueError("The stored Haunted Hollow snapshot is not supported.")
    if _score_record(save) is None:
        raise ValueError("The Haunted Hollow unlock has no Spook score record.")
    return state


def _reserved_object_ids(save):
    ids = set(world_travel._reserved_ids(save))
    state = save.get(WORLD_STATE_KEY)
    if isinstance(state, dict) and isinstance(state.get("inactive"), dict) and WORLD in state["inactive"]:
        ids.update(int(obj["id"]) for obj in state["inactive"][WORLD]["objectsArray"])
    return ids


def _allocate_object_ids(save, count):
    """Monotonic IDs unique across owned worlds, the dormant snapshot and storage."""
    state = save[WORLD_STATE_KEY]
    value = max(max(_reserved_object_ids(save), default=0) + 1, state["nextObjectId"])
    ids = []
    for _ in range(count):
        if constants.TEMP_ID_START <= value <= constants.TEMP_ID_END:
            value = constants.TEMP_ID_END + 1
        if value > world_travel.MAX_OBJECT_ID:
            raise ValueError("The farm has exhausted the supported object ID range.")
        ids.append(value)
        value += 1
    state["nextObjectId"] = value
    return ids


def unlock_all_access(save, *, now, experiments):
    """Apply the original allAccess unlock to a detached copy and commit once.

    Recovered rewards: world_unlock hallow, then unlock_world_score spook value 1,
    which starts the Spook score at one point on level 1. Level 1 declares no
    reward, and allAccess charges nothing. The empty local starter stays in the
    dormant durable state (no route can enter it). A complete retry returns False
    and changes nothing; partial or conflicting ownership fails closed.
    """
    contract = _access_contract()
    if type(now) is not int or now < 0:
        raise ValueError("The Haunted Hollow unlock time must be a whole number.")
    _require_experiments(experiments, ("fv_hallow", "fv_hallow_for_all"))
    world_travel.validate(save)
    if _access_state(save) is not None:
        return False
    user = save["userInfo"]
    active = user.get("currentWorldType") or "farm"
    if active == WORLD or active not in world_travel.SUPPORTED_WORLDS:
        raise ValueError("The imported active world cannot host Haunted Hollow's unlock.")
    unlocked = user.get("unlockedWorldTypes", [])
    if not isinstance(unlocked, list) or not all(isinstance(name, str) for name in unlocked):
        raise ValueError("The imported world unlock state is invalid.")
    summaries = user.get("worldSummaryData", {})
    player = user["player"]
    if (not isinstance(summaries, dict) or not isinstance(player.get("storageData"), dict)
            or not isinstance(player.get("worldScores", {}), dict)):
        raise ValueError("The imported Haunted Hollow player state is invalid.")
    if SCORE in player.get("worldScores", {}):
        raise ValueError("A Spook score exists without a Haunted Hollow unlock and cannot be reset.")
    if _integer(player.get("xp"), "Imported XP") < contract["minimumXP"]:
        raise ValueError("Haunted Hollow's all-access unlock requires player level 15.")
    snapshot = {"id": 2, "uid": str(uuid.uuid4()), "sizeX": contract["farmSize"],
                "sizeY": contract["farmSize"], "objectsArray": [], "messageManager": [],
                "tileSet": THEME, "localStarter": "empty-hallow-v1"}
    working = copy.deepcopy(save)
    wuser = working["userInfo"]
    wuser.setdefault("worldSummaryData", {})[WORLD] = {
        "firstLoaded": now, "lastLoaded": now, "storageId": STORAGE_ID}
    wuser["unlockedWorldTypes"] = [*unlocked, WORLD]
    wplayer = wuser["player"]
    wplayer["storageData"][str(STORAGE_ID)] = {}
    wplayer.setdefault("worldScores", {})[SCORE] = {
        "score": UNLOCK_SPOOK_POINTS, "level": level_for_score(UNLOCK_SPOOK_POINTS)}
    working[WORLD_STATE_KEY] = {"version": 1, "option": ACCESS_OPTION, "unlockedAt": now,
                                "inactive": {WORLD: snapshot}, "nextObjectId": 1}
    _access_state(working)
    world_travel.validate(working)
    save.clear()
    save.update(working)
    return True


def _expansion_plans(width):
    """Recovered configured additions for one width, with no coordinate transform."""
    archive = _archive()
    plans = []
    for node in archive["added"].get(width, []):
        item = archive["codes"].get(node["code"])
        if (item is None or item.get("className") not in (_TREASURE_CLASS, _AVIARY_CLASS)
                or node.get("z") != "0" or node.get("state") not in ("construct_0", "built_0")):
            raise ValueError("The mandatory Haunted Hollow expansion objects need review.")
        plans.append({"itemName": item["name"], "className": item["className"],
                      "sizeX": int(item["sizeX"]), "sizeY": int(item["sizeY"]),
                      "position": {"x": int(node["x"]), "y": int(node["y"]), "z": 0},
                      "state": node["state"]})
    return plans


def pending_client_position(raw_x, raw_y, current_width, next_width):
    """Display-only original ExpansionAreaMapTrigger transform for the pending expansion.

    FarmGameWorld.initializeExpansionAreaItems (method 5558) passes diff =
    currentWidth - nextWidth to ExpansionAreaMapTrigger, whose loadObject (21713)
    adds that diff to x and, by original code, to y too. The archive coordinates
    therefore belong to the expanded (next) farm frame. This shifts them into the
    still-current frame and must never be persisted: applied to a purchased
    expansion it would move the first treasure to x=-3.
    """
    diff = _integer(current_width, "Current width", minimum=50) - _integer(next_width, "Next width", minimum=58)
    return int(raw_x) + diff, int(raw_y) + diff


def _persisted_object(object_id, plan):
    """Exact client-written persisted shape for one recovered mandatory object.

    Defaults are the values written for the sample StorageBuilding (built, empty
    contents, no plant time, direction 0, not deleted, no components). The
    construction-state values for buildTime and contents are unverified.
    """
    return {"id": object_id, "className": plan["className"], "itemName": plan["itemName"],
            "position": copy.deepcopy(plan["position"]), "state": plan["state"],
            "deleted": False, "direction": 0, "components": {}, "instanceDataStoreKey": None,
            "plantTime": None, "buildTime": 0, "contents": []}


def _footprint(obj):
    position = obj.get("position")
    if not isinstance(position, dict):
        raise ValueError("A saved Haunted Hollow object has no readable position.")
    x = _integer(position.get("x"), "Saved object x")
    y = _integer(position.get("y"), "Saved object y")
    catalog = _archive()["items"]
    item = catalog.get(obj["itemName"]) if isinstance(obj.get("itemName"), str) else None
    if obj.get("className") == "Plot":
        width = max(4, int((item or {}).get("sizeX") or 1))
        height = max(4, int((item or {}).get("sizeY") or 1))
    elif item is None or not item.get("sizeX") or not item.get("sizeY"):
        raise ValueError("A saved Haunted Hollow object's footprint is unknown.")
    else:
        width, height = int(item["sizeX"]), int(item["sizeY"])
    return (x, y, width, height)


def _overlaps(first, second):
    return (first[0] < second[0] + second[2] and second[0] < first[0] + first[2]
            and first[1] < second[1] + second[3] and second[1] < first[1] + first[3])


def _check_new_footprints(world, plans, objects, width):
    if world.get("sizeX") != width or world.get("sizeY") != width:
        raise ValueError("Haunted Hollow's mandatory objects require the purchased land.")
    planned = []
    for plan, obj in zip(plans, objects):
        rect = (obj["position"]["x"], obj["position"]["y"], plan["sizeX"], plan["sizeY"])
        if rect[0] < 0 or rect[1] < 0 or rect[0] + rect[2] > width or rect[1] + rect[3] > width:
            raise ValueError("A mandatory Haunted Hollow object falls outside the purchased land.")
        planned.append(rect)
    occupied = [_footprint(obj) for obj in world["objectsArray"]]
    for index, rect in enumerate(planned):
        if (any(_overlaps(rect, other) for other in occupied)
                or any(_overlaps(rect, other) for other in planned[index + 1:])):
            raise ValueError("A mandatory Haunted Hollow object would overlap a saved object; the "
                             "original re-basing of existing placements is not recovered, so the "
                             "expansion is refused.")


def record_expansion_lifecycle(save, *, previous_world, item_name, score_experiments=None):
    """Account one verified Haunted Hollow expansion with its configured objects.

    The caller has already validated and charged the purchase, placed the new
    size in save['world'] and supplied the server's pre-purchase snapshot as
    previous_world. This function then adds the recovered objects for that width
    (for 58: three treasures and the finished aviary) and the original Spook
    points in one commit. A retry of an accounted size is a zero result: no
    points, objects or IDs change. Any failure leaves the save untouched.
    Objects carry exactly PERSISTED_FIELDS at unshifted next-width coordinates.
    Existing objects are not re-based (that original step is unrecovered), so
    any footprint overlap refuses the expansion.
    """
    if not isinstance(item_name, str):
        raise ValueError("The Haunted Hollow expansion item is unknown.")
    if save["userInfo"].get("currentWorldType") != WORLD:
        raise ValueError("Haunted Hollow expansion accounting requires the active Haunted Hollow world.")
    state = _access_state(save)
    if state is None or WORLD in state["inactive"]:
        raise ValueError("Haunted Hollow must be unlocked and active before its expansion is accounted.")
    rule = land_rules(item_name)
    canonical = item_name.removesuffix("_cash")
    if canonical in _ledger(save)["expansions"]:
        return {"points": 0, "levels": [], "coins": 0, "items": {}, "objects": []}
    plans = _expansion_plans(rule["width"])
    working = copy.deepcopy(save)
    ids = _allocate_object_ids(working, len(plans))
    # Positions are the recovered next-width frame coordinates, persisted unshifted.
    objects = [_persisted_object(object_id, plan) for object_id, plan in zip(ids, plans)]
    _check_new_footprints(working["world"], plans, objects, rule["width"])
    working["world"]["objectsArray"].extend(objects)
    result = record_verified_expansion(working, previous_world=previous_world,
        item_name=item_name, score_experiments=score_experiments)
    _access_state(working)
    world_travel.validate(working)
    save.clear()
    save.update(working)
    return {**result, "objects": ids}
