#!/usr/bin/env python3
"""REHEARSAL of the real Linux host runner against a synthetic stub game.

This is NOT a Bifrost install, NOT the guided setup wizard and NOT gameplay.

It starts the real FarmVillage/portable/Linux/server_runner.py as separate operating
system processes, on loopback, against a throwaway runtime whose game is a stub (only
the real native_paths.py, neighborhood_host.py and preloader_timing.py are real). It
exercises first-run password entry on a real terminal, the sign-in and request fences,
the single-owner lock, address refusal, the sign-in throttle, a SIGTERM that must let an
in-flight save finish, restart persistence and password rotation.

A pass here shows the runner's host behaviour on THIS machine with a stub game. It does
not show that the wizard, the systemd user service, the real game, the artwork or a LAN
address work. Those are the real acceptance run in docs/UBUNTU_ACCEPTANCE.md.

Exit status: 0 every check passed, 1 at least one check failed, 2 UNRUN (this host cannot
run the rehearsal, or the arguments were refused). Everything lives in a temporary folder
that is removed afterwards; only processes started here are ever signalled.
"""
from __future__ import annotations

import argparse
import http.client
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import secrets
import select
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time

DEFAULT_REPO = Path(__file__).resolve().parents[1]
LABEL = "REHEARSAL ONLY: this is NOT a Bifrost install, NOT the setup wizard and NOT gameplay. Real host runner, stub game, loopback only."
SCOPE = ("Real server_runner.py as separate OS processes on loopback with a STUB game. "
         "Not a Bifrost install, not the setup wizard, not gameplay, not a LAN address, not systemd.")

STUB_SERVER = '''
import json, os, time
from pathlib import Path
from flask import Flask, jsonify, request
TEMPLATES_DIR = str(Path(__file__).parent)
app = Flask(__name__)
DATA = Path(os.environ["FARMVILLAGE_DATA_DIR"])
SAVE = DATA / "saves" / "synthetic-farm.json"
def write_save(raw):
    with SAVE.open("wb") as out:
        out.write(raw); out.flush(); os.fsync(out.fileno())
@app.get("/play")
def play(): return "synthetic game page"
@app.get("/env")
def env(): return jsonify(data=os.environ["FARMVILLAGE_DATA_DIR"], native=os.environ.get("FARMVILLAGE_NATIVE"), cwd=os.getcwd())
@app.post("/save")
def save():
    write_save(request.get_data()); return jsonify(saved=True)
@app.post("/slow-save")
def slow_save():
    raw = request.get_data()
    (DATA / "slow-entered").touch()
    deadline = time.monotonic() + 20
    while not (DATA / "slow-release").exists():
        if time.monotonic() > deadline: return "release never came", 504
        time.sleep(0.02)
    write_save(raw); return jsonify(saved=True)
@app.get("/state")
def state(): return (SAVE.read_bytes(), 200) if SAVE.exists() else ("none", 404)
'''


class Refusal(Exception):
    """The rehearsal cannot run here; reported as UNRUN, never as a failure."""


class Rehearsal:
    def __init__(self, repo: Path):
        self.repo = repo
        self.runner = repo / "FarmVillage/portable/Linux/server_runner.py"
        self.native_paths = repo / "FarmVillage/macOS/Runtime/native_paths.py"
        self.results: list[dict] = []
        self.children: list[subprocess.Popen] = []

    # ------------------------------------------------------------------ plumbing
    def record(self, name: str, ok: bool, detail: str = "") -> None:
        self.results.append({"check": name, "result": "PASS" if ok else "FAIL", "detail": detail})
        print(("PASS  " if ok else "FAIL  ") + name + ("  | " + detail if detail else ""), flush=True)

    def command(self, runtime, data, port, *extra, bind="127.0.0.1"):
        return [sys.executable, "-B", str(self.runner), "--runtime", str(runtime), "--data-dir", str(data),
                "--bind", bind, "--port", str(port), "--public-url", f"http://{bind}:{port}", *extra]

    def start(self, argv):
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, env=child_environment())
        self.children.append(process)
        return process

    @staticmethod
    def finish(process, timeout=20):
        """Wait for a process expected to exit by itself; kill only our own handle if it hangs."""
        try:
            output, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate()
            return -9, output
        return process.returncode, output

    def stop(self, process, timeout=15):
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
        return self.finish(process, timeout)

    def tty(self, argv, answers, timeout=40):
        """Run argv on a real controlling terminal and answer its prompts, like an operator."""
        import pty
        pid, master = pty.fork()
        if pid == 0:
            os.execve(argv[0], argv, child_environment())
        transcript, pending, offset, deadline = b"", list(answers), 0, time.monotonic() + timeout
        while time.monotonic() < deadline:
            ready, _, _ = select.select([master], [], [], 0.2)
            if not ready:
                continue
            try:
                chunk = os.read(master, 4096)
            except OSError:
                break
            if not chunk:
                break
            transcript += chunk
            # Match each prompt only in output that arrived after the previous answer.
            if pending and pending[0][0].encode() in transcript[offset:]:
                os.write(master, (pending.pop(0)[1] + "\n").encode())
                offset = len(transcript)
        else:
            os.kill(pid, signal.SIGKILL)  # the child we forked, never a recorded PID
        _, status = os.waitpid(pid, 0)
        os.close(master)
        return os.waitstatus_to_exitcode(status), transcript.decode(errors="replace")

    def wait_ready(self, process, port, timeout=25):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process.poll() is not None:
                return False, (process.stdout.read() or "")[:200]
            with socket.socket() as probe:
                probe.settimeout(0.3)
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    return True, ""
            time.sleep(0.1)
        return False, "timed out"

    def build_world(self, work: Path):
        runtime, backend, data = work / "Runtime", work / "BackendHost", work / "data"
        (runtime / "GodBarn").mkdir(parents=True)
        backend.mkdir()
        (data / "assets/Environment").mkdir(parents=True)
        (data / "assets/xpromoSupport").mkdir(parents=True)
        (runtime / "server.py").write_text(STUB_SERVER)
        (runtime / "assets.py").write_text('import os\nASSETS_DIR = os.environ["FARMVILLAGE_DATA_DIR"] + "/assets"\ndef check_assets(): pass\n')
        for name in ("player", "bundle", "barn_actions"):
            (runtime / (name + ".py")).write_text("# synthetic\n")
        (runtime / "GodBarn/__init__.py").write_text("")
        (runtime / "GodBarn/integration.py").write_text(
            "def register_god_barn(app, *, game_server, player_module, bundle_module, farming_module, root):\n"
            "    app.extensions['god_barn'] = object()\n")
        shutil.copyfile(self.native_paths, backend / "native_paths.py")
        return runtime, data

    # ------------------------------------------------------------------ the checks
    def run(self, work: Path) -> None:
        runtime, data = self.build_world(work)
        password, port = "rehearsal-" + secrets.token_hex(6), free_port()
        origin, state = f"http://127.0.0.1:{port}", data / ".lan-server"
        save = data / "saves/synthetic-farm.json"

        # 1. Operator first run on a terminal.
        code, transcript = self.tty(self.command(runtime, data, port, "--init-only"),
                                    [("New server password: ", password), ("Repeat server password: ", password)])
        self.record("init-only-on-a-real-tty", code == 0 and "credentials are ready" in transcript, f"exit={code}")
        self.record("password-not-echoed", "New server password" in transcript and "Repeat server password" in transcript and password not in transcript,
                    "both prompts reached, typed text absent from the terminal")
        modes = {name: stat.S_IMODE((state / name).stat().st_mode) if (state / name).exists() else None for name in ("password.hash", "session.secret")}
        self.record("credential-files-private", modes == {"password.hash": 0o600, "session.secret": 0o600}
                    and state.is_dir() and stat.S_IMODE(state.stat().st_mode) == 0o700, str({k: oct(v) if v else v for k, v in modes.items()}))
        stored = (state / "password.hash").read_text() if (state / "password.hash").exists() else ""
        self.record("password-stored-as-a-salted-hash", bool(stored) and password not in stored and stored.startswith(("scrypt:", "pbkdf2:")))
        self.record("init-only-starts-no-game-and-saves-nothing", not save.exists())
        self.short_password_check(work, runtime)

        # 2. Service-style start (no terminal), as a user service would run it.
        first = self.start(self.command(runtime, data, port))
        ready, why = self.wait_ready(first, port)
        self.record("service-style-start-listens-on-loopback", ready, why)
        client = Client(port)
        status, body, _ = client.call("GET", "/play")
        self.record("unauthenticated-game-route-refused", status in (303, 401) and "synthetic game page" not in body, f"status={status}")
        status, _, headers = client.call("GET", "/")
        self.record("unauthenticated-root-redirects-to-sign-in", status == 303 and headers.get("Location") == "/server-login",
                    f"status={status} location={headers.get('Location')}")
        status, _, _ = client.call("GET", "/play", host="evil.test")
        self.record("wrong-host-header-refused", status in (400, 403), f"status={status} (400 or 403 as the project's own test allows)")
        status, _, _ = client.login(origin, "not-the-password")
        self.record("wrong-password-refused", status == 401, f"status={status}")
        status, _, headers = client.login(origin, password)
        self.record("correct-password-signs-in", status == 303 and headers.get("Location") == "/", f"status={status}")
        status, body, _ = client.call("GET", "/play")
        self.record("signed-in-cookie-reaches-the-game", status == 200 and "synthetic game page" in body)
        status, body, _ = client.call("GET", "/env")
        seen = json.loads(body) if status == 200 else {}
        self.record("runner-sets-data-dir-and-runs-from-runtime", seen.get("data") == str(data.resolve()) and seen.get("native") == "0"
                    and seen.get("cwd") == str(runtime.resolve()))
        status, _, _ = client.call("POST", "/save", b'{"coins":100}')
        self.record("post-without-origin-or-referer-fenced", status == 403, f"status={status}")
        status, _, _ = client.call("POST", "/save", b'{"coins":100}', {"Origin": "http://203.0.113.9:5501"})
        self.record("post-from-another-origin-fenced", status == 403, f"status={status}")
        status, _, _ = client.call("POST", "/save", b'{"coins":100}', {"Origin": origin})
        self.record("same-origin-post-saves-into-the-data-folder", status == 200 and save.exists() and save.read_bytes() == b'{"coins":100}')
        status, _, _ = client.call("GET", "/proxy?url=http://127.0.0.1/")
        self.record("arbitrary-url-proxy-disabled", status == 410, f"status={status}")

        # 3. Single owner and address policy.
        code, out = self.finish(self.start(self.command(runtime, data, free_port())))
        self.record("second-server-on-same-data-folder-refused", code == 1 and "already owns" in out, f"exit={code}")
        for bad, name in (("0.0.0.0", "wildcard-bind-refused"), ("8.8.8.8", "public-address-bind-refused")):
            code, out = self.finish(self.start(self.command(runtime, data, free_port(), bind=bad)))
            self.record(name, code == 1 and "wildcard binds are unsupported" in out, f"exit={code}")

        # 4. Sign-in throttle (last in this generation: it blocks sign-in for a minute).
        codes = [client.login(origin, "still-wrong-%d" % n)[0] for n in range(6)]
        self.record("repeated-wrong-passwords-are-throttled", 429 in codes, str(codes))

        # 5. SIGTERM must let an in-flight save finish before the process exits.
        self.drain_check(first, client, origin, data, save)

        # 6. Restart on the same data folder.
        second = self.start(self.command(runtime, data, port))
        ready, why = self.wait_ready(second, port)
        self.record("restart-on-the-same-data-folder", ready, why)
        status, body, _ = client.call("GET", "/play")
        self.record("sign-in-cookie-survives-restart", status == 200 and "synthetic game page" in body, f"status={status}")
        status, body, _ = client.call("GET", "/state")
        self.record("saved-state-survives-restart", status == 200 and body == '{"coins":250}', f"status={status}")

        # 7. Password rotation revokes old browser sign-ins.
        code, _ = self.stop(second)
        new_password = "rotated-" + secrets.token_hex(6)
        code, _ = self.tty(self.command(runtime, data, port, "--init-only", "--set-password"),
                           [("New server password: ", new_password), ("Repeat server password: ", new_password)])
        self.record("set-password-on-a-tty", code == 0, f"exit={code}")
        third = self.start(self.command(runtime, data, port))
        ready, why = self.wait_ready(third, port)
        status, _, _ = client.call("GET", "/play")
        self.record("old-cookie-revoked-after-rotation", ready and status in (303, 401), f"status={status}")
        old_status = Client(port).login(origin, password)[0]
        new_status = Client(port).login(origin, new_password)[0]
        self.record("old-password-fails-and-new-password-works", old_status == 401 and new_status == 303, f"old={old_status} new={new_status}")
        code, _ = self.stop(third)
        self.record("final-stop-is-clean", code == 0, f"exit={code}")
        leftover = [p.pid for p in self.children if p.poll() is None]
        self.record("no-process-from-this-run-is-left-alive", not leftover, str(leftover))

    def short_password_check(self, work, runtime):
        data = work / "short-data"
        (data / "assets/Environment").mkdir(parents=True)
        (data / "assets/xpromoSupport").mkdir(parents=True)
        code, transcript = self.tty(self.command(runtime, data, free_port(), "--init-only"),
                                    [("New server password: ", "seven77"), ("Repeat server password: ", "seven77")])
        self.record("seven-character-password-refused", code == 1 and "Passwords must match" in transcript
                    and not (data / ".lan-server/password.hash").exists(), f"exit={code}")

    def drain_check(self, process, client, origin, data, save):
        entered, release, outcome = data / "slow-entered", data / "slow-release", {}

        def request():
            try:
                outcome["reply"] = client.call("POST", "/slow-save", b'{"coins":250}', {"Origin": origin})
            except Exception as error:  # noqa: BLE001 - reported below
                outcome["error"] = repr(error)

        thread = threading.Thread(target=request)
        thread.start()
        deadline = time.monotonic() + 8
        while not entered.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        process.send_signal(signal.SIGTERM)
        time.sleep(0.7)
        still_serving = process.poll() is None and "reply" not in outcome
        release.touch()
        thread.join(15)
        code, _ = self.finish(process, 15)
        reply = outcome.get("reply")
        self.record("sigterm-lets-an-in-flight-save-finish-then-exits-zero",
                    entered.exists() and still_serving and bool(reply) and reply[0] == 200 and save.read_bytes() == b'{"coins":250}' and code == 0,
                    f"alive during={still_serving} reply={reply[0] if reply else outcome.get('error')} exit={code}")


class Client:
    def __init__(self, port):
        self.port, self.cookies = port, {}

    def call(self, method, path, body=None, headers=None, host=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        sent = dict(headers or {})
        if self.cookies:
            sent["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        if host:
            sent["Host"] = host
        connection.request(method, path, body=body, headers=sent)
        response = connection.getresponse()
        data = response.read().decode(errors="replace")
        for header, value in response.getheaders():
            if header.lower() == "set-cookie":
                name, _, rest = value.partition("=")
                self.cookies[name] = rest.split(";")[0]
        result = (response.status, data, dict(response.getheaders()))
        connection.close()
        return result

    def login(self, origin, password):
        _, page, _ = self.call("GET", "/server-login")
        token = re.search(r'name="token" value="([^"]+)"', page).group(1)
        return self.call("POST", "/server-login", f"token={token}&password={password}",
                         {"Origin": origin, "Content-Type": "application/x-www-form-urlencoded"})


def child_environment():
    keep = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR")
    return {**{key: os.environ[key] for key in keep if key in os.environ}, "PYTHONDONTWRITEBYTECODE": "1"}


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def unrun_reason(repo: Path):
    """Why this host cannot run the rehearsal (UNRUN), or None."""
    if os.name != "posix":
        return "needs a POSIX host with fcntl and pty"
    for module in ("fcntl", "pty", "flask"):
        if importlib.util.find_spec(module) is None:
            return f"the Python module '{module}' is not installed (python -m pip install -r FarmVillage/requirements.txt)"
    for relative in ("FarmVillage/portable/Linux/server_runner.py", "FarmVillage/macOS/Runtime/native_paths.py"):
        if not (repo / relative).is_file():
            return f"{repo / relative} is missing"
    try:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
    except OSError as error:
        return f"this host cannot bind a loopback port ({error})"
    return None


def environment_facts():
    facts = {"platform": platform.platform(), "python": platform.python_version(), "effectiveUid": os.geteuid(),
             "systemdRunning": Path("/run/systemd/system").is_dir(), "ubuntu": False}
    release = Path("/etc/os-release")
    if release.is_file():
        values = dict(line.split("=", 1) for line in release.read_text().splitlines() if "=" in line)
        facts["distribution"] = values.get("PRETTY_NAME", "").strip('"')
        facts["ubuntu"] = values.get("ID", "").strip('"') == "ubuntu"
    return facts


def wizard_preflight_note(repo: Path):
    """What step 1 of the wizard says on this host. Informational: it varies by host and is not scored."""
    path = repo / "tools/setup-wizard.py"
    if not path.is_file():
        return "setup-wizard.py not found"
    spec = importlib.util.spec_from_file_location("rehearsal_wizard_preflight", path)
    wizard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wizard)
    try:
        wizard.preflight()
        return "step 1 preflight completed without refusing on this host"
    except wizard.SetupError as error:
        return "step 1 preflight refused: " + str(error)
    except Exception as error:  # noqa: BLE001
        return "step 1 preflight could not be evaluated: " + repr(error)


def source_commit(repo: Path):
    try:
        done = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
        return done.stdout.strip() if done.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO, help="Source tree to rehearse (default: this checkout)")
    parser.add_argument("--receipt", type=Path, help="Write a JSON receipt to this NEW file, outside the source tree")
    arguments = parser.parse_args(argv)
    repo = arguments.repo.resolve()
    print(LABEL, flush=True)
    if arguments.receipt is not None:
        receipt = arguments.receipt.absolute()
        if receipt.exists() or receipt.is_symlink():
            print(f"UNRUN: refusing to overwrite {receipt}. Choose a new file name.")
            return 2
        if repo == receipt or repo in receipt.parents:
            print("UNRUN: the receipt must be written outside the source tree.")
            return 2
    reason = unrun_reason(repo)
    if reason:
        print("UNRUN: " + reason)
        return 2
    facts = environment_facts()
    print("ENVIRONMENT", json.dumps(facts), flush=True)
    note = wizard_preflight_note(repo)
    print("INFO (not scored): " + note, flush=True)
    work = Path(tempfile.mkdtemp(prefix="fv-rehearsal-"))
    rehearsal = Rehearsal(repo)
    try:
        rehearsal.run(work)
    finally:
        for child in rehearsal.children:
            if child.poll() is None:
                child.kill()
                child.communicate()
        if work.name.startswith("fv-rehearsal-"):  # the folder mkdtemp just made for this run
            shutil.rmtree(work, ignore_errors=True)
    passed = sum(item["result"] == "PASS" for item in rehearsal.results)
    failed = len(rehearsal.results) - passed
    print(f"\n{passed} PASS, {failed} FAIL of {len(rehearsal.results)} checks. {LABEL}", flush=True)
    if not facts["ubuntu"]:
        print("Note: this host is not Ubuntu, so this run says nothing about an Ubuntu host.")
    if arguments.receipt is not None:
        document = {"scope": SCOPE, "notBifrostInstall": True, "notGameplay": True, "sourceCommit": source_commit(repo),
                    "environment": facts, "wizardPreflightInfo": note, "passed": passed, "failed": failed,
                    "checks": rehearsal.results}
        with open(receipt, "x", encoding="utf-8") as stream:
            json.dump(document, stream, indent=2)
        print("Receipt written to " + str(receipt))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
