import copy
import json
import math

from player import session, village, neighbor_uids, neighbor_metadata, save_session
from engine import timestamp_now
import engine
from items import get_item_by_name, get_item_by_code
from game_settings import level_to_xp, get_farming_int
import storage
import cellar_progression
import cove_port
import cove_shipping
import quests
import avatar
import market
import progression
import peaceful
import barn_actions
import ugc
import construction
import creative_worlds
import crafting
import heritage_pricing
import breeding
import pets
import world_travel
import minigames
import instant_growth
import world_scores
import bushels
import irrigation_rewards
import paid_buildings
import building_harvest
import england_shipping
import england_animals
import placement_receipts

# Prize pools remain documented local substitutes; the dedicated module owns
# their durable balances, request receipts, payment checks and reward lifecycle.
_FC_SLOT_MACHINE_REWARDS = minigames.SLOT_REWARDS
_FC_SLOT_MACHINE_MYSTERY_PRIZES = minigames.SLOT_MYSTERY_PRIZES

# client ref.: src/Transactions/TInitUser.as (onComplete), src/Classes/Player.as (newPlayer/isFirstDay/accountAge)
# The save doubles as the initUser response, so this is also where the "brand new player" state gets consumed:
# is_new is only true for the very first initUser after new_village() created the farm, and is cleared right
# after, so every later login takes the returning-player path (TInitUser.as' `if(!result.is_new)` block: daily
# lottery, friend-unwither toaster, cross-game onboarding, incremental gate limited items, email bits, first
# tractor flag) and Player.isNewPlayer stops being true.
# firstDay is true while the farm is less than a day old. firstDayTimestamp is the creation time and never moves
# (Player.accountAge = serverTime - firstDayTimestamp, read by quest prerequisites).
def init_user(UID: str) -> dict:
    save = session(UID)
    storage.start_session(save)
    storage.normalize_empty_building_contents(save)
    placement_receipts.start_session(save)
    breeding.normalize_baby_contents(save)
    breeding.normalize_legacy_dna(save)
    breeding.start_session(save)
    pets.start_session(save, now=timestamp_now())
    crafting.start_session(save)
    england_shipping.start_session(save)
    england_animals.start_session(save)
    bushels.initialize(save)
    irrigation_rewards.start_session(save)
    paid_buildings.start_session(save)
    import meadows_storage
    meadows_sequence_id = meadows_storage.start_session(save)
    building_harvest.start_session(save)
    cove_port.start_session(save)
    save.pop(cellar_progression.REQUESTS, None)
    save.pop("_coveShippingTransfers", None)
    save.pop("_coveShippingUse", None)
    # Temporary placement IDs belong to one Flash session. A reloaded client
    # restarts its ID counter, so old mappings must not alias the next object.
    # Same-session retries still resolve through the mappings until initUser.
    world_travel.clear_temporary_ids(save)
    save.pop("_constructionResponse", None)
    progression.ensure_state(save)
    progression.refresh_owned(save, len(neighbor_uids(UID)))
    peaceful.refresh(save)
    user_info = save["userInfo"]
    ts_now = timestamp_now()
    is_new = bool(user_info["is_new"])
    first_day = ts_now - user_info["firstDayTimestamp"] < 86400
    # client ref.: src/Transactions/TInitUser.as (isInitTransaction), src/ZQuest/Managers/QuestManager.as
    # Quests are handed out before the response snapshot is taken: initUser is the transaction that seeds
    # the client's active quest list, so whatever is not in this refresh has no HUD icon until the next one.
    # This is also where the per-session quest state is reset - see quests.start_session().
    quests.start_session(save)
    # Persisted state: the session that just started is no longer the player's first one.
    user_info["is_new"] = False
    user_info["firstDay"] = first_day
    user_info["worldSummaryData"][user_info.get("currentWorldType") or "farm"]["lastLoaded"] = ts_now
    # Flash sequences restart on login, but earned spins/cards/tokens persist.
    minigames.start_session(save)
    save.pop(instant_growth.REQUESTS_KEY, None)
    # Response: shallow copies, so the flags this session reports don't get persisted back into the save.
    data = dict(save)
    data["world"] = cellar_progression.client_world(save)
    # Transient goal envelopes travel once, on TFarmTransaction. Duplicating
    # them inside initUser makes PyAMF emit nested reference-to-reference
    # objects that the pinned Ruffle decoder cannot deserialize.
    data.pop("_progressionResponse", None)
    data.pop(bushels.PENDING_KEY, None)
    data.pop(irrigation_rewards.REQUESTS_KEY, None)
    data.pop(storage.REQUESTS_KEY, None)
    data.pop(placement_receipts.KEY, None)
    data.pop(placement_receipts.EPOCHS_KEY, None)
    data.pop("_constructionResponse", None)
    data.pop("_animalBreeding", None)
    data.pop(world_travel.STATE_KEY, None)
    data.pop(creative_worlds.ACCESS_MARKER, None)
    data.pop("_quintessentialOctober", None)
    data.pop("_localMinigames", None)
    data.pop("_petRequests", None)
    data.pop(instant_growth.REQUESTS_KEY, None)
    data.pop(england_shipping.REQUESTS_KEY, None)
    data.pop(england_shipping.TRANSFER_REQUESTS_KEY, None)
    data.pop(england_animals.REQUESTS_KEY, None)
    data.pop(england_animals.RESPONSE_KEY, None)
    data.pop(meadows_storage.STATE, None)
    data.pop(cellar_progression.REQUESTS, None)
    data.pop(cove_shipping.REQUESTS, None)
    data.pop(cove_port.REQUESTS_KEY, None)
    data.pop(cove_port.RESPONSE_KEY, None)
    data.pop(cove_port.AWARDED_KEY, None)
    data.pop("_coveShippingTransfers", None)
    data.pop("_coveShippingUse", None)
    data["userInfo"] = dict(user_info)
    data["userInfo"]["unlockedWorldContentLicenses"] = england_shipping.client_licenses(save)
    data["userInfo"]["is_new"] = is_new
    # The client reads these two off the response's top level, not off userInfo.
    data["is_new"] = is_new
    data["firstDay"] = first_day
    # Same deal for energy: Player.loadObject only picks up energyMax out of userInfo.player, so without
    # this mirror Global.player.energy ends up undefined (0) no matter what the save says.
    data["energy"] = user_info["player"]["energy"]
    data["pendingPresents"] = len(save.get("localPresents", []))
    data["breedingSkillStates"] = copy.deepcopy(save.get("breedingSkillStates") or {})
    # TInitUser consumes the design ledger at the response root before
    # loading userInfo/world. The saved userInfo field is its durable home.
    data["ugcItemData"] = copy.deepcopy(user_info.get("ugcItemData") or {})
    # client ref.: src/Transactions/TInitUser.as (setUnparsedFriendData), src/Managers/FriendManager.as
    # Two separate things, both required: the top-level compressed blob carries each neighbour's metadata,
    # while userInfo.player.neighbors is the plain uid list that flags which of them are actual neighbours.
    # FriendManager.parseFriends() only promotes a neighbour into the friend bar when the blob entry is
    # matched by a social-network user of the same uid, which templates/play.html's getFriendData() serves.
    data["neighbors"] = engine.compress_and_encode(neighbor_metadata(UID))
    data["userInfo"]["player"] = dict(user_info["player"])
    data["userInfo"]["player"]["neighbors"] = neighbor_uids(UID)
    # Managers.EmailManager.parseEmailBits treats a missing/zero flag plus
    # the local social bridge's email permission as a newly completed signup:
    # it opens a thank-you popup and promises an unrecovered email reward.
    # Consume that retired promotion in the client response only. Real email
    # permission state, incoming presents, and saved gift inventory are intact.
    data["userInfo"]["player"]["hasReceivedGiftForEmailPermissions"] = 1
    # client ref.: src/Engine/Managers/TransactionManager.as (setSequenceID/getSequenceID)
    # TInitUser.onComplete feeds this straight into setSequenceID, which tags every later batch with it.
    # Meadows storage retains this opaque namespace in durable receipts.
    # The numeric sequence counter independently restarts on client load.
    data["sequenceId"] = meadows_sequence_id
    return data

def post_init_user(UID: str) -> dict:
    data = {
        # client ref.: src/Transactions/TPostInit.as (reads result[KEY_LOADTIME_POSTINIT]),
        # src/Classes/util/LoadingMetricsRecorder.as (KEY_LOADTIME_POSTINIT)
        "req_postInitEndTimestamp": timestamp_now(),
        "postInitTimestampMetric": timestamp_now(), # Unused?
        "friendsFertilized": [],
        "totalFriendsFertilized": 0,
        "friendsFedAnimals": [],
        "totalFriendsFedAnimals": 0,
        "showBookmark": True,
        # client ref.: src/Transactions/TPostInit.as (showToolbarThankYou branch), src/Classes/util/ZLocUtils.as (tk_pk)
        # The FarmVille Game Bar was a Zynga browser toolbar, gone with the rest of their web platform - it
        # can no longer be installed, so its "thanks for installing" toaster must never fire. toolbarGiftName
        # is a "package:key" localization pair; anything else makes tk_pk return null and the toaster renders
        # its unsubstituted "{item}" placeholder.
        "showToolbarThankYou": False,
        "toolbarGiftName": None,
        "isAbleToPlayMusic": True,
        "FOFData": [],
        "prereqDSData": [],
        "neighborCount": len(neighbor_uids(UID)),
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
        "marketView": market.view(),
        "marketViewCraftingSkills": None,
        "avatarState": avatar_state(UID),
        "breedingState": None,
        "w2wState": None,
        "bestSellers": None,
        # client ref.: src/Transactions/TPostInit.as (setPreviouslyCompletedQuests) - memStoreIds, not names
        "completedQuests": quests.completed_quest_memstore_ids(session(UID)),
        # client ref.: src/Classes/Quest/ReplayableFarmQuestData.as - the Quest Manager's completed tab
        "completedReplayableQuests": quests.completed_replayable_quests(session(UID)),
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
    if minigames.acknowledge_action_counter(save, action):
        return
    if action not in save["userInfo"]["player"]["actionCounts"]:
        save["userInfo"]["player"]["actionCounts"][action] = 1
    else:
        save["userInfo"]["player"]["actionCounts"][action] += 1
    return

# client ref.: src/Classes/Player.as (setActionCount), src/Widgets/Windows/Promotions/EmailCampaignWindow.as
# Unlike incrementActionCount, the client sends the counter's new absolute value (an
# arbitrary int: EmailCampaignWindow stores a subscription status code in it, not a count).
def set_action_count(UID: str, action: str, value: int) -> None:
    save = session(UID)
    if minigames.acknowledge_action_counter(save, action):
        return
    save["userInfo"]["player"]["actionCounts"][action] = int(value)
    return

def reset_action_count(UID: str, action: str) -> None:
    save = session(UID)
    if minigames.acknowledge_action_counter(save, action):
        return
    if action in save["userInfo"]["player"]["actionCounts"]:
        save["userInfo"]["player"]["actionCounts"][action] = 0
    return

def set_seen_flag(UID: str, flag: str) -> None:
    save = session(UID)
    crafting.acknowledge_seen_flag(save, flag)
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

# client ref.: src/Transactions/TCreateImage.as, src/Managers/UserContentManager.as,
# src/Classes/Idle/AvatarFeedIdleTask.as
# This is a user-generated-content *image* upload, not where the avatar itself is stored (that is
# AvatarService.saveAvatar below): the client renders the avatar it already has to a PNG for a feed
# post. The callback only reads result.imagePath, and nothing here posts to a social network anymore,
# so the snapshot is dropped and the client is left without an image path.
def set_avatar_appearance(UID: str, name, png_b64, image_type) -> None:
    return

# client ref.: src/Transactions/TSaveAvatar.as (signedCall("AvatarService.saveAvatar", params, gender)),
# src/Classes/FarmGameWorld.as (onCustomizationScreenSave/saveAvatar)
def save_avatar(UID: str, customization_data: dict, gender: str) -> None:
    save = session(UID)
    world_travel.guard_active_world(save)
    if not isinstance(customization_data, dict) or gender not in ("male", "female"):
        raise ValueError("The avatar customization or gender is invalid.")
    # Preserve worn imported cosmetics when an old wardrobe ledger is incomplete.
    old_items = (save["userInfo"].get("avatar") or {}).get("items", {})
    owned = {str(value) for value in save["avatarState"]["unlocked"]}
    if isinstance(old_items, dict):
        owned.update(str(row["itemId"]) for row in old_items.values()
                     if isinstance(row, dict) and row.get("itemId") is not None)
    # What the client sends is the *parsed* customization map (slot -> item), plus the gender as a separate
    # argument. initUser hands the stored blob straight to new FarmAvatar(avatar) with no gender argument,
    # and FarmvilleClothingLoader parses it by its "version" field while FarmAvatar picks the gender out of
    # the blob itself, so both have to be folded back into one object here.
    # Only the itemId is kept: parseFVVersion1 rebuilds every slot from getItemById(itemId).toRawObject(),
    # and everything else the client sends (filename, categoryId, category, metaData - each colour is its
    # own appearanceItem, with its meta_data baked into avatar.xml) comes from that config anyway. Slots
    # without an itemId are dropped, exactly as parseFVVersion1 drops the ones it cannot resolve; SimpleNPC
    # refills them from the gender defaults. This also keeps the save JSON-serializable, since the incoming
    # AMF objects carry pyamf.Undefined values.
    items = {}
    for slot, item in (customization_data or {}).items():
        if isinstance(item, dict) and item.get("itemId") is not None:
            definition = avatar.get_item_by_id(item["itemId"])
            if definition is None:
                raise ValueError("The avatar cosmetic is unknown.")
            if not avatar.item_is_free(definition) and definition["itemId"] not in owned:
                raise ValueError("Buy or earn this avatar cosmetic before wearing it.")
            if not isinstance(slot, str) or not slot or len(slot) > 64:
                raise ValueError("The avatar cosmetic slot is invalid.")
            items[slot] = {"itemId": definition["itemId"]}
    # Trusted imported garments remain available after changing outfits.
    unlocked = save["avatarState"]["unlocked"]
    for item_id in sorted(owned):
        definition = avatar.get_item_by_id(item_id)
        if definition and not avatar.item_is_free(definition) and item_id not in unlocked:
            unlocked.append(item_id)
    save["userInfo"]["avatar"] = {
        "version": "fv_1",
        "gender": gender,
        "items": items,
    }

    # client ref.: src/Transactions/TSaveAvatar.as (rememberRecentlySavedConfig),
    # src/Classes/Avatar/AvatarItemState.as (rememberConfigurationItem)
    # The editor's "recently worn" row, which the client rebuilds from postInit's avatarState. It is keyed
    # by the item's own category in avatar.xml, not by the slot the client sends it under, and items that
    # are not in the config are dropped, exactly as rememberConfigurationItem() drops them.
    configurations = save["avatarState"]["configurations"].setdefault(gender, {})
    for item in items.values():
        item_data = avatar.get_item_by_id(item["itemId"])
        if item_data is not None:
            configurations[item_data["category"]] = item_data["itemId"]
    return

# client ref.: src/Classes/Avatar/AvatarItemState.as (initAvatarStateFromInitUser),
# src/Transactions/TPostInit.as (result["avatarState"])
# The avatar wardrobe, as postInit hands it back. Only the keys of "unlocked" are read (each is looked up
# in avatar.xml and kept as an AvatarItem), and this object *must* carry the key at all: without it
# avatarState.inventoryInitialized stays false and FarmGameWorld.displayAvatarCustomizationScreen()
# silently refuses to open the avatar editor.
def avatar_state(UID: str) -> dict:
    save = session(UID)
    return {
        "unlocked": {item_id: True for item_id in save["avatarState"]["unlocked"]},
        "configurations": save["avatarState"]["configurations"],
    }

# client ref.: src/Transactions/TBuyAvatarItem.as, src/Classes/Avatar/AvatarManager.as (buyAvatarItem)
def buy_avatar_item(UID: str, item_id: str) -> None:
    save = session(UID)
    world_travel.guard_active_world(save)
    item_data = avatar.get_item_by_id(item_id)
    if item_data is None:
        raise ValueError("The avatar cosmetic is unknown.")
    if item_data["itemId"] in {str(value) for value in save["avatarState"]["unlocked"]}:
        return  # A durable retry cannot charge or award purchase XP twice.
    if not item_data["buyable"]:
        raise ValueError("This avatar cosmetic is not available for purchase.")
    balance_key = {"coins": "gold", "cash": "cash"}.get(item_data["market"])
    if balance_key is None:
        raise ValueError("This avatar cosmetic is not for sale.")
    balance = save["userInfo"]["player"][balance_key]
    if (type(balance) not in (int, float) or not math.isfinite(balance)
            or balance < item_data["cost"]):
        raise ValueError("Not enough currency for this avatar cosmetic.")

    # AvatarManager.buyAvatarItem pays for the item and grants its XP client-side *before* queueing the
    # transaction (the same optimistic pattern as neighborAct), so the server has to apply the very same
    # amounts or the HUD drifts from the save. It only queues one at all once the payment went through,
    # and only for a coins/cash item - a free (or marketless) one matches no case in its switch, and
    # AvatarItemState.grantItem() throws outright on a free item, so neither is ever unlocked.
    if item_data["market"] == "coins":
        engine.apply_coins_diff(save, -item_data["cost"])
    elif item_data["market"] == "cash":
        engine.apply_cash_diff(save, -item_data["cost"])
    else:
        raise ValueError("This avatar cosmetic is not for sale.")
    print(" * Bought avatar item {}: {} {}".format(item_data["name"], item_data["cost"], item_data["market"].upper()))
    engine.apply_xp_increment(save, avatar.get_item_xp(item_data))

    if item_data["itemId"] not in save["avatarState"]["unlocked"]:
        save["avatarState"]["unlocked"].append(item_data["itemId"])
    return

# storageData["<id>"] is the contents ledger of the world object with that id (storage._sync_building_contents).
# engine.get_new_world_object_id hands a removed id to the next placement, so a destroyed object's ledger has to
# go with it or that placement inherits the old contents.
def _forget_building_contents(save: dict, object_id) -> None:
    storage_data = save["userInfo"]["player"].get("storageData") or {}
    storage_data.pop(str(int(object_id)), None)

def _guard_object_deletion(stored):
    item = get_item_by_name(stored.get("itemName"))
    if item and item.get("disallowDelete") in (True, 1, "1", "true"):
        raise ValueError("This catalog building cannot be sold or removed.")

_FEATURED_SLOT_LIMIT = 99  # sanity cap; the client's slot range was not recovered

def _set_featured_item(stored, snapshot, params) -> None:
    # client ref.: src/Classes/FeatureBuilding.as (setFeaturedItem) and src/Transactions/TSetFeaturedItem.as.
    # The client has already written featuredItems[slot] locally and sends {itemSlot, itemCode, metaHash,
    # removeOrAdd}; removeOrAdd true adds the item, false clears the slot. setFeaturedItem then calls
    # setState(STATE_BARE), so the building ends 'bare'. No charge is involved.
    entry = params[0] if isinstance(params, list) and params else params
    if not isinstance(entry, dict):
        raise ValueError("A featured item change requires one slot entry.")
    slot, code = entry.get("itemSlot"), entry.get("itemCode")
    meta, add = entry.get("metaHash"), entry.get("removeOrAdd")
    if (type(slot) not in (int, float) or not math.isfinite(slot) or slot != int(slot)
            or not 0 <= slot <= _FEATURED_SLOT_LIMIT):
        raise ValueError("A featured item slot must be a whole number within the allowed range.")
    if not isinstance(code, str) or not code or get_item_by_code(code) is None:
        raise ValueError("The featured item is not a catalog item.")
    if not isinstance(meta, str) or len(meta) > 128:
        raise ValueError("The featured item metadata hash is invalid.")
    if type(add) is not bool:
        raise ValueError("A featured item change must say whether it adds or removes the item.")
    # Accept FeatureBuilding and its named subclasses (OrchardFeatureBuilding, FeatureBuildingOpenUIOnClick, ...).
    # Plots, animals, trees and decorations never match, so their state cannot be set through this action.
    if (stored is None or "FeatureBuilding" not in str(stored.get("className"))
            or "FeatureBuilding" not in str(snapshot.get("className"))):
        raise ValueError("Featured items require one owned feature building.")
    featured = stored.get("featuredItems")
    featured = dict(featured) if isinstance(featured, dict) else {}
    key = str(int(slot))
    if add:
        featured[key] = {"itemCode": code, "metaHash": meta}
    else:
        featured.pop(key, None)
    stored["featuredItems"] = featured
    stored["state"] = "bare"

def _remove_alt_graphic(stored, params) -> None:
    # The client sends {name: graphic} as an Object, not as an Array. Accept the bare object or a one-entry list.
    entry = params[0] if isinstance(params, list) and params else params
    name = entry.get("name") if isinstance(entry, dict) else None
    if not isinstance(name, str) or not name or len(name) > 64:
        raise ValueError("Alternative graphic removal requires one graphic name.")
    if stored is None:
        # Same as clear and sell: a missing object has no graphic to remove, and nothing is created.
        return
    # MapResource.removeAlternativeGraphic maps 'snow' to 'snow_altgraphic' before it sends the removal.
    aliases = {name, "snow"} if name == "snow_altgraphic" else {name}
    saved = stored.get("altGraphic")
    if isinstance(saved, str) and saved in aliases:
        stored["altGraphic"] = ""

def world_perform_action(UID: str, actionName: str, m_save: dict, params: list, request_id=None,
                         sequence_id=None, *, _placement_receipted=False) -> int:
    save = session(UID)
    world_travel.guard_active_world(save)
    if actionName == 'store' and sequence_id is not None and (
            england_shipping.is_transfer_request(save, actionName, m_save, params)
            or breeding.is_baby_request(save, actionName, m_save, params)):
        # These exact legacy handlers own their receipts and intentionally
        # reset numeric counters on initUser. Fence delayed original packets
        # before they can consume another stacked unit in the new namespace.
        state = save.get("_meadowsStorage", {})
        if (not isinstance(sequence_id, str) or not sequence_id or len(sequence_id) > 128
                or not isinstance(state, dict) or sequence_id != state.get("sessionID")):
            raise ValueError("This specialized storage sequenceID is stale or unknown.")
    if actionName == 'transform':
        world_travel.guard_world_context(save, m_save, params)
        return england_animals.perform(save, m_save, params, request_id=request_id,
                                       now=timestamp_now())
    if actionName == 'purchaseStorageUpgrade':
        import meadows_storage
        world_travel.guard_world_context(save, m_save, params)
        return meadows_storage.purchase_storage_upgrade(save, m_save, params,
            request_id=(sequence_id, request_id) if sequence_id is not None else request_id)['id']
    if actionName == 'cancelStorageUpgrade' and world_travel.guard_active_world(save) == 'meadows':
        import meadows_storage
        world_travel.guard_world_context(save, m_save, params)
        return meadows_storage.acknowledge_paid_storage_upgrade(save, m_save, params,
            request_id=(sequence_id, request_id) if sequence_id is not None else request_id)['id']
    if actionName == "place" and request_id is not None and not _placement_receipted:
        world_travel.guard_world_context(save, m_save, params)
        return placement_receipts.dispatch(save, m_save, params,
            (sequence_id, request_id) if sequence_id is not None else request_id,
            lambda: world_perform_action(UID, actionName, m_save, params,
                request_id=request_id, sequence_id=sequence_id, _placement_receipted=True))
    if actionName == 'instantGrow':
        # TInstantGrow carries an airplane snapshot, often temporary. Handle it
        # before placement ID allocation and the generic object-snapshot merge.
        return instant_growth.perform(save, m_save, params, now=timestamp_now(),
                                      request_id=request_id)
    if actionName != 'neighborAct':
        world_travel.guard_world_context(save, m_save, params)
        if actionName == 'use' and m_save.get('itemName') == cove_shipping.CONSUMABLE:
            return cove_shipping.use(save, m_save, params, request_id=request_id)
        if cellar_progression.is_request(save, actionName, m_save):
            return cellar_progression.perform(save, actionName, m_save, params,
                request_id=request_id, sequence_id=sequence_id)
        port_result = cove_port.perform(save, actionName, m_save, params,
            request_id=request_id, sequence_id=sequence_id, now=timestamp_now())
        if port_result is not None:
            return port_result['id']
        creative_worlds.guard_action(save, actionName, m_save, params,
                                    neighbor_count=len(neighbor_uids(UID)))
    if actionName == 'setMultipleFeaturedItems' and world_travel.guard_active_world(save) == 'rainforest':
        import rainforest_features
        owner, selection = rainforest_features.garden_featured_items(save, m_save, params)
        # Reuse the established slot validation/persistence engine on a detached
        # copy. This batch sender saves only the selection; its omitted/forged
        # object fields, imported state and production clocks are not mutations.
        candidate = copy.deepcopy(owner)
        candidate['featuredItems'] = {}
        for slot, entry in selection.items():
            _set_featured_item(candidate, m_save, [{
                'itemSlot': int(slot), **entry, 'removeOrAdd': True}])
        owner['featuredItems'] = candidate['featuredItems']
        return owner['id']
    if actionName in paid_buildings.ACTIONS:
        return paid_buildings.perform(save, actionName, m_save, params,
            request_id=request_id, now=timestamp_now())["id"]
    if request_id is not None and england_shipping.is_transfer_request(save, actionName, m_save, params):
        return england_shipping.dispatch_world(save, actionName, m_save, params, request_id,
            lambda: world_perform_action(UID, actionName, m_save, params))
    if request_id is not None and pets.is_request(actionName, m_save):
        return pets.dispatch(save, actionName, m_save, params, request_id,
                             lambda: world_perform_action(UID, actionName, m_save, params))
    if request_id is not None and breeding.is_baby_request(save, actionName, m_save, params):
        return breeding.dispatch_world(save, actionName, m_save, params, request_id,
            lambda: world_perform_action(UID, actionName, m_save, params))
    # A targeted food snapshot describes the consumable, not its owned dog.
    if actionName == 'use' and pets.feed(save, m_save, params, uid=UID, now=timestamp_now()):
        return m_save['id']
    if actionName == 'neighborAct':
        # Neighbor IDs belong to the host, not the visitor's active/inactive
        # object namespace. Never merge a visitor-owned object into this action.
        neighbor_act(UID, params[0]["hostId"], params[0]["actionType"], m_save)
        return m_save["id"]
    if actionName in UNRESTORED_WORLD_ACTIONS:
        raise ValueError(UNRESTORED_WORLD_ACTIONS[actionName])
    world_travel.guard_action_object(save, m_save["id"])
    world_travel.guard_new_object_id(save, actionName, m_save["id"])
    if actionName == 'place':
        world_travel.guard_placement(save, m_save)
    gold_before_action = save["userInfo"]["player"]["gold"]
    object_id = m_save["id"]
    object_tempId = None

    if actionName == 'getStorageInfo':
        # TUpgradeStorage(TYPE_UPDATE) runs during FeatureBuilding startup. Its
        # callback treats an absent helperURL as no active social-upgrade
        # campaign. This read must never merge the client's save snapshot.
        owned = [obj for obj in save["world"]["objectsArray"] if obj.get("id") == object_id]
        if (type(object_id) not in (int, float) or not math.isfinite(object_id)
                or int(object_id) != object_id or len(owned) != 1):
            raise ValueError("Storage information requires one owned building.")
        building = owned[0]
        item = get_item_by_name(building.get("itemName"))
        fountain_probe = False
        if item and item.get("name") == "xrf_fountainofyouth":
            import rainforest_features
            fountain_probe = (not building.get("deleted")
                and building.get("className") == item.get("className")
                and bool(rainforest_features.rule(item, world_travel.guard_active_world(save))))
        if (not item or not (item.get("storageType") or item.get("name") in crafting.COTTAGES.values()
                             or fountain_probe)
                or any(m_save.get(key) != building.get(key) for key in ("itemName", "className"))):
            raise ValueError("Storage information requires the saved building's identity.")
        return object_id

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
            object_id = world_travel.next_object_id(save)

        # Save the temporary ID. Attention: this must be cleared before saving, otherwise it will interfere with future games' temporary IDs.
        m_save["tempId"] = object_tempId

        m_save["id"] = object_id

    storage.normalize_empty_building_snapshot(m_save)
    # Keep the raw target identity for a retried final construction deposit.
    # The normal merge below protects the server's completed building identity.
    construction_snapshot = copy.deepcopy(m_save)
    stored = engine.get_world_object_by_id(save["world"]["objectsArray"], object_id)
    if stored is not None and actionName in ("sell", "clear", "clearWithered"):
        _guard_object_deletion(stored)
    if actionName == 'TransformBuilding':
        if paid_buildings.is_classic_transform(save, construction_snapshot):
            return paid_buildings.perform(save, actionName, construction_snapshot, params,
                request_id=request_id, now=timestamp_now())["id"]
        transformed_id = breeding.transform_baby(save, construction_snapshot, params, now=timestamp_now())
        progression.refresh_owned(save)
        return transformed_id
    pets.guard_action(actionName, stored, m_save)
    if stored is not None:
        m_save = construction.preserve_fields(stored, m_save)
        m_save = storage.preserve_container_fields(stored, m_save)
        m_save = crafting.preserve_fields(stored, m_save)
        m_save = breeding.preserve_fields(stored, m_save)
        m_save = pets.preserve_fields(stored, m_save)
        m_save = irrigation_rewards.preserve_fields(stored, m_save)
        m_save = paid_buildings.preserve_fields(stored, m_save, action=actionName)
        m_save = building_harvest.preserve_fields(stored, m_save, action=actionName)
        m_save = cove_port.preserve_fields(stored, m_save)
        m_save = bushels.preserve_stall_fields(stored, m_save, action=actionName)
        # Client snapshots omit server-owned feature fields and imported data.
        # Keep them when a player moves, plants or harvests the same object.
        if m_save.get("contents") == [] and stored.get("contents"):
            # Original building save snapshots deliberately omit contents.
            # Storage transactions own this field, including imported metadata.
            m_save = {**m_save, "contents": stored["contents"]}
        m_save = {**stored, **m_save}
        if actionName == "move":
            # Moving changes position, never the saved unit's inventory variant.
            # Otherwise a moved Gnome could forge metadata before storage.
            m_save.pop("metadata", None)
            if "metadata" in stored:
                m_save["metadata"] = copy.deepcopy(stored["metadata"])
        stored_item = get_item_by_name(stored.get("itemName"))
        if actionName == 'move' and (stored.get("className") == "Plot"
                or (stored_item or {}).get("type") in ("animal", "tree")):
            # Moving a harvestable cannot change its identity or reset its clock.
            for key in ("itemName", "className", "state", "plantTime", "isBigPlot", "isJumbo"):
                if key in stored:
                    m_save[key] = stored[key]

    # Handle NaN values
    if "plantTime" in m_save and m_save["plantTime"] and type(m_save["plantTime"]) in [int, float] and math.isnan(m_save["plantTime"]):
        m_save["plantTime"] = None
    if "tempId" in m_save and m_save["tempId"] and type(m_save["tempId"]) in [int, float] and math.isnan(m_save["tempId"]):
        m_save["tempId"] = None
    if "buildTime" in m_save and m_save["buildTime"] and type(m_save["buildTime"]) in [int, float] and math.isnan(m_save["buildTime"]):
        m_save["buildTime"] = None

    # An expandable building's save object needs an expansionParts map or the client's world load throws
    # on it - the client never sends one (see engine.world_object_ensure_expansion_parts).
    engine.world_object_ensure_expansion_parts(m_save)

    # Some checks
    if ("itemName" not in m_save or m_save["itemName"] is None) and ("className" in m_save and m_save["className"] != "Plow"):
        print(" * Warning: no item name. World object id: {}".format(object_id))

    incoming_item = get_item_by_name(m_save.get("itemName"))
    crafting.guard_action(save, actionName, m_save)
    building_harvest.guard_action(actionName, stored, m_save)
    paid_buildings.guard_action(actionName, stored, m_save)
    breeding.guard_action(save, actionName, stored, m_save)
    is_deco = (m_save.get("className") == "UGCDecoration"
               or (stored or {}).get("className") == "UGCDecoration"
               or (incoming_item or {}).get("className") == "UGCDecoration")
    if is_deco and actionName not in ('place', 'move', 'store', 'sell', 'clear'):
        raise ValueError("This action cannot create or replace a custom decoration.")
    if construction.manages(incoming_item) and actionName not in ('place', 'move', 'store', 'sell', 'clear', 'harvest', 'neighborAct'):
        raise ValueError("This action cannot create or replace a construction building.")
    if actionName in ('place', 'move') and m_save.get("ugcItemUUID"):
        if not str((incoming_item or {}).get("className", "")).startswith("UGC"):
            raise ValueError("This item cannot use a custom design identity.")
    
    if pets.perform_action(save, actionName, m_save, params, now=timestamp_now()):
        return object_id

    if actionName == 'plow': # Here itemName is usually None
        if stored is not None and stored.get("state") == "plowed":
            return object_id
        # Place the plot
        engine.world_update_or_add_object(session(UID)["world"]["objectsArray"], m_save)
        # Decrease the plow cost
        engine.apply_gold_diff(save, -get_farming_int("plowCost", 15))
        # Increase 1 xp
        engine.apply_xp_increment(save, 1)
        quests.record_action(save, "plowPlot")

    elif actionName == 'place':
        item_data = get_item_by_name(m_save["itemName"])
        if pets.placement_retry(stored, m_save, params):
            return object_id
        if stored is None:
            if item_data.get("className") in ("Gnome", "CraftRewardGnome"):
                # New purchases have no imported unit variant. A genuine
                # withdrawal restores its metadata from storage below.
                m_save.pop("metadata", None)
            m_save = construction.initialize_placement(m_save)
            m_save = storage.initialize_container_placement(m_save, now=timestamp_now())
            m_save = crafting.initialize_placement(m_save)
            m_save = irrigation_rewards.initialize_placement(m_save, now=timestamp_now())
            m_save = building_harvest.initialize_placement(m_save, now=timestamp_now())
            m_save = paid_buildings.initialize_placement(m_save, now=timestamp_now())
            m_save = bushels.initialize_stall_placement(m_save)
            m_save = breeding.initialize_placement(m_save)
            m_save = pets.initialize_placement(save, m_save, params, now=timestamp_now(),
                                              neighbor_count=len(neighbor_uids(UID)))
            if m_save.get("className") == "StorageBuilding":
                m_save.setdefault("contents", [])
                storage.normalize_empty_building_snapshot(m_save)
        if is_deco and m_save.get("className") != 'UGCDecoration':
            raise ValueError("The custom decoration class does not match its blueprint.")
        if stored is not None and (stored.get("ugcItemUUID") or m_save.get("ugcItemUUID")):
            if any(stored.get(key) != m_save.get(key)
                   for key in ("itemName", "className", "ugcItemUUID")):
                raise ValueError("A placement retry cannot replace an existing custom design.")
        if (object_tempId is not None and stored is not None
                and stored.get("tempId") == object_tempId
                and all(stored.get(key) == m_save.get(key)
                        for key in ("itemName", "state", "position"))):
            return object_id
        if item_data.get("type") == "seed" and m_save.get("state") == "planted":
            if stored is not None and stored.get("className") == "Plot" and stored.get("state") in ("planted", "grown"):
                if (stored.get("itemName") == m_save.get("itemName")
                        and stored.get("position") == m_save.get("position")):
                    return object_id
                raise ValueError("An occupied plot must be cleared and plowed before planting another crop.")
            if stored is None or stored.get("className") != "Plot" or stored.get("state") != "plowed":
                raise ValueError("Planting requires an existing plowed plot.")
            from game_settings import xp_to_level
            from client_catalog import purchase_required_level
            world_type = save["userInfo"].get("currentWorldType") or "farm"
            if m_save.get("className") != "Plot":
                raise ValueError("This crop cannot be planted on the current farm.")
            if not creative_worlds.world_requirement_matches(item_data, world_type):
                # A locked crop the Home overlay excluded is refused with its reason.
                refusal = heritage_pricing.crop_refusal(item_data) if world_type == "farm" else None
                raise ValueError(refusal or "This crop cannot be planted on the current farm.")
            if (xp_to_level(save["userInfo"]["player"]["xp"]) or 0) < purchase_required_level(item_data):
                raise ValueError("The player's level is too low for this crop.")
            options = storage._given_options(params[0] if params else {})
            if (not (options.get("isGift") or options.get("isInventoryWithdrawal")
                     or options.get("isStorageWithdrawal"))
                    and not building_harvest.has_seed(save, item_data)):
                expected_currency = item_data.get("market") or "coins"
                currency = options.get("currency") or expected_currency
                if currency == "gold":
                    currency = "coins"
                if expected_currency not in ("cash", "coins") or currency != expected_currency:
                    raise ValueError("The purchase currency does not match this crop's recovered price.")
                cost = engine.catalog_price(item_data, "cash" if currency == "cash" else "cost")
                balance = save["userInfo"]["player"]["cash" if currency == "cash" else "gold"]
                if (cost is None or cost < 0 or type(balance) not in (int, float)
                        or not math.isfinite(balance) or balance < cost):
                    raise ValueError("Not enough currency for this crop's recovered price.")
            # Planting starts a real server timer. A client timestamp must not
            # backdate a crop and bypass its catalog growth duration.
            m_save["plantTime"] = math.floor(timestamp_now() * 1000)
        if m_save.get("ugcItemUUID") and any(
                obj.get("ugcItemUUID") == m_save["ugcItemUUID"] and obj["id"] != object_id
                for obj in save["world"]["objectsArray"]):
            raise ValueError("This custom design is already placed on the farm.")
        # T*Place sends the exact container ID. Home inventory (-2), gift box
        # (-1) and positive building IDs must each lose exactly one item.
        withdrawn = building_harvest.withdraw_seed_for_placement(save, item_data, m_save, params)
        if withdrawn is None:
            withdrawn = breeding.withdraw_for_placement(save, m_save["itemName"], params, m_save)
        if withdrawn is None:
            withdrawn = storage.withdraw_for_placement(save, m_save["itemName"], params, m_save)
        must_apply_costs = not withdrawn
        if must_apply_costs:
            item_data = crafting.purchase_catalog_item(save, item_data)
        if must_apply_costs and (save["userInfo"].get("currentWorldType") or "farm") in ("farm", "england"):
            options = storage._given_options(params[0] if params else {})
            creative_worlds.guard_market_purchase(save, item_data, options.get("currency"), existing=stored)
        if m_save.get("ugcItemUUID") and any(
                obj.get("ugcItemUUID") == m_save["ugcItemUUID"] and obj["id"] != object_id
                for obj in save["world"]["objectsArray"]):
            raise ValueError("This custom design is already placed on the farm.")
        m_save = crafting.initialize_mastery_sign(save, m_save)
        engine.world_update_or_add_object(session(UID)["world"]["objectsArray"], m_save)
        # Apply costs with currency if explicit
        if must_apply_costs:
            if params and len(params)>0 and "currency" in params[0]:
                engine.apply_item_cost(save, item_data, currency=params[0]["currency"])
            else:
                engine.apply_item_cost(save, item_data)
            pets.finish_purchase(save, m_save)
        if stored is None:
            bushels.finish_stall_placement(save, m_save, now=timestamp_now())
        # If planted an object, increase XP by plantXP
        if m_save.get("state") == "planted" and "plantXp" in item_data and item_data["plantXp"] is not None:
            print(" * Applying plant XP: {}".format(item_data["plantXp"]))
            engine.apply_xp_increment(save, item_data["plantXp"])
            quests.record_action(save, "plantCropByCode", item_data["code"])
        # Assume is bought object
        elif must_apply_costs:
            realXp = 0
            cost = engine.catalog_price(item_data, "cost")
            if "buyXp" in item_data and item_data["buyXp"] is not None:
                realXp = int(item_data["buyXp"])
            elif cost is not None:
                realXp = cost // 100
            print(" * Applying buy XP: {}".format(realXp))
            engine.apply_xp_increment(save, realXp)
        # Original quest rules count market and gift-box placements as buys,
        # but moving items out of home/building storage is not another buy.
        options = storage._given_options(params[0] if params else {})
        is_gift_placement = bool(options.get("isGift")) or options.get("isStorageWithdrawal") == storage.GIFTBOX_ID
        if m_save.get("state") != "planted" and (must_apply_costs or is_gift_placement):
            quests.record_action(save, "buyItemByCode", item_data["code"])
            quests.record_item_action(save, "buy", item_data, placed_object=m_save)
        if m_save.get("itemName") in crafting.COTTAGES.values():
            if stored is None:
                crafting.finish_placement(save, m_save, now=timestamp_now())
            crafting.initialize(save)
        # largeCropXp is not a placement reward: Plot.doHarvestDropOff() adds it when a plot that is
        # flagged isBigPlot is *harvested*, so it is applied in the 'harvest' branch below instead.
    
    elif actionName == 'harvest':
        if stored is None:
            raise ValueError("The harvested object is missing from this farm.")
        england_animals.guard_harvest(save, stored)
        # The client reports the post-harvest state, not a new catalog item.
        # Rewards and quest categories must follow the crop/animal we own.
        m_save["itemName"] = stored.get("itemName")
        m_save["className"] = stored.get("className")
        if storage.home_habitat_container_class(get_item_by_name(stored.get("itemName"))):
            raise ValueError("This habitat's original harvest reward generator is not restored; its contents and clock were preserved.")
        herb_reward = building_harvest.harvest(save, stored, now=timestamp_now(),
                                              request_id=request_id)
        if herb_reward is not None:
            if herb_reward:
                herb_item = get_item_by_name(stored["itemName"])
                quests.record_action(save, "harvestByCode", herb_item["code"])
                quests.record_item_action(save, "harvest", herb_item)
            return object_id
        well_water = irrigation_rewards.harvest(save, stored, now=timestamp_now(),
                                              request_id=request_id)
        if well_water is not None:
            if well_water:
                well_item = get_item_by_name(stored["itemName"])
                quests.record_action(save, "harvestByCode", well_item["code"])
                quests.record_item_action(save, "harvest", well_item)
            return object_id
        orchard_harvest = paid_buildings.harvest_orchard(save, stored, now=timestamp_now(),
                                                       request_id=request_id)
        if orchard_harvest is not None:
            if orchard_harvest:
                orchard_item = get_item_by_name(stored['itemName'])
                quests.record_action(save, "harvestByCode", orchard_item['code'])
                quests.record_item_action(save, "harvest", orchard_item)
                progression.record_coins(save, earned=max(0,
                    save['userInfo']['player']['gold'] - gold_before_action))
            return object_id
        if barn_actions.harvest_for_game(save, stored, now=timestamp_now()):
            return object_id
        if stored.get("className") == "Plot" and stored.get("state") in ("fallow", "plowed"):
            # A transport retry after the first harvest must not pay twice.
            return object_id
        # Apply production reward
        item_data = get_item_by_name(m_save["itemName"])
        if stored.get("className") == "Plot" and item_data.get("type") == "seed":
            grow = peaceful.grow_seconds(item_data)
            planted = stored.get("plantTime")
            if (grow is None or type(planted) not in (int, float)
                    or not math.isfinite(planted)
                    # timestamp_now is whole seconds, matching tree cooldowns.
                    or timestamp_now() - planted / 1000 < grow - 1):
                raise ValueError("This crop has not finished growing.")
            if stored.get("state") == "withered" and not peaceful.enabled(save):
                raise ValueError("A withered crop must be revived before harvesting.")
        if item_data.get("type") in ("animal", "tree"):
            grow = peaceful.grow_seconds(item_data)
            if (stored.get("state") == "bare" and grow
                    and timestamp_now() - float(stored.get("plantTime") or 0) / 1000 < grow - 1):
                return object_id
        # HarvestableItem.bushelItemCode/get reads one String through
        # FarmItem.getXMLProperty. Eight archived seeds instead decode with
        # multiple values; do not choose a bushel or pass a list to the index.
        if (item_data.get("type") == "seed"
                and (save["userInfo"].get("currentWorldType") or "farm") == "farm"
                and item_data.get("bushelItemCode") is not None
                and not isinstance(item_data["bushelItemCode"], str)):
            raise ValueError("This crop's archived bushel mapping is ambiguous and is not restored.")
        bushels.harvest(save, item_data, stored, now=timestamp_now())
        engine.apply_item_yield_reward(save, item_data)
        # client ref.: src/Classes/Plot.as (doHarvestDropOff)
        # Harvest XP does not come from the seed: no seed item in items_opt.amf carries an xpYield, so
        # everything the client adds comes from the two flags the plot itself is carrying. Both are part
        # of Plot.getSaveObject(), and both are still set in the snapshot that arrives here - harvest()
        # builds THarvest before doHarvestDropOff() clears them.
        # The coin side needs nothing extra: fertilizeHarvestCoinMult is 1 in the recovered settings, and
        # the organic-certification / super-plot / power-hour multipliers are all experiment-gated, so
        # with no experiments served every one of them resolves to 1 and coinYield is already final.
        if m_save.get("isBigPlot") and item_data.get("largeCropXp") is not None:
            print(" * Applying large crop XP: {}".format(item_data["largeCropXp"]))
            engine.apply_xp_increment(save, int(item_data["largeCropXp"]))
        if m_save.get("isJumbo"):
            # Fertilized ("jumbo") plot. Organic fertilizer is the other way a plot gets here, and it pays
            # organicFertilizerXPGain instead - but that flag lives in the world's extraItemFlags bitfield,
            # which no transaction ever sends back, so the server cannot tell the two apart and treats
            # every jumbo plot as ordinarily fertilized.
            print(" * Applying fertilized harvest XP")
            engine.apply_xp_increment(save, get_farming_int("fertilizeHarvestXpGain", 1))
        quests.record_action(save, "harvestByCode", item_data["code"])
        quests.record_item_action(save, "harvest", item_data)
        if item_data.get("type") in ("animal", "tree"):
            # SimpleHarvestableResource queues THarvest BEFORE setting bare
            # and restarting plantTime. Reproduce that post-harvest state;
            # persisting its incoming snapshot makes every reload ready again.
            m_save.update(state="bare", plantTime=timestamp_now() * 1000)
        elif stored.get("className") == "Plot" and item_data.get("type") == "seed":
            # The owned crop has been consumed regardless of whether the
            # transaction carries a pre-harvest or post-harvest snapshot.
            m_save["state"] = "fallow"
        # Replace the object (probably a Plow) with the new one (usually with status "fallow")
        engine.world_update_or_add_object(session(UID)["world"]["objectsArray"], m_save)

    elif actionName == 'move':
        m_save = pets.move_fields(m_save, params)
        if stored and (stored.get("ugcItemUUID") or m_save.get("ugcItemUUID")):
            if any(stored.get(key) != m_save.get(key)
                   for key in ("itemName", "className", "ugcItemUUID")):
                raise ValueError("Moving a house cannot change its custom design.")
            ugc.validate_owned_state(save, stored["ugcItemUUID"], stored["itemName"])
        engine.world_replace_object(session(UID)["world"]["objectsArray"], m_save)

    elif actionName in ('clear', 'clearWithered'):
        if stored is None:
            return object_id
        if actionName == 'clearWithered':
            engine.world_replace_object(save["world"]["objectsArray"], m_save)
        else:
            engine.world_remove_object(save["world"]["objectsArray"], object_id)
            bushels.finish_stall_removal(save, stored)
            _forget_building_contents(save, object_id)
            ugc.award_recycling(save, get_item_by_name(stored.get("itemName")))
            if stored.get("className") == "Plot":
                engine.apply_coins_diff(save, -get_farming_int("plowCost", 15))

    elif actionName == 'sell':
        if stored is None:
            return object_id
        item_data = get_item_by_name(stored.get("itemName"))
        if not item_data:
            raise ValueError("This object's catalog entry is unavailable.")
        engine.world_remove_object(save["world"]["objectsArray"], object_id)
        bushels.finish_stall_removal(save, stored)
        _forget_building_contents(save, object_id)
        engine.apply_coins_diff(save, engine.item_sell_price(item_data))
        ugc.award_recycling(save, item_data)

    elif actionName == 'RemoveAltGraphic':
        # client ref.: src/Classes/MapResource.as (removeAlternativeGraphic, removeOverlay). The client sends this
        # inside the sell and store batches. Only the named graphic is cleared. The alt-graphic credit refund
        # (Managers/AltGraphicUtility.creditOnRemove) is client-side and not recorded by this server.
        _remove_alt_graphic(stored, params)

    elif actionName == 'setFeaturedItem':
        _set_featured_item(stored, construction_snapshot, params)

    elif actionName == 'store':
        construction.take_response(save)
        # Original inventory purchases address a negative container ID, not a
        # placed construction building. Let storage validate that exact group.
        construction_result = (None if world_travel._integer(object_id) and object_id < 0 else
            construction.store_for_game(save, construction_snapshot, params[0], now=timestamp_now(), request_id=request_id))
        if construction_result is None:
            if breeding.feed_bottles(save, construction_snapshot, params[0], now=timestamp_now()) is None:
                if breeding.store_for_game(save, m_save, params[0], now=timestamp_now()) is None:
                    storage.store_world_item(save, m_save, params[0],
                        request_id=(sequence_id, request_id) if sequence_id is not None else request_id,
                        request_snapshot=construction_snapshot)
        else:
            completed = engine.get_world_object_by_id(save["world"]["objectsArray"], object_id)
            quests.record_construction_change(save, stored, completed)

    elif actionName == 'use':
        item_name = m_save["itemName"]
        storage_group_id = params[0]["storageId"]
        count = params[0]["itemCount"]
        storage.consume_by_name(save, item_name, count, storage_group_id)
        quests.record_action(save, "useItemByCode", get_item_by_name(item_name)["code"], count)

    elif actionName == 'neighborAct':
        # client ref.: src/Transactions/NeighborActions/TBaseNeighborAction.as (perform)
        neighbor_act(UID, params[0]["hostId"], params[0]["actionType"], m_save)

    if actionName != 'neighborAct':
        if (actionName == 'store' and stored is not None
                and engine.get_world_object_by_id(save["world"]["objectsArray"], object_id) is None):
            bushels.finish_stall_removal(save, stored)
        coin_delta = save["userInfo"]["player"]["gold"] - gold_before_action
        progression.record_coins(save, earned=max(0, coin_delta), spent=max(0, -coin_delta))
    if actionName == 'harvest':
        progression.record_harvest(save, item_data, m_save)
    elif actionName == 'plow':
        progression.increment_ribbon(save, "lordoftheplow")
    elif actionName == 'place' and item_data.get("type") == 'seed':
        progression.increment_ribbon(save, "needforseed")
    if actionName in ('place', 'sell', 'store', 'clear'):
        progression.refresh_owned(save)
    if actionName not in HANDLED_WORLD_ACTIONS:
        log_unhandled_world_action(actionName, m_save)
    return object_id


# Client actions the server cannot reproduce from the original contract. Each one
# raises (per-call FORCE_RELOAD, save-error overlay) rather than acknowledging a
# change that would vanish on reload. The rejected call changes no save bytes;
# other accepted calls in the same AMF batch remain durable.
# Client refs (src/...): Transactions/TRedeemFertilize and TRedeemUnwither (no charge,
# entitlement from neighbour-action records this server never issues),
# TCompleteNow and THarvestReadyNow (cash deducted client-side), TMakeSlop (bushel
# deducted from the client crafting inventory), TAnimalTransform (grow-up classes with
# item, cash or random cost; TMystreeTransform and TMystreeReskinTransform also send
# 'transform', with plotId and featureName, so they are rejected by the same name),
# TGenericWorldObjectTransaction 'wither' / 'upgradeBuilding'
# / 'ExpandWithCurrency' (client-side cost or storage-level penalty), TPaintBuilding
# (Player.tryBuy on the paint item, client-side currency only), TDeprecateItem (reward
# gift-box items come back in the response), TUpgradeStorage, TSetAltGraphic and
# TSetOverlay (client-side alt-graphic credits or cash, from GMSetAltGraphic and the
# webOverlay trick action), TUnlockFestivalOfColorGraphic (deducts a colour pack and grants
# credits client-side), TSetOverlayOverride (value domain not recovered), TSetMultipleFeaturedItems
# (no live sender in the client), TPigHunt (truffle result comes back in the response), TCreditsPassNeighbor (reward
# URL comes back in the response), TSetFestivalOfColorGraphic (client-chosen colour from
# an unlock state the server does not record). See macOS/Documentation/CLIENT_ACTION_AUDIT.md.
UNRESTORED_WORLD_ACTIONS = {
    'redeemNeighborFertilize': "Neighbour fertilize redemption is not restored on this server.",
    'redeemNeighborUnwither': "Neighbour unwither redemption is not restored on this server.",
    'HarvestReadyNow': "Instant harvest is not restored on this server.",
    'CompleteNow': "Instant completion is not restored on this server.",
    'makeSlop': "Pig slop from bushels is not restored on this server.",
    'transform': "Animal growth is not restored on this server.",
    'wither': "Feature building withering is not restored on this server.",
    'upgradeBuilding': "Building upgrades are not restored on this server.",
    'ExpandWithCurrency': "Paid building expansion is not restored on this server.",
    'upgradeStorage': "Storage upgrades are not restored on this server.",
    'purchaseStorageUpgrade': "Storage upgrades are not restored on this server.",
    'cancelStorageUpgrade': "Storage upgrade cancellation is not restored on this server.",
    'paint': "Building paint is not restored on this server.",
    'deprecate': "Building removal and its reward are not restored on this server.",
    'SetAltGraphic': "Alternative graphics are not restored on this server.",
    'SetOverlay': "Overlays are not restored on this server.",
    'setOverlayOverride': "Building visual overrides are not restored on this server.",
    'SetFestivalOfColorGraphic': "Festival of Color graphics are not restored on this server.",
    'UnlockFestivalOfColorGraphic': "Festival of Color unlocks are not restored on this server.",
    'setMultipleFeaturedItems': "Featured item batch saves are not restored on this server.",
    'huntTruffle': "Pig truffle hunts are not restored on this server.",
    'createFriendRewardForPassing': "Friend rewards for passing a neighbour are not restored on this server.",
    # Each sender was confirmed by disassembling the served client (2026-10-23): the client grants the reward
    # or deducts the price locally and this server records neither. Event, voting, credit and present flows.
    'buyRedeemItem': "Redeem store purchases are not restored on this server.",
    'buyVoteItem': "Voting prize purchases are not restored on this server.",
    'tradeSubcredits': "Subcredit trades are not restored on this server.",
    'addMultipleCredits': "Credit building rewards are not restored on this server.",
    'openPresent': "Feature presents are not restored on this server.",
    'sendPresent': "Sending feature presents is not restored on this server.",
    'openOrTrade': "Holiday presents are not restored on this server.",
    'awardGifts': "Holiday tree gifts are not restored on this server.",
    'giftHarvestItem': "Gift flower decorations are not restored on this server.",
    # Remaining archived mutations recovered from the original transaction senders during takeover.
    # Social reward-link reads are deliberately separate; no startup/read prefix is refused here.
    'UnlockNow': "Treasure unlocking is not restored on this server.",
    'RemoveMysteryCrate': "Mystery crate removal is not restored on this server.",
    'RemoveMysteryCrateBuilding': "Mystery crate removal is not restored on this server.",
    'MysteryCrateCompleteNow': "Paid mystery crate completion is not restored on this server.",
    'UpdateViralTime': "Mystery crate social request state is not restored on this server.",
    'GrantRetroactiveUpgrade': "Retroactive building upgrade rewards are not restored on this server.",
    'finishVoting': "Ticket-party voting is not restored on this server.",
    'buyItemPutGiftbox': "Credit-building gift purchases are not restored on this server.",
    'awardOpenedGifts': "Holiday gift awards are not restored on this server.",
    'nutureFlowerShack': "Flower Shack nurturing is not restored on this server.",
}

# Gateway service calls (not performAction names) whose effect this server cannot save. The gateway raises
# for each of them, so the call changes no save bytes and is not logged as silently acknowledged. Verified
# against the served client's transaction senders (2026-10-23):
#   FarmService.buyFuel / buyTurboChargers: fuel and turbo effects are client-only (no energy model).
#   IrrigationService.onIrrigationAction and consumeIrrigationPackages are not listed: watering is restored
#     (see irrigation_action and consume_water_packages).
#   ResourceEquipmentWorldService.onUseEquipment: vehicle resource harvest, rewards are client-side.
#   UserService.toggleWither: decoration wither state, which the server does not store.
#   NeighborActionService.depositAnimalFeed: feed deposited into a host's animals, not recorded.
# NeighborActionService.clearNeighborAction is deliberately not listed: the server never issues neighbour-action
# records, so there is nothing for it to clear and it carries no charge.
# Read-only calls to social backends that no longer exist (friend sets, friend leaderboards, the 10th
# anniversary card, scheduled push messages), mapped to the empty reply each client handler accepts.
# Checked by disassembling the v855097 FarmGame.swf with macOS/Scripts/client-inspection/abcdis.py:
#   TInitializeLonelyAnimalFriendSet.onComplete reads data.uids && data.pending, so null throws #1009; {} skips.
#   TGetLeaderboardFriendLists.onComplete starts with if (data): null skips.
#   FarmvilleAnniversaryV10BirthdayCard.showGiftPopUp for-each's over data: null grants nothing.
#   PostInitSettings.scheduleAutomatedMessagesCheck registers no callback.
ABSENT_SOCIAL_READS = {
    "LonelyAnimalFriendSetService.getLonelyAnimalFriendSetData": {},
    "LeaderboardService.getBatchFriendLists": None,
    "FVV10AnniversaryBirthdayCardService.getGiftForUser": None,
    "AutomatedMessagesService.scheduleChecks": None,
}

UNRESTORED_SERVICE_CALLS = {
    'FarmService.buyFuel': "Fuel purchases are not restored on this server.",
    'FarmService.buyTurboChargers': "Turbo charger purchases are not restored on this server.",
    'ResourceEquipmentWorldService.onUseEquipment': "Resource harvesting by vehicle is not restored on this server.",
    'UserService.toggleWither': "Decoration withering is not restored on this server.",
    'NeighborActionService.depositAnimalFeed': "Neighbour animal feed deposits are not restored on this server.",
    'UserService.buyItemPutGiftbox': "Gift-box purchases are not restored on this server.",
    'FlowerShackService.onNutureAll': "Flower Shack nurturing is not restored on this server.",
    'FlowerShackService.onBuyWorldCurrency': "Flower Shack currency purchases are not restored on this server.",
}

# performAction names that have their own branch above (or the explicit rejection
# in UNRESTORED_WORLD_ACTIONS). Any other name falls through with no save change
# and is still acknowledged to the client, so it is logged for triage (see
# macOS/Documentation/CLIENT_ACTION_AUDIT.md).
HANDLED_WORLD_ACTIONS = frozenset({
    'plow', 'place', 'harvest', 'move', 'clear', 'clearWithered', 'sell', 'store',
    'use', 'neighborAct', 'getStorageInfo', 'TransformBuilding', 'RemoveAltGraphic', 'setFeaturedItem'}
    | set(UNRESTORED_WORLD_ACTIONS))


def log_unhandled_world_action(action_name, m_save) -> None:
    """Record an acknowledged performAction that changed nothing on the server."""
    import bundle
    snapshot = m_save if isinstance(m_save, dict) else {}
    entry = {"timestamp": timestamp_now(),
             "functionName": f"WorldService.performAction/{action_name}",
             "params": {"className": snapshot.get("className"), "itemName": snapshot.get("itemName"),
                        "id": snapshot.get("id")}}
    print(f"[!] Unhandled performAction acknowledged without a save change: {action_name}")
    try:
        with open(bundle.UNHANDLED_LOG, 'a') as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError as e:
        print(f"[!] Failed to write to unhandled.log: {e}")


def progression_response(UID: str) -> dict:
    return progression.take_response(session(UID))


def acknowledge_world_score_level_up(UID: str, unit: str) -> None:
    # Player.addWorldScore already ran locally. Trusted quest completion mirrors
    # the score and level rewards; this notification must never grant them again.
    world_scores.acknowledge_level_up(unit)


def increment_daily_counter(UID: str, group, category, action, amount, day) -> None:
    progression.increment_daily_counter(session(UID), group, category, action, amount, day)

# Equipment (tractor / seeder / harvester / combine)

# client ref.: src/Transactions/TEquipmentAction.as (perform/onComplete), src/AvatarMode/AMMultiPlotAction.as
# A vehicle pass is a single call covering every plot it drove over, instead of one
# WorldService.performAction per plot. What arrives per plot is usually *not* a save object: only a plot
# the client had to invent (a brand-new one, still carrying a temporary id) is serialized whole - every
# plot the server already knows about comes as {id, position} and nothing more. So the post-action state
# is rebuilt here off our own stored copy, mirroring what Plot.executePlow()/harvest()/plant() just did
# client-side, and then handed to world_perform_action so a vehicle action costs, pays and records for
# quests exactly like the single-plot one - all of it is applied optimistically client-side before the
# transaction is even queued, so the amounts have to match.
# Fuel is deliberately not spent. The client does spend it: Equipment.getEnergyCost() is a flat 1 per plot and
# HarvestableResource.useEnergy() subtracts it from Global.player.energy on the FUEL source. The client's refills
# are not all mirrored, though. Crafted-good fuel (CraftingUseGoodsWindow -> getFuelRewardForGood) is (crafting._use),
# but FarmService.buyFuel (TBuyFuel adds xml.count * energyMax), gift-box fuel canisters (CFuel.onUse), the avatar
# fuel feed (AMFertilize.update adds m_fuel * ENERGY_PER_FIFTHTANK), reward-point fuel (CraftingManager.performRewardFuel)
# and the power-hour fuel buff
# (BBonusFuelPowerHour.apply) are client-only, so charging the spend would strand the player at zero. The
# single-plot path ignores the energyCost it *is* sent for the same reason.
def equipment_use(UID: str, action: str, plots, item_name: str, metadata: dict):
    save = session(UID)
    world_travel.guard_active_world(save)
    # The bundle is keyed by the plot's index in the vehicle's sweep and only holds the plots the action
    # succeeded on, so the keys can be sparse - sort them back into sweep order, which is the order
    # TEquipmentAction.onComplete walks the response in.
    entries = [plots[key] for key in sorted(plots.keys(), key=int)] if isinstance(plots, dict) else list(plots)

    if action == "combine":
        # client ref.: src/AvatarMode/AMMultiPlotAction.as (multiCombine)
        # The combine runs all three passes over the same plots - harvest, then plow, then plant - and each
        # one overwrites the same bundle entry, so which of them ran on a given plot is not in the payload:
        # it follows from the state the plot was in, the same way the client's own isHarvestable() /
        # isPlowable() / isPlantable() decided it. The response mirrors the three passes, each an array
        # indexed like the bundle with a null for a plot that pass skipped.
        passes = {"harvest": [], "plow": [], "place": []}
        for entry in entries:
            state = (_equipment_plot_object(save, entry) or {}).get("state")
            # A plot the client invented in this pass has no stored copy yet: the plow pass is what created it,
            # so it is charged for the plow like any other plot.
            invented = state is None and "className" in entry
            # A harvest leaves the plot fallow, which is exactly what the plow pass then picks up.
            if state in ("planted", "grown"):
                applies = ("harvest", "plow", "place")
            elif state in ("fallow", "withered"):
                applies = ("plow", "place")
            elif invented:
                # Its serialized state is the final one, so it was planted only if that says so.
                applies = ("plow", "place") if entry.get("state") == "planted" else ("plow",)
            else:
                applies = ("place",)
            for name in passes:
                if name not in applies:
                    passes[name].append(None)
                elif name == "plow" and invented:
                    # Stored as freshly plowed ground first: a plant over an identical stored copy is a retry and
                    # would not be charged, so the plant pass needs the plot to differ from this one.
                    plowed = {**entry, "state": "plowed", "itemName": None, "plantTime": 0,
                              "isJumbo": False, "isBigPlot": False, "isProduceItem": False}
                    passes[name].append(_equipment_apply(UID, name, plowed, item_name))
                else:
                    passes[name].append(_equipment_apply(UID, name, entry, item_name))
        return {name: {"data": [_equipment_envelope(d, metadata) for d in datas]} for name, datas in passes.items()}

    return [_equipment_envelope(_equipment_apply(UID, action, entry, item_name), metadata) for entry in entries]

# client ref.: src/Transactions/TEquipmentAction.as (onComplete), src/Engine/Transactions/Transaction.as (onAmfComplete)
# The client unpacks the response by feeding every element back through its own onAmfComplete, so each
# element has to look like a whole gateway response: one without an errorType is read as an error and
# raises a fault instead. TFarmTransaction.onAmfCompleteSteps carries QuestComponent and ActionDrops
# from the previous rawResult into each child, so an independent empty metadata object is enough.
def _equipment_envelope(data: dict, metadata: dict) -> dict:
    if data is None:
        return None
    # Sharing the outer metadata emits AMF0 References, which the shipped Ruffle
    # maps to Undefined. A new empty object lets the client's existing callback
    # carry the late quest metadata without copying a whole quest list per plot.
    # https://github.com/ruffle-rs/ruffle/blob/v0.7.1/core/src/avm2/amf.rs#L469-L474
    response = {"errorType": 0, "errorData": None, "metadata": {}, "data": data}
    response.update(data.pop("_progressionResponse", {}))
    return response

def _equipment_plot_object(save: dict, entry: dict) -> dict:
    world_objects = save["world"]["objectsArray"]
    stored = engine.get_world_object_by_id(world_objects, entry["id"])
    if stored is None and engine.world_object_id_is_temporary(entry["id"]):
        # A plot created earlier in this same session whose real id the client has not been told yet, so
        # it is still calling it by the temporary one world_perform_action kept alongside.
        stored = next((obj for obj in world_objects if obj.get("tempId") == entry["id"]), None)
    return stored

def _equipment_apply(UID: str, action: str, entry: dict, item_name: str) -> dict:
    save = session(UID)
    world_travel.guard_active_world(save)

    if action == "plotRemove":
        # client ref.: src/Classes/Plot.as (remove)
        # The plot is deleted outright, for a plow's coin cost and no XP. Keep the
        # vehicle result shape while matching the single-plot clear action.
        world_travel.guard_world_context(save, entry, [])
        world_travel.guard_action_object(save, entry["id"])
        stored = _equipment_plot_object(save, entry)
        if stored is None:
            print(" * Equipment 'plotRemove' on unknown plot {}: skipped.".format(entry.get("id")))
            return None
        if stored.get("className") != "Plot":
            raise ValueError("Plot removal requires an owned ordinary plot.")
        _guard_object_deletion(stored)
        creative_worlds.guard_action(save, "clear", stored, [], neighbor_count=len(neighbor_uids(UID)))
        cost = get_farming_int("plowCost", 15)
        balance = save["userInfo"]["player"]["gold"]
        if type(balance) not in (int, float) or not math.isfinite(balance) or balance < cost:
            raise ValueError("Not enough coins to remove this plot.")
        engine.world_remove_object(save["world"]["objectsArray"], stored["id"])
        _forget_building_contents(save, stored["id"])
        engine.apply_coins_diff(save, -cost)
        progression.record_coins(save, spent=cost)
        return {"id": stored["id"], "_progressionResponse": progression.take_response(save)}

    if "className" in entry:
        # The brand-new plot case: the client serialized it whole, already in its post-action state
        # (getSaveObject() is taken after Plot.plow() ran), so it goes through as it arrived.
        m_save = entry
    else:
        stored = _equipment_plot_object(save, entry)
        if stored is None:
            print(" * Equipment '{}' on unknown plot {}: skipped.".format(action, entry.get("id")))
            return None
        m_save = dict(stored)
        if action == "plow":
            # client ref.: src/Classes/Plot.as (executePlow)
            m_save.update({"state": "plowed", "isJumbo": False, "isBigPlot": False, "isProduceItem": False})
        elif action == "place":
            # client ref.: src/Classes/Plot.as (plant -> initPlantTime)
            # Global.worldTime is our own worldTime in milliseconds (WorldManager.syncWorldTime), so "now"
            # is the plant time the client just wrote. initPlantTime's head start for an active harvest
            # helper is not reproduced - bushels are not modelled server-side - so a crop planted under one
            # grows from scratch again after a reload.
            m_save.update({"itemName": item_name, "state": "planted", "plantTime": timestamp_now() * 1000})
        elif action == "harvest":
            # client ref.: src/Classes/Plot.as (harvest, doHarvestDropOff)
            # isBigPlot/isJumbo stay on the snapshot on purpose: world_perform_action reads the harvest XP
            # off them, exactly as it does from THarvest's pre-harvest snapshot on the single-plot path.
            m_save.update({"state": "fallow", "plantTime": 0})

    object_id = world_perform_action(UID, action, m_save, [])
    # TFarmTransaction carries the outer ActionDrops across every mini result.
    # Keep bushel awards pending for one aggregate outer response/event.
    return {"id": object_id, "_progressionResponse": progression.take_response(save)}

# Neighbours

# client ref.: src/Classes/NeighborActions/*NeighborAction.as (getExecuteXpYield/getExecuteCoinYield)
# What the visitor earns for helping out, as (xpKey, xpDefault, goldKey, goldDefault) into the farming
# settings. BaseNeighborAction.execute() adds these to Global.player client-side before the transaction is
# even queued, so the server has to apply exactly the same amounts or the HUD drifts from the save. The
# seasonal actions (trickneighbor, the Halloween pair, neighborHarvestFeatureBuilding) never override the
# base class' yields, so they are deliberately absent here: they really do pay out nothing directly.
_NEIGHBOR_ACTION_YIELDS = {
    "plow":         ("neighborPlowBonusXp", 1, "neighborPlowBonusGold", 10),
    "harvest":      ("neighborPlowBonusXp", 1, "neighborPlowBonusGold", 10),
    "fert":         ("fertilizeSuccessXpGain", 0, "fertilizeSuccessCoinGain", 10),
    "unwither":     ("unwitherXpReward", 1, "unwitherGoldReward", 10),
    "feedchickens": ("feedAnimalSuccessXpGain", 1, "feedAnimalSuccessCoinGain", 10),
}

def neighbor_act(UID: str, host_id: str, action_type: str, m_save: dict) -> None:
    save = session(UID)
    world_travel.guard_active_world(save)
    host_id = str(host_id)

    host_village = village(host_id)
    if host_id == UID or host_village is None:
        raise ValueError("That neighbour is unavailable.")
    original = engine.get_world_object_by_id(world_travel.home_world(host_village)["objectsArray"], m_save["id"])
    if original is None:
        raise ValueError("That neighbour's farm object is unavailable.")
    m_save = {**original, **m_save}

    # The worked object arrives already in its post-action state - the client mutates the plot
    # (Plot.executePlow(), executeFertilize(), ...) and only then constructs the transaction off it - so the
    # host's world can take it as-is, the same way the player's own 'plow'/'harvest' branches do above.
    host = session(host_id)
    if host is None:
        # Static villages under /villages are templates loaded read-only, so helping one shows up for the
        # duration of the visit but is not written back to disk.
        print(f" * Neighbor action '{action_type}' on read-only village {host_id}: not persisted.")
    else:
        engine.world_update_or_add_object(world_travel.home_world(host)["objectsArray"], m_save)
        save_session(host_id)

    import progression
    progression.record_help(save, action_type)

    # Reward the visitor, mirroring BaseNeighborAction.execute()'s optimistic client-side update.
    if action_type in _NEIGHBOR_ACTION_YIELDS:
        xp_key, xp_default, gold_key, gold_default = _NEIGHBOR_ACTION_YIELDS[action_type]
        engine.apply_xp_increment(save, get_farming_int(xp_key, xp_default))
        engine.apply_coins_diff(save, get_farming_int(gold_key, gold_default))
    return

def load_own_world(UID: str, world_type: str, should_create=False, should_freeze=False,
                   next_season_unlock=False) -> dict:
    # client ref.: src/Transactions/TWorldLoad.as, src/Transactions/TBaseWorldLoad.as (onComplete),
    # src/Init/Worlds/HomeWorldInit.as (resyncToBackendData)
    # An empty worldType means home. Unsupported destinations fail explicitly;
    # silently substituting home could apply subsequent commands to the wrong farm.
    save = session(UID)
    world_travel.switch(save, world_type, should_create, should_freeze,
                        next_season_unlock, now=timestamp_now())
    storage.normalize_empty_building_contents(save)
    pets.refresh_world(save, now=timestamp_now())
    breeding.normalize_legacy_dna(save)
    crafting.initialize(save)
    peaceful.refresh(save)
    return {
        "user": {
            "currentWorldType": save["userInfo"]["currentWorldType"],
            "unlockedWorldTypes": save["userInfo"].get("unlockedWorldTypes", ["farm"]),
            # HomeWorldInit.resyncToBackendData reloads storage/inventory/crafting off user.player here, so
            # anything picked up while away (helping rewards, goodie bags) is in place on arrival.
            "player": save["userInfo"]["player"],
            "ugcItemData": save["userInfo"].get("ugcItemData"),
            "worldSummaryData": save["userInfo"].get("worldSummaryData"),
        },
        "world": save["world"],
        "craftingState": save.get("craftingState"),
    }

def get_gifts(UID: str) -> dict:
    # client ref.: src/Transactions/TRefreshGifts.as (onComplete -> Player.refreshGiftBox)
    # TWorldLoad.onComplete queues this unconditionally, so it follows every single world load.
    return {"storageData": session(UID)["userInfo"]["player"]["storageData"]}

def load_neighbor_world(UID: str, neighbor_id: str) -> dict:
    # client ref.: src/Transactions/TLoadNeighbor.as, src/Transactions/TBaseWorldLoad.as (onComplete),
    # src/Init/Worlds/VisitWorldInit.as (onEnterWorld -> VisitorManager.initForVisit)
    neighbor = village(str(neighbor_id))
    if neighbor is None:
        return {"isNeighborMissing": True}
    if str(neighbor_id) != UID and str(neighbor_id) in neighbor_uids(UID):
        # A successful visit is the original quest event. The owned world's
        # context remains England while the detached neighbour is displayed.
        quests.record_action(session(UID), "visitNeighbor")
    import copy
    neighbor = copy.deepcopy(neighbor)
    neighbor["world"] = world_travel.home_world(neighbor)
    neighbor["userInfo"]["currentWorldType"] = "farm"
    # This is a detached visit response, not an owned-world switch.
    neighbor.pop(world_travel.STATE_KEY, None)
    peaceful.refresh(neighbor)
    return {
        # client ref.: src/Transactions/TFarmTransaction.as (updateWorldTimeFromServer)
        # While visiting, the client ignores the envelope's top-level worldTime and syncs off
        # data.neighborWorldTime instead, so without this the world clock never resyncs during a visit.
        "neighborWorldTime": timestamp_now(),
        "user": {
            # `id` is filled in client-side from the uid that was visited; firstName titles the farm.
            "currentWorldType": "farm",
            "firstName": neighbor["userInfo"].get("attr", {}).get("name", "Farmer"),
            "avatar": neighbor["userInfo"].get("avatar"),
            # client ref.: src/Managers/NeighborUnwitherManager.as (offerFullFarmUnwither)
            # When the host's farm has withered plots, the visitor is offered a free full-farm unwither
            # if the host has been away for "unwitherNeighborFarmForFreeIfInactiveDays" days. That is
            # measured against this timestamp; missing, it reads as NaN -> 0 days and the offer never
            # shows. The last time the host loaded their farm is the closest thing a save records.
            "lastWorldAction": neighbor["userInfo"].get("worldSummaryData", {}).get("farm", {}).get("lastLoaded", 0),
            "ugcItemData": neighbor["userInfo"].get("ugcItemData"),
            "instanceDataStore": None,
        },
        "world": neighbor["world"],
        # Crafting crews are not implemented; an empty crew just means "you are not a member of theirs".
        "neighborCraftingCrew": [],
    }

# client ref.: src/Transactions/TResetSystemNotifications.as,
# src/Managers/SystemNotificationManager.as (displayPendingNotifications/resetNotifications)
# The client sends this once it has actually shown the notifications initUser handed it, so they must
# not come back on the next login. Both lists are read straight off initUser's top level
# (TInitUser.onComplete), and "nothing pending" there is null - an empty list is still truthy in AS3,
# which would make the manager load and re-arm m_needReset every session.
def reset_system_notifications(UID: str) -> None:
    save = session(UID)
    save["systemNotifications"] = None
    save["dynamicSystemNotifications"] = None
    return

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

# client ref.: xml/gz/v855098/postInitSequence.xml (the forceGrant* userActions), src/Managers/PostInitSettings.as
# Every limited-time event (the *InnovationService family, GiftRush2019, BoatRush2020...) ended before the
# shutdown, and postInitSequence fires its end-of-event payout on every login while a feature option is 0.
# A missing option counts as 0 (PrerequisiteUtility.isPrerequisiteMet_FeatureOption) and nothing client-side
# ever persists one (FeatureOptionsManager.setFeatureOption is session-only, even for the forceGrantedLB the
# managers set themselves), so the original server must have set it once the payout ran. This maps
# (featureName, the call each forceGrant* action ends up sending) to the option that gates it.
_FEATURE_END_GRANT_FLAGS = {
    ("Halloween2019Innovation", "featureEnd"): "forceGranted",
    ("CanadaInnovation", "featureEnd"): "forceGranted",
    ("BoraBoraInnovation", "featureEnd"): "forceGranted",
    ("BoraBoraInnovation", "onRedeemStarted"): "forceGrantedLB",
    ("FarmersMarket2020Innovation", "featureEnd"): "farmersMarket_bonus_reward_granted",
    ("FarmersMarket2020Innovation", "onRedeemStarted"): "forceGrantedLB",
    ("TropicalMarketInnovation", "featureEnd"): "tropical_market_bonus_reward_granted",
    ("TropicalMarketInnovation", "onRedeemStarted"): "forceGrantedLB",
    ("GiftRush2019", "featureEnd"): "forceGranted",
    ("BoatRush2020", "featureEnd"): "forceGranted",
    ("RussiaInnovation", "grantBonus"): "forceGranted",
    ("IsraelInnovation", "grantBonus"): "forceGranted",
    ("SouthindiaInnovation", "grantBonus"): "forceGranted",
    ("Dec19Innovation", "grantBonus"): "forceGranted",
    ("AmsterdamInnovation", "grantBonus"): "forceGranted",
    ("WreathFestivalInnovation", "grantBonus"): "forceGranted",
    ("IrelandInnovation", "onRedeemStarted"): "xid_bonus",
    ("WinternordInnovation", "onRedeemStarted"): "forceGrantedWeekly",
    ("MadagascarInnovation", "onRedeemStarted"): "forceGrantedWeekly",
    ("TwentiesInnovation", "onRedeemStarted"): "forceGrantedWeekly",
    ("PumpkinPartyInnovation", "onRedeemStarted"): "forceGrantedWeekly",
}

_FEATURE_END_SERVICES = ("WinterRacingFeatureService", "BoatRushService", "AnimalSanctuaryV2Service")
_FEATURE_END_METHODS = ("startQuest", "featureEnd", "grantBonus", "onRedeemStarted", "fetchDailyLimit",
                        "getLeaderboardEntries", "updateEscapeTokensCount", "initializeTropicEscapeConnection")

def is_feature_end_call(function_name: str) -> bool:
    service, _, method = function_name.partition(".")
    return (service.endswith("InnovationService") or service in _FEATURE_END_SERVICES) and method in _FEATURE_END_METHODS

# client ref.: src/Transactions/TGenericTransaction.as, src/Managers/OrderBoard/*InnovationManager.as, src/Managers/*InnovationManager.as
# The end-of-event calls those payouts (and the managers' own start-up) send, all with params[0] = featureName.
# The response stays empty: every callback treats a null result as "nothing happened" (no board tasks, no
# leaderboard, no reward). Rewards that do exist are granted client-side from the event's points
# (onBonusGrantComplete), which nothing ever earned here, so there is nothing for the server to mirror.
def feature_end_call(UID: str, method: str, feature_name: str) -> None:
    option_name = _FEATURE_END_GRANT_FLAGS.get((feature_name, method))
    if option_name:
        save = session(UID)
        save["userInfo"]["featureOptions"].setdefault(feature_name, {})[option_name] = 1

def slot_spin(UID: str, request_id=None) -> dict:
    return minigames.dispatch(session(UID), "SlotService.spin", [], request_id=request_id)

# client ref.: src/Transactions/TGetMOTD.as (perform, onComplete)
# client ref.: src/Display/MOTD.as (MOTD constructor - reads icon, text, dialog, title, buttonText, etc.)
def get_motd(UID: str, motd_seen_flag: str) -> dict:
    save = session(UID)

    # Track which MOTDs the player has seen in their save
    if "motdSeenFlags" not in save:
        save["motdSeenFlags"] = {}

    # Record that this MOTD was seen
    save["motdSeenFlags"][motd_seen_flag] = timestamp_now()

    # ItemMembershipManager.onGetMOTD (original client lines 1129-1136) reads
    # motdSeenFlag without checking for null, aborting AMF batch completion. An
    # empty object is safe to read and leaves its pending flag string unchanged;
    # conditionallyOnboard (991-995) requires a non-String object to show a MOTD.
    # Do not supply a matching flag without the unrecovered campaign body.
    if motd_seen_flag in (
        "MOTD_ITEM_MEMBERSHIP_TREES_2013",
        "MOTD_ITEM_MEMBERSHIP_HORSES_2013",
    ):
        return {"motdData": {}}

    # Other callers handle null to detach unavailable campaigns. Supplying a
    # fabricated body instead can display an untranslated default popup.
    return {"motdData": None}

def scratch_card_get_data(UID: str, unlock: bool, request_id=None) -> dict:
    return minigames.dispatch(session(UID), "ScratchCardService.getScratchCardData", [unlock], request_id=request_id)


def pigo_get_game_settings(UID: str, game_token_name: str, request_id=None) -> list:
    return minigames.dispatch(session(UID), "PigoService.getGameSettings", [game_token_name], request_id=request_id)


def pigo_buy_token(UID: str, game_token_name: str, request_id=None) -> str:
    return minigames.dispatch(session(UID), "PigoService.buyToken", [game_token_name], request_id=request_id)


def pigo_buy_token_package(UID: str, game_token_name: str, request_id=None) -> str:
    return minigames.dispatch(session(UID), "PigoService.buyTokenPackage", [game_token_name], request_id=request_id)


def pigo_grant_reward(UID: str, game_token_name: str, item_name: str, request_id=None) -> dict:
    return minigames.dispatch(session(UID), "PigoService.grantReward", [game_token_name, item_name], request_id=request_id)

# Farm expansion

# client ref.: src/Classes/ZItem/ChangeFarmItem.as (get saleCash)
# For an expand_farm item saleCash is hard-coded to 1, and TExpandFarm.onComplete subtracts
# realCashCost (which is saleCash), so in the recovered build a Farm Cash expansion really does cost
# 1 FC whatever items_opt.amf's `cash` says. The server has to charge the same amount the client
# already took off the HUD, so it mirrors the constant rather than the item's price.
EXPAND_FARM_CASH_COST = 1

# These are the land-expansion variants served by both original client pages.
# Unknown and disabled gates (including the 60x60 England cash offer) stay shut.
_LAND_EXPANSION_EXPERIMENTS = {
    "fv_britishinvasion", "fv_expansion_30x30", "fv_expansion_farm_32x32",
    "fv_expansion_xuk_32x32", "fv_expansion_home_34x34", "fv_england_farm32",
    *(f"fv_home_{size}coin" for size in (30, 32, 34, 36, 38)),
    *(f"fv_expansion_farm_{size}x{size}" for size in (36, 38, 40)),
    *(f"fv_expansion_farm_{size}" for size in range(42, 61, 2)),
    *(f"fv_england_{size}coin" for size in (34, 36, 38)),
    *(f"fv_expansion_EC_{size}x{size}" for size in (34, 36, 38, 40)),
    *(f"fv_expansion_ec_{size}" for size in range(42, 51, 2)),
    *(f"fv_expansion_ec_lc_hi_jf_{size}" for size in range(52, 59, 2)),
}

# client ref.: src/Transactions/TExpandFarm.as, src/Classes/ZItem/ChangeFarmItem.as (onBuy),
# src/Classes/ExpansionAreaMapTrigger.as (onWindowClose)
# Land expansions are ordinary market items (type change_farm / subtype expand_farm, market category
# landExpansion/expansion) whose `squares` attribute *is* the new world grid size - the whole farm is
# reloaded at that size. Which one the player may buy next is decided client-side in onBuy() by walking
# the expansion list sorted by squares and requiring the bought item to be the one right after the
# current grid size, so the server only has to honour the request and keep the save in step.
# Like neighborAct and quest rewards this is an optimistic action: onComplete already subtracted the
# price from Global.player before reading the response, so the server must apply exactly the same
# amount or the HUD drifts from the save.
def expand_farm(UID: str, item_name: str, currency_unit: str) -> dict:
    save = session(UID)
    world_travel.guard_active_world(save)
    world = save["world"]
    item = get_item_by_name(item_name)

    if creative_worlds.expand_farm(save, item, currency_unit,
                                  neighbor_count=len(neighbor_uids(UID))):
        return save["world"]

    world_type = save["userInfo"].get("currentWorldType") or "farm"
    prefix = {"farm": "farm", "england": "xukfarm"}.get(world_type)
    if (item is None or item.get("subtype") != "expand_farm" or not item.get("squares")
            or not prefix or not item_name.startswith(prefix)
            or not creative_worlds.world_requirement_matches(item, world_type)):
        raise ValueError("This expansion does not belong to the current farm.")

    squares = int(item["squares"])
    current = int(world["sizeX"])
    if squares == current == int(world["sizeY"]):
        return world
    from items import get_items
    from game_settings import xp_to_level
    sizes = sorted({int(entry["squares"]) for entry in get_items()
                    if entry.get("name", "").startswith(prefix)
                    and entry.get("subtype") == "expand_farm"
                    and creative_worlds.world_requirement_matches(entry, world_type)})
    if squares != next((size for size in sizes if size > current), None) or world["sizeY"] != current:
        raise ValueError("Buy this farm's land expansions in their original order.")
    if (any(entry.get("className") not in (None, "World")
            for entry in creative_worlds._nodes(item.get("requirements")))
            or any(item.get(key) for key in ("purchasePrereqs", "prereqs", "requiredMastery",
                "requiredQuest", "license", "marketPrereqs", "limitedStart", "limitedEnd", "gateCode", "experiment"))
            or item.get("unlock") not in (None, "", "neighbor")):
        raise ValueError("This expansion's additional unlock requirements are not restored.")
    gate = item.get("experimentGate")
    if gate and (gate not in _LAND_EXPANSION_EXPERIMENTS or item.get("experimentVariant", "1") not in (1, "1")):
        raise ValueError("This land expansion's experiment is not enabled.")
    if item.get("buyable") in (False, "false"):
        raise ValueError("This land expansion is not available for purchase.")
    if (xp_to_level(save["userInfo"]["player"]["xp"]) or 0) < int(item.get("requiredLevel") or 1):
        raise ValueError("The player's level is too low for this expansion.")
    if len(neighbor_uids(UID)) < int(item.get("minNeighbors") or 0):
        raise ValueError("This land expansion requires more neighbors.")
    currency_unit = creative_worlds._purchase_currency(item, currency_unit)
    cost = (EXPAND_FARM_CASH_COST if currency_unit == "cash"
            else engine.catalog_price(item, "cost"))
    if cost is None or cost < 0:
        raise ValueError("This land expansion's recovered price is unavailable.")
    balance_key = "cash" if currency_unit == "cash" else "gold"
    player = save["userInfo"]["player"]
    balance = player[balance_key]
    if type(balance) not in (int, float) or not math.isfinite(balance) or balance < cost:
        raise ValueError("Not enough currency for this land expansion.")
    player[balance_key] -= cost

    world["sizeX"] = squares
    world["sizeY"] = squares
    quests.record_action(save, "expandFarm", item_name)

    # The response is fed straight to FarmGameWorld.loadObject(), which reloads the farm from
    # objectsArray at the new size - so it is the world payload itself, not a wrapper around it.
    return world

# client ref.: src/Display/ExpandFarm.as (onCloseClick)
# How many times the "you can expand your farm" nag dialog has been dismissed. Nothing in the recovered
# client ever reads it back (the dialog is only constructed with a hard-coded 0), but it is player state
# the original server kept, so it is stored rather than dropped.
def set_seen_expand_farm(UID: str, amount: int) -> None:
    session(UID)["userInfo"]["player"]["seenExpandFarm"] = int(amount)
    return

# client ref.: src/Transactions/TGrantEmailPermission.as, src/Managers/EmailManager.as (parseEmailBits)
# Older clients may still auto-accept as EMAIL_PROACTIVE_USER (source "6").
# init_user now marks the retired promotion consumed in its response, and this
# handler retains the original acknowledgement for already-running clients.
# The gift itself (`giftName`) was never recovered, so none is granted: without `receivedEmailGift`
# onComplete adds nothing.
def grant_email_permission(UID: str) -> dict:
    session(UID)["userInfo"]["player"]["hasReceivedGiftForEmailPermissions"] = 1
    return {}

# client ref.: src/Transactions/TBuyConsumables.as
# The pkg_consume_irrigation_water_* offers take this generic route: cash is charged and the package's
# consume_irrigation_water_* gift is deposited, which consume_by_name unpacks into 3YG water gifts.
def buy_consumable_package(UID: str, package_name: str, request_id=None, sequence_id=None) -> dict:
    save = session(UID)
    world_travel.guard_active_world(save)
    if package_name == england_shipping.PACKAGE:
        return england_shipping.buy_package(save, package_name, request_id=request_id)
    import meadows_storage
    licensed = meadows_storage.buy_license_package(save, package_name, request_id=(sequence_id, request_id) if sequence_id is not None else request_id)
    if licensed is not None:
        return licensed
    if package_name == cove_shipping.PACKAGE:
        return cove_shipping.buy(save, request_id=request_id)
    if package_name in pets.FOOD_PACKAGES:
        return pets.buy_food_package(save, package_name, request_id=request_id)
    print(f"[BUY_PKG] package={package_name}")
    package_item = get_item_by_name(package_name)
    print(f"[BUY_PKG] * cost={package_item.get('cash')} cash")
    engine.apply_item_cost(save, package_item, currency="cash")

    # Extract items from the package and give them to the player
    if "itemPackage" in package_item:
        print(f"[BUY_PKG] Found itemPackage: {package_item['itemPackage']}")
        package_contents = package_item["itemPackage"]

        # itemPackage can be a dict (single item) or list (multiple items)
        if isinstance(package_contents, dict):
            package_contents = [package_contents]

        if isinstance(package_contents, list):
            for item_spec in package_contents:
                item_name = item_spec.get("value")
                amount = int(item_spec.get("amount", 1))

                print(f"[BUY_PKG] Deposit {amount}x {item_name} to GiftBox")
                storage.store_deposit_item_by_name(save, item_name, amount, group=storage.GIFTBOX_ID)
        else:
            print(f"[BUY_PKG] ERROR: itemPackage is not a list after conversion")
    else:
        print(f"[BUY_PKG] ERROR: No itemPackage field in package item")

    return {}

# Irrigation (watering)

WATER_PLOTS_ACTION = "waterPlots"
# client ref.: src/Managers/IrrigationManager.as (getMaxWaterForActionType)
IRRIGATION_WATER_CAP = 2000
# client ref.: src/Managers/IrrigationManager.as (consumeWaterPackages)
IRRIGATION_WATER_GIFT_CODE = "3YG"
# client ref.: src/Classes/HarvestableResource.as (waterHarvestableResource: f = 0.5; IRRIGATION_MINUTES_TO_INSTAGROW = 15)
PLOT_WATER_FRACTION = 0.5
IRRIGATION_MINUTES_TO_INSTAGROW = 15
# client ref.: src/Managers/SuperPlotManager.as (SUPER_PLOT_MULTIPLIER = 5)
SUPER_PLOT_WATER_MULTIPLIER = 5

def _whole_positive(value, message: str) -> int:
    if type(value) not in (int, float) or not math.isfinite(value) or int(value) != value or value <= 0:
        raise ValueError(message)
    return int(value)

def _gift_count_by_code(save: dict, code: str) -> int:
    entry = save["userInfo"]["player"]["storageData"].get(str(storage.GIFTBOX_ID), {}).get(code)
    return entry[storage.METADATA_INDEX_QUANTITY] if entry else 0

# client ref.: src/Managers/IrrigationManager.as (consumeWaterPackages), src/Widgets/Slots/GiftBox/GiftBoxSlot.as
# (useMultiWater, onUseClick). The client adds the water and removes the 3YG gifts before this call is queued, so
# the server checks everything first and only then moves the gifts and the water together.
def consume_water_packages(UID: str, action_type: str, amount: int) -> dict:
    save = session(UID)
    world_travel.guard_active_world(save)
    if action_type != WATER_PLOTS_ACTION:
        raise ValueError("Only irrigation water for crops is restored on this server.")
    amount = _whole_positive(amount, "Choose how much irrigation water to use.")
    # The gift box only spends irrigation water on the home farm (GiftBoxSlot.onUseClick).
    if (save["userInfo"].get("currentWorldType") or "farm") != "farm":
        raise ValueError("Irrigation water can only be used on the home farm.")
    if not engine.has_water_store(save, action_type):
        raise ValueError("Irrigation water is not available on this farm.")
    if engine.get_water_amount(save, action_type) + amount > IRRIGATION_WATER_CAP:
        raise ValueError("That would go over the irrigation water limit.")
    if _gift_count_by_code(save, IRRIGATION_WATER_GIFT_CODE) < amount:
        raise ValueError("There are not enough irrigation water packages to use.")
    if not storage.remove_gift_by_code(save, IRRIGATION_WATER_GIFT_CODE, amount):
        raise ValueError("There are not enough irrigation water packages to use.")
    engine.add_water(save, action_type, amount)
    return {}

def _superplots_experiment_served() -> bool:
    # client ref.: src/Managers/SuperPlotManager.as (isFeatureEnabled: EXPERIMENT_SUPERPLOTS variant 2). This
    # server serves no experiment variants, so the super-plot water multiplier never applies.
    return False

def _water_cost_of_plot(stored: dict) -> int:
    # client ref.: src/Managers/SuperPlotManager.as (getMultiplier, isSuperPlot)
    if _superplots_experiment_served() and stored.get("isSuperPlot"):
        return SUPER_PLOT_WATER_MULTIPLIER
    return 1

def _plant_time_after_watering(plant_time: float, grow_ms: float, now_ms: float) -> float:
    # client ref.: src/Classes/HarvestableResource.as (waterHarvestableResource, setFullGrown)
    # The remaining grow time (ms) is halved. When the half is no more than IRRIGATION_MINUTES_TO_INSTAGROW
    # the crop is simply ripe, as setFullGrown() leaves it: plantTime = worldTime - growMs.
    remaining = grow_ms - (now_ms - plant_time)
    reduction = remaining * PLOT_WATER_FRACTION
    if reduction > IRRIGATION_MINUTES_TO_INSTAGROW * 60000:
        return now_ms - grow_ms + reduction
    return now_ms - grow_ms

# client ref.: src/Transactions/TIrrigationAction.as, src/AvatarMode/AMIrrigationSprinkler.as (executeServiceCall),
# src/GameMode/GMIrrigationSprinkler.as (handleClick: getWaterCost, useWater)
# The client charges the sum of the selected plots' costs and moves each plot's plant time before this call is
# queued. The server charges the same cost from its ledger and applies the same plant-time change to its own
# copy, refusing the whole pass if any plot is not a planted crop on this farm or the water does not cover it.
def irrigation_action(UID: str, action: str, action_items, now: int = None) -> dict:
    save = session(UID)
    world_travel.guard_active_world(save)
    if action != WATER_PLOTS_ACTION:
        raise ValueError("Only crop watering is restored on this server.")
    if not isinstance(action_items, list) or not action_items:
        raise ValueError("Choose at least one crop to water.")
    ids = []
    for entry in action_items:
        object_id = entry.get("id") if isinstance(entry, dict) else None
        if (type(object_id) not in (int, float) or not math.isfinite(object_id)
                or int(object_id) != object_id or int(object_id) in ids):
            raise ValueError("Each crop to water needs its own id.")
        ids.append(int(object_id))

    now_ms = (timestamp_now() if now is None else now) * 1000
    world_objects = save["world"]["objectsArray"]
    plots = []
    cost = 0
    for object_id in ids:
        stored = engine.get_world_object_by_id(world_objects, object_id)
        if stored is None or stored.get("className") != "Plot" or stored.get("deleted"):
            raise ValueError("That crop is not on this farm.")
        if stored.get("state") != "planted":
            raise ValueError("Only planted crops can be watered.")
        world_travel.guard_action_object(save, object_id)
        grow_seconds = peaceful.grow_seconds(get_item_by_name(stored.get("itemName")) or {})
        planted = stored.get("plantTime")
        if grow_seconds is None or type(planted) not in (int, float) or not math.isfinite(planted):
            raise ValueError("This crop cannot be watered.")
        cost += _water_cost_of_plot(stored)
        plots.append((stored, planted, grow_seconds * 1000))

    engine.use_water(save, WATER_PLOTS_ACTION, cost)
    for stored, planted, grow_ms in plots:
        stored["plantTime"] = math.floor(_plant_time_after_watering(planted, grow_ms, now_ms))
    return {}

# Quests

# client ref.: src/ZQuest/Managers/QuestManager.as (onTransactionComplete),
# src/Classes/Quest/FarmQuestManager.as (handleWorldLoadQuestRefresh)
# metadata.QuestComponent for one gateway response. Legacy global quests are the exception: with client
# prediction on (it always is - FarmQuestComponent always passes a questUtility) the client keeps its own
# task progress and ignores ours everywhere except there, where handleWorldLoadQuestRefresh overwrites the
# active quest with whatever the server sent. The server only recounts part of the task actions
# (quests.record_action), so sending the list there would walk a session's progress backwards on the way
# home from a neighbour's farm. An empty Array is still truthy in AS3, so the client just finds nothing to
# apply. Explicitly world-bound quests need refreshed progress and removal
# tombstones when travelling. Keep global client-only counters untouched.
_QUEST_COMPONENT_SKIPPED_COMMANDS = ("WorldService.loadNeighborWorld",)

def quest_component(UID: str, function_name: str) -> list:
    save = session(UID)
    if save is None or function_name in _QUEST_COMPONENT_SKIPPED_COMMANDS:
        return []
    records = quests.quest_component(save, include_removed=function_name == "WorldService.loadOwnWorld")
    if function_name == "WorldService.loadOwnWorld":
        records = [record for record in records
                   if record.get("removed") or _world_bound_quest(record["name"])]
    return records


def _world_bound_quest(name):
    definition = quests.get_quest_by_name(name) or {}
    return bool(definition.get("restoredWorld") or any(
        requirement.get("type") == "location" for requirement in definition.get("prereqs", [])))

# client ref.: src/Transactions/Quests/TFullQuestRefresh.as
def full_quest_refresh(UID: str) -> None:
    quests.refresh_active_quests(session(UID))

# client ref.: src/Transactions/TMarkQuestAsViewed.as
def interacted_with_quest(UID: str, quest_name: str) -> None:
    quests.interacted_with_quest(session(UID), quest_name)

# client ref.: src/Transactions/Quests/TShareQuestLoot.as
def update_recently_completed_quests(UID: str, quest_name: str, should_generate_friend_reward: bool) -> dict:
    return quests.update_recently_completed_quests(session(UID), quest_name, should_generate_friend_reward)

# client ref.: src/Transactions/Quests/TKillQuest.as, src/Transactions/Quests/TPauseQuest.as
def retire_quest(UID: str, quest_name: str) -> None:
    quests.retire_quest(session(UID), quest_name)

# client ref.: src/Transactions/Quests/TUserTaskSeen.as
def mark_view_dialog_task_done(UID: str, quest_name: str) -> None:
    quests.mark_view_dialog_task_done(session(UID), quest_name)

# AMF numbers arrive as floats, so a whole float names a task too. None, strings, booleans, fractions, NaN and
# negative numbers name no task: quests.skip_task would take a negative index as one counted from the end.
def _task_index(value):
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        value = int(value)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None

# client ref.: src/Transactions/Quests/TSkipQuestTask.as
def skip_quest_task(UID: str, quest_name: str, task_index: int) -> None:
    index = _task_index(task_index)
    if index is None:
        print(" * Skip task on {}: no valid task index in {!r}; nothing skipped.".format(quest_name, task_index))
        return
    quests.skip_task(session(UID), quest_name, index)

# client ref.: src/Classes/Quest/FarmQuest.as (skipQuest)
def skip_entire_quest(UID: str, quest_name: str) -> None:
    quests.skip_entire_quest(session(UID), quest_name)

# client ref.: src/Transactions/Quests/TIncrementGenericFarmTask.as
def increment_generic_farm_task(UID: str, task_action: str) -> None:
    save = session(UID)
    quests.increment_generic_farm_task(save, task_action)
    # QuestMapWindow.close sends this exact original transaction. Viewing a
    # dialog has no independent server action to derive; limit the client
    # acknowledgement to this one visual task, never farming or rewards.
    if (task_action == "viewQuestMap"
            and save["userInfo"].get("currentWorldType") == "england"
            and "england-02-003" in save.get("questState", {}).get("active", {})):
        quests.record_action(save, "simpleAction", "viewQuestMap")

# client ref.: src/Widgets/Windows/QuestManager/QMWReplayableQuestsBaseSlot.as (Start / End buttons)
def start_replayable_quest_chain(UID: str, first_quest_name: str) -> None:
    quests.start_replayable_quest_chain(session(UID), first_quest_name)

def end_replayable_quest_chain(UID: str, quest_name: str) -> None:
    quests.end_replayable_quest_chain(session(UID), quest_name)
