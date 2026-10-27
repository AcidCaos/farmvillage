#!/usr/bin/env python3
"""Package a committed Deco repair as a bounded, source-only community overlay."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile


PROJECT = Path(__file__).resolve().parents[2]
SOURCE_FILES = (
    "ugc.py", "feature_options.py", "construction.py", "commands.py", "storage.py", "server.py", "player.py",
    "client_compatibility.py", "macOS/Tests/test_game_client_patch.py",
    "macOS/Tests/test_ugc.py", "macOS/Tests/test_ugc_wire.py",
    "macOS/Tests/test_construction.py", "macOS/Tests/test_construction_wire.py",
    "macOS/Tests/test_feature_options.py", "macOS/Tests/test_persistence.py",
    "macOS/Tests/test_packaging.py",
    "macOS/Documentation/ClientPatches/README.md",
    "macOS/Documentation/ClientPatches/deco-client-byte-review.json",
    "macOS/Scripts/prepare-portable-release.py",
    "portable/bifrost-update/build-bifrost-update.py",
    "portable/bifrost-update/test_bifrost_update.py",
    "portable/bifrost-update/package-community-source.py",
    "portable/bifrost-update/test_community_source.py",
    "macOS/Documentation/COMMUNITY_DECO_SOURCE.md",
)
CONTRACT = "macOS/Documentation/COMMUNITY_DECO_SOURCE.md"


def git(*arguments):
    return subprocess.run(["git", *arguments], cwd=PROJECT, check=True,
                          capture_output=True).stdout


def digest(data):
    return hashlib.sha256(data).hexdigest()


def contents(commit):
    revision = git("rev-parse", "--verify", "--end-of-options", commit + "^{commit}").decode().strip()
    parent = git("rev-parse", "--verify", revision + "^").decode().strip()
    selected = (*SOURCE_FILES, "LICENSE")
    # The explicit list is the archive boundary; neither untracked local files
    # nor unrelated committed assets or data can enter this source overlay.
    source = {name: git("cat-file", "blob", revision + ":" + name) for name in selected}
    files = {"source/" + name: data for name, data in source.items()}
    files["LICENSE"] = source["LICENSE"]
    files["README.md"] = source[CONTRACT]
    files["changes.patch"] = git("diff", "--no-ext-diff", "--no-textconv", parent, revision, "--", *selected)
    manifest = {
        "schema": 1, "kind": "community-deco-source-overlay", "commit": revision, "base_commit": parent,
        "scope": "Explicitly selected source, tests, source contract and existing repository license only",
        "excluded": ["game assets", "client binaries", "catalog data", "saves", "credentials", "local data"],
        "files": {name: {"sha256": digest(data), "bytes": len(data)} for name, data in sorted(files.items())},
    }
    return files, manifest


def package(commit, output):
    output = Path(output)
    sidecar = output.with_name(output.name + ".sha256")
    manifest_path = output.with_name(output.name + ".manifest.json")
    if any(path.exists() or path.is_symlink() for path in (output, sidecar, manifest_path)):
        raise ValueError("Choose a new output filename; existing source deliveries are preserved.")
    files, manifest = contents(commit)
    manifest_raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    files["SOURCE_MANIFEST.json"] = manifest_raw
    prefix = "community-deco-source/"
    # All inputs are a small fixed set of text files, so holding the archive in
    # memory avoids leaving partial archives on a failed source read or encode.
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=buffer, mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            for name, data in sorted(files.items()):
                entry = tarfile.TarInfo(prefix + name)
                entry.mode, entry.size = 0o644, len(data)
                archive.addfile(entry, io.BytesIO(data))
    payload = buffer.getvalue()
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        if set(archive.getnames()) != {prefix + name for name in files}:
            raise ValueError("The source overlay inventory differs from the selected text files.")
        for entry in archive:
            if not entry.isfile() or archive.extractfile(entry).read() != files[entry.name[len(prefix):]]:
                raise ValueError("The source overlay failed verification.")
    output.write_bytes(payload)
    manifest_path.write_bytes(manifest_raw)
    sidecar.write_text(digest(payload) + "  " + output.name + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", default="HEAD", help="The committed repair to package; default HEAD.")
    parser.add_argument("--output", required=True, type=Path, help="A new .tar.gz source overlay filename.")
    arguments = parser.parse_args()
    manifest = package(arguments.commit, arguments.output)
    print(f"Packaged {len(manifest['files'])} source files from {manifest['commit']} into {arguments.output}")


if __name__ == "__main__":
    main()
