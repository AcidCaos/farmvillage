#!/usr/bin/env bash
# Install the LAN host as this user's persistent Ubuntu service.
set -euo pipefail
umask 0077

managed_marker='# Managed by FarmVillage LAN hosting (install-service.sh)'
unit_name='farmvillage.service'

usage() {
    printf 'Usage: bash install-service.sh [PRIVATE_IP [PORT]]\n'
    printf '       bash install-service.sh --remove\n'
    printf 'Install for the current Ubuntu user, or remove this managed service.\n'
}

case "${1:-}" in
    -h|--help) usage; exit 0 ;;
esac
if [[ "$(uname -s)" != Linux ]]; then
    printf 'Run this installer on Ubuntu, as the user who owns the game files.\n' >&2
    exit 1
fi
if [[ "$(id -u)" == 0 ]]; then
    printf 'Run without sudo. The installer requests sudo only to enable startup at boot.\n' >&2
    exit 1
fi
for dependency in systemctl loginctl; do
    if ! command -v "$dependency" >/dev/null; then
        printf 'Required Ubuntu command is missing: %s\n' "$dependency" >&2
        exit 1
    fi
done

service_user="$(id -un)"
adapter_root="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
test_root="$(CDPATH= cd -- "$adapter_root/.." && pwd)"
game_python="$test_root/release/farmvillage-portable-preparation-1acf91b47487/.venv/bin/python"
unit_directory="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
unit_path="$unit_directory/$unit_name"

# Never replace another service or follow a unit symlink when writing/removing.
if [[ -e "$unit_path" || -L "$unit_path" ]]; then
    if [[ -L "$unit_path" || ! -f "$unit_path" ]] || ! grep -Fxq "$managed_marker" "$unit_path"; then
        printf 'An unrelated unit already exists at %s. It has been left alone.\n' "$unit_path" >&2
        exit 1
    fi
fi
loaded_unit="$(systemctl --user show "$unit_name" --property=FragmentPath --value 2>/dev/null || true)"
if [[ -n "$loaded_unit" && "$loaded_unit" != "$unit_path" ]]; then
    printf 'Another FarmVillage unit is loaded from %s. It has been left alone.\n' "$loaded_unit" >&2
    exit 1
fi

if [[ "${1:-}" == --remove ]]; then
    if [[ $# != 1 ]]; then usage >&2; exit 1; fi
    if [[ ! -f "$unit_path" ]]; then
        printf 'No managed FarmVillage service is installed.\n'
        exit 0
    fi
    systemctl --user disable --now "$unit_name"
    rm -- "$unit_path"
    systemctl --user daemon-reload
    systemctl --user reset-failed "$unit_name" 2>/dev/null || true
    printf 'FarmVillage service removed. Your farms, password, and game files are untouched.\n'
    printf 'User lingering remains enabled because other services may use it.\n'
    exit 0
fi

if [[ $# -gt 2 || "${1:-}" == --* ]]; then usage >&2; exit 1; fi
bind_address="${1:-192.168.50.80}"
bind_port="${2:-5501}"
if [[ ! -x "$game_python" ]]; then
    printf 'The installed game environment is missing: %s\n' "$game_python" >&2
    exit 1
fi
if [[ "$adapter_root" == *$'\n'* || "$adapter_root" == *$'\r'* ]]; then
    printf 'The hosting folder path must not contain a newline.\n' >&2
    exit 1
fi

# A previously installed managed instance may hold the data lock. Never stop an
# unknown foreground process: the runner and port probe below report that case.
temporary_unit=''
previously_active=0
unit_published=0
cleanup() {
    local exit_status=$?
    if [[ -n "$temporary_unit" ]]; then rm -f -- "$temporary_unit"; fi
    if [[ "$exit_status" != 0 && "$previously_active" == 1 && "$unit_published" == 0 ]]; then
        printf 'Installation stopped before replacing the unit; restarting the previously managed service.\n' >&2
        systemctl --user start "$unit_name" || printf 'Restart failed. Inspect: journalctl --user -u %s -n 50 --no-pager\n' "$unit_name" >&2
    fi
    return "$exit_status"
}
trap cleanup EXIT
if [[ -f "$unit_path" ]]; then
    if systemctl --user is-active --quiet "$unit_name"; then previously_active=1; fi
    systemctl --user stop "$unit_name"
fi
printf 'Checking the game files and saved server password...\n'
bash "$adapter_root/start-server.sh" "$bind_address" "$bind_port" --init-only

"$game_python" - "$bind_address" "$bind_port" <<'PY'
import socket
import sys

address, port = sys.argv[1], int(sys.argv[2])
for host in dict.fromkeys((address, "127.0.0.1")):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(1)
        if probe.connect_ex((host, port)) == 0:
            raise SystemExit(
                f"A server is already listening at {host}:{port}. "
                "Press Control+C in its Ubuntu terminal, then run this installer again. "
                "No process has been killed.")
PY

# Make a private, separately named copy before changing service configuration.
# Assets and host credentials are deliberately outside this archive.
backup_root="$test_root/backups"
if [[ -L "$backup_root" ]]; then
    printf 'The backups folder must not be a symbolic link: %s\n' "$backup_root" >&2
    exit 1
fi
mkdir -p -- "$backup_root"
chmod 700 "$backup_root"
backup_directory="$(mktemp -d "$backup_root/pre-service-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"
printf 'Backing up saves and God Barn before installing the service...\n'
tar -czf "$backup_directory/farm-data.tar.gz.partial" -C "$test_root/data" -- saves god-barn
mv -- "$backup_directory/farm-data.tar.gz.partial" "$backup_directory/farm-data.tar.gz"
printf 'Backup saved: %s\n' "$backup_directory/farm-data.tar.gz"

# ExecStart uses systemd's quoting and percent/dollar expansion, not shell rules.
unit_argument() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    value="${value//%/%%}"
    value="${value//\$/\$\$}"
    printf '"%s"' "$value"
}

mkdir -p -- "$unit_directory"
temporary_unit="$(mktemp "$unit_directory/.farmvillage.XXXXXX")"
{
    printf '%s\n' "$managed_marker"
    printf '[Unit]\nDescription=FarmVillage private LAN game server\nStartLimitIntervalSec=0\n\n'
    printf '[Service]\nType=simple\nExecStart=/bin/bash '
    unit_argument "$adapter_root/start-server.sh"
    printf ' '
    unit_argument "$bind_address"
    printf ' '
    unit_argument "$bind_port"
    printf '\nRestart=on-failure\nRestartSec=5\nKillSignal=SIGINT\nTimeoutStopSec=60\nSendSIGKILL=no\n'
    printf 'SuccessExitStatus=130 SIGINT\nUMask=0077\nStandardOutput=journal\nStandardError=journal\n\n'
    printf '[Install]\nWantedBy=default.target\n'
} > "$temporary_unit"
chmod 600 "$temporary_unit"

if [[ "$(loginctl show-user "$service_user" --property=Linger --value 2>/dev/null || true)" != yes ]]; then
    printf 'Enabling startup at boot for %s. Ubuntu may request your sudo password.\n' "$service_user"
    sudo loginctl enable-linger "$service_user"
fi
mv -f -- "$temporary_unit" "$unit_path"
temporary_unit=''
unit_published=1
systemctl --user daemon-reload
systemctl --user enable "$unit_name"
printf 'Starting FarmVillage in the background...\n'
if ! systemctl --user start "$unit_name"; then
    systemctl --user status "$unit_name" --no-pager --full >&2 || true
    printf 'See the server log with: journalctl --user -u %s -n 50 --no-pager\n' "$unit_name" >&2
    exit 1
fi

if ! "$game_python" - "$bind_address" "$bind_port" <<'PY'
import sys
import time
import urllib.error
import urllib.request

address, port = sys.argv[1], int(sys.argv[2])
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
deadline = time.monotonic() + 120
while time.monotonic() < deadline:
    try:
        with opener.open(f"http://{address}:{port}/server-login", timeout=1) as response:
            if response.status == 200 and b"FarmVillage" in response.read(32768):
                break
    except (OSError, urllib.error.URLError):
        pass
    time.sleep(0.5)
else:
    raise SystemExit("FarmVillage has not reported ready after 120 seconds. The service was left running; check its log below before retrying installation.")
PY
then
    journalctl --user -u "$unit_name" -n 50 --no-pager >&2 || true
    exit 1
fi
printf '\nFarmVillage is running at http://%s:%s/\n' "$bind_address" "$bind_port"
printf 'You can close this terminal. The server will start when Ubuntu boots.\n'
printf 'Status:  systemctl --user status %s --no-pager\n' "$unit_name"
printf 'Logs:    journalctl --user -u %s -n 50 --no-pager\n' "$unit_name"
printf 'Restart: systemctl --user restart %s\n' "$unit_name"
printf 'Stop:    systemctl --user stop %s\n' "$unit_name"
