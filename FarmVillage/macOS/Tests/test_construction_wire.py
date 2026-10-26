"""Classic construction through the real AMF gateway and temporary saved farms."""
from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

from pyamf import remoting

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures


class ConstructionWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    def prepare(self, name='turkeyroost', ident=600, built=False, **extra):
        from items import get_item_by_name
        path = self.write_fixture()
        save = self.player.session('fixture-farmer')
        item = get_item_by_name(name)
        obj = {'id': ident, 'itemName': name, 'className': item['className'], 'isFullyBuilt': built,
               'state': 'built' if built else 'construction', 'position': {'x': 10, 'y': 10, 'z': 0},
               'contents': [], 'plantTime': 1000000, 'importedBuilding': {'keep': [1, 2]}}
        obj.update(extra)
        save['world']['objectsArray'] = [obj]
        save['userInfo']['player']['storageData'] = {}
        return path, save, obj

    def send(self, action, obj, options=None):
        response = self.gateway([self.command('WorldService.performAction', [action, obj, [options or {}]])])
        return fixtures.gateway_results(self, response, [0])[0]['data']

    @staticmethod
    def snapshot(obj):
        return {'id': obj['id'], 'itemName': obj['itemName'], 'className': obj['className'],
                'state': obj['state'], 'position': copy.deepcopy(obj['position']), 'contents': []}

    @staticmethod
    def gift(save, name, amount=1):
        from items import get_item_by_name
        code = get_item_by_name(name)['code']
        save['userInfo']['player']['storageData'].setdefault('-1', {})[code] = [amount, ['friend'], [{'unit': n} for n in range(amount)]]

    def persist(self):
        with redirect_stdout(io.StringIO()):
            self.player.save_session('fixture-farmer')

    def test_final_turkey_material_callback_transform_persistence_and_retry(self):
        path, save, obj = self.prepare()
        # Archived storageConfig requires10 each, independent of the upstream PHP test.
        obj['contents'] = [{'itemCode': code, 'numItem': count, 'importedRow': 'keep'}
                           for code, count in [('K1', 9), ('K4', 10), ('K5', 10)]]
        self.gift(save, 'brick', 2); raw = self.snapshot(obj)
        result = self.send('store', raw, {'storedItemName': 'brick', 'storedItemCode': 'K1', 'isGift': True})
        self.assertEqual(result, {'id': 600, 'finishedName': 'turkeyroost_finished'})
        built = save['world']['objectsArray'][0]
        self.assertEqual(built['itemName'], 'turkeyroost_finished'); self.assertTrue(built['isFullyBuilt'])
        self.assertEqual(built['importedBuilding'], {'keep': [1, 2]})
        self.assertTrue(all(row['numItem'] == 0 and row['importedRow'] == 'keep' for row in built['contents']))
        self.assertNotIn('_constructionResponse', save)
        self.assertNotIn('_constructionResponse', json.loads(path.read_text()))
        before = path.read_bytes()
        self.assertEqual(self.send('store', raw, {'storedItemName': 'brick', 'isGift': True}), result)
        self.assertEqual(path.read_bytes(), before)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        reloaded = self.player.session('fixture-farmer')
        self.assertEqual(reloaded['world']['objectsArray'][0], built)
        self.assertEqual(reloaded['userInfo']['player']['storageData']['-1']['K1'][0], 1)

    def test_partial_and_completed_expansion_survive_move_snapshot_and_reload(self):
        path, save, obj = self.prepare('turkeyroost_finished', built=True, expansionLevel=1,
            expansionParts={'K1': 13, 'K4': 15, 'K5': 15, 'legacy': {'keep': True}},
            contents=[{'itemCode': 'd7', 'numItem': 1, 'importedOccupant': 'keep'}])
        self.gift(save, 'brick', 2)
        self.send('store', self.snapshot(obj), {'storedItemName': 'brick', 'isGift': True})
        obj = save['world']['objectsArray'][0]
        self.assertEqual(obj['expansionParts']['K1'], 14); self.assertEqual(obj['expansionLevel'], 1)
        self.send('store', self.snapshot(obj), {'storedItemName': 'brick', 'isGift': True})
        expanded = save['world']['objectsArray'][0]
        self.assertEqual((expanded['expansionLevel'], expanded['capacity']), (2, 30))
        self.assertEqual(expanded['expansionParts'], {'legacy': {'keep': True}})
        forged = {**self.snapshot(expanded), 'itemName': 'cow', 'className': 'Animal', 'isFullyBuilt': False, 'state': 'construction',
                  'expansionLevel': 50, 'expansionParts': {'K1': 999}, 'capacity': 999}
        forged['position']['x'] = 11
        self.send('move', forged)
        moved = save['world']['objectsArray'][0]
        self.assertEqual((moved['itemName'], moved['className'], moved['isFullyBuilt']), ('turkeyroost_finished', 'TurkeyRoostBuilding', True))
        self.assertEqual((moved['expansionLevel'], moved['capacity']), (2, 30)); self.assertEqual(moved['position']['x'], 11)
        self.assertEqual(moved['state'], 'built')
        self.assertEqual(moved['contents'], expanded['contents'])
        with redirect_stdout(io.StringIO()): self.player.load_saves()
        self.assertEqual(self.player.session('fixture-farmer')['world']['objectsArray'][0], moved)

    def test_combine_final_vehicle_part_records_original_objective_once_and_retries(self):
        import england_progression
        from game_settings import level_to_xp
        import quests
        import world_travel
        # Story restoration is deferred in the product. Exercise its preserved
        # construction hook with an explicitly enabled, test-only catalog.
        story = mock.patch.object(england_progression, 'STORY_ENABLED', True)
        story.start()
        self.addCleanup(story.stop)
        catalog = mock.patch.object(quests, '_cached_quests', {
            **quests.get_quests(), **england_progression.quest_definitions()})
        catalog.start()
        self.addCleanup(catalog.stop)
        path, save, obj = self.prepare('xukcombineconstruct')
        save['userInfo']['player']['xp'] = level_to_xp(15)
        world_travel.switch(save, 'england', True, now=1_700_000_000)
        obj = copy.deepcopy(obj); obj['id'] = 700
        obj['contents'] = [{'itemCode': 'dS', 'numItem': 39}]
        save['world']['objectsArray'] = [obj]
        name = england_progression.QUEST_NAMES[1]
        save['questState'] = {'active': {name: {'progress': [0, 0], 'new': 0}},
                             'completed': [england_progression.QUEST_NAMES[0]], 'retired': [], 'replayed': {}}
        self.gift(save, 'vehiclepart', 2); self.persist()
        raw = self.snapshot(obj)
        with mock.patch.object(quests, 'record_action', wraps=quests.record_action) as record:
            self.assertEqual(self.send('store', raw, {'storedItemName': 'vehiclepart', 'isGift': True}),
                             {'id': 700, 'finishedName': 'xukcombine'})
            before = path.read_bytes()
            self.assertEqual(self.send('store', raw, {'storedItemName': 'vehiclepart', 'isGift': True}),
                             {'id': 700, 'finishedName': 'xukcombine'})
        events = [call for call in record.call_args_list if call.args[1:3] == ('completeConstructionBuildingByCode', 'ko')]
        self.assertEqual(len(events), 1)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(save['questState']['active'][name]['progress'], [1, 0])
        self.assertEqual(save['userInfo']['player']['storageData']['-1']['dS'][0], 1)

    def test_new_placement_cannot_inject_completed_site_or_expansion_parts(self):
        path, save, obj = self.prepare()
        save['world']['objectsArray'] = []
        self.gift(save, 'horsestablewhite')
        forged = {'id': 64000, 'itemName': 'horsestablewhite', 'className': 'HorseStableBuilding',
                  'state': 'built', 'position': {'x': 8, 'y': 8, 'z': 0}, 'isFullyBuilt': True,
                  'expansionLevel': 5, 'capacity': 40, 'expansionParts': {'K1': 50},
                  'contents': [{'itemCode': 'K1', 'numItem': 50}]}
        placed = self.send('place', forged, {'isGift': True})
        stable = next(row for row in save['world']['objectsArray'] if row['id'] == placed['id'])
        self.assertFalse(stable['isFullyBuilt']); self.assertEqual(stable['state'], 'construction')
        self.assertEqual(stable['expansionLevel'], 1); self.assertEqual(stable['expansionParts'], {})
        self.assertEqual(stable['contents'], [{'itemCode': 'K1', 'numItem': 1}]); self.assertNotIn('capacity', stable)

    def test_invalid_followup_keeps_final_material_and_transformation(self):
        path, save, obj = self.prepare('orchard')
        obj['contents'] = [{'itemCode': code, 'numItem': count}
                           for code, count in [('K1', 9), ('K4', 10), ('K5', 10)]]
        self.gift(save, 'brick'); self.persist(); before = path.read_bytes()
        response = self.gateway([
            self.command('WorldService.performAction', ['store', self.snapshot(obj), [{'storedItemName': 'brick', 'isGift': True}]]),
            self.command('WorldService.performAction', ['use', {'id': 999, 'itemName': 'cow'}, []], 2),
        ])
        fixtures.gateway_results(self, response, [0, 29])
        restored = self.player.session('fixture-farmer')
        self.assertEqual(restored['world']['objectsArray'][0]['itemName'], 'orchard_finished')
        self.assertNotIn('K1', restored['userInfo']['player']['storageData']['-1'])
        self.assertNotIn('_constructionResponse', restored)
        self.assertEqual(json.loads(path.read_text()), restored)

    def test_overfill_missing_source_and_unsupported_orchard_upgrade_never_charge(self):
        path, save, obj = self.prepare('orchard_finished', built=True)
        self.gift(save, 'brick'); self.persist(); before = path.read_bytes()
        response = self.gateway([self.command('WorldService.performAction', ['store', self.snapshot(obj),
            [{'storedItemName': 'brick', 'currency': 'cash'}]])])
        fixtures.assert_gateway_rejected(self, response); self.assertEqual(path.read_bytes(), before)
        path, save, obj = self.prepare()
        self.persist(); before = path.read_bytes()
        for options in ({'storedItemName': 'brick', 'numToStore': 11, 'currency': 'cash'},
                        {'storedItemName': 'brick', 'isGift': True}):
            response = self.gateway([self.command('WorldService.performAction', ['store', self.snapshot(obj), [options]])])
            fixtures.assert_gateway_rejected(self, response); self.assertEqual(path.read_bytes(), before)

    def test_construction_callback_metadata_is_not_saved_or_nested_in_init_user(self):
        path, save, obj = self.prepare()
        save['_constructionResponse'] = {'finishedName': 'not-for-init'}
        self.persist()
        self.assertNotIn('_constructionResponse', json.loads(path.read_text()))
        response = self.gateway([self.command('UserService.initUser', ['QA', 0, True, None])])
        self.assertEqual(response.status_code, 200)
        data = remoting.decode(response.data).bodies[0][1].body['data'][0]['data']
        self.assertNotIn('_constructionResponse', data)
        self.assertIn('ugcItemData', data)

    def test_alternate_actions_and_replacement_ids_cannot_bypass_construction(self):
        path, save, obj = self.prepare()
        save['world']['objectsArray'] = [{'id': 7, 'itemName': 'cow', 'className': 'Animal',
                                          'position': {'x': 9, 'y': 9, 'z': 0}, 'state': 'bare'}]
        self.persist(); before = path.read_bytes()
        for action, ident in [('plow', 999), ('clearWithered', 999), ('use', 999), ('place', 7), ('move', 7)]:
            with self.subTest(action=action):
                forged = {**self.snapshot(obj), 'id': ident, 'isFullyBuilt': True,
                          'expansionLevel': 5, 'capacity': 40}
                response = self.gateway([self.command('WorldService.performAction', [action, forged, [{}]])])
                fixtures.assert_gateway_rejected(self, response)
                self.assertEqual(path.read_bytes(), before)

    def test_sheep_pen_exact_feature_expansions_preserve_parent_metadata_and_reload(self):
        path, save, obj = self.prepare('xuk_sheep_pen_finished', built=True,
            expansionLevel=1, expansionParts={'K1': 14, 'K4': 15, 'K5': 15}, capacity=20,
            contents=[{'itemCode': 'cw', 'numItem': 1}],
            storageMetadata={'cw:original': [{'dna': 'preserve'}]},
            extraDataState={'breedingQueue': [], 'breedHistory': {'keep': True}})
        save['userInfo']['player']['storageData']['600'] = {'cw': [1, [], ['original-parent-dna']]}
        parents = copy.deepcopy(save['userInfo']['player']['storageData']['600'])
        self.gift(save, 'brick', 2)
        self.assertEqual(self.send('store', self.snapshot(obj), {'storedItemName': 'brick', 'isGift': True}), {'id': 600})
        pen = save['world']['objectsArray'][0]
        self.assertEqual((pen['expansionLevel'], pen['capacity']), (2, 30))
        self.assertEqual(pen['storageMetadata'], {'cw:original': [{'dna': 'preserve'}]})
        self.assertEqual(save['userInfo']['player']['storageData']['600'], parents)
        pen['expansionParts'].update(K1=20, K4=20, K5=19)
        self.gift(save, 'woodenboard', 2)
        self.send('store', self.snapshot(pen), {'storedItemName': 'woodenboard', 'isGift': True})
        pen = save['world']['objectsArray'][0]
        self.assertEqual((pen['expansionLevel'], pen['capacity']), (3, 40))
        before = path.read_bytes()
        response = self.gateway([self.command('WorldService.performAction', ['store', self.snapshot(pen),
            [{'storedItemName': 'woodenboard', 'isGift': True}]])])
        fixtures.assert_gateway_rejected(self, response); self.assertEqual(path.read_bytes(), before)
        with redirect_stdout(io.StringIO()): self.player.load_saves()
        reloaded = self.player.session('fixture-farmer')
        self.assertEqual(reloaded['world']['objectsArray'][0], pen)
        self.assertEqual(reloaded['userInfo']['player']['storageData']['600'], parents)

    def test_sheep_pen_initial_site_and_expansion_survive_rejected_followup(self):
        from game_settings import level_to_xp
        from items import get_item_by_name
        path, save, obj = self.prepare('xuk_sheep_pen', built=False)
        self.gift(save, 'brick'); self.persist(); before = path.read_bytes()
        response = self.gateway([self.command('WorldService.performAction', ['store', self.snapshot(obj),
            [{'storedItemName': 'brick', 'isGift': True}]])])
        fixtures.gateway_results(self, response, [0])
        self.assertEqual(save['world']['objectsArray'][0]['contents'], [{'itemCode': 'K1', 'numItem': 1}])
        self.assertNotIn('K1', save['userInfo']['player']['storageData']['-1'])
        save['world']['objectsArray'] = []
        item = get_item_by_name('xuk_sheep_pen')
        self.assertEqual(item['requiredLevel'], '5')
        save['userInfo']['player']['xp'] = level_to_xp(int(item['requiredLevel']))
        self.persist(); before = path.read_bytes()
        response = self.gateway([self.command('WorldService.performAction', ['place',
            {'id': 64000, 'itemName': 'xuk_sheep_pen', 'className': 'SheepPenConstructionBuilding',
             'state': 'built', 'isFullyBuilt': True, 'position': {'x': 2, 'y': 2, 'z': 0}}, []])])
        fixtures.gateway_results(self, response, [0])
        placed = save['world']['objectsArray'][0]
        self.assertEqual(placed['itemName'], 'xuk_sheep_pen')
        self.assertFalse(placed['isFullyBuilt'])
        self.assertEqual(placed['contents'], [{'itemCode': 'K1', 'numItem': 1}])
        path, save, obj = self.prepare('xuk_sheep_pen_finished', built=True,
            expansionLevel=1, expansionParts={'K1': 14, 'K4': 15, 'K5': 15})
        self.gift(save, 'brick', 2); self.persist(); before = path.read_bytes()
        response = self.gateway([
            self.command('WorldService.performAction', ['store', self.snapshot(obj), [{'storedItemName': 'brick', 'isGift': True}]], 1),
            self.command('WorldService.performAction', ['use', {'id': 999, 'itemName': 'cow'}, []], 2)])
        fixtures.gateway_results(self, response, [0, 29])
        restored = self.player.session('fixture-farmer')
        self.assertEqual(restored['world']['objectsArray'][0]['expansionLevel'], 2)
        self.assertEqual(restored['userInfo']['player']['storageData']['-1']['K1'][0], 1)
        self.assertEqual(json.loads(path.read_text()), restored)


if __name__ == '__main__':
    unittest.main()
