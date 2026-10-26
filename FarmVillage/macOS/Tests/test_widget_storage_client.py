"""The Inventory route's actual widget window hides whole unsupported buttons."""
import hashlib
import struct
import unittest
import zlib
from test_turbo_client_refusal import PATCH, ROOT, ABC, read_abcs
import test_cottage_invitation_stage as invitation_tests
import test_image_row_client as image_tests


class WidgetStorageClientTests(unittest.TestCase):
    execute = invitation_tests.CottageInvitationStageTests.execute
    branch_errors = image_tests.ImageRowClientTests.branch_errors

    @classmethod
    def setUpClass(cls):
        cls.original = (ROOT / 'embeds/Flash/v855097-855094/FarmGame.swf').read_bytes()
        cls.previous = zlib.decompress(cls.original[8:])
        for edits in (PATCH.EDITS, PATCH.MARKET_EDITS, PATCH.TAB_EDITS, PATCH.SCRATCH_EDITS,
                      PATCH.EMPTY_WORLD_EDITS, PATCH.COTTAGE_EDITS, PATCH.COTTAGE_UPGRADE_EDITS,
                      PATCH.TURBO_EDITS, PATCH.STORAGE_EDITS, PATCH.INVITATION_EDITS,
                      PATCH.VIP_EDITS, PATCH.MARKET_WALKTHROUGH_EDITS, PATCH.QUEST_CLOSE_EDITS,
                      PATCH.IMAGE_ROW_EDITS, PATCH.INVENTORY_ART_EDITS, PATCH.MARKETSTALL_EXPANSION_EDITS):
            cls.previous = PATCH._apply_edits(cls.previous, edits)
        cls.prepared = PATCH.patch_client_bytes(cls.original)
        cls.body = PATCH._apply_edits(cls.previous, PATCH.WIDGET_STORAGE_EDITS)
        cls.before, cls.after = read_abcs(cls.previous), read_abcs(cls.body)
        cls.abc, cls.maxstack = cls.after[0], {4361: 2}

    def test_actual_inventory_route_uses_widget_window_and_both_asset_variants(self):
        lines = '\n'.join(ABC.disasm(self.abc, self.abc.bodies[2899]))
        self.assertIn('constructprop Widgets.Windows.Storage:StorageWindow 1', lines)
        self.assertIn('constructprop Display:InventoryWithdrawal 3', lines)
        self.assertLess(lines.index('StorageWindow 1'), lines.index('InventoryWithdrawal 3'))
        init = '\n'.join(ABC.disasm(self.abc, self.abc.bodies[12192]))
        self.assertIn('DIALOG_ASSET_V2', init); self.assertIn('DIALOG_ASSET', init)
        manager = '\n'.join(ABC.disasm(self.abc, self.abc.bodies[4439]))
        self.assertIn('41  getlocal1', manager); self.assertIn('42  getlocal2', manager)
        self.assertIn('43  setproperty visible', manager)

    def test_emitted_arguments_hide_entire_art_and_later_enable_has_no_visibility_write(self):
        code = self.abc.bodies[12193]
        for start, stop in ((762, 771), (1146, 1147)):
            stack = ['window', 'widget']
            for opcode in code[start:stop]:
                if opcode == 0x27: stack.append(False)
                else: self.assertEqual(opcode, 0x02)
            self.assertEqual(stack, ['window', 'widget', False])
            art = {'visible': True, 'children': ['checkbox', 'label']}
            # Execute actual visible setter used by WidgetManager.addWidget.
            self.execute(4361, 21, 30, {0: {'m_element': art}, 1: stack[-1]})
            self.assertEqual(art, {'visible': False, 'children': ['checkbox', 'label']})
        enable = '\n'.join(ABC.disasm(self.abc, self.abc.bodies[4367]))
        self.assertNotIn('setproperty visible', enable)
        state = '\n'.join(ABC.disasm(self.abc, self.abc.bodies[12218]))
        self.assertNotIn('setproperty visible', state)

    def test_two_arguments_are_only_delta_across_all_methods_pools_headers_and_branches(self):
        self.assertEqual(hashlib.sha256(self.previous).hexdigest(), PATCH.MARKETSTALL_EXPANSION_BODY_SHA256)
        self.assertEqual(hashlib.sha256(self.body).hexdigest(), PATCH.WIDGET_STORAGE_BODY_SHA256)
        self.assertEqual(self.body, PATCH._apply_edits(self.previous, PATCH.WIDGET_STORAGE_EDITS))
        total, changed = 0, []
        for index, (before, after) in enumerate(zip(self.before, self.after)):
            for field in ('ints', 'uints', 'strings', 'mn', 'ns', 'nssets', 'methods', 'instances', 'classes'):
                self.assertEqual(getattr(before, field), getattr(after, field))
            self.assertEqual([struct.pack('<d', x) for x in before.doubles], [struct.pack('<d', x) for x in after.doubles])
            for ident, code in before.bodies.items():
                total += 1
                if code != after.bodies[ident]:changed.append((index, ident))
        self.assertEqual((total, changed), (68492, [(0, 12193)]))
        for ident, offset, length, old_sha, new_sha in PATCH.WIDGET_STORAGE_METHODS:
            self.assertEqual(hashlib.sha256(self.previous[offset:offset+length]).hexdigest(), old_sha)
            self.assertEqual(hashlib.sha256(self.body[offset:offset+length]).hexdigest(), new_sha)
            self.assertEqual(self.body[offset-8:offset].hex(), 'a15f0b0f0c0d9715')
            starts, invalid, missing = self.branch_errors(self.abc.bodies[ident])
            self.assertEqual((invalid, missing), ([], []))
            self.assertEqual(ABC.R(self.body, offset+length).u30(), 0)
        self.assertEqual((ROOT/'embeds/Flash/v855097-855094/FarmGame.swf').read_bytes(), self.original)

    def test_prior_candidate_upgrades_idempotently_and_unknown_bytes_reject(self):
        previous = self.original[:4]+struct.pack('<I', len(self.previous)+8)+zlib.compress(self.previous, 1)
        self.assertEqual(PATCH.patch_client_bytes(previous), self.prepared)
        self.assertEqual(PATCH.patch_client_bytes(self.prepared), self.prepared)
        alternative = self.prepared[:8]+zlib.compress(zlib.decompress(self.prepared[8:]), 1)
        self.assertEqual(PATCH.patch_client_bytes(alternative), alternative)
        changed = bytearray(self.previous); changed[PATCH.WIDGET_STORAGE_METHODS[0][1]+1146] ^= 1
        with self.assertRaisesRegex(ValueError, 'refusing to modify unknown game code'):
            PATCH.patch_client_bytes(previous[:8]+zlib.compress(changed, 1))


if __name__ == '__main__':unittest.main()
