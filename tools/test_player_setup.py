"""Synthetic player-guide tests; no original data, network, install or build."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from unittest import mock
import urllib.request

spec = importlib.util.spec_from_file_location('player_setup', Path(__file__).with_name('player-setup.py'))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

class PlayerSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='farmvillage-player-guide-test-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / 'source'
        self.root.mkdir()
        self.raw = b'synthetic resource'
        self.identity = {'bytes': len(self.raw), 'sha256': hashlib.sha256(self.raw).hexdigest()}
        self.resources = {name: dict(self.identity) for name in ['FarmVillage/embeds/client.swf', 'FarmVillage/ruffle_runtime/player.wasm', 'GodBarn/data/catalog.json']}
        self.manifest()
        (self.root / 'docs').mkdir()
        (self.root / 'docs/PLAY_ON_MAC.md').write_text('# Local Mac guide\n')
        (self.root / 'docs/PLAY_ON_SERVER.md').write_text('# Local server guide\n')

    def manifest(self):
        (self.root / 'PrivateInputs.expected.json').write_text(json.dumps({'schema': 1, 'files': self.resources}))

    def populate(self):
        for name in self.resources:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.raw)

    def snapshot(self):
        return {str(x.relative_to(self.base)): x.read_bytes() for x in self.base.rglob('*') if not x.is_symlink() and x.is_file()}

    def main_output(self, args=None, answers=None):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = p.main(['--source-root', str(self.root), *(args or [])], input_fn=answers)
        return code, output.getvalue()

    def test_missing_inputs_grouped(self):
        report = p.build_report(self.root)
        self.assertEqual(report['resource_inputs']['missing_files'], 3)
        self.assertEqual(report['resource_inputs']['groups']['Pinned local Ruffle player']['missing'], 1)
        self.assertFalse(report['play_ready'])

    def test_matching_resources_never_claim_installer_or_gameplay(self):
        self.populate()
        report = p.build_report(self.root)
        self.assertTrue(report['prepared_resource_inputs_match'])
        self.assertFalse(report['play_ready'])
        self.assertTrue(report['public_bootstrap']['implemented'])

    def test_same_size_corrupt_input(self):
        self.populate()
        (self.root / 'FarmVillage/embeds/client.swf').write_bytes(b'x' * len(self.raw))
        self.assertEqual(p.build_report(self.root)['resource_inputs']['mismatched_files'], 1)

    def test_wrong_size_input(self):
        self.populate()
        (self.root / 'GodBarn/data/catalog.json').write_bytes(b'x')
        self.assertEqual(p.build_report(self.root)['resource_inputs']['mismatched_files'], 1)

    def test_leaf_symlink_refused(self):
        self.populate()
        outside = self.base / 'outside'
        outside.write_bytes(self.raw)
        path = self.root / 'FarmVillage/embeds/client.swf'
        path.unlink()
        path.symlink_to(outside)
        self.assertEqual(p.build_report(self.root)['resource_inputs']['refused_files'], 1)

    def test_parent_symlink_refused(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'data').mkdir()
        (outside / 'data/catalog.json').write_bytes(self.raw)
        (self.root / 'GodBarn').symlink_to(outside, target_is_directory=True)
        self.assertEqual(p.build_report(self.root)['resource_inputs']['refused_files'], 1)

    def test_non_regular_resource_is_refused_without_blocking(self):
        self.populate()
        path = self.root / 'FarmVillage/embeds/client.swf'
        path.unlink()
        os.mkfifo(path)
        self.assertEqual(p.build_report(self.root)['resource_inputs']['refused_files'], 1)

    def test_non_object_manifest_is_reported(self):
        (self.root / 'PrivateInputs.expected.json').write_text('[]')
        report = p.build_report(self.root)['resource_inputs']
        self.assertEqual(report['status'], 'manifest-unavailable')
        self.assertTrue(report['errors'])

    def test_source_symlink_refused(self):
        alias = self.base / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(p.RefusedInput):
            p.build_report(alias)

    def test_manifest_symlink_refused(self):
        path = self.root / 'PrivateInputs.expected.json'
        other = self.base / 'manifest.json'
        path.rename(other)
        path.symlink_to(other)
        result = p.build_report(self.root)['resource_inputs']
        self.assertEqual(result['status'], 'manifest-unavailable')
        self.assertTrue(result['errors'])

    def test_unsafe_manifest_paths_rejected(self):
        for name in ['../outside', '/absolute', 'FarmVillage/../outside', 'FarmVillage/a\\b', 'Other/place', 'FarmVillage/.git/config', 'GodBarn/.lan-server/password.hash', 'GodBarn/workspace/user.json', 'FarmVillage/saves/profile.json']:
            with self.subTest(name=name):
                self.resources = {name: dict(self.identity)}
                self.manifest()
                self.assertEqual(p.build_report(self.root)['resource_inputs']['status'], 'manifest-unavailable')

    def test_no_network_subprocess_or_writes_during_readiness(self):
        before = self.snapshot()
        with mock.patch.object(socket, 'socket', side_effect=AssertionError('network')), mock.patch.object(urllib.request, 'urlopen', side_effect=AssertionError('network')), mock.patch.object(p.subprocess, 'run', side_effect=AssertionError('process')):
            report = p.build_report(self.root)
        self.assertEqual(before, self.snapshot())
        self.assertFalse(any(report['actions_this_guide'].values()))

    def test_check_json_never_prompts(self):
        code, output = self.main_output(['--check', '--json'], mock.Mock(side_effect=AssertionError('prompt')))
        report = json.loads(output)
        self.assertEqual(code, 0)
        self.assertEqual(report['storage']['archive_bytes'], 19126111395)
        self.assertFalse(report['storage']['exact_peak_known'])

    def test_json_alone_never_prompts(self):
        code, output = self.main_output(['--json'], mock.Mock(side_effect=AssertionError('prompt')))
        self.assertEqual(code, 0)
        self.assertFalse(json.loads(output)['play_ready'])

    def test_server_explanation(self):
        _, output = self.main_output(['--audience', 'server', '--check'])
        self.assertIn('four original artwork archives', output)
        self.assertIn('do not install the full archive collection', output)
        self.assertIn('PLAY_ON_SERVER.md', output)

    def test_guide_read_only_after_explicit_choice(self):
        answers = iter(['2', '3'])
        with mock.patch.object(p.subprocess, 'run') as run:
            code, output = self.main_output(answers=lambda _: next(answers))
        run.assert_not_called()
        self.assertEqual(code, 0)
        self.assertIn('# Local Mac guide', output)

    def test_source_check_only_after_explicit_choice(self):
        checker = self.root / 'tools/check-source.py'
        checker.parent.mkdir()
        checker.write_text('# synthetic checker\n')
        answers = iter(['4', '3'])
        with mock.patch.object(p.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            _, output = self.main_output(answers=lambda _: next(answers))
        command = run.call_args.args[0]
        self.assertIn(str(checker), command)
        self.assertNotIn('--tests', command)
        self.assertIn('--root', command)
        self.assertIn('No installation was started', output)

    def test_guide_symlink_not_read(self):
        guide = self.root / 'docs/PLAY_ON_MAC.md'
        guide.unlink()
        outside = self.base / 'outside.md'
        outside.write_text('DO NOT DISPLAY')
        guide.symlink_to(outside)
        answers = iter(['2', '3'])
        _, output = self.main_output(answers=lambda _: next(answers))
        self.assertNotIn('DO NOT DISPLAY', output)
        self.assertIn('missing, linked or unreadable', output)

    def test_invalid_choice_and_close_have_no_side_effects(self):
        before = self.snapshot()
        answers = iter(['unknown', '3'])
        with mock.patch.object(p.subprocess, 'run') as run:
            _, output = self.main_output(answers=lambda _: next(answers))
        run.assert_not_called()
        self.assertEqual(before, self.snapshot())
        self.assertIn('No action was taken', output)

    def test_eof_is_clean_close(self):
        code, output = self.main_output(answers=mock.Mock(side_effect=EOFError))
        self.assertEqual(code, 0)
        self.assertIn('Installer closed', output)

    def test_launcher_guards_apple_shim_before_version_probe(self):
        text = (Path(__file__).resolve().parents[1] / 'START_MAC.command').read_text()
        self.assertLess(text.index('"$candidate" == /usr/bin/python3 || "$candidate" -ef /usr/bin/python3'), text.index('"$candidate" -I -S -B -c'))
        self.assertNotIn('xcode-select', text)
        self.assertNotIn('xcodebuild', text)

if __name__ == '__main__':
    unittest.main()
