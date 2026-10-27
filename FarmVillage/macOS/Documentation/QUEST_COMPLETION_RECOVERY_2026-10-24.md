> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../ACCEPTANCE.md), [current world scope](../../../WORLD_READINESS.md) and [the continuation backlog](<../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Recovering earned quest rewards after a lost acknowledgement

A client crash after displaying an optimistic quest reward can leave the saved quest active with every task finished. Previously, all normal quest metadata still carried `complete=false`. A fresh client loaded the checked tasks as active and had no completion event to reopen the reward window.

The server now announces a normal quest with strictly completed saved progress as `complete=true` once per Flash session. While that earned quest awaits the original reward-window acknowledgement, subsequent metadata omits it. Login resets the announcement latch, so a crash or lost acknowledgement can reoffer the earned reward through the original client flow. Generating metadata does not grant rewards, retire the quest or alter task progress.

The original `FarmQuestService.updateRecentlyCompletedQuests` acknowledgement remains the accounting boundary. Its existing idempotent `complete_quest` grants the saved reward, records completion and unlocks eligible children once. Retrying that acknowledgement, including after server restart, cannot grant the reward again. The zero-reward `viewDialog` introduction quests retain their existing special first-true/subsequent-false behavior.

## Original-client proof

Read-only disassembly used `/private/tmp/FarmGame-crafting-finish-20261024.swf`, a scratch copy of the original bundled client. No SWF was edited.

| Method | Relevant behavior |
| --- | --- |
| `ZQuest.Managers.QuestManager.onTransactionComplete` 6807, bytes 465–516 | An incoming `complete=true` entry dispatches `COMPLETED` when the quest is unknown locally or requires authoritative server progress. A fresh client has no active quest entry, so this is its recovery trigger. |
| Same method, bytes 520–620 | A completed incoming entry is not added to the active array. Repeating `complete=true` while waiting for acknowledgement could repeatedly dispatch client rewards. |
| Same method, bytes 524–567 | An unknown `complete=false` entry is added as active and dispatches progress. Sending a recovered quest as incomplete afterward would resurrect it. |
| `FarmQuestManager.onQuestProgress` 6843 and `FarmQuest.onProgress` 6713, bytes 163–175 | Progress can recreate a missing icon without consulting the completed-session list. Pending recovered quests must therefore be omitted, rather than resent as incomplete. |
| `QuestManager.performClientProgressUpdate` 6805, bytes 28–36 | Client prediction marks an existing active record complete before dispatching completion, retaining that record. For ordinary predicted quests, the normal final transaction response does not dispatch completion a second time. |
| `FarmQuestManager.shouldUpdateProgressFromServerResponse` 6881 and base 6808 | Distinguish server-dependent quests from ordinary client prediction; the base returns false when client prediction is enabled. |
| `FarmQuestManager.onQuestComplete` 6844, bytes 85–118 | Records session completion, grants optimistic client rewards through `UserRewardUtil` and schedules the original reward display. |
| `QuestRewardDialog.onCloseButtonPress` 23988, bytes 19–40; `QuestCompleteWindowWithRewardItem.onClose` 23728 | Closing the original reward dialog queues an immediate `TShareQuestLoot(name,false,dialog)` transaction. |
| `TShareQuestLoot.perform` 45950 | Sends `FarmQuestService.updateRecentlyCompletedQuests(name,shouldGenerateFriendReward)`. |

`fullQuestRefresh` alone cannot guarantee recovery inside an already loaded client whose predicted quest remains active: method 6807's ordinary prediction branch excludes that existing entry. A fresh VM/login is the reliable recovery path. Full refresh and sibling responses in that session must not repeatedly announce or resurrect the pending reward.

## Validation boundaries

Normal completion announcements require a nonempty task list, matching progress length, positive integer authored totals, and finite numeric saved progress meeting every total. Booleans, strings, missing counts and non-finite values are not accepted as completion. The existing world filtering runs before announcement. An announcement remains separate from the original acknowledgement and its accounting.

The regression uses the original `feather-01-005` definition: task totals `[7,2,700]`, 100 XP, 2,500 coins and avatar item `9239`. The avatar catalog identifies that item as `UnisexFeatherQuestSnowboardingOutfit`, with `buyable=false`. Tests do not replace this quest or its reward with a synthetic catalog definition.

The eight dedicated tests in `test_quest_completion_recovery.py` passed in 17.785 seconds, including three signed-AMF gateway tests. They cover first announcement, pending omission, session reset, invalid progress, legacy view-dialog behavior, a lost acknowledgement followed by reload, and exact-once outfit/coin/XP grants. The log is `/private/tmp/quest-completion-recovery-tests-20261024.log`. Browser acceptance is recorded by the lead agent separately.

The combined quest skip, action, score and completion-recovery regression batch passed 66 tests in 19.160 seconds (`/private/tmp/quest-completion-regression-20261024.log`). No changes to the existing quest test helpers were required.

Detailed research artifacts are `/private/tmp/quest-recovery-{manager,base-complete,close,authority}-20261024.txt` and `/private/tmp/quest-reload-review-{init,completion,prediction,resurrection,on-progress}.txt`.
