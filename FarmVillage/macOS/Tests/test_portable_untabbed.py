"""Current portable releases require the Not in Market classification index."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "Scripts/prepare-portable-release.py"
SPEC = importlib.util.spec_from_file_location("portable_untabbed_release", SCRIPT)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class PortableUntabbedTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="fv-portable-untabbed-")
        self.addCleanup(self.temporary.cleanup)
        self.payload = Path(self.temporary.name)
        self.index = self.payload / "GodBarn/data/untabbed.json"
        self.index.parent.mkdir(parents=True)

    def test_reads_the_index_packaged_with_the_accepted_payload(self):
        value = {"schema": 1, "items": {"pinkcow": {"origin": "other"}}}
        self.index.write_text(json.dumps(value))
        self.assertEqual(release.untabbed_index(self.payload), value)

    def test_old_payload_without_index_requests_a_rebuild(self):
        with self.assertRaisesRegex(ValueError, "rebuild the companion bundle"):
            release.untabbed_index(self.payload)

    def test_symlink_is_not_accepted_as_packaged_metadata(self):
        target = self.payload / "elsewhere.json"
        target.write_text('{"schema":1,"items":{}}')
        self.index.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "GodBarn/data/untabbed.json"):
            release.untabbed_index(self.payload)

    def test_non_index_json_is_rejected(self):
        for value in ([], {"schema": 2, "items": {}}, {"schema": 1, "items": []}):
            with self.subTest(value=value):
                self.index.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, "schema-1 item index"):
                    release.untabbed_index(self.payload)
