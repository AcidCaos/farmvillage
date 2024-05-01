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

def set_seen_flag(UID, flag) -> None:
    save = session(UID)
    save["userInfo"]["player"]["seenFlags"][flag] = True
    return

def save_options(UID, options) -> None:
    save = session(UID)
    # animationDisabled = options['animationDisabled']
    # sfxDisabled = options['sfxDisabled']
    # graphicsLowQuality = options['graphicsLowQuality']
    # musicDisabled = options['musicDisabled']
    save["userInfo"]["player"]["options"] = options.copy()
    save["options"] = options
    return

def set_avatar(UID, avatar_appearance) -> None:
    save = session(UID)
    # TODO: Figure out the format. This crashes at the loading screen.
    # save["userInfo"]["avatar"] = avatar_appearance
    return

def world_action_plow(UID, m_save, params) -> None:
    save = session(UID)
    # Add the plowed plot to the world objects
    m_save["plantTime"] = None
    save["world"]["objectsArray"].append(m_save)
    # Decrease 15 gold
    save["userInfo"]["player"]["gold"] = max(0, save["userInfo"]["player"]["gold"] - 15)
    return

def world_action_place(UID, m_save, params) -> None:
    save = session(UID)
    # Add the placed object to the world objects
    m_save["buildTime"] = None
    save["world"]["objectsArray"].append(m_save)
    return
