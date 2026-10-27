"""Vehicle response contracts that the shipped Ruffle AMF0 reader can consume."""

from pathlib import Path
import sys
import unittest
from unittest import mock

from pyamf import remoting

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures


class EquipmentWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    def check_vehicle_metadata(self, action):
        self.write_fixture()
        description = "fixture quest " * 1024
        quests = [{"code": "fixture-quest", "status": "active", "description": description}]
        with mock.patch.object(self.server.commands, "quest_component", return_value=quests):
            response = self.gateway([self.command("EquipmentWorldService.onUseEquipment", [
                action, {"id": 999}, [{"id": 4}, {"id": 5}], "eggplant",
            ])])
        self.assertEqual(response.status_code, 200)
        outer = remoting.decode(response.data).bodies[0][1].body["data"][0]
        groups = outer["data"].values() if action == "combine" else ({"data": outer["data"]},)
        children = [child for group in groups for child in group["data"] if child is not None]
        self.assertEqual(len(children), 6 if action == "combine" else 2)
        self.assertEqual(outer["metadata"]["QuestComponent"], quests)
        for child in children:
            self.assertEqual(child["metadata"], {})
            self.assertEqual(child["errorType"], 0)
        # AMF0 marker 07 is a reference. The shipped Ruffle deserializer maps
        # this marker to Undefined, although PyAMF resolves it transparently.
        # Check the actual bytes so a Python-only round trip cannot hide it.
        self.assertNotIn(b"\x00\x08metadata\x07", response.data)
        self.assertEqual(response.data.count(b"\x00\x08metadata\x03"), len(children) + 1)
        self.assertEqual(response.data.count(description.encode()), 1)

        # Recovered TEquipmentAction calls onAmfComplete for each child in this
        # order. TFarmTransaction preserves the previous rawResult's quests and
        # action drops, then restores them on the new rawResult after dispatch.
        outer["metadata"]["ActionDrops"] = {"fixture": "drop"}
        previous = outer
        for child in children:
            metadata = previous["metadata"]
            previous = child
            for key in ("QuestComponent", "ActionDrops"):
                if key in metadata:
                    child["metadata"][key] = metadata[key]
        self.assertEqual(previous["metadata"]["QuestComponent"], quests)
        self.assertEqual(previous["metadata"]["ActionDrops"], {"fixture": "drop"})

    def test_two_plot_harvest_keeps_compact_metadata_for_client_propagation(self):
        self.check_vehicle_metadata("harvest")

    def test_combine_keeps_compact_metadata_through_all_three_passes(self):
        self.check_vehicle_metadata("combine")


if __name__ == "__main__":
    unittest.main()
