"""October presentation responses follow only the selected disposable village.

These Flask checks use bundled source XML and synthetic profiles. No server
socket, artwork, real saves or external service is involved.
"""
import copy
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures  # Own data roots before every product import.
import october_presentation
import october_village
import themed_market_presentation


class OctoberPresentationRouteTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture

    def setUp(self):
        fixtures.RuntimeFixtureTests.setUp(self)
        self.source = Path(self.server.XML_DIR) / "gz/v855098/worldSettings.xml.gz"
        self.original = self.source.read_bytes()
        self.basic_worlds = themed_market_presentation.world_settings_payload(self.original)

    def select(self, uid):
        with self.client.session_transaction() as selected:
            if uid is None:
                selected.pop("UID", None)
            else:
                selected["UID"] = uid

    def mark_october(self, uid="fixture-farmer"):
        village = self.player.session(uid)
        village[october_village.STATE_KEY] = {
            "preset": october_village.PRESET, "version": 1,
            "privateEvidence": {"retain": ["authored", "borrowed"]}}
        with redirect_stdout(io.StringIO()):
            self.player.save_session(uid)
        return village

    def response(self, *, active=False):
        before = {uid: copy.deepcopy(self.player.session(uid))
                  for uid in self.player.all_saves_uids()}
        disk = {str(path.relative_to(self.saves)): path.read_bytes()
                for path in self.saves.rglob("*") if path.is_file()}
        response = self.client.get("/xml/gz/v855098/worldSettings.xml.gz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/xml")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertIn("Cookie", response.vary)
        october = october_presentation.world_settings_payload(self.original, active=active)
        self.assertEqual(response.data, themed_market_presentation.world_settings_payload(october))
        # The independent basic-world projection leaves Home exactly as the
        # selected profile's October/classic projection authored it.
        served = ET.fromstring(zlib.decompress(response.data))
        expected_home = ET.fromstring(zlib.decompress(october)).find("world[@name='farm']")
        self.assertEqual(ET.tostring(served.find("world[@name='farm']")), ET.tostring(expected_home))
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual({uid: self.player.session(uid)
                          for uid in self.player.all_saves_uids()}, before)
        self.assertEqual({str(path.relative_to(self.saves)): path.read_bytes()
                          for path in self.saves.rglob("*") if path.is_file()}, disk)
        return response

    def test_no_selected_village_keeps_classic_home_and_private_cache_headers(self):
        self.response()

    def test_classic_village_keeps_classic_home_and_save(self):
        self.write_fixture()
        self.select("fixture-farmer")
        self.response()

    def test_october_home_gets_borrowed_hud_without_publishing_or_mutating_marker(self):
        self.write_fixture()
        village = self.mark_october()
        self.select("fixture-farmer")
        response = self.response(active=True)
        root = ET.fromstring(zlib.decompress(response.data))
        self.assertEqual(root.find("world[@name='farm']/hudSkinConfig/hudAssets").get("path"),
                         october_presentation.HUD_ASSET_PATH)
        self.assertNotIn(october_village.STATE_KEY.encode(), zlib.decompress(response.data))
        self.assertEqual(village[october_village.STATE_KEY]["privateEvidence"],
                         {"retain": ["authored", "borrowed"]})

    def test_october_loading_in_another_world_keeps_home_skin_for_return_trip(self):
        self.write_fixture()
        village = self.mark_october()
        village["userInfo"]["currentWorldType"] = "canada"
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")
        self.select("fixture-farmer")
        response = self.response(active=True)
        projected = ET.fromstring(zlib.decompress(response.data))
        original = ET.fromstring(zlib.decompress(self.basic_worlds))
        for world in original:
            if world.get("name") != "farm":
                self.assertEqual(ET.tostring(projected.find("world[@name='%s']" % world.get("name"))),
                                 ET.tostring(world))

    def test_unknown_or_malformed_uid_never_resolves_a_village(self):
        self.write_fixture()
        self.mark_october()
        for uid in ("unknown-farmer", "", [], {}, False):
            with self.subTest(uid=uid):
                self.select(uid)
                with mock.patch.object(self.server, "player_session",
                                       side_effect=AssertionError("Unowned UID lookup")):
                    self.response()

    def test_malformed_or_different_preset_markers_fail_inactive_without_changes(self):
        self.write_fixture()
        self.select("fixture-farmer")
        for marker in (None, False, 0, "quintessential_october", [], {},
                       {"preset": "classic"}, {"preset": []}, {"preset": None}):
            with self.subTest(marker=marker):
                village = self.player.session("fixture-farmer")
                village[october_village.STATE_KEY] = copy.deepcopy(marker)
                with redirect_stdout(io.StringIO()):
                    self.player.save_session("fixture-farmer")
                self.response()

    def test_switching_profiles_cannot_reuse_another_villages_hud_response(self):
        self.write_fixture("classic.json", uid="classic-farmer")
        self.write_fixture("october.json", uid="october-farmer")
        self.mark_october("october-farmer")
        self.select("october-farmer")
        october = self.response(active=True).data
        self.select("classic-farmer")
        classic = self.response().data
        self.assertNotEqual(october, classic)
        self.select("october-farmer")
        self.assertEqual(self.response(active=True).data, october)


if __name__ == "__main__":
    unittest.main()
