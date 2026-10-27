> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../ACCEPTANCE.md), [current world scope](../../../WORLD_READINESS.md) and [the continuation backlog](<../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Cottage upgrades and invitation presentation — 2026-10-24

The client now exposes its original coin/cash cottage-upgrade controls only for
bakery, winery, perfumery and pub. The server restores those four craft types,
111 authored recipes, paid upgrades and paid recipe rushes. Upgrade labels,
prices, skill-XP calculation, maximum level, region prerequisites, callbacks and
price tooltips retain their original implementation.

The supported-type predicate replaces a debug-variable span after the original
star loop. The completed loop's local6 is free at that point; it now stores the
Boolean used by the two button-visible assignments. The predicate uses existing
pool entries only: `pub` comes from the archived `xukcraftingpub.substr(11)`.
Its maximum stack depth is five, within the original method's maxstack 13. The
original maximum-level branch still hides both controls. Other craft types keep
hidden upgrade buttons; their original informational progress text remains.

Five remaining hard-coded invitations are recorded separately from the original
HUD blacklist in `FEATURE_INVITATION_INVENTORY.csv`:

| Method | Change |
| --- | --- |
| 34693 CraftingMainWindow.updateUpgradeFrame | Restrict the original visible-button branches to the four restored craft types; restore original upgrade text |
| 11246 MarketWindow.setupMarket3FTUE | Hide the selected full walkthrough and return before obsolete tutorial activation |
| 11244 MarketWindow.setupMarketVIPFtue | Hide existing tutorial artwork even when VIP sales are disabled; return before tutorial/seen state |
| 12394 MarketMiniVIPWindow.onLoadComplete | Keep the VIP-only sale banner invisible |
| 12402 InventoryWithdrawal constructor | Always select the original Inventory section |
| 12403 InventoryWithdrawal.onLoadComplete | Hide the underlying Expand and Shipping button overlays |
| 11987 StorageBuilding.showMenu | Skip the expansion menu item; retain original storage/look-inside actions |
| 38972 TurboPPHOnBoardingDialog.shouldShow | Return false before any action-count, player-state or transaction access |
| 5911 CraftingManager.showCottageReminderOnLoad | Return before the automatic popup and its transient shown flag |

Manual `CraftingManager.showCottageReminder` and free-cottage acquisition are
unchanged. The original Turbo/storage purchase refusals remain available for
other entry points. All water-popup and sprinkler-tutorial methods are unchanged.
No invitation seen flags, bonus Turbo charges, balances, quest progress or earned
rewards are manufactured by these presentation changes.

## Pin and composition

The previous storage stage remains recognized as
`4437fffbebb1737cfa3e68b5c2e9fc77e0d67056873378452834591d1fed0eb8`.
The final decompressed body is 21,521,041 bytes with SHA-256
`87ce6267b37dc9dc7a0c2b2e5b8ca7c2be462fefbe2d16fab36bacd4ff64169a`.
The first invitation-stage body `132d826e3f0fd5f55659b3019b4df5e753e30fd239a8b0822c8879e19999cfd5` is also recognized and upgraded.
A browser check exposed default-visible VIP artwork when sales are disabled:
the original outer gate skipped both hide assignments. A final pinned correction
retains the artwork-presence guard, bypasses that sales condition, hides the clip
and returns before tutorial/seen-state access. The emitted-code test includes
this disabled-service case with no player or sales-manager globals available.

The corrected separate-VIP body `2ebd48a123dac7089469d5f570137c6b67ea57094dc03626d70aa40efa0a159c` is also recognized and upgraded.
A later fresh-browser check still displayed the full category walkthrough with an
embedded VIP promotion. That renderer belongs to `setupMarket3FTUE`, rather than
`setupMarketVIPFtue`. The final three-byte stage returns after its original
market-size selection and `m_ftue.visible=false` assignment, before seen-state
reads, frame changes or tutorial button creation. Both small and medium paths,
absent artwork, ordinary-market method preservation and prior-stage upgrades
are covered by emitted-code tests. Final browser acceptance is still separate.

The archived source SWF remains unchanged. Every old known stage advances through
the same pinned chain; final builds are verified idempotently at different zlib
compression levels. Unknown bodies fail closed before writing output.

`ClientPatches/COTTAGE_INVITATIONS_CLIENT_BYTE_REVIEW_2026-10-24.json` lists exact offsets,
method hashes and same-length replacement spans. Comparison of all 68,492 method
bodies finds exactly these nine changes. No constant pool, method header,
exception boundary, existing branch operand, tag length or other non-code data
changes in this final stage. Tests reconstruct each historical stage independently.

## Validation

`test_cottage_invitation_stage` passes eight tests; `test_market_walkthrough_client` adds three tests, including execution of the
actual emitted supported-type predicate, coin/cash and level-cap paths, Inventory
section selection, hidden overlays, storage-menu branching and early returns
with no player/global/transaction objects available. It also checks the complete
method and non-code delta, source identity, review inventory, idempotence and
unknown-body rejection. The existing patch, graphics, upgrade-gate, Turbo,
storage, serving and feature-availability modules pass another 32 tests.

These are bytecode and Python runtime checks. Browser and native presentation
acceptance require the active synthetic-farm verification; this document does
not claim those checks were performed by the client patch task.

Later functional/presentation stages are documented separately in
`ClientPatches/QUEST_REWARD_CLOSE_2026-10-24.md`,
`ClientPatches/IMAGE_ROW_LINEAR_2026-10-24.md` and
`ClientPatches/INVENTORY_TAB_ART_2026-10-24.md`. They retain this invitation
stage as a recognized predecessor; its hash above identifies that historical
stage rather than the current full compatibility body.
