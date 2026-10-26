"""Original stored-animal rename packets, isolated AMF gateway and JSON saves."""
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
from pyamf import remoting


class StoredAnimalRenameTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    def prepare(self, *, gift=False, ledger=True):
        import breeding
        path = self.write_fixture()
        save = self.player.session('fixture-farmer')
        dna = copy.deepcopy(breeding._config()['variants']['ewePlain'])
        dna.update(N='Hazel', imported={'keep': [1, 2]})
        other = copy.deepcopy(dna); other['N'] = 'Same Genes'
        packed = json.dumps(dna, separators=(',', ':'))
        packed_other = json.dumps(other, separators=(',', ':'))
        identity = breeding.dna_hash(dna)
        save['world']['objectsArray'] = []
        player = save['userInfo']['player']
        player['storageData'] = {}
        if gift:
            player['storageData']['-1'] = {'cw': [3, ['keep sender'], [packed, packed_other, 'unrelated']]}
            building = None; world_id = -1
        else:
            pen = {'id': 71, 'itemName': breeding.FEATURE, 'className': 'FeatureBuilding',
                   'state': 'built', 'isFullyBuilt': True, 'expansionLevel': 1,
                   'contents': [{'itemCode': 'cw', 'numItem': 2}],
                   'storageMetadata': {'cw:' + identity: [packed, packed_other]},
                   'extraDataState': {'breedingQueue': [], 'breedHistory': {}, 'imported': ['keep']}}
            save['world']['objectsArray'].append(pen)
            if ledger:
                player['storageData']['71'] = {'cw': [2, ['keep sender'], [packed, packed_other]]}
            # The client updates storageMetaData optimistically before serializing
            # this snapshot. Its contents and DNA are never authority for the server.
            building = {'id': 71, 'itemName': breeding.FEATURE,
                        'contents': [{'itemCode': 'cw', 'numItem': 999}],
                        'storageMetadata': {'forged': ['discard me']}}
            world_id = -1
        with redirect_stdout(io.StringIO()): self.player.save_session('fixture-farmer')
        return path, save, dna, ['cw', identity, 'Willow', world_id, building]

    def send(self, args, sequence=1):
        response = self.gateway([self.command('AnimalBreedingService.onSetAnimalName', args, sequence)])
        self.assertEqual(response.status_code, 200, response.data)
        body = remoting.decode(response.data).bodies[0][1].body['data'][0]
        self.assertEqual(body['errorType'], 0, body)
        return body['data']

    def test_pen_rename_changes_first_record_only_and_keeps_duplicate_ledger_durable(self):
        import breeding
        path, save, dna, args = self.prepare()
        before = copy.deepcopy(save)
        self.assertEqual(self.send(args), {})
        pen = save['world']['objectsArray'][0]
        key = 'cw:' + args[1]
        expected = copy.deepcopy(dna); expected['N'] = 'Willow'
        self.assertEqual(json.loads(pen['storageMetadata'][key][0]), expected)
        self.assertEqual(breeding.dna_hash(expected), args[1])
        self.assertEqual(pen['storageMetadata'][key][1], before['world']['objectsArray'][0]['storageMetadata'][key][1])
        self.assertEqual(pen['contents'], before['world']['objectsArray'][0]['contents'])
        self.assertEqual(pen['extraDataState'], before['world']['objectsArray'][0]['extraDataState'])
        ledger = save['userInfo']['player']['storageData']['71']['cw']
        self.assertEqual(ledger[:2], [2, ['keep sender']])
        self.assertEqual(ledger[2], pen['storageMetadata'][key])
        for field in ('gold', 'cash', 'xp'):
            self.assertEqual(save['userInfo']['player'].get(field), before['userInfo']['player'].get(field))
        once = path.read_bytes()
        self.assertEqual(self.send(args), {})
        self.assertEqual(path.read_bytes(), once)
        with redirect_stdout(io.StringIO()): self.player.load_saves()
        reloaded = self.player.session('fixture-farmer')
        self.assertEqual(reloaded['world']['objectsArray'][0]['storageMetadata'][key], ledger[2])
        self.assertEqual(json.loads(path.read_text())['userInfo']['player']['storageData']['71']['cw'], ledger)

    def test_pen_with_contents_only_ledger_renames_owned_metadata_without_inventing_storage(self):
        path, save, dna, args = self.prepare(ledger=False)
        self.assertEqual(self.send(args), {})
        self.assertNotIn('71', save['userInfo']['player']['storageData'])
        self.assertEqual(json.loads(save['world']['objectsArray'][0]['storageMetadata']['cw:' + args[1]][0])['N'], 'Willow')

    def test_gift_rename_changes_first_matching_hash_only_and_survives_reload(self):
        path, save, dna, args = self.prepare(gift=True)
        before = copy.deepcopy(save['userInfo']['player']['storageData']['-1']['cw'])
        self.assertEqual(self.send(args), {})
        entry = save['userInfo']['player']['storageData']['-1']['cw']
        expected = copy.deepcopy(dna); expected['N'] = 'Willow'
        self.assertEqual(json.loads(entry[2][0]), expected)
        self.assertEqual(entry[:2], before[:2]); self.assertEqual(entry[2][1:], before[2][1:])
        with redirect_stdout(io.StringIO()): self.player.load_saves()
        self.assertEqual(self.player.session('fixture-farmer')['userInfo']['player']['storageData']['-1']['cw'], entry)
        self.assertEqual(json.loads(path.read_text())['userInfo']['player']['storageData']['-1']['cw'], entry)

    def test_wrong_identity_context_and_malformed_ledger_reject_without_any_write(self):
        path, save, dna, args = self.prepare()
        original = copy.deepcopy(save)
        for label, change in (
                ('wrong hash', lambda s, a: a.__setitem__(1, 'deadbeef')),
                ('wrong code', lambda s, a: a.__setitem__(0, 'cow')),
                ('wrong pen', lambda s, a: a[4].__setitem__('id', 72)),
                ('wrong pen name', lambda s, a: a[4].__setitem__('itemName', 'cow')),
                ('bad context', lambda s, a: a.__setitem__(4, 71)),
                ('bad world id', lambda s, a: a.__setitem__(3, True)),
                ('invalid name', lambda s, a: a.__setitem__(2, 'Bad!')),
                ('missing hash', lambda s, a: a.__setitem__(1, '')),
                ('wrong count', lambda s, a: s['userInfo']['player']['storageData']['71']['cw'].__setitem__(0, 10)),
                ('wrong ledger dna', lambda s, a: s['userInfo']['player']['storageData']['71']['cw'].__setitem__(2, ['not dna'])),
                ('unowned world', lambda s, a: s['userInfo'].__setitem__('currentWorldType', 'unsupported'))):
            with self.subTest(label=label):
                save.clear(); save.update(copy.deepcopy(original))
                altered = copy.deepcopy(args); change(save, altered)
                with redirect_stdout(io.StringIO()): self.player.save_session('fixture-farmer')
                prior = path.read_bytes(); memory = copy.deepcopy(save)
                response = self.gateway([self.command('AnimalBreedingService.onSetAnimalName', altered)])
                fixtures.assert_gateway_rejected(self, response)
                self.assertEqual(path.read_bytes(), prior); self.assertEqual(save, memory)

    def test_malformed_in_memory_ledger_is_rejected_without_mutation(self):
        import breeding
        path, save, dna, args = self.prepare()
        save['userInfo']['player']['storageData']['71']['cw'] = []
        memory = copy.deepcopy(save); prior = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'metadata is malformed'):
            breeding.rename(save, *args)
        self.assertEqual(save, memory); self.assertEqual(path.read_bytes(), prior)

    def test_negative_world_id_cannot_rename_an_inventory_animal_as_a_gift(self):
        path, save, dna, args = self.prepare(gift=True)
        data = save['userInfo']['player']['storageData']
        data['-2'] = data.pop('-1')
        with redirect_stdout(io.StringIO()): self.player.save_session('fixture-farmer')
        prior = path.read_bytes(); memory = copy.deepcopy(save)
        response = self.gateway([self.command('AnimalBreedingService.onSetAnimalName', args)])
        fixtures.assert_gateway_rejected(self, response)
        self.assertEqual(path.read_bytes(), prior); self.assertEqual(save, memory)


if __name__ == '__main__':
    unittest.main()
