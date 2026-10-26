#!/bin/bash
# Xcode resource staging only: never installs dependencies or starts the server.
set -euo pipefail
TASK_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_MACOS_DIR="$(cd "$TASK_SCRIPT_DIR/.." && pwd)"
TASK_UPSTREAM_DIR="$(cd "$TASK_MACOS_DIR/.." && pwd)"
TASK_COMMUNITY_DIR="$(cd "$TASK_UPSTREAM_DIR/.." && pwd)"
TASK_PUBLIC_RESOURCES="${FARMVILLAGE_PUBLIC_RESOURCES:-}"
TASK_RESOURCE_PYTHON="${FARMVILLAGE_RESOURCE_PYTHON:-/usr/bin/python3}"
TASK_HERITAGE="$TASK_MACOS_DIR/Resources/Heritage"
TASK_PIN_ARGS=()
if [[ -n "$TASK_PUBLIC_RESOURCES" ]]; then
    [[ -x "$TASK_RESOURCE_PYTHON" ]] || { echo 'Select the prepared resource Python executable.' >&2; exit 2; }
    "$TASK_RESOURCE_PYTHON" -I -S -B "$TASK_COMMUNITY_DIR/tools/native_resources.py" --resources "$TASK_PUBLIC_RESOURCES" --check
    TASK_UPSTREAM_DIR="$TASK_PUBLIC_RESOURCES/Runtime"
    TASK_HERITAGE="$TASK_PUBLIC_RESOURCES/native/Heritage"
    TASK_PIN_SHA="$("$TASK_RESOURCE_PYTHON" -I -S -B -c 'import json,pathlib,sys; p=pathlib.Path(sys.argv[1])/"PREPARED_RUNTIME.json"; assert p.is_file() and not p.is_symlink(), "Missing prepared runtime pin"; m=json.loads(p.read_text()); assert m.get("schema")==1, "Invalid prepared runtime pin"; print(m["runtime_manifest_sha256"])' "$TASK_UPSTREAM_DIR")"
    TASK_PIN_ARGS=(--prepared-runtime-pin-sha256 "$TASK_PIN_SHA")
    "$TASK_RESOURCE_PYTHON" -I -S -B "$TASK_COMMUNITY_DIR/FarmVillage/runtime_compatibility.py" --payload "$TASK_UPSTREAM_DIR" "${TASK_PIN_ARGS[@]}"
fi
TASK_RESOURCES="${TARGET_BUILD_DIR:?Run this script from the Xcode build phase}/${UNLOCALIZED_RESOURCES_FOLDER_PATH:?Missing resource folder}"
mkdir -p "$TASK_RESOURCES"
TASK_STAGE="$(/usr/bin/mktemp -d "$TASK_RESOURCES/.farmvillage-stage.XXXXXX")"
trap '/bin/rm -rf "$TASK_STAGE"' EXIT
TASK_PAYLOAD="$TASK_STAGE/Runtime"

# The scoped controls depend on their authoritative handlers and routing.
# Refuse a partial source tree before replacing a complete resource generation.
for TASK_REQUIRED in client_compatibility cove_client meadows_client client_graphics meadows_rules meadows_storage england_animals england_shipping cove_rules cove_port cove_shipping cellar_progression rainforest_features rainforest_rules placement_receipts inventory_sales commands server storage; do
    if [[ ! -f "$TASK_UPSTREAM_DIR/$TASK_REQUIRED.py" || -L "$TASK_UPSTREAM_DIR/$TASK_REQUIRED.py" ]]; then
        echo "Missing ordinary required runtime module: $TASK_REQUIRED.py" >&2
        exit 1
    fi
done

# Build a complete fresh payload. Reusing the previous destination would retain
# Python modules removed or renamed since an earlier incremental build.
mkdir -p "$TASK_PAYLOAD" "$TASK_STAGE/Scripts" "$TASK_STAGE/WrapperRuntime"
for TASK_SOURCE in "$TASK_UPSTREAM_DIR"/*.py; do
    /bin/cp "$TASK_SOURCE" "$TASK_PAYLOAD/"
done
for TASK_NAME in requirements.txt LICENSE README.md FLASH.md; do
    /bin/cp "$TASK_UPSTREAM_DIR/$TASK_NAME" "$TASK_PAYLOAD/"
done
for TASK_NAME in assethash embeds patched templates villages warc_extractor xml ruffle_runtime; do
    mkdir -p "$TASK_PAYLOAD/$TASK_NAME"
    /usr/bin/rsync -a --delete \
        --exclude '__pycache__/' --exclude '.DS_Store' \
        "$TASK_UPSTREAM_DIR/$TASK_NAME/" "$TASK_PAYLOAD/$TASK_NAME/"
done
# Stage the independent companion without its workspace, saves, screenshots,
# tests, or copied thumbnail collection. The live adapter resolves thumbnails
# from this app's existing extracted archive instead.
if [[ -n "$TASK_PUBLIC_RESOURCES" ]]; then
    [[ -f "$TASK_UPSTREAM_DIR/GodBarn/data/catalog.json.gz" && -f "$TASK_UPSTREAM_DIR/GodBarn/integration.py" ]] || { echo 'Prepared God Barn is incomplete.' >&2; exit 2; }
    /usr/bin/rsync -a --delete --exclude '__pycache__/' --exclude '.DS_Store' "$TASK_UPSTREAM_DIR/GodBarn/" "$TASK_PAYLOAD/GodBarn/"
    for TASK_NAME in PREPARED_RUNTIME.json PUBLIC_RUNTIME_BUILD.json PUBLIC_INSTALL.json; do
        /bin/cp "$TASK_UPSTREAM_DIR/$TASK_NAME" "$TASK_PAYLOAD/$TASK_NAME"
    done
else
    TASK_GOD_BARN="$TASK_UPSTREAM_DIR/../GodBarn"
    "$TASK_RESOURCE_PYTHON" -I -B "$TASK_GOD_BARN/scripts/bundle_companion.py" "$TASK_GOD_BARN" "$TASK_PAYLOAD/GodBarn"
fi
# Prepare the complete reviewed compatibility + scoped Meadows + graphics copy before fingerprinting.
# The standard-library patcher pins the complete upstream and resulting bytecode;
# source archives and persistent game data are never modified by this build step.
"$TASK_RESOURCE_PYTHON" -I -S -B "$TASK_SCRIPT_DIR/patch-game-client.py" \
    "$TASK_UPSTREAM_DIR/embeds/Flash/v855097-855094/FarmGame.swf" \
    "$TASK_PAYLOAD/embeds/Flash/v855097-855094/FarmGame.swf"
/bin/cp "$TASK_SCRIPT_DIR/runtime.sh" "$TASK_STAGE/Scripts/runtime.sh"
/usr/bin/rsync -a --delete --exclude '__pycache__/' --exclude '.DS_Store' \
    "$TASK_MACOS_DIR/Runtime/" "$TASK_STAGE/WrapperRuntime/"
/bin/cp "$TASK_SCRIPT_DIR/patch-game-client.py" "$TASK_STAGE/WrapperRuntime/patch-game-client.py"
/bin/cp "$TASK_MACOS_DIR/Documentation/THIRD_PARTY.md" "$TASK_STAGE/THIRD_PARTY.md"
/usr/bin/rsync -a --delete --exclude '.DS_Store' \
    "$TASK_HERITAGE/" "$TASK_STAGE/Heritage/"

# Refuse an incomplete or modified bundled player before publishing resources.
"$TASK_RESOURCE_PYTHON" -I -S -B "$TASK_PAYLOAD/runtime_compatibility.py" --payload "$TASK_PAYLOAD" ${TASK_PIN_ARGS[@]+"${TASK_PIN_ARGS[@]}"}

# Relative names keep the fingerprint independent of the build location.
# The runtime launcher can refresh code without touching the farm data.
(
    cd "$TASK_PAYLOAD"
    /usr/bin/find . -type f ! -name '.payload-version' -print0 \
        | /usr/bin/xargs -0 /usr/bin/shasum -a 256 \
        | LC_ALL=C /usr/bin/sort \
        | /usr/bin/shasum -a 256 \
        | /usr/bin/awk '{print $1}' > .payload-version
)

# Publish only after every source file and fingerprint has been prepared. These
# are build-product resources; persistent farm data is never part of this tree.
for TASK_NAME in Runtime Scripts WrapperRuntime Heritage; do
    /bin/rm -rf "$TASK_RESOURCES/$TASK_NAME"
    /bin/mv "$TASK_STAGE/$TASK_NAME" "$TASK_RESOURCES/$TASK_NAME"
done
/bin/mv -f "$TASK_STAGE/THIRD_PARTY.md" "$TASK_RESOURCES/THIRD_PARTY.md"
