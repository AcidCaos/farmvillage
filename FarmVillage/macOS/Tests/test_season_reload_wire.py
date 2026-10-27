"""Original seasonal load flags are a same-world reload, with no season grant."""
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

NOW = 1_800_000_000


class SeasonReloadWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    @property
    def save(self):
        return self.player.session('fixture-farmer')

    def persist(self):
        with redirect_stdout(io.StringIO()):
            self.player.save_session('fixture-farmer')

    def send(self, params, *, sequence, now=NOW, error=0):
        with mock.patch.object(self.server.commands, 'timestamp_now', return_value=now):
            response = self.gateway([self.command('WorldService.loadOwnWorld', params, sequence)])
        return fixtures.gateway_results(self, response, [error])[0]

    def prepare(self, world):
        from game_settings import level_to_xp
        self.path = self.write_fixture()
        self.save['userInfo']['player'].update(xp=level_to_xp(15), gold=123456, cash=73)
        world_travel.unlock_england(self.save, 'allAccess', now=NOW - 100)
        self.persist()
        # Establish the owned world through its ordinary signed wire call.
        self.send([world, False, False, False], sequence=1, now=NOW - 20)
        self.save['world']['objectsArray'] = [{
            'id': 701, 'className': 'Plot', 'itemName': None, 'state': 'plowed',
            'plantTime': (NOW - 1000) * 1000, 'buildTime': (NOW - 1200) * 1000,
            'position': {'x': 4, 'y': 5, 'z': 0}, 'imported': {'keep': [1, 2]},
        }]
        self.save['world']['importedSeasonState'] = {'keep': [1, {'frozen': False}]}
        self.persist()
        self.send([world, False, False, False], sequence=2, now=NOW - 10)

    def assert_only_load_timestamp_changed(self, before, world, now):
        after = copy.deepcopy(self.save)
        summary = after['userInfo']['worldSummaryData'][world]
        self.assertEqual(summary['lastLoaded'], now)
        summary['lastLoaded'] = before['userInfo']['worldSummaryData'][world]['lastLoaded']
        self.assertEqual(after, before)

    def check_same_world(self, world):
        self.prepare(world)
        before = copy.deepcopy(self.save)
        # TWorldLoad from loadNextSeason sends create/freeze/nextSeason=true.
        result = self.send([world, True, True, True], sequence=3)
        self.assertEqual(result['data']['user']['currentWorldType'], world)
        self.assertEqual(result['data']['world'], before['world'])
        self.assertEqual(result['data']['user']['player'], before['userInfo']['player'])
        self.assert_only_load_timestamp_changed(before, world, NOW)
        persisted = json.loads(self.path.read_text())
        self.assertEqual(persisted['world'], before['world'])
        self.assertEqual(persisted['userInfo']['player'], before['userInfo']['player'])
        self.assertEqual(persisted['userInfo']['unlockedWorldTypes'], before['userInfo']['unlockedWorldTypes'])
        # A subsequent request remains an ordinary reload, without a charge or
        # added season/frozen field. Object clocks and inactive worlds survive.
        after_first = copy.deepcopy(self.save)
        self.send([world, True, True, True], sequence=4, now=NOW + 30)
        self.assert_only_load_timestamp_changed(after_first, world, NOW + 30)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.save['world'], before['world'])
        self.assertEqual(self.save['userInfo']['player'], before['userInfo']['player'])

    def test_home_season_flags_reload_without_freezing_or_unlocking(self):
        self.check_same_world('farm')

    def test_owned_england_season_flags_reload_without_freezing_or_unlocking(self):
        self.check_same_world('england')

    def test_cross_world_season_flags_refuse_without_memory_or_disk_changes(self):
        for current, destination in (('farm', 'england'), ('england', 'farm')):
            with self.subTest(current=current):
                self.prepare(current)
                before, disk = copy.deepcopy(self.save), self.path.read_bytes()
                result = self.send([destination, True, True, True], sequence=3, error=29)
                self.assertIn('Freezing farms and seasonal travel', result['errorData'])
                self.assertEqual(self.save, before)
                self.assertEqual(self.path.read_bytes(), disk)


if __name__ == '__main__':
    unittest.main()
