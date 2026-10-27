"""LAN host boundaries with real Flask cookies and temporary host credentials."""

import importlib.util
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import signal
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock
import urllib.request

from flask import Flask, jsonify, session
from werkzeug.security import check_password_hash, generate_password_hash


spec = importlib.util.spec_from_file_location("farmvillage_lan_host", Path(__file__).with_name("server_runner.py"))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

ORIGIN = "http://192.168.50.80:5501"
PASSWORD = "bifrost-test-password"


class LanAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password_hash = generate_password_hash(PASSWORD, method="pbkdf2:sha256:1000")

    def make_app(self, secret=b"s" * 32):
        app = Flask("lan-access-tests")
        app.config["TESTING"] = True
        runner.register_lan_access(app, origin=ORIGIN, secret=secret, password_hash=self.password_hash)

        @app.get("/")
        def index():
            session.pop("UID", None)  # Existing farm selector's logout behavior.
            return "choose farm"

        @app.get("/assets/original.swf")
        @app.get("/ruffle/core.wasm")
        @app.get("/health")
        @app.get("/proxy")
        def resource():
            return "private bytes"

        @app.post("/flashservices/gateway.php")
        def mutation():
            return jsonify(committed=True)

        @app.get("/new.html")
        @app.get("/god-barn/")
        @app.get("/god-barn/park")
        @app.get("/god-barn/resume")
        def old_mutation():
            return "mutated"

        return app

    def setUp(self):
        self.app = self.make_app()
        self.client = self.app.test_client()

    def get(self, path, **kwargs):
        return self.client.get(path, base_url=ORIGIN, **kwargs)

    def post(self, path, **kwargs):
        return self.client.post(path, base_url=ORIGIN, **kwargs)

    def login_token(self):
        page = self.get("/server-login")
        self.assertEqual(page.status_code, 200)
        return re.search(rb'name="token" value="([^"]+)"', page.data)[1].decode()

    def login(self):
        return self.post("/server-login", data={"token": self.login_token(), "password": PASSWORD}, headers={"Origin": ORIGIN})

    def test_every_game_and_asset_route_requires_browser_authentication(self):
        for path in ("/assets/original.swf", "/ruffle/core.wasm", "/health", "/proxy"):
            with self.subTest(path=path):
                response = self.get(path)
                self.assertEqual(response.status_code, 401)
                self.assertNotIn(b"private bytes", response.data)
        self.assertEqual(self.get("/").headers["Location"], "/server-login")
        self.assertEqual(self.post("/flashservices/gateway.php", headers={"Origin": ORIGIN}).status_code, 401)

    def test_valid_login_signs_cookie_and_game_selector_does_not_log_out_server_auth(self):
        response = self.login()
        self.assertEqual(response.status_code, 303)
        cookie = response.headers["Set-Cookie"]
        for option in ("HttpOnly", "SameSite=Strict", "Expires="):
            self.assertIn(option, cookie)
        self.assertNotIn(PASSWORD, cookie)
        self.assertEqual(self.get("/").data, b"choose farm")
        self.assertEqual(self.get("/ruffle/core.wasm").data, b"private bytes")
        self.assertEqual(self.get("/assets/original.swf").data, b"private bytes")

    def test_unsafe_requests_need_exact_origin_or_same_origin_referrer(self):
        self.login()
        for headers in ({}, {"Origin": "http://attacker.test"},
                        {"Origin": "null"}, {"Origin": "", "Referer": ORIGIN + "/ruffle.html"},
                        {"Referer": ORIGIN + ".attacker.test/page"},
                        {"Origin": ORIGIN, "Sec-Fetch-Site": "cross-site"},
                        {"Origin": ORIGIN, "Sec-Fetch-Site": "same-site"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.post("/flashservices/gateway.php", headers=headers).status_code, 403)
        for headers in ({"Origin": ORIGIN}, {"Referer": ORIGIN + "/ruffle.html"},
                        {"Referer": ORIGIN + "/ruffle.html", "Sec-Fetch-Site": "same-origin"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.post("/flashservices/gateway.php", headers=headers).status_code, 200)

    def test_mutating_legacy_gets_are_fenced_and_authenticated(self):
        self.login()
        for path in ("/new.html", "/god-barn/", "/god-barn/park", "/god-barn/resume"):
            with self.subTest(path=path):
                self.assertEqual(self.get(path).status_code, 403)
                self.assertEqual(self.get(path, headers={"Referer": ORIGIN + "/ruffle.html"}).status_code, 200)
                self.assertEqual(self.get(path, headers={"Referer": ORIGIN + "/ruffle.html", "Sec-Fetch-Site": "cross-site"}).status_code, 403)

    def test_host_rebinding_and_other_origins_rejected_before_login(self):
        for url in ("http://evil.test:5501", "http://192.168.50.80:9999", "http://localhost:5501"):
            with self.subTest(url=url):
                self.assertIn(self.client.get("/server-login", base_url=url).status_code, (400, 403))
        self.assertEqual(self.get("/server-login", headers={"Origin": "http://evil.test"}).status_code, 403)

    def test_login_csrf_wrong_password_and_rate_limit(self):
        token = self.login_token()
        self.assertEqual(self.post("/server-login", data={"token": "wrong", "password": PASSWORD}, headers={"Origin": ORIGIN}).status_code, 403)
        self.assertEqual(self.post("/server-login", data={"token": token, "password": PASSWORD}).status_code, 403)
        for _ in range(5):
            response = self.post("/server-login", data={"token": token, "password": "incorrect"}, headers={"Origin": ORIGIN})
            self.assertEqual(response.status_code, 401)
        response = self.post("/server-login", data={"token": token, "password": PASSWORD}, headers={"Origin": ORIGIN})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["Retry-After"], "60")

    def test_remote_proxy_stays_disabled_even_after_signin(self):
        self.login()
        self.assertEqual(self.get("/proxy?url=http://127.0.0.1/admin").status_code, 410)

    def test_secret_persists_cookie_across_restart_and_rotation_revokes_it(self):
        response = self.login()
        cookie = response.headers["Set-Cookie"].split(";", 1)[0].split("=", 1)[1]
        for secret, expected in ((b"s" * 32, 200), (b"r" * 32, 401)):
            client = self.make_app(secret).test_client()
            client.set_cookie("farmvillage_lan", cookie, domain="192.168.50.80")
            self.assertEqual(client.get("/ruffle/core.wasm", base_url=ORIGIN).status_code, expected)


class HostStateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="farmvillage-lan-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_private_bind_and_exact_origin(self):
        for bind in ("192.168.50.80", "10.2.3.4", "172.17.0.4", "100.69.163.49", "127.0.0.1"):
            origin = f"http://{bind}:5501"
            self.assertEqual(runner.validate_address(bind, 5501, origin + "/"), origin)
        for bind, port, origin in (("0.0.0.0", 5501, "http://0.0.0.0:5501"),
                                  ("8.8.8.8", 5501, "http://8.8.8.8:5501"),
                                  ("192.168.50.80", 5501, "http://evil.test:5501"),
                                  ("192.168.50.80", 5501, "http://192.168.50.80:5501/path"),
                                  ("192.168.50.80", 0, "http://192.168.50.80:0")):
            with self.subTest(bind=bind, origin=origin), self.assertRaises(ValueError):
                runner.validate_address(bind, port, origin)

    def test_second_owner_fails_until_first_releases_root(self):
        with runner.data_ownership(self.root):
            with self.assertRaisesRegex(RuntimeError, "already owns"):
                with runner.data_ownership(self.root):
                    self.fail("A second server took the same data root.")
        with runner.data_ownership(self.root) as state:
            self.assertEqual(state.name, ".lan-server")

    def test_ssh_only_server_is_rejected_before_lan_start(self):
        with mock.patch.object(runner.socket, "socket") as factory:
            probe = factory.return_value.__enter__.return_value
            probe.connect_ex.return_value = 0
            with self.assertRaisesRegex(RuntimeError, "Control-C"):
                runner.reject_old_loopback_server("192.168.50.80", 5501)
            probe.connect_ex.assert_called_once_with(("127.0.0.1", 5501))
            runner.reject_old_loopback_server("127.0.0.1", 5501)
            probe.connect_ex.assert_called_once()
            probe.connect_ex.return_value = 61  # Connection refused: no old owner.
            runner.reject_old_loopback_server("192.168.50.80", 5501)

    def test_password_and_secret_persist_and_reset_revokes_secret(self):
        with runner.data_ownership(self.root) as state:
            first = runner.load_credentials(state, prompt=lambda _: PASSWORD)
            second = runner.load_credentials(state, prompt=lambda _: self.fail("Existing password prompted again."))
            self.assertEqual(first, second)
            self.assertTrue(check_password_hash(first[1], PASSWORD))
            for name in ("password.hash", "session.secret"):
                self.assertEqual(stat.S_IMODE((state / name).stat().st_mode), 0o600)
            reset = runner.load_credentials(state, reset_password=True, prompt=lambda _: "replacement-password")
            self.assertNotEqual(reset[0], first[0])
            self.assertTrue(check_password_hash(reset[1], "replacement-password"))
            self.assertFalse(check_password_hash(reset[1], PASSWORD))

    def test_state_and_credential_symlinks_fail_closed(self):
        state = self.root / ".lan-server"
        outside = self.root / "outside"
        outside.mkdir()
        state.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "symbolic link"):
            with runner.data_ownership(self.root):
                pass
        state.unlink()
        with runner.data_ownership(self.root) as state:
            (state / "session.secret").symlink_to(outside / "secret")
            with self.assertRaisesRegex(RuntimeError, "symbolic link"):
                runner.load_credentials(state, prompt=lambda _: PASSWORD)

    def test_missing_assets_fail_without_invoking_download(self):
        assets = SimpleNamespace(ASSETS_DIR=str(self.root / "assets"))
        with self.assertRaisesRegex(RuntimeError, "never downloads"):
            runner.verify_existing_assets(assets)
        for name in ("Environment", "xpromoSupport"):
            (self.root / "assets" / name).mkdir(parents=True)
        runner.verify_existing_assets(assets)

    def test_noninteractive_initialization_never_imports_game_or_changes_saves(self):
        release = self.root / "release"
        runtime = release / "Runtime"
        backend = release / "BackendHost"
        runtime.mkdir(parents=True)
        backend.mkdir()
        (runtime / "server.py").write_text("raise RuntimeError('init-only imported gameplay')\n")
        project = Path(__file__).resolve().parents[2]
        shutil.copyfile(project / "macOS/Runtime/native_paths.py", backend / "native_paths.py")
        data = self.root / "data"
        (data / "saves").mkdir(parents=True)
        saved = data / "saves/existing.json"
        saved.write_bytes(b'{"preserve":true}\n')
        before = saved.stat().st_mtime_ns
        with runner.data_ownership(data) as state:
            runner.load_credentials(state, prompt=lambda _: PASSWORD)
        result = subprocess.run(
            [sys.executable, "-B", str(Path(__file__).with_name("server_runner.py")),
             "--runtime", str(runtime), "--data-dir", str(data), "--bind", "127.0.0.1",
             "--public-url", "http://127.0.0.1:5501", "--init-only"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("credentials are ready", result.stdout)
        self.assertEqual(saved.read_bytes(), b'{"preserve":true}\n')
        self.assertEqual(saved.stat().st_mtime_ns, before)

    def test_sigterm_drains_inflight_http_save_before_releasing_data_lock(self):
        # A real child owns the flock and runs the production shutdown function.
        # The synthetic request cannot complete until this parent releases it.
        child_source = r'''
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
from werkzeug.serving import make_server

spec = importlib.util.spec_from_file_location("shutdown_test_runner", sys.argv[1])
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
data = Path(sys.argv[2])

def app(environ, start_response):
    (data / "request-entered").touch()
    deadline = time.monotonic() + 12
    while not (data / "release-request").exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("The parent did not release the test request.")
        time.sleep(0.02)
    with (data / "saved-marker").open("wb") as output:
        output.write(b"saved durably\n")
        output.flush()
        os.fsync(output.fileno())
    directory = os.open(data, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    start_response("200 OK", [("Content-Type", "text/plain")])
    return [b"save completed"]

with runner.data_ownership(data):
    httpd = make_server("127.0.0.1", 0, app, threaded=True)
    httpd.daemon_threads = False
    original_close = httpd.server_close
    def observed_close():
        (data / "drain-entered").touch()
        original_close()
    httpd.server_close = observed_close
    (data / "listener-ready.json").write_text(json.dumps({"port": httpd.server_port}))
    runner.serve_with_shutdown(httpd)
'''
        child = subprocess.Popen(
            [sys.executable, "-B", "-c", child_source,
             str(Path(__file__).with_name("server_runner.py").resolve()), str(self.root)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        executor = ThreadPoolExecutor(max_workers=1)

        def wait_for(path):
            deadline = time.monotonic() + 5
            while not path.exists():
                if child.poll() is not None:
                    stdout, stderr = child.communicate()
                    self.fail(f"Child exited before {path.name}: {stdout}{stderr}")
                if time.monotonic() >= deadline:
                    self.fail(f"Timed out waiting for {path.name}.")
                time.sleep(0.02)

        def send_request(port):
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(f"http://127.0.0.1:{port}/save", timeout=10) as response:
                return response.status, response.read()

        try:
            ready = self.root / "listener-ready.json"
            wait_for(ready)
            port = json.loads(ready.read_text())["port"]
            response = executor.submit(send_request, port)
            wait_for(self.root / "request-entered")
            child.send_signal(signal.SIGTERM)
            wait_for(self.root / "drain-entered")
            self.assertIsNone(child.poll(), "Shutdown exited while an HTTP save was still running.")
            self.assertFalse(response.done(), "The HTTP request escaped its release gate.")
            self.assertFalse((self.root / "saved-marker").exists())
            with self.assertRaisesRegex(RuntimeError, "already owns"):
                with runner.data_ownership(self.root):
                    self.fail("Shutdown released the data lock before the save finished.")
            (self.root / "release-request").touch()
            self.assertEqual(response.result(timeout=5), (200, b"save completed"))
            stdout, stderr = child.communicate(timeout=5)
            self.assertEqual(child.returncode, 0, stdout + stderr)
            self.assertEqual((self.root / "saved-marker").read_bytes(), b"saved durably\n")
            with runner.data_ownership(self.root):
                pass
        finally:
            (self.root / "release-request").touch()
            if child.poll() is None:
                child.terminate()
                try:
                    child.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.communicate(timeout=5)
            executor.shutdown(wait=True)


if __name__ == "__main__":
    unittest.main()
