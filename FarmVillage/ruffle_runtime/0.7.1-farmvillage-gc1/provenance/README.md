# Public FarmVillage Ruffle build

The resource installer builds Ruffle from public commit
`89a7049965f3090e706265670df309a5128233ac` and the included
`gc-pacing.patch`. The patch starts incremental collection earlier on wasm32;
it preserves upstream frame scheduling, reachability, renderer, music and the
JPEG XR codec. Ruffle retains its MIT OR Apache-2.0 licenses.

The normal player wizard invokes `tools/build-public-ruffle.py`. Its standalone
equivalent, from the repository root, is:

```sh
python3 tools/build-public-ruffle.py \
  --work /path/to/resource-pack/work/ruffle \
  --output /path/to/resource-pack/Runtime/ruffle_runtime/0.7.1-farmvillage-gc1
```

Both locations must be outside the source checkout. Build tools, compiler
caches, source checkout and temporary files stay in the chosen work folder.
Builds can take hours and require several GB beyond the original game resources.
Nothing is installed globally. Git and a Clang C/C++ toolchain with wasm32
support must already be installed; the player wizard checks prerequisites.

The bootstrap downloads official checksum-pinned Rust 1.99.1 (with wasm32,
rust-src and LLVM tools), Node 24.19.0, npm 11.0.0, wasm-bindgen 0.2.127 and
Temurin Java 17.0.16+8. Pins for Apple Silicon/Intel macOS and ARM64/x86_64
Linux are in `tools/public-ruffle-toolchains.json`. Downloads are anonymous
HTTPS. Git runs with its own empty home and disabled personal configuration,
credential helpers, hooks and prompts.

The recipe checks the exact upstream commit and both lockfiles before applying
the reviewed patch. It builds `jpegxr` in modern `web-wasm-extensions` and
fallback `web-wasm-mvp` profiles. Modern WASM enables bulk memory, SIMD,
nontrapping conversions, sign extension and reference types; fallback uses
`target-cpu=mvp`, `build-std`, and C flags disabling reference types/multivalue.
The matching wasm-bindgen outputs, version seal, TypeScript generators and
self-hosted webpack produce twelve files: loader, two core chunks, two WASM
modules, source maps, metadata, README and licenses. No wasm-opt is applied.
Rust and C source paths map to `/farmvillage-public-build`.

Each host uses its installed Clang, so Linux output is allowed to differ from
Apple Clang output. The completed build receipt records source/patch/recipe,
lockfile/toolchain identities, host/compiler and every output SHA256. The
installer verifies it, adds source provenance, seals the full distribution in
`.farmvillage-ruffle.json`, and binds that manifest hash to its prepared resource
state. Launch requires that explicit prepared pin; it never substitutes an
arbitrary downloaded player. A failed command or partial build is not sealed.

`runtime-files.json` records earlier public Apple Silicon output hashes for
comparison; `historical-runtime-files.json` records older private build hashes.
Neither is a universal output pin for Linux. The strict historical default
runtime pin remains separate from newly prepared source builds.

A verified source build establishes input/output integrity. It does not claim
gameplay, native-window or Ubuntu qualification; those checks need a real game
installation on the relevant target.

[Pinned upstream source](https://github.com/ruffle-rs/ruffle/tree/89a7049965f3090e706265670df309a5128233ac)
