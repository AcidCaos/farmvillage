#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_PATH="${1:-}"
if [[ "$APP_PATH" != /* || ! -d "$APP_PATH" || ( "$#" -ne 1 && "$#" -ne 3 ) ]]; then
    echo "Usage: $0 /absolute/FarmVillage.app [http://127.0.0.1:5501/ EXPECTED_FIXTURE_TOKEN]" >&2
    exit 2
fi

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/FarmVillageNativeSmoke.XXXXXX")"
cleanup() {
    local result=$?
    if [[ "$result" -eq 75 || "$result" -eq 130 || "$result" -eq 143 ]]; then
        echo "Owned app cleanup is incomplete; isolated data preserved at $WORK_DIR" >&2
    else
        rm -rf "$WORK_DIR"
    fi
    return "$result"
}
trap cleanup EXIT

xcrun swiftc -parse-as-library -strict-concurrency=complete -warnings-as-errors \
    -module-cache-path "$WORK_DIR/ModuleCache" \
    "$SCRIPT_DIR/NativeLaunchSmoke.swift" -o "$WORK_DIR/NativeLaunchSmoke"
xcrun swiftc -parse-as-library -strict-concurrency=complete -warnings-as-errors \
    -module-cache-path "$WORK_DIR/ModuleCache" \
    "$MACOS_DIR/Sources/RuntimeController.swift" "$SCRIPT_DIR/RuntimeDirectorySmoke.swift" \
    -o "$WORK_DIR/RuntimeDirectorySmoke"
xcrun swiftc -parse-as-library -strict-concurrency=complete -warnings-as-errors \
    -module-cache-path "$WORK_DIR/ModuleCache" \
    "$MACOS_DIR/Sources/RuntimeController.swift" "$SCRIPT_DIR/NativeLogSmoke.swift" \
    -o "$WORK_DIR/NativeLogSmoke"

"$WORK_DIR/RuntimeDirectorySmoke" valid "$WORK_DIR/LaunchData" --farmvillage-data-dir "$WORK_DIR/LaunchData"
"$WORK_DIR/RuntimeDirectorySmoke" valid_equals "$WORK_DIR/EqualsData" "--farmvillage-data-dir=$WORK_DIR/EqualsData"
"$WORK_DIR/RuntimeDirectorySmoke" injected "$WORK_DIR/InjectedData"
"$WORK_DIR/RuntimeDirectorySmoke" relative --farmvillage-data-dir relative/path
"$WORK_DIR/RuntimeDirectorySmoke" missing --farmvillage-data-dir
"$WORK_DIR/RuntimeDirectorySmoke" duplicate --farmvillage-data-dir "$WORK_DIR/LaunchData" --farmvillage-data-dir "$WORK_DIR/OtherData"
"$WORK_DIR/RuntimeDirectorySmoke" relative_equals --farmvillage-data-dir=relative/path
"$WORK_DIR/RuntimeDirectorySmoke" empty_equals --farmvillage-data-dir=
"$WORK_DIR/RuntimeDirectorySmoke" mixed_duplicates --farmvillage-data-dir "$WORK_DIR/LaunchData" "--farmvillage-data-dir=$WORK_DIR/OtherData"
"$WORK_DIR/RuntimeDirectorySmoke" malformed_suffix --farmvillage-data-directory "$WORK_DIR/LaunchData"
"$WORK_DIR/RuntimeDirectorySmoke" double_equals "--farmvillage-data-dir==$WORK_DIR/LaunchData"
"$WORK_DIR/NativeLogSmoke"
"$WORK_DIR/NativeLaunchSmoke" "$APP_PATH" "$WORK_DIR/AppData" --paired

if [[ "$#" -eq 3 ]]; then
    xcrun swiftc -parse-as-library -strict-concurrency=complete -warnings-as-errors \
        -module-cache-path "$WORK_DIR/ModuleCache" \
        "$MACOS_DIR/Sources/GameWebView.swift" "$SCRIPT_DIR/NativeWebSmoke.swift" \
        -o "$WORK_DIR/NativeWebSmoke"
    "$WORK_DIR/NativeWebSmoke" "$2" "$3"
fi
