#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DATA_DIR="${1:-}"
TOKEN="${2:-}"
OUTPUT_DIR="${3:-$MACOS_DIR/.build/FullGameValidation}"
if [[ "$#" -lt 2 || "$#" -gt 3 || "$DATA_DIR" != /* || ! -d "$DATA_DIR/saves" || -z "$TOKEN" || "$OUTPUT_DIR" != "$MACOS_DIR/.build/"* ]]; then
    echo "Usage: $0 /absolute/isolated-data EXPECTED_FIXTURE_TOKEN [/absolute/repository/macOS/.build/output]" >&2
    exit 2
fi
mkdir -p "$OUTPUT_DIR" "$MACOS_DIR/.build/NativeSmokeModuleCache"
ACTION_PLAN="$OUTPUT_DIR/actions.json"
if [[ ! -e "$ACTION_PLAN" ]]; then
    printf '%s\n' '{"steps":[]}' > "$ACTION_PLAN"
fi
xcrun swiftc -parse-as-library -strict-concurrency=complete -warnings-as-errors \
    -module-cache-path "$MACOS_DIR/.build/NativeSmokeModuleCache" \
    "$MACOS_DIR/Sources/GameWebView.swift" "$SCRIPT_DIR/NativeWebSmoke.swift" \
    -o "$MACOS_DIR/.build/NativeFullGameSmoke"
FARMVILLAGE_SMOKE_OUTPUT_DIR="$OUTPUT_DIR" "$MACOS_DIR/.build/NativeFullGameSmoke" \
    http://127.0.0.1:5501/ "$TOKEN" --full-game "$DATA_DIR" --actions "$ACTION_PLAN"
"$DATA_DIR/venv/bin/python" -I -B "$SCRIPT_DIR/verify_native_gameplay.py" "$OUTPUT_DIR"
