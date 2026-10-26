#!/usr/bin/env python3
"""Explicit UI QA fixture for the live adapter; never starts/imports the game.

Run with a Python environment that already provides Flask, for example:
  ../FarmVillage/LocalData/venv/bin/python -B scripts/preview_integration.py

Real God Barn assets/catalog/engine are served with a fake player and gateway.
Every writable farm and snapshot is disposable under GodBarn/.qa/. The server
only binds 127.0.0.1:8878 (or 8879); it never contacts another local server.
"""

from __future__ import annotations

import argparse
import copy
from contextlib import contextmanager
import errno
import html
import json
import os
from pathlib import Path
import secrets
import socket
import sys
import tempfile
import threading
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT.parent))

try:
    from flask import Flask, jsonify, redirect, request, session
    from werkzeug.serving import make_server
except ModuleNotFoundError as error:
    raise SystemExit("This QA fixture needs an existing Flask Python environment; no dependencies were installed.") from error

from GodBarn.integration import register_god_barn


def atomic_json(path, value):
    temporary = path.with_name("." + path.name + "." + secrets.token_hex(6))
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class FixturePlayer:
    """Only copied dictionaries and files; this is not a game player module."""

    def __init__(self, directory):
        self.SAVE_LOCK = threading.RLock()
        self.directory = directory / "saves"
        self.directory.mkdir()
        bootstrap_bytes = (ROOT / "data" / "bootstrap-save.json").read_bytes()
        (directory / "copied-bootstrap.json").write_bytes(bootstrap_bytes)
        first = json.loads(bootstrap_bytes)
        first["userInfo"].setdefault("attr", {})["name"] = "QA · Clover Farm"
        second = copy.deepcopy(first)
        second["userInfo"]["player"]["userId"] = "god-barn-qa-second-farm"
        second["userInfo"]["player"]["gold"] = 900
        second["userInfo"]["attr"]["name"] = "QA · Neighbor Farm"
        if isinstance(second.get("flashHotParams"), dict):
            second["flashHotParams"]["ZYNGA_USER_ID"] = second["userInfo"]["player"]["userId"]
        self.farms = {str(save["userInfo"]["player"]["userId"]): save for save in (first, second)}
        for uid, save in self.farms.items():
            atomic_json(self.directory / (uid + ".json"), save)

    def all_saves_uids(self):
        return list(self.farms)

    def session(self, uid):
        return self.farms.get(uid)

    @contextmanager
    def village_transaction(self, uid):
        with self.SAVE_LOCK:
            before = copy.deepcopy(self.farms[uid])
            try:
                yield
                atomic_json(self.directory / (uid + ".json"), self.farms[uid])
            except BaseException:
                self.farms[uid] = before
                raise

    def save_session(self, uid):
        if uid not in self.farms:
            raise ValueError("Unknown fixture farm.")
        # The fake transaction publishes after the adapter finishes its change.


def create_fixture(directory, port):
    player = FixturePlayer(directory)
    first_uid = player.all_saves_uids()[0]
    app = Flask("god_barn_qa_fixture", static_folder=None)
    app.secret_key = secrets.token_bytes(32)
    # Cookies are scoped to hosts, not ports. Keep this QA session separate
    # from any existing FarmVillage session on another loopback port.
    app.config["SESSION_COOKIE_NAME"] = "god_barn_qa_fixture"

    @app.before_request
    def choose_fixture_farm():
        if session.get("UID") not in player.farms:
            session["UID"] = first_uid
        if request.path == "/god-barn/api/state" and session.pop("QA_FAIL_NEXT_STATE", False):
            return jsonify(error="The local QA connection took a hay break. Your copied test farm is safe."), 503

    @app.get("/fixture/error-page")
    def fixture_error_page():
        """Fail one state request so the real UI's retry screen can be checked."""
        session["QA_FAIL_NEXT_STATE"] = True
        return redirect("/god-barn/")

    @app.get("/")
    def home():
        return redirect("/god-barn/")

    @app.post("/flashservices/gateway.php", endpoint="flashservices_gateway")
    def fixture_gateway():
        payload = request.get_json()
        uid = payload.get("uid") if isinstance(payload, dict) else None
        amount = payload.get("amount", 0) if isinstance(payload, dict) else None
        if uid not in player.farms or isinstance(amount, bool) or not isinstance(amount, int) or abs(amount) > 100000:
            return jsonify(error="Invalid QA gateway request."), 400
        with player.village_transaction(uid):
            target = player.session(uid)["userInfo"]["player"]
            target["gold"] = max(0, target["gold"] + amount)
            player.save_session(uid)
        return jsonify(ok=True, coins=target["gold"], fixture=True)

    @app.get("/ruffle.html")
    @app.get("/play.html")
    def fixture_game_page():
        uid = session["UID"]
        with player.SAVE_LOCK:
            save = copy.deepcopy(player.session(uid))
        name = html.escape(save["userInfo"]["attr"]["name"])
        coins = save["userInfo"]["player"]["gold"]
        return f'''<!doctype html><html><head><meta charset="utf-8"><title>God Barn QA fixture</title>
<style>body{{margin:0;background:#d7efff;font:18px Georgia;color:#563b1d;display:grid;place-content:center;min-height:100vh}}main{{max-width:720px;background:#fff9dd;border:8px ridge #b27c3e;border-radius:16px;padding:40px}}a,button{{display:inline-block;margin:8px 8px 8px 0;padding:12px 18px;background:#54bae6;border:2px solid #2788b4;border-radius:9px;color:#173f48;font:17px Georgia}}small{{display:block;color:#765d3d;line-height:1.6}}pre{{white-space:pre-wrap}}</style>
</head><body><main><b>ISOLATED QA FIXTURE · NO GAME IS RUNNING HERE</b><h1>{name}</h1>
<p>Saved balance: <strong>{coins:,} coins</strong></p><small>UID: {html.escape(uid)}<br>This page exercises the real adapter’s resume and request-epoch behavior using copied data.</small>
<a href="/god-barn/">Open God Barn</a><button id="coin">Fixture gateway: add 1 coin</button><button onclick="location.reload()">Refresh fixture</button><pre id="result"></pre>
<script id="fixture-script">document.getElementById('coin').onclick=async()=>{{const response=await fetch('/flashservices/gateway.php',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{uid:{json.dumps(uid)},amount:1}})}});document.getElementById('result').textContent=response.status+' '+await response.text();}};</script>
</main></body></html>'''

    @app.get("/fixture/status")
    def fixture_status():
        with player.SAVE_LOCK:
            return jsonify(fixture=True, gameImported=False, dataDirectory=str(directory),
                           farms=[{"uid": uid, "coins": save["userInfo"]["player"]["gold"]} for uid, save in player.farms.items()])

    def decode_gateway(raw):
        return None, json.loads(raw)["uid"], []

    game = SimpleNamespace(BIND_PORT=port, _decode_gateway=decode_gateway)
    # All original thumbnails already exist in the companion's static folder.
    # This empty fixture asset root prevents any fallback into original assets.
    (directory / "assets").mkdir()
    bundle = SimpleNamespace(DATA_DIR=str(directory), ASSETS_DIR=str(directory / "assets"))
    register_god_barn(app, game_server=game, player_module=player, bundle_module=bundle, root=ROOT)
    forbidden = {"player", "server", "engine", "commands", "assets", "bundle", "game_settings"} & sys.modules.keys()
    if forbidden:
        raise RuntimeError("Unexpected top-level game module import: " + ", ".join(sorted(forbidden)))
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, choices=(8878, 8879), default=8878)
    args = parser.parse_args()
    listener = None
    for port in dict.fromkeys((args.port, 8879)):
        candidate = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        candidate.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            candidate.bind(("127.0.0.1", port))
            listener = candidate
            break
        except OSError as error:
            candidate.close()
            if error.errno != errno.EADDRINUSE:
                raise SystemExit(f"Cannot bind the isolated QA loopback port: {error}") from error
    if listener is None:
        raise SystemExit("QA ports 8878 and 8879 are occupied; no existing process was contacted or stopped.")
    qa_root = ROOT / ".qa"
    qa_root.mkdir(exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="live-preview-", dir=qa_root) as temporary:
            directory = Path(temporary)
            app = create_fixture(directory, port)
            listener.listen(128)
            server = make_server("127.0.0.1", port, app, threaded=True, fd=listener.fileno())
            listener.close()
            listener = None
            print(f"QA_URL=http://127.0.0.1:{port}/god-barn/", flush=True)
            print(f"QA_DATA={directory}", flush=True)
            print("ISOLATED FIXTURE: real God Barn adapter/UI; fake player/gateway; copied saves only. Control-C stops it.", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
    finally:
        if listener is not None:
            listener.close()


if __name__ == "__main__":
    main()
