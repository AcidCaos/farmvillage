#!/usr/bin/env python3
"""Read-only farm and host inventory; never import or start the game server."""

from __future__ import annotations

import argparse
import datetime
import grp
import json
import os
from pathlib import Path
import pwd
import shlex
import shutil
import stat
import subprocess
import sys


MAX_JSON_BYTES = 64 * 1024 * 1024
PROCESS_FIELDS = ("--runtime", "--data-dir", "--bind", "--port", "--public-url")


def quoted(value, limit=200):
    """Keep user-authored names on one terminal line and bound their length."""
    text = str(value)
    return ascii(text[:limit] + ("..." if len(text) > limit else ""))


def utc(timestamp):
    return datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc).isoformat(timespec="seconds")


class Inventory:
    def __init__(self, output=None):
        self.output = output if output is not None else sys.stdout
        self.errors = 0

    def print(self, text=""):
        print(text, file=self.output)

    def error(self, path, message):
        self.errors += 1
        self.print(f"ERROR {quoted(path)}: {message}")

    def metadata(self, path, *, missing_ok=False):
        try:
            info = path.lstat()
        except FileNotFoundError:
            if missing_ok:
                self.print(f"Absent: {quoted(path)}")
            else:
                self.error(path, "does not exist")
            return None
        except OSError as error:
            self.error(path, str(error))
            return None
        try:
            owner = pwd.getpwuid(info.st_uid).pw_name
        except KeyError:
            owner = str(info.st_uid)
        try:
            group = grp.getgrgid(info.st_gid).gr_name
        except KeyError:
            group = str(info.st_gid)
        self.print(
            f"Path: {quoted(path)} mode={stat.filemode(info.st_mode)} "
            f"owner={quoted(owner)} group={quoted(group)} "
            f"readable={os.access(path, os.R_OK)} writable={os.access(path, os.W_OK)}"
        )
        if stat.S_ISLNK(info.st_mode):
            self.error(path, "symlink; not inspected")
            return None
        return info

    def entries(self, directory, *, missing_ok=False):
        info = self.metadata(directory, missing_ok=missing_ok)
        if info is None:
            return []
        if not stat.S_ISDIR(info.st_mode):
            self.error(directory, "expected a directory")
            return []
        try:
            return sorted(directory.iterdir())
        except OSError as error:
            self.error(directory, str(error))
            return []

    def farm(self, path, *, snapshot=False):
        try:
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode):
                self.error(path, "not an ordinary file; not inspected")
                return
            if info.st_size > MAX_JSON_BYTES:
                self.error(path, "larger than 64 MiB; not inspected")
                return
            record = json.loads(path.read_text(encoding="utf-8"))
            save = record.get("save") if snapshot else record
            user = save["userInfo"]
            player = user["player"]
            objects = save["world"]["objectsArray"]
            if not isinstance(objects, list):
                raise TypeError("world.objectsArray is not a list")
            numbers = " ".join(
                f"{label}={player.get(key) if isinstance(player.get(key), (int, float)) and not isinstance(player.get(key), bool) else 'invalid'}"
                for label, key in (("XP", "xp"), ("coins", "gold"), ("cash", "cash"))
            )
            self.print(
                f"File={quoted(path.name)} modified_UTC={utc(info.st_mtime)} "
                f"UID={quoted(player.get('userId'), 128)} "
                f"name={quoted(user['attr'].get('name'))} {numbers} objects={len(objects)}"
            )
            if snapshot:
                self.print(
                    f"  snapshot_created={quoted(record.get('created'))} "
                    f"label={quoted(record.get('label'))}"
                )
        except (OSError, UnicodeError, ValueError, KeyError, TypeError, AttributeError) as error:
            self.error(path, f"cannot inspect ({type(error).__name__})")

    def saves(self, directory, *, missing_ok=False):
        entries = self.entries(directory, missing_ok=missing_ok)
        farms = [path for path in entries if not path.name.startswith((".", "~"))
                 and path.name.lower().endswith(".json")
                 and not path.name.lower().endswith((".bak.json", ".backup.json", ".tmp.json"))]
        self.print(f"Farm files: {len(farms)}")
        for path in farms:
            self.farm(path)
        for name in (".save-transactions", ".transactions"):
            pending = self.entries(directory / name, missing_ok=True)
            self.print(f"Pending transaction entries: {len(pending)} in {quoted(name)}")
            if pending:
                for path in pending[:20]:
                    self.print(f"  {quoted(path.name)}")
                if len(pending) > 20:
                    self.print("  Additional entries omitted.")

    def snapshots(self, directory):
        entries = self.entries(directory, missing_ok=True)
        candidates = []
        for path in entries:
            if not path.name.lower().endswith(".json") or path.name.startswith("."):
                continue
            try:
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode):
                    self.error(path, "not an ordinary snapshot file; not inspected")
                    continue
                candidates.append((info.st_mtime, path))
            except OSError as error:
                self.error(path, str(error))
        self.print(f"Snapshot files: {len(candidates)}; displaying latest 20")
        for _, path in sorted(candidates, key=lambda entry: (entry[0], entry[1].name), reverse=True)[:20]:
            self.farm(path, snapshot=True)

    def processes(self):
        self.print("\nRUNNING GAME PROCESSES (selected arguments only)")
        try:
            result = subprocess.run(
                ["pgrep", "-af", "server_runner[.]py"], capture_output=True,
                text=True, timeout=5, check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            self.print(f"Process inventory unavailable ({type(error).__name__}).")
            return
        if result.returncode not in (0, 1):
            self.print("Process inventory unavailable: pgrep failed.")
            return
        found = False
        for line in result.stdout.splitlines():
            try:
                pid, arguments = line.split(" ", 1)
                tokens = shlex.split(arguments)
            except ValueError:
                continue
            runner = next((token for token in tokens if Path(token).name == "server_runner.py"), None)
            if not pid.isdigit() or runner is None:
                continue
            found = True
            self.print(f"PID={pid} runner={quoted(runner)}")
            for index, token in enumerate(tokens):
                if token in PROCESS_FIELDS and index + 1 < len(tokens):
                    self.print(f"  {token}={quoted(tokens[index + 1])}")
                elif token.split("=", 1)[0] in PROCESS_FIELDS and "=" in token:
                    key, value = token.split("=", 1)
                    self.print(f"  {key}={quoted(value)}")
        if not found:
            self.print("No matching game process found.")

    def service_log(self):
        self.print("\nMANAGED SERVICE LOG (explicitly requested)")
        try:
            exists = subprocess.run(
                ["systemctl", "--user", "show", "farmvillage.service", "--property=LoadState", "--value"],
                capture_output=True, text=True, timeout=5, check=False,
            )
            if exists.returncode or exists.stdout.strip() in ("", "not-found"):
                self.print("No accessible user farmvillage.service was found.")
                return
            result = subprocess.run(
                ["journalctl", "--user", "-u", "farmvillage.service", "-n", "40", "--no-pager"],
                capture_output=True, text=True, timeout=10, check=False,
            )
            if result.returncode:
                self.print("The service journal is unavailable.")
                return
            self.print(result.stdout.rstrip())
        except (OSError, subprocess.SubprocessError) as error:
            self.print(f"Service log unavailable ({type(error).__name__}).")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("/home/farmvillage/farmville-test/data"))
    parser.add_argument("--runtime", type=Path, help="Also inspect Runtime/saves for a previous launch using the wrong data folder.")
    parser.add_argument("--service-log", action="store_true", help="Include the latest 40 lines from the user farmvillage.service journal, if present.")
    args = parser.parse_args(argv)
    inventory = Inventory()
    try:
        root = args.data_dir.expanduser().resolve()
    except (OSError, RuntimeError) as error:
        inventory.error(args.data_dir, str(error))
        return 1
    inventory.print("FarmVillage read-only save inventory")
    inventory.print(f"Current UTC: {utc(datetime.datetime.now(datetime.timezone.utc).timestamp())}")
    inventory.metadata(root)
    try:
        disk = shutil.disk_usage(root)
        inventory.print(f"Disk free: {disk.free / 1024 ** 3:.2f} GiB; total: {disk.total / 1024 ** 3:.2f} GiB")
    except OSError as error:
        inventory.error(root, f"cannot read free space ({type(error).__name__})")
    inventory.print("\nCURRENT SAVES")
    inventory.saves(root / "saves")
    inventory.print("\nGOD BARN SNAPSHOTS")
    inventory.snapshots(root / "god-barn" / "snapshots")
    if args.runtime:
        inventory.print("\nALTERNATE RUNTIME SAVE FOLDER")
        try:
            inventory.saves(args.runtime.expanduser().resolve() / "saves", missing_ok=True)
        except (OSError, RuntimeError) as error:
            inventory.error(args.runtime, str(error))
    inventory.processes()
    if args.service_log:
        inventory.service_log()
    inventory.print(f"\nFinished; inspection errors: {inventory.errors}. No files were changed.")
    return 1 if inventory.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
