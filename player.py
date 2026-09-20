import os
import sys
import json
import copy
import uuid
from urllib.parse import quote
#from flask import session

from engine import timestamp_now
from bundle import VILLAGES_DIR, SAVES_DIR
from game_settings import xp_to_level
from version import migrate_loaded_save

__villages = {}  # ALL static neighbors
__saves = {}  # ALL saved villages
'''__saves = {
    "UID_1": {
        "userInfo": {
            "player": {
                ...
                "userId": "UID_1",
                ...
            }
            ...
        },
        "world": { ... },
        "craftingState": {...},
        ...
    },
    "UID_2": {...}
}'''

__initial_village = json.load(open(os.path.join(VILLAGES_DIR, "initial.json")))

# Load saved villages

def load_saves() -> None:
    global __saves

    # Empty in memory
    __saves = {}

    # Saves dir check
    if not os.path.exists(SAVES_DIR):
        try:
            print(f" * Creating '{SAVES_DIR}' folder...")
            os.mkdir(SAVES_DIR)
        except:
            print(f"[!] Could not create '{SAVES_DIR}' folder.")
            sys.exit(1)
    if not os.path.isdir(SAVES_DIR):
        print(f"[!] '{SAVES_DIR}' is not a folder... Move the file somewhere else.")
        sys.exit(1)

    # Saves in /saves
    for file in os.listdir(SAVES_DIR):
        print(f" * Loading SAVE: village at {file}... ", end='')
        try:
            save = json.load(open(os.path.join(SAVES_DIR, file)))
        except json.decoder.JSONDecodeError as e:
            print("Corrupted JSON.")
            continue
        UID = save["userInfo"]["player"]["userId"]
        print("PLAYER UID:", UID)
        __saves[str(UID)] = save
        modified = migrate_loaded_save(save) # check save version for migration
        if modified:
            save_session(UID)

def load_static_villages() -> None:
    global __villages

    # Empty in memory
    __villages = {}

    # Static neighbors in /villages
    for file in os.listdir(VILLAGES_DIR):
        if file == "initial.json" or not file.endswith(".json"):
            continue
        print(f" * Loading STATIC NEIGHBOUR: village at {file}... ", end='')
        village = json.load(open(os.path.join(VILLAGES_DIR, file)))
        UID = village["userInfo"]["player"]["userId"]
        print("STATIC UID:", UID)
        __villages[str(UID)] = village

# New village

def new_village() -> str:
    ts_now = timestamp_now()
    # Generate UID
    UID: str = str(uuid.uuid4())
    assert UID not in all_uids()
    # Copy init
    village = copy.deepcopy(__initial_village)
    # Custom values
    village["version"] = None # Do not set version, migrate_loaded_save() does it
    village["userInfo"]["player"]["userId"] = UID
    village["flashHotParams"]["ZYNGA_USER_ID"] = UID
    village["world"]["id"] = 1
    village["world"]["uid"] = str(uuid.uuid4())
    village["userInfo"]["worldSummaryData"]["farm"]["firstLoaded"] = ts_now
    village["userInfo"]["worldSummaryData"]["farm"]["lastLoaded"] = ts_now
    village["userInfo"]["is_new"] = True
    village["userInfo"]["firstDay"] = True
    village["userInfo"]["firstDayTimestamp"] = ts_now
    # Migrate it if needed
    migrate_loaded_save(village)
    # Memory saves
    __saves[UID] = village
    # Generate save file
    save_session(UID)
    print("Done.")
    return UID

# Access functions

def all_saves_uids() -> list:
    return list(__saves.keys())

def all_uids() -> list:
    return list(__villages.keys()) + list(__saves.keys())

def session(UID: str) -> dict:
    assert(isinstance(UID, str))
    return __saves[UID] if UID in __saves else None

def village(UID: str) -> dict:
    # A neighbour is either another player's save or a static village under /villages. Both are the same
    # shape, but only saves are writable, so callers that mutate must go through session() instead.
    assert(isinstance(UID, str))
    if UID in __saves:
        return __saves[UID]
    return __villages[UID] if UID in __villages else None

# Neighbours

def neighbor_uids(UID: str) -> list:
    # Everyone on this server neighbours everyone else: there is no friend-request flow to reverse-engineer
    # (that lived on Facebook), and the client only ever sees the list the server hands it.
    return [uid for uid in all_uids() if uid != UID]

def profile_pic(UID: str) -> str:
    # client ref.: src/Classes/util/FacebookSocialNetwork.as (toSocialNetworkUser), src/Classes/Friend.as
    # The picture is just a url the client hands to a Loader, and the originals were Facebook CDN ones that
    # were never recovered - so each save/village carries its own in `userInfo.attr.profilePic` (empty means
    # "no picture", which is FriendBarSlot's embedded no-profile-pic art). Either a local file dropped in
    # templates/img/profile/ ("/img/profile/<file>") or any remote url.
    # client ref.: src/Engine/Classes/ResourceLoader.as (m_context.checkPolicyFile = true)
    # A remote url cannot be handed to the client as-is: Flash asks its host for a crossdomain.xml first and
    # fails with a SecurityError when there is none (no modern CDN serves one). It goes through server.py's
    # /proxy instead, which re-serves it from our own origin.
    save = village(UID)
    if save is None:
        return ""
    pic = save["userInfo"].get("attr", {}).get("profilePic") or ""
    if pic.startswith(("http://", "https://")):
        pic = "/proxy?url=" + quote(pic, safe="")
    return pic

def neighbor_metadata(UID: str) -> list:
    # client ref.: src/Classes/Friend.as (setMetaData) - one entry per neighbour, holding exactly the fields
    # Friend reads. `stats` is left out on purpose: FriendBarSlot only draws the stats card when the object
    # has ribbons/medals/masteries/collections/buildings, and we have nothing truthful to put in them.
    # `name`/`profilePic` are overwritten from the SN user (Friend's snUser setter) for anyone the JS
    # getFriendData() in templates/play.html also reports, and are the fallback for anyone it does not -
    # so both halves must serve the same profile_pic(), or the empty one wins by being assigned last.
    result = []
    for uid in neighbor_uids(UID):
        save = village(uid)
        if save is None:
            continue
        player = save["userInfo"]["player"]
        xp = player.get("xp") or 0
        result.append({
            "uid": uid,
            "name": save["userInfo"].get("attr", {}).get("name", "Farmer"),
            "gold": player.get("gold") or 0,
            "xp": xp,
            "level": xp_to_level(xp),
            "worldScores": player.get("worldScores"),
            "avatar": save["userInfo"].get("avatar"),
            "profilePic": profile_pic(uid),
            "worldName": "farm", # client ref.: src/Classes/Constants/WorldsConstants.as (WORLD_ID_HOME)
            "isNeighbor": True,
            "community": 0, # Not a community (non-network) neighbour: these are all real, visitable saves
            "hasEmailPermission": False,
            "usedPhotoContest": False,
            "unlockedWorldTypes": None,
            "featureCredits": None,
            "questIds": None,
            "breedingStats": None,
            "stats": None,
        })
    return result

def get_player(UID: str):
    # Update last logged in
    ts_now = timestamp_now()
    session(UID)["userInfo"]["worldSummaryData"]["farm"]["lastLoaded"] = ts_now
    player_info = session(UID)
    player_info["userInfo"]["player"]["neighbors"] = neighbor_uids(UID)
    return player_info

def save_info(UID: str) -> dict:
    save = __saves[UID]
    name = save["userInfo"]["attr"]["name"]
    xp = save["userInfo"]["player"]["xp"]
    return{"uid": UID, "name": name, "xp": xp, "profilePic": profile_pic(UID)}

def all_saves_info() -> list:
    saves_info = []
    for uid in __saves:
        saves_info.append(save_info(uid))
    return list(saves_info)

def social_network_friends(UID: str) -> list:
    # client ref.: src/Classes/util/FacebookSocialNetwork.as (getFriendList/getAppFriends, toSocialNetworkUser)
    # The client asks JavaScript for its social graph (templates/play.html's getFriendData()) before it asks
    # the gateway for anything. These uids must match neighbor_metadata()'s exactly: FriendManager only
    # promotes a neighbour into the friend bar when it can pair the two halves by uid.
    # `pic_square` is the half that actually decides the picture: Friend's constructor runs setMetaData()
    # first and then the snUser setter, which overwrites profilePic with whatever this reports, and
    # FriendBarSlot.setupOccupiedSpot() reads snUser.picture directly (falling back to its embedded
    # no-profile-pic art when it is empty).
    friends = []
    for uid in neighbor_uids(UID):
        save = village(uid)
        if save is None:
            continue
        name = save["userInfo"].get("attr", {}).get("name", "Farmer")
        friends.append({
            "uid": uid,
            "first_name": name,
            "name": name,
            "pic_square": profile_pic(uid),
            "sex": "",
        })
    return friends

# Persistency

def save_session(UID: str) -> None:
    file = f"{UID}.save.json"
    print(f" * Saving village at {file}... ", end='')
    # Must be a deep copy, otherwise we'll be modifying the in-memory object that is in use to check the temporary IDs.
    village = copy.deepcopy(session(UID))
    # Clean save file tempIds
    for obj in village["world"]["objectsArray"]:
        if "tempId" in obj:
            del obj["tempId"]
    # Save. Written to a temporary file first and moved into place: opening the real save with 'w'
    # truncates it before json.dump runs, so anything json cannot serialize (e.g. a pyamf.Undefined
    # that came straight off the wire) used to leave a half-written, unloadable save behind.
    path = os.path.join(SAVES_DIR, file)
    tmp = path + ".tmp"
    with open(tmp, 'w') as f:
        json.dump(village, f, indent=4)
    os.replace(tmp, path)
    print("Done.")