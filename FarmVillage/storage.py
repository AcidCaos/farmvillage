import copy
from functools import lru_cache
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import zlib

import pyamf

from items import get_item_by_name, get_item_by_code, get_items

# client ref.: src/Classes/storage/StorageItem.as
ITEM_KEY_DELIMITER:str = ":"
METADATA_INDEX_QUANTITY:int = 0
METADATA_INDEX_SENDER_IDS:int = 1
METADATA_INDEX_EXTRADATA:int = 2
REQUESTS_KEY = "_storageRequests"

# client ref.: src/Classes/FarmGameWorld.as
GIFTBOX_ID:int = -1 
CONSUME_ID:int = -6
# client ref.: src/Classes/Player.as
HOME_INVENTORY_ID:int = -2
ENGLAND_INVENTORY_ID:int = -8
FISHERMAN_INVENTORY_ID:int = -9
WINTER_WONDERLAND_INVENTORY_ID:int = -10
HAWAII_INVENTORY_ID:int = -11
HALLOW_INVENTORY_ID:int = -14
ASIA_INVENTORY_ID:int = -13
ANGLER_INVENTORY_ID:int = -17
HTOWN_INVENTORY_ID:int = -15
MEADOWS_INVENTORY_ID:int = -16
GLEN_INVENTORY_ID:int = -18
ATLANTIS_INVENTORY_ID:int = -19
GARDEN_INVENTORY_ID:int = -20
AUSTRALIA_INVENTORY_ID:int = -21
SPACE_INVENTORY_ID:int = -22
CANDY_INVENTORY_ID:int = -23
FFOREST_INVENTORY_ID:int = -24
HLIGHTS_INVENTORY_ID:int = -25
RAINFOREST_INVENTORY_ID:int = -26
OZ_INVENTORY_ID:int = -28
VILLAGE_INVENTORY_ID:int = -27
MEDITERRANEAN_INVENTORY_ID:int = -29
OASIS_INVENTORY_ID:int = -31
STORYBOOK_INVENTORY_ID:int = -32
SLEEPYHOLLOW_INVENTORY_ID:int = -33
EASTEROS_INVENTORY_ID:int = -35
TOYLAND_INVENTORY_ID:int = -34
AVALON_INVENTORY_ID:int = -35
WILDWEST_INVENTORY_ID:int = -36
TREASURETIDES_INVENTORY_ID:int = -37
AFRICA_INVENTORY_ID:int = -38
TRANSYLVANIA_INVENTORY_ID:int = -39
WINTER_INVENTORY_ID:int = -40
JAPAN_INVENTORY_ID:int = -42
INDIA_INVENTORY_ID:int = -41
JUNGLE_INVENTORY_ID:int = -43
MOUNT_INVENTORY_ID:int = -44
LIMBO_INVENTORY_ID:int = -45
XMAS_INVENTORY_ID:int = -46
MIDWEST_INVENTORY_ID:int = -47
TURTLEISLAND_INVENTORY_ID:int = -49
UNDERWATER_INVENTORY_ID:int = -48
DREAMWORLD_INVENTORY_ID:int = -50
BRAZIL_INVENTORY_ID:int = -52

_INVENTORY_ID_NAME_MAP = {globals()[name]: name for name in globals().keys() if name.endswith("_INVENTORY_ID") or name == "GIFTBOX_ID"}
def get_inventory_group_name_by_id(inventory_id) -> str:
    n = _INVENTORY_ID_NAME_MAP.get(inventory_id)
    if not n:
        return None
    return n.replace("_ID", "").replace("_", " ")



def _guard_active_world(save):
    from world_travel import guard_active_world
    return guard_active_world(save)


def active_inventory_id(save):
    """The owned farm inventory used by the original material dialogs."""
    from world_travel import supported_worlds
    world = _guard_active_world(save)
    user = save["userInfo"]
    fallback = supported_worlds()[world]
    return user.get("worldSummaryData", {}).get(world, {}).get("storageId", fallback)


def _capacity_integer(value, *, catalog=False):
    if catalog and isinstance(value, str) and value.isascii() and value.isdigit():
        value = int(value)
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or int(value) != value or not 0 <= value <= 2_147_483_647):
        raise ValueError("The imported inventory capacity or quantity is invalid.")
    return int(value)


_FEATURE_CONTAINER_CLASSES = frozenset(("gnomegarden", "xas_gnomegarden",
    "masterybillboardanimal", "masterybillboardcrop", "masterybillboardgardenflower",
    "masterybillboardrecipe", "masterybillboardtree"))

# Completed original Home habitats. Storage is independent of their unrecovered
# random breeding/harvest rewards; no regional variant is admitted by class alone.
_HOME_HABITATS = {
    "animal_breeding_aviary_finished": "animal_aviary",
    "animal_breeding_dairy_finished": "animal_dairy_pen",
    "animal_breeding_horsepaddock_finished": "animal_horsepaddock",
    "animal_breeding_livestock_finished": "animal_livestock_pen",
    "animal_breeding_petrun_finished": "animal_petrun",
    "animal_breeding_wildlife_finished": "animal_wildlife_pen",
    "animal_breeding_zoo_finished": "animal_zoo_pen",
}


def home_habitat_container_class(item):
    """Exact seven completed Home owners with the recovered storage component."""
    if not isinstance(item, dict):
        return None
    storage_class = _HOME_HABITATS.get(item.get("name"))
    if (not storage_class or item.get("className") != "FeatureBuilding"
            or item.get("type") != "building" or item.get("finishedName")
            or (item.get("storageType") or {}).get("itemClass") != storage_class
            or item.get("capacity") != "20" or item.get("initialExpansionLevel") != "1"
            or item.get("growTime") != "1" or item.get("stuffingPrevention") != "true"
            or item.get("stuffingPreventionPrereq")):
        return None
    features = _list((item.get("features") or {}).get("feature"))
    storage = [row for row in features if isinstance(row, dict)
               and row.get("className") == "StorageFManager"]
    expand = [row for row in features if isinstance(row, dict)
              and row.get("className") == "ExpandFManager"]
    harvest = [row for row in features if isinstance(row, dict)
               and row.get("className") == "AnimalBreedingHarvestFManager"]
    return storage_class if (storage == [{"name": "storage", "className": "StorageFManager",
        "capacity": "0", "storageSize": "1"}] and len(expand) == len(harvest) == 1) else None
# Exact classic occupant identities; this grants no additional world access.
_CLASSIC_CONTAINERS = {
    "horsestablewhite": ("HorseStableBuilding", "horses"),
    "xukhorsestable": ("HorseStableBuilding", "horses"),
    "xukhorsestable_finished": ("HorseStableBuildingFinished", "horses"),
    "nurserybarn_finished": ("NurseryBuilding", "nurserybarn"),
    "nurserybarn_finished_complete": ("NurseryBuildingFinished", "nurserybarn"),
    "pigpen_finished": ("PigpenBuilding", "pigpen"),
    "pigpenv2_finished": ("FeatureBuilding", "pigpenv2"),
}


def _classic_container_class(item):
    if not isinstance(item, dict):
        return None
    spec = _CLASSIC_CONTAINERS.get(item.get("name"))
    if (spec and item.get("className") == spec[0]
            and (item.get("storageType") or {}).get("itemClass") == spec[1]):
        return spec[1]
    return None


def _list(value):
    return value if isinstance(value, list) else ([] if value is None else [value])


def feature_container_class(item):
    """Recognize the 71 recovered completed gnome/mastery FeatureBuildings.

    This pure catalog predicate admits no other StorageFManager family. The
    ordinary 66 have authored material expansions; the five 5000-slot cash
    billboards have no authored expansion stages and are storage-only.
    """
    if not isinstance(item, dict) or item.get("className") != "FeatureBuilding" or item.get("type") != "building":
        return None
    storage_class = (item.get("storageType") or {}).get("itemClass")
    if storage_class not in _FEATURE_CONTAINER_CLASSES or item.get("finishedName"):
        return None
    features = _list((item.get("features") or {}).get("feature"))
    storage = [row for row in features if isinstance(row, dict)
               and row.get("name") == "storage" and row.get("className") == "StorageFManager"]
    expand = [row for row in features if isinstance(row, dict) and row.get("className") == "ExpandFManager"]
    if len(storage) != 1:
        return None
    ordinary = (item.get("capacity") == "10" and item.get("initialExpansionLevel") == "1"
                and len(expand) == 1 and expand[0].get("name") == "expand"
                and bool(expand[0].get("upgrade")))
    complete_cash = (storage_class not in ("gnomegarden", "xas_gnomegarden")
                     and item.get("capacity") == "5000" and len(expand) == 1
                     and expand[0].get("name") == "expand" and not expand[0].get("upgrade")
                     and item.get("initialExpansionLevel") is None)
    return storage_class if ordinary or complete_cash else None


def orchard_container_class(item):
    """The completed regional OrchardFeatureBuildings and their shared target."""
    if (not isinstance(item, dict) or item.get("className") != "OrchardFeatureBuilding"
            or item.get("type") != "building"
            or (item.get("storageType") or {}).get("itemClass") != "orchard"):
        return None
    features = _list((item.get("features") or {}).get("feature"))
    classes = {row.get("className") for row in features if isinstance(row, dict)}
    if len(features) != 5 or classes != {
            "ExpandFManager", "OrchardFeatureBuildingExpandIndicatorFManager",
            "StorageFManager", "HarvestFManager", "ContextMenuFManager"}:
        return None
    if any("prereq" in row or "prereqs" in row for row in features):
        return None
    storage = next(row for row in features if row["className"] == "StorageFManager")
    harvester = next(row for row in features if row["className"] == "HarvestFManager")
    expand = next(row for row in features if row["className"] == "ExpandFManager")
    if (storage != {"name": "storage", "className": "StorageFManager", "capacity": "0", "storageSize": "1"}
            or harvester.get("rewardType") != "HarvestRewardGenerator"
            or harvester.get("needItemsForHarvest") != "true"
            or expand.get("name") != "expand"
            or set(expand) - {"name", "className", "friendRewards", "upgrade", "infiniteUpgradeData"}):
        return None
    regional = (item.get("finishedName") == "superorchard_featurebuilding"
                and item.get("capacity") == "20" and item.get("initialExpansionLevel") is None
                and "infiniteUpgradeData" not in expand)
    target = (item.get("name") == "superorchard_featurebuilding" and not item.get("finishedName")
              and item.get("capacity") == "40" and item.get("initialExpansionLevel") == "3")
    return "orchard" if item.get("storageSize") == "1" and (regional or target) else None


def _container_class(item):
    return feature_container_class(item) or orchard_container_class(item) or home_habitat_container_class(item) or _classic_container_class(item)


@lru_cache(maxsize=1)
def _home_habitat_storage_filters():
    from bundle import XML_DIR
    raw = zlib.decompress((Path(XML_DIR) / "gz/v855098/storageConfig.amf.gz").read_bytes())
    rows = pyamf.get_decoder(pyamf.AMF3, raw).readElement()["storage"]["StorageBuilding"]
    result = {}
    for row in rows:
        if row.get("name") in _HOME_HABITATS.values():
            if (row["name"] in result or set(row) != {"name", "itemName", "metadata"}
                    or row.get("metadata") != {"type": "indexed", "storableValue": {
                        "type": "int", "name": "amount", "index": "0"}}
                    or not isinstance(row.get("itemName"), list)
                    or not all(isinstance(name, str) or (isinstance(name, dict)
                        and set(name) == {"part", "need", "value"} and name.get("part") == "true")
                        for name in row["itemName"])):
                raise ValueError("The original Home habitat storage filter is unavailable.")
            # Part rows belong to construction/expansion, not animal contents.
            result[row["name"]] = frozenset(name for name in row["itemName"] if isinstance(name, str))
    if set(result) != set(_HOME_HABITATS.values()):
        raise ValueError("The original Home habitat storage filters are unavailable.")
    return result


@lru_cache(maxsize=1)
def _orchard_storage_filter():
    from bundle import XML_DIR
    raw = zlib.decompress((Path(XML_DIR) / "gz/v855098/storageConfig.amf.gz").read_bytes())
    records = pyamf.get_decoder(pyamf.AMF3, raw).readElement()["storage"]["StorageBuilding"]
    rows = [row for row in records if row.get("name") == "orchard"]
    if (len(rows) != 1 or rows[0].get("allowedClass") != {"type": "Tree"}
            or rows[0].get("denyKeyword") != "noOrchard"):
        raise ValueError("The original Orchard storage filter is unavailable.")
    return rows[0]


def orchard_accepts(item):
    """StorageFilter15324 admits Tree subclasses, then denies noOrchard."""
    if not isinstance(item, dict):
        return False
    config = _orchard_storage_filter()
    # The preserved client has one Tree subclass, MystreeSapling. An omitted
    # class on a tree catalog item resolves to Tree through FarmItem.
    tree = (item.get("className") in ("Tree", "MystreeSapling")
            or not item.get("className") and item.get("type") == "tree")
    return tree and config["denyKeyword"] not in _list(item.get("keyword"))


def orchard_capacity(owner, item):
    """Read an Orchard's authored current capacity, including target level 3."""
    if not orchard_container_class(item):
        raise ValueError("This item is not a recovered Orchard container.")
    return _container_capacity(owner, item)


@lru_cache(maxsize=1)
def _feature_storage_filters():
    from bundle import XML_DIR
    raw = zlib.decompress((Path(XML_DIR) / "gz/v855098/storageConfig.amf.gz").read_bytes())
    records = pyamf.get_decoder(pyamf.AMF3, raw).readElement()["storage"]["StorageBuilding"]
    result = {}
    for row in records:
        if row.get("name") in _FEATURE_CONTAINER_CLASSES | {spec[1] for spec in _CLASSIC_CONTAINERS.values()}:
            if row["name"] in result:
                raise ValueError("The original feature storage filter is ambiguous.")
            result[row["name"]] = row
    if set(result) != _FEATURE_CONTAINER_CLASSES | {spec[1] for spec in _CLASSIC_CONTAINERS.values()}:
        raise ValueError("The original feature storage filters are unavailable.")
    return result


_mastery_catalog = None
_mastery_sources = {}


def _mastery_sign_sources():
    # addMarketConfigInfo (3202) reverses the LAST masteryLevel.gift only.
    # Keep the cache tied to the complete in-memory catalog, including derived
    # heritage signs; a catalog replacement must not retain stale ownership.
    global _mastery_catalog, _mastery_sources
    records = get_items()
    if records is not _mastery_catalog:
        result = {}
        for item in records:
            levels = _list(item.get("masteryLevel"))
            if item.get("mastery") in (True, "true") and levels and isinstance(levels[-1], dict):
                gift = levels[-1].get("gift")
                if isinstance(gift, str) and gift:
                    result[gift] = item.get("type")
        _mastery_catalog, _mastery_sources = records, result
    return _mastery_sources


@lru_cache(maxsize=1)
def _recipe_mastery_signs():
    from bundle import XML_DIR
    root = Path(XML_DIR) / "gz/v855098"
    crafting = ET.fromstring(zlib.decompress((root / "crafting.xml.gz").read_bytes()))
    # isValidRecipe (5198) requires id, craft and Ingredients, not our smaller
    # production allowlist. Storing an earned sign unlocks no recipe service.
    signs = {row.find("Mastery").get("sign") for row in crafting.find("recipes")
             if row.get("id") is not None and row.find("craft") is not None
             and row.find("Ingredients") is not None and row.find("Mastery") is not None}
    cms = ET.fromstring(zlib.decompress((root / "gameSettingsCMS.xml.gz").read_bytes()))
    names = {row.get("name") for feature in cms.findall("featureConfig/feature")
             if feature.get("name") == "FeatureCrafting"
             for row in feature.findall("craftingSystem/recipes/recipe")}
    return signs - {None, ""}, names - {None, ""}


def _feature_accepts(storage_class, item):
    if storage_class == "orchard":
        return orchard_accepts(item)
    if storage_class in _HOME_HABITATS.values():
        # Mutable animals have their own DNA/name/reservation transaction. Do
        # not silently turn their metadata into an ordinary anonymous animal.
        return (item.get("className") in (None, "Animal") and item.get("type") == "animal"
                and item.get("name") in _home_habitat_storage_filters()[storage_class])
    config = _feature_storage_filters()[storage_class]
    if storage_class in {spec[1] for spec in _CLASSIC_CONTAINERS.values()}:
        # StorageFilter.canTake15324: keywords, keyword denial, explicit names.
        # Indexed construction-part rows are not animal occupants.
        keywords = _list(item.get("keyword"))
        accepted = any(word in keywords for word in _list(config.get("allowKeyword")))
        if accepted and any(word in keywords for word in _list(config.get("denyKeyword"))):
            accepted = False
        return accepted or item.get("name") in [row for row in _list(config.get("itemName"))
                                               if isinstance(row, str)]
    if config.get("storageFilterClass") == "MasterySignStorageFilter":
        types = _list(config.get("masterySignType"))
        if "recipe" in types:
            signs, recipes = _recipe_mastery_signs()
            if item.get("code") in signs:
                return True
        owner_type = _mastery_sign_sources().get(item["name"])
        if owner_type is not None:
            if owner_type in types:
                return True
        elif (owner := get_item_by_code(item.get("masteredItemCode"))) and owner.get("type") in types:
            return True
        if "recipe" in types:
            name = item["name"]
            recipe = name.split("_")[1] if name.find("_") > 0 else (
                name[6:] if name.startswith("master") else None)
            return recipe in _recipe_mastery_signs()[1]
        return False
    classes = _list(config.get("allowedClass"))
    for row in classes:
        if row.get("allowSubclass") not in (False, "false") or row.get("experiment"):
            raise ValueError("This feature storage class needs an unsupported filter.")
    return (any(item.get("className") == row.get("type") for row in classes)
            or item.get("name") in [row for row in _list(config.get("itemName")) if isinstance(row, str)])


def feature_container_initial_level(item):
    """StorageBuilding.getInitialExpansionLevelFromItem uses both source fields."""
    if not feature_container_class(item):
        raise ValueError("This item is not a recovered feature container.")
    return max(1, _capacity_integer(item.get("initialExpansionLevel", "0"), catalog=True),
               _capacity_integer(item.get("storageSize", "0"), catalog=True))


def _feature_capacity(owner, item):
    feature_container_initial_level(item)
    return _container_capacity(owner, item)


def _container_capacity(owner, item):
    if _classic_container_class(item):
        initial = max(1, _capacity_integer(item.get("storageSize", "1"), catalog=True))
        level = _capacity_integer(owner.get("expansionLevel", initial))
        if level == initial:
            return _capacity_integer(item.get("capacity"), catalog=True)
        stages = [row for row in _list(item.get("upgrade")) if isinstance(row, dict)
                  and _capacity_integer(row.get("level"), catalog=True) == level]
        if len(stages) != 1:
            raise ValueError("The saved classic container expansion level is invalid.")
        return _capacity_integer(stages[0].get("capacity"), catalog=True)
    initial = max(1, _capacity_integer(item.get("initialExpansionLevel", "0"), catalog=True),
                  _capacity_integer(item.get("storageSize", "0"), catalog=True))
    level = _capacity_integer(owner.get("expansionLevel", initial))
    if level == initial:
        return _capacity_integer(item.get("capacity"), catalog=True)
    expand = [row for row in _list((item.get("features") or {}).get("feature"))
              if isinstance(row, dict) and row.get("className") == "ExpandFManager"]
    stages = [row for component in expand for row in _list(component.get("upgrade"))
              if isinstance(row, dict) and _capacity_integer(row.get("level"), catalog=True) == level]
    if level < 1 or len(stages) != 1:
        raise ValueError("The saved feature container expansion level is invalid.")
    return _capacity_integer(stages[0].get("capacity"), catalog=True)


def _feature_request(save, snapshot, options):
    destination = _storage_group(options.get("target", snapshot.get("id", 0)))
    return destination > 0 and (_container_class(get_item_by_name(snapshot.get("itemName")))
        or any(obj.get("id") == destination and _container_class(get_item_by_name(obj.get("itemName")))
               for obj in save["world"]["objectsArray"]))


def _feature_owner(save, destination, snapshot=None):
    owners = [obj for obj in save["world"]["objectsArray"] if obj.get("id") == destination]
    recognized = [obj for obj in owners if _container_class(get_item_by_name(obj.get("itemName")))]
    if not recognized and not _container_class(get_item_by_name((snapshot or {}).get("itemName"))):
        return None
    if len(owners) != 1 or len(recognized) != 1:
        raise ValueError("The feature container must have one owned current-world identity.")
    from world_travel import guard_action_object
    guard_action_object(save, destination)
    owner = owners[0]
    catalog = get_item_by_name(owner.get("itemName"))
    storage_class = _container_class(catalog)
    _capacity_integer(owner.get("id"))
    if snapshot is not None:
        _capacity_integer(snapshot.get("id"))
    if (owner.get("deleted") or owner.get("className") != catalog["className"]
            or (snapshot is not None and any(snapshot.get(field) != owner.get(field)
                                             for field in ("id", "itemName", "className")))):
        raise ValueError("The feature container does not match the saved owner.")
    images = {row.get("name") for row in _list(catalog.get("image")) if isinstance(row, dict)
              and str(row.get("name", "")).startswith("built_")}
    states = {"built", *images}
    if storage_class == "orchard" or home_habitat_container_class(catalog) or _classic_container_class(catalog):
        # StorageBuilding's ABC default is true; loaded Feature Orchards may
        # omit isFullyBuilt and legitimately be bare or ripe.
        states.update(("bare", "ripe"))
        order = owner.get("itemOrder", [])
        if storage_class == "orchard" and (not isinstance(order, list) or any(not isinstance(code, str) for code in order)):
            raise ValueError("The imported Orchard tree order is invalid.")
        if owner.get("state") not in states:
            raise ValueError("The saved Orchard state is invalid.")
    if ((owner.get("isFullyBuilt") is not None and owner.get("isFullyBuilt") is not True)
            or owner.get("state") in ("construction", "constructing")
            or (owner.get("isFullyBuilt") is None and owner.get("state") not in states)):
        raise ValueError("Finish the feature container before storing an item.")
    return owner, catalog, storage_class


def _home_habitat_store_clock(owner, item):
    """HarvestableStorageBuilding12064's exact 4% anti-stuffing adjustment.

    StorageFManager45154 increments count before FeatureBuilding22304 calls
    updatePlantTimeOnStore, so even the first occupant follows the nonempty
    branch. This changes no grow duration and grants no harvest reward.
    """
    from engine import timestamp_now
    from peaceful import grow_seconds
    now = timestamp_now() * 1000
    planted = owner.get("plantTime")
    grow = grow_seconds(item)
    if (isinstance(planted, bool) or not isinstance(planted, (int, float))
            or not math.isfinite(planted) or not 0 <= planted <= now or grow is None):
        raise ValueError("The saved Home habitat growth clock is invalid.")
    duration = grow * 1000
    penalty = math.floor(duration * 0.04 + 0.5)  # AS3 Math.round, milliseconds.
    # FeatureBuilding.addItemHelper22304 calls this once AFTER StorageFManager's
    # quantity loop, so one TStoreItem incurs one penalty even for several units.
    return min(now, (now - duration if now - planted >= duration else planted) + penalty)


def preserve_container_fields(stored, incoming):
    """A Home habitat snapshot cannot replace saved identity, contents or clocks."""
    catalog = get_item_by_name((stored or {}).get("itemName"))
    if not home_habitat_container_class(catalog):
        if stored and home_habitat_container_class(get_item_by_name(incoming.get("itemName"))):
            raise ValueError("A Home habitat snapshot cannot replace a different saved object.")
        return incoming
    if any(incoming.get(field) != stored.get(field) for field in ("id", "itemName", "className")):
        raise ValueError("A Home habitat action cannot replace its saved identity.")
    result = dict(incoming)
    for field in ("isFullyBuilt", "expansionLevel", "expansionParts", "capacity", "contents",
                  "plantTime", "storageMetadata", "extraDataState", "itemOrder", "featureProps", "state"):
        if field in stored:
            result[field] = copy.deepcopy(stored[field])
        else:
            result.pop(field, None)
    return result


def initialize_container_placement(snapshot, *, now):
    """Start a newly placed completed Home habitat at its authored first stage."""
    item = get_item_by_name(snapshot.get("itemName"))
    if not home_habitat_container_class(item):
        return snapshot
    now = _capacity_integer(now)
    result = copy.deepcopy(snapshot)
    result.update(itemName=item["name"], className=item["className"], state="built",
                  isFullyBuilt=True, expansionLevel=1, expansionParts={}, capacity=20,
                  contents=[], storageMetadata={}, plantTime=now * 1000)
    for field in ("extraDataState", "itemOrder", "featureProps"):
        result.pop(field, None)
    return result


def _guard_feature_deposit(save, snapshot, destination, item, quantity):
    if destination <= 0:
        return False
    owned = _feature_owner(save, destination, snapshot)
    if owned is None:
        return False
    owner, catalog, storage_class = owned
    if home_habitat_container_class(catalog):
        from creative_worlds import world_requirement_matches
        if not world_requirement_matches(catalog, _guard_active_world(save)):
            raise ValueError("This original habitat is not eligible on the current farm.")
    if not _feature_accepts(storage_class, item):
        raise ValueError("This item is incompatible with the original feature storage filter.")
    contents = owner.get("contents", [])
    if contents == {}:
        contents = []
    if not isinstance(contents, list):
        raise ValueError("The imported feature container contents are invalid.")
    counts = {}
    for row in contents:
        if not isinstance(row, dict) or not isinstance(row.get("itemCode"), str) or row["itemCode"] in counts:
            raise ValueError("The imported feature container contents are ambiguous.")
        counts[row["itemCode"]] = _capacity_integer(row.get("numItem"))
    ledger = save["userInfo"]["player"]["storageData"].get(str(destination))
    if ledger is not None:
        if not isinstance(ledger, dict):
            raise ValueError("The imported feature container ledger is invalid.")
        ledger_counts = {}
        for code, entry in ledger.items():
            if not isinstance(entry, list) or len(entry) < 3 or not isinstance(entry[1], list) or not isinstance(entry[2], list):
                raise ValueError("The imported feature container ledger is invalid.")
            ledger_counts[code] = _capacity_integer(entry[0])
        if ledger_counts != counts:
            raise ValueError("The imported feature container ledger disagrees with its contents.")
    if sum(counts.values()) + quantity > _container_capacity(owner, catalog):
        raise ValueError("The feature container does not have enough storage space.")
    return True


def _orchard_store_state(save, owner, item):
    """Feature.addItemHelper updates the clock AFTER the count increases."""
    from engine import timestamp_now
    from peaceful import grow_seconds
    now = timestamp_now() * 1000
    planted = owner.get("plantTime")
    grow = grow_seconds(item)
    if (isinstance(planted, bool) or not isinstance(planted, (int, float))
            or not math.isfinite(planted) or not 0 <= planted <= now or grow is None):
        raise ValueError("The saved Orchard growth clock is invalid.")
    if item.get("stuffingPrevention") in (True, "true"):
        # The only authored conditional rule is location_hawaii. Hawaii is
        # globally unsupported; do not turn that adjustment on elsewhere.
        if item.get("stuffingPreventionPrereq") != "location_hawaii":
            raise ValueError("This Orchard has an unsupported stuffing-prevention rule.")
        if save["userInfo"].get("currentWorldType") == "hawaii":
            raise ValueError("The Hawaii Orchard stuffing-prevention rule is not restored.")
    # StorageFManager45154 increments count before Feature.addItemHelper22304
    # calls updatePlantTimeOnStore. The empty-container clock branch therefore
    # does not run for Feature Orchards. Preserve the saved clock even for the
    # first incoming tree; Orchard25687 only recomputes bare/ripe state here.
    return "ripe" if now - planted >= grow * 1000 else "bare"


def _storage_group(value):
    if isinstance(value, str) and value.lstrip("-").isascii() and value.lstrip("-").isdigit():
        value = int(value)
    if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            or int(value) != value or not -2_147_483_648 <= value <= 2_147_483_647):
        raise ValueError("A storage source or target must be a signed whole ID.")
    return int(value)


@lru_cache(maxsize=1)
def _inventory_limits():
    # StorageConfigSettings.getMaxInventoryCapById reads StorageEntity.limit.
    # Recover every direct Inventory subclass from the original source. The
    # ceiling grants no slots, and admission below still requires an activated
    # world's exact inventory ID plus fully built ordinary storage buildings.
    from bundle import XML_DIR
    raw = zlib.decompress((Path(XML_DIR) / "gz/v855098/storageConfig.amf.gz").read_bytes())
    rows = pyamf.get_decoder(pyamf.AMF3, raw).readElement()["storage"]["StorageEntity"]
    bases = [row for row in rows if row.get("name") == "Inventory" and row.get("id") == "-2"]
    if len(bases) != 1:
        raise ValueError("The original inventory capacity rules are unavailable.")
    limit = _capacity_integer(bases[0].get("limit"), catalog=True)
    limits = {HOME_INVENTORY_ID: limit}
    for row in rows:
        if row.get("extends") != "Inventory":
            continue
        ident = row.get("id")
        if (not isinstance(ident, str) or not ident.startswith("-")
                or not ident[1:].isascii() or not ident[1:].isdigit()
                or row.get("loc") != "player"):
            raise ValueError("The original inventory capacity rules are unavailable.")
        ident = -_capacity_integer(ident[1:], catalog=True)
        if ident == 0 or ident in limits:
            raise ValueError("The original inventory capacity rules are unavailable.")
        limits[ident] = _capacity_integer(row.get("limit", limit), catalog=True)
    return limits


def _guard_inventory_deposit(save, destination, quantity, removed_object_id=None):
    """Admit only capacity proved by built ordinary storage on the active farm.

    Player.as 1325-1390 sums StorageBuilding.capacity for isInventoryBuilding(),
    clamps to StorageEntity.limit, and compares the sum of stored quantities.
    StorageBuilding.as 1863-1873 selects an inline upgrade by expansionLevel.
    InventoryCellar overrides capacity with min(base, credits received): its
    1250 catalog value alone never proves any available slots. Unsupported or
    ambiguous imports contribute no capacity and are preserved on rejection.
    Specialized positive building containers retain their own admission rules.
    """
    if destination > 0:
        return
    from world_travel import supported_worlds
    canonical_inventory = supported_worlds()[_guard_active_world(save)]
    if (destination != canonical_inventory or destination != active_inventory_id(save)
            or destination not in _inventory_limits()):
        raise ValueError("Only the active farm inventory can receive this item.")
    ledger = save["userInfo"]["player"]["storageData"].get(str(destination), {})
    if not isinstance(ledger, dict):
        raise ValueError("The imported inventory contents are invalid.")
    usage = 0
    for entry in ledger.values():
        if not isinstance(entry, list) or len(entry) < 3:
            raise ValueError("The imported inventory contents are invalid.")
        usage += _capacity_integer(entry[METADATA_INDEX_QUANTITY])
    capacity = 0
    unsupported = False
    for obj in save["world"]["objectsArray"]:
        if obj.get("deleted") or obj.get("id") == removed_object_id:
            continue
        item = get_item_by_name(obj.get("itemName"))
        if item is None:
            unsupported |= obj.get("className") in ("StorageBuilding", "InventoryCellar")
            continue
        if (item.get("storageType") or {}).get("itemClass") != "Inventory":
            continue
        if item.get("className") == "InventoryCellar" and obj.get("className") == "InventoryCellar":
            from meadows_storage import cellar_capacity
            cellar = cellar_capacity(save, obj, item)
            if cellar is not None:
                capacity += cellar
                continue
            import cellar_progression
            if _guard_active_world(save) in cellar_progression.WORLDS:
                try:
                    capacity += cellar_progression.capacity(save, obj, item)
                except ValueError:
                    unsupported = True
                continue
        if item.get("className") != "StorageBuilding" or obj.get("className") != "StorageBuilding":
            unsupported = True
            continue
        if obj.get("isFullyBuilt") is False or obj.get("state") in ("construction", "constructing"):
            continue
        images = item.get("image", [])
        images = images if isinstance(images, list) else [images]
        built_states = {row.get("name") for row in images if isinstance(row, dict)
                        and str(row.get("name", "")).startswith("built_")}
        if ((obj.get("isFullyBuilt") is not None and obj.get("isFullyBuilt") is not True)
                or obj.get("state") not in {"built", *built_states}):
            unsupported = True
            continue
        level = _capacity_integer(obj.get("expansionLevel", 1))
        if level < 1:
            raise ValueError("The imported storage expansion level is invalid.")
        contribution = item.get("capacity")
        if level > 1:
            upgrades = item.get("upgrade", [])
            upgrades = upgrades if isinstance(upgrades, list) else [upgrades]
            matches = [row for row in upgrades if isinstance(row, dict)
                       and _capacity_integer(row.get("level"), catalog=True) == level]
            if len(matches) > 1:
                unsupported = True
                continue
            # loadObject retains the catalog capacity if getUpgradeData has
            # no matching inline upgrade (classic upgrades replace the item).
            if matches:
                contribution = matches[0].get("capacity")
        capacity += _capacity_integer(contribution, catalog=True)
    capacity = min(capacity, _inventory_limits()[destination])
    if usage + quantity > capacity:
        if unsupported:
            raise ValueError("This farm's imported or special storage capacity is not supported yet.")
        raise ValueError("The active farm inventory does not have enough storage space.")


def normalize_empty_building_snapshot(snapshot):
    # StorageBuilding.getSaveObject can serialize its empty associative
    # contents as an AMF Object. loadObject (AS3 line 1843) instead coerces
    # truthy contents to Array, so a saved empty Object stops world loading.
    # Only this exact empty case is safe to repair without interpreting or
    # discarding imported storage data; specialized subclasses own their data.
    classic = _CLASSIC_CONTAINERS.get(snapshot.get("itemName"))
    fountain = False
    if (snapshot.get("itemName") == "xrf_fountainofyouth"
            and snapshot.get("className") == "FeatureBuilding"):
        # The owned visual Fountain also inherits StorageBuilding.loadObject;
        # its original place/save packet has the same empty Object shape.
        import rainforest_features
        fountain = bool(rainforest_features.rule(
            get_item_by_name(snapshot["itemName"]), rainforest_features.WORLD))
    if (snapshot.get("className") == "StorageBuilding"
            or classic and snapshot.get("className") == classic[0]
            or fountain) and snapshot.get("contents") == {}:
        snapshot["contents"] = []


def normalize_empty_building_contents(save):
    """Repair ordinary empty storage buildings in all owned world snapshots."""
    import world_travel
    for world in world_travel.worlds(save):
        for snapshot in world["objectsArray"]:
            normalize_empty_building_snapshot(snapshot)


def _adjust_quantity(entry: list, delta: int, trim_extra_data: bool = True) -> None:
    # client ref.: src/Classes/storage/StorageItem.as (adjustQuantity)
    # extraData holds one entry per unit, so a drop in quantity throws the oldest ones away from the front.
    entry[METADATA_INDEX_QUANTITY] += delta
    if trim_extra_data:
        extra_data = entry[METADATA_INDEX_EXTRADATA]
        while extra_data and len(extra_data) > entry[METADATA_INDEX_QUANTITY]:
            extra_data.pop(0)


def store_deposit_item_by_name(save: dict, item_name: str, amount: int = 1, group: int = HOME_INVENTORY_ID, sender: str = "0", instance_uuid=None) -> bool:
    _guard_active_world(save)
    amount = positive_quantity(amount)

    item_data = get_item_by_name(item_name)
    if item_data is None:
        raise ValueError("The stored item is unknown.")

    item_code = item_data["code"]
    if instance_uuid:
        _validate_ugc_instance(save, item_data, instance_uuid)
        if amount != 1:
            raise ValueError("A custom design can only be stored once.")
        if group != GIFTBOX_ID:
            item_code += ITEM_KEY_DELIMITER + instance_uuid
    storage = save["userInfo"]["player"]["storageData"]
    group_key = str(group)

    if group_key not in storage:
        storage[group_key] = {}
    if item_code in storage[group_key]:
        storage[group_key][item_code][METADATA_INDEX_QUANTITY] += amount
    else:
        storage[group_key][item_code] = [amount, [], []] # client ref.: src/Classes/Player.as (loadInventoryFromStorageData)

    # client ref.: src/Classes/Player.as (addGift) - one sender id per gift, not per unit, and "0" means
    # "not from a player" (the gift box then shows the generic FarmVille sender).
    if sender != "0":
        storage[group_key][item_code][METADATA_INDEX_SENDER_IDS].append(sender)
    if instance_uuid:
        # Gifts use the base code and a raw UUID per unit. Inventory uses
        # code:UUID (UGCResourceDelegate.getInventoryCode), preserving variants.
        storage[group_key][item_code][METADATA_INDEX_EXTRADATA].append(instance_uuid)

    print(" * Stored: {}x {} (code {}) to {}".format(amount, item_name, item_code, get_inventory_group_name_by_id(group)))
    return True


def store_withdraw_item_by_name(save: dict, item_name: str, amount: int = 1, group: int = HOME_INVENTORY_ID) -> bool:
    item = get_item_by_name(item_name)
    if item is None:
        raise ValueError("The stored item is unknown.")
    return store_withdraw_item_by_code(save, item["code"], amount, group)


def store_withdraw_item_by_code(save: dict, item_code: str, amount: int = 1, group: int = HOME_INVENTORY_ID, trim_extra_data: bool = True) -> bool:
    _guard_active_world(save)
    amount = positive_quantity(amount)
    storage = save["userInfo"]["player"]["storageData"]
    group_key = str(group)
    entry = storage.get(group_key, {}).get(item_code)
    if entry is None or entry[METADATA_INDEX_QUANTITY] < amount:
        return False

    _adjust_quantity(entry, -amount, trim_extra_data)
    if entry[METADATA_INDEX_QUANTITY] <= 0:
        del storage[group_key][item_code]
    elif entry[METADATA_INDEX_SENDER_IDS]:
        # client ref.: src/Classes/Player.as (removeGiftWithKey -> shiftSenderId): exactly one sender id
        # goes, however many units were taken, and only while the entry survives.
        entry[METADATA_INDEX_SENDER_IDS].pop(0)

    item_data = get_item_by_code(item_code.split(ITEM_KEY_DELIMITER, 1)[0])
    item_name = item_data["name"] if item_data else item_code
    print(" * Storage Withdrawal: {}x {} (code {}) from {}".format(amount, item_name, item_code, get_inventory_group_name_by_id(group)))
    return True


def consume_by_name(save: dict, item_name: str, count, group):
    _guard_active_world(save)
    count = positive_quantity(count)
    import cove_shipping
    if item_name == cove_shipping.CONSUMABLE:
        return cove_shipping.consume(save, count, group)
    from meadows_storage import consume_license
    if consume_license(save, item_name, count, group):
        return
    item = get_item_by_name(item_name)
    _ensure_building_storage(save, group)
    entry = save["userInfo"]["player"]["storageData"].get(str(group), {}).get(item["code"] if item else None)
    if not entry or entry[METADATA_INDEX_QUANTITY] < count:
        raise ValueError("There are not enough gifts to use.")
    if not item or not (item.get("type") == "consumable" or item.get("className") == "CRewardConsumable"):
        raise ValueError("This item cannot be consumed.")
    rewards = (item.get("rewards") or {}).get("reward")
    rewards = [rewards] if isinstance(rewards, dict) else rewards
    if not isinstance(rewards, list) or not rewards:
        raise ValueError("This consumable does not have a supported reward.")
    grants = []
    for reward in rewards:
        kind = reward.get("type")
        if kind == "item_grant":
            packed = get_item_by_code(reward.get("value"))
            if packed is None:
                raise ValueError("The package contains an unknown item.")
            quantity = positive_quantity(int(reward.get("quantity", 1)))
            grants.append((kind, packed["name"], count * quantity))
        elif kind == "coins":
            grants.append((kind, None, count * positive_quantity(int(reward.get("value", 0)))))
        elif kind == "seen_flag":
            grants.append((kind, reward["value"], 1))
        else:
            # Validate every reward before withdrawing; an archived travel or
            # crafting package must not silently eat the gift or partly unpack.
            raise ValueError("This package needs a game feature that is not supported yet.")
    store_withdraw_item_by_name(save, item_name, count, group)
    if group > 0:
        # A building's contents snapshot mirrors its ledger; keep it in step with the withdrawal.
        _sync_building_contents(save, group)
    for kind, value, quantity in grants:
        if kind == "item_grant":
            # CRewardConsumable calls UserRewardUtil, whose item_grant uses
            # Player.addGift regardless of the consumed package's container.
            store_deposit_item_by_name(save, value, quantity, GIFTBOX_ID)
        elif kind == "coins":
            from engine import apply_coins_diff
            apply_coins_diff(save, quantity)
        elif kind == "seen_flag":
            save["userInfo"]["player"]["seenFlags"][value] = True


def remove_gift_by_code(save: dict, code: str, amount: int = 1, meta_index=-1) -> bool:
    # client ref.: src/Classes/Player.as (removeGiftWithKey)
    if meta_index < 0:
        return store_withdraw_item_by_code(save, item_code=code, amount=amount, group=GIFTBOX_ID)

    # A meta_index names one exact unit (a bred animal's mutable state, a UGC item's uuid): the client
    # splices that entry out of extraData instead of trimming the front, so trimming stays off here.
    entry = save["userInfo"]["player"]["storageData"].get(str(GIFTBOX_ID), {}).get(code)
    extra_data = entry[METADATA_INDEX_EXTRADATA] if entry else []
    result = store_withdraw_item_by_code(save, item_code=code, amount=amount, group=GIFTBOX_ID,
                                         trim_extra_data=False)
    if result and meta_index < len(extra_data):
        extra_data.pop(meta_index)
    return result


def positive_quantity(value):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value <= 0 or int(value) != value):
        raise ValueError("The item quantity must be a positive whole number.")
    return int(value)


def validate_consumption_source(save, item, group, quantity, metadata_index=-1):
    """Preflight new credit/license grants without discarding opaque imports."""
    group = _storage_group(group)
    metadata_index = _storage_group(metadata_index)
    _ensure_building_storage(save, group)
    entry = save["userInfo"]["player"]["storageData"].get(str(group), {}).get(item["code"])
    if (not isinstance(entry, list) or len(entry) != 3
            or not isinstance(entry[1], list) or not isinstance(entry[2], list)):
        raise ValueError("The consumed item's imported quantity or metadata is invalid.")
    amount = _capacity_integer(entry[0])
    if amount < quantity or len(entry[2]) > amount:
        raise ValueError("The consumed item's imported quantity or metadata is invalid.")
    if metadata_index < -1 or (metadata_index >= 0 and (quantity != 1 or metadata_index >= len(entry[2]))):
        raise ValueError("The consumed item's metadata selection is invalid.")
    return metadata_index



def _validate_ugc_instance(save, item, instance_uuid):
    from ugc import validate_owned_state
    return validate_owned_state(save, instance_uuid, item["name"])


def _instance_uuid(save, item, metadata=None, snapshot=None):
    """Read the two original UGC transaction shapes without trusting a new UUID."""
    if not str(item.get("className", "")).startswith("UGC"):
        return None
    supplied = metadata.get("type") if isinstance(metadata, dict) else metadata
    saved = (snapshot or {}).get("ugcItemUUID")
    if supplied and saved and supplied != saved:
        raise ValueError("The custom design does not match the placed item.")
    instance_uuid = supplied or saved
    _validate_ugc_instance(save, item, instance_uuid)
    return instance_uuid


def _require_withdrawal(save, item, quantity, group, metadata_index=-1, instance_uuid=None):
    from breeding import guard_storage_withdrawal
    guard_storage_withdrawal(save, item, quantity, group)
    if group < 0 and group not in (GIFTBOX_ID, CONSUME_ID, active_inventory_id(save)):
        _guard_shipping(save, group, item=item)
    _ensure_building_storage(save, group)
    code = item["code"]
    if instance_uuid:
        _validate_ugc_instance(save, item, instance_uuid)
        if quantity != 1:
            raise ValueError("A custom design can only be withdrawn once.")
        if group == GIFTBOX_ID:
            entry = save["userInfo"]["player"]["storageData"].get(str(group), {}).get(code)
            extras = entry[METADATA_INDEX_EXTRADATA] if entry else []
            if metadata_index < 0:
                metadata_index = extras.index(instance_uuid) if instance_uuid in extras else -1
            if metadata_index < 0 or metadata_index >= len(extras) or extras[metadata_index] != instance_uuid:
                raise ValueError("The requested custom design is no longer in the gift box.")
        else:
            code += ITEM_KEY_DELIMITER + instance_uuid
    removed = (remove_gift_by_code(save, code, quantity, metadata_index)
               if group == GIFTBOX_ID else
               store_withdraw_item_by_code(save, code, quantity, group))
    if not removed:
        raise ValueError("The requested item is no longer in storage.")
    # Positive storage IDs are buildings. Their contents are loaded from the
    # world object, while inventory and gifts load from storageData.
    if group > 0:
        _sync_building_contents(save, group)
        owner = next((obj for obj in save["world"]["objectsArray"] if obj.get("id") == group), None)
        if owner and orchard_container_class(get_item_by_name(owner.get("itemName"))):
            # OrchardFeatureBuilding.removeContents25696 splices matching
            # order entries while advancing the index after every iteration.
            order = owner.get("itemOrder", [])
            index = 0
            while index < len(order):
                if order[index] == code:
                    order.pop(index)
                index += 1
            if not any(row.get("numItem", 0) for row in owner["contents"]):
                owner["state"] = "bare"


def _ensure_building_storage(save, group):
    current = _guard_active_world(save)
    group = _storage_group(group)
    owned = None
    if group > 0:
        # Recovery withdrawals validate ownership/completion, but deliberately
        # do not require the existing imported items or count to pass today's
        # deposit filter/capacity. They must remain removable.
        owned = _feature_owner(save, group)
    storage_data = save["userInfo"]["player"]["storageData"]
    if owned is not None:
        owner = owned[0]
        contents = owner.get("contents", [])
        if contents == {}:
            contents = []
        if not isinstance(contents, list):
            raise ValueError("The imported feature container contents are invalid.")
        counts = {}
        for row in contents:
            if not isinstance(row, dict) or not isinstance(row.get("itemCode"), str) or row["itemCode"] in counts:
                raise ValueError("The imported feature container contents are ambiguous.")
            counts[row["itemCode"]] = _capacity_integer(row.get("numItem"))
        ledger = storage_data.get(str(group))
        if ledger is not None:
            if not isinstance(ledger, dict):
                raise ValueError("The imported feature container ledger is invalid.")
            ledger_counts = {}
            for code, entry in ledger.items():
                if not isinstance(entry, list) or len(entry) < 3 or not isinstance(entry[1], list) or not isinstance(entry[2], list):
                    raise ValueError("The imported feature container ledger is invalid.")
                ledger_counts[code] = _capacity_integer(entry[0])
            if ledger_counts != counts:
                raise ValueError("The imported feature container ledger disagrees with its contents.")
    if group < 0 and group not in (GIFTBOX_ID, CONSUME_ID):
        from world_travel import supported_worlds
        active_inventory = _storage_group(active_inventory_id(save))
        if active_inventory != supported_worlds()[current]:
            raise ValueError("The imported active inventory does not match its world; recover its ownership before withdrawal.")
        if group != active_inventory:
            _guard_shipping(save, group)
    if group > 0:
        from world_travel import guard_action_object
        guard_action_object(save, group)
        owners = [obj for obj in save["world"]["objectsArray"] if obj.get("id") == group]
        if len(owners) != 1 or owners[0].get("deleted"):
            raise ValueError("The storage building must have one current owned identity.")
    if group > 0 and str(group) not in storage_data:
        building = next((obj for obj in save["world"]["objectsArray"] if obj["id"] == group), None)
        if building is not None:
            storage_data[str(group)] = {
                row["itemCode"]: [positive_quantity(row["numItem"]), [], []]
                for row in building.get("contents", []) if row.get("numItem", 0) > 0
            }


def _sync_building_contents(save, group):
    building = next((obj for obj in save["world"]["objectsArray"] if obj["id"] == group), None)
    if building is not None:
        old = {row["itemCode"]: row for row in building.get("contents", [])}
        building["contents"] = [{**old.get(code, {}), "itemCode": code, "numItem": entry[0]}
                                for code, entry in save["userInfo"]["player"]["storageData"].get(str(group), {}).items()]


def _given_options(options) -> dict:
    # AMF null and `undefined` both mean "not given". pyamf.Undefined is truthy and cannot be int()-converted,
    # so left in place it reads a flag as set (isGift) or crashes (giftMetadataIndex, target, numToStore).
    return {key: value for key, value in options.items()
            if value is not None and not isinstance(value, pyamf.UndefinedType)}


def world_action_options(params) -> dict:
    """Read one original options object from a strict or AMF0 mixed Array.

    Numeric keys identify the positional envelope. Refuse gaps, aliases and
    extra arguments rather than dropping them. TWorldState may append firstWA.
    Direct options objects remain valid for internal callers.
    """
    if isinstance(params, dict):
        indexed = any(type(key) is not str or key.isdecimal() for key in params)
        if not indexed:
            return _given_options(params)
        entries = {}
        for key, value in params.items():
            if type(key) is int and key in (0, 1):
                index = key
            elif type(key) is str and key in ('0', '1'):
                index = int(key)
            else:
                raise ValueError('Storage action options need consecutive positional indices.')
            if index in entries:
                raise ValueError('Storage action options have duplicate positional indices.')
            entries[index] = value
        if set(entries) != set(range(len(entries))):
            raise ValueError('Storage action options need consecutive positional indices.')
        params = [entries[index] for index in range(len(entries))]
    if not isinstance(params, (list, tuple)):
        raise ValueError('Storage action requires its original options object.')
    if (len(params) == 2 and isinstance(params[1], dict)
            and set(params[1]) == {'firstWA'} and params[1]['firstWA'] is True):
        params = params[:1]
    if not params:
        return {}
    if len(params) != 1 or not isinstance(params[0], dict):
        raise ValueError('Storage action requires one original options object.')
    return _given_options(params[0])


def withdraw_for_placement(save, item_name, params, snapshot=None):
    """Consume one gift/container item, returning whether placement was stored."""
    _guard_active_world(save)
    item = get_item_by_name(item_name)
    if item is None:
        raise ValueError("The placed item is unknown.")
    options = world_action_options(params)
    instance_uuid = _instance_uuid(save, item, options.get("metadata"), snapshot)
    group = _storage_group(options.get("isStorageWithdrawal", 0))
    if options.get("isGift"):
        group = GIFTBOX_ID
    elif options.get("isInventoryWithdrawal") and not group:
        group = active_inventory_id(save)
    if not group:
        if instance_uuid:
            raise ValueError("Build a custom design before placing it from storage.")
        return False
    if group < 0 and group not in (GIFTBOX_ID, CONSUME_ID, active_inventory_id(save)):
        lane = _guard_shipping(save, group, item=item)
        original = save["userInfo"]["player"]["storageData"].get(str(group), {}).get(item["code"])
        if lane != "england" and original and len(original) > METADATA_INDEX_EXTRADATA and original[METADATA_INDEX_EXTRADATA]:
            # Cross-world metadata remains transferable between inventories.
            # Placing specialized imported unit state needs its own consumer;
            # do not discard it through a generic placement withdrawal.
            raise ValueError("Move this imported item's metadata between inventories before placing it locally.")
    if group > 0 and any(obj.get("id") == group and _container_class(
            get_item_by_name(obj.get("itemName"))) for obj in save["world"]["objectsArray"]):
        _storage_group(options.get("isStorageWithdrawal"))
    _ensure_building_storage(save, group)
    restored_metadata = None
    if not instance_uuid:
        entry = save["userInfo"]["player"]["storageData"].get(str(group), {}).get(item["code"])
        if isinstance(entry, list) and len(entry) >= 3 and isinstance(entry[2], list):
            if len(entry[2]) > _capacity_integer(entry[0]):
                raise ValueError("The stored unit metadata exceeds its quantity; recover its mapping before withdrawal.")
            index = _storage_group(options.get("giftMetadataIndex", -1)) if group == GIFTBOX_ID else -1
            if index < -1:
                raise ValueError("The selected stored unit metadata is invalid.")
            if index >= 0:
                if index >= len(entry[2]):
                    raise ValueError("The selected stored unit metadata is unavailable.")
                restored_metadata = copy.deepcopy(entry[2][index])
            elif len(entry[2]) >= _capacity_integer(entry[0]) and entry[2]:
                restored_metadata = copy.deepcopy(entry[2][0])
    _require_withdrawal(save, item, 1, group, _storage_group(options.get("giftMetadataIndex", -1)), instance_uuid)
    if instance_uuid and snapshot is not None:
        snapshot["ugcItemUUID"] = instance_uuid
    elif restored_metadata is not None and snapshot is not None:
        snapshot["metadata"] = restored_metadata
    elif not instance_uuid and snapshot is not None:
        snapshot.pop("metadata", None)
    return True


def _guard_shipping(save, source, destination=None, item=None):
    """Choose exactly one restored pair; no world inherits another's license."""
    from world_travel import supported_worlds
    source = _storage_group(source)
    current = _guard_active_world(save)
    canonical = supported_worlds()[current]
    if source > 0 or source in (GIFTBOX_ID, CONSUME_ID, canonical):
        return None
    source_world = next((world for world, group in supported_worlds().items() if group == source), None)
    pair = {source_world, current}
    if pair == {"farm", "england"}:
        import england_shipping
        england_shipping.guard_transfer(save, source, destination)
        return "england"
    if pair == {"farm", "meadows"}:
        import meadows_storage
        meadows_storage.guard_shipping(save, source, item)
        lane = "meadows"
    elif pair == {"farm", "fisherman"}:
        import cove_shipping
        cove_shipping.guard_source(save, source)
        lane = "cove"
    else:
        raise ValueError("This world's shipping contract is not restored.")
    if destination is not None and _storage_group(destination) != canonical:
        raise ValueError("Licensed shipping must arrive in the active farm inventory.")
    return lane


def _storage_request_ids(snapshot, options):
    """Validate signed IDs before truthiness/conversion can alias a real ID."""
    _storage_group(snapshot.get("id", 0))
    parsed = {field: _storage_group(options[field]) for field in
              ("origin", "cameFromLocation", "target", "resource") if field in options}
    if ("origin" in parsed and "cameFromLocation" in parsed
            and parsed["origin"] != parsed["cameFromLocation"]):
        raise ValueError("The storage source inventory is ambiguous.")
    return (parsed.get("target", _storage_group(snapshot.get("id", 0))),
            parsed.get("cameFromLocation", parsed.get("origin", 0)), parsed.get("resource", 0))


def start_session(save):
    # Legacy numeric counters restart on initUser; namespace receipts remain
    # durable so a late original packet cannot mutate a newly loaded session.
    history = save.get(REQUESTS_KEY)
    if history is None:
        return
    if not isinstance(history, dict) or not isinstance(history.get("receipts", {}), dict):
        raise ValueError("The saved storage retry history is invalid.")
    retained = {key: value for key, value in history.get("receipts", {}).items()
                if isinstance(key, str) and ":" in key}
    if retained:
        save[REQUESTS_KEY] = {"receipts": retained, "highestSequences": history.get("highestSequences", {})}
    else:
        save.pop(REQUESTS_KEY, None)


def _request_signature(save, snapshot, options):
    def encode(value):
        if isinstance(value, pyamf.UndefinedType):
            return None
        raise ValueError("The storage request contains an unsupported value.")
    signed = copy.deepcopy(snapshot)
    for field in ("plantTime", "tempId", "buildTime"):
        value = signed.get(field)
        if type(value) is float and math.isnan(value):
            signed[field] = None
    return json.dumps([_guard_active_world(save), signed, options],
                      sort_keys=True, allow_nan=False, default=encode)


def store_world_item(save, snapshot, options, *, request_id=None, request_snapshot=None):
    """Atomic store with the original packet signature and durable retries."""
    normalized = _given_options(options)
    destination, origin, _ = _storage_request_ids(snapshot, normalized)
    foreign = origin < 0 and origin not in (GIFTBOX_ID, CONSUME_ID, active_inventory_id(save))
    # Read matching receipts before current item availability/capacity guards.
    # They acknowledge only the exact previously committed original packet.
    signed = snapshot if request_snapshot is None else request_snapshot
    signature = _request_signature(save, signed, normalized) if request_id is not None else None
    from world_travel import supported_worlds
    source_world = next((world for world, value in supported_worlds().items() if value == origin), None)
    meadows = foreign and {_guard_active_world(save), source_world} == {"farm", "meadows"}
    if meadows:
        if destination != active_inventory_id(save):
            raise ValueError("Licensed shipping must arrive in the active farm inventory.")
        if request_id is None:
            raise ValueError("Licensed shipping requires a signed request sequence.")
        from meadows_storage import _receipt, _record
        key, old = _receipt(save, "shipping", request_id, signature)
        if old is not None:
            return
    else:
        key = None
        namespace = None
        sequence = request_id
        if isinstance(request_id, tuple):
            if len(request_id) != 2:
                raise ValueError("A storage request needs its original sequenceID and sequence.")
            namespace, sequence = request_id
            if namespace is not None and (not isinstance(namespace, str) or not namespace or len(namespace) > 128):
                raise ValueError("The storage sequenceID is invalid.")
        if request_id is not None:
            sequence = _capacity_integer(sequence)
            key = (namespace + ":" if namespace is not None else "") + str(sequence)
            history = save.get(REQUESTS_KEY, {})
            if (not isinstance(history, dict) or not isinstance(history.get("receipts", {}), dict)
                    or not isinstance(history.get("highestSequences", {}), dict)):
                raise ValueError("The saved storage retry history is invalid.")
            old = history.get("receipts", {}).get(key)
            if old is not None:
                if not isinstance(old, dict) or old.get("signature") != signature:
                    raise ValueError("A storage sequence was reused for another request.")
                return
            if namespace is not None:
                current = save.get("_meadowsStorage", {}).get("sessionID")
                if namespace != current:
                    raise ValueError("This storage sequenceID is stale or unknown.")
                highest = history.get("highestSequences", {}).get(namespace, -1)
            else:
                highest = history.get("highestSequence", -1)
            if type(highest) is not int or highest < -1:
                raise ValueError("The saved storage request sequence is invalid.")
            if sequence <= highest:
                raise ValueError("This storage request is older than the retained retry history.")
    working = copy.deepcopy(save)
    _store_world_item(working, snapshot, normalized)
    if meadows:
        _record(working, key, signature, {})
    elif key is not None:
        history = working.setdefault(REQUESTS_KEY, {})
        receipts = history.setdefault("receipts", {})
        receipts[key] = {"signature": signature}
        if namespace is None:
            history["highestSequence"] = sequence
        else:
            history.setdefault("highestSequences", {})[namespace] = sequence
        while len(receipts) > 256:
            del receipts[next(iter(receipts))]
    save.clear(); save.update(working)


def _store_world_item(save, snapshot, options):
    """Mirror TInventoryStore/TStoreItem without dropping source or metadata."""
    _guard_active_world(save)
    from engine import apply_item_cost, get_world_object_by_id, world_remove_object, world_object_id_is_temporary
    options = _given_options(options)
    destination, source_group, resource_id = _storage_request_ids(snapshot, options)
    from breeding import guard_storage
    guard_storage(save, snapshot, options)
    from pets import guard_storage as guard_pet_storage
    guard_pet_storage(save, snapshot, options)
    item = get_item_by_name(options.get("storedItemName") or snapshot.get("itemName"))
    if item is None:
        raise ValueError("The stored item is unknown.")
    quantity = positive_quantity(options.get("numToStore", 1))
    if options.get("isGift") and source_group not in (0, GIFTBOX_ID):
        raise ValueError("The storage gift source is ambiguous.")
    if destination == 0 or destination in (GIFTBOX_ID, CONSUME_ID):
        raise ValueError("The storage destination is invalid.")
    source = get_world_object_by_id(save["world"]["objectsArray"], resource_id)
    instance_uuid = _instance_uuid(save, item, options.get("metadata"), source)
    shipping_metadata, shipping_senders = None, []
    if source_group < 0:
        if _guard_shipping(save, source_group, destination, item):
            code = item["code"] + (ITEM_KEY_DELIMITER + instance_uuid if instance_uuid else "")
            original = save["userInfo"]["player"]["storageData"].get(str(source_group), {}).get(code)
            if (not isinstance(original, list) or len(original) != 3
                    or not isinstance(original[1], list) or not isinstance(original[2], list)):
                raise ValueError("The shipped item's inventory metadata is invalid.")
            count = _capacity_integer(original[0])
            if len(original[2]) > count:
                raise ValueError("The shipped unit metadata exceeds its quantity; recover its mapping before transfer.")
            removed_extras = max(0, len(original[2]) - (count - quantity))
            shipping_metadata = copy.deepcopy(original[2][:removed_extras])
            shipping_senders = copy.deepcopy(original[1] if quantity >= count else original[1][:1])
    feature_container = _guard_feature_deposit(save, snapshot, destination, item, quantity)
    orchard_state = None
    orchard_metadata = None
    habitat_clock = None
    container_senders = []
    if feature_container:
        from world_travel import guard_action_object, supported_worlds
        for field in ("target", "resource", "cameFromLocation", "origin"):
            if field in options:
                _storage_group(options[field])
        if source_group < 0 and source_group != GIFTBOX_ID:
            canonical = supported_worlds()[_guard_active_world(save)]
            if source_group != canonical or source_group != active_inventory_id(save):
                _guard_shipping(save, source_group, destination, item)
        if source_group > 0:
            guard_action_object(save, source_group)
            sources = [row for row in save["world"]["objectsArray"] if row.get("id") == source_group]
            if len(sources) != 1 or sources[0].get("deleted"):
                raise ValueError("The source container must have one current owned identity.")
        if not options.get("isGift") and not source_group and resource_id:
            guard_action_object(save, resource_id)
            if source is not None and (source.get("deleted") or sum(
                    row.get("id") == resource_id for row in save["world"]["objectsArray"]) != 1):
                raise ValueError("The stored resource must have one current owned identity.")
        owner = get_world_object_by_id(save["world"]["objectsArray"], destination)
        owner_item = get_item_by_name(owner["itemName"])
        if orchard_container_class(owner_item):
            orchard_state = _orchard_store_state(save, owner, owner_item)
        elif home_habitat_container_class(owner_item):
            habitat_clock = _home_habitat_store_clock(owner, owner_item)
    origin = GIFTBOX_ID if options.get("isGift") else source_group
    # A loaded unit or inventory entry owns its existing variant. Market-to-
    # storage has no imported unit and cannot manufacture one from options.
    # Keep the legacy original-client metadata contract only for an ordinary
    # placed source whose saved object has no metadata field at all.
    authoritative_metadata = (not instance_uuid and (feature_container
        or item.get("className") in ("Gnome", "CraftRewardGnome") or origin
        or source is None or "metadata" in source))
    if authoritative_metadata:
        orchard_metadata = []  # Authoritative emptiness forbids client variants.
        if origin:
            _ensure_building_storage(save, origin)
            entry = save["userInfo"]["player"]["storageData"].get(str(origin), {}).get(item["code"])
            if entry is not None:
                if (not isinstance(entry, list) or len(entry) < 3
                        or not isinstance(entry[1], list) or not isinstance(entry[2], list)):
                    raise ValueError("The stored item's inventory metadata is invalid.")
                source_count = _capacity_integer(entry[0])
                if len(entry[2]) > source_count:
                    raise ValueError("The contained unit metadata exceeds its quantity; recover its mapping before storage.")
                index = _storage_group(options.get("giftMetadataIndex", -1)) if options.get("isGift") else -1
                if index < -1 or (index >= 0 and (quantity != 1 or index >= len(entry[2]))):
                    raise ValueError("The stored item's metadata selection is invalid.")
                removed = max(0, len(entry[2]) - (source_count - quantity))
                orchard_metadata = copy.deepcopy(entry[2][index:index + 1] if index >= 0 else entry[2][:removed])
                container_senders = copy.deepcopy(entry[1] if quantity >= source_count else entry[1][:1])
        elif source is not None and source.get("metadata") is not None:
            orchard_metadata = [copy.deepcopy(source["metadata"])]
    _guard_inventory_deposit(save, destination, quantity,
                             resource_id if source is not None and not source_group and not options.get("isGift") else None)
    if options.get("isGift"):
        _require_withdrawal(save, item, quantity, GIFTBOX_ID,
                            _storage_group(options.get("giftMetadataIndex", -1)), instance_uuid)
    elif source_group:
        if source_group == destination:
            raise ValueError("The item is already in that storage.")
        _require_withdrawal(save, item, quantity, source_group, instance_uuid=instance_uuid)
    elif source is not None:
        if source.get("itemName") != item["name"] or quantity != 1:
            raise ValueError("The stored resource does not match the farm.")
        world_remove_object(save["world"]["objectsArray"], resource_id)
    else:
        # Market-to-storage is a purchase; a retry whose resource disappeared
        # must never clone another copy for free.
        if resource_id > 0 and not world_object_id_is_temporary(resource_id):
            raise ValueError("The stored resource is missing from the farm.")
        if instance_uuid:
            raise ValueError("The custom design is missing from the farm or storage.")
        from creative_worlds import guard_market_purchase
        from crafting import purchase_catalog_item
        item = purchase_catalog_item(save, item)
        guard_market_purchase(save, item, options.get("currency"), quantity=quantity)
        for _ in range(quantity):
            apply_item_cost(save, item, currency=options.get("currency") or None)
    _ensure_building_storage(save, destination)
    store_deposit_item_by_name(save, item["name"], quantity, destination, instance_uuid=instance_uuid)
    stored_code = item["code"] + (ITEM_KEY_DELIMITER + instance_uuid if instance_uuid else "")
    entry = save["userInfo"]["player"]["storageData"][str(destination)][stored_code]
    metadata = options.get("metadata")
    if shipping_metadata is not None:
        # Transfer actual source units, preserving imported names and variants.
        if instance_uuid:
            entry[METADATA_INDEX_EXTRADATA].pop()  # added by deposit helper
        entry[METADATA_INDEX_EXTRADATA].extend(shipping_metadata)
        entry[METADATA_INDEX_SENDER_IDS].extend(shipping_senders)
    elif orchard_metadata is not None:
        entry[METADATA_INDEX_EXTRADATA].extend(orchard_metadata)
        entry[METADATA_INDEX_SENDER_IDS].extend(container_senders)
    elif metadata and not instance_uuid:
        entry[METADATA_INDEX_EXTRADATA].extend(copy.deepcopy(metadata) for _ in range(quantity))
    if destination > 0:
        building = get_world_object_by_id(save["world"]["objectsArray"], destination)
        if building is None:
            raise ValueError("The storage building is missing from the farm.")
        # StorageBuilding.getSaveObject deliberately emits contents=[], so its
        # snapshot must not erase the durable contents or imported row fields.
        if not feature_container:
            building.update({key: value for key, value in snapshot.items() if key != "contents"})
        _sync_building_contents(save, destination)
        if orchard_state is not None:
            building["state"] = orchard_state
            building.setdefault("itemOrder", []).append(item["code"])
        if habitat_clock is not None:
            building["plantTime"] = habitat_clock
