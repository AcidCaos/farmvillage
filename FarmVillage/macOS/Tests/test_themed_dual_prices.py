"""Authored same-code cash alternatives preserve primary coin prices and retries."""
import copy
from collections import Counter
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import unittest
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import test_cove_cellar as cellar
import creative_worlds,items,themed_worlds as tw,world_travel
NOW=1800000000

class ThemedDualPriceTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp=fixtures.RuntimeFixtureTests.setUp
    fixture=fixtures.RuntimeFixtureTests.fixture
    write_fixture=fixtures.RuntimeFixtureTests.write_fixture
    command=staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload=fixtures.RuntimeFixtureTests.gateway_payload
    gateway=fixtures.RuntimeFixtureTests.gateway
    save=cellar.CoveCellarTests.save
    persist=cellar.CoveCellarTests.persist
    send=cellar.CoveCellarTests.send
    rejected=cellar.CoveCellarTests.rejected
    def prepare(self):
        patch=mock.patch.object(tw,'ACTIVE_WORLDS',{'htown'});patch.start();self.addCleanup(patch.stop)
        self.path=self.write_fixture();self.save['world']['objectsArray']=[]
        self.save['userInfo']['player'].update(xp=100010,gold=10000,cash=100)
        creative_worlds.create(self.save,'htown','allAccess',now=NOW)
        world_travel.switch(self.save,'htown',now=NOW);self.persist()
        self.item=items.get_item_by_name('xhdpresentbox')
    @staticmethod
    def present(ident=64001,x=12):
        return {'id':ident,'className':'RotateableDecoration','itemName':'xhdpresentbox','state':'static',
                'direction':0,'position':{'x':x,'y':12,'z':0}}
    def test_signed_cash_coin_default_and_gold_alias(self):
        self.prepare()
        for ident,currency,cost in ((64001,'cash',1),(64002,'coins',100),(64003,None,100),(64004,'gold',100)):
            with self.subTest(currency=currency):
                before=copy.deepcopy(self.save['userInfo']['player'])
                result=self.send('place',self.present(ident,12+(ident-64001)*5),[] if currency is None else [{'currency':currency}])
                self.assertIn('id',result);p=self.save['userInfo']['player']
                self.assertEqual(p['cash'],before['cash']-(cost if currency=='cash' else 0))
                self.assertEqual(p['gold'],before['gold']-(0 if currency=='cash' else cost))
        self.assertEqual(tw.catalog_rules('htown')['items']['xhdpresentbox']['price'],{'currency':'coins','amount':100})
        self.assertEqual((self.item['code'],self.item['cost'],self.item['cash'],self.item['market']),('9pH','100','1','coins'))
    def test_signed_cash_live_retry_and_disk_reload_preserve_charge(self):
        self.prepare();snapshot=self.present()
        first=self.send('place',snapshot,[{'currency':'cash'}])
        before=copy.deepcopy(self.save['userInfo']['player']);count=len(self.save['world']['objectsArray'])
        self.send('place',snapshot,[{'currency':'cash'}])
        self.assertEqual((self.save['userInfo']['player']['gold'],self.save['userInfo']['player']['cash']),(before['gold'],before['cash']))
        self.assertEqual(len(self.save['world']['objectsArray']),count)
        with redirect_stdout(io.StringIO()):self.player.load_saves()
        self.assertEqual(self.save['userInfo']['currentWorldType'],'htown')
        # Temp IDs are transport aliases intentionally removed at save/login.
        # Reload uses the acknowledged persistent ID rather than replaying an old session alias.
        persisted=next(row for row in self.save['world']['objectsArray'] if row['id']==first['id'])
        self.assertNotIn('tempId',persisted)
        moved=copy.deepcopy(persisted);moved['position']={'x':13,'y':12,'z':0}
        self.send('move',moved)
        self.assertEqual((self.save['userInfo']['player']['gold'],self.save['userInfo']['player']['cash']),(before['gold'],before['cash']))
        self.assertEqual(len(self.save['world']['objectsArray']),count)
    def test_wrong_currency_and_insufficient_selected_wallet_are_atomic(self):
        self.prepare()
        for currency in ('jade','cash_bad',True):
            with self.subTest(currency=currency):self.rejected('place',self.present(),[{'currency':currency}])
        self.save['userInfo']['player']['cash']=0;self.persist()
        self.rejected('place',self.present(),[{'currency':'cash'}])
        self.save['userInfo']['player'].update(cash=100,gold=99);self.persist()
        self.rejected('place',self.present(),[{'currency':'coins'}])
        self.assertEqual(self.save['userInfo']['player']['cash'],100)
    def test_active_alternatives_and_canonical_price(self):
        active_worlds=tw.active_worlds()
        rows=[]
        for world in active_worlds:
            for name,rule in tw.catalog_rules(world)['items'].items():
                item=items.get_item_by_name(name)
                if rule['price'] and rule['price']['currency']=='coins' and (item.get('market') or 'coins')=='coins':
                    try:cash=tw._whole(item.get('cash'),'cash')
                    except ValueError:continue
                    owners={n.get('name') for n in creative_worlds._nodes(item.get('requirements')) if n.get('className')=='World'}
                    if world in owners:rows.append((world,name,item['code'],cash))
        self.assertEqual(len(rows),21);self.assertEqual(Counter(w for w,_,_,_ in rows),{'htown':21})
        self.assertIn(('htown','xhdpresentbox','9pH',1),rows)
        # Inspect every active contract before narrowing this action fixture
        # to Htown; otherwise another region's admission cache is poisoned.
        self.prepare()
        rule=copy.deepcopy(tw.catalog_rules('htown')['items']['xhdpresentbox']);before=copy.deepcopy(self.save)
        self.assertEqual(tw.guard_purchase(self.save,dict(self.item,cash='999999'),'cash',now=NOW),{'currency':'cash','amount':1})
        self.assertEqual(self.save,before);self.assertEqual(tw.catalog_rules('htown')['items']['xhdpresentbox'],rule)
        with self.assertRaisesRegex(ValueError,'currency'):tw.guard_purchase(self.save,dict(self.item,code='forged'),'cash',now=NOW)
        for value in (None,'','0','-1','1.5',True):
            with self.subTest(cash=value),mock.patch.object(tw,'_catalog_item',return_value=dict(self.item,cash=value)):
                with self.assertRaises(ValueError):tw.guard_purchase(self.save,self.item,'cash',now=NOW)
        coin_only=next(items.get_item_by_name(n) for n,r in tw.catalog_rules('htown')['items'].items()
                       if r['price'] and r['price']['currency']=='coins' and not items.get_item_by_name(n).get('cash'))
        with self.assertRaises(ValueError):tw.guard_purchase(self.save,coin_only,'cash',now=NOW)

if __name__=='__main__':unittest.main()
