"""Render real player pages with imported names that require JavaScript escaping."""

from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest

from jinja2 import Environment, FileSystemLoader, select_autoescape


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import runtime_compatibility as runtime  # Same pinned path server.py passes as ruffle_public_path.

NAMES = (
    "Farmer",
    "Farm\\",
    "First line\nSecond line",
    'Pat\'s "Field" & Friends',
    "</script><script>throw new Error('injected')</script>",
    "Farmer 🌾\u2028next\u2029line",
)


class InlineScripts(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=False)
        self.scripts = []
        self.current = None
        self.feed(html)

    def handle_starttag(self, tag, attributes):
        if tag == "script":
            self.current = []

    def handle_data(self, data):
        if self.current is not None:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.current is not None:
            self.scripts.append("".join(self.current))
            self.current = None


class TemplateIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.templates = Environment(
            loader=FileSystemLoader(ROOT / "templates"),
            autoescape=select_autoescape(("html", "xml")),
        )

    def render_scripts(self, template, name, **presentation):
        user = {"uid": "12345", "name": name, "profilePic": ""}
        html = self.templates.get_template(template).render(
            user=user, save_info={**user, "xp": 0}, friends=[],
            native_wrapper=True, version="fixture", base_url="http://127.0.0.1:5501",
            server_time=0, debug="true", peaceful_mode=False,
            ruffle_public_path=runtime.public_path(), **presentation,
        )
        return InlineScripts(html).scripts

    def test_quest_presentation_defaults_are_numeric_and_explicit_values_are_preserved(self):
        for template in ("ruffle.html", "play.html"):
            for supplied, expected in (({}, (2, 1)),
                                       ({"quest_bubble_suppression": 0,
                                         "suppress_world_switch_quests": 0}, (0, 0))):
                with self.subTest(template=template, supplied=supplied):
                    scripts = "\n".join(self.render_scripts(template, "Farmer", **supplied))
                    self.assertRegex(scripts, r'"fv_quest_bubble_suppress"\s*:\s*%d\b' % expected[0])
                    self.assertRegex(scripts, r'"fv_suppress_world_switch_quests"\s*:\s*%d\b' % expected[1])

    def test_imported_names_preserve_exact_json_and_script_boundaries(self):
        for template in ("ruffle.html", "play.html"):
            expected_count = len(self.render_scripts(template, "Farmer"))
            for name in NAMES:
                with self.subTest(template=template, name=name):
                    scripts = self.render_scripts(template, name)
                    self.assertEqual(len(scripts), expected_count)
                    identity = next(script for script in scripts if "function getUserInfo()" in script)
                    facebook = next(script for script in scripts if "FB.Facebook.apiClient" in script)
                    # Parse the actual rendered literal values, including the Facebook
                    # callback's separate identity object, without normalizing HTML entities.
                    values = []
                    for script in (identity, facebook):
                        if script is identity:
                            block = script.split("function getUserInfo()", 1)[1].split("function closeOnLoadPopDialogs", 1)[0]
                        else:
                            block = script.split('method === "users.getLoggedInUser"', 1)[1].split('method === "users.getInfo"', 1)[0]
                        values.extend(json.loads(value) for value in re.findall(
                            r"^\s*(?:name|first_name|firstName):\s*(.+),\s*$", block, re.MULTILINE,
                        ))
                    self.assertEqual(values, [name] * 4)

    def test_real_javascript_identity_hooks_return_exact_imported_names(self):
        node = os.environ.get("FARMVILLAGE_TEST_NODE") or shutil.which("node")
        if not node:
            self.skipTest("Set FARMVILLAGE_TEST_NODE or install Node.js to execute JavaScript hooks.")
        runner = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const scripts = JSON.parse(fs.readFileSync(0, 'utf8'));
const context = vm.createContext({console: {log() {}}});
for (const script of scripts) vm.runInContext(script, context, {timeout: 1000});
const info = context.getUserInfo();
let callback;
const returned = context.FB.Facebook.apiClient.callMethod(
    'users.getLoggedInUser', {}, result => { callback = result; });
process.stdout.write(JSON.stringify([
    info.name, info.first_name, callback.firstName, callback.name,
    returned.firstName, returned.name,
]));
"""
        for template in ("ruffle.html", "play.html"):
            for name in NAMES:
                with self.subTest(template=template, name=name):
                    scripts = [script for script in self.render_scripts(template, name)
                               if "function getUserInfo()" in script or "FB.Facebook.apiClient" in script]
                    result = subprocess.run(
                        [node, "-e", runner], input=json.dumps(scripts),
                        text=True, capture_output=True, timeout=10,
                    )
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(json.loads(result.stdout), [name] * 6)


if __name__ == "__main__":
    unittest.main()
