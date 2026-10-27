#!/usr/bin/env bash
# Run on the Mac. Deploy only the prepared God Barn hosting overlay.
set -euo pipefail
umask 077

barn_root="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
archive="$barn_root/.build/god-barn-catalog-recovery.tar.gz"
installer="$barn_root/scripts/install_bifrost_barn.py"
artwork_packer="$barn_root/scripts/pack_bifrost_artwork.py"
expected_sha='7ff2f6a639f08f656343f5d6b465effdecdcfb3bfc4534c5545ebc4a39067f96'
target='farmvillage@192.168.50.80'
test_root='/home/farmvillage/farmville-test'
incoming="$test_root/incoming/god-barn-$(date -u +%Y%m%dT%H%M%SZ)-$$"
remote_python="$test_root/release/farmvillage-portable-preparation-1acf91b47487/.venv/bin/python"

for path in "$archive" "$installer" "$artwork_packer"; do
    if [[ ! -f "$path" || -L "$path" ]]; then
        printf 'Missing regular God Barn deployment file: %s\n' "$path" >&2
        exit 1
    fi
done
actual_sha="$(shasum -a 256 "$archive" | awk '{print $1}')"
if [[ "$actual_sha" != "$expected_sha" ]]; then
    printf 'God Barn archive checksum does not match the reviewed update. Nothing was uploaded.\n' >&2
    exit 1
fi

printf 'God Barn update verified. Close farm/game tabs before this deployment.\n'
printf 'Uploading the Barn-only bundle. SSH may ask for your Bifrost login password.\n'
# All remote paths are fixed or generated here from a timestamp and numeric PID.
# The remote helper validates its own installation roots before any activation.
ssh -o ConnectTimeout=10 "$target" \
    "test -d '$test_root' && test ! -L '$test_root' && test ! -L '$test_root/incoming' && umask 077 && mkdir -p '$incoming'"
scp -o ConnectTimeout=10 "$archive" "$installer" "$target:$incoming/"
work_directory="$barn_root/.build/bifrost-deploy-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -m 700 "$work_directory"
printf 'Checking Bifrost’s artwork and preparing any missing images for Barn’s own folder...\n'
ssh -o ConnectTimeout=10 -o ServerAliveInterval=15 "$target" \
    "'$remote_python' -B '$incoming/install_bifrost_barn.py' --archive '$incoming/god-barn-catalog-recovery.tar.gz' --expected-sha256 '$expected_sha' --audit-artwork" \
    > "$work_directory/wanted.json"
missing_count="$(python3 -B - "$work_directory/wanted.json" <<'PY'
import json
import sys
from pathlib import Path
report = json.loads(Path(sys.argv[1]).read_text())
if report.get('schema') != 1 or not isinstance(report.get('items'), list):
    raise SystemExit('Bifrost returned an invalid artwork audit; no update was activated.')
print(len(report['items']))
PY
)"
artwork_options=''
if (( missing_count > 0 )); then
    printf 'Preparing %s missing/damaged images from the verified local Barn artwork.\n' "$missing_count"
    python3 -B "$artwork_packer" --wanted "$work_directory/wanted.json" \
        --output "$work_directory/god-barn-artwork.tar.gz"
    artwork_sha="$(shasum -a 256 "$work_directory/god-barn-artwork.tar.gz" | awk '{print $1}')"
    if [[ ! "$artwork_sha" =~ ^[0-9a-f]{64}$ ]]; then
        printf 'Invalid artwork archive digest. No update was activated.\n' >&2
        exit 1
    fi
    scp -o ConnectTimeout=10 "$work_directory/god-barn-artwork.tar.gz" "$target:$incoming/"
    artwork_options=" --artwork-archive '$incoming/god-barn-artwork.tar.gz' --artwork-sha256 '$artwork_sha'"
fi
printf 'Installing and checking the God Barn overlay; the existing service will restart briefly.\n'
ssh -o ConnectTimeout=10 -o ServerAliveInterval=15 "$target" \
    "'$remote_python' -B '$incoming/install_bifrost_barn.py' --archive '$incoming/god-barn-catalog-recovery.tar.gz' --expected-sha256 '$expected_sha'$artwork_options"
