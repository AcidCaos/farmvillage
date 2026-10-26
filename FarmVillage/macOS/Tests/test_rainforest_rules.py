"""Rainforest authored artifact/land contracts and atomic closed growth paths."""
import copy
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import test_cove_cellar as cellar
import construction
import creative_worlds
import game_settings
import items
import rainforest_rules as rules
import themed_land_offers
import world_travel

NOW = 1800000000


class RainforestRulesTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway
    save = cellar.CoveCellarTests.save
    persist = cellar.CoveCellarTests.persist

    def prepare(self):
        self.path = self.write_fixture()
        self.save['world']['objectsArray'] = []
        self.save['userInfo']['player'].update(xp=game_settings.level_to_xp(100),
                                              gold=100000000, cash=1000)
        creative_worlds.create(self.save, 'rainforest', 'allAccess', now=NOW)
        world_travel.switch(self.save, 'rainforest', now=NOW)
        self.persist()

    def test_recovered_exact_materials_and_all_mandatory_objects_are_independent(self):
        result = rules.recovered_growth_contract()
        self.assertEqual({name: (row['code'], row['material'], row['materialCount'])
                          for name, row in result['artifacts'].items()}, {
            'xrf_treasure_s': ('WTB', 'part_minimattock', 10),
            'xrf_treasure_m': ('Zp5', 'part_minimattock', 22),
            'xrf_treasure_l': ('XDh', 'part_handbrush', 28),
            'xrf_treasure_xl': ('VyY', 'part_handbrush', 42)})
        self.assertEqual(sum(map(len, result['expansionAdditions'].values())), 37)
        first = result['expansionAdditions'][58]
        self.assertEqual([(row['itemName'], row['position']) for row in first], [
            ('xrf_treasure_s', {'x': 3, 'y': 44, 'z': 0}),
            ('xrf_treasure_l', {'x': 24, 'y': 2, 'z': 0}),
            ('xrf_treasure_xl', {'x': 1, 'y': 16, 'z': 0})])
        first[0]['position']['x'] = 999
        self.assertEqual(rules.recovered_growth_contract()['expansionAdditions'][58][0]['position']['x'], 3)
        for row in result['artifacts'].values():
            self.assertIsNone(row['completionItem'])
            self.assertIsNone(row['completionGift'])
            self.assertIsNone(row['clockSeconds'])
            self.assertFalse(construction.manages(items.get_item_by_name(row['name'])))

    def test_all_land_prices_keep_raw_and_original_transaction_cash_distinct(self):
        offers = rules.recovered_growth_contract()['landOffers']
        self.assertEqual(len(offers), 38)
        self.assertEqual([offers[f'xrffarm{tier}']['catalogAmount'] for tier in range(14, 51, 2)],
            [10000, 25000, 50000, 75000, 1000000, 1500000, 2000000, 3000000,
             4500000, 5000000, 5500000, 6000000, 12000000, 15000000, 18000000,
             20000000, 22000000, 24000000, 26000000])
        self.assertEqual(offers['xrffarm14_cash']['catalogAmount'], 20)
        self.assertEqual(offers['xrffarm50_cash']['catalogAmount'], 380)
        for name, offer in offers.items():
            if name.endswith('_cash'):
                self.assertEqual(offer['transactionAmount'], 1)
            self.assertTrue(themed_land_offers.blocked_offer(items.get_item_by_name(name)))
            with self.assertRaisesRegex(ValueError, 'genuine'):
                rules.guard_land_growth(name)

    def test_contract_drift_is_rejected_without_reusing_neighboring_treasure(self):
        original = items.get_item_by_name
        def changed(name):
            result = copy.deepcopy(original(name))
            if name == 'xrf_treasure_s':
                result['matsNeeded'] = '9'
            return result
        rules._archive.cache_clear()
        try:
            with mock.patch.object(items, 'get_item_by_name', side_effect=changed), self.assertRaisesRegex(
                    ValueError, 'new source audit'):
                rules.recovered_growth_contract()
        finally:
            rules._archive.cache_clear()

    def test_expansion_signed_gateway_refusals_do_not_charge_on_retries_or_reload(self):
        self.prepare()
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        for name in rules.recovered_growth_contract()['landOffers']:
            currency = 'cash' if name.endswith('_cash') else 'coins'
            response = self.gateway([self.command('FarmService.expandFarm', [name, currency])])
            fixtures.assert_gateway_status(self, response, 400)
            self.assertEqual(self.save, before)
            self.assertEqual(self.path.read_bytes(), disk)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.save, before)
        response = self.gateway([self.command('FarmService.expandFarm', ['xrffarm14_cash', 'cash'])])
        fixtures.assert_gateway_status(self, response, 400)
        self.assertEqual(self.path.read_bytes(), disk)
        world_travel.switch(self.save, 'farm', now=NOW)
        world_travel.switch(self.save, 'rainforest', now=NOW)
        self.assertEqual(self.save['world']['sizeX'], 50)
        self.assertEqual(self.save['world']['objectsArray'], [])


if __name__ == '__main__':
    unittest.main()
