"""Classic England container metadata and imported recovery, synthetic only."""
from contextlib import redirect_stdout
import copy
import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import items
import storage


class ClassicContainerMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if items._cached_items is None:
            with redirect_stdout(io.StringIO()):
                items.load_items()

    def setUp(self):
        self.save = {'world': {'objectsArray': []}, 'userInfo': {'currentWorldType': 'england',
            'worldSummaryData': {'england': {'storageId': -8}},
            'player': {'gold': 2000000, 'cash': 1000, 'xp': 100015,
                       'storageData': {'-1': {}, '-8': {}}}}}

    @property
    def data(self):
        return self.save['userInfo']['player']['storageData']

    def owner(self, name='xukhorsestable_finished'):
        item = items.get_item_by_name(name)
        obj = {'id': 600, 'itemName': name, 'className': item['className'],
            'state': 'ripe', 'isFullyBuilt': True,
            'expansionLevel': int(item.get('storageSize', 1)), 'contents': [],
            'plantTime': 123456789, 'lastBonusTime': 987654321,
            'storageMetadata': {'imported': ['retain']}, 'opaque': {'keep': [1, 2]}}
        self.save['world']['objectsArray'] = [obj]
        return obj, item

    def call(self, owner, name, **options):
        with redirect_stdout(io.StringIO()):
            storage.store_world_item(self.save, copy.deepcopy(owner),
                {'storedItemName': name, 'isGift': True, **options})

    def test_indexed_gift_keeps_exact_unit_names_clock_and_owner_metadata(self):
        owner, _ = self.owner()
        horse = items.get_item_by_name('horse')
        selected = {'name': 'Imported Hazel', 'clock': 123456, 'nested': {'keep': [2]}}
        other = {'name': 'Other unit', 'clock': 999999}
        self.data['-1'][horse['code']] = [2, ['sender1', 'sender2'], [other, selected]]
        before = copy.deepcopy(owner)
        self.call(owner, horse['name'], giftMetadataIndex=1, metadata={'forged': True})
        owner = self.save['world']['objectsArray'][0]
        self.assertEqual(self.data['600'][horse['code']][2], [selected])
        self.assertEqual(self.data['-1'][horse['code']][2], [other])
        for field in ('plantTime', 'lastBonusTime', 'storageMetadata', 'opaque'):
            self.assertEqual(owner[field], before[field])
        snapshot = {'metadata': {'forged': True}}
        with redirect_stdout(io.StringIO()):
            self.assertTrue(storage.withdraw_for_placement(self.save, horse['name'],
                            [{'isStorageWithdrawal': 600}], snapshot))
        self.assertEqual(snapshot['metadata'], selected)
        self.assertNotIn(horse['code'], self.data['600'])
        self.assertEqual(owner['contents'], [])

    def test_sparse_and_empty_source_metadata_cannot_be_forged_on_container_deposit(self):
        for source_count, metadata in ((10, [{'name': 'Sparse retained'}]), (1, [])):
            with self.subTest(quantity=source_count):
                owner, _ = self.owner()
                horse = items.get_item_by_name('horse')
                self.data['600'] = {}
                self.data['-1'][horse['code']] = [source_count, [], copy.deepcopy(metadata)]
                self.call(owner, horse['name'], metadata={'forged': True})
                self.assertEqual(self.data['600'][horse['code']][2], [])
                if source_count > 1:
                    self.assertEqual(self.data['-1'][horse['code']][2], metadata)

    def test_full_cap_refusal_preserves_source_and_imported_overflow_remains_withdrawable(self):
        owner, catalog = self.owner()
        horse = items.get_item_by_name('horse')
        count = storage._container_capacity(owner, catalog)
        owner['contents'] = [{'itemCode': horse['code'], 'numItem': count, 'opaque': [5]}]
        self.data['600'] = {horse['code']: [count, [], []]}
        self.data['-1'][horse['code']] = [1, [], [{'name': 'Gift untouched'}]]
        before = copy.deepcopy(self.save)
        with self.assertRaises(ValueError):
            self.call(owner, horse['name'])
        self.assertEqual(self.save, before)
        owner['contents'][0]['numItem'] += 1
        self.data['600'][horse['code']] = [count + 1, [], [{'name': 'Sparse imported survivor'}]]
        snapshot = {}
        with redirect_stdout(io.StringIO()):
            storage.withdraw_for_placement(self.save, horse['name'], [{'isStorageWithdrawal': 600}], snapshot)
        self.assertEqual(self.data['600'][horse['code']][0], count)
        self.assertEqual(self.data['600'][horse['code']][2], [{'name': 'Sparse imported survivor'}])
        self.assertEqual(owner['contents'][0]['opaque'], [5])
        self.assertEqual((owner['plantTime'], owner['lastBonusTime']), (123456789, 987654321))

    def test_no_authoritative_withdrawal_metadata_discards_forged_snapshot_metadata(self):
        owner, _ = self.owner()
        horse = items.get_item_by_name('horse')
        owner['contents'] = [{'itemCode': horse['code'], 'numItem': 1}]
        self.data['600'] = {horse['code']: [1, [], []]}
        snapshot = {'metadata': {'name': 'Forged unit', 'clock': 1}}
        with redirect_stdout(io.StringIO()):
            storage.withdraw_for_placement(self.save, horse['name'], [{'isStorageWithdrawal': 600}], snapshot)
        self.assertNotIn('metadata', snapshot)

    def test_inventory_and_world_sources_copy_authoritative_unit_metadata_only(self):
        for source in ('inventory', 'world'):
            with self.subTest(source=source):
                self.setUp()
                owner, _ = self.owner()
                horse = items.get_item_by_name('horse')
                metadata = {'name': 'Owned Hazel', 'clock': 567890, 'nested': ['keep']}
                if source == 'inventory':
                    self.data['-8'][horse['code']] = [2, ['sender'], [metadata, {'other': True}]]
                    options = {'isGift': False, 'origin': -8}
                else:
                    self.save['world']['objectsArray'].append({'id': 700, 'itemName': horse['name'],
                        'className': 'Animal', 'metadata': copy.deepcopy(metadata), 'plantTime': 345678})
                    options = {'isGift': False, 'resource': 700}
                self.call(owner, horse['name'], metadata={'forged': True}, **options)
                self.assertEqual(self.data['600'][horse['code']][2], [metadata])
                current = self.save['world']['objectsArray'][0]
                self.assertEqual((current['plantTime'], current['lastBonusTime']), (123456789, 987654321))
                if source == 'inventory':
                    self.assertEqual(self.data['-8'][horse['code']], [1, [], [{'other': True}]])
                else:
                    self.assertEqual(len(self.save['world']['objectsArray']), 1)


if __name__ == '__main__':
    unittest.main()
