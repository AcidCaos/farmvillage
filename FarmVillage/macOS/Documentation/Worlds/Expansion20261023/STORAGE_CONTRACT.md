> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../../../ACCEPTANCE.md), [current world scope](../../../../../WORLD_READINESS.md) and [the continuation backlog](<../../../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Signed inventory identity and HUD fallback evidence

Snapshot: 2026-10-23. These are original-client disassembly findings, not observed save migration or browser packets. See the source SWF digest in ARCHIVE_INDEX.json (`ARCHIVE_INDEX.json`; external/private historical reference, not included in this source export).

## Inventory namespaces

`pushbyte` values must be interpreted as signed bytes. Fresh `abcdis.py` output from a scratch copy recovers the WorldManager inventory constants in client-storage-disassembly.txt (`client-storage-disassembly.txt`; external/private historical reference, not included in this source export). Earlier unsigned displays such as 241 for -15 are not additional storage IDs.

| World | XML storageId | Client constant | Consequence |
| --- | --- | --- | --- |
| Mistletoe Lane / htown | absent | -15 | Client namespace recovered; XML absence does not establish original starter theme. |
| Enchanted Glen / glen | absent | -18 | Preserve imported summary identity and terrain. |
| Atlantis / atlantis | absent | -19 | Preserve imported summary identity. |
| Australia / australia | absent | -21 | Namespace recovered from client; no guessed fallback ID. |
| Mystical Groves / fforest | -24 | -24 | Agrees across these two sources. |
| Holiday Lights / hlights | -24 | -25 | Hard conflict with fforest. Keep imported identity unresolved. |
| Horseman’s Hollow / sleepyhollow | -33 | -33 | Agrees. |
| Toy Town / toyland | -34 | -34 | Agrees. |
| Savannah Safari / africa | -38 | -38 | Agrees. |
| Phantom Valley / transylvania | -39 | -39 | Agrees. |
| Alpine Jingle / winter | -40 | -40 | Agrees. |
| Namaste India / india | -41 | -41 | Agrees. |
| Story of Sakura / japan | -42 | -42 | Agrees. |
| Caveman Club / jungle | -43 | -43 | Agrees. |
| Ode to Olympus / mount | -44 | -44 | Agrees. |
| El Carnaval / limbo | -45 | -45 | Agrees. |
| Once Upon a Winter / xmas | -46 | -46 | Agrees. |
| Groovy Hills / midwest | -47 | -47 | Agrees. |
| Legend of Tengguan / turtleisland | -49 | -49 | Agrees. |
| Maple Frontier / canada | -75 | -75 | Agrees. |

The client does not derive every runtime inventory from this constant list. `WorldSummary` constructor method11402 (`WorldSummary.as`, original debug lines42–56) copies the `storageId` supplied in the server summary. Method11403 returns that field. `WorldManager.getStorageIdByWorld` method2714 (original debug lines1571–1581) uses the matching summary’s ID; with no summary it falls back to Home storage -2. `isValidInventoryStorageId` method2743 checks the accepted namespace list. The disassembly contains these methods and their instructions.

Therefore, the HLights client constant identifies an original namespace but does not authorize rekeying an imported `-24` inventory. Recover the original server summary or provenance of that import and prove separation before activating it. Never merge/reassign fforest inventory based on its overlap with the HLights XML typo. Ownership, capacity, stored objects, giftbox, active world and shipping licence are different state concerns.

## Instant-grow carrier fallback

client-hud-disassembly.txt (`client-hud-disassembly.txt`; external/private historical reference, not included in this source export) contains `WorldSettingsManager.getWorldSpecificPlaneItemName`, method5265. It begins with the caller’s second argument, looks up the active world HUD config and replaces the value only when `instantGrowItemVisual` provides a non-null name.

client-plane-callers.txt (`client-plane-callers.txt`; external/private historical reference, not included in this source export) contains two callers: `AMAirplane` method49409 and `CInstagrow` method28536. Both pass `AMAirplane.DEFAULT_AIRPLANE_ITEM`. The original class initializer method49408 sets that constant to `biplanered`.

Thus Australia, Mistletoe Lane and Enchanted Glen, whose archived HUD configuration omits that visual, have an original `biplanered` fallback. Toy Town, Horseman’s Hollow and Mystical Groves have explicit world visual records. Atlantis explicitly uses `xalsubmarine` / `ht9`, an Airplane catalog record lacking a World requirement. Any temporary-object exception must match that exact original record and Atlantis context; it is not authority to buy, store or place arbitrary vehicles.

These instructions establish control flow. Each world still needs real original-client evidence for temporary plane/object payloads, charge/consume authority, cleanup, stale requests, refunds and replay behavior.

## Htown theme boundary

The archived Mistletoe expansion omits `startingFarm`, `startingTileSet`, `storageId` and prefix. Yimf contains the original `htown_theme` record, twice identically in the recovered archive. A search of recovered XML and relevant client initialization did not establish an original fallback assignment to that theme. `HtownWorldInit` method29766 initializes the superclass, DecoPointsManager, a progress window and a right-HUD icon; it supplies no recovered starter-theme mapping.

An empty local starter using `htown_theme` can be an explicit, reviewed product choice under the user’s themed-farming request. Document it as local behavior rather than restored original populated-starter evidence. Missing original fields must never trigger an overwrite of a newer imported farm.
