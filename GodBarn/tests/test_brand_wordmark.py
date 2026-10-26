"""Guard the wordmark derivative, its provenance record, and the page references to it."""

from pathlib import Path
import hashlib
import re
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "static/brand/god-barn-logo-v2.png"
DERIVATIVE = ROOT / "static/brand/god-barn-logo-v2@3x.png"


def png_header(path):
    with path.open("rb") as handle:
        data = handle.read(33)
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise AssertionError(f"{path.name} is not a PNG")
    width, height = struct.unpack(">II", data[16:24])
    return width, height, data[25]


class WordmarkDerivativeTests(unittest.TestCase):
    def test_runtime_derivative_is_three_times_the_box_with_alpha(self):
        width, height, color_type = png_header(DERIVATIVE)
        self.assertEqual((width, height), (438, 161))
        self.assertEqual(color_type, 6, "the wordmark must keep its alpha channel (RGBA)")
        self.assertLess(DERIVATIVE.stat().st_size, 200_000)

    def test_canonical_source_is_untouched_and_recorded(self):
        self.assertEqual(png_header(CANONICAL)[:2], (2065, 761))
        readme = (ROOT / "branding/README.md").read_text(encoding="utf-8")
        for path in (CANONICAL, DERIVATIVE):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertIn(digest, readme, f"README must record the SHA-256 of {path.name}")
        self.assertIn("sips -Z 438 static/brand/god-barn-logo-v2.png --out static/brand/god-barn-logo-v2@3x.png", readme)

    def test_page_uses_the_derivative_and_keeps_the_real_aspect_ratio(self):
        app = (ROOT / "static/app.js").read_text(encoding="utf-8")
        self.assertIn('/static/brand/god-barn-logo-v2@3x.png', app)
        self.assertNotIn('/static/brand/god-barn-logo-v2.png"', app)
        css = (ROOT / "static/farmville.css").read_text(encoding="utf-8")
        wordmark = re.search(r"\.brand\.brand-wordmarks>img\.godbarn-wordmark\{([^}]*)\}", css).group(1)
        self.assertIn("height:auto", wordmark)
        self.assertNotIn("object-fit:cover", wordmark)

    def test_viewport_declares_cover_for_safe_areas(self):
        html = (ROOT / "static/index.html").read_text(encoding="utf-8")
        viewport = re.search(r'<meta name="viewport" content="([^"]*)"', html).group(1)
        self.assertIn("viewport-fit=cover", viewport)
        self.assertIn("width=device-width", viewport)
        self.assertIn("initial-scale=1", viewport)


if __name__ == "__main__":
    unittest.main()
