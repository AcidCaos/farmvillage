#!/usr/bin/env python3
"""Recover item labels from the original locale's literal data, without running Flash.

Reads a local SWF and interprets only pushstring/newobject in Locale_en_US's
constructor. No game modules or third-party decompiler are needed. Unknown code
fails closed rather than guessing names from adjacent constant-pool strings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib


class Reader:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def take(self, size):
        end = self.pos + size
        if size < 0 or end > len(self.data):
            raise ValueError('Truncated locale data.')
        result = self.data[self.pos:end]
        self.pos = end
        return result

    def byte(self):
        return self.take(1)[0]

    def uint(self):
        value = 0
        for shift in range(0, 35, 7):
            part = self.byte()
            if shift == 28 and part & 0xf0:
                raise ValueError('Invalid ABC integer.')
            value |= (part & 127) << shift
            if not part & 128:
                return value
        raise ValueError('Invalid ABC integer.')

    def cstring(self):
        end = self.data.find(b'\0', self.pos)
        if end < 0:
            raise ValueError('Unterminated SWF string.')
        return self.take(end - self.pos + 1)[:-1]


def abc_blocks(payload):
    if payload[:3] == b'CWS':
        try:
            payload = b'FWS' + payload[3:8] + zlib.decompress(payload[8:])
        except zlib.error as error:
            raise ValueError('Invalid compressed locale SWF.') from error
    if payload[:3] != b'FWS' or len(payload) < 13:
        raise ValueError('Expected a regular or zlib-compressed SWF.')
    if struct.unpack('<I', payload[4:8])[0] != len(payload):
        raise ValueError('SWF length does not match its header.')
    rect_bytes = (5 + 4 * (payload[8] >> 3) + 7) // 8
    reader = Reader(payload)
    reader.take(8 + rect_bytes + 4)
    while reader.pos < len(payload):
        header = struct.unpack('<H', reader.take(2))[0]
        kind, length = header >> 6, header & 63
        if length == 63:
            length = struct.unpack('<I', reader.take(4))[0]
        data = reader.take(length)
        if kind == 82:
            block = Reader(data)
            block.take(4)
            block.cstring()
            yield block.data[block.pos:]
        if kind == 0:
            break


def traits(reader):
    for _ in range(reader.uint()):
        reader.uint()
        flags = reader.byte()
        kind = flags & 15
        if kind in (0, 6):
            reader.uint()
            reader.uint()
            if reader.uint():
                reader.byte()
        elif kind in (1, 2, 3, 4, 5):
            reader.uint()
            reader.uint()
        else:
            raise ValueError('Unknown locale trait.')
        if flags & 64:
            for _ in range(reader.uint()):
                reader.uint()


def pool_entry(pool, index, kind):
    if not 0 <= index < len(pool):
        raise ValueError('Invalid locale ' + kind + ' index.')
    return pool[index]


def locale_constructor(abc):
    reader = Reader(abc)
    reader.take(4)  # ABC minor and major versions.
    for _ in range(2):
        for _ in range(max(0, reader.uint() - 1)):
            reader.uint()
    reader.take(8 * max(0, reader.uint() - 1))
    strings = ['']
    for _ in range(max(0, reader.uint() - 1)):
        strings.append(reader.take(reader.uint()).decode('utf-8'))
    for _ in range(max(0, reader.uint() - 1)):
        reader.byte()
        reader.uint()
    for _ in range(max(0, reader.uint() - 1)):
        for _ in range(reader.uint()):
            reader.uint()
    names = ['']
    for _ in range(max(0, reader.uint() - 1)):
        kind = reader.byte()
        name = ''
        if kind in (7, 13):
            reader.uint()
            name = pool_entry(strings, reader.uint(), 'string')
        elif kind in (15, 16):
            name = pool_entry(strings, reader.uint(), 'string')
        elif kind in (9, 14):
            name = pool_entry(strings, reader.uint(), 'string')
            reader.uint()
        elif kind in (27, 28):
            reader.uint()
        elif kind == 29:
            reader.uint()
            for _ in range(reader.uint()):
                reader.uint()
        elif kind not in (17, 18):
            raise ValueError('Unknown locale multiname.')
        names.append(name)
    for _ in range(reader.uint()):
        params = reader.uint()
        reader.uint()
        for _ in range(params):
            reader.uint()
        reader.uint()
        flags = reader.byte()
        if flags & 8:
            for _ in range(reader.uint()):
                reader.uint()
                reader.byte()
        if flags & 128:
            for _ in range(params):
                reader.uint()
    for _ in range(reader.uint()):
        reader.uint()
        pairs = reader.uint()
        for _ in range(pairs * 2):
            reader.uint()
    classes = reader.uint()
    constructor = None
    for _ in range(classes):
        name = pool_entry(names, reader.uint(), 'multiname')
        reader.uint()
        if reader.byte() & 8:
            reader.uint()
        for _ in range(reader.uint()):
            reader.uint()
        initializer = reader.uint()
        if name == 'Locale_en_US':
            constructor = initializer
        traits(reader)
    for _ in range(classes):
        reader.uint()
        traits(reader)
    for _ in range(reader.uint()):
        reader.uint()
        traits(reader)
    for _ in range(reader.uint()):
        method = reader.uint()
        for _ in range(4):
            reader.uint()
        code = reader.take(reader.uint())
        if method == constructor:
            return strings, names, code
        for _ in range(reader.uint()):
            for _ in range(5):
                reader.uint()
        traits(reader)
    return None


def literal_properties(strings, names, code):
    reader, stack, properties = Reader(code), [], {}
    instance = object()
    while reader.pos < len(code):
        opcode = reader.byte()
        if opcode == 0xd0:  # getlocal0
            stack.append(instance)
        elif opcode == 0x30:  # pushscope
            if not stack or stack.pop() is not instance:
                raise ValueError('Unexpected locale scope.')
        elif opcode == 0x2c:  # pushstring
            stack.append(pool_entry(strings, reader.uint(), 'string'))
        elif opcode == 0x55:  # newobject (data only)
            count = reader.uint() * 2
            if count > len(stack):
                raise ValueError('Truncated locale object.')
            pairs = stack[-count:] if count else []
            if count:
                del stack[-count:]
            if any(not isinstance(pairs[i], str) for i in range(0, count, 2)):
                raise ValueError('Non-string locale property.')
            stack.append(dict(zip(pairs[::2], pairs[1::2])))
        elif opcode == 0x68:  # initproperty
            name = pool_entry(names, reader.uint(), 'multiname')
            if len(stack) < 2:
                raise ValueError('Missing locale property value.')
            value, owner = stack.pop(), stack.pop()
            if owner is not instance:
                raise ValueError('Unexpected locale property owner.')
            properties[name] = value
        elif opcode == 0x49:  # constructsuper, no code is executed
            if reader.uint() != 0 or not stack or stack.pop() is not instance:
                raise ValueError('Unexpected locale superclass arguments.')
        elif opcode == 0x47:  # returnvoid
            if stack:
                raise ValueError('Locale constructor left unconsumed values.')
            if reader.pos != len(code):
                raise ValueError('Locale constructor contains trailing instructions.')
            return properties
        else:
            raise ValueError(f'Locale contains unsupported instruction 0x{opcode:02x}.')
    raise ValueError('Locale constructor did not return.')


def item_entries(text):
    if not isinstance(text, dict):
        raise ValueError('Locale text table is missing.')
    section = text.get('Items', {})
    if not isinstance(section, dict):
        raise ValueError('Locale Items table is missing.')
    if any(not isinstance(key, str) for key in section):
        raise ValueError('Unexpected locale Items key.')
    if any(key.endswith('_friendlyName') for key in section):
        return section
    result = {}
    for key, bucket in section.items():
        if key == 'length':
            continue
        if not key.isdigit() or not isinstance(bucket, dict):
            raise ValueError('Unexpected locale Items bucket.')
        for name, value in bucket.items():
            if name in result and result[name] != value:
                raise ValueError('Conflicting locale item entries: ' + name)
            result[name] = value
    return result


def recover(payload):
    for abc in abc_blocks(payload):
        constructor = locale_constructor(abc)
        if not constructor:
            continue
        properties = literal_properties(*constructor)
        text = properties.get('text', {})
        items = item_entries(text)
        result, unresolved = {}, []
        for key, entry in items.items():
            if not key.endswith('_friendlyName') or not isinstance(entry, dict):
                continue
            variations = entry.get('variations', {})
            label = variations.get('singular') if isinstance(variations, dict) else None
            # Some original entries have only a literal, already display-ready name.
            if not label:
                label = entry.get('original')
            if not isinstance(label, str) or not label.strip():
                continue
            name = key[:-len('_friendlyName')]
            if '_friendlyName' in label or label.startswith('@Items.'):
                unresolved.append({'name': name, 'key': key, 'value': label,
                                   'reason': 'Unresolved or malformed original localization reference.'})
                continue
            row = {'displayName': label, 'labelSource': 'localization', 'localizationKey': 'Items.' + key}
            description = items.get(name + '_description', {})
            if isinstance(description, dict) and isinstance(description.get('original'), str):
                row['description'] = description['original']
            result[name] = row
        if not result:
            raise ValueError('Locale contained no recoverable item labels.')
        return {'schema': 1, 'recoveryVersion': 2,
                'source': {'file': 'xml/gz/v855098/en_US.swf',
                'sha256': hashlib.sha256(payload).hexdigest()},
                'items': result, 'unresolvedLabels': unresolved}
    raise ValueError('Locale_en_US class was not found.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Read-only original en_US.swf')
    parser.add_argument('output', type=Path, help='God Barn labels JSON destination')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if not output.is_relative_to(root) or output.is_symlink():
        raise SystemExit('Label output must stay inside GodBarn.')
    result = recover(args.source.read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n')
    print(f"Recovered {len(result['items']):,} original item labels.", flush=True)


if __name__ == '__main__':
    main()
