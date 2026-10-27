> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../../ACCEPTANCE.md), [current world scope](../../../../WORLD_READINESS.md) and [the continuation backlog](<../../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# W01 Home and Quintessential October — bounded source candidate

Baseline: FarmVillage `845de48027ac82bbf0ab07da91336d1becb57273`, audited on
24 October 2026. This is a private patch candidate; the coordinator owns canonical
Wave2 status and integration. No Bifrost deployment, native adoption or release
qualification is implied.

October remains creation preset `quintessential_october` on world `farm`, with
Home prices, clocks, inventories and feature rules. Existing starter objects,
provenance and already earned progress are preserved.

| Feature | Implemented contract | Acceptance boundary |
| --- | --- | --- |
| Cottage mastery | Existing admitted recipes use authored recipe-level thresholds, coins/XP and sign codes. Accepted OnMake progress emits the original RecipeMastery goal/popup contract. Existing signs update, missing signs enter the Gift Box once; placement derives earned stars. | Synthetic AMF covers four Home cottage types, all five tiers of the representative Bakery recipe, sign placement/move, rollback and reload. Imported already-mastered recipes receive no retroactive rewards. No social sales implementation. |
| Ordinary flower crops | Existing seed farming engine and catalogue yields. Harvest records fallow state even when a stale growing snapshot is submitted, preventing a second payout. | Sunflower acceptance is distinct from FeatureBuilding full-bloom flowers. Existing real grow durations remain unchanged. |
| Full-bloom flowers | Existing paid feeding/upgrading, material metadata and server clocks are retained. | RECOVERY_BLOCKED: all 258 FeatureBuilding blooms use an unrecovered HarvestRewardGenerator. The full-bloom `chance=5` field is not enough to define a payout distribution. Harvest and paid readiness refuse atomically; no deterministic substitute or invented bulb reward. |
| Pet lifecycle | Existing named puppies, original food targeting, fourteen-day growth/training, following, runaway/rescue and retry behavior retained. | Golden Retriever fetch and Border Collie harvest tricks still refuse without losing pet/food/clock. Authentic reward-producing tricks remain RECOVERY_BLOCKED. |
| Breeding | Existing Sheep Pen DNA, names, babies and paid construction preserved. Specialized animal storage now enforces built ordinary inventory capacity and authored Sheep Pen stages 20/30/40, rejecting ambiguous identities/ledgers. | Synthetic named-DNA round trips, full/overflow/recovery and October refusal cases. No invented genetics, rewards or shorter clocks. |
| Ordinary inventory | Real completed storage buildings supply slots; inherited ceilings are ceilings. Canonical active-world negative IDs and exact source/target identities are enforced. | Independently graded from positive feature containers, with capacity and cross-world refusal checks. |
| Orchards and Gnomes | Existing exact admission/filter/stage engines retained; new transaction replay handling applies to generic stores. Orchard clocks and per-unit metadata remain authoritative. | Existing Orchard/Gnome suites plus separate W01 boundary tests. Random Orchard bonuses remain unavailable. |
| Home animal habitats | Seven exact completed base owners admit only ordinary Animal occupants from original storageConfig name filters. Capacity derives from the authored stage. TStoreItem applies the recovered 4% anti-stuffing clock adjustment once per transaction; it does not change grow duration. Move/placement snapshots cannot forge contents, clocks or stages. | Storage only. Unknown/special/mutable occupants refuse; imported contents can be withdrawn for recovery. Random breeding/offspring harvest generators remain RECOVERY_BLOCKED and harvest refuses atomically. |
| Cosmetics | Coin/cash purchases charge original price and XP once; ownership survives retry/reload. Wearing validates known free/earned/bought cosmetics. Trusted imported worn garments remain in wardrobe after changing outfits. | AMF purchase/wear/reload and refusal checks; existing alternative-graphic/featured-item persistence retained. Building paint remains excluded. |
| Existing Home engines | Farming, cottages, bushels/owned stalls, wells, Herb Garden seed paths, paid construction, breeding rename and mastery-sign implementations reused. | Related regression suites, with authentic October fixture preservation. Off-server social economies and historical events remain outside scope. |

Original-client interactive acceptance remains OPEN. The owned browser fixture
reached the Home scene, but the available Ruffle Canvas renderer threw
`Render backend does not support BitmapData.draw` during enterFrame and
saveAvatar; no farming, mastery-popup or cosmetic UI pass is claimed. This is a
renderer gate, not evidence of a server mutation succeeding. NativeRuffle,
installed apps, simulators, iPad projects and real saves were left untouched.

The private delivery includes per-file baseline/candidate hashes, separate
shared-engine and world-acceptance patches, raw AMF requests/responses and
settled synthetic saves, regression receipts and exact browser diagnostics.
Fixtures explicitly seed near-threshold skill, mature crops, trained adults or
capacity contents as preconditions; those values are not earned gameplay.
