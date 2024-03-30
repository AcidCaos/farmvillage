import os
import json
import copy
import uuid
#from flask import session

from engine import timestamp_now
from bundle import VILLAGES_DIR, SAVES_DIR
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

def load_saves():
    global __saves

    # Empty in memory
    __saves = {}

    # Saves dir check
    if not os.path.exists(SAVES_DIR):
        try:
            print(f"Creating '{SAVES_DIR}' folder...")
            os.mkdir(SAVES_DIR)
        except:
            print(f"Could not create '{SAVES_DIR}' folder.")
            exit(1)
    if not os.path.isdir(SAVES_DIR):
        print(f"'{SAVES_DIR}' is not a folder... Move the file somewhere else.")
        exit(1)

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

def load_static_villages():
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

def get_player(UID):
    # Update last logged in
    ts_now = timestamp_now()
    session(UID)["userInfo"]["worldSummaryData"]["farm"]["lastLoaded"] = ts_now
    player_info = session(UID)
    player_info["userInfo"]["player"]["neighbors"] = [] # TODO
    return player_info

def save_info(UID: str) -> dict:
    save = __saves[UID]
    name = save["userInfo"]["attr"]["name"]
    xp = save["userInfo"]["player"]["xp"]
    return{"uid": UID, "name": name, "xp": xp}

def all_saves_info() -> list:
    saves_info = []
    for uid in __saves:
        saves_info.append(save_info(uid))
    return list(saves_info)

# Persistency

def save_session(UID: str):
    # TODO 
    file = f"{UID}.save.json"
    print(f" * Saving village at {file}... ", end='')
    village = session(UID)
    with open(os.path.join(SAVES_DIR, file), 'w') as f:
        json.dump(village, f, indent=4)
    print("Done.")