"""Owned first-stall placement/configuration/close through actual AMF and JSON."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import bushels


class MarketStallWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway
    NOW = 2_000_000

    @property
    def save(self):
        return self.player.session('fixture-farmer')

    def prepare(self, *, gifts=1, count=1, objects=()):
        self.path = self.write_fixture()
        self.save['world']['objectsArray'] = copy.deepcopy(list(objects))
        self.save['userInfo']['player'].update(xp=100_015, gold=1_000_000, cash=250,
            mastery={}, seenFlags={'FirstMarketStall': True}, buffs={},
            storageData={'-1': {'ms': [gifts, [], []]}})
        self.save['craftingState'].update(craftingItems=[{'itemCode': 'sb', 'quantity': 1, 'price': None,
                                                        'imported': {'keep': True}}],
                                         maxCapacity=400, currentMarketStallCount=count)
        bushels.initialize(self.save)
        self.player.save_session('fixture-farmer')

    @staticmethod
    def snapshot(ident=63001):
        return {'id': ident, 'itemName': 'marketstall', 'className': 'MarketStallBuilding',
                'state': 'built', 'position': {'x': 10, 'y': 10, 'z': 0},
                'currentBushelItemCode': 'forged', 'isConfigured': True,
                'dateClosed': 9_000_000_000, 'expansionLevel': 99,
                'capacity': 900, 'importedExtra': {'keep': 4}}

    def send(self, requests, errors=(0,), *, now=None):
        with mock.patch('commands.timestamp_now', return_value=now or self.NOW), \
                mock.patch.object(self.server, 'timestamp_now', return_value=now or self.NOW):
            return fixtures.gateway_results(self, self.gateway(requests), list(errors))

    def place(self, ident=63001, sequence=1):
        return self.command('WorldService.performAction', ['place', self.snapshot(ident), [{'isGift': True}]], sequence)

    def configure(self, ident=-1, code='sb', sequence=2):
        return self.command('CraftingService.onReconfigureStall', [ident, code], sequence)

    def close(self, ident, sequence=3):
        return self.command('CraftingService.onCloseStall', [ident], sequence)

    def owned(self):
        return [obj for obj in self.save['world']['objectsArray'] if obj.get('className') == 'MarketStallBuilding']

    def test_first_gift_place_auto_minus_one_configure_and_reload_keep_original_fields(self):
        self.prepare()
        cash = self.save['userInfo']['player']['cash']
        result = self.send([self.place(), self.configure()], (0, 0))
        self.assertEqual(result[1]['data'], {})
        obj = self.owned()[0]
        self.assertEqual(obj['id'], result[0]['data']['id'])
        self.assertEqual((obj['currentBushelItemCode'], obj['isConfigured'], obj['dateClosed']),
                         ('sb', True, self.NOW + 86400))
        self.assertEqual((obj['capacity'], obj['expansionLevel'], obj['contents']), (0, 0, []))
        self.assertEqual(obj['importedExtra'], {'keep': 4})
        self.assertEqual(self.save['craftingState']['currentMarketStallCount'], 2)
        self.assertNotIn('ms', self.save['userInfo']['player']['storageData']['-1'])
        self.assertEqual(self.save['craftingState']['craftingItems'], [
            {'itemCode': 'sb', 'quantity': 1, 'price': None, 'imported': {'keep': True}}])
        self.assertEqual(self.save['userInfo']['player']['cash'], cash)
        self.assertEqual(self.save[bushels.STALL_PLACEMENTS_KEY], [])
        self.assertEqual(self.player._save_contents(self.save), json.loads(self.path.read_text()))
        self.player.load_saves()
        init = self.send([self.command('UserService.initUser', ['QA', 0, True, {}], 10)])[0]['data']
        saved = next(obj for obj in init['world']['objectsArray'] if obj['id'] == result[0]['data']['id'])
        self.assertEqual((saved['currentBushelItemCode'], saved['dateClosed']), ('sb', self.NOW + 86400))
        self.assertEqual(init['craftingState']['currentMarketStallCount'], 2)
        self.assertNotIn(bushels.STALL_REQUESTS_KEY, init)
        self.assertNotIn(bushels.STALL_PLACEMENTS_KEY, init)

    def test_new_placement_ignores_configuration_and_count_advances_once_on_retry(self):
        self.prepare()
        first = self.send([self.place()])[0]
        obj = self.owned()[0]
        self.assertEqual((obj['currentBushelItemCode'], obj['dateClosed'], obj['isConfigured']), (None, 0, False))
        before = self.path.read_bytes()
        repeated = self.send([self.place(sequence=1)])[0]
        self.assertEqual(repeated['data']['id'], first['data']['id'])
        self.assertEqual(self.save['craftingState']['currentMarketStallCount'], 2)
        self.assertEqual(self.path.read_bytes(), before)
        # A new transport request for the same owned placement may record a
        # new receipt, while preserving all gameplay and gift accounting.
        accepted = copy.deepcopy(self.save)
        reissued = self.send([self.place(sequence=2)])[0]
        self.assertEqual(reissued['data']['id'], first['data']['id'])
        for field in ('world', 'userInfo', 'craftingState'):
            self.assertEqual(self.save[field], accepted[field])

    def test_configuration_and_close_replays_do_not_extend_expiry_or_debit_inventory(self):
        self.prepare()
        ident = self.send([self.place()])[0]['data']['id']
        self.send([self.configure(ident, sequence=20)])
        before = self.path.read_bytes()
        self.send([self.configure(ident, sequence=20)], now=self.NOW + 300)
        self.assertEqual(self.path.read_bytes(), before)
        self.send([self.close(ident, sequence=21)])
        self.assertEqual((self.owned()[0]['currentBushelItemCode'], self.owned()[0]['dateClosed'],
                          self.owned()[0]['isConfigured']), (None, 0, False))
        self.assertEqual(self.save['craftingState']['craftingItems'][0]['quantity'], 1)
        before = self.path.read_bytes()
        self.send([self.close(ident, sequence=21)], now=self.NOW + 600)
        self.assertEqual(self.path.read_bytes(), before)
        self.send([self.configure(ident, sequence=21)], (29,))
        self.assertEqual(self.path.read_bytes(), before)

    def test_minus_one_refuses_ambiguous_or_imported_unconfigured_stalls(self):
        self.prepare(gifts=2)
        self.send([self.place(), self.place(63002, 2)], (0, 0))
        before = self.path.read_bytes()
        self.send([self.configure(sequence=3)], (29,))
        self.assertEqual(self.path.read_bytes(), before)
        one = self.owned()[0]['id']
        self.send([self.configure(one, sequence=4)])
        self.send([self.configure(sequence=5)])
        self.assertTrue(all(obj['isConfigured'] for obj in self.owned()))
        self.prepare(objects=[dict(self.snapshot(71), currentBushelItemCode=None, isConfigured=False, dateClosed=0)])
        before = self.path.read_bytes()
        self.send([self.configure()], (29,))
        self.assertEqual(self.path.read_bytes(), before)

    def test_configuration_requires_owned_real_stall_and_positive_original_crop_bushel(self):
        self.prepare()
        ident = self.send([self.place()])[0]['data']['id']
        cases = [(999, 'sb'), (ident, 'ms'), (ident, 'SB'), (ident, 'unknown'), (ident, []), (0, 'sb')]
        for sequence, (target, code) in enumerate(cases, 20):
            with self.subTest(target=target, code=code):
                before = self.path.read_bytes()
                self.send([self.configure(target, code, sequence)], (29,))
                self.assertEqual(self.path.read_bytes(), before)
        self.save['craftingState']['craftingItems'][0]['quantity'] = 0
        self.player.save_session('fixture-farmer')
        before = self.path.read_bytes()
        self.send([self.configure(ident, sequence=40)], (29,))
        self.assertEqual(self.path.read_bytes(), before)

    def test_move_and_unsupported_snapshots_cannot_rewrite_config_or_timer(self):
        self.prepare()
        self.send([self.place(), self.configure()], (0, 0))
        obj = copy.deepcopy(self.owned()[0])
        forged = {**obj, 'currentBushelItemCode': None, 'isConfigured': False, 'dateClosed': 0, 'state': 'grown'}
        forged['position'] = {'x': 14, 'y': 10, 'z': 0}
        self.send([self.command('WorldService.performAction', ['move', forged, []], 5)])
        actual = self.owned()[0]
        self.assertEqual((actual['currentBushelItemCode'], actual['dateClosed'], actual['state']),
                         (obj['currentBushelItemCode'], obj['dateClosed'], obj['state']))
        self.assertEqual(actual['position'], forged['position'])
        for sequence, action in enumerate(('clearWithered', 'plow', 'harvest'), 6):
            before = self.path.read_bytes()
            self.send([self.command('WorldService.performAction', [action, forged, []], sequence)], (29,))
            self.assertEqual(self.path.read_bytes(), before)

    def test_accepted_configuration_survives_bad_sibling_and_normal_action(self):
        self.prepare()
        self.send([self.place()])
        results = self.send([self.configure(sequence=2), self.close(999, 3),
            self.command('UserService.incrementActionCount', ['stall-sibling'], 4)], (0, 29, 0))
        self.assertEqual(results[0]['data'], {})
        self.assertEqual(self.owned()[0]['currentBushelItemCode'], 'sb')
        self.assertEqual(self.save['userInfo']['player']['actionCounts']['stall-sibling'], 1)
        self.assertEqual(self.player._save_contents(self.save), json.loads(self.path.read_text()))

    def test_clear_and_sell_each_decrement_count_only_for_actual_removal(self):
        for action in ('clear', 'sell'):
            with self.subTest(action=action):
                self.prepare(count=8)
                self.send([self.place()])
                obj = copy.deepcopy(self.owned()[0])
                call = self.command('WorldService.performAction', [action, obj, []], 2)
                self.send([call])
                self.assertEqual(self.save['craftingState']['currentMarketStallCount'], 8)
                self.assertEqual(self.save[bushels.STALL_PLACEMENTS_KEY], [])
                self.send([call])
                self.assertEqual(self.save['craftingState']['currentMarketStallCount'], 8)

    def test_store_removal_decrements_once_and_keeps_gift_separate(self):
        barn = {'id': 50, 'itemName': 'barn', 'className': 'StorageBuilding', 'state': 'built',
                'isFullyBuilt': True, 'position': {'x': 0, 'y': 0, 'z': 0}, 'contents': [], 'expansionLevel': 1}
        self.prepare(objects=[barn])
        self.send([self.place()])
        obj = copy.deepcopy(self.owned()[0])
        call = self.command('WorldService.performAction', ['store', obj, [
            {'target': -2, 'resource': obj['id'], 'numToStore': 1}]], 2)
        self.send([call])
        self.assertEqual(self.save['craftingState']['currentMarketStallCount'], 1)
        self.assertEqual(self.save['userInfo']['player']['storageData']['-2']['ms'][0], 1)
        self.assertEqual(self.save[bushels.STALL_PLACEMENTS_KEY], [])
        before = self.path.read_bytes()
        self.send([call])
        self.assertEqual(self.path.read_bytes(), before)
        # A different request cannot remove or deposit the absent stall again.
        stale = self.command('WorldService.performAction', ['store', obj, [
            {'target': -2, 'resource': obj['id'], 'numToStore': 1}]], 3)
        self.send([stale], (29,))
        self.assertEqual(self.path.read_bytes(), before)

    def test_old_evicted_configuration_sequence_cannot_refresh_again(self):
        self.prepare()
        ident = self.send([self.place()])[0]['data']['id']
        self.send([self.configure(ident, sequence=10)])
        self.send([self.close(ident, sequence=sequence) for sequence in range(11, 267)], (0,) * 256)
        self.assertNotIn('10', self.save[bushels.STALL_REQUESTS_KEY]['receipts'])
        before = self.path.read_bytes()
        self.send([self.configure(ident, sequence=10)], (29,), now=self.NOW + 600)
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
