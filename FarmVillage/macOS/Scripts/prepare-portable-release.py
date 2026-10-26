#!/usr/bin/env python3
"""Prepare or verify an offline portable-play handoff; never run a backend."""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tarfile
import tempfile
import types
import unicodedata
import zlib


RUNTIME_ID = "0.7.1-farmvillage-gc1"
RUNTIME_MANIFEST_SHA = "a841dc7fc1729eab67afe67cf3418a4633a2de5e03ebd878e1cf6749387ddf03"
A4_BODY_SHA = "edae6c3be651b9d9e4082d68267dd829cc8a8e620213824faee4d7caa4630b1c"
MEADOWS_BODY_SHA = "8f34e1533a4949e411bf75706e3010b74a3e805f1d7f02f10bc799295baa4066"
CLIENT_BODY_SHA = "bd7386cf087f27d57b96c1d46d1629e3b562a3487de51aa2b5ee5adfb0a69d9e"
CLIENT_FILE_SHA = "476fbf7cee3df47fe97ab4d3aefbfdcd14c92b71e5e9d7b8dc2e82ef5ea2156a"
WAVE2_MODULES = ('client_compatibility.py', 'cove_client.py', 'meadows_client.py', 'client_graphics.py', 'meadows_rules.py', 'meadows_storage.py', 'england_animals.py', 'england_shipping.py', 'cove_rules.py', 'cove_port.py', 'cove_shipping.py', 'cellar_progression.py', 'rainforest_features.py', 'rainforest_rules.py', 'placement_receipts.py', 'inventory_sales.py', 'commands.py', 'server.py', 'storage.py', 'templates/play.html', 'templates/ruffle.html')
MEADOWS_MODULES = WAVE2_MODULES

SOURCE_CLIENT_SHA = "1edea7cbecefcb1e1233da207164942f0088a83b87afc9254850f5fcde5034ae"
SOURCE_ITEMS_SHA = "14987fd4c07f9de35ff5092aeab58584802fd7fbeca1131ad1a5e3eee381a4d7"
ALLOWED_DIRECTORIES = {"GodBarn", "assethash", "embeds", "patched", "templates", "villages", "warc_extractor", "xml", "ruffle_runtime"}
HELPERS = ("server_runner.py", "native_assets.py", "native_paths.py", "native_launcher.py")
CLIENT_REVIEWS = ("README.md", "provenance.json", "market-performance-byte-recipe.json",
                  "MEADOWS_SCOPED_CLIENT_REVIEW.json", "GRAPHICS_CACHE_CLIENT_REVIEW.json",
                  "WAVE2_COMBINED_REGIONAL_CLIENT_REVIEW.json",
                  "deco-client-byte-review.json", "COTTAGE_INVITATIONS_CLIENT_BYTE_REVIEW_2026-10-24.json", "QUEST_REWARD_CLOSE_BYTE_REVIEW_2026-10-24.json",
                  "IMAGE_ROW_LINEAR_BYTE_REVIEW_2026-10-24.json",
                  "INVENTORY_TAB_ART_BYTE_REVIEW_2026-10-24.json",
                  "MARKETSTALL_EXPANSION_BYTE_REVIEW_2026-10-24.json",
                  "WIDGET_STORAGE_VISIBILITY_BYTE_REVIEW_2026-10-24.json",
                  "THEMED_BASIC_PRESENTATION_REVIEW_2026-10-24.json",
                  "THEMED_MARKET_CONFIG_REVIEW_2026-10-24.json",
                  "THEMED_DUAL_PRICE_REVIEW_2026-10-24.json",
                  "PAID_FLOWER_CLIENT_PROJECTION_REVIEW_2026-10-24.json",
                  "scratch-coin-byte-review.json",
                  "empty-world-byte-review.json", "cottage-graphics-byte-review.json", "cottage-upgrade-visibility-byte-review.json", "turbo-purchase-refusal-byte-review.json", "storage-upgrade-refusal-byte-review.json",
                  "FarmGameSettingsManager.parseItemsBatch.pcode", "FarmGameSettingsManager.getFarmItemsArrayByType.pcode",
                  "FarmGameUtil.synchronizedDateToNumber.pcode", "FarmGameUtil.synchronizedDateTimeToNumber.pcode",
                  "SoundManager.getSoundObject.original.as", "audio-identity-review.json")
CHECKPOINTS = ("HANDOFF.md", "encyclopedia.py", "progression_tools.py", "scripts/prepare_encyclopedia.py",
               "scripts/prepare_progression.py", "data/historical-prizes.json")


def digest(contents):
    return hashlib.sha256(contents).hexdigest()


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def safe_name(value):
    path = PurePosixPath(value)
    if (not value or not path.parts or path.is_absolute() or path.as_posix() != value
            or "\\" in value or any(part in (".", "..") or ":" in part for part in path.parts)):
        raise ValueError("Unsafe archive member name.")
    return path


def ordinary_files(root):
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Release inputs must be ordinary directories.")
    for parent, directories, files in os.walk(root, followlinks=False):
        parent = Path(parent)
        for name in directories:
            if not stat.S_ISDIR((parent / name).lstat().st_mode):
                raise ValueError("Release inputs cannot contain directory links.")
        for name in files:
            path = parent / name
            if not stat.S_ISREG(path.lstat().st_mode):
                raise ValueError("Release inputs cannot contain links or special files.")
            yield path


def measure_assets(root):
    count = total = 0
    for path in ordinary_files(root):
        count += 1
        total += path.stat().st_size
    return {"schema": 1, "role": "External preserved original asset archive; excluded from the release tar",
            "file_count": count, "logical_bytes": total,
            "measured_utc": datetime.now(timezone.utc).isoformat(),
            "method": "Read-only filesystem metadata scan; asset contents were not rehashed or copied."}


def load_runtime_helper(path, name="portable_release_runtime_verifier"):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    # Executing this stdlib-only helper avoids bytecode writes into the accepted
    # application bundle. It verifies bytes; it never installs or starts them.
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


def mastery_definition_policy(payload):
    """Describe the staged policy roster without claiming a decoded AMF count."""
    source = payload / "mastery_signs.py"
    if source.is_symlink() or not source.is_file():
        raise ValueError("Mastery policy must be an ordinary staged source file.")
    module = load_runtime_helper(source, "portable_release_mastery_policy")
    rosters = {}
    for name in ("PRESERVED_GIFTS", "GLEN_GIFTS", "DEFINITION_GIFTS"):
        value = getattr(module, name, None)
        if (not isinstance(value, frozenset)
                or any(not isinstance(pair, tuple) or len(pair) != 2
                       or any(not isinstance(part, str) or not part for part in pair)
                       for pair in value)):
            raise ValueError("Mastery policy requires frozen nonempty name/code pairs: " + name)
        if len({gift for gift, _code in value}) != len(value):
            raise ValueError("Mastery policy contains conflicting gift owners: " + name)
        rosters[name] = value
    preserved, glen, definitions = (rosters[name] for name in
                                   ("PRESERVED_GIFTS", "GLEN_GIFTS", "DEFINITION_GIFTS"))
    if not definitions or preserved & glen or definitions != preserved | glen:
        raise ValueError("Mastery definition policy must be the disjoint preserved/Glen union.")
    return {
        "source_sha256": digest(source.read_bytes()),
        "preserved_pairs": len(preserved), "glen_pairs": len(glen),
        "eligible_pairs": len(definitions),
        "scope": "Pinned policy roster only; actual derived AMF rows are not measured by the stdlib sealer.",
    }


def literal_assignment(source, name):
    tree = ast.parse(source.read_text())
    node = next(node for node in ast.walk(tree) if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == name for target in node.targets))
    return ast.literal_eval(node.value)


def meadows_payload_policy(project, payload, game_contents):
    """Bind the staged client and required routing to the selected source.

    Payload fingerprints alone do not prove a self-consistent tree includes
    the modules needed by its scoped controls. Reject missing or stale source
    before invoking the reviewed standard-library byte transformers.
    """
    staged_tool = payload.parent / "WrapperRuntime/patch-game-client.py"
    source_tool = project / "macOS/Scripts/patch-game-client.py"
    if any(path.is_symlink() or not path.is_file() for path in (staged_tool, source_tool)):
        raise ValueError("The Meadows package is missing its ordinary client staging tool.")
    if staged_tool.read_bytes() != source_tool.read_bytes():
        raise ValueError("The staged Meadows client staging tool differs from selected source.")
    sources = {}
    for name in MEADOWS_MODULES:
        staged, source = payload / name, project / name
        if any(path.is_symlink() or not path.is_file() for path in (staged, source)):
            raise ValueError("The Meadows package is missing an ordinary required module: " + name)
        if staged.read_bytes() != source.read_bytes():
            raise ValueError("The staged Meadows module differs from selected source: " + name)
        sources[name] = digest(staged.read_bytes())
    if literal_assignment(payload / "meadows_client.py", "PATCHED_BODY_SHA256") != MEADOWS_BODY_SHA:
        raise ValueError("The historical Meadows module body pin disagrees.")
    if (literal_assignment(payload / "client_graphics.py", "BASE_BODY_SHA256") != MEADOWS_BODY_SHA
            or literal_assignment(payload / "client_graphics.py", "PATCHED_BODY_SHA256") != CLIENT_BODY_SHA):
        raise ValueError("The graphics module and portable client body pins disagree.")
    original = project / "embeds/Flash/v855097-855094/FarmGame.swf"
    if original.is_symlink() or not original.is_file() or digest(original.read_bytes()) != SOURCE_CLIENT_SHA:
        raise ValueError("The preserved original game client changed.")
    compatibility = load_runtime_helper(payload / "client_compatibility.py", "portable_compatibility_recipe")
    meadows = load_runtime_helper(payload / "meadows_client.py", "portable_meadows_recipe")
    graphics = load_runtime_helper(payload / "client_graphics.py", "portable_graphics_recipe")
    expected = graphics.patch_client_bytes(meadows.patch_client_bytes(compatibility.patch_client_bytes(original.read_bytes())))
    if (game_contents != expected or digest(game_contents) != CLIENT_FILE_SHA
            or digest(zlib.decompress(game_contents[8:])) != CLIENT_BODY_SHA):
        raise ValueError("The staged client differs from the complete served client composition.")
    return {"worlds": ["farm", "england", "meadows", "fisherman", "rainforest"], "required_source_sha256": sources,
            "staging_tool_sha256": digest(staged_tool.read_bytes()),
            "scope": "Scoped original paid storage and shipping controls; free/social growth and other worlds' controls retain their existing refusals."}


def device_acceptance(identity, historical_available=True):
    """Keep old native evidence distinct from validation of the current bytes."""
    current = identity.get("current_validation")
    if current is None:
        current = {"scope": "Current-payload device acceptance was not recorded in this identity."}
    return {
        "current_payload": current,
        "historical_native_evidence": {
            "available": True,
            "mac_native_wasm_peak": "Approximately 3.548 GB (accepted Mac native measurement)",
            "record": "Provenance/StableOrchard-native-verification.json",
            "scope": "Preserved prior-release evidence; this is not a measurement or acceptance of the current payload.",
        } if historical_available else {
            "available": False,
            "record": None,
            "scope": "Historical native verification was not supplied. No native acceptance is inferred from this package.",
        },
        "physical_ipad": "Not tested",
        "physical_iphone": "Not tested",
    }


def historical_native_record(project, explicit=None, *, omit=False):
    """Historical provenance is optional; current payload seals are mandatory.

    A clean checkout need not retain an old ignored build directory. Explicit
    historical inputs still fail closed when missing or linked. Absence is
    recorded in the manifest instead of manufacturing an acceptance record.
    """
    if omit:
        if explicit is not None:
            raise ValueError("Historical native verification cannot be both selected and omitted.")
        return None
    path = (Path(explicit) if explicit is not None else
            project / "macOS/.build/BarnActionsNativeValidation/verification.json")
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("Historical native verification must be an ordinary file.")
    if not path.is_file():
        if explicit is not None:
            raise ValueError("The selected historical native verification file is missing.")
        return None
    return path


def untabbed_index(payload):
    """Require the classifications used by the current Not in Market tab."""
    index = payload / "GodBarn/data/untabbed.json"
    if index.is_symlink() or not index.is_file():
        raise ValueError("The accepted payload must include GodBarn/data/untabbed.json; rebuild the companion bundle.")
    value = json.loads(index.read_text())
    if not isinstance(value, dict) or value.get("schema") != 1 or not isinstance(value.get("items"), dict):
        raise ValueError("GodBarn/data/untabbed.json must be a schema-1 item index.")
    return value


def verify_archive(archive):
    with tarfile.open(archive, "r:gz") as stream:
        members = stream.getmembers()
        names = [member.name for member in members]
        if len(names) != len(set(names)) or not members:
            raise ValueError("The archive has duplicate or missing members.")
        prefixes = {safe_name(name).parts[0] for name in names}
        if len(prefixes) != 1 or any(not member.isfile() for member in members):
            raise ValueError("The archive must contain one regular-file-only release tree.")
        prefix = prefixes.pop() + "/"
        manifest = json.loads(stream.extractfile(prefix + "manifest.json").read())
        manifest_raw = json_bytes(manifest)
        expected = set(manifest["files"]) | {"manifest.json", "SHA256SUMS"}
        if {name[len(prefix):] for name in names} != expected:
            raise ValueError("Archive file inventory differs from its manifest.")
        expected_sums = dict(manifest["files"])
        expected_sums["manifest.json"] = {"sha256": digest(manifest_raw), "bytes": len(manifest_raw)}
        for name, metadata in expected_sums.items():
            safe_name(name)
            contents = stream.extractfile(prefix + name).read()
            if len(contents) != metadata["bytes"] or digest(contents) != metadata["sha256"]:
                raise ValueError("Archive member failed verification: " + name)
        sums = "".join(metadata["sha256"] + "  " + name + "\n" for name, metadata in sorted(expected_sums.items())).encode()
        if stream.extractfile(prefix + "SHA256SUMS").read() != sums:
            raise ValueError("The checksum inventory is inconsistent.")
        return manifest


def prepare(arguments):
    project = arguments.project.resolve()
    companion = project.parent / "GodBarn"
    app = arguments.app.resolve()
    identity = json.loads(arguments.identity.read_text())
    accepted = next((entry for entry in identity["apps"] if Path(entry["path"]).resolve() == app), None)
    if identity.get("status") != "PASS" or accepted is None:
        raise ValueError("Select an application recorded in the accepted delivery identity.")
    resources = app / "Contents/Resources"
    payload = resources / "Runtime"
    historical_native = historical_native_record(
        project, getattr(arguments, "historical_native_verification", None),
        omit=getattr(arguments, "omit_historical_native_verification", False))
    untabbed = untabbed_index(payload)
    files = {}
    payload_records = {}
    case_names = {}

    def include(name, source):
        safe_name(name)
        if name in files:
            raise ValueError("Duplicate release member: " + name)
        if isinstance(source, Path) and (source.is_symlink() or not source.is_file()):
            raise ValueError("Release members must be ordinary files: " + name)
        key = unicodedata.normalize("NFC", name).casefold()
        if key in case_names:
            raise ValueError("Packaged paths collide when case folded: " + name)
        case_names[key] = name
        files[name] = source

    for path in ordinary_files(payload):
        relative = path.relative_to(payload)
        if ("__pycache__" in relative.parts or path.name == ".DS_Store"
                or (len(relative.parts) > 1 and relative.parts[0] not in ALLOWED_DIRECTORIES)):
            raise ValueError("Unexpected private/build content in accepted Runtime: " + relative.as_posix())
        contents = path.read_bytes()
        payload_records[relative.as_posix()] = {"sha256": digest(contents), "bytes": len(contents)}
        include("Runtime/" + relative.as_posix(), path)
    marker = (payload / ".payload-version").read_text().strip()
    lines = [metadata["sha256"] + "  ./" + name + "\n" for name, metadata in payload_records.items() if name != ".payload-version"]
    fingerprint = digest("".join(sorted(lines)).encode())
    if marker != accepted["payloadVersion"] or fingerprint != marker:
        raise ValueError("The accepted Runtime payload fingerprint does not match.")
    helper = load_runtime_helper(payload / "runtime_compatibility.py")
    selected = helper.ACTIVE_RELEASE
    if selected.runtime_id != RUNTIME_ID or selected.manifest_sha256 != RUNTIME_MANIFEST_SHA:
        raise ValueError("The accepted runtime is not the reviewed gc1 release.")
    verified = helper.verify_runtime(helper.bundled_runtime(payload))
    if len(verified.files) != 21:
        raise ValueError("The sealed runtime inventory is incomplete.")
    game = payload / "embeds/Flash/v855097-855094/FarmGame.swf"
    game_contents = game.read_bytes()
    if (digest(game_contents) != accepted["clientSHA256"] or digest(game_contents) != CLIENT_FILE_SHA
            or digest(zlib.decompress(game_contents[8:])) != CLIENT_BODY_SHA):
        raise ValueError("The accepted client is not the reviewed current compatibility body.")
    meadows_policy = meadows_payload_policy(project, payload, game_contents)
    source_game = project / "embeds/Flash/v855097-855094/FarmGame.swf"
    if digest(source_game.read_bytes()) != SOURCE_CLIENT_SHA:
        raise ValueError("The preserved original game client changed.")
    catalog = payload / "xml/gz/v855038/items_opt.amf"
    if digest(catalog.read_bytes()) != SOURCE_ITEMS_SHA:
        raise ValueError("The preserved complete item catalog changed.")
    if "fvPackedItem" in (payload / "client_catalog.py").read_text():
        raise ValueError("Experimental catalog packing is not an accepted portable release.")
    for name in HELPERS:
        include("BackendHost/" + name, resources / "WrapperRuntime" / name)
    include("Tools/patch-game-client.py", resources / "WrapperRuntime/patch-game-client.py")
    include("Tools/prepare-portable-release.py", Path(__file__).resolve())
    include("THIRD_PARTY.md", resources / "THIRD_PARTY.md")
    include("PORTABLE_HANDOFF.md", companion / "portable_release_handoff.md")
    include("Provenance/portable_play_plan.md", companion / "portable_play_plan.md")
    include("Provenance/for_2009_me.md", companion / "for_2009_me.md")
    include("Provenance/VALIDATION.md", project / "macOS/Documentation/VALIDATION.md")
    if historical_native is not None:
        include("Provenance/StableOrchard-native-verification.json", historical_native)
    include("Provenance/Original/FarmGame.swf", source_game)
    for name in CLIENT_REVIEWS:
        include("Provenance/ClientPatches/" + name, project / "macOS/Documentation/ClientPatches" / name)
    preserved_checkpoints = []
    for name in CHECKPOINTS:
        source = companion / name
        if source.is_file():
            include("Provenance/GodBarnPlanningCheckpoint/" + name, source)
            preserved_checkpoints.append(name)
    sanitized_identity = {key: value for key, value in identity.items() if key != "apps"}
    sanitized_identity["apps"] = [{key: value for key, value in entry.items() if key != "path"} for entry in identity["apps"]]
    include("Provenance/accepted-delivery-identity.json", json_bytes(sanitized_identity))
    asset_inventory = json.loads(arguments.asset_inventory.read_text()) if arguments.asset_inventory else measure_assets(arguments.assets_root.resolve())
    if not isinstance(asset_inventory.get("file_count"), int) or not isinstance(asset_inventory.get("logical_bytes"), int):
        raise ValueError("External asset inventory requires exact count and logical bytes.")
    include("external-assets.json", json_bytes(asset_inventory))
    metadata = {}
    for name, source in sorted(files.items()):
        contents = source.read_bytes() if isinstance(source, Path) else source
        metadata[name] = {"sha256": digest(contents), "bytes": len(contents)}
    powers = literal_assignment(payload / "GodBarn/engine.py", "schemas")
    farming_module = payload / "barn_actions.py"
    if farming_module.is_file():
        powers.update(literal_assignment(farming_module, "OPERATION_FIELDS"))
    encyclopedia_file = payload / "GodBarn/data/encyclopedia.json.gz"
    if not encyclopedia_file.is_file():
        raise ValueError("The final accepted payload must include the completed encyclopedia metadata.")
    encyclopedia = json.loads(gzip.decompress(encyclopedia_file.read_bytes()))
    progression = json.loads((payload / "GodBarn/data/progression.json").read_text())
    manifest = {
        "schema": 1, "kind": "portable-play-preparation", "deployment_status": "Not deployed; no remote/mobile acceptance claimed",
        "accepted_payload_version": marker, "accepted_architectures": accepted["architectures"],
        "runtime": {"id": RUNTIME_ID, "manifest_sha256": RUNTIME_MANIFEST_SHA, "sealed_files": len(verified.files)},
        "client": {"sha256": digest(game_contents), "body_sha256": CLIENT_BODY_SHA, "original_sha256": SOURCE_CLIENT_SHA,
                   "historical_a4_body_sha256": A4_BODY_SHA,
                   "historical_meadows_body_sha256": MEADOWS_BODY_SHA,
                   "graphics_cache_completion": {"module": "client_graphics.py", "method_id": 23400,
                       "scope": "Recheck synchronous cached image completion; original asynchronous path and all gameplay policy preserved"},
                   "graphics_tab_child_input": {"module": "client_graphics.py", "method_id": 4367,
                       "scope": "Exact existing FarmTabButton child-input contract; original parent enabled state preserved"},
                   "cove_port_dialog_admission": {"module": "client_graphics.py", "method_id": 22256,
                       "scope": "Current owned stable valid nonbusy Port opens its unchanged original material dialog; other clicks retain original code"},
                   "storage_dropdown_mask": {"module": "client_graphics.py", "method_id": 30984,
                       "scope": "Only farmDropDown_mc with an existing DisplayObject mask_mc keeps that authored mask visible; depth, geometry, input flags and callbacks preserved"},
                   "meadows_scoped_controls": meadows_policy,
                   "policy": "Reviewed Market/image allocation and tab routing, empty-farm/cottage rendering, supported cottage upgrades, quest Close acknowledgement, scoped Meadows paid-storage/shipping controls, synchronous cached-image completion, exact FarmTabButton child input, scoped original Cove Port dialog admission, original Storage mask pointer admission, and retained gates for unsupported VIP/Turbo/social-storage/stall invitations; exact byte reviews accompany this payload"},
        "catalog": {"source_sha256": SOURCE_ITEMS_SHA, "records": 111206,
                    "derived_mastery_definition_policy": mastery_definition_policy(payload),
                    "policy": "Immutable ordinary zlib/AMF3 source plus reviewed expired-offer, heritage-price, derived-mastery, paid-flower, themed-land and themed-Market client projections; original records and archives remain unchanged"},
        "god_barn": {"supported_operation_types": sorted(powers), "persistent_snapshots": "<data>/god-barn/snapshots",
                     "untabbed_items": len(untabbed["items"]),
                     "encyclopedia_items": len(encyclopedia["items"]), "historical_shelves": len(encyclopedia["shelves"]),
                     "matched_historical_prizes": sum(len(shelf["items"]) for shelf in encyclopedia["shelves"]),
                     "ribbon_definitions": len(progression["ribbons"]), "mastery_tracks": len(progression["masteryItems"]),
                     "planning_checkpoint_files": preserved_checkpoints,
                     "standalone_farming": False, "live_farming": farming_module.is_file()},
        "backend": {"processes": 1, "data_variable": "FARMVILLAGE_DATA_DIR",
                    "host_helpers": "Existing owned-loopback implementation; remote trusted-origin/auth/handoff work remains required"},
        "external_assets": asset_inventory, "packaged_casefold_collisions": 0,
        "device_acceptance": device_acceptance(identity, historical_native is not None),
        "excluded": ["live saves", "snapshots", "credentials", "venv", "extracted original assets", "cache", "tmp", "build products"],
        "files": metadata,
    }
    manifest_raw = json_bytes(manifest)
    files["manifest.json"] = manifest_raw
    sums = dict(metadata, **{"manifest.json": {"sha256": digest(manifest_raw), "bytes": len(manifest_raw)}})
    files["SHA256SUMS"] = "".join(value["sha256"] + "  " + name + "\n" for name, value in sorted(sums.items())).encode()
    output = arguments.output.absolute()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError("Choose a new output file; existing releases are never overwritten.")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".portable-stage-", suffix=".tar.gz", dir=output.parent)
    temporary = Path(temporary_name)
    prefix = "farmvillage-portable-preparation-" + marker[:12]
    try:
        with os.fdopen(descriptor, "wb") as raw:
            with gzip.GzipFile(filename="", fileobj=raw, mode="wb", compresslevel=6, mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as stream:
                    for name, source in sorted(files.items()):
                        contents = source.read_bytes() if isinstance(source, Path) else source
                        entry = tarfile.TarInfo(prefix + "/" + name)
                        entry.size, entry.mode, entry.mtime = len(contents), 0o644, 0
                        entry.uid = entry.gid = 0
                        entry.uname = entry.gname = ""
                        stream.addfile(entry, io.BytesIO(contents))
        verify_archive(temporary)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    Path(str(output) + ".manifest.json").write_bytes(manifest_raw)
    archive_sha = digest(output.read_bytes())
    Path(str(output) + ".sha256").write_text(archive_sha + "  " + output.name + "\n")
    return {"archive": str(output), "sha256": archive_sha, "bytes": output.stat().st_size,
            "files": len(files), "payload_version": marker, "external_assets": asset_inventory}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--app", type=Path)
    parser.add_argument("--identity", type=Path)
    historical = parser.add_mutually_exclusive_group()
    historical.add_argument("--historical-native-verification", type=Path,
                        help="Optional preserved historical native record; absence never establishes native acceptance.")
    historical.add_argument("--omit-historical-native-verification", action="store_true",
                            help="Do not adopt historical records from an old local build directory.")
    parser.add_argument("--output", type=Path)
    assets = parser.add_mutually_exclusive_group()
    assets.add_argument("--assets-root", type=Path)
    assets.add_argument("--asset-inventory", type=Path)
    arguments = parser.parse_args()
    if arguments.verify:
        manifest = verify_archive(arguments.verify)
        print(json.dumps({"status": "PASS", "payload_version": manifest["accepted_payload_version"], "files": len(manifest["files"])}, indent=2))
        return
    if not all((arguments.app, arguments.identity, arguments.output, arguments.assets_root or arguments.asset_inventory)):
        parser.error("Preparation requires --app, --identity, --output and an external asset inventory input.")
    print(json.dumps(prepare(arguments), indent=2))


if __name__ == "__main__":
    main()
