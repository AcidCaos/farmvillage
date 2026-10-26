import json
from pathlib import Path
import unittest
from test_engine import CheatEngine, CATALOG, NOW, farm


class HigherLevelTests(unittest.TestCase):
    def setUp(self):
        rules = json.loads((Path(__file__).resolve().parents[1] / 'data/rules.json').read_text())
        self.engine = CheatEngine(CATALOG, rules)
        self.save = farm()
        self.save['userInfo']['player'].update(xp=1500000, cash=0)

    def test_higher_levels_match_client_thresholds(self):
        self.assertEqual(self.engine.level_for_xp(1500000), 101)
        result = self.engine.apply(self.save, {'type': 'level', 'level': 251}, NOW)['save']
        self.assertEqual(result['userInfo']['player']['xp'], 16500000)
        self.assertEqual(result['userInfo']['player']['cash'], 149)
        self.assertEqual(self.engine.level_for_xp(result['userInfo']['player']['xp']), 251)

    def test_flash_limit_prevents_unsupported_level(self):
        with self.assertRaises(ValueError):
            self.engine.apply(self.save, {'type': 'level', 'level': 100000000}, NOW)
