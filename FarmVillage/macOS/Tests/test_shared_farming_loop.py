"""Original retained-crop farming loops across every enabled world; disposable AMF."""
import copy
import io
import math
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import test_cove_cellar as shared
import items
import peaceful

NOW = 1800000000
WORLDS = ("farm", "england", "meadows", "fisherman")


class SharedFarmingLoopTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway
    save = shared.CoveCellarTests.save
    prepare = shared.CoveCellarTests.prepare
    persist = shared.CoveCellarTests.persist

    def send(self, function, params, now, *, sequence=None):
        if sequence is None:
            sequence = getattr(self, "_wire_sequence", 0) + 1
        self._wire_sequence = max(getattr(self, "_wire_sequence", 0), sequence)
        with mock.patch("commands.timestamp_now", return_value=now), mock.patch(
                "engine.timestamp_now", return_value=now), mock.patch("server.timestamp_now", return_value=now):
            response = self.gateway([self.command(function, params, sequence)])
        return fixtures.gateway_results(self, response, [0])[0]["data"]

    def action(self, name, snapshot, now, *, sequence=None):
        return self.send("WorldService.performAction", [name, snapshot, []], now, sequence=sequence)

    def cycle(self, world, *, vehicle=False, clear_clock=False):
        self.prepare(world, gold=1000000)
        inactive = copy.deepcopy(self.save.get("_ownedWorldTravel", {}).get("inactive"))
        self.save["craftingState"]["unknownQueue"] = [{"preserve": "Bakery clock"}]
        self.persist()
        before = self.save["userInfo"]["player"]["gold"]
        crop = {"id": 64001, "className": "Plot", "itemName": None, "state": "plowed",
                "position": {"x": 12, "y": 12, "z": 0}, "plantTime": 0}
        crop["id"] = self.action("plow", crop, NOW, sequence=1)["id"]
        crop.update(itemName="strawberry", state="planted", plantTime=NOW * 1000)
        self.action("place", crop, NOW, sequence=2)
        item = items.get_item_by_name("strawberry")
        ready = NOW + math.ceil(peaceful.grow_seconds(item))
        fallow = dict(crop, state="fallow")
        self.action("harvest", fallow, ready, sequence=3)
        self.action("harvest", fallow, ready, sequence=3)
        replowed = dict(fallow, state="plowed")
        if clear_clock:
            # Observed original packet after paid Instant Grow, reload and harvest.
            replowed.update(plantTime=0, tempId=float("nan"))
        if vehicle:
            for _ in range(2):
                self.send("EquipmentWorldService.onUseEquipment", ["plow", {"id": 999},
                    [{"id": crop["id"], "position": crop["position"]}], None], ready, sequence=4)
        else:
            self.action("plow", replowed, ready, sequence=4)
            self.action("plow", replowed, ready, sequence=4)
        saved = next(obj for obj in self.save["world"]["objectsArray"] if obj["id"] == crop["id"])
        self.assertEqual((saved["state"], saved["itemName"], saved["plantTime"]),
                         ("plowed", "strawberry", 0 if clear_clock else NOW * 1000))
        self.assertEqual(self.save["userInfo"]["player"]["gold"],
                         before - 30 - int(item["cost"]) + int(item["coinYield"]))
        self.action("place", dict(crop, plantTime=1), ready, sequence=5)
        saved = next(obj for obj in self.save["world"]["objectsArray"] if obj["id"] == crop["id"])
        self.assertEqual(saved["plantTime"], ready * 1000)
        final = copy.deepcopy(saved)
        final.pop("tempId", None)  # Session-only transport aliases are intentionally not persisted.
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(next(obj for obj in self.save["world"]["objectsArray"] if obj["id"] == crop["id"]), final)
        self.assertEqual(self.save.get("_ownedWorldTravel", {}).get("inactive"), inactive)
        self.assertEqual(self.save["craftingState"]["unknownQueue"], [{"preserve": "Bakery clock"}])

    def test_original_plow_plant_harvest_replow_replant_retry_reload_all_worlds(self):
        for world in WORLDS:
            with self.subTest(world=world):
                self.cycle(world)

    def test_vehicle_replow_retains_crop_and_charges_once_all_worlds(self):
        for world in WORLDS:
            with self.subTest(world=world):
                self.cycle(world, vehicle=True)

    def test_cleared_clock_replow_retry_and_replant_all_worlds(self):
        for world in WORLDS:
            with self.subTest(world=world):
                self.cycle(world, clear_clock=True)


if __name__ == "__main__":
    unittest.main()
