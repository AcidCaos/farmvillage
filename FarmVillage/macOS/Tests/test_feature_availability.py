"""Original HUD invitation gate; archived data and player saves stay intact."""

from contextlib import redirect_stdout
import copy
import io
from pathlib import Path
import re
import sys
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import feature_availability as availability


class FeatureAvailabilityTests(unittest.TestCase):
    def test_all_archived_invitations_are_gated_and_restored_entries_survive(self):
        source = availability.CMS_SOURCE.read_bytes()
        root = ET.fromstring(zlib.decompress(source))
        invitations = {f.get("name") for f in root.find("featureMessagingManagerSettings")}
        self.assertEqual(len(invitations), 194)
        expected = invitations | {"FeatureCrafting", "GenericFeatureOfTheWeek", "pearup"}
        blocked = availability.blocked_hud_icons()
        self.assertEqual(set(blocked), expected)
        self.assertEqual(blocked, tuple(sorted(blocked)))
        self.assertFalse(set(blocked) & availability.PRESERVED_HUD_ICONS)
        self.assertEqual(availability.hud_icon_blacklist().split(","), list(blocked))
        self.assertEqual(availability.CMS_SOURCE.read_bytes(), source)

    def test_invalid_or_ambiguous_invitation_names_fail_closed(self):
        for nodes in ('<feature name="bad,name"/>',
                      '<feature name="same"/><feature name="same"/>',
                      '<feature/>', ''):
            with self.subTest(nodes=nodes), self.assertRaises(ValueError):
                availability._blocked_names(zlib.compress(
                    ("<settings><featureMessagingManagerSettings>" + nodes
                     + "</featureMessagingManagerSettings></settings>").encode()))

    def test_startup_projection_removes_only_reviewed_retired_event_presentations(self):
        source = availability.POST_INIT_SOURCE.read_bytes()
        original = ET.fromstring(zlib.decompress(source))
        projected = ET.fromstring(zlib.decompress(availability.post_init_payload()))
        blocked = availability.BLOCKED_POST_INIT_ACTIONS
        self.assertEqual(len(blocked), 41)
        self.assertTrue({"fuelBoost", "consumableCampaign", "consumableCampaignInactive"} <= blocked)
        for original_queue, projected_queue in zip(original, projected):
            expected = [ET.tostring(node) for node in original_queue if node.get("name") not in blocked]
            self.assertEqual([ET.tostring(node) for node in projected_queue], expected)
        retained = {node.get("name") for queue in projected for node in queue}
        self.assertTrue({"craftingReminder", "unlockedSuperCrop", "preloadExpansion",
                         "LazyloadNeighborData", "loadFreeGifts"} <= retained)
        self.assertFalse(retained & blocked)
        self.assertEqual(availability.POST_INIT_SOURCE.read_bytes(), source)


class FeatureAvailabilityServingTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture

    def test_both_game_bootstraps_send_exact_original_gate_without_editing_player(self):
        path = self.write_fixture()
        with self.client.session_transaction() as session:
            session["UID"] = "fixture-farmer"
        # An imported farm may already have partially completed stories and
        # acknowledged invitations. Presentation gates must preserve all of it.
        saved = self.player.session("fixture-farmer")
        saved["questState"] = {
            "active": {"Aam-01-001": {"progress": [2, 1, 0], "new": 0},
                       "Anaanasbubble-01-001": {"progress": [0], "new": 1}},
            "completed": ["Aambubble-01-001"], "retired": [],
            "replayed": {"Aam-01-001": {"count": 1, "lastCompleted": 123}},
        }
        self.player.save_session("fixture-farmer")
        before = copy.deepcopy(self.player.session("fixture-farmer"))
        disk = path.read_bytes()
        expected = availability.hud_icon_blacklist()
        for url in ("/play.html", "/ruffle.html"):
            with self.subTest(url=url), mock.patch.object(self.server, "NATIVE_WRAPPER", False), \
                    redirect_stdout(io.StringIO()):
                response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            matches = re.findall(r"&FEATURE_FLASHPARAM_HUD_ICON_BLACKLIST=([^&\\\s]+)",
                                 response.get_data(as_text=True))
            self.assertEqual(matches, [expected])
            self.assertRegex(response.get_data(as_text=True),
                             r'"fv_instagrow_autoharvestreplant"\s*:\s*0\b')
            self.assertRegex(response.get_data(as_text=True),
                             r'"fv_quest_bubble_suppress"\s*:\s*2\b')
            self.assertRegex(response.get_data(as_text=True),
                             r'"fv_suppress_world_switch_quests"\s*:\s*1\b')
        response = self.client.get("/xml/gz/v855098/postInitSequence.xml.gz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/xml")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.data, availability.post_init_payload())
        self.assertEqual(self.player.session("fixture-farmer"), before)
        self.assertEqual(path.read_bytes(), disk)


if __name__ == "__main__":
    unittest.main()
