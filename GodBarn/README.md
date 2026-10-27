# God Barn

God Barn is the FarmVillage companion for inspecting recovered items and previewing deliberate changes to a farm. The continuing products are the native macOS app and the browser game on Ubuntu/private LAN. The iPad/iOS product is abandoned. The active release has sixteen worlds; Enchanted Glen and Holiday Lights are excluded.

Start at the repository [README](../README.md) for the contributor environment and [development guide](../docs/DEVELOPMENT.md) for resource-dependent builds. Keep `GodBarn/` and `FarmVillage/` as siblings. This source folder contains the implementation, tests and recovery tools. Original artwork and generated metadata are separate resources. Old practice farms, player saves and build products are absent.

| Mode | State it can change | Entry point |
| --- | --- | --- |
| Integrated | The selected farm owned by the game server | The game's God Barn view; `integration.py` |
| Standalone | Copies explicitly imported into its own workspace | `launcher.py` and `server.py` |

The integrated view parks the selected farm, previews against its complete revision, snapshots before applying, and commits through the game's save transaction. Return to Farm opens a fresh game document. The standalone server does not attach to a running game or install an edited copy into the game.

## Run the supported integration

With compatible resources already prepared, follow the [macOS build and browser staging instructions](../docs/DEVELOPMENT.md). New farms and history belong in the selected external data profile. This clean-start release carries no previous farms, snapshots, authentication or practice-save copy. Prepared-release installation is covered separately in the [development guide](../docs/DEVELOPMENT.md).

The old separate integration build and double-click launcher shortcuts are historical development arrangements. The native app build described in the development guide is the current entry point. Building an app does not start or stop a game server.

After resource preparation, standalone mode can be opened from this directory with the same prepared Python interpreter:

```sh
"$FV_CHECK_ENV/bin/python" -B launcher.py --no-browser
```

`FV_CHECK_ENV` is the external environment created by the root README. The launcher selects a free loopback port and prints its URL. Use a newly created synthetic farm export when testing standalone import. A new standalone workspace has no bundled practice farm; its optional legacy demo action needs a separately supplied bootstrap and is outside this clean-start handoff.

## Maintainer map

| File | Responsibility |
| --- | --- |
| `engine.py` | Detached farm transformations, bounds and supported operations |
| `integration.py` | Live game adapter, session ownership, revision/epoch checks, transactions and snapshots |
| `server.py` | Standalone HTTP API and isolated workspace persistence |
| `catalog_tools.py`, `static/app.js` | Item classification, facets and Not in Market membership |
| `helper_tools.py`, `progression_tools.py` | Collections/quest helpers and advancement controls |
| `encyclopedia.py`, `seasonal.py` | Historical metadata and recurring discovery calendar |
| `static/` | Authored companion interface source |
| `scripts/` | Local archive recovery, preparation and bundling tools |
| `tests/` | Synthetic engine/HTTP contracts and resource-dependent regressions |

Read the [handoff](HANDOFF.md), [integration contracts](Documentation/INTEGRATION_CONTRACTS.md) and [catalogue pipeline](Documentation/CATALOG_PIPELINE.md) before changing the adapter or generators. [Resource setup](../docs/RESOURCE_SETUP.md) explains exactly what a source clone lacks.

## Feature boundaries

The existing engine includes balance/XP/level controls, crop ripen/revive/advance/fertilize, supported inventory grants, selected progression/collection/quest helpers and catalogue-defined expansion. Some actions, including ordinary-reward bulk harvest and supported Stable/Orchard tools, require the live adapter. A catalogue entry, successful grant or synthetic test does not establish that every associated game mechanic works.

All changes use a visible preview and explicit apply. Unknown/malformed state remains read-only where the engine cannot interpret it. A chosen offspring result is an explicit God Barn cheat, not an inferred historical probability. Original timers, prices and authentic gameplay rewards stay under the game's rules.

The recurring calendar repeats recovered month/day availability windows for discovery. It does not activate Market offers or change planting prerequisites. Not in Market means no recovered tab membership under the documented client fallback; it is not a complete audit of live availability.

## Checks and contribution

The root source-only command runs selected tests without the original resources. For the complete companion suite, first restore matching private inputs and install the root requirements, then run from this directory:

```sh
"$FV_CHECK_ENV/bin/python" -B -m unittest discover -s tests -v
```

Some tests start temporary loopback servers. Use fresh synthetic profiles and unused ports. Record source revision, resource identities, command, result and unrun UI/platform checks. Current acceptance lives in [ACCEPTANCE.md](../ACCEPTANCE.md); the remaining restoration backlog is [Wave 3.md](<../Wave 3.md>).

Preserve [CREDITS.md](CREDITS.md) and the root [source/resource notice](../SOURCE_NOTICE.md). The owner selected GPL-3.0 for the original companion code. This source licence does not grant rights to the original game resources.

## Source licence

The original God Barn companion code is licensed under [GPL-3.0](LICENSE), as selected by its owner on 25 October 2026. Preserve [credits and provenance](CREDITS.md); the code licence does not grant rights to original game resources.
