> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../ACCEPTANCE.md), [current world scope](../../../WORLD_READINESS.md) and [the continuation backlog](<../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Owned-world travel — 22 October 2026

This source supports Home and England with distinct durable world snapshots.
It does not certify browser acceptance or a deployment.

The recovered `TWorldLoad.perform` sends the world name, create flag, freeze
flag and next-season flag to `WorldService.loadOwnWorld`. `TBaseWorldLoad`
reads `user.currentWorldType` and the returned world; `TWorldLoad` also reloads
`user.worldSummaryData`. These contracts were inspected in the bundled
`embeds/Flash/v855097-855094/FarmGame.swf`.

England's `gameSettings.xml.gz` all-access reward is `world_unlock=england`.
Its referenced `gameSettingsCMS.xml.gz` prerequisite requires player level 15,
`fv_england_for_all=1`, and England not already unlocked. The local play page
already enables that experiment. Creation checks the recovered level gate and
accepts the original `EnglandService.unlockEnglandWorld ["allAccess"]`
transaction or the travel call's explicit create flag. The unlock transaction
creates an inactive snapshot and leaves Home active. Its empty AMF Array is
truthy in ActionScript, allowing `TExpansionWorldAccess.onComplete` to apply
the catalog unlock and install `TravelNameDisplay`. There is no unlock charge
or extra reward in that recovered all-access contract. Existing worlds can be
revisited without resetting their contents, grants or creation time.

The original England starter layout was not recovered. A new England farm is
an **empty local substitute**, sized from the catalog's `farmSize` (50×50),
marked `localStarter=empty-england-v1`. It grants no buildings or items. It
does not clone the player's home farm. The inventory IDs are the recovered
Home `-2` and England `-8` values.

The active world remains the existing top-level `world`; only inactive
snapshots live under the versioned `_ownedWorldTravel.inactive` map. This
server-only map is omitted from init responses. The save transaction commits
the destination, source snapshot and current-world flag together, and rolls
back all three if a later command, response encoding or save fails. Unknown
imported fields are preserved. An existing summary or unlock without a
recoverable world snapshot is rejected instead of replaced by an empty farm.

Object allocation considers every owned world and positive storage ledger,
skips the client's temporary-ID interval, and keeps a durable counter after
travel begins. New place/plow requests must supply temporary client IDs;
existing permanent IDs can identify current-world actions and retries.
Inactive objects cannot be mutated through active-world actions. Generic
storage access allows active-world buildings/inventory and shared gifts or
consumables; inactive/unknown inventories are retained but rejected for
transfer. Sheep inventory fallback resolves the current world. Ownership
counts include both worlds, and neighbor visits/help continue to use the
neighbor's home while that neighbor is in England. Temporary placement IDs
are removed from all snapshots when saving or starting a new client session.

Unsupported scope: destinations other than Home/England, original England
starter/onboarding quests, shipping licenses, freeze/pause semantics, seasons,
world-specific currencies/scores, and themed progression. Crafting cottages
cannot be placed in England because the current crafting queue is account-wide
by cottage type. Home production remains stored across trips. This is a
bounded travel implementation, not all-farms feature coverage.

Offline regressions in `macOS/Tests/test_world_travel.py` cover real AMF travel,
reload/return, unlock gating, retries, isolation, IDs, storage, sheep DNA,
neighbor visits/help, ownership counts, init serialization and rollback. The
independent `test_world_travel_review.py` suite exercises imported foreign
inventory and forged permanent-ID cases. All tests import `test_persistence`
before product modules and use disposable saves/caches.

The original generic inventory path is `MapResource.onAddToInventory` →
`TInventoryStore`: it keeps the placed resource's save snapshot, sends its
positive object ID in `resource`, and chooses `target` from the active
world's storage ID. `BaseStorageSlot.onUseClick` passes the displayed
inventory's exact storage ID when placing a stored item. The AMF regression
uses the recovered 100-coin Hay Bale (`haybale`, `HB`) to cover market
placement, storing into England `-8`, Home isolation, reload/return and
withdrawal without another payment. The recovered `storageConfig.amf.gz`
Inventory allows ordinary `Decoration` objects. Its specialized exclusions
remain outside this generic fixture.

An original Pink Tool Shed purchase exposed a separate reload contract:
`StorageBuilding.getSaveObject` can send empty `contents` as an AMF Object,
but `StorageBuilding.loadObject` coerces truthy contents to an Array. Ordinary
`StorageBuilding` snapshots now normalize only `{}` to `[]`, and new
placements default omitted contents to `[]`. Init and travel repair the same
empty case in both owned worlds. Nonempty imported maps, populated arrays,
their row metadata and storage ledgers are preserved. The original client's
empty move snapshot cannot overwrite populated saved contents. Regressions
cover both original purchase shapes, reload/return/init, legacy snapshots in
both worlds, preservation and rollback; visible reload acceptance still needs
the original browser after the corrected source is loaded.

For browser acceptance, use a disposable player at level 15 or above and allow
the original post-init all-access unlock. `TravelNameDisplay` installs click
handlers on its `nameBar_mc` and `travel_bt`. Both launch templates select
the original flyout (`fv_xas_traveldialog=0`), populated from available owned
destinations. The archived improved-dialog asset contains `slots4_mc` only;
its client asks for `slots1_mc` with one destination and otherwise shows an
empty shell. The flyout avoids that incompatible layout without advertising
unimplemented farms. Select England there, choose ordinary unfrozen travel,
plow a plot, travel Home, reload, return to England and confirm the plot and
both inventories. `WorldManager.doTransactionLoad` always sends the create
flag, including revisits. A successful AMF test is not a substitute for those
visible checks. No production save, Bifrost deployment, or native app rebuild
is part of this source work.

For the placement/storage portion, search the original market for Hay Bale,
place one, select the arrow/multi-tool, and use the object's `Store` context
menu. Open Inventory and inspect the current farm or the farm selector. Home
and England may both be inspected, but placing an item from the inactive
farm's inventory requires unsupported shipping licenses. Return to England
before selecting the stored Hay Bale's `Use` control, then place it and
reload to check its durable position and the emptied England inventory.
