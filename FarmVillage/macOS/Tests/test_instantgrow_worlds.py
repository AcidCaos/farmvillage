"""Original airplane Instant Grow packets; real catalogs, disposable AMF saves."""
import copy
from contextlib import redirect_stdout
import io
import math
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures  # Must precede every bundle-dependent import.
import test_cove_cellar as cellar_fixtures
import instant_growth
import creative_worlds
import peaceful
import themed_worlds
import world_travel
from game_settings import get_farming_int
from items import get_item_by_name

NOW = 1800000000
WORLDS = ("farm", "england", "meadows", "fisherman")


class InstantGrowWorldTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway
    save = cellar_fixtures.CoveCellarTests.save
    prepare = cellar_fixtures.CoveCellarTests.prepare
    persist = cellar_fixtures.CoveCellarTests.persist

    @staticmethod
    def plane(**changes):
        return dict({"tempId": -1, "position": {"x": 33, "z": 0, "y": 66},
            "state": "static", "instanceDataStoreKey": None, "m_equipmentPartsCount": 0,
            "id": 63000, "deleted": False, "components": {}, "direction": 0,
            "itemName": "biplanered", "className": "Airplane"}, **changes)

    @staticmethod
    def resource(ident=626, *, name="blackberriesdarrow", cls="Plot", state="planted", **changes):
        return dict({"id": ident, "className": cls, "itemName": name, "state": state,
            "position": {"x": 4, "y": 4, "z": 0}, "plantTime": NOW * 1000,
            "importedMetadata": {"preserve": True}}, **changes)

    def prepare_grow(self, world="fisherman"):
        self.prepare(world)
        self.save["world"]["objectsArray"] = [self.resource(
            name="blackberriesdarrow" if world == "fisherman" else "strawberry")]
        self.save["userInfo"]["player"]["cash"] = 594
        self.persist()

    def request(self, *, kind=1, sequence=11, plane=None, options=None):
        packet = {"aoeSources": {}, "type": kind, "autoHarvest": {"autoPPH": False}}
        if options:
            packet.update(options)
        # Match the real failing Ruffle packet's integer-key options Array.
        return self.command("WorldService.performAction", ["instantGrow", plane or self.plane(), {0: packet}], sequence)

    def send(self, request=None, *, expected=200):
        with mock.patch("commands.timestamp_now", return_value=NOW), mock.patch("server.timestamp_now", return_value=NOW):
            response = self.gateway([request or self.request()])
        fixtures.assert_gateway_status(self, response, expected)
        if expected == 200:
            from pyamf import remoting
            return remoting.decode(response.data).bodies[0][1].body["data"][0]

    def reject(self, request):
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.send(request, expected=400)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)

    def test_original_four_cash_packet_shared_by_all_worlds_without_plane_placement(self):
        for world in WORLDS:
            with self.subTest(world=world):
                self.prepare_grow(world)
                before = copy.deepcopy(self.save)
                response = self.send()
                self.assertEqual((response["id"], response["data"]["id"]), (63000, 63000))
                self.assertEqual(self.save["userInfo"]["player"]["cash"], 590)
                crop = self.save["world"]["objectsArray"][0]
                self.assertEqual(crop["state"], "grown")
                self.assertGreaterEqual(NOW - crop["plantTime"] / 1000,
                                        peaceful.grow_seconds(get_item_by_name(crop["itemName"])))
                self.assertEqual(len(self.save["world"]["objectsArray"]), 1)
                self.assertEqual(crop["id"], 626)
                self.assertEqual(crop["importedMetadata"], {"preserve": True})
                self.assertEqual(self.save["userInfo"]["player"]["storageData"], before["userInfo"]["player"]["storageData"])
                self.assertEqual(self.save.get(world_travel.STATE_KEY), before.get(world_travel.STATE_KEY))
                once = copy.deepcopy(self.save)
                self.send()  # Same transport sequence, same payment exactly once.
                self.assertEqual(self.save, once)
                with redirect_stdout(io.StringIO()):
                    self.player.load_saves()
                self.send()
                self.assertEqual(self.save, once)

    def test_ordinary_category_selection_and_combined_price(self):
        for world in WORLDS:
            with self.subTest(world=world):
                self.prepare_grow(world)
                self.save["world"]["objectsArray"].extend([
                    self.resource(627, name="apple", cls="Tree", state="bare"),
                    self.resource(628, name="cow", cls="Animal", state="bare")])
                self.persist()
                self.send(self.request(kind=2))
                self.assertEqual(self.save["userInfo"]["player"]["cash"], 591)
                self.assertEqual([o["state"] for o in self.save["world"]["objectsArray"]], ["planted", "ripe", "bare"])
                self.send(self.request(kind=7, sequence=12))
                self.assertEqual(self.save["userInfo"]["player"]["cash"], 584)
                self.assertEqual([o["state"] for o in self.save["world"]["objectsArray"]], ["grown", "ripe", "ripe"])

    def test_ready_empty_and_unselected_crops_never_cost_cash_or_reset_timers(self):
        for state in ("grown", "plowed", "fallow", "withered"):
            with self.subTest(state=state):
                self.prepare_grow()
                self.save["world"]["objectsArray"][0]["state"] = state
                self.persist()
                before = copy.deepcopy(self.save["world"])
                self.send()
                self.assertEqual(self.save["world"], before)
                self.assertEqual(self.save["userInfo"]["player"]["cash"], 594)

    def test_payment_failure_and_unsupported_options_preserve_each_world(self):
        for world in WORLDS:
            with self.subTest(world=world):
                self.prepare_grow(world)
                self.save["userInfo"]["player"]["cash"] = 3
                self.persist()
                self.reject(self.request())
                self.save["userInfo"]["player"]["cash"] = 594
                self.persist()
                for options in ({"autoHarvest": {"autoPPH": True}}, {"autoHarvest": {"autoTH": True}},
                        {"aoeSources": {"forged": 1}}, {"type": 8}, {"type": True},
                        {"worldType": "hawaii"}, {"price": 0}):
                    self.reject(self.request(options=options))

    def test_forged_identity_timer_and_request_reuse_preserve_save(self):
        self.prepare_grow()
        for plane in (self.plane(className="Plot"), self.plane(itemName="cow"),
                      self.plane(id=626), self.plane(id=4), self.plane(deleted=True)):
            self.reject(self.request(plane=plane))
        for value in (None, True, -1, (NOW + 100) * 1000):
            self.save["world"]["objectsArray"][0]["plantTime"] = value
            self.persist()
            self.reject(self.request())
        self.save["world"]["objectsArray"][0]["plantTime"] = NOW * 1000
        self.persist()
        self.send()
        self.reject(self.request(kind=2))

    def test_world_specific_temporary_airplane_only_in_its_own_world(self):
        # Browser 2026-10-23: Rainforest's client flies 'xrfbiplane' (temp id 63001).
        world_save = lambda world: {"userInfo": {"currentWorldType": world}}
        allowed = instant_growth._temporary_airplane_allowed
        self.assertTrue(allowed(world_save("rainforest"), get_item_by_name("xrfbiplane")))
        self.assertTrue(allowed(world_save("rainforest"), get_item_by_name("biplanered")))
        self.assertFalse(allowed(world_save("farm"), get_item_by_name("xrfbiplane")))
        self.assertFalse(allowed(world_save("rainforest"),
                                 get_item_by_name("xmd_michelangelosornithopter")))
        self.assertFalse(allowed(world_save("farm"), get_item_by_name("biplaneavg")))
        self.prepare_grow()
        self.reject(self.request(plane=self.plane(itemName="xrfbiplane", id=63001)))

    def test_original_themed_airplanes_grow_once_and_reject_cross_world_carriers(self):
        # worldSettings.xml hudSkinConfig.instantGrowItemVisual is what the
        # original client actually flies; Candy uses candybiplane, not xcwbiplane.
        originals = {
            "rainforest": ("xrfbiplane", "xrf_jungleblackberry"),
            "mediterranean": ("xmd_michelangelosornithopter", "xmd_sanmarzanotomato"),
            "storybook": ("xsb_fairylandbiplane", "xsb_whitesquills"),
            "candy": ("candybiplane", "sprinklestrawberry"),
            "oasis": ("xoa_egyptianeaglebiplane", "xoa_cherimoya"),
            "oz": ("xoz_emeraldbiplane", "xoz_bittybluetomatoes"),
            "toyland": ("xtl_toylandsbiplane", "xtl_appleinabox"),
            "sleepyhollow": ("xsh_huntsmanshollowbiplane", "xsh_autumncabbage"),
            "australia": ("biplanered", "australianalbinopineapple"),
            "fforest": ("xffbiplane", "aslantcarrot"),
            "htown": ("biplanered", "ciderapple"),
        }
        archived = instant_growth.cove_rules._xml("worldSettings.xml.gz")
        with mock.patch.object(themed_worlds, "ACTIVE_WORLDS", frozenset(originals)):
            for world, (plane_name, seed) in originals.items():
                with self.subTest(world=world):
                    visual = archived.find("world[@name='%s']/hudSkinConfig/instantGrowItemVisual" % world)
                    self.assertEqual(visual.get("name") if visual is not None else "biplanered", plane_name)
                    self.prepare("farm")
                    creative_worlds.create(self.save, world, "allAccess", now=NOW)
                    world_travel.switch(self.save, world, False, now=NOW)
                    self.save["world"]["objectsArray"] = [self.resource(name=seed)]
                    self.save["userInfo"]["player"]["cash"] = 594
                    self.persist()
                    for other_world, (foreign_plane, _) in originals.items():
                        if other_world != world and foreign_plane != "biplanered":
                            with self.subTest(foreign_world=other_world):
                                self.reject(self.request(plane=self.plane(itemName=foreign_plane, id=63001)))
                    request = self.request(plane=self.plane(itemName=plane_name, id=63001))
                    self.send(request)
                    self.assertEqual(self.save["userInfo"]["player"]["cash"], 590)
                    self.assertEqual(self.save["world"]["objectsArray"][0]["state"], "grown")
                    self.assertEqual(len(self.save["world"]["objectsArray"]), 1)
                    once = copy.deepcopy(self.save)
                    self.send(request)
                    self.assertEqual(self.save, once)
                    with redirect_stdout(io.StringIO()):
                        self.player.load_saves()
                    self.send(request)
                    self.assertEqual(self.save, once)

    def test_candy_visual_exception_does_not_bypass_catalog_licences(self):
        candy = {"userInfo": {"currentWorldType": "candy"}}
        plane = get_item_by_name("candybiplane")
        self.assertTrue(instant_growth._temporary_airplane_allowed(candy, plane))
        for changes in (
                {"requirements": {"requirement": {"className": "WorldLicense", "name": "candy"}}},
                {"experimentGate": "fv_space"},
                {"name": "chromeplane"}):
            with self.subTest(changes=changes):
                self.assertFalse(instant_growth._temporary_airplane_allowed(candy, {**plane, **changes}))

    def test_first_world_action_marker_is_accepted_and_nothing_else(self):
        # Browser 2026-10-23: Instant Grow as the first action after load sends
        # {0: options, 1: {'firstWA': True}}.
        options = {"aoeSources": {}, "type": 1, "autoHarvest": {"autoPPH": False}}
        self.assertEqual(instant_growth._options({0: options, 1: {"firstWA": True}}), (options, 1))
        self.assertEqual(instant_growth._options([options, {"firstWA": True}]), (options, 1))
        for extra in ({"firstWA": False}, {"firstWA": True, "x": 1}, {}, options):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                instant_growth._options({0: options, 1: extra})

    def test_second_batch_rejection_keeps_paid_growth_and_free_retry(self):
        self.prepare_grow()
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        with mock.patch("commands.timestamp_now", return_value=NOW):
            response = self.gateway([self.request(), self.request(kind=2)])
        fixtures.gateway_results(self, response, [0, 29])
        self.assertEqual(self.save['userInfo']['player']['cash'], before['userInfo']['player']['cash'] - 4)
        self.assertEqual(self.save['world']['objectsArray'][0]['state'], 'grown')
        after = self.path.read_bytes()
        self.send()
        self.assertEqual(self.path.read_bytes(), after)

    def test_new_sequence_after_replant_is_a_new_paid_growth(self):
        self.prepare_grow()
        self.send()
        self.save["world"]["objectsArray"][0].update(state="planted", plantTime=NOW * 1000)
        self.persist()
        self.send()  # The old sequence must not touch this new crop cycle.
        self.assertEqual(self.save["world"]["objectsArray"][0]["state"], "planted")
        self.assertEqual(self.save["userInfo"]["player"]["cash"], 590)
        self.send(self.request(sequence=12))
        self.assertEqual(self.save["userInfo"]["player"]["cash"], 586)
        self.assertEqual(self.save["world"]["objectsArray"][0]["state"], "grown")

    def test_owned_airplane_original_nan_temporary_field_does_not_break_payment_or_retry(self):
        self.prepare_grow("farm")
        saved_plane = self.plane(id=627, tempId=None)
        saved_plane["position"] = {"x": 12, "y": 12, "z": 0}
        self.save["world"]["objectsArray"].append(copy.deepcopy(saved_plane))
        self.persist()
        request = self.request(plane=dict(saved_plane, tempId=float("nan")))
        self.send(request)
        self.assertEqual(self.save["userInfo"]["player"]["cash"], 590)
        self.assertEqual(self.save["world"]["objectsArray"][1], saved_plane)
        once = copy.deepcopy(self.save)
        self.send(request)
        self.assertEqual(self.save, once)

    def test_category_prices_match_recovered_instagrow_helper_formulas(self):
        # InstagrowHelper.getPlotsPrice = max(4, 1 + h*0.002), getTreesPrice = max(3, h*0.002),
        # getPriceAnimal = min(18, max(3, h*0.0015)); calculateCost floors each category.
        prices = instant_growth.CATEGORY_PRICES
        self.assertEqual((prices[1](0), prices[1](2000)), (4, 5))
        self.assertEqual((prices[2](100), prices[2](2000)), (3, 4))
        self.assertEqual((prices[4](100), prices[4](3000), prices[4](20000)), (3, 4.5, 18))

    def test_animal_total_price_uses_recovered_rate_across_many_cows(self):
        grow = peaceful.grow_seconds(get_item_by_name("cow"))
        hour = get_farming_int("inGameDaySeconds", 82800) / 24
        count = round(3000 * hour / grow)  # About 3000 in-game hours: 0.0015 floors to 4, 0.00175 to 5.
        cows = [self.resource(1000 + index, name="cow", cls="Animal", state="bare") for index in range(count)]
        save = {"userInfo": {"currentWorldType": "farm"}, "world": {"objectsArray": cows}}
        targets, price = instant_growth._targets(save, 4, NOW)
        total = count * grow / hour
        self.assertEqual(len(targets), count)
        self.assertTrue(2880 <= total <= 3120, total)
        self.assertEqual(price, 4)
        self.assertEqual(price, math.floor(min(18, max(3, total * .0015))))

    def test_harvest_replant_and_container_variants_refuse_before_payment(self):
        # Refused by instant_growth._options with the recovered reasons; a refused packet never charges or matures.
        self.prepare_grow("farm")
        self.save["world"]["objectsArray"].extend([
            self.resource(627, name="apple", cls="Tree", state="bare"),
            self.resource(628, name="cow", cls="Animal", state="bare")])
        self.persist()
        for kind, options in (
                (1, {"autoHarvest": {"autoPPH": True}}),
                (1, {"autoHarvest": {"autoPPH": True, "autoTH": True}}),
                (2, {"autoHarvest": {"autoPPH": True}}),
                (2, {"autoHarvest": {"autoTH": True}}),
                (4, {"autoHarvest": {"autoAH": True}}),
                (8, {"autoHarvest": {"autoBH": True}}),
                (8, {})):
            with self.subTest(kind=kind, options=options):
                self.reject(self.request(kind=kind, options=options))
        self.send()  # The refused sequence number did not consume the retry history.
        self.assertEqual(self.save["userInfo"]["player"]["cash"], 590)


if __name__ == "__main__":
    unittest.main()
