"""Original cottage crafting, independently recovered from the bundled client.

The bounded recipes are ordinary skill-level-one through five goods of the
Home cottages, Pub, Mistletoe Lane, Cove restaurant and Herbal Hut. Seasonal recipes keep their
original availability windows. Regional world/UI admission is integrated by
its owning modules; accepting a recipe here does not open a world purchase.
TBuyBushel, TBeginRecipe, TClaimFinishedRecipes, RecipeItem.fromPhpObject,
RecipeState.addExperience and CraftingUseGoodsWindow define the wire contract.
The archived crafting.xml supplies ingredients, timers, output, XP and fuel.
No files or sessions are opened here; the caller's village transaction commits.
"""
import copy
from functools import lru_cache
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import zlib

from bundle import XML_DIR
import engine
import items
import quests
import progression
import storage
from engine import timestamp_now

HOME_COTTAGES = {"bakery": "craftingbakery", "winery": "craftingwinery",
                 "perfumery": "craftingspa", "pub": "xukcraftingpub"}
# Each reviewed craftSkills entry names an ordinary CraftingRecipeQueueManager
# cottage and uses the original global recipe/skill ladders unchanged.
# World admission and the prepared client's upgrade controls are separate
# integration gates; this map does not admit any other regional building.
REGIONAL_COTTAGES = {"xhdcrafttype": ("xhdcraftingcottage", "htown"),
                     "restaurant": ("xcovecraftingcottage", "fisherman"),
                     "xrfcrafttype": ("xrfcraftingcottage", "rainforest")}
# Pub remains readable/usable on legacy Home profiles. The original England
# identity is a second owner, with its own skill, recipes and production.
# Bushels and crafted-good gifts remain the original global inventories.
PUB_WORLD_STATE = "localWorldCrafting"
PUB_WORLDS = frozenset(("farm", "england"))
COTTAGES = HOME_COTTAGES | {craft: spec[0] for craft, spec in REGIONAL_COTTAGES.items()}
REGIONAL_RECIPES = {"xhdcrafttype": frozenset((
    "8WE", "8WC", "8WA", "ccL", "8WG", "8Wy", "8Ww", "8Ws", "8Wo",
    "8Wm", "caC", "8Wk", "8Wi", "8Wg", "8Wu", "8We", "8Wq")),
    # Eighteen ordinary restaurant rows, including the expired 2011 recipe.
    # h1O is a Craftshop sharing-loot recipe, without authored output counts.
    # Availability dates remain enforced by _guard_recipe_dates.
    "restaurant": frozenset(("0b9", "0b6", "0bx", "0bN", "0ca", "0b5", "0bL",
        "7Jp", "0bu", "0b2", "0bT", "0bP", "0a8", "0bB", "7KI", "0bv", "0ba",
        "0kS")),
    "xrfcrafttype": frozenset((
        "r34", "jxat", "r7a", "sea", "sgc", "r95", "sd7", "r3c", "sgw",
        "r9t", "sg3", "sfs", "sey", "r0q", "sf1", "sdk", "sec", "sfu",
        "sen", "se5", "sbf"))}
# Three reviewed Herbal Hut rows start below the usual skill-level default.
# Keep their authored recipe levels; this is not permission for other recipes
# or future XML rows to bypass the ordinary cottage contract.
REGIONAL_INITIAL_LEVELS = {"jxat": "1", "r0q": "6", "sfu": "9"}
# Reviewed immutable codes, not a broad inference from arbitrary future XML.
# Every row is skill 1, initial recipe level 1, nondeprecated, prerequisite-free,
# with an ordinary bushel ingredient array and same-code crafted-good output.
LEVEL_ONE_RECIPES = {
    "bakery": frozenset(("b0", "b1", "b2", "@c", "8yY", "8z6", "0fY", "0w4", "02y",
                          "v7", "tk", "@v", "f(", "P)", "0Wk")),
    "winery": frozenset(("0hu", "w0", "w1", "w2", "@*", "8zz", "0w0", "02x", "v8",
                          "tl", "@w", "j(", "M)", "0Wm")),
    "perfumery": frozenset(("p0", "p1", "p2", "^m", "0gC", "0xc", "02w", "o12", "v9",
                             "tm", "@x", "g(", "N)", "0Wn")),
    "pub": frozenset(("ln", "lq", "@@", "lj", "0gW", "mn5", "@y", "h(", "O)", "o2kt")),
}
HIGHER_SKILL_RECIPES = {
    "bakery": frozenset(("b3", "b4", "b5", "b6", "b7", "b8", "7KJ", "c0", "c1", "c2", "c3", "c4", "c5", "7Kw", "0gl", "0xf", "0Y1")),
    "winery": frozenset(("0f8", "w3", "w4", "w5", "7J5", "w6", "w7", "w8", "w9", "c6", "c7", "c8", "c9", "d1", "7JR", "0su", "0Zc")),
    "perfumery": frozenset(("0fW", "p3", "p4", "p5", "p6", "p7", "p8", "7HT", "p9", "d2", "d3", "d4", "d5", "d6", "7H4", "0wW", "0Zd")),
    "pub": frozenset(("lu", "ls", "7IR", "lv", "lr", "0hh", "7In")),
}
RECIPES_BY_CRAFT = ({craft: LEVEL_ONE_RECIPES[craft] | HIGHER_SKILL_RECIPES[craft]
                     for craft in HOME_COTTAGES} | REGIONAL_RECIPES)
RECIPES = frozenset().union(*RECIPES_BY_CRAFT.values())
FREE_COTTAGES = frozenset(("bakery", "winery", "perfumery"))
CRAFTED_GOODS_ID = "-7"  # FarmGameWorld.CRAFTEDGOODS_ID, signed int constant.
METHODS = frozenset(("FarmService.onPurchaseBushel", "CraftingService.onBeginRecipe",
                     "CraftingService.onClaimFinishedRecipes", "CraftingService.onUseCraftedGood",
                     "CraftingService.onClaimFreeCottage", "CraftingService.onCompleteCottageTutorial",
                     "CraftingService.onMarkCottageHistorySeen", "CraftingService.onBuyCraftUpgrade",
                     "CraftingService.onRushRecipe"))


def _int(value, label, minimum=0, maximum=2_147_483_647):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or int(value) != value or not minimum <= value <= maximum):
        raise ValueError(f"{label} must be a whole number from {minimum} to {maximum}.")
    return int(value)


@lru_cache(maxsize=1)
def _catalog():
    root = ET.fromstring(zlib.decompress((Path(XML_DIR) / "gz/v855098/crafting.xml.gz").read_bytes()))
    recipes = {r.get("id"): r for r in root.find("recipes") if r.get("id") in RECIPES}
    return root, recipes


@lru_cache(maxsize=2)
def _client_payload(raw):
    root = ET.fromstring(zlib.decompress(raw))
    for recipe in root.find("recipes"):
        if recipe.findtext("craft") in COTTAGES and recipe.get("id") not in RECIPES:
            # The original manager checks comingSoon before saved unlock state.
            # onBuilt.grantDefaultRecipes cannot reopen these unaccepted goods.
            field = recipe.find("ComingSoon")
            if field is None:
                field = ET.SubElement(recipe, "ComingSoon")
            field.text = "1"
    return zlib.compress(ET.tostring(root, encoding="utf-8"))


def client_payload():
    """A display-only projection; retain every recipe, date, price and clock."""
    source = Path(XML_DIR) / "gz/v855098/crafting.xml.gz"
    return _client_payload(source.read_bytes())


def _recipe(code):
    if not isinstance(code, str) or code not in RECIPES:
        raise ValueError("This recipe is outside the supported original cottage recipes.")
    recipe = _catalog()[1][code]
    if recipe.findtext("Deprecated") != "0" or recipe.find("prereqs") is not None:
        raise ValueError("This recipe has unsupported availability requirements.")
    skill = recipe.findtext("SkillLevelRequired")
    initial = recipe.findtext("InitialRecipeLevel")
    if (skill not in ("1", "2", "3", "4", "5") or initial != REGIONAL_INITIAL_LEVELS.get(code,
                {"1": "1", "2": "3", "3": "6", "4": "9", "5": "12"}[skill])
            or code not in RECIPES_BY_CRAFT.get(recipe.findtext("craft"), ())):
        raise ValueError("This recipe is outside the recovered cottage skill contract.")
    if recipe.find("Reward/OnFinish").get("itemCode") != code:
        raise ValueError("This recipe's distinct product code is not supported.")
    return recipe


def _php_xml(element):
    result = {"@attributes": dict(element.attrib)} if element.attrib else {}
    for child in element:
        value = _php_xml(child) if len(child) or child.attrib else (child.text or "").strip()
        if child.tag in result:
            if not isinstance(result[child.tag], list):
                result[child.tag] = [result[child.tag]]
            result[child.tag].append(value)
        else:
            result[child.tag] = value
    return result


def _normalize_empty_contents(snapshot):
    # StorageBuilding.getSaveObject emits an empty associative Object, while
    # its inherited loadObject (AS3 1843) coerces truthy contents to Array.
    # Repair only the proven empty case for the managed cottages. Never
    # reinterpret nonempty imported storage rows or another building class.
    if (snapshot.get("itemName") in COTTAGES.values()
            and snapshot.get("className") == "CraftingCottageBuilding"
            and snapshot.get("contents") == {}):
        snapshot["contents"] = []


def _cottages(save, craft):
    if craft in HOME_COTTAGES and craft != "pub" and _world(save) != "farm":
        return []
    if craft == "pub" and _world(save) not in PUB_WORLDS:
        return []
    if craft in REGIONAL_COTTAGES and _world(save) != REGIONAL_COTTAGES[craft][1]:
        return []
    objects = save.get("world", {}).get("objectsArray", [])
    result = [o for o in objects
            if o.get("itemName") == COTTAGES[craft] and o.get("isFullyBuilt") is not False
            and o.get("state") not in ("construction", "constructing")]
    for cottage in result:
        ident = _int(cottage.get("id"), "Saved cottage object ID")
        if (cottage.get("className") != "CraftingCottageBuilding"
                or sum(o.get("id") == ident for o in objects) != 1):
            raise ValueError("The cottage's saved class or unique object identity is invalid.")
    return result


def _state(save):
    state = save.setdefault("craftingState", {})
    if not isinstance(state, dict):
        raise ValueError("The saved crafting state is malformed.")
    return state



@lru_cache(maxsize=1)
def _pub_recipe_codes():
    return frozenset(row.get("id") for row in _catalog()[0].find("recipes")
                     if row.findtext("craft") == "pub")


def _pub_partition(state):
    """Copy only the Pub projection; leave global inventory/metadata in place."""
    skill = state.setdefault("craftingSkillState", {})
    if not isinstance(skill, dict):
        raise ValueError("The saved crafting skills are malformed.")
    recipe_states = skill.setdefault("recipeStates", [])
    craft_states = skill.setdefault("craftTypes", [])
    queues = state.setdefault("recipeQueue", {})
    inventory = state.setdefault("craftingPublicInventory", {})
    if not isinstance(inventory, dict):
        raise ValueError("The saved crafting public inventory is malformed.")
    public = inventory.setdefault("publicGoods", {})
    if (not isinstance(recipe_states, list) or not isinstance(craft_states, list)
            or any(not isinstance(row, dict) for row in [*recipe_states, *craft_states])
            or not isinstance(queues, dict) or not isinstance(public, dict)):
        raise ValueError("The saved Pub projection is malformed.")
    result = {"recipeStates": [copy.deepcopy(row) for row in recipe_states
                               if row.get("m_type") in _pub_recipe_codes()],
              "craftTypes": [copy.deepcopy(row) for row in craft_states if row.get("type") == "pub"]}
    if "pub" in queues:
        result["queue"] = copy.deepcopy(queues["pub"])
    if "pub" in public:
        result["publicGoods"] = copy.deepcopy(public["pub"])
    return result


def _restore_pub_partition(state, partition):
    if (not isinstance(partition, dict) or set(partition) - {"recipeStates", "craftTypes", "queue", "publicGoods"}
            or not isinstance(partition.get("recipeStates"), list)
            or not isinstance(partition.get("craftTypes"), list)
            or any(not isinstance(row, dict) or row.get("m_type") not in _pub_recipe_codes()
                   for row in partition["recipeStates"])
            or any(not isinstance(row, dict) or row.get("type") != "pub" for row in partition["craftTypes"])
            or ("queue" in partition and not isinstance(partition["queue"], list))
            or ("publicGoods" in partition and not isinstance(partition["publicGoods"], dict))):
        raise ValueError("The saved world Pub partition is malformed.")
    _pub_partition(state)
    skill = state["craftingSkillState"]
    skill["recipeStates"] = [row for row in skill["recipeStates"]
                             if row.get("m_type") not in _pub_recipe_codes()] + copy.deepcopy(partition["recipeStates"])
    skill["craftTypes"] = [row for row in skill["craftTypes"] if row.get("type") != "pub"] + copy.deepcopy(partition["craftTypes"])
    for field, target in (("queue", state["recipeQueue"]),
                          ("publicGoods", state["craftingPublicInventory"]["publicGoods"])):
        target.pop("pub", None)
        if field in partition:
            target["pub"] = copy.deepcopy(partition[field])


def _pub_owners(save):
    active = _world(save)
    worlds = {active: save.get("world", {})}
    inactive = save.get("_ownedWorldTravel", {}).get("inactive", {})
    if isinstance(inactive, dict):
        worlds.update(inactive)
    return {name for name, world in worlds.items() if name in PUB_WORLDS and any(
        isinstance(obj, dict) and obj.get("itemName") == COTTAGES["pub"]
        for obj in world.get("objectsArray", []))}


def _project_pub_context(save, *, create=False):
    """Select the active Pub without reinterpreting unknown imported progress.

    The old service's unlabelled Pub belongs to Home. An imported active
    England Pub can retain its existing state only when England is the sole
    Pub owner. Two owners plus unpartitioned progress are an explicit recovery
    case; no XP, recipes, queues or metadata are guessed, copied or discarded.
    """
    state = _state(save)
    scope = "england" if _world(save) == "england" else "farm"
    namespace = state.get(PUB_WORLD_STATE)
    if namespace is None:
        if scope != "england" and not create:
            return
        initial = "farm"
        if scope == "england":
            owners = _pub_owners(save)
            partition = _pub_partition(state)
            if owners == PUB_WORLDS and any(partition.values()):
                raise ValueError("Imported Home and England Pubs share unlabelled production; recover each owner's state before using either Pub.")
            if owners == {"england"}:
                initial = "england"
        namespace = {"version": 1, "activePubWorld": initial, "pubStates": {}}
        state[PUB_WORLD_STATE] = namespace
    if (not isinstance(namespace, dict) or namespace.get("version") != 1
            or namespace.get("activePubWorld") not in PUB_WORLDS
            or not isinstance(namespace.get("pubStates"), dict)
            or set(namespace["pubStates"]) - PUB_WORLDS
            or namespace["activePubWorld"] in namespace["pubStates"]):
        raise ValueError("The saved world Pub state is malformed.")
    current = namespace["activePubWorld"]
    if current == scope:
        return
    outgoing = _pub_partition(state)
    incoming = namespace["pubStates"].get(scope, {"recipeStates": [], "craftTypes": []})
    _restore_pub_partition(state, incoming)
    namespace["pubStates"][current] = outgoing
    namespace["pubStates"].pop(scope, None)
    namespace["activePubWorld"] = scope


def before_world_switch(save, destination):
    """Capture the old owner's Pub before swapping the active world object."""
    _project_pub_context(save, create=destination == "england")


def after_world_switch(save):
    """Load only the destination owner's Pub; initialize() supplies preview state."""
    _project_pub_context(save)

def _initialize(save):
    _project_pub_context(save)
    state = _state(save)
    # The client uses this server field directly as its bushel capacity. Old
    # templates predate the archived global limit; retain larger saved upgrades.
    state["maxCapacity"] = max(
        int(_catalog()[0].findtext("featureConfig/globalInventoryBushelCapacity")),
        _int(state.get("maxCapacity", 0), "Saved bushel capacity"))
    skill = state.setdefault("craftingSkillState", {})
    recipe_states = skill.setdefault("recipeStates", [])
    craft_states = skill.setdefault("craftTypes", [])
    queues = state.setdefault("recipeQueue", {})
    public = state.setdefault("craftingPublicInventory", {}).setdefault("publicGoods", {})
    state.setdefault("craftingItems", [])
    if (not isinstance(recipe_states, list) or not isinstance(craft_states, list)
            or not isinstance(queues, dict) or not isinstance(public, dict)
            or not isinstance(state["craftingItems"], list)):
        raise ValueError("The saved crafting inventories are malformed.")
    for craft in COTTAGES:
        cottages = _cottages(save, craft)
        if not cottages:
            if ((craft == "pub" and _world(save) == "england")
                    or (craft in REGIONAL_COTTAGES and _world(save) == REGIONAL_COTTAGES[craft][1])):
                if _world(save) == "england" or _regional_world_active(_world(save)):
                    # maximumSlots (served AS3 22573) reads the skill's level
                    # during placement preview, before onBuilt can create it.
                    # Level one is the archived zero-cost, zero-XP starting
                    # state; recipes and onboarding still require ownership.
                    matches = [r for r in craft_states if r.get("type") == craft]
                    if len(matches) > 1:
                        raise ValueError("Duplicate saved craft skill states.")
                    if not matches:
                        craft_states.append({"type": craft, "level": 1, "xp": 0, "exp": 0})
                    else:
                        _int(matches[0].get("level"), "Craft level", 1, 5)
                        for field in ("xp", "exp"):
                            if field in matches[0]:
                                _int(matches[0][field], f"Saved craft {field}")
            continue
        if len(cottages) != 1:
            raise ValueError("Multiple cottages of one supported craft are ambiguous.")
        cottage = cottages[0]
        _normalize_empty_contents(cottage)
        matches = [r for r in craft_states if r.get("type") == craft]
        if len(matches) > 1:
            raise ValueError("Duplicate saved craft skill states.")
        if not matches:
            craft_states.append({"type": craft, "level": _int(cottage.get("craftLevel", 1), "Craft level", 1, 5), "xp": 0, "exp": 0})
        craft_state = next(row for row in craft_states if row.get("type") == craft)
        craft_level = _int(craft_state.get("level"), "Craft level", 1, 5)
        if craft not in queues:
            queues[craft] = copy.deepcopy(cottage.get("recipeQueue") or [])
        if not isinstance(queues[craft], list):
            raise ValueError("The saved recipe queue is malformed.")
        if craft in REGIONAL_COTTAGES and any(
                not isinstance(row, dict) or row.get("worldType") != _craft_owner(save, craft)
                for row in queues[craft]):
            raise ValueError("The saved regional recipe queue belongs to another farm.")
        if craft == "pub" and any(not isinstance(row, dict) or (
                row.get("worldType") != _world(save)
                and not (_world(save) == "farm" and "worldType" not in row)) for row in queues[craft]):
            raise ValueError("The saved Pub recipe queue belongs to another farm.")
        public.setdefault(craft, copy.deepcopy(cottage.get("finishedRecipes") or {}))
        # CraftingMainWindow shows the next craft level too. Its recipe slots
        # dereference a saved RecipeState even for locked, unimplemented goods.
        # Supplying that display state does not extend the service allowlist.
        for recipe in _catalog()[0].find("recipes"):
            if recipe.findtext("craft") != craft or recipe.findtext("Deprecated") != "0":
                continue
            code = recipe.get("id")
            matches = [r for r in recipe_states if r.get("m_type") == code]
            if len(matches) > 1:
                raise ValueError("Duplicate saved recipe skill states.")
            if not matches:
                recipe_states.append({"m_type": code, "m_level": int(recipe.findtext("InitialRecipeLevel")),
                                      "m_experience": 0, "m_isUnlocked": code in RECIPES
                                      and int(recipe.findtext("SkillLevelRequired")) <= craft_level})
            elif code in RECIPES and int(recipe.findtext("SkillLevelRequired")) <= craft_level:
                # Eligible original goods unlock automatically. Old
                # local releases supplied false placeholders before restoration.
                # Keep experience, level and imported metadata unchanged.
                matches[0]["m_isUnlocked"] = True
        _sync(save, craft)
    return state


def initialize(save):
    """Prepare owned cottages and the active regional placement-preview skill."""
    working = copy.deepcopy(save)
    _initialize(working)
    save.clear(); save.update(working)


def start_session(save):
    """Fresh Flash sessions restart sequence numbers; queued goods survive."""
    initialize(save)
    _state(save)["localCraftingRequests"] = {}
    _state(save).pop("localCraftingHighestSequence", None)


def _sync(save, craft):
    state = _state(save)
    craft_state = next(row for row in state["craftingSkillState"]["craftTypes"] if row.get("type") == craft)
    for cottage in _cottages(save, craft):
        cottage["craftLevel"] = _int(craft_state.get("level"), "Craft level", 1, 5)
        cottage["recipeQueue"] = copy.deepcopy(state["recipeQueue"][craft])
        cottage["finishedRecipes"] = copy.deepcopy(state["craftingPublicInventory"]["publicGoods"][craft])


def preserve_fields(stored, incoming):
    """Move/store snapshots cannot overwrite cottage production or identity."""
    result = copy.deepcopy(incoming)
    if stored and stored.get("itemName") in COTTAGES.values():
        for key in ("itemName", "className", "isFullyBuilt", "state", "recipeQueue", "finishedRecipes", "craftLevel", "foundingTS", "cottageName",
                    "transactionHistory", "historyLastViewedTS", "historyXPGain", "pendingLevelUpFeed", "contents"):
            if key in stored:
                result[key] = copy.deepcopy(stored[key])
            else:
                result.pop(key, None)
    elif stored and incoming.get("itemName") in COTTAGES.values():
        raise ValueError("A cottage snapshot cannot replace another farm object.")
    if stored and stored.get("className") == "RecipeMasterySign":
        # loadObject reads level directly. Moving/storing a sign cannot import
        # the client's star count or change which recipe it belongs to.
        for key in ("itemName", "className", "level"):
            if key in stored:
                result[key] = copy.deepcopy(stored[key])
            else:
                result.pop(key, None)
    _normalize_empty_contents(result)
    return result


def guard_action(save, action, snapshot):
    """Reject alternate world actions that could replace/erase production."""
    ident = snapshot.get("id")
    existing = [o for o in save.get("world", {}).get("objectsArray", []) if o.get("id") == ident]
    managed = any(o.get("itemName") in COTTAGES.values() for o in existing)
    if not managed and snapshot.get("itemName") not in COTTAGES.values():
        return
    if len(existing) > 1:
        raise ValueError("A crafting cottage must have one unique saved object ID.")
    _int(ident, "Cottage object ID")
    if managed:
        craft = next(c for c, name in COTTAGES.items() if name == existing[0]["itemName"])
        _craft_world(save, craft)
    if action == "getStorageInfo":
        # TUpgradeStorage(TYPE_UPDATE) reads only the legacy social-upgrade
        # status. The commands layer returns the owned container's status;
        # this request never imports the client's production snapshot.
        if not managed or not existing:
            raise ValueError("Storage information requires an existing owned cottage.")
        return
    if not existing and action != "place":
        raise ValueError("This action requires an existing saved crafting cottage.")
    if (not existing and snapshot.get("className") != "CraftingCottageBuilding"):
        raise ValueError("A new cottage must have the original catalog class.")
    if not existing and action == "place":
        name = snapshot.get("itemName")
        craft = next(c for c, cottage in COTTAGES.items() if cottage == name)
        _craft_world(save, craft)
        item = items.get_item_by_name(name)
        if not item or item.get("className") != "CraftingCottageBuilding":
            raise ValueError("The cottage is not in the original catalog.")
        if any(o.get("itemName") == name for o in save["world"]["objectsArray"]):
            raise ValueError("Only one cottage of each craft can be placed.")
        if (engine.xp_to_level(save["userInfo"]["player"]["xp"]) or 0) < int(item["requiredLevel"]):
            raise ValueError("The player's level is too low for this cottage.")
    if action not in ("place", "move", "sell", "clear", "stash"):
        raise ValueError("This world action is not supported for a crafting cottage.")
    if managed and action in ("sell", "clear", "stash"):
        cottage = existing[0]
        craft = next(c for c, name in COTTAGES.items() if name == cottage["itemName"])
        state = _state(save)
        queue = state.get("recipeQueue", {}).get(craft, cottage.get("recipeQueue") or [])
        public = state.get("craftingPublicInventory", {}).get("publicGoods", {}).get(craft, cottage.get("finishedRecipes") or {})
        if queue or any(_int(row.get("qty", 0), "Saved public goods quantity") for row in public.values()):
            raise ValueError("Collect or sell the cottage's production before removing it.")


def initialize_placement(snapshot):
    result = copy.deepcopy(snapshot)
    if result.get("itemName") in COTTAGES.values():
        if result.get("className") != "CraftingCottageBuilding":
            raise ValueError("A new cottage must have the original catalog class.")
        result.update(recipeQueue=[], finishedRecipes={}, craftLevel=1)
        result.setdefault("contents", [])
        _normalize_empty_contents(result)
        for key in ("foundingTS", "cottageName", "transactionHistory", "historyLastViewedTS",
                    "historyXPGain", "pendingLevelUpFeed"):
            result.pop(key, None)
    return result


def finish_placement(save, snapshot, *, now=None):
    """Mirror onBuilt once, after a new completed cottage is actually placed.

    Loading an imported cottage must never award onboarding or reset its clock.
    The original bonus is already started by the client, without a begin RPC.
    """
    craft = next((c for c, name in COTTAGES.items() if name == snapshot.get("itemName")), None)
    if craft is None or snapshot not in _cottages(save, craft):
        return
    now = _int(timestamp_now() if now is None else now, "Cottage founding time", 1)
    snapshot.setdefault("foundingTS", now)
    state = _initialize(save)
    flags = save["userInfo"]["player"].setdefault("seenFlags", {})
    item_code = items.get_item_by_name(snapshot["itemName"])["code"]
    pending = (state.get("localCottageOnboardingPending") == item_code
               or state.get("localCottageFirstPlacementPending") is True)
    if state.get("localCottageOnboardingGranted") or (flags.get("placeCottage") and not pending):
        return
    # This is the same one-time flag read by CraftingCottageBuilding.onBuilt.
    flags["placeCottage"] = True
    state["localCottageOnboardingGranted"] = True
    state.pop("localCottageOnboardingPending", None)
    state.pop("localCottageFirstPlacementPending", None)
    skill = next(e for e in _catalog()[0].find("craftSkills") if e.get("id") == craft)
    code = skill.findtext("defaultRecipe")
    recipe = _recipe(code)
    inventory = state["craftingItems"]
    for ingredient, amount in _ingredients(recipe).items():
        matches = [r for r in inventory if r.get("itemCode") == ingredient]
        if len(matches) > 1:
            raise ValueError("Duplicate saved bushel stacks cannot receive cottage onboarding.")
        if matches:
            matches[0]["quantity"] = _int(matches[0]["quantity"], "Saved bushel quantity") + amount
        else:
            inventory.append({"itemCode": ingredient, "quantity": amount, "price": None})
    bonus = copy.deepcopy(recipe)
    bonus.find("MinutesToCook").text = "0.1"
    queue = state["recipeQueue"][craft]
    occupied = _occupied_ovens(queue, 2)
    if len(occupied) == 2:
        raise ValueError("The first cottage has no free onboarding oven.")
    queue.append({"id": code, "recipe": _php_xml(bonus), "recipeInitialRecipeLevel": 1,
                  "start_ts": 1, "finish_ts": now + 5, "ovenSlot": min({0, 1} - occupied),
                  "worldType": _world(save), "recipeLevel": 1})
    _sync(save, craft)


def acknowledge_seen_flag(save, flag):
    """Keep first placement eligibility if its original seen-flag RPC arrives first.

    Imported flags are not evidence of a new placement and never pass here.
    The normal command still persists the original client flag.
    """
    if (flag == "placeCottage"
            and not save["userInfo"]["player"].get("seenFlags", {}).get(flag)
            and not _state(save).get("localCottageOnboardingGranted")
            and not any(_cottages(save, craft) for craft in COTTAGES)):
        _state(save)["localCottageFirstPlacementPending"] = True


def _home(save):
    if (save["userInfo"].get("currentWorldType") or "farm") != "farm":
        raise ValueError("This cottage service requires the home farm.")


def _world(save):
    return save["userInfo"].get("currentWorldType") or "farm"


def _craft_owner(save, craft):
    return _world(save) if craft == "pub" else REGIONAL_COTTAGES.get(craft, (None, "farm"))[1]
def _regional_world_active(world):
    # Cove is one of the four original base worlds, outside SPECS. Recheck its
    # recovered contract instead of waiving admission for every base world.
    if world == "fisherman":
        import cove_rules
        return cove_rules.recovered_rules()["worldType"] == world
    import themed_worlds
    return world in themed_worlds.active_worlds()


def _craft_world(save, craft):
    if craft == "pub":
        if _world(save) not in PUB_WORLDS:
            raise ValueError("The Pub requires Home or its original England farm.")
    elif craft in REGIONAL_COTTAGES:
        world = REGIONAL_COTTAGES[craft][1]
        if _world(save) != world:
            raise ValueError("This regional cottage requires its original farm.")
        if not _regional_world_active(world):
            raise ValueError("This regional cottage's original farm is not active.")
    else:
        _home(save)


def regional_cottage(world_type, name, class_name="CraftingCottageBuilding"):
    """Narrow identity exception for the world owner's purchase/snapshot gates."""
    return (class_name == "CraftingCottageBuilding" and (
        (world_type == "england" and name == COTTAGES["pub"])
        or any(name == cottage and world_type == world for cottage, world in REGIONAL_COTTAGES.values())))


def regional_catalog_item(item, world_type):
    """First-tier Market preview; a purchase must resolve its live owned tier.

    This detached preview gives the world catalog its authored initial price.
    It is not authorization to buy, place, or bypass a world's admission rules.
    """
    if not isinstance(item, dict) or not regional_cottage(
            world_type, item.get("name"), item.get("className")):
        return item
    return purchase_catalog_item({"userInfo": {"currentWorldType": world_type,
        "player": {"storageData": {}}}, "world": {"objectsArray": []}}, item)


def purchase_catalog_item(save, item):
    """Resolve the original cottage's next purchase tier without editing catalog.

    BuildingItem.cost/market/levelRequired use getItemTier(offset=1).
    calculateCurrentTier counts placed cottages plus cottage gifts, by class.
    Ordinary catalog consumers must use this same detached view when charging.
    """
    if not isinstance(item, dict) or item.get("name") not in COTTAGES.values():
        return item
    if item.get("craftType") in REGIONAL_COTTAGES or item.get("craftType") == "pub":
        _craft_world(save, item.get("craftType"))
    if (item.get("className") != "CraftingCottageBuilding"
            or COTTAGES.get(item.get("craftType")) != item.get("name")
            or item.get("tiered") != "true" or item.get("unlock") != "instance_tiered"):
        raise ValueError("This cottage's original purchase tiers are unavailable.")
    count = sum(obj.get("className") == "CraftingCottageBuilding"
                for obj in save["world"]["objectsArray"])
    gifts = save["userInfo"]["player"].get("storageData", {}).get(str(storage.GIFTBOX_ID), {})
    if not isinstance(gifts, dict):
        raise ValueError("The saved gift box is malformed.")
    for code, entry in gifts.items():
        gift = items.get_item_by_code(code.split(":")[0])
        if gift and gift.get("className") == "CraftingCottageBuilding":
            if not isinstance(entry, list) or not entry:
                raise ValueError("The saved cottage gift quantity is invalid.")
            count += _int(entry[0], "Saved cottage gift quantity")
    # The original special case uses offset 1 for an already-owned same item.
    # Normal purchase guards still enforce the cottage's limit of one.
    existing = any(obj.get("itemName") == item["name"] for obj in save["world"]["objectsArray"])
    tier_id = 1 if existing else count + 1
    tiers = (item.get("tiers") or {}).get("tier", [])
    if isinstance(tiers, dict):
        tiers = [tiers]
    selected = [r for r in tiers if r.get("id") == str(tier_id)]
    if len(selected) != 1:
        raise ValueError("No recovered purchase tier remains for this cottage.")
    tier = selected[0]
    market = tier.get("market")
    price_key = "cash" if market == "cash" else "cost"
    if (market not in ("coins", "cash") or (market == "cash" and item.get("craftType") not in REGIONAL_COTTAGES)
            or not all(isinstance(tier.get(key), str) and tier[key].isascii()
                       and tier[key].isdigit() for key in (price_key, "buyXp", "levelRequired"))):
        raise ValueError("This cottage purchase tier has unsupported currency or prices.")
    result = copy.deepcopy(item)
    result.update({price_key: tier[price_key]})
    result.update(buyXp=tier["buyXp"], market=market,
                  requiredLevel=tier["levelRequired"])
    return result


def _gift_capacity(save):
    # Both launch templates supply the original Player.hasGiftBoxCapacity limit.
    gifts = save["userInfo"]["player"].setdefault("storageData", {}).get(str(storage.GIFTBOX_ID), {})
    if not isinstance(gifts, dict):
        raise ValueError("The saved gift box is malformed.")
    count = 0
    for entry in gifts.values():
        if not isinstance(entry, list) or len(entry) < 3:
            raise ValueError("The saved gift box is malformed.")
        count += _int(entry[0], "Saved gift quantity")
    if count >= 2_147_483_647:
        raise ValueError("The gift box is full.")


def _claim_free_cottage(save, code):
    _home(save)
    if not isinstance(code, str):
        raise ValueError("Choose an original cottage item code.")
    item = items.get_item_by_code(code)
    craft = (item or {}).get("craftType")
    if (craft not in FREE_COTTAGES or item.get("name") != COTTAGES[craft]
            or item.get("className") != "CraftingCottageBuilding"):
        raise ValueError("Choose an original free Home crafting cottage.")
    player = save["userInfo"]["player"]
    from game_settings import get_farming_int
    if (engine.xp_to_level(player["xp"]) or 0) < get_farming_int("craftingCottageStartLevel", 25):
        raise ValueError("Reach level 25 before choosing a crafting cottage.")
    flags = player.setdefault("seenFlags", {})
    state = _state(save)
    claimed = state.get("localFreeCottageCode")
    if flags.get("UnlockedCottage"):
        if claimed == code:
            return {}  # Same choice after reload cannot add another gift.
        raise ValueError("The free crafting cottage has already been chosen.")
    if claimed is not None:
        raise ValueError("The saved free cottage claim is inconsistent.")
    _gift_capacity(save)
    storage.store_deposit_item_by_name(save, item["name"], group=storage.GIFTBOX_ID)
    flags["UnlockedCottage"] = True
    state["localFreeCottageCode"] = code
    if not flags.get("placeCottage"):
        state["localCottageOnboardingPending"] = code
    return {}  # TClaimFreeCottage only requires a non-null callback value.


def _mark_history(save, craft, *, now):
    if not isinstance(craft, str) or craft not in COTTAGES:
        raise ValueError("Choose an original cottage craft.")
    _craft_world(save, craft)
    cottages = _cottages(save, craft)
    if len(cottages) != 1:
        raise ValueError("Cottage history requires one placed matching cottage.")
    cottages[0]["historyLastViewedTS"] = now
    # This is the report's unread XP total, not player or recipe experience.
    # hasFreshTransactions otherwise reopens it in every new Flash session.
    cottages[0]["historyXPGain"] = 0
    # Preserve the historical transaction rows; the timestamp filters the UI.
    return {"responseCode": 0}


def _complete_tutorial(save):
    _home(save)
    state = _state(save)
    if state.get("localCottageTutorialCompleted"):
        return None
    if not any(_cottages(save, craft) for craft in COTTAGES):
        raise ValueError("Place a crafting cottage before completing its tutorial.")
    goods = save["userInfo"]["player"].get("storageData", {}).get(CRAFTED_GOODS_ID, {})
    if not isinstance(goods, dict):
        raise ValueError("The saved crafted goods inventory is malformed.")
    usable = False
    for key, entry in goods.items():
        if not isinstance(key, str) or key.split(":")[0] not in RECIPES:
            continue
        parts = key.split(":")
        if (len(parts) != 2 or not parts[1].isascii() or not parts[1].isdigit()
                or str(int(parts[1])) != parts[1]):
            raise ValueError("The saved crafted good level is invalid.")
        _int(int(parts[1]), "Saved crafted good level", 1, 100)
        if not isinstance(entry, list) or not entry:
            raise ValueError("The saved crafted good quantity is invalid.")
        usable |= _int(entry[0], "Saved crafted good quantity") > 0
    if not usable:
        raise ValueError("Collect a crafted good before completing the cottage tutorial.")
    for obj in save["world"]["objectsArray"]:
        item = items.get_item_by_name(obj.get("itemName")) or {}
        # FarmGameWorld.getEquipment also searches the contents of a garage.
        owned_equipment = item.get("type") == "vehicle"
        if obj.get("className") == "GarageBuilding":
            contents = save["userInfo"]["player"].get("storageData", {}).get(str(obj["id"]), {})
            if not isinstance(contents, dict):
                raise ValueError("The saved garage contents are malformed.")
            for key, entry in contents.items():
                stored_item = items.get_item_by_code(key.split(":")[0]) or {}
                owned_equipment |= (stored_item.get("type") == "vehicle" and isinstance(entry, list)
                                    and bool(entry) and _int(entry[0], "Saved equipment quantity") > 0)
        if owned_equipment:
            raise ValueError("The free tutorial tractor is only for a farm without equipment.")
    _gift_capacity(save)
    storage.store_deposit_item_by_name(save, "tractor", group=storage.GIFTBOX_ID)
    state["localCottageTutorialCompleted"] = True
    return None


def _context(save, code, slot):
    recipe = _recipe(code)
    craft = recipe.findtext("craft")
    _craft_world(save, craft)
    if len(_cottages(save, craft)) != 1:
        raise ValueError("This recipe requires one placed, completed matching cottage.")
    state = _initialize(save)
    skills = state["craftingSkillState"]
    craft_state = next(r for r in skills["craftTypes"] if r.get("type") == craft)
    recipe_state = next(r for r in skills["recipeStates"] if r.get("m_type") == code)
    if recipe_state.get("m_isUnlocked") is not True:
        raise ValueError("This saved recipe is locked.")
    craft_level = _int(craft_state["level"], "Craft level", 1, 5)
    if craft_level < int(recipe.findtext("SkillLevelRequired")):
        raise ValueError("The cottage skill level is too low for this recipe.")
    _int(slot, "Oven slot", -1, _oven_capacity(craft_state) - 1)
    return state, recipe, craft, craft_state, recipe_state


def _oven_capacity(craft_state):
    levels = {int(row.get("num")): int(row.get("recipeSlots"))
              for row in _catalog()[0].find("craftTypeLevels")}
    return levels[craft_state["level"]]


def _balance(player, currency):
    value = player.get(currency)
    if (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
        raise ValueError("The saved crafting balance must be a finite nonnegative number.")
    return value


def _buy_upgrade(save, craft, is_rush):
    if not isinstance(craft, str) or craft not in COTTAGES:
        raise ValueError("Choose an original cottage craft.")
    _craft_world(save, craft)
    if type(is_rush) is not bool:
        raise ValueError("Choose whether to buy the craft upgrade with Farm Cash.")
    if len(_cottages(save, craft)) != 1:
        raise ValueError("A craft upgrade requires one placed, completed matching cottage.")
    state = _initialize(save)
    craft_state = next(row for row in state["craftingSkillState"]["craftTypes"] if row.get("type") == craft)
    level = _int(craft_state.get("level"), "Craft level", 1, 5)
    rows = [row for row in _catalog()[0].find("craftTypeLevels") if row.get("num") == str(level + 1)]
    if len(rows) != 1:
        raise ValueError("This cottage has reached its final craft level.")
    upgrade = rows[0]
    if upgrade.get("prereqName"):
        raise ValueError("This craft upgrade has an unsupported prerequisite.")
    experience = _int(craft_state.get("exp", craft_state.get("xp", 0)), "Craft experience")
    required = _int(int(upgrade.get("xp")), "Craft upgrade experience requirement")
    if not is_rush and experience < required:
        raise ValueError("Earn more craft experience before buying this coin upgrade.")
    price = _int(int(upgrade.get("cash" if is_rush else "gold")), "Craft upgrade price", 1)
    player = save["userInfo"]["player"]
    currency = "cash" if is_rush else "gold"
    balance = _balance(player, currency)
    if balance < price:
        raise ValueError("There are not enough funds for this craft upgrade.")
    (engine.apply_cash_diff if is_rush else engine.apply_coins_diff)(save, -price)
    # CraftTypeState.incrementLevel consumes the NEW level's requirement,
    # including on the cash bypass, and never carries a negative remainder.
    craft_state.update(level=level + 1, xp=max(0, experience - required), exp=max(0, experience - required))
    _initialize(save)  # Original grantDefaultRecipes; preserve old recipe XP/metadata.
    _sync(save, craft)
    # onCraftUpgraded dereferences rewardLink even when no social link exists.
    return {"rewardLink": None}


def _rush(save, code, start_ts, with_coins, slot, *, now):
    if type(with_coins) is not bool:
        raise ValueError("Choose whether to rush the recipe with coins.")
    start_ts = _int(start_ts, "Recipe start timestamp", 1)
    if start_ts > now:
        raise ValueError("A recipe cannot be rushed before its saved start time.")
    state, recipe, craft, craft_state, _ = _context(save, code, slot)
    _craft_world(save, craft)
    queue = state["recipeQueue"][craft]
    _occupied_ovens(queue, _oven_capacity(craft_state))
    matching = [row for row in queue if row.get("id") == code and row.get("start_ts") == start_ts
                and (slot == -1 or row.get("ovenSlot") == slot)]
    if len(matching) != 1:
        raise ValueError("Choose the exact saved recipe and oven to rush.")
    queued = matching[0]
    if _int(queued.get("finish_ts"), "Saved finish time", 1) <= now:
        raise ValueError("This recipe is already ready to collect.")
    price_text = recipe.findtext("RushCostCoins" if with_coins else "RushCostCash")
    try:
        price = int(price_text)
    except (TypeError, ValueError):
        raise ValueError("This recipe's rush price is unavailable.") from None
    # The original -1 sentinel means unavailable, never a credit to the player.
    if price < 1:
        raise ValueError("That currency cannot rush this recipe.")
    player = save["userInfo"]["player"]
    currency = "gold" if with_coins else "cash"
    if _balance(player, currency) < price:
        raise ValueError("There are not enough funds to rush this recipe.")
    (engine.apply_coins_diff if with_coins else engine.apply_cash_diff)(save, -price)
    # RecipeItem.onRushComplete uses start-300. Keep the original readiness
    # semantics for the special onboarding job whose authored start_ts is 1.
    queued["finish_ts"] = max(1, start_ts - 300)
    _sync(save, craft)
    # Transaction.onAmfComplete skips the callback when data is null. Return
    # a non-null object so the client follows with its normal claim RPC.
    # Only claim creates goods or records the crafting quest action.
    return {}


def _occupied_ovens(queue, capacity):
    # The original production frame places explicit slots first, then assigns
    # old -1 queue entries to the first empty oven in queue order.
    occupied = set()
    automatic = []
    for row in queue:
        slot = _int(row.get("ovenSlot", -1), "Saved oven slot", -1, capacity - 1)
        if slot == -1:
            automatic.append(row)
        elif slot in occupied:
            raise ValueError("Multiple saved recipes occupy the same oven.")
        else:
            occupied.add(slot)
    for row in automatic:
        available = sorted(set(range(capacity)) - occupied)
        if not available:
            raise ValueError("The cottage recipe queue is full.")
        row["ovenSlot"] = available[0]
        occupied.add(available[0])
    return occupied


def _ingredients(recipe):
    return {r.get("itemCode"): int(r.get("quantityRequired")) for r in recipe.find("Ingredients")}


def _guard_recipe_dates(recipe, now):
    # RecipeItem.isLimitedValid delegates to the same FarmGameUtil date gate
    # used by market items. Read original dates; never reopen expired recipes.
    from creative_worlds import _guard_purchase_dates
    dates = {key: recipe.findtext(key) for key in ("limitedStart", "limitedEnd")
             if recipe.find(key) is not None}
    _guard_purchase_dates(dates, now=now)


def _purchase(save, code, recipe_code, quantity, *, now):
    state, recipe, _, _, _ = _context(save, recipe_code, -1)
    _guard_recipe_dates(recipe, now)
    quantity = _int(quantity, "Bushel quantity", 1, 400)
    if code not in _ingredients(recipe):
        raise ValueError("This bushel is not an ingredient of the requested recipe.")
    item = items.get_item_by_code(code)
    if not item or item.get("type") != "bushel":
        raise ValueError("The requested ingredient is not a catalog bushel.")
    # CraftingManager.getBushelPrice uses1 unless a positive cash price exists.
    price = engine.catalog_price(item, "cash") or 1
    price = price if price > 0 else 1
    inventory = state["craftingItems"]
    total = sum(_int(r["quantity"], "Saved bushel quantity") for r in inventory)
    capacity = state["maxCapacity"]
    if total + quantity > capacity:
        raise ValueError("The global bushel inventory is full.")
    player = save["userInfo"]["player"]
    if player["cash"] < price * quantity:
        raise ValueError("There is not enough cash to buy these bushels.")
    engine.apply_cash_diff(save, -price * quantity)
    matches = [r for r in inventory if r.get("itemCode") == code]
    if len(matches) > 1:
        raise ValueError("Duplicate saved bushel stacks cannot be purchased into safely.")
    if matches:
        matches[0]["quantity"] += quantity
    else:
        inventory.append({"itemCode": code, "quantity": quantity, "price": None})
    return None


def _mastery_levels(recipe):
    """Original recipe mastery uses recipe LEVEL thresholds, not make counts."""
    mastery = recipe.find("Mastery")
    if mastery is None:
        return []
    return [(int(row.get("count")), int(row.get("level")), row)
            for row in mastery.findall("MasteryLevel")]


def _mastery_level(recipe, recipe_level):
    return max((stars for required, stars, _ in _mastery_levels(recipe)
                if recipe_level >= required), default=0)


def _sign_recipe(snapshot):
    item = items.get_item_by_name(snapshot.get("itemName"))
    if not item or item.get("className") != "RecipeMasterySign":
        return None
    return next((recipe for recipe in _catalog()[1].values()
                 if recipe.find("Mastery") is not None
                 and recipe.find("Mastery").get("sign") == item["code"]), None)


def initialize_mastery_sign(save, snapshot):
    """Gift/inventory placement uses earned stars, never the supplied level."""
    recipe = _sign_recipe(snapshot)
    if recipe is None:
        return snapshot
    states = _state(save).get("craftingSkillState", {}).get("recipeStates", [])
    matches = [row for row in states if row.get("m_type") == recipe.get("id")]
    if len(matches) != 1:
        raise ValueError("This mastery sign needs one saved recipe skill state.")
    level = _mastery_level(recipe, _int(matches[0].get("m_level"), "Recipe level", 1, 100))
    if not level:
        raise ValueError("This recipe has not earned its mastery sign.")
    return {**snapshot, "className": "RecipeMasterySign", "level": level}


def _award_recipe_mastery(save, recipe, previous, current):
    """Award only thresholds crossed by this accepted server-owned XP change.

    Imported high recipe levels are a baseline, not a backlog of gifts. The
    command receipt and persisted level make retries/reload once-only. The
    original mastery popup credits the same catalog coins/XP locally through
    RecipeMasteryEarningsFrame (44942); goals also update its sign and popup.
    """
    crossed = [(stars, row) for required, stars, row in _mastery_levels(recipe)
               if previous < required <= current]
    if not crossed:
        return
    sign = items.get_item_by_code(recipe.find("Mastery").get("sign"))
    if sign is None or sign.get("className") != "RecipeMasterySign":
        raise ValueError("This recipe's recovered mastery sign is unavailable.")
    import world_travel
    owned = [obj for world in world_travel.worlds(save) for obj in world["objectsArray"]
             if obj.get("itemName") == sign["name"]]
    stars = _mastery_level(recipe, current)
    for obj in owned:
        obj["level"] = stars
    inventories = save["userInfo"]["player"].get("storageData", {})
    stored = False
    for inventory in inventories.values():
        if not isinstance(inventory, dict):
            raise ValueError("The saved inventory is malformed.")
        entry = inventory.get(sign["code"])
        if entry is not None:
            if not isinstance(entry, list) or not entry:
                raise ValueError("The saved mastery sign stack is malformed.")
            stored |= _int(entry[0], "Saved mastery sign quantity") > 0
    if not owned and not stored:
        storage.store_deposit_item_by_name(save, sign["name"], group=storage.GIFTBOX_ID)
    for level, row in crossed:
        engine.apply_xp_increment(save, int(row.get("xp", "0")))
        engine.apply_coins_diff(save, int(row.get("coins", "0")))
        progression._pending(save)["goals"].append({
            "type": "RecipeMastery", "code": recipe.find("Reward/OnFinish").get("itemCode"),
            "difficulty": level, "link": "",
        })


def _add_recipe_xp(state, craft_state, recipe_state, amount):
    levels = {int(r.get("num")): int(r.get("xp")) for r in _catalog()[0].find("recipeLevels") if r.get("num").isdigit()}
    level = _int(recipe_state["m_level"], "Recipe level", 1, max(levels))
    xp = _int(recipe_state["m_experience"], "Recipe experience") + amount
    while level < max(levels) and xp >= levels[level] and levels[level + 1] > 0:
        xp -= levels[level]
        level += 1
        experience = _int(craft_state.get("exp", craft_state.get("xp", 0)), "Craft experience") + 1
        craft_state.update(exp=experience, xp=experience)
    recipe_state.update(m_level=level, m_experience=xp)
    return level


def _begin(save, code, slot=-1, *, now):
    state, recipe, craft, craft_state, recipe_state = _context(save, code, slot)
    _guard_recipe_dates(recipe, now)
    queue = state["recipeQueue"][craft]
    if any(r.get("id") == code and r.get("start_ts") == now for r in queue):
        raise ValueError("The same recipe cannot start twice in one second; its client identity is the start timestamp.")
    capacity = _oven_capacity(craft_state)
    occupied = _occupied_ovens(queue, capacity)
    if len(occupied) >= capacity:
        raise ValueError("The cottage recipe queue is full.")
    if slot in occupied:
        raise ValueError("The selected cottage oven is occupied.")
    oven_slot = min(set(range(capacity)) - occupied) if slot == -1 else int(slot)
    needed = _ingredients(recipe)
    inventory = state["craftingItems"]
    for ingredient, amount in needed.items():
        available = sum(_int(r["quantity"], "Saved bushel quantity") for r in inventory if r.get("itemCode") == ingredient)
        if available < amount:
            raise ValueError("There are not enough bushels for this recipe.")
    for ingredient, amount in needed.items():
        for row in inventory:
            if row.get("itemCode") == ingredient and amount:
                take = min(amount, row["quantity"])
                row["quantity"] -= take
                amount -= take
    # Preserve zero stacks and their imported metadata; the client accepts qty0.
    reward = recipe.find("Reward/OnMake")
    previous_level = _int(recipe_state["m_level"], "Recipe level", 1, 100)
    level = _add_recipe_xp(state, craft_state, recipe_state, int(reward.get("recipeXp", "0")))
    _award_recipe_mastery(save, recipe, previous_level, level)
    engine.apply_xp_increment(save, int(reward.get("playerXp", "0")))
    record = {"id": code, "recipe": _php_xml(recipe), "recipeInitialRecipeLevel": int(recipe.findtext("InitialRecipeLevel")),
              "start_ts": now, "finish_ts": now + int(recipe.findtext("MinutesToCook")) * 60,
              "ovenSlot": oven_slot, "worldType": _craft_owner(save, craft),
              "recipeLevel": level}
    queue.append(record)
    _sync(save, craft)
    return copy.deepcopy(record)


def _claim(save, code, slot=-1, *, now):
    state, recipe, craft, craft_state, recipe_state = _context(save, code, slot)
    queue = state["recipeQueue"][craft]
    _occupied_ovens(queue, _oven_capacity(craft_state))
    matching = [r for r in queue if r.get("id") == code and (slot == -1 or r["ovenSlot"] == slot)]
    ready = [r for r in matching if _int(r.get("finish_ts"), "Saved finish time", 1) <= now]
    if matching and not ready:
        raise ValueError("This recipe has not finished cooking.")
    results = []
    reward = recipe.find("Reward/OnFinish")
    sell_quantity, gift_quantity = int(reward.get("sellQty")), int(reward.get("giftQty"))
    product = reward.get("itemCode")
    public = state["craftingPublicInventory"]["publicGoods"][craft]
    for row in ready:
        # Classic callbacks look up the current recipe state, not the oven slot.
        level = _int(recipe_state["m_level"], "Recipe level", 1, 100)
        price_root = _catalog()[0].find("priceFormula")
        price = min(int(price_root.findtext("maxPrice")), int(price_root.findtext("basePrice")) + level * int(price_root.findtext("lvlMultiplier")))
        goods = public.setdefault(product, {"id": product, "qty": 0, "price": price})
        goods["qty"] = _int(goods.get("qty"), "Saved public goods quantity") + sell_quantity
        storage = save["userInfo"]["player"].setdefault("storageData", {}).setdefault(CRAFTED_GOODS_ID, {})
        key = f"{product}:{level}"
        entry = storage.setdefault(key, [0, [], []])
        entry[0] = _int(entry[0], "Saved crafted good quantity") + gift_quantity
        results.append({"recipeId": code, "start_ts": _int(row.get("start_ts"), "Saved start time", 1),
                        "quantity": sell_quantity, "productItemCode": product,
                        "numGiftProducts": gift_quantity, "recipeLevel": level})
        queue.remove(row)
    if results:
        # questSettings_0.taskTypes names onClaimFinishedRecipes, not begin.
        # TClaimFinishedRecipes.getTransactionData reports one recipeCode,
        # even when the callback array contains multiple ready queue entries.
        quests.record_crafting(save, code)
    _sync(save, craft)
    return results


def _use(save, key):
    if not isinstance(key, str) or key.count(":") != 1:
        raise ValueError("A level-specific crafted-good key is required.")
    code, level_text = key.split(":")
    # Crafted goods are a global inventory. CraftingUseGoodsWindow (34561,
    # 34567) lists allCraftedGoods and trades any good for its recipe fuel;
    # its world check gates only the Home tractor tutorial, not recipe origin.
    recipe = _recipe(code)
    if not level_text.isascii() or not level_text.isdigit() or str(int(level_text)) != level_text:
        raise ValueError("The crafted-good level is invalid.")
    level = _int(int(level_text), "Crafted-good level", 1, 100)
    player = save["userInfo"]["player"]
    goods_inventory = player.setdefault("storageData", {}).get(CRAFTED_GOODS_ID, {})
    entry = goods_inventory.get(key)
    if not isinstance(entry, list) or not entry or _int(entry[0], "Saved crafted good quantity") < 1:
        raise ValueError("There is no such crafted good to use.")
    fuel = next(int(r.get("fuel")) for r in _catalog()[0].find("recipeLevels") if r.get("num") == level_text)
    energy = player.get("energy", 0)
    if isinstance(energy, bool) or not isinstance(energy, (int, float)) or not math.isfinite(energy) or energy < 0:
        raise ValueError("The saved fuel quantity is invalid.")
    on_use = recipe.find("Reward/OnUse")
    if on_use is not None:
        # CraftConfigSettings.getFuelRewardForGood multiplies Number directly;
        # it never rounds. The four material recipes also award a catalog gift.
        try:
            multiplier = float(on_use.get("fuel", "1"))
        except (TypeError, ValueError):
            raise ValueError("The recipe's fuel reward is invalid.") from None
        if not math.isfinite(multiplier) or multiplier < 0:
            raise ValueError("The recipe's fuel reward is invalid.")
        fuel *= multiplier
        item = items.get_item_by_code(on_use.get("itemCode"))
        quantity_text = on_use.get("giftQty")
        if (not item or not isinstance(quantity_text, str) or not quantity_text.isascii()
                or not quantity_text.isdigit()):
            raise ValueError("The recipe's use gift is unavailable.")
        quantity = _int(int(quantity_text), "Recipe use gift quantity", 1, 1)
        _gift_capacity(save)
        storage.store_deposit_item_by_name(save, item["name"], quantity, group=storage.GIFTBOX_ID)
    entry[0] -= 1
    if entry[0] == 0:
        del goods_inventory[key]
    player["energy"] = energy + fuel
    return None


def dispatch(save, method, params, *, request_id=None, now=None):
    """Apply one supported wire command atomically, with session-scoped retries.

    request_id is the client's transaction sequence. Call start_session at
    initUser because Flash restarts sequences on reload. The last256 receipts
    survive server restart; a different command reusing a sequence is rejected.
    """
    if method not in METHODS:
        raise ValueError("This crafting service branch is not implemented.")
    if not isinstance(params, (list, tuple)):
        raise ValueError("Crafting parameters must be an array.")
    expected = {"FarmService.onPurchaseBushel": (3,), "CraftingService.onBeginRecipe": (1, 2),
                "CraftingService.onClaimFinishedRecipes": (1, 2), "CraftingService.onUseCraftedGood": (1,),
                "CraftingService.onClaimFreeCottage": (1,), "CraftingService.onCompleteCottageTutorial": (0,),
                "CraftingService.onMarkCottageHistorySeen": (1,),
                "CraftingService.onBuyCraftUpgrade": (2,), "CraftingService.onRushRecipe": (4,)}
    if len(params) not in expected[method]:
        raise ValueError("This crafting command has the wrong number of parameters.")
    working = copy.deepcopy(save)
    state = _state(working)
    receipts = state.setdefault("localCraftingRequests", {})
    if (not isinstance(receipts, dict) or any(not isinstance(k, str) or not k.isascii() or not k.isdigit()
                                             for k in receipts)):
        raise ValueError("The saved crafting retry history is malformed.")
    key = str(_int(request_id, "Crafting request sequence")) if request_id is not None else None
    signature = [method, list(params)]
    if key is not None and key in receipts:
        receipt = receipts[key]
        if receipt["signature"] != signature:
            raise ValueError("A crafting sequence was reused for a different command.")
        # Earlier Mistletoe receipts predate world labels. Their exact craft
        # identifies htown unambiguously; a legacy Pub receipt belongs Home.
        # Crafted-good use consumes the authored global gift inventory, so
        # its successful receipt remains valid after travel in either schema.
        origin = receipt.get("worldType")
        if "worldType" not in receipt:
            code = (params[1] if method == "FarmService.onPurchaseBushel" else params[0]) if params else None
            craft = (code if method in ("CraftingService.onBuyCraftUpgrade", "CraftingService.onMarkCottageHistorySeen")
                     else (_catalog()[1].get(code).findtext("craft") if code in RECIPES else None))
            origin = REGIONAL_COTTAGES.get(craft, (None, "farm"))[1]
        if method != "CraftingService.onUseCraftedGood" and origin != _world(working):
            raise ValueError("This crafting receipt belongs to another farm.")
        return copy.deepcopy(receipts[key]["result"])
    # Preserve the legacy receipts map while retaining an eviction floor.
    # Otherwise an old paid upgrade can buy the NEXT level after its receipt
    # falls out of the last256 records. Derive a floor for pre-migration saves.
    highest = _int(state.get("localCraftingHighestSequence", max((int(k) for k in receipts), default=-1)),
                   "Saved crafting request sequence", -1)
    if key is not None and int(key) <= highest:
        raise ValueError("This crafting request is older than the retained retry history.")
    now = _int(timestamp_now() if now is None else now, "Crafting time", 1)
    if method == "FarmService.onPurchaseBushel":
        result = _purchase(working, *params, now=now)
    elif method == "CraftingService.onBeginRecipe":
        result = _begin(working, *params, now=now)
    elif method == "CraftingService.onClaimFinishedRecipes":
        result = _claim(working, *params, now=now)
    elif method == "CraftingService.onUseCraftedGood":
        result = _use(working, *params)
    elif method == "CraftingService.onClaimFreeCottage":
        result = _claim_free_cottage(working, *params)
    elif method == "CraftingService.onMarkCottageHistorySeen":
        result = _mark_history(working, *params, now=now)
    elif method == "CraftingService.onBuyCraftUpgrade":
        result = _buy_upgrade(working, *params)
    elif method == "CraftingService.onRushRecipe":
        result = _rush(working, *params, now=now)
    else:
        result = _complete_tutorial(working)
    if key is not None:
        receipts[key] = {"signature": copy.deepcopy(signature), "result": copy.deepcopy(result),
                         "worldType": _world(working)}
        state["localCraftingHighestSequence"] = int(key)
        while len(receipts) > 256:
            del receipts[next(iter(receipts))]
    save.clear(); save.update(working)
    return result
