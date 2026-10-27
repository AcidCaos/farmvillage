"""Original stored-sale AMF shapes, accounting and durable refusal/replay."""
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import test_cove_cellar as world_fixtures
import inventory_sales
import items
import meadows_storage
import pyamf
import storage
import world_travel


class InventorySalesTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway
    save = world_fixtures.CoveCellarTests.save
    prepare = world_fixtures.CoveCellarTests.prepare
    persist = world_fixtures.CoveCellarTests.persist

    def setup_sale(self, world='meadows', entry=None):
        self.prepare(world, gold=1000)
        self.namespace = meadows_storage.start_session(self.save)
        self.group = storage.active_inventory_id(self.save)
        self.save['userInfo']['player']['storageData'][str(self.group)] = {
            'HB': copy.deepcopy(entry if entry is not None else [5, [], []])}
        self.persist()

    def args(self, code='HB', quantity=1, group=None):
        return [{'code': code}, False, str(self.group if group is None else group), quantity]

    def sale(self, params=None, sequence=10, namespace=None):
        request = self.command(inventory_sales.METHOD, self.args() if params is None else params,
                               sequence=sequence)
        request['sequenceID'] = self.namespace if namespace is None else namespace
        return request

    def send(self, params=None, sequence=10):
        response = self.gateway([self.sale(params, sequence)])
        return fixtures.gateway_results(self, response)[0]

    def test_observed_mixed_array_sale_returns_required_delta_and_quantity_once(self):
        self.setup_sale()
        params = pyamf.MixedArray({0: {'code': 'HB'}, 1: False, 2: '-16', 3: 1})
        request = self.sale()
        request['params'] = params
        raw = self.gateway_payload([request])
        from pyamf import remoting
        self.assertIsInstance(remoting.decode(raw).bodies[0][1].body[1][0]['params'], pyamf.MixedArray)
        with redirect_stdout(io.StringIO()):
            response = self.client.post('/flashservices/gateway.php', data=raw,
                                       content_type='application/x-amf')
        result = fixtures.gateway_results(self, response, [0])[0]['data']
        self.assertEqual(result, {'sellable': True, 'qtySold': 1, 'sellAmounts': {'coins': 5}})
        self.assertEqual(self.save['userInfo']['player']['gold'], 1005)
        self.assertEqual(self.save['userInfo']['player']['storageData']['-16']['HB'], [4, [], []])
        before = copy.deepcopy(self.save)
        self.assertEqual(self.send()['data'], result)
        self.assertEqual(self.save, before)
        self.player.load_saves()
        self.assertEqual(self.send()['data'], result)
        self.assertEqual(self.save, before)

    def test_receipt_survives_fresh_process_and_new_session_numeric_reuse(self):
        self.setup_sale()
        self.send()
        from bundle import BASE_DIR
        code = "import json; from pathlib import Path; p=Path(__import__('sys').argv[1]); s=json.loads(p.read_text()); assert s['userInfo']['player']['gold']==1005; assert s['userInfo']['player']['storageData']['-16']['HB'][0]==4; assert s['_meadowsStorage']['receipts']; print('persisted-sale-and-receipt')"
        check = subprocess.run([sys.executable, '-I', '-c', code, str(self.path)],
                               cwd=BASE_DIR, capture_output=True, text=True, check=True)
        self.assertIn('persisted-sale-and-receipt', check.stdout)
        previous = self.namespace
        self.namespace = meadows_storage.start_session(self.save)
        self.persist()
        self.assertEqual(self.send()['errorType'], 0)
        self.assertEqual(self.save['userInfo']['player']['gold'], 1010)
        before = copy.deepcopy(self.save)
        fixtures.gateway_results(self, self.gateway([self.sale(namespace=previous)]), [0])
        self.assertEqual(self.save, before)
        fixtures.gateway_results(self, self.gateway([self.sale(sequence=11, namespace=previous)]), [29])
        self.assertEqual(self.save, before)

    def test_original_local_signedcall_header_shape_with_synthetic_bypass_values(self):
        self.setup_sale()
        from pyamf import remoting
        header = {'authBypass': '1', 'sigTime': '1800000000', 'snId': 1,
                  'masterId': '1', 'token': '0', 'uid': 'fixture-farmer',
                  'flashRevision': '855098', 'configRevision': '855098',
                  'phpRevision': '855098'}
        envelope = remoting.Envelope(pyamf.AMF0)
        envelope['/1'] = remoting.Request('FarmService', body=[header, [self.sale()], 0])
        raw = remoting.encode(envelope).getvalue()
        with redirect_stdout(io.StringIO()):
            response = self.client.post('/flashservices/gateway.php', data=raw,
                                       content_type='application/x-amf')
        fixtures.gateway_results(self, response, [0])
        self.assertEqual(self.save['userInfo']['player']['gold'], 1005)
        # This is the actual local SignedCall protocol shape, not a MAC or
        # signature-verification test. The original local template supplies
        # token=0/authBypass=1 and the gateway does not validate a digest.
    def test_current_world_and_ordinary_inventory_only(self):
        for world in ('farm', 'england', 'meadows', 'fisherman'):
            with self.subTest(world=world):
                self.setup_sale(world)
                self.assertEqual(self.send()['errorType'], 0)
                self.assertEqual(self.save['userInfo']['player']['gold'], 1005)
        for group in (-1, -6, -2, 100, 0):
            self.setup_sale()
            before, disk = copy.deepcopy(self.save), self.path.read_bytes()
            self.assertEqual(self.send(self.args(group=group))['errorType'], 29)
            self.assertEqual(self.save, before)
            self.assertEqual(self.path.read_bytes(), disk)

    def test_metadata_fifo_and_senders_match_original_remove_inventory_item(self):
        for entry, quantity, expected in (
                ([3, ['a', 'b'], [{'unit': 1}, {'unit': 2}, {'unit': 3}]], 2,
                 [1, ['a', 'b'], [{'unit': 3}]]),
                ([4, [], [{'unit': 1}, {'unit': 2}]], 1,
                 [3, [], [{'unit': 1}, {'unit': 2}]])):
            self.setup_sale(entry=entry)
            self.assertEqual(self.send(self.args(quantity=quantity))['errorType'], 0)
            self.assertEqual(self.save['userInfo']['player']['storageData']['-16']['HB'], expected)
        self.setup_sale(entry=[1, [], [{'opaque': {'keep': True}}]])
        self.send()
        self.assertNotIn('HB', self.save['userInfo']['player']['storageData']['-16'])

    def test_forged_shapes_quantities_indices_sellall_and_item_keys_are_atomic(self):
        self.setup_sale()
        invalid = [self.args(quantity=q) for q in (0, -1, True, 1.5, float('nan'), 6, '1')]
        invalid += [[{'code': 'HB', 'price': 999}, False, '-16', 1],
                    [{'code': 'HB', 'metadataIndex': 0}, False, '-16', 1],
                    [{'code': 'HB'}, True, '-16', 1],
                    [{'code': 'HB'}, 0, '-16', 1],
                    [{'code': 'HB'}, False, -16, 1],
                    [{'code': 'HB'}, False, '-016', 1],
                    self.args(code='HB:2'), self.args(code='missing'),
                    self.args() + [{}], self.args()[:-1]]
        for params in invalid:
            with self.subTest(params=params):
                before, disk = copy.deepcopy(self.save), self.path.read_bytes()
                self.assertEqual(self.send(params)['errorType'], 29)
                self.assertEqual(self.save, before)
                self.assertEqual(self.path.read_bytes(), disk)
        for params in (pyamf.MixedArray({0: {}, 2: '-16'}),
                       pyamf.MixedArray({0: {'code': 'HB'}, '0': {}, 1: False, 2: '-16', 3: 1})):
            before = copy.deepcopy(self.save)
            with self.assertRaises(ValueError):
                inventory_sales.sell(self.save, params, request_id=(self.namespace, 10))
            self.assertEqual(self.save, before)

    def test_bad_imported_metadata_balance_and_special_contracts_refuse(self):
        for entry in ([3, [], [1, 2, 3, 4]],
                      [3, {}, []], [3, [], [], {'unknown': 1}], [True, [], []]):
            self.setup_sale()
            # The normal save importer already rejects malformed shapes.
            # Exercise the module's direct-call atomic guard independently.
            self.save['userInfo']['player']['storageData']['-16']['HB'] = entry
            before, disk = copy.deepcopy(self.save), self.path.read_bytes()
            with self.assertRaises(ValueError):
                inventory_sales.sell(self.save, self.args(), request_id=(self.namespace, 10))
            self.assertEqual(self.save, before)
            self.assertEqual(self.path.read_bytes(), disk)
        for changes in ({'sellable': 'false'}, {'disallowDelete': '1'},
                        {'market': 'jade'}, {'className': 'MutableAnimal'}, {'type': 'consumable'}):
            self.setup_sale()
            before = copy.deepcopy(self.save)
            with mock.patch.object(inventory_sales.items, 'get_item_by_code',
                                   return_value={**items.get_item_by_name('haybale'), **changes}):
                self.assertEqual(self.send()['errorType'], 29)
            self.assertEqual(self.save, before)
        self.setup_sale()
        self.save['userInfo']['player']['gold'] = True
        before = copy.deepcopy(self.save)
        with self.assertRaises(ValueError):
            inventory_sales.sell(self.save, self.args(), request_id=(self.namespace, 10))
        self.assertEqual(self.save, before)

    def test_receipt_conflict_and_stale_unknown_session_refuse_without_mutation(self):
        self.setup_sale()
        self.send()
        for request in (self.sale(self.args(quantity=2)), self.sale(sequence=9),
                        self.sale(sequence=11, namespace='unknown')):
            before, disk = copy.deepcopy(self.save), self.path.read_bytes()
            fixtures.gateway_results(self, self.gateway([request]), [29])
            self.assertEqual(self.save, before)
            self.assertEqual(self.path.read_bytes(), disk)

    def test_direct_failure_after_withdrawal_keeps_original_save_and_receipt(self):
        self.setup_sale()
        before = copy.deepcopy(self.save)
        with mock.patch.object(inventory_sales.engine, 'apply_coins_diff', side_effect=ValueError('write failure')):
            with self.assertRaises(ValueError):
                inventory_sales.sell(self.save, self.args(), request_id=(self.namespace, 10))
        self.assertEqual(self.save, before)

    def test_mixed_batch_sale_then_bad_sale_preserves_only_successful_call(self):
        self.setup_sale()
        response = self.gateway([self.sale(), self.sale(self.args(quantity=100), sequence=11)])
        fixtures.gateway_results(self, response, [0, 29])
        self.assertEqual(self.save['userInfo']['player']['gold'], 1005)
        self.assertEqual(self.save['userInfo']['player']['storageData']['-16']['HB'][0], 4)
        before = copy.deepcopy(self.save)
        fixtures.gateway_results(self, self.gateway([self.sale()]), [0])
        self.assertEqual(self.save, before)

    def test_final_encoding_failure_rolls_back_sale_receipt_balance_and_disk(self):
        self.setup_sale()
        payload = self.gateway_payload([self.sale()])
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        with mock.patch.object(self.server.remoting, 'encode', side_effect=ValueError('encoding failure')):
            with redirect_stdout(io.StringIO()):
                response = self.client.post('/flashservices/gateway.php', data=payload,
                                           content_type='application/x-amf')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)


if __name__ == '__main__':
    unittest.main()
