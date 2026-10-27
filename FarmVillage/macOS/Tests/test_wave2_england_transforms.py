"""Five exact classic cash growth contracts on England's signed gateway.

Babies and imported metadata are synthetic owned preconditions. No production
or growth clocks are accelerated, and no Nursery random birth is inferred.
"""
from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import test_wave2_england_depth as depth
import england_animals as animals
import creative_worlds
import world_travel

NOW = 1_800_000_000


class EnglandTransformsWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway
    save = depth.EnglandDepthWireTests.save
    obj = depth.EnglandDepthWireTests.obj
    persist = depth.EnglandDepthWireTests.persist
    rpc = depth.EnglandDepthWireTests.rpc
    assert_home = depth.EnglandDepthWireTests.assert_home

    def prepare(self, name="foal_gray"):
        depth.EnglandDepthWireTests.prepare(self, name)
        self.obj.update(metadata=json.dumps({"name": "Preserved Nursery Baby", "DNA": [1, {"keep": 2}]}),
                        persistentDataKey="imported-baby", petName="Opaque retained name",
                        mutableAnimalState={"imported": {"name": "Retained DNA", "alleles": [1, 2]}})
        self.persist()
        self.original = copy.deepcopy(self.obj)

    def transform(self, snapshot=None, *, sequence=None, error=0):
        from unittest import mock
        with mock.patch.object(self.server.commands, "timestamp_now", return_value=NOW):
            return self.rpc("WorldService.performAction", ["transform",
                copy.deepcopy(self.obj) if snapshot is None else snapshot, [{"firstWA": True}]],
                sequence=sequence, error=error)

    def reject(self, snapshot=None, **kwargs):
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.transform(snapshot, error=29, **kwargs)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)

    def test_all_five_exact_babies_grow_on_england_at_original_prices_with_owned_metadata(self):
        for name, (_, adult, cost) in animals.TRANSFORMS.items():
            with self.subTest(name=name):
                self.prepare(name)
                raw = {**copy.deepcopy(self.obj), "plantTime": 0, "metadata": {"forged": "ignored"},
                       "persistentDataKey": "forged", "mutableAnimalState": {"forged": True}}
                reply = self.transform(raw)
                self.assertEqual(reply, {"id": 600, "adultId": 600,
                    "adultMetadata": self.original["metadata"], "rewardLink": None})
                self.assertEqual((self.obj["itemName"], self.obj["className"], self.obj["state"], self.obj["plantTime"]),
                                 (adult, "Animal", "bare", NOW * 1000))
                self.assertEqual(self.save["userInfo"]["player"]["cash"], 2500 - cost)
                self.assertEqual(self.save["userInfo"]["player"]["gold"], 100_000_000)
                for field in ("id", "position", "metadata", "mutableAnimalState", "persistentDataKey", "petName", "importedBuilding"):
                    self.assertEqual(self.obj[field], self.original[field])
                self.assert_home()

    def test_same_signed_request_retries_before_and_after_reload_without_recharge(self):
        self.prepare()
        raw = copy.deepcopy(self.obj)
        reply = self.transform(raw, sequence=40)
        accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
        for reload in (False, True):
            if reload:
                with redirect_stdout(io.StringIO()):
                    self.player.load_saves()
            self.assertEqual(self.transform(raw, sequence=40), reply)
            self.assertEqual(self.save, accepted)
            self.assertEqual(self.path.read_bytes(), disk)
        self.reject({**raw, "plantTime": 0}, sequence=40)
        self.reject(raw, sequence=41)

    def test_missing_identity_forged_adult_class_and_insufficient_funds_are_atomic(self):
        self.prepare()
        raw = copy.deepcopy(self.obj)
        for changes in ({"id": 999}, {"itemName": "horse_gray", "className": "Animal"}, {"className": "Animal"}):
            with self.subTest(changes=changes):
                self.reject({**raw, **changes})
        self.save["userInfo"]["player"]["cash"] = 4
        self.persist()
        self.reject()
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.rpc("WorldService.performAction", ["transform", raw, [{"price": 0}]], error=29)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)

    def test_mystery_foal_and_other_world_remain_unmodified_while_home_retains_same_contract(self):
        self.prepare("foal_white")
        self.reject()
        self.prepare()
        # A synthetic owned other-world baby remains outside this admission.
        baby = {**copy.deepcopy(self.obj), "id": 700}
        creative_worlds.create(self.save, "meadows", now=NOW)
        world_travel.switch(self.save, "meadows", now=NOW)
        self.save["world"]["objectsArray"] = [baby]
        self.persist()
        self.reject()
        self.prepare("calf")
        baby = copy.deepcopy(self.obj)
        world_travel.switch(self.save, "farm", now=NOW)
        self.save["world"]["objectsArray"].append(baby)
        self.save[world_travel.STATE_KEY]["inactive"]["england"]["objectsArray"] = []
        self.persist()
        self.transform(baby)
        grown = next(row for row in self.save["world"]["objectsArray"] if row["id"] == 600)
        self.assertEqual(grown["itemName"], "cow")
        self.assertEqual(self.save["userInfo"]["player"]["cash"], 2499)


if __name__ == "__main__":
    unittest.main()
