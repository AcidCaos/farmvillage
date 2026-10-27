"""New Barn tools use the existing revision, preview and transaction boundary."""

import copy
import gzip
import json
from types import SimpleNamespace
import unittest

import test_integration as fixtures
import test_server as copied_fixtures
from GodBarn.integration import LiveGodBarn
from GodBarn.progression_tools import ProgressionTools


DEFINITIONS = {"ribbons": [{"code": "A005", "name": "harvests", "displayName": "Harvests",
    "counterSource": "cumulative", "levels": [{"count": 1, "xp": 5, "coins": 10},
                                                  {"count": 3, "xp": 20, "coins": 25}]}]}


class NewToolsIntegrationTests(unittest.TestCase):
    setUp = fixtures.LiveIntegrationTests.setUp
    tearDown = fixtures.LiveIntegrationTests.tearDown
    get = fixtures.LiveIntegrationTests.get
    post = fixtures.LiveIntegrationTests.post
    apply = fixtures.LiveIntegrationTests.apply

    def configure_progression(self):
        self.bridge.engine.progression = ProgressionTools(self.bridge.engine.catalog, DEFINITIONS)

    def preview_operation(self, operation):
        state = self.get('/god-barn/api/state').get_json()
        response = self.post('/god-barn/api/preview', {
            'farmId': state['farm']['id'], 'revision': state['farm']['revision'], 'operation': operation})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json(), state

    def test_progression_pages_validate_inputs_and_do_not_change_the_farm(self):
        self.configure_progression()
        original = copy.deepcopy(self.player.farms)
        response = self.get('/god-barn/api/progression?kind=ribbon&limit=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['items'][0]['code'], 'A005')
        self.assertEqual(response.get_json()['total'], 1)
        for query in ('limit=bad', 'kind=unknown', 'page=0'):
            self.assertEqual(self.get('/god-barn/api/progression?' + query).status_code, 400)
        self.assertEqual(self.player.farms, original)

    def test_progression_preview_apply_retry_and_snapshot_restore(self):
        self.configure_progression()
        original = copy.deepcopy(self.player.farms)
        operation = {'type': 'progression', 'kind': 'ribbon', 'code': 'A005', 'count': 3}
        preview, state = self.preview_operation(operation)
        self.assertEqual(self.player.farms, original)
        applied = self.apply(preview, state)
        self.assertEqual(applied.status_code, 200)
        player = self.player.session('farm-a')['userInfo']['player']
        self.assertEqual((player['gold'], player['xp'], player['achievements']['A005']), (235, 25, 1))
        self.assertEqual(self.apply(preview, state).status_code, 409)
        repeated, current = self.preview_operation(operation)
        self.assertEqual(repeated['changes'], [])
        self.assertEqual(self.apply(repeated, current).status_code, 200)
        self.assertEqual(self.player.session('farm-a')['userInfo']['player']['gold'], 235)
        snapshots = self.get('/god-barn/api/state').get_json()
        original_snapshot = next(record for record in snapshots['history'] if record['original'])
        restored = self.post('/god-barn/api/restore', {'farmId': 'farm-a',
            'revision': snapshots['farm']['revision'], 'id': original_snapshot['id']})
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(self.player.farms, original)

    def test_farming_delegation_is_detached_and_commits_once(self):
        def inspect(save, now):
            return {'bulk': {'animals': {'total': 1, 'ready': 1, 'ids': [9]}}, 'buildings': []}

        def apply(save, operation, now):
            result = copy.deepcopy(save)
            result['userInfo']['player']['gold'] += 88
            return {'save': result, 'summary': 'Harvested one eligible animal.', 'warnings': []}

        self.bridge.engine.farming_module = SimpleNamespace(inspect=inspect, apply=apply,
            OPERATION_FIELDS={'bulk_harvest': {'target'}})
        original = copy.deepcopy(self.player.farms)
        status = self.get('/god-barn/api/farming').get_json()
        self.assertTrue(status['available'])
        self.assertEqual(status['bulk']['animals']['ready'], 1)
        preview, state = self.preview_operation({'type': 'bulk_harvest', 'target': 'animals'})
        self.assertEqual(self.player.farms, original)
        self.assertEqual(self.apply(preview, state).status_code, 200)
        self.assertEqual(self.apply(preview, state).status_code, 409)
        self.assertEqual(self.player.session('farm-a')['userInfo']['player']['gold'], 288)
        self.assertEqual(self.player.session('farm-b'), original['farm-b'])
        self.assertEqual(self.player.session('farm-a')['unknownFeature'], original['farm-a']['unknownFeature'])

    def test_history_overlay_loads_in_live_adapter_without_rewriting_catalog(self):
        data = self.root / 'data'
        original = (data / 'catalog.json.gz').read_bytes()
        metadata = {'schema': 1, 'sources': [{'id': 'archive', 'title': 'Fixture archive'}],
            'items': {'cow': {'facts': {'coinYield': 6}, 'sourceIds': ['archive'],
                'releaseHistory': [{'date': '2009-12-15', 'acquisition': 'Mystery Box', 'event': 'Winter'}]}},
            'shelves': [{'id': 'mystery-fixture', 'name': 'Fixture shelf', 'items': ['cow'], 'sourceIds': ['archive']}]}
        (data / 'encyclopedia.json').write_text(json.dumps(metadata))
        bridge = LiveGodBarn(self.app, self.game, self.player, self.bundle, self.root)
        with self.app.test_request_context('/god-barn/api/catalog?year=2009&acquisition=Mystery%20Box'):
            result = bridge.catalog_page()
        self.assertEqual([item['name'] for item in result['items']], ['cow'])
        self.assertEqual(result['items'][0]['coinYield'], 6)
        self.assertIn('mystery-fixture', result['items'][0]['archive']['collections'])
        self.assertIn('2009', result['historyFilters']['years'])
        self.assertEqual((data / 'catalog.json.gz').read_bytes(), original)


class CopiedNewToolsTests(unittest.TestCase):
    setUp = copied_fixtures.CompanionFixture.setUp
    tearDown = copied_fixtures.CompanionFixture.tearDown

    def test_copied_mode_loads_new_definitions_and_keeps_farming_isolated(self):
        data = self.root / 'data'
        (data / 'rules.json').write_text(json.dumps({'levels': [{'level': 1, 'xp': 0}, {'level': 2, 'xp': 100}],
            'inGameDaySeconds': 82800, 'growMultiplier': 1, 'witherMultiplier': 2.2}))
        (data / 'progression.json').write_text(json.dumps(DEFINITIONS))
        app = copied_fixtures.GodBarn(self.root, self.base / 'new-tools-workspace')
        initial = app.state()
        self.assertEqual(app.progression_page({'kind': ['ribbon']})['items'][0]['code'], 'A005')
        self.assertFalse(app.farming_status()['available'])
        operation = {'type': 'progression', 'kind': 'ribbon', 'code': 'A005', 'count': 3}
        preview = app.preview(operation, initial['farm']['revision'], initial['farm']['id'])
        self.assertEqual(app.state()['farm']['summary']['coins'], 1000)
        applied = app.apply(preview['token'], initial['farm']['revision'], initial['farm']['id'])
        self.assertEqual(applied['farm']['summary']['coins'], 1035)
        self.assertEqual(applied['farm']['save']['unknownFeature'], initial['farm']['save']['unknownFeature'])


if __name__ == '__main__':
    unittest.main()
