"""Original construction and recovered finite material expansions.

The shipped storageConfig is authoritative for initial material counts; the
retired England Sheep Pen uses the separately documented 2011 recovery overlay.
item catalog's inline upgrades define expansion counts and capacities. This is
independent implementation from StorageBuilding.addItem, ConstructionBuilding
.addItem/onStoreComplete and ExpandFManager.addExpansionPart/refreshPartData in
FarmGame.swf. Both client templates disable the unsupported smart-buildable
cohort: getTunedPartRequirement otherwise adds ceil(base * 1.2), so its UI
would demand12 while the base catalog and local server require10.
Giving Building awards, explicit named completion gifts and the finite Orchard
replacement share the authored material path. Friend feeds, missing harvest
loot tables, random bonus selection and runtime-gated infinite stages remain
outside this handler.

All validation and withdrawals happen on a detached save. The caller's existing
village transaction commits the resulting in-memory state. No files or sessions
are opened here.
"""
import copy
from functools import lru_cache
import json
import math
from pathlib import Path
import re
import zlib

import pyamf

from bundle import TEMPLATES_DIR, XML_DIR
import engine
import england_progression
import items
import storage

_CLASSIC = {"turkeyroost": "turkeyroost_finished", "orchard": "orchard_finished",
            "xuk_sheep_pen": "xuk_sheep_pen_finished", "xukcombineconstruct": "xukcombine",
            "xukgarage": "xukgarage_finished", "nurserybarn": "nurserybarn_finished",
            "pigpen": "pigpenv2_finished"}
_FINISHED = frozenset((*_CLASSIC.values(), "nurserybarn_finished_complete", "pigpen_finished", "herbgarden",
                       "bldg_irrigationwell", "bldg_irrigationwell_8hr"))
_FINISH_REWARDS = {"nurserybarn": "foal_gray", "pigpen": "pigpen_male_light_green"}
REQUESTS_KEY = "_finiteConstructionRequests"
_PROGRESS_FIELDS = ("itemName", "className", "isFullyBuilt", "expansionLevel",
                    "expansionParts", "capacity", "contents", "plantTime", "itemOrder", "storageMetadata")


def _integer(value, label, minimum=0, maximum=2_147_483_647):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or int(value) != value
            or not minimum <= value <= maximum):
        raise ValueError(f"{label} must be a whole number from {minimum} to {maximum}.")
    return int(value)


def _catalog_integer(value, label, minimum=1):
    if isinstance(value, str) and value.isascii() and value.isdigit():
        value = int(value)
    return _integer(value, label, minimum)


def _list(value):
    return value if isinstance(value, list) else ([] if value is None else [value])


def _initial_level(item):
    if storage.feature_container_class(item):
        return storage.feature_container_initial_level(item)
    if _lootable_building(item) or storage.orchard_container_class(item):
        return max(1, _catalog_integer(item.get("storageSize", "1"), "Initial storage size"),
                   _catalog_integer(item.get("initialExpansionLevel", "1"), "Initial expansion level"))
    return _catalog_integer(item.get("initialExpansionLevel", "1"), "Initial building expansion level")


@lru_cache(maxsize=1)
def _storage_config():
    raw = zlib.decompress((Path(XML_DIR) / "gz/v855098/storageConfig.amf.gz").read_bytes())
    records = pyamf.get_decoder(pyamf.AMF3, raw).readElement()["storage"]["StorageBuilding"]
    return {record["name"]: record for record in records}


def _managed(item):
    return bool(item and (item.get("name") in _CLASSIC or item.get("name") in _FINISHED
                or _giving_building(item)
                or _lootable_building(item)
                or storage.orchard_container_class(item)
                or storage.feature_container_class(item)
                or (item.get("className") in ("HorseStableBuilding", "HorseStableBuildingFinished")
                    and (item.get("storageType") or {}).get("itemClass") == "horses")))


def _giving_building(item):
    """The recovered GivingBuildingWindow family, with no hidden harvester."""
    if (not item or item.get("className") != "FeatureBuilding" or item.get("type") != "building"
            or item.get("subtype") != "storage" or item.get("dialogName") != "FeatureBuildingGenericExpand"
            or item.get("initialExpansionLevel") != "1" or item.get("finishedName")):
        return False
    features = _list((item.get("features") or {}).get("feature"))
    classes = {row.get("className") for row in features if isinstance(row, dict)}
    if len(features) != 5 or classes != {
            "ExpandFManager", "StorageFManager", "ContextMenuFManager",
            "ImageProgressionFManager", "GivingBuildingTooltipFManager"}:
        return False
    if any("prereq" in row or "prereqs" in row for row in features):
        return False
    expand = next(row for row in features if row["className"] == "ExpandFManager")
    if set(expand) - {"name", "className", "upgrade", "friendRewards", "awardDialog", "awardDialogBackground"}:
        return False
    if next(row for row in features if row["className"] == "StorageFManager") != {
            "name": "storage", "className": "StorageFManager", "capacity": "0", "storageSize": "1"}:
        return False
    tooltip = next(row for row in features if row["className"] == "GivingBuildingTooltipFManager")
    dialogs = _list((item.get("dialogs") or {}).get("dialog"))
    return (tooltip == {"name": "tooltipText", "className": "GivingBuildingTooltipFManager"}
            and any(row.get("name") == "storage" and row.get("className") in (
                "Widgets.Windows.GivingBuildingWindow", "Widgets.Windows.HollyBrightTreeWindow")
                for row in dialogs if isinstance(row, dict))
            # Paid expansion uses its own authored part rows. Five shipped
            # Giving Building variants omit a StorageConfig entry entirely.
            and isinstance((item.get("storageType") or {}).get("itemClass"), str)
            and bool(item["storageType"]["itemClass"]))


def manages(item):
    """Whether this catalog item belongs to the bounded construction slice."""
    return _managed(item)


def _lootable_building(item):
    """Finite completion gifts, independently of the missing harvest tables."""
    if (not item or item.get("className") != "LootableFixedFeatureBuilding"
            or item.get("type") != "building" or item.get("capacity") != "0"
            or item.get("finishedName")):
        return False
    features = _list((item.get("features") or {}).get("feature"))
    if len(features) != 4 or {row.get("className") for row in features if isinstance(row, dict)} != {
            "ContextMenuFManager", "ExpandFManager", "HarvestFManager", "StorageFManager"}:
        return False
    if any("prereq" in row or "prereqs" in row for row in features):
        return False
    expand = next(row for row in features if row["className"] == "ExpandFManager")
    if set(expand) - {"name", "className", "friendRewards", "upgrade", "awardExperiment"}:
        return False
    # Owners with only an unrecovered harvest or an ambiguous owner-level
    # completion reward do not have a usable finite gift ladder.
    return any(isinstance(stage, dict) and isinstance(stage.get("rewardItem"), str)
               and stage["rewardItem"] for stage in _list(expand.get("upgrade")))


def _dynamic_parts_enabled():
    text = Path(TEMPLATES_DIR, "play.html").read_text(encoding="utf-8")
    return (re.search(r'"fv_dynamic_part_requirements_refactor"\s*:\s*1\s*[,}]', text) is not None
            and re.search(r'"fv_smartbuildable"\s*:\s*0\s*[,}]', text) is not None)


def is_complete(obj):
    """Read authoritative completion, including legacy finished-item saves."""
    item = items.get_item_by_name((obj or {}).get("itemName"))
    return bool(_managed(item) and _built(obj, item))


def preserve_fields(stored, incoming):
    """Protect durable progress from ordinary move/store client snapshots.

    StorageBuilding.getSaveObject deliberately emits contents=[] and does not
    serialize isFullyBuilt, expansionLevel or expansionParts. Even explicitly
    supplied progress fields must therefore never replace the server's state.
    New placement initialization is handled separately by initialize_placement.
    """
    result = copy.deepcopy(incoming)
    stored_item = items.get_item_by_name((stored or {}).get("itemName"))
    if stored and not _managed(stored_item) and _managed(items.get_item_by_name(incoming.get("itemName"))):
        raise ValueError("A construction snapshot cannot replace a different saved farm object.")
    if stored and _managed(stored_item):
        for field in _PROGRESS_FIELDS:
            if field in stored:
                result[field] = copy.deepcopy(stored[field])
            else:
                result.pop(field, None)
        if (_giving_building(stored_item) or _lootable_building(stored_item)
                or storage.orchard_container_class(stored_item) or storage.feature_container_class(stored_item)
                or not _built(stored, stored_item)
                or incoming.get("state") in ("construction", "constructing")):
            if "state" in stored:
                result["state"] = stored["state"]
    return result


def initialize_placement(snapshot):
    """Start new classic sites incomplete, ignoring optimistic client progress."""
    item = items.get_item_by_name(snapshot.get("itemName"))
    if not _managed(item):
        return snapshot
    result = copy.deepcopy(snapshot)
    result["className"] = item["className"]
    result.update(expansionLevel=_initial_level(item) if (storage.feature_container_class(item)
                  or _lootable_building(item) or storage.orchard_container_class(item)) else 1,
                  expansionParts={}, contents=[])
    result.pop("capacity", None)
    if item["name"] in _CLASSIC or item.get("className") == "HorseStableBuilding":
        result.update(isFullyBuilt=False, state="construction")
        # StorageBuilding.onBuilt -> addDefaultItems runs after TBuildingPlace
        # is constructed and emits no second transaction. Seed only catalog
        # defaults here so the saved and optimistic client counts agree.
        requirements = _initial_requirements(item)
        for row in _list(item.get("defaultItem")):
            if not isinstance(row, dict):
                raise ValueError("The building's default construction material is invalid.")
            material = items.get_item_by_name(row.get("name"))
            amount = _catalog_integer(row.get("amount"), "Default material quantity")
            if not material or material["code"] not in requirements or amount > requirements[material["code"]][1]:
                raise ValueError("The building's default material is not supported by its construction requirements.")
            result["contents"].append({"itemCode": material["code"], "numItem": amount})
    else:
        result.update(isFullyBuilt=True)
    return result


def _built(obj, item):
    if item["name"] in _CLASSIC:
        return False
    if item.get("className") == "HorseStableBuilding":
        return obj.get("isFullyBuilt") is True
    return obj.get("isFullyBuilt") is not False


def _requirements(rows, *, initial=False):
    result = {}
    for row in _list(rows):
        if not isinstance(row, dict) or (initial and row.get("part") not in (True, "true")):
            continue
        name = row.get("value" if initial else "name")
        item = items.get_item_by_name(name)
        if not item or not isinstance(item.get("code"), str):
            raise ValueError("A construction material is missing from the local catalog.")
        if item["code"] in result:
            raise ValueError("Construction material requirements must be unique.")
        result[item["code"]] = (item, _catalog_integer(row.get("need"), "Required material count"))
    if not result:
        raise ValueError("This building does not have supported material requirements.")
    return result


def _initial_requirements(item):
    if item.get("name") in ("xuk_sheep_pen", "xuk_sheep_pen_finished"):
        # The 2020 asset zeroed all three retired-site filters. Recover the
        # independently documented 2011 counts, shared with the client overlay.
        requirements = _requirements([
            {"name": name, "need": count}
            for name, count in england_progression.SHEEP_PEN_INITIAL_MATERIALS.items()
        ])
    else:
        config_name = (item.get("storageType") or {}).get("itemClass")
        requirements = _requirements(_storage_config().get(config_name, {}).get("itemName"), initial=True)
    if _catalog_integer(item.get("matsNeeded"), "Required construction total") != sum(count for _, count in requirements.values()):
        raise ValueError("The building's construction totals disagree with its material requirements.")
    return requirements


def _next_upgrade(obj, item):
    lootable = _lootable_building(item)
    orchard = storage.orchard_container_class(item)
    if (lootable or orchard) and ((obj.get("isFullyBuilt") is not None and obj.get("isFullyBuilt") is not True)
            or obj.get("state") in ("construction", "constructing")):
        raise ValueError("This finite feature must have its original completed building state.")
    if orchard:
        storage.orchard_capacity(obj, item)
    level = _integer(obj.get("expansionLevel", _initial_level(item)), "Building expansion level", 1)
    upgrades = item.get("upgrade")
    if (_giving_building(item) or lootable or orchard or storage.feature_container_class(item)
            or item.get("name") in ("xuk_sheep_pen_finished", "pigpenv2_finished", "herbgarden",
                            "bldg_irrigationwell", "bldg_irrigationwell_8hr")):
        if item["name"] == "herbgarden":
            import building_harvest
            if building_harvest._variant() not in (3, 4):
                raise ValueError("The original Herb Garden experiment is not enabled.")
        features = _list((item.get("features") or {}).get("feature"))
        expand = [feature for feature in features if isinstance(feature, dict)
                  and feature.get("name") == "expand" and feature.get("className") == "ExpandFManager"]
        if len(expand) != 1:
            raise ValueError("The original building expansion component is missing or ambiguous.")
        upgrades = expand[0].get("upgrade")
    upgrades = _list(upgrades)
    matches = [row for row in upgrades if isinstance(row, dict)
               and _catalog_integer(row.get("level"), "Catalog expansion level") == level + 1]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("The next building expansion is ambiguous.")
    upgrade = matches[0]
    # Other upgrade families can have currency, replacement items, awards or
    # region requirements. Only the original capacity + material shape is known.
    allowed = {"level", "capacity", "matsNeeded", "part"}
    if _giving_building(item):
        allowed.add("award")
        _expansion_gift_plan(upgrade)
    if lootable or orchard:
        if lootable and not _dynamic_parts_enabled():
            raise ValueError("The original finite-building dynamic part cohort is not enabled.")
        if "prereq" in upgrade or "prereqs" in upgrade:
            raise ValueError("This expansion's original region prerequisite is not restored.")
        allowed.add("rewardItem")
        if "rewardItem" in upgrade:
            _gift_plan(upgrade["rewardItem"], 1)
    if set(upgrade) - allowed:
        raise ValueError("This expansion needs a game feature that is not supported yet.")
    requirements = _requirements(upgrade.get("part"))
    # Dynamic part refactor32425 sums authored part.need; several archived
    # Lootable rows retain an empty or stale matsNeeded display total.
    if not lootable and _catalog_integer(upgrade.get("matsNeeded"), "Required expansion total") != sum(count for _, count in requirements.values()):
        raise ValueError("The expansion totals disagree with its material requirements.")
    return level + 1, _catalog_integer(upgrade.get("capacity"), "Expanded building capacity", minimum=0), requirements


def _gift_plan(name, amount, path=()):
    """Player.addGift4035 recursively unpacks itemPackage before storage."""
    if not isinstance(name, str) or not name or name in path:
        raise ValueError("The construction reward package is missing or cyclic.")
    amount = _integer(amount, "Construction gift quantity", 1)
    item = items.get_item_by_name(name)
    if not item:
        raise ValueError("The construction reward definition is unavailable.")
    if item.get("itemPackage"):
        result = {}
        for row in _list(item["itemPackage"]):
            if not isinstance(row, dict) or set(row) != {"value", "amount"}:
                raise ValueError("The construction reward package has unsupported contents.")
            quantity = _integer(amount * _catalog_integer(row.get("amount"), "Package gift quantity"),
                                "Expanded package gift quantity", 1)
            for leaf, count in _gift_plan(row.get("value"), quantity, (*path, name)).items():
                result[leaf] = _integer(result.get(leaf, 0) + count, "Combined package gift quantity", 1)
        return result
    # All 1111 recovered Giving Building leaf definitions use these ordinary
    # stored classes. Their ABC inheritance excludes AutoConsumable; bushel and
    # CSeedPackage addGift branches also need distinct inventory semantics.
    stored_classes = {"FestivalOfColorAnimal", "CTurbo", "Gnome", "RotateableDecoration", "ValentinesPresent",
                      "CHarvestTrees", "CHarvestAnimals", "BuildingPart", "CInstagrow", "CUnwither",
                      "COrganicFertilizer"}
    if (item.get("className") not in stored_classes and not (
            not item.get("className") and item.get("type") in ("animal", "decoration", "building", "tree"))):
        raise ValueError("This construction reward needs an unsupported automatic inventory effect.")
    if not isinstance(item.get("code"), str) or item["code"] == "XX":
        raise ValueError("The construction reward does not have a usable item code.")
    return {name: amount}


def _expansion_gift_plan(upgrade):
    award = upgrade.get("award")
    if (not isinstance(award, dict) or set(award) - {"name", "number", "dialog", "dialogBackground", "addToBuilding"}
            or award.get("addToBuilding", "false") not in (False, "false")):
        raise ValueError("The original construction award is not a supported Gift Box reward.")
    return _gift_plan(award.get("name"), _catalog_integer(award.get("number", "1"), "Construction award quantity"))


def _finish_expansion(save, obj, item, level, capacity):
    response = {}
    orchard = storage.orchard_container_class(item)
    if _giving_building(item) or _lootable_building(item) or orchard:
        features = _list(item["features"]["feature"])
        expand = next(row for row in features if row["className"] == "ExpandFManager")
        stage = next(row for row in _list(expand.get("upgrade"))
                     if _catalog_integer(row.get("level"), "Award expansion level") == level)
        if _giving_building(item):
            plan = _expansion_gift_plan(stage)
        else:
            name = stage.get("rewardItem")
            plan = _gift_plan(name, 1) if name else {}
            if name:
                # Lootable.onStoreComplete34258 passes an item NAME to addGift.
                response["completeRewardItem"] = name
        gifts = save["userInfo"]["player"].get("storageData", {}).get(str(storage.GIFTBOX_ID), {})
        if not isinstance(gifts, dict):
            raise ValueError("The saved construction gift inventory is invalid.")
        for name, count in plan.items():
            entry = gifts.get(items.get_item_by_name(name)["code"])
            if entry is not None:
                _entry(entry)
                _integer(entry[0] + count, "Resulting construction gift quantity")
        for name, count in plan.items():
            storage.store_deposit_item_by_name(save, name, count, storage.GIFTBOX_ID)
        # onStoreComplete45053 restores STATE_BUILT after the optimistic
        # completeExpansionLevel45045; it does not grant these awards again.
        obj["state"] = "built"
    if storage.feature_container_class(item):
        obj["state"] = "built"
    obj.update(expansionLevel=level, capacity=capacity)
    if orchard and level == 3 and item.get("finishedName"):
        target = items.get_item_by_name(item["finishedName"])
        if (not storage.orchard_container_class(target) or target.get("initialExpansionLevel") != "3"
                or storage.orchard_capacity({}, target) != capacity):
            raise ValueError("The original fully expanded Orchard target is unavailable.")
        # ExpandFManager45054 copies storage, itemOrder and plantTime. The
        # target's refreshPartData has no enabled next stage; copyParts11951
        # computes a zero transferable amount, so no old parts survive.
        obj.update(itemName=target["name"], className=target["className"],
                   isFullyBuilt=True, expansionParts={})
    return response


def _finish_initial(save, obj, item, *, now=None):
    """Apply the recovered finished identity and deterministic completion gift."""
    response = {}
    finished_name = _CLASSIC.get(item["name"])
    if finished_name:
        finished = items.get_item_by_name(finished_name)
        if not finished or not finished.get("className"):
            raise ValueError("The completed building definition is missing.")
        obj.update(itemName=finished_name, className=finished["className"])
        response["finishedName"] = finished_name
        if item["name"] in _FINISH_REWARDS:
            reward_name = _FINISH_REWARDS[item["name"]]
            if item.get("finishedReward") != reward_name or not items.get_item_by_name(reward_name):
                raise ValueError("The original construction completion gift is unavailable.")
            # transformBuilding15653 constructs the finished object anew;
            # SimpleHarvestableResource8384 initializes plantTime=worldTime.
            obj.update(expansionLevel=1,
                       capacity=_catalog_integer(finished.get("capacity"), "Finished building capacity"),
                       plantTime=_integer(engine.timestamp_now() if now is None else now,
                                          "Construction completion time", 1) * 1000)
            # grantFinishedReward15622 and giveFinishedReward54144 use an
            # item NAME. The durable gift must be deposited exactly once.
            storage.store_deposit_item_by_name(save, reward_name, group=storage.GIFTBOX_ID)
            response["gift"] = reward_name
    obj.update(isFullyBuilt=True, state="built")
    obj.setdefault("expansionLevel", 1)
    obj.setdefault("expansionParts", {})
    return response


def _entry(value):
    if (not isinstance(value, list) or len(value) < 3
            or not isinstance(value[1], list) or not isinstance(value[2], list)):
        raise ValueError("Material inventory metadata must contain quantity, sender IDs and extra data.")
    _integer(value[0], "Stored material quantity")
    return value


def _contents(save, obj):
    rows = obj.get("contents", [])
    if not isinstance(rows, list):
        raise ValueError("Building contents must be an array.")
    by_code = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("itemCode"), str) or row["itemCode"] in by_code:
            raise ValueError("Building content codes must be unique.")
        _integer(row.get("numItem"), "Contained material quantity")
        by_code[row["itemCode"]] = row
    data = save["userInfo"]["player"].setdefault("storageData", {})
    ledger = data.setdefault(str(obj["id"]), {})
    if not isinstance(ledger, dict):
        raise ValueError("The building's material ledger must be a map.")
    for code, entry in ledger.items():
        _entry(entry)
        if code in by_code and by_code[code]["numItem"] != entry[0]:
            raise ValueError("Building contents and material inventory disagree.")
        if code not in by_code:
            row = {"itemCode": code, "numItem": entry[0]}
            rows.append(row); by_code[code] = row
    for code, row in by_code.items():
        ledger.setdefault(code, [row["numItem"], [], []])
    obj["contents"] = rows
    return by_code, ledger


def _material(item):
    return bool(item and (item.get("className") in ("BuildingPart", "CVehiclePart")
                          or item.get("type") == "buildingpart"))


def _source(save, obj, material, quantity, options):
    """Remove actual units or charge the exact per-unit catalog purchase price."""
    code = material["code"]
    group = options.get("cameFromLocation", options.get("origin", 0))
    group = _integer(group, "Source storage ID", minimum=-2_147_483_647)
    flag = options.get("isGift", False)
    if flag not in (False, True, 0, 1):
        raise ValueError("The material gift flag is invalid.")
    if flag:
        group = storage.GIFTBOX_ID
    if group:
        if group == obj["id"]:
            raise ValueError("Materials cannot be withdrawn from their destination building.")
        if group not in (storage.GIFTBOX_ID, storage.active_inventory_id(save)):
            raise ValueError("Choose Gift Box or the active farm inventory as the material source.")
        entry = save["userInfo"]["player"].get("storageData", {}).get(str(group), {}).get(code)
        if entry is None or _entry(entry)[0] < quantity:
            raise ValueError("There are not enough materials in the selected source.")
        moved = copy.deepcopy(entry)
        moved[0] = quantity
        moved[1] = copy.deepcopy(entry[1] if entry[0] == quantity else entry[1][:1])
        # StorageItem.adjustQuantity trims only extras beyond the remaining
        # quantity. Sparse imported metadata stays with its surviving source;
        # copying a whole prefix here would duplicate that metadata.
        removed_extras = max(0, len(entry[2]) - (entry[0] - quantity))
        moved[2] = copy.deepcopy(entry[2][:removed_extras])
        metadata_index = _integer(options.get("giftMetadataIndex", -1), "Gift metadata index", minimum=-1)
        if metadata_index >= 0:
            if group != storage.GIFTBOX_ID or quantity != 1 or metadata_index >= len(entry[2]):
                raise ValueError("The selected material gift metadata is unavailable.")
            moved[2] = [copy.deepcopy(entry[2][metadata_index])]
        removed = (storage.remove_gift_by_code(save, code, quantity, metadata_index)
                   if group == storage.GIFTBOX_ID else
                   storage.store_withdraw_item_by_code(save, code, quantity, group))
        if not removed:
            raise ValueError("The selected construction materials are unavailable.")
        return moved
    resource = options.get("resource")
    if resource is not None:
        resource = _integer(resource, "Material resource ID", minimum=-2_147_483_647)
        source = next((row for row in save["world"]["objectsArray"] if row.get("id") == resource), None)
        if source and source.get("itemName") == material["name"] and not source.get("deleted"):
            if quantity != 1:
                raise ValueError("A placed material can only be used once.")
            save["world"]["objectsArray"].remove(source)
            return [1, [], [copy.deepcopy(source)]]
        if resource > 0 and not engine.world_object_id_is_temporary(resource):
            raise ValueError("The selected material is missing from the farm.")
    currency = options.get("currency") or material.get("market")
    if currency == "gold":
        currency = "coins"
    if currency not in ("coins", "cash"):
        raise ValueError("This material does not have a supported purchase currency.")
    price = engine.catalog_price(material, "cost" if currency == "coins" else "cash")
    if not price or price < 0:
        raise ValueError("This material does not have a positive catalog purchase price.")
    balance_key = "gold" if currency == "coins" else "cash"
    player = save["userInfo"]["player"]
    balance = _integer(player.get(balance_key), "Material purchase balance")
    total = _integer(price * quantity, "Material purchase cost", 1)
    if balance < total:
        raise ValueError(f"Not enough {currency} to buy these construction materials.")
    player[balance_key] = balance - total
    return [quantity, [], []]


def _apply(save, obj, item, snapshot, options, *, now=None):
    material = items.get_item_by_name(options.get("storedItemName"))
    if not material:
        raise ValueError("The construction material is unknown.")
    if options.get("storedItemCode", material["code"]) != material["code"]:
        raise ValueError("The construction material code does not match its name.")
    quantity = _integer(options.get("numToStore", 1), "Material quantity", 1, 100000)
    if options.get("target", obj["id"]) != obj["id"]:
        raise ValueError("The construction target does not match the farm building.")
    incoming_name = snapshot.get("itemName")
    if incoming_name != item["name"]:
        if _CLASSIC.get(incoming_name) == item["name"] and _built(obj, item):
            # A retried final material transaction still names the old site.
            return {"finishedName": item["name"]}
        raise ValueError("The construction target does not match the saved building.")
    initial = not _built(obj, item)
    if initial:
        requirements = _initial_requirements(item)
        rows, ledger = _contents(save, obj)
        counts = {code: ledger.get(code, [0])[0] for code in requirements}
        if any(row["numItem"] > 0 and code not in requirements for code, row in rows.items()):
            raise ValueError("Unload unsupported contents before completing this construction site.")
    else:
        upgrade = _next_upgrade(obj, item)
        if upgrade is None:
            raise ValueError("This building has no further supported material expansion.")
        level, capacity, requirements = upgrade
        parts = obj.setdefault("expansionParts", {})
        if not isinstance(parts, dict):
            raise ValueError("Building expansion parts must be a map.")
        counts = {code: _integer(parts.get(code, 0), "Collected expansion material quantity") for code in requirements}
    if material["code"] not in requirements:
        raise ValueError("That material is not required for this construction stage.")
    for code, (_, needed) in requirements.items():
        if counts[code] > needed:
            raise ValueError("The saved material count exceeds this construction stage's requirement.")
    code = material["code"]
    if counts[code] + quantity > requirements[code][1]:
        raise ValueError("That many materials would exceed this construction stage's requirement.")
    moved = _source(save, obj, material, quantity, options)
    counts[code] += quantity
    if initial:
        if code not in ledger:
            ledger[code] = moved
        else:
            entry = ledger[code]
            if len(moved) > 3:
                if len(entry) <= 3:
                    entry.extend(copy.deepcopy(moved[3:]))
                elif entry[3:] != moved[3:]:
                    raise ValueError("These material inventories carry different imported metadata; they cannot be merged safely.")
            entry[0] += quantity; entry[1].extend(moved[1]); entry[2].extend(moved[2])
        if code not in rows:
            row = {"itemCode": code, "numItem": counts[code]}
            obj["contents"].append(row); rows[code] = row
        rows[code]["numItem"] = counts[code]
        obj.update(isFullyBuilt=False, state="construction")
    else:
        parts[code] = counts[code]
    response = {}
    if all(counts[code] == needed for code, (_, needed) in requirements.items()):
        if initial:
            for code in requirements:
                rows[code]["numItem"] = 0
                ledger.pop(code, None)
            response = _finish_initial(save, obj, item, now=now)
        else:
            for code in requirements:
                parts.pop(code, None)
            response = _finish_expansion(save, obj, item, level, capacity)
    return response


def store_for_game(save, snapshot, options, now=None, request_id=None):
    """Handle a TStoreItem material action atomically; return None if unrelated.

    The original raw snapshot is used only for its target ID and old/new item
    identity. Progress, balances, contents and material counts come from save.
    A newly transformed Nursery/Pigpen starts its original finished clock;
    ordinary material expansions retain the saved harvest clock.
    """
    if not isinstance(snapshot, dict) or not isinstance(options, dict):
        raise ValueError("Construction storage needs a building and options map.")
    ident = _integer(snapshot.get("id"), "Construction building ID")
    objects = save["world"]["objectsArray"]
    matches = [row for row in objects if isinstance(row, dict) and row.get("id") == ident and not row.get("deleted")]
    if len(matches) > 1:
        raise ValueError("Construction building IDs must be unique.")
    obj = matches[0] if matches else None
    item = items.get_item_by_name((obj or {}).get("itemName"))
    incoming_item = items.get_item_by_name(snapshot.get("itemName"))
    if not _managed(item):
        if _managed(incoming_item):
            raise ValueError("The construction building is missing from the farm.")
        return None
    options = {key: value for key, value in options.items()
               if value is not None and not isinstance(value, pyamf.UndefinedType)}
    material = items.get_item_by_name(options.get("storedItemName"))
    if _built(obj, item) and not _material(material):
        return None
    key, signature, history = None, None, {}
    # Nursery/Pigpen initial sites become classic containers on completion.
    # Receipt the first accepted material action while its old site identity
    # is still authoritative; waiting for the finished container would create
    # a new receipt only when that same original request is retried.
    initial_reward_container = item.get("name") in _CLASSIC and item.get("name") in _FINISH_REWARDS
    if request_id is not None and (initial_reward_container
                                  or _lootable_building(item) or storage._container_class(item)):
        key = str(_integer(request_id, "Finite construction request sequence"))
        def encode(value):
            if isinstance(value, pyamf.UndefinedType):
                return None
            raise ValueError("The finite construction request contains an unsupported value.")
        signature = json.dumps([save.get("userInfo", {}).get("currentWorldType") or "farm",
                                snapshot, options], sort_keys=True, default=encode)
        history = save.get(REQUESTS_KEY, {})
        if not isinstance(history, dict) or not isinstance(history.get("receipts", {}), dict):
            raise ValueError("The saved finite construction retry history is invalid.")
        receipt = history.get("receipts", {}).get(key)
        if receipt is not None:
            if (not isinstance(receipt, dict) or receipt.get("signature") != signature
                    or not isinstance(receipt.get("response"), dict)):
                raise ValueError("A finite construction sequence was reused for another action.")
            response = copy.deepcopy(receipt["response"])
            save["_constructionResponse"] = copy.deepcopy(response)
            return response
        if int(key) <= _integer(history.get("highestSequence", -1), "Saved finite construction sequence", -1):
            raise ValueError("This finite construction request is older than its retained history.")
    detached = copy.deepcopy(save)
    target = next(row for row in detached["world"]["objectsArray"] if row.get("id") == ident)
    response = _apply(detached, target, item, snapshot, options, now=now)
    if key is not None:
        history = detached.setdefault(REQUESTS_KEY, {})
        receipts = history.setdefault("receipts", {})
        receipts[key] = {"signature": signature, "response": copy.deepcopy(response)}
        history["highestSequence"] = int(key)
        while len(receipts) > 256:
            del receipts[next(iter(receipts))]
    detached["_constructionResponse"] = copy.deepcopy(response)
    save.clear(); save.update(detached)
    return response


def take_response(save):
    """Drain only the current action's transient TStoreItem callback data."""
    return save.pop("_constructionResponse", {})


def start_session(save):
    save.pop(REQUESTS_KEY, None)
