> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../ACCEPTANCE.md), [current world scope](../../../WORLD_READINESS.md) and [the continuation backlog](<../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Home bushel persistence restored

Implementation: `bushels.py`, with the harvest/init hooks in `commands.py` and
one outer `metadata.ActionDrops` envelope in `server.py`. This supersedes the
read-only implementation status in `BUSHEL_RECOVERY_2026-10-24.md`; that document
retains the original recovery detail. Browser acceptance belongs to the main
continuation verification record and is not claimed by these offline checks.

## Recovered behavior and bounded local policy

The original copied FarmGame.swf has SHA-256
`1edea7cbecefcb1e1233da207164942f0088a83b87afc9254850f5fcde5034ae`.
Disassemblies in `HarvestWaterEvidence20261024/` came from a scratch copy; the
served SWF and compressed catalogs were not patched.

The enabled simplified Bushel Report predicts a deterministic threshold
`int(K / (1 + masteryStars + superCropBonus))`. K defaults to 50, the catalog
SuperCrop flag contributes the original bonus of 3, and zero-based mastery
values -1/0/1/2 contribute 0/1/2/3 stars. Ordinary mature Home plots count one
harvest before the existing mastery award runs. The hot-parameter K override
is supported when it produces a positive whole threshold.

The original client does **not** prove the original server's overflow/reset
algorithm. The explicit local policy is to carry all fractional or blocked
harvest credit and deduct a threshold only for a bushel actually deposited.
A full inventory neither loses credit nor generates a free stall gift. After
space becomes available, a later accepted harvest can deposit that retained
credit up to available capacity. This policy is an implementation decision,
not a claim about the former server.

The original crafting XML sets ordinary stall capacity to 400. Larger imported
capacity, existing stack metadata, unrelated crafting state and legacy rows are
preserved. Only ordinary `CBushel` stacks consume this capacity; animal/tree,
lab, unsharable and village bushels keep their separate paths. Ambiguous
ordinary duplicates or unknown imported item codes fail before reward changes.
The initial template's duplicate seed-code SB placeholders are unrelated rows
and are preserved unchanged.

The first actual stall bushel mirrors the client's free `marketstall` (ms)
gift. An existing gifted/placed catalog `MarketStallBuilding` or the client's
`FirstMarketStall` seen flag prevents another gift. The server does not fabricate
that seen flag, shared rewards, market stall listings or social reward URLs.

This first restored path covers ordinary Home crops with supported stall
bushels. SuperPlots, non-unit harvest multipliers, active gain buffs and
unrecovered Home boost configurations are refused rather than assigned guessed
awards. Other worlds and special bushel types continue their existing paths.
No grow clock or fuel behavior changes.

## One award route, including equipment

The response is an AMF Object with numeric string properties and named fields:

```text
metadata.ActionDrops.bushelReport.dropTypeFuncResult
  "0".."length"-1 -> {foundBushel: {bushelCode, bushelsAddedToInventory,
      bushelsAddedToSharedReward: 0, bushelAddedToStall: false}}
  length -> number of award records
  newHarvestQuantities -> [{itemCode: seedCode, quantity: remainingCredit}]
```

Counter-only harvests send length 0 and the authoritative quantity. The same
award never appears in `data.foundBushel`.

Further bytecode recovery resolved the equipment metadata question:
`TFarmTransaction.onAmfCompleteSteps` (1206) captures the prior rawResult's
ActionDrops and overwrites the next child's ActionDrops with it;
`TEquipmentAction.onComplete` (24849) reuses the same transaction for children;
`TWorldState.onMultiComplete` (9295) calls child callbacks without a completion
event; `TransactionManager.onAmfBatchComplete` (812) emits one network
transaction completion after the callback finishes. Therefore the server keeps
child metadata empty, aggregates all equipment bushel records in the outer
metadata, and drains pending records only once. Per-child award envelopes would
be overwritten and cannot safely replace that aggregate.

The durable counter is `seedHarvestCountsSinceLastBushelDrop`. The helper's
`_bushelResponse` is transient and drained before persistence, omitted from init
and cleared on a fresh init. Existing per-command savepoints roll back failed
equipment sweeps and preserve earlier successful batch siblings.

## Offline validation

`test_bushel_harvest.py` verifies threshold/mastery/SuperCrop behavior, capacity,
credit retention, legacy row preservation, first-stall gifts, rejection without
partial mutation, and numeric-plus-named AMF fields.
`test_bushels_wire.py` exercises real catalog items, the Flask AMF gateway,
individual/equipment award envelopes, retries, batch rollback, durable JSON and
reload/init. No production save, network service, archive or client binary is
written by these tests.
