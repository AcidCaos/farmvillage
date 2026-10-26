#!/usr/bin/env python3
"""Create a deterministic, asset-free source review candidate from saved files.

This snapshots a fixed allowlist, including local uncommitted work. It does not
commit, publish, install, read saves, or include proprietary catalog/client data.
"""
from __future__ import annotations

import argparse
import difflib
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

PROJECT = Path(__file__).resolve().parents[2]
MODULES = (
    "assets", "avatar", "barn_actions", "breeding", "bundle", "client_catalog",
    "client_compatibility", "client_england", "commands", "constants", "construction", "crafting",
    "creative_worlds", "cove_rules", "engine", "england_progression", "feature_availability", "feature_options", "game_settings", "gifting", "items", "market",
    "hallow_rules", "hallow_world_rules", "hawaii_rules", "instant_growth", "minigames", "peaceful", "persistence", "pets", "player", "progression",
    "quests", "runtime_compatibility", "server", "storage", "ugc", "version",
    "world_travel",
)
TESTS = (
    "persistence", "minion_backups", "barn_actions", "breeding", "breeding_wire",
    "construction", "construction_wire", "core_actions", "crafting", "cottage_lifecycle", "cottage_recipes", "cottage_client_graphics", "cottage_client_upgrades", "feature_availability",
    "equipment_wire", "gifts_storage", "levels", "level_progression_1_100", "market", "market_availability", "market_dates",
    "minion_commands_equipment", "minion_commands_pricing",
    "minion_player_storage_options", "minion_round3_commands",
    "minion_round3_quests", "peaceful", "progression", "quest_actions", "motd_wire",
    "world_travel", "world_travel_review", "pets", "minigames", "client_catalog",
    "game_client_patch", "creative_worlds", "additional_farms_http", "client_england", "england_progression",
    "cove_rules", "cove_travel", "enabled_farms_regression",
    "cove_cellar", "inventory_capacity", "hallow_rules", "hallow_world_rules", "hawaii_rules",
    "instantgrow_worlds", "shared_farming_loop",
)
SOURCE_FILES = (
    *(name + ".py" for name in MODULES),
    *("macOS/Tests/test_" + name + ".py" for name in TESTS),
    "requirements.txt", "LICENSE",
    "templates/play.html", "templates/ruffle.html",
    "templates/login.html", "templates/new.html", "templates/farms.html", "templates/css/farm-gate.css",
    "macOS/Scripts/run-other-mechanics-regressions.py",
    "macOS/Scripts/patch-game-client.py",
    "macOS/Scripts/prepare-portable-release.py",
    "macOS/Documentation/ClientPatches/README.md",
    "macOS/Documentation/ClientPatches/scratch-coin-byte-review.json",
    "macOS/Documentation/ClientPatches/empty-world-byte-review.json",
    "macOS/Documentation/ClientPatches/cottage-graphics-byte-review.json",
    "macOS/Documentation/ClientPatches/cottage-upgrade-visibility-byte-review.json",
    "macOS/Documentation/OTHER_MECHANICS_STATUS.md",
    "macOS/Documentation/COTTAGE_RECOVERY_2026-10-23.md",
    "macOS/Documentation/COTTAGE_LEVEL_ONE_RECIPES_2026-10-23.md",
    "macOS/Documentation/FEATURE_AVAILABILITY.md",
    "macOS/Documentation/FEATURE_INVITATION_INVENTORY.csv",
    "macOS/Documentation/LEVEL_PROGRESSION_AUDIT.md",
    "macOS/Documentation/PLAYABLE_BASE_FIXES_2026-10-23.md",
    "macOS/Documentation/MECHANICS_RELEASE.md",
    "macOS/Documentation/LAMB_RAISING_STATUS.md",
    "macOS/Documentation/MINIGAMES_STATUS.md",
    "macOS/Documentation/PETS_STATUS.md",
    "macOS/Documentation/WORLD_TRAVEL_STATUS.md",
    "macOS/Documentation/WORLD_RECOVERY_INVENTORY.md",
    "macOS/Documentation/Worlds/README.md",
    "macOS/Documentation/Worlds/STATUS.json",
    "macOS/Documentation/Worlds/INVENTORY_EVIDENCE.json",
    "macOS/Documentation/Worlds/refresh_index.py",
    "macOS/Documentation/Worlds/NEXT_WORLD_RULES.md",
    "macOS/Documentation/Worlds/HAUNTED_HOLLOW_RULES.md",
    "macOS/Documentation/Worlds/HAUNTED_HOLLOW_TERRAIN.md",
    "macOS/Documentation/Worlds/HAWAII_RULES.md",
    "portable/bifrost-update/package-mechanics-source.py",
    "portable/bifrost-update/test_mechanics_source.py",
    "portable/Linux/install-service.sh",
    "portable/Linux/test_install_service.py",
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args, check=True):
    return subprocess.run(["git", *args], cwd=PROJECT, check=check, capture_output=True)


def contents():
    base = git("rev-parse", "HEAD").stdout.decode().strip()
    source = {}
    patch = []
    for name in SOURCE_FILES:
        path = PROJECT / name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(PROJECT.resolve()):
            raise ValueError("Missing or linked source: " + name)
        raw = path.read_bytes()
        current = raw.decode("utf-8")
        source["source/" + name] = raw
        prior = git("cat-file", "blob", base + ":" + name, check=False)
        if prior.returncode and git("ls-tree", base, "--", name).stdout:
            raise ValueError("Cannot read base source: " + name)
        before = prior.stdout.decode("utf-8") if prior.returncode == 0 else ""
        lines = difflib.unified_diff(before.splitlines(keepends=True), current.splitlines(keepends=True),
                                    fromfile="a/" + name if prior.returncode == 0 else "/dev/null",
                                    tofile="b/" + name)
        # difflib leaves a missing final newline implicit, which otherwise
        # concatenates removed/added lines into an invalid or inexact patch.
        for line in lines:
            patch.append(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n")
    source["changes.patch"] = "".join(patch).encode()
    source["LICENSE"] = source["source/LICENSE"]
    source["README.md"] = source["source/macOS/Documentation/MECHANICS_RELEASE.md"]
    manifest = {
        "schema": 1, "kind": "mechanics-source-review-candidate",
        "base_commit": base, "source_state": "saved working-tree snapshot; may include uncommitted changes",
        "standalone": False, "deployment_performed": False,
        "launcher_assets": "Art and fonts remain excluded. The local portable bundle supplies templates/img/farm-gate/; HTML/CSS alone are not a standalone launcher delivery.",
        "excludes": ["game assets", "SWF binaries", "catalogs", "saves", "credentials", "logs"],
        "files": {name: {"sha256": sha(raw), "bytes": len(raw)} for name, raw in sorted(source.items())},
    }
    return source, manifest


def package(output):
    output = Path(output)
    sidecar = output.with_name(output.name + ".sha256")
    manifest_path = output.with_name(output.name + ".manifest.json")
    for path in (output, sidecar, manifest_path):
        if path.exists() or path.is_symlink():
            raise ValueError("Existing delivery is preserved: " + str(path))
    files, manifest = contents()
    manifest_raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    files["SOURCE_MANIFEST.json"] = manifest_raw
    buffer = io.BytesIO()
    prefix = "farmvillage-mechanics-source/"
    with gzip.GzipFile(filename="", fileobj=buffer, mode="wb", mtime=0) as stream:
        with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            for name, raw in sorted(files.items()):
                entry = tarfile.TarInfo(prefix + name)
                entry.mode, entry.size = 0o644, len(raw)
                archive.addfile(entry, io.BytesIO(raw))
    payload = buffer.getvalue()
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        if len(archive.getmembers()) != len(files) or set(archive.getnames()) != {prefix + name for name in files}:
            raise ValueError("Source archive inventory differs.")
        for member in archive:
            if not member.isfile() or archive.extractfile(member).read() != files[member.name[len(prefix):]]:
                raise ValueError("Source archive verification failed.")
    output.write_bytes(payload)
    sidecar.write_text(sha(payload) + "  " + output.name + "\n")
    manifest_path.write_bytes(manifest_raw)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = package(args.output)
    print("Verified %d source review files: %s" % (len(manifest["files"]), args.output))
