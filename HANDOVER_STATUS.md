# Development status and maintainer priorities

**Updated 26 October 2026.** The public resource installer is implemented for native Mac and Ubuntu/Linux server paths. It downloads verified originals, generates God Barn, builds pinned Ruffle, and connects generated resources to installation. No large downloads or real builds were run on the owner’s Mac for this update. Full clean-clone/native/Ubuntu gameplay qualification remains open.

The continuing targets are the native macOS desktop app and browser hosting on Ubuntu/Linux. The active alpha has sixteen worlds with different feature limits. iPad/iOS development is discontinued; Enchanted Glen and Holiday Lights are excluded. See [world readiness](WORLD_READINESS.md).

## Available now

- The Python game server, native macOS app source, browser hosting tools and God Barn companion.
- Source integrity, syntax and documentation checks, plus selected tests using synthetic data.
- Resource identity manifests, extraction tools, Ruffle build provenance and catalogue recovery utilities.
- [Architecture notes](TAKEOVER.md), [engineering contracts](FarmVillage/macOS/Documentation/ENGINEERING_INDEX.md) and a [restoration backlog](<Wave 3.md>).

The application source baseline is FarmVillage `62809de497404588f133e38740242864717af0c0` and God Barn `31245bb8bc2848908667ae0cf95af8244531bff5`. `SOURCE_MANIFEST.json` identifies the exact files in this source release. The public Git history is inherited from AcidCaos/FarmVillage through commit `2dc25ca24032041a8b68d299b861eb2d4d449653`; the current tree uses the reviewed source layout.

## Two player paths

- [Mac players](docs/PLAY_ON_MAC.md): `START_MAC.command` opens the plan and guided resource preparation, builds the native app externally, and launches it with dedicated player data. Extracted artwork is shared without a second archive download.
- [Server owners](docs/PLAY_ON_SERVER.md): `bash START_HERE.sh` prepares public resources, then opens the guarded clean Ubuntu installer. Browser players use the resulting server URL.

Both require an explicit target and download/build confirmation. No owner’s Mac files, account, token, historical farm or private server is an input. See [all sources, storage and retry behavior](docs/RESOURCE_SETUP.md).

## First priority: qualify real installations

1. Run the public source flow on a clean Mac and an actual Ubuntu host separately, with adequate user-approved disk/network budgets.
2. Record exact source revision, generated pack seals, runtime build receipt and native/compiler identities. Cross-host Ruffle output differences use explicit source-verified local manifests rather than the old Mac output pin.
3. Create fresh synthetic profiles; test a real farming cycle, save/reload and process restart. Confirm prices/timers/rewards remain original.
4. Record native UI acceptance, browser gameplay and Ubuntu service/network results separately. A mocked compiler or Mac adapter test does not establish Ubuntu execution.
5. Measure peak download/build/final-install storage and verify interruption/retry with actual sources.

## Briefs ready to pick up

Each brief is one bounded assignment written to be started cold. They follow the rules in [Wave 3](<Wave 3.md>) and [AGENTS.md](AGENTS.md).

- [M02 / F03: wiring the prerequisite evaluator](docs/briefs/M02_PREREQUISITE_WIRING_SCOPE.md): phased plan that changes no behavior until the owner settles the unknown and `end_time` policies. Starts with confirming one guessed attribute name.
- [Shelf first batch (proposal)](docs/briefs/SHELF_FIRST_BATCH.md): eight plain decorations proposed for Mistletoe Lane, what to hold back and why, and the questions only an integrator can answer. Nothing is admitted.
- [Asset review without a Mac](docs/briefs/ASSET_REVIEW_NO_MAC.md): one command fetches the 44 pinned public originals, verifies them, and writes the retired-world decor candidates and the Mistletoe recipe table. No Mac, no private inputs, no 19 GB download.
- [W15: Mistletoe Lane for the holiday season](docs/briefs/W15_MISTLETOE_HOLIDAY_SEASON.md): finish the active Christmas world honestly. Accept the other 16 Patisserie recipes one at a time, classify the open catalogue records, run the native loop.
- [World roster and repurposing](docs/briefs/WORLD_ROSTER_AND_REPURPOSING.md): which worlds are playing, which could return, which stay closed, and careful ideas for the closed ones. Reactivates nothing.

The recovery patch remains a historical record. Relevant generator/native/player work was selectively integrated and missing orchestration implemented. Do not apply [the old patch](RESOURCE_SETUP_RECOVERY.patch) wholesale to this active tree.

## Installer checks recorded for this update

The final targeted run includes 142 installer/handoff fixture tests, 66 God Barn reconstruction/bundling/parser tests, and 22 existing runtime compatibility/upgrade tests: **230 tests, 229 passed and one skipped because loopback binding is restricted**. Source integrity, Python/shell syntax and 308 repository-local documentation links also passed. The two player entry plans and resource-only dry run created no installation folder.

The orchestration tests use tiny synthetic originals/WARCs and mocked package/compiler/native-tool commands. They exercise Mac and server resource seals, resume/failure behavior, runtime-pin propagation, native staging, the generated Mac launch shortcut, browser staging and server-wizard handoff. They download no originals or toolchains and start no real game/service.

A broader existing native runtime suite was also attempted; it hit 17 environment errors from denied localhost binding and unavailable `requests` in the system interpreter. This update does not claim that broader suite or a full game regression passed. No dependencies or permissions were added to bypass those limits.

## Other open work

- Repeat the remaining native gameplay checks and qualify installation, service operation and gameplay on an actual Ubuntu host.
- Restore regional production, progression, treasures and expansion systems in bounded, source-supported steps.
- Keep unsupported features unavailable until their real rules and outcomes are known.
- Preserve original prices and timers, and test with fresh synthetic profiles. The current release policy uses new farms rather than migrating old saves.

[ACCEPTANCE.md](ACCEPTANCE.md) records historical testing with prepared resources. It is separate from clean-clone resource qualification, signing/notarization and long-session stability. Source-only tests, native builds, browser graphics and actual Ubuntu execution are distinct checks.
