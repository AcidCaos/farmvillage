"""Original paid completion alias, with no cancellation or free growth."""
import copy
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_wave2_meadows_storage as fixtures
import meadows_storage,pyamf,world_travel

class MeadowsCompletionTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.MeadowsStorageTests.setUpClass.__func__)
    command=staticmethod(fixtures.MeadowsStorageTests.command)
    shed=staticmethod(fixtures.MeadowsStorageTests.shed)
    for name in ('setUp','fixture','write_fixture','gateway_payload','gateway','save','prepare','persist','fixture_meadows','init_sequence'):
        locals()[name]=getattr(fixtures.MeadowsStorageTests,name)

    def wire(self,action,snapshot,sequence,token,params=None,expected=200):
        entry=self.command('WorldService.performAction',[action,snapshot,pyamf.MixedArray({0:{}}) if params is None else params],sequence)
        if token is not None:entry['sequenceID']=token
        response=self.gateway([entry]);fixtures.fixtures.assert_gateway_status(self,response,expected)
        return response

    def paid(self):
        self.fixture_meadows();self.save['world']['objectsArray']=[self.shed()];self.persist()
        token=self.init_sequence();self.wire('purchaseStorageUpgrade',self.shed(),7,token)
        return token

    def test_original_completion_is_noop_retry_reload_and_namespace_safe(self):
        token=self.paid();before=copy.deepcopy(self.save)
        self.wire('cancelStorageUpgrade',self.shed(),8,token);after=copy.deepcopy(self.save)
        left,right=copy.deepcopy(before),copy.deepcopy(after)
        left.pop(meadows_storage.STATE);right.pop(meadows_storage.STATE);self.assertEqual(left,right)
        self.assertEqual(after['userInfo']['player']['cash'],490)
        self.wire('cancelStorageUpgrade',self.shed(),8,token);self.assertEqual(self.save,after)
        self.player.load_saves();self.wire('cancelStorageUpgrade',self.shed(),8,token);self.assertEqual(self.save,after)
        current=self.init_sequence();before=copy.deepcopy(self.save)
        self.wire('cancelStorageUpgrade',self.shed(),8,token);self.assertEqual(self.save,before)
        for ident in (token,current,'unknown',None):
            self.wire('cancelStorageUpgrade',self.shed(),9,ident,expected=400);self.assertEqual(self.save,before)

    def test_each_paid_ladder_completion_preserves_both_ten_cash_charges(self):
        for root in meadows_storage._ROOTS:
            with self.subTest(root=root):
                self.fixture_meadows();self.save['world']['objectsArray']=[self.shed(root)]
                for seq,source in ((1,root),(3,root+'2')):
                    meadows_storage.purchase_storage_upgrade(self.save,self.shed(source),pyamf.MixedArray({0:{}}),request_id=seq)
                    before=copy.deepcopy(self.save)
                    meadows_storage.acknowledge_paid_storage_upgrade(self.save,self.shed(source),pyamf.MixedArray({0:{}}),request_id=seq+1)
                    self.assertEqual(self.save['world'],before['world']);self.assertEqual(self.save['userInfo'],before['userInfo'])
                self.assertEqual(self.save['userInfo']['player']['cash'],480)
                self.assertEqual(self.save['world']['objectsArray'][0]['expansionLevel'],3)

    def test_no_prior_paid_receipt_cannot_admit_cancel_or_free_growth(self):
        self.fixture_meadows();self.save['world']['objectsArray']=[dict(self.shed('toolshedpink2'),expansionLevel=2)]
        self.save['userInfo']['player']['upgradeStatus']={'isActive':False};self.persist();token=self.init_sequence()
        before,disk=copy.deepcopy(self.save),self.path.read_bytes()
        for action in ('cancelStorageUpgrade','upgradeStorage'):
            self.wire(action,self.shed(),8,token,expected=400)
            self.assertEqual(self.save,before);self.assertEqual(self.path.read_bytes(),disk)

    def test_wrong_source_target_campaign_options_and_proof_refuse_atomically(self):
        token=self.paid();baseline=copy.deepcopy(self.save)
        cases=[(dict(self.shed(),**{field:value}),None,None) for field,value in (('id',901),('itemName','toolshedpink2'),('className','Building'),('state','building'))]
        cases += [(self.shed(),pyamf.MixedArray({0:opts}),None) for opts in ({'price':0},{'materials':[]},{'firstWA':1})]
        cases += [(self.shed(),None,edit) for edit in ('no-receipt','wrong-response','bad-signature','wrong-target','wrong-level','deleted','active-social','helpers')]
        for snapshot,params,edit in cases:
            with self.subTest(edit=edit,snapshot=snapshot,params=params):
                self.save.clear();self.save.update(copy.deepcopy(baseline));receipts=self.save[meadows_storage.STATE]['receipts'];payment=token+':upgrade:7'
                if edit=='no-receipt':receipts.clear()
                elif edit=='wrong-response':receipts[payment]['response']={'id':901}
                elif edit=='bad-signature':receipts[payment]['signature']='unknown'
                elif edit=='wrong-target':self.save['world']['objectsArray'][0]['itemName']='toolshedpink3'
                elif edit=='wrong-level':self.save['world']['objectsArray'][0]['expansionLevel']=3
                elif edit=='deleted':self.save['world']['objectsArray'][0]['deleted']=True
                elif edit=='active-social':self.save['userInfo']['player']['upgradeStatus']['isActive']=True
                elif edit=='helpers':self.save['userInfo']['player']['upgradeStatus']['numHelped']=1
                self.persist();before,disk=copy.deepcopy(self.save),self.path.read_bytes()
                self.wire('cancelStorageUpgrade',snapshot,8,token,params,expected=400)
                self.assertEqual(self.save,before);self.assertEqual(self.path.read_bytes(),disk)
        self.save.clear();self.save.update(copy.deepcopy(baseline));self.persist();before=copy.deepcopy(self.save)
        self.wire('cancelStorageUpgrade',self.shed(),7,token,expected=400);self.assertEqual(self.save,before)

    def test_other_world_cancellation_retains_original_refusal(self):
        token=self.paid();world_travel.switch(self.save,'farm',now=fixtures.NOW);self.persist()
        before,disk=copy.deepcopy(self.save),self.path.read_bytes()
        self.wire('cancelStorageUpgrade',self.shed(),8,token,expected=400)
        self.assertEqual(self.save,before);self.assertEqual(self.path.read_bytes(),disk)

if __name__=='__main__':unittest.main()
