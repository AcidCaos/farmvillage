import os
import zlib
import json
import calendar
import xmltodict

from bundle import XML_DIR, CACHE_DIR
from game_settings import get_farming_int, xp_to_level
from items import get_item_by_code
from engine import timestamp_now
import engine
import storage

# client ref.: src/Classes/Quest/FarmQuestComponent.as (initialize), templates/play.html (quest_url flashvar)
# The same file the client itself downloads and parses into FarmQuest/FarmTask objects, so quest names,
# task indexes and totals decoded here are by construction the ones the client is looking at.
QUESTS_XML = os.path.join(XML_DIR, "gz", "v855098", "questSettings_0.xml.gz")
CACHE_QUESTS_JSON = os.path.join(CACHE_DIR, "gz_v855098_questSettings_0.json")

# Bumped whenever the decoded shape below changes, so an existing cache from an older server build is
# rebuilt instead of silently missing fields. (cache/ is disposable - deleting it forces a re-decode too.)
CACHE_VERSION:int = 3

_cached_quests: dict = None       # quest name -> quest definition
_startable_quests: list = None    # names of quests whose prerequisites the server can decide (see below)
_replayable_chains: dict = None   # quest name -> the name of the first quest of its replayable chain
_max_active_replayable_quests: int = 0

# client ref.: src/Classes/Constants/QuestConstants.as
NEW_QUEST:int = 1
NON_NEW_QUEST:int = 0

# How many quests the player is given at once. The number itself is not in any recovered file -
# questSettings.xml only caps the quest manager's replayable slots (maxActiveReplayableQuests="6") - so this
# is an invented cap, kept low enough not to bury the HUD's icon queue. That there is a slot budget at all
# is not invented: 860 quests carry ignoreSlotLimit="true" precisely to sit outside it, and on the home farm
# every one of those is a background tracker with <icon>none</icon>, so they cost the player nothing.
MAX_ACTIVE_QUESTS:int = 5

# client ref.: src/Classes/Quest/FarmQuestUtility.as (getProgression)
# The task actions the server recounts for itself, out of the ~90 FarmQuestUtility predicts client-side.
# They are the ones that fall out of the world actions commands.py already implements.
TRACKED_TASK_ACTIONS = (
    "plowPlot",
    "plantCropByCode",
    "buyItemByCode",
    "harvestByCode",
    "useItemByCode",
    "viewDialog",
)

# client ref.: src/Classes/Quest/PrerequisiteUtility.as (isPrerequisiteMet)
# The prerequisite types the server can actually decide from a save. Everything else the file uses
# (prereq_check, feature_option, in_experiment, ...) depends on state we do not model, and a quest carrying
# one is never handed out rather than handed out wrongly - see _quest_is_startable().
SUPPORTED_PREREQS = (
    "start_time",
    "end_time",
    "level_min",
    "level_max",
    "quest_complete",
    "tracked_quest_complete",
    "location",
    "has_seen_flag",
    "acct_age_days_min",
    "coins",
    "cash",
)

def _as_list(node) -> list:
    # xmltodict collapses a single child element into a dict instead of a one-element list
    if node is None:
        return []
    if isinstance(node, list):
        return node
    return [node]

def _cache_quests() -> None:
    # Read .xml.gz file
    obj:bytes = open(QUESTS_XML, 'rb').read()

    # Decompress
    obj_decomp:bytes = zlib.decompress(obj)

    # Decode Object
    arr:dict = xmltodict.parse(obj_decomp)

    # Flatten every <quest> into the handful of fields the server needs. The client reads the rest
    # (frontend art, text bundles, helper actions) straight out of the same XML, so it is dropped here.
    quests = {}
    for quest in _as_list(arr["questSettings"]["quest"]):
        name = quest["@name"]
        quests[name] = {
            "name": name,
            "memStoreId": int(quest["@memStoreId"]) if quest.get("@memStoreId") else None,
            "category": quest.get("@category"),
            "priority": int(quest["@priority"]) if quest.get("@priority") else 0,
            "ignoreSlotLimit": quest.get("@ignoreSlotLimit") == "true",
            # client ref.: src/Classes/Quest/FarmQuest.as (addIconToIconQueue, ICON_NONE)
            # "none" means the quest draws no HUD icon, which is also the only way the player can open its
            # dialog - so a quest with no icon has no reachable UI at all.
            "icon": ((quest.get("frontend") or {}).get("icon") or "none"),
            "prereqs": [
                {"type": p.get("@type"), "value": p.get("@value")}
                for p in _as_list((quest.get("prereqs") or {}).get("prereq"))
            ],
            "tasks": [
                {
                    "action": t.get("@action"),
                    "type": t.get("@type"),
                    "total": int(t.get("@total") or 0),
                    # client ref.: src/Classes/Quest/FarmTask.as (m_cashValue / skipCashValue)
                    "cashValue": int(t.get("@cashValue") or 0),
                }
                for t in _as_list((quest.get("tasks") or {}).get("task"))
            ],
            "rewards": [
                {
                    "type": r.get("@type"),
                    "value": r.get("@value"),
                    "quantity": int(r["@quantity"]) if r.get("@quantity") else 1,
                }
                for r in _as_list((quest.get("rewards") or {}).get("reward"))
            ],
            "children": [
                c.get("@value")
                for c in _as_list((quest.get("children") or {}).get("child"))
                if c.get("@type") == "Quest" and c.get("@value")
            ],
        }

    # client ref.: src/Classes/Quest/FarmQuestSettingsInit.as (parseQuestManager / cacheQuestManagerQuestChain)
    # The <questManager> node names the first quest of each chain the Quest Manager window can replay; the
    # chain itself is found by walking children from there. Flattened to the same quest -> chain head map
    # questManagerGetNameOfFirstQuestInReplayableChain() looks things up in.
    quest_manager = arr["questSettings"].get("questManager") or {}
    replayable_quests = quest_manager.get("replayableQuests") or {}
    chains = {}

    def _cache_chain(name:str, first_quest_name:str) -> None:
        # the client recurses without a visited set; guarding costs nothing and cannot change the result
        if not name or name not in quests or name in chains:
            return
        chains[name] = first_quest_name
        for child in quests[name]["children"]:
            _cache_chain(child, first_quest_name)

    for node in _as_list(replayable_quests.get("replayableQuest")):
        first_quest_name = node.get("@firstQuestName")
        if first_quest_name:
            _cache_chain(first_quest_name, first_quest_name)

    # Save to cache as JSON
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
    json.dump({
        "version": CACHE_VERSION,
        "quests": quests,
        "replayableChains": chains,
        # client ref.: FarmQuestSettingsInit.getMaxActiveReplayableQuests / FarmQuestManager.hasReachedMaxActiveReplayableQuests
        "maxActiveReplayableQuests": int(replayable_quests.get("@maxActiveReplayableQuests") or 0),
    }, open(CACHE_QUESTS_JSON, 'w'))

def _load_quests_cache() -> dict:
    try:
        cached = json.load(open(CACHE_QUESTS_JSON, 'r'))
        if cached.get("version") == CACHE_VERSION:
            return cached
        print(" * Quests cache is from an older server build. Re-caching quests...")
    except (OSError, ValueError, KeyError, AttributeError):
        print(" * No usable quests cache found. Caching quests...")
    _cache_quests()
    return json.load(open(CACHE_QUESTS_JSON, 'r'))

def load_quests() -> None:
    # Load cache, (re)building it if it is missing or was written by an older build
    print(" * Loading quests cache...")
    cached = _load_quests_cache()
    global _cached_quests, _replayable_chains, _max_active_replayable_quests
    _cached_quests = cached["quests"]
    _replayable_chains = cached["replayableChains"]
    _max_active_replayable_quests = cached["maxActiveReplayableQuests"]

    # Narrow the 3233 quests down to the ones that can ever be handed out (see _quest_is_startable), so
    # assigning quests is a scan over a few hundred entries instead of the whole file.
    global _startable_quests
    _startable_quests = sorted(
        (name for name, quest in _cached_quests.items() if _quest_is_startable(quest)),
        key=_assignment_order,
    )
    print(f" * {len(_startable_quests)} of {len(_cached_quests)} quests are startable, "
          f"{len(_replayable_chains)} belong to a replayable chain")

def get_quests() -> dict:
    global _cached_quests
    return _cached_quests

def get_quest_by_name(name:str) -> dict:
    global _cached_quests
    return (_cached_quests or {}).get(name)

# Quest times

# client ref.: src/Classes/util/FarmGameUtil.as (synchronizedDateTimeToNumber / getGlobalServerUTCOffsetHours)
# "M/D/YYYY" or "M/D/YYYY H:MM[:SS]" read as UTC and shifted by globalServerUTCOffsetHours. The client adds
# another hour when it is not on DST, and the gateway always answers isDST = 0, so that hour is added here
# too - otherwise our idea of when a quest window opens is an hour off from the client's.
def _quest_time_to_timestamp(value:str) -> int:
    try:
        date_part, _, time_part = str(value).partition(" ")
        month, day, year = [int(x) for x in date_part.split("/", 3)]
        hms = [int(x) for x in time_part.split(":", 3)] if time_part else []
        hms += [0] * (3 - len(hms))
        offset = (get_farming_int("globalServerUTCOffsetHours", 4) + 1) * 3600
        return calendar.timegm((year, month, day, hms[0], hms[1], hms[2], 0, 0, 0)) + offset
    except Exception:
        # 108 quests carry a malformed end_time (all of them 2011 dates), which is treated as "long gone"
        return None

# end_time is decoded but deliberately never enforced. 2159 of the 3233 quests have a window that closed
# before the shutdown, and they are the ones with artwork: every quest carrying a HUD icon on the home farm
# is date-expired, so honouring end_time leaves the player with nothing visible at all. Nothing client-side
# objects to a reopened quest - FarmQuestManager.isQuestExpired() is only ever read by JournalManager for
# its bubble list, and QuestManager only treats a quest as expired when *we* say so in QuestComponent.
# start_time is still enforced, so a quest cannot turn up before its release date.

# Prerequisites

def _player_level(save:dict) -> int:
    return xp_to_level(save["userInfo"]["player"]["xp"]) or 1

def _prereq_met(save:dict, prereq:dict, completed:list) -> bool:
    prereq_type = prereq["type"]
    value = prereq["value"]

    if prereq_type == "start_time":
        start_time = _quest_time_to_timestamp(value)
        return start_time is not None and timestamp_now() >= start_time
    if prereq_type == "end_time":
        return True  # never enforced - see above
    if prereq_type == "level_min":
        return _player_level(save) >= int(value)
    if prereq_type == "level_max":
        return _player_level(save) <= int(value)
    if prereq_type in ("quest_complete", "tracked_quest_complete"):
        return value in completed
    if prereq_type == "location":
        # client ref.: src/Classes/Quest/PrerequisiteUtility.as (PREREQUISITE_LOCATION -> currentWorldType)
        return value == save["userInfo"]["currentWorldType"]
    if prereq_type == "has_seen_flag":
        return bool(save["userInfo"]["player"]["seenFlags"].get(value))
    if prereq_type == "acct_age_days_min":
        age = timestamp_now() - save["userInfo"]["firstDayTimestamp"]
        return age // 86400 >= int(value)
    if prereq_type == "coins":
        return save["userInfo"]["player"]["gold"] >= int(value)
    if prereq_type == "cash":
        return save["userInfo"]["player"]["cash"] >= int(value)

    # Not a prerequisite the server can decide - see SUPPORTED_PREREQS
    return False

# The order quests are handed out in. A server-side choice, not recovered behaviour, in three tiers:
#  - the next link of a chain the player already started (it has a quest_complete prerequisite, and that
#    prerequisite is met or it would not be a candidate) beats opening a brand new one. Without this the
#    entry points below - which finish instantly - would win every freed slot and the story quests they
#    unlock would never get one;
#  - then quests whose every task is one we recount, so the player does not end up with a HUD full of
#    quests that can never move because they are gated on a feature (feature crafting, mastery, storage
#    buildings) the server does not implement yet;
#  - then the file's own @priority.
def _assignment_order(name:str) -> tuple:
    quest = _cached_quests[name]
    continues_chain = any(p["type"] in ("quest_complete", "tracked_quest_complete") for p in quest["prereqs"])
    trackable = all(task["action"] in TRACKED_TASK_ACTIONS for task in quest["tasks"])
    return (0 if continues_chain else 1, 0 if trackable else 1, quest["priority"], name)

# Replayable chains

# client ref.: src/Classes/Quest/FarmQuestSettingsInit.as (questManagerGetNameOfFirstQuestInReplayableChain)
def replayable_chain_head(quest_name:str) -> str:
    return (_replayable_chains or {}).get(quest_name)

def _is_replayable_chain_head(quest_name:str) -> bool:
    return replayable_chain_head(quest_name) == quest_name

# Every quest of the chain quest_name belongs to. The client reaches for the same set the long way round,
# by walking children and parents (prepForStart/EndReplayableQuestChain -> questManagerGetListOf*Quests),
# which comes to the same thing on these chains because they are linear.
def _replayable_chain_quests(quest_name:str) -> list:
    head = replayable_chain_head(quest_name)
    if head is None:
        return []
    return [name for name, chain_head in _replayable_chains.items() if chain_head == head]

# A quest the server could hand out at some point: every prerequisite is one we can decide, and it has tasks
# to make progress on. Computed once at load time, so it deliberately only looks at the quest definition and
# never at a save.
def _quest_is_startable(quest:dict) -> bool:
    if not quest["tasks"]:
        return False
    # client ref.: src/Widgets/Windows/QuestManager/QMWReplayableQuestsBaseSlot.as (onStartQuestButtonClicked)
    # The first quest of a replayable chain is the player's to start, from the Quest Manager window - never
    # ours to hand out, or its Start/End buttons would mean nothing. The rest of the chain is ordinary: once
    # the head is done, each link unlocks through its quest_complete prerequisite like any other.
    if _is_replayable_chain_head(quest["name"]):
        return False
    return all(prereq["type"] in SUPPORTED_PREREQS for prereq in quest["prereqs"])

# Save state
#
# save["questState"] = {
#     "active":    {questName: {"progress": [int per task], "new": NEW_QUEST|NON_NEW_QUEST,
#                                "announced": bool}},   # only on the speech-bubble quests below
#     "completed": [questName, ...],   # finished, and so unlocks whatever depends on quest_complete
#     "retired":   [questName, ...],   # dismissed by the player, never handed out again
#     "replayed":  {firstQuestName: {"count": int, "lastCompleted": timestamp}},   # replayable chains
# }

def _quest_state(save:dict) -> dict:
    return save["questState"]

# client ref.: src/ZQuest/Managers/QuestManager.as (onTransactionComplete), src/Classes/Quest/FarmQuestManager.as
# What every gateway response carries as metadata.QuestComponent: one entry per active quest, which is how
# the client learns a quest exists at all. It must be an Array - the client walks it by index and length -
# and every entry needs explicit complete/expired booleans, which the "unfinished first" reordering tests
# with ==. baseCashValue is what FarmTask.cashValue prices a task skip from; feeding it the task's authored
# @cashValue makes the skip button charge what the XML says instead of being free.
def quest_component(save:dict) -> list:
    component = []
    for name, state in _quest_state(save)["active"].items():
        quest = get_quest_by_name(name)
        if quest is None:
            continue
        entry = {
            "name": name,
            "progress": list(state["progress"]),
            "complete": _announce_view_dialog_quest(quest, state),
            "expired": False,
            "new": state["new"],
        }
        # Only the quests that can actually put a dialog on screen need the skip pricing. The rest are the
        # icon-less background trackers, which ignoreSlotLimit lets pile up - around 60 of them on a
        # mid-level farm - and this rides on every single gateway response, so it is worth not sending.
        if quest["icon"] != "none":
            entry["baseCashValue"] = [task["cashValue"] for task in quest["tasks"]]
            entry["pricePerAction"] = [0 for _ in quest["tasks"]]
            entry["prorateTask"] = [False for _ in quest["tasks"]]
        component.append(entry)
    return component

# client ref.: src/Classes/Quest/FarmQuest.as (isViewDialogQuest / showReward), src/Classes/Quest/FarmQuestManager.as
# A story chain's entry point is a quest with a single viewDialog task, no rewards and <icon>none</icon>:
# it draws no HUD icon, it is the NPC speech bubble that introduces the chain, and finishing it unlocks the
# first quest that does have artwork. The only caller of showReward() - which pops that bubble and sends
# TUserTaskSeen back - is the completion path, so the quest has to arrive already complete or nothing ever
# shows it and the chain stalls forever holding a slot.
def _is_view_dialog_quest(quest:dict) -> bool:
    return (
        len(quest["tasks"]) == 1
        and quest["tasks"][0]["action"] == "viewDialog"
        and not quest["rewards"]
    )

# QuestManager.onTransactionComplete dispatches COMPLETED for a complete entry it has not already got in
# m_activeQuests - and it never files one away - so it would pop the bubble again on every single response.
# Hence announcing it exactly once; FarmQuestService.markViewDialogTaskDone is the client coming back.
def _announce_view_dialog_quest(quest:dict, state:dict) -> bool:
    if not _is_view_dialog_quest(quest) or state.get("announced"):
        return False
    state["announced"] = True
    return True

# Assignment

# client ref.: src/Transactions/TInitUser.as (isInitTransaction), src/ZQuest/Managers/QuestManager.as
# Called once per session, from UserService.initUser. "announced" is session state, not save state: the
# client starts every session with an empty m_activeQuests, so a speech bubble the last session never got
# round to popping has to be offered again. Without this reset it is announced once, ever - and since only
# the client coming back through markViewDialogTaskDone retires one, it would sit in active forever holding
# a slot, which on a farm whose slots are all bubbles means no quest can ever start again.
def start_session(save:dict) -> None:
    for state in _quest_state(save)["active"].values():
        state.pop("announced", None)
    refresh_active_quests(save)

# Also what FarmQuestService.fullQuestRefresh runs: FarmQuestManager's refresh timer queues it when a quest
# window is due to open or close, and the refreshed list rides back in metadata.QuestComponent.
def refresh_active_quests(save:dict) -> None:
    state = _quest_state(save)
    active = state["active"]
    completed = state["completed"]

    # Drop anything the config no longer defines
    for name in list(active.keys()):
        if get_quest_by_name(name) is None:
            del active[name]

    # client ref.: questSettings.xml (<quest ignoreSlotLimit="true">)
    # Fill the free slots, best candidate first. Quests flagged ignoreSlotLimit are handed out whether or
    # not there is room and never take a slot from one that needs it - without that, the invisible trackers
    # a low-level farm qualifies for would hold every slot and the story chains could never start.
    used_slots = sum(1 for n in active
                     if not _cached_quests[n].get("ignoreSlotLimit") and replayable_chain_head(n) is None)
    for name in _startable_quests:
        if name in active or name in completed or name in state["retired"]:
            continue
        quest = _cached_quests[name]
        # A replayable chain the player opened by hand has its own budget client-side
        # (maxActiveReplayableQuests), so it does not compete with the story quests for these slots either.
        takes_a_slot = not quest.get("ignoreSlotLimit") and replayable_chain_head(name) is None
        if takes_a_slot and used_slots >= MAX_ACTIVE_QUESTS:
            continue
        if all(_prereq_met(save, prereq, completed) for prereq in quest["prereqs"]):
            active[name] = {"progress": [0 for _ in quest["tasks"]], "new": NEW_QUEST}
            used_slots += 1 if takes_a_slot else 0
            print(f" * Started quest {name}")

# Progress

# The client predicts progress for every task action itself (FarmQuestComponent always passes a questUtility,
# so QuestSettingsInit.isClientPredictionEnabled is always true) and does not report the result back. The
# server therefore recounts, from the actions it already handles, only the task actions below - anything else
# (mastery levels, crafting, storage buildings, ...) is predicted client-side for the session but is back at
# its stored value on the next login.
def record_action(save:dict, action:str, item_code:str = None, amount:int = 1) -> None:
    for name, state in _quest_state(save)["active"].items():
        quest = get_quest_by_name(name)
        if quest is None:
            continue
        for index, task in enumerate(quest["tasks"]):
            if task["action"] != action:
                continue
            if task["type"] and item_code is not None and task["type"] != item_code:
                continue
            _advance_task(save, name, index, amount)

def _advance_task(save:dict, quest_name:str, task_index:int, amount:int) -> None:
    quest = get_quest_by_name(quest_name)
    state = _quest_state(save)["active"].get(quest_name)
    if quest is None or state is None or task_index >= len(quest["tasks"]):
        return
    total = quest["tasks"][task_index]["total"]
    state["progress"][task_index] = min(total, state["progress"][task_index] + amount)

# Rewards

# client ref.: src/Classes/util/UserRewardUtil.as (grantUserReward), src/Classes/Quest/FarmQuestManager.as (onQuestComplete)
# The client grants a finished quest's rewards to Global.player itself, before it tells the server anything,
# so these have to be applied with exactly the same amounts or the HUD drifts from the save - the same deal
# as the neighbour actions. Reward types beyond these are for features the server does not model yet; they
# are skipped rather than approximated.
def _grant_rewards(save:dict, quest:dict) -> None:
    for reward in quest["rewards"]:
        reward_type = reward["type"]
        value = reward["value"]
        quantity = reward["quantity"]
        if reward_type == "xp":
            engine.apply_xp_increment(save, int(value))
        elif reward_type == "coins":
            engine.apply_coins_diff(save, int(value))
        elif reward_type == "cash":
            engine.apply_cash_diff(save, int(value))
        elif reward_type == "item_grant":
            # client ref.: UserRewardUtil.as REWARD_GRANT_ITEM -> Global.player.addGift(item.name,"0",quantity)
            item_data = get_item_by_code(value)
            if item_data is None:
                print(f" * Warning: quest {quest['name']} grants unknown item code {value}")
                continue
            storage.store_deposit_item_by_name(save, item_data["name"], quantity, group=storage.GIFTBOX_ID)
        elif reward_type == "seen_flag":
            save["userInfo"]["player"]["seenFlags"][value] = True
        else:
            print(f" * Warning: quest {quest['name']} has an unhandled reward type {reward_type}")

# Commands

# client ref.: src/Transactions/TMarkQuestAsViewed.as, src/Classes/Quest/FarmQuest.as (isNew / setAsSeen)
def interacted_with_quest(save:dict, quest_name:str) -> None:
    state = _quest_state(save)["active"].get(quest_name)
    if state is not None:
        state["new"] = NON_NEW_QUEST

# client ref.: src/Transactions/Quests/TShareQuestLoot.as, src/Classes/Quest/FarmQuestManager.as (onQuestComplete)
# Sent from the reward dialog once the client has decided a quest is finished and has already granted its
# rewards locally. There is no other call that reports a completion, so this is what makes it stick: mirror
# the rewards into the save, retire the quest and let its children become startable.
# friendReward is the Facebook feed post that used to go with "share your loot" - it is read off the result
# and only posted when non-null, so it stays null.
def update_recently_completed_quests(save:dict, quest_name:str, should_generate_friend_reward:bool) -> dict:
    complete_quest(save, quest_name)
    return {"friendReward": None}

# Retiring a finished quest: mirror its rewards into the save, remember it (which is what satisfies its
# children's quest_complete prerequisite) and refill the slot it just freed. Idempotent, because more than
# one call can report the same completion - the speech-bubble quests come back through
# markViewDialogTaskDone and their reward dialog may also send updateRecentlyCompletedQuests.
def complete_quest(save:dict, quest_name:str) -> None:
    state = _quest_state(save)
    quest = get_quest_by_name(quest_name)
    if quest is None or quest_name not in state["active"]:
        return
    del state["active"][quest_name]
    if quest_name not in state["completed"]:
        state["completed"].append(quest_name)
    _grant_rewards(save, quest)
    _record_replayable_chain_completion(save, quest)
    print(f" * Completed quest {quest_name}")
    refresh_active_quests(save)

# client ref.: src/Widgets/Windows/QuestManager/QMWReplayableQuestsCompletedSlotFrame.as
# A replayable chain counts as run once the player finishes its last quest - the one with no children -
# and the Quest Manager's completed tab is keyed by the *head* of that chain.
def _record_replayable_chain_completion(save:dict, quest:dict) -> None:
    head = replayable_chain_head(quest["name"])
    if head is None or quest["children"]:
        return
    replayed = _quest_state(save)["replayed"]
    entry = replayed.setdefault(head, {"count": 0, "lastCompleted": 0})
    entry["count"] += 1
    entry["lastCompleted"] = timestamp_now()
    print(f" * Replayable quest chain {head} completed x{entry['count']}")

# client ref.: src/Transactions/Quests/TKillQuest.as, src/Transactions/Quests/TPauseQuest.as,
# src/Classes/Quest/FarmQuestManager.as (onKillQuest / onPauseQuest)
# The two buttons on the skip-quest dialog. Client-side they do exactly the same thing - drop the quest's
# HUD icon - and no call exists that brings a paused quest back, so the server cannot tell them apart
# either: both retire the quest. Retired is kept separate from completed so a quest the player walked away
# from does not satisfy its children's quest_complete prerequisite.
def retire_quest(save:dict, quest_name:str) -> None:
    state = _quest_state(save)
    if quest_name in state["active"]:
        del state["active"][quest_name]
    if quest_name not in state["retired"] and quest_name not in state["completed"]:
        state["retired"].append(quest_name)
    refresh_active_quests(save)

# client ref.: src/Transactions/Quests/TUserTaskSeen.as, src/Classes/Quest/FarmQuest.as (showReward)
# The "viewDialog" task is done the moment the player has read the quest's dialog. For a speech-bubble
# quest that is its only task, so this is also how the chain's entry point finishes and its first real
# quest becomes startable.
def mark_view_dialog_task_done(save:dict, quest_name:str) -> None:
    quest = get_quest_by_name(quest_name)
    state = _quest_state(save)["active"].get(quest_name)
    if quest is None or state is None:
        return
    for index, task in enumerate(quest["tasks"]):
        if task["action"] == "viewDialog":
            _advance_task(save, quest_name, index, task["total"])
    if all(state["progress"][i] >= task["total"] for i, task in enumerate(quest["tasks"])):
        complete_quest(save, quest_name)

# client ref.: src/Widgets/Windows/QuestManager/QMWReplayableQuestsBaseSlot.as (onStartQuestButtonClicked),
# src/Classes/Quest/FarmQuestManager.as (prepForStartReplayableQuestChain)
# The Quest Manager window's Start button. The client has just wiped the whole chain out of its own
# m_activeQuests and m_sessionCompletedQuests, so the server forgets it too - that is what "replayable"
# means here, a chain the player has already finished can be run again from the top - and then activates
# the head. The transaction's callback only closes the window, so the response carries no data.
def start_replayable_quest_chain(save:dict, first_quest_name:str) -> None:
    quest = get_quest_by_name(first_quest_name)
    if quest is None or not _is_replayable_chain_head(first_quest_name):
        print(f" * Warning: {first_quest_name} is not the head of a replayable quest chain")
        return
    _forget_replayable_chain(save, first_quest_name)
    state = _quest_state(save)
    state["active"][first_quest_name] = {"progress": [0 for _ in quest["tasks"]], "new": NEW_QUEST}
    print(f" * Started replayable quest chain {first_quest_name}")
    refresh_active_quests(save)

# client ref.: src/Widgets/Windows/QuestManager/QMWReplayableQuestsBaseSlot.as (onHandleEndQuestPrompt),
# src/Classes/Quest/FarmQuestManager.as (prepForEndReplayableQuestChain)
# The same window's End button: the player drops the chain. Its quests are only forgotten, not retired -
# the head is not something refresh_active_quests hands out, so the chain simply goes back to being one the
# Quest Manager offers to start again.
def end_replayable_quest_chain(save:dict, quest_name:str) -> None:
    if replayable_chain_head(quest_name) is None:
        print(f" * Warning: {quest_name} does not belong to a replayable quest chain")
        return
    _forget_replayable_chain(save, quest_name)
    print(f" * Ended replayable quest chain {replayable_chain_head(quest_name)}")
    refresh_active_quests(save)

def _forget_replayable_chain(save:dict, quest_name:str) -> None:
    state = _quest_state(save)
    for name in _replayable_chain_quests(quest_name):
        state["active"].pop(name, None)
        if name in state["completed"]:
            state["completed"].remove(name)
        if name in state["retired"]:
            state["retired"].remove(name)

# client ref.: src/Transactions/Quests/TSkipQuestTask.as, src/Widgets/Slots/GenericQuestTaskSlot.as
# Paying cash to finish a task outright. The client checks canBuyCash() and subtracts the price from
# Global.player.cash before queueing this, so the save has to lose the same amount - the price being
# FarmTask.cashValue, which quest_component() feeds from the task's authored @cashValue.
def skip_task(save:dict, quest_name:str, task_index:int) -> None:
    quest = get_quest_by_name(quest_name)
    if quest is None or task_index >= len(quest["tasks"]):
        return
    engine.apply_cash_diff(save, -quest["tasks"][task_index]["cashValue"])
    _advance_task(save, quest_name, task_index, quest["tasks"][task_index]["total"])

# client ref.: src/Transactions/Quests/TIncrementGenericFarmTask.as
# A task action the client cannot infer from any other transaction (watching an ad, opening the quest map),
# so it reports it explicitly. Every active task with that action advances by one.
def increment_generic_farm_task(save:dict, task_action:str) -> None:
    record_action(save, task_action)

# client ref.: src/Transactions/TPostInit.as (setPreviouslyCompletedQuests), src/Classes/Quest/FarmQuestManager.as
# postInit's completedQuests, which the client resolves through getNamedQuestsFromMemstoreIds() - so it is a
# list of the XML's memStoreId values, not of quest names.
# client ref.: src/Transactions/TPostInit.as (completedReplayableQuests), src/Classes/Quest/ReplayableFarmQuestData.as
# postInit's completedReplayableQuests: a map keyed by the chain head's memStoreId (TPostInit copies the key
# into the entry as memStoreId), which the Quest Manager's completed tab lists so the chain can be run
# again. hideFromQuestManagerComplete is what would keep one off that tab, so it is always false here.
def completed_replayable_quests(save:dict) -> dict:
    result = {}
    for head, entry in _quest_state(save)["replayed"].items():
        quest = get_quest_by_name(head)
        if quest is None or quest["memStoreId"] is None:
            continue
        result[str(quest["memStoreId"])] = {
            "completion_count": entry["count"],
            "completion_date": entry["lastCompleted"],
            "hideFromQuestManagerComplete": False,
        }
    return result

def completed_quest_memstore_ids(save:dict) -> list:
    ids = []
    for name in _quest_state(save)["completed"]:
        quest = get_quest_by_name(name)
        if quest is not None and quest["memStoreId"] is not None:
            ids.append(quest["memStoreId"])
    return ids
