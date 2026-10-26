"""Isolated deployment checks; no SSH, systemd, live farm, or real service runs."""
from contextlib import redirect_stdout, redirect_stderr
import gzip
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/install_bifrost_barn.py'
SPEC = importlib.util.spec_from_file_location('barn_deploy_tests', SCRIPT)
deploy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deploy)


class FakeService:
    def __init__(self):
        self.calls = []

    def preflight(self):
        self.calls.append('preflight')

    def stop(self):
        self.calls.append('stop')

    def start(self):
        self.calls.append('start')


class BarnDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='barn-deployment-')
        self.root = Path(self.temporary.name).resolve()
        self.hosting = self.root / 'hosting'
        self.hosting.mkdir()
        self.write(self.hosting / 'GodBarn/integration.py', b'original Barn loader\n')
        self.write(self.hosting / 'server_runner.py', b'unchanged runner\n')
        self.write(self.hosting / 'start-server.sh', b'unchanged launcher\n')
        self.seal(self.hosting)
        self.release = self.root / 'release' / deploy.RELEASE
        self.write(self.release / 'Runtime/server.py', b'sealed game source\n')
        self.write(self.release / 'Runtime/ruffle/.release.json', b'sealed hidden identity\n')
        self.seal(self.release)
        for name in deploy.PROTECTED:
            self.write(self.root / 'data' / name / 'preserve.json', ('private ' + name).encode())
        self.write(self.root / 'data/.lan-server/owner.lock', b'1234\n')
        self.write(self.root / 'data/.lan-server/session.secret', b'x' * 32)
        self.files = {'GodBarn/' + name: b'' for name in deploy.MODULES}
        self.files.update({'GodBarn/data/' + name: b'{}' for name in deploy.DATA})
        self.files.update({'GodBarn/static/' + name: name.encode() for name in
                           ('index.html', 'app.js', 'style.css', 'farmville.css')})
        self.files['GodBarn/data/catalog.json.gz'] = gzip.compress(b'[]', mtime=0)
        self.files['GodBarn/static/assets/ui/missing-art.svg'] = b'<svg/>'
        self.files['GodBarn/integration.py'] = b'def register_god_barn(app, **arguments):\n    return arguments\n'
        self.archive = self.root / 'barn.tar.gz'
        self.make_archive()
        self.service = FakeService()
        self.initial_data = deploy.inventory(self.root / 'data')
        self.original_loader = (self.hosting / 'GodBarn/integration.py').read_bytes()
        self.original_sums = (self.hosting / 'SHA256SUMS').read_bytes()

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def write(path, contents):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)

    @staticmethod
    def seal(path):
        rows = []
        for item in sorted(path.rglob('*')):
            if item.is_file() and item.name != 'SHA256SUMS':
                rows.append(deploy.digest(item.read_bytes()) + '  ' + item.relative_to(path).as_posix() + '\n')
        (path / 'SHA256SUMS').write_text(''.join(rows))

    def make_archive(self, extra=None):
        with tarfile.open(self.archive, 'w:gz') as output:
            for name, contents in self.files.items():
                member = tarfile.TarInfo(name)
                member.size = len(contents)
                output.addfile(member, io.BytesIO(contents))
            if extra is not None:
                if isinstance(extra, str):
                    extra = tarfile.TarInfo(extra)
                    extra.size = 1
                    output.addfile(extra, io.BytesIO(b'x'))
                else:
                    output.addfile(extra)
        self.expected = deploy.digest(self.archive.read_bytes())

    def run_deploy(self, health=lambda root, files: None, **kwargs):
        return deploy.deploy(self.archive, self.expected, root=self.root,
                             service=self.service, health=health, **kwargs)

    def select_artwork(self, contents=b'original Amsterdam icon', *, shared=False):
        self.art_path = 'static/assets/items/b3f0d2d2577e2d5d575533d976eedc02.png'
        self.asset_path = 'dialogs/amsterdam/landbundle/b3f0d2d2577e2d5d575533d976eedc02.png'
        self.art_contents = contents
        self.requirement = {'path': self.art_path, 'assetPath': self.asset_path,
                            'sha256': deploy.digest(contents), 'bytes': len(contents)}
        self.catalog = [{'name': 'pkg_landbundle_reward_amsterdam',
                         'image': '/' + self.art_path, 'hasOriginalThumbnail': True,
                         'artwork': {'status': 'exact', 'sha256': deploy.digest(contents),
                                     'bytes': len(contents)}}]
        self.files['GodBarn/data/catalog.json.gz'] = gzip.compress(json.dumps(self.catalog).encode(), mtime=0)
        self.files['GodBarn/data/asset-map.json'] = json.dumps({self.art_path: self.asset_path}).encode()
        (self.root / 'data/assets').mkdir(parents=True, exist_ok=True)
        if shared:
            self.write(self.root / 'data/assets' / self.asset_path, contents)
        self.make_archive()

    def make_supplement(self, members=None):
        archive = self.root / 'artwork.tar.gz'
        with tarfile.open(archive, 'w:gz') as output:
            for name, contents in (members or [('GodBarn/' + self.art_path, self.art_contents)]):
                if isinstance(name, tarfile.TarInfo):
                    output.addfile(name)
                    continue
                member = tarfile.TarInfo(name)
                member.size = len(contents)
                output.addfile(member, io.BytesIO(contents))
        return {'artwork_archive': archive, 'artwork_sha256': deploy.file_digest(archive)}

    def test_success_only_publishes_barn_and_preserves_game_farms_and_credentials(self):
        credential = self.root / 'data/.lan-server/session.secret'
        credential_metadata = credential.stat()
        original_runner = (self.hosting / 'server_runner.py').read_bytes()
        backup = self.run_deploy()
        self.assertEqual(self.service.calls, ['preflight', 'stop', 'start'])
        self.assertEqual(deploy.inventory(self.root / 'data'), self.initial_data)
        self.assertEqual((self.hosting / 'server_runner.py').read_bytes(), original_runner)
        self.assertEqual(credential.stat().st_mtime_ns, credential_metadata.st_mtime_ns)
        self.assertEqual(credential.read_bytes(), b'x' * 32)
        deploy.verify_checksums(self.release)
        entries = deploy.verify_checksums(self.hosting)
        self.assertIn('god-barn-releases/' + self.expected[:12] + '/GodBarn/catalog_tools.py', entries)
        self.assertEqual((backup / 'integration.py').read_bytes(), self.original_loader)
        self.assertEqual((backup / 'SHA256SUMS').read_bytes(), self.original_sums)
        self.assertEqual(sorted(path.name for path in backup.iterdir()),
                         ['SHA256SUMS', 'integration.py', 'inventory-after-start.json',
                          'inventory-before-stop.json', 'inventory-stopped.json'])

    def test_new_untabbed_index_is_preserved_in_the_versioned_overlay(self):
        index = b'{"schema":1,"items":{"pinkcow":{"origin":"other"}}}'
        self.files['GodBarn/data/untabbed.json'] = index
        self.make_archive()
        self.run_deploy()
        path = 'god-barn-releases/' + self.expected[:12] + '/GodBarn/data/untabbed.json'
        self.assertEqual((self.hosting / path).read_bytes(), index)
        self.assertIn(path, deploy.verify_checksums(self.hosting))
        self.assertEqual(deploy.inventory(self.root / 'data'), self.initial_data)

    def test_loader_imports_whole_versioned_package_and_forces_new_resource_root(self):
        self.run_deploy()
        source = (self.hosting / 'GodBarn/integration.py').read_text()
        namespace = {}
        exec(compile(source, '<isolated Barn loader>', 'exec'), namespace)
        try:
            result = namespace['register_god_barn'](object(), root='old Runtime/GodBarn', marker=42)
            self.assertEqual(result['root'], self.hosting / 'god-barn-releases' / self.expected[:12] / 'GodBarn')
            self.assertEqual(result['marker'], 42)
        finally:
            for name in list(sys.modules):
                if name.startswith('_god_barn_' + self.expected[:12]):
                    del sys.modules[name]

    def test_health_failure_rolls_back_only_barn_then_restarts_previous_service(self):
        def failure(root, files):
            raise RuntimeError('synthetic health mismatch')
        with self.assertRaisesRegex(RuntimeError, 'synthetic health mismatch'):
            self.run_deploy(failure)
        self.assertEqual(self.service.calls, ['preflight', 'stop', 'start', 'stop', 'start'])
        self.assertEqual((self.hosting / 'GodBarn/integration.py').read_bytes(), self.original_loader)
        self.assertEqual((self.hosting / 'SHA256SUMS').read_bytes(), self.original_sums)
        self.assertEqual(deploy.inventory(self.root / 'data'), self.initial_data)
        deploy.verify_checksums(self.release)

    def test_post_stop_inventory_failure_restarts_the_original_service(self):
        with mock.patch.object(deploy, 'inventory', side_effect=[self.initial_data,
                                                               RuntimeError('synthetic inventory failure')]):
            with self.assertRaisesRegex(RuntimeError, 'synthetic inventory failure'):
                self.run_deploy()
        self.assertEqual(self.service.calls, ['preflight', 'stop', 'start'])
        self.assertEqual((self.hosting / 'GodBarn/integration.py').read_bytes(), self.original_loader)
        self.assertEqual((self.hosting / 'SHA256SUMS').read_bytes(), self.original_sums)
        self.assertEqual(deploy.inventory(self.root / 'data'), self.initial_data)

    def test_concurrent_farm_write_is_reported_and_never_undone(self):
        save = self.root / 'data/saves/preserve.json'
        def concurrent_user(root, files):
            save.write_bytes(b'user progress while a tab was open')
        with self.assertRaisesRegex(RuntimeError, 'Protected farm data changed after restart'):
            self.run_deploy(concurrent_user)
        self.assertEqual(save.read_bytes(), b'user progress while a tab was open')
        self.assertEqual((self.hosting / 'GodBarn/integration.py').read_bytes(), self.original_loader)

    def test_wrong_archive_checksum_stops_before_service_or_hosting_mutation(self):
        self.expected = '0' * 64
        with self.assertRaisesRegex(ValueError, 'expected SHA256'):
            self.run_deploy()
        self.assertEqual(self.service.calls, [])
        self.assertEqual((self.hosting / 'SHA256SUMS').read_bytes(), self.original_sums)

    def test_existing_game_or_hosting_checksum_failure_stops_before_service(self):
        for path in (self.hosting / 'server_runner.py', self.release / 'Runtime/server.py'):
            with self.subTest(path=path):
                original = path.read_bytes()
                path.write_bytes(b'bad checksum')
                with self.assertRaisesRegex(ValueError, 'Installed checksum mismatch'):
                    self.run_deploy()
                self.assertEqual(self.service.calls, [])
                path.write_bytes(original)

    def test_unsafe_or_private_archive_paths_are_rejected(self):
        for name in ('GodBarn/../save.json', '/GodBarn/engine.py', 'Runtime/server.py',
                     'GodBarn/workspace/farm.json', 'GodBarn/data/bootstrap-save.json',
                     'GodBarn/static/assets/items/cow.png', 'GodBarn/static/bootstrap-save.json',
                     'GodBarn/static/./asset.png', 'GodBarn/static//asset.png'):
            with self.subTest(name=name):
                self.make_archive(name)
                with self.assertRaises(ValueError):
                    deploy.archive_files(self.archive, self.expected)

    def test_archive_links_duplicates_and_incomplete_package_are_rejected(self):
        link = tarfile.TarInfo('GodBarn/static/link')
        link.type, link.linkname = tarfile.SYMTYPE, '/etc/passwd'
        self.make_archive(link)
        with self.assertRaisesRegex(ValueError, 'Unexpected'):
            deploy.archive_files(self.archive, self.expected)
        self.make_archive('GodBarn/engine.py')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            deploy.archive_files(self.archive, self.expected)
        del self.files['GodBarn/catalog_tools.py']
        self.make_archive()
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            deploy.archive_files(self.archive, self.expected)

    def test_asset_escape_is_rejected_before_stopping(self):
        for path in ('../saves/preserve.json', '/etc/passwd'):
            with self.subTest(path=path):
                self.files['GodBarn/data/asset-map.json'] = json.dumps({'image': path}).encode()
                self.make_archive()
                self.service.calls.clear()
                with self.assertRaises((ValueError, RuntimeError)):
                    self.run_deploy()
                self.assertEqual(self.service.calls, [])

    def test_artwork_audit_reports_missing_and_corrupt_exact_selected_art_without_service_operations(self):
        self.select_artwork()
        result = deploy.audit_artwork(self.archive, self.expected, root=self.root)
        self.assertEqual(result, {'schema': 1, 'bundleSha256': self.expected, 'items': [self.requirement]})
        self.assertEqual(self.service.calls, [])
        self.assertFalse((self.hosting / 'god-barn-releases').exists())
        self.write(self.root / 'data/assets' / self.asset_path, b'x' * len(self.art_contents))
        self.assertEqual(deploy.audit_artwork(self.archive, self.expected, root=self.root)['items'], [self.requirement])
        self.write(self.root / 'data/assets' / self.asset_path, self.art_contents)
        self.assertEqual(deploy.audit_artwork(self.archive, self.expected, root=self.root)['items'], [])
        self.assertEqual(deploy.inventory(self.root / 'data'), self.initial_data)

    def test_audit_cli_stdout_is_only_json_and_progress_stays_on_stderr(self):
        self.select_artwork()
        actual_audit = deploy.audit_artwork
        stdout, stderr = io.StringIO(), io.StringIO()
        arguments = ['install_bifrost_barn.py', '--archive', str(self.archive),
                     '--expected-sha256', self.expected, '--audit-artwork']
        with mock.patch.object(sys, 'argv', arguments), mock.patch.object(
                deploy, 'audit_artwork', side_effect=lambda archive, expected:
                actual_audit(archive, expected, root=self.root)), redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(deploy.main(), 0)
        self.assertEqual(json.loads(stdout.getvalue()),
                         {'schema': 1, 'bundleSha256': self.expected, 'items': [self.requirement]})
        self.assertIn('Artwork audit complete', stderr.getvalue())
        self.assertEqual(self.service.calls, [])

    def test_selected_missing_art_still_fails_before_stop_without_a_supplement(self):
        self.select_artwork()
        with self.assertRaisesRegex(RuntimeError, 'Missing or corrupt selected artwork'):
            self.run_deploy()
        self.assertEqual(self.service.calls, ['preflight'])
        self.assertEqual((self.hosting / 'GodBarn/integration.py').read_bytes(), self.original_loader)
        self.assertEqual(deploy.inventory(self.root / 'data'), self.initial_data)

    def test_unused_missing_mapping_is_ignored_but_duplicate_name_does_not_change_selection(self):
        self.select_artwork(shared=True)
        mapping = {self.art_path: self.asset_path, 'static/assets/items/' + 'a' * 32 + '.png': 'unused/missing.png'}
        self.files['GodBarn/data/asset-map.json'] = json.dumps(mapping).encode()
        duplicate = dict(self.catalog[0], image='/static/assets/items/' + 'a' * 32 + '.png')
        self.files['GodBarn/data/catalog.json.gz'] = gzip.compress(json.dumps(self.catalog + [duplicate]).encode(), mtime=0)
        self.make_archive()
        self.assertEqual(deploy.audit_artwork(self.archive, self.expected, root=self.root)['items'], [])
        self.run_deploy()
        self.assertEqual(self.service.calls, ['preflight', 'stop', 'start'])

    def test_missing_amsterdam_icon_is_installed_only_inside_barn_and_repeat_is_verified(self):
        self.select_artwork()
        supplement = self.make_supplement()
        self.run_deploy(**supplement)
        version = self.expected[:12] + '-' + supplement['artwork_sha256'][:12]
        art = self.hosting / 'god-barn-releases' / version / 'GodBarn' / self.art_path
        self.assertEqual(art.read_bytes(), self.art_contents)
        self.assertFalse((self.root / 'data/assets' / self.asset_path).exists())
        entries = deploy.verify_checksums(self.hosting)
        self.assertEqual(entries[art.relative_to(self.hosting).as_posix()], deploy.digest(self.art_contents))
        self.assertEqual(deploy.inventory(self.root / 'data'), self.initial_data)
        deploy.verify_checksums(self.release)
        self.run_deploy(**supplement)
        self.assertEqual(self.service.calls, ['preflight', 'stop', 'start', 'preflight', 'stop', 'start'])
        self.assertEqual(deploy.inventory(self.root / 'data'), self.initial_data)

    def test_supplement_version_alias_loads_the_package_and_relative_imports(self):
        self.select_artwork()
        self.files['GodBarn/engine.py'] = b'FLAG = 42\n'
        self.files['GodBarn/integration.py'] = (b'from .engine import FLAG\n'
            b'def register_god_barn(app, **arguments):\n    return FLAG, arguments["root"]\n')
        self.make_archive()
        supplement = self.make_supplement()
        self.run_deploy(**supplement)
        version = self.expected[:12] + '-' + supplement['artwork_sha256'][:12]
        namespace = {}
        exec(compile((self.hosting / 'GodBarn/integration.py').read_bytes(), '<supplement Barn loader>', 'exec'), namespace)
        try:
            flag, root = namespace['register_god_barn'](object(), root='old Runtime/GodBarn')
            self.assertEqual(flag, 42)
            self.assertEqual(root, self.hosting / 'god-barn-releases' / version / 'GodBarn')
        finally:
            for name in list(sys.modules):
                if name.startswith('_god_barn_' + version):
                    del sys.modules[name]

    def test_corrupt_shared_art_is_supplemented_without_changing_original_and_rollback_preserves_saves(self):
        self.select_artwork()
        shared = self.root / 'data/assets' / self.asset_path
        self.write(shared, b'x' * len(self.art_contents))
        original = shared.read_bytes(), shared.stat().st_mtime_ns
        supplement = self.make_supplement()
        def failure(root, files):
            raise RuntimeError('synthetic supplemental health failure')
        with self.assertRaisesRegex(RuntimeError, 'synthetic supplemental health failure'):
            self.run_deploy(failure, **supplement)
        self.assertEqual((shared.read_bytes(), shared.stat().st_mtime_ns), original)
        self.assertEqual((self.hosting / 'GodBarn/integration.py').read_bytes(), self.original_loader)
        self.assertEqual((self.hosting / 'SHA256SUMS').read_bytes(), self.original_sums)
        self.assertEqual(deploy.inventory(self.root / 'data'), self.initial_data)
        deploy.verify_checksums(self.release)

    def test_supplement_paths_unselected_art_links_and_wrong_bytes_are_rejected_before_stop(self):
        self.select_artwork()
        link = tarfile.TarInfo('GodBarn/' + self.art_path)
        link.type, link.linkname = tarfile.SYMTYPE, '/etc/passwd'
        cases = [
            [('GodBarn/../saves/preserve.json', b'injected')],
            [('GodBarn/static/assets/items/' + 'a' * 32 + '.png', self.art_contents)],
            [('GodBarn/' + self.art_path, b'x' * len(self.art_contents))],
            [(link, None)],
            [('GodBarn/' + self.art_path, self.art_contents)] * 2,
        ]
        for members in cases:
            with self.subTest(members=members):
                self.service.calls.clear()
                supplement = self.make_supplement(members)
                with self.assertRaises((ValueError, RuntimeError)):
                    self.run_deploy(**supplement)
                self.assertNotIn('stop', self.service.calls)
                self.assertEqual(deploy.inventory(self.root / 'data'), self.initial_data)
                self.assertEqual((self.hosting / 'GodBarn/integration.py').read_bytes(), self.original_loader)

    def test_artwork_mapping_and_shared_symlinks_are_rejected_even_when_unused(self):
        self.select_artwork()
        mapping = {self.art_path: self.asset_path, 'unused': '../saves/preserve.json'}
        self.files['GodBarn/data/asset-map.json'] = json.dumps(mapping).encode()
        self.make_archive()
        with self.assertRaisesRegex(ValueError, 'Unsafe relative path'):
            deploy.audit_artwork(self.archive, self.expected, root=self.root)
        self.select_artwork()
        shared = self.root / 'data/assets' / self.asset_path
        shared.parent.mkdir(parents=True, exist_ok=True)
        shared.symlink_to(self.root / 'data/saves/preserve.json')
        with self.assertRaisesRegex(RuntimeError, 'symbolic link'):
            deploy.audit_artwork(self.archive, self.expected, root=self.root)
        with self.assertRaisesRegex(RuntimeError, 'symbolic link'):
            self.run_deploy()
        self.assertNotIn('stop', self.service.calls)

    def test_supplement_checksum_and_declaration_mismatches_are_rejected_before_stop(self):
        self.select_artwork()
        supplement = self.make_supplement()
        supplement['artwork_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'artwork archive does not match'):
            self.run_deploy(**supplement)
        self.assertNotIn('stop', self.service.calls)
        self.catalog[0]['artwork']['sha256'] = 'invalid'
        self.files['GodBarn/data/catalog.json.gz'] = gzip.compress(json.dumps(self.catalog).encode(), mtime=0)
        self.make_archive()
        with self.assertRaisesRegex(ValueError, 'invalid SHA256'):
            self.run_deploy()
        self.assertNotIn('stop', self.service.calls)

    def test_symbolic_link_output_or_data_path_is_refused(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (self.hosting / 'god-barn-releases').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, 'symbolic link'):
            self.run_deploy()
        self.assertNotIn('stop', self.service.calls)
        (self.hosting / 'god-barn-releases').unlink()
        (self.root / 'data/saves/link.json').symlink_to(self.root / 'data/god-barn/preserve.json')
        with self.assertRaisesRegex(RuntimeError, 'protected data entry'):
            self.run_deploy()

    def test_repeat_deployment_reuses_verified_payload_without_duplicate_farm_operations(self):
        self.run_deploy()
        first = (self.hosting / 'SHA256SUMS').read_bytes()
        self.run_deploy()
        self.assertEqual((self.hosting / 'SHA256SUMS').read_bytes(), first)
        self.assertEqual(deploy.inventory(self.root / 'data'), self.initial_data)


if __name__ == '__main__':
    unittest.main()
