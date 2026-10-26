"""Isolated native-runtime regressions; no real game assets or user data are used.

Run with a Python 3.10+ environment containing the project's requirements:
    python -m unittest discover -s macOS/Tests -p test_runtime.py -v
"""

from __future__ import annotations

import contextlib
import gzip
import hashlib
import http.server
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import types
import unittest
from unittest import mock
import zipfile


PROJECT = Path(__file__).resolve().parents[2]
ADAPTER = PROJECT / "macOS" / "Runtime"


def load_module(name: str, filename: Path):
    spec = importlib.util.spec_from_file_location(name, filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


bootstrap = load_module("native_test_bootstrap", ADAPTER / "bootstrap.py")
native_assets = load_module("native_test_assets", ADAPTER / "native_assets.py")
compatibility_helper = load_module("native_test_ruffle_compatibility", PROJECT / "runtime_compatibility.py")


def wait_for(predicate, *, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Timed out waiting for the isolated subprocess fixture.")


@contextlib.contextmanager
def local_http(handler):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:" + str(server.server_port) + "/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class QuietHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def respond(self, body, status=200, headers=None):
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)


class TemporaryRuntimeCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="farmvillage-runtime-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        bootstrap.STOPPING = False
        bootstrap.STOP_REPORTED = False
        bootstrap.ACTIVE_CHILD = None

    def tearDown(self):
        bootstrap.STOPPING = False
        bootstrap.STOP_REPORTED = False
        bootstrap.ACTIVE_CHILD = None

    def source(self):
        source = self.root / "payload"
        source.mkdir()
        (source / "server.py").write_text("pass\n")
        (source / "requirements.txt").write_text("")
        (source / "old_module.py").write_text("OLD = True\n")
        (source / "xml").mkdir()
        (source / "xml" / "catalog.xml").write_text("<catalog/>\n")
        return source

    def ruffle(self, directory):
        directory.mkdir(parents=True)
        (directory / "ruffle.js").write_bytes(b"/* isolated test fixture */")
        (directory / "core.wasm").write_bytes(b"\0asm\x01\0\0\0")
        bootstrap.atomic_json(directory / ".farmvillage-ruffle.json", {
            "version": bootstrap.RUFFLE_VERSION,
            "files": {name: bootstrap.sha256(directory / name) for name in ("ruffle.js", "core.wasm")},
        })


class StagingTests(TemporaryRuntimeCase):
    def test_payload_update_removes_stale_modules_and_preserves_saves(self):
        source = self.source()
        data = self.root / "data"
        (data / "saves").mkdir(parents=True)
        saved = data / "saves" / "farm.json"
        saved.write_text("{\"farm\": 1}")
        runtime, initial = bootstrap.stage_runtime(source, data)
        self.assertTrue((runtime / "old_module.py").is_file())
        (source / "old_module.py").unlink()
        (source / "new_module.py").write_text("NEW = True\n")
        runtime, updated = bootstrap.stage_runtime(source, data)
        self.assertNotEqual(initial, updated)
        self.assertFalse((runtime / "old_module.py").exists())
        self.assertTrue((runtime / "new_module.py").is_file())
        self.assertEqual(saved.read_text(), "{\"farm\": 1}")
        self.assertFalse((data / ".runtime-previous").exists())

    def test_failed_publication_restores_previous_runtime(self):
        source = self.source()
        data = self.root / "data"
        data.mkdir()
        runtime, _ = bootstrap.stage_runtime(source, data)
        (source / "server.py").write_text("UPDATED = True\n")
        original_replace = os.replace

        def fail_publication(origin, destination):
            if Path(origin).name.startswith(".runtime-stage-") and Path(destination) == runtime:
                raise OSError("Simulated publication failure")
            original_replace(origin, destination)

        with mock.patch.object(bootstrap.os, "replace", side_effect=fail_publication):
            with self.assertRaisesRegex(OSError, "publication failure"):
                bootstrap.stage_runtime(source, data)
        self.assertEqual((runtime / "server.py").read_text(), "pass\n")
        self.assertFalse(list(data.glob(".runtime-stage-*")))

    def test_interrupted_rename_recovers_last_runtime(self):
        source = self.source()
        data = self.root / "data"
        data.mkdir()
        runtime, version = bootstrap.stage_runtime(source, data)
        runtime.rename(data / ".runtime-previous")
        recovered, recovered_version = bootstrap.stage_runtime(source, data)
        self.assertEqual(version, recovered_version)
        self.assertEqual(recovered, runtime)
        self.assertTrue((runtime / "server.py").is_file())

    def test_current_runtime_cleans_interrupted_staging_and_previous_copy(self):
        source = self.source()
        data = self.root / "data"
        data.mkdir()
        bootstrap.stage_runtime(source, data)
        for name in (".runtime-previous", ".runtime-stage-abandoned"):
            (data / name).mkdir()
            (data / name / "stale.py").write_text("stale")
        bootstrap.stage_runtime(source, data)
        self.assertFalse((data / ".runtime-previous").exists())
        self.assertFalse((data / ".runtime-stage-abandoned").exists())

    def test_staging_does_not_follow_abandoned_symlinks(self):
        source = self.source()
        data = self.root / "data"
        data.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "keep").write_text("preserved")
        (data / ".runtime-stage-link").symlink_to(outside, target_is_directory=True)
        bootstrap.stage_runtime(source, data)
        self.assertEqual((outside / "keep").read_text(), "preserved")


class PreparationTests(TemporaryRuntimeCase):
    def test_real_venv_pip_ignores_hostile_environment_and_config(self):
        wheel = self.root / "farmvillage_audit_dependency-1.0-py3-none-any.whl"
        info = "farmvillage_audit_dependency-1.0.dist-info/"
        members = {
            "farmvillage_audit_dependency.py": "VALUE = 'isolated'\n",
            info + "METADATA": "Metadata-Version: 2.1\nName: farmvillage-audit-dependency\nVersion: 1.0\n",
            info + "WHEEL": "Wheel-Version: 1.0\nGenerator: FarmVillage-audit\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        }
        members[info + "RECORD"] = "".join(name + ",,\n" for name in members) + info + "RECORD,,\n"
        with zipfile.ZipFile(wheel, "w") as archive:
            for name, contents in members.items():
                archive.writestr(name, contents)
        runtime = self.root / "runtime"
        runtime.mkdir()
        (runtime / "requirements.txt").write_text(str(wheel) + "\n")
        data = self.root / "data"
        data.mkdir()
        forbidden = self.root / "redirected-install"
        config = self.root / "hostile-pip.conf"
        config.write_text(f"[global]\ntarget = {forbidden}\n[install]\ndry-run = true\n")
        def local_compatibility(payload, profile):
            runtime_id = "0.7.1-prepare-fixture"
            directory = payload / "ruffle_runtime" / runtime_id
            directory.mkdir(parents=True)
            values = {"ruffle.js": b"offline reviewed loader", "core.wasm": b"\x00asm\x01\x00\x00\x00"}
            for name, value in values.items():
                (directory / name).write_bytes(value)
            manifest = {"schema": 1, "runtime_id": runtime_id, "version": "0.7.1",
                        "upstream_commit": "89a7049965f3090e706265670df309a5128233ac",
                        "files": {name: hashlib.sha256(value).hexdigest() for name, value in values.items()}}
            raw = json.dumps(manifest, sort_keys=True).encode()
            (directory / compatibility_helper.MANIFEST_NAME).write_bytes(raw)
            release = compatibility_helper.RuntimeRelease(runtime_id, "0.7.1", manifest["upstream_commit"], hashlib.sha256(raw).hexdigest())
            installed = compatibility_helper.install_runtime(payload, profile, release)
            return types.SimpleNamespace(ACTIVE_RELEASE=release), installed

        hostile = {
            "PIP_TARGET": str(forbidden), "PIP_DRY_RUN": "1", "PIP_CONFIG_FILE": str(config),
            "PIP_REQUIREMENT": str(self.root / "nonexistent-requirement"),
            "PYTHONPATH": str(self.root / "invalid-pythonpath"), "PYTHONHOME": str(self.root / "invalid-pythonhome"),
        }
        with mock.patch.dict(os.environ, hostile), \
             mock.patch.object(bootstrap, "compatibility_runtime", side_effect=local_compatibility), \
             mock.patch.object(bootstrap, "request_url", side_effect=AssertionError("Ruffle must install offline")):
            bootstrap.prepare(runtime, data, "isolated-payload")
        result = subprocess.run([str(data / "venv/bin/python"), "-I", "-B", "-c",
                                 "import farmvillage_audit_dependency as d; print(d.VALUE)"],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "isolated")
        self.assertFalse(forbidden.exists())
        self.assertEqual(json.loads((data / "prepared.json").read_text())["schema"], bootstrap.PREPARED_SCHEMA)

    def test_failed_prepare_removes_readiness_marker(self):
        runtime = self.root / "runtime"
        runtime.mkdir()
        (runtime / "requirements.txt").write_text("")
        data = self.root / "data"
        data.mkdir()
        (data / "prepared.json").write_text('{"schema": 2}')
        with mock.patch.object(bootstrap, "run_owned", side_effect=RuntimeError("Simulated setup failure")):
            with self.assertRaisesRegex(RuntimeError, "setup failure"):
                bootstrap.prepare(runtime, data, "payload")
        self.assertFalse((data / "prepared.json").exists())


class PathSafetyTests(TemporaryRuntimeCase):
    def setUp(self):
        super().setUp()
        self.data = self.root / "data"
        self.data.mkdir()
        self.external = self.root / "external"
        self.external.mkdir()
        self.sentinel = self.external / "sentinel"
        self.sentinel.write_bytes(b"unrelated content must survive")

    def assert_sentinel(self):
        self.assertEqual(self.sentinel.read_bytes(), b"unrelated content must survive")

    def asset_specification(self):
        temporary = self.data / "tmp"
        extracted = temporary / "extracted"
        return types.SimpleNamespace(
            ASSETS_DIR=str(self.data / "assets"), TMP_DIR=str(temporary),
            WARC_PATH=str(temporary / "warc"), EXTRACTION_PATH=str(extracted),
            EXTRACTED_INNER_ASSETS_PATH=str(extracted / "inner"), FILES=[],
            BASE_URL="http://127.0.0.1:1/",
        )

    def test_ruffle_parent_link_rejected_before_cleanup_or_download(self):
        stale = self.external / ".ruffle-download-unrelated"
        stale.mkdir()
        keep = stale / "keep"
        keep.write_bytes(b"external download")
        (self.data / "ruffle").symlink_to(self.external, target_is_directory=True)
        for action in (bootstrap.clean_ruffle_workspaces, bootstrap.install_ruffle):
            with self.subTest(action=action.__name__), mock.patch.object(bootstrap, "request_url", side_effect=AssertionError("No network is expected")):
                with self.assertRaisesRegex(RuntimeError, "symbolic link"):
                    action(self.data)
            self.assertEqual(keep.read_bytes(), b"external download")
            self.assert_sentinel()

    def test_prepare_rejects_venv_cache_or_marker_links_before_external_mutation(self):
        runtime = self.root / "runtime"
        runtime.mkdir()
        (runtime / "requirements.txt").write_text("")
        for name in ("venv", "cache", "prepared.json"):
            link = self.data / name
            link.symlink_to(self.sentinel if name == "prepared.json" else self.external,
                            target_is_directory=name != "prepared.json")
            with self.subTest(path=name), mock.patch.object(bootstrap, "run_owned", side_effect=AssertionError("No child may run")):
                with self.assertRaisesRegex(RuntimeError, "symbolic link"):
                    bootstrap.prepare(runtime, self.data, "payload")
            self.assert_sentinel()
            link.unlink()

    def test_atomic_marker_rejects_parent_or_leaf_link_and_uses_exclusive_temporary(self):
        parent_link = self.data / "linked"
        parent_link.symlink_to(self.external, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "symbolic link"):
            bootstrap.atomic_json(parent_link / "sentinel", {"overwrite": True}, data_root=self.data)
        destination = self.data / "prepared.json"
        destination.symlink_to(self.sentinel)
        with self.assertRaisesRegex(RuntimeError, "symbolic link"):
            bootstrap.atomic_json(destination, {"overwrite": True}, data_root=self.data)
        destination.unlink()
        legacy_temp = destination.with_name(destination.name + f".{os.getpid()}.tmp")
        legacy_temp.symlink_to(self.sentinel)
        bootstrap.atomic_json(destination, {"safe": True}, data_root=self.data)
        self.assertEqual(json.loads(destination.read_text()), {"safe": True})
        self.assert_sentinel()

    def test_main_rejects_redirected_temp_folder_or_lock(self):
        source = self.source()
        for name in ("tmp", ".runtime.lock"):
            link = self.data / name
            link.symlink_to(self.external if name == "tmp" else self.sentinel, target_is_directory=name == "tmp")
            result = subprocess.run([sys.executable, "-I", "-B", str(ADAPTER / "bootstrap.py"), "start",
                                     "--runtime", str(source), "--data-dir", str(self.data), "--token", "fixture"],
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("symbolic link", result.stdout)
            self.assert_sentinel()
            link.unlink()
            if name == "tmp":
                (self.data / "tmp").mkdir()

    def test_asset_temp_parent_link_cannot_redirect_cleanup_or_publication(self):
        assets = self.asset_specification()
        for name in ("Environment", "xpromoSupport"):
            (Path(assets.ASSETS_DIR) / name).mkdir(parents=True)
        for name in ("warc", "extracted"):
            (self.external / name).mkdir()
            (self.external / name / "keep").write_bytes(b"external temporary data")
        (self.external / ".farmvillage-assets-cleanup").touch()
        Path(assets.TMP_DIR).symlink_to(self.external, target_is_directory=True)
        for action in (native_assets.cleanup_completed_assets, native_assets.check_assets):
            with self.subTest(action=action.__name__):
                with self.assertRaisesRegex(RuntimeError, "symbolic link"):
                    action(assets)
            self.assert_sentinel()
            self.assertEqual((self.external / "warc" / "keep").read_bytes(), b"external temporary data")
            self.assertEqual((self.external / "extracted" / "keep").read_bytes(), b"external temporary data")

    def test_asset_archive_extraction_or_publication_links_are_rejected(self):
        assets = self.asset_specification()
        Path(assets.TMP_DIR).mkdir()
        for attribute in ("ASSETS_DIR", "WARC_PATH", "EXTRACTION_PATH"):
            link = Path(getattr(assets, attribute))
            link.symlink_to(self.external, target_is_directory=True)
            with self.subTest(path=attribute):
                with self.assertRaisesRegex(RuntimeError, "symbolic link"):
                    native_assets.check_assets(assets)
            self.assert_sentinel()
            link.unlink()
        Path(assets.EXTRACTION_PATH).mkdir()
        linked_parent = Path(assets.EXTRACTION_PATH) / "linked"
        linked_parent.symlink_to(self.external, target_is_directory=True)
        assets.EXTRACTED_INNER_ASSETS_PATH = str(linked_parent / "inner")
        with self.assertRaisesRegex(RuntimeError, "symbolic link"):
            native_assets.check_assets(assets)
        self.assert_sentinel()

    def test_partial_archive_link_is_rejected_before_network_or_write(self):
        assets = self.asset_specification()
        directory = Path(assets.WARC_PATH)
        directory.mkdir(parents=True)
        (directory / "tiny.warc.gz.part").symlink_to(self.sentinel)
        with mock.patch("requests.get", side_effect=AssertionError("No network is expected")):
            with self.assertRaisesRegex(RuntimeError, "symbolic link"):
                native_assets.download(assets, {"filename": "tiny.warc.gz", "hash": "0" * 32}, directory)
        self.assert_sentinel()

    def test_cleanup_marker_link_cannot_touch_external_file(self):
        assets = self.asset_specification()
        Path(assets.TMP_DIR).mkdir()
        (Path(assets.TMP_DIR) / ".farmvillage-assets-cleanup").symlink_to(self.sentinel)
        with self.assertRaisesRegex(RuntimeError, "symbolic link"):
            native_assets.cleanup_completed_assets(assets)
        self.assert_sentinel()

    def test_archive_cleanup_must_stay_in_temporary_folder(self):
        assets = self.asset_specification()
        assets.WARC_PATH = str(self.data / "saves")
        Path(assets.WARC_PATH).mkdir()
        saved = Path(assets.WARC_PATH) / "farm.json"
        saved.write_bytes(b"farm data")
        with self.assertRaisesRegex(RuntimeError, "inside the owned temporary folder"):
            native_assets.cleanup_completed_assets(assets)
        self.assertEqual(saved.read_bytes(), b"farm data")

    def test_venv_interpreter_leaf_link_is_permitted_but_linked_parent_is_rejected(self):
        binary = self.data / "venv/bin/python"
        binary.parent.mkdir(parents=True)
        binary.symlink_to(sys.executable)
        checked = bootstrap.owned_path(self.data, binary, allow_leaf_symlink=True)
        self.assertEqual(checked.resolve(), Path(sys.executable).resolve())
        with self.assertRaisesRegex(RuntimeError, "symbolic link"):
            bootstrap.owned_path(self.data, binary)
        parent = self.data / "other-venv"
        parent.symlink_to(self.external, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "symbolic link"):
            bootstrap.owned_path(self.data, parent / "bin/python", allow_leaf_symlink=True)


class OwnershipTests(TemporaryRuntimeCase):
    def supervisor(self, script):
        fixture = self.root / "supervisor.py"
        fixture.write_text(textwrap.dedent(script))
        process = subprocess.Popen([sys.executable, "-I", "-B", "-u", str(fixture)],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        self.addCleanup(self.reap, process)
        return process

    @staticmethod
    def reap(process):
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)

    def test_signal_during_wait_reaps_owned_descendants_and_preserves_other_process(self):
        child_info = self.root / "child.json"
        heartbeat = self.root / "descendant-heartbeat"
        descendant_code = (
            "import pathlib, signal, time; "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            f"p=pathlib.Path({str(heartbeat)!r}); "
            "exec('while True:\\n p.write_text(str(time.monotonic()))\\n time.sleep(.02)')"
        )
        child_code = (
            "import json, os, pathlib, subprocess, sys, time; "
            f"p=subprocess.Popen([sys.executable, '-I', '-B', '-c', {descendant_code!r}]); "
            f"pathlib.Path({str(child_info)!r}).write_text(json.dumps([os.getpid(), p.pid])); "
            "time.sleep(120)"
        )
        unrelated = subprocess.Popen([sys.executable, "-I", "-B", "-c", "import time; time.sleep(120)"])
        self.addCleanup(self.reap, unrelated)
        process = self.supervisor(f"""
            import importlib.util, signal, sys
            spec=importlib.util.spec_from_file_location('bootstrap', {str(ADAPTER / 'bootstrap.py')!r})
            b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
            signal.signal(signal.SIGTERM, b.interrupted)
            b.run_owned([sys.executable, '-I', '-B', '-c', {child_code!r}])
        """)
        wait_for(lambda: child_info.exists() and heartbeat.exists())
        child_pid = json.loads(child_info.read_text())[0]
        self.addCleanup(lambda: self.kill_group(child_pid))
        process.send_signal(signal.SIGTERM)
        output = process.communicate(timeout=8)[0].decode()
        self.assertEqual(process.returncode, 128 + signal.SIGTERM, output)
        old_heartbeat = heartbeat.read_bytes()
        time.sleep(0.15)
        self.assertEqual(heartbeat.read_bytes(), old_heartbeat)
        self.assertIsNone(unrelated.poll())

    @staticmethod
    def kill_group(pid):
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def test_nonzero_child_is_reported_and_reaped(self):
        with self.assertRaisesRegex(RuntimeError, "status 7"):
            bootstrap.run_owned([sys.executable, "-I", "-B", "-c", "raise SystemExit(7)"])
        self.assertIsNone(bootstrap.ACTIVE_CHILD)

    def test_data_lock_rejects_second_owner_and_releases_on_shutdown(self):
        source = self.source()
        data = self.root / "data"
        ready = self.root / "lock-owned"
        process = self.supervisor(f"""
            import importlib.util, pathlib, sys, time
            spec=importlib.util.spec_from_file_location('bootstrap', {str(ADAPTER / 'bootstrap.py')!r})
            b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
            def fake_prepare(*_args):
                pathlib.Path({str(ready)!r}).touch()
                while True:
                    b.check_cancelled()
                    time.sleep(.05)
            b.prepare=fake_prepare
            sys.argv=['bootstrap.py', 'prepare', '--runtime', {str(source)!r},
                      '--data-dir', {str(data)!r}, '--token', 'fixture-owner']
            b.main()
        """)
        wait_for(ready.exists)
        command = [sys.executable, "-I", "-B", str(ADAPTER / "bootstrap.py"), "start",
                   "--runtime", str(source), "--data-dir", str(data), "--token", "second-owner"]
        duplicate = subprocess.run(command, capture_output=True, text=True, timeout=5)
        self.assertEqual(duplicate.returncode, 1)
        self.assertIn("Another FarmVillage runtime already owns", duplicate.stdout)
        process.terminate()
        process.communicate(timeout=5)
        after = subprocess.run(command, capture_output=True, text=True, timeout=5)
        self.assertEqual(after.returncode, 1)
        self.assertIn("Prepare the runtime in the app", after.stdout)

    def test_data_payload_overlap_is_rejected_before_staging(self):
        source = self.source()
        data = source / "forbidden-data"
        result = subprocess.run([sys.executable, "-I", "-B", str(ADAPTER / "bootstrap.py"), "start",
                                 "--runtime", str(source), "--data-dir", str(data), "--token", "fixture"],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 1)
        self.assertIn("separate folders", result.stdout)
        self.assertFalse(data.exists())

    def test_parent_watchdog_requests_shutdown(self):
        finished = threading.Event()
        with mock.patch.object(bootstrap.os, "getppid", return_value=1):
            watcher = threading.Thread(target=bootstrap.watch_parent, args=(999999, finished))
            watcher.start()
            watcher.join(timeout=2)
        self.assertFalse(watcher.is_alive())
        with self.assertRaises(SystemExit) as stopped:
            bootstrap.check_cancelled()
        self.assertEqual(stopped.exception.code, 128 + signal.SIGTERM)

    def test_worker_watchdog_exits_orphaned_helper(self):
        process = self.supervisor(f"""
            import importlib.util, threading
            spec=importlib.util.spec_from_file_location('bootstrap', {str(ADAPTER / 'bootstrap.py')!r})
            b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
            b.watch_parent(999999, threading.Event(), worker=True)
            raise SystemExit(99)
        """)
        output = process.communicate(timeout=3)[0].decode()
        self.assertEqual(process.returncode, 128 + signal.SIGTERM, output)

    def test_abrupt_parent_exit_stops_actual_supervisor_and_owned_child(self):
        ready = self.root / "owned-child-pid"
        completed = self.root / "supervisor-cleaned"
        supervisor_path = self.root / "watched-supervisor.py"
        child_code = f"import os, pathlib, time; pathlib.Path({str(ready)!r}).write_text(str(os.getpid())); time.sleep(120)"
        supervisor_path.write_text(textwrap.dedent(f"""
            import importlib.util, os, pathlib, sys, threading
            spec=importlib.util.spec_from_file_location('bootstrap', {str(ADAPTER / 'bootstrap.py')!r})
            b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
            finished=threading.Event()
            threading.Thread(target=b.watch_parent, args=(os.getppid(), finished), daemon=True).start()
            try:
                b.run_owned([sys.executable, '-I', '-B', '-c', {child_code!r}])
            finally:
                finished.set()
                pathlib.Path({str(completed)!r}).touch()
        """))
        owner = self.supervisor(f"""
            import subprocess, sys, time
            subprocess.Popen([sys.executable, '-I', '-B', {str(supervisor_path)!r}],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(120)
        """)
        wait_for(ready.exists)
        child_pid = int(ready.read_text())
        self.addCleanup(lambda: self.kill_group(child_pid))
        owner.kill()
        owner.communicate(timeout=3)
        wait_for(completed.exists, timeout=8)
        # The supervisor reaches its finalizer only after run_owned has reaped
        # the server and killed any remaining process-group members.
        self.assertTrue(completed.is_file())

    def test_blocked_ruffle_network_read_is_cancellable_and_cleaned(self):
        release_request = threading.Event()
        unblock = threading.Event()
        data = self.root / "data"
        data.mkdir()

        class Handler(QuietHandler):
            def do_GET(self):
                if self.path == "/release":
                    self.respond(json.dumps({"tag_name": "v" + bootstrap.RUFFLE_VERSION, "assets": [{
                        "name": bootstrap.RUFFLE_ASSET, "browser_download_url": base + "ruffle.zip",
                    }]}).encode())
                else:
                    self.send_response(200)
                    self.send_header("Content-Length", "1048576")
                    self.end_headers()
                    self.wfile.write(b"P")
                    self.wfile.flush()
                    release_request.set()
                    unblock.wait(15)

        helper = self.root / "ruffle-helper.py"
        try:
            with local_http(Handler) as base:
                helper.write_text(textwrap.dedent(f"""
                    import importlib.util
                    spec=importlib.util.spec_from_file_location('bootstrap', {str(ADAPTER / 'bootstrap.py')!r})
                    b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
                    b.RUFFLE_RELEASE={base + 'release'!r}
                    b.RUFFLE_DOWNLOAD={base + 'ruffle.zip'!r}
                    b.ruffle_worker()
                """))
                process = self.supervisor(f"""
                    import importlib.util, os, pathlib, signal, sys
                    spec=importlib.util.spec_from_file_location('bootstrap', {str(ADAPTER / 'bootstrap.py')!r})
                    b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
                    signal.signal(signal.SIGTERM, b.interrupted)
                    try:
                        b.run_owned([sys.executable, '-I', '-B', '-u', {str(helper)!r}, '_install-ruffle',
                                     '--data-dir', {str(data)!r}, '--parent-pid', str(os.getpid())])
                    finally:
                        b.clean_ruffle_workspaces(pathlib.Path({str(data)!r}))
                """)
                self.assertTrue(release_request.wait(5))
                self.assertTrue(list((data / "ruffle").glob(".ruffle-download-*")))
                process.send_signal(signal.SIGTERM)
                output = process.communicate(timeout=8)[0].decode()
                self.assertEqual(process.returncode, 128 + signal.SIGTERM, output)
                self.assertFalse(list((data / "ruffle").glob(".ruffle-download-*")))
        finally:
            unblock.set()


class RuffleTests(TemporaryRuntimeCase):
    def archive(self, entries=None):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            for name, contents in (entries or {"dist/ruffle.js": b"// fake", "dist/core.wasm": b"\0asm\x01\0\0\0"}).items():
                archive.writestr(name, contents)
        return output.getvalue()

    def install(self, body, *, digest=None):
        digest = digest if digest is not None else "sha256:" + hashlib.sha256(body).hexdigest()

        class Handler(QuietHandler):
            def do_GET(self):
                if self.path == "/release":
                    self.respond(json.dumps({"tag_name": "v" + bootstrap.RUFFLE_VERSION, "assets": [{
                        "name": bootstrap.RUFFLE_ASSET, "browser_download_url": base + "ruffle.zip", "digest": digest,
                    }]}).encode())
                else:
                    self.respond(body)

        with local_http(Handler) as base:
            with mock.patch.multiple(bootstrap, RUFFLE_RELEASE=base + "release", RUFFLE_DOWNLOAD=base + "ruffle.zip"):
                return bootstrap.install_ruffle(self.root / "data")

    def test_official_digest_local_download_install_and_tamper_rejection(self):
        installed = self.install(self.archive())
        self.assertTrue(bootstrap.ruffle_valid(installed))
        (installed / "core.wasm").write_bytes(b"tampered")
        self.assertFalse(bootstrap.ruffle_valid(installed))
        self.assertFalse(list(installed.parent.glob(".ruffle-download-*")))

    def test_wrong_official_digest_is_rejected_and_cleaned(self):
        with self.assertRaisesRegex(RuntimeError, "integrity check"):
            self.install(self.archive(), digest="sha256:" + "0" * 64)
        self.assertFalse(list((self.root / "data" / "ruffle").glob(".ruffle-download-*")))

    def test_traversal_archive_is_rejected_without_writing_outside_workspace(self):
        with self.assertRaisesRegex(RuntimeError, "unsafe path"):
            self.install(self.archive({"../../escaped": b"unsafe", "ruffle.js": b"a", "core.wasm": b"b"}))
        self.assertFalse((self.root / "escaped").exists())

    def test_incomplete_archive_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "expected JavaScript"):
            self.install(self.archive({"ruffle.js": b"missing wasm"}))

    def test_manifest_escape_is_invalid(self):
        directory = self.root / "ruffle"
        self.ruffle(directory)
        manifest = directory / ".farmvillage-ruffle.json"
        value = json.loads(manifest.read_text())
        value["files"]["../escape"] = "0" * 64
        manifest.write_text(json.dumps(value))
        self.assertFalse(bootstrap.ruffle_valid(directory))


class DownloadTests(TemporaryRuntimeCase):
    content = b"synthetic archive bytes\n" * 100

    @contextlib.contextmanager
    def archive_server(self, mode="range"):
        calls = []
        content = self.content

        class Handler(QuietHandler):
            def do_GET(self):
                calls.append(dict(self.headers))
                offset = int(self.headers.get("Range", "bytes=0-").split("=")[1].split("-")[0])
                representation = content
                headers = {}
                if mode == "compressed-negotiation" and self.headers.get("Accept-Encoding") != "identity":
                    representation = gzip.compress(content)
                    headers["Content-Encoding"] = "gzip"
                if mode == "error":
                    self.respond(b"unavailable", 503)
                elif mode == "disconnect-once" and len(calls) == 1:
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content[:1024 * 1024 + 128])
                    self.wfile.flush()
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                elif mode == "invalid-length":
                    self.send_response(200)
                    self.send_header("Content-Length", "unknown")
                    self.end_headers()
                    self.wfile.write(content)
                elif offset >= len(representation):
                    self.respond(b"", 416)
                elif offset and mode != "ignore":
                    start = offset + 1 if mode == "wrong-range" else offset
                    headers["Content-Range"] = f"bytes {start}-{len(representation)-1}/{len(representation)}"
                    self.respond(representation[offset:], 206, headers)
                else:
                    self.respond(representation, headers=headers)

        with local_http(Handler) as base:
            yield types.SimpleNamespace(BASE_URL=base), calls

    def specification(self):
        return {"filename": "tiny.warc.gz", "hash": hashlib.md5(self.content).hexdigest()}

    def test_resumes_range_and_promotes_only_verified_archive(self):
        partial = self.root / "tiny.warc.gz.part"
        partial.write_bytes(self.content[:173])
        with self.archive_server() as (assets, calls):
            native_assets.download(assets, self.specification(), self.root)
        self.assertEqual(calls[0].get("Range"), "bytes=173-")
        self.assertEqual((self.root / "tiny.warc.gz").read_bytes(), self.content)
        self.assertFalse(partial.exists())

    def test_mirror_ignoring_range_restarts_instead_of_appending(self):
        (self.root / "tiny.warc.gz.part").write_bytes(self.content[:200])
        with self.archive_server("ignore") as (assets, calls):
            native_assets.download(assets, self.specification(), self.root)
        self.assertEqual(len(calls), 1)
        self.assertEqual((self.root / "tiny.warc.gz").read_bytes(), self.content)

    def test_resumes_archive_bytes_without_transport_compression(self):
        (self.root / "tiny.warc.gz.part").write_bytes(self.content[:30])
        with self.archive_server("compressed-negotiation") as (assets, calls):
            native_assets.download(assets, self.specification(), self.root)
        self.assertEqual(len(calls), 1)
        self.assertEqual((self.root / "tiny.warc.gz").read_bytes(), self.content)

    def test_stream_disconnect_resumes_from_written_archive_bytes(self):
        self.content = b"synthetic archive bytes\n" * 100000
        with self.archive_server("disconnect-once") as (assets, calls):
            native_assets.download(assets, self.specification(), self.root)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1].get("Range"), "bytes=1048576-")
        self.assertEqual((self.root / "tiny.warc.gz").read_bytes(), self.content)

    def test_invalid_progress_length_does_not_discard_valid_stream(self):
        with self.archive_server("invalid-length") as (assets, calls):
            native_assets.download(assets, self.specification(), self.root)
        self.assertEqual(len(calls), 1)
        self.assertEqual((self.root / "tiny.warc.gz").read_bytes(), self.content)

    def test_complete_partial_is_promoted_after_416(self):
        (self.root / "tiny.warc.gz.part").write_bytes(self.content)
        with self.archive_server() as (assets, calls):
            native_assets.download(assets, self.specification(), self.root)
        self.assertEqual(len(calls), 1)
        self.assertEqual((self.root / "tiny.warc.gz").read_bytes(), self.content)

    def test_invalid_oversized_partial_restarts_after_416(self):
        (self.root / "tiny.warc.gz.part").write_bytes(self.content + b"invalid")
        with self.archive_server() as (assets, calls):
            native_assets.download(assets, self.specification(), self.root)
        self.assertEqual(len(calls), 2)
        self.assertEqual((self.root / "tiny.warc.gz").read_bytes(), self.content)

    def test_wrong_range_does_not_append_untrusted_bytes(self):
        partial = self.root / "tiny.warc.gz.part"
        partial.write_bytes(self.content[:30])
        with self.archive_server("wrong-range") as (assets, calls):
            with self.assertRaisesRegex(RuntimeError, "Could not download"):
                native_assets.download(assets, self.specification(), self.root)
        self.assertEqual(len(calls), 3)
        self.assertEqual(partial.read_bytes(), self.content[:30])

    def test_network_failure_preserves_partial(self):
        partial = self.root / "tiny.warc.gz.part"
        partial.write_bytes(self.content[:30])
        with self.archive_server("error") as (assets, calls):
            with self.assertRaisesRegex(RuntimeError, "Could not download"):
                native_assets.download(assets, self.specification(), self.root)
        self.assertEqual(len(calls), 3)
        self.assertEqual(partial.read_bytes(), self.content[:30])

    def test_corrupt_complete_archive_is_replaced(self):
        (self.root / "tiny.warc.gz").write_bytes(b"bad archive")
        with self.archive_server() as (assets, calls):
            native_assets.download(assets, self.specification(), self.root)
        self.assertEqual(len(calls), 1)
        self.assertEqual((self.root / "tiny.warc.gz").read_bytes(), self.content)


class AssetPublicationTests(TemporaryRuntimeCase):
    def assets(self):
        temporary = self.root / "tmp"
        temporary.mkdir()
        extracted = temporary / "extracted"
        return types.SimpleNamespace(
            ASSETS_DIR=str(self.root / "assets"), TMP_DIR=str(temporary),
            WARC_PATH=str(temporary / "warc"), EXTRACTION_PATH=str(extracted),
            EXTRACTED_INNER_ASSETS_PATH=str(extracted / "inner"), FILES=[],
        )

    @staticmethod
    def extracted_fixture(assets):
        for name in ("Environment", "xpromoSupport"):
            directory = Path(assets.EXTRACTED_INNER_ASSETS_PATH) / name
            directory.mkdir(parents=True)
            (directory / "synthetic.swf").write_bytes(b"synthetic SWF")

    def test_publication_preserves_incomplete_assets_and_cleans_owned_temporary_files(self):
        assets = self.assets()
        Path(assets.ASSETS_DIR).mkdir()
        (Path(assets.ASSETS_DIR) / "old-file").write_text("keep")
        assets.assets_extract = lambda: self.extracted_fixture(assets)
        native_assets.check_assets(assets)
        self.assertEqual(list(self.root.glob("assets.incomplete-*/old-file"))[0].read_text(), "keep")
        self.assertTrue((Path(assets.ASSETS_DIR) / "Environment" / "synthetic.swf").is_file())
        self.assertFalse(Path(assets.WARC_PATH).exists())
        self.assertFalse(Path(assets.EXTRACTION_PATH).exists())
        self.assertFalse((Path(assets.TMP_DIR) / ".farmvillage-assets-cleanup").exists())

    def test_failed_publication_restores_incomplete_assets(self):
        assets = self.assets()
        destination = Path(assets.ASSETS_DIR)
        destination.mkdir()
        (destination / "old-file").write_text("keep")
        assets.assets_extract = lambda: self.extracted_fixture(assets)
        original_replace = os.replace

        def fail_publication(origin, target):
            if Path(origin).resolve() == Path(assets.EXTRACTED_INNER_ASSETS_PATH).resolve():
                raise OSError("Simulated publication failure")
            original_replace(origin, target)

        with mock.patch.object(native_assets.os, "replace", side_effect=fail_publication):
            with self.assertRaisesRegex(OSError, "publication failure"):
                native_assets.check_assets(assets)
        self.assertEqual((destination / "old-file").read_text(), "keep")

    def test_restarts_interrupted_extraction_from_verified_archives(self):
        assets = self.assets()
        stale = Path(assets.EXTRACTION_PATH) / "truncated.swf"
        stale.parent.mkdir()
        stale.write_bytes(b"truncated")

        def extraction():
            self.assertFalse(stale.exists())
            self.extracted_fixture(assets)

        assets.assets_extract = extraction
        native_assets.check_assets(assets)
        self.assertTrue((Path(assets.ASSETS_DIR) / "xpromoSupport" / "synthetic.swf").is_file())

    def test_complete_assets_resume_interrupted_cleanup(self):
        assets = self.assets()
        for name in ("Environment", "xpromoSupport"):
            (Path(assets.ASSETS_DIR) / name).mkdir(parents=True)
        for directory in (assets.EXTRACTION_PATH, assets.WARC_PATH):
            Path(directory).mkdir()
            (Path(directory) / "owned-temp").write_text("stale")
        (Path(assets.TMP_DIR) / ".farmvillage-assets-cleanup").touch()
        assets.assets_extract = mock.Mock(side_effect=AssertionError("Must not re-extract complete assets"))
        native_assets.check_assets(assets)
        self.assertFalse(Path(assets.EXTRACTION_PATH).exists())
        self.assertFalse(Path(assets.WARC_PATH).exists())

    def test_real_synthetic_warc_extraction_and_publication(self):
        extractor = load_module("native_test_warc", PROJECT / "warc_extractor" / "warc_extractor.py")
        assets = self.assets()
        warcs = Path(assets.WARC_PATH)
        warcs.mkdir()
        archive = warcs / "synthetic.warc.gz"
        assets.EXTRACTED_INNER_ASSETS_PATH = str(Path(assets.EXTRACTION_PATH) / "zynga1-a.akamaihd.net/farmville/assets/hashed/assets")
        with gzip.open(archive, "wb") as output:
            for name in ("Environment", "xpromoSupport"):
                payload = b"FWS\x09synthetic fixture"
                response = b"HTTP/1.1 200 OK\r\nContent-Type: application/x-shockwave-flash\r\nContent-Length: " + str(len(payload)).encode() + b"\r\n\r\n" + payload
                record = extractor.WARCRecord(payload=response, headers={
                    "WARC-Target-URI": f"http://zynga1-a.akamaihd.net/farmville/assets/hashed/assets/{name}/fixture.swf",
                })
                record.header.write_to(output)
                output.write(response + b"\r\n\r\n")
        assets.FILES = [{"filename": archive.name, "hash": native_assets.md5(archive)}]
        assets.assets_extract = lambda: extractor._main_interface(
            path=assets.WARC_PATH, output_path=assets.EXTRACTION_PATH, dump="content",
            filter=["WARC-Target-URI:zynga1-a.akamaihd.net/farmville/assets/hashed/assets"], silence=False,
        )
        native_assets.check_assets(assets)
        self.assertEqual((Path(assets.ASSETS_DIR) / "Environment" / "fixture.swf").read_bytes(), b"FWS\x09synthetic fixture")


if __name__ == "__main__":
    unittest.main()
