# FarmVillage — God Barn Edition

A community preservation fork of [AcidCaos/FarmVillage](https://github.com/AcidCaos/farmvillage), extending the original preservation work with a native macOS application, browser hosting tools and **God Barn**, a companion for inspecting items and editing farms.

The aim is to make the original farming experience playable locally while preserving its prices, timers and game rules. Restoration is incomplete, and contributions are welcome.

**Development status:** a sixteen-world alpha. The public installer downloads original resources, generates God Barn and builds the reviewed local player, but a complete install from a clean computer has not yet been run end to end. On 26 October 2026 an owner-run QA of the published code on an Apple Silicon Mac passed the source checks, the full active-game test suite, the native app build, and bounded Home farming checks in both the native app and a browser, using resources that were already on hand. Actual Ubuntu hosting, all sixteen worlds graphically on the current revision, and long play sessions remain untested. See [validation scope](ACCEPTANCE.md) for exactly what ran.

## Choose how you want to play

| Audience | Where the full game lives | Start here |
| --- | --- | --- |
| **Mac players who can spare the disk space and a few hours** | On your Mac, using the native app; a separate server is not required | [New to this? Mac quick start](#new-to-this-start-here-on-a-mac) · [Mac player guide](docs/PLAY_ON_MAC.md) |
| **People with an Ubuntu/Linux server** | On the host; players connect through their browsers without installing the full archives on each computer | [Server owner guide](docs/PLAY_ON_SERVER.md) · `bash START_HERE.sh` on the host |

The source launchers show the complete download plan, ask for a dedicated folder and require exact confirmation before downloads/builds. They fetch the original client and four artwork WARCs from public sources, generate metadata and build Ruffle. No owner’s Mac files, private server or GitHub account is required.

**Storage:** original compressed artwork is 19.13 GB. Source compilation and extracted artwork require more: the installer conservatively asks for 110 GiB free for Mac or 80 GiB for server resource preparation. The server’s final installation needs additional staging space. Exact fresh-install peak is not yet qualified. Read the appropriate player guide before starting.

## New to this? Start here on a Mac

You do not need to be a programmer to try this. You do need patience. The installer builds the game on your own computer, a bit like baking from scratch instead of buying the cake: the first time takes hours, but nearly all of it is waiting. The installer does the work and tells you what it is doing at each step.

**Honest status:** this is an alpha, and the complete install, from a clean Mac to a farm that survives a restart, has not yet been tested end to end. If you try it, you are one of the first, and your report of what happened is valuable. Nothing here needs an account, a password, an Apple developer membership or a GitHub login.

### What you need first

| You need | Why | Good to know |
| --- | --- | --- |
| A Mac with **macOS 14 or newer** | The game runs as a native Mac app. | Apple Silicon Macs are the ones tested so far. Intel Macs are supported on paper but have not been played yet. |
| About **110 GB free** on one drive | The original artwork alone is 19 GB compressed, and unpacking and building need much more. | This is a cautious allowance, not a measured size. You can check your space in System Settings, General, Storage. 20 GB free is not enough. |
| **Python 3.10 or newer** from [python.org](https://www.python.org/downloads/macos/) | The installer is written in Python. | The `python3` that comes with the Mac does not count, and the installer will not use it. Install the python.org one, then start again. |
| **Full Xcode** from the Mac App Store | It builds the app. | The smaller "Command Line Tools" are not enough. Open Xcode once after installing so it can finish its first-time setup. If the installer still cannot find it, open Xcode, go to Settings, Locations, and choose Xcode under Command Line Tools. |
| A steady internet connection and a few hours | The installer downloads the original game files. | A first installation can take hours. You can leave it running. |

If something is missing, the installer says so and stops before downloading anything.

### The steps

1. On the [repository page](https://github.com/jannsenburke/FarmVillage-GodBarn), choose **Code, then Download ZIP**, and unzip it.
2. Open **Terminal** (press Command and Space, type `Terminal`, press Return). It is the plain text window; you only need to paste or type a few lines. Type `cd ` with a space after it, drag the unzipped folder onto the Terminal window, and press Return. Then run:

   ```sh
   bash START_MAC.command
   ```

   You can also double-click `START_MAC.command` in Finder. If macOS blocks it because it came from the internet, use the Terminal route above instead.
3. Choose **1** to install. The installer shows the full plan first: what it will download, how much space it needs and where it will put things.
4. Give it the path of a **brand new, empty folder** on a drive with plenty of space, for example `/Volumes/Games/FarmVillage`. Not your home folder, not the folder you just unzipped, and not a folder that already has things in it.
5. When you are happy with the plan, type the word `INSTALL` followed by the exact folder path it shows you. Until you do that, nothing is downloaded and nothing is built.
6. Leave Terminal open and let it work. Lots of text scrolling past is normal.
7. When it finishes, the app opens. Choose **Create Farm**, pick a name and start playing. Next time, double-click **PLAY_MAC.command** inside your game folder.

### Things that look scary but are normal

- **A very long wait.** Four large archives download, the artwork is unpacked, and the Flash player is compiled from source. Hours are expected.
- **A wall of text in Terminal.** It is a progress log, not an error. Real problems are named in plain words and the installer stops.
- **An app you built yourself.** It is not signed by Apple's developer program, because it is made on your own Mac.
- **Incomplete corners of the game.** There are sixteen worlds and some regional features are unfinished. [World readiness](WORLD_READINESS.md) says which.

### If something stops

You cannot break anything by stopping and trying again. Fix whatever the message names (a missing Python or Xcode is the usual one), run `bash START_MAC.command` again, and choose the **same** folder. Downloads that already passed their checks are reused. Do not run two installers on the same folder, and do not delete the game folder afterwards: it holds the artwork the app needs and your farms.

For every detail, including what is downloaded from where, read the full [Mac player guide](docs/PLAY_ON_MAC.md). To tell us how it went, [open an install report](https://github.com/jannsenburke/FarmVillage-GodBarn/issues/new?template=install-report.md): a short form where a failure is as useful as a success. See [contributing](CONTRIBUTING.md) for the rest.

## What’s included

- **Native macOS application:** a SwiftUI/AppKit desktop app using WebKit, Ruffle and a supervised local Python server.
- **Browser game server:** Python game logic, persistence and hosting tools for the Ubuntu/Linux browser target. Actual Ubuntu installation and gameplay qualification remain open.
- **God Barn:** an item browser and farm editor with previews, explicit apply actions and supported progression, inventory and crop tools.
- **Sixteen-world alpha:** farming, inventory, travel and selected regional systems, with different restoration limits in each world. See [world readiness](WORLD_READINESS.md).
- **Contributor tools:** synthetic tests, resource recovery utilities, client compatibility work and engineering documentation.

macOS desktop and browser/Ubuntu are the continuing targets. iPad/iOS development is discontinued. Enchanted Glen and Holiday Lights are excluded from the active world roster.

## For contributors: check the source

Players can skip this section. It is for people who want to read, test or change the code.

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

Useful starting points include qualifying complete clean-clone installation, testing the native app and actual Ubuntu hosting, improving documentation, and restoring one well-defined game feature at a time. Mistletoe Lane is the active Christmas-themed world, and a brief covers getting it ready for the holidays.

**No Mac? You can still help.** A read-only review of the retired-world decorations and the Mistletoe Lane recipes needs only Python and about 100 MB of disk: see [asset review without a Mac](docs/briefs/ASSET_REVIEW_NO_MAC.md). More bounded tasks, each written to be picked up cold, are listed under [briefs ready to pick up](HANDOVER_STATUS.md#briefs-ready-to-pick-up).

Start with [contributing](CONTRIBUTING.md), the [maintainer guide](TAKEOVER.md) and [current development priorities](HANDOVER_STATUS.md). The [restoration backlog](<Wave 3.md>) and [engineering index](FarmVillage/macOS/Documentation/ENGINEERING_INDEX.md) provide more detail. Please preserve original costs and timers, document unsupported behavior, and distinguish tests from actual gameplay checks.

## Credits and licence

This project builds on the preservation work of **AcidCaos and the Farm Village team**. FarmVillage and the original God Barn code are licensed under **GPL-3.0**; see [LICENSE](LICENSE), [God Barn’s licence](GodBarn/LICENSE) and [credits](GodBarn/CREDITS.md).

Original game resources retain their separate rights and are not covered by the code licence. Ruffle and other dependencies retain their own licences and notices. See [source and resource notices](SOURCE_NOTICE.md) and [third-party notices](FarmVillage/macOS/Documentation/THIRD_PARTY.md).
