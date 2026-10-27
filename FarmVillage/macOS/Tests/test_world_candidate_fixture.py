"""Only marked disposable QA copies can enable dormant world candidates."""
import ast
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("world_candidate_preparation", ROOT / "macOS/Scripts/enable-world-candidate.py")
HELPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPER)
BASELINE_ACTIVE_WORLDS = frozenset({"rainforest", "mediterranean", "storybook", "candy", "oasis", "oz"})
# enable-world-candidate.py accepts only fixtures under /private/tmp (a macOS location), so a
# fixture elsewhere would be refused for that reason and prove nothing about the other checks.
needs_private_tmp = unittest.skipUnless(Path("/private/tmp").is_dir(), "UNRUN: the tool under test accepts only /private/tmp fixtures, which exist only on macOS")


class CandidateFixtureTests(unittest.TestCase):
    def fixture(self, path):
        root = Path(path).resolve()
        (root / ".disposable-features-fixture").touch()
        (root / "Runtime").mkdir()
        source = root / "Runtime/themed_worlds.py"
        source.write_bytes((ROOT / "themed_worlds.py").read_bytes())
        # Recreate the six-world fixture baseline without changing production's
        # browser-accepted activation list or any copied world contracts.
        node = self.activation_node(source)
        lines = source.read_text().splitlines(keepends=True)
        values = ", ".join(json.dumps(world) for world in sorted(BASELINE_ACTIVE_WORLDS))
        lines[node.lineno - 1:node.end_lineno] = ["ACTIVE_WORLDS = frozenset({" + values + "})\n"]
        source.write_text("".join(lines))
        (root / "data").mkdir()
        save = root / "data/preserve.save.json"
        save.write_bytes(b"synthetic progress must remain byte-identical")
        metadata = {"root": str(root), "runtime": str(root / "Runtime"),
                    "synthetic": True, "credentials": False, "port": 45489}
        (root / "fixture.json").write_text(json.dumps(metadata))
        return root, source, save, metadata

    @staticmethod
    def activation_node(source):
        tree = ast.parse(source.read_text())
        return next(n for n in tree.body if isinstance(n, ast.Assign)
                    and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "ACTIVE_WORLDS")

    @classmethod
    def active(cls, source):
        node = cls.activation_node(source)
        return frozenset(ast.literal_eval(node.value.args[0]))

    @needs_private_tmp
    def test_explicit_candidates_compose_idempotently_only_in_fixture_copy(self):
        original = (ROOT / "themed_worlds.py").read_bytes()
        accepted = BASELINE_ACTIVE_WORLDS
        self.assertEqual(self.active(ROOT / "themed_worlds.py"), (accepted | HELPER.CANDIDATES) - {"glen", "hlights"})
        with tempfile.TemporaryDirectory(prefix="fv-world-candidate-test-", dir="/private/tmp") as temporary:
            root, source, save, _ = self.fixture(temporary)
            progress = save.read_bytes()
            self.assertEqual(self.active(source), accepted)
            self.assertTrue(HELPER.enable_candidate(root, "toyland"))
            self.assertEqual(self.active(source), accepted | {"toyland"})
            first = source.read_bytes()
            self.assertFalse(HELPER.enable_candidate(root, "toyland"))
            self.assertEqual(source.read_bytes(), first)
            self.assertTrue(HELPER.enable_candidate(root, "htown"))
            self.assertEqual(self.active(source), accepted | {"toyland", "htown"})
            self.assertTrue(HELPER.enable_candidate(root, "atlantis"))
            self.assertEqual(self.active(source), accepted | {"toyland", "htown", "atlantis"})
            enabled = source.read_bytes()
            self.assertFalse(HELPER.enable_candidate(root, "atlantis"))
            self.assertEqual(source.read_bytes(), enabled)
            self.assertTrue(HELPER.enable_candidate(root, "glen"))
            self.assertEqual(self.active(source), accepted | {"toyland", "htown", "atlantis", "glen"})
            enabled = source.read_bytes()
            self.assertFalse(HELPER.enable_candidate(root, "glen"))
            self.assertEqual(source.read_bytes(), enabled)
            self.assertTrue(HELPER.enable_candidate(root, "hlights"))
            self.assertEqual(self.active(source), accepted | {"toyland", "htown", "atlantis", "glen", "hlights"})
            enabled = source.read_bytes()
            self.assertFalse(HELPER.enable_candidate(root, "hlights"))
            self.assertEqual(source.read_bytes(), enabled)
            self.assertEqual(save.read_bytes(), progress)
        self.assertEqual((ROOT / "themed_worlds.py").read_bytes(), original)

    def test_source_checkout_is_refused_on_every_host(self):
        with self.assertRaisesRegex(ValueError, "/private/tmp|marked disposable fixture"):
            HELPER.enable_candidate(ROOT, "toyland")

    @needs_private_tmp
    def test_source_checkout_unknown_world_unmarked_and_owner_fixture_are_refused(self):
        with self.assertRaisesRegex(ValueError, "/private/tmp|marked disposable fixture"):
            HELPER.enable_candidate(ROOT, "toyland")
        with tempfile.TemporaryDirectory(prefix="fv-world-candidate-test-", dir="/private/tmp") as temporary:
            root, source, _, metadata = self.fixture(temporary)
            original = source.read_bytes()
            for changes in ({"port": 45467}, {"port": 45358}, {"synthetic": False},
                            {"credentials": True}, {"runtime": str(ROOT)}):
                (root / "fixture.json").write_text(json.dumps({**metadata, **changes}))
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    HELPER.enable_candidate(root, "toyland")
                self.assertEqual(source.read_bytes(), original)
            (root / "fixture.json").write_text(json.dumps(metadata))
            with self.assertRaises(ValueError):
                HELPER.enable_candidate(root, "not-a-recovered-world")
            (root / ".disposable-features-fixture").unlink()
            with self.assertRaises(ValueError):
                HELPER.enable_candidate(root, "toyland")
            self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
