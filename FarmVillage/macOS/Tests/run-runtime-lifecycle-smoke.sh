#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCE_APP="${1:-}"
DATA_DIR="${2:-}"
if [[ "$#" -ne 2 || "$SOURCE_APP" != /* || ! -d "$SOURCE_APP/Contents/Resources" || "$DATA_DIR" != /* || ! -f "$DATA_DIR/prepared.json" ]]; then
    echo "Usage: $0 /absolute/FarmVillage.app /absolute/isolated-prepared-data" >&2
    exit 2
fi

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/FarmVillageRuntimeSmoke.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT
SMOKE_APP="$WORK_DIR/FarmVillageRuntimeSmoke.app"
mkdir -p "$SMOKE_APP/Contents/MacOS"
ln -s "$SOURCE_APP/Contents/Resources" "$SMOKE_APP/Contents/Resources"
cat > "$SMOKE_APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleExecutable</key><string>RuntimeLifecycleSmoke</string>
  <key>CFBundleIdentifier</key><string>org.farmvillage.runtime-smoke</string>
  <key>CFBundleName</key><string>FarmVillageRuntimeSmoke</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict></plist>
PLIST
xcrun swiftc -parse-as-library -strict-concurrency=complete -warnings-as-errors \
    -module-cache-path "$WORK_DIR/ModuleCache" \
    "$MACOS_DIR/Sources/RuntimeController.swift" "$SCRIPT_DIR/RuntimeLifecycleSmoke.swift" \
    -o "$SMOKE_APP/Contents/MacOS/RuntimeLifecycleSmoke"
"$SMOKE_APP/Contents/MacOS/RuntimeLifecycleSmoke" "$DATA_DIR"
