#!/bin/bash
# Build the local unsigned app without launching it or running tests.
set -euo pipefail
TASK_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_PROJECT_DIR="$(cd "$TASK_SCRIPT_DIR/.." && pwd)"
TASK_SOURCE_ROOT="$(cd "$TASK_PROJECT_DIR/../.." && pwd)"
TASK_CONFIGURATION=Debug
TASK_PUBLIC_RESOURCES=""
TASK_OUTPUT=""
TASK_BUILD_PYTHON="${FARMVILLAGE_BUILD_PYTHON:-}"
while [[ $# -gt 0 ]]; do
    case "$1" in
        Debug|Release) TASK_CONFIGURATION="$1"; shift ;;
        --resources|--output|--python)
            [[ $# -ge 2 && -n "$2" ]] || { echo "Missing value for $1" >&2; exit 2; }
            case "$1" in
                --resources) TASK_PUBLIC_RESOURCES="$2" ;;
                --output) TASK_OUTPUT="$2" ;;
                --python) TASK_BUILD_PYTHON="$2" ;;
            esac
            shift 2 ;;
        *) printf 'Usage: %s [Debug|Release] [--resources PACK --output EXTERNAL --python PYTHON]\n' "$0" >&2; exit 2 ;;
    esac
done
if [[ -n "$TASK_PUBLIC_RESOURCES" && -z "$TASK_OUTPUT" ]] || [[ -z "$TASK_PUBLIC_RESOURCES" && -n "$TASK_OUTPUT" ]]; then
    echo '--resources and --output must be supplied together.' >&2
    exit 2
fi

# A public source clone lacks the separately prepared game resources. Check
# representative original/player/companion/native inputs with Bash before
# invoking Python, Apple's developer-tool shims, or the compiler.
if [[ -z "$TASK_PUBLIC_RESOURCES" ]]; then
TASK_MISSING=()
for TASK_INPUT in \
    FarmVillage/assethash/v9/assethash.master.amf.gz \
    FarmVillage/embeds/Flash/v855097-855094/FarmGame.swf \
    FarmVillage/embeds/Flash/v855097-855094/FV_Preloader.swf \
    FarmVillage/xml/gz/v855098/FarmConfig.swf \
    FarmVillage/ruffle_runtime/0.7.1-farmvillage-gc1/ruffle.js \
    FarmVillage/ruffle_runtime/0.7.1-farmvillage-gc1/50c5ac40cece24645a25.wasm \
    GodBarn/data/catalog.json \
    GodBarn/data/ui-assets.json \
    FarmVillage/macOS/Resources/Heritage/manifest.json \
    FarmVillage/macOS/Resources/Heritage/farmville-logo.png \
    FarmVillage/macOS/Resources/Assets.xcassets/AppIcon.appiconset/icon_512x512.png; do
    if [[ ! -f "$TASK_SOURCE_ROOT/$TASK_INPUT" || -L "$TASK_SOURCE_ROOT/$TASK_INPUT" ]]; then
        TASK_MISSING+=("$TASK_INPUT")
    fi
done
if [[ ${#TASK_MISSING[@]} -ne 0 ]]; then
    printf '\nMac build paused: required prepared game resources are missing.\n' >&2
    printf 'Run START_MAC.command for the guided public-resource installer. Read docs/PLAY_ON_MAC.md and its Mac installation guide before building.\n' >&2
    printf 'Missing resource examples:\n' >&2
    printf '  %s\n' "${TASK_MISSING[@]}" >&2
    printf 'No Python setup, compilation or game-resource download was started.\n' >&2
    exit 2
fi

TASK_RESOURCE_CHECKER="$TASK_SOURCE_ROOT/tools/private-inputs.py"
if [[ ! -f "$TASK_RESOURCE_CHECKER" || -L "$TASK_RESOURCE_CHECKER" ]]; then
    printf 'The prepared-resource verification tool is missing. Use the complete source checkout and read docs/PLAY_ON_MAC.md.\n' >&2
    exit 2
fi
fi
TASK_HOST_SYSTEM="$(/usr/bin/uname -s)"
task_is_apple_python_shim() {
    [[ "$TASK_HOST_SYSTEM" == Darwin ]] && [[ "$1" == /usr/bin/python3 || "$1" -ef /usr/bin/python3 ]]
}
if [[ -z "$TASK_BUILD_PYTHON" ]]; then
    for TASK_CANDIDATE in /opt/homebrew/bin/python3 /usr/local/bin/python3 \
        /Library/Frameworks/Python.framework/Versions/Current/bin/python3 python3; do
        TASK_RESOLVED="$(command -v "$TASK_CANDIDATE" 2>/dev/null || true)"
        if [[ -n "$TASK_RESOLVED" && -x "$TASK_RESOLVED" ]] && ! task_is_apple_python_shim "$TASK_RESOLVED"; then
            TASK_BUILD_PYTHON="$TASK_RESOLVED"
            break
        fi
    done
fi
if [[ -z "$TASK_BUILD_PYTHON" || ! -x "$TASK_BUILD_PYTHON" ]] || task_is_apple_python_shim "$TASK_BUILD_PYTHON"; then
    printf 'An installed Python is needed to verify the prepared resources. Install Python 3.10+ as described in docs/PLAY_ON_MAC.md, or set FARMVILLAGE_BUILD_PYTHON to its executable path.\n' >&2
    printf 'Apple’s Python installation shim was not invoked. No compilation was started.\n' >&2
    exit 2
fi
printf 'Checking the complete prepared resource set before compiling...\n'
TASK_XCODE_EXTRA=()
TASK_DERIVED_DATA="$TASK_PROJECT_DIR/.build/DerivedData"
if [[ -n "$TASK_PUBLIC_RESOURCES" ]]; then
    TASK_PATHS="$("$TASK_BUILD_PYTHON" -I -S -B -c 'import pathlib,sys; paths=[pathlib.Path(p).absolute() for p in sys.argv[1:]]; source,pack,out=paths; assert all(".." not in p.parts and "\n" not in str(p) and not any(q.is_symlink() for q in (p,*p.parents)) for p in paths), "Linked or traversing build paths refused"; assert all(source != p and source not in p.parents and p not in source.parents for p in (pack,out)), "Resources and build output must be outside the source checkout"; assert out == pack / "macos-build" or (pack != out and pack not in out.parents and out not in pack.parents), "Build output must be external or PACK/macos-build"; assert pack.is_dir(), "Prepare the resource pack first"; print(pack); print(out)' "$TASK_SOURCE_ROOT" "$TASK_PUBLIC_RESOURCES" "$TASK_OUTPUT")" || exit 2
    TASK_PUBLIC_RESOURCES="${TASK_PATHS%%$'\n'*}"
    TASK_OUTPUT="${TASK_PATHS#*$'\n'}"
    if ! "$TASK_BUILD_PYTHON" -I -S -B "$TASK_SOURCE_ROOT/tools/native_resources.py" --resources "$TASK_PUBLIC_RESOURCES" --check; then
        echo 'Native resource verification failed; no compilation started.' >&2
        exit 2
    fi
    TASK_PIN_SHA="$("$TASK_BUILD_PYTHON" -I -S -B -c 'import json,pathlib,sys; p=pathlib.Path(sys.argv[1])/"Runtime/PREPARED_RUNTIME.json"; assert p.is_file() and not p.is_symlink(), "Missing prepared runtime pin"; m=json.loads(p.read_text()); assert m.get("schema")==1, "Invalid prepared runtime pin"; print(m["runtime_manifest_sha256"])' "$TASK_PUBLIC_RESOURCES")" || exit 2
    if ! "$TASK_BUILD_PYTHON" -I -S -B "$TASK_SOURCE_ROOT/FarmVillage/runtime_compatibility.py" --payload "$TASK_PUBLIC_RESOURCES/Runtime" --prepared-runtime-pin-sha256 "$TASK_PIN_SHA"; then
        echo 'Player resource verification failed; no compilation started.' >&2
        exit 2
    fi
    TASK_DERIVED_DATA="$TASK_OUTPUT/DerivedData"
    TASK_XCODE_EXTRA=(FARMVILLAGE_PUBLIC_RESOURCES="$TASK_PUBLIC_RESOURCES" FARMVILLAGE_NATIVE_ASSET_ROOT="$TASK_PUBLIC_RESOURCES/native" FARMVILLAGE_RESOURCE_PYTHON="$TASK_BUILD_PYTHON" CODE_SIGNING_REQUIRED=NO CODE_SIGN_IDENTITY= CODE_SIGN_STYLE=Manual DEVELOPMENT_TEAM=)
else
if ! "$TASK_BUILD_PYTHON" -I -S -B "$TASK_RESOURCE_CHECKER" check; then
    printf '\nPrepared-resource verification failed. Read docs/PLAY_ON_MAC.md and use its resource installer. No compilation or game-resource download was started.\n' >&2
    exit 2
fi
fi

# Tests can supply an owned compiler stub. Otherwise use the selected full
# Xcode binary directly, avoiding /usr/bin/xcodebuild's installation shim.
TASK_XCODEBUILD="${FARMVILLAGE_XCODEBUILD:-}"
if [[ -z "$TASK_XCODEBUILD" ]]; then
    TASK_DEVELOPER_DIR="${DEVELOPER_DIR:-}"
    if [[ -z "$TASK_DEVELOPER_DIR" ]]; then
        TASK_DEVELOPER_DIR="$(/usr/bin/xcode-select -p 2>/dev/null || true)"
    elif [[ -d "$TASK_DEVELOPER_DIR/Contents/Developer" ]]; then
        TASK_DEVELOPER_DIR="$TASK_DEVELOPER_DIR/Contents/Developer"
    fi
    if [[ -z "$TASK_DEVELOPER_DIR" || ! -d "$TASK_DEVELOPER_DIR/Platforms/MacOSX.platform" ]]; then
        printf 'Full Xcode with its macOS SDK is required to build the app. Read docs/PLAY_ON_MAC.md; no developer tools were installed or compilation started.\n' >&2
        exit 2
    fi
    TASK_XCODEBUILD="$TASK_DEVELOPER_DIR/usr/bin/xcodebuild"
fi
if [[ ! -x "$TASK_XCODEBUILD" ]]; then
    printf 'The selected Xcode build executable is unavailable. Check Xcode selection or FARMVILLAGE_XCODEBUILD; see docs/PLAY_ON_MAC.md.\n' >&2
    exit 2
fi
"$TASK_XCODEBUILD" \
    -project "$TASK_PROJECT_DIR/FarmVillage.xcodeproj" \
    -scheme FarmVillage \
    -configuration "$TASK_CONFIGURATION" \
    -destination 'platform=macOS' \
    -derivedDataPath "$TASK_DERIVED_DATA" \
    ${TASK_XCODE_EXTRA[@]+"${TASK_XCODE_EXTRA[@]}"} \
    CODE_SIGNING_ALLOWED=NO \
    build
printf '\nApp: %s/Build/Products/%s/FarmVillage.app\n' "$TASK_DERIVED_DATA" "$TASK_CONFIGURATION"
