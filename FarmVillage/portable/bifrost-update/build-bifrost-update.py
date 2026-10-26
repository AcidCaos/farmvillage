#!/usr/bin/env python3
"""Build a complete Bifrost LAN update folder from the current working tree.

The folder holds two verified archives plus a Mac-side helper and instructions:

* farmvillage-portable-preparation-<payload>.tar.gz: the game server bundle
  (Runtime, BackendHost, provenance), produced by the same staging script the
  Xcode build uses (macOS/Scripts/bundle-runtime.sh) and then sealed by
  macOS/Scripts/prepare-portable-release.py.
* farmvillage-lan-host.tar.gz: the small hosting folder. Its start/install
  scripts point at the new bundle, and activate-release.sh unpacks the bundle
  beside the previous release on Bifrost.

This script only reads the working tree and writes into the chosen output
folder and a temporary work folder. It never contacts Bifrost, installs
anything, or reads farm saves. Rerun it whenever the sources change.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import types

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
WORKSPACE = PROJECT.parent
PREVIOUS_RELEASE = "farmvillage-portable-preparation-1acf91b47487"
DEFAULT_REFERENCE = WORKSPACE / "Bifrost Game Files" / (PREVIOUS_RELEASE + "-final.tar.gz")
DEFAULT_OUTPUT = WORKSPACE / "Bifrost LAN Update Candidate"
PROTECTED_OUTPUTS = {WORKSPACE / "Bifrost LAN Update", WORKSPACE / "Bifrost Game Files",
                     WORKSPACE / "Bifrost Fresh Start"}
DEBUG_APP = PROJECT / "macOS/.build/DerivedData/Build/Products/Debug/FarmVillage.app"
PREPARE_SCRIPT = PROJECT / "macOS/Scripts/prepare-portable-release.py"
BUNDLE_SCRIPT = PROJECT / "macOS/Scripts/bundle-runtime.sh"
HISTORICAL_NATIVE = "Provenance/StableOrchard-native-verification.json"
HOSTING_SOURCES = {
    "server_runner.py": PROJECT / "portable/Linux/server_runner.py",
    "start-server.sh": PROJECT / "portable/Linux/start-server.sh",
    "install-service.sh": PROJECT / "portable/Linux/install-service.sh",
    "diagnose-saves.py": PROJECT / "portable/Linux/diagnose-saves.py",
    "neighborhood_host.py": PROJECT / "portable/Linux/neighborhood_host.py",
    "preloader_timing.py": PROJECT / "portable/Linux/preloader_timing.py",
    "install-fresh-world.py": PROJECT / "portable/Linux/install-fresh-world.py",
    "activate-release.sh": HERE / "activate-release.sh",
    "GodBarn/integration.py": WORKSPACE / "GodBarn/integration.py",
}
# Hosting scripts that name the game release folder; each must name it once.
RELEASE_POINTERS = ("start-server.sh", "install-service.sh")
DEFAULT_VALIDATION_TEXT = (
    "Current source staged and archived offline; payload files, archive inventory and checksums verified. "
    "Packaging does not establish browser gameplay, native Mac, iPad, iPhone or Bifrost runtime acceptance."
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            result.update(chunk)
    return result.hexdigest()


def log(message: str) -> None:
    print("[bifrost-update] " + message, flush=True)


def read_reference(reference: Path) -> dict[str, bytes]:
    """Read verified inventory and optional genuine history without extraction.

    The retained release need not use the server's old environment release ID.
    Current SWF/runtime/index seals are checked when building the NEW payload.
    """
    sidecar = reference.with_name(reference.name + ".sha256")
    for path in (reference, sidecar):
        if path.is_symlink() or not path.is_file():
            raise ValueError("Reference archive and sidecar must be regular files.")
    recorded = sidecar.read_text().split()
    if (len(recorded) != 2 or not re.fullmatch(r"[0-9a-f]{64}", recorded[0])
            or recorded[1] != reference.name):
        raise ValueError("The reference sidecar must name this archive and its SHA-256.")
    if file_sha256(reference) != recorded[0]:
        raise ValueError("The previous release archive does not match its .sha256 sidecar.")
    prepare = load_prepare()
    # Verify every regular member, manifest, path and checksum before reuse.
    manifest = prepare.verify_archive(reference)
    result = {}
    with tarfile.open(reference, "r:gz") as stream:
        root = stream.getmembers()[0].name.split("/", 1)[0]
        if not re.fullmatch(r"farmvillage-portable-preparation-[0-9a-f]{12}", root):
            raise ValueError("The reference must contain one safe portable release root.")
        if "external-assets.json" not in manifest["files"]:
            raise ValueError("The reference has no verified external-assets.json inventory.")
        for name in ("external-assets.json", HISTORICAL_NATIVE):
            if name in manifest["files"]:
                result[name] = stream.extractfile(root + "/" + name).read()
    inventory = json.loads(result["external-assets.json"])
    if not isinstance(inventory, dict) or any(
            type(inventory.get(key)) is not int or inventory[key] < 0
            for key in ("file_count", "logical_bytes")):
        raise ValueError("The reference external-assets.json inventory is invalid.")
    if inventory != manifest.get("external_assets"):
        raise ValueError("The reference asset inventory differs from its manifest.")
    return result


def stage_payload(work: Path) -> Path:
    """Run the Xcode resource-staging script outside Xcode into a scratch app."""
    resources = "FarmVillage.app/Contents/Resources"
    environment = dict(os.environ, TARGET_BUILD_DIR=str(work / "stage"),
                       UNLOCALIZED_RESOURCES_FOLDER_PATH=resources, COPYFILE_DISABLE="1")
    subprocess.run(["/bin/bash", str(BUNDLE_SCRIPT)], check=True, env=environment)
    return work / "stage" / "FarmVillage.app"


def check_payload_matches_tree(payload: Path) -> int:
    """Match server/templates and every staged GodBarn resource to the source."""
    pairs = [(path, payload / path.name) for path in PROJECT.glob("*.py")]
    pairs += [(path, payload / "templates" / path.relative_to(PROJECT / "templates"))
              for path in (PROJECT / "templates").rglob("*")
              if path.is_file() and path.name != ".DS_Store" and "__pycache__" not in path.parts]
    for source, staged in pairs:
        if not staged.is_file() or staged.read_bytes() != source.read_bytes():
            raise ValueError("Staged payload differs from the working tree: " + str(source))
    # Match bundle-runtime.sh's interpreter too: gzip framing can differ across
    # Python versions. Verify helpers, UI, index and all companion metadata.
    companion = WORKSPACE / "GodBarn"
    with tempfile.TemporaryDirectory(prefix="bifrost-barn-parity-") as temporary:
        expected = Path(temporary) / "GodBarn"
        subprocess.run(["/usr/bin/python3", "-I", "-B", str(companion / "scripts/bundle_companion.py"),
                        str(companion), str(expected)], check=True)
        actual = payload / "GodBarn"
        expected_files = {path.relative_to(expected) for path in expected.rglob("*") if path.is_file()}
        actual_files = {path.relative_to(actual) for path in actual.rglob("*") if path.is_file()}
        if any(path.is_symlink() for path in actual.rglob("*")) or actual_files != expected_files:
            raise ValueError("Staged GodBarn inventory differs from the working tree.")
        for name in sorted(expected_files):
            if (expected / name).read_bytes() != (actual / name).read_bytes():
                raise ValueError("Staged GodBarn resource differs from the working tree: " + str(name))
    return len(pairs) + len(expected_files)


def load_prepare() -> types.ModuleType:
    """Load the unchanged sealer without bytecode writes or source substitution."""
    module = types.ModuleType("farmvillage_prepare_portable_release")
    module.__file__ = str(PREPARE_SCRIPT)
    sys.modules[module.__name__] = module
    exec(compile(PREPARE_SCRIPT.read_bytes(), str(PREPARE_SCRIPT), "exec"), module.__dict__)
    return module


def build_bundle(work: Path, reference: dict[str, bytes],
                 validation_text: str = DEFAULT_VALIDATION_TEXT) -> tuple[Path, str]:
    log("Staging the game payload with macOS/Scripts/bundle-runtime.sh ...")
    app = stage_payload(work)
    payload = app / "Contents/Resources/Runtime"
    marker = (payload / ".payload-version").read_text().strip()
    log(f"Payload fingerprint {marker}; {check_payload_matches_tree(payload)} source files match the tree.")
    debug_marker = DEBUG_APP / "Contents/Resources/Runtime/.payload-version"
    if debug_marker.is_file():
        same = debug_marker.read_text().strip() == marker
        log("Mac Debug app payload " + ("matches this bundle exactly." if same else
            "DIFFERS from this bundle (sources changed after the last Mac build)."))
    evidence = None
    if HISTORICAL_NATIVE in reference:
        evidence = work / "StableOrchard-native-verification.json"
        evidence.write_bytes(reference[HISTORICAL_NATIVE])
    inventory = work / "external-assets.json"
    inventory.write_bytes(reference["external-assets.json"])
    game = payload / "embeds/Flash/v855097-855094/FarmGame.swf"
    identity = {
        "status": "PASS",
        "runtime": "0.7.1-farmvillage-gc1",
        "manifestSHA256": "a841dc7fc1729eab67afe67cf3418a4633a2de5e03ebd878e1cf6749387ddf03",
        "originalClientSHA256": "1edea7cbecefcb1e1233da207164942f0088a83b87afc9254850f5fcde5034ae",
        "source": "FarmVillage working tree staged by macOS/Scripts/bundle-runtime.sh for the Bifrost LAN update",
        "acceptance": validation_text,
        "current_validation": {
            "scope": "Current source and archive; see acceptance for the checks actually performed.",
            "mac_native": "Not run for this payload",
            "bifrost": "Not run for this payload",
            "physical_ipad": "Not run for this payload",
            "physical_iphone": "Not run for this payload",
        },
        "historical_evidence": (
            "StableOrchard-native-verification.json is preserved prior-release evidence; "
            "it does not validate the current payload." if evidence is not None else
            "No historical native record was supplied by the reference archive. "
            "The manifest records any genuine optional sealer input; no native acceptance is inferred."
        ),
        "apps": [{"path": str(app), "payloadVersion": marker, "clientSHA256": file_sha256(game),
                  "architectures": "portable Python (Linux LAN host)"}],
    }
    identity_path = work / "identity.json"
    identity_path.write_text(json.dumps(identity, indent=2) + "\n")
    prepare = load_prepare()
    name = "farmvillage-portable-preparation-" + marker[:12]
    output = work / "out" / (name + ".tar.gz")
    log("Sealing the bundle with prepare-portable-release.py ...")
    result = prepare.prepare(argparse.Namespace(project=PROJECT, app=app, identity=identity_path,
                                                output=output, assets_root=None, asset_inventory=inventory,
                                                historical_native_verification=evidence,
                                                omit_historical_native_verification=evidence is None))
    manifest = prepare.verify_archive(output)
    if manifest["accepted_payload_version"] != marker or "Runtime/GodBarn/catalog_tools.py" not in manifest["files"]:
        raise ValueError("The sealed bundle is missing the expected payload or catalog_tools.py.")
    log(f"Bundle {output.name}: {result['files']} files, {result['bytes']:,} bytes, sha256 {result['sha256']}")
    return output, name


def build_hosting(work: Path, release_name: str) -> Path:
    contents = {}
    for name, path in HOSTING_SOURCES.items():
        data = path.read_bytes()
        if name in RELEASE_POINTERS:
            old = PREVIOUS_RELEASE.encode()
            if data.count(old) != 1:
                raise ValueError(f"{name} must name {PREVIOUS_RELEASE} exactly once.")
            data = data.replace(old, release_name.encode())
        contents[name] = data
    contents["SHA256SUMS"] = "".join(f"{sha256(data)}  {name}\n"
                                     for name, data in sorted(contents.items())).encode()
    archive = work / "out" / "farmvillage-lan-host.tar.gz"
    with archive.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as output:
                for name, data in sorted(contents.items()):
                    member = tarfile.TarInfo("hosting/" + name)
                    member.mode = 0o755 if name.endswith(".sh") else 0o644
                    member.size = len(data)
                    output.addfile(member, io.BytesIO(data))
    with tarfile.open(archive, "r:gz") as check:
        if set(check.getnames()) != {"hosting/" + name for name in contents}:
            raise ValueError("Unexpected hosting update inventory.")
        for name, data in contents.items():
            member = check.getmember("hosting/" + name)
            if not member.isfile() or check.extractfile(member).read() != data:
                raise ValueError("Hosting update failed verification: " + name)
    digest = file_sha256(archive)
    archive.with_name(archive.name + ".sha256").write_text(f"{digest}  {archive.name}\n")
    log(f"Hosting package {archive.name}: {len(contents)} files, sha256 {digest}")
    return archive


def readme(bundle: Path, folder: Path, unpacked_bytes: int,
           validation_text: str = DEFAULT_VALIDATION_TEXT) -> str:
    helper = folder / "manage-bifrost.sh"
    megabytes = -(-bundle.stat().st_size // 1_000_000)
    # Uploaded bundle + unpacked release + copied Python environment and backup headroom.
    needed = megabytes + -(-unpacked_bytes // 1_000_000) + 200
    return f"""FarmVillage on Bifrost: current-source update candidate

WHAT THIS UPDATE CONTAINS
This candidate packages current FarmVillage and sibling GodBarn source for
Bifrost (http://192.168.50.80:5501/), including farming, owned-world travel and
the current Not in Market index. Feature scope and remaining limits come from
the source documentation and exact validation record below.
MECHANICS_RELEASE.md is retained background, not current runtime acceptance.
The installer preserves your farms, God Barn history, artwork and browser
password.

VALIDATION STATUS
{validation_text}
This payload has not been run in the Mac native app, on a physical iPad or
iPhone, or on Bifrost by this builder. Packaging alone does not establish a
browser gameplay pass; retain any graphics/gameplay limits in that record.
The bundle's accepted-delivery identity records these checks. Optional native
verification from a previous release is historical evidence only; absence
does not establish native acceptance. NativeRuffle resources/app qualification
remain separate from this browser-server update.

This folder is prepared only. Installation requires the owner's separate choice.

NEVER RUN --fresh-start. It wipes your farm progress. This update does not use
it, and this folder's helper refuses it.

STEP 1: CHECK THE SAVES
In a MAC terminal tab, not the SSH/Ubuntu tab, run this single line:
bash "{helper}" --check-saves

It uploads the small hosting archive/sidecar and lists farms, snapshots and
free disk space. It does not start or stop the active game or edit farm files;
uploading the archive does write to the release directory.
SSH may ask for your Ubuntu login password; typed
characters stay hidden. Check that your farms are listed and that Bifrost has
at least {needed} MB free. If anything looks wrong, stop and paste the output
into the chat.

STEP 2: INSTALL THE UPDATE
Before installing, keep a dated copy of /home/farmvillage/farmville-test/hosting/
and the current managed farmvillage.service unit. The installer backs up farm
data but replaces hosting scripts without saving their old release pointers.
Confirm the old release {PREVIOUS_RELEASE}/.venv still exists: activation
copies that environment to the new release. Stop if it is missing.

Close every game tab on the Mac, and close the FarmVillage app on the iPad
(swipe it away from the app switcher). If the server is running in an Ubuntu
terminal instead of in the background, press Control+C there once and wait for
the normal prompt. Then, in a MAC terminal tab, run this single line:
bash "{helper}" --install

This copies the new game files (about {megabytes} MB) and checks their checksum
on Bifrost before anything changes. The new version is unpacked beside the old
one, and the old one is kept. The background service is then stopped, saves
and God Barn history are backed up to
/home/farmvillage/farmville-test/backups/pre-service-*/farm-data.tar.gz
and the service starts again on the new version. SSH may ask for your Ubuntu
login password and Ubuntu may ask for your sudo password.

Wait for "You can close this terminal", then open http://192.168.50.80:5501/ .
The first start rebuilds the quest list, so the first load may take a little
longer than usual. If the install stops with an error, nothing has been
deleted: paste the output into the chat.

AFTER THE UPDATE
The packaged source retains automatic farm backups under
/home/farmvillage/farmville-test/data/saves/.backups/ .
Do not run the older God Barn deployment script (deploy_bifrost_barn.sh) after
this update; it still points at the old game version. Report missing God Barn
pictures rather than applying an old package to a new release.

IF SOMETHING GOES WRONG
Keep the output and inspect the service log. The old release and save backup
remain. A code rollback needs the saved hosting scripts/release pointers and
managed unit. Do not restore old farm backups over newer progress without a
specific recovery decision. Never use --fresh-start for this update.

USEFUL UBUNTU COMMANDS (ONE AT A TIME)
systemctl --user status farmvillage.service --no-pager
journalctl --user -u farmvillage.service -n 50 --no-pager
systemctl --user restart farmvillage.service
"""


def publish(work: Path, output: Path, bundle: Path, release_name: str,
            validation_text: str = DEFAULT_VALIDATION_TEXT) -> None:
    output.mkdir(exist_ok=False)
    unpacked = 0
    with tarfile.open(bundle, "r:gz") as stream:
        unpacked = sum(member.size for member in stream.getmembers())
    names = [bundle.name, bundle.name + ".sha256", bundle.name + ".manifest.json",
             "farmvillage-lan-host.tar.gz", "farmvillage-lan-host.tar.gz.sha256"]
    for name in names:
        temporary = output / (name + ".partial")
        shutil.copyfile(work / "out" / name, temporary)
        temporary.replace(output / name)
    helper = output / "manage-bifrost.sh"
    shutil.copyfile(HERE / "manage-bifrost.sh", helper)
    helper.chmod(0o755)
    (output / "READ ME.txt").write_text(readme(bundle, output, unpacked, validation_text))
    # The installation README explicitly requires reviewing this scope record.
    # Keep it beside the candidate instead of leaving a dangling instruction.
    shutil.copyfile(PROJECT / "macOS/Documentation/MECHANICS_RELEASE.md", output / "MECHANICS_RELEASE.md")
    for name in names:
        if name.endswith(".tar.gz"):
            recorded = (output / (name + ".sha256")).read_text().split()
            if recorded != [file_sha256(output / name), name]:
                raise ValueError("Published archive does not match its sidecar: " + name)
    log("Published into " + str(output))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reference-archive", type=Path, default=DEFAULT_REFERENCE,
                        help="A verified sealed release supplying asset inventory and optional historical evidence.")
    parser.add_argument("--work-dir", type=Path, help="Parent for the temporary work folder.")
    parser.add_argument("--validation-text", default=DEFAULT_VALIDATION_TEXT,
                        help="Exact checks performed for this payload, recorded in its provenance identity.")
    arguments = parser.parse_args()
    output = arguments.output.absolute()
    if output in PROTECTED_OUTPUTS:
        raise SystemExit("Refusing to write into an existing delivery folder: " + str(output))
    if output.exists() or output.is_symlink():
        raise SystemExit("Choose a new output folder; existing update candidates are never overwritten.")
    if not re.fullmatch(r"[^\n\r\"$`\\]+", str(output)):
        raise SystemExit("Choose an output path without quotes, dollar signs, backslashes or newlines.")
    reference = read_reference(arguments.reference_archive)
    with tempfile.TemporaryDirectory(prefix="bifrost-update-", dir=arguments.work_dir) as temporary:
        work = Path(temporary)
        (work / "out").mkdir()
        bundle, release_name = build_bundle(work, reference, arguments.validation_text)
        build_hosting(work, release_name)
        publish(work, output, bundle, release_name, arguments.validation_text)


if __name__ == "__main__":
    main()
