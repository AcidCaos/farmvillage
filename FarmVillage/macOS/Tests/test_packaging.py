"""Exercise resource staging with a small fixture and the pinned real game client."""

import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="FarmVillage packaging ")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source = self.base / "Source with spaces"
        self.scripts = self.source / "macOS" / "Scripts"
        self.scripts.mkdir(parents=True)
        shutil.copy2(ROOT / "macOS/Scripts/bundle-runtime.sh", self.scripts)
        shutil.copy2(ROOT / "macOS/Scripts/patch-game-client.py", self.scripts)
        for name in ('client_compatibility.py', 'cove_client.py', 'meadows_client.py', 'client_graphics.py', 'meadows_rules.py', 'meadows_storage.py', 'england_animals.py', 'england_shipping.py', 'cove_rules.py', 'cove_port.py', 'cove_shipping.py', 'cellar_progression.py', 'rainforest_features.py', 'rainforest_rules.py', 'placement_receipts.py', 'inventory_sales.py', 'commands.py', 'storage.py'):
            shutil.copy2(ROOT / name, self.source)
        (self.scripts / "runtime.sh").write_text("# launcher fixture\n")
        helpers = self.source / "macOS/Runtime"
        helpers.mkdir()
        (helpers / "bootstrap.py").write_text("# helper fixture\n")
        notices = self.source / "macOS/Documentation"
        notices.mkdir()
        (notices / "THIRD_PARTY.md").write_text("Fixture notices\n")
        heritage = self.source / "macOS/Resources/Heritage"
        heritage.mkdir(parents=True)
        (heritage / "manifest.json").write_text('{"schema": 1, "assets": []}')
        (heritage / "NOTICES.md").write_text("Original artwork/font notices\n")
        (heritage / "heading.ttf").write_bytes(b"private Merkin fixture")
        (heritage / "farmville-logo.png").write_bytes(b"original logo fixture")
        for name in ("server.py", "persistence.py", "world_scores.py", "requirements.txt", "LICENSE", "README.md", "FLASH.md"):
            (self.source / name).write_text(f"Fixture {name}\n")
        for name in ("assethash", "embeds", "patched", "templates", "villages", "warc_extractor", "xml"):
            directory = self.source / name
            directory.mkdir()
            (directory / "fixture.txt").write_text(f"Resource {name}\n")
        game = self.source / "embeds/Flash/v855097-855094/FarmGame.swf"
        game.parent.mkdir(parents=True)
        shutil.copy2(ROOT / "embeds/Flash/v855097-855094/FarmGame.swf", game)
        # The native payload now includes the independent sibling companion.
        companion = self.base / "GodBarn"
        (companion / "scripts").mkdir(parents=True)
        shutil.copy2(ROOT.parent / "GodBarn/scripts/bundle_companion.py", companion / "scripts")
        for name in ("__init__.py", "engine.py", "integration.py", "seasonal.py", "catalog_tools.py", "encyclopedia.py", "progression_tools.py", "helper_tools.py"):
            (companion / name).write_text("# companion fixture\n")
        (companion / "static/assets/ui").mkdir(parents=True)
        for name in ("index.html", "app.js", "style.css", "farmville.css", "touch.js"):
            (companion / "static" / name).write_text("fixture")
        (companion / "static/assets/ui/icon.png").write_bytes(b"fixture art")
        (companion / "data").mkdir()
        (companion / "data/catalog.json").write_text("[]")
        (companion / "data/rules.json").write_text("{}")
        (companion / "data/untabbed.json").write_text('{"schema":1,"items":{}}')
        (companion / "data/encyclopedia.json").write_text('{"schema":1,"items":{},"shelves":[],"sources":[]}')
        (companion / "data/progression.json").write_text('{"schemaVersion":1,"ribbons":[],"masteryItems":[]}')
        (companion / "data/historical-prizes.json").write_text('{"schema":1,"sources":[],"shelves":[]}')
        (companion / "data/provenance.json").write_text('{"sourceDirectory": "fixture", "assets": []}')
        (companion / "data/bootstrap-save.json").write_text("private practice save")
        (companion / "workspace").mkdir()
        (companion / "workspace/private.json").write_text("private working save")
        self.product = self.base / "Build Product"
        self.runtime_id = "0.7.1-farmvillage-packaging-fixture"
        self.runtime_files = {"ruffle.js": b"fixture reviewed loader", "core.wasm": b"\x00asm\x01\x00\x00\x00"}
        self.write_runtime_package()

    def write_runtime_package(self):
        directory = self.source / "ruffle_runtime" / self.runtime_id
        directory.mkdir(parents=True, exist_ok=True)
        for name, value in self.runtime_files.items():
            (directory / name).write_bytes(value)
        manifest = {"schema": 1, "runtime_id": self.runtime_id, "version": "0.7.1",
                    "upstream_commit": "89a7049965f3090e706265670df309a5128233ac",
                    "files": {name: hashlib.sha256(value).hexdigest() for name, value in self.runtime_files.items()}}
        raw = json.dumps(manifest, sort_keys=True).encode()
        (directory / ".farmvillage-ruffle.json").write_bytes(raw)
        helper = (ROOT / "runtime_compatibility.py").read_text()
        assignment = next(node for node in ast.parse(helper).body
                          if (isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
                              and node.target.id == "ACTIVE_RELEASE")
                          or (isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
                              and target.id == "ACTIVE_RELEASE" for target in node.targets)))
        lines = helper.splitlines(keepends=True)
        lines[assignment.lineno - 1:assignment.end_lineno] = [
            "ACTIVE_RELEASE = RuntimeRelease(" + repr(self.runtime_id) + ", '0.7.1', "
            + repr(manifest["upstream_commit"]) + ", " + repr(hashlib.sha256(raw).hexdigest()) + ")\n"]
        (self.source / "runtime_compatibility.py").write_text("".join(lines))
        return directory

    def stage(self, *, product=None, succeeds=True):
        environment = os.environ.copy()
        environment.update({
            "TARGET_BUILD_DIR": str(product or self.product),
            "UNLOCALIZED_RESOURCES_FOLDER_PATH": "FarmVillage.app/Contents/Resources",
        })
        result = subprocess.run(
            ["/bin/bash", str(self.scripts / "bundle-runtime.sh")],
            env=environment, text=True, capture_output=True, timeout=30,
        )
        if succeeds:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return (product or self.product) / "FarmVillage.app/Contents/Resources"

    def test_payload_contains_required_sources_helpers_and_notices(self):
        resources = self.stage()
        for name in ("Runtime/server.py", "Runtime/persistence.py", "Runtime/world_scores.py", "Runtime/client_compatibility.py", "Runtime/meadows_client.py", "Runtime/client_graphics.py", "Runtime/meadows_rules.py", "Runtime/meadows_storage.py", "Runtime/runtime_compatibility.py", "Runtime/requirements.txt",
                     "Runtime/LICENSE", "Scripts/runtime.sh", "WrapperRuntime/bootstrap.py",
                     "WrapperRuntime/patch-game-client.py", "THIRD_PARTY.md",
                     "Runtime/GodBarn/integration.py", "Runtime/GodBarn/engine.py", "Runtime/GodBarn/seasonal.py",
                     "Runtime/GodBarn/encyclopedia.py", "Runtime/GodBarn/progression_tools.py", "Runtime/GodBarn/catalog_tools.py", "Runtime/GodBarn/helper_tools.py",
                     "Runtime/GodBarn/data/encyclopedia.json.gz", "Runtime/GodBarn/data/progression.json",
                     "Runtime/GodBarn/data/historical-prizes.json", "Runtime/GodBarn/data/untabbed.json",
                     "Runtime/GodBarn/static/index.html", "Runtime/GodBarn/static/touch.js", "Runtime/GodBarn/data/catalog.json.gz",
                     "Runtime/GodBarn/data/asset-map.json", "Heritage/manifest.json",
                     "Heritage/NOTICES.md", "Heritage/heading.ttf", "Heritage/farmville-logo.png"):
            self.assertTrue((resources / name).is_file(), name)
        for name in ('client_compatibility.py', 'cove_client.py', 'meadows_client.py', 'client_graphics.py', 'meadows_rules.py', 'meadows_storage.py', 'england_animals.py', 'england_shipping.py', 'cove_rules.py', 'cove_port.py', 'cove_shipping.py', 'cellar_progression.py', 'rainforest_features.py', 'rainforest_rules.py', 'placement_receipts.py', 'inventory_sales.py', 'commands.py', 'server.py', 'storage.py'):
            self.assertEqual((resources / "Runtime" / name).read_bytes(), (self.source / name).read_bytes())
        self.assertEqual(len((resources / "Runtime/.payload-version").read_text().strip()), 64)
        runtime_relative = "ruffle_runtime/" + self.runtime_id
        for name in (*self.runtime_files, ".farmvillage-ruffle.json"):
            self.assertEqual((resources / "Runtime" / runtime_relative / name).read_bytes(),
                             (self.source / runtime_relative / name).read_bytes())
        self.assertFalse((resources / "Runtime/macOS").exists())
        self.assertFalse(list(resources.glob(".farmvillage-stage.*")))
        game_path = "embeds/Flash/v855097-855094/FarmGame.swf"
        self.assertEqual((self.source / game_path).read_bytes(), (ROOT / game_path).read_bytes())
        self.assertNotEqual((resources / "Runtime" / game_path).read_bytes(), (self.source / game_path).read_bytes())
        result = subprocess.run(
            [os.sys.executable, "-I", "-B", str(resources / "WrapperRuntime/patch-game-client.py"),
             str(resources / "Runtime" / game_path), str(resources / "Runtime" / game_path)],
            text=True, capture_output=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_unknown_game_client_preserves_last_complete_payload(self):
        resources = self.stage()
        game_path = "embeds/Flash/v855097-855094/FarmGame.swf"
        previous = (resources / "Runtime" / game_path).read_bytes()
        (self.source / game_path).write_bytes(b"unsupported client revision")
        self.stage(succeeds=False)
        self.assertEqual((resources / "Runtime" / game_path).read_bytes(), previous)
        self.assertFalse(list(resources.glob(".farmvillage-stage.*")))

    def test_missing_meadows_runtime_module_preserves_complete_payload(self):
        resources = self.stage()
        previous = (resources / "Runtime/.payload-version").read_bytes()
        for name in ("meadows_client.py", "client_graphics.py", "meadows_rules.py", "meadows_storage.py", "commands.py", "storage.py"):
            with self.subTest(module=name):
                source = self.source / name
                original = source.read_bytes()
                source.unlink()
                try:
                    self.stage(succeeds=False)
                    self.assertEqual((resources / "Runtime/.payload-version").read_bytes(), previous)
                    self.assertFalse(list(resources.glob(".farmvillage-stage.*")))
                finally:
                    source.write_bytes(original)

    def test_incremental_build_drops_removed_root_modules_and_helpers(self):
        (self.source / "removed.py").write_text("# old module\n")
        (self.source / "macOS/Runtime/removed_helper.py").write_text("# old helper\n")
        resources = self.stage()
        self.assertTrue((resources / "Runtime/removed.py").exists())
        (self.source / "removed.py").unlink()
        (self.source / "macOS/Runtime/removed_helper.py").unlink()
        (self.source / "replacement.py").write_text("# replacement\n")
        self.stage()
        self.assertFalse((resources / "Runtime/removed.py").exists())
        self.assertFalse((resources / "WrapperRuntime/removed_helper.py").exists())
        self.assertTrue((resources / "Runtime/replacement.py").exists())

    def test_heritage_is_independent_of_private_game_assets_and_removes_stale_art(self):
        heritage = self.source / "macOS/Resources/Heritage"
        (heritage / "removed-image.png").write_bytes(b"retired source art")
        (heritage / ".DS_Store").write_bytes(b"private Finder metadata")
        resources = self.stage()
        self.assertEqual((resources / "Heritage/heading.ttf").read_bytes(), b"private Merkin fixture")
        self.assertTrue((resources / "Heritage/removed-image.png").exists())
        self.assertFalse((resources / "Runtime/assets").exists())
        self.assertFalse((resources / "Heritage/.DS_Store").exists())
        (heritage / "removed-image.png").unlink()
        (heritage / "new-image.png").write_bytes(b"new source art")
        self.stage()
        self.assertFalse((resources / "Heritage/removed-image.png").exists())
        self.assertTrue((resources / "Heritage/new-image.png").exists())

    def test_missing_heritage_preserves_complete_native_and_runtime_payloads(self):
        resources = self.stage()
        previous_runtime = (resources / "Runtime/server.py").read_bytes()
        previous_logo = (resources / "Heritage/farmville-logo.png").read_bytes()
        (self.source / "server.py").write_text("# incomplete replacement\n")
        shutil.rmtree(self.source / "macOS/Resources/Heritage")
        self.stage(succeeds=False)
        self.assertEqual((resources / "Runtime/server.py").read_bytes(), previous_runtime)
        self.assertEqual((resources / "Heritage/farmville-logo.png").read_bytes(), previous_logo)
        self.assertFalse(list(resources.glob(".farmvillage-stage.*")))

    def test_private_data_git_tests_and_bytecode_are_excluded(self):
        for name in ("saves", "assets", "cache", "tmp", ".git", "macOS/Tests"):
            directory = self.source / name
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "private.txt").write_text("must not be bundled\n")
        for name in ("templates/__pycache__", "macOS/Runtime/__pycache__"):
            directory = self.source / name
            directory.mkdir()
            (directory / "module.pyc").write_bytes(b"cached")
        (self.source / "templates/.DS_Store").write_text("metadata")
        resources = self.stage()
        for name in ("saves", "assets", "cache", "tmp", ".git", "macOS"):
            self.assertFalse((resources / "Runtime" / name).exists(), name)
        self.assertFalse((resources / "Runtime/GodBarn/workspace").exists())
        self.assertFalse((resources / "Runtime/GodBarn/data/bootstrap-save.json").exists())
        self.assertFalse((resources / "Runtime/GodBarn/data/provenance.json").exists())
        self.assertFalse(list(resources.rglob("*.pyc")))
        self.assertFalse(list(resources.rglob(".DS_Store")))

    def test_failed_staging_preserves_last_complete_payload(self):
        resources = self.stage()
        previous = (resources / "Runtime/server.py").read_bytes()
        (self.source / "server.py").write_text("# incomplete replacement\n")
        (self.source / "requirements.txt").unlink()
        self.stage(succeeds=False)
        self.assertEqual((resources / "Runtime/server.py").read_bytes(), previous)
        self.assertFalse(list(resources.glob(".farmvillage-stage.*")))

    def test_fingerprint_changes_with_content_and_is_location_independent(self):
        first = self.stage()
        fingerprint = (first / "Runtime/.payload-version").read_text()
        other = self.stage(product=self.base / "Different Build Product")
        self.assertEqual((other / "Runtime/.payload-version").read_text(), fingerprint)
        (self.source / "templates/fixture.txt").write_text("changed\n")
        self.stage()
        self.assertNotEqual((first / "Runtime/.payload-version").read_text(), fingerprint)

    def test_runtime_updates_change_fingerprint_and_remove_retired_core_files(self):
        self.runtime_files["retired-core.js"] = b"retired reviewed core"
        directory = self.write_runtime_package()
        resources = self.stage()
        retired = resources / "Runtime/ruffle_runtime" / self.runtime_id / "retired-core.js"
        self.assertTrue(retired.exists())
        fingerprint = (resources / "Runtime/.payload-version").read_bytes()
        del self.runtime_files["retired-core.js"]
        (directory / "retired-core.js").unlink()
        self.runtime_files["core.wasm"] += b"new reviewed revision"
        self.write_runtime_package()
        self.stage()
        self.assertFalse(retired.exists())
        self.assertNotEqual((resources / "Runtime/.payload-version").read_bytes(), fingerprint)

    def test_incomplete_reviewed_runtime_preserves_last_complete_bundle(self):
        resources = self.stage()
        published = resources / "Runtime/ruffle_runtime" / self.runtime_id / "core.wasm"
        previous = published.read_bytes()
        fingerprint = (resources / "Runtime/.payload-version").read_bytes()
        (self.source / "ruffle_runtime" / self.runtime_id / "core.wasm").unlink()
        self.stage(succeeds=False)
        self.assertEqual(published.read_bytes(), previous)
        self.assertEqual((resources / "Runtime/.payload-version").read_bytes(), fingerprint)
        self.assertFalse(list(resources.glob(".farmvillage-stage.*")))

    def test_companion_changes_invalidate_runtime_fingerprint(self):
        resources = self.stage()
        fingerprint = (resources / "Runtime/.payload-version").read_text()
        (self.base / "GodBarn/static/app.js").write_text("updated companion fixture")
        self.stage()
        self.assertNotEqual((resources / "Runtime/.payload-version").read_text(), fingerprint)


if __name__ == "__main__":
    unittest.main()
