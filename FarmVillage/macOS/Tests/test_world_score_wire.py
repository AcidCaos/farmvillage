"""The original score level-up notification cannot mint points or rewards."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
from pyamf import remoting


class WorldScoreWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    def test_repeated_valid_notification_acknowledges_without_awarding(self):
        path = self.write_fixture()
        saved = self.player.session('fixture-farmer')
        before = copy.deepcopy(saved)
        disk = path.read_bytes()
        for sequence in (1, 2):
            response = self.gateway([self.command('UserService.updateWorldScoreLevelUp', ['spook'], sequence)])
            self.assertEqual(response.status_code, 200)
            body = remoting.decode(response.data).bodies[0][1].body
            self.assertEqual(body['errorType'], 0, body)
            self.assertEqual(body['data'][0]['errorType'], 0, body)
            self.assertIsNone(body['data'][0]['data'])
            self.assertEqual(self.player.session('fixture-farmer'), before)
            self.assertEqual(json.loads(path.read_text()), json.loads(disk))

    def test_unknown_unit_or_forged_amount_is_rejected_without_mutation(self):
        path = self.write_fixture()
        disk = path.read_bytes()
        before = copy.deepcopy(self.player.session('fixture-farmer'))
        for sequence, params in enumerate((['not-a-world-score'], ['spook', 1000000], [], [None]), 1):
            with self.subTest(params=params):
                response = self.gateway([self.command('UserService.updateWorldScoreLevelUp', params, sequence)])
                body = remoting.decode(response.data).bodies[0][1].body
                self.assertEqual(body['data'][0]['errorType'], 29, body)
                self.assertEqual(self.player.session('fixture-farmer'), before)
                self.assertEqual(path.read_bytes(), disk)


if __name__ == '__main__':
    unittest.main()
