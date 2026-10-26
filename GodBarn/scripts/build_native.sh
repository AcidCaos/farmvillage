#!/bin/bash
# Compile a separate app without launching a server or changing farm data.
set -euo pipefail
TASK_BARN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TASK_GAME_DIR="$(cd "$TASK_BARN_DIR/../FarmVillage" && pwd)"
/usr/bin/xcodebuild \
    -project "$TASK_GAME_DIR/macOS/FarmVillage.xcodeproj" \
    -scheme FarmVillage \
    -configuration Release \
    -destination 'platform=macOS' \
    -derivedDataPath "$TASK_BARN_DIR/.build/NativeIntegration" \
    CODE_SIGNING_ALLOWED=NO \
    build
printf '\nApp: %s/.build/NativeIntegration/Build/Products/Release/FarmVillage.app\n' "$TASK_BARN_DIR"
