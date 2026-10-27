# Maintainer guide

This guide introduces the architecture, restoration boundaries and validation practices for contributors continuing the project. Start with the [README](README.md) and [current priorities](HANDOVER_STATUS.md).

## Direction and first steps

macOS native desktop and browser/Ubuntu are the active targets. iPad/iOS is abandoned as of 25 October 2026. Only a new explicit human instruction can reverse that decision. The desktop app is SwiftUI/AppKit with WebKit/Ruffle and a supervised Python backend; it does not use the iOS Rust player.

Read README.md and ACCEPTANCE.md, record the current commit and inspect SOURCE_MANIFEST.json. Start with asset-free synthetic tests. Read [resource setup](docs/RESOURCE_SETUP.md) before attempting a complete app/game check; the public resource installer is implemented; real clean-clone installation qualification remains open. Use a newly created synthetic profile and an unused port. The clean-start installer may wipe only its identified managed installation, and must refuse unrelated/system/source paths.

## Architectural entry points

The [engineering index](FarmVillage/macOS/Documentation/ENGINEERING_INDEX.md) preserves the implementation findings behind these modules. The [resource guide](docs/RESOURCE_SETUP.md) distinguishes the checked matching-input route from the remaining reconstruction prerequisites.

- `FarmVillage/server.py` owns Flask routes and loads the game modules. `bundle.py` separates read-only payload paths from the writable profile selected by `FARMVILLAGE_DATA_DIR`.
- `persistence.py`, `player.py` and command transaction boundaries preserve atomic saves, multi-farm recovery, identity and unknown imported fields. Keep their rollback/durability distinctions intact.
- `commands.py` routes original AMF actions to authoritative rules. World feature admission remains intentionally exact; broad class bypasses are not a restoration.
- `client_compatibility.py`, `client_graphics.py`, `cove_client.py` and `meadows_client.py` prepare a version-pinned client. Unknown inputs must fail instead of being patched by guesswork.
- `FarmVillage/macOS/Sources/RuntimeController.swift` coordinates native setup/start/stop and logs; `GameWebView.swift` owns the game/companion documents. `macOS/Runtime/` supervises the server and runtime updates.
- `FarmVillage/portable/Linux/server_runner.py` adds private-address validation, browser authentication, origin/CSRF checks and one-owner data locks. It needs a prepared Runtime/BackendHost layout, not raw source.
- `GodBarn/integration.py` parks the selected farm, binds preview to its revision, applies through the game's transaction layer, snapshots before writes and reloads a fresh page after Return. `engine.py` provides copied-save transformations. These are different modes.

## Bounded scope and open work

Sixteen destinations are supported, including Home/October, England, Meadows, Cove, Rainforest and eleven other supported worlds. Existing engines include ordinary storage, selected regional production, finite construction/container ladders and original-client compatibility repairs. Each world/variant keeps its own tested scope.

The full Wave 2 restoration program is not complete. Mediterranean continuation has not been delivered by this handoff. Remaining work includes regional Cafe/Craftshop and production variants, authenticated authored score/Beat progression, treasures and expansion terrain, authentic populated starters and unrecovered repeat-loot/reward timing. Do not invent outcomes to fill those gaps.

Enchanted Glen and Holiday Lights have been dropped from the active release. They must have no supported-play, unlock or travel offers. Older eighteen-world/UI evidence remains historical. Reactivation requires a new explicit human instruction. See WORLD_READINESS.md for the sixteen supported worlds.

## Evidence discipline

A source-only green run proves syntax, selected synthetic contracts and source integrity. A complete app build proves compilation/packaging. An actual native window with rendered gameplay proves the observed native interactions. Browser graphics, protocol save/restart, actual Ubuntu execution, managed clean-install execution and long-session memory behavior are separate gates. Report PASS, FAIL and UNRUN per target; never sum overlapping historical test counts.

Use original prices and actual timers. A synthetic balance or ready-crop fixture is setup, not an earned reward. Verify newly created QA farms, crop clocks, world state, storage/crafting and newly created God Barn history across reload/restart. Ship none of that QA state or any previous player state. Record the source commit, served client/catalog hashes, player runtime pin and exact artifact inventory for each new acceptance.

## Safe continuation workflow

Choose one bounded bug or contract, reproduce it on a newly created synthetic profile, fix source, run affected tests and retest the client when appropriate. Preserve prices/timers and honest refusal behavior. The broader restoration backlog stays open.

This is a clean-start release, not migration: the owner authorized wiping all old saves for the next managed Ubuntu installation. Ship no old farms, snapshots, history, passwords or sessions. Do not spend this release on legacy-save recovery or backup promotion. Ordinary persistence/restart of new farms must work.

The guided wizard and the [prepared-release installer reference](BIFROST_SETUP.md) must follow exactly the same sequence. A destructive installer names its exact managed target and refuses unrelated/system/source/linked paths. Preparing a package does not authorize deploying it live.

The unfinished restoration plan and measured catalog/engine-sharing findings are in [Wave 3.md](<Wave 3.md>). It is a future-work backlog, not permission to reopen iPad, reactivate retired worlds, deploy, or claim complete restoration.
