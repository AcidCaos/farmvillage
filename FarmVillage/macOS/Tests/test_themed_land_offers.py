"""Derived themed land availability is bounded to fourteen accepted contracts."""
import copy
from collections import Counter
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zlib

import pyamf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence  # Configure synthetic data paths before product imports.
import themed_land_offers as policy
import themed_worlds


class ThemedLandOfferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT / 'xml/gz/v855038/items_opt.amf'
        cls.raw = cls.source.read_bytes()
        cls.settings = policy.SETTINGS_SOURCE.read_bytes()
        cls.items = pyamf.get_decoder(pyamf.AMF3, zlib.decompress(cls.raw)).readElement()['settings']['items']['item']

    def test_actual_catalog_has_exact_522_closures_and_fourteen_base_records_remain(self):
        counts, bases, blocked = Counter(), [], []
        for item in self.items:
            if policy.blocked_offer(item):
                blocked.append(item)
                owners = sorted(set(policy._world_nodes(item.get('requirements'))))
                self.assertEqual(len(owners), 1)
                counts[owners[0]] += 1
            elif (item.get('type') == 'change_farm' and item.get('subtype') == 'expand_farm'
                  and policy._width(item.get('squares')) == 50
                  and set(policy._world_nodes(item.get('requirements'))) & set(themed_worlds.SPECS)):
                bases.append(item)
        self.assertEqual(counts, {'rainforest': 38, 'mediterranean': 38, 'storybook': 38,
            'candy': 42, 'oasis': 38, 'oz': 38, 'toyland': 38, 'sleepyhollow': 27,
            'australia': 38, 'fforest': 38, 'htown': 35, 'atlantis': 38, 'glen': 38, 'hlights': 38})
        self.assertEqual((len(blocked), len(bases)), (522, 14))
        toy = next(x for x in blocked if x['name'] == 'xtlfarm14')
        self.assertEqual((toy['code'], toy['squares'], toy['cost']), ('XX', '58', '10000'))

    def test_other_worlds_home_england_and_all_nonland_definitions_are_untouched(self):
        worlds = set()
        for item in self.items:
            owners = set(policy._world_nodes(item.get('requirements')))
            if not owners & set(themed_worlds.SPECS):
                self.assertFalse(policy.blocked_offer(item))
                worlds.update(owners)
            if item.get('type') != 'change_farm' or item.get('subtype') != 'expand_farm':
                self.assertFalse(policy.blocked_offer(item))
        self.assertGreaterEqual(len(worlds), 53)
        self.assertEqual(len(worlds), 70)
        base = {'name': 'xtlfarm14', 'type': 'change_farm', 'subtype': 'expand_farm', 'squares': '58'}
        for world in ('farm', 'home', 'england', 'meadows', 'fisherman', 'unrecognized'):
            with self.subTest(world=world):
                item = {**base, 'requirements': {'requirement': {'className': 'World', 'name': world}}}
                self.assertFalse(policy.blocked_offer(item))
        for width in (None, '', '58.0', -1, True, 58.5, ['58']):
            self.assertFalse(policy.blocked_offer({**base, 'squares': width}))

    def test_original_added_objects_are_also_fenced_below_the_later_width_boundary(self):
        item = {'name': 'xtlfarm13', 'type': 'change_farm', 'subtype': 'expand_farm', 'squares': '54',
                'requirements': {'requirement': {'className': 'World', 'name': 'toyland'}}}
        original = copy.deepcopy(item)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'settings.xml.gz'
            source.write_bytes(zlib.compress(b'<settings><farmExpansions><world name="toyland"><farmExpansionAddedItems><addedItems squares="54"><addedItem code="authored"/></addedItems></farmExpansionAddedItems></world></farmExpansions></settings>'))
            with mock.patch.object(policy, 'SETTINGS_SOURCE', source):
                self.assertTrue(policy.blocked_offer(item))
        self.assertEqual(item, original)

    def test_policy_is_pure_and_cache_identity_covers_settings_specs_and_own_source(self):
        item = next(x for x in self.items if x['name'] == 'xtlfarm14')
        before = copy.deepcopy(item)
        self.assertTrue(policy.blocked_offer(item)); self.assertEqual(item, before)
        baseline = policy.policy_digest()
        self.assertRegex(baseline, r'^[0-9a-f]{64}$')
        with tempfile.TemporaryDirectory() as directory:
            settings = Path(directory) / 'settings.gz'; settings.write_bytes(self.settings + b'identity-only-change')
            with mock.patch.object(policy, 'SETTINGS_SOURCE', settings):
                self.assertNotEqual(policy.policy_digest(), baseline)
            source = Path(directory) / 'source.py'; source.write_bytes(Path(policy.__file__).read_bytes() + b'\n# identity')
            with mock.patch.object(policy, '__file__', str(source)):
                self.assertNotEqual(policy.policy_digest(), baseline)
        specs = copy.deepcopy(themed_worlds.SPECS); specs['toyland']['prefix'] = 'changed'
        with mock.patch.object(themed_worlds, 'SPECS', specs):
            self.assertNotEqual(policy.policy_digest(), baseline)
        self.assertEqual(self.source.read_bytes(), self.raw)
        self.assertEqual(policy.SETTINGS_SOURCE.read_bytes(), self.settings)
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), '14987fd4c07f9de35ff5092aeab58584802fd7fbeca1131ad1a5e3eee381a4d7')


if __name__ == '__main__':
    unittest.main()
