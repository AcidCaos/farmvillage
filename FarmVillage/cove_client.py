"""Pinned regional cottage stage for the restored Cove and rainforest crafts.

Append three literals, replace only updateUpgradeFrame's supported craft predicate.
The original pub substring expression is equivalent to the appended 'pub'
literal. Seven exact crafts fit the existing span: Array.indexOf returns -1
for missing or 0..6 for a match; increment_i then convert_b is the same Boolean
as index >= 0. Branches, method geometry and every price path stay unchanged.
Prices, prerequisites, callbacks, stack/locals and method length are unchanged.
"""
import hashlib
import struct
import zlib

SOURCE_BODY_SHA256 = '2200ebcdc58dfa2061ffaf20e58f8c83b1868449a6b8bae8f81395c27a0454c6'
PATCHED_BODY_SHA256 = '51c484d32ac455abd3669fe1e96bd2cf17303fcfd18a4d265cb9b2eb661ed8f9'
SOURCE_BODY_BYTES = 21521054
PATCHED_BODY_BYTES = SOURCE_BODY_BYTES + 28
METHOD_OFFSET = 16464766
METHOD_BYTES = 1155
METHOD_SOURCE_SHA256 = 'e76391ac236973e0aba013f1e1137c0f4f77a9d5a6a3fbf48656a5440bbb378e'
METHOD_PATCHED_SHA256 = 'b7d5a1bc6c9d65dbc55fa3a37587a9a786dafb0247810f6f64153fd2ea7d20df'
EDITS = ((3399686, b"\x87'\x14\x01", b"\xa3'\x14\x01"), (3411801, b'\x94\xf2\n', b'\x97\xf2\n'), (9457200, b'', b'\x03pub\nrestaurant\x0cxrfcrafttype'), (16465155, b',\xbd\x85\x07,\xbf\x85\x07,\xc1\x85\x07,\xa8\x98\x07$\x0bF\xea\xd1\x05\x01,\x93\xf2\nV\x05\xd0f\xf4\xec\x01f\xcd7F\xe9\xd1\x05\x01$\x00\xb0c\x06\x02', b',\xbd\x85\x07,\xbf\x85\x07,\xc1\x85\x07,\x94\xf2\n,\x93\xf2\n,\x95\xf2\n,\x96\xf2\nV\x07\xd0f\xf4\xec\x01f\xcd7F\xe9\xd1\x05\x01\xc0vc\x06\x02'))



def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _body(data):
    if (len(data) < 8 or data[:4] != b'CWS\x0a'
            or struct.unpack_from('<I', data, 4)[0] not in
               (SOURCE_BODY_BYTES + 8, PATCHED_BODY_BYTES + 8)):
        raise ValueError('The Cove upgrade stage requires a known prepared client.')
    decoder = zlib.decompressobj()
    try:
        body = decoder.decompress(data[8:], PATCHED_BODY_BYTES + 1)
    except zlib.error as error:
        raise ValueError("The Cove upgrade client has invalid compressed data.") from error
    if (len(body) + 8 != struct.unpack_from('<I', data, 4)[0] or not decoder.eof
            or decoder.unused_data or decoder.unconsumed_tail):
        raise ValueError('The Cove upgrade client is truncated or has trailing data.')
    return body


def is_prepared(data):
    """Recognize and validate the final size without accepting an unknown body."""
    if len(data) < 8 or struct.unpack_from('<I', data, 4)[0] != PATCHED_BODY_BYTES + 8:
        return False
    if _digest(_body(data)) != PATCHED_BODY_SHA256:
        raise ValueError('The final Cove client does not match its reviewed pin.')
    return True


def prepare(data):
    if is_prepared(data):
        return data
    body = _body(data)
    if (_digest(body) != SOURCE_BODY_SHA256
            or _digest(body[METHOD_OFFSET:METHOD_OFFSET + METHOD_BYTES]) != METHOD_SOURCE_SHA256):
        raise ValueError('The Cove upgrade source does not match its reviewed pin.')
    for offset, expected, replacement in reversed(EDITS):
        if body[offset:offset+len(expected)] != expected:
            raise ValueError('The Cove upgrade patch does not match its reviewed bytes.')
        body = body[:offset] + replacement + body[offset+len(expected):]
    offset = METHOD_OFFSET + 28
    if (_digest(body) != PATCHED_BODY_SHA256
            or _digest(body[offset:offset+METHOD_BYTES]) != METHOD_PATCHED_SHA256):
        raise ValueError('The Cove upgrade patch did not produce the reviewed client.')
    return data[:4] + struct.pack('<I', len(body)+8) + zlib.compress(body, 9)
