"""Atlantis's source exceptions and bounded loops; only synthetic in-memory/disk saves."""
from collections import Counter
from contextlib import redirect_stdout
import copy
import io
import json
import re
from pathlib import Path
import sys
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
import zlib
import pyamf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import test_cove_cellar as cellar
import test_inventory_capacity as capacity
import test_themed_worlds as worlds
import creative_worlds
import heritage_pricing
import items
import storage
import themed_client_presentation as presentation
import themed_land_offers
import themed_market_presentation as market
import themed_worlds as tw
import world_travel
from game_settings import level_to_xp
from bundle import XML_DIR

NOW = 1800000000
WORLD = 'atlantis'

def decode(name):
    return pyamf.get_decoder(pyamf.AMF3,zlib.decompress((Path(XML_DIR)/'gz/v855098'/name).read_bytes())).readElement()

class AtlantisContractTests(unittest.TestCase):
    def setUp(self):
        patcher=mock.patch.object(tw,'ACTIVE_WORLDS',frozenset({WORLD}))
        patcher.start();self.addCleanup(patcher.stop)

    def save(self, **kwargs):
        save=worlds.base_save(**kwargs)
        creative_worlds.create(save,WORLD,'allAccess',now=NOW)
        world_travel.switch(save,WORLD,now=NOW)
        return save

    def test_original_xml_omissions_remain_exact_and_local_theme_is_disclosed(self):
        spec=tw.SPECS[WORLD]
        self.assertEqual((spec['xmlStorageId'],spec['xmlPrefix'],spec['xmlTheme']),(None,None,None))
        record=tw._xml('gameSettings.xml.gz').find("expansions/expansion[@name='atlantis']")
        self.assertEqual(record.attrib,{'name':'atlantis','score':'shell','scoreFile':'worldScoreShell.xml'})
        self.assertIsNone(record.find('startingTileSet'))
        rules=tw.recovered_rules(WORLD)
        self.assertEqual((rules['storageId'],rules['tileSet'],rules['initialSize'],rules['plotCeiling']),
                         (-19,'atlantis_theme',50,5500))
        self.assertTrue(rules['localThemeChoice'])
        self.assertEqual(rules['theme']['tileClass'],'grass')
        self.assertEqual(rules['theme']['weights'],'18,36,54,55,56,57,58,59')
        card=next(row for row in creative_worlds.candidates() if row['worldType']==WORLD)
        self.assertIn('theme',card['starter']);self.assertIn('not recovered',card['starter'])

    def test_normalizing_missing_expansion_fields_fails_closed(self):
        original=tw._xml
        for field,value in (('storageId','-19'),('prefix','xal'),('startingTileSet','atlantis_theme')):
            def changed(name):
                root=original(name)
                if name=='gameSettings.xml.gz':
                    node=root.find("expansions/expansion[@name='atlantis']")
                    if field=='startingTileSet':ET.SubElement(node,field).text=value
                    else:node.set(field,value)
                return root
            tw.recovered_rules.cache_clear()
            try:
                with self.subTest(field=field),mock.patch.object(tw,'_xml',side_effect=changed),self.assertRaisesRegex(ValueError,'world record'):
                    tw.recovered_rules(WORLD)
            finally:tw.recovered_rules.cache_clear()

    def test_original_inventory_identity_is_distinct_and_inherits_only_the_ceiling(self):
        rows=decode('storageConfig.amf.gz')['storage']['StorageEntity']
        self.assertEqual([row for row in rows if row.get('name')=='AtlantisInventory'],
                         [{'name':'AtlantisInventory','extends':'Inventory','loc':'player','id':'-19'}])
        self.assertEqual(next(row['id'] for row in rows if row.get('name')=='GlenInventory'),'-18')
        self.assertEqual(next(row['limit'] for row in rows if row.get('name')=='Inventory'),'1250')
        self.assertEqual(storage.ATLANTIS_INVENTORY_ID,-19)
        save=self.save()
        self.assertEqual(storage.active_inventory_id(save),-19)
        self.assertEqual(storage._inventory_limits()[-19],1250)
        before=copy.deepcopy(save)
        with self.assertRaisesRegex(ValueError,'storage space'):storage._guard_inventory_deposit(save,-19,1)
        self.assertEqual(save,before)

    def test_free_access_grants_only_world_unlock_and_repeat_is_durable(self):
        save=worlds.base_save();save['userInfo']['player']['worldScores']={'shell':{'preserve':[7]}}
        before=copy.deepcopy(save['userInfo']['player'])
        before['storageData']['-19']={}
        self.assertTrue(creative_worlds.create(save,WORLD,'allAccess',now=NOW))
        self.assertEqual(save['userInfo']['player'],before)
        self.assertEqual(save['userInfo']['worldSummaryData'][WORLD]['storageId'],-19)
        self.assertEqual(save[world_travel.STATE_KEY]['inactive'][WORLD]['objectsArray'],[])
        restored=json.loads(json.dumps(save))
        self.assertFalse(creative_worlds.create(restored,WORLD,'allAccess',now=NOW))
        world_travel.switch(restored,WORLD,now=NOW)
        self.assertEqual(restored['world']['localStarter'],'empty-atlantis-v1')
        world_travel.switch(restored,'farm',now=NOW)
        world_travel.switch(restored,WORLD,now=NOW)
        self.assertEqual(restored['userInfo']['player'],before)

    def test_access_uses_open_master_and_for_all_but_retains_level_and_option_guards(self):
        rules=tw.recovered_rules(WORLD)
        self.assertEqual(rules['experiments'],{'master':'fv_atlantis','forAll':'fv_atlantis_for_all'})
        self.assertEqual({key:tw.served_experiments().get(key) for key in rules['experiments'].values()},
                         {'fv_atlantis':1,'fv_atlantis_for_all':1})
        for option,level in (('earlyAccess',15),('generalAccess',15),('allAccess',14)):
            save=worlds.base_save(level=level);before=copy.deepcopy(save)
            with self.subTest(option=option,level=level),self.assertRaises(ValueError):creative_worlds.create(save,WORLD,option,now=NOW)
            self.assertEqual(save,before)
        for gate in ('fv_atlantis','fv_atlantis_for_all'):
            served=dict(tw.served_experiments());served[gate]=0
            save=worlds.base_save();before=copy.deepcopy(save)
            with self.subTest(gate=gate),mock.patch.object(tw,'served_experiments',return_value=served),self.assertRaisesRegex(ValueError,'not served'):
                creative_worlds.create(save,WORLD,'allAccess',now=NOW)
            self.assertEqual(save,before)

    def test_ordinary_catalog_has_eighteen_seeds_twelve_decorations_and_no_tree_or_animal(self):
        catalog=tw.catalog_rules(WORLD)
        self.assertEqual(Counter(row['type'] for row in catalog['items'].values()),{'seed':18,'decoration':12,'building':39})
        self.assertEqual(catalog['unpriced'],{})
        globals_=[]
        for name,row in catalog['items'].items():
            self.assertIn(row['price']['currency'],('coins','cash'))
            item=items.get_item_by_name(name)
            owners={n.get('name') for n in creative_worlds._nodes(item.get('requirements')) if n.get('className')=='World'}
            if WORLD in owners:continue
            globals_.append(name)
            self.assertEqual((item.get('className'),item.get('storageType',{}).get('itemClass')),('StorageBuilding','Inventory'))
        self.assertEqual(len(globals_),32)
        self.assertEqual(catalog['items']['aquamarinerose']['price'],{'currency':'coins','amount':40})
        self.assertEqual(catalog['items']['toolshedpink']['price'],{'currency':'cash','amount':22})
        self.assertEqual(catalog['items']['ancientstatue']['price'],{'currency':'cash','amount':12})

    def test_items_remain_world_owned_and_special_feature_offers_stay_closed(self):
        self.assertIn(WORLD,heritage_pricing.RESERVED_WORLDS)
        save=self.save(gold=1000000,cash=100)
        for name in ('strawberry','animal_breeding_observatory','animal_breeding_observatory_finished'):
            item=items.get_item_by_name(name);before=copy.deepcopy(save)
            with self.subTest(item=name),self.assertRaises(ValueError):tw.guard_purchase(save,item,now=NOW)
            self.assertEqual(save,before)
        self.assertTrue(creative_worlds.world_requirement_matches(items.get_item_by_name('aquamarinerose'),WORLD))
        self.assertFalse(creative_worlds.world_requirement_matches(items.get_item_by_name('aquamarinerose'),'farm'))
        self.assertFalse(tw._own_gate('fv_AquariumGarden',WORLD))
        self.assertFalse(tw._own_gate('fv_atlantis_le_sale',WORLD))
        self.assertTrue(tw._own_gate('fv_xal_farm14_coins',WORLD))

    def test_only_original_submarine_visual_can_be_a_requirement_free_atlantis_carrier(self):
        import instant_growth
        plane=items.get_item_by_name('xalsubmarine')
        self.assertEqual((plane['code'],plane['className'],plane.get('requirements'),plane['experimentGate']),
                         ('ht9','Airplane',None,'fv_atlantis'))
        ui=tw._xml('worldSettings.xml.gz').find("world[@name='atlantis']/hudSkinConfig/instantGrowItemVisual")
        self.assertEqual(ui.get('name'),'xalsubmarine')
        saved={'userInfo':{'currentWorldType':WORLD}}
        self.assertTrue(instant_growth._temporary_airplane_allowed(saved,plane))
        self.assertFalse(instant_growth._temporary_airplane_allowed({'userInfo':{'currentWorldType':'glen'}},plane))
        self.assertFalse(instant_growth._temporary_airplane_allowed(saved,dict(plane,experimentGate='fv_other')))
        self.assertFalse(instant_growth._temporary_airplane_allowed(saved,dict(plane,name='unrelated')))
        self.assertFalse(instant_growth._temporary_airplane_allowed(saved,dict(plane,requirements={'requirement':{'className':'WorldLicense','name':WORLD}})))

    def test_imported_minus_nineteen_claims_and_missing_snapshots_are_preserved(self):
        for value in (-19,'-19','-19.0'):
            save=worlds.base_save();save['userInfo']['worldSummaryData']['opaque']={'storageId':value,'retained':[1]}
            before=copy.deepcopy(save)
            with self.subTest(value=value),self.assertRaises(ValueError):creative_worlds.create(save,WORLD,'allAccess',now=NOW)
            self.assertEqual(save,before)
        for claim in ('ledger','summary','unlock'):
            save=worlds.base_save()
            if claim=='ledger':save['userInfo']['player']['storageData']['-19']={'old':[1,[],[{'keep':True}]]}
            elif claim=='summary':save['userInfo']['worldSummaryData'][WORLD]={'storageId':-19}
            else:save['userInfo']['unlockedWorldTypes'].append(WORLD)
            before=copy.deepcopy(save)
            with self.subTest(claim=claim),self.assertRaises(ValueError):creative_worlds.create(save,WORLD,'allAccess',now=NOW)
            self.assertEqual(save,before)
        save=worlds.base_save();save['userInfo']['worldSummaryData']['glen']={'storageId':-18,'retained':[1]}
        self.assertTrue(creative_worlds.create(save,WORLD,'allAccess',now=NOW))
        self.assertEqual(save['userInfo']['worldSummaryData']['glen'],{'storageId':-18,'retained':[1]})

    def test_all_forty_original_expansion_objects_are_recorded_and_land_offers_fenced(self):
        additions=tw.expansion_additions(WORLD)
        self.assertEqual((min(additions),sum(map(len,additions.values()))),(58,40))
        self.assertEqual(additions[58][0],{'code':'qt8','x':'5','y':'44','z':'0','state':'construct_0'})
        save=self.save(gold=1000000,cash=100)
        for row in tw.catalog_rules(WORLD)['expansions'][58]:
            item=items.get_item_by_name(row['name']);before=copy.deepcopy(save)
            self.assertTrue(themed_land_offers.blocked_offer(item))
            with self.assertRaisesRegex(ValueError,'not restored'):tw.expand(save,item,row['price']['currency'],now=NOW)
            self.assertEqual(save,before)

    def test_score_and_beat_projection_preserves_original_records_and_other_worlds(self):
        original=tw._xml('gameSettings.xml.gz')
        derived=ET.fromstring(zlib.decompress(presentation.game_settings_payload()))
        self.assertEqual(original.find("expansions/expansion[@name='atlantis']").get('score'),'shell')
        self.assertIsNone(derived.find("expansions/expansion[@name='atlantis']").get('score'))
        self.assertEqual(presentation.BEAT_GATES[WORLD],('beatAtlantis','fv_beat_atlantis',1))
        self.assertEqual(presentation.beat_experiment_overrides()['fv_beat_atlantis'],0)
        before=decode('worldScore.amf.gz')
        after=pyamf.get_decoder(pyamf.AMF3,zlib.decompress(presentation.world_score_payload())).readElement()
        tasks=before['worldScoreGlobal']['scores']['score']['task']
        shell=[t for t in tasks if 'shell' in json.dumps(t)]
        self.assertEqual(len(shell),2)
        self.assertEqual({t['action'] for t in shell},{'buyItemByCategory','plantCropByCategory'})
        self.assertTrue(all(presentation.blocked_global_task(t) for t in shell))
        before['worldScoreGlobal']['scores']['score']['task']=[t for t in tasks if not presentation.blocked_global_task(t)]
        self.assertEqual(after,before)
        hud=ET.fromstring(zlib.decompress(market.world_settings_payload())).find("world[@name='atlantis']")
        self.assertIsNotNone(hud.find('hudSkinConfig/showOnlyWorldMarketClassLock'))
        self.assertEqual([b.get('name') for b in hud.findall('actionMenuConfig/button')],['FastTravel'])

class AtlantisGatewayTests(unittest.TestCase):
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
        patcher=mock.patch.object(tw,'ACTIVE_WORLDS',frozenset({WORLD}));patcher.start();self.addCleanup(patcher.stop)
        self.path=self.write_fixture();self.save['world']['objectsArray']=[]
        self.save['userInfo']['player'].update(xp=level_to_xp(20),gold=123456,cash=73)
        creative_worlds.create(self.save,WORLD,'allAccess',now=NOW)
        world_travel.switch(self.save,WORLD,now=NOW);self.persist()

    def test_both_full_bootstraps_close_exact_new_invitations_and_keep_access_open(self):
        with self.client.session_transaction() as session:session['UID']='fixture-farmer'
        gates=('fv_beat_hlights','fv_beat_atlantis','fv_beat_enchanted_glen','fv_hlights_ftue')
        for route in ('/play.html','/ruffle.html'):
            with self.subTest(route=route),mock.patch.object(self.server,'NATIVE_WRAPPER',False),redirect_stdout(io.StringIO()):
                response=self.client.get(route)
            self.assertEqual(response.status_code,200)
            values={name:int(value) for name,value in re.findall(r'"(fv_[A-Za-z0-9_]+)"\s*:\s*(-?\d+)',response.get_data(as_text=True))}
            self.assertEqual({gate:values.get(gate) for gate in gates},{gate:0 for gate in gates})
            for world in ('atlantis','hlights','glen'):
                expected = 1 if world == 'atlantis' else 0
                self.assertEqual(values.get('fv_'+world),expected)
                self.assertEqual(values.get('fv_'+world+'_for_all'),expected)

    def test_crop_plow_plant_first_action_instant_grow_harvest_and_replow(self):
        initial_gold=self.save['userInfo']['player']['gold']
        initial_xp=self.save['userInfo']['player']['xp']
        before_scores=copy.deepcopy(self.save['userInfo']['player'].get('worldScores'))
        snapshot={'id':64010,'className':'Plot','itemName':None,'state':'plowed',
                  'position':{'x':4,'y':4,'z':0}}
        ident=self.send('plow',snapshot)['id']
        snapshot=dict(snapshot,id=ident)
        self.assertEqual(self.save['userInfo']['player']['gold'],initial_gold-15)
        self.send('plow',snapshot)
        self.assertEqual(self.save['userInfo']['player']['gold'],initial_gold-15)
        planted=dict(snapshot,state='planted',itemName='aquamarinerose')
        self.send('place',planted,[{'currency':'coins'}])
        self.assertEqual(self.save['userInfo']['player']['gold'],initial_gold-55)
        with redirect_stdout(io.StringIO()):self.player.load_saves()
        plane={'id':63999,'tempId':-1,'className':'Airplane','itemName':'xalsubmarine',
               'state':'static','position':{'x':33,'y':66,'z':0}}
        self.send('instantGrow',plane,[{'aoeSources':{},'type':1,'autoHarvest':{'autoPPH':False}},{'firstWA':True}])
        self.assertEqual(self.save['userInfo']['player']['cash'],69)
        grown=copy.deepcopy(next(obj for obj in self.save['world']['objectsArray'] if obj['id']==ident))
        self.assertEqual(grown['state'],'grown')
        self.send('harvest',dict(grown,state='fallow'))
        self.assertEqual(self.save['userInfo']['player']['gold'],initial_gold-55+295)
        self.assertGreater(self.save['userInfo']['player']['xp'],initial_xp)
        self.assertEqual(self.save['userInfo']['player'].get('worldScores'),before_scores)
        harvested=copy.deepcopy(next(obj for obj in self.save['world']['objectsArray'] if obj['id']==ident))
        self.send('harvest',harvested)
        self.assertEqual(self.save['userInfo']['player']['gold'],initial_gold-55+295)
        self.send('plow',snapshot)
        self.assertEqual(self.save['userInfo']['player']['gold'],initial_gold-70+295)
        self.send('plow',snapshot)
        self.assertEqual(self.save['userInfo']['player']['gold'],initial_gold-70+295)
        with redirect_stdout(io.StringIO()):self.player.load_saves()
        world_travel.switch(self.save,'farm',now=NOW);world_travel.switch(self.save,WORLD,now=NOW)
        self.assertEqual(next(obj for obj in self.save['world']['objectsArray'] if obj['id']==ident)['state'],'plowed')

    def test_paid_capacity_deposit_disk_reload_travel_withdraw_move_and_sale(self):
        home=copy.deepcopy(self.save['userInfo']['player']['storageData']['-2'])
        self.send('place',capacity.InventoryCapacityTests.shed())
        self.assertEqual(self.save['userInfo']['player']['cash'],51)
        item=items.get_item_by_name('ancientstatue')
        snapshot={'id':64002,'className':item.get('className') or 'Decoration','itemName':'ancientstatue',
                  'state':'horizontal','direction':0,'position':{'x':20,'y':20,'z':0}}
        ident=self.send('place',snapshot)['id']
        self.assertEqual(self.save['userInfo']['player']['cash'],39)
        saved=copy.deepcopy(next(obj for obj in self.save['world']['objectsArray'] if obj['id']==ident))
        self.send('store',saved,[{'storedItemName':'ancientstatue','target':-19,'origin':0,'resource':ident}])
        self.assertEqual(self.save['userInfo']['player']['storageData']['-19'][item['code']],[1,[],[]])
        with redirect_stdout(io.StringIO()):self.player.load_saves()
        world_travel.switch(self.save,'farm',now=NOW);world_travel.switch(self.save,WORLD,now=NOW);self.persist()
        balances=(self.save['userInfo']['player']['gold'],self.save['userInfo']['player']['cash'])
        ident=self.send('place',dict(saved,id=64003),[{'isInventoryWithdrawal':True,'cameFromLocation':-19}])['id']
        self.assertNotIn(item['code'],self.save['userInfo']['player']['storageData']['-19'])
        self.assertEqual((self.save['userInfo']['player']['gold'],self.save['userInfo']['player']['cash']),balances)
        moved=dict(saved,id=ident,position={'x':25,'y':25,'z':0})
        self.send('move',moved);self.send('sell',moved)
        self.assertFalse(any(obj['id']==ident for obj in self.save['world']['objectsArray']))
        self.assertEqual(self.save['userInfo']['player']['storageData']['-2'],home)

    def test_empty_capacity_or_other_world_inventory_rejects_without_state_or_disk_change(self):
        item=items.get_item_by_name('ancientstatue')
        snapshot={'id':64002,'className':item.get('className') or 'Decoration','itemName':'ancientstatue',
                  'state':'horizontal','direction':0,'position':{'x':20,'y':20,'z':0}}
        ident=self.send('place',snapshot)['id'];saved=copy.deepcopy(next(obj for obj in self.save['world']['objectsArray'] if obj['id']==ident))
        self.rejected('store',saved,[{'storedItemName':'ancientstatue','target':-19,'origin':0,'resource':ident}])
        self.send('place',capacity.InventoryCapacityTests.shed())
        self.rejected('store',saved,[{'storedItemName':'ancientstatue','target':-2,'origin':0,'resource':ident}])

    def test_unrestored_feature_and_land_gateway_refusals_preserve_memory_and_disk(self):
        feature=items.get_item_by_name('animal_breeding_observatory')
        snapshot={'id':64011,'className':feature['className'],
                  'itemName':feature['name'],'state':'built',
                  'position':{'x':20,'y':20,'z':0}}
        self.rejected('place',snapshot,[{'currency':'coins'}])
        for name,currency in (('xalfarm14','coins'),('xalfarm14_cash','cash')):
            with self.subTest(offer=name):
                self.assertIsNotNone(items.get_item_by_name(name))
                before,disk=copy.deepcopy(self.save),self.path.read_bytes()
                response=self.gateway([self.command('FarmService.expandFarm',[name,currency])])
                fixtures.assert_gateway_status(self,response,400)
                self.assertEqual(self.save,before)
                self.assertEqual(self.path.read_bytes(),disk)

if __name__=='__main__':unittest.main()
