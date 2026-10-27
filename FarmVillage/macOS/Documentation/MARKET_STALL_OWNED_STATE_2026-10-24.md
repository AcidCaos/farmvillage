> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../ACCEPTANCE.md), [current world scope](../../../WORLD_READINESS.md) and [the continuation backlog](<../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Owned Home Market Stall state — 24 October 2026

The ordinary bushel harvest restoration grants the original first Market Stall
gift. The client contains a conditional automatic configuration path which can
send `CraftingService.onReconfigureStall(-1, bushelCode)` after placement. The
shipped bytecode has no assignment to its private `m_lastBushelFound` field,
however: its only method reference is the getter. In the actual first-stall
browser check the free gift placed successfully, remained unconfigured, and
sent no configuration RPC. The server does not force a crop configuration.
`bushels.py` persists explicit owned configuration/close requests and supports
the conditional initial-ID wire contract when a valid request is received.
Neighbour offerings, reward URLs, sharing, Market Stall expansion and timed
bushel gain/use effects remain outside this implementation.

## Original contract

All bytecode evidence came from the copied original FarmGame.swf, SHA-256
`1edea7cbecefcb1e1233da207164942f0088a83b87afc9254850f5fcde5034ae`.
The compressed original catalogs and game client were read unchanged during
recovery. Disassemblies are in `MarketStallEvidence20261024/`.

- FirstMarketStallWindow.startGameMode23042 constructs
  GMBuild('marketstall', true, 0, false) and sets reconfigureOnPlace only when a
  lastBushelFound exists. The observed served first-stall path does not meet
  that condition.
- MarketStallBuilding.onBuilt22874 calls reconfigureMarketStallInitial5831.
  It sets the crop bushel code, isConfigured=true and estimated expiry, then
  sends TReconfigureMarketStall(-1, code). Ordinary manual configuration5830
  sends the owned stall ID and the same code.
- TReconfigureMarketStall.perform22689 calls
  CraftingService.onReconfigureStall(id, code). onComplete22690 only invokes
  its optional callback when data is non-null. The server returns {}.
- The original configuration functions spend no coins, cash or bushel quantity.
  The local handler requires an actually owned positive ordinary crop-bushel
  stack and a matching original seed/bushel relationship before configuration.
- getEstimatedStallClosureTime5832 and CraftingConstants23074 give
  floor(serverTimeMs / 1000) + 86400 + floor(masteryStars * 0.333). For the
  recovered zero-to-three-star crop ladder the last term is zero. dateClosed
  is in seconds; this is a map offering's display expiry, not a gain buff.
- MarketStallBuilding.loadObject22846 reads currentBushelItemCode, dateClosed,
  isConfigured. Its getSaveObject22875 delegates StorageBuilding11985 and
  does not serialize those fields, so trusting ordinary snapshots would lose
  server configuration on the next move or reload.
- closeStall22855 resets code to null, dateClosed to zero and isConfigured to
  false. TCloseMarketStall23055 sends CraftingService.onCloseStall(id); its
  optional success field is returned as {success:true}.
- onBuilt increments the client placedMarketStallCount. onSell22876 and
  onDelete22879 decrement it. CraftingState.initCraftingStateFromInitUser15798
  reads the durable value from craftingState.currentMarketStallCount.

The original first gift is ordinary ms:[1,[],[]]. Player.addGift4035 has defaults
sender='0', quantity=1; it constructs StorageItem('ms') with empty sender and
extra-data arrays, then adjusts quantity. It does not supply tier metadata.

## Bounded persistence and integration

New placement clears forged configuration fields, starts closed/unconfigured,
and uses the catalog's original zero capacity/storage size. Existing imported
configuration, progress and clock fields are protected from ordinary snapshots.
Unsupported Plot/growth actions on stalls are rejected before mutation.

After a genuinely new insertion, finish_stall_placement records its owned ID and
increments the saved count. Transport retries return through the existing
placement retry gate before that hook. Initial ID -1 resolves only when exactly
one trusted newly placed unconfigured owned stall exists. Imported stalls are
not guessed as the target; multiple eligible new stalls are visibly refused.
An explicit owned ID remains available for ordinary configuration.

finish_stall_removal runs only after actual sell/clear/store removal and prunes
that pending binding. Imported count baselines are retained and advanced rather
than reconstructed from a possibly partial world. A legacy zero count stays at
zero on removal instead of becoming negative; that floor is a bounded local
validation policy, not a claim about the original client's arithmetic.

The two service methods validate a detached save, preserve balances/inventory,
and retain the last256 sequence receipts plus a monotonic stale-sequence floor.
A transport retry cannot extend the expiry or reopen a later-closed stall.
Receipts and pending placement bindings survive a server restart. Fresh init
clears them because Flash sequence numbers restart; configuration and counts
remain durable. Initial bindings are therefore session-scoped.

commands.py owns snapshot/placement/removal hooks; server.py dispatches these
methods before its broader unsupported-crafting branch. No social reward or
income is generated by these operations.

## Allocation diagnosis and separate client fix

First-stall placement exposed a separate Ruffle allocation failure. Each of the
3,383 image rows caused createImageObject6230 to call getArray('image') again;
OptItemDataSource.convertToDataSourceArray13723 allocated fresh wrappers for the
entire array each time. Including the outer conversion, this is 11,448,072
wrappers/array pushes in one script event. The pinned Ruffle collects GC debt
after its update/action closure, consistent with the observed ArrayStorage::push
OOM. The selected empty image is only125x150 and its alpha plane is valid.
MapResourceDL handles only requested images; the catalog size does not imply
that every bitmap was decoded.

The client owner is validating a separate one-method fast path which selects
and wraps the individual raw Opt image row while retaining the original
non-Opt/singleton fallback. Browser acceptance and final client hashes belong
to the main continuation verification record, not to these server tests.

## Verification

`test_market_stalls_wire.py` uses the actual Flask AMF gateway, original catalog,
JSON persistence and temporary test_persistence fixture. It covers free gift
placement and the conditional -1 configuration packet, explicit IDs, no inventory/cash debit,
exact expiry, close/replay, placement retries, ambiguity/import refusal, forged
snapshots, positive owned bushel validation, mixed-command rollback, reload/init,
sell/clear/store count changes and stale receipt eviction. The generated first
attempt differed from disk only by the intentionally ephemeral tempId; final
comparisons use player._save_contents, the actual persistence projection.
These AMF handler tests do not claim that the browser sends the conditional
configuration packet during normal first-stall placement.
