"""Focused tests for the dormant world-currency to Farm Cash conversion.

Rates are derived from the archived exchange packs in the real item catalog.
Nothing here activates a world, changes travel, or writes a save.
"""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence  # Establish disposable writable paths before bundle imports.
import items
import world_currency_conversion as wcc
import world_travel


def _catalog():
    if getattr(items, "_cached_items", None) is None:
        items.load_items()
    return items.get_items()


def _pack(currency, cash, units, name):
    return {"name": name, "type": "currency_exchange", "subtype": currency,
            "cash": str(cash), "count": str(units), "market": "cash"}


class RecoveredRateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = _catalog()
        cls.rates = wcc.recovered_rates(cls.catalog)

    def test_base_packs_match_the_archived_exchange_items(self):
        self.assertEqual(self.rates["jade"]["cash"], 5)
        self.assertEqual(self.rates["jade"]["units"], 5000)
        self.assertEqual(self.rates["coconuts"]["cash"], 5)
        self.assertEqual(self.rates["coconuts"]["units"], 5000)
        self.assertEqual(self.rates["villageCoins"]["cash"], 10)
        self.assertEqual(self.rates["villageCoins"]["units"], 1000)
        self.assertTrue(self.rates["jade"]["pack"].startswith("jade_exchange_variant"))

    def test_coins_have_no_recovered_rate_and_stay_in_coins(self):
        self.assertNotIn("coins", self.rates)
        coins_item = {"name": "coin_only", "market": "coins", "cost": "100"}
        self.assertIsNone(wcc.price_for_item(coins_item, self.rates))

    def test_exact_ceiling_without_float_drift(self):
        jade = self.rates["jade"]
        self.assertEqual([wcc.farm_cash_for(v, jade) for v in (0, 1, 1000, 1001, 5000, 15)],
                         [0, 1, 1, 2, 5, 1])
        village = self.rates["villageCoins"]
        self.assertEqual([wcc.farm_cash_for(v, village) for v in (1000, 1001)], [10, 11])

    def test_plow_prices_convert_at_the_recovered_base_rate(self):
        self.assertEqual(wcc.plow_charge("asia", self.rates), 1)
        self.assertEqual(wcc.plow_charge("hawaii", self.rates), 1)
        with self.assertRaises(ValueError):
            wcc.plow_charge("farm", self.rates)


class RateFailureTests(unittest.TestCase):
    def test_ambiguous_base_rate_fails_closed(self):
        catalog = [_pack("jade", 5, 5000, "a"), _pack("jade", 5, 4000, "b")]
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            wcc.recovered_rates(catalog)

    def test_invalid_or_unnamed_packs_fail_closed(self):
        with self.assertRaises(ValueError):
            wcc.recovered_rates([_pack("jade", 0, 5000, "zero")])
        with self.assertRaises(ValueError):
            wcc.recovered_rates([_pack(None, 5, 5000, "nocurrency")])


class PriceRuleTests(unittest.TestCase):
    rates = {"jade": {"cash": 5, "units": 5000, "pack": "jade_exchange_variant_p1"}}

    def test_cash_and_coin_items_keep_their_original_price(self):
        self.assertIsNone(wcc.price_for_item({"market": "cash", "cash": "10"}, self.rates))
        self.assertIsNone(wcc.price_for_item({"market": "coins", "cost": "50"}, self.rates))
        self.assertIsNone(wcc.price_for_item({"market": None}, self.rates))

    def test_world_currency_item_with_a_farm_cash_price_keeps_it(self):
        result = wcc.price_for_item({"market": "jade", "cost": "400", "cash": "30"}, self.rates)
        self.assertEqual(result, {"currency": "cash", "amount": 30, "converted": False})

    def test_world_currency_only_item_is_converted_with_source_record(self):
        result = wcc.price_for_item({"market": "jade", "cost": "15"}, self.rates)
        self.assertEqual(result["amount"], 1)
        self.assertTrue(result["converted"])
        self.assertEqual(result["source"], {"currency": "jade", "amount": 15, "packCash": 5,
                                             "packUnits": 5000, "pack": "jade_exchange_variant_p1"})

    def test_unknown_currency_and_unrecovered_price_raise(self):
        with self.assertRaises(ValueError):
            wcc.price_for_item({"market": "berry", "cost": "5"}, self.rates)
        with self.assertRaises(ValueError):
            wcc.price_for_item({"market": "jade"}, self.rates)

    def test_audit_lists_unpriced_items_without_charging_them(self):
        catalog = [{"name": "x", "market": "jade", "cost": None, "requirements": {
            "className": "World", "name": "asia"}},
            {"name": "y", "market": "jade", "cost": "5", "requirements": {
            "className": "World", "name": "asia"}}]
        records = wcc.conversion_audit(catalog, "asia", self.rates)
        self.assertEqual([r["name"] for r in records], ["x", "y"])
        self.assertIn("unpriced", records[0])
        self.assertTrue(records[1]["converted"])


class RecoveredAsiaCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = _catalog()
        cls.rates = wcc.recovered_rates(cls.catalog)
        cls.records = wcc.conversion_audit(cls.catalog, "asia", cls.rates)

    def test_every_world_currency_item_is_accounted_for_once(self):
        names = [r["name"] for r in self.records]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(names), 108)  # Asia items whose market is jade.
        converted = [r for r in self.records if r.get("converted")]
        kept = [r for r in self.records if r.get("converted") is False]
        unpriced = [r for r in self.records if "unpriced" in r]
        self.assertEqual((len(converted), len(kept), len(unpriced)), (73, 34, 1))
        self.assertEqual([r["name"] for r in unpriced], ["xascraftingcottageteahouse"])

    def test_converted_amounts_are_exact_ceilings_of_recovered_prices(self):
        for record in self.records:
            if not record.get("converted"):
                continue
            cost = int(record["source"]["amount"])
            self.assertEqual(record["amount"], -(-cost * 5 // 5000))
            self.assertIsInstance(record["amount"], int)

    def test_asia_seeds_cost_one_farm_cash_each(self):
        seeds = [r["amount"] for r in self.records if r.get("converted") and r["type"] == "seed"]
        self.assertEqual(len(seeds), 56)
        self.assertEqual(set(seeds), {1})

    def test_hawaii_and_village_audits_match_recovered_catalog(self):
        hawaii = wcc.conversion_audit(self.catalog, "hawaii", self.rates)
        self.assertEqual((sum(1 for r in hawaii if r.get("converted")),
                          sum(1 for r in hawaii if "unpriced" in r)), (49, 1))
        village = wcc.conversion_audit(self.catalog, "village", self.rates)
        self.assertEqual(len(village), 3)
        self.assertTrue(all(r.get("converted") for r in village))

    def test_served_item_rewrites_only_converted_items(self):
        converted = next(r for r in self.records if r.get("converted"))
        original = next(item for item in self.catalog if item["name"] == converted["name"])
        before = copy.deepcopy(original)
        served = wcc.served_item(original, self.rates)
        self.assertEqual((served["market"], served["cash"]), ("cash", str(converted["amount"])))
        self.assertEqual(original, before)
        kept = next(r for r in self.records if r.get("converted") is False)
        kept_item = next(item for item in self.catalog if item["name"] == kept["name"])
        self.assertIs(wcc.served_item(kept_item, self.rates), kept_item)

    def test_dormant_worlds_stay_out_of_supported_travel(self):
        for world in ("asia", "hawaii", "village"):
            self.assertNotIn(world, world_travel.SUPPORTED_WORLDS)


if __name__ == "__main__":
    unittest.main()
