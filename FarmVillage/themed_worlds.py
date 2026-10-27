"""Dormant themed farms: basic farming and decorating in recovered score-era worlds.

Each world is an explicit SPECS entry checked against the preserved archive, so
an unexpected archive change fails closed. A themed world gets the same kind of
durable record as Lighthouse Cove: all-access unlock without a charge, a
disclosed empty 50x50 starter, the world's ordinary-ground theme, the original
ceiling of 5500 objects (no plotLimits table), and a World-requirement item
allow-list derived from the catalog.

Only browser-accepted ACTIVE_WORLDS are reachable. creative_worlds and
world_travel dispatch to this module only for listed worlds. Quests,
world scores and score rewards, shipping licenses, feature buildings, unsupported
crafting, breeding, vehicles, consumables and unpriced world-currency offers stay
closed unless an exact regional contract is admitted. Mistletoe Lane and
rainforest cottages use crafting.py's live tiers. Rainforest's exact completed
Orchard/Gnome containers and owned visual Fountain use rainforest_features.py;
their engines and unrecovered boundaries remain independent.
World-currency-only items are charged Farm Cash through world_currency_conversion.
"""
from functools import lru_cache
from pathlib import Path
import copy
import math
import re
import uuid
import xml.etree.ElementTree as ET
import zlib

from bundle import TEMPLATES_DIR, XML_DIR
from game_settings import get_farming_int, xp_to_level
import cove_rules
import creative_worlds
import items
import retired_decor
import world_currency_conversion as wcc
import world_travel

# Activation list. The parent adds a key here only after the browser checks in
# THEMED_WORLDS.md pass. Empty means dormant: no travel, creation, placement or
# purchase reaches these rules.
ACTIVE_WORLDS = frozenset({"rainforest", "mediterranean", "storybook", "candy", "oasis", "oz",
                           "toyland", "sleepyhollow", "australia", "fforest", "htown", "atlantis"})  # glen/hlights retired by owner 2026-10-25; source contracts retained

SPECS = {
    # XML -24 conflicts with original client/StorageConfig Hlights -25.
    "hlights": {"name":"Holiday Lights", "prefix":"xlg", "storageId":-25,
                "xmlStorageId":-24, "theme":"hlights_theme"},
    # Preserve original Glen -18 and absent expansion XML fields.
    "glen": {"name":"Enchanted Glen", "prefix":"xeg", "storageId":-18,
             "xmlStorageId":None, "xmlPrefix":None, "xmlTheme":None,
             "theme":"glen_theme", "localThemeChoice":True,
             "landGatePrefixes":("fv_glen_farm", "fv_xeg_farm")},
    # Original WorldManager and StorageConfig pin AtlantisInventory=-19.
    # Preserve absent expansion XML prefix/storage/theme; the original
    # populated starter is unrecovered and this local theme is disclosed.
    "atlantis": {"name": "Atlantis", "prefix": "xal", "storageId": -19,
                 "xmlStorageId": None, "xmlPrefix": None, "xmlTheme": None,
                 "theme": "atlantis_theme", "localThemeChoice": True,
                 "landGatePrefixes": ("fv_atlantis_farm", "fv_xal_farm")},
    "rainforest": {"name": "Rainforest", "prefix": "xrf", "storageId": -26,
                   "theme": "rainforest_theme"},
    "mediterranean": {"name": "Mediterranean", "prefix": "xmd", "storageId": -29,
                      "theme": "mediterranean_theme"},
    "storybook": {"name": "Fairytale Fields", "prefix": "xsb", "storageId": -32,
                  "theme": "storybook_theme"},
    "candy": {"name": "Sweet Acres", "prefix": "xcw", "storageId": -23,
              "theme": "candy_theme"},
    "oasis": {"name": "Oasis Gardens", "prefix": "xoa", "storageId": -31,
              "theme": "oasis_theme"},
    "oz": {"name": "Emerald Valley", "prefix": "xoz", "storageId": -28,
           "theme": "oz_theme"},
    # Dormant contracts. Browser acceptance is required before adding any key
    # to ACTIVE_WORLDS. These early worlds have explicit original differences.
    "toyland": {"name": "Toy Town", "prefix": "xtl", "storageId": -34,
                "theme": "toyland_theme", "masterExperiment": "fv_xtl_master",
                "forAllExperiment": "fv_xtl_for_all",
                "landGatePrefixes": ("fv_toyland_farm", "fv_toyland_expansion_")},
    "sleepyhollow": {"name": "Horseman's Hollow", "prefix": "xsh", "storageId": -33,
                     "theme": "sleepyhollow_theme", "masterExperiment": "fv_xsh_master",
                     "forAllExperiment": "fv_xsh_for_all",
                     "landGatePrefixes": ("fv_sleepyhollow_farm", "fv_xsh_farm", "fv_horsemans_hollow_expansion_")},
    # gameSettings omits these inventory IDs. WorldManager.<cinit> in the
    # original client pins AUSTRALIA_INVENTORY_ID=-21 and HTOWN_INVENTORY_ID=-15.
    "australia": {"name": "Australia", "prefix": "xau", "storageId": -21,
                  "xmlStorageId": None, "theme": "australia_theme",
                  "landGatePrefixes": ("fv_australia_farm", "fv_xau_farm")},
    "fforest": {"name": "Mystical Groves", "prefix": "xff", "storageId": -24,
                "theme": "fforest_theme"},
    # Htown also omits its prefix and startingTileSet. xhd is recovered from
    # its all-access prerequisite and catalog names. Its exact yimf theme is a
    # deliberate local empty-starter choice; the original starter is absent.
    "htown": {"name": "Mistletoe Lane", "prefix": "xhd", "storageId": -15,
              "xmlStorageId": None, "xmlPrefix": None, "xmlTheme": None,
              "theme": "htown_theme", "localThemeChoice": True,
              "landGatePrefixes": ("fv_htown_farm", "fv_xhd_farm")},
}
TYPES = frozenset(("seed", "tree", "animal", "building", "decoration"))
BASIC_CLASSES = frozenset((None, "Animal", "Tree", "Building", "Decoration",
                           "RotateableDecoration", "MaskedDecoration", "GateDecoration",
                           "StorageBuilding"))
EXPECTED_CLASS = {"seed": "Plot", "animal": "Animal", "tree": "Tree",
                  "building": "Building", "decoration": "Decoration"}
ACTIONS = ("plow", "place", "move", "harvest", "clear", "sell", "store", "getStorageInfo")
INITIAL_SIZE = 50
PLOT_CEILING = 5500
MINIMUM_LEVEL = 15
SPECIAL_PLOT_FLAGS = ("isJumbo", "isBigPlot", "isProduceItem", "isSuperPlot")
NONE_VALUES = (None, "", 0, False, [], {})


def active_worlds():
    return ACTIVE_WORLDS


def storage_id(world_type):
    return SPECS[world_type]["storageId"]


def _spec(world_type):
    if world_type not in SPECS:
        raise ValueError("This themed world is not recovered.")
    return SPECS[world_type]


def _xml(name):
    return ET.fromstring(zlib.decompress(Path(XML_DIR, "gz/v855098", name).read_bytes()))


def _whole(value, label):
    if value is None or value == "":
        raise ValueError(f"The recovered {label} is unavailable.")
    text = str(value).strip()
    if not re.fullmatch(r"[0-9]+", text) or int(text) <= 0:
        raise ValueError(f"The recovered {label} is not a positive whole number.")
    return int(text)


def _prereq_leaves(cms, name, seen=()):
    prereqs = {p.get("name"): p for p in cms.iter("prereq") if p.get("name")}
    node = prereqs.get(name)
    if node is None or name in seen:
        raise ValueError("A recovered access prerequisite is unavailable.")
    leaves = []
    for child in node:
        if child.get("type") == "prereq_check":
            leaves += _prereq_leaves(cms, child.get("value"), seen + (name,))
        else:
            leaves.append((child.get("type"), child.get("value"), child.get("variant")))
    return leaves


@lru_cache(maxsize=None)
def recovered_rules(world_type):
    """Return the checked original contract for one themed world (a copy)."""
    spec = _spec(world_type)
    settings, cms, yimfs = _xml("gameSettings.xml.gz"), _xml("gameSettingsCMS.xml.gz"), _xml("yimf.xml.gz")
    expansion = settings.find(f"expansions/expansion[@name='{world_type}']")
    xml_storage_id = spec.get("xmlStorageId", spec["storageId"])
    xml_storage_id = None if xml_storage_id is None else str(xml_storage_id)
    if (expansion is None or expansion.get("prefix") != spec.get("xmlPrefix", spec["prefix"])
            or expansion.get("storageId") != xml_storage_id
            or expansion.get("currency") is not None
            or expansion.find("plotLimits") is not None
            or expansion.find("worldRequirementOverride") is not None
            or expansion.findtext("startingTileSet") != spec.get("xmlTheme", spec["theme"])
            ):
        raise ValueError(f"{spec['name']}'s recovered world record is unavailable.")
    access = expansion.find("allAccess")
    if access is None or access.attrib or access.find("prereqs/prereq") is None:
        raise ValueError(f"{spec['name']}'s recovered all-access is unavailable.")
    prereq_name = f"fv_{spec['prefix']}_all_access"
    if [e.get("value") for e in access.findall("prereqs/prereq")] != [prereq_name]:
        raise ValueError(f"{spec['name']}'s all-access prerequisite changed.")
    leaves = _prereq_leaves(cms, prereq_name)
    experiments = {"master": spec.get("masterExperiment", f"fv_{world_type}"),
                   "forAll": spec.get("forAllExperiment", f"fv_{world_type}_for_all")}
    expected = {("level_min", str(MINIMUM_LEVEL), None),
                ("experiment", experiments["master"], "1"),
                ("has_not_unlocked_world", world_type, None),
                ("experiment", experiments["forAll"], "1")}
    if set(leaves) != expected or len(leaves) != len(expected):
        raise ValueError(f"{spec['name']}'s recovered all-access conditions changed.")
    rewards = [dict(e.attrib) for e in access.findall("rewards/reward")]
    if {"type": "world_unlock", "value": world_type} not in rewards or any(
            r.get("type") not in ("world_unlock", "unlock_world_score") for r in rewards):
        raise ValueError(f"{spec['name']}'s recovered all-access rewards changed.")
    if cms.find("farming/farmingEntry[@key='farmSize']") is None or \
            cms.find("farming/farmingEntry[@key='farmSize']").get("value") != str(INITIAL_SIZE):
        raise ValueError("The recovered initial farm size is unavailable.")
    if cms.find("farming/farmingEntry[@key='maxNumObjects']") is None or \
            cms.find("farming/farmingEntry[@key='maxNumObjects']").get("value") != str(PLOT_CEILING):
        raise ValueError("The recovered object ceiling is unavailable.")
    theme = yimfs.find(f"yimf[@type='{spec['theme']}']")
    if theme is None or theme.find("weights") is None or theme.findtext("tileClass") != "grass" \
            or not theme.findtext("horizon") or not theme.findtext("backgroundPath"):
        raise ValueError(f"{spec['name']}'s recovered theme is unavailable.")
    return {"worldType": world_type, "name": spec["name"], "minimumLevel": MINIMUM_LEVEL,
            "accessType": "allAccess", "cashCost": 0, "coinCost": 0,
            "rewards": [{"type": "world_unlock", "value": world_type}],
            "scoreReward": "unlock_world_score (not restored)",
            "initialSize": INITIAL_SIZE, "plotCeiling": PLOT_CEILING,
            "tileSet": spec["theme"], "storageId": spec["storageId"],
            "theme": {"horizon": theme.findtext("horizon"),
                      "backgroundPath": theme.findtext("backgroundPath"),
                      "tileClass": "grass", "weights": theme.findtext("weights")},
            "localStarter": f"empty-{world_type}-v1",
            "experiments": experiments,
            "storageIdSource": "WorldManager original client" if "xmlStorageId" in spec else "gameSettings expansion",
            "localThemeChoice": bool(spec.get("localThemeChoice")),
            "currency": "coins", "score": None}


@lru_cache(maxsize=1)
def served_experiments():
    """Experiment values the served client config sends; unreadable means none."""
    try:
        text = Path(TEMPLATES_DIR, "play.html").read_text(encoding="utf-8")
    except OSError:
        return {}
    return {key: int(value) for key, value in re.findall(r'"(fv_[A-Za-z0-9_]+)":\s*(-?\d+)', text)}


def _own_gate(gate, world_type):
    """Only the world's own master and its farm-expansion gates are admitted."""
    spec = _spec(world_type)
    master = spec.get("masterExperiment", "fv_" + world_type)
    for_all = spec.get("forAllExperiment", "fv_" + world_type + "_for_all")
    prefixes = spec.get("landGatePrefixes", ("fv_" + world_type + "_farm",))
    return gate in (master, for_all) or any(gate.startswith(prefix) for prefix in prefixes)


def _gates(item):
    gate = item.get("experimentGate")
    if gate in NONE_VALUES:
        return []
    return [str(g) for g in (gate if isinstance(gate, list) else [gate])]


def _classes(node, found=None):
    found = [] if found is None else found
    if isinstance(node, dict):
        if node.get("className") is not None:
            found.append(node["className"])
        for child in node.values():
            _classes(child, found)
    elif isinstance(node, list):
        for child in node:
            _classes(child, found)
    return found


def _mastery_gift_rule(world_type, name, class_name=None):
    """Only canonical earned signs for ordinary seeds of these new farms."""
    if (world_type not in ("hlights", "atlantis", "glen") or not name
            or world_type not in SPECS or world_type not in active_worlds()):
        return None
    item = _catalog_item(name)
    if (not item or item.get("type") != "decoration"
            or item.get("className") != "DynamicMasterySign"
            or (class_name is not None and class_name != item["className"])):
        return None
    crop = items.get_item_by_code(item.get("masteredItemCode"))
    if (not crop or crop.get("type") != "seed"
            or crop.get("name") not in allowed_seeds(world_type)
            or crop.get("mastery") not in (True, "true")):
        return None
    levels = crop.get("masteryLevel") or []
    levels = levels if isinstance(levels, list) else [levels]
    if not any(isinstance(level, dict) and level.get("gift") == name for level in levels):
        return None
    # This is an owned-item rule only: it is never added to the purchasable
    # catalog. The ordinary gift/inventory withdrawal must prove possession.
    return {"type": "decoration", "className": "DynamicMasterySign",
            "price": None, "masteryGift": True}


def _regional_cottage(item, world_type):
    """Only the crafting owner's recovered exact regional identity is excepted."""
    import crafting
    return (isinstance(item, dict)
            and crafting.regional_cottage(world_type, item.get("name"), item.get("className"))
            and crafting.COTTAGES.get(item.get("craftType")) == item.get("name"))


def _regional_snapshot(world_type, obj):
    import crafting
    return (isinstance(obj, dict)
            and crafting.regional_cottage(world_type, obj.get("itemName"), obj.get("className")))


def _world_feature(item, world_type):
    """Exact reviewed world contracts, never a special-class bypass."""
    if world_type == "rainforest":
        import rainforest_features
        return rainforest_features.rule(item, world_type)
    return None


def feature_policy_sources():
    import rainforest_features
    return rainforest_features.policy_sources()


def _feature_snapshot(world_type, obj):
    if not isinstance(obj, dict):
        return False
    item = _catalog_item(obj.get("itemName"))
    return bool(_world_feature(item, world_type)
                and obj.get("className") == item.get("className"))


def _reasons(item, world_type):
    """Empty list means admitted to the themed allow-list (price is separate)."""
    reasons = []
    if item.get("type") not in TYPES:
        reasons.append("type")
    regional = _regional_cottage(item, world_type)
    feature = _world_feature(item, world_type)
    if item.get("className") not in BASIC_CLASSES and not regional and not feature:
        reasons.append("class")
    if any(name != "World" for name in _classes(item.get("requirements"))):
        reasons.append("requirement")
    if not creative_worlds.world_requirement_matches(item, world_type):
        reasons.append("world")
    if item.get("features") and not feature:
        reasons.append("feature")
    for key in ("purchasePrereqs", "prereqs", "requiredMastery", "requiredQuest",
                "license", "marketPrereqs", "gateCode", "experiment", "experimentVariant"):
        if item.get(key) not in NONE_VALUES and not (key == "experimentVariant" and item[key] in (1, "1")):
            reasons.append(key)
    if (item.get("unlock") not in (None, "", "neighbor")
            and not (regional and item.get("unlock") == "instance_tiered")):
        reasons.append("unlock")
    if ((item.get("buyable") in (False, "false") and not (feature or {}).get("ownedOnly"))
            or item.get("placeable") in (False, "false")):
        reasons.append("unavailable")
    served = served_experiments()
    waived = retired_decor.waived_gates(item, world_type)
    if any(not _own_gate(g, world_type) or served.get(g) != 1 for g in _gates(item) if g not in waived):
        reasons.append("gate")
    return reasons


def _price(item, rates):
    """Original coin/cash price, or a converted Farm Cash charge for world currency."""
    market = item.get("market")
    if market in (None, "coins"):
        return {"currency": "coins", "amount": _whole(item.get("cost"), "coin price")}
    if market == "cash":
        return {"currency": "cash", "amount": _whole(item.get("cash"), "Farm Cash price")}
    if market in rates:
        return wcc.price_for_item(item, rates)
    raise ValueError(f"The {market} market has no recovered price.")


def _catalog():
    if getattr(items, "_cached_items", None) is None:
        items.load_items()
    return items.get_items()


@lru_cache(maxsize=None)
def catalog_rules(world_type):
    """Admitted items and expansion offers for one themed world, from the catalog."""
    spec = _spec(world_type)
    catalog = _catalog()
    rates = wcc.recovered_rates(catalog)
    admitted, unpriced, expansions = {}, {}, {}
    for item in catalog:
        # Ordinary global inventory buildings have no World requirement in the
        # original catalog. Admit only this narrow class so an empty themed farm
        # can acquire its own real storage capacity. Special cellars, other
        # containers and all other global items retain the existing boundary.
        global_inventory_building = (item.get("type") == "building"
            and item.get("className") == "StorageBuilding"
            and (item.get("storageType") or {}).get("itemClass") == "Inventory"
            and item.get("requirements") in NONE_VALUES)
        own_world_item = (any(node.get("className") == "World" and node.get("name") == world_type
                              for node in creative_worlds._nodes(item.get("requirements")))
                          or retired_decor.allows(item, world_type))
        feature = _world_feature(item, world_type)
        if not own_world_item and not global_inventory_building and not (feature or {}).get("worldless"):
            continue
        name = item.get("name")
        # Authored initial tier is display/admission only. Purchases below
        # resolve again against the live placed/gift count.
        import crafting
        try:
            item = crafting.regional_catalog_item(item, world_type)
        except ValueError as error:
            unpriced[name] = str(error)
            continue
        if item.get("subtype") == "expand_farm" and str(name).startswith(spec["prefix"] + "farm"):
            reasons = [r for r in _reasons(item, world_type) if r not in ("type", "class")]
            if reasons:
                continue
            try:
                price = _price(item, rates)
            except ValueError as error:
                unpriced[name] = str(error)
                continue
            expansions.setdefault(int(item["squares"]), []).append(
                {"name": name, "price": price, "gates": _gates(item)})
            continue
        if _reasons(item, world_type):
            continue
        try:
            price = None if (feature or {}).get("ownedOnly") else _price(item, rates)
        except ValueError as error:
            unpriced[name] = str(error)
            price = None
        admitted[name] = {"type": item.get("type"), "className": item.get("className"),
                          "price": price}
    return {"items": admitted, "unpriced": unpriced, "expansions": expansions,
            "rates": sorted(rates)}


def allowed_seeds(world_type):
    return sorted(n for n, r in catalog_rules(world_type)["items"].items() if r["type"] == "seed")


@lru_cache(maxsize=None)
def expansion_additions(world_type):
    """Original construct_0 objects granted with each land width (recorded only).

    Restoring them needs their construction state contract. Until then, a width
    that adds objects is refused by expand(); the initial farm stays playable.
    """
    _spec(world_type)
    settings = _xml("gameSettings.xml.gz")
    world = settings.find(f"farmExpansions/world[@name='{world_type}']")
    additions = {}
    if world is not None:
        for group in world.findall("farmExpansionAddedItems/addedItems"):
            additions[int(group.get("squares"))] = tuple(
                dict(node.attrib) for node in group.findall("addedItem"))
    return additions


def _widths(world_type):
    return {INITIAL_SIZE} | set(catalog_rules(world_type)["expansions"])


def plow_cost():
    """Every themed world, including currency worlds, plows at Home's coin rate.

    Deliberate deviation (user decision): a world-currency plow price is never
    converted. See THEMED_WORLDS.md and WORLD_CURRENCY_CONVERSION.md.
    """
    return get_farming_int("plowCost", 15)


def _plow_due(existing):
    """A plow is paid unless the saved plot is already plowed (a retry)."""
    return existing is None or existing.get("state") != "plowed"


def plow_charge(save, snapshot, existing):
    """Debit one Home-rate plow once; retries of a saved plowed plot are free.

    Insufficient coins raise before any mutation. Never reads a world currency.
    """
    cove_rules.guard_plow_snapshot(snapshot, existing)
    if not _plow_due(existing):
        return 0
    cost = plow_cost()
    key, balance = _balance(save, "coins")
    if balance < cost:
        raise ValueError("Not enough coins to plow in this themed farm.")
    save["userInfo"]["player"][key] -= cost
    return cost


def _world_user_state(save):
    return save["userInfo"].get("currentWorldType") or "farm"


def guard_snapshot(world_type, snapshot):
    """Check a themed world snapshot before travel or any farm operation."""
    rules = recovered_rules(world_type)
    if (not isinstance(snapshot, dict) or snapshot.get("tileSet") != rules["tileSet"]
            or snapshot.get("terrain") or snapshot.get("sizeX") != snapshot.get("sizeY")
            or snapshot.get("sizeX") not in _widths(world_type)
            or not isinstance(snapshot.get("objectsArray"), list)):
        raise ValueError(f"{rules['name']} requires its recovered ordinary-ground farm.")
    count = 0
    import crafting
    for obj in snapshot["objectsArray"]:
        mastery_rule = _mastery_gift_rule(world_type, obj.get("itemName")) if isinstance(obj, dict) else None
        if mastery_rule and obj.get("className") != mastery_rule["className"]:
            raise ValueError("A mastery sign must retain its canonical object class.")
        regional_name = (isinstance(obj, dict) and any(
            obj.get("itemName") == name for name, _ in crafting.REGIONAL_COTTAGES.values()))
        if regional_name and not _regional_snapshot(world_type, obj):
            raise ValueError("A regional cottage snapshot must retain its original world and class.")
        if (isinstance(obj, dict) and _world_feature(_catalog_item(obj.get("itemName")), world_type)
                and not _feature_snapshot(world_type, obj)):
            raise ValueError("A world feature snapshot must retain its original class.")
        if (not isinstance(obj, dict)
                or (obj.get("className") not in BASIC_CLASSES | {"Plot"}
                    and not _regional_snapshot(world_type, obj)
                    and not _feature_snapshot(world_type, obj)
                    and mastery_rule is None)):
            raise ValueError(f"The {rules['name']} snapshot contains an unsupported object.")
        if obj.get("className") == "Plot":
            if any(obj.get(flag) for flag in SPECIAL_PLOT_FLAGS):
                raise ValueError("Specialized plots are not restored.")
            count += 1
    if count > rules["plotCeiling"]:
        raise ValueError(f"{rules['name']} exceeds its recovered object ceiling.")
    return count


def _admit_snapshot_item(world_type, snapshot_item):
    rule = catalog_rules(world_type)["items"].get(snapshot_item) if snapshot_item else None
    if rule is None and snapshot_item:
        item = _catalog_item(snapshot_item)
        if (_world_feature(item, world_type) or {}).get("replacementOnly"):
            rule = {"type": item["type"], "className": item["className"], "price": None}
    if rule is None:
        rule = _mastery_gift_rule(world_type, snapshot_item)
    if snapshot_item and rule is None:
        raise ValueError("That item is not admitted to this themed farm.")
    return rule


def _guard_class(rule, snapshot, item_type):
    # Same rule as creative_worlds._guard_cove_item_class: the catalog class
    # (e.g. RotateableDecoration) wins; the per-type default applies only when
    # the catalog names none.
    expected = (rule or {}).get("className") or EXPECTED_CLASS.get(item_type)
    if expected and snapshot.get("className") != expected:
        raise ValueError("A themed item must retain its recovered object class.")


def _find(world_obj, snapshot):
    return next((obj for obj in world_obj["objectsArray"]
                 if obj.get("id") == snapshot.get("id")
                 or (snapshot.get("id") is not None and obj.get("tempId") == snapshot.get("id"))), None)


def _balance(save, currency):
    player = save["userInfo"]["player"]
    key = "gold" if currency == "coins" else "cash"
    value = player[key]
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("The currency balance is unavailable.")
    return key, value


def _charge_total(price, quantity):
    if price is None:
        raise ValueError("This item is not available for purchase.")
    return price["amount"] * quantity


def guard_purchase(save, item, currency=None, *, quantity=1, neighbor_count=0, existing=None, now=None):
    """Preflight an ordinary purchase; never debits."""
    world_type = _world_user_state(save)
    rule = catalog_rules(world_type)["items"].get(item.get("name")) if isinstance(item, dict) else None
    if rule is None:
        raise ValueError("That item is not admitted to this themed farm.")
    source = _catalog_item(item.get("name"))
    regional = _regional_cottage(source, world_type)
    if regional:
        if type(quantity) is not int or quantity != 1:
            raise ValueError("A regional cottage must be purchased one at a time.")
        # Neither a cached tier-one preview nor client-supplied price fields
        # authorize a live purchase. Identity and tier come from the catalog.
        if any(item.get(key) != source.get(key) for key in ("code", "className", "craftType")):
            raise ValueError("A regional cottage must retain its recovered catalog identity.")
        import crafting
        item = crafting.purchase_catalog_item(save, source)
        price = _price(item, {})  # helper accepts recovered coin/cash tiers only
    else:
        price = rule["price"]
    creative_worlds._guard_purchase_dates(item, now=now)
    creative_worlds._guard_item_access(save, item, neighbor_count=neighbor_count,
                                       quantity=quantity, existing=existing, world_type=world_type)
    if price is None:
        raise ValueError("This item is not available for purchase.")
    requested = currency or price["currency"]
    if requested == "gold":
        requested = "coins"
    if requested != price["currency"]:
        # The Market exposes a same-code cash button when a coin record also
        # authors a cash price. Use only explicit cash and the server catalog;
        # keep the cached primary price and the default route unchanged.
        source = _catalog_item(item.get("name"))
        owners = {node.get("name") for node in creative_worlds._nodes((source or {}).get("requirements"))
                  if node.get("className") == "World"}
        if (regional or currency != "cash" or price["currency"] != "coins" or not source
                or source.get("code") != item.get("code")
                or (source.get("market") or "coins") != "coins"
                or world_type not in owners):
            raise ValueError("The purchase currency does not match this item's recovered price.")
        price = {"currency": "cash", "amount": _whole(source.get("cash"), "alternate Farm Cash price")}
    key, balance = _balance(save, price["currency"])
    if balance < _charge_total(price, quantity):
        raise ValueError("Not enough currency for this themed farm purchase.")
    return price


def charge_purchase(save, item, currency=None, *, quantity=1, neighbor_count=0, existing=None, now=None):
    """Preflight, then debit the recovered price once for the whole quantity."""
    price = guard_purchase(save, item, currency, quantity=quantity, neighbor_count=neighbor_count,
                           existing=existing, now=now)
    total = _charge_total(price, quantity)
    key, _ = _balance(save, price["currency"])
    save["userInfo"]["player"][key] -= total
    return {"currency": price["currency"], "amount": total}


def guard_action(save, action, snapshot, params, *, neighbor_count=0, now=None):
    """Fence every themed action; purchases are preflighted, never debited here."""
    world_type = _world_user_state(save)
    guard_snapshot(world_type, save["world"])
    # Reject unsupported incoming plot variants before the shared handler can
    # merge them into the save. Otherwise a single placement could make every
    # later action and even travel fail the saved-snapshot guard above.
    if any(snapshot.get(flag) for flag in SPECIAL_PLOT_FLAGS):
        raise ValueError("Specialized plots are not restored.")
    feature = _world_feature(_catalog_item(snapshot.get("itemName")), world_type)
    if action not in ((feature or {}).get("actions") or ACTIONS):
        raise ValueError("This themed farm feature action is not restored.")
    if (action == "store" and snapshot.get("id") == storage_id(world_type)
            and snapshot.get("className") == "StorageBuilding" and snapshot.get("itemName") is None):
        # Original TInventoryStore addresses the inventory, not a farm object.
        # Shared storage still validates source, quantity, price and capacity.
        from storage import _given_options
        options = _given_options(params[0] if params and isinstance(params[0], dict) else {})
        if options.get("target", snapshot["id"]) != snapshot["id"]:
            raise ValueError("The themed inventory target must be the active world.")
        rule = _admit_snapshot_item(world_type, options.get("storedItemName"))
        if rule is None or rule.get("type") not in ("tree", "animal", "building", "decoration"):
            raise ValueError("That item cannot be stored in this themed inventory.")
        return
    world_obj = save["world"]
    existing = _find(world_obj, snapshot)
    if action == "store" and (feature or {}).get("container") and existing is not None:
        from storage import _given_options
        options = _given_options(params[0] if params and isinstance(params[0], dict) else {})
        if (options.get("target", existing["id"]) != existing["id"]
                or options.get("storedItemName", existing["itemName"]) == existing["itemName"]):
            raise ValueError("Storing this feature building's own progress is not restored; move it on the farm instead.")
    if action not in ("plow", "place") and existing is None:
        raise ValueError("A themed farm action requires its saved object.")
    if existing is not None and existing.get("itemName"):
        _admit_snapshot_item(world_type, existing["itemName"])
    replacement_retry = (action == "store" and existing is not None
        and _feature_snapshot(world_type, existing) and _feature_snapshot(world_type, snapshot)
        and (_catalog_item(snapshot.get("itemName")) or {}).get("finishedName") == existing.get("itemName"))
    if action not in ("place", "plow") and not replacement_retry and any(
            existing.get(key) != snapshot.get(key) for key in ("className", "itemName")):
        raise ValueError("A themed farm action cannot change its saved object's identity.")
    if action not in ("place", "plow", "move") and "position" in snapshot \
            and snapshot["position"] != (existing or {}).get("position"):
        raise ValueError("Only moving can change a themed object's position.")
    if action == "move" and existing is None:
        raise ValueError("Moving a themed object requires its saved object.")
    if action == "plow":
        cove_rules.guard_plow_snapshot(snapshot, existing)
        if _plow_due(existing):
            _, balance = _balance(save, "coins")
            if balance < plow_cost():
                raise ValueError("Not enough coins to plow in this themed farm.")
    item_name = snapshot.get("itemName")
    rule = _admit_snapshot_item(world_type, item_name) if item_name else None
    if action == "clear" and existing is not None and existing.get("className") == "Plot":
        _, balance = _balance(save, "coins")
        if balance < plow_cost():
            raise ValueError("Not enough coins to clear a themed plot.")
    if action in ("plow", "place") and snapshot.get("className") == "Plot" and rule is None:
        if action == "place":
            raise ValueError("Planting in a themed farm requires an admitted crop.")
    if rule is not None:
        if rule.get("masteryGift") and action not in ("place", "move"):
            raise ValueError("Only placing and moving this earned mastery sign are restored here.")
        _guard_class(rule, snapshot, rule["type"])
    if action == "place":
        if (snapshot.get("className") not in BASIC_CLASSES | {"Plot"}
                and not _regional_snapshot(world_type, snapshot)
                and not _feature_snapshot(world_type, snapshot)
                and _mastery_gift_rule(world_type, item_name, snapshot.get("className")) is None):
            raise ValueError("This themed object class is not restored.")
        from storage import _given_options
        options = _given_options(params[0] if params and isinstance(params[0], dict) else {})
        withdrawal = bool(options.get("isGift") or options.get("isInventoryWithdrawal")
                          or options.get("isStorageWithdrawal"))
        if not withdrawal and not creative_worlds._placement_retry(existing, snapshot, _catalog_item(item_name)):
            guard_purchase(save, _catalog_item(item_name), options.get("currency"),
                           neighbor_count=neighbor_count, existing=existing, now=now)
    if action in ("place", "plow", "move"):
        position = snapshot.get("position")
        if not isinstance(position, dict):
            raise ValueError("A themed placement requires a position.")
        size_source = _catalog_item(item_name) if item_name else {}
        for coordinate, dimension in (("x", "sizeX"), ("y", "sizeY")):
            value = position.get(coordinate)
            size = int((size_source or {}).get(dimension) or 1)
            if snapshot.get("className") == "Plot":
                size = max(4, size)
            if not world_travel._integer(value) or value < 0 or value + size > world_obj[dimension]:
                raise ValueError("The placement is outside the current themed land.")
        if position.get("z", 0) != 0:
            raise ValueError("Themed placements require ordinary ground terrain.")


def _catalog_item(name):
    return items.get_item_by_name(name) if name else {}



def summary_claims_storage(summary, storage_id):
    """Compare imported numeric inventory ownership without rewriting its form.

    WorldSummary stores its inventory ID as Number. Compare numeric text too,
    but preserve unknown and fractional imported IDs without truncating them.
    """
    if not isinstance(summary, dict):
        return False
    try:
        value = float(summary.get("storageId"))
    except (TypeError, ValueError, OverflowError):
        return False
    return math.isfinite(value) and value == storage_id


def create(save, world_type, option="allAccess", *, now):
    """Unlock one themed farm through its recovered all-access condition.

    No charge or item grant. Repeat calls return False without changing the save.
    Also requires the served experiments; they are read from the client config.
    """
    if world_type not in active_worlds():
        raise ValueError("This themed world is awaiting original-client acceptance.")
    rules = recovered_rules(world_type)
    if option != "allAccess":
        raise ValueError("Only this themed world's recovered all-access option is available.")
    world_travel.validate(save)
    user = save["userInfo"]
    active = user.get("currentWorldType") or "farm"
    if active not in world_travel.supported_worlds():
        raise ValueError("The imported active world cannot be replaced.")
    old_state = save.get(world_travel.STATE_KEY)
    if active == world_type or (old_state and world_type in old_state["inactive"]):
        return False
    # Imported unrelated worlds can claim an inventory even without an owned
    # snapshot. Never share, relabel or absorb their ledger on local creation.
    summaries = user.get("worldSummaryData")
    if not isinstance(summaries, dict) or any(
            name != world_type and summary_claims_storage(summary, rules["storageId"])
            for name, summary in summaries.items()):
        raise ValueError("The requested world inventory is already claimed by another world.")
    unlocked = user.get("unlockedWorldTypes", [])
    if not isinstance(unlocked, list) or not all(isinstance(name, str) for name in unlocked):
        raise ValueError("The imported world unlock state is invalid.")
    if (world_type in user["worldSummaryData"] or world_type in unlocked
            or user["player"]["storageData"].get(str(rules["storageId"]))):
        raise ValueError("The requested world snapshot is missing; it cannot be recreated safely.")
    if (xp_to_level(user["player"]["xp"]) or 0) < rules["minimumLevel"]:
        raise ValueError(f"{rules['name']} requires player level {rules['minimumLevel']}.")
    served = served_experiments()
    if any(served.get(rules["experiments"][k]) != 1 for k in ("master", "forAll")):
        raise ValueError(f"{rules['name']}'s all-access experiment is not served.")
    state = copy.deepcopy(old_state)
    if state is None:
        next_id = max(world_travel._reserved_ids(save), default=0) + 1
        if next_id > world_travel.MAX_OBJECT_ID + 1:
            raise ValueError("An imported storage ID exceeds the supported object ID range.")
        state = {"version": 1, "inactive": {}, "nextObjectId": next_id}
    size = rules["initialSize"]
    state["inactive"][world_type] = {"id": 2, "uid": str(uuid.uuid4()), "sizeX": size,
        "sizeY": size, "objectsArray": [], "messageManager": [], "tileSet": rules["tileSet"],
        "localStarter": rules["localStarter"]}
    new_user = copy.deepcopy(user)
    new_user["worldSummaryData"][world_type] = {"firstLoaded": now, "lastLoaded": now,
                                                "storageId": rules["storageId"]}
    new_user["unlockedWorldTypes"] = list(dict.fromkeys([*unlocked, "farm", world_type]))
    new_user["player"]["storageData"].setdefault(str(rules["storageId"]), {})
    marker = {**copy.deepcopy(save.get(creative_worlds.ACCESS_MARKER, {})), world_type:
              {"version": 1, "option": option, "purchasedAt": now, "cashPaid": 0,
               "storyRestored": False}}
    working = {**save, "userInfo": new_user, world_travel.STATE_KEY: state,
               creative_worlds.ACCESS_MARKER: marker}
    world_travel.validate(working)
    save["userInfo"] = new_user
    save[world_travel.STATE_KEY] = state
    save[creative_worlds.ACCESS_MARKER] = marker
    return True


def expand(save, item, currency, *, neighbor_count=0, now=None):
    """Buy the next themed land width; returns True, or raises."""
    world_type = _world_user_state(save)
    rules = recovered_rules(world_type)
    guard_snapshot(world_type, save["world"])
    if not isinstance(item, dict) or item.get("subtype") != "expand_farm":
        raise ValueError("Themed farms require their own recovered land expansions.")
    offers = catalog_rules(world_type)["expansions"]
    squares = int(item.get("squares") or 0)
    current = save["world"]["sizeX"]
    if squares == current:
        return True
    next_width = min((w for w in offers if w > current), default=None)
    if squares != next_width:
        raise ValueError("Buy themed land expansions in their original order.")
    if world_type == "rainforest":
        import rainforest_rules
        rainforest_rules.guard_land_growth(item)
    if expansion_additions(world_type).get(squares):
        raise ValueError("This themed expansion adds original objects that are not restored.")
    offer = next((o for o in offers[squares] if o["name"] == item.get("name")), None)
    if offer is None:
        raise ValueError("That themed expansion is not available for purchase.")
    if any(not _own_gate(g, world_type) or served_experiments().get(g) != 1 for g in offer["gates"]):
        raise ValueError("That themed expansion's experiment is not enabled.")
    if (xp_to_level(save["userInfo"]["player"]["xp"]) or 0) < int(item.get("requiredLevel") or 1):
        raise ValueError("The player's level is too low for this expansion.")
    if neighbor_count < int(item.get("minNeighbors") or 0):
        raise ValueError("This expansion requires more neighbors.")
    price = offer["price"]
    requested = currency or price["currency"]
    if requested == "gold":
        requested = "coins"
    if requested != price["currency"]:
        raise ValueError("The purchase currency does not match this expansion's recovered price.")
    # ChangeFarmItem.saleCash is 1 for expand_farm, as Lighthouse Cove and Meadows apply.
    cost = 1 if price["currency"] == "cash" else price["amount"]
    key, balance = _balance(save, price["currency"])
    if balance < cost:
        raise ValueError("Not enough currency for this themed expansion.")
    save["userInfo"]["player"][key] -= cost
    save["world"]["sizeX"] = save["world"]["sizeY"] = squares
    return True


def recovered_record(world_type):
    """A JSON-serializable record used by the tests and the documentation."""
    rules = recovered_rules(world_type)
    catalog = catalog_rules(world_type)
    additions = expansion_additions(world_type)
    return {**rules, "allowedSeeds": allowed_seeds(world_type),
            "expansionAddedWidths": sorted(additions),
            "expansionAddedObjects": sum(len(v) for v in additions.values()),
            "admittedItems": len(catalog["items"]), "unpricedItems": len(catalog["unpriced"]),
            "expansionWidths": sorted(catalog["expansions"]), "rates": catalog["rates"]}
