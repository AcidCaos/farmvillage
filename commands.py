from datetime import datetime
import json

from player import get_player, session
from engine import timestamp_now

def init_user(UID) -> dict:
    save = session(UID)
    return save

def post_init_user(UID) -> dict:
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

def increment_action_count(UID, action) -> None:
    save = session(UID)
    if action not in save["userInfo"]["player"]["actionCounts"]:
        save["userInfo"]["player"]["actionCounts"][action] = 1
    else:
        save["userInfo"]["player"]["actionCounts"][action] += 1
    return

def reset_action_count(UID, action) -> None:
    save = session(UID)
    if action in save["userInfo"]["player"]["actionCounts"]:
        save["userInfo"]["player"]["actionCounts"][action] = 0
    return

def set_seen_flag(UID, flag) -> None:
    save = session(UID)
    save["userInfo"]["player"]["seenFlags"][flag] = True
    return

def save_options(UID, options) -> None:
    save = session(UID)
    save["userInfo"]["player"]["options"] = options.copy()
    save["options"] = options
    return

def set_avatar(UID, avatar_appearance) -> None:
    save = session(UID)
    # TODO: Figure out the format. This crashes at the loading screen.
    # save["userInfo"]["avatar"] = avatar_appearance
    return

def world_perform_action(UID, actionName, m_save, params) -> None:
    save = session(UID)

    if actionName == 'plow':
        # Decrease 15 gold
        save["userInfo"]["player"]["gold"] = max(0, save["userInfo"]["player"]["gold"] - 15)
        # Add the plowed plot to the world objects
        m_save["plantTime"] = timestamp_now()
        # Place the plot
        world_perform_action(UID, 'place', m_save, params)

    elif actionName == 'place':
        # TODO: replace temporary ID
        save["world"]["objectsArray"].append(m_save)

def world_action_place(UID, m_save, params) -> None:
    save = session(UID)
    # Add the placed object to the world objects
    m_save["buildTime"] = None
    save["world"]["objectsArray"].append(m_save)
    return

def update_feature_frequency_timestamp(UID, feature) -> None:
    save = session(UID)
    save["userInfo"]["player"]["featureFrequency"][feature] = timestamp_now()
    return