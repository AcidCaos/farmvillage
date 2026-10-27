#!/bin/bash
set -euo pipefail

TASK_TEST_DIR="$(cd "$(dirname "$0")" && pwd)"
TASK_MACOS_DIR="$(cd "$TASK_TEST_DIR/.." && pwd)"
TASK_BUILT_APP="${1:-}"
TASK_DATA="${2:-}"
if [[ "$#" -lt 2 || "$#" -gt 3 || "$TASK_BUILT_APP" != /* || "$TASK_DATA" != /* || ! -d "$TASK_BUILT_APP/Contents/Resources/Runtime" ]]; then
    echo "Usage: $0 /absolute/FarmVillage.app /absolute/repository/LocalData [/absolute/evidence-folder]" >&2
    exit 2
fi
mkdir -p "$TASK_MACOS_DIR/.build"
TASK_OUTPUT="${3:-$(mktemp -d "$TASK_MACOS_DIR/.build/NativeHeritageValidation.XXXXXX")}"
if [[ "$TASK_OUTPUT" != /* ]]; then
    echo "The evidence folder must be absolute." >&2
    exit 2
fi
TASK_WORK="$(mktemp -d "${TMPDIR:-/tmp}/FarmVillageHeritageNative.XXXXXX")"
cleanup() {
    local task_result=$?
    if [[ "$task_result" -eq 75 || "$task_result" -eq 130 || "$task_result" -eq 143 ]]; then
        echo "Native cleanup requires inspection; test bundle preserved at $TASK_WORK" >&2
    else
        rm -rf "$TASK_WORK"
    fi
    return "$task_result"
}
trap cleanup EXIT
TASK_HARNESS="$TASK_WORK/NativeHeritageGodBarnSmoke.app/Contents"
mkdir -p "$TASK_HARNESS/MacOS"
/usr/bin/ditto "$TASK_BUILT_APP/Contents/Resources" "$TASK_HARNESS/Resources"
/usr/bin/python3 -I -B - "$TASK_HARNESS/Info.plist" <<'PY'
import plistlib
import sys
from pathlib import Path
Path(sys.argv[1]).write_bytes(plistlib.dumps({
    "CFBundleIdentifier": "org.farmvillage.NativeHeritageGodBarnSmoke",
    "CFBundleExecutable": "NativeHeritageGodBarnSmoke",
    "CFBundlePackageType": "APPL", "NSHighResolutionCapable": True,
    "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
}))
PY
TASK_SOURCES=()
for TASK_NAME in RuntimeController GameWebView LauncherLibrary ContentView HeritageTheme HeritageAudio; do
    TASK_SOURCES+=("$TASK_MACOS_DIR/Sources/$TASK_NAME.swift")
done
xcrun swiftc -parse-as-library -swift-version 5 -strict-concurrency=complete -warnings-as-errors \
    -module-cache-path "$TASK_WORK/ModuleCache" \
    "${TASK_SOURCES[@]}" "$TASK_TEST_DIR/NativeHeritageGodBarnSmoke.swift" \
    -o "$TASK_HARNESS/MacOS/NativeHeritageGodBarnSmoke"
"$TASK_HARNESS/MacOS/NativeHeritageGodBarnSmoke" "$TASK_DATA" "$TASK_OUTPUT"
echo "Native launcher and God Barn evidence: $TASK_OUTPUT"
