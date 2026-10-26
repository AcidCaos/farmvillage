"""Recover the real earned feather quest after a lost reward-close callback."""
from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import avatar
import quests

QUEST = 'feather-01-005'
OUTFIT = '9239'


class QuestCompletionRecoveryTests(unittest.TestCase):
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

    def prepare(self, progress=None):
        self.path = self.write_fixture()
        self.definition = quests.get_quest_by_name(QUEST)
        self.assertIsNotNone(self.definition)
        self.assertEqual([task['total'] for task in self.definition['tasks']], [7, 2, 700])
        self.save['userInfo']['currentWorldType'] = 'farm'
        self.save['userInfo']['player'].update(gold=1234, cash=50, xp=100015, storageData={})
        self.save['world']['objectsArray'] = []
        self.save['avatarState']['unlocked'] = [code for code in self.save['avatarState']['unlocked'] if code != OUTFIT]
        self.save['avatarState']['importedWardrobe'] = {'retain': [1, 2]}
        self.save['questState'].update(active={QUEST: {
            'progress': list(progress) if progress is not None else [7, 2, 700],
            'new': quests.NON_NEW_QUEST}}, completed=['feather-01-004'], retired=[], replayed={})
        self.sequence = 0
        self.persist()

    def persist(self):
        with redirect_stdout(io.StringIO()):
            self.player.save_session('fixture-farmer')

    def accounting(self):
        player = self.save['userInfo']['player']
        return (player['gold'], player['cash'], player['xp'], copy.deepcopy(self.save['avatarState']))

    @staticmethod
    def target(records):
        return next((entry for entry in records if entry['name'] == QUEST), None)

    def send(self, method, params=()):
        self.sequence += 1
        result = self.gateway([self.command(method, params, self.sequence)])
        return fixtures.gateway_results(self, result, [0])[0]

    def test_actual_archived_reward_is_the_unpurchasable_snowboarding_outfit_and_original_amounts(self):
        self.prepare()
        self.assertEqual([(r['type'], r['value']) for r in self.definition['rewards']],
                         [('xp', '100'), ('avatar_item', OUTFIT), ('coins', '2500')])
        outfit = avatar.get_item_by_id(OUTFIT)
        self.assertEqual(outfit['name'], 'UnisexFeatherQuestSnowboardingOutfit')
        self.assertFalse(outfit['buyable'])

    def test_component_announces_once_then_omits_pending_normal_quest_without_granting(self):
        self.prepare()
        before = self.accounting()
        first = self.target(quests.quest_component(self.save))
        self.assertIs(first['complete'], True)
        self.assertEqual(first['progress'], [7, 2, 700])
        self.assertIsNone(self.target(quests.quest_component(self.save)))
        self.assertEqual(self.accounting(), before)
        self.assertIn(QUEST, self.save['questState']['active'])
        self.assertNotIn(QUEST, self.save['questState']['completed'])
        self.assertTrue(self.save['questState']['active'][QUEST]['announced'])

    def test_new_session_reoffers_earned_quest_without_awarding_or_fabricating_progress(self):
        self.prepare()
        original_progress = copy.deepcopy(self.save['questState']['active'][QUEST]['progress'])
        before = self.accounting()
        self.assertTrue(self.target(quests.quest_component(self.save))['complete'])
        self.assertIsNone(self.target(quests.quest_component(self.save)))
        quests.start_session(self.save)
        self.assertTrue(self.target(quests.quest_component(self.save))['complete'])
        self.assertEqual(self.save['questState']['active'][QUEST]['progress'], original_progress)
        self.assertEqual(self.accounting(), before)

    def test_partial_invalid_and_nonfinite_saved_counts_are_not_announced_complete(self):
        self.prepare()
        cases = ([7, 2, 699], [7, 2], [7, 2, 700, 1], [True, 2, 700],
                 [7, False, 700], ['7', 2, 700], [7, None, 700],
                 [7, 2, float('nan')], [7, 2, float('inf')], [7, 2, float('-inf')])
        for progress in cases:
            with self.subTest(progress=progress):
                state = {'progress': list(progress), 'new': quests.NON_NEW_QUEST}
                self.assertIs(quests._announce_completed_quest(self.definition, state), False)
                self.assertNotIn('announced', state)
        for progress in ([7.0, 2.0, 700.0], [8, 3, 701]):
            with self.subTest(valid_progress=progress):
                state = {'progress': list(progress), 'new': quests.NON_NEW_QUEST}
                self.assertIs(quests._announce_completed_quest(self.definition, state), True)
                self.assertIs(quests._announce_completed_quest(self.definition, state), None)

    def test_existing_zero_reward_view_dialog_keeps_its_original_first_true_then_false_contract(self):
        self.prepare()
        definition = next(q for q in quests._cached_quests.values()
                          if quests._is_view_dialog_quest(q) and quests._quest_matches_world(self.save, q))
        state = {'progress': [0], 'new': quests.NON_NEW_QUEST}
        self.assertIs(quests._announce_completed_quest(definition, state), True)
        self.assertIs(quests._announce_completed_quest(definition, state), False)

    def test_signed_init_announces_once_siblings_and_refresh_omit_until_ack(self):
        self.prepare()
        before = self.accounting()
        initialized = self.send('UserService.initUser', ['QA', 0, True, None])
        first = self.target(initialized['metadata']['QuestComponent'])
        self.assertIs(first['complete'], True)
        self.assertEqual(first['progress'], [7, 2, 700])
        sibling = self.send('UserService.setSeenFlag', ['questRecoverySibling'])
        self.assertIsNone(self.target(sibling['metadata']['QuestComponent']))
        refreshed = self.send('FarmQuestService.fullQuestRefresh')
        self.assertIsNone(self.target(refreshed['metadata']['QuestComponent']))
        self.assertEqual(self.accounting(), before)
        self.assertIn(QUEST, json.loads(self.path.read_text())['questState']['active'])

    def test_signed_reload_after_lost_ack_reoffers_then_ack_unlocks_avatar_and_pays_exactly_once(self):
        self.prepare()
        before = self.accounting()
        first = self.send('UserService.initUser', ['QA', 0, True, None])
        self.assertTrue(self.target(first['metadata']['QuestComponent'])['complete'])
        self.assertNotIn(OUTFIT, self.save['avatarState']['unlocked'])
        self.assertEqual(self.accounting(), before)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        second = self.send('UserService.initUser', ['QA', 0, True, None])
        self.assertTrue(self.target(second['metadata']['QuestComponent'])['complete'])
        self.assertEqual(self.accounting(), before)
        acknowledged = self.send('FarmQuestService.updateRecentlyCompletedQuests', [QUEST, False])
        self.assertEqual(acknowledged['data'], {'friendReward': None})
        self.assertNotIn(QUEST, self.save['questState']['active'])
        self.assertEqual(self.save['questState']['completed'].count(QUEST), 1)
        self.assertEqual(self.save['userInfo']['player']['gold'], 1234 + 2500)
        self.assertEqual(self.save['userInfo']['player']['xp'], 100015 + 100)
        self.assertEqual(self.save['userInfo']['player']['cash'], 50)
        self.assertEqual(self.save['avatarState']['unlocked'].count(OUTFIT), 1)
        self.assertEqual(self.save['avatarState']['importedWardrobe'], {'retain': [1, 2]})
        paid = self.accounting()
        self.send('FarmQuestService.updateRecentlyCompletedQuests', [QUEST, False])
        self.assertEqual(self.accounting(), paid)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.send('FarmQuestService.updateRecentlyCompletedQuests', [QUEST, True])
        self.assertEqual(self.accounting(), paid)
        final_init = self.send('UserService.initUser', ['QA', 0, True, None])
        self.assertIsNone(self.target(final_init['metadata']['QuestComponent']))
        self.assertEqual(self.accounting(), paid)
        disk = json.loads(self.path.read_text())
        self.assertEqual(disk['avatarState']['unlocked'].count(OUTFIT), 1)
        self.assertEqual(disk['userInfo']['player']['gold'], 3734)

    def test_signed_incomplete_quest_is_present_and_incomplete_after_login_and_refresh(self):
        self.prepare(progress=[7, 2, 699])
        before = self.accounting()
        for method, params in (('UserService.initUser', ['QA', 0, True, None]),
                               ('FarmQuestService.fullQuestRefresh', [])):
            result = self.send(method, params)
            entry = self.target(result['metadata']['QuestComponent'])
            self.assertIs(entry['complete'], False)
            self.assertEqual(entry['progress'], [7, 2, 699])
        self.assertEqual(self.accounting(), before)
        self.assertNotIn('announced', self.save['questState']['active'][QUEST])


if __name__ == '__main__':
    unittest.main()
