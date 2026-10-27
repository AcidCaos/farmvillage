"""The origin index is built from pristine originals without a cache dependency."""

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("prepare_untabbed", ROOT / "scripts" / "prepare_untabbed.py")
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)


class StubHeritage:
    """Mimics heritage_pricing's public surface: it rehomes worlds and sets a Farm Cash price."""
    ENABLED = True

    def __init__(self, overlaid):
        self.overlaid = set(overlaid)
        self.keys = set()

    def apply(self, records, server=False):
        for record in records:
            if (record.get("name"), record.get("code")) in self.overlaid:
                for node in record.get("requirements", []):
                    node["name"] = "farm"
                record["market"], record["cash"] = "cash", "18"
                self.keys.add((record["name"], record["code"]))

    def is_overlaid(self, item):
        return (item.get("name"), item.get("code")) in self.keys

    def overlay_digest(self):
        return "stub-digest"


def records():
    return [
        {"name": "tabbed", "code": "TB", "marketEntries": {"marketEntry": {"type": "decoration"}}},
        {"name": "lockedcow", "code": "LC", "cost": "1000",
         "requirements": [{"className": "World", "name": "avalon"}]},
        {"name": "priceless", "code": "PL"},
        {"name": "worldfence", "code": "WF", "requirements": [{"className": "World", "name": "whitewinter"}]},
        {"name": "pricedloose", "code": "PR", "cost": "500"},
        {"name": "priceless", "code": "PZ", "cost": "5"},
    ]


class ClassifyTests(unittest.TestCase):
    def test_origins_use_pre_overlay_worlds_and_prices_for_each_untabbed_name(self):
        data = records()
        first = prepare.first_indexes(data)
        heritage = StubHeritage(overlaid={("lockedcow", "LC")})
        origins = prepare.classify(data, first, heritage)
        self.assertNotIn("tabbed", origins)
        self.assertEqual(origins["lockedcow"], {"origin": "heritage", "home": {"currency": "cash", "amount": 18},
                                                "worlds": ["avalon"]})
        self.assertEqual(origins["priceless"], {"origin": "exclusive"})
        self.assertEqual(origins["worldfence"], {"origin": "other", "worlds": ["whitewinter"]})
        self.assertEqual(origins["pricedloose"], {"origin": "other"})

    def test_sold_seed_fallback_is_shared_by_index_generation_and_copied_rows(self):
        data = [{"name": name, "code": code, "type": "seed", "buyable": "true", "cost": price}
                for name, code, price in (("strawberry", "SB", "10"), ("wheat", "WH", "13"))]
        first = prepare.first_indexes(data)
        self.assertEqual(prepare.classify(data, first, StubHeritage(set())), {})
        with tempfile.TemporaryDirectory(prefix="god-barn-sold-crop-", dir="/private/tmp" if Path("/private/tmp").is_dir() else None) as directory:
            catalog = Path(directory) / "catalog.json"
            catalog.write_text(json.dumps([{"name": item["name"], "type": "seed", "archive": {"raw": {
                "buyable": item["buyable"], "cost": item["cost"]}}} for item in data]))
            self.assertEqual(prepare.verify_against_catalog(data, first, catalog), 2)

    def test_first_record_of_a_duplicate_name_decides_its_origin(self):
        data = records()
        first = prepare.first_indexes(data)
        self.assertEqual(first["priceless"], 2)
        origins = prepare.classify(data, first, StubHeritage(overlaid=set()))
        self.assertEqual(origins["priceless"], {"origin": "exclusive"})

    def test_copied_rows_must_agree_with_the_game_records(self):
        data = records()
        first = prepare.first_indexes(data)
        with tempfile.TemporaryDirectory(prefix="god-barn-untabbed-script-", dir="/private/tmp" if Path("/private/tmp").is_dir() else None) as directory:
            catalog = Path(directory) / "catalog.json"
            # Mirror the game's tab data for every row except lockedcow, which gains a tab here.
            copied = [{"name": name, "archive": {"raw": {"marketEntries": {"marketEntry": {"type": "seed"}}}
                                                  if name == "lockedcow" else
                                                  {"marketEntries": data[first[name]].get("marketEntries")}}}
                      for name in first]
            catalog.write_text(json.dumps(copied))
            with self.assertRaises(SystemExit) as caught:
                prepare.verify_against_catalog(data, first, catalog)
            self.assertIn("lockedcow", str(caught.exception))
            catalog.write_text(json.dumps(copied[:-1]))
            with self.assertRaises(SystemExit):
                prepare.verify_against_catalog(data, first, catalog)

    def test_cli_uses_explicit_original_output_and_policy_without_reading_old_cache(self):
        with tempfile.TemporaryDirectory(prefix="god-barn-untabbed-checkout-", dir="/private/tmp" if Path("/private/tmp").is_dir() else None) as directory:
            checkout = Path(directory)
            (checkout / "xml/gz/v855038").mkdir(parents=True)
            (checkout / "xml/gz/v855038/items_opt.amf").write_bytes(b"current source")
            (checkout / "cache").mkdir()
            (checkout / "cache/gz_v855038_items_opt.json").write_text(json.dumps(
                {"identity": {"source_sha256": hashlib.sha256(b"older source").hexdigest()},
                 "data": {"settings": {"items": {"item": []}}}}))
            output=checkout.parent/'fixture-output'
            policy=checkout.parent/'fixture-policy'
            document={'counts':{'untabbed':0,'heritage':0,'exclusive':0,'other':0}}
            with mock.patch.object(prepare,'generate',return_value=document) as generate:
                with mock.patch.object(Path,'read_text',side_effect=AssertionError('legacy cache read')):
                    prepare.main([str(checkout),'--root',str(output),'--policy-root',str(policy)])
            generate.assert_called_once_with(checkout,output,policy_root=policy)


if __name__ == "__main__":
    unittest.main()
