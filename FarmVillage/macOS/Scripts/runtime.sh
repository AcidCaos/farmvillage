#!/bin/bash
# The native app owns this process. Replace the shell with the lifecycle supervisor.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/../WrapperRuntime/bootstrap.py" ]; then
    ADAPTER_DIR="$SCRIPT_DIR/../WrapperRuntime"
else
    ADAPTER_DIR="$SCRIPT_DIR/../Runtime"
fi

ACTION="${1:-}"
PYTHON_OVERRIDE=""
DATA_DIR=""
ARGS=("$@")
while [ "$#" -gt 0 ]; do
    case "$1" in
        --python|--data-dir)
            OPTION="$1"
            shift
            if [ "$#" -eq 0 ]; then
                echo "[FarmVillage] Missing value for $OPTION." >&2
                exit 2
            fi
            if [ "$OPTION" = "--python" ]; then PYTHON_OVERRIDE="$1"; else DATA_DIR="$1"; fi
            ;;
    esac
    shift
done

usable_python() {
    [ -x "$1" ] || return 1
    # Apple's stub may open a developer-tools installation dialog.
    if [ "$1" = "/usr/bin/python3" ] && ! /usr/bin/xcode-select -p >/dev/null 2>&1; then
        return 1
    fi
    "$1" -I -B -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1
}

PYTHON=""
if [ -n "$PYTHON_OVERRIDE" ]; then
    if usable_python "$PYTHON_OVERRIDE"; then PYTHON="$PYTHON_OVERRIDE"; else
        echo "[FarmVillage] The selected Python must be an executable Python 3.10 or newer: $PYTHON_OVERRIDE" >&2
        exit 1
    fi
elif [ "$ACTION" = "start" ] && [ -n "$DATA_DIR" ] && usable_python "$DATA_DIR/venv/bin/python"; then
    PYTHON="$DATA_DIR/venv/bin/python"
else
    for CANDIDATE in /opt/homebrew/bin/python3 /usr/local/bin/python3 \
        /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
        python3.13 python3.12 python3.11 python3.10 python3; do
        RESOLVED="$(command -v "$CANDIDATE" 2>/dev/null || true)"
        if [ -n "$RESOLVED" ] && usable_python "$RESOLVED"; then
            PYTHON="$RESOLVED"
            break
        fi
    done
fi

if [ -z "$PYTHON" ]; then
    echo "[FarmVillage] Python 3.10 or newer is required. Install Python from python.org or Homebrew, then select its executable in the app." >&2
    exit 1
fi

export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1
# A public install reuses its already verified archive. This small path-only
# receipt is bundled by the installer; the game archive is never copied into
# the app or downloaded a second time by Start.
PUBLIC_INSTALL="$SCRIPT_DIR/../Runtime/PUBLIC_INSTALL.json"
if [ -e "$PUBLIC_INSTALL" ] || [ -L "$PUBLIC_INSTALL" ]; then
    FARMVILLAGE_ASSETS_DIR="$("$PYTHON" -I -S -B -c 'import json,pathlib,sys; p=pathlib.Path(sys.argv[1]).absolute(); assert not p.is_symlink(), "Linked public install receipt refused"; m=json.loads(p.read_text()); assert m.get("schema")==1, "Invalid public install receipt"; a=pathlib.Path(m["assets_root"]); assert a.is_absolute() and ".." not in a.parts and not any(q.is_symlink() for q in (a,*a.parents)), "Public assets must be an ordinary absolute folder"; assert (a/"Environment").is_dir() and (a/"xpromoSupport").is_dir(), "Public assets are missing; rerun START_MAC.command"; print(a)' "$PUBLIC_INSTALL")" || exit 2
    export FARMVILLAGE_ASSETS_DIR
elif [ -f "$SCRIPT_DIR/../Runtime/PREPARED_RUNTIME.json" ]; then
    echo '[FarmVillage] The public-install asset receipt is missing. Run START_MAC.command again; no archive will be downloaded by Start.' >&2
    exit 2
fi
exec "$PYTHON" -I -B -u "$ADAPTER_DIR/bootstrap.py" "${ARGS[@]}"
