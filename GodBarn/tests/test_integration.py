"""Live-adapter tests with a fake game and disposable saves; no game startup."""

import copy
from contextlib import contextmanager
import gzip
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

try:
    from flask import Flask, Response, jsonify, request
except ModuleNotFoundError as error:
    raise unittest.SkipTest("Live integration tests use the game's existing Flask environment.") from error

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from GodBarn.integration import register_god_barn


def save(uid="farm-a", gold=200):
    return {"userInfo": {"player": {"userId": uid, "gold": gold, "cash": 5, "xp": 0,
                                    "energy": 45, "energyMax": 50, "storageData": {},
                                    "energyManager": {"turboChargers": 0}},
                         "attr": {"name": uid}},
            "world": {"sizeX": 50, "sizeY": 50,
                      "objectsArray": [{"id": 1, "className": "Plot", "itemName": "strawberry",
                                        "state": "planted", "plantTime": 100000}]},
            "unknownFeature": {"preserve": [1, "all", "fields"]}}


class FakeCommittedSaveError(OSError):
    pass


class FakePlayer:
    CommittedSaveError = FakeCommittedSaveError
    def __init__(self):
        self.SAVE_LOCK = threading.RLock()
        self.farms = {"farm-a": save(), "farm-b": save("farm-b", 900)}
        self.persisted = copy.deepcopy(self.farms)
        self.fail = False
        self.committed_failure = False

    def all_saves_uids(self):
        return list(self.farms)

    def session(self, uid):
        return self.farms.get(uid)

    @contextmanager
    def village_transaction(self, uid):
        with self.SAVE_LOCK:
            before = copy.deepcopy(self.farms)
            try:
                yield
                if self.fail:
                    raise OSError("Simulated disk failure before commit")
                self.persisted = copy.deepcopy(self.farms)
            except BaseException:
                if not self.committed_failure:
                    self.farms = before
                raise

    def save_session(self, uid):
        if self.committed_failure:
            self.persisted = copy.deepcopy(self.farms)
            raise FakeCommittedSaveError("Simulated durability failure after commit")


class LiveIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="god-barn-live-", dir="/private/tmp" if Path("/private/tmp").is_dir() else None)
        self.root = Path(self.temporary.name)
        data = self.root / "data"
        data.mkdir()
        static = self.root / "static"
        static.mkdir()
        (static / "index.html").write_text("<html><head></head><body>God Barn fixture</body></html>")
        (static / "app.js").write_text("console.log('God Barn')")
        (static / "error.html").write_text((Path(__file__).resolve().parents[1] / "static/error.html").read_text())
        self.game_data = self.root / "game-data"
        assets = self.game_data / "assets" / "animals"
        assets.mkdir(parents=True)
        (assets / "cow-hash.png").write_bytes(b"original game PNG bytes")
        catalog = [
            {"name": "strawberry", "code": "strawberry-code", "type": "seed", "growTime": 1, "plantXp": 1,
             "displayName": "Strawberries", "grantable": True, "hasOriginalThumbnail": True,
             "image": "/static/assets/items/strawberry.png"},
            {"name": "cow", "code": "cow-code", "type": "animal", "displayName": "Cow",
             "grantable": True, "hasOriginalThumbnail": True, "image": "/static/assets/items/cow.png"},
            {"name": "expand58", "code": "expand-code", "type": "change_farm", "subtype": "expand_farm", "squares": 58},
        ]
        with gzip.open(data / "catalog.json.gz", "wt") as output:
            json.dump(catalog, output)
        (data / "rules.json").write_text(json.dumps({"levels": [{"level": 1, "xp": 0}, {"level": 2, "xp": 100}, {"level": 3, "xp": 300}],
                                                    "inGameDaySeconds": 82800, "growMultiplier": 1, "witherMultiplier": 2.2}))
        (data / "asset-map.json").write_text(json.dumps({"static/assets/items/cow.png": "animals/cow-hash.png"}))
        self.player = FakePlayer()
        self.app = Flask(__name__)
        self.app.secret_key = "isolated-test-key"
        self.app.testing = True
        self.gateway_calls = 0

        @self.app.post("/flashservices/gateway.php", endpoint="flashservices_gateway")
        def gateway():
            self.gateway_calls += 1
            payload = request.get_json()
            uid = payload["uid"]
            with self.player.village_transaction(uid):
                self.player.session(uid)["userInfo"]["player"]["gold"] += payload.get("amount", 0)
                self.player.save_session(uid)
            return jsonify(ok=True)

        @self.app.get("/ruffle.html")
        @self.app.get("/play.html")
        def game_page():
            return '<!doctype html><html><head><script id="game-script">window.game=true;</script></head><body>Farm fixture</body></html>'

        def decode(raw):
            payload = json.loads(raw)
            return None, payload["uid"], payload.get("commands", [])
        self.game = SimpleNamespace(BIND_PORT=5501, _decode_gateway=decode)
        self.bundle = SimpleNamespace(DATA_DIR=str(self.game_data), ASSETS_DIR=str(self.game_data / "assets"))
        self.bridge = register_god_barn(self.app, game_server=self.game, player_module=self.player, bundle_module=self.bundle, root=self.root)
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["UID"] = "farm-a"
        # Session transactions default to localhost; make the fake HTTP host
        # agree with the session cookie domain while keeping the expected port.
        self.base = "http://localhost:5501"
        self.state = self.get("/god-barn/api/state").get_json()
        self.csrf = self.state["csrf"]

    def tearDown(self):
        self.temporary.cleanup()

    def get(self, path, **kwargs):
        return self.client.get(path, base_url=self.base, **kwargs)

    def post(self, path, payload, *, csrf=True, headers=None):
        headers = dict(headers or {})
        if csrf:
            headers.setdefault("X-God-Barn-Token", self.csrf)
        return self.client.post(path, json=payload, base_url=self.base, headers=headers)

    def preview(self, amount=1000, state=None):
        state = state or self.get("/god-barn/api/state").get_json()
        response = self.post("/god-barn/api/preview", {"farmId": state["farm"]["id"], "revision": state["farm"]["revision"],
                              "operation": {"type": "balance", "field": "gold", "mode": "add", "amount": amount}})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json(), state

    def apply(self, preview, state):
        return self.post("/god-barn/api/apply", {"farmId": state["farm"]["id"], "revision": state["farm"]["revision"], "token": preview["token"]})

    def test_gift_reveal_retains_recovered_image_and_label_evidence(self):
        item = self.bridge.items["strawberry"]
        item.update(hasOriginalThumbnail=True, artwork={"status": "exact", "logical": "assets/strawberry.png"},
                    labelSource="localization")
        gift = self.bridge._gift_card({"type": "grant", "item": "strawberry", "quantity": 2})
        self.assertEqual(gift["item"]["artwork"], item["artwork"])
        self.assertTrue(gift["item"]["hasOriginalThumbnail"])
        self.assertEqual(gift["item"]["labelSource"], "localization")

    def test_state_uses_live_uid_full_hash_and_does_not_park_on_read(self):
        self.assertEqual(self.state["mode"], "live")
        self.assertTrue(self.state["liveConnection"])
        self.assertEqual(self.state["farm"]["id"], "farm-a")
        self.assertEqual(len(self.state["farm"]["revision"]), 64)
        self.assertEqual(self.state["farm"]["summary"]["coins"], 200)
        self.assertFalse(self.state["parked"])
        self.assertEqual(len(self.state["farms"]), 2)

    def test_preview_apply_snapshot_restore_and_unknown_fields(self):
        before = copy.deepcopy(self.player.farms)
        preview, state = self.preview()
        self.assertEqual(self.player.farms, before)
        applied = self.apply(preview, state)
        self.assertEqual(applied.status_code, 200)
        applied = applied.get_json()
        self.assertEqual(applied["farm"]["summary"]["coins"], 1200)
        self.assertNotEqual(applied["farm"]["revision"], state["farm"]["revision"])
        self.assertTrue(applied["reloadGame"])
        self.assertTrue(applied["committed"])
        self.assertTrue(applied["durabilityConfirmed"])
        self.assertIsNone(applied["durabilityWarning"])
        self.assertEqual(self.player.persisted["farm-a"]["userInfo"]["player"]["gold"], 1200)
        self.assertEqual(self.player.farms["farm-a"]["unknownFeature"], before["farm-a"]["unknownFeature"])
        self.assertEqual(self.player.farms["farm-b"], before["farm-b"])
        snapshot = applied["history"][0]
        self.assertTrue(snapshot["original"])
        original_bytes = (self.bridge.snapshots / (snapshot["id"] + ".json")).read_bytes()
        restored = self.post("/god-barn/api/restore", {"farmId": "farm-a", "revision": applied["farm"]["revision"], "id": snapshot["id"]})
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.get_json()["farm"]["summary"]["coins"], 200)
        self.assertEqual(self.player.farms, before)
        self.assertEqual((self.bridge.snapshots / (snapshot["id"] + ".json")).read_bytes(), original_bytes)

    def test_game_change_after_preview_is_rejected_without_snapshot_or_mutation(self):
        preview, state = self.preview()
        self.player.farms["farm-a"]["unknownFeature"]["newServerField"] = "a full-state conflict"
        response = self.apply(preview, state)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["code"], "stale_revision")
        self.assertEqual(self.player.farms["farm-a"]["userInfo"]["player"]["gold"], 200)
        self.assertEqual(list(self.bridge.snapshots.glob("*.json")), [])

    def test_missing_identity_wrong_farm_and_wrong_snapshot_rejected(self):
        response = self.post("/god-barn/api/preview", {"revision": self.state["farm"]["revision"]})
        self.assertEqual(response.get_json()["code"], "farm_required")
        response = self.post("/god-barn/api/preview", {"farmId": "farm-b", "revision": self.state["farm"]["revision"]})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["code"], "farm_changed")
        preview, state = self.preview()
        applied = self.apply(preview, state).get_json()
        snapshot = applied["history"][0]["id"]
        state_b = self.post("/god-barn/api/select", {"id": "farm-b"}).get_json()
        response = self.post("/god-barn/api/restore", {"farmId": "farm-b", "revision": state_b["farm"]["revision"], "id": snapshot})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["code"], "wrong_farm")

    def test_csrf_host_origin_content_type_and_live_mode_boundaries(self):
        self.assertEqual(self.post("/god-barn/api/select", {"id": "farm-b"}, csrf=False).status_code, 403)
        self.assertEqual(self.post("/god-barn/api/select", {"id": "farm-b"}, headers={"Origin": "https://example.test"}).status_code, 403)
        self.assertEqual(self.client.get("/god-barn/api/state", base_url="http://example.test:5501").status_code, 403)
        self.assertEqual(self.client.post("/god-barn/api/select", data="{}", base_url=self.base, headers={"X-God-Barn-Token": self.csrf}).status_code, 415)
        self.assertEqual(self.get("/god-barn/resume?uid=farm-a", headers={"Sec-Fetch-Site": "cross-site"}).status_code, 403)
        for path in ("/god-barn/api/demo", "/god-barn/api/import"):
            response = self.post(path, {})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.get_json()["code"], "live_mode")

    def configured_app(self, origins):
        app = Flask("god-barn-configured-origin-test")
        app.secret_key = "separate-origin-test-key"
        app.testing = True
        app.config["FARMVILLAGE_TRUSTED_ORIGINS"] = origins
        app.add_url_rule("/flashservices/gateway.php", "flashservices_gateway", lambda: jsonify(ok=True), methods=["POST"])
        register_god_barn(app, game_server=self.game, player_module=self.player, bundle_module=self.bundle, root=self.root)
        return app

    def test_configured_lan_origin_can_use_barn_with_the_same_csrf_protection(self):
        origin = "http://192.168.50.80:5501"
        client = self.configured_app([origin]).test_client()
        response = client.get("/god-barn/api/state", base_url=origin)
        self.assertEqual(response.status_code, 200)
        csrf = response.get_json()["csrf"]
        with client.get("/god-barn/", base_url=origin) as response:
            self.assertEqual(response.status_code, 200)
        response = client.post("/god-barn/api/select", json={"id": "farm-b"}, base_url=origin,
                               headers={"Origin": origin, "X-God-Barn-Token": csrf})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["farm"]["id"], "farm-b")
        response = client.post("/god-barn/api/select", json={"id": "farm-a"}, base_url=origin,
                               headers={"Origin": origin})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["code"], "csrf")
        self.assertEqual(client.get("/god-barn/api/state", base_url=self.base).status_code, 200)

    def test_configured_lan_origin_keeps_host_origin_and_cross_site_checks(self):
        origin = "http://192.168.50.80:5501"
        client = self.configured_app([origin]).test_client()
        for other_host in ("http://192.168.2.81:5501", "http://192.168.50.80:5502", "http://example.test:5501"):
            with self.subTest(host=other_host):
                response = client.get("/god-barn/api/state", base_url=other_host)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.get_json()["code"], "forbidden_host")
        for other_origin in ("https://192.168.50.80:5501", "http://192.168.2.81:5501", origin + "/"):
            with self.subTest(origin=other_origin):
                response = client.get("/god-barn/api/state", base_url=origin, headers={"Origin": other_origin})
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.get_json()["code"], "forbidden_origin")
        response = client.get("/god-barn/", base_url=origin, headers={"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["code"], "forbidden_origin")

    def test_malformed_trusted_origins_fail_registration(self):
        invalid = ["http://192.168.50.80:5501", None, [None], ["*"], ["http://*.example.test:5501"],
                   ["http://192.168.50.80:5501/"], ["http://user:password@192.168.50.80:5501"],
                   ["http://192.168.50.80:5501?"], ["http://192.168.50.80:5501#"],
                   ["http://192.168.50.80:65536"], ["http://192.168.50.80:"],
                   ["http://example..test:5501"], ["http://192.168.50.80:5501\n"]]
        for origins in invalid:
            with self.subTest(origins=origins):
                with self.assertRaisesRegex(ValueError, "FARMVILLAGE_TRUSTED_ORIGINS"):
                    self.configured_app(origins)

    def test_transaction_failure_restores_live_save(self):
        preview, state = self.preview()
        self.player.fail = True
        response = self.apply(preview, state)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json()["code"], "storage_error")
        self.assertEqual(self.player.farms["farm-a"]["userInfo"]["player"]["gold"], 200)
        self.assertNotIn("farm-a", self.bridge.rotated)
        self.assertEqual(len(list(self.bridge.snapshots.glob("*.json"))), 1)

    def test_committed_durability_failure_still_rotates_epoch(self):
        preview, state = self.preview()
        self.player.committed_failure = True
        response = self.apply(preview, state)
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertTrue(result["committed"])
        self.assertFalse(result["durabilityConfirmed"])
        self.assertIn("change is applied", result["durabilityWarning"])
        self.assertIn("Do not repeat", result["durabilityWarning"])
        self.assertIn(result["durabilityWarning"], result["lastAction"]["warnings"])
        self.assertEqual(result["farm"]["summary"]["coins"], 1200)
        self.assertNotEqual(result["farm"]["revision"], state["farm"]["revision"])
        self.assertNotIn(preview["token"], self.bridge.previews)
        self.assertEqual(self.player.farms["farm-a"]["userInfo"]["player"]["gold"], 1200)
        self.assertIn("farm-a", self.bridge.rotated)

    def test_committed_noop_consumes_token_even_when_revision_is_unchanged(self):
        preview, state = self.preview(amount=0)
        self.player.committed_failure = True
        response = self.apply(preview, state)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["committed"])
        self.assertFalse(response.get_json()["durabilityConfirmed"])
        self.assertEqual(response.get_json()["farm"]["revision"], state["farm"]["revision"])
        repeated = self.apply(preview, state)
        self.assertEqual(repeated.status_code, 409)
        self.assertEqual(repeated.get_json()["code"], "preview_expired")
        self.assertEqual(self.player.farms["farm-a"]["userInfo"]["player"]["gold"], 200)

    def test_committed_restore_returns_fresh_state_with_durability_warning(self):
        preview, state = self.preview()
        applied = self.apply(preview, state).get_json()
        self.player.committed_failure = True
        response = self.post("/god-barn/api/restore", {"farmId": "farm-a", "revision": applied["farm"]["revision"],
                             "id": applied["history"][0]["id"]})
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertTrue(result["committed"])
        self.assertFalse(result["durabilityConfirmed"])
        self.assertEqual(result["farm"]["summary"]["coins"], 200)
        self.assertEqual(result["farm"]["revision"], state["farm"]["revision"])
        self.assertIn(result["durabilityWarning"], result["lastAction"]["warnings"])

    def test_park_and_epoch_guard_fence_old_game_requests(self):
        old_epoch = self.bridge._epoch("farm-a")
        response = self.client.post("/flashservices/gateway.php", json={"uid": "farm-a"}, base_url=self.base)
        self.assertEqual(response.status_code, 200)  # first legacy page remains compatible
        with self.get("/god-barn/") as response:
            self.assertEqual(response.status_code, 200)
        response = self.client.post("/flashservices/gateway.php", json={"uid": "farm-a", "amount": 1}, base_url=self.base,
                                    headers={"X-God-Barn-Epoch": old_epoch})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["code"], "farm_parked")
        preview, state = self.preview()
        self.assertEqual(self.apply(preview, state).status_code, 200)
        self.assertEqual(self.get("/god-barn/resume?uid=farm-a").status_code, 302)
        for headers in ({}, {"X-God-Barn-Epoch": old_epoch}):
            response = self.client.post("/flashservices/gateway.php", json={"uid": "farm-a", "amount": 1}, base_url=self.base, headers=headers)
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.get_json()["code"], "stale_game_page")
        response = self.client.post("/flashservices/gateway.php", json={"uid": "farm-a", "amount": 1}, base_url=self.base,
                                    headers={"X-God-Barn-Epoch": self.bridge._epoch("farm-a")})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.player.farms["farm-a"]["userInfo"]["player"]["gold"], 1201)
        self.assertEqual(self.gateway_calls, 2)

    def test_fresh_page_injects_epoch_before_game_and_resume_updates_uid(self):
        with self.get("/god-barn/") as response:
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.get("/god-barn/resume?uid=missing").status_code, 404)
        self.assertEqual(self.get("/god-barn/resume?uid=farm-b").status_code, 302)
        html = self.get("/ruffle.html").get_data(as_text=True)
        self.assertLess(html.index('id="god-barn-game-epoch"'), html.index('id="game-script"'))
        self.assertIn(self.bridge._epoch("farm-b"), html)
        self.assertIn("XMLHttpRequest", html)
        self.assertIn("X-God-Barn-Epoch", html)
        self.assertFalse(self.bridge.parked)

    def test_browser_game_pages_link_to_barn_in_the_same_tab(self):
        for page in ("/ruffle.html", "/play.html"):
            with self.subTest(page=page):
                html = self.get(page).get_data(as_text=True)
                self.assertIn('id="god-barn-browser-navigation"', html)
                self.assertIn('href="/god-barn/" target="_self"', html)
                self.assertIn("Your farm pauses while you edit", html)
                self.assertLess(html.index('id="god-barn-game-epoch"'), html.index('id="game-script"'))
        with self.get("/god-barn/") as response:
            self.assertNotIn('id="god-barn-browser-navigation"', response.get_data(as_text=True))

    def test_native_game_page_keeps_the_native_toolbar_and_epoch(self):
        self.game.NATIVE_WRAPPER = True
        html = self.get("/ruffle.html").get_data(as_text=True)
        self.assertIn('id="god-barn-game-epoch"', html)
        self.assertNotIn("god-barn-browser-navigation", html)

    def test_loading_either_game_page_resumes_and_fences_pre_park_requests(self):
        for page in ("/ruffle.html", "/play.html"):
            with self.subTest(page=page):
                old_epoch = self.bridge._epoch("farm-a")
                with self.get("/god-barn/") as response:
                    self.assertEqual(response.status_code, 200)
                response = self.get(page)
                self.assertEqual(response.status_code, 200)
                current_epoch = self.bridge._epoch("farm-a")
                self.assertNotEqual(current_epoch, old_epoch)
                self.assertNotIn("farm-a", self.bridge.parked)
                self.assertNotIn("farm-a", self.bridge.park_owners)
                self.assertIn(current_epoch, response.get_data(as_text=True))
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                before = copy.deepcopy(self.player.farms)
                stale = self.client.post("/flashservices/gateway.php", json={"uid": "farm-a", "amount": 1},
                                         base_url=self.base, headers={"X-God-Barn-Epoch": old_epoch})
                self.assertEqual(stale.status_code, 409)
                self.assertEqual(stale.get_json()["code"], "stale_game_page")
                self.assertEqual(self.player.farms, before)
                current = self.client.post("/flashservices/gateway.php", json={"uid": "farm-a", "amount": 1},
                                           base_url=self.base, headers={"X-God-Barn-Epoch": current_epoch})
                self.assertEqual(current.status_code, 200)
                self.assertEqual(self.player.persisted["farm-a"]["userInfo"]["player"]["gold"],
                                 before["farm-a"]["userInfo"]["player"]["gold"] + 1)

    def test_another_game_session_resumes_only_its_selected_farm(self):
        with self.get("/god-barn/") as response:
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.post("/god-barn/api/select", {"id": "farm-b"}).status_code, 200)
        owners = dict(self.bridge.park_owners)
        second = self.app.test_client()
        with second.session_transaction() as session:
            session["UID"] = "farm-a"
        old_epochs = {uid: self.bridge._epoch(uid) for uid in ("farm-a", "farm-b")}
        response = second.get("/ruffle.html", base_url=self.base)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.bridge.parked, {"farm-b"})
        self.assertEqual(self.bridge.park_owners, {"farm-b": owners["farm-b"]})
        self.assertNotEqual(self.bridge._epoch("farm-a"), old_epochs["farm-a"])
        self.assertEqual(self.bridge._epoch("farm-b"), old_epochs["farm-b"])
        self.assertIn(self.bridge._epoch("farm-a"), response.get_data(as_text=True))

    def test_reloading_current_game_pages_does_not_rotate_the_epoch(self):
        epoch = self.bridge._epoch("farm-a")
        with patch.object(self.bridge, "_rotate", wraps=self.bridge._rotate) as rotate:
            for page in ("/ruffle.html", "/play.html", "/ruffle.html"):
                self.assertIn(epoch, self.get(page).get_data(as_text=True))
            rotate.assert_not_called()
            with self.get("/god-barn/") as response:
                self.assertEqual(response.status_code, 200)
            self.assertEqual(self.get("/ruffle.html").status_code, 200)
            resumed_epoch = self.bridge._epoch("farm-a")
            self.assertNotEqual(resumed_epoch, epoch)
            self.assertIn(resumed_epoch, self.get("/ruffle.html").get_data(as_text=True))
            self.assertIn(resumed_epoch, self.get("/play.html").get_data(as_text=True))
            rotate.assert_called_once_with("farm-a")

    def test_non_game_responses_and_cross_site_probes_do_not_resume(self):
        with self.get("/god-barn/") as response:
            self.assertEqual(response.status_code, 200)
        epoch = self.bridge._epoch("farm-a")
        game_page = self.app.view_functions["game_page"]
        for status, mimetype in ((302, "text/html"), (404, "text/html"), (200, "text/plain")):
            with self.subTest(status=status, mimetype=mimetype):
                self.app.view_functions["game_page"] = lambda: Response("fixture", status=status, mimetype=mimetype)
                self.get("/ruffle.html")
                self.assertIn("farm-a", self.bridge.parked)
                self.assertEqual(self.bridge._epoch("farm-a"), epoch)
        self.app.view_functions["game_page"] = game_page
        for headers in ({"Sec-Fetch-Site": "cross-site"}, {"Origin": "https://example.test"}):
            with self.subTest(headers=headers):
                self.get("/ruffle.html", headers=headers)
                self.assertIn("farm-a", self.bridge.parked)
                self.assertEqual(self.bridge._epoch("farm-a"), epoch)
        self.client.head("/ruffle.html", base_url=self.base)
        self.assertIn("farm-a", self.bridge.parked)
        with self.client.session_transaction() as session:
            session["UID"] = "missing"
        self.get("/ruffle.html")
        self.assertIn("farm-a", self.bridge.parked)
        self.assertEqual(self.bridge._epoch("farm-a"), epoch)

    def test_apply_reparks_a_resumed_farm_before_snapshot_and_write(self):
        preview, state = self.preview()
        self.get("/ruffle.html")
        resumed_epoch = self.bridge._epoch("farm-a")
        self.assertNotIn("farm-a", self.bridge.parked)
        snapshot = self.bridge._snapshot

        def snapshot_while_parked(*args, **kwargs):
            self.assertIn("farm-a", self.bridge.parked)
            self.assertEqual(self.bridge.park_owners["farm-a"], self.csrf)
            return snapshot(*args, **kwargs)

        with patch.object(self.bridge, "_snapshot", side_effect=snapshot_while_parked):
            applied = self.apply(preview, state)
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(self.player.persisted["farm-a"]["userInfo"]["player"]["gold"], 1200)
        rejected = self.client.post("/flashservices/gateway.php", json={"uid": "farm-a", "amount": 1},
                                    base_url=self.base, headers={"X-God-Barn-Epoch": resumed_epoch})
        self.assertEqual(rejected.status_code, 409)
        self.assertEqual(rejected.get_json()["code"], "farm_parked")
        self.assertEqual(self.get("/ruffle.html").status_code, 200)
        self.assertNotIn("farm-a", self.bridge.parked)
        stale = self.client.post("/flashservices/gateway.php", json={"uid": "farm-a", "amount": 1},
                                 base_url=self.base, headers={"X-God-Barn-Epoch": resumed_epoch})
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.get_json()["code"], "stale_game_page")
        self.assertEqual(self.player.persisted["farm-a"]["userInfo"]["player"]["gold"], 1200)

    def test_game_save_after_resume_rejects_old_apply_without_parking_again(self):
        preview, state = self.preview()
        self.get("/ruffle.html")
        epoch = self.bridge._epoch("farm-a")
        saved = self.client.post("/flashservices/gateway.php", json={"uid": "farm-a", "amount": 7},
                                 base_url=self.base, headers={"X-God-Barn-Epoch": epoch})
        self.assertEqual(saved.status_code, 200)
        response = self.apply(preview, state)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["code"], "stale_revision")
        self.assertNotIn("farm-a", self.bridge.parked)
        self.assertEqual(self.bridge._epoch("farm-a"), epoch)
        self.assertEqual(self.player.persisted["farm-a"]["userInfo"]["player"]["gold"], 207)
        self.assertEqual(list(self.bridge.snapshots.glob("*.json")), [])

    def test_expired_apply_and_wrong_restore_do_not_park_a_resumed_game(self):
        preview, state = self.preview()
        applied = self.apply(preview, state).get_json()
        state_b = self.post("/god-barn/api/select", {"id": "farm-b"}).get_json()
        expired_preview, state_b = self.preview(state=state_b)
        self.bridge.previews[expired_preview["token"]]["created"] = 0
        with self.client.session_transaction() as session:
            session["UID"] = "farm-b"
        self.get("/ruffle.html")
        epoch = self.bridge._epoch("farm-b")
        wrong = self.post("/god-barn/api/restore", {"farmId": "farm-b", "revision": state_b["farm"]["revision"],
                          "id": applied["history"][0]["id"]})
        self.assertEqual(wrong.status_code, 409)
        self.assertEqual(wrong.get_json()["code"], "wrong_farm")
        self.assertNotIn("farm-b", self.bridge.parked)
        expired = self.post("/god-barn/api/apply", {"farmId": "farm-b", "revision": state_b["farm"]["revision"],
                            "token": expired_preview["token"]})
        self.assertEqual(expired.status_code, 409)
        self.assertEqual(expired.get_json()["code"], "preview_expired")
        self.assertNotIn("farm-b", self.bridge.parked)
        self.assertEqual(self.bridge._epoch("farm-b"), epoch)

    def test_page_resume_does_not_transfer_editor_or_preview_permissions(self):
        preview, state = self.preview()
        second = self.app.test_client()
        with second.session_transaction() as session:
            session["UID"] = "farm-a"
        second.get("/ruffle.html", base_url=self.base)
        other_state = second.get("/god-barn/api/state", base_url=self.base).get_json()
        replay = second.post("/god-barn/api/apply", base_url=self.base,
                             headers={"X-God-Barn-Token": other_state["csrf"]},
                             json={"farmId": "farm-a", "revision": state["farm"]["revision"], "token": preview["token"]})
        self.assertEqual(replay.status_code, 409)
        self.assertEqual(replay.get_json()["code"], "preview_expired")
        self.assertNotIn("farm-a", self.bridge.parked)
        with second.get("/god-barn/", base_url=self.base) as response:
            self.assertEqual(response.status_code, 200)
        response = self.apply(preview, state)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["code"], "farm_in_use")
        self.assertEqual(self.bridge.park_owners["farm-a"], other_state["csrf"])
        self.assertEqual(self.player.persisted["farm-a"]["userInfo"]["player"]["gold"], 200)
        self.assertEqual(list(self.bridge.snapshots.glob("*.json")), [])

    def test_other_session_cannot_take_over_or_resume_an_open_farm(self):
        with self.get("/god-barn/") as response:
            self.assertEqual(response.status_code, 200)
        second = self.app.test_client()
        with second.session_transaction() as session:
            session["UID"] = "farm-a"
        other_state = second.get("/god-barn/api/state", base_url=self.base).get_json()
        token = {"X-God-Barn-Token": other_state["csrf"]}
        for path in ("/god-barn/", "/god-barn/park?uid=farm-a", "/god-barn/resume?uid=farm-a"):
            response = second.get(path, base_url=self.base)
            self.assertEqual(response.status_code, 409, path)
            self.assertEqual(response.get_json()["code"], "farm_in_use")
        response = second.post("/god-barn/api/preview", base_url=self.base, headers=token,
                               json={"farmId": "farm-a", "revision": other_state["farm"]["revision"],
                                     "operation": {"type": "balance", "field": "gold", "mode": "add", "amount": 1}})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["code"], "farm_in_use")
        self.assertEqual(self.player.farms["farm-a"]["userInfo"]["player"]["gold"], 200)
        self.assertIn("farm-a", self.bridge.parked)
        self.assertEqual(self.get("/god-barn/resume?uid=farm-a").status_code, 302)
        with second.get("/god-barn/", base_url=self.base) as response:
            self.assertEqual(response.status_code, 200)

    def test_resume_releases_only_this_sessions_farms(self):
        with self.get("/god-barn/") as response:
            self.assertEqual(response.status_code, 200)
        second = self.app.test_client()
        with second.session_transaction() as session:
            session["UID"] = "farm-b"
        with second.get("/god-barn/", base_url=self.base) as response:
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.bridge.parked, {"farm-a", "farm-b"})
        self.assertEqual(self.get("/god-barn/resume?uid=farm-a").status_code, 302)
        self.assertEqual(self.bridge.parked, {"farm-b"})
        response = self.client.post("/flashservices/gateway.php", json={"uid": "farm-b", "amount": 1},
                                    base_url=self.base, headers={"X-God-Barn-Epoch": self.bridge._epoch("farm-b")})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["code"], "farm_parked")
        self.assertEqual(second.get("/god-barn/resume?uid=farm-b", base_url=self.base).status_code, 302)
        self.assertFalse(self.bridge.parked)

    def test_preview_claims_farm_and_noop_resume_fences_the_previous_game_page(self):
        old_epoch = self.bridge._epoch("farm-a")
        preview, state = self.preview()
        self.assertIn("farm-a", self.bridge.parked)
        self.assertEqual(self.player.farms["farm-a"]["userInfo"]["player"]["gold"], 200)
        self.assertEqual(self.get("/god-barn/resume?uid=farm-a").status_code, 302)
        self.assertNotEqual(self.bridge._epoch("farm-a"), old_epoch)
        response = self.client.post("/flashservices/gateway.php", json={"uid": "farm-a", "amount": 1},
                                    base_url=self.base, headers={"X-God-Barn-Epoch": old_epoch})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["code"], "stale_game_page")

    def test_neighbor_action_cannot_write_a_parked_host_farm(self):
        with self.get("/god-barn/") as response:
            self.assertEqual(response.status_code, 200)
        before = copy.deepcopy(self.player.farms)
        response = self.client.post("/flashservices/gateway.php", base_url=self.base,
                                    json={"uid": "farm-b", "amount": 1, "commands": [
                                        {"functionName": "WorldService.performAction", "params": [
                                            "neighborAct", {"id": 1}, [{"hostId": "farm-a", "actionType": "harvest"}]]}]})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["code"], "farm_parked")
        self.assertEqual(self.gateway_calls, 0)
        self.assertEqual(self.player.farms, before)

    def test_catalog_asset_map_exports_and_private_paths(self):
        result = self.get("/god-barn/api/catalog?names=cow,strawberry").get_json()
        self.assertEqual(result["total"], 2)
        self.assertTrue(all(item["image"].startswith("/god-barn/static/assets/") for item in result["items"]))
        self.assertEqual(self.get("/god-barn/api/catalog?type=expand_farm").get_json()["expansionSizes"], [58])
        with self.get("/god-barn/static/assets/items/cow.png") as response:
            self.assertEqual(response.get_data(), b"original game PNG bytes")
        with self.get("/god-barn/static/app.js") as response:
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.get("/god-barn/static/../data/rules.json").status_code, 404)
        self.assertEqual(self.get("/god-barn/api/export").status_code, 400)
        exported = self.get("/god-barn/api/export?id=farm-b")
        self.assertEqual(exported.get_json()["userInfo"]["player"]["userId"], "farm-b")
        self.assertIn("attachment", exported.headers["Content-Disposition"])

    def test_discovery_search_facets_artwork_and_sort_are_exposed(self):
        self.bridge.catalog.append({"name": "pinkhat", "displayName": "Pink Party Hat", "code": "H7",
                                    "type": "consumable", "subtype": "clothes", "grantable": False,
                                    "labelSource": "localization", "hasOriginalThumbnail": True,
                                    "image": "/god-barn/static/assets/items/hat.png",
                                    "artwork": {"status": "exact", "logical": "assets/clothes/pink_hat.png"}})
        result = self.get("/god-barn/api/catalog?q=H7+pink&artwork=exact&sort=name").get_json()
        self.assertEqual(result["items"][0]["name"], "pinkhat")
        self.assertEqual(result["coverage"]["total"], 4)
        self.assertEqual(result["resultCoverage"]["localizedNames"], 1)
        self.assertEqual(result["subtypes"], [{"subtype": "clothes", "count": 1}])
        self.assertEqual(self.get("/god-barn/api/catalog?q=clothes+hat").get_json()["total"], 1)
        for query in ("artwork=invalid", "sort=invalid"):
            self.assertEqual(self.get("/god-barn/api/catalog?" + query).status_code, 400)

    def test_seasonal_catalog_uses_the_same_read_only_calendar_contract(self):
        self.bridge.items["strawberry"]["archive"] = {"availability": {"start": "2011-10-05", "end": "2011-11-10"}}
        self.bridge.catalog.extend([
            {"name": "winter", "type": "seed", "archive": {"availability": {"start": "2010-12-15", "end": "2011-01-10"}}},
            {"name": "unknown", "type": "seed"},
        ])
        before, farms_before = copy.deepcopy(self.bridge.catalog), copy.deepcopy(self.player.farms)
        response = self.get("/god-barn/api/catalog?calendarDate=2026-10-21&seasonal=in")
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertEqual([item["name"] for item in result["items"]], ["strawberry"])
        self.assertEqual(result["items"][0]["seasonal"]["status"], "in")
        self.assertEqual(result["calendar"]["date"], "2026-10-21")
        self.assertTrue(result["calendar"]["override"])
        self.assertEqual(result["seasonalCounts"], {"in": 1, "out": 1, "known": 2, "unknown": 1, "total": 3})
        nonseed = self.get("/god-barn/api/catalog?calendarDate=2026-10-21&type=animal&q=Cow").get_json()
        self.assertEqual(nonseed["seasonalCounts"], result["seasonalCounts"])
        self.assertNotIn("seasonal", nonseed["items"][0])
        self.assertEqual(self.bridge.catalog, before)
        self.assertEqual(self.player.farms, farms_before)
        for query in ("calendarDate=2026-02-30", "seasonal=summer"):
            with self.subTest(query=query):
                self.assertEqual(self.get("/god-barn/api/catalog?" + query).status_code, 400)

    def test_registration_is_idempotent(self):
        again = register_god_barn(self.app, game_server=self.game, player_module=self.player, bundle_module=self.bundle, root=self.root)
        self.assertIs(again, self.bridge)

    def test_opening_barn_follows_current_game_uid(self):
        with self.client.session_transaction() as session:
            session["GOD_BARN_UID"] = "farm-a"
            session["UID"] = "farm-b"
        with self.get("/god-barn/") as response:
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.get("/god-barn/api/state").get_json()["farm"]["id"], "farm-b")
        self.assertIn("farm-b", self.bridge.parked)

    def test_mapped_asset_symlinks_cannot_escape_game_asset_directory(self):
        original = self.game_data / "assets" / "animals" / "cow-hash.png"
        original.unlink()
        outside = self.root / "private-do-not-serve.txt"
        outside.write_text("private fixture")
        original.symlink_to(outside)
        self.assertEqual(self.get("/god-barn/static/assets/items/cow.png").status_code, 404)

    def test_snapshot_failure_prevents_live_mutation(self):
        preview, state = self.preview()
        with patch("GodBarn.integration._atomic", side_effect=OSError("Simulated snapshot write failure")):
            response = self.apply(preview, state)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.player.farms["farm-a"]["userInfo"]["player"]["gold"], 200)
        self.assertEqual(self.player.persisted["farm-a"]["userInfo"]["player"]["gold"], 200)
        self.assertFalse(self.bridge.rotated)

    def test_gateway_gate_check_waits_for_the_same_save_lock(self):
        attempted = threading.Event()
        actual_lock = self.player.SAVE_LOCK
        class ObservedLock:
            def __enter__(self):
                attempted.set()
                return actual_lock.__enter__()
            def __exit__(self, *args):
                return actual_lock.__exit__(*args)
        self.bridge.lock = ObservedLock()
        responses = []
        def gateway_request():
            with self.app.test_client() as client:
                responses.append(client.post("/flashservices/gateway.php", json={"uid": "farm-a", "amount": 1},
                                             base_url=self.base).status_code)
        with actual_lock:
            worker = threading.Thread(target=gateway_request)
            worker.start()
            self.assertTrue(attempted.wait(timeout=2))
            self.assertEqual(self.gateway_calls, 0)
            self.bridge.parked.add("farm-a")
        worker.join(timeout=3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(responses, [409])
        self.assertEqual(self.gateway_calls, 0)
        self.assertEqual(self.player.farms["farm-a"]["userInfo"]["player"]["gold"], 200)

    def test_branded_missing_page_keeps_api_and_original_game_errors_separate(self):
        response = self.get("/god-barn/lost-pasture")
        self.assertEqual(response.status_code, 404)
        html = response.get_data(as_text=True)
        self.assertEqual(response.mimetype, "text/html")
        self.assertIn("The cows deny everything", html)
        self.assertIn('href="/god-barn/"', html)
        self.assertIn('/god-barn/static/assets/ui/cow.png', html)
        self.assertNotIn("__BASE__", html)
        api = self.get("/god-barn/api/unknown-endpoint")
        self.assertEqual(api.status_code, 404)
        self.assertEqual(api.get_json()["code"], "not_found")
        original = self.get("/unrelated-game-route")
        self.assertEqual(original.status_code, 404)
        self.assertNotIn("The cows deny everything", original.get_data(as_text=True))

    def test_branded_html_server_error_and_json_api_server_error(self):
        self.app.testing = False
        self.app.logger.disabled = True
        with patch("GodBarn.integration.send_from_directory", side_effect=RuntimeError("Isolated page failure")):
            response = self.get("/god-barn/")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.mimetype, "text/html")
        self.assertIn("The tractor ate a server gremlin", response.get_data(as_text=True))
        self.assertNotIn("Isolated page failure", response.get_data(as_text=True))
        with patch.object(self.bridge.engine, "summarize", side_effect=RuntimeError("Isolated API failure")):
            response = self.get("/god-barn/api/state")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json()["code"], "internal_error")


if __name__ == "__main__":
    unittest.main()
