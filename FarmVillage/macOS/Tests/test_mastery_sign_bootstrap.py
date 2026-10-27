"""Restore the original mastery-popup gift path without altering sign definitions.

The removal experiment controls new popup insertion. Persisted GiftBox All
filtering has a separate path; these checks do not claim native UI acceptance.
"""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import unittest
from unittest import mock
import zlib

from jinja2 import DictLoader

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures  # Establish temporary data before product imports.
import items
import mastery_signs
from test_turbo_client_refusal import ABC, ROOT, read_abcs

GATE = 'fv_ops_remove_masterysigns'
LITERAL = '"' + GATE + '": 0'


def experiments(text):
    return [(key, int(value)) for key, value in
            re.findall(r'"(fv_[A-Za-z0-9_]+)"\s*:\s*(-?\d+)', text)]


def execute(abc, method, instance, globals_, *, start=0, stop=None, argument=None):
    """Execute only the original AVM2 gate/call-site/filter instructions."""
    reader = ABC.R(abc.bodies[method], start)
    stack, locals_ = [], {0: instance, 1: argument}

    def truth(value):
        return True if isinstance(value, (dict, list)) else bool(value)

    for _ in range(1000):
        if reader.p == stop:
            if stack:
                raise AssertionError('Unbalanced original call-site stack')
            return None
        at, op = reader.p, reader.u8()
        if op in (0x02, 0x09):
            pass
        elif op in (0xf0, 0xf1):
            reader.u30()
        elif op == 0xef:
            reader.u8(); reader.u30(); reader.u8(); reader.u30()
        elif 0xd0 <= op <= 0xd3:
            stack.append(locals_[op - 0xd0])
        elif 0xd4 <= op <= 0xd7:
            locals_[op - 0xd4] = stack.pop()
        elif op == 0x62:
            stack.append(locals_[reader.u30()])
        elif op == 0x63:
            locals_[reader.u30()] = stack.pop()
        elif op == 0x08:
            locals_.pop(reader.u30(), None)
        elif op == 0x30:
            stack.pop()
        elif op == 0x20:
            stack.append(None)
        elif op in (0x26, 0x27):
            stack.append(op == 0x26)
        elif op == 0x24:
            value = reader.u8()
            stack.append(value - 256 if value > 127 else value)
        elif op == 0x2c:
            stack.append(abc.strings[reader.u30()])
        elif op in (0x60, 0x5d):
            stack.append(globals_[abc.mname(reader.u30())])
        elif op == 0x66:
            name = abc.short(reader.u30())
            stack.append(stack.pop()[name])
        elif op == 0x80:
            reader.u30()
        elif op in (0x73, 0x76, 0x85):
            value = stack.pop()
            stack.append(int(value) if op == 0x73 else truth(value) if op == 0x76
                         else str(value) if value is not None else None)
        elif op == 0x2a:
            stack.append(stack[-1])
        elif op == 0x29:
            stack.pop()
        elif op == 0x96:
            stack.append(not truth(stack.pop()))
        elif op in (0xab, 0xaf, 0xb0):
            right, left = stack.pop(), stack.pop()
            stack.append(left == right if op == 0xab else left > right if op == 0xaf else left >= right)
        elif op in (0x46, 0x4f):
            name, count = abc.short(reader.u30()), reader.u30()
            args = [stack.pop() for _ in range(count)][::-1]
            receiver = stack.pop()
            result = receiver(*args) if callable(receiver) else receiver[name](*args)
            if op == 0x46:
                stack.append(result)
        elif op in (0x10, 0x11, 0x12, 0x13, 0x14, 0x1a):
            delta = reader.s24()
            if op == 0x10:
                take = True
            elif op in (0x11, 0x12):
                take = truth(stack.pop()) == (op == 0x11)
            else:
                right, left = stack.pop(), stack.pop()
                equal = left == right
                if op == 0x1a:
                    equal = equal and type(left) is type(right)
                take = equal == (op == 0x13)
            if take:
                reader.p += delta
        elif op == 0x1b:
            default = reader.s24()
            offsets = [reader.s24() for _ in range(reader.u30() + 1)]
            index = stack.pop()
            reader.p = at + (offsets[index] if 0 <= index < len(offsets) else default)
        elif op == 0x48:
            result = stack.pop()
            if stack:
                raise AssertionError('Unbalanced original return stack')
            return result
        else:
            raise AssertionError(f'Unexpected original opcode {op:#x} at {at}')
    raise AssertionError('Original method did not finish')


class MasterySignClientGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        original = (ROOT / 'embeds/Flash/v855097-855094/FarmGame.swf').read_bytes()
        cls.abc = read_abcs(zlib.decompress(original[8:]))[0]

    def gate(self, variant):
        def get_variant(key):
            self.assertEqual(key, GATE)
            return variant
        return execute(self.abc, 4218, {}, {
            'Global': {'experimentManager': {'getExperimentVariant': get_variant}},
            'Classes.Constants:Experiments': {'EXPERIMENT_FLASH_MASTERYSIGNS': GATE},
        })

    def test_original_gate_keeps_signs_for_zero_and_removes_them_for_one(self):
        self.assertIs(self.gate(0), True)
        self.assertIs(self.gate(1), False)
        self.assertIs(self.gate(2), True)

    def test_original_popup_inserts_only_nonempty_new_reward_when_gate_allows(self):
        for variant, gift, reward, expected in (
            (0, 'masterxhl_santaberries', True, ['masterxhl_santaberries']),
            (1, 'masterxhl_santaberries', True, []),
            (0, 'masterxhl_santaberries', False, []), (0, '', True, []),
        ):
            calls = []
            with self.subTest(variant=variant, gift=gift, reward=reward):
                execute(self.abc, 15755, {'m_masteryGift': gift, 'm_giveReward': reward},
                        {'Global': {'player': {'masterySignEnabled': lambda: self.gate(variant),
                                               'addGift': calls.append}}}, start=303, stop=363)
                self.assertEqual(calls, expected)

    def test_persisted_all_filter_remains_independent_of_popup_removal_gate(self):
        row = {'farmItem': {'name': 'masterxhl_santaberries'},
               'type': 'decoration', 'className': 'DynamicMasterySign'}
        for variant in (0, 1):
            globals_ = {'Classes.ZItem:FarmItem': lambda item: item,
                        'Global': {'player': {'masterySignEnabled': lambda: self.gate(variant)}}}
            self.assertIs(execute(self.abc, 32681, {'m_type': 'all'}, globals_, argument=row), True)
            self.assertIs(execute(self.abc, 32681, {'m_type': 'unknown'}, globals_, argument=row), False)


class MasterySignBootstrapTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture

    def render(self, route, templates=None):
        self.server.app.jinja_env.cache.clear()
        loader = self.server.app.jinja_loader if templates is None else DictLoader(templates)
        try:
            with mock.patch.object(self.server.app, 'jinja_loader', loader), \
                    mock.patch.object(self.server, 'NATIVE_WRAPPER', False), redirect_stdout(io.StringIO()):
                return self.client.get(route)
        finally:
            self.server.app.jinja_env.cache.clear()

    def test_both_rendered_routes_enable_signs_and_preserve_every_other_experiment(self):
        path = self.write_fixture()
        saved = path.read_bytes()
        with self.client.session_transaction() as session:
            session['UID'] = 'fixture-farmer'
        for route in ('/play.html', '/ruffle.html'):
            source = (ROOT / 'templates' / route[1:]).read_text()
            self.assertEqual(source.count(LITERAL), 1)
            # Reconstruct the previous flag state without modifying a source file.
            previous = source.replace(LITERAL, LITERAL[:-1] + '1')
            with self.subTest(route=route):
                before = self.render(route, {route[1:]: previous})
                after = self.render(route)
                self.assertEqual((before.status_code, after.status_code), (200, 200))
                before, after = experiments(before.get_data(as_text=True)), experiments(after.get_data(as_text=True))
                self.assertEqual(sum(key == GATE for key, _ in after), 1)
                self.assertEqual(dict(before)[GATE], 1)
                self.assertEqual(dict(after)[GATE], 0)
                self.assertEqual([(key, value) for key, value in before if key != GATE],
                                 [(key, value) for key, value in after if key != GATE])
                self.assertEqual(path.read_bytes(), saved)

    def test_unauthenticated_routes_still_redirect_without_mutating_save(self):
        path = self.write_fixture()
        saved = path.read_bytes()
        for route in ('/play.html', '/ruffle.html'):
            response = self.render(route)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers['Location'], '/')
        self.assertEqual(path.read_bytes(), saved)

    def test_rendering_keeps_exact155_legacy_and12_glen_definitions(self):
        path = self.write_fixture()
        with self.client.session_transaction() as session:
            session['UID'] = 'fixture-farmer'
        raw = Path(items.ITEMS_AMF).read_bytes()
        definitions = [row for row in items.get_items()
                       if str(row.get('code', '')).startswith(mastery_signs.CODE_PREFIX)]
        golden = json.loads((ROOT / 'macOS/Tests/Fixtures/mastery-signs-legacy155.json').read_text())['definitions']
        self.assertEqual(definitions[:155], golden)
        self.assertEqual(len(definitions), 167)
        self.assertEqual({(row['name'], row['masteredItemCode']) for row in definitions[155:]},
                         mastery_signs.GLEN_GIFTS)
        canonical = json.dumps(definitions, separators=(',', ':')).encode()
        self.assertEqual(hashlib.sha256(canonical).hexdigest(),
                         'efda8b9bcf9bb065a3c67b993b75ecb5ebbb639ccd4e05508c19f606ca1de9fe')
        for route in ('/play.html', '/ruffle.html'):
            self.assertEqual(self.render(route).status_code, 200)
        after = [row for row in items.get_items()
                 if str(row.get('code', '')).startswith(mastery_signs.CODE_PREFIX)]
        self.assertEqual(json.dumps(after, separators=(',', ':')).encode(), canonical)
        self.assertEqual(Path(items.ITEMS_AMF).read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
