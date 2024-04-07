from datetime import datetime
import json

from player import get_player, session

def init_user(UID) -> dict:
    save = session(UID)
    return save

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
