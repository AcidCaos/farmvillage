"""Simplified Bushel Report cadence, inventory and AMF shape."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence
import bushels
import items
import pyamf
NOW = 2000000
CATALOG = [{'name': 'berry', 'code': 'SB', 'type': 'seed', 'bushelItemCode': 'sb', 'growTime': '1'}, {'name': 'berrybushel', 'code': 'sb', 'type': 'bushel', 'className': 'CBushel', 'subtype': 'fruit'}, {'name': 'wheat', 'code': 'WW', 'type': 'seed', 'bushelItemCode': 'ww', 'growTime': '1'}, {'name': 'wheatbushel', 'code': 'ww', 'type': 'bushel', 'className': 'CBushel', 'subtype': 'grain'}, {'name': 'marketstall', 'code': 'ms', 'type': 'building', 'className': 'MarketStallBuilding'}, {'name': 'otherstall', 'code': 'os', 'type': 'building', 'className': 'MarketStallBuilding'}, {'name': 'silo', 'code': 'ss', 'type': 'bushel', 'className': 'CBushel', 'subtype': 'animal'}, {'name': 'gain', 'code': 'bg', 'type': 'buff', 'className': 'BPermanentTypeGain', 'subtype': 'bushel_gain'}]

def fixture():
    return {'userInfo': {'currentWorldType': 'farm', 'player': {'mastery': {}, 'seenFlags': {}, 'storageData': {}, 'buffs': {}}}, 'world': {'objectsArray': [{'id': 1, 'className': 'Plot', 'itemName': 'berry', 'state': 'planted', 'plantTime': (NOW - 1000) * 1000, 'position': {'x': 0, 'y': 0, 'z': 0}}]}, 'craftingState': {'craftingItems': [], 'maxCapacity': 400, 'recipeQueue': {'bakery': ['keep']}}}

class BushelHarvestTests(unittest.TestCase):

    def setUp(self):
        self.save = fixture()
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(items, '_cached_items', {'settings': {'items': {'item': copy.deepcopy(CATALOG)}}}).start()
        mock.patch.object(bushels.peaceful, 'grow_seconds', return_value=1000).start()
        mock.patch.object(bushels, 'get_farming_int', side_effect=lambda name, default: default).start()

    def harvest(self, count=None):
        if count is not None:
            self.save[bushels.COUNTERS_KEY] = {'SB': count}
        bushels.harvest(self.save, items.get_item_by_name('berry'), self.save['world']['objectsArray'][0], now=NOW)

    def test_49_50_boundary_and_counter_only_then_award_envelope(self):
        self.harvest(48)
        self.assertEqual(self.save[bushels.COUNTERS_KEY], {'SB': 49})
        self.assertEqual(self.save['craftingState']['craftingItems'], [])
        report = bushels.take_metadata(self.save)['bushelReport']['dropTypeFuncResult']
        self.assertEqual(report, {'length': 0, 'newHarvestQuantities': [{'itemCode': 'SB', 'quantity': 49}]})
        self.harvest()
        self.assertEqual(self.save[bushels.COUNTERS_KEY]['SB'], 0)
        self.assertEqual(self.save['craftingState']['craftingItems'], [{'itemCode': 'sb', 'quantity': 1, 'price': None}])
        self.assertEqual(self.save['craftingState']['recipeQueue'], {'bakery': ['keep']})
        report = bushels.take_metadata(self.save)['bushelReport']['dropTypeFuncResult']
        self.assertEqual(report['0']['foundBushel'], {'bushelCode': 'sb', 'bushelsAddedToInventory': 1, 'bushelsAddedToSharedReward': 0, 'bushelAddedToStall': False})
        self.assertEqual(report['length'], 1)
        self.assertEqual(bushels.take_metadata(self.save), {})

    def test_mastery_thresholds_and_supercrop_flag(self):
        for index, threshold in ((-1, 50), (0, 25), (1, 16), (2, 12)):
            with self.subTest(stars=index + 1):
                self.save = fixture()
                self.save['userInfo']['player']['mastery'] = {'SB': index}
                self.harvest(threshold - 1)
                self.assertEqual(self.save['craftingState']['craftingItems'][0]['quantity'], 1)
                self.assertEqual(self.save[bushels.COUNTERS_KEY]['SB'], 0)
        self.save = fixture()
        items.get_item_by_name('berry')['superCrop'] = 'true'
        self.harvest(11)
        self.assertEqual(self.save['craftingState']['craftingItems'][0]['quantity'], 1)

    def test_independent_seed_counters_and_original_k_override(self):
        self.save[bushels.COUNTERS_KEY] = {'WW': 31}
        self.save['flashHotParams'] = {'KBUSHEL_MULTIPLIER_TMPRT': '2'}
        self.harvest()
        self.assertEqual(self.save[bushels.COUNTERS_KEY], {'WW': 31, 'SB': 1})
        self.harvest()
        self.assertEqual(self.save[bushels.COUNTERS_KEY], {'WW': 31, 'SB': 0})

    def test_full_inventory_carries_credit_without_overflow_or_free_gift(self):
        self.save['craftingState']['craftingItems'] = [{'itemCode': 'ww', 'quantity': 400, 'price': 8, 'other': 'keep'}]
        self.harvest(49)
        self.assertEqual(self.save[bushels.COUNTERS_KEY]['SB'], 50)
        self.assertNotIn('-1', self.save['userInfo']['player']['storageData'])
        self.save['craftingState']['craftingItems'][0]['quantity'] -= 1
        self.harvest()
        self.assertEqual(self.save[bushels.COUNTERS_KEY]['SB'], 1)
        self.assertEqual(self.save['craftingState']['craftingItems'], [{'itemCode': 'ww', 'quantity': 399, 'price': 8, 'other': 'keep'}, {'itemCode': 'sb', 'quantity': 1, 'price': None}])

    def test_larger_imported_capacity_and_stack_metadata_are_preserved(self):
        self.save['craftingState'].update(maxCapacity=501, craftingItems=[{'itemCode': 'sb', 'quantity': 500, 'price': 3, 'imported': True}])
        self.harvest(49)
        self.assertEqual(self.save['craftingState']['craftingItems'][0], {'itemCode': 'sb', 'quantity': 501, 'price': 3, 'imported': True})
        self.assertEqual(self.save['craftingState']['maxCapacity'], 501)

    def test_special_bushels_do_not_consume_stall_capacity(self):
        self.save['craftingState']['craftingItems'] = [{'itemCode': 'ss', 'quantity': 400, 'price': None}]
        self.harvest(49)
        self.assertEqual(self.save['craftingState']['craftingItems'][-1]['quantity'], 1)

    def test_legacy_duplicate_nonbushel_placeholders_are_preserved(self):
        placeholders = [{'itemCode': 'SB', 'quantity': 2, 'price': None}] * 2
        self.save['craftingState']['craftingItems'] = copy.deepcopy(placeholders)
        self.harvest(49)
        self.assertEqual(self.save['craftingState']['craftingItems'][:2], placeholders)
        self.assertEqual(self.save['craftingState']['craftingItems'][-1]['quantity'], 1)

    def test_withered_crop_harvest_requires_peaceful_and_the_original_maturity(self):
        for enabled, age, accepted in ((True, 1000, True), (False, 1000, False), (True, 0, False)):
            with self.subTest(enabled=enabled, age=age):
                self.save = fixture()
                self.save['peacefulMode'] = {'enabled': enabled}
                self.save['world']['objectsArray'][0].update(state='withered', plantTime=(NOW - age) * 1000)
                self.save[bushels.COUNTERS_KEY] = {'SB': 49}
                before = copy.deepcopy(self.save)
                if accepted:
                    self.harvest()
                    self.assertEqual(self.save['craftingState']['craftingItems'][0]['quantity'], 1)
                else:
                    with self.assertRaises(ValueError):
                        self.harvest()
                    self.assertEqual(self.save, before)

    def test_first_stall_gift_once_and_no_fabricated_seen_flag(self):
        self.harvest(49)
        self.assertEqual(self.save['userInfo']['player']['storageData']['-1']['ms'], [1, [], []])
        self.assertNotIn('FirstMarketStall', self.save['userInfo']['player']['seenFlags'])
        self.harvest(49)
        self.assertEqual(self.save['userInfo']['player']['storageData']['-1']['ms'][0], 1)

    def test_any_placed_or_gifted_stall_class_prevents_duplicate_gift(self):
        for where in ('placed', 'gift', 'seen'):
            with self.subTest(where=where):
                self.save = fixture()
                if where == 'placed':
                    self.save['world']['objectsArray'].append({'id': 3, 'itemName': 'otherstall', 'className': 'MarketStallBuilding'})
                elif where == 'gift':
                    self.save['userInfo']['player']['storageData'] = {'-1': {'os': [1, [], []]}}
                else:
                    self.save['userInfo']['player']['seenFlags']['FirstMarketStall'] = True
                self.harvest(49)
                self.assertNotIn('ms', self.save['userInfo']['player']['storageData'].get('-1', {}))

    def test_other_world_and_special_bushel_paths_remain_unchanged(self):
        self.save['userInfo']['currentWorldType'] = 'england'
        before = copy.deepcopy(self.save)
        self.harvest()
        self.assertEqual(self.save, before)
        self.save = fixture()
        items.get_item_by_name('berry')['bushelItemCode'] = 'ss'
        before = copy.deepcopy(self.save)
        self.harvest()
        self.assertEqual(self.save, before)

    def test_malformed_states_or_unsupported_modifiers_fail_without_partial_changes(self):
        changes = [lambda s: s['craftingState'].update(craftingItems=[{'itemCode': 'sb', 'quantity': -1}]), lambda s: s['craftingState'].update(craftingItems=[{'itemCode': 'sb', 'quantity': 1}] * 2), lambda s: s['userInfo']['player'].update(buffs={'gain': {}}), lambda s: s['world']['objectsArray'][0].update(isSuperPlot=True), lambda s: s['world']['objectsArray'][0].update(plantTime=NOW * 1000), lambda s: s['userInfo']['player'].update(storageData={'-1': {'ms': [1]}})]
        for change in changes:
            with self.subTest(change=change):
                self.save = fixture()
                change(self.save)
                self.save[bushels.COUNTERS_KEY] = {'SB': 49}
                before = copy.deepcopy(self.save)
                with self.assertRaises(ValueError):
                    self.harvest()
                self.assertEqual(self.save, before)

    def test_init_json_and_amf_preserve_numeric_and_named_properties(self):
        self.harvest(49)
        metadata = bushels.take_metadata(self.save)
        decoded = pyamf.decode(pyamf.encode(metadata, encoding=pyamf.AMF0).getvalue(), encoding=pyamf.AMF0).readElement()
        report = decoded['bushelReport']['dropTypeFuncResult']
        self.assertEqual(report['length'], 1)
        self.assertEqual(report['0']['foundBushel']['bushelCode'], 'sb')
        self.assertEqual(report['newHarvestQuantities'][0]['quantity'], 0)
        reloaded = json.loads(json.dumps(self.save))
        bushels.initialize(reloaded)
        self.assertEqual(reloaded[bushels.COUNTERS_KEY], {'SB': 0})
        self.assertNotIn(bushels.PENDING_KEY, reloaded)
if __name__ == '__main__':
    unittest.main()
