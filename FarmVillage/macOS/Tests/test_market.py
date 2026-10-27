"""Isolated AMF regression for the market refresh completion contract."""
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures


class MarketTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    def test_market_refresh_returns_every_array_and_current_seconds(self):
        self.write_fixture()
        from pyamf import remoting
        with mock.patch('market.timestamp_now', return_value=1792598400):
            response = self.gateway([self.command('CraftingService.onRefreshMarketView', [])])
        self.assertEqual(response.status_code, 200)
        envelope = remoting.decode(response.data)
        data = envelope.bodies[0][1].body['data'][0]['data']
        self.assertEqual(data['lastUpdated'], 1792598400)
        for key in ('marketStalls', 'craftedGoods', 'craftingSkills', 'ages'):
            self.assertIsNotNone(data[key])
            self.assertEqual(len(data[key]), 0)

    def test_postinit_and_refresh_use_same_market_shape(self):
        self.write_fixture()
        import commands
        import market
        with mock.patch('market.timestamp_now', return_value=1792598400):
            initial = commands.post_init_user('fixture-farmer')['marketView']
            self.assertEqual(initial, market.view())
        initial['marketStalls'].append({'uid': 'previous-response'})
        self.assertEqual(market.view()['marketStalls'], [])


if __name__ == '__main__':
    unittest.main()
