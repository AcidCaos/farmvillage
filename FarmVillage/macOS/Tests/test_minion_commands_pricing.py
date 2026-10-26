"""Catalog prices that decode as lists, empty objects or stray strings must not break a purchase or a sale.

Only the price in the currency being spent is read, so an unrelated malformed field on the same catalog entry
cannot fail the transaction; a list means its first entry.
"""

from contextlib import ExitStack, redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence  # noqa: F401,E402  Loads first so FARMVILLAGE_DATA_DIR is set before product modules resolve paths.

import commands
import engine
import game_settings
import items


class CatalogPriceTests(unittest.TestCase):
    def test_catalog_price_reads_first_entry_of_a_list_and_plain_integers(self):
        self.assertEqual(engine.catalog_price({"cost": ["15000", "15000"]}, "cost"), 15000)
        self.assertEqual(engine.catalog_price({"cost": "35"}, "cost"), 35)
        self.assertEqual(engine.catalog_price({"cost": "10000."}, "cost"), 10000)

    def test_catalog_price_is_none_for_absent_empty_or_stray_values(self):
        for value in (None, {}, [], "n", "200,000"):
            with self.subTest(value=value):
                self.assertIsNone(engine.catalog_price({"cost": value}, "cost"))
        self.assertIsNone(engine.catalog_price({}, "cost"))


class ItemCostTests(unittest.TestCase):
    def setUp(self):
        self.save = {"userInfo": {"player": {"gold": 1000, "cash": 500, "xp": 0}}}
        self.player = self.save["userInfo"]["player"]

    def test_farm_cash_statue_with_empty_coin_price_is_bought_for_its_cash_price(self):
        statue = {"name": "doublecoinstatue", "market": "cash", "cost": {}, "cash": "300"}
        engine.apply_item_cost(self.save, statue, currency="cash")
        self.assertEqual(self.player["cash"], 200)
        self.assertEqual(self.player["gold"], 1000)

    def test_cash_price_given_as_a_list_uses_its_first_entry(self):
        unicorn = {"name": "unicorn_wonderland", "market": "cash", "cost": "100000", "cash": ["57", "57"]}
        engine.apply_item_cost(self.save, unicorn)
        self.assertEqual(self.player["cash"], 443)

    def test_coin_purchase_ignores_a_malformed_cash_field(self):
        board = {"name": "partydirectionsboard", "market": None, "cost": "100000", "cash": {}}
        self.player["gold"] = 200000
        engine.apply_item_cost(self.save, board)
        self.assertEqual(self.player["gold"], 100000)

    def test_sale_of_a_list_priced_item_uses_its_first_entry(self):
        tree = {"name": "bonsaiadeniumtree", "market": "cash", "cost": ["15000", "15000"], "cash": "10"}
        self.assertEqual(engine.item_sell_price(tree), 750)

    def test_sale_of_an_item_with_a_stray_coin_price_is_worth_nothing_rather_than_a_crash(self):
        self.assertEqual(engine.item_sell_price({"name": "placeholder", "cost": "n"}), 0)
        self.assertEqual(engine.item_sell_price({"name": "placeholder", "cost": {}}), 0)


class FarmCashPurchaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The authoritative settings, so the farming and achievement tables are the shipped ones.
        cls.settings = game_settings._decode_game_settings((ROOT / "xml/gz/v855098/gameSettings.xml.gz").read_bytes())
        cls.initial = json.loads((ROOT / "villages/initial.json").read_text())
        cls.catalog = [
            {"name": "doublecoinstatue", "code": "DC", "type": "decoration", "subtype": "decor_misc",
             "market": "cash", "cost": {}, "cash": "300"},
            {"name": "bonsaiadeniumtree", "code": "BA", "type": "tree", "market": "cash",
             "cost": ["15000", "15000"], "cash": "10"},
            {"name": "haybale", "code": "HB", "type": "decoration", "subtype": "haybale", "cost": "100"},
        ]

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for module, key, value in (
            (game_settings, "_cached_game_settings", self.settings),
            (game_settings, "_cached_farming", {}),
            (game_settings, "_xp_level_map", None),
            (game_settings, "_level_xp_map", None),
            (items, "_cached_items", {"settings": {"items": {"item": self.catalog}}}),
        ):
            self.stack.enter_context(mock.patch.object(module, key, value))
        game_settings._xp_level_map_init()
        self.save = copy.deepcopy(self.initial)
        self.save["world"]["objectsArray"] = []
        self.player = self.save["userInfo"]["player"]
        self.player.update(gold=1000, xp=0, cash=500, achievements={}, achCounters={}, mastery={},
                           masteryCounters={}, storageData={})
        self.stack.enter_context(mock.patch.object(commands, "session", return_value=self.save))
        self.stack.enter_context(mock.patch.object(commands.quests, "record_action"))
        self.stack.enter_context(redirect_stdout(io.StringIO()))

    def statue(self, ident=900, currency=None):
        obj = {"id": ident, "className": "Decoration", "itemName": "doublecoinstatue", "state": "static",
               "position": {"x": 0, "y": 0, "z": 0}}
        return commands.world_perform_action("test", "place", obj, [{"currency": currency}] if currency else [])

    def test_buying_a_farm_cash_statue_with_empty_coin_price_charges_cash_and_places_it(self):
        self.statue(currency="cash")
        self.assertEqual(self.player["cash"], 200)
        self.assertEqual(self.player["gold"], 1000)
        self.assertEqual([obj["itemName"] for obj in self.save["world"]["objectsArray"]], ["doublecoinstatue"])

    def test_buying_without_an_explicit_currency_defaults_to_the_cash_market(self):
        self.statue()
        self.assertEqual(self.player["cash"], 200)
        self.assertEqual(self.player["xp"], 0)  # no buy XP without a coin price to derive it from


if __name__ == "__main__":
    unittest.main()
