#!/usr/bin/env python3
"""Stage the same complete reviewed client served by the source backend."""

import argparse
import importlib.util
import os
from pathlib import Path
import stat
import struct
import tempfile

_SCRIPT = Path(__file__).resolve()
_CANDIDATES = ((_SCRIPT.parent.parent / "Runtime/client_compatibility.py",)
    if _SCRIPT.parent.name in ("Tools", "WrapperRuntime")
    else (_SCRIPT.parents[2] / "client_compatibility.py",))
_SOURCE = next((path for path in _CANDIDATES if path.is_file()), None)
if _SOURCE is None:
    raise RuntimeError("The reviewed client compatibility module is missing.")


def _load(name, source):
    if source.is_symlink() or not source.is_file():
        raise RuntimeError("The reviewed client module is missing or linked: " + source.name)
    spec = importlib.util.spec_from_file_location(name, source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MODULE = _load("farmvillage_client_compatibility", _SOURCE)
_MEADOWS = _load("farmvillage_meadows_client", _SOURCE.parent / "meadows_client.py")
_GRAPHICS = _load("farmvillage_client_graphics", _SOURCE.parent / "client_graphics.py")
BASE_COMPATIBILITY_BODY_SHA256 = _MODULE.COVE_UPGRADE_BODY_SHA256
PATCHED_BODY_SHA256 = _GRAPHICS.PATCHED_BODY_SHA256
PATCHED_BODY_BYTES = _GRAPHICS.PATCHED_BODY_BYTES


def __getattr__(name):
    # Expose historical constants/recipes for read-only inspection.
    # Public preparation APIs below always use the complete composition.
    return getattr(_MODULE, name)


def prepared_client_bytes(data):
    # Explicit composition works under Python -I without ambient import paths.
    if len(data) >= 8 and struct.unpack_from("<I", data, 4)[0] in (
            _MEADOWS.PATCHED_BODY_BYTES + 8, _GRAPHICS.IMAGE_BODY_BYTES + 8,
            _GRAPHICS.WIDGET_BODY_BYTES + 8, _GRAPHICS.PORT_BODY_BYTES + 8, _GRAPHICS.PATCHED_BODY_BYTES + 8):
        return _GRAPHICS.patch_client_bytes(data)
    return _GRAPHICS.patch_client_bytes(_MEADOWS.patch_client_bytes(_MODULE.patch_client_bytes(data)))


def prepared_client(source):
    return prepared_client_bytes(Path(source).read_bytes())


def stage_client_file(source, destination):
    """Prepare atomically; unknown inputs never replace a complete output."""
    original = source.read_bytes()
    prepared = prepared_client_bytes(original)
    if source == destination and prepared == original:
        return False
    mode = stat.S_IMODE(source.stat().st_mode)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".farmvillage-client-", suffix=".swf",
                                         dir=destination.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(prepared)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return prepared != original


# Keep both public preparation APIs aligned with the CLI and source server.
patch_client_bytes = prepared_client_bytes
patch_client_file = stage_client_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    try:
        changed = stage_client_file(arguments.input, arguments.output)
    except (OSError, ValueError) as error:
        parser.exit(1, "FarmVillage client staging failed: " + str(error) + "\n")
    print(("Prepared" if changed else "Verified") + " complete compatibility, scoped Meadows and graphics client: " + str(arguments.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
