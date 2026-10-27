"""Legacy specialized stores reject delayed packets from a prior initUser."""
import base64
from contextlib import redirect_stdout
import copy
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import test_wave2_england_shipping as shipping
import test_breeding_wire as animals

NOW = 1800000000


class StoreEpochCases:
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

    def persist(self):
        with redirect_stdout(io.StringIO()):
            self.player.save_session('fixture-farmer')

    def request(self, name, params, sequence, namespace=None):
        request = self.command(name, copy.deepcopy(params), sequence)
        if namespace is not None:
            request['sequenceID'] = namespace
        return request

    def rpc(self, name, params, sequence, namespace=None, error=0):
        with mock.patch('server.timestamp_now', return_value=NOW), mock.patch(
                'commands.timestamp_now', return_value=NOW), mock.patch('engine.timestamp_now', return_value=NOW):
            response = self.gateway([self.request(name, params, sequence, namespace)])
        return fixtures.gateway_results(self, response, [error])[0]['data']

    def init(self):
        return self.rpc('UserService.initUser', ['Synthetic specialized store', 0, True, None], 1)['sequenceId']

    def replay_in_fresh_process(self, namespace, expected):
        original = self.path.read_bytes()
        shutil.copytree(self.bundle.CACHE_DIR, self.saves.parent / 'cache', dirs_exist_ok=True)
        payload = self.gateway_payload([self.request('WorldService.performAction', self.packet, 801, namespace)])
        program = '''import base64,sys
from unittest import mock
import assets
with mock.patch.object(assets,"check_assets"),mock.patch.object(sys,"argv",["server.py"]):
 import server
response=server.app.test_client().post("/flashservices/gateway.php",data=base64.b64decode(sys.argv[1]),content_type="application/x-amf")
print("STORE_EPOCH_RESPONSE:"+str(response.status_code)+":"+base64.b64encode(response.data).decode())
'''
        child = subprocess.run([sys.executable, '-B', '-c', program, base64.b64encode(payload).decode()],
            cwd=fixtures.ROOT, env={**os.environ, 'FARMVILLAGE_DATA_DIR': str(self.saves.parent),
                                   'PYTHONDONTWRITEBYTECODE': '1'}, capture_output=True, text=True, timeout=90)
        self.assertEqual(child.returncode, 0, child.stderr + child.stdout[-1000:])
        record = next(row for row in child.stdout.splitlines() if row.startswith('STORE_EPOCH_RESPONSE:'))
        _, status, encoded = record.split(':', 2)
        self.assertEqual(status, '200')
        from pyamf import remoting
        result = remoting.decode(base64.b64decode(encoded)).bodies[0][1].body['data'][0]
        self.assertEqual((result['errorType'], result['data']), (0, expected))
        self.assertEqual(self.path.read_bytes(), original)

    def test_current_retry_restart_stale_epoch_refusal_and_fresh_epoch_counter_reuse(self):
        self.prepare_case()
        first = self.init()
        original = self.rpc('WorldService.performAction', self.packet, 801, first)
        after_first, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.assertEqual(self.quantity(), 2)
        self.assertEqual(self.rpc('WorldService.performAction', self.packet, 801, first), original)
        self.assertEqual(self.save, after_first)
        self.assertEqual(self.path.read_bytes(), disk)
        self.replay_in_fresh_process(first, original)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        current = self.init()
        self.assertNotEqual(current, first)
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        for namespace in (first, 'unknown-epoch', '', 1, True, [], {}, 'x' * 129):
            with self.subTest(namespace=namespace):
                self.rpc('WorldService.performAction', self.packet, 801, namespace, error=29)
                self.assertEqual(self.save, before)
                self.assertEqual(self.path.read_bytes(), disk)
        current_result = self.rpc('WorldService.performAction', self.packet, 801, current)
        self.assertEqual(self.quantity(), 1)
        accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.assertEqual(self.rpc('WorldService.performAction', self.packet, 801, current), current_result)
        changed = copy.deepcopy(self.packet)
        changed[2][0]['numToStore'] = 2
        self.rpc('WorldService.performAction', changed, 801, current, error=29)
        self.assertEqual(self.save, accepted)
        self.assertEqual(self.path.read_bytes(), disk)
        self.assert_case_state()


class EnglandStoreEpochTests(StoreEpochCases, unittest.TestCase):
    def prepare_case(self):
        shipping.EnglandShippingWireTests.prepare(self,
            licenses={'farm': {'world': True}, 'england': {'world': True}})
        self.packet = shipping.EnglandShippingWireTests.store_packet(self)

    def quantity(self):
        return self.save['userInfo']['player']['storageData']['-2']['HB'][0]

    def assert_case_state(self):
        data = self.save['userInfo']['player']['storageData']
        self.assertEqual(data['-2']['HB'], [1, [], [{'unit': 3}]])
        self.assertEqual(data['-8']['HB'], [3, ['England sender', 'home sender'],
            [{'England': 'keep'}, {'unit': 1}, {'unit': 2}]])
        self.assertEqual(self.save['userInfo']['unlockedWorldContentLicenses'],
                         {'farm': {'world': True}, 'england': {'world': True}})


class BabyStoreEpochTests(StoreEpochCases, unittest.TestCase):
    prepare = animals.BreedingWireTests.prepare

    def prepare_case(self):
        self.path, save, snapshot, self.dna = animals.BreedingWireTests.baby(self, gifts=3)
        save['world']['objectsArray'][0]['plantTime'] = 1234567890000
        save['userInfo']['player']['storageData']['-1']['B8'] = [3, ['original-sender'],
            [{'unit': 1}, {'unit': 2}, {'unit': 3}]]
        self.persist()
        self.packet = ['store', snapshot, [{'storedItemName': 'bottle', 'storedItemCode': 'B8',
                                          'numToStore': 1, 'isGift': True}]]

    def quantity(self):
        return self.save['userInfo']['player']['storageData']['-1']['B8'][0]

    def assert_case_state(self):
        obj = self.save['world']['objectsArray'][0]
        self.assertEqual(obj['contents'], [{'itemCode': 'B8', 'numItem': 2}])
        self.assertEqual(obj['mutableAnimalState']['dna'], self.dna)
        self.assertEqual(obj['plantTime'], 1234567890000)
        self.assertEqual(obj['importedAnimal'], {'keep': True})
        self.assertEqual(self.save['userInfo']['player']['storageData']['-1']['B8'], [1, [], [{'unit': 3}]])


if __name__ == '__main__':
    unittest.main()
