"""Herb Garden paid readiness, harvest, seed use and saves over signed AMF."""
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
import building_harvest
import constants
import items

NOW = 2_000_000
DAY = 82_800


class BuildingHarvestWireTests(unittest.TestCase):
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

    @property
    def garden(self):
        return next(obj for obj in self.save['world']['objectsArray'] if obj.get('itemName') == 'herbgarden')

    def persist(self):
        with redirect_stdout(io.StringIO()):
            self.player.save_session('fixture-farmer')

    def prepare(self, *, ripe=False, level=1):
        self.path = self.write_fixture()
        self.save['userInfo']['currentWorldType'] = 'farm'
        self.save['userInfo']['player'].update(xp=100015, gold=0, cash=50, storageData={}, mastery={})
        self.save['world']['objectsArray'] = [
            {'id': 600, 'itemName': 'herbgarden', 'className': 'FeatureBuilding', 'state': 'bare',
             'isFullyBuilt': True, 'expansionLevel': level, 'expansionParts': {}, 'capacity': 0, 'contents': [],
             'plantTime': (NOW - DAY if ripe else NOW - 10) * 1000,
             'position': {'x': 10, 'y': 10, 'z': 0}, 'imported': {'keep': [1, 2]}},
            {'id': 601, 'className': 'Plot', 'itemName': None, 'state': 'plowed', 'plantTime': None,
             'position': {'x': 20, 'y': 20, 'z': 0}}]
        self.sequence = 0
        self.persist()

    def send(self, action, snapshot=None, *, options=None, sequence=None, now=NOW, reject=False):
        self.sequence += 1
        request = self.command('WorldService.performAction', [action,
            copy.deepcopy(self.garden) if snapshot is None else snapshot,
            [] if options is None else [options]], self.sequence if sequence is None else sequence)
        with mock.patch.object(self.server.commands, 'timestamp_now', return_value=now):
            response = self.gateway([request])
        return fixtures.gateway_results(self, response, [29 if reject else 0])[0]

    def reject(self, action, snapshot=None, **kwargs):
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.send(action, snapshot, reject=True, **kwargs)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)

    def test_paid_ready_then_harvest_grants_twenty_usable_seeds_once_and_reloads(self):
        self.prepare()
        raw = copy.deepcopy(self.garden)
        result = self.send('HarvestReadyNow', raw, sequence=10)
        self.assertEqual(result['data'], {'id': 600})
        self.assertEqual(self.save['userInfo']['player']['cash'], 45)
        self.assertEqual(self.save['userInfo']['player']['storageData'], {})
        self.assertEqual((self.garden['state'], self.garden['plantTime']), ('grown', (NOW - DAY) * 1000))
        self.reject('HarvestReadyNow', sequence=11)
        self.send('harvest', {**copy.deepcopy(self.garden), 'state': 'bare', 'plantTime': NOW * 1000}, sequence=12)
        package = items.get_item_by_name('thaibasil_seedpackage')['code']
        self.assertEqual(self.save['userInfo']['player']['storageData']['-1'][package], [20, [], []])
        self.assertEqual(self.garden['plantTime'], NOW * 1000)
        accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.send('HarvestReadyNow', raw, sequence=10, now=NOW + 1)
        self.send('harvest', {**copy.deepcopy(self.garden), 'state': 'bare', 'plantTime': NOW * 1000}, sequence=12, now=NOW + 1)
        self.assertEqual(self.save, accepted)
        self.assertEqual(self.path.read_bytes(), disk)
        self.reject('harvest', sequence=13, now=NOW + 1)
        plot = copy.deepcopy(self.save['world']['objectsArray'][1])
        plot.update(itemName='thaibasil', state='planted', plantTime=0)
        self.send('place', plot, options={'isGift': False, 'currency': '', 'energySource': 0,
                                         'energyCost': 0, 'energyMetadata': {}, 'isStorageWithdrawal': 0,
                                         'aoeSources': []}, sequence=14, now=NOW + 2)
        self.assertEqual(self.save['userInfo']['player']['storageData']['-1'][package][0], 19)
        self.assertEqual(self.save['userInfo']['player']['gold'], 0)
        self.assertEqual(self.save['userInfo']['player']['cash'], 45)
        self.assertEqual(self.save['world']['objectsArray'][1]['plantTime'], (NOW + 2) * 1000)
        self.assertEqual(self.save['userInfo']['player']['xp'], 100016)
        self.assertEqual(json.loads(self.path.read_text())['userInfo']['player']['storageData']['-1'][package][0], 19)

    def test_mastery_selects_next_seed_and_completed_mastery_pays_1500_coins(self):
        self.prepare(ripe=True, level=2)
        self.save['userInfo']['player']['mastery'] = {items.get_item_by_name('thaibasil')['code']: 2}
        self.persist()
        self.send('harvest')
        package = items.get_item_by_name('thyme_seedpackage')['code']
        self.assertEqual(self.save['userInfo']['player']['storageData']['-1'][package][0], 100)
        self.garden['plantTime'] = (NOW - DAY) * 1000
        self.save['userInfo']['player']['mastery'] = {items.get_item_by_name(name)['code']: 2 for name in building_harvest.HERBS}
        self.persist()
        inventory = copy.deepcopy(self.save['userInfo']['player']['storageData'])
        self.send('harvest')
        self.assertEqual(self.save['userInfo']['player']['gold'], 1500)
        self.assertEqual(self.save['userInfo']['player']['storageData'], inventory)

    def test_failed_ready_unrelated_seed_and_stale_move_do_not_change_inventory_or_timer(self):
        self.prepare()
        self.save['userInfo']['player']['cash'] = 4
        self.persist()
        self.reject('HarvestReadyNow')
        self.reject('HarvestReadyNow', options={'price': 0})
        old_timer = self.garden['plantTime']
        forged = {**copy.deepcopy(self.garden), 'state': 'grown', 'plantTime': 0}
        self.reject('clearWithered', forged)
        self.reject('harvest', forged)
        self.assertEqual(self.garden['plantTime'], old_timer)
        self.send('move', {**copy.deepcopy(self.garden), 'expansionLevel': 6, 'plantTime': 0,
                          'position': {'x': 11, 'y': 11, 'z': 0}})
        self.assertEqual(self.garden['plantTime'], old_timer)
        self.assertEqual(self.garden['expansionLevel'], 1)
        plot = copy.deepcopy(self.save['world']['objectsArray'][1])
        plot.update(itemName='strawberry', state='planted')
        self.reject('place', plot, options={'currency': 'coins'})
        self.assertEqual(self.save['userInfo']['player']['storageData'], {})

    def test_new_gift_garden_placement_starts_original_level_and_server_clock(self):
        self.prepare()
        self.save['world']['objectsArray'] = [self.save['world']['objectsArray'][1]]
        self.save['userInfo']['player']['storageData'] = {'-1': {'91v': [1, [], []]}}
        self.persist()
        raw = {'id': constants.TEMP_ID_START, 'tempId': -1, 'itemName': 'herbgarden',
               'className': 'FeatureBuilding', 'state': 'grown', 'isFullyBuilt': True,
               'expansionLevel': 6, 'plantTime': 0, 'contents': [], 'capacity': 999,
               'position': {'x': 10, 'y': 10, 'z': 0}}
        result = self.send('place', raw, options={'isGift': True})
        self.assertNotEqual(result['data']['id'], constants.TEMP_ID_START)
        self.assertEqual((self.garden['state'], self.garden['expansionLevel'], self.garden['plantTime']), ('bare', 1, NOW * 1000))
        self.assertNotIn('91v', self.save['userInfo']['player']['storageData']['-1'])
        self.reject('harvest')

    def test_init_hides_internal_harvest_history_and_original_lootable_family_does_not_charge(self):
        self.prepare(ripe=True)
        self.send('harvest')
        self.assertIn('_buildingHarvestRequests', self.save)
        initialized = self.gateway([self.command('UserService.initUser', ['QA', 0, True, None], 20)])
        data = fixtures.gateway_results(self, initialized, [0])[0]['data']
        self.assertNotIn('_buildingHarvestRequests', data)
        self.garden.update(itemName='bldg_xhh_bigbuildable', className='LootableFixedFeatureBuilding')
        self.persist()
        raw = copy.deepcopy(self.save['world']['objectsArray'][0])
        self.reject('HarvestReadyNow', raw)
        self.reject('harvest', raw)


if __name__ == '__main__':
    unittest.main()
