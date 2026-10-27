"""Cellar credit economy over original signed AMF with synthetic private saves.

The owned cellar, imported ledgers and owned gift shovels are fixture inputs.
No historical gift campaign, social reward or authentic starter is claimed.
"""
import copy
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import unittest
from unittest import mock
import pyamf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import test_cove_cellar as cellar_fixtures
import cellar_progression
import items
import storage
import world_travel

NOW = 1800000000


class CoveCellarProgressionTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway
    save = cellar_fixtures.CoveCellarTests.save
    persist = cellar_fixtures.CoveCellarTests.persist

    def prepare(self, world="fisherman", *, current=0, received=0, gifts=0):
        cellar_fixtures.CoveCellarTests.prepare(self, world, gold=1000000)
        self.sequence = 0
        self.cellar = cellar_fixtures.CoveCellarTests.cellar(900)
        self.cellar["imported"] = {"keep": [1, 2]}
        self.save["world"]["objectsArray"] = [copy.deepcopy(self.cellar)]
        self.save["userInfo"]["player"].update(cash=100, featureCredits={
            world: {"InventoryCellar": {"current": current, "received": received,
                                         "imported": {"keep": True}}}})
        self.group = storage.active_inventory_id(self.save)
        self.save["userInfo"]["player"]["storageData"][str(self.group)] = {}
        self.save["userInfo"]["player"]["storageData"]["-1"] = (
            {"v1": [gifts, ["fixture-sender"], [{"fixture": n} for n in range(gifts)]]}
            if gifts else {})
        self.persist()

    @property
    def row(self):
        return self.save["userInfo"]["player"]["featureCredits"][
            self.save["userInfo"]["currentWorldType"]]["InventoryCellar"]

    def options(self, **changes):
        return {"storedItemName": "shovel_item_01", "storedItemCode": "v1",
                "target": 900, "resource": 0, "origin": 0, **changes}

    def send(self, action, params=(), *, snapshot=None, sequence=None, expected=200):
        self.sequence += 1
        ident = self.sequence if sequence is None else sequence
        self.sequence = max(self.sequence, ident)
        request = self.command("WorldService.performAction", [action,
            copy.deepcopy(snapshot if snapshot is not None else self.cellar),
            copy.deepcopy(params) if isinstance(params, dict) else list(params)], sequence=ident)
        with mock.patch("server.timestamp_now", return_value=NOW), mock.patch(
                "commands.timestamp_now", return_value=NOW), mock.patch("engine.timestamp_now", return_value=NOW):
            response = self.gateway([request])
        fixtures.assert_gateway_status(self, response, expected)
        if expected == 200:
            return fixtures.gateway_results(self, response)[0]["data"]

    def rejected(self, action, params=(), **changes):
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.send(action, params, expected=400, **changes)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)

    def reload(self):
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()

    def test_original_shovel_and_redeem_contracts_are_exact(self):
        self.assertEqual(cellar_progression.contract(), {
            "mole": 20, "crystalrock": 40, "sheep_mine": 60,
            "gnomecaveman": 120, "tractorvintage": 200})
        part = items.get_item_by_name("shovel_item_01")
        self.assertEqual(tuple(part[k] for k in ("code", "basketClass", "className", "count", "cash", "buyXp")),
            ("v1", "InventoryCellar", "BuildingPart", "2", "1", "0"))

    def test_owned_gift_shovel_credits_metadata_retry_and_restart(self):
        self.prepare(gifts=2)
        before = copy.deepcopy(self.save["userInfo"]["player"])
        options = self.options(isGift=True, giftMetadataIndex=0)
        result = self.send("store", [options], sequence=11)
        self.assertEqual(result, {"id": 900})
        self.assertEqual((self.row["current"], self.row["received"]), (2, 2))
        player = self.save["userInfo"]["player"]
        self.assertEqual(tuple(player[k] for k in ("gold", "cash", "xp")),
                         tuple(before[k] for k in ("gold", "cash", "xp")))
        self.assertEqual(player["storageData"]["-1"]["v1"], [1, [], [{"fixture": 1}]])
        self.assertEqual(self.row["imported"], {"keep": True})
        self.assertEqual(self.save["world"]["objectsArray"][0]["imported"], {"keep": [1, 2]})
        settled = copy.deepcopy(self.save)
        self.send("store", [options], sequence=11)
        self.assertEqual(self.save, settled)
        self.reload()
        self.send("store", [options], sequence=11)
        self.assertEqual(self.save, settled)
        self.rejected("store", [self.options(isGift=True, numToStore=2)], sequence=11)
        self.send("store", [self.options(isGift=True)], sequence=12)
        self.assertNotIn("v1", self.save["userInfo"]["player"]["storageData"]["-1"])
        self.assertEqual((self.row["current"], self.row["received"]), (4, 4))

    def test_market_shovels_charge_one_cash_each_and_add_two_credits_each_atomically(self):
        self.prepare()
        before = copy.deepcopy(self.save["userInfo"]["player"])
        params = [self.options(numToStore=3, currency="cash")]
        self.send("store", params, sequence=20)
        player = self.save["userInfo"]["player"]
        self.assertEqual(player["cash"], before["cash"] - 3)
        self.assertEqual((player["gold"], player["xp"]), (before["gold"], before["xp"]))
        self.assertEqual((self.row["current"], self.row["received"]), (6, 6))
        settled = copy.deepcopy(self.save)
        self.send("store", params, sequence=20)
        self.assertEqual(self.save, settled)
        self.reload()
        self.send("store", params, sequence=20)
        self.assertEqual(self.save, settled)
        self.save["userInfo"]["player"]["cash"] = 1
        self.persist()
        self.rejected("store", [self.options(numToStore=2)])
        self.rejected("store", [self.options(currency="coins")])

    def test_original_market_blank_currency_uses_authored_cash_price_and_retries(self):
        # Captured original-client FeatureCreditItem options, not a new price.
        for currency in ("", None, "cash"):
            with self.subTest(currency=currency):
                self.prepare(current=18, received=18, gifts=2)
                before = copy.deepcopy(self.save["userInfo"]["player"])
                options = self.options(currency=currency, cameFromLocation=0,
                    storedClassName="FeatureCreditItem", clientQty=-1,
                    clientTotal=-1, containeeItemCode="", metadata=None,
                    containeeMetadata=None, containeeMetadataIndex=-1,
                    isFull=0, isGift=False, numToStore=1)
                self.assertEqual(self.send("store", [options], sequence=80), {"id": 900})
                player = self.save["userInfo"]["player"]
                self.assertEqual(player["cash"], before["cash"] - 1)
                self.assertEqual((self.row["current"], self.row["received"]), (20, 20))
                self.assertEqual(player["storageData"], before["storageData"])
                self.assertEqual(self.row["imported"], {"keep": True})
                settled = copy.deepcopy(self.save)
                self.send("store", [options], sequence=80)
                self.assertEqual(self.save, settled)
                self.reload()
                self.send("store", [options], sequence=80)
                self.assertEqual(self.save, settled)
                for index, invalid in enumerate((False, True, 0, "coins", "FVCASH"), 81):
                    self.rejected("store", [self.options(currency=invalid)], sequence=index)

    def test_original_built_lifecycle_and_legacy_image_keys_keep_earned_capacity(self):
        # StorageBuilding.getCurrentImageName12005 supplies built_<suffix>;
        # CreditsBuilding28912 derives that suffix from received credits.
        for state in ("built", "built_0", "built_1", "built_2"):
            with self.subTest(imported_state=state):
                self.prepare(current=198, received=198)
                obj = self.save["world"]["objectsArray"][0]
                obj.update(state=state, plantTime=1234567890000)
                self.persist()
                self.assertEqual(cellar_progression.capacity(self.save, obj,
                    items.get_item_by_name("hatchstorage")), 198)
                self.send("store", [self.options(currency="")], sequence=90)
                obj = self.save["world"]["objectsArray"][0]
                self.assertEqual((obj["state"], obj["plantTime"]), ("built", 1234567890000))
                self.assertEqual((self.row["current"], self.row["received"]), (200, 200))
                self.assertEqual(obj["imported"], {"keep": [1, 2]})
                self.reload()
                self.assertEqual(self.save["world"]["objectsArray"][0]["state"], "built")
        for state in ("construction", "bare", "built_3", None):
            with self.subTest(invalid_state=state):
                self.prepare()
                self.save["world"]["objectsArray"][0]["state"] = state
                self.persist()
                self.rejected("store", [self.options(currency="")])

    def test_original_amf0_mixed_array_store_and_redeem_retries(self):
        self.prepare(current=38, received=38)
        options = self.options(currency="", cameFromLocation=0,
            storedClassName="FeatureCreditItem", clientQty=-1, clientTotal=-1,
            containeeItemCode="", metadata=None, containeeMetadata=None,
            containeeMetadataIndex=-1, isFull=0, isGift=False, numToStore=1)
        params = pyamf.MixedArray({0: options})
        self.assertEqual(self.send("store", params, sequence=100), {"id": 900})
        self.assertEqual((self.row["current"], self.row["received"]), (40, 40))
        self.assertEqual(self.save["userInfo"]["player"]["cash"], 99)
        accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.send("store", params, sequence=100)
        self.send("store", [options, {"firstWA": True}], sequence=100)
        self.assertEqual(self.save, accepted)
        self.assertEqual(self.path.read_bytes(), disk)
        self.reload()
        self.send("store", params, sequence=100)
        self.assertEqual(self.save, accepted)

        params = pyamf.MixedArray({0: "mole", 1: False, 2: {"firstWA": True}})
        self.assertEqual(self.send("buyRedeemItem", params, sequence=101), {"id": 900})
        self.assertEqual((self.row["current"], self.row["received"]), (20, 40))
        self.assertEqual(self.save["userInfo"]["player"]["cash"], 99)
        code = items.get_item_by_name("mole")["code"]
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-1"][code], [1, [], []])
        accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.send("buyRedeemItem", params, sequence=101)
        self.send("buyRedeemItem", ["mole", False], sequence=101)
        self.assertEqual(self.save, accepted)
        self.assertEqual(self.path.read_bytes(), disk)

    def test_legacy_cellar_projection_is_response_only_then_transaction_persists_built(self):
        for state in ("built_0", "built_1", "built_2"):
            with self.subTest(state=state):
                self.prepare(current=198, received=198)
                obj = self.save["world"]["objectsArray"][0]
                obj.update(state=state, plantTime=1234567890000)
                self.persist()
                durable = copy.deepcopy(self.save["world"])
                projected = cellar_progression.client_world(self.save)
                self.assertIsNot(projected, self.save["world"])
                self.assertEqual(projected, {**durable, "objectsArray": [{**obj, "state": "built"}]})
                self.assertEqual(self.save["world"], durable)
                response = self.gateway([self.command("UserService.initUser",
                    ["Synthetic legacy cellar", 0, True, None], sequence=110)])
                initialized = fixtures.gateway_results(self, response, [0])[0]["data"]
                self.assertEqual(initialized["world"]["objectsArray"][0]["state"], "built")
                self.assertEqual(self.save["world"], durable)
                self.reload()
                self.assertEqual(self.save["world"], durable)
                self.assertEqual((self.row["current"], self.row["received"]), (198, 198))
                self.send("store", [self.options(currency="")],
                    snapshot=initialized["world"]["objectsArray"][0], sequence=111)
                self.assertEqual(self.save["world"]["objectsArray"][0]["state"], "built")
                self.assertEqual(self.save["world"]["objectsArray"][0]["plantTime"], 1234567890000)
                self.assertEqual((self.row["current"], self.row["received"]), (200, 200))

    def test_cellar_projection_excludes_invalid_ambiguous_foreign_and_unsupported_state(self):
        changes = ({"state": "built"}, {"state": "bare"}, {"state": "construction"},
            {"state": "built_3"}, {"deleted": True}, {"id": 0},
            {"isFullyBuilt": False}, {"itemName": "haybale"},
            {"className": "StorageBuilding"})
        for change in changes:
            with self.subTest(change=change):
                self.prepare()
                self.save["world"]["objectsArray"][0].update({"state": "built_0", **change})
                before = copy.deepcopy(self.save)
                self.assertIs(cellar_progression.client_world(self.save), self.save["world"])
                self.assertEqual(self.save, before)
        for failure in ("ambiguous", "invalid_credit", "foreign_identity", "unsupported_world"):
            with self.subTest(failure=failure):
                self.prepare()
                self.save["world"]["objectsArray"][0]["state"] = "built_0"
                if failure == "ambiguous":
                    self.save["world"]["objectsArray"].append({**self.cellar, "id": 901})
                elif failure == "invalid_credit": self.row["received"] = -1
                elif failure == "foreign_identity":
                    self.save[world_travel.STATE_KEY]["inactive"]["farm"]["objectsArray"].append(copy.deepcopy(self.cellar))
                else: self.save["userInfo"]["currentWorldType"] = "rainforest"
                before = copy.deepcopy(self.save)
                self.assertIs(cellar_progression.client_world(self.save), self.save["world"])
                self.assertEqual(self.save, before)

    def test_malformed_positional_envelopes_refuse_without_accounting_changes(self):
        self.prepare(current=40, received=40)
        malformed = {
            "store": ({1: self.options()}, {0: self.options(), 2: {"firstWA": True}},
                {0: self.options(), "0": self.options()}, {"00": self.options()},
                {0: self.options(), "other": 1}, [self.options(), {"firstWA": False}],
                [self.options(), {"firstWA": True, "extra": True}]),
            "buyRedeemItem": ({1: "mole", 2: False}, {0: "mole", 2: False},
                {0: "mole", "0": "mole", 1: False}, {"00": "mole", 1: False},
                {0: "mole", 1: False, "other": 1}, ["mole", False, {"firstWA": False}],
                ["mole", False, {"firstWA": True, "extra": True}], ["mole", False, True]),
        }
        # Direct reducer checks preserve duplicate aliases which AMF itself
        # cannot represent distinctly after decoding its string property keys.
        for action, variants in malformed.items():
            for params in variants:
                with self.subTest(action=action, params=params):
                    before, disk = copy.deepcopy(self.save), self.path.read_bytes()
                    with self.assertRaises(ValueError):
                        cellar_progression.perform(self.save, action, self.cellar, params, request_id=102)
                    self.assertEqual(self.save, before)
                    self.assertEqual(self.path.read_bytes(), disk)
        self.rejected("store", pyamf.MixedArray({1: self.options()}), sequence=102)
        self.rejected("buyRedeemItem", pyamf.MixedArray({0: "mole", 2: False}), sequence=103)

    def test_capacity_is_earned_received_count_and_inventory_full_refusal_is_atomic(self):
        self.prepare(gifts=1)
        inventory = {"id": self.group, "className": "StorageBuilding"}
        hay = {"storedItemName": "haybale", "target": self.group, "origin": 0, "resource": 0}
        self.rejected("store", [hay], snapshot=inventory)
        self.send("store", [self.options(isGift=True)])
        self.assertEqual(cellar_progression.capacity(self.save, self.cellar, items.get_item_by_name("hatchstorage")), 2)
        gold = self.save["userInfo"]["player"]["gold"]
        self.send("store", [{**hay, "numToStore": 2}], snapshot=inventory)
        self.assertEqual(self.save["userInfo"]["player"]["storageData"][str(self.group)]["HB"], [2, [], []])
        self.assertEqual(self.save["userInfo"]["player"]["gold"], gold - 2 * int(items.get_item_by_name("haybale")["cost"]))
        self.rejected("store", [hay], snapshot=inventory)
        self.reload()
        self.rejected("store", [hay], snapshot=inventory)

    def test_all_five_redeems_spend_current_preserve_received_capacity_and_grant_once(self):
        self.prepare(current=440, received=440)
        for index, (name, cost) in enumerate(cellar_progression.contract().items(), 30):
            with self.subTest(name=name):
                current = self.row["current"]
                money = tuple(self.save["userInfo"]["player"][key] for key in ("gold", "cash", "xp"))
                result = self.send("buyRedeemItem", [name, False], sequence=index)
                self.assertEqual(result, {"id": 900})
                self.assertEqual((self.row["current"], self.row["received"]), (current - cost, 440))
                self.assertEqual(cellar_progression.capacity(self.save,
                    self.save["world"]["objectsArray"][0], items.get_item_by_name("hatchstorage")), 440)
                code = items.get_item_by_name(name)["code"]
                self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-1"][code], [1, [], []])
                self.assertEqual(tuple(self.save["userInfo"]["player"][key] for key in ("gold", "cash", "xp")), money)
                settled = copy.deepcopy(self.save)
                self.send("buyRedeemItem", [name, False], sequence=index)
                self.assertEqual(self.save, settled)
        self.assertEqual(self.row["current"], 0)
        self.reload()
        self.send("buyRedeemItem", ["tractorvintage", False], sequence=34)
        self.rejected("buyRedeemItem", ["mole", False])
        self.rejected("buyRedeemItem", ["mole", True])
        self.rejected("buyRedeemItem", ["unknown", False])

    def test_original_redeemItem_mixed_arrays_use_pinned_costs_and_grant_once(self):
        self.prepare(current=440, received=440)
        for index, (name, cost) in enumerate(cellar_progression.contract().items(), 120):
            with self.subTest(name=name):
                current = self.row["current"]
                before_money = tuple(self.save["userInfo"]["player"][k] for k in ("gold", "cash", "xp"))
                params = pyamf.MixedArray({0: name, 1: cost, 2: False, 3: {"firstWA": True}})
                self.assertEqual(self.send("redeemItem", params, sequence=index), {"id": 900})
                self.assertEqual((self.row["current"], self.row["received"]), (current - cost, 440))
                code = items.get_item_by_name(name)["code"]
                self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-1"][code], [1, [], []])
                self.assertEqual(tuple(self.save["userInfo"]["player"][k] for k in ("gold", "cash", "xp")), before_money)
                self.assertEqual(cellar_progression.capacity(self.save,
                    self.save["world"]["objectsArray"][0], items.get_item_by_name("hatchstorage")), 440)
                accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
                self.send("redeemItem", params, sequence=index)
                self.send("redeemItem", [name, cost, False], sequence=index)
                self.assertEqual(self.save, accepted)
                self.assertEqual(self.path.read_bytes(), disk)
        self.reload()
        self.send("redeemItem", ["tractorvintage", 200, False], sequence=124)
        self.assertEqual(self.row["current"], 0)
        self.rejected("redeemItem", ["mole", 20, False], sequence=125)

    def test_original_redeemItem_rejects_forged_price_flags_and_malformed_arguments(self):
        self.prepare(current=440, received=440)
        for cost in (0, -1, 19, 21, 20.5, True, None, "20", float("nan"), float("inf")):
            with self.subTest(cost=cost):
                self.rejected("redeemItem", pyamf.MixedArray({0: "mole", 1: cost, 2: False}))
        for params in (["mole", 20, True], ["mole", 20, 0], ["mole", False],
                ["unknown", 20, False], [[], 20, False], ["mole", 20, False, True],
                ["mole", 20, False, {"firstWA": False}],
                pyamf.MixedArray({0: "mole", 2: 20, 3: False})):
            with self.subTest(params=params): self.rejected("redeemItem", params)
        # PyAMF coerces numeric mixed-array keys to integers while decoding;
        # test the unrecoverable spelling/alias ambiguity at the reducer edge.
        for params in ({0: "mole", "0": "mole", 1: 20, 2: False},
                {"00": "mole", 1: 20, 2: False}):
            before, disk = copy.deepcopy(self.save), self.path.read_bytes()
            with self.assertRaises(ValueError):
                cellar_progression.perform(self.save, "redeemItem", self.cellar, params, request_id=999)
            self.assertEqual(self.save, before)
            self.assertEqual(self.path.read_bytes(), disk)

    def test_first_world_action_trailer_is_accepted_for_store_and_redeem(self):
        self.prepare(current=20, received=20, gifts=1)
        self.send("store", [self.options(isGift=True), {"firstWA": True}])
        self.assertEqual((self.row["current"], self.row["received"]), (22, 22))
        self.send("buyRedeemItem", ["mole", False, {"firstWA": True}])
        self.assertEqual((self.row["current"], self.row["received"]), (2, 22))

    def test_wrong_world_identity_part_source_quantity_and_price_refuse_without_loss(self):
        self.prepare(current=20, received=20, gifts=3)
        for snapshot in ({**self.cellar, "id": 901}, {**self.cellar, "itemName": "haybale"},
                         {**self.cellar, "className": "StorageBuilding"},
                         {**self.cellar, "position": {"x": 8, "y": 4, "z": 0}},
                         {**self.cellar, "worldType": "farm"}):
            with self.subTest(snapshot=snapshot):
                self.rejected("store", [self.options(isGift=True)], snapshot=snapshot)
        for change in ({"storedItemName": "stonepart"}, {"storedItemCode": "0el"}, {"target": 901},
                       {"numToStore": 0}, {"numToStore": -1}, {"numToStore": True}, {"numToStore": 1.5},
                       {"origin": -2, "cameFromLocation": -9}, {"resource": 123},
                       {"currency": "coins"}, {"worldType": "farm"}):
            with self.subTest(change=change):
                self.rejected("store", [self.options(**change)])
        self.rejected("store", [self.options(isGift=True, numToStore=4)])
        self.rejected("store", [self.options(cameFromLocation=-2)])
        self.rejected("buyRedeemItem", ["mole", 0])

    def test_credit_world_isolation_capacity_ceiling_and_imported_overflow_preservation(self):
        self.prepare(current=1300, received=1300)
        self.save["userInfo"]["player"]["featureCredits"]["farm"] = {
            "InventoryCellar": {"current": 777, "received": 777, "keep": True}}
        self.save["userInfo"]["player"]["storageData"][str(self.group)] = {"HB": [1251, [], [{"keep": True}]]}
        self.persist()
        self.assertEqual(cellar_progression.capacity(self.save, self.cellar, items.get_item_by_name("hatchstorage")), 1250)
        self.rejected("store", [{"storedItemName": "haybale", "target": self.group}],
                      snapshot={"id": self.group, "className": "StorageBuilding"})
        self.send("buyRedeemItem", ["mole", False])
        self.assertEqual((self.row["current"], self.row["received"]), (1280, 1300))
        self.assertEqual(self.save["userInfo"]["player"]["featureCredits"]["farm"], {
            "InventoryCellar": {"current": 777, "received": 777, "keep": True}})
        self.assertEqual(self.save["userInfo"]["player"]["storageData"][str(self.group)]["HB"],
                         [1251, [], [{"keep": True}]])
        self.reload()
        self.assertEqual(cellar_progression.record(self.save)["received"], 1300)

    def test_legacy_cove_without_travel_namespace_refuses_foreign_source_withdrawals(self):
        self.prepare()
        # Imported active Cove is still structurally supported without the
        # local travel namespace. It does not establish ownership of Home's
        # inventory, even when imported license flags claim both worlds.
        self.save.pop(world_travel.STATE_KEY)
        self.save["userInfo"]["player"]["storageData"]["-2"] = {
            "v1": [1, [], [{"keep": "foreign-shovel"}]],
            "HB": [1, [], [{"keep": "foreign-decoration"}]]}
        hay = {"id": 64001, "className": "Decoration", "itemName": "haybale",
               "state": "static", "position": {"x": 12, "y": 12, "z": 0}}
        for licenses in ({}, {"farm": {"world": True}, "fisherman": {"world": True}}):
            self.save["userInfo"]["unlockedWorldContentLicenses"] = licenses
            self.persist()
            with self.subTest(licenses=licenses):
                self.rejected("store", [self.options(cameFromLocation=-2)])
                self.rejected("place", [{"isStorageWithdrawal": -2,
                    "isInventoryWithdrawal": True}], snapshot=hay)

    def test_malformed_owned_shovel_and_license_sources_are_preserved(self):
        self.prepare()
        import cove_shipping
        malformed = ([True, [], []], [1.5, [], []], [-1, [], []], [1, None, []],
                     [1, [], None], [1, [], [{"keep": 1}, {"keep": 2}]],
                     [1, [], [], {"opaque": True}])
        for entry in malformed:
            with self.subTest(entry=entry):
                # Some rows are rejected by the save loader itself. Prove the
                # direct reducer preserves them without claiming they load.
                self.save["userInfo"]["player"]["storageData"]["-1"] = {
                    "v1": copy.deepcopy(entry), "06x": copy.deepcopy(entry)}
                self.save["userInfo"]["player"]["storageData"][str(self.group)] = {"v1": copy.deepcopy(entry)}
                for operation in (
                    lambda: cellar_progression.perform(self.save, "store", self.cellar,
                        [self.options(isGift=True)], request_id=100),
                    lambda: cellar_progression.perform(self.save, "store", self.cellar,
                        [self.options(cameFromLocation=self.group)], request_id=101),
                    lambda: cove_shipping.consume(self.save, 1, -1)):
                    before, disk = copy.deepcopy(self.save), self.path.read_bytes()
                    with self.assertRaises(ValueError):
                        operation()
                    self.assertEqual(self.save, before)
                    self.assertEqual(self.path.read_bytes(), disk)
        # Structurally loadable malformed quantities/metadata also reach the
        # signed-AMF refusal path, without charging or normalizing the import.
        for entry in ([1.5, [], []], [-1, [], []], [1, [], [{"keep": 1}, {"keep": 2}]]):
            self.save["userInfo"]["player"]["storageData"]["-1"] = {
                "v1": copy.deepcopy(entry), "06x": copy.deepcopy(entry)}
            self.save["userInfo"]["player"]["storageData"][str(self.group)] = {"v1": copy.deepcopy(entry)}
            self.persist()
            self.rejected("store", [self.options(isGift=True)])
            self.rejected("store", [self.options(cameFromLocation=self.group)])
            self.rejected("use", [{"storageId": -1, "itemCount": 1}], snapshot={
                "id": 64010, "className": "CRewardConsumable", "itemName": "consume_fishermanXfer"})

    def test_licensed_foreign_opaque_placement_and_fractional_source_are_unavailable(self):
        self.prepare()
        self.save["userInfo"]["unlockedWorldContentLicenses"] = {
            "farm": {"world": True}, "fisherman": {"world": True}}
        self.save["userInfo"]["player"]["storageData"]["-2"] = {"HB": [1, [], [{"opaque": "retain"}]]}
        self.persist()
        hay = {"id": 64001, "className": "Decoration", "itemName": "haybale",
               "state": "static", "position": {"x": 12, "y": 12, "z": 0}}
        self.rejected("place", [{"isStorageWithdrawal": -2, "isInventoryWithdrawal": True}], snapshot=hay)
        self.rejected("place", [{"isStorageWithdrawal": -2.5, "isInventoryWithdrawal": True}], snapshot=hay)

    def test_gift_metadata_selection_is_a_whole_owned_unit_selector(self):
        self.prepare(gifts=2)
        for selector in (0.5, True, -2, 2):
            with self.subTest(selector=selector):
                self.rejected("store", [self.options(isGift=True, giftMetadataIndex=selector)])
        self.send("store", [self.options(isGift=True, giftMetadataIndex=1)])
        self.assertEqual(self.save["userInfo"]["player"]["storageData"]["-1"]["v1"],
                         [1, [], [{"fixture": 0}]])
        self.assertEqual((self.row["current"], self.row["received"]), (2, 2))

    def test_duplicate_imported_cellars_do_not_multiply_world_credits_or_grant_progression(self):
        self.prepare(current=100, received=100, gifts=1)
        self.save["world"]["objectsArray"].append({**copy.deepcopy(self.cellar), "id": 901,
            "position": {"x": 20, "y": 20, "z": 0}})
        self.persist()
        before = copy.deepcopy(self.save)
        with self.assertRaisesRegex(ValueError, "one|limit|single"):
            cellar_progression.capacity(self.save, self.cellar, items.get_item_by_name("hatchstorage"))
        self.assertEqual(self.save, before)
        self.rejected("store", [self.options(isGift=True)])
        self.rejected("buyRedeemItem", ["mole", False])
        self.rejected("store", [{"storedItemName": "haybale", "target": self.group}],
                      snapshot={"id": self.group, "className": "StorageBuilding"})
        self.reload()
        self.assertEqual(len([o for o in self.save["world"]["objectsArray"]
                              if o.get("itemName") == "hatchstorage"]), 2)
        self.assertEqual((self.row["current"], self.row["received"]), (100, 100))

    def test_new_village_starts_with_zero_feature_credits_without_rewriting_scalar_import(self):
        # The retained historical template contains a scalar placeholder. A
        # new village must receive a fresh empty ledger, while existing saves
        # and the template remain untouched.
        self.path = self.write_fixture()
        self.assertEqual(self.save["userInfo"]["player"]["featureCredits"], "10")
        imported, disk = copy.deepcopy(self.save), self.path.read_bytes()
        with redirect_stdout(io.StringIO()), mock.patch("player.timestamp_now", return_value=NOW):
            uid = self.player.new_village("Zero Credit Farmer")
        created = self.player.session(uid)
        self.assertEqual(created["userInfo"]["player"]["featureCredits"], {})
        self.assertEqual(cellar_progression.record(created), {"current": 0, "received": 0})
        self.assertEqual(self.save, imported)
        self.assertEqual(self.path.read_bytes(), disk)
        self.assertEqual(self.initial["userInfo"]["player"]["featureCredits"], "10")
        self.reload()
        self.assertEqual(self.player.session(uid)["userInfo"]["player"]["featureCredits"], {})
        self.assertEqual(cellar_progression.record(self.player.session(uid)), {"current": 0, "received": 0})
        self.assertEqual(self.save["userInfo"]["player"]["featureCredits"], "10")

    def test_scalar_imported_feature_credits_refuse_cellar_without_conversion_or_phantom_capacity(self):
        self.prepare(gifts=1)
        self.save["userInfo"]["player"]["featureCredits"] = 10
        self.persist()
        self.reload()
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "ledger"):
            cellar_progression.record(self.save)
        with self.assertRaises(ValueError):
            cellar_progression.capacity(self.save, self.cellar, items.get_item_by_name("hatchstorage"))
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)
        self.rejected("store", [self.options(isGift=True)])
        self.rejected("buyRedeemItem", ["mole", False])
        self.rejected("store", [{"storedItemName": "haybale", "target": self.group}],
                      snapshot={"id": self.group, "className": "StorageBuilding"})
        self.assertEqual(self.save["userInfo"]["player"]["featureCredits"], 10)
        self.reload()
        self.assertEqual(self.save["userInfo"]["player"]["featureCredits"], 10)

    def test_invalid_imported_ledgers_and_incomplete_cellar_preserve_save(self):
        self.prepare(gifts=1)
        original = copy.deepcopy(self.row)
        for mutation in ({"current": -1}, {"received": True}, {"current": 3, "received": 2},
                         {"current": 1.5}, {"received": None}):
            self.save["userInfo"]["player"]["featureCredits"]["fisherman"]["InventoryCellar"] = {**original, **mutation}
            self.persist()
            with self.subTest(mutation=mutation):
                self.rejected("store", [self.options(isGift=True)])
        self.save["userInfo"]["player"]["featureCredits"]["fisherman"]["InventoryCellar"] = original
        self.save["world"]["objectsArray"][0]["isFullyBuilt"] = False
        self.persist()
        self.rejected("store", [self.options(isGift=True)])


if __name__ == "__main__":
    unittest.main()
