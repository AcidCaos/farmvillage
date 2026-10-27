> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../ACCEPTANCE.md), [current world scope](../../../WORLD_READINESS.md) and [the continuation backlog](<../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Missing heritage-crop mastery signs — 24 October 2026

`mastery_signs.py` supplies 155 **derived local fallback** definitions for missing
gifts named in the original mastery ladders of Home-admitted heritage crops.
These definitions reuse original assets; they are not recovered original crop
sign records or original crop sign artwork. Gift-box thumbnails use the crop's
own icon. Placed signs use the existing animal mastery sign frame with that crop
icon inserted by the original `DynamicMasterySign` renderer.

The original catalog contains 1,545 working `DynamicMasterySign` definitions,
but 1,504 seed mastery gift names have no item record. Of those missing names,
155 belong to crops admitted by the heritage pricing plan. The fallback is
restricted to that set. Existing reward records always take precedence. It
does not admit another crop, alter a mastery threshold, change its authored gift
name, grant mastery on load, or put a sign on sale.

## Recovery evidence

The four full asset CDX indexes linked by
[the original-farmville archive metadata](https://archive.org/metadata/original-farmville)
were downloaded and searched: 396,839 lines, no `masterysign_items` or
`/masterysigns/` catalog match. Exact public web searches for the catalog filename
and FlashVar returned no results. The recovered master asset hash has no matching
original `cropmaster_<seed>_icon.png` entries for these 155 crops. This establishes
the gap in the checked sources, not the absence of a catalog in every archive.

The copied original FarmGame SWF proves the fallback's rendering contract:

- `DynamicMasterySign.<cinit>` (48547): `masteredItem`, `static`, and `holder_mc`.
- Constructor (48550): load the `masteredItem` image with the original loader.
- `onIconLoadComplete` (48551): skew/center the recovered icon and add it to the sign.
- `getCurrentImageName` (48552): use the `static` frame.
- `replaceContent` (48555): reinsert the loaded icon when frame content changes.
- `tooltipNotes` (48549): resolve the mastered crop through `masteredItemCode`.

All derived rows use the original `assets/misc/animalmastery_sign.swf`, `loadClass`
`mc`, `overrideExportName` `animalmastery`, and `imageScale` `1.5`. Every frame and
crop image reference exists in the recovered master asset hash. No new art or
guessed asset URL was added. The fallback omits the animal template's purchase
price, sets `buyable=false`, and has no market entries. This closes even Home's
legacy direct purchase path, which checks price availability without reading
the buyable flag.

The derivation evidence JSON (`MASTERY_SIGNS_DERIVATION_2026-10-24.json`; external/private historical reference, not included in this source export) records
source hashes, checked CDX hashes, exact client methods, and all 155 mappings.

## Catalog and save behavior

Server and client derive records from the same pure function before heritage
pricing rehomes the source World requirements. The original 111,206 records stay
in their original order; 155 definitions append in authored gift-name order.
Codes use `fvlocal_mastery_` plus a full SHA256 of the gift name. The local
namespace distinguishes them from original codes, and avoids `:`, the client's
storage metadata delimiter. Conflicting owners or codes fail closed.

The source AMF and recovered JSON cache remain unchanged. Server additions live
in memory, while the derived client cache includes the fallback module and
heritage policy digests in its identity. The ordinary served item payload carries
the definitions, so the unavailable supplementary `/masterysigns/v1/` catalog
does not require a fabricated original payload.

The existing progression protocol now resolves these authored gift names and
deposits each newly earned reward into the gift box once. Normal gift withdrawal
places the sign without charging coins, cash, or XP, and its ordinary item name
and class persist across save/reload. Already mastered historical saves are not
automatically backfilled: without a persisted award ledger, load-time repair
could duplicate previously placed, stored, or deleted rewards.

## Verification

`macOS/Tests/test_derived_mastery_signs.py` covers the exact 155-row boundary,
unique codes and authored names, recovered image references, original record
preservation, append idempotence, existing-definition precedence, excluded crop
gates, client/server equivalence, pristine source/cache, policy cache invalidation,
and the real AMF harvest → mastery reward → gift placement → disk reload flow.
It also verifies that market purchase is refused. The existing client catalog
preservation test accounts for the appended records and still checks every
original record in order. Browser and native visual acceptance remain separate.

Focused result: `python -m unittest test_derived_mastery_signs test_client_catalog -v`
completed **17 tests in 161.198 seconds, OK**. All writes used the temporary
`test_persistence` harness; no owner save or running production server was used.
