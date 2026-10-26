"""Consent and final product routing using tiny owned folders and stub commands."""
import io, contextlib
from pathlib import Path
import tempfile, unittest
from unittest import mock
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import player_install as p

class PlayerInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fv-player-install-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.source = self.base / 'source'; self.source.mkdir()
        self.pack = self.base / 'chosen-pack'
    def test_no_consent_never_checks_tools_or_downloads(self):
        with mock.patch.object(p, 'preflight') as check, mock.patch.object(p, 'setup') as setup:
            with self.assertRaisesRegex(ValueError, 'consent'):
                p.install(self.source, 'mac', self.pack)
        check.assert_not_called(); setup.assert_not_called()
        self.assertFalse(self.pack.exists())
    def test_missing_prerequisite_stops_before_download(self):
        with mock.patch.object(p, 'preflight', side_effect=ValueError('missing tool')), mock.patch.object(p, 'setup') as setup:
            with self.assertRaisesRegex(ValueError, 'missing tool'):
                p.install(self.source, 'server', self.pack, consent=True)
        setup.assert_not_called(); self.assertFalse(self.pack.exists())
    def test_mac_opens_owned_app_with_selected_data(self):
        app = self.pack / 'macos-build/DerivedData/Build/Products/Release/FarmVillage.app'
        def compiler(command, pack, **kwargs):
            if '--resources' not in command:
                self.assertIn('prepare', command)
                self.assertIn(str(self.pack / 'player-data'), [str(x) for x in command])
                return
            self.assertEqual(pack, self.pack)
            self.assertEqual(kwargs['audience'], 'mac')
            app.mkdir(parents=True)
            (app / 'synthetic.txt').write_text('fixture app; no native executable')
        with mock.patch.object(p, 'preflight'), mock.patch.object(p, 'setup') as setup, mock.patch.object(p, 'check_pack') as check, mock.patch.object(p, 'run', side_effect=compiler), mock.patch.object(p.subprocess, 'run') as launch, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(p.install(self.source, 'mac', self.pack, consent=True), 0)
        setup.assert_called_once_with(self.pack, 'mac', self.source); check.assert_called_once_with(self.pack, verify_art=False)
        self.assertEqual(launch.call_args.args[0], ['/usr/bin/open', '-n', str(app), '--args', '--farmvillage-data-dir', str(self.pack / 'player-data')])
        self.assertFalse((self.source / 'FarmVillage/macOS/.build').exists())
        self.assertTrue((self.pack / 'PLAY_MAC.command').is_file())
        self.assertIn('player-data', (self.pack / 'PLAY_MAC.command').read_text())
    def test_server_enters_clean_installer_with_pack(self):
        with mock.patch.object(p, 'preflight'), mock.patch.object(p, 'setup'), mock.patch.object(p, 'check_pack'), mock.patch.object(p, 'run') as compiler, mock.patch.object(p.subprocess, 'run') as launch:
            self.assertEqual(p.install(self.source, 'server', self.pack, consent=True), 0)
        compiler.assert_not_called()
        self.assertEqual(launch.call_args.args[0][-3:], [str(self.source / 'tools/setup-wizard.py'), '--resources', str(self.pack)])
        self.assertFalse(self.pack.exists())
    def test_wrong_confirmation_never_installs(self):
        answers = iter(['1', str(self.pack), 'wrong', '3'])
        with mock.patch.object(p, 'install') as install, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(p.wizard(self.source, 'mac', lambda _: next(answers)), 0)
        install.assert_not_called(); self.assertFalse(self.pack.exists())
    def test_confirmed_target_enters_once(self):
        answers = iter(['1', str(self.pack), 'INSTALL ' + str(self.pack)])
        with mock.patch.object(p, 'install', return_value=0) as install, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(p.wizard(self.source, 'server', lambda _: next(answers)), 0)
        install.assert_called_once_with(self.source, 'server', self.pack, consent=True)
        self.assertFalse(self.pack.exists())
