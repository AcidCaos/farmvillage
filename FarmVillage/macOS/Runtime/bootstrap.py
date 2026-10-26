"""Native wrapper setup and lifecycle supervision. No game assets are fetched by prepare."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import urllib.request
import zipfile

# Isolated Python omits its script directory. Add only our bundled helper folder.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_paths import owned_path


RUFFLE_VERSION = "0.7.1"
RUFFLE_ASSET = "ruffle-0.7.1-web-selfhosted.zip"
RUFFLE_RELEASE = "https://api.github.com/repos/ruffle-rs/ruffle/releases/tags/v0.7.1"
RUFFLE_DOWNLOAD = "https://github.com/ruffle-rs/ruffle/releases/download/v0.7.1/" + RUFFLE_ASSET
# Official release and asset link checked against https://ruffle.rs/downloads on 2026-10-20.
PAYLOAD_DIRECTORIES = ("assethash", "embeds", "patched", "templates", "villages", "warc_extractor", "xml", "GodBarn", "ruffle_runtime")
PREPARED_SCHEMA = 2
ACTIVE_CHILD: subprocess.Popen | None = None
STOPPING = False
STOP_SIGNAL = signal.SIGTERM
STOP_REPORTED = False


def log(message: str) -> None:
    print(f"[FarmVillage] {message}", flush=True)


def interrupted(signum: int, _frame: object) -> None:
    # A signal can interrupt Popen.wait while it holds its nonreentrant lock,
    # or interrupt a write while stdout is locked. Defer all work to normal flow.
    global STOPPING, STOP_SIGNAL
    if not STOPPING:
        STOP_SIGNAL = signum
        STOPPING = True


def check_cancelled() -> None:
    global STOP_REPORTED
    if STOPPING:
        if not STOP_REPORTED:
            STOP_REPORTED = True
            log("Stopping the owned runtime and its child processes…")
        raise SystemExit(128 + STOP_SIGNAL)


def watch_parent(parent_pid: int, finished: threading.Event, *, worker: bool = False) -> None:
    """A vanished app requests cleanup; its PID is never signalled or reused."""
    while not finished.wait(0.5):
        if os.getppid() != parent_pid:
            if worker:
                # This helper owns no children. Exit only ourselves if its
                # supervisor was killed before it could stop the process group.
                os._exit(128 + signal.SIGTERM)
            interrupted(signal.SIGTERM, None)
            return


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            check_cancelled()
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, contents: dict, *, data_root: Path | None = None) -> None:
    path = owned_path(data_root if data_root is not None else path.parent, path)
    descriptor, name = tempfile.mkstemp(prefix="." + path.name + "-", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(contents, indent=2) + "\n")
        os.replace(temporary, owned_path(data_root if data_root is not None else path.parent, path))
    finally:
        temporary.unlink(missing_ok=True)


def terminate_child() -> None:
    """Only signal the dedicated group created for our own child, then reap it."""
    child = ACTIVE_CHILD
    if child is None:
        return
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    # A child can exit before one of its descendants. Always clean the whole group.
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    child.wait()


def run_owned(command: list[str], *, cwd: Path | None = None, env: dict | None = None) -> None:
    global ACTIVE_CHILD
    check_cancelled()
    # The handler only sets a flag, so Popen always finishes handing off the
    # child's PID before cancellation can enter the cleanup below.
    child = subprocess.Popen(command, cwd=cwd, env=env, start_new_session=True)
    ACTIVE_CHILD = child
    try:
        while True:
            check_cancelled()
            try:
                result = child.wait(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                continue
        check_cancelled()
        if result:
            raise RuntimeError(f"Runtime command exited with status {result}.")
    finally:
        terminate_child()
        ACTIVE_CHILD = None


def payload_files(source: Path) -> list[Path]:
    files = list(source.glob("*.py"))
    files.extend(source / name for name in ("requirements.txt", "LICENSE", "PREPARED_RUNTIME.json",
                                           "PUBLIC_RUNTIME_BUILD.json", "PUBLIC_INSTALL.json")
                 if (source / name).is_file())
    for directory in PAYLOAD_DIRECTORIES:
        files.extend(path for path in (source / directory).rglob("*") if path.is_file() and "__pycache__" not in path.parts)
    return sorted(files)


def payload_version(source: Path) -> str:
    marker = source / ".payload-version"
    if marker.is_file():
        return marker.read_text(encoding="utf-8").strip()
    digest = hashlib.sha256()
    for path in payload_files(source):
        check_cancelled()
        digest.update(path.relative_to(source).as_posix().encode("utf-8"))
        digest.update(bytes.fromhex(sha256(path)))
    return digest.hexdigest()


def stage_runtime(source: Path, data: Path) -> tuple[Path, str]:
    check_cancelled()
    data = data.resolve()
    if not (source / "server.py").is_file() or not (source / "requirements.txt").is_file():
        raise RuntimeError(f"The bundled upstream payload is missing at {source}.")
    version = payload_version(source)
    runtime = owned_path(data, data / "runtime")
    previous = owned_path(data, data / ".runtime-previous")
    if previous.exists() and not runtime.exists():
        os.replace(owned_path(data, previous), owned_path(data, runtime))
    # The caller holds the data lock. A force quit can bypass Python's finally
    # cleanup, leaving an unpublished stage or the prior published runtime.
    for abandoned in data.glob(".runtime-stage-*"):
        if abandoned.is_symlink() or not abandoned.is_dir():
            continue
        try:
            shutil.rmtree(owned_path(data, abandoned))
        except OSError as error:
            log(f"Could not remove an interrupted runtime stage; the next launch will retry cleanup: {error}")
    marker = owned_path(data, runtime / ".payload-version")
    if marker.is_file() and marker.read_text(encoding="utf-8").strip() == version and (runtime / "server.py").is_file():
        if previous.exists():
            try:
                shutil.rmtree(owned_path(data, previous))
            except OSError as error:
                log(f"Could not remove the previous runtime; the next launch will retry cleanup: {error}")
        return runtime, version
    log("Copying the bundled game into its writable runtime folder…")
    temporary = Path(tempfile.mkdtemp(prefix=".runtime-stage-", dir=data))
    try:
        for source_file in payload_files(source):
            check_cancelled()
            destination = temporary / source_file.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, destination)
            destination.chmod(destination.stat().st_mode | stat.S_IWUSR)
        (temporary / ".payload-version").write_text(version + "\n", encoding="utf-8")
        if previous.exists():
            shutil.rmtree(owned_path(data, previous))
        try:
            if runtime.exists():
                os.replace(owned_path(data, runtime), owned_path(data, previous))
            os.replace(owned_path(data, temporary), owned_path(data, runtime))
        except BaseException:
            if previous.exists() and not runtime.exists():
                os.replace(owned_path(data, previous), owned_path(data, runtime))
            raise
        if previous.exists():
            shutil.rmtree(owned_path(data, previous))
    finally:
        if temporary.exists():
            shutil.rmtree(owned_path(data, temporary))
    return runtime, version


def ruffle_valid(directory: Path) -> bool:
    try:
        if directory.is_symlink():
            return False
        manifest = json.loads(owned_path(directory, directory / ".farmvillage-ruffle.json").read_text(encoding="utf-8"))
        if manifest["version"] != RUFFLE_VERSION or not owned_path(directory, directory / "ruffle.js").is_file():
            return False
        files = manifest["files"]
        if not isinstance(files, dict) or not files or not all(isinstance(name, str) and isinstance(digest, str) for name, digest in files.items()):
            return False
        if not any(name.endswith(".wasm") for name in files):
            return False
        for name, digest in files.items():
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts or sha256(owned_path(directory, directory / name)) != digest:
                return False
        return True
    except (OSError, RuntimeError, ValueError, KeyError, TypeError):
        return False


def request_url(url: str):
    check_cancelled()
    return urllib.request.urlopen(urllib.request.Request(url, headers={
        "User-Agent": "FarmVillage-macOS-wrapper/1.0",
        "Accept": "application/vnd.github+json" if "api.github.com" in url else "application/octet-stream",
    }), timeout=60)


def install_ruffle(data: Path) -> Path:
    check_cancelled()
    data = data.resolve()
    destination = owned_path(data, data / "ruffle" / RUFFLE_VERSION)
    if ruffle_valid(destination):
        log(f"Using the verified local Ruffle {RUFFLE_VERSION} files.")
        return destination
    log(f"Downloading official self-hosted Ruffle {RUFFLE_VERSION} (game archives are deferred until Start)…")
    with request_url(RUFFLE_RELEASE) as response:
        release = json.load(response)
    check_cancelled()
    if release.get("tag_name") != "v" + RUFFLE_VERSION:
        raise RuntimeError("The official Ruffle release metadata returned an unexpected version.")
    asset = next((item for item in release.get("assets", []) if item.get("name") == RUFFLE_ASSET), None)
    if not asset or asset.get("browser_download_url") != RUFFLE_DOWNLOAD:
        raise RuntimeError("The pinned self-hosted Ruffle archive was not found in its official release.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix=".ruffle-download-", dir=destination.parent))
    try:
        archive = workspace / RUFFLE_ASSET
        with request_url(RUFFLE_DOWNLOAD) as response, owned_path(data, archive).open("wb") as output:
            total = 0
            while chunk := response.read(1024 * 1024):
                check_cancelled()
                total += len(chunk)
                if total > 128 * 1024 * 1024:
                    raise RuntimeError("The Ruffle download exceeded the expected archive size.")
                output.write(chunk)
        archive_hash = sha256(archive)
        official_digest = asset.get("digest")
        if official_digest and official_digest != "sha256:" + archive_hash:
            raise RuntimeError("The downloaded Ruffle archive failed the official SHA-256 integrity check.")
        if not official_digest:
            log("GitHub did not publish an archive digest; using its pinned HTTPS release and recording file checksums.")
        unpacked = workspace / "unpacked"
        with zipfile.ZipFile(archive) as package:
            total_unpacked = 0
            for info in package.infolist():
                check_cancelled()
                relative = PurePosixPath(info.filename)
                if relative.is_absolute() or ".." in relative.parts or stat.S_ISLNK(info.external_attr >> 16):
                    raise RuntimeError("The Ruffle archive contained an unsafe path.")
                total_unpacked += info.file_size
                if total_unpacked > 256 * 1024 * 1024:
                    raise RuntimeError("The Ruffle archive expanded beyond the expected size.")
            package.extractall(owned_path(data, unpacked))
        entries = list(unpacked.rglob("ruffle.js"))
        if len(entries) != 1 or not list(entries[0].parent.glob("*.wasm")):
            raise RuntimeError("The Ruffle archive did not contain the expected JavaScript and WebAssembly files.")
        root = entries[0].parent
        files = {path.relative_to(root).as_posix(): sha256(path) for path in root.rglob("*") if path.is_file()}
        atomic_json(root / ".farmvillage-ruffle.json", {
            "version": RUFFLE_VERSION, "source": RUFFLE_DOWNLOAD,
            "archive_sha256": archive_hash, "files": files,
        }, data_root=data)
        if destination.exists():
            shutil.rmtree(owned_path(data, destination))
        os.replace(owned_path(data, root), owned_path(data, destination))
        log("Ruffle JavaScript and WebAssembly are now stored locally.")
    finally:
        shutil.rmtree(owned_path(data, workspace), ignore_errors=True)
    return destination


def private_python_environment() -> dict[str, str]:
    # Forward runtime necessities without account/proxy configuration.
    environment = {name: os.environ[name] for name in ('PATH', 'LANG', 'LC_ALL', 'LC_CTYPE', 'HOME', 'FARMVILLAGE_ASSETS_DIR') if name in os.environ}
    environment['NETRC'] = os.devnull
    environment['PIP_CONFIG_FILE'] = os.devnull
    return environment


def clean_ruffle_workspaces(data: Path) -> None:
    # The caller holds the data lock and has reaped its helper. Never follow a
    # link or remove installed Ruffle files while clearing abandoned downloads.
    data = data.resolve()
    parent = owned_path(data, data / "ruffle")
    for directory in parent.glob(".ruffle-download-*"):
        if directory.is_symlink() or not directory.is_dir():
            continue
        try:
            shutil.rmtree(owned_path(data, directory))
        except OSError as error:
            log(f"Could not remove a temporary Ruffle download; preparation will retry cleanup: {error}")


def ruffle_worker() -> None:
    parser = argparse.ArgumentParser(description="Internal owned Ruffle installer")
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--parent-pid", required=True, type=int)
    arguments = parser.parse_args(sys.argv[2:])
    if arguments.parent_pid <= 0 or os.getppid() != arguments.parent_pid:
        raise RuntimeError("The Ruffle installer's supervisor is no longer running.")
    finished = threading.Event()
    threading.Thread(target=watch_parent, args=(arguments.parent_pid, finished),
                     kwargs={"worker": True}, daemon=True).start()
    try:
        # Keep default SIGTERM handling: the supervisor must be able to stop a
        # blocked/trickling HTTPS read, then clean this helper's temporary files.
        install_ruffle(arguments.data_dir.expanduser().resolve())
    finally:
        finished.set()


def compatibility_runtime(runtime: Path, data: Path):
    """Load the staged shared verifier and install only reviewed local bytes."""
    helper = owned_path(runtime, runtime / "runtime_compatibility.py")
    spec = importlib.util.spec_from_file_location("farmvillage_runtime_compatibility", helper)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    release = compatibility_release(module, runtime)
    installed = module.install_runtime(runtime, data, release, check_cancelled=check_cancelled)
    return module, installed


def compatibility_release(module, runtime: Path):
    """Read the explicit source-build pin copied by the prepared-pack bundler."""
    prepared_path = owned_path(runtime, runtime / "PREPARED_RUNTIME.json")
    if not prepared_path.exists():
        return module.ACTIVE_RELEASE
    if prepared_path.stat().st_size > 1024 * 1024:
        raise RuntimeError("The prepared runtime marker exceeds its expected size.")
    try:
        prepared = json.loads(prepared_path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as error:
        raise RuntimeError("The prepared runtime marker is damaged; rebuild the app from the prepared resource pack.") from error
    if not isinstance(prepared, dict) or prepared.get("schema") != 1 or not prepared.get("runtime_manifest_sha256"):
        raise RuntimeError("The prepared runtime marker is missing its player integrity pin.")
    return module.select_runtime_release(runtime, prepared_pin_sha256=prepared["runtime_manifest_sha256"])


def prepare(runtime: Path, data: Path, version: str) -> None:
    check_cancelled()
    data = data.resolve()
    marker = owned_path(data, data / "prepared.json")
    marker.unlink(missing_ok=True)
    venv = owned_path(data, data / "venv")
    pip_cache = owned_path(data, data / "cache" / "pip")
    base_python = getattr(sys, "_base_executable", sys.executable)
    environment = private_python_environment()
    package_home = owned_path(data, data / 'cache/package-home')
    package_home.mkdir(parents=True, exist_ok=True)
    environment['HOME'] = str(package_home)
    environment['XDG_CACHE_HOME'] = str(package_home / '.cache')
    log("Creating the isolated Python environment…")
    run_owned([base_python, "-I", "-B", "-m", "venv", "--clear", str(venv)], env=environment)
    log("Installing the upstream project's pinned Python requirements…")
    run_owned([str(venv / "bin" / "python"), "-I", "-B", "-m", "pip", "--isolated", "install",
               "--disable-pip-version-check", "--no-input", "--require-virtualenv", "--prefer-binary",
               "--index-url", "https://pypi.org/simple", "--cache-dir", str(pip_cache),
               "-r", str(runtime / "requirements.txt")], env=environment)
    log("Installing the reviewed local Ruffle runtime…")
    compatibility, _ruffle = compatibility_runtime(runtime, data)
    release = compatibility_release(compatibility, runtime)
    check_cancelled()
    atomic_json(marker, {
        "schema": PREPARED_SCHEMA, "payload_version": version,
        "requirements_sha256": sha256(runtime / "requirements.txt"),
        "ruffle_version": RUFFLE_VERSION, "python_version": sys.version.split()[0],
        "ruffle_runtime_id": release.runtime_id,
        "ruffle_manifest_sha256": release.manifest_sha256,
    }, data_root=data)
    log("Preparation complete. Start will reuse the prepared public artwork." if (runtime / "PUBLIC_INSTALL.json").is_file() else "Preparation complete. Start will download and extract the game archives if assets are missing.")


def start(runtime: Path, data: Path, arguments: argparse.Namespace) -> None:
    data = data.resolve()
    try:
        prepared = json.loads(owned_path(data, data / "prepared.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeError("Prepare the runtime in the app before starting the game.") from error
    if not isinstance(prepared, dict):
        raise RuntimeError("The runtime setup marker is damaged. Choose Prepare Runtime to repair it.")
    python = owned_path(data, data / "venv" / "bin" / "python", allow_leaf_symlink=True)
    if prepared.get("schema") != PREPARED_SCHEMA or not python.is_file() or prepared.get("requirements_sha256") != sha256(runtime / "requirements.txt"):
        raise RuntimeError("The Python environment needs preparation after this update. Choose Prepare Runtime.")
    # Existing schema-2 Python environments receive only this verified offline
    # runtime migration. No venv, dependency, asset, save or God Barn reset.
    compatibility, ruffle = compatibility_runtime(runtime, data)
    release = compatibility_release(compatibility, runtime)
    runtime_marker = {"ruffle_version": RUFFLE_VERSION,
                      "ruffle_runtime_id": release.runtime_id,
                      "ruffle_manifest_sha256": release.manifest_sha256}
    if any(prepared.get(key) != value for key, value in runtime_marker.items()):
        prepared.update(runtime_marker)
        prepared["payload_version"] = payload_version(runtime)
        atomic_json(data / "prepared.json", prepared, data_root=data)
    environment = private_python_environment()
    environment.update({
        "FARMVILLAGE_DATA_DIR": str(data), "FARMVILLAGE_NATIVE": "1",
        "FARMVILLAGE_RUFFLE_DIR": str(ruffle), "FARMVILLAGE_INSTANCE_TOKEN": arguments.token,
        "PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1",
    })
    if (runtime / "PREPARED_RUNTIME.json").is_file():
        environment["FARMVILLAGE_PREPARED_RUNTIME_PIN_SHA256"] = release.manifest_sha256
    log(f"Starting the owned local server at http://127.0.0.1:{arguments.port}/…")
    run_owned([str(python), "-E", "-s", "-B", "-u", str(Path(__file__).with_name("server_runner.py")),
               "--runtime", str(runtime), "--port", str(arguments.port)], cwd=runtime, env=environment)


def main() -> None:
    parser = argparse.ArgumentParser(description="FarmVillage native runtime")
    parser.add_argument("action", choices=("prepare", "start"))
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--python")  # Interpreter selection is handled by runtime.sh.
    parser.add_argument("--port", type=int, default=5501)
    parser.add_argument("--token", required=True)
    parser.add_argument("--parent-pid", type=int, help="PID of the native app that owns this supervisor")
    arguments = parser.parse_args()
    if not 1024 <= arguments.port <= 65535 or not arguments.token:
        parser.error("A nonempty ownership token and an unprivileged valid TCP port are required.")
    if arguments.parent_pid is not None and arguments.parent_pid <= 0:
        parser.error("The parent PID must be positive.")
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    if arguments.parent_pid is not None and os.getppid() != arguments.parent_pid:
        raise RuntimeError("The launching app is no longer running. Open the app again to continue.")
    source = arguments.runtime.resolve()
    data = arguments.data_dir.expanduser().resolve()
    if source == data or source in data.parents or data in source.parents:
        raise RuntimeError("Game data and the bundled payload must use separate folders.")
    data.mkdir(parents=True, exist_ok=True)
    for name in ("saves", "assets", "cache", "tmp"):
        owned_path(data, data / name).mkdir(exist_ok=True)
    with owned_path(data, data / ".runtime.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another FarmVillage runtime already owns this data folder. Stop it before continuing.") from error
        finished = threading.Event()
        if arguments.parent_pid is not None:
            threading.Thread(target=watch_parent, args=(arguments.parent_pid, finished), daemon=True).start()
        try:
            runtime, version = stage_runtime(source, data)
            if arguments.action == "prepare":
                prepare(runtime, data, version)
            else:
                start(runtime, data, arguments)
        finally:
            finished.set()


if __name__ == "__main__":
    try:
        if sys.argv[1:2] == ["_install-ruffle"]:
            ruffle_worker()
        else:
            main()
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as error:
        log(f"ERROR: {error}")
        raise SystemExit(1)
