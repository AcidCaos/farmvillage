"""W02 England Pub admission using synthetic saves and original signed AMF.

These cases grade England explicitly. Fixtures carry level/currency/gifts;
those preconditions are not represented as earned gameplay.
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
import crafting
import engine
import game_settings
import items
import world_travel

NOW = 1800000000
NAME = "xukcraftingpub"
CLASS = "CraftingCottageBuilding"


class EnglandPubAdmissionTests(unittest.TestCase):
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

    def prepare(self, *, level=20, gifts=0):
        self.path = self.write_fixture()
        self.save["world"]["objectsArray"] = []
        self.save["userInfo"]["player"].update(
            xp=game_settings.level_to_xp(level), gold=1000000, cash=100,
            storageData={}, seenFlags={"placeCottage": True, "craftTutDone": True})
        self.save["craftingState"] = {"craftingItems": [], "craftingSkillState": {
            "recipeStates": [], "craftTypes": []}, "imported": {"keep": [1, 2]}}
        world_travel.switch(self.save, "england", True, now=NOW)
        if gifts:
            self.save["userInfo"]["player"]["storageData"]["-1"] = {"LA": [gifts, [], []]}
        self.sequence = 0
        self.persist()

    def persist(self):
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")

    @staticmethod
    def snapshot(**fields):
        return dict({"id": 64001, "itemName": NAME, "className": CLASS,
            "state": "built", "isFullyBuilt": True, "craftLevel": 5,
            "recipeQueue": [{"forged": True}], "finishedRecipes": {"lq": {"qty": 999}},
            "contents": {}, "position": {"x": 10, "y": 10, "z": 0}}, **fields)

    def send(self, snapshot, *, options=(), error=0, sequence=None):
        self.sequence += 1
        if sequence is None:
            sequence = self.sequence
        with mock.patch.object(self.server, "timestamp_now", return_value=NOW), \
                mock.patch.object(self.server.commands, "timestamp_now", return_value=NOW), \
                mock.patch.object(engine, "timestamp_now", return_value=NOW), \
                mock.patch.object(crafting, "timestamp_now", return_value=NOW):
            response = self.gateway([self.command("WorldService.performAction",
                ["place", snapshot, list(options)], sequence)])
        return fixtures.gateway_results(self, response, [error])[0]["data"]

    def reject(self, snapshot, **kwargs):
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.send(snapshot, error=29, **kwargs)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)

    def test_england_exact_pub_placement_charges_original_tier_and_replays_once(self):
        self.prepare()
        home = copy.deepcopy(self.save[world_travel.STATE_KEY]["inactive"]["farm"])
        player = self.save["userInfo"]["player"]
        gold, xp = player["gold"], player["xp"]
        self.send(self.snapshot(), sequence=40)
        pub = next(o for o in self.save["world"]["objectsArray"] if o["itemName"] == NAME)
        self.assertEqual((player["gold"], player["xp"]), (gold - 1000, xp + 1000))
        self.assertEqual((pub["className"], pub["craftLevel"], pub["contents"]), (CLASS, 1, []))
        self.assertFalse(any(row.get("forged") for row in pub["recipeQueue"]))
        self.assertNotIn("lq", pub["finishedRecipes"])
        self.assertEqual(self.save[world_travel.STATE_KEY]["inactive"]["farm"], home)
        self.assertEqual(self.save["craftingState"]["imported"], {"keep": [1, 2]})
        accepted = copy.deepcopy(self.save)
        self.send(self.snapshot(), sequence=40)
        self.assertEqual(self.save, accepted)
        # Temporary placement IDs belong to this client document only. The
        # persisted farm and cold reload deliberately discard them.
        persisted = json.loads(self.path.read_text())
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.save, persisted)

    def test_england_later_purchase_tiers_count_current_world_and_cottage_gifts(self):
        for gifts, price in ((1, 10000), (2, 100000)):
            with self.subTest(gifts=gifts):
                self.prepare(gifts=gifts)
                gold = self.save["userInfo"]["player"]["gold"]
                self.send(self.snapshot())
                self.assertEqual(self.save["userInfo"]["player"]["gold"], gold - price)
                self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-1"]["LA"][0], gifts)

    def test_england_unrecovered_fourth_tier_refuses_before_charge(self):
        self.prepare(gifts=3)
        self.reject(self.snapshot())

    def test_england_insufficient_level_funds_currency_and_duplicate_refuse_atomically(self):
        self.prepare(level=19)
        self.reject(self.snapshot())
        self.prepare()
        self.save["userInfo"]["player"]["gold"] = 999
        self.persist()
        self.reject(self.snapshot())
        self.prepare()
        self.reject(self.snapshot(), options=[{"currency": "cash"}])
        self.send(self.snapshot())
        self.reject(self.snapshot(id=64002))

    def test_england_wrong_class_cottage_and_explicit_world_payload_refuse(self):
        self.prepare()
        for fields in ({"className": "Building"}, {"className": "FeatureBuilding"},
                       {"itemName": "craftingbakery"}, {"itemName": "xhdcraftingcottage"},
                       {"worldType": "farm"}):
            with self.subTest(fields=fields):
                self.reject(self.snapshot(**fields))

    def test_exact_regional_admission_helper_does_not_open_neighbor_worlds(self):
        self.prepare()
        self.assertTrue(crafting.regional_cottage("england", NAME, CLASS))
        for world in ("meadows", "fisherman", "rainforest", "htown", "glen"):
            self.assertFalse(crafting.regional_cottage(world, NAME, CLASS), world)
        for name, class_name in (("craftingbakery", CLASS), (NAME, "Building"),
                                 ("xhdcraftingcottage", CLASS), (NAME + " ", CLASS)):
            self.assertFalse(crafting.regional_cottage("england", name, class_name))

    def test_malformed_destination_pub_partition_refuses_direct_travel_atomically(self):
        self.prepare()
        world_travel.switch(self.save, "farm", now=NOW + 1)
        namespace = self.save["craftingState"][crafting.PUB_WORLD_STATE]
        namespace["pubStates"]["england"] = {
            "recipeStates": [], "craftTypes": [], "queue": "unresolved imported queue"}
        self.persist()
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        with self.assertRaises(ValueError):
            world_travel.switch(self.save, "england", now=NOW + 2)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)


if __name__ == "__main__":
    unittest.main()
