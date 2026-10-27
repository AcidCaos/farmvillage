"""Peaceful policies remain detached, previewable and compatible with crop tools."""
import copy
import unittest
from test_engine import CheatEngine, CATALOG, RULES, NOW, farm


class PeacefulEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = CheatEngine(CATALOG, RULES)
        self.save = farm()

    def test_enable_revives_old_crops_preserves_original_and_previews_policy(self):
        original = copy.deepcopy(self.save)
        result = self.engine.apply(self.save, {'type': 'peaceful', 'enabled': True}, NOW)
        changed = result['save']
        self.assertEqual(self.save, original)
        self.assertEqual(changed['world']['objectsArray'][1]['state'], 'grown')
        self.assertEqual(changed['world']['objectsArray'][0]['state'], 'planted')
        self.assertFalse(changed['witherOn']['farm'])
        self.assertTrue(changed['peacefulMode']['enabled'])
        self.assertTrue(any(change['path'] == '/peacefulMode' for change in result['changes']))

    def test_long_time_jump_never_withers_peaceful_crop_even_without_one_shot_protection(self):
        protected = self.engine.apply(self.save, {'type': 'peaceful', 'enabled': True}, NOW)['save']
        advanced = self.engine.apply(protected, {'type': 'crops', 'action': 'advance', 'hours': 87600, 'protect': False}, NOW)['save']
        summary = self.engine.summarize(advanced, NOW + 10 * 365 * 86400)
        self.assertEqual([p['phase'] for p in summary['plots'][:2]], ['grown', 'grown'])
        self.assertEqual(advanced['world']['objectsArray'][3], self.save['world']['objectsArray'][3])

    def test_disable_restores_original_world_policies_and_fresh_harvest_window(self):
        self.save['witherOn'] = {'farm': True, 'england': False}
        protected = self.engine.apply(self.save, {'type': 'peaceful', 'enabled': True}, NOW)['save']
        disabled = self.engine.apply(protected, {'type': 'peaceful', 'enabled': False}, NOW)['save']
        self.assertEqual(disabled['witherOn'], {'farm': True, 'england': False})
        obj = disabled['world']['objectsArray'][1]
        self.assertEqual(self.engine.crop_status(obj, NOW)['phase'], 'grown')
        self.assertFalse(disabled['peacefulMode']['enabled'])

    def test_toggle_requires_a_real_boolean(self):
        for value in ('false', 0, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.engine.apply(self.save, {'type': 'peaceful', 'enabled': value}, NOW)

    def test_repeated_disable_keeps_world_policies_and_rebased_timer_unchanged(self):
        self.save['witherOn'] = {'farm': True, 'england': False, 'future_world': True}
        self.save['world']['objectsArray'][1]['unknownFutureData'] = {'keep': [1, 2]}
        protected = self.engine.apply(self.save, {'type': 'peaceful', 'enabled': True}, NOW)['save']
        disabled = self.engine.apply(protected, {'type': 'peaceful', 'enabled': False}, NOW)['save']
        again = self.engine.apply(disabled, {'type': 'peaceful', 'enabled': False}, NOW + 86400)['save']
        self.assertEqual(again, disabled)
        self.assertEqual(again['witherOn'], {'farm': True, 'england': False, 'future_world': True})
