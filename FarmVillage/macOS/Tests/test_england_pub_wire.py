"""Signed-AMF England Pub production; synthetic completed Pub preconditions."""
from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import test_england_pub_engine as engine_tests
import crafting
import engine

NOW = engine_tests.NOW


class EnglandPubWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway
    prepare = engine_tests.EnglandPubEngineTests.prepare
    travel = engine_tests.EnglandPubEngineTests.travel
    skill = engine_tests.EnglandPubEngineTests.skill

    def persist(self):
        with redirect_stdout(io.StringIO()):
            self.player.save_session('fixture-farmer')

    def send(self, method, params=(), *, now=NOW, sequence=None):
        self.sequence += 1
        sequence = self.sequence if sequence is None else sequence
        self.sequence = max(sequence, self.sequence)
        with mock.patch.object(crafting, 'timestamp_now', return_value=now), \
                mock.patch.object(self.server.commands, 'timestamp_now', return_value=now), \
                mock.patch.object(self.server, 'timestamp_now', return_value=now), \
                mock.patch.object(engine, 'timestamp_now', return_value=now):
            response = self.gateway([self.command(method, params, sequence)])
        return fixtures.gateway_results(self, response, [0])[0]['data']

    def test_signed_england_begin_home_roundtrip_rush_claim_use_retry_and_restart(self):
        self.prepare(home_pub=True)
        self.persist()
        for code, amount in crafting._ingredients(crafting._recipe('ln')).items():
            self.send('FarmService.onPurchaseBushel', [code, 'ln', amount])
        queued = self.send('CraftingService.onBeginRecipe', ['ln', 0])
        self.assertEqual((queued['worldType'], queued['start_ts'], queued['finish_ts']),
                         ('england', NOW, NOW + 21600))
        home = self.send('WorldService.loadOwnWorld', ['farm'])
        self.assertEqual(home['craftingState']['recipeQueue']['pub'], [])
        self.assertEqual(next(row for row in home['craftingState']['craftingSkillState']['craftTypes']
                              if row['type'] == 'pub')['owner'], 'Home')
        self.send('WorldService.loadOwnWorld', ['england'])
        self.assertEqual(self.save['craftingState']['recipeQueue']['pub'], [queued])
        cash = self.save['userInfo']['player']['cash']
        self.assertEqual(self.send('CraftingService.onRushRecipe', ['ln', NOW, False, 0], now=NOW + 1, sequence=50), {})
        self.assertEqual(self.save['userInfo']['player']['cash'], cash - 5)
        accepted = copy.deepcopy(self.save)
        self.send('CraftingService.onRushRecipe', ['ln', NOW, False, 0], now=NOW + 2, sequence=50)
        self.assertEqual(self.save, accepted)
        result = self.send('CraftingService.onClaimFinishedRecipes', ['ln', 0], now=NOW + 3, sequence=51)
        self.assertEqual(result, [{'recipeId': 'ln', 'start_ts': NOW, 'quantity': 2,
                                  'productItemCode': 'ln', 'numGiftProducts': 1, 'recipeLevel': 1}])
        accepted = copy.deepcopy(self.save)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.save = self.player.session('fixture-farmer')
        self.assertEqual(self.save, accepted)
        self.send('CraftingService.onClaimFinishedRecipes', ['ln', 0], now=NOW + 4, sequence=51)
        self.assertEqual(self.save, accepted)
        self.send('WorldService.loadOwnWorld', ['farm'])
        self.send('CraftingService.onUseCraftedGood', ['ln:1'], now=NOW + 5)
        self.assertEqual(self.save['userInfo']['player']['energy'], 35)
        self.assertEqual(self.save['userInfo']['player']['storageData']['-7'], {})
        self.assertEqual(json.loads(self.path.read_text()), self.save)

    def test_signed_mixed_batch_retains_only_accepted_english_upgrade(self):
        self.prepare()
        self.skill.update(xp=6, exp=6)
        self.persist()
        gold = self.save['userInfo']['player']['gold']
        response = self.gateway([
            self.command('CraftingService.onBuyCraftUpgrade', ['pub', False], 2),
            self.command('CraftingService.onRushRecipe', ['ln', NOW, False, 0], 3)])
        fixtures.gateway_results(self, response, [0, 29])
        self.save = self.player.session('fixture-farmer')
        self.assertEqual(self.skill['level'], 2)
        self.assertEqual(self.save['userInfo']['player']['gold'], gold - 50000)
        self.assertEqual(json.loads(self.path.read_text()), self.save)


if __name__ == '__main__':
    unittest.main()
