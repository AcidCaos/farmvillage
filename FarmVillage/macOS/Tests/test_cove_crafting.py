"""Cove's exact restaurant contract on disposable synthetic saves.

Seeded skills/bushels are fixture preconditions; no original clock is shortened.
Signed-AMF world entry and graphical client acceptance are separate gates.
"""
from contextlib import redirect_stdout
import copy
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import crafting
import items

CRAFT, WORLD, NAME = 'restaurant', 'fisherman', 'xcovecraftingcottage'
CODES = frozenset(('0b9', '0b6', '0bx', '0bN', '0ca', '0b5', '0bL', '7Jp',
                  '0bu', '0b2', '0bT', '0bP', '0a8', '0bB', '7KI', '0bv', '0ba',
                  '0kS'))
NOW = 1800000000


class CoveCraftingTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture

    def prepare(self, level=1, experience=0):
        self.save = self.fixture()
        self.save['userInfo']['currentWorldType'] = WORLD
        self.save['userInfo']['player'].update(xp=100015, gold=6000000, cash=10000,
            energy=5, storageData={}, seenFlags={'placeCottage': True})
        self.save['world'].update(sizeX=50, sizeY=50, tileSet=WORLD, objectsArray=[{
            'id': 600, 'itemName': NAME, 'className': 'CraftingCottageBuilding',
            'state': 'built', 'isFullyBuilt': True, 'craftLevel': level,
            'position': {'x': 10, 'y': 10, 'z': 0}, 'imported': {'keep': [1]}}])
        self.save['craftingState'] = {'craftingItems': [], 'craftingSkillState': {
            'recipeStates': [], 'craftTypes': []}, 'imported': {'keep': True}}
        crafting.start_session(self.save)
        self.skill.update(exp=experience, xp=experience, imported={'keep': 2})
        self.sequence = 0

    @property
    def skill(self):
        return next(r for r in self.save['craftingState']['craftingSkillState']['craftTypes']
                    if r['type'] == CRAFT)

    def call(self, method, params=(), now=NOW, sequence=None):
        self.sequence += 1
        sequence = self.sequence if sequence is None else sequence
        self.sequence = max(sequence, self.sequence)
        with redirect_stdout(io.StringIO()):
            return crafting.dispatch(self.save, method, params, now=now, request_id=sequence)

    def reject(self, method, params=(), **kwargs):
        before = copy.deepcopy(self.save)
        with self.assertRaises(ValueError):
            self.call(method, params, **kwargs)
        self.assertEqual(self.save, before)

    def buy(self, code, now=NOW):
        for ingredient, quantity in crafting._ingredients(crafting._recipe(code)).items():
            self.call('FarmService.onPurchaseBushel', [ingredient, code, quantity], now=now)

    def test_exact_craft_item_recipe_and_untouched_projection_contract(self):
        root = crafting._catalog()[0]
        skill = root.find("craftSkills/craftSkill[@id='restaurant']")
        self.assertEqual(skill.find('cottageBuilding').get('name'), NAME)
        self.assertEqual(skill.findtext('recipeQueueClass'), 'CraftingRecipeQueueManager')
        self.assertEqual(skill.findtext('defaultRecipe'), '0b6')
        self.assertEqual(crafting.REGIONAL_RECIPES[CRAFT], CODES)
        self.assertEqual({r.get('id') for r in root.find('recipes') if r.findtext('craft') == CRAFT}, CODES | {'h1O'})
        with self.assertRaises(ValueError): crafting._recipe('h1O')
        projected = ET.fromstring(zlib.decompress(crafting.client_payload()))
        self.assertEqual(projected.findtext("recipes/CraftingRecipe[@id='h1O']/ComingSoon"), '1')
        for code in CODES:
            recipe = crafting._recipe(code)
            self.assertEqual(ET.tostring(recipe), ET.tostring(projected.find(
                "recipes/CraftingRecipe[@id='%s']" % code)))
            self.assertEqual(recipe.find('Reward/OnFinish').get('itemCode'), code)
            self.assertIsNone(recipe.find('prereqs'))
        item = items.get_item_by_name(NAME)
        self.assertEqual((item['code'], item['className'], item['craftType']),
                         ('^2', 'CraftingCottageBuilding', CRAFT))
        self.assertTrue(crafting.regional_cottage(WORLD, NAME))
        for world in ('farm', 'england', 'meadows', 'htown', 'rainforest'):
            self.assertFalse(crafting.regional_cottage(world, NAME))

    def test_every_nonseasonal_recipe_natural_timer_rewards_and_fuel(self):
        for code in CODES - {'0kS'}:
            with self.subTest(code=code):
                self.prepare(level=5)
                recipe = crafting._recipe(code)
                self.buy(code)
                xp = self.save['userInfo']['player']['xp']
                row = self.call('CraftingService.onBeginRecipe', [code, 0])
                finish = NOW + int(recipe.findtext('MinutesToCook')) * 60
                self.assertEqual((row['worldType'], row['start_ts'], row['finish_ts']),
                                 (WORLD, NOW, finish))
                self.assertEqual(self.save['userInfo']['player']['xp'],
                                 xp + int(recipe.find('Reward/OnMake').get('playerXp')))
                self.reject('CraftingService.onClaimFinishedRecipes', [code, 0], now=finish - 1)
                result = self.call('CraftingService.onClaimFinishedRecipes', [code, 0], now=finish)
                reward = recipe.find('Reward/OnFinish')
                self.assertEqual(result[0]['quantity'], int(reward.get('sellQty')))
                self.assertEqual(result[0]['numGiftProducts'], int(reward.get('giftQty')))
                self.assertEqual(result[0]['productItemCode'], code)
                level = result[0]['recipeLevel']
                fuel = next(int(r.get('fuel')) for r in crafting._catalog()[0].find('recipeLevels')
                            if r.get('num') == str(level))
                self.call('CraftingService.onUseCraftedGood', ['%s:%s' % (code, level)], now=finish+1)
                self.assertEqual(self.save['userInfo']['player']['energy'], 5 + fuel)
                self.assertEqual(self.save['world']['objectsArray'][0]['imported'], {'keep': [1]})

    def test_expired_recipe_remains_expired_and_original_window_works(self):
        self.prepare()
        self.reject('FarmService.onPurchaseBushel', ['0e8', '0kS', 1])
        self.reject('CraftingService.onBeginRecipe', ['0kS', 0])
        old_now = int(datetime(2011, 10, 25, tzinfo=timezone.utc).timestamp())
        self.buy('0kS', now=old_now)
        row = self.call('CraftingService.onBeginRecipe', ['0kS', 0], now=old_now)
        self.assertEqual(row['finish_ts'], old_now + 21600)

    def test_all_skill_upgrades_coin_and_cash_exact_prices_and_slots(self):
        for rush in (False, True):
            self.prepare(experience=200 if not rush else 0)
            for level, required, coins, cash, slots in (
                    (2, 6, 50000, 15, 3), (3, 18, 100000, 25, 4),
                    (4, 27, 400000, 40, 5), (5, 36, 1000000, 60, 6)):
                before = copy.deepcopy(self.save['userInfo']['player'])
                experience = self.skill['exp']
                self.assertEqual(self.call('CraftingService.onBuyCraftUpgrade', [CRAFT, rush]),
                                 {'rewardLink': None})
                self.assertEqual(self.save['userInfo']['player']['gold'], before['gold'] - (0 if rush else coins))
                self.assertEqual(self.save['userInfo']['player']['cash'], before['cash'] - (cash if rush else 0))
                self.assertEqual((self.skill['level'], self.skill['exp'], crafting._oven_capacity(self.skill)),
                                 (level, max(0, experience-required), slots))
                self.assertEqual(self.skill['imported'], {'keep': 2})
            self.reject('CraftingService.onBuyCraftUpgrade', [CRAFT, rush])

    def test_purchase_tiers_are_detached_exact_and_world_bound(self):
        self.prepare()
        self.save['world']['objectsArray'] = []
        item = items.get_item_by_name(NAME)
        original = copy.deepcopy(item)
        first = crafting.purchase_catalog_item(self.save, item)
        self.assertEqual((first['market'], first['cost'], first['buyXp'], first['requiredLevel']),
                         ('coins', '100000', '1000', '15'))
        for count in (1, 2):
            self.save['userInfo']['player']['storageData']['-1'] = {'LA': [count, [], []]}
            tier = crafting.purchase_catalog_item(self.save, item)
            self.assertEqual((tier['market'], tier['cash']), ('cash', '80'))
        self.save['userInfo']['player']['storageData']['-1'] = {'LA': [3, [], []]}
        with self.assertRaises(ValueError): crafting.purchase_catalog_item(self.save, item)
        self.assertEqual(item, original)
        self.save['userInfo']['currentWorldType'] = 'farm'
        with self.assertRaises(ValueError): crafting.purchase_catalog_item(self.save, item)

    def test_wrong_world_missing_ownership_forged_queue_and_insufficient_funds_are_atomic(self):
        self.prepare()
        self.reject('CraftingService.onBeginRecipe', ['0ca', 0])
        for world in ('farm', 'england', 'htown', 'rainforest'):
            self.save['userInfo']['currentWorldType'] = world
            self.reject('CraftingService.onBuyCraftUpgrade', [CRAFT, True])
            self.reject('CraftingService.onBeginRecipe', ['0b6', 0])
        self.save['userInfo']['currentWorldType'] = WORLD
        self.save['userInfo']['player']['cash'] = 4
        self.reject('CraftingService.onBuyCraftUpgrade', [CRAFT, True])
        self.prepare()
        self.buy('0b6')
        self.call('CraftingService.onBeginRecipe', ['0b6', 0])
        accepted = copy.deepcopy(self.save)
        self.save['craftingState']['recipeQueue'][CRAFT][0]['worldType'] = 'farm'
        self.reject('CraftingService.onClaimFinishedRecipes', ['0b6', 0], now=NOW+21600)
        self.save = accepted
        self.save['world']['objectsArray'] = []
        self.reject('CraftingService.onBeginRecipe', ['0b6', 0])

    def test_retry_json_reload_and_other_world_queues_are_preserved(self):
        self.prepare()
        self.save['craftingState']['recipeQueue']['xhdcrafttype'] = [{'opaque': {'keep': True}}]
        self.buy('0b6')
        row = self.call('CraftingService.onBeginRecipe', ['0b6', 0], sequence=100)
        accepted = copy.deepcopy(self.save)
        self.save = json.loads(json.dumps(self.save))
        self.assertEqual(self.call('CraftingService.onBeginRecipe', ['0b6', 0], now=NOW+1, sequence=100), row)
        self.assertEqual(self.save, accepted)
        self.reject('CraftingService.onBeginRecipe', ['0bx', 0], sequence=100)
        self.call('CraftingService.onClaimFinishedRecipes', ['0b6', 0], now=NOW+21600, sequence=101)
        self.assertEqual(self.save['craftingState']['recipeQueue']['xhdcrafttype'], [{'opaque': {'keep': True}}])
        claimed = copy.deepcopy(self.save)
        self.call('CraftingService.onClaimFinishedRecipes', ['0b6', 0], now=NOW+21601, sequence=101)
        self.assertEqual(self.save, claimed)

    def test_empty_cove_preview_initializes_only_own_zero_cost_skill(self):
        self.prepare()
        self.save['world']['objectsArray'] = []
        self.save['craftingState'] = {}
        before = copy.deepcopy(self.save['userInfo']['player'])
        crafting.initialize(self.save)
        self.assertEqual(self.save['craftingState']['craftingSkillState']['craftTypes'],
                         [{'type': CRAFT, 'level': 1, 'xp': 0, 'exp': 0}])
        self.assertEqual(self.save['craftingState']['recipeQueue'], {})
        self.assertEqual(self.save['userInfo']['player'], before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
