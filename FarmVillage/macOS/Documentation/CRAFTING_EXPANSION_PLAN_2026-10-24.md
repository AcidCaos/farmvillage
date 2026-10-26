> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../ACCEPTANCE.md), [current world scope](../../../WORLD_READINESS.md) and [the continuation backlog](<../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Bounded cottage crafting expansion: recovered implementation plan

Read-only investigation on 2026-10-24. No crafting implementation, allowlist,
client projection or saved timer was changed. No browser acceptance is claimed.

## Scope supported by the recovered data

The 2,946 archived recipes span **87 craft types**, including 1,187 `craftshop`
recipes. They do not all belong to the four cottages currently implemented.
Other types need their original buildings, queues, products and world rules.
Removing the current recipe filter would incorrectly admit those contracts.

The four current cottages have 139 recipes. A coherent next batch contains
111 prerequisite-free, nondeprecated, same-code-product recipes:

| Craft | All rows | Bounded candidates | Already supported | Additional |
| --- | ---: | ---: | ---: | ---: |
| Bakery | 46 | 32 | 15 | 17 |
| Winery | 37 | 31 | 14 | 17 |
| Perfumery | 39 | 31 | 14 | 17 |
| Pub | 17 | 17 | 10 | 7 |
| Total | 139 | 111 | 53 | 58 |

Every candidate ingredient resolves to an original `bushel`/`CBushel` item
(313 ingredient rows). All 111 products resolve to `crafted`/`CCrafted` items.
Every referenced mastery sign exists in the original item catalog. None has
recipe-level or craft-level override tables. Twenty-one of the existing
level-one candidates have original seasonal windows; retain those gates. All
58 additional recipes have no seasonal window.

Use an explicit reviewed extension to the immutable allowlist rather than
admitting arbitrary future catalog entries. Additional codes are:

- Bakery: `b3 b4 b5 b6 b7 b8 7KJ c0 c1 c2 c3 c4 c5 7Kw 0gl 0xf 0Y1`.
- Winery: `0f8 w3 w4 w5 7J5 w6 w7 w8 w9 c6 c7 c8 c9 d1 7JR 0su 0Zc`.
- Perfumery: `0fW p3 p4 p5 p6 p7 p8 7HT p9 d2 d3 d4 d5 d6 7H4 0wW 0Zd`.
- Pub: `lu ls 7IR lv lr 0hh 7In`.

## Skill progression is a paid upgrade, not automatic leveling

Disassembled a scratch copy of `FarmGame.swf` using `abcdis.py`. Relevant
contracts and source positions:

- `RecipeState.incrementLevel`, method 22764, source lines 83–93, increases
  recipe level, resets recipe XP, and calls the matching craft state's
  `addExperience(1)`. `RecipeState.addExperience`, method 22765, source
  lines 100–120, recursively carries positive recipe-XP remainder through
  subsequent recipe levels. The existing `_add_recipe_xp` already mirrors
  these recipe-level and craft-XP steps.
- `CraftTypeState.addExperience`, method 22216, source lines 112–114, only
  accumulates experience. It does **not** raise craft level.
- `CraftingMainWindow.updateUpgradeFrame`, method 34693, source lines
  817–835, compares saved craft XP with the next craft level's XP requirement.
  Before the threshold it offers the cash upgrade; at the threshold it offers
  the coin upgrade. Configured level prerequisites must also pass.
- `CraftingManager.buyCraftTypeUpgrade`, method 5904, source lines 3686–3717,
  deducts the next level's cash or coin price locally, increments the craft
  level, grants newly eligible default recipes, and queues `TCraftBuyUpgrade`.
- `TCraftBuyUpgrade.perform`, method 22729, sends
  `CraftingService.onBuyCraftUpgrade(craftType, isRushUpgrade)`.
  `getTransactionData`, method 22731, reports `nextLevel` for local quest
  prediction; **nextLevel is not a server request parameter**.
- `CraftTypeState.incrementLevel`, method 22213, source lines 82–91, raises
  the level once and sets XP to `max(0, oldXP - newLevelRequirement)`.
- `CraftingSkillState.grantDefaultRecipes`, method 23033, source lines
  100–117, grants/unlocks eligible recipes through the craft's current level,
  using each recipe's original initial level. Higher skill recipes start at
  recipe levels **3, 6, 9 and 12**, rather than always level one.
- `CraftConfigSettings.getAllRecipes`, method 5166, source lines 415–418,
  applies the recipe prerequisite, skill requirement and limited-date checks.
- The upgrade callback closure (method 5903) invokes
  `CraftingManager.onCraftUpgraded`, method 5908. That method dereferences
  `result.rewardLink` without checking `result` first. A local upgrade must
  return **`{"rewardLink": null}`**, never a null result.

Original global upgrade table (`crafting.xml.gz/craftTypeLevels`):

| New craft level | Required craft XP for coin route | Coins | Cash bypass | Ovens |
| --- | ---: | ---: | ---: | ---: |
| 2 | 6 | 50,000 | 15 | 3 |
| 3 | 18 | 100,000 | 25 | 4 |
| 4 | 27 | 400,000 | 40 | 5 |
| 5 | 36 | 1,000,000 | 60 | 6 |

The server must enforce the XP threshold for the coin route even though the
client hides that button until it is eligible. The cash route bypasses craft
XP but still needs an owned completed matching cottage and sufficient cash.
Level five has no further upgrade.

## Recipe rush wire path

- `TBuyRecipeRush.perform`, method 22204, source lines 42–53, sends
  `CraftingService.onRushRecipe(recipeId, serverStartTS, withCoins, ovenSlot)`.
  It deducts the configured rush price locally before the response. All 58
  additional recipes have `RushCostCash=5` and `RushCostCoins=-1`.
  **-1 means an unavailable coin route; do not subtract it as a price.**
- `TBuyRecipeRush.onComplete`, method 22205, calls its callback. Closure
  5955 passes the result to `CraftingManager.endRecipeRushedBuy`, method 5957,
  which calls `RecipeItem.onRushComplete` then the UI callback.
- `RecipeItem.onRushComplete`, method 17902, source lines 1093–1096, sets
  the client finish timestamp to `serverStartTS - 300`.
  `CraftingMainProductionSlot.onEndRecipeRush`, method 62919, immediately
  calls the existing claim path. The rush response does not itself award the
  product; claim remains responsible for inventory and quest progress.
- The transaction can alternatively call `onRushRecipeWithTime`, omitting a
  balance deduction. That alternate currency/timer contract was not recovered
  here and should remain an explicit rejection.

## Smallest coherent implementation batch

1. Add the reviewed 58 codes and retain current structural/availability guards.
   Admit their original initial recipe levels. Update the `ComingSoon` client
   projection only for the accepted extension.
2. Unlock each admitted recipe only when the matching owned cottage's saved
   craft level satisfies its authored requirement. Keep locked display states
   for other recipes, preserve imported XP/metadata, and retain original dates.
3. Add `onBuyCraftUpgrade` to `crafting.METHODS` and `dispatch`: validate a
   strict Boolean rush flag, next level, funds, required craft XP and cottage
   ownership; debit once, advance one level, carry XP, unlock eligible recipes,
   synchronize cottage/skill state, and return the recovered callback object.
4. Add `onRushRecipe` with four exact parameters: resolve the saved recipe,
   start timestamp and oven, reject a ready/missing/mismatched entry, enforce
   a positive available price and sufficient balance, debit once, and make
   only that queue entry ready. Reuse the existing request receipts and
   copy-before-commit dispatch boundary. Claim awards the goods afterwards.
5. Do not add automatic craft levels, silently enable the time-rush branch,
   alter existing timers, or expose unrelated craft types.

Tests must cover coin XP gates, cash bypass, all original level prices and
oven capacities, initial recipe levels, insufficient funds, malformed flags,
recipe availability, preserved metadata, independent ovens, duplicate requests,
sequence reuse, rush/claim ordering and persistence after reload. Exercise the
new operations through signed AMF and verify a rejected call cannot debit or
unlock anything while accepted neighbors in a batch remain durable.

Use a fresh disposable landscape browser fixture to accept an earned coin
upgrade, cash bypass, a newly unlocked higher-skill recipe, paid rush followed
by automatic claim, replay/reload, and its original fuel output. Confirm other
crafts still open correctly and retained recipes remain locked. Only activate
the widened client projection after those checks, then rerun the full suites.

Crafting mastery presentation/rewards (`CraftingManager.handleMastery`, method
5816) and social crafted-good sales are additional existing gaps. Review their
server metadata before claiming that all original crafting behavior is restored.
