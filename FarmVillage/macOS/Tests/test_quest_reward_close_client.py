"""Bind the real quest close shortcut and execute its original local acknowledgment."""
import hashlib
import struct
import unittest
import xml.etree.ElementTree as ET
import zlib

from test_turbo_client_refusal import PATCH, ROOT, ABC, read_abcs


class QuestRewardCloseClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT / "embeds/Flash/v855097-855094/FarmGame.swf"
        cls.original = cls.source.read_bytes()
        cls.previous = zlib.decompress(cls.original[8:])
        for edits in (PATCH.EDITS, PATCH.MARKET_EDITS, PATCH.TAB_EDITS,
                      PATCH.SCRATCH_EDITS, PATCH.EMPTY_WORLD_EDITS, PATCH.COTTAGE_EDITS,
                      PATCH.COTTAGE_UPGRADE_EDITS, PATCH.TURBO_EDITS, PATCH.STORAGE_EDITS,
                      PATCH.INVITATION_EDITS, PATCH.VIP_EDITS, PATCH.MARKET_WALKTHROUGH_EDITS):
            cls.previous = PATCH._apply_edits(cls.previous, edits)
        cls.prepared = PATCH.patch_client_bytes(cls.original)
        cls.body = PATCH._apply_edits(cls.previous, PATCH.QUEST_CLOSE_EDITS)
        cls.final_body = zlib.decompress(cls.prepared[8:])
        cls.before, cls.after = read_abcs(cls.previous), read_abcs(cls.body)
        cls.abc = cls.after[0]
        original_body = zlib.decompress(cls.original[8:])
        bits = original_body[0] >> 3
        position = (5 + 4 * bits + 7) // 8 + 4
        blobs = []
        while position < len(original_body):
            header = struct.unpack_from("<H", original_body, position)[0]
            position += 2
            kind, length = header >> 6, header & 63
            if length == 63:
                length = struct.unpack_from("<I", original_body, position)[0]
                position += 4
            data = original_body[position:position + length]
            if kind == 87 and struct.unpack_from("<H", data)[0] == 668:
                blobs.append(data[6:])
            position += length
            if kind == 0:
                break
        assert len(blobs) == 1
        cls.xml_bytes = blobs[0]
        cls.xml = ET.fromstring(cls.xml_bytes)

    def test_embedded_original_xml_proves_close_pin_is_on_outer_mask_not_content(self):
        self.assertEqual(hashlib.sha256(self.xml_bytes).hexdigest(),
                         "a5f76dab6cf5b65e8c3383560021a1c24a68a17cb228b123b5e3c8e3400f5f86")
        reward = self.xml.find(".//view[@name='questRewardView']")
        masks = [node for node in reward if node.get("controller") == "Mask"]
        self.assertEqual(len(masks), 1)
        self.assertIsNone(masks[0].get("name"))
        self.assertEqual(masks[0].get("viewToPin"), "CloseButtonView")
        content = reward.find(".//view[@name='content']")
        self.assertEqual(content.get("controller"), "Resize")
        self.assertIsNone(content.get("viewToPin"))

    def test_complete_stage_changes_one_method_and_retains_original_header_callback_and_widgets(self):
        self.assertEqual(hashlib.sha256(self.previous).hexdigest(), PATCH.MARKET_WALKTHROUGH_BODY_SHA256)
        self.assertEqual(hashlib.sha256(self.body).hexdigest(), PATCH.QUEST_CLOSE_BODY_SHA256)
        self.assertEqual(self.body, PATCH._apply_edits(self.previous, PATCH.QUEST_CLOSE_EDITS))
        self.assertEqual(self.final_body, PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(self.body, PATCH.IMAGE_ROW_EDITS), PATCH.INVENTORY_ART_EDITS), PATCH.MARKETSTALL_EXPANSION_EDITS), PATCH.WIDGET_STORAGE_EDITS), PATCH.REGIONAL_UPGRADE_EDITS), PATCH.OPTIONAL_BACKGROUND_EDITS), PATCH.COVE_UPGRADE_EDITS))
        total, changes = 0, []
        for index, (before, after) in enumerate(zip(self.before, self.after)):
            for field in ("ints", "uints", "strings", "mn", "ns", "nssets", "methods", "instances", "classes"):
                self.assertEqual(getattr(before, field), getattr(after, field))
            self.assertEqual([struct.pack("<d", x) for x in before.doubles],
                             [struct.pack("<d", x) for x in after.doubles])
            self.assertEqual(list(before.bodies), list(after.bodies))
            for ident, code in before.bodies.items():
                total += 1
                if code != after.bodies[ident]:
                    changes.append((index, ident))
                    self.assertEqual(len(code), len(after.bodies[ident]))
        self.assertEqual((total, changes), (68492, [(0, 23979)]))
        for _, start, size, old_sha, new_sha in PATCH.QUEST_CLOSE_METHODS:
            self.assertEqual(hashlib.sha256(self.previous[start:start + size]).hexdigest(), old_sha)
            self.assertEqual(hashlib.sha256(self.body[start:start + size]).hexdigest(), new_sha)
            # method23979, maxstack3, locals2, scope9..10, code156 remain exact.
            self.assertEqual(self.body[start - 9:start].hex(), "abbb010302090a9c01")
        before, after = self.before[0].bodies[23979], self.abc.bodies[23979]
        self.assertEqual(before[:95], after[:95])
        self.assertEqual(before[152:], after[152:])
        self.assertEqual(self.before[0].bodies[23988], self.abc.bodies[23988])
        self.assertEqual(self.source.read_bytes(), self.original)

    def execute(self, code, *, position, locals_, globals_, call):
        stack, peak = [], 0
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
            opcode = code[position]; position += 1
            if opcode in (0x02,):
                pass
            elif opcode in (0xf0, 0xf1):
                u30()
            elif opcode == 0xef:
                position += 1; u30(); position += 1; u30()
            elif opcode in (0xd0, 0xd1):
                stack.append(locals_[opcode - 0xd0])
            elif opcode == 0xd5:
                locals_[1] = stack.pop()
            elif opcode == 0x30:
                self.assertIs(stack.pop(), locals_[0])
            elif opcode == 0x2c:
                stack.append(self.abc.strings[u30()])
            elif opcode in (0x5d, 0x60):
                stack.append(globals_[self.abc.mname(u30())])
            elif opcode == 0x66:
                name = self.abc.short(u30()); stack.append(stack.pop()[name])
            elif opcode == 0x80:
                u30()  # Cast preserves the nullable stub object.
            elif opcode == 0x2a:
                stack.append(stack[-1])
            elif opcode == 0x20:
                stack.append(None)
            elif opcode in (0x26, 0x27):
                stack.append(opcode == 0x26)
            elif opcode in (0x12, 0x13):
                delta = int.from_bytes(code[position:position + 3], "little", signed=True); position += 3
                branch = not stack.pop() if opcode == 0x12 else stack.pop() == stack.pop()
                if branch:
                    position += delta
            elif opcode in (0x46, 0x4f, 0x4a):
                method, count = self.abc.short(u30()), u30()
                args = [stack.pop() for _ in range(count)][::-1]
                receiver = stack.pop()
                result = call(method, receiver, args, opcode)
                if opcode in (0x46, 0x4a):
                    stack.append(result)
            elif opcode == 0x47:
                self.assertEqual(stack, [])
                return peak
            else:
                self.fail(f"Unexpected quest close opcode {opcode:#x} at {position - 1}")
            peak = max(peak, len(stack))
        self.fail("Quest close code did not return.")

    def test_real_old_tail_skips_binding_and_new_tail_binds_once_within_maxstack_three(self):
        reward = self.xml.find(".//view[@name='questRewardView']")
        content = reward.find(".//view[@name='content']")
        callback = object()
        for missing in (False, True):
            with self.subTest(missing=missing):
                listeners = []
                close = {"listeners": listeners}
                instance = {"onCloseButtonPress": callback}
                def call(method, receiver, args, opcode):
                    if method == "getShortcutController":
                        self.assertIs(receiver, instance)
                        if args == ["content"]:
                            return {"attributes": dict(content.attrib)}
                        self.assertEqual(args, ["CloseButtonView"])
                        return None if missing else close
                    if method == "getAttribute":
                        return receiver["attributes"].get(args[0])
                    if method == "listen":
                        self.assertIs(receiver, close)
                        self.assertEqual(args, ["buttonPressed", callback])
                        listeners.append(args)
                        return None
                    self.fail("Unexpected setup call: " + method)
                globals_ = {"com.troyer.widget.controller:ResizeController": {"ATTRIBUTE_VIEW_TO_PIN": "viewToPin"},
                            "com.troyer.widget.event:WidgetControllerEvent": {"BUTTON_PRESSED": "buttonPressed"}}
                self.execute(self.before[0].bodies[23979], position=95, locals_={0: instance}, globals_=globals_, call=call)
                self.assertEqual(listeners, [])
                peak = self.execute(self.abc.bodies[23979], position=95, locals_={0: instance}, globals_=globals_, call=call)
                self.assertLessEqual(peak, 3)
                self.assertEqual(len(listeners), 0 if missing else 1)

    def test_original_bound_callback_schedules_nonsharing_local_ack_before_generic_close(self):
        instance = object()
        manager, constructor = object(), object()
        transactions = []
        globals_ = {"Engine.Managers:TransactionManager": manager,
                    "Transactions.Quests:TShareQuestLoot": constructor,
                    "Display.Quests:QuestDialog:m_questObject": {"name": "feather-01-005"}}
        def call(method, receiver, args, opcode):
            if method == "TShareQuestLoot":
                self.assertIs(receiver, constructor)
                self.assertEqual(args, ["feather-01-005", False, instance])
                return {"name": args[0], "share": args[1], "dialog": args[2]}
            self.assertEqual(method, "addTransaction")
            self.assertIs(receiver, manager)
            self.assertIs(args[1], True)
            transactions.append(args[0])
        self.execute(self.abc.bodies[23988], position=0, locals_={0: instance}, globals_=globals_, call=call)
        self.assertEqual(len(transactions), 1)
        self.assertFalse(transactions[0]["share"])
        close = ABC.disasm(self.abc, self.abc.bodies[32819])
        base = ABC.disasm(self.abc, self.abc.bodies[24062])
        super_index = next(i for i, line in enumerate(close) if "callsupervoid" in line)
        close_event = next(i for i, line in enumerate(close) if "getproperty CLOSE" in line)
        self.assertLess(super_index, close_event)
        self.assertTrue(any("getproperty BUTTON_PRESSED" in line for line in base))

    def test_market_stage_upgrades_idempotently_and_unknown_setup_is_rejected(self):
        previous = self.original[:4] + struct.pack("<I", len(self.previous) + 8) + zlib.compress(self.previous, 1)
        self.assertEqual(PATCH.patch_client_bytes(previous), self.prepared)
        self.assertEqual(PATCH.patch_client_bytes(self.prepared), self.prepared)
        changed = bytearray(self.previous); changed[PATCH.QUEST_CLOSE_METHODS[0][1] + 95] ^= 1
        with self.assertRaisesRegex(ValueError, "refusing to modify unknown game code"):
            PATCH.patch_client_bytes(previous[:8] + zlib.compress(changed, 1))


if __name__ == "__main__":
    unittest.main()
