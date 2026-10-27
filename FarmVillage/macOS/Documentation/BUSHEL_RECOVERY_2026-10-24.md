> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../ACCEPTANCE.md), [current world scope](../../../WORLD_READINESS.md) and [the continuation backlog](<../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Home crop bushels: recovered contract and next implementation

Status: read-only recovery. No bushel economy or harvest source was changed.
This document separates proven client reads from a proposed server model;
neither unit tests nor browser acceptance for that model have been performed.

## Why nothing drops now

`commands.world_perform_action` validates crop maturity, pays coin/XP/mastery
and saves the harvested plot. It never adds the crop's `bushelItemCode` to
`craftingState.craftingItems`. The ordinary gateway response contains an ID,
and `metadata.ActionDrops` is not populated with bushel results. Both client
paths which add found bushels therefore receive nothing.

Both `templates/play.html` and `templates/ruffle.html` set
`fv_simplified_bushels = 2`. The client enables its Bushel Report when that
experiment is greater than one. The old CMS values `craftingBushelChance = 1`
and `craftingBushelChanceBoosted = 5` must not be guessed into an RNG algorithm
for this currently enabled feature.

## Proven client reads

All method numbers below come from a copy of the original
`embeds/Flash/v855097-855094/FarmGame.swf`, SHA-256
`1edea7cbecefcb1e1233da207164942f0088a83b87afc9254850f5fcde5034ae`.
The SWF and product sources were not modified during recovery.

| Method | Recovered behavior |
| --- | --- |
| `TInitUser.onComplete` (6891), lines 553–554 | Reads top-level `seedHarvestCountsSinceLastBushelDrop`, passing it to `Player.setAllSeedHarvestCountsSinceLastBushelDrop`. |
| `Player.getHarvestCountForSeedSinceLastBushelDrop` (4204) | Reads a map keyed by **seed** item code, defaulting to zero. |
| `Plot.harvest` (21798), lines 1551–1559 | Increments the local seed harvest counter after queuing `THarvest`. Normal plots add one; SuperPlot and harvest-yield buffs can change the increment. |
| `BushelReportSlot.setKMultiplier` (33193), lines 91–93 | Reads `flashHotParams.KBUSHEL_MULTIPLIER_TMPRT`, defaulting to 50. |
| `BushelReportSlot.setupBushelYield` (33198), lines 168–185 | Computes the report's expected yield from seed harvest count, a mastery/supercrop adder, permanent-buff multiplier and world scale. See below. |
| `CraftingManager.getNewBushelBonusAdders` (5788), lines 955–971 | For non-silo bushels: adds the seed's zero-based mastery value plus one when present, and `bushelSuperCropBonus` (default/CMS value 3) for a SuperCrop. |
| `SeedItem.isSuperCrop` (14258), lines 124–140 | Reads the catalog's `superCrop` boolean/`"true"` value. It is not the large-plot flag. |
| `BPermanentTypeGain.getNewDoubleBushelBonus` (15302) | Reads active `bushel_gain` permanent type gains. When the report feature is enabled and gain >1, multiplies it by the additional constant 2. |
| `FarmGameSettingsManager.getWorldBushelChanceScale` (3217) | Starts with scale 1, then considers dated world/season hot parameters and expansion `bushelChanceScale`. |
| `THarvest.onComplete` (26920), lines 157–163 | Calls `checkHarvestProduce` for an item with a bushel code or a response containing `foundBushel`. |
| `THarvest.checkHarvestProduce` (26924), line 396 | Calls `CraftingManager.handleBushelFound(response)`. |
| `CraftingManager.handleBushelFound` (5764), lines 1143–1147 | Calls `recordBushelFound` only when `foundBushel` is present. |
| `CraftingManager.recordBushelFound` (5798), lines 1165–1191 | Reads the nested `foundBushel.bushelCode`; adds `bushelsAddedToInventory` once to the client inventory when positive. |
| `ActionDropsManager.onTransactionComplete` (33156), lines 69–80 | Dispatches `rawResult.metadata.ActionDrops` to action-drop listeners. |
| `BushelReportActionDropHandler.refreshActionDropStatus` (12508), lines 50–73 | Reads `bushelReport.dropTypeFuncResult`, calls `handleBushelFound` for its numeric entries, then applies `newHarvestQuantities` records with `itemCode` and `quantity`. |

The recovered **UI report formula**, with integer truncation at the two shown
points, is:

```text
bonus = masteryStars + (3 if superCrop else 0)  # non-silo case
threshold = int(K / (1 + bonus))
weightedCount = savedCounter + permanentGain * (pendingCount + worldCountAOE)
reportYield = int(weightedCount / threshold * worldScale)
```

For an ordinary Home seed with no mastery, buffs or hot-parameter override,
the report predicts one bushel per 50 harvested plots. For one/two/three mastery
stars the threshold is 25/16/12. That report is evidence for a deterministic
cadence; the original server's actual counter-reset, overflow and full-inventory
algorithm is not present in this client and remains an implementation inference.
Do not label those details recovered merely because the UI can predict a yield.

The source expansion XML has no Home expansion override. Its four explicit
`bushelChanceScale` values belong to Hawaii (2), Asia (5), HTown (2) and Angler
(5). Home therefore follows the default path unless its live hot parameters
provide a boost. Limiting an initial implementation to Home is a proposed scope
boundary, not an original client eligibility rule. Foreign seeds admitted to
Home must still use their actual catalog `bushelItemCode` and the bushel's type.

## Award envelope and double-grant boundary

The direct harvest route consumes:

```json
{
  "foundBushel": {
    "bushelCode": "sb",
    "bushelsAddedToInventory": 1,
    "bushelsAddedToSharedReward": 0,
    "bushelAddedToStall": false
  }
}
```

The simplified ActionDrops route reads this structure:

```text
metadata.ActionDrops.bushelReport.dropTypeFuncResult
  [0..length-1] -> objects containing foundBushel, as above
  newHarvestQuantities -> [{itemCode: "SB", quantity: newCounter}, ...]
```

This is the exact set of accesses from bytecode, not a captured original
server response. `dropTypeFuncResult` is coerced to Object and accessed by
`length`, numeric index and the named `newHarvestQuantities` property. A proposed
Python encoding as an Object with explicit numeric properties and `length`
needs a real-client check; a plain JSON/AMF list cannot carry its named property.

**Never send the same award in both data.foundBushel and numeric ActionDrops
entries.** Both handlers call `recordBushelFound`, which increments the client
inventory. The server can grant once while the client incorrectly shows twice.
The proposed simplified implementation should use one award route, with the
ActionDrops route also synchronizing the authoritative counter. Counter-only
metadata is needed even for harvests that do not cross a threshold.

`marketStallBushelFoundDialogs` (5791) only reads `marketStallId`,
`newTimeExpires` and `openStallRewardUrl` when `bushelAddedToStall` is true.
Its no-stall-sharing branch can still display an invitation to buy/reconfigure
a stall. Do not invent an open-stall reward URL or claim social sharing.

## Capacity, inventory and free-stall side effects

- `crafting.xml.gz/featureConfig/globalInventoryBushelCapacity` is 400.
  Existing `crafting._initialize` already upgrades legacy capacity to at least
  this value and preserves larger saved upgrades.
- `CraftingState.initCraftingStateFromInitUser` (15798), lines 461 onward,
  loads `craftingItems`; lines 517–518 assign the supplied `maxCapacity` to
  `CraftingInventoryStateV2.baseCapacity`.
- `CraftingInventoryStateV2.maxCapacity` (22474) returns that base field;
  `currentCapacity` (22462/22448) sums the quantities of market-stall bushels.
  Silo, laboratory, unsharable and village items have distinct client storage
  paths. A crop having `bushelItemCode` alone does not prove it belongs in the
  ordinary 400-capacity inventory.
- Existing server bushels are rows `{itemCode, quantity, price}` inside
  `craftingState.craftingItems`. Recipe purchase already enforces capacity,
  rejects duplicate stacks and uses `{price: null}` for a new row.
- `CraftingManager.firstMarketStallDialog` (5795), lines 1072–1084, runs after
  an ordinary stall-type bushel is actually awarded. If the `FirstMarketStall`
  seen flag is absent and no stall is placed or in gifts, it immediately adds
  a **free marketstall gift** on the client. That must be mirrored durably.
- `FirstMarketStallWindow.<cinit>` (23036) defines `SEEN_FLAG = FirstMarketStall`.
  `getFirstMarketStallSeenFlag` (23037) uses that spelling on Home and suffixes
  `_worldType` elsewhere. `setSeenFlag` (23043) records it when the window
  progresses; do not pre-mark it before the initial popup without acceptance.
- `getAllMarketStallsCount` (5866) sums placed stalls and gift-box stalls.
  `getMarketStallsInGiftBox` (5867) recognizes catalog class
  `MarketStallBuilding`, not only an invented item-name list. Ordinary world
  inventory is not included in that client function.
- The original `marketstall` catalog item has code `ms`, class
  `MarketStallBuilding`, five tiers and an ordinary purchase/expansion price.
  Its free first-bushel onboarding gift is a separate event from market purchase.

## Proposed minimal implementation after the current batch stabilizes

1. Add a separate `bushels.py` helper; do not put new crafting state into
   engine currency helpers. Restrict its first accepted path to validated,
   mature ordinary Home plots with supported stall-type bushels and known
   multipliers. Read owned state, not optimistic harvest options.
2. Persist top-level `seedHarvestCountsSinceLastBushelDrop`. Count once only
   after maturity checks and before the original mastery update, so an award's
   mastery adder matches the client state at harvest start. Use existing
   fallow/retry guards and preserve valid neighboring AMF calls on rejection.
3. Plan the inferred full-inventory/overflow policy explicitly before coding.
   The client proves how to display a grant, not whether a full inventory
   preserves credit toward the next grant. Never silently overflow capacity.
4. Add inventory rows using the actual bushel code; preserve unrelated rows,
   larger saved capacities, quantities, metadata and pending cottage timers.
   Mirror the one-time free-stall gift without duplicating it on retries or
   reload. Keep unsupported social/stall opening separate.
5. Populate per-command ActionDrops metadata and drain it safely. The equipment
   path returns child gateway envelopes; attach each award exactly once, with
   independent AMF objects so Ruffle does not receive shared AMF0 references.
   Do not emit the same foundBushel in child data and metadata.
6. Verify seed count/crafting inventory initialization and world reload against
   `TInitUser`; preserve the existing global crafting-state design. Home-only
   scope must not change bushels or charges in another world.

Required tests before browser acceptance: 49/50-plot boundary, separate seed
counters, mastery thresholds, supercrop recognition, normal and equipment
harvest, retry without a second grant, immutable too-early/forged/foreign-world
rejections, capacity 399/400 and imported upgrades, duplicate/malformed stacks,
free-stall gift exactly once, persisted counters/inventory after init and JSON
reload, and a mixed AMF batch retaining its accepted sibling. Add AMF roundtrip
coverage for numeric-and-named ActionDrops properties, then verify that exact
envelope with the real client on a fresh synthetic landscape farm.

## Reproduction commands

From the FarmVillage root, copy the SWF first; the disassembler writes its parse
cache beside the copy:

```sh
mkdir -p /private/tmp/fv-bushel-inspection-20261024
cp embeds/Flash/v855097-855094/FarmGame.swf \
  /private/tmp/fv-bushel-inspection-20261024/FarmGame.swf
LocalData/venv/bin/python -I macOS/Scripts/client-inspection/abcdis.py \
  /private/tmp/fv-bushel-inspection-20261024/FarmGame.swf dis \
  'BushelReport|CraftingManager.(handleBushelFound|recordBushelFound|getNewBushelBonusAdders|firstMarketStallDialog)|FirstMarketStallWindow.(getFirstMarketStallSeenFlag|setSeenFlag|<cinit>)|CraftingState.initCraftingStateFromInitUser|SeedItem.isSuperCrop|FarmGameSettingsManager.getWorldBushelChanceScale'
```

The scratch evidence from this session is under
`/private/tmp/fv-lamb-rename-20261024/bushel-*.txt` and
`plot-harvest.txt`. It is method disassembly/data inspection, not browser proof.
