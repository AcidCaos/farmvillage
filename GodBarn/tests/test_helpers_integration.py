"""Collection and quest tools retain the Barn's snapshot and revision boundary."""

import copy
import json
import unittest

import test_integration as live_fixtures
import test_server as copied_fixtures
from GodBarn.integration import LiveGodBarn


DEFINITIONS = {
    "schemaVersion": 1,
    "collections": [{"name": "grains", "code": "C001", "type": "permanent",
                     "displayName": "Grains Collection", "items": [
                         {"code": "strawberry-code", "rarity": "rare", "numneeded": 1}]}],
    "quests": [{"name": "test_quest", "displayName": "Test quest", "tasks": [
        {"action": "harvestByCode", "type": "strawberry-code", "total": 2,
         "displayName": "Harvest 2 Strawberries"}]}],
}


class LiveHelperBoundaryTests(unittest.TestCase):
    setUp = live_fixtures.LiveIntegrationTests.setUp
    tearDown = live_fixtures.LiveIntegrationTests.tearDown
    get = live_fixtures.LiveIntegrationTests.get
    post = live_fixtures.LiveIntegrationTests.post
    apply = live_fixtures.LiveIntegrationTests.apply

    def configure(self):
        (self.root / 'data/helpers.json').write_text(json.dumps(DEFINITIONS))
        # The constructor must load the definitions from the staged Barn data.
        loaded = LiveGodBarn(self.app, self.game, self.player, self.bundle, self.root)
        self.bridge.engine = loaded.engine
        self.player.session('farm-a')['questState'] = {
            'active': {'test_quest': {'progress': [0], 'new': 1, 'keep': 'metadata'}},
            'completed': [], 'retired': [], 'unknown': 'preserve',
        }

    def preview_operation(self, operation):
        state = self.get('/god-barn/api/state').get_json()
        response = self.post('/god-barn/api/preview', {
            'farmId': state['farm']['id'], 'revision': state['farm']['revision'],
            'operation': operation})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json(), state

    def test_inspection_is_read_only_and_validates_queries(self):
        self.configure()
        before = copy.deepcopy(self.player.farms)
        result = self.get('/god-barn/api/helpers?kind=quest').get_json()
        self.assertEqual(result['items'][0]['name'], 'test_quest')
        self.assertEqual(result['items'][0]['tasks'][0]['remaining'], 2)
        for query in ('kind=unknown', 'status=unknown', 'page=0', 'limit=bad'):
            self.assertEqual(self.get('/god-barn/api/helpers?' + query).status_code, 400)
        self.assertEqual(self.player.farms, before)

    def test_task_preview_apply_rejects_stale_retry_and_restore_preserves_quest(self):
        self.configure()
        before = copy.deepcopy(self.player.farms)
        preview, state = self.preview_operation({'type': 'quest', 'name': 'test_quest', 'task': 0})
        self.assertEqual(self.player.farms, before)
        applied = self.apply(preview, state)
        self.assertEqual(applied.status_code, 200)
        after = self.player.session('farm-a')
        self.assertEqual(after['questState']['active']['test_quest']['progress'], [2])
        self.assertEqual(after['questState']['active']['test_quest']['keep'], 'metadata')
        self.assertEqual(after['userInfo']['player'], before['farm-a']['userInfo']['player'])
        self.assertEqual(after['questState']['completed'], [])
        self.assertEqual(self.player.session('farm-b'), before['farm-b'])
        self.assertEqual(self.apply(preview, state).status_code, 409)
        current = applied.get_json()
        snapshot = next(entry for entry in current['history'] if entry['original'])
        restored = self.post('/god-barn/api/restore', {
            'farmId': 'farm-a', 'revision': current['farm']['revision'], 'id': snapshot['id']})
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(self.player.farms, before)

    def test_collection_apply_changes_only_missing_ownership_counters(self):
        self.configure()
        player = self.player.session('farm-a')['userInfo']['player']
        player.update(collectionCounters={'unknown-code': 19}, collectionLevels={'grains': 2},
                      storedCollections={'previous-set': True})
        before = copy.deepcopy(self.player.farms)
        operation = {'type': 'collection', 'name': 'grains', 'action': 'fill'}
        preview, state = self.preview_operation(operation)
        self.assertEqual(self.player.farms, before)
        response = self.apply(preview, state)
        self.assertEqual(response.status_code, 200)
        expected = copy.deepcopy(before)
        expected['farm-a']['userInfo']['player']['collectionCounters']['strawberry-code'] = 1
        self.assertEqual(self.player.farms, expected)
        repeated, _ = self.preview_operation(operation)
        self.assertEqual(repeated['changes'], [])


class CopiedHelperBoundaryTests(unittest.TestCase):
    setUp = copied_fixtures.CompanionFixture.setUp
    tearDown = copied_fixtures.CompanionFixture.tearDown

    def test_copied_helper_loads_and_snapshots_selected_task(self):
        data = self.root / 'data'
        (data / 'rules.json').write_text(json.dumps({
            'levels': [{'level': 1, 'xp': 0}, {'level': 2, 'xp': 100}],
            'inGameDaySeconds': 82800, 'growMultiplier': 1, 'witherMultiplier': 2.2}))
        (data / 'helpers.json').write_text(json.dumps(DEFINITIONS))
        save = copied_fixtures.farm_save()
        save['questState'] = {'active': {'test_quest': {'progress': [0], 'new': 1}}}
        (data / 'bootstrap-save.json').write_text(json.dumps(save))
        app = copied_fixtures.GodBarn(self.root, self.base / 'helper-workspace')
        initial = app.state()
        self.assertEqual(app.helpers_page({'kind': ['quest']})['items'][0]['name'], 'test_quest')
        operation = {'type': 'quest', 'name': 'test_quest', 'task': 0}
        preview = app.preview(operation, initial['farm']['revision'], initial['farm']['id'])
        self.assertEqual(app.state()['farm']['save'], initial['farm']['save'])
        result = app.apply(preview['token'], initial['farm']['revision'], initial['farm']['id'])
        self.assertEqual(result['farm']['save']['questState']['active']['test_quest']['progress'], [2])
        self.assertEqual(result['farm']['summary']['coins'], initial['farm']['summary']['coins'])
        self.assertGreater(len(result['history']), len(initial['history']))


if __name__ == '__main__':
    unittest.main()
