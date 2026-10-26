"""Recovered cottage skill upgrades, higher recipes, and paid queue rushes."""
from contextlib import redirect_stdout
import copy
import io
from pathlib import Path
import sys
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import test_crafting as legacy
import crafting
import items


EXPECTED_HIGHER = {
    'bakery': {'b3', 'b4', 'b5', 'b6', 'b7', 'b8', '7KJ', 'c0', 'c1', 'c2', 'c3', 'c4', 'c5', '7Kw', '0gl', '0xf', '0Y1'},
    'winery': {'0f8', 'w3', 'w4', 'w5', '7J5', 'w6', 'w7', 'w8', 'w9', 'c6', 'c7', 'c8', 'c9', 'd1', '7JR', '0su', '0Zc'},
    'perfumery': {'0fW', 'p3', 'p4', 'p5', 'p6', 'p7', 'p8', '7HT', 'p9', 'd2', 'd3', 'd4', 'd5', 'd6', '7H4', '0wW', '0Zd'},
    'pub': {'lu', 'ls', '7IR', 'lv', 'lr', '0hh', '7In'},
}


class CraftingProgressionTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    call = legacy.CraftingTests.call
    purchase = legacy.CraftingTests.purchase
    assert_rejected_without_mutation = legacy.CraftingTests.assert_rejected_without_mutation

    def prepare(self, craft='bakery'):
        legacy.CraftingTests.prepare(self, craft)
        self.save['userInfo']['player'].update(gold=6_000_000, cash=10_000, xp=100_015)
        return self.save

    def skill(self, craft='bakery'):
        return next(row for row in self.save['craftingState']['craftingSkillState']['craftTypes'] if row['type'] == craft)

    def recipe_state(self, code):
        return next(row for row in self.save['craftingState']['craftingSkillState']['recipeStates'] if row['m_type'] == code)

    def test_exact_reviewed_extension_and_original_ladder(self):
        self.assertEqual(crafting.HIGHER_SKILL_RECIPES, EXPECTED_HIGHER)
        self.assertEqual(sum(len(crafting.RECIPES_BY_CRAFT[c]) for c in crafting.HOME_COTTAGES), 111)
        self.assertEqual([len(crafting.RECIPES_BY_CRAFT[c]) for c in crafting.HOME_COTTAGES], [32, 31, 31, 17])
        self.assertEqual([row.attrib for row in crafting._catalog()[0].find('craftTypeLevels')], [
            {'num': '1', 'xp': '0', 'gold': '0', 'cash': '0', 'recipeSlots': '2'},
            {'num': '2', 'xp': '6', 'gold': '50000', 'cash': '15', 'recipeSlots': '3'},
            {'num': '3', 'xp': '18', 'gold': '100000', 'cash': '25', 'recipeSlots': '4'},
            {'num': '4', 'xp': '27', 'gold': '400000', 'cash': '40', 'recipeSlots': '5'},
            {'num': '5', 'xp': '36', 'gold': '1000000', 'cash': '60', 'recipeSlots': '6'},
        ])
        for craft, codes in EXPECTED_HIGHER.items():
            for code in codes:
                recipe = crafting._recipe(code)
                self.assertEqual(recipe.findtext('craft'), craft)
                self.assertEqual(recipe.findtext('InitialRecipeLevel'), {'2': '3', '3': '6', '4': '9', '5': '12'}[recipe.findtext('SkillLevelRequired')])
                self.assertEqual((recipe.findtext('RushCostCash'), recipe.findtext('RushCostCoins')), ('5', '-1'))
                self.assertIsNone(recipe.find('limitedStart'))
                self.assertIsNone(recipe.find('prereqs'))

    def test_coin_upgrade_spends_each_authored_price_and_experience_once(self):
        for craft in crafting.HOME_COTTAGES:
            with self.subTest(craft=craft):
                self.prepare(craft)
                self.skill(craft).update(xp=200, exp=200, imported={'keep': [1]})
                expected_xp, expected_gold = 200, 6_000_000
                for level, required, price, ovens in ((2, 6, 50_000, 3), (3, 18, 100_000, 4), (4, 27, 400_000, 5), (5, 36, 1_000_000, 6)):
                    self.assertEqual(self.call('CraftingService.onBuyCraftUpgrade', [craft, False]), {'rewardLink': None})
                    expected_xp -= required; expected_gold -= price
                    skill = self.skill(craft)
                    self.assertEqual((skill['level'], skill['xp'], skill['exp']), (level, expected_xp, expected_xp))
                    self.assertEqual(skill['imported'], {'keep': [1]})
                    self.assertEqual(crafting._oven_capacity(skill), ovens)
                    self.assertEqual(self.save['userInfo']['player']['gold'], expected_gold)
                    self.assertEqual(self.save['world']['objectsArray'][0]['craftLevel'], level)
                    for code in crafting.RECIPES_BY_CRAFT[craft]:
                        recipe = crafting._recipe(code)
                        self.assertEqual(self.recipe_state(code)['m_isUnlocked'], int(recipe.findtext('SkillLevelRequired')) <= level)
                self.assert_rejected_without_mutation('CraftingService.onBuyCraftUpgrade', [craft, True])

    def test_cash_bypass_spends_original_prices_and_clamps_experience(self):
        self.prepare()
        self.skill().update(exp=0, xp=0)
        for level, price in ((2, 15), (3, 25), (4, 40), (5, 60)):
            old_cash = self.save['userInfo']['player']['cash']
            self.call('CraftingService.onBuyCraftUpgrade', ['bakery', True])
            self.assertEqual(self.skill()['level'], level)
            self.assertEqual((self.skill()['exp'], self.skill()['xp']), (0, 0))
            self.assertEqual(self.save['userInfo']['player']['cash'], old_cash - price)
        self.assertEqual(self.save['userInfo']['player']['gold'], 6_000_000)

    def test_coin_xp_threshold_and_cash_funds_cannot_be_forged(self):
        self.prepare()
        self.skill().update(exp=5, xp=5)
        self.assert_rejected_without_mutation('CraftingService.onBuyCraftUpgrade', ['bakery', False])
        self.skill().update(exp=6, xp=6)
        self.save['userInfo']['player']['gold'] = 49_999
        self.assert_rejected_without_mutation('CraftingService.onBuyCraftUpgrade', ['bakery', False])
        self.save['userInfo']['player']['cash'] = 14
        self.assert_rejected_without_mutation('CraftingService.onBuyCraftUpgrade', ['bakery', True])
        for flag in (0, 1, 'false', None, [], {}):
            self.assert_rejected_without_mutation('CraftingService.onBuyCraftUpgrade', ['bakery', flag])
        self.save['userInfo']['player']['gold'] = 50_000
        self.call('CraftingService.onBuyCraftUpgrade', ['bakery', False])
        self.assertEqual((self.skill()['level'], self.skill()['exp'], self.save['userInfo']['player']['gold']), (2, 0, 0))

    def test_upgrade_needs_one_completed_owned_home_cottage(self):
        self.prepare()
        for craft in ('craftshop', 'winery', None, []):
            self.assert_rejected_without_mutation('CraftingService.onBuyCraftUpgrade', [craft, True])
        self.save['userInfo']['currentWorldType'] = 'england'
        self.assert_rejected_without_mutation('CraftingService.onBuyCraftUpgrade', ['bakery', True])
        self.save['userInfo']['currentWorldType'] = 'farm'
        self.save['world']['objectsArray'][0]['isFullyBuilt'] = False
        self.assert_rejected_without_mutation('CraftingService.onBuyCraftUpgrade', ['bakery', True])
        self.save['world']['objectsArray'][0]['isFullyBuilt'] = True
        duplicate = copy.deepcopy(self.save['world']['objectsArray'][0]); duplicate['id'] = 601
        self.save['world']['objectsArray'].append(duplicate)
        self.assert_rejected_without_mutation('CraftingService.onBuyCraftUpgrade', ['bakery', True])

    def test_higher_recipes_stay_locked_until_required_skill_and_keep_original_initial_levels(self):
        self.prepare()
        for code in EXPECTED_HIGHER['bakery']:
            self.assertFalse(self.recipe_state(code)['m_isUnlocked'])
            ingredient = next(iter(crafting._ingredients(crafting._recipe(code))))
            self.assert_rejected_without_mutation('FarmService.onPurchaseBushel', [ingredient, code, 1])
            self.assert_rejected_without_mutation('CraftingService.onBeginRecipe', [code, -1])
        self.call('CraftingService.onBuyCraftUpgrade', ['bakery', True])
        self.assertEqual(self.recipe_state('b3'), {'m_type': 'b3', 'm_level': 3, 'm_experience': 0, 'm_isUnlocked': True})
        self.assertFalse(self.recipe_state('b8')['m_isUnlocked'])
        self.assertFalse(self.recipe_state('c0')['m_isUnlocked'])
        self.recipe_state('b3').update(m_level=8, m_experience=7, imported={'preserve': True})
        before = copy.deepcopy(self.recipe_state('b3'))
        self.call('CraftingService.onBuyCraftUpgrade', ['bakery', True])
        self.assertEqual(self.recipe_state('b3'), before)
        self.assertEqual(self.recipe_state('b8')['m_level'], 6)
        self.assertTrue(self.recipe_state('b8')['m_isUnlocked'])
        self.assertFalse(self.recipe_state('c0')['m_isUnlocked'])

    def test_all_58_new_recipes_begin_rush_claim_and_use_the_original_product(self):
        for craft, codes in EXPECTED_HIGHER.items():
            for code in sorted(codes):
                with self.subTest(craft=craft, code=code):
                    self.prepare(craft)
                    self.skill(craft)['level'] = 5
                    crafting.initialize(self.save)
                    self.purchase(code)
                    recipe = crafting._recipe(code)
                    initial = int(recipe.findtext('InitialRecipeLevel'))
                    record = self.call('CraftingService.onBeginRecipe', [code, 0], now=1000)
                    self.assertEqual(record['recipeInitialRecipeLevel'], initial)
                    self.assertEqual(record['recipeLevel'], initial)
                    before_goods = copy.deepcopy(self.save['userInfo']['player']['storageData'])
                    cash = self.save['userInfo']['player']['cash']
                    self.assertEqual(self.call('CraftingService.onRushRecipe', [code, 1000, False, 0], now=1001), {})
                    self.assertEqual(self.save['userInfo']['player']['cash'], cash - 5)
                    self.assertEqual(self.save['userInfo']['player']['storageData'], before_goods)
                    self.assertEqual(self.save['craftingState']['recipeQueue'][craft][0]['finish_ts'], 700)
                    result = self.call('CraftingService.onClaimFinishedRecipes', [code, 0], now=1001)
                    self.assertEqual(result[0]['recipeLevel'], initial)
                    self.assertEqual(result[0]['quantity'], int(recipe.find('Reward/OnFinish').get('sellQty')))
                    self.assertEqual(self.save['userInfo']['player']['storageData']['-7'][f'{code}:{initial}'][0], 1)
                    energy = self.save['userInfo']['player']['energy']
                    self.call('CraftingService.onUseCraftedGood', [f'{code}:{initial}'], now=1002)
                    fuel = next(int(row.get('fuel')) for row in crafting._catalog()[0].find('recipeLevels') if row.get('num') == str(initial))
                    self.assertEqual(self.save['userInfo']['player']['energy'], energy + fuel)

    def test_rush_targets_exact_saved_recipe_timestamp_and_oven_without_other_queue_changes(self):
        self.prepare(); self.purchase(count=2)
        first = self.call('CraftingService.onBeginRecipe', ['b0', 0], now=1000)
        other = self.call('CraftingService.onBeginRecipe', ['b0', 1], now=1001)
        for params in (['b0', 999, False, 0], ['b0', 1000, False, 1], ['b0', 1000, True, 0],
                       ['b0', 1000, 0, 0], ['b0', 1000.5, False, 0], ['b0', 1000, False, 0.5]):
            self.assert_rejected_without_mutation('CraftingService.onRushRecipe', params, now=1002)
        self.call('CraftingService.onRushRecipe', ['b0', 1000, False, 0], now=1002, sequence=100)
        queue = self.save['craftingState']['recipeQueue']['bakery']
        self.assertEqual(queue[1], other)
        self.assertEqual(queue[0], dict(first, finish_ts=700))
        before = copy.deepcopy(self.save)
        self.call('CraftingService.onRushRecipe', ['b0', 1000, False, 0], now=2000, sequence=100)
        self.assertEqual(self.save, before)
        self.assert_rejected_without_mutation('CraftingService.onRushRecipe', ['b0', 1000, False, 0], now=1002)
        result = self.call('CraftingService.onClaimFinishedRecipes', ['b0', 0], now=1002)
        self.assertEqual(len(result), 1)
        self.assertEqual(self.save['craftingState']['recipeQueue']['bakery'], [other])

    def test_rush_insufficient_funds_ready_or_missing_queue_rejects_without_effect(self):
        self.prepare(); self.purchase(); record = self.call('CraftingService.onBeginRecipe', ['b0', 0], now=1000)
        self.save['userInfo']['player']['cash'] = 4
        self.assert_rejected_without_mutation('CraftingService.onRushRecipe', ['b0', 1000, False, 0], now=1001)
        self.save['userInfo']['player']['cash'] = 100
        self.assert_rejected_without_mutation('CraftingService.onRushRecipe', ['b0', 1000, False, 0], now=record['finish_ts'])
        self.assert_rejected_without_mutation('CraftingService.onRushRecipeWithTime', ['b0', 1000, False, 0], now=1001)
        self.save['craftingState']['recipeQueue']['bakery'] = []
        self.assert_rejected_without_mutation('CraftingService.onRushRecipe', ['b0', 1000, False, 0], now=1001)

    def test_upgrade_retry_persists_and_different_sequence_cannot_refund_or_repeat_level(self):
        self.prepare()
        first = self.call('CraftingService.onBuyCraftUpgrade', ['bakery', True], sequence=100)
        with redirect_stdout(io.StringIO()):
            self.player.save_session('fixture-farmer'); self.player.load_saves()
        self.save = self.player.session('fixture-farmer')
        before = copy.deepcopy(self.save)
        self.assertEqual(self.call('CraftingService.onBuyCraftUpgrade', ['bakery', True], sequence=100), first)
        self.assertEqual(self.save, before)
        self.assert_rejected_without_mutation('CraftingService.onBuyCraftUpgrade', ['bakery', False], sequence=100)
        crafting.start_session(self.save)
        self.assertEqual(self.skill()['level'], 2)
        self.assertEqual(self.save['world']['objectsArray'][0]['craftLevel'], 2)
        self.assertEqual(self.recipe_state('b3')['m_level'], 3)
        self.call('CraftingService.onBuyCraftUpgrade', ['bakery', True], sequence=100)
        self.assertEqual(self.skill()['level'], 3)

    def test_evicted_paid_upgrade_cannot_purchase_next_level_even_for_legacy_receipts(self):
        self.prepare()
        self.call('CraftingService.onBuyCraftUpgrade', ['bakery', True], sequence=1)
        for sequence in range(2, 258):
            self.call('CraftingService.onMarkCottageHistorySeen', ['bakery'], sequence=sequence)
        state = self.save['craftingState']
        self.assertEqual(len(state['localCraftingRequests']), 256)
        self.assertNotIn('1', state['localCraftingRequests'])
        self.assertEqual(state['localCraftingHighestSequence'], 257)
        self.assert_rejected_without_mutation('CraftingService.onBuyCraftUpgrade', ['bakery', True], sequence=1)
        state.pop('localCraftingHighestSequence')
        self.assert_rejected_without_mutation('CraftingService.onBuyCraftUpgrade', ['bakery', True], sequence=1)
        self.assertEqual(self.skill()['level'], 2)
        crafting.start_session(self.save)
        self.assertNotIn('localCraftingHighestSequence', self.save['craftingState'])
        self.call('CraftingService.onBuyCraftUpgrade', ['bakery', True], sequence=1)
        self.assertEqual(self.skill()['level'], 3)


if __name__ == '__main__':
    unittest.main()
