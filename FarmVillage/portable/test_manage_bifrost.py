"""Check reset-critical Mac wrapper commands using fake SSH/SCP, with no network."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class BifrostWrapperTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="farmvillage-wrapper-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.delivery = self.root / "Bifrost LAN Update"
        self.delivery.mkdir()
        self.wrapper = self.delivery / "manage-bifrost.sh"
        shutil.copyfile(Path(__file__).with_name("manage-bifrost.sh"), self.wrapper)
        for filename in ("farmvillage-lan-host.tar.gz", "farmvillage-lan-host.tar.gz.sha256",
                         "farmvillage-fresh-world.tar.gz", "farmvillage-fresh-world.tar.gz.sha256"):
            (self.delivery / filename).write_bytes(b"disposable wrapper fixture")
        commands = self.root / "commands"
        commands.mkdir()
        self.log = self.root / "invocations.jsonl"
        interpreter = Path(sys.executable).resolve()
        stub = f"""#!{interpreter}
import json, os, sys
name = os.path.basename(sys.argv[0])
with open(os.environ['FV_WRAPPER_LOG'], 'a') as output:
    output.write(json.dumps([name] + sys.argv[1:]) + '\\n')
if os.environ.get('FV_FAIL_COMMAND') == name:
    sys.exit(42)
"""
        for name in ("ssh", "scp"):
            target = commands / name
            target.write_text(stub)
            target.chmod(0o755)
        self.environment = dict(os.environ, PATH=str(commands) + os.pathsep + os.environ["PATH"], FV_WRAPPER_LOG=str(self.log))

    def invoke(self, *arguments, **environment):
        return subprocess.run(["/bin/bash", str(self.wrapper), *arguments], capture_output=True,
                              text=True, timeout=5, env=dict(self.environment, **environment))

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def remote_command(self):
        calls = self.calls()
        self.assertEqual(calls[-1][:3], ["ssh", "-t", "farmvillage@192.168.50.80"])
        self.assertEqual(len(calls[-1]), 4, "The remote operation must remain one quoted SSH argument.")
        return calls[-1][-1]

    def test_no_option_and_explicit_check_do_not_start_stop_or_reset_the_world(self):
        for arguments in ((), ("--check-saves",)):
            with self.subTest(arguments=arguments):
                self.log.unlink(missing_ok=True)
                result = self.invoke(*arguments)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual([call[0] for call in self.calls()], ["scp", "ssh"])
                command = self.remote_command()
                self.assertIn("sha256sum -c farmvillage-lan-host.tar.gz.sha256", command)
                self.assertIn("diagnose-saves.py", command)
                for mutation in ("install-service.sh", "install-fresh-world.py", "systemctl", "kill "):
                    self.assertNotIn(mutation, command)

    def test_install_transfers_only_host_and_runs_service_installer(self):
        result = self.invoke("--install")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([call[0] for call in self.calls()], ["scp", "ssh"])
        transfer = self.calls()[0]
        self.assertEqual(transfer[1:3], [str(self.delivery / "farmvillage-lan-host.tar.gz"),
                                       str(self.delivery / "farmvillage-lan-host.tar.gz.sha256")])
        command = self.remote_command()
        self.assertIn("bash ../hosting/install-service.sh", command)
        self.assertNotIn("install-fresh-world.py", command)
        self.assertNotIn("farmvillage-fresh-world.tar.gz", command)

    def test_fresh_start_transfers_both_archives_checks_both_and_runs_reset_installer(self):
        result = self.invoke("--fresh-start")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([call[0] for call in self.calls()], ["scp", "scp", "ssh"])
        self.assertEqual(self.calls()[1][1:3], [str(self.delivery / "farmvillage-fresh-world.tar.gz"),
                                              str(self.delivery / "farmvillage-fresh-world.tar.gz.sha256")])
        for transfer in self.calls()[:2]:
            self.assertEqual(transfer[-1], "farmvillage@192.168.50.80:/home/farmvillage/farmville-test/release/")
        command = self.remote_command()
        self.assertTrue(command.startswith("cd /home/farmvillage/farmville-test/release && "))
        host_check = command.index("sha256sum -c farmvillage-lan-host.tar.gz.sha256")
        world_check = command.index("sha256sum -c farmvillage-fresh-world.tar.gz.sha256")
        reset = command.index("python3 -B ../hosting/install-fresh-world.py --archive farmvillage-fresh-world.tar.gz")
        self.assertLess(host_check, world_check)
        self.assertLess(world_check, reset)
        self.assertNotIn("bash ../hosting/install-service.sh", command)

    def test_invalid_option_or_missing_world_stops_before_any_transfer(self):
        result = self.invoke("--unknown")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])
        (self.delivery / "farmvillage-fresh-world.tar.gz.sha256").unlink()
        result = self.invoke("--fresh-start")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing fresh neighbourhood update", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_failed_transfer_never_runs_a_remote_reset(self):
        result = self.invoke("--fresh-start", FV_FAIL_COMMAND="scp")
        self.assertEqual(result.returncode, 42)
        self.assertEqual([call[0] for call in self.calls()], ["scp"])


if __name__ == "__main__":
    unittest.main()
