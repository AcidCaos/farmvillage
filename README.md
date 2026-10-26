# FarmVillage — God Barn Edition

A community preservation fork of [AcidCaos/FarmVillage](https://github.com/AcidCaos/farmvillage), extending the original preservation work with a native macOS application, browser hosting tools and **God Barn**, a companion for inspecting items and editing farms.

The aim is to make the original farming experience playable locally while preserving its prices, timers and game rules. Restoration is incomplete, and contributions are welcome.

**Development status:** a sixteen-world alpha. The public installer now downloads original resources, generates God Barn and builds the reviewed local player. Full fresh-install/native/Ubuntu gameplay qualification remains open; this update was checked with small synthetic files and mocked build tools.

## Choose how you want to play

| Audience | Where the full game lives | Start here |
| --- | --- | --- |
| **Mac players willing to install 20+ GB locally** | On your Mac, using the native app; a separate server is not required | [Mac player guide](docs/PLAY_ON_MAC.md) · `START_MAC.command` |
| **People with an Ubuntu/Linux server** | On the host; players connect through their browsers without installing the full archives on each computer | [Server owner guide](docs/PLAY_ON_SERVER.md) · `bash START_HERE.sh` on the host |

The source launchers show the complete download plan, ask for a dedicated folder and require exact confirmation before downloads/builds. They fetch the original client and four artwork WARCs from public sources, generate metadata and build Ruffle. No owner’s Mac files, private server or GitHub account is required.

**Storage:** original compressed artwork is 19.13 GB. Source compilation and extracted artwork require more: the installer conservatively asks for 110 GiB free for Mac or 80 GiB for server resource preparation. The server’s final installation needs additional staging space. Exact fresh-install peak is not yet qualified. Read the appropriate player guide before starting.

## What’s included

- **Native macOS application:** a SwiftUI/AppKit desktop app using WebKit, Ruffle and a supervised local Python server.
- **Browser game server:** Python game logic, persistence and hosting tools for the Ubuntu/Linux browser target. Actual Ubuntu installation and gameplay qualification remain open.
- **God Barn:** an item browser and farm editor with previews, explicit apply actions and supported progression, inventory and crop tools.
- **Sixteen-world alpha:** farming, inventory, travel and selected regional systems, with different restoration limits in each world. See [world readiness](WORLD_READINESS.md).
- **Contributor tools:** synthetic tests, resource recovery utilities, client compatibility work and engineering documentation.

macOS desktop and browser/Ubuntu are the continuing targets. iPad/iOS development is discontinued. Enchanted Glen and Holiday Lights are excluded from the active world roster.

## Get started with the source

Use Python 3.10+ and Bash. Clone the repository and run the lightweight source check:

```sh
git clone https://github.com/jannsenburke/FarmVillage-GodBarn.git
cd FarmVillage-GodBarn
python3 -I -B tools/check-source.py --for-publication
```

This checks the source manifest, Python and shell syntax, merge markers and local documentation links. It does not install dependencies or download game files.

To run the selected synthetic tests, create a Python environment outside the checkout:

```sh
FV_CHECK_ENV="$HOME/.local/share/farmvillage-dev-venv"
python3 -m venv "$FV_CHECK_ENV"
"$FV_CHECK_ENV/bin/python" -m pip install -r FarmVillage/requirements.txt
"$FV_CHECK_ENV/bin/python" -B tools/check-source.py --for-publication --tests
```

The tests use synthetic data and do not require original game resources. Keep the environment outside the checkout because the publication check expects source files only. In a new terminal, set `FV_CHECK_ENV` to the same path again before using the examples in the developer guides.

## Game resources and playing

The current source tree excludes original game binaries, artwork, fonts, audio, generated catalogues and the compiled Ruffle player. Public upstream history is retained; it is not a complete playable resource pack.

The original preservation sources include:

- [AcidCaos/FarmVillage’s pinned upstream files](https://github.com/AcidCaos/farmvillage/tree/2dc25ca24032041a8b68d299b861eb2d4d449653).
- [Internet Archive’s original-farmville collection](https://archive.org/details/original-farmville).

The installer connects these originals to extraction, catalogue generation, player compilation and installation. It keeps generated resources outside the source checkout and records their identities.

Read [game resource setup](docs/RESOURCE_SETUP.md) for all download sources, storage, generated files and retry behavior. Contributors who already have compatible prepared resources can use the [development and build guide](docs/DEVELOPMENT.md). Historical gameplay results are recorded in [validation scope](ACCEPTANCE.md); they do not establish clean-clone playability.

## Find your way around

| Directory | Contents |
| --- | --- |
| `FarmVillage/` | Python game server, browser interface and game rules |
| `FarmVillage/macOS/` | Native desktop application and runtime supervision |
| `FarmVillage/portable/` | Browser hosting and installation tools |
| `GodBarn/` | Companion interface, farm editor and recovery utilities |
| `tools/` | Source validation and resource staging tools |

Keep `FarmVillage/` and `GodBarn/` as sibling directories.

## Help continue the project

Useful starting points include qualifying complete clean-clone installation, testing the native app and actual Ubuntu hosting, improving documentation, and restoring one well-defined game feature at a time.

Start with [contributing](CONTRIBUTING.md), the [maintainer guide](TAKEOVER.md) and [current development priorities](HANDOVER_STATUS.md). The [restoration backlog](<Wave 3.md>) and [engineering index](FarmVillage/macOS/Documentation/ENGINEERING_INDEX.md) provide more detail. Please preserve original costs and timers, document unsupported behavior, and distinguish tests from actual gameplay checks.

## Credits and licence

This project builds on the preservation work of **AcidCaos and the Farm Village team**. FarmVillage and the original God Barn code are licensed under **GPL-3.0**; see [LICENSE](LICENSE), [God Barn’s licence](GodBarn/LICENSE) and [credits](GodBarn/CREDITS.md).

Original game resources retain their separate rights and are not covered by the code licence. Ruffle and other dependencies retain their own licences and notices. See [source and resource notices](SOURCE_NOTICE.md) and [third-party notices](FarmVillage/macOS/Documentation/THIRD_PARTY.md).
