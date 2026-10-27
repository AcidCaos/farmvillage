"""Exercise the Not in Market tab, its origin chips, and gift reasons in JavaScript."""

from pathlib import Path
import shutil
import subprocess
import sys
import unittest


class UntabbedJavaScriptTests(unittest.TestCase):
    def test_untabbed_tab_contract(self):
        executable = shutil.which("node")
        if not executable:
            candidate = Path(sys.executable).resolve().parents[2] / "node/bin/node"
            if candidate.is_file():
                executable = str(candidate)
        if not executable:
            self.skipTest("Node.js is required for the Not in Market interface contract tests.")
        result = subprocess.run(
            [executable, "--test", str(Path(__file__).with_name("untabbed_ui.test.cjs"))],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertRegex(result.stdout, r"(?:#|ℹ) pass 6")


if __name__ == "__main__":
    unittest.main()
