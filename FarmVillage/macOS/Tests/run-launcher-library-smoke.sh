#!/bin/bash
set -euo pipefail
TASK_TESTS="$(cd "$(dirname "$0")" && pwd)"
TASK_MACOS="$(cd "$TASK_TESTS/.." && pwd)"
TASK_WORK="$(mktemp -d "${TMPDIR:-/tmp}/FarmVillageLibraryCompile.XXXXXX")"
trap '/bin/rm -rf "$TASK_WORK"' EXIT
xcrun swiftc -parse-as-library -strict-concurrency=complete -warnings-as-errors \
    -module-cache-path "$TASK_WORK/ModuleCache" \
    "$TASK_MACOS/Sources/LauncherLibrary.swift" \
    "$TASK_MACOS/Sources/RuntimeController.swift" \
    "$TASK_MACOS/Sources/GameWebView.swift" \
    "$TASK_TESTS/LauncherLibrarySmoke.swift" \
    -o "$TASK_WORK/LauncherLibrarySmoke"
"$TASK_WORK/LauncherLibrarySmoke"
