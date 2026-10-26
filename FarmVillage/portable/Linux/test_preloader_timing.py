"""Keep the original photo list and all game behavior except its missing delay."""

import importlib.util
from pathlib import Path
import unittest

from flask import Flask, redirect


spec = importlib.util.spec_from_file_location("preloader_timing", Path(__file__).with_name("preloader_timing.py"))
timing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(timing)


class PreloaderTimingTests(unittest.TestCase):
    def test_missing_delay_is_inserted_without_touching_art_music_or_progress_settings(self):
        document = "<script>const flashvars='game=FarmGame.swf&music=true&fotd=a.jpg;b.jpg&brk=0&progress=original';</script>"
        result = timing.photo_interval(document)
        self.assertEqual(result, document.replace("&fotd=", "&fotdChangeTime=5&fotd="))
        self.assertEqual(timing.photo_interval(result), result)
        self.assertNotIn("frameRate", result)

    def test_existing_zero_delay_and_html_encoding_are_preserved_correctly(self):
        self.assertEqual(timing.photo_interval("x&amp;fotdChangeTime=0&amp;fotd=a;b&amp;end=1"),
                         "x&amp;fotdChangeTime=5&amp;fotd=a;b&amp;end=1")
        self.assertEqual(timing.photo_interval("x&fotd=a;b&fotdChangeTime=0&other=1"),
                         "x&fotd=a;b&fotdChangeTime=5&other=1")
        with self.assertRaises(ValueError):
            timing.photo_interval("no recognized photo list")

    def test_actual_both_source_templates_have_the_expected_exact_flashvar_edit(self):
        root = Path(__file__).resolve().parents[2]
        for name in ("ruffle.html", "play.html"):
            # The source templates now carry the five-second pace themselves, so
            # the portable hook must recognize it and leave the page unchanged.
            original = (root / "templates" / name).read_text()
            self.assertEqual(original.count("fotdChangeTime=5"), 1)
            result = timing.photo_interval(original)
            self.assertEqual(result, original)

    def test_bounded_execution_budget_precedes_loader_and_preserves_public_path(self):
        original = '<script>window.RufflePlayer.config = { publicPath: "/pinned/", autoplay: "on" };</script><script src="/pinned/ruffle.js"></script>'
        result = timing.execution_budget(original)
        self.assertEqual(result, original.replace("config = {", "config = { maxExecutionDuration: 60,"))
        self.assertEqual(timing.execution_budget(result), result)
        self.assertLess(result.index("maxExecutionDuration: 60"), result.index('src="/pinned/ruffle.js"'))
        for key in ("maxExecutionDuration", '"maxExecutionDuration"', "'maxExecutionDuration'"):
            configured = original.replace("autoplay:", key + ":15, autoplay:")
            self.assertIn(key + ":60", timing.execution_budget(configured))
            self.assertNotIn(key + ":15", timing.execution_budget(configured))
        wrong_order = '<script src="/pinned/ruffle.js"></script>' + original
        with self.assertRaises(ValueError):
            timing.execution_budget(wrong_order)

    def test_actual_rendered_template_keeps_pinned_path_and_sets_budget_before_loader(self):
        from flask import render_template
        root = Path(__file__).resolve().parents[2]
        app = Flask("actual-ruffle-template", template_folder=str(root / "templates"))
        with app.app_context():
            original = render_template("ruffle.html", ruffle_public_path="/ruffle/0.7.1-farmvillage-gc1/",
                                       native_wrapper=False, user={"uid": "fixture", "name": "Farmer", "profilePic": ""},
                                       friends=[], save_info={"name": "Farmer", "xp": 0})
        result = timing.execution_budget(original)
        self.assertIn('publicPath: "/ruffle/0.7.1-farmvillage-gc1/"', result)
        self.assertLess(result.index("maxExecutionDuration: 60"), result.index('src="/ruffle/0.7.1-farmvillage-gc1/ruffle.js"'))

    def test_response_hook_is_limited_to_successful_game_html_and_updates_length(self):
        app = Flask("preloader-timing-test")
        body = '<html><script>window.RufflePlayer.config = {publicPath:"/pinned/"};</script><script src="/pinned/ruffle.js"></script>native wrapper or browser&fotd=a.jpg;b.jpg&other=1</html>'
        for path in ("/ruffle.html", "/play.html", "/god-barn/", "/assets/photo.jpg"):
            app.add_url_rule(path, path, lambda: body)
        app.add_url_rule("/login", "login", lambda: redirect("/"))
        timing.configure_preloader(app)
        timing.configure_preloader(app)  # Re-registering cannot add duplicate parameters.
        client = app.test_client()
        for path in ("/ruffle.html", "/play.html"):
            expected = timing.photo_interval(body)
            if path == "/ruffle.html": expected = timing.execution_budget(expected)
            expected = expected.encode()
            response = client.get(path)
            self.assertEqual(response.data, expected)
            self.assertEqual(int(response.headers["Content-Length"]), len(expected))
        self.assertEqual(client.get("/god-barn/").data, body.encode())
        self.assertEqual(client.get("/assets/photo.jpg").data, body.encode())
        self.assertEqual(client.get("/login").status_code, 302)


if __name__ == "__main__":
    unittest.main()
