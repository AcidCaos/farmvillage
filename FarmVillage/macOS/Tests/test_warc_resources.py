"""WARC reader resource ownership regressions with tiny local archives."""

import gzip
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from warc_extractor import warc_extractor


class WARCResourceTests(unittest.TestCase):
    def test_context_closes_both_gzip_and_owned_raw_file(self):
        with tempfile.TemporaryDirectory(prefix="farmvillage-warc-handles-") as temporary:
            path = Path(temporary) / "fixture.warc.gz"
            with gzip.open(path, "wb") as stream:
                stream.write(b"tiny fixture")
            with warc_extractor.WARCFile(filename=str(path)) as archive:
                raw = archive.fileobj.fileobj
                self.assertEqual(archive.fileobj.read(), b"tiny fixture")
                self.assertFalse(raw.closed)
            self.assertTrue(archive.fileobj.closed)
            self.assertTrue(raw.closed)
            archive.close()  # Repeated cleanup is safe.

    def test_failed_compression_wrapper_closes_owned_file(self):
        with tempfile.TemporaryDirectory(prefix="farmvillage-warc-wrap-") as temporary:
            path = Path(temporary) / "fixture.warc.gz"
            path.write_bytes(b"fixture")
            with path.open("rb") as raw:
                with mock.patch.object(warc_extractor, "open", return_value=raw, create=True):
                    with mock.patch.object(warc_extractor.gzip, "open", side_effect=OSError("cannot wrap")):
                        with self.assertRaises(OSError):
                            warc_extractor.WARCFile(filename=str(path))
                self.assertTrue(raw.closed)


class WARCNativeOutputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="farmvillage-warc-paths-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output = self.root / "owned-extraction"
        self.output.mkdir()
        self.arguments = SimpleNamespace(
            dump="content", output_path=str(self.output) + "/", filter=[],
            silence=False, error=False, string="", path="unused",
        )
        self.environment = mock.patch.dict(os.environ, {"FARMVILLAGE_NATIVE": "1"})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def extract(self, uri):
        class Record(dict):
            http = {"content_type": "text/plain"}
        record = Record({"WARC-Target-URI": uri})
        with mock.patch.object(warc_extractor, "warc_records", return_value=[record]):
            warc_extractor.parse(self.arguments)

    def test_record_host_cannot_escape_extraction_root(self):
        with self.assertRaisesRegex(RuntimeError, "outside its output folder"):
            self.extract("http://../escaped/file.txt")
        self.assertFalse((self.root / "escaped").exists())
        self.assertEqual(list(self.output.iterdir()), [])

    def test_existing_link_cannot_redirect_record_output(self):
        outside = self.root / "outside"
        outside.mkdir()
        sentinel = outside / "file.txt"
        sentinel.write_text("keep this file", encoding="utf-8")
        (self.output / "example.invalid").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "outside its output folder"):
            self.extract("http://example.invalid/file.txt")
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep this file")

    def test_directory_failure_never_retries_a_truncated_absolute_path(self):
        with mock.patch.object(warc_extractor.os, "makedirs", side_effect=OSError("disk full")) as mkdir:
            with self.assertRaisesRegex(OSError, "disk full"):
                self.extract("http://example.invalid/folder/file.txt")
        self.assertEqual(mkdir.call_count, 1)
        attempted = Path(mkdir.call_args.args[0])
        attempted.relative_to(self.output)


if __name__ == "__main__":
    unittest.main()
