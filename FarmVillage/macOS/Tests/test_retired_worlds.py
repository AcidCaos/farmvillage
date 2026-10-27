"""Clean-start release admits sixteen worlds and never offers retired ones."""
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import re
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import creative_worlds
from game_settings import level_to_xp
import themed_worlds as tw
import world_travel

RETIRED = {"glen", "hlights"}
NOW = 1800000000


class CleanReleaseWorldTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    def fresh(self):
        self.assertEqual(list(self.saves.iterdir()), [])
        with redirect_stdout(io.StringIO()):
            response = self.client.post("/new.html", data={"name": "Clean Release QA", "preset": "classic"})
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            self.uid = session["UID"]
        self.path = self.saves / (self.uid + ".save.json")
        self.assertTrue(self.path.is_file())
        self.assertEqual(list(self.saves.glob("*.json")), [self.path])
        return self.player.session(self.uid)

    def prepare(self):
        self.save = self.fresh()
        # Clearly synthetic test funding; never an earned gameplay reward.
        self.save["userInfo"]["player"].update(xp=level_to_xp(15), gold=500000, cash=1000)
        with redirect_stdout(io.StringIO()):
            self.player.save_session(self.uid)
        response = self.client.get("/farms")
        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as session:
            self.token = session["farms_token"]
        return response.get_data(as_text=True)

    def post(self, action, world):
        with redirect_stdout(io.StringIO()):
            return self.client.post("/farms", data={"token": self.token, "action": action,
                                                    "world": world, "option": "allAccess"})

    def test_active_release_has_sixteen_worlds_and_no_retired_creation_or_travel_offer(self):
        self.assertEqual(len(world_travel.supported_worlds()), 16)
        self.assertEqual(len(tw.active_worlds()), 12)
        self.assertFalse(RETIRED & world_travel.supported_worlds().keys())
        self.assertTrue(RETIRED <= tw.SPECS.keys())  # Dormant source remains archived.
        page = self.prepare()
        self.assertNotRegex(page, r'name="world" value="(?:glen|hlights)"')
        self.assertFalse(RETIRED & {row["worldType"] for row in creative_worlds.candidates(self.save)})
        self.assertEqual(self.save["userInfo"]["currentWorldType"], "farm")
        self.assertFalse(RETIRED & set(self.save["userInfo"].get("unlockedWorldTypes", [])))

    def test_both_fresh_player_routes_disable_retired_access_and_invitation_flags(self):
        self.prepare()
        before = self.path.read_bytes()
        for route in ("/play.html", "/ruffle.html"):
            with self.subTest(route=route), mock.patch.object(self.server, "NATIVE_WRAPPER", False):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                flags = dict(re.findall(r'"(fv_[A-Za-z0-9_]+)"\s*:\s*(-?\d+)', response.get_data(as_text=True)))
                for gate in ("fv_glen", "fv_glen_for_all", "fv_hlights", "fv_hlights_for_all",
                             "fv_xeg_starter", "fv_xlg_starter", "fv_xlg_motd_generalaccess"):
                    self.assertEqual(flags[gate], "0", gate)
        self.assertEqual(self.path.read_bytes(), before)

    def test_retired_unlocks_and_visits_refuse_for_a_fresh_farm_without_charges(self):
        self.prepare()
        before = self.path.read_bytes()
        balances = copy.deepcopy(self.save["userInfo"]["player"])
        for world in sorted(RETIRED):
            for action in ("purchase", "visit"):
                with self.subTest(world=world, action=action):
                    response = self.post(action, world)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn('role="alert"', response.get_data(as_text=True))
                    self.assertEqual(self.path.read_bytes(), before)
            response = self.gateway([self.command("WorldService.loadOwnWorld", [world], 100)], uid=self.uid)
            fixtures.assert_gateway_rejected(self, response)
            self.assertEqual(self.path.read_bytes(), before)
            with self.assertRaises(ValueError):
                creative_worlds.create(self.save, world, "allAccess", now=NOW)
            self.assertEqual(self.save["userInfo"]["player"], balances)

    def test_fresh_sixteen_world_ownership_persists_after_save_registry_reload(self):
        self.prepare()
        world_travel.unlock_england(self.save, "allAccess", now=NOW)
        for world in sorted(world_travel.supported_worlds()):
            if world in {"farm", "england"}:
                continue
            creative_worlds.create(self.save, world, "cash60" if world == "meadows" else "allAccess", now=NOW)
        worlds = {self.save["userInfo"]["currentWorldType"], *self.save[world_travel.STATE_KEY]["inactive"]}
        self.assertEqual(worlds, set(world_travel.supported_worlds()))
        self.assertFalse(RETIRED & worlds)
        with redirect_stdout(io.StringIO()):
            self.player.save_session(self.uid)
        saved = json.loads(self.path.read_text())
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.player.session(self.uid), saved)
        self.assertEqual(self.player.all_saves_uids(), [self.uid])
        self.assertFalse(RETIRED & self.player.session(self.uid)[world_travel.STATE_KEY]["inactive"].keys())


if __name__ == "__main__":
    unittest.main()
