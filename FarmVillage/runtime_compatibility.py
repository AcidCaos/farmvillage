"""Verify and atomically stage a reviewed local Ruffle distribution.

This module is shared by source and bundled launches and needs only the Python
standard library. No modified runtime is selected until ACTIVE_RELEASE is pinned
after native acceptance. The caller retains the existing profile lifecycle lock.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from types import MappingProxyType
from typing import Callable, Mapping, Optional
import uuid


MANIFEST_NAME = ".farmvillage-ruffle.json"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}\Z")
CheckCancelled = Optional[Callable[[], None]]


class RuntimeIntegrityError(ValueError):
    """A local runtime does not match its reviewed identity or complete files."""


@dataclass(frozen=True)
class RuntimeRelease:
    runtime_id: str
    upstream_version: str
    upstream_commit: str
    manifest_sha256: str

    def __post_init__(self):
        if (not all(isinstance(value, str) for value in (
                    self.runtime_id, self.upstream_version, self.upstream_commit, self.manifest_sha256))
                or not _IDENTIFIER.fullmatch(self.runtime_id)
                or not _IDENTIFIER.fullmatch(self.upstream_version)
                or not _COMMIT.fullmatch(self.upstream_commit)
                or not _SHA256.fullmatch(self.manifest_sha256)):
            raise ValueError("A runtime release requires a safe id and exact reviewed hashes.")


# Activation is deliberately separate from this reviewed verifier/installer.
ACTIVE_RELEASE: RuntimeRelease | None = RuntimeRelease(
    "0.7.1-farmvillage-gc1",
    "0.7.1",
    "89a7049965f3090e706265670df309a5128233ac",
    "a841dc7fc1729eab67afe67cf3418a4633a2de5e03ebd878e1cf6749387ddf03",
)

# A source-build receipt is integrity evidence, not a signature or gameplay pass.
# Installer state binds its generated manifest hash; the private default remains
# strict and cannot silently select a different or downloaded player.
PUBLIC_SOURCE_INPUTS = {
    "gc-pacing.patch": "502ad9492deb3b5904d1b09c535ec521345b86b17b8db16145de862046515d14",
    "Cargo.lock": "c63981977750d740c24a70fdd1582f9f4b40f9bb8bf18fd8ed2790e576628e0d",
    "package-lock.json": "fff432c1cd6a43c1b907dca1ebe438d38f28748368060cd1769bb9cb5bf05147",
    "version-seal.json": "e31f5d3d95f93dc508f2921263917950907ca616a16f63ba7fbb0a6656f4db5a",
    "build-runtime.py": "a761b283d051f78fe18c85e9a5cb09733d17dc65b4c2a5cf86b064d453154e04",
    "toolchain-pins.json": "80730d80f097224c84ac0bdb7c24115656f325be770eff8c9a56b55521411622",
}
PUBLIC_RECEIPT_KIND = "farmvillage-public-runtime-build-v1"
_HOSTS = {"aarch64-apple-darwin", "x86_64-apple-darwin",
          "aarch64-unknown-linux-gnu", "x86_64-unknown-linux-gnu"}


def verify_public_build_inputs(provenance: Path, toolchain_pins: Path) -> None:
    provenance = _directory(provenance)
    for name, expected in PUBLIC_SOURCE_INPUTS.items():
        path = toolchain_pins if name == "toolchain-pins.json" else _child(provenance, name)
        if path.is_symlink() or not path.is_file() or _file_digest(path, None) != expected:
            raise RuntimeIntegrityError("A public player build source input changed: " + name)


def verify_public_tool_versions(versions: dict) -> None:
    if (not isinstance(versions, dict) or set(versions) != {"rust", "node", "npm", "wasm_bindgen"}
            or not isinstance(versions.get("rust"), str)
            or not versions["rust"].startswith("rustc 1.99.1 ")
            or versions.get("node") != "v24.19.0"
            or versions.get("npm") != "11.0.0"
            or versions.get("wasm_bindgen") != "wasm-bindgen 0.2.127"):
        raise RuntimeIntegrityError("The public player build used unsupported toolchain versions.")


def _public_output_names(files: dict) -> None:
    if not isinstance(files, dict):
        raise RuntimeIntegrityError("The public player build has no output inventory.")
    required = {"LICENSE_APACHE", "LICENSE_MIT", "README.md", "package.json", "ruffle.js", "ruffle.js.map"}
    wasm = {name for name in files if isinstance(name, str) and re.fullmatch(r"[0-9a-f]{20}\.wasm", name)}
    chunks = {name for name in files if isinstance(name, str) and re.fullmatch(r"core\.ruffle\.[0-9a-f]{20}\.js", name)}
    expected = required | wasm | chunks | {name + ".map" for name in chunks}
    if len(wasm) != 2 or len(chunks) != 2 or len(files) != 12 or set(files) != expected:
        raise RuntimeIntegrityError("The public player requires all twelve dual-WASM distribution files.")
    for name, checksum in files.items():
        _relative(name)
        if not isinstance(checksum, str) or not _SHA256.fullmatch(checksum):
            raise RuntimeIntegrityError("A public player output hash is invalid.")


def _read_public_receipt(receipt_path: Path, receipt_sha256: str) -> dict:
    if not isinstance(receipt_sha256, str) or not _SHA256.fullmatch(receipt_sha256):
        raise RuntimeIntegrityError("An explicit SHA256 pin is required for the public build receipt.")
    if receipt_path.is_symlink() or not receipt_path.is_file() or receipt_path.stat().st_size > 1024 * 1024:
        raise RuntimeIntegrityError("The public build receipt is unavailable or exceeds its size limit.")
    raw = receipt_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != receipt_sha256:
        raise RuntimeIntegrityError("The public build receipt changed after installer verification.")
    try:
        receipt = json.loads(raw)
    except (ValueError, UnicodeError) as error:
        raise RuntimeIntegrityError("The public build receipt is invalid JSON.") from error
    active = _release(None)
    if (not isinstance(receipt, dict) or receipt.get("schema") != 1
            or receipt.get("kind") != PUBLIC_RECEIPT_KIND
            or receipt.get("runtime_id") != active.runtime_id
            or receipt.get("upstream_commit") != active.upstream_commit
            or receipt.get("source_inputs") != PUBLIC_SOURCE_INPUTS
            or receipt.get("source_state") != "clean-pinned-checkout-plus-reviewed-gc-patch"
            or receipt.get("host") not in _HOSTS
            or not isinstance(receipt.get("compiler"), str)
            or "clang" not in receipt["compiler"].lower()
            or receipt.get("gameplay_acceptance") is not False):
        raise RuntimeIntegrityError("The public player receipt does not match the reviewed source-build contract.")
    verify_public_tool_versions(receipt.get("tool_versions"))
    _public_output_names(receipt.get("files"))
    return receipt


def _verify_public_artifact_pins(receipt: dict, directory: Path) -> None:
    pins_path = directory / "provenance/toolchain-pins.json"
    if not pins_path.exists():
        pins_path = Path(__file__).absolute().parent.parent / "tools/public-ruffle-toolchains.json"
    if pins_path.is_symlink() or _file_digest(pins_path, None) != PUBLIC_SOURCE_INPUTS["toolchain-pins.json"]:
        raise RuntimeIntegrityError("The toolchain archive pins changed.")
    pins = json.loads(pins_path.read_text())
    host = receipt["host"]
    node_host = ("darwin" if "apple" in host else "linux") + ("-arm64" if host.startswith("aarch64") else "-x64")
    rust = pins["rustVersion"]
    expected = {f"{component}-{rust}-{host}.tar.xz": ("sha256", checksum)
                for component, checksum in pins["rust"][host].items()}
    expected[f"rust-src-{rust}.tar.xz"] = ("sha256", pins["rustSrc"])
    expected[f"rust-std-{rust}-wasm32-unknown-unknown.tar.xz"] = ("sha256", pins["rustWasm"])
    expected[f"node-v{pins['nodeVersion']}-{node_host}.tar.xz"] = ("sha256", pins["node"][node_host])
    bindgen_host = "x86_64-unknown-linux-musl" if host == "x86_64-unknown-linux-gnu" else host
    expected[f"wasm-bindgen-{pins['bindgenVersion']}-{bindgen_host}.tar.gz"] = ("sha256", pins["bindgen"][bindgen_host])
    cpu = "aarch64" if host.startswith("aarch64") else "x64"
    system = "mac" if "apple" in host else "linux"
    version, build = pins["javaVersion"].split("+")
    expected[f"OpenJDK17U-jdk_{cpu}_{system}_hotspot_{version}_{build}.tar.gz"] = ("sha256", pins["java"][node_host])
    expected[f"npm-{pins['npmVersion']}.tgz"] = ("sha512", base64.b64decode(pins["npmIntegrity"]).hex())
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != len(expected):
        raise RuntimeIntegrityError("The player receipt is missing a pinned toolchain archive.")
    actual = {}
    for entry in artifacts:
        if not isinstance(entry, dict) or entry.get("name") not in expected:
            raise RuntimeIntegrityError("The player receipt names an unreviewed toolchain archive.")
        name = entry["name"]
        algorithm, checksum = expected[name]
        if name in actual or entry.get(algorithm) != checksum:
            raise RuntimeIntegrityError("A player receipt toolchain archive hash changed.")
        actual[name] = checksum


def validate_public_build(directory: Path, receipt_path: Path, *, receipt_sha256: str) -> dict:
    """Check one completed local source build before the installer seals it."""
    directory = _directory(directory)
    receipt = _read_public_receipt(Path(receipt_path), receipt_sha256)
    _verify_public_artifact_pins(receipt, directory)
    if {path.name for path in directory.iterdir()} - {"provenance", MANIFEST_NAME} != set(receipt["files"]):
        raise RuntimeIntegrityError("The public player directory contains missing or unexpected output files.")
    for name, checksum in receipt["files"].items():
        if _file_digest(_child(directory, name), None) != checksum:
            raise RuntimeIntegrityError("A public player output does not match its build receipt: " + name)
    try:
        package = json.loads(_child(directory, "package.json").read_text())
    except (ValueError, UnicodeError) as error:
        raise RuntimeIntegrityError("The public player package metadata is invalid.") from error
    if package.get("version") != _release(None).runtime_id or package.get("upstreamVersion") != "0.7.1":
        raise RuntimeIntegrityError("The public player package version changed.")
    for name in receipt["files"]:
        if name.endswith(".wasm"):
            with _child(directory, name).open("rb") as stream:
                if stream.read(8) != b"\0asm\x01\0\0\0":
                    raise RuntimeIntegrityError("A public player module is not valid WebAssembly version 1.")
    return receipt


def prepare_public_runtime(payload: Path, receipt_path: Path, *, receipt_sha256: str) -> str:
    """Seal a checked source build; return its pin for the installer's state.

    The caller binds this returned pin to its resource-state/prepared bundle
    manifest. Runtime launch never discovers a pin from a receipt's own claim.
    No downloading or building occurs here.
    """
    selected = _release(None)
    directory = bundled_runtime(payload, selected)
    receipt = validate_public_build(directory, Path(receipt_path), receipt_sha256=receipt_sha256)
    # The recipe lives beside the installer tools, apart from the hard-pinned historical player directory.
    provenance_source = Path(__file__).absolute().parent.parent / "tools/public-ruffle-build"
    toolchain_pins = Path(__file__).absolute().parent.parent / "tools/public-ruffle-toolchains.json"
    verify_public_build_inputs(provenance_source, toolchain_pins)
    provenance = directory / "provenance"
    if provenance.exists():
        _directory(provenance)
        if {path.name for path in provenance.iterdir()} - (set(PUBLIC_SOURCE_INPUTS) | {"build-receipt.json"}):
            raise RuntimeIntegrityError("The public player contains unexpected provenance sidecars.")
    else:
        provenance.mkdir()
    for name in PUBLIC_SOURCE_INPUTS:
        source = toolchain_pins if name == "toolchain-pins.json" else provenance_source / name
        target = provenance / name
        if target.is_symlink():
            raise RuntimeIntegrityError("A public player provenance file is a symbolic link.")
        if source.absolute() != target.absolute():
            shutil.copyfile(source, target)
    target_receipt = provenance / "build-receipt.json"
    if target_receipt.is_symlink():
        raise RuntimeIntegrityError("A public player receipt is a symbolic link.")
    if Path(receipt_path).absolute() != target_receipt.absolute():
        shutil.copyfile(receipt_path, target_receipt)
    files = dict(receipt["files"])
    for path in provenance.iterdir():
        _child(directory, "provenance/" + path.name)
        files["provenance/" + path.name] = _file_digest(path, None)
    manifest = {"schema": 1, "runtime_id": selected.runtime_id,
                "version": selected.upstream_version, "upstream_commit": selected.upstream_commit,
                "kind": "installer-local-public-source-build-v1", "files": files,
                "build_receipt_sha256": receipt_sha256, "gameplay_acceptance": False}
    raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    pin = hashlib.sha256(raw).hexdigest()
    manifest_path = directory / MANIFEST_NAME
    if manifest_path.is_symlink():
        raise RuntimeIntegrityError("The public player manifest is a symbolic link.")
    manifest_path.write_bytes(raw)
    select_runtime_release(payload, prepared_pin_sha256=pin)
    return pin


def select_runtime_release(payload: Path, *, prepared_pin_sha256: str | None = None) -> RuntimeRelease:
    """Use the strict default, or an explicitly installer-bound source build."""
    active = _release(None)
    if prepared_pin_sha256 is None:
        return active
    if not isinstance(prepared_pin_sha256, str) or not _SHA256.fullmatch(prepared_pin_sha256):
        raise RuntimeIntegrityError("The prepared player manifest pin is invalid.")
    selected = RuntimeRelease(active.runtime_id, active.upstream_version, active.upstream_commit, prepared_pin_sha256)
    directory = bundled_runtime(payload, selected)
    manifest = _manifest(directory, selected)
    if manifest.get("kind") != "installer-local-public-source-build-v1" or manifest.get("gameplay_acceptance") is not False:
        raise RuntimeIntegrityError("The explicit player pin is not a prepared public source build.")
    provenance = _child(directory, "provenance", directory=True)
    verify_public_build_inputs(provenance, _child(provenance, "toolchain-pins.json"))
    receipt = validate_public_build(directory, _child(provenance, "build-receipt.json"),
                                    receipt_sha256=manifest.get("build_receipt_sha256"))
    expected = set(receipt["files"]) | {"provenance/" + name for name in (*PUBLIC_SOURCE_INPUTS, "build-receipt.json")}
    if set(manifest["files"]) != expected:
        raise RuntimeIntegrityError("The public player manifest contains missing or unexpected provenance files.")
    verify_runtime(directory, selected)
    return selected


@dataclass(frozen=True)
class VerifiedRuntime:
    directory: Path
    release: RuntimeRelease
    files: Mapping[str, str]


def _release(release: RuntimeRelease | None) -> RuntimeRelease:
    selected = release if release is not None else ACTIVE_RELEASE
    if selected is None:
        raise RuntimeIntegrityError("No reviewed compatibility runtime has been activated.")
    return selected


def _check(callback: CheckCancelled) -> None:
    if callback is not None:
        callback()


def _directory(path: Path) -> Path:
    path = Path(path).absolute()
    try:
        mode = path.lstat().st_mode
    except OSError as error:
        raise RuntimeIntegrityError(f"The runtime directory is unavailable: {path.name}") from error
    if not stat.S_ISDIR(mode) or stat.S_ISLNK(mode):
        raise RuntimeIntegrityError("Runtime directories must be ordinary directories, not links.")
    return path


def _relative(name: str) -> PurePosixPath:
    if not isinstance(name, str) or not name or "\\" in name or "\x00" in name:
        raise RuntimeIntegrityError("The runtime manifest contains an unsafe file name.")
    relative = PurePosixPath(name)
    if (not relative.parts or relative.is_absolute() or relative.as_posix() != name
            or any(part in ("", ".", "..") or ":" in part for part in relative.parts)):
        raise RuntimeIntegrityError("The runtime manifest contains an unsafe file name.")
    return relative


def _child(root: Path, name: str, *, directory: bool = False, missing: bool = False) -> Path:
    relative = _relative(name)
    current = root
    for index, part in enumerate(relative.parts):
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            if missing:
                return root / relative
            raise RuntimeIntegrityError(f"A reviewed runtime file is missing: {name}") from None
        if stat.S_ISLNK(mode):
            raise RuntimeIntegrityError("The runtime contains a symbolic link.")
        final = index == len(relative.parts) - 1
        expected_directory = not final or directory
        if expected_directory and not stat.S_ISDIR(mode):
            raise RuntimeIntegrityError("A runtime directory path is not a directory.")
        if not expected_directory and not stat.S_ISREG(mode):
            raise RuntimeIntegrityError("A runtime file is not an ordinary file.")
    return current


def _file_digest(path: Path, check_cancelled: CheckCancelled) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            _check(check_cancelled)
            digest.update(chunk)
    return digest.hexdigest()


def _manifest(directory: Path, release: RuntimeRelease) -> dict:
    manifest_file = _child(directory, MANIFEST_NAME)
    if manifest_file.stat().st_size > 1024 * 1024:
        raise RuntimeIntegrityError("The runtime manifest exceeds its expected size.")
    raw = manifest_file.read_bytes()
    if hashlib.sha256(raw).hexdigest() != release.manifest_sha256:
        raise RuntimeIntegrityError("The runtime manifest does not match its reviewed hash.")
    try:
        manifest = json.loads(raw)
    except (ValueError, UnicodeError) as error:
        raise RuntimeIntegrityError("The reviewed runtime manifest is invalid JSON.") from error
    if (not isinstance(manifest, dict) or manifest.get("schema") != 1
            or manifest.get("runtime_id") != release.runtime_id
            or manifest.get("version") != release.upstream_version
            or manifest.get("upstream_commit") != release.upstream_commit):
        raise RuntimeIntegrityError("The runtime manifest has an unsupported identity.")
    files = manifest.get("files")
    if (not isinstance(files, dict) or not files or "ruffle.js" not in files
            or not any(isinstance(name, str) and name.endswith(".wasm") for name in files)):
        raise RuntimeIntegrityError("The runtime manifest is missing its loader or WebAssembly.")
    for name, digest in files.items():
        _relative(name)
        if name == MANIFEST_NAME or not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise RuntimeIntegrityError("The runtime manifest has an invalid file hash.")
    return manifest


def verify_runtime(directory: Path, release: RuntimeRelease | None = None,
                   *, check_cancelled: CheckCancelled = None) -> VerifiedRuntime:
    """Verify a hard-pinned manifest and its exact complete file set."""
    _check(check_cancelled)
    selected = _release(release)
    directory = _directory(directory)
    manifest = _manifest(directory, selected)
    expected = set(manifest["files"]) | {MANIFEST_NAME}
    actual = set()
    for parent, directories, files in os.walk(directory, followlinks=False):
        _check(check_cancelled)
        parent = Path(parent)
        for name in directories:
            _child(directory, (parent / name).relative_to(directory).as_posix(), directory=True)
        for name in files:
            relative = (parent / name).relative_to(directory).as_posix()
            _child(directory, relative)
            actual.add(relative)
    if actual != expected:
        raise RuntimeIntegrityError("The runtime file set is incomplete or contains unreviewed files.")
    for name, digest in manifest["files"].items():
        if _file_digest(_child(directory, name), check_cancelled) != digest:
            raise RuntimeIntegrityError(f"A runtime file failed its reviewed hash: {name}")
    return VerifiedRuntime(directory, selected, MappingProxyType(dict(manifest["files"])))


def runtime_valid(directory: Path, release: RuntimeRelease | None = None) -> bool:
    try:
        verify_runtime(directory, release)
        return True
    except (OSError, RuntimeIntegrityError):
        return False


def read_resource(runtime: VerifiedRuntime, name: str) -> bytes:
    """Read once and verify exactly the bytes that a response will serve.

    A verified startup inventory is not a promise that mutable profile/source
    files stay unchanged. Hash the requested file without reopening it, so a
    replacement after verification cannot turn into a mixed runtime response.
    """
    _relative(name)
    if name not in runtime.files:
        raise RuntimeIntegrityError("The requested file is not a reviewed player resource.")
    try:
        contents = _child(_directory(runtime.directory), name).read_bytes()
    except OSError as error:
        raise RuntimeIntegrityError("The requested runtime file is unavailable.") from error
    if hashlib.sha256(contents).hexdigest() != runtime.files[name]:
        raise RuntimeIntegrityError("The requested runtime file changed after verification.")
    return contents


def bundled_runtime(payload: Path, release: RuntimeRelease | None = None) -> Path:
    """Locate the same reviewed runtime inside a source or staged payload."""
    selected = _release(release)
    payload = _directory(payload)
    return _child(payload, "ruffle_runtime/" + selected.runtime_id, directory=True)


def _remove_owned_directory(directory: Path) -> None:
    if directory.is_symlink():
        directory.unlink()
    elif directory.exists():
        shutil.rmtree(directory)


def _clean_stages(parent: Path, release: RuntimeRelease) -> None:
    # The profile lock excludes a live installer. Never follow links or remove
    # a prior-runtime quarantine, which may be the only copy after a failed
    # rollback. Only unpublished stages for this exact id are disposable.
    prefix = ".ruffle-stage-" + release.runtime_id + "-"
    for entry in parent.iterdir():
        if entry.name.startswith(prefix) and stat.S_ISDIR(entry.lstat().st_mode):
            shutil.rmtree(entry)


def install_runtime(payload: Path, data: Path, release: RuntimeRelease | None = None,
                    *, check_cancelled: CheckCancelled = None) -> Path:
    """Atomically install verified local bytes; preserve older runtime ids.

    The caller holds its normal profile lock. A valid installed copy is reused
    without network access. No interpreter, save, asset or other profile content
    is modified, and a failed replacement restores the previous directory.
    """
    selected = _release(release)
    data = _directory(data)
    parent = _child(data, "ruffle", directory=True, missing=True)
    parent.mkdir(exist_ok=True)
    parent = _child(data, "ruffle", directory=True)
    _clean_stages(parent, selected)
    destination = _child(parent, selected.runtime_id, directory=True, missing=True)
    _check(check_cancelled)
    try:
        verify_runtime(destination, selected, check_cancelled=check_cancelled)
        return destination
    except (OSError, RuntimeIntegrityError):
        pass
    source = verify_runtime(bundled_runtime(payload, selected), selected,
                            check_cancelled=check_cancelled)
    stage = Path(tempfile.mkdtemp(prefix=".ruffle-stage-" + selected.runtime_id + "-", dir=parent))
    previous: Path | None = None
    published = False
    try:
        for name in (*source.files, MANIFEST_NAME):
            _check(check_cancelled)
            target = stage / _relative(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(_child(source.directory, name), target)
        verify_runtime(stage, selected, check_cancelled=check_cancelled)
        _check(check_cancelled)
        # A prior invalid copy is quarantined only after the complete new copy
        # has verified; the official upstream directory has a different id.
        if destination.exists():
            previous = parent / (".ruffle-previous-" + selected.runtime_id + "-" + uuid.uuid4().hex)
            os.replace(destination, previous)
        try:
            os.replace(stage, destination)
            published = True
        except BaseException:
            if previous is not None:
                os.replace(previous, destination)
                previous = None
            raise
    finally:
        _remove_owned_directory(stage)
        if published and previous is not None:
            # Successful publication is not undone by an obsolete-copy cleanup
            # failure. The live verified runtime remains the authoritative copy.
            try:
                _remove_owned_directory(previous)
            except OSError:
                pass
    return destination


def public_path(release: RuntimeRelease | None = None) -> str:
    return "/ruffle/" + _release(release).runtime_id + "/"


def resource_name(path: str, release: RuntimeRelease | None = None) -> str:
    """Resolve only the active version prefix; never accept an old mixed URL."""
    selected = _release(release)
    prefix = selected.runtime_id + "/"
    if not isinstance(path, str) or not path.startswith(prefix):
        raise RuntimeIntegrityError("The requested Ruffle runtime id is unsupported.")
    relative = path[len(prefix):]
    _relative(relative)
    if relative == MANIFEST_NAME:
        raise RuntimeIntegrityError("The runtime manifest is not a player resource.")
    return relative


def main(arguments=None) -> None:
    """Build-time verification only; this command never installs a runtime."""
    parser = argparse.ArgumentParser(description="Verify the reviewed local Ruffle package.")
    parser.add_argument("--payload", required=True, type=Path)
    parser.add_argument("--prepared-runtime-pin-sha256", help="Manifest hash bound to the installer's prepared resource state")
    options = parser.parse_args(arguments)
    release = select_runtime_release(options.payload, prepared_pin_sha256=options.prepared_runtime_pin_sha256)
    verified = verify_runtime(bundled_runtime(options.payload, release), release)
    print(f"Verified local Ruffle {verified.release.runtime_id}: {len(verified.files)} reviewed files.")


if __name__ == "__main__":
    main()
