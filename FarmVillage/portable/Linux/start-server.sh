#!/usr/bin/env bash
# Start the separately packaged LAN adapter beside the accepted game release.
set -euo pipefail

adapter_root="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
test_root="$(CDPATH= cd -- "$adapter_root/.." && pwd)"
game_release="$test_root/release/farmvillage-portable-preparation-1acf91b47487"
bind_address="${1:-192.168.50.80}"
bind_port="${2:-5501}"
if (( $# >= 2 )); then
    shift 2
elif (( $# == 1 )); then
    shift
fi

if [[ ! -x "$game_release/.venv/bin/python" ]]; then
    printf 'The installed game environment is missing: %s\n' "$game_release/.venv/bin/python" >&2
    exit 1
fi

cd -- "$adapter_root"
sha256sum --quiet -c SHA256SUMS

exec "$game_release/.venv/bin/python" -B -u "$adapter_root/server_runner.py" \
    --runtime "$game_release/Runtime" \
    --data-dir "$test_root/data" \
    --bind "$bind_address" \
    --port "$bind_port" \
    --public-url "http://$bind_address:$bind_port" \
    --integration-module-file "$adapter_root/GodBarn/integration.py" "$@"
