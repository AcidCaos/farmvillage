> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../ACCEPTANCE.md), [current world scope](../../../WORLD_READINESS.md) and [the continuation backlog](<../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Feature invitation availability

Updated 2026-10-23. The original client was still advertising archived events
whose full entry, production, social and reward flows have not passed local
acceptance. A feature's building or basic world support does not certify its
marketing invitation. These invitations are now withheld pending acceptance.

`feature_availability.py` generates `FEATURE_FLASHPARAM_HUD_ICON_BLACKLIST` for
both launch templates. The recovered `Display.DynamicIconQueue.checkIconBlacklist`
reads a comma-separated FlashVar; `addIcon` checks the icon name and
`Classes.FeatureMessagingDefinition.addIcon` additionally checks the feature name.
The blacklist contains the 194 names in the archive's
`featureMessagingManagerSettings`, plus the shared `FeatureCrafting` and
`GenericFeatureOfTheWeek` invitation renderers, plus `pearup`. Pear Up calls
`TokenPlayFeatureService.buyToken` and its token/reward economy is not one of
the restored scratch, slot or Pigo paths. The exact categories and names
are listed in `FEATURE_INVITATION_INVENTORY.csv`.

This affects invitation visibility. It does not mark anything seen, claim a
reward, remove objects or gifts, alter balances, replace the source archive,
or disable core farming tools. `scratchCard`, `fcSlotMachine`, `carnivalBooth`,
`QuestGenericIcon` and `QuestManager` are explicitly protected because they
have independent restored entry paths. Ordinary cottage recipes keep their
own original UI.
The red-roof shop artwork is the original `fcSlotMachine` icon.
`CarnivalBoothQueuedIcon.injectContent` places a random Pigo prize image into
its card; the changing animal picture remains the restored Game Tent entry.
These are retained alongside Scratch-Off. The toolbar camera is a separate
control and is outside this invitation gate.

The launch templates also both serve `fv_instagrow_autoharvestreplant=0`.
The Flash bootstrap previously used 4 while the Ruffle bootstrap used 0;
the combined Harvest & Replant action has no restored server implementation.
Ordinary harvest, planting and supported Instant Grow remain independent.

The archived `postInitSequence.xml.gz` is projected when served, using the
explicit 41 action names below. These actions introduce terminal presentations
for retired event economies, limited offers or external email campaigns. Missing feature options evaluate
to zero in the client and would otherwise open old leaderboard and NPC windows
on a newly created farm. For example,
`forceGrantFarmersMarketInnovationLeaderBoardReward` calls the original market
manager's `onRedeemStarted`; `forceShowAnimalSAnctuaryV2FinalWindow` calls
`AnimalSanctuaryV2Manager.featureEnd` and sets `asV2` seen on the client.
Withholding those invitations avoids implying an event payout was earned.
The delayed `fuelBoost` idle task calls `FuelBoostWindow.showStatic` after
six seconds for level 12+ players with the legacy email permission and no
`fuelBoostWindowPermanent` flag. The related `consumableCampaign` idle tasks
open the external email-program windows. Withholding these tasks leaves real
email permissions and all saved flags unchanged.

Only these named startup actions are removed. Their saved feature ledgers,
already owned gifts and rewards remain untouched, as do server-side legacy
payout acknowledgments. Ordinary quest, collection, ribbon and level rewards
are outside this projection. Every other startup node is preserved, including
the crafting reminder, crop-unlock notification, world preload, neighbors and
free-gift loading. This is not a complete audit of every hard-coded client
popup or late event manager.

| Removed startup action | Reason |
| --- | --- |
| forceGrantWhiteWinterRewards | Retired event reward presentation |
| forceGrantTuscanyInnovationBonusReward | Retired event reward presentation |
| forceGrantHalloween2019InnovationBonusReward | Retired event reward presentation |
| forceGrantCanadaInnovationBonusReward | Retired event reward presentation |
| forceGrantBoraboraInnovationBonusReward | Retired event reward presentation |
| forceShowAnimalSAnctuaryV2FinalWindow | Retired sanctuary final window |
| forceGrantFarmersMarketInnovationBonusReward | Retired market event reward presentation |
| forceGrantFarmersMarketInnovationLeaderBoardReward | Retired market leaderboard |
| forceGrantTropicalMarketInnovationBonusReward | Retired market event reward presentation |
| forceGrantTropicalMarketInnovationLeaderBoardReward | Retired market leaderboard |
| forceGrantBoraboraInnovationLeaderBoardReward | Retired event leaderboard |
| forceGrantGiftRacing2019BonusReward | Retired racing reward presentation |
| forceGrantBoatRacing2020BonusReward | Retired racing reward presentation |
| forceStopCoOpAndGrantGift | Retired co-op shutdown gift presentation |
| forceGrantRussiaInnovationBonusReward | Retired event reward presentation |
| forceGrantIsraelInnovationBonusReward | Retired event reward presentation |
| forceGrantSouthindiaInnovationBonusReward | Retired event reward presentation |
| forceGrantDec19InnovationBonusReward | Retired event reward presentation |
| forceGrantIrelandInnovationWeeklyReward | Retired event reward presentation |
| forceGrantWinternordInnovationCommunityReward | Retired event reward presentation |
| forceGrantWinternordInnovationWeeklyReward | Retired event reward presentation |
| forceGrantMadagascarInnovationCommunityReward | Retired event reward presentation |
| forceGrantMadagascarInnovationWeeklyReward | Retired event reward presentation |
| forceGrantAmsterdamInnovationBonusReward | Retired event reward presentation |
| forceGrantWreathFestivalInnovationBonusReward | Retired event reward presentation |
| forceGrantTwentiesInnovationWeeklyReward | Retired event reward presentation |
| forceGrantPumpkinPartyInnovationWeeklyReward | Retired event reward presentation |
| forceGrantWinternordInnovationChristmasReward | Retired event reward presentation |
| forcePopupSpecialLEBundleWindowDay1 | Expired limited-offer popup |
| forcePopupSpecialLEBundleWindowDay2 | Expired limited-offer popup |
| forcePopupSpecialLEBundleWindowDay3 | Expired limited-offer popup |
| forcePopupContingencyBuildableBonusRewardWindowDay1 | Retired buildable compensation popup |
| forcePopupContingencyBuildableBonusRewardWindowDay2 | Retired buildable compensation popup |
| forcePopupContingencyBuildableBonusRewardWindowDay3 | Retired buildable compensation popup |
| forcePopupContingencyBuildableBonusRewardWindowDay4 | Retired buildable compensation popup |
| forcePopupContingencyBuildableBonusRewardWindowDay5 | Retired buildable compensation popup |
| forcePopupContingencyBuildableBonusRewardWindowDay6 | Retired buildable compensation popup |
| forcePopupContingencyBuildableBonusRewardWindowDay7 | Retired buildable compensation popup |
| fuelBoost | Retired external email-program fuel signup |
| consumableCampaign | Retired external email-program signup |
| consumableCampaignInactive | Retired external email-program return signup |

Regression coverage verifies exact invitation membership and preserved entries,
identical Flash/Ruffle parameters, source archive byte identity, exact retained
startup nodes, the served compressed response and unchanged player memory/disk.
Browser acceptance is tracked separately by the active investigation.

## Hard-coded invitations reviewed on 2026-10-24

Five entries in `FEATURE_INVITATION_INVENTORY.csv` use category
`client_presentation_gate`. They bypass `DynamicIconQueue`; their names are
review identifiers in `feature_availability.CLIENT_PRESENTATION_GATES`, rather
than FlashVar blacklist entries. The final pinned `client_compatibility.py`
stage handles the original methods:

| Invitation | Original presentation gate |
| --- | --- |
| Market VIP only Sale | Hide the full Market3 walkthrough with its embedded VIP promotion plus the separate VIP tutorial and mini-window banner |
| Shipping Licenses | Open Inventory and hide its shipping tab |
| Farm with One Click / 3 free Turbo | Return false before Turbo onboarding increments its action count |
| Expand Storage 6 to 6 | Hide the Inventory expansion tab and omit the storage-building expansion menu item |
| Repeated automatic cottage choice | Return from `showCottageReminderOnLoad`; retain manual cottage choice and the free-cottage gift path |

The existing Turbo/storage purchase refusals remain as fallback entry guards.
Cottage upgrades are now shown for bakery, winery, perfumery and pub, whose
paid upgrade and recipe services are restored. Other craft purchase buttons
stay hidden. The water purchase popup and sprinkler tutorial are outside these
nine changed methods and retain their original code.

This stage does not write invitation acknowledgments, award three Turbo charges,
or alter saved progress. The startup crafting-reminder node remains in the
served XML; its automatic presentation method now returns without a popup.
See `COTTAGE_INVITATIONS_CLIENT_2026-10-24.md` and its JSON byte review for the
exact methods, hashes and validation boundary.

The later Inventory artwork correction is documented in
`ClientPatches/INVENTORY_TAB_ART_2026-10-24.md`. GenericButton's transparent hit
rectangle is a sibling of its visible target; both layers now hide for Expand
and Shipping. Ordinary Inventory content and controls remain unchanged.

The restored ordinary market stall exposes a separate archived expansion economy. Its own `readyToExpand` invitation getter is now false, and both direct expansion entries show the existing local storage refusal before any callback, optimistic capacity change, transaction or cash debit. Ordinary bushel configuration and stall management remain available. See the [source-backed byte review](ClientPatches/MARKETSTALL_EXPANSION_2026-10-24.md).

The ordinary Inventory route uses `Widgets.Windows.Storage.StorageWindow`; its
new [visibility gate](ClientPatches/WIDGET_STORAGE_VISIBILITY_2026-10-24.md) registers
both complete unsupported buttons as hidden. The older InventoryWithdrawal art
patch covers the separate legacy renderer. Fresh-browser screenshot22 established
that the legacy patch alone did not cover the ordinary route.
