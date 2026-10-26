"""W01: Home inventory and positive containers are separate storage authorities."""
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
import peaceful
import storage

NOW = 1_800_000_000


class HomeContainerBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if items._cached_items is None:
            with redirect_stdout(io.StringIO()):
                items.load_items()
        cls.occupants = {}
        for name, kind in storage._HOME_HABITATS.items():
            cls.occupants[name] = next(item for item_name in sorted(storage._home_habitat_storage_filters()[kind])
                if (item := items.get_item_by_name(item_name)) and item.get('type') == 'animal'
                and item.get('className') in (None, 'Animal'))

    def setUp(self):
        self.save = {'world': {'objectsArray': []}, 'userInfo': {'currentWorldType': 'farm',
            'player': {'gold': 2_000_000, 'cash': 1000, 'xp': 100015,
                'storageData': {'-1': {}, '-2': {}, '-8': {'HB': [1, [], [{'foreign': True}]]}}}}}
        self.owner()

    @property
    def owner_object(self):
        return self.save['world']['objectsArray'][0]

    def owner(self, name='animal_breeding_aviary_finished', level=1, **extra):
        self.name = name
        self.catalog = items.get_item_by_name(name)
        self.save['world']['objectsArray'] = [{'id': 600, 'itemName': name,
            'className': self.catalog['className'], 'state': 'built', 'isFullyBuilt': True,
            'expansionLevel': level, 'capacity': 99999, 'contents': [],
            'plantTime': NOW * 1000 - 20_000_000, 'storageMetadata': {'opaque': {'keep': [1]}},
            'extraDataState': {'opaque': [2]}, 'position': {'x': 10, 'y': 10, 'z': 0}, **extra}]
        self.save['userInfo']['player']['storageData'].pop('600', None)

    def gift(self, item, quantity=1, metadata=None):
        self.save['userInfo']['player']['storageData']['-1'][item['code']] = [
            quantity, ['friend'], copy.deepcopy(metadata or [])]

    def store(self, item, **options):
        with redirect_stdout(io.StringIO()), mock.patch.object(engine, 'timestamp_now', return_value=NOW):
            storage.store_world_item(self.save, copy.deepcopy(self.owner_object), {
                'storedItemName': item['name'], 'isGift': True, **options})

    def reject(self, item, **options):
        before = copy.deepcopy(self.save)
        with self.assertRaises(ValueError):
            self.store(item, **options)
        self.assertEqual(self.save, before)

    def test_seven_exact_base_owners_original_filters_and_finite_capacities(self):
        self.assertEqual(len(storage._HOME_HABITATS), 7)
        self.assertEqual(len(storage._home_habitat_storage_filters()), 7)
        for name, kind in storage._HOME_HABITATS.items():
            item = items.get_item_by_name(name)
            self.assertEqual(storage.home_habitat_container_class(item), kind)
            for level, expected in ((1, 20), (2, 30), (3, 40), (4, 60)):
                self.assertEqual(storage._container_capacity({'expansionLevel': level, 'capacity': 99999}, item), expected)
            with self.assertRaises(ValueError):
                storage._container_capacity({'expansionLevel': 5}, item)
            self.assertTrue(storage._feature_accepts(kind, self.occupants[name]))
            self.assertFalse(storage._feature_accepts(kind, items.get_item_by_name('haybale')))
            self.assertIsNone(storage.home_habitat_container_class({**item, 'name': 'unreviewed-regional-owner'}))
        self.assertIsNone(storage.home_habitat_container_class(items.get_item_by_name('animal_breeding_xwwaviary_finished')))
        self.assertEqual(sum(bool(storage.feature_container_class(row)) for row in items.get_items()), 71)
        self.assertEqual(sum(bool(storage.orchard_container_class(row)) for row in items.get_items()), 67)

    def test_each_home_habitat_fills_only_its_own_20_slots_and_keeps_authoritative_fields(self):
        for name in storage._HOME_HABITATS:
            with self.subTest(name=name):
                self.owner(name)
                item = self.occupants[name]
                self.gift(item, 21, [{'authoritative unit': [n]} for n in range(21)])
                original = copy.deepcopy(self.owner_object)
                self.store(item, numToStore=20, metadata={'forged': True})
                owner = self.owner_object
                self.assertEqual(owner['contents'], [{'itemCode': item['code'], 'numItem': 20}])
                for key in ('capacity', 'expansionLevel', 'position', 'extraDataState', 'storageMetadata'):
                    self.assertEqual(owner[key], original[key])
                self.assertEqual(self.save['userInfo']['player']['storageData']['600'][item['code']][2],
                                 [{'authoritative unit': [n]} for n in range(20)])
                self.reject(item)
                # Positive habitat slots do not create a single ordinary inventory slot.
                with self.assertRaisesRegex(ValueError, 'storage space'):
                    storage._guard_inventory_deposit(self.save, -2, 1)

    def test_habitat_anti_stuffing_clock_uses_exact_four_percent_without_shortening(self):
        item = self.occupants[self.name]
        duration = peaceful.grow_seconds(self.catalog) * 1000
        penalty = int(duration * 0.04 + 0.5)
        for planted, amount, expected in ((NOW * 1000 - 1000, 1, NOW * 1000),
                (NOW * 1000 - duration - 1, 1, NOW * 1000 - duration + penalty),
                (NOW * 1000 - 20_000_000, 3, NOW * 1000 - 20_000_000 + penalty)):
            self.owner(plantTime=planted)
            self.gift(item, amount)
            self.store(item, numToStore=amount)
            self.assertEqual(self.owner_object['plantTime'], expected)
            self.assertGreaterEqual(expected, planted)
        self.owner(plantTime=NOW * 1000 + 1)
        self.gift(item)
        self.reject(item)

    def test_base_habitat_retains_authored_eligibility_in_supported_original_contexts(self):
        item = self.occupants[self.name]
        for world in ('farm', 'england', 'fisherman', 'meadows'):
            with self.subTest(world=world):
                self.owner()
                self.save['userInfo']['currentWorldType'] = world
                self.gift(item)
                self.store(item)
                self.assertEqual(self.owner_object['contents'], [{'itemCode': item['code'], 'numItem': 1}])
        # This tests the shared storage contract, not full England/Cove UI admission.

    def test_ordinary_inventory_counts_units_independently_of_gnome_orchard_and_habitat_contents(self):
        self.save['world']['objectsArray'] += [
            {'id': 601, 'itemName': 'toolshedpink', 'className': 'StorageBuilding', 'state': 'built'},
            {'id': 602, 'itemName': 'gnomegarden_finished', 'className': 'FeatureBuilding',
                'state': 'built', 'isFullyBuilt': True, 'contents': [{'itemCode': 'HB', 'numItem': 100}]},
            {'id': 603, 'itemName': 'orchard_featurebuilding_finished', 'className': 'OrchardFeatureBuilding',
                'state': 'bare', 'contents': [{'itemCode': 'HB', 'numItem': 100}], 'plantTime': 1000}]
        self.save['userInfo']['player']['storageData']['-2'] = {'HB': [14, [], []]}
        storage._guard_inventory_deposit(self.save, -2, 1)
        with self.assertRaises(ValueError):
            storage._guard_inventory_deposit(self.save, -2, 2)
        self.save['userInfo']['player']['storageData']['600'] = {'HB': [100, [], []]}
        storage._guard_inventory_deposit(self.save, -2, 1)

    def test_wrong_item_world_id_owner_and_sources_refuse_before_loss(self):
        item = self.occupants[self.name]
        self.gift(item)
        base = copy.deepcopy(self.save)
        for field, value in (('isFullyBuilt', False), ('expansionLevel', 5),
                             ('plantTime', True), ('className', 'StorageBuilding')):
            self.save = copy.deepcopy(base)
            self.owner_object[field] = value
            self.reject(item)
        for options in ({'target': 600.5}, {'resource': 1.5}, {'origin': True},
                        {'isGift': False, 'origin': -8}, {'giftMetadataIndex': 0.5}):
            self.save = copy.deepcopy(base)
            self.reject(item, **options)
        self.save = copy.deepcopy(base)
        self.save['userInfo']['currentWorldType'] = 'rainforest'
        self.reject(item)
        self.save = copy.deepcopy(base)
        self.gift(items.get_item_by_name('haybale'))
        self.reject(items.get_item_by_name('haybale'))

    def test_overflow_or_incompatible_imported_occupants_are_recoverable_with_clock_and_metadata(self):
        hay = items.get_item_by_name('haybale')
        self.owner_object['contents'] = [{'itemCode': hay['code'], 'numItem': 50, 'opaque': {'keep': True}}]
        original = copy.deepcopy(self.owner_object)
        with redirect_stdout(io.StringIO()):
            self.assertTrue(storage.withdraw_for_placement(self.save, 'haybale', [{'isStorageWithdrawal': 600}]))
        self.assertEqual(self.owner_object['contents'], [{'itemCode': hay['code'], 'numItem': 49, 'opaque': {'keep': True}}])
        for field in ('plantTime', 'storageMetadata', 'extraDataState', 'capacity'):
            self.assertEqual(self.owner_object[field], original[field])

    def test_recognized_positive_withdrawals_preserve_disagreeing_imported_ledgers(self):
        for name in ('animal_breeding_aviary_finished', 'gnomegarden_finished',
                     'orchard_featurebuilding_finished'):
            self.owner(name)
            self.owner_object['contents'] = [{'itemCode': 'HB', 'numItem': 50}]
            self.save['userInfo']['player']['storageData']['600'] = {'HB': [1, [], [{'unit': True}]]}
            before = copy.deepcopy(self.save)
            with self.assertRaisesRegex(ValueError, 'disagrees'):
                storage.withdraw_for_placement(self.save, 'haybale', [{'isStorageWithdrawal': 600}])
            self.assertEqual(self.save, before)

    def test_storage_request_receipts_protect_all_four_stack_sources_and_request_reuse(self):
        gnome = next(item for item in items.get_items() if item.get('className') == 'Gnome'
                     and storage._feature_accepts('gnomegarden', item))
        for family in ('ordinary', 'gnome', 'orchard', 'habitat'):
            with self.subTest(family=family):
                self.setUp()
                if family == 'ordinary':
                    self.save['world']['objectsArray'] = [{'id': 601, 'itemName': 'toolshedpink',
                        'className': 'StorageBuilding', 'state': 'built'}]
                    snapshot = {'id': -2, 'className': 'StorageBuilding'}
                    target, item = -2, items.get_item_by_name('haybale')
                else:
                    name = {'gnome': 'gnomegarden_finished', 'orchard': 'orchard_featurebuilding_finished',
                            'habitat': 'animal_breeding_aviary_finished'}[family]
                    self.owner(name)
                    snapshot, target = copy.deepcopy(self.owner_object), 600
                    item = {'gnome': gnome, 'orchard': items.get_item_by_name('cherry'),
                            'habitat': self.occupants['animal_breeding_aviary_finished']}[family]
                self.gift(item, 2)
                options = {'target': target, 'storedItemName': item['name'], 'isGift': True}
                with redirect_stdout(io.StringIO()), mock.patch.object(engine, 'timestamp_now', return_value=NOW):
                    storage.store_world_item(self.save, snapshot, options, request_id=77)
                    settled = copy.deepcopy(self.save)
                    storage.store_world_item(self.save, snapshot, options, request_id=77)
                self.assertEqual(self.save, settled)
                self.assertEqual(self.save['userInfo']['player']['storageData']['-1'][item['code']][0], 1)
                with self.assertRaisesRegex(ValueError, 'reused'):
                    storage.store_world_item(self.save, snapshot, {**options, 'numToStore': 2}, request_id=77)
                self.assertEqual(self.save, settled)

    def test_legacy_foreign_inventory_and_orphan_positive_ledgers_never_supply_items(self):
        for group in (-8, -8.5, True, 700, 700.5):
            self.save['userInfo']['player']['storageData']['700'] = {'HB': [1, [], []]}
            before = copy.deepcopy(self.save)
            with self.assertRaises(ValueError):
                storage.withdraw_for_placement(self.save, 'haybale', [{'isStorageWithdrawal': group}])
            self.assertEqual(self.save, before)


class HomeHabitatWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    @property
    def save(self):
        return self.player.session('fixture-farmer')

    def prepare_habitat(self):
        path = self.write_fixture()
        self.save['userInfo']['currentWorldType'] = 'farm'
        self.save['userInfo']['player'].update(xp=100015, gold=2_000_000, cash=1000,
            storageData={'-1': {'0gG': [1, ['friend'], [{'unit': [1]}]]}, '-2': {}})
        kind = storage._HOME_HABITATS['animal_breeding_aviary_finished']
        animal = next(i for n in sorted(storage._home_habitat_storage_filters()[kind])
                      if (i := items.get_item_by_name(n)) and i.get('type') == 'animal'
                      and i.get('className') in (None, 'Animal'))
        self.save['userInfo']['player']['storageData']['-1'] = {animal['code']: [2, ['friend'], [{'unit': [1]}, {'unit': [2]}]]}
        owner = {'id': 600, 'itemName': 'animal_breeding_aviary_finished', 'className': 'FeatureBuilding',
            'state': 'built_0', 'isFullyBuilt': True, 'expansionLevel': 1, 'expansionParts': {}, 'contents': [],
            'plantTime': (NOW - 86400) * 1000, 'storageMetadata': {'opaque': [1]},
            'position': {'x': 10, 'y': 10, 'z': 0}}
        self.save['world']['objectsArray'] = [owner]
        with redirect_stdout(io.StringIO()):
            self.player.save_session('fixture-farmer')
        return path, owner, animal

    def test_habitat_store_retry_reload_and_real_duration_are_durable(self):
        path, owner, animal = self.prepare_habitat()
        packet = self.command('WorldService.performAction', ['store', copy.deepcopy(owner), [
            {'storedItemName': animal['name'], 'isGift': True, 'giftMetadataIndex': 0}]], 1)
        with mock.patch.object(engine, 'timestamp_now', return_value=NOW):
            response = self.gateway([packet])
        results = fixtures.gateway_results(self, response)
        self.assertEqual([result['errorType'] for result in results], [0], repr(results))
        saved = path.read_bytes()
        self.assertEqual(json.loads(saved)['world']['objectsArray'][0]['contents'],
                         [{'itemCode': animal['code'], 'numItem': 1}])
        with mock.patch.object(engine, 'timestamp_now', return_value=NOW):
            fixtures.gateway_results(self, self.gateway([packet]), [0])
        self.assertEqual(path.read_bytes(), saved)
        self.player.load_saves()
        self.assertEqual(self.save['world']['objectsArray'][0], json.loads(saved)['world']['objectsArray'][0])
        fixtures.gateway_results(self, self.gateway([packet]), [0])
        self.assertEqual(path.read_bytes(), saved)
        self.assertEqual(peaceful.grow_seconds(items.get_item_by_name(owner['itemName'])), 82800)


    def test_new_completed_habitat_placement_starts_first_stage_and_server_clock(self):
        path, owner, animal = self.prepare_habitat()
        self.save['world']['objectsArray'] = []
        item = items.get_item_by_name(owner['itemName'])
        self.save['userInfo']['player']['storageData']['-1'] = {item['code']: [1, ['friend'], []]}
        with redirect_stdout(io.StringIO()):
            self.player.save_session('fixture-farmer')
        incoming = {**copy.deepcopy(owner), 'id': 64000, 'tempId': -1, 'plantTime': 0,
            'expansionLevel': 4, 'capacity': 99999,
            'contents': [{'itemCode': animal['code'], 'numItem': 99}],
            'storageMetadata': {'forged': True}, 'extraDataState': {'forged': True}}
        packet = self.command('WorldService.performAction', ['place', incoming, [{'isGift': True}]], 1)
        with mock.patch.object(self.server.commands, 'timestamp_now', return_value=NOW):
            results = fixtures.gateway_results(self, self.gateway([packet]))
        self.assertEqual([r['errorType'] for r in results], [0], repr(results))
        actual = self.save['world']['objectsArray'][0]
        self.assertEqual((actual['expansionLevel'], actual['capacity'], actual['plantTime']), (1, 20, NOW * 1000))
        self.assertEqual(actual['contents'], [])
        self.assertEqual(actual['storageMetadata'], {})
        self.assertNotIn('extraDataState', actual)
        self.assertNotIn(item['code'], self.save['userInfo']['player']['storageData']['-1'])
        self.player.load_saves()
        self.assertEqual(self.save['world']['objectsArray'][0], json.loads(path.read_bytes())['world']['objectsArray'][0])

    def test_habitat_move_cannot_replace_identity_contents_or_growth_clock(self):
        path, owner, animal = self.prepare_habitat()
        snapshot = {**copy.deepcopy(owner), 'position': {'x': 20, 'y': 10, 'z': 0},
            'plantTime': 0, 'capacity': 99999, 'expansionLevel': 4,
            'contents': [{'itemCode': animal['code'], 'numItem': 99}],
            'storageMetadata': {}, 'extraDataState': {'forged': True}}
        packet = self.command('WorldService.performAction', ['move', snapshot, []], 2)
        fixtures.gateway_results(self, self.gateway([packet]), [0])
        actual = self.save['world']['objectsArray'][0]
        self.assertEqual(actual['position'], snapshot['position'])
        for field in ('plantTime', 'contents', 'storageMetadata', 'expansionLevel'):
            self.assertEqual(actual[field], owner[field])
        self.assertNotIn('capacity', actual)
        self.assertNotIn('extraDataState', actual)
        saved = path.read_bytes()
        forged = {**copy.deepcopy(actual), 'itemName': 'animal_breeding_zoo_finished'}
        packet = self.command('WorldService.performAction', ['move', forged, []], 3)
        fixtures.gateway_results(self, self.gateway([packet]), [29])
        self.assertEqual(path.read_bytes(), saved)
        self.player.load_saves()
        self.assertEqual(self.save['world']['objectsArray'][0], actual)


if __name__ == '__main__':
    unittest.main()
