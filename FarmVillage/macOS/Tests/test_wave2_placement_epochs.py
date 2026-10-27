"""Delayed signed placement packets cannot consume another unit after reload."""
from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import test_rainforest_containers_wire as containers
import placement_receipts

NOW = containers.NOW


class PlacementEpochWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway
    save = containers.RainforestContainerWireTests.save
    persist = containers.RainforestContainerWireTests.persist
    prepare = containers.RainforestContainerWireTests.prepare
    gift = containers.RainforestContainerWireTests.gift
    snapshot = staticmethod(containers.RainforestContainerWireTests.snapshot)

    def rpc(self, name, params, sequence, namespace=None, error=0):
        command = self.command(name, copy.deepcopy(params), sequence)
        if namespace is not None:
            command['sequenceID'] = namespace
        with mock.patch('server.timestamp_now', return_value=NOW), mock.patch(
                'commands.timestamp_now', return_value=NOW), mock.patch('engine.timestamp_now', return_value=NOW):
            response = self.gateway([command])
        return fixtures.gateway_results(self, response, [error])[0]['data']

    def init(self):
        result = self.rpc('UserService.initUser', ['Synthetic placement epoch', 0, True, None], 1)
        self.assertNotIn(placement_receipts.KEY, result)
        self.assertNotIn(placement_receipts.EPOCHS_KEY, result)
        return result['sequenceId']

    def test_exact_old_packet_survives_two_inits_and_disk_reload_without_second_withdrawal(self):
        self.prepare()
        first = self.init()
        item = self.gift('gnome_xrf_headdresstte', 3, [{'unit': 1}, {'unit': 2}, {'unit': 3}])
        packet = ['place', self.snapshot(item['name'], 64022, 20, 20), [{'isGift': True}]]
        original = self.rpc('WorldService.performAction', packet, 801, first)
        second = self.init()
        self.assertNotEqual(first, second)
        third = self.init()
        self.assertNotEqual(second, third)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.assertEqual(self.rpc('WorldService.performAction', packet, 801, first), original)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)
        self.assertEqual(self.save['userInfo']['player']['storageData']['-1'][item['code']][0], 2)
        altered = copy.deepcopy(packet)
        altered[1]['position']['x'] = 26
        self.rpc('WorldService.performAction', altered, 801, first, error=29)
        self.rpc('WorldService.performAction', packet, 802, first, error=29)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)
        # The same numeric counter in the new original namespace is a fresh
        # intentional placement and consumes the next authoritative unit once.
        self.rpc('WorldService.performAction', altered, 801, third)
        self.assertEqual(self.save['userInfo']['player']['storageData']['-1'][item['code']][0], 1)
        import world_travel
        expected = copy.deepcopy(self.save)
        world_travel.clear_temporary_ids(expected)
        self.assertEqual(json.loads(self.path.read_text()), expected)


class PlacementEpochBoundaryTests(unittest.TestCase):
    def test_evicted_namespaced_receipt_refuses_without_running_the_callback(self):
        save = {'userInfo': {'currentWorldType': 'farm'}, '_meadowsStorage': {'sessionID': 'current'}}
        snapshot = {'id': 64001, 'itemName': 'haybale', 'className': 'Decoration'}
        for sequence in range(placement_receipts.NAMESPACE_LIMIT + 1):
            placement_receipts.dispatch(save, snapshot, [], ('current', sequence), lambda: 1000 + sequence)
        self.assertEqual(len(save[placement_receipts.KEY]), placement_receipts.NAMESPACE_LIMIT)
        before = copy.deepcopy(save)
        callback = mock.Mock(side_effect=AssertionError('evicted replay performed mutation'))
        with self.assertRaisesRegex(ValueError, 'older'):
            placement_receipts.dispatch(save, snapshot, [], ('current', 0), callback)
        self.assertEqual(save, before)
        placement_receipts.start_session(save)
        save['_meadowsStorage']['sessionID'] = 'next'
        with self.assertRaisesRegex(ValueError, 'stale'):
            placement_receipts.dispatch(save, snapshot, [], ('current', 0), callback)
        callback.assert_not_called()

    def test_legacy_numeric_no_init_callers_keep_their_original_reset_contract(self):
        save = {'userInfo': {'currentWorldType': 'farm'}, 'opaqueImport': {'keep': [1, 2]}}
        snapshot = {'id': 64001, 'itemName': 'haybale', 'className': 'Decoration'}
        callback = mock.Mock(return_value=7)
        self.assertEqual(placement_receipts.dispatch(save, snapshot, [], 1, callback), 7)
        self.assertEqual(placement_receipts.dispatch(save, snapshot, [], 1, callback), 7)
        callback.assert_called_once()
        placement_receipts.start_session(save)
        self.assertEqual(placement_receipts.dispatch(save, snapshot, [], 1, callback), 7)
        self.assertEqual(callback.call_count, 2)
        self.assertEqual(save['opaqueImport'], {'keep': [1, 2]})


if __name__ == '__main__':
    unittest.main()
