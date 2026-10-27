"""Portable metadata describes the staged roster, not an invented AMF measurement."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT / "macOS/Scripts/prepare-portable-release.py"
SPEC = importlib.util.spec_from_file_location("portable_mastery_policy", SCRIPT)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class PortableMasteryPolicyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="fv-portable-mastery-policy-")
        self.addCleanup(temporary.cleanup)
        self.payload = Path(temporary.name)
        self.source = self.payload / "mastery_signs.py"

    def write(self, preserved, glen, definitions=None):
        union = "PRESERVED_GIFTS | GLEN_GIFTS" if definitions is None else definitions
        self.source.write_text(f"PRESERVED_GIFTS = {preserved}\nGLEN_GIFTS = {glen}\n"
                               f"DEFINITION_GIFTS = {union}\n")

    def test_current_staged_policy_records_both_preserved_and_glen_definitions(self):
        original = (PROJECT / "mastery_signs.py").read_bytes()
        self.source.write_bytes(original)
        result = release.mastery_definition_policy(self.payload)
        self.assertEqual((result["preserved_pairs"], result["glen_pairs"], result["eligible_pairs"]),
                         (155, 12, 167))
        self.assertEqual(result["source_sha256"], hashlib.sha256(original).hexdigest())
        self.assertIn("actual derived AMF rows are not measured", result["scope"])
        self.assertEqual(self.source.read_bytes(), original)

    def test_roster_is_taken_from_the_payload_and_is_not_a_fixed_record_count(self):
        self.write("frozenset({('legacy', 'a')})",
                   "frozenset({('glen1', 'b'), ('glen2', 'c')})")
        result = release.mastery_definition_policy(self.payload)
        self.assertEqual((result["preserved_pairs"], result["glen_pairs"], result["eligible_pairs"]),
                         (1, 2, 3))
        self.write("frozenset({('legacy', 'a')})", "frozenset()")
        self.assertEqual(release.mastery_definition_policy(self.payload)["eligible_pairs"], 1)

    def test_invalid_or_conflicting_rosters_are_rejected(self):
        cases = [
            ("set({('legacy', 'a')})", "frozenset()", None),
            ("frozenset({('legacy', '')})", "frozenset()", None),
            ("frozenset({('legacy', 'a')})", "frozenset({('legacy', 'b')})", None),
            ("frozenset({('legacy', 'a')})", "frozenset({('legacy', 'a')})", None),
            ("frozenset({('legacy', 'a')})", "frozenset({('glen', 'b')})", "PRESERVED_GIFTS"),
            ("frozenset()", "frozenset()", None),
        ]
        for preserved, glen, definitions in cases:
            with self.subTest(preserved=preserved, glen=glen, definitions=definitions):
                self.write(preserved, glen, definitions)
                with self.assertRaises(ValueError):
                    release.mastery_definition_policy(self.payload)

    def test_missing_and_linked_policy_sources_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "ordinary staged source"):
            release.mastery_definition_policy(self.payload)
        target = self.payload / "other.py"
        target.write_text("raise AssertionError('must not execute a linked file')\n")
        self.source.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "ordinary staged source"):
            release.mastery_definition_policy(self.payload)


if __name__ == "__main__":
    unittest.main()
