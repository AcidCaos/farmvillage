> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../../ACCEPTANCE.md), [current world scope](../../../../WORLD_READINESS.md) and [the continuation backlog](<../../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Reviewed client compatibility patches

The archived client remains at `embeds/Flash/v855097-855094/FarmGame.swf`.
`macOS/Scripts/patch-game-client.py` prepares a separate copy using Python's
standard library. It verifies the complete input and output body hashes and
rejects an unknown client. Java and FFDec are review tools, not build or runtime
dependencies.

The original compressed artifact SHA-256 is
`1edea7cbecefcb1e1233da207164942f0088a83b87afc9254850f5fcde5034ae`.
Its decompressed body is
`a9b719e6be4ceb40b9136880bfecf08399975f6babf7199db9af2d19a985794d`.
The existing XML style-dictionary fix first produces body
`29130263405a7bb27be44bb8abf5c09e0a5fa4e31563ad0abe3ba4823f61cee2`.
The four Market changes below then produce the reviewed 21,520,934-byte body
`edae6c3be651b9d9e4082d68267dd829cc8a8e620213824faee4d7caa4630b1c`.
Different valid zlib compression produces different compressed-file hashes;
the complete decompressed body is the identity used for verification.

That A4 body and its original `provenance.json` remain the historical Market
review. The separate 22 October Deco tab preparation starts from that exact
body and produces
`9cb08381610e988c4d944b7ee06d0b7d0bbae2264bc5a988ee94597255afa5d4`.
`deco-client-byte-review.json` records its independent byte and method review;
earlier native measurements do not validate this current client or payload.
The tab callback identifies its listener with `MouseEvent.currentTarget` so a
clicked label changing its pressed/selected display object cannot lose the
tab's ancestry. All 68,492 method bodies were compared with A4: only
`FarmTabMenu.onItemClick` changed, and its length, branch operands and exception
table stay intact. Two NOPs replace one debug line to accommodate the longer
property operand. The archived client remains unchanged, and preparation
accepts known original, style-only and A4 inputs before verifying the complete
current output.

The Scratch-Off icon repair then produces the same-size body
`43d624db101b0f343761eca4087819d0fd7c203dcc1d5727a0f90347af299045`.
`scratch-coin-byte-review.json` records the exact 99-byte replacement within
`ScratchCardWindow.loadItemIconWithScratchData` (method 24645). The archived
coin pictures contain “1 MILLION” and “2 MILLION” in their artwork. Those exact
amounts retain their original pictures; other coin prizes use the existing
amount-free `assets/hud/FV_coins_100x100.png` and return their actual quantity
to the original tile and win/lose labels. Payouts, reward matching identities,
other reward branches, method length and exception tables stay unchanged.
No asset is replaced. The preparation pipeline accepts the prior tab-prepared
body and upgrades it, while verifying the complete final body hash. Bytecode
execution tests cover 500, 2,000, 1,000,000 and 2,000,000; visible browser
acceptance is a separate check.

The empty-world initial-load repair produces the same-size body
`68152f8c2f5cc22913ff6d3a80d5a4a0c2e054c3d1f80cd3457fbd056eb525de`.
`empty-world-byte-review.json` pins the single changed byte in
`WorldManager.onUserInit` (method 2720). The original login path requires
`world.objectsArray.length > 0` before calling the ordinary world loader.
The disclosed empty local England and Meadows starts therefore load through
live travel but skip terrain initialization on a fresh login. This leaves
`world.terrainMap` null, causing the flat green floor and exceptions when a
plow or gift placement queries terrain. The comparison now accepts zero
objects while retaining the world and array presence checks, then runs the
existing loader, terrain, collision and plot-limit setup. No starter objects,
story flags, unlocks or farming rules are added. Method length, pool references,
branches and exception tables are unchanged. The pipeline accepts the prior
Scratch-Off body and upgrades it. Tests execute the emitted gate for empty and
populated arrays, absent data and disabled loading; visible browser acceptance
remains a separate check.

The cottage first-placement graphics repair then produces body
`5b9b7811210904d86ccd672469b4608e55f271c91e0f20102cee39a5ac8a0acf`.
`cottage-graphics-byte-review.json` records the rendering-only change to
`CraftingCottageBuilding.getCurrentSuffix` (method 22586). `Building.build`
loads its sprite before `onBuilt` creates the local craft skill state; the
original owner getter returns 0 during that interval, selecting absent
`built_-1` artwork. The image suffix now uses `max(0, int(craftLevel-1))`,
so initial placement uses the original `built_0` bitmap. Positive craft levels
and visitor stages retain the original progression. Ownership, recipes,
queues, inventories and saved skill levels are unchanged. The 32-byte method
keeps its original header, maxstack 2, pools and exception table. An independent inventory compared all 68,492 method bodies: only this selector
changed. Every byte outside its 32-byte span, including frame/asset tags, is
identical to the prior prepared client. Unknown clients
fail closed, and original/source and previous prepared builds upgrade through
the same verified pipeline. Tests execute the emitted selector at levels 0–5;
visible first-placement acceptance is recorded separately.

The cottage upgrade invitation gate then produces body
`cbbc8d5fac34542697c722d37f7912f7f4a9155162bb09f5b7cd988eb8063f62`.
`cottage-upgrade-visibility-byte-review.json` pins five changed bytes in
`CraftingMainWindow.updateUpgradeFrame` (method 34693). The cash and coin
upgrade buttons previously invited a service that has not passed acceptance.
Their two `visible=true` opcodes now write false; the four other visibility
branches already hide both controls. A three-byte debug line becomes an
empty-string assignment, clearing upgrade-only instructions and the shared
frame tooltip. The method length, header, branches, prices and all other code
remain unchanged. Cottage levels, recipe XP, stars, the meter and production
slots retain their existing state and behavior. Original source assets remain
unchanged, and known prior clients upgrade through the pinned pipeline.
Tests execute the actual cash, coin and maximum-level UI branches, including
unmet prerequisites; browser acceptance is required separately.


The Turbo purchase refusal then produces intermediate body
`3a957c0ae98e9f86af41af0f87b925e93aebc49a722feeaa31d252b576569862`.
`turbo-purchase-refusal-byte-review.json` records the one-method change to
`TurboItem.onBuy` (14159). The original callback constructs `TBuyTurboChargers`,
whose constructor adds client turbo and subtracts currency before its server
reply. The 23 October browser run proved that this call's error 29 was silent,
leaving a false seven Farm Cash deduction until reload. The callback now uses
the existing OK popup to say "Turbo charger purchases are not restored on this
server." and returns false before constructing that transaction. The server
retains its no-charge refusal as a backstop. Turbo gift use remains unchanged
and is not claimed accepted.

One 57-byte string-pool entry is appended without changing any existing index;
the pool count and enclosing DoABC length are adjusted. The method length,
header, maxstack and exception table remain unchanged. An independent reader
compared all 68,492 method bodies: only this callback differs from the prior
prepared client. The emitted-code test reaches exactly one popup and returns
false with no player/transaction globals available. Source assets remain
unchanged, previous builds upgrade through the composed recipe, and unknown
inputs fail closed. Scripted verification passed 24 tests. Independent browser
acceptance on the disposable 45481 fixture showed the visible refusal, unchanged
HUD and saved cash, no purchase gateway request and usable Market afterward.
Native acceptance was not performed.

The 24 October Inventory storage-upgrade refusal produces current body
`4437fffbebb1737cfa3e68b5c2e9fc77e0d67056873378452834591d1fed0eb8`.
`storage-upgrade-refusal-byte-review.json` records the two entry-point changes
to `InventoryWithdrawal.onUpgrade` (12421) and `onPurchaseUpgrade` (12423).
Both now use the existing OK popup to say "Storage upgrades are not restored
on this server." and return before disabling buttons, opening a confirmation,
constructing `TUpgradeStorage`, or changing the local building. The original
paid confirmation callback called `building.upgrade()` before the refused
reply, replacing its item, capacity and level until reload.

One 50-byte string-pool entry is appended without renumbering existing entries.
Method lengths, headers, maxstack, exception tables and all other 68,490 methods
remain unchanged from the Turbo stage. The original storage read/withdrawal and
material-construction routes remain intact. Separate barnraising reprompts,
Orchard-specific upgrade paths and MOTD offers are outside these two Inventory
gates and retain their server backstops. Emitted-code tests execute both actual
callbacks with only popup globals available; bytecode inspection and scripted
execution do not establish browser or native acceptance.

| Method | Method/body index | Result |
| --- | --- | --- |
| `FarmGameSettingsManager.parseItemsBatch` | 3193 / 3133 | With buildtime configuration and optimized item AMF, leave conclusively dormant raw offers unconstructed during both background and immediate parsing. |
| `FarmGameSettingsManager.getFarmItemsArrayByType` | 3216 / 3156 | For Market queries using a buildtime name index, resolve a temporary filtered name array instead of constructing every archived definition. |
| `FarmGameUtil.synchronizedDateToNumber` | 1364 / 1338 | Cache the unadjusted date conversion, then apply the current server UTC offset on every call. |
| `FarmGameUtil.synchronizedDateTimeToNumber` | 1365 / 1339 | Cache the original UTC date/time parse result, then apply the current server UTC offset on every call. |

The loading gates omit only an explicit raw `buyable="false"` offer without a
license, seed/seed-package role, deal marker or giftable flag. Market name
filtering also retains a base with either cash or sale companion. Missing or
already resolved raw entries remain eligible. The complete definition lookup
maps and buildtime indexes remain available for placed items, gifts, class/AOE
queries and mastery signs. The Market filter does not replace its complete name
index with a permanently filtered cache. Other query modes retain the original
path. The date caches live only in the running client's `Global.flashHotParams`;
they do not change the catalog or saved farm.

The server also serves the complete derived catalog from `client_catalog.py`.
It retains every definition and disables only conclusively expired buyable
offers using the reviewed date margin. The source catalog is preserved. The
initial native run used this full derived catalog together with these four
methods. A later run using genuine Ruffle background worker ticks still reached
the 4 GiB WebAssembly limit. These assembly inputs and hashes remain verified,
but these four methods alone do not complete performance acceptance; see
validation (`../VALIDATION.md`; external/private historical reference, not included in this source export) for the exercised interactions and current status.

The four `.pcode` files are the exact FFDec 26.4.0 assembly inputs.
`market-performance-byte-recipe.json` records all twelve edits applied to the
style-prepared body, complete hashes and the independent method inventory.
Its temporary assembler paths record provenance only. `provenance.json` pins
the review files and standard-library output. All 68,492 method bodies were
compared: these four Market bodies changed, their exception tables did not,
and every decoded branch target is a valid instruction boundary.

Backward branches to a not-yet-seen target have an additional verifier
requirement: their destination must include AVM2 opcode `label` (`0x09`). The new Market loop contains that
instruction. A boundary-only check missed this requirement during development;
the accepted review checks both boundaries and backward labels. The failed
chunking, Pigo preselection, missing-buyable and standalone cache experiments
are excluded from this patch set. Their diagnostic history remains in the
validation record rather than in the build recipe.

The packed-catalog candidate is retained for review only. Its five-method
version completed broad Market interaction, then reached the 4 GiB limit after
idle; it has not passed native performance acceptance. Its `FarmGameSettingsManager.parseItem.pcode` adds a 52-byte prefix
that recognizes `fvPackedItem` as an AMF3 `ByteArray`, selects object encoding 3,
resets its position and reads the complete original definition before the
unchanged method continues. The corresponding five-method, thirteen-edit recipe
is `market-packed-candidate-byte-recipe.json`; it produces body
`90a1ac894dcdfe9c947d7d7760778a0f936e038ffe948599ee56813d24cd310f`.
`market-packed-candidate-review.json` records raw-property access and lifetime
audits. `market-packed-catalog-parity.json` records all 111,206 source definitions
roundtripping through a copied outer catalog, with 81,546 dormant definitions
packed losslessly and every expanded field equal. This is a paired client and
catalog experiment. A combination with the separately reviewed Pigo
preselection method remains under test; none of these candidate files establish
completed performance acceptance.

The 24 October continuation adds separately pinned stages for the
[cottage/invitation controls](../COTTAGE_INVITATIONS_CLIENT_2026-10-24.md),
[local quest reward close acknowledgment](QUEST_REWARD_CLOSE_2026-10-24.md),
[linear image metadata selection](IMAGE_ROW_LINEAR_2026-10-24.md),
[Inventory tab artwork](INVENTORY_TAB_ART_2026-10-24.md), and the
[MarketStall expansion fence](MARKETSTALL_EXPANSION_2026-10-24.md).
Each linked review identifies its historical input/output SHA; recognized earlier
stages advance through the complete current chain. The current output identity is
`client_compatibility.PATCHED_BODY_SHA256` and the packager's matching client pin.
Browser acceptance remains recorded separately from bytecode tests.

Fresh browser evidence subsequently identified the ordinary Inventory route's
separate widget renderer. Its [two visibility arguments](WIDGET_STORAGE_VISIBILITY_2026-10-24.md)
are pinned in a later stage; the legacy artwork stage remains an intermediate.
