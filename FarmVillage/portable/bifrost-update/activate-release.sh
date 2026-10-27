#!/usr/bin/env bash
# Run on Bifrost: unpack a checksum-verified game bundle beside the previous
# release and give it a copy of the previous release's Python environment.
# It never touches saves, God Barn history, the hosting folder or the service,
# and it never deletes or edits the previous release.
set -euo pipefail
umask 0077

previous='farmvillage-portable-preparation-1acf91b47487'

usage() {
    printf 'Usage: bash activate-release.sh RELEASE_FOLDER farmvillage-portable-preparation-<id>.tar.gz\n'
}
fail() {
    printf 'Game update stopped: %s\n' "$1" >&2
    printf 'Nothing in the running game, saves or God Barn history was changed.\n' >&2
    exit 1
}
if [[ $# != 2 ]]; then usage >&2; exit 1; fi
if [[ "$(id -u)" == 0 ]]; then fail 'run without sudo, as the user who owns the game files.'; fi

release_root="$1"
bundle="$2"
if [[ ! "$bundle" =~ ^(farmvillage-portable-preparation-[0-9a-f]{12})\.tar\.gz$ ]]; then
    fail "unexpected bundle name: $bundle"
fi
release="${BASH_REMATCH[1]}"
if [[ -L "$release_root" || ! -d "$release_root" ]]; then fail "missing release folder: $release_root"; fi
cd -- "$release_root"
for path in "$bundle" "$bundle.sha256"; do
    if [[ -L "$path" || ! -f "$path" ]]; then fail "missing file: $path"; fi
done
read -r _ recorded_name _extra < "$bundle.sha256" || true
if [[ "$recorded_name" != "$bundle" ]]; then fail "the checksum file does not name $bundle."; fi
printf 'Checking the game bundle checksum...\n'
sha256sum --quiet -c -- "$bundle.sha256" || fail 'the game bundle checksum does not match.'

check_environment() {
    # The bundle's Python requirements are unchanged from the previous release.
    "$1/.venv/bin/python" -B -c 'import flask, pyamf, requests, tqdm, xmltodict' \
        || fail "the Python environment in $1 cannot load the game's libraries."
}

if [[ -e "$release" || -L "$release" ]]; then
    if [[ -L "$release" || ! -d "$release" ]]; then fail "$release exists but is not an ordinary folder."; fi
    (cd -- "$release" && sha256sum --quiet -c SHA256SUMS) \
        || fail "$release already exists and differs from this bundle. It has been left alone."
    if [[ ! -x "$release/.venv/bin/python" ]]; then fail "$release has no Python environment."; fi
    check_environment "$release"
    printf 'The new game version is already unpacked and verified: %s\n' "$release"
    exit 0
fi

if [[ ! -x "$previous/.venv/bin/python" ]]; then fail "the previous Python environment is missing: $previous/.venv"; fi
stage="$(mktemp -d "./.unpack-$release-XXXXXX")"
trap 'rm -rf -- "$stage"' EXIT
printf 'Unpacking the new game version beside the current one...\n'
tar -xzf "$bundle" --no-same-owner -C "$stage"
if [[ "$(ls -A -- "$stage")" != "$release" ]]; then fail 'the bundle does not contain exactly one release folder.'; fi
if [[ -n "$(find "$stage" -type l -print -quit)" ]] || [[ -n "$(find "$stage" ! -type f ! -type d -print -quit)" ]]; then
    fail 'the bundle contains links or special files.'
fi
(cd -- "$stage/$release" && sha256sum --quiet -c SHA256SUMS) || fail 'an unpacked file failed its checksum.'
printf 'Copying the Python environment from %s...\n' "$previous"
cp -a -- "$previous/.venv" "$stage/$release/.venv"
check_environment "$stage/$release"
mv -- "$stage/$release" "$release"
check_environment "$release"
printf 'New game version ready: %s/%s\n' "$(pwd)" "$release"
printf 'The previous version is kept: %s/%s\n' "$(pwd)" "$previous"
