#!/usr/bin/env python3
"""Enable one named world only in a marked disposable /private/tmp Runtime copy.

This edits the fixture's copied activation list. It supplies no production
configuration switch, touches no saves and never starts or stops a server.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import stat
import tempfile


CANDIDATES = frozenset({"toyland", "sleepyhollow", "australia", "fforest", "htown", "atlantis", "glen", "hlights"})
PROTECTED_PORTS = frozenset({45358, 45467})


def enable_candidate(fixture: Path, world: str) -> bool:
    if world not in CANDIDATES:
        raise ValueError("Choose one explicitly recovered dormant world.")
    root = fixture.resolve(strict=True)
    if Path("/private/tmp") not in root.parents:
        raise ValueError("World candidates can be enabled only in /private/tmp fixtures.")
    marker = root / ".disposable-features-fixture"
    metadata_path = root / "fixture.json"
    if marker.is_symlink() or not marker.is_file() or metadata_path.is_symlink():
        raise ValueError("A marked disposable fixture is required.")
    metadata = json.loads(metadata_path.read_text())
    runtime = root / "Runtime"
    source = runtime / "themed_worlds.py"
    if (runtime.is_symlink() or source.is_symlink() or source.resolve().parent != runtime
            or Path(metadata.get("root", "")).resolve() != root
            or Path(metadata.get("runtime", "")).resolve() != runtime
            or metadata.get("synthetic") is not True or metadata.get("credentials") is not False
            or type(metadata.get("port")) is not int or metadata["port"] in PROTECTED_PORTS):
        raise ValueError("The fixture must be synthetic, isolated and have no credentials.")
    text = source.read_text()
    tree = ast.parse(text)
    assignments = {node.targets[0].id: node for node in tree.body
                   if isinstance(node, ast.Assign) and len(node.targets) == 1
                   and isinstance(node.targets[0], ast.Name)}
    specs = ast.literal_eval(assignments["SPECS"].value)
    node = assignments["ACTIVE_WORLDS"]
    if (not isinstance(node.value, ast.Call) or not isinstance(node.value.func, ast.Name)
            or node.value.func.id != "frozenset" or len(node.value.args) != 1):
        raise ValueError("The copied activation list does not match the reviewed structure.")
    active = frozenset(ast.literal_eval(node.value.args[0]))
    if world not in specs or not active <= specs.keys():
        raise ValueError("The copied runtime lacks this world's explicit contract.")
    if world in active:
        return False
    lines = text.splitlines(keepends=True)
    values = ", ".join(json.dumps(key) for key in sorted(active | {world}))
    lines[node.lineno - 1:node.end_lineno] = [
        "ACTIVE_WORLDS = frozenset({" + values + "})  # Disposable QA candidates only.\n"]
    prepared = "".join(lines)
    ast.parse(prepared)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=runtime,
                                         prefix=".world-candidate-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(prepared)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, stat.S_IMODE(source.stat().st_mode))
        os.replace(temporary, source)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("world", choices=sorted(CANDIDATES))
    args = parser.parse_args()
    try:
        changed = enable_candidate(args.fixture, args.world)
    except (OSError, ValueError, KeyError, SyntaxError) as error:
        parser.exit(1, f"World candidate preparation failed: {error}\n")
    print(f"{'Enabled' if changed else 'Verified'} {args.world} in disposable fixture {args.fixture}; restart that fixture separately.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
