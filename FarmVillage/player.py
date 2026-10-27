import os
import copy
import json
import math
import uuid
import re
import threading
from contextlib import contextmanager
from pathlib import Path
#from flask import session

from engine import timestamp_now
from bundle import VILLAGES_DIR, SAVES_DIR
from game_settings import xp_to_level, get_farming_number
from items import get_item_by_name
import world_travel
import october_village
from version import migrate_loaded_save
from persistence import (SAVE_LOCK, CommittedSaveError, atomic_bytes, commit_json_batch,
                         decode_json, read_json, recover_json_transactions, save_transaction)

__villages = {}  # ALL static neighbors
__saves = {}  # ALL saved villages
__save_paths = {}  # UID -> the original imported or newly created save file
__transactions = threading.local()
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

__initial_village = read_json(os.path.join(VILLAGES_DIR, "initial.json"))

# Load saved villages

def _safe_uid(value) -> str:
    # Preserve UUIDs, numeric IDs, and ordinary imported IDs, while excluding
    # path components, separators, drive prefixes, and control characters.
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("The village UID must be a string or integer.")
    uid = str(value)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", uid):
        raise ValueError("The village UID contains unsupported characters.")
    return uid


def _validate_save(save, *, ready=False) -> str:
    if not isinstance(save, dict):
        raise ValueError("The save is not a JSON object.")
    user = save.get("userInfo")
    world = save.get("world")
    if (not isinstance(user, dict) or not isinstance(user.get("player"), dict)
            or not isinstance(user.get("attr"), dict)
            or not isinstance(user.get("featureOptions"), dict)
            or not isinstance(user.get("worldSummaryData"), dict)
            or not isinstance(user["worldSummaryData"].get("farm"), dict)
            or not isinstance(save.get("flashHotParams"), dict)
            or not isinstance(world, dict) or not isinstance(world.get("objectsArray"), list)
            or not all(isinstance(obj, dict) for obj in world["objectsArray"])):
        raise ValueError("The save is missing the village's required object structure.")
    if not isinstance(user["attr"].get("name"), str):
        raise ValueError("The village name must be a string.")
    if isinstance(user["player"].get("xp"), bool):
        raise ValueError("The village XP must be numeric.")
    try:
        int(user["player"]["xp"])
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise ValueError("The village XP must be numeric.") from error
    uid = _safe_uid(user["player"].get("userId"))
    if ready:
        _validate_runtime_fields(save)
    return uid


def _validate_runtime_fields(save) -> None:
    """Reject malformed core fields after legacy migrations have had a chance.

    These are the structures init/postInit and ordinary persistence immediately
    dereference. Optional cosmetics and unknown feature fields remain intact.
    """
    user = save["userInfo"]
    world_travel.validate(save)
    player = user["player"]
    def number(value):
        return (not isinstance(value, bool) and isinstance(value, (int, float))
                and (not isinstance(value, float) or math.isfinite(value)))
    for key in ("xp", "gold", "cash", "energy"):
        if not number(player.get(key)):
            raise ValueError(f"The village player.{key} must be a finite number.")
    for key in ("actionCounts", "seenFlags", "itemFlags", "storageData", "featureFrequency"):
        if not isinstance(player.get(key), dict):
            raise ValueError(f"The village player.{key} must be an object.")
    if ("is_new" not in user or not number(user.get("firstDayTimestamp"))
            or not isinstance(user.get("currentWorldType"), str)):
        raise ValueError("The village has invalid login/creation fields.")
    if not all(number(save["world"].get(key)) for key in ("sizeX", "sizeY")):
        raise ValueError("The village world dimensions must be finite numbers.")
    for obj in save["world"]["objectsArray"]:
        if not number(obj.get("id")) or not isinstance(obj.get("className"), str):
            raise ValueError("A village world object has an invalid ID or class.")
    state = save.get("questState")
    if (not isinstance(state, dict) or not isinstance(state.get("active"), dict)
            or not isinstance(state.get("completed"), list) or not isinstance(state.get("retired"), list)
            or not isinstance(state.get("replayed"), dict)
            or not all(isinstance(entry, dict) and isinstance(entry.get("progress"), list)
                       and "new" in entry for entry in state["active"].values())):
        raise ValueError("The village quest state has an invalid structure.")
    avatar = save.get("avatarState")
    if (not isinstance(avatar, dict) or not isinstance(avatar.get("unlocked"), list)
            or not isinstance(avatar.get("configurations"), dict)):
        raise ValueError("The village avatar state has an invalid structure.")
    for inventory in player["storageData"].values():
        if not isinstance(inventory, dict):
            raise ValueError("A village inventory must be an object.")
        for entry in inventory.values():
            if (not isinstance(entry, list) or len(entry) != 3 or not number(entry[0])
                    or not isinstance(entry[1], list) or not isinstance(entry[2], list)):
                raise ValueError("A village inventory entry has invalid metadata.")


def _save_contents(save: dict) -> dict:
    village = copy.deepcopy(save)
    village.pop("_progressionResponse", None)
    village.pop("_constructionResponse", None)
    village.pop("_paidBuildingResponse", None)
    world_travel.clear_temporary_ids(village)
    return village


@save_transaction
def load_saves() -> None:
    global __saves, __save_paths
    directory = Path(SAVES_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    recover_json_transactions(directory)
    candidates = {}
    # Recognize top-level JSON farm exports only. Hidden files, links, backup
    # directories, temporary writes, and unrelated metadata never become farms.
    for path in sorted(directory.iterdir()):
        filename = path.name.lower()
        if (path.name.startswith((".", "~")) or path.is_symlink() or not path.is_file()
                or not filename.endswith(".json")
                or filename.endswith((".bak.json", ".backup.json", ".tmp.json"))):
            continue
        try:
            original = path.read_bytes()
            save = decode_json(original)
            uid = _validate_save(save)
            candidates.setdefault(uid, []).append((path, original, save))
        except (OSError, UnicodeError, ValueError, TypeError, RecursionError) as error:
            print(f"[!] Skipping save '{path.name}'; the original is unchanged: {error}")

    loaded = {}
    loaded_paths = {}
    for uid, entries in candidates.items():
        if len(entries) != 1:
            names = ", ".join(path.name for path, _, _ in entries)
            print(f"[!] Skipping duplicate village UID {uid} in {names}; all originals are unchanged.")
            continue
        path, original, save = entries[0]
        try:
            # Migration may mutate before failing. Work on a detached object and
            # publish it only after validation and any required write succeed.
            migrated = copy.deepcopy(save)
            modified = migrate_loaded_save(migrated)
            if _validate_save(migrated, ready=True) != uid:
                raise ValueError("Migration changed the village UID.")
            if modified:
                backup_directory = directory / ".migration-backups"
                if (backup_directory.is_symlink()
                        or (backup_directory.exists() and not backup_directory.is_dir())):
                    raise ValueError("The migration backup directory is unsafe.")
                backup_directory.mkdir(exist_ok=True)
                # Recheck after creation: an existing nested link must never
                # redirect original farm bytes outside the owned save folder.
                if (backup_directory.is_symlink() or not backup_directory.is_dir()
                        or backup_directory.resolve().parent != directory.resolve()):
                    raise ValueError("The migration backup directory is unsafe.")
                backup = backup_directory / f"{uid}.{uuid.uuid4().hex}.original"
                atomic_bytes(backup, original)
                try:
                    commit_json_batch(directory, {path: _save_contents(migrated)}, indent=4,
                                      backup_uids={path: uid})
                except CommittedSaveError as error:
                    print(f"[!] Migration committed with a storage durability failure: {error}")
            loaded[uid] = migrated
            loaded_paths[uid] = path
            print(f" * Loaded SAVE: {path.name}; PLAYER UID: {uid}")
        except Exception as error:
            print(f"[!] Could not load/migrate '{path.name}'; its source or migration backup is preserved: {error}")
    # A request can never observe a partially rebuilt registry.
    __saves = loaded
    __save_paths = loaded_paths

def load_static_villages() -> None:
    global __villages

    # Empty in memory
    __villages = {}

    # Static neighbors in /villages
    for file in os.listdir(VILLAGES_DIR):
        if file == "initial.json" or not file.endswith(".json"):
            continue
        print(f" * Loading STATIC NEIGHBOUR: village at {file}... ", end='')
        village = read_json(os.path.join(VILLAGES_DIR, file))
        UID = village["userInfo"]["player"]["userId"]
        print("STATIC UID:", UID)
        __villages[str(UID)] = village

# New village

@save_transaction
def new_village(name: str = "Farmer", *, preset: str = "classic") -> str:
    if not isinstance(name, str) or not name.strip() or len(name) > 80:
        raise ValueError("Use a farmer name between 1 and 80 characters.")
    if preset not in ("classic", october_village.PRESET):
        raise ValueError("Choose an available village style.")
    if preset == october_village.PRESET and not october_village.AVAILABLE:
        raise ValueError("Quintessential October is still being prepared.")
    ts_now = timestamp_now()
    # Generate UID
    UID: str = str(uuid.uuid4())
    while UID in all_uids() or (Path(SAVES_DIR) / f"{UID}.save.json").exists():
        UID = str(uuid.uuid4())
    # Copy init
    village = copy.deepcopy(__initial_village)
    village["userInfo"]["attr"]["name"] = name.strip()
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
    # The local template's legacy scalar is not a credit ledger. New farms
    # start with no feature credits; imported saves are never rewritten here.
    village["userInfo"]["player"]["featureCredits"] = {}
    # client ref.: src/Classes/TutController.as (calcPlot), src/Classes/HarvestableResource.as (getGrowTime)
    # The starter plots are what the first-time tutorial points at (harvest -> plow -> plant). The grown ones
    # are planted exactly one grow time ago (ms, like Global.worldTime): ripe now, and far from the
    # growTime * witherMultiplier (2.2) the client withers them at.
    for obj in village["world"]["objectsArray"]:
        if obj["className"] == "Plot" and obj["state"] == "grown":
            grow_days = float(get_item_by_name(obj["itemName"])["growTime"])
            grow_seconds = grow_days * get_farming_number("inGameDaySeconds") * get_farming_number("growMultiplier", 1.0)
            obj["plantTime"] = int((ts_now - grow_seconds) * 1000)
    if preset == october_village.PRESET:
        village = october_village.apply_new_preset(
            village, catalog_lookup=get_item_by_name,
            growth_seconds=lambda item: float(item["growTime"])
            * get_farming_number("inGameDaySeconds")
            * get_farming_number("growMultiplier", 1.0))
    # Migrate it if needed
    migrate_loaded_save(village)
    # Memory saves
    __saves[UID] = village
    # Generate save file
    try:
        save_session(UID)
    except CommittedSaveError:
        # The save exists. Keep its registry entry even when storage reports a
        # durability failure after publishing the transaction's commit marker.
        raise
    except BaseException:
        __saves.pop(UID, None)
        __save_paths.pop(UID, None)
        raise
    print("Done.")
    return UID

# Access functions

def all_saves_uids() -> list:
    return list(__saves.keys())

def all_uids() -> list:
    return list(__villages.keys()) + list(__saves.keys())

def session(UID: str) -> dict:
    assert(isinstance(UID, str))
    transaction = getattr(__transactions, "current", None)
    if transaction is not None and UID in __saves and UID not in transaction["originals"]:
        # Neighbor actions can mutate another writable farm. Capture it lazily
        # before handing a mutable reference to any command in the batch.
        transaction["originals"][UID] = copy.deepcopy(__saves[UID])
    if transaction is not None and UID in __saves:
        for savepoint in transaction["savepoints"]:
            if UID not in savepoint["originals"]:
                savepoint["originals"][UID] = copy.deepcopy(__saves[UID])
    return __saves[UID] if UID in __saves else None

def village(UID: str) -> dict:
    # A neighbour is either another player's save or a static village under /villages. Both are the same
    # shape, but only saves are writable, so callers that mutate must go through session() instead.
    assert(isinstance(UID, str))
    if UID in __saves:
        return session(UID)
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
    # templates/img/profile/ ("/img/profile/<file>") can provide a local picture.
    # Remote pictures are optional imported cosmetics, not a gameplay dependency:
    # the LAN host intentionally disables /proxy, and an unavailable remote photo
    # otherwise raises a client-wide resource error during startup. Project the
    # client's existing empty-picture fallback without rewriting the saved URL.
    save = village(UID)
    if save is None:
        return ""
    pic = save["userInfo"].get("attr", {}).get("profilePic")
    # A malformed optional cosmetic field must not hide an otherwise usable
    # village or break every farm in the login selector. Keep its source intact
    # and use the client's existing no-picture fallback.
    if not isinstance(pic, str):
        return ""
    if pic.lstrip().lower().startswith(("http://", "https://", "//", "/proxy?")):
        return ""
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
    current = session(UID)["userInfo"].get("currentWorldType") or "farm"
    session(UID)["userInfo"]["worldSummaryData"][current]["lastLoaded"] = ts_now
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

@contextmanager
def village_transaction(UID: str):
    """Commit the batch's farms together, restoring them if any command fails.

    The gateway's outer request lock covers concurrent reads as well. Keep the
    lock here too so a future caller cannot expose the provisional mutations.
    """
    with SAVE_LOCK:
        uid = _safe_uid(UID)
        if uid not in __saves:
            raise ValueError("Cannot transact an unknown village UID.")
        if getattr(__transactions, "current", None) is not None:
            raise RuntimeError("Nested village transactions are unsupported.")
        recover_json_transactions(SAVES_DIR)
        transaction = {"originals": {uid: copy.deepcopy(__saves[uid])}, "pending": {}, "savepoints": []}
        __transactions.current = transaction
        try:
            yield
            pending = transaction["pending"]
            commit_json_batch(SAVES_DIR, {
                path: _save_contents(__saves[save_uid])
                for save_uid, path in pending.items()
            }, indent=4, backup_uids={path: save_uid for save_uid, path in pending.items()})
            __save_paths.update(transaction["pending"])
        except CommittedSaveError:
            __save_paths.update(transaction["pending"])
            raise
        except BaseException:
            __saves.update(transaction["originals"])
            raise
        finally:
            del __transactions.current


@contextmanager
def village_savepoint(UID: str):
    """Roll back one rejected call while keeping earlier calls in its batch.

    Farms first touched by a neighbor action are captured by session(), just
    as they are for the outer disk transaction. Only the outer transaction
    publishes files, so a disk failure still rolls back every farm together.
    """
    transaction = getattr(__transactions, "current", None)
    if transaction is None:
        raise RuntimeError("A village savepoint requires an active transaction.")
    uid = _safe_uid(UID)
    savepoint = {"originals": {}, "pending": transaction["pending"].copy()}
    transaction["savepoints"].append(savepoint)
    try:
        if session(uid) is None:
            raise ValueError("Cannot transact an unknown village UID.")
        yield
        # Commands can merge client snapshots before their invalid fields are
        # noticed by the save validator. Reject those mutations while this
        # call can still be restored, including farms staged earlier by a
        # neighbor command. Use the same strict JSON/UTF-8 contract as commit.
        for save_uid in savepoint["originals"]:
            save = __saves[save_uid]
            if _validate_save(save, ready=True) != save_uid:
                raise ValueError("Cannot save an inconsistent village UID.")
            json.dumps(_save_contents(save), allow_nan=False).encode("utf-8")
    except BaseException:
        for save_uid, original in savepoint["originals"].items():
            __saves[save_uid].clear()
            __saves[save_uid].update(original)
        transaction["pending"] = savepoint["pending"]
        raise
    finally:
        transaction["savepoints"].pop()


@save_transaction
def save_session(UID: str) -> None:
    uid = _safe_uid(UID)
    save = session(uid)
    if save is None or _validate_save(save, ready=True) != uid:
        raise ValueError("Cannot save an unknown or inconsistent village UID.")
    path = __save_paths.get(uid, Path(SAVES_DIR) / f"{uid}.save.json")
    transaction = getattr(__transactions, "current", None)
    if transaction is not None:
        transaction["pending"][uid] = path
        return
    recover_json_transactions(SAVES_DIR)
    print(f" * Saving village at {path.name}... ", end='')
    # Retain an imported filename rather than creating a second farm or
    # overwriting another file named after the imported UID during migration.
    try:
        commit_json_batch(SAVES_DIR, {path: _save_contents(save)}, indent=4, backup_uids={path: uid})
    except CommittedSaveError:
        __save_paths[uid] = path
        raise
    __save_paths[uid] = path
    print("Done.")
