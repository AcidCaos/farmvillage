"""Catalog rows that no Market tab lists: membership, origin labels, and gift refusals."""

import copy
import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from catalog_tools import UNTABBED_ORIGINS, UntabbedCatalog, has_market_entry, validate_untabbed_origins  # noqa: E402
from engine import CheatEngine, grant_refusal  # noqa: E402
from server import APIError, GodBarn, GodBarnServer, atomic_json  # noqa: E402


RULES = {"levels": [{"level": 1, "xp": 0}, {"level": 2, "xp": 15}], "inGameDaySeconds": 82800,
         "growMultiplier": 1, "witherMultiplier": 2.2}
TABBED = {"marketEntries": {"marketEntry": {"type": "decoration", "subtype": "ornament"}}}
INDEX = {"schema": 1, "items": {
    "ghostcow": {"origin": "heritage", "worlds": ["avalon"], "home": {"currency": "coins", "amount": 2400}},
    "ghostbarn": {"origin": "exclusive"},
    "ghostsilo": {"origin": "other", "worlds": ["whitewinter"]},
    "plainfence": {"origin": "exclusive"},
}}


def row(name, *, type_="decoration", code=None, raw=None, archive=True, **extra):
    item = {"name": name, "displayName": name.title(), "code": name[:2].upper() + "1" if code is None else code,
            "type": type_, "subtype": "deco", "grantable": True}
    if archive:
        item["archive"] = {"raw": {} if raw is None else raw}
    item.update(extra)
    return item


def fixture_catalog():
    return [
        row("plainfence", raw=TABBED),
        row("ghostcow", type_="animal", raw={}),
        row("ghostbarn", type_="building", raw={"buyable": "true"}),
        row("ghostsilo", type_="building", raw={}),
        row("unindexed", raw={"marketEntries": {"marketEntry": {"type": "hidden"}}}),
        row("supply", type_="consumable", raw={}),
        row("nocode", raw={}, code=""),
        row("bare", raw={}, archive=False),
    ]


class MarketTabMembershipTests(unittest.TestCase):
    def test_typed_entries_in_every_recorded_shape_are_tabs(self):
        self.assertTrue(has_market_entry({"marketEntries": {"marketEntry": {"type": "seed"}}}))
        self.assertTrue(has_market_entry({"marketEntries": {"marketEntry": [{"type": "hidden"}, {"type": "animal"}]}}))
        self.assertTrue(has_market_entry({"marketEntries": [{"marketEntry": [{"type": "building", "subtype": "pens"}]}]}))

    def test_sold_crops_without_explicit_entries_use_the_client_seed_fallback(self):
        for sale in (True, "true", "1"):
            self.assertTrue(has_market_entry({"type": "seed", "buyable": sale}))
            self.assertTrue(has_market_entry({"buyable": sale}, item_type="seed"))
        for raw in ({"buyable": "false"}, {},
                    {"buyable": "true", "marketEntries": {"marketEntry": {"type": "hidden"}}}):
            self.assertFalse(has_market_entry(raw, item_type="seed"), raw)
        self.assertFalse(has_market_entry({"buyable": "true"}, item_type="animal"))

    def test_missing_untyped_hidden_only_and_absent_records_are_untabbed(self):
        for raw in ({}, {"marketEntries": None}, {"marketEntries": {}}, {"marketEntries": {"marketEntry": []}},
                    {"marketEntries": {"marketEntry": {"subtype": "ornament"}}},
                    {"marketEntries": {"marketEntry": {"type": "hidden"}}}):
            self.assertFalse(has_market_entry(raw), raw)
        self.assertFalse(has_market_entry(None))


class UntabbedCatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = UntabbedCatalog(fixture_catalog(), INDEX)
        self.by_name = {item["name"]: item for item in self.catalog.items}

    def test_only_rows_without_a_tab_are_listed_and_absent_records_are_skipped(self):
        self.assertEqual(set(self.by_name), {"ghostcow", "ghostbarn", "ghostsilo", "unindexed", "supply", "nocode"})
        self.assertTrue(self.catalog.generated)

    def test_strawberry_and_wheat_stay_in_archive_but_not_in_not_in_market(self):
        crops = [row(name, type_="seed", raw={"buyable": "true", "cost": price})
                 for name, price in (("strawberry", "10"), ("wheat", "13"))]
        hidden = row("hiddenseed", type_="seed", raw={"buyable": "true",
            "marketEntries": {"marketEntry": {"type": "hidden"}}})
        unavailable = row("unavailableseed", type_="seed", raw={"buyable": "false"})
        source = crops + [hidden, unavailable]
        stale = {"schema": 1, "items": {item["name"]: {"origin": "other"} for item in source}}
        result = UntabbedCatalog(source, stale)
        self.assertEqual([item["name"] for item in result.items], ["hiddenseed", "unavailableseed"])
        self.assertEqual([item["name"] for item in source[:2]], ["strawberry", "wheat"])
        self.assertEqual(result.summary["total"], 2)

    def test_index_cannot_make_a_tabbed_row_untabbed(self):
        self.assertNotIn("plainfence", self.by_name)

    def test_origin_worlds_and_home_price_come_from_the_index(self):
        cow = self.by_name["ghostcow"]["untabbed"]
        self.assertEqual(cow["origin"], "heritage")
        self.assertEqual(cow["label"], "Heritage – no market tab")
        self.assertEqual(cow["worlds"], ["avalon"])
        self.assertEqual(cow["home"], {"currency": "coins", "amount": 2400})
        self.assertIsNone(self.by_name["ghostbarn"]["untabbed"]["home"])
        self.assertEqual(self.by_name["ghostsilo"]["untabbed"]["worlds"], ["whitewinter"])

    def test_unindexed_rows_fall_back_to_other_and_missing_index_labels_everything_other(self):
        self.assertEqual(self.by_name["unindexed"]["untabbed"]["origin"], "other")
        blank = UntabbedCatalog(fixture_catalog(), None)
        self.assertFalse(blank.generated)
        self.assertEqual({item["untabbed"]["origin"] for item in blank.items}, {"other"})

    def test_recorded_sale_flag_is_read_from_the_copied_buyable_field(self):
        self.assertTrue(self.by_name["ghostbarn"]["untabbed"]["recordedForSale"])
        self.assertFalse(self.by_name["ghostcow"]["untabbed"]["recordedForSale"])

    def test_gift_refusals_match_the_rules_the_barn_already_applies(self):
        self.assertIsNone(self.by_name["ghostcow"]["untabbed"]["giftRefusal"])
        self.assertEqual(self.by_name["supply"]["untabbed"]["giftRefusal"],
                         'Category "consumable" is not supported for gifts yet.')
        self.assertEqual(self.by_name["nocode"]["untabbed"]["giftRefusal"],
                         "This record has no usable item code, so God Barn cannot gift it.")

    def test_summary_counts_totals_giftable_and_refusals_by_origin(self):
        summary = self.catalog.summary
        self.assertEqual((summary["total"], summary["giftable"], summary["refused"]), (6, 4, 2))
        self.assertEqual(summary["origins"]["heritage"], {"label": "Heritage – no market tab", "total": 1, "giftable": 1})
        self.assertEqual(summary["origins"]["other"]["total"], 4)
        self.assertEqual(summary["origins"]["other"]["giftable"], 2)
        self.assertEqual(summary["refusals"][0]["count"], 1)
        self.assertEqual(set(summary["origins"]), set(UNTABBED_ORIGINS))

    def test_page_filters_by_origin_and_gift_status_and_rejects_bad_values(self):
        heritage = self.catalog.page({"origin": "heritage"})
        self.assertEqual([item["name"] for item in heritage["items"]], ["ghostcow"])
        self.assertEqual(heritage["untabbed"]["origin"], "heritage")
        self.assertEqual(self.catalog.page({"origin": "other"})["total"], 2)
        self.assertEqual(self.catalog.page({"origin": "other", "gift": "all"})["total"], 4)
        self.assertEqual(self.catalog.page({"gift": "all"})["total"], 6)
        self.assertEqual(self.catalog.page({"q": "ghostsilo"})["total"], 1)
        for params in ({"origin": "shelf"}, {"gift": "some"}, {"sort": "random"}, {"limit": "nope"}):
            with self.assertRaises(ValueError):
                self.catalog.page(params)

    def test_index_validation_rejects_malformed_origins(self):
        self.assertIsNone(validate_untabbed_origins(None))
        valid = copy.deepcopy(INDEX)
        self.assertIs(validate_untabbed_origins(valid), valid)
        for mutate in (lambda d: d.update(schema=2),
                       lambda d: d["items"]["ghostcow"].update(origin="shelf"),
                       lambda d: d["items"]["ghostsilo"].update(worlds="avalon"),
                       lambda d: d["items"]["ghostcow"].update(home={"currency": "gold", "amount": 5}),
                       lambda d: d["items"]["ghostcow"].update(home={"currency": "coins", "amount": 0})):
            broken = copy.deepcopy(INDEX)
            mutate(broken)
            with self.assertRaises(ValueError):
                validate_untabbed_origins(broken)


class GiftRefusalAgreementTests(unittest.TestCase):
    def test_refusal_reasons_agree_with_the_engine_grant_path(self):
        items = [row("cow", type_="animal", code="CW"), row("supply", type_="consumable", code="PL"),
                 row("nocode", type_="decoration", code="")]
        engine = CheatEngine(items, RULES)
        for item in items:
            save = {"userInfo": {"player": {"userId": "copied-user"}}, "world": {}}
            refusal = grant_refusal(item)
            operation = {"item": item["name"], "quantity": 1, "group": "giftbox"}
            if refusal is None:
                engine._grant(save, operation, 0, [])
                self.assertIn("CW", save["userInfo"]["player"]["storageData"]["-1"])
            else:
                with self.assertRaises(ValueError) as caught:
                    engine._grant(save, operation, 0, [])
                self.assertEqual(str(caught.exception), refusal)


class CompanionRouteTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="god-barn-untabbed-", dir="/private/tmp" if Path("/private/tmp").is_dir() else None)
        self.base = Path(self.temporary.name)
        self.root = self.base / "app"
        (self.root / "data").mkdir(parents=True)
        (self.root / "static").mkdir()
        (self.root / "static" / "index.html").write_text("<html>God Barn test</html>")
        atomic_json(self.root / "data" / "catalog.json", fixture_catalog())
        atomic_json(self.root / "data" / "rules.json", RULES)
        atomic_json(self.root / "data" / "untabbed.json", INDEX)
        self.app = GodBarn(self.root, self.base / "workspace", CheatEngine(fixture_catalog(), RULES))
        self.server = GodBarnServer(("127.0.0.1", 0), self.app)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.temporary.cleanup()

    def get(self, path):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        connection.request("GET", path)
        response = connection.getresponse()
        body = response.read()
        connection.close()
        return response.status, json.loads(body)

    def test_server_pages_default_to_giftable_rows_and_report_summary(self):
        page = self.app.untabbed_page({})
        self.assertEqual(page["total"], 4)
        self.assertNotIn("supply", {item["name"] for item in page["items"]})
        self.assertEqual(page["untabbed"]["summary"]["total"], 6)
        self.assertEqual(self.app.untabbed_page({"gift": ["all"], "origin": ["other"]})["total"], 4)

    def test_server_rejects_unknown_filters_with_api_errors(self):
        for params in ({"origin": ["shelf"]}, {"gift": ["maybe"]}):
            with self.assertRaises(APIError):
                self.app.untabbed_page(params)

    def test_http_route_serves_the_untabbed_page_and_keeps_catalog_separate(self):
        status, page = self.get("/api/untabbed?origin=heritage&gift=all")
        self.assertEqual(status, 200)
        self.assertEqual([item["name"] for item in page["items"]], ["ghostcow"])
        status, body = self.get("/api/untabbed?origin=shelf")
        self.assertEqual(status, 400)
        self.assertIn("error", body)
        status, catalog = self.get("/api/catalog?limit=50")
        self.assertEqual(status, 200)
        self.assertNotIn("untabbed", catalog)


class ShippedOriginIndexTests(unittest.TestCase):
    """Checks the generated index against the copied catalog it was built for."""

    @classmethod
    def setUpClass(cls):
        cls.index = validate_untabbed_origins(json.loads((ROOT / "data/untabbed.json").read_text()))
        catalog = json.loads((ROOT / "data/catalog.json").read_text())
        unique = {}
        for item in catalog:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                unique.setdefault(item["name"], item)
        cls.untabbed = UntabbedCatalog(list(unique.values()), cls.index)

    def test_every_untabbed_copied_row_has_an_origin_record(self):
        names = {item["name"] for item in self.untabbed.items}
        self.assertEqual(names, set(self.index["items"]))
        self.assertEqual(len(names), self.index["counts"]["untabbed"])

    def test_origin_counts_add_up_and_heritage_rows_carry_a_home_price(self):
        counts = self.index["counts"]
        self.assertEqual(sum(counts[origin] for origin in UNTABBED_ORIGINS), counts["untabbed"])
        for name, record in self.index["items"].items():
            if record["origin"] == "heritage":
                self.assertIn("home", record, name)


if __name__ == "__main__":
    unittest.main()
