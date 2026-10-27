# FarmVillage Ruffle GC compatibility build

This is a separately identified build of Ruffle 0.7.1 at upstream commit
`89a7049965f3090e706265670df309a5128233ac`. The only tracked Rust source change
is the accompanying `gc-pacing.patch`: on wasm32, install smaller gc-arena
sleep/work factors before creating player globals. This allows incremental
collection to begin earlier and do more work before the 4 GiB linear heap fills.
It preserves normal frame scheduling, reachability, drop behavior, codecs,
original game music, and the upstream renderer. It adds no allocator logging,
Arena tracing, forced collection, PixelBender instrumentation, or runtime debug API.

Keeping this directory in the repository does not select or install it. Selection
uses the separately reviewed `runtime_compatibility.ACTIVE_RELEASE` manifest pin.
Native acceptance evidence is recorded separately. The previous official Ruffle
0.7.1 runtime is preserved in existing profiles.

The twelve runtime files are the complete self-hosted distribution: matching
loader, core chunks, modern and MVP WebAssembly, source maps, package metadata,
upstream README, and MIT/Apache licenses. `runtime-files.json` pins those outputs.
The outer `.farmvillage-ruffle.json` additionally pins every provenance file.

## Maintainer rebuild

End users need no Rust, Cargo, Node, npm, LLVM, or wasm-bindgen. These tools are
only used to produce the already vendored package.

Use a fresh checkout of the exact upstream commit with its normal submodules,
Rust 1.99.1 (`58cf8f9c35b355199727627d07ae34a4e2846d67`, LLVM 23.1.1), the
`wasm32-unknown-unknown` target, `rust-src` and `llvm-tools` components,
wasm-bindgen CLI 0.2.127, Node v24.19.0 and npm 11.0.0. The included Cargo.lock
and npm package-lock.json are byte-identical to the pinned upstream checkout.
Run npm with `ci --ignore-scripts`; invoke the explicit upstream build steps.
The complete adaptable command driver is `build-runtime.py`:

```sh
python3 build-runtime.py --source /absolute/path/to/clean/ruffle \
  --destination /absolute/path/to/new/output \
  --node /absolute/path/to/node \
  --npm-cli /absolute/path/to/npm/bin/npm-cli.js \
  --wasm-bindgen /absolute/path/to/wasm-bindgen
```

Both Cargo builds use `-p ruffle_web --features jpegxr --locked` and the wasm32
target, preserving the full JPEG XR codec. The modern profile enables bulk
memory, SIMD, nontrapping float-to-int, sign extension and reference types;
wasm-bindgen receives `--reference-types`. The fallback uses `target-cpu=mvp`,
`RUSTC_BOOTSTRAP=1`, and `-Z build-std=std,panic_abort`; its C codec flags disable
reference types and multivalue. Both builds set `AR_wasm32_unknown_unknown` to
the Rust sysroot's host `llvm-ar`. Native macOS `ar` creates an empty wasm codec
archive and must not be substituted. Both use `CARGO_BUILD_JOBS=3`.

Packaging uses the fixed `version-seal.json`, matching bindgen output for both
modules, TypeScript build, version/text/CSS generation, and self-hosted webpack.
No wasm-opt pass was applied. The driver compares all twelve final SHA256s and
refuses to call a different output the reviewed build. The executed build used
an Apple Silicon macOS host; rebuilding on another host must pass those pins or
receive a new review. No claim of cross-host byte reproducibility is implied.

The fork remains under upstream's MIT OR Apache-2.0 licenses, retained at the
package root. Upstream source: https://github.com/ruffle-rs/ruffle/tree/89a7049965f3090e706265670df309a5128233ac
