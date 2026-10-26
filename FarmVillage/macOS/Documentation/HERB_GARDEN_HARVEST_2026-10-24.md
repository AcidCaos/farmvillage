> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../ACCEPTANCE.md), [current world scope](../../../WORLD_READINESS.md) and [the continuation backlog](<../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Original Herb Garden harvest and the other instant-harvest families

`building_harvest.py` restores the deterministic Herb Garden reward, its paid timer advance, and usable saved herb seeds. The other priced harvest families were audited individually. priced-building-audit.csv (`HarvestReadyNowEvidence20261024/priced-building-audit.csv`; external/private historical reference, not included in this source export) accounts for all 67 CMS prices.

## Functional Herb Garden

The original CMS feature gives ten ordered seeds: Thai Basil, Thyme, Rosemary, Marjoram, Parsley, French Tarragon, Oregano, Sorrel, Shiso and Cilantro. `SeedDispenserManager.getActiveSeed` (57599) selects the first eligible seed whose three mastery levels are unfinished. `SeedDispenserHarvestFManager.harvestReward` (45394) returns that seed's authored package. The server uses the same saved zero-based mastery levels and the same server-configured `fv_herbgarden` variant 3; the client cannot choose a later seed or quantity in a harvest request.

| Saved garden level | Archived size key | Seed units per harvest |
| --- | --- | ---: |
| 1 | CSeedPackageSize | 20 |
| 2 | CSeedPackageSize_100 | 100 |
| 3 | CSeedPackageSize_200 | 200 |
| 4 | CSeedPackageSize_400 | 400 |
| 5 | CSeedPackageSize_600 | 600 |
| 6 | CSeedPackageSize_900 | 900 |

The first key's actual CMS value is 20. It does not use the default value from a different seed-package handler. When every herb has all three mastery levels, `getHarvestAmount` (45393) returns the authored 1,500-coin fallback with multiplier `oneFixed` (45361).

The garden retains its original one-game-day grow time (82,800 seconds with the archived settings). New placements start at level 1 with a server-owned clock. Moves and other ordinary snapshots preserve saved state, timestamps, level, materials and imported metadata. Plot-only actions such as `clearWithered` and `plow` cannot reset or create a garden. Paid readiness and harvest change the owned object through their own validated handlers.

`HarvestReadyNow` uses the authored `herbgardenHarvestReadyNowCashPrice=5`. The paid action validates the owned completed garden, saved level, mastery and inventory, refuses an already ready garden, pays once and sets the original ready clock. It grants no seeds or coins. The following normal `harvest` grants the deterministic reward once and restarts the original timer. Duplicate request receipts survive server restart; login resets Flash sequence history. A subsequent fresh harvest before the next growth interval is refused.

`Player.refreshGiftBox` (4154) and `addGiftData` (3950) route `CSeedPackage` items from saved Gift Box storage into `Player.seeds`. The server therefore stores seed **units** under the package code in `storageData["-1"]`. `Player.useSeed` (3959) and `Plot.plant` (21806) automatically consume one seed before considering a market purchase. The server mirrors that behavior for the ten reviewed herbs: saved seeds bypass the currency charge, lose exactly one unit, retain imported sender data and trim unit metadata with `StorageItem.adjustQuantity`. The planted crop still earns its authored plant XP and receives a real server timer. Ordinary seeds and explicit gift/storage withdrawals continue through their existing paths.

This does not restore the Herb Garden's separate in-app-purchase expansion progression or arbitrary seed-dispenser families.

## Why the other 66 prices cannot be charged faithfully

There are 64 priced catalog records of class `LootableFixedFeatureBuilding`. Every record contains a distinct `dialogs/dialog/harvestLootKey`; examples are `springfairBuildableLoot` and `africaSafarilodgeBuildableLoot`. None of those 64 keys occurs in any bundled `.xml.gz` file. Their only local catalog occurrence names the remote table. The inline expansion `rewardItem` fields describe stage-completion rewards and do not define repeat-harvest loot.

The exact original dependency is external: `LootableFixedFeatureBuildingWithdrawal.initPotentialLoot` (39491) constructs `TFetchLoot` with that key. `TFetchLoot.<cinit>` (57212) names `LootService.fetchLoot`, and `perform` (57214) sends the signed request. `onComplete` (57215) reads the server's `lootItems` response. `LootItem.loadObject` (57205) reads each returned item, quantity and rarity. The client SWF contains the request, parser and presentation, rather than the table entries or authoritative draw weights. The 24 bundled files under `xml/` contain no recovered responses for these tables. A historical server response dataset or server implementation is required to establish their original repeat rewards; assigning expansion prizes, uniform odds or guessed rarity probabilities would fabricate the economy.

`xoa_lostpalace` is the 65th unresolved catalog record. It has `growTime=0`, no harvester component and a runtime `upgradeMax`. `RuntimeDrivenLootableFixedFeatureBuilding.getExpansionLevelFromRuntime` (34266) reads server `flashHotParams`. Its CMS runtime configuration names charity/community milestones and level rewards, which do not define a repeat harvest. The stray price does not establish one.

`building_xaf_safarilodge` is the remaining CMS name with no catalog item. It cannot be treated as an alias for `xaf_safarilodge` without source evidence.

All these unsupported paid timer actions refuse before withdrawal. The normal harvest path also refuses these priced unsupported families rather than discarding a clock for an empty reward.

## Reproducible sources and checks

| Source | SHA-256 |
| --- | --- |
| items_opt.amf | 14987fd4c07f9de35ff5092aeab58584802fd7fbeca1131ad1a5e3eee381a4d7 |
| gameSettingsCMS.xml.gz | 2153a81311632e5697b6e10fb40be729bbd87ed1719554bc7fdf0ef8934fb43d |
| gameSettings.xml.gz | c1fa55f130c4942ea978b07168b37285389d36e30fce30fc30647deff5e5e11b |
| Original FarmGame.swf | 1edea7cbecefcb1e1233da207164942f0088a83b87afc9254850f5fcde5034ae |

The original client was copied to `/private/tmp/FarmGame-crafting-finish-20261024.swf` for read-only disassembly. Detailed research files are `/private/tmp/paid-herb-*-20261024.txt` and `/private/tmp/paid-harvest-*-20261024.txt`.

The dedicated eight unit tests and five signed-AMF tests passed in 16.678 seconds (`/private/tmp/herb-garden-final-20261024.log`). They cover every saved package size, all ten mastery choices, the coin fallback, paid ready followed by a separate harvest, saved-seed planting at zero coins, reload/retry, placement clocks, forged clock actions and initialization metadata. The final combined paid-building, Herb Garden and cottage batch passed 104 tests in 33.570 seconds (`/private/tmp/crafting-paid-herb-final-20261024.log`). A separate 82-test batch covering ordinary seed, Gift Box, farming-loop and equipment compatibility passed in 36.584 seconds (`/private/tmp/building-harvest-paid-final-20261024.log`).
