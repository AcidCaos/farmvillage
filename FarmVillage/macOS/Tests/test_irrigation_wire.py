"""Actual sprinkler AMF0 arrays must reach the authoritative water ledger."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
from pyamf import remoting


class IrrigationWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    def prepare(self):
        path = self.write_fixture()
        save = self.player.session('fixture-farmer')
        now = 2_000_000
        save['userInfo']['featureOptions']['irrigation'] = {
            'irrigation': {'waterPlots': {'farm': {'amount': 20}}}}
        save['world']['objectsArray'] = [{
            'id': ident, 'className': 'Plot', 'itemName': 'strawberry',
            'state': 'planted', 'plantTime': (now - age) * 1000,
            'position': {'x': ident * 4, 'y': 0, 'z': 0},
        } for ident, age in ((11, 0), (12, 13_800))]
        self.player.save_session('fixture-farmer')
        return path, now

    def test_captured_numeric_keyed_array_waters_both_plots_and_survives_reload(self):
        path, now = self.prepare()
        # Captured in the original browser: ['waterPlots', {0:{id:6},1:{id:7}}, {}].
        params = ['waterPlots', {0: {'id': 11}, 1: {'id': 12}}, {}]
        with mock.patch('commands.timestamp_now', return_value=now), \
                mock.patch('commands.peaceful.grow_seconds', return_value=14_400):
            response = self.gateway([self.command('IrrigationService.onIrrigationAction', params, 1)])
        result = remoting.decode(response.data).bodies[0][1].body['data'][0]
        self.assertEqual(result['errorType'], 0, result)
        self.player.load_saves()
        save = self.player.session('fixture-farmer')
        self.assertEqual(save['userInfo']['featureOptions']['irrigation']['irrigation']['waterPlots']['farm']['amount'], 18)
        first, second = save['world']['objectsArray']
        self.assertEqual(first['plantTime'], (now - 7200) * 1000)
        self.assertEqual(second['plantTime'], (now - 14_400) * 1000)
        self.assertEqual(json.loads(path.read_text())['world'], save['world'])

    def test_sparse_or_named_array_is_refused_without_water_or_crop_changes(self):
        path, now = self.prepare()
        before = copy.deepcopy(self.player.session('fixture-farmer'))
        disk = path.read_bytes()
        for sequence, entries in enumerate(({1: {'id': 11}}, {'crop': {'id': 11}},
                                             {0: {'id': 11}, 2: {'id': 12}}), 1):
            result = self.gateway([self.command('IrrigationService.onIrrigationAction',
                ['waterPlots', entries, {}], sequence)])
            decoded = remoting.decode(result.data).bodies[0][1].body['data'][0]
            self.assertEqual(decoded['errorType'], 29)
            self.assertEqual(self.player.session('fixture-farmer'), before)
            self.assertEqual(path.read_bytes(), disk)


if __name__ == '__main__':
    unittest.main()
