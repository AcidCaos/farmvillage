> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../../ACCEPTANCE.md), [current world scope](../../../../WORLD_READINESS.md) and [the continuation backlog](<../../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Themed Market presentation — 24 October 2026

Australia's Market displayed the unrestricted global `australianbarley` (`e8p`),
with a decorative `xau` ribbon, although the themed basic-mode server correctly
refused its purchase. The accepted Australian definition is `australianbarley2`
(`UYa`). The normal Market now uses the original world-specific class lock plus
derived catalog availability to match the basic-world admission boundary.

The original `HUDSkinConfig.parseWorldClassLock`11645 reads
`hudSkinConfig/showOnlyWorldMarketClassLock/className` into an array.
`WorldManager.initWorldSpecificClassLocks`2650 exposes it for the current world;
`FarmItem.isVisibleOnApplyWorldItemsOnlyCheck`6383 then requires an explicit World
restriction matching that world for each listed class. The existing Asia config
uses this same schema. All 292 recovered class names are covered on the exact 11
SPECS worlds. This includes an empty XML className: `FarmItem.className`6475 calls
`BaseDataSource.getString`13716, which converts a missing raw class to `''`.
Thus global crops need no item-record change to disappear in these worlds.

Three bounded derived item changes complement that original gate:

- Own-only items admitted in none of their themed owners have buyable closed.
  There are 2,505 candidate rows after excluding the 419 land-family rows. The
  direct raw-data delta is 892 fields: 822 true and 70 missing values become false;
  the other 1,613 rows were already false. The separate land policy still closes
  408 distinct expanded offers and preserves all 11 base 50 records.
- Of 85 rows mixing themed and legacy Worlds, 53 are admitted/priced and remain
  unchanged. The other 32 lose only their unsupported themed World alternatives.
  All 85 use compare=any; every legacy World and WorldLicense node stays intact.
- Exactly 32 global Inventory StorageBuilding records are priced/admitted across
  all 11 worlds. They gain World-any requirements covering the 17 currently
  supported legacy/themed worlds, so storage remains available through the lock.
  The other 81 raw global storage candidates are left unchanged.

No global crop or other global item record changes. In particular, e8p remains
available through its original legacy-world paths. All other fields, images,
mastery links, gift definitions and source files remain intact. Independent
review exercised 10,030 requirement truth comparisons across 59 non-SPECS worlds
and both license truth states without a difference. The only original World
alias is Meadows→farm; none aliases a themed world.

`themed_market_presentation.world_settings_payload(base_payload)` composes after
the existing October Home projection. It validates all non-Home source nodes,
adds only the 11 themed HUD locks, preserves Home/other legacy HUDs, and is
idempotent. The parent owns the route's Cookie Vary and no-store headers.
`client_catalog` includes this policy's source/SPECS/supported-world/catalog/XML/
template digest in memory and disk cache identity (schema v7). Frozen deployments
restart the process; the original archive is never rewritten.

The original `FarmItem.isVisible`6382 OR paths still permit owned seed packages,
valid licenses and deal-of-day entries. These imported gift/seed/license flows
are intentionally preserved. This is an ordinary Market presentation gate,
not a claim that every imported Gift Box action has been restored.

The JSON review (`../ClientPatches/THEMED_MARKET_CONFIG_REVIEW_2026-10-24.json`; external/private historical reference, not included in this source export)
records identities and exact counts. Independent source evidence (`ThemedMarketEvidence20261024/themed-market-review-findings-child-20261024.md`; external/private historical reference, not included in this source export)
and legacy truth checks (`ThemedMarketEvidence20261024/themed-market-legacy-truth-child-20261024.json`; external/private historical reference, not included in this source export)
are preserved with it. The existing SWF body remains
`c5aaff1f2ef9d60d4d2606ecac81ad7190d3f120b1500fb6b4e1d98ea4bbf589`.

Five dedicated emitted-visibility, actual catalog, legacy-truth and composition
checks passed in 38.694 seconds. Four final route/catalog/paid/land-cache checks
passed in 63.934 seconds. The Market memory/disk-policy invalidation check passed
separately. The split optional October checks remain exercised in the mixed
worktree and skip only that owner-specific integration in a surgical feature
tree. Actual browser verification belongs to the parent.

The same catalog pass also applies the paid-building owner's pure flower
projection: all 258 FeatureBuilding blooms lose only HarvestFManager. Every other
feature and catalog field retains its existing independent policy. The paid source
hash participates in both cache identities. See the paid projection review (`../ClientPatches/PAID_FLOWER_CLIENT_PROJECTION_REVIEW_2026-10-24.json`; external/private historical reference, not included in this source export).

After splitting the optional owner integration, the core Home/legacy projection, optional October composition and served-route checks all passed again: 3 tests in 36.320 seconds.

`HUDSkinConfig.loadFromXML`11644 calls the existing parser at byte297 and stores `m_worldSpecificMarketClassLock` at301; its complete loader disassembly is preserved in the evidence folder.

The final Htown progress-map correction removes only its authored
`actionMenuConfig/button[@name='WorldProgress']`. The original init handler51681
creates that dialog only while scanning a matching button's popup configuration.
Hallow owns the only other such button and retains it unchanged; the shared
`fv_xhw_enable_world_progress_icon` experiment stays enabled. No seen flags are
fabricated or added by the projection. The original first-visit skip callback
can still run before config lookup; that pre-existing behavior is unchanged.
Core, optional October and served-route checks passed again after this change:
3 tests in 36.853 seconds, with idempotence and all legacy nodes preserved.
