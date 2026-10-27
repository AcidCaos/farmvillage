> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../ACCEPTANCE.md), [current world scope](../../../WORLD_READINESS.md) and [the continuation backlog](<../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Paid building actions restored on 2026-10-24

`paid_buildings.py` restores the bounded original paid construction, material expansion, flower feeding and flower replacement paths. It uses the owned saved object, its current material counts and its archived catalog entry. Client snapshots can contain an already advanced level or completed appearance; they cannot supply the price, progress, replacement item, contents or position for a paid action.

## Restored behavior

- `CompleteNow` purchases exactly the missing material units with their catalog Farm Cash prices. The existing construction slice covers the classic Turkey Roost, Orchard, England Sheep Pen, England Combine/Garage and original horse stables. Whole-stage and selected-material purchases preserve other progress, occupants and imported metadata. Legacy horse-stable and Turkey Roost dialogs send this action; generic construction dialogs use the separate `TransformBuilding` action.
- `ExpandWithCurrency` purchases exactly the next saved material stage. Each material uses its own original market and price: Farm Cash uses `cash`; other currencies use `cost`. A world-currency purchase changes only its saved `worldCurrencies[currency].total`, preserving the rest of that record. Every currency is checked before any charge.
- Both actions can feed the reviewed flower family. All 172 UpgradeManager source records have one five-unit `part_flowerfood` stage, authored level 2 and capacity 0. The 86 bulbs start at level 1. On completion, 84 replace themselves with their authored single-bloom item; `purplepetunia_bulb` and `royalbluebell_bulb` retain their names. The new feeding stage activates the withering component and resets `plantTime` to server time. Feeding does not grant a friend-feed reward or gift.
- `upgradeBuilding` requires a fully fed flower. All 172 original source records replace themselves with their authored full-bloom target. Prices are read per item: 149 cost 3 cash, 6 cost 2, 6 cost 7, 4 cost 4, 4 cost 6, 2 cost 1 and 1 costs 5. Upgrade preserves the object ID, position, clock and imported metadata and sets the new state to `bare`; it grants no XP.
- The unambiguous single-material flower bulk-gift completion consumes the exact missing quantity from the saved Gift Box and charges no cash. Quantities and gift metadata use the existing construction/storage withdrawal rules. A multi-part combined-gift packet is refused because its original sender communicates a Boolean without its actual quantity while the constructor removes that quantity for every current material.

These methods validate and mutate a detached save. The signed-AMF transaction sequence retains the last 256 responses, survives server restart and cannot be reused for another request. Login clears sequence history because Flash restarts its sequences. The callback is a non-null object containing the owned ID, allowing the original transaction completion callback to run. Transient response data is excluded from saved files and initialization responses.

Ordinary moves preserve paid flower identity, progress and timers. A stale bulb snapshot cannot undo a paid full-bloom replacement or change its saved clock.
New flower placements use the catalog's initial stage and a server-owned clock.
A gifted bulb therefore starts at level 1 with no food, while a gifted
single-bloom item retains its authored initial level 2. Incoming placement
snapshots cannot import feeding progress, capacity, contents or a ready clock.

## Original-client evidence

The bytecode was inspected from a scratch copy of the bundled `FarmGame.swf`; source assets were not edited.

| Method | Recovered contract |
| --- | --- |
| `TCompleteNow.perform` 44969 | World action `CompleteNow`, options `partName`, `isGift`, and optional forced `currency="cash"`. |
| `TCompleteNow.<init>` 44968 | `isGift` means a combined count greater than one; constructor removes that count of gifts for every current material. |
| `HorseStableWithdrawal.onCompleteNowAcceptCallback` 33418; `TurkeyRoostExpansionWithdrawal.onCompleteNowAcceptCallback` 64163 | Optimistic completion followed by a whole-stage `TCompleteNow` request and local cash debit. |
| `StorageBuilding.getCashNeeded` 12000 | Missing count times each material's Farm Cash price. |
| `FeatureBuilding.frictionlessExpand` 22412 | Advances locally, then sends forced-cash `TCompleteNow`. |
| `ExpandFManager.buyExpansionWithCurrencyOrCash` 45061; `getPriceForExpansion` 45062 | Group missing material prices by authored currency before local debit and `ExpandWithCurrency`. |
| `ExpandFManager.completeExpansionLevel` 45045; `FeatureBuilding.witherer/get` 22337 | When feeding activates the level-2 witherer, reset the owner's clock to world time. |
| `ExpandFManager.conditionallySwapOnFullyExpanded` 45054; `FeatureBuilding.shouldCopyPlantTimeWhenReplacing` 22235 | Use authored `finishedName`; retain identity, metadata, position and the newly reset clock. |
| `UpgradeManager.<init>` 45491; `upgradeCallback` 45493 | Read authored target/cost, debit Farm Cash, retain identity/position/metadata and replace the saved flower. |
| `Transaction.onAmfComplete` 1187 | The transaction's `onComplete(data)` requires non-null response data. |

Research artifacts are in `/private/tmp/paid-*-20261024.txt` and `/private/tmp/paid-review-*.txt` for this run.

## Remaining explicit refusals

`HarvestReadyNow` now supports the original Herb Garden's functional deterministic harvest through `building_harvest.py`, at its authored 5-cash price. Readying grants no reward; the following normal harvest grants the original seed quantity or all-mastered coin fallback. Earned seed units are usable by ordinary planting. See [HERB_GARDEN_HARVEST_2026-10-24.md](HERB_GARDEN_HARVEST_2026-10-24.md).

The other 66 priced entries remain refused before payment: 64 `LootableFixedFeatureBuilding` records require absent server loot tables, `xoa_lostpalace` is a runtime community/charity building without a normal harvester, and `building_xaf_safarilodge` is absent from the catalog. A positive price alone is insufficient to sell an unusable timer advance. The per-item audit and exact evidence are linked from the Herb Garden document.

Expansions outside the existing classic construction and reviewed flower family remain refused, including reward-bearing replacement, award, runtime-gated and experiment-gated stage families.

### Flower harvest boundary and presentation

Ordinary `harvest` explicitly refuses all 258 catalog `FeatureBuilding` blooms.
An independent signed-AMF review found that the generic harvest branch paid the
flower's 360 coins repeatedly without advancing its protected saved timer. The
guard now refuses before a reward, clock, quest or receipt change, including on
the early and mature full-bloom stages. Feeding and paid replacement remain
the separate supported actions described above.

This family is separate from the missing `LootService.fetchLoot` tables. The
full-bloom catalog names the backend `HarvestRewardGenerator`, a `chance="5"`
and a bulb reward. The client contains its response consumer rather than that
generator's draw implementation: `HarvestFManager.onHarvestComplete` (45355,
bytes 424–760) reads `rewardItem` and `numRewards` from the server response before
adding the gift. A bare chance value does not establish its authoritative draw
semantics. The ordinary timer contract is known: `FeatureBuilding.harvest`
(22351) delegates to `SimpleHarvestableResource.harvest` (8407), which queues
`THarvest` before resetting state and `plantTime` (bytes 382–412). Paying only
the generic coin yield would leave this reward contract incomplete.

`paid_buildings.client_item_projection` removes only `HarvestFManager` from the
derived client definitions of these blooms. It preserves every other field and
the feeding, paid-upgrade, withering and image-progression components; raw
catalogs remain unchanged. `FeatureBuilding.attachFeatureManagers` (22245)
constructs only listed components. `isHarvestable` (22311, bytes 172–191)
returns false without the harvester, `isReadyForHarvest` (22259) requires that
result, and `onClick` (22256) checks readiness before scheduling `AMHarvest`.
The base harvest (8407) and `CHarvestBlooms.canHarvest` (28677) recheck
harvestability. `BloomProgressionFObject.setProgression` (58947) does not
dereference a harvester, so its remaining artwork path is retained. Exact
original listings are preserved in
PaidFlowerHarvestEvidence20261024 (`PaidFlowerHarvestEvidence20261024/`; external/private historical reference, not included in this source export).
This is source-backed invitation suppression; its original-client visual check
remains separate.

## Verification

Dedicated unit tests cover all 172 authored flower replacements and all 86 bulb feeding stages, saved material prices, mixed-currency rollback, gift quantities/metadata, strict parameters, replay/reload and growth clocks. Dedicated signed-AMF tests exercise real gateway dispatch, callbacks, durable saves, stale moves, rollback within mixed batches, all seven upgrade price families, paid feeding and gift feeding. Existing construction tests are also rerun.

The final placement regression submits a gifted bulb with forged completed
feeding and a zero clock through signed AMF. Placement resets those fields;
the premature upgrade is refused, then the ordinary five-cash feeding and
three-cash full-bloom upgrade both succeed. This closes a separately reproduced
placement bypass without charging a gifted, already single-bloom item for food.
The resulting paid-building batch passed all 25 unit and signed-AMF tests in
24.987 seconds (`/private/tmp/paid-flower-placement-final-tests-20261024.log`).
The subsequent flower-harvest guard and client-projection batch passed all
27 tests in 24.713 seconds, including repeated signed-AMF harvest refusals with
unchanged balances, clocks, owned objects, saved paid receipts and disk files.
The projection check covers all 258 bloom rows and preserves their other
components. Its log is
PaidFlowerHarvestEvidence20261024/focused-tests.log (`PaidFlowerHarvestEvidence20261024/focused-tests.log`; external/private historical reference, not included in this source export).

The construction compatibility batch passed 51 tests in 37.958 seconds (`/private/tmp/paid-buildings-final-tests-20261024.log`). The final combined paid-building, Herb Garden and cottage batch passed 104 tests in 33.570 seconds, including the added generic-action forgery regression. The final log is `/private/tmp/crafting-paid-herb-final-20261024.log`. A separate 82-test batch covered ordinary seed, storage, shared farming-loop and equipment compatibility in 36.584 seconds (`/private/tmp/building-harvest-paid-final-20261024.log`).
