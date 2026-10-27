"""Synthetic wipe/scope/completion tests. No Ubuntu, network, pip or real farms."""
import contextlib
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec=importlib.util.spec_from_file_location('wizard',Path(__file__).with_name('setup-wizard.py'))
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)

class CleanInstallTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix='fv-wizard-test-');self.addCleanup(self.temp.cleanup)
  self.base=Path(self.temp.name).resolve();self.home=self.base/'home';self.home.mkdir();self.target=self.home/'farmvillage-server';self.bundle=self.base/'bundle';self.bundle.mkdir();self.unit=self.home/'.config/systemd/user/farmvillage.service'
  self.manifest={'schema':1,'source':{'FarmVillage':'synthetic16','GodBarn':'synthetic'},'files':{}}
  for name in ['Runtime/server.py','Runtime/requirements.txt','BackendHost/native_paths.py','hosting/server_runner.py']:
   raw=b'# synthetic fixture\n';self.put(self.bundle/name,raw);self.manifest['files'][name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
  self.put(self.bundle/'PRIVATE_RELEASE_MANIFEST.json',json.dumps(self.manifest).encode())
  self.art=self.base/'art';self.put(self.art/'Environment/field.swf',b'synthetic-art');self.put(self.art/'xpromoSupport/placeholder.swf',b'synthetic-art')
 def put(self,p,raw=b'synthetic'):
  p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);return p
 def legacy(self):
  self.put(self.target/'hosting/server_runner.py',b'_farmvillage_lan_authenticated\ndef data_ownership(\ndef register_lan_access(');self.put(self.target/'release/farmvillage-portable-preparation-123456789abc/Runtime/server.py');self.put(self.target/'data/saves/old.json',b'old-farm');self.put(self.target/'data/god-barn/history.json',b'old-history');self.put(self.target/'data/.lan-server/password.hash',b'old-password')
  self.put(self.unit,(w.LEGACY_MARKER+'\nExecStart=/bin/bash '+str(self.target)+'/hosting/start-server.sh\n').encode())
 def stage(self):
  p=Path(tempfile.mkdtemp(prefix='.farmvillage-stage-',dir=self.home));w.copy_clean_payload(self.bundle,p,self.art,self.manifest);return p
 def config(self):return {'bind':'127.0.0.1','port':5501,'origin':'http://127.0.0.1:5501','service':w.UNIT}
 def test_new_empty_and_existing_managed_are_identified(self):
  self.assertEqual(w.classify_target(self.target,self.home,self.bundle,self.unit),'new');self.target.mkdir();self.assertEqual(w.classify_target(self.target,self.home,self.bundle,self.unit),'new')
  self.put(self.target/w.MARKER,json.dumps({'schema':1,'product':w.PRODUCT,'target':str(self.target)}).encode());self.assertEqual(w.classify_target(self.target,self.home,self.bundle,self.unit),'managed')
 def test_known_legacy_requires_exact_service_identity(self):
  self.legacy();self.assertEqual(w.classify_target(self.target,self.home,self.bundle,self.unit),'legacy-managed');self.unit.write_text('ExecStart=/bin/other\n')
  with self.assertRaises(w.SetupError):w.classify_target(self.target,self.home,self.bundle,self.unit)
 def test_refuse_system_home_source_unrelated_and_symlink(self):
  for target in [Path('/'),Path('/etc/farmville-test'),self.home,self.home/'Documents']:
   with self.subTest(target=target),self.assertRaises(w.SetupError):w.classify_target(target,self.home,self.bundle,self.unit)
  self.target.mkdir();self.put(self.target/'.git/config')
  with self.assertRaises(w.SetupError):w.classify_target(self.target,self.home,self.bundle,self.unit)
  link=self.home/'farmville-linked';link.symlink_to(self.target,target_is_directory=True)
  with self.assertRaises(w.SetupError):w.classify_target(link,self.home,self.bundle,self.unit)
 def test_refuse_root_or_system_home(self):
  for home in [Path('/'),Path('/root'),Path('/var/lib/svc'),Path('/etc/x/y')]:
   with self.subTest(home=home),self.assertRaises(w.SetupError):w.classify_target(home/'farmvillage-server',home,self.bundle,self.unit)
 def test_unknown_existing_directory_is_never_wiped(self):
  self.put(self.target/'keep.txt',b'unrelated');stage=self.stage()
  with self.assertRaises(w.SetupError):w.publish_clean_stage(stage,self.target,self.home,self.bundle,self.unit,self.config(),'WIPE '+str(self.target))
  self.assertEqual((self.target/'keep.txt').read_bytes(),b'unrelated')
 def test_wrong_confirmation_preserves_every_old_byte(self):
  self.legacy();stage=self.stage()
  with self.assertRaises(w.SetupError):w.publish_clean_stage(stage,self.target,self.home,self.bundle,self.unit,self.config(),'yes')
  self.assertEqual((self.target/'data/saves/old.json').read_bytes(),b'old-farm')
 def test_full_managed_wipe_removes_all_old_state(self):
  self.legacy();stage=self.stage();w.publish_clean_stage(stage,self.target,self.home,self.bundle,self.unit,self.config(),'WIPE '+str(self.target))
  self.assertFalse((self.target/'data/saves').exists());self.assertFalse((self.target/'data/god-barn').exists());self.assertFalse((self.target/'data/.lan-server').exists());self.assertTrue((self.target/'data/assets/Environment/field.swf').is_file());self.assertTrue(json.loads((self.target/w.MARKER).read_text())['cleanStart'])
 def test_assets_inside_wipe_target_are_staged_first(self):
  self.legacy();inside=self.target/'data/assets';self.put(inside/'Environment/field.swf',b'art-to-keep');self.put(inside/'xpromoSupport/logo.swf',b'art')
  self.assertGreater(w.validate_assets(inside),0);stage=Path(tempfile.mkdtemp(prefix='.farmvillage-stage-',dir=self.home));w.copy_clean_payload(self.bundle,stage,inside,self.manifest);w.publish_clean_stage(stage,self.target,self.home,self.bundle,self.unit,self.config(),'WIPE '+str(self.target))
  self.assertEqual((self.target/'data/assets/Environment/field.swf').read_bytes(),b'art-to-keep');self.assertFalse((self.target/'data/saves').exists())
 def test_active_data_owner_blocks_deletion(self):
  self.legacy();lock=self.put(self.target/'data/.lan-server/owner.lock');stage=self.stage()
  with lock.open('r+') as stream:
   fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
   with self.assertRaises(w.SetupError):w.publish_clean_stage(stage,self.target,self.home,self.bundle,self.unit,self.config(),'WIPE '+str(self.target))
  self.assertTrue((self.target/'data/saves/old.json').exists())
 def test_unowned_stage_cannot_replace_target(self):
  self.legacy();wrong=self.base/'unrelated-stage';wrong.mkdir()
  with self.assertRaises(w.SetupError):w.publish_clean_stage(wrong,self.target,self.home,self.bundle,self.unit,self.config(),'WIPE '+str(self.target))
  self.assertTrue((self.target/'data/saves/old.json').exists())
 def test_assets_refuse_state_and_links(self):
  self.put(self.art/'saves/old.json')
  with self.assertRaises(w.SetupError):w.validate_assets(self.art)
  (self.art/'saves/old.json').unlink();(self.art/'saves').rmdir();(self.art/'Environment/link.swf').symlink_to(self.art/'Environment/field.swf')
  with self.assertRaises(w.SetupError):w.validate_assets(self.art)
 def test_manifest_refuses_old_state_and_corruption(self):
  self.manifest['files']['Runtime/saves/old.json']={'bytes':1,'sha256':'0'*64};self.put(self.bundle/'PRIVATE_RELEASE_MANIFEST.json',json.dumps(self.manifest).encode())
  with self.assertRaises(w.SetupError):w.verify_payload(self.bundle)
  del self.manifest['files']['Runtime/saves/old.json'];self.put(self.bundle/'PRIVATE_RELEASE_MANIFEST.json',json.dumps(self.manifest).encode());self.put(self.bundle/'Runtime/server.py',b'changed')
  with self.assertRaises(w.SetupError):w.verify_payload(self.bundle)
 def test_network_private_only(self):
  self.assertEqual(w.validate_network('127.0.0.1',5501),'http://127.0.0.1:5501')
  for address in ['0.0.0.0','8.8.8.8','not-an-address']:
   with self.assertRaises(w.SetupError):w.validate_network(address,5501)
 def test_service_refuses_shell_confusion(self):
  self.legacy();self.unit.write_text(w.LEGACY_MARKER+'\nExecStart=/bin/bash -c "echo '+str(self.target)+'/hosting/start-server.sh"\n');self.assertFalse(w.service_matches(self.unit,self.target))
 def test_guided_completion_has_fresh_state_without_real_network_or_service(self):
  self.legacy();answers=iter([str(self.target),'127.0.0.1','5501',str(self.art),'WIPE '+str(self.target),'n']);commands=[]
  class Builder:
   def __init__(builder,**kwargs):pass
   def create(builder,path):self.put(Path(path)/'bin/python',b'fake-venv')
  def fake_run(command,**kwargs):
   commands.append(command)
   if 'venv' in command:self.put(Path(command[-1])/'bin/python',b'fresh-environment')
   if '--init-only' in command:self.put(self.target/'data/.lan-server/password.hash',b'fresh-hash');self.put(self.target/'data/.lan-server/session.secret',b'fresh-secret')
  with mock.patch.object(w,'preflight'),mock.patch.object(w,'verify_loaded_service'),mock.patch.object(w,'choose_bundle',return_value=(self.bundle,None)),mock.patch.object(w.Path,'home',return_value=self.home),mock.patch.dict(os.environ,{'XDG_CONFIG_HOME':str(self.home/'.config')}),mock.patch.object(w,'ask',side_effect=lambda *a,**k:next(answers)),mock.patch.object(w,'run',side_effect=fake_run),mock.patch('venv.EnvBuilder',Builder),mock.patch.object(w,'install_user_service') as service,mock.patch.object(w,'check_origin',return_value=True),mock.patch.object(w.webbrowser,'open') as browser,mock.patch.object(w.socket.socket,'connect_ex',return_value=111),contextlib.redirect_stdout(io.StringIO()) as output:
   result=w.wizard()
  self.assertEqual(result,self.target);self.assertEqual((self.target/'release/.venv/bin/python').read_bytes(),b'fresh-environment');self.assertEqual((self.target/'data/.lan-server/password.hash').read_bytes(),b'fresh-hash');self.assertFalse((self.target/'data/saves').exists());self.assertFalse((self.target/'data/god-barn').exists());service.assert_called_once_with(self.target,self.unit);browser.assert_called_once_with('http://127.0.0.1:5501/new.html');self.assertIn('Step 8 of 8',output.getvalue());self.assertNotIn('old-password',output.getvalue());self.assertTrue(any('--init-only' in c for c in commands))

 def test_dotdot_target_escape_is_refused(self):
  escaped=self.home/'foo/../../outside/farmville-test'
  with self.assertRaises(w.SetupError):w.classify_target(escaped,self.home,self.bundle,self.unit)
  self.assertFalse((self.base/'outside').exists())
 def test_loaded_unrelated_service_fragment_is_refused(self):
  result=type('Result',(),{'stdout':str(self.base/'unrelated.service')+'\n','returncode':0})()
  with mock.patch.object(w.subprocess,'run',return_value=result),self.assertRaises(w.SetupError):w.verify_loaded_service(self.unit)

 def test_python_pip_environment_ignores_external_targets_and_config(self):
  with mock.patch.dict(os.environ,{'PIP_TARGET':'/outside','PIP_PREFIX':'/outside','PIP_CONFIG_FILE':'/outside/pip.conf','PYTHONPATH':'/outside','HTTPS_PROXY':'http://proxy.invalid'}):
   env=w.private_python_environment()
  self.assertNotIn('PIP_TARGET',env);self.assertNotIn('PIP_PREFIX',env);self.assertNotIn('PYTHONPATH',env);self.assertEqual(env['PIP_CONFIG_FILE'],os.devnull);self.assertNotIn('HTTPS_PROXY',env);self.assertEqual(env['NETRC'],os.devnull)

 def test_detected_network_choices_offer_private_access_and_reject_public(self):
  result=type('Result',(),{'stdout':'192.168.50.22 0.0.0.0 8.8.8.8 100.88.0.5 ::1','returncode':0})()
  with mock.patch.object(w.shutil,'which',return_value='/bin/hostname'),mock.patch.object(w.subprocess,'run',return_value=result):
   self.assertEqual(w.network_choices(),['192.168.50.22','100.88.0.5','127.0.0.1'])
   with mock.patch.object(w,'ask',side_effect=['1','5501']),contextlib.redirect_stdout(io.StringIO()) as output:
    bind,port,origin=w.choose_network()
   self.assertEqual((bind,port,origin),('192.168.50.22',5501,'http://192.168.50.22:5501'));self.assertIn('Open from another computer',output.getvalue());self.assertIn('Only this Ubuntu computer',output.getvalue());self.assertIn('/new.html',output.getvalue())
   for address in ['0.0.0.0','8.8.8.8','not-an-address']:
    with mock.patch.object(w,'ask',side_effect=[address,'5501']),contextlib.redirect_stdout(io.StringIO()),self.assertRaises(w.SetupError):w.choose_network()

 def source_clone(self):
  root=self.base/'community-source'
  self.put(root/'FarmVillage/server.py',b'# synthetic source\n')
  self.put(root/'tools/setup-wizard.py',b'# synthetic wizard location\n')
  self.put(root/'tools/private-inputs.py',b'# synthetic checker location\n')
  self.put(root/'tools/prepare-browser-runtime.py',b'# synthetic staging location\n')
  return root

 def test_incomplete_source_stops_before_prompts_import_staging_or_temp_creation(self):
  root=self.source_clone();result=type('Result',(),{'returncode':1})()
  with mock.patch.object(w,'__file__',str(root/'tools/setup-wizard.py')),mock.patch.object(w.subprocess,'run',return_value=result) as check,mock.patch.object(w,'ask') as ask,mock.patch.object(w,'run') as stage,mock.patch.object(w.tempfile,'TemporaryDirectory') as temporary:
   with self.assertRaisesRegex(w.SetupError,'No prepared resource pack was selected') as failure:w.choose_bundle()
  self.assertIn('PLAY_ON_SERVER.md',str(failure.exception));self.assertIn('no files were downloaded',str(failure.exception));self.assertIn('bash START_HERE.sh',str(failure.exception))
  check.assert_called_once_with([w.sys.executable,'-I','-S','-B',str(root/'tools/private-inputs.py'),'check'],stdout=w.subprocess.DEVNULL,stderr=w.subprocess.DEVNULL)
  ask.assert_not_called();stage.assert_not_called();temporary.assert_not_called()

 def test_matching_source_stages_existing_resources_without_import_or_prompts(self):
  root=self.source_clone();result=type('Result',(),{'returncode':0})()
  def stage_existing(command):
   self.assertEqual(command[:3],[w.sys.executable,'-B',str(root/'tools/prepare-browser-runtime.py')]);self.assertEqual(command[3],'--output')
   destination=Path(command[4]);self.put(destination/'PRIVATE_RELEASE_MANIFEST.json',b'{"schema":1}')
  with mock.patch.object(w,'__file__',str(root/'tools/setup-wizard.py')),mock.patch.object(w.subprocess,'run',return_value=result) as check,mock.patch.object(w,'ask') as ask,mock.patch.object(w,'run',side_effect=stage_existing) as stage:
   output,temporary=w.choose_bundle()
  try:
   self.assertEqual(output.name,'payload');self.assertTrue((output/'PRIVATE_RELEASE_MANIFEST.json').is_file());self.assertIsNotNone(temporary)
   check.assert_called_once_with([w.sys.executable,'-I','-S','-B',str(root/'tools/private-inputs.py'),'check'],stdout=w.subprocess.DEVNULL,stderr=w.subprocess.DEVNULL)
   ask.assert_not_called();stage.assert_called_once();self.assertNotIn('import',stage.call_args.args[0])
  finally:temporary.cleanup()
  self.assertFalse(output.parent.exists())

 def test_complete_prepared_bundle_keeps_direct_path_without_checks_or_staging(self):
  with mock.patch.object(w,'__file__',str(self.bundle/'setup-wizard.py')),mock.patch.object(w.subprocess,'run') as check,mock.patch.object(w,'ask') as ask,mock.patch.object(w,'run') as stage:
   self.assertEqual(w.choose_bundle(),(self.bundle,None))
  check.assert_not_called();ask.assert_not_called();stage.assert_not_called()

if __name__=='__main__':unittest.main()
