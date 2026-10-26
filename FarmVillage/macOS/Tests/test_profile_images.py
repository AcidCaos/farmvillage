"""Optional network pictures never block an offline farm or mutate imports."""
import base64
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures


class ProfileImageProjectionTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    def prepare(self, picture):
        for uid in ("picture-owner", "picture-viewer"):
            save = self.fixture(uid)
            save["userInfo"]["attr"]["profilePic"] = picture if uid == "picture-owner" else ""
            fixtures.persistence.atomic_json(self.saves / (uid + ".json"), save)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        return self.saves / "picture-owner.json"

    def test_remote_picture_uses_original_empty_fallback_in_both_friend_channels_without_save_mutation(self):
        for picture in ("https://avatars.githubusercontent.com/u/11525599?size=48",
                        "http://unavailable.invalid/picture.png", "//unavailable.invalid/picture.png",
                        "/proxy?url=https%3A%2F%2Funavailable.invalid%2Fpicture.png",
                        "HTTPS://unavailable.invalid/picture.png"):
            with self.subTest(picture=picture):
                path = self.prepare(picture)
                before = path.read_bytes()
                self.assertEqual(self.player.profile_pic("picture-owner"), "")
                self.assertEqual(self.player.save_info("picture-owner")["profilePic"], "")
                friend = next(row for row in self.player.social_network_friends("picture-viewer")
                              if row["uid"] == "picture-owner")
                neighbor = next(row for row in self.player.neighbor_metadata("picture-viewer")
                                if row["uid"] == "picture-owner")
                self.assertEqual(friend["pic_square"], "")
                self.assertEqual(neighbor["profilePic"], "")
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(self.player.session("picture-owner")["userInfo"]["attr"]["profilePic"], picture)

    def test_actual_player_html_omits_unavailable_picture_for_browser_and_native_routes(self):
        picture = "https://unavailable.invalid/picture.png"
        path = self.prepare(picture)
        before = path.read_bytes()
        with self.client.session_transaction() as session:
            session["UID"] = "picture-owner"
        for route in ("/play.html", "/ruffle.html"):
            with self.subTest(route=route), fixtures.mock.patch.object(self.server, "NATIVE_WRAPPER", False):
                with redirect_stdout(io.StringIO()):
                    response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn(picture.encode(), response.data)
                self.assertNotIn(b"/proxy?url=", response.data)
        self.assertEqual(path.read_bytes(), before)

    def test_actual_amf_neighbor_bootstrap_uses_fallback_and_preserves_imported_picture(self):
        picture = "https://unavailable.invalid/picture.png"
        path = self.prepare(picture)
        before = path.read_bytes()
        response = self.gateway([self.command("UserService.initUser", ["Viewer", 0, True, {}], 1)], uid="picture-viewer")
        result = fixtures.gateway_results(self, response)[0]
        self.assertEqual(result["errorType"], 0)
        neighbors = json.loads(zlib.decompress(base64.b64decode(result["data"]["neighbors"])))
        owner = next(row for row in neighbors if row["uid"] == "picture-owner")
        self.assertEqual(owner["profilePic"], "")
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(json.loads(path.read_text())["userInfo"]["attr"]["profilePic"], picture)

    def test_existing_local_profile_and_neighborhood_artwork_are_preserved(self):
        for picture in ("", "/img/profile/acid.48.jpg", "/img/profile/unk.48.png",
                        "/assets/achievements/48x48/local-original.png"):
            with self.subTest(picture=picture):
                path = self.prepare(picture)
                before = path.read_bytes()
                self.assertEqual(self.player.profile_pic("picture-owner"), picture)
                self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
