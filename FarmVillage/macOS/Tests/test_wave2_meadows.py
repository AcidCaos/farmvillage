"""W03 complete original land variants and narrow item boundaries."""
import copy
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import unittest
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_creative_worlds as base
import test_persistence as fixtures
import creative_worlds
import items
import meadows_rules
import world_travel


class MeadowsWaveTwoTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway
    prepare = base.AdditionalFarmTests.prepare
    create = base.AdditionalFarmTests.create

    def meadow(self):
        save = self.prepare(cash=1000, level=100)
        self.create(save)
        world_travel.switch(save, 'meadows', now=base.NOW)
        save['userInfo']['player']['gold'] = 1000000000
        return save

    def test_admission_date_is_inclusive_at_original_five_hour_offset(self):
        from datetime import datetime, timezone
        boundary = int(datetime(2012, 10, 8, 5, tzinfo=timezone.utc).timestamp())
        self.assertEqual(creative_worlds.recovered_rules()['startTime'], boundary)
        save = self.prepare()
        before = copy.deepcopy(save)
        with self.assertRaisesRegex(ValueError, 'date'):
            creative_worlds.create(save, 'meadows', now=boundary - 1)
        self.assertEqual(save, before)
        self.assertTrue(creative_worlds.create(save, 'meadows', now=boundary))
        self.assertEqual(save['userInfo']['player']['cash'], 0)
        self.assertEqual(save['userInfo']['player']['storageData']['-1']['66e'][0], 1)

    def test_placement_cannot_replace_owned_object_or_plow_without_coins(self):
        save = self.meadow()
        hay = {'id': 900, 'className': 'Decoration', 'itemName': 'haybale',
               'state': 'static', 'position': {'x': 4, 'y': 4, 'z': 0}}
        save['world']['objectsArray'] = [hay]
        plot = dict(hay, className='Plot', itemName=None, state='plowed')
        other = dict(hay, className='Tree', itemName='apple', state='grown')
        for action, snapshot in (('plow', plot), ('place', other)):
            before = copy.deepcopy(save)
            with self.assertRaises(ValueError):
                creative_worlds.guard_action(save, action, snapshot, [])
            self.assertEqual(save, before)
        save['world']['objectsArray'] = []
        save['userInfo']['player']['gold'] = 14
        before = copy.deepcopy(save)
        with self.assertRaisesRegex(ValueError, 'Not enough coins'):
            creative_worlds.guard_action(save, 'plow', plot, [])
        self.assertEqual(save, before)
        save['userInfo']['player']['gold'] = 15
        creative_worlds.guard_action(save, 'plow', plot, [])

    def test_all_32_original_variants_charge_once_without_added_objects(self):
        for cash in (False, True):
            save = self.meadow()
            original_objects = copy.deepcopy(save['world']['objectsArray'])
            for size in range(14, (50 if cash else 38) + 1, 2):
                name = 'xmwfarm' + str(size) + ('_cash' if cash else '')
                item = items.get_item_by_name(name)
                balance = 'cash' if cash else 'gold'
                before = save['userInfo']['player'][balance]
                creative_worlds.expand_farm(save, item, 'cash' if cash else 'coins', neighbor_count=45)
                self.assertEqual(save['world']['sizeX'], size * 4 + 2)
                self.assertEqual(save['world']['sizeY'], size * 4 + 2)
                cost = 1 if cash else meadows_rules.COIN_PRICES[(size - 14) // 2]
                self.assertEqual(save['userInfo']['player'][balance], before - cost)
                once = copy.deepcopy(save)
                creative_worlds.expand_farm(save, item, 'cash' if cash else 'coins', neighbor_count=45)
                self.assertEqual(save, once)
            self.assertEqual(save['world']['objectsArray'], original_objects)

    def test_wrong_order_currency_identity_gate_and_imported_size_are_atomic(self):
        save = self.meadow()
        item = items.get_item_by_name('xmwfarm14_cash')
        cases = [items.get_item_by_name('xmwfarm16_cash'), items.get_item_by_name('xmwfarm12'),
                 dict(item, experimentGate='fv_meadows_fiction'), dict(item, squares='202'),
                 dict(item, requiredQuest='unknown'), dict(item, limitedStart='1/1/2099')]
        for bad in cases:
            before = copy.deepcopy(save)
            with self.assertRaises(ValueError):
                creative_worlds.expand_farm(save, bad, 'cash')
            self.assertEqual(save, before)
        before = copy.deepcopy(save)
        with self.assertRaises(ValueError):
            creative_worlds.expand_farm(save, item, 'coins')
        self.assertEqual(save, before)
        with mock.patch.object(meadows_rules, 'experiment_enabled', return_value=False):
            with self.assertRaisesRegex(ValueError, 'experiment'):
                creative_worlds.expand_farm(save, item, 'cash')
        self.assertEqual(save, before)
        save['world'].update(sizeX=59, sizeY=59)
        before = copy.deepcopy(save)
        with self.assertRaisesRegex(ValueError, 'recovery'):
            creative_worlds.expand_farm(save, items.get_item_by_name('xmwfarm16_cash'), 'cash')
        self.assertEqual(save, before)

    def test_original_45_neighbor_boundary_and_insufficient_funds(self):
        save = self.meadow()
        save['world'].update(sizeX=106, sizeY=106)  # Explicit late-stage fixture.
        item = items.get_item_by_name('xmwfarm28')
        for neighbors, coins in ((44, 4000000), (45, 3999999)):
            save['userInfo']['player']['gold'] = coins
            before = copy.deepcopy(save)
            with self.assertRaises(ValueError):
                creative_worlds.expand_farm(save, item, 'coins', neighbor_count=neighbors)
            self.assertEqual(save, before)
        save['userInfo']['player']['gold'] = 4000000
        creative_worlds.expand_farm(save, item, 'coins', neighbor_count=45)
        self.assertEqual(save['userInfo']['player']['gold'], 0)

    def test_authoritative_object_class_prevents_item_spoof(self):
        save = self.meadow()
        for name, forged in (('haybale', 'Building'), ('toolshedpink', 'Decoration'), ('cow', 'Tree')):
            item = items.get_item_by_name(name)
            snapshot = {'id': 64001, 'itemName': name, 'className': forged,
                        'state': 'static', 'position': {'x': 10, 'y': 10, 'z': 0}}
            before = copy.deepcopy(save)
            with self.assertRaisesRegex(ValueError, 'recovered object class'):
                creative_worlds.guard_action(save, 'place', snapshot, [{'isGift': True}])
            self.assertEqual(save, before)

    def test_item_experiment_exact_variants_and_unknown_prerequisites(self):
        save = self.meadow()
        hay = items.get_item_by_name('haybale')
        for item in (dict(hay, experimentGate='fv_meadows_activate', experimentVariant='2,3'),
                     dict(hay, experimentGate='fv_meadows_1436FC'),
                     dict(hay, experimentGate='fv_meadows_activate'),
                     dict(hay, experimentGate='fv_meadows_activate', experimentVariant=''),
                     dict(hay, experimentVariant='2')):
            creative_worlds.guard_market_purchase(save, item, neighbor_count=0)
        for changes in ({'experimentGate': 'fv_unrecovered'}, {'gateCode': 'unknown'},
                        {'experimentGate': 'fv_meadows_activate', 'experimentVariant': '1,2'},
                        {'unlock': 'unknown'}):
            before = copy.deepcopy(save)
            with self.assertRaises(ValueError):
                creative_worlds.guard_market_purchase(save, dict(hay, **changes), neighbor_count=0)
            self.assertEqual(save, before)

    def test_global_object_ceiling_and_imported_limit_preserve_recovery(self):
        from game_settings import get_farming_int
        self.assertEqual(get_farming_int('maxNumObjects', 5000), 5500)
        snapshot = {'id': 64001, 'className': 'Plot'}
        for imported, maximum in ((None, 5500), (23, 23)):
            with self.subTest(imported=imported):
                save = self.meadow()
                if imported is not None:
                    save['world']['maxNumObjects'] = imported
                objects = [{'id': number + 1, 'className': 'Plot'} for number in range(maximum - 1)]
                save['world']['objectsArray'] = objects
                before = copy.deepcopy(save)
                meadows_rules.guard_new_object(save, snapshot, None)
                self.assertEqual(save, before)
                objects.append({'id': maximum, 'className': 'Plot'})
                before = copy.deepcopy(save)
                with self.assertRaisesRegex(ValueError, 'object limit'):
                    meadows_rules.guard_new_object(save, snapshot, None)
                self.assertEqual(save, before)
                # Existing plots remain editable even at/above an imported cap.
                objects.append({'id': maximum + 1, 'className': 'Plot'})
                before = copy.deepcopy(save)
                meadows_rules.guard_new_object(save, objects[0], objects[0])
                self.assertEqual(save, before)
                if imported is not None:
                    self.assertEqual(save['world']['maxNumObjects'], imported)
                else:
                    self.assertNotIn('maxNumObjects', save['world'])

    def test_experiment_variant_parser_rejects_malformed_lists_and_client_disagreement(self):
        hay = items.get_item_by_name('haybale')
        gate = dict(hay, experimentGate='fv_meadows_activate')
        for variant in (None, True, False, 3.0, [], {}, '2,,3', '2, 3', '03', '3.0', ',3', '3,'):
            with self.subTest(variant=variant), self.assertRaisesRegex(ValueError, 'invalid'):
                meadows_rules.guard_item_experiment(dict(gate, experimentVariant=variant))
        # Explicit lists select by integer membership; absent lists require >0.
        with mock.patch.object(meadows_rules.Path, 'read_text', return_value='"fv_meadows_activate": 0'):
            with self.assertRaisesRegex(ValueError, 'not enabled'):
                meadows_rules.guard_item_experiment(gate)
            meadows_rules.guard_item_experiment(dict(gate, experimentVariant='0,3'))
        with mock.patch.object(meadows_rules.Path, 'read_text', side_effect=(
                '"fv_meadows_activate": 2', '"fv_meadows_activate": 3')):
            with self.assertRaisesRegex(ValueError, 'disagree'):
                meadows_rules.guard_item_experiment(dict(gate, experimentVariant='2,3'))
        for variant in (None, False, {}, 'unparsed orphan'):
            meadows_rules.guard_item_experiment(dict(hay, experimentVariant=variant))

    def test_amf_later_expansion_retry_per_command_rollback_and_reload(self):
        save = self.meadow()
        save['world'].update(sizeX=146, sizeY=146)  # Seeded prerequisite size.
        with redirect_stdout(io.StringIO()):
            self.player.save_session('fixture-farmer')
        command = self.command('FarmService.expandFarm', ['xmwfarm38_cash', 'cash'])
        response = self.gateway([command])
        fixtures.assert_gateway_status(self, response, 200)
        cash = self.player.session('fixture-farmer')['userInfo']['player']['cash']
        fixtures.assert_gateway_status(self, self.gateway([command]), 200)
        self.assertEqual(self.player.session('fixture-farmer')['userInfo']['player']['cash'], cash)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        mixed = [self.command('FarmService.expandFarm', ['xmwfarm40_cash', 'cash'], 2),
                 self.command('FarmService.expandFarm', ['xmwfarm50_cash', 'cash'], 3)]
        fixtures.gateway_results(self, self.gateway(mixed), errors=[0, 29])
        saved = self.player.session('fixture-farmer')
        self.assertEqual(saved['world']['sizeX'], 162)
        self.assertEqual(saved['userInfo']['player']['cash'], cash - 1)
        settled = self.path.read_bytes()
        fixtures.gateway_results(self, self.gateway(mixed), errors=[0, 29])
        self.assertEqual(self.path.read_bytes(), settled)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        saved = self.player.session('fixture-farmer')
        self.assertEqual(saved['world']['sizeX'], 162)
        self.assertEqual(saved['userInfo']['player']['cash'], cash - 1)


if __name__ == '__main__':
    unittest.main()
