"""Original Sheep Pen breeding: real archived catalog, temporary saves only."""
import copy
from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence  # Establish the temporary data directory before product imports.
import breeding
import items
import persistence

ROOT = Path(__file__).resolve().parents[2]
NOW = 1_700_000_000


class BreedingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = items._decode_items((ROOT / 'xml/gz/v855038/items_opt.amf').read_bytes())
        cls.initial = json.loads((ROOT / 'villages/initial.json').read_text())

    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.object(items, '_cached_items', self.catalog))
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.save = copy.deepcopy(self.initial)
        self.save['world']['objectsArray'] = []
        self.player = self.save['userInfo']['player']
        self.player.update(cash=100, userId='breeder-fixture', storageData={})
        self.pen = {'id': 71, 'itemName': breeding.FEATURE, 'className': 'FeatureBuilding', 'state': 'built',
                    'isFullyBuilt': True, 'expansionLevel': 1, 'position': {'x': 2, 'y': 5},
                    'contents': [{'itemCode': 'cx', 'numItem': 1}, {'itemCode': 'cw', 'numItem': 1}],
                    'storageMetadata': {}, 'extraDataState': {'breedHistory': {}, 'breedingQueue': [], 'imported': ['keep']}}
        self.save['world']['objectsArray'].append(self.pen)
        self.raw = {'buildingId': 71, 'suiteSlot': 0, 'numPotions': 0, 'start_ts': 0, 'finish_ts': 0,
                    'breedObjs': [{'hash': 'cx:'}, {'hash': 'cw:'}], 'patternGuarantee': False}

    def current_pen(self):
        return self.save['world']['objectsArray'][0]

    def begin(self, potions=0, *, now=NOW, seed=1, **changes):
        raw = dict(self.raw, numPotions=potions, **changes)
        with mock.patch.object(random, 'getrandbits', return_value=seed):
            result = breeding.begin(self.save, raw, now=now)
        return result['extraDataState']['breedingQueue'][raw['suiteSlot']]

    def rejected(self, call):
        before = copy.deepcopy(self.save)
        with self.assertRaises(ValueError):
            call()
        self.assertEqual(self.save, before)

    def test_archived_sheep_contract_and_exact_client_hash(self):
        config = breeding._config()
        self.assertEqual(config['times'], [86400, 43200, 21600, 10800, 3600, 0])
        self.assertEqual(config['defaultBreedItem'], 'sheeppen_lamb')
        self.assertEqual(items.get_item_by_code('gk')['name'], 'xuk_animal_love_potion')
        self.assertTrue(breeding.manages(items.get_item_by_name(breeding.FEATURE)))
        dna = {'N': 'Exact', 'G': 'F', 'B': {'H': ['0', '0'], 'S': ['0', '0'], 'V': ['f', 'f']},
               'P': {'H': ['0', '0'], 'S': ['0', '0'], 'V': ['0', '0'], 'T': 'a'}}
        import hashlib
        self.assertEqual(breeding.dna_hash(dna), hashlib.md5(b'F0,00,0f,f0,00,00,0a').hexdigest()[:8])
        dna['N'] = 'Different personal name'
        self.assertEqual(breeding.dna_hash(dna), hashlib.md5(b'F0,00,0f,f0,00,00,0a').hexdigest()[:8])

    def test_real_parent_loop_waits_grants_lamb_dna_once_and_preserves_parents(self):
        before_contents = copy.deepcopy(self.pen['contents'])
        job = self.begin()
        self.assertEqual((job['start_ts'], job['finish_ts']), (NOW, NOW + 86400))
        self.rejected(lambda: breeding.finish(self.save, job, now=NOW + 86399))
        result = breeding.finish(self.save, job, now=NOW + 86400)
        self.assertEqual(result['reward']['itemName'], 'sheeppen_lamb')
        packed = result['reward']['mutableState']
        dna = breeding._dna(packed)
        self.assertEqual(dna['U'], 'breeder-fixture')
        self.assertEqual(self.save['userInfo']['player']['storageData']['-1']['cy'], [1, [], [packed]])
        self.assertEqual(self.current_pen()['contents'], before_contents)
        self.assertEqual(self.current_pen()['extraDataState']['imported'], ['keep'])
        before = copy.deepcopy(self.save)
        retry = breeding.finish(self.save, job, now=NOW + 86401)
        self.assertIsNone(retry['reward'])
        self.assertEqual(self.save, before)
        self.assertEqual(self.save['breedingSkillStates'][breeding.FEATURE]['xp'], 3)

    def test_potions_use_existing_gifts_then_charge_exact_package_shortfall(self):
        self.player['storageData']['-1'] = {'gk': [2, ['friend'], ['old', 'new']]}
        job = self.begin(3)
        self.assertEqual(job['finish_ts'], NOW + 10800)
        self.assertEqual(self.save['userInfo']['player']['cash'], 98)
        self.assertNotIn('gk', self.save['userInfo']['player']['storageData']['-1'])
        before = copy.deepcopy(self.save)
        breeding.begin(self.save, dict(self.raw, numPotions=3), now=NOW + 2)
        self.assertEqual(self.save, before)
        self.rejected(lambda: breeding.begin(self.save, dict(self.raw, numPotions=4), now=NOW))

    def test_no_potions_can_fail_without_a_fabricated_offspring(self):
        job = self.begin(seed=0)
        result = breeding.finish(self.save, job, now=job['finish_ts'])
        self.assertIsNone(result['reward'])
        self.assertNotIn('cy', self.save['userInfo']['player']['storageData'].get('-1', {}))
        self.assertNotIn('breedingSkillStates', self.save)
        self.assertEqual(self.current_pen()['extraDataState']['breedingQueue'], [None])

    def test_five_potions_guarantee_success_and_allow_immediate_claim(self):
        job = self.begin(5, seed=0)
        self.assertEqual(job['finish_ts'], NOW)
        self.assertIsNotNone(breeding.finish(self.save, job, now=NOW)['reward'])
        self.assertEqual(self.save['userInfo']['player']['cash'], 90)
        breeding.assert_can_remove(self.save, 71, 'cx:', now=NOW)

    def test_finish_now_cost_is_catalog_value_and_retry_never_charges_again(self):
        job = self.begin()
        result = breeding.finish(self.save, job, now=NOW + 1, finish_now=True)
        self.assertIsNotNone(result['reward'])
        self.assertEqual(self.save['userInfo']['player']['cash'], 90)
        breeding.finish(self.save, job, now=NOW + 2, finish_now=True)
        self.assertEqual(self.save['userInfo']['player']['cash'], 90)
        self.rejected(lambda: breeding.begin(self.save, self.raw, now=NOW + 3))
        self.rejected(lambda: breeding.assert_can_remove(self.save, 71, 'cx:', now=NOW + 3))
        self.rejected(lambda: breeding.assert_can_remove(self.save, 71, now=NOW + 3))
        breeding.assert_can_remove(self.save, 71, 'cx:', now=NOW + 86400)

    def test_pattern_guarantee_cost_and_original_male_pattern(self):
        dna = copy.deepcopy(breeding._config()['variants']['sheeppen_ram'])
        dna['P']['T'] = 'b'
        packed = json.dumps(dna, separators=(',', ':'))
        key = 'cx:' + breeding.dna_hash(dna)
        self.pen['storageMetadata'][key] = [packed]
        raw = dict(self.raw, breedObjs=[{'hash': key}, {'hash': 'cw:'}], patternGuarantee=True, numPotions=5)
        with mock.patch.object(random, 'getrandbits', return_value=1):
            result = breeding.begin(self.save, raw, now=NOW)
        self.assertEqual(self.save['userInfo']['player']['cash'], 85)
        job = result['extraDataState']['breedingQueue'][0]
        result = breeding.finish(self.save, job, now=NOW)
        self.assertEqual(json.loads(result['reward']['mutableState'])['P']['T'], ['b'])
        self.assertEqual(self.current_pen()['storageMetadata'][key], [packed])

    def test_locked_suite_missing_pen_unfinished_pen_missing_and_wrong_gender_parents(self):
        for changes in ({'buildingId': 900}, {'suiteSlot': 1}, {'suiteSlot': -1}, {'numPotions': 6},
                        {'numPotions': True}, {'numPotions': float('nan')}, {'patternGuarantee': 1},
                        {'breedObjs': [{'hash': []}, {'hash': 'cw:'}]},
                        {'breedObjs': [{'hash': 'cw:'}, {'hash': 'cw:'}]},
                        {'breedObjs': [{'hash': 'ZZ:'}, {'hash': 'cw:'}]},
                        {'breedObjs': [{'hash': 'cy:'}, {'hash': 'cw:'}]}):
            with self.subTest(changes=changes):
                self.rejected(lambda: breeding.begin(self.save, dict(self.raw, **changes), now=NOW))
        self.pen['isFullyBuilt'] = False
        self.rejected(lambda: breeding.begin(self.save, self.raw, now=NOW))
        self.pen['isFullyBuilt'] = True
        self.pen['contents'][0]['numItem'] = 0
        self.rejected(lambda: breeding.begin(self.save, self.raw, now=NOW))

    def test_parent_hash_cannot_import_dna_from_another_farm_or_invent_metadata(self):
        raw = dict(self.raw, breedObjs=[{'hash': 'cx:12345678'}, {'hash': 'cw:'}])
        self.rejected(lambda: breeding.begin(self.save, raw, now=NOW))
        self.pen['storageMetadata']['cx:12345678'] = [json.dumps(breeding._config()['variants']['sheeppen_ram'])]
        self.rejected(lambda: breeding.begin(self.save, raw, now=NOW))

    def test_experimental_or_invalid_color_genes_reject_without_spending(self):
        for change in (['f0', 'f0'], ['not-hex', '0'], ['0'], [0, 0]):
            dna = copy.deepcopy(breeding._config()['variants']['sheeppen_ram'])
            dna['B']['H'] = change
            self.pen['storageMetadata']['cx:12345678'] = [json.dumps(dna)]
            raw = dict(self.raw, breedObjs=[{'hash': 'cx:12345678'}, {'hash': 'cw:'}], numPotions=5)
            self.rejected(lambda: breeding.begin(self.save, raw, now=NOW))

    def test_pending_parents_cannot_be_reused_in_another_suite_or_removed(self):
        self.pen['expansionLevel'] = 2
        self.begin()
        self.rejected(lambda: breeding.begin(self.save, dict(self.raw, suiteSlot=1), now=NOW + 1))
        self.rejected(lambda: breeding.assert_can_remove(self.save, 71, 'cx:', now=NOW))
        self.rejected(lambda: breeding.assert_can_remove(self.save, 71, now=NOW))

    def test_forged_finish_start_parents_and_shortfall_leave_job_and_balances_intact(self):
        job = self.begin()
        for changes in ({'start_ts': NOW - 1}, {'numPotions': 5}, {'buildingId': 72},
                        {'breedObjs': [{'hash': 'cw:'}, {'hash': 'cx:'}]}):
            self.rejected(lambda: breeding.finish(self.save, dict(job, **changes), now=NOW + 86400))
        self.save['userInfo']['player']['cash'] = 0
        self.rejected(lambda: breeding.finish(self.save, job, now=NOW, finish_now=True))

    def test_cash_failure_and_late_reward_failure_roll_back_all_mutations(self):
        self.player['cash'] = 0
        self.rejected(lambda: self.begin(1))
        self.player['cash'] = 100
        job = self.begin()
        actual = breeding.storage.store_deposit_item_by_name
        def fail_after_grant(*args, **kwargs):
            actual(*args, **kwargs)
            raise ValueError('Synthetic late reward failure')
        with mock.patch.object(breeding.storage, 'store_deposit_item_by_name', side_effect=fail_after_grant):
            self.rejected(lambda: breeding.finish(self.save, job, now=job['finish_ts']))
        first = breeding.finish(self.save, job, now=job['finish_ts'])['reward']
        self.assertIsNotNone(first)

    def test_progression_threshold_awards_real_potion_and_milestone_bottles(self):
        self.save['breedingSkillStates'] = {breeding.FEATURE: {'featureName': breeding.FEATURE, 'xp': 6,
            'level': 1, 'milestones': [True, True]}}
        job = self.begin(5)
        breeding.finish(self.save, job, now=NOW)
        self.assertEqual(self.save['breedingSkillStates'][breeding.FEATURE],
                         {'featureName': breeding.FEATURE, 'xp': 0, 'level': 2, 'milestones': [False, False]})
        self.assertEqual(self.save['userInfo']['player']['storageData']['-1']['gk'][0], 1)

    def test_real_animal_limit_and_duplicate_content_reject(self):
        self.pen['contents'][0]['numItem'] = 99
        self.rejected(lambda: self.begin())
        self.pen['contents'][0]['numItem'] = 1
        self.pen['contents'].append({'itemCode': 'cx', 'numItem': 1})
        self.rejected(lambda: self.begin())

    def test_pending_and_claimed_state_survive_atomic_json_restart(self):
        job = self.begin(1)
        with tempfile.TemporaryDirectory(prefix='farmvillage-breeding-restart-') as directory:
            path = Path(directory) / 'synthetic-farm.json'
            persistence.atomic_json(path, self.save)
            restored = persistence.read_json(path)
            result = breeding.finish(restored, job, now=job['finish_ts'])
            self.assertIsNotNone(result['reward'])
            persistence.atomic_json(path, restored)
            restored = persistence.read_json(path)
            before = copy.deepcopy(restored)
            self.assertIsNone(breeding.finish(restored, job, now=job['finish_ts'] + 1)['reward'])
            self.assertEqual(restored, before)

    def test_ordinary_snapshots_cannot_replace_parents_queue_or_metadata(self):
        self.begin()
        stored = self.current_pen()
        incoming = {'id': 71, 'itemName': breeding.FEATURE, 'className': 'Animal', 'contents': [],
                    'storageMetadata': {'cx:injected': ['bad']}, 'extraDataState': {'breedingQueue': []},
                    'position': {'x': 7, 'y': 8}}
        result = breeding.preserve_fields(stored, incoming)
        for field in ('itemName', 'className', 'contents', 'storageMetadata', 'extraDataState'):
            self.assertEqual(result[field], stored[field])
        self.assertEqual(result['position'], incoming['position'])
        self.assertEqual(breeding.initialize_placement(incoming)['contents'], [{'itemCode': 'ng', 'numItem': 1}])
        self.assertEqual(breeding.initialize_placement(incoming)['extraDataState']['breedingQueue'], [])


    def test_offspring_gift_placement_keeps_exact_dna_then_world_moves_preserve_it(self):
        job = self.begin(5)
        reward = breeding.finish(self.save, job, now=NOW)['reward']
        snapshot = {'id': 92, 'itemName': 'sheeppen_lamb', 'className': 'MutableAnimalBaby', 'state': 'construction',
                    'position': {'x': 7, 'y': 4}, 'mutableAnimalState': {'dna': {'injected': True}},
                    'isFullyBuilt': True, 'contents': [{'itemCode': 'B8', 'numItem': 10}],
                    'expansionParts': {'B8': 10}, 'capacity': 999}
        params = [{'isGift': True, 'giftMetadataIndex': 0, 'metadata': reward['mutableState']}]
        self.assertTrue(breeding.withdraw_for_placement(self.save, 'sheeppen_lamb', params, snapshot, now=NOW))
        self.assertEqual(snapshot['mutableAnimalState']['dna'], json.loads(reward['mutableState']))
        self.assertEqual(snapshot['contents'], [])
        self.assertFalse(snapshot['isFullyBuilt'])
        self.assertNotIn('capacity', snapshot); self.assertNotIn('expansionParts', snapshot)
        self.assertNotIn('cy', self.save['userInfo']['player']['storageData']['-1'])
        moved = breeding.preserve_fields(snapshot, dict(snapshot, mutableAnimalState={'dna': {'injected': True}},
                                                      position={'x': 9, 'y': 10}))
        self.assertEqual(moved['mutableAnimalState'], snapshot['mutableAnimalState'])
        with tempfile.TemporaryDirectory(prefix='farmvillage-breeding-placement-') as directory:
            path = Path(directory) / 'synthetic.json'
            persistence.atomic_json(path, moved)
            self.assertEqual(persistence.read_json(path)['mutableAnimalState']['dna'], json.loads(reward['mutableState']))

    def test_forged_or_wrong_index_offspring_placement_cannot_consume_another_gift(self):
        job = self.begin(5)
        reward = breeding.finish(self.save, job, now=NOW)['reward']
        snapshot = {'id': 92, 'itemName': 'sheeppen_lamb', 'className': 'MutableAnimalBaby'}
        changed = json.loads(reward['mutableState']); changed['G'] = 'M' if changed['G'] == 'F' else 'F'
        for metadata, index in ((json.dumps(changed), 0), (reward['mutableState'], 3), (None, -1)):
            self.rejected(lambda: breeding.withdraw_for_placement(self.save, 'sheeppen_lamb',
                [{'isGift': True, 'giftMetadataIndex': index, 'metadata': metadata}], snapshot, now=NOW))

    def test_exact_adult_world_to_pen_and_pen_to_inventory_to_world_roundtrip(self):
        self.save['world']['objectsArray'].append({'id': 90, 'itemName': 'toolshedpink',
            'className': 'StorageBuilding', 'state': 'built'})
        dna = copy.deepcopy(breeding._config()['variants']['sheeppen_ram'])
        dna['N'] = 'Own Ram'; dna['P']['T'] = 'b'
        adult = {'id': 84, 'itemName': 'sheeppen_ram', 'className': 'MutableAnimal', 'mutableAnimalState': {'dna': dna}}
        self.save['world']['objectsArray'].append(adult)
        options = {'storedItemName': 'sheeppen_ram', 'resource': 84, 'numToStore': 1, 'metadata': {'type': json.dumps(dna)}}
        self.assertTrue(breeding.store_for_game(self.save, {'id': 71, 'itemName': breeding.FEATURE}, options, now=NOW))
        key = 'cx:' + breeding.dna_hash(dna)
        self.assertEqual(json.loads(self.current_pen()['storageMetadata'][key][0]), dna)
        self.assertEqual(self.current_pen()['contents'][0]['numItem'], 2)
        options = {'storedItemName': 'sheeppen_ram', 'cameFromLocation': 71, 'target': -2,
                   'numToStore': 1, 'metadata': json.dumps(dna)}
        self.assertTrue(breeding.store_for_game(self.save, {'id': 71}, options, now=NOW))
        self.assertNotIn(key, self.current_pen()['storageMetadata'])
        self.assertEqual(self.save['userInfo']['player']['storageData']['-2'][key][0], 1)
        snapshot = {'id': 85, 'itemName': 'sheeppen_ram', 'className': 'MutableAnimal'}
        self.assertTrue(breeding.withdraw_for_placement(self.save, 'sheeppen_ram',
            [{'isInventoryWithdrawal': True, 'metadata': json.dumps(dna)}], snapshot, now=NOW))
        # Placement repairs the legacy scalar gene to the original client Array
        # while preserving the animal's identity and every other DNA field.
        expected_dna = copy.deepcopy(dna)
        expected_dna['P']['T'] = ['b']
        placed_dna = snapshot['mutableAnimalState']['dna']
        self.assertEqual(placed_dna, expected_dna)
        self.assertEqual(breeding.dna_hash(placed_dna), breeding.dna_hash(dna))
        self.assertNotIn(key, self.save['userInfo']['player']['storageData']['-2'])

    def test_reserved_parent_generic_storage_bypass_and_progress_injection_reject(self):
        self.begin()
        self.rejected(lambda: breeding.guard_storage_withdrawal(self.save, items.get_item_by_code('cx'), 1, 71))
        self.rejected(lambda: breeding.guard_action(self.save, 'plow', self.current_pen(), {'className': 'Plow'}, now=NOW))
        self.rejected(lambda: breeding.guard_action(self.save, 'sell', self.current_pen(), {}, now=NOW))
        self.rejected(lambda: breeding.guard_storage(self.save, {'id': 71}, {'storedItemName': 'cow'}, now=NOW))
        result = breeding.preserve_fields(self.current_pen(), dict(self.current_pen(), expansionLevel=3, isFullyBuilt=True))
        self.assertEqual(result['expansionLevel'], 1)

    def test_same_second_completed_suite_rejects_new_purchase_before_charging(self):
        job = self.begin(5)
        breeding.finish(self.save, job, now=NOW)
        self.rejected(lambda: self.begin(5))
        self.begin(5, now=NOW + 1)



    def test_pattern_skill_gate_and_level_thirty_capacity_use_original_rewards(self):
        dna = copy.deepcopy(breeding._config()['variants']['sheeppen_ram'])
        dna['P']['T'] = 'm'  # tigerstripe unlocks at original skill level5.
        key = 'cx:' + breeding.dna_hash(dna)
        self.pen['storageMetadata'][key] = [json.dumps(dna)]
        raw = dict(self.raw, breedObjs=[{'hash': key}, {'hash': 'cw:'}])
        self.rejected(lambda: breeding.begin(self.save, raw, now=NOW))
        self.save['breedingSkillStates'] = {breeding.FEATURE: {'level': 5, 'xp': 0, 'milestones': [False, False]}}
        breeding.begin(self.save, raw, now=NOW)
        fresh = copy.deepcopy(self.initial)
        fresh['world']['objectsArray'] = [copy.deepcopy(self.pen)]
        fresh['world']['objectsArray'][0]['storageMetadata'] = {}
        fresh['world']['objectsArray'][0]['contents'][0]['numItem'] = 100
        fresh['userInfo']['player'].update(cash=100, storageData={})
        fresh['breedingSkillStates'] = {breeding.FEATURE: {'level': 30, 'xp': 0, 'milestones': [False, False]}}
        breeding.begin(fresh, self.raw, now=NOW)
        self.assertIsNotNone(fresh['world']['objectsArray'][0]['extraDataState']['breedingQueue'][0])

    def test_new_pen_snapshot_and_wrong_world_identity_cannot_unlock_or_inject_animals(self):
        import_snapshot = dict(self.pen, expansionLevel=3, capacity=999)
        initialized = breeding.initialize_placement(import_snapshot)
        self.assertEqual((initialized['expansionLevel'], initialized['capacity']), (1, 20))
        self.rejected(lambda: breeding.guard_action(self.save, 'move',
            {'id': 7, 'itemName': 'cow', 'className': 'Animal'},
            {'id': 7, 'itemName': 'sheeppen_ram', 'className': 'MutableAnimal'}, now=NOW))
        self.rejected(lambda: breeding.withdraw_for_placement(self.save, 'sheeppen_lamb', [],
            {'id': 7, 'itemName': 'sheeppen_lamb', 'className': 'MutableAnimalBaby'}, now=NOW))



    def test_new_finished_pen_seeds_only_the_catalog_default_ram_and_exact_original_dna(self):
        snapshot = {'id': 9, 'itemName': breeding.FEATURE, 'className': 'FeatureBuilding', 'state': 'built',
                    'isFullyBuilt': True, 'contents': [{'itemCode': 'cx', 'numItem': 999}]}
        initialized = breeding.initialize_placement(snapshot)
        self.assertEqual(initialized['contents'], [{'itemCode': 'ng', 'numItem': 1}])
        dna = breeding._config()['variants']['sheeppen_ram_quest0203']
        key = 'ng:' + breeding.dna_hash(dna)
        self.assertEqual(json.loads(initialized['storageMetadata'][key][0]), dna)
        self.assertEqual(dna['P']['T'], ['c'])
        self.assertEqual(initialized['state'], 'built')
        self.assertEqual(initialized['extraDataState']['breedingQueue'], [])
        self.assertNotIn('breedingSkillStates', self.save)

    def test_legacy_scalar_pattern_repair_preserves_identity_both_worlds_and_storage(self):
        dna = copy.deepcopy(breeding._config()['variants']['ewePlain'])
        dna['N'] = 'Legacy Lamb'; dna['P']['T'] = 'a'; dna['unknown'] = {'keep': [1, 2]}
        packed = json.dumps(dna)
        expected = copy.deepcopy(dna); expected['P']['T'] = ['a']
        identity = breeding.dna_hash(dna)
        baby = {'id': 603, 'itemName': 'sheeppen_lamb', 'className': 'MutableAnimalBaby',
                'contents': [], 'mutableAnimalState': {'dna': copy.deepcopy(dna)}, 'metadata': packed}
        untouched = {'id': 605, 'itemName': 'cow', 'className': 'Animal',
                     'mutableAnimalState': {'dna': copy.deepcopy(dna)}}
        self.save['world']['objectsArray'].extend([baby, untouched])
        self.pen['storageMetadata'] = {'cw:' + identity: [packed]}
        self.player['storageData'] = {'-1': {'cy': [2, ['sender'], [packed, 'unrelated']]},
                                     '-2': {'cw:' + identity: [1, [], [packed]], 'unknown': [1, [], [packed]]}}
        self.save['userInfo']['currentWorldType'] = 'farm'
        self.save['userInfo']['worldSummaryData']['farm']['storageId'] = -2
        self.save['userInfo']['worldSummaryData']['england'] = {'storageId': -8}
        inactive = copy.deepcopy(baby); inactive['id'] = 604
        self.save['_ownedWorldTravel'] = {'version': 1, 'nextObjectId': 606, 'inactive': {
            'england': {'sizeX': 24, 'sizeY': 24, 'objectsArray': [inactive]}}}
        breeding.normalize_legacy_dna(self.save)
        for obj in (baby, inactive):
            self.assertEqual(obj['mutableAnimalState']['dna'], expected)
            self.assertEqual(json.loads(obj['metadata']), expected)
            self.assertEqual(breeding.dna_hash(obj['mutableAnimalState']['dna']), identity)
        self.assertEqual(json.loads(self.pen['storageMetadata']['cw:' + identity][0]), expected)
        self.assertEqual(json.loads(self.player['storageData']['-1']['cy'][2][0]), expected)
        self.assertEqual(self.player['storageData']['-1']['cy'][:2], [2, ['sender']])
        self.assertEqual(self.player['storageData']['-1']['cy'][2][1], 'unrelated')
        self.assertEqual(json.loads(self.player['storageData']['-2']['cw:' + identity][2][0]), expected)
        self.assertEqual(self.player['storageData']['-2']['unknown'][2][0], packed)
        self.assertEqual(untouched['mutableAnimalState']['dna'], dna)
        normalized = copy.deepcopy(self.save)
        breeding.normalize_legacy_dna(self.save)
        self.assertEqual(self.save, normalized)


if __name__ == '__main__':
    unittest.main()
