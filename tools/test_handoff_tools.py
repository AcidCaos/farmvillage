"""Synthetic importer/staging regressions; no original game inputs or farm access."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent

def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

inputs = load("handoff_inputs", "private-inputs.py")
stager = load("handoff_stager", "prepare-browser-runtime.py")

class InputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="farmvillage-handoff-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "source"
        self.root.mkdir()
        self.runtime = self.base / "private-game"
        self.barn = self.base / "private-barn"
        self.runtime.mkdir()
        self.barn.mkdir()
        self.raw = b"synthetic input, no game data"
        (self.runtime / "fixture.amf").write_bytes(self.raw)
        self.files = {"FarmVillage/fixture.amf": {"bytes": len(self.raw), "sha256": hashlib.sha256(self.raw).hexdigest()}}
        self.write_manifest()

    def write_manifest(self, public=None):
        (self.root / "PrivateInputs.expected.json").write_text(json.dumps({"schema": 1, "files": self.files}))
        (self.root / "SOURCE_MANIFEST.json").write_text(json.dumps({"files": public or {}}))

    def test_matching_complete_import_and_check(self):
        result = inputs.import_inputs(self.root, self.runtime, self.barn)
        self.assertEqual(result["status"], "all-private-inputs-match")
        self.assertEqual((self.root / "FarmVillage/fixture.amf").read_bytes(), self.raw)
        self.assertEqual(inputs.check(self.root)["files"], 1)

    def test_corrupt_source_fails_before_any_write(self):
        (self.runtime / "fixture.amf").write_bytes(b"wrong")
        with self.assertRaises(ValueError):
            inputs.import_inputs(self.root, self.runtime, self.barn)
        self.assertFalse((self.root / "FarmVillage").exists())

    def test_missing_later_source_fails_before_first_copy(self):
        self.files["GodBarn/missing.json"] = dict(next(iter(self.files.values())))
        self.write_manifest()
        with self.assertRaises(ValueError):
            inputs.import_inputs(self.root, self.runtime, self.barn)
        self.assertFalse((self.root / "FarmVillage").exists())

    def test_different_existing_file_is_preserved(self):
        target = self.root / "FarmVillage/fixture.amf"
        target.parent.mkdir()
        target.write_bytes(b"previous")
        with self.assertRaises(ValueError):
            inputs.import_inputs(self.root, self.runtime, self.barn)
        self.assertEqual(target.read_bytes(), b"previous")

    def test_explicit_replace_works(self):
        target = self.root / "FarmVillage/fixture.amf"
        target.parent.mkdir()
        target.write_bytes(b"previous")
        inputs.import_inputs(self.root, self.runtime, self.barn, replace=True)
        self.assertEqual(target.read_bytes(), self.raw)

    def test_source_link_is_refused(self):
        (self.runtime / "fixture.amf").unlink()
        outside = self.base / "outside.amf"
        outside.write_bytes(self.raw)
        (self.runtime / "fixture.amf").symlink_to(outside)
        with self.assertRaises(ValueError):
            inputs.import_inputs(self.root, self.runtime, self.barn)

    def test_destination_parent_link_is_refused(self):
        outside = self.base / "outside"
        outside.mkdir()
        (self.root / "FarmVillage").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            inputs.import_inputs(self.root, self.runtime, self.barn)
        self.assertEqual(list(outside.iterdir()), [])

    def test_source_root_linked_ancestor_is_refused(self):
        link = self.base / "linked-parent"
        link.symlink_to(self.base, target_is_directory=True)
        with self.assertRaises(ValueError):
            inputs.import_inputs(self.root, link / "private-game", self.barn)

    def test_traversal_absolute_and_backslash_paths_are_refused(self):
        info = next(iter(self.files.values()))
        for name in ["FarmVillage/../../outside", "/absolute", "FarmVillage/..\\outside"]:
            with self.subTest(name=name):
                self.files = {name: info}
                self.write_manifest()
                with self.assertRaises(ValueError):
                    inputs.manifest(self.root)

    def test_source_overlap_is_refused(self):
        self.write_manifest(public={"FarmVillage/fixture.amf": {}})
        with self.assertRaises(ValueError):
            inputs.manifest(self.root)

    def test_missing_installed_input_fails_check(self):
        with self.assertRaises(ValueError):
            inputs.check(self.root)

    def test_existing_stage_output_is_preserved(self):
        output = self.base / "release"
        output.mkdir()
        (output / "keep.txt").write_text("previous")
        with self.assertRaises(ValueError):
            stager.prepare(self.root, output)
        self.assertEqual((output / "keep.txt").read_text(), "previous")

    def test_stage_inside_source_is_refused(self):
        with self.assertRaises(ValueError):
            stager.prepare(self.root, self.root / "private-release")
        self.assertFalse((self.root / "private-release").exists())

    def test_stage_linked_root_is_refused(self):
        alias = self.base / "source-alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            stager.prepare(alias, self.base / "release")
        self.assertFalse((self.base / "release").exists())

    def test_stage_linked_output_parent_is_refused(self):
        alias = self.base / "output-alias"
        alias.symlink_to(self.base, target_is_directory=True)
        with self.assertRaises(ValueError):
            stager.prepare(self.root, alias / "release")
        self.assertFalse((self.base / "release").exists())


class SourceIntegrityTests(unittest.TestCase):
    def check_readme(self, text):
        checker = load("handoff_source_checker", "check-source.py")
        with tempfile.TemporaryDirectory(prefix="farmvillage-source-marker-test-") as directory:
            root = Path(directory)
            raw = text.encode()
            (root / "README.md").write_bytes(raw)
            inputs_raw = json.dumps({"files": {}}).encode()
            (root / "PrivateInputs.expected.json").write_bytes(inputs_raw)
            files = {name: {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()} for name, content in {"README.md": raw, "PrivateInputs.expected.json": inputs_raw}.items()}
            (root / "SOURCE_MANIFEST.json").write_text(json.dumps({"source": {}, "files": files}))
            return checker.verify(root)

    def test_sealed_markdown_conflict_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unresolved merge conflict"):
            self.check_readme("<<<<<<< HEAD\n# Local\n=======\n# Remote\n>>>>>>> main\n")

    def test_clean_sealed_markdown_is_accepted(self):
        self.assertEqual(self.check_readme("# Reviewed source\n")["status"], "source-manifest-verified")

if __name__ == "__main__":
    unittest.main()
