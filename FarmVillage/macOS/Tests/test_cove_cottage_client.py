"""Exact final Cove upgrade predicate: all other client code remains pinned."""
import hashlib
from pathlib import Path
import struct
import unittest
import zlib

from test_turbo_client_refusal import read_abcs, ABC
import test_cottage_client_upgrades as upgrade_tests
import test_image_row_client as image_tests
import client_compatibility as compatibility
import cove_client

ROOT = Path(__file__).resolve().parents[2]


class CoveCottageClientTests(unittest.TestCase):
    execute_frame = upgrade_tests.CottageClientUpgradeTests.execute_frame
    branch_errors = image_tests.ImageRowClientTests.branch_errors

    @classmethod
    def setUpClass(cls):
        cls.path = ROOT / 'embeds/Flash/v855097-855094/FarmGame.swf'
        cls.source = cls.path.read_bytes()
        body = zlib.decompress(cls.source[8:])
        for edits in (compatibility.EDITS, compatibility.MARKET_EDITS,
                      compatibility.TAB_EDITS, compatibility.SCRATCH_EDITS,
                      compatibility.EMPTY_WORLD_EDITS, compatibility.COTTAGE_EDITS,
                      compatibility.COTTAGE_UPGRADE_EDITS, compatibility.TURBO_EDITS,
                      compatibility.STORAGE_EDITS, compatibility.INVITATION_EDITS,
                      compatibility.VIP_EDITS, compatibility.MARKET_WALKTHROUGH_EDITS,
                      compatibility.QUEST_CLOSE_EDITS, compatibility.IMAGE_ROW_EDITS,
                      compatibility.INVENTORY_ART_EDITS, compatibility.MARKETSTALL_EXPANSION_EDITS,
                      compatibility.WIDGET_STORAGE_EDITS, compatibility.REGIONAL_UPGRADE_EDITS,
                      compatibility.OPTIONAL_BACKGROUND_EDITS):
            body = compatibility._apply_edits(body, edits)
        cls.previous_body = body
        cls.previous = cls.source[:4] + struct.pack('<I', len(body)+8) + zlib.compress(body, 9)
        cls.final = compatibility.patch_client_bytes(cls.source)
        cls.body = zlib.decompress(cls.final[8:])
        cls.before, cls.after = read_abcs(body), read_abcs(cls.body)

    def test_only_three_new_strings_and_one_fixed_length_method_change(self):
        self.assertEqual(hashlib.sha256(self.previous_body).hexdigest(), cove_client.SOURCE_BODY_SHA256)
        self.assertEqual(hashlib.sha256(self.body).hexdigest(), cove_client.PATCHED_BODY_SHA256)
        self.assertEqual(len(self.body)-len(self.previous_body), 28)
        self.assertEqual(self.after[0].strings, self.before[0].strings+['pub','restaurant','xrfcrafttype'])
        changed=[]
        total=0
        for index,(a,b) in enumerate(zip(self.before,self.after)):
            if index: self.assertEqual(a.strings,b.strings)
            for field in ('ints','uints','mn','ns','nssets','methods','instances','classes'):
                self.assertEqual(getattr(a,field),getattr(b,field),(index,field))
            for ident,code in a.bodies.items():
                total+=1
                if code!=b.bodies[ident]:changed.append((index,ident))
        self.assertEqual((total,changed),(68492,[(0,34693)]))
        old,new=self.before[0].bodies[34693],self.after[0].bodies[34693]
        self.assertEqual((len(old),len(new)),(1155,1155))
        self.assertEqual(old[:389],new[:389])
        self.assertEqual(old[437:],new[437:])
        self.assertEqual(hashlib.sha256(new).hexdigest(),cove_client.METHOD_PATCHED_SHA256)
        for code in (old,new):
            _,invalid,missing=self.branch_errors(code)
            self.assertEqual((invalid,missing),([],[]))
        self.assertEqual(self.path.read_bytes(),self.source)

    def predicate(self, craft):
        abc=self.after[0]
        code=abc.bodies[34693]
        reader=ABC.R(code,389)
        stack=[]
        instance={'cottage':{'craftType':craft}}
        result=None
        while reader.p<437:
            op=reader.u8()
            if op==0x02:pass
            elif op==0x2c:stack.append(abc.strings[reader.u30()])
            elif op==0x24:stack.append(reader.u8())
            elif op==0x56:
                count=reader.u30();stack.append([stack.pop() for _ in range(count)][::-1])
            elif op==0xd0:stack.append(instance)
            elif op==0x66:stack.append(stack.pop()[abc.short(reader.u30())])
            elif op==0x46:
                method,count=abc.mname(reader.u30()),reader.u30()
                self.assertEqual(count,1)
                argument,receiver=stack.pop(),stack.pop()
                self.assertTrue(method.endswith(':indexOf'))
                stack.append(receiver.index(argument) if argument in receiver else -1)
            elif op==0xc0:stack.append(int(stack.pop())+1)
            elif op==0x76:stack.append(bool(stack.pop()))
            elif op==0xb0:
                right=stack.pop();stack.append(stack.pop()>=right)
            elif op==0x63:
                self.assertEqual(reader.u30(),6);result=stack.pop()
            else:self.fail('Unexpected opcode %x'%op)
        self.assertEqual(stack,[])
        return result

    def test_seven_exact_crafts_only_keep_original_upgrade_price_and_xp_paths(self):
        accepted=('bakery','winery','perfumery','pub','xhdcrafttype','restaurant','xrfcrafttype')
        for craft in accepted+('Restaurant','restaurant ','xcovecraftingcottage','Xrfcrafttype','xrfcrafttype ','',None):
            result=self.predicate(craft)
            self.assertEqual(result,craft in accepted)
            for remaining,maximum,prereq in ((6,False,False),(0,False,False),
                    (-2,False,False),(0,True,False),(6,False,True),(0,False,True)):
                frame,_=self.execute_frame(self.after[0].bodies[34693],remaining,
                    max_level=maximum,prereq=prereq,supported=result)
                self.assertEqual(frame['coin']['visible'],result and not maximum and remaining<=0)
                self.assertEqual(frame['cash']['visible'],result and not maximum and remaining>0)

    def test_prior_final_and_new_final_are_verified_idempotently(self):
        self.assertEqual(cove_client.prepare(self.previous),self.final)
        self.assertEqual(compatibility.patch_client_bytes(self.previous),self.final)
        self.assertEqual(compatibility.patch_client_bytes(self.final),self.final)
        alternative=self.final[:8]+zlib.compress(self.body,1)
        self.assertEqual(compatibility.patch_client_bytes(alternative),alternative)
        for offset in (10,3399686,3411801,9457200,cove_client.METHOD_OFFSET+404):
            damaged=bytearray(self.previous_body);damaged[offset]^=1
            swf=self.previous[:8]+zlib.compress(damaged)
            with self.assertRaises(ValueError):cove_client.prepare(swf)
        with self.assertRaises(ValueError):cove_client.prepare(self.final+b'extra')
        with self.assertRaises(ValueError):compatibility.patch_client_bytes(self.final[:8]+b'bad compressed data')


if __name__=='__main__':unittest.main(verbosity=2)
