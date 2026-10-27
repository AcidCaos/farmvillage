> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../../ACCEPTANCE.md), [current world scope](../../../../WORLD_READINESS.md) and [the continuation backlog](<../../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Mistletoe cottage admission — 2026-10-24

**Implemented in the actual `worlds-2026-10-24` worktree; uncommitted for root review.** Actual-source focused validation completed with **173 tests passing**. No browser or listening server was opened, and all saves/cache used disposable unit fixtures.

## Resulting behavior

Mistletoe Lane admits only its original `xhdcraftingcottage` / `xhdcrafttype` / `CraftingCottageBuilding` identity, code `7la`. Authored tier one costs 100000 coins, grants 1000 buy XP and requires level 15. Live gift/owned counts select the original subsequent tiers: tiers two and three cost 80 cash; no later tier is guessed.

The changes do not add `CraftingCottageBuilding` to `BASIC_CLASSES`. The source audit confirms `SPECS`, `ACTIVE_WORLDS` and `BASIC_CLASSES` are identical to the pre-change revision. No new world contract or activation was integrated in this task.

## Source changes

- `themed_worlds.py`: narrow class and `instance_tiered` exceptions delegate identity/world validation to A's `crafting.regional_cottage` helper, with the catalog's craft type mapping also checked. Other world, feature, prerequisite, quest, license, availability and experiment refusals remain in force.
- `catalog_rules` obtains the detached `crafting.regional_catalog_item` preview before determining catalog price. A malformed recovered tier remains unpriced/unadmitted.
- `guard_purchase` resolves the canonical catalog record through **live** `crafting.purchase_catalog_item(save, source)` before checking level, date, currency and balance. It validates code/class/craft identity and quantity one. Supplied prices or a cached tier-one preview cannot authorize a later purchase. The ordinary alternate-cash fallback does not apply to a regional tier.
- Snapshot and placement guards admit only the exact cottage identity/world/class, preserve valid imported opaque fields, and refuse class relabeling or unsupported cottages without modifying memory or existing disk bytes.
- `world_travel.py`: the existing Home-only placement guard now has the same exact regional helper exception. Other non-Home cottages retain their original refusal. This additional gate was proven necessary by a real signed AMF placement test.
- `macOS/Tests/test_htown_crafting_admission.py`: 12 native tests now import actual worktree modules directly. There is no temporary-module override or fixed external evidence write in this test file.

A's helpers were already integrated as B commits `3bf82bf` and `93717ad` (from A `de14ac6` and `1737ab6`). No crafting source or existing test file was edited by this task.

## Validation

Run from `macOS/Tests` with the independent worktree environment:

```sh
PYTHONPATH=../.. PYTHONDONTWRITEBYTECODE=1 ../../LocalData/venv/bin/python \
  -B -W error::ResourceWarning -m unittest \
  test_htown_crafting_admission test_themed_worlds test_themed_inventory \
  test_themed_dual_prices test_crafting_expansion -v
```

The process finished with exit code 0:

```text
Ran 173 tests in 46.131s

OK
```

The run includes all 12 new admission tests, the existing themed-world/inventory/dual-price regressions, and A's 12 Mistletoe crafting expansion tests. It exercises actual catalogs and signed AMF gateway calls without binding a port. `git diff --check` also passed.

Coverage includes exact helper identity/world/class, unchanged global classes, retained special gates, detached immutable previews, live tiers 1–3, missing tiers, minimum level, forged preview fields, invalid currencies/quantities/gifts, short wallets, limit one, snapshots, signed coin/cash placement, retry charging, disk reload, world round trips, imported fields and atomic wrong-world/other-cottage/class-spoof refusals. Existing farming/storage behavior and 21 authored same-code cash alternatives also pass.

The signed purchase's wrapping observer runs the real XP function and verifies the authored 1000 XP increment separately from normal quest rewards. This fresh fixture additionally earns 50 and 100 quest XP; those rewards remain enabled. Signed level-30 fixtures avoid an incidental level-up cash reward; level-14 refusal and level-15 admission are checked separately.

## Evidence and remaining acceptance

- Actual-source test log (`SessionBHtownCraftingEvidence20261024/actual-source-focused-tests.log`; external/private historical reference, not included in this source export)
- Source hashes, unchanged-scope audit and command (`SessionBHtownCraftingEvidence20261024/actual-source-manifest.json`; external/private historical reference, not included in this source export)
- Exact two-file source diff (`SessionBHtownCraftingEvidence20261024/source.patch`; external/private historical reference, not included in this source export)

This replaces the earlier temporary proposal result (161 tests passed) with actual-source validation. The client upgrade predicate and browser acceptance remain separate work; no browser acceptance for the 17-recipe UI is claimed here. No commit was created. Root owns review/commit, after which shared-source ownership can return to the world integrator.
