"""Meadows control boundary, original callbacks and complete client identity."""
import base64
import hashlib
from pathlib import Path
import struct
import sys
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import meadows_client
from test_turbo_client_refusal import PATCH, ROOT, ABC, read_abcs
import test_image_row_client as image_tests


class MeadowsClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (ROOT/'embeds/Flash/v855097-855094/FarmGame.swf').read_bytes()
        cls.base = PATCH.patch_client_bytes(cls.raw)
        cls.prepared = meadows_client.patch_client_bytes(cls.base)
        cls.before = read_abcs(zlib.decompress(cls.base[8:]))
        cls.after = read_abcs(zlib.decompress(cls.prepared[8:]))
        cls.original = read_abcs(zlib.decompress(cls.raw[8:]))

    def test_only_five_control_methods_change_and_pools_stay_exact(self):
        self.assertEqual(len(self.before), len(self.after))
        changed=[]
        for index,(before,after) in enumerate(zip(self.before,self.after)):
            for field in ('ints','uints','strings','mn','ns','nssets','methods','instances','classes'):
                self.assertEqual(getattr(before,field),getattr(after,field),field)
            self.assertEqual(list(before.bodies),list(after.bodies))
            for ident,code in before.bodies.items():
                if code != after.bodies[ident]:changed.append((index,ident))
        self.assertEqual(changed,[(0,row[0]) for row in meadows_client.METHODS])

    def test_guard_selects_original_only_on_meadows_with_unchanged_callbacks(self):
        # Execute the exact guard instructions. A branch selection cannot read
        # a building, mutate player state, construct a transaction or issue RPC.
        for ident,_,length,_,compressed in meadows_client.METHODS:
            code=self.after[0].bodies[ident]
            raw=self.original[0].bodies[ident]
            self.assertEqual(zlib.decompress(base64.b64decode(compressed)),raw)
            prefix_length=len(meadows_client.WORLD_GUARD)+4
            self.assertEqual(code[prefix_length:prefix_length+length],self.before[0].bodies[ident])
            self.assertEqual(code[prefix_length+length:],raw)
            for world in ('farm','england','meadows','fisherman','hlights',None,'meadows-fake'):
                with self.subTest(method=ident,world=world):
                    selected=self.select_branch(self.after[0],code,world)
                    self.assertEqual(selected,prefix_length+(length if world=='meadows' else 0))
            starts,invalid,missing=image_tests.ImageRowClientTests.branch_errors(self,code)
            self.assertEqual((invalid,missing),([],[]))
        # Social/helper free growth remains refused, even on Meadows.
        self.assertEqual(self.before[0].bodies[12421],self.after[0].bodies[12421])
        # The recovered methods still select original upgrade/shipping views.
        widget='\n'.join(ABC.disasm(self.original[0],self.original[0].bodies[12193]))
        self.assertIn('getproperty Widgets.Windows.Storage:StorageWindow:onExpandButtonClick',widget)
        self.assertIn('getproperty Widgets.Windows.Storage:StorageWindow:onShippingLicensesButtonClick',widget)
        upgrade='\n'.join(ABC.disasm(self.after[0],self.after[0].bodies[12423]))
        self.assertIn('displayMessage',upgrade)

    def select_branch(self,abc,code,world):
        reader=ABC.R(code);stack=[]
        globals_={'Global':{'worldManager':{'currentWorldType':world}}}
        for _ in range(8):
            op=reader.u8()
            if op==0x60:stack.append(globals_[abc.mname(reader.u30())])
            elif op==0x66:
                name=abc.short(reader.u30());stack.append(stack.pop()[name])
            elif op==0x2c:stack.append(abc.strings[reader.u30()])
            elif op==0x13:
                delta=reader.s24();right,left=stack.pop(),stack.pop()
                self.assertEqual(stack,[])
                return reader.p+delta if left==right else reader.p
            else:self.fail('Unexpected guard instruction '+hex(op))
        self.fail('Guard did not branch')

    def test_scope_stack_and_exception_headers_are_preserved(self):
        before_body=zlib.decompress(self.base[8:])
        after_body=zlib.decompress(self.prepared[8:])
        for ident,offset,length,_,_ in meadows_client.METHODS:
            old_code=self.before[0].bodies[ident]
            new_code=self.after[0].bodies[ident]
            after_offset=after_body.find(new_code)
            headers=[]
            for body,position,code in ((before_body,offset,old_code),(after_body,after_offset,new_code)):
                header=ABC.R(body,position-len(meadows_client._u30(len(code)))-6)
                values=[header.u30() for _ in range(6)]
                self.assertEqual(header.p,position)
                self.assertEqual(values[0],ident)
                self.assertGreaterEqual(values[1],2)  # Guard peaks at two values.
                self.assertEqual(values[-1],len(code))
                self.assertEqual(ABC.R(body,position+len(code)).u30(),0)
                headers.append(values[:5])
            self.assertEqual(*headers)

    def test_idempotent_exact_artifact_and_unknown_inputs_refuse(self):
        body=zlib.decompress(self.prepared[8:])
        self.assertEqual(hashlib.sha256(body).hexdigest(),meadows_client.PATCHED_BODY_SHA256)
        self.assertEqual(struct.unpack_from('<I',self.prepared,4)[0],len(body)+8)
        self.assertEqual(meadows_client.patch_client_bytes(self.prepared),self.prepared)
        alternative=self.prepared[:8]+zlib.compress(body,9)
        self.assertEqual(meadows_client.patch_client_bytes(alternative),alternative)
        for invalid in (self.prepared+b'trailing', self.prepared[:8]+b'bad compressed data', self.prepared[:-3]):
            with self.assertRaises(ValueError): meadows_client.patch_client_bytes(invalid)
        altered=bytearray(zlib.decompress(self.base[8:]));altered[meadows_client.METHODS[0][1]+8]^=1
        unknown=self.base[:8]+zlib.compress(altered,1)
        with self.assertRaisesRegex(ValueError,'unknown Meadows game code'):
            meadows_client.patch_client_bytes(unknown)
        with self.assertRaisesRegex(ValueError,'length'):
            meadows_client.patch_client_bytes(self.base[:4]+b'\0\0\0\0'+self.base[8:])
        self.assertEqual((ROOT/'embeds/Flash/v855097-855094/FarmGame.swf').read_bytes(),self.raw)


if __name__=='__main__':unittest.main()
