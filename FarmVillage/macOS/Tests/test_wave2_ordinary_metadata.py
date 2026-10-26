"""Imported ordinary units keep authoritative metadata through inventory routes."""
from contextlib import redirect_stdout
import copy
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import test_cove_cellar as cellar
import creative_worlds
import items
import storage
import themed_worlds
import world_travel

NOW = cellar.NOW


class OrdinaryMetadataWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway
    save = cellar.CoveCellarTests.save
    prepare = cellar.CoveCellarTests.prepare
    persist = cellar.CoveCellarTests.persist

    def call(self, action, snapshot, options, sequence):
        packet = self.command('WorldService.performAction', [action, copy.deepcopy(snapshot), [options]], sequence)
        with mock.patch('server.timestamp_now', return_value=NOW), mock.patch(
                'commands.timestamp_now', return_value=NOW), mock.patch('engine.timestamp_now', return_value=NOW):
            response = self.gateway([packet])
        return fixtures.gateway_results(self, response, [0])[0]['data']['id']

    def source(self, world):
        self.prepare('farm' if world == 'rainforest' else world, level=100, gold=1000000000)
        if world == 'rainforest':
            creative_worlds.create(self.save, world, 'allAccess', now=NOW)
            world_travel.switch(self.save, world, now=NOW)
            names = sorted(name for name, row in themed_worlds.catalog_rules(world)['items'].items()
                           if row['type'] == 'decoration' and row['className'] in (None, 'Decoration'))
            name = next(name for name in names if items.get_item_by_name(name).get('requiredLevel', '1').isdigit())
        else:
            name = 'haybale'
        obj = {'id': 7001, 'className': 'Decoration', 'itemName': name, 'state': 'static',
               'position': {'x': 10, 'y': 10, 'z': 0},
               'metadata': {'importedVariant': world, 'opaque': {'keep': [1, 2]}}}
        self.save['world']['objectsArray'] = [
            {'id': 7000, 'className': 'StorageBuilding', 'itemName': 'toolshedpink', 'state': 'built',
             'contents': [], 'position': {'x': 4, 'y': 4, 'z': 0}}, obj]
        self.persist()
        return obj

    def test_loaded_unit_metadata_survives_store_withdraw_reload_and_world_return_in_five_worlds(self):
        for world in ('farm', 'england', 'meadows', 'fisherman', 'rainforest'):
            with self.subTest(world=world):
                obj = self.source(world)
                item = items.get_item_by_name(obj['itemName'])
                group = storage.active_inventory_id(self.save)
                self.call('store', obj, {'target': group, 'resource': obj['id'], 'storedItemName': item['name'],
                                        'metadata': {'forged': 'store-options'}}, 501)
                self.assertEqual(self.save['userInfo']['player']['storageData'][str(group)][item['code']][2], [obj['metadata']])
                snapshot = {**obj, 'id': 64022, 'metadata': {'forged': 'withdrawal'},
                            'position': {'x': 20, 'y': 20, 'z': 0}}
                ident = self.call('place', snapshot, {'isInventoryWithdrawal': True}, 502)
                with redirect_stdout(io.StringIO()):
                    self.player.load_saves()
                world_travel.switch(self.save, 'farm', now=NOW)
                world_travel.switch(self.save, world, now=NOW)
                restored = next(row for row in self.save['world']['objectsArray'] if row['id'] == ident)
                self.assertEqual(restored['metadata'], obj['metadata'])
                self.assertNotIn(item['code'], self.save['userInfo']['player']['storageData'][str(group)])

    def test_ordinary_market_to_inventory_does_not_invent_variant_metadata(self):
        self.source('farm')
        self.save['world']['objectsArray'] = self.save['world']['objectsArray'][:1]
        self.persist()
        self.call('store', {'id': -2, 'className': 'StorageBuilding'},
                  {'target': -2, 'resource': 0, 'storedItemName': 'haybale', 'currency': 'coins',
                   'metadata': {'forged': 'market-variant'}}, 601)
        self.assertEqual(self.save['userInfo']['player']['storageData']['-2']['HB'][2], [])

    def test_owned_gift_sparse_metadata_keeps_original_unit_order_in_ordinary_inventory(self):
        self.source('farm')
        self.save['userInfo']['player']['storageData']['-1']['HB'] = [3, ['original-sender'], [{'lastUnit': 'keep'}]]
        self.persist()
        for sequence, expected in ((701, []), (702, []), (703, [{'lastUnit': 'keep'}])):
            self.call('store', {'id': -2, 'className': 'StorageBuilding'},
                      {'target': -2, 'storedItemName': 'haybale', 'isGift': True,
                       'metadata': {'forged': 'gift-variant'}}, sequence)
            self.assertEqual(self.save['userInfo']['player']['storageData']['-2']['HB'][2], expected)
        self.assertNotIn('HB', self.save['userInfo']['player']['storageData']['-1'])


if __name__ == '__main__':
    unittest.main()
