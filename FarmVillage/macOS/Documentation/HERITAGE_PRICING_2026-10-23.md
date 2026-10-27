> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../ACCEPTANCE.md), [current world scope](../../../WORLD_READINESS.md) and [the continuation backlog](<../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Home Farm heritage pricing, 2026-10-23 (crops admitted 2026-10-24)

## What it does

Ordinary items from catalog-only worlds, exclusive items that never had a price, and crops (seeds) from catalog-only worlds become buyable on the Home Farm. Each one gets a deterministic price from the recovered catalog. The overlay is server-side and sits behind one constant:

- `heritage_pricing.ENABLED` in `heritage_pricing.py` (currently `True`). Set it to `False` and the served market and purchase path return to the recovered catalog exactly.

No SWF was edited. No original asset, archived catalog, or saved player was modified. The derived records are not written back to any cache file.

## Where it is wired

| Point | File | Role |
|---|---|---|
| Server item copy | `items.py:48` | `heritage_pricing.apply(get_items(), server=True)` after the recovered cache loads. Feeds `get_item_by_name`, so `apply_item_cost` charges the derived price. The same call records the refused crops for `crop_refusal`. |
| Served market | `client_catalog.py:138` | `heritage_pricing.apply(records)` in `_generate`, before the expiry and level closures. The derived-cache schema is `client-amf-v3` and includes `overlay_digest()`. |
| England guard | `creative_worlds.py:346-348` | England shares the Home purchase branch, so an overlaid item is refused there. |
| Home crop purchase guard | `creative_worlds.py` (`guard_market_purchase`, Home branch) | A crop whose World requirement does not name `farm` is refused with its `crop_refusal` reason before any inventory purchase charges. |
| Home crop planting | `commands.py` (`place`, seed branch) | A crop that fails `world_requirement_matches` on Home is refused with its `crop_refusal` reason. Other worlds keep the generic message. |

Additional farms are refused without edits: a rehomed item carries `strict`, so the Meadows non-strict Home alias cannot admit it.

## Scope: reserved worlds stay as recovered

An item is never overlaid if any of its World requirements names a reserved world. Reserved worlds are the ones with their own rule modules or themed admission and price rules: `farm`, `england`, `meadows`, `fisherman`, `hallow`, `hawaii`, and the eleven `themed_worlds.SPECS` worlds (`rainforest`, `mediterranean`, `storybook`, `candy`, `oasis`, `oz`, `toyland`, `sleepyhollow`, `australia`, `fforest`, `htown`).

Those rules select items by their World requirement and price them from the catalog. The first version rehomed every locked item on the shared server copy and broke them: `test_themed_worlds` and the Rainforest packet test failed, and `test_world_currency_conversion` failed because its audits count the world-currency items. The current version leaves reserved-world items and world-currency items exactly as recovered. A test checks that `RESERVED_WORLDS` covers every SPECS key and the other rule-module worlds.

## The rule

1. **Eligibility.** The item's `(type, className)` must be an ordinary class (below). Its requirements must be World entries only. None of `purchasePrereqs`, `prereqs`, `requiredQuest`, `requiredMastery`, `license`, `marketPrereqs`, `experiment`, `geoip`, `promoMode`, or `minNeighbors` may be set. Items already sold on Home (a World requirement naming `farm`) are untouched.
   - Locked: at least one World, none reserved. Several Worlds need `compare: any`.
   - Exclusive: no World requirement, and no price in `cash` or `cost`.
2. **Ordinary classes.** `tree`; `animal` with className none, `CashGrowableBaby`, or `ItemGrowableBaby`; `decoration` with className none, `RotateableDecoration`, or `Gnome`; `building` with className none; and `seed` with className none (crops, rule 3).
3. **Crops (seeds).** A crop is admitted only when its whole Home loop works with the existing server code: buy at its coin price, plant on a plowed Home plot, grow for `growTime`, then harvest for `coinYield`, `masteryYield` and the mastery ladder. The crop XP is applied at planting, as before. Any gate below excludes the crop with the named reason. The first matching reason is recorded.
   - `crop: licence`, `crop: purchase prerequisite`, `crop: market prerequisite`, `crop: experiment prerequisite`, `crop: geo gate`, `crop: promo`, `crop: neighbour gate`: the Home server never checks these before a sale or planting.
   - `crop: unlock or donation`: `unlock`, `unlockCost`, `donation`, or `friendReward` is set. Those flows are not restored.
   - `crop: harvest yield in world currency or score`: a `harvestYield` pays jade, coconuts, or a world score. The server does not pay it on Home.
   - `crop: harvest item drop`, `crop: produce item`: the harvest drops an item the server never creates.
   - `crop: organic certification`, `crop: hybrid breeding`, `crop: weather modifier`, `crop: present gift`, `crop: seed package`: each is a mechanic the server does not restore.
   - `crop: non-land terrain`: `terrainSet` names none of the Home land terrains (`LAND_TERRAINS`: `all`, `amphibious`, `land`, `plowable`, the set `creative_worlds._land_terrain_names()` reads from the recovered settings). Water, earth, terrace, zen, snow, dream and turtle crops cannot be plowed on Home.
   - `crop: experiment closed`: the `experimentGate` is not served with a positive variant, or the served variant is not one the crop lists in `experimentVariant`. This follows the client's `checkExperimentGate`. The gate is checked against the served client configuration (`themed_worlds.served_experiments`), so the overlay opens no closed experiment.
   - `crop: no market entry`: no `marketEntries`, so the crop cannot be bought from a market tab.
   - `crop: level requirement`: `requiredLevel` is junk or conflicts, which the purchase path refuses.
   - `crop: reward value`: `coinYield`, `plantXp`, `largeCropXp`, `masteryYield` or a mastery ladder value is not an integer the server can read.
   - `crop: grow time invalid`: `growTime` is not a positive number, so the harvest could never be ready.
   - `crop: special requirement`: a SuperCrop, HybridSeed, Mastery, WorldLicense or FriendSet requirement.
   - Crops keep their own `experimentGate` after rehoming, because the gate was checked open. Other locked items still lose it.
   - Exclusive crops that carry a price are untouched (1,808 records). They are Home items already, left exactly as recovered.
4. **Currency.** An item with a market other than coins or Farm Cash is excluded (world currency: jade, coconuts, villageCoins, berry). An item keeps its own price in its own market: Farm Cash in `cash`, or coins in `cost`. A locked item with only a Farm Cash price gets market `cash`. A locked crop with no coin price takes a coin price (rule 5). Anything else with no price is priced in Farm Cash.
5. **Derived price.**
   - Crop: the nearest priced crop in record order with the same `(subtype, growth band)` supplies its coin price, and the crop is charged in coins. Growth bands cut `growTime` at 0.25, 0.5, 0.75, 1 and 2 days. With no sibling, the lower median coin price of Home-visible crops with the same subtype is used, then the lower median of all Home-visible crops. A crop with no price basis is refused as `crop: no price basis`. Every recovered locked crop has its own coin price, so none of these fallbacks applies to the recovered catalog today. The tests exercise them on synthetic records.
   - Other items, Farm Cash: the nearest priced sibling in record order with the same `(type, className, subtype, sizeX*sizeY)` supplies its Farm Cash price. Equal distance prefers the earlier record. Record order is roughly alphabetical by internal name, so "nearest" tends to mean the same series.
   - Other items, tier, when no sibling matches: the lower median Farm Cash price of Home-visible items in the same tier, first `(type, className, footprint)`, then `(type, className)`, then `type`.
6. **Rehoming.** Each World requirement of a locked item is renamed `farm` with `strict: "true"`. Its limited date window (`limitedStart`, `limitedEnd`) is removed, and so is its `experimentGate` unless it is a crop (rule 3). `archived` becomes `"no"`, and `buyable` becomes `"true"`.
7. **Malformed prices.** Each currency field is parsed on its own, as `engine.catalog_price` does. A valid Farm Cash price is not invalidated by a malformed coin field (for example `cost: "200,000"`).

## Counts (recovered catalog, 111,206 records)

Candidates considered: 13,017 ordinary-class records that are locked to a non-Home World or priceless and unlocked. That is 11,060 non-crop records plus 1,957 locked crops.

| Result | Count |
|---|---:|
| Overlaid, total | 5,025 |
| Locked | 4,725 |
| Exclusive | 300 |
| Locked, Farm Cash price kept (market already `cash`) | 3,269 |
| Locked, coin price kept (`cost`), non-crop | 426 |
| Locked, coin price kept (`cost`), crops | 998 |
| Locked, sibling price (previously unpriced) | 18 |
| Locked, tier price (previously unpriced) | 14 |
| Exclusive, sibling price | 255 |
| Exclusive, tier price | 45 |

Overlaid by class: `animal/none` 1,410; `decoration/none` 1,045; `decoration/RotateableDecoration` 758; `tree/none` 453; `building/none` 217; `seed/none` 998 (crops); `animal/CashGrowableBaby` 88; `decoration/Gnome` 50; `animal/ItemGrowableBaby` 6.

Crops, 1,957 locked: 998 admitted at their own coin price, and 959 refused with a named reason:

| Crop refusal reason | Count |
|---|---:|
| `crop: non-land terrain` | 271 |
| `reserved world` | 269 |
| `crop: purchase prerequisite` | 225 |
| `crop: market prerequisite` | 77 |
| `crop: special requirement` | 54 |
| `world currency` (jade, coconuts) | 23 |
| `crop: experiment closed` | 22 |
| `crop: harvest yield in world currency or score` | 12 |
| `crop: no market entry` | 4 |
| `crop: experiment prerequisite` | 1 |
| `crop: produce item` | 1 |

Each refused crop is refused on Home at planting and at storage purchase, with the reason in the message: "This crop is not sold on the Home Farm (crop: non-land terrain)."

Excluded at the record level, non-crop:

| Group | Reason | Count |
|---|---|---:|
| Locked | prerequisite (`purchasePrereqs`, `marketPrereqs`, `experiment`, `prereqs`; overlapping) | 4,310 |
| Locked | reserved world (rule modules and SPECS worlds, left as recovered) | 1,924 |
| Locked | non-World requirement (WorldLicense, Mastery, and similar) | 23 |
| Locked | world currency (jade, berry) | 3 |
| Exclusive | prerequisite (`marketPrereqs`, `experiment`; overlapping) | 587 |
| Exclusive | `experimentGate` (world-launch experiment) | 186 |
| Exclusive | malformed price (`cost: "na"`) | 1 |

Excluded by class, among the candidate records outside the ordinary classes (independent of the reserved-world rule above). Crops are no longer in this table; see the crop counts above.

| Class | Locked | Exclusive | Why |
|---|---:|---:|---|
| `change_farm` (expansions) | 1,309 | 96 | World land expansions |
| `building`, world mechanics (Feature, FixedTreasure, MultiRewardTreasure, Chicken coop, Garage, Orchard, Cellar, Construction, Breeding pen, Land bundle, Lootable and similar) | 3,890 | 283 | Feature, treasure and construction mechanics |
| `consumable` (quest progress, reward, feature and similar) | 651 | 8,675 | Quest and feature mechanics; quest progress is priceless |
| `decoration` (mastery signs, Bora Bora, Valentine presents, lootable, innovation triggers, and similar) | 592 | 96 | Mastery, loot and world mechanics |
| `vehicle` (Tractor, Harvester, Seeder, Combine, Airplane, Orchard harvester, Plot remover) | 457 | 0 | Fuel and irrigation work in progress elsewhere |
| `crafted` 433, `bushel` 320, `egg` 58, `buff` 6 (locked); `crafted` 1,079, `bushel` 3,046, `egg` 886, `ugc_part` 112, `buff` 102, `bloom` 88, and a small remainder (exclusive) | 817 | 5,350 | Crafting, production, and special systems |

Excluded animal classes: `FestivalOfColorAnimal`, `UGCAnimal`, `MutableAnimal`, `Pet`, `DoghouseAnimal`. `ChickenCoopBuilding` is excluded because it has a production loop.

## Sample of 20 derived items

Fixed sample across all price sources, in catalog order. "Derived" is the effective price on Home. Items whose own price was kept show "own". The sample is non-crop; crops keep their own coin price, so none of these rows changed.

| Name | Group | Class | Footprint | Original world | Original market | Original cost | Original cash | Derived | Source |
|---|---|---|---|---|---|---|---|---|---|
| 10thbirthdaycake1 | exclusive | decoration/none | 8x8 | none | none | 0 | none | 18 cash | sibling:134 |
| 10thbirthdaycake2 | exclusive | decoration/none | 8x8 | none | none | 0 | none | 18 cash | sibling:134 |
| 10thbirthdaycake3 | exclusive | decoration/none | 8x8 | none | none | 0 | none | 18 cash | sibling:134 |
| adventure_refresh_xpromo_sign | exclusive | decoration/none | 10x1 | none | none | 0 | none | 12 cash | tier:footprint |
| adventure_xpromo_sign | exclusive | decoration/none | 10x1 | none | none | 0 | none | 12 cash | tier:footprint |
| anniversaryfountain2012 | exclusive | decoration/none | 5x5 | none | none | 0 | none | 10 cash | sibling:73684 |
| balancepin | exclusive | decoration/none | 40x40 | none | none | 0 | none | 12 cash | tier:class |
| abandonedrailwaystation | locked | building/none | 5x17 | halloweenusa | cash | 0 | 25 | 25 cash | own |
| alpaca_xfw_nordic | locked | animal/none | 1x1 | whitewinter | cash | 10000 | 18 | 18 cash | own |
| ancientclocktower | locked | building/none | 7x3 | israel | cash | 10000 | 18 | 18 cash | own |
| ancientstatue | locked | decoration/RotateableDecoration | 2x4 | atlantis | cash | 12000 | 12 | 12 cash | own |
| alpaca_xfe_frenchsoldier | locked | animal/none | 2x2 | anglofrench | none | 1500000 | none | 1,500,000 coins | own |
| bigcat_xch_holidayreadyleopard | locked | animal/none | 2x2 | xmas | none | 100000 | none | 100,000 coins | own |
| bigcat_xmo_furiousredcat | locked | animal/none | 2x2 | mount | none | 18000 | none | 18,000 coins | own |
| bird_xaf_africanparadiseflycatcher | locked | animal/none | 2x2 | africa | none | 20000 | none | 20,000 coins | own |
| bird_xaf_prismaticbirdie | locked | animal/none | 1x1 | africa | none | 25000 | none | 25,000 coins | own |
| hawaiiantugboat1 | locked | decoration/none | 10x10 | aloha | none | 0 | none | 13 cash | tier:footprint |
| hawaiiantugboat2 | locked | decoration/none | 10x10 | aloha | none | 0 | none | 13 cash | tier:footprint |
| racing_blockerstone | locked | decoration/none | 5x5 | santavillage | none | 0 | none | 10 cash | sibling:73684 |
| racing_gift_2019 | locked | decoration/none | 5x5 | santavillage | none | 0 | none | 10 cash | sibling:73684 |

## Tier table

Lower median Farm Cash price of Home-visible priced items, used for 59 items. Decoration with className none has a class median of 12 Farm Cash. Seen in use: 10x1 = 12; 10x10 = 13; 40x40 falls back to the class median of 12. Footprints with no exact match fall back to the class median, so very large decorations may be underpriced. Review before shipping.

Crop tiers are coin medians, by subtype and then overall, and are not used by the recovered catalog (every admitted crop has its own coin price).

## How items appear in the market (not browser-verified)

Client visibility, from the SWF (`FarmItem.isVisible`): `buyable`, the date gate, the geo gate, `isLicenseHidden`, `checkMarketPrereqs`, `isVisibleOnApplyWorldItemsOnlyCheck` (World restriction), and `isInExperiment`. The overlay satisfies each for overlaid items. For admitted crops, `isInExperiment` is served open, and the gate is kept.

Market tabs are built from `marketEntries`. Non-crop overlaid records with none: 776. They may be missing from category tabs and reachable only by search. Not verified, and synthesizing `marketEntries` was not done. Every admitted crop has a market entry.

## Crop loop, checked against the server code

For each admitted crop:

- Buy: charged `cost` in coins at planting, or at storage purchase. The purchase path checks the World requirement (now refused on mismatch), the level, the balance, and the date window (removed).
- Plant: needs a plowed Home plot. Gives `plantXp` and the `plantCropByCode` quest action.
- Grow: `growTime` days, through `peaceful.grow_seconds`. Peaceful mode (default on) never withers it.
- Harvest: `coinYield` coins, `masteryYield` (up to 5) toward the crop's mastery counter, with the ladder's coins and XP at each step, and `largeCropXp` for the four large-crop records.
- Gifts: 41 mastery ladder steps across the admitted crops grant an existing sign (41 distinct `masterxaf_*` and `masterxwi_*` decorations, buyable false, no requirement) into the gift box. The other 155 steps name signs that are not in the catalog, so they grant nothing. Either way the harvest does not fail.

Not restored, for every Home crop and not only admitted ones:

- **Bushels.** The client's harvest response handling (`THarvest.onComplete`) reads `bushelItemCode`, then the response's `bumperCropFlag` and `foundBushel` keys decide the bonus popups. The server sends none of those keys (`commands.py` only models the plot and XP), and it does not restore the neighbour bushel feed (`TGetBushelRequestFeed`). So no Home crop yields a bushel.
- **Crop art.** Crop SWF art is not checked per crop. The client loads it from the recovered assets.

## Known limits and decisions to review

- **Conflicts with World status policy.** `STATUS.json` requires `crop_item_exclusivity` and the other rule gates to be verified before any world activation. This overlay claims no activation. It does open Home purchases of locked-world content that those gates were meant to keep out, except for the reserved worlds above. The 998 admitted crops are the largest part of that.
- **Crops admitted by rule, not by playtest.** The loop was traced in the server code and the client disassembly, and tested through the gateway for one crop. The other crops are not played.
- **Bushel leg not restored.** See Crop loop above. No Home crop pays a bushel.
- **World-currency items excluded.** Jade and berry items (3 locked non-crop, and 23 crops) stay locked. The conversion module `world_currency_conversion.py` is not used by the overlay.
- **Dates removed.** `limitedStart` and `limitedEnd` are removed for overlaid items, so expired seasonal offers become permanent. This is a policy choice. No admitted crop has a date window.
- **Experiment gates removed on locked non-crop items.** `experimentGate` values such as `fv_oz` are removed. They were world-launch flags. Crops keep their gate, which is served open. Exclusive items with an experiment gate are excluded.
- **Purchase guard gaps (pre-existing).** `creative_worlds.guard_market_purchase` on Home does not check `buyable`, prerequisites, or World requirements for non-crop items, and England reuses that branch. The overlay's exclusions are the only filter on the Home path for those items. The England refusal applies to overlaid items only. Crops are now checked on Home for their World requirement, at planting and at storage purchase.
- **Sibling "nearest" uses record order.** The catalog is roughly alphabetical, so the nearest priced sibling is usually a name-series neighbour. This is deterministic but not a semantic match.
- **Stale comment.** `commands.py` says no seed carries an `xpYield`. `wildflowers` does (1, Home-visible and not overlaid), so the comment is out of date. No admitted crop has one.
- **Derived-cache identity.** The client schema is `client-amf-v3`. Changes to `heritage_pricing.py` invalidate both the disk and memory caches.

## Tests

`macOS/Tests/test_heritage_pricing.py` (31 tests). Plan tests on synthetic records: the rule and derivation, exclusions and their counts, reserved-world and world-currency exclusion, the reserved list covering SPECS and the rule-module worlds, the disabled switch, determinism, `LAND_TERRAINS` equal to the recovered land terrain, each crop refusal reason (one case per reason, each refused with its name), crop coin pricing from the nearest sibling and from the subtype median, a crop with no price basis, the served-variant gate, and the server copy's refusal reason. Server tests: the real overlaid set (5,025), the 998 admitted crops at their recovered coin prices and the 959 refusals by reason, an admitted crop bought with coins, planted and harvested on Home at the recovered amounts (plow cost and XP, planting XP, coin charge, coin yield, mastery counter), an excluded crop refused on Home with its reason and no change to the save, home purchase charging the derived price, place-action charging once, England refusal, Meadows alias refusal, and client and server agreement.

`macOS/Tests/test_client_catalog.py` was adapted: two tests that assert the served catalog differs from the archive only by expired-buyable flags now expect the overlay's own mutation for overlaid records (5,025), and keep the strict check for everything else.
