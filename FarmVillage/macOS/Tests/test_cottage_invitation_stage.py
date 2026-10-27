"""Execute the final cottage controls and invitation gates in their emitted code."""

import csv
import hashlib
import struct
import unittest
import zlib

from test_turbo_client_refusal import PATCH, ROOT, ABC, read_abcs
import test_cottage_client_upgrades as cottage_upgrade_tests
import test_persistence  # Establish disposable paths before availability imports bundle.
import feature_availability


class CottageInvitationStageTests(unittest.TestCase):
    execute_frame = cottage_upgrade_tests.CottageClientUpgradeTests.execute_frame

    @classmethod
    def setUpClass(cls):
        cls.original = (ROOT / "embeds/Flash/v855097-855094/FarmGame.swf").read_bytes()
        cls.previous = zlib.decompress(cls.original[8:])
        for edits in (PATCH.EDITS, PATCH.MARKET_EDITS, PATCH.TAB_EDITS,
                      PATCH.SCRATCH_EDITS, PATCH.EMPTY_WORLD_EDITS, PATCH.COTTAGE_EDITS,
                      PATCH.COTTAGE_UPGRADE_EDITS, PATCH.TURBO_EDITS, PATCH.STORAGE_EDITS):
            cls.previous = PATCH._apply_edits(cls.previous, edits)
        cls.prepared = PATCH.patch_client_bytes(cls.original)
        cls.body = PATCH._apply_edits(PATCH._apply_edits(cls.previous, PATCH.INVITATION_EDITS), PATCH.VIP_EDITS)
        cls.final_body = zlib.decompress(cls.prepared[8:])
        cls.before = read_abcs(cls.previous)
        cls.after = read_abcs(cls.body)
        cls.abc = cls.after[0]
        cls.maxstack = {}
        for ident, offset, length, _, _ in PATCH.INVITATION_METHODS:
            headers = []
            for start in range(offset - 16, offset):
                reader = ABC.R(cls.previous, start)
                method, maxstack, locals_, initial_scope, max_scope, size = [reader.u30() for _ in range(6)]
                if reader.p == offset and method == ident and size == length:
                    headers.append(maxstack)
            assert len(headers) == 1, (ident, headers)
            cls.maxstack[ident] = headers[0]

    def test_all_68492_methods_pools_headers_and_noncode_bytes_have_exact_bounded_delta(self):
        self.assertEqual(hashlib.sha256(self.previous).hexdigest(), PATCH.STORAGE_BODY_SHA256)
        self.assertEqual(hashlib.sha256(self.body).hexdigest(), PATCH.VIP_BODY_SHA256)
        self.assertEqual(self.body, PATCH._apply_edits(PATCH._apply_edits(self.previous, PATCH.INVITATION_EDITS), PATCH.VIP_EDITS))
        self.assertEqual(self.final_body, PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(self.body, PATCH.MARKET_WALKTHROUGH_EDITS), PATCH.QUEST_CLOSE_EDITS), PATCH.IMAGE_ROW_EDITS), PATCH.INVENTORY_ART_EDITS), PATCH.MARKETSTALL_EXPANSION_EDITS), PATCH.WIDGET_STORAGE_EDITS), PATCH.REGIONAL_UPGRADE_EDITS), PATCH.OPTIONAL_BACKGROUND_EDITS), PATCH.COVE_UPGRADE_EDITS))
        self.assertEqual(len(self.body), len(self.previous))
        changed, total = [], 0
        for abc_index, (before, after) in enumerate(zip(self.before, self.after)):
            for field in ("ints", "uints", "strings", "mn", "ns", "nssets",
                          "methods", "instances", "classes"):
                self.assertEqual(getattr(before, field), getattr(after, field), field)
            self.assertEqual([struct.pack("<d", value) for value in before.doubles],
                             [struct.pack("<d", value) for value in after.doubles])
            self.assertEqual(list(before.bodies), list(after.bodies))
            for ident, code in before.bodies.items():
                total += 1
                if code != after.bodies[ident]:
                    changed.append((abc_index, ident))
                    self.assertEqual(len(code), len(after.bodies[ident]))
        self.assertEqual(total, 68_492)
        self.assertEqual(changed, [(0, row[0]) for row in PATCH.INVITATION_METHODS])
        for ident, offset, length, before_sha, after_sha in PATCH.INVITATION_METHODS:
            if ident == PATCH.VIP_METHOD_ID:
                after_sha = PATCH.VIP_METHOD_PATCHED_SHA256
            self.assertEqual(hashlib.sha256(self.previous[offset:offset + length]).hexdigest(), before_sha)
            self.assertEqual(hashlib.sha256(self.body[offset:offset + length]).hexdigest(), after_sha)
        # Every edit fits entirely inside one declared method. Equality outside
        # these spans also covers maxstack/local-count headers and exception data.
        for offset, old, new in (*PATCH.INVITATION_EDITS, *PATCH.VIP_EDITS):
            self.assertEqual(len(old), len(new))
            self.assertEqual(sum(start <= offset and offset + len(old) <= start + size
                                 for _, start, size, _, _ in PATCH.INVITATION_METHODS), 1)
        self.assertEqual((ROOT / "embeds/Flash/v855097-855094/FarmGame.swf").read_bytes(), self.original)

    def execute(self, ident, start, stop, locals_, globals_=None):
        """Minimal strict interpreter of actual emitted spans, with no globals."""
        code, abc = self.abc.bodies[ident], self.abc
        stack, position, peak = [], start, 0

        def u30():
            nonlocal position
            value = shift = 0
            while True:
                byte = code[position]; position += 1
                value |= (byte & 127) << shift
                if byte < 128:
                    return value
                shift += 7

        for _ in range(100):
            if position == stop:
                self.assertEqual(stack, [])
                return locals_
            opcode = code[position]; position += 1
            if opcode in (0x02, 0x09):
                pass
            elif opcode in (0xf0, 0xf1):
                u30()
            elif opcode in (0xd0, 0xd1, 0xd2, 0xd3):
                stack.append(locals_[opcode - 0xd0])
            elif opcode == 0x62:
                stack.append(locals_[u30()])
            elif opcode == 0x63:
                locals_[u30()] = stack.pop()
            elif opcode == 0x30:
                self.assertIs(stack.pop(), locals_[0])
            elif opcode == 0x2c:
                index = u30()
                self.assertGreater(index, 0)
                stack.append(abc.strings[index])
            elif opcode == 0x24:
                stack.append(int.from_bytes(code[position:position + 1], "little", signed=True)); position += 1
            elif opcode in (0x26, 0x27):
                stack.append(opcode == 0x26)
            elif opcode == 0x56:
                count = u30()
                values = [stack.pop() for _ in range(count)][::-1]
                stack.append(values)
            elif opcode == 0x60:
                stack.append(globals_[abc.mname(u30())])
            elif opcode == 0x87:
                stack.pop()  # Original MovieClip astypelate; object remains.
            elif opcode == 0x66:
                name = abc.short(u30())
                stack.append(stack.pop()[name])
            elif opcode in (0x61, 0x68):
                name = abc.short(u30())
                value = stack.pop(); stack.pop()[name] = value
            elif opcode == 0x46:
                method, count = abc.mname(u30()), u30()
                args = [stack.pop() for _ in range(count)][::-1]
                receiver = stack.pop()
                if method == "http://adobe.com/AS3/2006/builtin:substr":
                    self.assertIsInstance(receiver, str)
                    self.assertEqual(args, [11])
                    result = receiver[args[0]:]
                elif method == "http://adobe.com/AS3/2006/builtin:indexOf":
                    self.assertEqual(receiver, ["bakery", "winery", "perfumery", "pub"])
                    result = receiver.index(args[0]) if args[0] in receiver else -1
                elif method == "getMarketSize":
                    self.assertEqual(args, [])
                    result = receiver["marketSize"]
                elif method == "http://adobe.com/AS3/2006/builtin:hasOwnProperty":
                    self.assertEqual(len(args), 1)
                    result = args[0] in receiver
                else:
                    self.fail(f"Unexpected method {method}")
                stack.append(result)
            elif opcode == 0xab:
                stack.append(stack.pop() == stack.pop())
            elif opcode == 0xb0:
                right = stack.pop(); stack.append(stack.pop() >= right)
            elif opcode == 0x76:
                stack.append(bool(stack.pop()))
            elif opcode == 0x2a:
                stack.append(stack[-1])
            elif opcode == 0x29:
                stack.pop()
            elif opcode in (0x10, 0x12):
                delta = int.from_bytes(code[position:position + 3], "little", signed=True); position += 3
                if opcode == 0x10 or not stack.pop():
                    position += delta
            elif opcode == 0x47:
                self.assertEqual(stack, [])
                return None
            elif opcode == 0x48:
                result = stack.pop()
                self.assertEqual(stack, [])
                return result
            else:
                self.fail(f"Unexpected opcode {opcode:#x} at {position - 1}")
            peak = max(peak, len(stack))
            self.assertLessEqual(peak, self.maxstack[ident])
        self.fail("Emitted invitation span did not finish.")

    def test_actual_supported_type_predicate_and_cash_coin_cap_paths(self):
        code = self.abc.bodies[34693]
        for craft in ("bakery", "winery", "perfumery", "pub", "japan", "hawaii", "", None):
            with self.subTest(craft=craft):
                instance = {"cottage": {"craftType": craft}}
                locals_ = self.execute(34693, 389, 437, {0: instance, 6: 5})
                supported = craft in ("bakery", "winery", "perfumery", "pub")
                self.assertIs(locals_[6], supported)
                self.assertEqual(instance, {"cottage": {"craftType": craft}})
                for remaining, maximum, prereq in ((6, False, False), (0, False, False),
                                                    (-2, False, False), (0, True, False),
                                                    (6, False, True), (0, False, True)):
                    new, new_instance = self.execute_frame(code, remaining, max_level=maximum, prereq=prereq, supported=supported)
                    old, old_instance = self.execute_frame(self.before[0].bodies[34693], remaining, max_level=maximum, prereq=prereq)
                    self.assertEqual(new["coin"]["visible"], supported and not maximum and remaining <= 0)
                    self.assertEqual(new["cash"]["visible"], supported and not maximum and remaining > 0)
                    self.assertEqual(new["meter"], old["meter"])
                    for button in ("coin", "cash"):
                        self.assertEqual(new[button].get("enabled"), old[button].get("enabled"))
                    self.assertNotEqual(new["message"]["text"], "")
                    self.assertNotEqual(new_instance["tooltip"]["text"], "")

    def test_automatic_reminders_return_before_accessing_action_counts_or_seen_flags(self):
        # No globals/player/transactions are available to this interpreter.
        instance = {"sentinel": "unchanged"}
        self.assertIs(self.execute(38972, 0, None, {0: instance}), False)
        self.assertIsNone(self.execute(5911, 0, None, {0: instance}))
        self.assertEqual(instance, {"sentinel": "unchanged"})
        # Manual cottage reminder/choice methods retain all original code.
        self.assertEqual(self.before[0].bodies[5912], self.abc.bodies[5912])

    def test_inventory_opens_inventory_and_hides_shipping_and_expand_overlays(self):
        for section in ("inventory", "upgrade", "shippingLicenses", None):
            instance = {}
            self.execute(12402, 96, 103, {0: instance, 2: section})
            self.assertEqual(instance, {"m_currentSection": "inventory"})
        for start, stop in ((401, 410), (491, 500)):
            overlay = {"visible": True, "sentinel": "unchanged"}
            self.execute(12403, start, stop, {2: {"m_overlay": overlay}})
            self.assertEqual(overlay, {"visible": False, "sentinel": "unchanged"})
        # Both original conditionals skip the expansion menu builder.
        self.execute(11987, 212, 277, {1: True})

    def test_vip_layers_only_change_visible_true_to_false(self):
        for ident, index in ((12394, 58),):
            before, after = self.before[0].bodies[ident], self.abc.bodies[ident]
            self.assertEqual(before[:index], after[:index])
            self.assertEqual(before[index + 1:], after[index + 1:])
            self.assertEqual((before[index], after[index]), (0x26, 0x27))

    def test_full_vip_gate_hides_default_art_when_sales_are_disabled_without_seen_state(self):
        # The browser exposed this case: disabled VIP sales skip the original
        # outer branch, leaving default-visible artwork on screen. No sales
        # manager, experiment manager or player seen flags exist in this VM.
        for artwork in ({"visible": True}, None):
            instance = {}
            globals_ = {"Widgets.Core.Windows:ZwAbstractWindow:m_window": {"VIPFTUE_mc": artwork},
                        "flash.display:MovieClip": object()}
            self.assertIsNone(self.execute(11244, 0, None, {0: instance}, globals_))
            if artwork is not None:
                self.assertEqual(artwork, {"visible": False})
                self.assertIs(instance["m_ftueVip"], artwork)
            else:
                self.assertEqual(instance, {})

    def test_inventory_declarations_match_reviewed_stage_and_original_hud_gate_is_separate(self):
        with (ROOT / "macOS/Documentation/FEATURE_INVITATION_INVENTORY.csv").open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        gates = {row["name"] for row in rows if row["category"] == "client_presentation_gate"}
        self.assertEqual(gates, set(feature_availability.CLIENT_PRESENTATION_GATES))
        self.assertFalse(gates & set(feature_availability.blocked_hud_icons()))
        self.assertEqual({ident for values in feature_availability.CLIENT_PRESENTATION_GATES.values() for ident in values},
                         {row[0] for row in (*PATCH.INVITATION_METHODS, *PATCH.MARKET_WALKTHROUGH_METHODS, *PATCH.MARKETSTALL_EXPANSION_METHODS, *PATCH.WIDGET_STORAGE_METHODS)} - {34693})

    def test_storage_stage_upgrades_idempotently_and_unknown_code_fails_closed(self):
        previous = self.original[:4] + struct.pack("<I", len(self.previous) + 8) + zlib.compress(self.previous, 1)
        self.assertEqual(PATCH.patch_client_bytes(previous), self.prepared)
        self.assertEqual(PATCH.patch_client_bytes(self.prepared), self.prepared)
        invitation = PATCH._apply_edits(self.previous, PATCH.INVITATION_EDITS)
        legacy = previous[:8] + zlib.compress(invitation, 1)
        self.assertEqual(hashlib.sha256(invitation).hexdigest(), PATCH.INVITATION_BODY_SHA256)
        self.assertEqual(PATCH.patch_client_bytes(legacy), self.prepared)
        for _, offset, _, _, _ in PATCH.INVITATION_METHODS:
            altered = bytearray(self.previous); altered[offset] ^= 1
            unknown = previous[:8] + zlib.compress(altered, 1)
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, "refusing to modify unknown game code"):
                PATCH.patch_client_bytes(unknown)


if __name__ == "__main__":
    unittest.main()
