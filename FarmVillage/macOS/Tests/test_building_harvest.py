"""Deterministic Herb Garden harvests, paid readiness and usable seed units."""
from contextlib import ExitStack, redirect_stdout
import copy
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence
import building_harvest as harvest
import items
import paid_buildings

NOW = 2_000_000
DAY = 82_800
SIZES = {'CSeedPackageSize': 20, 'CSeedPackageSize_100': 100, 'CSeedPackageSize_200': 200,
         'CSeedPackageSize_400': 400, 'CSeedPackageSize_600': 600, 'CSeedPackageSize_900': 900,
         'herbgardenHarvestReadyNowCashPrice': 5}


class BuildingHarvestTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.catalog = [{'name': 'herbgarden', 'code': '91v', 'className': 'FeatureBuilding', 'type': 'building',
                         'growTime': '1', 'initialExpansionLevel': '1', 'features': {'feature': {
                             'className': 'SeedDispenserHarvestFManager', 'name': 'harvester',
                             'rewardType': 'SeedDispenserRewardGenerator', 'rewardMultiplier': 'oneFixed',
                             'limitedCoinYield': '1500'}}},
                        {'name': 'strawberry', 'code': 'ST', 'type': 'seed', 'cost': '10'}]
        for index, name in enumerate(harvest.HERBS):
            self.catalog += [{'name': name, 'code': f'herb{index}', 'type': 'seed',
                              'seedpackage': name + '_seedpackage', 'mastery': 'true',
                              'masteryLevel': [{'count': '10'}, {'count': '20'}, {'count': '30'}]},
                             {'name': name + '_seedpackage', 'code': f'package{index}',
                              'className': 'CSeedPackage', 'type': 'consumable', 'seed': name}]
        self.stack.enter_context(mock.patch.object(items, '_cached_items', {'settings': {'items': {'item': self.catalog}}}))
        self.stack.enter_context(mock.patch.object(harvest, '_variant', return_value=3))
        self.stack.enter_context(mock.patch.object(harvest, 'get_farming_int', side_effect=lambda key, default=0: SIZES.get(key, default)))
        self.save = {'world': {'objectsArray': []}, 'userInfo': {'currentWorldType': 'farm', 'player': {
            'cash': 50, 'gold': 1000, 'xp': 100015, 'mastery': {}, 'storageData': {}}},
            'imported': {'retain': [1, 2]}}

    def garden(self, *, level=1, ripe=True, ident=600):
        obj = {'id': ident, 'itemName': 'herbgarden', 'className': 'FeatureBuilding',
               'state': 'bare', 'isFullyBuilt': True, 'expansionLevel': level,
               'plantTime': (NOW - DAY if ripe else NOW - 10) * 1000,
               'position': {'x': 10, 'y': 11}, 'imported': {'keep': True}}
        self.save['world']['objectsArray'].append(obj)
        return obj

    def test_original_cms_seed_order_and_all_six_package_sizes(self):
        self.assertEqual(harvest._configuration()[0], harvest.HERBS)
        for level, quantity in enumerate((20, 100, 200, 400, 600, 900), 1):
            with self.subTest(level=level):
                self.save['world']['objectsArray'] = []
                self.save['userInfo']['player']['storageData'] = {}
                obj = self.garden(level=level)
                self.assertEqual(harvest.harvest(self.save, obj, now=NOW), 1)
                self.assertEqual(self.save['userInfo']['player']['storageData']['-1']['package0'][0], quantity)
                self.assertEqual(self.save['userInfo']['player']['gold'], 1000)
                self.assertEqual(self.save['userInfo']['player']['xp'], 100015)

    def test_first_unmastered_herb_advances_in_order_then_all_mastered_pays_original_coins(self):
        for index in range(len(harvest.HERBS)):
            self.save['world']['objectsArray'] = []
            self.save['userInfo']['player']['storageData'] = {}
            self.save['userInfo']['player']['mastery'] = {f'herb{n}': 2 for n in range(index)}
            obj = self.garden()
            harvest.harvest(self.save, obj, now=NOW)
            self.assertEqual(set(self.save['userInfo']['player']['storageData']['-1']), {f'package{index}'})
        self.save['world']['objectsArray'] = []
        self.save['userInfo']['player']['storageData'] = {}
        self.save['userInfo']['player']['mastery'] = {f'herb{n}': 2 for n in range(10)}
        harvest.harvest(self.save, self.garden(), now=NOW)
        self.assertEqual(self.save['userInfo']['player']['gold'], 2500)
        self.assertEqual(self.save['userInfo']['player']['storageData'], {})

    def test_paid_readiness_charges_five_cash_without_reward_then_harvests_once(self):
        obj = self.garden(ripe=False)
        result = paid_buildings.perform(self.save, 'HarvestReadyNow', copy.deepcopy(obj), [], request_id=1, now=NOW)
        paid_buildings.take_response(self.save)
        self.assertEqual(result, {'id': 600})
        self.assertEqual(self.save['userInfo']['player']['cash'], 45)
        self.assertEqual(self.save['userInfo']['player']['storageData'], {})
        target = self.save['world']['objectsArray'][0]
        self.assertEqual((target['state'], target['plantTime']), ('grown', (NOW - DAY) * 1000))
        self.assertEqual(harvest.harvest(self.save, target, now=NOW, request_id=2), 1)
        target = self.save['world']['objectsArray'][0]
        before = copy.deepcopy(self.save)
        self.assertEqual(harvest.harvest(self.save, target, now=NOW + 1, request_id=2), 0)
        self.assertEqual(self.save, before)
        with self.assertRaises(ValueError):
            harvest.harvest(self.save, target, now=NOW + 1, request_id=3)
        self.assertEqual(self.save, before)

    def test_insufficient_funds_or_ready_clock_never_changes_save(self):
        obj = self.garden(ripe=False)
        self.save['userInfo']['player']['cash'] = 4
        before = copy.deepcopy(self.save)
        with self.assertRaises(ValueError):
            paid_buildings.perform(self.save, 'HarvestReadyNow', copy.deepcopy(obj), [], now=NOW)
        self.assertEqual(self.save, before)
        self.save['userInfo']['player']['cash'] = 50
        self.save['world']['objectsArray'][0]['plantTime'] = (NOW - DAY) * 1000
        before = copy.deepcopy(self.save)
        with self.assertRaises(ValueError):
            paid_buildings.perform(self.save, 'HarvestReadyNow', copy.deepcopy(obj), [], now=NOW)
        self.assertEqual(self.save, before)

    def test_seed_use_consumes_one_saved_unit_and_preserves_sparse_metadata(self):
        player = self.save['userInfo']['player']
        player['storageData'] = {'-1': {'package0': [2, ['sender'], [{'opaque': 'one'}]]}}
        seed = items.get_item_by_name('thaibasil')
        self.assertTrue(harvest.has_seed(self.save, seed))
        snapshot = {'itemName': 'thaibasil', 'className': 'Plot', 'state': 'planted'}
        self.assertTrue(harvest.withdraw_seed_for_placement(self.save, seed, snapshot, [{}]))
        self.assertEqual(player['storageData']['-1']['package0'], [1, ['sender'], [{'opaque': 'one'}]])
        self.assertTrue(harvest.withdraw_seed_for_placement(self.save, seed, snapshot, [{}]))
        self.assertNotIn('package0', player['storageData']['-1'])
        self.assertIsNone(harvest.withdraw_seed_for_placement(self.save, seed, snapshot, [{}]))
        self.assertFalse(harvest.has_seed(self.save, items.get_item_by_name('strawberry')))

    def test_unrelated_or_explicit_gift_placement_does_not_consume_herb_packages(self):
        self.save['userInfo']['player']['storageData'] = {'-1': {'package0': [2, [], []]}}
        before = copy.deepcopy(self.save)
        seed = items.get_item_by_name('thaibasil')
        self.assertIsNone(harvest.withdraw_seed_for_placement(self.save, seed,
            {'className': 'Plot', 'state': 'planted'}, [{'isGift': True}]))
        self.assertIsNone(harvest.withdraw_seed_for_placement(self.save, seed,
            {'className': 'Animal', 'state': 'bare'}, [{}]))
        self.assertEqual(self.save, before)

    def test_bad_mastery_inventory_clock_or_experiment_is_atomic(self):
        for mutation in ('mastery', 'inventory', 'clock', 'experiment'):
            with self.subTest(mutation=mutation):
                obj = self.garden()
                if mutation == 'mastery':
                    self.save['userInfo']['player']['mastery'] = {'herb0': True}
                elif mutation == 'inventory':
                    self.save['userInfo']['player']['storageData'] = {'-1': {'package0': [1, 'bad', []]}}
                elif mutation == 'clock':
                    obj['plantTime'] = (NOW + 1) * 1000
                else:
                    self.stack.enter_context(mock.patch.object(harvest, '_variant', return_value=0))
                before = copy.deepcopy(self.save)
                with self.assertRaises(ValueError):
                    harvest.harvest(self.save, obj, now=NOW)
                self.assertEqual(self.save, before)
                self.save['world']['objectsArray'] = []
                self.save['userInfo']['player'].update(mastery={}, storageData={})

    def test_placement_and_moves_cannot_forge_harvest_progress(self):
        raw = {'id': 600, 'itemName': 'herbgarden', 'className': 'FeatureBuilding', 'state': 'grown',
               'expansionLevel': 6, 'plantTime': 0, 'capacity': 999, 'contents': [{'fake': True}]}
        placed = harvest.initialize_placement(raw, now=NOW)
        self.assertEqual((placed['expansionLevel'], placed['state'], placed['plantTime']), (1, 'bare', NOW * 1000))
        self.assertEqual(placed['contents'], [])
        moved = harvest.preserve_fields(placed, {**raw, 'position': {'x': 11, 'y': 12}}, action='move')
        self.assertEqual(moved['plantTime'], placed['plantTime'])
        self.assertEqual(moved['expansionLevel'], 1)
        self.assertEqual(moved['position'], {'x': 11, 'y': 12})
        for action in ('clearWithered', 'plow', 'use', 'plant'):
            protected = harvest.preserve_fields(placed, raw, action=action)
            self.assertEqual((protected['state'], protected['plantTime']), ('bare', NOW * 1000))
            with self.assertRaises(ValueError):
                harvest.guard_action(action, placed, raw)


if __name__ == '__main__':
    unittest.main()
