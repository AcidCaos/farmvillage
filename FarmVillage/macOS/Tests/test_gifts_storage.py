"""Gift and inventory regressions against the real AMF gateway, isolated farms."""

import copy
import io
import json
from pathlib import Path
import re
from contextlib import redirect_stdout
import sys
import unittest
from unittest import mock
from urllib.parse import parse_qs

from pyamf import remoting

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures


class GiftsAndStorageTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    @staticmethod
    def result(response):
        return remoting.decode(response.data).bodies[0][1].body["data"][0]["data"]

    def test_gift_error_state_and_retention_return_client_contract(self):
        self.write_fixture()
        for name, expected in (("UserService.getGiftboxErrorState", {"giftboxError": 0}),
                               ("UserService.onGiveRetentionItem", {"gifts": []}),
                               ("PresentService.receiveAllPresents", {"presents": []})):
            with self.subTest(name=name):
                response = self.gateway([self.command(name)])
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.result(response), expected)

    def test_send_and_receive_persist_once_with_sender_and_no_expiry(self):
        self.write_fixture()
        other = self.write_fixture("neighbour.json", "neighbour")
        response = self.gateway([self.command("PresentService.buyAndSend", ["cow", ["neighbour"], "normal", None])])
        self.assertTrue(self.result(response)["complete"])
        self.assertEqual(len(json.loads(other.read_text())["localPresents"]), 1)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        response = self.gateway([self.command("PresentService.receiveAllPresents")], uid="neighbour")
        self.assertEqual(self.result(response)["presents"][0]["senderUID"], "fixture-farmer")
        saved = json.loads(other.read_text())
        self.assertEqual(saved["userInfo"]["player"]["storageData"]["-1"]["CW"][:2], [1, ["fixture-farmer"]])
        self.assertEqual(saved["localPresents"], [])
        response = self.gateway([self.command("PresentService.receiveAllPresents")], uid="neighbour")
        self.assertEqual(self.result(response), {"presents": []})

    def test_invalid_followup_preserves_sender_and_recipient_queue(self):
        first = self.write_fixture()
        other = self.write_fixture("neighbour.json", "neighbour")
        original = [first.read_bytes(), other.read_bytes()]
        response = self.gateway([
            self.command("PresentService.buyAndSend", ["cow", ["neighbour"], "normal", None]),
            self.command("WorldService.performAction", ["use", {"id": 999, "itemName": "cow"}, []], 2),
        ])
        results = fixtures.gateway_results(self, response, [0, 29])
        self.assertEqual(len(json.loads(other.read_text())["localPresents"]), 1)
        self.assertEqual(self.player.session("neighbour"), json.loads(other.read_text()))
        self.assertEqual(json.loads(first.read_text())["userInfo"]["player"]["cash"],
                         json.loads(original[0])["userInfo"]["player"]["cash"] - results[0]["data"]["totalCost"])

    def test_static_or_missing_recipient_does_not_charge_or_claim_success(self):
        self.write_fixture()
        before = copy.deepcopy(self.player.session("fixture-farmer"))
        response = self.gateway([self.command("PresentService.buyAndSend", ["cow", ["missing"], "normal", None])])
        self.assertFalse(self.result(response)["complete"])
        self.assertEqual(self.player.session("fixture-farmer")["userInfo"]["player"]["cash"], before["userInfo"]["player"]["cash"])

    def test_gift_page_keeps_login_and_sends_free_gift(self):
        self.write_fixture()
        self.write_fixture("neighbour.json", "neighbour")
        with self.client.session_transaction() as session:
            session["UID"] = "fixture-farmer"
        response = self.client.get("/sn_app_url/gifts.php")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Choose a free gift", response.data)
        with self.client.session_transaction() as session:
            token = session["gift_token"]
            self.assertEqual(session["UID"], "fixture-farmer")
        response = self.client.post("/sn_app_url/gifts.php", data={"token": token, "item": "chicken", "recipients": "neighbour"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.player.session("neighbour")["localPresents"][0]["itemName"], "chicken")

    def test_empty_gift_page_selection_is_friendly(self):
        self.write_fixture()
        self.write_fixture("neighbour.json", "neighbour")
        with self.client.session_transaction() as session:
            session.update(UID="fixture-farmer", gift_token="token")
        response = self.client.post("/sn_app_url/gifts.php", data={"token": "token", "item": "cow"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Choose at least one local farmer", response.data)

    def test_rendered_clients_have_valid_patient_gift_capacity_and_no_eviction_ui(self):
        self.write_fixture()
        with self.client.session_transaction() as session:
            session["UID"] = "fixture-farmer"
        for route, pattern in (("/ruffle.html", r"parameters:\s*'(.+?)'"),
                               ("/play.html", r"flashvars='(.+?)'")):
            with self.subTest(route=route):
                # The native wrapper redirects legacy Flash routes. Render
                # each supported client under its actual wrapper mode.
                with mock.patch.object(self.server, "NATIVE_WRAPPER", route == "/ruffle.html"):
                    response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                flashvars = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
                self.assertIsNotNone(flashvars)
                values = parse_qs(re.sub(r"\s|\\", "", flashvars.group(1)))
                capacity = int(values["GIFTBOX_TOTAL_ITEM_LIMIT"][0])
                # Display.UI multiplies this actual FlashVar by the recovered
                # 0.9 warning threshold. An absent value became zero and warned
                # even with two gifts. Stay within Flash's signed Int range.
                self.assertEqual(capacity, 2147483647)
                self.assertLess(10000, capacity * 0.9)
                self.assertRegex(html, r'"fv_giftBoxDeletion":\s*0\s*,')

    def test_init_retires_email_reward_popup_without_consuming_real_gifts(self):
        for existing_flag in (None, 0):
            with self.subTest(existing_flag=existing_flag):
                path = self.write_fixture()
                saved = json.loads(path.read_text())
                if existing_flag is not None:
                    saved["userInfo"]["player"]["hasReceivedGiftForEmailPermissions"] = existing_flag
                saved["localPresents"] = [{"complete": True, "itemName": "cow", "senderUID": "neighbour",
                                          "presentXp": 0, "regiftItemCode": "CW", "itemContext": "normal"}]
                path.write_text(json.dumps(saved))
                with redirect_stdout(io.StringIO()):
                    self.player.load_saves()
                before = copy.deepcopy(self.player.session("fixture-farmer"))
                response = self.gateway([self.command("UserService.initUser", ["Farmer", 0, True, {}])])
                self.assertEqual(response.status_code, 200)
                result = self.result(response)
                self.assertEqual(result["userInfo"]["player"]["hasReceivedGiftForEmailPermissions"], 1)
                self.assertEqual(result["pendingPresents"], 1)
                after = json.loads(path.read_text())
                self.assertEqual(after["localPresents"], before["localPresents"])
                self.assertEqual(after["userInfo"]["player"]["storageData"], before["userInfo"]["player"]["storageData"])
                self.assertEqual(after["userInfo"]["player"].get("hasReceivedGiftForEmailPermissions"), existing_flag)

    def test_withdrawal_cannot_overdraw_or_add_negative_quantity(self):
        self.write_fixture()
        import storage
        save = self.player.session("fixture-farmer")
        save["userInfo"]["player"]["storageData"]["-1"]["CW"] = [1, [], []]
        self.assertFalse(storage.store_withdraw_item_by_code(save, "CW", 2, -1))
        self.assertEqual(save["userInfo"]["player"]["storageData"]["-1"]["CW"][0], 1)
        for amount in (-1, 0, 1.5, True):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                storage.store_withdraw_item_by_code(save, "CW", amount, -1)

    def test_placement_consumes_exact_inventory_and_ignores_duplicate_flag(self):
        self.write_fixture()
        import storage
        save = self.player.session("fixture-farmer")
        storage.store_deposit_item_by_name(save, "cow", 2, -2)
        self.assertTrue(storage.withdraw_for_placement(save, "cow", [{"isStorageWithdrawal": -2, "isInventoryWithdrawal": True}]))
        self.assertEqual(save["userInfo"]["player"]["storageData"]["-2"]["CW"][0], 1)
        self.assertNotIn("CW", save["userInfo"]["player"]["storageData"]["-1"])

    def test_positive_building_withdrawal_preserves_home_inventory(self):
        self.write_fixture()
        import storage
        save = self.player.session("fixture-farmer")
        save["world"]["objectsArray"].append({"id": 600, "className": "StorageBuilding", "contents": [{"itemCode": "CW", "numItem": 1}]})
        storage.store_deposit_item_by_name(save, "cow", 3, -2)
        storage.withdraw_for_placement(save, "cow", [{"isStorageWithdrawal": 600}])
        self.assertEqual(save["userInfo"]["player"]["storageData"]["-2"]["CW"][0], 3)
        self.assertEqual(save["world"]["objectsArray"][-1]["contents"], [])

    def test_inventory_store_removes_world_object_and_retains_metadata(self):
        self.write_fixture()
        save = self.player.session("fixture-farmer")
        obj = {"id": 600, "className": "Animal", "itemName": "cow", "state": "bare", "position": {"x": 1, "y": 1}}
        save["world"]["objectsArray"].append(copy.deepcopy(obj))
        response = self.gateway([self.command("WorldService.performAction", ["store", obj, [{"target": -2, "resource": 600, "storedItemName": "cow", "metadata": {"uuid": "cow-state"}}]])])
        self.assertEqual(response.status_code, 200)
        self.assertFalse(any(item["id"] == 600 for item in save["world"]["objectsArray"]))
        self.assertEqual(save["userInfo"]["player"]["storageData"]["-2"]["CW"], [1, [], [{"uuid": "cow-state"}]])

    def test_gift_placement_retry_with_same_temp_id_consumes_once(self):
        self.write_fixture()
        import storage
        save = self.player.session("fixture-farmer")
        storage.store_deposit_item_by_name(save, "cow", 2, -1)
        obj = {"id": 64000, "className": "Animal", "itemName": "cow", "state": "bare", "position": {"x": 1, "y": 1}}
        for sequence in (1, 2):
            response = self.gateway([self.command("WorldService.performAction", ["place", obj, [{"isGift": True}]], sequence)])
            self.assertEqual(response.status_code, 200)
        self.assertEqual(save["userInfo"]["player"]["storageData"]["-1"]["CW"][0], 1)
        self.assertEqual(sum(item.get("itemName") == "cow" for item in save["world"]["objectsArray"]), 1)

    def test_absent_gift_cannot_place_a_free_object(self):
        path = self.write_fixture()
        original = path.read_bytes()
        obj = {"id": 64000, "className": "Animal", "itemName": "cow", "state": "bare"}
        response = self.gateway([self.command("WorldService.performAction", ["place", obj, [{"isGift": True}]])])
        fixtures.assert_gateway_rejected(self, response)
        self.assertEqual(path.read_bytes(), original)

    def test_archived_gate_and_received_animal_place_once_and_survive_reload(self):
        path = self.write_fixture()
        import storage
        save = self.player.session("fixture-farmer")
        storage.store_deposit_item_by_name(save, "candycanegate", 1, -1)
        save["localPresents"] = [{"complete": True, "itemName": "cow", "senderUID": "AcidCaos",
                                  "presentXp": 0, "regiftItemCode": "CW", "itemContext": "normal"}]
        balance = tuple(save["userInfo"]["player"][key] for key in ("gold", "cash"))
        response = self.gateway([self.command("PresentService.receiveAllPresents")])
        self.assertEqual(response.status_code, 200)
        objects = [
            {"id": 64000, "className": "Decoration", "itemName": "candycanegate", "position": {"x": 1, "y": 1, "z": 0}},
            {"id": 64001, "className": "Animal", "itemName": "cow", "state": "bare", "position": {"x": 3, "y": 3, "z": 0}},
        ]
        for sequence, obj in enumerate(objects, 1):
            response = self.gateway([self.command("WorldService.performAction", ["place", obj, [{"isGift": True}]], sequence)])
            self.assertEqual(response.status_code, 200)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        reloaded = self.player.session("fixture-farmer")
        self.assertEqual(tuple(reloaded["userInfo"]["player"][key] for key in ("gold", "cash")), balance)
        self.assertEqual(reloaded["localPresents"], [])
        gifts = reloaded["userInfo"]["player"]["storageData"]["-1"]
        self.assertNotIn("CW", gifts)
        self.assertNotIn("UF", gifts)
        for item in ("cow", "candycanegate"):
            self.assertEqual(sum(obj.get("itemName") == item for obj in reloaded["world"]["objectsArray"]), 1)
        self.assertEqual(json.loads(path.read_text())["world"]["objectsArray"], reloaded["world"]["objectsArray"])

    def test_multi_reward_package_unpacks_every_item_once(self):
        self.write_fixture()
        import storage
        from items import get_item_by_name
        save = self.player.session("fixture-farmer")
        package = get_item_by_name("bundle_10")
        storage.store_deposit_item_by_name(save, package["name"], 1, -1)
        storage.consume_by_name(save, package["name"], 1, -1)
        inventory = save["userInfo"]["player"]["storageData"]["-1"]
        self.assertNotIn(package["code"], inventory)
        for reward in package["rewards"]["reward"]:
            self.assertEqual(inventory[reward["value"]][0], int(reward["quantity"]))
        with self.assertRaises(ValueError):
            storage.consume_by_name(save, package["name"], 1, -1)

    def test_unsupported_package_keeps_original_gift(self):
        self.write_fixture()
        import storage
        save = self.player.session("fixture-farmer")
        storage.store_deposit_item_by_name(save, "consume_africaXfer", 1, -1)
        before = copy.deepcopy(save["userInfo"]["player"]["storageData"])
        with self.assertRaises(ValueError):
            storage.consume_by_name(save, "consume_africaXfer", 1, -1)
        self.assertEqual(before, save["userInfo"]["player"]["storageData"])

    def test_consumable_container_rewards_land_in_gift_box(self):
        self.write_fixture()
        import storage
        save = self.player.session("fixture-farmer")
        storage.store_deposit_item_by_name(save, "bundle_10", 1, storage.CONSUME_ID)
        storage.consume_by_name(save, "bundle_10", 1, storage.CONSUME_ID)
        self.assertEqual(save["userInfo"]["player"]["storageData"]["-6"], {})
        self.assertIn("0pjm", save["userInfo"]["player"]["storageData"]["-1"])

    def test_gift_store_into_existing_building_retains_old_contents(self):
        self.write_fixture()
        import storage
        save = self.player.session("fixture-farmer")
        building = {"id": 600, "className": "StorageBuilding", "itemName": "orchard",
                    "contents": [{"itemCode": "CW", "numItem": 1, "importedNote": "keep"}]}
        save["world"]["objectsArray"].append(building)
        storage.store_deposit_item_by_name(save, "chicken", 1, -1)
        storage.store_world_item(save, {**building, "contents": []},
                                 {"storedItemName": "chicken", "isGift": True})
        self.assertEqual(save["userInfo"]["player"]["storageData"]["600"]["CW"][0], 1)
        self.assertEqual(save["userInfo"]["player"]["storageData"]["600"]["CK"][0], 1)
        self.assertEqual(next(row for row in building["contents"] if row["itemCode"] == "CW")["importedNote"], "keep")

    def test_neighbor_load_applies_peaceful_policy_without_mutating_source(self):
        self.write_fixture()
        self.write_fixture("neighbour.json", "neighbour")
        neighbor = self.player.session("neighbour")
        plot = next(obj for obj in neighbor["world"]["objectsArray"] if obj.get("className") == "Plot" and obj.get("itemName"))
        plot.update(state="withered", plantTime=1)
        before = copy.deepcopy(neighbor)
        response = self.gateway([self.command("WorldService.loadNeighborWorld", ["neighbour"])])
        self.assertEqual(response.status_code, 200)
        loaded = next(obj for obj in self.result(response)["world"]["objectsArray"] if obj["id"] == plot["id"])
        self.assertEqual(loaded["state"], "grown")
        self.assertEqual(neighbor, before)


if __name__ == "__main__":
    unittest.main()
