"""The source server and native bundle deliver the same compatible client."""

from pathlib import Path
from unittest import mock
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures


ROOT = Path(__file__).resolve().parents[2]
GAME_PATH = "Flash/v855097-855094/FarmGame.swf"
GAME_URL = "/embeds/" + GAME_PATH


class ClientServingTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp

    def test_source_route_returns_prepared_copy_without_changing_archive(self):
        import client_compatibility, meadows_client, client_graphics
        source = ROOT / "embeds" / GAME_PATH
        original = source.read_bytes()
        response = self.client.get(GAME_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/x-shockwave-flash")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.data, client_graphics.patch_client_bytes(meadows_client.patch_client_bytes(client_compatibility.patch_client_bytes(original))))
        self.assertNotEqual(response.data, original)
        self.assertEqual(source.read_bytes(), original)

    def test_bundled_route_accepts_prepared_client_and_rejects_replaced_unknown_code(self):
        import client_compatibility, meadows_client, client_graphics
        original = (ROOT / "embeds" / GAME_PATH).read_bytes()
        staged = Path(self.directory.name) / GAME_PATH
        staged.parent.mkdir(parents=True)
        prepared = client_compatibility.patch_client_bytes(original)
        staged.write_bytes(prepared)
        with mock.patch.object(self.server, "EMBEDS_DIR", self.directory.name):
            final = client_graphics.patch_client_bytes(meadows_client.patch_client_bytes(prepared))
            self.assertEqual(self.client.get(GAME_URL).data, final)
            for contents in (meadows_client.patch_client_bytes(prepared), final):
                staged.write_bytes(contents)
                self.assertEqual(self.client.get(GAME_URL).data, final)
            staged.write_bytes(b"unsupported client revision")
            with self.assertRaises(ValueError):
                self.client.get(GAME_URL)
        self.assertEqual(staged.read_bytes(), b"unsupported client revision")


if __name__ == "__main__":
    unittest.main()
