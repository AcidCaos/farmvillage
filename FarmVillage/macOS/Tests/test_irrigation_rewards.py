"""Authored well placement, all reward tiers, and safe additive water balances."""
import copy
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import engine
import irrigation_rewards as irrigation
import items


class IrrigationRewardTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)

    def setUp(self):
        self.save = copy.deepcopy(self.initial)
        self.save['userInfo']['currentWorldType'] = 'farm'
        self.save['userInfo']['featureOptions']['irrigation'] = {'irrigation': {
            'waterPlots': {'farm': {'amount': 2200, 'imported': 'keep'}, 'england': {'amount': 17}}}}

    def test_all_authored_well_levels_use_original_tables(self):
        for name, expected in (
                ('bldg_irrigationwell', [50, 125, 190, 240, 280, 310]),
                ('bldg_irrigationwell_8hr', [25, 62, 95, 120, 140, 155])):
            item = items.get_item_by_name(name)
            for level, amount in enumerate(expected, 2):
                with self.subTest(name=name, level=level):
                    self.assertEqual(irrigation.reward_for_level(item, level), amount)
            for level in (0, 1, 8):
                with self.subTest(name=name, refused_level=level), self.assertRaises(ValueError):
                    irrigation.reward_for_level(item, level)

    def test_new_well_placement_uses_authored_level_and_current_clock(self):
        for name in irrigation.WELLS:
            with self.subTest(name=name):
                incoming = {'id': 71, 'itemName': name, 'className': 'FeatureBuilding',
                            'expansionLevel': 7, 'plantTime': 0, 'state': 'grown',
                            'imported': {'keep': True}}
                before = copy.deepcopy(incoming)
                actual = irrigation.initialize_placement(incoming, now=2_000_000)
                self.assertEqual((actual['expansionLevel'], actual['plantTime'], actual['state']),
                                 (2, 2_000_000_000, 'bare'))
                self.assertEqual(actual['imported'], {'keep': True})
                self.assertTrue(actual['isFullyBuilt'])
                self.assertEqual(incoming, before)

    def test_well_snapshot_cannot_add_progress_fields_absent_from_import(self):
        owned = {'id': 71, 'itemName': 'bldg_irrigationwell', 'className': 'FeatureBuilding',
                 'state': 'bare', 'plantTime': 10}
        result = irrigation.preserve_fields(owned, {**owned, 'expansionLevel': 7,
                                                     'plantTime': 0, 'capacity': 999})
        self.assertEqual(result, owned)
        with self.assertRaises(ValueError):
            irrigation.preserve_fields({'id': 71, 'itemName': 'strawberry'}, owned)

    def test_exact_generic_grant_preserves_imported_overcap_and_other_world(self):
        irrigation.grant(self.save, 'waterPlots', 50)
        store = self.save['userInfo']['featureOptions']['irrigation']['irrigation']['waterPlots']
        self.assertEqual(store['farm'], {'amount': 2250, 'imported': 'keep'})
        self.assertEqual(store['england'], {'amount': 17})

    def test_generic_grant_creates_absent_world_balance_without_losing_configuration(self):
        self.save['userInfo']['currentWorldType'] = 'australia'
        irrigation.grant(self.save, 'waterPlots', 50)
        store = self.save['userInfo']['featureOptions']['irrigation']['irrigation']['waterPlots']
        self.assertEqual(store['australia'], {'amount': 50})
        self.assertEqual(store['farm'], {'amount': 2200, 'imported': 'keep'})

    def test_malformed_reward_or_imported_balance_fails_before_mutation(self):
        for amount in (-1, True, 0.5, float('nan'), float('inf'), 2**53):
            with self.subTest(amount=amount):
                before = copy.deepcopy(self.save)
                with self.assertRaises(ValueError):
                    irrigation.grant(self.save, 'waterPlots', amount)
                self.assertEqual(self.save, before)
        store = self.save['userInfo']['featureOptions']['irrigation']['irrigation']['waterPlots']
        for amount in (-1, True, 0.5, float('inf'), 2**53):
            with self.subTest(saved=amount):
                store['farm']['amount'] = amount
                before = copy.deepcopy(self.save)
                with self.assertRaises(ValueError):
                    engine.add_water(self.save, 'waterPlots', 50)
                self.assertEqual(self.save, before)

    def test_init_resets_only_session_receipts(self):
        self.save[irrigation.REQUESTS_KEY] = {'41': {'id': 71}}
        before = copy.deepcopy(self.save)
        irrigation.start_session(self.save)
        before[irrigation.REQUESTS_KEY] = {}
        self.assertEqual(self.save, before)


if __name__ == '__main__':
    unittest.main()
