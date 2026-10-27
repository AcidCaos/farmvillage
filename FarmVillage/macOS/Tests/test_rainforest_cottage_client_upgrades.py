"""The final pinned client admits only the recovered rainforest craft upgrade."""
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
import cove_client as STAGE


class RainforestCottageClientUpgradeTests(unittest.TestCase):
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
                PATCH.MARKETSTALL_EXPANSION_EDITS, PATCH.WIDGET_STORAGE_EDITS,
                PATCH.REGIONAL_UPGRADE_EDITS, PATCH.OPTIONAL_BACKGROUND_EDITS):
            cls.previous = PATCH._apply_edits(cls.previous, edits)
        cls.prepared = PATCH.patch_client_bytes(cls.original)
        cls.body = zlib.decompress(cls.prepared[8:])
        cls.before, cls.after = read_abcs(cls.previous), read_abcs(cls.body)

    def test_only_three_appended_strings_and_one_method_change_after_previous_final(self):
        self.assertEqual(hashlib.sha256(self.previous).hexdigest(), STAGE.SOURCE_BODY_SHA256)
        self.assertEqual(hashlib.sha256(self.body).hexdigest(),
                         "51c484d32ac455abd3669fe1e96bd2cf17303fcfd18a4d265cb9b2eb661ed8f9")
        self.assertEqual(hashlib.sha256(self.prepared).hexdigest(),
                         "9412a405b62ec59dd444445738360f0a648d5b7d1d9d021e0756aefca9d911b8")
        self.assertEqual(self.body, PATCH._apply_edits(self.previous, STAGE.EDITS))
        self.assertEqual(len(self.body) - len(self.previous), 28)
        self.assertEqual(struct.unpack_from("<I", self.prepared, 4)[0], 21_521_090)
        total, changed = 0, []
        self.assertEqual(len(self.before), len(self.after))
        for index, (before, after) in enumerate(zip(self.before, self.after)):
            if index == 0:
                self.assertEqual(len(before.strings), 178_452)
                self.assertEqual(after.strings, before.strings + ["pub", "restaurant", "xrfcrafttype"])
            else:
                self.assertEqual(after.strings, before.strings)
            for field in ("ints", "uints", "mn", "ns", "nssets", "methods", "instances", "classes"):
                self.assertEqual(getattr(before, field), getattr(after, field), (index, field))
            self.assertEqual([struct.pack("<d", x) for x in before.doubles],
                             [struct.pack("<d", x) for x in after.doubles])
            self.assertEqual(list(before.bodies), list(after.bodies))
            for ident, code in before.bodies.items():
                total += 1
                if code != after.bodies[ident]: changed.append((index, ident))
        self.assertEqual((total, changed), (68_492, [(0, 34693)]))
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(hashlib.sha256(self.original).hexdigest(), PATCH.SOURCE_SHA256)

    def test_unchanged_method_geometry_branch_targets_and_non_abc_assets(self):
        offset = STAGE.METHOD_OFFSET
        for body, start in ((self.previous, offset), (self.body, offset + 28)):
            header = ABC.R(body, start - 9)
            self.assertEqual([header.u30() for _ in range(6)], [34693, 13, 14, 12, 13, 1155])
            self.assertEqual(header.p, start)
            self.assertEqual(ABC.R(body, start + 1155).u30(), 0)
        old, new = self.before[0].bodies[34693], self.after[0].bodies[34693]
        self.assertEqual(len(new), 1155)
        self.assertEqual(old[:389], new[:389]); self.assertEqual(old[437:], new[437:])
        self.assertEqual(hashlib.sha256(old).hexdigest(), STAGE.METHOD_SOURCE_SHA256)
        self.assertEqual(hashlib.sha256(new).hexdigest(), STAGE.METHOD_PATCHED_SHA256)
        for code in (old, new):
            _, invalid, missing = self.branch_errors(code)
            self.assertEqual((invalid, missing), ([], []))
        def tags(body):
            position = (5 + 4 * (body[0] >> 3) + 7) // 8 + 4
            result = []
            while position < len(body):
                tag = struct.unpack_from("<H", body, position)[0]; position += 2
                kind, size = tag >> 6, tag & 63
                if size == 63:
                    size = struct.unpack_from("<I", body, position)[0]; position += 4
                result.append((kind, body[position:position + size])); position += size
                if kind == 0: break
            self.assertEqual(position, len(body))
            return result
        before, after = tags(self.previous), tags(self.body)
        self.assertEqual([k for k, _ in before], [k for k, _ in after])
        self.assertEqual([(k, len(a), len(b)) for (k, a), (_, b) in zip(before, after) if a != b],
                         [(82, 18_098_055, 18_098_083)])

    def predicate(self, abc, craft):
        reader, stack, peak = ABC.R(abc.bodies[34693], 389), [], 0
        instance, result = {"cottage": {"craftType": craft}}, None
        while reader.p < 437:
            opcode = reader.u8()
            if opcode == 0x02: pass
            elif opcode == 0x2c: stack.append(abc.strings[reader.u30()])
            elif opcode == 0x24: stack.append(reader.u8())
            elif opcode == 0x56:
                count = reader.u30(); stack.append([stack.pop() for _ in range(count)][::-1])
            elif opcode == 0xd0: stack.append(instance)
            elif opcode == 0x66: stack.append(stack.pop()[abc.short(reader.u30())])
            elif opcode == 0x46:
                method, count = abc.mname(reader.u30()), reader.u30(); self.assertEqual(count, 1)
                argument, receiver = stack.pop(), stack.pop()
                if method.endswith(":substr"):
                    self.assertEqual((receiver, argument), ("xukcraftingpub", 11)); stack.append(receiver[argument:])
                else:
                    self.assertTrue(method.endswith(":indexOf")); stack.append(receiver.index(argument) if argument in receiver else -1)
            elif opcode == 0xc0: stack.append(int(stack.pop()) + 1)
            elif opcode == 0x76: stack.append(bool(stack.pop()))
            elif opcode == 0xb0:
                right = stack.pop(); stack.append(stack.pop() >= right)
            elif opcode == 0x63:
                self.assertEqual(reader.u30(), 6); result = stack.pop()
            else: self.fail(f"Unexpected predicate opcode {opcode:#x}")
            peak = max(peak, len(stack))
        self.assertEqual((reader.p, stack, instance), (437, [], {"cottage": {"craftType": craft}}))
        self.assertLessEqual(peak, 7)
        return result

    def test_exact_seven_crafts_use_original_coin_cash_and_prerequisite_paths(self):
        previous = ("bakery", "winery", "perfumery", "pub", "xhdcrafttype")
        supported = (*previous, "restaurant", "xrfcrafttype")
        for craft in (*supported, "japan", "hawaii", "", "Xrfcrafttype", "xrfcrafttype ",
                      "xrfcrafting", "xrfcraftshop", "xukcraftingpub", None):
            before, after = self.predicate(self.before[0], craft), self.predicate(self.after[0], craft)
            self.assertIs(before, craft in previous); self.assertIs(after, craft in supported)
            for remaining, maximum, prereq in ((6, False, False), (0, False, False),
                    (-2, False, False), (0, True, False), (6, False, True), (0, False, True)):
                frame, info = self.execute_frame(self.after[0].bodies[34693], remaining,
                    max_level=maximum, prereq=prereq, supported=after)
                old_frame, old_info = self.execute_frame(self.before[0].bodies[34693], remaining,
                    max_level=maximum, prereq=prereq, supported=before)
                self.assertEqual(frame["coin"]["visible"], after and not maximum and remaining <= 0)
                self.assertEqual(frame["cash"]["visible"], after and not maximum and remaining > 0)
                self.assertEqual(frame["meter"], old_frame["meter"])
                for button in ("coin", "cash"):
                    self.assertEqual(frame[button].get("enabled"), old_frame[button].get("enabled"))
                if craft not in ("restaurant", "xrfcrafttype"): self.assertEqual((frame, info), (old_frame, old_info))

    def test_previous_final_cache_upgrade_idempotence_and_tamper_refusal(self):
        previous = self.original[:4] + struct.pack("<I", len(self.previous) + 8) + zlib.compress(self.previous, 1)
        self.assertEqual(PATCH.patch_client_bytes(previous), self.prepared)
        self.assertEqual(PATCH.patch_client_bytes(self.prepared), self.prepared)
        alternative = self.prepared[:8] + zlib.compress(self.body, 1)
        self.assertEqual(PATCH.patch_client_bytes(alternative), alternative)
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory)/"source.swf", Path(directory)/"output.swf"
            source.write_bytes(previous)
            self.assertEqual(PATCH.prepared_client(source), self.prepared)
            self.assertTrue(PATCH.patch_client_file(source, output))
            self.assertEqual((source.read_bytes(), output.read_bytes()), (previous, self.prepared))
            self.assertFalse(PATCH.patch_client_file(output, output))
            output.write_bytes(b"preserve destination")
            for body, offset in ((self.previous, 3_411_801),
                    (self.previous, STAGE.METHOD_OFFSET+389),
                    (self.body, 9_457_200)):
                changed = bytearray(body); changed[offset] ^= 1
                source.write_bytes(self.original[:4]+struct.pack("<I", len(changed)+8)+zlib.compress(changed, 1))
                with self.assertRaises(ValueError): PATCH.patch_client_file(source, output)
                self.assertEqual(output.read_bytes(), b"preserve destination")
            source.write_bytes(self.original)
            with mock.patch.object(PATCH, "PATCHED_BODY_SHA256", "0"*64):
                with self.assertRaisesRegex(ValueError, "did not produce the verified output"):
                    PATCH.patch_client_file(source, output)
            self.assertEqual(output.read_bytes(), b"preserve destination")
        self.assertEqual(self.source.read_bytes(), self.original)


if __name__ == "__main__": unittest.main()
