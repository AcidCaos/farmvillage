> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../../ACCEPTANCE.md), [current world scope](../../../../WORLD_READINESS.md) and [the continuation backlog](<../../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Next world: Lighthouse Cove

Checked 2026-10-22. Lighthouse Cove (`fisherman`) is now a bounded local source candidate following Meadows' ordinary-farming browser checks. This document records the recovered contract; current browser evidence and remaining gates live in `STATUS.json`. Story remains deferred. No deployment, native build, simulator run, commit, push, or real-player-save edit was performed in this work.

Winter Wonderland has fewer recovered items and special systems, but its preserved free access chain ends on 18 February 2012. Cove's preserved free access has a start date and no end date. A new Winter unlock at the current date would therefore bypass an original rule. Already-unlocked Winter imports are a different future scope and must retain their snapshots.

## Primary sources and reproducibility

All paths below are relative to the FarmVillage repository. The `.gz` XML and manifest files use **zlib**, not gzip framing.

| Original input | SHA-256 |
| --- | --- |
| `xml/gz/v855098/gameSettings.xml.gz` | `c1fa55f130c4942ea978b07168b37285389d36e30fce30fc30647deff5e5e11b` |
| `xml/gz/v855098/gameSettingsCMS.xml.gz` | `2153a81311632e5697b6e10fb40be729bbd87ed1719554bc7fdf0ef8934fb43d` |
| `xml/gz/v855098/worldSettings.xml.gz` | `769db5f72b5586b036792332c9c9c89dac43ca6ae2fc6f5ddb761d829d1c014e` |
| `xml/gz/v855098/yimf.xml.gz` | `6a4756dcdc6f701628a51e2b1e1c6e26467735df5011c758b272241669af9065` |
| `xml/gz/v855098/terrain.xml.gz` | `521130a19bc9dd8b9e05f31db11ba51debf2e4bd48d076cd769d84506cea6318` |
| `xml/gz/v855038/items_opt.amf` | `14987fd4c07f9de35ff5092aeab58584802fd7fbeca1131ad1a5e3eee381a4d7` |
| `embeds/Flash/v855097-855094/FarmGame.swf` | `1edea7cbecefcb1e1233da207164942f0088a83b87afc9254850f5fcde5034ae` |

The local decoded catalog `LocalData/cache/gz_v855038_items_opt.json` records the same original AMF source hash. Definitions were read from that cache without rebuilding it. Scenery paths were resolved through both original manifests, `assethash/v9/assethash.master.amf.gz` and `xml/gz/v855098/assethash.min.amf.gz`, then checked for nonempty files in `LocalData/assets`.

No target-class `.as` export was found in the workspace or temporary/decompiler directories. Exact method bodies were inspected directly from the preserved original SWF using the existing standard-library script `/private/tmp/inspect_fv_abc.py`; this does not patch or run the client. Inspect these original classes/methods again when extending the scope:

| Original method | Method ID / original source reference | Recovered behavior |
| --- | --- | --- |
| `TExpansionWorldAccess` static initialization and `perform` | 11713, 11715; `Transactions/TExpansionWorldAccess.as:120,475` | Exact service `FishermansCoveService.unlockFishermanWorld`; send `accessType`, then optional `optionId` only when present. Supported all-access arguments are `["allAccess"]`. |
| `ExpansionData` constructor | 11617; `Classes/ZItem/ExpansionData.as:226` | Missing currency attribute defaults to `Currency.COINS`; default world requirement is the expansion's own name. Cove has no Home requirement override. |
| `WorldManager` static initialization | 2635; `Managers/WorldManager.as:205,207` | Signed storage IDs: Cove `-9`, Winter Wonderland `-10`. The disassembly prints unsigned `pushbyte` operands 247/246; AVM2 interprets these as signed bytes. |
| `WorldManager.getMaximumPlotsAllowed` | 2680; `Managers/WorldManager.as:1101` | Lookup by the current grid width, then terrain code. |
| `ExpansionPlotLimits.getPlotLimitByTerrainCode` | 9350; `Classes/ZItem/ExpansionPlotLimits.as:290` | Exact width lookup; missing width/group returns zero. Never interpolate or inherit Home's limit. |
| `FarmGameWorld.loadObject`, `completeWorldLoad` | 5477, 5480; `Classes/FarmGameWorld.as:381,502` | Explicit snapshot `tileSet` selects the Yimf map/background. Without an explicit terrain array, construct `YimfMap(sizeX,sizeY,tileSet,true)`. Missing tileSet otherwise defaults to grass. |
| `TerrainUtil.getTerrainCode` | 9332; `Classes/Terrain/TerrainUtil.as:82` | A `YimfMap` uses default terrain code `0`; explicit terrain maps have their own codes. |
| `FarmGameWorld.initPlotLimitCounts` | 5483; `Classes/FarmGameWorld.as:551` | Count every plot object, regardless of planted/fallow/withered state; do not count only currently planted crops. |

Temporary disassembly evidence: `/private/tmp/next-world-original-contract.txt`, `next-world-original-terrain.txt`, `next-world-original-plot-terrain.txt`, `next-world-original-yimf.txt`; existing `/private/tmp/travel-world-access.txt` and `creative-world-rules-client.txt` also contain the exact methods. These temporary files are convenient evidence, not required runtime inputs.

## Cove contract

| Rule | Exact recovered contract | Implementation consequence |
| --- | --- | --- |
| Access | `expansions/expansion[@name='fisherman']/allAccess` checks `fv_fisherman_all_access`, which delegates to `fv_fisherman_general_access`. That AND requires level 15, `has_not_unlocked_world=fisherman`, and `start_time=9/19/2011`. No end date. | Enforce level/date once; repeated requests reuse the existing durable snapshot and do not regrant. Reject an imported unlock/summary/inventory without its snapshot instead of resetting it. |
| Price/reward | `generalAccess` and `allAccess` have no price attributes; each grants only `world_unlock=fisherman`. `earlyAccess` is a different original option: 55 Farm Cash, item `0iS`, and world unlock. | Implement free `allAccess` alone. Do not grant the early-access animal or shipping license. Do not label 55 Farm Cash as the all-access price. |
| Initial state | CMS `farmSize=50`; no original `startingFarm` reference, populated starter, object coordinates, port placement, or construction grants recovered. | An empty 50×50 local reconstruction must be disclosed and marked locally. It is not an original starter. Preserve imported snapshots. |
| Theme | `yimf[@type='fisherman']`, `tileClass=cove`, weights `5,10,20,25,30,35,40,45,50,51,56,61,66,71,76,81`. Background prefix `assets/Environment/xcove_themeBackground_`; horizon `assets/Environment/xcove_theme.swf`. | Store `tileSet=fisherman`; never silently substitute `grass_theme`. Current empty candidate uses the Yimf fallback. Original shoreline/buildable bounds are unresolved; do not fabricate shoreline/water arrays or claim full terrain parity. |
| Colors | `bgColor=0xFF6E8422`, `outlineColor=0x617519`, `expansionColor=0x3A6F29`, `skyColor=0xFF6F65C8`. | Preserve original scenery configuration. |
| Item/crop requirements | Cove has no `worldRequirementOverride`. Original World requirements retain `all`/`any` semantics. A Home-only requirement does not match Cove. | Gate purchases, gifts, inventory withdrawal, placement and harvest; reject unsupported mastery/quest/license/experiment/other requirement classes. |
| Terrain sets | `gameSettings/terrains` maps `default=0`, `land=1`; hierarchy says land contains default. `amphibious`, `plowable`, `all` are ancestors of default. | Ordinary Yimf ground accepts a terrain set containing default or an ancestor. Water/shoreline/terrace-only items fail. Specialized plots/custom terrain stay unavailable. |
| Currency/score | Cove expansion has no `currency`, `score`, `score2`, or score-file attribute; original `ExpansionData` defaults currency to coins. | Retain ordinary coins/Farm Cash accounting; never synthesize a world currency or score. Check each catalog price, dates, level and purchase requirements. |
| Inventory | Original `FISHERMAN_INVENTORY_ID=-9`. `hatchstorage` (`v0`, `InventoryCellar`) explicitly includes Cove, level 16, cost 1 coin, capacity 1250, limit 1, disallow-delete; `storage_world_locks` explicitly allows Cove. | Durable separate inventory `-9`; ordinary building contents remain keyed by object identity. Travel/reload and blocked cross-world withdrawal still need integration/browser proof. |
| Shipping | Expansion names `pkg_fishermanXfer`; raw catalog package costs 75 Farm Cash, uses `consume_fishermanXfer` (`06x`), and grants `world_content_license`, `licenseType=world`, value `fisherman`. Visibility requires unlocked Cove and no existing world license. A coin package is `buyable=false`, cost 0, locked-hidden-price. | Unlocking Cove does not grant shipping. Reject unsupported shipping and license transactions rather than charging or transferring. |
| Expansion-added objects | `gameSettings/farmExpansions` contains **no** `world[@name='fisherman']` record. | No configured expansion-added Cove objects; never copy Winter's treasures, Home grants, or an invented port. |
| Special systems | `fishermanscove` (`.d`, `FishermansCoveBuilding`) is a nonbuyable, limit-one feature building with storage/harvest/expand components. Upgrades 2–11 need 3/5/10/15/20/25/30/40/50/60 each of stone/log/steel-beam parts. Level 11 conditionally awards `consume_fishermanXfer`. Cove crafting cottage `xcovecraftingcottage` (`^2`) uses `CraftingCottageBuilding`. | No port, crafting, feature-building, specialized-plot or vehicle interaction may use a generic farming fallback. Keep these unavailable until their own durable contracts are implemented. An empty local farm receives none of them. |

### Plot cap and expansion sizes

The archive has the following exact width→plot caps. Initial 50×50 land permits **35** plots.

| Width | Plots | Width | Plots | Width | Plots |
| --- | --- | --- | --- | --- | --- |
| 50 | 35 | 122 | 225 | 194 | 835 |
| 58 | 45 | 130 | 255 | 202 | 915 |
| 66 | 60 | 138 | 315 | 210 | 995 |
| 74 | 75 | 146 | 375 | 218 | 1075 |
| 82 | 95 | 154 | 435 | 226 | 1155 |
| 90 | 115 | 162 | 515 | 234 | 1240 |
| 98 | 140 | 170 | 595 | 242 | 1325 |
| 106 | 165 | 178 | 675 | — | — |
| 114 | 195 | 186 | 755 | — | — |

Original expansion catalog names are `xlcfarm{size}` and `_cash`, where `squares=4*size+2`. `xlcfarm12` (50) is nonbuyable. The next expansion must be the next exact width, retain square land, enforce its own world requirement, gates, level and neighbors, and be atomic/idempotent. Raw prices below are evidence; the original `ChangeFarmItem.saleCash`/`TExpandFarm` path charges **1 Farm Cash** for a cash `expand_farm` offer, as already recovered for Meadows. Do not charge the raw cash field while claiming parity with that client.

| Size / width | Raw coin cost | Raw cash field | Coin experiment gate | Cash experiment gate |
| --- | --- | --- | --- | --- |
| 14 / 58 | 25,000 | 30 | `fv_fisherman_farm34` | none |
| 16 / 66 | 125,000 | 40 | `fv_fisherman_farm16` | none |
| 18 / 74 | 225,000 | 50 | `fv_fisherman_farm18` | none |
| 20 / 82 | 325,000 | 60 | none | none |
| 22 / 90 | 425,000 | 80 | none | none |
| 24 / 98 | 525,000 | 100 | none | none |
| 26 / 106 | 625,000 | 120 | `fv_fisherman_farm26` | none |
| 28 / 114 | 725,000 | 145 | `fv_fisherman_farm28` | none |
| 30 / 122 | 825,000 | 170 | `fv_fisherman_farm30` | none |
| 32 / 130 | 925,000 | 195 | `fv_fisherman_farm32` | none |
| 34 / 138 | 2,000,000 | 200 | `fv_fisherman_farm34` variant 1 | `fv_expansion_LC_34x34` variant 1 |
| 36 / 146 | 3,000,000 | 200 | `fv_lighthouse_36coin` | `fv_expansion_LC_36x36` variant 1 |
| 38 / 154 | 4,000,000 | 200 | `fv_lighthouse_38coin` | `fv_expansion_LC_38x38` variant 1 |
| 40 / 162 | 8,000,000 | 200 | none | `fv_expansion_LC_40x40` variant 1 |
| 42 / 170 | 9,000,000 | 210 | none | `fv_expansion_lc_42` |
| 44 / 178 | 10,000,000 | 210 | none | `fv_expansion_lc_44` |
| 46 / 186 | 11,000,000 | 210 | none | `fv_expansion_lc_46` |
| 48 / 194 | 12,000,000 | 210 | none | `fv_expansion_lc_48` |
| 50 / 202 | 13,000,000 | 210 | none | `fv_expansion_lc_50` |
| 52 / 210 | no coin offer | 210 | — | `fv_expansion_ec_lc_hi_jf_52` |
| 54 / 218 | no coin offer | 210 | — | `fv_expansion_ec_lc_hi_jf_54` |
| 56 / 226 | no coin offer | 210 | — | `fv_expansion_ec_lc_hi_jf_56` |
| 58 / 234 | no coin offer | 210 | — | `fv_expansion_ec_lc_hi_jf_58` |
| 60 / 242 | no coin offer | 220 | — | `fv_expansion_ec_lc_hi_jf_60` |

`xlcfarm26` contains both `cost=625000` and `cash=120`; its absence of `market=cash` matters. All expansion codes are the historic placeholder `XX`, so lookup must use the offer name and exact world/size instead of treating the first code match as an expansion. Unprovided experiment variants are not permission to enable a gate. Later gated sizes can stay unavailable.

## Recovered asset availability

The inventory records 304 Cove and 191 Winter items with explicit World requirements; these are not complete content counts. Direct worldSettings UI references are 8/8 present for both. Three selected catalog icons per world are present. That limited inventory does not certify every asset or rendered state.

This pass also verified all Cove scenery variants: 25 backgrounds `xcove_themeBackground_{12,14,...60}.swf` plus the horizon, all mapped and nonempty. Examples:

| Logical asset | Local path | Bytes |
| --- | --- | --- |
| `assets/Environment/xcove_theme.swf` | `LocalData/assets/Environment/fcb15722bb73d2e36479e9313c7dac2a.swf` | 6,633 |
| `assets/Environment/xcove_themeBackground_12.swf` | `LocalData/assets/Environment/e0b8c9d20850640eda81f9b83d0f0557.swf` | 136,988 |
| `assets/Environment/xcove_themeBackground_14.swf` | `LocalData/assets/Environment/603ac37845290ca6f7169ff80bc198f3.swf` | 136,964 |
| `assets/Environment/xcove_themeBackground_60.swf` | `LocalData/assets/Environment/30ea7d3cab8442aa35de3fb99cd366ee.swf` | 150,892 |
| `assets/Environment/xww_theme.swf` | `LocalData/assets/Environment/48465bebe0844fda863af2987023a64a.swf` | 15,299 |
| `assets/Environment/xww_themeBackground_12.swf` | `LocalData/assets/Environment/5666d827b383ec8c3f56170fed0a32ad.swf` | 187,834 |

All 20 Winter background variants 12–50 and its horizon were likewise mapped/nonempty. Original-client scenery, tile palette, HUD, crop, construction and storage rendering still require browser acceptance; existence alone does not pass that gate.

## Winter Wonderland: preserve for later

The exact chain is `allAccess` → `fv_xww_all_access` → `fv_xww_general_access` → `fv_xww_access_shared` → `fv_xww_shared` (level 15) plus `has_not_unlocked_world=winterwonderland`. General access requires 5 December 2011 through 18 February 2012. Early access requires 28 November through 4 December 2011, costs 55 Farm Cash, and grants item `0Ft` plus world unlock. `fv_xww_preaccess` is 18–27 November 2011. No currently valid alternative new-unlock route was recovered.

Its correct tileSet is `winterwonderland`, tileClass `xww`, weights `18,36,54,55,56,57,58,59,60,61,62,62,63`, inventory `-10`, and no dedicated currency/score. Its plot caps at widths 50..202 by steps of 8 are `100,130,160,190,230,270,310,350,400,450,500,560,630,700,780,860,940,1020,1100,1180`.

Unlike Cove, Winter expansion-added construction objects are explicitly configured. Every entry has `z=0`, `state=construct_0`; preserve these exact codes and coordinates if implementing it later:

| Expansion width | Added objects `code@(x,y)` |
| --- | --- |
| 58 | `0uG@(44,4)`, `0uI@(0,48)` |
| 66 | `0vK@(4,48)`, `0uI@(56,0)` |
| 74 | `0uG@(5,40)`, `0up@(56,0)`, `0up@(2,60)` |
| 82 | `0uG@(73,2)`, `0vK@(54,4)`, `0uI@(0,8)` |
| 90 | `0uG@(68,2)`, `0vK@(4,76)`, `0up@(2,32)` |
| 98 | `0uG@(6,20)`, `0vK@(2,72)`, `0uI@(0,88)` |
| 106 | `0uG@(4,56)`, `0up@(88,4)` |
| 114 | `0uG@(88,4)`, `0vK@(4,82)`, `0uI@(0,16)` |
| 122 | `0uG@(6,60)`, `0up@(80,2)` |
| 130 | `0up@(2,92)`, `0uI@(116,0)` |
| 138 | `0uG@(4,28)`, `0up@(104,4)`, `0uI@(0,76)` |

No original populated Winter starter or original campaign was recovered. Its catalog has special construction, Sweet Shoppe crafting, breeding, storage, vehicle and Ice Palace systems; missing campaign counts do not make these non-story systems optional.

## Implementation and remaining acceptance

`cove_rules.py` provides checked read-only archive extraction, exact plot-cap lookup, snapshot/cap guards, an explicit basic-item boundary, terrain-set checks and an empty expansion-addition result. `creative_worlds.py`, `world_travel.py`, `server.py` and `templates/farms.html` now integrate the bounded free-access candidate. Its ten dedicated rules tests pass with:

```text
LocalData/venv/bin/python -B -m unittest macOS/Tests/test_cove_rules.py -v
Ran 10 tests in 0.867s — OK
```

Tests cover the 35-plot boundary across every plot state, last permitted plot, expansion cap increase, temporary-ID retry, forged class changes/special plots, wrong terrain/dimensions, unsupported imported special objects, archive drift, basic-item restrictions and untouched other worlds.

The integration now wires these checks through unlock/travel, ordinary single/batch/equipment actions and market-to-storage paths, exposes the recovered free all-access option, applies exact world expansions with current gates and prices, and retains per-world inventory, unique IDs, retries and rollback. Unsupported feature/shipping/crafting paths fail closed. New imports with special objects or custom terrain remain preserved but unavailable until their rules are restored.

Fresh shared-rule review also closed premature crop harvest, seed placement without paid plowing, forged animal/tree move cooldowns, unsupported purchase currencies, negative-inventory dispatch, foreign-world expansion offers, and protected-building deletion. Dedicated matrix tests cover the applicable Home/England/Meadows/Cove paths. Combined results are recorded separately in `STATUS.json`; focused suites overlap and must not be added as unique coverage.

Ordinary inventory admission now follows original `Player.as:1325–1390`: sum capacities from built inventory StorageBuildings on the active farm, clamp to `StorageEntity.limit` (1,250 for these four worlds), and count stored quantities. Multi-item deposits preflight the full quantity before payment or removal. Pink Tool Shed provides 15 ordinary slots. `InventoryCellar.as:127–130` limits cellar capacity to `min(base capacity, credits received)`; its raw 1,250 catalog value is only a ceiling. Cellar purchase prerequisites and protected deletion are restored, but its credit mechanism is not. Unsupported cellar/imported capacity contributes no assumed slots; existing data is preserved. Tests are in `test_inventory_capacity.py` and `test_cove_cellar.py`. Source-backed ordinary capacity is not a claim that cellar credits or storage expansion systems are restored.

Before activation acceptance, record disposable-player browser evidence for correct Cove scene/HUD, below-level rejection, free one-time unlock, Home→Cove→Home→Cove and fresh reload, ordinary planting/harvest, cap failure and retry without charge, supported next expansion and correct cap increase, separate inventory store/withdraw, unsupported item/terrain/shipping/feature rejection, and failed-transaction rollback. Story is the only deferred content category; every other exposed rule needs source and runtime evidence in `STATUS.json`.

## Cove follow-up: cap, re-plow and unresolved shoreline

Original-browser follow-up on 22 October 2026 filled all 45 ordinary plots on the 58-wide farm through paid UI actions (44 new plots, 660 coins, 44 XP). Attempt 46 on clear inland grass displayed the original expansion notice; the complete saved state remained identical. The existing fallow plot counts toward the cap.

The original client retains a harvested crop's itemName, plantTime and position when re-plowing it. The prior Cove guard wrongly rejected that packet. `cove_rules.guard_plow_snapshot` now allows the same saved ordinary fallow plot and an identical plowed retry, while rejecting fabricated crop-bearing plots, changed identity/clock/position and special flags. The post-fix combined run passed 505 tests with zero failures/errors/skips (141.531s); the subsequent dormant Haunted Hollow tests are recorded separately.

**Shoreline acceptance remains unresolved.** Browser plowing exposed plots overlapping the painted water. Five test plots were moved inland through the original Move Tool without changing their identity/state or the balances. That relocation is not a terrain fix. `FarmBackgroundRenderer.loadOutsideImage` method9839 chooses suffix `(width-2)/4`, so58 correctly uses `_14.swf`; methods9842/9849 use actual SWF dimensions and the normal centered transform. Cove has no configured outside-image size/offset override. `YimfMap.isPathable` returns true and supplies default terrain, but generic `FarmGameWorld.loadObject` can instead receive server-supplied terrain. The fallback does not prove original Cove snapshots lacked a coastline map or collision objects. No original populated starter, shoreline mask or blocker layout has been recovered. Preserve the original transform; obtain original snapshot/geometry evidence before certifying buildable boundaries.

Read-only disassembly: `/private/tmp/cove-shore-{background,world,yimf,special}-full.txt`. Browser evidence is in workspace sibling `Browser Verification 2026-10-22/cove-followup/`. Candidate8 predates the re-plow fix and Haunted Hollow module; no package was deployed.
