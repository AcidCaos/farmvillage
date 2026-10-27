# Play on your Mac

This route builds the native Mac app and keeps the game on your computer. You do not need a server or the project owner's Mac. The game is a sixteen-world alpha with incomplete regional features; see [world readiness](../WORLD_READINESS.md).

The installer downloads the preserved originals, extracts the artwork, generates God Barn's catalogue and the native launcher artwork, builds the pinned Ruffle player from public source, and builds an unsigned Mac app. **It is a large installation, not a small app download.**

## Before you start

You need:

- **macOS 14 or newer**, on an Apple Silicon or Intel Mac.
- An **already installed Python 3.10 or newer**, such as the installer from [python.org](https://www.python.org/downloads/macos/).
- **Full Xcode with its macOS SDK already installed**. Command Line Tools alone cannot build this app. Open Xcode once and finish its normal first-launch setup before running this installer.
- A reliable internet connection and **at least 110 GiB free** on the volume you choose for the game.

Python and Xcode are prerequisites; this installer does not install them. The game is built locally without signing, a developer membership, a GitHub token or access to your accounts. The installer does not read your Keychain or search your computer for another person's resources.

## Install, step by step

1. On the [repository page](https://github.com/jannsenburke/FarmVillage-GodBarn), choose **Code → Download ZIP** and extract it. An existing clone works too. Keep this source folder separate from the large game installation.
2. Double-click **START_MAC.command** in the extracted folder. If you prefer Terminal, change to that folder and run:

   ```sh
   bash START_MAC.command
   ```

3. Choose **1 — install** in the Mac setup menu. Read the download, disk-space and destination plan before continuing.
4. Enter the full path of a **new, dedicated game folder**, for example `/Volumes/Games/FarmVillage`. Choose a location you can keep: the app will use the extracted artwork there. Do not choose your home folder, the source checkout, an existing collection of files or a system folder.
5. Check the exact destination displayed. Type **INSTALL followed by the displayed absolute folder path** only when you want the downloads and builds to begin. Before that confirmation, the installer shows the plan without downloading the game or starting a build.
6. Leave the Terminal window open. It reports each download, integrity check, extraction and build. The four game archives alone are 19.13 GB; extraction and the player build can take a long time. A first installation may take hours, depending on your connection and Mac.
7. The installer prepares the app’s Python engine and opens the app using your installation’s `player-data` folder. It also creates **PLAY_MAC.command** in the chosen game folder for later launches.
8. In the app, choose **Create Farm**, enter your farmer name and follow its prompts. Watch **Activity** for startup details. If the app later needs repair, use **Settings → Setup → Prepare Runtime**; this reinstalls the app environment’s pinned Python packages from PyPI.

With `PACK` meaning the game folder you selected, the app is built at:

```text
PACK/macos-build/DerivedData/Build/Products/Release/FarmVillage.app
```

Double-click **PLAY_MAC.command** in your chosen game folder for later sessions so it keeps using `PACK/player-data`. If opening the app manually, pass the same data folder:

```sh
open "/your/game/folder/macos-build/DerivedData/Build/Products/Release/FarmVillage.app" --args --farmvillage-data-dir "/your/game/folder/player-data"
```

Replace both `/your/game/folder` examples with your installation's full path. The app's normal direct-open default is `~/Library/Application Support/FarmVillage`; the generated shortcut avoids accidentally creating a second set of farm data there.

**Prepare Runtime does not download the game archives again.** This public build reads its `PUBLIC_INSTALL.json` receipt and uses `PACK/assets` as a shared input. It does not copy that large artwork collection into the app or into `player-data`. If that archive is missing or incomplete, Start reports the problem and directs you back to the installer.

## What downloads, and where it goes

| Input | Original source | Purpose |
| --- | --- | --- |
| Original client, configuration, browser images and starter templates | Pinned public revision of [AcidCaos/farmvillage](https://github.com/AcidCaos/farmvillage/tree/2dc25ca24032041a8b68d299b861eb2d4d449653) | Original game inputs; identities are listed in `tools/public-resources.json` |
| Four preserved WARC archives | [Internet Archive's original-farmville collection](https://archive.org/details/original-farmville) | Original artwork, audio and fonts; downloads are checked against pinned sizes and digests |
| Ruffle and its build dependencies | Pinned [Ruffle source](https://github.com/ruffle-rs/ruffle), Rust distribution, Node.js/npm and Eclipse Temurin Java sources | Builds the reviewed player with the project's compatibility patch; the installer records the resulting identity |
| FFDec 26.4.0 and Temurin Java 17 | [JPEXS releases](https://github.com/jindrapetrik/jpexs-decompiler/releases/tag/version26.4.0) and [Adoptium](https://github.com/adoptium/temurin17-binaries/releases) | Recovers original launcher artwork from archived SWFs; no private display font is needed |
| Python dependencies | [PyPI](https://pypi.org/) | Isolated installer/game environments; no global package installation |

Downloads, extracted assets, generated catalogues, tool state and build products stay in your selected game folder. The source checkout stays separate. God Barn's public metadata is generated from the original catalogue and the project's policy code; no old farm, owner's backup or private server configuration is required. Original artwork, marks, audio and fonts retain their creators' rights; see [resource setup](RESOURCE_SETUP.md) and the notices supplied with the resources.

The four compressed archives total **19,126,111,395 bytes — 19.13 GB / 17.81 GiB**. This is only one part of the installation. Extracted files, download caches, Rust/Node/Java tools, the Ruffle source build, Xcode output and game data need additional space.

The installer uses a conservative **110 GiB free-space preflight**, a **100 GiB installation budget** and a **5 GiB free-space reserve**. These are protective checks, not a measured fresh-install peak or a filesystem quota. A complete real installation's peak usage has not yet been qualified. **Having only 20 GB free is insufficient.**

## If something stops

Keep the source folder and the chosen game folder. Run **START_MAC.command** again and choose the same installation folder to retry. Verified downloads are reused. Partial downloads resume when the server supports byte ranges; otherwise that file restarts. An interrupted extraction or build may need to repeat its current step. Do not start a second installer against the same folder.

Read the named failure before changing anything. A missing Python or full Xcode installation must be fixed separately. A digest failure is not a successful download. A disk-space refusal means the installer will not safely continue with the available space. Do not solve these errors by copying files from an unrelated installation.

Keep the whole installation folder after success: `assets` is required for play, and `player-data` holds your new farms and app runtime. Do not delete it as temporary build trash. Avoid manually deleting individual caches while setup is running. Retry the installer after correcting the reported problem.

## What has actually been checked

The installation and native staging paths have synthetic fixture coverage for resource identities, external output paths, player-pin propagation, artwork staging and reuse of the external archive without another WARC download. **The complete public download, native build and fresh-Mac farming/save/restart journey have not been executed together for this installer.** Fixture tests and a build path do not constitute gameplay acceptance.

If you want to host the game once for browser players, use [the server instructions](PLAY_ON_SERVER.md). Developers can use the [build guide](DEVELOPMENT.md).
