import math

from player import session
from engine import timestamp_now
import engine

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

    if actionName == 'plow':
        # Decrease 15 gold
        save["userInfo"]["player"]["gold"] = max(0, save["userInfo"]["player"]["gold"] - 15)
        # Increase 1 xp
        save["userInfo"]["player"]["xp"] += 1
        # Place the plot
        world_perform_action(UID, 'place', m_save, params)

    elif actionName == 'place':
        replaced = False
        for i in range(len(save["world"]["objectsArray"])):
            if engine.world_objects_equal(save["world"]["objectsArray"][i], m_save):
                save["world"]["objectsArray"][i] = m_save
                replaced = True
                break
        if not replaced:
            save["world"]["objectsArray"].append(m_save)
    
    elif actionName == 'move':
        for i in range(len(save["world"]["objectsArray"])):
            if engine.world_objects_equal(save["world"]["objectsArray"][i], m_save):
                save["world"]["objectsArray"][i] = m_save
                break
    
    return object_id

def update_feature_frequency_timestamp(UID: str, feature: str) -> None:
    save = session(UID)
    save["userInfo"]["player"]["featureFrequency"][feature] = timestamp_now()
    return