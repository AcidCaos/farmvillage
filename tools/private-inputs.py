#!/usr/bin/env python3
"""Validate/import authorized local build inputs; no downloads or farm access."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil

ROOT = Path(__file__).resolve().parents[1]

def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()

def safe_path(root, name, missing=False):
    relative = PurePosixPath(name)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts or "\\" in name:
        raise ValueError("Invalid relative path: " + name)
    path = root.absolute()
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError("Linked root/ancestor refused; use an ordinary canonical path")
    for index, part in enumerate(relative.parts):
        path /= part
        if path.is_symlink():
            raise ValueError("Linked path refused: " + name)
        if path.exists() and index < len(relative.parts) - 1 and not path.is_dir():
            raise ValueError("Parent is not a directory: " + name)
    if path.exists() and not path.is_file():
        raise ValueError("Leaf is not an ordinary file: " + name)
    if not missing and not path.is_file():
        raise ValueError("Missing input: " + name)
    return path

def manifest(root):
    d = json.loads((root / "PrivateInputs.expected.json").read_text())
    public = json.loads((root / "SOURCE_MANIFEST.json").read_text())["files"]
    files = d["files"]
    if d.get("schema") != 1 or not files:
        raise ValueError("Unsupported/empty private input manifest")
    for name, info in files.items():
        safe_path(root, name, True)
        if name in public or name.split("/", 1)[0] not in {"FarmVillage", "GodBarn"}:
            raise ValueError("Input overlaps source or escapes component: " + name)
        if not isinstance(info.get("bytes"), int) or info["bytes"] < 0 or len(info.get("sha256", "")) != 64:
            raise ValueError("Invalid input seal: " + name)
    return files

def matches(path, info):
    return path.is_file() and not path.is_symlink() and path.stat().st_size == info["bytes"] and sha(path) == info["sha256"]

def check(root):
    files = manifest(root)
    bad = [name for name, info in files.items() if not matches(safe_path(root, name, True), info)]
    if bad:
        raise ValueError("Private input check failed for %d files; first: %s" % (len(bad), bad[0]))
    return {"status": "all-private-inputs-match", "files": len(files), "bytes": sum(x["bytes"] for x in files.values())}

def import_inputs(root, runtime, barn, replace=False):
    files = manifest(root)
    roots = {"FarmVillage": runtime.absolute(), "GodBarn": barn.absolute()}
    plan = []
    for name, info in files.items():
        component, relative = name.split("/", 1)
        source = safe_path(roots[component], relative)
        if not matches(source, info):
            raise ValueError("Source differs from the reviewed set: " + name)
        target = safe_path(root, name, True)
        if target.exists() and not matches(target, info) and not replace:
            raise ValueError("Different existing input preserved; back it up then use --replace: " + name)
        plan.append((source, target, info))
    # Validate every source and destination before the first write.
    for source, target, info in plan:
        if not matches(target, info):
            target.parent.mkdir(parents=True, exist_ok=True)
            safe_path(root, target.relative_to(root).as_posix(), True)
            shutil.copyfile(source, target)
    return check(root)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=ROOT)
    sub = p.add_subparsers(dest="action", required=True)
    sub.add_parser("check")
    i = sub.add_parser("import")
    i.add_argument("--runtime-source", required=True, type=Path)
    i.add_argument("--godbarn-source", required=True, type=Path)
    i.add_argument("--replace", action="store_true")
    a = p.parse_args()
    result = check(a.root.absolute()) if a.action == "check" else import_inputs(a.root.absolute(), a.runtime_source, a.godbarn_source, a.replace)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(str(error))
