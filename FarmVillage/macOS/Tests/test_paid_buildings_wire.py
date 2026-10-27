"""Original paid building requests through signed AMF and temporary farm saves."""
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


class PaidBuildingsWireTests(unittest.TestCase):
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
    def obj(self):
        return self.save['world']['objectsArray'][0]

    def persist(self):
        with redirect_stdout(io.StringIO()):
            self.player.save_session('fixture-farmer')

    def prepare(self, name='africandaisies_bulb', **extra):
        import items
        self.path = self.write_fixture()
        self.save['userInfo']['currentWorldType'] = 'farm'
        self.save['userInfo']['player'].update(xp=100015, gold=500000, cash=200, storageData={})
        item = items.get_item_by_name(name)
        if name.endswith(('_bulb', '_singlebloom')):
            # The original upgrade menu opens only after feeding the current
            # flower stage to its final authored expansion level.
            extra.setdefault('expansionLevel', 2)
        self.save['world']['objectsArray'] = [{
            'id': 600, 'itemName': name, 'className': item['className'],
            'state': 'bare', 'isFullyBuilt': True, 'plantTime': 1000000,
            'position': {'x': 10, 'y': 11, 'z': 0}, 'contents': [],
            'importedBuilding': {'keep': [1, {'value': 2}]},
            **extra,
        }]
        self.sequence = 0
        self.persist()

    def snapshot(self):
        return copy.deepcopy(self.obj)

    def send(self, action, snapshot=None, options=None, *, sequence=None, reject=False):
        self.sequence += 1
        request = self.command('WorldService.performAction',
            [action, self.snapshot() if snapshot is None else snapshot, [options or {}]],
            self.sequence if sequence is None else sequence)
        response = self.gateway([request])
        return fixtures.gateway_results(self, response, [29 if reject else 0])[0]

    def reject_unchanged(self, action, snapshot=None, options=None, **kwargs):
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        result = self.send(action, snapshot, options, reject=True, **kwargs)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)
        return result

    def test_authored_flower_upgrade_preserves_identity_and_replays_after_reload(self):
        self.prepare()
        raw = self.snapshot()
        result = self.send('upgradeBuilding', raw, sequence=40)
        self.assertEqual(result['data']['id'], 600)
        self.assertEqual(self.obj['itemName'], 'africandaisies_fullbloom')
        self.assertEqual(self.obj['state'], 'bare')
        for field in ('id', 'position', 'importedBuilding', 'plantTime'):
            self.assertEqual(self.obj[field], raw[field])
        self.assertEqual(self.save['userInfo']['player']['cash'], 197)
        self.assertEqual(self.save['userInfo']['player']['gold'], 500000)
        self.assertEqual(self.save['userInfo']['player']['xp'], 100015)
        accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.assertEqual(self.send('upgradeBuilding', raw, sequence=40)['data'], result['data'])
        self.assertEqual(self.save, accepted)
        self.assertEqual(self.path.read_bytes(), disk)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.save, accepted)
        self.assertEqual(self.send('upgradeBuilding', raw, sequence=40)['data'], result['data'])
        self.assertEqual(self.save, accepted)
        self.reject_unchanged('upgradeBuilding', {**raw, 'position': {'x': 20, 'y': 20, 'z': 0}}, sequence=40)
        self.reject_unchanged('upgradeBuilding')

    def test_flower_forgery_funds_and_unsupported_harvest_are_atomic(self):
        self.prepare()
        raw = self.snapshot()
        for changes in ({'id': 999}, {'itemName': 'cow'}, {'className': 'Animal'}):
            with self.subTest(changes=changes):
                self.reject_unchanged('upgradeBuilding', {**raw, **changes})
        self.reject_unchanged('upgradeBuilding', options={'cash': 0})
        self.reject_unchanged('plow', {**copy.deepcopy(raw), 'id': 999})
        self.reject_unchanged('clearWithered', {**copy.deepcopy(raw), 'state': 'grown', 'plantTime': 0})
        self.save['userInfo']['player']['cash'] = 2
        self.persist()
        self.reject_unchanged('upgradeBuilding')
        self.reject_unchanged('HarvestReadyNow')

    def test_new_gift_flower_placement_cannot_import_fed_stage_or_clock(self):
        import items
        now = 1_792_844_000
        self.prepare('africandaisies_bulb')
        item = items.get_item_by_name('africandaisies_bulb')
        self.save['world']['objectsArray'] = []
        self.save['userInfo']['player']['storageData'] = {'-1': {item['code']: [1, [], []]}}
        self.persist()
        raw = {'id': 701, 'itemName': item['name'], 'className': 'FeatureBuilding',
               'state': 'grown', 'isFullyBuilt': True, 'plantTime': 0, 'buildTime': 0,
               'expansionLevel': 2, 'expansionParts': {'5T8': 5}, 'capacity': 999,
               'contents': [{'itemCode': '5T8', 'numItem': 5}],
               'position': {'x': 10, 'y': 10, 'z': 0}, 'importedBuilding': {'keep': True}}
        with mock.patch.object(self.server.commands, 'timestamp_now', return_value=now):
            self.send('place', raw, {'isGift': True})
        self.assertEqual(self.obj['expansionLevel'], 1)
        self.assertEqual(self.obj['expansionParts'], {})
        self.assertEqual(self.obj['contents'], [])
        self.assertEqual(self.obj['capacity'], 0)
        self.assertEqual((self.obj['state'], self.obj['plantTime']), ('bare', now * 1000))
        self.assertEqual(self.obj['importedBuilding'], {'keep': True})
        self.assertNotIn(item['code'], self.save['userInfo']['player']['storageData']['-1'])
        self.reject_unchanged('upgradeBuilding')
        with mock.patch.object(self.server.commands, 'timestamp_now', return_value=now + 5):
            self.send('CompleteNow', options={'partName': 'part_flowerfood', 'isGift': False})
        self.assertEqual(self.obj['itemName'], 'africandaisies_singlebloom')
        self.assertEqual(self.obj['expansionLevel'], 2)
        self.assertEqual(self.obj['plantTime'], (now + 5) * 1000)
        self.assertEqual(self.save['userInfo']['player']['cash'], 195)
        self.send('upgradeBuilding')
        self.assertEqual(self.obj['itemName'], 'africandaisies_fullbloom')
        self.assertEqual(self.save['userInfo']['player']['cash'], 192)

    def test_bloom_harvest_refuses_without_coins_timer_or_receipt_changes(self):
        import paid_buildings
        # Start with a genuinely paid upgrade so its durable receipt must also
        # survive the rejected generic harvest, not merely an empty ledger.
        self.prepare('africandaisies_singlebloom')
        self.send('upgradeBuilding')
        self.assertEqual(self.obj['itemName'], 'africandaisies_fullbloom')
        self.assertTrue(self.save[paid_buildings.REQUESTS_KEY])
        for planted in (0, 1_800_000_000_000):
            with self.subTest(planted=planted):
                self.obj.update(state='bare', plantTime=planted)
                self.persist()
                for _ in range(2):
                    result = self.reject_unchanged('harvest')
                    self.assertIn('Flower harvest rewards are not restored', result['errorData'])
        for name in ('africandaisies_bulb', 'africandaisies_singlebloom'):
            with self.subTest(name=name):
                self.prepare(name)
                result = self.reject_unchanged('harvest')
                self.assertIn('Flower harvest rewards are not restored', result['errorData'])

    def test_flower_families_charge_each_authored_cash_price(self):
        for name, target, price in (
            ('carnationpurple_bulb', 'carnationpurple_fullbloom', 1),
            ('daisywhite_bulb', 'daisywhite_fullbloom', 2),
            ('africandaisies_bulb', 'africandaisies_fullbloom', 3),
            ('orangetulip_bulb', 'orangetulip_fullbloom', 4),
            ('hemlock_single', 'hemlock_full', 5),
            ('orchid_bulb', 'orchid_fullbloom', 6),
            ('pinkgladiolas_bulb', 'pinkgladiolas_fullbloom', 7),
        ):
            with self.subTest(name=name, price=price):
                self.prepare(name, expansionLevel=2)
                self.send('upgradeBuilding')
                self.assertEqual(self.obj['itemName'], target)
                self.assertEqual(self.save['userInfo']['player']['cash'], 200 - price)
                self.assertEqual(self.save['userInfo']['player']['gold'], 500000)
                self.assertEqual(self.save['userInfo']['player']['xp'], 100015)

    def test_flower_requires_finished_stage_and_stale_move_preserves_paid_identity(self):
        self.prepare(expansionLevel=1)
        self.reject_unchanged('upgradeBuilding')
        self.obj['expansionLevel'] = 2
        self.persist()
        raw = self.snapshot()
        self.send('upgradeBuilding')
        paid = copy.deepcopy(self.obj)
        raw.update(state='grown', plantTime=0, expansionLevel=1, capacity=999,
                   position={'x': 14, 'y': 15, 'z': 0})
        self.send('move', raw)
        for field in ('itemName', 'className', 'state', 'plantTime', 'expansionLevel'):
            self.assertEqual(self.obj[field], paid[field])
        self.assertEqual(self.obj['position'], raw['position'])
        self.assertNotEqual(self.obj.get('capacity'), 999)
        self.assertEqual(self.save['userInfo']['player']['cash'], 197)

    def test_initial_stable_cash_completion_uses_saved_materials(self):
        self.prepare('horsestablewhite', state='construction', isFullyBuilt=False,
            expansionLevel=1, expansionParts={},
            contents=[{'itemCode': 'K1', 'numItem': 9, 'importedRow': 'retain'},
                      {'itemCode': 'K2', 'numItem': 10}, {'itemCode': 'K3', 'numItem': 10},
                      {'itemCode': 'K4', 'numItem': 10}, {'itemCode': 'K5', 'numItem': 8}])
        self.persist()
        raw = self.snapshot()
        # The client has already completed its local object when it sends this.
        raw.update(state='built', isFullyBuilt=True, capacity=999, contents=[])
        result = self.send('CompleteNow', raw, {'partName': None, 'isGift': False})
        self.assertEqual(result['data']['id'], 600)
        self.assertTrue(self.obj['isFullyBuilt'])
        self.assertEqual(self.obj['state'], 'built')
        self.assertEqual(self.obj['itemName'], 'horsestablewhite')
        self.assertEqual(self.save['userInfo']['player']['cash'], 197)
        self.assertNotEqual(self.obj.get('capacity'), 999)
        self.assertEqual(self.obj['contents'][0]['importedRow'], 'retain')
        self.assertTrue(all(row['numItem'] == 0 for row in self.obj['contents']))
        self.assertEqual(self.obj['importedBuilding'], raw['importedBuilding'])
        self.assertEqual(self.save['userInfo']['player']['xp'], 100015)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertTrue(self.obj['isFullyBuilt'])
        self.assertEqual(self.save['userInfo']['player']['cash'], 197)

    def test_expansion_uses_saved_level_and_preserves_occupants(self):
        self.prepare('xuk_sheep_pen_finished', state='built', expansionLevel=1, capacity=20,
            expansionParts={'K1': 13, 'K4': 15, 'K5': 15, 'importedPart': {'keep': True}},
            contents=[{'itemCode': 'd7', 'numItem': 1, 'importedOccupant': 'retain'}])
        self.persist()
        raw = self.snapshot()
        raw.update(expansionLevel=2, capacity=999, expansionParts={}, contents=[])
        result = self.send('ExpandWithCurrency', raw)
        self.assertEqual(result['data']['id'], 600)
        self.assertEqual((self.obj['expansionLevel'], self.obj['capacity']), (2, 30))
        self.assertEqual(self.obj['expansionParts'], {'importedPart': {'keep': True}})
        self.assertEqual(self.obj['contents'], [{'itemCode': 'd7', 'numItem': 1, 'importedOccupant': 'retain'}])
        self.assertEqual(self.save['userInfo']['player']['cash'], 198)
        self.assertEqual(self.save['userInfo']['player']['gold'], 500000)
        self.assertEqual(self.obj['position'], raw['position'])
        self.assertEqual(self.obj['importedBuilding'], raw['importedBuilding'])
        self.assertEqual(self.save['userInfo']['player']['xp'], 100015)
        accepted = copy.deepcopy(self.save)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.save, accepted)

    def test_finished_english_stable_paid_expansion_replay_and_reload_preserve_horses(self):
        self.prepare('xukhorsestable_finished', state='built', expansionLevel=1, capacity=20,
            expansionParts={'K1': 9, 'K2': 10, 'K3': 10, 'K4': 10, 'K5': 10,
                            'importedPart': {'keep': True}},
            contents=[{'itemCode': 'HO', 'numItem': 1, 'importedOccupant': {'keep': [1]}}])
        horse = [1, ['sender'], [{'itemName': 'horse', 'name': 'Clover',
                                 'DNA': {'keep': [2]}, 'opaque': 'retain'}]]
        self.save['userInfo']['player']['storageData']['600'] = {'HO': copy.deepcopy(horse)}
        self.persist()
        raw = self.snapshot()
        raw.update(expansionLevel=99, capacity=999, expansionParts={}, contents=[], plantTime=0)
        result = self.send('CompleteNow', raw, {'partName': None, 'isGift': False}, sequence=40)
        self.assertEqual(result['data'], {'id': 600})
        self.assertEqual((self.obj['itemName'], self.obj['expansionLevel'], self.obj['capacity']),
                         ('xukhorsestable_finished', 2, 25))
        self.assertEqual(self.obj['expansionParts'], {'importedPart': {'keep': True}})
        self.assertEqual(self.obj['contents'], [{'itemCode': 'HO', 'numItem': 1,
                                               'importedOccupant': {'keep': [1]}}])
        self.assertEqual(self.save['userInfo']['player']['storageData']['600'], {'HO': horse})
        self.assertEqual(self.obj['plantTime'], 1000000)
        self.assertEqual(self.save['userInfo']['player']['cash'], 199)
        accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.assertEqual(self.send('CompleteNow', raw, {'partName': None, 'isGift': False}, sequence=40)['data'],
                         result['data'])
        self.assertEqual(self.save, accepted)
        self.assertEqual(self.path.read_bytes(), disk)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.save, accepted)
        self.assertEqual(self.send('CompleteNow', raw, {'partName': None, 'isGift': False}, sequence=40)['data'],
                         result['data'])
        self.assertEqual(self.save, accepted)
        self.reject_unchanged('CompleteNow', {**raw, 'itemName': 'horsestablewhite',
                                            'className': 'HorseStableBuilding'})
        self.save['userInfo']['player']['cash'] = 49
        self.persist()
        self.reject_unchanged('ExpandWithCurrency')

    def test_original_classic_transform_paid_completion_replays_and_reloads(self):
        import construction
        import items
        for name, reward in (('pigpen', 'pigpen_male_light_green'), ('nurserybarn', 'foal_gray')):
            with self.subTest(name=name):
                needs = construction._initial_requirements(items.get_item_by_name(name))
                self.prepare(name, state='construction', isFullyBuilt=False, expansionLevel=1,
                    contents=[{'itemCode': code, 'numItem': count - (code == 'K1')}
                              for code, (_, count) in needs.items()])
                self.persist()
                raw = self.snapshot()
                raw['tempId'] = float('nan')
                request = self.command('WorldService.performAction', ['TransformBuilding', raw, []], 40)
                with mock.patch.object(self.server.commands, 'timestamp_now', return_value=2_000_000):
                    result = fixtures.gateway_results(self, self.gateway([request]), [0])[0]
                self.assertEqual(result['data'], {'id': 600,
                    'finishedName': construction._CLASSIC[name], 'gift': reward})
                self.assertEqual(self.save['userInfo']['player']['cash'], 199)
                self.assertEqual((self.obj['itemName'], self.obj['capacity'], self.obj['plantTime']),
                                 (construction._CLASSIC[name], 20, 2_000_000_000))
                self.assertEqual(self.save['userInfo']['player']['storageData']['-1'][
                    items.get_item_by_name(reward)['code']][0], 1)
                accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
                for reload in (False, True):
                    if reload:
                        with redirect_stdout(io.StringIO()):
                            self.player.load_saves()
                    self.assertEqual(fixtures.gateway_results(self, self.gateway([request]), [0])[0]['data'],
                                     result['data'])
                    self.assertEqual(self.save, accepted)
                    self.assertEqual(self.path.read_bytes(), disk)
                self.reject_unchanged('TransformBuilding', {**raw, 'id': 601}, sequence=41)
                self.reject_unchanged('TransformBuilding', {**raw, 'className': 'Lamb'}, sequence=42)

    def test_classic_transform_insufficient_cash_and_wrong_identity_are_atomic(self):
        import construction
        import items
        self.prepare('pigpen', state='construction', isFullyBuilt=False, contents=[])
        self.save['userInfo']['player']['cash'] = 0
        self.persist()
        self.reject_unchanged('TransformBuilding', sequence=40)
        self.save['userInfo']['player']['cash'] = 100
        self.persist()
        self.reject_unchanged('TransformBuilding', options={'partName': 'brick'}, sequence=41)
        self.reject_unchanged('TransformBuilding', {**self.snapshot(),
            'itemName': 'nurserybarn', 'className': 'NurseryBarnBuilding'}, sequence=42)

    def _assert_finite_material_replay(self, name, level, parts, part_name, code, reward):
        self.prepare(name, state='built', expansionLevel=level, capacity=0 if name == 'xoz_emeraldcity' else 30,
                     expansionParts=parts)
        self.save['userInfo']['player']['storageData']['-1'] = {code: [1, ['sender'], []]}
        self.persist()
        raw = self.snapshot()
        options = {'storedItemName': part_name, 'isGift': True, 'numToStore': 1}
        result = self.send('store', raw, options, sequence=40)
        self.assertEqual(result['data'], {'id': 600, 'completeRewardItem': reward})
        accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
        for reload in (False, True):
            if reload:
                with redirect_stdout(io.StringIO()):
                    self.player.load_saves()
            self.assertEqual(self.send('store', raw, options, sequence=40)['data'], result['data'])
            self.assertEqual(self.save, accepted)
            self.assertEqual(self.path.read_bytes(), disk)
        self.reject_unchanged('store', raw, {**options, 'numToStore': 2}, sequence=40)
        self.assertEqual(self.save['userInfo']['player']['cash'], 200)

    def test_finite_final_material_replay_never_deposits_into_next_stage(self):
        self._assert_finite_material_replay('xoz_emeraldcity', 1, {'XjO': 6, 'Xj4': 6, 'xw6': 7},
            'part_silverbelltrowel', 'xw6', 'xoz_verdigrisspiraltree')
        self.assertEqual(self.obj['expansionLevel'], 2)
        self.assertEqual(self.obj['expansionParts'], {})

    def test_orchard_final_material_replay_survives_shared_identity_swap(self):
        import items
        item = items.get_item_by_name('xah_orchard_finished')
        stage = next(row for row in item['features']['feature'] if row['className'] == 'ExpandFManager')['upgrade'][-1]
        self._assert_finite_material_replay(item['name'], 2, {'3Ty': 9, '3TA': 10, '3Tz': 10},
            'part_leafblower', '3Ty', stage['rewardItem'])
        self.assertEqual(self.obj['itemName'], 'superorchard_featurebuilding')
        self.assertEqual(self.obj['expansionParts'], {})

    def test_orchard_expand_store_swap_base_harvest_replay_and_reload(self):
        self.prepare('orchard_featurebuilding_finished', state='ripe', expansionLevel=1,
            capacity=20, expansionParts={'3Ty': 9, '3TA': 10, '3Tz': 10, 'opaque': {'keep': [1]}},
            contents=[{'itemCode': 'CH', 'numItem': 20, 'opaque': {'keep': [2]}}], itemOrder=['CH'] * 20,
            storageMetadata={'unit metadata': {'keep': [3]}})
        self.save['userInfo']['player']['storageData'] = {
            '600': {'CH': [20, ['old sender'], [{'tree unit': 'keep'}]]},
            '-1': {'CH': [10, ['friend'], []]}}
        self.persist()
        raw = self.snapshot()
        self.send('CompleteNow', sequence=40)
        self.assertEqual((self.obj['expansionLevel'], self.obj['capacity'], self.obj['plantTime']),
                         (2, 30, 1000000))
        self.send('store', options={'storedItemName': 'cherry', 'isGift': True, 'numToStore': 10}, sequence=41)
        self.assertEqual(self.obj['contents'], [{'itemCode': 'CH', 'numItem': 30, 'opaque': {'keep': [2]}}])
        before_swap = copy.deepcopy(self.obj)
        ledger = copy.deepcopy(self.save['userInfo']['player']['storageData']['600'])
        raw_swap = self.snapshot()
        reply = self.send('CompleteNow', raw_swap, sequence=42)
        self.assertEqual(reply['data'], {'id': 600})
        self.assertEqual((self.obj['itemName'], self.obj['expansionLevel'], self.obj['capacity']),
                         ('superorchard_featurebuilding', 3, 40))
        self.assertEqual(self.obj['expansionParts'], {})
        for key in ('plantTime', 'contents', 'itemOrder', 'position', 'importedBuilding'):
            self.assertEqual(self.obj[key], before_swap[key])
        self.assertEqual(self.save['userInfo']['player']['storageData']['600'], ledger)
        self.assertEqual(self.save['userInfo']['player']['cash'], 169)
        self.assertEqual(self.send('CompleteNow', raw_swap, sequence=42)['data'], reply['data'])
        self.reject_unchanged('CompleteNow', sequence=43)
        self.reject_unchanged('HarvestReadyNow', sequence=44)
        raw_harvest = self.snapshot()
        gold = self.save['userInfo']['player']['gold']
        with mock.patch.object(self.server.commands, 'timestamp_now', return_value=2_000_000):
            harvest = self.send('harvest', raw_harvest, sequence=45)
        self.assertEqual(self.save['userInfo']['player']['gold'], gold + 30 * 18)
        self.assertEqual((self.obj['state'], self.obj['plantTime']), ('bare', 2_000_000_000))
        self.assertEqual(self.save['userInfo']['player']['cash'], 169)
        self.assertEqual(self.save['userInfo']['player']['xp'], 100015)
        self.assertEqual(self.save['userInfo']['player']['storageData']['600'], ledger)
        self.assertEqual(self.obj['contents'], before_swap['contents'])
        self.assertNotIn('mysterySeedRewardData', harvest['data'])
        self.assertNotIn('consolationGiftRewardData', harvest['data'])
        accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        with mock.patch.object(self.server.commands, 'timestamp_now', return_value=2_000_000):
            self.assertEqual(self.send('harvest', raw_harvest, sequence=45)['data'], harvest['data'])
            self.assertEqual(self.save, accepted)
            self.assertEqual(self.path.read_bytes(), disk)
            self.reject_unchanged('harvest', sequence=46)
        self.send('move', {**raw, 'position': {'x': 20, 'y': 20, 'z': 0},
                          'storageMetadata': {}, 'itemOrder': ['forged']}, sequence=47)
        self.assertEqual((self.obj['itemName'], self.obj['capacity'], self.obj['plantTime']),
                         ('superorchard_featurebuilding', 40, 2_000_000_000))
        self.assertEqual(self.obj['itemOrder'], before_swap['itemOrder'])
        self.assertEqual(self.obj['storageMetadata'], {'unit metadata': {'keep': [3]}})

    def test_orchard_final_material_grants_authored_tree_and_preserves_tree_units(self):
        import items
        item = items.get_item_by_name('xah_orchard_finished')
        stage = next(row for row in item['features']['feature'] if row['className'] == 'ExpandFManager')['upgrade'][-1]
        reward = stage['rewardItem']
        self.prepare(item['name'], state='ripe', expansionLevel=2, capacity=30,
            expansionParts={'3Ty': 9, '3TA': 10, '3Tz': 10},
            contents=[{'itemCode': 'CH', 'numItem': 1}], itemOrder=['CH'])
        self.save['userInfo']['player']['storageData'] = {
            '600': {'CH': [1, ['tree sender'], [{'tree unit': 'keep'}]]},
            '-1': {'3Ty': [1, ['sender'], []]}}
        self.persist()
        reply = self.send('store', options={'storedItemName': 'part_leafblower', 'isGift': True})
        self.assertEqual(reply['data'], {'id': 600, 'completeRewardItem': reward})
        self.assertEqual((self.obj['itemName'], self.obj['expansionLevel'], self.obj['capacity']),
                         ('superorchard_featurebuilding', 3, 40))
        self.assertEqual(self.obj['expansionParts'], {})
        self.assertEqual(self.obj['itemOrder'], ['CH'])
        self.assertEqual(self.save['userInfo']['player']['cash'], 200)
        self.assertEqual(self.save['userInfo']['player']['storageData']['-1'],
                         {items.get_item_by_name(reward)['code']: [1, [], []]})
        accepted = copy.deepcopy(self.save)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.save, accepted)

    def test_finite_named_completion_callback_and_gift_replay_reload(self):
        self.prepare('xoz_emeraldcity', state='built', expansionLevel=1, capacity=0,
                     expansionParts={'XjO': 6, 'Xj4': 6, 'xw6': 7, 'opaque': {'keep': [1]}})
        self.save['userInfo']['player']['storageData']['-1'] = {'s40': [2, ['sender'], [{'unit': 'keep'}]]}
        self.persist()
        raw = self.snapshot()
        raw.update(expansionLevel=99, expansionParts={}, plantTime=0, capacity=999)
        result = self.send('CompleteNow', raw, sequence=40)
        self.assertEqual(result['data'], {'id': 600, 'completeRewardItem': 'xoz_verdigrisspiraltree'})
        self.assertEqual((self.obj['expansionLevel'], self.obj['capacity'], self.obj['plantTime']),
                         (2, 0, 1000000))
        self.assertEqual(self.obj['expansionParts'], {'opaque': {'keep': [1]}})
        self.assertEqual(self.save['userInfo']['player']['cash'], 199)
        self.assertEqual(self.save['userInfo']['player']['storageData']['-1']['s40'],
                         [3, ['sender'], [{'unit': 'keep'}]])
        accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.send('CompleteNow', raw, sequence=40)['data'], result['data'])
        self.assertEqual(self.save, accepted)
        self.assertEqual(self.path.read_bytes(), disk)
        self.reject_unchanged('HarvestReadyNow', sequence=41)
        self.reject_unchanged('harvest', sequence=42)
        self.reject_unchanged('plow', sequence=43)

    def test_finite_last_material_uses_same_named_callback_without_cash(self):
        self.prepare('xoz_emeraldcity', state='built', expansionLevel=1, capacity=0,
                     expansionParts={'XjO': 6, 'Xj4': 6, 'xw6': 7})
        self.save['userInfo']['player']['storageData']['-1'] = {'xw6': [1, ['sender'], []]}
        self.persist()
        result = self.send('store', options={'storedItemName': 'part_silverbelltrowel',
                                           'numToStore': 1, 'isGift': True})
        self.assertEqual(result['data'], {'id': 600, 'completeRewardItem': 'xoz_verdigrisspiraltree'})
        self.assertEqual(self.obj['expansionLevel'], 2)
        self.assertEqual(self.save['userInfo']['player']['cash'], 200)
        self.assertEqual(self.save['userInfo']['player']['storageData']['-1'], {'s40': [1, [], []]})
        accepted = copy.deepcopy(self.save)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.save, accepted)

    def test_legacy_completion_gift_expansion_and_replay_survive_reload(self):
        import construction
        import items
        for name, finished, reward, expansion_cost in (
                ('nurserybarn', 'nurserybarn_finished', 'foal_gray', 50),
                ('pigpen', 'pigpenv2_finished', 'pigpen_male_light_green', 36)):
            with self.subTest(name=name):
                item = items.get_item_by_name(name)
                needs = construction._initial_requirements(item)
                self.prepare(name, state='construction', isFullyBuilt=False, expansionLevel=1,
                    expansionParts={'opaquePart': {'keep': [1]}},
                    contents=[{'itemCode': code, 'numItem': count - (code == 'K1'), 'importedRow': 'keep'}
                              for code, (_, count) in needs.items()])
                reward_code = items.get_item_by_name(reward)['code']
                self.save['userInfo']['player']['storageData']['-1'] = {
                    reward_code: [2, ['sender'], [{'opaque': 'keep'}]]}
                self.persist()
                raw = self.snapshot()
                raw.update(itemName=finished, className=items.get_item_by_name(finished)['className'],
                           state='built', isFullyBuilt=True, capacity=999, expansionLevel=99,
                           expansionParts={}, contents=[], plantTime=0)
                with mock.patch.object(self.server.commands, 'timestamp_now', return_value=2_000_000):
                    result = self.send('CompleteNow', raw, {'partName': None, 'isGift': False}, sequence=40)
                self.assertEqual(result['data'], {'id': 600, 'finishedName': finished, 'gift': reward})
                self.assertEqual((self.obj['itemName'], self.obj['expansionLevel'], self.obj['capacity'],
                                  self.obj['plantTime']), (finished, 1, 20, 2_000_000_000))
                self.assertTrue(all(row['numItem'] == 0 and row['importedRow'] == 'keep'
                                    for row in self.obj['contents']))
                self.assertEqual(self.save['userInfo']['player']['cash'], 199)
                self.assertEqual(self.save['userInfo']['player']['storageData']['-1'][reward_code],
                                 [3, ['sender'], [{'opaque': 'keep'}]])
                accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
                self.assertEqual(self.send('CompleteNow', raw, {'partName': None, 'isGift': False}, sequence=40)['data'],
                                 result['data'])
                self.assertEqual(self.save, accepted)
                self.assertEqual(self.path.read_bytes(), disk)
                with redirect_stdout(io.StringIO()):
                    self.player.load_saves()
                self.assertEqual(self.save, accepted)
                self.assertEqual(self.send('CompleteNow', raw, {'partName': None, 'isGift': False}, sequence=40)['data'],
                                 result['data'])
                self.assertEqual(self.save, accepted)
                occupant = {'itemCode': reward_code, 'numItem': 1, 'opaque': 'retain occupant'}
                self.obj['contents'].append(occupant)
                self.save['userInfo']['player']['storageData']['600'] = {
                    reward_code: [1, ['sender'], [{'itemName': reward, 'DNA': {'keep': [2]}}]]}
                self.persist()
                contents, ledger = copy.deepcopy(self.obj['contents']), copy.deepcopy(
                    self.save['userInfo']['player']['storageData']['600'])
                self.send('ExpandWithCurrency', sequence=41)
                self.assertEqual((self.obj['expansionLevel'], self.obj['capacity']), (2, 30))
                self.assertEqual(self.obj['plantTime'], 2_000_000_000)
                self.assertEqual(self.obj['contents'], contents)
                self.assertEqual(self.obj['expansionParts'], {'opaquePart': {'keep': [1]}})
                self.assertEqual(self.save['userInfo']['player']['storageData']['600'], ledger)
                self.assertEqual(self.save['userInfo']['player']['storageData']['-1'][reward_code][0], 3)
                self.assertEqual(self.save['userInfo']['player']['cash'], 199 - expansion_cost)
                expanded = copy.deepcopy(self.save)
                with redirect_stdout(io.StringIO()):
                    self.player.load_saves()
                self.assertEqual(self.save, expanded)
                self.reject_unchanged('CompleteNow', {**raw, 'itemName': name,
                                                    'className': item['className']}, sequence=42)
                self.send('move', {**raw, 'position': {'x': 14, 'y': 15, 'z': 0}}, sequence=43)
                self.assertEqual((self.obj['itemName'], self.obj['expansionLevel'], self.obj['capacity'],
                                  self.obj['plantTime']), (finished, 2, 30, 2_000_000_000))
                self.assertEqual(self.obj['contents'], contents)
                self.assertEqual(self.save['userInfo']['player']['storageData']['600'], ledger)
                self.assertEqual(self.obj['position'], {'x': 14, 'y': 15, 'z': 0})

    def test_herbgarden_expansion_readiness_and_larger_reward_survive_replay_reload(self):
        import items
        self.prepare('herbgarden', state='bare', expansionLevel=1, capacity=0,
                     plantTime=1_999_990_000,
                     expansionParts={'91w': 9, '91x': 10, '91z': 10, 'opaque': {'keep': [1]}})
        raw = self.snapshot()
        raw.update(expansionLevel=6, expansionParts={}, plantTime=0)
        with mock.patch.object(self.server.commands, 'timestamp_now', return_value=2_000_000):
            result = self.send('CompleteNow', raw, {'partName': None, 'isGift': False}, sequence=40)
            self.assertEqual(result['data'], {'id': 600})
            self.assertEqual((self.obj['expansionLevel'], self.obj['capacity'], self.obj['plantTime']),
                             (2, 0, 1_999_990_000))
            self.assertEqual(self.save['userInfo']['player']['cash'], 198)
            self.assertEqual(self.obj['expansionParts'], {'opaque': {'keep': [1]}})
            self.send('HarvestReadyNow', sequence=41)
            self.assertEqual(self.save['userInfo']['player']['cash'], 193)
            self.send('harvest', sequence=42)
        package = items.get_item_by_name('thaibasil_seedpackage')['code']
        self.assertEqual(self.save['userInfo']['player']['storageData']['-1'][package][0], 100)
        self.assertEqual(self.obj['plantTime'], 2_000_000_000)
        accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.save, accepted)
        self.assertEqual(self.send('CompleteNow', raw, {'partName': None, 'isGift': False}, sequence=40)['data'],
                         result['data'])
        self.assertEqual(self.save, accepted)
        self.assertEqual(self.path.read_bytes(), disk)

    def test_both_well_paid_expansions_increase_real_water_harvest_and_survive_reload(self):
        for name, action, reward in (('bldg_irrigationwell', 'CompleteNow', 125),
                                    ('bldg_irrigationwell_8hr', 'ExpandWithCurrency', 62)):
            with self.subTest(name=name):
                self.prepare(name, state='bare', expansionLevel=2, capacity=0,
                    expansionParts={'xde': 6, 'ple': 7, 'Wzu': 7, 'opaque': {'keep': [1]}})
                self.save['userInfo']['featureOptions']['irrigation'] = {'irrigation': {
                    'waterPlots': {'farm': {'amount': 20, 'opaque': 'keep'}}}}
                self.persist()
                raw = self.snapshot()
                raw.update(expansionLevel=7, plantTime=0, expansionParts={})
                with mock.patch.object(self.server.commands, 'timestamp_now', return_value=2_000_000):
                    result = self.send(action, raw, sequence=40)
                    self.assertEqual(result['data'], {'id': 600})
                    self.assertEqual((self.obj['expansionLevel'], self.obj['capacity'], self.obj['plantTime']),
                                     (3, 0, 1000000))
                    self.assertEqual(self.save['userInfo']['player']['cash'], 198)
                    self.send('harvest', sequence=41)
                water = self.save['userInfo']['featureOptions']['irrigation']['irrigation']['waterPlots']['farm']
                self.assertEqual(water, {'amount': 20 + reward, 'opaque': 'keep'})
                self.assertEqual(self.obj['plantTime'], 2_000_000_000)
                accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
                with redirect_stdout(io.StringIO()):
                    self.player.load_saves()
                self.assertEqual(self.save, accepted)
                self.assertEqual(self.send(action, raw, sequence=40)['data'], result['data'])
                self.assertEqual(self.save, accepted)
                self.assertEqual(self.path.read_bytes(), disk)

    def test_giving_building_direct_and_package_awards_are_atomic_and_replay_after_reload(self):
        import items
        self.prepare('bldg_holidaygivingtree', state='built', expansionLevel=1,
                     expansionParts={'opaque': {'keep': [1]}})
        raw = self.snapshot()
        raw.update(expansionLevel=31, expansionParts={}, plantTime=0)
        result = self.send('CompleteNow', raw, sequence=40)
        self.assertEqual(result['data'], {'id': 600})
        wolf = items.get_item_by_name('wolf_xhl_icey')['code']
        self.assertEqual(self.save['userInfo']['player']['cash'], 199)
        self.assertEqual(self.save['userInfo']['player']['storageData']['-1'][wolf][0], 1)
        self.assertEqual((self.obj['expansionLevel'], self.obj['capacity'], self.obj['plantTime']), (2, 25, 1000000))
        self.send('ExpandWithCurrency', sequence=41)
        unwither = items.get_item_by_name('consume_unwither')['code']
        gifts = self.save['userInfo']['player']['storageData']['-1']
        self.assertEqual(gifts[unwither][0], 1)
        self.assertNotIn('XX', gifts)
        self.assertEqual(self.save['userInfo']['player']['cash'], 196)
        self.assertEqual((self.obj['expansionLevel'], self.obj['plantTime']), (3, 1000000))
        accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.save, accepted)
        self.assertEqual(self.send('CompleteNow', raw, sequence=40)['data'], result['data'])
        self.assertEqual(self.save, accepted)
        self.assertEqual(self.path.read_bytes(), disk)
        self.send('move', {**raw, 'position': {'x': 14, 'y': 15, 'z': 0}}, sequence=42)
        self.assertEqual((self.obj['expansionLevel'], self.obj['state'], self.obj['plantTime']), (3, 'built', 1000000))
        self.save['userInfo']['player']['cash'] = 0
        self.persist()
        self.reject_unchanged('CompleteNow', sequence=43)

    def test_gnome_expansion_unlocks_real_capacity_store_and_withdrawal_after_reload(self):
        import items
        gnome = next(row for row in items.get_items() if row.get('className') == 'Gnome')
        self.prepare('gnomegarden_finished', state='built', expansionLevel=1, capacity=10,
            expansionParts={items.get_item_by_name(name)['code']: count for name, count in (
                ('part_toadstool', 13), ('part_tinywindow', 14), ('part_gardenfence', 14))},
            contents=[{'itemCode': gnome['code'], 'numItem': 10, 'imported': {'keep': [1]}}])
        self.save['userInfo']['player']['storageData'] = {
            '600': {gnome['code']: [10, ['old sender'], [{'opaque': 'keep'}]]},
            '-1': {gnome['code']: [15, ['friend'], []]}}
        self.persist()
        self.reject_unchanged('store', options={'storedItemName': gnome['name'], 'isGift': True}, sequence=39)
        raw = self.snapshot()
        raw.update(capacity=999, expansionLevel=6, contents=[], expansionParts={}, plantTime=0)
        self.send('CompleteNow', raw, sequence=40)
        self.assertEqual((self.obj['expansionLevel'], self.obj['capacity'], self.obj['plantTime']), (2, 25, 1000000))
        self.assertEqual(self.save['userInfo']['player']['cash'], 199)
        self.send('store', options={'storedItemName': gnome['name'], 'isGift': True, 'numToStore': 15}, sequence=41)
        self.assertEqual(self.obj['contents'], [{'itemCode': gnome['code'], 'numItem': 25, 'imported': {'keep': [1]}}])
        self.assertEqual(self.save['userInfo']['player']['storageData']['600'][gnome['code']],
                         [25, ['old sender', 'friend'], [{'opaque': 'keep'}]])
        self.assertNotIn(gnome['code'], self.save['userInfo']['player']['storageData']['-1'])
        self.send('place', {'id': 701, 'itemName': gnome['name'], 'className': 'Gnome', 'state': 'built',
                           'plantTime': 0, 'position': {'x': 20, 'y': 20, 'z': 0}},
                  {'isStorageWithdrawal': 600}, sequence=42)
        self.assertEqual(self.obj['contents'][0]['numItem'], 24)
        self.assertEqual(self.save['userInfo']['player']['cash'], 199)
        accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.save, accepted)
        self.assertEqual(self.path.read_bytes(), disk)
        self.assertEqual(self.send('CompleteNow', raw, sequence=40)['data'], {'id': 600})
        self.assertEqual(self.save, accepted)

    def test_paid_flower_food_finishes_saved_stage_then_allows_authored_upgrade(self):
        for action, options in (('CompleteNow', {'partName': None, 'isGift': False, 'currency': 'cash'}),
                                ('ExpandWithCurrency', {})):
            with self.subTest(action=action):
                self.prepare(expansionLevel=1, expansionParts={'5T8': 3})
                raw = self.snapshot()
                raw.update(expansionLevel=2, expansionParts={'5T8': 999}, plantTime=0)
                inventory = copy.deepcopy(self.save['userInfo']['player']['storageData'])
                # Feeding activates the flower's level-two witherer, so the
                # original completeExpansionLevel45045 starts its growth clock.
                with mock.patch.object(self.server.commands, 'timestamp_now', return_value=2_000_000):
                    result = self.send(action, raw, options)
                self.assertEqual(result['data']['id'], 600)
                self.assertEqual(self.obj['itemName'], 'africandaisies_singlebloom')
                self.assertEqual(self.obj['expansionLevel'], 2)
                self.assertEqual(self.obj['state'], 'bare')
                self.assertEqual(self.obj['plantTime'], 2_000_000_000)
                self.assertNotIn('5T8', self.obj['expansionParts'])
                self.assertEqual(self.obj['importedBuilding'], raw['importedBuilding'])
                self.assertEqual(self.obj['position'], raw['position'])
                self.assertEqual(self.save['userInfo']['player']['cash'], 198)
                self.assertEqual(self.save['userInfo']['player']['storageData'], inventory)
                self.send('upgradeBuilding')
                self.assertEqual(self.obj['itemName'], 'africandaisies_fullbloom')
                self.assertEqual(self.save['userInfo']['player']['cash'], 195)
                self.assertEqual(self.save['userInfo']['player']['xp'], 100015)

    def test_partial_part_purchase_and_ambiguous_gift_refusal_preserve_other_parts(self):
        self.prepare('turkeyroost_finished', state='built', expansionLevel=1, capacity=20,
            expansionParts={'K1': 13, 'K4': 10, 'K5': 10})
        self.persist()
        self.reject_unchanged('CompleteNow', options={'partName': 'brick', 'isGift': True})
        self.send('CompleteNow', options={'partName': 'brick', 'isGift': False})
        self.assertEqual(self.obj['expansionLevel'], 1)
        self.assertEqual(self.obj['expansionParts'], {'K1': 15, 'K4': 10, 'K5': 10})
        self.assertEqual(self.save['userInfo']['player']['cash'], 198)
        self.reject_unchanged('CompleteNow', options={'partName': 'brick', 'isGift': False})
        for options in ({'partName': 'cow', 'isGift': False}, {'partName': None, 'isGift': 1},
                        {'partName': None, 'isGift': False, 'currency': 'coins'}):
            with self.subTest(options=options):
                self.reject_unchanged('CompleteNow', options=options)

    def test_mixed_batch_keeps_accepted_actions_and_rolls_back_failed_charge(self):
        self.prepare()
        first = self.snapshot()
        second = {**copy.deepcopy(first), 'id': 601, 'itemName': 'amaryllis_bulb'}
        self.save['world']['objectsArray'].append(second)
        self.save['userInfo']['player']['cash'] = 4
        self.persist()
        requests = [
            self.command('WorldService.performAction', ['upgradeBuilding', first, [{}]], 10),
            self.command('WorldService.performAction', ['upgradeBuilding', copy.deepcopy(second), [{}]], 11),
            self.command('WorldService.performAction', ['move',
                {**copy.deepcopy(second), 'position': {'x': 12, 'y': 12, 'z': 0}}, [{}]], 12),
        ]
        results = fixtures.gateway_results(self, self.gateway(requests), [0, 29, 0])
        self.assertEqual(results[0]['data']['id'], 600)
        self.assertEqual(self.save['userInfo']['player']['cash'], 1)
        self.assertEqual(self.obj['itemName'], 'africandaisies_fullbloom')
        saved_second = self.save['world']['objectsArray'][1]
        self.assertEqual(saved_second['itemName'], 'amaryllis_bulb')
        self.assertEqual(saved_second['position'], {'x': 12, 'y': 12, 'z': 0})
        self.assertEqual(json.loads(self.path.read_text())['userInfo']['player']['cash'], 1)

    def test_single_material_bulk_gift_completion_and_retry_survive_reload(self):
        from unittest import mock
        self.prepare('africandaisies_bulb', expansionLevel=1, expansionParts={'5T8': 0})
        self.save['userInfo']['player']['storageData'] = {'-1': {'5T8': [7, ['senderA', 'senderB'],
                                                                           [{'unit': n} for n in range(7)]]}}
        self.persist()
        raw = self.snapshot()
        options = {'partName': 'part_flowerfood', 'isGift': True}
        with mock.patch.object(self.server.commands, 'timestamp_now', return_value=2_000_000):
            result = self.send('CompleteNow', raw, options, sequence=40)
        self.assertEqual(self.obj['itemName'], 'africandaisies_singlebloom')
        self.assertEqual(self.obj['plantTime'], 2_000_000_000)
        self.assertEqual(self.save['userInfo']['player']['cash'], 200)
        entry = self.save['userInfo']['player']['storageData']['-1']['5T8']
        self.assertEqual(entry[0], 2)
        self.assertEqual(entry[2], [{'unit': 5}, {'unit': 6}])
        accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.assertNotIn('_paidBuildingResponse', json.loads(disk))
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.send('CompleteNow', raw, options, sequence=40)['data'], result['data'])
        self.assertEqual(self.save, accepted)
        self.assertEqual(self.path.read_bytes(), disk)
        initialized = self.gateway([self.command('UserService.initUser', ['QA', 0, True, None], 41)])
        data = fixtures.gateway_results(self, initialized, [0])[0]['data']
        self.assertNotIn('_paidBuildingRequests', data)
        self.assertNotIn('_paidBuildingResponse', data)


if __name__ == '__main__':
    unittest.main()
