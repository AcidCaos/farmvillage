"""Exercise complete catalog discovery and honest artwork rendering in JavaScript."""

from pathlib import Path
import shutil
import subprocess
import sys
import unittest


class CatalogJavaScriptTests(unittest.TestCase):
    def test_catalog_discovery_and_artwork_contract(self):
        executable = shutil.which("node")
        if not executable:
            candidate = Path(sys.executable).resolve().parents[2] / "node/bin/node"
            if candidate.is_file():
                executable = str(candidate)
        if not executable:
            self.skipTest("Node.js is required for the catalog interface contract tests.")
        result = subprocess.run(
            [executable, "--test", str(Path(__file__).with_name("catalog_ui.test.cjs"))],
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertRegex(result.stdout, r"(?:#|ℹ) pass 14")


if __name__ == "__main__":
    unittest.main()
