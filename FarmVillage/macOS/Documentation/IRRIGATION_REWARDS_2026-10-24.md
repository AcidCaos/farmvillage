> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../ACCEPTANCE.md), [current world scope](../../../WORLD_READINESS.md) and [the continuation backlog](<../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Well and authored irrigation reward persistence

`irrigation_rewards.py` now mirrors the original well rewards and authored
`UserRewardUtil` irrigation grants into the existing per-world water ledger.
`engine.add_water` validates whole finite nonnegative values and preserves extra
fields on imported balances. The existing watering reductions, package-use
acceptance rule and fuel behavior remain in place.

## Original client and catalog evidence

All disassembly was generated from a scratch copy of FarmGame.swf, SHA-256
`1edea7cbecefcb1e1233da207164942f0088a83b87afc9254850f5fcde5034ae`.
The original compressed item and game settings catalogs were read unchanged.
`HarvestWaterEvidence20261024/` preserves the relevant method listings and the
exact two-item catalog summary.

| Item | Code | growTime | Seconds at the original 82,800-second day | Water at expansion levels 2/3/4/5/6/7 |
| --- | --- | --- | --- | --- |
| bldg_irrigationwell | ni9 | .69 | 57,132 | 50 / 125 / 190 / 240 / 280 / 310 |
| bldg_irrigationwell_8hr | ZWX | .334 | 27,655.2 | 25 / 62 / 95 / 120 / 140 / 155 |

Both catalog items use `FeatureBuilding` and `WaterHarvestFManager`, start at
expansion level 2, and have rewardMultiplierOverride 1. Their authored reward
prerequisites compare `expand.storageLevel` with backend `expansionLevel`; an
unsupported level has no guessed fallback reward. The existing growth helper
uses the actual game settings for duration instead of changing timers.

`WaterHarvestFManager.canAcceptHarvestReward` (45535) rejects the entire well
harvest if current water plus its level reward exceeds 2000. At exactly 2000 it
succeeds. `UserRewardUtil.grantUserReward` (7125), by contrast, passes authored
irrigation value directly to `IrrigationManager.addWater` (24630), whose generic
branch has no cap. Therefore generic quest rewards may take an imported balance
above 2000; a well still refuses until its entire award fits. The quest reward
quantity is not multiplied into the irrigation value.

`SimpleHarvestableResource.<init>` (8384) sets a new object's plantTime to the
current world time. Its `harvest` (8407) queues THarvest before resetting state
to bare and plantTime to world time. `FeatureBuilding.setState` (22297) maps
built to bare; `onBuilt` (22318) does not replace the initial clock. New well
placement therefore starts the current server timer at authored level 2, while
existing imported well clocks/levels are retained. An incoming move or harvest
snapshot cannot rewrite those saved fields.

## Server behavior

The well helper reads one unique completed owned well, its saved level and its
saved timer, then credits water and restarts that timer together in the existing
command savepoint. A fresh early request is visibly refused; a successfully
recorded same-sequence transport retry returns without another grant or quest
increment. Session receipts are reset on init and omitted from the client data.
A full store leaves both water and the original timer unchanged.

The quests decoder retains the original reward actionType and invalidates its
derived cache. The irrigation reward branch uses that actionType and authored
value. Generic addWater retains the original behavior of ignoring unconfigured
action stores; no new water feature is silently activated.

## Offline validation

`test_irrigation_rewards.py` checks every authored reward tier, new-placement
clock/level authority, imported balances and metadata, absent world balances,
invalid numeric values, preserved imported fields and session reset.
`test_irrigation_rewards_wire.py` was independently authored by the delegated
well test agent. Its 9 real-AMF tests cover both variants, saved level/timer
selection, forged snapshots, cooldowns, retries, whole-cap refusal, exact-cap
mixed-batch rollback, JSON/reload/init, and decoded quest grants above 2000.
The pre-existing `test_irrigation_fuel.py` checks unchanged watering/package and
fuel refusal behavior. Browser acceptance is recorded separately by the main
continuation verification, not inferred from these offline tests.
