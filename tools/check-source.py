#!/usr/bin/env python3
"""Verify the source manifest and run asset-free synthetic regression suites."""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def verify(root, publication=False):
    document = json.loads((root / "SOURCE_MANIFEST.json").read_text())
    files = document["files"]
    private = json.loads((root / "PrivateInputs.expected.json").read_text())["files"]
    for name, seal in files.items():
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Missing or linked source: " + name)
        raw = path.read_bytes()
        if len(raw) != seal["bytes"] or hashlib.sha256(raw).hexdigest() != seal["sha256"]:
            raise ValueError("Source differs from initial handoff manifest: " + name)
        text = raw.decode("utf-8")
        for line_number, line in enumerate(text.splitlines(), 1):
            if line.startswith(("<<<<<<< ", ">>>>>>> ")):
                raise ValueError("Unresolved merge conflict in %s:%d" % (name, line_number))
        if path.suffix == ".py":
            ast.parse(text, filename=name)
        elif path.suffix in {".sh", ".command"}:
            subprocess.run(["bash", "-n", str(path)], check=True,
                           env={key: value for key, value in os.environ.items() if key not in {"BASH_ENV", "ENV"}})
    unexpected = []
    for path in root.rglob("*"):
        name = path.relative_to(root).as_posix()
        if ".git" in path.relative_to(root).parts or "__pycache__" in path.relative_to(root).parts:
            continue
        if path.is_symlink():
            raise ValueError("Linked outgoing file refused: " + name)
        if path.name == ".DS_Store" and path.is_file():
            continue  # Finder metadata is ignored by Git and never selected for source archives.
        if not path.is_file() or name in files or name == "SOURCE_MANIFEST.json":
            continue
        if name in private and not publication:
            continue
        unexpected.append(name)
    if unexpected:
        raise ValueError("Unexpected files in source folder; first: " + unexpected[0])
    return {"status": "source-manifest-verified", "files": len(files), "publicationCheck": publication, "source": document["source"]}

def run_tests(root):
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    suites = [
        (root / "FarmVillage/portable/Linux", ["-m", "unittest", "-v", "test_server_runner", "test_install_service", "test_diagnose_saves", "test_preloader_timing", "test_install_fresh_world"]),
        (root / "FarmVillage/macOS/Tests", ["-m", "unittest", "-v", "test_persistence.AtomicStorageTests", "test_persistence.CacheIdentityTests", "test_persistence.MultiFarmJournalTests"]),
        (root / "GodBarn", ["-m", "unittest", "discover", "-s", "tests", "-p", "test_engine.py", "-v"]),
        (root / "GodBarn", ["-m", "unittest", "discover", "-s", "tests", "-p", "test_seasonal.py", "-v"]),
        (root / "GodBarn", ["-m", "unittest", "discover", "-s", "tests", "-p", "test_resource_bootstrap.py", "-v"]),
        (root / "GodBarn", ["-m", "unittest", "discover", "-s", "tests", "-p", "test_bundle_companion.py", "-v"]),
        (root / "tools", ["-m", "unittest", "discover", "-s", ".", "-p", "test_*.py"]),
    ]
    for directory, args in suites:
        subprocess.run([sys.executable, "-B", *args], cwd=directory, env=env, check=True)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--for-publication", action="store_true", help="Also refuse any imported private files")
    p.add_argument("--tests", action="store_true")
    p.add_argument("--with-private-inputs", action="store_true", help="Validate private inputs and list the exact active release selection without executing it")
    a = p.parse_args()
    print(json.dumps(verify(a.root, a.for_publication), indent=2), flush=True)
    subprocess.run([sys.executable, "-I", "-S", "-B", str(a.root / "tools/check-doc-links.py"), "--root", str(a.root)], check=True)
    if a.tests:
        run_tests(a.root)
    if a.with_private_inputs:
        if a.for_publication:
            p.error("Private selection and publication checks use separate clean/imported source copies")
        subprocess.run([sys.executable, "-B", str(a.root / "tools/private-inputs.py"), "check"], check=True)
        with tempfile.TemporaryDirectory(prefix="farmvillage-active-selection-") as temporary:
            subprocess.run([sys.executable, "-I", "-B", str(a.root / "FarmVillage/macOS/Scripts/run-active-release-regressions.py"), "--list-only", "--report", str(Path(temporary) / "selection.json")], check=True)

if __name__ == "__main__":
    main()
