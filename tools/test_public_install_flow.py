"""Mocked clean-clone install flow: tiny original archives, no network or builds."""
from __future__ import annotations

import collections
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pipeline = load("test_install_resource_pipeline", ROOT / "tools/resource_pipeline.py")
fixtures = load("test_install_runtime_fixtures", ROOT / "tools/test_public_ruffle.py")


def sha(value):
    return hashlib.sha256(value).hexdigest()


def tiny_warc():
    records = []
    for name in ("Environment/fixture.png", "xpromoSupport/fixture.png"):
        body = ("synthetic-art:" + name).encode()
        http = b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
        records.append(b"WARC/1.0\r\nWARC-Type: response\r\nWARC-Target-URI: https://zynga1-a.akamaihd.net/farmville/assets/hashed/assets/" + name.encode()
                       + b"\r\nContent-Length: " + str(len(http)).encode() + b"\r\n\r\n" + http + b"\r\n\r\n")
    return gzip.compress(b"".join(records))


class PublicInstallFlowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="fv-install-flow-fixture-")
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / "source"
        self.pack = self.root / "resources"
        self.game = self.source / "FarmVillage"
        (self.source / "tools").mkdir(parents=True)
        self.game.mkdir()
        self.commands = []
        self.downloads = []
        self.originals = {
            "embeds/Flash/v855097-855094/FarmGame.swf": b"synthetic original game",
            "patched/FV_Preloader_mod.swf": b"synthetic original preloader",
            "xml/gz/v855098/gameSettings.xml.gz": gzip.compress(b"<fixture/>"),
        }
        self.archive = tiny_warc()
        self.specification = {"schema": 1, "upstream": {"revision": "1" * 40,
            "files": [{"path": name, "bytes": len(value), "sha256": sha(value)} for name, value in self.originals.items()]},
            "archiveBase": "https://example.invalid/original-archives/",
            "archives": [{"name": "fixture-%d.warc.gz" % number, "bytes": len(self.archive), "sha256": sha(self.archive)} for number in range(4)]}
        (self.source / "tools/public-resources.json").write_text(json.dumps(self.specification))
        (self.source / "SOURCE_MANIFEST.json").write_text('{"synthetic-source-fixture":true}\n')
        (self.game / "server.py").write_text("# synthetic server, never executed\n")
        for name in ("requirements.txt", "LICENSE", "FLASH.md", "README.md"):
            (self.game / name).write_text("synthetic fixture\n")
        (self.game / "templates").mkdir()
        (self.game / "templates/index.html").write_text("synthetic source template")
        shutil.copyfile(ROOT / "FarmVillage/runtime_compatibility.py", self.game / "runtime_compatibility.py")
        provenance = self.source / "tools/public-ruffle-build"
        provenance.mkdir(parents=True)
        for name in fixtures.compat.PUBLIC_SOURCE_INPUTS:
            if name != "toolchain-pins.json":
                shutil.copyfile(fixtures.builder.PUBLIC_BUILD_INPUTS / name, provenance / name)
        shutil.copyfile(fixtures.builder.PINS_PATH, self.source / "tools/public-ruffle-toolchains.json")
        self.patches = [mock.patch.object(pipeline, "ROOT", self.source),
                        mock.patch.object(pipeline, "download", side_effect=self.download),
                        mock.patch.object(pipeline, "run", side_effect=self.mock_command),
                        mock.patch.object(pipeline.shutil, "disk_usage", return_value=collections.namedtuple("usage", "total used free")(400 * pipeline.GIB, 0, 400 * pipeline.GIB))]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        for patch in reversed(self.patches):
            patch.stop()
        self.temporary.cleanup()

    def download(self, url, destination, entry):
        self.assertTrue(url.startswith("https://"))
        self.assertTrue(destination.is_relative_to(self.pack))
        value = self.originals[entry["path"]] if "path" in entry else self.archive
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(value)
        self.assertTrue(pipeline.identity(destination, entry))
        self.downloads.append(url)
        return destination

    def mock_command(self, command, pack, **kwargs):
        command = [str(value) for value in command]
        self.commands.append(command)
        self.assertEqual(pack, self.pack)
        if "venv" in command:
            python = Path(command[-1]) / "bin/python"
            python.parent.mkdir(parents=True)
            python.write_text("synthetic-python-never-executed")
        elif any(value.endswith("bootstrap_resources.py") for value in command):
            output = Path(command[command.index("--output") + 1])
            output.mkdir()
            (output / "catalog.json").write_text('{"synthetic":true}')
        elif any(value.endswith("verify_resources.py") for value in command):
            self.assertEqual(command[command.index("--expected-records") + 1], "111206")
            self.assertTrue(Path(command[command.index("--resources") + 1]).is_dir())
        elif any(value.endswith("patch-game-client.py") for value in command):
            original, patched = Path(command[-2]), Path(command[-1])
            self.assertTrue(original.is_relative_to(self.pack / "original"))
            self.assertTrue(patched.is_relative_to(self.pack / "Runtime"))
            patched.write_bytes(b"patched-fixture:" + original.read_bytes())
        elif any(value.endswith("bundle_companion.py") for value in command):
            index = next(index for index, value in enumerate(command) if value.endswith("bundle_companion.py"))
            output = Path(command[index + 2])
            output.mkdir()
            (output / "companion.html").write_text("synthetic companion")
        elif any(value.endswith("build-public-ruffle.py") for value in command):
            output = Path(command[command.index("--output") + 1])
            if not output.exists():
                files = fixtures.write_fixture(output)
                receipt = output.with_name(output.name + ".build-receipt.json")
                receipt.write_text(json.dumps(fixtures.fixture_receipt(files), sort_keys=True) + "\n")
        elif any(value.endswith("native_resources.py") for value in command):
            native = self.pack / "native"
            native.mkdir()
            (native / "native-fixture.json").write_text('{"synthetic":true}')
        elif "pip" not in command:
            self.fail("Unexpected command in mocked install: " + repr(command))

    def install(self, audience):
        return pipeline.setup(self.pack, audience, self.source)

    def test_server_clean_install_fetches_extracts_builds_and_seals(self):
        self.assertEqual(self.install("server"), self.pack)
        self.assertEqual(len(self.downloads), 7)
        self.assertFalse(list((self.pack / "downloads").glob("*.warc.gz")))
        self.assertEqual(json.loads((self.pack / "archive-receipts.json").read_text()).keys(),
                         {entry["name"] for entry in self.specification["archives"]})
        self.assertEqual((self.pack / "Runtime/templates/index.html").read_text(), "synthetic source template")
        self.assertTrue((self.pack / "Runtime/embeds/Flash/v855097-855094/FarmGame.swf").read_bytes().startswith(b"patched-fixture:"))
        self.assertTrue((self.pack / "Runtime/GodBarn/companion.html").is_file())
        self.assertTrue((self.pack / "Runtime/PUBLIC_RUNTIME_BUILD.json").is_file())
        self.assertEqual((self.pack / "Runtime/README.md").read_text(), "synthetic fixture\n")
        prepared = json.loads((self.pack / "Runtime/PREPARED_RUNTIME.json").read_text())
        release = fixtures.compat.select_runtime_release(self.pack / "Runtime", prepared_pin_sha256=prepared["runtime_manifest_sha256"])
        self.assertNotEqual(release.manifest_sha256, fixtures.compat.ACTIVE_RELEASE.manifest_sha256)
        state = pipeline.check_pack(self.pack)
        self.assertEqual(state["audience"], "server")
        self.assertEqual(state["active_worlds"], 16)
        self.assertEqual(state["retired_worlds"], ["glen", "hlights"])
        self.assertIn("Runtime/PREPARED_RUNTIME.json", state["files"])
        self.assertNotIn("native/native-fixture.json", state["files"])

    def test_mac_install_seals_native_inputs_and_external_art_location(self):
        self.install("mac")
        state = pipeline.check_pack(self.pack)
        self.assertEqual(state["audience"], "mac")
        self.assertIn("native/native-fixture.json", state["files"])
        location = json.loads((self.pack / "Runtime/PUBLIC_INSTALL.json").read_text())
        self.assertEqual(location, {"schema": 1, "assets_root": str(self.pack / "assets")})
        self.assertTrue(any(any(value.endswith("native_resources.py") for value in command) for command in self.commands))

    def test_verified_complete_pack_resumes_without_commands_or_downloads(self):
        self.install("server")
        counts = len(self.downloads), len(self.commands)
        self.install("server")
        self.assertEqual((len(self.downloads), len(self.commands)), counts)

    def test_tampered_prepared_pin_or_artwork_invalidates_pack(self):
        self.install("server")
        prepared = self.pack / "Runtime/PREPARED_RUNTIME.json"
        original = prepared.read_bytes()
        prepared.write_text('{"schema":1,"runtime_manifest_sha256":"forged"}')
        with self.assertRaises(ValueError):
            pipeline.check_pack(self.pack)
        prepared.write_bytes(original)
        (self.pack / "assets/Environment/fixture.png").write_text("changed")
        with self.assertRaises(ValueError):
            pipeline.check_pack(self.pack)

    def test_failed_build_cannot_publish_complete_seal(self):
        original_run = self.mock_command
        def fail_build(command, pack, **kwargs):
            if any(str(value).endswith("build-public-ruffle.py") for value in command):
                raise RuntimeError("synthetic compiler failure")
            return original_run(command, pack, **kwargs)
        with mock.patch.object(pipeline, "run", side_effect=fail_build), self.assertRaisesRegex(RuntimeError, "compiler failure"):
            self.install("server")
        self.assertFalse((self.pack / "resource-state.json").exists())
        self.assertFalse((self.pack / "Runtime/PREPARED_RUNTIME.json").exists())


if __name__ == "__main__":
    unittest.main()
