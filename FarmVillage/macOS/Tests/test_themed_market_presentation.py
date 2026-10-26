"""Original world-class Market gate matches basic-themed server admission."""
from collections import Counter
import copy
import hashlib
from pathlib import Path
from unittest import mock
import sys
import unittest
import xml.etree.ElementTree as ET
import zlib

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(Path(__file__).resolve().parent)]
import test_persistence as fixtures  # Synthetic data paths before product imports.
import themed_market_presentation as policy
import themed_worlds
try:
    import october_presentation
except ModuleNotFoundError as error:
    if error.name != 'october_presentation':raise
    october_presentation=None
from test_turbo_client_refusal import PATCH,ABC,read_abcs


class ThemedMarketPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=policy._raw_items()
        cls.by_name={x['name']:x for x in cls.rows}
        cls.raw=policy.WORLD_SETTINGS_SOURCE.read_bytes()
        cls.template_bytes={name:(ROOT/'templates'/name).read_bytes() for name in ('play.html','ruffle.html')}
        cls.abc=read_abcs(zlib.decompress(PATCH.patch_client_bytes(
            (ROOT/'embeds/Flash/v855097-855094/FarmGame.swf').read_bytes())[8:]))[0]

    def run_visibility(self, ident, item, world, *, seed=False, license=False, deal=False):
        state={'className':item.get('className') or '', 'worldRestrictions':list(policy._worlds(item)),
               'buyable':item.get('buyable') not in (False,'false'), 'isInExperiment':True,
               'isLicenseHidden':False,'isLicenseValid':license,'isDealOfDaySaleItem':deal,
               'isInDealOfDayExperiment':deal}
        locks=list(policy.class_locks()) if world in themed_worlds.SPECS else None
        globals_={'Global':{'worldManager':{'worldSpecificClassLocks':locks,'currentWorldType':world}}}
        def execute(method):
            code=self.abc.bodies[method];locals_={0:state};stack=[];pos=0;peak=0
            def u30():
                nonlocal pos
                value=shift=0
                while True:
                    byte=code[pos];pos+=1;value|=(byte&127)<<shift
                    if byte<128:return value
                    shift+=7
            for _ in range(300):
                op=code[pos];pos+=1
                if op in (0xf0,0xf1):u30()
                elif op==0xef:u30();u30();u30();u30()
                elif op in (0x02,0x09):pass
                elif op in (0xd0,0xd1,0xd2,0xd3):stack.append(locals_[op-0xd0])
                elif op in (0xd4,0xd5,0xd6,0xd7):locals_[op-0xd4]=stack.pop()
                elif op==0x62:stack.append(locals_[u30()])
                elif op==0x63:locals_[u30()]=stack.pop()
                elif op==0x30:self.assertIs(stack.pop(),state)
                elif op==0x20:stack.append(None)
                elif op in (0x26,0x27):stack.append(op==0x26)
                elif op==0x24:stack.append(int.from_bytes(code[pos:pos+1],'little',signed=True));pos+=1
                elif op==0x80:u30()
                elif op==0x85:pass
                elif op==0x76:stack.append(bool(stack.pop()))
                elif op==0x96:stack.append(not stack.pop())
                elif op==0x2a:stack.append(stack[-1])
                elif op==0x29:stack.pop()
                elif op==0xab:stack.append(stack.pop()==stack.pop())
                elif op==0xaf:right=stack.pop();stack.append(stack.pop()>right)
                elif op==0x60:stack.append(globals_[self.abc.mname(u30())])
                elif op==0x66:
                    name=self.abc.short(u30());receiver=stack.pop()
                    if name=='length':stack.append(len(receiver))
                    elif name=='isVisibleOnApplyWorldItemsOnlyCheck':stack.append(execute(6383))
                    else:stack.append(receiver[name])
                elif op==0x46:
                    name=self.abc.short(u30());count=u30();args=[stack.pop() for _ in range(count)][::-1];receiver=stack.pop()
                    if name=='indexOf':value=receiver.index(args[0]) if args[0] in receiver else -1
                    elif name=='checkSeedInventory':value=seed
                    elif name in ('checkDateGate','checkGeoGate','checkMarketPrereqs'):value=True
                    else:self.fail('Unexpected visibility call '+name)
                    stack.append(value)
                elif op in (0x10,0x11,0x12):
                    delta=int.from_bytes(code[pos:pos+3],'little',signed=True);pos+=3
                    if op==0x10 or (bool(stack.pop())==(op==0x11)):pos+=delta
                elif op==0x48:
                    value=stack.pop();self.assertEqual(stack,[]);self.assertLessEqual(peak,2);return value
                else:self.fail(f'Unexpected opcode {op:#x} at{pos-1}')
                peak=max(peak,len(stack))
            self.fail('Visibility did not return')
        return execute(ident)

    def test_emitted_blank_class_filter_hides_global_barley_keeps_australian_crop_and_legacy(self):
        global_seed=self.by_name['australianbarley'];own_seed=self.by_name['australianbarley2']
        self.assertEqual((global_seed['code'],own_seed['code']),('e8p','UYa'))
        self.assertIs(self.run_visibility(6382,global_seed,'australia'),False)
        self.assertIs(self.run_visibility(6382,own_seed,'australia'),True)
        for world in policy.LEGACY_WORLDS:
            self.assertIs(self.run_visibility(6382,global_seed,world),True)
        self.assertIs(policy.item_projection(global_seed),global_seed)
        for flag in ('seed','license','deal'):
            self.assertIs(self.run_visibility(6382,global_seed,'australia',**{flag:True}),True)

    def test_exact_raw_catalog_delta_and_every_land_row_preserved_by_this_policy(self):
        counts=Counter();classes=set();storage=[];features=[]
        for item in self.rows:
            before=copy.deepcopy(item);after=policy.item_projection(item)
            self.assertEqual(item,before)
            classes.add(item.get('className') or '')
            if policy._is_land(item):self.assertIs(after,item)
            if after!=item:
                owners=policy._worlds(item)
                if item.get('name') in policy.GLEN_SCORE_SEEDS and owners=={'glen'}:
                    kind='harvest_score'
                    self.assertEqual(before['harvestYield'], {'className':'QuestRewardHarvestYield',
                        'type':'world_score','unit':'pixie','value':'2','class':item['name'],'phylum':'harvest'})
                    self.assertNotIn('harvestYield',after)
                else:
                    kind=('feature' if item['name']=='xrforchard_finished' else
                          'storage' if not owners else 'mixed' if owners-set(themed_worlds.SPECS) else 'closed')
                counts[kind]+=1
                allowed={'harvestYield'} if kind=='harvest_score' else {'requirements'} if kind in ('storage','mixed','feature') else {'buyable'}
                if kind=='harvest_score' and 'glen' not in themed_worlds.active_worlds():
                    # The retired crop remains readable, with its old score
                    # removed, and is now explicitly unavailable to purchase.
                    allowed.add('buyable')
                    self.assertEqual(after['buyable'],'false')
                self.assertEqual({k:v for k,v in before.items() if k not in allowed},
                                 {k:v for k,v in after.items() if k not in allowed})
                if kind=='storage':storage.append((item,after))
                if kind=='feature':features.append((item,after))
            elif not policy._worlds(item)&set(themed_worlds.SPECS):self.assertIs(after,item)
        # The recovered Mistletoe cottage is now admitted by its exact regional contract.
        cottage=self.by_name['xhdcraftingcottage']
        self.assertIs(policy.item_projection(cottage),cottage)
        # Retirement closes129 Holiday and2 Glen offers in addition to the
        # prior1153. The12 score-bearing Glen crops keep their separate check.
        self.assertEqual(counts,{'closed':1284,'mixed':32,'storage':32,'feature':1,'harvest_score':12})
        self.assertEqual(set(policy.class_locks()),classes)
        self.assertEqual(len(classes),292);self.assertIn('',classes)
        self.assertEqual(len(policy.supported_worlds()),20)
        for before,after in storage:
            self.assertEqual(policy._worlds(after),set(policy.supported_worlds()))
            for world in policy.supported_worlds():
                self.assertIs(self.run_visibility(6382,after,world),True)
        self.assertEqual([before['name'] for before,_ in features],['xrforchard_finished'])
        for before,after in features:
            self.assertEqual(before['code'],'ruh')
            self.assertEqual(policy._worlds(after),set(policy.LEGACY_WORLDS)|{'rainforest'})
            for world in policy.supported_worlds():
                self.assertIs(self.run_visibility(6382,after,world),world in policy.LEGACY_WORLDS|{'rainforest'})

    def test_mixed_world_legacy_truth_and_license_nodes_are_identical(self):
        mixed=[]
        for item in self.rows:
            owners=policy._worlds(item)
            if owners&set(themed_worlds.SPECS) and owners-set(themed_worlds.SPECS):mixed.append(item)
        self.assertEqual(len(mixed),85)
        changed=0
        def truth(item,world,license_value):
            values=[]
            for node in themed_worlds.creative_worlds._nodes(item['requirements']):
                if node.get('className')=='World':
                    values.append(node.get('name')==world or node.get('strict')!='true' and world=='meadows' and node.get('name')=='farm')
                elif node.get('className')=='WorldLicense':values.append(license_value)
            return any(values)
        legacy={w.get('name') for w in ET.fromstring(zlib.decompress(self.raw))}-set(themed_worlds.SPECS)
        for item in mixed:
            self.assertEqual(item['requirements']['compare'],'any')
            after=policy.item_projection(item)
            if after!=item:changed+=1;self.assertFalse(policy._worlds(after)&set(themed_worlds.SPECS))
            for world in legacy:
                for license_value in (False,True):self.assertEqual(truth(item,world,license_value),truth(after,world,license_value))
        self.assertEqual(changed,32)

    def assert_projection_preserves_other_nodes(self,base):
        projected=policy.world_settings_payload(base)
        source=ET.fromstring(zlib.decompress(base));after=ET.fromstring(zlib.decompress(projected))
        for old,new in zip(source,after):
            if old.get('name') in themed_worlds.SPECS:
                hud=new.find('hudSkinConfig');lock=hud.find('showOnlyWorldMarketClassLock')
                self.assertEqual([node.text or '' for node in lock],list(policy.class_locks()))
                hud.remove(lock)
                if old.get('name')=='htown':
                    old.find('actionMenuConfig').remove(old.find("actionMenuConfig/button[@name='WorldProgress']"))
                    self.assertIsNone(new.find("actionMenuConfig/button[@name='WorldProgress']"))
            self.assertEqual(ET.tostring(new),ET.tostring(old))
        self.assertEqual(policy.world_settings_payload(projected),projected)

    def test_world_settings_preserve_legacy_home_and_all_other_nodes(self):
        self.assert_projection_preserves_other_nodes(self.raw)
        changed=ET.fromstring(zlib.decompress(self.raw));changed.find("world[@name='england']").set('unknown','bad')
        with self.assertRaisesRegex(ValueError,'legacy'):policy.world_settings_payload(zlib.compress(ET.tostring(changed)))
        self.assertEqual(policy.WORLD_SETTINGS_SOURCE.read_bytes(),self.raw)
        self.assertEqual(hashlib.sha256(policy.CATALOG_SOURCE.read_bytes()).hexdigest(),policy.CATALOG_SHA256)

    @unittest.skipIf(october_presentation is None,'October composition belongs to the separate owner worktree')
    def test_optional_october_composition_preserves_its_home_projection(self):
        self.assert_projection_preserves_other_nodes(october_presentation.world_settings_payload(self.raw,active=True))

    def test_trim_keeps_unrelated_null_fields_and_policy_identity_tracks_all_sources(self):
        value={'compare':'any','retain':None,'requirement':[{'className':'World','name':'toyland'},
               {'className':'World','name':'farm','strict':'true'},{'className':'WorldLicense','name':'keep','extra':None}]}
        result=policy._trim_worlds(value,{'toyland'})
        self.assertEqual(result,{'compare':'any','retain':None,'requirement':value['requirement'][1:]})
        self.assertNotEqual(result,value)
        self.assertEqual(policy.policy_digest(),policy.policy_digest())
        for name,data in self.template_bytes.items():self.assertEqual((ROOT/'templates'/name).read_bytes(),data)


class ThemedMarketServingTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp=fixtures.RuntimeFixtureTests.setUp
    fixture=fixtures.RuntimeFixtureTests.fixture
    write_fixture=fixtures.RuntimeFixtureTests.write_fixture

    def test_world_settings_route_composes_both_projects_and_preserves_save_bytes(self):
        path=self.write_fixture();before=path.read_bytes()
        raw=policy.WORLD_SETTINGS_SOURCE.read_bytes()
        for active in ((False,True) if october_presentation is not None else (False,)):
            with self.subTest(october=active), mock.patch.object(self.server,'october_style_selected',return_value=active,create=True):
                response=self.client.get('/xml/gz/v855098/worldSettings.xml.gz')
            self.assertEqual(response.status_code,200)
            base=october_presentation.world_settings_payload(raw,active=active) if october_presentation is not None else raw
            self.assertEqual(response.data,policy.world_settings_payload(base))
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            self.assertIn('Cookie',response.headers.get('Vary',''))
        self.assertEqual(path.read_bytes(),before)


if __name__=='__main__':unittest.main()
