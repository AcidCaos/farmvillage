"""The real game receives its supported Sound identity lookup option."""

import copy
from pathlib import Path
import re
import sys
import unittest
from unittest import mock
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures


class AudioClientTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    fixture = fixtures.RuntimeFixtureTests.fixture

    def test_both_real_clients_use_sound_identity_without_changing_audio_options(self):
        self.write_fixture()
        saved_options = copy.deepcopy(self.player.session("fixture-farmer")["userInfo"]["player"]["options"])
        with self.client.session_transaction() as session:
            session["UID"] = "fixture-farmer"
        for route, pattern in (("/ruffle.html", r"parameters:\s*'(.+?)'"),
                               ("/play.html", r"flashvars='(.+?)'")):
            with self.subTest(route=route):
                with mock.patch.object(self.server, "NATIVE_WRAPPER", route == "/ruffle.html"):
                    response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                flashvars = re.search(pattern, response.get_data(as_text=True), re.DOTALL | re.IGNORECASE)
                self.assertIsNotNone(flashvars)
                # Parse the actual player load parameters, not the separate
                # experiments object. SoundManager tests the literal "true".
                values = parse_qs(re.sub(r"\s|\\", "", flashvars.group(1)))
                self.assertEqual(values["soundOptimizedCheck"], ["true"])
                self.assertEqual(values["noSound"], ["0"])
                self.assertNotIn("musicDisabled", values)
                self.assertNotIn("sfxDisabled", values)
        self.assertEqual(self.player.session("fixture-farmer")["userInfo"]["player"]["options"], saved_options)


if __name__ == "__main__":
    unittest.main()
