"""Atomic JSON storage, disposable catalog caches, and server save coordination."""

from __future__ import annotations

import errno
from datetime import datetime, timedelta, timezone
from functools import wraps
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
import uuid


SAVE_LOCK = threading.RLock()


class AtomicWriteInstalledError(OSError):
    """The replacement is visible, but its directory could not be synced."""


class CommittedSaveError(OSError):
    """Farm data committed; callers must retain it while reporting durability loss."""


def save_transaction(function):
    """Serialize a complete request, including reads, mutations, and persistence."""
    @wraps(function)
    def coordinated(*args, **kwargs):
        with SAVE_LOCK:
            return function(*args, **kwargs)
    return coordinated


def _reject_constant(value: str):
    raise ValueError(f"Non-finite JSON number: {value}")


def _finite_float(value: str):
    number = float(value)
    if not math.isfinite(number):
        _reject_constant(value)
    return number


def read_json(path):
    with open(path, "r", encoding="utf-8") as stream:
        return json.load(stream, parse_constant=_reject_constant, parse_float=_finite_float)


def decode_json(contents):
    return json.loads(contents, parse_constant=_reject_constant, parse_float=_finite_float)


def _sync_directory(directory: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        try:
            os.fsync(descriptor)
        except OSError as error:
            # Some filesystems do not support directory fsync. File data has
            # already been synced before the atomic replacement.
            if error.errno not in (errno.EINVAL, errno.ENOTSUP, errno.EBADF):
                raise
    finally:
        os.close(descriptor)


def _atomic_file(path, write, *, binary=False) -> None:
    """Leave the old file intact until a complete, synced replacement exists."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".farmvillage-", suffix=".tmp", dir=destination.parent,
    )
    try:
        options = {} if binary else {"encoding": "utf-8"}
        with os.fdopen(descriptor, "wb" if binary else "w", **options) as stream:
            write(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        try:
            _sync_directory(destination.parent)
        except OSError as error:
            raise AtomicWriteInstalledError(
                f"Installed {destination.name}, but its directory sync failed: {error}"
            ) from error
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def atomic_json(path, contents, *, indent=None) -> None:
    def write(stream):
        json.dump(contents, stream, indent=indent, allow_nan=False)
        stream.write("\n")
    _atomic_file(path, write)


def atomic_bytes(path, contents: bytes) -> None:
    _atomic_file(path, lambda stream: stream.write(contents), binary=True)


def _remove_transaction(directory: Path) -> None:
    # A committed transaction may be left behind if cleanup is interrupted.
    # Its marker lets recovery finish cleanup without reverting valid saves.
    try:
        shutil.rmtree(directory)
        _sync_directory(directory.parent)
    except OSError as error:
        print(f"[!] Save transaction cleanup will be retried: {error}")


def _recover_transaction(directory: Path, saves: Path) -> None:
    manifest_path = directory / "manifest.json"
    if manifest_path.is_symlink():
        raise ValueError("The save recovery manifest is unsafe.")
    if not manifest_path.exists():
        # No destination can be changed before a complete manifest is durable.
        _remove_transaction(directory)
        return
    manifest = read_json(manifest_path)
    if (not isinstance(manifest, dict) or manifest.get("version") != 1
            or manifest.get("state") not in ("prepared", "committed")
            or not isinstance(manifest.get("targets"), list) or not manifest["targets"]):
        raise ValueError("Unrecognized save recovery manifest.")
    targets = []
    names = set()
    for index, target in enumerate(manifest["targets"]):
        if not isinstance(target, dict):
            raise ValueError("Invalid save recovery target.")
        name = target.get("name")
        if (not isinstance(name, str) or not name or name in (".", "..")
                or Path(name).name != name or name in names
                or not isinstance(target.get("existed"), bool)):
            raise ValueError("Unsafe or duplicate save recovery target.")
        names.add(name)
        original = None
        if manifest["state"] == "prepared" and target["existed"]:
            backup = directory / f"{index}.original"
            if backup.is_symlink():
                raise ValueError("The save recovery copy is unsafe.")
            original = backup.read_bytes()
            if hashlib.sha256(original).hexdigest() != target.get("sha256"):
                raise ValueError("The original save recovery copy is damaged.")
        targets.append((saves / name, original, target["existed"]))
    if manifest["state"] == "prepared":
        # Validate all originals before touching any destination. Replaying this
        # loop after interruption is safe: the durable originals never change.
        for destination, original, existed in targets:
            if existed:
                atomic_bytes(destination, original)
            else:
                destination.unlink(missing_ok=True)
                _sync_directory(saves)
        # Record that rollback finished before deleting its backup files. An
        # interruption during deletion must never look like partial recovery.
        manifest["state"] = "committed"
        atomic_json(manifest_path, manifest)
    _remove_transaction(directory)


def recover_json_transactions(directory) -> None:
    """Recover interrupted multi-farm saves before any reads or further writes."""
    saves = Path(directory)
    journal = saves / ".save-transactions"
    try:
        if journal.is_symlink():
            raise ValueError("The save recovery directory is unsafe.")
        if not journal.exists():
            return
        if not journal.is_dir():
            raise ValueError("The save recovery directory is unsafe.")
        for transaction in sorted(journal.iterdir()):
            if transaction.is_symlink() or not transaction.is_dir():
                raise ValueError("The save recovery entry is unsafe.")
            _recover_transaction(transaction, saves)
    except Exception as error:
        raise RuntimeError(
            "Save recovery is incomplete. Original farms are preserved in "
            f"{journal}; resolve the storage problem before saving again: {error}"
        ) from error


FARM_BACKUP_DIRECTORY = ".backups"
FARM_BACKUP_INTERVAL = timedelta(minutes=10)
FARM_BACKUP_KEEP = 20
FARM_BACKUP_DAILY_DAYS = 7
_FARM_BACKUP_NAME = re.compile(r"(\d{8}T\d{12})Z\.save\.json")
_FARM_BACKUP_UID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


def _backup_clock() -> datetime:
    return datetime.now(timezone.utc)


def _farm_backup_stamp(path: Path):
    match = _FARM_BACKUP_NAME.fullmatch(path.name)
    if match is None:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%dT%H%M%S%f").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _farm_backups(directory: Path) -> list:
    """Return (timestamp, path) for this farm's backups, newest first.

    Only regular files with the backup naming scheme count. Links, other names,
    and anything else placed in the folder are never read, pruned, or restored.
    """
    entries = []
    for path in directory.iterdir():
        stamp = _farm_backup_stamp(path)
        if stamp is not None and path.is_file() and not path.is_symlink():
            entries.append((stamp, path))
    entries.sort(key=lambda entry: entry[0], reverse=True)
    return entries


def _prune_farm_backups(directory: Path, now: datetime) -> None:
    """Keep at most FARM_BACKUP_KEEP backups, always including the newest backup
    of each UTC day in the last FARM_BACKUP_DAILY_DAYS days, then the newest rest.
    """
    entries = _farm_backups(directory)
    keep = set()
    days = set()
    for stamp, path in entries:
        if now - stamp < timedelta(days=FARM_BACKUP_DAILY_DAYS) and stamp.date() not in days:
            days.add(stamp.date())
            keep.add(path)
    for _, path in entries:
        if len(keep) >= FARM_BACKUP_KEEP:
            break
        keep.add(path)
    for _, path in entries:
        if path not in keep:
            try:
                path.unlink()
            except OSError as error:
                print(f"[!] Could not prune farm backup {path.name}: {error}")


def _backup_farm_file(saves: Path, uid: str, current: bytes):
    if not isinstance(uid, str) or not _FARM_BACKUP_UID.fullmatch(uid):
        raise ValueError("The farm backup UID is unsafe.")
    root = saves / FARM_BACKUP_DIRECTORY
    farm = root / uid
    for directory in (root, farm):
        if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
            raise ValueError(f"The farm backup folder is unsafe: {directory.name}")
        directory.mkdir(mode=0o700, exist_ok=True)
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError(f"The farm backup folder is unsafe: {directory.name}")
    now = _backup_clock()
    entries = _farm_backups(farm)
    # Throttle on the newest backup's own timestamp. A timestamp in the future
    # (clock moved back) does not suppress backups, and pruning bounds the count.
    if entries and timedelta(0) <= now - entries[0][0] < FARM_BACKUP_INTERVAL:
        return None
    stamp = now
    target = farm / f"{stamp.strftime('%Y%m%dT%H%M%S%f')}Z.save.json"
    while target.exists() or target.is_symlink():
        stamp += timedelta(microseconds=1)
        target = farm / f"{stamp.strftime('%Y%m%dT%H%M%S%f')}Z.save.json"
    # atomic_bytes creates the file with mkstemp, so it is 0600 like the saves.
    atomic_bytes(target, current)
    _prune_farm_backups(farm, stamp)
    return target


def backup_farm_before_overwrite(saves, uid: str, current: bytes):
    """Keep a rolling copy of a farm's current on-disk bytes before they are replaced.

    Throttled to one backup per farm per FARM_BACKUP_INTERVAL. Never raises: a
    backup failure is logged so the save that triggered it still completes.
    """
    try:
        return _backup_farm_file(Path(saves), uid, current)
    except Exception as error:
        print(f"[!] Farm backup skipped for {uid}; the save continues: {error}")
        return None


def commit_json_batch(directory, files, *, indent=None, backup_uids=None) -> None:
    """Commit one or several JSON saves, recovering multi-file interruption.

    Requests stage durable new bytes and original copies before any replacement;
    the prepared manifest remains a rollback journal until every save is synced.
    Even one-farm writes use the journal so a directory-sync failure after an
    installed replacement can be rolled back without losing the original data.

    backup_uids maps destination paths that are farm saves to their UIDs. A farm
    whose bytes change is backed up (see backup_farm_before_overwrite) after the
    journal is durable and before it is replaced. Identical bytes are not backed up.
    """
    saves = Path(directory)
    saves.mkdir(parents=True, exist_ok=True)
    recover_json_transactions(saves)
    prepared = []
    for path, contents in files.items():
        destination = Path(path)
        if destination.parent.resolve() != saves.resolve():
            raise ValueError("A save transaction cannot write outside its save directory.")
        if destination.is_symlink():
            raise ValueError("A save transaction cannot replace a symbolic link.")
        encoded = (json.dumps(contents, indent=indent, allow_nan=False) + "\n").encode("utf-8")
        prepared.append((destination, encoded))
    if not prepared:
        return
    journal = saves / ".save-transactions"
    if journal.is_symlink() or (journal.exists() and not journal.is_dir()):
        raise ValueError("The save recovery directory is unsafe.")
    journal.mkdir(exist_ok=True)
    transaction = journal / uuid.uuid4().hex
    transaction.mkdir()
    manifest = {"version": 1, "state": "prepared", "targets": []}
    publishing_commit = False
    try:
        originals = {}
        for index, (destination, encoded) in enumerate(prepared):
            existed = destination.exists()
            target = {"name": destination.name, "existed": existed}
            if existed:
                original = destination.read_bytes()
                originals[index] = original
                atomic_bytes(transaction / f"{index}.original", original)
                target["sha256"] = hashlib.sha256(original).hexdigest()
            atomic_bytes(transaction / f"{index}.new", encoded)
            manifest["targets"].append(target)
        atomic_json(transaction / "manifest.json", manifest)
        _sync_directory(journal)
        _sync_directory(saves)
        # Rolling backups are best effort and never fail the commit.
        for index, (destination, encoded) in enumerate(prepared):
            uid = backup_uids.get(destination) if backup_uids else None
            if uid is not None and index in originals and originals[index] != encoded:
                backup_farm_before_overwrite(saves, uid, originals[index])
        for index, (destination, _) in enumerate(prepared):
            atomic_bytes(destination, (transaction / f"{index}.new").read_bytes())
        manifest["state"] = "committed"
        publishing_commit = True
        atomic_json(transaction / "manifest.json", manifest)
    except BaseException as error:
        if publishing_commit and isinstance(error, AtomicWriteInstalledError):
            # The commit marker and every new farm are already installed. A
            # caller must preserve that memory state rather than undoing only
            # memory and leaving successful on-disk changes hidden until reload.
            raise CommittedSaveError(
                "Farm changes were committed, but storage could not confirm "
                f"their durability. The recovery journal is preserved: {error}"
            ) from error
        # Keep the journal if rollback fails. Recovery blocks future writes
        # rather than publishing an inconsistent registry or losing originals.
        _recover_transaction(transaction, saves)
        raise
    _remove_transaction(transaction)


def _json_digest(contents) -> str:
    encoded = json.dumps(contents, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def load_catalog_cache(path, *, source, decoder, schema, build, validate):
    """Rebuild legacy, malformed, or stale JSON from the exact source bytes.

    The decoder module digest invalidates cached values after parser changes;
    schema is an additional explicit version for the decoded data contract.
    """
    source_bytes = Path(source).read_bytes()
    requirements = Path(decoder).with_name("requirements.txt")
    identity = {
        "format": 1,
        "schema": schema,
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "decoder_sha256": hashlib.sha256(Path(decoder).read_bytes()).hexdigest(),
        "storage_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "requirements_sha256": (hashlib.sha256(requirements.read_bytes()).hexdigest()
                                if requirements.is_file() else None),
    }
    try:
        cached = read_json(path)
        if (isinstance(cached, dict) and cached.get("identity") == identity
                and validate(cached.get("data"))
                and cached.get("data_sha256") == _json_digest(cached["data"])):
            return cached["data"]
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        pass
    print(f" * Rebuilding derived cache: {Path(path).name}...")
    # Match the old decode -> JSON file -> read workflow, including AMF dict
    # keys and tuple/list normalization, even on the first rebuilt-cache load.
    result = decode_json(json.dumps(build(source_bytes), allow_nan=False))
    if not validate(result):
        raise ValueError(f"The decoded catalog has an invalid shape: {source}")
    atomic_json(path, {"identity": identity, "data_sha256": _json_digest(result), "data": result})
    return result
