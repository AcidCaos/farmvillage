"""Build FarmVillage's dual-WASM player from the reviewed public source recipe.

The installer supplies an isolated checkout and checksum-pinned tools. The
default mode compares historical public Mac outputs; --source-build records
host-local outputs for the installer to seal with its verified build receipt.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess

COMMIT = "89a7049965f3090e706265670df309a5128233ac"
HERE = Path(__file__).resolve().parent


def run(arguments, cwd, environment, capture=False):
    if str(arguments[0]) == "git":
        arguments = ["git", "-c", "credential.helper=", "-c", "core.askPass=/usr/bin/false",
                     "-c", "credential.interactive=false", *arguments[1:]]
    return subprocess.run(arguments, cwd=cwd, env=environment, check=True,
                          text=True, stdout=subprocess.PIPE if capture else None).stdout


def isolated_environment(source):
    allowed = ("PATH", "LANG", "LC_ALL", "SDKROOT", "MACOSX_DEPLOYMENT_TARGET",
               "CC_wasm32_unknown_unknown", "CXX_wasm32_unknown_unknown", "JAVA_HOME")
    environment = {key: os.environ[key] for key in allowed if key in os.environ}
    home = source.parent / "home"
    config = source.parent / "config"
    temporary = source.parent / "tmp"
    home.mkdir(parents=True, exist_ok=True)
    config.mkdir(parents=True, exist_ok=True)
    temporary.mkdir(parents=True, exist_ok=True)
    environment.update(HOME=str(home), XDG_CONFIG_HOME=str(config), TMPDIR=str(temporary),
                       CARGO_HOME=str(source.parent / "cargo-home"), CARGO_TARGET_DIR=str(source.parent / "cargo-target"),
                       GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GIT_CONFIG_NOSYSTEM="1",
                       NETRC=os.devnull,
                       GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="/usr/bin/false", SSH_ASKPASS="/usr/bin/false",
                       GCM_INTERACTIVE="Never", CARGO_NET_GIT_FETCH_WITH_CLI="true",
                       npm_config_cache=str(source.parent / "npm-cache"), npm_config_userconfig=os.devnull)
    overrides = [("credential.helper", ""), ("core.askPass", "/usr/bin/false"),
                 ("credential.interactive", "false"), ("protocol.allow", "never"), ("protocol.https.allow", "always"),
                 ("core.hooksPath", os.devnull)]
    environment["GIT_CONFIG_COUNT"] = str(len(overrides))
    for index, (key, value) in enumerate(overrides):
        environment[f"GIT_CONFIG_KEY_{index}"] = key
        environment[f"GIT_CONFIG_VALUE_{index}"] = value
    return environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--node", default="node")
    parser.add_argument("--npm-cli", required=True, type=Path)
    parser.add_argument("--wasm-bindgen", default="wasm-bindgen")
    parser.add_argument("--repro-candidate", action="store_true", help="Build a comparison candidate without approving different output pins")
    parser.add_argument("--source-build", action="store_true", help="Produce host-local files for the public installer receipt")
    args = parser.parse_args()
    source = args.source.resolve()
    destination = args.destination.absolute()
    environment = isolated_environment(source)
    if destination.exists():
        parser.error("The destination must be a new directory.")
    if run(["git", "rev-parse", "HEAD"], source, environment, capture=True).strip() != COMMIT:
        parser.error("The source checkout must match the pinned upstream commit.")
    if run(["git", "status", "--porcelain", "--untracked-files=all"], source, environment, capture=True).strip():
        parser.error("Use a clean checkout; the script applies the only source patch itself.")
    for name in ("Cargo.lock", "web/package-lock.json"):
        checked = (HERE / Path(name).name).read_bytes()
        if (source / name).read_bytes() != checked:
            parser.error("The source lock files differ from the reviewed build inputs.")
    rust = run(["rustc", "--version"], source, environment, capture=True).strip()
    if not rust.startswith("rustc 1.99.1 "):
        parser.error("rustc 1.99.1 is required for the reviewed build.")
    if run([args.wasm_bindgen, "--version"], source, environment, capture=True).strip() != "wasm-bindgen 0.2.127":
        parser.error("wasm-bindgen 0.2.127 is required.")
    if run([args.node, "--version"], source, environment, capture=True).strip() != "v24.19.0":
        parser.error("Node v24.19.0 is required for the reviewed package.")
    if run([args.node, str(args.npm_cli), "--version"], source, environment, capture=True).strip() != "11.0.0":
        parser.error("npm 11.0.0 is required.")
    run(["git", "apply", str(HERE / "gc-pacing.patch")], source, environment)
    # LLVM's archiver is essential: native macOS `ar` produces an empty wasm
    # jpegxr archive. CC/CXX must select clang with wasm32 support.
    sysroot = Path(run(["rustc", "--print", "sysroot"], source, environment, capture=True).strip())
    host = next(line.partition(": ")[2] for line in run(["rustc", "-vV"], source, environment, capture=True).splitlines() if line.startswith("host: "))
    environment.update(AR_wasm32_unknown_unknown=str(sysroot / "lib/rustlib" / host / "bin/llvm-ar"), CARGO_BUILD_JOBS="3")
    # Panic/source-location strings otherwise embed the caller's absolute Cargo,
    # Rust-src and checkout paths. Encode flags so paths containing spaces work.
    canonical = "/farmvillage-public-build"
    common = ["--cfg=web_sys_unstable_apis", '--cfg=getrandom_backend="wasm_js"', "-Aunknown_lints",
              "--remap-path-prefix=" + str(source.parent) + "=" + canonical]
    c_mapping = shlex.quote("-ffile-prefix-map=" + str(source.parent) + "=" + canonical)
    environment.update(CC_SHELL_ESCAPED_FLAGS="1", CFLAGS_wasm32_unknown_unknown=c_mapping,
                       CXXFLAGS_wasm32_unknown_unknown=c_mapping)
    modern = dict(environment, CARGO_ENCODED_RUSTFLAGS="\x1f".join(common + ["-C", "target-feature=+bulk-memory,+simd128,+nontrapping-fptoint,+sign-ext,+reference-types"]), RUSTC_BOOTSTRAP="0")
    base = ["cargo", "build", "-p", "ruffle_web", "--features", "jpegxr", "--target", "wasm32-unknown-unknown", "--locked"]
    run(base + ["--profile", "web-wasm-extensions"], source, modern)
    fallback = dict(environment, CARGO_ENCODED_RUSTFLAGS="\x1f".join(common + ["-C", "target-cpu=mvp"]), RUSTC_BOOTSTRAP="1",
                    CFLAGS_wasm32_unknown_unknown=c_mapping + " -mno-reference-types -mno-multivalue",
                    CXXFLAGS_wasm32_unknown_unknown=c_mapping + " -mno-reference-types -mno-multivalue")
    run(base + ["--profile", "web-wasm-mvp", "-Z", "build-std=std,panic_abort"], source, fallback)
    web = source / "web"
    run([args.node, str(args.npm_cli), "ci", "--ignore-scripts"], web, environment)
    core = web / "packages/core"
    selfhosted = web / "packages/selfhosted"
    shutil.copyfile(HERE / "version-seal.json", web / "version_seal.json")
    package_environment = dict(environment, npm_package_version="0.7.1-farmvillage-gc1", CFG_RELEASE_CHANNEL="farmvillage", BUILD_WASM_MVP="true", ENABLE_VERSION_SEAL="true")
    target_root = Path(environment.get("CARGO_TARGET_DIR", source / "target"))
    for profile, name, flags in (("web-wasm-extensions", "ruffle_web", ["--reference-types"]), ("web-wasm-mvp", "ruffle_web-wasm_mvp", [])):
        run([args.wasm_bindgen, str(target_root / "wasm32-unknown-unknown" / profile / "ruffle_web.wasm"), "--target", "web", "--out-dir", str(core / "dist"), "--out-name", name] + flags, source, package_environment)
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
    if args.source_build:
        print("Public source build complete; the installer must verify and seal its complete output inventory.")
        return
    if args.repro_candidate:
        report = {"schema": 1, "kind": "public-source-build-comparison-candidate", "qualified": False,
                  "upstream_commit": COMMIT, "files": actual, "canonical_source_prefix": canonical}
        destination.with_name(destination.name + ".candidate.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print("Public source comparison candidate built; no changed output has been approved.")
        return
    if actual != expected:
        raise RuntimeError("Build completed, but output differs from the reviewed runtime file hashes. Preserve it for review; do not install it.")
    print("All twelve runtime files match the reviewed SHA256 pins.")


if __name__ == "__main__":
    main()
