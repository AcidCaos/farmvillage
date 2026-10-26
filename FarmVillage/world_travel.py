"""Durable owned-world travel for Home, England, Meadows and Lighthouse Cove.

The recovered England all-access contract is level 15 with
fv_england_for_all=1 (already enabled by templates/play.html), no currency
cost, and a world_unlock reward. The original England starter farm was not
recovered. New England farms deliberately use an empty local starter at the
catalog's farmSize, without invented original buildings or rewards.

The active world remains save['world'] for existing action handlers. Only
inactive worlds live in our versioned namespace, avoiding duplicate/stale
copies and preserving unrelated imported fields. The normal village
transaction makes a switch and its response/save atomic.
"""
from functools import lru_cache
import copy
import math
from pathlib import Path
import uuid
import xml.etree.ElementTree as ET
import zlib

import constants
from game_settings import CONFIG_CMS_XML, get_farming_int, xp_to_level

STATE_KEY = "_ownedWorldTravel"
SUPPORTED_WORLDS = {"farm": -2, "england": -8, "meadows": -16, "fisherman": -9}


def supported_worlds():
    """Recovered worlds plus any dormant themed world explicitly activated."""
    import themed_worlds
    return {**SUPPORTED_WORLDS,
            **{name: themed_worlds.storage_id(name) for name in themed_worlds.active_worlds()}}
MAX_OBJECT_ID = 2147483647


def _integer(value):
    return (type(value) in (int, float) and math.isfinite(value)
            and int(value) == value)


def _validate_world(world):
    if (not isinstance(world, dict) or not isinstance(world.get("objectsArray"), list)
            or any(not _integer(world.get(k)) or world[k] <= 0 for k in ("sizeX", "sizeY"))):
        raise ValueError("The saved travel world has an invalid structure.")
    seen = set()
    for obj in world["objectsArray"]:
        if (not isinstance(obj, dict) or not _integer(obj.get("id"))
                or not 0 < obj["id"] <= MAX_OBJECT_ID
                or constants.TEMP_ID_START <= obj["id"] <= constants.TEMP_ID_END
                or not isinstance(obj.get("className"), str)):
            raise ValueError("The saved travel world has an invalid object.")
        if obj["id"] in seen:
            raise ValueError("The saved travel world contains duplicate object IDs.")
        seen.add(obj["id"])


def validate(save):
    """Validate only our namespace; unknown imported feature state stays opaque."""
    if STATE_KEY not in save:
        if save["userInfo"].get("currentWorldType") == "fisherman":
            import cove_rules
            cove_rules.guard_snapshot(save["world"])
        return
    state = save[STATE_KEY]
    active = save["userInfo"]["currentWorldType"]
    if (not isinstance(state, dict) or state.get("version") != 1
            or not isinstance(state.get("inactive"), dict)
            or active in state["inactive"]
            or not _integer(state.get("nextObjectId"))
            or not 1 <= state["nextObjectId"] <= MAX_OBJECT_ID + 1):
        raise ValueError("The saved owned-world travel state is invalid.")
    if active not in supported_worlds():
        raise ValueError("The active owned world is not supported by this travel version.")
    seen = set()
    worlds = {active: save["world"], **state["inactive"]}
    if "farm" not in worlds:
        raise ValueError("The owned-world travel save is missing its home farm.")
    for name, world in worlds.items():
        if name not in supported_worlds():
            raise ValueError("An owned-world snapshot is unsupported by this travel version.")
        _validate_world(world)
        if name == "fisherman":
            import cove_rules
            cove_rules.guard_snapshot(world)
        elif name not in SUPPORTED_WORLDS:
            import themed_worlds
            themed_worlds.guard_snapshot(name, world)
        summary = save["userInfo"]["worldSummaryData"].get(name)
        if not isinstance(summary, dict) or summary.get("storageId") != supported_worlds()[name]:
            raise ValueError("The saved world inventory does not match its world.")
        # Imported summaries remain opaque. WorldSummary uses Number, so
        # compare numeric text as well without truncating fractional IDs or
        # wrapping unknown imported values onto an owned inventory.
        import themed_worlds
        for other_name, other in save["userInfo"]["worldSummaryData"].items():
            if other_name == name:
                continue
            if themed_worlds.summary_claims_storage(other, summary["storageId"]):
                raise ValueError("An imported world shares this farm's inventory ID; travel is unavailable until its storage contract is resolved.")
        for obj in world["objectsArray"]:
            if obj["id"] in seen:
                raise ValueError("Owned worlds contain colliding object IDs.")
            seen.add(obj["id"])


def worlds(save):
    yield save["world"]
    state = save.get(STATE_KEY)
    if state is not None:
        validate(save)
        yield from state["inactive"].values()


def clear_temporary_ids(save):
    for world in worlds(save):
        for obj in world["objectsArray"]:
            obj.pop("tempId", None)


def home_world(save):
    """A neighbor's home must not follow the owner's active destination."""
    if save["userInfo"].get("currentWorldType", "farm") in ("", "farm"):
        return save["world"]
    validate(save)
    home = save.get(STATE_KEY, {}).get("inactive", {}).get("farm")
    if home is None:
        raise ValueError("The saved home world is unavailable; its data was not reconstructed.")
    return home


def _reserved_ids(save):
    ids = {int(obj["id"]) for world in worlds(save) for obj in world["objectsArray"]}
    # A retained ledger must never be inherited by a new building, even when
    # its imported source object is unavailable.
    for key in save["userInfo"]["player"].get("storageData", {}):
        try:
            value = int(key)
        except (ValueError, TypeError):
            continue
        if value > 0:
            ids.add(value)
    return ids


def next_object_id(save):
    """Allocate across every owned world and positive storage ledger."""
    from engine import get_new_world_object_id
    if STATE_KEY not in save:
        return get_new_world_object_id(save["world"]["objectsArray"])
    ids = _reserved_ids(save)
    state = save[STATE_KEY]
    value = max(max(ids, default=0) + 1, int(state["nextObjectId"]))
    if constants.TEMP_ID_START <= value <= constants.TEMP_ID_END:
        value = constants.TEMP_ID_END + 1
    if value > MAX_OBJECT_ID:
        raise ValueError("The farm has exhausted the supported object ID range.")
    state["nextObjectId"] = value + 1
    return value



def guard_active_world(save):
    """Refuse mutation of an unsupported imported active farm, even legacy ones.

    An absent/empty world label is the original Home spelling. Every nonempty
    label must be explicitly supported; never reinterpret another world as Home.
    Read/import validation remains separate so opaque saves stay recoverable.
    """
    current = save["userInfo"].get("currentWorldType")
    if current in (None, ""):
        current = "farm"
    if not isinstance(current, str) or current not in supported_worlds():
        raise ValueError("The imported active world is not supported for farming or purchases.")
    return current


def guard_action_object(save, object_id):
    guard_active_world(save)
    if STATE_KEY not in save:
        return
    validate(save)
    if any(obj["id"] == object_id for world in save[STATE_KEY]["inactive"].values()
           for obj in world["objectsArray"]):
        raise ValueError("That object belongs to another owned world.")


def guard_placement(save, snapshot):
    current = guard_active_world(save)
    if current == "farm":
        return
    import crafting
    if crafting.regional_cottage(current, snapshot.get("itemName"), snapshot.get("className")):
        return
    # Only exact regional identities with isolated production state pass.
    if (snapshot.get("itemName") in crafting.COTTAGES.values()
            or snapshot.get("className") == "CraftingCottageBuilding"):
        raise ValueError("Crafting cottage placement is currently supported on the home farm only.")


def guard_new_object_id(save, action, object_id):
    guard_active_world(save)
    if STATE_KEY not in save or action not in ("place", "plow"):
        return
    if not _integer(object_id):
        raise ValueError("A new world object's ID must be a whole number.")
    if any(obj["id"] == object_id for obj in save["world"]["objectsArray"]):
        return
    if not constants.TEMP_ID_START <= object_id <= constants.TEMP_ID_END:
        raise ValueError("A new world object requires a temporary client ID.")


def guard_world_context(save, snapshot, params):
    """Reject unsupported active worlds and every explicit payload mismatch."""
    current = guard_active_world(save)
    contexts = [snapshot, *(entry for entry in params if isinstance(entry, dict))]
    for context in contexts:
        for key in ("worldType", "currentWorldType"):
            if key in context and context[key] not in (current,):
                raise ValueError("The action's world does not match the current owned world.")


@lru_cache(maxsize=1)
def england_level_requirement():
    root = ET.fromstring(zlib.decompress(Path(CONFIG_CMS_XML).read_bytes()))
    prereq = root.find(".//prereq[@name='fv_england_all_access']")
    expected = {("experiment", "fv_england_for_all", "1"),
                ("has_not_unlocked_world", "england", None)}
    if prereq is None or prereq.get("type") != "AND":
        raise ValueError("England's recovered unlock requirements are unavailable.")
    level = None
    for child in prereq:
        signature = (child.get("type"), child.get("value"), child.get("variant"))
        if child.get("type") == "level_min" and level is None:
            level = int(child.get("value"))
        elif signature in expected:
            expected.remove(signature)
        else:
            raise ValueError("England's unlock prerequisites are not supported.")
    if expected or level is None or level < 1:
        raise ValueError("England's recovered unlock requirements are incomplete.")
    return level


def _boolean(value, name):
    if type(value) is bool:
        return value
    if type(value) in (int, float) and value in (0, 1):
        return bool(value)
    raise ValueError(f"Invalid {name} travel option.")


def unlock_england(save, access_type, *, now):
    """Honor the original allAccess transaction without changing active farms.

    TExpansionWorldAccess requires a truthy ActionScript result before it
    applies the catalog world_unlock reward and exposes the travel controls.
    An empty Array satisfies that wire contract without inventing rewards.
    """
    if access_type != "allAccess":
        raise ValueError("Only England's recovered all-access unlock is supported.")
    validate(save)
    active = save["userInfo"].get("currentWorldType", "farm") or "farm"
    state = save.get(STATE_KEY)
    if state is not None and (active == "england" or "england" in state["inactive"]):
        return []
    # The client sends this unlock on load from whichever owned farm is active,
    # so a player who reaches level 15 and then opens Cove or a themed farm first
    # must not be refused (a refusal leaves that farm's client out of sync).
    if active not in supported_worlds():
        raise ValueError("The owned world snapshots needed for England unlock are unavailable.")
    # Reuse creation validation in a detached copy. Unlock happens during
    # post-init, so the live farm and its temporary placement mappings must
    # remain exactly as they were until the client actually travels.
    working = copy.deepcopy(save)
    switch(working, "england", True, now=now)
    created = working["world"]
    new_state = working[STATE_KEY]
    new_state["inactive"].pop(active)
    new_state["inactive"]["england"] = created
    working["world"] = save["world"]
    working["userInfo"]["currentWorldType"] = active
    validate(working)
    save[STATE_KEY] = new_state
    user = save["userInfo"]
    user["worldSummaryData"]["england"] = working["userInfo"]["worldSummaryData"]["england"]
    user["unlockedWorldTypes"] = working["userInfo"]["unlockedWorldTypes"]
    user["player"]["storageData"].setdefault(str(SUPPORTED_WORLDS["england"]), {})
    return []


def unlock_fisherman(save, access_type, *, now):
    """Match TExpansionWorldAccess's truthy Array without inventing rewards."""
    import creative_worlds
    creative_worlds.create(save, "fisherman", access_type, now=now)
    return []


def switch(save, world_type, should_create=False, should_freeze=False,
           next_season_unlock=False, *, now):
    # Production projections can reject malformed imported partitions. Publish
    # world and production together, including for direct non-gateway callers.
    working = copy.deepcopy(save)
    _switch(working, world_type, should_create, should_freeze,
            next_season_unlock, now=now)
    save.clear()
    save.update(working)


def _switch(save, world_type, should_create=False, should_freeze=False,
            next_season_unlock=False, *, now):
    """Switch only after validating all input; never substitute the home farm."""
    if not isinstance(world_type, str):
        raise ValueError("The destination world must be a string.")
    destination = world_type or "farm"
    create = _boolean(should_create, "create")
    seasonal = _boolean(should_freeze, "freeze") or _boolean(next_season_unlock, "season")
    if seasonal and destination != (save["userInfo"].get("currentWorldType", "farm") or "farm"):
        # Freezing one world while leaving for another has no recovered semantics, so it stays refused.
        raise ValueError("Freezing farms and seasonal travel are not supported.")
    # The client's loadNextSeason re-enters the world it is already on with these flags set. Seasons are
    # not modelled, so that is answered as a plain same-world reload: nothing frozen, nothing unlocked.
    if destination not in supported_worlds():
        raise ValueError("Travel currently supports the active farms in this release only.")
    validate(save)
    user = save["userInfo"]
    active = user.get("currentWorldType", "farm") or "farm"
    if active not in supported_worlds():
        raise ValueError("The imported active world cannot be replaced by this travel version.")
    summaries = user["worldSummaryData"]
    unlocked = user.get("unlockedWorldTypes", [])
    if not isinstance(unlocked, list) or not all(isinstance(name, str) for name in unlocked):
        raise ValueError("The imported world unlock state is invalid.")
    if destination == active:
        summary = summaries.get(active)
        if not isinstance(summary, dict):
            raise ValueError("The current world's summary is unavailable.")
        summary["lastLoaded"] = now
        return
    state = save.get(STATE_KEY)
    inactive = state["inactive"] if state else {}
    target = inactive.get(destination)
    new_world = target is None
    if new_world:
        if destination == "farm" or destination in summaries or destination in unlocked:
            raise ValueError("The requested world snapshot is missing; it cannot be recreated safely.")
        if not create:
            raise ValueError("The destination has not been created; explicit world creation is required.")
        if destination not in SUPPORTED_WORLDS:
            raise ValueError("Unlock this farm from the additional farms page before traveling there.")
        if destination != "england":
            if destination == "fisherman":
                raise ValueError("Unlock Lighthouse Cove from the additional farms page before traveling there.")
            raise ValueError("Purchase Sunflower Meadows from the additional farms page before traveling there.")
        minimum = england_level_requirement()
        if (xp_to_level(user["player"]["xp"]) or 0) < minimum:
            raise ValueError(f"England requires player level {minimum}.")
        size = get_farming_int("farmSize")
        if size <= 0:
            raise ValueError("The local starter farm size is unavailable.")
        target = {"id": 2, "uid": str(uuid.uuid4()), "sizeX": size, "sizeY": size,
                  "objectsArray": [], "messageManager": [],
                  "localStarter": "empty-england-v1"}
    _validate_world(save["world"])
    _validate_world(target)
    if destination == "fisherman":
        import cove_rules
        cove_rules.guard_snapshot(target)
    elif destination not in SUPPORTED_WORLDS:
        import themed_worlds
        themed_worlds.guard_snapshot(destination, target)
    if not isinstance(summaries.get(active), dict):
        raise ValueError("The current world's summary is unavailable.")
    if summaries[active].get("storageId") != supported_worlds()[active]:
        raise ValueError("The imported active world inventory does not match its world.")
    # Validate/suspend production before replacing its owning world. This
    # preserves legacy Home progress without projecting it onto England.
    import crafting
    crafting.before_world_switch(save, destination)
    # Nothing above changes the world. The regular gateway transaction also
    # rolls this switch back on response-encoding or disk-write failure.
    if state is None:
        next_id = max(_reserved_ids(save), default=0) + 1
        if next_id > MAX_OBJECT_ID + 1:
            raise ValueError("An imported storage ID exceeds the supported object ID range.")
        state = {"version": 1, "inactive": {}, "nextObjectId": next_id}
        save[STATE_KEY] = state
    if new_world:
        summaries[destination] = {"firstLoaded": now, "lastLoaded": now,
                                  "storageId": supported_worlds()[destination]}
    state["inactive"][active] = save["world"]
    state["inactive"].pop(destination, None)
    save["world"] = target
    user["currentWorldType"] = destination
    crafting.after_world_switch(save)
    user["unlockedWorldTypes"] = list(dict.fromkeys([*unlocked, "farm", destination]))
    summaries[destination]["lastLoaded"] = now
    user["player"]["storageData"].setdefault(str(supported_worlds()[destination]), {})
    clear_temporary_ids(save)
    validate(save)

