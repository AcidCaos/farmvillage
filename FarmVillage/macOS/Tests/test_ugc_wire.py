"""Deco creation and exact-instance storage through the actual AMF gateway."""
import copy
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

from pyamf import remoting

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures


class DecoWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    def prepare(self):
        from items import get_item_by_name
        import ugc
        path = self.write_fixture()
        save = self.player.session('fixture-farmer')
        data = ugc.feature_data(save)
        data['ugc_materials'] = {name: cap for name, cap in ugc._config()[0].items()}
        save['userInfo'].setdefault('featureOptions', {}).setdefault('UGCDeco', {})['UGCDeco'] = data
        item = get_item_by_name('ugc_deco_shack')
        return path, save, item

    def send(self, method, params, *, sequence=None):
        if sequence is None:
            sequence = getattr(self, '_ugc_sequence', 0) + 1
        self._ugc_sequence = max(getattr(self, '_ugc_sequence', 0), sequence)
        response = self.gateway([self.command(method, params, sequence)])
        return fixtures.gateway_results(self, response, [0])[0]['data']

    def create(self, name='QA house'):
        path, save, item = self.prepare()
        result = self.send('UGCDecoService.purchaseUGCDecoration', [{'I': item['code'], 'N': name}, 0])
        self.assertIn('ugcItemState', result)
        self.assertNotIn('data', result)
        return path, save, item, result['ugcItemState']['U']

    @staticmethod
    def house(item, instance, object_id=64000):
        return {'id': object_id, 'className': 'UGCDecoration', 'itemName': item['name'],
                'ugcItemUUID': instance, 'position': {'x': 10, 'y': 10, 'z': 0}, 'state': 'static'}

    def test_creation_place_store_replace_and_reload_keep_exact_design(self):
        path, save, item, instance = self.create()
        gifts = save['userInfo']['player']['storageData']['-1']
        self.assertEqual(gifts[item['code']], [1, [], [instance]])
        obj = self.house(item, instance)
        placed = self.send('WorldService.performAction', ['place', obj,
            [{'isGift': True, 'metadata': instance, 'giftMetadataIndex': 0}]])
        self.assertNotIn(item['code'], gifts)
        object_id = int(placed['id'])
        obj['id'] = object_id
        self.send('WorldService.performAction', ['store', obj,
            [{'resource': object_id, 'target': -2, 'storedItemName': item['name'], 'metadata': {'type': instance}}]])
        key = item['code'] + ':' + instance
        self.assertEqual(save['userInfo']['player']['storageData']['-2'][key], [1, [], [instance]])
        self.assertFalse(any(x.get('ugcItemUUID') == instance for x in save['world']['objectsArray']))
        obj['id'] = 64001
        self.send('WorldService.performAction', ['place', obj,
            [{'isInventoryWithdrawal': True, 'metadata': instance}]])
        self.assertNotIn(key, save['userInfo']['player']['storageData']['-2'])
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        reloaded = self.player.session('fixture-farmer')
        self.assertEqual(reloaded['userInfo']['ugcItemData'][instance]['N'], 'QA house')
        self.assertEqual(sum(x.get('ugcItemUUID') == instance for x in reloaded['world']['objectsArray']), 1)
        own = self.send('WorldService.loadOwnWorld', ['farm'])
        self.assertEqual(own['user']['ugcItemData'][instance]['U'], instance)
        self.assertEqual(json.loads(path.read_text())['userInfo']['ugcItemData'], own['user']['ugcItemData'])
        initialized = self.send('UserService.initUser', ['QA', 0, True, None])
        self.assertEqual(initialized['ugcItemData'][instance], reloaded['userInfo']['ugcItemData'][instance])

    def test_exact_gift_metadata_index_cannot_consume_another_design(self):
        path, save, item, first = self.create('First')
        second = self.send('UGCDecoService.purchaseUGCDecoration', [{'I': item['code'], 'N': 'Second'}, 0])['ugcItemState']['U']
        before = path.read_bytes()
        response = self.gateway([self.command('WorldService.performAction', ['place', self.house(item, second),
            [{'isGift': True, 'metadata': second, 'giftMetadataIndex': 0}]])])
        fixtures.assert_gateway_rejected(self, response)
        self.assertEqual(path.read_bytes(), before)
        self.send('WorldService.performAction', ['place', self.house(item, second),
            [{'isGift': True, 'metadata': second, 'giftMetadataIndex': 1}]])
        self.assertEqual(self.player.session('fixture-farmer')['userInfo']['player']['storageData']['-1'][item['code']], [1, [], [first]])

    def test_browser_reload_reuses_temporary_id_without_replacing_previous_house(self):
        path, save, item, first = self.create('Before reload')
        # TUGCItemPlace carries the UUID in options, not the object snapshot.
        # A fresh Flash session restarts its temporary object counter at 63000.
        obj = self.house(item, first, 63000)
        obj.pop('ugcItemUUID')
        obj['tempId'] = -1
        options = [{'isStorageWithdrawal': 0, 'isGift': True,
                    'metadata': first, 'giftMetadataIndex': 0}]
        placed = self.send('WorldService.performAction', ['place', obj, options])
        retry = self.send('WorldService.performAction', ['place', obj, options], sequence=2)
        self.assertEqual(retry['id'], placed['id'])
        self.send('UserService.initUser', ['QA', 0, True, None])
        second = self.send('UGCDecoService.purchaseUGCDecoration',
                           [{'I': item['code'], 'N': 'After reload'}, 0])['ugcItemState']['U']
        obj['position'] = {'x': 25, 'y': 25, 'z': 0}
        options[0]['metadata'] = second
        new_placed = self.send('WorldService.performAction', ['place', obj, options])
        self.assertNotEqual(new_placed['id'], placed['id'])
        houses = {o['ugcItemUUID']: o for o in save['world']['objectsArray'] if o.get('ugcItemUUID')}
        self.assertEqual(set(houses), {first, second})
        self.assertEqual(houses[first]['position'], {'x': 10, 'y': 10, 'z': 0})
        self.assertEqual(houses[second]['position'], obj['position'])
        self.assertNotIn(item['code'], save['userInfo']['player']['storageData']['-1'])
        self.assertTrue(all('tempId' not in o for o in json.loads(path.read_text())['world']['objectsArray']))

    def test_rejected_followup_preserves_material_purchase_gift_and_design(self):
        path, save, item = self.prepare()
        with redirect_stdout(io.StringIO()):
            self.player.save_session('fixture-farmer')
        before = path.read_bytes()
        response = self.gateway([
            self.command('UGCDecoService.purchaseUGCDecoration', [{'I': item['code']}, 0]),
            self.command('WorldService.performAction', ['use', {'id': 999, 'itemName': 'cow'}, []], 2),
        ])
        result = fixtures.gateway_results(self, response, [0, 29])[0]['data']
        saved = json.loads(path.read_text())
        instance = result['ugcItemState']['U']
        self.assertEqual(saved['userInfo']['ugcItemData'][instance]['U'], instance)
        self.assertEqual(saved['userInfo']['player']['storageData']['-1'][item['code']], [1, [], [instance]])
        self.assertEqual(self.player.session('fixture-farmer'), saved)

    def test_retry_creation_returns_one_pending_gift_without_second_charge(self):
        path, save, item, instance = self.create()
        before = copy.deepcopy(save['userInfo'])
        result = self.send('UGCDecoService.purchaseUGCDecoration', [{'I': item['code'], 'N': 'QA house'}, 0], sequence=1)
        self.assertEqual(result['ugcItemState']['U'], instance)
        self.assertEqual(save['userInfo'], before)

    def test_neighbor_designs_are_read_from_host_without_mutation(self):
        path, save, item, instance = self.create()
        self.write_fixture('neighbor.json', 'neighbor')
        before = path.read_bytes()
        response = self.gateway([self.command('WorldService.loadNeighborWorld', ['fixture-farmer'])], uid='neighbor')
        self.assertEqual(response.status_code, 200)
        result = remoting.decode(response.data).bodies[0][1].body['data'][0]['data']
        self.assertEqual(result['user']['ugcItemData'][instance]['I'], item['code'])
        self.assertEqual(path.read_bytes(), before)

    def test_move_and_reused_temporary_id_cannot_replace_custom_house_identity(self):
        path, save, item, instance = self.create()
        obj = self.house(item, instance)
        placed = self.send('WorldService.performAction', ['place', obj,
            [{'isGift': True, 'metadata': instance, 'giftMetadataIndex': 0}]])
        before = path.read_bytes()
        for action, object_id, field, value in (
            ('move', placed['id'], 'itemName', 'ugc_deco_mansion'),
            ('move', placed['id'], 'className', 'Building'),
            ('place', 64000, 'ugcItemUUID', '9cb367f7-075a-40e0-8720-23f17300e713'),
        ):
            changed = {**obj, 'id': object_id, field: value}
            response = self.gateway([self.command('WorldService.performAction', [action, changed, [{'isGift': True}]])])
            fixtures.assert_gateway_rejected(self, response)
            self.assertEqual(path.read_bytes(), before)

    def test_recycling_sale_returns_materials_once_and_duplicate_does_not_grant_again(self):
        path, save, item = self.prepare()
        import ugc
        data = ugc.feature_data(save)
        data['ugc_materials'] = {}
        save['userInfo']['featureOptions']['UGCDeco']['UGCDeco'] = data
        obj = {'id': 600, 'itemName': 'cottage', 'className': 'Building', 'position': {'x': 10, 'y': 10, 'z': 0}}
        save['world']['objectsArray'].append(obj)
        result = self.send('WorldService.performAction', ['sell', obj, []])
        self.assertTrue(result['ugcdeco']['ugc_materials'])
        self.assertGreater(sum(result['ugcdeco']['ugc_materials'].values()), 0)
        before = copy.deepcopy(save['userInfo'])
        again = self.send('WorldService.performAction', ['sell', obj, []], sequence=1)
        self.assertEqual(again['ugcdeco'], result['ugcdeco'])
        self.assertEqual(save['userInfo'], before)

    def test_plot_actions_cannot_bypass_custom_design_ownership(self):
        path, save, item = self.prepare()
        before = path.read_bytes()
        for action in ('plow', 'clearWithered', 'harvest'):
            obj = self.house(item, '9cb367f7-075a-40e0-8720-23f17300e713')
            response = self.gateway([self.command('WorldService.performAction', [action, obj, []])])
            fixtures.assert_gateway_rejected(self, response)
            self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
