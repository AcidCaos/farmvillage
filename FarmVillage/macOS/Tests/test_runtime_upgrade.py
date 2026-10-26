"""Existing prepared profiles receive an offline runtime-only upgrade on Start."""

import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_FILE = ROOT / "macOS/Runtime/bootstrap.py"
SPEC = importlib.util.spec_from_file_location("runtime_upgrade_bootstrap", BOOTSTRAP_FILE)
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


class PreparedRuntimeUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="farmvillage-local-upgrade-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.payload = self.root / "runtime"
        self.payload.mkdir()
        (self.payload / "requirements.txt").write_text("reviewed==1.0\n")
        (self.payload / ".payload-version").write_text("new-payload\n")
        self.data = self.root / "data"
        self.data.mkdir()
        self.preserved = {
            "venv/bin/python": b"preserved existing interpreter",
            "saves/farm.json": b"preserved growing farm",
            "god_barn/state.json": b"preserved God Barn powers",
            "assets/old-art.swf": b"preserved original artwork",
            "cache/item-cache.json": b"preserved catalog cache",
            "ruffle/0.7.1/ruffle.js": b"preserved official release",
        }
        for name, value in self.preserved.items():
            target = self.data / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value)
        self.runtime_id = "0.7.1-farmvillage-fixture1"
        self.bundled = self.payload / "ruffle_runtime" / self.runtime_id
        self.bundled.mkdir(parents=True)
        values = {"ruffle.js": b"new fixture loader", "core.wasm": b"\x00asm\x01\x00\x00\x00"}
        for name, value in values.items():
            (self.bundled / name).write_bytes(value)
        manifest = {"schema": 1, "runtime_id": self.runtime_id, "version": "0.7.1",
                    "upstream_commit": "89a7049965f3090e706265670df309a5128233ac",
                    "files": {name: hashlib.sha256(value).hexdigest() for name, value in values.items()}}
        raw = json.dumps(manifest, sort_keys=True).encode()
        self.manifest_sha = hashlib.sha256(raw).hexdigest()
        (self.bundled / ".farmvillage-ruffle.json").write_bytes(raw)
        helper = (ROOT / "runtime_compatibility.py").read_text()
        assignment = next(node for node in ast.parse(helper).body
                          if (isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
                              and node.target.id == "ACTIVE_RELEASE")
                          or (isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
                              and target.id == "ACTIVE_RELEASE" for target in node.targets)))
        lines = helper.splitlines(keepends=True)
        lines[assignment.lineno - 1:assignment.end_lineno] = [
            "ACTIVE_RELEASE = RuntimeRelease(" + repr(self.runtime_id) + ", '0.7.1', "
            + repr(manifest["upstream_commit"]) + ", " + repr(self.manifest_sha) + ")\n"]
        helper = "".join(lines)
        (self.payload / "runtime_compatibility.py").write_text(helper)
        self.prepared = {"schema": 2, "payload_version": "prior-payload", "ruffle_version": "0.7.1",
                         "requirements_sha256": bootstrap.sha256(self.payload / "requirements.txt"),
                         "python_version": "prior-python", "other_marker": {"preserve": True}}
        self.marker = self.data / "prepared.json"
        self.marker.write_text(json.dumps(self.prepared))
        self.arguments = argparse.Namespace(token="disposable-test", port=5502)
        bootstrap.STOPPING = False
        bootstrap.STOP_REPORTED = False

    def start(self):
        # The single permitted launch is intercepted; runtime installation itself
        # executes through the actual dynamically loaded shared helper.
        with mock.patch.object(bootstrap, "request_url", side_effect=AssertionError("network access forbidden")), \
             mock.patch.object(bootstrap, "install_ruffle", side_effect=AssertionError("official downloader forbidden")), \
             mock.patch.object(bootstrap, "run_owned") as launch:
            bootstrap.start(self.payload, self.data, self.arguments)
            return launch

    def test_existing_profile_migrates_offline_without_recreating_python_or_farm_data(self):
        launch = self.start()
        self.assertEqual(launch.call_count, 1)
        command = launch.call_args.args[0]
        self.assertEqual(command[0], str(self.data / "venv/bin/python"))
        self.assertIn("server_runner.py", command[5])
        self.assertNotIn("pip", command)
        self.assertNotIn("venv", command)
        environment = launch.call_args.kwargs["env"]
        installed = self.data / "ruffle" / self.runtime_id
        self.assertEqual(environment["FARMVILLAGE_RUFFLE_DIR"], str(installed))
        self.assertEqual((installed / "ruffle.js").read_bytes(), b"new fixture loader")
        for name, value in self.preserved.items():
            self.assertEqual((self.data / name).read_bytes(), value, name)
        marker = json.loads(self.marker.read_text())
        self.assertEqual(marker["ruffle_runtime_id"], self.runtime_id)
        self.assertEqual(marker["ruffle_manifest_sha256"], self.manifest_sha)
        self.assertEqual(marker["other_marker"], {"preserve": True})
        self.assertEqual(marker["python_version"], "prior-python")

    def test_repeat_start_reuses_runtime_and_does_not_rewrite_marker(self):
        self.start()
        before = self.marker.stat().st_mtime_ns
        with mock.patch.object(bootstrap, "atomic_json", side_effect=AssertionError("unchanged marker")):
            self.start()
        self.assertEqual(self.marker.stat().st_mtime_ns, before)

    def test_requirements_change_requires_prepare_before_any_runtime_migration(self):
        (self.payload / "requirements.txt").write_text("changed==2\n")
        with mock.patch.object(bootstrap, "compatibility_runtime", side_effect=AssertionError("must not install")), \
             self.assertRaisesRegex(RuntimeError, "Python environment needs preparation"):
            bootstrap.start(self.payload, self.data, self.arguments)
        self.assertEqual(json.loads(self.marker.read_text()), self.prepared)

    def test_corrupt_candidate_never_launches_or_updates_existing_marker(self):
        (self.bundled / "core.wasm").write_bytes(b"changed")
        with mock.patch.object(bootstrap, "run_owned") as launch:
            with self.assertRaisesRegex(ValueError, "reviewed hash"):
                self.start()
        launch.assert_not_called()
        self.assertEqual(json.loads(self.marker.read_text()), self.prepared)
        for name, value in self.preserved.items():
            self.assertEqual((self.data / name).read_bytes(), value, name)


if __name__ == "__main__":
    unittest.main()
