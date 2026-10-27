"""Paid building validation, rollback and material accounting without UI mocks."""
import copy
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_construction as legacy
import construction
import building_harvest
import game_settings
import irrigation_rewards
import storage
import items
import paid_buildings as paid


class PaidBuildingsTests(unittest.TestCase):
    catalog = legacy.ConstructionTests.catalog
    setUp = legacy.ConstructionTests.setUp
    site = legacy.ConstructionTests.site
    snapshot = legacy.ConstructionTests.snapshot

    def perform(self, action, obj, options=None, sequence=None):
        result = paid.perform(self.save, action, self.snapshot(obj), [options or {}], request_id=sequence)
        self.assertEqual(paid.take_response(self.save), result)
        return result

    def reject(self, action, obj, options=None, **kwargs):
        before = copy.deepcopy(self.save)
        with self.assertRaises(ValueError):
            paid.perform(self.save, action, self.snapshot(obj), [options or {}], **kwargs)
        self.assertEqual(self.save, before)

    def test_initial_completion_preserves_metadata_and_only_purchases_missing_units(self):
        obj = self.site()
        obj['contents'] = [{'itemCode': 'K1', 'numItem': 9, 'imported': 'keep'},
                           {'itemCode': 'K4', 'numItem': 10}, {'itemCode': 'K5', 'numItem': 8}]
        self.assertEqual(self.perform('CompleteNow', obj, {'partName': None, 'isGift': False}),
                         {'id': 0, 'finishedName': 'turkeyroost_finished'})
        built = self.save['world']['objectsArray'][0]
        self.assertEqual(built['itemName'], 'turkeyroost_finished')
        self.assertEqual((built['state'], built['isFullyBuilt']), ('built', True))
        self.assertEqual(built['contents'][0]['imported'], 'keep')
        self.assertTrue(all(row['numItem'] == 0 for row in built['contents']))
        self.assertEqual(self.save['userInfo']['player']['cash'], 97)
        self.assertEqual(built['imported'], {'keep': [1, 2]})
        self.assertEqual(built['plantTime'], 1000000)

    def test_exact_next_expansion_ignores_optimistic_snapshot(self):
        obj = self.site('turkeyroost_finished', expansionLevel=1, capacity=20,
                        expansionParts={'K1': 13, 'K4': 15, 'K5': 15, 'legacy': {'keep': True}},
                        contents=[{'itemCode': 'TU', 'numItem': 1, 'imported': 'occupant'}])
        raw = {**self.snapshot(obj), 'expansionLevel': 99, 'capacity': 999, 'contents': []}
        paid.perform(self.save, 'ExpandWithCurrency', raw, [{}], request_id=1)
        paid.take_response(self.save)
        expanded = self.save['world']['objectsArray'][0]
        self.assertEqual((expanded['expansionLevel'], expanded['capacity']), (2, 30))
        self.assertEqual(expanded['expansionParts'], {'legacy': {'keep': True}})
        self.assertEqual(expanded['contents'], obj['contents'])
        self.assertEqual(self.save['userInfo']['player']['cash'], 98)

    def test_all_horse_stable_expansions_use_original_capacity_and_stop_at_maximum(self):
        obj = self.site('horsestablewhite', isFullyBuilt=True, state='built', expansionLevel=1)
        self.player['cash'] = 250
        for level, capacity in ((2, 25), (3, 30), (4, 35), (5, 40)):
            self.perform('CompleteNow', obj)
            obj = self.save['world']['objectsArray'][0]
            self.assertEqual((obj['expansionLevel'], obj['capacity']), (level, capacity))
        self.assertEqual(self.save['userInfo']['player']['cash'], 50)
        self.reject('CompleteNow', obj)

    def test_selected_part_never_fills_or_charges_other_parts(self):
        obj = self.site('turkeyroost_finished', expansionLevel=1,
                        expansionParts={'K1': 13, 'K4': 10, 'K5': 10})
        self.perform('CompleteNow', obj, {'partName': 'brick', 'isGift': False})
        target = self.save['world']['objectsArray'][0]
        self.assertEqual(target['expansionParts'], {'K1': 15, 'K4': 10, 'K5': 10})
        self.assertEqual(target['expansionLevel'], 1)
        self.assertEqual(self.save['userInfo']['player']['cash'], 98)
        self.reject('CompleteNow', target, {'partName': 'brick'})
        self.reject('CompleteNow', target, {'partName': 'brick', 'isGift': True})

    def test_mixed_authored_currencies_are_atomic_and_preserve_opaque_currency_fields(self):
        # The original expansion price algorithm groups each missing material
        # by its own market; a later insufficient group rolls back all groups.
        catalog = copy.deepcopy(self.catalog)
        next(row for row in catalog if row['name'] == 'brick').update(market='coconuts', cost='3')
        next(row for row in catalog if row['name'] == 'nail').update(market='cash', cash='2')
        with mock.patch.object(items, '_cached_items', {'settings': {'items': {'item': catalog}}}):
            obj = self.site('turkeyroost_finished', expansionLevel=1,
                            expansionParts={'K1': 13, 'K4': 14, 'K5': 15})
            self.player['worldCurrencies'] = {'coconuts': {'total': 6, 'earned': 44, 'opaque': [1]},
                                               'trowels': {'total': 9}}
            self.player['cash'] = 1
            self.reject('ExpandWithCurrency', obj)
            self.player['cash'] = 2
            self.perform('ExpandWithCurrency', obj)
        player = self.save['userInfo']['player']
        self.assertEqual(player['cash'], 0)
        self.assertEqual(player['gold'], 10000)
        self.assertEqual(player['worldCurrencies'], {'coconuts': {'total': 0, 'earned': 44, 'opaque': [1]},
                                                     'trowels': {'total': 9}})

    def test_rejected_counts_options_funds_identity_and_harvest_leave_save_unchanged(self):
        obj = self.site('turkeyroost_finished', expansionLevel=1, expansionParts={'K1': 16})
        self.reject('CompleteNow', obj)
        obj['expansionParts'] = {}
        for options in ({'isGift': 1}, {'currency': 'coins'}, {'price': 0}, {'partName': []}):
            self.reject('CompleteNow', obj, options)
        self.player['cash'] = 1
        self.reject('CompleteNow', obj)
        self.reject('HarvestReadyNow', obj)
        self.reject('upgradeBuilding', obj)
        self.save['world']['objectsArray'].append(copy.deepcopy(obj))
        self.reject('CompleteNow', obj)

    def test_receipt_replay_reload_eviction_and_login_reset(self):
        obj = self.site('turkeyroost_finished', expansionLevel=1, expansionParts={'K1': 13, 'K4': 15, 'K5': 15})
        raw = self.snapshot(obj)
        result = self.perform('CompleteNow', obj, sequence=10)
        before = copy.deepcopy(self.save)
        self.assertEqual(paid.perform(self.save, 'CompleteNow', raw, [{}], request_id=10), result)
        paid.take_response(self.save)
        self.assertEqual(self.save, before)
        import json
        self.save = json.loads(json.dumps(self.save))
        self.assertEqual(paid.perform(self.save, 'CompleteNow', raw, [{}], request_id=10), result)
        paid.take_response(self.save)
        with self.assertRaises(ValueError):
            paid.perform(self.save, 'CompleteNow', raw, [{'partName': 'brick'}], request_id=10)
        with self.assertRaises(ValueError):
            paid.perform(self.save, 'CompleteNow', raw, [{}], request_id=9)
        paid.start_session(self.save)
        self.assertNotIn(paid.REQUESTS_KEY, self.save)
        self.assertNotIn(paid.RESPONSE_KEY, self.save)

    def test_first_world_action_marker_is_accepted_without_trusting_extra_options(self):
        obj = self.site('turkeyroost_finished', expansionLevel=1, expansionParts={'K1': 14, 'K4': 15, 'K5': 15})
        paid.perform(self.save, 'CompleteNow', self.snapshot(obj),
                     [{'partName': None, 'isGift': False}, {'firstWA': True}])
        self.assertEqual(self.save['userInfo']['player']['cash'], 99)


class PaidLegacyCatalogTests(unittest.TestCase):
    """Pin recovered families to the archived catalog, without product caches."""
    @classmethod
    def setUpClass(cls):
        raw = items._decode_items((Path(__file__).resolve().parents[2] / 'xml/gz/v855038/items_opt.amf').read_bytes())
        names = {'xukhorsestable_finished', 'horsestablewhite', 'brick', 'harness',
                 'horseshoe', 'nail', 'woodenboard', 'bottle', 'blanket',
                 'nurserybarn', 'nurserybarn_finished', 'nurserybarn_finished_complete',
                 'pigpen', 'pigpen_finished', 'pigpenv2_finished',
                 'foal_gray', 'pigpen_male_light_green', 'herbgarden',
                 'part_claypot', 'part_specialsoil', 'part_peatpellet',
                 *irrigation_rewards.WELLS, 'part_redbricks', 'part_waterpail', 'part_rope',
                 *building_harvest.HERBS, *(name + '_seedpackage' for name in building_harvest.HERBS)}
        cls.catalog = [row for row in raw['settings']['items']['item'] if row['name'] in names]
        cls.farming = game_settings._decode_farming_entries(
            (Path(__file__).resolve().parents[2] / 'xml/gz/v855098/gameSettingsCMS.xml.gz').read_bytes())

    def setUp(self):
        self.patcher = mock.patch.object(items, '_cached_items', {'settings': {'items': {'item': self.catalog}}})
        self.patcher.start(); self.addCleanup(self.patcher.stop)
        farming = mock.patch.object(game_settings, '_cached_farming', self.farming)
        farming.start(); self.addCleanup(farming.stop)
        self.save = {'world': {'objectsArray': []}, 'userInfo': {'player': {
            'cash': 250, 'gold': 1000, 'xp': 100015, 'storageData': {}}}}

    def test_finished_english_stable_inherits_exact_original_material_stages(self):
        item = items.get_item_by_name('xukhorsestable_finished')
        self.assertEqual((item['code'], item['className'], item['storageType']['itemClass']),
                         ('4S8', 'HorseStableBuildingFinished', 'horses'))
        self.assertEqual(item['upgrade'], items.get_item_by_name('horsestablewhite')['upgrade'])
        obj = {'id': 91, 'itemName': item['name'], 'className': item['className'],
               'isFullyBuilt': True, 'state': 'built', 'expansionLevel': 1, 'capacity': 20,
               'expansionParts': {}, 'contents': [], 'plantTime': 1000000}
        self.save['world']['objectsArray'] = [obj]
        for level, capacity in ((2, 25), (3, 30), (4, 35), (5, 40)):
            paid.perform(self.save, 'CompleteNow', copy.deepcopy(obj), [{}])
            paid.take_response(self.save)
            obj = self.save['world']['objectsArray'][0]
            self.assertEqual((obj['expansionLevel'], obj['capacity']), (level, capacity))
            self.assertEqual(obj['plantTime'], 1000000)
        self.assertEqual(self.save['userInfo']['player']['cash'], 50)
        before = copy.deepcopy(self.save)
        with self.assertRaises(ValueError):
            paid.perform(self.save, 'CompleteNow', copy.deepcopy(obj), [{}])
        self.assertEqual(self.save, before)

    def test_legacy_paid_completion_keeps_defaults_and_grants_exact_gift_once(self):
        for name, finished, reward, default, cost in (
                ('nurserybarn', 'nurserybarn_finished', 'foal_gray', 'bottle', 49),
                ('pigpen', 'pigpenv2_finished', 'pigpen_male_light_green', 'brick', 23)):
            with self.subTest(name=name):
                item = items.get_item_by_name(name)
                reward_code = items.get_item_by_name(reward)['code']
                self.save['userInfo']['player'].update(cash=250,
                    storageData={'-1': {reward_code: [2, ['sender'], [{'opaque': 'keep'}]]}})
                obj = construction.initialize_placement({'id': 92, 'itemName': name,
                    'className': item['className'], 'isFullyBuilt': True, 'state': 'built',
                    'capacity': 999, 'expansionLevel': 99, 'contents': [], 'plantTime': 1000000,
                    'imported': {'keep': [1]}})
                self.assertEqual((obj['state'], obj['isFullyBuilt'], obj['expansionLevel']),
                                 ('construction', False, 1))
                self.assertEqual(obj['contents'], [{'itemCode': items.get_item_by_name(default)['code'], 'numItem': 1}])
                self.save['world']['objectsArray'] = [obj]
                raw = {**copy.deepcopy(obj), 'itemName': finished,
                       'className': items.get_item_by_name(finished)['className'], 'contents': [],
                       'isFullyBuilt': True, 'capacity': 999, 'expansionLevel': 99, 'plantTime': 0}
                result = paid.perform(self.save, 'CompleteNow', raw,
                                      [{'partName': None, 'isGift': False}], request_id=20, now=2000000)
                paid.take_response(self.save)
                self.assertEqual(result, {'id': 92, 'finishedName': finished, 'gift': reward})
                built = self.save['world']['objectsArray'][0]
                self.assertEqual((built['itemName'], built['expansionLevel'], built['capacity'], built['plantTime']),
                                 (finished, 1, 20, 2000000000))
                self.assertEqual(built['imported'], {'keep': [1]})
                self.assertTrue(all(row['numItem'] == 0 for row in built['contents']))
                self.assertEqual(self.save['userInfo']['player']['cash'], 250 - cost)
                self.assertEqual(self.save['userInfo']['player']['storageData']['-1'][reward_code],
                                 [3, ['sender'], [{'opaque': 'keep'}]])
                accepted = copy.deepcopy(self.save)
                self.assertEqual(paid.perform(self.save, 'CompleteNow', raw,
                    [{'partName': None, 'isGift': False}], request_id=20, now=2000010), result)
                paid.take_response(self.save)
                self.assertEqual(self.save, accepted)
                self.save.pop(paid.REQUESTS_KEY)

    def test_legacy_finished_variants_use_archived_capacity_stages(self):
        for name, stages in (
                ('nurserybarn_finished', ((2, 30, 50), (3, 40, 50))),
                ('nurserybarn_finished_complete', ((2, 30, 50), (3, 40, 50))),
                ('pigpen_finished', ((2, 30, 36), (3, 40, 60))),
                ('pigpenv2_finished', ((2, 30, 36), (3, 40, 60)))):
            with self.subTest(name=name):
                item = items.get_item_by_name(name)
                obj = {'id': 93, 'itemName': name, 'className': item['className'],
                       'isFullyBuilt': True, 'state': 'built', 'expansionLevel': 1, 'capacity': 20,
                       'expansionParts': {'opaque': {'keep': [2]}}, 'plantTime': 1000000,
                       'contents': [{'itemCode': 'FF', 'numItem': 1, 'imported': 'keep'}]}
                self.save['world']['objectsArray'] = [obj]
                self.save['userInfo']['player'].update(cash=250, storageData={})
                balance = 250
                for level, capacity, cost in stages:
                    paid.perform(self.save, 'ExpandWithCurrency', copy.deepcopy(obj), [{}], now=2000000)
                    paid.take_response(self.save)
                    obj = self.save['world']['objectsArray'][0]
                    balance -= cost
                    self.assertEqual((obj['expansionLevel'], obj['capacity']), (level, capacity))
                    self.assertEqual(obj['plantTime'], 1000000)
                    self.assertEqual(obj['expansionParts'], {'opaque': {'keep': [2]}})
                    self.assertEqual(obj['contents'], [{'itemCode': 'FF', 'numItem': 1, 'imported': 'keep'}])
                    self.assertEqual(self.save['userInfo']['player']['cash'], balance)
                    self.assertEqual(self.save['userInfo']['player']['storageData'], {})

    def test_final_gift_material_uses_the_same_completion_reward_without_retry_duplication(self):
        for name, finished, reward in (
                ('nurserybarn', 'nurserybarn_finished', 'foal_gray'),
                ('pigpen', 'pigpenv2_finished', 'pigpen_male_light_green')):
            with self.subTest(name=name):
                item = items.get_item_by_name(name)
                needs = construction._initial_requirements(item)
                obj = {'id': 94, 'itemName': name, 'className': item['className'],
                       'state': 'construction', 'isFullyBuilt': False, 'plantTime': 1000000,
                       'contents': [{'itemCode': code, 'numItem': count - (code == 'K1'), 'opaque': 'keep'}
                                    for code, (_, count) in needs.items()]}
                self.save['world']['objectsArray'] = [obj]
                self.save['userInfo']['player'].update(cash=250, storageData={'-1': {'K1': [1, ['sender'], []]}})
                options = {'storedItemName': 'brick', 'numToStore': 1, 'isGift': True}
                raw = copy.deepcopy(obj)
                result = construction.store_for_game(self.save, raw, options, now=2000000)
                self.assertEqual(result, {'finishedName': finished, 'gift': reward})
                self.assertEqual(construction.take_response(self.save), result)
                self.assertEqual(self.save['world']['objectsArray'][0]['plantTime'], 2000000000)
                code = items.get_item_by_name(reward)['code']
                self.assertEqual(self.save['userInfo']['player']['storageData']['-1'][code], [1, [], []])
                self.assertEqual(self.save['userInfo']['player']['cash'], 250)
                accepted = copy.deepcopy(self.save)
                self.assertEqual(construction.store_for_game(self.save, raw, options, now=2000010),
                                 {'finishedName': finished})
                construction.take_response(self.save)
                self.assertEqual(self.save, accepted)

    def test_herb_expansion_prices_and_original_seed_package_sizes(self):
        item = items.get_item_by_name('herbgarden')
        self.save['userInfo']['player'].update(cash=1000, mastery={})
        obj = {'id': 95, 'itemName': item['name'], 'className': item['className'],
               'isFullyBuilt': True, 'state': 'bare', 'expansionLevel': 1, 'capacity': 0,
               'expansionParts': {'opaque': {'keep': [1]}}, 'contents': [], 'plantTime': 1000000}
        self.save['world']['objectsArray'] = [obj]
        balance, seeds, now = 1000, 0, 2000000
        package_code = items.get_item_by_name('thaibasil_seedpackage')['code']
        for level, cost, quantity in ((2, 60, 100), (3, 120, 200), (4, 180, 400),
                                      (5, 240, 600), (6, 300, 900)):
            planted = obj['plantTime']
            paid.perform(self.save, 'ExpandWithCurrency', copy.deepcopy(obj), [{}], now=now)
            paid.take_response(self.save)
            obj = self.save['world']['objectsArray'][0]
            balance -= cost
            self.assertEqual((obj['expansionLevel'], obj['capacity'], obj['plantTime']), (level, 0, planted))
            self.assertEqual(obj['expansionParts'], {'opaque': {'keep': [1]}})
            self.assertEqual(self.save['userInfo']['player']['cash'], balance)
            self.assertEqual(building_harvest.harvest(self.save, obj, now=now), 1)
            obj = self.save['world']['objectsArray'][0]
            seeds += quantity
            self.assertEqual(self.save['userInfo']['player']['storageData']['-1'][package_code][0], seeds)
            now += 82800
        before = copy.deepcopy(self.save)
        with self.assertRaises(ValueError):
            paid.perform(self.save, 'CompleteNow', copy.deepcopy(obj), [{}], now=now)
        self.assertEqual(self.save, before)
        obj['expansionLevel'] = 1
        before = copy.deepcopy(self.save)
        with mock.patch.object(building_harvest, '_variant', return_value=0):
            with self.assertRaisesRegex(ValueError, 'experiment'):
                paid.perform(self.save, 'ExpandWithCurrency', copy.deepcopy(obj), [{}], now=now)
        self.assertEqual(self.save, before)

    def test_both_wells_keep_clocks_and_use_original_initial_level_prices_and_rewards(self):
        for name, rewards in (
                ('bldg_irrigationwell', (125, 190, 240, 280, 310)),
                ('bldg_irrigationwell_8hr', (62, 95, 120, 140, 155))):
            with self.subTest(name=name):
                item = items.get_item_by_name(name)
                self.save['userInfo']['player'].update(cash=1500, storageData={})
                # Original imported objects may omit this serialized field;
                # the constructor's catalog initial level is two, not one.
                obj = {'id': 96, 'itemName': name, 'className': 'FeatureBuilding',
                       'isFullyBuilt': True, 'state': 'bare', 'capacity': 0,
                       'expansionParts': {'opaque': {'keep': [1]}}, 'contents': [], 'plantTime': 1000000}
                self.save['world']['objectsArray'] = [obj]
                balance = 1500
                for level, cost, water in zip(range(3, 8), (42, 162, 240, 324, 438), rewards):
                    paid.perform(self.save, 'ExpandWithCurrency', copy.deepcopy(obj), [{}], now=2000000)
                    paid.take_response(self.save)
                    obj = self.save['world']['objectsArray'][0]
                    balance -= cost
                    self.assertEqual((obj['expansionLevel'], obj['capacity'], obj['plantTime']),
                                     (level, 0, 1000000))
                    self.assertEqual(irrigation_rewards.reward_for_level(item, level), water)
                    self.assertEqual(self.save['userInfo']['player']['cash'], balance)
                    self.assertEqual(self.save['userInfo']['player']['storageData'], {})
                    self.assertEqual(obj['expansionParts'], {'opaque': {'keep': [1]}})
                before = copy.deepcopy(self.save)
                with self.assertRaises(ValueError):
                    paid.perform(self.save, 'CompleteNow', copy.deepcopy(obj), [{}], now=2000000)
                self.assertEqual(self.save, before)


class PaidFeatureContainerExpansionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = items._decode_items((Path(__file__).resolve().parents[2] / 'xml/gz/v855038/items_opt.amf').read_bytes())
        cls.catalog = raw['settings']['items']['item']
        cls.sources = [row for row in cls.catalog if storage.feature_container_class(row)]

    def setUp(self):
        patcher = mock.patch.object(items, '_cached_items', {'settings': {'items': {'item': self.catalog}}})
        patcher.start(); self.addCleanup(patcher.stop)
        self.save = {'world': {'objectsArray': []}, 'userInfo': {'player': {
            'cash': 100000, 'gold': 1000, 'xp': 100015, 'storageData': {}}}}

    def test_all_66_finite_expansion_variants_preserve_imported_contents_and_ledgers(self):
        paid_sources, completed = 0, 0
        for source in self.sources:
            stages = paid._list(paid._features(source, 'ExpandFManager')[0].get('upgrade'))
            if not stages:
                continue
            paid_sources += 1
            self.save['userInfo']['player'].update(cash=100000,
                storageData={'600': {'opaque-import': [1, ['sender'], [{'DNA': {'keep': [1]}}]]}})
            obj = {'id': 600, 'itemName': source['name'], 'className': 'FeatureBuilding',
                   'isFullyBuilt': True, 'state': 'built', 'expansionLevel': 1, 'capacity': 10,
                   'contents': [{'itemCode': 'opaque-import', 'numItem': 1, 'imported': {'keep': [1]}}],
                   'expansionParts': {'opaque': {'keep': [2]}}, 'plantTime': 1000000}
            self.save['world']['objectsArray'] = [obj]
            contents, ledger = copy.deepcopy(obj['contents']), copy.deepcopy(
                self.save['userInfo']['player']['storageData']['600'])
            for stage in stages:
                with self.subTest(name=source['name'], level=stage['level']):
                    price = sum(int(row['need']) * int(items.get_item_by_name(row['name'])['cash'])
                                for row in paid._list(stage['part']))
                    before = self.save['userInfo']['player']['cash']
                    paid.perform(self.save, 'CompleteNow', copy.deepcopy(obj), [{}], now=2000000)
                    paid.take_response(self.save)
                    obj = self.save['world']['objectsArray'][0]
                    self.assertEqual((obj['expansionLevel'], obj['capacity'], obj['plantTime']),
                                     (int(stage['level']), int(stage['capacity']), 1000000))
                    self.assertEqual(self.save['userInfo']['player']['cash'], before - price)
                    self.assertEqual(obj['contents'], contents)
                    self.assertEqual(obj['expansionParts'], {'opaque': {'keep': [2]}})
                    self.assertEqual(self.save['userInfo']['player']['storageData'], {'600': ledger})
                    completed += 1
        self.assertEqual(paid_sources, 66)
        self.assertEqual(completed, 330)

    def test_five_complete_cash_billboards_start_at_six_and_never_charge_for_missing_stages(self):
        cash = [item for item in self.sources if not paid._features(item, 'ExpandFManager')[0].get('upgrade')]
        self.assertEqual(len(cash), 5)
        for item in cash:
            with self.subTest(name=item['name']):
                obj = construction.initialize_placement({'id': 601, 'itemName': item['name'],
                    'className': 'FeatureBuilding', 'state': 'built', 'isFullyBuilt': True,
                    'expansionLevel': 1, 'expansionParts': {}, 'contents': [], 'plantTime': 1000000})
                self.assertEqual(obj['expansionLevel'], 6)
                self.save['world']['objectsArray'] = [obj]
                before = copy.deepcopy(self.save)
                for action in ('CompleteNow', 'ExpandWithCurrency'):
                    with self.assertRaises(ValueError):
                        paid.perform(self.save, action, copy.deepcopy(obj), [{}], now=2000000)
                    self.assertEqual(self.save, before)
        garage = items.get_item_by_name('xukgarage_finished')
        self.assertEqual(garage['storageSize'], '20')
        legacy = construction.initialize_placement({'id': 602, 'itemName': garage['name'],
            'className': garage['className'], 'state': 'built', 'isFullyBuilt': True})
        self.assertEqual(legacy['expansionLevel'], 1)


class PaidGivingBuildingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = items._decode_items((Path(__file__).resolve().parents[2] / 'xml/gz/v855038/items_opt.amf').read_bytes())
        cls.catalog = raw['settings']['items']['item']
        cls.sources = [row for row in cls.catalog if construction._giving_building(row)]

    def setUp(self):
        patcher = mock.patch.object(items, '_cached_items', {'settings': {'items': {'item': self.catalog}}})
        patcher.start(); self.addCleanup(patcher.stop)
        from contextlib import redirect_stdout
        import io
        redirect = redirect_stdout(io.StringIO())
        redirect.__enter__(); self.addCleanup(redirect.__exit__, None, None, None)
        self.save = {'world': {'objectsArray': []}, 'userInfo': {'player': {
            'cash': 100000, 'gold': 1000, 'xp': 100015, 'storageData': {}}}}

    def building(self, source, level=1):
        obj = {'id': 97, 'itemName': source['name'], 'className': 'FeatureBuilding',
               'isFullyBuilt': True, 'state': 'built', 'expansionLevel': level,
               'expansionParts': {'opaque': {'keep': [1]}}, 'contents': [], 'plantTime': 1000000,
               'imported': {'keep': [2]}}
        self.save['world']['objectsArray'] = [obj]
        return obj

    def test_all_55_authored_giving_buildings_and_1560_stages_pay_and_grant(self):
        self.assertEqual(len(self.sources), 55)
        completed, leaf_codes = 0, set()
        for source in self.sources:
            self.save['userInfo']['player'].update(cash=100000, storageData={})
            obj = self.building(source)
            expand = paid._features(source, 'ExpandFManager')[0]
            for stage in paid._list(expand['upgrade']):
                with self.subTest(name=source['name'], level=stage['level']):
                    before = self.save['userInfo']['player']['cash']
                    price = sum(int(row['need']) * int(items.get_item_by_name(row['name'])['cash'])
                                for row in paid._list(stage['part']))
                    paid.perform(self.save, 'CompleteNow', copy.deepcopy(obj), [{}], now=2000000)
                    paid.take_response(self.save)
                    obj = self.save['world']['objectsArray'][0]
                    self.assertEqual((obj['expansionLevel'], obj['capacity'], obj['state'], obj['plantTime']),
                                     (int(stage['level']), int(stage['capacity']), 'built', 1000000))
                    self.assertEqual(self.save['userInfo']['player']['cash'], before - price)
                    self.assertEqual(obj['imported'], {'keep': [2]})
                    self.assertEqual(obj['expansionParts'], {'opaque': {'keep': [1]}})
                    gifts = self.save['userInfo']['player']['storageData']['-1']
                    self.assertNotIn('XX', gifts)
                    self.assertTrue(all(entry[0] > 0 for entry in gifts.values()))
                    leaf_codes.update(gifts)
                    completed += 1
            before = copy.deepcopy(self.save)
            with self.assertRaises(ValueError):
                paid.perform(self.save, 'ExpandWithCurrency', copy.deepcopy(obj), [{}], now=2000000)
            self.assertEqual(self.save, before)
        self.assertEqual(completed, 1560)
        self.assertEqual(len(leaf_codes), 1111)

    def test_recursive_packages_expand_names_and_quantities_instead_of_placeholder_codes(self):
        self.assertEqual(construction._gift_plan('pkg_unwither_3', 2), {'consume_unwither': 6})
        self.assertEqual(construction._gift_plan('pkg_hollybright_finish', 1),
                         {'pegacorn_xhl_holidaylights': 1, 'xlgunwitherringbox': 1})
        self.assertEqual(construction._gift_plan('pkg_gardenpavilion_finish', 1),
                         {'part_xjp_bamboomachete': 5, 'part_xjp_bamboosmasher': 5,
                          'xjp_land_unwitherringbox': 1})

    def test_bad_package_missing_leaf_and_automatic_effect_refuse_before_any_charge(self):
        source = items.get_item_by_name('bldg_holidaygivingtree')
        for mutation in ('cycle', 'missing', 'automatic'):
            with self.subTest(mutation=mutation):
                obj = self.building(source, level=2)
                changed = copy.deepcopy(items.get_item_by_name('pkg_unwither_1'))
                if mutation == 'cycle':
                    changed['itemPackage'] = {'value': changed['name'], 'amount': '1'}
                elif mutation == 'missing':
                    changed['itemPackage'] = {'value': 'missing_original_reward', 'amount': '1'}
                else:
                    changed.pop('itemPackage')
                    changed.update(className='AutoConsumable', type='consumable')
                records = [changed if row['name'] == changed['name'] else row for row in self.catalog]
                before = copy.deepcopy(self.save)
                with mock.patch.object(items, '_cached_items', {'settings': {'items': {'item': records}}}):
                    with self.assertRaises(ValueError):
                        paid.perform(self.save, 'CompleteNow', copy.deepcopy(obj), [{}], now=2000000)
                self.assertEqual(self.save, before)

    def test_final_gift_material_grants_award_and_preserves_existing_gift_metadata(self):
        source = items.get_item_by_name('bldg_holidaygivingtree')
        obj = self.building(source)
        reward = items.get_item_by_name('wolf_xhl_icey')['code']
        self.save['userInfo']['player']['storageData'] = {
            '-1': {'whz': [1, ['sender'], [{'unit': 1}]], reward: [2, ['old sender'], [{'opaque': 'keep'}]]}}
        result = construction.store_for_game(self.save, copy.deepcopy(obj), {
            'storedItemName': 'part_sparklelight', 'numToStore': 1, 'isGift': True}, now=2000000)
        self.assertEqual(result, {})
        construction.take_response(self.save)
        target = self.save['world']['objectsArray'][0]
        self.assertEqual((target['expansionLevel'], target['capacity'], target['plantTime']), (2, 25, 1000000))
        self.assertEqual(self.save['userInfo']['player']['cash'], 100000)
        self.assertEqual(self.save['userInfo']['player']['storageData']['-1'],
                         {reward: [3, ['old sender'], [{'opaque': 'keep'}]]})


class PaidFiniteCompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = items._decode_items((Path(__file__).resolve().parents[2] / 'xml/gz/v855038/items_opt.amf').read_bytes())
        cls.catalog = raw['settings']['items']['item']
        cls.sources = [row for row in cls.catalog if construction._lootable_building(row)]

    def setUp(self):
        patcher = mock.patch.object(items, '_cached_items', {'settings': {'items': {'item': self.catalog}}})
        patcher.start(); self.addCleanup(patcher.stop)
        from contextlib import redirect_stdout
        import io
        redirect = redirect_stdout(io.StringIO())
        redirect.__enter__(); self.addCleanup(redirect.__exit__, None, None, None)
        self.save = {'world': {'objectsArray': []}, 'userInfo': {'player': {
            'cash': 100000, 'gold': 1000, 'xp': 100015, 'storageData': {}}}}

    def building(self, item, level=1):
        obj = {'id': 97, 'itemName': item['name'], 'className': item['className'],
               'state': 'built', 'expansionLevel': level, 'expansionParts': {'opaque': {'keep': [1]}},
               'contents': [], 'plantTime': 1000000, 'imported': {'keep': [2]}}
        self.save['world']['objectsArray'] = [obj]
        return obj

    def test_54_source_ladders_469_ungated_rows_and_433_named_gifts(self):
        self.assertEqual(len(self.sources), 54)
        completed, rewards, gated = 0, 0, 0
        for item in self.sources:
            self.save['userInfo']['player'].update(cash=100000, storageData={})
            obj = self.building(item)
            for stage in paid._list(paid._features(item, 'ExpandFManager')[0]['upgrade']):
                with self.subTest(name=item['name'], level=stage['level']):
                    before = copy.deepcopy(self.save)
                    if 'prereq' in stage or 'prereqs' in stage:
                        with self.assertRaisesRegex(ValueError, 'region prerequisite'):
                            paid.perform(self.save, 'CompleteNow', copy.deepcopy(obj), [], now=2000000)
                        self.assertEqual(self.save, before)
                        obj['expansionLevel'] += 1
                        gated += 1
                        continue
                    price = sum(int(row['need']) * int(items.get_item_by_name(row['name'])['cash'])
                                for row in paid._list(stage['part']))
                    reply = paid.perform(self.save, 'CompleteNow', copy.deepcopy(obj), [], now=2000000)
                    paid.take_response(self.save)
                    obj = self.save['world']['objectsArray'][0]
                    self.assertEqual((obj['expansionLevel'], obj['capacity'], obj['plantTime']),
                                     (int(stage['level']), 0, 1000000))
                    self.assertEqual(self.save['userInfo']['player']['cash'],
                                     before['userInfo']['player']['cash'] - price)
                    self.assertEqual(obj['expansionParts'], {'opaque': {'keep': [1]}})
                    self.assertEqual(obj['imported'], {'keep': [2]})
                    if stage.get('rewardItem'):
                        rewards += 1
                        self.assertEqual(reply, {'id': 97, 'completeRewardItem': stage['rewardItem']})
                        gift = items.get_item_by_name(stage['rewardItem'])['code']
                        prior = before['userInfo']['player']['storageData'].get('-1', {}).get(gift, [0])[0]
                        self.assertEqual(self.save['userInfo']['player']['storageData']['-1'][gift][0], prior + 1)
                    else:
                        self.assertEqual(reply, {'id': 97})
                        self.assertEqual(self.save['userInfo']['player']['storageData'],
                                         before['userInfo']['player']['storageData'])
                    completed += 1
        self.assertEqual((completed, rewards, gated), (469, 433, 14))

    def test_initial_size_twenty_explicit_saved_level_and_stale_owner_reward(self):
        item = items.get_item_by_name('xch_bigbuildable')
        self.assertEqual(item['storageSize'], '20')
        obj = self.building(item)
        obj.pop('expansionLevel')
        before = copy.deepcopy(self.save)
        with self.assertRaises(ValueError):
            paid.perform(self.save, 'CompleteNow', copy.deepcopy(obj), [], now=2000000)
        self.assertEqual(self.save, before)
        self.assertEqual(construction.initialize_placement(obj)['expansionLevel'], 20)
        item = items.get_item_by_name('xoz_emeraldcity')
        obj = self.building(item, 5)
        reply = paid.perform(self.save, 'CompleteNow', copy.deepcopy(obj), [], now=2000000)
        self.assertEqual(reply['completeRewardItem'], 'pegacorn_xoz_goldenemerald')
        gifts = self.save['userInfo']['player']['storageData']['-1']
        self.assertNotIn(items.get_item_by_name(item['completeRewardItem'])['code'], gifts)

    def test_missing_loot_only_ladders_and_disabled_dynamic_cohort_never_charge(self):
        for name in ('xau_daydreamisland', 'xrf_hiddenpalace', 'xww_trainstation', 'xhd_buildable'):
            obj = self.building(items.get_item_by_name(name))
            before = copy.deepcopy(self.save)
            for action in ('CompleteNow', 'HarvestReadyNow'):
                with self.assertRaises(ValueError):
                    paid.perform(self.save, action, copy.deepcopy(obj), [], now=2000000)
                self.assertEqual(self.save, before)
        obj = self.building(items.get_item_by_name('xoz_emeraldcity'))
        before = copy.deepcopy(self.save)
        with mock.patch.object(construction, '_dynamic_parts_enabled', return_value=False):
            with self.assertRaises(ValueError):
                paid.perform(self.save, 'CompleteNow', copy.deepcopy(obj), [], now=2000000)
        self.assertEqual(self.save, before)


class PaidOrchardTests(unittest.TestCase):
    setUp = PaidFiniteCompletionTests.setUp
    building = PaidFiniteCompletionTests.building

    @classmethod
    def setUpClass(cls):
        raw = items._decode_items((Path(__file__).resolve().parents[2] / 'xml/gz/v855038/items_opt.amf').read_bytes())
        cls.catalog = raw['settings']['items']['item']
        cls.sources = [row for row in cls.catalog if storage.orchard_container_class(row)]

    def owner(self, item):
        self.save['userInfo']['currentWorldType'] = 'farm'
        self.save['userInfo']['player']['storageData'] = {
            '97': {'CH': [2, ['sender'], [{'tree': 'keep'}]]}, '-1': {}}
        obj = self.building(item, int(item.get('initialExpansionLevel', 1)))
        obj.update(state='ripe', contents=[{'itemCode': 'CH', 'numItem': 2, 'opaque': {'keep': [1]}}],
                   itemOrder=['CH', 'CH'], plantTime=1000)
        return obj

    def test_all_66_orchards_132_finite_stages_36_gifts_and_exact_shared_swap(self):
        regions = [row for row in self.sources if row.get('finishedName')]
        self.assertEqual((len(self.sources), len(regions)), (67, 66))
        completed, gifts = 0, 0
        for item in regions:
            self.save['userInfo']['player']['cash'] = 1000
            obj = self.owner(item)
            contents = copy.deepcopy(obj['contents'])
            ledger = copy.deepcopy(self.save['userInfo']['player']['storageData']['97'])
            for stage in paid._list(paid._features(item, 'ExpandFManager')[0]['upgrade']):
                with self.subTest(name=item['name'], level=stage['level']):
                    result = paid.perform(self.save, 'CompleteNow', copy.deepcopy(obj), [], now=2000000)
                    paid.take_response(self.save)
                    obj = self.save['world']['objectsArray'][0]
                    level = int(stage['level'])
                    self.assertEqual((obj['expansionLevel'], obj['capacity'], obj['plantTime']),
                                     (level, int(stage['capacity']), 1000))
                    self.assertEqual(obj['contents'], contents)
                    self.assertEqual(obj['itemOrder'], ['CH', 'CH'])
                    self.assertEqual(obj['imported'], {'keep': [2]})
                    self.assertEqual(self.save['userInfo']['player']['storageData']['97'], ledger)
                    self.assertEqual(self.save['userInfo']['player']['cash'], 1000 - 30 * (level - 1))
                    self.assertEqual(obj['itemName'], item['name'] if level == 2 else 'superorchard_featurebuilding')
                    self.assertEqual(obj['expansionParts'], {'opaque': {'keep': [1]}} if level == 2 else {})
                    if stage.get('rewardItem'):
                        gifts += 1
                        self.assertEqual(result['completeRewardItem'], stage['rewardItem'])
                        code = items.get_item_by_name(stage['rewardItem'])['code']
                        self.assertEqual(self.save['userInfo']['player']['storageData']['-1'][code][0], 1)
                    completed += 1
            before = copy.deepcopy(self.save)
            for action in ('CompleteNow', 'ExpandWithCurrency', 'HarvestReadyNow'):
                with self.assertRaises(ValueError):
                    paid.perform(self.save, action, copy.deepcopy(obj), [], now=2000000)
                self.assertEqual(self.save, before)
        self.assertEqual((completed, gifts), (132, 36))
        target = items.get_item_by_name('superorchard_featurebuilding')
        self.assertEqual(construction.initialize_placement({'id': 98, 'itemName': target['name']})['expansionLevel'], 3)

    def test_all_67_base_harvests_pay_only_tree_coins_preserve_stock_and_replay(self):
        import peaceful
        with mock.patch.object(peaceful, 'grow_seconds', return_value=165600):
            for item in self.sources:
                self.save['userInfo']['player']['gold'] = 1000
                obj = self.owner(item)
                before = copy.deepcopy(obj)
                self.assertEqual(paid.harvest_orchard(self.save, obj, now=2000000, request_id=40), 1)
                after = self.save['world']['objectsArray'][0]
                self.assertEqual(after, {**before, 'state': 'bare', 'plantTime': 2000000000})
                self.assertEqual(self.save['userInfo']['player']['gold'], 1036)
                accepted = copy.deepcopy(self.save)
                self.assertEqual(paid.harvest_orchard(self.save, after, now=2000000, request_id=40), 0)
                self.assertEqual(self.save, accepted)
                self.save.pop(paid.ORCHARD_REQUESTS_KEY)

    def test_new_orchards_start_current_clock_and_missing_coin_yield_defaults_zero(self):
        import peaceful
        for name, level in (('orchard_featurebuilding_finished', 1), ('superorchard_featurebuilding', 3)):
            result = paid.initialize_placement({'id': 98, 'itemName': name, 'plantTime': 0,
                'state': 'ripe', 'contents': [{'itemCode': 'CH', 'numItem': 20}],
                'itemOrder': ['forged'], 'expansionLevel': 99}, now=2000000)
            self.assertEqual((result['plantTime'], result['state'], result['expansionLevel']),
                             (2000000000, 'bare', level))
            self.assertEqual((result['contents'], result['itemOrder']), ([], []))
        obj = self.owner(items.get_item_by_name('orchard_featurebuilding_finished'))
        tree = items.get_item_by_name('berry_pkg_arborists')
        self.assertNotIn('coinYield', tree)
        obj['contents'] = [{'itemCode': tree['code'], 'numItem': 1}]
        self.save['userInfo']['player']['storageData']['97'] = {tree['code']: [1, [], []]}
        with mock.patch.object(peaceful, 'grow_seconds', return_value=165600):
            gold = self.save['userInfo']['player']['gold']
            self.assertEqual(paid.harvest_orchard(self.save, obj, now=2000000), 1)
            self.assertEqual(self.save['userInfo']['player']['gold'], gold)

    def test_bad_clock_empty_wrong_owner_world_ledger_and_early_harvest_are_atomic(self):
        import peaceful
        with mock.patch.object(peaceful, 'grow_seconds', return_value=165600):
            item = items.get_item_by_name('orchard_featurebuilding_finished')
            for mutation in ('clock', 'empty', 'foreign', 'identity', 'incomplete', 'ledger',
                             'ledger_only_tree', 'contents_only_tree'):
                obj = self.owner(item)
                if mutation == 'clock': obj['plantTime'] = 2000000000
                elif mutation == 'empty': obj['contents'] = []; self.save['userInfo']['player']['storageData']['97'] = {}
                elif mutation == 'foreign': self.save['userInfo']['currentWorldType'] = 'hawaii'
                elif mutation == 'identity': obj['className'] = 'Plot'
                elif mutation == 'incomplete': obj['isFullyBuilt'] = False
                elif mutation == 'ledger_only_tree':
                    self.save['userInfo']['player']['storageData']['97']['AP'] = [1, [], []]
                elif mutation == 'contents_only_tree':
                    obj['contents'].append({'itemCode': 'AP', 'numItem': 1})
                else: self.save['userInfo']['player']['storageData']['97']['CH'][0] = 3
                before = copy.deepcopy(self.save)
                with self.assertRaises(ValueError):
                    paid.harvest_orchard(self.save, obj, now=2000000, request_id=40)
                self.assertEqual(self.save, before)


class PaidFlowerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = items._decode_items((Path(__file__).resolve().parents[2] / 'xml/gz/v855038/items_opt.amf').read_bytes())
        cls.catalog = [row for row in raw['settings']['items']['item']
                       if row.get('type') == 'bloom' or row['name'] == 'part_flowerfood']
        cls.sources = [row for row in cls.catalog if paid._features(row, 'UpgradeManager')]

    def setUp(self):
        self.patcher = mock.patch.object(items, '_cached_items', {'settings': {'items': {'item': self.catalog}}})
        self.patcher.start(); self.addCleanup(self.patcher.stop)
        self.save = {'world': {'objectsArray': []}, 'userInfo': {'player': {
            'cash': 100, 'gold': 1000, 'xp': 100015, 'storageData': {}}}}

    def flower(self, source, *, level=1, state='bare', food=0):
        obj = {'id': 600, 'itemName': source['name'], 'className': 'FeatureBuilding',
               'expansionLevel': level, 'expansionParts': {'5T8': food, 'imported': {'keep': True}},
               'contents': [], 'state': state, 'plantTime': 1000000, 'isFullyBuilt': True,
               'position': {'x': 3, 'y': 4, 'z': 0}, 'imported': {'keep': [1, 2]}}
        self.save['world']['objectsArray'] = [obj]
        return obj

    def test_new_flower_uses_authored_initial_stage_and_keeps_placement_metadata(self):
        for name, initial in (('africandaisies_bulb', 1), ('africandaisies_singlebloom', 2)):
            with self.subTest(name=name):
                raw = {'id': 701, 'itemName': name, 'className': 'FeatureBuilding',
                       'state': 'grown', 'isFullyBuilt': False, 'plantTime': 0,
                       'expansionLevel': 99, 'expansionParts': {'5T8': 5}, 'capacity': 999,
                       'contents': [{'itemCode': '5T8', 'numItem': 5}],
                       'position': {'x': 10, 'y': 11, 'z': 0}, 'imported': {'keep': [1, 2]}}
                before = copy.deepcopy(raw)
                result = paid.initialize_placement(raw, now=1000)
                self.assertEqual(raw, before)
                self.assertEqual((result['expansionLevel'], result['state'], result['plantTime']),
                                 (initial, 'bare', 1000000))
                self.assertEqual((result['expansionParts'], result['capacity'], result['contents']), ({}, 0, []))
                self.assertIs(result['isFullyBuilt'], True)
                for field in ('id', 'itemName', 'position', 'imported'):
                    self.assertEqual(result[field], before[field])
        ordinary = {'itemName': 'cow', 'className': 'Animal', 'plantTime': 0}
        self.assertEqual(paid.initialize_placement(ordinary, now=1000), ordinary)

    def test_client_projection_removes_only_bloom_harvest_components(self):
        changed = 0
        for item in self.catalog:
            with self.subTest(item=item['name']):
                before = copy.deepcopy(item)
                result = paid.client_item_projection(item)
                self.assertEqual(item, before)
                if paid._bloom(item) and paid._features(item, 'HarvestFManager'):
                    changed += 1
                    expected = copy.deepcopy(item)
                    expected['features']['feature'] = [row for row in paid._list(item['features']['feature'])
                                                       if row.get('className') != 'HarvestFManager']
                    self.assertEqual(result, expected)
                    self.assertFalse(paid._features(result, 'HarvestFManager'))
                    for component in ('ExpandFManager', 'UpgradeManager', 'WitherManager', 'ImageProgressionFManager'):
                        self.assertEqual(paid._features(result, component), paid._features(item, component))
                else:
                    self.assertEqual(result, item)
        self.assertEqual(changed, 258)
        well = {'name': 'well', 'type': 'building', 'className': 'FeatureBuilding',
                'features': {'feature': {'name': 'harvester', 'className': 'HarvestFManager'}}}
        self.assertEqual(paid.client_item_projection(well), well)

    def test_all_172_authored_upgrade_prices_targets_and_unchanged_timer(self):
        self.assertEqual(len(self.sources), 172)
        prices = set()
        for source in self.sources:
            with self.subTest(source=source['name']):
                obj = self.flower(source, level=2)
                self.save['userInfo']['player']['cash'] = 100
                upgrade = paid._features(source, 'UpgradeManager')[0]
                paid.perform(self.save, 'upgradeBuilding', copy.deepcopy(obj), [{}])
                paid.take_response(self.save)
                target = self.save['world']['objectsArray'][0]
                price = int(upgrade['upgradeCost']); prices.add(price)
                self.assertEqual(self.save['userInfo']['player']['cash'], 100 - price)
                self.assertEqual(target['itemName'], upgrade['upgradeItem'])
                self.assertEqual(target['state'], 'bare')
                self.assertEqual(target['plantTime'], 1000000)
                for field in ('id', 'position', 'imported'):
                    self.assertEqual(target[field], obj[field])
        self.assertEqual(prices, set(range(1, 8)))

    def test_every_bulb_feeds_using_saved_food_and_restarts_clock_including_no_replacement_bulbs(self):
        bulbs = [row for row in self.sources if row.get('initialExpansionLevel') == '1']
        self.assertEqual(len(bulbs), 86)
        for source in bulbs:
            with self.subTest(source=source['name']):
                obj = self.flower(source, state='grown', food=3)
                self.save['userInfo']['player']['cash'] = 100
                raw = {**copy.deepcopy(obj), 'expansionLevel': 2, 'plantTime': 999999999, 'expansionParts': {}}
                paid.perform(self.save, 'ExpandWithCurrency', raw, [{}], now=2000000)
                paid.take_response(self.save)
                fed = self.save['world']['objectsArray'][0]
                self.assertEqual((fed['expansionLevel'], fed['state'], fed['plantTime']), (2, 'bare', 2000000000))
                self.assertEqual(fed['itemName'], source.get('finishedName', source['name']))
                self.assertEqual(fed['expansionParts'], {'imported': {'keep': True}})
                self.assertEqual(fed['imported'], obj['imported'])
                self.assertEqual(self.save['userInfo']['player']['cash'], 98)

    def test_exact_single_part_bulk_gifts_are_consumed_once_without_cash_or_metadata_duplication(self):
        source = next(row for row in self.sources if row['name'] == 'africandaisies_bulb')
        obj = self.flower(source)
        self.save['userInfo']['player']['storageData'] = {'-1': {'5T8': [7, ['senderA', 'senderB'],
                                                                           [{'unit': n} for n in range(7)]]}}
        raw = copy.deepcopy(obj)
        options = {'partName': 'part_flowerfood', 'isGift': True}
        result = paid.perform(self.save, 'CompleteNow', raw, [options], request_id=7, now=2000000)
        paid.take_response(self.save)
        player = self.save['userInfo']['player']
        self.assertEqual(player['cash'], 100)
        self.assertEqual(player['storageData']['-1']['5T8'][0], 2)
        self.assertEqual(player['storageData']['-1']['5T8'][2], [{'unit': 5}, {'unit': 6}])
        self.assertEqual(self.save['world']['objectsArray'][0]['itemName'], 'africandaisies_singlebloom')
        before = copy.deepcopy(self.save)
        self.assertEqual(paid.perform(self.save, 'CompleteNow', raw, [options], request_id=7, now=2000010), result)
        paid.take_response(self.save)
        self.assertEqual(self.save, before)

    def test_missing_single_part_gifts_and_one_unit_combination_are_atomic(self):
        source = next(row for row in self.sources if row['name'] == 'africandaisies_bulb')
        for food, gifts in ((0, 4), (4, 1)):
            obj = self.flower(source, food=food)
            self.save['userInfo']['player']['storageData'] = {'-1': {'5T8': [gifts, [], []]}}
            before = copy.deepcopy(self.save)
            with self.assertRaises(ValueError):
                paid.perform(self.save, 'CompleteNow', copy.deepcopy(obj),
                             [{'partName': 'part_flowerfood', 'isGift': True}], now=2000000)
            self.assertEqual(self.save, before)

    def test_plot_actions_cannot_create_flowers_or_reset_their_saved_clocks(self):
        source = next(row for row in self.sources if row['name'] == 'africandaisies_bulb')
        obj = self.flower(source)
        forged = {**copy.deepcopy(obj), 'state': 'grown', 'plantTime': 0, 'expansionLevel': 99}
        for action in ('plow', 'clearWithered', 'use', 'plant'):
            with self.assertRaises(ValueError):
                paid.guard_action(action, obj, forged)
            with self.assertRaises(ValueError):
                paid.guard_action(action, None, {**forged, 'id': 999})
            protected = paid.preserve_fields(obj, forged, action=action)
            self.assertEqual((protected['state'], protected['plantTime'], protected['expansionLevel']), ('bare', 1000000, 1))


if __name__ == '__main__':
    unittest.main()
