#!/usr/bin/env python3
"""Deliberately reseal reviewed source changes; never adopt private inputs."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = {".swf", ".wasm", ".amf", ".png", ".jpg", ".jpeg", ".gif", ".mp3", ".ttf", ".gz", ".zip", ".tar", ".pyc", ".log", ".secret", ".hash"}

def refresh(root, additions):
    path = root / "SOURCE_MANIFEST.json"
    document = json.loads(path.read_text())
    private = json.loads((root / "PrivateInputs.expected.json").read_text())["files"]
    names = set(document["files"]) | set(additions)
    files = {}
    for name in sorted(names):
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name or name in private or name == "SOURCE_MANIFEST.json":
            raise ValueError("Unsafe/private manifest path: " + name)
        if any(x in relative.parts for x in [".git", ".venv", "LocalData", "saves", "workspace", "god-barn", ".lan-server", "__pycache__"]) or Path(name).suffix.lower() in FORBIDDEN:
            raise ValueError("Local/binary file refused: " + name)
        p = root
        for part in relative.parts:
            p /= part
            if p.is_symlink():
                raise ValueError("Linked source refused: " + name)
        raw = p.read_bytes()
        raw.decode("utf-8")
        if b"\0" in raw:
            raise ValueError("Binary source refused: " + name)
        files[name] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    document["files"] = files
    result = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True)
    document["reviewedFromCommit"] = result.stdout.strip() if result.returncode == 0 else "no-local-git-revision"
    document["resealScope"] = "Reviewed source changes only; gameplay/platform acceptance requires a separate new record"
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    return len(files)

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reviewed", action="store_true", required=True, help="Confirm that the exact source diff has been reviewed")
    p.add_argument("--add", action="append", default=[], help="Explicit new text-source path to adopt")
    a = p.parse_args()
    print("Resealed %d reviewed source files; no gameplay acceptance implied." % refresh(ROOT, a.add))
