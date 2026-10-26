#!/usr/bin/env bash
# Run on the Mac: send this folder's Bifrost update and run one Ubuntu step.
#   --check-saves  (default) read-only: list farms, snapshots and free space.
#   --install      unpack the new game version, back up saves and God Barn
#                  history, then restart the background service on it.
set -euo pipefail

usage() { printf 'Usage: bash manage-bifrost.sh [--check-saves | --install]\n'; }
case "${1:---check-saves}" in
    --check-saves) operation=check ;;
    --install) operation=install ;;
    *) usage >&2; exit 1 ;;
esac
if (( $# > 1 )); then usage >&2; exit 1; fi

target='farmvillage@192.168.50.80'
test_root='/home/farmvillage/farmville-test'
previous_runtime="$test_root/release/farmvillage-portable-preparation-1acf91b47487/Runtime"
delivery_directory="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
host_archive="$delivery_directory/farmvillage-lan-host.tar.gz"

shopt -s nullglob
bundles=("$delivery_directory"/farmvillage-portable-preparation-*.tar.gz)
shopt -u nullglob
if (( ${#bundles[@]} != 1 )); then
    printf 'Expected exactly one game bundle in %s, found %s.\n' "$delivery_directory" "${#bundles[@]}" >&2
    exit 1
fi
bundle="${bundles[0]}"
bundle_name="$(basename -- "$bundle")"
if [[ ! "$bundle_name" =~ ^farmvillage-portable-preparation-[0-9a-f]{12}\.tar\.gz$ ]]; then
    printf 'Unexpected game bundle name: %s\n' "$bundle_name" >&2
    exit 1
fi
for path in "$host_archive" "$host_archive.sha256" "$bundle" "$bundle.sha256"; do
    if [[ ! -f "$path" ]]; then printf 'Missing update file: %s\n' "$path" >&2; exit 1; fi
done

printf 'Checking the update files on this Mac...\n'
(
    cd -- "$delivery_directory"
    shasum -a 256 -c farmvillage-lan-host.tar.gz.sha256
    if [[ "$operation" == install ]]; then shasum -a 256 -c "$bundle_name.sha256"; fi
)

remote_check="cd $test_root/release && sha256sum -c farmvillage-lan-host.tar.gz.sha256"
remote_check+=' && stage="$(mktemp -d)" && { tar -xzf farmvillage-lan-host.tar.gz --no-same-owner -C "$stage"'
remote_check+=" && python3 -B \"\$stage/hosting/diagnose-saves.py\" --runtime $previous_runtime"
remote_check+='; status=$?; rm -rf -- "$stage"; exit "$status"; }'

remote_install="cd $test_root/release && sha256sum -c farmvillage-lan-host.tar.gz.sha256"
remote_install+=" && sha256sum -c $bundle_name.sha256"
remote_install+=' && stage="$(mktemp -d ./.hosting-stage-XXXXXX)" && { tar -xzf farmvillage-lan-host.tar.gz --no-same-owner -C "$stage"'
remote_install+=' && (cd "$stage/hosting" && sha256sum --quiet -c SHA256SUMS)'
remote_install+=" && bash \"\$stage/hosting/activate-release.sh\" $test_root/release $bundle_name"
remote_install+='; status=$?; rm -rf -- "$stage"; test "$status" = 0; }'
remote_install+=' && tar -xzf farmvillage-lan-host.tar.gz --no-same-owner -C .. && bash ../hosting/install-service.sh'

if [[ "$operation" == check ]]; then
    printf 'Copying the small hosting file to Bifrost. SSH may ask for your Ubuntu login password.\n'
    scp "$host_archive" "$host_archive.sha256" "$target:$test_root/release/"
    printf 'Reading the saved farms and snapshots; this does not start, stop or change the game.\n'
    ssh -t "$target" "$remote_check"
else
    printf 'Copying the new game version and hosting files to Bifrost. SSH may ask for your Ubuntu login password.\n'
    scp "$host_archive" "$host_archive.sha256" "$bundle" "$bundle.sha256" "$target:$test_root/release/"
    printf 'Installing. Close game tabs and stop any foreground server with Control+C first.\n'
    printf 'Saves and God Barn history are backed up before the service restarts.\n'
    printf 'If prompted for a new browser password, type it and press Return; the characters stay hidden.\n'
    ssh -t "$target" "$remote_install"
fi
