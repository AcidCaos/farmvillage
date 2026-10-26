"""October protocol acceptance on disposable saves; not browser acceptance."""
import copy
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures  # Resolve disposable data before product imports.
import october_village


class OctoberActionTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    def prepare(self):
        self.other_path = self.write_fixture("existing-export.json", "existing-farmer")
        self.other_bytes = self.other_path.read_bytes()
        with redirect_stdout(io.StringIO()):
            classic_response = self.client.post("/new.html", data={"name": "Classic action control"})
        self.assertEqual(classic_response.status_code, 302)
        with self.client.session_transaction() as session:
            control_uid = session["UID"]
        control_created = copy.deepcopy(self.player.session(control_uid)["userInfo"]["player"])
        self.assertEqual({key: control_created[key] for key in ("gold", "cash", "xp", "energy")},
                         {"gold": 200, "cash": 5, "xp": 0, "energy": 45})
        # Only the acceptance gate is opened for this synthetic farm. The real
        # creation, catalog, gateway, action handlers and persistence run intact.
        with mock.patch.object(october_village, "AVAILABLE", True), redirect_stdout(io.StringIO()):
            response = self.client.post("/new.html", data={
                "name": "October action acceptance", "preset": october_village.PRESET})
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            self.uid = session["UID"]
        self.assertNotEqual(self.uid, "existing-farmer")
        self.path = self.saves / (self.uid + ".save.json")
        self.assertTrue(self.path.is_file())
        created = copy.deepcopy(self.save()["userInfo"]["player"])
        self.assertEqual({key: created[key] for key in ("gold", "cash", "xp", "energy")},
                         {"gold": 200, "cash": 5, "xp": 0, "energy": 45})
        self.assertEqual(created["storageData"], control_created["storageData"])
        # Original gameSettings.xml: boughtdecorations/A009 has a yellow tier
        # at 5, rewarding 25 XP and a picnic table; the next tier starts at 50.
        # Ownership includes authored starter props, not just bought items.
        # Derive the expected award from the actual loaded original metadata.
        settings = self.catalogs[0]
        definition = next(row for row in settings.get_game_settings()["achievements"]["achievement"]
                          if row["@name"] == "boughtdecorations")
        self.assertEqual(definition["@code"], "A009")
        tiers = definition["level"]
        self.assertEqual([int(row["@count"]) for row in tiers], [5, 50, 100, 250])
        first = tiers[0]
        self.assertEqual((int(first["@xp"]), first["@gift"]), (25, "picnictable"))
        items = self.catalogs[1]
        decorations = sum((items.get_item_by_name(obj.get("itemName")) or {}).get("type") == "decoration"
                          for obj in self.save()["world"]["objectsArray"])
        self.assertEqual(decorations, 26)
        self.assertTrue(int(first["@count"]) <= decorations < int(tiers[1]["@count"]))
        gift = items.get_item_by_name(first["@gift"])
        self.assertIsNotNone(gift)
        xp_after_award = created["xp"] + int(first["@xp"])
        original_levels = settings.get_game_settings()["levels"]["level"]
        thresholds = {int(row["@num"]): int(row["@requiredXP"]) for row in original_levels}
        self.assertEqual({level: thresholds[level] for level in (1, 2, 3)}, {1: 0, 2: 15, 3: 30})
        old_level = max(level for level, xp in thresholds.items() if xp <= created["xp"])
        new_level = max(level for level, xp in thresholds.items() if xp <= xp_after_award)
        reward_cap = settings.get_farming_int("highestLevelForFCReward")
        self.assertEqual(reward_cap, 250)
        self.assertEqual((old_level, new_level), (1, 2))
        self.expected_october_startup = {
            "gold": created["gold"] + int(first.get("@coins") or 0),
            "cash": created["cash"] + min(new_level, reward_cap) - min(old_level, reward_cap),
            "xp": xp_after_award, "energy": created["energy"]}
        self.assertEqual(self.expected_october_startup, {"gold": 200, "cash": 6, "xp": 25, "energy": 45})

        # Run actual startup for the Classic control and the October farm.
        # Classic has no decoration ownership award; preserve its bytes while
        # testing October's separate, legitimately earned starting ribbon.
        self.normal_startup(control_uid, "Classic action control")
        control_player = self.player.session(control_uid)["userInfo"]["player"]
        self.classic_startup = {key: control_player[key] for key in ("gold", "cash", "xp", "energy")}
        self.assertEqual(self.classic_startup, {"gold": 200, "cash": 5, "xp": 0, "energy": 45})
        self.assertEqual(control_player["achCounters"][definition["@code"]], 0)
        self.assertEqual(control_player["achievements"].get(definition["@code"], -1), -1)
        self.control_path = self.saves / (control_uid + ".save.json")
        self.control_bytes = self.control_path.read_bytes()
        self.normal_startup(self.uid, "October action acceptance")
        player = self.save()["userInfo"]["player"]
        self.assertEqual(self.balances(), self.expected_october_startup)
        self.assertEqual(player["achCounters"][definition["@code"]], decorations)
        self.assertEqual(player["achievements"][definition["@code"]], 0)
        expected_gifts = copy.deepcopy(created["storageData"].get("-1", {}))
        expected_gifts[gift["code"]] = [1, [], []]
        self.assertEqual(player["storageData"]["-1"], expected_gifts)
        earned_inventory = copy.deepcopy(player["storageData"])
        # A second real login/init may refresh ownership counters but must
        # neither pay the earned tier again nor duplicate its picnic-table gift.
        self.normal_startup(self.uid, "October action acceptance")
        self.assertEqual(self.balances(), self.expected_october_startup)
        self.assertEqual(self.save()["userInfo"]["player"]["storageData"], earned_inventory)
        self.assertEqual(self.save()["userInfo"]["player"]["achievements"][definition["@code"]], 0)
        self.assertEqual(self.save()["userInfo"]["player"]["achCounters"][definition["@code"]], decorations)
        self.sequence = 2
        self.assertEqual(self.other_path.read_bytes(), self.other_bytes)
        return self.save()

    def normal_startup(self, uid, name):
        with redirect_stdout(io.StringIO()):
            login = self.client.post("/", data={"UID": uid})
        self.assertEqual(login.status_code, 302)
        response = self.gateway([
            self.command("UserService.initUser", [name, 0, True, {}], 1),
            self.command("UserService.postInit", [], 2),
        ], uid=uid)
        fixtures.gateway_results(self, response, errors=[0, 0])

    def save(self):
        return self.player.session(self.uid)

    def object(self, identity):
        return next(obj for obj in self.save()["world"]["objectsArray"] if obj["id"] == identity)

    def balances(self):
        player = self.save()["userInfo"]["player"]
        return {key: player[key] for key in ("gold", "cash", "xp", "energy")}

    def action(self, name, snapshot, params=None, *, error=0):
        self.sequence += 1
        response = self.gateway([self.command("WorldService.performAction",
            [name, copy.deepcopy(snapshot), copy.deepcopy(params or [])], self.sequence)], uid=self.uid)
        return fixtures.gateway_results(self, response, errors=[error])[0]["data"]

    def reload(self):
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.other_path.read_bytes(), self.other_bytes)
        self.assertEqual(self.control_path.read_bytes(), self.control_bytes)
        self.assertIsNotNone(self.player.session(self.uid))
        return self.save()

    def test_every_borrowed_decoration_moves_stores_and_replaces_without_charge_or_crop_changes(self):
        save = self.prepare()
        original_balances = self.balances()
        original_inventory = copy.deepcopy(save["userInfo"]["player"]["storageData"])
        starter = copy.deepcopy(save["world"]["objectsArray"][:7])
        provenance = copy.deepcopy(save[october_village.STATE_KEY])
        item_names = [obj["itemName"] for obj in save["world"]["objectsArray"]]
        items = self.catalogs[1]

        decorations = [name for name, row in october_village.PALETTE.items()
                       if row["type"] == "decoration"]
        for index, name in enumerate(decorations):
            with self.subTest(item=name):
                item = items.get_item_by_name(name)
                self.assertFalse(item.get("requirements"))
                self.assertFalse(item.get("terrainSet"))
                original = copy.deepcopy(next(obj for obj in self.save()["world"]["objectsArray"]
                                              if obj.get("itemName") == name))
                original_id = original["id"]
                moved = copy.deepcopy(original)
                # This 10×10 patch is clear of the barn, crops and all authored
                # props. Re-place each item at its original spot before the
                # next case, keeping the shared move destination clear.
                moved["position"] = {"x": 36, "y": 26, "z": 0}
                result = self.action("move", moved)
                self.assertEqual(result["id"], original_id)
                self.assertEqual(self.object(original_id)["position"], moved["position"])
                self.assertEqual(self.balances(), original_balances)

                options = {"origin": "0", "cameFromLocation": 0, "resource": original_id,
                    "isGift": False, "isStorageWithdrawal": 0, "target": -2,
                    "code": item["code"], "storedItemCode": item["code"],
                    "storedItemName": name, "storedClassName": original["className"],
                    "currency": None, "metadata": None}
                self.action("store", moved, [options])
                self.assertFalse(any(obj["id"] == original_id for obj in self.save()["world"]["objectsArray"]))
                self.assertEqual(self.save()["userInfo"]["player"]["storageData"]["-2"][item["code"]],
                                 [1, [], []])
                self.assertEqual(self.balances(), original_balances)
                stored_bytes = self.path.read_bytes()
                # A transport retry whose source has disappeared must reject,
                # rather than buying or duplicating another decoration.
                self.action("store", moved, [options], error=29)
                self.assertEqual(self.path.read_bytes(), stored_bytes)
                self.reload()
                self.assertEqual(self.save()["userInfo"]["player"]["storageData"]["-2"][item["code"]],
                                 [1, [], []])

                placed = copy.deepcopy(original)
                placed["id"] = 64000 + index
                placed.pop("tempId", None)
                withdrawal = [{"isGift": False, "isInventoryWithdrawal": True,
                               "isStorageWithdrawal": -2}]
                result = self.action("place", placed, withdrawal)
                new_id = result["id"]
                self.assertNotEqual(new_id, original_id)
                restored = self.object(new_id)
                self.assertEqual((restored["itemName"], restored["className"], restored["position"]),
                                 (name, original["className"], original["position"]))
                self.assertNotIn(item["code"], self.save()["userInfo"]["player"]["storageData"]["-2"])
                self.assertEqual(self.balances(), original_balances)
                # The same temporary-ID placement is an accepted free retry,
                # consuming no second inventory unit or catalog payment.
                retried = self.action("place", placed, withdrawal)
                self.assertEqual(retried["id"], new_id)
                self.assertEqual(self.balances(), original_balances)
                self.reload()
                self.assertEqual(self.object(new_id)["position"], original["position"])
                self.assertEqual(self.save()["userInfo"]["player"]["storageData"], original_inventory)
                self.assertEqual(self.save()["world"]["objectsArray"][:7], starter)
                self.assertEqual(self.save()[october_village.STATE_KEY], provenance)
                self.assertCountEqual([obj["itemName"] for obj in self.save()["world"]["objectsArray"]],
                                      item_names)

    def test_normal_harvest_plow_and_plant_pay_catalog_amounts_and_keep_server_timer_on_reload(self):
        save = self.prepare()
        before = self.balances()
        self.assertEqual(before, self.expected_october_startup)
        crop = copy.deepcopy(next(obj for obj in save["world"]["objectsArray"]
                                  if obj.get("className") == "Plot" and obj.get("state") == "grown"))
        untouched = {obj["id"]: copy.deepcopy(obj) for obj in save["world"]["objectsArray"]
                     if obj["id"] != crop["id"]}
        provenance = copy.deepcopy(save[october_village.STATE_KEY])
        inventory = copy.deepcopy(save["userInfo"]["player"]["storageData"])
        items = self.catalogs[1]
        harvested_item = items.get_item_by_name(crop["itemName"])
        seed = items.get_item_by_name("strawberry")

        fallow = dict(crop, state="fallow", plantTime=0)
        self.action("harvest", fallow)
        after_harvest = {**before, "gold": before["gold"] + int(harvested_item["coinYield"])}
        self.assertEqual(self.balances(), after_harvest)
        self.assertEqual(self.object(crop["id"])["state"], "fallow")
        self.action("harvest", fallow)
        self.assertEqual(self.balances(), after_harvest)

        plowed = dict(fallow, state="plowed")
        self.action("plow", plowed)
        after_plow = {**after_harvest, "gold": after_harvest["gold"] - 15, "xp": before["xp"] + 1}
        self.assertEqual(self.balances(), after_plow)
        self.action("plow", plowed)
        self.assertEqual(self.balances(), after_plow)

        planting = dict(plowed, itemName="strawberry", state="planted", plantTime=1)
        started = int(time.time()) * 1000
        self.action("place", planting)
        finished = (int(time.time()) + 1) * 1000
        clock = self.object(crop["id"])["plantTime"]
        self.assertGreaterEqual(clock, started)
        self.assertLessEqual(clock, finished)
        self.assertNotEqual(clock, 1)
        expected = {**after_plow, "gold": after_plow["gold"] - int(seed["cost"]),
                    "xp": after_plow["xp"] + int(seed["plantXp"])}
        self.assertEqual(self.balances(), expected)
        self.action("place", planting)
        self.assertEqual(self.balances(), expected)
        self.assertEqual(self.object(crop["id"])["plantTime"], clock)

        planted_bytes = self.path.read_bytes()
        self.action("harvest", dict(planting, state="fallow", plantTime=0), error=29)
        self.assertEqual(self.path.read_bytes(), planted_bytes)
        self.reload()
        self.assertEqual(self.balances(), expected)
        self.assertEqual((self.object(crop["id"])["state"], self.object(crop["id"])["itemName"],
                          self.object(crop["id"])["plantTime"]), ("planted", "strawberry", clock))
        self.assertEqual(self.save()["userInfo"]["player"]["storageData"], inventory)
        self.assertEqual(self.save()[october_village.STATE_KEY], provenance)
        for identity, obj in untouched.items():
            self.assertEqual(self.object(identity), obj)

    def test_each_starter_tree_harvest_uses_original_yield_cooldown_and_once_only_progression(self):
        save = self.prepare()
        items, settings = self.catalogs[1], self.catalogs[0]
        names = [name for name, record in october_village.PALETTE.items() if record["type"] == "tree"]
        self.assertEqual(len(names), 3)
        definitions = {row["@name"]: row for row in settings.get_game_settings()["achievements"]["achievement"]}
        total = definitions["harvesttrees"]
        variety = definitions["harvesttreetype"]
        self.assertEqual((total["@code"], int(total["level"][0]["@count"])), ("A006", 20))
        first_variety = variety["level"][0]
        self.assertEqual((variety["@code"], int(first_variety["@count"]),
                          int(first_variety["@xp"]), int(first_variety["@coins"]), first_variety["@gift"]),
                         ("A013", 3, 10, 500, "plum"))
        gift = items.get_item_by_name(first_variety["@gift"])
        self.assertIsNotNone(gift)
        levels = {int(row["@num"]): int(row["@requiredXP"])
                  for row in settings.get_game_settings()["levels"]["level"]}
        cap = settings.get_farming_int("highestLevelForFCReward")
        expected = self.balances()
        expected_inventory = copy.deepcopy(save["userInfo"]["player"]["storageData"])
        provenance = copy.deepcopy(save[october_village.STATE_KEY])

        for index, name in enumerate(names, 1):
            with self.subTest(tree=name):
                item = items.get_item_by_name(name)
                self.assertEqual((item["type"], item["growTime"], item["coinYield"]), ("tree", "2", "150"))
                self.assertFalse(item.get("requirements"))
                original = copy.deepcopy(next(obj for obj in self.save()["world"]["objectsArray"]
                                              if obj.get("itemName") == name))
                self.assertEqual((original["className"], original["state"]), ("Tree", "ripe"))
                untouched = {obj["id"]: copy.deepcopy(obj) for obj in self.save()["world"]["objectsArray"]
                             if obj["id"] != original["id"]}
                duration = (float(item["growTime"]) * settings.get_farming_number("inGameDaySeconds")
                            * settings.get_farming_number("growMultiplier", 1.0))
                self.assertGreater(duration, 0)
                # SimpleHarvestableResource queues its ripe pre-harvest
                # snapshot. The server owns the resulting bare state/clock.
                started = int(time.time()) * 1000
                result = self.action("harvest", original)
                finished = (int(time.time()) + 1) * 1000
                self.assertEqual(result["id"], original["id"])
                harvested = self.object(original["id"])
                clock = harvested["plantTime"]
                self.assertEqual(harvested["state"], "bare")
                self.assertGreaterEqual(clock, started)
                self.assertLessEqual(clock, finished)
                self.assertGreater(clock, original["plantTime"])

                expected["gold"] += int(item["coinYield"])
                if index == int(first_variety["@count"]):
                    # Three distinct species legitimately earn the original
                    # yellow variety ribbon, separately from each 150-coin
                    # tree yield. Its XP can also cross a normal player level.
                    old_level = max(level for level, xp in levels.items() if xp <= expected["xp"])
                    expected["gold"] += int(first_variety["@coins"])
                    expected["xp"] += int(first_variety["@xp"])
                    new_level = max(level for level, xp in levels.items() if xp <= expected["xp"])
                    expected["cash"] += min(new_level, cap) - min(old_level, cap)
                    gifts = expected_inventory.setdefault("-1", {})
                    self.assertNotIn(gift["code"], gifts)
                    gifts[gift["code"]] = [1, [], []]
                self.assertEqual(self.balances(), expected)
                player = self.save()["userInfo"]["player"]
                self.assertEqual(player["storageData"], expected_inventory)
                self.assertEqual(player["achCounters"][total["@code"]], index)
                self.assertEqual(player["achCounters"][variety["@code"]], index)
                self.assertEqual(player["achievements"].get(total["@code"], -1), -1)
                self.assertEqual(player["achievements"].get(variety["@code"], -1), 0 if index == 3 else -1)
                paid_player = copy.deepcopy(player)
                paid_bytes = self.path.read_bytes()

                # A current bare tree has its full original cooldown left.
                # Replaying the old ripe packet is accepted without paying,
                # resetting its clock, or advancing mastery/ribbons again.
                self.assertLess(time.time() - clock / 1000, duration)
                repeated = self.action("harvest", original)
                self.assertEqual(repeated["id"], original["id"])
                self.assertEqual(self.object(original["id"])["plantTime"], clock)
                self.assertEqual(self.save()["userInfo"]["player"], paid_player)
                self.assertEqual(self.path.read_bytes(), paid_bytes)
                self.reload()
                self.assertEqual(self.balances(), expected)
                self.assertEqual(self.save()["userInfo"]["player"]["storageData"], expected_inventory)
                self.assertEqual((self.object(original["id"])["state"], self.object(original["id"])["plantTime"]),
                                 ("bare", clock))
                self.assertEqual(self.save()[october_village.STATE_KEY], provenance)
                for identity, obj in untouched.items():
                    self.assertEqual(self.object(identity), obj)

        self.assertEqual(expected, {"gold": 1150, "cash": 7, "xp": 35, "energy": 45})


if __name__ == "__main__":
    unittest.main()
