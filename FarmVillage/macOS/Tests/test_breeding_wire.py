"""Original breeding requests and exact offspring placement through real AMF."""
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures  # Temporary storage must precede all product imports.
from pyamf import remoting


class BreedingWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    def prepare(self):
        import breeding
        path = self.write_fixture()
        save = self.player.session('fixture-farmer')
        save['userInfo']['player']['cash'] = 100
        parents = [('cx', breeding._config()['variants']['ramPlain']),
                   ('cw', breeding._config()['variants']['ewePlain'])]
        metadata = {code + ':' + breeding.dna_hash(dna): [json.dumps(dna, separators=(',', ':'))]
                    for code, dna in parents}
        save['world']['objectsArray'] = [{'id': 71, 'itemName': breeding.FEATURE, 'className': 'FeatureBuilding',
            'state': 'built', 'isFullyBuilt': True, 'expansionLevel': 1, 'position': {'x': 2, 'y': 5, 'z': 0},
            'contents': [{'itemCode': 'cx', 'numItem': 1}, {'itemCode': 'cw', 'numItem': 1}],
            'storageMetadata': metadata, 'extraDataState': {'breedHistory': {}, 'breedingQueue': []}}]
        with redirect_stdout(io.StringIO()):
            self.player.save_session('fixture-farmer')
        raw = {'buildingId': 71, 'suiteSlot': 0, 'numPotions': 5, 'start_ts': 0, 'finish_ts': 0,
               'breedObjs': [{'hash': key} for key in metadata], 'patternGuarantee': False}
        return path, raw

    def send(self, method, params, sequence=1):
        response = self.gateway([self.command(method, params, sequence)])
        self.assertEqual(response.status_code, 200, response.data)
        return remoting.decode(response.data).bodies[0][1].body['data'][0]['data']

    def start(self):
        path, raw = self.prepare()
        with mock.patch('breeding.random.getrandbits', return_value=1):
            result = self.send('AnimalBreedingService.onBeginBreeding', [raw])
        job = result['extraDataState']['breedingQueue'][0]
        return path, raw, job

    def test_actual_nested_parent_packet_birth_gift_place_move_reload_and_init(self):
        import breeding
        path, raw, job = self.start()
        self.assertEqual(job['breedObjs'], raw['breedObjs'])
        self.assertEqual(job['finish_ts'], job['start_ts'])
        result = self.send('AnimalBreedingService.onFinishBreeding', [job], 2)
        packed = result['reward']['mutableState']
        expected = json.loads(packed)
        save = self.player.session('fixture-farmer')
        self.assertEqual(save['userInfo']['player']['storageData']['-1']['cy'], [1, [], [packed]])
        snapshot = {'id': 64000, 'tempId': -1, 'itemName': 'sheeppen_lamb', 'className': 'MutableAnimalBaby',
                    'state': 'construction', 'position': {'x': 10, 'y': 10, 'z': 0}, 'contents': []}
        placed = self.send('WorldService.performAction', ['place', snapshot,
            [{'isGift': True, 'isStorageWithdrawal': 0, 'giftMetadataIndex': 0, 'metadata': packed}]], 3)
        ident = int(placed['id'])
        saved = next(obj for obj in self.player.session('fixture-farmer')['world']['objectsArray'] if obj['id'] == ident)
        self.assertEqual(saved['mutableAnimalState']['dna'], expected)
        moved = copy.deepcopy(snapshot)
        moved.update(id=ident, position={'x': 12, 'y': 12, 'z': 0}, mutableAnimalState={'dna': {'forged': True}})
        self.send('WorldService.performAction', ['move', moved, []], 4)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        reloaded = self.player.session('fixture-farmer')
        baby = next(obj for obj in reloaded['world']['objectsArray'] if obj['id'] == ident)
        self.assertEqual(baby['mutableAnimalState']['dna'], expected)
        self.assertNotIn('cy', reloaded['userInfo']['player']['storageData']['-1'])
        initialized = self.send('UserService.initUser', ['Breeding fixture', 0, True, None], 5)
        self.assertNotIn('_animalBreeding', initialized)
        self.assertEqual(initialized['breedingSkillStates'][breeding.FEATURE]['xp'], 3)
        self.assertEqual(json.loads(path.read_text())['world']['objectsArray'][-1]['mutableAnimalState']['dna'], expected)

    def test_browser_empty_baby_contents_placement_reload_and_owned_world_repair(self):
        path, raw, job = self.start()
        result = self.send('AnimalBreedingService.onFinishBreeding', [job], 2)
        packed = result['reward']['mutableState']
        expected_dna = json.loads(packed)
        snapshot = {'id': 64000, 'tempId': -1, 'itemName': 'sheeppen_lamb',
                    'className': 'MutableAnimalBaby', 'state': 'built',
                    'position': {'x': 20, 'y': 26, 'z': 0}, 'contents': {}}
        placed = self.send('WorldService.performAction', ['place', snapshot,
            [{'isGift': True, 'isStorageWithdrawal': 0, 'giftMetadataIndex': 0, 'metadata': packed}]], 3)
        ident = int(placed['id'])
        save = self.player.session('fixture-farmer')
        baby = next(obj for obj in save['world']['objectsArray'] if obj['id'] == ident)
        self.assertEqual(baby['contents'], [])
        self.assertEqual(baby['mutableAnimalState']['dna'], expected_dna)
        # The actual later move packet must not reintroduce the Object shape.
        self.send('WorldService.performAction', ['move', dict(snapshot, id=ident), []], 4)
        self.assertEqual(next(obj for obj in save['world']['objectsArray'] if obj['id'] == ident)['contents'], [])
        # Model an earlier persisted browser placement and an inactive world.
        # All writes here are the isolated fixture, never a real game save.
        baby = next(obj for obj in save['world']['objectsArray'] if obj['id'] == ident)
        baby['contents'] = {}
        untouched = dict(copy.deepcopy(baby), id=800, contents={'owned': 'retain'})
        inactive = dict(copy.deepcopy(baby), id=801, contents={})
        ordinary = {'id': 802, 'className': 'Building', 'contents': {}}
        save['userInfo']['currentWorldType'] = 'farm'
        save['userInfo']['worldSummaryData']['farm']['storageId'] = -2
        save['userInfo']['worldSummaryData']['england'] = {'storageId': -8}
        save['_ownedWorldTravel'] = {'version': 1, 'nextObjectId': 803, 'inactive': {
            'england': {'sizeX': 24, 'sizeY': 24, 'objectsArray': [untouched, inactive, ordinary]}}}
        with redirect_stdout(io.StringIO()):
            self.player.save_session('fixture-farmer')
            self.player.load_saves()
        initialized = self.send('UserService.initUser', ['Breeding fixture', 0, True, None], 5)
        loaded_baby = next(obj for obj in initialized['world']['objectsArray'] if obj['id'] == ident)
        self.assertEqual(loaded_baby['contents'], [])
        self.assertEqual(loaded_baby['mutableAnimalState']['dna'], expected_dna)
        persisted = json.loads(path.read_text())
        others = persisted['_ownedWorldTravel']['inactive']['england']['objectsArray']
        self.assertEqual([obj['contents'] for obj in others], [{'owned': 'retain'}, [], {}])
        self.assertEqual(others[1]['mutableAnimalState']['dna'], expected_dna)

    def test_actual_world_storage_and_init_supply_complete_parent_preview_dna(self):
        import breeding
        path, raw = self.prepare()
        save = self.player.session('fixture-farmer')
        pen = save['world']['objectsArray'][0]
        packed_parents = copy.deepcopy(pen['storageMetadata'])
        pen.update(contents=[], storageMetadata={})
        save['userInfo']['player']['storageData'].pop('71', None)
        for ident, (code, item_name), parent in zip((84, 85),
                (('cx', 'sheeppen_ram'), ('cw', 'sheeppen_ewe')), raw['breedObjs']):
            packed = packed_parents[parent['hash']][0]
            save['world']['objectsArray'].append({'id': ident, 'itemName': item_name,
                'className': 'MutableAnimal', 'state': 'static',
                'position': {'x': ident - 75, 'y': 10, 'z': 0},
                'mutableAnimalState': {'dna': json.loads(packed)}})
        with redirect_stdout(io.StringIO()):
            self.player.save_session('fixture-farmer')
        for sequence, (ident, item_name, parent) in enumerate(zip((84, 85),
                ('sheeppen_ram', 'sheeppen_ewe'), raw['breedObjs']), 1):
            packed = packed_parents[parent['hash']][0]
            self.send('WorldService.performAction', ['store',
                {'id': 71, 'itemName': breeding.FEATURE, 'className': 'FeatureBuilding'},
                [{'storedItemName': item_name, 'resource': ident, 'numToStore': 1,
                  'metadata': {'type': packed}}]], sequence)
        initialized = self.send('UserService.initUser', ['Breeding fixture', 0, True, None], 3)
        loaded = next(obj for obj in initialized['world']['objectsArray'] if obj['id'] == 71)
        self.assertEqual(loaded['storageMetadata'], packed_parents)
        self.assertEqual(loaded['contents'], [{'itemCode': 'cx', 'numItem': 1}, {'itemCode': 'cw', 'numItem': 1}])
        for parent in raw['breedObjs']:
            dna = json.loads(loaded['storageMetadata'][parent['hash']][0])
            self.assertEqual(parent['hash'].split(':')[1], breeding.dna_hash(dna))
            for layer in ('B', 'P'):
                for channel in ('H', 'S', 'V'):
                    self.assertEqual(len(dna[layer][channel]), 2)
        result = self.send('AnimalBreedingService.onBeginBreeding', [raw], 4)
        self.assertEqual(result['extraDataState']['breedingQueue'][0]['breedObjs'], raw['breedObjs'])

    def test_retried_begin_and_claim_neither_recharge_nor_duplicate_offspring(self):
        path, raw, job = self.start()
        save = self.player.session('fixture-farmer')
        self.assertEqual(save['userInfo']['player']['cash'], 90)
        result = self.send('AnimalBreedingService.onBeginBreeding', [raw], 2)
        self.assertEqual(result['extraDataState']['breedingQueue'][0]['start_ts'], job['start_ts'])
        self.assertEqual(self.player.session('fixture-farmer')['userInfo']['player']['cash'], 90)
        self.send('AnimalBreedingService.onFinishBreeding', [job], 3)
        result = self.send('AnimalBreedingService.onFinishBreeding', [job], 4)
        self.assertIsNone(result['reward'])
        self.assertEqual(self.player.session('fixture-farmer')['userInfo']['player']['storageData']['-1']['cy'][0], 1)
        self.assertEqual(json.loads(path.read_text())['userInfo']['player']['cash'], 90)

    def test_actual_indexed_parent_maps_begin_retry_finish_and_reload(self):
        for key_type in (int, str):
            with self.subTest(key_type=key_type.__name__):
                path, raw = self.prepare()
                expected = copy.deepcopy(raw['breedObjs'])
                raw['breedObjs'] = {key_type(index): parent for index, parent in enumerate(expected)}
                result = self.send('AnimalBreedingService.onBeginBreeding', [raw])
                job = result['extraDataState']['breedingQueue'][0]
                self.assertEqual(job['breedObjs'], expected)
                self.assertEqual(self.player.session('fixture-farmer')['userInfo']['player']['cash'], 90)
                # The list response and indexed request identify the same job.
                self.send('AnimalBreedingService.onBeginBreeding', [dict(raw, breedObjs=expected)], 2)
                self.assertEqual(self.player.session('fixture-farmer')['userInfo']['player']['cash'], 90)
                finish = dict(job, breedObjs={key_type(index): parent for index, parent in enumerate(expected)})
                claimed = self.send('AnimalBreedingService.onFinishBreeding', [finish], 3)
                self.assertIsInstance(claimed['reward']['mutableState'], str)
                self.assertIsNone(self.send('AnimalBreedingService.onFinishBreeding', [job], 4)['reward'])
                with redirect_stdout(io.StringIO()):
                    self.player.load_saves()
                saved = json.loads(path.read_text())
                self.assertEqual(saved['userInfo']['player']['cash'], 90)
                self.assertEqual(saved['userInfo']['player']['storageData']['-1']['cy'][0], 1)

    def test_parent_maps_with_holes_extra_keys_or_invalid_rows_are_atomic(self):
        path, raw = self.prepare()
        first, second = raw['breedObjs']
        for parents in ({0: first}, {0: first, 2: second}, {'0': first, '2': second},
                        {0: first, 1: second, 2: first}, {'0': first, '1': second, 'extra': first},
                        {'0': first, '1': dict(second, unexpected=True)}):
            with self.subTest(parents=parents):
                before = path.read_bytes()
                memory = copy.deepcopy(self.player.session('fixture-farmer'))
                response = self.gateway([self.command('AnimalBreedingService.onBeginBreeding',
                                                      [dict(raw, breedObjs=parents)])])
                fixtures.assert_gateway_rejected(self, response)
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(self.player.session('fixture-farmer'), memory)

    def test_foreign_parent_and_locked_suite_fail_without_save_mutation(self):
        path, raw = self.prepare()
        for changes in ({'buildingId': 72}, {'suiteSlot': 1},
                        {'breedObjs': [{'hash': 'cx:12345678'}, {'hash': 'cw:'}]}):
            before = path.read_bytes()
            response = self.gateway([self.command('AnimalBreedingService.onBeginBreeding', [dict(raw, **changes)])])
            fixtures.assert_gateway_rejected(self, response)
            self.assertEqual(path.read_bytes(), before)

    def test_unsupported_breeding_service_does_not_fake_success(self):
        path, _ = self.prepare()
        before = path.read_bytes()
        response = self.gateway([self.command('AnimalBreedingService.onTradeCollection', ['fake'])])
        fixtures.assert_gateway_rejected(self, response)
        self.assertEqual(path.read_bytes(), before)

    def test_rejected_followup_keeps_paid_breeding_queue_and_retry_receipts(self):
        path, raw = self.prepare()
        response = self.gateway([
            self.command('AnimalBreedingService.onBeginBreeding', [raw]),
            self.command('AnimalBreedingService.onFinishBreeding', [dict(raw, start_ts=1)], 2),
        ])
        fixtures.gateway_results(self, response, [0, 29])
        saved = json.loads(path.read_text())
        self.assertEqual(saved['userInfo']['player']['cash'], 90)
        self.assertEqual(len(saved['world']['objectsArray'][0]['extraDataState']['breedingQueue']), 1)
        self.assertIn('_animalBreeding', saved)
        self.send('AnimalBreedingService.onBeginBreeding', [raw])
        self.assertEqual(json.loads(path.read_text()), saved)

    def test_pending_parent_withdrawal_and_plow_cannot_bypass_server_queue(self):
        path, _, _ = self.start()
        before = path.read_bytes()
        snapshot = {'id': 64000, 'itemName': 'sheeppen_ram', 'className': 'MutableAnimal',
                    'position': {'x': 10, 'y': 10, 'z': 0}, 'state': 'static'}
        response = self.gateway([self.command('WorldService.performAction', ['place', snapshot,
            [{'isStorageWithdrawal': 71}]], 2)])
        fixtures.assert_gateway_rejected(self, response)
        self.assertEqual(path.read_bytes(), before)
        response = self.gateway([self.command('WorldService.performAction', ['plow',
            {'id': 71, 'className': 'Plow', 'itemName': None, 'position': {'x': 1, 'y': 1}}, []], 3)])
        fixtures.assert_gateway_rejected(self, response)
        self.assertEqual(path.read_bytes(), before)

    def baby(self, *, gender='F', bottles=0, cash=100, gifts=10):
        import breeding
        path, _ = self.prepare()
        save = self.player.session('fixture-farmer')
        dna = copy.deepcopy(breeding._config()['variants']['ewePlain'])
        dna.update(G=gender, N='Original Lamb')
        baby = {'id': 603, 'itemName': 'sheeppen_lamb', 'className': 'MutableAnimalBaby',
                'state': 'construction', 'isFullyBuilt': False, 'direction': 2,
                'position': {'x': 20, 'y': 26, 'z': 0}, 'contents': [],
                'mutableAnimalState': {'dna': dna}, 'importedAnimal': {'keep': True}}
        save['world']['objectsArray'] = [baby]
        save['userInfo']['player'].update(cash=cash, storageData={'-1': {'B8': [gifts, [], []]}})
        if bottles:
            baby['contents'] = [{'itemCode': 'B8', 'numItem': bottles}]
            save['userInfo']['player']['storageData']['603'] = {'B8': [bottles, [], []]}
        with redirect_stdout(io.StringIO()):
            self.player.save_session('fixture-farmer')
        snapshot = {key: copy.deepcopy(baby[key]) for key in ('id', 'itemName', 'className', 'position', 'direction')}
        snapshot.update(state='built', contents={})  # Actual optimistic TBuildingPlace shape.
        return path, save, snapshot, copy.deepcopy(dna)

    def bottle(self, snapshot, *, count=1, sequence=1, **options):
        return self.send('WorldService.performAction', ['store', copy.deepcopy(snapshot),
            [dict(storedItemName='bottle', storedItemCode='B8', numToStore=count, isGift=True, **options)]], sequence)

    def test_original_rename_packet_changes_only_name_and_survives_reload(self):
        import breeding
        path, save, snapshot, dna = self.baby()
        args = ['cy', breeding.dna_hash(dna), 'Willow 2', 603, None]
        self.assertEqual(self.send('AnimalBreedingService.onSetAnimalName', args), {})
        expected = dict(dna, N='Willow 2')
        self.assertEqual(save['world']['objectsArray'][0]['mutableAnimalState']['dna'], expected)
        self.assertEqual(breeding.dna_hash(expected), breeding.dna_hash(dna))
        forged = dict(snapshot, mutableAnimalState={'dna': dict(dna, N='Injected', G='M')},
                      contents=[{'itemCode': 'B8', 'numItem': 10}], isFullyBuilt=True)
        self.send('WorldService.performAction', ['move', forged, [{'x': 21, 'y': 26, 'state': 'built'}]], 2)
        obj = save['world']['objectsArray'][0]
        self.assertEqual(obj['mutableAnimalState']['dna'], expected)
        self.assertEqual(obj['contents'], [])
        self.assertFalse(obj['isFullyBuilt']); self.assertEqual(obj['state'], 'construction')
        with redirect_stdout(io.StringIO()): self.player.load_saves()
        self.assertEqual(self.player.session('fixture-farmer')['world']['objectsArray'][0]['mutableAnimalState']['dna'], expected)
        self.assertEqual(json.loads(path.read_text())['world']['objectsArray'][0]['mutableAnimalState']['dna'], expected)

    def test_rename_rejects_wrong_hash_code_name_storage_context_and_foreign_identity_atomically(self):
        import breeding
        path, save, snapshot, dna = self.baby()
        args = ['cy', breeding.dna_hash(dna), 'Willow', 603, None]
        for index, value in ((0, 'cw'), (1, 'forged'), (2, 'A' * 21), (2, 'Name!'),
                             (3, 604), (3, -1), (4, {'id': 71})):
            altered = list(args); altered[index] = value
            before = path.read_bytes(); memory = copy.deepcopy(save)
            response = self.gateway([self.command('AnimalBreedingService.onSetAnimalName', altered)])
            fixtures.assert_gateway_rejected(self, response)
            self.assertEqual(path.read_bytes(), before); self.assertEqual(save, memory)

    def test_partial_bottle_gift_deposit_and_original_empty_move_snapshot_reload(self):
        path, save, snapshot, dna = self.baby(gifts=12)
        self.assertEqual(self.bottle(snapshot, count=3), {'id': 603})
        obj = save['world']['objectsArray'][0]
        self.assertEqual(obj['contents'], [{'itemCode': 'B8', 'numItem': 3}])
        self.assertEqual(save['userInfo']['player']['storageData']['-1']['B8'][0], 9)
        self.assertEqual(save['userInfo']['player']['cash'], 100)
        self.send('WorldService.performAction', ['move', snapshot, []], 2)
        with redirect_stdout(io.StringIO()): self.player.load_saves()
        obj = self.player.session('fixture-farmer')['world']['objectsArray'][0]
        self.assertEqual(obj['contents'], [{'itemCode': 'B8', 'numItem': 3}])
        self.assertEqual(obj['mutableAnimalState']['dna'], dna)
        self.assertNotIn('response', json.loads(path.read_text())['_animalBreeding'])

    def test_tenth_bottle_transforms_exact_saved_gender_name_dna_and_identity(self):
        for gender, adult in (('F', 'sheeppen_ewe'), ('M', 'sheeppen_ram')):
            with self.subTest(gender=gender):
                path, save, snapshot, dna = self.baby(gender=gender, bottles=9, gifts=2)
                forged = dict(snapshot, mutableAnimalState={'dna': dict(dna, G='M' if gender == 'F' else 'F')})
                with mock.patch('commands.timestamp_now', return_value=1_700_000_000):
                    self.assertEqual(self.bottle(forged), {'id': 603, 'finishedName': adult})
                grown = save['world']['objectsArray'][0]
                self.assertEqual((grown['id'], grown['itemName'], grown['className'], grown['state']),
                                 (603, adult, 'MutableAnimal', 'bare'))
                self.assertEqual(grown['plantTime'], 1_700_000_000_000)
                self.assertEqual(grown['mutableAnimalState']['dna'], dna)
                self.assertEqual(grown['position'], snapshot['position'])
                self.assertEqual(grown['importedAnimal'], {'keep': True})
                self.assertNotIn('603', save['userInfo']['player']['storageData'])
                self.assertEqual(save['userInfo']['player']['storageData']['-1']['B8'][0], 1)
                self.assertEqual(save['userInfo']['player']['cash'], 100)
                self.assertNotIn('response', json.loads(path.read_text())['_animalBreeding'])

    def test_paid_bottle_uses_catalog_cash_and_complete_now_charges_only_missing_bottles(self):
        import progression
        path, save, snapshot, dna = self.baby(gifts=0)
        progression.refresh_owned(save)
        self.assertEqual(save['userInfo']['player']['stats']['buildings'], 1)
        result = self.send('WorldService.performAction', ['store', snapshot,
            [{'storedItemName': 'bottle', 'currency': 'cash', 'numToStore': 2}]], 1)
        self.assertEqual(result, {'id': 603})
        self.assertEqual(save['userInfo']['player']['cash'], 98)
        with mock.patch('commands.timestamp_now', return_value=1_700_000_000):
            self.assertEqual(self.send('WorldService.performAction',
                ['TransformBuilding', snapshot, [{'firstWA': True}]], 2),
                {'id': 603, 'finishedName': 'sheeppen_ewe'})
        self.assertEqual(save['userInfo']['player']['cash'], 90)
        self.assertEqual(save['userInfo']['player']['stats']['buildings'], 0)
        self.assertEqual(save['world']['objectsArray'][0]['mutableAnimalState']['dna'], dna)
        with redirect_stdout(io.StringIO()): self.player.load_saves()
        self.assertEqual(self.player.session('fixture-farmer')['world']['objectsArray'][0]['itemName'], 'sheeppen_ewe')
        self.assertEqual(json.loads(path.read_text())['userInfo']['player']['cash'], 90)

    def test_original_england_lamb_objective_advances_once_for_bottles_and_paid_growth(self):
        import england_progression
        from game_settings import level_to_xp
        import quests
        import world_travel
        # Story restoration is deferred in the product. Exercise its preserved
        # lamb growth hook with an explicitly enabled, test-only catalog.
        story = mock.patch.object(england_progression, 'STORY_ENABLED', True)
        story.start()
        self.addCleanup(story.stop)
        catalog = mock.patch.object(quests, '_cached_quests', {
            **quests.get_quests(), **england_progression.quest_definitions()})
        catalog.start()
        self.addCleanup(catalog.stop)
        for action in ('bottle', 'complete'):
            with self.subTest(action=action):
                path, save, snapshot, _ = self.baby(bottles=9, gifts=2)
                lamb = copy.deepcopy(save['world']['objectsArray'][0]); lamb['id'] = 700
                ledger = copy.deepcopy(save['userInfo']['player']['storageData']['603'])
                save['userInfo']['player']['xp'] = level_to_xp(15)
                world_travel.switch(save, 'england', True, now=1_700_000_000)
                save['world']['objectsArray'] = [lamb]
                save['userInfo']['player']['storageData']['700'] = ledger
                snapshot = dict(snapshot, id=700)
                name = england_progression.QUEST_NAMES[-1]
                save['questState'] = {'active': {name: {'progress': [1, 0], 'new': 0}},
                                     'completed': list(england_progression.QUEST_NAMES[:-1]), 'retired': [], 'replayed': {}}
                with redirect_stdout(io.StringIO()): self.player.save_session('fixture-farmer')
                with mock.patch.object(quests, 'record_action', wraps=quests.record_action) as record:
                    if action == 'bottle':
                        expected = self.bottle(snapshot)
                        self.assertEqual(self.bottle(snapshot), expected)
                    else:
                        args = ['TransformBuilding', snapshot, []]
                        expected = self.send('WorldService.performAction', args, 1)
                        self.assertEqual(self.send('WorldService.performAction', args, 1), expected)
                events = [call for call in record.call_args_list
                          if call.args[1:3] == ('completeConstructionBuildingByCode', 'cy')]
                self.assertEqual(len(events), 1)
                self.assertEqual(save['questState']['active'][name]['progress'], [1, 1])
                with redirect_stdout(io.StringIO()): self.player.load_saves()
                self.assertEqual(self.player.session('fixture-farmer')['questState']['active'][name]['progress'], [1, 1])

    def test_bottle_and_complete_retry_receipts_survive_restart_and_reject_sequence_reuse(self):
        path, save, snapshot, dna = self.baby(gifts=20)
        self.bottle(snapshot, count=3)
        with redirect_stdout(io.StringIO()): self.player.load_saves()
        self.assertEqual(self.bottle(snapshot, count=3), {'id': 603})
        save = self.player.session('fixture-farmer')
        self.assertEqual(save['world']['objectsArray'][0]['contents'][0]['numItem'], 3)
        self.assertEqual(save['userInfo']['player']['storageData']['-1']['B8'][0], 17)
        result = self.send('WorldService.performAction', ['TransformBuilding', snapshot, []], 2)
        with redirect_stdout(io.StringIO()): self.player.load_saves()
        self.assertEqual(self.send('WorldService.performAction', ['TransformBuilding', snapshot, []], 2), result)
        self.assertEqual(self.player.session('fixture-farmer')['userInfo']['player']['cash'], 93)
        before = path.read_bytes()
        response = self.gateway([self.command('WorldService.performAction', ['store', snapshot,
            [{'storedItemName': 'bottle', 'isGift': True}]], 2)])
        fixtures.assert_gateway_rejected(self, response); self.assertEqual(path.read_bytes(), before)

    def test_missing_bottles_overfeed_wrong_material_currency_and_forged_target_never_mutate(self):
        path, save, snapshot, dna = self.baby(bottles=9, gifts=0, cash=0)
        packets = [
            ['store', snapshot, [{'storedItemName': 'bottle', 'isGift': True}]],
            ['store', snapshot, [{'storedItemName': 'bottle', 'numToStore': 2, 'currency': 'cash'}]],
            ['store', snapshot, [{'storedItemName': 'brick', 'currency': 'cash'}]],
            ['store', snapshot, [{'storedItemName': 'bottle', 'currency': 'coins'}]],
            ['store', dict(snapshot, itemName='cow', className='Animal'), [{'storedItemName': 'bottle', 'currency': 'cash'}]],
            ['TransformBuilding', snapshot, []],
            ['TransformBuilding', snapshot, [{'price': 0}]],
            ['TransformBuilding', dict(snapshot, id=999), []],
        ]
        for packet in packets:
            before = path.read_bytes(); memory = copy.deepcopy(save)
            response = self.gateway([self.command('WorldService.performAction', packet)])
            fixtures.assert_gateway_rejected(self, response)
            self.assertEqual(path.read_bytes(), before); self.assertEqual(save, memory)

    def test_rejected_followup_keeps_bottles_name_adult_and_retry_receipts(self):
        import breeding
        path, save, snapshot, dna = self.baby(gifts=2, bottles=8)
        before = path.read_bytes(); memory = copy.deepcopy(save)
        response = self.gateway([
            self.command('AnimalBreedingService.onSetAnimalName', ['cy', breeding.dna_hash(dna), 'Willow', 603, None], 1),
            self.command('WorldService.performAction', ['store', snapshot,
                [{'storedItemName': 'bottle', 'isGift': True}]], 2),
            self.command('WorldService.performAction', ['TransformBuilding', snapshot, []], 3),
            self.command('AnimalBreedingService.onSetAnimalName', ['cw', 'forged', 'Bad', 603, None], 4),
        ])
        fixtures.gateway_results(self, response, [0, 0, 0, 29])
        saved = json.loads(path.read_text())
        adult = saved['world']['objectsArray'][0]
        self.assertEqual(adult['mutableAnimalState']['dna']['N'], 'Willow')
        self.assertNotEqual(adult['itemName'], 'sheeppen_lamb')
        self.assertEqual(saved['userInfo']['player']['storageData']['-1']['B8'][0], 1)
        self.assertEqual(saved['userInfo']['player']['cash'], memory['userInfo']['player']['cash'] - 1)
        self.assertEqual(self.player.session('fixture-farmer'), saved)

    def test_lamb_requests_reject_inactive_world_and_cross_world_replay(self):
        import breeding
        from game_settings import level_to_xp
        path, save, snapshot, dna = self.baby()
        save['userInfo']['player']['xp'] = level_to_xp(15)
        self.bottle(snapshot)
        self.send('WorldService.loadOwnWorld', ['england', True, False, False], 2)
        before = path.read_bytes()
        packets = [('WorldService.performAction', ['store', snapshot,
                    [{'storedItemName': 'bottle', 'storedItemCode': 'B8', 'numToStore': 1, 'isGift': True}]], 1),
                   ('WorldService.performAction', ['TransformBuilding', snapshot, []], 3),
                   ('AnimalBreedingService.onSetAnimalName', ['cy', breeding.dna_hash(dna), 'Foreign', 603, None], 4)]
        for method, params, sequence in packets:
            response = self.gateway([self.command(method, params, sequence)])
            fixtures.assert_gateway_rejected(self, response)
            self.assertEqual(path.read_bytes(), before)

    def test_login_resets_only_request_receipts_and_keeps_bottle_progress_private(self):
        path, save, snapshot, dna = self.baby()
        self.bottle(snapshot, count=2)
        data = self.send('UserService.initUser', ['Lamb fixture', 0, True, None], 2)
        self.assertNotIn('_animalBreeding', data)
        self.assertEqual(data['world']['objectsArray'][0]['contents'][0]['numItem'], 2)
        self.assertNotIn('requests', save.get('_animalBreeding', {}))
        self.bottle(snapshot, count=3, sequence=1)
        self.assertEqual(save['world']['objectsArray'][0]['contents'][0]['numItem'], 5)
        self.assertEqual(save['userInfo']['player']['storageData']['-1']['B8'][0], 5)

    def test_fed_lamb_storage_cannot_discard_progress_and_adult_moves_cannot_reset_clock(self):
        path, save, snapshot, dna = self.baby(bottles=2)
        before = path.read_bytes()
        response = self.gateway([self.command('WorldService.performAction', ['store',
            snapshot, [{'storedItemName': 'sheeppen_lamb', 'target': -2, 'resource': 603, 'numToStore': 1}]], 1)])
        fixtures.assert_gateway_rejected(self, response); self.assertEqual(path.read_bytes(), before)
        save = self.player.session('fixture-farmer')
        with mock.patch('commands.timestamp_now', return_value=1_700_000_000):
            self.send('WorldService.performAction', ['TransformBuilding', snapshot, []], 2)
            grown = copy.deepcopy(save['world']['objectsArray'][0])
            forged = dict(grown, plantTime=0, state='grown', mutableAnimalState={'dna': {'forged': True}})
            self.send('WorldService.performAction', ['move', forged, []], 3)
            self.assertEqual(save['world']['objectsArray'][0]['plantTime'], grown['plantTime'])
            self.assertEqual(save['world']['objectsArray'][0]['state'], 'bare')
            self.assertEqual(save['world']['objectsArray'][0]['mutableAnimalState']['dna'], dna)

    def test_empty_lamb_original_inventory_storage_and_placement_preserve_exact_dna(self):
        import breeding
        path, save, snapshot, dna = self.baby()
        shed = {'id': 90, 'itemName': 'toolshedpink', 'className': 'StorageBuilding',
                'state': 'built', 'position': {'x': 14, 'y': 14, 'z': 0}}
        save['world']['objectsArray'].append(shed)
        packed = json.dumps(dna, separators=(',', ':'))
        self.send('WorldService.performAction', ['store',
            snapshot,
            [{'storedItemName': 'sheeppen_lamb', 'target': -2, 'resource': 603,
              'numToStore': 1, 'metadata': {'type': packed}}]], 1)
        self.assertEqual(save['world']['objectsArray'], [shed])
        key = 'cy:' + breeding.dna_hash(dna)
        self.assertEqual(save['userInfo']['player']['storageData']['-2'][key], [1, [], [packed]])
        placed = self.send('WorldService.performAction', ['place', dict(snapshot, id=64000),
            [{'isStorageWithdrawal': -2, 'metadata': packed}]], 2)
        obj = next(obj for obj in save['world']['objectsArray'] if obj['id'] == placed['id'])
        self.assertEqual(obj['id'], placed['id'])
        self.assertEqual(obj['mutableAnimalState']['dna'], dna)
        self.assertEqual(obj['contents'], []); self.assertFalse(obj['isFullyBuilt'])
        self.assertNotIn(key, save['userInfo']['player']['storageData']['-2'])

    def test_england_bottles_use_only_active_inventory_and_preserve_home_stock(self):
        from game_settings import level_to_xp
        path, save, snapshot, dna = self.baby()
        english_lamb = copy.deepcopy(save['world']['objectsArray'][0]); english_lamb['id'] = 700
        save['userInfo']['player']['xp'] = level_to_xp(15)
        self.send('WorldService.loadOwnWorld', ['england', True, False, False], 1)
        save['world']['objectsArray'] = [english_lamb]
        data = save['userInfo']['player']['storageData']
        data['-2'] = {'B8': [4, [], []]}; data['-8'] = {'B8': [2, [], []]}
        raw = dict(snapshot, id=700)
        with redirect_stdout(io.StringIO()): self.player.save_session('fixture-farmer')
        before = path.read_bytes()
        response = self.gateway([self.command('WorldService.performAction', ['store', raw,
            [{'storedItemName': 'bottle', 'cameFromLocation': -2}]], 2)])
        fixtures.assert_gateway_rejected(self, response); self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.send('WorldService.performAction', ['store', raw,
            [{'storedItemName': 'bottle', 'cameFromLocation': -8, 'numToStore': 2}]], 3), {'id': 700})
        current = self.player.session('fixture-farmer')
        self.assertEqual(current['world']['objectsArray'][0]['contents'], [{'itemCode': 'B8', 'numItem': 2}])
        self.assertEqual(current['userInfo']['player']['storageData']['-2']['B8'][0], 4)
        self.assertNotIn('B8', current['userInfo']['player']['storageData']['-8'])

    def test_legacy_scalar_pattern_init_is_original_array_then_rename_and_reload(self):
        import breeding
        path, save, snapshot, dna = self.baby()
        dna['P']['T'] = 'a'
        save['world']['objectsArray'][0]['mutableAnimalState']['dna'] = copy.deepcopy(dna)
        with redirect_stdout(io.StringIO()): self.player.save_session('fixture-farmer')
        initialized = self.send('UserService.initUser', ['Lamb fixture', 0, True, None], 1)
        loaded_dna = initialized['world']['objectsArray'][0]['mutableAnimalState']['dna']
        self.assertEqual(loaded_dna['P']['T'], ['a'])
        self.assertEqual(breeding.dna_hash(loaded_dna), breeding.dna_hash(dna))
        self.send('AnimalBreedingService.onSetAnimalName', ['cy', breeding.dna_hash(dna), 'Willow', 603, None], 2)
        expected = copy.deepcopy(dna); expected['N'] = 'Willow'; expected['P']['T'] = ['a']
        with redirect_stdout(io.StringIO()): self.player.load_saves()
        self.assertEqual(self.player.session('fixture-farmer')['world']['objectsArray'][0]['mutableAnimalState']['dna'], expected)
        self.assertEqual(json.loads(path.read_text())['world']['objectsArray'][0]['mutableAnimalState']['dna'], expected)
