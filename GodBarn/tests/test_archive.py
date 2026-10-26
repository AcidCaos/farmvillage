"""Price context is evidence, and never an extra charge for a God Barn grant."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
from test_engine import CheatEngine, CATALOG, RULES, NOW, farm

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('prepare_archive', ROOT / 'scripts/prepare_archive.py')
archive = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(archive)


class ArchiveTests(unittest.TestCase):
    def test_selected_cash_offer_does_not_invent_coin_offer(self):
        raw = {'market': 'cash', 'cash': '7', 'cost': '12500'}
        p = archive.price(raw)
        self.assertEqual((p['amount'], p['currency']), (7, 'cash'))
        self.assertNotIn('offers', p)

    def test_special_currency_and_default_currency_match_client_rules(self):
        self.assertEqual(archive.price({'market': 'villageCoins', 'cost': '50'})['currencyLabel'], 'Village Coins')
        p = archive.price({'cost': '250', 'cash': '12'})
        self.assertEqual((p['amount'], p['currency']), (250, 'coins'))
        self.assertNotIn('offers', p)

    def test_missing_ambiguous_and_non_scalar_prices_are_not_free(self):
        for value in (None, '', {}, [], 'NaN', 'Infinity', '-1', True):
            with self.subTest(value=value):
                p = archive.price({'market': 'cash', 'cash': value, 'cost': 200})
                self.assertFalse(p['recorded'])
                self.assertEqual(p['label'], 'Price not recorded')
                self.assertNotIn('amount', p)
        self.assertFalse(archive.price({'market': ['cash'], 'cash': '7'})['recorded'])
        self.assertEqual(archive.price({'market': 'coins', 'cost': '0'})['amount'], 0)

    def test_explicit_both_selector_preserves_separate_offers(self):
        p = archive.price({'market': 'both', 'cash': 3, 'cost': 500})
        self.assertEqual([(x['amount'], x['currency']) for x in p['offers']], [(500, 'coins'), (3, 'cash')])

    def test_invalid_windows_and_archived_flag_do_not_create_rarity_or_season(self):
        raw = {'name': 'cow', 'code': 'CW', 'archived': 'yes', 'limitedStart': '1/1/1970', 'limitedEnd': '12/31/9999'}
        record = archive.context(raw, 5, 'hash')
        self.assertIsNone(record['availability'])
        self.assertEqual(record['collections'], [])
        self.assertNotIn('rarity', record)
        self.assertEqual(record['raw']['limitedStart'], '1/1/1970')

    def test_context_retains_raw_values_absences_record_identity_and_variants(self):
        raw = {'name': 'x', 'code': 'X', 'market': 'cash', 'cash': {'tier': 3},
               'marketEntries': {'marketEntry': [{'type': 'limited'}, {'type': 'decoration'}]}}
        before = copy.deepcopy(raw)
        result = archive.context(raw, 24, 'snapshot-digest')
        self.assertEqual(result['raw']['cash'], {'tier': 3})
        self.assertNotIn('cost', result['raw'])
        self.assertEqual(result['source']['recordIndex'], 24)
        self.assertEqual(result['source']['sha256'], 'snapshot-digest')
        self.assertEqual(raw, before)

    def test_shipped_examples_have_selected_price_and_evidenced_collection(self):
        catalog = json.loads((ROOT / 'data/catalog.json').read_text())
        by_code = {item['code']: item for item in catalog if item.get('code') in ('UF', 'v4', 'Fg', 'Ev')}
        for code, amount, currency, collection in [('UF', 7, 'cash', 'winter-2010'), ('v4', 12, 'cash', 'halloween-2010'),
                                                   ('Fg', 30, 'cash', 'adobe-village'), ('Ev', 50, 'villageCoins', 'adobe-village')]:
            with self.subTest(code=code):
                evidence = by_code[code]['archive']
                self.assertEqual((evidence['price']['amount'], evidence['price']['currency']), (amount, currency))
                self.assertIn(collection, evidence['collections'])
                self.assertEqual(evidence['price']['label'], 'Archive price')
                self.assertTrue(evidence['source']['sha256'])
        self.assertEqual(by_code['UF']['archive']['availability'], {'start': '2010-11-26', 'end': '2010-12-26'})

    def test_grant_does_not_charge_archive_price_or_change_identity(self):
        catalog = copy.deepcopy(CATALOG)
        catalog[2]['archive'] = {'price': {'amount': 500, 'currency': 'cash', 'recorded': True}}
        engine = CheatEngine(catalog, RULES)
        save = farm()
        result = engine.apply(save, {'type': 'grant', 'item': 'cow', 'quantity': 4}, NOW)['save']
        for key in ('gold', 'cash', 'userId'):
            self.assertEqual(result['userInfo']['player'][key], save['userInfo']['player'][key])
