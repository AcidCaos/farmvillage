"""Exercise service installation without touching the machine's service manager."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import unittest


MARKER = "# Managed by FarmVillage LAN hosting (install-service.sh)"
INSTALLER = Path(__file__).with_name("install-service.sh")


class ServiceInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="farmvillage-service-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.hosting = self.root / 'hosting %$money "quoted"'
        self.hosting.mkdir()
        shutil.copyfile(INSTALLER, self.hosting / "install-service.sh")
        self.commands = self.root / "commands"
        self.commands.mkdir()
        self.log = self.root / "commands.jsonl"
        self.environment = dict(os.environ, PATH=str(self.commands) + os.pathsep + os.environ["PATH"],
                                XDG_CONFIG_HOME=str(self.root / "config"), FV_TEST_LOG=str(self.log),
                                COPYFILE_DISABLE="1")  # macOS BSD tar otherwise synthesizes AppleDouble entries.
        self.unit = self.root / "config/systemd/user/farmvillage.service"
        self.write_executable(self.commands / "uname", "#!/bin/sh\nprintf 'Linux\\n'\n")
        self.write_executable(self.commands / "id", "#!/bin/sh\nif [ \"$1\" = -u ]; then echo 1001; else echo fvtest; fi\n")
        # The workspace virtualenv path contains spaces; kernels do not accept
        # shell quoting in a shebang. Resolve its symlink to the real executable.
        fixture_python = Path(sys.executable).resolve()
        command_stub = f"""#!{fixture_python}
import json, os, sys
name = os.path.basename(sys.argv[0])
with open(os.environ['FV_TEST_LOG'], 'a') as log:
    log.write(json.dumps([name] + sys.argv[1:]) + '\\n')
if name == 'systemctl' and '--property=FragmentPath' in sys.argv:
    print(os.environ.get('FV_LOADED_UNIT', ''))
elif name == 'systemctl' and 'start' in sys.argv and os.environ.get('FV_START_FAIL'):
    sys.exit(1)
elif name == 'systemctl' and 'is-active' in sys.argv and os.environ.get('FV_INACTIVE'):
    sys.exit(3)
elif name == 'loginctl' and 'show-user' in sys.argv:
    print(os.environ.get('FV_LINGER', 'no'))
elif name == 'sudo':
    if os.environ.get('FV_SUDO_FAIL'):
        sys.exit(1)
    os.execvp(sys.argv[1], sys.argv[1:])
"""
        for name in ("systemctl", "loginctl", "sudo", "journalctl"):
            self.write_executable(self.commands / name, command_stub)
        self.write_executable(self.hosting / "start-server.sh", """#!/usr/bin/env bash
set -eu
[[ $# == 3 && "$3" == --init-only ]]
printf 'INIT %s %s\\n' "$1" "$2"
if [[ -n "${FV_INIT_FAIL:-}" ]]; then exit 1; fi
""")
        game_python = self.root / "release/farmvillage-portable-preparation-1acf91b47487/.venv/bin/python"
        game_python.parent.mkdir(parents=True)
        self.write_executable(game_python, f"""#!{fixture_python}
import os, sys
code = sys.stdin.read()
sys.argv = sys.argv[1:]
if 'import urllib.request' in code:
    # Readiness is supplied by the fake service manager; the port preflight runs
    # the installer's real socket code against actual listening sockets below.
    sys.exit(0 if not os.environ.get('FV_READY_FAIL') else 1)
exec(compile(code, '<service-installer>', 'exec'))
""")
        for name, contents in (("saves/farm.json", '{"coins":123}'),
                               ("god-barn/history.json", '["original"]'),
                               ("assets/do-not-copy.swf", "large-asset"),
                               (".lan-server/password.hash", "private-test-hash")):
            path = self.root / "data" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents)

    @staticmethod
    def write_executable(path, contents):
        path.write_text(contents)
        path.chmod(0o755)

    def run_installer(self, *arguments, **environment):
        return subprocess.run(["/bin/bash", str(self.hosting / "install-service.sh"), *arguments],
                              env=dict(self.environment, **environment), capture_output=True, text=True, timeout=10)

    def commands_called(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def unused_port(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            return str(listener.getsockname()[1])

    def test_install_initializes_credentials_enables_boot_and_builds_graceful_unit(self):
        port = self.unused_port()
        result = self.run_installer("127.0.0.1", port)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"INIT 127.0.0.1 {port}", result.stdout)
        self.assertIn("You can close this terminal", result.stdout)
        unit = self.unit.read_text()
        self.assertTrue(unit.startswith(MARKER + "\n"))
        self.assertIn('hosting %%$$money \\"quoted\\"/start-server.sh', unit)
        self.assertIn(f'"127.0.0.1" "{port}"', unit)
        for setting in ("WantedBy=default.target", "Restart=on-failure", "RestartSec=5", "KillSignal=SIGINT", "TimeoutStopSec=60", "SendSIGKILL=no"):
            self.assertIn(setting, unit)
        self.assertIn(["sudo", "loginctl", "enable-linger", "fvtest"], self.commands_called())
        self.assertIn(["systemctl", "--user", "enable", "farmvillage.service"], self.commands_called())
        self.assertIn(["systemctl", "--user", "start", "farmvillage.service"], self.commands_called())
        backups = list((self.root / "backups").glob("pre-service-*/farm-data.tar.gz"))
        self.assertEqual(len(backups), 1)
        backup = backups[0]
        self.assertEqual(backup.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        with tarfile.open(backup, "r:gz") as archive:
            names = set(archive.getnames())
            self.assertEqual(names, {"saves", "saves/farm.json", "god-barn", "god-barn/history.json"})
            self.assertEqual(archive.extractfile("saves/farm.json").read(), b'{"coins":123}')
            self.assertEqual(archive.extractfile("god-barn/history.json").read(), b'["original"]')
        self.assertEqual((self.root / "data/saves/farm.json").read_text(), '{"coins":123}')
        self.assertEqual((self.root / "data/assets/do-not-copy.swf").read_text(), "large-asset")

    def test_existing_linger_does_not_request_sudo(self):
        result = self.run_installer("127.0.0.1", self.unused_port(), FV_LINGER="yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(command[0] == "sudo" for command in self.commands_called()))

    def test_existing_listener_fails_without_installing_unit_or_stopping_process(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            result = self.run_installer("127.0.0.1", str(listener.getsockname()[1]))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Control+C", result.stderr)
        self.assertFalse(self.unit.exists())
        self.assertFalse((self.root / "backups").exists())
        self.assertFalse(any("stop" in command or command[0] == "sudo" for command in self.commands_called()))

    def test_existing_unrelated_unit_and_symlink_are_not_changed(self):
        self.unit.parent.mkdir(parents=True)
        original = "[Service]\nExecStart=/bin/true\n"
        self.unit.write_text(original)
        result = self.run_installer("--remove")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unrelated unit", result.stderr)
        self.assertEqual(self.unit.read_text(), original)
        self.assertEqual(self.commands_called(), [])
        self.unit.unlink()
        target = self.root / "foreign.service"
        target.write_text(MARKER)
        self.unit.symlink_to(target)
        result = self.run_installer("--remove")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_text(), MARKER)

    def test_other_loaded_unit_is_not_shadowed(self):
        result = self.run_installer("127.0.0.1", self.unused_port(), FV_LOADED_UNIT="/etc/systemd/user/farmvillage.service")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("left alone", result.stderr)
        self.assertFalse(self.unit.exists())
        self.assertFalse(any("stop" in command for command in self.commands_called()))

    def test_failed_initialization_or_linger_does_not_install_unit(self):
        for failure in ("FV_INIT_FAIL", "FV_SUDO_FAIL"):
            with self.subTest(failure=failure):
                result = self.run_installer("127.0.0.1", self.unused_port(), **{failure: "1"})
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.unit.exists())
                self.assertFalse(list(self.unit.parent.glob(".farmvillage.*")))

    def test_failed_reinstall_restores_previously_active_managed_service(self):
        self.unit.parent.mkdir(parents=True)
        original = MARKER + "\n[Service]\nExecStart=/bin/true\n"
        self.unit.write_text(original)
        result = self.run_installer("127.0.0.1", self.unused_port(), FV_INIT_FAIL="1", FV_LOADED_UNIT=str(self.unit))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.unit.read_text(), original)
        commands = self.commands_called()
        self.assertLess(commands.index(["systemctl", "--user", "stop", "farmvillage.service"]),
                        commands.index(["systemctl", "--user", "start", "farmvillage.service"]))
        self.assertIn("restarting the previously managed service", result.stderr)

    def test_repeated_install_preserves_each_backup(self):
        arguments = ("127.0.0.1", self.unused_port())
        first = self.run_installer(*arguments, FV_LINGER="yes")
        self.assertEqual(first.returncode, 0, first.stderr)
        (self.root / "data/saves/farm.json").write_text('{"coins":456}')
        second = self.run_installer(*arguments, FV_LINGER="yes", FV_LOADED_UNIT=str(self.unit))
        self.assertEqual(second.returncode, 0, second.stderr)
        archives = list((self.root / "backups").glob("pre-service-*/farm-data.tar.gz"))
        self.assertEqual(len(archives), 2)
        contents = set()
        for archive_path in archives:
            with tarfile.open(archive_path) as archive:
                contents.add(archive.extractfile("saves/farm.json").read())
        self.assertEqual(contents, {b'{"coins":123}', b'{"coins":456}'})

    def test_failure_to_start_reports_status_and_log_command(self):
        result = self.run_installer("127.0.0.1", self.unused_port(), FV_START_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("journalctl --user -u farmvillage.service", result.stderr)
        self.assertTrue(any("status" in command for command in self.commands_called()))

    def test_readiness_failure_reports_journal(self):
        result = self.run_installer("127.0.0.1", self.unused_port(), FV_READY_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any(command[0] == "journalctl" for command in self.commands_called()))

    def test_reinstall_stops_only_its_managed_unit_and_remove_preserves_data(self):
        self.unit.parent.mkdir(parents=True)
        self.unit.write_text(MARKER + "\n[Service]\nExecStart=/bin/true\n")
        farm = self.root / "data/saves/farm.json"
        farm.parent.mkdir(parents=True, exist_ok=True)
        farm.write_text('{"coins":123}')
        result = self.run_installer("127.0.0.1", self.unused_port(), FV_LOADED_UNIT=str(self.unit), FV_LINGER="yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(["systemctl", "--user", "stop", "farmvillage.service"], self.commands_called())
        result = self.run_installer("--remove", FV_LOADED_UNIT=str(self.unit))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(["systemctl", "--user", "disable", "--now", "farmvillage.service"], self.commands_called())
        self.assertFalse(self.unit.exists())
        self.assertEqual(farm.read_text(), '{"coins":123}')


if __name__ == "__main__":
    unittest.main()
