"""Missing old build provenance cannot fabricate current native acceptance."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "Scripts/prepare-portable-release.py"
SPEC = importlib.util.spec_from_file_location("portable_native_history", SCRIPT)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class PortableNativeHistoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="fv-portable-native-history-")
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        self.record = self.project / "macOS/.build/BarnActionsNativeValidation/verification.json"

    def test_clean_checkout_records_unavailable_history_without_claiming_acceptance(self):
        self.assertIsNone(release.historical_native_record(self.project))
        result = release.device_acceptance({}, historical_available=False)
        self.assertFalse(result["historical_native_evidence"]["available"])
        self.assertIsNone(result["historical_native_evidence"]["record"])
        self.assertNotIn("mac_native_wasm_peak", result["historical_native_evidence"])
        self.assertIn("not recorded", result["current_payload"]["scope"])
        self.assertEqual(result["physical_ipad"], "Not tested")

    def test_existing_historical_record_is_preserved_and_remains_historical(self):
        self.record.parent.mkdir(parents=True)
        self.record.write_text('{"historical":true}')
        self.assertEqual(release.historical_native_record(self.project), self.record)
        result = release.device_acceptance({"current_validation": {"scope": "Browser only"}})
        self.assertTrue(result["historical_native_evidence"]["available"])
        self.assertIn("not a measurement or acceptance of the current payload",
                      result["historical_native_evidence"]["scope"])
        self.assertEqual(result["current_payload"], {"scope": "Browser only"})

    def test_explicit_missing_history_fails_instead_of_silently_substituting(self):
        with self.assertRaisesRegex(ValueError, "selected.*missing"):
            release.historical_native_record(self.project, self.project / "selected.json")

    def test_explicit_omission_does_not_adopt_unrelated_old_build_history(self):
        self.record.parent.mkdir(parents=True)
        original = b'{"historical":"different release"}'
        self.record.write_bytes(original)
        self.assertIsNone(release.historical_native_record(self.project, omit=True))
        self.assertEqual(self.record.read_bytes(), original)
        self.assertFalse(release.device_acceptance({}, historical_available=False)
                         ["historical_native_evidence"]["available"])

    def test_selecting_and_omitting_history_together_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "both selected and omitted"):
            release.historical_native_record(self.project, self.project / "selected.json", omit=True)

    def test_history_links_and_nonfiles_are_rejected(self):
        self.record.parent.mkdir(parents=True)
        target = self.project / "actual.json"
        target.write_text("{}")
        self.record.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "ordinary file"):
            release.historical_native_record(self.project)
        self.record.unlink()
        self.record.mkdir()
        with self.assertRaisesRegex(ValueError, "ordinary file"):
            release.historical_native_record(self.project)


if __name__ == "__main__":
    unittest.main()
