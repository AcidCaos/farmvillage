"""Synthetic imported Port only; no starter grant, real saves or timer edits."""
import copy
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import cove_port
import creative_worlds
import items
import storage
import world_travel

NOW = 1800000000


class CovePortWave2Tests(unittest.TestCase):
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
    def port(self):
        return self.save["world"]["objectsArray"][0]

    def prepare(self, level=1, cash=5000):
        from game_settings import level_to_xp
        self.write_fixture()
        self.save["userInfo"]["player"].update(xp=level_to_xp(20), cash=cash, gold=10000)
        creative_worlds.create(self.save, "fisherman", "allAccess", now=NOW)
        world_travel.switch(self.save, "fisherman", now=NOW)
        # Imported-owned building is a seeded precondition, never earned play.
        self.save["world"]["objectsArray"].append({"id": 7001, "className": cove_port.CLASS,
            "itemName": cove_port.NAME, "state": "built", "expansionLevel": level,
            "expansionParts": {}, "capacity": 0, "isFullyBuilt": True, "contents": [],
            "plantTime": 1700000000123, "position": {"x": 25, "y": 25, "z": 0},
            "imported": {"retain": ["yes"]}})

    def run_action(self, action, options=None, seq=None, snapshot=None):
        return cove_port.perform(self.save, action, copy.deepcopy(snapshot or self.port),
            [] if options is None else [options], request_id=seq, now=NOW)

    def material(self, name, amount=1, seq=None, *, gift=False, snapshot=None):
        return self.run_action("store", {"storedItemName": name,
            "storedItemCode": items.get_item_by_name(name)["code"],
            "numToStore": amount, "target": self.port["id"], "isGift": gift}, seq, snapshot)

    def rejects(self, action, options=None, **kwargs):
        before = copy.deepcopy(self.save)
        with self.assertRaises((ValueError, TypeError)):
            self.run_action(action, options, **kwargs)
        self.assertEqual(self.save, before)

    def persist(self):
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")

    def wire(self, action, options=None, seq=1, expected=200, snapshot=None):
        self.persist()
        snapshot = copy.deepcopy(snapshot or self.port)
        with mock.patch("commands.timestamp_now", return_value=NOW), mock.patch("server.timestamp_now", return_value=NOW):
            result = self.gateway([self.command("WorldService.performAction", [action, snapshot,
                [] if options is None else [options]], seq)])
        fixtures.assert_gateway_status(self, result, expected)
        if expected == 200:
            from pyamf import remoting
            return remoting.decode(result.data).bodies[0][1].body["data"][0]["data"]

    def test_exact_contract_and_no_automatic_starter_port(self):
        self.prepare()
        contract = cove_port.recovered_contract()
        self.assertEqual([r["part"][0]["need"] for r in contract["upgrades"]],
                         [str(n) for n in cove_port.STAGE_COUNTS])
        self.assertEqual(contract["harvestSeconds"], 86400)
        self.assertFalse(contract["buyable"])
        self.assertFalse(contract["harvestAvailable"])
        self.assertEqual(contract["upgrades"][-1]["award"], {"name": "consume_fishermanXfer", "number": "1"})
        # Creation before this fixture import had an empty objectsArray.
        self.assertEqual(self.save[creative_worlds.ACCESS_MARKER]["fisherman"]["cashPaid"], 0)

    def test_material_ladder_all_ten_stages_exact_counts_and_once_only_award(self):
        self.prepare()
        seq = 1
        for level, count in enumerate(cove_port.STAGE_COUNTS, 2):
            for name in cove_port.PART_NAMES:
                response = self.material(name, count, seq)
                seq += 1
            self.assertEqual(response, {"id": 7001, "expansionRewardType": 2})
            self.assertEqual((self.port["expansionLevel"], self.port["expansionParts"]), (level, {}))
            self.assertEqual(self.port["plantTime"], 1700000000123)
            gifts = self.save["userInfo"]["player"]["storageData"]["-1"]
            self.assertEqual(gifts.get("06x", [0])[0], 1 if level == 11 else 0)
        self.assertEqual(self.save["userInfo"]["player"]["cash"], 5000 - 3 * sum(cove_port.STAGE_COUNTS))
        self.assertEqual(self.port["imported"], {"retain": ["yes"]})
        self.assertNotIn("unlockedWorldContentLicenses", self.save["userInfo"])
        self.rejects("CompleteNow")
        self.run_action("GrantRetroactiveUpgrade", seq=seq)
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-1"]["06x"][0], 1)

    def test_paid_completion_uses_missing_authored_parts_and_retains_clock(self):
        self.prepare()
        self.material("stonepart", 2, seq=1)
        response = self.run_action("CompleteNow", {"partName": "stonepart", "isGift": False}, seq=2)
        self.assertEqual(response, {"id": 7001})
        self.assertEqual(self.port["expansionParts"], {"0el": 3})
        self.assertEqual(self.save["userInfo"]["player"]["cash"], 4997)
        response = self.run_action("CompleteNow", {"isGift": False, "currency": "cash"}, seq=3)
        self.assertEqual(response, {"id": 7001, "expansionRewardType": 2})
        self.assertEqual(self.save["userInfo"]["player"]["cash"], 4991)
        self.assertEqual(self.port["plantTime"], 1700000000123)

    def test_expand_with_currency_uses_original_cash_market(self):
        self.prepare()
        self.run_action("ExpandWithCurrency", seq=1)
        self.assertEqual((self.port["expansionLevel"], self.save["userInfo"]["player"]["cash"]), (2, 4991))
        self.assertEqual(self.save["userInfo"]["player"]["gold"], 10000)

    def test_gift_material_withdrawal_preserves_surviving_metadata(self):
        self.prepare()
        self.save["userInfo"]["player"]["storageData"]["-1"]["0el"] = [4, ["sender"], [{"a": 1}, {"b": 2}]]
        self.material("stonepart", 3, seq=1, gift=True)
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-1"]["0el"], [1, [], [{"b": 2}]])
        self.assertEqual(self.port["expansionParts"], {"0el": 3})
        self.assertEqual(self.save["userInfo"]["player"]["cash"], 5000)

    def test_retry_survives_serialization_without_second_charge(self):
        self.prepare()
        snapshot = copy.deepcopy(self.port)
        response = self.run_action("CompleteNow", {"isGift": False}, seq=1, snapshot=snapshot)
        import json
        restored = json.loads(json.dumps(self.save))
        second = cove_port.perform(restored, "CompleteNow", snapshot, [{"isGift": False}], request_id=1, now=NOW)
        self.assertEqual(second, response)
        self.assertEqual(restored["userInfo"]["player"]["cash"], 4991)
        self.assertEqual(restored["world"]["objectsArray"][0]["expansionLevel"], 2)
        self.rejects("CompleteNow", {"partName": "stonepart"}, seq=1)

    def test_insufficient_cash_and_overfill_are_atomic(self):
        self.prepare(cash=2)
        self.rejects("CompleteNow", {"isGift": False})
        self.rejects("store", {"storedItemName": "stonepart", "numToStore": 4})
        self.rejects("store", {"storedItemName": "logpart", "numToStore": 3, "isGift": True})
        self.rejects("CompleteNow", {"partName": "wrong"})

    def test_forged_optimistic_progress_is_ignored_and_identity_rejected(self):
        self.prepare()
        incoming = {**self.port, "expansionLevel": 10, "expansionParts": {"0el": 60}, "plantTime": 1}
        self.run_action("CompleteNow", {"isGift": False}, seq=1, snapshot=incoming)
        self.assertEqual(self.port["expansionLevel"], 2)
        self.assertEqual(self.port["plantTime"], 1700000000123)
        self.rejects("CompleteNow", snapshot={**self.port, "itemName": "barn"})

    def test_wrong_world_and_missing_port_are_atomic(self):
        self.prepare()
        self.save["userInfo"]["currentWorldType"] = "farm"
        self.rejects("CompleteNow")
        self.save["userInfo"]["currentWorldType"] = "fisherman"
        snapshot = copy.deepcopy(self.port)
        self.save["world"]["objectsArray"] = []
        self.rejects("CompleteNow", snapshot=snapshot)

    def test_harvest_paid_readiness_and_fixed_object_operations_refuse(self):
        self.prepare()
        for action in ("harvest", "HarvestReadyNow", "sell", "clear", "move", "place", "plant", "use"):
            with self.subTest(action=action):
                self.rejects(action)

    def test_imported_full_port_retroactive_award_exact_callback_and_repeat_safe(self):
        self.prepare(level=11)
        response = self.run_action("GrantRetroactiveUpgrade", seq=1)
        self.assertEqual(response, {"id": 7001, "upgradeAward": [{"itemName": "consume_fishermanXfer", "number": 1}]})
        self.run_action("GrantRetroactiveUpgrade", seq=2)
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-1"]["06x"][0], 1)
        # Generic client action counters cannot reset the authoritative award ledger.
        self.save["userInfo"]["player"]["actionCounts"]["upgradeaward_fishermanscove"] = 0
        self.run_action("GrantRetroactiveUpgrade", seq=3)
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-1"]["06x"][0], 1)

    def test_lower_finite_retroactive_probe_acknowledges_without_award(self):
        self.prepare()
        before = copy.deepcopy(self.save)
        self.assertEqual(self.run_action("GrantRetroactiveUpgrade"), {"id": 7001})
        self.save.pop(cove_port.RESPONSE_KEY)
        self.assertEqual(self.save, before)
        self.rejects("GrantRetroactiveUpgrade", {"isGift": False})
        self.rejects("CompleteNow", {"partName": "stonepart", "isGift": True})

    def test_captured_optional_nan_and_undefined_probe_retry_and_paid_completion(self):
        import pyamf
        self.prepare()
        snapshot = {**self.port, "tempId": float("nan"), "buildTime": float("nan"),
                    "plantTime": float("nan"), "instanceDataStoreKey": pyamf.Undefined}
        original_port = copy.deepcopy(self.port)
        cash = self.save["userInfo"]["player"]["cash"]
        self.assertEqual(self.wire("GrantRetroactiveUpgrade", seq=20, snapshot=snapshot), {"id": 7001})
        self.assertEqual(self.port, original_port)
        self.assertNotIn(cove_port.AWARDED_KEY, self.save)
        settled = copy.deepcopy(self.save)
        nulls = {**snapshot, "tempId": None, "buildTime": None, "plantTime": None,
                 "instanceDataStoreKey": None}
        self.assertEqual(self.wire("GrantRetroactiveUpgrade", seq=20, snapshot=nulls), {"id": 7001})
        self.assertEqual(self.save, settled)
        self.assertEqual(self.wire("CompleteNow", {"isGift": False}, seq=21, snapshot=snapshot),
                         {"id": 7001, "expansionRewardType": 2})
        self.assertEqual((self.port["expansionLevel"], self.port["plantTime"]), (2, original_port["plantTime"]))
        self.assertEqual(self.save["userInfo"]["player"]["cash"], cash - 9)
        accepted = copy.deepcopy(self.save)
        self.wire("CompleteNow", {"isGift": False}, seq=21, snapshot=nulls)
        self.assertEqual(self.save, accepted)
        # The action remains part of the signed receipt; a probe is not a paid retry.
        self.wire("GrantRetroactiveUpgrade", seq=21, snapshot=nulls, expected=400)
        self.assertEqual(self.save, accepted)

    def test_probe_accepts_all_owned_lower_finite_levels_and_refuses_invalid_values(self):
        for level in range(1, 11):
            with self.subTest(level=level):
                self.prepare(level=level)
                before = copy.deepcopy(self.save)
                self.assertEqual(self.run_action("GrantRetroactiveUpgrade"), {"id": 7001})
                self.save.pop(cove_port.RESPONSE_KEY)
                self.assertEqual(self.save, before)
        self.prepare()
        for change in ({"position": {"x": float("nan"), "y": 25, "z": 0}},
                       {"cash": float("nan")}, {"buildTime": float("inf")},
                       {"tempId": float("-inf")}):
            with self.subTest(change=change):
                self.rejects("GrantRetroactiveUpgrade", snapshot={**self.port, **change})
        for change in ({"expansionLevel": 0}, {"expansionLevel": 12},
                       {"isFullyBuilt": False}, {"capacity": 1}):
            with self.subTest(saved=change):
                original = copy.deepcopy(self.port)
                self.port.update(change)
                self.rejects("GrantRetroactiveUpgrade")
                self.port.clear(); self.port.update(original)

    def test_cohort_off_preserves_final_progress_without_grant(self):
        self.prepare(level=10)
        with mock.patch.object(cove_port, "_award_enabled", return_value=False):
            self.run_action("CompleteNow")
        self.assertEqual(self.port["expansionLevel"], 11)
        self.assertNotIn("06x", self.save["userInfo"]["player"]["storageData"]["-1"])

    def test_stale_snapshot_preserves_progress_clock_and_imported_metadata(self):
        self.prepare()
        self.run_action("CompleteNow")
        incoming = {"id": 7001, "itemName": "barn", "className": "Building", "expansionLevel": 99,
                    "contents": [], "state": "construction", "plantTime": 0}
        merged = cove_port.preserve_fields(self.port, incoming)
        self.assertEqual((merged["itemName"], merged["expansionLevel"], merged["plantTime"]),
                         (cove_port.NAME, 2, 1700000000123))

    def test_saved_malformed_progress_fails_closed(self):
        self.prepare()
        for change in ({"expansionLevel": 12}, {"expansionParts": {"0el": 4}},
                       {"capacity": 1}, {"contents": [{"itemCode": "x", "numItem": 1}]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                cove_port.guard_snapshot({**self.port, **change})

    def test_wire_paid_completion_callback_reward_and_restart_retry(self):
        self.prepare(level=10)
        snapshot = copy.deepcopy(self.port)
        response = self.wire("CompleteNow", {"isGift": False}, snapshot=snapshot)
        self.assertEqual(response, {"id": 7001, "expansionRewardType": 2})
        self.assertEqual(self.save["userInfo"]["player"]["cash"], 4820)
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-1"]["06x"][0], 1)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.wire("CompleteNow", {"isGift": False}, snapshot=snapshot), response)
        self.assertEqual(self.save["userInfo"]["player"]["cash"], 4820)
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-1"]["06x"][0], 1)

    def test_wire_material_final_callback_uses_saved_progress_and_exact_charge(self):
        self.prepare()
        self.port["expansionParts"] = {"0el": 3, "0en": 3, "0es": 2}
        self.assertEqual(self.wire("store", {"storedItemName": "steelbeampart", "numToStore": 1}),
                         {"id": 7001, "expansionRewardType": 2})
        self.assertEqual((self.port["expansionLevel"], self.port["expansionParts"]), (2, {}))
        self.assertEqual(self.save["userInfo"]["player"]["cash"], 4999)

    def test_wire_closed_harvest_preserves_disk_clock_and_balances(self):
        self.prepare()
        self.persist()
        disk = next(self.saves.glob("*.json")).read_bytes()
        before = copy.deepcopy(self.save)
        self.wire("HarvestReadyNow", expected=400)
        self.assertEqual(self.save, before)
        self.assertEqual(next(self.saves.glob("*.json")).read_bytes(), disk)


if __name__ == "__main__":
    unittest.main()
