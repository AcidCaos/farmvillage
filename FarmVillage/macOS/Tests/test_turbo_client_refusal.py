"""Keep unsupported Turbo purchases visible without optimistic client charges."""

import hashlib
import importlib.util
from pathlib import Path
import struct
import unittest
import zlib


ROOT = Path(__file__).resolve().parents[2]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PATCH = load_module("turbo_compatibility", ROOT / "client_compatibility.py")
ABC = load_module("turbo_abc_reader", ROOT / "macOS/Scripts/client-inspection/abcdis.py")


def read_abcs(body):
    """Parse bytes in memory; never create an inspection cache by source assets."""
    bits = body[0] >> 3
    position = (5 + 4 * bits + 7) // 8 + 4
    result = []
    while position < len(body):
        tag = struct.unpack_from("<H", body, position)[0]
        position += 2
        kind, length = tag >> 6, tag & 63
        if length == 63:
            length = struct.unpack_from("<I", body, position)[0]
            position += 4
        if kind == 82:
            start = body.index(0, position + 4, position + length) + 1
            result.append(ABC.ABC(body[start:position + length]))
        position += length
        if kind == 0:
            break
    return result


class TurboClientRefusalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = (ROOT / "embeds/Flash/v855097-855094/FarmGame.swf").read_bytes()
        cls.previous = zlib.decompress(cls.original[8:])
        for edits in (PATCH.EDITS, PATCH.MARKET_EDITS, PATCH.TAB_EDITS,
                      PATCH.SCRATCH_EDITS, PATCH.EMPTY_WORLD_EDITS,
                      PATCH.COTTAGE_EDITS, PATCH.COTTAGE_UPGRADE_EDITS):
            cls.previous = PATCH._apply_edits(cls.previous, edits)
        cls.prepared = PATCH.patch_client_bytes(cls.original)
        # Review Turbo's own intermediate stage independently of later gates.
        cls.body = PATCH._apply_edits(cls.previous, PATCH.TURBO_EDITS)
        cls.final_body = zlib.decompress(cls.prepared[8:])
        cls.old_abcs = read_abcs(cls.previous)
        cls.new_abcs = read_abcs(cls.body)

    def test_only_turbo_purchase_method_changes_and_one_literal_is_appended(self):
        self.assertEqual(len(self.old_abcs), len(self.new_abcs))
        changes = []
        total = 0
        for abc_index, (before, after) in enumerate(zip(self.old_abcs, self.new_abcs)):
            self.assertEqual(before.methods, after.methods)
            self.assertEqual(before.mn, after.mn)
            self.assertEqual(before.ns, after.ns)
            self.assertEqual(before.nssets, after.nssets)
            self.assertEqual(before.instances, after.instances)
            self.assertEqual(before.classes, after.classes)
            self.assertEqual(list(before.bodies), list(after.bodies))
            self.assertEqual(after.strings[:-1], before.strings)
            self.assertEqual(after.strings[-1], PATCH.TURBO_MESSAGE)
            self.assertEqual(len(before.strings), PATCH.TURBO_STRING_INDEX)
            for method, code in before.bodies.items():
                total += 1
                if code != after.bodies[method]:
                    changes.append((abc_index, method))
                    self.assertEqual(len(code), len(after.bodies[method]))
        self.assertEqual(total, 68_492)
        self.assertEqual(changes, [(0, 14159)])
        # Complete byte composition also pins headers, exception boundaries,
        # assets and all non-method data outside the three declared pool edits.
        self.assertEqual(self.body, PATCH._apply_edits(self.previous, PATCH.TURBO_EDITS))
        self.assertEqual(len(self.body) - len(self.previous), PATCH.TURBO_STRING_BYTES)

    def test_actual_callback_shows_reason_then_returns_false_without_accessing_player(self):
        abc = self.new_abcs[0]
        code = abc.bodies[14159]
        self.assertEqual(hashlib.sha256(code).hexdigest(), PATCH.TURBO_METHOD_PATCHED_SHA256)
        popup = {"TYPE_OK": "ok"}
        instance = object()
        globals_ = {"Display:UI": "ui", "Display:GenericPopup": popup}
        stack = []
        messages = []
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

        # Execute the exact emitted instructions. Only UI and GenericPopup
        # globals exist: accessing balances, equipment or transactions fails.
        for _ in range(40):
            opcode = code[position]; position += 1
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
            elif opcode in (0x26, 0x27):
                stack.append(opcode == 0x26)
            elif opcode == 0x4f:
                self.assertEqual(abc.short(read_u30()), "displayMessage")
                count = read_u30()
                args = [stack.pop() for _ in range(count)][::-1]
                self.assertEqual(stack.pop(), "ui")
                messages.append(args)
            elif opcode == 0x48:
                self.assertIs(stack.pop(), False)
                self.assertEqual(stack, [])
                self.assertEqual(messages, [[PATCH.TURBO_MESSAGE, "ok", None, "", True]])
                return
            else:
                self.fail(f"Unexpected Turbo purchase opcode {opcode:#x} at {position - 1}")
        self.fail("Turbo purchase callback did not return.")

    def test_previous_build_upgrades_and_prepared_build_is_idempotent(self):
        previous = self.original[:4] + struct.pack("<I", len(self.previous) + 8) + zlib.compress(self.previous, 1)
        self.assertEqual(PATCH.patch_client_bytes(previous), self.prepared)
        self.assertEqual(PATCH.patch_client_bytes(self.prepared), self.prepared)
        # Compressed representation is not part of the trusted body identity.
        alternative = self.prepared[:8] + zlib.compress(self.final_body, 1)
        self.assertEqual(PATCH.patch_client_bytes(alternative), alternative)

    def test_unknown_pool_and_callback_bytes_are_rejected(self):
        for offset in (3_411_801, PATCH.TURBO_METHOD_CODE_OFFSET + 8):
            altered = bytearray(self.previous)
            altered[offset] ^= 1
            unknown = self.original[:4] + struct.pack("<I", len(altered) + 8) + zlib.compress(altered, 1)
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, "refusing to modify unknown game code"):
                PATCH.patch_client_bytes(unknown)


if __name__ == "__main__":
    unittest.main()
