"""Read-only diagnostics preserve farms and expose only selected host arguments."""

import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


spec = importlib.util.spec_from_file_location("diagnose_saves", Path(__file__).with_name("diagnose-saves.py"))
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


def farm(uid="one", *, xp=16, coins=50604):
    return {
        "userInfo": {"attr": {"name": "Farmer"}, "player": {
            "userId": uid, "xp": xp, "gold": coins, "cash": 6,
        }},
        "world": {"objectsArray": [{"id": 1}]},
        "private_metadata": "DO-NOT-PRINT",
    }


class SaveInventoryTests(unittest.TestCase):
    def test_farm_inventory_preserves_all_files_and_continues_after_invalid_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "one.save.json").write_text(json.dumps(farm()))
            (root / "two.save.json").write_text(json.dumps(farm("two", xp=50)))
            (root / "broken.json").write_text("{")
            (root / "hidden.backup.json").write_text(json.dumps(farm("backup")))
            (root / ".save-transactions" / "interrupted").mkdir(parents=True)
            original = {path.relative_to(root): (path.stat().st_mtime_ns, path.read_bytes())
                        for path in root.rglob("*") if path.is_file()}
            output = io.StringIO()
            inventory = diagnostic.Inventory(output)
            inventory.saves(root)
            self.assertEqual(inventory.errors, 1)
            self.assertIn("Farm files: 3", output.getvalue())
            self.assertIn("UID='one' name='Farmer' XP=16 coins=50604 cash=6 objects=1", output.getvalue())
            self.assertIn("UID='two'", output.getvalue())
            self.assertIn("Pending transaction entries: 1", output.getvalue())
            self.assertNotIn("UID='backup'", output.getvalue())
            self.assertNotIn("DO-NOT-PRINT", output.getvalue())
            after = {path.relative_to(root): (path.stat().st_mtime_ns, path.read_bytes())
                     for path in root.rglob("*") if path.is_file()}
            self.assertEqual(original, after)
            self.assertTrue((root / ".save-transactions" / "interrupted").is_dir())

    def test_snapshots_read_nested_saves_and_skip_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "ordinary.json").write_text(json.dumps({
                "save": farm("recovered", xp=75), "created": "2026-10-21T17:00:00Z",
                "label": "Before: Coins changed.\nDo not overwrite.",
            }))
            (root / "link.json").symlink_to(root / "ordinary.json")
            output = io.StringIO()
            inventory = diagnostic.Inventory(output)
            inventory.snapshots(root)
            text = output.getvalue()
            self.assertIn("Snapshot files: 1", text)
            self.assertIn("UID='recovered'", text)
            self.assertIn("XP=75", text)
            self.assertIn(r"changed.\nDo not overwrite.", text)
            self.assertIn("not an ordinary snapshot file", text)
            self.assertEqual(inventory.errors, 1)

    def test_process_inventory_excludes_nonrunner_and_unknown_arguments(self):
        output = io.StringIO()
        inventory = diagnostic.Inventory(output)
        result = SimpleNamespace(returncode=0, stdout=(
            "123 python /home/user/hosting/server_runner.py --data-dir /home/user/data "
            "--runtime=/home/user/release/Runtime --port 5501 --private secret-value\n"
            "456 sh -c echo-server_runner.py --private another-secret\n"
        ))
        with mock.patch.object(diagnostic.subprocess, "run", return_value=result) as run:
            inventory.processes()
        run.assert_called_once()
        self.assertIn("PID=123", output.getvalue())
        self.assertIn("--runtime='/home/user/release/Runtime'", output.getvalue())
        self.assertIn("--data-dir='/home/user/data'", output.getvalue())
        self.assertNotIn("PID=456", output.getvalue())
        self.assertNotIn("secret", output.getvalue())


if __name__ == "__main__":
    unittest.main()
