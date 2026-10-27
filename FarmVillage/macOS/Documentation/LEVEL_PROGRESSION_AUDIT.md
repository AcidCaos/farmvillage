> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../ACCEPTANCE.md), [current world scope](../../../WORLD_READINESS.md) and [the continuation backlog](<../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Level 1–100 progression and purchase availability

Updated 2026-10-23. Scope: local source and isolated synthetic test farms.
This document does not certify a 100-level browser playthrough or deployment.

## XP and reward verification

The preserved `gameSettings.xml.gz` contains exactly 100 original level rows.
`test_level_progression_1_100.py` checks each XP threshold, reverse lookup and
the point immediately below the next threshold. All 99 crossings from level 2
through 100 run through the actual AMF `WorldService.performAction` plow route:
15 coins charged, 1 XP earned, 1 Farm Cash awarded, same-session request replay
unchanged on disk and full save reload. A direct level 1→100 jump awards 99
Farm Cash once; `initUser` does not pay again. Three tests passed in 17.744s.

Those checks establish XP/reward progression. A Market card or event window at
the resulting level needs its own action, persistence and browser acceptance.

## Authoritative purchase gates

The audit reproduced two missing checks with real archived items over AMF:

| Trigger | Before | Corrected behavior |
| --- | --- | --- |
| Home level 1 buys `bushhorse` / `7T`, required level 6, price 100 coins | Placement and direct inventory purchase both charged and persisted | Both reject with error 29 before payment, XP, object or inventory changes |
| Home buys `xaf_herbalinn` / `0iux`, an unsupported Africa cottage | Placement and direct inventory purchase both persisted an unusable cottage | New Market acquisition rejects before mutation |

`creative_worlds.guard_market_purchase` is shared by paid placement and
source-less Market-to-storage. Home and England now check the original
`requiredLevel` before the balance/payment path. Supported tiered cottages use
`crafting.purchase_catalog_item` to select their original tier price, currency,
buy XP and required level; their parent item is not an unpriced free offer.
Each cottage purchase must have quantity 1. Bulk inventory acquisition rejects
before payment rather than applying one tier's price repeatedly to several
copies.

The same guard rejects `CraftingCottageBuilding` names outside the exact
restored roster in `crafting.COTTAGES`. The archive has 70 cottage records:
Bakery, Winery, Spa and Pub are the four restored base names; the other 66
require independent production restoration and acceptance. Existing world,
date and experiment rules still apply. These counts do not mean all 70 were
visible on a particular farm.

The gates apply to new purchases. They do not delete archived definitions,
gift rows or imported objects. Ordinary owned-object movement and inventory/
gift withdrawal keep their existing paths. Tests preserve below-level owned
decorations, original gift quantities/metadata, and imported unknown production
fields on a previously owned unsupported cottage.

The archive also has 41 array-valued level fields. The shared
`client_catalog.purchase_required_level` accepts the 29 repeated identical
numeric arrays as their scalar value. Twelve lamb variants conflict between
levels 1 and 15: their definitions and owned/gift data remain intact, their
derived purchase flag is false and new purchases reject before payment until
the contract is recovered. This helper also serves crop planting and existing
additional-world access checks. No minimum/maximum of conflicting values is
silently invented.

## Client availability and cache identity

The derived client catalog marks the 66 unsupported cottage records and the
12 conflicting-level records `buyable=false`. Every one of the 111,206 records remains present, with every
other field retained. Original assets/catalog bytes and server item definitions
are unchanged. The existing expired-offer and exact 26-puppy transformations
remain separate.

Derived memory and disk caches include the SHA-256 of `crafting.py`, in addition
to the item source, client-catalog decoder, day and AMF library version. A later
reviewed change to the supported cottage roster therefore regenerates the
client purchase flags. The disk cache schema is `client-amf-v2` plus those
identities. Tests change the policy identity, verify stale memory and disk data
are replaced, then prove the new valid disk cache is reused after restart.

## Focused validation

| Suite | Result | Scope |
| --- | --- | --- |
| `test_level_progression_1_100.py` | 3 passed, 17.744s | 100 boundaries, 99 real AMF crossings, retry/reload/reward |
| `test_market_availability.py` | 10 passed, 27.249s | Home/England below/exact level, both purchase routes, original price, placement replay/reload, all 66 cottage gates, single-cottage quantity, conflicting levels, repeated-level real crop packet, owned/gift preservation |
| `test_client_catalog.py` | 9 passed, 86.662s | All 111,206 original records and field differences, exact 66 cottage and 12 conflicting-level flags, 29 repeated levels, 26 puppy restoration, expired offers, dependency-aware memory/disk cache |
| `test_construction_wire.py` | 10 passed, 16.400s | Sheep Pen paid placement fixture uses original level 5; accepted calls require per-command success, with material/expansion retry/reload behavior preserved |
| Original four diagnostic probes rerun | 4 rejected with error 29 | Zero money/XP/object/inventory changes after reload |

The focused suites do not certify every catalog item's lifecycle. The parent
workspace's `Progression Audit 2026-10-23/` contains the complete level/catalog/
prompt/startup ledgers, baseline and corrected probe observations, original
client method disassembly and test logs. Right-side event and startup-window
availability is documented separately in `FEATURE_AVAILABILITY.md`.

The full-suite pass initially exposed a fixture that purchased a new Sheep Pen
at level 1 despite its original required level 5. The fixture now starts that
paid placement at the exact catalog threshold; existing owned/gift construction
continues to work below it. The construction test helper also checks the AMF
per-command result, preventing HTTP 200 from masking an error 29. No product
gate was relaxed for that correction.

Run from the FarmVillage root:

```sh
LocalData/venv/bin/python -B -m unittest discover -s macOS/Tests -p test_market_availability.py -v
LocalData/venv/bin/python -B -m unittest discover -s macOS/Tests -p test_client_catalog.py -v
```

No deployment was performed by this workstream. Browser acceptance and any
server deployment must be recorded against the final integrated source.
