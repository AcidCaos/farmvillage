"""Home Farm heritage pricing: derivation, exclusions, served market and purchase path."""
import copy
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures  # Redirect writable paths before product imports.
import heritage_pricing

NOW = 1800000000


def item(name, **fields):
    base = {"name": name, "code": "c_" + name, "type": "decoration", "className": None, "subtype": "decor",
            "sizeX": "2", "sizeY": "2", "buyable": "false", "archived": "yes"}
    base.update(fields)
    return base


def world(name, compare="any", requirements=None, **fields):
    if requirements is None:
        requirements = {"compare": compare, "requirement": {"name": name, "className": "World"}}
    return item(name, requirements=requirements, **fields)


def overlay(records):
    working = copy.deepcopy(records)
    report = heritage_pricing.apply(working)
    return working, report


def crop(name, **fields):
    """A seed the Home loop can run: coin-priced, a day or less to grow, with a market entry."""
    base = {"name": name, "code": "s_" + name, "type": "seed", "className": None, "subtype": "flowers",
            "sizeX": "4", "sizeY": "4", "growTime": "0.5", "cost": "60", "coinYield": "100",
            "plantXp": "2", "requiredLevel": "5", "buyable": "true", "archived": "yes",
            "mastery": "true", "masteryYield": "1", "masteryLevel": [{"coins": "500", "count": "600", "xp": "25"}],
            "marketEntries": {"marketEntry": {"type": "seed", "subtype": "flowers"}}}
    base.update(fields)
    return base


def locked_crop(name, world_name="avalon", **fields):
    fields.setdefault("requirements", {"compare": "any", "requirement": {"name": world_name, "className": "World"}})
    return crop(name, **fields)


def overlay_with(records, served):
    """The plan and its mutation, with the served experiment configuration supplied."""
    working = copy.deepcopy(records)
    patches, report = heritage_pricing.plan(working, served=served)
    for index, patch in patches.items():
        heritage_pricing._mutate(working[index], patch)
    return working, report


class HeritagePlanTests(unittest.TestCase):
    def setUp(self):
        for target, name, value in ((heritage_pricing, "ENABLED", True),
                                    (heritage_pricing, "_overlaid", heritage_pricing._overlaid),
                                    (heritage_pricing, "_refused", {})):
            patcher = mock.patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_nearest_priced_sibling_supplies_the_farm_cash_price(self):
        records = [item("far_sibling", cash="40", market="cash", buyable="true"),
                   item("target", limitedStart="1/1/2010", limitedEnd="1/1/2011"),
                   item("pad_a", type="tree", subtype="fruit"), item("pad_b", type="tree", subtype="fruit"),
                   item("right_sibling", cash="90", market="cash", buyable="true")]
        patches, report = heritage_pricing.plan(records)
        self.assertEqual(patches[1], {"group": "exclusive", "market": "cash", "cash": "40", "coins": None,
                                      "source": "sibling:0"})
        self.assertNotIn(0, patches)  # Already-priced Home items are left as recovered.
        self.assertEqual(report["sources"], {"sibling": 1})

    def test_equal_distance_prefers_the_earlier_record(self):
        records = [item("left", cash="40", market="cash"), item("target"),
                   item("right", cash="90", market="cash")]
        patches, _ = heritage_pricing.plan(records)
        self.assertEqual((patches[1]["cash"], patches[1]["source"]), ("40", "sibling:0"))

    def test_tier_fallback_uses_lower_median_of_home_visible_footprint(self):
        records = [item("t10", type="tree", subtype="fruit", sizeX="1", sizeY="1", cash="10", market="cash"),
                   item("t30", type="tree", subtype="fruit", sizeX="1", sizeY="1", cash="30", market="cash"),
                   item("t50", type="tree", subtype="fruit", sizeX="1", sizeY="1", cash="50", market="cash"),
                   item("nut_target", type="tree", subtype="nut", sizeX="1", sizeY="1")]
        patches, _ = heritage_pricing.plan(records)
        self.assertEqual((patches[3]["cash"], patches[3]["source"]), ("30", "tier:footprint"))

    def test_locked_items_keep_their_own_price_and_are_rehomed(self):
        record = world("avalon", type="tree", subtype="fruit", cost="5000", limitedStart="1/1/2010",
                       limitedEnd="1/1/2011", experimentGate="fv_avalon")
        records = [record]
        patches, _ = heritage_pricing.plan(records)
        self.assertEqual(patches[0]["source"], "own")
        working, report = overlay(records)
        result = working[0]
        self.assertEqual((result["buyable"], result["archived"], result["cost"]), ("true", "no", "5000"))
        self.assertNotIn("cash", result)
        self.assertNotIn("limitedStart", result)
        self.assertNotIn("limitedEnd", result)
        self.assertNotIn("experimentGate", result)
        self.assertEqual(result["requirements"]["requirement"], {"name": "farm", "className": "World", "strict": "true"})
        self.assertEqual(report["groups"], {"locked": 1})

    def test_unpriced_locked_item_takes_a_farm_cash_price(self):
        records = [world("avalon", type="decoration", subtype="decor", sizeX="1", sizeY="1"),
                   item("neighbour", cash="20", market="cash", sizeX="1", sizeY="1")]
        patches, _ = heritage_pricing.plan(records)
        self.assertEqual((patches[0]["market"], patches[0]["cash"], patches[0]["source"]),
                         ("cash", "20", "sibling:1"))

    def test_world_currency_items_are_excluded_and_left_as_recovered(self):
        records = [world("jadeitem", type="decoration", subtype="decor", market="jade", cost="50000"),
                   world("berryitem", type="decoration", market="berry", cost="30", cash="7")]
        before = copy.deepcopy(records)
        working, report = overlay(records)
        self.assertEqual(working, before)
        self.assertEqual(report["excluded"], {"locked": {"world currency": 2}})

    def test_reserved_worlds_are_excluded_and_left_as_recovered(self):
        records = [world("rainforest", type="decoration", cost="100"),
                   item("multi_reserved", requirements={"compare": "any", "requirement": [
                       {"name": "hlights", "className": "World"}, {"name": "oz", "className": "World"}]},
                       cost="100")]
        before = copy.deepcopy(records)
        working, report = overlay(records)
        self.assertEqual(working, before)
        self.assertEqual(report["excluded"], {"locked": {"reserved world": 2}})

    def test_reserved_worlds_cover_every_themed_and_rule_module_world(self):
        import creative_worlds
        import cove_rules
        import england_progression
        import hallow_rules
        import hawaii_rules
        import themed_worlds
        required = set(themed_worlds.SPECS) | {creative_worlds.WORLD, cove_rules.WORLD, hallow_rules.WORLD,
                                               hawaii_rules.WORLD, england_progression.WORLD, "farm"}
        self.assertLessEqual(required, heritage_pricing.RESERVED_WORLDS)

    def test_multi_world_items_need_any_and_rehome_every_name(self):
        any_record = item("multi_any", requirements={"compare": "any", "requirement": [
            {"name": "yuletide", "className": "World"}, {"name": "winterwonderland", "className": "World"}]},
            cost="100", market=None)
        all_record = dict(any_record, name="multi_all", requirements={"compare": "all", "requirement": [
            {"name": "yuletide", "className": "World"}, {"name": "winterwonderland", "className": "World"}]})
        working, report = overlay([any_record, all_record])
        self.assertEqual([entry["name"] for entry in working if entry.get("buyable") == "true"], ["multi_any"])
        self.assertEqual({node["name"] for node in working[0]["requirements"]["requirement"]}, {"farm"})
        self.assertEqual(report["excluded"], {"locked": {"multiple worlds": 1}})

    def test_exclusions_are_counted_and_leave_records_untouched(self):
        records = [
            item("feature", type="building", className="FeatureBuilding", cost="100", market="cash"),
            world("licensed", cost="100", requirements={"requirement": [
                {"name": "avalon", "className": "World"}, {"name": "farm", "className": "WorldLicense"}]}),
            world("prereq", cost="100", purchasePrereqs="quest_x"),
            world("marketed", cost="100", marketPrereqs="marketHidden"),
            world("gated", cost="100", experiment="fv_x"),
            item("exclusive_gate", experimentGate="fv_mystery"),
            item("malformed_only", cost="na"),
            world("home_priced", cost="100", requirements={"requirement": {"name": "farm", "className": "World"}}),
            item("comma_cost", cash="20", cost="200,000", market="cash"),
        ]
        before = copy.deepcopy(records)
        working, report = overlay(records)
        self.assertEqual(working[0], before[0])
        self.assertEqual(report["excluded"], {
            "locked": {"requirement": 1, "prerequisite": 3},
            "exclusive": {"experiment gate": 1, "malformed price": 1},
        })
        self.assertEqual(report["overlaid"], 0)
        self.assertEqual(working[8], before[8])

    def test_experiment_gate_is_removed_only_from_locked_items(self):
        working, report = overlay([world("avalon", cost="100", experimentGate="fv_avalon")])
        self.assertNotIn("experimentGate", working[0])
        self.assertEqual(report["groups"], {"locked": 1})

    def test_disabled_switch_leaves_the_catalog_exactly_as_recovered(self):
        records = [world("avalon", cost="100"), item("priceless")]
        before = copy.deepcopy(records)
        with mock.patch.object(heritage_pricing, "ENABLED", False):
            working, report = overlay(records)
        self.assertEqual(working, before)
        self.assertEqual(report["overlaid"], 0)

    def test_plan_is_deterministic_and_pure(self):
        records = [item("a", cash="40", market="cash"), item("b"), world("c", cost="10")]
        before = copy.deepcopy(records)
        first, _ = heritage_pricing.plan(records)
        second, _ = heritage_pricing.plan(records)
        self.assertEqual(first, second)
        self.assertEqual(records, before)

    def test_land_terrains_are_the_recovered_home_land_terrain(self):
        import creative_worlds
        self.assertEqual(heritage_pricing.LAND_TERRAINS, creative_worlds._land_terrain_names())

    def test_admitted_crop_keeps_its_own_coin_price_and_is_rehomed(self):
        records = [locked_crop("avalonbloom", experimentGate="fv_avalon", limitedEnd="1/1/2011")]
        working, report = overlay_with(records, {"fv_avalon": 1})
        result = working[0]
        self.assertEqual((result["cost"], result["buyable"], result["archived"]), ("60", "true", "no"))
        self.assertNotIn("market", result)
        self.assertNotIn("limitedEnd", result)
        self.assertEqual(result["experimentGate"], "fv_avalon")
        self.assertEqual(result["requirements"]["requirement"], {"name": "farm", "className": "World", "strict": "true"})
        self.assertEqual((report["groups"], report["sources"]), ({"locked": 1}, {"own": 1}))

    def test_crop_without_coin_price_takes_nearest_sibling_price_in_coins(self):
        records = [crop("far_bloom", cost="40"), crop("other_bloom", subtype="fruit", cost="999"),
                   crop("near_bloom", cost="90"), locked_crop("target_bloom", cost=None)]
        patches, _ = heritage_pricing.plan(records, served={})
        self.assertEqual(set(patches), {3})
        self.assertEqual(patches[3], {"group": "locked", "market": None, "cash": None, "coins": "90",
                                      "source": "sibling:2"})

    def test_crop_tier_uses_lower_median_of_home_crops_in_its_subtype(self):
        records = [crop("h10", cost="10", growTime="1"), crop("h30", cost="30", growTime="1"),
                   crop("h50", cost="50", growTime="1"), locked_crop("target_bloom", cost=None, growTime="0.5")]
        patches, _ = heritage_pricing.plan(records, served={})
        self.assertEqual((patches[3]["coins"], patches[3]["source"]), ("30", "tier:subtype"))

    def test_crop_without_any_price_basis_is_refused(self):
        patches, report = heritage_pricing.plan([locked_crop("lonely", cost=None)], served={})
        self.assertEqual(patches, {})
        self.assertEqual(report["excluded"], {"locked": {"crop: no price basis": 1}})
        self.assertEqual(report["refused"], {0: "crop: no price basis"})

    def test_each_crop_exclusion_names_its_reason_and_is_refused(self):
        cases = [
            ("crop: licence", {"license": "true"}),
            ("crop: purchase prerequisite", {"purchasePrereqs": "quest_x"}),
            ("crop: market prerequisite", {"marketPrereqs": "marketHidden"}),
            ("crop: experiment prerequisite", {"experiment": "fv_x"}),
            ("crop: geo gate", {"geoip": "US"}),
            ("crop: unlock or donation", {"unlockCost": "5"}),
            ("crop: harvest yield in world currency or score",
             {"harvestYield": {"className": "CurrencyHarvestYield", "type": "jade", "yield": "38"}}),
            ("crop: harvest item drop", {"harvestItem": "nachos_plate"}),
            ("crop: produce item", {"producesItem": "true"}),
            ("crop: organic certification", {"organic": "true"}),
            ("crop: hybrid breeding", {"isHybrid": "true"}),
            ("crop: weather modifier", {"weatherData": {"weather": []}}),
            ("crop: present gift", {"present": "true"}),
            ("crop: seed package", {"seedpackage": "bloom_seedpackage"}),
            ("crop: non-land terrain", {"terrainSet": {"terrain": {"name": "water"}}}),
            ("crop: experiment closed", {"experimentGate": "fv_unserved"}),
            ("crop: experiment closed", {"experimentGate": "fv_avalon", "experimentVariant": "2"}),
            ("crop: no market entry", {"marketEntries": None}),
            ("crop: level requirement", {"requiredLevel": ["1", "15"]}),
            ("crop: reward value", {"coinYield": "lots"}),
            ("crop: grow time invalid", {"growTime": "0"}),
            ("crop: special requirement", {"requirements": {"compare": "all", "requirement": [
                {"name": "avalon", "className": "World"}, {"name": "superCrop", "className": "SuperCrop"}]}}),
            ("reserved world", {"requirements": {"compare": "any", "requirement": {
                "name": "rainforest", "className": "World"}}}),
        ]
        for reason, fields in cases:
            with self.subTest(reason=reason, fields=fields):
                patches, report = heritage_pricing.plan([locked_crop("blocked", **fields)], served={"fv_avalon": 1})
                self.assertEqual(patches, {})
                self.assertEqual(report["excluded"], {"locked": {reason: 1}})
                self.assertEqual(report["refused"], {0: reason})

    def test_crop_gate_open_only_when_served_and_its_variant_matches(self):
        for fields, expected in (({"experimentGate": "fv_avalon", "experimentVariant": "2,3"}, 1),
                                 ({"experimentGate": "fv_avalon", "experimentVariant": "3"}, 0)):
            with self.subTest(fields=fields):
                patches, _ = heritage_pricing.plan([locked_crop("gated", **fields)], served={"fv_avalon": 2})
                self.assertEqual(len(patches), expected)

    def test_a_locked_crop_excluded_by_the_overlay_names_its_reason_on_the_server_copy(self):
        records = [locked_crop("terrainbloom", terrainSet={"terrain": {"name": "water"}}), locked_crop("kept")]
        working = copy.deepcopy(records)
        heritage_pricing.apply(working, server=True)
        self.assertEqual(heritage_pricing.crop_refusal(working[0]),
                         "This crop is not sold on the Home Farm (crop: non-land terrain).")
        self.assertIsNone(heritage_pricing.crop_refusal(working[1]))
        self.assertIsNone(heritage_pricing.crop_refusal(item("decor")))


class HeritageServerTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    def setUp(self):
        fixtures.RuntimeFixtureTests.setUp(self)
        import items
        self.items = items
        self.overlaid = [entry for entry in items.get_items() if heritage_pricing.is_overlaid(entry)]

    def prepare(self, *, cash=1000):
        from game_settings import level_to_xp
        self.path = self.write_fixture()
        save = self.player.session("fixture-farmer")
        save["userInfo"]["player"].update(xp=level_to_xp(100), cash=cash, gold=1000000)
        self.save = save
        return save

    def exclusive_decoration(self):
        for entry in self.overlaid:
            if entry.get("className") is None and entry.get("type") == "decoration" and entry.get("requirements") is None \
                    and entry.get("sizeX") == "1" and entry.get("sizeY") == "1":
                return entry
        self.fail("no overlaid one-square decoration in the recovered catalog")

    def admitted_crop(self):
        for entry in self.overlaid:
            if (entry.get("type") == "seed" and entry.get("mastery") == "true" and entry.get("masteryLevel")
                    and int(entry.get("masteryYield") or 0) >= 1 and float(entry["growTime"]) <= 0.02):
                return entry
        self.fail("no admitted quick crop with a mastery ladder in the recovered catalog")

    def crop_action(self, action, snapshot, options=(), *, now=NOW):
        return self.crop_send("WorldService.performAction", [action, snapshot, list(options)], now=now)

    def crop_send(self, name, params, *, now=NOW):
        with mock.patch("commands.timestamp_now", return_value=now), mock.patch("engine.timestamp_now", return_value=now):
            response = self.gateway([self.command(name, params)])
        fixtures.assert_gateway_status(self, response, 200)
        from pyamf import remoting
        return remoting.decode(response.data).bodies[0][1].body["data"][0]["data"]

    def crop_refusal_text(self, name, params, *, now=NOW):
        """Refuse one command and return its message, with the save and the disk unchanged."""
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")
        before = copy.deepcopy(self.player.session("fixture-farmer"))
        disk = self.path.read_bytes()
        with mock.patch("commands.timestamp_now", return_value=now), mock.patch("engine.timestamp_now", return_value=now):
            response = self.gateway([self.command(name, params)])
        results = fixtures.gateway_results(self, response, errors=[29])
        self.assertEqual(self.player.session("fixture-farmer"), before)
        self.assertEqual(self.path.read_bytes(), disk)
        return results[0]["errorData"]

    def test_recovered_catalog_overlay_is_exactly_the_planned_set(self):
        self.assertEqual(len(self.overlaid), 4721)
        classes = {(entry.get("type"), entry.get("className")) for entry in self.overlaid}
        self.assertLessEqual(classes, heritage_pricing.ORDINARY_CLASSES)

    def test_recovered_crops_admit_948_at_their_own_coin_price_and_refuse_the_rest_with_reasons(self):
        import collections
        import json
        import items
        crops = [entry for entry in self.overlaid if entry.get("type") == "seed"]
        self.assertEqual(len(crops), 948)
        recovered = {(row["name"], row["code"]): row for row in
                     json.loads(Path(items.CACHE_ITEMS_JSON).read_text())["data"]["settings"]["items"]["item"]
                     if row.get("type") == "seed"}
        for entry in crops:
            with self.subTest(name=entry["name"]):
                self.assertEqual(entry["cost"], recovered[(entry["name"], entry["code"])]["cost"])
                self.assertNotIn("market", entry)
        refused = collections.Counter(heritage_pricing._refused.values())
        self.assertEqual(sum(refused.values()), 1009)
        self.assertEqual(refused, collections.Counter({
            "crop: non-land terrain": 271, "reserved world": 331, "crop: purchase prerequisite": 225,
            "crop: market prerequisite": 77, "crop: special requirement": 54, "world currency": 23,
            "crop: experiment closed": 22,
            "crop: no market entry": 4, "crop: experiment prerequisite": 1, "crop: produce item": 1}))

    def test_admitted_foreign_crop_is_bought_planted_and_harvested_on_home(self):
        import math
        import creative_worlds
        import engine
        import peaceful
        from game_settings import get_farming_int
        crop_item = self.admitted_crop()
        code = crop_item["code"]
        self.prepare(cash=0)
        player = self.player.session("fixture-farmer")["userInfo"]["player"]
        before = {"gold": player["gold"], "xp": player["xp"]}
        mastery_before = player["masteryCounters"].get(code, 0)
        plow_cost = get_farming_int("plowCost", 15)
        plot = {"id": 64001, "className": "Plot", "itemName": None, "state": "plowed",
                "position": {"x": 4, "y": 4, "z": 0}, "plantTime": 0}
        ident = self.crop_action("plow", plot)["id"]
        planted = dict(plot, id=ident, itemName=crop_item["name"], state="planted", plantTime=1)
        self.crop_action("place", planted, [{"currency": "coins"}])

        player = self.player.session("fixture-farmer")["userInfo"]["player"]
        cost = engine.catalog_price(crop_item, "cost")
        self.assertEqual(player["gold"], before["gold"] - plow_cost - cost)
        self.assertEqual(player["xp"], before["xp"] + 1 + int(crop_item["plantXp"]))
        crop_object = next(obj for obj in self.player.session("fixture-farmer")["world"]["objectsArray"]
                           if obj["id"] == ident)
        self.assertEqual((crop_object["itemName"], crop_object["state"], crop_object["plantTime"]),
                         (crop_item["name"], "planted", NOW * 1000))

        gold = player["gold"]
        ready = NOW + math.ceil(peaceful.grow_seconds(crop_item))
        self.crop_action("harvest", dict(crop_object, state="fallow", plantTime=1), now=ready)
        player = self.player.session("fixture-farmer")["userInfo"]["player"]
        self.assertEqual(player["gold"], gold + int(crop_item["coinYield"]))
        self.assertEqual(player["masteryCounters"][code], mastery_before + min(5, int(crop_item["masteryYield"])))
        self.assertTrue(creative_worlds.world_requirement_matches(crop_item, "farm"))

    def test_excluded_foreign_crop_is_refused_on_home_with_its_reason(self):
        import creative_worlds
        excluded = next(entry for entry in self.items.get_items() if entry.get("type") == "seed"
                        and heritage_pricing.crop_refusal(entry) is not None
                        and "non-land terrain" in heritage_pricing.crop_refusal(entry))
        message = heritage_pricing.crop_refusal(excluded)
        self.assertEqual(message, "This crop is not sold on the Home Farm (crop: non-land terrain).")
        self.prepare(cash=0)
        plot = {"id": 64001, "className": "Plot", "itemName": None, "state": "plowed",
                "position": {"x": 4, "y": 4, "z": 0}, "plantTime": 0}
        ident = self.crop_action("plow", plot)["id"]
        planted = dict(plot, id=ident, itemName=excluded["name"], state="planted", plantTime=1)
        gold = self.player.session("fixture-farmer")["userInfo"]["player"]["gold"]
        self.assertEqual(self.crop_refusal_text("WorldService.performAction", ["place", planted, [{"currency": "coins"}]]),
                         message)
        save = self.player.session("fixture-farmer")
        with self.assertRaisesRegex(ValueError, "non-land terrain"):
            creative_worlds.guard_market_purchase(save, excluded, "coins", neighbor_count=0)
        self.assertEqual(save["userInfo"]["player"]["gold"], gold)

    def test_overlaid_items_are_buyable_home_items_with_a_farm_cash_price(self):
        import items
        for entry in self.overlaid[:200]:
            with self.subTest(name=entry["name"]):
                self.assertEqual(entry["buyable"], "true")
                self.assertEqual(entry["archived"], "no")
                self.assertNotIn("limitedEnd", entry)
                if entry.get("market") == "cash":
                    self.assertGreater(int(entry["cash"]), 0)
                self.assertIs(items.get_item_by_name(entry["name"]), entry)

    def test_home_purchase_charges_the_derived_farm_cash_price(self):
        from engine import catalog_price
        import creative_worlds
        import engine
        entry = self.exclusive_decoration()
        price = catalog_price(entry, "cash")
        self.assertIsNotNone(price)
        save = self.prepare(cash=price)
        creative_worlds.guard_market_purchase(save, entry, "cash", neighbor_count=0)
        engine.apply_item_cost(save, entry, currency="cash")
        self.assertEqual(save["userInfo"]["player"]["cash"], 0)
        save = self.prepare(cash=price - 1)
        with self.assertRaisesRegex(ValueError, "Not enough"):
            creative_worlds.guard_market_purchase(save, entry, "cash", neighbor_count=0)

    def test_place_action_charges_the_derived_price_once_and_places_the_item(self):
        entry = self.exclusive_decoration()
        from engine import catalog_price
        price = catalog_price(entry, "cash")
        save = self.prepare(cash=price + 5)
        snapshot = {"id": 64001, "className": "Decoration", "itemName": entry["name"], "state": "static",
                    "position": {"x": 6, "y": 6, "z": 0}}
        with mock.patch("server.timestamp_now", return_value=NOW), mock.patch(
                "commands.timestamp_now", return_value=NOW), mock.patch("engine.timestamp_now", return_value=NOW):
            with redirect_stdout(io.StringIO()):
                response = self.gateway([self.command("WorldService.performAction", ["place", snapshot, [{"currency": "cash"}]])])
        fixtures.assert_gateway_status(self, response, 200)
        self.assertEqual(save["userInfo"]["player"]["cash"], 5)
        self.assertEqual([obj["itemName"] for obj in save["world"]["objectsArray"] if obj.get("itemName") == entry["name"]],
                         [entry["name"]])

    def test_england_refuses_a_home_only_overlaid_item(self):
        import creative_worlds
        import world_travel
        entry = self.exclusive_decoration()
        save = self.prepare(cash=10000)
        with mock.patch.object(world_travel, "guard_active_world", return_value="england"):
            with self.assertRaisesRegex(ValueError, "not sold on this farm"):
                creative_worlds.guard_market_purchase(save, entry, "cash", neighbor_count=0)
        self.assertEqual(save["userInfo"]["player"]["cash"], 10000)

    def test_meadows_non_strict_home_alias_cannot_admit_a_rehomed_locked_item(self):
        import creative_worlds
        locked = [entry for entry in self.overlaid if entry.get("requirements")]
        self.assertTrue(locked)
        for entry in locked[:50]:
            with self.subTest(name=entry["name"]):
                self.assertTrue(creative_worlds.world_requirement_matches(entry, "farm"))
                self.assertFalse(creative_worlds.world_requirement_matches(entry, creative_worlds.WORLD))

    def test_served_market_agrees_with_the_server_copy(self):
        from client_catalog import payload
        from pyamf import remoting  # noqa: F401  Imported for the AMF decoder used by payload.
        import items
        import zlib
        import pyamf
        entry = self.exclusive_decoration()
        served = pyamf.get_decoder(pyamf.AMF3, zlib.decompress(payload(items.ITEMS_AMF, now=NOW))).readElement()
        row = next(row for row in served["settings"]["items"]["item"] if row["name"] == entry["name"])
        self.assertEqual((row["buyable"], row["market"], row["cash"]), ("true", "cash", entry["cash"]))
        self.assertNotIn("limitedEnd", row)


if __name__ == "__main__":
    unittest.main()
