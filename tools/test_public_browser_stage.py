"""Public browser staging with tiny fixtures; no network, native builds or servers."""
from __future__ import annotations
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TOOLS=Path(__file__).resolve().parent
sys.path.insert(0,str(TOOLS))
import resource_pipeline as pipeline


def load(name,filename):
    spec=importlib.util.spec_from_file_location(name,TOOLS/filename)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stager=load('public_browser_stager','prepare-browser-runtime.py')
wizard=load('public_browser_wizard','setup-wizard.py')


class PublicBrowserStageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='fv-browser-fixture-',dir='/private/tmp' if Path('/private/tmp').is_dir() else None)
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name).resolve()
        self.source=self.base/'source';self.source.mkdir()
        self.source_identity={'FarmVillage':'synthetic-source','GodBarn':'synthetic-barn'}
        self.put(self.source/'SOURCE_MANIFEST.json',json.dumps({'source':self.source_identity}).encode())
        for name in ('tools/check-source.py','tools/private-inputs.py','tools/prepare-browser-runtime.py',
                     'FarmVillage/macOS/Runtime/native_paths.py','FarmVillage/macOS/Runtime/server_host.py',
                     'FarmVillage/portable/Linux/server_runner.py','FarmVillage/portable/Linux/neighborhood_host.py',
                     'FarmVillage/portable/Linux/preloader_timing.py'):
            self.put(self.source/name,b'# reviewed synthetic source\n')
        self.root_patch=mock.patch.object(pipeline,'ROOT',self.source);self.root_patch.start();self.addCleanup(self.root_patch.stop)
        self.pack=pipeline.own_target(self.base/'public-pack',self.source)
        self.pin='f'*64
        for name in ('Runtime/server.py','Runtime/runtime_compatibility.py','Runtime/GodBarn/__init__.py',
                     'Runtime/ruffle_runtime/0.7.1-farmvillage-gc1/ruffle.js'):
            self.put(self.pack/name,b'# reviewed synthetic runtime\n')
        self.put(self.pack/'Runtime/PREPARED_RUNTIME.json',json.dumps({'schema':1,'runtime_manifest_sha256':self.pin}).encode())
        self.put(self.pack/'Runtime/PUBLIC_INSTALL.json',b'{"source-pack-only":true}\n')
        self.put(self.pack/'assets/Environment/fixture.bin',b'original fixture')
        self.put(self.pack/'assets/xpromoSupport/fixture.bin',b'original fixture')
        self.put(self.pack/'assets-manifest.jsonl',b'')
        pipeline.seal(self.pack,'server')
        self.output=self.base/'browser-release'
        self.commands=[]
    def put(self,path,payload):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(payload);return path
    def snapshot(self,root):
        return {path.relative_to(root).as_posix():path.read_bytes() for path in root.rglob('*') if path.is_file()}
    def command(self,command,**kwargs):
        self.commands.append(command)
        return subprocess.CompletedProcess(command,0)
    def prepare(self,output=None):
        with mock.patch.object(stager.subprocess,'run',side_effect=self.command):
            return stager.prepare(self.source,output or self.output,self.pack)
    def test_verified_pack_stages_exact_runtime_hosts_and_manifest_without_source_mutation(self):
        source_before=self.snapshot(self.source);pack_before=self.snapshot(self.pack)
        result=self.prepare()
        self.assertFalse(result['started']);self.assertFalse(result['downloaded']);self.assertFalse(result['savesRead'])
        self.assertEqual(self.snapshot(self.source),source_before);self.assertEqual(self.snapshot(self.pack),pack_before)
        self.assertEqual((self.output/'Runtime/server.py').read_bytes(),(self.pack/'Runtime/server.py').read_bytes())
        self.assertFalse((self.output/'Runtime/PUBLIC_INSTALL.json').exists())
        self.assertTrue((self.pack/'Runtime/PUBLIC_INSTALL.json').is_file())
        manifest=wizard.verify_payload(self.output)
        self.assertEqual(manifest['source'],self.source_identity)
        self.assertEqual(result['files'],len(manifest['files']))
        self.assertEqual(set(manifest['files']),set(self.snapshot(self.output))-{'PRIVATE_RELEASE_MANIFEST.json'})
        self.assertFalse((self.output/'assets').exists())
        self.assertFalse(any('private-inputs.py' in ' '.join(command) for command in self.commands))
    def test_staged_dynamic_player_pin_is_forwarded_to_runtime_verification(self):
        self.prepare()
        commands=[command for command in self.commands if '--prepared-runtime-pin-sha256' in command]
        self.assertEqual(len(commands),1)
        command=commands[0]
        self.assertEqual(command[1:3],['-I','-B'])
        self.assertEqual(command[command.index('--payload')+1],str(self.output/'Runtime'))
        self.assertEqual(command[command.index('--prepared-runtime-pin-sha256')+1],self.pin)
        self.assertEqual(command[3],str(self.output/'Runtime/runtime_compatibility.py'))
    def test_runtime_verification_failure_rolls_back_only_new_stage(self):
        before=self.snapshot(self.pack)
        def reject(command,**kwargs):
            if '--prepared-runtime-pin-sha256' in command:raise subprocess.CalledProcessError(1,command)
            return self.command(command,**kwargs)
        with mock.patch.object(stager.subprocess,'run',side_effect=reject),self.assertRaises(subprocess.CalledProcessError):
            stager.prepare(self.source,self.output,self.pack)
        self.assertFalse(self.output.exists());self.assertEqual(self.snapshot(self.pack),before)
    def test_unlisted_linked_pack_inputs_are_rejected_before_stage_creation(self):
        outside=self.put(self.base/'outside-fixture',b'preserved synthetic fixture')
        (self.pack/'Runtime/linked.py').symlink_to(outside)
        with mock.patch.object(stager.subprocess,'run',side_effect=self.command),self.assertRaises(ValueError):
            stager.prepare(self.source,self.output,self.pack)
        self.assertFalse(self.output.exists());self.assertEqual(outside.read_bytes(),b'preserved synthetic fixture')
    def test_outputs_inside_pack_inputs_are_rejected_before_commands_or_copy(self):
        for output in (self.pack/'Runtime/new-release',self.pack/'assets/new-release',self.pack/'work/new-release'):
            with self.subTest(output=output),mock.patch.object(stager.subprocess,'run',side_effect=AssertionError('unsafe output spawned a command')),self.assertRaises(ValueError):
                stager.prepare(self.source,output,self.pack)
            self.assertFalse(output.exists())
    def test_cli_routes_source_output_and_public_resources_to_prepare(self):
        argv=['prepare-browser-runtime.py','--source-root',str(self.source),'--output',str(self.output),'--resources',str(self.pack)]
        with mock.patch.object(sys,'argv',argv),mock.patch.object(stager,'prepare',return_value={'status':'fixture'}) as prepare,contextlib.redirect_stdout(io.StringIO()):
            stager.main()
        prepare.assert_called_once_with(self.source,self.output,self.pack)
    def choose_public_bundle(self):
        def stage(command,**kwargs):
            self.commands.append(command)
            output=Path(command[command.index('--output')+1])
            return self.prepare(output)
        with mock.patch.object(wizard,'PUBLIC_RESOURCES',self.pack),mock.patch.object(wizard,'__file__',str(self.source/'tools/setup-wizard.py')),mock.patch.object(wizard,'run',side_effect=stage),mock.patch.object(wizard,'ask',side_effect=AssertionError('public bundle selection asked for owner inputs')):
            return wizard.choose_bundle()
    def test_public_bundle_defaults_to_pack_browser_release_and_uses_public_resources(self):
        bundle,temporary=self.choose_public_bundle()
        self.assertEqual(bundle,self.pack/'browser-release');self.assertIsNone(temporary)
        self.assertTrue((bundle/'PRIVATE_RELEASE_MANIFEST.json').is_file())
        routed=[command for command in self.commands if '--resources' in command]
        self.assertEqual(len(routed),1)
        command=routed[0]
        self.assertEqual(command[:3],[wizard.sys.executable,'-I','-B'])
        self.assertEqual(command[3],str(self.source/'tools/prepare-browser-runtime.py'))
        self.assertEqual(command[command.index('--resources')+1],str(self.pack))
        self.assertEqual(pipeline.check_pack(self.pack)['status'],'complete')
    def test_existing_public_browser_release_is_verified_and_reused_without_rebuilding(self):
        bundle,_=self.choose_public_bundle()
        with mock.patch.object(wizard,'PUBLIC_RESOURCES',self.pack),mock.patch.object(wizard,'run',side_effect=AssertionError('existing verified stage rebuilt')):
            self.assertEqual(wizard.choose_bundle(),(bundle,None))
        (bundle/'Runtime/server.py').write_bytes(b'changed')
        with mock.patch.object(wizard,'PUBLIC_RESOURCES',self.pack),mock.patch.object(wizard,'run',side_effect=AssertionError('corrupt stage launched tool')),self.assertRaises(wizard.SetupError):
            wizard.choose_bundle()
    def test_server_wizard_defaults_to_public_pack_assets_before_any_install_write(self):
        bundle,_=self.choose_public_bundle();home=self.base/'fixture-home';home.mkdir();captured=[]
        class ReachedAssets(Exception):pass
        def ask(prompt,default=None):
            if prompt.startswith('Extracted assets folder'):
                captured.append(default);raise ReachedAssets()
            return str(default)
        with mock.patch.object(wizard,'PUBLIC_RESOURCES',self.pack),mock.patch.object(wizard,'choose_bundle',return_value=(bundle,None)),mock.patch.object(wizard,'preflight'),mock.patch.object(wizard,'verify_loaded_service'),mock.patch.object(wizard,'choose_network',return_value=('127.0.0.1',5501,'http://127.0.0.1:5501')),mock.patch.object(wizard.Path,'home',return_value=home),mock.patch.object(wizard,'service_path',return_value=home/'.config/systemd/user/farmvillage.service'),mock.patch.object(wizard.os,'umask'),mock.patch.object(wizard,'ask',side_effect=ask),mock.patch.object(wizard,'run',side_effect=AssertionError('installer spawned a command before asset selection')),contextlib.redirect_stdout(io.StringIO()),self.assertRaises(ReachedAssets):
            wizard.wizard()
        self.assertEqual(captured,[self.pack/'assets'])
        self.assertEqual(list(home.iterdir()),[])


if __name__=='__main__':unittest.main()
