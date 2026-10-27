"""Publication preparation must preserve upstream and the active local checkout."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "Scripts/prepare-github-fork.py"
spec = importlib.util.spec_from_file_location("github_publication", SCRIPT)
publication = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publication)


class PublicationTests(unittest.TestCase):
    def test_isolated_replay_keeps_upstream_and_local_assets_but_cleans_outgoing_history(self):
        with tempfile.TemporaryDirectory(prefix="fv-publication-test-") as temporary:
            root = Path(temporary)
            source, candidate = root / "source", root / "candidate"
            source.mkdir()
            publication.git(source, "init", "--initial-branch=main")
            publication.git(source, "config", "user.name", "Fixture owner")
            publication.git(source, "config", "user.email", "owner@example.invalid")
            (source / ".gitignore").write_text("/LocalData/\n")
            (source / "upstream.swf").write_bytes(b"unchanged upstream fixture")
            publication.git(source, "add", ".")
            publication.git(source, "commit", "-m", "Upstream fixture")
            base = publication.git(source, "rev-parse", "HEAD").decode().strip()
            (source / "portable").mkdir()
            (source / "portable/manage-bifrost.sh").write_text(
                "#!/bin/bash\nset -euo pipefail\n"
                "scp archive fixture@192.168.77.11:/home/fixture/farmville-test/release/\n")
            (source / "macOS/Resources/Heritage").mkdir(parents=True)
            (source / "macOS/Resources/Heritage/cow.png").write_bytes(b"local artwork fixture")
            (source / "macOS/Resources/Heritage/NOTICES.md").write_text("Retain ownership notice\n")
            (source / "BADABB__.TTF").write_bytes(b"local font fixture")
            publication.git(source, "add", ".")
            publication.git(source, "commit", "-m", "Local wrapper fixture")
            head = publication.git(source, "rev-parse", "HEAD").decode().strip()
            with patch.object(publication, "LEGACY_OWNER_COMMITS", (head,)):
                report = publication.prepare(source, candidate, base=base)
            self.assertEqual(publication.git(source, "rev-parse", "HEAD").decode().strip(), head)
            self.assertEqual(publication.git(source, "status", "--porcelain"), b"")
            self.assertEqual(publication.git(candidate, "status", "--porcelain"), b"")
            self.assertEqual(publication.git(candidate, "rev-parse", "HEAD^").decode().strip(), base)
            self.assertEqual(publication.git(candidate, "show", "HEAD:upstream.swf"), b"unchanged upstream fixture")
            inventory = publication.entries(candidate, "HEAD")
            self.assertNotIn("BADABB__.TTF", inventory)
            self.assertNotIn("macOS/Resources/Heritage/cow.png", inventory)
            self.assertIn("macOS/Resources/Heritage/NOTICES.md", inventory)
            self.assertEqual((candidate / "BADABB__.TTF").read_bytes(), b"local font fixture")
            identity = publication.git(candidate, "show", "-s", "--format=%an <%ae> %cn <%ce>").decode()
            self.assertNotIn("owner@example.invalid", identity)
            self.assertEqual(identity.count(publication.OWNER_EMAIL), 2)
            self.assertFalse(report["pushed"])
            self.assertFalse(report["deployed"])
            self.assertEqual(publication.git(candidate, "remote", "get-url", "--push", "upstream").strip(), b"DISABLED")

    def test_sanitized_helpers_require_configuration_and_parse_as_shell(self):
        identifiers = {"target": "fixture@192.168.77.11", "user": "fixture",
                       "root": "/home/fixture/farmville-test", "host": "192.168.77.11",
                       "workspace": "/private/example-workspace"}
        fixture = ("#!/bin/bash\nset -euo pipefail\n"
                   "target='fixture@192.168.77.11'\n"
                   "test_root='/home/fixture/farmville-test'\n")
        for relative in ("portable/manage-bifrost.sh", "portable/bifrost-update/manage-bifrost.sh"):
            with self.subTest(relative=relative):
                transformed = publication.sanitize_portable(relative, fixture.encode(), identifiers)
                self.assertNotIn(identifiers["target"].encode(), transformed)
                self.assertNotIn(identifiers["root"].encode(), transformed)
                self.assertIn(b"BIFROST_TARGET:?", transformed)
                checked = subprocess.run(["bash", "-n"], input=transformed, capture_output=True)
                self.assertEqual(checked.returncode, 0, checked.stderr.decode())
                environment = dict(os.environ, BIFROST_TARGET="farmvillage@192.168.50.80")
                for key, value in (("BIFROST_TARGET", "user@host;injected"),
                                   ("BIFROST_ROOT", "/home/user/has space"),
                                   ("BIFROST_BIND", "192.168.50.80;injected")):
                    refused = subprocess.run(["bash"], input=transformed, capture_output=True,
                                             env=dict(environment, **{key: value}))
                    self.assertNotEqual(refused.returncode, 0, (key, refused.stdout))


if __name__ == "__main__":
    unittest.main()
