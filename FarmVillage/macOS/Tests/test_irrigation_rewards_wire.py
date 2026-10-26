"""Recovered well and authored water rewards through the actual AMF gateway.

The copied original SWF's WaterHarvestFManager rejects a whole well reward above
2,000 water. UserRewardUtil's irrigation branch calls uncapped addWater instead.
All saves and runtime caches belong to the temporary test_persistence harness.
"""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import quests


class IrrigationRewardWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    NOW = 2_000_000
    # Exact recovered growTime * the original 82,800-second farming day.
    WELLS = (
        ('bldg_irrigationwell', 57_132, {2: 50, 7: 310}),
        ('bldg_irrigationwell_8hr', 27_655.2, {2: 25, 7: 155}),
    )

    def water(self, save=None):
        save = save or self.player.session('fixture-farmer')
        return save['userInfo']['featureOptions']['irrigation']['irrigation']['waterPlots']['farm']['amount']

    def well(self, name='bldg_irrigationwell', *, ident=71, level=2, age=70_000):
        return {'id': ident, 'className': 'FeatureBuilding', 'itemName': name,
                'state': 'bare', 'plantTime': (self.NOW - age) * 1000,
                'expansionLevel': level, 'importedExtra': {'keep': True},
                'position': {'x': ident * 4, 'y': 0, 'z': 0}}

    def prepare(self, *wells, water=20):
        self.path = self.write_fixture()
        save = self.player.session('fixture-farmer')
        save['userInfo']['featureOptions']['irrigation'] = {'irrigation': {
            'waterPlots': {'farm': {'amount': water, 'importedExtra': 'keep'},
                           'england': {'amount': 17}}}}
        save['world']['objectsArray'] = list(wells) or [self.well()]
        self.player.save_session('fixture-farmer')
        return save

    def harvest(self, snapshot, sequence=1):
        return self.command('WorldService.performAction', ['harvest', snapshot, []], sequence)

    def send(self, requests, errors):
        with mock.patch('commands.timestamp_now', return_value=self.NOW):
            return fixtures.gateway_results(self, self.gateway(requests), errors)

    def test_both_original_wells_pay_owned_level_reward_and_restart_the_clock(self):
        for name, _grow, rewards in self.WELLS:
            for level, award in rewards.items():
                with self.subTest(name=name, level=level):
                    owned = self.well(name, level=level)
                    save = self.prepare(owned)
                    snapshot = copy.deepcopy(owned)
                    snapshot.update(state='grown', plantTime=0, expansionLevel=7)
                    self.send([self.harvest(snapshot)], [0])
                    saved = json.loads(self.path.read_text())
                    self.assertEqual(self.water(saved), 20 + award)
                    self.assertEqual(saved['userInfo']['featureOptions']['irrigation']['irrigation']['waterPlots']['england'],
                                     {'amount': 17})
                    stored = saved['world']['objectsArray'][0]
                    self.assertEqual(stored['expansionLevel'], level)
                    self.assertEqual(stored['plantTime'], self.NOW * 1000)
                    self.assertEqual(stored['state'], 'bare')
                    self.assertEqual(stored['importedExtra'], {'keep': True})
                    self.assertEqual(self.water(save), 20 + award)

    def test_forged_ready_snapshot_cannot_bypass_either_original_cooldown(self):
        for name, grow, _rewards in self.WELLS:
            with self.subTest(name=name):
                owned = self.well(name, age=grow - 10)
                self.prepare(owned)
                before = self.path.read_bytes()
                snapshot = copy.deepcopy(owned)
                snapshot.update(state='grown', plantTime=0, expansionLevel=7)
                self.send([self.harvest(snapshot)], [29])
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(self.water(), 20)

    def test_move_snapshot_cannot_change_imported_owned_level_or_harvest_timer(self):
        owned = self.well(level=3, age=10)
        self.prepare(owned)
        snapshot = copy.deepcopy(owned)
        snapshot.update(expansionLevel=7, plantTime=0)
        snapshot['position']['x'] += 4
        self.send([self.command('WorldService.performAction', ['move', snapshot, []])], [0])
        stored = self.player.session('fixture-farmer')['world']['objectsArray'][0]
        self.assertEqual((stored['expansionLevel'], stored['plantTime']),
                         (owned['expansionLevel'], owned['plantTime']))
        self.assertEqual(stored['position'], snapshot['position'])
        self.assertEqual(stored['importedExtra'], {'keep': True})
        self.send([self.harvest(snapshot, 2)], [29])
        self.assertEqual(self.water(), 20)

    def test_original_cooldown_maturity_uses_authored_grow_time(self):
        for name, grow, rewards in self.WELLS:
            with self.subTest(name=name):
                self.prepare(self.well(name, age=grow + 1))
                self.send([self.harvest({'id': 71})], [0])
                self.assertEqual(self.water(), 20 + rewards[2])

    def test_same_sequence_retry_has_no_second_grant_and_new_early_request_is_refused(self):
        snapshot = self.well()
        self.prepare(snapshot)
        self.send([self.harvest(snapshot, 41)], [0])
        saved = self.path.read_bytes()
        self.send([self.harvest(snapshot, 41)], [0])
        self.assertEqual(self.path.read_bytes(), saved)
        self.send([self.harvest(snapshot, 42)], [29])
        self.assertEqual(self.path.read_bytes(), saved)
        self.assertEqual(self.water(), 70)

    def test_full_reward_above_cap_is_refused_without_timer_or_balance_changes(self):
        owned = self.well(level=7)
        self.prepare(owned, water=1691)
        before = self.path.read_bytes()
        self.send([self.harvest(owned)], [29])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.player.session('fixture-farmer')['world']['objectsArray'][0], owned)
        self.assertEqual(self.water(), 1691)

    def test_mixed_batch_keeps_exact_cap_harvest_and_accepted_sibling_after_refusal(self):
        first, second = self.well(ident=71), self.well(ident=72)
        self.prepare(first, second, water=1950)
        self.send([self.harvest(first, 10), self.harvest(second, 11),
                   self.command('UserService.incrementActionCount', ['water-sibling'], 12)], [0, 29, 0])
        saved = json.loads(self.path.read_text())
        self.assertEqual(self.water(saved), 2000)
        self.assertEqual(saved['world']['objectsArray'][0]['plantTime'], self.NOW * 1000)
        self.assertEqual(saved['world']['objectsArray'][1], second)
        self.assertEqual(saved['userInfo']['player']['actionCounts']['water-sibling'], 1)
        self.assertEqual(self.player.session('fixture-farmer'), saved)

    def test_water_reward_and_server_timer_survive_reload_and_init(self):
        self.prepare(self.well('bldg_irrigationwell_8hr', level=7))
        self.send([self.harvest({'id': 71})], [0])
        self.player.load_saves()
        init = self.send([self.command('UserService.initUser', ['QA', 0, True, {}], 2)], [0])[0]['data']
        self.assertEqual(self.water(init), 175)
        well = next(obj for obj in init['world']['objectsArray'] if obj['id'] == 71)
        self.assertEqual((well['expansionLevel'], well['plantTime'], well['state']),
                         (7, self.NOW * 1000, 'bare'))
        self.assertEqual(self.water(json.loads(self.path.read_text())), 175)

    def test_decoded_authored_quest_reward_grants_value_uncapped_once(self):
        raw = b'''<questSettings><quest name="water-reward"><tasks>
            <task action="plowPlot" total="1"/>
            </tasks><rewards><reward type="irrigation" actionType="waterPlots" value="50" quantity="9"/>
            </rewards></quest></questSettings>'''
        decoded = quests._decode_quests(zlib.compress(raw))
        definition = decoded['quests']['water-reward']
        self.assertEqual(definition['rewards'][0]['actionType'], 'waterPlots')
        save = self.prepare(water=1980)
        save['questState'] = {'active': {'water-reward': {'progress': [1], 'new': 0}},
                              'completed': [], 'retired': [], 'replayed': {}}
        self.player.save_session('fixture-farmer')
        with mock.patch.object(quests, '_cached_quests', {'water-reward': definition}), \
                mock.patch.object(quests, '_startable_quests', []), \
                mock.patch.object(quests, '_replayable_chains', {}):
            call = self.command('FarmQuestService.updateRecentlyCompletedQuests', ['water-reward', False])
            self.send([call], [0])
            self.assertEqual(self.water(), 2030)
            saved = self.path.read_bytes()
            self.send([call], [0])
            self.assertEqual(self.path.read_bytes(), saved)
        self.player.load_saves()
        self.assertEqual(self.water(), 2030)
        self.assertIn('water-reward', self.player.session('fixture-farmer')['questState']['completed'])


if __name__ == '__main__':
    unittest.main()
