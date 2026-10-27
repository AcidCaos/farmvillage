"""Same-origin God Barn bridge, registered by an owned game runtime.

Unlike the standalone server, this adapter intentionally edits the selected live
farm through the game's existing lock, validation, transaction and save APIs.
It never imports a top-level ``engine`` or ``server`` module.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from functools import wraps
import errno
import gzip
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import time
from urllib.parse import quote, urlsplit

from flask import Blueprint, Response, jsonify, redirect, request, send_from_directory, session

from .engine import CheatEngine
from .encyclopedia import enrich_catalog, history_filters, load_metadata
from .seasonal import annotate_item, calendar_context
from .catalog_tools import UntabbedCatalog, discover_catalog


PREFIX = "/god-barn"
SNAPSHOT_ID = re.compile(r"^[0-9a-f]{32}$")
PREVIEW_TTL = 900
CLASSICS = {name: index for index, name in enumerate((
    "strawberry", "eggplant", "wheat", "soybeans", "blueberry", "rice", "pumpkin",
    "raspberry", "corn", "cow", "chicken", "horse", "sheep", "pig", "goat",
    "apple", "orange", "cherry", "lemon", "peach", "tractor", "harvester", "seeder"))}


class BridgeError(Exception):
    def __init__(self, message, status=400, code="invalid_request"):
        super().__init__(message)
        self.status, self.code = status, code


def _bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")).encode("utf-8")


def _hash(save):
    return hashlib.sha256(_bytes(save)).hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _atomic(path, value):
    if path.is_symlink():
        raise OSError("Refusing a symlink snapshot.")
    temporary = path.with_name("." + path.name + "." + secrets.token_hex(8))
    try:
        with temporary.open("xb") as output:
            output.write(_bytes(value))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            try:
                os.fsync(directory)
            except OSError as error:
                if error.errno not in (errno.EINVAL, errno.ENOTSUP, errno.EBADF):
                    raise
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _reject_number(value):
    raise ValueError("Numbers must be finite.")


def _trusted_origins(app, port):
    """Keep loopback defaults and accept only explicitly configured origins."""
    configured = app.config.get("FARMVILLAGE_TRUSTED_ORIGINS", ())
    if not isinstance(configured, (list, tuple, set, frozenset)):
        raise ValueError("FARMVILLAGE_TRUSTED_ORIGINS must be a collection of exact http(s) origins.")
    origins = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
    for origin in configured:
        try:
            if not isinstance(origin, str) or not origin.isascii() or any(char.isspace() for char in origin):
                raise ValueError
            parts = urlsplit(origin)
            host = parts.hostname
            if (parts.scheme not in ("http", "https") or not host or parts.username is not None
                    or parts.password is not None or parts.path or parts.query or parts.fragment
                    or "?" in origin or "#" in origin or origin != parts.scheme + "://" + parts.netloc
                    or parts.netloc != parts.netloc.lower()):
                raise ValueError
            if ":" in host:
                ipaddress.IPv6Address(host)
            elif not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label) for label in host.split(".")):
                raise ValueError
            port_number = parts.port
            if port_number is not None and not 1 <= port_number <= 65535:
                raise ValueError
            if parts.netloc.endswith(":"):
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError("FARMVILLAGE_TRUSTED_ORIGINS contains an invalid origin; use an exact URL such as http://192.168.50.80:5501.") from None
        origins.add(origin)
    return frozenset(origins)


class LiveGodBarn:
    def __init__(self, app, game_server, player_module, bundle_module, root, farming_module=None):
        self.app, self.game = app, game_server
        self.player, self.bundle = player_module, bundle_module
        self.root = Path(root).resolve()
        self.lock = player_module.SAVE_LOCK
        self.previews, self.epochs = {}, {}
        self.rotated, self.parked = set(), set()
        self.park_owners = {}
        directory = Path(bundle_module.DATA_DIR).resolve() / "god-barn" / "snapshots"
        for parent in (directory, directory.parent):
            if parent.is_symlink():
                raise ValueError("God Barn snapshot directories must not be symlinks.")
        directory.mkdir(parents=True, exist_ok=True)
        self.snapshots = directory.resolve()
        data = self.root / "data"
        archive_path = data / "archive-provenance.json"
        self.collections = json.loads(archive_path.read_text()).get("collections", []) if archive_path.is_file() else []
        catalog_path = data / "catalog.json"
        if catalog_path.is_file():
            catalog = json.loads(catalog_path.read_text())
        else:
            with gzip.open(data / "catalog.json.gz", "rt", encoding="utf-8") as source:
                catalog = json.load(source)
        self.rules = json.loads((data / "rules.json").read_text())
        catalog, shelves = enrich_catalog(catalog, load_metadata(data))
        known_collections = {collection.get("id") for collection in self.collections}
        self.collections.extend(shelf for shelf in shelves if shelf.get("id") not in known_collections)
        self.items = {}
        for item in catalog:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                normalized = dict(item)
                image = normalized.get("image")
                if isinstance(image, str) and image.startswith(("/static/assets/", "/assets/")):
                    normalized["image"] = PREFIX + image
                else:
                    normalized["image"] = None
                self.items.setdefault(item["name"], normalized)
        self.catalog = sorted(self.items.values(), key=lambda item: (
            not bool(item.get("hasOriginalThumbnail")), CLASSICS.get(item["name"], len(CLASSICS)),
            str(item.get("displayName") or item["name"]).casefold(), item["name"]))
        self.history_filters = history_filters(self.catalog)
        progression_path = data / "progression.json"
        progression = json.loads(progression_path.read_text()) if progression_path.is_file() else None
        helpers_path = data / "helpers.json"
        helpers = json.loads(helpers_path.read_text()) if helpers_path.is_file() else None
        self.engine = CheatEngine(self.catalog, self.rules, progression=progression,
                                  farming_module=farming_module, helpers=helpers)
        untabbed_path = data / "untabbed.json"
        untabbed_origins = json.loads(untabbed_path.read_text()) if untabbed_path.is_file() else None
        self.untabbed = UntabbedCatalog(self.catalog, untabbed_origins)
        self.asset_map = {}
        asset_map = data / "asset-map.json"
        if asset_map.is_file():
            self.asset_map = json.loads(asset_map.read_text())
        elif (data / "provenance.json").is_file():
            provenance = json.loads((data / "provenance.json").read_text())
            for entry in provenance.get("assets", []):
                original = entry.get("originalPath", "")
                if "/assets/" in original:
                    self.asset_map[entry["path"]] = original.rsplit("/assets/", 1)[-1]

    def _uids(self):
        return [str(uid) for uid in self.player.all_saves_uids()]

    def _uid(self, candidate=None):
        uid = candidate if candidate is not None else session.get("GOD_BARN_UID", session.get("UID"))
        uids = self._uids()
        if uid is None and uids:
            uid = uids[0]
        if not isinstance(uid, str) or uid not in uids:
            raise BridgeError("Select an existing farm to use the live God Barn.", 404, "not_found")
        return uid

    def _csrf(self):
        if not isinstance(session.get("GOD_BARN_CSRF"), str):
            session["GOD_BARN_CSRF"] = secrets.token_urlsafe(32)
        return session["GOD_BARN_CSRF"]

    def _epoch(self, uid):
        return self.epochs.setdefault(uid, secrets.token_hex(24))

    def _rotate(self, uid):
        self.epochs[uid] = secrets.token_hex(24)
        self.rotated.add(uid)

    def _park(self, uid):
        """Fence a farm for this editor session without stealing another editor."""
        owner = self._csrf()
        existing = self.park_owners.get(uid)
        if existing is not None and not secrets.compare_digest(existing, owner):
            raise BridgeError("This farm is open in another God Barn session. Return to the farm there before editing here.",
                              409, "farm_in_use")
        self.park_owners[uid] = owner
        self.parked.add(uid)

    def _resume(self, uid):
        owner = self._csrf()
        existing = self.park_owners.get(uid)
        if existing is not None and not secrets.compare_digest(existing, owner):
            raise BridgeError("This farm is open in another God Barn session. Return to the farm there before resuming here.",
                              409, "farm_in_use")
        # A picker can park several farms in one session. Release only those
        # farms, and fence any late game requests from before their parking.
        for parked_uid, parked_owner in list(self.park_owners.items()):
            if secrets.compare_digest(parked_owner, owner):
                self.parked.discard(parked_uid)
                del self.park_owners[parked_uid]
                self._rotate(parked_uid)

    def _resume_game_page(self, uid):
        """A fresh game document releases only its selected farm, from any editor.

        Call with the save lock held. Rotate only when releasing a park, so
        ordinary page reloads do not invalidate another current game document.
        An editor left open must claim the farm again and pass its revision
        check before applying anything.
        """
        if uid in self.parked:
            self.parked.remove(uid)
            self.park_owners.pop(uid, None)
            self._rotate(uid)

    def _summary(self, save):
        details = self.engine.summarize(save)
        plots = details["plots"]
        summary = {key: details[key] for key in ("name", "uid", "cash", "xp", "level", "energy", "energyMax", "turboChargers", "objectCount")}
        summary.update(coins=details["gold"], plots=len(plots),
                       ready=sum(plot["phase"] == "grown" for plot in plots),
                       withered=sum(plot["phase"] == "withered" for plot in plots),
                       items=details["inventoryCount"], worldSize={"x": details["sizeX"], "y": details["sizeY"]})
        return summary, details

    def _history(self, uid):
        history = []
        for path in self.snapshots.glob("*.json"):
            if path.is_symlink() or not SNAPSHOT_ID.fullmatch(path.stem):
                continue
            try:
                record = json.loads(path.read_text())
                if (record.get("uid") == uid and record.get("id") == path.stem
                        and isinstance(record.get("created"), str)):
                    history.append({key: record.get(key) for key in
                                    ("id", "label", "created", "summary", "original", "action", "restoredFrom")})
            except (OSError, ValueError, TypeError, AttributeError):
                continue
        return sorted(history, key=lambda entry: entry["created"], reverse=True)

    def state(self, uid=None):
        with self.lock:
            uid = self._uid(uid)
            save = copy.deepcopy(self.player.session(uid))
            summary, details = self._summary(save)
            farms = []
            for farm_uid in self._uids():
                other = self.player.session(farm_uid)
                name = other.get("userInfo", {}).get("attr", {}).get("name", "Farmer")
                farms.append({"id": farm_uid, "name": name, "filename": "Live farm · " + name, "updated": None})
            return {"mode": "live", "liveConnection": True, "csrf": self._csrf(), "rules": self.rules,
                    "farm": {"id": uid, "name": summary["name"], "filename": "Live farm · " + summary["name"],
                             "revision": _hash(save), "summary": summary, "details": details, "save": save},
                    "farms": farms, "history": self._history(uid), "parked": uid in self.parked,
                    "resumeURL": PREFIX + "/resume?uid=" + quote(uid, safe="")}

    def _check(self, body):
        explicit = body.get("farmId")
        if not isinstance(explicit, str) or not explicit:
            raise BridgeError("The live farm ID is required.", 400, "farm_required")
        uid = self._uid(explicit)
        selected = self._uid()
        if uid != selected:
            raise BridgeError("Another tab selected a different farm. Refresh before applying.", 409, "farm_changed")
        save = self.player.session(uid)
        if not isinstance(body.get("revision"), str) or body["revision"] != _hash(save):
            raise BridgeError("The farm changed. Preview this action again.", 409, "stale_revision")
        return uid, save

    def preview(self, body):
        with self.lock:
            uid, save = self._check(body)
            self._park(uid)
            result = self.engine.apply(copy.deepcopy(save), body.get("operation"), now=time.time())
            if result["save"]["userInfo"]["player"]["userId"] != save["userInfo"]["player"]["userId"]:
                raise BridgeError("A cheat cannot change player identity.")
            token = secrets.token_urlsafe(32)
            self.previews = {key: value for key, value in self.previews.items() if time.time() - value["created"] < PREVIEW_TTL}
            if len(self.previews) > 200:
                self.previews.clear()
            self.previews[token] = {"uid": uid, "before": _hash(save), "created": time.time(),
                                    "result": result, "operation": body.get("operation"), "csrf": self._csrf()}
            return {"token": token, "revision": body["revision"], "summary": result["summary"],
                    "changes": result["changes"], "warnings": result["warnings"],
                    "summaryAfter": self._summary(result["save"])[0], "expiresIn": PREVIEW_TTL,
                    "gift": self._gift_card(body.get("operation"))}

    def _gift_card(self, operation):
        if not isinstance(operation, dict) or operation.get("type") != "grant":
            return None
        item = self.items.get(operation.get("item"), {})
        return {"item": {key: item.get(key) for key in ("name", "displayName", "image", "archive",
                                                      "artwork", "hasOriginalThumbnail", "labelSource")},
                "quantity": operation.get("quantity"), "group": operation.get("group", "giftbox")}

    def _snapshot(self, uid, save, label, *, action=None, restored_from=None):
        snapshot_id = secrets.token_hex(16)
        record = {"id": snapshot_id, "uid": uid, "label": label, "created": _now(),
                  "original": not bool(self._history(uid)), "summary": self._summary(save)[0],
                  "action": action, "restoredFrom": restored_from, "save": copy.deepcopy(save)}
        _atomic(self.snapshots / (snapshot_id + ".json"), record)
        return record

    def _commit(self, uid, before, after):
        self.engine.validate_save(after)
        # The game's transaction owns rollback and imported-filename retention.
        try:
            with self.player.village_transaction(uid):
                target = self.player.session(uid)
                target.clear()
                target.update(copy.deepcopy(after))
                self.player.save_session(uid)
        except BaseException as error:
            # A durability error may mean the game's journal committed anyway.
            # Keep stale pages fenced off if the committed state changed.
            committed_error = getattr(self.player, "CommittedSaveError", ())
            committed = isinstance(error, committed_error)
            if committed or _hash(self.player.session(uid)) != _hash(before):
                self._rotate(uid)
            if committed:
                warning = ("The change is applied, but the filesystem could not confirm the save's durability. "
                           "Do not repeat the cheat. Your previous farm is in Snapshots; inspect Activity before restarting.")
                self.app.logger.warning("God Barn change committed with a storage durability warning for %s: %s", uid, error)
                return warning
            raise
        self._rotate(uid)
        return None

    def apply(self, body):
        with self.lock:
            uid, save = self._check(body)
            token = body.get("token")
            preview = self.previews.get(token) if isinstance(token, str) else None
            if (preview is None or preview["uid"] != uid or preview["before"] != _hash(save)
                    or time.time() - preview["created"] >= PREVIEW_TTL
                    or not secrets.compare_digest(preview["csrf"], self._csrf())):
                raise BridgeError("This preview expired. Preview the live change again.", 409, "preview_expired")
            # A game page may have resumed since this preview. Claim it again
            # under the same save lock before taking a snapshot or writing.
            # Invalid/stale previews must not pause a resumed game.
            self._park(uid)
            result = preview["result"]
            self._snapshot(uid, save, "Before: " + result["summary"], action=preview["operation"].get("type"))
            durability_warning = self._commit(uid, copy.deepcopy(save), result["save"])
            self.previews.pop(token, None)
            response = self.state(uid)
            warnings = list(result["warnings"])
            if durability_warning:
                warnings.append(durability_warning)
            response["lastAction"] = {"summary": result["summary"], "changes": result["changes"], "warnings": warnings}
            response.update(reloadGame=True, committed=True, durabilityConfirmed=not bool(durability_warning),
                            durabilityWarning=durability_warning)
            return response

    def snapshot(self, snapshot_id):
        if not isinstance(snapshot_id, str) or not SNAPSHOT_ID.fullmatch(snapshot_id):
            raise BridgeError("That live snapshot does not exist.", 404, "not_found")
        path = self.snapshots / (snapshot_id + ".json")
        if path.is_symlink() or not path.is_file():
            raise BridgeError("That live snapshot does not exist.", 404, "not_found")
        record = json.loads(path.read_text())
        if record.get("id") != snapshot_id or record.get("uid") not in self._uids():
            raise BridgeError("That live snapshot does not exist.", 404, "not_found")
        return record

    def restore(self, body):
        with self.lock:
            uid, save = self._check(body)
            snapshot = self.snapshot(body.get("id"))
            if (snapshot["uid"] != uid or snapshot["save"]["userInfo"]["player"]["userId"]
                    != save["userInfo"]["player"]["userId"]):
                raise BridgeError("That snapshot belongs to another farm.", 409, "wrong_farm")
            self._park(uid)
            self._snapshot(uid, save, "Before restoring: " + snapshot["label"], action="restore", restored_from=snapshot["id"])
            durability_warning = self._commit(uid, copy.deepcopy(save), snapshot["save"])
            response = self.state(uid)
            response.update(reloadGame=True, committed=True, durabilityConfirmed=not bool(durability_warning),
                            durabilityWarning=durability_warning,
                            lastAction={"summary": "Restored " + snapshot["label"], "changes": [],
                                        "warnings": [durability_warning] if durability_warning else []})
            return response

    def catalog_page(self):
        try:
            result = discover_catalog(self.catalog, request.args)
        except (ValueError, TypeError) as error:
            raise BridgeError(str(error)) from error
        result["collections"] = self.collections
        result["historyFilters"] = self.history_filters
        return result

    def untabbed_page(self):
        try:
            return self.untabbed.page(dict(request.args))
        except (ValueError, TypeError) as error:
            raise BridgeError(str(error)) from error

    def progression_page(self):
        with self.lock:
            save = self.player.session(self._uid())
            return self.engine.progression_page(save, q=request.args.get("q", ""),
                kind=request.args.get("kind", "all"), status=request.args.get("status", "all"),
                page=int(request.args.get("page", 1)), limit=int(request.args.get("limit", 30)))

    def farming_status(self):
        with self.lock:
            return self.engine.farming_status(self.player.session(self._uid()))

    def helpers_page(self):
        with self.lock:
            return self.engine.helpers_page(self.player.session(self._uid()),
                kind=request.args.get("kind", "all"), q=request.args.get("q", ""),
                status=request.args.get("status", "all"), page=int(request.args.get("page", 1)),
                limit=int(request.args.get("limit", 30)))

    def install_gateway_guard(self):
        original = self.app.view_functions.get("flashservices_gateway")
        if original is None:
            raise ValueError("The game's gateway must exist before God Barn is registered.")

        @wraps(original)
        def guarded_gateway(*args, **kwargs):
            with self.lock:
                try:
                    _, uid, commands = self.game._decode_gateway(request.get_data(cache=True))
                    uid = str(uid)
                except Exception:
                    return original(*args, **kwargs)
                supplied = request.headers.get("X-God-Barn-Epoch")
                if uid in self.parked:
                    return jsonify(error="The farm is parked while God Barn is open.", code="farm_parked"), 409
                # Helping a neighbor writes the host's plot as well as the
                # acting player's rewards. Fence that second farm too.
                for command in commands:
                    if command.get("functionName") != "WorldService.performAction":
                        continue
                    params = command.get("params", ())
                    if (len(params) >= 3 and params[0] == "neighborAct"
                            and isinstance(params[2], (list, tuple)) and params[2]
                            and isinstance(params[2][0], dict)
                            and str(params[2][0].get("hostId")) in self.parked):
                        return jsonify(error="That neighbor's farm is parked while God Barn is open.", code="farm_parked"), 409
                if ((supplied is not None and supplied != self._epoch(uid))
                        or (supplied is None and uid in self.rotated)):
                    return jsonify(error="Reload the farm after using God Barn.", code="stale_game_page"), 409
                return original(*args, **kwargs)
        self.app.view_functions["flashservices_gateway"] = guarded_gateway


def _game_script(epoch):
    # Epoch is an opaque hex token, captured once by each game document.
    return """<script id="god-barn-game-epoch">(()=>{const epoch=%s;
const gateway=u=>{try{const x=new URL(u,location.href);return x.origin===location.origin&&x.pathname==='/flashservices/gateway.php';}catch{return false;}};
let leaving=false;addEventListener('pagehide',()=>{leaving=true;});addEventListener('pageshow',()=>{leaving=false;});
const failed=(status,code)=>{setTimeout(()=>{if(leaving||document.getElementById('farmvillage-save-interrupted'))return;const panel=document.createElement('div');panel.id='farmvillage-save-interrupted';panel.setAttribute('role','alertdialog');panel.setAttribute('aria-modal','true');panel.setAttribute('aria-labelledby','farmvillage-save-interrupted-title');panel.style.cssText='position:fixed;inset:0;z-index:2147483647;background:rgba(28,34,22,.82);display:flex;align-items:center;justify-content:center;padding:24px;box-sizing:border-box;';const card=document.createElement('div');card.style.cssText='max-width:430px;background:#fff9e7;color:#332b20;border:3px solid #bd9c60;border-radius:16px;padding:26px;font:17px/1.5 system-ui;text-align:center;box-shadow:0 10px 60px #0008;';const title=document.createElement('h2');title.id='farmvillage-save-interrupted-title';title.textContent='Your farm needs attention';const message=document.createElement('p');message.textContent=code==='farm_parked'?'Your farm is paused in God Barn. Open God Barn and use Return to Farm before playing.':status===409?'This game tab is out of date. Reopen your farm before continuing.':'The game could not confirm this action was saved. Reopen your farm before continuing.';const detail=document.createElement('p');detail.textContent='Your latest actions may not have saved.';const action=document.createElement('a');action.href=code==='farm_parked'?'/god-barn/':'/';action.textContent=code==='farm_parked'?'Open God Barn':'Reopen my farm';action.style.cssText='display:inline-block;background:#507b35;color:white;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:700;';card.append(title,message,detail,action);panel.append(card);document.body.append(panel);action.focus();},0);};
const inspect=response=>{if(!response.ok){if((response.headers.get('content-type')||'').includes('application/json'))response.clone().json().then(value=>failed(response.status,value.code)).catch(()=>failed(response.status));else failed(response.status);}return response;};
const fetchOriginal=window.fetch;window.fetch=function(input,init){if(gateway(input instanceof Request?input.url:input)){const options={...(init||{})};options.headers=new Headers(options.headers||(input instanceof Request?input.headers:undefined));options.headers.set('X-God-Barn-Epoch',epoch);const pending=fetchOriginal.call(this,input,options);pending.then(inspect,()=>{failed(0);});return pending;}return fetchOriginal.call(this,input,init);};
const openOriginal=XMLHttpRequest.prototype.open,sendOriginal=XMLHttpRequest.prototype.send;XMLHttpRequest.prototype.open=function(method,url,...args){this.__godBarnGateway=gateway(url);return openOriginal.call(this,method,url,...args);};XMLHttpRequest.prototype.send=function(body){if(this.__godBarnGateway){this.setRequestHeader('X-God-Barn-Epoch',epoch);this.addEventListener('loadend',()=>{if(this.status===0||this.status>=400){let code;try{if((this.getResponseHeader('content-type')||'').includes('application/json'))code=JSON.parse(this.responseText).code;}catch{}failed(this.status,code);}},{once:true});}return sendOriginal.call(this,body);};
})();</script>""" % json.dumps(epoch)


def _browser_navigation():
    # A normal same-tab link unloads Ruffle before the editor parks the farm.
    # The native app supplies its own Tools toolbar and must keep that layout.
    return """<nav id="god-barn-browser-navigation" aria-label="Farm tools">
<a href="/god-barn/" target="_self">God Barn <span aria-hidden="true">→</span></a>
<span>Gifts, crops &amp; farm tools · Your farm pauses while you edit.</span>
</nav>"""


_BROWSER_NAV_STYLE = """<style id="god-barn-browser-navigation-style">
#god-barn-browser-navigation{box-sizing:border-box;display:flex;align-items:center;justify-content:center;gap:14px;flex-wrap:wrap;max-width:760px;margin:12px auto 0;padding:10px 16px;background:#fff9e7;border:1px solid #d7c49b;border-radius:12px;color:#66553a;font:13px/1.5 system-ui,-apple-system,sans-serif}
#god-barn-browser-navigation a{display:inline-flex;align-items:center;gap:18px;min-height:44px;box-sizing:border-box;padding:9px 18px;border:1px solid #42652d;border-radius:8px;background:#507b35;color:#fff;text-decoration:none;font-size:16px;font-weight:700;white-space:nowrap}
#god-barn-browser-navigation a:hover{background:#42652d}
#god-barn-browser-navigation a:focus-visible{outline:3px solid #b77c22;outline-offset:3px}
</style>"""


def register_god_barn(app, *, game_server, player_module, bundle_module, root=None, farming_module=None):
    """Mount one live bridge on the owned runtime's existing Flask application."""
    if "god_barn" in app.extensions:
        return app.extensions["god_barn"]
    trusted_origins = _trusted_origins(app, int(game_server.BIND_PORT))
    trusted_hosts = {urlsplit(origin).netloc for origin in trusted_origins}
    bridge = LiveGodBarn(app, game_server, player_module, bundle_module, root or Path(__file__).resolve().parent,
                         farming_module=farming_module)
    blueprint = Blueprint("god_barn", __name__, url_prefix=PREFIX)

    def error_response(status):
        if request.path.startswith(PREFIX + "/api/"):
            return jsonify(error="That God Barn endpoint does not exist." if status == 404 else "God Barn could not finish that request.",
                           code="not_found" if status == 404 else "internal_error"), status
        template = bridge.root / "static" / "error.html"
        if not template.is_file():
            return Response("God Barn · " + str(status), status=status, mimetype="text/html")
        values = {"__BASE__": PREFIX, "__HOME__": PREFIX + "/", "__CODE__": str(status),
                  "__TITLE__": "A little lost in the fields?" if status == 404 else "Aw, shucks. Barn trouble.",
                  "__MESSAGE__": "This pasture doesn’t exist. The cows deny everything." if status == 404 else "The tractor ate a server gremlin. The cows are withholding comment.",
                  "__DETAIL__": "That page has wandered off. Head back to God Barn and choose another path." if status == 404 else "Something went wrong while opening this part of God Barn. Return to the barn, and inspect Activity if it happens again."}
        html = template.read_text()
        for key, value in values.items():
            html = html.replace(key, value)
        return Response(html, status=status, mimetype="text/html")

    @blueprint.before_request
    def local_request_only():
        if request.host.lower() not in trusted_hosts:
            raise BridgeError("God Barn is available only at a configured game address.", 403, "forbidden_host")
        origin = request.headers.get("Origin")
        if origin and origin not in trusted_origins:
            raise BridgeError("This origin cannot access God Barn.", 403, "forbidden_origin")
        if request.headers.get("Sec-Fetch-Site") == "cross-site":
            raise BridgeError("Cross-site God Barn navigation is not supported.", 403, "forbidden_origin")
        if request.method == "POST":
            if request.content_length is None or request.content_length > 1024 * 1024:
                raise BridgeError("God Barn action bodies must be smaller than 1 MiB.", 413, "too_large")
            if not request.is_json:
                raise BridgeError("Use application/json for God Barn actions.", 415, "content_type")
            provided = request.headers.get("X-God-Barn-Token", "")
            if not secrets.compare_digest(provided, bridge._csrf()):
                raise BridgeError("Refresh God Barn before sending this action.", 403, "csrf")

    @blueprint.errorhandler(BridgeError)
    def bridge_error(error):
        if error.status in (404, 500) and not request.path.startswith(PREFIX + "/api/"):
            return error_response(error.status)
        return jsonify(error=str(error), code=error.code), error.status

    @blueprint.errorhandler(404)
    @blueprint.errorhandler(500)
    def branded_http_error(error):
        return error_response(error.code)

    @blueprint.errorhandler(ValueError)
    @blueprint.errorhandler(TypeError)
    @blueprint.errorhandler(KeyError)
    def invalid_action(error):
        return jsonify(error=str(error), code="invalid_request"), 400

    @blueprint.errorhandler(OSError)
    def storage_error(error):
        return jsonify(error="The live farm or God Barn snapshot could not be saved. Inspect Activity before retrying.", code="storage_error"), 500

    @blueprint.after_request
    def secure_response(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        return response

    def body():
        try:
            value = json.loads(request.get_data(), parse_constant=_reject_number)
        except (ValueError, UnicodeError):
            raise BridgeError("Provide a valid JSON action with finite numbers.")
        if not isinstance(value, dict):
            raise BridgeError("The God Barn action must be an object.")
        return value

    @blueprint.get("/")
    def index():
        with bridge.lock:
            # Opening the native tab follows the farm actually playing now.
            # The picker can subsequently choose a different live farm.
            uid = bridge._uid(session.get("UID"))
            bridge._park(uid)
            session["GOD_BARN_UID"] = uid
        return send_from_directory(bridge.root / "static", "index.html")

    @blueprint.get("/park")
    def park():
        with bridge.lock:
            uid = bridge._uid(request.args.get("uid") or session.get("UID"))
            bridge._park(uid)
        return Response("<!doctype html><html><head><title>FarmVillage</title></head><body><p>Your farm is resting while God Barn is open.</p></body></html>", mimetype="text/html")

    @blueprint.get("/resume")
    def resume():
        with bridge.lock:
            uid = bridge._uid(request.args.get("uid"))
            bridge._resume(uid)
            session["UID"] = uid
            session["GOD_BARN_UID"] = uid
        return redirect("/ruffle.html")

    @blueprint.get("/static/<path:path>")
    def static_file(path):
        relative = "static/" + path
        if ("\\" in path or any(part in ("", ".", "..") or part.startswith(".") for part in path.split("/"))):
            raise BridgeError("That God Barn file does not exist.", 404, "not_found")
        local = bridge.root / relative
        if local.is_file() and not local.is_symlink() and local.resolve().is_relative_to(bridge.root / "static"):
            return send_from_directory(bridge.root / "static", path)
        mapped = bridge.asset_map.get(relative)
        if (isinstance(mapped, str) and not mapped.startswith(("/", "\\"))
                and ".." not in mapped.replace("\\", "/").split("/")):
            asset_root = Path(bundle_module.ASSETS_DIR).resolve()
            resolved = (asset_root / mapped).resolve()
            if resolved.is_relative_to(asset_root):
                return send_from_directory(bundle_module.ASSETS_DIR, mapped)
        raise BridgeError("That God Barn file does not exist.", 404, "not_found")

    @blueprint.get("/api/state")
    def state():
        return jsonify(bridge.state())

    @blueprint.get("/api/catalog")
    def catalog():
        return jsonify(bridge.catalog_page())

    @blueprint.get("/api/untabbed")
    def untabbed():
        return jsonify(bridge.untabbed_page())

    @blueprint.get("/api/progression")
    def progression():
        return jsonify(bridge.progression_page())

    @blueprint.get("/api/farming")
    def farming():
        return jsonify(bridge.farming_status())

    @blueprint.get("/api/helpers")
    def helpers():
        return jsonify(bridge.helpers_page())

    @blueprint.get("/api/items")
    def items():
        names = list(dict.fromkeys(request.args.get("names", "").split(",")))[:100]
        day, calendar = calendar_context()
        return jsonify(items=[annotate_item(bridge.items[name], day) for name in names if name in bridge.items],
                       calendar=calendar)

    @blueprint.post("/api/select")
    def select():
        payload = body()
        with bridge.lock:
            uid = bridge._uid(payload.get("id"))
            bridge._park(uid)
            session["GOD_BARN_UID"] = uid
            return jsonify(bridge.state(uid))

    @blueprint.post("/api/preview")
    def preview():
        return jsonify(bridge.preview(body()))

    @blueprint.post("/api/apply")
    def apply():
        return jsonify(bridge.apply(body()))

    @blueprint.post("/api/restore")
    def restore():
        return jsonify(bridge.restore(body()))

    @blueprint.post("/api/import")
    @blueprint.post("/api/demo")
    def copied_save_action():
        raise BridgeError("Import and demo farms are available in the standalone copied-save God Barn.", 400, "live_mode")

    @blueprint.get("/api/export")
    def export():
        with bridge.lock:
            if not request.args.get("id"):
                raise BridgeError("An explicit live farm ID is required.", 400, "farm_required")
            uid = bridge._uid(request.args["id"])
            raw = _bytes(copy.deepcopy(bridge.player.session(uid)))
        response = Response(raw, mimetype="application/json")
        response.headers["Content-Disposition"] = 'attachment; filename="god-barn-live-farm.json"'
        return response

    @blueprint.get("/api/snapshot")
    def snapshot():
        with bridge.lock:
            record = bridge.snapshot(request.args.get("id"))
            raw = _bytes(record["save"])
        response = Response(raw, mimetype="application/json")
        response.headers["Content-Disposition"] = 'attachment; filename="god-barn-live-snapshot.json"'
        return response

    @blueprint.route("/<path:missing>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def missing_page(missing):
        return error_response(404)

    @app.after_request
    def inject_game_epoch(response):
        if (request.path in ("/ruffle.html", "/play.html") and response.status_code == 200
                and response.mimetype == "text/html"):
            with bridge.lock:
                uid = session.get("UID")
                if uid not in bridge._uids():
                    return response
                # The existing game login chooses UID. Returning through any
                # real game page also ends its park, even from another device.
                # A cross-site embed, HEAD probe, or untrusted Host must not
                # release an editor just by requesting this URL.
                if (request.method == "GET" and request.host.lower() in trusted_hosts
                        and (not request.headers.get("Origin") or request.headers["Origin"] in trusted_origins)
                        and request.headers.get("Sec-Fetch-Site") != "cross-site"):
                    bridge._resume_game_page(uid)
                script = _game_script(bridge._epoch(uid))
            # Every game document carries its own epoch; a cached page cannot
            # perform the resume above or receive its current fencing token.
            response.headers["Cache-Control"] = "no-store"
            html = response.get_data(as_text=True)
            head = re.search(r"<head(?:\s[^>]*)?>", html, flags=re.I)
            insertion = head.end() if head else 0
            response.set_data(html[:insertion] + script + html[insertion:])
            if not getattr(game_server, "NATIVE_WRAPPER", False):
                html = response.get_data(as_text=True)
                head = re.search(r"<head(?:\s[^>]*)?>", html, flags=re.I)
                insertion = head.end() if head else 0
                html = html[:insertion] + _BROWSER_NAV_STYLE + html[insertion:]
                body = re.search(r"<body(?:\s[^>]*)?>", html, flags=re.I)
                insertion = body.end() if body else len(html)
                response.set_data(html[:insertion] + _browser_navigation() + html[insertion:])
        return response

    bridge.install_gateway_guard()
    app.register_blueprint(blueprint)
    app.extensions["god_barn"] = bridge
    return bridge
