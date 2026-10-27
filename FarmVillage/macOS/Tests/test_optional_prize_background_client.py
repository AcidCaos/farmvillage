"""Skip only absent optional prize artwork in the original client constructor."""
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock
import zlib

from test_turbo_client_refusal import PATCH, ROOT, ABC, read_abcs
import test_image_row_client as image_tests


class OptionalPrizeBackgroundClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT / 'embeds/Flash/v855097-855094/FarmGame.swf'
        cls.original = cls.source.read_bytes()
        cls.previous = zlib.decompress(cls.original[8:])
        for edits in (PATCH.EDITS, PATCH.MARKET_EDITS, PATCH.TAB_EDITS,
                PATCH.SCRATCH_EDITS, PATCH.EMPTY_WORLD_EDITS, PATCH.COTTAGE_EDITS,
                PATCH.COTTAGE_UPGRADE_EDITS, PATCH.TURBO_EDITS, PATCH.STORAGE_EDITS,
                PATCH.INVITATION_EDITS, PATCH.VIP_EDITS, PATCH.MARKET_WALKTHROUGH_EDITS,
                PATCH.QUEST_CLOSE_EDITS, PATCH.IMAGE_ROW_EDITS, PATCH.INVENTORY_ART_EDITS,
                PATCH.MARKETSTALL_EXPANSION_EDITS, PATCH.WIDGET_STORAGE_EDITS,
                PATCH.REGIONAL_UPGRADE_EDITS):
            cls.previous = PATCH._apply_edits(cls.previous, edits)
        cls.prepared = PATCH.patch_client_bytes(cls.original)
        # Retain this historical stage receipt; the final client adds Cove.
        cls.body = PATCH._apply_edits(cls.previous, PATCH.OPTIONAL_BACKGROUND_EDITS)
        cls.historical = cls.original[:4] + struct.pack("<I", len(cls.body)+8) + zlib.compress(cls.body, 9)
        cls.before, cls.after = read_abcs(cls.previous), read_abcs(cls.body)

    def test_exact_two_bytes_and_one_method_with_identical_pools_and_metadata(self):
        self.assertEqual(hashlib.sha256(self.previous).hexdigest(), PATCH.REGIONAL_UPGRADE_BODY_SHA256)
        self.assertEqual(hashlib.sha256(self.body).hexdigest(),
                         '2200ebcdc58dfa2061ffaf20e58f8c83b1868449a6b8bae8f81395c27a0454c6')
        self.assertEqual(hashlib.sha256(self.historical).hexdigest(),
                         'b5a8949100498151eeeadb561ad01c7a87778c2c4db6f8b2cdc129f642dd29d3')
        self.assertEqual(len(self.body), len(self.previous))
        self.assertEqual(struct.unpack_from('<I', self.historical, 4)[0], 21_521_062)
        self.assertEqual([i for i, (a, b) in enumerate(zip(self.previous, self.body)) if a != b],
                         [19_292_764, 19_292_765])
        total, changed = 0, []
        self.assertEqual(len(self.before), len(self.after))
        for index, (before, after) in enumerate(zip(self.before, self.after)):
            for field in ('strings', 'ints', 'uints', 'mn', 'ns', 'nssets', 'methods', 'instances', 'classes'):
                self.assertEqual(getattr(before, field), getattr(after, field), (index, field))
            self.assertEqual([struct.pack('<d', x) for x in before.doubles],
                             [struct.pack('<d', x) for x in after.doubles])
            self.assertEqual(list(before.bodies), list(after.bodies))
            for ident, code in before.bodies.items():
                total += 1
                if code != after.bodies[ident]: changed.append((index, ident))
        self.assertEqual((total, changed), (68_492, [(0, 54167)]))
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_headers_exception_geometry_and_branch_targets_are_unchanged(self):
        start, length = PATCH.OPTIONAL_BACKGROUND_METHOD_CODE_OFFSET, 153
        self.assertEqual(self.previous[start - 9:start], self.body[start - 9:start])
        header = ABC.R(self.body, start - 9)
        values = [header.u30() for _ in range(6)]
        self.assertEqual((values[0], values[-1], header.p), (54167, 153, start))
        self.assertGreaterEqual(values[1], 2)
        self.assertEqual(ABC.R(self.body, start + length).u30(), 0)
        old, new = self.before[0].bodies[54167], self.after[0].bodies[54167]
        self.assertEqual((len(old), len(new)), (153, 153))
        self.assertEqual(old[:102], new[:102])
        self.assertEqual(old[104:], new[104:])
        self.assertEqual((old[102:104], new[102:104]), (b'\x20\x13', b'\x76\x12'))
        self.assertEqual(hashlib.sha256(old).hexdigest(), PATCH.OPTIONAL_BACKGROUND_METHOD_SOURCE_SHA256)
        self.assertEqual(hashlib.sha256(new).hexdigest(), PATCH.OPTIONAL_BACKGROUND_METHOD_PATCHED_SHA256)
        self.assertEqual(107 + int.from_bytes(new[104:107], 'little', signed=True), 150)
        for code in (old, new):
            _, invalid, missing = image_tests.ImageRowClientTests.branch_errors(self, code)
            self.assertEqual((invalid, missing), ([], []))

    def branch_loads(self, code, background):
        reader, stack, peak = ABC.R(code, 97), [], 0
        while reader.p < 107:
            opcode = reader.u8()
            if opcode == 0xd0:
                stack.append({'m_dialogBackground': background})
            elif opcode == 0x66:
                self.assertTrue(self.after[0].mname(reader.u30()).endswith(':m_dialogBackground'))
                stack.append(stack.pop()['m_dialogBackground'])
            elif opcode == 0x20:
                stack.append(None)
            elif opcode == 0x76:
                stack.append(bool(stack.pop()))
            elif opcode in (0x12, 0x13):
                delta = reader.s24()
                if opcode == 0x12: take = not stack.pop()
                else:
                    right = stack.pop(); take = stack.pop() == right
                if take: reader.p += delta
            else:
                self.fail(f'Unexpected optional-background guard opcode {opcode:#x}')
            peak = max(peak, len(stack))
        self.assertEqual(stack, [])
        self.assertIn(reader.p, (107, 150))
        return reader.p == 107, peak

    def test_null_and_empty_skip_but_all_nonempty_strings_retain_original_loader_path(self):
        old, new = self.before[0].bodies[54167], self.after[0].bodies[54167]
        for value in (None, '', 'assets/dialogs/valid-background.swf', '0', 'false', ' '):
            with self.subTest(background=value):
                before, old_peak = self.branch_loads(old, value)
                after, new_peak = self.branch_loads(new, value)
                self.assertEqual(before, value is not None)
                self.assertEqual(after, value not in (None, ''))
                self.assertEqual((old_peak, new_peak), (2, 1))
        # Main-dialog constructor, reward/owner assignments, actual background
        # URL/ImageLoader/getContent/onBgLoad path and return remain byte exact.
        self.assertEqual(old[:102], new[:102])
        self.assertEqual(old[107:], new[107:])

    def test_prior_regional_stage_and_original_reach_same_final_and_cache_is_content_based(self):
        previous = self.original[:4] + struct.pack('<I', len(self.previous) + 8) + zlib.compress(self.previous, 1)
        self.assertEqual(PATCH.patch_client_bytes(previous), self.prepared)
        self.assertEqual(PATCH.patch_client_bytes(self.prepared), self.prepared)
        alternative = self.prepared[:8] + zlib.compress(zlib.decompress(self.prepared[8:]), 1)
        self.assertEqual(PATCH.patch_client_bytes(alternative), alternative)
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / 'source.swf', Path(directory) / 'output.swf'
            source.write_bytes(self.original)
            self.assertEqual(PATCH.prepared_client(source), self.prepared)
            source.write_bytes(previous)
            self.assertEqual(PATCH.prepared_client(source), self.prepared)
            self.assertTrue(PATCH.patch_client_file(source, output))
            self.assertEqual((source.read_bytes(), output.read_bytes()), (previous, self.prepared))
            self.assertFalse(PATCH.patch_client_file(output, output))

    def test_tampered_prior_final_or_final_pin_never_replaces_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / 'source.swf', Path(directory) / 'output.swf'
            output.write_bytes(b'keep destination')
            for body, offset in ((self.previous, 19_292_764), (self.body, 19_292_765)):
                changed = bytearray(body); changed[offset] ^= 1
                source.write_bytes(self.original[:4] + struct.pack('<I', len(changed) + 8) + zlib.compress(changed, 1))
                with self.assertRaises(ValueError): PATCH.patch_client_file(source, output)
                self.assertEqual(output.read_bytes(), b'keep destination')
            source.write_bytes(self.original)
            with mock.patch.object(PATCH, 'PATCHED_BODY_SHA256', '0' * 64):
                with self.assertRaisesRegex(ValueError, 'did not produce the verified output'):
                    PATCH.patch_client_file(source, output)
            self.assertEqual(output.read_bytes(), b'keep destination')


if __name__ == '__main__':
    unittest.main()
