"""Independent W02 review: shipping imports, IDs, receipt and placement edges."""
from contextlib import redirect_stdout
import copy
import io
import json
from unittest import mock
import unittest

import test_wave2_england_shipping as wire
import england_shipping as shipping
import items
import pyamf
import storage


class EnglandShippingReviewTests(unittest.TestCase):
    setUpClass = classmethod(wire.EnglandShippingWireTests.setUpClass.__func__)
    setUp = wire.EnglandShippingWireTests.setUp
    fixture = wire.EnglandShippingWireTests.fixture
    write_fixture = wire.EnglandShippingWireTests.write_fixture
    command = staticmethod(wire.EnglandShippingWireTests.command)
    gateway_payload = wire.EnglandShippingWireTests.gateway_payload
    gateway = wire.EnglandShippingWireTests.gateway
    save = wire.EnglandShippingWireTests.save
    persist = wire.EnglandShippingWireTests.persist
    prepare = wire.EnglandShippingWireTests.prepare
    send = wire.EnglandShippingWireTests.send
    reject = wire.EnglandShippingWireTests.reject
    store_packet = wire.EnglandShippingWireTests.store_packet

    def licensed(self):
        self.prepare(licenses={"farm": {"world": True}, "england": {"world": True}})

    def test_legacy_import_without_retained_home_snapshot_cannot_ship_or_place_foreign_units(self):
        self.licensed()
        self.save.pop("_ownedWorldTravel")
        self.persist()
        for packet in (self.store_packet(), self.placement()):
            with self.subTest(action=packet[0]):
                self.reject("WorldService.performAction", copy.deepcopy(packet))
        self.save["userInfo"]["worldSummaryData"]["england"]["storageId"] = -2
        self.persist()
        self.reject("WorldService.performAction", copy.deepcopy(self.placement()))

    def test_numeric_text_source_uses_shipping_receipts_through_disk_restart(self):
        self.licensed()
        packet = self.store_packet(source="-2", destination=-8)
        packet[2][0]["target"] = "-8"
        self.assertTrue(shipping.is_transfer_request(self.save, *packet))
        self.send("WorldService.performAction", copy.deepcopy(packet), sequence=40)
        accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
        for restart in (False, True):
            if restart:
                with redirect_stdout(io.StringIO()):
                    self.player.load_saves()
            self.send("WorldService.performAction", copy.deepcopy(packet), sequence=40)
            self.assertEqual(self.save, accepted)
            self.assertEqual(self.path.read_bytes(), disk)

    def test_undefined_gift_flag_cannot_bypass_transfer_retry_wrapper(self):
        self.licensed()
        packet = self.store_packet()
        packet[2][0]["isGift"] = pyamf.Undefined
        self.assertTrue(shipping.is_transfer_request(self.save, *packet))
        self.send("WorldService.performAction", copy.deepcopy(packet), sequence=40)
        accepted = copy.deepcopy(self.save)
        self.send("WorldService.performAction", copy.deepcopy(packet), sequence=40)
        self.assertEqual(self.save, accepted)

    def test_fractional_and_malformed_shipping_ids_refuse_without_debit(self):
        self.licensed()
        for field, value in (("cameFromLocation", -2.5), ("cameFromLocation", "-2.5"),
                             ("cameFromLocation", "--2"), ("cameFromLocation", True),
                             ("target", -8.5), ("target", "-8.5"),
                             ("target", True), ("resource", 600.5),
                             ("resource", "600.5")):
            with self.subTest(field=field, value=value):
                packet = self.store_packet()
                packet[2][0][field] = value
                self.reject("WorldService.performAction", packet)
        packet = self.store_packet()
        packet[2][0]["origin"] = -8
        self.reject("WorldService.performAction", packet)

    @staticmethod
    def placement():
        return ["place", {"id": 64001, "itemName": "haybale", "className": "Decoration",
            "state": "static", "position": {"x": 15, "y": 15, "z": 0},
            "metadata": {"forged": "snapshot"}}, [{"isInventoryWithdrawal": True,
            "isStorageWithdrawal": -2, "metadata": {"forged": "options"}}]]

    def test_foreign_inventory_placement_keeps_source_metadata_and_imported_clock(self):
        self.licensed()
        metadata = {"name": "Imported unit", "clock": 1234567890000,
                    "opaque": {"keep": [1, "two"]}}
        self.save["userInfo"]["player"]["storageData"]["-2"]["HB"][2][0] = metadata
        self.persist()
        packet = self.placement()
        result = self.send("WorldService.performAction", copy.deepcopy(packet), sequence=40)
        placed = next(obj for obj in self.save["world"]["objectsArray"] if obj["id"] == result["id"])
        self.assertEqual(placed["metadata"], metadata)
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-2"]["HB"][2],
                         [{"unit": 2}, {"unit": 3}])
        accepted = copy.deepcopy(self.save)
        self.send("WorldService.performAction", copy.deepcopy(packet), sequence=40)
        self.assertEqual(self.save, accepted)
        persisted = json.loads(self.path.read_text())
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.save, persisted)
        self.send("WorldService.performAction", copy.deepcopy(packet), sequence=40)
        self.assertEqual(self.save, persisted)

    def test_sparse_source_metadata_does_not_adopt_forged_placement_metadata(self):
        self.licensed()
        self.save["userInfo"]["player"]["storageData"]["-2"]["HB"][2] = []
        self.persist()
        result = self.send("WorldService.performAction", self.placement(), sequence=40)
        placed = next(obj for obj in self.save["world"]["objectsArray"] if obj["id"] == result["id"])
        self.assertNotIn("metadata", placed)

    def test_receipt_signature_survives_callback_input_mutation_and_rejects_bad_import(self):
        self.licensed()
        packet = self.store_packet()
        original = copy.deepcopy(packet)
        def callback():
            packet[1]["id"] = 9999
            packet[2][0]["metadata"] = {"mutated": True}
            return -8
        self.assertEqual(shipping.dispatch_world(self.save, *packet, 40, callback), -8)
        self.assertEqual(shipping.dispatch_world(self.save, *original, 40,
            mock.Mock(side_effect=AssertionError("replay ran callback"))), -8)
        before = copy.deepcopy(self.save)
        self.save[shipping.TRANSFER_REQUESTS_KEY]["receipts"]["40"]["result"] = True
        malformed = copy.deepcopy(self.save)
        with self.assertRaises(ValueError):
            shipping.dispatch_world(self.save, *original, 40, lambda: -8)
        self.assertEqual(self.save, malformed)
        self.save.clear(); self.save.update(before)

    def test_new_client_session_resets_sequence_while_imports_and_entitlements_persist(self):
        self.licensed()
        self.send("WorldService.performAction", self.store_packet(), sequence=40)
        first = copy.deepcopy(self.save["userInfo"]["player"]["storageData"])
        self.send("UserService.initUser", ["Synthetic shipping review", 0, True, None], sequence=1)
        self.assertEqual(self.save["userInfo"]["player"]["storageData"], first)
        self.assertNotIn(shipping.TRANSFER_REQUESTS_KEY, self.save)
        # A newly initialized Flash document starts its sequence counter again;
        # this is a new intentional action, not a retry across the new session.
        self.send("WorldService.performAction", self.store_packet(amount=2), sequence=40)
        self.assertNotIn("HB", self.save["userInfo"]["player"]["storageData"]["-2"])
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-8"]["HB"][0], 4)
        self.assertEqual(self.save["userInfo"]["unlockedWorldContentLicenses"],
                         {"farm": {"world": True}, "england": {"world": True}})

    def test_shipping_into_english_stable_preserves_unit_metadata_and_building_clock(self):
        self.licensed()
        stable = {"id": 601, "itemName": "xukhorsestable_finished",
            "className": "HorseStableBuildingFinished", "state": "built",
            "isFullyBuilt": True, "capacity": 20, "expansionLevel": 1,
            "contents": [], "plantTime": 1600000000000,
            "position": {"x": 20, "y": 20, "z": 0}}
        self.save["world"]["objectsArray"].append(stable)
        horse = items.get_item_by_name("horse_black")
        metadata = [{"name": "Imported horse", "clock": 1234567890000}, {"variant": "retained"}]
        self.save["userInfo"]["player"]["storageData"]["-2"][horse["code"]] = [2, ["sender"], metadata]
        self.persist()
        packet = ["store", copy.deepcopy(stable), [{"target": 601, "cameFromLocation": -2,
            "storedItemName": "horse_black", "numToStore": 1, "resource": 0,
            "metadata": {"forged": True}}]]
        self.send("WorldService.performAction", copy.deepcopy(packet), sequence=40)
        ledger = self.save["userInfo"]["player"]["storageData"]
        self.assertEqual(ledger["601"][horse["code"]], [1, ["sender"], metadata[:1]])
        self.assertEqual(ledger["-2"][horse["code"]], [1, [], metadata[1:]])
        owned = next(obj for obj in self.save["world"]["objectsArray"] if obj["id"] == 601)
        self.assertEqual(owned["plantTime"], stable["plantTime"])
        self.assertEqual(owned["capacity"], 20)
        accepted = copy.deepcopy(self.save)
        self.send("WorldService.performAction", copy.deepcopy(packet), sequence=40)
        self.assertEqual(self.save, accepted)

    def test_failed_direct_transfer_callback_restores_source_and_retry_history(self):
        self.licensed()
        packet = self.store_packet(destination=9999)
        before = copy.deepcopy(self.save)
        def callback():
            storage.store_world_item(self.save, packet[1], packet[2][0])
            return 9999
        with self.assertRaises(ValueError):
            shipping.dispatch_world(self.save, *packet, 40, callback)
        self.assertEqual(self.save, before)

    def test_ambiguous_surplus_imported_metadata_refuses_before_withdrawal(self):
        for place in (False, True):
            with self.subTest(place=place):
                self.licensed()
                self.save["userInfo"]["player"]["storageData"]["-2"]["HB"] = [1, [],
                    [{"name": "Imported unit"}, {"opaque": "unresolved surplus"}]]
                self.persist()
                packet = self.placement() if place else self.store_packet()
                self.reject("WorldService.performAction", packet)


if __name__ == "__main__":
    unittest.main()
