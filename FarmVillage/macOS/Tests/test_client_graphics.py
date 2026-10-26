"""Cached-image completion, tab input semantics and exact client composition."""
import hashlib
import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import client_graphics as graphics
import meadows_client
from test_turbo_client_refusal import PATCH, ABC, read_abcs
import test_image_row_client as image_tests


class ClientGraphicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (ROOT / 'embeds/Flash/v855097-855094/FarmGame.swf').read_bytes()
        cls.previous = meadows_client.patch_client_bytes(PATCH.patch_client_bytes(cls.raw))
        cls.image_client = graphics.patch_image_bytes(cls.previous)
        cls.image_body = zlib.decompress(cls.image_client[8:])
        cls.widget_client = graphics.patch_widget_bytes(cls.previous)
        cls.widget_body = zlib.decompress(cls.widget_client[8:])
        cls.port_client = graphics.patch_port_bytes(cls.previous)
        cls.port_body = zlib.decompress(cls.port_client[8:])
        cls.final = graphics.patch_client_bytes(cls.previous)
        cls.before_body = zlib.decompress(cls.previous[8:])
        cls.body = zlib.decompress(cls.final[8:])
        cls.before = read_abcs(cls.before_body)
        cls.after = read_abcs(cls.body)
        cls.old_code = cls.before[0].bodies[23400]
        cls.code = cls.after[0].bodies[23400]

    def test_only_four_reviewed_methods_change_with_all_existing_pools_preserved(self):
        changes, total = [], 0
        for index, (before, after) in enumerate(zip(self.before, self.after)):
            for field in ('ints', 'uints', 'strings', 'mn', 'ns', 'nssets', 'methods', 'instances', 'classes'):
                self.assertEqual(getattr(before, field), getattr(after, field), field)
            self.assertEqual([struct.pack('<d', v) for v in before.doubles],
                             [struct.pack('<d', v) for v in after.doubles])
            self.assertEqual(list(before.bodies), list(after.bodies))
            for ident, code in before.bodies.items():
                total += 1
                if code != after.bodies[ident]: changes.append((index, ident))
        self.assertEqual(total, 68492)
        self.assertEqual(changes, [(0, 4367), (0, 22256), (0, 23400), (0, 30984)])
        self.assertEqual(self.code[:125], self.old_code[:125])
        self.assertEqual(self.code[128:141], self.old_code[128:141])
        self.assertEqual(self.code[141:153], graphics.CACHE_GUARD)
        self.assertEqual(self.code[153:], self.old_code[141:])
        self.assertEqual(hashlib.sha256(self.old_code).hexdigest(), graphics.METHOD_SOURCE_SHA256)
        self.assertEqual(hashlib.sha256(self.code).hexdigest(), graphics.METHOD_PATCHED_SHA256)
        _, invalid, missing = image_tests.ImageRowClientTests.branch_errors(self, self.code)
        self.assertEqual((invalid, missing), ([], []))

    def run_cache_prefix(self, code, loaded, synchronous):
        """Execute the actual lookup/request/guard instructions, with a fake cache."""
        cache, activation, receiver = {'loaded': loaded}, None, object()
        activation = {'cache': cache}
        stack, requests = [], 0
        reader = ABC.R(code, 116)
        loaded_path = 157 if len(code) == 1127 else 145
        null_return = len(code) - 8
        for _ in range(40):
            if reader.p == loaded_path: return 'image', requests
            if reader.p == null_return: return 'null', requests
            op = reader.u8()
            if op == 0x65:
                self.assertEqual(reader.u8(), 1); stack.append(activation)
            elif op == 0x6c:
                self.assertEqual(reader.u30(), 3); self.assertIs(stack.pop(), activation); stack.append(cache)
            elif op == 0x66:
                self.assertEqual(self.after[0].short(reader.u30()), 'loaded'); stack.append(stack.pop()['loaded'])
            elif op == 0x11:
                delta = reader.s24()
                if stack.pop(): reader.p += delta
            elif op == 0xf0: reader.u30()
            elif op == 0xd0: stack.append(receiver)
            elif op == 0x4f:
                self.assertEqual(self.after[0].short(reader.u30()), 'requestImage')
                self.assertEqual(reader.u30(), 1)
                self.assertIs(stack.pop(), cache); self.assertIs(stack.pop(), receiver)
                requests += 1
                if synchronous: cache['loaded'] = True
            elif op == 0x10:
                delta = reader.s24(); reader.p += delta
            else: self.fail('Unexpected instruction ' + hex(op))
        self.fail('Cache prefix did not choose an original branch')

    def test_synchronous_cache_completion_resumes_original_image_construction_once(self):
        self.assertEqual(self.run_cache_prefix(self.old_code, False, True), ('null', 1))
        self.assertEqual(self.run_cache_prefix(self.code, False, True), ('image', 1))

    def test_already_loaded_and_genuinely_async_paths_remain_unchanged(self):
        for code in (self.old_code, self.code):
            self.assertEqual(self.run_cache_prefix(code, True, False), ('image', 0))
            self.assertEqual(self.run_cache_prefix(code, False, False), ('null', 1))

    def test_method_limits_exception_types_traits_and_all_later_bytes_are_preserved(self):
        def metadata(body, length):
            header = ABC.R(body, graphics.METHOD_CODE_OFFSET - 9)
            values = [header.u30() for _ in range(6)]
            self.assertEqual(header.p, graphics.METHOD_CODE_OFFSET)
            self.assertEqual(values, [23400, 3, 5, 6, 11, length])
            r = ABC.R(body, graphics.METHOD_CODE_OFFSET + length)
            exceptions = [[r.u30() for _ in range(5)] for _ in range(r.u30())]
            return exceptions, r.p
        before, old_end = metadata(self.before_body, 1115)
        after, new_end = metadata(self.image_body, 1127)
        self.assertEqual(before, [[552, 571, 578, 76, 10259]])
        self.assertEqual(after, [[564, 583, 590, 76, 10259]])
        self.assertEqual(self.before_body[old_end:], self.image_body[new_end:])
        delta = graphics.WIDGET_BODY_DELTA + graphics.PORT_BODY_DELTA
        self.assertEqual(self.image_body[graphics.METHOD_CODE_OFFSET:],
                         self.port_body[graphics.METHOD_CODE_OFFSET + delta:])

    def test_tab_tail_matches_locked_native_method_and_retains_original_setter(self):
        before, after = self.before[0].bodies[4367], self.after[0].bodies[4367]
        self.assertEqual(hashlib.sha256(before).hexdigest(), graphics.WIDGET_METHOD_SOURCE_SHA256)
        self.assertEqual(hashlib.sha256(after).hexdigest(), graphics.WIDGET_METHOD_PATCHED_SHA256)
        self.assertEqual(before[:-1], after[:123])
        self.assertEqual(after[123:], graphics.WIDGET_TAIL)
        _, invalid, missing = image_tests.ImageRowClientTests.branch_errors(self, after)
        self.assertEqual((invalid, missing), ([], []))
        # This is the enabled/set trait, not a method-number assumption.
        self.assertEqual(self.after[0].short(1095), 'FarmTabButton')
        self.assertEqual(self.after[0].short(5075), 'm_element')
        self.assertEqual(self.after[0].short(25), 'DisplayObjectContainer')
        self.assertEqual(self.after[0].short(74657), 'toggleInputOnlyChildren')
        header = ABC.R(self.body, graphics.WIDGET_CODE_OFFSET - 7)
        self.assertEqual([header.u30() for _ in range(6)], [4367, 3, 2, 6, 7, 158])
        self.assertEqual(header.p, graphics.WIDGET_CODE_OFFSET + 1)
        end = ABC.R(self.body, header.p + 158)
        self.assertEqual((end.u30(), end.u30()), (0, 0))  # Exceptions, activation traits.

    def test_tab_tail_disables_only_visual_children_of_tab_containers(self):
        code = self.after[0].bodies[4367]
        for tab, container in ((False, False), (False, True), (True, False), (True, True)):
            with self.subTest(tab=tab, container=container):
                element = {'container': container}
                widget = {'tab': tab, 'element': element}
                utilities = object()
                reader, stack, calls = ABC.R(code, 123), [], []
                for _ in range(30):
                    op = reader.u8()
                    if op == 0xd0: stack.append(widget)
                    elif op == 0xb2:
                        name, value = self.after[0].short(reader.u30()), stack.pop()
                        stack.append(value['tab'] if name == 'FarmTabButton' else value['container'])
                    elif op == 0x12:
                        offset = reader.s24()
                        if not stack.pop(): reader.p += offset
                    elif op == 0x66:
                        self.assertEqual(self.after[0].short(reader.u30()), 'm_element')
                        self.assertIs(stack.pop(), widget)
                        stack.append(element)
                    elif op == 0x60:
                        name = self.after[0].short(reader.u30())
                        stack.append(utilities if name == 'Utilities' else 'DisplayObjectContainer')
                    elif op == 0x87:
                        self.assertEqual(stack.pop(), 'DisplayObjectContainer')
                        self.assertTrue(stack[-1]['container'])
                    elif op == 0x27: stack.append(False)
                    elif op == 0x4f:
                        self.assertEqual(self.after[0].short(reader.u30()), 'toggleInputOnlyChildren')
                        self.assertEqual(reader.u30(), 2)
                        enabled, target, receiver = stack.pop(), stack.pop(), stack.pop()
                        self.assertIs(receiver, utilities)
                        calls.append((target, enabled))
                    elif op == 0x47: break
                    else: self.fail('Unexpected tab tail instruction ' + hex(op))
                else: self.fail('Tab tail did not return')
                self.assertEqual(calls, [(element, False)] if tab and container else [])
                self.assertEqual(stack, [])

    def test_port_prefix_preserves_original_method_and_uses_existing_owned_dialog(self):
        before, after = self.before[0].bodies[22256], self.after[0].bodies[22256]
        self.assertEqual(after, graphics.PORT_PREFIX + before)
        self.assertEqual(hashlib.sha256(before).hexdigest(), graphics.PORT_METHOD_SOURCE_SHA256)
        self.assertEqual(hashlib.sha256(after).hexdigest(), graphics.PORT_METHOD_PATCHED_SHA256)
        _, invalid, missing = image_tests.ImageRowClientTests.branch_errors(self, after)
        self.assertEqual((invalid, missing), ([], []))
        for index, name in {2078: 'Global', 75058: 'worldManager', 3407: 'currentWorldType',
                3440: 'isVisiting', 3400: 'isWorldSwapStable', 2912: 'hasValidId',
                6656: 'getState', 8934: 'STATE_BUSY', 2984: 'getItem',
                2057: 'name', 11987: 'displayStorageDialog'}.items():
            self.assertEqual(self.after[0].short(index), name)
        header = ABC.R(self.body, graphics.PORT_CODE_OFFSET - 9)
        self.assertEqual([header.u30() for _ in range(6)], [22256, 4, 2, 18, 19, 431])
        self.assertEqual(header.p, graphics.PORT_CODE_OFFSET)
        end = ABC.R(self.body, header.p + 431)
        self.assertEqual((end.u30(), end.u30()), (0, 0))
        self.assertEqual(self.widget_body[graphics.PORT_CODE_OFFSET:],
                         self.port_body[graphics.PORT_CODE_OFFSET + graphics.PORT_BODY_DELTA:])

    def run_port_prefix(self, case):
        """Execute the real added AVM2; fallback never executes new game actions."""
        world = {'currentWorldType': case.get('world', 'fisherman'),
            'isVisiting': case.get('visiting', False), 'isWorldSwapStable': case.get('stable', True)}
        resource = {'hasValidId': case.get('valid', True), 'getState': case.get('state', 'built_0'),
            'STATE_BUSY': 'busy', 'getItem': {'name': case.get('item', 'fishermanscove')}}
        globals_ = {'Global': {'worldManager': world}}
        reader, stack, calls = ABC.R(self.after[0].bodies[22256]), [], []
        for _ in range(80):
            if reader.p == len(graphics.PORT_PREFIX):
                self.assertEqual(stack, []); return 'original', calls
            op = reader.u8()
            if op == 0x60: stack.append(globals_[self.after[0].short(reader.u30())])
            elif op == 0x66:
                key = self.after[0].short(reader.u30()); stack.append(stack.pop()[key])
            elif op == 0x2c: stack.append(self.after[0].strings[reader.u30()])
            elif op == 0xd0: stack.append(resource)
            elif op == 0x46:
                key = self.after[0].short(reader.u30()); self.assertEqual(reader.u30(), 0)
                owner = stack.pop(); calls.append(key); stack.append(owner[key])
            elif op in (0x11, 0x12, 0x13, 0x14):
                offset = reader.s24()
                if op in (0x11, 0x12):
                    value = bool(stack.pop()); taken = value if op == 0x11 else not value
                else:
                    right, left = stack.pop(), stack.pop()
                    taken = (left == right) if op == 0x13 else (left != right)
                if taken: reader.p += offset
            elif op == 0x4f:
                key = self.after[0].short(reader.u30()); self.assertEqual(reader.u30(), 0)
                self.assertIs(stack.pop(), resource); self.assertEqual(key, 'displayStorageDialog')
                calls.append(key)
            elif op == 0x47:
                self.assertEqual(stack, []); return 'dialog', calls
            else: self.fail('Unexpected Port prefix instruction ' + hex(op))
        self.fail('Port prefix did not choose a branch')

    def test_port_dialog_admission_rejects_foreign_unstable_busy_and_other_worlds(self):
        for case in ({}, {'state': 'built'}, {'state': 'built_11'}):
            with self.subTest(admitted=case):
                result, calls = self.run_port_prefix(case)
                self.assertEqual(result, 'dialog')
                self.assertEqual(calls.count('displayStorageDialog'), 1)
                self.assertTrue(set(calls) <= {'isVisiting', 'hasValidId', 'getState', 'getItem', 'displayStorageDialog'})
        for case in ({'world': 'farm'}, {'world': 'meadows'}, {'world': 'rainforest'},
                {'world': 'fisherman-fake'}, {'world': None}, {'visiting': True},
                {'stable': False}, {'valid': False}, {'state': 'busy'},
                {'item': 'fishermanscovestorage'}, {'item': None}):
            with self.subTest(fallback=case):
                result, calls = self.run_port_prefix(case)
                self.assertEqual(result, 'original')
                self.assertNotIn('displayStorageDialog', calls)

    def test_storage_mask_tail_preserves_original_ctor_and_all_other_fields(self):
        before, after = self.before[0].bodies[30984], self.after[0].bodies[30984]
        self.assertEqual(after, before[:-1] + graphics.MASK_TAIL + before[-1:])
        self.assertEqual(hashlib.sha256(before).hexdigest(), graphics.MASK_METHOD_SOURCE_SHA256)
        self.assertEqual(hashlib.sha256(after).hexdigest(), graphics.MASK_METHOD_PATCHED_SHA256)
        _, invalid, missing = image_tests.ImageRowClientTests.branch_errors(self, after)
        self.assertEqual((invalid, missing), ([], []))
        self.assertEqual(self.after[0].short(2057), 'name')
        self.assertEqual(self.after[0].short(12473), 'getChildByName')
        self.assertEqual(self.after[0].short(28), 'DisplayObject')
        self.assertEqual(self.after[0].short(5085), 'visible')
        self.assertEqual(self.after[0].strings[135712], 'farmDropDown_mc')
        self.assertEqual(self.after[0].strings[139595], 'mask_mc')
        header = ABC.R(self.body, graphics.MASK_CODE_OFFSET - 8)
        self.assertEqual([header.u30() for _ in range(6)], [30984, 2, 3, 13, 14, 76])
        self.assertEqual(header.p, graphics.MASK_CODE_OFFSET)
        end = ABC.R(self.body, header.p + 76)
        self.assertEqual((end.u30(), end.u30()), (0, 0))
        self.assertEqual(self.port_body[graphics.MASK_CODE_OFFSET + 37:],
                         self.body[graphics.MASK_CODE_OFFSET + 37 + graphics.MASK_BODY_DELTA:])

    def run_mask_tail(self, element):
        reader, stack = ABC.R(self.after[0].bodies[30984], 37), []
        for _ in range(40):
            op = reader.u8()
            if op == 0xd1: stack.append(element)
            elif op == 0x66:
                self.assertEqual(self.after[0].short(reader.u30()), 'name')
                stack.append(stack.pop()['name'])
            elif op == 0x2c: stack.append(self.after[0].strings[reader.u30()])
            elif op == 0xac:
                right, left = stack.pop(), stack.pop(); stack.append(type(left) is type(right) and left == right)
            elif op == 0x12:
                offset = reader.s24()
                if not stack.pop(): reader.p += offset
            elif op == 0x46:
                self.assertEqual(self.after[0].short(reader.u30()), 'getChildByName')
                self.assertEqual(reader.u30(), 1)
                name, owner = stack.pop(), stack.pop(); stack.append(owner['children'].get(name))
            elif op == 0x2a: stack.append(stack[-1])
            elif op == 0xb2:
                self.assertEqual(self.after[0].short(reader.u30()), 'DisplayObject')
                value = stack.pop(); stack.append(isinstance(value, dict) and value.get('displayObject') is True)
            elif op == 0x26: stack.append(True)
            elif op == 0x61:
                self.assertEqual(self.after[0].short(reader.u30()), 'visible')
                value, owner = stack.pop(), stack.pop(); owner['visible'] = value
            elif op == 0x10:
                offset = reader.s24(); reader.p += offset
            elif op == 0x29: stack.pop()
            elif op == 0x47: self.assertEqual(stack, []); return
            else: self.fail('Unexpected Storage mask instruction ' + hex(op))
        self.fail('Storage mask tail did not return')

    def test_storage_mask_guard_preserves_other_dropdowns_missing_masks_and_disabled_rows(self):
        import copy
        for name in ('farmDropDown_mc', 'sortDropDown_mc', None):
            for child in (None, 1, {'displayObject': False, 'visible': False},
                    {'displayObject': True, 'visible': False, 'geometry': [1, 2, 3], 'clipDepth': 152}):
                for hidden, disabled in ((False, False), (False, True), (True, False), (True, True)):
                    with self.subTest(name=name, child=child, hidden=hidden, disabled=disabled):
                        element = {'name': name, 'visible': not hidden, 'mouseEnabled': True,
                            'mouseChildren': True, 'children': {'mask_mc': copy.deepcopy(child)},
                            'row': {'visible': True, 'mouseEnabled': not disabled,
                                'mouseChildren': not disabled, 'callback': 'unchanged original callback'}}
                        expected = copy.deepcopy(element)
                        if name == 'farmDropDown_mc' and isinstance(child, dict) and child.get('displayObject') is True:
                            expected['children']['mask_mc']['visible'] = True
                        self.run_mask_tail(element)
                        self.assertEqual(element, expected)
                        self.assertEqual(element['row']['mouseEnabled'], not disabled)
                        self.assertEqual(element['visible'], not hidden)

    def test_exact_final_identity_idempotence_and_all_supported_composition_inputs(self):
        self.assertEqual(graphics.BASE_BODY_SHA256, meadows_client.PATCHED_BODY_SHA256)
        self.assertEqual(hashlib.sha256(self.image_body).hexdigest(), graphics.IMAGE_BODY_SHA256)
        self.assertEqual(hashlib.sha256(self.image_client).hexdigest(), graphics.IMAGE_FILE_SHA256)
        self.assertEqual(hashlib.sha256(self.widget_body).hexdigest(), graphics.WIDGET_BODY_SHA256)
        self.assertEqual(hashlib.sha256(self.widget_client).hexdigest(), graphics.WIDGET_FILE_SHA256)
        self.assertEqual(hashlib.sha256(self.port_body).hexdigest(), graphics.PORT_BODY_SHA256)
        self.assertEqual(hashlib.sha256(self.port_client).hexdigest(), graphics.PORT_FILE_SHA256)
        self.assertEqual(hashlib.sha256(self.body).hexdigest(), graphics.PATCHED_BODY_SHA256)
        self.assertEqual(hashlib.sha256(self.final).hexdigest(), graphics.PATCHED_FILE_SHA256)
        self.assertEqual(graphics.patch_client_bytes(self.final), self.final)
        alternate = self.final[:8] + zlib.compress(self.body, 1)
        self.assertEqual(graphics.patch_client_bytes(alternate), alternate)
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'source.swf'
            for content in (self.raw, PATCH.patch_client_bytes(self.raw), self.previous,
                            self.image_client, self.widget_client, self.port_client, self.final):
                source.write_bytes(content)
                self.assertEqual(graphics.prepared_client(source), self.final)
                self.assertEqual(source.read_bytes(), content)

    def test_stdlib_stager_composes_each_pinned_intermediate_without_reapplying_history(self):
        spec = importlib.util.spec_from_file_location('graphics_stdlib_stager', ROOT / 'macOS/Scripts/patch-game-client.py')
        stager = importlib.util.module_from_spec(spec); spec.loader.exec_module(stager)
        for value in (self.raw, PATCH.patch_client_bytes(self.raw), self.previous,
                self.image_client, self.widget_client, self.port_client, self.final):
            with self.subTest(input_hash=hashlib.sha256(value).hexdigest()):
                self.assertEqual(stager.prepared_client_bytes(value), self.final)

    def test_unknown_modified_oversized_truncated_and_trailing_inputs_refuse(self):
        altered = bytearray(self.before_body); altered[graphics.METHOD_CODE_OFFSET + 400] ^= 1
        unknown = self.previous[:8] + zlib.compress(altered, 1)
        invalid = (b'unknown', self.final[:-3], self.final + b'trailing', self.final[:8] + b'bad',
                   self.final[:4] + b'\0\0\0\0' + self.final[8:], unknown,
                   self.final[:8] + zlib.compress(self.body + b'oversized', 1))
        for value in invalid:
            with self.subTest(value=value[:12]), self.assertRaises(ValueError): graphics.patch_client_bytes(value)
        with mock.patch.object(graphics, 'PATCHED_BODY_SHA256', '0' * 64):
            with self.assertRaisesRegex(ValueError, 'reviewed output'): graphics.patch_client_bytes(self.previous)


if __name__ == '__main__': unittest.main()
