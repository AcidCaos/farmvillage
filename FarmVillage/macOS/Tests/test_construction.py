"""Offline original-material construction checks; all writable data is temporary."""
from contextlib import ExitStack, redirect_stdout
import copy
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence  # Loads the temporary data root before any product module.
import construction
import items

PARTS = [('brick', 'K1'), ('harness', 'K2'), ('horseshoe', 'K3'), ('nail', 'K4'), ('woodenboard', 'K5')]


def upgrade(level, capacity, count, names=('brick', 'nail', 'woodenboard')):
    return {'level': str(level), 'capacity': str(capacity), 'matsNeeded': str(count * len(names)),
            'part': [{'name': name, 'need': str(count)} for name in names]}


class ConstructionTests(unittest.TestCase):
    catalog = [
        {'name': 'turkeyroost', 'code': 'zG', 'type': 'building', 'className': 'ConstructionBuilding',
         'finishedName': 'turkeyroost_finished', 'storageType': {'itemClass': 'turkeyroost_constructable'}, 'matsNeeded': '30',
         'defaultItem': {'name': 'brick', 'amount': '1'}},
        {'name': 'turkeyroost_finished', 'code': 'zH', 'type': 'building', 'className': 'TurkeyRoostBuilding',
         'storageType': {'itemClass': 'turkeyroost_finished'}, 'capacity': '20', 'storageSize': '1',
         'upgrade': [upgrade(2, 30, 15), upgrade(3, 40, 20)]},
        {'name': 'orchard', 'code': 'wM', 'type': 'building', 'className': 'OrchardConstructionBuilding',
         'finishedName': 'orchard_finished', 'storageType': {'itemClass': 'orchard_construct'}, 'matsNeeded': '30',
         'defaultItem': {'name': 'brick', 'amount': '1'}},
        {'name': 'orchard_finished', 'code': 'wN', 'type': 'building', 'className': 'OrchardBuilding',
         'storageType': {'itemClass': 'orchard'}, 'capacity': '20', 'expansion': 'superorchard_upgrade'},
        {'name': 'horsestablewhite', 'code': 'K0', 'type': 'building', 'className': 'HorseStableBuilding',
         'storageType': {'itemClass': 'horses'}, 'matsNeeded': '50', 'capacity': '20', 'storageSize': '1',
         'defaultItem': {'name': 'brick', 'amount': '1'},
         'upgrade': [upgrade(level, capacity, 10, tuple(name for name, _ in PARTS))
                     for level, capacity in [(2, 25), (3, 30), (4, 35), (5, 40)]]},
        *[{'name': name, 'code': code, 'className': 'BuildingPart', 'type': 'building', 'market': 'cash', 'cash': '1', 'cost': '100'}
          for name, code in PARTS],
        {'name': 'turkey', 'code': 'TU', 'type': 'animal', 'className': 'Animal'},
        {'name': 'cow', 'code': 'CW', 'type': 'animal', 'className': 'Animal'},
        {'name': 'xuk_sheep_pen', 'code': 'ct', 'type': 'building', 'className': 'SheepPenConstructionBuilding',
         'finishedName': 'xuk_sheep_pen_finished', 'storageType': {'itemClass': 'xuk_sheep_pen_construct'}, 'matsNeeded': '30',
         'defaultItem': {'name': 'brick', 'amount': '1'}},
        {'name': 'xuk_sheep_pen_finished', 'code': 'cv', 'type': 'building', 'className': 'FeatureBuilding',
         'storageType': {'itemClass': 'xuk_sheep_pen'}, 'capacity': '20', 'matsNeeded': '30', 'cost': '1', 'market': 'coins',
         'features': {'feature': [{'name': 'expand', 'className': 'ExpandFManager',
                                  'upgrade': [upgrade(2, 30, 15), upgrade(3, 40, 20)]}]}},
        {'name': 'vehiclepart', 'code': 'dS', 'className': 'CVehiclePart', 'market': 'cash', 'cash': '1'},
        {'name': 'xukcombineconstruct', 'code': 'ko', 'type': 'building',
         'className': 'CombineChassisConstructionBuilding', 'finishedName': 'xukcombine',
         'storageType': {'itemClass': 'combine_construct'}, 'matsNeeded': '40',
         'defaultItem': {'name': 'vehiclepart', 'amount': '1'}},
        {'name': 'xukcombine', 'code': 'kp', 'type': 'vehicle', 'className': 'Combine'},
        {'name': 'xukgarage', 'code': 'kn', 'type': 'building', 'className': 'GarageConstructionBuilding',
         'finishedName': 'xukgarage_finished', 'storageType': {'itemClass': 'garage_construct'}, 'matsNeeded': '30',
         'defaultItem': {'name': 'brick', 'amount': '1'}},
        {'name': 'xukgarage_finished', 'code': 'kv', 'type': 'building', 'className': 'GarageBuilding',
         'storageType': {'itemClass': 'garage'}},
    ]

    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.object(items, '_cached_items', {'settings': {'items': {'item': self.catalog}}}))
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.save = {'world': {'objectsArray': []}, 'userInfo': {'player': {'gold': 10000, 'cash': 100, 'storageData': {}}},
                     'importedSave': {'keep': ['all', 'fields']}}
        self.player = self.save['userInfo']['player']

    def site(self, name='turkeyroost', ident=0, **extra):
        item = items.get_item_by_name(name)
        obj = {'id': ident, 'itemName': name, 'className': item['className'], 'isFullyBuilt': name.endswith('_finished'),
               'state': 'built' if name.endswith('_finished') else 'construction', 'contents': [],
               'position': {'x': 7, 'y': 9}, 'plantTime': 1000000,
               'imported': {'keep': [1, 2]}}
        obj.update(extra); self.save['world']['objectsArray'].append(obj)
        return obj

    def gift(self, name, amount=1, group=-1):
        code = items.get_item_by_name(name)['code']
        self.save['userInfo']['player']['storageData'].setdefault(str(group), {})[code] = [amount, ['senderA', 'senderB'],
            [{'unit': index} for index in range(amount)], {'importedEntry': 'keep'}]

    def snapshot(self, obj):
        return {'id': obj['id'], 'itemName': obj['itemName'], 'className': obj['className'], 'contents': []}

    def apply(self, obj, name, amount=1, **options):
        return construction.store_for_game(self.save, self.snapshot(obj),
            {'storedItemName': name, 'numToStore': amount, 'isGift': True, **options})

    def complete_except(self, obj, last='brick'):
        requirements = construction._initial_requirements(items.get_item_by_name(obj['itemName']))
        obj['contents'] = [{'itemCode': code, 'numItem': needed - (item['name'] == last), 'importedRow': 'keep'}
                           for code, (item, needed) in requirements.items()]
        return requirements

    def test_primary_catalog_matches_the_supported_contract(self):
        # Read the archived AMF directly: never load or write the product cache.
        catalog = items._decode_items((ROOT / 'xml/gz/v855038/items_opt.amf').read_bytes())
        by_name = {item['name']: item for item in catalog['settings']['items']['item']}
        for name in ('turkeyroost', 'orchard', 'horsestablewhite', 'xukgarage'):
            requirements = construction._initial_requirements(by_name[name])
            expected = 50 if name == 'horsestablewhite' else 30
            self.assertEqual(sum(count for _, count in requirements.values()), expected)
            self.assertTrue(all(count == 10 for _, count in requirements.values()))
        self.assertEqual(by_name['turkeyroost_finished']['upgrade'], self.catalog[1]['upgrade'])
        self.assertEqual(by_name['horsestablewhite']['upgrade'], self.catalog[4]['upgrade'])
        pen = by_name['xuk_sheep_pen_finished']
        self.assertEqual((pen['cost'], pen['market'], pen['className']), ('1', 'coins', 'FeatureBuilding'))
        for current, expected_level, capacity, count in [(1, 2, 30, 15), (2, 3, 40, 20)]:
            level, size, requirements = construction._next_upgrade({'expansionLevel': current}, pen)
            self.assertEqual((level, size), (expected_level, capacity))
            self.assertEqual({code: needed for code, (_, needed) in requirements.items()}, {'K1': count, 'K4': count, 'K5': count})
        for name in ('xuk_sheep_pen', 'xuk_sheep_pen_finished'):
            self.assertTrue(all(row['need'] == '0' for row in construction._storage_config()[
                by_name[name]['storageType']['itemClass']]['itemName']))
            requirements = construction._initial_requirements(by_name[name])
            self.assertEqual({code: needed for code, (_, needed) in requirements.items()},
                             {'K1': 10, 'K4': 10, 'K5': 10})
        requirements = construction._initial_requirements(by_name['xukcombineconstruct'])
        self.assertEqual({code: needed for code, (_, needed) in requirements.items()}, {'dS': 40})
        for name, code in PARTS:
            self.assertEqual((by_name[name]['code'], by_name[name]['cash'], by_name[name]['market']), (code, '1', 'cash'))

    def test_supported_material_counts_use_base_catalog_in_both_clients(self):
        # StorageBuilding.getTunedPartRequirement11971 multiplies need by
        # double-pool132(1.2) under the smart cohort. Its personalized server
        # state is unrecovered, so both entry points must show base counts.
        requirements = construction._initial_requirements(items.get_item_by_name('turkeyroost'))
        self.assertEqual({code: needed for code, (_, needed) in requirements.items()}, {'K1': 10, 'K4': 10, 'K5': 10})
        for name in ('play.html', 'ruffle.html'):
            with self.subTest(template=name):
                template = (ROOT / 'templates' / name).read_text()
                self.assertRegex(template, r'"fv_smartbuildable"\s*:\s*0\s*,')
                # Dynamic part support still supplies catalog requirements
                # and ExpandFManager updates; only personalization is off.
                self.assertRegex(template, r'"fv_dynamic_part_requirements_refactor"\s*:\s*1\s*,')

    def test_partial_material_uses_real_gifts_and_preserves_metadata(self):
        obj = self.site(); self.gift('brick', 3)
        self.apply(obj, 'brick', 2)
        obj = self.save['world']['objectsArray'][0]
        data = self.save['userInfo']['player']['storageData']
        self.assertFalse(obj['isFullyBuilt']); self.assertEqual(obj['state'], 'construction')
        self.assertEqual(obj['contents'], [{'itemCode': 'K1', 'numItem': 2}])
        self.assertEqual(data['0']['K1'], [2, ['senderA'], [{'unit': 0}, {'unit': 1}], {'importedEntry': 'keep'}])
        self.assertEqual(data['-1']['K1'], [1, ['senderB'], [{'unit': 2}], {'importedEntry': 'keep'}])
        self.assertEqual(obj['imported'], {'keep': [1, 2]})
        self.assertEqual(self.save['importedSave'], {'keep': ['all', 'fields']})
        self.assertEqual(self.save['userInfo']['player']['cash'], 100)
        self.assertEqual(construction.take_response(self.save), {})
        self.assertNotIn('_constructionResponse', self.save)

    def test_sparse_metadata_is_not_duplicated_and_conflicting_tails_are_atomic(self):
        obj = self.site(); self.gift('brick', 5)
        source = self.save['userInfo']['player']['storageData']['-1']['K1']
        source[2] = [{'sparse': 'keep with source'}]
        self.apply(obj, 'brick')
        data = self.save['userInfo']['player']['storageData']
        self.assertEqual(data['-1']['K1'][2], [{'sparse': 'keep with source'}])
        self.assertEqual(data['0']['K1'][2], [])
        obj = self.save['world']['objectsArray'][0]
        data['-1']['K1'][3] = {'different': 'imported metadata'}
        before = copy.deepcopy(self.save)
        with self.assertRaisesRegex(ValueError, 'different imported metadata'):
            self.apply(obj, 'brick')
        self.assertEqual(self.save, before)

    def test_classic_final_material_transforms_same_object_once(self):
        for name, finished in [('turkeyroost', 'turkeyroost_finished'), ('orchard', 'orchard_finished'),
                               ('xukgarage', 'xukgarage_finished')]:
            with self.subTest(name=name):
                self.save['world']['objectsArray'] = []; self.save['userInfo']['player']['storageData'] = {}
                obj = self.site(name); self.complete_except(obj); self.gift('brick', 2)
                raw = self.snapshot(obj); before = copy.deepcopy(obj)
                self.assertEqual(self.apply(obj, 'brick'), {'finishedName': finished})
                built = self.save['world']['objectsArray'][0]
                self.assertEqual((built['id'], built['itemName'], built['isFullyBuilt'], built['state']), (0, finished, True, 'built'))
                self.assertEqual(built['position'], before['position']); self.assertEqual(built['plantTime'], 1000000)
                self.assertTrue(all(row['numItem'] == 0 and row['importedRow'] == 'keep' for row in built['contents']))
                self.assertEqual(self.save['userInfo']['player']['storageData']['0'], {})
                self.assertEqual(construction.take_response(self.save), {'finishedName': finished})
                after = copy.deepcopy(self.save)
                self.assertEqual(construction.store_for_game(self.save, raw, {'storedItemName': 'brick', 'isGift': True}), {'finishedName': finished})
                construction.take_response(self.save)
                self.assertEqual(self.save, after)

    def test_stable_requires_all_five_exact_material_counts(self):
        obj = self.site('horsestablewhite'); self.complete_except(obj, 'horseshoe'); self.gift('horseshoe')
        self.apply(obj, 'horseshoe')
        stable = self.save['world']['objectsArray'][0]
        self.assertTrue(stable['isFullyBuilt']); self.assertEqual(stable['itemName'], 'horsestablewhite')
        self.assertEqual(stable['expansionLevel'], 1); self.assertEqual(stable['state'], 'built')
        self.assertTrue(all(row['numItem'] == 0 for row in stable['contents']))

    def test_finished_building_expansion_consumes_only_its_current_parts(self):
        obj = self.site('turkeyroost_finished', expansionLevel=1,
                        expansionParts={'K1': 14, 'K4': 15, 'K5': 15, 'legacy': {'keep': True}},
                        contents=[{'itemCode': 'TU', 'numItem': 2, 'importedOccupant': 'keep'}])
        self.gift('brick', 2)
        self.apply(obj, 'brick')
        expanded = self.save['world']['objectsArray'][0]
        self.assertEqual((expanded['expansionLevel'], expanded['capacity']), (2, 30))
        self.assertEqual(expanded['expansionParts'], {'legacy': {'keep': True}})
        self.assertEqual(expanded['contents'], obj['contents'])
        self.assertEqual(expanded['plantTime'], 1000000)
        self.assertEqual(self.save['userInfo']['player']['storageData']['-1']['K1'][0], 1)
        # The next stage requires 20 of each; the previous stage's counts cannot carry over.
        self.apply(expanded, 'brick')
        self.assertEqual(self.save['world']['objectsArray'][0]['expansionParts']['K1'], 1)
        self.assertEqual(self.save['world']['objectsArray'][0]['expansionLevel'], 2)

    def test_stable_expands_to_catalog_capacity_and_stops_at_level_five(self):
        obj = self.site('horsestablewhite', isFullyBuilt=True, state='built', expansionLevel=4,
                        expansionParts={code: 9 if name == 'brick' else 10 for name, code in PARTS})
        self.gift('brick', 2); self.apply(obj, 'brick')
        obj = self.save['world']['objectsArray'][0]
        self.assertEqual((obj['expansionLevel'], obj['capacity']), (5, 40))
        before = copy.deepcopy(self.save)
        with self.assertRaisesRegex(ValueError, 'no further'): self.apply(obj, 'brick')
        self.assertEqual(self.save, before)

    def test_exact_part_purchase_and_insufficient_balance_are_atomic(self):
        obj = self.site(); options = {'storedItemName': 'nail', 'numToStore': 4, 'resource': -1, 'currency': 'cash'}
        construction.store_for_game(self.save, self.snapshot(obj), options)
        self.assertEqual(self.save['userInfo']['player']['cash'], 96)
        self.assertEqual(self.save['userInfo']['player']['gold'], 10000)
        obj = self.save['world']['objectsArray'][0]
        self.save['userInfo']['player']['cash'] = 0
        before = copy.deepcopy(self.save)
        with self.assertRaisesRegex(ValueError, 'Not enough cash'):
            construction.store_for_game(self.save, self.snapshot(obj), options)
        self.assertEqual(self.save, before)

    def test_inventory_and_world_id_zero_sources(self):
        obj = self.site(ident=4); self.gift('brick', 2, group=-2)
        self.apply(obj, 'brick', 2, isGift=False, cameFromLocation=-2)
        obj = self.save['world']['objectsArray'][0]
        self.save['world']['objectsArray'].append({'id': 0, 'itemName': 'nail', 'className': 'BuildingPart', 'imported': 'source'})
        self.apply(obj, 'nail', isGift=False, resource=0)
        self.assertEqual(len(self.save['world']['objectsArray']), 1)
        self.assertEqual(self.save['userInfo']['player']['storageData']['4']['K4'][2][0]['imported'], 'source')
        self.assertNotIn('K1', self.save['userInfo']['player']['storageData']['-2'])

    def test_forged_progress_is_ignored_and_metadata_mismatch_rolls_back(self):
        obj = self.site(); self.gift('brick')
        raw = {**self.snapshot(obj), 'isFullyBuilt': True, 'expansionLevel': 99, 'capacity': 999,
               'expansionParts': {'K1': 999}, 'contents': [{'itemCode': 'K5', 'numItem': 999}]}
        construction.store_for_game(self.save, raw, {'storedItemName': 'brick', 'isGift': True})
        obj = self.save['world']['objectsArray'][0]
        self.assertFalse(obj['isFullyBuilt']); self.assertNotIn('capacity', obj); self.assertNotIn('expansionLevel', obj)
        self.assertEqual(obj['contents'], [{'itemCode': 'K1', 'numItem': 1}])
        obj['contents'][0]['numItem'] = 9; self.gift('nail')
        before = copy.deepcopy(self.save)
        with self.assertRaisesRegex(ValueError, 'disagree'): self.apply(obj, 'nail')
        self.assertEqual(self.save, before)

    def test_invalid_material_quantity_source_and_overfill_preserve_save(self):
        obj = self.site(); self.gift('brick', 20); self.gift('harness')
        for name, amount, options in [('brick', 11, {}), ('brick', True, {}), ('brick', float('nan'), {}),
                                      ('harness', 1, {}), ('brick', 1, {'storedItemCode': 'K4'}),
                                      ('brick', 1, {'cameFromLocation': -99, 'isGift': False}),
                                      ('brick', 1, {'target': 23}), ('brick', 1, {'giftMetadataIndex': 99})]:
            with self.subTest(name=name, amount=amount, options=options):
                before = copy.deepcopy(self.save)
                with self.assertRaises(ValueError): self.apply(obj, name, amount, **options)
                self.assertEqual(self.save, before)

    def test_unsupported_contents_and_catalog_shape_fail_before_charging(self):
        obj = self.site(contents=[{'itemCode': 'CW', 'numItem': 1, 'legacy': 'keep'}]); self.gift('brick')
        before = copy.deepcopy(self.save)
        with self.assertRaisesRegex(ValueError, 'Unload unsupported'): self.apply(obj, 'brick')
        self.assertEqual(self.save, before)
        obj['contents'] = []; self.save['world']['objectsArray'] = [obj]
        with mock.patch.object(construction, '_initial_requirements', side_effect=ValueError('Unsupported catalog')):
            before = copy.deepcopy(self.save)
            with self.assertRaisesRegex(ValueError, 'Unsupported catalog'): self.apply(obj, 'brick')
            self.assertEqual(self.save, before)

    def test_finished_orchard_does_not_eat_replacement_upgrade_parts(self):
        obj = self.site('orchard_finished'); self.gift('brick')
        before = copy.deepcopy(self.save)
        with self.assertRaisesRegex(ValueError, 'no further'): self.apply(obj, 'brick')
        self.assertEqual(self.save, before)
        self.assertIsNone(self.apply(obj, 'turkey'))
        self.assertEqual(self.save, before)

    def test_progress_field_protection_and_placement_initialization_are_detached(self):
        obj = self.site('horsestablewhite', expansionLevel=2, expansionParts={'K1': 3}, capacity=25)
        incoming = {**self.snapshot(obj), 'isFullyBuilt': True, 'expansionLevel': 50, 'expansionParts': {}, 'capacity': 999}
        before = copy.deepcopy(incoming); protected = construction.preserve_fields(obj, incoming)
        for field in construction._PROGRESS_FIELDS:
            if field in obj: self.assertEqual(protected[field], obj[field])
        self.assertEqual(incoming, before)
        protected['expansionParts']['K1'] = 999; self.assertEqual(obj['expansionParts']['K1'], 3)
        initialized = construction.initialize_placement(incoming)
        self.assertFalse(initialized['isFullyBuilt']); self.assertEqual(initialized['expansionParts'], {})
        self.assertEqual(initialized['contents'], [{'itemCode': 'K1', 'numItem': 1}]); self.assertEqual(initialized['expansionLevel'], 1)
        self.assertNotIn('capacity', initialized); self.assertEqual(incoming, before)

    def test_finished_sheep_pen_expansions_preserve_parents_and_reach_catalog_capacity(self):
        obj = self.site('xuk_sheep_pen_finished', expansionLevel=1,
            expansionParts={'K1': 14, 'K4': 15, 'K5': 15}, capacity=20,
            contents=[{'itemCode': 'CW', 'numItem': 1, 'dna': 'keep'}],
            storageMetadata={'CW:original': ['keep']}, extraDataState={'breedingQueue': [None], 'breedHistory': {'keep': 1}})
        self.save['userInfo']['player']['storageData']['0'] = {'CW': [1, ['parent'], [{'dna': 'keep'}]]}
        self.gift('brick', 2)
        parents = copy.deepcopy(self.save['userInfo']['player']['storageData']['0'])
        self.assertEqual(self.apply(obj, 'brick'), {})
        pen = self.save['world']['objectsArray'][0]
        self.assertEqual((pen['expansionLevel'], pen['capacity']), (2, 30))
        self.assertEqual(pen['storageMetadata'], {'CW:original': ['keep']})
        self.assertEqual(pen['extraDataState'], obj['extraDataState'])
        self.assertEqual(pen['contents'], obj['contents'])
        self.assertEqual(self.save['userInfo']['player']['storageData']['0'], parents)
        pen['expansionParts'].update(K1=20, K4=20, K5=19)
        self.gift('woodenboard', 2)
        self.apply(pen, 'woodenboard')
        pen = self.save['world']['objectsArray'][0]
        self.assertEqual((pen['expansionLevel'], pen['capacity']), (3, 40))
        before = copy.deepcopy(self.save)
        with self.assertRaisesRegex(ValueError, 'no further'):
            self.apply(pen, 'woodenboard')
        self.assertEqual(self.save, before)

    def test_recovered_sheep_pen_initial_materials_consume_only_required_units(self):
        obj = self.site('xuk_sheep_pen'); self.gift('brick')
        initialized = construction.initialize_placement(obj)
        self.assertEqual(initialized['contents'], [{'itemCode': 'K1', 'numItem': 1}])
        self.complete_except(obj)
        raw = self.snapshot(obj)
        self.assertEqual(self.apply(obj, 'brick'), {'finishedName': 'xuk_sheep_pen_finished'})
        self.assertNotIn('K1', self.save['userInfo']['player']['storageData']['-1'])
        before = copy.deepcopy(self.save)
        self.assertEqual(construction.store_for_game(self.save, raw, {'storedItemName': 'brick', 'isGift': True}),
                         {'finishedName': 'xuk_sheep_pen_finished'})
        self.assertEqual(self.save, before)
        latest = construction.initialize_placement({'id': 1, 'itemName': 'xuk_sheep_pen_finished',
            'isFullyBuilt': False, 'expansionLevel': 99, 'expansionParts': {'K1': 999}})
        self.assertTrue(latest['isFullyBuilt']); self.assertEqual(latest['expansionLevel'], 1)
        self.assertEqual(latest['expansionParts'], {}); self.assertEqual(latest['contents'], [])

    def test_combine_uses_catalog_default_and_final_part_retry_preserves_inventory(self):
        obj = self.site('xukcombineconstruct')
        initialized = construction.initialize_placement(obj)
        self.assertEqual(initialized['contents'], [{'itemCode': 'dS', 'numItem': 1}])
        obj['contents'] = [{'itemCode': 'dS', 'numItem': 39}]
        self.gift('vehiclepart', 2)
        raw = self.snapshot(obj)
        self.assertEqual(self.apply(obj, 'vehiclepart'), {'finishedName': 'xukcombine'})
        built = self.save['world']['objectsArray'][0]
        self.assertEqual((built['itemName'], built['className'], built['isFullyBuilt']), ('xukcombine', 'Combine', True))
        self.assertEqual(self.save['userInfo']['player']['storageData']['-1']['dS'][0], 1)
        before = copy.deepcopy(self.save)
        self.assertEqual(construction.store_for_game(self.save, raw, {'storedItemName': 'vehiclepart', 'isGift': True}),
                         {'finishedName': 'xukcombine'})
        self.assertEqual(self.save, before)

    def test_england_materials_use_only_active_inventory(self):
        self.save['userInfo']['currentWorldType'] = 'england'
        obj = self.site('xuk_sheep_pen')
        self.gift('brick', 2, group=-2); self.gift('brick', 2, group=-8)
        before = copy.deepcopy(self.save)
        with self.assertRaisesRegex(ValueError, 'active farm inventory'):
            self.apply(obj, 'brick', isGift=False, cameFromLocation=-2)
        self.assertEqual(self.save, before)
        self.apply(obj, 'brick', isGift=False, cameFromLocation=-8)
        self.assertEqual(self.save['userInfo']['player']['storageData']['-8']['K1'][0], 1)
        self.assertEqual(self.save['userInfo']['player']['storageData']['-2']['K1'][0], 2)


if __name__ == '__main__':
    unittest.main()
