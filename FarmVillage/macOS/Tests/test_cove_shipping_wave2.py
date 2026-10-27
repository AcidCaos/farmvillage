"""Synthetic signed-AMF acceptance of Cove licenses and inventory shipping."""
import copy
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import cove_shipping
import creative_worlds
import items
import storage
import world_travel

NOW = 1800000000


class CoveShippingWave2Tests(unittest.TestCase):
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

    @property
    def player_state(self):
        return self.save["userInfo"]["player"]

    def persist(self):
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")

    def prepare(self, *, unlocked=True, active="fisherman", cash=100):
        from game_settings import level_to_xp
        self.path = self.write_fixture()
        self.player_state.update(xp=level_to_xp(20), cash=cash, gold=10000)
        if unlocked:
            creative_worlds.create(self.save, "fisherman", "allAccess", now=NOW)
            world_travel.switch(self.save, "fisherman", now=NOW)
            # Fully built imported storage is an explicit capacity precondition.
            self.save["world"]["objectsArray"].append({"id": 7002, "className": "StorageBuilding",
                "itemName": "barn", "isFullyBuilt": True, "state": "built",
                "position": {"x": 4, "y": 4, "z": 0}, "contents": []})
        self.player_state["storageData"]["-2"] = {}
        if active != self.save["userInfo"].get("currentWorldType"):
            world_travel.switch(self.save, active, now=NOW)
        # Settle rewards caused by the seeded second storage building before
        # measuring a shipping transaction's own balance changes.
        import progression
        progression.refresh_owned(self.save)
        progression.take_response(self.save)
        self.seq = 0
        self.persist()

    def send(self, name, params, *, expected=200, sequence=None):
        if sequence is None:
            self.seq += 1
            sequence = self.seq
        with mock.patch("server.timestamp_now", return_value=NOW), mock.patch(
                "commands.timestamp_now", return_value=NOW), mock.patch("engine.timestamp_now", return_value=NOW):
            result = self.gateway([self.command(name, params, sequence)])
        fixtures.assert_gateway_status(self, result, expected)
        if expected == 200:
            from pyamf import remoting
            return remoting.decode(result.data).bodies[0][1].body["data"][0]["data"]

    def rejected(self, name, params):
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.send(name, params, expected=400)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)

    def buy(self, **kwargs):
        return self.send("FarmService.buyConsumablePackage", [cove_shipping.PACKAGE], **kwargs)

    def licenses(self, *worlds):
        self.save["userInfo"]["unlockedWorldContentLicenses"] = {name: {"world": True} for name in worlds}

    def shipping_payload(self, source=-2, target=-9, quantity=1, **changes):
        options = {"storedItemName": "haybale", "cameFromLocation": source,
                   "target": target, "resource": 0, "numToStore": quantity}
        options.update(changes)
        return ["store", {"id": target, "className": "StorageBuilding"}, [options]]

    def consume_payload(self, *, count=1, group=-1):
        return ["use", {"id": 65102, "className": "CRewardConsumable",
                        "itemName": cove_shipping.CONSUMABLE}, [{"storageId": group, "itemCount": count}]]

    def test_exact_package_and_signed_buy_applies_75fc_license_immediately_without_gift(self):
        self.prepare()
        self.assertEqual(cove_shipping.contract(), {"cash": 75, "world": "fisherman", "licenseType": "world"})
        before = copy.deepcopy(self.player_state)
        self.assertEqual(self.buy(), {})
        self.assertEqual(self.player_state["cash"], 25)
        for field in ("gold", "xp", "storageData"):
            self.assertEqual(self.player_state[field], before[field])
        self.assertEqual(self.save["userInfo"]["unlockedWorldContentLicenses"], {"fisherman": {"world": True}})
        self.assertNotIn("06x", self.player_state["storageData"]["-1"])

    def test_buy_is_permanently_repeat_free_and_survives_reload_restart(self):
        self.prepare()
        self.buy(sequence=10)
        self.buy(sequence=10)
        self.buy(sequence=11)
        self.assertEqual(self.player_state["cash"], 25)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.buy(sequence=1)
        self.assertEqual(self.player_state["cash"], 25)
        self.assertTrue(cove_shipping.licensed(self.save, "fisherman"))

    def test_locked_cove_and_insufficient_funds_refuse_without_state_or_disk_change(self):
        self.prepare(cash=74)
        self.rejected("FarmService.buyConsumablePackage", [cove_shipping.PACKAGE])
        self.prepare(unlocked=False, active="farm")
        self.rejected("FarmService.buyConsumablePackage", [cove_shipping.PACKAGE])

    def test_owned_gift_use_is_signed_once_and_existing_license_preserves_spare_gift(self):
        self.prepare()
        self.player_state["storageData"]["-1"]["06x"] = [2, ["port"], [{"award": 1}, {"award": 2}]]
        self.persist()
        self.send("WorldService.performAction", self.consume_payload())
        self.assertTrue(cove_shipping.licensed(self.save, "fisherman"))
        self.assertEqual(self.player_state["storageData"]["-1"]["06x"][0], 1)
        self.assertEqual(self.player_state["cash"], 100)
        self.rejected("WorldService.performAction", self.consume_payload())
        self.assertEqual(self.player_state["storageData"]["-1"]["06x"][0], 1)

    def test_missing_or_multiple_license_gifts_refuse_before_withdrawal(self):
        self.prepare()
        self.rejected("WorldService.performAction", self.consume_payload())
        self.player_state["storageData"]["-1"]["06x"] = [2, [], []]
        self.persist()
        self.rejected("WorldService.performAction", self.consume_payload(count=2))

    def test_source_license_alone_does_not_enable_shipping_into_cove(self):
        self.prepare()
        self.player_state["storageData"]["-2"]["HB"] = [2, [], []]
        for license_worlds in ((), ("farm",), ("fisherman",)):
            with self.subTest(license_worlds=license_worlds):
                self.licenses(*license_worlds)
                self.persist()
                self.rejected("WorldService.performAction", self.shipping_payload())

    def test_home_to_cove_signed_shipping_preserves_quantity_extra_order_and_retry(self):
        self.prepare()
        self.licenses("farm", "fisherman")
        self.player_state["storageData"]["-2"]["HB"] = [4, ["one", "two"], [{"unit": 1}, {"unit": 2}, {"unit": 3}]]
        self.player_state["storageData"]["-9"]["HB"] = [1, [], [{"unit": 0}]]
        self.persist()
        payload = self.shipping_payload(quantity=3, metadata={"forged": True})
        before_money = self.player_state["cash"], self.player_state["gold"]
        self.send("WorldService.performAction", payload, sequence=20)
        self.assertEqual(self.player_state["storageData"]["-2"]["HB"], [1, ["two"], [{"unit": 3}]])
        self.assertEqual(self.player_state["storageData"]["-9"]["HB"], [4, ["one"], [{"unit": 0}, {"unit": 1}, {"unit": 2}]])
        self.assertEqual((self.player_state["cash"], self.player_state["gold"]), before_money)
        settled = copy.deepcopy(self.save)
        self.send("WorldService.performAction", payload, sequence=20)
        self.assertEqual(self.save, settled)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.send("WorldService.performAction", payload, sequence=20)
        self.assertEqual(self.player_state["storageData"], settled["userInfo"]["player"]["storageData"])
        self.rejected("WorldService.performAction", self.shipping_payload(quantity=2))

    def test_cove_to_home_signed_shipping_and_home_cove_travel_preserve_state(self):
        self.prepare()
        self.licenses("farm", "fisherman")
        self.player_state["storageData"]["-9"]["HB"] = [2, [], [{"unit": "CoveA"}, {"unit": "CoveB"}]]
        world_travel.switch(self.save, "farm", now=NOW)
        self.persist()
        self.send("WorldService.performAction", self.shipping_payload(source=-9, target=-2, quantity=2))
        self.assertNotIn("HB", self.player_state["storageData"]["-9"])
        self.assertEqual(self.player_state["storageData"]["-2"]["HB"], [2, [], [{"unit": "CoveA"}, {"unit": "CoveB"}]])
        world_travel.switch(self.save, "fisherman", now=NOW)
        world_travel.switch(self.save, "farm", now=NOW)
        self.assertEqual(self.player_state["storageData"]["-2"]["HB"][0], 2)

    def test_full_capacity_and_imported_overflow_refuse_without_source_loss(self):
        self.prepare()
        self.licenses("farm", "fisherman")
        self.player_state["storageData"]["-2"]["HB"] = [2, [], []]
        cap = int(items.get_item_by_name("barn")["capacity"])
        for count in (cap, cap + 1):
            with self.subTest(count=count):
                self.player_state["storageData"]["-9"]["HB"] = [count, [], []]
                self.persist()
                self.rejected("WorldService.performAction", self.shipping_payload())

    def test_imported_source_overflow_can_be_recovered_into_real_destination_capacity(self):
        self.prepare()
        self.licenses("farm", "fisherman")
        cap = int(items.get_item_by_name("barn")["capacity"])
        self.player_state["storageData"]["-2"]["HB"] = [cap + 1, [], [{"sparse": "retain"}]]
        self.persist()
        self.send("WorldService.performAction", self.shipping_payload(quantity=2))
        self.assertEqual(self.player_state["storageData"]["-2"]["HB"], [cap - 1, [], [{"sparse": "retain"}]])
        self.assertEqual(self.player_state["storageData"]["-9"]["HB"], [2, [], []])

    def test_malformed_source_metadata_refuses_without_replacement_or_withdrawal(self):
        self.prepare()
        self.licenses("farm", "fisherman")
        self.player_state["storageData"]["-2"]["HB"] = [1, [], [{"unit": 1}, {"unit": 2}]]
        self.persist()
        self.rejected("WorldService.performAction", self.shipping_payload())
        # Four-field entries are rejected by the save loader itself. Exercise
        # the direct transaction boundary without pretending it is loadable.
        self.player_state["storageData"]["-2"]["HB"] = [1, [], [], {"unknown": "preserve"}]
        before = copy.deepcopy(self.save)
        payload = self.shipping_payload()
        with self.assertRaises(ValueError):
            storage.store_world_item(self.save, payload[1], payload[2][0], request_id=100)
        self.assertEqual(self.save, before)

    def test_unknown_nonowned_and_other_world_pair_sources_refuse_direct_and_signed(self):
        self.prepare()
        self.licenses("farm", "fisherman", "england")
        for source in (-999, -8):
            with self.subTest(source=source):
                self.rejected("WorldService.performAction", self.shipping_payload(source=source))
        world_travel.switch(self.save, "farm", now=NOW)
        before = copy.deepcopy(self.save)
        with self.assertRaises(ValueError):
            cove_shipping.guard_source(self.save, -8)
        self.assertEqual(self.save, before)

    def test_wrong_target_ambiguous_source_and_changed_sequence_are_atomic(self):
        self.prepare()
        self.licenses("farm", "fisherman")
        self.player_state["storageData"]["-2"]["HB"] = [4, [], []]
        self.persist()
        self.rejected("WorldService.performAction", self.shipping_payload(target=-8))
        self.rejected("WorldService.performAction", self.shipping_payload(origin=-8))
        self.rejected("WorldService.performAction", self.shipping_payload(isGift=True))
        self.send("WorldService.performAction", self.shipping_payload(), sequence=30)
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.send("WorldService.performAction", self.shipping_payload(quantity=2), sequence=30, expected=400)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)


if __name__ == "__main__":
    unittest.main()
