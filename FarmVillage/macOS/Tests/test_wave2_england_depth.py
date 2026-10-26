"""Own-world classic construction and land through signed AMF.

Imported occupants, materials and preceding tiers are synthetic preconditions;
no real clocks are shortened. This is source/gateway acceptance, not UI proof.
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
import test_paid_buildings_wire as legacy
import test_persistence as fixtures
import construction
import england_progression
import items
import peaceful
import world_travel

NOW = 1_800_000_000


class EnglandDepthWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway
    save = legacy.PaidBuildingsWireTests.save
    obj = legacy.PaidBuildingsWireTests.obj
    persist = legacy.PaidBuildingsWireTests.persist
    snapshot = legacy.PaidBuildingsWireTests.snapshot
    send = legacy.PaidBuildingsWireTests.send
    reject_unchanged = legacy.PaidBuildingsWireTests.reject_unchanged

    def prepare(self, name="xukhorsestable_finished", **extra):
        options = {"state": "built", "expansionLevel": 1, "capacity": 20, **extra}
        legacy.PaidBuildingsWireTests.prepare(self, name, **options)
        obj = copy.deepcopy(self.obj)
        self.save["world"]["objectsArray"] = [{"id": 9, "itemName": "cow", "className": "Animal",
            "state": "bare", "plantTime": 1_600_000_000_000,
            "position": {"x": 2, "y": 2, "z": 0}, "imported": {"name": "Home cow"}}]
        world_travel.switch(self.save, "england", True, now=NOW)
        self.home = copy.deepcopy(self.save[world_travel.STATE_KEY]["inactive"]["farm"])
        self.save["world"]["objectsArray"] = [obj]
        self.save["userInfo"]["player"].update(cash=2500, gold=100_000_000,
            storageData={"-2": {"HB": [3, [], [{"Home": "keep"}]]}})
        self.persist()

    def assert_home(self):
        self.assertEqual(self.save[world_travel.STATE_KEY]["inactive"]["farm"], self.home)
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-2"],
                         {"HB": [3, [], [{"Home": "keep"}]]})

    def rpc(self, method, params, *, sequence=None, error=0):
        self.sequence += 1
        response = self.gateway([self.command(method, copy.deepcopy(params), self.sequence if sequence is None else sequence)])
        return fixtures.gateway_results(self, response, [error])[0]["data"]

    def test_all_five_classic_variants_every_authored_tier_preserve_occupants_imports_and_clock(self):
        cases = (("xukhorsestable_finished", ((2, 25, 50), (3, 30, 50), (4, 35, 50), (5, 40, 50))),
                 ("nurserybarn_finished", ((2, 30, 50), (3, 40, 50))),
                 ("nurserybarn_finished_complete", ((2, 30, 50), (3, 40, 50))),
                 ("pigpen_finished", ((2, 30, 36), (3, 40, 60))),
                 ("pigpenv2_finished", ((2, 30, 36), (3, 40, 60))))
        for name, stages in cases:
            with self.subTest(name=name):
                self.prepare(name, contents=[{"itemCode": "opaque-import", "numItem": 1,
                    "imported": {"name": "Retained occupant", "DNA": [1, 2]}}],
                    storageMetadata={"opaque": [{"name": "Retained occupant", "DNA": [1, 2]}]})
                self.obj["expansionParts"] = {"opaque": {"keep": [1]}}
                self.save["userInfo"]["player"]["storageData"]["600"] = {
                    "opaque-import": [1, ["original sender"], [{"name": "Retained occupant", "DNA": [1, 2]}]]}
                self.persist()
                original, balance = copy.deepcopy(self.obj), 2500
                for level, capacity, price in stages:
                    self.send("CompleteNow")
                    balance -= price
                    self.assertEqual((self.obj["expansionLevel"], self.obj["capacity"]), (level, capacity))
                    self.assertEqual(self.save["userInfo"]["player"]["cash"], balance)
                    for key in ("id", "contents", "plantTime", "storageMetadata", "position", "importedBuilding", "expansionParts"):
                        self.assertEqual(self.obj[key], original[key])
                self.reject_unchanged("CompleteNow")
                self.assert_home()
                accepted = copy.deepcopy(self.save)
                with redirect_stdout(io.StringIO()):
                    self.player.load_saves()
                self.assertEqual(self.save, accepted)

    def test_nursery_and_pigpen_finish_from_active_material_or_cash_with_exact_once_only_reward(self):
        for name, reward in (("nurserybarn", "foal_gray"), ("pigpen", "pigpen_male_light_green")):
            for action in ("store", "TransformBuilding"):
                with self.subTest(name=name, action=action):
                    needs = construction._initial_requirements(items.get_item_by_name(name))
                    self.prepare(name, state="construction", isFullyBuilt=False,
                        contents=[{"itemCode": code, "numItem": needed - (code == "K1"), "opaque": "keep"}
                                  for code, (_, needed) in needs.items()])
                    self.save["userInfo"]["player"]["storageData"]["-8"] = {"K1": [1, [], [{"England brick": 1}]]}
                    self.persist()
                    raw = self.snapshot()
                    options = {"storedItemName": "brick", "cameFromLocation": -8} if action == "store" else {}
                    with mock.patch.object(self.server.commands, "timestamp_now", return_value=NOW):
                        reply = self.send(action, raw, options, sequence=40)["data"]
                    self.assertEqual(reply["finishedName"], construction._CLASSIC[name])
                    self.assertEqual(reply["gift"], reward)
                    self.assertEqual((self.obj["plantTime"], self.obj["capacity"]), (NOW * 1000, 20))
                    self.assertTrue(all(row["numItem"] == 0 and row["opaque"] == "keep" for row in self.obj["contents"]))
                    self.assertEqual(self.save["userInfo"]["player"]["cash"], 2500 - (action == "TransformBuilding"))
                    reward_code = items.get_item_by_name(reward)["code"]
                    self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-1"][reward_code], [1, [], []])
                    accepted = copy.deepcopy(self.save)
                    with mock.patch.object(self.server.commands, "timestamp_now", return_value=NOW):
                        self.send(action, raw, options, sequence=40)
                    self.assertEqual(self.save, accepted)
                    self.assert_home()

    def test_first_initial_material_receipt_is_atomic_and_replays_after_completion_and_reload(self):
        for name, reward in (("nurserybarn", "foal_gray"), ("pigpen", "pigpen_male_light_green")):
            with self.subTest(name=name):
                needs = construction._initial_requirements(items.get_item_by_name(name))
                self.prepare(name, state="construction", isFullyBuilt=False,
                    contents=[{"itemCode": code, "numItem": needed - (code == "K1"), "opaque": "keep"}
                              for code, (_, needed) in needs.items()])
                self.save["userInfo"]["player"]["storageData"]["-8"] = {"K1": [1, [], [{"England brick": 1}]]}
                self.persist()
                raw = self.snapshot()
                options = {"storedItemName": "brick", "cameFromLocation": -8}
                before, disk = copy.deepcopy(self.save), self.path.read_bytes()
                with mock.patch.object(construction, "_finish_initial", side_effect=ValueError("Synthetic post-withdrawal failure")):
                    self.send("store", raw, options, sequence=40, reject=True)
                self.assertEqual(self.save, before)
                self.assertEqual(self.path.read_bytes(), disk)
                self.assertNotIn("40", self.save.get(construction.REQUESTS_KEY, {}).get("receipts", {}))
                with mock.patch.object(self.server.commands, "timestamp_now", return_value=NOW):
                    reply = self.send("store", raw, options, sequence=40)["data"]
                history = self.save[construction.REQUESTS_KEY]
                self.assertEqual(history["highestSequence"], 40)
                self.assertEqual(history["receipts"]["40"]["response"],
                                 {"finishedName": construction._CLASSIC[name], "gift": reward})
                self.assertEqual(reply, {"id": 600, "finishedName": construction._CLASSIC[name], "gift": reward})
                self.assertEqual(self.obj["plantTime"], NOW * 1000)
                reward_code = items.get_item_by_name(reward)["code"]
                self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-1"][reward_code], [1, [], []])
                accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
                self.assertEqual(self.send("store", raw, options, sequence=40)["data"], reply)
                self.assertEqual(self.save, accepted)
                self.assertEqual(self.path.read_bytes(), disk)
                with redirect_stdout(io.StringIO()):
                    self.player.load_saves()
                self.assertEqual(self.save, accepted)
                self.assertEqual(self.send("store", raw, options, sequence=40)["data"], reply)
                self.assertEqual(self.save, accepted)
                self.assertEqual(self.path.read_bytes(), disk)
                self.assert_home()

    def test_exact_classic_occupants_filters_capacity_and_source_metadata_in_england(self):
        cases = (("xukhorsestable_finished", "horse_black"), ("nurserybarn_finished", "foal_gray"),
                 ("nurserybarn_finished_complete", "foal_gray"), ("pigpen_finished", "pigpen_male_light_green"),
                 ("pigpenv2_finished", "pigpen_male_light_green"))
        for name, occupant in cases:
            with self.subTest(name=name):
                self.prepare(name)
                code = items.get_item_by_name(occupant)["code"]
                metadata = [{"name": f"Imported {index}", "DNA": {"keep": [index]}} for index in range(21)]
                self.save["userInfo"]["player"]["storageData"]["-1"] = {
                    code: [21, ["synthetic sender"], metadata], "CW": [1, [], []]}
                self.persist()
                self.reject_unchanged("store", options={"storedItemName": "cow", "isGift": True})
                raw = {**self.snapshot(), "capacity": 999, "plantTime": 0}
                self.send("store", raw, {"storedItemName": occupant, "isGift": True,
                    "numToStore": 20, "metadata": {"forged": "ignored"}})
                self.assertEqual((self.obj["capacity"], self.obj["plantTime"]), (20, 1000000))
                self.assertEqual(self.obj["contents"], [{"itemCode": code, "numItem": 20}])
                self.assertEqual(self.save["userInfo"]["player"]["storageData"]["600"][code][2], metadata[:20])
                self.reject_unchanged("store", options={"storedItemName": occupant, "isGift": True})
                self.assert_home()

    def test_ordered_cash_land_ladder_through_58_disabled_60_and_roundtrip(self):
        self.prepare()
        original, cash = copy.deepcopy(self.save["world"]["objectsArray"]), 2500
        for nominal in range(14, 60, 2):
            name = f"xukfarm{nominal}_cash"
            width = int(items.get_item_by_name(name)["squares"])
            result = self.rpc("FarmService.expandFarm", [name, "cash"])
            cash -= 1
            self.assertEqual((result["sizeX"], result["sizeY"]), (width, width))
            self.assertEqual(self.save["userInfo"]["player"]["cash"], cash)
            self.assertEqual(self.save["world"]["objectsArray"], original)
            accepted = copy.deepcopy(self.save)
            self.rpc("FarmService.expandFarm", [name, "cash"], sequence=self.sequence)
            self.assertEqual(self.save, accepted)
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.rpc("FarmService.expandFarm", ["xukfarm60_cash", "cash"], error=29)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)
        self.assert_home()
        world_travel.switch(self.save, "farm", now=NOW + 1)
        self.assertEqual(self.save["world"], self.home)
        world_travel.switch(self.save, "england", now=NOW + 2)
        self.persist()
        accepted = copy.deepcopy(self.save)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.save, accepted)
        self.assertFalse(england_progression.STORY_ENABLED)

    def test_all_nineteen_coin_land_steps_exact_costs_neighbors_funds_and_wrong_world(self):
        self.prepare()
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        for name in ("farm14", "xukfarm16"):
            self.rpc("FarmService.expandFarm", [name, "coins"], error=29)
            self.assertEqual(self.save, before)
            self.assertEqual(self.path.read_bytes(), disk)
        for nominal in range(14, 52, 2):
            name = f"xukfarm{nominal}"
            item = items.get_item_by_name(name)
            cost, neighbors = int(item["cost"]), int(item.get("minNeighbors", 0))
            if neighbors:
                before, disk = copy.deepcopy(self.save), self.path.read_bytes()
                with mock.patch.object(self.server.commands, "neighbor_uids", return_value=[str(n) for n in range(neighbors - 1)]):
                    self.rpc("FarmService.expandFarm", [name, "coins"], error=29)
                self.assertEqual(self.save, before)
                self.assertEqual(self.path.read_bytes(), disk)
            balance = self.save["userInfo"]["player"]["gold"]
            self.save["userInfo"]["player"]["gold"] = cost - 1
            self.persist()
            before, disk = copy.deepcopy(self.save), self.path.read_bytes()
            with mock.patch.object(self.server.commands, "neighbor_uids", return_value=[str(n) for n in range(30)]):
                self.rpc("FarmService.expandFarm", [name, "coins"], error=29)
            self.assertEqual(self.save, before)
            self.assertEqual(self.path.read_bytes(), disk)
            self.save["userInfo"]["player"]["gold"] = balance
            self.persist()
            # Recovered neighbor counts are injected synthetic preconditions,
            # not earned/social/browser evidence or alterations to real farms.
            with mock.patch.object(self.server.commands, "neighbor_uids", return_value=[str(n) for n in range(30)]):
                result = self.rpc("FarmService.expandFarm", [name, "coins"])
            self.assertEqual((result["sizeX"], result["sizeY"]), (int(item["squares"]), int(item["squares"])))
            self.assertEqual(self.save["userInfo"]["player"]["gold"], balance - cost)
        self.assert_home()
        self.assertFalse(england_progression.STORY_ENABLED)

    def test_exact_english_stable_mature_base_yield_cooldown_retry_reload_and_natural_next_clock(self):
        horse = items.get_item_by_name("horse_black")
        stable = items.get_item_by_name("xukhorsestable_finished")
        grow = peaceful.grow_seconds(stable)
        code = horse["code"]
        self.prepare(contents=[{"itemCode": code, "numItem": 2, "opaque": "keep"}],
                     plantTime=(NOW - grow) * 1000,
                     storageMetadata={"opaque": [{"name": "Two horses", "DNA": [1, 2]}]})
        self.save["userInfo"]["player"]["storageData"]["600"] = {
            code: [2, ["synthetic sender"], [{"name": "Two horses", "DNA": [1, 2]}]]}
        self.persist()
        raw = self.snapshot()
        ledger = copy.deepcopy(self.save["userInfo"]["player"]["storageData"])
        before_gold = self.save["userInfo"]["player"]["gold"]
        expected = 2 * int(horse["coinYield"])
        with mock.patch.object(self.server.commands, "timestamp_now", return_value=NOW):
            self.send("harvest", raw, sequence=40)
        self.assertEqual(self.save["userInfo"]["player"]["gold"], before_gold + expected)
        self.assertEqual((self.obj["state"], self.obj["plantTime"]), ("bare", NOW * 1000))
        self.assertEqual(self.save["userInfo"]["player"]["storageData"], ledger)
        accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
        with mock.patch.object(self.server.commands, "timestamp_now", return_value=NOW):
            self.send("harvest", raw, sequence=40)
        self.assertEqual(self.save, accepted)
        self.assertEqual(self.path.read_bytes(), disk)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        with mock.patch.object(self.server.commands, "timestamp_now", return_value=NOW + grow - 2):
            self.send("harvest", raw)
        self.assertEqual(self.save, accepted)
        # Move the synthetic observation time through the full archived period;
        # the authored growTime and saved clock are never reduced.
        with mock.patch.object(self.server.commands, "timestamp_now", return_value=NOW + grow):
            self.send("harvest", raw)
        self.assertEqual(self.save["userInfo"]["player"]["gold"], before_gold + 2 * expected)
        self.assertEqual(self.obj["plantTime"], (NOW + grow) * 1000)
        self.assertEqual(self.save["userInfo"]["player"]["storageData"], ledger)
        self.assert_home()

    def test_unrecovered_nursery_and_pigpen_harvest_refuse_without_clock_occupant_or_reward_loss(self):
        for name in ("nurserybarn_finished", "nurserybarn_finished_complete", "pigpen_finished", "pigpenv2_finished"):
            with self.subTest(name=name):
                self.prepare(name, contents=[{"itemCode": "opaque-import", "numItem": 1}],
                    storageMetadata={"opaque": [{"name": "Retained occupant", "DNA": [1, 2]}]})
                self.save["userInfo"]["player"]["storageData"]["600"] = {
                    "opaque-import": [1, ["original sender"], [{"name": "Retained occupant", "DNA": [1, 2]}]]}
                self.persist()
                with mock.patch.object(self.server.commands, "timestamp_now", return_value=NOW):
                    self.reject_unchanged("harvest")
                self.assert_home()


if __name__ == "__main__":
    unittest.main()
