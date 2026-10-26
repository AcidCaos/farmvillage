#!/usr/bin/env bash
set -euo pipefail
FV_SETUP_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# Public source copies open the guided resource and player installer.
# Complete prepared bundles keep the separately documented eight-step installer.
if [[ -f "$FV_SETUP_DIR/PrivateInputs.expected.json" && -f "$FV_SETUP_DIR/tools/player-setup.py" ]]; then
  if [[ "$(uname -s)" == Darwin ]]; then
    exec /bin/bash "$FV_SETUP_DIR/START_MAC.command" "$@"
  fi
  if ! command -v python3 >/dev/null || ! python3 -I -B -c 'import sys; assert sys.version_info >= (3, 10)' >/dev/null 2>&1; then
    printf 'The server installer needs an existing Python 3.10+. Nothing was installed or downloaded. Read docs/PLAY_ON_SERVER.md for the setup prerequisites.\n' >&2
    exit 2
  fi
  exec python3 -I -B "$FV_SETUP_DIR/tools/player-setup.py" --audience server "$@"
fi
if [[ "$(uname -s)" != Linux ]]; then
  printf 'Run this guide on the Ubuntu/Linux game host. macOS players should read docs/PLAY_ON_MAC.md and use START_MAC.command. Nothing is deployed remotely.\n' >&2
  exit 2
fi
if [[ -f "$FV_SETUP_DIR/SHA256SUMS" ]]; then
  printf 'Checking the complete private bundle before setup...\n'
  if ! command -v sha256sum >/dev/null; then
    printf 'Install Ubuntu coreutils (sudo apt install coreutils), then rerun this same entry. No game data has changed.\n' >&2
    exit 2
  fi
  if ! (cd -- "$FV_SETUP_DIR" && sha256sum --quiet -c SHA256SUMS); then
    printf "Some bundle files are missing or different. Extract the complete matching private ZIP again, then rerun this same entry. No installation data has changed.\n" >&2
    exit 2
  fi
fi
if ! command -v python3 >/dev/null || ! python3 -c 'import sys, venv, ensurepip; assert sys.version_info >= (3,10)' >/dev/null 2>&1; then
  printf 'A few Ubuntu tools are needed first. Run:\n\n  sudo apt update\n  sudo apt install python3 python3-venv python3-pip\n\nThen run this same START_HERE.sh again. No game files have changed.\n' >&2
  exit 2
fi
if [[ -f "$FV_SETUP_DIR/setup-wizard.py" ]]; then
  exec python3 -I -B "$FV_SETUP_DIR/setup-wizard.py"
fi
exec python3 -I -B "$FV_SETUP_DIR/tools/setup-wizard.py"
