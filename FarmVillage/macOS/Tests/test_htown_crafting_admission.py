"""Exact Mistletoe admission and live purchase tiers use disposable saves only."""
from contextlib import redirect_stdout
import copy
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import crafting
import themed_worlds as tw
import creative_worlds
import game_settings
import engine
import items
import world_travel

NOW = 1800000000
NAME = 'xhdcraftingcottage'
CLASS = 'CraftingCottageBuilding'
WORLD = 'htown'

class HtownCraftingAdmissionTests(unittest.TestCase):
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

    def prepare(self, *, level=15):
        self.path = self.write_fixture()
        self.save['world']['objectsArray'] = []
        self.save['userInfo']['player'].update(xp=game_settings.level_to_xp(level), gold=1000000, cash=200)
        creative_worlds.create(self.save, WORLD, 'allAccess', now=NOW)
        world_travel.switch(self.save, WORLD, now=NOW)
        self.save['importedProposalState'] = {'keep': [1, {'opaque': True}]}
        self.persist()
        self.item = items.get_item_by_name(NAME)

    def persist(self):
        with redirect_stdout(io.StringIO()):
            self.player.save_session('fixture-farmer')

    @staticmethod
    def cottage(ident=64001, **fields):
        return dict({'id': ident, 'className': CLASS, 'itemName': NAME, 'state': 'built',
                     'isFullyBuilt': True, 'craftLevel': 1, 'position': {'x': 10, 'y': 10, 'z': 0},
                     'opaqueImport': {'keep': [1, 2]}}, **fields)

    def guard(self, item=None, currency=None, **kw):
        return tw.guard_purchase(self.save, self.item if item is None else item, currency, now=NOW, **kw)

    def assert_refused(self, fn, *args, **kw):
        before = copy.deepcopy(self.save)
        disk = self.path.read_bytes()
        with self.assertRaises(ValueError):
            fn(*args, **kw)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)

    def send(self, snapshot, *, params=(), sequence=1, error=0):
        with mock.patch('server.timestamp_now', return_value=NOW), mock.patch('commands.timestamp_now', return_value=NOW), mock.patch('engine.timestamp_now', return_value=NOW):
            response = self.gateway([self.command('WorldService.performAction', ['place', snapshot, list(params)], sequence)])
        from pyamf import remoting
        result = remoting.decode(response.data).bodies[0][1].body['data'][0]
        self.assertEqual(result['errorType'], error, result)
        return fixtures.gateway_results(self, response, [error])[0]

    def test_catalog_preview_is_detached_authored_initial_tier(self):
        self.prepare()
        before = copy.deepcopy(self.item)
        self.assertEqual((self.item['name'], self.item['code'], self.item['craftType'], self.item['unlock']),
                         (NAME, '7la', 'xhdcrafttype', 'instance_tiered'))
        preview = crafting.regional_catalog_item(self.item, WORLD)
        self.assertEqual((preview['market'], preview['cost'], preview['buyXp'], preview['requiredLevel']),
                         ('coins', '100000', '1000', '15'))
        self.assertEqual(tw.catalog_rules(WORLD)['items'][NAME],
                         {'type': 'building', 'className': CLASS, 'price': {'currency': 'coins', 'amount': 100000}})
        self.assertEqual(self.item, before)
        self.assertIsNot(preview, self.item)
        self.assertNotIn(CLASS, tw.BASIC_CLASSES)

    def test_exact_helper_identity_world_class_and_unlock_only(self):
        self.prepare()
        self.assertEqual(tw._reasons(self.item, WORLD), [])
        for changes in ({'className': 'Building'}, {'className': 'FeatureBuilding'},
                        {'name': 'xrfcraftingcottage'}, {'craftType': 'bakery'}, {'craftType': None}):
            forged = dict(self.item, **changes)
            self.assertFalse(tw._regional_cottage(forged, WORLD))
            self.assertTrue(tw._reasons(forged, WORLD))
        for world in tw.SPECS:
            if world != WORLD:
                self.assertFalse(tw._regional_cottage(self.item, world))
                self.assertNotIn(NAME, tw.catalog_rules(world)['items'])
        for name in ('craftingbakery', 'xukcraftingpub', 'xrfcraftingcottage', 'xaf_herbalinn'):
            self.assertNotIn(name, tw.catalog_rules(WORLD)['items'])
        for changes, reason in (({'unlock': 'quest'}, 'unlock'), ({'features': {'expand': {}}}, 'feature'),
                                ({'requiredQuest': 'quest'}, 'requiredQuest'), ({'prereqs': {'id': 'real'}}, 'prereqs'),
                                ({'license': 'license'}, 'license'), ({'buyable': 'false'}, 'unavailable')):
            self.assertIn(reason, tw._reasons(dict(self.item, **changes), WORLD))

    def test_guard_resolves_live_first_tier_and_ignores_forged_price_preview(self):
        self.prepare()
        before = copy.deepcopy(self.save)
        preview = crafting.regional_catalog_item(self.item, WORLD)
        forged = dict(preview, cost='1', cash='0', buyXp='999999', requiredLevel='1')
        self.assertEqual(self.guard(forged), {'currency': 'coins', 'amount': 100000})
        self.assertEqual(self.guard(currency='gold'), {'currency': 'coins', 'amount': 100000})
        self.assertEqual(self.save, before)
        self.save['userInfo']['player']['xp'] = game_settings.level_to_xp(14)
        self.persist()
        self.assert_refused(self.guard, forged)

    def test_guard_uses_next_live_gift_tiers_two_three_and_no_later_guess(self):
        self.prepare()
        preview = crafting.regional_catalog_item(self.item, WORLD)
        for count in (1, 2):
            self.save['userInfo']['player']['storageData']['-1'] = {'LA': [count, [], []]}
            before = copy.deepcopy(self.save)
            resolved = crafting.purchase_catalog_item(self.save, self.item)
            self.assertEqual((resolved['market'], resolved['cash']), ('cash', '80'))
            self.assertEqual(self.guard(preview), {'currency': 'cash', 'amount': 80})
            self.assertEqual(self.save, before)
            self.assert_refused(self.guard, preview, 'coins')
        self.save['userInfo']['player']['storageData']['-1'] = {'LA': [3, [], []]}
        self.persist()
        self.assert_refused(self.guard, preview)
        self.assertEqual(tw.catalog_rules(WORLD)['items'][NAME]['price'], {'currency': 'coins', 'amount': 100000})

    def test_identity_currency_quantity_wallet_and_gift_shape_refuse_without_change(self):
        self.prepare()
        for changes in ({'code': 'forged'}, {'craftType': 'bakery'}, {'className': 'Decoration'}):
            self.assert_refused(self.guard, dict(self.item, **changes))
        for value in ('cash', 'jade', 'not-cash', True):
            self.assert_refused(self.guard, currency=value)
        for quantity in (0, -1, 2, True, 1.5):
            self.assert_refused(self.guard, quantity=quantity)
        self.save['userInfo']['player']['gold'] = 99999
        self.persist()
        self.assert_refused(self.guard)
        self.save['userInfo']['player'].update(gold=1000000, cash=79)
        self.save['userInfo']['player']['storageData']['-1'] = {'LA': [1, [], []]}
        self.persist()
        self.assert_refused(self.guard)
        for gifts in ([], {'LA': []}, {'LA': [-1, [], []]}, {'LA': [True, [], []]}):
            self.save['userInfo']['player']['storageData']['-1'] = gifts
            self.assert_refused(self.guard)

    def test_existing_same_cottage_remains_limit_one(self):
        self.prepare()
        self.save['world']['objectsArray'] = [self.cottage(901)]
        self.persist()
        self.assert_refused(self.guard)

    def test_exact_snapshot_and_place_accept_without_rewriting_imported_fields(self):
        self.prepare()
        self.save['world']['objectsArray'] = [self.cottage(901)]
        before = copy.deepcopy(self.save)
        self.assertEqual(tw.guard_snapshot(WORLD, self.save['world']), 0)
        self.assertEqual(self.save, before)
        self.save['world']['objectsArray'] = []
        before = copy.deepcopy(self.save)
        tw.guard_action(self.save, 'place', self.cottage(), [], now=NOW)
        self.assertEqual(self.save, before)
        for forged in (self.cottage(itemName='xrfcraftingcottage'), self.cottage(className='FeatureBuilding'),
                       self.cottage(className='Building'), self.cottage(itemName='craftingbakery')):
            self.assert_refused(tw.guard_action, self.save, 'place', forged, [], now=NOW)

    def test_unsupported_imported_cottages_and_other_worlds_stay_closed_unchanged(self):
        self.prepare()
        for fields in ({'itemName': 'xrfcraftingcottage'}, {'itemName': 'craftingbakery'},
                       {'itemName': 'unknown-cottage'}, {'className': 'FeatureBuilding'}, {'className': 'Building'}):
            self.save['world']['objectsArray'] = [self.cottage(901, **fields)]
            self.assert_refused(tw.guard_snapshot, WORLD, self.save['world'])
        for world in ('rainforest', 'australia', 'fforest'):
            snapshot = copy.deepcopy(self.save['world'])
            snapshot.update(tileSet=tw.recovered_rules(world)['tileSet'], objectsArray=[self.cottage(901)])
            before = copy.deepcopy(snapshot)
            with self.assertRaises(ValueError):
                tw.guard_snapshot(world, snapshot)
            self.assertEqual(snapshot, before)

    def test_world_travel_exception_is_only_exact_original_regional_cottage(self):
        self.prepare()
        before = copy.deepcopy(self.save)
        world_travel.guard_placement(self.save, self.cottage())
        self.assertEqual(self.save, before)
        for changes in ({'itemName': 'craftingbakery'}, {'itemName': 'xukcraftingpub'},
                        {'itemName': 'xrfcraftingcottage'}, {'className': 'Building'},
                        {'className': 'FeatureBuilding'}):
            self.assert_refused(world_travel.guard_placement, self.save, self.cottage(**changes))
        world_travel.switch(self.save, 'farm', now=NOW)
        world_travel.unlock_england(self.save, 'allAccess', now=NOW)
        world_travel.switch(self.save, 'england', now=NOW)
        self.assert_refused(world_travel.guard_placement, self.save, self.cottage())

    def test_signed_coin_place_charges_exact_xp_retry_reload_and_travel_preserve(self):
        self.prepare(level=30)
        before = copy.deepcopy(self.save)
        with mock.patch.object(engine, 'apply_xp_increment', wraps=engine.apply_xp_increment) as xp_calls:
            result = self.send(self.cottage())
        increments = [int(call.args[1]) for call in xp_calls.call_args_list]
        self.assertIn(1000, increments)
        self.assertEqual(result['errorType'], 0)
        self.assertEqual(self.save['userInfo']['player']['gold'], before['userInfo']['player']['gold'] - 100000)
        self.assertEqual(self.save['userInfo']['player']['cash'], before['userInfo']['player']['cash'])
        self.assertEqual(self.save['userInfo']['player']['xp'], before['userInfo']['player']['xp'] + sum(increments))
        self.assertEqual(self.save['importedProposalState'], before['importedProposalState'])
        accepted = copy.deepcopy(self.save['userInfo']['player'])
        self.send(self.cottage(), sequence=2)
        self.assertEqual(self.save['userInfo']['player'], accepted)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(len(self.save['world']['objectsArray']), 1)
        self.assertEqual(self.save['world']['objectsArray'][0]['opaqueImport'], {'keep': [1, 2]})
        world_travel.switch(self.save, 'farm', now=NOW)
        world_travel.switch(self.save, WORLD, now=NOW)
        self.assertEqual(self.save['userInfo']['player'], accepted)
        self.assertEqual(self.save['importedProposalState'], before['importedProposalState'])

    def test_signed_wrong_identity_class_world_and_other_cottages_are_atomic(self):
        self.prepare()
        for changes in ({'itemName': 'craftingbakery'}, {'itemName': 'xukcraftingpub'},
                        {'itemName': 'xrfcraftingcottage'}, {'className': 'Building'},
                        {'className': 'FeatureBuilding'}, {'className': 'Decoration'}):
            memory, disk = copy.deepcopy(self.save), self.path.read_bytes()
            self.send(self.cottage(**changes), error=29)
            self.assertEqual(self.save, memory)
            self.assertEqual(self.path.read_bytes(), disk)
        world_travel.switch(self.save, 'farm', now=NOW)
        world_travel.unlock_england(self.save, 'allAccess', now=NOW)
        world_travel.switch(self.save, 'england', now=NOW)
        self.persist()
        memory, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.send(self.cottage(), error=29)
        self.assertEqual(self.save, memory)
        self.assertEqual(self.path.read_bytes(), disk)

    def test_signed_cash_tier_ignores_cached_coin_preview_and_low_wallet_refuses_atomically(self):
        self.prepare(level=30)
        self.save['userInfo']['player']['storageData']['-1'] = {'LA': [1, [], []]}
        self.persist()
        before = copy.deepcopy(self.save['userInfo']['player'])
        self.send(self.cottage(), params=[{'currency': 'cash'}])
        self.assertEqual(self.save['userInfo']['player']['cash'], before['cash'] - 80)
        self.assertEqual(self.save['userInfo']['player']['gold'], before['gold'])
        self.prepare()
        self.save['userInfo']['player']['storageData']['-1'] = {'LA': [1, [], []]}
        self.save['userInfo']['player']['cash'] = 79
        self.persist()
        memory, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.send(self.cottage(), params=[{'currency': 'cash'}], error=29)
        self.assertEqual(self.save, memory)
        self.assertEqual(self.path.read_bytes(), disk)

if __name__ == '__main__':
    unittest.main(verbosity=2)
