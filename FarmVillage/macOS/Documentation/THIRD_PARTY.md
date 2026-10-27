# Third-party notices

## Farm Village preservation project

- Source: https://github.com/AcidCaos/farmvillage
- Base commit: `2dc25ca24032041a8b68d299b861eb2d4d449653`
- Copyright (C) 2024 The Farm Village team.
- License: GNU General Public License version 3, supplied in the checkout's `LICENSE`
  and copied into the bundled server payload.

Local wrapper code is provided under the same GPL-3.0 license as the project.
The original game client, graphics, sounds, and archived content retain their
respective ownership and notices. The macOS wrapper does not change their provenance.
Game asset archives remain separate downloads from the URLs configured by upstream.

Source and macOS launches use the same version-checked client compatibility
preparation. XML style keys are converted to strings, preserving inherited
numeric hover values and the first-run "Let's Play!" button. Market preparation
memoizes pure date parsing, skips explicitly unbuyable definitions during forced
bulk loading, and checks raw names before expanding definitions for filtering.
The original source SWF is preserved. `client_compatibility.py` pins the complete
input and output bytecode; `macOS/Scripts/patch-game-client.py` is its build CLI
and is retained in `Contents/Resources/WrapperRuntime/`. No diagnostic traces are
shipped. The source-backed sound identity setting is documented separately in
`ClientPatches/audio-identity-review.json`.

The bundled WARC extractor retains its notices for Ryan Chartier and Internet
Archive within `warc_extractor/warc_extractor.py`.

## Ruffle

- Project: https://ruffle.rs/
- Source: https://github.com/ruffle-rs/ruffle
- Upstream version: **0.7.1**, commit `89a7049965f3090e706265670df309a5128233ac`.
- Local compatibility build: **0.7.1-farmvillage-gc1**, vendored in
  `ruffle_runtime/0.7.1-farmvillage-gc1/` and installed from the app without a
  runtime download.
- The wasm-only patch starts incremental garbage collection earlier and increases
  its work rate. Frame scheduling, audio, codecs and renderer remain upstream.
- The complete matching loader/core/modern and MVP WASM distribution retains
  upstream MIT and Apache-2.0 licenses. Its `provenance/` folder includes the exact
  source patch, lock files, version seal, build driver, output hashes and audit.

Ruffle's own repository supplies MIT and Apache-2.0 license texts and licensing
details. Keep all package files and notices together. Ruffle is a Flash emulator;
The validation record distinguishes emulator startup from game feature coverage.

`runtime_compatibility.py` pins the complete manifest independently and verifies
installed and served bytes. Existing official 0.7.1 profile files are preserved;
the legacy official downloader remains available internally but is not used by
normal Prepare or Start. Future updates require a deliberate pin and compatibility
checks. Native acceptance is recorded in `VALIDATION.md` separately from build
provenance.

## Python packages and icon

The runtime installs the versions listed in upstream `requirements.txt` and their
transitive dependencies into an isolated environment. Their package metadata carries
their respective licenses. Audit installations use isolated virtual environments;
the application prepares its own environment when requested.

The app icon is the original geometric farm artwork from the adjacent FV Replowed
macOS wrapper project, reused for this local sibling application. It is separate
from the preserved game's graphics.

## Heritage launcher assets

The curated `Contents/Resources/Heritage/` pack contains original FarmVille
artwork, animation frames, Merkin and BadaBoom fonts, and sounds. Its `manifest.json`
records exact source and exported hashes, logical paths, extraction recipes, and
uncertain first-use dates. `NOTICES.md` retains the pack's ownership and font
information. `macOS/Scripts/prepare-heritage-assets.py` reproduces the curated
exports from explicit local source paths. No synthetic replacement artwork is used.

## God Barn companion

The native runtime includes the sibling GodBarn engine, live adapter, local UI,
compressed catalog, and thumbnail map. Its working saves, tests, development
screenshots, and copied thumbnail collection are excluded from the app. The
packaged UI assets retain their original provenance in the companion's notices
and mappings; catalog thumbnails resolve from the active profile's extracted game
archive.
