"""England's original75FC entitlement and licensed transfers over signed AMF.

All accounts, snapshots, balances and license preconditions are synthetic.
These are gateway/persistence checks; they are not original-client UI evidence.
"""
from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import england_shipping as shipping
import world_travel
import items

NOW = 1_800_000_000


class EnglandShippingWireTests(unittest.TestCase):
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

    def persist(self):
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")

    def prepare(self, *, licenses=None, cash=200, active="england"):
        self.path = self.write_fixture()
        self.save["userInfo"]["player"].update(xp=100015, gold=100000, cash=cash, storageData={})
        self.save["world"]["objectsArray"] = []
        world_travel.switch(self.save, "england", True, now=NOW)
        if active == "farm":
            world_travel.switch(self.save, "farm", now=NOW)
        self.save["world"]["objectsArray"] = [{"id": 600, "itemName": "toolshedpink",
            "className": "StorageBuilding", "state": "built", "isFullyBuilt": True,
            "contents": [], "position": {"x": 10, "y": 10, "z": 0}}]
        self.save["userInfo"]["player"]["storageData"] = {
            "-2": {"HB": [3, ["home sender"], [{"unit": 1}, {"unit": 2}, {"unit": 3}]]},
            "-8": {"HB": [1, ["England sender"], [{"England": "keep"}]]}}
        self.save["userInfo"]["unlockedWorldContentLicenses"] = copy.deepcopy(
            licenses if licenses is not None else {"oz": {"world": True, "opaque": [1]}})
        self.sequence = 0
        self.persist()

    def send(self, method, params=(), *, sequence=None, error=0):
        self.sequence += 1
        if sequence is None:
            sequence = self.sequence
        self.sequence = max(self.sequence, sequence)
        response = self.gateway([self.command(method, params, sequence)])
        return fixtures.gateway_results(self, response, [error])[0]["data"]

    def reject(self, method, params=(), **kwargs):
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.send(method, params, error=29, **kwargs)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)

    def store_packet(self, *, source=-2, destination=-8, amount=1, metadata=None):
        obj = {"id": destination, "itemName": "haybale", "className": "Decoration", "state": "static"}
        options = {"target": destination, "cameFromLocation": source, "storedItemName": "haybale",
                   "numToStore": amount, "resource": 0}
        if metadata is not None:
            options["metadata"] = metadata
        return ["store", obj, [options]]

    def test_purchase_grants_exact_original_licenses_once_with_no_stranded_consumable(self):
        self.prepare()
        before_inventory = copy.deepcopy(self.save["userInfo"]["player"]["storageData"])
        self.assertEqual(self.send("FarmService.buyConsumablePackage", [shipping.PACKAGE], sequence=40), {})
        self.assertEqual(self.save["userInfo"]["player"]["cash"], 125)
        self.assertEqual(self.save["userInfo"]["unlockedWorldContentLicenses"],
            {"farm": {"world": True}, "england": {"world": True}, "oz": {"world": True, "opaque": [1]}})
        self.assertEqual(self.save["userInfo"]["player"]["storageData"], before_inventory)
        accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.send("FarmService.buyConsumablePackage", [shipping.PACKAGE], sequence=40)
        self.assertEqual(self.save, accepted)
        self.assertEqual(self.path.read_bytes(), disk)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.save, accepted)
        self.send("FarmService.buyConsumablePackage", [shipping.PACKAGE], sequence=41)
        self.assertEqual(self.save, accepted)
        self.assertEqual(json.loads(self.path.read_text()), accepted)

    def test_unowned_insufficient_disabled_and_malformed_license_never_charge(self):
        self.prepare(cash=74)
        self.reject("FarmService.buyConsumablePackage", [shipping.PACKAGE])
        self.save["userInfo"]["player"]["cash"] = 200
        self.persist()
        with mock.patch.object(shipping, "ENABLE_PURCHASE", False):
            self.reject("FarmService.buyConsumablePackage", [shipping.PACKAGE])
        self.save["userInfo"]["unlockedWorldContentLicenses"]["farm"] = ["malformed"]
        self.persist()
        self.reject("FarmService.buyConsumablePackage", [shipping.PACKAGE])
        self.prepare(licenses={"england": {"world": True}})
        self.reject("FarmService.buyConsumablePackage", [shipping.PACKAGE])
        for licenses in ({}, {"england": {"world": True}}, {"farm": {"world": True}, "england": []}):
            self.prepare(licenses=licenses)
            self.save[shipping.REQUESTS_KEY] = {"receipts": {"40": {"package": shipping.PACKAGE, "result": {}}},
                                                "highestSequence": 40}
            self.persist()
            self.reject("FarmService.buyConsumablePackage", [shipping.PACKAGE], sequence=40)
        self.prepare(active="farm")
        self.save[world_travel.STATE_KEY]["inactive"].pop("england")
        self.persist()
        self.reject("FarmService.buyConsumablePackage", [shipping.PACKAGE])

    def test_transfer_requires_both_real_saved_licenses_and_rejects_wrong_destination(self):
        for licenses in ({}, {"england": {"world": True}}, {"farm": {"world": True}}):
            with self.subTest(licenses=licenses):
                self.prepare(licenses=licenses)
                self.reject("WorldService.performAction", self.store_packet())
        self.prepare(licenses={"farm": {"world": True}, "england": {"world": True}})
        self.reject("WorldService.performAction", self.store_packet(source=-9))
        self.reject("WorldService.performAction", self.store_packet(destination=-2))

    def test_signed_inventory_transfer_preserves_unit_metadata_and_replays_once(self):
        self.prepare(licenses={"farm": {"world": True}, "england": {"world": True}})
        objects = copy.deepcopy(self.save["world"]["objectsArray"])
        raw = self.store_packet(source="-2", metadata={"forged": "ignored"})
        raw[1]["tempId"] = float("nan")
        self.send("WorldService.performAction", raw, sequence=40)
        ledger = self.save["userInfo"]["player"]["storageData"]
        self.assertEqual(ledger["-2"]["HB"], [2, [], [{"unit": 2}, {"unit": 3}]])
        self.assertEqual(ledger["-8"]["HB"][0], 2)
        self.assertEqual(ledger["-8"]["HB"][2], [{"England": "keep"}, {"unit": 1}])
        self.assertEqual(self.save["world"]["objectsArray"], objects)
        accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
        for reload in (False, True):
            if reload:
                with redirect_stdout(io.StringIO()):
                    self.player.load_saves()
            self.send("WorldService.performAction", raw, sequence=40)
            self.assertEqual(self.save, accepted)
            self.assertEqual(self.path.read_bytes(), disk)
        self.reject("WorldService.performAction", self.store_packet(amount=2), sequence=40)

    def test_full_destination_and_overdraw_are_atomic_and_recovery_can_withdraw_overflow(self):
        self.prepare(licenses={"farm": {"world": True}, "england": {"world": True}})
        self.save["userInfo"]["player"]["storageData"]["-8"]["HB"] = [15, [], [{"overflow": "keep"}]]
        self.persist()
        self.reject("WorldService.performAction", self.store_packet())
        self.save["userInfo"]["player"]["storageData"]["-8"]["HB"][0] = 1
        self.persist()
        self.reject("WorldService.performAction", self.store_packet(amount=4))
        # Imported overflowing Home inventory remains removable. No capacity
        # repair or truncation is allowed merely to make shipping available.
        self.save["userInfo"]["player"]["storageData"]["-2"]["HB"] = [1300, [], [{"overflow": "retain"}]]
        self.persist()
        self.send("WorldService.performAction", self.store_packet())
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-2"]["HB"][0], 1299)

    def test_imported_entitlement_other_types_and_home_roundtrip_are_preserved(self):
        licenses = {"farm": {"world": 0, "opaque": {"keep": [1]}},
                    "england": {"world": False, "other": 7}, "glen": {"world": True}}
        self.prepare(licenses=licenses)
        self.send("FarmService.buyConsumablePackage", [shipping.PACKAGE])
        self.assertEqual(self.save["userInfo"]["player"]["cash"], 200)
        self.assertEqual(self.save["userInfo"]["unlockedWorldContentLicenses"], licenses)
        self.assertTrue(shipping.guard_transfer(self.save, -2))
        world_travel.switch(self.save, "farm", now=NOW + 1)
        self.assertTrue(shipping.guard_transfer(self.save, -8))
        world_travel.switch(self.save, "england", now=NOW + 2)
        self.assertEqual(self.save["userInfo"]["unlockedWorldContentLicenses"], licenses)
        self.persist()
        initialized = self.send("UserService.initUser", ["Synthetic shipping", 0, True, None])
        self.assertEqual(initialized["userInfo"]["unlockedWorldContentLicenses"], licenses)
        self.assertNotIn(shipping.REQUESTS_KEY, initialized)
        self.assertNotIn(shipping.TRANSFER_REQUESTS_KEY, initialized)


if __name__ == "__main__":
    unittest.main()
