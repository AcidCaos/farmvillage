#!/usr/bin/env python3
"""Guided resource installation for Mac players and Ubuntu server owners."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_BYTES = 19_126_111_395
GUIDES = {"mac": "docs/PLAY_ON_MAC.md", "server": "docs/PLAY_ON_SERVER.md"}

class RefusedInput(ValueError):
    pass

def ordinary_root(value):
    path = Path(value)
    if ".." in path.parts:
        raise RefusedInput("Choose the exact ordinary source folder without parent-directory traversal.")
    root = path.absolute()
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise RefusedInput("The selected source folder or an ancestor is a symbolic link.")
    if not root.is_dir():
        raise RefusedInput("The selected source folder is missing or is not a directory.")
    return root

def relative_file(name):
    if not isinstance(name, str) or not name or "\\" in name:
        raise RefusedInput("Invalid relative resource path.")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise RefusedInput("A manifest resource path escapes the selected source folder.")
    if any(part in {".git", ".ssh", ".aws", "Keychains", ".lan-server", "saves", "workspace", "snapshots", "history", ".venv"} for part in path.parts):
        raise RefusedInput("Player state, account data and private workspaces are not prepared resource inputs.")
    return path

@contextmanager
def ordinary_file(root, name):
    """Read one named regular file; never follow relative component symlinks."""
    path = relative_file(name)
    directories, descriptor = [], None
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        current = os.open(root, flags | getattr(os, "O_DIRECTORY", 0))
        directories.append(current)
        for part in path.parts[:-1]:
            current = os.open(part, flags | getattr(os, "O_DIRECTORY", 0), dir_fd=current)
            directories.append(current)
        descriptor = os.open(path.parts[-1], flags, dir_fd=current)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise RefusedInput("The resource is not an ordinary file.")
        stream = os.fdopen(descriptor, "rb")
        descriptor = None
        with stream:
            yield stream
    except OSError as error:
        if error.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise RefusedInput("The resource is linked or has a non-directory parent.") from error
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)
        for directory in reversed(directories):
            os.close(directory)

def group_name(name):
    for prefix, group in [
        ("FarmVillage/ruffle_runtime/", "Pinned local Ruffle player"),
        ("FarmVillage/macOS/Resources/", "Native macOS interface resources"),
        ("FarmVillage/macOS/Tests/", "Resource-dependent test fixtures"),
        ("FarmVillage/templates/", "Original browser interface resources"),
        ("FarmVillage/villages/", "Original starter templates"),
        ("GodBarn/data/", "God Barn metadata"),
        ("GodBarn/static/", "God Barn interface resources")]:
        if name.startswith(prefix):
            return group
    return "Original client and configuration" if name.startswith("FarmVillage/") else "Other prepared resources"

def resource_report(root):
    result = {"status": "manifest-unavailable", "scope": "Shared prepared-source compatibility set, not a minimal player download list", "expected_files": 0, "expected_bytes": 0,
              "matching_files": 0, "missing_files": 0, "mismatched_files": 0,
              "refused_files": 0, "unreadable_files": 0, "groups": {}, "errors": []}
    try:
        with ordinary_file(root, "PrivateInputs.expected.json") as stream:
            document = json.load(stream)
        if not isinstance(document, dict):
            raise ValueError("The prepared-resource manifest must be an object.")
        files = document.get("files")
        if document.get("schema") != 1 or not isinstance(files, dict) or not files:
            raise ValueError("The prepared-resource manifest is empty or unsupported.")
        for name, identity in files.items():
            if relative_file(name).parts[0] not in {"FarmVillage", "GodBarn"}:
                raise RefusedInput("A manifest resource is outside the two game components.")
            if not isinstance(identity, dict) or type(identity.get("bytes")) is not int or identity["bytes"] < 0:
                raise ValueError("Invalid resource byte count in the manifest.")
            if not isinstance(identity.get("sha256"), str) or not re.fullmatch(r"[0-9a-fA-F]{64}", identity["sha256"]):
                raise ValueError("Invalid resource SHA-256 identity in the manifest.")
        result["expected_files"] = len(files)
        result["expected_bytes"] = sum(x["bytes"] for x in files.values())
        for name, identity in sorted(files.items()):
            group = result["groups"].setdefault(group_name(name), {"expected": 0, "matching": 0,
                "missing": 0, "mismatched": 0, "refused": 0, "unreadable": 0, "problem_examples": []})
            group["expected"] += 1
            problem = None
            try:
                with ordinary_file(root, name) as stream:
                    if os.fstat(stream.fileno()).st_size != identity["bytes"]:
                        problem = "mismatched"
                    else:
                        digest = hashlib.sha256()
                        for block in iter(lambda: stream.read(1024 * 1024), b""):
                            digest.update(block)
                        if digest.hexdigest() != identity["sha256"].lower():
                            problem = "mismatched"
            except FileNotFoundError:
                problem = "missing"
            except RefusedInput:
                problem = "refused"
            except OSError:
                problem = "unreadable"
            if problem:
                group[problem] += 1
                result[problem + "_files"] += 1
                if len(group["problem_examples"]) < 3:
                    group["problem_examples"].append({"path": name, "problem": problem})
            else:
                group["matching"] += 1
                result["matching_files"] += 1
        result["status"] = "complete" if result["matching_files"] == len(files) else "incomplete"
    except (OSError, ValueError, TypeError) as error:
        result["errors"].append(str(error) if isinstance(error, ValueError) else "The resource manifest cannot be read as an ordinary file.")
    return result

def build_report(source_root=ROOT, audience="mac"):
    root = ordinary_root(source_root)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from resource_pipeline import plan
    resources = resource_report(root)
    return {"schema": 2, "audience": audience, "source_root": str(root), "status": "installation-plan", "play_ready": False,
        "public_bootstrap": {"implemented": True}, "resource_inputs": resources,
        "prepared_resource_inputs_match": resources["status"] == "complete",
        "storage": {"archive_bytes": ARCHIVE_BYTES, "exact_peak_known": False}, "download_plan": plan(audience),
        "guide": GUIDES[audience], "active_worlds": 16, "excluded_worlds": ["glen", "hlights"],
        "actions_this_guide": {"downloads": False, "installs": False, "builds": False,
          "creates_environment_or_cache": False, "reads_accounts_or_credentials": False, "scans_personal_folders": False}}

def main(argv=None, input_fn=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audience', choices=sorted(GUIDES), default='mac')
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--check', action='store_true', help='Show plan without downloads, writes or prompts')
    parser.add_argument('--json', action='store_true', help='Print the read-only plan as JSON')
    parser.add_argument('--resources', type=Path)
    parser.add_argument('--accept-downloads', action='store_true')
    args = parser.parse_args(argv)
    try:
        report = build_report(args.source_root, args.audience)
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from player_install import show_plan, wizard, install
        show_plan(args.audience)
        print('Guide: ' + GUIDES[args.audience])
        if args.check:
            return 0
        root = Path(report['source_root'])
        if args.accept_downloads:
            if args.resources is None:
                raise ValueError('--accept-downloads requires an explicit --resources folder')
            return install(root, args.audience, args.resources, consent=True)
        return wizard(root, args.audience, input_fn or input)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError, EOFError, KeyboardInterrupt) as error:
        print('Setup paused: ' + str(error) + '\nRerun with the same folder to resume. No unrelated folder was erased.', file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
