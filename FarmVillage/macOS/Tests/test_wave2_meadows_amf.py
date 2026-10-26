"""Original paid-storage AMF0 envelopes, never client price authority."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_wave2_meadows_storage as fixtures
import pyamf
import meadows_storage
import storage


class StorageOptionsTests(unittest.TestCase):
    def test_actual_mixed_array_and_strict_array_options(self):
        for value in ({}, [], [{}], [{'firstWA': True}],
                      pyamf.MixedArray(), pyamf.MixedArray({0: {}}),
                      pyamf.MixedArray({0: {'firstWA': True}}),
                      pyamf.MixedArray({0: {}, 1: {'firstWA': True}}),
                      pyamf.MixedArray({'0': {}})):
            with self.subTest(value=value):
                self.assertIn(storage.world_action_options(value), ({}, {'firstWA': True}))
        flags = {'isStorageWithdrawal': -16, 'metadata': {'keep': 1}}
        self.assertEqual(storage.world_action_options(pyamf.MixedArray({0: flags})), flags)

    def test_malformed_gap_alias_extra_and_nonobject_arguments_refuse(self):
        for value in (None, 'bad', [1], [{}, {}], [{}, {'firstWA': 1}],
                      [{}, {'firstWA': False}], [{}, {'price': 0}], [{}, {}, {}],
                      pyamf.MixedArray({1: {}}), pyamf.MixedArray({0: {}, 2: {}}),
                      pyamf.MixedArray({0: {}, '0': {}}),
                      pyamf.MixedArray({False: {}}), pyamf.MixedArray({0.0: {}}),
                      pyamf.MixedArray({'00': {}}), pyamf.MixedArray({0: {}, 'price': 0}),
                      pyamf.MixedArray({0: [], 1: {'firstWA': True}})):
            with self.subTest(value=value), self.assertRaises(ValueError):
                storage.world_action_options(value)


class MeadowsAMFUpgradeTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.MeadowsStorageTests.setUpClass.__func__)
    setUp = fixtures.MeadowsStorageTests.setUp
    fixture = fixtures.MeadowsStorageTests.fixture
    write_fixture = fixtures.MeadowsStorageTests.write_fixture
    command = staticmethod(fixtures.MeadowsStorageTests.command)
    gateway_payload = fixtures.MeadowsStorageTests.gateway_payload
    gateway = fixtures.MeadowsStorageTests.gateway
    save = fixtures.MeadowsStorageTests.save
    prepare = fixtures.MeadowsStorageTests.prepare
    persist = fixtures.MeadowsStorageTests.persist
    fixture_meadows = fixtures.MeadowsStorageTests.fixture_meadows
    shed = staticmethod(fixtures.MeadowsStorageTests.shed)

    def upgrade(self, params, sequence=1):
        entry = self.command('WorldService.performAction',
                             ['purchaseStorageUpgrade', self.shed(), params], sequence)
        return self.gateway([entry])

    def test_real_encoded_mixed_array_upgrade_retry_reload_and_capacity(self):
        self.fixture_meadows()
        self.save['world']['objectsArray'] = [self.shed()]
        self.persist()
        params = pyamf.MixedArray({0: pyamf.ASObject()})
        payload = self.gateway_payload([self.command('WorldService.performAction',
            ['purchaseStorageUpgrade', self.shed(), params])])
        from pyamf import remoting
        decoded = remoting.decode(payload).bodies[0][1].body[1][0]['params'][2]
        self.assertIsInstance(decoded, pyamf.MixedArray)
        self.assertEqual(decoded, {0: {}})
        fixtures.fixtures.assert_gateway_status(self, self.upgrade(params), 200)
        self.assertEqual(self.save['userInfo']['player']['cash'], 490)
        self.assertEqual(self.save['world']['objectsArray'][0]['itemName'], 'toolshedpink2')
        before = copy.deepcopy(self.save)
        fixtures.fixtures.assert_gateway_status(self, self.upgrade(params), 200)
        self.assertEqual(self.save, before)
        self.player.load_saves()
        self.assertEqual(self.save['world']['objectsArray'][0]['itemName'], 'toolshedpink2')
        storage._guard_inventory_deposit(self.save, -16, 20)
        with self.assertRaises(ValueError):
            storage._guard_inventory_deposit(self.save, -16, 21)

    def test_empty_and_first_world_action_mixed_shapes_charge_original_ten(self):
        for params in (pyamf.MixedArray(), pyamf.MixedArray({0: {}}),
                       pyamf.MixedArray({0: {'firstWA': True}}),
                       pyamf.MixedArray({0: {}, 1: {'firstWA': True}})):
            with self.subTest(params=params):
                self.fixture_meadows()
                self.save['world']['objectsArray'] = [self.shed()]
                self.persist()
                fixtures.fixtures.assert_gateway_status(self, self.upgrade(params), 200)
                self.assertEqual(self.save['userInfo']['player']['cash'], 490)

    def test_mixed_client_prices_materials_levels_gaps_and_trailers_are_atomic(self):
        for params in (pyamf.MixedArray({0: {'price': 0}}),
                       pyamf.MixedArray({0: {'level': 3}}),
                       pyamf.MixedArray({0: {'materials': []}}),
                       pyamf.MixedArray({0: {'firstWA': 1}}),
                       pyamf.MixedArray({1: {}}), pyamf.MixedArray({0: {}, 2: {}}),
                       pyamf.MixedArray({0: {}, 'price': 0}),
                       pyamf.MixedArray({0: {}, 1: {'cash': 0}}),
                       pyamf.MixedArray({0: {}, 1: {'firstWA': 1}})):
            with self.subTest(params=params):
                self.fixture_meadows()
                self.save['world']['objectsArray'] = [self.shed()]
                self.persist()
                before, disk = copy.deepcopy(self.save), self.path.read_bytes()
                with self.assertRaises(ValueError):
                    meadows_storage.purchase_storage_upgrade(self.save, self.shed(), params, request_id=1)
                fixtures.fixtures.assert_gateway_status(self, self.upgrade(params), 400)
                self.assertEqual(self.save, before)
                self.assertEqual(self.path.read_bytes(), disk)
    def test_actual_nested_shipping_and_inventory_placement_keep_existing_guards(self):
        self.fixture_meadows()
        self.save['world']['objectsArray'] = [self.shed()]
        self.save['userInfo']['unlockedWorldContentLicenses'] = {
            'farm': {'world': True}, 'meadows': {'world': True}}
        self.save['userInfo']['player']['storageData']['-2'] = {'HB': [2, [], []]}
        self.persist()
        transfer = pyamf.MixedArray({0: {'storedItemName': 'haybale', 'origin': -2,
                                        'target': -16, 'resource': 0, 'numToStore': 1}})
        entry = self.command('WorldService.performAction',
            ['store', {'id': -16, 'className': 'StorageBuilding'}, transfer], 11)
        fixtures.fixtures.assert_gateway_status(self, self.gateway([entry]), 200)
        self.assertEqual(self.save['userInfo']['player']['storageData']['-16']['HB'][0], 1)
        before_gold = self.save['userInfo']['player']['gold']
        snapshot = {'id': 63001, 'itemName': 'haybale', 'className': 'Decoration',
                    'state': 'static', 'position': {'x': 12, 'y': 12, 'z': 0}}
        flags = pyamf.MixedArray({0: {'isStorageWithdrawal': -16,
                                     'isInventoryWithdrawal': True}})
        entry = self.command('WorldService.performAction', ['place', snapshot, flags], 12)
        fixtures.fixtures.assert_gateway_status(self, self.gateway([entry]), 200)
        self.assertEqual(self.save['userInfo']['player']['gold'], before_gold)
        self.assertNotIn('HB', self.save['userInfo']['player']['storageData']['-16'])
        self.assertTrue(any(obj['itemName'] == 'haybale' for obj in self.save['world']['objectsArray']))
        self.save['userInfo']['unlockedWorldContentLicenses'] = {}
        self.persist()
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        entry = self.command('WorldService.performAction',
            ['store', {'id': -16, 'className': 'StorageBuilding'}, transfer], 13)
        fixtures.fixtures.assert_gateway_status(self, self.gateway([entry]), 400)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)


if __name__ == '__main__':
    unittest.main()
