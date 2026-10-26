#!/usr/bin/env bash
# Run on the Mac: transfer the small host update and run one Ubuntu operation.
set -euo pipefail

case "${1:---check-saves}" in
    --install) operation=install ;;
    --check-saves) operation=check ;;
    --fresh-start) operation=fresh ;;
    *) printf 'Usage: bash manage-bifrost.sh [--install | --check-saves | --fresh-start]\n' >&2; exit 1 ;;
esac
delivery_directory="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
archive="$delivery_directory/farmvillage-lan-host.tar.gz"
checksum="$archive.sha256"
for path in "$archive" "$checksum"; do
    if [[ ! -f "$path" ]]; then printf 'Missing hosting update: %s\n' "$path" >&2; exit 1; fi
done
world_archive="$delivery_directory/farmvillage-fresh-world.tar.gz"
if [[ "$operation" == fresh ]]; then
    for path in "$world_archive" "$world_archive.sha256"; do
        if [[ ! -f "$path" ]]; then printf 'Missing fresh neighbourhood update: %s\n' "$path" >&2; exit 1; fi
    done
fi
printf 'Copying the small server update to Bifrost. SSH may ask for your Ubuntu login password.\n'
scp "$archive" "$checksum" farmvillage@192.168.50.80:/home/farmvillage/farmville-test/release/
if [[ "$operation" == fresh ]]; then
    printf 'Copying the fresh player farm and five authored resident farms.\n'
    scp "$world_archive" "$world_archive.sha256" farmvillage@192.168.50.80:/home/farmvillage/farmville-test/release/
fi
remote_prepare='cd /home/farmvillage/farmville-test/release && sha256sum -c farmvillage-lan-host.tar.gz.sha256 && tar -xzf farmvillage-lan-host.tar.gz --no-same-owner -C ..'
if [[ "$operation" == fresh ]]; then
    printf 'Resetting progress and installing the five neighbours. Close all game tabs now.\n'
    printf 'Existing farms and God Barn history will be backed up before the reset.\n'
    ssh -t farmvillage@192.168.50.80 "$remote_prepare && sha256sum -c farmvillage-fresh-world.tar.gz.sha256 && python3 -B ../hosting/install-fresh-world.py --archive farmvillage-fresh-world.tar.gz"
elif [[ "$operation" == check ]]; then
    printf 'Reading the saved farms and snapshots; this does not start or stop the server.\n'
    ssh -t farmvillage@192.168.50.80 "$remote_prepare && python3 -B ../hosting/diagnose-saves.py --runtime /home/farmvillage/farmville-test/release/farmvillage-portable-preparation-1acf91b47487/Runtime"
else
    printf 'Installing automatic startup. Close game tabs and stop the foreground server with Control+C first.\n'
    printf 'If prompted for a new browser password, type it and press Return; the characters stay hidden.\n'
    ssh -t farmvillage@192.168.50.80 "$remote_prepare && bash ../hosting/install-service.sh"
fi
