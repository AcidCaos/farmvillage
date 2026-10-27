#!/usr/bin/env python3
"""Serve an existing portable runtime on a private LAN, with browser sign-in.

This host is separate from the native Mac launcher and never modifies Runtime.
The only persistent host files live in DATA_DIR/.lan-server.
"""

from __future__ import annotations

import argparse
from collections import OrderedDict
from contextlib import contextmanager
import fcntl
import getpass
import importlib
import importlib.util
import ipaddress
import os
from pathlib import Path
import secrets
import signal
import socket
import sys
import threading
import time
from urllib.parse import urlsplit


AUTH_KEY = "_farmvillage_lan_authenticated"
CSRF_KEY = "_farmvillage_lan_csrf"
LOGIN_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FarmVillage · Your server</title><style>
body{font:18px system-ui;background:#f6f0df;color:#2f3828;max-width:26rem;margin:12vh auto;padding:1.5rem}
main{background:white;border-radius:1rem;padding:1.5rem}label,input,button{display:block;width:100%;box-sizing:border-box}
input,button{font:inherit;padding:.75rem;margin-top:.5rem}button{background:#436d34;color:white;border:0;border-radius:.4rem}
.error{color:#a32525}</style></head><body><main><h1>FarmVillage</h1>
<p>Enter your server password to open your farms and God Barn.</p>
{% if error %}<p class="error" role="alert">{{ error }}</p>{% endif %}
<form method="post" action="/server-login"><input type="hidden" name="token" value="{{ token }}">
<label>Server password<input type="password" name="password" autocomplete="current-password" required autofocus></label>
<button type="submit">Open FarmVillage</button></form></main></body></html>"""


def validate_address(bind: str, port: int, public_url: str) -> str:
    """Require an explicit private address; wildcard/public listening is absent."""
    try:
        address = ipaddress.IPv4Address(bind)
    except ipaddress.AddressValueError as error:
        raise ValueError("--bind must be the server's private IPv4 address.") from error
    networks = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "127.0.0.0/8")
    if not any(address in ipaddress.IPv4Network(network) for network in networks):
        raise ValueError("Use a private LAN, Tailscale, or loopback IPv4 address; public/wildcard binds are unsupported.")
    if not 1 <= port <= 65535:
        raise ValueError("--port must be between 1 and 65535.")
    expected = f"http://{address}:{port}"
    if public_url.rstrip("/") != expected:
        raise ValueError(f"--public-url must exactly match {expected}")
    return expected


def reject_old_loopback_server(bind: str, port: int) -> None:
    """The earlier SSH-only runner has no data lock; refuse to overlap it."""
    if ipaddress.IPv4Address(bind).is_loopback:
        return
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(1)
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            raise RuntimeError(
                f"An older server is still running on 127.0.0.1:{port}. "
                "Press Control-C in its Ubuntu terminal before starting the LAN server.")


def _ordinary_child(directory: Path, name: str) -> Path:
    path = directory / name
    if path.is_symlink():
        raise RuntimeError(f"A server file must not be a symbolic link: {path}")
    if path.exists() and not path.is_file():
        raise RuntimeError(f"A server file must be an ordinary file: {path}")
    return path


def _private_file(path: Path, contents: bytes) -> None:
    """Publish a new 0600 file exclusively, flushing its content before use."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(contents)
        stream.flush()
        os.fsync(stream.fileno())


@contextmanager
def data_ownership(data: Path):
    """Hold one OS lock throughout import, requests, and final server shutdown."""
    state = data / ".lan-server"
    if state.is_symlink():
        raise RuntimeError("The server state directory must not be a symbolic link.")
    state.mkdir(mode=0o700, exist_ok=True)
    state.chmod(0o700)
    lock_path = _ordinary_child(state, "owner.lock")
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another LAN server already owns this data folder. Stop it before starting again.") from error
        os.ftruncate(descriptor, 0)
        os.write(descriptor, f"{os.getpid()}\n".encode())
        yield state
    finally:
        os.close(descriptor)


def load_credentials(state: Path, *, reset_password: bool = False, prompt=getpass.getpass):
    from werkzeug.security import generate_password_hash

    secret_path = _ordinary_child(state, "session.secret")
    if not secret_path.exists():
        _private_file(secret_path, secrets.token_bytes(32))
    secret = secret_path.read_bytes()
    if len(secret) != 32:
        raise RuntimeError("The saved server session secret is invalid; restore .lan-server/session.secret.")
    secret_path.chmod(0o600)
    password_path = _ordinary_child(state, "password.hash")
    if reset_password or not password_path.exists():
        if not sys.stdin.isatty() and prompt is getpass.getpass:
            raise RuntimeError("First start needs a terminal to set the server password. Run this command interactively once.")
        print("[FarmVillage] Choose the browser password for this private server (at least 8 characters).", flush=True)
        password = prompt("New server password: ")
        confirmation = prompt("Repeat server password: ")
        if len(password) < 8 or len(password) > 1024 or not secrets.compare_digest(password.encode(), confirmation.encode()):
            raise RuntimeError("Passwords must match and contain 8–1024 characters. Start again to retry.")
        contents = (generate_password_hash(password) + "\n").encode()
        if password_path.exists():
            temporary = state / (".password-" + secrets.token_hex(12))
            try:
                _private_file(temporary, contents)
                os.replace(temporary, password_path)
            finally:
                temporary.unlink(missing_ok=True)
        else:
            _private_file(password_path, contents)
        # Rotating the secret makes --set-password also revoke old browser access.
        if reset_password:
            temporary = state / (".secret-" + secrets.token_hex(12))
            try:
                secret = secrets.token_bytes(32)
                _private_file(temporary, secret)
                os.replace(temporary, secret_path)
            finally:
                temporary.unlink(missing_ok=True)
        print("[FarmVillage] Your server password is ready. Use it in the browser to open your farm.", flush=True)
    password_hash = password_path.read_text().strip()
    if not password_hash.startswith(("scrypt:", "pbkdf2:")):
        raise RuntimeError("The saved password hash is invalid. Run once with --set-password.")
    password_path.chmod(0o600)
    return secret, password_hash


def register_lan_access(app, *, origin: str, secret: bytes, password_hash: str):
    """Fence every route, including Ruffle/WASM/assets, before game handlers."""
    from flask import Response, redirect, render_template_string, request, session
    from werkzeug.security import check_password_hash

    authority = urlsplit(origin).netloc
    app.secret_key = secret
    app.config.update(FARMVILLAGE_TRUSTED_ORIGINS=[origin], TRUSTED_HOSTS=[authority.split(":")[0]],
                      SESSION_COOKIE_NAME="farmvillage_lan", SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE="Strict", SESSION_COOKIE_SECURE=False,
                      PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 30)
    attempts = OrderedDict()
    attempt_lock = threading.Lock()

    def same_origin(value):
        try:
            parsed = urlsplit(value)
        except ValueError:
            return False
        return f"{parsed.scheme}://{parsed.netloc}" == origin

    def denied(message, status=403):
        return Response(message + "\n", status=status, mimetype="text/plain")

    @app.before_request
    def lan_request_gate():
        if request.host != authority:
            return denied("Use the configured FarmVillage server address.")
        supplied_origin = request.headers.get("Origin")
        if supplied_origin is not None and supplied_origin != origin:
            return denied("This origin cannot access FarmVillage.")
        fetch_site = request.headers.get("Sec-Fetch-Site", "")
        if fetch_site in ("cross-site", "same-site"):
            return denied("Open FarmVillage directly at its server address.")
        # The upstream game also contains creation/park/resume actions on GET.
        mutating_get = request.path in ("/new.html", "/god-barn/", "/god-barn/park", "/god-barn/resume")
        if request.method not in ("GET", "HEAD", "OPTIONS") or mutating_get:
            referred = same_origin(request.headers.get("Referer", ""))
            if supplied_origin != origin and not referred:
                return denied("Refresh FarmVillage before sending this action.")
        if request.path == "/server-login":
            return None
        if not session.get(AUTH_KEY):
            if request.method == "GET" and (request.path in ("/", "/ruffle.html", "/play.html", "/god-barn", "/god-barn/")
                                               or request.accept_mimetypes.best == "text/html"):
                return redirect("/server-login", code=303)
            return denied("Sign in at /server-login before accessing FarmVillage.", 401)
        # This upstream convenience endpoint fetches arbitrary URLs. The LAN
        # host serves local assets only, so it cannot proxy requests to Bifrost's
        # other services or the internet. Remote profile photos may be absent.
        if request.path == "/proxy":
            return denied("Remote profile-photo fetching is disabled on this server.", 410)

    @app.route("/server-login", methods=["GET", "POST"])
    def server_login():
        session.setdefault(CSRF_KEY, secrets.token_urlsafe(32))
        error = None
        status = 200
        if request.method == "POST":
            request.max_content_length = 4096
            token = request.form.get("token", "")
            if not secrets.compare_digest(token.encode(), session[CSRF_KEY].encode()):
                return denied("Refresh this sign-in page and try again.")
            remote = request.remote_addr or "unknown"
            now = time.monotonic()
            with attempt_lock:
                recent = [stamp for stamp in attempts.pop(remote, []) if now - stamp < 60]
                attempts[remote] = recent
                while len(attempts) > 512:
                    attempts.popitem(last=False)
                limited = len(recent) >= 5
                if not limited:
                    recent.append(now)
            if limited:
                response = denied("Too many password attempts. Wait one minute and try again.", 429)
                response.headers["Retry-After"] = "60"
                return response
            password = request.form.get("password", "")
            if len(password) <= 1024 and check_password_hash(password_hash, password):
                with attempt_lock:
                    attempts.pop(remote, None)
                session.clear()
                session[AUTH_KEY] = True
                session.permanent = True
                return redirect("/", code=303)
            error, status = "That password did not match. Try again.", 401
        return render_template_string(LOGIN_PAGE, token=session[CSRF_KEY], error=error), status

    @app.after_request
    def lan_response_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if request.path == "/server-login":
            response.headers["Cache-Control"] = "no-store"
            response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
        return response


def verify_existing_assets(assets):
    """Fail before loading game catalogs instead of beginning another download."""
    root = Path(assets.ASSETS_DIR)
    missing = [name for name in ("Environment", "xpromoSupport") if not (root / name).is_dir()]
    if missing:
        raise RuntimeError("Copied assets are missing required folders: " + ", ".join(missing) + ". Extract farmvillage-data.tar first; this server never downloads assets.")
    print("[FarmVillage] Using the copied local game assets; no downloads.", flush=True)


def load_integration(runtime: Path, overlay: Path | None):
    package = importlib.import_module("GodBarn")
    if overlay is None:
        return importlib.import_module("GodBarn.integration")
    if overlay.is_symlink() or not overlay.is_file():
        raise RuntimeError("The God Barn integration overlay must be an ordinary local file.")
    spec = importlib.util.spec_from_file_location("GodBarn.integration", overlay)
    if spec is None or spec.loader is None:
        raise RuntimeError("The God Barn integration overlay could not be loaded.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    package.integration = module
    return module


def serve_with_shutdown(httpd):
    """Drain request threads before releasing the data lock on stop/reboot."""
    requested = threading.Event()
    previous = {}

    def stop(signum, frame):
        if not requested.is_set():
            requested.set()
            # BaseServer.shutdown waits for serve_forever; it must run on a
            # different thread from the one currently serving requests.
            threading.Thread(target=httpd.shutdown, name="farmvillage-stop", daemon=True).start()

    for number in (signal.SIGINT, signal.SIGTERM):
        previous[number] = signal.signal(number, stop)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        for number, handler in previous.items():
            signal.signal(number, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--bind", required=True)
    parser.add_argument("--port", type=int, default=5501)
    parser.add_argument("--public-url", required=True)
    parser.add_argument("--backend-host", type=Path)
    parser.add_argument("--integration-module-file", type=Path)
    parser.add_argument("--set-password", action="store_true", help="Set a new password and revoke existing browser sign-ins.")
    parser.add_argument("--init-only", action="store_true", help="Initialize host credentials and exit without starting the game.")
    arguments = parser.parse_args()
    origin = validate_address(arguments.bind, arguments.port, arguments.public_url)
    runtime = arguments.runtime.expanduser().resolve()
    overlay = arguments.integration_module_file.expanduser().absolute() if arguments.integration_module_file else None
    backend = (arguments.backend_host or runtime.parent / "BackendHost").expanduser().resolve()
    data = arguments.data_dir.expanduser().resolve()
    if not runtime.is_dir() or not (runtime / "server.py").is_file() or not backend.is_dir():
        raise RuntimeError("Select the extracted portable Runtime and BackendHost folders.")
    if data == runtime or runtime in data.parents or data in runtime.parents:
        raise RuntimeError("Keep the copied data folder separate from Runtime.")
    reject_old_loopback_server(arguments.bind, arguments.port)
    data.mkdir(parents=True, exist_ok=True)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(backend))
    from native_paths import owned_path
    for name in ("assets", "saves", "god-barn", "cache", "tmp"):
        owned_path(data, data / name).mkdir(parents=True, exist_ok=True)
    for name in ("Environment", "xpromoSupport"):
        owned_path(data, data / "assets" / name)
    with data_ownership(data) as state:
        secret, password_hash = load_credentials(state, reset_password=arguments.set_password)
        if arguments.init_only:
            print("[FarmVillage] Server credentials are ready for background startup.", flush=True)
            return
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            try:
                listener.bind((arguments.bind, arguments.port))
            except OSError as error:
                raise RuntimeError(f"Cannot listen at {origin}. Stop the old server and check your server’s IP address.") from error
            os.environ["FARMVILLAGE_DATA_DIR"] = str(data)
            os.environ["FARMVILLAGE_NATIVE"] = "0"
            os.chdir(runtime)
            sys.path.insert(0, str(runtime))
            prepared_path = runtime / "PREPARED_RUNTIME.json"
            if prepared_path.is_file():
                import json
                import runtime_compatibility
                if prepared_path.is_symlink():
                    raise RuntimeError("Linked runtime identity refused")
                prepared = json.loads(prepared_path.read_text())
                release = runtime_compatibility.select_runtime_release(runtime, prepared_pin_sha256=prepared["runtime_manifest_sha256"])
                os.environ["FARMVILLAGE_PREPARED_RUNTIME_PIN_SHA256"] = release.manifest_sha256
            assets = importlib.import_module("assets")
            assets.check_assets = lambda: verify_existing_assets(assets)
            from neighborhood_host import activate_neighborhood, configure_neighborhood
            neighborhood = activate_neighborhood(data, runtime)
            sys.argv = [str(runtime / "server.py"), "--host", arguments.bind, "--port", str(arguments.port), "--public-url", origin]
            server = importlib.import_module("server")
            server.app.root_path = str(runtime)
            server.app.template_folder = server.TEMPLATES_DIR
            server.app.static_folder = server.TEMPLATES_DIR
            register_lan_access(server.app, origin=origin, secret=secret, password_hash=password_hash)
            integration = load_integration(runtime, overlay)
            integration.register_god_barn(server.app, game_server=server,
                                          player_module=importlib.import_module("player"),
                                          bundle_module=importlib.import_module("bundle"),
                                          farming_module=importlib.import_module("barn_actions"), root=runtime / "GodBarn")
            configure_neighborhood(server, importlib.import_module("player"), neighborhood)
            from preloader_timing import configure_preloader
            configure_preloader(server.app)
            from werkzeug.serving import make_server
            listener.listen(128)
            httpd = make_server(arguments.bind, arguments.port, server.app, threaded=True, fd=listener.fileno())
            # Keep the data lock until in-flight saves finish during shutdown.
            httpd.daemon_threads = False
            listener.close()
            print(f"[FarmVillage] Ready. Open {origin}/ in your browser.", flush=True)
            print("[FarmVillage] Choose your farm, then use the God Barn button above the game.", flush=True)
            serve_with_shutdown(httpd)
        finally:
            listener.close()


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as error:
        print(f"[FarmVillage] ERROR: {error}", flush=True)
        raise SystemExit(1)
