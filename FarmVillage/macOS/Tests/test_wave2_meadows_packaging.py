"""Final client staging and source-bound portable Meadows identities."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release = load("meadows_portable_identity", ROOT / "macOS/Scripts/prepare-portable-release.py")
patch = load("meadows_staging_identity", ROOT / "macOS/Scripts/patch-game-client.py")
meadows = load("meadows_served_identity", ROOT / "meadows_client.py")
graphics = load("graphics_served_identity", ROOT / "client_graphics.py")
compatibility = load("meadows_base_identity", ROOT / "client_compatibility.py")


class MeadowsPackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = (ROOT / "embeds/Flash/v855097-855094/FarmGame.swf").read_bytes()
        cls.base = compatibility.patch_client_bytes(cls.original)
        cls.meadows_current = meadows.patch_client_bytes(cls.base)
        cls.current = graphics.patch_client_bytes(cls.meadows_current)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="meadows package ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def cli(self, source, output, script=None):
        return subprocess.run([sys.executable, "-I", "-B",
            str(script or ROOT / "macOS/Scripts/patch-game-client.py"), str(source), str(output)],
            text=True, capture_output=True, timeout=20)

    def test_isolated_cli_matches_served_bytes_for_raw_prior_and_final_inputs(self):
        original_path = self.root / "original.swf"
        original_path.write_bytes(self.original)
        sys.path.insert(0, str(ROOT))
        try:
            served = graphics.prepared_client(original_path)
        finally:
            sys.path.pop(0)
        self.assertEqual(served, self.current)
        self.assertEqual(patch.patch_client_bytes(self.original), served)
        self.assertEqual(patch.prepared_client(original_path), served)
        self.assertEqual(hashlib.sha256(served).hexdigest(), release.CLIENT_FILE_SHA)
        api_output = self.root / "api-output.swf"
        self.assertTrue(patch.patch_client_file(original_path, api_output))
        self.assertEqual(api_output.read_bytes(), served)
        for label, content in (("raw", self.original), ("prior", self.base), ("meadows", self.meadows_current), ("final", self.current)):
            with self.subTest(input=label):
                source, output = self.root / (label + ".swf"), self.root / (label + "-output.swf")
                source.write_bytes(content)
                result = self.cli(source, output)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(output.read_bytes(), served)
                self.assertEqual(source.read_bytes(), content)
                again = self.cli(output, output)
                self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
                self.assertEqual(output.read_bytes(), served)

    def test_relocated_tools_and_runtime_use_only_their_local_recipe(self):
        outer = self.root / "Outer"
        release_root = outer / "Release"
        tools, payload = release_root / "Tools", release_root / "Runtime"
        tools.mkdir(parents=True); payload.mkdir()
        (outer / "client_compatibility.py").write_text("raise RuntimeError('ambient recipe must not execute')\n")
        script = tools / "patch-game-client.py"
        shutil.copy2(ROOT / "macOS/Scripts/patch-game-client.py", script)
        for name in ("client_compatibility.py", "cove_client.py", "meadows_client.py", "client_graphics.py"):
            shutil.copy2(ROOT / name, payload / name)
        source, output = self.root / "raw.swf", self.root / "output.swf"
        source.write_bytes(self.original)
        result = self.cli(source, output, script)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(output.read_bytes(), self.current)
        (payload / "meadows_client.py").unlink()
        output.write_bytes(b"keep complete previous generation")
        result = self.cli(source, output, script)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("meadows_client.py", result.stderr)
        self.assertEqual(output.read_bytes(), b"keep complete previous generation")
        (payload / "client_compatibility.py").unlink()
        result = self.cli(source, output, script)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("compatibility module is missing", result.stderr)
        self.assertNotIn("ambient recipe must not execute", result.stderr)

    def test_unknown_client_preserves_previous_output_without_temporary_files(self):
        source, output = self.root / "unknown.swf", self.root / "output.swf"
        source.write_bytes(b"unknown client revision")
        output.write_bytes(self.current)
        result = self.cli(source, output)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output.read_bytes(), self.current)
        self.assertEqual({p.name for p in self.root.iterdir()}, {"unknown.swf", "output.swf"})

    def fixture_policy(self):
        project, payload = self.root / "Source", self.root / "Runtime"
        for name in release.MEADOWS_MODULES:
            for destination in (project / name, payload / name):
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / name, destination)
        original = project / "embeds/Flash/v855097-855094/FarmGame.swf"
        original.parent.mkdir(parents=True)
        original.write_bytes(self.original)
        for target in (project / "macOS/Scripts/patch-game-client.py", payload.parent / "WrapperRuntime/patch-game-client.py"):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / "macOS/Scripts/patch-game-client.py", target)
        return project, payload

    def test_missing_stale_or_linked_staging_tool_cannot_be_sealed(self):
        project, payload = self.fixture_policy()
        tool = payload.parent / "WrapperRuntime/patch-game-client.py"
        original = tool.read_bytes()
        tool.unlink()
        with self.assertRaisesRegex(ValueError, "missing its ordinary client staging tool"):
            release.meadows_payload_policy(project, payload, self.current)
        tool.write_bytes(original + b"\n# stale tool\n")
        with self.assertRaisesRegex(ValueError, "staging tool differs from selected source"):
            release.meadows_payload_policy(project, payload, self.current)
        tool.unlink(); tool.symlink_to(project / "macOS/Scripts/patch-game-client.py")
        with self.assertRaisesRegex(ValueError, "missing its ordinary client staging tool"):
            release.meadows_payload_policy(project, payload, self.current)

    def test_portable_policy_requires_current_modules_and_exact_served_composition(self):
        project, payload = self.fixture_policy()
        policy = release.meadows_payload_policy(project, payload, self.current)
        self.assertEqual(policy["worlds"], ["farm", "england", "meadows", "fisherman", "rainforest"])
        self.assertEqual(set(policy["required_source_sha256"]), set(release.MEADOWS_MODULES))
        with self.assertRaisesRegex(ValueError, "served client composition"):
            release.meadows_payload_policy(project, payload, self.base)
        with self.assertRaisesRegex(ValueError, "served client composition"):
            release.meadows_payload_policy(project, payload, self.current + b"trailing bytes")

    def test_missing_stale_or_linked_required_sources_cannot_be_sealed(self):
        project, payload = self.fixture_policy()
        for name in release.MEADOWS_MODULES:
            with self.subTest(module=name):
                path = payload / name
                original = path.read_bytes()
                path.unlink()
                with self.assertRaisesRegex(ValueError, "missing an ordinary required"):
                    release.meadows_payload_policy(project, payload, self.current)
                path.write_bytes(original + b"\n# stale generation\n")
                with self.assertRaisesRegex(ValueError, "differs from selected source"):
                    release.meadows_payload_policy(project, payload, self.current)
                path.unlink(); path.symlink_to(project / name)
                with self.assertRaisesRegex(ValueError, "missing an ordinary required"):
                    release.meadows_payload_policy(project, payload, self.current)
                path.unlink(); path.write_bytes(original)

    def test_manifest_pin_and_review_describe_final_scoped_client(self):
        self.assertEqual(release.MEADOWS_BODY_SHA, meadows.PATCHED_BODY_SHA256)
        self.assertEqual(graphics.BASE_BODY_SHA256, meadows.PATCHED_BODY_SHA256)
        self.assertEqual(release.CLIENT_BODY_SHA, graphics.PATCHED_BODY_SHA256)
        self.assertEqual(patch.PATCHED_BODY_SHA256, graphics.PATCHED_BODY_SHA256)
        self.assertEqual(patch.PATCHED_BODY_BYTES, graphics.PATCHED_BODY_BYTES)
        self.assertIn("GRAPHICS_CACHE_CLIENT_REVIEW.json", release.CLIENT_REVIEWS)
        self.assertIn("MEADOWS_SCOPED_CLIENT_REVIEW.json", release.CLIENT_REVIEWS)
        self.assertIn("meadows_scoped_controls", (ROOT / "macOS/Scripts/prepare-portable-release.py").read_text())


if __name__ == "__main__":
    unittest.main()
