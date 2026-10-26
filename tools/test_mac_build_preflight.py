"""Synthetic Mac build gate tests; every compiler invocation is an owned stub."""

import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RESOURCE_FILES = (
    "FarmVillage/assethash/v9/assethash.master.amf.gz",
    "FarmVillage/embeds/Flash/v855097-855094/FarmGame.swf",
    "FarmVillage/embeds/Flash/v855097-855094/FV_Preloader.swf",
    "FarmVillage/xml/gz/v855098/FarmConfig.swf",
    "FarmVillage/ruffle_runtime/0.7.1-farmvillage-gc1/ruffle.js",
    "FarmVillage/ruffle_runtime/0.7.1-farmvillage-gc1/50c5ac40cece24645a25.wasm",
    "GodBarn/data/catalog.json",
    "GodBarn/data/ui-assets.json",
    "FarmVillage/macOS/Resources/Heritage/manifest.json",
    "FarmVillage/macOS/Resources/Heritage/farmville-logo.png",
    "FarmVillage/macOS/Resources/Assets.xcassets/AppIcon.appiconset/icon_512x512.png",
    # This is deliberately beyond the fast sentinel set: all manifest entries
    # must pass the real verifier before the compiler can be invoked.
    "GodBarn/data/progression.json",
)


class MacBuildPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="fv-mac-build-gate-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "source checkout"
        self.project = self.root / "FarmVillage/macOS"
        self.script = self.project / "Scripts/build.sh"
        self.script.parent.mkdir(parents=True)
        self.compiler_log = self.base / "compiler-arguments.txt"
        self.python_log = self.base / "python-invoked.txt"
        self.compiler_stub = self.base / "compiler-stub"
        self.compiler_stub.write_text(
            "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$FARMVILLAGE_TEST_COMPILER_LOG\"\n"
        )
        self.compiler_stub.chmod(0o755)
        self.metadata_stub = self.base / "xcode-select-stub"
        self.metadata_stub.write_text("#!/bin/sh\nexit 1\n")
        self.metadata_stub.chmod(0o755)
        # Besides the supported override, replace hardcoded Apple tool paths in
        # the fixture copy. A broken gate can invoke only our stub or fail; it
        # cannot invoke a real compiler or developer-tool installation shim.
        source = (ROOT / "FarmVillage/macOS/Scripts/build.sh").read_text()
        source = source.replace("/usr/bin/xcodebuild", str(self.compiler_stub))
        source = source.replace("/usr/bin/xcode-select", str(self.metadata_stub))
        self.script.write_text(source)
        tools = self.root / "tools"
        tools.mkdir()
        shutil.copyfile(ROOT / "tools/private-inputs.py", tools / "private-inputs.py")
        (self.root / "SOURCE_MANIFEST.json").write_text(json.dumps({"files": {}}))
        self.environment = {
            "PATH": "/usr/bin:/bin",
            "FARMVILLAGE_BUILD_PYTHON": sys.executable,
            "FARMVILLAGE_XCODEBUILD": str(self.compiler_stub),
            "FARMVILLAGE_TEST_COMPILER_LOG": str(self.compiler_log),
        }

    def prepare_resources(self):
        files = {}
        for name in RESOURCE_FILES:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = ("synthetic resource: " + name + "\n").encode()
            path.write_bytes(raw)
            files[name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        (self.root / "PrivateInputs.expected.json").write_text(
            json.dumps({"schema": 1, "files": files})
        )

    def run_build(self):
        return subprocess.run(
            ["/bin/bash", str(self.script), "Release"],
            cwd=self.root,
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=15,
        )

    def test_source_clone_stops_before_python_compiler_or_build_writes(self):
        python_stub = self.base / "python-must-not-run"
        python_stub.write_text(
            "#!/bin/sh\nprintf called > " + shlex.quote(str(self.python_log)) + "\nexit 91\n"
        )
        python_stub.chmod(0o755)
        self.environment["FARMVILLAGE_BUILD_PYTHON"] = str(python_stub)
        result = self.run_build()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("PLAY_ON_MAC.md", result.stderr)
        self.assertIn("installation guide", result.stderr)
        self.assertIn("No Python setup, compilation or game-resource download", result.stderr)
        self.assertFalse(self.python_log.exists())
        self.assertFalse(self.compiler_log.exists())
        self.assertFalse((self.project / ".build").exists())

    def test_manifest_mismatch_beyond_sentinels_blocks_compilation(self):
        self.prepare_resources()
        path = self.root / "GodBarn/data/progression.json"
        original = path.read_bytes()
        path.write_bytes(b"X" + original[1:])
        result = self.run_build()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("Prepared-resource verification failed", result.stderr)
        self.assertIn("PLAY_ON_MAC.md", result.stderr)
        self.assertFalse(self.compiler_log.exists())
        self.assertFalse((self.project / ".build").exists())

    def test_complete_matching_resources_reach_only_stub_with_build_arguments(self):
        self.prepare_resources()
        result = self.run_build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.compiler_log.read_text().splitlines(),
            [
                "-project", str(self.project / "FarmVillage.xcodeproj"),
                "-scheme", "FarmVillage",
                "-configuration", "Release",
                "-destination", "platform=macOS",
                "-derivedDataPath", str(self.project / ".build/DerivedData"),
                "CODE_SIGNING_ALLOWED=NO", "build",
            ],
        )
        self.assertIn("all-private-inputs-match", result.stdout)
        self.assertFalse((self.project / ".build").exists())


if __name__ == "__main__":
    unittest.main()
