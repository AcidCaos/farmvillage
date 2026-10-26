# FarmVillage — Wave 3 community restoration plan

**Canonical future-work plan · 25 October 2026.** This file records uncompleted work after the macOS/browser stability and clean-start handoff. It does not launch the pasted twenty-agent proposal, create new chats, or declare those tasks complete. Assign one bounded lane against an identified baseline before implementation.

## 1. Decisions that override the older plan

- **Continue native macOS desktop and browser/Ubuntu/Linux. iPad/iOS is abandoned.** The desktop product is the existing SwiftUI/AppKit app with WebKit and the pinned web Ruffle player. Do not substitute the abandoned iOS Rust player or resume simulator/device work.
- **Sixteen worlds are supported. Enchanted Glen (`glen`) and Holiday Lights (`hlights`) are dropped.** They must have no unlock, travel or supported-play offers. Historical eighteen-world receipts do not authorize reactivation. Only a new explicit human instruction can restore either world to the release.
- **The next Bifrost release starts clean.** The owner authorized wiping every old save in the exact managed installation and said there are no existing released farms. Ship no previous farms, snapshots, player history, password hashes, session secrets or old environments. Do not add migration, retired-world compatibility, backup/restore promotion or old-farm recovery work to this release.
- **The clean installer is a complete guided journey.** Its README must follow precisely the same steps, with a warm, playful and respectful tone. It names its wipe target and refuses unrelated, source, linked and system paths. Wipe authorization is not permission for arbitrary deletion. Preparing a build does not authorize live Bifrost deployment.
- **Original costs, clocks and feature contracts remain authoritative.** Unknown rewards, probabilities, terrain and timers stay blocked. Synthetic funding, ready-crop fixtures and test grants are setup, not earned-play evidence. Restoring a helper does not automatically enable campaigns or inactive worlds.

These decisions replace the old proposal's eighteen-world roster, iPad/native-compatibility lane and legacy backup/migration program. Wave 2 remains historical implementation context. The final handoff's `README.md`, `ACCEPTANCE.md`, `WORLD_READINESS.md` and `SOURCE_MANIFEST.json` identify what was actually delivered and tested.

## 2. What is done, what is being checked, and what is still open

Planning baseline: Runtime `62809de497404588f133e38740242864717af0c0` (gameplay bytes unchanged from `4958c4836dd5fe1ee24dd59f686af53f4c3714f6`) and God Barn `31245bb8bc2848908667ae0cf95af8244531bff5`. Use the final handoff manifest if it names a newer integrated revision. Never pick an older sibling checkout by name or assume every contributor used the same base.

| Area | Current position | Wave 3 disposition |
| --- | --- | --- |
| Home/October, England, Meadows, Cove and Fields of El Dorado | Agents 1–5 delivered deeper bounded slices, not complete historical worlds. Ordinary play and selected production, storage, construction/container and original-client repairs exist. | Preserve them; extend exact missing variants. Do not recreate or reapply completed patches from the old prompts. |
| Other eleven supported worlds | Ordinary bounded crop/decorating/storage/travel/reload cycles have recorded acceptance. Mistletoe also has a separately checked Patisserie slice. | Restore regional systems one contract at a time. Basic play does not certify landmarks, production, scores, terrain or growth. |
| Sixteen-world roster | Integrated source removes Glen/Holiday from supported creation, travel and invitations; four fresh clean-start/roster cases pass. | Keep both retired worlds out of supported buyable, unlock and travel offers, entry pages and supported-play claims. Preserve historical catalogue records and their original IDs. No legacy migration is required. |
| Optional profile photos | Remote photos use the original no-photo fallback instead of interrupting offline/private-LAN startup. Local artwork paths remain supported; four focused HTML/AMF/save cases pass. | Preserve the narrow fallback and qualify final native/browser gameplay. Do not reopen the deliberately unavailable arbitrary image proxy. |
| Native macOS | The current sixteen-world production build compiled universally with warnings as errors. The production GameWebView/AppKit QA harness passed twelve actual crop loops, settled scenes and mature-art checks. The Mac then locked; four remaining native loops and three fresh post-restart visual checks are **UNRUN**. The earlier actual lifecycle/God Barn baseline is retained separately. | After the human unlocks the Mac, finish Oasis (`oasis`), Mistletoe (`htown`), Emerald Valley (`oz`) and Horseman's Hollow (`sleepyhollow`), then Home/Groves/last-world fresh restart visuals. The generic hidden-document condition is a confirmed host-session gate, not evidence of a world defect. Intel execution, distribution signing/notarization and long-session qualification remain separate. |
| Browser/server | Fresh sixteen-world HTTP/AMF passed 112 request/response pairs across two server generations. All sixteen browser scenes/HUDs passed on macOS; a genuine Groves plow/plant/original paid Instant Grow/harvest loop survived process restart. God Barn preview/apply/new-session snapshot restore and fresh returns passed. | These are separate scopes: one new browser crop loop is not sixteen new browser loops or actual Ubuntu execution. Older eighteen-world results remain historical. Preserve exact source/catalogue and the recovered QA process-interruption record. |
| Active regression selection | **1,909 current active/shared tests passed**, zero failures/errors/skips, with exact source stability recorded. The 51 retired-only cases are explicitly excluded with IDs/reasons, never counted as passes. | Preserve the selection contract and rerun affected shared tests; retain the raw historical failed-discovery/setup reports as history. |
| Code-only handoff | A history-free exporter, hash-checked BYO-input importer, source checks and private browser-runtime stager are implemented and exercised with synthetic fixtures. | Preserve allowlists and independent input validation; re-export the final merged source. Keep game assets and player state outside GitHub. |
| Guided clean install | A sixteen-world bundle with no previous player/authentication state and the original starter is prepared. Wizard/README have eighteen synthetic installer tests, including managed wipe, fresh environment/authentication, path/service refusal and network selection. | Actual Ubuntu installation, user service, sign-in/new-farm/restart remain **UNRUN** until executed on an Ubuntu host. macOS fixture tests do not close that gate. |
| Complete restoration | Regional feature admission, production variants, resource economies, prerequisites and many original reward/terrain contracts remain incomplete. | Use the lanes below. Missing original data is a named recovery blocker, not permission to invent behavior. |

This plan records the bounded handoff. Remaining native GUI work needs the human to unlock the Mac; actual Ubuntu execution needs an Ubuntu host. A locked test session is not a passed or failed game-world contract. Change a status only after evidence identifies its exact source and artifact.

## 3. Readiness and evidence language

| State | Meaning |
| --- | --- |
| `OPEN` | Not implemented or adequately investigated. |
| `SOURCE_IMPLEMENTED` | Source exists; required client/runtime acceptance is incomplete. |
| `VERIFIED_SCOPE` | Exact tests and actual client/native/browser evidence prove the stated subset on an identified source/artifact. |
| `RECOVERY_BLOCKED` | A named original contract, timer, reward, terrain record or payload is missing. Record the next artifact needed. |
| `EXCLUDED` | Intentionally outside this release, including the retired worlds and abandoned iPad. |
| `UNRUN` | A target/scenario was not executed; this is neither a pass nor automatically a defect. |

Keep four questions separate: does a world load, does ordinary play work, does a particular special system work, and was that exact combination tested on native macOS, a browser and actual Ubuntu? A screenshot, HTTP 200, unit pass or build answers only its own question. Never sum overlapping historical suites or promote one representative to all recipes/stages.

Every accepted change records its baseline and relevant hashes, original input/version identities, item IDs/world/feature scope, authored or explicit local policy, tests and actual UI actions, accounting/clocks, retry/reload/process restart, refusal behavior, artifact identity and remaining failures/UNRUN cases. Do not commit private QA saves, passwords, raw traffic or evidence to the public source.

## 4. Priority and practical sequence

1. Close the named platform gates: finish the four native crop loops and fresh post-restart visuals after the Mac is unlocked, then perform actual Ubuntu guided clean-install/new-farm/restart acceptance. Keep the sixteen-world offers and handoff consistent. Intel runtime, signing/notarization and longer-session qualification need separate evidence.
2. Classify unusable themed catalogue entries and publish shared-engine contracts. Diagnose unusability before changing admission; avoid sixteen independent versions of the same container or cottage protocol.
3. **Mediterranean Riviera is the next planned deep restoration lane, not completed work.** Start its Cafe/Craftshop/landmark/terrain work only as a new explicit task from the current integrated source.
4. Extend other regional worlds and the remaining agents 1–5 variants. Parallel isolated lanes are useful where ownership is clear; no contributor may assume another private patch is already merged.
5. Complete cross-world crafting, score/Beat/prerequisites, RPC/effects, fuel/Turbo and the local daily-token design with original-client accounting and new-farm persistence.
6. Integrate once, regenerate projections, repeat affected/cross-lane checks, build/play merged macOS/browser artifacts and qualify the new release on actual Ubuntu.

There are no invented hour estimates or mandatory agent counts. A blocked lane can return a precise research result while independent lanes continue.

## 5. Catalogue audit and semantic engine sharing

The full catalogue is broader than the sixteen-world release. Raw record count is not a count of usable regional features. The completed source-inventory audit at Runtime `4958c4836dd5fe1ee24dd59f686af53f4c3714f6` measured:

| Inventory measure | Result and exact meaning |
| --- | --- |
| Original catalogue | **111,206 raw records**, SHA-256 `14987fd4c07f9de35ff5092aeab58584802fd7fbeca1131ad1a5e3eee381a4d7`. |
| Effective served catalogue | **111,373 records**, SHA-256 `0f7903fb4d9eb4ceecd233341e525b38f504489e0d3d262576585d0831909e92`; derived/projection records mean this is a different denominator. |
| Active themed scope | **12 themed worlds**; Home, England, Meadows and Cove are four separate base worlds and are outside this themed denominator. |
| Distinct associated original records | **4,325** raw records associated with at least one of those twelve themed worlds. |
| Current themed admission | **1,258** of those associated records fall within the audit's current themed admission contract, including its exact regional feature exceptions. This is not 1,258 individually GUI-tested items; current date, level and other eligibility gates still apply. |
| Outside current themed admission | **3,067** associated records are outside that contract. **This is not a broken-item count.** The set includes intentional gates, special-engine paths, component/non-placeable records, missing contracts and out-of-scope systems. |
| Existing Home heritage overlay | **13,017 considered; 4,721 derived overlays** (4,421 locked-world and 300 exclusive). This is already implemented, not 4,721 new GUI passes or a new Wave 3 proposal. Do not add it to the themed counts: the scopes/methods overlap. |
| Duplicate values | One duplicated code value and two duplicated name values were found. Those are collision values, not proof of semantically interchangeable items or permission to merge them. |

The per-world counts below are static contract inventory, not gameplay certification. A record can be associated with more than one world, so these rows must not be summed as distinct catalogue items. Blocking-reason tags overlap and must not be added together. A separate supported feature engine can admit an item outside the ordinary themed guard; inspect its exact route before calling it unusable.

| Active themed world | Associated raw records | Within current themed admission | Outside current themed admission |
| --- | ---: | ---: | ---: |
| Fields of El Dorado (`rainforest`) | 543 | 133 | 410 |
| Mediterranean Riviera (`mediterranean`) | 483 | 134 | 349 |
| Fairytale Fields (`storybook`) | 314 | 108 | 206 |
| Sweet Acres (`candy`) | 420 | 101 | 319 |
| Oasis Gardens (`oasis`) | 385 | 120 | 265 |
| Emerald Valley (`oz`) | 522 | 172 | 350 |
| Toy Town (`toyland`) | 323 | 117 | 206 |
| Horseman’s Hollow (`sleepyhollow`) | 300 | 105 | 195 |
| Australia (`australia`) | 197 | 77 | 120 |
| Mystical Groves (`fforest`) | 508 | 93 | 415 |
| Mistletoe Lane (`htown`) | 193 | 61 | 132 |
| Atlantis (`atlantis`) | 162 | 37 | 125 |

The audit is an identified source inventory. C01 must now turn those records into semantic dispositions and actual feature acceptance; changing admission merely to reduce the outside count is not a valid objective.

`heritage_pricing.py` already re-homes eligible ordinary catalogue-only-world items to Home with a documented deterministic pricing policy. Preserve and audit that existing behavior rather than presenting it as new Wave 3 work. Reserved worlds include the active sixteen and both dropped worlds. Existing heritage handling does not authorize restoring Glen/Holiday travel or enabling their special systems.

Classify each audited original item under one primary disposition and secondary reason tags. Retain item name/code, world restrictions, client class/type, market/purchase prerequisites, feature/date/experiment gates, currency, capacity, recipe/production, timers/rewards and actual caller. Distinguish world-exclusive from shared records; report unique IDs and family counts without multiplying shared items into a misleading total.

| Disposition | Meaning and next step |
| --- | --- |
| `SUPPORTED_VERIFIED` | Exact purchase/place/use/store/reload accepted; preserve it. |
| `SUPPORTED_NEEDS_CLIENT_CHECK` | Source/automated contract exists; actual original UI/runtime remains unrun. |
| `ADMISSION_GAP_WITH_KNOWN_ENGINE` | Compatible engine exists; add exact world/item adapter, routing/projection and both allowed/refused cases. |
| `MISSING_AUTHORED_PARAMETERS` | Missing costs, ingredients, capacity, timers, stage/reward or transform data; recover before enabling/charging. |
| `MISSING_SERVICE_OR_CLIENT_CONTRACT` | Sender/callback/state transition is unknown or unsupported; capture it first. |
| `RUNTIME_OR_COMMUNITY_DEPENDENCY` | Original community/runtime process is required; a static price or grow time does not define it. |
| `DISPLAY_ONLY_OR_NONPLACEABLE` | UI tokens, intermediate products and references are not necessarily standalone purchases. |
| `RETIRED_OR_OUT_OF_SCOPE` | Dropped/inactive worlds, deferred campaigns and unsupported historical events are intentional exclusions. |
| `UNRECOVERED_REWARD_TIMER_OR_TERRAIN` | Missing probability tables, milestone timing, collision/shoreline masks or growth data blocks restoration; name the missing artifact. |

**Merge duplicate implementation behavior, not original IDs or authored differences.** Good candidates are ordinary storage ledgers, finite construction stages, compatible regional cottage queues, supported Orchard/Gnome/habitat containers and once-only receipts. A shared engine accepts explicit item/world contracts while retaining original names/codes, art, costs, capacities, clocks and rewards. IDs remain referenced by crafting, quests, mastery and collections even in a fresh-start release.

Practical implementation-reuse map (paths are relative to `FarmVillage/` in the reviewed handoff). Every candidate below is **OPEN contract/admission work**, not a newly enabled item or an instruction to merge original IDs.

| Working implementation to reuse | Candidate work | Differences that must remain explicit |
| --- | --- | --- |
| `crafting.py`: `REGIONAL_COTTAGES` / `REGIONAL_RECIPES`, with `themed_worlds.py` admission | Investigate cottage-compatible regional Cafe/Shop production using the existing Home/England/Cove/Mistletoe slices. Keep Craftshops separate until their actual queue protocol is proven compatible. | World owner, ingredients, recipe/skill levels, queues, original time/rush/currency, yield, mastery and claim callbacks. Do not rename a Cafe into a Bakery. |
| `storage.py`: `orchard_container_class` / `feature_container_class`, plus exact adapters in `rainforest_features.py` | Extend supported Orchard/Gnome/habitat/container families through explicit regional adapters, rather than building a new generic inventory for every world. | Occupant class and metadata, capacity, deposit/withdrawal, clocks, supported transform/output and inventory identity. Random bonuses and unknown offspring remain blocked. |
| `construction.py`: `manages` / `_next_upgrade`, and `paid_buildings.py`: `perform` | Reuse finite stage/material/payment/receipt machinery for compatible regional upgrades and finite landmarks. | Authored stage ladder, materials, charge, object replacement, once-only completion gift and world eligibility. Finite completion never establishes repeat-harvest loot or missing reward timing. |
| `cellar_progression.py`: contract/record/capacity helpers | Investigate remaining regional Cellar adapters, including Emerald and other named Cellars in the world lanes. | World-specific material/redemption rules, capacity, stored quantities, licence and transfer rules. Do not grant free capacity or combine separate world ledgers. |
| `themed_worlds.py`: `catalog_rules` / `guard_purchase` / `guard_action`, with `creative_worlds.py` terrain/date checks | Share ordinary crop/decor eligibility and refusal logic; review the exact retired-decoration candidates below under destination-specific contracts. | Original IDs, date/level/prerequisite/price/terrain gates and feature-engine routing. A matching class or picture does not authorize special buildings, rewards or a general animal/tree loop. |

Compare state machine, sender/callback, currency, queue/occupancy model, capacity, growth/harvest clock, finite versus repeat reward, ownership, retries and client class. Same art, superclass or name is not proof of equivalence. Keep adapters where semantics differ. Do not flatten special containers, nursery transforms or community buildings into Home buildings, borrow a neighbouring ladder's payout, or turn finite gifts into random repeat loot.

The retired-world inventory contains **172 Glen-associated raw records**, of which **91 pass only an ordinary-class screen**, and **591 Holiday-associated records**, of which **379 pass only that screen**. These are pre-gate research candidates, not approved market items, usable-item counts or permission to move every retired animal/crop/building.

A future catalogue-reuse proposal may review ordinary retired seasonal decorations for Mistletoe Lane, or ordinary Glen-themed decor for Fairytale/Mystical Groves. `cobblestonebridge` and `fairybed` are candidates to investigate, not approved admissions. Even a plain-class item such as `beatholidaylightsstatue` has reward semantics: keep it reward-gated rather than turning it into an ordinary sale or free grant. A suggestive name or class cannot establish valid entitlement, price, terrain or yield.

Any reuse must prove ordinary semantics, all original gates and destination eligibility/pricing while preserving original names/codes. It must neither reactivate either retired world nor silently relocate special systems. Unknown reward/timer/terrain or earned-event semantics remain blocked.

Deliver a machine-readable disposition table, human summary, candidate engine families, exact blocked parameters and an accepted sample per proposed family. The world owner and integration reviewer approve each new admission.

## 6. Shared-engine lanes

Each row is a future assignable lane. One owner per shared module in a checkout; others return separate patches/tests instead of overwriting it.

| Lane | Ownership and work | Exit and required checks |
| --- | --- | --- |
| **C01 Catalogue/admission** | Own disposition audit, exact item/world allowlists and projections; coordinate `items.py`, `themed_worlds.py` and catalogue generation. | Reproducible counts/denominators; original UI purchase/place/use and refusal on enabled samples; no charge/material consumption for unusable features; God Barn agrees. |
| **F01 Ordinary storage/cellar/shipping** | Reuse per-world inventory IDs, finite capacity and licensed transfers. Separate ordinary inventory from Orchard/Gnome/habitat contents and cellar credits. | Built/full capacity, quantities/metadata, source/destination charge, licensed/refused transfer, retry and new-farm reload/restart pass. No free capacity or item loss. |
| **F02 Crafting/production** | Preserve Home's four cottages, England Pub ownership/queues, Cove Restaurant, Herbal Hut and Mistletoe Patisserie slices. Separate cottages, Craftshops and reward-point goods contracts. | Ingredients/queues/skills/recipe levels, original time/rush/prices, claim/use/fuel, mastery/rewards and world partitioning pass. One recipe is not the entire roster. |
| **F03 Scores/Beat/prerequisites** | Separate quest rewards, ordinary score earning, thresholds and Beat completion. Preserve full prerequisite attributes; exact typed `feature_option`/`building_level` and bounded recursive `prereq_check`. | Trusted state; operators/AND/OR/cycle handling; unknown false; rewards once; forged/replayed reports cannot grant; HUD/reload/restart agree. Cove level-10 comparison is `lte`, not a guessed minimum. A Japan predicate does not activate Japan. |
| **F04 Treasures/terrain/growth** | Recover expansion-added objects, material/stage/replacement data, coordinates/rebasing, plot caps and shoreline/land/water rules. | Correct next size/authored charge once; required state/caps persist; no overlaps or ID collisions; invalid terrain refuses. Scenery is not a collision mask; growth stays closed where mandatory data is missing. |
| **F05 Special containers/finite landmarks** | Admit existing Orchard/Gnome/Stable/Nursery/Pigpen/finite-stage engines through exact regional contracts; distinguish offspring/seedling/transform rules. | Occupants/capacity/deposit/withdrawal/metadata/clocks/supported outputs/stage rewards and travel/restart pass. Grade finite completion separately from unknown random repeat loot. |

Historical quest counts (3,242 definitions; 404 with unsupported leaves: 399 named prerequisites, four feature options and one building level) are research inputs, not current measured release counts. Recompute against the chosen archive before claiming newly eligible quests.

## 7. Sixteen world lanes

The first five continue implemented slices; they do not recreate completed work. The other eleven preserve ordinary mode while regional systems are recovered and qualified. All lanes inherit the shared exits below.

| Lane / active world | Preserve | Next bounded work and explicit blocks |
| --- | --- | --- |
| **W01 Home / October** (`farm`) | Farming/Market/travel, cottages, water/wells, Herb Garden, bushels, paid finite construction, supported pets/breeding/rename, containers and mastery safeguards. October retains Home identity. | Close unexecuted mastery/sign/popup, supported flower harvest, pet/occupant and cosmetic cases. Test ordinary inventory separately from special contents. No claim that every recipe, event or social economy works. |
| **W02 English Countryside** (`england`) | Pub ownership/queue/skills, representative production, animal transformation, storage/shipping and travel. | Other recipes, higher construction/occupant variants, exact transformations and growth acceptance. Preserve new-profile names/DNA and clocks. Full campaign/authentic starter recovery remains separate. |
| **W03 Sunflower Meadows** (`meadows`) | Original access price/gift, farming/Instant Grow, storage growth/sale/transfer, and automated evidence for 32 expansion contracts. | Individually verify later expansion/UI variants, prerequisites, capacity and licence paths. Keep unsupported foreign placement refused; invent no bespoke mechanic to match another farm's feature count. |
| **W04 Lighthouse Cove** (`fisherman`) | Ordinary growth/storage/travel, Restaurant slice, finite Port/Cellar paths and original material/currency callbacks. | Higher finite tiers/shipping UI; recover shoreline/buildable geometry and special plots. Cove has no configured expansion-added-object list; do not borrow another world's treasures. Repeat Port loot stays blocked until recovered. |
| **W05 Fields of El Dorado** (`rainforest`) | Herbal Hut slice, Jungle Orchard/Garden finite engines, supported contents and owned Fountain visuals/placement. | Craftshop, artifacts/clearing, growth, regional habitats/Gnomes/cellar/shipping and authored score/Beat. Hidden Palace timing is recovery-blocked; Fountain visuals do not prove its complete reward lifecycle. |
| **W06 Mediterranean Riviera** (`mediterranean`) | Accepted ordinary mode, inventory and travel. | **Next planned deep lane, not started:** Blue Sea Cafe, Craftshop, Carnival Plaza, ruins, Riviera Orchard/habitats/Gnomes, growth and authored score/Beat. Pantheon Isle's owner fallback needs genuine reward timing. |
| **W07 Fairytale Fields** (`storybook`) | Ordinary crop/decor/storage/travel and exact feature fences. | Fairy Forum, Craftshop, Royal/Hill Castles, Jack's Mystree Nursery, signpost/door/bridge clearing, regional containers and growth. Mystree transform/reskin is not generic decoration or animal transformation. |
| **W08 Sweet Acres** (`candy`) | Basic mode and the original Candy Instant Grow carrier exception. | Sugar Shack, Craftshop, Candy Factory/Sweet Shop/Cellar, candy/marshmallow/rock-candy treasures, regional containers and growth. Candy's score tasks differ; do not copy another world's expansion points. |
| **W09 Oasis Gardens** (`oasis`) | Basic crop/decor/storage/travel and allowed Instant Grow behavior. | Cairo Boutique, Craftshop, Oasis Citadel, genie clearing, habitats/cellar/shipping and growth. Palace of Treasures needs its runtime/community contract; a price or zero timer is not a repeat-harvest implementation. |
| **W10 Emerald Valley** (`oz`) | Basic mode plus representative Emerald City finite-completion/Orchard engine evidence. | Porcelain Shop, Craftshop, Tin Man Fountain, debris/treasures, Emerald Cellar, Munchkin Orchard/habitats/Gnomes, shipping/growth and rainbow score/Beat. Engine evidence is not complete Oz admission; random repeat loot remains separate. |
| **W11 Toy Town** (`toyland`) | Ordinary crop/decor/storage/restart/travel and intentional presentation/refusal fences. | Food Van, Toy Mansion, treasures/containers/habitats, score/Beat and growth. Do not reintroduce optimistic unsupported expansion offers. |
| **W12 Horseman's Hollow** (`sleepyhollow`) | Ordinary cycle, isolated inventory, withdrawal/move/sale, reload/travel and presentation fences. | Witcher Hut, Town Hollow, tombstones/treasures, score/Beat and growth. Judge settled scenes separately from early loading frames. |
| **W13 Australia** (`australia`) | Ordinary crop/decor/storage/travel and Home-only variant refusal. | Daydream Island, Vineyard, mine clearing, regional feature contracts and growth. No general animal/tree loop is certified. Daydream reward timing remains recovery-blocked. |
| **W14 Mystical Groves** (`fforest`) | Farming/re-plow, isolated storage/reload/withdrawal/move/sale and travel. | Alchemist's Shop, Destiny/Unicorn Bridge, Ancient Oak/Willow Spirits, treasures and growth. Unicorn Bridge's owner fallback stays excluded until real timing is recovered. |
| **W15 Mistletoe Lane** (`htown`) | Full basic cycle plus the implemented 17-recipe Patisserie roster and representative recipe/skill-to-3 browser slice. | Individually accept the other 16 recipes/higher tiers, Holiday Square, Cheer and treasures/growth. Preserve local starter/theme disclosure and no unsupported animal/tree claims. |
| **W16 Atlantis** (`atlantis`) | Crop/storage/decor/travel, exact submarine carrier and regional inventory identity. | Original-client earned-sign placement, Coral Cafe, Palace/Garden, shell progression, authentic terrain/treasures/growth and applicable regional containers. |

**No W17/W18:** Glen and Holiday Lights are retired. Their old defects can remain archived research, but are not release lanes. Reactivation needs an explicit owner decision and its own acceptance, not a hidden allowlist edit.

## 8. Cross-world loose ends and resource economies

### D01 — RPCs, gifts and targeted effects

Re-audit before editing. `PresentService.receiveAllPresents` is already routed; giftbox error state exists for the local non-expiring model; retention callbacks safely grant nothing without authentic entitlement data; email acknowledgment exists without a fabricated gift; exact pet-food targeting exists; unsupported fetch/harvest already has atomic refusal. Do not duplicate handlers because an old prompt calls them missing.

Own small contracts in dedicated modules; one writer integrates `server.py` routing. Return a disposition table: sender, actual parameters, callback consumer, saved transition, cost/reward, retry semantics, source state and evidence. Priorities are exact Growable feeding/effects, NPC/static-world payloads and residual targeted consumables. Never invent an empty world or acknowledge an unpersisted mutation. Loading metrics is low priority unless a concrete gameplay failure is demonstrated. Do not revive external email/advertising services.

**Exit:** supported families have original UI/AMF use, target validation, duration, charge/withdrawal, retry, reload and restart; unknown effects refuse before consumption. Receive-all covers empty/multiple gifts and duplicate delivery. Gift pricing covers buy/send/regift, quantity/recipients and campaign/VIP parity. Unknown retention/email rewards are not granted.

### D02 — explicit client, Market and minigame cases

- **Land offers:** `farm14` and `farm16_cash` need exact eligibility, next width and original client/server pricing. Historical observations say 10,000 coins/eight neighbours for `farm14` and the recovered getter's one-Farm-Cash charge for `farm16_cash`; recheck the chosen revision instead of using an unreviewed raw field.
- **Bakery exclusive item:** identify the exact recipe/item/gate, then claim/use once; queues/goods/fuel/balances survive reload. An unrelated recipe pass does not close an interrupted exclusive-item case.
- **Minigame completion:** actual scratch win/replay, Pig-O set bonus/free play/post-win reload, and slot pending/free-spin/prize accounting. Retain disclosed substitute reward pools; do not rig product randomness to force a pass.
- **Archived promotional UI:** fresh browser checks still show original Membership and Oasis charity/community introductions. These are archived artwork, not evidence that any membership, donation or external community service works. Audit reachable offers and provide truthful local explanations or exact unavailable-action fences before presenting them as supported; do not invent a payment or charitable outcome.
- **Compatibility assets:** inspect grass `7`/`8.25` alias geometry/MIME/cache/rendering. The supplementary mastery route intentionally returns valid empty AMF while supported fallback definitions are inline. Verify active-world completeness/rendering instead of fabricating an authentic supplementary catalogue. Retired Glen sign data is not an active restoration task.

### M01 — complete fuel and Turbo economy

The server deliberately does not enforce equipment fuel spend while important refills remain client-only; unusable fuel/Turbo purchases are refused. Crafted-good fuel is mirrored already. Preserve that truthful boundary until the model is complete.

1. Recover/implement supported refills first: purchases, canisters/gifts, crafted goods, reward points, quests, buffs and unlimited-fuel entitlements. Preserve authored fractional values and metadata.
2. Add authoritative vehicle/resource/Turbo spend, exact footprint/multiplier, world eligibility and refund/retry rules only after refills are usable and saved.
3. Lift a purchase refusal only when that resource can be received, consumed and reloaded correctly. Do not charge fuel while valid refills remain stranded client-side.

**Exit:** sufficient/insufficient, free/unlimited, per-plot/equipment batches, rejected/forged requests, duplicate/replay, world switching, HUD and new-farm restart pass across all applicable sixteen worlds. A watering ledger is not a complete fuel economy.

### M02 — prerequisites and visible progression

Preserve full authored attributes and bump the derived-cache schema before enabling new predicates. Resolve named CMS prerequisites with typed operators, nesting, AND/OR, cycle/depth limits and trusted state. Audit every Beat dependency against earned completion. Unknown remains false. Supporting a predicate does not expose an inactive quest/world/campaign. Deliver an eligible-quest list only after its task/reward families and actual UI are accepted.

### M04 — truthful local daily token

Current watch-to-earn returns an empty token list because its ad network cannot complete; a local daily token is **not implemented**. The inherited local design is one token per player per day across worlds, documented configurable reset timezone, and America/Halifax as the local default.

First recover token type, consumer, saved inventory and prize/free-play contracts. Then present “Daily token” honestly: no fake advertisement, impression or third-party completion. Persist the claim receipt before success. Preserve distinct paid/earned tokens and other games' currencies. **Exit:** duplicate/concurrent claims, relogin/world switching, process restart, reset boundaries/DST, actual token use and once-only prizes pass on new farms.

## 9. Runtime, installer and handoff lanes

| Lane | Work | Exit |
| --- | --- | --- |
| **R01 Demonstrated player defects** | Investigate reachable shipped web Ruffle/WebKit/browser loading/cancellation, weak references, optional resources, rendering, memory and transport. Read actual callers and pins. | Authored minimal reproduction plus observed game impact; narrow fix and gameplay/reload/long-session regression. Stub warnings alone prove no cause. Do not enable arbitrary sockets, upgrade blindly or reopen iPad/Rust player work. |
| **R02 Actual Ubuntu clean installation** | Preserve the eight-step wizard/README sequence and managed-target refusal. Test on Ubuntu with a fresh target, new password and newly created farm. | Prerequisites, art staging, target confirmation, matching-service stop, clean publish, fresh venv/password, user-service/sign-in/creation complete. New-farm restart and actual served identities pass. No previous state ships; no unrelated path/service is touched. |
| **R03 Normal launch and persistence** | Keep development separate from the selected release, endpoint ownership, one data owner, clear errors and native Start/Stop/Quit/relaunch. Use new profiles. | Dev edits cannot mutate installed payload; normal saving/reload/restart works; failed setup/start never displays an unrelated server; owned processes stop cleanly. No legacy migration, backup promotion or old-farm recovery lane. |
| **R04 Source-only community handoff** | Preserve allowlists, explicit local roots, hash-checked BYO files, private runtime staging, licenses/attribution and curated docs. A future build-only import can distinguish the 1,841 build inputs from the two private regression fixtures; the current full-input contract has 1,843 files. Keep virtual environments outside the reviewed source export. Require Node for release/CI; label optional local skips. | Data-absent CI; missing/incompatible/corrupt/partial/linked input; repeated import; staging interruption/failure; full authorized-input builds pass. Source contains no game/media/WARC/generated catalogue, prior state, private history or evidence. No remote/push/deployment without a separate request. |

Full extracted artwork is an authorized external input, not a repository asset. A WARC is not an extracted asset folder. The wizard can stage selected artwork while erasing managed player state, but cannot silently retain farms, histories or credentials. Actual Ubuntu execution remains UNRUN until recorded; synthetic filesystem/service/process fixtures on macOS are a different result.

## 10. Shared acceptance for every feature and world lane

Document why any case is not applicable; do not omit it silently.

1. **New setup:** create a fresh named synthetic farm. Label test funds/levels/materials/ready objects separately from earned play. No old-profile migration fixture is required.
2. **Eligibility:** exact world, original item identity, level/date/experiment/licence/prerequisite, terrain and plot cap. Wrong class, retired world or unsupported target refuses without charge.
3. **Accounting/time:** original currencies/costs, trusted rewards and saved clocks. Insufficient resources and premature harvest refuse. Natural timers or original paid rush/Instant Grow are allowed; timer shortening is not.
4. **Actual client:** buy/place/use/claim through original UI and match callbacks. A successful direct API mutation is not visible gameplay acceptance.
5. **Inventory:** distinguish ordinary capacity/quantities from special contents/per-unit metadata. Store/withdraw/sell and world isolation persist; refused deposits lose nothing.
6. **Durability:** browser reload, fresh native document when relevant, owned server restart and Home→world→Home→world preserve newly created farms, clocks, queues, materials and balances.
7. **Retries/refusal:** preserve per-command savepoints. A valid preceding command can persist; a rejected command and its receipt roll back. Do not call the entire mixed batch atomic if it is not.
8. **God Barn:** correct selected farm/revision, exclusive park/edit, preview without mutation, explicit apply and fresh return document without stale overwrite. Editor changes are not earned rewards. Test new-session history; ship no previous history.
9. **Separate platforms:** source contracts, actual native window, browser graphics, Ubuntu execution and long-session memory each have their own PASS/FAIL/UNRUN. Intel compilation is not Intel gameplay execution.
10. **Identity/content:** exact source/pins/catalogue/God Barn projections, clean artifact inventory, no previous player/auth/environment files. Reference historical results without overwriting them.

## 11. Future assignments and final integration

Choose one bounded issue or feature family. Parallel isolated work is useful; nobody must wait idle before researching a contract, but contributors must not assume another private edit is merged.

- Record baseline revision and relevant hashes before editing. Declare owned world/features and shared files.
- Keep shared-engine patches separate from world adapters/admissions. One integration owner reconciles server routing, storage/crafting/progression and projections against each actual baseline.
- One writer per file in a checkout, one controller per owned native/browser/server session; distinct new data/cookies and unused ports. Other owners' processes and protected ports remain untouched.
- Return patches, tests, actual-client evidence, exact verified scope and a next source artifact for every recovery blocker. “Done” is not a substitute for that evidence.
- Use available capacity rather than the old instruction to create twenty chats. Do not activate retired worlds, campaigns or iPad incidentally.

Reusable assignment:

> Work on Wave 3 lane `<ID>` from the final handoff revision. Re-audit before editing. Own `<files/feature>` in an isolated checkout with a newly created synthetic farm. Preserve the sixteen-world roster, abandoned-iPad decision, original costs/clocks and truthful refusals. Return a shared-contract patch separately from world admission, affected tests, actual native/browser/client evidence, exact accepted scope and named recovery blockers. Do not deploy/publish or implement legacy-save migration, backup promotion or old-farm recovery.

After useful lanes complete, the integration owner:

1. Compares patches to actual baselines, preserves other work and reconciles semantic contracts rather than replacing files/remapping IDs blindly.
2. Integrates shared engines, exact world admissions, progression/resource/RPC consumers, then setup/export tooling; regenerates catalogue/God Barn projections from that source.
3. Runs affected and final suites with required tools. Missing Node, fixtures or private inputs are explicit setup/UNRUN outcomes, not hidden skips promoted to a pass.
4. Repeats cross-lane storage/container/production/score/reward, sixteen-world travel/reload/restart, God Barn, and implemented fuel/daily-token interactions on new farms.
5. Builds/plays exact macOS/browser artifacts and runs the guided new installation on actual Ubuntu, or reports that gate UNRUN and open.
6. Verifies no retired offers, prior state/environments or proprietary payloads/private history in the code export. The wipe stays inside the exact managed installation; no live deployment happens by implication.
7. Publishes manifests/checksums, per-world results, source-only/full-input test scope, accepted/excluded features, known failures and smallest next tasks in the handoff, without rewriting sealed history.

**Completion means the stated contract and target passed.** A safe bounded alpha can exclude unrecovered systems, but cannot advertise them as restored or charge for unusable actions. The next community contributor should be able to choose a precise issue without guessing what “all worlds work” meant.
