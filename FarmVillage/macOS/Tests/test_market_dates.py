"""Original market date windows and paid planting; disposable AMF saves only."""
import copy
from contextlib import contextmanager, ExitStack, redirect_stdout
from datetime import datetime, timezone
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures  # Redirect all writable paths before product imports.
import test_cove_cellar as cellar_fixtures
import creative_worlds
import items
import storage


NOW = 1800000000
WORLDS = ("farm", "england", "meadows", "fisherman")


class MarketDateTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway
    save = cellar_fixtures.CoveCellarTests.save
    prepare = cellar_fixtures.CoveCellarTests.prepare
    persist = cellar_fixtures.CoveCellarTests.persist

    def send(self, action, snapshot, params=(), *, now=NOW, expected=200, sequence=None):
        self._gateway_sequence = getattr(self, "_gateway_sequence", 0) + 1
        if sequence is None:
            sequence = self._gateway_sequence
        self._gateway_sequence = max(self._gateway_sequence, sequence)
        with mock.patch("server.timestamp_now", return_value=now), mock.patch(
                "commands.timestamp_now", return_value=now), mock.patch("engine.timestamp_now", return_value=now):
            response = self.gateway([self.command("WorldService.performAction", [action, snapshot, list(params)], sequence)])
        fixtures.assert_gateway_status(self, response, expected)
        if expected == 200:
            from pyamf import remoting
            return remoting.decode(response.data).bodies[0][1].body["data"][0]["data"]

    def rejected(self, action, snapshot, params=()):
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.send(action, snapshot, params, expected=400)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)

    @staticmethod
    def plot(ident=630, **changes):
        return dict({"id": ident, "className": "Plot", "itemName": None,
            "state": "plowed", "position": {"x": 4, "y": 4, "z": 0}, "plantTime": 0}, **changes)

    @contextmanager
    def dated_item(self, name, **dates):
        lookup = items.get_item_by_name
        original = lookup(name)
        before = copy.deepcopy(original)
        dated = dict(original, **dates)
        def find(requested):
            return dated if requested == name else lookup(requested)
        with ExitStack() as stack:
            for target in ("items.get_item_by_name", "commands.get_item_by_name", "storage.get_item_by_name"):
                stack.enter_context(mock.patch(target, side_effect=find))
            yield dated
        self.assertEqual(lookup(name), before)

    def prepare_market(self, world):
        self.prepare(world, gold=1000000)
        self.save["world"]["objectsArray"] = [self.plot(), {
            "id": 900, "className": "StorageBuilding", "itemName": "toolshedpink",
            "state": "built", "contents": [], "position": {"x": 12, "y": 12, "z": 0}}]
        self.save["userInfo"]["player"]["cash"] = 100
        self.group = storage.active_inventory_id(self.save)
        self.save["userInfo"]["player"]["storageData"][str(self.group)] = {}
        self.persist()

    def market_snapshot(self):
        return {"id": self.group, "className": "StorageBuilding"}

    def market_options(self, name="haybale", **changes):
        return dict({"storedItemName": name, "target": self.group,
                     "origin": 0, "resource": 0}, **changes)

    def test_original_cove_blackberries_with_historical_start_save_and_retry_once(self):
        item = items.get_item_by_name("blackberriesdarrow")
        self.assertEqual((item["code"], item["limitedStart"], item["cost"], item["buyable"]),
                         ("0eR", "9/12/2011", "30", "true"))
        self.assertNotIn("limitedEnd", item)
        self.assertNotIn("market", item)  # The original empty currency means coins.
        self.prepare_market("fisherman")
        self.save["world"].update(sizeX=58, sizeY=58)
        self.save["world"]["objectsArray"][0]["position"] = {"x": 50, "y": 43, "z": 0}
        self.persist()
        crop = self.plot(itemName=item["name"], state="planted", plantTime=1,
                         position={"x": 50, "y": 43, "z": 0})
        before = copy.deepcopy(self.save["userInfo"]["player"])
        self.send("place", crop, [{"currency": ""}], sequence=10)
        self.assertEqual(self.save["userInfo"]["player"]["gold"], before["gold"] - 30)
        self.assertEqual(self.save["userInfo"]["player"]["cash"], before["cash"])
        saved = copy.deepcopy(self.save["world"]["objectsArray"][0])
        self.assertEqual((saved["id"], saved["plantTime"], saved["itemName"]), (630, NOW * 1000, item["name"]))
        once = copy.deepcopy(self.save)
        self.send("place", crop, [{"currency": ""}], sequence=10)
        self.assertEqual(self.save, once)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.save["world"]["objectsArray"][0], saved)
        self.assertEqual(self.save["userInfo"]["player"]["gold"], before["gold"] - 30)

    def test_start_and_end_are_exclusive_at_original_server_offset(self):
        from game_settings import get_farming_int
        self.assertEqual(get_farming_int("globalServerUTCOffsetHours"), 4)
        boundary = int(datetime(2026, 10, 22, 5, tzinfo=timezone.utc).timestamp())
        date = "10/22/2026"
        with self.assertRaisesRegex(ValueError, "start date"):
            creative_worlds._guard_purchase_dates({"limitedStart": date}, now=boundary - 1)
        with self.assertRaisesRegex(ValueError, "start date"):
            creative_worlds._guard_purchase_dates({"limitedStart": date}, now=boundary)
        creative_worlds._guard_purchase_dates({"limitedStart": date}, now=boundary + 1)
        creative_worlds._guard_purchase_dates({"limitedEnd": date}, now=boundary - 1)
        with self.assertRaisesRegex(ValueError, "end date"):
            creative_worlds._guard_purchase_dates({"limitedEnd": date}, now=boundary)

    def test_historical_and_epoch_start_pass_but_epoch_end_remains_expired(self):
        for value in ("9/12/2011", "01/01/1970", "1/1/1970"):
            creative_worlds._guard_purchase_dates({"limitedStart": value}, now=NOW)
        with self.assertRaisesRegex(ValueError, "end date"):
            creative_worlds._guard_purchase_dates({"limitedEnd": "01/01/1970"}, now=NOW)
        creative_worlds._guard_purchase_dates({}, now=NOW)

    def test_malformed_present_dates_fail_closed(self):
        for key in ("limitedStart", "limitedEnd"):
            for value in (None, "", False, 0, [], {}, "02/30/2026", "2/29/2025", "13/1/2026",
                          "2026-10-22", "10/22/26", "10/22/2026 00:00", " 10/22/2026"):
                with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, "date is invalid"):
                    creative_worlds._guard_purchase_dates({key: value}, now=NOW)

    def test_plant_and_market_storage_share_started_offer_and_original_coin_prices_in_four_worlds(self):
        for world in WORLDS:
            with self.subTest(world=world):
                self.prepare_market(world)
                before = copy.deepcopy(self.save["userInfo"]["player"])
                with self.dated_item("strawberry", limitedStart="9/12/2011"):
                    crop = self.plot(itemName="strawberry", state="planted", plantTime=1)
                    self.send("place", crop)
                    self.assertEqual(self.save["userInfo"]["player"]["gold"], before["gold"] - 10)
                    self.send("place", crop)
                    self.assertEqual(self.save["userInfo"]["player"]["gold"], before["gold"] - 10)
                with self.dated_item("haybale", limitedStart="01/01/1970"):
                    self.send("store", self.market_snapshot(), [self.market_options(numToStore=2)])
                player = self.save["userInfo"]["player"]
                self.assertEqual(player["gold"], before["gold"] - 210)
                self.assertEqual(player["cash"], before["cash"])
                self.assertEqual(player["storageData"][str(self.group)]["HB"][0], 2)

    def test_future_expired_and_malformed_planting_and_storage_never_mutate_any_world(self):
        windows = ({"limitedStart": "1/1/2099"}, {"limitedEnd": "9/12/2011"},
                   {"limitedStart": "broken"}, {"limitedEnd": "02/30/2011"})
        for world in WORLDS:
            self.prepare_market(world)
            for dates in windows:
                with self.subTest(world=world, dates=dates):
                    with self.dated_item("strawberry", **dates):
                        self.rejected("place", self.plot(itemName="strawberry", state="planted"))
                    with self.dated_item("haybale", **dates):
                        self.rejected("store", self.market_snapshot(), [self.market_options()])

    def test_active_dates_preserve_original_cash_price_and_full_quantity_preflight(self):
        for world in WORLDS:
            with self.subTest(world=world):
                self.prepare_market(world)
                self.save["userInfo"]["player"].update(cash=43)
                self.persist()
                with self.dated_item("toolshedpink", limitedStart="9/12/2011", limitedEnd="1/1/2099"):
                    self.rejected("store", self.market_snapshot(), [self.market_options("toolshedpink", numToStore=2)])
                    self.send("store", self.market_snapshot(), [self.market_options("toolshedpink")])
                    self.assertEqual(self.save["userInfo"]["player"]["cash"], 21)
                    self.assertEqual(self.save["userInfo"]["player"]["gold"], 1000000)

    def test_owned_gift_withdrawal_and_successful_crop_retry_do_not_repurchase_an_expired_offer(self):
        for world in WORLDS:
            with self.subTest(world=world):
                self.prepare_market(world)
                crop = self.plot(itemName="strawberry", state="planted")
                with self.dated_item("strawberry", limitedStart="9/12/2011", limitedEnd="1/1/2099"):
                    self.send("place", crop, sequence=10)
                once = copy.deepcopy(self.save)
                with self.dated_item("strawberry", limitedEnd="9/12/2011"):
                    self.send("place", crop, sequence=10)
                self.assertEqual(self.save, once)
                self.save["userInfo"]["player"]["storageData"]["-1"] = {"HB": [1, [], []]}
                self.persist()
                before = copy.deepcopy(self.save["userInfo"]["player"])
                hay = {"id": 64001, "className": "Decoration", "itemName": "haybale",
                       "state": "static", "position": {"x": 20, "y": 20, "z": 0}}
                with self.dated_item("haybale", limitedEnd="9/12/2011"):
                    self.send("place", hay, [{"isGift": True}])
                self.assertEqual(self.save["userInfo"]["player"]["gold"], before["gold"])
                self.assertEqual(self.save["userInfo"]["player"]["cash"], before["cash"])
                self.assertNotIn("HB", self.save["userInfo"]["player"]["storageData"]["-1"])

    def test_blackberry_world_and_currency_requirements_still_reject_without_charge(self):
        for world in WORLDS:
            with self.subTest(world=world):
                self.prepare_market(world)
                crop = self.plot(itemName="blackberriesdarrow", state="planted")
                if world != "fisherman":
                    self.rejected("place", crop)
                else:
                    self.rejected("place", crop, [{"currency": "cash"}])
                    self.save["userInfo"]["player"]["gold"] = 29
                    self.persist()
                    self.rejected("place", crop)


if __name__ == "__main__":
    unittest.main()
