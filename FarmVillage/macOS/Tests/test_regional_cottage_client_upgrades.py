"""The prepared upgrade gate adds only the recovered Mistletoe craft."""
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock
import zlib

from test_turbo_client_refusal import PATCH, ROOT, ABC, read_abcs
import test_cottage_client_upgrades as cottage_upgrade_tests
import test_image_row_client as image_tests


class RegionalCottageClientUpgradeTests(unittest.TestCase):
    execute_frame = cottage_upgrade_tests.CottageClientUpgradeTests.execute_frame
    branch_errors = image_tests.ImageRowClientTests.branch_errors

    @classmethod
    def setUpClass(cls):
        cls.source = ROOT / "embeds/Flash/v855097-855094/FarmGame.swf"
        cls.original = cls.source.read_bytes()
        cls.previous = zlib.decompress(cls.original[8:])
        for edits in (PATCH.EDITS, PATCH.MARKET_EDITS, PATCH.TAB_EDITS,
                      PATCH.SCRATCH_EDITS, PATCH.EMPTY_WORLD_EDITS, PATCH.COTTAGE_EDITS,
                      PATCH.COTTAGE_UPGRADE_EDITS, PATCH.TURBO_EDITS, PATCH.STORAGE_EDITS,
                      PATCH.INVITATION_EDITS, PATCH.VIP_EDITS, PATCH.MARKET_WALKTHROUGH_EDITS,
                      PATCH.QUEST_CLOSE_EDITS, PATCH.IMAGE_ROW_EDITS, PATCH.INVENTORY_ART_EDITS,
                      PATCH.MARKETSTALL_EXPANSION_EDITS, PATCH.WIDGET_STORAGE_EDITS):
            cls.previous = PATCH._apply_edits(cls.previous, edits)
        cls.body = PATCH._apply_edits(cls.previous, PATCH.REGIONAL_UPGRADE_EDITS)
        cls.prepared = cls.original[:4] + struct.pack("<I", len(cls.body) + 8) + zlib.compress(cls.body, 9)
        cls.final = PATCH.patch_client_bytes(cls.original)
        cls.before, cls.after = read_abcs(cls.previous), read_abcs(cls.body)

    def test_one_appended_literal_and_one_method_are_the_entire_final_stage(self):
        self.assertEqual(hashlib.sha256(self.previous).hexdigest(), PATCH.WIDGET_STORAGE_BODY_SHA256)
        self.assertEqual(hashlib.sha256(self.body).hexdigest(),
                         "0a1e5b2689cd203c40a8d9694740a0929a88b986172bdf3b0b670baaceb182ed")
        self.assertEqual(hashlib.sha256(self.prepared).hexdigest(),
                         "7c3d57a027c0df270c6b05c9da89a7f244de70a97bba71675585caadc604699d")
        self.assertEqual(self.body, PATCH._apply_edits(self.previous, PATCH.REGIONAL_UPGRADE_EDITS))
        self.assertEqual(len(self.body) - len(self.previous), 13)
        self.assertEqual(struct.unpack_from("<I", self.prepared, 4)[0], 21_521_062)
        total, changed = 0, []
        self.assertEqual(len(self.before), len(self.after))
        for index, (before, after) in enumerate(zip(self.before, self.after)):
            if index == 0:
                self.assertEqual(len(before.strings), 178_451)
                self.assertEqual(after.strings, before.strings + ["xhdcrafttype"])
            else:
                self.assertEqual(after.strings, before.strings)
            for field in ("ints", "uints", "mn", "ns", "nssets", "methods", "instances", "classes"):
                self.assertEqual(getattr(before, field), getattr(after, field), (index, field))
            self.assertEqual([struct.pack("<d", x) for x in before.doubles],
                             [struct.pack("<d", x) for x in after.doubles])
            self.assertEqual(list(before.bodies), list(after.bodies))
            for ident, code in before.bodies.items():
                total += 1
                if code != after.bodies[ident]:
                    changed.append((index, ident))
        self.assertEqual((total, changed), (68_492, [(0, 34693)]))
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(hashlib.sha256(self.original).hexdigest(), PATCH.SOURCE_SHA256)

    def test_method_headers_exceptions_branches_and_all_other_tags_are_preserved(self):
        offset = PATCH.REGIONAL_UPGRADE_METHOD_CODE_OFFSET
        for body, start in ((self.previous, offset), (self.body, offset + 13)):
            header = ABC.R(body, start - 9)
            self.assertEqual([header.u30() for _ in range(6)], [34693, 13, 14, 12, 13, 1155])
            self.assertEqual(header.p, start)
            self.assertEqual(ABC.R(body, start + 1155).u30(), 0)
        old, new = self.before[0].bodies[34693], self.after[0].bodies[34693]
        self.assertEqual(len(new), 1155)
        self.assertEqual(old[:389], new[:389])
        self.assertEqual(old[437:], new[437:])
        self.assertEqual(hashlib.sha256(old).hexdigest(), PATCH.REGIONAL_UPGRADE_METHOD_SOURCE_SHA256)
        self.assertEqual(hashlib.sha256(new).hexdigest(), PATCH.REGIONAL_UPGRADE_METHOD_PATCHED_SHA256)
        for code in (old, new):
            _, invalid, missing_labels = self.branch_errors(code)
            self.assertEqual((invalid, missing_labels), ([], []))
        # The edited span has no branches. Every original branch byte and
        # instruction offset stays fixed by the two unchanged method slices.
        def tags(body):
            position = (5 + 4 * (body[0] >> 3) + 7) // 8 + 4
            result = []
            while position < len(body):
                tag = struct.unpack_from("<H", body, position)[0]; position += 2
                kind, size = tag >> 6, tag & 63
                if size == 63:
                    size = struct.unpack_from("<I", body, position)[0]; position += 4
                result.append((kind, body[position:position + size]))
                position += size
                if kind == 0:
                    break
            self.assertEqual(position, len(body))
            return result
        before, after = tags(self.previous), tags(self.body)
        self.assertEqual([kind for kind, _ in before], [kind for kind, _ in after])
        changed = [(kind, len(a), len(b)) for (kind, a), (_, b) in zip(before, after) if a != b]
        self.assertEqual(changed, [(82, 18_098_042, 18_098_055)])

    def predicate(self, abc, craft):
        code, position, stack, peak = abc.bodies[34693], 389, [], 0
        instance, result = {"cottage": {"craftType": craft}}, None
        reader = ABC.R(code, position)
        while reader.p < 437:
            opcode = reader.u8()
            if opcode == 0x02:
                pass
            elif opcode == 0x2c:
                stack.append(abc.strings[reader.u30()])
            elif opcode == 0x24:
                stack.append(reader.u8())
            elif opcode == 0x56:
                count = reader.u30()
                stack.append([stack.pop() for _ in range(count)][::-1])
            elif opcode == 0xd0:
                stack.append(instance)
            elif opcode == 0x66:
                stack.append(stack.pop()[abc.short(reader.u30())])
            elif opcode == 0x46:
                method, count = abc.mname(reader.u30()), reader.u30()
                self.assertEqual(count, 1)
                argument, receiver = stack.pop(), stack.pop()
                if method.endswith(":substr"):
                    self.assertEqual((receiver, argument), ("xukcraftingpub", 11))
                    stack.append(receiver[argument:])
                else:
                    self.assertTrue(method.endswith(":indexOf"))
                    stack.append(receiver.index(argument) if argument in receiver else -1)
            elif opcode == 0xb0:
                right = stack.pop(); stack.append(stack.pop() >= right)
            elif opcode == 0x63:
                self.assertEqual(reader.u30(), 6)
                result = stack.pop()
            else:
                self.fail(f"Unexpected predicate opcode {opcode:#x}")
            peak = max(peak, len(stack))
        self.assertEqual((reader.p, stack, instance), (437, [], {"cottage": {"craftType": craft}}))
        self.assertEqual(peak, 5)  # Both candidates fit the unchanged max_stack=13.
        return result

    def test_original_four_and_only_exact_regional_type_reach_original_upgrade_paths(self):
        classics = ("bakery", "winery", "perfumery", "pub")
        for craft in (*classics, "xhdcrafttype", "xrfcrafttype", "japan", "hawaii", "",
                      "Xhdcrafttype", "xhdcrafttype ", "xukcraftingpub", None):
            before, after = self.predicate(self.before[0], craft), self.predicate(self.after[0], craft)
            self.assertIs(before, craft in classics)
            self.assertIs(after, craft in (*classics, "xhdcrafttype"))
            for remaining, maximum, prereq in ((6, False, False), (0, False, False),
                                               (-2, False, False), (0, True, False),
                                               (6, False, True), (0, False, True)):
                frame, info = self.execute_frame(self.after[0].bodies[34693], remaining,
                    max_level=maximum, prereq=prereq, supported=after)
                old_frame, old_info = self.execute_frame(self.before[0].bodies[34693], remaining,
                    max_level=maximum, prereq=prereq, supported=before)
                self.assertEqual(frame["coin"]["visible"], after and not maximum and remaining <= 0)
                self.assertEqual(frame["cash"]["visible"], after and not maximum and remaining > 0)
                self.assertEqual(frame["meter"], old_frame["meter"])
                for button in ("coin", "cash"):
                    self.assertEqual(frame[button].get("enabled"), old_frame[button].get("enabled"))
                if craft != "xhdcrafttype":
                    self.assertEqual((frame, info), (old_frame, old_info))

    def test_prior_prepared_stage_and_content_cache_upgrade_without_touching_source(self):
        previous = self.original[:4] + struct.pack("<I", len(self.previous) + 8) + zlib.compress(self.previous, 1)
        self.assertEqual(PATCH.patch_client_bytes(previous), self.final)
        self.assertEqual(PATCH.patch_client_bytes(self.final), self.final)
        alternative = self.final[:8] + zlib.compress(zlib.decompress(self.final[8:]), 1)
        self.assertEqual(PATCH.patch_client_bytes(alternative), alternative)
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "source.swf", Path(directory) / "output.swf"
            source.write_bytes(self.original)
            self.assertEqual(PATCH.prepared_client(source), self.final)
            source.write_bytes(previous)
            self.assertEqual(PATCH.prepared_client(source), self.final)
            self.assertTrue(PATCH.patch_client_file(source, output))
            self.assertEqual((source.read_bytes(), output.read_bytes()), (previous, self.final))
            self.assertFalse(PATCH.patch_client_file(output, output))
            source.write_bytes(b"unknown replaced client")
            with self.assertRaises(ValueError):
                PATCH.prepared_client(source)
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_bad_pool_method_or_final_pin_cannot_replace_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "source.swf", Path(directory) / "output.swf"
            output.write_bytes(b"keep previous destination")
            for original, body, offset in ((self.original, self.previous, 3_411_801),
                    (self.original, self.previous, PATCH.REGIONAL_UPGRADE_METHOD_CODE_OFFSET + 389),
                    (self.prepared, self.body, 9_457_188)):
                changed = bytearray(body); changed[offset] ^= 1
                source.write_bytes(original[:4] + struct.pack("<I", len(body) + 8) + zlib.compress(changed, 1))
                with self.assertRaises(ValueError):
                    PATCH.patch_client_file(source, output)
                self.assertEqual(output.read_bytes(), b"keep previous destination")
            source.write_bytes(self.original)
            with mock.patch.object(PATCH, "PATCHED_BODY_SHA256", "0" * 64):
                with self.assertRaisesRegex(ValueError, "did not produce the verified output"):
                    PATCH.patch_client_file(source, output)
            self.assertEqual(output.read_bytes(), b"keep previous destination")


if __name__ == "__main__":
    unittest.main()
