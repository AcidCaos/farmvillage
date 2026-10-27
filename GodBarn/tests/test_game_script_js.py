"""Exercise the emitted browser transport observer with real JavaScript promises."""

from pathlib import Path
import shutil
import subprocess
import sys
import unittest

from GodBarn.integration import _game_script


class GameScriptJavaScriptTests(unittest.TestCase):
    def test_gateway_observer_preserves_transport_and_consumer_timing(self):
        executable = shutil.which("node")
        if not executable:
            candidate = Path(sys.executable).resolve().parents[2] / "node/bin/node"
            if candidate.is_file():
                executable = str(candidate)
        if not executable:
            self.skipTest("Node.js is required for the browser observer contract tests.")
        emitted = _game_script("observer-test-epoch")
        script = emitted[emitted.index(">") + 1:emitted.rindex("</script>")]
        result = subprocess.run([executable, str(Path(__file__).with_name("game_script_observer.test.cjs"))],
                                input=script, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertRegex(result.stdout, r"(?:#|ℹ) pass 9")


if __name__ == "__main__":
    unittest.main()
