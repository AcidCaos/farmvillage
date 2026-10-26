> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../ACCEPTANCE.md), [current world scope](../../../WORLD_READINESS.md) and [the continuation backlog](<../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Other mechanics restoration — 22 October 2026

Scope: local source changes and disposable localhost verification. Nothing in
this report certifies or changes the Bifrost deployment. Deco work is stopped
at the user's request; its earlier uncommitted changes remain preserved.
The current release scope and final acceptance record belong to
`MECHANICS_RELEASE.md` (`MECHANICS_RELEASE.md`; external/private historical reference, not included in this source export). This report retains the earlier
browser findings and records the newly implemented bounded features below.

## This pass

| System | Implemented and tested scope | Remaining limitation |
|---|---|---|
| Quests | Recovered category/subtype harvests; gift/market purchase categories; completed construction and exact expansion levels; successful crafting claims. Rewards follow stored item identity. Duplicate requests, rollback, reload, and forged progress are covered. | Unsupported objectives, seasonal prerequisites, world score, and full crafting progression remain. |
| Crafting | Three starter recipes across Bakery/Pub; paid bushels, original production timers, ingredient consumption, claim, personal goods to fuel, durable queue and request retries. Normal cottage storage-info reads no longer abort startup. Locked recipe display states fix the Bakery window; catalog bushel capacity replaces the legacy template's five-bushel limit. | Bakery window, ingredient purchases, reload of purchased ingredients, and Make It to oven 0 verified in browser; saved queue uses the original six-hour timer and ingredients are consumed. Browser claim/fuel use remains pending; automated claim/fuel tests pass. More recipes, harvest bushels, upgrades, crew, neighbor trades, rush/cancel and other cottages remain. |
| Original sheep breeding | Parent eligibility, catalog potion costs and timers, cooldowns, offspring DNA, exact gift/placement/storage identity, reload, retries and rollback. New finished pens receive their catalog default ram. MutableAnimalBaby empty `contents={}` snapshots normalize to the Array required by its inherited loader; existing owned worlds are repaired without changing DNA or nonempty contents. | Earlier browser checks verified parent selection, five-potion instant breeding, ready-suite claim and a female lamb gift with full DNA and 3 pen breeding XP. The lamb has since been placed, and the farm draws after reload with its DNA preserved and contents normalized. Separate naming behavior, the full lamb-raising lifecycle and other animal families remain uncertified. |
| Construction | Turkey Roost, Orchard and classic Stable material completion; supported capacity expansions; Sheep Pen catalog upgrades of 15/20 per material to capacities 30/40, retaining parents and DNA. Disabled unsupported smart-build tuning so the browser uses the same base catalog counts. | Turkey Roost displayed 10 per material; the final Gift Box brick completed it. After server restart and browser reload it opens the completed My Turkeys view with capacity 20. Other families remain scoped. Retired unfinished Sheep Pen has unrecovered zero material requirements and is rejected before payment; latest finished-pen purchase is retained. |
| Original pets | A derived client catalog locally restores availability of 26 exact paid, undated puppy variants while preserving source data, prices and limits. Catalog-priced name/gender/variant purchase, kibble bonus, paid food packages, targeted feeding, follow/move, timed adulthood, daily treat training, runaway/rescue, exact identity and durable request receipts. | The browser bought a female gold Golden Retriever named Maple for 65 Farm Cash, placed her, consumed one of her 14 bonus kibble, and reloaded with her identity, one feed, 13 kibble and 957 Farm Cash preserved. Follow is separately scoped. Original fourteen-day adulthood and daily feeding/training timers apply. Reward-producing fetch/harvest tricks, generic pet storage and Pet Academy remain unsupported. See `PETS_STATUS.md`. |
| Owned-world travel | Home and England have distinct durable snapshots, global object/storage IDs and separate inventories. England follows the recovered level-15 all-access unlock. Inactive-world mutations and unsupported destinations reject explicitly. | England uses an empty catalog-sized local starter because the original starter layout is unavailable. Home→England→Home passed through the original travel flyout and both confirmations; Home returned with its buildings, lamb and original Bakery queue. Separate England placement/inventory browser acceptance remains pending; automated isolation tests pass. Freezing, seasons, shipping licenses, other destinations and themed progression remain unsupported. See `WORLD_TRAVEL_STATUS.md`. |
| Prize minigames | Slots, scratch cards and supported Pigo now persist payment/free-play balances and active results, validate requests and prizes, and protect same-session retries across server restart. Unsupported operations in these three service families reject explicitly. | Odds and prize pools remain bounded local substitutes. Pigo's physics-selected outcome cannot be authenticated from the original request; the server checks allowed prizes and payment. Browser spin/reveal/drop acceptance remains separate. See `MINIGAMES_STATUS.md`. |

Historical earlier-pass result, after capacity and breeding-wire corrections
and before the final explicit-oven correction:
**292 tests passed, zero failures, errors or skips**, runner elapsed 62.355
seconds. The final explicit-oven correction separately passed all 28 crafting
tests, including the real browser request, save reload, occupied-slot rejection,
and claim. The breeding core/wire suites passed 34 tests. The 22-module run covers persistence,
backups, barn actions, breeding, construction, crafting, core actions,
equipment, pricing, gifts/storage, levels, market, peaceful mode, progression,
quests and MOTD. It excludes Deco, client patches, packaging, native-device
and browser acceptance. Individual suite totals overlap this integrated run
and must not be added to it.

The final expanded integrated server regression passed **378 tests, zero
failures, errors or skips**, in 222.329 seconds. Six additional client-catalog
tests passed. See `MECHANICS_RELEASE.md` for final browser and packaging
acceptance; the historical 292-test result above is retained as earlier evidence.

The disposable farm completes startup without the former save-error overlay.
The Bakery and Sheep Pen windows now draw. The original QA parents required
full catalog DNA; geneless fixture parents were corrected with a byte-for-byte
backup before replacement. The subsequent placed-lamb reload exposed an
Object-to-Array loader error; the narrow empty-contents correction now passes
the browser reload, with the farm drawing and the lamb's saved DNA intact.
This does not establish every feature window works.

## The comparison list

The screenshot compares other server versions using an unavailable manifest.
Its percentages are not a completion metric for this checkout. The earlier
audit records existing source behavior; the scoped additions above do not
establish a complete original feature set.

| Screenshot row | Status for this checkout |
|---|---|
| Plow / plant / harvest | Existing home-farm implementation; integrated regression passed. Special crop modifiers remain scoped. |
| Place / move | Existing core implementation plus exact sheep/pet identity protection and active-owned-world isolation. Placed-lamb browser reload now draws successfully. |
| Sell / delete | Existing core implementation and retry protections; integrated regression passed. |
| Vehicles | Existing tractor/seeder/harvester/combine actions; integrated regression passed. All machine variants not certified. |
| Land expansion | Existing home-farm sizing/pricing remains covered. Owned travel supports Home/England, but this does not certify every alternate-world expansion family. |
| Inventory / gift box | Existing local transfers and metadata; integrated regression passed. Specialized families remain scoped. |
| Consumables / irrigation | Existing selected effects and water packages; integrated regression passed. Event resources excluded. |
| Withering / unwither | Existing peaceful-mode policy and limited neighbor path; regression passed. |
| Quests | Extended in this pass; partial overall. |
| Neighbors / visiting | Existing local and read-only template visiting; persistence regression passed. External social services absent. |
| Helping neighbors | Existing limited local helper actions; regression passed. All event helpers not covered. |
| Gifting between players | Existing local writable recipients; integrated regression passed. No external social-network delivery. |
| Avatar / wardrobe | Existing state and purchasing; pricing regression passed. Synthetic avatar setup succeeded in browser. |
| Crafting | New bounded server loop; browser acceptance scope recorded above. |
| Animal breeding / pets | Original Sheep Pen and bounded original puppy purchase/feed/training loops are implemented. Lamb placement/reload is browser-verified; named-puppy purchase/feed/reload is also browser-verified; full raising lifecycles remain pending. Other breeding families remain unsupported. |
| Building construction / expansion | Bounded original families added; other families remain. |
| Prize minigames | Slots, scratch cards and supported Pigo have durable balances, payment/prize validation and retry protection. Odds/reward pools remain local substitutes, and original Pigo physics outcomes cannot be authenticated server-side. |
| Travel to other farms | Neighbor visits remain. Owned travel supports Home and England with separate durable layouts/storage and an explicitly empty local England starter; the original UI Home→England→Home round trip passed. Other destinations remain unsupported. |
| Experiments served | No general original experiment-assignment service. |
| Player accounts / login | Existing local village selection/persistence; deployment access control is separate. |
| Ruffle | Disposable Codex browser loads the farm; individual feature acceptance remains necessary. No Safari/native-device claim. |

## Completion gates

1. Finish Bakery browser claim and fuel use after its original six-hour timer.
   No clock was advanced in this browser pass. Recipe controls, ingredient
   consumption and the durable oven queue have passed. Pumpkin Bread in oven 0
   finishes **22 October 2026 at 10:18:57 p.m. America/Halifax**. The browser
   collection/fuel/reload follow-up is scheduled for **10:20 p.m.**
2. Finish the remaining lamb naming/raising checks and the fourteen-day puppy
   adulthood/daily-training lifecycle. Puppy purchase, naming, feeding and
   full browser reload passed. Parent selection, instant breeding, ready-suite claim and
   placed-lamb reload passed; construction completion and reload passed.
   A protocol test does not replace a visible lifecycle check.
3. Home/England unlock and round-trip travel passed through the original UI.
   Further browser coverage can add independent placement and storage in
   both worlds; automated isolation and reload regressions pass. Preserve the documented empty England starter limitation.
   Other worlds require their own recovered contracts.
4. Finish prize-game UI checks and retain their local-substitute labels.
   Broader unsupported mutations, retired dependencies and other
   crafting/breeding/building families require separate bounded restoration.
5. The source review archive and separate private release candidate are
   packaged locally. All 16 private-candidate checks and five source-package
   tests passed; the release record identifies artifacts and verification. Nothing has been
   deployed to Bifrost, and no all-features-working claim has been made.

## Reproduction and evidence

Run `LocalData/venv/bin/python -B macOS/Scripts/run-other-mechanics-regressions.py`
from the FarmVillage repository. The runner imports isolated persistence fixtures
before product modules. Browser screenshots, source SHA-256 hashes and a
sanitized saved-state summary are in the workspace folder
`Browser Verification 2026-10-22/other-mechanics/` and
`Browser Verification 2026-10-22/mechanics-release/`.

Changes remain local and uncommitted. Source and private-candidate packages are built locally; consult `MECHANICS_RELEASE.md` for final artifacts and status.
