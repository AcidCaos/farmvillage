"""Execute the bounded cottage sprite selector and verify the complete delta."""

import hashlib
import importlib.util
from pathlib import Path
import struct
import unittest
import zlib


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("cottage_graphics_compatibility", ROOT / "client_compatibility.py")
PATCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PATCH)


class CottageClientGraphicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT / "embeds/Flash/v855097-855094/FarmGame.swf"
        cls.original = cls.source.read_bytes()
        previous = zlib.decompress(cls.original[8:])
        for edits in (PATCH.EDITS, PATCH.MARKET_EDITS, PATCH.TAB_EDITS,
                      PATCH.SCRATCH_EDITS, PATCH.EMPTY_WORLD_EDITS):
            previous = PATCH._apply_edits(previous, edits)
        cls.previous = previous
        cls.prepared = PATCH.patch_client_bytes(cls.original)
        cls.body = PATCH._apply_edits(previous, PATCH.COTTAGE_EDITS)
        assert zlib.decompress(cls.prepared[8:]) == PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(cls.body, PATCH.COTTAGE_UPGRADE_EDITS), PATCH.TURBO_EDITS), PATCH.STORAGE_EDITS), PATCH.INVITATION_EDITS), PATCH.VIP_EDITS), PATCH.MARKET_WALKTHROUGH_EDITS), PATCH.QUEST_CLOSE_EDITS), PATCH.IMAGE_ROW_EDITS), PATCH.INVENTORY_ART_EDITS), PATCH.MARKETSTALL_EXPANSION_EDITS), PATCH.WIDGET_STORAGE_EDITS), PATCH.REGIONAL_UPGRADE_EDITS), PATCH.OPTIONAL_BACKGROUND_EDITS), PATCH.COVE_UPGRADE_EDITS)

    def test_only_original_rendering_method_changes_and_all_headers_and_assets_remain(self):
        start = PATCH.COTTAGE_METHOD_CODE_OFFSET
        end = start + PATCH.COTTAGE_METHOD_CODE_BYTES
        self.assertEqual(hashlib.sha256(self.previous).hexdigest(), PATCH.EMPTY_WORLD_BODY_SHA256)
        self.assertEqual(hashlib.sha256(self.body).hexdigest(), PATCH.COTTAGE_GRAPHICS_BODY_SHA256)
        self.assertEqual(len(self.body), len(self.previous))
        # Complete byte equality outside this one method proves unchanged
        # other methods, pools, frames, tags, assets and exception tables.
        self.assertEqual(self.body[:start], self.previous[:start])
        self.assertEqual(self.body[end:], self.previous[end:])
        self.assertEqual(self.previous[start - 8:start].hex(), "bab0010202101120")
        self.assertEqual(hashlib.sha256(self.previous[start:end]).hexdigest(), PATCH.COTTAGE_METHOD_SOURCE_SHA256)
        self.assertEqual(hashlib.sha256(self.body[start:end]).hexdigest(), PATCH.COTTAGE_METHOD_PATCHED_SHA256)
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_emitted_selector_uses_stage_zero_until_craft_state_exists_and_preserves_all_levels(self):
        code = self.body[PATCH.COTTAGE_METHOD_CODE_OFFSET:
                         PATCH.COTTAGE_METHOD_CODE_OFFSET + PATCH.COTTAGE_METHOD_CODE_BYTES]

        def execute(craft_level):
            instance = {20251: craft_level}
            locals_ = {0: instance}
            stack = []
            position = 0

            def read_u30():
                nonlocal position
                value = shift = 0
                while True:
                    byte = code[position]; position += 1
                    value |= (byte & 127) << shift
                    if byte < 128:
                        return value
                    shift += 7

            for _ in range(40):
                opcode = code[position]; position += 1
                if opcode in (0xf0, 0xf1):
                    read_u30()
                elif opcode in (0xd0, 0xd1):
                    stack.append(locals_[opcode - 0xd0])
                elif opcode == 0x30:
                    self.assertIs(stack.pop(), instance)
                elif opcode == 0x66:
                    self.assertEqual(read_u30(), 20251)
                    stack.append(stack.pop()[20251])
                elif opcode == 0x93:
                    stack.append(stack.pop() - 1)
                elif opcode == 0x73:
                    stack.append(int(stack.pop()))
                elif opcode == 0xd5:
                    locals_[1] = stack.pop()
                elif opcode == 0x24:
                    stack.append(int.from_bytes(code[position:position + 1], "little", signed=True)); position += 1
                elif opcode == 0x18:
                    delta = int.from_bytes(code[position:position + 3], "little", signed=True); position += 3
                    right = stack.pop()
                    if stack.pop() >= right:
                        position += delta
                elif opcode == 0x48:
                    result = stack.pop()
                    self.assertEqual(instance, {20251: craft_level})
                    self.assertEqual(stack, [])
                    return result
                else:
                    self.fail(f"Unexpected cottage image opcode {opcode:#x} at {position - 1}")
                self.assertLessEqual(len(stack), 2)  # Original maxstack remains sufficient.
            self.fail("Cottage image selector did not return.")

        self.assertEqual(execute(0), 0)
        self.assertEqual(execute(-1), 0)
        for level in range(1, 6):
            with self.subTest(level=level):
                self.assertEqual(execute(level), level - 1)

    def test_previous_prepared_client_upgrades_idempotently_and_unknown_code_rejects(self):
        previous = self.original[:4] + struct.pack("<I", len(self.previous) + 8) + zlib.compress(self.previous, 1)
        self.assertEqual(PATCH.patch_client_bytes(previous), self.prepared)
        self.assertEqual(PATCH.patch_client_bytes(self.prepared), self.prepared)
        for offset in (PATCH.COTTAGE_METHOD_CODE_OFFSET, 10):
            altered = bytearray(self.previous)
            altered[offset] ^= 1
            unknown = previous[:8] + zlib.compress(altered, 1)
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, "refusing to modify unknown game code"):
                PATCH.patch_client_bytes(unknown)


if __name__ == "__main__":
    unittest.main()
