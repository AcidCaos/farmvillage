# Engineering knowledge for community maintainers

The active products are the native macOS SwiftUI/AppKit desktop app and the browser game on Ubuntu/Linux. Sixteen worlds remain; iPad/iOS is abandoned and Enchanted Glen/Holiday Lights are retired. Use [TAKEOVER](../../../TAKEOVER.md), [current acceptance](../../../ACCEPTANCE.md), [current world readiness](../../../WORLD_READINESS.md) and [Wave 3](<../../../Wave 3.md>) as the current authority.

This index preserves authored technical findings that the initial code-only selection omitted. The historical documents explain recovered contracts and implementation reasoning. Their recorded test totals, candidate patches, old roster and earlier instructions belong to their dates/revisions; they do not add release acceptance or authorize activation/deployment. Raw QA material, original game payloads and generated catalogues remain external/private. Broken links to those excluded artifacts have been replaced with explicit descriptions, so their absence is visible.

## Persistence, protocol and reward boundaries

| Read | What it explains |
| --- | --- |
| [AMF rejection isolation](AMF_BATCH_ISOLATION.md) | Per-command savepoints, accepted neighboring actions, response envelopes and the client's FORCE_RELOAD behavior. |
| [Quest acknowledgement recovery](QUEST_COMPLETION_RECOVERY_2026-10-24.md) | Earned reward idempotency when a response/acknowledgement is lost. |
| [Quest world-score/currency rewards](WORLD_SCORE_QUEST_REWARDS_2026-10-24.md) | Trusted rewards versus general authored score/Beat restoration. |
| [Level progression](LEVEL_PROGRESSION_AUDIT.md) | XP, purchase eligibility and server/client availability boundaries. |
| [Travel-window recovery](TRAVEL_WINDOW_RECOVERY.md) | Original paged travel UI, local artwork and separate acceptance limits. |

## Farming, inventory and animals

| Read | What it explains |
| --- | --- |
| [Heritage pricing](HERITAGE_PRICING_2026-10-23.md) | Explicit local pricing policy and recovered-world exceptions. |
| [Bushel recovery](BUSHEL_RECOVERY_2026-10-24.md) and [implementation](BUSHEL_RESTORATION_2026-10-24.md) | Award callbacks, capacity, duplicate-grant boundaries and bounded local policy. |
| [Owned Market Stall state](MARKET_STALL_OWNED_STATE_2026-10-24.md) | Owned stall lifecycle and the separate client allocation issue. |
| [Water, fuel and energy](WATER_FUEL_ENERGY_2026-10-23.md) | Recovered service behavior, unresolved fuel accounting and explicit refusals. |
| [Well/irrigation rewards](IRRIGATION_REWARDS_2026-10-24.md) | Original metadata and persistent award targeting. |
| [Herb Garden harvest](HERB_GARDEN_HARVEST_2026-10-24.md) and [paid building actions](PAID_BUILDING_ACTIONS_2026-10-24.md) | Finite recovered harvest contracts and why unrelated prices cannot imply valid rewards. |
| [Mastery signs](MASTERY_SIGNS_2026-10-24.md) | Derived heritage sign definitions and save/catalogue boundaries. |
| [Animal naming](ANIMAL_RENAME_2026-10-24.md), [lamb raising](LAMB_RAISING_STATUS.md) and [pets](PETS_STATUS.md) | Original parameters, persistence and bounded supported interactions. |
| [Prize games](MINIGAMES_STATUS.md) | Local prize policy, retry boundaries and unsupported original mutations. |

## Crafting and client repair

| Read | What it explains |
| --- | --- |
| [Cottage recovery](COTTAGE_RECOVERY_2026-10-23.md) | Original ownership, reload and queue/callback shapes. |
| [Crafting expansion plan](CRAFTING_EXPANSION_PLAN_2026-10-24.md) and [implemented progression](CRAFTING_PROGRESSION_2026-10-24.md) | Paid skill progression, exact recipe rush identity and mastery gaps. The plan is historical; check current source before applying it. |
| [Cottage invitation presentation](COTTAGE_INVITATIONS_CLIENT_2026-10-24.md) | Keep UI offers aligned with supported server actions. |
| [Reviewed compatibility pipeline](ClientPatches/README.md) | Whole-body identity, composed stages, unchanged methods, verifier/branch requirements and historical failed candidates. |
| [Linear image rows](ClientPatches/IMAGE_ROW_LINEAR_2026-10-24.md) | Narrow renderer metadata selection correction. |
| [Inventory tab art](ClientPatches/INVENTORY_TAB_ART_2026-10-24.md) and [actual widget visibility](ClientPatches/WIDGET_STORAGE_VISIBILITY_2026-10-24.md) | Distinct legacy and widget inventory renderers. |
| [Market Stall fence](ClientPatches/MARKETSTALL_EXPANSION_2026-10-24.md) | Refuse unsupported client behavior before optimistic mutation. |
| [Quest close callback](ClientPatches/QUEST_REWARD_CLOSE_2026-10-24.md) | Original reward acknowledgement shape and narrow client handling. |
| [Ruffle candidate review](ClientPatches/Ruffle-runtime-candidate.md) | Historical runtime investigation, independent of the current pinned runtime provenance. |

Start regional work at [the world engineering index](Worlds/README.md). The pinned Ruffle source/build recipe lives under `FarmVillage/ruffle_runtime/`; the current client pipeline is in `client_compatibility.py` and `macOS/Scripts/patch-game-client.py`. Current source/tests outrank an older research note. Preserve original prices/timers, record unknowns explicitly, and test any proposed behavior on a fresh synthetic profile.

## Reproducing versus reading history

Use the repository root README for current environment setup and private-input import. Historical commands may mention a temporary checkout, `LocalData` environment, research archive or an excluded evidence file; those are provenance descriptions, not a working setup recipe. Matching private inputs are separately required for full regression/gameplay checks. Nothing here restores old player data or changes the clean-start release decision.

These references were curated from the handoff's authoritative Runtime revision `62809de497404588f133e38740242864717af0c0`. Owner-machine paths/hostnames are examples in this export. The curation adds knowledge; it does not claim a new full suite, native game pass, actual Ubuntu pass or release deployment.
