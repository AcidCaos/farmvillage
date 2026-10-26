"""Browser quality-of-life checks: login defaults, game bar links, loading slideshow, new-village form, error bounce.

Run with the runtime dependencies installed:
    LocalData/venv/bin/python -m unittest discover -s macOS/Tests -p test_minion_browser_qol.py -v
All writable data is temporary (see test_persistence); no server socket is opened.
"""

from contextlib import redirect_stdout
from html.parser import HTMLParser
import io
import json
import os
import re
import shutil
import sys
import subprocess
import unittest
from unittest import mock
from urllib.parse import parse_qs

# Importing test_persistence sets up the temporary data directory and native-wrapper environment.
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
import test_persistence as fixtures
import persistence


INERT_HREFS = ("#", "javascript:void(0)")
NEW_VILLAGE_ERROR = "Use a farmer name between 1 and 80 characters."
ERROR_NOTICE = "The game hit a problem and returned you to the farm gate. Your farm was saved."


class Elements(HTMLParser):
    """Every start tag as (tag, attributes); valueless attributes such as `checked` map to None."""

    def __init__(self, markup):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.feed(markup)

    def handle_starttag(self, tag, attributes):
        self.tags.append((tag, dict(attributes)))

    handle_startendtag = handle_starttag


class MinionBrowserQolTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    fixture = fixtures.RuntimeFixtureTests.fixture

    def render_game(self, route):
        with self.client.session_transaction() as session:
            session["UID"] = "fixture-farmer"
        # Same wrapper mode each real client uses: ruffle.html for the native wrapper, play.html for legacy Flash.
        with mock.patch.object(self.server, "NATIVE_WRAPPER", route == "/ruffle.html"), redirect_stdout(io.StringIO()):
            response = self.client.get(route)
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def assert_no_farm_created(self):
        self.assertEqual(self.player.all_saves_uids(), [])
        self.assertEqual(list(self.saves.glob("*.json")), [])
        with self.client.session_transaction() as session:
            self.assertNotIn("UID", session)

    # 1. Ruffle is the default choice on the login page, but still optional.

    def test_ruffle_checkbox_is_checked_by_default_and_can_still_be_unchecked(self):
        self.write_fixture()
        with mock.patch.object(self.server, "NATIVE_WRAPPER", False), redirect_stdout(io.StringIO()):
            page = self.client.get("/").get_data(as_text=True)
        box = next(attrs for tag, attrs in Elements(page).tags if tag == "input" and attrs.get("id") == "RUFFLE")
        self.assertEqual(box.get("type"), "checkbox")
        self.assertIn("checked", box)

        # Unchecked (legacy Flash) still goes to play.html; checked goes to ruffle.html.
        with mock.patch.object(self.server, "NATIVE_WRAPPER", False), redirect_stdout(io.StringIO()):
            flash = self.client.post("/", data={"UID": "fixture-farmer"})
            ruffle = self.client.post("/", data={"UID": "fixture-farmer", "RUFFLE": "on"})
        self.assertEqual(flash.location, "/play.html")
        self.assertEqual(ruffle.location, "/ruffle.html")

    # 2. Game bar links that used href="#" must not open a duplicate window or navigate.

    def test_hash_links_in_both_game_bars_never_open_a_new_window(self):
        self.write_fixture()
        for route in ("/ruffle.html", "/play.html"):
            with self.subTest(route=route):
                anchors = [attrs for tag, attrs in Elements(self.render_game(route)).tags if tag == "a"]
                inert = [attrs for attrs in anchors if attrs.get("href") in INERT_HREFS]
                self.assertEqual(len(inert), 7)
                for attrs in anchors:
                    if attrs.get("href") == "#":
                        self.fail(f"href=\"#\" anchor remains: {attrs.get('title')}")
                    if attrs.get("href") in INERT_HREFS:
                        self.assertNotIn("target", attrs, attrs.get("title"))
                # Real links keep their behaviour.
                gifts = [attrs for attrs in anchors if attrs.get("href") == "/sn_app_url/gifts.php"]
                self.assertEqual(len(gifts), 1)
                self.assertEqual(gifts[0].get("target"), "_blank")

    def test_add_neighbors_handler_is_safe_when_the_client_lacks_the_function(self):
        node = os.environ.get("FARMVILLAGE_TEST_NODE") or shutil.which("node")
        if not node:
            self.skipTest("Set FARMVILLAGE_TEST_NODE or install Node.js to execute the inline handler.")
        self.write_fixture()
        handlers = {}
        for route in ("/ruffle.html", "/play.html"):
            anchors = [attrs for tag, attrs in Elements(self.render_game(route)).tags if tag == "a"]
            neighbor = next(attrs for attrs in anchors if attrs.get("title") == "Add Neighbors")
            self.assertIn("typeof farm.popR2AddNeighbor === 'function'", neighbor["onclick"])
            self.assertTrue(neighbor["onclick"].rstrip().endswith("return false;"))
            handlers[route] = neighbor["onclick"]
        runner = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const handler = new Function(input.code);
const scenarios = {
    missingFlashapp: () => null,
    missingFunction: () => ({}),
    presentFunction: () => { const element = {calls: []}; element.popR2AddNeighbor = (...args) => element.calls.push(args); return element; },
};
const results = {};
for (const [name, make] of Object.entries(scenarios)) {
    const element = make();
    globalThis.document = {getElementById: (id) => (id === 'flashapp' ? element : null)};
    try {
        const returned = handler.call({});
        results[name] = {returned, calls: element && element.calls ? element.calls : []};
    } catch (error) {
        results[name] = {error: String(error)};
    }
}
process.stdout.write(JSON.stringify(results));
"""
        for route, onclick in handlers.items():
            with self.subTest(route=route):
                # The parser already unescaped the attribute value, so it is the handler body itself.
                result = subprocess.run([node, "-e", runner], input=json.dumps({"code": onclick}),
                                        text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                outcome = json.loads(result.stdout)
                self.assertEqual(outcome["missingFlashapp"], {"returned": False, "calls": []})
                self.assertEqual(outcome["missingFunction"], {"returned": False, "calls": []})
                self.assertEqual(outcome["presentFunction"], {"returned": False, "calls": [["open"]]})

    # 3. The loading slideshow rotates every five seconds, as the original client did.

    def test_loading_slideshow_passes_five_second_change_time_in_both_clients(self):
        self.write_fixture()
        for route, pattern in (("/ruffle.html", r"parameters:\s*'(.+?)'"), ("/play.html", r"flashvars='(.+?)'")):
            with self.subTest(route=route):
                html_text = self.render_game(route)
                flashvars = re.search(pattern, html_text, re.DOTALL | re.IGNORECASE)
                self.assertIsNotNone(flashvars)
                raw = re.sub(r"\s|\\", "", flashvars.group(1))
                values = parse_qs(raw)
                self.assertEqual(values["fotdChangeTime"], ["5"])
                slides = values["fotd"][0].split(";")
                self.assertEqual(len(slides), 11)
                self.assertTrue(all(slide.startswith("/assets/fotd/Defaults/") and slide.endswith(".jpg")
                                    for slide in slides))
                # Directly after the photo list and before the cache-busting tail.
                self.assertRegex(raw, r"fotd=[^&]+&fotdChangeTime=5&brk=0")

    # 4. A Ruffle load failure shows a visible notice with a reload button (structural check).

    def test_ruffle_load_failure_shows_a_reload_notice(self):
        self.write_fixture()
        page = self.render_game("/ruffle.html")
        self.assertIn("}).catch(function (error) {", page)
        self.assertIn("The farm couldn't load. Click to reload.", page)
        self.assertIn('reload.addEventListener("click"', page)

    # 5. The new-village form: GET only shows it, POST creates the farm.

    def test_get_new_village_shows_the_form_without_creating_a_farm(self):
        with mock.patch.object(self.server, "new_village", wraps=self.server.new_village) as creator, \
             redirect_stdout(io.StringIO()):
            first = self.client.get("/new.html")
            second = self.client.get("/new.html")  # A reload must not create another farm either.
        for response in (first, second):
            self.assertEqual(response.status_code, 200)
            self.assertIn('action="/new.html"', response.get_data(as_text=True))
            self.assertIn('name="name"', response.get_data(as_text=True))
        creator.assert_not_called()
        self.assert_no_farm_created()

    def test_post_new_village_creates_one_named_farm_and_selects_it(self):
        with mock.patch.object(self.server, "NATIVE_WRAPPER", True), redirect_stdout(io.StringIO()):
            response = self.client.post("/new.html", data={"name": "Pat"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/ruffle.html")
        uids = self.player.all_saves_uids()
        self.assertEqual(len(uids), 1)
        saved = persistence.read_json(next(self.saves.glob("*.json")))
        self.assertEqual(saved["userInfo"]["attr"]["name"], "Pat")
        with self.client.session_transaction() as session:
            self.assertEqual(session["UID"], uids[0])

    def test_post_new_village_keeps_the_legacy_flash_redirect_outside_the_wrapper(self):
        with mock.patch.object(self.server, "NATIVE_WRAPPER", False), redirect_stdout(io.StringIO()):
            response = self.client.post("/new.html", data={"name": "Pat"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/play.html")
        self.assertEqual(len(self.player.all_saves_uids()), 1)

    def test_post_new_village_rejects_empty_and_overlong_names_on_the_form(self):
        for label, name in (("empty", ""), ("blank", "   "), ("too long", "x" * 81)):
            with self.subTest(label):
                with redirect_stdout(io.StringIO()):
                    response = self.client.post("/new.html", data={"name": name})
                self.assertEqual(response.status_code, 400)
                self.assertIn(NEW_VILLAGE_ERROR, response.get_data(as_text=True))
                self.assert_no_farm_created()

    def test_post_new_village_accepts_the_longest_allowed_name(self):
        with mock.patch.object(self.server, "NATIVE_WRAPPER", True), redirect_stdout(io.StringIO()):
            response = self.client.post("/new.html", data={"name": "x" * 80})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(self.player.all_saves_uids()), 1)

    def test_rejected_name_is_escaped_when_shown_back_on_the_form(self):
        hostile = "<script>alert(1)</script>" + "x" * 80
        with redirect_stdout(io.StringIO()):
            response = self.client.post("/new.html", data={"name": hostile})
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)

    # 6. A reported game error returns to the login page with a fixed notice, never the reported text.

    def test_game_error_redirects_to_login_with_a_fixed_notice_and_no_echo(self):
        query = {"ref": "1", "ooscode": "9", "oosfunc": "fn", "oosmsg": "<script>alert(1)</script>"}
        with redirect_stdout(io.StringIO()) as log:
            response = self.client.get("/sn_app_url/index.php", query_string=query)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/?error=1")
        self.assertIn("alert(1)", log.getvalue())  # Still logged for diagnosis.

        with redirect_stdout(io.StringIO()):
            banner = self.client.get(response.location).get_data(as_text=True)
            plain = self.client.get("/").get_data(as_text=True)
            injected = self.client.get("/?error=%3Cscript%3Ealert(1)%3C%2Fscript%3E").get_data(as_text=True)
        self.assertIn(ERROR_NOTICE, banner)
        self.assertNotIn(ERROR_NOTICE, plain)
        self.assertNotIn(ERROR_NOTICE, injected)
        self.assertNotIn("<script>alert(1)", injected)


if __name__ == "__main__":
    unittest.main()
