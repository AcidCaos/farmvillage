#!/bin/bash
# Guided installer: plan and target confirmation before downloads.
set -euo pipefail
TASK_SETUP_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$(/usr/bin/uname -s)" != Darwin ]]; then
    printf 'For an Ubuntu game server, read docs/PLAY_ON_SERVER.md. This launcher is for macOS.\n'
    exit 2
fi
usable_python() {
    local candidate="$1"
    [[ -x "$candidate" ]] || return 1
    # Refuse Apple's developer-tools shim, including aliases, before execution.
    if [[ "$candidate" == /usr/bin/python3 || "$candidate" -ef /usr/bin/python3 ]]; then return 1; fi
    "$candidate" -I -S -B -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)' >/dev/null 2>&1
}
TASK_PYTHON=""
if [[ -n "${FARMVILLAGE_SETUP_PYTHON:-}" ]]; then
    if usable_python "$FARMVILLAGE_SETUP_PYTHON"; then TASK_PYTHON="$FARMVILLAGE_SETUP_PYTHON"; fi
else
    for TASK_CANDIDATE in /opt/homebrew/bin/python3 /usr/local/bin/python3 /Library/Frameworks/Python.framework/Versions/Current/bin/python3 python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
        TASK_RESOLVED="$(command -v "$TASK_CANDIDATE" 2>/dev/null || true)"
        if [[ -n "$TASK_RESOLVED" ]] && usable_python "$TASK_RESOLVED"; then TASK_PYTHON="$TASK_RESOLVED"; break; fi
    done
fi
if [[ -z "$TASK_PYTHON" ]]; then
    printf '\nFarmVillage — Mac player setup\n\n'
    printf 'An existing Python interpreter is needed before the installer can start.\nNothing has been downloaded, installed or built.\n\n'
    printf 'The installer needs an installed Python 3.10+. Read docs/PLAY_ON_MAC.md now without installing anything.\n'
    printf 'If you choose to install Python, use python.org, then reopen this installer.\n'
    printf 'For a custom interpreter, set FARMVILLAGE_SETUP_PYTHON to its full path. The Apple /usr/bin/python3 shim is not launched.\n'
    printf '\nGuide: %s/docs/PLAY_ON_MAC.md\n' "$TASK_SETUP_DIR"
    if [[ -t 0 ]]; then read -r -p 'Press Return to close. ' TASK_CLOSE; fi
    exit 2
fi
exec "$TASK_PYTHON" -I -S -B "$TASK_SETUP_DIR/tools/player-setup.py" --audience mac "$@"
