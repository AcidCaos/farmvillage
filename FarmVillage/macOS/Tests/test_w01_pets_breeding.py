"""W01 exact-animal storage admission and pet refusal, synthetic saves only."""
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import test_breeding_wire as breeding_fixtures
import test_pets as pet_fixtures
import breeding


class W01AnimalBoundaryTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway
    prepare = breeding_fixtures.BreedingWireTests.prepare

    def send(self, method, params, sequence=None):
        self.sequence = max(getattr(self, 'sequence', 0), sequence or 0)
        if sequence is None:
            self.sequence += 1
            sequence = self.sequence
        return breeding_fixtures.BreedingWireTests.send(self, method, params, sequence)

    def arrange(self, *, level=1, count=0):
        self.path, _ = self.prepare()
        self.sequence = 0
        self.save = self.player.session('fixture-farmer')
        self.pen = self.save['world']['objectsArray'][0]
        self.pen.update(expansionLevel=level, expansionParts={}, capacity=99999,
                        contents=[{'itemCode': 'cw', 'numItem': count}] if count else [], storageMetadata={})
        self.dna = copy.deepcopy(breeding._config()['variants']['ewePlain'])
        self.dna['N'] = 'Hazel'
        self.packed = json.dumps(self.dna, separators=(',', ':'))
        self.animal = {'id': 84, 'itemName': 'sheeppen_ewe', 'className': 'MutableAnimal',
                       'state': 'static', 'plantTime': 123000, 'position': {'x': 10, 'y': 10, 'z': 0},
                       'mutableAnimalState': {'dna': self.dna}, 'imported': {'keep': True}}
        self.save['world']['objectsArray'].append(self.animal)
        self.persist()

    def persist(self):
        with redirect_stdout(io.StringIO()):
            self.player.save_session('fixture-farmer')

    def packet(self, target=71, **changes):
        snapshot = ({'id': target, 'className': 'StorageBuilding'} if target < 0 else
                    {'id': 71, 'itemName': breeding.FEATURE, 'className': 'FeatureBuilding'})
        options = {'storedItemName': 'sheeppen_ewe', 'target': target,
                   'resource': 84, 'numToStore': 1, 'metadata': {'type': self.packed}, **changes}
        return ['store', snapshot, [options]]

    def refused(self, packet):
        memory, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.sequence += 1
        response = self.gateway([self.command('WorldService.performAction', packet, self.sequence)])
        fixtures.assert_gateway_rejected(self, response)
        self.assertEqual(self.save, memory)
        self.assertEqual(self.path.read_bytes(), disk)

    def test_all_three_authored_pen_capacities_and_imported_overflow_are_atomic(self):
        for level, capacity in ((1, 20), (2, 30), (3, 40)):
            with self.subTest(level=level):
                self.arrange(level=level, count=capacity - 1)
                self.send('WorldService.performAction', self.packet())
                self.assertEqual(sum(row['numItem'] for row in self.save['world']['objectsArray'][0]['contents']), capacity)
                # An extra existing animal is a capacity fixture, not a birth.
                self.save['world']['objectsArray'].append(copy.deepcopy(self.animal))
                self.persist()
                self.refused(self.packet())
                with redirect_stdout(io.StringIO()): self.player.load_saves()
                self.save = self.player.session('fixture-farmer')
                self.assertEqual(sum(row['numItem'] for row in self.save['world']['objectsArray'][0]['contents']), capacity)
                self.save['world']['objectsArray'][0]['contents'][0]['numItem'] += 1
                self.persist()
                self.refused(self.packet())

    def test_ordinary_inventory_requires_real_slots_and_counts_each_animal(self):
        self.arrange()
        self.refused(self.packet(-2))
        self.save['world']['objectsArray'].append({'id': 90, 'itemName': 'toolshedpink',
            'className': 'StorageBuilding', 'state': 'built', 'position': {'x': 14, 'y': 14, 'z': 0}})
        self.save['userInfo']['player']['storageData']['-2'] = {'HB': [14, [], []]}
        self.persist()
        self.send('WorldService.performAction', self.packet(-2))
        ledger = self.save['userInfo']['player']['storageData']['-2']
        self.assertEqual(ledger['cw'], [1, [], [self.packed]])
        self.assertEqual(ledger['HB'], [14, [], []])
        self.save['world']['objectsArray'].append(copy.deepcopy(self.animal))
        self.persist()
        self.refused(self.packet(-2))
        with redirect_stdout(io.StringIO()): self.player.load_saves()
        self.assertEqual(self.player.session('fixture-farmer')['userInfo']['player']['storageData']['-2'], ledger)

    def test_foreign_inventory_destination_and_disagreeing_pen_ledger_are_atomic(self):
        self.arrange()
        self.refused(self.packet(-8))
        self.save['userInfo']['player']['storageData']['71'] = {'cw': [1, [], [self.packed]]}
        self.persist()
        self.refused(self.packet())

    def test_fractional_boolean_and_ambiguous_source_ids_are_atomic(self):
        self.arrange()
        for options in ({'origin': 71.5}, {'origin': True},
                        {'origin': -2, 'cameFromLocation': 71}):
            with self.subTest(options=options):
                self.refused(self.packet(**options))
        for group in (71.5, True):
            before = copy.deepcopy(self.save)
            with self.assertRaises(ValueError):
                breeding.withdraw_for_placement(self.save, 'sheeppen_ewe',
                    [{'isStorageWithdrawal': group, 'metadata': self.packed}], copy.deepcopy(self.animal))
            self.assertEqual(self.save, before)

    def test_legacy_foreign_inventory_withdrawal_cannot_ship_exact_dna(self):
        self.arrange()
        self.save.pop('_ownedWorldTravel', None)
        self.save['userInfo']['player']['storageData']['-8'] = {'cw': [1, [], [self.packed]]}
        self.persist()
        before = copy.deepcopy(self.save)
        with self.assertRaises(ValueError):
            breeding.withdraw_for_placement(self.save, 'sheeppen_ewe',
                [{'isStorageWithdrawal': -8, 'metadata': self.packed}], copy.deepcopy(self.animal))
        self.assertEqual(self.save, before)

    def test_overflow_pen_withdrawal_preserves_name_dna_and_breeding_state(self):
        self.arrange(count=21)
        self.pen['storageMetadata'] = {'cw:' + breeding.dna_hash(self.dna): [self.packed]}
        self.persist()
        state = copy.deepcopy(self.pen['extraDataState'])
        snapshot = copy.deepcopy(self.animal)
        self.assertTrue(breeding.withdraw_for_placement(self.save, 'sheeppen_ewe',
            [{'isStorageWithdrawal': 71, 'metadata': self.packed}], snapshot, now=1_800_000_000))
        self.assertEqual(snapshot['mutableAnimalState']['dna'], self.dna)
        self.assertEqual(self.save['world']['objectsArray'][0]['contents'][0]['numItem'], 20)
        self.assertEqual(self.save['world']['objectsArray'][0]['extraDataState'], state)

    def test_identical_dna_stack_store_retry_restart_and_sequence_reuse_are_atomic(self):
        import pyamf
        for origin, indexed in ((-1, False), (-2, False), (72, False), (-1, True)):
            with self.subTest(origin=origin, indexed=indexed):
                self.arrange()
                data = self.save['userInfo']['player']['storageData']
                if origin > 0:
                    source = copy.deepcopy(self.pen)
                    source.update(id=72, contents=[{'itemCode': 'cw', 'numItem': 2}],
                                  storageMetadata={'cw:' + breeding.dna_hash(self.dna): [self.packed, self.packed]})
                    self.save['world']['objectsArray'].append(source)
                data[str(origin)] = {'cw': [2, ['sender'], [self.packed, self.packed]]}
                self.persist()
                packet = self.packet(resource=0, origin=origin, isGift=origin == -1)
                if indexed:
                    packet[2] = pyamf.MixedArray({0: packet[2][0]})
                self.send('WorldService.performAction', packet, sequence=10)
                once = copy.deepcopy(self.save)
                disk = self.path.read_bytes()
                self.send('WorldService.performAction', packet, sequence=10)
                self.assertEqual(self.save, once)
                self.assertEqual(self.path.read_bytes(), disk)
                with redirect_stdout(io.StringIO()): self.player.load_saves()
                self.save = self.player.session('fixture-farmer')
                self.send('WorldService.performAction', packet, sequence=10)
                self.assertEqual(self.save, once)
                self.assertEqual(self.path.read_bytes(), disk)
                self.assertEqual(self.save['userInfo']['player']['storageData'][str(origin)]['cw'][0], 1)
                self.assertEqual(self.save['world']['objectsArray'][0]['storageMetadata'],
                                 {'cw:' + breeding.dna_hash(self.dna): [self.packed]})
                altered = copy.deepcopy(packet)
                altered[2][0]['metadata'] = {'type': json.dumps(dict(self.dna, N='Other Name'))}
                before = copy.deepcopy(self.save)
                response = self.gateway([self.command('WorldService.performAction', altered, sequence=10)])
                fixtures.assert_gateway_rejected(self, response)
                self.assertEqual(self.save, before)
                self.assertEqual(self.path.read_bytes(), disk)
                self.send('UserService.initUser', ['Breeding retry fixture', 0, True, None], sequence=11)
                # A new Flash session restarts its counter and may transfer
                # the second separately owned unit as a new transaction.
                self.send('WorldService.performAction', packet, sequence=10)
                self.assertNotIn('cw', self.save['userInfo']['player']['storageData'][str(origin)])
                self.assertEqual(self.save['world']['objectsArray'][0]['storageMetadata'],
                                 {'cw:' + breeding.dna_hash(self.dna): [self.packed, self.packed]})

    def test_undefined_stored_item_cannot_bypass_owned_animal_dna(self):
        import pyamf
        self.arrange()
        self.save['world']['objectsArray'].append({'id': 90, 'itemName': 'toolshedpink',
            'className': 'StorageBuilding', 'state': 'built', 'position': {'x': 14, 'y': 14, 'z': 0}})
        self.persist()
        packet = ['store', copy.deepcopy(self.animal), [{'storedItemName': pyamf.Undefined,
            'target': -2, 'resource': 84, 'metadata': {'type': json.dumps(dict(self.dna, N='Forged'))}}]]
        self.refused(packet)

    def test_owned_identity_restored_during_merge_still_receipts_stack_transfer(self):
        for mode in ('direct', 'temporary', 'deleted'):
            with self.subTest(mode=mode):
                self.arrange()
                self.save['userInfo']['player']['storageData']['-1'] = {'cw': [2, [], [self.packed, self.packed]]}
                if mode == 'temporary':
                    self.animal['tempId'] = 64000
                elif mode == 'deleted':
                    self.animal['deleted'] = True
                self.persist()
                snapshot = dict(copy.deepcopy(self.animal), itemName='haybale', className='Decoration',
                                id=64000 if mode == 'temporary' else 84)
                packet = ['store', snapshot, [{'target': 71, 'origin': -1, 'isGift': True,
                                              'metadata': {'type': self.packed}, 'resource': 0}]]
                self.assertTrue(breeding.is_baby_request(self.save, 'store', snapshot, packet[2]))
                if mode == 'deleted':
                    # Classification adds no permission to use a deleted
                    # object; later admission remains the action's authority.
                    continue
                self.send('WorldService.performAction', packet, sequence=10)
                once, disk = copy.deepcopy(self.save), self.path.read_bytes()
                self.send('WorldService.performAction', packet, sequence=10)
                self.assertEqual(self.save, once)
                self.assertEqual(self.path.read_bytes(), disk)
                self.assertEqual(self.save['userInfo']['player']['storageData']['-1']['cw'][0], 1)


class W01PetRefusalTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway
    NOW = pet_fixtures.PetWireTests.NOW
    prepare = pet_fixtures.PetWireTests.prepare
    send = pet_fixtures.PetWireTests.send
    buy = pet_fixtures.PetWireTests.buy
    pet = pet_fixtures.PetWireTests.pet
    adult = pet_fixtures.PetWireTests.adult
    assert_atomic = pet_fixtures.PetWireTests.assert_atomic

    def fixture(self, uid='fixture-farmer'):
        import items
        import october_village
        import peaceful
        save = fixtures.RuntimeFixtureTests.fixture(self, uid)
        save['version'] = None
        save['world'].update(id=1, uid='october-fixture-world', sizeX=50, sizeY=50, tileSet='grass_theme')
        save['userInfo'].update(currentWorldType='farm', is_new=True, firstDay=True,
                                firstDayTimestamp=self.NOW)
        save['userInfo']['worldSummaryData'] = {'farm': {'storageId': -2,
            'firstLoaded': self.NOW, 'lastLoaded': self.NOW}}
        return october_village.apply_new_preset(save, catalog_lookup=items.get_item_by_name,
                                                growth_seconds=peaceful.grow_seconds)

    def test_fetch_and_harvest_tricks_keep_pet_clock_and_october_identity(self):
        for variant, trick in (('goldenretriever_puppy_cash', 'fetch'),
                               ('bordercollie_puppy_red', 'harvest')):
            with self.subTest(variant=variant):
                self.prepare(variant)
                self.buy()
                # A fully trained adult is a seeded precondition; this does
                # not award training or change the real fourteen-day clock.
                self.adult(level=5)
                save = self.player.session('fixture-farmer')
                october = copy.deepcopy(save['_quintessentialOctober'])
                with redirect_stdout(io.StringIO()): self.player.save_session('fixture-farmer')
                self.assert_atomic('performTrick', self.pet(),
                    {'trickName': trick, 'harvestObjectIds': [999]}, sequence=2)
                with redirect_stdout(io.StringIO()): self.player.load_saves()
                self.assertEqual(self.player.session('fixture-farmer')['_quintessentialOctober'], october)
                self.assertEqual(self.player.session('fixture-farmer')['userInfo']['currentWorldType'], 'farm')


if __name__ == '__main__':
    unittest.main()
