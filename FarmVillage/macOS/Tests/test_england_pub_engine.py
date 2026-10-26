"""England Pub mechanics; all farms/skill preconditions are synthetic."""
from contextlib import redirect_stdout
import copy
from datetime import datetime, timezone
import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import test_crafting as legacy
import crafting
import world_travel

NOW = 1800000000


class EnglandPubEngineTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    call = legacy.CraftingTests.call
    purchase = legacy.CraftingTests.purchase
    assert_rejected_without_mutation = legacy.CraftingTests.assert_rejected_without_mutation

    @property
    def skill(self):
        return next(row for row in self.save['craftingState']['craftingSkillState']['craftTypes']
                    if row['type'] == 'pub')

    def travel(self, destination, create=False):
        # The hooks remain idempotent if world_travel also invokes them.
        crafting.before_world_switch(self.save, destination)
        world_travel.switch(self.save, destination, create, now=NOW)
        crafting.after_world_switch(self.save)

    def prepare(self, level=1, home_pub=False):
        legacy.CraftingTests.prepare(self, 'pub')
        self.save['userInfo']['player'].update(gold=6000000, cash=10000, xp=100015,
                                              seenFlags={'placeCottage': True})
        self.skill.update(level=5, exp=200, xp=200, owner='Home')
        if not home_pub:
            self.save['world']['objectsArray'] = []
        self.travel('england', True)
        self.save['world']['objectsArray'] = [{'id': 602, 'itemName': 'xukcraftingpub',
            'className': 'CraftingCottageBuilding', 'state': 'built', 'isFullyBuilt': True,
            'craftLevel': level, 'cottageName': 'Imported owner', 'foundingTS': 12345,
            'position': {'x': 10, 'y': 10, 'z': 0}, 'imported': {'keep': [1, 2]}}]
        # initialize() already supplies the level-one placement preview. Skill
        # levels above one are a clearly seeded precondition, never earned XP.
        crafting.initialize(self.save)
        self.skill.update(level=level, exp=0, xp=0)
        crafting.initialize(self.save)

    def test_all_seventeen_pub_recipes_keep_authored_clocks_products_and_global_fuel(self):
        self.assertEqual(len(crafting.RECIPES_BY_CRAFT['pub']), 17)
        for code in sorted(crafting.RECIPES_BY_CRAFT['pub']):
            with self.subTest(recipe=code):
                recipe = crafting._recipe(code)
                self.prepare(int(recipe.findtext('SkillLevelRequired')))
                date = recipe.findtext('limitedStart')
                now = (int(datetime.strptime(date, '%m/%d/%Y').replace(tzinfo=timezone.utc).timestamp()) + 86400
                       if date else NOW)
                for ingredient, amount in crafting._ingredients(recipe).items():
                    self.call('FarmService.onPurchaseBushel', [ingredient, code, amount], now)
                record = self.call('CraftingService.onBeginRecipe', [code, 0], now)
                self.assertEqual(record['worldType'], 'england')
                self.assertEqual(record['recipe'], crafting._php_xml(recipe))
                self.assertEqual(record['finish_ts'], now + int(recipe.findtext('MinutesToCook')) * 60)
                self.assert_rejected_without_mutation('CraftingService.onClaimFinishedRecipes', [code, 0],
                                                      now=record['finish_ts'] - 1)
                self.call('CraftingService.onRushRecipe', [code, now, False, 0], now + 1)
                result = self.call('CraftingService.onClaimFinishedRecipes', [code, 0], now + 2)
                level = int(recipe.findtext('InitialRecipeLevel'))
                reward = recipe.find('Reward/OnFinish')
                self.assertEqual(result, [{'recipeId': code, 'start_ts': now,
                    'quantity': int(reward.get('sellQty')), 'productItemCode': code,
                    'numGiftProducts': int(reward.get('giftQty')), 'recipeLevel': level}])
                public = copy.deepcopy(self.save['craftingState']['craftingPublicInventory']['publicGoods']['pub'])
                self.travel('farm')
                self.assertEqual(self.save['craftingState']['craftingPublicInventory']['publicGoods'].get('pub'), {})
                self.call('CraftingService.onUseCraftedGood', [f'{code}:{level}'], now + 3)
                fuel = next(int(row.get('fuel')) for row in crafting._catalog()[0].find('recipeLevels')
                            if row.get('num') == str(level))
                on_use = recipe.find('Reward/OnUse')
                if on_use is not None:
                    fuel *= float(on_use.get('fuel', '1'))
                    self.assertEqual(self.save['userInfo']['player']['storageData']['-1'][on_use.get('itemCode')][0], 1)
                self.assertEqual(self.save['userInfo']['player']['energy'], 5 + fuel)
                self.travel('england')
                self.assertEqual(self.save['craftingState']['craftingPublicInventory']['publicGoods']['pub'], public)

    def test_home_and_england_pub_skills_queues_names_and_clocks_do_not_copy(self):
        self.prepare(home_pub=True)
        self.assertEqual((self.skill['level'], self.skill['exp']), (1, 0))
        self.assertNotIn('owner', self.skill)
        self.purchase('ln')
        england = self.call('CraftingService.onBeginRecipe', ['ln', 0], NOW)
        self.skill.update(xp=6, exp=6, owner='England')
        self.call('CraftingService.onBuyCraftUpgrade', ['pub', False], NOW + 1)
        self.travel('farm')
        self.assertEqual((self.skill['level'], self.skill['exp'], self.skill['owner']), (5, 200, 'Home'))
        self.assertEqual(self.save['craftingState']['recipeQueue']['pub'], [])
        self.purchase('ln')
        home = self.call('CraftingService.onBeginRecipe', ['ln', 1], NOW + 10)
        self.assertEqual(home['worldType'], 'farm')
        self.travel('england')
        self.assertEqual((self.skill['level'], self.skill['exp'], self.skill['owner']), (2, 0, 'England'))
        self.assertEqual(self.save['craftingState']['recipeQueue']['pub'], [england])
        cottage = self.save['world']['objectsArray'][0]
        self.assertEqual((cottage['foundingTS'], cottage['cottageName'], cottage['imported']),
                         (12345, 'Imported owner', {'keep': [1, 2]}))
        self.travel('farm')
        self.assertEqual(self.save['craftingState']['recipeQueue']['pub'], [home])

    def test_all_skill_tiers_both_payment_routes_are_england_owned(self):
        for rush in (False, True):
            with self.subTest(cash_bypass=rush):
                self.prepare(home_pub=True)
                self.skill.update(exp=200 if not rush else 0, xp=200 if not rush else 0)
                balance = self.save['userInfo']['player']['cash' if rush else 'gold']
                required = 0
                for level, xp, gold, cash, ovens in ((2, 6, 50000, 15, 3), (3, 18, 100000, 25, 4),
                                                    (4, 27, 400000, 40, 5), (5, 36, 1000000, 60, 6)):
                    self.assertEqual(self.call('CraftingService.onBuyCraftUpgrade', ['pub', rush]), {'rewardLink': None})
                    balance -= cash if rush else gold
                    required += xp
                    self.assertEqual((self.skill['level'], crafting._oven_capacity(self.skill)), (level, ovens))
                    self.assertEqual(self.skill['exp'], 0 if rush else 200 - required)
                    self.assertEqual(self.save['userInfo']['player']['cash' if rush else 'gold'], balance)
                self.assert_rejected_without_mutation('CraftingService.onBuyCraftUpgrade', ['pub', rush])
                self.travel('farm')
                self.assertEqual((self.skill['level'], self.skill['exp']), (5, 200))

    def test_wrong_world_queue_unowned_and_cross_context_retry_refuse_without_mutation(self):
        self.prepare(home_pub=True)
        self.purchase('ln')
        self.call('CraftingService.onBeginRecipe', ['ln', 0], NOW)
        self.save['craftingState']['recipeQueue']['pub'][0]['worldType'] = 'farm'
        self.assert_rejected_without_mutation('CraftingService.onRushRecipe', ['ln', NOW, False, 0], now=NOW + 1)
        self.assert_rejected_without_mutation('CraftingService.onClaimFinishedRecipes', ['ln', 0], now=NOW + 30000)
        self.save['craftingState']['recipeQueue']['pub'][0]['worldType'] = 'england'
        self.call('CraftingService.onRushRecipe', ['ln', NOW, False, 0], NOW + 1, sequence=100)
        self.travel('farm')
        self.assert_rejected_without_mutation('CraftingService.onRushRecipe', ['ln', NOW, False, 0],
                                              now=NOW + 1, sequence=100)
        self.travel('england')
        self.save['world']['objectsArray'] = []
        for method, params in (('CraftingService.onBeginRecipe', ['ln', 1]),
                               ('FarmService.onPurchaseBushel', ['kc', 'lq', 1]),
                               ('CraftingService.onBuyCraftUpgrade', ['pub', True])):
            self.assert_rejected_without_mutation(method, params)

    def test_ambiguous_dual_pub_import_is_preserved_and_explicitly_blocked(self):
        self.prepare(home_pub=True)
        self.save['craftingState'].pop(crafting.PUB_WORLD_STATE)
        before = copy.deepcopy(self.save)
        with self.assertRaisesRegex(ValueError, 'unlabelled production'):
            crafting.initialize(self.save)
        self.assertEqual(self.save, before)

    def test_single_england_pub_import_preserves_existing_skill_and_queue(self):
        self.prepare()
        self.skill.update(level=3, exp=17, xp=17, imported={'keep': [4]})
        self.purchase('ln')
        queued = self.call('CraftingService.onBeginRecipe', ['ln', 0], NOW)
        self.save['craftingState'].pop(crafting.PUB_WORLD_STATE)
        crafting.initialize(self.save)
        self.assertEqual((self.skill['level'], self.skill['exp'], self.skill['imported']), (3, 17, {'keep': [4]}))
        self.assertEqual(self.save['craftingState']['recipeQueue']['pub'], [queued])
        self.assertEqual(self.save['world']['objectsArray'][0]['foundingTS'], 12345)

    def test_unlock_england_detached_creation_does_not_project_live_home_pub(self):
        legacy.CraftingTests.prepare(self, 'pub')
        self.save['userInfo']['player']['xp'] = 100015
        before = copy.deepcopy(self.save['craftingState'])
        world = copy.deepcopy(self.save['world'])
        self.assertEqual(world_travel.unlock_england(self.save, 'allAccess', now=NOW), [])
        self.assertEqual(self.save['craftingState'], before)
        self.assertEqual(self.save['world'], world)
        self.assertEqual(self.save['userInfo']['currentWorldType'], 'farm')
        self.assertIn('england', self.save[world_travel.STATE_KEY]['inactive'])
        self.travel('england')
        self.assertNotIn('pub', self.save['craftingState']['recipeQueue'])
        self.travel('farm')
        self.assertEqual(self.save['craftingState']['recipeQueue'], before['recipeQueue'])

    def test_legacy_mistletoe_receipt_keeps_same_world_retry_after_schema_change(self):
        self.prepare()
        self.save['userInfo']['currentWorldType'] = 'htown'
        self.save['world']['objectsArray'] = [{'id': 603, 'itemName': 'xhdcraftingcottage',
            'className': 'CraftingCottageBuilding', 'state': 'built', 'isFullyBuilt': True,
            'position': {'x': 10, 'y': 10, 'z': 0}}]
        self.save['craftingState'] = {'craftingItems': [], 'craftingSkillState': {
            'recipeStates': [], 'craftTypes': []}}
        crafting.initialize(self.save)
        result = self.call('CraftingService.onBuyCraftUpgrade', ['xhdcrafttype', True], sequence=200)
        self.save['craftingState']['localCraftingRequests']['200'].pop('worldType')
        accepted = copy.deepcopy(self.save)
        self.assertEqual(self.call('CraftingService.onBuyCraftUpgrade', ['xhdcrafttype', True], sequence=200), result)
        self.assertEqual(self.save, accepted)


if __name__ == '__main__':
    unittest.main()
