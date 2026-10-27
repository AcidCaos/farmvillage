"""Independent regressions for concrete owned-world review findings."""
import copy
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence  # Writable-path isolation must precede all product imports.
import test_world_travel as travel_fixtures
from items import get_item_by_name
import storage


class WorldTravelReviewTests(unittest.TestCase):
    setUpClass = classmethod(travel_fixtures.WorldTravelTests.setUpClass.__func__)
    setUp = travel_fixtures.WorldTravelTests.setUp
    fixture = travel_fixtures.WorldTravelTests.fixture
    write_fixture = travel_fixtures.WorldTravelTests.write_fixture
    command = staticmethod(travel_fixtures.WorldTravelTests.command)
    gateway = travel_fixtures.WorldTravelTests.gateway
    gateway_payload = travel_fixtures.WorldTravelTests.gateway_payload
    prepare = travel_fixtures.WorldTravelTests.prepare
    send = travel_fixtures.WorldTravelTests.send

    def test_foreign_imported_inventory_cannot_be_withdrawn_in_england(self):
        self.prepare()
        self.send(["england", True])
        save = self.player.session("fixture-farmer")
        code = get_item_by_name("cow")["code"]
        for foreign in (-9, -10, -999):
            with self.subTest(foreign=foreign):
                save["userInfo"]["player"]["storageData"][str(foreign)] = {code: [1, [], []]}
                before = copy.deepcopy(save)
                with self.assertRaises(ValueError):
                    storage.withdraw_for_placement(save, "cow", [{"isStorageWithdrawal": foreign}],
                        {"id": 64001, "itemName": "cow", "className": "Animal"})
                self.assertEqual(save, before)

    def test_caller_permanent_id_cannot_reuse_an_orphan_storage_ledger(self):
        self.prepare()
        self.send(["england", True])
        save = self.player.session("fixture-farmer")
        code = get_item_by_name("cow")["code"]
        save["userInfo"]["player"]["storageData"]["70000"] = {code: [1, [], []]}
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")
        original = self.path.read_bytes()
        for action, name, kind in (("plow", None, "Plot"), ("place", "cow", "Animal")):
            with self.subTest(action=action):
                snapshot = {"id": 70000, "className": kind, "itemName": name,
                            "state": "plowed" if action == "plow" else "grown",
                            "position": {"x": 10, "y": 10, "z": 0}}
                response = self.gateway([self.command("WorldService.performAction", [action, snapshot, []])])
                test_persistence.assert_gateway_rejected(self, response)
                self.assertEqual(self.path.read_bytes(), original)
                active = self.player.session("fixture-farmer")
                self.assertEqual(active["world"]["objectsArray"], [])
                self.assertEqual(active["userInfo"]["player"]["storageData"]["70000"], {code: [1, [], []]})

    def test_existing_permanent_id_plow_retry_remains_valid_without_payment(self):
        self.prepare()
        self.send(["england", True])
        snapshot = {"id": 64001, "className": "Plot", "itemName": None,
                    "state": "plowed", "position": {"x": 10, "y": 10, "z": 0}}
        self.assertEqual(self.gateway([self.command("WorldService.performAction", ["plow", snapshot, []])]).status_code, 200)
        save = self.player.session("fixture-farmer")
        permanent = copy.deepcopy(save["world"]["objectsArray"][0])
        before = (save["userInfo"]["player"]["gold"], save["userInfo"]["player"]["xp"])
        self.assertEqual(self.gateway([self.command("WorldService.performAction", ["plow", permanent, []])]).status_code, 200)
        save = self.player.session("fixture-farmer")
        self.assertEqual(len(save["world"]["objectsArray"]), 1)
        self.assertEqual((save["userInfo"]["player"]["gold"], save["userInfo"]["player"]["xp"]), before)


if __name__ == "__main__":
    unittest.main()
