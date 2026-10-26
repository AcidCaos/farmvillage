> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../ACCEPTANCE.md), [current world scope](../../../WORLD_READINESS.md) and [the continuation backlog](<../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Original pets restoration — 22 October 2026

Local source only. No Bifrost deployment or native application rebuild.

The bounded original puppy feature supports catalog-priced named purchases,
gender/color variant identity, catalog kibble bonuses, Gift Box feeding,
follow/move, timed adulthood, daily treat training, animation tricks, runaway
coin puppies and paid rescue. Original generic storage and reward-producing
fetch/harvest tricks reject explicitly because their complete state/reward
contracts have not been recovered. Pet Academy is a separate feature and is
not implemented here. Naming is purchase customization; no rename endpoint
was invented.

The historical catalog had retired every original puppy (`archived=yes`,
`buyable=false`), making the supported purchase flow inaccessible in Market.
The derived client catalog locally restores those two availability flags for
26 exact, paid, undated puppy variants. Prices, codes, requirements, limits,
bonuses and source assets remain unchanged; the three seasonal base variants
retain their historical date gates. This is an explicit local compatibility
restore, not a claim that the archived offers were still active. The normal
Market purchase opens the original naming/gender/color customization dialog.

## Recovered client contract

Evidence comes from the shipped `FarmGame.swf` and
`XML/gz/v855098/gameSettings.xml.gz`, not a substitute pet simulation:

- `TPetsPlace` uses `WorldService.performAction('place', save, [options])`.
  Options carry `petName`, `petGender` (`0` female, `1` male), and `petType`
  (the exact catalog code), with false/zero Gift Box and storage flags.
  `CustomizePets` limits names to 16 letters, spaces, dots and hyphens.
- `Pet.loadObject` reads `petName`, `petGender`, `petLevel`, `allowFollow`,
  `direction`, `lastFedTime`, `kibbleFedCount`, `isCash`, `hasUserSeenAdult`,
  `wasLevelResetOnLoad`, `levelStartTime` and `isRunAway`. Pet times are
  milliseconds. Server envelopes continue to use seconds.
- `TUseTargetedConsumable` uses action `use`, a `CPetsKibble` consumable
  snapshot and options `isGift`, `isFree`, `targetObjectId` (a string) and
  `targetUser`. Nonnumeric local farmer IDs serialize their own user as `"0"`.
  `consume_kibble` and `consume_treat` have no individual catalog sale price:
  this implementation consumes one owned Gift Box unit. The original
  `FarmService.buyConsumablePackage` path sells `pkg_kibble` (3 Farm Cash,
  one kibble) and `pkg_treat` (5 Farm Cash, seven treats), using catalog
  contents and durable request receipts. Both packages share catalog code
  `XX`, so the transaction must use their distinct names.
- `Pet.isAdult` requires fourteen real days for every puppy. Coin puppies
  also need fourteen kibble feeds; cash puppies mature by age. Feeding uses
  the original daily windows anchored at purchase/training start.
- `Pet.updateLevel` and `petData.levels` advance an adult from level 1 to 5
  after 1, 3, 3 and 7 daily treats. Missing a training day resets only the
  current level's progress. `rollover`, `playdead` and `shake` are the
  recovered animation tricks. Fetch/harvest rewards remain unsupported.
- `Pet.syncPosition` sends `x`, `y`, `direction` and `allowFollow` in `TMove`
  options. Client snapshots cannot overwrite name, gender, age or training.
- `TPetRunaway`, `TPetAdulthoodReached` and `TRescuePet` use world actions
  `runaway`, `adulthoodReached` and `rescuePet`. Rescue charges the catalog
  `pet_rescue` price (2 Farm Cash), once, and returns `lastFedTime` in
  milliseconds as the original callback expects.

## Persistence and verification

Each pet remains an individual world object. Input snapshots cannot replace
its identity, age, currency category or training progress. Generic storage
rejects pet transfers before losing those fields. Active-world ownership is
required for feeding and actions; catalog limits count inactive owned worlds
too. Per-session transaction receipts survive a server restart, reject reused
sequence numbers and retain a high-water mark when old receipts are evicted.
Fresh Flash sessions clear these receipts. The existing village transaction
rolls back the pet, currency, gifts and receipts together on failure.

The isolated `macOS/Tests/test_pets.py` suite exercises the real AMF gateway:
purchase prices/bonus, invalid customization and currency, durable replay,
first-world-action metadata, food ownership, daily windows, maturity/training,
follow, rescue, unsupported actions, cross-world replay, save reload, batch
rollback and the served puppy catalog. `test_client_catalog.py` compares every
derived record with the archive, allowing only expired-offer flags and the
26 exact puppy availability restorations. Tests import `test_persistence`
before product modules; all writes
use disposable saves. Run from the FarmVillage repository:

```sh
LocalData/venv/bin/python -B -m unittest discover -s macOS/Tests -p test_pets.py -v
```

## Browser acceptance entry points

- `goldenretriever_puppy_cash` / code `62`: 65 Farm Cash and 14 kibble.
- `bordercollie_puppy_red` / code `71`: 300,000 coins, one kibble, limit one.
- `terrier_puppy_honey` / code `7D`: 5,000 coins and one kibble; requires
  fifteen local neighbors and is limited to one.

Use the original market customization dialog to name/place a puppy, feed it
from its purchased kibble bonus, toggle follow, and reload to verify identity.
Browser acceptance is recorded separately by the main verification pass.
Automated timer tests do not certify the full adult lifecycle in the browser;
the fourteen-day adulthood timer and later daily training remain real timers.
