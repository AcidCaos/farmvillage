"""W05 positive containers; signed AMF on disposable synthetic saves only."""
import copy
from contextlib import redirect_stdout
import io
import json
import os
import subprocess
from pathlib import Path
import sys
import unittest
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import test_cove_cellar as cellar
import creative_worlds, game_settings, items, peaceful, storage, world_travel
NOW = 1800000000

class RainforestContainerWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway
    save = cellar.CoveCellarTests.save
    persist = cellar.CoveCellarTests.persist
    def prepare(self):
        self.path = self.write_fixture(); self.save['world']['objectsArray'] = []
        self.save['userInfo']['player'].update(xp=game_settings.level_to_xp(100), gold=10000000, cash=1000)
        creative_worlds.create(self.save, 'rainforest', 'allAccess', now=NOW)
        world_travel.switch(self.save, 'rainforest', now=NOW); self.persist()
    def obj(self, ident):
        return next(obj for obj in self.save['world']['objectsArray'] if obj['id'] == ident)
    @staticmethod
    def snapshot(name, ident=64001, x=4, y=4):
        item = items.get_item_by_name(name)
        return {'id':ident, 'itemName':name, 'className':item.get('className') or {'tree':'Tree','animal':'Animal'}.get(item['type']),
                'state':'built', 'position':{'x':x,'y':y,'z':0}, 'contents':[], 'expansionLevel':999,
                'capacity':99999, 'plantTime':0, 'direction':0}
    def send(self, action, snapshot, params=(), sequence=1, now=NOW, expected=200):
        with mock.patch('server.timestamp_now', return_value=now), mock.patch('commands.timestamp_now', return_value=now), mock.patch('engine.timestamp_now', return_value=now):
            result = self.gateway([self.command('WorldService.performAction', [action,copy.deepcopy(snapshot),list(params)],sequence)])

        if expected == 200:
            from pyamf import remoting
            body=remoting.decode(result.data).bodies[0][1].body
            self.assertEqual(body['data'][0].get('errorType'),0,body)
        fixtures.assert_gateway_status(self,result,expected)
        if expected == 200:
            from pyamf import remoting
            return remoting.decode(result.data).bodies[0][1].body['data'][0]['data']
    def reject(self, action, snapshot, params=(), sequence=1, now=NOW):
        before,disk=copy.deepcopy(self.save),self.path.read_bytes()
        self.send(action,snapshot,params,sequence,now,400)
        self.assertEqual(self.save,before); self.assertEqual(self.path.read_bytes(),disk)
    def gift(self,name,quantity=1,extras=None):
        item=items.get_item_by_name(name)
        self.save['userInfo']['player']['storageData'].setdefault('-1',{})[item['code']]=[quantity,['fixture-sender'],copy.deepcopy(extras or [])]
        self.persist(); return item
    def reload_travel(self):
        accepted=copy.deepcopy(self.save)
        with redirect_stdout(io.StringIO()): self.player.load_saves()
        world_travel.clear_temporary_ids(accepted)
        self.assertEqual(self.save,accepted)
        world=copy.deepcopy(self.save['world'])
        world_travel.switch(self.save,'farm',now=NOW); world_travel.switch(self.save,'rainforest',now=NOW)
        self.assertEqual(self.save['world'],world)
    def test_exact_finished_prices_default_gnome_retry_reload_and_travel(self):
        self.prepare(); snap=self.snapshot('xrf_gnomegarden_finished')
        ident=self.send('place',snap)['id']; owner=self.obj(ident)
        self.assertEqual(self.save['userInfo']['player']['cash'],964)
        self.assertEqual((owner['expansionLevel'],storage._feature_capacity(owner,items.get_item_by_name(owner['itemName']))),(1,10))
        code=items.get_item_by_name('gnome_xrf_headdresstte')['code']
        self.assertEqual(owner['contents'],[{'itemCode':code,'numItem':1}])
        self.assertNotIn(code,self.save['userInfo']['player']['storageData'].get('-1',{}))
        self.send('place',snap)
        self.assertEqual(self.save['userInfo']['player']['cash'],964)
        self.assertEqual(self.obj(ident)['contents'],[{'itemCode':code,'numItem':1}])
        orchard=self.send('place',self.snapshot('xrforchard_finished',64002,20,5),sequence=2)['id']
        self.assertEqual(self.save['userInfo']['player']['cash'],934)
        self.assertEqual((self.obj(orchard)['plantTime'],self.obj(orchard)['state']),(NOW*1000,'bare'))
        self.reload_travel()
    def test_gnome_full_capacity_actual_metadata_retry_withdraw_and_overflow_recovery(self):
        self.prepare(); ident=self.send('place',self.snapshot('xrf_gnomegarden_finished'))['id']
        extras=[{'fixtureUnit':i} for i in range(9)]
        gnome=self.gift('gnome_xrf_headdresstte',10,extras)
        opts=[{'storedItemName':gnome['name'],'isGift':True,'numToStore':9,'metadata':{'forgedUnit':True}}]
        snapshot=copy.deepcopy(self.obj(ident)); self.send('store',snapshot,opts,sequence=20)
        self.assertEqual(self.obj(ident)['contents'],[{'itemCode':gnome['code'],'numItem':10}])
        ledger=self.save['userInfo']['player']['storageData']
        self.assertEqual(ledger[str(ident)][gnome['code']][2],extras[:8]); self.assertEqual(ledger['-1'][gnome['code']][2],extras[8:])
        before=copy.deepcopy(self.save); self.send('store',snapshot,opts,sequence=20); self.assertEqual(self.save,before)
        self.reject('store',self.obj(ident),[{'storedItemName':gnome['name'],'isGift':True}],sequence=21)
        withdrawal=self.snapshot(gnome['name'],64003,30,30); withdrawal['metadata']={'forgedUnit':True}
        placed=self.send('place',withdrawal,[{'isStorageWithdrawal':ident}],sequence=22)['id']
        self.assertNotEqual(self.obj(placed).get('metadata'),{'forgedUnit':True})
        self.assertEqual(self.obj(ident)['contents'][0]['numItem'],9)
        # Imported overflow is a seeded recovery fixture, not earned capacity.
        self.obj(ident)['contents'][0].update(numItem=11, importedRow={'keep':True})
        self.save['userInfo']['player']['storageData'][str(ident)][gnome['code']][0]=11
        self.persist()
        self.send('place',self.snapshot(gnome['name'],64004,34,30),[{'isStorageWithdrawal':ident}],sequence=23)
        self.assertEqual(self.obj(ident)['contents'][0],{'itemCode':gnome['code'],'numItem':10,'importedRow':{'keep':True}})
        self.reload_travel()
    def test_all_five_authored_gnome_material_tiers_and_final_limit(self):
        self.prepare()
        ident = self.send('place', self.snapshot('xrf_gnomegarden_finished'), sequence=1000)['id']
        occupant = copy.deepcopy(self.obj(ident)['contents'])
        sequence = 1000
        for level, capacity, count in ((2,25,14),(3,50,16),(4,75,18),(5,100,22),(6,500,24)):
            for name in ('part_toadstool','part_tinywindow','part_gardenfence'):
                self.gift(name, count)
                sequence += 1
                snapshot = copy.deepcopy(self.obj(ident))
                options = [{'storedItemName':name,'isGift':True,'numToStore':count}]
                self.send('store', snapshot, options, sequence=sequence)
            self.assertEqual((self.obj(ident)['expansionLevel'],self.obj(ident)['capacity']), (level,capacity))
            self.assertEqual(self.obj(ident)['contents'],occupant)
            self.assertEqual(self.obj(ident)['expansionParts'],{})
            accepted, disk = copy.deepcopy(self.save), self.path.read_bytes()
            self.send('store', snapshot, options, sequence=sequence)
            self.assertEqual(self.save,accepted)
            self.assertEqual(self.path.read_bytes(),disk)
        self.assertEqual(self.save['userInfo']['player']['cash'],964)
        self.gift('part_toadstool')
        self.reject('store',self.obj(ident),[{'storedItemName':'part_toadstool','isGift':True}],sequence=sequence+1)
        self.reload_travel()
    def test_orchard_original_two_day_clock_base_coins_metadata_and_retries(self):
        self.prepare(); ident=self.send('place',self.snapshot('xrforchard_finished'))['id']
        tree=self.gift('xrf_achiotetree',2,[{'sourceVariant':'one'},{'sourceVariant':'two'}])
        self.send('store',self.obj(ident),[{'storedItemName':tree['name'],'isGift':True,'numToStore':2,'metadata':{'forged':True}}],sequence=30)
        self.assertEqual(self.obj(ident)['plantTime'],NOW*1000)
        self.assertEqual(self.save['userInfo']['player']['storageData'][str(ident)][tree['code']][2],[{'sourceVariant':'one'},{'sourceVariant':'two'}])
        grow=peaceful.grow_seconds(items.get_item_by_name('xrforchard_finished')); self.assertEqual(grow,165600)
        self.reject('harvest',self.obj(ident),sequence=31,now=NOW+grow-2)
        gold=self.save['userInfo']['player']['gold']; self.send('harvest',self.obj(ident),sequence=32,now=NOW+grow)
        self.assertEqual(self.save['userInfo']['player']['gold'],gold+300)
        self.assertEqual((self.obj(ident)['plantTime'],self.obj(ident)['state']),((NOW+grow)*1000,'bare'))
        self.send('harvest',self.obj(ident),sequence=32,now=NOW+grow)
        self.assertEqual(self.save['userInfo']['player']['gold'],gold+300); self.reload_travel()
    def test_orchard_twenty_slot_full_refusal_withdraw_refill_and_metadata(self):
        self.prepare()
        ident = self.send('place',self.snapshot('xrforchard_finished'),sequence=1100)['id']
        extras = [{'treeUnit':index} for index in range(21)]
        tree = self.gift('xrf_achiotetree',21,extras)
        clock = self.obj(ident)['plantTime']
        self.send('store',self.obj(ident),[{'storedItemName':tree['name'],'isGift':True,'numToStore':20}],sequence=1101)
        ledger = self.save['userInfo']['player']['storageData']
        self.assertEqual(ledger[str(ident)][tree['code']][0],20)
        self.assertEqual(ledger[str(ident)][tree['code']][2],extras[:20])
        self.reject('store',self.obj(ident),[{'storedItemName':tree['name'],'isGift':True}],sequence=1102)
        packet = self.snapshot(tree['name'],64070,30,30)
        packet['metadata'] = {'forged':'full-capacity-withdrawal'}
        placed = self.send('place',packet,[{'isStorageWithdrawal':ident}],sequence=1103)['id']
        self.assertEqual(self.obj(placed)['metadata'],extras[0])
        self.send('store',self.obj(ident),[{'storedItemName':tree['name'],'isGift':True}],sequence=1104)
        ledger = self.save['userInfo']['player']['storageData']
        self.assertEqual(ledger[str(ident)][tree['code']][0],20)
        self.assertEqual(ledger[str(ident)][tree['code']][2],extras[1:])
        self.assertNotIn(tree['code'],ledger['-1'])
        self.assertEqual(self.obj(ident)['plantTime'],clock)
        self.reload_travel()
    def test_orchard_materials_30_40_capacity_owned_super_transform_without_free_market(self):
        self.prepare(); ident=self.send('place',self.snapshot('xrforchard_finished'))['id']
        for name in ('part_leafblower','part_pot','part_rake'): self.gift(name,20)
        clock=self.obj(ident)['plantTime']; sequence=40
        for level,capacity in ((2,30),(3,40)):
            for name in ('part_leafblower','part_pot','part_rake'):
                sequence+=1; opts=[{'storedItemName':name,'isGift':True,'numToStore':10}]; snapshot=copy.deepcopy(self.obj(ident))
                self.send('store',snapshot,opts,sequence=sequence)
                before=copy.deepcopy(self.save); self.send('store',snapshot,opts,sequence=sequence); self.assertEqual(self.save,before)
            self.assertEqual((self.obj(ident)['expansionLevel'],self.obj(ident)['capacity']),(level,capacity))
            self.assertEqual(self.obj(ident)['plantTime'],clock)
        self.assertEqual(self.obj(ident)['itemName'],'superorchard_featurebuilding')
        self.reject('place',self.snapshot('superorchard_featurebuilding',64003,20,5),sequence=60); self.reload_travel()
    def test_populated_owner_move_preserves_progress_and_destructive_storage_paths_refuse(self):
        self.prepare(); ident=self.send('place',self.snapshot('xrf_gnomegarden_finished'))['id']
        saved=copy.deepcopy(self.obj(ident)); forged=copy.deepcopy(saved)
        forged.update(contents=[], expansionLevel=999, capacity=99999, expansionParts={})
        forged['position']={'x':20,'y':20,'z':0}
        self.send('move',forged,sequence=80)
        self.assertEqual(self.obj(ident)['contents'],saved['contents'])
        self.assertEqual(self.obj(ident)['expansionLevel'],saved['expansionLevel'])
        self.reject('sell',self.obj(ident),sequence=81); self.reject('clear',self.obj(ident),sequence=82)
        self.reject('store',self.obj(ident),[{'storedItemName':'xrf_gnomegarden_finished','target':-26,'resource':ident,'origin':0}],sequence=83)

    def test_fresh_process_reload_preserves_purchased_container_contents_and_clock(self):
        self.prepare(); ident=self.send('place',self.snapshot('xrforchard_finished'))['id']
        tree=self.gift('xrf_achiotetree',1,[{'restartVariant':'keep'}])
        self.send('store',self.obj(ident),[{'storedItemName':tree['name'],'isGift':True}],sequence=90)
        expected=copy.deepcopy(self.save); world_travel.clear_temporary_ids(expected)
        program="import player,json,sys; player.SAVES_DIR=sys.argv[1]; player.load_saves(); print(json.dumps(player.session('fixture-farmer'),sort_keys=True))"
        child=subprocess.run([sys.executable,'-B','-c',program,str(self.saves)],cwd=fixtures.ROOT,
            env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','FARMVILLAGE_DATA_DIR':str(self.saves.parent)},
            capture_output=True,text=True,timeout=30)
        self.assertEqual(child.returncode,0,child.stderr)
        recovered=json.loads(child.stdout.splitlines()[-1]); self.assertEqual(recovered,expected)

    def test_owned_fountain_visual_only_and_unrecovered_frames_stay_atomic(self):
        self.prepare(); fountain=self.snapshot('xrf_fountainofyouth'); self.reject('place',fountain)
        self.gift('xrf_fountainofyouth'); ident=self.send('place',fountain,[{'isGift':True}],sequence=70)['id']
        self.assertEqual(self.save['userInfo']['player']['cash'],1000)
        self.reject('harvest',self.obj(ident),sequence=71); self.reject('CompleteNow',self.obj(ident),sequence=72)
        for name in ('xrf_hiddenpalace','xrf_gnomegarden','xrforchard','xrf_treasure_s', *[f'animal_breeding_xrf{name}_finished' for name in ('aviary','dairy','horsepaddock','livestock','petrun','wildlife','zoo')]):
            self.reject('place',self.snapshot(name,64004,20,5),sequence=73)
        self.reload_travel()

if __name__=='__main__': unittest.main()
