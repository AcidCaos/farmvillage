"""Check Bifrost packaging with sealed fixtures and fake SSH/SCP; no network."""

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import types
import unittest
from unittest import mock
from contextlib import redirect_stdout

HERE = Path(__file__).resolve().parent
PREVIOUS = "farmvillage-portable-preparation-1acf91b47487"
NEW = "farmvillage-portable-preparation-0123456789ab"


def load_script(path, name):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


builder = load_script(HERE / "build-bifrost-update.py", "bifrost_update_builder_tests")
release_builder = load_script(HERE.parents[1] / "macOS/Scripts/prepare-portable-release.py",
                              "portable_release_builder_tests")


def sidecar(path):
    path.with_name(path.name + ".sha256").write_text(
        hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n")


def write_tar(path, members):
    with tarfile.open(path, "w:gz", format=tarfile.USTAR_FORMAT) as output:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o644
            output.addfile(info, io.BytesIO(data))
    sidecar(path)


def write_reference(path, *, root=NEW, history=None, inventory=None, include_inventory=True):
    """Minimal sealed fixture accepted by the unmodified archive verifier."""
    inventory = {"file_count": 12, "logical_bytes": 345} if inventory is None else inventory
    files = {"external-assets.json": release_builder.json_bytes(inventory)} if include_inventory else {}
    if history is not None:
        files[builder.HISTORICAL_NATIVE] = history
    metadata = {name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                for name, data in files.items()}
    files["manifest.json"] = release_builder.json_bytes({"files": metadata, "external_assets": inventory})
    sums = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    files["SHA256SUMS"] = "".join(f"{digest}  {name}\n" for name, digest in sorted(sums.items())).encode()
    write_tar(path, {root + "/" + name: data for name, data in files.items()})


class ReferenceArchiveTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="bifrost-reference-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.reference = self.root / "retained-v2.tar.gz"

    def test_different_release_root_without_history_reuses_only_verified_inventory(self):
        write_reference(self.reference)
        inputs = [self.reference, Path(str(self.reference) + ".sha256"), builder.PREPARE_SCRIPT]
        before = {path: path.read_bytes() for path in inputs}
        result = builder.read_reference(self.reference)
        self.assertEqual(set(result), {"external-assets.json"})
        self.assertEqual(json.loads(result["external-assets.json"]), {"file_count": 12, "logical_bytes": 345})
        self.assertEqual({path: path.read_bytes() for path in inputs}, before)
        self.assertFalse((self.root / NEW).exists(), "Reference members must not be extracted")

    def test_supplied_historical_record_is_preserved_byte_for_byte(self):
        history = b'{"historicalFixture":"retained verbatim"}\n'
        write_reference(self.reference, root=PREVIOUS, history=history)
        self.assertEqual(builder.read_reference(self.reference)[builder.HISTORICAL_NATIVE], history)

    def test_bad_checksum_or_misnamed_sidecar_is_rejected(self):
        write_reference(self.reference)
        checksum = self.reference.with_name(self.reference.name + ".sha256")
        for text in ("0" * 64 + "  " + self.reference.name + "\n",
                     hashlib.sha256(self.reference.read_bytes()).hexdigest() + "  other.tar.gz\n", "", "invalid"):
            with self.subTest(sidecar=text):
                checksum.write_text(text)
                with self.assertRaises(ValueError):
                    builder.read_reference(self.reference)

    def test_symlink_archive_and_sidecar_are_rejected(self):
        write_reference(self.reference)
        for linked in (self.reference, Path(str(self.reference) + ".sha256")):
            with self.subTest(path=linked.name):
                original = linked.with_name(linked.name + ".original")
                linked.rename(original)
                linked.symlink_to(original.name)
                with self.assertRaisesRegex(ValueError, "regular files"):
                    builder.read_reference(self.reference)
                linked.unlink()
                original.rename(linked)

    def test_missing_invalid_or_manifest_mismatched_asset_inventory_is_rejected(self):
        write_reference(self.reference, include_inventory=False)
        with self.assertRaisesRegex(ValueError, "no verified"):
            builder.read_reference(self.reference)
        for value in ({"file_count": True, "logical_bytes": 2}, {"file_count": 2, "logical_bytes": -1}, []):
            write_reference(self.reference, inventory=value)
            with self.subTest(inventory=value), self.assertRaisesRegex(ValueError, "inventory is invalid"):
                builder.read_reference(self.reference)
        write_reference(self.reference)
        with tarfile.open(self.reference) as stream:
            members = {m.name: stream.extractfile(m).read() for m in stream.getmembers()}
        manifest = json.loads(members[NEW + "/manifest.json"])
        manifest["external_assets"]["file_count"] += 1
        members[NEW + "/manifest.json"] = release_builder.json_bytes(manifest)
        members[NEW + "/SHA256SUMS"] = "".join(
            hashlib.sha256(data).hexdigest() + "  " + name[len(NEW) + 1:] + "\n"
            for name, data in sorted(members.items()) if not name.endswith("/SHA256SUMS")).encode()
        write_tar(self.reference, members)
        with self.assertRaisesRegex(ValueError, "differs from its manifest"):
            builder.read_reference(self.reference)

    def test_unsafe_root_duplicate_link_traversal_and_tampered_members_are_rejected(self):
        for root in ("other-release", "../escape", "/absolute"):
            with self.subTest(root=root):
                write_reference(self.reference, root=root)
                with self.assertRaises(ValueError):
                    builder.read_reference(self.reference)
        for variant in ("duplicate", "link", "traversal", "second-root", "tampered"):
            with self.subTest(variant=variant):
                write_reference(self.reference)
                with tarfile.open(self.reference) as stream:
                    members = [(m, stream.extractfile(m).read()) for m in stream.getmembers()]
                if variant == "duplicate":
                    members.append(members[0])
                elif variant == "link":
                    link = tarfile.TarInfo(NEW + "/linked")
                    link.type, link.linkname = tarfile.SYMTYPE, "../outside"
                    members.append((link, b""))
                elif variant in {"traversal", "second-root"}:
                    info = tarfile.TarInfo(NEW + "/../escape" if variant == "traversal" else PREVIOUS + "/extra")
                    members.append((info, b""))
                else:
                    member, original = members[0]
                    members[0] = (member, b"x" * len(original))
                with tarfile.open(self.reference, "w:gz") as output:
                    for member, data in members:
                        output.addfile(member, io.BytesIO(data))
                sidecar(self.reference)
                with self.assertRaises(ValueError):
                    builder.read_reference(self.reference)


class ManageWrapperTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="bifrost-update-wrapper-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.delivery = self.root / "Bifrost LAN Update 2026-10-22"
        self.delivery.mkdir()
        self.wrapper = self.delivery / "manage-bifrost.sh"
        shutil.copyfile(HERE / "manage-bifrost.sh", self.wrapper)
        for name in ("farmvillage-lan-host.tar.gz", NEW + ".tar.gz"):
            (self.delivery / name).write_bytes(b"fixture " + name.encode())
            sidecar(self.delivery / name)
        commands = self.root / "commands"
        commands.mkdir()
        self.log = self.root / "calls.jsonl"
        stub = f"""#!{Path(sys.executable).resolve()}
import json, os, sys
with open(os.environ['FV_WRAPPER_LOG'], 'a') as output:
    output.write(json.dumps([os.path.basename(sys.argv[0])] + sys.argv[1:]) + '\\n')
sys.exit(42 if os.environ.get('FV_FAIL_COMMAND') == os.path.basename(sys.argv[0]) else 0)
"""
        for name in ("ssh", "scp"):
            (commands / name).write_text(stub)
            (commands / name).chmod(0o755)
        self.environment = dict(os.environ, PATH=str(commands) + os.pathsep + os.environ["PATH"],
                                FV_WRAPPER_LOG=str(self.log))

    def invoke(self, *arguments, **environment):
        return subprocess.run(["/bin/bash", str(self.wrapper), *arguments], capture_output=True, text=True,
                              timeout=10, env=dict(self.environment, **environment))

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def remote(self):
        call = self.calls()[-1]
        self.assertEqual(call[:3], ["ssh", "-t", "farmvillage@192.168.50.80"])
        self.assertEqual(len(call), 4, "The remote operation must be one SSH argument.")
        return call[3]

    def test_check_saves_is_default_and_read_only(self):
        for arguments in ((), ("--check-saves",)):
            with self.subTest(arguments=arguments):
                self.log.unlink(missing_ok=True)
                result = self.invoke(*arguments)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual([call[0] for call in self.calls()], ["scp", "ssh"])
                self.assertEqual(self.calls()[0][1:3], [str(self.delivery / "farmvillage-lan-host.tar.gz"),
                                                      str(self.delivery / "farmvillage-lan-host.tar.gz.sha256")])
                command = self.remote()
                self.assertIn("sha256sum -c farmvillage-lan-host.tar.gz.sha256", command)
                self.assertIn('diagnose-saves.py" --runtime /home/farmvillage/farmville-test/release/' + PREVIOUS, command)
                self.assertIn('-C "$stage"', command)
                for mutation in ("-C ..", "install-service.sh", "activate-release.sh", "install-fresh-world",
                                 "systemctl", "kill ", NEW):
                    self.assertNotIn(mutation, command)

    def test_install_verifies_activates_then_installs_service(self):
        result = self.invoke("--install")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([call[0] for call in self.calls()], ["scp", "ssh"])
        self.assertEqual(self.calls()[0][1:], [str(self.delivery / name) for name in (
            "farmvillage-lan-host.tar.gz", "farmvillage-lan-host.tar.gz.sha256", NEW + ".tar.gz",
            NEW + ".tar.gz.sha256")] + ["farmvillage@192.168.50.80:/home/farmvillage/farmville-test/release/"])
        command = self.remote()
        order = ["sha256sum -c farmvillage-lan-host.tar.gz.sha256", f"sha256sum -c {NEW}.tar.gz.sha256",
                 'sha256sum --quiet -c SHA256SUMS',
                 f'activate-release.sh" /home/farmvillage/farmville-test/release {NEW}.tar.gz',
                 "-C .. ", "bash ../hosting/install-service.sh"]
        positions = [command.index(part) for part in order]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("install-fresh-world", command)
        self.assertNotIn("rm -rf -- ../", command)

    def test_fresh_start_and_unknown_options_are_refused_before_transfer(self):
        for arguments in (("--fresh-start",), ("--unknown",), ("--install", "--check-saves")):
            with self.subTest(arguments=arguments):
                result = self.invoke(*arguments)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.calls(), [])

    def test_corrupt_or_ambiguous_bundle_stops_before_transfer(self):
        (self.delivery / (NEW + ".tar.gz")).write_bytes(b"tampered")
        self.assertNotEqual(self.invoke("--install").returncode, 0)
        self.assertEqual(self.calls(), [])
        sidecar(self.delivery / (NEW + ".tar.gz"))
        other = self.delivery / "farmvillage-portable-preparation-ffffffffffff.tar.gz"
        other.write_bytes(b"second")
        sidecar(other)
        result = self.invoke("--install")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exactly one game bundle", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_failed_transfer_never_runs_remote_install(self):
        result = self.invoke("--install", FV_FAIL_COMMAND="scp")
        self.assertEqual(result.returncode, 42)
        self.assertEqual([call[0] for call in self.calls()], ["scp"])


@unittest.skipUnless(shutil.which("sha256sum"), "sha256sum is required")
class ActivateReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="bifrost-update-activate-")
        self.addCleanup(temporary.cleanup)
        self.release = Path(temporary.name) / "release"
        venv = self.release / PREVIOUS / ".venv/bin"
        venv.mkdir(parents=True)
        (venv / "python").write_text(f"#!/bin/sh\nexec '{Path(sys.executable).resolve()}' \"$@\"\n")
        (venv / "python").chmod(0o755)
        (self.release / PREVIOUS / "Runtime").mkdir()
        (self.release / PREVIOUS / "Runtime/server.py").write_text("old\n")
        self.files = {"Runtime/server.py": b"new\n", "manifest.json": b"{}\n"}
        sums = "".join(hashlib.sha256(data).hexdigest() + "  " + name + "\n" for name, data in sorted(self.files.items()))
        self.members = {NEW + "/" + name: data for name, data in self.files.items()}
        self.members[NEW + "/SHA256SUMS"] = sums.encode()
        self.bundle = self.release / (NEW + ".tar.gz")
        write_tar(self.bundle, self.members)
        # The fixture interpreter only needs to accept the library import check.
        shim = Path(temporary.name) / "shim"
        shim.mkdir()
        for module in ("flask", "pyamf", "requests", "tqdm", "xmltodict"):
            (shim / (module + ".py")).write_text("")
        self.environment = dict(os.environ, PYTHONPATH=str(shim))

    def activate(self, bundle_name=None):
        return subprocess.run(["/bin/bash", str(HERE / "activate-release.sh"), str(self.release),
                               bundle_name or self.bundle.name], capture_output=True, text=True,
                              timeout=30, env=self.environment)

    def test_unpacks_beside_previous_with_copied_environment_and_is_rerunnable(self):
        result = self.activate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.release / NEW / "Runtime/server.py").read_text(), "new\n")
        self.assertTrue(os.access(self.release / NEW / ".venv/bin/python", os.X_OK))
        self.assertEqual((self.release / PREVIOUS / "Runtime/server.py").read_text(), "old\n")
        self.assertEqual(sorted(path.name for path in self.release.iterdir()),
                         sorted([PREVIOUS, NEW, self.bundle.name, self.bundle.name + ".sha256"]))
        again = self.activate()
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("already unpacked", again.stdout)

    def test_checksum_mismatch_changes_nothing(self):
        self.bundle.write_bytes(self.bundle.read_bytes() + b"x")
        result = self.activate()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.release / NEW).exists())
        self.assertFalse(any(path.name.startswith(".unpack") for path in self.release.iterdir()))

    def test_tampered_member_or_extra_folder_is_rejected_and_cleaned_up(self):
        for members in ({**self.members, NEW + "/Runtime/server.py": b"evil\n"},
                        {**self.members, "other/file": b"x"}):
            with self.subTest(members=sorted(members)):
                write_tar(self.bundle, members)
                result = self.activate()
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((self.release / NEW).exists())
                self.assertFalse(any(path.name.startswith(".unpack") for path in self.release.iterdir()))

    def test_existing_different_release_is_left_alone(self):
        (self.release / NEW).mkdir()
        (self.release / NEW / "SHA256SUMS").write_text("0" * 64 + "  missing\n")
        result = self.activate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("left alone", result.stderr)
        self.assertEqual([path.name for path in (self.release / NEW).iterdir()], ["SHA256SUMS"])

    def test_bad_bundle_name_is_refused(self):
        self.assertNotEqual(self.activate("../evil.tar.gz").returncode, 0)


class BuildProvenanceTests(unittest.TestCase):
    def test_current_client_pin_matches_preparation_and_keeps_a4_review_historical(self):
        project = HERE.parents[1]
        base = release_builder.literal_assignment(project / "client_compatibility.py", "PATCHED_BODY_SHA256")
        meadows_body = release_builder.literal_assignment(project / "meadows_client.py", "PATCHED_BODY_SHA256")
        current = release_builder.literal_assignment(project / "client_graphics.py", "PATCHED_BODY_SHA256")
        graphics_base = release_builder.literal_assignment(project / "client_graphics.py", "BASE_BODY_SHA256")
        reviews = project / "macOS/Documentation/ClientPatches"
        historical = json.loads((reviews / "provenance.json").read_text())
        deco = json.loads((reviews / "deco-client-byte-review.json").read_text())
        scratch = json.loads((reviews / "scratch-coin-byte-review.json").read_text())
        empty_world = json.loads((reviews / "empty-world-byte-review.json").read_text())
        cottage = json.loads((reviews / "cottage-graphics-byte-review.json").read_text())
        upgrades = json.loads((reviews / "cottage-upgrade-visibility-byte-review.json").read_text())
        turbo = json.loads((reviews / "turbo-purchase-refusal-byte-review.json").read_text())
        self.assertEqual(release_builder.CLIENT_BODY_SHA, current)
        self.assertEqual(deco["target_body_sha256"], scratch["baseline_body_sha256"])
        self.assertEqual(scratch["target_body_sha256"], empty_world["input_body_sha256"])
        self.assertEqual(empty_world["output_body_sha256"], cottage["input_body_sha256"])
        self.assertEqual(cottage["output_body_sha256"], upgrades["input_body_sha256"])
        self.assertEqual(upgrades["output_body_sha256"], turbo["input_body_sha256"])
        turbo_stage = release_builder.literal_assignment(project / "client_compatibility.py", "TURBO_BODY_SHA256")
        self.assertEqual(turbo["output_body_sha256"], turbo_stage)
        self.assertNotEqual(current, turbo_stage)
        self.assertEqual(base, "2200ebcdc58dfa2061ffaf20e58f8c83b1868449a6b8bae8f81395c27a0454c6")
        self.assertEqual(meadows_body, "8f34e1533a4949e411bf75706e3010b74a3e805f1d7f02f10bc799295baa4066")
        self.assertEqual(graphics_base, meadows_body)
        self.assertEqual(current, "bd7386cf087f27d57b96c1d46d1629e3b562a3487de51aa2b5ee5adfb0a69d9e")
        meadows = json.loads((reviews / "MEADOWS_SCOPED_CLIENT_REVIEW.json").read_text())
        self.assertEqual(meadows["input_body_sha256"], "51c484d32ac455abd3669fe1e96bd2cf17303fcfd18a4d265cb9b2eb661ed8f9")
        self.assertEqual(meadows["output_body_sha256"], meadows_body)
        graphics = json.loads((reviews / "GRAPHICS_CACHE_CLIENT_REVIEW.json").read_text())
        self.assertEqual(graphics["baseBodySHA256"], meadows_body)
        self.assertEqual(graphics["finalBodySHA256"], current)
        self.assertIn("GRAPHICS_CACHE_CLIENT_REVIEW.json", release_builder.CLIENT_REVIEWS)
        self.assertIn("MEADOWS_SCOPED_CLIENT_REVIEW.json", release_builder.CLIENT_REVIEWS)
        self.assertEqual(release_builder.A4_BODY_SHA, historical["market_prepared_body_sha256"])
        self.assertEqual(deco["baseline_body_sha256"], release_builder.A4_BODY_SHA)
        self.assertNotEqual(current, release_builder.A4_BODY_SHA)
        self.assertIn("deco-client-byte-review.json", release_builder.CLIENT_REVIEWS)
        self.assertIn("scratch-coin-byte-review.json", release_builder.CLIENT_REVIEWS)
        self.assertIn("empty-world-byte-review.json", release_builder.CLIENT_REVIEWS)
        self.assertIn("cottage-graphics-byte-review.json", release_builder.CLIENT_REVIEWS)
        self.assertIn("cottage-upgrade-visibility-byte-review.json", release_builder.CLIENT_REVIEWS)
        self.assertIn("turbo-purchase-refusal-byte-review.json", release_builder.CLIENT_REVIEWS)

    def build_identity_fixture(self, historical=True):
        with tempfile.TemporaryDirectory(prefix="bifrost-update-identity-") as temporary:
            work = Path(temporary)
            (work / "out").mkdir()
            app = work / "Fixture.app"
            payload = app / "Contents/Resources/Runtime"
            game = payload / "embeds/Flash/v855097-855094/FarmGame.swf"
            game.parent.mkdir(parents=True)
            game.write_bytes(b"synthetic client bytes")
            marker = "0" * 64
            (payload / ".payload-version").write_text(marker)
            identities = []
            history_arguments = []

            def seal(arguments):
                identities.append(json.loads(arguments.identity.read_text()))
                history_arguments.append({
                    "omit": arguments.omit_historical_native_verification,
                    "record": (arguments.historical_native_verification.read_bytes()
                               if arguments.historical_native_verification is not None else None),
                })
                arguments.output.write_bytes(b"synthetic sealed archive")
                return {"files": 1, "bytes": 24, "sha256": "synthetic"}

            prepare = mock.Mock(prepare=seal)
            prepare.verify_archive.return_value = {
                "accepted_payload_version": marker, "files": {"Runtime/GodBarn/catalog_tools.py": {}},
            }
            reference = {"external-assets.json": b"{}"}
            if historical:
                reference[builder.HISTORICAL_NATIVE] = b'{"historical":true}'
            exact = "Offline feature and Deco tests passed; native and Bifrost execution remain untested."
            with mock.patch.object(builder, "stage_payload", return_value=app), \
                 mock.patch.object(builder, "check_payload_matches_tree", return_value=3), \
                 mock.patch.object(builder, "load_prepare", return_value=prepare), \
                 mock.patch.object(builder, "DEBUG_APP", work / "missing-debug-app"), \
                 redirect_stdout(io.StringIO()):
                builder.build_bundle(work, reference, exact)
            if not historical:
                self.assertFalse((work / "StableOrchard-native-verification.json").exists())
            return identities[0], history_arguments[0], exact

    def test_new_identity_records_exact_validation_and_does_not_claim_old_playtest(self):
        identity, history, exact = self.build_identity_fixture()
        self.assertEqual(identity["acceptance"], exact)
        self.assertEqual(identity["current_validation"]["mac_native"], "Not run for this payload")
        self.assertEqual(identity["current_validation"]["bifrost"], "Not run for this payload")
        self.assertIn("prior-release evidence", identity["historical_evidence"])
        self.assertNotIn("play-tested", json.dumps(identity))
        self.assertEqual(history, {"omit": False, "record": b'{"historical":true}'})

    def test_absent_reference_history_is_explicitly_omitted_without_fabrication(self):
        identity, history, exact = self.build_identity_fixture(historical=False)
        self.assertEqual(identity["acceptance"], exact)
        self.assertEqual(history, {"omit": True, "record": None})
        self.assertIn("No historical native record was supplied", identity["historical_evidence"])
        self.assertIn("no native acceptance is inferred", identity["historical_evidence"])

    def test_sealer_is_loaded_unchanged_without_deleted_build_source_replacement(self):
        with tempfile.TemporaryDirectory(prefix="bifrost-sealer-loader-") as temporary:
            source = Path(temporary) / "sealer.py"
            source.write_text("VALUE = 'sealer without any historical .build expression'\n")
            before = source.read_bytes()
            with mock.patch.object(builder, "PREPARE_SCRIPT", source):
                loaded = builder.load_prepare()
            self.assertEqual(loaded.VALUE, "sealer without any historical .build expression")
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(sorted(p.name for p in Path(temporary).iterdir()), ["sealer.py"])

    def test_manifest_keeps_old_measurement_under_explicit_historical_scope(self):
        identity = {"current_validation": {"mac_native": "Not run for this payload",
                                            "bifrost": "Not run for this payload"}}
        result = release_builder.device_acceptance(identity)
        self.assertEqual(result["current_payload"], identity["current_validation"])
        historical = result["historical_native_evidence"]
        self.assertEqual(historical["mac_native_wasm_peak"],
                         "Approximately 3.548 GB (accepted Mac native measurement)")
        self.assertIn("not a measurement or acceptance of the current payload", historical["scope"])
        self.assertEqual(historical["record"], "Provenance/StableOrchard-native-verification.json")
        self.assertNotIn("mac_native_wasm_peak", result)
        self.assertIn("not recorded", release_builder.device_acceptance({})["current_payload"]["scope"])

    def test_readme_describes_current_source_and_explicit_runtime_limits(self):
        with tempfile.TemporaryDirectory(prefix="bifrost-update-readme-") as temporary:
            folder = Path(temporary)
            bundle = folder / (NEW + ".tar.gz")
            bundle.write_bytes(b"synthetic archive")
            text = builder.readme(bundle, folder, 1024)
        self.assertIn("current-source update candidate", text)
        self.assertIn("current FarmVillage and sibling GodBarn", text)
        self.assertIn("This payload has not been run in the Mac native app", text)
        self.assertIn("historical evidence only", text)
        self.assertIn("Packaging alone does not establish", text)
        self.assertIn("without saving their old release pointers", text)
        self.assertNotIn("22 October 2026", text)
        self.assertNotIn("version you have been playing", text)
        self.assertNotIn("It works with a mouse", text)

    def test_publish_includes_the_scope_document_required_by_readme(self):
        with tempfile.TemporaryDirectory(prefix="bifrost-update-publish-") as temporary:
            work = Path(temporary) / "work"
            (work / "out").mkdir(parents=True)
            bundle = work / "out" / (NEW + ".tar.gz")
            write_tar(bundle, {NEW + "/fixture.txt": b"synthetic release"})
            bundle.with_name(bundle.name + ".manifest.json").write_text("{}\n")
            write_tar(work / "out/farmvillage-lan-host.tar.gz", {"hosting/fixture.txt": b"synthetic host"})
            output = Path(temporary) / "delivery"
            exact = "Full unit suites passed; final canvas gameplay smoke remains unpassed."
            with redirect_stdout(io.StringIO()):
                builder.publish(work, output, bundle, NEW, exact)
            self.assertEqual((output / "MECHANICS_RELEASE.md").read_bytes(),
                             (builder.PROJECT / "macOS/Documentation/MECHANICS_RELEASE.md").read_bytes())
            self.assertIn("MECHANICS_RELEASE.md", (output / "READ ME.txt").read_text())
            self.assertIn(exact, (output / "READ ME.txt").read_text())

    def test_publish_refuses_existing_output_without_mutating_it(self):
        with tempfile.TemporaryDirectory(prefix="bifrost-existing-output-") as temporary:
            output = Path(temporary) / "delivery"
            output.mkdir()
            original = output / "previous-release.tar.gz"
            original.write_bytes(b"retained")
            with self.assertRaises(FileExistsError):
                builder.publish(Path(temporary), output, Path(temporary) / "missing.tar.gz", NEW)
            self.assertEqual(original.read_bytes(), b"retained")
            self.assertEqual(sorted(p.name for p in output.iterdir()), [original.name])

    def test_source_parity_covers_helper_index_and_unexpected_companion_files(self):
        with tempfile.TemporaryDirectory(prefix="bifrost-source-parity-") as temporary:
            workspace = Path(temporary)
            project, barn, payload = workspace / "FarmVillage", workspace / "GodBarn", workspace / "Runtime"
            (project / "templates").mkdir(parents=True)
            (barn / "scripts").mkdir(parents=True)
            (barn / "data").mkdir()
            (payload / "GodBarn/data").mkdir(parents=True)
            (barn / "helper_tools.py").write_bytes(b"original helper\n")
            (barn / "data/untabbed.json").write_bytes(b'{"schema":1}\n')
            (barn / "scripts/bundle_companion.py").write_text(
                "from pathlib import Path\nimport shutil,sys\n"
                "source,destination=map(Path,sys.argv[1:])\n"
                "(destination/'data').mkdir(parents=True)\n"
                "for name in ['helper_tools.py','data/untabbed.json']:\n"
                " shutil.copyfile(source/name,destination/name)\n")
            for name in ("helper_tools.py", "data/untabbed.json"):
                shutil.copyfile(barn / name, payload / "GodBarn" / name)
            with mock.patch.object(builder, "PROJECT", project), mock.patch.object(builder, "WORKSPACE", workspace):
                self.assertEqual(builder.check_payload_matches_tree(payload), 2)
                for name in ("helper_tools.py", "data/untabbed.json"):
                    with self.subTest(resource=name):
                        target = payload / "GodBarn" / name
                        target.write_bytes(b"tampered")
                        with self.assertRaisesRegex(ValueError, "resource differs"):
                            builder.check_payload_matches_tree(payload)
                        shutil.copyfile(barn / name, target)
                (payload / "GodBarn/unexpected.py").write_bytes(b"extra")
                with self.assertRaisesRegex(ValueError, "inventory differs"):
                    builder.check_payload_matches_tree(payload)


class PublishedFolderTests(unittest.TestCase):
    """Check the built delivery folder, when present, against these sources."""
    folder = Path(os.environ.get("FARMVILLAGE_BIFROST_UPDATE_FOLDER", str(builder.DEFAULT_OUTPUT)))

    def setUp(self):
        if not self.folder.is_dir():
            self.skipTest("The delivery folder has not been built.")

    def test_folder_contents_sidecars_and_packaged_service_installer(self):
        bundles = list(self.folder.glob("farmvillage-portable-preparation-*.tar.gz"))
        self.assertEqual(len(bundles), 1)
        release = bundles[0].name[:-len(".tar.gz")]
        for archive in (bundles[0], self.folder / "farmvillage-lan-host.tar.gz"):
            digest, name = (archive.with_name(archive.name + ".sha256")).read_text().split()
            self.assertEqual((digest, name), (hashlib.sha256(archive.read_bytes()).hexdigest(), archive.name))
        self.assertEqual((self.folder / "manage-bifrost.sh").read_bytes(), (HERE / "manage-bifrost.sh").read_bytes())
        readme = (self.folder / "READ ME.txt").read_text()
        self.assertIn("NEVER RUN --fresh-start", readme)
        self.assertLess(readme.index("--check-saves"), readme.index("--install"))
        with tarfile.open(self.folder / "farmvillage-lan-host.tar.gz") as hosting:
            files = {member.name: hosting.extractfile(member).read() for member in hosting.getmembers()}
        self.assertEqual(files["hosting/activate-release.sh"], (HERE / "activate-release.sh").read_bytes())
        for name in ("start-server.sh", "install-service.sh"):
            text = files["hosting/" + name].decode()
            self.assertIn(release, text)
            self.assertNotIn(PREVIOUS, text)
        # Run the existing service-installer suite against the packaged copy.
        with tempfile.TemporaryDirectory(prefix="bifrost-update-service-") as temporary:
            directory = Path(temporary)
            (directory / "install-service.sh").write_bytes(files["hosting/install-service.sh"])
            suite = (HERE.parent / "Linux/test_install_service.py").read_text()
            self.assertEqual(suite.count(PREVIOUS), 1)
            (directory / "test_packaged_install_service.py").write_text(suite.replace(PREVIOUS, release))
            result = subprocess.run([sys.executable, "-B", "-m", "unittest", "-q", "test_packaged_install_service"],
                                    cwd=directory, capture_output=True, text=True, timeout=300)
            self.assertEqual(result.returncode, 0, result.stderr[-4000:])


if __name__ == "__main__":
    unittest.main()
