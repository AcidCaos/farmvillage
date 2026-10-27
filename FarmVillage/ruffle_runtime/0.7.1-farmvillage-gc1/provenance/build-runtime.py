"""Maintainer-only rebuild of FarmVillage's pinned dual-WASM Ruffle package.

This script is not run by the game, its installer, or either macOS application.
Supply a clean checkout and the pinned tool versions documented beside it.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

COMMIT = "89a7049965f3090e706265670df309a5128233ac"
HERE = Path(__file__).resolve().parent


def run(arguments, cwd, environment=None, capture=False):
    return subprocess.run(arguments, cwd=cwd, env=environment, check=True,
                          text=True, stdout=subprocess.PIPE if capture else None).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--node", default="node")
    parser.add_argument("--npm-cli", required=True, type=Path)
    parser.add_argument("--wasm-bindgen", default="wasm-bindgen")
    args = parser.parse_args()
    source = args.source.resolve()
    destination = args.destination.absolute()
    if destination.exists():
        parser.error("The destination must be a new directory.")
    if run(["git", "rev-parse", "HEAD"], source, capture=True).strip() != COMMIT:
        parser.error("The source checkout must match the pinned upstream commit.")
    if run(["git", "status", "--porcelain", "--untracked-files=all"], source, capture=True).strip():
        parser.error("Use a clean checkout; the script applies the only source patch itself.")
    for name in ("Cargo.lock", "web/package-lock.json"):
        checked = (HERE / Path(name).name).read_bytes()
        if (source / name).read_bytes() != checked:
            parser.error("The source lock files differ from the reviewed build inputs.")
    rust = run(["rustc", "--version"], source, capture=True).strip()
    if not rust.startswith("rustc 1.99.1 "):
        parser.error("rustc 1.99.1 is required for the reviewed build.")
    if run([args.wasm_bindgen, "--version"], source, capture=True).strip() != "wasm-bindgen 0.2.127":
        parser.error("wasm-bindgen 0.2.127 is required.")
    if run([args.node, "--version"], source, capture=True).strip() != "v24.19.0":
        parser.error("Node v24.19.0 is required for the reviewed package.")
    if run([args.node, str(args.npm_cli), "--version"], source, capture=True).strip() != "11.0.0":
        parser.error("npm 11.0.0 is required.")
    run(["git", "apply", str(HERE / "gc-pacing.patch")], source)
    # LLVM's archiver is essential: native macOS `ar` produces an empty wasm
    # jpegxr archive. CC/CXX must select clang with wasm32 support.
    sysroot = Path(run(["rustc", "--print", "sysroot"], source, capture=True).strip())
    host = next(line.partition(": ")[2] for line in run(["rustc", "-vV"], source, capture=True).splitlines() if line.startswith("host: "))
    environment = dict(os.environ, AR_wasm32_unknown_unknown=str(sysroot / "lib/rustlib" / host / "bin/llvm-ar"), CARGO_BUILD_JOBS="3")
    common = '--cfg=web_sys_unstable_apis --cfg=getrandom_backend="wasm_js" -Aunknown_lints'
    modern = dict(environment, RUSTFLAGS=common + ' -C target-feature=+bulk-memory,+simd128,+nontrapping-fptoint,+sign-ext,+reference-types', RUSTC_BOOTSTRAP="0")
    base = ["cargo", "build", "-p", "ruffle_web", "--features", "jpegxr", "--target", "wasm32-unknown-unknown", "--locked"]
    run(base + ["--profile", "web-wasm-extensions"], source, modern)
    fallback = dict(environment, RUSTFLAGS=common + ' -C target-cpu=mvp', RUSTC_BOOTSTRAP="1", CFLAGS_wasm32_unknown_unknown="-mno-reference-types -mno-multivalue")
    run(base + ["--profile", "web-wasm-mvp", "-Z", "build-std=std,panic_abort"], source, fallback)
    web = source / "web"
    run([args.node, str(args.npm_cli), "ci", "--ignore-scripts"], web, environment)
    core = web / "packages/core"
    selfhosted = web / "packages/selfhosted"
    shutil.copyfile(HERE / "version-seal.json", web / "version_seal.json")
    package_environment = dict(environment, npm_package_version="0.7.1-farmvillage-gc1", CFG_RELEASE_CHANNEL="farmvillage", BUILD_WASM_MVP="true", ENABLE_VERSION_SEAL="true")
    for profile, name, flags in (("web-wasm-extensions", "ruffle_web", ["--reference-types"]), ("web-wasm-mvp", "ruffle_web-wasm_mvp", [])):
        run([args.wasm_bindgen, str(source / "target/wasm32-unknown-unknown" / profile / "ruffle_web.wasm"), "--target", "web", "--out-dir", str(core / "dist"), "--out-name", name] + flags, source, package_environment)
    for command, cwd in ((["../../node_modules/typescript/bin/tsc", "--build", "--force"], core),
                         (["tools/set_version.ts"], core), (["tools/bundle_texts.ts"], core),
                         (["tools/bundle_css.ts"], core), (["../../node_modules/webpack-cli/bin/cli.js"], selfhosted)):
        run([args.node] + command, cwd, package_environment)
    shutil.copytree(selfhosted / "dist", destination)
    package = destination / "package.json"
    metadata = json.loads(package.read_text())
    metadata.update(version="0.7.1-farmvillage-gc1", upstreamVersion="0.7.1")
    package.write_text(json.dumps(metadata, indent=2) + "\n")
    expected = json.loads((HERE / "runtime-files.json").read_text())
    actual = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in destination.iterdir() if path.is_file()}
    if actual != expected:
        raise RuntimeError("Build completed, but output differs from the reviewed runtime file hashes. Preserve it for review; do not install it.")
    print("All twelve runtime files match the reviewed SHA256 pins.")


if __name__ == "__main__":
    main()
