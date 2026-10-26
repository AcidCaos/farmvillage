"""Regression boundaries where independently restored storage lanes overlap."""
from contextlib import redirect_stdout
import copy
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence  # Isolate all mutable data before runtime imports.
import test_w01_containers as home
import engine
import items
import storage


class IntegratedStorageTests(unittest.TestCase):
    setUpClass = classmethod(home.HomeContainerBoundaryTests.setUpClass.__func__)
    setUp = home.HomeContainerBoundaryTests.setUp
    owner = home.HomeContainerBoundaryTests.owner
    owner_object = home.HomeContainerBoundaryTests.owner_object
    gift = home.HomeContainerBoundaryTests.gift

    def test_shipping_selects_one_exact_contract_and_refuses_cross_pairs(self):
        for current, source, lane in (('farm', -8, 'england'), ('england', -2, 'england'),
                ('farm', -16, 'meadows'), ('meadows', -2, 'meadows'),
                ('farm', -9, 'cove'), ('fisherman', -2, 'cove')):
            with self.subTest(current=current, source=source), mock.patch(
                    'storage._guard_active_world', return_value=current), mock.patch(
                    'england_shipping.guard_transfer') as england, mock.patch(
                    'meadows_storage.guard_shipping') as meadows, mock.patch(
                    'cove_shipping.guard_source') as cove:
                self.assertEqual(storage._guard_shipping(self.save, source), lane)
                for name, guard in (('england', england), ('meadows', meadows), ('cove', cove)):
                    self.assertEqual(guard.call_count, int(name == lane))
        for current, source in (('england', -16), ('meadows', -9), ('fisherman', -8), ('rainforest', -2)):
            with self.subTest(current=current, source=source), mock.patch(
                    'storage._guard_active_world', return_value=current), self.assertRaises(ValueError):
                storage._guard_shipping(self.save, source)

    def test_classic_store_does_not_run_home_habitat_clock(self):
        self.owner('horsestablewhite', plantTime=1234567890000)
        horse = items.get_item_by_name('horse_black')
        self.gift(horse, 2, [{'name': 'Stored classic horse'}, {'name': 'Second'}])
        original = copy.deepcopy(self.owner_object)
        with redirect_stdout(io.StringIO()), mock.patch.object(
                storage, '_home_habitat_store_clock', side_effect=AssertionError('Home-only clock leaked')):
            storage.store_world_item(self.save, copy.deepcopy(original), {
                'target': 600, 'storedItemName': horse['name'], 'isGift': True}, request_id=8)
        self.assertEqual(self.owner_object['plantTime'], original['plantTime'])
        self.assertEqual(self.save['userInfo']['player']['storageData']['600'][horse['code']][2],
                         [{'name': 'Stored classic horse'}])

    def test_namespaced_store_retry_survives_new_session_without_second_clock_penalty(self):
        item = self.occupants['animal_breeding_aviary_finished']
        self.gift(item, 3)
        snapshot = copy.deepcopy(self.owner_object)
        packet = {'target': 600, 'storedItemName': item['name'], 'isGift': True}
        self.save['_meadowsStorage'] = {'sessionID': 'first-session'}
        with redirect_stdout(io.StringIO()), mock.patch.object(engine, 'timestamp_now', return_value=home.NOW):
            storage.store_world_item(self.save, copy.deepcopy(snapshot), packet, request_id=('first-session', 7))
            storage.start_session(self.save)
            self.save['_meadowsStorage']['sessionID'] = 'second-session'
            accepted = copy.deepcopy(self.save)
            storage.store_world_item(self.save, copy.deepcopy(snapshot), packet, request_id=('first-session', 7))
            self.assertEqual(self.save, accepted)
            with self.assertRaisesRegex(ValueError, 'stale'):
                storage.store_world_item(self.save, copy.deepcopy(snapshot), packet, request_id=('first-session', 8))
            storage.store_world_item(self.save, copy.deepcopy(snapshot), packet, request_id=('second-session', 7))
        self.assertEqual(self.save['userInfo']['player']['storageData']['-1'][item['code']][0], 1)

    def test_bad_store_identity_never_aliases_a_real_container(self):
        item = self.occupants['animal_breeding_aviary_finished']
        self.gift(item, 2)
        for field, value in (('target', True), ('resource', 0.5), ('origin', -1.25),
                             ('cameFromLocation', float('nan'))):
            with self.subTest(field=field, value=value):
                packet = {'target': 600, 'storedItemName': item['name'], 'isGift': True, field: value}
                before = copy.deepcopy(self.save)
                with self.assertRaises(ValueError):
                    storage.store_world_item(self.save, copy.deepcopy(self.owner_object), packet, request_id=9)
                self.assertEqual(self.save, before)


if __name__ == '__main__':
    unittest.main()
