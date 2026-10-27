"""Save transformations exercised without importing or contacting the game."""

import copy
import json
import math
import unittest

from engine import CheatEngine, MAX_BALANCE


NOW = 1_800_000_000
RULES = {"levels": [{"level": 1, "xp": 0}, {"level": 2, "xp": 15}, {"level": 3, "xp": 30},
                    {"level": 4, "xp": 70}, {"level": 5, "xp": 140}],
         "inGameDaySeconds": 82800, "growMultiplier": 1, "witherMultiplier": 2.2}
CATALOG = [{"name": "strawberry", "code": "SB", "type": "seed", "growTime": "0.174"},
           {"name": "eggplant", "code": "EP", "type": "seed", "growTime": "2"},
           {"name": "cow", "code": "CW", "type": "animal", "displayName": "Cow"},
           {"name": "haybale", "code": "HB", "type": "decoration"},
           {"name": "questthing", "code": "QT", "type": "mission"},
           {"name": "placeholder", "code": "XX", "type": "tree"},
           {"name": "farm14", "code": "XX", "type": "change_farm", "subtype": "expand_farm", "squares": "58"},
           {"name": "farm16", "code": "XX", "type": "change_farm", "subtype": "expand_farm", "squares": "66"}]


def farm():
    return {"version": "unknown-future-version", "userInfo": {
        "attr": {"name": "Test Farmer"},
        "player": {"userId": "original.UID-123", "gold": 200, "cash": 5, "xp": 0, "energy": 20,
                   "energyMax": 50, "energyManager": {"turboChargers": 3, "unknown": "kept"},
                   "storageData": {"-1": {"CW": [2, ["friend-1"], [{"color": "blue"}]]}, "-2": {}},
                   "futureFeature": {"nested": [1, 2, {"secret": "preserved"}]}},
        "worldSummaryData": {"farm": {"lastLoaded": 123, "firstLoaded": 100}},
        "unknown": {"keep": True}},
        "world": {"id": 1, "uid": "world-identity", "sizeX": 50, "sizeY": 50, "objectsArray": [
            {"id": 2, "className": "Plot", "state": "planted", "itemName": "strawberry", "plantTime": (NOW - 3600) * 1000,
             "position": {"x": 20, "y": 30, "z": 0}, "custom": ["preserved"]},
            {"id": 3, "className": "Plot", "state": "withered", "itemName": "eggplant", "plantTime": (NOW - 700000) * 1000},
            {"id": 4, "className": "Plot", "state": "plowed", "itemName": None, "plantTime": 0},
            {"id": 9, "className": "Animal", "state": "grown", "itemName": "cow", "plantTime": 1234567},
        ]}, "flashHotParams": {"ZYNGA_USER_ID": "original.UID-123"},
        "craftingState": {"notOurBusiness": [1, 2, 3]}}


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = CheatEngine(CATALOG, RULES)
        self.save = farm()

    def apply(self, **operation):
        return self.engine.apply(self.save, operation, NOW)

    def test_money_result_is_detached_and_unknown_state_survives(self):
        original = copy.deepcopy(self.save)
        result = self.apply(type="balance", field="gold", mode="add", amount=500)
        self.assertEqual(self.save, original)
        self.assertEqual(result["save"]["userInfo"]["player"]["gold"], 700)
        result["save"]["userInfo"]["player"]["futureFeature"]["nested"].append("detached")
        self.assertEqual(self.save, original)
        self.assertEqual(result["save"]["craftingState"], original["craftingState"])
        self.assertEqual(result["changes"], [{"path": "/userInfo/player/gold", "before": 200, "after": 700}])

    def test_identity_and_world_objects_preserved_across_all_operation_types(self):
        before_ids = [obj["id"] for obj in self.save["world"]["objectsArray"]]
        for op in [{"type": "balance", "field": "xp", "mode": "add", "amount": 30}, {"type": "level", "level": 4},
                   {"type": "crops", "action": "ripen"}, {"type": "grant", "item": "cow", "quantity": 1},
                   {"type": "expand", "size": 58}, {"type": "preset", "name": "gentle"}]:
            with self.subTest(op=op):
                result = self.engine.apply(self.save, op, NOW)["save"]
                self.assertEqual(result["userInfo"]["player"]["userId"], "original.UID-123")
                self.assertEqual(result["world"]["uid"], "world-identity")
                self.assertEqual(result["flashHotParams"], self.save["flashHotParams"])
                self.assertEqual([obj["id"] for obj in result["world"]["objectsArray"]], before_ids)
                self.assertEqual(result["world"]["objectsArray"][3], self.save["world"]["objectsArray"][3])

    def test_xp_crosses_original_thresholds_and_grants_one_cash_per_level(self):
        result = self.apply(type="balance", field="xp", mode="add", amount=70)
        player = result["save"]["userInfo"]["player"]
        self.assertEqual(player["cash"], 8)
        self.assertEqual(self.engine.level_for_xp(player["xp"]), 4)
        self.assertNotIn("level", player)
        self.assertEqual({entry["path"] for entry in result["changes"]}, {"/userInfo/player/xp", "/userInfo/player/cash"})

    def test_lowering_xp_does_not_claw_back_cash(self):
        self.save["userInfo"]["player"]["xp"] = 140
        player = self.apply(type="balance", field="xp", mode="set", amount=15)["save"]["userInfo"]["player"]
        self.assertEqual((player["xp"], player["cash"]), (15, 5))

    def test_explicit_level_uses_threshold_and_does_not_invent_table_entries(self):
        player = self.apply(type="level", level=5)["save"]["userInfo"]["player"]
        self.assertEqual((player["xp"], player["cash"]), (140, 9))
        with self.assertRaises(ValueError):
            self.apply(type="level", level=1000)

    def test_fractional_multiplier_floors_and_flash_cap_is_reported(self):
        self.save["userInfo"]["player"]["gold"] = 201
        self.assertEqual(self.apply(type="balance", field="gold", mode="multiply", amount=1.5)["save"]["userInfo"]["player"]["gold"], 301)
        result = self.apply(type="balance", field="gold", mode="multiply", amount=1e308)
        self.assertEqual(result["save"]["userInfo"]["player"]["gold"], MAX_BALANCE)
        self.assertTrue(any("Flash" in warning for warning in result["warnings"]))

    def test_subtraction_floors_at_zero(self):
        self.assertEqual(self.apply(type="balance", field="gold", mode="add", amount=-500)["save"]["userInfo"]["player"]["gold"], 0)

    def test_turbo_charges_use_energy_manager_without_losing_metadata(self):
        player = self.apply(type="balance", field="turboChargers", mode="add", amount=20)["save"]["userInfo"]["player"]
        self.assertEqual(player["energyManager"], {"turboChargers": 23, "unknown": "kept"})
        self.assertNotIn("turboChargers", player)

    def test_bad_operations_fail_without_mutating_original(self):
        original = copy.deepcopy(self.save)
        ops = [{"type": "balance", "field": "gold", "mode": "set", "amount": amount} for amount in [True, -1, 1.1, float("nan"), float("inf"), "100", 10**1000]]
        ops.extend([{"type": "balance", "field": "userId", "mode": "set", "amount": 3},
                    {"type": "balance", "field": "cash", "mode": "add", "amount": 2, "evil": True},
                    {"type": "delete"}, {}, None])
        for op in ops:
            with self.subTest(op=str(op)[:100]), self.assertRaises(ValueError):
                self.engine.apply(self.save, op, NOW)
        self.assertEqual(self.save, original)

    def test_ripen_uses_23_hour_days_and_millisecond_plant_times(self):
        result = self.apply(type="crops", action="ripen", ids=[2])
        plot = result["save"]["world"]["objectsArray"][0]
        grow = 0.174 * 82800
        self.assertEqual(plot["state"], "grown")
        self.assertEqual(plot["plantTime"], math.floor((NOW - grow) * 1000))
        self.assertEqual(plot["position"], self.save["world"]["objectsArray"][0]["position"])
        status = self.engine.crop_status(plot, NOW)
        self.assertEqual(status["phase"], "grown")
        self.assertAlmostEqual(status["growSeconds"], 14407.2)
        self.assertEqual(result["save"]["world"]["objectsArray"][1], self.save["world"]["objectsArray"][1])

    def test_grow_multiplier_is_applied_once(self):
        engine = CheatEngine(CATALOG, dict(RULES, growMultiplier=0.5))
        plot = engine.apply(self.save, {"type": "crops", "action": "ripen", "ids": [2]}, NOW)["save"]["world"]["objectsArray"][0]
        self.assertAlmostEqual((NOW * 1000 - plot["plantTime"]) / 1000, 0.174 * 82800 * 0.5, places=3)

    def test_unwither_changes_only_withered_crops(self):
        result = self.apply(type="crops", action="unwither")["save"]
        self.assertEqual(result["world"]["objectsArray"][0], self.save["world"]["objectsArray"][0])
        plot = result["world"]["objectsArray"][1]
        self.assertEqual(plot["state"], "grown")
        self.assertEqual(self.engine.crop_status(plot, NOW)["phase"], "grown")

    def test_time_advance_with_protection_clamps_to_harvest_and_skips_withered(self):
        result = self.apply(type="crops", action="advance", hours=1000, protect=True)
        plots = result["save"]["world"]["objectsArray"]
        self.assertEqual(self.engine.crop_status(plots[0], NOW)["phase"], "grown")
        self.assertAlmostEqual(self.engine.crop_status(plots[0], NOW)["elapsedSeconds"], 14407.2, places=3)
        self.assertEqual(plots[1], self.save["world"]["objectsArray"][1])
        self.assertTrue(any("Skipped" in warning for warning in result["warnings"]))

    def test_time_advance_without_protection_can_wither_and_does_not_change_global_clock(self):
        result = self.apply(type="crops", action="advance", hours=24, protect=False)
        self.assertEqual(result["save"]["world"]["objectsArray"][0]["state"], "withered")
        self.assertEqual(result["save"]["userInfo"]["worldSummaryData"], self.save["userInfo"]["worldSummaryData"])

    def test_fertilizer_uses_is_jumbo_and_leaves_empty_plots_alone(self):
        plots = self.apply(type="crops", action="fertilize")["save"]["world"]["objectsArray"]
        self.assertIs(plots[0]["isJumbo"], True)
        self.assertNotIn("isJumbo", plots[2])
        self.assertEqual(plots[1], self.save["world"]["objectsArray"][1])

    def test_selected_crop_validation_rejects_unknown_nonplot_and_duplicate_ids(self):
        for ids in [[500], [9], [4], [2, 2], [True], "2"]:
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                self.apply(type="crops", action="ripen", ids=ids)

    def test_gift_grant_preserves_existing_sender_and_extra_data(self):
        result = self.apply(type="grant", item="cow", quantity=10, group="giftbox")["save"]
        self.assertEqual(result["userInfo"]["player"]["storageData"]["-1"]["CW"], [12, ["friend-1"], [{"color": "blue"}]])

    def test_storage_grant_uses_home_group_and_standard_metadata(self):
        result = self.apply(type="grant", item="haybale", quantity=7, group="storage")["save"]
        self.assertEqual(result["userInfo"]["player"]["storageData"]["-2"]["HB"], [7, [], []])
        self.assertEqual(result["userInfo"]["player"]["storageData"]["-1"], self.save["userInfo"]["player"]["storageData"]["-1"])

    def test_grant_validation_blocks_unsupported_items_placeholder_codes_and_bad_quantities(self):
        for name, qty in [("questthing", 1), ("placeholder", 1), ("cow", 0), ("cow", True), ("cow", 100001), ("unknown", 1)]:
            with self.subTest(name=name, qty=qty), self.assertRaises(ValueError):
                self.apply(type="grant", item=name, quantity=qty)

    def test_item_codes_are_case_sensitive_placeholder_does_not_block_real_codes(self):
        catalog = CATALOG + [{"name": "realpond", "type": "decoration", "code": "Xx"},
                             {"name": "realpig", "type": "decoration", "code": "xX"}]
        engine = CheatEngine(catalog, RULES)
        for name, code in (("realpond", "Xx"), ("realpig", "xX")):
            result = engine.apply(self.save, {"type": "grant", "item": name, "quantity": 1}, NOW)
            self.assertEqual(result["save"]["userInfo"]["player"]["storageData"]["-1"][code], [1, [], []])

    def test_expansion_uses_catalog_sizes_and_cannot_shrink(self):
        result = self.apply(type="expand", size=66)["save"]
        self.assertEqual((result["world"]["sizeX"], result["world"]["sizeY"]), (66, 66))
        self.assertEqual(result["world"]["objectsArray"], self.save["world"]["objectsArray"])
        with self.assertRaises(ValueError):
            self.apply(type="expand", size=999)
        self.save["world"]["sizeX"] = 66
        with self.assertRaises(ValueError):
            self.apply(type="expand", size=58)

    def test_presets_are_concrete_and_preview_serializes(self):
        for name in ("millionaire", "gentle", "collector"):
            with self.subTest(name=name):
                result = self.apply(type="preset", name=name)
                self.assertTrue(result["changes"])
                json.dumps(result, allow_nan=False)
        player = self.apply(type="preset", name="gentle")["save"]["userInfo"]["player"]
        self.assertEqual((player["energy"], player["energyManager"]["turboChargers"]), (50, 103))

    def test_malformed_save_is_rejected_even_for_unrelated_operation(self):
        for mutate in [lambda s: s["userInfo"]["player"].update(gold=float("nan")),
                       lambda s: s["userInfo"]["player"].update(userId=None),
                       lambda s: s["world"]["objectsArray"].append(copy.deepcopy(s["world"]["objectsArray"][0])),
                       lambda s: s["userInfo"]["player"].update(storageData={"-1": {"SB": [1, {}, []]}})]:
            save = farm()
            mutate(save)
            with self.assertRaises(ValueError):
                self.engine.apply(save, {"type": "balance", "field": "gold", "mode": "set", "amount": 20}, NOW)

    def test_summary_reports_derived_state_without_mutating_save(self):
        original = copy.deepcopy(self.save)
        result = self.engine.summarize(self.save, NOW)
        self.assertEqual((result["level"], result["inventoryCount"], result["objectCount"]), (1, 2, 4))
        self.assertEqual([p["phase"] for p in result["plots"]], ["planted", "withered", "empty"])
        self.assertEqual(self.save, original)


if __name__ == "__main__":
    unittest.main()
