"""Detached farming transactions, original progression and storage-rule regressions."""
from contextlib import ExitStack, redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence  # noqa: F401  Loads first so FARMVILLAGE_DATA_DIR is set before product modules resolve paths.
import barn_actions as barn
import commands
import game_settings
import items
import progression

NOW = 1_800_000_000
OLD = (NOW - 10 * 82800) * 1000

class BarnActionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.initial = json.loads((ROOT / 'villages/initial.json').read_text())
        cls.settings = game_settings._decode_game_settings((ROOT / 'xml/gz/v855098/gameSettings.xml.gz').read_bytes())
        cls.catalog = [
            {'name':'horse','code':'HO','type':'animal','className':'Animal','growTime':'3','coinYield':'84','baby':'foal',
             'mastery':'true','masteryYield':'1','masteryLevel':[{'count':'2','xp':'5','coins':'50'}]},
            {'name':'clydesdale_black','code':'*4','type':'animal','className':'Animal','growTime':'3','coinYield':'84','stallion':'true','baby':'foal'},
            {'name':'foal','code':'F2','type':'animal','className':'CashGrowableBaby','growTime':'1','coinYield':'80'},
            {'name':'cow','code':'CW','type':'animal','className':'Animal','growTime':'1','coinYield':'6'},
            {'name':'fakehorse','code':'FA','type':'animal','growTime':'1','coinYield':'99'},
            {'name':'apple','code':'AP','type':'tree','className':'Tree','growTime':'3','coinYield':'28','nextLevel':'6A'},
            {'name':'apple2','code':'6A','type':'tree','className':'Tree','growTime':'3','coinYield':'56'},
            {'name':'excludedtree','code':'XT','type':'tree','growTime':'1','coinYield':'1','keywords':'noOrchard'},
            {'name':'unknownGrow','code':'UG','type':'animal','coinYield':'100'},
            {'name':'horsestablewhite','code':'K0','type':'building','className':'HorseStableBuilding','growTime':'1','capacity':'20','storageSize':'1','storageType':{'itemClass':'horses'}},
            {'name':'orchard','code':'wM','type':'building','className':'OrchardConstructionBuilding','finishedName':'orchard_finished','storageType':{'itemClass':'orchard_construct'}},
            {'name':'orchard_finished','code':'wN','type':'building','className':'OrchardBuilding','growTime':'2','capacity':'20','storageType':{'itemClass':'orchard'}},
            *[{'name':name,'code':code,'type':'buildingpart'} for name,code in [('brick','K1'),('nail','K4'),('woodenboard','K5'),('harness','KH'),('horseshoe','KS'),('part_leafblower','PL'),('part_pot','PP'),('part_rake','PR')]],
        ]

    def setUp(self):
        stack = self.stack = ExitStack(); self.addCleanup(stack.close)
        for module,key,value in [(game_settings,'_cached_game_settings',self.settings),(game_settings,'_cached_farming',{}),
                (game_settings,'_xp_level_map',None),(game_settings,'_level_xp_map',None),
                (items,'_cached_items',{'settings':{'items':{'item':self.catalog}}})]:
            stack.enter_context(mock.patch.object(module,key,value))
        game_settings._xp_level_map_init()
        self.save = copy.deepcopy(self.initial); self.save['world']['objectsArray'] = []
        self.player = self.save['userInfo']['player']
        self.player.update(gold=1000,xp=0,cash=5,achievements={},achCounters={},mastery={},masteryCounters={},storageData={})
        progression.ensure_state(self.save)
        stack.enter_context(mock.patch.object(commands,'session',return_value=self.save))
        stack.enter_context(mock.patch.object(commands,'timestamp_now',return_value=NOW))
        stack.enter_context(mock.patch.object(barn.quests,'record_action'))
        stack.enter_context(redirect_stdout(io.StringIO()))

    def obj(self,name,ident,**extra):
        item=items.get_item_by_name(name)
        result={'id':ident,'className':item.get('className','Animal'),'itemName':name,'state':'bare','plantTime':OLD,
                'position':{'x':ident,'y':3},'imported':{'keep':[1,2]}}
        result.update(extra); self.save['world']['objectsArray'].append(result); return result

    def building(self,name='horsestablewhite',ident=10,**extra):
        return self.obj(name,ident,isFullyBuilt=True,contents=[],**extra)

    def apply(self,**operation):
        return barn.apply(self.save,operation,now=NOW)['save']

    def test_inspect_is_readonly_and_uses_original_growth(self):
        self.obj('horse',0); self.obj('horse',1,plantTime=NOW*1000); self.obj('apple',2)
        self.obj('foal',3); self.obj('unknownGrow',4); self.obj('cow',5,deleted=True)
        before=copy.deepcopy(self.save); report=barn.inspect(self.save,NOW)
        self.assertEqual(report['bulk']['animals'],{'total':2,'ready':1,'ids':[0]})
        self.assertEqual(report['bulk']['trees']['ids'],[2]); self.assertEqual(self.save,before)

    def test_bulk_rewards_mastery_and_retries_without_mutating_input(self):
        first=self.obj('horse',1); second=self.obj('horse',2)
        before=copy.deepcopy(self.save)
        result=self.apply(type='bulk_harvest',target='animals')
        player=result['userInfo']['player']
        self.assertEqual(player['gold'],1218)  # 2*84 + original mastery reward50
        self.assertEqual(player['xp'],5); self.assertEqual(player['mastery']['HO'],0)
        self.assertEqual(player['masteryCounters']['HO'],2)
        self.assertNotIn('_progressionResponse',result); self.assertEqual(self.save,before)
        for obj in result['world']['objectsArray']:
            self.assertEqual(obj['state'],'bare'); self.assertEqual(obj['plantTime'],NOW*1000)
            self.assertEqual(obj['imported'],first['imported'])
        again=barn.apply(result,{'type':'bulk_harvest','target':'animals'},NOW)['save']
        self.assertEqual(again,result)

    def test_bulk_tree_yield_and_no_plant_xp(self):
        self.obj('apple',1); result=self.apply(type='bulk_harvest',target='trees')
        self.assertEqual(result['userInfo']['player']['gold'],1028)
        self.assertEqual(result['userInfo']['player']['xp'],0)

    def test_classic_construction_uses_exact_parts_and_preserves_unknown_fields(self):
        obj=self.obj('orchard',0,isFullyBuilt=False,state='construction',contents=[{'itemCode':'K1','numItem':4,'legacy':'yes'}])
        parts=barn.inspect(self.save,NOW)['buildings'][0]['parts']
        self.assertEqual({p['name'] for p in parts},{'brick','nail','woodenboard'})
        result=self.apply(type='building',buildingId=0,action='complete'); built=result['world']['objectsArray'][0]
        self.assertEqual((built['itemName'],built['className']),('orchard_finished','OrchardBuilding'))
        self.assertEqual(built['id'],0); self.assertEqual(built['contents'][0],{'itemCode':'K1','numItem':0,'legacy':'yes'})
        self.assertEqual(built['imported'],obj['imported']); self.assertTrue(built['isFullyBuilt'])
        self.assertEqual(result['userInfo']['player']['gold'],1000)

    def test_stable_load_world_id_zero_and_timer_metadata_roundtrip(self):
        stable=self.building(); horse=self.obj('horse',0)
        result=self.apply(type='building',buildingId=10,action='load',objectId=0)
        built=result['world']['objectsArray'][0]
        self.assertEqual(built['plantTime'],OLD); self.assertEqual(len(result['world']['objectsArray']),1)
        self.assertEqual(result['userInfo']['player']['storageData']['10']['HO'][2][0]['godBarnStoredObject'],horse)
        unloaded=barn.apply(result,{'type':'building','buildingId':10,'action':'unload','itemCode':'HO'},NOW)['save']
        reloaded=barn.apply(unloaded,{'type':'building','buildingId':10,'action':'load','itemCode':'HO','source':'giftbox'},NOW)['save']
        self.assertEqual(reloaded['world']['objectsArray'][0]['plantTime'],OLD)
        self.assertNotIn('HO',reloaded['userInfo']['player']['storageData']['-1'])

    def test_orchard_starts_first_timer_and_keeps_later_timer(self):
        orchard=self.building('orchard_finished'); self.obj('apple',1)
        result=self.apply(type='building',buildingId=10,action='load',objectId=1)
        self.assertEqual(result['world']['objectsArray'][0]['plantTime'],NOW*1000)
        result['world']['objectsArray'].append({'id':2,'className':'Tree','itemName':'apple','plantTime':OLD})
        result=barn.apply(result,{'type':'building','buildingId':10,'action':'load','objectId':2},NOW+60)['save']
        self.assertEqual(result['world']['objectsArray'][0]['plantTime'],NOW*1000)
        self.assertEqual(result['world']['objectsArray'][0]['contents'][0]['numItem'],2)

    def test_exact_allowlist_and_orchard_deny_keyword(self):
        self.building(); self.obj('fakehorse',1)
        with self.assertRaisesRegex(ValueError,'not allowed'): self.apply(type='building',buildingId=10,action='load',objectId=1)
        self.building('orchard_finished',20); self.obj('excludedtree',2)
        with self.assertRaisesRegex(ValueError,'not allowed'): self.apply(type='building',buildingId=20,action='load',objectId=2)

    def test_capacity_counts_unknown_occupants_and_expansion(self):
        obj=self.building(contents_override=True)
        obj.pop('contents_override'); obj['contents']=[{'itemCode':'HO','numItem':20,'custom':5}]
        self.obj('horse',1)
        with self.assertRaisesRegex(ValueError,'capacity'): self.apply(type='building',buildingId=10,action='load',objectId=1)
        obj['expansionLevel']=2
        result=self.apply(type='building',buildingId=10,action='load',objectId=1)
        self.assertEqual(result['world']['objectsArray'][0]['contents'][0],{'itemCode':'HO','numItem':21,'custom':5})
        obj['contents']=[{'itemCode':'MISSING','numItem':20}]
        report=barn.inspect(self.save,NOW)
        self.assertEqual(report['buildings'][0]['count'],20); self.assertTrue(report['warnings'])

    def test_inventory_partial_transfer_preserves_metadata_and_last_unload_state(self):
        obj=self.building(); self.player['storageData']['-1']={'HO':[3,['senderA','senderB'],[{'a':1},{'a':2},{'a':3}],{'legacy':'retained'}]}
        result=self.apply(type='building',buildingId=10,action='load',itemCode='HO',quantity=2)
        data=result['userInfo']['player']['storageData']
        self.assertEqual(data['10']['HO'],[2,['senderA'],[{'a':1},{'a':2}],{'legacy':'retained'}])
        self.assertEqual(data['-1']['HO'],[1,['senderB'],[{'a':3}],{'legacy':'retained'}])
        result=barn.apply(result,{'type':'building','buildingId':10,'action':'unload','itemCode':'HO','quantity':2},NOW)['save']
        self.assertEqual(result['userInfo']['player']['storageData']['-1']['HO'][0],3)
        self.assertEqual(result['world']['objectsArray'][0]['state'],'built')

    def test_destination_overflow_is_atomic(self):
        obj=self.building(); obj['contents']=[{'itemCode':'HO','numItem':1}]
        self.player['storageData']['-1']={'HO':[2147483647,[],[]]}
        before=copy.deepcopy(self.save)
        with self.assertRaisesRegex(ValueError,'Destination quantity'): self.apply(type='building',buildingId=10,action='unload',itemCode='HO')
        self.assertEqual(self.save,before)

    def test_building_harvest_normal_yields_progression_and_timer(self):
        obj=self.building(); obj['contents']=[{'itemCode':'HO','numItem':2,'custom':9}]
        result=self.apply(type='building',buildingId=10,action='harvest')
        self.assertEqual(result['userInfo']['player']['gold'],1218)
        self.assertEqual(result['world']['objectsArray'][0]['contents'],obj['contents'])
        self.assertEqual(result['world']['objectsArray'][0]['plantTime'],NOW*1000)
        with self.assertRaisesRegex(ValueError,'not ready'): barn.apply(result,{'type':'building','buildingId':10,'action':'harvest'},NOW)

    def test_reward_overflow_rejects_without_partial_mutation(self):
        self.obj('horse',1); self.player['gold']=2147483640; before=copy.deepcopy(self.save)
        with self.assertRaisesRegex(ValueError,'Resulting gold'): self.apply(type='bulk_harvest',target='animals')
        self.assertEqual(self.save,before)

    def test_stable_offspring_requires_exact_parent_and_stallion(self):
        obj=self.building(); obj['contents']=[{'itemCode':'HO','numItem':1}]
        self.assertEqual(barn.inspect(self.save,NOW)['buildings'][0]['offspring'],[])
        with self.assertRaisesRegex(ValueError,'supported'): self.apply(type='building',buildingId=10,action='offspring',itemCode='F2')
        obj['contents'].append({'itemCode':'*4','numItem':1})
        result=self.apply(type='building',buildingId=10,action='offspring',itemCode='F2')
        self.assertEqual(result['userInfo']['player']['storageData']['-1']['F2'][0],1)
        # 168 occupant coins plus the original two-animal-type ribbon reward.
        self.assertEqual(result['userInfo']['player']['gold'],1668)
        self.assertEqual(result['world']['objectsArray'][0]['plantTime'],NOW*1000)

    def test_orchard_offspring_resolves_nextlevel_as_code(self):
        obj=self.building('orchard_finished'); obj['contents']=[{'itemCode':'AP','numItem':1}]
        self.assertEqual(barn.inspect(self.save,NOW)['buildings'][0]['offspring'][0]['itemName'],'apple2')
        result=self.apply(type='building',buildingId=10,action='offspring',itemCode='6A')
        self.assertEqual(result['userInfo']['player']['storageData']['-1']['6A'][0],1)
        self.assertEqual(result['userInfo']['player']['gold'],1028)

    def test_original_client_empty_snapshot_move_does_not_erase_occupants(self):
        obj=self.building(); obj['contents']=[{'itemCode':'HO','numItem':1,'legacy':{'k':8}}]
        commands.world_perform_action('fixture','move',{'id':10,'itemName':'horsestablewhite','className':'HorseStableBuilding','contents':[], 'position':{'x':5,'y':5}},[])
        self.assertEqual(self.save['world']['objectsArray'][0]['contents'],obj['contents'])
        self.assertEqual(self.save['world']['objectsArray'][0]['imported'],obj['imported'])

    def test_original_client_building_harvest_pays_once_and_keeps_goal_envelope(self):
        obj=self.building(); obj['contents']=[{'itemCode':'HO','numItem':2}]
        packet={'id':10,'itemName':'horsestablewhite','className':'HorseStableBuilding','contents':[],'state':'ripe','plantTime':OLD}
        commands.world_perform_action('fixture','harvest',copy.deepcopy(packet),[])
        self.assertEqual(self.player['gold'],1218); self.assertIn('_progressionResponse',self.save)
        commands.world_perform_action('fixture','harvest',copy.deepcopy(packet),[])
        self.assertEqual(self.player['gold'],1218); self.assertEqual(obj['plantTime'],NOW*1000)
        self.assertEqual(obj['contents'],[{'itemCode':'HO','numItem':2}])

    def test_unknown_class_import_and_strict_schema_are_safe(self):
        self.save['world']['objectsArray']=[{'id':0,'className':'HorseStableBuilding','itemName':'missing'}]
        self.assertEqual(barn.inspect(self.save,NOW)['buildings'],[])
        with self.assertRaisesRegex(ValueError,'unexpected'): self.apply(type='bulk_harvest',target='animals',surprise=True)
        self.building()
        with self.assertRaisesRegex(ValueError,'Quantity'): self.apply(type='building',buildingId=10,action='load',quantity=True)

    def test_unflagged_stable_defaults_incomplete_and_oversized_import_cannot_harvest(self):
        obj=self.obj('horsestablewhite',0,contents=[])
        self.assertFalse(barn.inspect(self.save,NOW)['buildings'][0]['built'])
        obj.update(isFullyBuilt=True,contents=[{'itemCode':'HO','numItem':2147483647}])
        before=copy.deepcopy(self.save)
        with self.assertRaisesRegex(ValueError,'capacity'): self.apply(type='building',buildingId=0,action='harvest')
        self.assertEqual(self.save,before)

if __name__=='__main__': unittest.main()
