"""Match recovered FarmGameSettingsManager higher levels and cash reward cap."""
from contextlib import ExitStack, redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import game_settings
import engine

ROOT = Path(__file__).resolve().parents[2]


class LevelParityTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        settings = game_settings._decode_game_settings((ROOT / 'xml/gz/v855098/gameSettings.xml.gz').read_bytes())
        for field, value in (('_cached_game_settings', settings), ('_cached_farming', {}),
                             ('_xp_level_map', None), ('_level_xp_map', None)):
            stack.enter_context(mock.patch.object(game_settings, field, value))
        game_settings._xp_level_map_init()
        stack.enter_context(redirect_stdout(io.StringIO()))
        self.save = json.loads((ROOT / 'villages/initial.json').read_text())
        self.save['userInfo']['player'].update(xp=game_settings.level_to_xp(100), cash=10)

    def test_original_table_boundary_and_extrapolated_thresholds(self):
        self.assertEqual(game_settings.xp_to_level(1499999), 100)
        self.assertEqual(game_settings.xp_to_level(1500000), 101)
        self.assertEqual(game_settings.xp_to_level(1600000), 102)
        self.assertEqual(game_settings.level_to_xp(101), 1500000)
        self.assertEqual(game_settings.level_to_xp(250), 16400000)

    def test_rewards_stop_at_original_client_cap_even_for_enormous_xp_grants(self):
        player = self.save['userInfo']['player']
        engine.apply_xp_increment(self.save, 2147483647 - player['xp'])
        self.assertEqual(player['cash'], 160)  # levels101 through250, once each
        engine.apply_xp_increment(self.save, 100000)
        self.assertEqual(player['cash'], 160)

    def test_level101_earnings_match_original_client(self):
        player = self.save['userInfo']['player']
        engine.apply_xp_increment(self.save, 1500000 - player['xp'])
        self.assertEqual(player['cash'], 11)
        self.assertEqual(game_settings.xp_to_level(player['xp']), 101)
