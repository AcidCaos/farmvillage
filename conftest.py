"""Report tests that need absent original or built inputs as UNRUN, never as bugs.

A public clone does not contain the original 2009 game files listed in
PrivateInputs.expected.json, nor anything built from them. Tests that need them
would otherwise crash and look like defects. Here a failure becomes a skip with an
"UNRUN: needs ..." reason, so PASS, FAIL and UNRUN stay separate, but only when
all of this holds:

* the failure is one of the exact signatures below (exception type, exact message
  and, where stated, the function that raised it), and
* the input it names is genuinely absent from disk when the report is made.

Signatures:

1. FileNotFoundError or NotADirectoryError naming a path listed in
   PrivateInputs.expected.json.
2. TypeError "'NoneType' object is not subscriptable" raised inside
   FarmVillage/items.py get_items() while its ITEMS_AMF catalog file is absent.
3. ValueError "Missing regular companion resource: data/..." raised inside
   GodBarn/scripts/bundle_companion.py _bundle_into() for an absent private file.
4. RuntimeError "Select the accepted Runtime using FARMVILLAGE_TEST_RUNTIME." from
   the neighborhood host tests, with the variable unset and no built tarball.
5. FileNotFoundError whose filename is an absent path under FarmVillage/macOS/.build.

Everything else still fails normally: assertion errors, other messages, the same
message from a different function, a missing non-data companion file, and any of
the above when the input is actually present. Failures during collection are only
recognised for signature 1.
"""
import json
import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
# Documented as external/private and absent from this source export.
EXTERNAL_REFERENCES = {"FarmVillage/macOS/Documentation/MECHANICS_RELEASE.md"}
BUILD_DIR = ROOT / "FarmVillage/macOS/.build"
ITEMS_FILE = ROOT / "FarmVillage/items.py"
COMPANION_FILE = ROOT / "GodBarn/scripts/bundle_companion.py"
NEIGHBORHOOD_FILE = ROOT / "FarmVillage/portable/neighborhood/test_neighborhood_host.py"
COMPANION_PREFIX = "Missing regular companion resource: "
NONE_SUBSCRIPT = "'NoneType' object is not subscriptable"
ACCEPTED_RUNTIME = "Select the accepted Runtime using FARMVILLAGE_TEST_RUNTIME."


def _private_paths():
    try:
        files = json.loads((ROOT / "PrivateInputs.expected.json").read_text())["files"]
    except (OSError, ValueError, KeyError):
        return set(EXTERNAL_REFERENCES)
    return set(files) | EXTERNAL_REFERENCES


PRIVATE = _private_paths()
MISSING = re.compile(r"(?:FileNotFoundError|NotADirectoryError): \[Errno 2\] No such file or directory: '([^']+)'")


def _private_input(text):
    for match in MISSING.finditer(text):
        try:
            relative = Path(match.group(1)).resolve().relative_to(ROOT).as_posix()
        except ValueError:
            continue
        if relative in PRIVATE and not (ROOT / relative).exists():
            return relative
    return None


def _same_file(path, expected):
    try:
        return Path(path).resolve() == expected.resolve()
    except OSError:
        return False


def _absent_private(path):
    """Reason text when path is a listed private input that is not on disk, else None."""
    if not isinstance(path, (str, os.PathLike)):
        return None
    try:
        relative = Path(path).resolve().relative_to(ROOT).as_posix()
    except (OSError, ValueError, RuntimeError):
        return None
    if relative in PRIVATE and not os.path.lexists(ROOT / relative):
        return "needs private input " + relative
    return None


def _items_catalog(error, last):
    if (type(error) is TypeError and str(error) == NONE_SUBSCRIPT
            and last.name == "get_items" and _same_file(last.path, ITEMS_FILE)):
        return _absent_private(last.frame.f_globals.get("ITEMS_AMF"))
    return None


def _companion_resource(error, last):
    if (type(error) is ValueError and str(error).startswith(COMPANION_PREFIX)
            and last.name == "_bundle_into" and _same_file(last.path, COMPANION_FILE)):
        name = last.frame.f_locals.get("name")
        if isinstance(name, str) and name.startswith("data/") and str(error) == COMPANION_PREFIX + name:
            return _absent_private(last.frame.f_locals.get("path"))
    return None


def _accepted_runtime(error, last):
    if (type(error) is RuntimeError and str(error) == ACCEPTED_RUNTIME
            and _same_file(last.path, NEIGHBORHOOD_FILE)
            and not os.environ.get("FARMVILLAGE_TEST_RUNTIME")
            and not list((BUILD_DIR / "PortablePreparation").glob("*-final.tar.gz"))):
        return ("needs an accepted Runtime: set FARMVILLAGE_TEST_RUNTIME or build one under "
                "FarmVillage/macOS/.build/PortablePreparation")
    return None


def _built_artifact(error, last):
    if isinstance(error, FileNotFoundError) and isinstance(error.filename, (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(error.filename))
        try:
            relative = path.resolve().relative_to(BUILD_DIR.resolve()).as_posix()
        except (OSError, ValueError, RuntimeError):
            return None
        if not os.path.lexists(BUILD_DIR / relative):
            return "needs built artifact FarmVillage/macOS/.build/" + relative
    return None


SIGNATURES = (_items_catalog, _companion_resource, _accepted_runtime, _built_artifact)


def _unrun_reason(excinfo, text):
    """Why this failure is only an absent input, or None for a genuine failure."""
    error = excinfo.value
    if isinstance(error, OSError):
        path = _private_input(text)
        if path:
            return "needs private input " + path
    entries = excinfo.traceback
    if not len(entries):
        return None
    last = entries[-1]
    for signature in SIGNATURES:
        reason = signature(error, last)
        if reason:
            return reason
    return None


def _as_unrun(report, reason):
    report.outcome = "skipped"
    location = str(getattr(report, "fspath", "") or report.nodeid)
    report.longrepr = (location, 0, "UNRUN: " + reason)


@pytest.hookimpl(hookwrapper=True)
def pytest_make_collect_report(collector):
    outcome = yield
    report = outcome.get_result()
    if report.failed:
        path = _private_input(str(report.longrepr))
        if path:
            _as_unrun(report, "needs private input " + path)
            report.result = []


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.failed and call.excinfo is not None:
        reason = _unrun_reason(call.excinfo, str(report.longrepr))
        if reason:
            _as_unrun(report, reason)
