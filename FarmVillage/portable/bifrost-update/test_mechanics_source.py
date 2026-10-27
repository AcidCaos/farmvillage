"""Verify source-delivery boundaries and reproducibility in disposable repos."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("mechanics_packager", HERE / "package-mechanics-source.py")
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


class MechanicsSourceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mechanics-source-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.repo = self.directory / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        for name in packager.SOURCE_FILES:
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture source " + name + "\n")
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        (self.repo / "commands.py").write_text("review candidate change\n")
        self.git("rm", "--cached", "pets.py")
        self.git("commit", "-qm", "remove newly developed module from base")
        (self.repo / "saves").mkdir()
        (self.repo / "saves/private.json").write_text("private save sentinel")
        (self.repo / "secret.txt").write_text("credential sentinel")
        (self.repo / "assets").mkdir()
        (self.repo / "assets/client.swf").write_text("proprietary binary sentinel")
        patcher = mock.patch.object(packager, "PROJECT", self.repo)
        patcher.start()
        self.addCleanup(patcher.stop)

    def git(self, *args):
        return subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", *args],
                              cwd=self.repo, check=True, capture_output=True).stdout

    def test_saved_source_and_new_modules_are_reviewable_without_private_files(self):
        output = self.directory / "source.tar.gz"
        manifest = packager.package(output)
        with tarfile.open(output) as archive:
            self.assertTrue(all(member.isfile() for member in archive))
            files = {member.name.removeprefix("farmvillage-mechanics-source/"): archive.extractfile(member).read()
                     for member in archive}
        self.assertEqual(files["source/commands.py"], b"review candidate change\n")
        self.assertIn("source/pets.py", files)
        for name in ("templates/play.html", "templates/ruffle.html", "feature_availability.py",
                     "macOS/Tests/test_cottage_lifecycle.py", "macOS/Tests/test_feature_availability.py",
                     "macOS/Tests/test_cottage_recipes.py", "macOS/Tests/test_cottage_client_graphics.py", "macOS/Tests/test_cottage_client_upgrades.py",
                     "macOS/Documentation/ClientPatches/cottage-graphics-byte-review.json",
                     "macOS/Documentation/ClientPatches/cottage-upgrade-visibility-byte-review.json",
                     "macOS/Scripts/prepare-portable-release.py",
                     "macOS/Tests/test_level_progression_1_100.py",
                     "macOS/Tests/test_market_availability.py",
                     "macOS/Documentation/COTTAGE_RECOVERY_2026-10-23.md",
                     "macOS/Documentation/COTTAGE_LEVEL_ONE_RECIPES_2026-10-23.md",
                     "macOS/Documentation/FEATURE_AVAILABILITY.md",
                     "macOS/Documentation/FEATURE_INVITATION_INVENTORY.csv",
                     "macOS/Documentation/LEVEL_PROGRESSION_AUDIT.md",
                     "macOS/Documentation/PLAYABLE_BASE_FIXES_2026-10-23.md",
                     "macOS/Documentation/LAMB_RAISING_STATUS.md", "macOS/Documentation/WORLD_TRAVEL_STATUS.md"):
            self.assertEqual(files["source/" + name], (self.repo / name).read_bytes())
        self.assertIn(b"--- /dev/null\n+++ b/pets.py", files["changes.patch"])
        self.assertIn(b"+review candidate change", files["changes.patch"])
        for sentinel in (b"private save sentinel", b"credential sentinel", b"proprietary binary sentinel"):
            self.assertFalse(any(sentinel in value for value in files.values()))
        self.assertEqual(json.loads(files["SOURCE_MANIFEST.json"]), manifest)
        for name, record in manifest["files"].items():
            self.assertEqual(record, {"sha256": hashlib.sha256(files[name]).hexdigest(), "bytes": len(files[name])})
        self.assertEqual(output.with_name(output.name + ".sha256").read_text().split(),
                         [hashlib.sha256(output.read_bytes()).hexdigest(), output.name])

    def test_source_patch_applies_to_the_recorded_base(self):
        files, _ = packager.contents()
        patch = self.directory / "review.patch"
        patch.write_bytes(files["changes.patch"])
        self.git("reset", "--hard", "HEAD")
        (self.repo / "pets.py").unlink()
        self.git("apply", "--check", str(patch))
        self.git("apply", str(patch))
        for name in packager.SOURCE_FILES:
            self.assertEqual((self.repo / name).read_bytes(), files["source/" + name])

    def test_repeatable_archive_and_existing_output_preservation(self):
        first, second = self.directory / "first.tgz", self.directory / "second.tgz"
        packager.package(first)
        packager.package(second)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        original = first.read_bytes()
        with self.assertRaises(ValueError):
            packager.package(first)
        self.assertEqual(first.read_bytes(), original)

    def test_patch_preserves_files_without_a_final_newline(self):
        target = self.repo / "requirements.txt"
        target.write_bytes(b"original dependency without newline")
        self.git("add", "requirements.txt")
        self.git("commit", "-qm", "base without final newline")
        target.write_bytes(b"updated dependency without newline")
        files, _ = packager.contents()
        patch = self.directory / "no-newline.patch"
        patch.write_bytes(files["changes.patch"])
        self.assertIn(b"\\ No newline at end of file\n", files["changes.patch"])
        self.git("reset", "--hard", "HEAD")
        (self.repo / "pets.py").unlink()
        self.git("apply", "--check", str(patch))
        self.git("apply", str(patch))
        self.assertEqual(target.read_bytes(), b"updated dependency without newline")

    def test_missing_or_symlinked_sources_fail_before_writing(self):
        target = self.repo / "pets.py"
        target.unlink()
        output = self.directory / "bad.tgz"
        with self.assertRaises(ValueError):
            packager.package(output)
        self.assertFalse(output.exists())
        target.symlink_to(self.repo / "secret.txt")
        with self.assertRaises(ValueError):
            packager.package(output)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
