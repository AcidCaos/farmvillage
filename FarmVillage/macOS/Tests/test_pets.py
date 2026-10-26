"""Original named puppies and timed feeding through real isolated AMF requests."""
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures  # Must precede every product import.
from pyamf import remoting


class PetWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway
    NOW = 1_800_000_000

    def prepare(self, name='goldenretriever_puppy_cash'):
        import items
        from game_settings import level_to_xp
        self.path = self.write_fixture()
        save = self.player.session('fixture-farmer')
        save['userInfo']['player'].update(cash=1000, gold=1_000_000, xp=level_to_xp(100) + 100, level=100)
        with redirect_stdout(io.StringIO()):
            self.player.save_session('fixture-farmer')
        item = items.get_item_by_name(name)
        self.snapshot = {'id': 64000, 'tempId': -1, 'itemName': name, 'className': 'Pet',
                         'state': 'static', 'position': {'x': 3, 'y': 4, 'z': 0}}
        self.options = {'petName': 'Juniper', 'petGender': 1, 'petType': item['code'],
                        'isGift': False, 'isStorageWithdrawal': 0}
        return save

    def send(self, action, snapshot=None, options=None, sequence=1, now=None, status=200):
        snapshot = copy.deepcopy(self.snapshot if snapshot is None else snapshot)
        params = [] if options is None else [copy.deepcopy(options)]
        with mock.patch('commands.timestamp_now', return_value=self.NOW if now is None else now):
            result = self.gateway([self.command('WorldService.performAction', [action, snapshot, params], sequence)])
        fixtures.assert_gateway_status(self, result, status)
        if status == 200:
            return remoting.decode(result.data).bodies[0][1].body['data'][0]['data']

    def buy(self, **kwargs):
        result = self.send('place', options=self.options, **kwargs)
        self.ident = int(result['id'])
        return self.pet()

    def pet(self):
        return next(p for p in self.player.session('fixture-farmer')['world']['objectsArray'] if p['id'] == self.ident)

    def food(self, food='consume_kibble', **kwargs):
        snapshot = {'id': 0, 'itemName': food, 'className': 'CPetsKibble'}
        options = {'targetObjectId': str(self.ident), 'targetUser': '0', 'isGift': True, 'isFree': False}
        options.update(kwargs.pop('options', {}))
        return self.send('use', snapshot, options, **kwargs)

    def gift_count(self, code):
        return self.player.session('fixture-farmer')['userInfo']['player']['storageData'].get('-1', {}).get(code, [0])[0]

    def grant(self, name, count):
        import storage
        with redirect_stdout(io.StringIO()):
            storage.store_deposit_item_by_name(self.player.session('fixture-farmer'), name, count, storage.GIFTBOX_ID)
            self.player.save_session('fixture-farmer')

    def adult(self, level=1, count=0, last=0, start=0):
        self.pet().update(petLevel=level, kibbleFedCount=count, lastFedTime=last, levelStartTime=start,
                          plantTime=(self.NOW - 15 * 86400) * 1000)
        self.pet().pop('_petLastFeed', None)
        with redirect_stdout(io.StringIO()):
            self.player.save_session('fixture-farmer')

    def assert_atomic(self, action, snapshot=None, options=None, sequence=2, now=None):
        memory = copy.deepcopy(self.player.session('fixture-farmer'))
        before = self.path.read_bytes()
        self.send(action, snapshot, options, sequence=sequence, now=now, status=400)
        self.assertEqual(self.player.session('fixture-farmer'), memory)
        self.assertEqual(self.path.read_bytes(), before)

    def test_named_purchase_initializes_state_and_catalog_bonus(self):
        self.prepare()
        self.snapshot.update(petLevel=5, lastFedTime=0, kibbleFedCount=14, isCash=False, plantTime=1,
                             _petLastFeed={'item': 'fake', 'until': 99999999999999})
        pet = self.buy()
        self.assertEqual((pet['petName'], pet['petGender'], pet['petLevel']), ('Juniper', 1, 0))
        self.assertEqual(pet['plantTime'], self.NOW * 1000)
        self.assertEqual(pet['kibbleFedCount'], 0)
        self.assertTrue(pet['isCash'])
        self.assertNotIn('_petLastFeed', pet)
        self.assertEqual(self.gift_count('0O'), 14)
        self.assertEqual(self.player.session('fixture-farmer')['userInfo']['player']['cash'], 935)
        saved = json.loads(self.path.read_text())['world']['objectsArray'][-1]
        self.assertEqual(saved['petName'], 'Juniper')

    def test_http_catalog_restores_paid_puppy_without_changing_gameplay_catalog(self):
        import items
        import pyamf
        import zlib
        before = copy.deepcopy(items.get_item_by_name('goldenretriever_puppy_cash'))
        response = self.client.get('/xml/gz/v855038/items_opt.amf')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        catalog = pyamf.get_decoder(pyamf.AMF3, zlib.decompress(response.data)).readElement()
        actual = next(item for item in catalog['settings']['items']['item']
                      if item['name'] == before['name'])
        self.assertEqual(actual, dict(before, buyable='true', archived='no'))
        self.assertEqual(items.get_item_by_name(before['name']), before)

    def test_purchase_receipt_survives_restart_and_same_session_retry(self):
        self.prepare()
        self.buy()
        before = self.path.read_bytes()
        self.send('place', options=self.options)
        self.assertEqual(self.path.read_bytes(), before)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.send('place', options=self.options)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.gift_count('0O'), 14)

    def test_permanent_id_placement_retry_cannot_repurchase_bonus(self):
        self.prepare()
        self.buy()
        self.send('place', self.pet(), self.options, sequence=2)
        self.assertEqual(self.gift_count('0O'), 14)
        self.assertEqual(self.player.session('fixture-farmer')['userInfo']['player']['cash'], 935)

    def test_purchase_rejects_type_name_gender_currency_and_free_storage(self):
        self.prepare()
        for changes in ({'petType': '66'}, {'petName': 'X' * 17}, {'petName': '<script>'},
                        {'petName': ' '}, {'petGender': True}, {'petGender': 2},
                        {'currency': 'coins'}, {'isGift': True}, {'isStorageWithdrawal': -2}):
            with self.subTest(changes=changes):
                self.assert_atomic('place', options=dict(self.options, **changes))

    def test_insufficient_cash_rolls_back_pet_and_bonus(self):
        save = self.prepare()
        save['userInfo']['player']['cash'] = 1
        with redirect_stdout(io.StringIO()):
            self.player.save_session('fixture-farmer')
        self.assert_atomic('place', options=self.options)

    def test_daily_kibble_feeding_and_retry_are_durable(self):
        self.prepare()
        self.buy()
        self.food(sequence=2)
        self.assertEqual(self.pet()['kibbleFedCount'], 1)
        self.assertEqual(self.gift_count('0O'), 13)
        self.food(sequence=3)
        self.assertEqual(self.gift_count('0O'), 13)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.food(sequence=2)
        self.assertEqual(self.pet()['kibbleFedCount'], 1)
        self.food(sequence=4, now=self.NOW + 86400)
        self.assertEqual(self.pet()['kibbleFedCount'], 2)
        self.assertEqual(self.gift_count('0O'), 12)

    def test_wrong_food_foreign_target_free_or_bulk_feed_are_atomic(self):
        self.prepare()
        self.buy()
        food = {'id': 0, 'itemName': 'consume_kibble', 'className': 'CPetsKibble'}
        opts = {'targetObjectId': str(self.ident), 'targetUser': '0', 'isGift': True, 'isFree': False}
        for changes in ({'targetObjectId': '99999'}, {'targetObjectId': True}, {'targetUser': 'someone-else'},
                        {'isFree': True}, {'isGift': False}, {'itemCount': 2}, {'storageId': -2}):
            self.assert_atomic('use', food, dict(opts, **changes))
        self.assert_atomic('use', dict(food, itemName='consume_treat'), opts)

    def test_missing_food_does_not_train_or_change_saved_state(self):
        self.prepare()
        self.buy()
        self.adult()
        before = self.path.read_bytes()
        self.food('consume_treat', sequence=2, status=400)
        self.assertEqual(self.path.read_bytes(), before)

    def test_cash_puppy_matures_after_real_fourteen_days(self):
        self.prepare()
        self.buy()
        self.assert_atomic('adulthoodReached', self.pet(), sequence=2, now=self.NOW + 14 * 86400 - 1)
        self.send('adulthoodReached', self.pet(), sequence=3, now=self.NOW + 14 * 86400)
        self.assertEqual(self.pet()['petLevel'], 1)
        self.assertTrue(self.pet()['hasUserSeenAdult'])

    def test_coin_puppy_requires_feeds_as_well_as_age_and_catalog_limit(self):
        self.prepare('bordercollie_puppy_red')
        self.buy()
        self.assertEqual(self.gift_count('0O'), 1)
        self.assert_atomic('adulthoodReached', self.pet(), sequence=2, now=self.NOW + 15 * 86400)
        self.assert_atomic('place', dict(self.snapshot, id=64001), self.options, sequence=3)
        self.pet().update(kibbleFedCount=14)
        self.send('adulthoodReached', self.pet(), sequence=4, now=self.NOW + 14 * 86400)
        self.assertEqual(self.pet()['petLevel'], 1)

    def test_training_thresholds_unlock_only_catalog_tricks(self):
        self.prepare()
        self.buy()
        self.adult()
        self.grant('consume_treat', 14)
        for day in range(14):
            self.food('consume_treat', sequence=day + 2, now=self.NOW + day * 86400)
            self.assertEqual(self.pet()['petLevel'], 2 if day < 3 else 3 if day < 6 else 4 if day < 13 else 5)
        self.assertEqual(self.gift_count('0z'), 0)
        self.send('performTrick', self.pet(), {'trickName': 'shake', 'harvestObjectIds': []}, sequence=20)
        self.assert_atomic('performTrick', self.pet(), {'trickName': 'fetch', 'harvestObjectIds': []}, sequence=21)

    def test_unlearned_trick_and_client_training_forgery_are_rejected(self):
        self.prepare()
        self.buy()
        self.assert_atomic('performTrick', dict(self.pet(), petLevel=5),
                           {'trickName': 'shake', 'harvestObjectIds': []})
        moved = dict(self.pet(), petLevel=5, petName='Forged', isCash=False, plantTime=1,
                     position={'x': 5, 'y': 6, 'z': 0})
        self.send('move', moved, {'allowFollow': True}, sequence=3)
        self.assertEqual((self.pet()['petName'], self.pet()['petLevel']), ('Juniper', 0))
        self.assertTrue(self.pet()['allowFollow'])

    def test_follow_move_uses_actual_tmove_params_and_preserves_identity(self):
        self.prepare()
        self.buy()
        self.send('move', self.pet(), {'x': 9, 'y': 10, 'direction': 2, 'allowFollow': True, 'visiting': '0'}, sequence=2)
        self.assertEqual(self.pet()['position'], {'x': 9, 'y': 10, 'z': 0})
        self.assertTrue(self.pet()['allowFollow'])
        self.assert_atomic('move', dict(self.pet(), itemName='goldenretriever_puppy_cream_cash'), sequence=3)
        self.assert_atomic('move', self.pet(), {'allowFollow': 'true'}, sequence=4)

    def test_runaway_rescue_cost_and_response_do_not_repeat(self):
        self.prepare('bordercollie_puppy_red')
        self.buy()
        self.send('runaway', self.pet(), sequence=2, now=self.NOW + 2 * 86400)
        self.assertTrue(self.pet()['isRunAway'])
        result = self.send('rescuePet', self.pet(), sequence=3, now=self.NOW + 2 * 86400)
        self.assertEqual(result['lastFedTime'], (self.NOW + 2 * 86400) * 1000)
        self.assertFalse(self.pet()['isRunAway'])
        self.assertEqual(self.player.session('fixture-farmer')['userInfo']['player']['cash'], 998)
        self.send('rescuePet', self.pet(), sequence=4, now=self.NOW + 2 * 86400)
        self.assertEqual(self.player.session('fixture-farmer')['userInfo']['player']['cash'], 998)

    def test_missed_adult_training_day_resets_only_current_level_progress(self):
        self.prepare()
        self.buy()
        self.adult(level=3, count=2, last=(self.NOW - 3 * 86400) * 1000,
                   start=(self.NOW - 3 * 86400) * 1000)
        self.grant('consume_treat', 1)
        self.food('consume_treat', sequence=2)
        self.assertEqual((self.pet()['petLevel'], self.pet()['kibbleFedCount']), (3, 1))
        self.assertEqual(self.pet()['levelStartTime'], self.NOW * 1000)

    def test_storage_and_harvest_cannot_erase_pet_identity_or_pay_yield(self):
        self.prepare()
        self.buy()
        self.assert_atomic('harvest', self.pet())
        self.assert_atomic('store', self.pet(), {'storedItemName': self.pet()['itemName'],
                           'resource': self.ident, 'target': -2, 'numToStore': 1}, sequence=3)
        building = {'id': -2, 'itemName': 'barn', 'className': 'Building'}
        self.assert_atomic('store', building, {'storedItemName': self.pet()['itemName'],
                           'resource': self.ident, 'target': -2, 'numToStore': 1}, sequence=4)

    def test_rejected_followup_keeps_pet_price_bonus_and_receipts(self):
        self.prepare()
        before = self.path.read_bytes()
        with mock.patch('commands.timestamp_now', return_value=self.NOW):
            response = self.gateway([
                self.command('WorldService.performAction', ['place', self.snapshot, [self.options]], 1),
                self.command('WorldService.performAction', ['rescuePet', {'id': 99999, 'itemName': self.snapshot['itemName'], 'className': 'Pet'}, []], 2),
            ])
        fixtures.gateway_results(self, response, [0, 29])
        saved = json.loads(self.path.read_text())
        self.assertEqual(saved['userInfo']['player']['cash'], 935)
        self.assertEqual(self.gift_count('0O'), 14)
        self.assertIn('_petRequests', saved)
        with mock.patch('commands.timestamp_now', return_value=self.NOW):
            self.send('place', options=self.options)
        self.assertEqual(json.loads(self.path.read_text()), saved)

    def test_sequence_reuse_different_action_is_atomic(self):
        self.prepare()
        self.buy()
        self.assert_atomic('move', self.pet(), sequence=1)

    def test_original_first_world_action_marker_is_accepted(self):
        self.prepare()
        with mock.patch('commands.timestamp_now', return_value=self.NOW):
            response = self.gateway([self.command('WorldService.performAction',
                ['place', self.snapshot, [self.options, {'firstWA': True}]], 1)])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.gift_count('0O'), 14)

    def test_receipts_cannot_replay_across_active_worlds(self):
        import pets
        self.prepare()
        self.buy()
        save = self.player.session('fixture-farmer')
        save['userInfo']['currentWorldType'] = 'england'
        with self.assertRaisesRegex(ValueError, 'reused'):
            pets.dispatch(save, 'place', self.snapshot, [self.options], 1,
                          lambda: self.fail('A foreign-world receipt must not execute.'))

    def test_targeted_feed_rejects_explicit_foreign_world_context(self):
        self.prepare()
        self.buy()
        save = self.player.session('fixture-farmer')
        save['userInfo']['currentWorldType'] = 'farm'
        save['userInfo']['worldSummaryData']['farm']['storageId'] = -2
        save['_ownedWorldTravel'] = {'version': 1, 'inactive': {}, 'nextObjectId': self.ident + 1}
        with redirect_stdout(io.StringIO()):
            self.player.save_session('fixture-farmer')
        before = self.path.read_bytes()
        self.food(options={'worldType': 'england'}, sequence=2, status=400)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.gift_count('0O'), 14)

    def test_evicted_old_receipt_cannot_repurchase_after_restart(self):
        import pets
        save = self.prepare()
        for sequence in range(1, 258):
            pets.dispatch(save, 'place', self.snapshot, [self.options], sequence, lambda: 42)
        self.assertEqual(len(save['_petRequests']['receipts']), 256)
        with redirect_stdout(io.StringIO()):
            self.player.save_session('fixture-farmer')
            self.player.load_saves()
        save = self.player.session('fixture-farmer')
        with self.assertRaisesRegex(ValueError, 'older'):
            pets.dispatch(save, 'place', self.snapshot, [self.options], 1,
                          lambda: self.fail('An evicted receipt must not execute.'))

    def test_init_refreshes_maturity_and_strips_internal_receipts(self):
        self.prepare()
        self.buy()
        with mock.patch('commands.timestamp_now', return_value=self.NOW + 14 * 86400):
            response = self.gateway([self.command('UserService.initUser', ['Pet fixture', 0, True, None], 2)])
        self.assertEqual(response.status_code, 200)
        payload = remoting.decode(response.data).bodies[0][1].body['data'][0]['data']
        self.assertNotIn('_petRequests', payload)
        self.assertEqual(self.pet()['petLevel'], 1)

    def test_food_package_catalog_payment_and_restart_retry(self):
        self.prepare()
        for name, code, quantity, cost, sequence in (('pkg_kibble', '0O', 1, 3, 1),
                                                   ('pkg_treat', '0z', 7, 5, 2)):
            cash = self.player.session('fixture-farmer')['userInfo']['player']['cash']
            response = self.gateway([self.command('FarmService.buyConsumablePackage', [name], sequence)])
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.gift_count(code), quantity)
            self.assertEqual(self.player.session('fixture-farmer')['userInfo']['player']['cash'], cash - cost)
            with redirect_stdout(io.StringIO()):
                self.player.load_saves()
            response = self.gateway([self.command('FarmService.buyConsumablePackage', [name], sequence)])
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.gift_count(code), quantity)
            self.assertEqual(self.player.session('fixture-farmer')['userInfo']['player']['cash'], cash - cost)

    def test_food_package_insufficient_cash_and_reused_sequence_are_atomic(self):
        save = self.prepare()
        save['userInfo']['player']['cash'] = 3
        with redirect_stdout(io.StringIO()):
            self.player.save_session('fixture-farmer')
        before = self.path.read_bytes()
        response = self.gateway([self.command('FarmService.buyConsumablePackage', ['pkg_treat'], 1)])
        fixtures.assert_gateway_rejected(self, response)
        self.assertEqual(self.path.read_bytes(), before)
        response = self.gateway([self.command('FarmService.buyConsumablePackage', ['pkg_kibble'], 1)])
        self.assertEqual(response.status_code, 200)
        before = self.path.read_bytes()
        response = self.gateway([self.command('FarmService.buyConsumablePackage', ['pkg_treat'], 1)])
        fixtures.assert_gateway_rejected(self, response)
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
