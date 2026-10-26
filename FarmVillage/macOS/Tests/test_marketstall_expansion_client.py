"""MarketStall expansion cannot advertise or optimistically charge unaccepted stages."""
import hashlib
import struct
import unittest
import zlib

from test_turbo_client_refusal import PATCH, ROOT, ABC, read_abcs
import test_storage_client_refusal as storage_tests
import test_cottage_invitation_stage as invitation_tests
import test_image_row_client as image_tests


class MarketStallExpansionClientTests(unittest.TestCase):
    execute = invitation_tests.CottageInvitationStageTests.execute
    execute_refusal = storage_tests.StorageClientRefusalTests.execute_refusal
    branch_errors = image_tests.ImageRowClientTests.branch_errors

    @classmethod
    def setUpClass(cls):
        cls.original = (ROOT / 'embeds/Flash/v855097-855094/FarmGame.swf').read_bytes()
        cls.previous = zlib.decompress(cls.original[8:])
        for edits in (PATCH.EDITS, PATCH.MARKET_EDITS, PATCH.TAB_EDITS, PATCH.SCRATCH_EDITS,
                      PATCH.EMPTY_WORLD_EDITS, PATCH.COTTAGE_EDITS, PATCH.COTTAGE_UPGRADE_EDITS,
                      PATCH.TURBO_EDITS, PATCH.STORAGE_EDITS, PATCH.INVITATION_EDITS,
                      PATCH.VIP_EDITS, PATCH.MARKET_WALKTHROUGH_EDITS, PATCH.QUEST_CLOSE_EDITS,
                      PATCH.IMAGE_ROW_EDITS, PATCH.INVENTORY_ART_EDITS):
            cls.previous = PATCH._apply_edits(cls.previous, edits)
        cls.prepared = PATCH.patch_client_bytes(cls.original)
        cls.body = PATCH._apply_edits(cls.previous, PATCH.MARKETSTALL_EXPANSION_EDITS)
        cls.final_body = zlib.decompress(cls.prepared[8:])
        cls.before, cls.after = read_abcs(cls.previous), read_abcs(cls.body)
        cls.abc, cls.maxstack = cls.after[0], {22858: 1}

    def test_original_caller_paths_prove_invitation_and_direct_charge_bypasses(self):
        original = self.before[0]
        for ident in (22856, 34575):
            self.assertTrue(any('callproperty readyToExpand 0' in line
                                for line in ABC.disasm(original, original.bodies[ident])))
        self.assertIn('callpropvoid beginCompleteExpansionFlow 2', '\n'.join(ABC.disasm(original, original.bodies[62869])))
        self.assertIn('frictionlessExpand', '\n'.join(ABC.disasm(original, original.bodies[62338])))
        charge = '\n'.join(ABC.disasm(original, original.bodies[22903]))
        for operation in ('expandToNextStorageLevel', 'constructprop Transactions:TCompleteNow 3', 'setproperty cash'):
            self.assertIn(operation, charge)

    def test_emitted_getter_never_reads_capacity_and_direct_entries_only_refuse(self):
        # Missing building/player/transaction globals make any capacity lookup,
        # callback write or optimistic charge fail the emitted-code execution.
        self.assertIs(self.execute(22858, 0, None, {0: object()}), False)
        for ident in (22845, 22903):
            with self.subTest(method=ident):
                self.execute_refusal(self.abc, self.abc.bodies[ident])
                expected = self.before[0].bodies[ident][:9] + self.abc.bodies[12421][9:33]
                self.assertEqual(self.abc.bodies[ident], expected + b'\x02' * (len(self.abc.bodies[ident]) - len(expected)))

    def test_only_three_methods_change_and_headers_pools_branches_exceptions_stay_valid(self):
        self.assertEqual(hashlib.sha256(self.previous).hexdigest(), PATCH.INVENTORY_ART_BODY_SHA256)
        self.assertEqual(hashlib.sha256(self.body).hexdigest(), PATCH.MARKETSTALL_EXPANSION_BODY_SHA256)
        self.assertEqual(self.body, PATCH._apply_edits(self.previous, PATCH.MARKETSTALL_EXPANSION_EDITS))
        self.assertEqual(self.final_body, PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(self.body, PATCH.WIDGET_STORAGE_EDITS), PATCH.REGIONAL_UPGRADE_EDITS), PATCH.OPTIONAL_BACKGROUND_EDITS), PATCH.COVE_UPGRADE_EDITS))
        total, changed = 0, []
        for index, (before, after) in enumerate(zip(self.before, self.after)):
            for field in ('ints', 'uints', 'strings', 'mn', 'ns', 'nssets', 'methods', 'instances', 'classes'):
                self.assertEqual(getattr(before, field), getattr(after, field))
            self.assertEqual([struct.pack('<d', x) for x in before.doubles], [struct.pack('<d', x) for x in after.doubles])
            for ident, code in before.bodies.items():
                total += 1
                if code != after.bodies[ident]:
                    changed.append((index, ident)); self.assertEqual(len(code), len(after.bodies[ident]))
        self.assertEqual((total, changed), (68492, [(0, 22845), (0, 22858), (0, 22903)]))
        headers = {22845: 'bdb20109061011c702', 22858: 'cab2010101101113', 22903: 'f7b20107031011cd01'}
        for ident, offset, length, old_sha, new_sha in PATCH.MARKETSTALL_EXPANSION_METHODS:
            self.assertEqual(hashlib.sha256(self.previous[offset:offset+length]).hexdigest(), old_sha)
            self.assertEqual(hashlib.sha256(self.body[offset:offset+length]).hexdigest(), new_sha)
            header = bytes.fromhex(headers[ident]); self.assertEqual(self.body[offset-len(header):offset], header)
            starts, invalid, missing = self.branch_errors(self.abc.bodies[ident])
            self.assertEqual((invalid, missing), ([], []))
            self.assertEqual(ABC.R(self.body, offset+length).u30(), 0)
        self.assertEqual((ROOT / 'embeds/Flash/v855097-855094/FarmGame.swf').read_bytes(), self.original)

    def test_known_art_stage_upgrades_idempotently_and_unknown_entries_reject(self):
        previous = self.original[:4] + struct.pack('<I', len(self.previous)+8) + zlib.compress(self.previous, 1)
        self.assertEqual(PATCH.patch_client_bytes(previous), self.prepared)
        self.assertEqual(PATCH.patch_client_bytes(self.prepared), self.prepared)
        alternative = self.prepared[:8] + zlib.compress(self.final_body, 1)
        self.assertEqual(PATCH.patch_client_bytes(alternative), alternative)
        for _, offset, _, _, _ in PATCH.MARKETSTALL_EXPANSION_METHODS:
            changed = bytearray(self.previous); changed[offset+12] ^= 1
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, 'refusing to modify unknown game code'):
                PATCH.patch_client_bytes(previous[:8] + zlib.compress(changed, 1))


if __name__ == '__main__':
    unittest.main()
