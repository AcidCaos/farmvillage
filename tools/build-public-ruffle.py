#!/usr/bin/env python3
"""Build the GC compatibility player from anonymous public sources, locally.

Downloads and compiler caches stay under --work. Nothing is installed globally.
This can take hours and several GB; it is invoked only after the player's setup
wizard has shown its storage plan and received download consent.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import ssl
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
RUNTIME_ID = "0.7.1-farmvillage-gc1"
COMMIT = "89a7049965f3090e706265670df309a5128233ac"
# The source-build recipe. Deliberately NOT inside FarmVillage/ruffle_runtime/<id>/: that directory is the
# hard-pinned historical player, whose manifest names its own provenance/ files by hash.
PUBLIC_BUILD_INPUTS = ROOT / "tools/public-ruffle-build"
PINS_PATH = ROOT / "tools/public-ruffle-toolchains.json"
MARKER = ".farmvillage-public-ruffle-work.json"
PRODUCT = "org.farmvillage.public-ruffle-build.v1"


class BuildError(ValueError):
    pass


def digest(path, algorithm="sha256"):
    value = hashlib.new(algorithm)
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def atomic_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def ordinary(path):
    path = Path(path).absolute()
    for entry in (path, *path.parents):
        if entry.is_symlink():
            raise BuildError("Choose an ordinary build/output folder without symbolic links.")
    return path


def host_identity(system=None, machine=None):
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    cpu = {"arm64": "aarch64", "aarch64": "aarch64", "x86_64": "x86_64", "amd64": "x86_64"}.get(machine)
    if system not in ("darwin", "linux") or cpu is None:
        raise BuildError("Public player builds support Intel/Apple Silicon macOS and x86_64/ARM64 Ubuntu/Linux.")
    return (cpu + ("-apple-darwin" if system == "darwin" else "-unknown-linux-gnu"),
            system + ("-arm64" if cpu == "aarch64" else "-x64"))


def toolchain_artifacts(pins, host, node_host):
    """Fixed official URLs and reviewed archive checksums; no release discovery."""
    rust = pins["rustVersion"]
    base = "https://static.rust-lang.org/dist/" + pins["rustDate"] + "/"
    artifacts = []
    for component, checksum in pins["rust"][host].items():
        name = f"{component}-{rust}-{host}.tar.xz"
        artifacts.append(dict(name=name, url=base + name, sha256=checksum, kind="rust"))
    for name, checksum in ((f"rust-src-{rust}.tar.xz", pins["rustSrc"]),
                           (f"rust-std-{rust}-wasm32-unknown-unknown.tar.xz", pins["rustWasm"])):
        artifacts.append(dict(name=name, url=base + name, sha256=checksum, kind="rust"))
    name = f"node-v{pins['nodeVersion']}-{node_host}.tar.xz"
    artifacts.append(dict(name=name, url=f"https://nodejs.org/dist/v{pins['nodeVersion']}/{name}",
                          sha256=pins["node"][node_host], kind="node"))
    bindgen_host = "x86_64-unknown-linux-musl" if host == "x86_64-unknown-linux-gnu" else host
    name = f"wasm-bindgen-{pins['bindgenVersion']}-{bindgen_host}.tar.gz"
    artifacts.append(dict(name=name, url=f"https://github.com/wasm-bindgen/wasm-bindgen/releases/download/{pins['bindgenVersion']}/{name}",
                          sha256=pins["bindgen"][bindgen_host], kind="bindgen"))
    cpu = "aarch64" if host.startswith("aarch64") else "x64"
    system = "mac" if "apple" in host else "linux"
    version, build = pins["javaVersion"].split("+")
    name = f"OpenJDK17U-jdk_{cpu}_{system}_hotspot_{version}_{build}.tar.gz"
    artifacts.append(dict(name=name, url=f"https://github.com/adoptium/temurin17-binaries/releases/download/jdk-{version}%2B{build}/{name}",
                          sha256=pins["java"][node_host], kind="java"))
    name = "npm-" + pins["npmVersion"] + ".tgz"
    artifacts.append(dict(name=name, url="https://registry.npmjs.org/npm/-/" + name,
                          sha512=base64.b64decode(pins["npmIntegrity"], validate=True).hex(), kind="npm"))
    return artifacts


def download_artifact(entry, destination):
    """Anonymous HTTPS only. No cookie jar, netrc, browser or credential helper."""
    destination = ordinary(destination)
    algorithm = "sha256" if "sha256" in entry else "sha512"
    expected = entry[algorithm]
    if destination.is_file() and not destination.is_symlink() and digest(destination, algorithm) == expected:
        return destination
    certificate = next((Path(value) for value in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt") if Path(value).is_file()), None)
    if certificate is None:
        raise BuildError("Install the operating system's CA certificates before downloading public tools.")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                        urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=str(certificate))))
    # urllib's default redirect handler can follow HTTP. Require HTTPS at every hop.
    class HTTPSRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            parsed = urlsplit(newurl)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
                raise BuildError("A toolchain download attempted an insecure redirect.")
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    opener.add_handler(HTTPSRedirect())
    parsed = urlsplit(entry["url"])
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise BuildError("Toolchain downloads require HTTPS.")
    temporary = ordinary(destination.with_name(destination.name + ".part"))
    try:
        total = 0
        checksum = hashlib.new(algorithm)
        request = urllib.request.Request(entry["url"], headers={"User-Agent": "FarmVillage-public-resource-setup/1"})
        with opener.open(request, timeout=45) as response, temporary.open("wb") as target:
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > 1024 * 1024 * 1024:
                    raise BuildError("A toolchain archive exceeded its 1 GiB download limit.")
                if shutil.disk_usage(destination.parent).free < 5 * 1024**3 + len(chunk):
                    raise BuildError("The player tool download reached its 5 GiB free-space reserve; choose a larger resource volume.")
                checksum.update(chunk)
                target.write(chunk)
        if checksum.hexdigest() != expected:
            raise BuildError("Official toolchain archive checksum mismatch: " + entry["name"])
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def extract_archive(archive, target):
    """Extract pinned toolchain archives, rejecting unsafe members and links."""
    archive, target = ordinary(archive), ordinary(target)
    target.mkdir(parents=True, exist_ok=True)
    root = target.resolve()
    with tarfile.open(archive) as contents:
        members = contents.getmembers()
        if sum(member.size for member in members) > 8 * 1024**3:
            raise BuildError("Toolchain extraction exceeds its 8 GiB limit.")
        for member in members:
            relative = PurePosixPath(member.name)
            if relative.is_absolute() or ".." in relative.parts or "\\" in member.name:
                raise BuildError("A toolchain archive contains an unsafe path.")
            destination = root.joinpath(*relative.parts)
            if not destination.resolve().is_relative_to(root):
                raise BuildError("A toolchain archive escapes its folder.")
            if member.issym() or member.islnk():
                link = PurePosixPath(member.linkname)
                linked = (destination.parent if member.issym() else root).joinpath(*link.parts)
                if link.is_absolute() or not linked.resolve().is_relative_to(root):
                    raise BuildError("A toolchain archive contains an unsafe link.")
            elif not (member.isdir() or member.isfile()):
                raise BuildError("A toolchain archive contains an unsupported special file.")
            # Recheck immediately before every extraction, so links created by
            # earlier members cannot redirect a later member outside the root.
            # This also works on Python 3.11 installations predating data_filter.
            contents.extract(member, root)
    roots = list(target.iterdir())
    if len(roots) != 1 or not roots[0].is_dir():
        raise BuildError("A toolchain archive has an unexpected layout.")
    return roots[0]


def run(arguments, cwd, environment, *, capture=False):
    print("Player build: " + Path(str(arguments[0])).name + " " + " ".join(str(x) for x in arguments[1:3]), flush=True)
    result = subprocess.run([str(x) for x in arguments], cwd=cwd, env=environment, check=True,
                            text=True, stdout=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else ""


def isolated_environment(work, path):
    home = ordinary(work / "home")
    home.mkdir(exist_ok=True)
    temporary = ordinary(work / "tmp")
    temporary.mkdir(exist_ok=True)
    environment = dict(PATH=path, HOME=str(home), XDG_CONFIG_HOME=str(work / "config"),
                       TMPDIR=str(temporary), LANG="en_US.UTF-8", LC_ALL="C",
                       CARGO_HOME=str(work / "cargo-home"), CARGO_TARGET_DIR=str(work / "cargo-target"),
                       GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GIT_CONFIG_NOSYSTEM="1",
                       NETRC=os.devnull,
                       GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="/usr/bin/false", SSH_ASKPASS="/usr/bin/false",
                       GCM_INTERACTIVE="Never", CARGO_NET_GIT_FETCH_WITH_CLI="true",
                       npm_config_cache=str(work / "npm-cache"), npm_config_userconfig=os.devnull)
    overrides = [("credential.helper", ""), ("core.askPass", "/usr/bin/false"),
                 ("credential.interactive", "false"), ("protocol.allow", "never"),
                 ("protocol.https.allow", "always"), ("core.hooksPath", os.devnull)]
    environment["GIT_CONFIG_COUNT"] = str(len(overrides))
    for index, (key, value) in enumerate(overrides):
        environment[f"GIT_CONFIG_KEY_{index}"] = key
        environment[f"GIT_CONFIG_VALUE_{index}"] = value
    return environment


def compatibility_module():
    spec = importlib.util.spec_from_file_location("farmvillage_public_compatibility", ROOT / "FarmVillage/runtime_compatibility.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_public_runtime(work, output, *, runner=run, fetch=download_artifact):
    work, output = ordinary(work), ordinary(output)
    if work == ROOT or ROOT in work.parents or output == ROOT or ROOT in output.parents:
        raise BuildError("Choose build and player folders outside the source checkout.")
    if work == output or work in output.parents or output in work.parents:
        raise BuildError("Build work and player output must be separate folders.")
    work.mkdir(parents=True, exist_ok=True)
    marker = work / MARKER
    identity = {"schema": 1, "product": PRODUCT, "work": str(work)}
    if marker.exists():
        if marker.is_symlink() or json.loads(marker.read_text()) != identity:
            raise BuildError("This is not the named managed player build workspace.")
    elif any(work.iterdir()):
        raise BuildError("Choose a new empty player build workspace; unrelated files are refused.")
    else:
        atomic_json(marker, identity)
    receipt_path = ordinary(output.with_name(output.name + ".build-receipt.json"))
    compatibility = compatibility_module()
    if output.exists() and receipt_path.is_file():
        receipt_sha = digest(receipt_path)
        compatibility.validate_public_build(output, receipt_path, receipt_sha256=receipt_sha)
        return receipt_path
    if output.exists():
        raise BuildError("The player output exists without a valid completed build receipt. Choose an empty output folder.")
    pins = json.loads(PINS_PATH.read_text())
    compatibility.verify_public_build_inputs(PUBLIC_BUILD_INPUTS, PINS_PATH)
    host, node_host = host_identity()
    artifacts = toolchain_artifacts(pins, host, node_host)
    downloads = ordinary(work / "downloads")
    downloads.mkdir(exist_ok=True)
    tools = ordinary(work / "tools")
    tools.mkdir(exist_ok=True)
    prefix = ordinary(tools / "rust")
    system_path = "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin"
    environment = isolated_environment(work, system_path)
    clang = shutil.which("clang", path=system_path)
    if not clang or not shutil.which("git", path=system_path):
        raise BuildError("Install Git and Clang development tools first (macOS: xcode-select --install; Ubuntu: git clang build-essential pkg-config libssl-dev).")
    targets = runner([clang, "--print-targets"], work, environment, capture=True)
    if "wasm32" not in targets:
        raise BuildError("The C/C++ compiler must support wasm32; install a current Clang development toolchain.")
    compiler = runner([clang, "--version"], work, environment, capture=True).splitlines()[0]
    environment.update(CC_wasm32_unknown_unknown=clang,
                       CXX_wasm32_unknown_unknown=shutil.which("clang++", path=system_path) or clang)
    locations = {}
    for entry in artifacts:
        print("Fetching pinned player tool: " + entry["name"], flush=True)
        archive = fetch(entry, downloads / entry["name"])
        algorithm = "sha256" if "sha256" in entry else "sha512"
        if digest(archive, algorithm) != entry[algorithm]:
            raise BuildError("Toolchain checksum mismatch: " + entry["name"])
        extracted = ordinary(tools / entry["name"].replace(".tar.xz", "").replace(".tar.gz", "").replace(".tgz", ""))
        if not extracted.exists():
            extraction = ordinary(tools / (extracted.name + ".extracting"))
            if extraction.exists():
                shutil.rmtree(extraction)
            unpacked = extract_archive(archive, extraction)
            os.replace(unpacked, extracted)
            extraction.rmdir()
        if entry["kind"] == "rust":
            installed = ordinary(extracted / ".farmvillage-installed")
            if not installed.exists():
                runner(["/bin/sh", str(extracted / "install.sh"), "--prefix=" + str(prefix), "--disable-ldconfig"], extracted, environment)
                installed.touch()
        else:
            locations[entry["kind"]] = extracted
    environment["PATH"] = os.pathsep.join((str(prefix / "bin"), str(locations["node"] / "bin"), str(locations["bindgen"]), system_path))
    java = locations["java"]
    if (java / "Contents/Home").is_dir():
        java = java / "Contents/Home"
    environment["JAVA_HOME"] = str(java)
    environment["PATH"] = str(java / "bin") + os.pathsep + environment["PATH"]
    source = ordinary(work / "source")
    if not source.exists():
        source.mkdir()
        runner(["git", "init", "--quiet"], source, environment)
        runner(["git", "remote", "add", "origin", "https://github.com/ruffle-rs/ruffle.git"], source, environment)
    ordinary(source / ".git")
    runner(["git", "remote", "set-url", "origin", "https://github.com/ruffle-rs/ruffle.git"], source, environment)
    runner(["git", "fetch", "--depth=1", "origin", COMMIT], source, environment)
    runner(["git", "reset", "--hard", COMMIT], source, environment)
    runner(["git", "clean", "-fdx"], source, environment)
    runner(["git", "submodule", "update", "--init", "--recursive", "--depth=1"], source, environment)
    actual_commit = runner(["git", "rev-parse", "HEAD"], source, environment, capture=True)
    if actual_commit != COMMIT:
        raise BuildError("Public source fetch did not produce the pinned commit.")
    submodules = runner(["git", "submodule", "status", "--recursive"], source, environment, capture=True)
    if any(line.startswith(("-", "+", "U")) for line in submodules.splitlines()):
        raise BuildError("A public source submodule does not match its pinned gitlink.")
    versions = {}
    commands = {"rust": [prefix / "bin/rustc", "--version"],
                "node": [locations["node"] / "bin/node", "--version"],
                "npm": [locations["node"] / "bin/node", locations["npm"] / "bin/npm-cli.js", "--version"],
                "wasm_bindgen": [locations["bindgen"] / "wasm-bindgen", "--version"]}
    for name, command in commands.items():
        versions[name] = runner(command, work, environment, capture=True)
    compatibility.verify_public_tool_versions(versions)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".player-build-", dir=output.parent))
    candidate = stage / "player"
    try:
        runner([sys.executable, "-I", "-B", PUBLIC_BUILD_INPUTS / "build-runtime.py", "--source", source,
                "--destination", candidate, "--node", locations["node"] / "bin/node",
                "--npm-cli", locations["npm"] / "bin/npm-cli.js", "--wasm-bindgen",
                locations["bindgen"] / "wasm-bindgen", "--source-build"], source, environment)
        files = {path.name: digest(path) for path in candidate.iterdir() if path.is_file()}
        receipt = {"schema": 1, "kind": "farmvillage-public-runtime-build-v1", "upstream_commit": COMMIT,
                   "runtime_id": RUNTIME_ID, "host": host, "compiler": compiler,
                   "tool_versions": versions, "source_inputs": compatibility.PUBLIC_SOURCE_INPUTS,
                   "source_state": "clean-pinned-checkout-plus-reviewed-gc-patch",
                   "submodules": submodules.splitlines(),
                   "artifacts": [{key: entry[key] for key in ("name", "url", "sha256", "sha512") if key in entry} for entry in artifacts],
                   "files": files, "gameplay_acceptance": False}
        temporary_receipt = stage / "build-receipt.json"
        atomic_json(temporary_receipt, receipt)
        compatibility.validate_public_build(candidate, temporary_receipt, receipt_sha256=digest(temporary_receipt))
        os.replace(candidate, output)
        os.replace(temporary_receipt, receipt_path)
    finally:
        shutil.rmtree(stage)
    return receipt_path


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    options = parser.parse_args(arguments)
    try:
        receipt = build_public_runtime(options.work, options.output)
        print(json.dumps({"receipt": str(receipt), "receipt_sha256": digest(receipt)}, sort_keys=True))
    except (BuildError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print("Player build paused: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
