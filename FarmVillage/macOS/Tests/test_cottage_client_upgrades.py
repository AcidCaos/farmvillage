"""Unsupported cottage upgrade buttons and instructions stay unavailable."""

import hashlib
import importlib.util
from pathlib import Path
import struct
import unittest
import zlib


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("cottage_upgrade_compatibility", ROOT / "client_compatibility.py")
PATCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PATCH)


class CottageClientUpgradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT / "embeds/Flash/v855097-855094/FarmGame.swf"
        cls.original = cls.source.read_bytes()
        cls.previous = zlib.decompress(cls.original[8:])
        for edits in (PATCH.EDITS, PATCH.MARKET_EDITS, PATCH.TAB_EDITS,
                      PATCH.SCRATCH_EDITS, PATCH.EMPTY_WORLD_EDITS, PATCH.COTTAGE_EDITS):
            cls.previous = PATCH._apply_edits(cls.previous, edits)
        cls.prepared = PATCH.patch_client_bytes(cls.original)
        cls.body = PATCH._apply_edits(cls.previous, PATCH.COTTAGE_UPGRADE_EDITS)
        assert zlib.decompress(cls.prepared[8:]) == PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(cls.body, PATCH.TURBO_EDITS), PATCH.STORAGE_EDITS), PATCH.INVITATION_EDITS), PATCH.VIP_EDITS), PATCH.MARKET_WALKTHROUGH_EDITS), PATCH.QUEST_CLOSE_EDITS), PATCH.IMAGE_ROW_EDITS), PATCH.INVENTORY_ART_EDITS), PATCH.MARKETSTALL_EXPANSION_EDITS), PATCH.WIDGET_STORAGE_EDITS), PATCH.REGIONAL_UPGRADE_EDITS), PATCH.OPTIONAL_BACKGROUND_EDITS), PATCH.COVE_UPGRADE_EDITS)
        start = PATCH.COTTAGE_UPGRADE_METHOD_CODE_OFFSET
        cls.before_code = cls.previous[start:start + 1155]
        # Preserve this historical gate test independently of its later restoration.
        cls.code = cls.body[start:start + 1155]

    def test_exact_five_byte_delta_preserves_prices_progress_headers_branches_and_assets(self):
        self.assertEqual(hashlib.sha256(self.previous).hexdigest(), PATCH.COTTAGE_GRAPHICS_BODY_SHA256)
        self.assertEqual(hashlib.sha256(self.body).hexdigest(), PATCH.COTTAGE_UPGRADE_BODY_SHA256)
        start = PATCH.COTTAGE_UPGRADE_METHOD_CODE_OFFSET
        differences = [i for i, (old, new) in enumerate(zip(self.previous, self.body)) if old != new]
        self.assertEqual(differences, [start + i for i in (683, 796, 989, 990, 991)])
        self.assertEqual(len(self.previous), len(self.body))
        self.assertEqual(hashlib.sha256(self.before_code).hexdigest(), PATCH.COTTAGE_UPGRADE_METHOD_SOURCE_SHA256)
        self.assertEqual(hashlib.sha256(self.code).hexdigest(), PATCH.COTTAGE_UPGRADE_METHOD_PATCHED_SHA256)
        self.assertEqual(self.code[1021:], self.before_code[1021:])  # Original price tooltip and craft-level logic.
        self.assertEqual(self.source.read_bytes(), self.original)
        # Pool zero is the parser sentinel, not the original runtime literal.
        self.assertEqual(self.before_code[696:698], bytes.fromhex("2c01"))
        self.assertEqual(self.before_code[828:830], bytes.fromhex("2c01"))
        self.assertEqual(self.code[989:992], bytes.fromhex("2c01d5"))

    def execute_frame(self, code, remaining_xp, *, max_level=False, prereq=False, supported=False):
        # Execute the real XP visibility branch and final label/tooltip writes.
        # The original progress/star arithmetic precedes this span and remains
        # byte-identical; the price tooltip follows it and also remains intact.
        names = {108947: "frame", 108948: "coin", 108949: "cash", 108970: "visible",
                 108956: "meter", 108957: "bar", 108973: "width", 108950: "message",
                 108974: "text", 30343: "tooltip", 30331: "widgetFrame", 16439: "prereq"}
        frame = {"coin": {"visible": True}, "cash": {"visible": True},
                 "meter": {"width": 100, "bar": {"width": 37}}, "message": {"text": "old"}}
        window = {"frame": frame}
        instance = {"tooltip": {"text": "old"}, "widgetFrame": "widget-frame"}
        locals_ = {0: instance, 1: "old", 3: {"prereq": "region" if prereq else ""},
                   6: supported, 8: remaining_xp, 13: "legacy region instruction"}
        stack = []
        position = 894 if max_level else 612

        def read_u30():
            nonlocal position
            value = shift = 0
            while True:
                byte = code[position]; position += 1
                value |= (byte & 127) << shift
                if byte < 128:
                    return value
                shift += 7

        for _ in range(220):
            if position == 1021:
                self.assertEqual(stack, [])
                return frame, instance
            opcode = code[position]; position += 1
            if opcode == 0x02:
                continue
            if opcode == 0xf0:
                read_u30()
            elif opcode in (0xd0, 0xd1, 0xd3):
                stack.append(locals_[opcode - 0xd0])
            elif opcode == 0xd5:
                locals_[1] = stack.pop()
            elif opcode == 0x62:
                stack.append(locals_[read_u30()])
            elif opcode == 0x60:
                field = read_u30()
                stack.append({2001: window, 3358: "localizer", 10561: "prereqs", 576: "button-class"}[field])
            elif opcode == 0x66:
                field = names[read_u30()]; stack.append(stack.pop()[field])
            elif opcode == 0x61:
                field = names[read_u30()]; value = stack.pop(); stack.pop()[field] = value
            elif opcode == 0x24:
                stack.append(int.from_bytes(code[position:position + 1], "little", signed=True)); position += 1
            elif opcode in (0x26, 0x27):
                stack.append(opcode == 0x26)
            elif opcode == 0x2c:
                index = read_u30()
                self.assertGreater(index, 0, "PushString requires a nonzero archived constant-pool entry.")
                stack.append("" if index == 1 else f"string-{index}")
            elif opcode == 0x55:
                pairs = [(stack.pop(), stack.pop()) for _ in range(read_u30())]
                stack.append({key: value for value, key in pairs})
            elif opcode in (0x46, 0x4f):
                method = read_u30(); count = read_u30()
                args = [stack.pop() for _ in range(count)][::-1]; receiver = stack.pop()
                if method == 24750:
                    self.assertEqual(receiver, "localizer"); result = "unaccepted upgrade instruction"
                elif method == 79836:
                    self.assertEqual(receiver, "prereqs"); result = False
                elif method == 5147:
                    self.assertEqual(receiver, "widget-frame"); result = args[0]
                elif method == 5159:
                    receiver["enabled"] = args[0]; result = None
                elif method == 5213:
                    receiver["text"] = args[0]; result = None
                else:
                    self.fail(f"Unexpected upgrade UI method {method}")
                if opcode == 0x46:
                    stack.append(result)
            elif opcode == 0x85:
                stack.append(str(stack.pop()))
            elif opcode == 0x87:
                self.assertEqual(stack.pop(), "button-class")
            elif opcode == 0xab:
                stack.append(stack.pop() == stack.pop())
            elif opcode == 0x96:
                stack.append(not stack.pop())
            elif opcode == 0x2a:
                stack.append(stack[-1])
            elif opcode == 0x29:
                stack.pop()
            elif opcode in (0x10, 0x12, 0x0e):
                delta = int.from_bytes(code[position:position + 3], "little", signed=True); position += 3
                if opcode == 0x10:
                    branch = True
                elif opcode == 0x12:
                    branch = not stack.pop()
                else:
                    right = stack.pop(); branch = not stack.pop() > right
                if branch:
                    position += delta
            else:
                self.fail(f"Unexpected upgrade opcode {opcode:#x} at {position - 1}")
        self.fail("Upgrade presentation did not finish.")

    def test_emitted_cash_coin_and_max_level_paths_hide_both_controls_and_upgrade_instructions(self):
        for remaining, maximum, prereq in ((6, False, False), (0, False, False),
                                           (-2, False, False), (6, False, True),
                                           (0, False, True), (0, True, False)):
            with self.subTest(remaining_xp=remaining, max_level=maximum, prereq=prereq):
                old, old_instance = self.execute_frame(self.before_code, remaining, max_level=maximum, prereq=prereq)
                new, new_instance = self.execute_frame(self.code, remaining, max_level=maximum, prereq=prereq)
                self.assertFalse(new["coin"]["visible"])
                self.assertFalse(new["cash"]["visible"])
                self.assertEqual(new["message"]["text"], "")
                self.assertEqual(new_instance["tooltip"]["text"], "")
                self.assertNotEqual(old["message"]["text"], "")
                self.assertEqual(new["meter"], old["meter"])
                if not maximum:
                    self.assertTrue(old["cash" if remaining > 0 else "coin"]["visible"])
        invalid = bytearray(self.code)
        invalid[990] = 0  # The rejected development candidate used the parser sentinel.
        with self.assertRaisesRegex(AssertionError, "nonzero archived constant-pool"):
            self.execute_frame(invalid, 6)

    def test_previous_graphics_build_upgrades_and_unknown_code_cannot_replace_output(self):
        previous = self.original[:4] + struct.pack("<I", len(self.previous) + 8) + zlib.compress(self.previous, 1)
        self.assertEqual(PATCH.patch_client_bytes(previous), self.prepared)
        self.assertEqual(PATCH.patch_client_bytes(self.prepared), self.prepared)
        altered = bytearray(self.previous); altered[PATCH.COTTAGE_UPGRADE_METHOD_CODE_OFFSET + 10] ^= 1
        with self.assertRaisesRegex(ValueError, "refusing to modify unknown game code"):
            PATCH.patch_client_bytes(previous[:8] + zlib.compress(altered, 1))


if __name__ == "__main__":
    unittest.main()
