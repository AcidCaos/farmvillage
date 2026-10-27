from datetime import datetime
import base64
import json
import zlib
import math
import constants
from game_settings import xp_to_level, level_to_xp, get_farming_number, get_farming_int
from items import get_item_by_name, item_has_feature

# Utils

def timestamp_now():
    return int(datetime.now().timestamp())

# client ref.: src/Classes/util/FarmGameUtil.as (uncompressAndDecodeDefault)
# A few initUser fields travel as a string rather than as AMF: base64 of the zlib-compressed JSON. The
# client picks the decoder off the fv_ops_json_optimization experiment, but both variants parse plain
# JSON, and templates/play.html pins that experiment to 0 (the Base64Decoder + ByteArray.uncompress path).
def compress_and_encode(obj) -> str:
    return base64.b64encode(zlib.compress(json.dumps(obj).encode("utf-8"))).decode("ascii")

# World Objects

def world_object_id_is_temporary(world_object_id: int) -> bool:
    return constants.TEMP_ID_START <= world_object_id <= constants.TEMP_ID_END

def world_objects_equal(a: dict, b: dict) -> bool: # , check_temp_id: bool = False) -> bool:
    if a["id"] == b["id"]:
        return True
    # Temp ID system already handles this. Should not be needed.
    # if check_temp_id and ( \
    #     ("tempId" in a and a["tempId"] is not None and a["tempId"] == b["id"]) \
    #     or ("tempId" in b and b["tempId"] is not None and a["id"] == b["tempId"]) \
    #     or ("tempId" in a and "tempId" in b and a["tempId"] is not None and b["tempId"] is not None and a["tempId"] == b["tempId"])
    # ):
    #     return True
    return False

def get_new_world_object_id(world_objects: list) -> int:
    object_ids = [obj["id"] for obj in world_objects]
    next_id = max(object_ids, default=0) + 1
    if world_object_id_is_temporary(next_id): # skip temporary ids
            next_id = constants.TEMP_ID_END + 1
    assert not world_object_id_is_temporary(next_id)
    assert not next_id in object_ids
    return next_id

def get_world_object_by_id(world_objects: list, object_id: int) -> dict:
    for obj in world_objects:
        if obj["id"] == object_id:
            return obj
    return None

def world_replace_object(world_objects: list, new_object: dict) -> bool:
    replaced = False
    for i in range(len(world_objects)):
        if world_objects_equal(world_objects[i], new_object):
            world_objects[i] = new_object
            replaced = True
            break
    return replaced

def world_remove_object(world_objects: list, object_id: int) -> bool:
    for i in range(len(world_objects)):
        if world_objects[i]["id"] == object_id:
            del world_objects[i]
            return True
    return False

def world_update_or_add_object(world_objects: list, new_object: dict) -> None:
    replaced = world_replace_object(world_objects, new_object)
    if not replaced:
        world_objects.append(new_object)

# client ref.: src/Classes/FeatureComponents/ExpandFManager.as (loadObject -> refreshPartData)
# Every building carrying an "expand" feature is loaded through ExpandFManager, and refreshPartData()
# reads data.expansionParts[partCode] for each part of the next expansion level without checking that
# the field is there. No client-side getSaveObject() ever writes it - expansionParts was the original
# server's to own - so a world object stored verbatim from the client has none, and reading a property
# off that undefined throws TypeError #1010 in the middle of the world load: the farm never finishes
# loading. Building expansions are not implemented server-side, so an empty map ("no parts collected")
# is both the fix and the truthful value.
def world_object_ensure_expansion_parts(world_object: dict) -> bool:
    if "expansionParts" in world_object or not world_object.get("itemName"):
        return False
    item_data = get_item_by_name(world_object["itemName"])
    if item_data is None or not item_has_feature(item_data, "expand"):
        return False
    world_object["expansionParts"] = {}
    return True

# XP and Levels

def apply_xp_increment(save: dict, const: int) -> None:

    const = int(const)

    if const <= 0:
        return
    
    old_xp = save["userInfo"]["player"]["xp"]
    new_xp = old_xp + const

    print(" * XP Gain: {} ({}->{}).".format(const, old_xp, new_xp))

    save["userInfo"]["player"]["xp"] = new_xp

    # Check if level up

    old_level = xp_to_level(old_xp)
    new_level = xp_to_level(new_xp)

    assert old_level <= new_level

    if old_level < new_level:
        print(" * Level Up: {}->{}".format(old_level, new_level))

    # Add 1 cash per level up
        
    reward_cap = get_farming_int("highestLevelForFCReward", 250)
    cash_gain = max(0, min(new_level, reward_cap) - min(old_level, reward_cap))

    old_cash = save["userInfo"]["player"]["cash"]
    new_cash = old_cash + cash_gain

    if cash_gain > 0:
        print(" * Cash Gain: {} ({}->{})".format(cash_gain, old_cash, new_cash))

    apply_cash_diff(save, cash_gain)

    # New state
    next_level_xp = level_to_xp(new_level + 1)
    if next_level_xp is not None:
        print(" * You need {} XP to reach level {}".format(next_level_xp - new_xp, new_level+1))

# Items costs and rewards

def apply_coins_diff(save: dict, const: int) -> None:
    if const == 0:
        return
    if const > 0:
        save["userInfo"]["player"]["gold"] = save["userInfo"]["player"]["gold"] + const
    if const < 0:
        save["userInfo"]["player"]["gold"] = max(0, save["userInfo"]["player"]["gold"] + const) # const is already negative

def apply_gold_diff(save: dict, const: int) -> None: # Deprecated
    return apply_coins_diff(save, const)

def apply_cash_diff(save: dict, const: int) -> None:
    if const == 0:
        return
    if const > 0:
        save["userInfo"]["player"]["cash"] = save["userInfo"]["player"]["cash"] + const
    if const < 0:
        save["userInfo"]["player"]["cash"] = max(0, save["userInfo"]["player"]["cash"] + const) # const is already negative

# Catalog prices are integers kept as strings, but some entries repeat a price as a list, leave an empty object,
# or carry a stray value such as "200,000" or "n". A list means its first entry; anything unreadable counts as no
# price, the same as an absent field.
def catalog_price(item_data: dict, field: str):
    value = item_data.get(field)
    if isinstance(value, list):
        value = value[0] if value else None
    try:
        return None if value is None else int(float(value))
    except (TypeError, ValueError, OverflowError):
        return None

def apply_item_cost(save: dict, item_data: dict, currency: str = None) -> None:

    if not isinstance(item_data, dict):
        raise ValueError("This item is not in the local catalog.")

    item_name = item_data["name"] if "name" in item_data else ""
    item_market = item_data["market"] if "market" in item_data and item_data["market"] != "" else None

    if currency is None or currency == "":
        if item_market and item_market in ["cash", "coins"]:
            currency = item_market
        else:
            currency = "coins" # Default to coins

    # Only the price in the currency being spent is read: an unrelated price field on the same entry can be malformed.
    cost = 0

    if currency == "coins":
        cost = catalog_price(item_data, "cost") or 0
    elif currency == "cash":
        cost = catalog_price(item_data, "cash") or 0
    elif currency == "gold":
        currency, cost = "coins", catalog_price(item_data, "cost") or 0
    else:
        raise ValueError(f"Unsupported purchase currency: {currency}.")

    if cost == 0 or cost < 0: # No cost or negative cost
        print(" * No cost or negative cost")
        return

    apply_currency_diff_f_map = {
        "coins": apply_coins_diff,
        "gold": apply_gold_diff, # Deprecated (use coins)
        "cash": apply_cash_diff,
    }
    
    print(" * Apply {} item cost: {} {}".format(item_name, cost, currency.upper()))
    balance = save["userInfo"]["player"]["gold" if currency == "coins" else "cash"]
    if balance < cost:
        raise ValueError(f"Not enough {currency} to buy {item_name}.")
    apply_currency_diff_f_map[currency](save, -cost)


def item_sell_price(item_data):
    value = item_data.get("sellPrice")
    if value is None or float(value) < 0:
        value = math.floor((catalog_price(item_data, "cost") or 0) * get_farming_number("sellBackRatio", 0.05))
    return max(0, int(value))

def apply_item_yield_reward(save: dict, item_data: dict) -> None:
    item_coin_yield = int(item_data["coinYield"]) if "coinYield" in item_data and item_data["coinYield"] is not None else None

    if item_coin_yield is not None and item_coin_yield > 0:
        print(" * Apply {} item yield reward: {} COINS".format(item_data["name"], item_coin_yield))
        apply_coins_diff(save, item_coin_yield)

# client ref.: src/Classes/Player.as (turboChargers, loaded from userInfo.player.energyManager.turboChargers)
def apply_turbo_chargers_diff(save: dict, const: int) -> None:
    if const == 0:
        return
    energy_manager = save["userInfo"]["player"]["energyManager"]
    energy_manager["turboChargers"] = max(0, energy_manager["turboChargers"] + const)

# Feature Options

# client ref.: src/Managers/FeatureOptionsManager.as (getFeatureOption)
def get_feature_option(save: dict, feature_name: str, option_name: str = None) -> dict:
         featureOptions = save["userInfo"]["featureOptions"]
         if feature_name in featureOptions:
            if option_name and option_name in featureOptions[feature_name]:
                    return featureOptions[feature_name][option_name]
            return featureOptions[feature_name]

# Irrigation

# client ref.: src/Managers/IrrigationManager.as (addWater)
def has_water_store(save: dict, actionType: str) -> bool:
    irrigation_feature_data = get_feature_option(save, "irrigation", "irrigation")
    return isinstance(irrigation_feature_data, dict) and isinstance(irrigation_feature_data.get(actionType), dict)

def add_water(save: dict, actionType: str, increment: int):
    FEATURE_NAME = "irrigation"
    irrigation_feature_data = get_feature_option(save, FEATURE_NAME, FEATURE_NAME)

    # Only action types the farm's irrigation options define hold water; any other type is ignored.
    if (type(increment) not in (int, float) or not math.isfinite(increment)
            or increment < 0 or increment != int(increment) or increment > 9_007_199_254_740_991):
        raise ValueError("Irrigation rewards must be supported nonnegative whole numbers.")
    if not has_water_store(save, actionType):
        print(" * Irrigation: no water store for action type {!r}; water not added.".format(actionType))
        return

    currentWorld = save["userInfo"].get("currentWorldType") or "farm"
    current = irrigation_feature_data[actionType].get(currentWorld, {"amount": 0})
    amount = current.get("amount") if isinstance(current, dict) else None
    if (type(amount) not in (int, float) or not math.isfinite(amount) or amount < 0
            or amount != int(amount) or amount + increment > 9_007_199_254_740_991):
        raise ValueError("The saved irrigation water balance is invalid.")
    # The generic client addWater branch has no cap. Wells and gift-package
    # use enforce their separate 2000-water acceptance gates before this call.
    irrigation_feature_data[actionType][currentWorld] = {**current, "amount": int(amount + increment)}

# client ref.: src/Managers/IrrigationManager.as (getWaterAmount)
def get_water_amount(save: dict, actionType: str) -> int:
    if not has_water_store(save, actionType):
        return 0
    entry = get_feature_option(save, "irrigation", "irrigation")[actionType].get(save["userInfo"].get("currentWorldType") or "farm")
    amount = entry.get("amount") if isinstance(entry, dict) else None
    return int(amount) if type(amount) in (int, float) and amount else 0

# client ref.: src/Managers/IrrigationManager.as (useWater)
# The client only spends water it has just checked it holds, so an absent store or a short balance is refused.
def use_water(save: dict, actionType: str, amount: int) -> None:
    if not has_water_store(save, actionType):
        raise ValueError("No irrigation water is stored for this action.")
    entry = get_feature_option(save, "irrigation", "irrigation")[actionType].get(save["userInfo"]["currentWorldType"])
    if not isinstance(entry, dict) or get_water_amount(save, actionType) < amount:
        raise ValueError("Not enough irrigation water.")
    entry["amount"] -= amount
