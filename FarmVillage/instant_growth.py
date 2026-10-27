"""Paid ordinary Instant Grow shared by the restored farms.

Recovered FarmGame.swf contracts: Managers.InstagrowHelper.calculateCost,
getPlotsPrice/getTreesPrice/getPriceAnimal; MapResourceHelper's type bits and
getHarvestTimeLeft; TInstantGrow.perform; HarvestableResource.setFullGrown.
The airplane is a transaction carrier, often a transient biplanered, never a
placement. The server selects its own active-world harvestables and timers.
"""
import copy
import json
import math

import constants
import cove_rules
from game_settings import get_farming_int, xp_to_level
from items import get_item_by_name
import peaceful
import world_travel

REQUESTS_KEY = "_instantGrowRequests"
TYPES = {"seed": (1, "Plot"), "tree": (2, "Tree"), "animal": (4, "Animal")}
# Per-category price of the summed in-game hours h (InstagrowHelper.getPlotsPrice, getTreesPrice,
# getPriceAnimal). The animal rate is the pushdouble 0.0015 in getPriceAnimal, not 0.00175.
CATEGORY_PRICES = {1: lambda h: max(4, 1 + h * .002),
                   2: lambda h: max(3, h * .002),
                   4: lambda h: min(18, max(3, h * .0015))}


def _integer(value):
    return type(value) in (int, float) and math.isfinite(value) and int(value) == value


def _options(params):
    # AMF0 serializes the argument Array as either a list or an integer-key map.
    if isinstance(params, dict) and set(params) <= {0, 1, "0", "1"} and (0 in params or "0" in params):
        params = [params.get(0, params.get("0"))] + (
            [params.get(1, params.get("1"))] if (1 in params or "1" in params) else [])
    # TWorldState.signedWorldAction appends {firstWA: true} to the first world
    # action after load (same shape pets.py accepts). It carries no option.
    if isinstance(params, (list, tuple)) and len(params) == 2 and params[1] == {"firstWA": True}:
        params = [params[0]]
    if not isinstance(params, (list, tuple)) or len(params) != 1 or not isinstance(params[0], dict):
        raise ValueError("Instant Grow requires its original options.")
    options = params[0]
    if set(options) - {"type", "autoHarvest", "aoeSources", "worldType", "currentWorldType"}:
        raise ValueError("Unsupported Instant Grow options.")
    kind = options.get("type")
    if not _integer(kind) or not 1 <= kind <= 7:
        raise ValueError("Instant Grow currently supports ordinary crops, trees and animals.")
    # Refused before payment, with the recovered reason:
    #  autoPPH (Harvest & Replant): AMAirplane.prepareAutoPPHCrops chooses the plots client-side (plots sorted
    #    by id, seed counts from the player's inventory, seed visibility, the seedpackage data-source
    #    experiment). The packet carries only the flag. AMAirplane.update runs multiCombine with explicit false
    #    send flags, and multiHarvest/multiPlow/multiPlant gate their TEquipmentAction sends on those flags,
    #    so no harvest/plow/plant transaction follows. The server cannot know which plots to replant.
    #  autoTH/autoAH/autoBH: AMAirplane.doAutoHarvestForAll consumes an arborist, farm-hand or gardener
    #    Consumable (TUseConsumable, no server handler) and harvests orchard, animal-storage or garden containers.
    auto = options.get("autoHarvest", {})
    if (not isinstance(auto, dict) or set(auto) - {"autoPPH", "autoTH", "autoAH", "autoBH"}
            or any(value is not False for value in auto.values())):
        if isinstance(auto, dict) and auto.get("autoPPH") is True:
            raise ValueError("Instant Grow Harvest & Replant is not restored: its plots are chosen client-side.")
        raise ValueError("Instant Grow automatic harvesting is not restored.")
    if options.get("aoeSources", {}) != {}:
        raise ValueError("Instant Grow area bonuses are not restored.")
    return options, int(kind)


def _temporary_airplane_allowed(save, item):
    """Original biplanered fallback, or the catalog airplane tied to this world.

    Later worlds fly their own plane (e.g. xrfbiplane for rainforest), usually
    with a World requirement in the catalog. Candy's configured visual is the
    sole requirement-free exception here.
    """
    # WorldSettingsManager.getWorldSpecificPlaneItemName keeps its caller's
    # second argument when the world has no hudSkinConfig instantGrowItemVisual.
    # AMAirplane and CInstagrow pass DEFAULT_AIRPLANE_ITEM="biplanered". Australia
    # and Htown use that original fallback; it is not a new licence bypass.
    if item.get("name") == "biplanered":
        return not item.get("requirements")
    world = save["userInfo"].get("currentWorldType") or "farm"
    # Candy's actual temporary visual is candybiplane, not the separately
    # purchasable xcwbiplane. worldSettings.xml hudSkinConfig names it, while
    # its catalog record has only fv_candy and no World requirement. Keep this
    # exception exact; it must not admit arbitrary requirement-free planes or
    # bypass any licence subsequently attached to this item.
    if world == "candy" and item.get("name") == "candybiplane":
        return not item.get("requirements") and item.get("experimentGate") == "fv_candy"
    # Atlantis's configured xalsubmarine visual has the same requirement-free
    # shape as Candy's visual. This is a transaction carrier, not a purchase.
    if world == "atlantis" and item.get("name") == "xalsubmarine":
        return not item.get("requirements") and item.get("experimentGate") == "fv_atlantis"
    requirements = item.get("requirements")
    nodes = requirements.get("requirement") if isinstance(requirements, dict) else None
    nodes = nodes if isinstance(nodes, list) else [nodes] if nodes else []
    # Exactly one plain World requirement for the current world; planes that
    # also need licences or other conditions (e.g. biplaneavg) are not accepted.
    return (len(nodes) == 1 and isinstance(nodes[0], dict)
            and nodes[0].get("className") == "World" and nodes[0].get("name") == world)


def _carrier(save, snapshot):
    if (not isinstance(snapshot, dict) or snapshot.get("className") != "Airplane"
            or snapshot.get("deleted") or not _integer(snapshot.get("id"))):
        raise ValueError("Instant Grow requires its original airplane transaction.")
    ident = int(snapshot["id"])
    item = get_item_by_name(snapshot.get("itemName"))
    if not item or item.get("className") != "Airplane":
        raise ValueError("Instant Grow's airplane catalog entry is unavailable.")
    world_travel.guard_action_object(save, ident)
    owned = [obj for obj in save["world"]["objectsArray"]
             if obj.get("id") == ident or obj.get("tempId") == ident]
    if owned:
        if len(owned) != 1 or any(owned[0].get(key) != snapshot.get(key)
                                 for key in ("className", "itemName", "position")):
            raise ValueError("Instant Grow cannot replace the saved airplane's identity.")
    elif not (constants.TEMP_ID_START <= ident <= constants.TEMP_ID_END
              and _temporary_airplane_allowed(save, item) and snapshot.get("tempId") == -1
              and snapshot.get("state") == "static"):
        raise ValueError("Instant Grow requires an owned or original temporary airplane.")
    return ident


def _targets(save, kind, now):
    from creative_worlds import world_requirement_matches
    world = save["userInfo"].get("currentWorldType") or "farm"
    if world == cove_rules.WORLD:
        cove_rules.guard_snapshot(save["world"])
    targets, hours = [], {1: 0, 2: 0, 4: 0}
    hour = get_farming_int("inGameDaySeconds", 82800) / 24
    if hour <= 0:
        raise ValueError("Instant Grow's recovered clock is unavailable.")
    for obj in save["world"]["objectsArray"]:
        if obj.get("deleted"):
            continue
        if ((kind & 2 and obj.get("className") in ("OrchardBuilding", "OrchardFeatureBuilding"))
                or (kind & 4 and obj.get("className") == "AnimalStorageBuilding")
                or (kind & 2 and obj.get("itemName") in ("seedlingnursery_finished", "bonsaigarden_finished"))):
            raise ValueError("Instant Grow harvestable containers are not restored.")
        item = get_item_by_name(obj.get("itemName"))
        category = TYPES.get((item or {}).get("type"))
        if not category or not (kind & category[0]):
            continue
        bit, expected = category
        if obj.get("state") not in (("planted",) if bit == 1 else ("bare",)):
            continue
        if (obj.get("className") != expected
                or item.get("className") not in (None, expected)
                or item.get("features") or not world_requirement_matches(item, world)
                or any(obj.get(flag) for flag in ("isBigPlot", "isSuperPlot", "isProduceItem"))):
            raise ValueError("Instant Grow requires ordinary saved harvestables on this farm.")
        grow, planted = peaceful.grow_seconds(item), obj.get("plantTime")
        if (grow is None or type(planted) not in (int, float) or not math.isfinite(planted)
                or planted < 0 or planted > now * 1000):
            raise ValueError("Instant Grow requires a valid saved growth timer.")
        remaining = max(0, grow - (now - planted / 1000))
        if remaining <= 0:
            continue
        if world == cove_rules.WORLD:
            cove_rules.guard_special_item(item)
            cove_rules.guard_land_terrain(item)
        targets.append((obj, grow, "grown" if bit == 1 else "ripe"))
        hours[bit] += remaining / hour
    # The client floors EACH selected category, then adds the categories.
    return targets, sum(math.floor(CATEGORY_PRICES[bit](value)) for bit, value in hours.items() if value > 0)


def perform(save, snapshot, params, *, now, request_id=None):
    """Preflight everything before paying or maturing; retries never charge twice."""
    world = save["userInfo"].get("currentWorldType") or "farm"
    if world not in world_travel.supported_worlds():
        raise ValueError("Instant Grow is unavailable on this world.")
    options, kind = _options(params)
    for context in (snapshot, options):
        if any(key in context and context[key] != world for key in ("worldType", "currentWorldType")):
            raise ValueError("Instant Grow's world does not match the current farm.")
    ident = _carrier(save, snapshot)
    if (xp_to_level(save["userInfo"]["player"]["xp"]) or 0) < get_farming_int("instantGrowStartingLevel", 15):
        raise ValueError("Instant Grow requires player level 15.")
    # Original owned airplanes report tempId=NaN. Only validated carrier
    # identity participates in a receipt; no client snapshot is ever merged.
    carrier = {key: snapshot.get(key) for key in ("id", "className", "itemName", "position")}
    signature = json.dumps([world, carrier, options], sort_keys=True, allow_nan=False)
    state = save.get(REQUESTS_KEY, {})
    receipts = state.get("receipts", {})
    if request_id is not None:
        if not _integer(request_id) or request_id < 0:
            raise ValueError("Instant Grow requires a valid request sequence.")
        key = str(int(request_id))
        if key in receipts:
            if receipts[key]["signature"] != signature:
                raise ValueError("An Instant Grow request sequence was reused for another action.")
            return receipts[key]["result"]
        if request_id <= state.get("highestSequence", -1):
            raise ValueError("This Instant Grow request is older than the retained retry history.")
    targets, price = _targets(save, kind, now)
    cash = save["userInfo"]["player"]["cash"]
    if type(cash) not in (int, float) or not math.isfinite(cash) or cash < price:
        raise ValueError("Not enough Farm Cash for Instant Grow.")
    # Store the receipt alongside the purchase in the gateway's atomic save.
    # Preserve every ID, object field, inactive world and inventory ledger.
    receipt_state = copy.deepcopy(state)
    if request_id is not None:
        retained = receipt_state.setdefault("receipts", {})
        retained[key] = {"signature": signature, "result": ident}
        receipt_state["highestSequence"] = int(request_id)
        while len(retained) > 256:
            del retained[next(iter(retained))]
    save["userInfo"]["player"]["cash"] = cash - price
    for obj, grow, grown_state in targets:
        obj.update(state=grown_state, plantTime=math.floor((now - grow) * 1000))
    if request_id is not None:
        save[REQUESTS_KEY] = receipt_state
    return ident
