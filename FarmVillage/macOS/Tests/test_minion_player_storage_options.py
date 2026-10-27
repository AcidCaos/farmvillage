"""AMF null and undefined option values for gift placement and storage stores, on in-memory farms."""
import io
import json
from pathlib import Path
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

import pyamf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence  # noqa: F401,E402  Loads first so FARMVILLAGE_DATA_DIR is set before product modules resolve paths.
import items  # noqa: E402
import storage  # noqa: E402

UNDEFINED = pyamf.Undefined
CATALOG = [
    {'name': 'cow', 'code': 'CW', 'type': 'animal', 'className': 'Animal', 'growTime': '1', 'coinYield': '6'},
    {'name': 'bundle_test', 'code': 'BT', 'type': 'consumable', 'rewards': {'reward': [{'type': 'coins', 'value': '5'}]}},
]


def _farm(inventory=0, gifts=0):
    save = {'userInfo': {'player': {'storageData': {}, 'gold': 0}},
            'world': {'objectsArray': [{'id': 600, 'className': 'StorageBuilding', 'itemName': 'xma_villagegranary',
                                        'contents': [], 'position': {'x': 3, 'y': 3}}]}}
    with redirect_stdout(io.StringIO()):
        if inventory:
            storage.store_deposit_item_by_name(save, 'cow', inventory, storage.HOME_INVENTORY_ID)
        if gifts:
            storage.store_deposit_item_by_name(save, 'cow', gifts, storage.GIFTBOX_ID)
    return save


class StorageOptionTests(unittest.TestCase):
    def setUp(self):
        catalog = mock.patch.object(items, '_cached_items', {'settings': {'items': {'item': CATALOG}}})
        catalog.start()
        self.addCleanup(catalog.stop)

    def test_gift_placement_with_null_or_undefined_index_consumes_the_gift(self):
        for index in (None, UNDEFINED):
            with self.subTest(index=repr(index)):
                save = _farm(gifts=1)
                with redirect_stdout(io.StringIO()):
                    self.assertTrue(storage.withdraw_for_placement(save, 'cow', [{'isGift': True, 'giftMetadataIndex': index}]))
                self.assertNotIn('CW', save['userInfo']['player']['storageData'].get('-1', {}))

    def test_undefined_gift_flag_does_not_divert_inventory_placement_to_gift_box(self):
        save = _farm(inventory=1)
        with redirect_stdout(io.StringIO()):
            self.assertTrue(storage.withdraw_for_placement(save, 'cow', [{'isGift': UNDEFINED, 'isInventoryWithdrawal': True}]))
        self.assertNotIn('CW', save['userInfo']['player']['storageData']['-2'])

    def test_null_or_undefined_storage_withdrawal_id_is_treated_as_absent(self):
        for value in (None, UNDEFINED):
            with self.subTest(value=repr(value)):
                save = _farm(inventory=1)
                with redirect_stdout(io.StringIO()):
                    self.assertTrue(storage.withdraw_for_placement(save, 'cow', [{'isStorageWithdrawal': value, 'isInventoryWithdrawal': True}]))
                self.assertNotIn('CW', save['userInfo']['player']['storageData']['-2'])

    def test_store_ignores_null_count_and_undefined_metadata_and_stays_serializable(self):
        save = _farm(inventory=2)
        building = {'id': 600, 'className': 'StorageBuilding', 'itemName': 'xma_villagegranary', 'contents': []}
        options = {'target': 600, 'cameFromLocation': -2, 'storedItemName': 'cow',
                   'numToStore': None, 'metadata': UNDEFINED}
        with redirect_stdout(io.StringIO()):
            storage.store_world_item(save, building, options)
        storage_data = save['userInfo']['player']['storageData']
        self.assertEqual(storage_data['600']['CW'], [1, [], []])
        self.assertEqual(storage_data['-2']['CW'][0], 1)
        json.dumps(save)

    def test_consuming_from_building_storage_keeps_building_contents_in_step(self):
        save = _farm()
        with redirect_stdout(io.StringIO()):
            storage.store_deposit_item_by_name(save, 'bundle_test', 1, storage.HOME_INVENTORY_ID)
            storage.store_world_item(save, {'id': 600, 'className': 'StorageBuilding', 'itemName': 'xma_villagegranary', 'contents': []},
                                     {'target': 600, 'cameFromLocation': storage.HOME_INVENTORY_ID, 'storedItemName': 'bundle_test'})
            storage.consume_by_name(save, 'bundle_test', 1, 600)
        building = next(obj for obj in save['world']['objectsArray'] if obj['id'] == 600)
        self.assertEqual(building['contents'], [])
        self.assertNotIn('BT', save['userInfo']['player']['storageData'].get('600', {}))
        self.assertEqual(save['userInfo']['player']['gold'], 5)


if __name__ == '__main__':
    unittest.main()
