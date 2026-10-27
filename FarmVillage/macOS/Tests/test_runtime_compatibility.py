"""Offline integrity, rollback and cancellation checks for local runtime staging."""

import hashlib
import contextlib
import importlib.util
import json
import io
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("farmvillage_runtime_compatibility", ROOT / "runtime_compatibility.py")
RUNTIME = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUNTIME
SPEC.loader.exec_module(RUNTIME)


class Cancelled(Exception):
    pass


class RuntimeCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.payload = self.root / "payload"
        self.data = self.root / "profile"
        self.data.mkdir()
        self.runtime_id = "0.7.1-farmvillage-test1"
        self.source = self.payload / "ruffle_runtime" / self.runtime_id
        self.source.mkdir(parents=True)
        self.contents = {"ruffle.js": b"reviewed loader", "core.wasm": b"\x00asm\x01\x00\x00\x00", "nested/core.js": b"reviewed core", "LICENSE.md": b"license"}
        for name, value in self.contents.items():
            path = self.source / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(value)
        self.manifest = {
            "schema": 1, "runtime_id": self.runtime_id, "version": "0.7.1",
            "upstream_commit": "89a7049965f3090e706265670df309a5128233ac",
            "files": {name: hashlib.sha256(value).hexdigest() for name, value in self.contents.items()},
            "provenance": {"change": "test fixture only"},
        }
        self.release = self.write_manifest()

    def write_manifest(self):
        raw = json.dumps(self.manifest, sort_keys=True).encode()
        (self.source / RUNTIME.MANIFEST_NAME).write_bytes(raw)
        return RUNTIME.RuntimeRelease(self.runtime_id, "0.7.1", self.manifest["upstream_commit"], hashlib.sha256(raw).hexdigest())

    def old_destination(self):
        destination = self.data / "ruffle" / self.runtime_id
        destination.mkdir(parents=True)
        (destination / "prior-runtime").write_bytes(b"preserve during failure")
        return destination

    def leftovers(self):
        return list((self.data / "ruffle").glob(".ruffle-*"))

    def test_verified_distribution_and_immutable_file_map(self):
        verified = RUNTIME.verify_runtime(self.source, self.release)
        self.assertEqual(dict(verified.files), self.manifest["files"])
        with self.assertRaises(TypeError):
            verified.files["ruffle.js"] = "replacement"
        self.assertEqual(RUNTIME.bundled_runtime(self.payload, self.release), self.source)

    def test_manifest_hash_is_pinned_outside_package(self):
        (self.source / "ruffle.js").write_bytes(b"tampered loader")
        self.manifest["files"]["ruffle.js"] = hashlib.sha256(b"tampered loader").hexdigest()
        self.write_manifest()
        with self.assertRaisesRegex(RUNTIME.RuntimeIntegrityError, "reviewed hash"):
            RUNTIME.verify_runtime(self.source, self.release)

    def test_missing_extra_and_modified_files_fail_closed(self):
        missing = self.source / "nested/core.js"
        missing.unlink()
        self.assertFalse(RUNTIME.runtime_valid(self.source, self.release))
        missing.write_bytes(self.contents["nested/core.js"])
        extra = self.source / "unreviewed.js"
        extra.write_bytes(b"extra")
        self.assertFalse(RUNTIME.runtime_valid(self.source, self.release))
        extra.unlink()
        (self.source / "core.wasm").write_bytes(b"tampered")
        self.assertFalse(RUNTIME.runtime_valid(self.source, self.release))

    def test_package_and_intermediate_symlinks_are_rejected(self):
        linked = self.root / "runtime-link"
        linked.symlink_to(self.source, target_is_directory=True)
        self.assertFalse(RUNTIME.runtime_valid(linked, self.release))
        (self.source / "nested/core.js").unlink()
        (self.source / "nested").rmdir()
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "core.js").write_bytes(self.contents["nested/core.js"])
        (self.source / "nested").symlink_to(elsewhere, target_is_directory=True)
        self.assertFalse(RUNTIME.runtime_valid(self.source, self.release))

    def test_resource_replacement_after_startup_cannot_serve_unreviewed_bytes(self):
        verified = RUNTIME.verify_runtime(self.source, self.release)
        self.assertEqual(RUNTIME.read_resource(verified, "ruffle.js"), self.contents["ruffle.js"])
        replacement = self.root / "replacement.js"
        replacement.write_bytes(b"a different runtime loader")
        replacement.replace(self.source / "ruffle.js")
        with self.assertRaisesRegex(RUNTIME.RuntimeIntegrityError, "changed after verification"):
            RUNTIME.read_resource(verified, "ruffle.js")
        for name in ("unknown.js", "../ruffle.js", RUNTIME.MANIFEST_NAME):
            with self.subTest(name=name), self.assertRaises(RUNTIME.RuntimeIntegrityError):
                RUNTIME.read_resource(verified, name)

    def test_source_and_installed_resource_bytes_match_and_missing_or_linked_files_fail(self):
        source = RUNTIME.verify_runtime(self.source, self.release)
        installed = RUNTIME.install_runtime(self.payload, self.data, self.release)
        native = RUNTIME.verify_runtime(installed, self.release)
        for name in self.contents:
            self.assertEqual(RUNTIME.read_resource(source, name), RUNTIME.read_resource(native, name))
        target = installed / "core.wasm"
        target.unlink()
        with self.assertRaises(RUNTIME.RuntimeIntegrityError):
            RUNTIME.read_resource(native, "core.wasm")
        target.symlink_to(self.source / "core.wasm")
        with self.assertRaises(RUNTIME.RuntimeIntegrityError):
            RUNTIME.read_resource(native, "core.wasm")

    def test_pinned_manifest_still_requires_safe_identity_and_paths(self):
        for name in ("../outside", "/absolute", "nested//core.js", "a/./b", "a\\b", "a:b", ".", ""):
            with self.subTest(name=name):
                self.manifest["files"][name] = "0" * 64
                release = self.write_manifest()
                with self.assertRaises(RUNTIME.RuntimeIntegrityError):
                    RUNTIME.verify_runtime(self.source, release)
                del self.manifest["files"][name]
        self.manifest["runtime_id"] = "different"
        release = self.write_manifest()
        with self.assertRaisesRegex(RUNTIME.RuntimeIntegrityError, "identity"):
            RUNTIME.verify_runtime(self.source, release)

    def test_offline_install_preserves_official_runtime_and_all_profile_data(self):
        official = self.data / "ruffle/0.7.1"
        official.mkdir(parents=True)
        (official / "ruffle.js").write_bytes(b"original official release")
        (self.data / "save.json").write_bytes(b"unchanged save")
        installed = RUNTIME.install_runtime(self.payload, self.data, self.release)
        RUNTIME.verify_runtime(installed, self.release)
        self.assertEqual((official / "ruffle.js").read_bytes(), b"original official release")
        self.assertEqual((self.data / "save.json").read_bytes(), b"unchanged save")
        shutil.rmtree(self.payload)
        with mock.patch.object(RUNTIME.shutil, "copyfile", side_effect=AssertionError("valid installation must be reused")):
            self.assertEqual(RUNTIME.install_runtime(self.payload, self.data, self.release), installed)
        self.assertEqual(self.leftovers(), [])

    def test_invalid_existing_runtime_replaced_after_complete_verification(self):
        destination = self.old_destination()
        RUNTIME.install_runtime(self.payload, self.data, self.release)
        self.assertFalse((destination / "prior-runtime").exists())
        RUNTIME.verify_runtime(destination, self.release)
        self.assertEqual(self.leftovers(), [])

    def test_source_or_copy_failure_keeps_existing_runtime(self):
        destination = self.old_destination()
        with mock.patch.object(RUNTIME.shutil, "copyfile", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                RUNTIME.install_runtime(self.payload, self.data, self.release)
        self.assertEqual((destination / "prior-runtime").read_bytes(), b"preserve during failure")
        self.assertEqual(self.leftovers(), [])
        (self.source / "core.wasm").write_bytes(b"modified source")
        with self.assertRaises(RUNTIME.RuntimeIntegrityError):
            RUNTIME.install_runtime(self.payload, self.data, self.release)
        self.assertTrue((destination / "prior-runtime").exists())

    def test_failed_publication_restores_previous_directory(self):
        destination = self.old_destination()
        replace = RUNTIME.os.replace

        def fail_publish(source, target):
            if Path(source).name.startswith(".ruffle-stage-"):
                raise OSError("publication failed")
            return replace(source, target)

        with mock.patch.object(RUNTIME.os, "replace", side_effect=fail_publish):
            with self.assertRaisesRegex(OSError, "publication failed"):
                RUNTIME.install_runtime(self.payload, self.data, self.release)
        self.assertTrue((destination / "prior-runtime").exists())
        self.assertEqual(self.leftovers(), [])

    def test_failed_rollback_retains_quarantined_previous_directory(self):
        self.old_destination()
        replace = RUNTIME.os.replace

        def fail_publish_and_restore(source, target):
            if Path(source).name.startswith((".ruffle-stage-", ".ruffle-previous-")):
                raise OSError("replacement unavailable")
            return replace(source, target)

        with mock.patch.object(RUNTIME.os, "replace", side_effect=fail_publish_and_restore):
            with self.assertRaisesRegex(OSError, "replacement unavailable"):
                RUNTIME.install_runtime(self.payload, self.data, self.release)
        previous = self.leftovers()
        self.assertEqual(len(previous), 1)
        self.assertTrue(previous[0].name.startswith(".ruffle-previous-"))
        self.assertEqual((previous[0] / "prior-runtime").read_bytes(), b"preserve during failure")

    def test_cancellation_during_copy_removes_only_new_stage(self):
        destination = self.old_destination()
        copy = RUNTIME.shutil.copyfile
        copied = []

        def record_copy(source, target):
            result = copy(source, target)
            copied.append(target)
            return result

        def cancel():
            if copied:
                raise Cancelled()

        with mock.patch.object(RUNTIME.shutil, "copyfile", side_effect=record_copy):
            with self.assertRaises(Cancelled):
                RUNTIME.install_runtime(self.payload, self.data, self.release, check_cancelled=cancel)
        self.assertTrue((destination / "prior-runtime").exists())
        self.assertEqual(self.leftovers(), [])

    def test_cancellation_is_observed_when_reusing_installed_runtime(self):
        RUNTIME.install_runtime(self.payload, self.data, self.release)
        with self.assertRaises(Cancelled):
            RUNTIME.install_runtime(self.payload, self.data, self.release,
                                    check_cancelled=lambda: (_ for _ in ()).throw(Cancelled()))

    def test_interrupted_stage_cleanup_preserves_quarantines_and_other_runtime_ids(self):
        parent = self.data / "ruffle"
        parent.mkdir()
        abandoned = parent / (".ruffle-stage-" + self.runtime_id + "-interrupted")
        abandoned.mkdir()
        (abandoned / "partial.wasm").write_bytes(b"partial")
        preserved = [parent / (".ruffle-previous-" + self.runtime_id + "-recovery"),
                     parent / ".ruffle-stage-other-runtime-id-interrupted"]
        for path in preserved:
            path.mkdir()
            (path / "keep").write_bytes(b"owned by another operation or recovery")
        external = self.root / "external"
        external.mkdir()
        linked = parent / (".ruffle-stage-" + self.runtime_id + "-link")
        linked.symlink_to(external, target_is_directory=True)
        RUNTIME.install_runtime(self.payload, self.data, self.release)
        self.assertFalse(abandoned.exists())
        self.assertTrue(linked.is_symlink())
        for path in preserved:
            self.assertTrue((path / "keep").is_file())

    def test_resource_urls_require_exact_runtime_id_and_safe_relative_file(self):
        prefix = self.runtime_id + "/"
        self.assertEqual(RUNTIME.public_path(self.release), "/ruffle/" + prefix)
        self.assertEqual(RUNTIME.resource_name(prefix + "nested/core.js", self.release), "nested/core.js")
        for name in ("0.7.1/ruffle.js", prefix, prefix + "../core.wasm", prefix + "/core.wasm", prefix + "a\\b", prefix + RUNTIME.MANIFEST_NAME):
            with self.subTest(name=name), self.assertRaises(RUNTIME.RuntimeIntegrityError):
                RUNTIME.resource_name(name, self.release)

    def test_unconfigured_runtime_fails_closed(self):
        with mock.patch.object(RUNTIME, "ACTIVE_RELEASE", None):
            with self.assertRaisesRegex(RUNTIME.RuntimeIntegrityError, "activated"):
                RUNTIME.install_runtime(self.payload, self.data)

    def test_build_verifier_checks_bundle_without_installing_or_requiring_tools(self):
        with mock.patch.object(RUNTIME, "ACTIVE_RELEASE", self.release), \
             mock.patch.object(RUNTIME, "install_runtime", side_effect=AssertionError("verification must not install")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            RUNTIME.main(["--payload", str(self.payload)])
        self.assertIn(self.runtime_id, output.getvalue())
        self.assertFalse((self.data / "ruffle").exists())
        (self.source / "core.wasm").unlink()
        with mock.patch.object(RUNTIME, "ACTIVE_RELEASE", self.release), self.assertRaises(RUNTIME.RuntimeIntegrityError):
            RUNTIME.main(["--payload", str(self.payload)])


if __name__ == "__main__":
    unittest.main()
