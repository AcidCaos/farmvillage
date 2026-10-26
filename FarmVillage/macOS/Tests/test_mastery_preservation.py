"""Stable gift definitions under the reviewed private three-world reservation."""
from contextlib import ExitStack, contextmanager, redirect_stdout
import copy
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import pyamf
import client_catalog
import creative_worlds
import heritage_pricing
import items
import mastery_signs
import peaceful
import persistence
import progression
import themed_worlds as tw
import themed_market_presentation
import world_travel

ROOT = Path(__file__).resolve().parents[2]

def decode(raw):
    return pyamf.get_decoder(pyamf.AMF3,zlib.decompress(raw)).readElement()

RAW = decode(Path(items.ITEMS_AMF).read_bytes())['settings']['items']['item']
BEFORE = json.loads((ROOT/'macOS/Tests/Fixtures/mastery-signs-legacy155.json').read_text())
OWNERS = {row['code']:row for row in RAW}
# Original reviewed archive contracts, installed only in reversible test scopes.
CANDIDATE_SPECS = {'hlights': {'name': 'Holiday Lights',
             'prefix': 'xlg',
             'storageId': -25,
             'xmlStorageId': -24,
             'theme': 'hlights_theme'},
 'atlantis': {'name': 'Atlantis',
              'prefix': 'xal',
              'storageId': -19,
              'xmlStorageId': None,
              'xmlPrefix': None,
              'xmlTheme': None,
              'theme': 'atlantis_theme',
              'localThemeChoice': True,
              'landGatePrefixes': ('fv_atlantis_farm', 'fv_xal_farm')},
 'glen': {'name': 'Enchanted Glen',
          'prefix': 'xeg',
          'storageId': -18,
          'xmlStorageId': None,
          'xmlPrefix': None,
          'xmlTheme': None,
          'theme': 'glen_theme',
          'localThemeChoice': True,
          'landGatePrefixes': ('fv_glen_farm', 'fv_xeg_farm')}}
_PRODUCTION_SPECS = copy.deepcopy(tw.SPECS)
_PRODUCTION_ACTIVE = tw.ACTIVE_WORLDS
_PRODUCTION_RESERVED = heritage_pricing.RESERVED_WORLDS
LOST = {row['name']:row for row in BEFORE['definitions']
        if set(heritage_pricing._world_names(OWNERS[row['masteredItemCode']])) & set(CANDIDATE_SPECS)}
AFTER = {'definitions':[row for row in BEFORE['definitions'] if row['name'] not in LOST]}
NOW = 2_000_000_000


def clear_policy_caches():
    for function in (tw.catalog_rules, tw.recovered_rules, tw.expansion_additions,
                     tw.served_experiments, themed_market_presentation._admissions,
                     themed_market_presentation.class_locks):
        function.cache_clear()
    client_catalog._cache.clear()


@contextmanager
def candidate_worlds(*, reload_items=False):
    """Exercise future contracts without registering or activating production."""
    state = {name:getattr(items,name) for name in
             ('_cached_items','_indexed_catalog','_items_by_name','_items_by_code')}
    heritage_state = (heritage_pricing._overlaid, heritage_pricing._refused)
    stack = ExitStack()
    try:
        stack.enter_context(mock.patch.object(tw,'SPECS',{**tw.SPECS,**CANDIDATE_SPECS}))
        stack.enter_context(mock.patch.object(tw,'ACTIVE_WORLDS',tw.ACTIVE_WORLDS | CANDIDATE_SPECS.keys()))
        stack.enter_context(mock.patch.object(heritage_pricing,'RESERVED_WORLDS',
                                              heritage_pricing.RESERVED_WORLDS | CANDIDATE_SPECS.keys()))
        clear_policy_caches()
        import test_themed_worlds as common
        stack.enter_context(mock.patch.object(tw,'served_experiments',return_value=common.dormant_experiments()))
        if reload_items:
            with redirect_stdout(io.StringIO()):items.load_items()
        yield
    finally:
        stack.close()
        if reload_items:
            for name,value in state.items():setattr(items,name,value)
            heritage_pricing._overlaid,heritage_pricing._refused = heritage_state
        clear_policy_caches()


def themed_crop_rows():
    rows=[]
    for world in ('hlights','atlantis','glen'):
        for name,rule in tw.catalog_rules(world)['items'].items():
            if rule['type']!='seed':continue
            crop=items.get_item_by_name(name)
            rows.append({'world':world,'name':name,'code':crop['code'],
                         'gifts':[level.get('gift') for level in crop.get('masteryLevel',[]) if level.get('gift')]})
    return rows



class PreservationCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policies = ExitStack()
        cls.addClassCleanup(cls.policies.close)
        cls.policies.enter_context(candidate_worlds())

    def test_exact49_loss_and_every155_legacy_field_is_preserved(self):
        self.assertEqual((len(BEFORE['definitions']),len(AFTER['definitions']),len(LOST)),(155,106,49))
        before={r['name']:r for r in BEFORE['definitions']}
        self.assertTrue(all(row==before[row['name']] for row in AFTER['definitions']))
        actual=mastery_signs.derive(copy.deepcopy(RAW))
        self.assertEqual(actual[:155],BEFORE['definitions'])
        self.assertEqual(len(actual),len(mastery_signs.DEFINITION_GIFTS))
        self.assertEqual(len(actual),155 if not hasattr(mastery_signs,'GLEN_GIFTS') else 167)

    def test_original_ladders_art_and_gift_only_fields_are_source_backed(self):
        root=Path(__file__).resolve().parents[2]
        hashes=decode((root/'assethash/v9/assethash.master.amf.gz').read_bytes())
        for row in mastery_signs.derive(RAW):
            crop=OWNERS[row['masteredItemCode']]
            self.assertIn(row['name'],[level.get('gift') for level in crop.get('masteryLevel',[])])
            self.assertEqual((row['buyable'],row['giftable'],row['className']),('false','false','DynamicMasterySign'))
            self.assertFalse({'cost','cash','requirements','marketEntries'} & row.keys())
            icon=next(image['url'] for image in crop['image'] if image['name']=='icon')
            self.assertEqual(next(image['url'] for image in row['image'] if image['name']=='masteredItem'),icon)
            for image in row['image']:
                _,group,filename=image['url'].split('/',2)
                self.assertIn(filename,hashes[group])

    def test_append_only_and_existing_authored_definition_wins(self):
        records=copy.deepcopy(RAW)
        expected=mastery_signs.derive(records)
        self.assertEqual(mastery_signs.apply(records),len(expected))
        self.assertEqual(records[:len(RAW)],RAW)
        self.assertEqual(mastery_signs.apply(records),0)
        self.assertEqual(records[len(RAW):],expected)
        crop=copy.deepcopy(OWNERS[LOST['masterbubblebeans']['masteredItemCode']])
        authored={'name':'masterbubblebeans','code':'original-sign','className':'OriginalSign','opaque':[1]}
        self.assertEqual(mastery_signs.derive([crop,authored]),[])
        self.assertEqual(authored,{'name':'masterbubblebeans','code':'original-sign','className':'OriginalSign','opaque':[1]})
        for change in ({'code':'not-pinned'},{'type':'animal'},{'className':'SpecialPlot'}):
            self.assertEqual(mastery_signs.derive([dict(crop,**change)]),[])
        forged=copy.deepcopy(crop)
        forged['masteryLevel'][-1]['gift']='unreviewed-gift'
        self.assertEqual(mastery_signs.derive([forged]),[])

    def test_definition_policy_is_independent_of_home_purchase_policy(self):
        digest=mastery_signs.policy_digest()
        with mock.patch.object(heritage_pricing,'overlay_digest',side_effect=AssertionError('definition policy read market digest')):
            self.assertEqual(mastery_signs.policy_digest(),digest)
            self.assertEqual(mastery_signs.derive(RAW),mastery_signs.derive(RAW))
        self.assertTrue({'hlights','atlantis','glen'} <= heritage_pricing.RESERVED_WORLDS)


class PreservationWireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.RuntimeFixtureTests.setUpClass.__func__(cls)
        cls.policies = ExitStack()
        cls.addClassCleanup(cls.policies.close)
        cls.policies.enter_context(candidate_worlds(reload_items=True))

    setUp=fixtures.RuntimeFixtureTests.setUp
    fixture=fixtures.RuntimeFixtureTests.fixture
    write_fixture=fixtures.RuntimeFixtureTests.write_fixture
    command=staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload=fixtures.RuntimeFixtureTests.gateway_payload
    gateway=fixtures.RuntimeFixtureTests.gateway

    @property
    def save(self):return self.player.session('fixture-farmer')

    def prepare(self,world='farm'):
        self.path=self.write_fixture()
        import game_settings
        self.save['world']['objectsArray']=[]
        self.save['userInfo']['player'].update(xp=game_settings.level_to_xp(100),gold=10_000_000,cash=500,
            mastery={},masteryCounters={},achievements={},achCounters={},storageData={})
        self.save['importedPreservationState']={'keep':[1,{'opaque':True}]}
        if world!='farm':
            creative_worlds.create(self.save,world,'allAccess',now=NOW)
            world_travel.switch(self.save,world,now=NOW)
        self.persist()

    def persist(self):
        with redirect_stdout(io.StringIO()):self.player.save_session('fixture-farmer')

    def send(self,action,snapshot,params=(),*,error=0):
        with mock.patch('commands.timestamp_now',return_value=NOW),mock.patch('server.timestamp_now',return_value=NOW),mock.patch('engine.timestamp_now',return_value=NOW):
            response=self.gateway([self.command('WorldService.performAction',[action,snapshot,list(params)])])
        return fixtures.gateway_results(self,response,[error])[0]

    def test_all61_authored_new_world_gifts_map_to_exact_seed_and_ladder(self):
        counts = {'hlights':0,'atlantis':0,'glen':0}
        for row in themed_crop_rows():
            for name in row['gifts']:
                counts[row['world']] += 1
                gift = items.get_item_by_name(name)
                self.assertIsNotNone(gift)
                self.assertEqual(gift['masteredItemCode'],row['code'])
                self.assertEqual(gift['className'],'DynamicMasterySign')
                self.assertEqual(gift['buyable'],'false')
                self.assertFalse({'cash','cost','marketEntries'} & gift.keys())
                rule = tw._mastery_gift_rule(row['world'],name,'DynamicMasterySign')
                self.assertTrue(rule['masteryGift'])
                self.assertIsNone(rule['price'])
                self.assertNotIn(name,tw.catalog_rules(row['world'])['items'])
                self.assertIsNone(tw._mastery_gift_rule(row['world'],name,'Building'))
                for other in counts:
                    if other != row['world']:
                        self.assertIsNone(tw._mastery_gift_rule(other,name,'DynamicMasterySign'))
                snapshot = {'sizeX':50,'sizeY':50,'tileSet':CANDIDATE_SPECS[row['world']]['theme'],
                            'objectsArray':[{'id':101,'className':'DynamicMasterySign','itemName':name,
                                             'position':{'x':4,'y':4,'z':0},'opaque':[1,2]}]}
                before = copy.deepcopy(snapshot)
                tw.guard_snapshot(row['world'],snapshot)
                self.assertEqual(snapshot,before)
        self.assertEqual(counts,{'hlights':32,'atlantis':17,'glen':12})

    def test_all49_previously_earned_placed_held_and_gifted_definitions_survive_load(self):
        self.prepare()
        player=self.save['userInfo']['player']
        player['storageData']={'-1':{},'-2':{}}
        for index,row in enumerate(LOST.values()):
            crop=OWNERS[row['masteredItemCode']]
            player['mastery'][crop['code']]=2
            player['masteryCounters'][crop['code']]=int(crop['masteryLevel'][-1]['count'])
            player['storageData']['-1'][row['code']]=[2,['synthetic-sender'],[{'preserve':[1]}]]
            player['storageData']['-2'][row['code']]=[1,[],[{'opaque':True}]]
            self.save['world']['objectsArray'].append({'id':index+1,'className':'DynamicMasterySign','itemName':row['name'],
                'state':'static','position':{'x':index%10*3,'y':index//10*3,'z':0},'importedSign':{'keep':[row['code']]}})
        self.persist()
        saved_bytes=self.path.read_bytes()
        expected=json.loads(saved_bytes)
        with redirect_stdout(io.StringIO()):self.player.load_saves()
        self.assertEqual(self.save,expected)
        self.assertEqual(self.path.read_bytes(),saved_bytes)
        for row in LOST.values():
            self.assertEqual(items.get_item_by_name(row['name']),row)
            self.assertEqual(items.get_item_by_code(row['code']),row)
        # Reload is definition preservation, never an award/backfill.
        self.assertEqual(self.save['userInfo']['player']['storageData'],expected['userInfo']['player']['storageData'])

    def test_all49_original_final_rewards_still_grant_once_under_actual_reservation(self):
        self.prepare()
        player=self.save['userInfo']['player']
        for row in LOST.values():
            crop=items.get_item_by_code(row['masteredItemCode'])
            self.assertFalse(heritage_pricing.is_overlaid(crop))
            final=int(crop['masteryLevel'][-1]['count'])
            player['mastery'][crop['code']]=1
            player['masteryCounters'][crop['code']]=final-int(crop['masteryYield'])
            with redirect_stdout(io.StringIO()):
                progression.record_harvest(self.save,crop)
                progression.record_harvest(self.save,crop)
            self.assertEqual(player['storageData']['-1'][row['code']],[1,[],[]])
        self.persist()
        expected=copy.deepcopy(player['storageData'])
        with redirect_stdout(io.StringIO()):self.player.load_saves()
        self.assertEqual(self.save['userInfo']['player']['storageData'],expected)

    def test_reserved_seed_and_gift_market_purchases_are_still_refused(self):
        self.prepare()
        for row in LOST.values():
            for item in (items.get_item_by_code(row['masteredItemCode']),items.get_item_by_name(row['name'])):
                before=copy.deepcopy(self.save);disk=self.path.read_bytes()
                with self.assertRaises(ValueError):creative_worlds.guard_market_purchase(self.save,item,'coins',neighbor_count=0)
                self.assertEqual(self.save,before);self.assertEqual(self.path.read_bytes(),disk)
        crop=items.get_item_by_name('bubblebeans')
        snapshot={'id':64001,'className':'Plot','itemName':crop['name'],'state':'planted','position':{'x':4,'y':4,'z':0}}
        before,disk=copy.deepcopy(self.save),self.path.read_bytes()
        self.send('place',snapshot,error=29)
        self.assertEqual(self.save,before);self.assertEqual(self.path.read_bytes(),disk)

    def check_themed_gift(self,world,crop_name):
        self.prepare(world)
        crop=items.get_item_by_name(crop_name)
        gift_name=crop['masteryLevel'][-1]['gift']
        gift=items.get_item_by_name(gift_name)
        self.assertIsNotNone(gift)
        self.assertIn(crop_name,tw.allowed_seeds(world))
        player=self.save['userInfo']['player']
        final=int(crop['masteryLevel'][-1]['count'])
        player['mastery'][crop['code']]=1
        player['masteryCounters'][crop['code']]=final-int(crop['masteryYield'])
        plot={'id':101,'className':'Plot','itemName':crop_name,'state':'grown',
              'plantTime':(NOW-peaceful.grow_seconds(crop)-1)*1000,'position':{'x':4,'y':4,'z':0}}
        self.save['world']['objectsArray']=[plot];self.persist()
        self.send('harvest',dict(plot,state='fallow'))
        self.send('harvest',dict(plot,state='fallow'))
        self.assertEqual(self.save['userInfo']['player']['storageData']['-1'][gift['code']],[1,[],[]])
        with redirect_stdout(io.StringIO()):self.player.load_saves()
        self.assertEqual(self.save['userInfo']['player']['storageData']['-1'][gift['code']],[1,[],[]])
        sign={'id':64001,'className':'DynamicMasterySign','itemName':gift_name,'state':'static','position':{'x':12,'y':4,'z':0}}
        before,disk=copy.deepcopy(self.save),self.path.read_bytes()
        with self.assertRaises(ValueError):tw.guard_purchase(self.save,gift,'coins',now=NOW)
        self.assertNotIn(gift_name,tw.catalog_rules(world)['items'])
        for forged,params in ((sign,[]),(dict(sign,className='Building'),[{'isGift':True}]),
                              (dict(sign,itemName='masterdazzlers'),[{'isGift':True}])):
            self.send('place',forged,params,error=29)
            self.assertEqual(self.save,before);self.assertEqual(self.path.read_bytes(),disk)
        balances={k:self.save['userInfo']['player'][k] for k in ('gold','cash','xp')}
        self.send('place',sign,[{'isGift':True}]);self.send('place',sign,[{'isGift':True}])
        self.assertEqual({k:self.save['userInfo']['player'][k] for k in balances},balances)
        self.assertNotIn(gift['code'],self.save['userInfo']['player']['storageData']['-1'])
        expected=json.loads(self.path.read_text())
        with redirect_stdout(io.StringIO()):self.player.load_saves()
        self.assertEqual(self.save['world']['objectsArray'],expected['world']['objectsArray'])
        placed=next(obj for obj in self.save['world']['objectsArray'] if obj.get('itemName')==gift_name)
        moved=dict(placed,position={'x':16,'y':4,'z':0});self.send('move',moved)
        before,disk=copy.deepcopy(self.save),self.path.read_bytes()
        self.send('place',dict(sign,id=64002,position={'x':20,'y':4,'z':0}),[{'isGift':True}],error=29)
        self.assertEqual(self.save,before);self.assertEqual(self.path.read_bytes(),disk)
        for action in ('harvest','sell','clear','store'):
            self.send(action,moved,error=29)
            self.assertEqual(self.save,before);self.assertEqual(self.path.read_bytes(),disk)
        forged=copy.deepcopy(self.save['world'])
        next(obj for obj in forged['objectsArray'] if obj.get('itemName')==gift_name)['className']='Building'
        with self.assertRaises(ValueError):tw.guard_snapshot(world,forged)
        self.assertEqual(self.save['importedPreservationState'],{'keep':[1,{'opaque':True}]})

    def test_hlights_actual_harvest_retry_gift_reload_then_free_placement(self):
        self.check_themed_gift('hlights','xhl_kindleonions')

    def test_atlantis_actual_harvest_retry_gift_reload_then_free_placement(self):
        self.check_themed_gift('atlantis','bubblebeans')

    def test_legacy_home_bubblebeans_crop_and_gift_survive_after_home_sale_closes(self):
        self.prepare()
        crop=items.get_item_by_name('bubblebeans');gift=items.get_item_by_name('masterbubblebeans')
        self.assertFalse(heritage_pricing.is_overlaid(crop))
        player=self.save['userInfo']['player'];final=int(crop['masteryLevel'][-1]['count'])
        player['mastery'][crop['code']]=1
        player['masteryCounters'][crop['code']]=final-int(crop['masteryYield'])
        plot={'id':101,'className':'Plot','itemName':'bubblebeans','state':'grown',
              'plantTime':(NOW-peaceful.grow_seconds(crop)-1)*1000,'position':{'x':4,'y':4,'z':0}}
        self.save['world']['objectsArray']=[plot];self.persist()
        self.send('harvest',dict(plot,state='fallow'));self.send('harvest',dict(plot,state='fallow'))
        self.assertEqual(self.save['userInfo']['player']['storageData']['-1'][gift['code']],[1,[],[]])
        sign={'id':64001,'className':'DynamicMasterySign','itemName':gift['name'],'state':'static','position':{'x':12,'y':4,'z':0}}
        before={k:self.save['userInfo']['player'][k] for k in ('gold','cash','xp')}
        self.send('place',sign,[{'isGift':True}]);self.send('place',sign,[{'isGift':True}])
        self.assertEqual({k:self.save['userInfo']['player'][k] for k in before},before)
        saved=self.path.read_bytes()
        with redirect_stdout(io.StringIO()):self.player.load_saves()
        self.assertEqual(self.path.read_bytes(),saved)
        self.assertEqual(next(o for o in self.save['world']['objectsArray'] if o.get('itemName')==gift['name'])['className'],'DynamicMasterySign')

    def test_authored_empty_atlantis_gift_remains_empty_without_fabricated_reward(self):
        self.prepare('atlantis')
        crop=items.get_item_by_name('aquamarinerose')
        self.assertEqual(crop['masteryLevel'][-1]['gift'],'')
        self.assertIsNone(items.get_item_by_name('masteraquamarinerose'))
        player=self.save['userInfo']['player'];player['mastery'][crop['code']]=1
        player['masteryCounters'][crop['code']]=int(crop['masteryLevel'][-1]['count'])-int(crop['masteryYield'])
        before=copy.deepcopy(player['storageData'])
        with redirect_stdout(io.StringIO()):
            progression.record_harvest(self.save,crop);progression.record_harvest(self.save,crop)
        self.assertEqual(player['storageData'],before)
        self.assertEqual(player['mastery'][crop['code']],2)

    def test_optional_glen12_missing_rewards_are_explicit_not_silently_dropped(self):
        rows=themed_crop_rows()
        glen=[row for row in rows if row['world']=='glen']
        self.assertEqual(len(glen),12)
        for row in glen:
            for gift in row['gifts']:
                self.assertEqual(items.get_item_by_name(gift) is not None,hasattr(mastery_signs,'GLEN_GIFTS'))
        if hasattr(mastery_signs,'GLEN_GIFTS'):
            self.prepare('glen');player=self.save['userInfo']['player']
            for row in glen:
                crop=items.get_item_by_name(row['name']);player['mastery'][crop['code']]=1
                player['masteryCounters'][crop['code']]=int(crop['masteryLevel'][-1]['count'])-int(crop['masteryYield'])
                with redirect_stdout(io.StringIO()):
                    progression.record_harvest(self.save,crop);progression.record_harvest(self.save,crop)
                gift=items.get_item_by_name(row['gifts'][0])
                self.assertEqual(player['storageData']['-1'][gift['code']],[1,[],[]])
            self.persist();expected=copy.deepcopy(player['storageData'])
            with redirect_stdout(io.StringIO()):self.player.load_saves()
            self.assertEqual(self.save['userInfo']['player']['storageData'],expected)
            self.check_themed_gift('glen','ambrosiatulip')

    def test_client_server_full_gift_rows_agree_and_original_source_cache_are_pristine(self):
        original=Path(items.ITEMS_AMF).read_bytes()
        expected=mastery_signs.derive(RAW)
        payload=decode(client_catalog._generate(original,date(2026,10,24)))['settings']['items']['item']
        self.assertEqual(payload[len(RAW):],expected)
        self.assertEqual([r for r in items.get_items() if r['code'].startswith(mastery_signs.CODE_PREFIX)],expected)
        pristine=persistence.read_json(items.CACHE_ITEMS_JSON)['data']['settings']['items']['item']
        self.assertEqual(pristine,RAW)
        self.assertEqual(hashlib.sha256(original).hexdigest(),'14987fd4c07f9de35ff5092aeab58584802fd7fbeca1131ad1a5e3eee381a4d7')
        self.assertEqual(Path(items.ITEMS_AMF).read_bytes(),original)

class ProductionBoundaryTests(unittest.TestCase):
    def test_candidate_fixture_restores_production_registries_and_catalog(self):
        self.assertEqual(tw.SPECS,_PRODUCTION_SPECS)
        self.assertEqual(tw.ACTIVE_WORLDS,_PRODUCTION_ACTIVE)
        self.assertEqual(heritage_pricing.RESERVED_WORLDS,_PRODUCTION_RESERVED)
        self.assertNotIn('DynamicMasterySign',tw.BASIC_CLASSES)
        crop = items.get_item_by_name('bubblebeans')
        self.assertEqual(heritage_pricing.is_overlaid(crop),'atlantis' not in _PRODUCTION_RESERVED)
        for world in CANDIDATE_SPECS:
            if world not in _PRODUCTION_ACTIVE:
                self.assertIsNone(tw._mastery_gift_rule(world,'masterbubblebeans','DynamicMasterySign'))


if __name__=='__main__':unittest.main(verbosity=2)
