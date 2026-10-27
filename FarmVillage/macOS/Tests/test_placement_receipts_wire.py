"""Original AMF NaN placement fields retain durable, packet-bound retries."""
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
import test_rainforest_containers_wire as containers
import items
import placement_receipts
import world_travel

NOW = containers.NOW


class PlacementReceiptWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway
    save = containers.RainforestContainerWireTests.save
    persist = containers.RainforestContainerWireTests.persist
    prepare = containers.RainforestContainerWireTests.prepare
    obj = containers.RainforestContainerWireTests.obj
    snapshot = staticmethod(containers.RainforestContainerWireTests.snapshot)
    send = containers.RainforestContainerWireTests.send
    reject = containers.RainforestContainerWireTests.reject
    gift = containers.RainforestContainerWireTests.gift

    @staticmethod
    def with_original_nan(snapshot):
        return {**snapshot, "plantTime": float("nan"), "tempId": float("nan"),
                "buildTime": float("nan")}

    def test_signed_building_nan_fields_first_placement_and_packet_bound_replay(self):
        self.prepare()
        packet = self.with_original_nan(self.snapshot("xrf_gnomegarden_finished"))
        ident = self.send("place", packet, sequence=501)["id"]
        self.assertEqual(self.save["userInfo"]["player"]["cash"], 964)
        default = items.get_item_by_name("gnome_xrf_headdresstte")["code"]
        self.assertEqual(self.obj(ident)["contents"], [{"itemCode": default, "numItem": 1}])
        accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.assertEqual(self.send("place", packet, sequence=501)["id"], ident)
        self.assertEqual(self.save, accepted)
        self.assertEqual(self.path.read_bytes(), disk)
        # These are the three legacy fields normalized by the shared handler.
        # Their canonical null spelling must identify the same request, rather
        # than charging again or rejecting a harmless encoding difference.
        canonical = {**packet, "plantTime": None, "tempId": None, "buildTime": None}
        self.assertEqual(self.send("place", canonical, sequence=501)["id"], ident)
        self.assertEqual(self.save, accepted)
        changed = copy.deepcopy(packet); changed["position"]["x"] += 1
        self.reject("place", changed, sequence=501)
        self.assertEqual(self.save, accepted)
        self.assertIn("501", self.save[placement_receipts.KEY])

    def test_signed_existing_plot_nan_plant_replay_preserves_exact_charge_and_clock(self):
        self.prepare()
        plot = {"id": 64020, "className": "Plot", "itemName": None,
                "state": "plowed", "position": {"x": 30, "y": 30, "z": 0}}
        ident = self.send("plow", plot, sequence=601)["id"]
        packet = self.with_original_nan({**self.obj(ident),
            "itemName": "xrf_wildpintobean", "state": "planted"})
        gold = self.save["userInfo"]["player"]["gold"]
        self.assertEqual(self.send("place", packet, sequence=602)["id"], ident)
        self.assertEqual(self.save["userInfo"]["player"]["gold"], gold - 145)
        self.assertEqual(self.obj(ident)["plantTime"], NOW * 1000)
        accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.send("place", packet, sequence=602)
        self.assertEqual(self.save, accepted)
        self.assertEqual(self.path.read_bytes(), disk)
        # Arbitrary non-finite snapshot fields are not covered by the legacy
        # timestamp normalization and must fail without consuming currency.
        other = self.with_original_nan(self.snapshot("xrf_gnomegarden_finished", 64021, 5, 5))
        other["unrecognizedNan"] = float("nan")
        self.reject("place", other, sequence=603)
        self.assertEqual(self.save, accepted)

    def test_trusted_gnome_unit_metadata_survives_forged_move_and_container_deposit(self):
        self.prepare()
        garden = self.send("place", self.snapshot("xrf_gnomegarden_finished"), sequence=801)["id"]
        trusted = {"variant": "trusted-fixture", "opaque": {"keep": [1, 2]}}
        gnome = self.gift("gnome_xrf_headdresstte", extras=[trusted])
        packet = self.snapshot(gnome["name"], 64022, 20, 20)
        packet["metadata"] = {"forged": "placement"}
        ident = self.send("place", packet, [{"isGift": True}], sequence=802)["id"]
        self.assertEqual(self.obj(ident)["metadata"], trusted)
        moved = copy.deepcopy(self.obj(ident))
        moved.update(metadata={"forged": "move"}, position={"x": 26, "y": 26, "z": 0})
        self.send("move", moved, sequence=803)
        self.assertEqual(self.obj(ident)["metadata"], trusted)
        self.send("store", self.obj(garden), [{"storedItemName": gnome["name"],
            "resource": ident, "metadata": {"forged": "deposit"}}], sequence=804)
        self.assertFalse(any(row.get("id") == ident for row in self.save["world"]["objectsArray"]))
        ledger = self.save["userInfo"]["player"]["storageData"][str(garden)][gnome["code"]]
        self.assertEqual((ledger[0], ledger[2]), (2, [trusted]))
        self.assertEqual(self.obj(garden)["contents"], [{"itemCode": gnome["code"], "numItem": 2}])
        # Sparse metadata means the untagged default occupant comes out first.
        bare = self.send("place", self.snapshot(gnome["name"], 64023, 32, 32),
            [{"isStorageWithdrawal": garden}], sequence=805)["id"]
        self.assertNotIn("metadata", self.obj(bare))
        forged = copy.deepcopy(self.obj(bare))
        forged.update(metadata={"forged": "new-move"}, position={"x": 36, "y": 36, "z": 0})
        self.send("move", forged, sequence=806)
        self.assertNotIn("metadata", self.obj(bare))
        self.assertEqual(self.save["userInfo"]["player"]["storageData"][str(garden)][gnome["code"]][2], [trusted])

    def test_fresh_server_process_replays_saved_nan_receipt_without_charge_or_default_gnome(self):
        self.prepare()
        packet = self.with_original_nan(self.snapshot("xrf_gnomegarden_finished"))
        ident = self.send("place", packet, sequence=701)["id"]
        original = json.loads(self.path.read_text())
        payload = self.gateway_payload([self.command("WorldService.performAction",
            ["place", packet, []], 701)])
        shutil.copytree(self.bundle.CACHE_DIR, self.saves.parent / "cache", dirs_exist_ok=True)
        program = '''import base64,sys
from unittest import mock
import assets
with mock.patch.object(assets,"check_assets"), mock.patch.object(sys,"argv",["server.py"]):
 import server
response=server.app.test_client().post("/flashservices/gateway.php",data=base64.b64decode(sys.argv[1]),content_type="application/x-amf")
print("REVIEW_RESPONSE:"+str(response.status_code)+":"+base64.b64encode(response.data).decode())
'''
        env = {**os.environ, "FARMVILLAGE_DATA_DIR": str(self.saves.parent),
               "PYTHONDONTWRITEBYTECODE": "1"}
        for _ in range(2):
            child = subprocess.run([sys.executable, "-B", "-c", program,
                base64.b64encode(payload).decode()], cwd=fixtures.ROOT, env=env,
                capture_output=True, text=True, timeout=90)
            self.assertEqual(child.returncode, 0, child.stderr + child.stdout[-1000:])
            record = next(row for row in child.stdout.splitlines() if row.startswith("REVIEW_RESPONSE:"))
            _, status, raw = record.split(":", 2)
            self.assertEqual(status, "200")
            from pyamf import remoting
            response = remoting.decode(base64.b64decode(raw)).bodies[0][1].body["data"][0]
            self.assertEqual(response["errorType"], 0, response)
            self.assertEqual(response["data"]["id"], ident)
            self.assertEqual(json.loads(self.path.read_text()), original)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.save, original)

    def test_trusted_gnome_metadata_survives_ordinary_inventory_route(self):
        self.prepare()
        self.send("place", self.snapshot("toolshedpink", 64050, 5, 5), sequence=901)
        trusted = {"variant": "original-unit", "opaque": {"keep": [3, 4]}}
        gnome = self.gift("gnome_xrf_headdresstte", extras=[trusted])
        ident = self.send("place", self.snapshot(gnome["name"], 64051, 20, 20),
            [{"isGift": True}], sequence=902)["id"]
        self.send("store", copy.deepcopy(self.obj(ident)), [{"storedItemName": gnome["name"],
            "resource": ident, "target": -26, "metadata": {"forged": "inventory"}}], sequence=903)
        ledger = self.save["userInfo"]["player"]["storageData"]["-26"][gnome["code"]]
        self.assertEqual((ledger[0], ledger[2]), (1, [trusted]))
        packet = self.snapshot(gnome["name"], 64052, 26, 26)
        packet["metadata"] = {"forged": "withdrawal"}
        restored = self.send("place", packet, [{"isInventoryWithdrawal": True}], sequence=904)["id"]
        self.assertEqual(self.obj(restored)["metadata"], trusted)
        self.assertNotIn(gnome["code"], self.save["userInfo"]["player"]["storageData"]["-26"])
        market = self.snapshot("gnome_xrf_ballgame", 64053, 32, 32)
        market["metadata"] = {"forged": "market-unit"}
        gold = self.save["userInfo"]["player"]["gold"]
        bought = self.send("place", market, sequence=905)["id"]
        self.assertEqual(self.save["userInfo"]["player"]["gold"], gold-50000)
        self.assertNotIn("metadata", self.obj(bought))


if __name__ == "__main__":
    unittest.main(verbosity=2)
