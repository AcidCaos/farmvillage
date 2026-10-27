"""Authored cottage mastery transitions over signed AMF, on synthetic saves.

Recipe skill immediately below each threshold is explicitly seeded precondition;
no cooking clock is changed and no seeded level is counted as earned gameplay.
"""
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
import crafting
import items
import progression


class CraftingMasteryWireTests(unittest.TestCase):
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

    def prepare(self, *, level=19, xp=7, craft="bakery", code="b0"):
        self.path = self.write_fixture()
        self.save['userInfo']['currentWorldType'] = 'farm'
        self.save['userInfo']['player'].update(xp=100015, gold=2_000_000, cash=200,
                                                energy=5, storageData={})
        self.save['world']['objectsArray'] = [{
            'id': 600, 'itemName': crafting.COTTAGES[craft], 'className': 'CraftingCottageBuilding',
            'state': 'built', 'isFullyBuilt': True, 'craftLevel': 1,
            'position': {'x': 10, 'y': 10, 'z': 0}, 'imported': {'keep': [1, 2]},
        }]
        self.save['craftingState'] = {'craftingItems': [],
            'craftingSkillState': {'recipeStates': [], 'craftTypes': []}}
        crafting.start_session(self.save)
        next(r for r in self.save['craftingState']['craftingSkillState']['recipeStates']
             if r['m_type'] == code).update(m_level=level, m_experience=xp, imported={'keep': True})
        self.save['craftingState']['craftingItems'] = [
            {'itemCode': code, 'quantity': amount, 'imported': [code]}
            for code, amount in crafting._ingredients(crafting._recipe(code)).items()]
        self.sequence = 0
        self.persist()

    def persist(self):
        with redirect_stdout(io.StringIO()):
            self.player.save_session('fixture-farmer')

    def send(self, method='CraftingService.onBeginRecipe', params=('b0', 0), *, sequence=None, reject=False, now=1000):
        self.sequence += 1
        if sequence is not None:
            self.sequence = max(self.sequence, sequence)
        command = self.command(method, list(params), self.sequence if sequence is None else sequence)
        with mock.patch.object(crafting, 'timestamp_now', return_value=now):
            response = self.gateway([command])
        return fixtures.gateway_results(self, response, [29 if reject else 0])[0]

    def test_each_authored_star_awards_exact_balance_goal_and_one_sign(self):
        for threshold, stars, row in crafting._mastery_levels(crafting._recipe('b0')):
            with self.subTest(stars=stars):
                previous = threshold - 1
                needed = next(int(r.get('xp')) for r in crafting._catalog()[0].find('recipeLevels')
                              if r.get('num') == str(previous))
                self.prepare(level=previous, xp=needed - 1)
                old = copy.deepcopy(self.save['userInfo']['player'])
                response = self.send()
                self.assertEqual(response['goals'], [{'type': 'RecipeMastery', 'code': 'b0',
                                                      'difficulty': stars, 'link': ''}])
                self.assertEqual(self.save['userInfo']['player']['gold'], old['gold'] + int(row.get('coins')))
                self.assertEqual(self.save['userInfo']['player']['xp'], old['xp'] + 50 + int(row.get('xp')))
                self.assertEqual(self.save['userInfo']['player']['storageData']['-1']['11'], [1, [], []])
                # Authored 360-minute b0 clock is retained, including on mastery.
                self.assertEqual(response['data']['finish_ts'] - response['data']['start_ts'], 21600)
                self.assertEqual(json.loads(self.path.read_text())['craftingState']['recipeQueue']['bakery'][0]['finish_ts'], 22600)

    def test_each_home_cottage_routes_its_own_authored_mastery_sign(self):
        for craft, code in (('bakery', 'b0'), ('winery', 'w0'), ('perfumery', 'p0'), ('pub', 'lq')):
            with self.subTest(craft=craft):
                recipe = crafting._recipe(code)
                threshold, stars, row = crafting._mastery_levels(recipe)[0]
                level = threshold - 1
                needed = next(int(r.get('xp')) for r in crafting._catalog()[0].find('recipeLevels')
                              if r.get('num') == str(level))
                self.prepare(level=level, xp=needed - 1, craft=craft, code=code)
                response = self.send(params=(code, 0))
                self.assertEqual(response['goals'], [{'type': 'RecipeMastery', 'code': code,
                                                     'difficulty': stars, 'link': ''}])
                self.assertEqual(self.save['userInfo']['player']['storageData']['-1'],
                                 {recipe.find('Mastery').get('sign'): [1, [], []]})
                self.assertEqual(response['data']['finish_ts'] - response['data']['start_ts'],
                                 int(recipe.findtext('MinutesToCook')) * 60)

    def test_earned_gift_placement_and_move_ignore_forged_star_count(self):
        self.prepare()
        self.send()
        snapshot = {'id': 64000, 'tempId': -1, 'itemName': 'marketpumpkinbread',
                    'className': 'RecipeMasterySign', 'state': 'static', 'level': 5,
                    'position': {'x': 8, 'y': 8, 'z': 0}}
        response = self.send('WorldService.performAction', ('place', snapshot, [{'isGift': True}]))
        ident = response['data']['id']
        sign = next(r for r in self.save['world']['objectsArray'] if r['id'] == ident)
        self.assertEqual(sign['level'], 1)
        self.assertNotIn('11', self.save['userInfo']['player']['storageData']['-1'])
        forged = {**sign, 'level': 5, 'position': {'x': 9, 'y': 8, 'z': 0}}
        self.send('WorldService.performAction', ('move', forged, []))
        self.assertEqual(next(r for r in self.save['world']['objectsArray'] if r['id'] == ident)['level'], 1)
        persisted = json.loads(self.path.read_text())
        self.assertEqual(next(r for r in persisted['world']['objectsArray'] if r['id'] == ident)['level'], 1)

    def test_authored_single_five_star_tier_has_no_invented_lower_stars(self):
        self.prepare()
        recipe = crafting._recipe('v7')
        self.assertEqual([(required, stars) for required, stars, _ in crafting._mastery_levels(recipe)], [(20, 5)])
        before = copy.deepcopy(self.save['userInfo']['player'])
        with redirect_stdout(io.StringIO()):
            crafting._award_recipe_mastery(self.save, recipe, 19, 20)
        self.assertEqual(progression.take_response(self.save)['goals'], [{
            'type': 'RecipeMastery', 'code': 'v7', 'difficulty': 5, 'link': ''}])
        self.assertEqual(self.save['userInfo']['player']['gold'], before['gold'] + 2500)
        self.assertEqual(self.save['userInfo']['player']['xp'], before['xp'] + 1000)
        self.assertIsNone(crafting._recipe('@y').find('Mastery'))
        crafting._award_recipe_mastery(self.save, crafting._recipe('@y'), 19, 20)
        self.assertEqual(progression.take_response(self.save), {})

    def test_retry_reload_and_next_make_do_not_reaward_or_repeat_popup(self):
        self.prepare()
        first = self.send(sequence=40)
        accepted = copy.deepcopy(self.save)
        disk = self.path.read_bytes()
        retry = self.send(sequence=40)
        self.assertNotIn('goals', retry)
        self.assertEqual(retry['data'], first['data'])
        self.assertEqual(self.save, accepted)
        self.assertEqual(self.path.read_bytes(), disk)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        retry = self.send(sequence=40)
        self.assertNotIn('goals', retry)
        self.assertEqual(self.save, accepted)
        # initUser may clear request sequence receipts; the persisted recipe
        # level still prevents regranting the previous star on a later make.
        crafting.start_session(self.save)
        self.send('CraftingService.onClaimFinishedRecipes', ('b0', 0), sequence=1, now=22600)
        for code, amount in crafting._ingredients(crafting._recipe('b0')).items():
            self.send('FarmService.onPurchaseBushel', (code, 'b0', amount), now=22601)
        before = copy.deepcopy(self.save['userInfo']['player'])
        response = self.send(now=22602)
        self.assertNotIn('goals', response)
        self.assertEqual(self.save['userInfo']['player']['gold'], before['gold'])
        self.assertEqual(self.save['userInfo']['player']['xp'], before['xp'] + 50)
        self.assertEqual(self.save['userInfo']['player']['storageData'], before['storageData'])

    def test_imported_mastered_recipe_never_gets_retroactive_rewards(self):
        self.prepare(level=100, xp=0)
        before = copy.deepcopy(self.save['userInfo']['player'])
        response = self.send()
        self.assertNotIn('goals', response)
        self.assertEqual(self.save['userInfo']['player']['storageData'], {})
        self.assertEqual(self.save['userInfo']['player']['gold'], before['gold'])
        self.assertEqual(self.save['userInfo']['player']['xp'], before['xp'] + 50)

    def test_placed_and_stored_signs_upgrade_without_duplicate_gifts(self):
        for location in ('placed', '-1', '-2', '700'):
            with self.subTest(location=location):
                self.prepare(level=29, xp=10)
                if location == 'placed':
                    self.save['world']['objectsArray'].append({
                        'id': 701, 'itemName': 'marketpumpkinbread', 'className': 'RecipeMasterySign',
                        'state': 'static', 'level': 1, 'position': {'x': 8, 'y': 8, 'z': 0},
                        'imported': {'keep': True}})
                else:
                    self.save['userInfo']['player']['storageData'][location] = {'11': [1, ['sender'], [{'keep': True}]]}
                self.persist()
                before = copy.deepcopy(self.save['userInfo']['player']['storageData'])
                response = self.send()
                self.assertEqual(response['goals'][0]['difficulty'], 2)
                self.assertEqual(self.save['userInfo']['player']['storageData'], before)
                if location == 'placed':
                    sign = self.save['world']['objectsArray'][-1]
                    self.assertEqual(sign['level'], 2)
                    self.assertEqual(sign['imported'], {'keep': True})

    def test_sign_placement_and_moves_use_earned_level(self):
        self.prepare(level=30, xp=0)
        sign = {'id': 701, 'itemName': 'marketpumpkinbread', 'className': 'RecipeMasterySign',
                'state': 'static', 'level': 5, 'position': {'x': 8, 'y': 8, 'z': 0}}
        earned = crafting.initialize_mastery_sign(self.save, sign)
        self.assertEqual(earned['level'], 2)
        self.assertEqual(sign['level'], 5)
        protected = crafting.preserve_fields(earned, {**sign, 'level': 99, 'itemName': 'marketdaisyperfume'})
        self.assertEqual((protected['level'], protected['itemName']), (2, 'marketpumpkinbread'))
        self.prepare(level=19, xp=0)
        with self.assertRaisesRegex(ValueError, 'not earned'):
            crafting.initialize_mastery_sign(self.save, sign)

    def test_missing_sign_contract_rolls_back_bushels_xp_and_queue(self):
        self.prepare()
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        original = items.get_item_by_code
        with mock.patch.object(items, 'get_item_by_code', side_effect=lambda code: None if code == '11' else original(code)):
            self.send(reject=True)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)

    def test_admitted_recipes_retain_only_their_authored_mastery_tiers(self):
        for code in crafting.RECIPES:
            with self.subTest(code=code):
                recipe = crafting._recipe(code)
                tiers = crafting._mastery_levels(recipe)
                if recipe.find('Mastery') is None:
                    self.assertEqual(tiers, [])
                    continue
                stars = [stars for _, stars, _ in tiers]
                self.assertTrue(stars and set(stars) <= set(range(1, 6)))
                self.assertEqual(stars, sorted(set(stars)))
                thresholds = [required for required, _, _ in tiers]
                self.assertEqual(thresholds, sorted(set(thresholds)))
                self.assertTrue(all(int(row.get('xp')) >= 0 and int(row.get('coins')) >= 0
                                    for _, _, row in tiers))
                self.assertEqual(items.get_item_by_code(recipe.find('Mastery').get('sign'))['className'],
                                 'RecipeMasterySign')


if __name__ == '__main__':
    unittest.main()
