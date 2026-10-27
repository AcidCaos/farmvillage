"""Integration checks for the isolated copied-save server; no game requests."""

import copy
import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import APIError, GodBarn, GodBarnServer, atomic_json


def farm_save():
    return {
        "version": 99,
        "userInfo": {
            "player": {"userId": "copied-user-42", "gold": 1000, "cash": 25,
                       "xp": 60, "energy": 20, "turboChargers": 3,
                       "storageData": {"giftbox": {}}},
            "attr": {"name": "Copied Clover Farm"},
        },
        "world": {"sizeX": 24, "sizeY": 24, "objectsArray": []},
        "unknownFeature": {"preserve": ["this", 17]},
    }


class FakeEngine:
    def validate_save(self, save):
        pass

    def summarize(self, save, now=None):
        player = save["userInfo"]["player"]
        return {"name": save["userInfo"]["attr"]["name"], "uid": player["userId"],
                "gold": player["gold"], "cash": player["cash"], "xp": player["xp"],
                "level": 2, "energy": player["energy"], "energyMax": 30,
                "turboChargers": player["turboChargers"],
                "plots": [{"id": 1, "phase": "grown"}, {"id": 2, "phase": "withered"}],
                "inventoryCount": 9, "objectCount": 4}

    def apply(self, save, operation, now=None):
        result = copy.deepcopy(save)
        if operation.get("type") != "coins":
            raise ValueError("Unknown test operation")
        amount = operation.get("amount", 0)
        result["userInfo"]["player"]["gold"] += amount
        if operation.get("changeIdentity"):
            result["userInfo"]["player"]["userId"] = "another-user"
        return {"save": result, "summary": f"Added {amount} coins",
                "changes": [{"field": "gold", "before": 1000, "after": 1000 + amount}],
                "warnings": []}


class CompanionFixture(unittest.TestCase):
    def setUp(self):
        # /private/tmp avoids macOS's symlinked /tmp directory.
        temporary_root = "/private/tmp" if Path("/private/tmp").is_dir() else None
        self.temporary = tempfile.TemporaryDirectory(prefix="god-barn-tests-", dir=temporary_root)
        self.base = Path(self.temporary.name)
        self.root = self.base / "app"
        (self.root / "data").mkdir(parents=True)
        (self.root / "static").mkdir()
        (self.root / "assets").mkdir()
        (self.root / "static" / "index.html").write_text("<html>God Barn test</html>")
        (self.root / "static" / "app.js").write_text("console.log('local companion')")
        (self.root / "static" / "error.html").write_text((Path(__file__).resolve().parents[1] / "static/error.html").read_text())
        (self.root / "assets" / "coin.png").write_bytes(b"fake local asset")
        self.catalog = [
            {"name": "strawberry", "displayName": "Strawberries", "type": "seed",
             "grantable": False, "image": "assets/coin.png"},
            {"name": "tractor", "displayName": "Old Red Tractor", "type": "vehicle",
             "grantable": True, "image": "/assets/coin.png"},
            {"name": "cow", "displayName": "Dairy Cow", "type": "animal",
             "grantable": True, "image": "https://example.test/cow.png"},
        ]
        atomic_json(self.root / "data" / "catalog.json", self.catalog)
        atomic_json(self.root / "data" / "rules.json", {"test": True})
        atomic_json(self.root / "data" / "bootstrap-save.json", farm_save())
        self.workspace = self.base / "workspace"
        self.app = GodBarn(self.root, self.workspace, FakeEngine())

    def tearDown(self):
        self.temporary.cleanup()


class WorkspaceTests(CompanionFixture):
    def test_gift_reveal_retains_recovered_image_and_label_evidence(self):
        item = self.app.items_by_name["tractor"]
        item.update(hasOriginalThumbnail=True, artwork={"status": "exact", "logical": "assets/tractor.png"},
                    labelSource="localization")
        gift = self.app._gift_card({"type": "grant", "item": "tractor", "quantity": 2})
        self.assertEqual(gift["item"]["artwork"], item["artwork"])
        self.assertTrue(gift["item"]["hasOriginalThumbnail"])
        self.assertEqual(gift["item"]["labelSource"], "localization")

    def test_demo_copies_bootstrap_and_preserves_identity(self):
        state = self.app.state()
        self.assertEqual(state["farm"]["revision"], 1)
        self.assertEqual(state["farm"]["save"], farm_save())
        self.assertFalse(state["liveConnection"])
        self.assertEqual(state["mode"], "copied-save")
        self.assertEqual(state["farm"]["summary"]["coins"], 1000)
        self.assertEqual(state["farm"]["summary"]["ready"], 1)
        self.assertEqual(state["farm"]["summary"]["withered"], 1)
        self.assertTrue(state["history"][0]["original"])

    def test_preview_apply_restore_and_original_are_independent(self):
        original_bytes = (self.root / "data" / "bootstrap-save.json").read_bytes()
        original_snapshot = self.app.state()["history"][0]["id"]
        original_snapshot_path = self.workspace / "originals" / (original_snapshot + ".json")
        immutable = original_snapshot_path.read_bytes()
        preview = self.app.preview({"type": "coins", "amount": 500}, 1, farm_id=self.app.selected)
        self.assertEqual(preview["summaryAfter"]["coins"], 1500)
        self.assertEqual(self.app.state()["farm"]["summary"]["coins"], 1000)
        state = self.app.apply(preview["token"], 1, farm_id=self.app.selected)
        self.assertEqual(state["farm"]["revision"], 2)
        self.assertEqual(state["farm"]["summary"]["coins"], 1500)
        self.assertEqual(state["farm"]["save"]["unknownFeature"], farm_save()["unknownFeature"])
        self.assertEqual(state["farm"]["save"]["userInfo"]["player"]["userId"], "copied-user-42")
        restored = self.app.restore(original_snapshot, 2, farm_id=self.app.selected)
        self.assertEqual(restored["farm"]["summary"]["coins"], 1000)
        self.assertEqual(restored["farm"]["revision"], 3)
        self.assertEqual(len(restored["history"]), 3)
        self.assertEqual(original_snapshot_path.read_bytes(), immutable)
        self.assertEqual((self.root / "data" / "bootstrap-save.json").read_bytes(), original_bytes)

    def test_preview_is_single_use_and_revision_bound(self):
        preview_a = self.app.preview({"type": "coins", "amount": 3}, 1, farm_id=self.app.selected)
        preview_b = self.app.preview({"type": "coins", "amount": 7}, 1, farm_id=self.app.selected)
        self.app.apply(preview_a["token"], 1, farm_id=self.app.selected)
        with self.assertRaises(APIError) as raised:
            self.app.apply(preview_b["token"], 1, farm_id=self.app.selected)
        self.assertEqual(raised.exception.code, "stale_revision")
        with self.assertRaises(APIError) as raised:
            self.app.apply(preview_a["token"], 2, farm_id=self.app.selected)
        self.assertEqual(raised.exception.code, "preview_expired")

    def test_expired_preview_and_identity_changes_are_rejected(self):
        preview = self.app.preview({"type": "coins", "amount": 1}, 1, farm_id=self.app.selected)
        self.app.previews[preview["token"]]["created"] -= 10000
        with self.assertRaises(APIError) as raised:
            self.app.apply(preview["token"], 1, farm_id=self.app.selected)
        self.assertEqual(raised.exception.code, "preview_expired")
        with self.assertRaisesRegex(APIError, "identity"):
            self.app.preview({"type": "coins", "amount": 1, "changeIdentity": True}, 1, farm_id=self.app.selected)
        self.assertEqual(self.app.state()["farm"]["revision"], 1)

    def test_import_never_uses_source_filename_as_path(self):
        source = farm_save()
        state = self.app.import_save("../../outside.json", source)
        source["userInfo"]["player"]["gold"] = 1
        self.assertEqual(state["farm"]["filename"], "outside.json")
        self.assertEqual(state["farm"]["summary"]["coins"], 1000)
        self.assertFalse((self.base / "outside.json").exists())
        self.assertEqual(len(list((self.workspace / "farms").glob("*.json"))), 2)
        self.assertEqual(len(state["history"]), 1)

    def test_restart_restores_selected_farm_revision_and_snapshots(self):
        imported = self.app.import_save("my-copy.json", farm_save())
        selected_id = imported["farm"]["id"]
        preview = self.app.preview({"type": "coins", "amount": 42}, 1, farm_id=self.app.selected)
        self.app.apply(preview["token"], 1, farm_id=self.app.selected)
        recovered = GodBarn(self.root, self.workspace, FakeEngine()).state()
        self.assertEqual(recovered["farm"]["id"], selected_id)
        self.assertEqual(recovered["farm"]["revision"], 2)
        self.assertEqual(recovered["farm"]["summary"]["coins"], 1042)
        self.assertEqual(len(recovered["history"]), 2)

    def test_select_and_restore_cannot_cross_farms(self):
        state = self.app.state()
        first_id = state["farm"]["id"]
        snapshot = state["history"][0]["id"]
        second_id = self.app.demo()["farm"]["id"]
        self.assertNotEqual(first_id, second_id)
        with self.assertRaises(APIError) as raised:
            self.app.restore(snapshot, 1, farm_id=self.app.selected)
        self.assertEqual(raised.exception.code, "wrong_farm")
        selected = self.app.select(first_id)
        self.assertEqual(selected["farm"]["id"], first_id)

    def test_bad_core_numbers_and_nonfinite_unknown_fields_rejected(self):
        for field, value in (("gold", True), ("cash", "12"), ("xp", -1), ("energy", float("inf"))):
            with self.subTest(field=field):
                source = farm_save()
                source["userInfo"]["player"][field] = value
                with self.assertRaises(APIError):
                    self.app.import_save("bad.json", source)
        source = farm_save()
        source["unknownFeature"]["nan"] = float("nan")
        with self.assertRaises(APIError):
            self.app.import_save("bad.json", source)
        self.assertEqual(len(self.app.farms), 1)

    def test_catalog_pagination_filter_and_local_asset_normalization(self):
        page = self.app.catalog_page({"limit": ["2"], "page": ["2"]})
        self.assertEqual(page["total"], 3)
        self.assertEqual(len(page["items"]), 1)
        self.assertEqual(page["pages"], 2)
        self.assertEqual(self.app.catalog_items("cow")["items"][0]["image"], None)
        self.assertEqual(self.app.catalog_page({"q": ["red tractor"]})["items"][0]["name"], "tractor")
        self.assertEqual(self.app.catalog_page({"type": ["seed"]})["total"], 1)
        self.assertEqual(self.app.catalog_page({"grantable": ["1"]})["total"], 2)
        self.assertEqual(self.app.catalog_items("tractor,strawberry,missing")["items"][0]["image"], "/assets/coin.png")

    def test_exact_favorites_and_expansion_subtype_filters(self):
        favorites = self.app.catalog_page({"names": ["tractor,cow"]})
        self.assertEqual({item["name"] for item in favorites["items"]}, {"tractor", "cow"})
        self.assertEqual(self.app.catalog_page({"names": [""]})["total"], 0)
        expansion = {"name": "expand20", "type": "change_farm", "subtype": "expand_farm", "squares": 20}
        self.app.catalog.append(expansion)
        self.assertEqual(self.app.catalog_page({"type": ["expand_farm"]})["items"], [expansion])
        self.assertEqual(self.app.catalog_page({"subtype": ["expand_farm"]})["items"], [expansion])
        self.app.catalog.append(dict(expansion, name="expand30", squares=30))
        self.assertEqual(self.app.catalog_page({"type": ["expand_farm"], "limit": ["1"]})["expansionSizes"], [20, 30])

    def test_catalog_deduplication_and_original_artwork_order(self):
        catalog = [dict(self.catalog[0], hasOriginalThumbnail=False),
                   dict(self.catalog[1], hasOriginalThumbnail=True),
                   dict(self.catalog[0], displayName="Duplicate must lose", hasOriginalThumbnail=True)]
        atomic_json(self.root / "data" / "catalog.json", catalog)
        app = GodBarn(self.root, self.base / "dedupe-workspace", FakeEngine())
        self.assertEqual(len(app.catalog), 2)
        self.assertEqual(app.catalog[0]["name"], "tractor")
        self.assertEqual(app.items_by_name["strawberry"]["displayName"], "Strawberries")

    def test_discovery_search_facets_artwork_and_sort_are_exposed(self):
        self.app.catalog.append({"name": "pinkhat", "displayName": "Pink Party Hat", "code": "H7",
                                 "type": "consumable", "subtype": "clothes", "grantable": False,
                                 "labelSource": "localization", "hasOriginalThumbnail": True,
                                 "image": "/static/assets/items/hat.png",
                                 "artwork": {"status": "exact", "logical": "assets/clothes/pink_hat.png"}})
        result = self.app.catalog_page({"q": ["H7 pink"], "artwork": ["exact"], "sort": ["name"]})
        self.assertEqual(result["items"][0]["name"], "pinkhat")
        self.assertEqual(result["coverage"]["total"], 4)
        self.assertEqual(result["resultCoverage"]["localizedNames"], 1)
        self.assertEqual(result["subtypes"], [{"subtype": "clothes", "count": 1}])
        self.assertEqual(self.app.catalog_page({"q": ["clothes hat"]})["total"], 1)
        for params in ({"artwork": ["invalid"]}, {"sort": ["invalid"]}):
            with self.assertRaises(APIError):
                self.app.catalog_page(params)

    def test_seasonal_catalog_is_read_only_and_counts_ignore_category_and_query(self):
        self.app.items_by_name["strawberry"]["archive"] = {"availability": {"start": "2011-10-05", "end": "2011-11-10"}}
        self.app.catalog.extend([
            {"name": "winter", "type": "seed", "archive": {"availability": {"start": "2010-12-15", "end": "2011-01-10"}}},
            {"name": "unknown", "type": "seed"},
        ])
        before, farm_before = copy.deepcopy(self.app.catalog), self.app.state()["farm"]
        result = self.app.catalog_page({"calendarDate": ["2026-10-21"], "seasonal": ["in"]})
        self.assertEqual([item["name"] for item in result["items"]], ["strawberry"])
        self.assertEqual(result["items"][0]["seasonal"]["status"], "in")
        self.assertEqual(result["calendar"]["date"], "2026-10-21")
        self.assertTrue(result["calendar"]["override"])
        self.assertEqual(result["seasonalCounts"], {"in": 1, "out": 1, "known": 2, "unknown": 1, "total": 3})
        nonseed = self.app.catalog_page({"calendarDate": ["2026-10-21"], "type": ["animal"], "q": ["Dairy"]})
        self.assertEqual(nonseed["seasonalCounts"], result["seasonalCounts"])
        self.assertNotIn("seasonal", nonseed["items"][0])
        self.assertEqual(self.app.catalog, before)
        self.assertEqual(self.app.state()["farm"], farm_before)
        for params in ({"calendarDate": ["2026-02-30"]}, {"seasonal": ["summer"]}):
            with self.subTest(params=params), self.assertRaises(APIError) as error:
                self.app.catalog_page(params)
            self.assertEqual(error.exception.status, 400)

    def test_symlink_workspaces_are_rejected_without_writes(self):
        target = self.base / "untouched"
        target.mkdir()
        link = self.base / "linked"
        link.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            GodBarn(self.root, link, FakeEngine())
        self.assertEqual(list(target.iterdir()), [])

    def test_game_workspace_and_game_port_are_always_refused(self):
        import server
        protected = server.ROOT.parent / "FarmVillage" / "must-not-create"
        with self.assertRaisesRegex(ValueError, "outside FarmVillage"):
            GodBarn(self.root, protected, FakeEngine())
        self.assertFalse(protected.exists())
        with self.assertRaisesRegex(ValueError, "separate from port 5500"):
            GodBarnServer(("127.0.0.1", 5500), self.app)
        with self.assertRaisesRegex(ValueError, "loopback"):
            GodBarnServer(("0.0.0.0", 8877), self.app)


class HTTPTests(CompanionFixture):
    def setUp(self):
        super().setUp()
        self.server = GodBarnServer(("127.0.0.1", 0), self.app)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        super().tearDown()

    def request(self, path, method="GET", payload=None, headers=None, raw=None):
        request_headers = dict(headers or {})
        if payload is not None:
            payload = dict(payload)
            if path in ("/api/preview", "/api/apply", "/api/restore"):
                payload.setdefault("farmId", self.app.selected)
            raw = json.dumps(payload).encode()
            request_headers.setdefault("Content-Type", "application/json")
            request_headers.setdefault("X-God-Barn-Token", self.app.csrf)
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.request(method, path, body=raw, headers=request_headers)
        response = connection.getresponse()
        body = response.read()
        status, response_headers = response.status, dict(response.getheaders())
        connection.close()
        return status, response_headers, body

    def test_ui_and_local_assets_served_without_private_files(self):
        status, headers, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"God Barn test", body)
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(self.request("/assets/coin.png")[0], 200)
        for path in ("/server.py", "/data/catalog.json", "/workspace/index.json", "/static/../data/rules.json",
                     "/static/%2e%2e/data/rules.json", "/assets/%2e%2e/workspace/index.json"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], 404)

    def test_host_and_origin_checks_reject_other_services(self):
        self.assertEqual(self.request("/api/state", headers={"Host": "example.test"})[0], 403)
        self.assertEqual(self.request("/api/state", headers={"Origin": "https://example.test"})[0], 403)
        self.assertEqual(self.request("/api/state", headers={"Origin": "http://127.0.0.1:5500"})[0], 403)
        self.assertEqual(self.request("/api/state", headers={"Origin": f"http://localhost:{self.port}"})[0], 200)

    def test_post_requires_json_and_current_secret(self):
        self.assertEqual(self.request("/api/demo", "POST", raw=b"{}", headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.request("/api/demo", "POST", raw=b"{}", headers={"Content-Type": "application/json"})[0], 403)
        status, _, body = self.request("/api/demo", "POST", payload={})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["farm"]["revision"], 1)

    def test_http_full_preview_apply_and_download_roundtrip(self):
        status, _, body = self.request("/api/state")
        state = json.loads(body)
        original_id = state["history"][0]["id"]
        status, _, body = self.request("/api/preview", "POST", payload={
            "revision": 1, "operation": {"type": "coins", "amount": 400}})
        self.assertEqual(status, 200)
        preview = json.loads(body)
        status, _, body = self.request("/api/apply", "POST", payload={"revision": 1, "token": preview["token"]})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["farm"]["summary"]["coins"], 1400)
        status, headers, body = self.request("/api/export?id=" + state["farm"]["id"])
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertEqual(json.loads(body)["userInfo"]["player"]["gold"], 1400)
        status, _, body = self.request("/api/snapshot?id=" + original_id)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["userInfo"]["player"]["gold"], 1000)

    def test_stale_revision_and_bad_json_get_clear_errors(self):
        status, _, body = self.request("/api/preview", "POST", payload={"revision": 99, "operation": {"type": "coins"}})
        self.assertEqual(status, 409)
        self.assertEqual(json.loads(body)["code"], "stale_revision")
        status, _, body = self.request("/api/import", "POST", raw=b'{"save":{"bad":NaN}}', headers={
            "Content-Type": "application/json", "X-God-Barn-Token": self.app.csrf})
        self.assertEqual(status, 400)
        self.assertIn("finite", json.loads(body)["error"])
        self.assertEqual(self.request("/api/import", "POST", payload={"path": "/some/source.json"})[0], 400)

    def test_http_catalog_and_items(self):
        status, _, body = self.request("/api/catalog?grantable=1&limit=1&page=2")
        result = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["page"], 2)
        status, _, body = self.request("/api/items?names=tractor%2Ccow")
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(body)["items"]), 2)

    def test_concurrent_apply_only_commits_once(self):
        preview = self.app.preview({"type": "coins", "amount": 10}, 1, farm_id=self.app.selected)
        statuses = []
        def apply_same_preview():
            status, _, _ = self.request("/api/apply", "POST", payload={"revision": 1, "token": preview["token"]})
            statuses.append(status)
        threads = [threading.Thread(target=apply_same_preview) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        self.assertEqual(sorted(statuses), [200, 409])
        self.assertEqual(self.app.state()["farm"]["summary"]["coins"], 1010)
        self.assertEqual(self.app.state()["farm"]["revision"], 2)

    def test_cross_tab_same_revision_cannot_mutate_another_farm(self):
        tab_a = self.app.state()
        farm_a = tab_a["farm"]["id"]
        original_a = tab_a["history"][0]["id"]
        preview_a = self.app.preview({"type": "coins", "amount": 10}, 1, farm_id=farm_a)
        second = farm_save()
        second["userInfo"]["player"]["gold"] = 2000
        farm_b = self.app.import_save("second-copy.json", second)["farm"]["id"]
        self.assertEqual(self.app.state()["farm"]["revision"], 1)
        for path, payload in (
                ("/api/preview", {"operation": {"type": "coins", "amount": 10}}),
                ("/api/apply", {"token": preview_a["token"]}),
                ("/api/restore", {"id": original_a})):
            with self.subTest(path=path):
                status, _, body = self.request(path, "POST", payload={"farmId": farm_a, "revision": 1, **payload})
                self.assertEqual(status, 409)
                self.assertEqual(json.loads(body)["code"], "farm_changed")
        self.assertEqual(self.app.state()["farm"]["id"], farm_b)
        self.assertEqual(self.app.state()["farm"]["summary"]["coins"], 2000)
        status, _, body = self.request("/api/export?id=" + farm_a)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["userInfo"]["player"]["gold"], 1000)
        self.assertEqual(self.request("/api/export")[0], 400)

    def test_mutations_require_explicit_farm_identity(self):
        for path in ("/api/preview", "/api/apply", "/api/restore"):
            with self.subTest(path=path):
                status, _, body = self.request(path, "POST", payload={"farmId": None, "revision": 1})
                self.assertEqual(status, 400)
                self.assertEqual(json.loads(body)["code"], "farm_required")

    def test_branded_missing_page_keeps_api_error_json(self):
        status, headers, body = self.request("/lost-pasture")
        self.assertEqual(status, 404)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn("The cows deny everything", body.decode())
        self.assertIn('href="/"', body.decode())
        self.assertIn('/static/assets/ui/cow.png', body.decode())
        status, headers, body = self.request("/api/unknown-endpoint")
        self.assertEqual(status, 404)
        self.assertIn("application/json", headers["Content-Type"])
        self.assertEqual(json.loads(body)["code"], "not_found")


if __name__ == "__main__":
    unittest.main()
