"""B1 action-ledger regressions (2026-10-23).

Client calls whose effect this server cannot save must fail visibly, per call, without touching the save.
Calls that the server does handle, and the logged fall-through for names nothing recognises, must keep working.
"""
import copy
import json
from pathlib import Path
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import commands
import engine
import items


class ActionLedgerTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    def dict_action(self, action, obj, payload, sequence=1):
        return self.command('WorldService.performAction', [action, copy.deepcopy(obj), dict(payload)], sequence)

    def plot(self):
        save = self.player.session('fixture-farmer')
        return next(obj for obj in save['world']['objectsArray'] if obj.get('className') == 'Plot')

    def give_water_store(self, packages=0):
        save = self.player.session('fixture-farmer')
        save['userInfo']['featureOptions']['irrigation'] = {
            'irrigation': {'waterPlots': {'farm': {'amount': 20}}}}
        save['userInfo']['player']['storageData'] = {'-1': {'3YG': [packages, [], []]}} if packages else {}
        self.player.save_session('fixture-farmer')

    def test_event_credit_and_present_actions_reject_without_save_change(self):
        import bundle
        path = self.write_fixture()
        plot = self.plot()
        original = path.read_bytes()
        gold = json.loads(original)['userInfo']['player']['gold']
        log = Path(bundle.UNHANDLED_LOG)
        start = log.read_text() if log.exists() else ''
        names = ('buyRedeemItem', 'buyVoteItem', 'tradeSubcredits', 'addMultipleCredits', 'openPresent',
                 'sendPresent', 'openOrTrade', 'awardGifts', 'giftHarvestItem')
        for name in names:
            with self.subTest(action=name):
                # Two sequences: a client retry must fail the same way and charge or grant nothing.
                response = self.gateway([self.dict_action(name, plot, {'name': 'x'}),
                                         self.dict_action(name, plot, {'name': 'x'}, sequence=2)])
                fixtures.assert_gateway_rejected(self, response)
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(json.loads(path.read_text())['userInfo']['player']['gold'], gold)
                self.assertIn(name, commands.UNRESTORED_WORLD_ACTIONS)
        # Refused names are reported as refusals, not as silent acknowledgements.
        self.assertEqual(log.read_text() if log.exists() else '', start)

    def test_remaining_archived_mutations_refuse_without_save_change(self):
        path = self.write_fixture()
        plot = self.plot()
        before = path.read_bytes()
        names = ('UnlockNow', 'RemoveMysteryCrate', 'RemoveMysteryCrateBuilding', 'MysteryCrateCompleteNow',
                 'UpdateViralTime', 'GrantRetroactiveUpgrade', 'finishVoting', 'buyItemPutGiftbox',
                 'awardOpenedGifts', 'nutureFlowerShack')
        for name in names:
            with self.subTest(action=name):
                response = self.gateway([self.dict_action(name, plot, {'numGifts': 3}),
                                         self.dict_action(name, plot, {'numGifts': 3}, sequence=2)])
                fixtures.gateway_results(self, response, errors=[29, 29])
                self.assertEqual(path.read_bytes(), before)

    def test_archived_paid_services_refuse_and_do_not_erase_an_accepted_batch_mate(self):
        path = self.write_fixture()
        before = json.loads(path.read_text())
        response = self.gateway([
            self.command('UserService.buyItemPutGiftbox', ['cow', 1, True], 1),
            self.command('FlowerShackService.onBuyWorldCurrency', ['theflowershack', 100], 2),
            self.command('UserService.setSeenFlag', ['flag_archived_paid_services'], 3),
            self.command('FlowerShackService.onNutureAll', ['theflowershack', 'blossom'], 4),
        ])
        fixtures.gateway_results(self, response, errors=[29, 29, 0, 29])
        saved = json.loads(path.read_text())
        self.assertIs(saved['userInfo']['player']['seenFlags'].pop('flag_archived_paid_services'), True)
        self.assertEqual(saved, before)

    def test_unrestored_service_calls_fail_per_call_and_keep_their_batch_mates(self):
        path = self.write_fixture()
        before = json.loads(path.read_text())
        batch = [
            self.command('FarmService.buyFuel', [], 1),
            self.command('UserService.setSeenFlag', ['flag_action_ledger_test'], 2),
            self.command('IrrigationService.onIrrigationAction', ['water', 'sprinkler', 'water_crops'], 3),
            self.command('UserService.toggleWither', [{'id': 1}, True], 4),
            self.command('FarmService.buyTurboChargers', [], 5),
            self.command('ResourceEquipmentWorldService.onUseEquipment', [[], 'tractor', {}], 6),
            self.command('NeighborActionService.depositAnimalFeed', ['2', 'animalFeed'], 7),
        ]
        response = self.gateway(batch)
        fixtures.gateway_results(self, response, errors=[29, 0, 29, 29, 29, 29, 29])
        saved = json.loads(path.read_text())
        # Only the accepted batch mate changed the save; every refused call left it alone.
        self.assertIs(saved['userInfo']['player']['seenFlags']['flag_action_ledger_test'], True)
        self.assertEqual(saved['world'], before['world'])
        self.assertEqual(saved['userInfo']['player']['gold'], before['userInfo']['player']['gold'])

    def test_irrigation_package_use_credits_water_once_and_a_retry_is_refused(self):
        path = self.write_fixture()
        self.give_water_store(packages=2)
        self.assertEqual(json.loads(path.read_text())['userInfo']['player']['storageData'],
                         {'-1': {'3YG': [2, [], []]}})
        used = self.gateway([self.command('IrrigationService.consumeIrrigationPackages', ['waterPlots', 2], 1)])
        fixtures.gateway_results(self, used, errors=[0])
        saved = json.loads(path.read_text())
        self.assertNotIn('3YG', saved['userInfo']['player']['storageData'].get('-1', {}))
        self.assertEqual(saved['userInfo']['featureOptions']['irrigation']['irrigation']['waterPlots']['farm']['amount'],
                         22)
        # The packages are gone, so the same call again is refused and grants nothing.
        before = path.read_bytes()
        retry = self.gateway([self.command('IrrigationService.consumeIrrigationPackages', ['waterPlots', 2], 2)])
        fixtures.gateway_results(self, retry, errors=[29])
        self.assertEqual(path.read_bytes(), before)
        # Watering with an action name the client never sends is still refused.
        watering = self.gateway([self.command('IrrigationService.onIrrigationAction',
                                              ['water', 'sprinkler', 'water_crops'], 3)])
        fixtures.gateway_results(self, watering, errors=[29])
        self.assertEqual(path.read_bytes(), before)

    def test_planted_plot_watering_through_the_gateway_charges_one_unit_and_halves_the_wait(self):
        path = self.write_fixture()
        seed = next(item for item in items.get_items() if item.get('type') == 'seed' and item.get('growTime'))
        self.give_water_store(packages=0)
        save = self.player.session('fixture-farmer')
        plot = next(obj for obj in save['world']['objectsArray'] if obj.get('className') == 'Plot')
        planted_ms = int(time.time()) * 1000
        plot.update(state='planted', itemName=seed['name'], plantTime=planted_ms)
        self.player.save_session('fixture-farmer')
        grow_ms = commands.peaceful.grow_seconds(seed) * 1000
        response = self.gateway([self.command('IrrigationService.onIrrigationAction',
                                              ['waterPlots', [{'id': plot['id']}], None], 1)])
        fixtures.gateway_results(self, response, errors=[0])
        saved = json.loads(path.read_text())
        self.assertEqual(saved['userInfo']['featureOptions']['irrigation']['irrigation']['waterPlots']['farm']['amount'],
                         19)
        saved_plot = next(obj for obj in saved['world']['objectsArray'] if obj['id'] == plot['id'])
        self.assertEqual(saved_plot['state'], 'planted')
        # The watering happened within a few seconds of planting, so half of the full wait is left, give or take that.
        self.assertAlmostEqual(grow_ms - (int(time.time()) * 1000 - saved_plot['plantTime']), grow_ms / 2, delta=5000)

    def test_irrigation_package_purchases_charge_cash_and_deposit_each_water_gift(self):
        path = self.write_fixture()
        save = self.player.session('fixture-farmer')
        save['userInfo']['player']['cash'] = 100
        save['userInfo']['player']['storageData'] = {}
        self.player.save_session('fixture-farmer')
        names = sorted(f'pkg_consume_irrigation_water_{amount}' for amount in (100, 500, 1000, 2000))
        batch = [self.command('FarmService.buyConsumablePackage', [name], sequence)
                 for sequence, name in enumerate(names, 1)]
        response = self.gateway(batch)
        fixtures.gateway_results(self, response, errors=[0, 0, 0, 0])
        saved = json.loads(path.read_text())['userInfo']['player']
        self.assertEqual(saved['cash'], 100 - 57)
        gifts = saved['storageData']['-1']
        for code in ('Pcr', 'RcF', 'zSW', 'zT2'):
            self.assertEqual(gifts[code][0], 1, code)

    def test_refused_water_consume_without_a_store_changes_nothing(self):
        path = self.write_fixture()
        save = self.player.session('fixture-farmer')
        save['userInfo']['featureOptions']['irrigation'] = {'irrigation': {}}
        save['userInfo']['player']['storageData'] = {'-1': {'3YG': [2, [], []]}}
        self.player.save_session('fixture-farmer')
        before = path.read_bytes()
        response = self.gateway([self.command('IrrigationService.consumeIrrigationPackages', ['waterPlots', 2], 1)])
        fixtures.gateway_results(self, response, errors=[29])
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(engine.get_feature_option(self.player.session('fixture-farmer'), 'irrigation', 'irrigation'),
                         {})

    def test_unlisted_service_calls_still_acknowledge_without_rejection(self):
        import bundle
        path = self.write_fixture()
        before = json.loads(path.read_text())
        log = Path(bundle.UNHANDLED_LOG)
        start = log.read_text() if log.exists() else ''
        # Neighbour clear has no server record to clear and no charge, so it stays an acknowledged call that is
        # logged for triage. Unknown top-level names are acknowledged and logged, not refused: startup reads
        # depend on that fall-through.
        response = self.gateway([
            self.command('NeighborActionService.clearNeighborAction', ['2', 'plow', 99], 1),
            self.command('SomeUnknownService.readThing', [], 2),
        ])
        fixtures.gateway_results(self, response, errors=[0, 0])
        added = [json.loads(line) for line in log.read_text()[len(start):].splitlines() if line]
        self.assertEqual([row['functionName'] for row in added],
                         ['NeighborActionService.clearNeighborAction', 'SomeUnknownService.readThing'])
        self.assertEqual(json.loads(path.read_text())['world'], before['world'])


if __name__ == '__main__':
    unittest.main()
