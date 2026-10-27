> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../ACCEPTANCE.md), [current world scope](../../../WORLD_READINESS.md) and [the continuation backlog](<../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Cottage skill progression and recipe rushes

Implemented on 24 October 2026 in `crafting.py`. This document records source,
unit and signed-AMF verification. The lead agent's
Finish Verification report (`../../../Finish%20Verification%202026-10-24/README.md`; external/private historical reference, not included in this source export)
also records the observed Bakery progression, both paid upgrade routes,
higher-skill recipe rush/automatic claim, goods use and fresh-VM persistence.
That browser pass covers the recorded loop; the full reviewed recipe roster
retains its broader automated evidence.

## Restored behavior

The four supported cottage types are Bakery, Winery, Perfumery/Spa and Pub.
An explicit reviewed extension adds 58 higher-skill recipes to the existing
53 skill-one recipes: 32 Bakery, 31 Winery, 31 Perfumery and 17 Pub recipes,
111 in total. Other craft types and prerequisite-dependent recipes stay outside
the service allowlist. Original seasonal gates on the existing recipes remain.
Every added recipe keeps its authored skill requirement, initial recipe level,
ingredients, production time, player/recipe XP, product quantity and fuel value.

Recipe XP still raises the recipe level and adds one craft XP per recipe level.
Craft XP does not raise cottage skill automatically. The original paid upgrade
uses `CraftingService.onBuyCraftUpgrade(craftType, isRushUpgrade)`, with a strict
Boolean second parameter and one owned completed matching cottage on Home.

| New skill | XP required for coin route | Coin price | Cash bypass | Ovens |
| --- | ---: | ---: | ---: | ---: |
| 2 | 6 | 50,000 | 15 | 3 |
| 3 | 18 | 100,000 | 25 | 4 |
| 4 | 27 | 400,000 | 40 | 5 |
| 5 | 36 | 1,000,000 | 60 | 6 |

Both routes consume the new level's craft XP requirement, clamping the remainder
to zero. The cash route bypasses the XP eligibility check. The coin route enforces
it even if a forged caller bypasses the client button. The skill state and saved
cottage level are synchronized, newly eligible recipes unlock at their original
initial levels (3, 6, 9 or 12), and existing recipe levels, XP, timers and imported
metadata are retained. Level five has no further upgrade.

`CraftingService.onRushRecipe(recipeId, serverStartTS, withCoins, ovenSlot)`
selects an exact saved queue entry. It validates ownership, timestamp, oven,
readiness, currency availability and balance. The original 111 recipes have a
5 Farm Cash price and an unavailable coin price of -1; unavailable prices are
never subtracted as credits. Only that entry becomes ready. Rushing creates no
goods and records no crafting quest completion; the client follows the callback
with the normal claim, which creates the original products once.

For ordinary jobs the saved finish time becomes `serverStartTS - 300`, matching
`RecipeItem.onRushComplete`. The special five-second onboarding job has an
authored start timestamp of 1; its equivalent ready timestamp is clamped to 1 so
it remains valid in the existing queue schema. No production duration was changed.
`onRushRecipeWithTime` remains an explicit unsupported service branch.

The existing detached-copy dispatch and bounded per-session request receipts
make retries free and prevent reused sequences from running a different action.
Server restart preserves receipts; a new Flash session clears them while keeping
skill, recipes, queues, goods and balances.
The separate `localCraftingHighestSequence` floor also rejects old requests
after the last-256 receipt eviction. Existing saved receipt maps derive that
floor from their retained keys; login resets both pieces of session history.

## Bytecode evidence and callback shapes

Inspected `/private/tmp/FarmGame-crafting-finish-20261024.swf`, a copy of the
original source client, using `macOS/Scripts/client-inspection/abcdis.py`.
The repository SWF was not edited.

- `CraftTypeState.incrementLevel` (22213), `addExperience` (22216),
  `CraftingSkillState.grantDefaultRecipes` (23033), and
  `CraftingManager.buyCraftTypeUpgrade` (5904) establish paid progression,
  craft-XP subtraction and authored recipe unlocks.
- `TCraftBuyUpgrade.perform` (22729) sends craft type and the Boolean rush flag.
  It does not send a target level. `CraftingManager.onCraftUpgraded` (5908)
  dereferences `result.rewardLink`; the server therefore returns
  `{"rewardLink": null}`.
- `TBuyRecipeRush.perform` (22204) sends recipe ID, saved start timestamp,
  Boolean currency choice and oven slot. `endRecipeRushedBuy` (5957) invokes
  `RecipeItem.onRushComplete` (17902); `CraftingMainProductionSlot.onEndRecipeRush`
  (62919) immediately invokes the normal claim path.
- **Rush reply must be a non-null object.** `Engine.Transactions:Transaction.onAmfComplete`
  (1187), byte offsets 110–126, calls the transaction callback only when
  `data != null`. Returning null would debit the rush but suppress automatic
  claim. The implemented rush reply is `{}`, and the AMF regression asserts it.

The broader 2,946 recipes still span 87 craft types and independent buildings,
queues and world rules. This work does not label all historical crafting restored.

## Verification

Focused command, from `macOS/Tests`:

```sh
PYTHONPATH=../.. ../../LocalData/venv/bin/python -m unittest \
  test_crafting_progression test_crafting_progression_wire \
  test_crafting test_cottage_recipes test_cottage_lifecycle
```

**68 tests passed in 19.989 seconds.** Log:
`/private/tmp/crafting-receipt-floor-final-20261024.log`.

The eleven new unit tests cover all 58 added recipes through ingredient purchase,
begin, paid rush, separate claim and original fuel use; all skill prices/XP/oven
counts; locks and initial levels; insufficient funds/context; exact queue identity;
metadata, reload and request replay. The seven new signed-AMF tests cover the
actual gateway replies, retry/reload, forged packets and per-command rollback
with accepted neighboring actions. Existing 50 cottage tests retain ordinary
production, seasonal gates, onboarding, snapshots and goods behavior.
The eviction regression sends 257 accepted signed-AMF requests, then proves
that an evicted paid-upgrade retry cannot purchase the next level, including
after save reload.

## Quest progression boundary

The browser acceptance log records the ordinary higher-skill sequence for `b3`:
begin, a five-cash `onRushRecipe` request, and its automatic
`onClaimFinishedRecipes` callback. Recipe/player XP is earned on begin through
`RecipeItem.grantMakeReward` (17905); finishing adds the goods. The successful
nonempty claim records one crafting quest action, matching
`TClaimFinishedRecipes.getTransactionData` (22561), which supplies one
`recipeCode` even when several queue entries are returned.

One older quest implementation remains outside this Home-cottage verification.
`getRecipeLevelByCategory` is currently derived as a count of unlocked recipe
members, while `FarmQuestUtility.getAchieveRecipeLevelByCategoryProgression`
(7207, bytes 41–155) increments for each `recipeLeveledUp=true` event in the
category. The four archived tasks using this action belong to the Japan craft
type `xjpcrafttype`: `regionach-r1-002` through `regionach-r4-002`, with category
sizes 12, 12, 4 and 16 but task totals 54, 40, 36 and 60. None of those recipes
is among the 111 supported cottage recipes. Restoring that craft family requires
the original event-count progression; the current member count must not be
treated as proof that those four regional tasks work.

## Additional mastery investigation

Crafting mastery bonuses and presentation are a separate historical gap; no new
mastery reward path was silently inferred here. `RecipeItem.getMasteryLevelForRecipeLevel`
(17899) reads the recipe's `Mastery/MasteryLevel` thresholds; the archived
`TFarmTransaction.GOAL_TYPE_RECIPEMASTERY` constant is exactly `RecipeMastery`.
`handleGoalResponse` (1213) consumes `goals` records with product `code`,
`difficulty` (the star level) and `link`, then calls `CraftingManager.handleMastery`
(5816). The latter updates an owned sign, avoids a duplicate sign gift, and
opens the original popup. `RecipeMasterySign.loadObject` (22174) reads saved
`level` directly.

The popup reads the original coin/XP values for display; the inspected handlers
and base transaction do not themselves credit those balances. An additional
original reward-accounting/HUD path must be established before claiming that
crafting mastery bonuses are restored. Existing seasonal and production timers
must not be changed to simulate that progress.
