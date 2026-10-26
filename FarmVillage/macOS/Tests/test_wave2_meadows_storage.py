"""W03 exact ordinary capacity, paid replacement growth and licensed shipping.

Synthetic preconditions are explicit fixtures; no clocks are accelerated.
"""
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import test_cove_cellar as cellar_fixtures
import items
import storage
import meadows_storage
import world_travel

NOW = 1800000000


class MeadowsStorageTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway
    save = cellar_fixtures.CoveCellarTests.save
    prepare = cellar_fixtures.CoveCellarTests.prepare
    persist = cellar_fixtures.CoveCellarTests.persist
    send = cellar_fixtures.CoveCellarTests.send
    rejected = cellar_fixtures.CoveCellarTests.rejected

    def fixture_meadows(self):
        self.prepare('meadows', gold=1000000)
        self.save['userInfo']['player']['cash'] = 500
        self.save['world']['objectsArray'] = []
        self.persist()

    @staticmethod
    def shed(name='toolshedpink', ident=900):
        return {'id': ident, 'itemName': name, 'className': 'StorageBuilding',
                'state': 'built_0', 'position': {'x': 4, 'y': 4, 'z': 0},
                'contents': [], 'unknownImported': {'keep': [1, 2]}}

    def license_fixture(self):
        # Genuine saved-license shape, seeded rather than earned gameplay.
        self.save['userInfo']['unlockedWorldContentLicenses'] = {
            'farm': {'world': True}, 'meadows': {'world': True}}

    def transfer(self, *, sequence=1, quantity=1, metadata=None):
        return storage.store_world_item(self.save, {'id': -16, 'className': 'StorageBuilding'},
            {'storedItemName': 'haybale', 'origin': -2, 'target': -16, 'resource': 0,
             'numToStore': quantity, 'metadata': metadata}, request_id=sequence)

    def test_each_exact_paid_shed_barn_ladder_retains_identity_and_imports(self):
        for root in meadows_storage._ROOTS:
            with self.subTest(root=root):
                self.fixture_meadows()
                self.save['world']['objectsArray'] = [self.shed(root)]
                self.save['userInfo']['player']['storageData']['900'] = {'HB': [1, ['friend'], [{'keep': 1}]]}
                for sequence, suffix in enumerate(('2', '3'), 1):
                    snapshot = self.shed(root if sequence == 1 else root + '2')
                    before = self.save['userInfo']['player']['cash']
                    meadows_storage.purchase_storage_upgrade(self.save, snapshot, [], request_id=sequence)
                    obj = self.save['world']['objectsArray'][0]
                    self.assertEqual(obj['itemName'], root + suffix)
                    self.assertEqual(obj['expansionLevel'], sequence + 1)
                    self.assertEqual(obj['unknownImported'], {'keep': [1, 2]})
                    self.assertEqual(self.save['userInfo']['player']['cash'], before - 10)
                    after = copy.deepcopy(self.save)
                    meadows_storage.purchase_storage_upgrade(self.save, snapshot, [], request_id=sequence)
                    self.assertEqual(self.save, after)
                self.assertEqual(self.save['userInfo']['player']['storageData']['900'], {'HB': [1, ['friend'], [{'keep': 1}]]})
                after = copy.deepcopy(self.save)
                with self.assertRaisesRegex(ValueError, 'last recovered'):
                    meadows_storage.purchase_storage_upgrade(self.save, self.shed(root + '3'), [], request_id=3)
                self.assertEqual(self.save, after)

    def test_growth_refuses_forged_identity_price_funds_helper_and_wrong_world_atomically(self):
        self.fixture_meadows()
        self.save['world']['objectsArray'] = [self.shed()]
        for snapshot, params, cash, status in (
                (self.shed('toolshedpink3'), [], 500, {}),
                (self.shed('toolshedpink2'), [{'price': 0}], 500, {}),
                (self.shed('toolshedpink2'), [], 9, {}),
                (self.shed('toolshedpink2'), [], 500, {'isActive': True, 'numHelped': 8}),
                (dict(self.shed('toolshedpink2'), id=901), [], 500, {})):
            self.save['userInfo']['player'].update(cash=cash, upgradeStatus=status)
            before = copy.deepcopy(self.save)
            with self.assertRaises(ValueError):
                meadows_storage.purchase_storage_upgrade(self.save, snapshot, params, request_id=4)
            self.assertEqual(self.save, before)
        world_travel.switch(self.save, 'farm', now=NOW)
        before = copy.deepcopy(self.save)
        with self.assertRaises(ValueError):
            meadows_storage.purchase_storage_upgrade(self.save, self.shed('toolshedpink2'), [], request_id=5)
        self.assertEqual(self.save, before)

    def test_capacity_grows_from_fifteen_to_twenty_and_twentyseven_without_free_slots(self):
        self.fixture_meadows()
        self.save['world']['objectsArray'] = [self.shed()]
        for sequence, name, capacity in ((0, 'toolshedpink', 15), (1, 'toolshedpink2', 20), (2, 'toolshedpink3', 27)):
            if sequence:
                meadows_storage.purchase_storage_upgrade(self.save, self.shed('toolshedpink' if sequence == 1 else 'toolshedpink2'), [], request_id=sequence)
            storage._guard_inventory_deposit(self.save, -16, capacity)
            with self.assertRaises(ValueError):
                storage._guard_inventory_deposit(self.save, -16, capacity + 1)
        self.persist()
        self.player.load_saves()
        storage._guard_inventory_deposit(self.save, -16, 27)

    def test_shipping_requires_both_saved_boolean_licenses_and_owned_source(self):
        self.fixture_meadows()
        self.save['world']['objectsArray'] = [self.shed()]
        self.save['userInfo']['player']['storageData']['-2'] = {'HB': [2, [], []]}
        for licenses in ({}, {'meadows': {'world': True}}, {'farm': {'world': True}},
                         {'farm': {'world': 'true'}, 'meadows': {'world': True}},
                         {'farm': {'world': True}, 'meadows': {'world': 1}}):
            self.save['userInfo']['unlockedWorldContentLicenses'] = licenses
            before = copy.deepcopy(self.save)
            with self.assertRaisesRegex(ValueError, 'license'):
                self.transfer()
            self.assertEqual(self.save, before)
        self.license_fixture()
        foreign = copy.deepcopy(self.save['_ownedWorldTravel']['inactive']['farm'])
        del self.save['_ownedWorldTravel']['inactive']['farm']
        with self.assertRaises(ValueError):
            self.transfer()
        self.save['_ownedWorldTravel']['inactive']['farm'] = foreign
        before = copy.deepcopy(self.save)
        with self.assertRaises(ValueError):
            meadows_storage.guard_shipping(self.save, -8, items.get_item_by_name('haybale'))
        self.assertEqual(self.save, before)

    def test_shipping_preserves_authoritative_metadata_quantity_retry_reload_and_home(self):
        self.fixture_meadows()
        self.save['world']['objectsArray'] = [self.shed()]
        self.license_fixture()
        self.save['userInfo']['player']['storageData']['-2'] = {'HB': [3, ['a', 'b'], [{'unit': 1}, {'unit': 2}, {'unit': 3}]]}
        self.transfer(sequence=4, quantity=2, metadata={'forged': 999})
        ledger = self.save['userInfo']['player']['storageData']
        self.assertEqual(ledger['-2']['HB'], [1, ['b'], [{'unit': 3}]])
        self.assertEqual(ledger['-16']['HB'], [2, ['a'], [{'unit': 1}, {'unit': 2}]])
        self.persist()
        self.player.load_saves()
        before = copy.deepcopy(self.save)
        self.transfer(sequence=4, quantity=2, metadata={'forged': 999})
        self.assertEqual(self.save, before)
        with self.assertRaisesRegex(ValueError, 'reused'):
            self.transfer(sequence=4, quantity=1)
        world_travel.switch(self.save, 'farm', now=NOW)
        self.assertEqual(self.save['userInfo']['player']['storageData']['-2']['HB'], [1, ['b'], [{'unit': 3}]])

    def test_shipping_full_capacity_and_bad_items_refuse_without_source_loss(self):
        self.fixture_meadows()
        self.license_fixture()
        self.save['userInfo']['player']['storageData']['-2'] = {'HB': [2, [], [{'keep': 1}]]}
        before = copy.deepcopy(self.save)
        with self.assertRaises(ValueError):
            self.transfer()
        self.assertEqual(self.save, before)
        self.save['world']['objectsArray'] = [self.shed()]
        for name in ('xukcraftingpub', 'superplot', 'hatchstorage'):
            item = items.get_item_by_name(name)
            if item:
                with self.assertRaises(ValueError):
                    meadows_storage.guard_shipping(self.save, -2, item)

    def test_exact_license_package_and_owned_consumer_charge_once_and_do_not_grant_home(self):
        self.fixture_meadows()
        before = self.save['userInfo']['player']['cash']
        self.assertEqual(meadows_storage.buy_license_package(self.save, 'pkg_meadowsXfer', request_id=20), {})
        self.assertEqual(self.save['userInfo']['player']['cash'], before - 250)
        self.assertNotIn('bpT', self.save['userInfo']['player']['storageData']['-1'])
        self.assertTrue(meadows_storage.has_license(self.save, 'meadows'))
        self.assertEqual(meadows_storage.buy_license_package(self.save, 'pkg_meadowsXfer', request_id=20), {})
        self.assertEqual(meadows_storage.buy_license_package(self.save, 'pkg_meadowsXfer', request_id=21), {})
        self.assertEqual(self.save['userInfo']['player']['cash'], before - 250)
        storage.consume_by_name(self.save, 'consume_meadowsXfer', 1, -1)
        self.assertTrue(meadows_storage.has_license(self.save, 'meadows'))
        self.assertFalse(meadows_storage.has_license(self.save, 'farm'))
        after = copy.deepcopy(self.save)
        storage.consume_by_name(self.save, 'consume_meadowsXfer', 1, -1)
        self.assertEqual(self.save, after)
        self.persist()
        self.player.load_saves()
        self.assertTrue(meadows_storage.has_license(self.save, 'meadows'))

    def test_license_gates_insufficient_cash_missing_gift_and_malformed_licenses_are_atomic(self):
        self.fixture_meadows()
        self.save['userInfo']['player']['cash'] = 249
        before = copy.deepcopy(self.save)
        with self.assertRaises(ValueError):
            meadows_storage.buy_license_package(self.save, 'pkg_meadowsXfer', request_id=22)
        self.assertEqual(self.save, before)
        self.save['userInfo']['player']['cash'] = 500
        before = copy.deepcopy(self.save)
        with mock.patch.object(meadows_storage, '_experiment', return_value=False), self.assertRaises(ValueError):
            meadows_storage.buy_license_package(self.save, 'pkg_meadowsXfer', request_id=22)
        self.assertEqual(self.save, before)
        for group, count in ((-1, 1), (-16, 1), (-1, 2)):
            with self.assertRaises(ValueError):
                storage.consume_by_name(self.save, 'consume_meadowsXfer', count, group)
            self.assertEqual(self.save, before)

    def test_imported_cellar_received_credits_provide_only_the_exact_current_world_capacity(self):
        self.fixture_meadows()
        self.save['world']['objectsArray'] = [cellar_fixtures.CoveCellarTests.cellar()]
        self.save['userInfo']['player']['featureCredits'] = {
            'farm': {'InventoryCellar': {'current': 99, 'received': 999}},
            'meadows': {'InventoryCellar': {'current': 1, 'received': 7, 'future': {'keep': True}}}}
        storage._guard_inventory_deposit(self.save, -16, 7)
        with self.assertRaises(ValueError):
            storage._guard_inventory_deposit(self.save, -16, 8)
        self.save['userInfo']['player']['featureCredits']['meadows']['InventoryCellar']['received'] = 99999
        storage._guard_inventory_deposit(self.save, -16, 1250)
        with self.assertRaises(ValueError):
            storage._guard_inventory_deposit(self.save, -16, 1251)
        self.assertEqual(self.save['userInfo']['player']['featureCredits']['meadows']['InventoryCellar']['current'], 1)

    def test_signed_amf_paid_upgrade_and_retry_charge_once(self):
        self.fixture_meadows()
        self.save['world']['objectsArray'] = [self.shed()]
        self.persist()
        before = self.save['userInfo']['player']['cash']
        snapshot = self.shed('toolshedpink')
        self.send('purchaseStorageUpgrade', snapshot)
        self.assertEqual(self.save['userInfo']['player']['cash'], before - 10)
        self.assertEqual(self.save['world']['objectsArray'][0]['expansionLevel'], 2)
        after = copy.deepcopy(self.save)
        # Replay the same signed request, not a fresh transaction with a stale tier.
        self._gateway_sequence -= 1
        self.send('purchaseStorageUpgrade', snapshot)
        self.assertEqual(self.save, after)
        self.player.load_saves()
        self.assertEqual(self.save['world']['objectsArray'][0]['itemName'], 'toolshedpink2')
        storage._guard_inventory_deposit(self.save, -16, 20)

    def test_owned_imported_license_consumable_uses_gift_once_without_buying(self):
        self.fixture_meadows()
        self.save['userInfo']['player']['storageData']['-1']['bpT'] = [1, ['sender'], [{'keep': 1}]]
        before = self.save['userInfo']['player']['cash']
        storage.consume_by_name(self.save, 'consume_meadowsXfer', 1, -1)
        self.assertTrue(meadows_storage.has_license(self.save, 'meadows'))
        self.assertNotIn('bpT', self.save['userInfo']['player']['storageData']['-1'])
        self.assertEqual(self.save['userInfo']['player']['cash'], before)

    def init_sequence(self):
        response = self.gateway([self.command('UserService.initUser', ['QA', 0, True, {}])])
        data = fixtures.gateway_results(self, response, [0])[0]['data']
        self.assertEqual(data['sequenceId'], self.save[meadows_storage.STATE]['sessionID'])
        self.assertNotIn(meadows_storage.STATE, data)
        return data['sequenceId']

    def session_action(self, action, snapshot, params=(), *, sequence=1, sequence_id=None, expected=200):
        entry = self.command('WorldService.performAction', [action, copy.deepcopy(snapshot), list(params)], sequence)
        if sequence_id is not None:
            entry['sequenceID'] = sequence_id
        response = self.gateway([entry])
        fixtures.assert_gateway_status(self, response, expected)
        return response

    def test_original_sequence_id_retains_upgrade_retry_across_init_and_restart(self):
        self.fixture_meadows()
        self.save['world']['objectsArray'] = [self.shed()]
        self.persist()
        first_id = self.init_sequence()
        self.session_action('purchaseStorageUpgrade', self.shed('toolshedpink'), sequence=7, sequence_id=first_id)
        self.persist()
        self.player.load_saves()
        cash = self.save['userInfo']['player']['cash']
        self.session_action('purchaseStorageUpgrade', self.shed('toolshedpink'), sequence=7, sequence_id=first_id)
        self.assertEqual(self.save['userInfo']['player']['cash'], cash)
        self.init_sequence()
        current_id = self.init_sequence()
        self.assertNotEqual(current_id, first_id)
        self.session_action('purchaseStorageUpgrade', self.shed('toolshedpink'), sequence=7, sequence_id=first_id)
        self.assertEqual(self.save['userInfo']['player']['cash'], cash)
        self.session_action('purchaseStorageUpgrade', self.shed('toolshedpink2'), sequence=7, sequence_id=current_id)
        self.assertEqual(self.save['world']['objectsArray'][0]['expansionLevel'], 3)
        self.assertEqual(self.save['userInfo']['player']['cash'], cash - 10)
        before = copy.deepcopy(self.save)
        self.session_action('purchaseStorageUpgrade', self.shed('toolshedpink'), sequence=8,
                            sequence_id=current_id, expected=400)
        self.assertEqual(self.save, before)

    def test_old_shipping_packet_after_two_init_calls_cannot_withdraw_twice(self):
        self.fixture_meadows()
        self.license_fixture()
        self.save['world']['objectsArray'] = [self.shed()]
        self.save['userInfo']['player']['storageData']['-2'] = {'HB': [4, [], []]}
        self.persist()
        snapshot = {'id': -16, 'className': 'StorageBuilding'}
        options = {'storedItemName': 'haybale', 'origin': -2, 'target': -16, 'resource': 0}
        first_id = self.init_sequence()
        self.session_action('store', snapshot, [options], sequence=11, sequence_id=first_id)
        previous_id = self.init_sequence()
        current_id = self.init_sequence()
        self.session_action('store', snapshot, [options], sequence=11, sequence_id=first_id)
        ledger = self.save['userInfo']['player']['storageData']
        self.assertEqual((ledger['-2']['HB'][0], ledger['-16']['HB'][0]), (3, 1))
        self.session_action('store', snapshot, [options], sequence=11, sequence_id=current_id)
        ledger = self.save['userInfo']['player']['storageData']
        self.assertEqual((ledger['-2']['HB'][0], ledger['-16']['HB'][0]), (2, 2))
        self.persist()
        self.player.load_saves()
        self.session_action('store', snapshot, [options], sequence=11, sequence_id=current_id)
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        for token in (previous_id, 'unknown-session', None):
            self.session_action('store', snapshot, [options], sequence=99, sequence_id=token, expected=400)
            self.assertEqual(self.save, before)
            self.assertEqual(self.path.read_bytes(), disk)
        # Explicitly seeded evicted receipt: an old ID cannot become new.
        del self.save[meadows_storage.STATE]['receipts'][first_id + ':shipping:11']
        self.persist()
        before = copy.deepcopy(self.save)
        self.session_action('store', snapshot, [options], sequence=11, sequence_id=first_id, expected=400)
        self.assertEqual(self.save, before)

    def test_licensed_source_cannot_bypass_capacity_through_positive_or_wrong_target(self):
        self.fixture_meadows()
        self.license_fixture()
        self.save['world']['objectsArray'] = [self.shed(ident=901)]
        self.save['userInfo']['player']['storageData']['-2'] = {'HB': [2, [], []]}
        self.persist()
        for target in (901, -8, -2):
            snapshot = {'id': target, 'className': 'StorageBuilding'}
            options = {'storedItemName': 'haybale', 'origin': -2, 'target': target, 'resource': 0}
            before = copy.deepcopy(self.save)
            with self.assertRaisesRegex(ValueError, 'active farm inventory'):
                storage.store_world_item(self.save, snapshot, options, request_id=1)
            self.assertEqual(self.save, before)
            self.rejected('store', snapshot, [options])

    def test_other_authored_shipping_packages_are_refused_before_generic_charge_on_meadows(self):
        self.fixture_meadows()
        for package in ('pkg_englandXfer', 'pkg_fishermanXfer'):
            before, disk = copy.deepcopy(self.save), self.path.read_bytes()
            with self.assertRaisesRegex(ValueError, 'other world shipping license'):
                meadows_storage.buy_license_package(self.save, package, request_id=1)
            response = self.gateway([self.command('FarmService.buyConsumablePackage', [package])])
            fixtures.assert_gateway_status(self, response, 400)
            self.assertEqual(self.save, before)
            self.assertEqual(self.path.read_bytes(), disk)
        world_travel.switch(self.save, 'farm', now=NOW)
        self.assertIsNone(meadows_storage.buy_license_package(self.save, 'pkg_englandXfer', request_id=1))

    def test_evicted_sequences_remain_refused_instead_of_recharging(self):
        self.fixture_meadows()
        self.license_fixture()
        self.save['world']['objectsArray'] = [self.shed()]
        self.save['userInfo']['player']['storageData']['-2'] = {'HB': [1, [], []]}
        self.save[meadows_storage.STATE] = {'receipts': {}, 'highestSequences': {'shipping': 300}}
        before = copy.deepcopy(self.save)
        with self.assertRaisesRegex(ValueError, 'older'):
            self.transfer(sequence=1)
        self.assertEqual(self.save, before)

    def test_shipping_id_fields_reject_fraction_bool_nan_unknown_and_ambiguous_sources_atomically(self):
        self.fixture_meadows()
        self.license_fixture()
        self.save['world']['objectsArray'] = [self.shed()]
        self.save['userInfo']['player']['storageData']['-2'] = {'HB': [2, ['sender'], [{'keep': 1}]]}
        self.persist()
        snapshot = {'id': -16, 'className': 'StorageBuilding'}
        base = {'storedItemName': 'haybale', 'origin': -2, 'target': -16, 'resource': 0}
        cases = []
        for field in ('origin', 'cameFromLocation', 'target', 'resource'):
            for value in (-2.5, True, False, float('nan'), float('inf'), '-2.5'):
                cases.append((snapshot, {**base, field: value}))
        cases.extend((
            ({**snapshot, 'id': -16.5}, base),
            ({**snapshot, 'id': True}, base),
            ({**snapshot, 'id': float('nan')}, base),
            (snapshot, {**base, 'origin': -999}),
            (snapshot, {**base, 'origin': -2, 'cameFromLocation': -16}),
            (snapshot, {**base, 'origin': 0, 'cameFromLocation': -2}),
        ))
        for index, (incoming, options) in enumerate(cases, 1):
            with self.subTest(index=index, options=options, snapshot=incoming):
                before = copy.deepcopy(self.save)
                disk = self.path.read_bytes()
                with self.assertRaises(ValueError):
                    storage.store_world_item(self.save, incoming, options, request_id=index)
                self.assertEqual(self.save, before)
                self.assertEqual(self.path.read_bytes(), disk)
                self.rejected('store', incoming, [options])

    def test_shipping_whole_string_origin_matches_original_client_without_aliasing(self):
        self.fixture_meadows()
        self.license_fixture()
        self.save['world']['objectsArray'] = [self.shed()]
        self.save['userInfo']['player']['storageData']['-2'] = {'HB': [1, ['sender'], [{'keep': 1}]]}
        self.persist()
        self.send('store', {'id': -16, 'className': 'StorageBuilding'},
                  [{'storedItemName': 'haybale', 'origin': '-2', 'cameFromLocation': -2,
                    'target': '-16', 'resource': '0'}])
        self.assertEqual(self.save['userInfo']['player']['storageData']['-16']['HB'], [1, ['sender'], [{'keep': 1}]])
        self.assertNotIn('HB', self.save['userInfo']['player']['storageData']['-2'])

    def test_foreign_placement_group_refuses_nonwhole_ids_before_withdrawal(self):
        self.fixture_meadows()
        self.license_fixture()
        self.save['userInfo']['player']['storageData']['-2'] = {'HB': [1, [], []]}
        for source in (-2.5, True, False, float('nan')):
            before = copy.deepcopy(self.save)
            with self.assertRaises(ValueError):
                storage.withdraw_for_placement(self.save, 'haybale', [{'isStorageWithdrawal': source}],
                                              {'id': 64001, 'itemName': 'haybale', 'className': 'Decoration'})
            self.assertEqual(self.save, before)

    def test_signed_amf_package_use_and_shipping_persist(self):
        self.fixture_meadows()
        package = self.gateway([self.command('FarmService.buyConsumablePackage', ['pkg_meadowsXfer'], 30)])
        fixtures.assert_gateway_status(self, package, 200)
        self.send('use', {'id': -1, 'itemName': 'consume_meadowsXfer', 'className': 'CRewardConsumable'},
                  [{'storageId': -1, 'itemCount': 1}])
        self.assertTrue(meadows_storage.has_license(self.save, 'meadows'))
        self.save['userInfo']['unlockedWorldContentLicenses']['farm'] = {'world': True}
        self.save['world']['objectsArray'] = [self.shed()]
        self.save['userInfo']['player']['storageData']['-2'] = {'HB': [1, [], [{'keep': 1}]]}
        self.persist()
        self.send('store', {'id': -16, 'className': 'StorageBuilding'},
                  [{'storedItemName': 'haybale', 'origin': -2, 'target': -16, 'resource': 0}])
        self.assertEqual(self.save['userInfo']['player']['storageData']['-16']['HB'], [1, [], [{'keep': 1}]])
        self.player.load_saves()
        self.assertNotIn('HB', self.save['userInfo']['player']['storageData']['-2'])


if __name__ == '__main__':
    unittest.main()
