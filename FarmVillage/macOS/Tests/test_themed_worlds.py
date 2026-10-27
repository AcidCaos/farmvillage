"""Themed-world rules: travel, placement, prices, plowing and fences.

Inactive fixture baselines and single-world activations are patched per test.
The activated-farm checks run once per SPECS world (one TestCase class each).
Every test uses an in-memory disposable save; nothing writes a real save.
"""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence  # Establish disposable writable paths before bundle imports.
import creative_worlds
import items
import themed_worlds as tw
import world_currency_conversion as wcc
import world_travel
import game_settings
from game_settings import level_to_xp

NOW = 1800000000
RICH = {"gold": 10_000_000, "cash": 100_000}


def clear_theme_caches():
    """Drop the process-wide admission caches.

    themed_worlds.catalog_rules is cached for the life of the process, and the Market admissions built
    from it are cached too. Both depend on the served experiments, which several tests here patch. Clear
    them whenever a test changes that input, and again afterwards, so a result computed under a patch is
    neither read stale by this test nor kept for the tests that run after it.
    """
    tw.catalog_rules.cache_clear()
    presentation = sys.modules.get("themed_market_presentation")
    if presentation is not None:
        presentation._admissions.cache_clear()


def ensure_levels():
    if game_settings._level_xp_map is None:
        game_settings.load_game_settings()


def dormant_experiments():
    """Explicit unit fixture for preserved retired contracts, never production activation."""
    values = dict(tw.served_experiments())
    for world in ("glen", "hlights"):
        for gate in tw.recovered_rules(world)["experiments"].values():
            values[gate] = 1
    return values


def home_world():
    return {"id": 1, "sizeX": 50, "sizeY": 50, "objectsArray": [], "messageManager": []}


def base_save(*, level=15, gold=1000, cash=100):
    ensure_levels()
    return {"userInfo": {"currentWorldType": "farm",
                         "worldSummaryData": {"farm": {"storageId": -2, "firstLoaded": 1,
                                                       "lastLoaded": 1}},
                         "unlockedWorldTypes": ["farm"],
                         "player": {"xp": level_to_xp(level), "gold": gold, "cash": cash,
                                    "userId": "owner", "storageData": {"-2": {}, "-1": {}}}},
            "world": home_world()}


def roundtrip(save):
    return json.loads(json.dumps(save))


def catalog_item(name):
    if getattr(items, "_cached_items", None) is None:
        items.load_items()
    item = items.get_item_by_name(name)
    if item is None:
        raise AssertionError("catalog item missing: " + name)
    return copy.deepcopy(item)


def plot(index, state="plowed", **extra):
    return {"id": index, "className": "Plot", "state": state, "itemName": None,
            "position": {"x": 0, "y": 0, "z": 0}, **extra}


def balance_key(currency):
    return "gold" if currency == "coins" else "cash"


class DormantDefaultTests(unittest.TestCase):
    def test_nothing_is_reachable_while_the_active_list_is_empty(self):
        with mock.patch.object(tw, "ACTIVE_WORLDS", frozenset()):
            self._assert_dormant()

    def _assert_dormant(self):
        self.assertEqual(tw.active_worlds(), frozenset())
        self.assertEqual(world_travel.supported_worlds(), world_travel.SUPPORTED_WORLDS)
        save = base_save()
        with self.assertRaisesRegex(ValueError, "Travel currently supports"):
            world_travel.switch(save, "rainforest", True, now=NOW)
        with self.assertRaisesRegex(ValueError, "Sunflower Meadows"):
            creative_worlds.create(save, "rainforest", "allAccess", now=NOW)
        self.assertEqual(save, base_save())


class DormantCandidateContractTests(unittest.TestCase):
    candidates = ("toyland", "sleepyhollow", "australia", "fforest", "htown", "atlantis", "glen", "hlights")

    def test_eight_accepted_contracts_are_refused_in_an_inactive_fixture(self):
        baseline = frozenset({"rainforest", "mediterranean", "storybook", "candy", "oasis", "oz"})
        self.assertEqual(tw.ACTIVE_WORLDS, (baseline | set(self.candidates)) - {"glen", "hlights"})
        with mock.patch.object(tw, "ACTIVE_WORLDS", baseline):
            visible = {entry["worldType"] for entry in creative_worlds.candidates()}
            for name in self.candidates:
                with self.subTest(world=name):
                    self.assertNotIn(name, world_travel.supported_worlds())
                    self.assertNotIn(name, visible)
                    save = base_save()
                    before = copy.deepcopy(save)
                    with self.assertRaisesRegex(ValueError, "awaiting original-client"):
                        tw.create(save, name, now=NOW)
                    self.assertEqual(save, before)

    def test_original_distinct_experiments_admit_only_the_world_and_its_land_gates(self):
        for world in self.candidates:
            rules = tw.recovered_rules(world)
            with self.subTest(world=world):
                self.assertTrue(tw._own_gate(rules["experiments"]["master"], world))
                self.assertTrue(tw._own_gate(rules["experiments"]["forAll"], world))
                self.assertFalse(tw._own_gate("fv_xtl_shipping_license", world))
                self.assertFalse(tw._own_gate("fv_xsh_starter", world))
                self.assertFalse(tw._own_gate("fv_rainforest", world))
        self.assertEqual(tw.recovered_rules("toyland")["experiments"],
                         {"master": "fv_xtl_master", "forAll": "fv_xtl_for_all"})
        self.assertEqual(tw.recovered_rules("sleepyhollow")["experiments"],
                         {"master": "fv_xsh_master", "forAll": "fv_xsh_for_all"})

    def test_legacy_storage_absence_and_local_theme_are_exact_and_disclosed(self):
        self.assertEqual((tw.recovered_rules("australia")["storageId"],
                          tw.recovered_rules("htown")["storageId"]), (-21, -15))
        with mock.patch.object(tw, "ACTIVE_WORLDS", {"htown"}):
            card = next(entry for entry in creative_worlds.candidates() if entry["worldType"] == "htown")
            self.assertIn("theme", card["starter"])
            self.assertIn("not recovered", card["starter"])
        original_xml = tw._xml
        def changed_xml(name):
            xml = original_xml(name)
            if name == "gameSettings.xml.gz":
                xml.find("expansions/expansion[@name='australia']").set("storageId", "-21")
            return xml
        tw.recovered_rules.cache_clear()
        try:
            with mock.patch.object(tw, "_xml", side_effect=changed_xml), self.assertRaisesRegex(ValueError, "world record"):
                tw.recovered_rules("australia")
        finally:
            tw.recovered_rules.cache_clear()

    def test_number_inventory_comparison_does_not_truncate_fractional_imports(self):
        for value in (-21.9, "-21.9", float("inf"), "unrecovered"):
            summary = {"storageId": value, "original": ["preserve"]}
            before = json.dumps(summary, sort_keys=True).encode()
            with self.subTest(value=value):
                self.assertFalse(tw.summary_claims_storage(summary, -21))
                self.assertEqual(json.dumps(summary, sort_keys=True).encode(), before)
        for value in (-21, "-21", " -21.0 ", "-2.1e1"):
            self.assertTrue(tw.summary_claims_storage({"storageId": value}, -21))

    def test_imported_storage_or_summary_claims_never_get_absorbed(self):
        for world in self.candidates:
            with self.subTest(world=world), mock.patch.object(tw, "ACTIVE_WORLDS", {world}):
                for imported in ("summary", "numeric-string-summary", "ledger"):
                    save = base_save()
                    storage_id = tw.storage_id(world)
                    if imported in ("summary", "numeric-string-summary"):
                        imported_id = str(storage_id) if imported == "numeric-string-summary" else storage_id
                        save["userInfo"]["worldSummaryData"]["imported-unrestored-world"] = {"storageId": imported_id}
                    else:
                        save["userInfo"]["player"]["storageData"][str(storage_id)] = {"HB": 1}
                    before = copy.deepcopy(save)
                    with self.assertRaises(ValueError):
                        creative_worlds.create(save, world, "allAccess", now=NOW)
                    self.assertEqual(save, before)




class RecoveredRecordTests(unittest.TestCase):
    def test_contracts_match_the_archive_and_drop_score_rewards(self):
        for world, spec in tw.SPECS.items():
            with self.subTest(world=world):
                rules = tw.recovered_rules(world)
                self.assertEqual((rules["name"], rules["storageId"], rules["tileSet"],
                                  rules["minimumLevel"]),
                                 (spec["name"], spec["storageId"], spec["theme"], 15))
                self.assertEqual(rules["rewards"], [{"type": "world_unlock", "value": world}])
                self.assertEqual((rules["initialSize"], rules["plotCeiling"]), (50, 5500))
                self.assertEqual((rules["cashCost"], rules["coinCost"], rules["currency"]),
                                 (0, 0, "coins"))
                self.assertEqual(rules["localStarter"], "empty-%s-v1" % world)
                self.assertIsNone(rules["score"])
                self.assertEqual(rules["experiments"]["master"], spec.get("masterExperiment", "fv_" + world))

    def test_admitted_items_are_basic_world_items_with_recovered_prices(self):
        for world in tw.active_worlds():
            with self.subTest(world=world):
                catalog = tw.catalog_rules(world)
                self.assertTrue(tw.allowed_seeds(world))
                self.assertEqual(catalog["unpriced"], {})
                for name, rule in catalog["items"].items():
                    self.assertIn(rule["type"], tw.TYPES)
                    if rule["price"] is None:
                        self.assertEqual((world, name, rule["className"]),
                            ("rainforest", "xrf_fountainofyouth", "FeatureBuilding"))
                        self.assertTrue(tw._world_feature(catalog_item(name), world)["ownedOnly"])
                        continue
                    self.assertIsNotNone(rule["price"], name)
                    self.assertIn(rule["price"]["currency"], ("coins", "cash"))
        for world in ('glen', 'hlights'):
            with self.subTest(retired=world):
                self.assertEqual(tw.allowed_seeds(world), [])

    def test_original_expansion_additions_are_recorded_for_every_world(self):
        for world in tw.SPECS:
            with self.subTest(world=world):
                additions = tw.expansion_additions(world)
                self.assertEqual(min(additions), 58)
                self.assertEqual(sum(len(v) for v in additions.values()), {"australia": 40, "htown": 36, "atlantis": 40, "glen": 36}.get(world, 37))


class ActivatedFarmHelpers:
    """Shared setup for activated-farm tests. Not a TestCase; mixed in below."""

    world = None

    def setUp(self):
        # Registered first, so it runs last: after the patches below are undone, drop whatever was
        # computed under them. Otherwise the retired worlds' "switched on" admissions leak into later tests.
        self.addCleanup(clear_theme_caches)
        if self.world in {"glen", "hlights"}:
            patcher = mock.patch.object(tw, "served_experiments", return_value=dormant_experiments())
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(tw, "ACTIVE_WORLDS", frozenset({self.world}))
        patcher.start()
        self.addCleanup(patcher.stop)
        clear_theme_caches()  # never reuse a result computed before the patches took effect

    def unlocked(self, **kwargs):
        save = base_save(**{**RICH, **kwargs})
        before_user = copy.deepcopy(save["userInfo"])
        self.assertTrue(creative_worlds.create(save, self.world, "allAccess", now=NOW))
        self.assertEqual(save["userInfo"]["player"]["gold"], before_user["player"]["gold"])
        self.assertEqual(save["userInfo"]["player"]["cash"], before_user["player"]["cash"])
        return save

    def travelled(self, **kwargs):
        save = self.unlocked(**kwargs)
        world_travel.switch(save, self.world, False, now=NOW)
        return save

    def purchasable(self, names):
        """First name whose ordinary purchase passes the date and access guards at NOW."""
        save = self.travelled()
        for name in names:
            try:
                tw.guard_purchase(save, catalog_item(name), now=NOW)
            except ValueError:
                continue
            return name
        raise AssertionError("no purchasable item for " + self.world)


class ActivatedFarmCases(ActivatedFarmHelpers):
    """Activated-farm checks, generated below as one TestCase class per SPECS world."""

    def test_all_access_is_free_idempotent_and_survives_reload(self):
        save = self.unlocked()
        target = save[world_travel.STATE_KEY]["inactive"][self.world]
        self.assertEqual((target["sizeX"], target["sizeY"], target["objectsArray"]), (50, 50, []))
        self.assertEqual((target["tileSet"], target["localStarter"]),
                         (tw.SPECS[self.world]["theme"], "empty-%s-v1" % self.world))
        self.assertEqual(save["userInfo"]["worldSummaryData"][self.world]["storageId"],
                         tw.storage_id(self.world))
        self.assertIn(self.world, save["userInfo"]["unlockedWorldTypes"])
        self.assertFalse(creative_worlds.create(save, self.world, "allAccess", now=NOW))
        reloaded = roundtrip(save)
        self.assertFalse(creative_worlds.create(reloaded, self.world, "allAccess", now=NOW))
        self.assertEqual(reloaded["userInfo"]["player"]["gold"], save["userInfo"]["player"]["gold"])
        world_travel.validate(reloaded)

    def test_rejections_leave_the_save_unchanged(self):
        with self.subTest("level 14"):
            save = base_save(level=14)
            before = copy.deepcopy(save)
            with self.assertRaisesRegex(ValueError, "requires player level"):
                creative_worlds.create(save, self.world, "allAccess", now=NOW)
            self.assertEqual(save, before)
        with self.subTest("general access option"):
            save = base_save()
            before = copy.deepcopy(save)
            with self.assertRaisesRegex(ValueError, "all-access option"):
                creative_worlds.create(save, self.world, "generalAccess", now=NOW)
            self.assertEqual(save, before)
        self.addCleanup(clear_theme_caches)  # runs after the patch below is undone
        with self.subTest("experiment not served"), \
                mock.patch.object(tw, "served_experiments", return_value={}):
            clear_theme_caches()
            save = base_save()
            before = copy.deepcopy(save)
            with self.assertRaisesRegex(ValueError, "not served"):
                creative_worlds.create(save, self.world, "allAccess", now=NOW)
            self.assertEqual(save, before)

    def test_travel_round_trip_and_reload(self):
        save = self.unlocked()
        world_travel.switch(save, self.world, False, now=NOW)
        self.assertEqual((save["userInfo"]["currentWorldType"], save["world"]["tileSet"]),
                         (self.world, tw.SPECS[self.world]["theme"]))
        self.assertEqual(tw.guard_snapshot(self.world, save["world"]), 0)
        world_travel.validate(save)
        world_travel.switch(save, "farm", False, now=NOW)
        self.assertEqual(save["userInfo"]["currentWorldType"], "farm")
        reloaded = roundtrip(save)
        world_travel.switch(reloaded, self.world, False, now=NOW)
        self.assertEqual(reloaded["userInfo"]["currentWorldType"], self.world)
        world_travel.validate(reloaded)

    def test_seed_allow_list_bounds_and_single_purchase_charge(self):
        seed = self.purchasable(tw.allowed_seeds(self.world))
        save = self.travelled()
        price = tw.catalog_rules(self.world)["items"][seed]["price"]
        key = balance_key(price["currency"])
        snapshot = plot(900, "planted", itemName=seed, position={"x": 4, "y": 4, "z": 0})
        snapshot["className"] = "Plot"
        before = save["userInfo"]["player"][key]
        tw.guard_action(save, "place", snapshot, [{}], neighbor_count=0, now=NOW)
        self.assertEqual(save["userInfo"]["player"][key], before)
        charge = tw.charge_purchase(save, catalog_item(seed), neighbor_count=0, now=NOW)
        self.assertEqual(charge, {"currency": price["currency"], "amount": price["amount"]})
        self.assertEqual(save["userInfo"]["player"][key], before - price["amount"])
        admitted = tw.catalog_rules(self.world)["items"]
        off_world = next(i["name"] for i in items.get_items()
                         if i.get("type") == "seed" and i["name"] not in admitted)
        with self.assertRaisesRegex(ValueError, "not admitted"):
            tw.guard_action(save, "place", dict(snapshot, itemName=off_world), [{}], now=NOW)
        out = dict(snapshot, position={"x": 48, "y": 4, "z": 0})
        with self.assertRaisesRegex(ValueError, "outside"):
            tw.guard_action(save, "place", out, [{}], now=NOW)

    def test_decoration_is_placed_with_its_catalog_class_and_charged_once(self):
        admitted = tw.catalog_rules(self.world)["items"]
        decorations = sorted(n for n, r in admitted.items() if r["type"] == "decoration")
        name = self.purchasable(decorations)
        rule = admitted[name]
        price = rule["price"]
        # The catalog class wins; the per-type default applies only when the catalog names none.
        klass = rule["className"] or "Decoration"
        save = self.travelled()
        key = balance_key(price["currency"])
        snapshot = {"tempId": -1, "position": {"x": 19, "y": 19, "z": 0}, "state": "horizontal",
                    "instanceDataStoreKey": None, "id": 63000, "deleted": False, "components": {},
                    "direction": 0, "itemName": name, "className": klass}
        before = copy.deepcopy(save)
        tw.guard_action(save, "place", snapshot, [{"currency": price["currency"]}], now=NOW)
        self.assertEqual(save, before)
        self.assertEqual(tw.charge_purchase(save, catalog_item(name), now=NOW),
                         {"currency": price["currency"], "amount": price["amount"]})
        self.assertEqual(save["userInfo"]["player"][key], before["userInfo"]["player"][key] - price["amount"])
        wrong = "Decoration" if klass != "Decoration" else "RotateableDecoration"
        with self.assertRaisesRegex(ValueError, "recovered object class"):
            tw.guard_action(before, "place", dict(snapshot, className=wrong), [{}], now=NOW)

    def test_placement_retry_is_free_and_never_recharged(self):
        seed = self.purchasable(tw.allowed_seeds(self.world))
        save = self.travelled()
        saved = plot(7000, "planted", itemName=seed, position={"x": 4, "y": 4, "z": 0})
        saved["tempId"] = 900
        save["world"]["objectsArray"].append(saved)
        retry = plot(900, "planted", itemName=seed, position={"x": 4, "y": 4, "z": 0})
        player = save["userInfo"]["player"]
        balances = (player["gold"], player["cash"])
        tw.guard_action(save, "place", retry, [{}], now=NOW)
        self.assertEqual((player["gold"], player["cash"]), balances)

    def test_purchase_guard_rejects_unpaid_or_short_balance_without_debit(self):
        seed = self.purchasable(tw.allowed_seeds(self.world))
        save = self.travelled()
        price = tw.catalog_rules(self.world)["items"][seed]["price"]
        save["userInfo"]["player"][balance_key(price["currency"])] = price["amount"] - 1
        before = copy.deepcopy(save)
        with self.assertRaisesRegex(ValueError, "Not enough currency"):
            tw.charge_purchase(save, catalog_item(seed), now=NOW)
        self.assertEqual(save, before)

    def test_plow_costs_home_rate_coins_once_and_retries_free(self):
        save = self.travelled()
        save["userInfo"]["player"]["gold"] = 40
        save["userInfo"]["player"]["jade"] = 9999  # A world currency is never charged to plow.
        self.assertEqual(tw.plow_cost(), 15)
        self.assertEqual(tw.plow_charge(save, plot(1, "plowed"), None), 15)
        self.assertEqual(save["userInfo"]["player"]["gold"], 25)
        saved = plot(1, "plowed")
        self.assertEqual(tw.plow_charge(save, saved, saved), 0)
        self.assertEqual(save["userInfo"]["player"]["gold"], 25)
        save["userInfo"]["player"]["gold"] = 14
        before = copy.deepcopy(save)
        with self.assertRaisesRegex(ValueError, "Not enough coins"):
            tw.plow_charge(save, plot(2, "plowed"), None)
        self.assertEqual(save, before)

    def test_expansion_past_the_initial_farm_is_refused_without_charge(self):
        offer = tw.catalog_rules(self.world)["expansions"][58][0]
        save = self.travelled()
        before = copy.deepcopy(save)
        with self.assertRaisesRegex(ValueError, "not (?:restored|recovered)"):
            tw.expand(save, catalog_item(offer["name"]), offer["price"]["currency"], now=NOW)
        self.assertEqual(save, before)

    def test_quest_score_and_currency_offers_are_rejected(self):
        self.assertEqual(tw._reasons({"type": "decoration", "className": "Decoration",
                                      "requiredQuest": "q1",
                                      "requirements": {"requirement": [
                                          {"name": self.world, "className": "World"}]}},
                                     self.world), ["requiredQuest"])
        mastery = {"type": "seed", "requirements": {"requirement": [
            {"name": self.world, "className": "World"}, {"name": "x", "className": "Mastery"}]}}
        self.assertIn("requirement", tw._reasons(mastery, self.world))
        rates = wcc.recovered_rates(tw._catalog())
        converted = tw._price({"name": "x", "market": "jade", "cost": "6000"}, rates)
        self.assertEqual((converted["currency"], converted["amount"], converted["converted"]),
                         ("cash", 6, True))
        with self.assertRaisesRegex(ValueError, "no recovered price"):
            tw._price({"name": "x", "market": "berry", "cost": "10"}, rates)
        self.assertNotIn("unlock_world_score", str(tw.recovered_rules(self.world)["rewards"]))

    def test_snapshot_guard_rejects_special_objects_and_wrong_tileset(self):
        save = self.travelled()
        with self.assertRaisesRegex(ValueError, "unsupported object"):
            tw.guard_snapshot(self.world, dict(save["world"], objectsArray=[
                {"id": 3, "className": "FishermansCoveBuilding"}]))
        with self.assertRaisesRegex(ValueError, "ordinary-ground"):
            tw.guard_snapshot(self.world, dict(save["world"], tileSet="grass_theme"))

    def test_incoming_special_plots_are_rejected_before_they_can_poison_the_save(self):
        save = self.travelled()
        seed = self.purchasable(tw.allowed_seeds(self.world))
        before = copy.deepcopy(save)
        for action, snapshot in (
                ("plow", plot(900)),
                ("place", plot(900, "planted", itemName=seed))):
            for flag in tw.SPECIAL_PLOT_FLAGS:
                with self.subTest(action=action, flag=flag):
                    with self.assertRaisesRegex(ValueError, "Specialized plots"):
                        tw.guard_action(save, action, {**snapshot, flag: True}, [{}], now=NOW)
                    self.assertEqual(save, before)
        # A rejected placement must leave the world valid and travel usable.
        tw.guard_snapshot(self.world, save["world"])
        world_travel.switch(save, "farm", False, now=NOW)


class RainforestPacketTests(ActivatedFarmHelpers, unittest.TestCase):
    world = "rainforest"

    def test_decoration_keeps_its_catalog_class_like_the_original_client(self):
        # Exact packet shape from the browser (2026-10-23): a Rainforest
        # decoration whose catalog class is RotateableDecoration.
        save = self.unlocked()
        world_travel.switch(save, self.world, False, now=NOW)
        name = "xrf_eaglewallruins"
        rule = tw.catalog_rules(self.world)["items"][name]
        self.assertEqual(rule["className"], "RotateableDecoration")
        snapshot = {"tempId": -1, "position": {"x": 19, "y": 19, "z": 0}, "state": "horizontal",
                    "instanceDataStoreKey": None, "id": 63000, "deleted": False, "components": {},
                    "direction": 0, "itemName": name, "className": "RotateableDecoration"}
        save["userInfo"]["player"]["gold"] = 10000
        before = copy.deepcopy(save)
        tw.guard_action(save, "place", snapshot, [{"currency": "coins"}], now=NOW)
        self.assertEqual(tw.charge_purchase(save, catalog_item(name), now=NOW),
                         {"currency": "coins", "amount": 5000})
        self.assertEqual(save["userInfo"]["player"]["gold"], before["userInfo"]["player"]["gold"] - 5000)
        # The per-type default class is not the recovered one for this item.
        with self.assertRaisesRegex(ValueError, "recovered object class"):
            tw.guard_action(before, "place", dict(snapshot, className="Decoration"), [{}], now=NOW)


def _activated_case(world):
    return type("Activated%sTests" % world.capitalize(), (ActivatedFarmCases, unittest.TestCase),
                {"world": world, "__module__": __name__})


globals().update({case.__name__: case for case in (_activated_case(w) for w in tw.SPECS)})


if __name__ == "__main__":
    unittest.main()
