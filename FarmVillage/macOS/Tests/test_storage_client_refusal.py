"""Inventory storage expansion refuses visibly before optimistic local changes."""
import hashlib
import struct
import unittest
import zlib

from test_turbo_client_refusal import PATCH, ROOT, read_abcs


class StorageClientRefusalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = (ROOT / "embeds/Flash/v855097-855094/FarmGame.swf").read_bytes()
        cls.previous = zlib.decompress(cls.original[8:])
        for edits in (PATCH.EDITS, PATCH.MARKET_EDITS, PATCH.TAB_EDITS,
                      PATCH.SCRATCH_EDITS, PATCH.EMPTY_WORLD_EDITS,
                      PATCH.COTTAGE_EDITS, PATCH.COTTAGE_UPGRADE_EDITS, PATCH.TURBO_EDITS):
            cls.previous = PATCH._apply_edits(cls.previous, edits)
        cls.prepared = PATCH.patch_client_bytes(cls.original)
        cls.body = PATCH._apply_edits(cls.previous, PATCH.STORAGE_EDITS)
        cls.final_body = zlib.decompress(cls.prepared[8:])
        cls.old_abcs = read_abcs(cls.previous)
        cls.new_abcs = read_abcs(cls.body)

    def test_only_the_two_inventory_upgrade_entries_and_one_new_literal_change(self):
        self.assertEqual(len(self.old_abcs), len(self.new_abcs))
        changes = []
        total = 0
        for abc_index, (before, after) in enumerate(zip(self.old_abcs, self.new_abcs)):
            for name in ("methods", "mn", "ns", "nssets", "instances", "classes"):
                self.assertEqual(getattr(before, name), getattr(after, name), name)
            self.assertEqual(list(before.bodies), list(after.bodies))
            self.assertEqual(after.strings[:-1], before.strings)
            self.assertEqual(after.strings[-1], PATCH.STORAGE_MESSAGE)
            self.assertEqual(len(before.strings), PATCH.STORAGE_STRING_INDEX)
            for method, code in before.bodies.items():
                total += 1
                if code != after.bodies[method]:
                    changes.append((abc_index, method))
                    self.assertEqual(len(code), len(after.bodies[method]))
        self.assertEqual(total, 68_492)
        self.assertEqual(changes, [(0, 12421), (0, 12423)])
        self.assertEqual(self.body, PATCH._apply_edits(self.previous, PATCH.STORAGE_EDITS))
        self.assertEqual(len(self.body) - len(self.previous), PATCH.STORAGE_STRING_BYTES)

    def test_both_actual_entries_only_show_reason_and_return_without_state_access(self):
        abc = self.new_abcs[0]
        for ident, _, _, _, expected_sha in PATCH.STORAGE_METHODS:
            with self.subTest(method=ident):
                code = abc.bodies[ident]
                self.assertEqual(hashlib.sha256(code).hexdigest(), expected_sha)
                self.execute_refusal(abc, code)

    def execute_refusal(self, abc, code):
        instance = object()
        globals_ = {"Display:UI": "ui", "Display:GenericPopup": {"TYPE_OK": "ok"}}
        stack, messages = [], []
        position = 0

        def read_u30():
            nonlocal position
            value = shift = 0
            while True:
                byte = code[position]
                position += 1
                value |= (byte & 127) << shift
                if byte < 128:
                    return value
                shift += 7

        # Only the existing popup globals are available. Any attempted player,
        # dialog-button, building, balance, or transaction access fails here.
        for _ in range(40):
            opcode = code[position]
            position += 1
            if opcode in (0xf0, 0xf1):
                read_u30()
            elif opcode == 0xd0:
                stack.append(instance)
            elif opcode == 0x30:
                self.assertIs(stack.pop(), instance)
            elif opcode == 0x60:
                stack.append(globals_[abc.mname(read_u30())])
            elif opcode == 0x2c:
                stack.append(abc.strings[read_u30()])
            elif opcode == 0x66:
                name = abc.short(read_u30())
                stack.append(stack.pop()[name])
            elif opcode == 0x20:
                stack.append(None)
            elif opcode == 0x26:
                stack.append(True)
            elif opcode == 0x4f:
                self.assertEqual(abc.short(read_u30()), "displayMessage")
                count = read_u30()
                args = [stack.pop() for _ in range(count)][::-1]
                self.assertEqual(stack.pop(), "ui")
                messages.append(args)
            elif opcode == 0x47:
                self.assertEqual(stack, [])
                self.assertEqual(messages, [[PATCH.STORAGE_MESSAGE, "ok", None, "", True]])
                return
            else:
                self.fail(f"Unexpected storage upgrade opcode {opcode:#x} at {position - 1}")
        self.fail("Storage upgrade callback did not return.")

    def test_turbo_build_upgrades_and_final_build_remains_idempotent(self):
        previous = self.original[:4] + struct.pack("<I", len(self.previous) + 8) + zlib.compress(self.previous, 1)
        self.assertEqual(hashlib.sha256(self.previous).hexdigest(), PATCH.TURBO_BODY_SHA256)
        self.assertEqual(PATCH.patch_client_bytes(previous), self.prepared)
        self.assertEqual(PATCH.patch_client_bytes(self.prepared), self.prepared)
        alternative = self.prepared[:8] + zlib.compress(self.final_body, 1)
        self.assertEqual(PATCH.patch_client_bytes(alternative), alternative)

    def test_unknown_input_pool_or_upgrade_code_fails_closed(self):
        for offset in (3_411_801, PATCH.STORAGE_METHODS[0][1] + 8, PATCH.STORAGE_METHODS[1][1] + 8):
            altered = bytearray(self.previous)
            altered[offset] ^= 1
            unknown = self.original[:4] + struct.pack("<I", len(altered) + 8) + zlib.compress(altered, 1)
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, "refusing to modify unknown game code"):
                PATCH.patch_client_bytes(unknown)


if __name__ == "__main__":
    unittest.main()
