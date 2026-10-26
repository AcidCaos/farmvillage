#!/usr/bin/env python3
"""Stage only God Barn's application resources into the native game payload."""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile


def _unlinked(path: Path) -> Path:
    path = path.expanduser().absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("Companion input/output paths must not contain symbolic links: " + str(path))
    return path


def bundle_companion(source: Path, destination: Path, *, resources: Path | None = None) -> None:
    """Publish a portable runtime atomically into a new or empty directory."""
    source = _unlinked(Path(source))
    resources = _unlinked(Path(resources)) if resources is not None else source
    destination = _unlinked(Path(destination))
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError("God Barn must be staged into a fresh empty directory.")
    for original in (source, resources):
        if destination == original or destination in original.parents or original in destination.parents:
            raise ValueError("Companion output must remain separate from source and resources.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".god-barn-bundle-", dir=destination.parent))
    try:
        _bundle_into(source, staging, resources=resources)
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging)
        raise


def _bundle_into(source: Path, destination: Path, *, resources: Path) -> None:
    source = source.resolve()
    resources = resources.resolve()
    destination = destination.absolute()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("God Barn must be staged into a fresh empty directory.")
    # Every module here is imported at runtime, so a missing one must fail the build.
    modules = ("__init__.py", "engine.py", "integration.py", "seasonal.py", "encyclopedia.py",
               "progression_tools.py", "catalog_tools.py", "helper_tools.py")
    required = (*modules, "static/index.html", "static/app.js", "static/style.css", "static/farmville.css",
                "static/touch.js",
                "data/rules.json", "data/catalog.json", "data/provenance.json", "data/untabbed.json")
    for name in required:
        root = resources if name.startswith("data/") else source
        path = root / name
        _unlinked(path)
        if not path.is_file() or path.is_symlink():
            raise ValueError("Missing regular companion resource: " + name)
    destination.mkdir(parents=True, exist_ok=True)
    for name in modules:
        shutil.copyfile(source / name, destination / name)
    # Thumbnails already exist in the user's extracted game asset archive. Copy
    # only interface art and fonts; map the large thumbnail collection by hash.
    static_roots = [source] if resources == source else [source, resources]
    for static_root in static_roots:
        for path in (static_root / "static").rglob("*"):
            relative = path.relative_to(static_root)
            if path.is_symlink():
                raise ValueError("Companion resources must not contain symbolic links.")
            if not path.is_file() or "__pycache__" in relative.parts or path.name == ".DS_Store":
                continue
            if static_root == source and resources != source and path.suffix not in {".html", ".js", ".css"}:
                continue
            if relative.parts[:3] == ("static", "assets", "items"):
                continue
            if "contact-sheet" in path.name:
                continue
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    data = destination / "data"
    data.mkdir(exist_ok=True)
    shutil.copyfile(resources / "data/rules.json", data / "rules.json")
    shutil.copyfile(resources / "data/untabbed.json", data / "untabbed.json")
    if (resources / "data/archive-provenance.json").is_file():
        shutil.copyfile(resources / "data/archive-provenance.json", data / "archive-provenance.json")
    for name in ("progression.json", "historical-prizes.json", "catalog-audit.json", "helpers.json"):
        metadata = resources / "data" / name
        _unlinked(metadata)
        if metadata.is_symlink():
            raise ValueError("Companion metadata must not be symbolic links.")
        if metadata.is_file():
            shutil.copyfile(metadata, data / name)
    encyclopedia = resources / "data/encyclopedia.json"
    _unlinked(encyclopedia)
    if encyclopedia.is_symlink():
        raise ValueError("Companion metadata must not be symbolic links.")
    if encyclopedia.is_file():
        (data / "encyclopedia.json.gz").write_bytes(gzip.compress(encyclopedia.read_bytes(), compresslevel=6, mtime=0))
    # Deterministic gzip keeps repeat builds and payload fingerprints stable.
    (data / "catalog.json.gz").write_bytes(gzip.compress((resources / "data/catalog.json").read_bytes(), compresslevel=6, mtime=0))
    provenance = json.loads((resources / "data/provenance.json").read_text())
    original_assets = Path(provenance.get("sourceDirectory", ".")) / "LocalData/assets"
    mapping = {}
    for item in provenance.get("assets", []):
        copied = item.get("path", "")
        if not copied.startswith("static/assets/items/"):
            continue
        if ".." in PurePosixPath(copied).parts or "\\" in copied:
            raise ValueError("Invalid copied thumbnail path.")
        try:
            relative = (Path(item["assetRelativePath"]) if "assetRelativePath" in item
                        else Path(item["originalPath"]).relative_to(original_assets))
        except (KeyError, ValueError) as error:
            raise ValueError("A catalog image escapes the original asset archive.") from error
        if not relative.parts or ".." in relative.parts or relative.is_absolute() or "\\" in str(relative):
            raise ValueError("Invalid archived thumbnail path.")
        mapping[copied] = relative.as_posix()
    (data / "asset-map.json").write_text(json.dumps(mapping, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--resources", type=Path, help="Fresh generated data/artwork root, separate from authored source")
    args = parser.parse_args()
    bundle_companion(args.source, args.destination, resources=args.resources)
