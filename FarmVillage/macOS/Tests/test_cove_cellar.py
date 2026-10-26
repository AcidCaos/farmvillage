"""Original cellar market gate and deletion rules; disposable AMF saves only."""
import copy
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import cove_rules
import creative_worlds
import world_travel

NOW = 1800000000


class CoveCellarTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    @property
    def save(self):
        return self.player.session("fixture-farmer")

    def prepare(self, world="fisherman", *, level=16, gold=1000):
        from game_settings import level_to_xp
        self.path = self.write_fixture()
        # Keep purchase accounting below the unrelated two-building ribbon.
        self.save["world"]["objectsArray"] = []
        self.save["userInfo"]["player"].update(xp=level_to_xp(level), cash=60, gold=gold)
        if world in ("fisherman", "meadows"):
            creative_worlds.create(self.save, world,
                "allAccess" if world == "fisherman" else "cash60", now=NOW)
        if world != "farm":
            world_travel.switch(self.save, world, world == "england", now=NOW)
        self.persist()

    def persist(self):
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")

    @staticmethod
    def cellar(ident=64001):
        return {"id": ident, "className": "InventoryCellar", "itemName": "hatchstorage",
                "state": "built", "position": {"x": 4, "y": 4, "z": 0}}

    def send(self, action, snapshot, params=(), *, expected=200):
        self._gateway_sequence = getattr(self, "_gateway_sequence", 0) + 1
        with mock.patch("server.timestamp_now", return_value=NOW), mock.patch(
                "commands.timestamp_now", return_value=NOW), mock.patch("engine.timestamp_now", return_value=NOW):
            response = self.gateway([self.command("WorldService.performAction", [action, snapshot, list(params)], sequence=self._gateway_sequence)])
        fixtures.assert_gateway_status(self, response, expected)
        if expected == 200:
            from pyamf import remoting
            return remoting.decode(response.data).bodies[0][1].body["data"][0]["data"]

    def rejected(self, action, snapshot, params=()):
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.send(action, snapshot, params, expected=400)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)

    def test_original_cellar_catalog_and_location_predicate_are_exact(self):
        from items import get_item_by_name
        item = get_item_by_name("hatchstorage")
        self.assertEqual(tuple(item[key] for key in ("code", "className", "marketPrereqs",
            "requiredLevel", "cost", "capacity", "limit", "disallowDelete")),
            ("v0", "InventoryCellar", "storage_world_locks", "16", "1", "1250", "1", "1"))
        self.assertEqual(cove_rules._storage_market_worlds(),
            frozenset(("garden", "england", "fisherman", "farm", "village", "meadows")))
        for world in ("fisherman", "meadows"):
            self.assertTrue(cove_rules.allows_cellar_market_prerequisite(item, world))
        for world in ("winterwonderland", "hawaii", "unknown"):
            self.assertFalse(cove_rules.allows_cellar_market_prerequisite(item, world))
        self.assertFalse(cove_rules.allows_cellar_market_prerequisite(dict(item, name="other"), "fisherman"))
        self.assertFalse(cove_rules.allows_cellar_market_prerequisite(dict(item, marketPrereqs="unknown"), "fisherman"))

    def test_cellar_contract_drift_and_other_purchase_gates_still_fail_closed(self):
        from items import get_item_by_name
        self.prepare()
        item = get_item_by_name("hatchstorage")
        for key, value in (("requiredLevel", "1"), ("cost", "0"), ("capacity", "99999"),
                ("limit", "2"), ("disallowDelete", "0"), ("code", "other"), ("market", "cash")):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "catalog rules"):
                creative_worlds.guard_market_purchase(self.save, dict(item, **{key: value}), neighbor_count=0)
        for key in ("purchasePrereqs", "prereqs", "requiredQuest", "license", "experimentGate", "experiment"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                creative_worlds.guard_market_purchase(self.save, dict(item, **{key: "unknown"}), neighbor_count=0)
        original = cove_rules._xml
        def changed(name):
            root = original(name)
            if name == "gameSettingsCMS.xml.gz":
                root.find(".//prereq[@name='storage_world_locks']").set("type", "AND")
            return root
        cove_rules._storage_market_worlds.cache_clear()
        try:
            with mock.patch.object(cove_rules, "_xml", changed), self.assertRaisesRegex(ValueError, "prerequisite"):
                creative_worlds.guard_market_purchase(self.save, item, neighbor_count=0)
        finally:
            cove_rules._storage_market_worlds.cache_clear()

    def test_normal_cellar_purchase_costs_one_coin_once_and_survives_reload(self):
        for world in ("fisherman", "meadows"):
            with self.subTest(world=world):
                self.prepare(world)
                before = copy.deepcopy(self.save["userInfo"]["player"])
                ident = self.send("place", self.cellar())["id"]
                player = self.save["userInfo"]["player"]
                self.assertEqual(player["gold"], before["gold"] - 1)
                self.assertEqual(player["cash"], before["cash"])
                self.assertEqual(player["storageData"], before["storageData"])
                self.assertEqual(player["xp"], before["xp"])
                self.send("place", self.cellar())
                self.assertEqual(player["gold"], before["gold"] - 1)
                self.rejected("place", self.cellar(64002))
                with redirect_stdout(io.StringIO()):
                    self.player.load_saves()
                saved = next(obj for obj in self.save["world"]["objectsArray"] if obj["id"] == ident)
                self.assertEqual((saved["itemName"], saved["className"]), ("hatchstorage", "InventoryCellar"))
                self.assertEqual(self.save["userInfo"]["player"]["gold"], before["gold"] - 1)
                world_travel.switch(self.save, "farm", now=NOW)
                world_travel.switch(self.save, world, now=NOW)
                self.assertEqual(next(obj for obj in self.save["world"]["objectsArray"] if obj["id"] == ident), saved)

    def test_cellar_level_currency_and_balance_reject_without_charging(self):
        for world in ("fisherman", "meadows"):
            for level, gold, params in ((15, 1000, []), (16, 0, []),
                    (16, 1000, [{"currency": "cash"}])):
                with self.subTest(world=world, level=level, gold=gold, params=params):
                    self.prepare(world, level=level, gold=gold)
                    self.rejected("place", self.cellar(), params)

    def test_saved_cellar_cannot_be_sold_cleared_or_replaced_by_clearwithered(self):
        for world in ("farm", "england", "meadows", "fisherman"):
            with self.subTest(world=world):
                self.prepare(world)
                ident = self.send("place", self.cellar())["id"]
                saved = copy.deepcopy(next(obj for obj in self.save["world"]["objectsArray"] if obj["id"] == ident))
                # Contents are separate from the cellar's identity; deletion
                # must never discard either ledger, even for imported data.
                self.save["userInfo"]["player"]["storageData"][str(ident)] = {"HB": [2, [], []]}
                self.persist()
                for action in ("sell", "clear", "clearWithered"):
                    self.rejected(action, saved)
                    self.rejected(action, dict(saved, itemName="haybale", className="Decoration"))


if __name__ == "__main__":
    unittest.main()
