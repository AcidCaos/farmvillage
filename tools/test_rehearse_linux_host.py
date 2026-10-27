"""The Ubuntu rehearsal tool and its run sheet must stay honest and in step with the code.

Source-only. The rehearsal runs the real host runner on loopback against a stub game, so
it is skipped as UNRUN where a host cannot run it. Nothing here is a Bifrost install, a
wizard run or gameplay. Sabotaged copies of the runner prove the tool can fail.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/rehearse-linux-host.py"
SHEET = ROOT / "docs/UBUNTU_ACCEPTANCE.md"
LINUX_DIR = ROOT / "FarmVillage/portable/Linux"
NATIVE_PATHS = ROOT / "FarmVillage/macOS/Runtime/native_paths.py"

EXPECTED_CHECKS = [
    "init-only-on-a-real-tty", "password-not-echoed", "credential-files-private", "password-stored-as-a-salted-hash",
    "init-only-starts-no-game-and-saves-nothing", "seven-character-password-refused", "service-style-start-listens-on-loopback",
    "unauthenticated-game-route-refused", "unauthenticated-root-redirects-to-sign-in", "wrong-host-header-refused",
    "wrong-password-refused", "correct-password-signs-in", "signed-in-cookie-reaches-the-game",
    "runner-sets-data-dir-and-runs-from-runtime", "post-without-origin-or-referer-fenced", "post-from-another-origin-fenced",
    "same-origin-post-saves-into-the-data-folder", "arbitrary-url-proxy-disabled", "second-server-on-same-data-folder-refused",
    "wildcard-bind-refused", "public-address-bind-refused", "repeated-wrong-passwords-are-throttled",
    "sigterm-lets-an-in-flight-save-finish-then-exits-zero", "restart-on-the-same-data-folder", "sign-in-cookie-survives-restart",
    "saved-state-survives-restart", "set-password-on-a-tty", "old-cookie-revoked-after-rotation",
    "old-password-fails-and-new-password-works", "final-stop-is-clean", "no-process-from-this-run-is-left-alive",
]

# (name, text to find exactly once in server_runner.py, replacement, checks that must then FAIL)
SABOTAGE = [
    ("sign-in-gate-removed", "if not session.get(AUTH_KEY):", "if False:",
     {"unauthenticated-game-route-refused", "unauthenticated-root-redirects-to-sign-in"}),
    ("origin-fence-removed", "if supplied_origin != origin and not referred:", "if False:",
     {"post-without-origin-or-referer-fenced"}),
    ("password-minimum-lowered", "len(password) < 8", "len(password) < 3",
     {"seven-character-password-refused"}),
    ("shutdown-no-longer-drains", "httpd.daemon_threads = False", "httpd.daemon_threads = True",
     {"sigterm-lets-an-in-flight-save-finish-then-exits-zero"}),
]


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def mirror(destination: Path):
    """A minimal source tree the rehearsal accepts: the Linux host files plus native_paths."""
    target = destination / "FarmVillage/portable/Linux"
    target.mkdir(parents=True)
    for source in LINUX_DIR.glob("*"):
        if source.is_file() and not source.name.startswith("test_"):
            shutil.copyfile(source, target / source.name)
    (destination / "FarmVillage/macOS/Runtime").mkdir(parents=True)
    shutil.copyfile(NATIVE_PATHS, destination / "FarmVillage/macOS/Runtime/native_paths.py")
    return destination


def run_tool(repo: Path, receipt: Path):
    done = subprocess.run([sys.executable, "-I", "-B", str(TOOL), "--repo", str(repo), "--receipt", str(receipt)],
                          capture_output=True, text=True, timeout=180)
    document = json.loads(receipt.read_text()) if receipt.exists() else None
    return done.returncode, done.stdout, document


class RehearsalToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="fv-rehearsal-test-")
        cls.addClassCleanup(cls.temporary.cleanup)
        base = Path(cls.temporary.name).resolve()
        jobs = {"clean": None}
        for name, find, replace, _ in SABOTAGE:
            copy = mirror(base / name)
            runner = copy / "FarmVillage/portable/Linux/server_runner.py"
            text = runner.read_text()
            if text.count(find) != 1:
                raise AssertionError(f"Sabotage '{name}': expected exactly one '{find}' in server_runner.py, found {text.count(find)}. "
                                     "The runner changed; update SABOTAGE in this test.")
            runner.write_text(text.replace(find, replace))
            jobs[name] = copy
        jobs["clean"] = mirror(base / "clean")
        (base / "receipts").mkdir()
        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            futures = {name: pool.submit(run_tool, repo, base / "receipts" / (name + ".json")) for name, repo in jobs.items()}
            cls.runs = {name: future.result() for name, future in futures.items()}
        if cls.runs["clean"][0] == 2:
            raise unittest.SkipTest("UNRUN: " + cls.runs["clean"][1].strip().splitlines()[-1])

    def test_clean_runner_passes_every_check_and_the_tool_labels_itself(self):
        code, output, document = self.runs["clean"]
        self.assertEqual(code, 0, output[-800:])
        self.assertEqual([item["check"] for item in document["checks"]], EXPECTED_CHECKS)
        self.assertEqual((document["failed"], document["passed"]), (0, len(EXPECTED_CHECKS)))
        lines = output.splitlines()
        summary = next(line for line in lines if line.startswith("%d PASS" % document["passed"]))
        for line in (lines[0], summary):
            self.assertIn("NOT a Bifrost install", line)
            self.assertIn("NOT gameplay", line)
        self.assertIn("Not a Bifrost install", document["scope"])
        self.assertTrue(document["notBifrostInstall"] and document["notGameplay"])

    def test_every_sabotage_is_detected_and_named(self):
        for name, _, _, must_fail in SABOTAGE:
            with self.subTest(name):
                code, output, document = self.runs[name]
                failed = {item["check"] for item in document["checks"] if item["result"] == "FAIL"}
                self.assertEqual(code, 1, output[-600:])
                self.assertTrue(must_fail <= failed, f"expected {sorted(must_fail)} to fail, got {sorted(failed)}")
                self.assertIn("FAIL", output)

    def test_receipt_is_refused_inside_the_source_tree_and_never_overwritten(self):
        with tempfile.TemporaryDirectory(prefix="fv-rehearsal-test-") as directory:
            existing = Path(directory) / "already.json"
            existing.write_text("keep me")
            for receipt in (ROOT / "should-not-exist.json", existing):
                done = subprocess.run([sys.executable, "-I", "-B", str(TOOL), "--receipt", str(receipt)],
                                      capture_output=True, text=True, timeout=60)
                self.assertEqual(done.returncode, 2, done.stdout)
                self.assertIn("UNRUN", done.stdout)
            self.assertEqual(existing.read_text(), "keep me")
            self.assertFalse((ROOT / "should-not-exist.json").exists())


class RunSheetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sheet = SHEET.read_text(encoding="utf-8")
        cls.wizard = load_module(ROOT / "tools/setup-wizard.py", "sheet_wizard")

    def snippet(self, name):
        found = re.search(r"```sh %s\n(.*?)\n```" % name, self.sheet, re.S)
        self.assertIsNotNone(found, "the sheet lost its '%s' block" % name)
        return found.group(1)

    def run_snippet(self, name, target):
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "T": str(target)}
        return subprocess.run(["bash", "-c", self.snippet(name)], env=env, capture_output=True, text=True, timeout=30)

    def test_evidence_rows_are_consecutive_unrun_and_match_the_ledger(self):
        rows = re.findall(r"^\| (E\d\d) \|.*\| (\w[\w ]*) \| *\|$", self.sheet, re.M)
        self.assertEqual([row[0] for row in rows], ["E%02d" % n for n in range(1, len(rows) + 1)])
        self.assertGreaterEqual(len(rows), 20)
        self.assertEqual({row[1] for row in rows}, {"UNRUN"}, "the committed sheet must not pre-fill a PASS or FAIL")
        ledger = self.sheet[self.sheet.index("## Results ledger"):]
        self.assertEqual(re.findall(r"E\d\d", ledger), [row[0] for row in rows])

    def test_step_references_stay_within_the_wizard_steps(self):
        total = max(int(n) for n in re.findall(r"say\((\d+),", (ROOT / "tools/setup-wizard.py").read_text()))
        mentioned = [int(n) for n in re.findall(r"\bstep (\d+)\b", self.sheet, re.I)]
        self.assertTrue(mentioned)
        self.assertTrue(all(1 <= n <= total for n in mentioned), mentioned)
        self.assertIn("step 1 of 8" if total == 8 else "step 1 of %d" % total, self.sheet)

    def release(self, base, files):
        release = base / "release"
        manifest = {"schema": 1, "files": {}}
        for name, raw in files.items():
            path = release / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            manifest["files"][name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        (release / "PRIVATE_RELEASE_MANIFEST.json").write_text(json.dumps(manifest))
        return release

    def test_identity_check_agrees_with_the_wizards_own_verification(self):
        files = {"Runtime/server.py": b"server", "BackendHost/native_paths.py": b"paths", "hosting/server_runner.py": b"runner", "Runtime/extra.bin": b"x" * 40}
        with tempfile.TemporaryDirectory(prefix="fv-sheet-test-") as directory:
            target = Path(directory).resolve()
            release = self.release(target, files)
            done = self.run_snippet("identity-check", target)
            self.assertEqual((done.returncode, done.stdout.strip()), (0, "4 files match the release manifest"), done.stderr)
            self.wizard.verify_payload(release)
            for label, damage in (("changed byte", lambda: (release / "Runtime/extra.bin").write_bytes(b"y" * 40)),
                                  ("changed size", lambda: (release / "Runtime/extra.bin").write_bytes(b"y" * 41)),
                                  ("missing file", lambda: (release / "Runtime/extra.bin").unlink())):
                with self.subTest(label):
                    damage()
                    done = self.run_snippet("identity-check", target)
                    self.assertEqual(done.returncode, 1, done.stdout)
                    self.assertIn("Runtime/extra.bin", done.stdout)
                    with self.assertRaises(self.wizard.SetupError):
                        self.wizard.verify_payload(release)
                    (release / "Runtime/extra.bin").write_bytes(b"x" * 40)

    def test_rotation_command_is_the_wizards_start_command_plus_the_two_flags(self):
        with tempfile.TemporaryDirectory(prefix="fv-sheet-test-") as directory:
            target = Path(directory).resolve() / "farmvillage-server"
            target.mkdir()
            marker = {"bind": "192.168.50.80", "port": 5601, "origin": "http://192.168.50.80:5601"}
            (target / self.wizard.MARKER).write_text(json.dumps(marker))
            done = self.run_snippet("rotation-command", target)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(shlex.split(done.stdout), self.wizard.command_for(target, marker) + ["--init-only", "--set-password"])


if __name__ == "__main__":
    unittest.main()
