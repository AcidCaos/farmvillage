from datetime import datetime
import constants
from items import get_item_by_name
from game_settings import xp_to_level, level_to_xp

# Utils

def timestamp_now():
    return int(datetime.now().timestamp())

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
    next_id = max(object_ids) + 1
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

def world_update_or_add_object(world_objects: list, new_object: dict) -> None:
    replaced = world_replace_object(world_objects, new_object)
    if not replaced:
        world_objects.append(new_object)

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
        
    cash_gain = (new_level - old_level)

    old_cash = save["userInfo"]["player"]["cash"]
    new_cash = old_cash + cash_gain

    if cash_gain > 0:
        print(" * Cash Gain: {} ({}->{})".format(cash_gain, old_cash, new_cash))

    apply_cash_diff(save, cash_gain)

    # New state
    print(" * You need {} XP to reach level {}".format(level_to_xp(new_level+1)-new_xp, new_level+1))

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

def apply_item_cost(save: dict, item_data: dict, currency: str = None) -> None:

    item_name = item_data["name"] if "name" in item_data else ""
    item_cost = int(item_data["cost"]) if "cost" in item_data and item_data["cost"] is not None else None
    item_market = item_data["market"] if "market" in item_data and item_data["market"] is not "" else None
    item_cash = int(item_data["cash"]) if "cash" in item_data and item_data["cash"] is not None else None

    if currency is None or currency == "":
        if item_market and item_market in ["cash", "coins"]:
            currency = item_market
        else:
            currency = "coins" # Default to coins

    cost = 0
    
    if currency == "coins":
        cost = item_cost if item_cost is not None else 0
    elif currency == "cash":
        cost = item_cash if item_cash is not None else 0
    else:
        print(" * Unknown currency: {}".format(currency))
        return

    if cost == 0 or cost < 0: # No cost or negative cost
        print(" * No cost or negative cost")
        return

    apply_currency_diff_f_map = {
        "coins": apply_coins_diff,
        "gold": apply_gold_diff, # Deprecated (use coins)
        "cash": apply_cash_diff,
    }
    
    print(" * Apply {} item cost: {} {}".format(item_name, cost, currency.upper()))
    apply_currency_diff_f_map[currency](save, -cost)

def apply_item_yield_reward(save: dict, item_data: dict) -> None:
    item_coin_yield = int(item_data["coinYield"]) if "coinYield" in item_data and item_data["coinYield"] is not None else None

    if item_coin_yield is not None and item_coin_yield > 0:
        print(" * Apply {} item yield reward: {} COINS".format(item_data["name"], item_coin_yield))
        apply_coins_diff(save, item_coin_yield)

# Storage and Inventory

def storage_withdrawal(save: dict, item_name: str, amount: int = 1) -> None:
    item_data = get_item_by_name(item_name)
    if item_data is None:
        print(" * Storage Withdrawal: item '{}' not found.".format(item_name))
        return
    if amount <= 0:
        print(" * Storage Withdrawal: invalid amount: {}".format(amount))
        return
    
    item_code = item_data["code"]
    
    storage = save["userInfo"]["player"]["storageData"]

    # TODO: Fix this code and player save data structure (it's oddly formatted)
    for group in storage:
        for code in storage[group]:
            if code == item_code:
                storage[group][code][0] -= amount
                if storage[group][code][0] <= 0:
                    del storage[group][code]
                print(" * Storage Withdrawal: {}x {} (code {})".format(amount, item_name, item_code))
                return