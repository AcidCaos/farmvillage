"""Glen candidate checks. Run only in a marked disposable candidate runtime."""
from collections import Counter
from contextlib import redirect_stdout
import copy
import io
import json
import math
from pathlib import Path
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
import zlib

import test_themed_worlds as common  # Installs synthetic writable paths first.
import test_persistence as fixtures
import test_cove_cellar as cellar
import test_inventory_capacity as capacity
import creative_worlds
import heritage_pricing
import items
import peaceful
import pyamf
import storage
import themed_client_presentation as presentation
import themed_land_offers
import themed_market_presentation as market
import themed_worlds as tw
import world_travel

WORLD = 'glen'
NOW = common.NOW


class GlenContractTests(unittest.TestCase):
    def test_exact_omissions_disclosed_theme_and_source_inventory(self):
        original = tw._xml('gameSettings.xml.gz').find("expansions/expansion[@name='glen']")
        self.assertEqual(original.attrib, {'name':'glen','score':'pixie','scoreFile':'worldScorePixie.xml'})
        self.assertIsNone(original.find('startingTileSet'))
        rules = tw.recovered_rules(WORLD)
        self.assertEqual((rules['storageId'],rules['tileSet'],rules['initialSize'],rules['plotCeiling']),
                         (-18,'glen_theme',50,5500))
        self.assertTrue(rules['localThemeChoice'])
        self.assertEqual(rules['theme'], {'horizon':'assets/Environment/xeg_theme.swf',
            'backgroundPath':'assets/Environment/xeg_themeBackground_', 'tileClass':'grass',
            'weights':'18,36,54,55,56,57,58,59'})
        rows = pyamf.get_decoder(pyamf.AMF3,zlib.decompress(
            (Path(tw.XML_DIR)/'gz/v855098/storageConfig.amf.gz').read_bytes())).readElement()['storage']['StorageEntity']
        self.assertEqual([r for r in rows if r.get('name')=='GlenInventory'],
                         [{'name':'GlenInventory','extends':'Inventory','loc':'player','id':'-18'}])
        self.assertEqual(storage._inventory_limits()[-18],1250)
        self.assertIn(WORLD,heritage_pricing.RESERVED_WORLDS)

    def test_normalizing_missing_archive_fields_rejects_drift(self):
        original=tw._xml
        for field,value in (('storageId','-18'),('prefix','xeg'),('startingTileSet','glen_theme')):
            def changed(name):
                root=original(name)
                if name=='gameSettings.xml.gz':
                    node=root.find("expansions/expansion[@name='glen']")
                    if field=='startingTileSet':ET.SubElement(node,field).text=value
                    else:node.set(field,value)
                return root
            tw.recovered_rules.cache_clear()
            try:
                with self.subTest(field=field),mock.patch.object(tw,'_xml',side_effect=changed),self.assertRaisesRegex(ValueError,'world record'):
                    tw.recovered_rules(WORLD)
            finally:tw.recovered_rules.cache_clear()

    def test_ordinary_catalog_is_twelve_seeds_two_decorations_and_thirtytwo_storage_buildings(self):
        catalog=tw.catalog_rules(WORLD)
        self.assertEqual(Counter(r['type'] for r in catalog['items'].values()),{'seed':12,'decoration':2,'building':32})
        self.assertEqual(catalog['unpriced'],{})
        self.assertEqual(catalog['items']['ambrosiatulip']['price'],{'currency':'coins','amount':75})
        self.assertEqual(catalog['items']['xegpebbles3']['price'],{'currency':'coins','amount':1500})
        self.assertEqual(catalog['items']['xegleafboatwithafairy']['price'],{'currency':'coins','amount':1300})
        def writers(value):
            if isinstance(value,dict):
                for key,child in value.items():
                    if 'score' in key.lower() and child not in tw.NONE_VALUES:yield key,child
                    if isinstance(child,str) and child in ('world_score','unlock_world_score'):yield key,child
                    yield from writers(child)
            elif isinstance(value,list):
                for child in value:yield from writers(child)
        globals_=[]
        for name,rule in catalog['items'].items():
            self.assertIn(rule['price']['currency'],('coins','cash'))
            item=items.get_item_by_name(name)
            projected=market.item_projection(item)
            self.assertEqual(list(writers(projected)),[],name)
            owners={n.get('name') for n in creative_worlds._nodes(item.get('requirements')) if n.get('className')=='World'}
            if WORLD not in owners:
                globals_.append(name)
                self.assertEqual((item['className'],item['storageType']['itemClass']),('StorageBuilding','Inventory'))
        self.assertEqual(len(globals_),32)

    def test_imported_inventory_claims_remain_unchanged_on_rejection(self):
        for ident in (-18,'-18','-1.8e1'):
            save=common.base_save();save['userInfo']['worldSummaryData']['opaque']={'storageId':ident,'preserve':[1]}
            before=copy.deepcopy(save)
            with self.subTest(ident=ident),self.assertRaises(ValueError):tw.create(save,WORLD,now=NOW)
            self.assertEqual(save,before)
        for claim in ('ledger','summary','unlock'):
            save=common.base_save()
            if claim=='ledger':save['userInfo']['player']['storageData']['-18']={'opaque':[1,[],[{'preserve':True}]]}
            elif claim=='summary':save['userInfo']['worldSummaryData'][WORLD]={'storageId':-18}
            else:save['userInfo']['unlockedWorldTypes'].append(WORLD)
            before=copy.deepcopy(save)
            with self.subTest(claim=claim),self.assertRaises(ValueError):tw.create(save,WORLD,now=NOW)
            self.assertEqual(save,before)

    def test_all_thirtysix_expansion_objects_recorded_and_land_fenced(self):
        additions=tw.expansion_additions(WORLD)
        self.assertEqual((min(additions),sum(map(len,additions.values()))),(58,36))
        self.assertEqual(list(additions[58]),[{'code':code,'x':x,'y':y,'z':'0','state':'construct_0'}
            for code,x,y in (('afx','5','44'),('cfx','24','5'),('dfx','4','16'))])
        for width,offers in tw.catalog_rules(WORLD)['expansions'].items():
            for offer in offers:self.assertTrue(themed_land_offers.blocked_offer(items.get_item_by_name(offer['name'])),(width,offer))

    def test_exact_one_pixie_task_and_beat_fence_preserve_other_tracks(self):
        original=tw._xml('gameSettings.xml.gz')
        derived=ET.fromstring(zlib.decompress(presentation.game_settings_payload()))
        self.assertEqual(original.find("expansions/expansion[@name='glen']").get('score'),'pixie')
        projected=derived.find("expansions/expansion[@name='glen']")
        self.assertIsNone(projected.get('score'));self.assertEqual(projected.get('scoreFile'),'worldScorePixie.xml')
        self.assertEqual(presentation.BEAT_GATES[WORLD],('beatEnchantedGlen','fv_beat_enchanted_glen',1))
        self.assertEqual(presentation.beat_experiment_overrides()['fv_beat_enchanted_glen'],0)
        before=pyamf.get_decoder(pyamf.AMF3,zlib.decompress(presentation.SCORE_SOURCE.read_bytes())).readElement()
        after=pyamf.get_decoder(pyamf.AMF3,zlib.decompress(presentation.world_score_payload())).readElement()
        tasks=before['worldScoreGlobal']['scores']['score']['task']
        pixie=[t for t in tasks if 'pixie' in json.dumps(t)]
        self.assertEqual(pixie,[{'action':'buyItemByCategory','type':'GlenLE','total':'1','rewards':{'reward':
            {'unit':'pixie','class':'LE','phylum':'bought_le','type':'world_score','value':'5'}}}])
        self.assertTrue(presentation.blocked_global_task(pixie[0]))
        blocked=[t for t in tasks if presentation.blocked_global_task(t)]
        self.assertEqual(len(blocked),presentation.BLOCKED_GLOBAL_TASK_COUNT)
        before['worldScoreGlobal']['scores']['score']['task']=[t for t in tasks if not presentation.blocked_global_task(t)]
        self.assertEqual(after,before)
        hud=ET.fromstring(zlib.decompress(market.world_settings_payload())).find("world[@name='glen']")
        self.assertEqual([b.get('name') for b in hud.findall('actionMenuConfig/button')],['FastTravel'])
        self.assertIsNotNone(hud.find('hudSkinConfig/showOnlyWorldMarketClassLock'))

    def test_derived_harvest_projection_only_removes_exact_original_pixie_reward(self):
        self.assertEqual(set(tw.allowed_seeds(WORLD)),set(market.GLEN_SCORE_SEEDS))
        for name in tw.allowed_seeds(WORLD):
            source=copy.deepcopy(items.get_item_by_name(name));before=copy.deepcopy(source)
            expected=copy.deepcopy(source);expected.pop('harvestYield')
            projected=market.item_projection(source)
            self.assertEqual(source,before);self.assertEqual(projected,expected)
            self.assertEqual(market.item_projection(projected),projected)
            for changed in ({**source['harvestYield'],'value':'3'},[source['harvestYield']],{'type':'world_score','unit':'shell'}):
                with self.subTest(name=name,changed=changed),self.assertRaisesRegex(ValueError,'harvest-score reward'):
                    market.item_projection(dict(source,harvestYield=changed))
        home=copy.deepcopy(items.get_item_by_name('strawberry'))
        self.assertEqual(market.item_projection(home),home)
        opaque=dict(home,harvestYield={'type':'world_score','unit':'pixie','preserve':[1]})
        self.assertEqual(market.item_projection(opaque),opaque)

    def test_real_client_catalog_pipeline_preserves_server_records_and_source_bytes(self):
        from datetime import date
        import client_catalog
        source=Path(items.ITEMS_AMF);source_before=source.read_bytes()
        names=tw.allowed_seeds(WORLD)+['strawberry','xegpebbles3']
        server_before={name:copy.deepcopy(items.get_item_by_name(name)) for name in names}
        records=[copy.deepcopy(server_before[name]) for name in names]
        encoded=zlib.compress(pyamf.encode({'settings':{'items':{'item':records}}},encoding=pyamf.AMF3).getvalue())
        with mock.patch.object(client_catalog.mastery_signs,'apply'),mock.patch.object(client_catalog.heritage_pricing,'apply'),mock.patch.object(client_catalog,'_paid_projection_policy',return_value=(lambda x:x,'test')):
            result=client_catalog._generate(encoded,date(2026,10,24),frozenset())
        derived=pyamf.get_decoder(pyamf.AMF3,zlib.decompress(result)).readElement()['settings']['items']['item']
        for original,projected in zip(records,derived):
            expected=copy.deepcopy(original)
            if original['name'] in market.GLEN_SCORE_SEEDS:expected.pop('harvestYield')
            self.assertEqual(projected,expected)
        self.assertEqual(source.read_bytes(),source_before)
        self.assertEqual({name:items.get_item_by_name(name) for name in names},server_before)


class GlenGatewayTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    fixture=fixtures.RuntimeFixtureTests.fixture
    write_fixture=fixtures.RuntimeFixtureTests.write_fixture
    command=staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload=fixtures.RuntimeFixtureTests.gateway_payload
    gateway=fixtures.RuntimeFixtureTests.gateway
    save=cellar.CoveCellarTests.save
    persist=cellar.CoveCellarTests.persist
    send=cellar.CoveCellarTests.send
    rejected=cellar.CoveCellarTests.rejected

    def setUp(self):
        fixtures.RuntimeFixtureTests.setUp(self)
        experiments=mock.patch.object(tw,'served_experiments',return_value=common.dormant_experiments())
        experiments.start();self.addCleanup(experiments.stop)
        patcher=mock.patch.object(tw,'ACTIVE_WORLDS',frozenset({WORLD}));patcher.start();self.addCleanup(patcher.stop)
        self.path=self.write_fixture();self.save['world']['objectsArray']=[]
        self.save['userInfo']['player'].update(xp=common.level_to_xp(20),gold=123456,cash=73)
        creative_worlds.create(self.save,WORLD,'allAccess',now=NOW)
        world_travel.switch(self.save,WORLD,now=NOW);self.persist()

    def test_paid_storage_deposit_disk_reload_roundtrip_withdraw_move_sale(self):
        home=copy.deepcopy(self.save['userInfo']['player']['storageData']['-2'])
        self.send('place',capacity.InventoryCapacityTests.shed())
        self.assertEqual(self.save['userInfo']['player']['cash'],51)
        snapshot={'id':64002,'className':'RotateableDecoration','itemName':'xegpebbles3','state':'horizontal',
                  'direction':0,'position':{'x':20,'y':20,'z':0}}
        ident=self.send('place',snapshot)['id'];self.assertEqual(self.save['userInfo']['player']['gold'],121956)
        saved=copy.deepcopy(next(o for o in self.save['world']['objectsArray'] if o['id']==ident))
        self.send('store',saved,[{'storedItemName':'xegpebbles3','target':-18,'origin':0,'resource':ident}])
        self.assertEqual(self.save['userInfo']['player']['storageData']['-18']['a65'],[1,[],[]])
        with redirect_stdout(io.StringIO()):self.player.load_saves()
        world_travel.switch(self.save,'farm',now=NOW);world_travel.switch(self.save,WORLD,now=NOW);self.persist()
        balance=(self.save['userInfo']['player']['gold'],self.save['userInfo']['player']['cash'])
        ident=self.send('place',dict(saved,id=64003),[{'isInventoryWithdrawal':True,'cameFromLocation':-18}])['id']
        self.assertEqual((self.save['userInfo']['player']['gold'],self.save['userInfo']['player']['cash']),balance)
        moved=dict(saved,id=ident,position={'x':25,'y':25,'z':0});self.send('move',moved);self.send('sell',moved)
        self.assertFalse(any(o['id']==ident for o in self.save['world']['objectsArray']))
        self.assertEqual(self.save['userInfo']['player']['storageData']['-2'],home)

    def test_zero_capacity_cross_world_and_unsupported_actions_preserve_state_and_disk(self):
        snapshot={'id':64002,'className':'Decoration','itemName':'xegleafboatwithafairy','state':'static',
                  'direction':0,'position':{'x':20,'y':20,'z':0}}
        ident=self.send('place',snapshot)['id'];saved=copy.deepcopy(next(o for o in self.save['world']['objectsArray'] if o['id']==ident))
        self.rejected('store',saved,[{'storedItemName':'xegleafboatwithafairy','target':-18,'origin':0,'resource':ident}])
        self.send('place',capacity.InventoryCapacityTests.shed())
        self.rejected('store',saved,[{'storedItemName':'xegleafboatwithafairy','target':-2,'origin':0,'resource':ident}])
        self.rejected('place',dict(snapshot,id=64005,itemName='haybale'))
        self.rejected('plow',common.plot(64006,isSuperPlot=True))

    def test_paid_plow_plant_grow_harvest_replow_and_retry_survive_disk_and_travel(self):
        scores=copy.deepcopy(self.save['userInfo']['player'].get('worldScores'))
        crop=common.plot(64001,plantTime=0,position={'x':12,'y':12,'z':0})
        crop['id']=self.send('plow',crop)['id'];self.send('plow',crop)
        self.assertEqual(self.save['userInfo']['player']['gold'],123441)
        crop.update(itemName='ambrosiatulip',state='planted',plantTime=NOW*1000)
        self.send('place',crop);self.assertEqual(self.save['userInfo']['player']['gold'],123366)
        fallow=dict(crop,state='fallow');self.rejected('harvest',fallow)
        ready=NOW+math.ceil(peaceful.grow_seconds(items.get_item_by_name('ambrosiatulip')))
        self.timed_action('harvest',fallow,ready)
        self.timed_action('harvest',fallow,ready)
        replowed=dict(fallow,state='plowed')
        self.timed_action('plow',replowed,ready)
        self.timed_action('plow',replowed,ready)
        item=items.get_item_by_name('ambrosiatulip')
        self.assertEqual(self.save['userInfo']['player']['gold'],123456-30-75+int(item['coinYield']))
        with redirect_stdout(io.StringIO()):self.player.load_saves()
        world_travel.switch(self.save,'farm',now=ready);world_travel.switch(self.save,WORLD,now=ready)
        obj=next(o for o in self.save['world']['objectsArray'] if o['id']==crop['id'])
        self.assertEqual((obj['state'],obj['itemName'],obj['plantTime']),('plowed','ambrosiatulip',NOW*1000))
        self.assertEqual(self.save['userInfo']['player'].get('worldScores'),scores)

    def test_first_action_instant_grow_costs_four_cash_once_and_reloads(self):
        self.save['world']['objectsArray']=[common.plot(10,'planted',itemName='ambrosiatulip',plantTime=NOW*1000)]
        self.persist()
        plane={'id':63001,'className':'Airplane','itemName':'biplanered','tempId':-1,'state':'static',
               'position':{'x':33,'y':66,'z':0}}
        options={0:{'aoeSources':{},'type':1,'autoHarvest':{'autoPPH':False}},1:{'firstWA':True}}
        request=self.command('WorldService.performAction',['instantGrow',plane,options],99)
        with mock.patch('commands.timestamp_now',return_value=NOW),mock.patch('server.timestamp_now',return_value=NOW):
            response=self.gateway([request]);fixtures.assert_gateway_status(self,response,200)
            self.assertEqual(self.save['userInfo']['player']['cash'],69)
            self.assertEqual(self.save['world']['objectsArray'][0]['state'],'grown')
            once=copy.deepcopy(self.save);disk=self.path.read_bytes()
            response=self.gateway([request]);fixtures.assert_gateway_status(self,response,200)
            self.assertEqual(self.save,once);self.assertEqual(self.path.read_bytes(),disk)
            with redirect_stdout(io.StringIO()):self.player.load_saves()
            response=self.gateway([request]);fixtures.assert_gateway_status(self,response,200)
            self.assertEqual(self.save,once)

    def timed_action(self,name,snapshot,now):
        with mock.patch('commands.timestamp_now',return_value=now),mock.patch('engine.timestamp_now',return_value=now),mock.patch('server.timestamp_now',return_value=now):
            response=self.gateway([self.command('WorldService.performAction',[name,snapshot,[]])])
        fixtures.assert_gateway_status(self,response,200)
        from pyamf import remoting
        return remoting.decode(response.data).bodies[0][1].body['data'][0]['data']
