"""Resource reconstruction contracts use only synthetic original-file fixtures."""
import hashlib
import importlib.util
import contextlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest
from unittest import mock
import zlib
ROOT = Path(__file__).resolve().parents[1]
def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
bootstrap = load('resource_bootstrap', 'bootstrap_resources.py')
verifier = load('verify_reconstructed_resources', 'verify_resources.py')
REAL_HELPERS_RECOVER = bootstrap.prepare_helpers.recover
REAL_PROGRESSION_RECOVER = bootstrap.prepare_progression.recover

def png():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB',1,1,8,6,0,0,0)) + chunk(b'IDAT',zlib.compress(b'\0\x10\x20\x30\xff')) + chunk(b'IEND',b'')

class ResourceBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.game, self.output, self.policy = (self.base / name for name in ('original','generated','policy'))
        (self.policy / 'templates').mkdir(parents=True)
        (self.policy / 'templates/play.html').write_text('"fv_fixture": 1')
        (self.policy / 'heritage_pricing.py').write_text('ENABLED=True\ndef plan(records,served=None):\n    assert served=={"fv_fixture":1}\n    return {},{}\ndef _mutate(record,patch):\n    raise AssertionError("no mutation")\ndef overlay_digest():\n    return "fixture-policy"\n')
        self.records = [{'name':'fixturecrop','code':'FC','type':'seed','buyable':'true','cost':'10','growTime':'1','coinYield':'20','image':{'name':'icon','url':'assets/crops/fixture.png'}}]
        raster=png()
        self.asset_relative='crops/'+hashlib.md5(raster).hexdigest()+'.png'
        asset=self.game/'assets'/self.asset_relative
        asset.parent.mkdir(parents=True)
        asset.write_bytes(raster)
        for name in bootstrap.REQUIRED:
            path=self.game/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(b'original fixture')
        self.put_amf('xml/gz/v855038/items_opt.amf',{'settings':{'items':{'item':self.records}}})
        self.put_amf('assethash/v9/assethash.master.amf.gz',{'crops':{'fixture.png':Path(self.asset_relative).stem}})
        self.put_amf('xml/gz/v855098/assethash.min.amf.gz',{})
        (self.game/'xml/gz/v855098/gameSettings.xml.gz').write_bytes(zlib.compress(b'<settings><levels><level num="1" requiredXP="0"/></levels></settings>'))
        (self.game/'xml/gz/v855098/gameSettingsCMS.xml.gz').write_bytes(zlib.compress(b'<settings><farming><farmingEntry key="inGameDaySeconds" value="82800"/></farming></settings>'))
        decoder=types.SimpleNamespace(AMF3=3,get_decoder=lambda _,data:types.SimpleNamespace(readElement=lambda:json.loads(data)))
        self.addCleanup(mock.patch.stopall)
        mock.patch.dict(sys.modules,{'pyamf':decoder}).start()
        mock.patch.object(bootstrap.recover_labels,'recover',return_value={'recoveryVersion':2,'source':{'file':'xml/gz/v855098/en_US.swf'},'items':{'fixturecrop':{'displayName':'Fixture crop'}}}).start()
        mock.patch.object(bootstrap.prepare_helpers,'recover',return_value={'schemaVersion':1,'source':{},'collections':[],'quests':[]}).start()
        mock.patch.object(bootstrap.prepare_progression,'recover',return_value={'schemaVersion':1,'source':{},'ribbons':[],'masteryItems':[]}).start()
    def put_amf(self,name,value):
        (self.game/name).write_bytes(zlib.compress(json.dumps(value).encode()))
    def generate(self,**kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return bootstrap.generate(self.game,self.output,policy_root=self.policy,include_skin=False,**kwargs)
    def verify(self,*args,**kwargs):
        kwargs.setdefault('expected_records',1)
        return verifier.verify(*args,**kwargs)
    def verification_source(self):
        source=self.base/'source-ui'
        (source/'static').mkdir(parents=True,exist_ok=True)
        return source
    def test_fresh_original_files_generate_resources_without_saves_or_cached_catalogue(self):
        result=self.generate()
        self.assertFalse((self.game/'LocalData').exists())
        self.assertFalse((self.game/'cache').exists())
        self.assertFalse((self.output/'data/bootstrap-save.json').exists())
        self.assertFalse(result['containsPlayerState'])
        self.assertEqual((result['catalogRecords'],result['exactArtworkRecords'],result['historicalPrizeShelves']),(1,1,0))
        catalog=json.loads((self.output/'data/catalog.json').read_text())
        self.assertEqual(catalog[0]['displayName'],'Fixture crop')
        self.assertEqual(catalog[0]['archive']['raw']['cost'],'10')
        self.assertEqual(json.loads((self.output/'data/asset-map.json').read_text()),{catalog[0]['image'].lstrip('/'):self.asset_relative})
        for path in self.output.rglob('*.json'):
            text=path.read_text()
            self.assertNotIn(str(self.game),text)
            self.assertNotIn(str(self.temp.name),text)
            self.assertNotIn('"originalPath"',text)
        self.assertEqual(json.loads((self.output/'data/untabbed.json').read_text())['items'],{})
    def test_verifier_compares_original_rows_and_normalized_metadata(self):
        self.generate()
        result=self.verify(self.output,game_root=self.game,companion_source=self.verification_source())
        self.assertEqual(result['originalRowsCompared'],1)
        self.assertEqual(result['uiReferences'],1)
        self.assertFalse(result['gameplayAcceptance'])
        with self.assertRaisesRegex(ValueError,'record count'):
            self.verify(self.output,companion_source=self.verification_source(),expected_records=111206)
    def test_semantic_validation_catches_resealed_wrong_catalogue_identity(self):
        self.generate()
        path=self.output/'data/catalog.json'
        catalog=json.loads(path.read_text());catalog[0]['code']='WRONG';path.write_text(json.dumps(catalog))
        receipt_path=self.output/'RESOURCE_BUILD.json';receipt=json.loads(receipt_path.read_text())
        receipt['files']['data/catalog.json']={'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        receipt_path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'identity/order'):
            self.verify(self.output,game_root=self.game,companion_source=self.verification_source())
    def test_semantic_validation_rejects_resealed_changed_original_price(self):
        self.generate()
        path=self.output/'data/catalog.json'
        catalog=json.loads(path.read_text());catalog[0]['cost']=0;path.write_text(json.dumps(catalog))
        receipt_path=self.output/'RESOURCE_BUILD.json';receipt=json.loads(receipt_path.read_text())
        receipt['files']['data/catalog.json']={'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        receipt_path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'numeric fact changed.*cost'):
            self.verify(self.output,game_root=self.game,companion_source=self.verification_source())
    def test_missing_literal_ui_asset_is_an_explicit_failure(self):
        self.generate();source=self.verification_source();(source/'static/app.js').write_text("img('absent')")
        with self.assertRaisesRegex(ValueError,'absent.png'):
            self.verify(self.output,companion_source=source)
    def test_metadata_only_keeps_missing_authored_artwork_unqualified(self):
        self.generate();source=self.verification_source();(source/'static/app.js').write_text("img('not-extracted')")
        result=self.verify(self.output,companion_source=source,metadata_only=True)
        self.assertFalse(result['uiReadiness']);self.assertFalse(result['gameplayAcceptance'])
    def test_owned_http_readiness_checks_return_generated_bytes(self):
        self.generate();source=self.verification_source();(source/'static/app.js').write_text('// Neutral unavailable marker')
        try:
            result=self.verify(self.output,companion_source=source,http=True)
        except PermissionError:
            self.skipTest('This sandbox disallows binding a loopback HTTP socket')
        self.assertEqual(result['http200'],2);self.assertFalse(result['gameplayAcceptance'])
    def test_finder_metadata_is_not_part_of_resource_identity(self):
        prepare=bootstrap.prepare_assets.prepare
        def seed(*args,**kwargs):
            result=prepare(*args,**kwargs);(Path(args[1])/'.DS_Store').write_bytes(b'folder metadata');return result
        with mock.patch.object(bootstrap.prepare_assets,'prepare',side_effect=seed):self.generate()
        self.assertNotIn('.DS_Store',json.loads((self.output/'RESOURCE_BUILD.json').read_text())['files'])
        (self.output/'.DS_Store').write_bytes(b'changed metadata')
        self.assertEqual(self.verify(self.output,game_root=self.game,companion_source=self.verification_source())['originalRowsCompared'],1)
    def test_ui_reference_scan_does_not_treat_currency_names_as_image_files(self):
        source=self.verification_source()
        (source/'static/app.js').write_text("const nav=[['bank','coin','The bank']];if(['coins','gold','farmcoins'].includes(key)){};balanceCard('gold','Coins','coin',1);[['mastery','Mastery stars','xp-star']].map(([value,label,icon])=>img(icon));")
        refs=verifier.referenced_ui(source)
        self.assertIn('static/assets/ui/coin.png',refs);self.assertIn('static/assets/ui/xp-star.png',refs)
        self.assertNotIn('static/assets/ui/gold.png',refs);self.assertNotIn('static/assets/ui/farmcoins.png',refs)
    def test_existing_destination_is_preserved(self):
        self.output.mkdir();marker=self.output/'keep';marker.write_text('existing')
        with self.assertRaisesRegex(ValueError,'existing files are preserved'):self.generate()
        self.assertEqual(marker.read_text(),'existing')
    def test_missing_original_file_fails_before_creating_output(self):
        (self.game/'xml/gz/v855098/en_US.swf').unlink()
        with self.assertRaisesRegex(ValueError,'en_US.swf'):self.generate()
        self.assertFalse(self.output.exists());self.assertEqual(list(self.base.glob('.god-barn-resources-*')),[])
    def test_failure_rolls_back_staging_without_touching_original_inputs(self):
        before={p.relative_to(self.game):p.read_bytes() for p in self.game.rglob('*') if p.is_file()}
        with mock.patch.object(bootstrap.prepare_helpers,'recover',side_effect=ValueError('bad original XML')):
            with self.assertRaisesRegex(ValueError,'bad original XML'):self.generate()
        self.assertFalse(self.output.exists());self.assertEqual(list(self.base.glob('.god-barn-resources-*')),[])
        self.assertEqual(before,{p.relative_to(self.game):p.read_bytes() for p in self.game.rglob('*') if p.is_file()})
    def test_output_cannot_be_inside_source_or_linked(self):
        for target in (self.game/'generated',self.policy/'generated'):
            with self.subTest(target=target),self.assertRaisesRegex(ValueError,'separate'):
                bootstrap.generate(self.game,target,policy_root=self.policy,include_skin=False)
        linked=self.base/'linked';linked.symlink_to(self.game,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'Linked'):
            bootstrap.generate(self.game,linked/'generated',policy_root=self.policy,include_skin=False)
    def test_legacy_skin_module_does_not_access_files_at_import(self):
        with mock.patch.object(Path,'read_bytes',side_effect=AssertionError('import reads resources')):
            module=load('skin_no_io','prepare_skin.py')
        self.assertTrue(callable(module.prepare))
    def test_repeated_resource_builds_have_identical_content(self):
        self.generate();second=self.base/'second'
        with contextlib.redirect_stdout(io.StringIO()):
            bootstrap.generate(self.game,second,policy_root=self.policy,include_skin=False)
        self.assertEqual({p.relative_to(self.output):p.read_bytes() for p in self.output.rglob('*') if p.is_file()},{p.relative_to(second):p.read_bytes() for p in second.rglob('*') if p.is_file()})
    def test_verifier_defaults_to_complete_public_catalogue(self):
        self.generate()
        with self.assertRaisesRegex(ValueError,'record count'):
            verifier.verify(self.output,companion_source=self.verification_source())
    def test_required_metadata_cannot_be_removed_and_resealed(self):
        self.generate()
        target='data/helpers.json'
        (self.output/target).unlink()
        receipt_path=self.output/'RESOURCE_BUILD.json'
        receipt=json.loads(receipt_path.read_text());del receipt['files'][target]
        receipt_path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'helpers.json'):
            self.verify(self.output,companion_source=self.verification_source())
    def test_modified_non_catalogue_original_is_rejected(self):
        self.generate()
        (self.game/'xml/gz/v855098/collections.xml.gz').write_bytes(b'different original')
        with self.assertRaisesRegex(ValueError,'collections.xml.gz'):
            self.verify(self.output,game_root=self.game,companion_source=self.verification_source())
    def test_source_inventory_cannot_omit_a_required_original(self):
        self.generate()
        path=self.output/'RESOURCE_BUILD.json';receipt=json.loads(path.read_text())
        del receipt['sourceInputs']['xml/gz/v855098/collections.xml.gz'];path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'source inventory is incomplete'):
            self.verify(self.output,companion_source=self.verification_source())
    def test_even_empty_linked_resource_directories_are_rejected(self):
        self.generate();empty=self.base/'unrelated';empty.mkdir()
        (self.output/'linked').symlink_to(empty,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'Linked'):
            self.verify(self.output,companion_source=self.verification_source())
    def test_output_cannot_mutate_an_external_extracted_asset_tree(self):
        assets=self.base/'extracted';assets.mkdir()
        with self.assertRaisesRegex(ValueError,'separate from extracted'):
            bootstrap.generate(self.game,assets/'generated',assets_root=assets,policy_root=self.policy,include_skin=False)
        self.assertEqual(list(assets.iterdir()),[])
    def test_duplicate_original_records_keep_identity_order_and_raw_prices(self):
        self.records.append(dict(self.records[0],cost='999',code='DUP'))
        self.put_amf('xml/gz/v855038/items_opt.amf',{'settings':{'items':{'item':self.records}}})
        self.generate()
        catalog=json.loads((self.output/'data/catalog.json').read_text())
        self.assertEqual([(row['code'],row['cost']) for row in catalog],[('FC',10),('DUP',999)])
        self.assertTrue(catalog[1]['artwork']['duplicateLookup'])
        self.assertEqual(self.verify(self.output,game_root=self.game,companion_source=self.verification_source(),expected_records=2)['originalRowsCompared'],2)
    def test_original_collection_and_quest_xml_yield_localized_helper_definitions(self):
        (self.game/'xml/gz/v855098/collections.xml.gz').write_bytes(zlib.compress(
            b'<collections><collection name="fixture" code="C1" icon="assets/crops/fixture.png"><collectable name="fixturecrop" numneeded="3"/></collection></collections>'))
        (self.game/'xml/gz/v855098/questSettings_0.xml.gz').write_bytes(zlib.compress(
            b'<quests><quest name="fixtureQuest"><frontend><textBundle>fixtureQuest</textBundle><icon>assets/crops/fixture.png</icon></frontend><tasks><task action="harvest" type="seed" total="5"/></tasks></quest></quests>'))
        labels={'text':{'Collections':{'fixture_friendlyName':{'original':'Fixture collection'}},
                        'Quests':{'fixtureQuest_Title':{'original':'Harvest fixture crops'},
                                  'fixtureQuest_harvest_seed_Description':{'original':'Harvest five crops'}}}}
        module=bootstrap.prepare_helpers
        with mock.patch.object(module,'abc_blocks',return_value=[b'fixture']), mock.patch.object(module,'locale_constructor',return_value=([],[],b'')), mock.patch.object(module,'literal_properties',return_value=labels):
            result=REAL_HELPERS_RECOVER(self.game)
        self.assertEqual(result['collections'][0]['displayName'],'Fixture collection')
        self.assertEqual(result['collections'][0]['items'][0]['numneeded'],3)
        self.assertEqual((result['quests'][0]['displayName'],result['quests'][0]['tasks'][0]['total']),('Harvest fixture crops',5))
        module.copy_artwork(self.game,result,root=self.output,assets_root=self.game/'assets')
        self.assertEqual(result['quests'][0]['imageStatus'],'exact')
        self.assertEqual((self.output/result['quests'][0]['image'].lstrip('/')).read_bytes(),png())
    def test_original_progression_rewards_and_mastery_are_read_without_player_state(self):
        self.records[0].update(mastery='true',masteryLevel=[{'level':'1'}])
        self.put_amf('xml/gz/v855038/items_opt.amf',{'settings':{'items':{'item':self.records}}})
        (self.game/'xml/gz/v855098/gameSettings.xml.gz').write_bytes(zlib.compress(
            b'<settings><achievements><achievement name="haveneighbors" code="R1"><image name="icon_100" url="assets/crops/fixture.png"/><image name="icon_blue" url="assets/crops/fixture.png"/><level count="5" xp="7" coins="11" gift="FC"/></achievement></achievements></settings>'))
        result=REAL_PROGRESSION_RECOVER(self.game,root=self.output,assets_root=self.game/'assets')
        tier=result['ribbons'][0]['levels'][0]
        self.assertEqual((tier['count'],tier['xp'],tier['coins'],tier['gift']),(5,7,11,'FC'))
        self.assertEqual(result['masteryItems'],['fixturecrop'])
        self.assertEqual((self.output/'static/assets/ui/ribbon.png').read_bytes(),png())
        self.assertFalse((self.game/'LocalData').exists())
    def test_original_lossless_swf_raster_recovers_alpha_without_private_art(self):
        module=load('fixture_skin_rasters','prepare_skin.py')
        module.SOURCE=self.game;module.DEST=self.output
        self.output.mkdir()
        content=struct.pack('<HBHH',32,5,1,1)+zlib.compress(bytes((128,16,32,48)))
        tag=struct.pack('<H',(36<<6)|63)+struct.pack('<I',len(content))+content
        body=b'\0'+b'\0'*4+tag+b'\0\0'
        swf=self.game/'embeds/fixture.swf';swf.write_bytes(b'FWS'+bytes((10,))+struct.pack('<I',8+len(body))+body)
        module.extract('embeds/fixture.swf','fixture')
        output=self.output/'fixture-32.png'
        self.assertTrue(output.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertEqual(module.records[0]['swfCharacterId'],32)
        self.assertEqual(module.records[0]['sha256'],hashlib.sha256(output.read_bytes()).hexdigest())

if __name__=='__main__':unittest.main()
