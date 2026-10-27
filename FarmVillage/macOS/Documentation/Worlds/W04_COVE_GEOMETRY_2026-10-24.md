> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../../ACCEPTANCE.md), [current world scope](../../../../WORLD_READINESS.md) and [the continuation backlog](<../../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# W04 Cove geometry and special plots — 24 October 2026

Source baseline: `845de48027ac82bbf0ab07da91336d1becb57273`. This is a private source proposal. No original populated starter or authentic shoreline/buildability layout is claimed.

`cove_rules.py` retains the exact 25 width/cap pairs (50→35 through 242→1325, step eight), the original Cove theme, square dimensions, named default/land terrain ancestors, and the empty expansion-added object list. The existing sequential expansion engine is unchanged. There is no `farmExpansions/world[@name='fisherman']` configuration. No treasure, port, blocker, or coastline object is granted by this change.

## Recovered original behavior

The preserved original client is `embeds/Flash/v855097-855094/FarmGame.swf`, SHA-256 `1edea7cbecefcb1e1233da207164942f0088a83b87afc9254850f5fcde5034ae`.

| Original method | Exact relevant behavior |
| --- | --- |
| FarmGameWorld.loadObject 5477, source lines 381–439 | An explicit supplied terrain array selects an InvisibleTerrainMap; absent terrain falls through to the Yimf path. It also reads `serializedExtraItemFlags` into BitFlagsById. Theme choice does not prove the absence of a server terrain array. |
| YimfMap.isPathable 21951, lines 125–126 | Returns true. This is fallback pathability, not recovered Cove shoreline collision data. |
| TerrainUtil.getTerrainCode 9332, lines 82–90 | InvisibleTerrainMap supplies a tile's terrainCode; UDTMap supplies its tile code; the other path returns default code0. |
| TerrainUtil.getTerrainCodesForItemInstance 9335 / isAreaAcceptable 9333 | Terrain selection uses an object's position and footprint, then the terrain map. Painted background pixels are never queried for collision. |
| FarmGameWorld.initPlotLimitCounts 5483, lines 551–570 | Iterates every Plot object, resolves its footprint's terrain groups, and increments each applicable limit group once. Crop state does not exempt a plot from the cap. There is no jumbo/super reward multiplier in this count. |
| FarmBackgroundRenderer.loadOutsideImage 9839 | Uses background suffix `(width−2)/4`. It does not supply a collision mask. Cove's Yimf row has no authored outside-image size/offset override. |
| Plot.getSaveObject 21739 / loadObject 21740 | Serializes `isJumbo`, `isBigPlot`, `isProduceItem`. Load may derive jumbo from organic fertilization; fallow/withered state clears jumbo/produce/organic state. |
| FarmGameWorld static initializer 5471 | Extra-item flag1=organic fertilizer; flag2=ignore smart buildable requirements; flag3=super plot. |
| BitFlagsById.unpack 22123 / serialize 22124 | Array of groups; each uint packs `(objectId << 16) | flags`. Sixteen flag bits per group. Per-object `isSuperPlot` is not the original serialized super-plot authority. |
| SuperPlotManager.isFeatureEnabled 24861 | Requires `fv_superplots` experiment variant2. No Cove-specific exclusion appears in this method. |
| SuperPlotManager.getWorldLimit 24869 / canPurchase 24871 | `superPlotsWorldLimit` defaults to104 and CMS explicitly supplies104. Purchase checks current super plots plus Gift Box super plots plus requested quantity against the limit. |
| SuperPlotManager static initializer 24860 / getMultiplier 24872 | Authored super-plot multiplier5. It does not establish a server-owned purchase/consume/claim ledger. |
| OrganicFertilizerHelper.playerCanSeeFeature 7649 | Delegates to CMS `allow_organic_fertilizer`: level≥5 AND experiment `fv_organicfertilizer` variant10. This gate alone does not restore its durable consumable effect. |

## Implemented scope

The exact restaurant (`xcovecraftingcottage`, code `^2`, class CraftingCottageBuilding, craftType restaurant) and the independently validated imported Port are admitted. Other special classes/identities remain closed. Snapshots cannot contain more than the authored one Port or one restaurant.

The Cove snapshot guard now inspects the original out-of-object `serializedExtraItemFlags` field. Nonzero flags, unknown groups with active bits, and malformed serializations refuse without changing the snapshot. This prevents organic/super plots or the smart-buildability bypass from silently entering an ordinary fallback. Missing/null/empty groups and zero-bit entries do not affect ordinary farming or caps. No imported flag is deleted or converted into ordinary ground.

## Acceptance and blockers

Five dedicated `test_cove_geometry.py` tests cover packed flags, malformed imports, zero-bit groups, preservation of supplied terrain arrays, exact restaurant admission, duplicate limits and rejection of unrelated cottages. The existing `test_cove_rules.py` suite passed11 tests and `test_cove_travel.py` passed18 tests, covering cap/replow, ordinary farming/storage, four-world travel, coin/cash sequential expansion, exact prices and unchanged refusal paths. Logs are separate; these are focused unit/Flask-AMF acceptance cells, not original-client or artifact acceptance.

**RECOVERY_BLOCKED — authentic shoreline/buildable geometry:** obtain an original Cove `WorldService.initUser`/world-load snapshot containing the terrain array and blocker/Port placement objects, or an authoritative server generator with coordinate/rebasing rules for each expansion. Available theme art, Yimf weights, the generic pathability fallback and terrain tile definitions cannot recover these coordinates. Authored background and grid transforms are preserved. Supported imported unknown terrain remains preserved but unavailable; the empty local Yimf starter remains a disclosed local substitute. Full authentic terrain acceptance cannot pass from the current artifacts.

**RECOVERY_BLOCKED — specialized plot economies:** original field encoding, feature gates, multiplier and limit are recovered above. Durable purchase/consumption callbacks, per-target effects, authoritative reward application, retry/restart ledgers and original-client acceptance are not supplied by those static rules. Organic/jumbo, big/produce and super-plot actions remain unavailable. Do not enable them by accepting a supplied boolean or setting an experiment variant.

Read-only disassembly and input hashes are in this lane's evidence files `geometry-*.pcode` and `geometry-inputs.json`; these are research receipts, not runtime inputs. No artwork-derived mask, rectangle/diagonal coastline, invented reward, plot-weight scaling, borrowed expansion treasure, or populated starter was introduced.
