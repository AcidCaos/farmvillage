#!/usr/bin/env python3
"""God Barn: a loopback-only companion for detached FarmVillage save copies.

This module has no dependency on, and never imports, the running game's code.
All writable state belongs to the companion workspace. Imports arrive as JSON
bytes from the browser; no API accepts a source filesystem path.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import mimetypes
import os
import re
import secrets
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

if __package__:
    from .seasonal import annotate_item, calendar_context
    from .catalog_tools import UntabbedCatalog, discover_catalog
    from .encyclopedia import enrich_catalog, history_filters, load_metadata
else:
    from seasonal import annotate_item, calendar_context
    from catalog_tools import UntabbedCatalog, discover_catalog
    from encyclopedia import enrich_catalog, history_filters, load_metadata


ROOT = Path(__file__).resolve().parent
MAX_IMPORT_BYTES = 10 * 1024 * 1024
MAX_REQUEST_BYTES = MAX_IMPORT_BYTES + 256 * 1024
PREVIEW_TTL = 15 * 60
SAFE_ID = re.compile(r"^[a-f0-9]{32}$")
CLASSIC_ITEMS = (
    "strawberry", "eggplant", "wheat", "soybeans", "blueberry", "rice", "pumpkin",
    "raspberry", "corn", "cow", "chicken", "horse", "sheep", "pig", "goat",
    "apple", "orange", "cherry", "lemon", "peach", "tractor", "harvester", "seeder",
)
CLASSIC_RANK = {name: index for index, name in enumerate(CLASSIC_ITEMS)}
TYPE_RANK = {name: index for index, name in enumerate(("seed", "animal", "tree", "vehicle", "building", "decoration"))}


class APIError(Exception):
    def __init__(self, message, status=400, code="invalid_request"):
        super().__init__(message)
        self.status = status
        self.code = code


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def json_bytes(value, *, pretty=False):
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        indent=2 if pretty else None, separators=None if pretty else (",", ":"),
    ).encode("utf-8")


def _reject_constant(value):
    raise ValueError(f"Non-finite number {value} is not valid save data.")


def decode_json(raw):
    try:
        return json.loads(raw.decode("utf-8-sig"), parse_constant=_reject_constant)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise APIError("Provide valid UTF-8 JSON containing only finite numbers.") from error


def safe_filename(value):
    if not isinstance(value, str):
        raise APIError("The source filename must be text.")
    basename = value.replace("\\", "/").rsplit("/", 1)[-1]
    basename = re.sub(r"[\x00-\x1f\x7f\";]", "", basename).strip()[:150]
    return basename or "farm-copy.json"


def _finite_number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and (not isinstance(value, float) or math.isfinite(value)))


def _check_json_numbers(value, depth=0):
    if depth > 100:
        raise APIError("The save is nested too deeply.")
    if isinstance(value, float) and not math.isfinite(value):
        raise APIError("Save numbers must be finite.")
    if isinstance(value, dict):
        for nested in value.values():
            _check_json_numbers(nested, depth + 1)
    elif isinstance(value, list):
        for nested in value:
            _check_json_numbers(nested, depth + 1)


def _strict_core_validation(save):
    if not isinstance(save, dict):
        raise APIError("The save must be a JSON object.")
    _check_json_numbers(save)
    user = save.get("userInfo")
    player = user.get("player") if isinstance(user, dict) else None
    world = save.get("world")
    if not isinstance(player, dict) or not isinstance(world, dict):
        raise APIError("The save needs userInfo.player and world objects.")
    for field in ("gold", "cash", "xp", "energy"):
        value = player.get(field)
        if not _finite_number(value) or value < 0:
            raise APIError(f"player.{field} must be a finite nonnegative number.")
    uid = player.get("userId")
    if isinstance(uid, bool) or not isinstance(uid, (str, int)) or not str(uid):
        raise APIError("The save must preserve a valid player.userId.")
    for field in ("sizeX", "sizeY"):
        value = world.get(field)
        if not _finite_number(value) or value <= 0:
            raise APIError(f"world.{field} must be a finite positive number.")
    if not isinstance(world.get("objectsArray"), list):
        raise APIError("world.objectsArray must be an array.")
    if not all(isinstance(obj, dict) for obj in world["objectsArray"]):
        raise APIError("All farm objects must be JSON objects.")


def _safe_directory(path):
    """Do not follow a preexisting workspace-directory symlink."""
    path = Path(path).absolute()
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ValueError(f"Refusing symlink workspace directory: {parent}")
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise ValueError(f"Workspace path is not a directory: {path}")
    return path.resolve()


def atomic_json(path, value):
    """Publish a whole record in one replace; never overwrite through a link."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Refusing to overwrite a symlink.")
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    try:
        with temporary.open("xb") as output:
            output.write(json_bytes(value, pretty=True))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        # fsync the directory when supported, to preserve the rename on crash.
        try:
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError:
            pass
    finally:
        temporary.unlink(missing_ok=True)


class GodBarn:
    def __init__(self, root=ROOT, workspace=None, engine=None):
        self.root = Path(root).resolve()
        requested_workspace = Path(workspace or self.root / "workspace").expanduser().absolute()
        protected_game = (ROOT.parent / "FarmVillage").resolve()
        resolved_workspace = requested_workspace.resolve()
        if resolved_workspace == protected_game or resolved_workspace.is_relative_to(protected_game):
            raise ValueError("The companion workspace must be outside FarmVillage.")
        self.workspace = _safe_directory(requested_workspace)
        self.farms_dir = _safe_directory(self.workspace / "farms")
        self.snapshots_dir = _safe_directory(self.workspace / "snapshots")
        self.originals_dir = _safe_directory(self.workspace / "originals")
        self.lock = threading.RLock()
        self.csrf = secrets.token_urlsafe(32)
        self.previews = {}
        self.farms = {}
        self.selected = None
        self.catalog = self._read_data("catalog.json", [])
        self.collections = self._read_data("archive-provenance.json", {}).get("collections", [])
        if isinstance(self.catalog, dict):
            self.catalog = self.catalog.get("items", [])
        if not isinstance(self.catalog, list):
            raise ValueError("data/catalog.json must contain an item array.")
        self.catalog, shelves = enrich_catalog(self.catalog, load_metadata(self.root / "data"))
        known_collections = {collection.get("id") for collection in self.collections}
        self.collections.extend(shelf for shelf in shelves if shelf.get("id") not in known_collections)
        self.items_by_name = {}
        for item in self.catalog:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                self.items_by_name.setdefault(item["name"], self._normalize_item(item))
        # Resolve historic duplicates exactly as the game does (first entry),
        # then put recognizable original artwork at the front of the market.
        self.catalog = sorted(self.items_by_name.values(), key=lambda item: (
            not bool(item.get("hasOriginalThumbnail")),
            CLASSIC_RANK.get(item.get("name"), len(CLASSIC_RANK)),
            TYPE_RANK.get(item.get("type"), len(TYPE_RANK)),
            str(item.get("displayName") or item["name"]).casefold(), item["name"],
        ))
        self.rules = self._read_data("rules.json", {})
        self.history_filters = history_filters(self.catalog)
        if engine is None:
            if __package__:
                from .engine import CheatEngine
            else:
                from engine import CheatEngine
            engine = CheatEngine(self.catalog, self.rules, progression=self._read_data("progression.json", {}),
                                 helpers=self._read_data("helpers.json", {}))
        self.engine = engine
        # Labels are added after the engine has copied the rows, so the engine never sees them.
        self.untabbed = UntabbedCatalog(self.catalog, self._read_data("untabbed.json", None))
        self._load_workspace()

    def _read_data(self, filename, default):
        path = self.root / "data" / filename
        if not path.exists():
            return copy.deepcopy(default)
        return decode_json(path.read_bytes())

    def _normalize_item(self, source):
        item = copy.deepcopy(source)
        image = item.get("image")
        if isinstance(image, str):
            image = image.replace("\\", "/")
            relative = image.lstrip("/")
            if (relative.startswith(("assets/", "static/assets/")) and ".." not in relative.split("/")
                    and not urlsplit(image).scheme and not urlsplit(image).netloc):
                item["image"] = "/" + relative
            else:
                item["image"] = None
        return item

    def _validate(self, save):
        _strict_core_validation(save)
        validator = getattr(self.engine, "validate_save", None)
        if validator:
            try:
                validator(save)
            except (ValueError, TypeError, KeyError) as error:
                raise APIError(str(error)) from error

    def _load_workspace(self):
        for path in sorted(self.farms_dir.glob("*.json")):
            if path.is_symlink() or not SAFE_ID.fullmatch(path.stem):
                continue
            try:
                record = decode_json(path.read_bytes())
                if (record.get("id") != path.stem
                        or not isinstance(record.get("revision"), int)
                        or isinstance(record.get("revision"), bool)
                        or record["revision"] < 1):
                    continue
                self._validate(record["save"])
                self.farms[record["id"]] = record
            except (APIError, ValueError, KeyError, TypeError, OSError):
                # An invalid record is preserved for manual recovery, never repaired
                # or deleted automatically.
                continue
        index = self.workspace / "index.json"
        if index.exists() and not index.is_symlink():
            try:
                selected = decode_json(index.read_bytes()).get("selected")
                if selected in self.farms:
                    self.selected = selected
            except (APIError, OSError, AttributeError, TypeError):
                pass
        if self.selected is None and self.farms:
            self.selected = max(self.farms.values(), key=lambda farm: farm.get("updated", ""))["id"]
        if self.selected is None:
            bootstrap = self._read_data("bootstrap-save.json", None)
            if bootstrap is not None:
                self.import_save("God Barn Demo.json", bootstrap, demo=True)

    def _persist_selection(self):
        atomic_json(self.workspace / "index.json", {"version": 1, "selected": self.selected})

    def _current(self):
        if self.selected not in self.farms:
            raise APIError("Import a copied save or start a demo farm first.", 409, "no_farm")
        return self.farms[self.selected]

    def _check_revision(self, requested, farm_id):
        record = self._current()
        if not isinstance(farm_id, str) or not farm_id:
            raise APIError("The companion farm ID is required for this action.", 400, "farm_required")
        if farm_id != record["id"]:
            raise APIError("Another tab selected a different farm. Refresh before applying an action.", 409, "farm_changed")
        if (not isinstance(requested, int) or isinstance(requested, bool)
                or requested != record["revision"]):
            raise APIError("This farm changed. Refresh the preview before applying.", 409, "stale_revision")
        return record

    def _summary(self, save):
        method = getattr(self.engine, "summarize", None)
        detail = method(save) if method else {}
        player = save["userInfo"]["player"]
        world = save["world"]
        plots = detail.get("plots", [])
        if not isinstance(plots, list):
            plots = []
        attr = save["userInfo"].get("attr", {})
        name = detail.get("name") or (attr.get("name") if isinstance(attr, dict) else None) or "My Farm"
        summary = {
            "name": name, "uid": player.get("userId"),
            "coins": detail.get("gold", player.get("gold", 0)),
            "cash": detail.get("cash", player.get("cash", 0)),
            "xp": detail.get("xp", player.get("xp", 0)),
            "level": detail.get("level", player.get("level", 1)),
            "energy": detail.get("energy", player.get("energy", 0)),
            "energyMax": detail.get("energyMax", player.get("maxEnergy", 0)),
            "turboChargers": detail.get("turboChargers", player.get("turboChargers", 0)),
            "plots": len(plots),
            "ready": sum(plot.get("phase") == "grown" for plot in plots),
            "withered": sum(plot.get("phase") == "withered" for plot in plots),
            "items": detail.get("inventoryCount", 0),
            "objectCount": detail.get("objectCount", len(world["objectsArray"])),
            "worldSize": {"x": world["sizeX"], "y": world["sizeY"]},
        }
        return summary, detail

    def _snapshots(self, farm_id):
        records = []
        for folder, original in ((self.originals_dir, True), (self.snapshots_dir, False)):
            for path in folder.glob("*.json"):
                if path.is_symlink() or not SAFE_ID.fullmatch(path.stem):
                    continue
                try:
                    record = decode_json(path.read_bytes())
                    if record.get("farmId") != farm_id or record.get("id") != path.stem:
                        continue
                    records.append({key: record.get(key) for key in
                                    ("id", "label", "created", "summary", "action", "restoredFrom")}
                                   | {"original": original})
                except (APIError, OSError, AttributeError):
                    continue
        return sorted(records, key=lambda item: (item.get("created") or "", item["id"]), reverse=True)

    def state(self):
        with self.lock:
            record = self._current() if self.selected else None
            farm = None
            if record:
                summary, details = self._summary(record["save"])
                farm = {
                    "id": record["id"], "name": record["name"],
                    "revision": record["revision"], "filename": record["filename"],
                    "summary": summary, "details": details, "save": copy.deepcopy(record["save"]),
                }
            farms = [{key: entry.get(key) for key in ("id", "name", "filename", "updated")}
                     for entry in self.farms.values()]
            farms.sort(key=lambda item: item.get("updated", ""), reverse=True)
            return {"farm": farm, "farms": farms,
                    "history": self._snapshots(record["id"]) if record else [],
                    "rules": self.rules, "csrf": self.csrf,
                    "mode": "copied-save", "liveConnection": False}

    def _snapshot(self, record, label, *, original=False, action=None, restored_from=None):
        snapshot_id = secrets.token_hex(16)
        summary, _ = self._summary(record["save"])
        snapshot = {
            "id": snapshot_id, "farmId": record["id"], "label": label,
            "created": utc_now(), "summary": summary, "action": action,
            "restoredFrom": restored_from, "save": copy.deepcopy(record["save"]),
        }
        folder = self.originals_dir if original else self.snapshots_dir
        atomic_json(folder / (snapshot_id + ".json"), snapshot)
        return snapshot

    def import_save(self, filename, save, *, demo=False):
        with self.lock:
            self._validate(save)
            if len(json_bytes(save)) > MAX_IMPORT_BYTES:
                raise APIError("Save copies must be no larger than 10 MiB.", 413, "too_large")
            filename = safe_filename(filename)
            detached = copy.deepcopy(save)
            summary, _ = self._summary(detached)
            farm_id = secrets.token_hex(16)
            record = {
                "id": farm_id, "name": summary["name"], "filename": filename,
                "created": utc_now(), "updated": utc_now(), "revision": 1,
                "demo": demo, "save": detached,
            }
            self._snapshot(record, "Original demo copy" if demo else "Original imported copy",
                           original=True, action="demo" if demo else "import")
            atomic_json(self.farms_dir / (farm_id + ".json"), record)
            self.farms[farm_id] = record
            self.selected = farm_id
            self._persist_selection()
            self.previews.clear()
            return self.state()

    def demo(self):
        bootstrap = self._read_data("bootstrap-save.json", None)
        if bootstrap is None:
            raise APIError("The bundled demo farm is unavailable.", 503, "demo_unavailable")
        return self.import_save("God Barn Demo.json", bootstrap, demo=True)

    def select(self, farm_id):
        with self.lock:
            if not isinstance(farm_id, str) or farm_id not in self.farms:
                raise APIError("That companion farm does not exist.", 404, "not_found")
            self.selected = farm_id
            self._persist_selection()
            self.previews.clear()
            return self.state()

    def preview(self, operation, revision, farm_id):
        with self.lock:
            record = self._check_revision(revision, farm_id)
            if not isinstance(operation, dict):
                raise APIError("An operation object is required.")
            now = time.time()
            self.previews = {key: value for key, value in self.previews.items()
                             if now - value["created"] < PREVIEW_TTL}
            if len(self.previews) >= 200:
                oldest = min(self.previews, key=lambda key: self.previews[key]["created"])
                self.previews.pop(oldest, None)
            try:
                result = self.engine.apply(copy.deepcopy(record["save"]), copy.deepcopy(operation), now=now)
            except (ValueError, TypeError, KeyError, OverflowError) as error:
                raise APIError(str(error)) from error
            self._validate(result["save"])
            if result["save"]["userInfo"]["player"]["userId"] != record["save"]["userInfo"]["player"]["userId"]:
                raise APIError("A cheat cannot change the save's player identity.")
            token = secrets.token_urlsafe(32)
            self.previews[token] = {"farmId": record["id"], "revision": revision, "created": now,
                                    "result": copy.deepcopy(result), "operation": copy.deepcopy(operation)}
            after, _ = self._summary(result["save"])
            return {"token": token, "summary": result.get("summary", "Preview ready"),
                    "changes": result.get("changes", []), "warnings": result.get("warnings", []),
                    "summaryAfter": after, "revision": revision, "expiresIn": PREVIEW_TTL,
                    "gift": self._gift_card(operation)}

    def _gift_card(self, operation):
        if operation.get("type") != "grant":
            return None
        item = self.items_by_name.get(operation.get("item"), {})
        return {"item": {key: item.get(key) for key in ("name", "displayName", "image", "archive",
                                                      "artwork", "hasOriginalThumbnail", "labelSource")},
                "quantity": operation.get("quantity"), "group": operation.get("group", "giftbox")}

    def apply(self, token, revision, farm_id):
        with self.lock:
            record = self._check_revision(revision, farm_id)
            if not isinstance(token, str):
                raise APIError("Preview this action before applying it.", 409, "preview_required")
            preview = self.previews.get(token)
            if (preview is None or preview["farmId"] != record["id"]
                    or preview["revision"] != revision
                    or time.time() - preview["created"] >= PREVIEW_TTL):
                raise APIError("This preview expired or belongs to another farm. Preview again.", 409, "preview_expired")
            result = preview["result"]
            action_label = result.get("summary") or "Cheat applied"
            if not isinstance(action_label, str):
                action_label = str(action_label)
            self._snapshot(record, "Before: " + action_label, action=preview["operation"].get("type"))
            updated = copy.deepcopy(record)
            updated["save"] = copy.deepcopy(result["save"])
            updated["revision"] += 1
            updated["updated"] = utc_now()
            updated["name"] = self._summary(updated["save"])[0]["name"]
            atomic_json(self.farms_dir / (record["id"] + ".json"), updated)
            self.farms[record["id"]] = updated
            self.previews.clear()
            response = self.state()
            response["lastAction"] = {"summary": action_label, "changes": result.get("changes", []),
                                      "warnings": result.get("warnings", [])}
            return response

    def _snapshot_record(self, snapshot_id):
        if not isinstance(snapshot_id, str) or not SAFE_ID.fullmatch(snapshot_id):
            raise APIError("That snapshot does not exist.", 404, "not_found")
        for folder in (self.originals_dir, self.snapshots_dir):
            path = folder / (snapshot_id + ".json")
            if path.is_file() and not path.is_symlink():
                snapshot = decode_json(path.read_bytes())
                if snapshot.get("id") == snapshot_id and snapshot.get("farmId") in self.farms:
                    return snapshot
        raise APIError("That snapshot does not exist.", 404, "not_found")

    def restore(self, snapshot_id, revision, farm_id):
        with self.lock:
            record = self._check_revision(revision, farm_id)
            snapshot = self._snapshot_record(snapshot_id)
            if snapshot["farmId"] != record["id"]:
                raise APIError("This snapshot belongs to another companion farm.", 409, "wrong_farm")
            self._validate(snapshot["save"])
            if snapshot["save"]["userInfo"]["player"]["userId"] != record["save"]["userInfo"]["player"]["userId"]:
                raise APIError("Snapshot player identity does not match this farm.")
            self._snapshot(record, "Before restoring: " + snapshot["label"], action="restore", restored_from=snapshot_id)
            updated = copy.deepcopy(record)
            updated["save"] = copy.deepcopy(snapshot["save"])
            updated["revision"] += 1
            updated["updated"] = utc_now()
            updated["name"] = self._summary(updated["save"])[0]["name"]
            atomic_json(self.farms_dir / (record["id"] + ".json"), updated)
            self.farms[record["id"]] = updated
            self.previews.clear()
            state = self.state()
            state["lastAction"] = {"summary": "Restored " + snapshot["label"], "changes": [], "warnings": []}
            return state

    def export(self, snapshot_id=None, farm_id=None):
        with self.lock:
            if snapshot_id:
                snapshot = self._snapshot_record(snapshot_id)
                save = snapshot["save"]
                filename = "god-barn-snapshot-" + snapshot_id[:8] + ".json"
            else:
                if not isinstance(farm_id, str) or farm_id not in self.farms:
                    raise APIError("That companion farm does not exist.", 404, "not_found")
                record = self.farms[farm_id]
                save = record["save"]
                filename = "god-barn-" + safe_filename(record["filename"])
                if not filename.lower().endswith(".json"):
                    filename += ".json"
            return filename, json_bytes(save, pretty=True)

    def catalog_page(self, params):
        try:
            result = discover_catalog(self.catalog, {key: values[0] for key, values in params.items() if values})
        except (ValueError, TypeError) as error:
            raise APIError(str(error)) from error
        result["collections"] = self.collections
        result["historyFilters"] = self.history_filters
        return result

    def untabbed_page(self, params):
        try:
            return self.untabbed.page({key: values[0] for key, values in params.items() if values})
        except (ValueError, TypeError) as error:
            raise APIError(str(error)) from error

    def progression_page(self, params):
        with self.lock:
            record = self._current()
            try:
                return self.engine.progression_page(record["save"],
                    q=params.get("q", [""])[0], kind=params.get("kind", ["all"])[0],
                    status=params.get("status", ["all"])[0], page=int(params.get("page", ["1"])[0]),
                    limit=int(params.get("limit", ["30"])[0]))
            except (ValueError, TypeError) as error:
                raise APIError(str(error)) from error

    def farming_status(self):
        with self.lock:
            return self.engine.farming_status(self._current()["save"])

    def helpers_page(self, params):
        with self.lock:
            try:
                return self.engine.helpers_page(self._current()["save"],
                    kind=params.get("kind", ["all"])[0], q=params.get("q", [""])[0],
                    status=params.get("status", ["all"])[0], page=int(params.get("page", ["1"])[0]),
                    limit=int(params.get("limit", ["30"])[0]))
            except (ValueError, TypeError) as error:
                raise APIError(str(error)) from error

    def catalog_items(self, names):
        wanted = list(dict.fromkeys(names.split(",")))[:100]
        day, calendar = calendar_context()
        return {"items": [annotate_item(self.items_by_name[name], day) for name in wanted if name in self.items_by_name],
                "calendar": calendar}


class GodBarnServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, app):
        if address[0] != "127.0.0.1" or address[1] == 5500:
            raise ValueError("God Barn must use its own IPv4 loopback port, separate from port 5500.")
        self.app = app
        super().__init__(address, GodBarnHandler)


class GodBarnHandler(BaseHTTPRequestHandler):
    server_version = "GodBarn/1.0"
    sys_version = ""

    def log_message(self, format, *args):
        # Avoid printing untrusted request text, save data, and per-process tokens.
        if getattr(self.server, "verbose", False):
            print(f"God Barn {self.command}: {args[1] if len(args) > 1 else ''}", file=sys.stderr)

    @property
    def app(self):
        return self.server.app

    def _security_check(self):
        port = self.server.server_address[1]
        allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host", "").lower() not in allowed_hosts:
            raise APIError("God Barn only accepts its local companion address.", 403, "forbidden_host")
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://{host}" for host in allowed_hosts}:
            raise APIError("This origin cannot access the companion.", 403, "forbidden_origin")

    def _headers(self, status, content_type, length, *, attachment=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if attachment:
            ascii_name = attachment.encode("ascii", errors="ignore").decode("ascii") or "farm-copy.json"
            self.send_header("Content-Disposition", f'attachment; filename="{ascii_name}"')
        self.end_headers()

    def _respond(self, value, status=200):
        raw = json_bytes(value)
        self._headers(status, "application/json; charset=utf-8", len(raw))
        if self.command != "HEAD":
            self.wfile.write(raw)

    def _error(self, error):
        if error.status in (404, 500) and not urlsplit(self.path).path.startswith("/api/"):
            template = self.app.root / "static" / "error.html"
            if template.is_file():
                values = {"__BASE__": "", "__HOME__": "/", "__CODE__": str(error.status),
                          "__TITLE__": "A little lost in the fields?" if error.status == 404 else "Aw, shucks. Barn trouble.",
                          "__MESSAGE__": "This pasture doesn’t exist. The cows deny everything." if error.status == 404 else "The tractor ate a server gremlin. The cows are withholding comment.",
                          "__DETAIL__": "That page has wandered off. Head back to God Barn and choose another path." if error.status == 404 else "Something went wrong while opening this part of God Barn. Return to the barn and try again."}
                html = template.read_text()
                for key, value in values.items():
                    html = html.replace(key, value)
                raw = html.encode("utf-8")
                self._headers(error.status, "text/html; charset=utf-8", len(raw))
                if self.command != "HEAD":
                    self.wfile.write(raw)
                return
        self._respond({"error": str(error), "code": error.code}, error.status)

    def _dispatch_get(self):
        self._security_check()
        parsed = urlsplit(self.path)
        route = unquote(parsed.path)
        params = parse_qs(parsed.query, keep_blank_values=True)
        if route in ("/api/state", "/api/bootstrap"):
            return self._respond(self.app.state())
        if route == "/api/catalog":
            return self._respond(self.app.catalog_page(params))
        if route == "/api/untabbed":
            return self._respond(self.app.untabbed_page(params))
        if route == "/api/progression":
            return self._respond(self.app.progression_page(params))
        if route == "/api/farming":
            return self._respond(self.app.farming_status())
        if route == "/api/helpers":
            return self._respond(self.app.helpers_page(params))
        if route == "/api/items":
            return self._respond(self.app.catalog_items(params.get("names", [""])[0]))
        if route in ("/api/export", "/api/snapshot"):
            snapshot_id = None
            if route == "/api/snapshot":
                snapshot_id = params.get("id", [""])[0]
                if not snapshot_id:
                    raise APIError("A snapshot ID is required.")
            farm_id = None
            if route == "/api/export":
                farm_id = params.get("id", [""])[0]
                if not farm_id:
                    raise APIError("An explicit companion farm ID is required for export.", 400, "farm_required")
            filename, raw = self.app.export(snapshot_id, farm_id=farm_id)
            self._headers(200, "application/json; charset=utf-8", len(raw), attachment=filename)
            if self.command != "HEAD":
                self.wfile.write(raw)
            return
        if route.startswith("/api/"):
            raise APIError("That companion endpoint does not exist.", 404, "not_found")
        self._static(route)

    def _static(self, route):
        if route in ("/", "/index.html"):
            root = self.app.root / "static"
            relative = "index.html"
        elif route.startswith("/static/"):
            root = self.app.root / "static"
            relative = route[len("/static/"):]
        elif route.startswith("/assets/"):
            root = self.app.root / "assets"
            relative = route[len("/assets/"):]
        else:
            raise APIError("That companion file does not exist.", 404, "not_found")
        if (not relative or "\\" in relative or "\x00" in relative
                or any(part in (".", "..", "") or part.startswith(".") for part in relative.split("/"))):
            raise APIError("That companion file does not exist.", 404, "not_found")
        if root.is_symlink():
            raise APIError("That companion file does not exist.", 404, "not_found")
        root = root.resolve()
        path = root / relative
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
            raise APIError("That companion file does not exist.", 404, "not_found")
        # Reject symlinked subdirectories too, even if they happen to resolve inside.
        if any(parent.is_symlink() for parent in path.parents if parent != root.parent):
            raise APIError("That companion file does not exist.", 404, "not_found")
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if content_type in ("text/html", "text/css", "text/javascript", "application/javascript"):
            content_type += "; charset=utf-8"
        raw = path.read_bytes()
        self._headers(200, content_type, len(raw))
        if self.command != "HEAD":
            self.wfile.write(raw)

    def _read_request(self):
        if self.headers.get("Transfer-Encoding"):
            raise APIError("Chunked requests are not supported.")
        media_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            raise APIError("Use application/json for companion actions.", 415, "content_type")
        csrf = self.headers.get("X-God-Barn-Token", "")
        if not secrets.compare_digest(csrf, self.app.csrf):
            raise APIError("Refresh God Barn before sending this action.", 403, "csrf")
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            raise APIError("A valid Content-Length is required.", 411, "length_required")
        if length <= 0:
            raise APIError("Provide a JSON request body.")
        if length > MAX_REQUEST_BYTES:
            raise APIError("Save copies must be no larger than 10 MiB.", 413, "too_large")
        value = decode_json(self.rfile.read(length))
        if not isinstance(value, dict):
            raise APIError("The request body must be a JSON object.")
        return value

    def _dispatch_post(self):
        self._security_check()
        route = urlsplit(self.path).path
        if route not in ("/api/import", "/api/select", "/api/demo", "/api/preview", "/api/apply", "/api/restore"):
            raise APIError("That companion endpoint does not exist.", 404, "not_found")
        body = self._read_request()
        if route == "/api/import":
            response = self.app.import_save(body.get("filename", "farm-copy.json"), body.get("save"))
        elif route == "/api/select":
            response = self.app.select(body.get("id"))
        elif route == "/api/demo":
            response = self.app.demo()
        elif route == "/api/preview":
            response = self.app.preview(body.get("operation"), body.get("revision"), body.get("farmId"))
        elif route == "/api/apply":
            response = self.app.apply(body.get("token"), body.get("revision"), body.get("farmId"))
        else:
            response = self.app.restore(body.get("id"), body.get("revision"), body.get("farmId"))
        self._respond(response)

    def _run(self, operation):
        try:
            operation()
        except APIError as error:
            self._error(error)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
            self._error(APIError("The action could not be processed: " + str(error)))
        except OSError:
            self._error(APIError("The companion could not read or save its local workspace.", 500, "storage_error"))

    def do_GET(self):
        self._run(self._dispatch_get)

    def do_HEAD(self):
        self._run(self._dispatch_get)

    def do_POST(self):
        self._run(self._dispatch_post)

    def do_OPTIONS(self):
        self._error(APIError("Cross-origin actions are not supported.", 405, "method_not_allowed"))


def create_server(*, root=ROOT, workspace=None, port=8877, engine=None):
    app = GodBarn(root=root, workspace=workspace, engine=engine)
    return GodBarnServer(("127.0.0.1", port), app)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8877, help="Companion-only loopback port (default: 8877)")
    parser.add_argument("--workspace", type=Path, help="Companion data directory; never point this at the game's saves")
    parser.add_argument("--verbose", action="store_true", help="Print request methods and response status codes")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535 or args.port == 5500:
        parser.error("Choose a companion port from 1–65535 other than the game's port 5500.")
    # A custom directory is allowed for isolated tests and alternate companion
    # workspaces, but never the original game's checkout or any directory in it.
    if args.workspace:
        original_root = ROOT.parent / "FarmVillage"
        candidate = args.workspace.expanduser().absolute().resolve()
        if candidate == original_root.resolve() or candidate.is_relative_to(original_root.resolve()):
            parser.error("The workspace must be outside FarmVillage. Only companion copies may be edited.")
    try:
        server = create_server(workspace=args.workspace, port=args.port)
    except (OSError, ValueError, APIError) as error:
        parser.exit(1, f"God Barn could not start: {error}\n")
    server.verbose = args.verbose
    print(f"God Barn is ready at http://127.0.0.1:{server.server_address[1]}")
    print(f"Copied-save workspace: {server.app.workspace}")
    print("The running game is not connected. Press Control-C to stop.", flush=True)
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        print("\nGod Barn stopped. Companion copies remain saved.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
