"""Private copied-companion acceptance with real saves and signed game packets.

No socket/browser/app is opened. The copied bridge uses a synthetic minimal
catalogue fixture, so this does not certify a regenerated companion catalogue.
WAVE2_GODBARN_ROOT may point to an independently copied tracked GodBarn tree.
"""
from contextlib import redirect_stdout
import copy
import io
import json
import os
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import test_england_pub_engine as pub_fixtures
import barn_actions
import breeding
import crafting
import england_shipping
import engine
import items

ROOT = Path(__file__).resolve().parents[2]
COMPANION = Path(os.environ.get('WAVE2_GODBARN_ROOT', ROOT.parent / 'companion' / 'GodBarn')).resolve()
NOW = pub_fixtures.NOW


class EnglandGodBarnAcceptanceTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    prepare = pub_fixtures.EnglandPubEngineTests.prepare
    travel = pub_fixtures.EnglandPubEngineTests.travel
    skill = pub_fixtures.EnglandPubEngineTests.skill

    def setUp(self):
        fixtures.RuntimeFixtureTests.setUp(self)
        self.assertTrue((COMPANION / 'integration.py').is_file(),
                        'Set WAVE2_GODBARN_ROOT to a private tracked GodBarn source copy.')
        sys.path.insert(0, str(COMPANION.parent))
        from GodBarn import integration
        self.assertTrue(Path(integration.__file__).resolve().is_relative_to(COMPANION))
        self.prepare(home_pub=True)
        for code, quantity in crafting._ingredients(crafting._recipe('ln')).items():
            crafting.dispatch(self.save, 'FarmService.onPurchaseBushel', [code, 'ln', quantity], now=NOW)
        crafting.dispatch(self.save, 'CraftingService.onBeginRecipe', ['ln', 0], now=NOW)
        england_shipping.buy_package(self.save, england_shipping.PACKAGE, request_id=77)
        dna = copy.deepcopy(breeding._config()['variants']['ewePlain'])
        dna.update(N='Imported Hazel', imported={'clock': 4321, 'keep': [1, 2]})
        packed = json.dumps(dna, separators=(',', ':'))
        self.save['world']['objectsArray'].extend([
            {'id': 610, 'itemName': breeding.FEATURE, 'className': 'FeatureBuilding',
             'state': 'built', 'isFullyBuilt': True, 'expansionLevel': 1, 'expansionParts': {},
             'contents': [{'itemCode': 'cw', 'numItem': 1}],
             'storageMetadata': {'cw:' + breeding.dna_hash(dna): [packed]},
             'extraDataState': {'breedingQueue': [], 'breedHistory': {}, 'imported': ['retain']}},
            {'id': 611, 'itemName': 'ewePlain', 'className': 'MutableAnimal', 'state': 'bare',
             'plantTime': 123456789, 'mutableAnimalState': copy.deepcopy(dna), 'metadata': packed},
            {'id': 612, 'itemName': 'nurserybarn_finished_complete', 'className': 'NurseryBuildingFinished',
             'isFullyBuilt': True, 'state': 'bare', 'contents': [], 'expansionLevel': 1,
             'plantTime': 987654321, 'imported': {'retain': [3]}}])
        self.stable = {'id': 613, 'itemName': 'xukhorsestable_finished',
            'className': 'HorseStableBuildingFinished', 'state': 'built', 'isFullyBuilt': True,
            'expansionLevel': 1, 'contents': [], 'plantTime': 24681012, 'opaque': {'retain': [4]}}
        self.save['world']['objectsArray'].append(self.stable)
        self.save['unknownW02Import'] = {'retain': [5, {'field': 'opaque'}]}
        self.horse = items.get_item_by_name('horse')
        self.save['userInfo']['player']['storageData']['-2'] = {
            self.horse['code']: [3, ['Home sender'], [{'name': 'Home horse'}]]}
        self.save['userInfo']['player']['storageData']['-8'] = {
            self.horse['code']: [2, ['England sender', 'Other sender'],
                [{'name': 'England horse', 'plantTime': 13579113, 'opaque': [6]}, {'name': 'Other horse'}]]}
        self.persist()
        # The code copy stays byte-identical; its generated catalogue is not
        # tracked. Only this disposable integration fixture creates index data.
        data_root = Path(self.directory.name) / 'bridge-fixture'
        data = data_root / 'data'; data.mkdir(parents=True)
        (data / 'catalog.json').write_text(json.dumps([
            {'name': 'xukcraftingpub', 'code': 'jm', 'type': 'building', 'displayName': 'Pub'},
            {'name': self.horse['name'], 'code': self.horse['code'], 'type': 'animal', 'displayName': 'Horse'}]))
        shutil.copyfile(COMPANION / 'data/rules.json', data / 'rules.json')
        from flask import Flask
        self.app = Flask('private-wave2-england-godbarn')
        self.app.secret_key = 'private-W02-synthetic-only'
        self.app.testing = True
        self.app.add_url_rule('/flashservices/gateway.php', 'flashservices_gateway',
            self.server.app.view_functions['flashservices_gateway'], methods=['POST'])
        self.app.add_url_rule('/ruffle.html', 'synthetic_game_document',
            lambda: '<html><head><script id="game-script">window.fixture=true;</script></head><body>Fixture</body></html>')
        fake_game = SimpleNamespace(BIND_PORT=48179, _decode_gateway=self.server._decode_gateway)
        fake_bundle = SimpleNamespace(DATA_DIR=str(Path(self.directory.name) / 'private-data'),
                                      ASSETS_DIR=str(Path(self.directory.name) / 'private-assets'))
        self.bridge = integration.register_god_barn(self.app, game_server=fake_game,
            player_module=self.player, bundle_module=fake_bundle, root=data_root,
            farming_module=barn_actions)
        self.client = self.app.test_client()
        self.base = 'http://localhost:48179'
        with self.client.session_transaction() as session:
            session['UID'] = 'fixture-farmer'
        state = self.get('/god-barn/api/state').get_json()
        self.csrf = state['csrf']

    def persist(self):
        with redirect_stdout(io.StringIO()):
            self.player.save_session('fixture-farmer')

    def get(self, path):
        return self.client.get(path, base_url=self.base)

    def post(self, path, body):
        return self.client.post(path, json=body, base_url=self.base,
                                headers={'X-God-Barn-Token': self.csrf})

    def preview(self, operation):
        state = self.get('/god-barn/api/state').get_json()
        response = self.post('/god-barn/api/preview', {'farmId': 'fixture-farmer',
            'revision': state['farm']['revision'], 'operation': operation})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return state, response.get_json()

    def apply(self, state, preview):
        return self.post('/god-barn/api/apply', {'farmId': 'fixture-farmer',
            'revision': state['farm']['revision'], 'token': preview['token']})

    def packet(self, epoch=None, sequence=101):
        headers = {} if epoch is None else {'X-God-Barn-Epoch': epoch}
        payload = self.gateway_payload([self.command('CraftingService.onRushRecipe', ['ln', NOW, False, 0], sequence)])
        with redirect_stdout(io.StringIO()), mock.patch.object(crafting, 'timestamp_now', return_value=NOW + 1), \
                mock.patch.object(self.server, 'timestamp_now', return_value=NOW + 1), \
                mock.patch.object(engine, 'timestamp_now', return_value=NOW + 1):
            return self.client.post('/flashservices/gateway.php', data=payload,
                content_type='application/x-amf', base_url=self.base, headers=headers)

    def test_park_balance_edit_resume_preserves_england_and_fences_stale_game_packets(self):
        self.get('/ruffle.html')
        old = self.bridge._epoch('fixture-farmer')
        before = copy.deepcopy(self.save)
        disk = self.path.read_bytes()
        self.assertEqual(self.get('/god-barn/park?uid=fixture-farmer').status_code, 200)
        blocked = self.packet(old)
        self.assertEqual((blocked.status_code, blocked.get_json()['code']), (409, 'farm_parked'))
        self.assertEqual(self.save, before); self.assertEqual(self.path.read_bytes(), disk)
        state, preview = self.preview({'type': 'balance', 'field': 'gold', 'mode': 'add', 'amount': 123})
        self.assertEqual(self.save, before)
        applied = self.apply(state, preview)
        self.assertEqual(applied.status_code, 200, applied.get_data(as_text=True))
        self.assertTrue(applied.get_json()['durabilityConfirmed'])
        expected = copy.deepcopy(before); expected['userInfo']['player']['gold'] += 123
        self.assertEqual(self.save, expected)
        self.assertEqual(json.loads(self.path.read_text()), expected)
        original = next(row for row in applied.get_json()['history'] if row['original'])
        saved_original = json.loads((self.bridge.snapshots / (original['id'] + '.json')).read_text())
        self.assertEqual(saved_original['save'], before)
        self.assertEqual(self.get('/god-barn/resume?uid=fixture-farmer').status_code, 302)
        page = self.get('/ruffle.html').get_data(as_text=True)
        current = self.bridge._epoch('fixture-farmer')
        self.assertNotEqual(current, old); self.assertIn(current, page)
        for epoch in (None, old):
            prior = self.path.read_bytes(); memory = copy.deepcopy(self.save)
            blocked = self.packet(epoch)
            self.assertEqual((blocked.status_code, blocked.get_json()['code']), (409, 'stale_game_page'))
            self.assertEqual(self.save, memory); self.assertEqual(self.path.read_bytes(), prior)
        response = self.packet(current)
        self.assertEqual(fixtures.gateway_results(self, response, [0])[0]['data'], {})
        self.assertEqual(self.save['userInfo']['player']['cash'], expected['userInfo']['player']['cash'] - 5)
        self.assertEqual(self.save['craftingState'][crafting.PUB_WORLD_STATE], expected['craftingState'][crafting.PUB_WORLD_STATE])
        self.assertEqual(self.save['userInfo']['unlockedWorldContentLicenses'], expected['userInfo']['unlockedWorldContentLicenses'])
        self.assertEqual(self.save['world']['objectsArray'][1:], expected['world']['objectsArray'][1:])
        latest = copy.deepcopy(self.save)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.save = self.player.session('fixture-farmer')
        self.assertEqual(self.save, latest)
        unchanged = self.path.read_bytes()
        stale = self.apply(state, preview)
        self.assertEqual((stale.status_code, stale.get_json()['code']), (409, 'stale_revision'))
        self.assertEqual(self.save, latest); self.assertEqual(self.path.read_bytes(), unchanged)
        self.assertNotIn('fixture-farmer', self.bridge.parked)

    def test_england_stable_load_uses_minus8_and_preserves_home_and_pub_state(self):
        before = copy.deepcopy(self.save)
        report = self.get('/god-barn/api/farming')
        self.assertEqual(report.status_code, 200, report.get_data(as_text=True))
        stable = next(row for row in report.get_json()['buildings'] if row['id'] == 613)
        source = next(row for row in stable['loadableInventory'] if row.get('source') == 'storage' and row['code'] == self.horse['code'])
        self.assertEqual(source['quantity'], 2)
        state, preview = self.preview({'type': 'building', 'buildingId': 613, 'action': 'load',
                                      'itemCode': self.horse['code'], 'source': 'storage', 'quantity': 1})
        self.assertEqual(self.save, before)
        applied = self.apply(state, preview)
        self.assertEqual(applied.status_code, 200, applied.get_data(as_text=True))
        data = self.save['userInfo']['player']['storageData']
        self.assertEqual(data['-2'], before['userInfo']['player']['storageData']['-2'])
        self.assertEqual(data['-8'][self.horse['code']], [1, ['Other sender'], [{'name': 'Other horse'}]])
        self.assertEqual(data['613'][self.horse['code']][2], [{'name': 'England horse', 'plantTime': 13579113, 'opaque': [6]}])
        self.assertEqual(next(row for row in self.save['world']['objectsArray'] if row['id'] == 613)['plantTime'], 13579113)
        self.assertEqual(self.save['craftingState'], before['craftingState'])
        self.assertEqual(self.save['world']['objectsArray'][:4], before['world']['objectsArray'][:4])
        self.assertEqual(self.save['userInfo']['unlockedWorldContentLicenses'], before['userInfo']['unlockedWorldContentLicenses'])
        self.assertEqual(self.save['_ownedWorldTravel'], before['_ownedWorldTravel'])
        once = self.path.read_bytes()
        self.assertEqual(self.apply(state, preview).status_code, 409)
        self.assertEqual(self.path.read_bytes(), once)
        self.assertEqual(self.get('/god-barn/resume?uid=fixture-farmer').status_code, 302)
        latest = copy.deepcopy(self.save)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.save = self.player.session('fixture-farmer')
        self.assertEqual(self.save, latest)


if __name__ == '__main__':
    unittest.main()
