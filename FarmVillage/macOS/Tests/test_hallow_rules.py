"""Offline original-rule and dormant accounting proofs; no hallow activation."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence  # Isolate writable runtime paths before product imports.
import hallow_rules as hallow
import persistence


def world(width):
    return {"sizeX": width, "sizeY": width, "objectsArray": []}


def saved(score=1, width=58, current="hallow"):
    return {"opaqueImport": {"keep": [1, 2, 3]},
        "world": world(width), "userInfo": {"currentWorldType": current,
            "player": {"xp": 3700, "gold": 100, "cash": 50, "storageData": {"-1": {}},
                "worldScores": {"spook": {"score": score, "level": hallow.level_for_score(score),
                                          "originalExtra": "preserved"},
                                "zen": {"score": 800, "level": 7}}}}}


def award_expansion(save, *, previous_world, item_name):
    return hallow.record_verified_expansion(save, previous_world=previous_world,
        item_name=item_name, score_experiments={"fv_hallow": 1})


class HauntedHollowRulesTests(unittest.TestCase):
    def test_original_contract_has_cumulative_score_and_all_access(self):
        rules = hallow.recovered_rules()
        self.assertEqual((rules["worldType"], rules["storageId"], rules["currency"],
                          rules["scoreUnit"], rules["spendableScore"]),
                         ("hallow", -14, "coins", "spook", False))
        self.assertEqual(len(rules["levels"]), 31)
        self.assertEqual(len(rules["tasks"]), 23)
        self.assertEqual(len(rules["globalTasks"]), 5)
        self.assertEqual(rules["access"]["allAccess"]["attributes"], {})
        self.assertEqual(rules["access"]["allAccess"]["rewards"], [
            {"type": "world_unlock", "value": "hallow"},
            {"type": "unlock_world_score", "unit": "spook", "value": "1"}])
        self.assertEqual(rules["access"]["earlyAccess"]["attributes"], {"cashCost": "35"})
        rules["levels"][2]["required"] = "1"
        self.assertEqual(hallow.level_requirement(2), 10)

    def test_original_earning_tasks_have_no_harvest_or_plow_points(self):
        rules = hallow.recovered_rules()
        actions = {task["action"] for task in rules["tasks"]}
        self.assertEqual(actions, {"useInstantGrow", "expandFarm",
            "completeNondeterministicConstructionBuildingByCode", "expandStorageBuildingToLevelByCode"})
        self.assertEqual([(task["type"], int(task["rewards"]["reward"]["value"]))
            for task in rules["globalTasks"]],
            [("SpookLE1", 5), ("SpookLE2", 40), ("SpookLE3", 100), ("SpookLE4", 150), ("SpookLE5", 200)])

    def test_exact_and_calculated_level_boundaries_match_original_rounding(self):
        golden = {0: 0, 1: 1, 2: 10, 27: 5939, 30: 7520,
                  31: 8119, 32: 8701, 40: 14074, 50: 22591, 100: 95195}
        for level, required in golden.items():
            with self.subTest(level=level):
                self.assertEqual(hallow.level_requirement(level), required)
                self.assertEqual(hallow.level_for_score(required), level)
                if level:
                    self.assertEqual(hallow.level_for_score(required - 1), level - 1)
        for invalid in (None, False, -1, 1.5, float("inf"), "10", 10 ** 1000):
            with self.subTest(invalid=str(invalid)[:30]), self.assertRaises(ValueError):
                hallow.level_for_score(invalid)
        with self.assertRaises(ValueError):
            hallow.level_for_score(hallow.level_requirement(1000))

    def test_missing_score_is_locked_and_readers_never_initialize_it(self):
        save = saved()
        del save["userInfo"]["player"]["worldScores"]["spook"]
        before = copy.deepcopy(save)
        self.assertEqual(hallow.world_level(save), -1)
        self.assertFalse(hallow.meets_level_prerequisite(save, "fv_spook_unlock_level_1"))
        with self.assertRaisesRegex(ValueError, "not been unlocked"):
            award_expansion(save, previous_world=world(50), item_name="xhwfarm14")
        self.assertEqual(save, before)

    def test_original_shared_score_gate_requires_xp_and_server_experiments(self):
        cases = [(3699, {"fv_hallow": 1}), (3700, None),
                 (3700, {"fv_hallow": 0}), (3700, {"fv_hallow": True}),
                 (3700, {"fv_xhw": 1, "fv_xhw_farm14_coin": 1})]
        for xp, experiments in cases:
            save = saved()
            save["userInfo"]["player"]["xp"] = xp
            before = copy.deepcopy(save)
            with self.subTest(xp=xp, experiments=experiments), self.assertRaisesRegex(ValueError, "level15"):
                hallow.record_verified_expansion(save, previous_world=world(50),
                    item_name="xhwfarm14", score_experiments=experiments)
            self.assertEqual(save, before)

    def test_six_catalog_crop_gates_use_spook_level(self):
        gates = {"garlic2": 2, "greentoadstool": 5, "wormwood": 15,
                 "phantomfrond": 20, "candiedcorn": 24, "frankenfruit": 30}
        for name, required in gates.items():
            with self.subTest(name=name):
                self.assertEqual(hallow.item_level_requirement(name), required)
                save = saved(hallow.level_requirement(required) - 1)
                save["userInfo"]["player"]["level"] = 1000
                before = copy.deepcopy(save)
                with self.assertRaisesRegex(ValueError, "Spook level"):
                    hallow.guard_item_level(save, name)
                self.assertEqual(save, before)
                hallow.guard_item_level(saved(hallow.level_requirement(required)), name)
        with self.assertRaisesRegex(ValueError, "quest or special"):
            hallow.item_level_requirement("xhw_hauntedinn")
        for name in ("unknown", "fv_spook_unlock_level_0", "fv_spook_unlock_level_51", "fv_xhw_shared"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                hallow.meets_level_prerequisite(saved(), name)

    def test_land_has_exact_original_prices_gates_and_treasures(self):
        coin = hallow.land_rules("xhwfarm14")
        cash = hallow.land_rules("xhwfarm14_cash")
        self.assertEqual((coin["width"], coin["coinCost"], coin["cashCost"], coin["scoreAward"]),
                         (58, 10000, 0, 160))
        self.assertEqual(coin["experimentGate"], "fv_xhw_farm14_coin")
        self.assertEqual((cash["coinCost"], cash["cashCost"], cash["experimentGate"]), (0, 1, "fv_xhw"))
        self.assertEqual(cash["catalogCash"], 20)
        self.assertIsNone(coin["spookLevelRequirement"])
        self.assertTrue(coin["archived"])
        self.assertEqual(coin["addedObjects"], [
            {"code": "7Ec", "x": "5", "y": "44", "z": "0", "state": "construct_0"},
            {"code": "7DI", "x": "24", "y": "5", "z": "0", "state": "construct_0"},
            {"code": "7D0", "x": "4", "y": "16", "z": "0", "state": "construct_0"},
            {"code": "7IZ", "x": "40", "y": "0", "z": "0", "state": "built_0"}])
        self.assertEqual(hallow.land_rules("xhwfarm26")["scoreAward"], 0)
        self.assertEqual(hallow.land_rules("xhwfarm50_cash")["width"], 202)
        for name in ("xhwfarm14", "xhwfarm14_cash"):
            with self.assertRaisesRegex(ValueError, "not restored"):
                hallow.guard_land_purchase(saved(), name)

    def test_spend_and_unknown_event_classes_cannot_change_save(self):
        save = saved()
        before = copy.deepcopy(save)
        with self.assertRaisesRegex(ValueError, "cannot be spent"):
            hallow.spend_score(save, 1)
        for name in ("xhwfarm12", "xhwfarm26", "xhwfarm38", "garlic2", "unknown"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                award_expansion(save, previous_world=world(50), item_name=name)
        self.assertEqual(save, before)

    def test_verified_expansion_records_only_original_score_not_display_grants(self):
        save = saved()
        original = copy.deepcopy(save)
        result = award_expansion(save, previous_world=world(50), item_name="xhwfarm14")
        self.assertEqual(result, {"points": 160, "levels": [2, 3, 4, 5, 6], "coins": 0, "items": {}})
        record = save["userInfo"]["player"]["worldScores"]["spook"]
        self.assertEqual(record, {"score": 161, "level": 6, "originalExtra": "preserved"})
        self.assertEqual(save["userInfo"]["player"]["gold"], 100)
        self.assertEqual(save["userInfo"]["player"]["storageData"], {"-1": {}})
        self.assertEqual(save["opaqueImport"], original["opaqueImport"])
        self.assertEqual(save["userInfo"]["player"]["worldScores"]["zen"],
                         original["userInfo"]["player"]["worldScores"]["zen"])

    def test_real_level_grants_are_once_and_cash_alias_owns_same_receipt(self):
        save = saved(2250, width=66)
        save["userInfo"]["player"]["storageData"]["-1"]["7KR"] = [4, ["sender"], ["meta"]]
        result = award_expansion(save, previous_world=world(58), item_name="xhwfarm16_cash")
        self.assertEqual((result["points"], result["levels"], result["items"]), (240, [18], {"7KR": 3}))
        self.assertEqual(save["userInfo"]["player"]["storageData"]["-1"]["7KR"], [7, ["sender"], ["meta"]])
        before = copy.deepcopy(save)
        self.assertEqual(award_expansion(save, previous_world=world(58), item_name="xhwfarm16"),
                         {"points": 0, "levels": [], "coins": 0, "items": {}})
        self.assertEqual(save, before)

    def test_beyond_thirty_grants_default_coins_once(self):
        save = saved(8000)
        result = award_expansion(save, previous_world=world(50), item_name="xhwfarm14")
        self.assertEqual(result, {"points": 160, "levels": [31], "coins": 5000, "items": {}})
        self.assertEqual(save["userInfo"]["player"]["gold"], 5100)
        before = copy.deepcopy(save)
        award_expansion(save, previous_world=world(50), item_name="xhwfarm14_cash")
        self.assertEqual(save, before)

    def test_receipt_persists_across_atomic_json_reload(self):
        save = saved(2250, width=66)
        award_expansion(save, previous_world=world(58), item_name="xhwfarm16")
        with tempfile.TemporaryDirectory(prefix="hallow-accounting-") as directory:
            path = Path(directory, "save.json")
            persistence.atomic_json(path, save)
            reloaded = persistence.read_json(path)
        before = copy.deepcopy(reloaded)
        award_expansion(reloaded, previous_world=world(58), item_name="xhwfarm16_cash")
        self.assertEqual(reloaded, before)
        self.assertEqual(len(reloaded[hallow.STATE_KEY]["expansions"]), 1)

    def test_impossible_expansion_world_and_shape_fail_without_mutation(self):
        cases = [(saved(current="farm"), world(50), "xhwfarm14"),
                 (saved(width=66), world(50), "xhwfarm16"),
                 (saved(width=58), world(58), "xhwfarm14"),
                 (saved(width=58), {"sizeX": 50, "sizeY": 58}, "xhwfarm14")]
        for save, previous, name in cases:
            before = copy.deepcopy(save)
            with self.subTest(name=name, previous=previous), self.assertRaises(ValueError):
                award_expansion(save, previous_world=previous, item_name=name)
            self.assertEqual(save, before)

    def test_imported_inconsistent_scores_preserved_and_closed(self):
        for record in (None, {}, {"score": 1, "level": 30}, {"score": 0, "level": 1},
                       {"score": -1, "level": 1}, {"score": True, "level": 1},
                       {"score": "10", "level": 2}):
            save = saved()
            save["userInfo"]["player"]["worldScores"]["spook"] = record
            before = copy.deepcopy(save)
            with self.subTest(record=record), self.assertRaises(ValueError):
                award_expansion(save, previous_world=world(50), item_name="xhwfarm14")
            self.assertEqual(save, before)

    def test_invalid_or_forged_receipt_namespace_is_preserved(self):
        cases = [None, [], {"version": 2, "expansions": {}},
            {"version": 1, "baselineScore": 1, "expansions": {"xhwfarm26": {"width": 106, "points": 123}}},
            {"version": 1, "baselineScore": 1, "expansions": {"xhwfarm14": {"width": 58, "points": 999}}},
            {"version": 1, "baselineScore": 1, "expansions": {"xhwfarm14": {"width": 58, "points": 160}}}]
        for state in cases:
            save = saved()
            save[hallow.STATE_KEY] = state
            before = copy.deepcopy(save)
            with self.subTest(state=state), self.assertRaises(ValueError):
                award_expansion(save, previous_world=world(50), item_name="xhwfarm14")
            self.assertEqual(save, before)

    def test_unrestored_imported_buff_and_trophy_cannot_receive_base_rate(self):
        cases = [{"buffs": {"buff_permanent_spook": 0}}, {"buffs": {"buff_permanent_coin": 0}}, {"buffs": {"unknown_imported_buff": 1}},
                 {"buffs": []}, {"trophy": "xhwdoublesptrophy"}, {"trophy": "doublecoinstatue"}]
        for case in cases:
            save = saved()
            if case.get("trophy"):
                save["world"]["objectsArray"] = [{"id": 1, "itemName": case["trophy"]}]
            else:
                save["userInfo"]["player"].update(case)
            before = copy.deepcopy(save)
            with self.subTest(case=case), self.assertRaisesRegex(ValueError, "buff|trophy"):
                award_expansion(save, previous_world=world(50), item_name="xhwfarm14")
            self.assertEqual(save, before)

    def test_failure_in_reward_storage_does_not_partly_award_score(self):
        for entry in (None, ["bad", [], []]):
            save = saved(2250, width=66)
            save["userInfo"]["player"]["storageData"]["-1"]["7KR"] = entry
            before = copy.deepcopy(save)
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                award_expansion(save, previous_world=world(58), item_name="xhwfarm16")
            self.assertEqual(save, before)

    def test_changed_archive_source_requires_review(self):
        name = "gz/v855098/worldScore.amf.gz"
        with tempfile.TemporaryDirectory(prefix="hallow-source-") as directory:
            target = Path(directory, name)
            target.parent.mkdir(parents=True)
            target.write_bytes(b"changed")
            with patch.object(hallow, "XML_DIR", directory), self.assertRaisesRegex(ValueError, "require review"):
                hallow._source(name)


EXPERIMENTS = {"fv_hallow": 1, "fv_hallow_for_all": 1}
FIRST_EXPANSION_OBJECTS = [
    ("FixedTreasureConstructionBuilding", "xhw_treasure1_s", (5, 44), "construct_0"),
    ("FixedTreasureConstructionBuilding", "xhw_treasure1_l", (24, 5), "construct_0"),
    ("FixedTreasureConstructionBuilding", "xhw_treasure1_xl", (4, 16), "construct_0"),
    ("FeatureBuilding", "animal_breeding_xhwaviary_finished", (40, 0), "built_0"),
]


def persisted(object_id, class_name, item_name, position, state):
    """Literal client-written shape (independent of the product helper)."""
    x, y = position
    return {"id": object_id, "className": class_name, "itemName": item_name,
            "position": {"x": x, "y": y, "z": 0}, "state": state, "deleted": False,
            "direction": 0, "components": {}, "instanceDataStoreKey": None,
            "plantTime": None, "buildTime": 0, "contents": []}


def home_save():
    return {"opaqueImport": {"keep": [1, 2]}, "world": {"sizeX": 50, "sizeY": 50,
            "objectsArray": [{"id": 7, "className": "Plot", "position": {"x": 1, "y": 1, "z": 0},
                              "state": "fallow"}]},
        "userInfo": {"currentWorldType": "farm", "unlockedWorldTypes": ["farm"],
            "worldSummaryData": {"farm": {"storageId": -2, "firstLoaded": 1, "lastLoaded": 1}},
            "player": {"xp": 3700, "gold": 10, "cash": 5, "storageData": {"-2": {}},
                       "worldScores": {}}}}


def unlocked_save(now=1000):
    save = home_save()
    assert hallow.unlock_all_access(save, now=now, experiments=EXPERIMENTS) is True
    return save


def enter_hallow(save, width=50):
    """Test-only stand-in for the not-yet-wired travel switch."""
    save["world"] = save["_hallowWorldState"]["inactive"].pop(hallow.WORLD)
    save["world"]["sizeX"] = save["world"]["sizeY"] = width
    save["userInfo"]["currentWorldType"] = hallow.WORLD
    return save


PREVIOUS = {"sizeX": 50, "sizeY": 50, "objectsArray": []}


class HauntedHollowLifecycleTests(unittest.TestCase):
    def test_contract_pins_allaccess_chain_storage_and_start_size(self):
        import storage
        contract = hallow._access_contract()
        self.assertEqual((contract["farmSize"], contract["minimumXP"]), (50, 3700))
        self.assertEqual(hallow.STORAGE_ID, storage.HALLOW_INVENTORY_ID)
        self.assertEqual(hallow.STORAGE_ID, -14)
        self.assertEqual(hallow._level_rewards(1), [])

    def test_allaccess_unlock_grants_only_recovered_rewards_atomically(self):
        import hallow_world_rules
        save = unlocked_save()
        user = save["userInfo"]
        self.assertIn("hallow", user["unlockedWorldTypes"])
        self.assertEqual(user["worldSummaryData"]["hallow"]["storageId"], -14)
        self.assertEqual(user["player"]["storageData"]["-14"], {})
        self.assertEqual(user["player"]["worldScores"]["spook"], {"score": 1, "level": 1})
        self.assertEqual((user["player"]["gold"], user["player"]["cash"]), (10, 5))
        self.assertEqual(save["userInfo"]["currentWorldType"], "farm")
        self.assertEqual(save["world"]["objectsArray"][0]["id"], 7)
        self.assertEqual(save["opaqueImport"], {"keep": [1, 2]})
        snapshot = save[hallow.WORLD_STATE_KEY]["inactive"]["hallow"]
        self.assertEqual((snapshot["sizeX"], snapshot["sizeY"], snapshot["tileSet"],
                          snapshot["objectsArray"]), (50, 50, "hallow_theme", []))
        self.assertEqual(hallow_world_rules.guard_snapshot(snapshot), 0)

    def test_unlock_retry_is_a_noop_before_and_after_reload(self):
        save = unlocked_save()
        before = copy.deepcopy(save)
        self.assertIs(hallow.unlock_all_access(save, now=9999, experiments=EXPERIMENTS), False)
        self.assertEqual(save, before)
        reloaded = json.loads(json.dumps(save))
        self.assertIs(hallow.unlock_all_access(reloaded, now=9999, experiments=EXPERIMENTS), False)
        self.assertEqual(reloaded, before)

    def test_unlock_refuses_missing_experiments_levels_and_conflicts_unchanged(self):
        cases = [
            ("missing for-all", lambda s: None, {"fv_hallow": 1}),
            ("boolean experiment", lambda s: None, {"fv_hallow": True, "fv_hallow_for_all": 1}),
            ("string experiment", lambda s: None, {"fv_hallow": 1, "fv_hallow_for_all": "1"}),
            ("below level15", lambda s: s["userInfo"]["player"].update(xp=3699), EXPERIMENTS),
            ("orphan spook score", lambda s: s["userInfo"]["player"]["worldScores"].update(
                spook={"score": 5, "level": 2}), EXPERIMENTS),
            ("active hallow", lambda s: s["userInfo"].update(currentWorldType="hallow"), EXPERIMENTS),
            ("unknown active world", lambda s: s["userInfo"].update(currentWorldType="atlantis"), EXPERIMENTS),
        ]
        for label, mutate, experiments in cases:
            save = home_save()
            mutate(save)
            before = copy.deepcopy(save)
            with self.subTest(case=label), self.assertRaises(ValueError):
                hallow.unlock_all_access(save, now=1000, experiments=experiments)
            self.assertEqual(save, before)

    def test_partial_ownership_fails_closed_and_is_preserved(self):
        save = unlocked_save()
        del save[hallow.WORLD_STATE_KEY]
        before = copy.deepcopy(save)
        with self.assertRaisesRegex(ValueError, "partial"):
            hallow.unlock_all_access(save, now=2000, experiments=EXPERIMENTS)
        self.assertEqual(save, before)

    def test_unlock_rolls_back_when_final_validation_fails(self):
        save = home_save()
        before = copy.deepcopy(save)
        real_validate = hallow.world_travel.validate

        def fail_on_working_copy(candidate):
            if hallow.WORLD_STATE_KEY in candidate:
                raise ValueError("forced failure")
            return real_validate(candidate)

        with patch.object(hallow.world_travel, "validate", side_effect=fail_on_working_copy), \
                self.assertRaisesRegex(ValueError, "forced failure"):
            hallow.unlock_all_access(save, now=1000, experiments=EXPERIMENTS)
        self.assertEqual(save, before)

    def test_first_expansion_adds_exact_mandatory_objects_and_score_once(self):
        save = enter_hallow(unlocked_save(), width=58)
        result = hallow.record_expansion_lifecycle(save, previous_world=PREVIOUS,
            item_name="xhwfarm14", score_experiments={"fv_hallow": 1})
        objects = save["world"]["objectsArray"]
        self.assertEqual(len(objects), 4)
        self.assertEqual(result["objects"], [obj["id"] for obj in objects])
        self.assertEqual(len({obj["id"] for obj in objects}), 4)
        for obj, (class_name, item_name, (x, y), state) in zip(objects, FIRST_EXPANSION_OBJECTS):
            self.assertEqual(obj, persisted(obj["id"], class_name, item_name, (x, y), state))
        self.assertEqual(result["points"], 160)
        self.assertEqual(save["userInfo"]["player"]["worldScores"]["spook"],
                         {"score": 161, "level": hallow.level_for_score(161)})
        self.assertEqual(save["_hallowScoreAccounting"]["expansions"],
                         {"xhwfarm14": {"width": 58, "points": 160}})

    def test_expansion_retry_after_reload_is_charge_once(self):
        save = enter_hallow(unlocked_save(), width=58)
        hallow.record_expansion_lifecycle(save, previous_world=PREVIOUS,
            item_name="xhwfarm14", score_experiments={"fv_hallow": 1})
        before = copy.deepcopy(save)
        for item in ("xhwfarm14", "xhwfarm14_cash"):
            with self.subTest(item=item):
                result = hallow.record_expansion_lifecycle(save, previous_world=PREVIOUS,
                    item_name=item, score_experiments={"fv_hallow": 1})
                self.assertEqual((result["points"], result["objects"]), (0, []))
                self.assertEqual(save, before)
        reloaded = json.loads(json.dumps(save))
        result = hallow.record_expansion_lifecycle(reloaded, previous_world=PREVIOUS,
            item_name="xhwfarm14", score_experiments={"fv_hallow": 1})
        self.assertEqual(result["objects"], [])
        self.assertEqual(reloaded, before)
        self.assertEqual(len(reloaded["world"]["objectsArray"]), 4)

    def test_expansion_refuses_unsupported_or_out_of_order_and_stays_unchanged(self):
        cases = [("xhwfarm26", 106, PREVIOUS, "earning task"),
                 ("xhwfarm16", 66, PREVIOUS, "next original")]
        for item, width, previous, message in cases:
            save = enter_hallow(unlocked_save(), width=width)
            before = copy.deepcopy(save)
            with self.subTest(item=item), self.assertRaisesRegex(ValueError, message):
                hallow.record_expansion_lifecycle(save, previous_world=previous,
                    item_name=item, score_experiments={"fv_hallow": 1})
            self.assertEqual(save, before)

    def test_expansion_requires_unlock_and_an_active_hallow_world(self):
        farm = home_save()
        with self.assertRaisesRegex(ValueError, "active Haunted Hollow"):
            hallow.record_expansion_lifecycle(farm, previous_world=PREVIOUS,
                item_name="xhwfarm14", score_experiments={"fv_hallow": 1})
        unlocked = unlocked_save()
        before = copy.deepcopy(unlocked)
        unlocked["userInfo"]["currentWorldType"] = "hallow"
        with self.assertRaisesRegex(ValueError, "unlocked and active"):
            hallow.record_expansion_lifecycle(unlocked, previous_world=PREVIOUS,
                item_name="xhwfarm14", score_experiments={"fv_hallow": 1})
        unlocked["userInfo"]["currentWorldType"] = "farm"
        self.assertEqual(unlocked, before)

    def test_second_expansion_overlapping_recovered_aviary_fails_closed(self):
        save = enter_hallow(unlocked_save(), width=58)
        hallow.record_expansion_lifecycle(save, previous_world=PREVIOUS,
            item_name="xhwfarm14", score_experiments={"fv_hallow": 1})
        save["world"]["sizeX"] = save["world"]["sizeY"] = 66
        before = copy.deepcopy(save)
        with self.assertRaisesRegex(ValueError, "overlap"):
            hallow.record_expansion_lifecycle(save, previous_world={"sizeX": 58, "sizeY": 58,
                "objectsArray": []}, item_name="xhwfarm16", score_experiments={"fv_hallow": 1})
        self.assertEqual(save, before)

    def test_persisted_fields_are_the_client_chain_key_set_with_no_temp_id(self):
        self.assertEqual(hallow.PERSISTED_FIELDS, frozenset({"buildTime", "className", "components",
            "contents", "deleted", "direction", "id", "instanceDataStoreKey", "itemName",
            "plantTime", "position", "state"}))
        save = enter_hallow(unlocked_save(), width=58)
        hallow.record_expansion_lifecycle(save, previous_world=PREVIOUS,
            item_name="xhwfarm14", score_experiments={"fv_hallow": 1})
        for obj in save["world"]["objectsArray"]:
            with self.subTest(item=obj["itemName"]):
                self.assertEqual(set(obj), hallow.PERSISTED_FIELDS)
                self.assertNotIn("tempId", obj)

    def test_placement_is_the_recovered_next_width_frame_not_the_display_shift(self):
        # The client's display-only shift would put the first treasure at x=-3.
        self.assertEqual(hallow.pending_client_position(5, 44, 50, 58), (-3, 36))
        self.assertEqual(hallow.pending_client_position(38, 5, 58, 66), (30, -3))
        save = enter_hallow(unlocked_save(), width=58)
        hallow.record_expansion_lifecycle(save, previous_world=PREVIOUS,
            item_name="xhwfarm14", score_experiments={"fv_hallow": 1})
        self.assertEqual([obj["position"] for obj in save["world"]["objectsArray"]],
                         [{"x": 5, "y": 44, "z": 0}, {"x": 24, "y": 5, "z": 0},
                          {"x": 4, "y": 16, "z": 0}, {"x": 40, "y": 0, "z": 0}])

    def test_recovered_additions_fill_the_eight_square_top_and_left_strip(self):
        previous = 50
        for width in sorted(hallow._archive()["added"]):
            self.assertEqual(width - previous, 8)
            previous = width
            for plan in hallow._expansion_plans(width):
                x, y = plan["position"]["x"], plan["position"]["y"]
                with self.subTest(width=width, item=plan["itemName"]):
                    self.assertTrue(x + plan["sizeX"] <= 8 or y + plan["sizeY"] <= 8)
                    self.assertTrue(x + plan["sizeX"] <= width and y + plan["sizeY"] <= width)

    def test_second_expansion_leaves_clear_existing_objects_unshifted(self):
        save = enter_hallow(unlocked_save(), width=66)
        plot = {"id": 9, "className": "Plot", "position": {"x": 1, "y": 1, "z": 0}, "state": "fallow"}
        save["world"]["objectsArray"].append(copy.deepcopy(plot))
        hallow.record_expansion_lifecycle(save, previous_world={"sizeX": 58, "sizeY": 58, "objectsArray": []},
            item_name="xhwfarm16", score_experiments={"fv_hallow": 1})
        self.assertEqual(save["world"]["objectsArray"][0], plot)
        self.assertEqual(len(save["world"]["objectsArray"]), 6)

    def test_recovered_addition_plans_fit_their_width_without_self_overlap(self):
        def overlaps(first, second):
            return (first[0] < second[0] + second[2] and second[0] < first[0] + first[2]
                    and first[1] < second[1] + second[3] and second[1] < first[1] + first[3])
        for width in sorted(hallow._archive()["added"]):
            plans = hallow._expansion_plans(width)
            rects = [(p["position"]["x"], p["position"]["y"], p["sizeX"], p["sizeY"]) for p in plans]
            with self.subTest(width=width):
                self.assertTrue(all(x + w <= width and y + h <= width for x, y, w, h in rects))
                self.assertFalse(any(overlaps(rects[i], rects[j])
                                     for i in range(len(rects)) for j in range(i + 1, len(rects))))
        self.assertEqual([(p["className"], p["itemName"]) for p in hallow._expansion_plans(58)],
                         [(c, n) for c, n, _, _ in FIRST_EXPANSION_OBJECTS])

    def test_new_object_ids_skip_storage_reservations(self):
        save = unlocked_save()
        save["userInfo"]["player"]["storageData"]["50"] = {}
        enter_hallow(save, width=58)
        result = hallow.record_expansion_lifecycle(save, previous_world=PREVIOUS,
            item_name="xhwfarm14", score_experiments={"fv_hallow": 1})
        self.assertEqual(result["objects"], [51, 52, 53, 54])

    def test_dormant_gates_stay_closed_after_unlock(self):
        import world_travel
        save = unlocked_save()
        self.assertNotIn("hallow", world_travel.SUPPORTED_WORLDS)
        before = copy.deepcopy(save)
        with self.assertRaisesRegex(ValueError, "not restored"):
            hallow.guard_land_purchase()
        with self.assertRaisesRegex(ValueError, "Travel currently supports"):
            world_travel.switch(save, "hallow", True, now=2000)
        self.assertEqual(save, before)


if __name__ == "__main__":
    unittest.main()
