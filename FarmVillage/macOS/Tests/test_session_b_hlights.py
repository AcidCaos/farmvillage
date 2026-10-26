"""Holiday Lights candidate checks; run only in the marked disposable runtime."""
import copy
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path
import test_themed_worlds as common
import test_themed_inventory as inventory
import themed_worlds as tw
import themed_client_presentation as presentation
import items


class HlightsContractTests(unittest.TestCase):
    def test_xml_storage_conflict_and_disclosed_bounded_record(self):
        original = tw._xml('gameSettings.xml.gz').find("expansions/expansion[@name='hlights']")
        self.assertEqual(original.get('storageId'), '-24')
        record = tw.recovered_record('hlights')
        self.assertEqual((record['storageId'],record['tileSet'],record['score']),(-25,'hlights_theme',None))
        self.assertEqual((record['admittedItems'],record['unpricedItems'],len(record['allowedSeeds'])),(214,0,32))
        self.assertEqual(record['expansionAddedObjects'],37)

    def test_xml_drift_does_not_silently_normalize_conflicting_storage(self):
        original = tw._xml
        def changed(name):
            root=original(name)
            if name=='gameSettings.xml.gz':root.find("expansions/expansion[@name='hlights']").set('storageId','-25')
            return root
        tw.recovered_rules.cache_clear()
        try:
            with mock.patch.object(tw,'_xml',side_effect=changed),self.assertRaisesRegex(ValueError,'world record'):
                tw.recovered_rules('hlights')
        finally:tw.recovered_rules.cache_clear()

    def test_other_world_claims_and_orphan_ledgers_are_preserved_on_rejection(self):
        for ident in (-25,'-25','-2.5e1'):
            save=common.base_save();save['userInfo']['worldSummaryData']['unrestored-import']={'storageId':ident,'keep':[1]}
            before=copy.deepcopy(save)
            with self.subTest(ident=ident),self.assertRaises(ValueError):tw.create(save,'hlights',now=common.NOW)
            self.assertEqual(save,before)
        save=common.base_save();save['userInfo']['player']['storageData']['-25']={'imported':[1,['sender'],[{'keep':1}]]}
        before=copy.deepcopy(save)
        with self.assertRaises(ValueError):tw.create(save,'hlights',now=common.NOW)
        self.assertEqual(save,before)

    def test_exact_score_and_beat_presentation_projection(self):
        self.assertEqual(presentation.beat_experiment_overrides()['fv_beat_hlights'],0)
        projected=ET.fromstring(zlib.decompress(presentation.game_settings_payload())).find("expansions/expansion[@name='hlights']")
        self.assertIsNone(projected.get('score'))
        self.assertEqual(projected.get('scoreFile'),'worldScoreHlights.xml')
        import pyamf
        original=pyamf.get_decoder(pyamf.AMF3,zlib.decompress(presentation.SCORE_SOURCE.read_bytes())).readElement()
        filtered=pyamf.get_decoder(pyamf.AMF3,zlib.decompress(presentation.world_score_payload())).readElement()
        self.assertEqual(len(original['worldScoreGlobal']['scores']['score']['task'])-len(filtered['worldScoreGlobal']['scores']['score']['task']),42)
        def score_writers(value):
            if isinstance(value,dict):
                for k,v in value.items():
                    if 'score' in k.lower() and v not in tw.NONE_VALUES:yield(k,v)
                    if isinstance(v,str) and v in ('world_score','unlock_world_score'):yield(k,v)
                    yield from score_writers(v)
            elif isinstance(value,list):
                for v in value:yield from score_writers(v)
        for name in tw.catalog_rules('hlights')['items']:
            self.assertEqual(list(score_writers(items.get_item_by_name(name))),[],name)


class HlightsGatewayTests(unittest.TestCase):
    setUpClass=classmethod(inventory.ThemedInventoryTests.setUpClass.__func__)
    def setUp(self):
        # Archived contract test only; this never activates production release worlds.
        inventory.ThemedInventoryTests.setUp(self)
        experiments=mock.patch.object(tw,'served_experiments',return_value=common.dormant_experiments())
        experiments.start();self.addCleanup(experiments.stop)
        active=mock.patch.object(tw,'ACTIVE_WORLDS',tw.ACTIVE_WORLDS | {'hlights'})
        active.start();self.addCleanup(active.stop)
    fixture=inventory.ThemedInventoryTests.fixture
    write_fixture=inventory.ThemedInventoryTests.write_fixture
    command=staticmethod(inventory.ThemedInventoryTests.command)
    gateway_payload=inventory.ThemedInventoryTests.gateway_payload
    gateway=inventory.ThemedInventoryTests.gateway
    save=inventory.ThemedInventoryTests.save
    persist=inventory.ThemedInventoryTests.persist
    send=inventory.ThemedInventoryTests.send
    rejected=inventory.ThemedInventoryTests.rejected
    shed=staticmethod(inventory.ThemedInventoryTests.shed)
    prepare=inventory.ThemedInventoryTests.prepare

    def test_purchase_store_disk_reload_home_roundtrip_and_withdraw(self):
        names=[n for n,r in tw.catalog_rules('hlights')['items'].items() if r['type']=='decoration']
        name=common.ActivatedHlightsTests('test_travel_round_trip_and_reload').purchasable(names)
        with mock.patch.object(inventory,'DECORATIONS',{'hlights':name}):
            inventory.ThemedInventoryTests.test_five_candidate_gateway_purchase_store_withdraw_reload_and_travel(self)

    def test_empty_inventory_has_no_assumed_capacity(self):
        with mock.patch.object(tw,'ACTIVE_WORLDS',{'hlights'}):
            self.prepare('hlights')
            self.assertEqual(self.group,-25)
            import storage
            before=copy.deepcopy(self.save)
            with self.assertRaisesRegex(ValueError,'storage space'):storage._guard_inventory_deposit(self.save,-25,1)
            self.assertEqual(self.save,before)

    def test_crop_first_action_after_reload_instant_grow_harvest_and_replow(self):
        from contextlib import redirect_stdout
        import io
        with mock.patch.object(tw,'ACTIVE_WORLDS',{'hlights'}):
            self.prepare('hlights')
            before=copy.deepcopy(self.save['userInfo']['player'])
            snapshot={'id':64010,'className':'Plot','itemName':None,'state':'plowed',
                      'position':{'x':4,'y':4,'z':0}}
            ident=self.send('plow',snapshot)['id']
            snapshot=dict(snapshot,id=ident)
            self.assertEqual(self.save['userInfo']['player']['gold'],before['gold']-15)
            self.send('plow',snapshot)
            self.assertEqual(self.save['userInfo']['player']['gold'],before['gold']-15)
            self.send('place',dict(snapshot,state='planted',itemName='xhl_santaberries'),[{'currency':'coins'}])
            self.assertEqual(self.save['userInfo']['player']['gold'],before['gold']-120)
            with redirect_stdout(io.StringIO()):self.player.load_saves()
            plane={'id':63999,'tempId':-1,'className':'Airplane','itemName':'xhlbiplane',
                   'state':'static','position':{'x':33,'y':66,'z':0}}
            self.send('instantGrow',plane,[{'aoeSources':{},'type':1,'autoHarvest':{'autoPPH':False}},{'firstWA':True}])
            self.assertEqual(self.save['userInfo']['player']['cash'],before['cash']-4)
            grown=copy.deepcopy(next(x for x in self.save['world']['objectsArray'] if x['id']==ident))
            self.assertEqual(grown['state'],'grown')
            self.send('harvest',dict(grown,state='fallow'))
            self.assertEqual(self.save['userInfo']['player']['gold'],before['gold']-120+155)
            self.assertEqual(self.save['userInfo']['player'].get('worldScores'),before.get('worldScores'))
            harvested=copy.deepcopy(next(x for x in self.save['world']['objectsArray'] if x['id']==ident))
            self.send('harvest',harvested)
            self.assertEqual(self.save['userInfo']['player']['gold'],before['gold']-120+155)
            self.send('plow',snapshot)
            self.send('plow',snapshot)
            self.assertEqual(self.save['userInfo']['player']['gold'],before['gold']-135+155)
