#!/usr/bin/env python3
"""Install one reviewed fresh neighborhood once, preserving the previous world."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time


SERVICE_MARKER = "# Managed by FarmVillage LAN hosting (install-service.sh)"
APPLIED_MARKER = "fresh-world-installed.json"
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
WORLD_NAMES = ("saves", "god-barn", "neighborhood")
SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


class World:
    def __init__(self, manifest, files):
        self.manifest = manifest
        self.files = files

    @property
    def update_id(self):
        return self.manifest["updateId"]


def json_object(contents, description):
    try:
        result = json.loads(contents)
    except (ValueError, UnicodeError) as error:
        raise ValueError(f"Invalid JSON in {description}.") from error
    if not isinstance(result, dict):
        raise ValueError(f"Expected a JSON object in {description}.")
    return result


def validate_archive(archive):
    """Read the small payload manually; no archive paths are ever extracted."""
    files = {}
    seen = set()
    total = 0
    directories = {"world", "world/saves", "world/neighborhood", "world/neighborhood/templates"}
    with tarfile.open(archive, "r:gz") as source:
        for member in source:
            name = member.name.rstrip("/")
            path = PurePosixPath(name)
            if (not name or path.is_absolute() or ".." in path.parts or
                    str(path) != name or name in seen):
                raise ValueError("The fresh-world archive has an unsafe or duplicate path.")
            seen.add(name)
            if member.isdir() and name in directories:
                continue
            allowed = (name in {"world/neighborhood/manifest.json", "world/neighborhood/templates/initial.json",
                                "SHA256SUMS", "world/SHA256SUMS"} or
                       (path.parent == PurePosixPath("world/saves") and path.name.endswith(".save.json")))
            if not allowed or not member.isfile() or member.size < 0 or member.size > MAX_FILE_BYTES:
                raise ValueError(f"Unexpected archive entry: {name!r}.")
            total += member.size
            if total > MAX_ARCHIVE_BYTES:
                raise ValueError("The fresh-world payload is unexpectedly large.")
            contents = source.extractfile(member).read(MAX_FILE_BYTES + 1)
            if len(contents) != member.size:
                raise ValueError(f"Incomplete archive member: {name!r}.")
            files[name] = contents
    manifest_name = "world/neighborhood/manifest.json"
    if manifest_name not in files:
        raise ValueError("The fresh-world manifest is missing.")
    manifest = json_object(files[manifest_name], "neighborhood manifest")
    if manifest.get("schemaVersion") != 1 or isinstance(manifest.get("schemaVersion"), bool):
        raise ValueError("Unsupported fresh-world manifest schema.")
    update_id = manifest.get("updateId")
    if not isinstance(update_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", update_id):
        raise ValueError("Invalid fresh-world updateId.")
    player = manifest.get("playerUid")
    residents = manifest.get("residents")
    if not isinstance(player, str) or not SAFE_ID.fullmatch(player) or not isinstance(residents, list) or len(residents) != 5:
        raise ValueError("The fresh world must contain one player and five neighbors.")
    ids = [player]
    for resident in residents:
        if (not isinstance(resident, dict) or not isinstance(resident.get("uid"), str) or
                not SAFE_ID.fullmatch(resident["uid"]) or
                any(not isinstance(resident.get(key), str) or not resident[key].strip() for key in ("name", "theme"))):
            raise ValueError("Invalid neighbor record in the manifest.")
        ids.append(resident["uid"])
    if len(set(ids)) != 6:
        raise ValueError("The fresh-world player and neighbor IDs must be distinct.")
    expected_saves = {uid: f"{uid}.save.json" for uid in ids}
    if manifest.get("saveFiles") != expected_saves:
        raise ValueError("Manifest saveFiles must map all six IDs to their own save filename.")
    expected = {manifest_name, "world/neighborhood/templates/initial.json"}
    expected.update("world/saves/" + name for name in expected_saves.values())
    checksum_names = {name for name in files if name in ("SHA256SUMS", "world/SHA256SUMS")}
    if set(files) - checksum_names != expected or len(checksum_names) > 1:
        raise ValueError("The fresh world must contain exactly six saves, its manifest, and the initial template.")
    for uid, name in expected_saves.items():
        save = json_object(files["world/saves/" + name], name)
        try:
            valid = save["userInfo"]["player"]["userId"] == uid and isinstance(save["world"]["objectsArray"], list)
        except (KeyError, TypeError):
            valid = False
        if not valid:
            raise ValueError(f"Save identity or world is invalid: {name!r}.")
    json_object(files["world/neighborhood/templates/initial.json"], "initial template")
    if ("initialTemplateSha256" in manifest and manifest["initialTemplateSha256"] !=
            hashlib.sha256(files["world/neighborhood/templates/initial.json"]).hexdigest()):
        raise ValueError("Initial template checksum mismatch.")
    if "saveSha256" in manifest:
        hashes = manifest["saveSha256"]
        if not isinstance(hashes, dict) or set(hashes) != set(expected_saves.values()):
            raise ValueError("Manifest saveSha256 must describe every save.")
        for name, digest in hashes.items():
            if digest != hashlib.sha256(files["world/saves/" + name]).hexdigest():
                raise ValueError(f"Save checksum mismatch: {name!r}.")
    if checksum_names:
        checksum_name = checksum_names.pop()
        checked = set()
        for line in files[checksum_name].decode("ascii").splitlines():
            match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](.+)", line)
            if not match:
                raise ValueError("Invalid internal SHA256SUMS.")
            digest, name = match.groups()
            if checksum_name.startswith("world/") and not name.startswith("world/"):
                name = "world/" + name
            if name not in expected or name in checked or hashlib.sha256(files[name]).hexdigest() != digest.lower():
                raise ValueError("An internal fresh-world checksum does not match.")
            checked.add(name)
        if checked != expected:
            raise ValueError("Internal SHA256SUMS does not cover the complete fresh world.")
    return World(manifest, {name: files[name] for name in expected})


def ordinary_directory(path, *, create=False):
    if path.is_symlink():
        raise RuntimeError(f"A deployment folder must not be a symbolic link: {path}")
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not path.is_dir():
        raise RuntimeError(f"Expected an ordinary deployment folder: {path}")


def verify_owner(pid, hosting, data, *, proc_root=Path("/proc")):
    """Confirm this user's exact Python LAN runner and configured data root."""
    process = proc_root / str(pid)
    if pid <= 1 or pid == os.getpid() or process.stat().st_uid != os.getuid():
        raise RuntimeError("The data owner is not an eligible runner belonging to this user.")
    tokens = process.joinpath("cmdline").read_bytes().decode().rstrip("\0").split("\0")
    runner = str(hosting / "server_runner.py")
    if (not tokens or not Path(tokens[0]).name.startswith("python") or tokens.count(runner) != 1 or
            any(token in ("-c", "-m") for token in tokens[:tokens.index(runner)])):
        raise RuntimeError("The data owner is not the expected LAN runner; no process was stopped.")
    options = {}
    for index, token in enumerate(tokens):
        if token.startswith("--data-dir="):
            options.setdefault("--data-dir", []).append(token.split("=", 1)[1])
        elif token == "--data-dir" and index + 1 < len(tokens):
            options.setdefault("--data-dir", []).append(tokens[index + 1])
    values = options.get("--data-dir", [])
    if len(values) != 1 or Path(values[0]).resolve() != data.resolve():
        raise RuntimeError("The runner's data folder does not match; no process was stopped.")


def interrupt_owner(pid, hosting, data):
    # A pidfd prevents PID reuse from redirecting the signal to another process.
    if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        raise RuntimeError("Stop the foreground server with Control+C, then run the installer again.")
    descriptor = os.pidfd_open(pid)
    try:
        verify_owner(pid, hosting, data)
        signal.pidfd_send_signal(descriptor, signal.SIGINT)
    finally:
        os.close(descriptor)


class ManagedService:
    def __init__(self):
        self.unit = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "systemd/user/farmvillage.service"

    def stop_if_owned(self):
        if self.unit.is_symlink() or not self.unit.is_file() or self.unit.stat().st_uid != os.getuid():
            return False
        if SERVICE_MARKER not in self.unit.read_text().splitlines():
            return False
        try:
            result = subprocess.run(["systemctl", "--user", "show", "farmvillage.service", "--property=FragmentPath", "--value"],
                                    capture_output=True, text=True, timeout=5, check=False)
        except OSError:
            return False
        if result.returncode or result.stdout.strip() != str(self.unit):
            return False
        subprocess.run(["systemctl", "--user", "stop", "farmvillage.service"], check=True, timeout=70)
        return True


def open_lock(path):
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise RuntimeError(f"A deployment lock must be an ordinary file: {path}")
    return descriptor


@contextmanager
def world_lock(data, hosting, *, service=None, inspector=verify_owner, interrupt=interrupt_owner, timeout=60):
    state = data / ".lan-server"
    ordinary_directory(state, create=True)
    descriptor = open_lock(state / "owner.lock")
    service = service if service is not None else ManagedService()
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raw = os.read(descriptor, 64).strip()
            if not raw.isdigit():
                raise RuntimeError("The active data owner has no readable PID; stop the foreground server before retrying.")
            pid = int(raw)
            inspector(pid, hosting, data)
            print(f"[FarmVillage] Gracefully stopping the verified LAN runner (PID {pid}).", flush=True)
            if not service.stop_if_owned():
                interrupt(pid, hosting, data)
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("The old server is still finishing requests. Nothing was replaced; wait and retry.")
                    time.sleep(0.1)
        else:
            # Prevent a managed restart from racing the directory swap.
            service.stop_if_owned()
        yield state
    finally:
        os.close(descriptor)


def fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_private(path, contents):
    with path.open("xb") as output:
        os.chmod(path, 0o600)
        output.write(contents)
        output.flush()
        os.fsync(output.fileno())


def atomic_marker(path, contents):
    descriptor, temporary = tempfile.mkstemp(prefix=".fresh-world-marker-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(contents)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def backup_world(data):
    root = data.parent / "backups"
    ordinary_directory(root, create=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = Path(tempfile.mkdtemp(prefix=f"pre-fresh-world-{stamp}-", dir=root))
    if backup.stat().st_dev != data.stat().st_dev:
        raise RuntimeError("The backup and data folders must share a filesystem for a safe directory swap.")
    archive = backup / "farm-data.tar.gz"
    with archive.open("xb") as raw:
        os.chmod(archive, 0o600)
        with tarfile.open(fileobj=raw, mode="w:gz", dereference=False) as output:
            for name in WORLD_NAMES:
                path = data / name
                if path.exists():
                    output.add(path, arcname=name)
        raw.flush()
        os.fsync(raw.fileno())
    fsync_directory(backup)
    fsync_directory(root)
    print(f"[FarmVillage] Previous world backed up at {archive}", flush=True)
    return backup


def apply_world(world, data, state):
    for name in WORLD_NAMES:
        if (data / name).exists() or (data / name).is_symlink():
            ordinary_directory(data / name)
    marker = state / APPLIED_MARKER
    if marker.is_symlink() or (marker.exists() and not marker.is_file()):
        raise RuntimeError("The fresh-world marker must be an ordinary file.")
    previous_marker = marker.read_bytes() if marker.exists() else None
    if previous_marker and json_object(previous_marker, "installed-world marker").get("updateId") == world.update_id:
        print("[FarmVillage] This fresh-world update is already installed; keeping all current progress.", flush=True)
        return None
    backup = backup_world(data)
    previous = backup / "previous-directories"
    previous.mkdir(mode=0o700)
    fsync_directory(backup)
    with tempfile.TemporaryDirectory(prefix=".fresh-world-stage-", dir=data) as temporary:
        stage = Path(temporary)
        for name in WORLD_NAMES:
            (stage / name).mkdir(mode=0o700)
        for name, contents in world.files.items():
            relative = PurePosixPath(name).relative_to("world")
            target = stage.joinpath(*relative.parts)
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            write_private(target, contents)
        for directory in sorted((path for path in stage.rglob("*") if path.is_dir()), key=lambda path: len(path.parts), reverse=True):
            fsync_directory(directory)
        fsync_directory(stage)
        installed = []
        moved_old = []
        try:
            for name in WORLD_NAMES:
                target = data / name
                if target.exists():
                    os.rename(target, previous / name)
                    moved_old.append(name)
                os.rename(stage / name, target)
                installed.append(name)
            fsync_directory(data)
            fsync_directory(previous)
            fsync_directory(backup)
            record = {"schemaVersion": 1, "updateId": world.update_id,
                      "installedUTC": datetime.datetime.now(datetime.timezone.utc).isoformat(), "backup": str(backup)}
            atomic_marker(marker, (json.dumps(record, sort_keys=True) + "\n").encode())
        except BaseException:
            try:
                for name in reversed(installed):
                    os.rename(data / name, stage / name)
                for name in reversed(moved_old):
                    os.rename(previous / name, data / name)
                if previous_marker is None:
                    marker.unlink(missing_ok=True)
                else:
                    atomic_marker(marker, previous_marker)
                fsync_directory(data)
            except BaseException as error:
                raise RuntimeError(f"Rollback needs manual recovery from {backup}; do not start the game.") from error
            raise
    return backup


def install_world(archive, data, hosting, *, locker=world_lock, start_service=None):
    world = validate_archive(archive)
    data = data.absolute()
    ordinary_directory(data)
    ordinary_directory(data / ".lan-server", create=True)
    install_lock = open_lock(data / ".lan-server/fresh-world-install.lock")
    try:
        try:
            fcntl.flock(install_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another fresh-world installation is already running.") from error
        with locker(data, hosting) as state:
            backup = apply_world(world, data, state)
        # The service's initialization needs the data lock, so release it first.
        try:
            if start_service is None:
                subprocess.run(["bash", str(hosting / "install-service.sh")], check=True)
            else:
                start_service()
        except Exception:
            saved_backup = backup or json_object((data / ".lan-server" / APPLIED_MARKER).read_bytes(), "installed-world marker").get("backup")
            print(f"[FarmVillage] The fresh world is installed; its backup remains at {saved_backup}. "
                  "Startup was unsuccessful. Run this same installer again to retry startup without resetting progress.",
                  file=sys.stderr, flush=True)
            raise
        return {"updateId": world.update_id, "applied": backup is not None, "backup": backup}
    finally:
        os.close(install_lock)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path)
    args = parser.parse_args(argv)
    if os.getuid() == 0:
        print("Run this installer as the Ubuntu user who owns the game files, without sudo.", file=sys.stderr)
        return 1
    hosting = Path(__file__).resolve().parent
    data = args.data_dir or hosting.parent / "data"
    try:
        install_world(args.archive, data, hosting)
    except (OSError, RuntimeError, ValueError, tarfile.TarError, subprocess.SubprocessError) as error:
        print(f"[FarmVillage] Fresh-world installation stopped: {error}", file=sys.stderr, flush=True)
        return 1
    print("[FarmVillage] Fresh neighborhood ready. Open http://192.168.50.80:5501/", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
