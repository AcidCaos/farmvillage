"""My Deco Studio checks against the real archived catalog, using temp farms."""
import copy
from pathlib import Path
import sys
import unittest
from unittest import mock
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import items
import ugc


class DecoStudioTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    fixture = fixtures.RuntimeFixtureTests.fixture

    def setUp(self):
        self.save = self.fixture()
        self.save['userInfo']['player']['cash'] = 100
        self.save['userInfo'].setdefault('featureOptions', {})['UGCDeco'] = {'UGCDeco': {
            'ugc_materials': {name: cap for name, cap in ugc._config()[0].items()},
            'ugc_completed': {}}}
        self.raw = {'I': '6H6', 'D': {'b': {'C': '16711680'}, 'd': {'I': '6OK'}}}

    def test_real_blueprint_charges_base_and_selected_parts_and_grants_uuid_gift(self):
        before_gold = self.save['userInfo']['player']['gold']
        result = ugc.purchase_decoration(self.save, self.raw)
        state = result['ugcItemState']
        self.assertEqual(uuid.UUID(state['U']).version, 4)
        self.assertEqual(state['D'], self.raw['D'])
        self.assertEqual(result['featureData']['ugc_materials']['ugc_deco_log'], 84)
        self.assertEqual(result['featureData']['ugc_materials']['ugc_deco_tool'], 88)
        self.assertEqual(result['featureData']['ugc_materials']['ugc_deco_chip'], 96)
        self.assertEqual(result['featureData']['ugc_materials']['ugc_deco_crew'], 18)
        self.assertEqual(result['storageData']['-1']['6H6'], [1, [], [state['U']]])
        self.assertEqual(self.save['userInfo']['player']['gold'], before_gold)
        self.assertIn('ugc_deco_shack', result['featureData']['ugc_completed'])
        self.assertEqual(ugc.validate_owned_state(self.save, state['U'], 'ugc_deco_shack'), state)

    def test_pending_purchase_retry_neither_recharges_nor_duplicates(self):
        first = ugc.purchase_decoration(self.save, self.raw)
        before = copy.deepcopy(self.save)
        second = ugc.purchase_decoration(self.save, self.raw)
        self.assertEqual(second['ugcItemState']['U'], first['ugcItemState']['U'])
        self.assertEqual(second['xpGain'], 0)
        self.assertEqual(self.save, before)

    def test_new_build_after_gift_placement_gets_another_identity(self):
        first = ugc.purchase_decoration(self.save, self.raw)
        del self.save['userInfo']['player']['storageData']['-1']['6H6']
        second = ugc.purchase_decoration(self.save, self.raw)
        self.assertNotEqual(first['ugcItemState']['U'], second['ugcItemState']['U'])
        self.assertEqual(second['featureData']['ugc_materials']['ugc_deco_log'], 68)

    def test_insufficient_materials_and_locked_blueprint_leave_state_unchanged(self):
        for raw in ({'I': '61Y'}, self.raw):
            with self.subTest(raw=raw):
                before = copy.deepcopy(self.save)
                if raw is self.raw:
                    self.save['userInfo']['featureOptions']['UGCDeco']['UGCDeco']['ugc_materials']['ugc_deco_log'] = 0
                    before = copy.deepcopy(self.save)
                with self.assertRaises(ValueError):
                    ugc.purchase_decoration(self.save, raw)
                self.assertEqual(self.save, before)

    def test_rejects_unknown_part_wrong_layer_unpaintable_color_and_invalid_name(self):
        bad = [{'I': '6H6', 'D': {'b': {'I': '6OK'}}},
               {'I': '6H6', 'D': {'w': {'I': '6OK'}}},
               {'I': '6H6', 'D': {'d': {'I': '6OK', 'C': '255'}}},
               {'I': '6H6', 'D': {'b': {'C': '-1'}}},
               {'I': '6H6', 'D': {'b': {'C': 'NaN'}}},
               {'I': '6H6', 'D': {'invented': {}}},
               {'I': '6H6', 'N': 'x' * 33}, {'I': 'not-real'}]
        for raw in bad:
            with self.subTest(raw=raw):
                before = copy.deepcopy(self.save)
                with self.assertRaises(ValueError):
                    ugc.purchase_decoration(self.save, raw)
                self.assertEqual(self.save, before)

    def test_temporary_design_preserves_all_completed_designs_and_cannot_impersonate_one(self):
        result = ugc.purchase_decoration(self.save, self.raw)
        ugc.save_temp_state(self.save, {'I': '6H6', 'D': {'b': {'C': '255'}}})
        self.assertIn(result['ugcItemState']['U'], self.save['userInfo']['ugcItemData'])
        self.assertNotIn('U', self.save['userInfo']['ugcItemData']['6H6'])
        before = copy.deepcopy(self.save)
        with self.assertRaises(ValueError):
            ugc.save_temp_state(self.save, result['ugcItemState'])
        self.assertEqual(self.save, before)

    def test_part_purchase_charges_catalog_cash_and_checks_caps_and_balance(self):
        self.save['userInfo']['featureOptions']['UGCDeco']['UGCDeco']['ugc_materials']['ugc_deco_tool'] = 1
        result = ugc.purchase_part(self.save, 'ugc_deco_tool', 2)
        self.assertEqual(result['featureData']['ugc_materials']['ugc_deco_tool'], 3)
        self.assertEqual(self.save['userInfo']['player']['cash'], 96)
        for name, count in [('ugc_deco_tool', 100), ('cow', 1), ('ugc_deco_tool', -1), ('ugc_deco_tool', 1.5)]:
            before = copy.deepcopy(self.save)
            with self.subTest(name=name, count=count), self.assertRaises(ValueError):
                ugc.purchase_part(self.save, name, count)
            self.assertEqual(self.save, before)
        self.save['userInfo']['player']['cash'] = 0
        before = copy.deepcopy(self.save)
        with self.assertRaises(ValueError):
            ugc.purchase_part(self.save, 'ugc_deco_tool', 1)
        self.assertEqual(self.save, before)

    def test_ownership_validation_cannot_substitute_other_farm_or_blueprint(self):
        result = ugc.purchase_decoration(self.save, self.raw)
        state_uuid = result['ugcItemState']['U']
        for save, name in [(self.fixture(), 'ugc_deco_shack'), (self.save, 'ugc_deco_cottage')]:
            with self.assertRaises(ValueError):
                ugc.validate_owned_state(save, state_uuid, name)

    def test_legacy_null_state_map_is_initialized_and_unsupported_modify_is_rejected(self):
        self.save['userInfo']['ugcItemData'] = None
        ugc.purchase_decoration(self.save, self.raw)
        self.assertIsInstance(self.save['userInfo']['ugcItemData'], dict)
        before = copy.deepcopy(self.save)
        with self.assertRaises(ValueError):
            ugc.purchase_decoration(self.save, self.raw, modify_id=123)
        self.assertEqual(self.save, before)

    def test_completed_blueprints_unlock_in_recovered_prerequisite_order(self):
        ugc.purchase_decoration(self.save, {'I': '6H6'})
        ugc.set_last_blueprint(self.save, 'UGCDeco', 'ugc_deco_cottage')
        self.assertEqual(ugc.feature_data(self.save)['ugc_lastEdited']['UGCDeco'], 'ugc_deco_cottage')
        ugc.purchase_decoration(self.save, {'I': '61Y'})
        ugc.set_last_blueprint(self.save, 'UGCDeco', 'ugc_deco_house')
        with self.assertRaises(ValueError):
            ugc.set_last_blueprint(self.save, 'UGCDeco', 'ugc_deco_mansion')

    def test_recycling_uses_real_tables_and_does_not_exceed_material_caps(self):
        data = self.save['userInfo']['featureOptions']['UGCDeco']['UGCDeco']
        data['ugc_materials']['ugc_deco_tool'] = 0
        data['ugc_materials']['ugc_deco_log'] = 99
        with mock.patch('ugc.random.choices', side_effect=lambda pool, **kwargs: [pool[-1]]):
            result = ugc.award_recycling(self.save, {'name': 'fixture_tree', 'type': 'tree', 'cost': '500'})
        self.assertEqual(result['ugc_materials']['ugc_deco_tool'], 4)
        self.assertEqual(result['ugc_materials']['ugc_deco_log'], 100)
        before = copy.deepcopy(self.save)
        for item in [items.get_item_by_name('ugc_deco_workshop'), items.get_item_by_name('cow'),
                     {'name': 'cheap', 'type': 'decoration', 'cost': '499'}]:
            self.assertIsNone(ugc.award_recycling(self.save, item))
        self.assertEqual(self.save, before)

    def test_results_are_detached_from_durable_state(self):
        result = ugc.purchase_decoration(self.save, self.raw)
        result['featureData']['ugc_materials']['ugc_deco_tool'] = -1
        result['ugcItemState']['D']['b']['C'] = '1'
        result['storageData']['-1']['6H6'][0] = 99
        self.assertEqual(ugc.feature_data(self.save)['ugc_materials']['ugc_deco_tool'], 88)
        self.assertEqual(self.save['userInfo']['player']['storageData']['-1']['6H6'][0], 1)
