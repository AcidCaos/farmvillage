"""Captured Cove packets retain accounting across retries, initUser and restart."""
import copy
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import unittest
from unittest import mock
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import test_wave2_specialized_store_epochs as epochs
import test_cove_port_wave2 as port_fixtures
import test_cove_cellar_progression as cellar_fixtures
import cellar_progression
import cove_port

NOW = 1800000000


class CoveEpochCases:
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway
    save = epochs.StoreEpochCases.save
    persist = epochs.StoreEpochCases.persist
    request = epochs.StoreEpochCases.request
    rpc = epochs.StoreEpochCases.rpc
    init = epochs.StoreEpochCases.init
    replay_in_fresh_process = epochs.StoreEpochCases.replay_in_fresh_process

    def test_real_uuid_current_retry_restart_old_epoch_refusal_and_new_counter(self):
        self.prepare_case()
        first = self.init()
        self.assertEqual(str(uuid.UUID(first)), first)
        self.initial_cash = self.save['userInfo']['player']['cash']
        result = self.rpc('WorldService.performAction', self.packet, 801, first)
        self.assert_first()
        accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.assertEqual(self.rpc('WorldService.performAction', self.packet, 801, first), result)
        self.assertEqual(self.save, accepted)
        self.assertEqual(self.path.read_bytes(), disk)
        self.replay_in_fresh_process(first, result)
        with redirect_stdout(io.StringIO()): self.player.load_saves()
        current = self.init()
        self.assertNotEqual(current, first)
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        for namespace in (first, 'unknown-epoch', '', 1, True, [], {}, 'x' * 129):
            with self.subTest(namespace=namespace):
                self.rpc('WorldService.performAction', self.packet, 801, namespace, error=29)
                self.assertEqual(self.save, before)
                self.assertEqual(self.path.read_bytes(), disk)
        result = self.rpc('WorldService.performAction', self.packet, 801, current)
        self.assert_second()
        accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.assertEqual(self.rpc('WorldService.performAction', self.packet, 801, current), result)
        changed = copy.deepcopy(self.packet)
        if self.packet[0] in ('buyRedeemItem', 'redeemItem'): changed[2][0] = 'crystalrock'
        elif self.packet[0] == 'CompleteNow': changed[2][0]['partName'] = 'stonepart'
        else: changed[2][0]['numToStore'] = 2
        self.rpc('WorldService.performAction', changed, 801, current, error=29)
        self.assertEqual(self.save, accepted)
        self.assertEqual(self.path.read_bytes(), disk)

    def test_mixed_batch_keeps_success_and_rolls_back_the_failed_command(self):
        self.prepare_case()
        namespace = self.init()
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        foreign = copy.deepcopy(self.packet)
        foreign[1]['id'] += 100
        batch = [self.request('WorldService.performAction', self.packet, 901, namespace),
                 self.request('WorldService.performAction', foreign, 902, namespace)]
        with mock.patch('commands.timestamp_now', return_value=NOW), mock.patch('server.timestamp_now', return_value=NOW):
            response = self.gateway(batch)
        results = fixtures.gateway_results(self, response)
        self.assertTrue(any(row['errorType'] == 29 for row in results))
        self.initial_cash = before['userInfo']['player']['cash']
        self.assert_first()
        accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
        history = self.save.get(cove_port.REQUESTS_KEY, self.save.get(cellar_progression.REQUESTS, {}))
        self.assertIn('901', history['receipts'])
        self.assertNotIn('902', history['receipts'])
        # The established gateway uses per-command savepoints: accepted work
        # persists, rejected work and its receipt roll back. Replaying either
        # the accepted command or the same mixed batch cannot charge it twice.
        self.assertEqual([row['errorType'] for row in results], [0, 29])
        with mock.patch('commands.timestamp_now', return_value=NOW), mock.patch('server.timestamp_now', return_value=NOW):
            repeated = self.gateway(batch)
        fixtures.gateway_results(self, repeated, [0, 29])
        self.assertEqual(self.save, accepted)
        self.assertEqual(self.path.read_bytes(), disk)


class CovePortCompletionEpochTests(CoveEpochCases, unittest.TestCase):
    port = port_fixtures.CovePortWave2Tests.port

    def prepare_case(self):
        import pyamf
        port_fixtures.CovePortWave2Tests.prepare(self)
        self.path = self.saves / 'custom-export.json'
        self.persist()
        snapshot = {**copy.deepcopy(self.port), 'buildTime': float('nan'),
                    'tempId': float('nan'), 'instanceDataStoreKey': pyamf.Undefined}
        self.packet = ['CompleteNow', snapshot, [{'isGift': False}, {'firstWA': True}]]

    def assert_first(self): self.assert_state(2, 9)
    def assert_second(self): self.assert_state(3, 24)
    def assert_state(self, level, cost):
        self.assertEqual(self.port['expansionLevel'], level)
        self.assertEqual(self.save['userInfo']['player']['cash'], self.initial_cash - cost)
        self.assertEqual(self.port['plantTime'], 1700000000123)
        self.assertEqual(self.port['imported'], {'retain': ['yes']})
        self.assertNotIn(cove_port.AWARDED_KEY, self.save)

    def test_captured_dialog_probe_then_paid_action_uses_current_original_uuid(self):
        self.prepare_case()
        namespace = self.init()
        self.initial_cash = self.save['userInfo']['player']['cash']
        probe = ['GrantRetroactiveUpgrade', copy.deepcopy(self.packet[1]), []]
        self.assertEqual(self.rpc('WorldService.performAction', probe, 800, namespace), {'id': 7001})
        self.assertEqual(self.port['expansionLevel'], 1)
        self.assertEqual(self.port['plantTime'], 1700000000123)
        self.assertNotIn(cove_port.AWARDED_KEY, self.save)
        self.rpc('WorldService.performAction', self.packet, 801, namespace)
        self.assert_first()
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.rpc('WorldService.performAction', ['GrantRetroactiveUpgrade', probe[1], [{'isGift': False}]],
                 802, namespace, error=29)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)

    def test_final_port_probe_grants_once_across_real_init_and_restart(self):
        self.prepare_case()
        self.port['expansionLevel'] = 11
        self.persist()
        namespace = self.init()
        self.packet = ['GrantRetroactiveUpgrade', copy.deepcopy(self.packet[1]), []]
        # The optimistic packet still says level one; only saved level eleven earns it.
        expected = {'id': 7001, 'upgradeAward': [{'itemName': 'consume_fishermanXfer', 'number': 1}]}
        self.assertEqual(self.rpc('WorldService.performAction', self.packet, 801, namespace), expected)
        self.assertEqual(self.save['userInfo']['player']['storageData']['-1']['06x'][0], 1)
        self.replay_in_fresh_process(namespace, expected)
        current = self.init()
        self.assertEqual(self.rpc('WorldService.performAction', self.packet, 801, current), {'id': 7001})
        self.assertEqual(self.save['userInfo']['player']['storageData']['-1']['06x'][0], 1)


class CovePortMaterialEpochTests(CoveEpochCases, unittest.TestCase):
    port = port_fixtures.CovePortWave2Tests.port

    def prepare_case(self):
        port_fixtures.CovePortWave2Tests.prepare(self)
        self.path = self.saves / 'custom-export.json'
        self.save['userInfo']['player']['storageData']['-1']['0el'] = [3, ['owner'],
            [{'unit': 1}, {'unit': 2}, {'unit': 3}]]
        self.packet = ['store', copy.deepcopy(self.port), [{'storedItemName': 'stonepart',
            'storedItemCode': '0el', 'numToStore': 1, 'isGift': True, 'target': 7001}]]
        self.persist()

    def assert_first(self): self.assert_state(1)
    def assert_second(self): self.assert_state(2)
    def assert_state(self, count):
        self.assertEqual(self.port['expansionLevel'], 1)
        self.assertEqual(self.port['expansionParts'], {'0el': count})
        self.assertEqual(self.save['userInfo']['player']['cash'], self.initial_cash)
        self.assertEqual(self.save['userInfo']['player']['storageData']['-1']['0el'][0], 3 - count)
        self.assertEqual(self.port['plantTime'], 1700000000123)


class CoveCellarPurchaseEpochTests(CoveEpochCases, unittest.TestCase):
    options = cellar_fixtures.CoveCellarProgressionTests.options
    row = cellar_fixtures.CoveCellarProgressionTests.row

    def prepare_case(self):
        cellar_fixtures.CoveCellarProgressionTests.prepare(self)
        self.packet = ['store', copy.deepcopy(self.cellar), [self.options(currency='',
            storedClassName='FeatureCreditItem', isGift=False), {'firstWA': True}]]

    def assert_first(self): self.assert_state(1)
    def assert_second(self): self.assert_state(2)
    def assert_state(self, count):
        self.assertEqual(self.save['userInfo']['player']['cash'], self.initial_cash - count)
        self.assertEqual((self.row['current'], self.row['received']), (2 * count, 2 * count))
        self.assertEqual(self.save['world']['objectsArray'][0]['state'], 'built')
        self.assertEqual(self.save['world']['objectsArray'][0]['imported'], {'keep': [1, 2]})


class CoveCellarRedeemEpochTests(CoveCellarPurchaseEpochTests):
    def prepare_case(self):
        cellar_fixtures.CoveCellarProgressionTests.prepare(self, current=40, received=40)
        self.packet = ['buyRedeemItem', copy.deepcopy(self.cellar), ['mole', False]]

    def assert_state(self, count):
        import items
        self.assertEqual(self.save['userInfo']['player']['cash'], self.initial_cash)
        self.assertEqual((self.row['current'], self.row['received']), (40 - 20 * count, 40))
        code = items.get_item_by_name('mole')['code']
        self.assertEqual(self.save['userInfo']['player']['storageData']['-1'][code][0], count)
        self.assertEqual(self.save['world']['objectsArray'][0]['state'], 'built')


class OriginalCoveCellarRedeemEpochTests(CoveCellarRedeemEpochTests):
    def prepare_case(self):
        import pyamf
        cellar_fixtures.CoveCellarProgressionTests.prepare(self, current=40, received=40)
        self.packet = ['redeemItem', copy.deepcopy(self.cellar),
            pyamf.MixedArray({0: 'mole', 1: 20, 2: False})]


if __name__ == '__main__': unittest.main()
