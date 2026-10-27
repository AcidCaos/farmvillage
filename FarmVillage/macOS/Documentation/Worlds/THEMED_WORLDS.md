> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../../ACCEPTANCE.md), [current world scope](../../../../WORLD_READINESS.md) and [the continuation backlog](<../../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Themed worlds: basic farming and decorating

Checked 2026-10-24. Production `themed_worlds.ACTIVE_WORLDS` contains fourteen accepted themed worlds: `rainforest`, `mediterranean`, `storybook`, `candy`, `oasis`, `oz`, `toyland`, `sleepyhollow`, `australia`, `fforest`, `htown`, `atlantis`, `glen` and `hlights`. The original six passed the recorded bounded farming and decorating scenarios on disposable farms on 2026-10-23. The parent explicitly accepted all five additional final cycles on 2026-10-24 before adding their keys to production source. These are bounded original-browser results, not certification of every historical feature or of native/device runtime. No Bifrost deployment or real-save write is claimed. Story is deferred by the user.

The five additional contracts were accepted first in the parent's disposable candidate runtime. Their preparatory market samples, source audit and browser checklist are preserved in DORMANT_FIVE_BROWSER_CANDIDATES_2026-10-24.md (`DORMANT_FIVE_BROWSER_CANDIDATES_2026-10-24.md`; external/private historical reference, not included in this source export); its dormant/no-browser statements describe that earlier preparation checkpoint. Current acceptance and source activation are recorded here and in `STATUS.json`.

## Five-world browser acceptance — 2026-10-24

The parent performed original-client acceptance at `http://127.0.0.1:45525`, using the marked runtime `/private/tmp/fv-finish-20261024`. The prior final cycles and Toy Town presentation recheck used revision 8; final Htown acceptance used revision 9 after its derived WorldProgress button was fenced. `source-hashes-revision8.json` and `source-hashes-revision9.json` pin those configurations. The reviewed client SHA-256 is `c5aaff1f2ef9d60d4d2606ecac81ad7190d3f120b1500fb6b4e1d98ea4bbf589`; the Htown correction changes the derived world configuration. The later declared source change adds the five accepted keys to `ACTIVE_WORLDS`. Checkpoints are under the fixture's `evidence/` and retained in the parent workspace's `Finish Verification 2026-10-24/evidence/`. Screenshots are landscape 1280×800.

| World | Final bounded result | Evidence and precise limits |
| --- | --- | --- |
| Toy Town | Crop, decorating, storage, restart and travel loops accepted; fresh-VM final theme/HUD, land/score/Map/Beat fences and normal 15-coin re-plow accepted | `toyland-final-accepted.json`, screenshot 42; earlier optimistic expansion animation remains a failed attempt, superseded by final hidden-offer presentation. |
| Horseman's Hollow | Final cycle accepted, including inventory isolation, reload, round trip, withdrawal/move/sale and final presentation fences | `hollow-final-accepted.json`, screenshots 25–27. |
| Australia | Revision-8 cycle accepted, including Home-only variant refusal, storage/reload/withdraw/sale, travel, context Market and final land gate | `australia-final-cycle.json`, screenshots 30–33; no ordinary animal/tree purchase loop claimed. |
| Mystical Groves | Final cycle accepted, including crop/re-plow, isolated storage, reload/withdraw/move/sale, travel and final presentation fences | `groves-final-cycle.json`, screenshots 34–36. |
| Mistletoe Lane | Complete crop/decorating/storage/Home-travel/reload/withdraw/sale/re-plow cycle accepted; revision-9 fresh VM has no automatic WorldProgress or Map/Score/Beat/help menu invitation; authored same-code 1-cash Present Box alternative accepted | `mistletoe-basic-cycle.json` and `mistletoe-final-accepted.json`, screenshots 41, 47–48; final cash purchase placed object 20, cash 922→921, unchanged gold 2,494,582 and XP 101,227→101,228. Earlier screenshot 40 preserves the map-invitation failure. No ordinary animal/tree purchase loop claimed. |

Toy Town used synthetic player `a87f3421-bcde-4f5c-82db-da2437cb732a`; Hollow used `ac74314d-78f3-42c7-bee9-c858af88087c`; Australia, Groves and Mistletoe used `3c524ff5-c266-41e9-a09b-5ffa9e1d4ce9`. These records do not test the user's farms. `STATUS.json` preserves the recovered inventory and earlier histories, including partial checkpoints. Its five new `rule_readiness_scope` maps define exactly what each verified gate covers: the disclosed ordinary 50×50 mode and enforcement of its fences, not restoration of original populated starters, land growth, story, scores or special systems.

## Three further bounded decisions — 2026-10-24

The root separately accepted and activated Atlantis (`fda3241`), Enchanted Glen (`fb6ab4c`) and Holiday Lights (`4535b1`), one feature commit per world with exact12-/13-/14-world assertions. Original −19/−18 storage and XML omissions remain preserved for Atlantis/Glen; Hlights retains original −25 separately from conflicting XML−24. Atlantis/Glen local themes and all empty starters are disclosed.

Atlantis native evidence (`AtlantisEvidence20261024/BROWSER_ACCEPTANCE.md`; external/private historical reference, not included in this source export), Glen native evidence (`SESSION_B_GLEN_BROWSER_2026-10-24.md`; external/private historical reference, not included in this source export), Hlights final scope (`SESSION_B_HLIGHTS_BROWSER_FINAL_2026-10-24.md`; external/private historical reference, not included in this source export) and serial source checks (`SessionBSerialActivation20261024/RESULT.json`; external/private historical reference, not included in this source export) define the bounds. Native ordinary economy, crop/decorating, original Storage widget, travel/reload and labeled gateway negatives/retries passed. Atlantis final mastery gifts are unit-tested only. Glen's earned gift was shown/consumed/placed/moved/reloaded but its fallback sign artwork failed (shadow only). Hlights' backend reward passed, while latest gift All/Use/placement remained unverified because later clients blanked or remained loading. No full mastery artwork or latest-Hgift pass is claimed.

Immediate IG crop redraw failed in Hlights/Glen; original grown art after reload and manual harvest passed. The root accepted this explicit bounded limitation and retained the rendering failures for separate follow-up, with unknown cause. Final actual full-suite validation is delegated; its result is recorded separately, not inferred from focused counts. Original geometry/art is unchanged and no speculative rendering fix was added.

## Mode

A themed farm is an additional farm that, once unlocked:

- is free through its archived all-access condition (level 15, served experiments, one `world_unlock` reward, no charge and no item grant);
- starts as an explicit empty 50×50 farm (`localStarter: empty-<world>-v1`), because the original `.farm` starter was not recovered;
- uses the world's own ordinary-ground theme (`<world>_theme`, horizon and background art checked locally);
- lets the player plow, plant, harvest, re-plow, place, move, store and sell that world's own basic items.

**In scope:** seeds (Plot), trees, animals, buildings and decorations whose only requirement is their World, with coin or Farm Cash prices from the catalog. Original unrestricted ordinary Inventory StorageBuildings (32 priced records) are also admitted so each farm can buy its own normal capacity; no other global items are added. Plowing costs Home's 15 coins (see Deviations).

**Out of scope, fenced:**

- quests: campaign and location quest exposure, quest/mastery-gated purchases, and unknown requirement classes (`Mastery`, `WorldLicense`, `SuperCrop`, `HybridSeed`, `Platform`). Existing shared earned crop mastery is a separate path;
- themed world scores: the `unlock_world_score` reward is not granted by themed creation, ordinary world points do not accrue or display, and `score` is `None` in the bounded record. Common `world_scores.py` quest-reward support does not restore those ordinary themed score lifecycles;
- world currencies: a world-currency price is converted to Farm Cash only through `world_currency_conversion`; coins are never converted and an unconvertible price is refused;
- shipping licenses, feature buildings, crafting cottages, breeding, vehicles, consumables, bushels, eggs and superplots;
- expansion-added objects (below), specialized plots, and any placement outside the grid or on a non-ground terrain.

## Ranking

Gates, in order: (1) background and horizon art present locally, all 20 background variants for widths 50–202 (suffixes 12–50); (2) a unique, recovered `storageId`; (3) all-access experiments `fv_<w>` and `fv_<w>_for_all` served as `1` in `templates/play.html`; (4) quest exposure (`location_gated_quest_count`, `prefix_attributed_campaign_quest_count` in `INVENTORY_EVIDENCE.json`); (5) admitted basic item count from the catalog.

| # | World | storageId | Art (horizon, backgrounds) | Quest exposure (location / campaign) | Admitted basic items | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `rainforest` (Rainforest) | -26 unique | yes, 20/20 | 0 / 0 | 157 (27 seeds) | 28 dated-offer fences (22 windows open today); expansion adds objects from 58 |
| 2 | `mediterranean` (Mediterranean) | -29 unique | yes, 20/20 | 6 / 0 | 166 (23 seeds) | no dated offers; expansion adds objects from 58 |
| 3 | `toyland` | -34 unique | yes, 20/20 | 7 / 0 | 149 (21 seeds) | Exact `fv_xtl_master` / `fv_xtl_for_all` gates; bounded final cycle accepted and active |
| 4 | `storybook` | -32 unique | yes, 20/20 (backgrounds `xsb_themeBackground2_`) | 7 / 0 | 140 (21 seeds) | In SPECS 2026-10-23; no admitted item has a purchase window; expansion adds objects from 58 |
| 5 | `sleepyhollow` | -33 unique | yes, 20/20 | 6 / 0 | 137 (21 seeds) | Exact `fv_xsh_master` / `fv_xsh_for_all` gates; bounded final cycle accepted and active |
| 6 | `candy` | -23 unique | yes, 20/20 | 6 / 0 | 133 (19 seeds) | In SPECS 2026-10-23; expansions are cash-priced only (20 FC from width 58); 2 admitted items with purchase windows |
| 7 | `oasis` | -31 unique | yes, 20/20 | 6 / 0 | 152 (27 seeds) | In SPECS 2026-10-23; 72 admitted items with purchase windows (checked at purchase); expansion adds objects from 58 |
| 8 | `oz` | -28 unique | yes, 20/20 | 6 / 0 | 204 (19 seeds) | In SPECS 2026-10-23; 128 admitted items with purchase windows (checked at purchase); expansion adds objects from 58 |
| 9 | `hallow` (Haunted Hollow) | claimed -14 by the dormant `hallow_rules` track | yes, 20/20 | 6 / 0 | ~30 (scan) | Owned by the Haunted Hollow track; not wired here |
| 10 | `hlights` | original client/storageConfig -25; XML -24 preserved | yes, 20/20 | 6 / 0 | 214 (32 seeds) | Bounded ordinary activation4535b1; failed later gift/loading follow-up explicit |
| — | `australia` | -21, original client/storageConfig | yes, 20/20 | see inventory evidence | 109 (37 seeds) | Bounded final cycle accepted and active; no ordinary tree/animal admitted |
| — | `fforest` | -24 | yes, 20/20 | see inventory evidence | 125 (21 seeds) | Bounded final cycle accepted and active; imported inventory claims preserved |
| — | `htown` | -15, original client/storageConfig | yes, 20/20 | see inventory evidence | 93 (7 seeds) | Bounded revision-9 final cycle accepted and active; local theme disclosed; score-help/map remain fenced |
| — | `atlantis` | -19 original client/storageConfig | yes, 20/20 | 6 / 0 | 69 (18 seeds) | Individually activatedfda3241; XML omissions/local theme disclosed |
| — | `glen` | -18 original client/storageConfig | yes, 20/20 | 6 / 0 | 46 (12 seeds) | Individually activatedfb6ab4c; fallback sign artwork FAIL is retained |

Current exact counts include the 32 original unrestricted ordinary global Inventory StorageBuildings in each themed catalog. No other global items enter this exception. Candidate counts are reproduced in `DORMANT_FIVE_BROWSER_CANDIDATES_2026-10-24.json`; rows marked `~` remain historical scan estimates.

Excluded, with the gate that fails:

- **Fixed/large scene layouts need assessment (44 worlds):** the earlier 0/20 ordinary-variant scan did not mean no background art. All 43 formerly listed keys **plus `japan`** have recovered configured-prefix backgrounds at suffixes 80/120; 42 have their configured horizon, while `wildwest` and `treasuretides` lack it. The suffixes are filenames, not asserted grid dimensions. The complete 70-world asset audit (`ASSET_AVAILABILITY_2026-10-23.md`; external/private historical reference, not included in this source export) lists every friendly name/key and exact local evidence. Recover the original scene sizing, renderer and terrain contract before exposure.
- **Missing expansion storage ID:** `space` remains outside this contract. Atlantis−19 and Glen−18 were independently recovered from original WorldManager/StorageConfig; absent XML prefix/storage/theme fields remain absent, with the local theme disclosed. Australia (-21) and Mistletoe Lane (-15) are now recovered independently from the original client and StorageConfig; their omission in expansion XML is preserved rather than normalized. `space` also has `fv_space_for_all = 0`.
- **Conflicting archive metadata:** `fforest` and `hlights` expansion XML both claim -24, while StorageConfig assigns HlightsInventory -25. New Mystical Groves creation still rejects any imported summary or ledger already claiming -24; it never absorbs or relabels that data.
- **Exact accepted gate contracts:** Toy Town and Horseman’s Hollow use the recovered `fv_xtl_master` / `fv_xtl_for_all` and `fv_xsh_master` / `fv_xsh_for_all` names. All four are served as 1. Only each world's own master/for-all and documented land-gate prefixes are admitted; unrelated feature gates stay fenced. All five additional worlds are active after their bounded final browser cycles passed.
- **Experiment closed:** `yuletide` (`fv_xyt_master_for_all = 0`), `avalon` (feature option and `fv_xmb_master_for_all = 0`).
- **Other owners or closed:** `asia`, `hawaii` (world-currency markets and their own dormant modules; asia has an expansion plot table), `village` (no admitted basic items), `winterwonderland` (general access ended 18 Feb 2012; a new unlock would bypass it), `fisherman` and `meadows` (already active or candidates), `angler` and `garden` (no basic farm).

## Names

`SPECS[world]["name"]` is what `/farms` shows (`creative_worlds.candidates`). For storybook, candy, oasis and oz, added 2026-10-23, it is the en_US friendly farm name, read from the string table of `xml/gz/v855098/en_US.swf`. The `friendlyName` key `FarmName_<world>` resolves to `FarmTravel_<world>` ("To <name>"), and `defaultWorldNameLocKey` `FarmName<World>` reads "{user,name}'s <name>". The two agree for every world listed here.

Rainforest and Mediterranean predate this rule and still use the plain capitalised keys ("Rainforest", "Mediterranean"). Their recovered friendly names are "Fields of El Dorado" and "Mediterranean Riviera". They were not changed here because Rainforest is now browser-accepted; changing its displayed name is the parent's decision.

## Recovered records

Derived by `themed_worlds.recovered_rules` and checked against the archive at each call. Any drift raises instead of falling back.

| World | Access | Rewards | Theme | Initial size | Ceiling | Experiments |
| --- | --- | --- | --- | --- | --- | --- |
| `rainforest` | `allAccess`: level 15, `fv_rainforest` = 1, `fv_rainforest_for_all` = 1, not unlocked | `world_unlock` only | `rainforest_theme` (grass, weights) | 50×50 | 5500 objects (CMS `maxNumObjects`; no plot table) | served 1 / 1 |
| `mediterranean` | `allAccess`: level 15, `fv_mediterranean` = 1, `fv_mediterranean_for_all` = 1 | `world_unlock` only | `mediterranean_theme` | 50×50 | 5500 | served 1 / 1 |
| `storybook` | `allAccess`: level 15, `fv_storybook` = 1, `fv_storybook_for_all` = 1, not unlocked | `world_unlock` only | `storybook_theme` (grass, weights) | 50×50 | 5500 | served 1 / 1 |
| `candy` | `allAccess`: level 15, `fv_candy` = 1, `fv_candy_for_all` = 1, not unlocked | `world_unlock` only | `candy_theme` (grass, weights) | 50×50 | 5500 | served 1 / 1 |
| `oasis` | `allAccess`: level 15, `fv_oasis` = 1, `fv_oasis_for_all` = 1, not unlocked | `world_unlock` only | `oasis_theme` (grass, weights) | 50×50 | 5500 | served 1 / 1 |
| `oz` | `allAccess`: level 15, `fv_oz` = 1, `fv_oz_for_all` = 1, not unlocked | `world_unlock` only | `oz_theme` (grass, weights) | 50×50 | 5500 | served 1 / 1 |

The all-access prerequisite is named by the storage prefix (`fv_xrf_all_access`, `fv_xmd_all_access`, `fv_xsb_all_access`, `fv_xcw_all_access`, `fv_xoa_all_access`, `fv_xoz_all_access`), while the experiment names use the world key.

Price rules, applied per item:

- coin-market (or unmarketed with a `cost`): the original coin cost;
- cash-market: the original Farm Cash price;
- world-currency market (`jade`, `coconuts`, `villageCoins`): `world_currency_conversion.price_for_item` (ceiling of cost × cash / units); an item with its own `cash` keeps it;
- anything else, or a missing price: unpriced, listed, and refused.

No admitted item in any world listed above is priced in a world currency, and no item is unpriced. Every price is a coin or Farm Cash price.

## Expansion-added objects (not restored)

Every world in SPECS records original expansion-added construction objects beginning at width 58. The original six plus toyland/sleepyhollow/fforest/hlights have37 objects each; Australia/Atlantis have40 and Mistletoe Lane/Glen36. Exact widths/codes/coordinates remain in `gameSettings.xml.gz` and the candidate audit evidence. Restoring them needs their construction-state contract, which was not recovered. `themed_worlds.expand` therefore refuses any width that adds objects. The initial 50×50 farm is fully playable; land growth stays closed.

## Module design

`themed_worlds.py` (shared rule functions with explicit state):

- `SPECS`: per-world friendly name, storage prefix, storage ID and theme. Adding a world means adding one entry; the activated-farm tests run for every SPECS world automatically.
- `recovered_rules(world)`: the archive contract (access, rewards, theme, storage, ceiling, starter).
- `catalog_rules(world)`: admitted items, prices, unpriced items and expansion offers from the live catalog. Admission requires only `World` requirements, a basic type and class, no feature, purchase prerequisite, license, quest, mastery, neighbor-only unlock or unavailable flag, and experiment gates limited to the world's own `fv_<key>` and `fv_<key>_farm*` names, served as `1`.
- `guard_snapshot`, `guard_action`, `guard_purchase`, `charge_purchase`: travel and farm guards. The purchase guard reuses `creative_worlds._guard_purchase_dates`, `_guard_item_access`, `_placement_retry` and `_guard_land_terrain`; `cove_rules.guard_plow_snapshot` is reused for plowing.
- `plow_cost`, `plow_charge`: Home's rate, world-agnostic; a retry on a saved plowed plot is free.
- `create`: the all-access unlock (no charge, idempotent).
- `expand`: next-width purchase, refused where objects would be added.

Hooks, all no-ops for worlds not listed in `ACTIVE_WORLDS`:

- `world_travel.supported_worlds()` adds active themed worlds to `SUPPORTED_WORLDS`; `validate` and `switch` use it, and themed snapshots are checked with `themed_worlds.guard_snapshot`.
- `creative_worlds.create`, `guard_action`, `guard_market_purchase` and `expand_farm` dispatch to `themed_worlds` only for active worlds.

`SUPPORTED_WORLDS` remains the base set. The server's farm visits and names, and
Instant Grow's world checks, use the dynamic active-world hooks.

## Activation (parent)

Activate one world at a time, after each world's browser checks pass.

1. Browser checks, on a disposable player: the scene and HUD use the world theme; the free all-access unlock charges nothing and repeats cleanly; Home→world→Home→world survives reload; plowing charges 15 coins once and a retry is free; a seed plants and harvests; a decoration places, moves, stores and sells; the expansion past 50 is refused without charge; a rejected quest or world-currency item leaves the save unchanged.
2. Add the key to `ACTIVE_WORLDS` in `themed_worlds.py`, preserving all previously accepted keys. The fourteen worlds listed above are now individually active; new worlds still require their own acceptance.
3. `server.py` already checks farm visits with `world_travel.supported_worlds()` and adds active themed names to `/farms`; no per-world server edit is needed. Verify both the visit and displayed name during browser acceptance.
4. `creative_worlds.candidates()` already lists each active world (done). The `templates/farms.html` page was not re-checked here.
5. `instant_growth.py` already accepts `world_travel.supported_worlds()` and selects the world's original airplane. Browser-check Instant Grow for 4 Farm Cash, including as the first action after loading (`{firstWA: true}`), then harvest and reload. No additional Instant Grow edit is needed to activate a tested world.
6. Purchases: the existing catalog price path already charges the recovered coin or Farm Cash price for each listed world. Currency worlds would need `themed_worlds.charge_purchase` wired into the charge path; that is not done.

## Known UI limits

- The legacy HUD travel dropdown has fixed slots per world skin. Both launch templates now select the original paged travel window; its recovered configuration and remaining acceptance scope are documented in `macOS/Documentation/TRAVEL_WINDOW_RECOVERY.md`. The `/farms` page always lists every owned farm.

## Deviations (deliberate)

- **Currency items:** priced only in a world currency are charged Farm Cash through `world_currency_conversion` (rates from archived exchange packs). See `WORLD_CURRENCY_CONVERSION.md`.
- **Plowing:** 15 coins in every themed world, including currency worlds, never converted (user decision, 2026-10-23). This supersedes the plow conversion in `WORLD_CURRENCY_CONVERSION.md`; `world_currency_conversion.plow_charge` still computes the converted value and must not be used for themed worlds.
- **Scores:** no `unlock_world_score` reward, no score accrual or display.
- **Starter:** empty local 50×50 farm; no original populated `.farm` was recovered.
- **Expansion charge:** a Farm Cash expansion costs 1 FC, as recovered for Cove and Meadows (`ChangeFarmItem.saleCash` is 1 for `expand_farm`).
- **Expansions:** refused where original objects would be added (all candidates from 58 up).
- **Shipping licenses:** not granted and not sold.
- **Experiments:** served values are read from `templates/play.html`; the rules fail closed if it is unreadable.

## Evidence

- Art: manifests `assethash/v9/assethash.master.amf.gz` and `xml/gz/v855098/assethash.min.amf.gz` (pyamf decode), resolved to `LocalData/assets/<dir>/<md5>.<ext>` and checked for nonempty files.
- Catalog: the 111,206-item decoded catalog (`items.get_items()`); classification and prices reproduced in `macOS/Tests/test_themed_worlds.py`.
- Access, experiments, storage and expansion records: `gameSettings.xml.gz`, `gameSettingsCMS.xml.gz`, `yimf.xml.gz`, and `templates/play.html`.
- Art check (2026-10-23): for all eight worlds with `*_theme` entries (rainforest, mediterranean, toyland, storybook, sleepyhollow, candy, oasis, oz), the horizon swf and background variants 12–50 (21 files) are in the assethash manifest and nonempty under `LocalData/assets`.
- Tests: `macOS/Tests/test_themed_worlds.py` (77 tests: archive contracts and activation defaults, `ActivatedFarmCases` run once per SPECS world, and the Rainforest packet regression), included in `macOS/Scripts/run-other-mechanics-regressions.py`. Focused run of `test_themed_worlds`, `test_creative_worlds`, `test_world_travel` and `test_world_currency_conversion`: 136 tests passed on 2026-10-23 with `ACTIVE_WORLDS = {"rainforest"}`.


## Ordinary themed inventory correction — 2026-10-24

`storage._inventory_limits` now verifies the exact original Inventory inheritance
for all fourteen SPECS worlds, alongside Home/England/Cove/Meadows (18 scoped IDs).
Each inherited ceiling is 1250. The unchanged admission guard still sums only
fully built ordinary catalog StorageBuilding capacity, subtracts usage by unit,
clamps to the ceiling, excludes special/credit cellars, and protects other-world
ledgers. No capacity is granted by creation or by the ceiling itself.

A narrow catalog exception admits original global Inventory StorageBuildings
with no requirements, subject to `_reasons`, actual prices, level/date/gate checks
and normal placement. Pink Tool Shed costs 22 Farm Cash and contributes 15 slots.
Other global items, nonbuyable upgrades, specialized cellars and unsupported
features remain outside the themed catalog. Three shared tests iterate all14
inherited limits, the exact global exception, and five candidates’ complete AMF
gateway purchase→store→disk reload→travel→withdraw loops. The historical combined storage,
themed, travel and creative-world run passed208 tests before the three new activations. These overlapping
tests are separate from the parent browser checkpoint recorded above.
