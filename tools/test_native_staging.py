"""Tiny synthetic external-pack build/staging checks; never invoke Xcode or Java."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RSYNC = '/usr/bin/rsync'  # Hard-coded by FarmVillage/macOS/Scripts/bundle-runtime.sh.
spec = importlib.util.spec_from_file_location('fv_native_stage_test', ROOT / 'tools/native_resources.py')
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)
VERIFY = '''import argparse,json,pathlib
p=argparse.ArgumentParser(); p.add_argument('--payload',type=pathlib.Path); p.add_argument('--prepared-runtime-pin-sha256'); a=p.parse_args()
assert json.loads((a.payload/'PREPARED_RUNTIME.json').read_text())['runtime_manifest_sha256']==a.prepared_runtime_pin_sha256
assert (a.payload/'ruffle_runtime/fake/player.js').read_bytes()==b'synthetic player'
'''


class NativeStagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='fv-native-staging-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.source = self.base / 'source checkout'
        self.pack = self.base / 'resource pack'
        self.buildroot = self.pack / 'macos-build'
        self.mac = self.source / 'FarmVillage/macOS'
        self.runtime = self.pack / 'Runtime'
        for folder in (self.mac / 'Scripts', self.source / 'tools', self.runtime):
            folder.mkdir(parents=True)
        for name in ('build.sh', 'bundle-runtime.sh'):
            shutil.copyfile(ROOT / 'FarmVillage/macOS/Scripts' / name, self.mac / 'Scripts' / name)
        for name in ('native_resources.py', 'public_downloads.py'):
            shutil.copyfile(ROOT / 'tools' / name, self.source / 'tools' / name)
        metadata = self.mac / 'Resources/Assets.xcassets'
        (metadata / 'AppIcon.appiconset').mkdir(parents=True)
        for name in ('Contents.json', 'AppIcon.appiconset/Contents.json'):
            shutil.copyfile(ROOT / 'FarmVillage/macOS/Resources/Assets.xcassets' / name, metadata / name)
        entries = {}
        for name in native.required_files():
            p = self.pack / 'native' / name
            p.parent.mkdir(parents=True, exist_ok=True)
            data = ('synthetic ' + name).encode()
            p.write_bytes(data)
            entries[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        (self.pack / 'native/native-manifest.json').write_text(json.dumps({'schema': 1, 'kind': 'public-native-resources', 'files': entries}))
        for parent in (self.source / 'FarmVillage', self.runtime):
            (parent / 'runtime_compatibility.py').write_text(VERIFY)
        (self.runtime / 'PREPARED_RUNTIME.json').write_text('{"schema":1,"runtime_manifest_sha256":"synthetic"}')
        (self.runtime / 'PUBLIC_RUNTIME_BUILD.json').write_text('{"synthetic":true}')
        self.assets = self.pack / 'assets'
        for name in ('Environment', 'xpromoSupport'):
            (self.assets / name).mkdir(parents=True)
        (self.runtime / 'PUBLIC_INSTALL.json').write_text(json.dumps({'schema': 1, 'assets_root': str(self.assets)}))
        player = self.runtime / 'ruffle_runtime/fake/player.js'
        player.parent.mkdir(parents=True)
        player.write_bytes(b'synthetic player')
        self.log = self.base / 'compiler.log'
        self.compiler = self.base / 'compiler-stub'
        self.compiler.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$FARMVILLAGE_TEST_COMPILER_LOG"\n')
        self.compiler.chmod(0o755)
        self.env = {'PATH': '/usr/bin:/bin', 'FARMVILLAGE_BUILD_PYTHON': sys.executable,
                    'FARMVILLAGE_XCODEBUILD': str(self.compiler), 'FARMVILLAGE_TEST_COMPILER_LOG': str(self.log)}

    def build(self, output=None, extra=()):
        return subprocess.run(['/bin/bash', str(self.mac / 'Scripts/build.sh'), 'Release',
                               '--resources', str(self.pack), '--output', str(output or self.buildroot),
                               '--python', sys.executable, *extra], env=self.env,
                              capture_output=True, text=True, timeout=15)

    def test_external_build_paths_and_selected_python_reach_only_stub(self):
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        args = self.log.read_text().splitlines()
        self.assertEqual(args[args.index('-derivedDataPath') + 1], str(self.buildroot / 'DerivedData'))
        self.assertIn('FARMVILLAGE_PUBLIC_RESOURCES=' + str(self.pack), args)
        self.assertIn('FARMVILLAGE_NATIVE_ASSET_ROOT=' + str(self.pack / 'native'), args)
        self.assertIn('FARMVILLAGE_RESOURCE_PYTHON=' + sys.executable, args)
        self.assertFalse((self.mac / '.build').exists())
        self.assertFalse(self.buildroot.exists())

    def test_repository_output_is_refused_before_compiler_or_mutation(self):
        result = self.build(self.source / 'output')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(self.log.exists())
        self.assertFalse((self.source / 'output').exists())

    def test_arbitrary_resource_subtree_is_refused(self):
        result = self.build(self.pack / 'Runtime/build')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(self.log.exists())

    def test_traversing_output_cannot_hide_a_source_destination(self):
        result = self.build(self.base / 'elsewhere/../source checkout/output')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(self.log.exists())
        self.assertFalse((self.source / 'output').exists())

    def test_changed_art_stops_before_compiler(self):
        (self.pack / 'native/Heritage/cow.png').write_bytes(b'changed')
        result = self.build()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('Native resource verification failed', result.stderr)
        self.assertFalse(self.log.exists())

    def test_changed_player_stops_before_compiler(self):
        (self.runtime / 'ruffle_runtime/fake/player.js').write_bytes(b'changed')
        result = self.build()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('Player resource verification failed', result.stderr)
        self.assertFalse(self.log.exists())

    @unittest.skipUnless(os.access(RSYNC, os.X_OK), 'UNRUN: bundle-runtime.sh calls ' + RSYNC + ', which this host lacks (macOS ships it; on Ubuntu install the rsync package)')
    def test_prepared_bundle_uses_external_media_and_receipts(self):
        required = 'client_compatibility cove_client meadows_client client_graphics meadows_rules meadows_storage england_animals england_shipping cove_rules cove_port cove_shipping cellar_progression rainforest_features rainforest_rules placement_receipts inventory_sales commands server storage'.split()
        for name in required:
            (self.runtime / (name + '.py')).write_text('# synthetic\n')
        for name in ('requirements.txt', 'LICENSE', 'README.md', 'FLASH.md'):
            (self.runtime / name).write_text('synthetic\n')
        for name in ('assethash', 'embeds', 'patched', 'templates', 'villages', 'warc_extractor', 'xml'):
            (self.runtime / name).mkdir()
        original = self.runtime / 'embeds/Flash/v855097-855094/FarmGame.swf'
        original.parent.mkdir(parents=True)
        original.write_bytes(b'synthetic original')
        barn = self.runtime / 'GodBarn'
        (barn / 'data').mkdir(parents=True)
        (barn / 'data/catalog.json.gz').write_bytes(b'synthetic compressed catalog')
        (barn / 'integration.py').write_text('# synthetic companion\n')
        (self.mac / 'Scripts/patch-game-client.py').write_text('import shutil,sys; shutil.copyfile(sys.argv[1],sys.argv[2])\n')
        (self.mac / 'Scripts/runtime.sh').write_text('# synthetic launcher\n')
        (self.mac / 'Runtime').mkdir()
        (self.mac / 'Runtime/bootstrap.py').write_text('# synthetic bootstrap\n')
        (self.mac / 'Documentation').mkdir()
        (self.mac / 'Documentation/THIRD_PARTY.md').write_text('synthetic notices\n')
        product = self.buildroot / 'synthetic.app/Contents'
        env = {**self.env, 'FARMVILLAGE_PUBLIC_RESOURCES': str(self.pack),
               'FARMVILLAGE_RESOURCE_PYTHON': sys.executable, 'TARGET_BUILD_DIR': str(product),
               'UNLOCALIZED_RESOURCES_FOLDER_PATH': 'Resources'}
        result = subprocess.run(['/bin/bash', str(self.mac / 'Scripts/bundle-runtime.sh')], env=env,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = product / 'Resources/Runtime'
        self.assertEqual((payload / 'PREPARED_RUNTIME.json').read_bytes(), (self.runtime / 'PREPARED_RUNTIME.json').read_bytes())
        self.assertEqual((payload / 'PUBLIC_RUNTIME_BUILD.json').read_bytes(), (self.runtime / 'PUBLIC_RUNTIME_BUILD.json').read_bytes())
        self.assertEqual((payload / 'PUBLIC_INSTALL.json').read_bytes(), (self.runtime / 'PUBLIC_INSTALL.json').read_bytes())
        self.assertEqual((product / 'Resources/Heritage/cow.png').read_bytes(), (self.pack / 'native/Heritage/cow.png').read_bytes())
        self.assertTrue((payload / '.payload-version').is_file())
        self.assertFalse((self.mac / 'Resources/Heritage').exists())
        self.assertFalse((payload / 'assets').exists())

    def test_native_public_assets_are_reused_without_downloading_or_cleanup(self):
        from types import SimpleNamespace
        from unittest import mock
        spec = importlib.util.spec_from_file_location('fv_native_external_assets_test', ROOT / 'FarmVillage/macOS/Runtime/native_assets.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assets = SimpleNamespace(ASSETS_DIR=str(self.assets))
        with mock.patch.dict(os.environ, {'FARMVILLAGE_ASSETS_DIR': str(self.assets)}), \
                mock.patch.object(module, 'download') as download, \
                mock.patch.object(module, 'cleanup_completed_assets') as cleanup:
            module.check_assets(assets)
            (self.assets / 'Environment').rmdir()
            with self.assertRaisesRegex(RuntimeError, 'will not download another archive'):
                module.check_assets(assets)
            download.assert_not_called()
            cleanup.assert_not_called()

    def test_launcher_passes_the_external_asset_receipt_to_bootstrap(self):
        shutil.copyfile(ROOT / 'FarmVillage/macOS/Scripts/runtime.sh', self.mac / 'Scripts/runtime.sh')
        (self.mac / 'WrapperRuntime').mkdir()
        (self.mac / 'WrapperRuntime/bootstrap.py').write_text('import os; print(os.environ["FARMVILLAGE_ASSETS_DIR"])\n')
        (self.mac / 'Runtime').mkdir()
        shutil.copyfile(self.runtime / 'PUBLIC_INSTALL.json', self.mac / 'Runtime/PUBLIC_INSTALL.json')
        # The fixture interpreter may be Apple's installed Python 3.9. Only
        # bypass the launcher's version probe, then execute our tiny fixture.
        interpreter = self.base / 'fixture-python'
        import shlex
        interpreter.write_text('#!/bin/sh\ncase "$*" in *"sys.version_info >= (3, 10)"*) exit 0;; esac\nexec ' + shlex.quote(sys.executable) + ' "$@"\n')
        interpreter.chmod(0o755)
        result = subprocess.run(['/bin/bash', str(self.mac / 'Scripts/runtime.sh'), 'start', '--python', str(interpreter)],
                                env=self.env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.assets))

    def test_native_bootstrap_staging_preserves_the_explicit_player_pin(self):
        spec = importlib.util.spec_from_file_location('fv_native_stage_bootstrap_test', ROOT / 'FarmVillage/macOS/Runtime/bootstrap.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        (self.runtime / 'server.py').write_text('# synthetic server; never executed\n')
        (self.runtime / 'requirements.txt').write_text('# synthetic requirements; never installed\n')
        data = self.base / 'new synthetic data'
        data.mkdir()
        staged, _version = module.stage_runtime(self.runtime, data)
        for name in ('PREPARED_RUNTIME.json', 'PUBLIC_RUNTIME_BUILD.json', 'PUBLIC_INSTALL.json'):
            self.assertEqual((staged / name).read_bytes(), (self.runtime / name).read_bytes())
        self.assertFalse((data / 'venv').exists())
        self.assertFalse((data / 'assets').exists())


if __name__ == '__main__':
    unittest.main()
