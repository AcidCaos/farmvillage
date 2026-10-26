"""Basic-world config gates keep every authored quest score track available."""
from collections import Counter
from contextlib import redirect_stdout
import io
import re
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
import zlib

import pyamf
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]
import test_persistence as fixtures  # Synthetic data setup before product imports.
import themed_client_presentation as policy
import themed_worlds
import themed_market_presentation as market_policy
import items
from test_turbo_client_refusal import PATCH, ABC, read_abcs
import test_cottage_invitation_stage as invitation_tests


def decode(raw):
    return pyamf.get_decoder(pyamf.AMF3, zlib.decompress(raw)).readElement()


class ThemedClientPresentationTests(unittest.TestCase):
    execute = invitation_tests.CottageInvitationStageTests.execute

    @classmethod
    def setUpClass(cls):
        cls.settings_raw = policy.SETTINGS_SOURCE.read_bytes()
        cls.score_raw = policy.SCORE_SOURCE.read_bytes()
        cls.settings = ET.fromstring(zlib.decompress(cls.settings_raw))
        cls.scores = decode(cls.score_raw)
        cls.abc = read_abcs(zlib.decompress(PATCH.patch_client_bytes(
            (ROOT/'embeds/Flash/v855097-855094/FarmGame.swf').read_bytes())[8:]))[0]
        cls.maxstack = {2649: 3, 29690: 2}

    def test_exact_fourteen_expansion_ids_removed_and_all_other_xml_preserved(self):
        before = copy.deepcopy(self.settings)
        after = ET.fromstring(zlib.decompress(policy.game_settings_payload(self.settings_raw)))
        seen = set()
        for node in before.findall('expansions/expansion'):
            world = node.get('name')
            if world in policy.WORLD_SCORE_UNITS:
                self.assertEqual(node.get('score'), policy.WORLD_SCORE_UNITS[world])
                self.assertTrue(node.get('scoreFile'))
                node.attrib.pop('score'); seen.add(world)
        self.assertEqual(seen, set(themed_worlds.SPECS))
        self.assertEqual(ET.tostring(after), ET.tostring(before))
        self.assertEqual(policy.SETTINGS_SOURCE.read_bytes(), self.settings_raw)

    def test_actual_emitted_world_assignment_and_hud_skip_when_ids_are_empty(self):
        instance = {}
        self.execute(2649, 112, 147, {0: instance, 2: {'scoreId': ''}})
        self.assertEqual(instance, {'m_currentWorldScoreId': ''})
        # Missing HUD/ScoreMeter globals make accidental construction fail.
        self.execute(29690, 28, 105, {0: {}}, {'Global': {'worldManager': {'currentWorldScoreId': ''}}})
        lines = '\n'.join(ABC.disasm(self.abc, self.abc.bodies[8937]))
        self.assertIn('68  callproperty getTasksForWorldScoreId 1', lines)
        self.assertIn('95  callproperty isEnabled 1', lines)
        self.assertIn('99  iffalse ->196', lines)
        self.assertIn('123  callproperty getTasksForWorldScoreId 1', lines)

    def test_exact42_global_tasks_removed_all_other_groups_and_unit_definitions_identical(self):
        before = copy.deepcopy(self.scores)
        original_tasks = before['worldScoreGlobal']['scores']['score']['task']
        blocked = [x for x in original_tasks if policy.blocked_global_task(x)]
        self.assertEqual(len(blocked), 42)
        self.assertEqual(Counter(x['action'] for x in blocked), {'buyItemByCategory':18,
                         'plantCropByCategory':12, 'getMasteryLevelByCategory':12})
        self.assertEqual(Counter(x['rewards']['reward']['unit'] for x in blocked),
                         {unit:17 if unit=='cheer' else 1 if unit=='pixie' else 2 for unit in policy.WORLD_SCORE_UNITS.values()})
        before['worldScoreGlobal']['scores']['score']['task'] = [x for x in original_tasks if not policy.blocked_global_task(x)]
        self.assertEqual(decode(policy.world_score_payload(self.score_raw)), before)
        self.assertEqual(len(before['worldScoreGlobal']['scores']['score']['task']), 119)
        self.assertEqual(policy.SCORE_SOURCE.read_bytes(), self.score_raw)

    def test_every_admitted_basic_item_has_no_explicit_or_nested_score_writer(self):
        items.load_items()
        by_name = {x['name']:x for x in items.get_items()}
        def writers(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if 'score' in key.lower() and child not in themed_worlds.NONE_VALUES:
                        yield (key, child)
                    if isinstance(child, str) and child in ('world_score', 'unlock_world_score'):
                        yield (key, child)
                    yield from writers(child)
            elif isinstance(value, list):
                for child in value:yield from writers(child)
        counts = {}
        for world in policy.WORLD_SCORE_UNITS:
            names = themed_worlds.catalog_rules(world)['items']; counts[world] = len(names)
            for name in names:
                original = copy.deepcopy(by_name[name])
                projected = market_policy.item_projection(by_name[name])
                self.assertEqual(list(writers(projected)), [], (world,name))
                self.assertEqual(by_name[name], original)
        self.assertTrue(all(counts.values()))

    def test_all_fourteen_beat_gates_keep_original_locations_and_variants(self):
        overrides = policy.beat_experiment_overrides()
        self.assertEqual(len(overrides), 14)
        self.assertEqual(set(overrides.values()), {0})
        self.assertEqual(set(policy.BEAT_GATES), set(themed_worlds.SPECS))
        self.assertEqual(policy.BEAT_GATES['australia'][2], 1)
        self.assertEqual(policy.BEAT_GATES['atlantis'], ('beatAtlantis', 'fv_beat_atlantis', 1))
        self.assertEqual(policy.BEAT_GATES['glen'], ('beatEnchantedGlen', 'fv_beat_enchanted_glen', 1))
        self.assertEqual(policy.BEAT_GATES['hlights'], ('beatHlights', 'fv_beat_hlights', 2))
        self.assertTrue(all(v[2] == 2 for w,v in policy.BEAT_GATES.items() if w not in ('australia', 'atlantis', 'glen')))
        self.assertFalse(any('master' in name or 'for_all' in name for name in overrides))

    def test_unknown_inputs_or_mixed_rewards_fail_closed_and_policy_is_static(self):
        for function, raw in ((policy.game_settings_payload,self.settings_raw), (policy.world_score_payload,self.score_raw)):
            with self.assertRaisesRegex(ValueError, 'require review'):
                function(raw+b'unknown')
        with self.assertRaisesRegex(ValueError, 'requires review'):
            policy.blocked_global_task({'action':'plantCropByCategory','rewards':{'reward':[
                {'type':'world_score','unit':'toylandPoints'}, {'type':'coins','value':1}]}})
        first = policy.policy_digest()
        with mock.patch.object(themed_worlds, 'ACTIVE_WORLDS', frozenset()):
            self.assertEqual(policy.policy_digest(), first)
            self.assertEqual(policy.game_settings_payload(), policy.game_settings_payload(self.settings_raw))
        self.assertEqual(hashlib.sha256(self.settings_raw).hexdigest(),policy.SETTINGS_SHA256)
        self.assertEqual(hashlib.sha256(self.score_raw).hexdigest(),policy.SCORE_SHA256)


class ThemedPresentationServingTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture

    def test_static_routes_are_exact_no_store_and_do_not_touch_player(self):
        path = self.write_fixture()
        before = path.read_bytes()
        routes = (("/xml/gz/v855098/gameSettings.xml.gz", policy.game_settings_payload()),
                  ("/xml/gz/v855098/worldScore.amf.gz", policy.world_score_payload()))
        for uid in (None, 'fixture-farmer'):
            with self.client.session_transaction() as session:
                session.clear()
                if uid:session['UID'] = uid
            for route, expected in routes:
                with self.subTest(uid=uid, route=route):
                    response = self.client.get(route)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.data, expected)
                    self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(path.read_bytes(), before)

    def test_both_bootstraps_use_all_original_beat_gates_without_muting_quests(self):
        self.write_fixture()
        with self.client.session_transaction() as session:session['UID'] = 'fixture-farmer'
        for route in ('/play.html','/ruffle.html'):
            with self.subTest(route=route), mock.patch.object(self.server,'NATIVE_WRAPPER',False), redirect_stdout(io.StringIO()):
                response = self.client.get(route)
            self.assertEqual(response.status_code,200)
            values = {name:int(value) for name,value in re.findall(r'"(fv_[A-Za-z0-9_]+)"\s*:\s*(-?\d+)',response.get_data(as_text=True))}
            for name,value in policy.beat_experiment_overrides().items():self.assertEqual(values[name],value)
            self.assertTrue(all(name not in policy.BEAT_EXPERIMENTS for name in ('fv_xtl_master','fv_xsh_master','fv_candy')))


if __name__ == '__main__':unittest.main()
