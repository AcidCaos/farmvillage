"""Paid extra-farm HTTP transactions, using disposable saves only."""
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import world_travel


class AdditionalFarmsHTTPTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture

    def prepare(self, *, cash=120):
        from game_settings import level_to_xp
        import crafting
        self.path = self.write_fixture()
        save = self.player.session('fixture-farmer')
        save['userInfo']['player'].update(cash=cash, xp=level_to_xp(15))
        save['craftingState']['unrecognizedQueue'] = [{'finish_ts': 1792718337}]
        crafting.initialize(save)
        with redirect_stdout(io.StringIO()):
            self.player.save_session('fixture-farmer')
            response = self.client.post('/', data={'UID': 'fixture-farmer', 'RUFFLE': '1',
                                                   'destination': 'farms'})
        self.assertEqual(response.location, '/farms')
        self.assertEqual(self.client.get('/farms').status_code, 200)
        with self.client.session_transaction() as session:
            self.token = session['farms_token']
        return self.player.session('fixture-farmer')

    def post(self, **overrides):
        data = dict(token=self.token, action='purchase', world='meadows', option='cash60')
        data.update(overrides)
        with redirect_stdout(io.StringIO()), mock.patch.object(self.server, 'timestamp_now', return_value=1800000000):
            return self.client.post('/farms', data=data)

    def test_login_and_token_required_without_save_changes(self):
        self.assertEqual(self.client.get('/farms').location, '/')
        self.prepare()
        before = self.path.read_bytes()
        for token in ('', 'wrong-token', '🌻'):
            self.assertEqual(self.post(token=token).status_code, 400)
            self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.client.post('/', data={'UID': 'not-a-save', 'destination': 'farms'}).location, '/')
        self.assertEqual(self.client.get('/farms').location, '/')

    def test_purchase_is_durable_once_and_travel_preserves_home_and_bakery(self):
        before = copy.deepcopy(self.prepare())
        self.assertEqual(self.post().location, '/farms')
        first = json.loads(self.path.read_text())
        self.assertEqual(first['userInfo']['player']['cash'], 60)
        self.assertEqual(first['userInfo']['player']['storageData']['-1']['66e'][0], 1)
        self.assertEqual(self.post().location, '/farms')
        self.assertEqual(json.loads(self.path.read_text()), first)
        self.assertEqual(self.post(action='visit').location, '/ruffle.html')
        meadow = json.loads(self.path.read_text())
        self.assertEqual(meadow['userInfo']['currentWorldType'], 'meadows')
        self.assertEqual(meadow['craftingState'], before['craftingState'])
        self.assertEqual(world_travel.home_world(meadow), before['world'])
        self.assertEqual(self.post(action='visit', world='farm').location, '/ruffle.html')
        home = json.loads(self.path.read_text())
        self.assertEqual(home['world'], before['world'])
        self.assertEqual(home['craftingState'], before['craftingState'])
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        page = self.client.get('/farms').get_data(as_text=True)
        self.assertIn('Sunflower Meadows', page)
        self.assertNotIn('Add farm · 60', page)

    def test_failed_purchase_and_unsupported_visits_do_not_mutate(self):
        self.prepare(cash=59)
        before = self.path.read_bytes()
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertIn('role="alert"', response.get_data(as_text=True))
        self.assertEqual(self.path.read_bytes(), before)
        for fields in ({'action': 'visit'}, {'action': 'visit', 'world': 'hawaii'},
                       {'option': 'cash199'}, {'action': 'unknown'}):
            response = self.post(**fields)
            self.assertEqual(response.status_code, 200)
            self.assertIn('role="alert"', response.get_data(as_text=True))
            self.assertEqual(self.path.read_bytes(), before)

    def test_failed_write_rolls_back_purchase_and_can_retry(self):
        self.prepare()
        before = copy.deepcopy(self.player.session('fixture-farmer'))
        disk = self.path.read_bytes()
        with mock.patch.object(self.server, 'save_session', side_effect=OSError('test disk full')):
            with self.assertRaises(OSError):
                self.post()
        self.assertEqual(self.path.read_bytes(), disk)
        self.assertEqual(self.player.session('fixture-farmer'), before)
        self.assertEqual(self.post().location, '/farms')
        self.assertEqual(self.player.session('fixture-farmer')['userInfo']['player']['cash'], 60)


if __name__ == '__main__':
    unittest.main()
