
version_code = "0.01a"
version_name = "alpha " + version_code

def migrate_loaded_save(save: dict):
    
    _changed = False

    # 0.01a saves
    if "version" not in save or save["version"] is None:
        _changed = True
        save["version"] = "0.01a"
        print("[!] Applied version to save")
    
    # 0.01a.2024_05_04 -> 0.01a.2024_09_16
    if save["version"] == "0.01a":
        if save["userInfo"]["player"]["lonelyAnimalCode"] == 0:
            _changed = True
            save["userInfo"]["player"]["lonelyAnimalCode"] = ""
            print("[!] Fixed lonelyAnimalCode format")

        # client ref.: src/Classes/ExtendedPermissionState.as (hasExtendedPermission)
        # Was stored as a list of permission names, but the client indexes it by name.
        if isinstance(save.get("snExtendedPermissions"), list):
            _changed = True
            save["snExtendedPermissions"] = {perm: True for perm in save["snExtendedPermissions"]}
            print("[!] Fixed snExtendedPermissions format")

        # client ref.: src/Classes/MarketConfigSettings.as (getActiveCarnivalPromotions) - without these,
        # the Carnival Booth's promo grid stays empty (Global.flashHotParams["CARNIVAL_PROMOS_ACTIVE"] is NaN).
        if "CARNIVAL_PROMOS_ACTIVE" not in save["flashHotParams"]:
            _changed = True
            save["flashHotParams"]["CARNIVAL_PROMOS_ACTIVE"] = 6
            save["flashHotParams"]["CARNIVAL_PROMO_DEFAULT"] = "Carnival_Coming_Soon"
            print("[!] Added Carnival Booth flashHotParams")

        # client ref.: src/Widgets/Windows/Pigo/PigoWindow.as - per-token, per-prize win counts.
        if "pigoState" not in save:
            _changed = True
            save["pigoState"] = {}
            print("[!] Added pigoState")

        # Migrate motdSeenFlags from int (0) to dict to track MOTD timestamps
        if not isinstance(save.get("motdSeenFlags"), dict):
            _changed = True
            save["motdSeenFlags"] = {}
            print("[!] Fixed motdSeenFlags format")

        # Add currentMOTD needed for MOTD support
        if "currentMOTD" not in save["userInfo"]["player"]:
            _changed = True
            save["userInfo"]["player"]["currentMOTD"] = None
            print("[!] Added currentMOTD")

        # Add irrigation featureOptions
        if "irrigation" not in save["userInfo"]["featureOptions"]:
            _changed = True
            save["userInfo"]["featureOptions"]["irrigation"] = {
                "irrigation": {
                    "waterPlots": {
                        "farm": {
                            "amount": 20
                        }
                    }
                }
            }
            print("[!] Added irrigation featureOptions")

        # client ref.: src/Transactions/TInitUser.as (Global.witherOnObject = result.witherOn),
        # src/Global.as (getCurrentWitherStatus / setCurrentWitherStatus) - it's a map keyed by world
        # type, not a flag. As a Boolean, setCurrentWitherStatus throws #1056 on assignment.
        if not isinstance(save.get("witherOn"), dict):
            _changed = True
            save["witherOn"] = {"farm": bool(save.get("witherOn", True))}
            print("[!] Fixed witherOn format")

        # client ref.: src/Transactions/TInitUser.as (if(result.avatar != null) ... else DoCreateNewAvatar)
        # An empty object is truthy in AS3, so it took the "player already has an avatar" branch and built a
        # blank FarmAvatar({}) instead of running the avatar customization screen. "No avatar yet" is null.
        if save["userInfo"].get("avatar") == {}:
            _changed = True
            save["userInfo"]["avatar"] = None
            print("[!] Fixed empty avatar (blocked avatar creation)")

        # client ref.: src/Classes/Player.as (loadObject)
        # These keys were named after Player's member variables instead of the keys loadObject actually
        # reads off the response, so their values never reached the client. Rename them (and give them the
        # type the client expects - lotteryTickets is read with "as Array", and limitedSaleInfo lands in
        # m_limitedSaleTimers, which getLimitedSaleExpiration dereferences with .hasOwnProperty).
        player = save["userInfo"]["player"]
        _renames = {
            "organicCertificationTotal": ("organicCertificationCount", 0),
            "lastSocialPlumbingActionTime": ("lastSocialPlumbingTime", 0),
            "adoptedAnimals": ("m_adoptedAnimals", {}),
            "limitedSaleExpirations": ("limitedSaleInfo", {}),
            "initialCashPurchaseTransactions": ("numCashTransactions", 0),
            "initialCPATransactions": ("numCPATransactions", 0),
        }
        for old_key, (new_key, default) in _renames.items():
            if old_key in player:
                _changed = True
                value = player.pop(old_key)
                # the old values were all placeholders of the wrong type, so only keep matching ones
                player[new_key] = value if isinstance(value, type(default)) else default
                print(f"[!] Renamed player.{old_key} -> player.{new_key}")

        if not isinstance(player.get("lotteryTickets"), list):
            _changed = True
            player["lotteryTickets"] = []
            print("[!] Fixed lotteryTickets format")

        # client ref.: src/Transactions/TInitUser.as (isAQA / isAKeynoteUser / isEligibleForNoPopup),
        # src/Classes/Player.as (setIsAutomatedQA / setIsKeynoteQA)
        # Zynga-internal QA flags. Either one set to "1" permanently sets Global.suppressAllToasters and
        # postInitActionsManager.dialogSupress - neither is ever reset - which silently drops every toaster
        # and every post-init popup for the whole session. Ordinary players are "0".
        # Note isEligibleForNoPopup is read off the response's *top level*, not userInfo.player, and with a
        # bare truthiness test, so the string "0" would be truthy there - keep it on the player, where the
        # client ignores it, rather than promoting it.
        for _qa_flag in ("isAKeynoteUser", "isAQA", "isEligibleForNoPopup"):
            if player.get(_qa_flag) != "0":
                _changed = True
                player[_qa_flag] = "0"
                print(f"[!] Cleared player.{_qa_flag} (QA flag, suppresses toasters/popups)")

        # client ref.: src/Classes/Player.as (loadStatsFromPlayerObject), src/Display/HUD/StatsDropDown.as
        # The status shelf needs userInfo.player.stats: loadStatsFromPlayerObject returns immediately when
        # it is missing, so every cell (level/ribbons/masteries/medals/collections/buildings) stays empty.
        # It only needs medals.{bronze,silver,gold,total}, collections and buildings - ribbons/masteries are
        # overwritten in place, recounted from player.achievements/player.mastery.
        if not isinstance(player.get("stats"), dict):
            _changed = True
            player["stats"] = {
                "medals": {"bronze": 0, "silver": 0, "gold": 0, "total": 0},
                "collections": 0,
                "buildings": 0,
            }
            print("[!] Added player.stats")

        # client ref.: src/Classes/Mastery.as (currentLevel, MASTERED_LEVEL = 2), src/Classes/Player.as (addMastery)
        # mastery[code] is a 0-based mastery star level (so 1 = the second star) and masteryCounters[code] a
        # harvest count; both only ever move through a transaction response's goals/goalCounters
        # (TFarmTransaction.handleGoalResponse), which the server does not send yet. villages/initial.json
        # used to seed every crop with 1, handing new farms 51 level-2 masteries - an all-ones map is that
        # seed and nothing else, since no server code has ever written to either field.
        for _mastery_key in ("mastery", "masteryCounters"):
            _seeded = player.get(_mastery_key)
            if isinstance(_seeded, dict) and _seeded and set(_seeded.values()) == {1}:
                _changed = True
                player[_mastery_key] = {}
                print(f"[!] Cleared seeded player.{_mastery_key}")

        # client ref.: src/ZQuest/Managers/QuestManager.as, src/Classes/Quest/FarmQuestManager.as
        # Quest state (server/quests.py): which quests the player has been handed and how far each task
        # got, which ones are finished (they unlock their children through the quest_complete prerequisite
        # and become postInit's completedQuests) and which ones the player dismissed. Without it every
        # response's metadata.QuestComponent is empty and no quest ever reaches the HUD.
        if not isinstance(save.get("questState"), dict):
            _changed = True
            save["questState"] = {"active": {}, "completed": [], "retired": [], "replayed": {}}
            print("[!] Added questState")

        # client ref.: src/Classes/Quest/ReplayableFarmQuestData.as - how many times each replayable quest
        # chain has been run, which postInit's completedReplayableQuests is built from.
        if "replayed" not in save["questState"]:
            _changed = True
            save["questState"]["replayed"] = {}
            print("[!] Added questState.replayed")

        # client ref.: src/Transactions/TInitUser.as (systemNotifications/dynamicSystemNotifications),
        # src/Managers/SystemNotificationManager.as (load/displayPendingNotifications/resetNotifications)
        # Both are lists of pending notifications (static ones are localization handles, dynamic ones are
        # ready-made message strings), and "none pending" is null. They were seeded as the Boolean `true`,
        # which is truthy but not iterable: the manager loaded, displayed nothing, armed m_needReset and
        # fired a TResetSystemNotifications on every single login.
        for _notif_key in ("systemNotifications", "dynamicSystemNotifications"):
            if not isinstance(save.get(_notif_key), (list, type(None))):
                _changed = True
                save[_notif_key] = None
                print(f"[!] Cleared non-list save.{_notif_key}")

        # Fix storage format
        # client ref.: src/Classes/Player.as (loadInventoryFromStorageData)
        _fix_storage = False
        storage = save["userInfo"]["player"]["storageData"]
        for sid in storage.keys():
            for itemCode in storage[sid].keys():
                metadata: list = storage[sid][itemCode]
                if len(metadata) != 3:
                    _fix_storage = True
                    storage[sid][itemCode] = [
                        metadata[0] if len(metadata) > 0 else 1,
                        metadata[1] if len(metadata) > 1 else [],
                        metadata[2] if len(metadata) > 2 else [],
                    ]
        if _fix_storage:
            _changed = True
            print("[!] Fixed storage format")

        # save["version"] = "0.02a"
        # _changed = True
        # print("[!] Bump version to save")

    return _changed