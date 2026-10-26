"""Isolated regression checks for the reviewed client compatibility patch."""

import hashlib
import importlib.util
from pathlib import Path
import stat
import struct
import tempfile
import unittest
import zlib


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "farmvillage_client_patch", ROOT / "client_compatibility.py"
)
PATCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PATCH)


class ClientStylePatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = (ROOT / "embeds/Flash/v855097-855094/FarmGame.swf").read_bytes()
        cls.patched = PATCH.patch_client_bytes(cls.original)

    def test_output_matches_independently_assembled_client_body(self):
        body = zlib.decompress(self.patched[8:])
        self.assertEqual(
            hashlib.sha256(body).hexdigest(),
            "51c484d32ac455abd3669fe1e96bd2cf17303fcfd18a4d265cb9b2eb661ed8f9",
        )
        self.assertEqual(struct.unpack_from("<I", self.patched, 4)[0], len(body) + 8)
        self.assertEqual(self.patched[:4], self.original[:4])
        self.assertEqual(len(body), len(zlib.decompress(self.original[8:])) + 599)

    def test_already_patched_client_is_idempotent_across_compression_levels(self):
        alternative = self.patched[:8] + zlib.compress(zlib.decompress(self.patched[8:]), 1)
        self.assertEqual(PATCH.patch_client_bytes(self.patched), self.patched)
        self.assertEqual(PATCH.patch_client_bytes(alternative), alternative)

    def test_known_legacy_style_build_upgrades_to_complete_compatibility_patch(self):
        body = PATCH._apply_edits(zlib.decompress(self.original[8:]), PATCH.EDITS)
        legacy = self.original[:4] + struct.pack("<I", len(body) + 8) + zlib.compress(body, 1)
        self.assertEqual(PATCH.patch_client_bytes(legacy), self.patched)

    def test_known_market_build_changes_only_the_tab_callback_span(self):
        styled = PATCH._apply_edits(zlib.decompress(self.original[8:]), PATCH.EDITS)
        market = PATCH._apply_edits(styled, PATCH.MARKET_EDITS)
        self.assertEqual(hashlib.sha256(market).hexdigest(), PATCH.MARKET_BODY_SHA256)
        legacy = self.original[:4] + struct.pack("<I", len(market) + 8) + zlib.compress(market, 1)
        upgraded = PATCH.patch_client_bytes(legacy)
        self.assertEqual(upgraded, self.patched)
        body = zlib.decompress(upgraded[8:])
        tabbed = PATCH._apply_edits(market, PATCH.TAB_EDITS)
        start = PATCH.TAB_METHOD_CODE_OFFSET + 90
        end = PATCH.TAB_METHOD_CODE_OFFSET + 107
        self.assertEqual(tabbed[:start], market[:start])
        self.assertEqual(tabbed[end:], market[end:])
        self.assertEqual(body, PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(
            PATCH._apply_edits(PATCH._apply_edits(tabbed, PATCH.SCRATCH_EDITS), PATCH.EMPTY_WORLD_EDITS), PATCH.COTTAGE_EDITS), PATCH.COTTAGE_UPGRADE_EDITS), PATCH.TURBO_EDITS), PATCH.STORAGE_EDITS), PATCH.INVITATION_EDITS), PATCH.VIP_EDITS), PATCH.MARKET_WALKTHROUGH_EDITS), PATCH.QUEST_CLOSE_EDITS), PATCH.IMAGE_ROW_EDITS), PATCH.INVENTORY_ART_EDITS), PATCH.MARKETSTALL_EXPANSION_EDITS), PATCH.WIDGET_STORAGE_EDITS), PATCH.REGIONAL_UPGRADE_EDITS), PATCH.OPTIONAL_BACKGROUND_EDITS), PATCH.COVE_UPGRADE_EDITS))
        pool_shift = PATCH.TURBO_STRING_BYTES + PATCH.STORAGE_STRING_BYTES + PATCH.REGIONAL_UPGRADE_STRING_BYTES + PATCH.COVE_UPGRADE_STRING_BYTES
        self.assertEqual(len(body), len(market) + pool_shift)
        # currentTarget is followed by the original DisplayObject cast and
        # isDescendant call; every branch instruction stays at its old offset.
        self.assertEqual(body[start + pool_shift:end + pool_shift].hex(), "020260fb11d366d627601987d166aad205")
        method_start = PATCH.TAB_METHOD_CODE_OFFSET + pool_shift
        method = body[method_start:method_start + PATCH.TAB_METHOD_CODE_BYTES]
        self.assertEqual(hashlib.sha256(method).hexdigest(), PATCH.TAB_METHOD_PATCHED_SHA256)

    def test_previous_tab_build_changes_only_the_scratch_coin_block(self):
        original = zlib.decompress(self.original[8:])
        tabbed = PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(
            original, PATCH.EDITS), PATCH.MARKET_EDITS), PATCH.TAB_EDITS)
        self.assertEqual(hashlib.sha256(tabbed).hexdigest(), PATCH.TAB_BODY_SHA256)
        legacy = self.original[:4] + struct.pack("<I", len(tabbed) + 8) + zlib.compress(tabbed, 1)
        body = PATCH._apply_edits(tabbed, PATCH.SCRATCH_EDITS)
        self.assertEqual(zlib.decompress(PATCH.patch_client_bytes(legacy)[8:]),
                         PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(body, PATCH.EMPTY_WORLD_EDITS), PATCH.COTTAGE_EDITS), PATCH.COTTAGE_UPGRADE_EDITS), PATCH.TURBO_EDITS), PATCH.STORAGE_EDITS), PATCH.INVITATION_EDITS), PATCH.VIP_EDITS), PATCH.MARKET_WALKTHROUGH_EDITS), PATCH.QUEST_CLOSE_EDITS), PATCH.IMAGE_ROW_EDITS), PATCH.INVENTORY_ART_EDITS), PATCH.MARKETSTALL_EXPANSION_EDITS), PATCH.WIDGET_STORAGE_EDITS), PATCH.REGIONAL_UPGRADE_EDITS), PATCH.OPTIONAL_BACKGROUND_EDITS), PATCH.COVE_UPGRADE_EDITS))
        start = PATCH.SCRATCH_METHOD_CODE_OFFSET + 233
        end = PATCH.SCRATCH_METHOD_CODE_OFFSET + 332
        self.assertEqual(body[:start], tabbed[:start])
        self.assertEqual(body[end:], tabbed[end:])
        self.assertEqual(len(body), len(tabbed))

    def test_previous_scratch_build_changes_only_the_empty_world_comparison(self):
        original = zlib.decompress(self.original[8:])
        previous = PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(
            PATCH._apply_edits(original, PATCH.EDITS), PATCH.MARKET_EDITS),
            PATCH.TAB_EDITS), PATCH.SCRATCH_EDITS)
        self.assertEqual(hashlib.sha256(previous).hexdigest(), PATCH.SCRATCH_BODY_SHA256)
        legacy = self.original[:4] + struct.pack("<I", len(previous) + 8) + zlib.compress(previous, 1)
        body = PATCH._apply_edits(previous, PATCH.EMPTY_WORLD_EDITS)
        self.assertEqual(zlib.decompress(PATCH.patch_client_bytes(legacy)[8:]),
                         PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(body, PATCH.COTTAGE_EDITS), PATCH.COTTAGE_UPGRADE_EDITS), PATCH.TURBO_EDITS), PATCH.STORAGE_EDITS), PATCH.INVITATION_EDITS), PATCH.VIP_EDITS), PATCH.MARKET_WALKTHROUGH_EDITS), PATCH.QUEST_CLOSE_EDITS), PATCH.IMAGE_ROW_EDITS), PATCH.INVENTORY_ART_EDITS), PATCH.MARKETSTALL_EXPANSION_EDITS), PATCH.WIDGET_STORAGE_EDITS), PATCH.REGIONAL_UPGRADE_EDITS), PATCH.OPTIONAL_BACKGROUND_EDITS), PATCH.COVE_UPGRADE_EDITS))
        changed = [index for index, (before, after) in enumerate(zip(previous, body))
                   if before != after]
        self.assertEqual(changed, [PATCH.EMPTY_WORLD_METHOD_CODE_OFFSET + 340])
        self.assertEqual((previous[changed[0]], body[changed[0]]), (0xaf, 0xb0))
        method = slice(PATCH.EMPTY_WORLD_METHOD_CODE_OFFSET,
                       PATCH.EMPTY_WORLD_METHOD_CODE_OFFSET + PATCH.EMPTY_WORLD_METHOD_CODE_BYTES)
        self.assertEqual(hashlib.sha256(previous[method]).hexdigest(),
                         PATCH.EMPTY_WORLD_METHOD_SOURCE_SHA256)
        self.assertEqual(hashlib.sha256(body[method]).hexdigest(),
                         PATCH.EMPTY_WORLD_METHOD_PATCHED_SHA256)
        self.assertEqual(len(previous), len(body))

    def test_initial_world_gate_loads_empty_and_populated_arrays_and_retains_presence_checks(self):
        body = zlib.decompress(self.patched[8:])
        start = PATCH.EMPTY_WORLD_METHOD_CODE_OFFSET + PATCH.TURBO_STRING_BYTES + PATCH.STORAGE_STRING_BYTES + PATCH.REGIONAL_UPGRADE_STRING_BYTES + PATCH.COVE_UPGRADE_STRING_BYTES
        code = body[start:start + PATCH.EMPTY_WORLD_METHOD_CODE_BYTES]

        # Execute the actual onUserInit world/array gate up to loadObject. AS3
        # treats even an empty Array/Object as true. Keep the surrounding
        # original branch operands, so this checks the retained null guards too.
        def execute(result, should_load=True):
            marker = object()
            global_ = {10952: marker}
            locals_ = {1: result, 2: should_load}
            stack = []; loaded = []; position = 271
            def truth(value):
                return True if isinstance(value, (dict, list)) else bool(value)
            def read_u30():
                nonlocal position
                value = shift = 0
                while True:
                    byte = code[position]; position += 1
                    value |= (byte & 127) << shift
                    if byte < 128:
                        return value
                    shift += 7
            for _ in range(70):
                if position >= 367:
                    return loaded
                opcode = code[position]; position += 1
                if opcode == 0xf0:
                    read_u30()
                elif opcode == 0xef:
                    position += 1; read_u30(); position += 1; read_u30()
                elif opcode == 0x62:
                    stack.append(locals_[read_u30()])
                elif opcode == 0x63:
                    locals_[read_u30()] = stack.pop()
                elif opcode == 0x80:
                    self.assertEqual(read_u30(), 1)
                elif opcode in (0xd1, 0xd2):
                    stack.append(locals_[opcode - 0xd0])
                elif opcode == 0x60:
                    self.assertEqual(read_u30(), 2078); stack.append(global_)
                elif opcode == 0x66:
                    field = read_u30(); value = stack.pop()
                    if field == 93312:
                        stack.append(len(value))
                    elif field == 10952:
                        stack.append(value[field])
                    else:
                        stack.append(value.get({93310: "world", 93311: "objectsArray"}[field]))
                elif opcode == 0x76:
                    stack.append(truth(stack.pop()))
                elif opcode == 0x2a:
                    stack.append(stack[-1])
                elif opcode == 0x29:
                    stack.pop()
                elif opcode == 0x24:
                    stack.append(code[position]); position += 1
                elif opcode == 0xb0:
                    right = stack.pop(); stack.append(stack.pop() >= right)
                elif opcode == 0x12:
                    delta = int.from_bytes(code[position:position + 3], "little", signed=True)
                    position += 3
                    if not truth(stack.pop()):
                        position += delta
                elif opcode == 0x4f:
                    self.assertEqual((read_u30(), read_u30()), (2747, 1))
                    loaded.append(stack.pop()); self.assertIs(stack.pop(), marker)
                else:
                    self.fail(f"Unexpected initial-world gate opcode {opcode:#x} at {position - 1}")
            self.fail("Initial-world gate did not finish.")

        for objects in ([], [{"className": "Plot", "id": 1}]):
            snapshot = {"objectsArray": objects}
            self.assertEqual(execute({"world": snapshot}), [snapshot])
        for result in ({}, {"world": None}, {"world": {}}, {"world": {"objectsArray": None}}):
            self.assertEqual(execute(result), [])
        self.assertEqual(execute({"world": {"objectsArray": []}}, should_load=False), [])

    def test_scratch_coin_bytecode_loads_truthful_icons_and_quantity_labels(self):
        body = zlib.decompress(self.patched[8:])
        start = PATCH.SCRATCH_METHOD_CODE_OFFSET + PATCH.TURBO_STRING_BYTES + PATCH.STORAGE_STRING_BYTES + PATCH.REGIONAL_UPGRADE_STRING_BYTES + PATCH.COVE_UPGRADE_STRING_BYTES
        code = body[start:start + PATCH.SCRATCH_METHOD_CODE_BYTES]
        self.assertEqual(hashlib.sha256(code).hexdigest(), PATCH.SCRATCH_METHOD_PATCHED_SHA256)
        # Execute the emitted coin branch's AVM2 stack operations, including
        # its real branch operands and existing pool references. The original
        # scratch tile and win/lose panel use its return value for their labels.
        def execute(value):
            reward = {"type": "coins", "value": str(value)}
            locals_ = {1: "icon", 2: reward}
            constants = {83817: 1000000, 83819: 2000000,
                         83816: "one-million", 83818: "two-million"}
            strings = {669: "value", 115208: "assets/hud/FV_coins_100x100.png"}
            stack = []; loaded = []; position = 233
            def read_u30():
                nonlocal position
                result = shift = 0
                while True:
                    byte = code[position]; position += 1
                    result |= (byte & 127) << shift
                    if byte < 128:
                        return result
                    shift += 7
            for _ in range(80):
                opcode = code[position]; position += 1
                if opcode in (2, 9):
                    continue
                if opcode in (0x10, 0x13):
                    delta = int.from_bytes(code[position:position + 3], "little", signed=True); position += 3
                    if opcode == 0x10 or stack.pop() == stack.pop():
                        position += delta
                elif opcode == 0x24:
                    stack.append(code[position]); position += 1
                elif opcode == 0x2c:
                    stack.append(strings[read_u30()])
                elif opcode == 0x5d:
                    self.assertEqual(read_u30(), 92442); stack.append("global")
                elif opcode == 0x60:
                    stack.append(constants[read_u30()])
                elif opcode == 0x62:
                    stack.append(locals_[read_u30()])
                elif opcode == 0x63:
                    locals_[read_u30()] = stack.pop()
                elif opcode == 0x66:
                    self.assertEqual(read_u30(), 104378)
                    key = stack.pop(); stack.append(stack.pop()[key])
                elif opcode in (0x46, 0x4f):
                    method = read_u30(); self.assertEqual(read_u30(), 1)
                    argument = stack.pop(); receiver = stack.pop()
                    if opcode == 0x46:
                        self.assertEqual((method, receiver), (92442, "global")); stack.append(int(argument))
                    else:
                        self.assertEqual((method, receiver), (45158, "icon")); loaded.append(argument)
                elif opcode == 0x73:
                    stack.append(int(stack.pop()))
                elif opcode in (0xd1, 0xd2):
                    stack.append(locals_[opcode - 0xd0])
                elif opcode == 0xf0:
                    read_u30()
                elif opcode == 0x48:
                    self.assertEqual(reward, {"type": "coins", "value": str(value)})
                    return loaded, stack.pop()
                else:
                    self.fail(f"Unexpected coin-branch opcode {opcode:#x} at {position - 1}")
            self.fail("Coin icon bytecode did not return.")
        for value in (500, 2000):
            self.assertEqual(execute(value), (["assets/hud/FV_coins_100x100.png"], value))
        self.assertEqual(execute(1000000), (["one-million"], 1))
        self.assertEqual(execute(2000000), (["two-million"], 1))

    def test_unknown_client_cannot_replace_existing_output(self):
        body = bytearray(zlib.decompress(self.original[8:]))
        body[PATCH.METHOD_CODE_OFFSET + 20] ^= 1
        unknown = self.original[:8] + zlib.compress(body)
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "unknown.swf"
            output = Path(temporary) / "output.swf"
            source.write_bytes(unknown)
            output.write_bytes(b"preserve existing output")
            with self.assertRaisesRegex(ValueError, "refusing to modify unknown game code"):
                PATCH.patch_client_file(source, output)
            self.assertEqual(output.read_bytes(), b"preserve existing output")
            self.assertEqual(source.read_bytes(), unknown)

    def test_truncated_and_trailing_payloads_are_rejected(self):
        for malformed in (self.original[:-8], self.original + b"unexpected trailing data"):
            with self.subTest(length=len(malformed)), self.assertRaises(ValueError):
                PATCH.patch_client_bytes(malformed)

    def test_copy_is_atomic_preserves_source_and_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.swf"
            output = Path(temporary) / "output.swf"
            source.write_bytes(self.original)
            source.chmod(0o640)
            output.write_bytes(b"old staging copy")
            self.assertTrue(PATCH.patch_client_file(source, output))
            self.assertEqual(source.read_bytes(), self.original)
            self.assertEqual(output.read_bytes(), self.patched)
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o640)
            self.assertEqual({path.name for path in Path(temporary).iterdir()}, {"source.swf", "output.swf"})

    def test_in_place_staging_and_repeat_preparation(self):
        with tempfile.TemporaryDirectory() as temporary:
            staged = Path(temporary) / "staged.swf"
            staged.write_bytes(self.original)
            self.assertTrue(PATCH.patch_client_file(staged, staged))
            self.assertEqual(staged.read_bytes(), self.patched)
            self.assertFalse(PATCH.patch_client_file(staged, staged))
            self.assertEqual(staged.read_bytes(), self.patched)


if __name__ == "__main__":
    unittest.main()
