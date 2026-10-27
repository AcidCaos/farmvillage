"""Small synthetic tests. Never download toolchains, clone Ruffle or compile it."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import os
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


compat = module("test_public_runtime_compatibility", ROOT / "FarmVillage/runtime_compatibility.py")
builder = module("test_public_runtime_builder", ROOT / "tools/build-public-ruffle.py")
PINS = json.loads(builder.PINS_PATH.read_text())
bootstrap = module("test_public_runtime_bootstrap", ROOT / "FarmVillage/macOS/Runtime/bootstrap.py")


def write_fixture(directory):
    directory.mkdir(parents=True)
    names = {"LICENSE_APACHE", "LICENSE_MIT", "README.md", "package.json", "ruffle.js", "ruffle.js.map"}
    for number in ("1", "2"):
        names.add(number * 20 + ".wasm")
        names.add("core.ruffle." + number * 20 + ".js")
        names.add("core.ruffle." + number * 20 + ".js.map")
    for name in names:
        contents = b"\0asm\x01\0\0\0" if name.endswith(".wasm") else (name + "\n").encode()
        if name == "package.json":
            contents = json.dumps({"version": builder.RUNTIME_ID, "upstreamVersion": "0.7.1"}).encode()
        (directory / name).write_bytes(contents)
    return {name: builder.digest(directory / name) for name in names}


def fixture_receipt(files, host="x86_64-unknown-linux-gnu"):
    node_host = "linux-x64" if host == "x86_64-unknown-linux-gnu" else "darwin-arm64"
    artifacts = builder.toolchain_artifacts(PINS, host, node_host)
    return {"schema": 1, "kind": compat.PUBLIC_RECEIPT_KIND, "upstream_commit": builder.COMMIT,
            "runtime_id": builder.RUNTIME_ID, "host": host, "compiler": "clang version synthetic-fixture",
            "tool_versions": {"rust": "rustc 1.99.1 (synthetic)", "node": "v24.19.0", "npm": "11.0.0", "wasm_bindgen": "wasm-bindgen 0.2.127"},
            "source_inputs": dict(compat.PUBLIC_SOURCE_INPUTS),
            "source_state": "clean-pinned-checkout-plus-reviewed-gc-patch", "submodules": [],
            "artifacts": [{key: entry[key] for key in ("name", "url", "sha256", "sha512") if key in entry} for entry in artifacts],
            "files": files, "gameplay_acceptance": False}


class PublicRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="fv-player-fixture-")
        self.root = Path(self.temporary.name).resolve()
        self.payload = self.root / "Runtime"
        self.player = self.payload / "ruffle_runtime" / builder.RUNTIME_ID
        self.files = write_fixture(self.player)
        self.receipt = fixture_receipt(self.files)
        self.receipt_path = self.root / "receipt.json"
        self.pin_receipt()

    def tearDown(self):
        self.temporary.cleanup()

    def pin_receipt(self):
        builder.atomic_json(self.receipt_path, self.receipt)
        self.receipt_pin = builder.digest(self.receipt_path)

    def seal(self):
        return compat.prepare_public_runtime(self.payload, self.receipt_path, receipt_sha256=self.receipt_pin)

    def test_real_source_contract_files_match_pins(self):
        compat.verify_public_build_inputs(builder.PUBLIC_BUILD_INPUTS, builder.PINS_PATH)

    def test_explicit_source_build_pin_required_and_installs_offline(self):
        pin = self.seal()
        release = compat.select_runtime_release(self.payload, prepared_pin_sha256=pin)
        self.assertEqual(release.manifest_sha256, pin)
        self.assertEqual(compat.select_runtime_release(self.payload), compat.ACTIVE_RELEASE)
        with self.assertRaises(compat.RuntimeIntegrityError):
            compat.verify_runtime(self.player)
        data = self.root / "data"
        data.mkdir()
        destination = compat.install_runtime(self.payload, data, release)
        self.assertEqual(compat.verify_runtime(destination, release).files["ruffle.js"], self.files["ruffle.js"])

    def test_linux_and_mac_local_outputs_can_have_distinct_pins(self):
        linux_pin = self.seal()
        self.receipt["host"] = "aarch64-apple-darwin"
        self.receipt["artifacts"] = fixture_receipt(self.files, "aarch64-apple-darwin")["artifacts"]
        self.pin_receipt()
        mac_pin = self.seal()
        self.assertNotEqual(linux_pin, mac_pin)

    def test_wrong_or_missing_receipt_hash_rejected(self):
        for pin in (None, "", "f" * 64):
            with self.subTest(pin=pin), self.assertRaises(compat.RuntimeIntegrityError):
                compat.prepare_public_runtime(self.payload, self.receipt_path, receipt_sha256=pin)

    def test_pinned_receipt_cannot_change(self):
        self.receipt_path.write_text("{}")
        with self.assertRaises(compat.RuntimeIntegrityError):
            self.seal()

    def test_source_commit_patch_or_toolchain_contract_change_rejected(self):
        for key in ("upstream_commit", "source_state", "source_inputs", "tool_versions", "artifacts", "gameplay_acceptance"):
            original = copy.deepcopy(self.receipt)
            if key == "source_inputs":
                self.receipt[key]["gc-pacing.patch"] = "0" * 64
            elif key == "tool_versions":
                self.receipt[key]["node"] = "v99.0.0"
            elif key == "artifacts":
                self.receipt[key][0]["sha256"] = "0" * 64
            else:
                self.receipt[key] = "unreviewed"
            self.pin_receipt()
            with self.subTest(key=key), self.assertRaises(compat.RuntimeIntegrityError):
                self.seal()
            self.receipt = original

    def test_changed_output_missing_output_and_extra_file_rejected(self):
        (self.player / "ruffle.js").write_bytes(b"changed")
        with self.assertRaises(compat.RuntimeIntegrityError):
            self.seal()
        (self.player / "ruffle.js").unlink()
        with self.assertRaises(compat.RuntimeIntegrityError):
            self.seal()
        (self.player / "unexpected.txt").write_text("unexpected")
        with self.assertRaises(compat.RuntimeIntegrityError):
            self.seal()

    def test_pinned_manifest_and_provenance_are_checked_on_selection(self):
        pin = self.seal()
        with self.assertRaises(compat.RuntimeIntegrityError):
            compat.select_runtime_release(self.payload, prepared_pin_sha256="0" * 64)
        (self.player / "provenance/gc-pacing.patch").write_text("changed")
        with self.assertRaises(compat.RuntimeIntegrityError):
            compat.select_runtime_release(self.payload, prepared_pin_sha256=pin)

    def test_non_wasm_file_not_accepted_as_module(self):
        name = "1" * 20 + ".wasm"
        (self.player / name).write_bytes(b"invalid")
        self.receipt["files"][name] = builder.digest(self.player / name)
        self.pin_receipt()
        with self.assertRaises(compat.RuntimeIntegrityError):
            self.seal()

    def test_symlink_output_rejected(self):
        (self.player / "ruffle.js").unlink()
        (self.root / "external.js").write_text("external")
        (self.player / "ruffle.js").symlink_to(self.root / "external.js")
        with self.assertRaises(compat.RuntimeIntegrityError):
            self.seal()

    def test_unexpected_provenance_sidecar_rejected(self):
        self.seal()
        (self.player / "provenance/unreviewed.json").write_text("{}")
        with self.assertRaises(compat.RuntimeIntegrityError):
            self.seal()

    def test_native_start_propagates_prepared_pin_to_server(self):
        pin = self.seal()
        (self.payload / "PREPARED_RUNTIME.json").write_text(json.dumps({"schema": 1, "runtime_manifest_sha256": pin}))
        (self.payload / "requirements.txt").write_text("synthetic requirements")
        data = self.root / "profile"
        (data / "venv/bin").mkdir(parents=True)
        (data / "venv/bin/python").write_text("never executed")
        (data / "prepared.json").write_text(json.dumps({"schema": bootstrap.PREPARED_SCHEMA,
            "requirements_sha256": builder.digest(self.payload / "requirements.txt")}))
        runner = mock.Mock()
        with mock.patch.object(bootstrap, "compatibility_runtime", return_value=(compat, self.player)), mock.patch.object(bootstrap, "run_owned", runner):
            bootstrap.start(self.payload, data, SimpleNamespace(token="synthetic-token", port=46231))
        self.assertEqual(runner.call_args.kwargs["env"]["FARMVILLAGE_PREPARED_RUNTIME_PIN_SHA256"], pin)
        self.assertEqual(runner.call_args.kwargs["env"]["FARMVILLAGE_RUFFLE_DIR"], str(self.player))

    def test_native_package_environment_drops_accounts_and_netrc(self):
        with mock.patch.dict(os.environ, {'GH_TOKEN':'synthetic-only', 'AWS_SECRET_ACCESS_KEY':'synthetic-only',
             'PIP_TARGET':'/outside', 'HTTPS_PROXY':'http://unused.invalid', 'FARMVILLAGE_ASSETS_DIR':'/fixture/assets'}):
            env = bootstrap.private_python_environment()
        for key in ('GH_TOKEN', 'AWS_SECRET_ACCESS_KEY', 'PIP_TARGET', 'HTTPS_PROXY'):
            self.assertNotIn(key, env)
        self.assertEqual(env['NETRC'], os.devnull)
        self.assertEqual(env['PIP_CONFIG_FILE'], os.devnull)
        self.assertEqual(env['FARMVILLAGE_ASSETS_DIR'], '/fixture/assets')

    def test_native_payload_staging_preserves_prepared_receipts(self):
        source = self.root / "bundled"
        source.mkdir()
        contents = {"server.py": "# synthetic", "requirements.txt": "", "PREPARED_RUNTIME.json": '{"schema":1}',
                    "PUBLIC_RUNTIME_BUILD.json": '{"fixture":true}', "PUBLIC_INSTALL.json": '{"schema":1}'}
        for name, value in contents.items():
            (source / name).write_text(value)
        data = self.root / "staged-profile"
        data.mkdir()
        staged, version = bootstrap.stage_runtime(source, data)
        for name, value in contents.items():
            self.assertEqual((staged / name).read_text(), value)


class BuildBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="fv-player-build-fixture-")
        self.root = Path(self.temporary.name).resolve()

    def tearDown(self):
        self.temporary.cleanup()

    def test_platforms_have_complete_pinned_tools(self):
        for system, cpu in (("Darwin", "arm64"), ("Darwin", "x86_64"), ("Linux", "aarch64"), ("Linux", "x86_64")):
            host, node_host = builder.host_identity(system, cpu)
            artifacts = builder.toolchain_artifacts(PINS, host, node_host)
            self.assertEqual(len(artifacts), 10)
            self.assertTrue(all(entry["url"].startswith("https://") for entry in artifacts))
        with self.assertRaises(builder.BuildError):
            builder.host_identity("Windows", "arm64")

    def test_private_environment_is_not_inherited(self):
        with mock.patch.dict(builder.os.environ, {"GITHUB_TOKEN": "fixture-secret", "AWS_PROFILE": "fixture-private", "HOME": "/private-personal"}):
            environment = builder.isolated_environment(self.root, "/usr/bin:/bin")
        self.assertEqual(environment["HOME"], str(self.root / "home"))
        self.assertEqual(environment["NETRC"], "/dev/null")
        self.assertNotIn("GITHUB_TOKEN", environment)
        self.assertNotIn("AWS_PROFILE", environment)
        self.assertIn("credential.helper", environment.values())
        self.assertIn("core.hooksPath", environment.values())

    def test_unrelated_build_directory_refused(self):
        work = self.root / "work"
        work.mkdir()
        (work / "unrelated.txt").write_text("keep")
        with self.assertRaises(builder.BuildError):
            builder.build_public_runtime(work, self.root / "player", runner=mock.Mock(), fetch=mock.Mock())
        self.assertEqual((work / "unrelated.txt").read_text(), "keep")

    def test_failed_preflight_command_publishes_no_receipt(self):
        runner = mock.Mock(side_effect=subprocess.CalledProcessError(1, ["clang", "--print-targets"]))
        fetch = mock.Mock()
        with mock.patch.object(builder.shutil, "which", return_value="/usr/bin/clang"):
            with self.assertRaises(subprocess.CalledProcessError):
                builder.build_public_runtime(self.root / "work", self.root / "player", runner=runner, fetch=fetch)
        self.assertFalse((self.root / "player.build-receipt.json").exists())
        fetch.assert_not_called()

    def test_bad_toolchain_archive_cannot_start_build(self):
        def runner(arguments, cwd, environment, capture=False):
            return "wasm32" if "--print-targets" in arguments else "clang fixture"
        def fetch(entry, destination):
            destination.write_bytes(b"fixture-invalid-archive")
            return destination
        with mock.patch.object(builder.shutil, "which", return_value="/usr/bin/clang"):
            with self.assertRaises(builder.BuildError):
                builder.build_public_runtime(self.root / "work", self.root / "player", runner=runner, fetch=fetch)
        self.assertFalse((self.root / "player.build-receipt.json").exists())

    def test_tar_traversal_and_escaping_symlink_rejected(self):
        for name, link in (("../escape", None), ("root/escape", "/outside")):
            archive = self.root / "bad.tar.gz"
            with tarfile.open(archive, "w:gz") as output:
                info = tarfile.TarInfo(name)
                if link:
                    info.type = tarfile.SYMTYPE
                    info.linkname = link
                else:
                    info.size = 1
                output.addfile(info, None if link else io.BytesIO(b"x"))
            with self.subTest(name=name), self.assertRaises(builder.BuildError):
                builder.extract_archive(archive, self.root / "unpack")
        self.assertFalse((self.root / "escape").exists())

    def test_safe_archive_extracts_with_internal_relative_link(self):
        archive = self.root / "safe.tar.gz"
        with tarfile.open(archive, "w:gz") as output:
            info = tarfile.TarInfo("tool/bin/example")
            info.size = 1
            info.mode = 0o755
            output.addfile(info, io.BytesIO(b"x"))
            link = tarfile.TarInfo("tool/bin/alias")
            link.type = tarfile.SYMTYPE
            link.linkname = "example"
            output.addfile(link)
        result = builder.extract_archive(archive, self.root / "safe")
        self.assertEqual((result / "bin/alias").read_bytes(), b"x")
        self.assertTrue((result / "bin/example").stat().st_mode & 0o100)

    def mock_pipeline(self, *, fail_recipe=False, wrong_commit=False):
        expected = {}
        real_digest = builder.digest
        commands = []
        def fetch(entry, destination):
            destination.write_bytes(b"tiny-synthetic-archive")
            expected[destination] = entry.get("sha256", entry.get("sha512"))
            return destination
        def digest(path, algorithm="sha256"):
            return expected.get(Path(path)) or real_digest(path, algorithm)
        def extract(archive, destination):
            result = destination / "synthetic-tool"
            result.mkdir(parents=True)
            (result / "install.sh").write_text("synthetic; never executed")
            return result
        def runner(arguments, cwd, environment, capture=False):
            arguments = [str(value) for value in arguments]
            commands.append(arguments)
            self.assertTrue(Path(environment["HOME"]).is_relative_to(self.root))
            self.assertNotIn("GITHUB_TOKEN", environment)
            if "--print-targets" in arguments:
                return "wasm32 - WebAssembly 32-bit"
            if "--version" in arguments:
                if arguments[0].endswith("rustc"):
                    return "rustc 1.99.1 (fixture)"
                if any(value.endswith("npm-cli.js") for value in arguments):
                    return "11.0.0"
                if arguments[0].endswith("node"):
                    return "v24.19.0"
                if arguments[0].endswith("wasm-bindgen"):
                    return "wasm-bindgen 0.2.127"
                return "clang synthetic fixture"
            if "rev-parse" in arguments:
                return "0" * 40 if wrong_commit else builder.COMMIT
            if any(value.endswith("build-runtime.py") for value in arguments):
                candidate = Path(arguments[arguments.index("--destination") + 1])
                write_fixture(candidate)
                if fail_recipe:
                    raise subprocess.CalledProcessError(9, arguments)
            return ""
        patches = (mock.patch.object(builder, "digest", side_effect=digest),
                   mock.patch.object(builder, "extract_archive", side_effect=extract),
                   mock.patch.object(builder.shutil, "which", return_value="/usr/bin/clang"))
        return runner, fetch, patches, commands

    def test_complete_mocked_pipeline_emits_verified_receipt_and_resumes(self):
        runner, fetch, patches, commands = self.mock_pipeline()
        output = self.root / "Runtime/ruffle_runtime" / builder.RUNTIME_ID
        with patches[0], patches[1], patches[2]:
            receipt_path = builder.build_public_runtime(self.root / "work", output, runner=runner, fetch=fetch)
            receipt_sha = builder.digest(receipt_path)
            compat.validate_public_build(output, receipt_path, receipt_sha256=receipt_sha)
            command_count = len(commands)
            self.assertEqual(builder.build_public_runtime(self.root / "work", output, runner=runner, fetch=fetch), receipt_path)
            self.assertEqual(len(commands), command_count)
        pin = compat.prepare_public_runtime(self.root / "Runtime", receipt_path, receipt_sha256=receipt_sha)
        self.assertEqual(compat.select_runtime_release(self.root / "Runtime", prepared_pin_sha256=pin).manifest_sha256, pin)

    def test_failed_recipe_or_wrong_source_commit_publishes_nothing(self):
        for kind in ("recipe", "commit"):
            task_root = self.root / kind
            task_root.mkdir()
            runner, fetch, patches, commands = self.mock_pipeline(fail_recipe=kind == "recipe", wrong_commit=kind == "commit")
            with patches[0], patches[1], patches[2]:
                with self.subTest(kind=kind), self.assertRaises((subprocess.CalledProcessError, builder.BuildError)):
                    builder.build_public_runtime(task_root / "work", task_root / "player", runner=runner, fetch=fetch)
            self.assertFalse((task_root / "player").exists())
            self.assertFalse((task_root / "player.build-receipt.json").exists())
            self.assertFalse(list(task_root.glob(".player-build-*")))


class PublishedSourceStagingTests(unittest.TestCase):
    """The tracked source plus the approved private import must be exactly the default player pin.

    The private player files cannot exist in a source checkout, so their digests are taken from the
    importer's own expected hashes (tools/private-inputs.py verifies them on a real import). The
    complete file set and every source-owned byte go through the real strict verifier.
    """

    RELEASE = compat.ACTIVE_RELEASE
    PREFIX = "FarmVillage/ruffle_runtime/%s/" % RELEASE.runtime_id
    SHARED_RECIPE_FILES = ("gc-pacing.patch", "Cargo.lock", "package-lock.json", "version-seal.json")

    def setUp(self):
        self.directory = ROOT / self.PREFIX.rstrip("/")
        raw = (self.directory / compat.MANIFEST_NAME).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), self.RELEASE.manifest_sha256)
        self.pin = json.loads(raw)["files"]
        expected = json.loads((ROOT / "PrivateInputs.expected.json").read_text())["files"]
        self.private = {name[len(self.PREFIX):]: seal["sha256"] for name, seal in expected.items() if name.startswith(self.PREFIX)}
        tracked = json.loads((ROOT / "SOURCE_MANIFEST.json").read_text())["files"]
        self.owned = {name[len(self.PREFIX):] for name in tracked if name.startswith(self.PREFIX)}

    def test_source_and_private_import_together_are_exactly_the_pinned_file_set(self):
        wanted = set(self.pin) | {compat.MANIFEST_NAME}
        self.assertEqual(self.owned & set(self.private), set(), "tracked source must not shadow an imported player file")
        self.assertEqual(sorted((self.owned | set(self.private)) - wanted), [], "extra files the strict verifier rejects")
        self.assertEqual(sorted(wanted - (self.owned | set(self.private))), [], "pinned files neither tracked nor imported")
        for name, digest in self.private.items():
            self.assertEqual(digest, self.pin[name], "the importer expects different bytes than the pin: " + name)
        for name in sorted(self.owned - {compat.MANIFEST_NAME}):
            self.assertEqual(builder.digest(self.directory / name), self.pin[name], "tracked source differs from the pin: " + name)

    def test_the_real_verifier_accepts_the_source_plus_import_overlay(self):
        with tempfile.TemporaryDirectory() as temporary:
            staged = Path(temporary) / "player"
            for name in self.owned:
                (staged / name).parent.mkdir(parents=True, exist_ok=True)
                (staged / name).write_bytes((self.directory / name).read_bytes())
            for name in self.private:
                (staged / name).parent.mkdir(parents=True, exist_ok=True)
                (staged / name).write_bytes(b"placeholder for a file the importer verifies")
            real_digest = compat._file_digest

            def digest(path, check_cancelled):
                name = Path(path).relative_to(staged).as_posix()
                return self.private[name] if name in self.private else real_digest(path, check_cancelled)

            with mock.patch.object(compat, "_file_digest", digest):
                self.assertEqual(set(compat.verify_runtime(staged).files), set(self.pin))

    def test_the_public_build_recipe_is_apart_from_the_pinned_player_and_shares_only_identical_files(self):
        recipe = builder.PUBLIC_BUILD_INPUTS
        self.assertFalse(recipe.is_relative_to(self.directory), "the recipe must not live in the hard-pinned player directory")
        for name in self.SHARED_RECIPE_FILES:
            with self.subTest(name):
                shared = (self.directory / "provenance" / name).read_bytes()
                self.assertEqual((recipe / name).read_bytes(), shared)
                self.assertEqual(hashlib.sha256(shared).hexdigest(), compat.PUBLIC_SOURCE_INPUTS[name])
        compat.verify_public_build_inputs(recipe, builder.PINS_PATH)


if __name__ == "__main__":
    unittest.main()
