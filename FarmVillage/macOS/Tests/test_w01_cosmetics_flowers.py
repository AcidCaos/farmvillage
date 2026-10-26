"""W01 cosmetic economy and separate ordinary-flower/bloom boundaries over AMF."""
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
import avatar
import items
import october_village
import peaceful
import paid_buildings


class HomeCosmeticsTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    def fixture(self, uid='fixture-farmer'):
        save = fixtures.RuntimeFixtureTests.fixture(self, uid)
        if not getattr(self, 'october_fixture', False):
            return save
        now = 1_800_000_000
        save['version'] = None
        save['world'].update(id=1, uid='october-cosmetic-fixture', sizeX=50, sizeY=50, tileSet='grass_theme')
        save['userInfo'].update(currentWorldType='farm', is_new=True, firstDay=True, firstDayTimestamp=now)
        save['userInfo']['worldSummaryData'] = {'farm': {'storageId': -2, 'firstLoaded': now, 'lastLoaded': now}}
        return october_village.apply_new_preset(save, catalog_lookup=items.get_item_by_name,
                                               growth_seconds=peaceful.grow_seconds)
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    def prepare(self, october=False):
        self.october_fixture = october
        self.path = self.write_fixture()
        self.save = self.player.session('fixture-farmer')
        self.save['userInfo']['player'].update(gold=1_000_000, cash=500, xp=100015)
        self.save['avatarState']['unlocked'] = []
        self.save['avatarState']['imported'] = {'retain': [1, 2]}
        self.save['userInfo']['avatar'] = {'version': 'fv_1', 'gender': 'female', 'items': {}}
        self.sequence = 0
        self.persist()

    def persist(self):
        with redirect_stdout(io.StringIO()):
            self.player.save_session('fixture-farmer')

    def send(self, method, params, reject=False):
        self.sequence += 1
        return fixtures.gateway_results(self, self.gateway([self.command(method, params, self.sequence)]),
                                        [29 if reject else 0])[0]

    def reject_unchanged(self, method, params):
        memory, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.send(method, params, reject=True)
        self.assertEqual(self.player.session('fixture-farmer'), memory)
        self.assertEqual(self.path.read_bytes(), disk)

    def test_exact_coin_and_cash_purchase_wear_retry_and_cold_reload_home_october(self):
        for october in (False, True):
            for market, balance in (('coins', 'gold'), ('cash', 'cash')):
                with self.subTest(october=october, market=market):
                    self.prepare(october)
                    item = next(row for row in avatar._cached_items.values()
                        if row['buyable'] and row['market'] == market and row['cost'] > 0)
                    person = self.save['userInfo']['player']
                    before = person[balance]
                    self.send('AvatarService.buyAvatarItem', [item['itemId']])
                    self.assertEqual(person[balance], before - item['cost'])
                    purchased = copy.deepcopy(self.save)
                    self.send('AvatarService.buyAvatarItem', [item['itemId']])
                    self.assertEqual(self.save, purchased)
                    self.send('AvatarService.saveAvatar', [{item['category']: {
                        'itemId': item['itemId'], 'filename': 'forged', 'metaData': {'forged': True}}}, 'female'])
                    expected = {'version': 'fv_1', 'gender': 'female',
                                'items': {item['category']: {'itemId': item['itemId']}}}
                    self.assertEqual(self.save['userInfo']['avatar'], expected)
                    self.assertEqual(self.save['avatarState']['configurations']['female'][item['category']], item['itemId'])
                    accepted = copy.deepcopy(self.save)
                    with redirect_stdout(io.StringIO()): self.player.load_saves()
                    self.save = self.player.session('fixture-farmer')
                    self.assertEqual(self.save, accepted)
                    self.send('AvatarService.buyAvatarItem', [item['itemId']])
                    self.assertEqual(self.save, accepted)
                    self.assertEqual(self.save['userInfo']['currentWorldType'], 'farm')
                    self.assertEqual(self.save['avatarState']['imported'], {'retain': [1, 2]})

    def test_unowned_unknown_unsaleable_and_insufficient_cosmetics_refuse_atomically(self):
        self.prepare()
        paid = next(row for row in avatar._cached_items.values() if row['buyable'] and row['market'] == 'cash')
        self.reject_unchanged('AvatarService.saveAvatar', [{paid['category']: {'itemId': paid['itemId']}}, 'female'])
        self.reject_unchanged('AvatarService.saveAvatar', [{'costume': {'itemId': 'unknown'}}, 'female'])
        self.reject_unchanged('AvatarService.saveAvatar', [[], 'female'])
        self.reject_unchanged('AvatarService.saveAvatar', [{}, 'invalid'])
        self.reject_unchanged('AvatarService.buyAvatarItem', ['unknown'])
        self.save['userInfo']['player']['cash'] = 0; self.persist()
        self.reject_unchanged('AvatarService.buyAvatarItem', [paid['itemId']])
        unsaleable = next(row for row in avatar._cached_items.values() if not row['buyable'])
        self.reject_unchanged('AvatarService.buyAvatarItem', [unsaleable['itemId']])

    def test_free_and_imported_worn_cosmetics_remain_usable(self):
        self.prepare()
        free = next(row for row in avatar._cached_items.values() if row['market'] == 'free')
        imported = next(row for row in avatar._cached_items.values() if row['market'] == 'cash')
        self.save['userInfo']['avatar']['items'] = {imported['category']: {'itemId': imported['itemId']}}
        self.persist()
        for row in (imported, free, imported):
            self.send('AvatarService.saveAvatar', [{row['category']: {'itemId': row['itemId']}}, 'female'])
            self.assertEqual(self.save['userInfo']['avatar']['items'][row['category']], {'itemId': row['itemId']})
            with redirect_stdout(io.StringIO()): self.player.load_saves()
            self.save = self.player.session('fixture-farmer')

    def test_ordinary_flower_crop_harvest_has_exact_yield_real_clock_and_no_double_pay(self):
        self.prepare(october=True)
        seed = items.get_item_by_name('sunflowers')
        now = 1_800_000_000
        plot = {'id': 700, 'className': 'Plot', 'itemName': seed['name'], 'state': 'grown',
                'plantTime': int((now - peaceful.grow_seconds(seed) - 60) * 1000),
                'position': {'x': 16, 'y': 0, 'z': 0}}
        authored = copy.deepcopy(self.save['world']['objectsArray'])
        marker = copy.deepcopy(self.save[october_village.STATE_KEY])
        self.save['world']['objectsArray'].append(plot); self.persist()
        gold = self.save['userInfo']['player']['gold']
        with mock.patch.object(self.server.commands, 'timestamp_now', return_value=now):
            self.send('WorldService.performAction', ['harvest', copy.deepcopy(plot), []])
            harvested = copy.deepcopy(self.player.session('fixture-farmer'))
            self.send('WorldService.performAction', ['harvest', copy.deepcopy(plot), []])
        self.assertEqual(self.player.session('fixture-farmer'), harvested)
        self.assertEqual(harvested['userInfo']['player']['gold'], gold + int(seed['coinYield']))
        self.assertEqual(next(row for row in harvested['world']['objectsArray'] if row['id'] == 700)['state'], 'fallow')
        self.assertEqual([row for row in harvested['world']['objectsArray'] if row['id'] != 700], authored)
        self.assertEqual(harvested[october_village.STATE_KEY], marker)
        self.assertEqual(json.loads(self.path.read_text())['world'], harvested['world'])

    def test_full_bloom_unrecovered_generator_refuses_without_reward_food_or_clock_loss(self):
        self.prepare()
        bloom = items.get_item_by_name('africandaisies_fullbloom')
        obj = {'id': 700, 'itemName': bloom['name'], 'className': 'FeatureBuilding',
               'isFullyBuilt': True, 'expansionLevel': 2, 'expansionParts': {}, 'contents': [],
               'state': 'grown', 'plantTime': 1, 'position': {'x': 10, 'y': 10, 'z': 0}}
        self.save['world']['objectsArray'] = [obj]; self.persist()
        self.reject_unchanged('WorldService.performAction', ['harvest', copy.deepcopy(obj), []])
        self.reject_unchanged('WorldService.performAction', ['HarvestReadyNow', copy.deepcopy(obj), []])
        all_blooms = [row for row in items.get_items() if paid_buildings._bloom(row)]
        self.assertEqual(len(all_blooms), 258)
        for row in all_blooms:
            self.assertFalse(paid_buildings._features(paid_buildings.client_item_projection(row), 'HarvestFManager'))


if __name__ == '__main__': unittest.main()
