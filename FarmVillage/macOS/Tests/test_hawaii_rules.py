"""Focused read-only Hawaii contracts; no activation, save or browser writes."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence  # Redirect writable paths before importing product code.
import hawaii_rules as hawaii


def saved(total=6000):
    return {"opaqueImport": {"keep": [1, 2, 3]}, "userInfo": {"player": {
        "gold": 123456, "cash": 50, "worldCurrencies": {
            "coconuts": {"total": total, "earned": 17, "purchased": 8, "extra": "preserved"},
            "trowels": {"total": 91}}}}}


class HawaiianParadiseRulesTests(unittest.TestCase):
    def test_original_currency_access_and_source_contract_are_independent(self):
        rules = hawaii.recovered_rules()
        self.assertEqual((rules["worldType"], rules["storageId"], rules["currency"]),
                         ("hawaii", -11, "coconuts"))
        self.assertEqual(rules["farming"], {"plowCost": "15", "plowCurrency": "coconuts"})
        self.assertEqual(rules["minimumXP"], 3700)
        self.assertIsNone(rules["startingFarm"])
        self.assertEqual(rules["access"]["earlyAccess"]["attributes"], {"cashCost": "45"})
        rewards = rules["access"]["allAccess"]["children"][1]["children"]
        self.assertEqual([row["attributes"] for row in rewards], [
            {"type": "world_unlock", "value": "hawaii"},
            {"type": "unlock_world_currency", "unit": "coconuts", "value": "6000"}])
        rules["plotLimits"][50]["ground"] = 9999
        rules["sourceHashes"].clear()
        self.assertEqual(hawaii.plot_limit(50, "land"), 45)
        self.assertEqual(len(hawaii.recovered_rules()["sourceHashes"]), 6)

    def test_exact_ground_and_water_caps_at_every_supported_width(self):
        ground = (45, 55, 65, 90, 100, 145, 175, 215, 260, 310, 370, 415,
                  465, 495, 530, 565, 595, 630, 665, 700, 735, 770, 805, 849, 897)
        water = (10, 20, 40, 60, 85, 110, 135, 165, 195, 225, 260, 290,
                 325, 350, 390, 430, 470, 510, 550, 590, 630, 670, 710, 760, 810)
        for width, land_cap, water_cap in zip(range(50, 243, 8), ground, water):
            with self.subTest(width=width):
                self.assertEqual(hawaii.plot_limit(width, "default"), land_cap)
                self.assertEqual(hawaii.plot_limit(width, "land"), land_cap)
                self.assertEqual(hawaii.plot_limit(width, "water"), water_cap)
                hawaii.guard_plot_counts(width, ground=land_cap, water=water_cap)
                with self.assertRaisesRegex(ValueError, "land plot limit"):
                    hawaii.guard_plot_counts(width, ground=land_cap + 1, water=0)
                with self.assertRaisesRegex(ValueError, "water plot limit"):
                    hawaii.guard_plot_counts(width, ground=0, water=water_cap + 1)

    def test_unknown_width_terrain_or_counts_do_not_get_fallback_caps(self):
        for width in (None, False, "50", 49, 51, 250, -1, 50.5, float("inf"), 10 ** 1000):
            with self.subTest(width=str(width)[:25]), self.assertRaises(ValueError):
                hawaii.plot_limit(width, "land")
        for terrain in (None, False, 0, "ground", "shoreline", "terrace", "farm"):
            with self.subTest(terrain=terrain), self.assertRaises(ValueError):
                hawaii.plot_limit(50, terrain)
        for count in (None, False, -1, "1", 0.5, float("nan"), 10 ** 1000):
            with self.subTest(count=str(count)[:25]), self.assertRaises(ValueError):
                hawaii.guard_plot_counts(50, ground=count, water=0)

    def test_all_access_requires_both_original_server_experiments_and_level(self):
        experiments = {"fv_hawaii": 1, "fv_hawaii_for_all": 1}
        before = copy.deepcopy(experiments)
        hawaii.guard_all_access(xp=3700, experiments=experiments, already_unlocked=False)
        self.assertEqual(experiments, before)
        for xp, supplied, owned in ((3699, experiments, False), (3700, experiments, True),
                (3700, {}, False), (3700, {"fv_hawaii": 1}, False),
                (3700, {"fv_hawaii": True, "fv_hawaii_for_all": 1}, False),
                (3700, {"fv_hawaii": 1, "fv_hawaii_for_all": 0}, False),
                (3700, None, False), (3700, experiments, None), (False, experiments, False)):
            with self.subTest(xp=xp, supplied=supplied, owned=owned), self.assertRaises(ValueError):
                hawaii.guard_all_access(xp=xp, experiments=supplied, already_unlocked=owned)

    def test_historical_access_dates_are_retained_and_never_substitute_for_all_access(self):
        prereqs = hawaii.recovered_rules()["prerequisites"]
        for key, start, end in (("fv_xhi_early_access", "2/27/2012", "3/5/2012"),
                                ("fv_xhi_general_access", "3/5/2012", "5/28/2012")):
            self.assertEqual([n["attributes"] for n in prereqs[key]["children"]][1:],
                             [{"type": "start_time", "value": start},
                              {"type": "end_time", "value": end}])

    def test_coconut_total_stays_separate_from_coins_and_other_imported_fields(self):
        save = saved(15)
        before = copy.deepcopy(save)
        self.assertEqual(hawaii.coconut_balance(save), 15)
        hawaii.guard_coconut_affordability(save, 15)
        with self.assertRaisesRegex(ValueError, "not enough coconuts"):
            hawaii.guard_coconut_affordability(save, 16)
        self.assertEqual(save, before)

    def test_missing_coconut_currency_never_initializes_the_6000_access_grant(self):
        for save in ({}, {"userInfo": {"player": {"gold": 999999}}},
                     {"userInfo": {"player": {"worldCurrencies": {"trowels": {"total": 30}}}}}):
            before = copy.deepcopy(save)
            self.assertIsNone(hawaii.coconut_balance(save))
            with self.assertRaisesRegex(ValueError, "not been unlocked"):
                hawaii.guard_coconut_affordability(save, 0)
            self.assertEqual(save, before)

    def test_malformed_imported_currency_is_rejected_without_coercion_or_mutation(self):
        for record in ({}, 6000, {"total": "6000"}, {"total": True}, {"total": -1},
                       {"total": 1.5}, {"total": float("inf")}, {"total": 2 ** 53}):
            save = saved()
            save["userInfo"]["player"]["worldCurrencies"]["coconuts"] = record
            before = copy.deepcopy(save)
            with self.subTest(record=record), self.assertRaises(ValueError):
                hawaii.coconut_balance(save)
            self.assertEqual(save, before)
        for save in ([], {"userInfo": []}, {"userInfo": {"player": []}},
                     {"userInfo": {"player": {"worldCurrencies": []}}}):
            with self.subTest(save=save), self.assertRaises(ValueError):
                hawaii.coconut_balance(save)

    def test_tuning_and_coconut_buff_are_evidence_not_an_assumed_base_reward(self):
        rules = hawaii.recovered_rules()["currencyRules"]
        self.assertEqual(rules["inflowExperiment"], "fv_hawaii_coconuts_tuning")
        self.assertEqual(rules["displayVariant"], 1)
        self.assertEqual(rules["inflowMultipliers"],
                         {0: "1.0", 1: ".85", 2: ".90", 3: ".95", 4: "1.0",
                          5: "1.0", 6: "1.05", 7: "1.1", 8: "1.15"})
        self.assertEqual(rules["buffs"], ["coco_gain"])
        with self.assertRaisesRegex(ValueError, "not restored"):
            hawaii.guard_transaction(saved(), amount=100, operation="harvest")

    def test_client_expansion_grants_preserve_duplicates_and_last_definition_wins(self):
        rules = hawaii.recovered_rules()
        raw = [row for row in rules["expansionAddedDefinitions"] if row["width"] == 138]
        self.assertEqual(len(raw), 2)
        self.assertEqual([obj["code"] for obj in raw[0]["objects"]], ["0T8", "0T8", "0T9", "0T9"])
        self.assertEqual([obj["code"] for obj in raw[1]["objects"]], ["0T8", "0RC", "0Ua", "0T9"])
        effective = hawaii.client_expansion_grants(138)
        self.assertEqual([obj["code"] for obj in effective], ["0T8", "0RC", "0Ua", "0T9"])
        self.assertEqual(effective[1], {"code": "0RC", "state": "construct_0",
                                      "position": {"x": 0, "y": 50, "z": 0}})
        first = hawaii.client_expansion_grants(58)
        self.assertEqual(first[2], {"code": "1uN", "state": "static",
                                   "position": {"x": 0, "y": 22, "z": 0}})
        effective.clear()
        self.assertEqual(len(hawaii.client_expansion_grants(138)), 4)
        for width in (50, 146, 170, 242):
            self.assertEqual(hawaii.client_expansion_grants(width), [])

    def test_catalog_keeps_water_seed_world_currency_and_non_currency_exceptions(self):
        water_seeds = ("mussels", "ono", "rockcrab", "stonecrab", "tunayellowfin")
        for name in water_seeds:
            with self.subTest(name=name):
                item = hawaii.item_rules(name)
                self.assertEqual(item["market"], "coconuts")
                self.assertEqual(item["harvestYield"]["type"], "coconuts")
                self.assertEqual(item["requirements"]["requirement"], {"name": "hawaii", "className": "World"})
                self.assertEqual(hawaii.item_terrain_codes(name), (2,))
        orchid = hawaii.item_rules("hawaiianorchid")
        self.assertEqual((orchid["cost"], orchid["harvestYield"]["yield"]), ("230", "465"))
        self.assertEqual(hawaii.item_terrain_codes("hawaiianorchid"), (1,))
        # World exclusivity does not imply every crop is sold/yielded in coconuts.
        for name in ("blackbatflower", "vinejade", "whitehibiscus"):
            item = hawaii.item_rules(name)
            self.assertNotIn("market", item)
            self.assertNotIn("harvestYield", item)
        royal = hawaii.item_rules("royaltaro")
        self.assertIn({"name": "taro", "className": "Mastery", "level": "2"}, royal["requirements"]["requirement"])
        self.assertEqual(hawaii.item_rules("stonecrab")["limitedEnd"], "02/16/2013")
        orchid["harvestYield"]["yield"] = "999999"
        self.assertEqual(hawaii.item_rules("hawaiianorchid")["harvestYield"]["yield"], "465")
        for name in ("xhifarm99", "does-not-exist", None):
            with self.assertRaises(ValueError):
                hawaii.item_rules(name)

    def test_exact_land_offers_keep_raw_currency_and_original_client_cash_override(self):
        land = hawaii.land_rules("xhifarm14")
        self.assertEqual((land["width"], land["catalog"]["market"], land["catalog"]["cost"],
                          land["catalog"]["cash"], land["clientSaleCash"]),
                         (58, "coconuts", "11250", "30", 1))
        self.assertEqual(land["plotLimits"], {"ground": 55, "water": 20})
        self.assertEqual(len(land["clientAddedObjects"]), 3)
        self.assertEqual(hawaii.land_rules("xhifarm34")["addedDefinitionCount"], 2)
        self.assertEqual(hawaii.land_rules("xhifarm36")["addedDefinitionCount"], 0)
        cash = hawaii.land_rules("xhifarm60_cash")
        self.assertEqual((cash["width"], cash["catalog"]["market"], cash["catalog"]["cash"],
                          cash["clientSaleCash"]), (242, "cash", "250", 1))
        self.assertEqual(cash["catalog"]["experimentGate"], "fv_expansion_ec_lc_hi_jf_60")
        self.assertEqual(hawaii.land_rules("xhifarm12")["catalog"]["buyable"], "false")
        for name in ("xlcfarm14", "XX", "xhifarm99", "watertractor"):
            with self.assertRaises(ValueError):
                hawaii.land_rules(name)

    def test_shipping_is_a_separate_paid_license_and_expansion_grants_are_special_items(self):
        package = hawaii.item_rules("pkg_hawaiiXfer")
        self.assertEqual((package["market"], package["cash"], package["marketPrereqs"]),
                         ("cash", "75", "hawaiiParadiseXfer_visible"))
        self.assertEqual(hawaii.item_rules("consume_hawaiiXfer")["rewards"]["reward"],
                         {"type": "world_content_license", "licenseType": "world", "value": "hawaii"})
        self.assertEqual(hawaii.item_rules("xhi_flotsamgift_xl")["className"], "FixedTreasureConstructionBuilding")
        self.assertEqual(hawaii.item_rules("watertractor")["className"], "Tractor")

    def test_archive_drift_fails_closed_for_every_pinned_source(self):
        rules = hawaii.recovered_rules()
        with patch.object(hawaii.Path, "read_bytes", return_value=b"changed source"):
            for name in rules["sourceHashes"]:
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "changed and require review"):
                    hawaii._source(name)


if __name__ == "__main__":
    unittest.main()
