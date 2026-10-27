# Live companion integration contracts

These are maintenance contracts distilled from the included `integration.py`, `engine.py`, the game transaction layer and their tests. They are not a new gameplay or platform acceptance result. Current release scope and unrun checks are in [ACCEPTANCE.md](../../ACCEPTANCE.md).

## Ownership and page lifecycle

The live adapter operates on the game server's selected farm. Opening the Barn parks that farm for the current browser session. Another session cannot claim it, edit it or release it through the ordinary resume route. The native wrapper dismantles the playing view while the Barn is shown, and returning creates a fresh game document.

Each farm has a page epoch. A Barn change rotates the epoch so commands from a game page created before that change are rejected. Releasing a park also rotates the epoch. A plain reload of an unparked farm must not continually rotate it and invalidate its own requests.

A fresh trusted game document is the deliberate recovery exception: a GET of the normal game document can release the farm selected by that page even if another session parked it. The old editor then needs to claim again and pass a new save revision check. Do not expand this exception to arbitrary requests or mutation routes.

## Preview and apply

Previews run transformations on detached farm data. They bind the chosen operation and resulting change to the selected farm, session, complete save revision and an expiring preview token. The current preview lifetime is fifteen minutes.

Apply must recheck the live revision under the game save lock, claim the farm for the correct session and reject stale tokens. The submitted request must not be able to replace the reviewed preview with new client-controlled amounts or targets. Save identity and unknown fields remain intact unless an explicitly supported operation changes a known field.

The detached engine and live adapter intentionally differ for live-only operations. Bulk animal/tree harvest and supported Stable/Orchard actions need the game's authoritative rules. Standalone copied-save mode must not emulate those calls by guessing missing game behavior.

## Transaction and durability boundaries

Live writes go through the existing `SAVE_LOCK`, `village_transaction` and `save_session` APIs. A before-change snapshot is created before applying a supported change. Snapshot restore verifies farm identity and snapshots the current state before replacing it through the same transaction boundary.

An ordinary transaction failure rolls back the prior in-memory state. A committed durability error is different: data may already be committed. Undoing only memory after that point would create disagreement between disk and the process. Preserve the existing committed-state handling and test it separately from pre-commit failures.

Snapshot files live under the selected external profile's `god-barn/snapshots/`, not inside source or a disposable app build. The clean-start release ships none; snapshots created during later use are new player state. Snapshot restore during synthetic QA tests the current mechanism and is not a legacy-save migration requirement.

## HTTP and isolation

Standalone `server.py` binds loopback, validates Host/Origin and uses a session mutation token. It rejects the game's default port and workspace locations inside a FarmVillage checkout. Its HTTP API accepts data, not arbitrary filesystem source/destination paths.

The Ubuntu host adds its own configured private-network authentication, origin/CSRF checks and single-owner process lock. Preserve that host boundary when changing Barn routes. Setting the native-mode environment flag alone does not establish authenticated remote hosting.

## Checks that carry meaning

Focused synthetic cases should exercise wrong farm/session, expired token, changed save, repeated apply, parked farm ownership, stale game epoch, transaction failure and restart persistence. The companion tests cover these at different layers; read the specific fixture before interpreting a passing result.

Then exercise the supported operation in the real client: preview leaves state unchanged, explicit apply changes the expected fields once, Return loads a fresh document, and reload/restart retain the same new farm state. Record browser graphics and native-window results separately. Test on actual Ubuntu before recording Ubuntu execution.

The root [TAKEOVER.md](../../TAKEOVER.md) and [WORLD_READINESS.md](../../WORLD_READINESS.md) define current direction. Older technical notes do not authorize iPad work, retired-world offers, invented reward probabilities or remote deployment.
