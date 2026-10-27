"""Source delivery boundaries against temporary Git repositories; no network."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import types
import unittest
from unittest import mock


HERE = Path(__file__).resolve().parent
packager = types.ModuleType("community_source_packager_tests")
packager.__file__ = str(HERE / "package-community-source.py")
sys.modules[packager.__name__] = packager
exec(compile(Path(packager.__file__).read_bytes(), packager.__file__, "exec"), packager.__dict__)


class CommunitySourceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="community-source-tests-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.repository = self.directory / "repository"
        self.repository.mkdir()
        self.git("init", "-q")
        for name in (*packager.SOURCE_FILES, "LICENSE"):
            path = self.repository / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture text for " + name + "\n")
        for name in ("assets/art.swf", "saves/farm.json", "LocalData/password.txt"):
            path = self.repository / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("excluded private fixture\n")
        self.git("add", ".")
        self.git("commit", "-qm", "base fixture")
        (self.repository / "ugc.py").write_text("committed repair source\n")
        (self.repository / "assets/art.swf").write_text("excluded asset change\n")
        self.git("add", ".")
        self.git("commit", "-qm", "repair fixture")
        # Dirty and untracked local changes must never be part of this delivery.
        (self.repository / "ugc.py").write_text("uncommitted working source\n")
        (self.repository / "secret.txt").write_text("untracked credential fixture\n")
        patcher = mock.patch.object(packager, "PROJECT", self.repository)
        patcher.start()
        self.addCleanup(patcher.stop)

    def git(self, *arguments):
        return subprocess.run(["git", "-c", "user.name=Source Fixture", "-c", "user.email=fixture@example.invalid",
                               *arguments], cwd=self.repository, check=True, capture_output=True).stdout

    def test_archive_contains_committed_source_tests_license_contract_and_scoped_patch_only(self):
        output = self.directory / "source.tar.gz"
        manifest = packager.package("HEAD", output)
        with tarfile.open(output, "r:gz") as archive:
            members = archive.getmembers()
            files = {member.name.removeprefix("community-deco-source/"): archive.extractfile(member).read()
                     for member in members}
        self.assertTrue(all(member.isfile() for member in members))
        self.assertEqual(files["source/ugc.py"], b"committed repair source\n")
        self.assertEqual(files["LICENSE"], (self.repository / "LICENSE").read_bytes())
        self.assertEqual(files["README.md"], (self.repository / packager.CONTRACT).read_bytes())
        self.assertIn("source/macOS/Tests/test_feature_options.py", files)
        self.assertIn("source/macOS/Documentation/ClientPatches/deco-client-byte-review.json", files)
        self.assertIn("source/macOS/Documentation/ClientPatches/README.md", files)
        self.assertIn(b"committed repair source", files["changes.patch"])
        for excluded in (b"excluded private fixture", b"excluded asset change", b"uncommitted working source",
                         b"untracked credential fixture"):
            self.assertFalse(any(excluded in data for data in files.values()))
        self.assertFalse(any(name.startswith(("source/assets/", "source/saves/", "source/LocalData/")) for name in files))
        self.assertEqual(json.loads(files["SOURCE_MANIFEST.json"]), manifest)
        self.assertEqual(json.loads(output.with_name(output.name + ".manifest.json").read_text()), manifest)
        self.assertEqual(output.with_name(output.name + ".sha256").read_text().split(),
                         [hashlib.sha256(output.read_bytes()).hexdigest(), output.name])
        for name, record in manifest["files"].items():
            self.assertEqual(record, {"sha256": hashlib.sha256(files[name]).hexdigest(), "bytes": len(files[name])})

    def test_same_commit_has_reproducible_archive_bytes(self):
        first, second = self.directory / "first.tar.gz", self.directory / "second.tar.gz"
        packager.package("HEAD", first)
        packager.package("HEAD", second)
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_existing_deliveries_are_preserved_without_reading_repository(self):
        output = self.directory / "existing.tar.gz"
        output.write_bytes(b"keep existing delivery")
        with mock.patch.object(packager, "contents") as contents:
            with self.assertRaises(ValueError):
                packager.package("HEAD", output)
        contents.assert_not_called()
        self.assertEqual(output.read_bytes(), b"keep existing delivery")

    def test_missing_committed_source_aborts_before_writing_delivery(self):
        self.git("rm", "-f", "ugc.py")
        self.git("commit", "-qm", "incomplete source fixture")
        output = self.directory / "incomplete.tar.gz"
        with self.assertRaises(subprocess.CalledProcessError):
            packager.package("HEAD", output)
        self.assertFalse(output.exists())
        self.assertFalse(output.with_name(output.name + ".sha256").exists())


if __name__ == "__main__":
    unittest.main()
