"""Ordinary rainforest inventory; separate from positive special containers.

Real catalog and AMF gateway, synthetic private saves. The process test starts
fresh Python/server imports without a listener or the optional artwork check.
"""
import base64
import copy
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import test_inventory_capacity as capacity
import creative_worlds
import engine
import game_settings
import items
import storage
import world_travel

NOW = 1800000000
WORLD = "rainforest"
GROUP = -26
NAME = "xrf_adornedwaterfall"
CODE = "rz9"


class RainforestInventoryWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway
    shed = staticmethod(capacity.InventoryCapacityTests.shed)

    @property
    def save(self):
        return self.player.session("fixture-farmer")

    def prepare(self):
        self.path = self.write_fixture()
        self.save["world"]["objectsArray"] = []
        self.save["userInfo"]["player"].update(xp=game_settings.level_to_xp(40),
            gold=10_000_000, cash=1000, storageData={"-2": {"HB": [2, [], [{"home": "keep"}]]}})
        creative_worlds.create(self.save, WORLD, "allAccess", now=NOW)
        world_travel.switch(self.save, WORLD, now=NOW)
        self.assertEqual(storage.active_inventory_id(self.save), GROUP)
        self.home = copy.deepcopy(self.save["userInfo"]["player"]["storageData"]["-2"])
        self.sequence = 0
        self.persist()

    def persist(self):
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")

    def send(self, action, snapshot, options=(), *, sequence=None, error=0):
        self.sequence += 1
        if sequence is None:
            sequence = self.sequence
        self.sequence = max(sequence, self.sequence)
        with mock.patch("server.timestamp_now", return_value=NOW), mock.patch(
                "commands.timestamp_now", return_value=NOW), mock.patch("engine.timestamp_now", return_value=NOW):
            response = self.gateway([self.command("WorldService.performAction",
                [action, snapshot, list(options)], sequence)])
        results = fixtures.gateway_results(self, response)
        self.assertEqual(results[0]["errorType"], error, results[0])
        return results[0]["data"]

    def refused(self, action, snapshot, options):
        memory, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.send(action, snapshot, options, error=29)
        self.assertEqual(self.save, memory)
        self.assertEqual(self.path.read_bytes(), disk)

    def decor(self, ident=64002, **extra):
        return {"id": ident, "itemName": NAME, "className": "Decoration", "state": "static",
                "direction": 0, "position": {"x": 20, "y": 20, "z": 0}, **extra}

    def options(self, **extra):
        return {"storedItemName": NAME, "target": GROUP, "origin": 0, "resource": 0, **extra}

    def market(self):
        return {"id": GROUP, "className": "StorageBuilding"}

    def ledger(self):
        return self.save["userInfo"]["player"]["storageData"].setdefault(str(GROUP), {})

    def test_paid_shed_exact_cash_and_fifteen_real_slots_never_free_ceiling(self):
        self.prepare()
        self.assertEqual(storage._inventory_limits()[GROUP], 1250)
        item = items.get_item_by_name(NAME)
        self.assertEqual((item["code"], item["market"], item["cash"], item["cost"]),
                         (CODE, "cash", "14", "10000"))
        self.refused("store", self.market(), [self.options()])
        before = copy.deepcopy(self.save["userInfo"]["player"])
        ident = self.send("place", self.shed(capacity=999999))["id"]
        self.assertEqual(self.save["userInfo"]["player"]["cash"], before["cash"] - 22)
        self.assertEqual(items.get_item_by_name("toolshedpink")["capacity"], "15")
        self.send("place", self.shed(capacity=999999), sequence=2)
        self.assertEqual(self.save["userInfo"]["player"]["cash"], before["cash"] - 22)
        self.ledger().update({CODE: [12, [], []], CODE + ":imported": [2, [], [{"keep": 1}]]})
        self.persist()
        self.refused("store", self.market(), [self.options(numToStore=2)])
        cash = self.save["userInfo"]["player"]["cash"]
        self.send("store", self.market(), [self.options()])
        self.assertEqual(self.ledger()[CODE][0], 13)
        self.assertEqual(self.save["userInfo"]["player"]["cash"], cash - 14)
        self.refused("store", self.market(), [self.options()])
        self.assertEqual(next(row for row in self.save["world"]["objectsArray"] if row["id"] == ident)["itemName"], "toolshedpink")
        self.assertEqual(self.ledger()[CODE + ":imported"], [2, [], [{"keep": 1}]])
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-2"], self.home)

    def test_own_decor_unit_metadata_store_withdraw_retries_reload_and_home_roundtrip(self):
        self.prepare()
        self.send("place", self.shed())
        ident = self.send("place", self.decor())["id"]
        saved = copy.deepcopy(next(row for row in self.save["world"]["objectsArray"] if row["id"] == ident))
        metadata = {"unit": "waterfall-1", "imported": {"keep": [1, 2]}}
        options = [self.options(resource=ident, metadata=metadata)]
        self.send("store", saved, options, sequence=20)
        self.assertEqual(self.ledger()[CODE], [1, [], [metadata]])
        accepted = copy.deepcopy(self.save)
        self.send("store", saved, options, sequence=20, error=29)
        self.assertEqual(self.save, accepted)
        # Explicit imported second-unit fixture proves one-at-a-time trimming.
        self.ledger()[CODE] = [2, ["synthetic-sender"], [metadata, {"unit": "waterfall-2"}]]
        self.persist()
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        world_travel.switch(self.save, "farm", now=NOW + 1)
        world_travel.switch(self.save, WORLD, now=NOW + 2)
        self.persist()
        balances = tuple(self.save["userInfo"]["player"][key] for key in ("gold", "cash"))
        withdrawal = self.decor(64003, position={"x": 27, "y": 27, "z": 0})
        self.send("place", withdrawal, [{"isInventoryWithdrawal": True}], sequence=21)
        self.assertEqual(self.ledger()[CODE], [1, [], [{"unit": "waterfall-2"}]])
        accepted = copy.deepcopy(self.save)
        self.send("place", withdrawal, [{"isInventoryWithdrawal": True}], sequence=21)
        self.assertEqual(self.save, accepted)
        self.assertEqual(tuple(self.save["userInfo"]["player"][key] for key in ("gold", "cash")), balances)
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-2"], self.home)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(json.loads(self.path.read_text()), self.save)

    def test_imported_excess_blocks_new_deposits_but_remains_withdrawable_and_recovers(self):
        self.prepare()
        self.send("place", self.shed())
        self.ledger()[CODE] = [16, ["synthetic"], [{"unit": number} for number in range(16)]]
        self.persist()
        self.refused("store", self.market(), [self.options()])
        for number in range(2):
            self.send("place", self.decor(64010 + number,
                position={"x": 25 + 8 * number, "y": 28, "z": 0}), [{"isInventoryWithdrawal": True}])
            self.assertEqual(self.ledger()[CODE][0], 15 - number)
        self.assertEqual(self.ledger()[CODE][2], [{"unit": number} for number in range(2, 16)])
        cash = self.save["userInfo"]["player"]["cash"]
        self.send("store", self.market(), [self.options()])
        self.assertEqual((self.ledger()[CODE][0], self.save["userInfo"]["player"]["cash"]), (15, cash - 14))
        self.refused("store", self.market(), [self.options()])

    def test_foreign_source_target_summary_and_license_claims_never_move_ordinary_inventory(self):
        self.prepare()
        self.send("place", self.shed())
        self.save["userInfo"]["player"]["storageData"]["-2"][CODE] = [2, [], [{"foreign": True}]]
        self.persist()
        self.refused("store", self.market(), [self.options(target=-2)])
        for options in ({"isStorageWithdrawal": -2},
                        {"isStorageWithdrawal": -2, "license": "shipping", "shippingLicense": True},
                        {"isInventoryWithdrawal": True, "cameFromLocation": -2}):
            self.refused("place", self.decor(), [options])
        self.refused("store", self.market(), [self.options(origin=-2)])
        self.save["userInfo"]["worldSummaryData"][WORLD]["storageId"] = -2
        memory, disk = copy.deepcopy(self.save), self.path.read_bytes()
        with self.assertRaises(ValueError):
            storage._guard_inventory_deposit(self.save, -2, 1)
        with self.assertRaises(ValueError):
            self.persist()
        self.assertEqual(self.save, memory)
        self.assertEqual(self.path.read_bytes(), disk)
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-2"][CODE], [2, [], [{"foreign": True}]])

    def test_market_to_inventory_paid_request_replay_cannot_charge_or_clone_twice(self):
        self.prepare()
        self.send("place", self.shed())
        before = copy.deepcopy(self.save["userInfo"]["player"])
        self.send("store", self.market(), [self.options()], sequence=100)
        self.assertEqual(self.ledger()[CODE], [1, [], []])
        self.assertEqual(self.save["userInfo"]["player"]["cash"], before["cash"] - 14)
        accepted = copy.deepcopy(self.save)
        self.send("store", self.market(), [self.options()], sequence=100)
        self.assertEqual(self.save, accepted)
        self.send("store", self.market(), [self.options(numToStore=2)], sequence=100, error=29)
        self.assertEqual(self.save, accepted)

    def test_placement_sequence_binds_full_packet_and_world_and_init_starts_fresh_epoch(self):
        self.prepare()
        self.send("place", self.shed(), sequence=10)
        accepted = copy.deepcopy(self.save)
        self.send("place", self.shed(position={"x": 5, "y": 5, "z": 0}), sequence=10, error=29)
        self.assertEqual(self.save, accepted)
        world_travel.switch(self.save, "farm", now=NOW + 1)
        self.persist()
        memory, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.send("place", self.shed(), sequence=10, error=29)
        self.assertEqual(self.save, memory)
        self.assertEqual(self.path.read_bytes(), disk)
        world_travel.switch(self.save, WORLD, now=NOW + 2)
        self.persist()
        self.send("store", self.market(), [self.options()], sequence=100)
        accepted = copy.deepcopy(self.save)
        response = self.gateway([self.command("UserService.initUser", ["Rainforest QA", 0, True, None], 1)])
        fixtures.gateway_results(self, response, [0])
        cash = self.save["userInfo"]["player"]["cash"]
        self.send("store", self.market(), [self.options()], sequence=100)
        self.assertEqual(self.save["userInfo"]["player"]["cash"], cash - 14)
        self.assertEqual(self.ledger()[CODE][0], 2)

    def test_new_server_process_reopens_saved_inventory_and_cannot_repeat_paid_purchase(self):
        self.prepare()
        self.send("place", self.shed(), sequence=41)
        ident = self.send("place", self.decor(), sequence=42)["id"]
        saved = copy.deepcopy(next(row for row in self.save["world"]["objectsArray"] if row["id"] == ident))
        self.send("store", saved, [self.options(resource=ident)], sequence=43)
        original = json.loads(self.path.read_text())
        # No listener; the child starts the actual server/catalog/save runtime.
        # All copied cache files and profile writes stay in this test's own dir.
        shutil.copytree(self.bundle.CACHE_DIR, self.saves.parent / "cache", dirs_exist_ok=True)
        payload = self.gateway_payload([self.command("WorldService.performAction",
            ["place", self.shed(), []], 41)])
        program = '''import base64,sys,json
from unittest import mock
import assets
with mock.patch.object(assets, "check_assets"), mock.patch.object(sys, "argv", ["server.py"]):
 import server
client=server.app.test_client()
response=client.post("/flashservices/gateway.php", data=base64.b64decode(sys.argv[1]), content_type="application/x-amf")
print("RESTART_RESPONSE:"+str(response.status_code)+":"+base64.b64encode(response.data).decode())
'''
        env = {**os.environ, "FARMVILLAGE_DATA_DIR": str(self.saves.parent), "PYTHONDONTWRITEBYTECODE": "1"}
        for _ in range(2):
            result = subprocess.run([sys.executable, "-c", program, base64.b64encode(payload).decode()],
                cwd=fixtures.ROOT, env=env, capture_output=True, text=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout[-1000:])
            record = next(line for line in result.stdout.splitlines() if line.startswith("RESTART_RESPONSE:"))
            _, status, raw = record.split(":", 2)
            self.assertEqual(status, "200")
            from pyamf import remoting
            body = remoting.decode(base64.b64decode(raw)).bodies[0][1].body
            self.assertEqual(body["data"][0]["errorType"], 0, body)
            self.assertEqual(json.loads(self.path.read_text()), original)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.save, original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
