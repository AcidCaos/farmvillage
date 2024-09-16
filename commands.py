import math

from player import session
from engine import timestamp_now
import engine
from items import get_item_by_name
from game_settings import level_to_xp

def init_user(UID: str) -> dict:
    save = session(UID)
    return save

def post_init_user(UID: str) -> dict:
    data = {
        "postInitTimestampMetric": timestamp_now(),
        "friendsFertilized": [],
        "totalFriendsFertilized": 0,
        "friendsFedAnimals": [],
        "totalFriendsFedAnimals": 0,
        "showBookmark": True,
        "showToolbarThankYou": True,
        "toolbarGiftName": True,
        "isAbleToPlayMusic": True,
        "FOFData": [],
        "prereqDSData": [],
        "neighborCount": 1,
        "fcSlotMachineRewards": None,
        "hudIcons": ["scratchCard"],
        "crossGameGiftingState": None,
        "marketView": None,
        "marketViewCraftingSkills": None,
        "avatarState": None,
        "breedingState": None,
        "w2wState": None,
        "bestSellers": None,
        "completedQuests": [],
        "completedReplayableQuests": None,
        "pricingTests": None,
        "buildingActions": None,
        "bingoNums": None,
        "holidayCountdown": None,
        "faceOffFeatureOptions": None,
        "lastPphActionType": "PphAction",
        "communityGoalsData": None,
        "turtleInnovationData": [],
        "dragonCollection": None,
        "worldCurrencies": [],
        "lotteryData": [],
        "birthdayGiftData": None,
        "primeZCache": None,
        "raffleData": None,
        "fbFeedAutopublishCap": None,
        "fbFeedAutopublishCount": None,
        "fbFeedAutopublishCapTimeInterval": None,
        "unacceptedFbPermissions": None,
        "acceptedFbPermissions": None,
        "popupTwitterDialog": False,
    }
    return data

def increment_action_count(UID: str, action: str) -> None:
    save = session(UID)
    if action not in save["userInfo"]["player"]["actionCounts"]:
        save["userInfo"]["player"]["actionCounts"][action] = 1
    else:
        save["userInfo"]["player"]["actionCounts"][action] += 1
    return

def reset_action_count(UID: str, action: str) -> None:
    save = session(UID)
    if action in save["userInfo"]["player"]["actionCounts"]:
        save["userInfo"]["player"]["actionCounts"][action] = 0
    return

def set_seen_flag(UID: str, flag: str) -> None:
    save = session(UID)
    save["userInfo"]["player"]["seenFlags"][flag] = True
    return

def save_options(UID: str, options: dict) -> None:
    save = session(UID)
    save["userInfo"]["player"]["options"] = options.copy()
    save["options"] = options
    return

def set_avatar_appearance(UID: str, name, png_b64, feed_post) -> None:
    save = session(UID)
    # TODO: Figure out the format. This crashes at the loading screen.
    # save["userInfo"]["avatar"] = {
    #     "gender": ,
    #     "version": "fv_1",
    #     "items": ,
    #     "": png_b64

    # }
    return {}

def world_perform_action(UID: str, actionName: str, m_save: dict, params: list) -> int:
    save = session(UID)
    object_id = m_save["id"]
    object_tempId = None

    # Handle temporary IDs
    if engine.world_object_id_is_temporary(m_save["id"]):
        # TODO: The game sends whether the "id" provided is temp through the "tempId" field. 
        #         if is a temp "id", then: m_save["tempId"] == -1
        #         otherwise: math.isnan(m_save["tempId"])
        #       but its NOT reliable, and it breaks our temporary ID system.
        #       We are not using this fields. We assume that the "id" is temporary if it is in the range of temporary IDs.
        #       And we use the "tempId" field to store the temporary ID assigned for future reference.

        object_tempId = m_save["id"]

        # Search if there is an object with the same temporary ID in the world: they are the same object
        already_generated_id = False
        for obj in save["world"]["objectsArray"]:
            if "tempId" in obj and obj["tempId"] == object_tempId:
                # Replace with the already generated ID (the game still doesn't know it, so it's still sending the temporary ID)
                object_id = obj["id"]
                already_generated_id = True
                break
        # Otherwise, generate a new ID
        if not already_generated_id:
            object_id = engine.get_new_world_object_id(session(UID)["world"]["objectsArray"])

        # Save the temporary ID. Attention: this must be cleared before saving, otherwise it will interfere with future games' temporary IDs.
        m_save["tempId"] = object_tempId

        m_save["id"] = object_id

    # Handle NaN values
    if "plantTime" in m_save and m_save["plantTime"] and type(m_save["plantTime"]) in [int, float] and math.isnan(m_save["plantTime"]):
        m_save["plantTime"] = None
    if "tempId" in m_save and m_save["tempId"] and type(m_save["tempId"]) in [int, float] and math.isnan(m_save["tempId"]):
        m_save["tempId"] = None
    if "buildTime" in m_save and m_save["buildTime"] and type(m_save["buildTime"]) in [int, float] and math.isnan(m_save["buildTime"]):
        m_save["buildTime"] = None

    # Some checks
    if ("itemName" not in m_save or m_save["itemName"] is None) and ("className" in m_save and m_save["className"] != "Plow"):
        print(" * Warning: no item name. World object id: {}".format(object_id))
    
    if actionName == 'plow': # Here itemName is usually None
        # Place the plot
        engine.world_update_or_add_object(session(UID)["world"]["objectsArray"], m_save)
        # Decrease 15 gold
        engine.apply_gold_diff(save, -15)
        # Increase 1 xp
        engine.apply_xp_increment(save, 1)

    elif actionName == 'place':
        item_data = get_item_by_name(m_save["itemName"])
        # Place the object
        engine.world_update_or_add_object(session(UID)["world"]["objectsArray"], m_save)
        # Extract params
        isGift: bool = False
        isInventoryWithdrawal: bool = False
        isStorageWithdrawal: bool = False
        if params and len(params)>0:
            if "isStorageWithdrawal" in params[0] and params[0]["isStorageWithdrawal"] != 0:
                isStorageWithdrawal = True
                print(" * Storage withdrawal")
            if "isInventoryWithdrawal" in params[0] and params[0]["isInventoryWithdrawal"] == True:
                isInventoryWithdrawal = True
                print(" * Inventory withdrawal")
            if "isGift" in params[0] and params[0]["isGift"] == True:
                isGift = True
                print(" * Gift")
        # Withdrawal from storage
        if isStorageWithdrawal:
            engine.storage_withdrawal(save, m_save["itemName"], 1)
        # TODO: Inventory withdrawal
        # Check if must apply costs
        must_apply_costs = True
        if isGift or isInventoryWithdrawal or isStorageWithdrawal:
            must_apply_costs = False
        # Apply costs with currency if explicit
        if must_apply_costs:
            if params and len(params)>0 and "currency" in params[0]:
                engine.apply_item_cost(save, item_data, currency=params[0]["currency"])
            else:
                engine.apply_item_cost(save, item_data)
        # If planted an object, increase XP by plantXP
        if m_save["state"] == "planted" and "plantXp" in item_data and item_data["plantXp"] is not None:
            print(" * Applying plant XP: {}".format(item_data["plantXp"]))
            engine.apply_xp_increment(save, item_data["plantXp"])
        # Assume is bought object
        elif must_apply_costs:
            realXp = 0
            if "buyXp" in item_data and item_data["buyXp"] is not None:
                realXp = int(item_data["buyXp"])
            elif "cost" in item_data and item_data["cost"] is not None:
                realXp = int(item_data["cost"]) // 100
            print(" * Applying buy XP: {}".format(realXp))
            engine.apply_xp_increment(save, realXp)
        # TODO: largeCropXp - check conditions: isBigPlot
        # if "largeCropXp" in m_save and m_save["largeCropXp"] is not None:
        #     print(" * Applying large crop XP: {}".format(m_save["largeCropXp"]))
        #     engine.apply_xp_increment(save, m_save["largeCropXp"])
    
    elif actionName == 'harvest':
        # Apply production reward
        item_data = get_item_by_name(m_save["itemName"])
        engine.apply_item_yield_reward(save, item_data)
        # Replace the object (probably a Plow) with the new one (usually with status "fallow")
        engine.world_update_or_add_object(session(UID)["world"]["objectsArray"], m_save)

    elif actionName == 'move':
        engine.world_replace_object(session(UID)["world"]["objectsArray"], m_save)
    
    return object_id

def update_feature_frequency_timestamp(UID: str, feature: str) -> None:
    save = session(UID)
    save["userInfo"]["player"]["featureFrequency"][feature] = timestamp_now()
    return

def publish_user_actions(UID: str, action: str, params: dict) -> None:
    save = session(UID)
    # We are not tracking XP increments properly, so we'll use this to correct the XP level on Level Ups.
    if action == "LevelUp":
        level = int(params["level_number"])
        current_xp = int(save["userInfo"]["player"]["xp"])
        expected_minimum_xp = int(level_to_xp(level))
        if current_xp < expected_minimum_xp:
            print(" * Correcting XP: {}->{} (minimal XP for level {})".format(current_xp, expected_minimum_xp, level))
            save["userInfo"]["player"]["xp"] = expected_minimum_xp