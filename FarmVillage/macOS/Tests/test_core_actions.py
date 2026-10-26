"""Actual catalog and AMF regressions for ordinary farm editing."""
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
import engine
import items


class CoreActionTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    def action(self, action, obj, params=(), sequence=1):
        return self.command('WorldService.performAction', [action, copy.deepcopy(obj), list(params)], sequence)

    def test_empty_farm_can_plow_first_plot_and_save_permanent_id(self):
        path = self.write_fixture()
        self.player.session('fixture-farmer')['world']['objectsArray'] = []
        import constants
        plot = {'id': constants.TEMP_ID_START, 'className': 'Plot', 'state': 'plowed', 'itemName': None,
                'position': {'x': 0, 'y': 0, 'z': 0}, 'plantTime': 0}
        response = self.gateway([self.action('plow', plot)])
        self.assertEqual(response.status_code, 200)
        saved = json.loads(path.read_text())
        self.assertEqual(saved['world']['objectsArray'][0]['id'], 1)
        self.assertNotIn('tempId', saved['world']['objectsArray'][0])

    def test_unhandled_world_action_is_logged_and_changes_nothing(self):
        import bundle
        path = self.write_fixture()
        save = self.player.session('fixture-farmer')
        plot = next(obj for obj in save['world']['objectsArray'] if obj.get('className') == 'Plot')
        before = json.loads(path.read_text())
        log = Path(bundle.UNHANDLED_LOG)
        start = log.read_text() if log.exists() else ''
        # 'paint' is now an explicit rejection, so the unknown-name fall-through needs a name no branch knows.
        response = self.gateway([self.action('notARealAction', plot)])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(path.read_text())['world'], before['world'])
        self.assertEqual(json.loads(path.read_text())['userInfo']['player']['gold'],
                         before['userInfo']['player']['gold'])
        added = [json.loads(line) for line in log.read_text()[len(start):].splitlines() if line]
        self.assertEqual([row['functionName'] for row in added],
                         ['WorldService.performAction/notARealAction'])
        self.assertEqual(added[0]['params']['id'], plot['id'])
        # Handled actions are not logged.
        mark = log.read_text()
        self.gateway([self.action('move', plot, sequence=2)])
        self.assertEqual(log.read_text(), mark)

    def test_unrestored_redeem_and_instant_actions_reject_without_save_change(self):
        import bundle
        import commands
        path = self.write_fixture()
        save = self.player.session('fixture-farmer')
        plot = next(obj for obj in save['world']['objectsArray'] if obj.get('className') == 'Plot')
        building = {'id': 1001, 'className': 'FeatureBuilding', 'itemName': 'animal_breeding_horsepaddock_finished',
                    'state': 'built', 'position': {'x': 0, 'y': 0, 'z': 0}}
        save['world']['objectsArray'].append(building)
        self.player.save_session('fixture-farmer')
        original = path.read_bytes()
        gold = json.loads(original)['userInfo']['player']['gold']
        log = Path(bundle.UNHANDLED_LOG)
        start = log.read_text() if log.exists() else ''
        cases = (
            ('redeemNeighborFertilize', plot, [{'neighborId': '2'}]),
            ('redeemNeighborUnwither', plot, [{'neighborId': '2'}]),
            ('CompleteNow', building, [{'partName': None, 'isGift': False, 'currency': 'cash'}]),
            ('HarvestReadyNow', building, []),
        )
        for name, obj, params in cases:
            with self.subTest(action=name):
                # Two sequences: a client retry must fail the same way and change nothing.
                response = self.gateway([self.action(name, obj, params),
                                         self.action(name, obj, params, sequence=2)])
                fixtures.assert_gateway_rejected(self, response)
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(json.loads(path.read_text())['userInfo']['player']['gold'], gold)
                self.assertIn(name, commands.HANDLED_WORLD_ACTIONS)
        # Rejections raise before the unhandled-action log, so they are not reported as silent.
        self.assertEqual(log.read_text() if log.exists() else '', start)

    def test_plot_removal_persists_and_retry_does_not_charge_twice(self):
        path = self.write_fixture()
        save = self.player.session('fixture-farmer')
        plot = next(obj for obj in save['world']['objectsArray'] if obj.get('className') == 'Plot')
        before = save['userInfo']['player']['gold']
        response = self.gateway([self.action('clear', plot), self.action('clear', plot, sequence=2)])
        self.assertEqual(response.status_code, 200)
        saved = json.loads(path.read_text())
        self.assertNotIn(plot['id'], [obj['id'] for obj in saved['world']['objectsArray']])
        self.assertEqual(saved['userInfo']['player']['gold'], before - 15)

    def test_sale_persists_once_and_uses_original_sell_price(self):
        path = self.write_fixture()
        save = self.player.session('fixture-farmer')
        obj = {'id': 999, 'className': 'Decoration', 'itemName': 'haybale', 'state': 'static',
               'position': {'x': 0, 'y': 0, 'z': 0}}
        save['world']['objectsArray'].append(obj)
        before = save['userInfo']['player']['gold']
        value = engine.item_sell_price(items.get_item_by_name('haybale'))
        response = self.gateway([self.action('sell', obj), self.action('sell', obj, sequence=2)])
        self.assertEqual(response.status_code, 200)
        saved = json.loads(path.read_text())
        self.assertEqual(saved['userInfo']['player']['gold'], before + value)
        self.assertNotIn(999, [entry['id'] for entry in saved['world']['objectsArray']])

    def test_move_preserves_imported_server_owned_fields(self):
        self.write_fixture()
        save = self.player.session('fixture-farmer')
        obj = save['world']['objectsArray'][0]
        obj['unknownServerField'] = {'future': [1, 2, 3]}
        incoming = {key: copy.deepcopy(value) for key, value in obj.items() if key != 'unknownServerField'}
        incoming['position'] = {'x': 20, 'y': 20, 'z': 0}
        self.assertEqual(self.gateway([self.action('move', incoming)]).status_code, 200)
        self.assertEqual(save['world']['objectsArray'][0]['unknownServerField'], {'future': [1, 2, 3]})

    def test_failed_purchase_restores_every_field_and_original_save_bytes(self):
        path = self.write_fixture()
        save = self.player.session('fixture-farmer')
        save['userInfo']['player']['gold'] = 0
        self.player.save_session('fixture-farmer')
        original = path.read_bytes()
        incoming = {'id': 1000, 'className': 'Decoration', 'itemName': 'haybale', 'state': 'static',
                    'position': {'x': 0, 'y': 0, 'z': 0}}
        response = self.gateway([self.action('place', incoming)])
        fixtures.assert_gateway_rejected(self, response)
        self.assertEqual(path.read_bytes(), original)
        self.assertNotIn(1000, [entry['id'] for entry in self.player.session('fixture-farmer')['world']['objectsArray']])

    def test_harvest_retry_cannot_double_coin_reward(self):
        path = self.write_fixture()
        save = self.player.session('fixture-farmer')
        plot = next(obj for obj in save['world']['objectsArray'] if obj.get('className') == 'Plot')
        plot.update(itemName='strawberry', state='grown', plantTime=1)
        before = save['userInfo']['player']['gold']
        incoming = dict(plot, state='fallow')
        response = self.gateway([self.action('harvest', incoming), self.action('harvest', incoming, sequence=2)])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(path.read_text())['userInfo']['player']['gold'],
                         before + int(items.get_item_by_name('strawberry')['coinYield']))

    def test_animal_and_tree_harvests_restart_real_timer_and_cannot_double_pay(self):
        self.write_fixture()
        save = self.player.session('fixture-farmer')
        for index, (name, cls) in enumerate((('cow', 'Animal'), ('apple', 'Tree')), 1000):
            obj = {'id': index, 'className': cls, 'itemName': name, 'state': 'grown', 'plantTime': 1,
                   'position': {'x': 0, 'y': 0, 'z': 0}}
            save['world']['objectsArray'].append(obj)
            before = save['userInfo']['player']['gold']
            response = self.gateway([self.action('harvest', obj), self.action('harvest', obj, sequence=2)])
            self.assertEqual(response.status_code, 200)
            stored = next(entry for entry in save['world']['objectsArray'] if entry['id'] == index)
            self.assertEqual(stored['state'], 'bare')
            self.assertGreater(stored['plantTime'], 1_000_000)
            reward = int(items.get_item_by_name(name)['coinYield'])
            self.assertEqual(save['userInfo']['player']['gold'], before + reward)

    def test_plow_retry_does_not_charge_or_award_xp_twice(self):
        self.write_fixture()
        save = self.player.session('fixture-farmer')
        obj = next(entry for entry in save['world']['objectsArray'] if entry.get('className') == 'Plot')
        obj['state'] = 'fallow'
        planted = dict(obj, state='plowed')
        before = save['userInfo']['player']['gold']
        self.assertEqual(self.gateway([self.action('plow', planted), self.action('plow', planted, sequence=2)]).status_code, 200)
        self.assertEqual(save['userInfo']['player']['gold'], before - 15)

    def dict_action(self, action, obj, payload, sequence=1):
        # Some client transactions send an Object, not an Array, as the third performAction argument.
        return self.command('WorldService.performAction', [action, copy.deepcopy(obj), dict(payload)], sequence)

    def graphic_object(self, save, graphic='lights', object_id=999):
        obj = {'id': object_id, 'className': 'Decoration', 'itemName': 'haybale', 'state': 'static',
               'position': {'x': 0, 'y': 0, 'z': 0}, 'altGraphic': graphic}
        save['world']['objectsArray'].append(obj)
        self.player.save_session('fixture-farmer')
        return obj

    @staticmethod
    def saved_object(path, object_id):
        return next(obj for obj in json.loads(path.read_text())['world']['objectsArray'] if obj['id'] == object_id)

    def test_remove_alt_graphic_clears_only_the_named_graphic_and_survives_reload(self):
        path = self.write_fixture()
        save = self.player.session('fixture-farmer')
        obj = self.graphic_object(save)
        gold = save['userInfo']['player']['gold']
        # The snapshot carries forged fields that no removal may persist.
        removed = dict(obj, altGraphic='', paintColor='red', featuredItems={'1': {'itemCode': 'forged'}})
        response = self.gateway([self.dict_action('RemoveAltGraphic', removed, {'name': 'lights'}),
                                 self.dict_action('RemoveAltGraphic', removed, {'name': 'lights'}, sequence=2)])
        self.assertEqual(response.status_code, 200)
        stored = self.saved_object(path, 999)
        self.assertEqual(stored['altGraphic'], '')
        self.assertNotIn('paintColor', stored)
        self.assertNotIn('featuredItems', stored)
        self.assertEqual(json.loads(path.read_text())['userInfo']['player']['gold'], gold)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        reloaded = next(o for o in self.player.session('fixture-farmer')['world']['objectsArray'] if o['id'] == 999)
        self.assertEqual(reloaded['altGraphic'], '')

    def test_remove_alt_graphic_leaves_other_graphics_untouched(self):
        path = self.write_fixture()
        save = self.player.session('fixture-farmer')
        obj = self.graphic_object(save, graphic='lights')
        # 'snow_altgraphic' is the mapped name for 'snow', so a different name must not clear 'lights'.
        response = self.gateway([self.dict_action('RemoveAltGraphic', obj, {'name': 'snow_altgraphic'})])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.saved_object(path, 999)['altGraphic'], 'lights')

    def test_remove_alt_graphic_rejects_malformed_payloads_without_save_change(self):
        path = self.write_fixture()
        save = self.player.session('fixture-farmer')
        obj = self.graphic_object(save)
        original = path.read_bytes()
        for payload in ({}, {'name': 7}, {'name': ''}, {'name': 'x' * 65}):
            with self.subTest(payload=payload):
                response = self.gateway([self.dict_action('RemoveAltGraphic', obj, payload)])
                fixtures.assert_gateway_rejected(self, response)
                self.assertEqual(path.read_bytes(), original)

    def test_remove_alt_graphic_on_a_non_owned_object_creates_nothing(self):
        path = self.write_fixture()
        before = json.loads(path.read_text())
        ghost = {'id': 4242, 'className': 'Decoration', 'itemName': 'haybale', 'state': 'static',
                 'position': {'x': 0, 'y': 0, 'z': 0}, 'altGraphic': 'lights'}
        response = self.gateway([self.dict_action('RemoveAltGraphic', ghost, {'name': 'lights'})])
        self.assertEqual(response.status_code, 200)
        after = json.loads(path.read_text())
        self.assertEqual(after['world'], before['world'])
        self.assertEqual(after['userInfo']['player']['gold'], before['userInfo']['player']['gold'])

    def test_sale_of_graphic_decorated_object_still_succeeds_after_graphic_removal(self):
        path = self.write_fixture()
        save = self.player.session('fixture-farmer')
        obj = self.graphic_object(save)
        before = save['userInfo']['player']['gold']
        value = engine.item_sell_price(items.get_item_by_name('haybale'))
        removed = dict(obj, altGraphic='')
        response = self.gateway([self.dict_action('RemoveAltGraphic', removed, {'name': 'lights'}),
                                 self.action('sell', removed, sequence=2)])
        self.assertEqual(response.status_code, 200)
        saved = json.loads(path.read_text())
        self.assertNotIn(999, [entry['id'] for entry in saved['world']['objectsArray']])
        self.assertEqual(saved['userInfo']['player']['gold'], before + value)

    def test_every_client_action_without_a_faithful_server_model_fails_visibly(self):
        import bundle
        import commands
        path = self.write_fixture()
        save = self.player.session('fixture-farmer')
        plot = next(obj for obj in save['world']['objectsArray'] if obj.get('className') == 'Plot')
        original = path.read_bytes()
        gold = json.loads(original)['userInfo']['player']['gold']
        rejected = (
            'redeemNeighborFertilize', 'redeemNeighborUnwither', 'HarvestReadyNow', 'CompleteNow',
            'makeSlop', 'transform', 'wither', 'upgradeBuilding', 'ExpandWithCurrency',
            'upgradeStorage', 'purchaseStorageUpgrade', 'cancelStorageUpgrade', 'paint', 'deprecate',
            'SetAltGraphic', 'SetOverlay', 'setOverlayOverride', 'SetFestivalOfColorGraphic',
            'UnlockFestivalOfColorGraphic', 'setMultipleFeaturedItems',
            'huntTruffle', 'createFriendRewardForPassing',
        )
        log = Path(bundle.UNHANDLED_LOG)
        start = log.read_text() if log.exists() else ''
        for name in rejected:
            with self.subTest(action=name):
                # Two sequences: a client retry must fail the same way and change nothing.
                response = self.gateway([self.dict_action(name, plot, {'name': 'x'}),
                                         self.dict_action(name, plot, {'name': 'x'}, sequence=2)])
                fixtures.assert_gateway_rejected(self, response)
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(json.loads(path.read_text())['userInfo']['player']['gold'], gold)
                self.assertIn(name, commands.UNRESTORED_WORLD_ACTIONS)
                self.assertIn(name, commands.HANDLED_WORLD_ACTIONS)
        for name in ('RemoveAltGraphic', 'setFeaturedItem'):
            self.assertNotIn(name, commands.UNRESTORED_WORLD_ACTIONS)
            self.assertIn(name, commands.HANDLED_WORLD_ACTIONS)
        self.assertEqual(log.read_text() if log.exists() else '', start)

    def featured_building(self, save, object_id=998):
        obj = {'id': object_id, 'className': 'FeatureBuilding', 'itemName': 'alaskanmalamutedoghouse',
               'state': 'built', 'position': {'x': 0, 'y': 0, 'z': 0}}
        save['world']['objectsArray'].append(obj)
        self.player.save_session('fixture-farmer')
        return obj

    def test_set_featured_item_persists_one_slot_sets_bare_and_survives_reload(self):
        path = self.write_fixture()
        save = self.player.session('fixture-farmer')
        obj = self.featured_building(save)
        code = items.get_item_by_name('haybale')['code']
        # The snapshot carries a forged featured entry in another slot; only the transaction's slot may change.
        snapshot = dict(obj, featuredItems={'1': {'itemCode': 'forged', 'metaHash': 'x'}})
        add = {'itemSlot': 0.0, 'itemCode': code, 'metaHash': '', 'removeOrAdd': True}
        response = self.gateway([self.dict_action('setFeaturedItem', snapshot, add),
                                 self.dict_action('setFeaturedItem', snapshot, add, sequence=2)])
        self.assertEqual(response.status_code, 200)
        expected = {'0': {'itemCode': code, 'metaHash': ''}}
        stored = self.saved_object(path, 998)
        self.assertEqual(stored['featuredItems'], expected)
        self.assertEqual(stored['state'], 'bare')
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        reloaded = next(o for o in self.player.session('fixture-farmer')['world']['objectsArray'] if o['id'] == 998)
        self.assertEqual(reloaded['featuredItems'], expected)
        self.assertEqual(reloaded['state'], 'bare')
        # Clearing the slot is idempotent too.
        clear = dict(add, removeOrAdd=False)
        response = self.gateway([self.dict_action('setFeaturedItem', dict(reloaded, state='bare'), clear),
                                 self.dict_action('setFeaturedItem', dict(reloaded, state='bare'), clear, sequence=2)])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.saved_object(path, 998)['featuredItems'], {})

    def test_set_featured_item_rejects_forged_payloads_and_non_owned_objects_without_save_change(self):
        path = self.write_fixture()
        save = self.player.session('fixture-farmer')
        obj = self.featured_building(save)
        original = path.read_bytes()
        code = items.get_item_by_name('haybale')['code']
        good = {'itemSlot': 0, 'itemCode': code, 'metaHash': '', 'removeOrAdd': True}
        payloads = (
            dict(good, itemCode='notARealItem'), dict(good, itemCode=''), dict(good, itemSlot=-1),
            dict(good, itemSlot=1.5), dict(good, itemSlot=100), dict(good, itemSlot='0'),
            dict(good, removeOrAdd='yes'), dict(good, metaHash=7), dict(good, metaHash='x' * 129),
            {'itemSlot': 0, 'itemCode': code},
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                response = self.gateway([self.dict_action('setFeaturedItem', obj, payload)])
                fixtures.assert_gateway_rejected(self, response)
                self.assertEqual(path.read_bytes(), original)
        plot = next(o for o in save['world']['objectsArray'] if o.get('className') == 'Plot')
        cases = (
            ('non-owned building', dict(obj, id=4343)),
            ('plot must not become bare', plot),
            ('snapshot class mismatch', dict(obj, className='Plot')),
        )
        for label, incoming in cases:
            with self.subTest(case=label):
                response = self.gateway([self.dict_action('setFeaturedItem', incoming, good)])
                fixtures.assert_gateway_rejected(self, response)
                self.assertEqual(path.read_bytes(), original)

    def test_catalog_index_preserves_first_historic_duplicate_and_refreshes(self):
        original = items._cached_items
        first = {'name': 'duplicate', 'code': 'X'}
        second = {'name': 'duplicate', 'code': 'X'}
        try:
            items._cached_items = {'settings': {'items': {'item': [first, second]}}}
            self.assertIs(items.get_item_by_name('duplicate'), first)
            self.assertIs(items.get_item_by_code('X'), first)
            replacement = {'name': 'changed', 'code': 'Y'}
            items._cached_items = {'settings': {'items': {'item': [replacement]}}}
            self.assertIsNone(items.get_item_by_name('duplicate'))
            self.assertIs(items.get_item_by_code('Y'), replacement)
        finally:
            items._cached_items = original
            items._index_items()
