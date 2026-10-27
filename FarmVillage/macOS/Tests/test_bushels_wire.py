"""Home crop bushel rewards through the real AMF gateway and saved JSON."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import bushels
import items


class BushelWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway
    NOW = 2_000_000
    # Recovered catalog spellings are intentionally kept distinct. In
    # particular flower/grains/other must not silently disappear behind the
    # more common flowers/grain/misc families.
    FAMILY_CROPS = {
        'fruit': 'strawberry', 'grain': 'wheat', 'vegetable': 'soybeans',
        'flowers': 'sunflowers', 'misc': 'cotton', 'flower': 'brooch',
        'grains': 'capricorn', 'other': 'chardswiss',
    }

    def plot(self, ident=71, name='strawberry', age=100_000):
        return {'id': ident, 'className': 'Plot', 'itemName': name,
                'state': 'planted', 'plantTime': (self.NOW - age) * 1000,
                'position': {'x': ident * 4, 'y': 0, 'z': 0},
                'isJumbo': False, 'isBigPlot': False}

    def prepare(self, *plots, count=49, k=None, name='strawberry'):
        self.path = self.write_fixture()
        save = self.player.session('fixture-farmer')
        save['world']['objectsArray'] = list(plots) or [self.plot(name=name)]
        self.seed = items.get_item_by_name(name)
        self.code = self.seed['code']
        self.bushel = self.seed['bushelItemCode']
        save[bushels.COUNTERS_KEY] = {self.code: count}
        save.setdefault('craftingState', {}).update(craftingItems=[], maxCapacity=400)
        save['userInfo']['player'].update(mastery={}, seenFlags={}, storageData={}, buffs={})
        if k is not None:
            save['flashHotParams']['KBUSHEL_MULTIPLIER_TMPRT'] = k
        self.player.save_session('fixture-farmer')
        return save

    def harvest(self, plot=None, sequence=1):
        snapshot = copy.deepcopy(plot or self.plot())
        snapshot.update(state='fallow', plantTime=0)
        return self.command('WorldService.performAction', ['harvest', snapshot, []], sequence)

    def send(self, requests, errors):
        with mock.patch('commands.timestamp_now', return_value=self.NOW):
            response = self.gateway(requests)
        return fixtures.gateway_results(self, response, errors)

    def report(self, result):
        self.assertNotIn('foundBushel', result['data'])
        return result['metadata']['ActionDrops']['bushelReport']['dropTypeFuncResult']

    def quantity(self, save=None):
        save = self.player.session('fixture-farmer') if save is None else save
        return sum(row['quantity'] for row in save['craftingState']['craftingItems']
                   if row['itemCode'] == self.bushel)

    def test_ripe_harvest_persists_one_bushel_and_exact_action_drop_shape(self):
        self.prepare()
        result = self.send([self.harvest()], [0])[0]
        report = self.report(result)
        self.assertEqual(report, {
            '0': {'foundBushel': {'bushelCode': self.bushel, 'bushelsAddedToInventory': 1,
                                 'bushelsAddedToSharedReward': 0, 'bushelAddedToStall': False}},
            'length': 1, 'newHarvestQuantities': [{'itemCode': self.code, 'quantity': 0}]})
        saved = json.loads(self.path.read_text())
        self.assertEqual(self.quantity(saved), 1)
        self.assertEqual(saved[bushels.COUNTERS_KEY], {self.code: 0})
        self.assertEqual(saved['userInfo']['player']['storageData']['-1']['ms'], [1, [], []])
        self.assertNotIn('FirstMarketStall', saved['userInfo']['player']['seenFlags'])
        self.assertNotIn(bushels.PENDING_KEY, saved)
        self.assertEqual(self.player.session('fixture-farmer'), saved)

    def test_counter_only_response_and_fallow_retry_do_not_award_twice(self):
        self.prepare(count=48)
        result = self.send([self.harvest()], [0])[0]
        self.assertEqual(self.report(result), {
            'length': 0, 'newHarvestQuantities': [{'itemCode': self.code, 'quantity': 49}]})
        saved = self.path.read_bytes()
        result = self.send([self.harvest(sequence=2)], [0])[0]
        self.assertEqual(result['metadata']['ActionDrops'], {})
        self.assertEqual(self.path.read_bytes(), saved)
        self.assertEqual(self.quantity(), 0)

    def test_mature_imported_withered_crop_keeps_peaceful_harvest_compatibility(self):
        for enabled in (True, False):
            with self.subTest(peaceful=enabled):
                save = self.prepare()
                save['peacefulMode'] = {'enabled': enabled}
                save['world']['objectsArray'][0]['state'] = 'withered'
                self.player.save_session('fixture-farmer')
                before = self.path.read_bytes()
                result = self.send([self.harvest()], [0 if enabled else 29])[0]
                if enabled:
                    self.assertEqual(self.report(result)['length'], 1)
                    self.assertEqual(self.quantity(json.loads(self.path.read_text())), 1)
                else:
                    self.assertEqual(self.path.read_bytes(), before)

    def test_equipment_aggregates_awards_only_in_outer_metadata(self):
        plots = [self.plot(71), self.plot(72)]
        self.prepare(*plots, count=0, k=1)
        result = self.send([self.command('EquipmentWorldService.onUseEquipment', [
            'harvest', {'id': 999}, [{'id': row['id']} for row in plots], 'strawberry'])], [0])[0]
        report = self.report(result)
        self.assertEqual(report['length'], 2)
        self.assertEqual(report['newHarvestQuantities'], [{'itemCode': self.code, 'quantity': 0}])
        for index in ('0', '1'):
            self.assertEqual(report[index]['foundBushel']['bushelsAddedToInventory'], 1)
        self.assertEqual(len(result['data']), 2)
        for child in result['data']:
            self.assertEqual(child['metadata'], {})
            self.assertNotIn('foundBushel', child['data'])
        # The same TFarmTransaction processes each equipment child and carries
        # the previous rawResult's ActionDrops through them. The network manager
        # emits one transaction-completed event after the final child.
        previous = result
        for child in result['data']:
            metadata = previous['metadata']
            previous = child
            for key in ('QuestComponent', 'ActionDrops'):
                if key in metadata:
                    child['metadata'][key] = metadata[key]
        final = previous['metadata']['ActionDrops']['bushelReport']['dropTypeFuncResult']
        self.assertEqual(sum(final[str(index)]['foundBushel']['bushelsAddedToInventory']
                             for index in range(final['length'])), 2)
        self.assertEqual(self.quantity(), 2)
        self.assertEqual(self.player.session('fixture-farmer')['userInfo']['player']['storageData']['-1']['ms'][0], 1)

    def test_invalid_sibling_rolls_back_without_erasing_prior_bushel_award(self):
        first, early = self.plot(71), self.plot(72, age=0)
        self.prepare(first, early)
        results = self.send([self.harvest(first, 1), self.harvest(early, 2),
                             self.command('UserService.incrementActionCount', ['bushel-sibling'], 3)], [0, 29, 0])
        self.assertEqual(self.report(results[0])['length'], 1)
        self.assertEqual(results[1]['metadata'].get('ActionDrops', {}), {})
        self.assertEqual(results[2]['metadata']['ActionDrops'], {})
        save = self.player.session('fixture-farmer')
        self.assertEqual(self.quantity(save), 1)
        self.assertEqual(save[bushels.COUNTERS_KEY], {self.code: 0})
        self.assertEqual(save['world']['objectsArray'][1], early)
        self.assertEqual(save['userInfo']['player']['actionCounts']['bushel-sibling'], 1)
        self.assertEqual(save, json.loads(self.path.read_text()))

    def test_equipment_failure_rolls_back_all_plots_counters_and_gift(self):
        plots = [self.plot(71), self.plot(72, age=0)]
        self.prepare(*plots)
        before = self.path.read_bytes()
        self.send([self.command('EquipmentWorldService.onUseEquipment', [
            'harvest', {'id': 999}, [{'id': row['id']} for row in plots], 'strawberry'])], [29])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.quantity(), 0)
        self.assertEqual(self.player.session('fixture-farmer')[bushels.COUNTERS_KEY], {self.code: 49})
        self.assertNotIn(bushels.PENDING_KEY, self.player.session('fixture-farmer'))

    def test_awards_counters_and_first_stall_gift_survive_reload_init(self):
        self.prepare(count=49)
        self.send([self.harvest()], [0])
        self.player.load_saves()
        init = self.send([self.command('UserService.initUser', ['QA', 0, True, {}], 2)], [0])[0]['data']
        self.assertEqual(self.quantity(init), 1)
        self.assertEqual(init[bushels.COUNTERS_KEY], {self.code: 0})
        self.assertEqual(init['userInfo']['player']['storageData']['-1']['ms'], [1, [], []])
        self.assertNotIn(bushels.PENDING_KEY, init)
        self.assertEqual(self.quantity(json.loads(self.path.read_text())), 1)

    def test_every_ordinary_catalog_family_awards_its_bushel_and_reloads(self):
        recovered = set()
        for seed in items.get_items():
            if seed.get('type') != 'seed' or not isinstance(seed.get('bushelItemCode'), str):
                continue
            item = items.get_item_by_code(seed['bushelItemCode'])
            if bushels.is_stall_bushel(item):
                recovered.add(item.get('subtype'))
        self.assertEqual(set(self.FAMILY_CROPS), recovered)
        for family, name in self.FAMILY_CROPS.items():
            with self.subTest(family=family, crop=name):
                plot = self.plot(name=name, age=200_000)
                self.prepare(plot, name=name)
                self.assertEqual(items.get_item_by_code(self.bushel)['subtype'], family)
                self.assertEqual(self.report(self.send([self.harvest(plot)], [0])[0]), {
                    '0': {'foundBushel': {'bushelCode': self.bushel,
                        'bushelsAddedToInventory': 1, 'bushelsAddedToSharedReward': 0,
                        'bushelAddedToStall': False}},
                    'length': 1,
                    'newHarvestQuantities': [{'itemCode': self.code, 'quantity': 0}]})
                self.player.load_saves()
                initialized = self.send([self.command('UserService.initUser',
                    ['Family QA', 0, True, {}], 2)], [0])[0]['data']
                self.assertEqual(self.quantity(initialized), 1)
                self.assertEqual(initialized[bushels.COUNTERS_KEY], {self.code: 0})
                self.assertEqual(self.quantity(json.loads(self.path.read_text())), 1)
                self.assertEqual(initialized['userInfo']['player']['storageData']['-1']['ms'][0], 1)

    def test_mixed_family_equipment_keeps_crop_identity_counters_and_one_stall_gift(self):
        names = tuple(self.FAMILY_CROPS.values())
        plots = [self.plot(71 + index, name, age=200_000)
                 for index, name in enumerate(names)]
        save = self.prepare(*plots)
        seeds = [items.get_item_by_name(name) for name in names]
        save[bushels.COUNTERS_KEY] = {seed['code']: 49 for seed in seeds}
        save[bushels.COUNTERS_KEY]['unrelated-imported-seed'] = 17
        self.player.save_session('fixture-farmer')
        result = self.send([self.command('EquipmentWorldService.onUseEquipment', [
            'harvest', {'id': 999}, [{'id': plot['id']} for plot in plots], None])], [0])[0]
        report = self.report(result)
        self.assertEqual(report['length'], len(seeds))
        self.assertEqual([report[str(index)]['foundBushel']['bushelCode']
                          for index in range(len(seeds))],
                         [seed['bushelItemCode'] for seed in seeds])
        self.assertEqual(report['newHarvestQuantities'],
                         [{'itemCode': seed['code'], 'quantity': 0} for seed in seeds])
        for child in result['data']:
            self.assertEqual(child['metadata'], {})
        saved = json.loads(self.path.read_text())
        self.assertEqual({row['itemCode']: row['quantity']
                          for row in saved['craftingState']['craftingItems']},
                         {seed['bushelItemCode']: 1 for seed in seeds})
        self.assertEqual(saved[bushels.COUNTERS_KEY],
                         {**{seed['code']: 0 for seed in seeds}, 'unrelated-imported-seed': 17})
        self.assertEqual(saved['userInfo']['player']['storageData']['-1']['ms'], [1, [], []])
        self.player.load_saves()
        self.assertEqual(self.player.session('fixture-farmer'), saved)

    def test_ambiguous_archived_bushel_mapping_refuses_without_any_harvest_mutation(self):
        plot = self.plot(name='snowballflower', age=200_000)
        save = self.prepare(plot, name='snowballflower')
        self.assertEqual(self.seed['bushelItemCode'], ['sb', '1572'])
        before = copy.deepcopy(save)
        before_bytes = self.path.read_bytes()
        result = self.send([self.harvest(plot)], [29])[0]
        self.assertIn('bushel mapping is ambiguous and is not restored', result['errorData'])
        self.assertEqual(save, before)
        self.assertEqual(self.path.read_bytes(), before_bytes)
        self.assertNotIn(bushels.PENDING_KEY, save)
        self.player.load_saves()
        self.assertEqual(self.player.session('fixture-farmer'), before)


if __name__ == '__main__':
    unittest.main()
