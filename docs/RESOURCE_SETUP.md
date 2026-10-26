# Public resource installer

The active installer acquires originals, extracts artwork, generates God Barn, builds reviewed Ruffle and prepares native Mac or Ubuntu/Linux installation. Follow the [Mac guide](PLAY_ON_MAC.md) or [server guide](PLAY_ON_SERVER.md).

**Qualification:** the complete public installation was not run on the owner’s Mac for this update. No large downloads, real compiler/toolchain builds or Ubuntu session were used. Small synthetic archives and mocked build/staging tests cover the implementation. Full clean-clone installation, native gameplay and actual Ubuntu gameplay/persistence still require qualification.

## Download sources

| Public source | Purpose and verification |
| --- | --- |
| [Pinned AcidCaos/FarmVillage](https://github.com/AcidCaos/farmvillage/tree/2dc25ca24032041a8b68d299b861eb2d4d449653) | Original client, configuration, starter templates and browser media. Byte sizes/Git blob identities are pinned in [the manifest](../tools/public-resources.json). |
| [Internet Archive original-farmville](https://archive.org/download/original-farmville/) | Four WARCs ending `00000`–`00003`, totalling **19,126,111,395 bytes**. Pinned sizes, SHA-1 and MD5 checksums. |
| PyPI / files.pythonhosted.org | Runtime packages and Pillow for generation; [preparation requirements](../tools/preparation-requirements.txt). |
| GitHub, Rust distribution servers, Node.js, npm and Cargo registries | Pinned Ruffle source/submodules, reviewed patch, Rust/Node/npm/wasm-bindgen/Adoptium Java tools for both hosts and locked dependencies. See [toolchain pins](../tools/public-ruffle-toolchains.json) and [provenance](../FarmVillage/ruffle_runtime/0.7.1-farmvillage-gc1/provenance/README.md). |
| GitHub FFDec / Eclipse Adoptium | Mac image/font extraction tools pinned by checksum in [native preparation](../tools/native_resources.py). |

Downloads use anonymous public access. The installer does not request tokens, clone private repositories or read browser sessions. Build commands use an isolated HOME/cache in the chosen folder. Original media keeps its separate rights; see [resource notices](../SOURCE_NOTICE.md).

## Consent, storage and retry

Source launchers show a plan first. Installation requires a dedicated ordinary folder outside source and exact path confirmation. Unrelated, linked, system and source targets are refused. Preparation does not erase an existing game installation or import player state.

Conservative preparation requirements: **110 GiB free for Mac**, **80 GiB for server resources**. Resource-folder budgets are 100/70 GiB respectively, with a 5 GiB disk reserve. Exact fresh-install peak is unmeasured; these guards may pause a build. The server’s final installation additionally copies runtime/artwork and checks staging space before its explicit wipe confirmation.

One WARC is downloaded, verified and extracted at a time, then its compressed file is removed. Interrupted downloads keep `.part` files. Valid HTTP Range responses resume; sources ignoring Range restart the file. Interrupted extraction replays the same archive. Completed extraction receipts avoid unnecessary downloads. Keep the prepared originals/receipts intact between retries.

Ruffle compilation takes time and disk. Tools/caches remain inside the chosen folder. Closing setup stops its owned build process group. Rerun with the same folder to retry. Repeated checksum failure may require removing only the named failed `.part` inside the owned `downloads/` directory before retry.

## Generated layout

| Location within the resource root | Contents |
| --- | --- |
| `original/` | Pinned upstream originals |
| `assets/` | Extracted artwork shared by the Mac app |
| `godbarn/` | Generated catalogue, labels, skins, progression |
| `Runtime/` | Patched runtime, prepared companion, source-built Ruffle |
| `Runtime/PREPARED_RUNTIME.json` | Explicit local player manifest identity |
| `Runtime/PUBLIC_RUNTIME_BUILD.json` | Source/toolchain/output receipt |
| `native/` | Mac images, font and icon |
| `python/` | Preparation environment |
| `work/`, `tools/`, `downloads/` | Isolated build workspace, tools, downloads |
| `assets-manifest.jsonl`, `resource-state.json` | Artwork identities and complete runtime seal |
| `macos-build/` | Mac build output and app |
| `browser-release/` | Prepared server bundle |

Generated folders never belong in the GitHub source upload. `PrivateInputs.expected.json` remains a historical resource baseline. New public packs use their own source-build receipts and seals. Compiler differences are recorded without pretending the output matches the old Mac binary hash.

## Command-line plan and verification

Run from the repository root, choosing an absolute new folder on your own machine:

```sh
# Plan only: no folder, download, environment or build.
python3 -I -B tools/setup-resources.py --audience mac --resources /absolute/new/FarmVillage

# Explicitly consent to downloads and builds.
python3 -I -B tools/setup-resources.py --audience mac --resources /absolute/new/FarmVillage --accept-downloads

# Verify all sealed runtime/artwork files without downloading.
python3 -I -B tools/setup-resources.py --audience mac --resources /absolute/new/FarmVillage --check
```

Use `--audience server` for server preparation. Resource-only setup does not launch the app or install a service. The guided source launchers handle subsequent steps.

Sixteen worlds remain active; Enchanted Glen and Holiday Lights are retired. Original costs/timers/earned rewards are preserved. Historical prize curation unrecoverable from originals is explicitly empty. Setup does not establish that every original feature is restored.
