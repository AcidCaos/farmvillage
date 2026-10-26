#!/usr/bin/env python3
"""Synthetic native identity and extraction checks; no downloads or original media."""
import hashlib, importlib.util, io, json, subprocess, sys, tarfile, tempfile, unittest, zipfile
from unittest import mock
from pathlib import Path
spec = importlib.util.spec_from_file_location('native_resources', Path(__file__).with_name('native_resources.py'))
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)

class NativeResourceTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fv-native-resource-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def prepared(self):
        root = self.root / 'native'
        entries = {}
        for name in native.required_files():
            p = root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            raw = ('synthetic identity ' + name).encode()
            p.write_bytes(raw)
            entries[name] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        manifest = {'schema': 1, 'kind': 'public-native-resources', 'files': entries}
        (root / 'native-manifest.json').write_text(json.dumps(manifest))
        return (root, manifest)

    def test_complete_set_and_changed_art(self):
        (root, _) = self.prepared()
        self.assertEqual(native.check(self.root)['status'], 'ready')
        (root / 'Heritage/cow-idle-01.png').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'differs or is missing'):
            native.check(self.root)

    def test_required_icon_or_font_cannot_be_hidden_elsewhere(self):
        (root, manifest) = self.prepared()
        for name in ['Assets.xcassets/AppIcon.appiconset/icon_512x512@2x.png', 'Heritage/heading.ttf']:
            altered = {**manifest, 'files': dict(manifest['files'])}
            altered['files']['other/' + Path(name).name] = altered['files'].pop(name)
            (root / 'native-manifest.json').write_text(json.dumps(altered))
            with self.assertRaisesRegex(ValueError, 'omitted required'):
                native.check(self.root)

    def test_linked_root_refused(self):
        self.prepared()
        link = self.root.parent / (self.root.name + '-link')
        link.symlink_to(self.root, target_is_directory=True)
        self.addCleanup(link.unlink)
        with self.assertRaises(ValueError):
            native.check(link)

    def test_extra_state_is_not_artwork(self):
        (root, _) = self.prepared()
        p = root / 'Heritage/saves/old.json'
        p.parent.mkdir()
        p.write_text('{"synthetic":true}')
        with self.assertRaisesRegex(ValueError, 'unreviewed additional'):
            native.check(self.root)

    def test_added_manifest_entry_is_not_a_native_resource(self):
        (root, manifest) = self.prepared()
        p = root / 'old-farm.json'
        p.write_bytes(b'synthetic')
        manifest['files']['old-farm.json'] = {'bytes': 9, 'sha256': hashlib.sha256(b'synthetic').hexdigest()}
        (root / 'native-manifest.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'unreviewed additional'):
            native.check(self.root)

    def test_source_checkout_is_not_a_resource_target(self):
        with mock.patch.object(native, 'prepare_tools') as tools:
            with self.assertRaisesRegex(ValueError, 'external resource folder'):
                native.prepare(native.ROOT / 'generated', self.root, self.root, '/not/a/python')
        tools.assert_not_called()

    def test_generation_uses_selected_inputs_and_publishes_only_complete_pack(self):
        original, assets = self.root / 'original', self.root / 'assets'
        original.mkdir()
        assets.mkdir()
        calls = []
        def fake_process(arguments, **kwargs):
            calls.append((arguments, kwargs))
            if '--output' in arguments:
                output = Path(arguments[arguments.index('--output') + 1])
                names = {name for name in native.required_files() if name.startswith('Heritage/')}
                names = {name[len('Heritage/'):] for name in names}
            else:
                output = Path(arguments[arguments.index('--icon-output') + 1])
                names = {name[len('Assets.xcassets/'):] for name in native.required_files() if name.startswith('Assets.xcassets/')}
            for name in names:
                path = output / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(('synthetic export ' + name).encode())
            process = mock.Mock(pid=999999)
            process.wait.return_value = 0
            return process
        with mock.patch.object(native, 'prepare_tools', return_value=(self.root / 'fake-java', self.root / 'fake-ffdec.jar')) as tools, \
                mock.patch.object(native.subprocess, 'Popen', side_effect=fake_process):
            result = native.prepare(self.root, original, assets, sys.executable)
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['files'], len(native.required_files()))
        self.assertEqual(len(calls), 2)
        first = calls[0][0]
        self.assertEqual(first[0], sys.executable)
        self.assertEqual(first[first.index('--game-root') + 1], str(original))
        self.assertEqual(first[first.index('--assets-root') + 1], str(assets))
        self.assertTrue(calls[0][1]['start_new_session'])
        self.assertFalse(list(self.root.glob('.native-stage-*')))
        with mock.patch.object(native, 'prepare_tools') as tools:
            native.prepare(self.root, original, assets, sys.executable)
        tools.assert_not_called()

    def test_failed_export_does_not_publish_a_partial_pack(self):
        original, assets = self.root / 'original', self.root / 'assets'
        original.mkdir()
        assets.mkdir()
        process = mock.Mock(pid=999999)
        process.wait.return_value = 4
        with mock.patch.object(native, 'prepare_tools', return_value=(self.root / 'fake-java', self.root / 'fake-ffdec.jar')), \
                mock.patch.object(native.subprocess, 'Popen', return_value=process):
            with self.assertRaises(subprocess.CalledProcessError):
                native.prepare(self.root, original, assets, sys.executable)
        self.assertFalse((self.root / 'native').exists())
        self.assertFalse(list(self.root.glob('.native-stage-*')))

    def test_zip_traversal_and_existing_target_refused(self):
        archive = self.root / 'unsafe.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('../escape.txt', 'no')
        with self.assertRaises(ValueError):
            native.extract_tool(archive, self.root / 'extract')
        self.assertFalse((self.root / 'escape.txt').exists())
        existing = self.root / 'existing'
        existing.mkdir()
        with self.assertRaises(ValueError):
            native.extract_tool(archive, existing)

    def test_tar_link_escape_refused(self):
        archive = self.root / 'unsafe.tar.gz'
        with tarfile.open(archive, 'w:gz') as t:
            e = tarfile.TarInfo('tool/link')
            e.type = tarfile.SYMTYPE
            e.linkname = '../../outside'
            t.addfile(e)
        with self.assertRaises(ValueError):
            native.extract_tool(archive, self.root / 'extract')

    def test_safe_tar_preserves_executable_and_internal_link(self):
        archive = self.root / 'safe.tar.gz'
        with tarfile.open(archive, 'w:gz') as t:
            e = tarfile.TarInfo('jre/bin/java')
            e.mode = 0o755
            e.size = 4
            t.addfile(e, io.BytesIO(b'fake'))
            link = tarfile.TarInfo('jre/java')
            link.type = tarfile.SYMTYPE
            link.linkname = 'bin/java'
            t.addfile(link)
        target = self.root / 'extract'
        native.extract_tool(archive, target)
        self.assertEqual((target / 'jre/bin/java').read_bytes(), b'fake')
        self.assertEqual((target / 'jre/bin/java').stat().st_mode & 0o777, 0o755)
        self.assertTrue((target / 'jre/java').is_symlink())

    def test_tar_member_below_link_refused(self):
        archive = self.root / 'unsafe.tar.gz'
        with tarfile.open(archive, 'w:gz') as t:
            e = tarfile.TarInfo('jre/bin')
            e.type = tarfile.SYMTYPE
            e.linkname = 'other'
            t.addfile(e)
            e = tarfile.TarInfo('jre/bin/java')
            e.size = 4
            t.addfile(e, io.BytesIO(b'fake'))
        with self.assertRaisesRegex(ValueError, 'below archive link'):
            native.extract_tool(archive, self.root / 'extract')
if __name__ == '__main__':
    unittest.main()
