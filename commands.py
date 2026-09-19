import math
import random

from player import session
from engine import timestamp_now
import engine
from items import get_item_by_name
from game_settings import level_to_xp

def _pick_weighted(pool: list) -> dict:
    return random.choices(pool, weights=[entry["weight"] for entry in pool])[0]

# client ref.: src/Widgets/Windows/FCSlotMachineWindow.as (grantReward), src/Widgets/Slots/FCSlotMachine/FCSlotMachineItemPanel.as
# The FC Slot Machine's reward pool/odds are server-authored data with no trace in any recovered client
# asset (TPostInit.as just expects postInit's fcSlotMachineRewards.allRewards/mgRewards to be non-empty, or
# it pops "invalid rewards for FC Slot Machine"). This pool is an invented, reasonable substitute - not
# FarmVille's original values - using item names/fields the client can actually resolve (see FCSlotMachineWindow.as
# grantReward()'s switch on payOut.type, and Player.as addGift() for why item_grant uses giftable animal items).
_FC_SLOT_MACHINE_REWARDS = [
    {"type": "coins", "quantity": 500, "classType": "1", "weight": 30},
    {"type": "coins", "quantity": 2000, "classType": "1", "weight": 20},
    {"type": "free_spin", "quantity": 1, "classType": "1", "weight": 20},
    {"type": "turbo_charger", "quantity": 1, "classType": "2", "weight": 15},
    {"type": "cash", "quantity": 1, "classType": "2", "weight": 8},
    {"type": "item_grant", "value": "cow", "quantity": 1, "classType": "2", "weight": 4},
    {"type": "item_grant", "value": "horse", "quantity": 1, "classType": "3", "weight": 2},
    {"type": "cash", "quantity": 3, "classType": "3", "weight": 1},
]

# Decorative "this week's prizes" panel (FCSlotMachinePrizeFrame) - only `value` (a FarmItem name) is read.
_FC_SLOT_MACHINE_MYSTERY_PRIZES = [
    {"value": "cow"},
    {"value": "horse"},
    {"value": "sheep"},
    {"value": "goat"},
]

_FC_SLOT_MACHINE_WIN_CHANCE = 0.35

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
        # client ref.: src/Transactions/TPostInit.as (pops "invalid rewards for FC Slot Machine" otherwise)
        "fcSlotMachineRewards": {
            "allRewards": _FC_SLOT_MACHINE_REWARDS,
            "mgRewards": _FC_SLOT_MACHINE_MYSTERY_PRIZES,
        },
        # client ref.: src/Display/QueuedIcon.as, gameSettingsCMS.xml's <icons> block (matched by name/code) -
        # "carnivalBooth" opens the Game Tent; which of its promo tiles show up is controlled separately by
        # flashHotParams' CARNIVAL_PROMOS_ACTIVE/CARNIVAL_PROMO_DEFAULT (see villages/initial.json, version.py).
        "hudIcons": ["scratchCard", "fcSlotMachine", "carnivalBooth"],
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

# client ref.: src/Transactions/TSetItemFlag.as, src/Classes/Player.as (setItemFlag/getItemFlag)
def set_item_flag(UID: str, flag: str, value: str) -> None:
    save = session(UID)
    # Values are always strings client-side; an empty string is the "unset" value,
    # but it still has to be stored so getItemFlag() stops returning undefined.
    save["userInfo"]["player"]["itemFlags"][flag] = "" if value is None else str(value)
    return

def save_options(UID: str, options: dict) -> None:
    save = session(UID)
    save["userInfo"]["player"]["options"] = options.copy()
    save["options"] = options
    return

# client ref.: src/Transactions/TSetSNExtendedPermissions.as, src/Classes/ExtendedPermissionState.as
def set_sn_extended_permissions(UID: str, permissions: dict) -> None:
    save = session(UID)
    # The client refreshes the social network permissions from the page (see the
    # FarmNS.FlashExtendedPermissionsManager shim in templates/play.html) and sends us the
    # whole map whenever it differs from what initUser handed it back in "snExtendedPermissions".
    # hasExtendedPermission() reads it as name -> truthy, so it is stored exactly as received.
    save["snExtendedPermissions"] = dict(permissions or {})
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

# client ref.: src/Transactions/TSetFeatureFrequencyWithBackoff.as, src/Classes/Player.as (incrementBackoffInterval)
def update_feature_frequency_with_backoff(UID: str, feature: str, backoff_increments: int) -> None:
    save = session(UID)
    backoff_increments = int(backoff_increments)
    # Mirror of Player.incrementBackoffInterval(): every time the feature is shown it gets
    # pushed back one more "<feature>_backoff_days" period (that attribute is never set in
    # gameSettings.xml, so it is always the client's default of 1 day), and the increment
    # count the client just computed is stored next to it under the "_backoff" postfix.
    # Unlike the plain timestamp variant, canShowFeatureWithBackoff() compares this value
    # against GlobalEngine.serverTime, which is in milliseconds.
    backoff_increment_days = 1
    next_time = (timestamp_now() + backoff_increments * backoff_increment_days * 86400) * 1000
    save["userInfo"]["player"]["featureFrequency"][feature] = next_time
    save["userInfo"]["player"]["featureFrequency"][feature + "_backoff"] = backoff_increments
    # The matching actionCounts["<feature>_backoff"] bump arrives on its own, as
    # Player.incrementBackoffInterval() also queues a TActionCount for it.
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

# client ref.: src/Transactions/TPostInit.as (getUserZid/onGetUserZid)
def w2e_get_user_zid(UID: str) -> dict:
    # The client only hands the zid over to the page's ad shim (FarmNS.setZid), which is a
    # logging stub in templates/play.html, so our UID is as good a "Zynga id" as any.
    return {"success": True, "zid": UID}

# client ref.: src/Classes/WatchToEarnManager.as (generateDailyTokens/onGenerateDailyToken)
def w2e_generate_daily_tokens() -> dict:
    # Watch-to-earn traded ad views for Farm Cash through an external ad network (IronSource);
    # that network is gone and templates/play.html only stubs out FarmNS.initW2e/showW2eIron,
    # so no ad can ever complete and no token could ever be redeemed via grantReward.
    # An empty token list is the state the client already handles: WatchToEarnManager falls
    # through to oninitW2e("") and hides the watch-to-earn HUD icon.
    return {"success": True, "Tokens": []}

def _apply_fc_slot_machine_reward(save: dict, reward: dict) -> None:
    quantity = int(reward["quantity"])
    if reward["type"] == "cash":
        engine.apply_cash_diff(save, quantity)
    elif reward["type"] == "coins":
        engine.apply_coins_diff(save, quantity)
    elif reward["type"] == "turbo_charger":
        engine.apply_turbo_chargers_diff(save, quantity)
    elif reward["type"] == "item_grant":
        engine.storage_deposit(save, reward["value"], quantity)
    # "free_spin" is tracked purely client-side (FeatureOptionsManager's SLOT_MACHINE/
    # SLOT_MACHINE_FREESPINS option, bumped locally by FCSlotMachineWindow.grantReward) - there is
    # nothing to mirror server-side for it yet, since UserService.saveFeatureOptions isn't handled.

# client ref.: src/Widgets/Windows/FCSlotMachineWindow.as (spin/onSpinTransactionComplete/stopSpin/grantReward)
def slot_spin(UID: str) -> dict:
    save = session(UID)

    won = random.random() < _FC_SLOT_MACHINE_WIN_CHANCE
    if won:
        reward = _pick_weighted(_FC_SLOT_MACHINE_REWARDS)
        pay_out = reward
        slots = [reward, reward, reward]
        _apply_fc_slot_machine_reward(save, reward)
    else:
        pay_out = None
        # 3 reel results that aren't all identical, so the client's own compareSlots() (which decides
        # whether to visually highlight a match) doesn't show a win when there isn't a payOut.
        while True:
            slots = random.choices(_FC_SLOT_MACHINE_REWARDS, k=3)
            if not (slots[0] == slots[1] == slots[2]):
                break

    return {
        "slots": slots,
        "payOut": pay_out,
    }

# client ref.: src/Transactions/TGetMOTD.as (perform, onComplete)
# client ref.: src/Display/MOTD.as (MOTD constructor - reads icon, text, dialog, title, buttonText, etc.)
def get_motd(UID: str, motd_seen_flag: str) -> dict:
    save = session(UID)

    # Track which MOTDs the player has seen in their save
    if "motdSeenFlags" not in save:
        save["motdSeenFlags"] = {}

    # Record that this MOTD was seen
    save["motdSeenFlags"][motd_seen_flag] = timestamp_now()

    # Return a basic MOTD response. The client expects motdData to have at least:
    # motdSeenFlag, dialog, icon, text. Most actual MOTDs are config-driven from client XML
    # (MarketData.xml, gameSettingsCMS.xml, etc.); this is a placeholder server-side MOTD.
    motd_data = {
        "motdSeenFlag": motd_seen_flag,
        "dialog": "MotdNormal",
        "icon": "MOTD_ICON",
        "text": "motd_default_message",
    }

    return {"motdData": motd_data}

# client ref.: src/Widgets/Windows/ScratchCardWindow.as (loadItemIconWithScratchData, grantUserReward's
# equivalent cases in UserRewardUtil.as). Like the FC Slot Machine, the reward pool/odds/card price are
# server-authored data with no trace in any recovered client asset - invented substitute, not FarmVille's
# original values. Reward "value" holds whatever loadItemIconWithScratchData expects per type: an amount
# for coins/cash_from_card, an item *code* (not name) for item_grant, nothing for scratch_card.
_SCRATCH_CARD_TILE_COUNT = 9
_SCRATCH_CARD_PRICE = 4  # Farm Cash
_SCRATCH_CARD_WIN_CHANCE = 0.15
_SCRATCH_CARD_NEAR_MISS_CHANCE = 0.35

_SCRATCH_CARD_REWARDS = [
    {"type": "coins", "value": "500", "weight": 30},
    {"type": "coins", "value": "2000", "weight": 20},
    {"type": "scratch_card", "weight": 15},
    {"type": "cash_from_card", "value": "1", "weight": 10},
    {"type": "item_grant", "item_name": "cow", "quantity": "1", "weight": 4},
    {"type": "item_grant", "item_name": "horse", "quantity": "1", "weight": 2},
    {"type": "cash_from_card", "value": "3", "weight": 4},
]

# Decorative "this week's prizes" panel - only `value` (a FarmItem *code*) is read.
_SCRATCH_CARD_MYSTERY_PRIZES = ["cow", "horse", "sheep", "goat"]

def _scratch_card_tile(reward: dict) -> dict:
    tile = {"type": reward["type"]}
    if reward["type"] == "item_grant":
        tile["value"] = get_item_by_name(reward["item_name"])["code"]
        tile["quantity"] = reward["quantity"]
    elif reward["type"] != "scratch_card":
        tile["value"] = reward["value"]
    return tile

def _apply_scratch_card_reward(save: dict, reward: dict) -> None:
    if reward["type"] == "cash_from_card":
        engine.apply_cash_diff(save, int(reward["value"]))
    elif reward["type"] == "coins":
        engine.apply_coins_diff(save, int(reward["value"]))
    elif reward["type"] == "item_grant":
        engine.storage_deposit(save, reward["item_name"], int(reward["quantity"]))
    # "scratch_card" (another free play) is granted purely client-side (ScratchCardWindow.grantFreeCard()).

def _build_scratch_card_tiles(win_tile: dict = None, near_miss_tile: dict = None) -> list:
    tiles = []
    if win_tile is not None:
        tiles.extend([win_tile] * 3)
    elif near_miss_tile is not None:
        tiles.extend([near_miss_tile] * 2)

    while len(tiles) < _SCRATCH_CARD_TILE_COUNT:
        candidate = _scratch_card_tile(_pick_weighted(_SCRATCH_CARD_REWARDS))
        # Cap at 2-of-a-kind so a filler tile can't accidentally complete an unintended 3-of-a-kind
        # (onSlotClick's compareScratchObjects() would then call scratchAll() with no winEntry/almostWon set).
        if sum(1 for tile in tiles if tile == candidate) < 2:
            tiles.append(candidate)

    random.shuffle(tiles)
    return tiles

# client ref.: src/Widgets/Windows/ScratchCardWindow.as (postLoadComplete/reloadDataFromBackend/onUnlock/onPlayAgain)
# The win/lose outcome (and its reward) is decided here, at "unlock" time, rather than deferred to the
# separate ScratchCardService.grantReward call the client fires once the player finishes scratching - simpler,
# and equivalent in effect since a bought card's outcome is already fixed before the reveal animation.
def scratch_card_get_data(UID: str, unlock: bool) -> dict:
    save = session(UID)

    data = {
        "mysteryGifts": [{"value": get_item_by_name(name)["code"]} for name in _SCRATCH_CARD_MYSTERY_PRIZES],
        "price_per_card": _SCRATCH_CARD_PRICE,
        "card": None,
        "almostWon": None,
        "winEntry": None,
    }

    if not unlock:
        return data

    outcome = random.random()
    win_tile = near_miss_tile = None

    if outcome < _SCRATCH_CARD_WIN_CHANCE:
        reward = _pick_weighted(_SCRATCH_CARD_REWARDS)
        win_tile = _scratch_card_tile(reward)
        data["winEntry"] = win_tile
        _apply_scratch_card_reward(save, reward)
    elif outcome < _SCRATCH_CARD_WIN_CHANCE + _SCRATCH_CARD_NEAR_MISS_CHANCE:
        near_miss_tile = _scratch_card_tile(_pick_weighted(_SCRATCH_CARD_REWARDS))
        data["almostWon"] = near_miss_tile

    data["card"] = _build_scratch_card_tiles(win_tile, near_miss_tile)
    return data

# client ref.: src/Widgets/Windows/Pigo/PigoWindow.as, src/Widgets/Slots/Pigo/PigoPrizeSlot.as
# The 6 physical prize-peg slots (mysteryId 0-5) plus the "set bonus" slot (mysteryId -1) are, again,
# server-authored data (items_opt.amf's pigov2game item references a "pigov2" lootTable name, but that table's
# actual contents are nowhere in any recovered client asset) - invented substitute using real giftable items.
# winCount is real, persisted per-player progress (save["pigoState"][gameTokenName][itemName]), incremented by
# PigoService.grantReward; the set-bonus slot's winCount is derived (1 once all 6 regular slots are >=1) rather
# than stored separately, since PigoWindow only ever *reads* it (checkForSetBonus()'s local grant never calls
# the server) and it's a pure function of the other 6 counts.
_PIGO_PRIZE_ITEMS = ["chicken", "duck", "goat", "goose", "pig", "rabbit"]
_PIGO_SET_BONUS_ITEM = "sheep"

_PIGO_TOKEN_ITEM_NAME = "consume_pigo_game_token"  # PigoWindow.TOKEN_CONSUMABLE_ITEM_NAME
_PIGO_TOKEN_PACKAGE_COUNT = 3  # PigoWindow.TOKEN_PACKAGE_COUNT

def _pigo_win_counts(save: dict, game_token_name: str) -> dict:
    return save.setdefault("pigoState", {}).setdefault(game_token_name, {})

def pigo_get_game_settings(UID: str, game_token_name: str) -> list:
    save = session(UID)
    win_counts = _pigo_win_counts(save, game_token_name)

    slots = [
        {"mysteryId": mystery_id, "itemName": item_name, "winCount": win_counts.get(item_name, 0)}
        for mystery_id, item_name in enumerate(_PIGO_PRIZE_ITEMS)
    ]
    has_set_bonus = all(win_counts.get(item_name, 0) > 0 for item_name in _PIGO_PRIZE_ITEMS)
    slots.append({
        "mysteryId": -1,
        "itemName": _PIGO_SET_BONUS_ITEM,
        "winCount": 1 if has_set_bonus else 0,
    })
    return slots

def pigo_buy_token(UID: str) -> str:
    save = session(UID)
    engine.storage_deposit(save, _PIGO_TOKEN_ITEM_NAME, 1)
    return "success"

def pigo_buy_token_package(UID: str) -> str:
    save = session(UID)
    engine.storage_deposit(save, _PIGO_TOKEN_ITEM_NAME, _PIGO_TOKEN_PACKAGE_COUNT)
    return "success"

def pigo_grant_reward(UID: str, game_token_name: str, item_name: str) -> dict:
    save = session(UID)
    win_counts = _pigo_win_counts(save, game_token_name)
    win_counts[item_name] = win_counts.get(item_name, 0) + 1
    engine.storage_deposit(save, item_name, 1)
    engine.storage_withdrawal(save, _PIGO_TOKEN_ITEM_NAME, 1)
    return {"complete": True}