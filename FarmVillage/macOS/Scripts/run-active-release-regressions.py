#!/usr/bin/env python3
"""Run the current clean-start16 release tests with explicit retired-case scope.

Requires the matching private inputs and pinned requirements. Run from any
working directory. WAVE2_GODBARN_ROOT selects the matching companion checkout.
Retired cases remain in source and are listed individually in the report;
new/shared cases are never discarded just because they share a module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "macOS/Tests"
MANIFEST = TESTS / "retired-world-test-cases.json"


def flattened(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from flattened(test)
        else:
            yield test


def source_hashes():
    paths = set(ROOT.glob("*.py"))
    for directory in (TESTS, ROOT / "macOS/Runtime", ROOT / "macOS/Scripts", ROOT / "portable"):
        paths.update(p for p in directory.rglob("*")
                     if p.is_file() and p.suffix in (".py", ".sh"))
    paths.update((MANIFEST, ROOT / "templates/play.html", ROOT / "templates/ruffle.html"))
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-only", action="store_true", help="Validate and list the selection without executing tests")
    parser.add_argument("--report", type=Path, help="Write a new JSON receipt; an existing file is never overwritten")
    arguments = parser.parse_args()
    if arguments.report and arguments.report.exists():
        parser.error("Choose a new report path; the existing receipt is preserved.")
    manifest = json.loads(MANIFEST.read_text())
    if manifest.get("schema") != 1:
        parser.error("Unsupported retired-case manifest; review the release test selection.")
    for name, expected in manifest["sourceFiles"].items():
        if hashlib.sha256((TESTS / name).read_bytes()).hexdigest() != expected:
            parser.error(f"Review retired-case IDs after changing {name}; its source lock differs.")
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(TESTS))
    os.environ.setdefault("WAVE2_GODBARN_ROOT", str(ROOT.parent / "GodBarn"))
    # Establish a temporary data directory before importing any game module.
    import test_persistence  # noqa: F401
    import world_travel
    active = sorted(world_travel.supported_worlds())
    if active != manifest["activeWorlds"] or set(active) & set(manifest["retiredWorlds"]):
        parser.error("The active world roster differs from the reviewed clean-start release.")
    names = [path.stem for path in sorted(TESTS.glob("test_*.py"))]
    loader = unittest.TestLoader()
    loaded = list(flattened(loader.loadTestsFromNames(names)))
    if loader.errors:
        parser.error("Test discovery failed; restore the matching private inputs before running this suite. " + loader.errors[0])
    excluded = {row["id"]: row for row in manifest["excludedCases"]}
    if len(excluded) != len(manifest["excludedCases"]):
        parser.error("Duplicate retired-case IDs require review.")
    missing = set(excluded) - {test.id() for test in loaded}
    if missing:
        parser.error("Retired-case IDs no longer exist: " + ", ".join(sorted(missing)))
    selected = [test for test in loaded if test.id() not in excluded]
    report = {
        "scope": "Current clean-start16 release; exact retired-only cases excluded explicitly, never counted as passes",
        "activeWorlds": active,
        "activeCaseCount": len(selected),
        "excludedCaseCount": len(excluded),
        "excludedCases": sorted(excluded.values(), key=lambda row: row["id"]),
        "selectionManifestSHA256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        "runnerSHA256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "source": str(ROOT),
        "python": sys.version,
        "hostPlatform": platform.platform(),
        "linuxExecution": sys.platform.startswith("linux"),
        "ubuntuExecution": False,
    }
    if sys.platform.startswith("linux"):
        try:
            distribution = platform.freedesktop_os_release()
            report["linuxDistribution"] = distribution.get("ID")
            report["ubuntuExecution"] = distribution.get("ID") == "ubuntu"
        except (AttributeError, OSError):
            report["linuxDistribution"] = "unverified"
    try:
        report["sourceCommit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        report["sourceCommit"] = None
    print(f"Active release: {len(active)} worlds, {len(selected)} selected cases; {len(excluded)} archived retired-only cases excluded explicitly.", flush=True)
    successful = True
    if arguments.list_only:
        report["status"] = "selection-validated-not-executed"
        report["selectedCases"] = [test.id() for test in selected]
    else:
        before = source_hashes()
        started = time.monotonic()
        result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(selected))
        after = source_hashes()
        successful = result.wasSuccessful() and before == after
        report.update(status="PASS" if successful else "FAIL", tests=result.testsRun,
                      failures=len(result.failures), errors=len(result.errors),
                      skipped=[{"id": test.id(), "reason": reason} for test, reason in result.skipped],
                      elapsedSeconds=round(time.monotonic() - started, 3),
                      sourceStable=before == after, hashesBefore=before, hashesAfter=after,
                      failureDetails=[{"id": test.id(), "traceback": detail}
                                      for test, detail in result.failures + result.errors])
    if arguments.report:
        with arguments.report.open("x") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
    print(json.dumps({key: report[key] for key in ("status", "activeCaseCount", "excludedCaseCount")}), flush=True)
    return 0 if successful else 1


if __name__ == "__main__":
    raise SystemExit(main())
