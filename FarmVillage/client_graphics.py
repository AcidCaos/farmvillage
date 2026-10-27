"""Reviewed image completion, input, Cove Port and Storage mask admission.

Applied after the unchanged Meadows compatibility stage. createItemImage
(method23400) rechecks the same cache entry after requestImage, then
continue its original loaded-image path if it completed synchronously. The
asynchronous path still returns null and receives its normal LOADED callback.
ZwBaseWidget.enabled (method4367) then restores the locked native contract:
FarmTabButton visual children cannot intercept their parent's original click.
FeatureBuilding.onClick (method22256) admits the current owned Cove Port
to its unchanged material dialog before an unavailable harvest can block it.
DropDownMenu (method30984) keeps the authored Storage clipping mask visible
so its original rows receive pointer hits under the pinned Ruffle runtime.
No gameplay state, timer, price, reward or callback is created or changed.
Original archives and all earlier compatibility stages remain unchanged.
"""
import hashlib
from pathlib import Path
import struct
import zlib

BASE_BODY_SHA256 = '8f34e1533a4949e411bf75706e3010b74a3e805f1d7f02f10bc799295baa4066'
IMAGE_BODY_SHA256 = '3e05f5235e1ccd540a4a5271e4abcecb9379bce5e9e7b9313e67907f50173fcf'
IMAGE_FILE_SHA256 = '24ae66494840e748f8453d46aea57fda71b336d4854a2a80f42f5e4b240d5d7c'
WIDGET_BODY_SHA256 = 'f46930956f1b11b4a76d03837d683c7777ff0ebd7d3c58c297ba41a0eb1119d5'
PORT_BODY_SHA256 = '5513701851309794566187df76db7337fcb918a1b732b200d108557da8362405'
PATCHED_BODY_SHA256 = 'bd7386cf087f27d57b96c1d46d1629e3b562a3487de51aa2b5ee5adfb0a69d9e'
WIDGET_FILE_SHA256 = '3f97c7212a973ffb7952cad2906b0296d3778472d279374f2a0d5e20ac997d29'
PORT_FILE_SHA256 = 'c2e6dd203b036ce13d1828498addcfac4b4b619f9efdce1c7e1d27a528db7bbf'
PATCHED_FILE_SHA256 = '476fbf7cee3df47fe97ab4d3aefbfdcd14c92b71e5e9d7b8dc2e82ef5ea2156a'
BASE_BODY_BYTES = 21525563
IMAGE_BODY_BYTES = 21525575
WIDGET_BODY_BYTES = 21525610
PORT_BODY_BYTES = 21525701
PATCHED_BODY_BYTES = 21525739
METHOD_ID = 23400
METHOD_CODE_OFFSET = 14980752
METHOD_CODE_BYTES = 1115
METHOD_SOURCE_SHA256 = '75d58352681e577f5e8f92c746befea397f2c1e0b780a3a4cb608799339c889c'
METHOD_PATCHED_SHA256 = '200ba413abef08060bf13592e77a627b714a85b844eb2976a80d623f34b0023f'
CACHE_GUARD = bytes.fromhex('65016c036689a90611040000')
# Decompressed SWF body offsets, after its eight-byte file header.
# Only the enclosing DoABC length, method length/guard/branch and relocated
# exception offsets change. All original limits and activation traits remain.
EDITS = (
    (3399686, bytes.fromhex('24391401'), bytes.fromhex('30391401')),
    (14980750, bytes.fromhex('db08'), bytes.fromhex('e708')),
    (14980877, bytes.fromhex('110000'), bytes.fromhex('1d0000')),
    (14980893, bytes.fromhex(''), bytes.fromhex('65016c036689a90611040000')),
    (14981867, bytes.fromhex('01a804bb04c2044c9350'), bytes.fromhex('01b404c704ce044c9350')),
)
WIDGET_METHOD_ID = 4367
WIDGET_METHOD_BODY_INDEX = 4299
WIDGET_CODE_OFFSET = 12420172  # In the completed image-cache stage.
WIDGET_CODE_BYTES = 124
WIDGET_METHOD_SOURCE_SHA256 = 'bfe5a5aff3a27c161c29464cba0ceb2be9261ec4dc18a806007f5f240ed9a1fc'
WIDGET_METHOD_PATCHED_SHA256 = '259c3c436a0718a9e6f5561ad76db4d27087ad94badb5435d69d79cda2000ff2'
WIDGET_TAIL = bytes.fromhex('d0b2c708121a0000d066d327b2191210000060c40dd066d327601987274fa1c7040247')
WIDGET_BODY_DELTA = 35  # 34 instruction bytes plus one U30 code-length byte.
WIDGET_EDITS = (
    (3399686, bytes.fromhex('30391401'), bytes.fromhex('53391401')),
    (12420171, bytes.fromhex('7c'), bytes.fromhex('9e01')),
    (12420295, bytes.fromhex('47'), WIDGET_TAIL),
)


PORT_METHOD_ID = 22256
PORT_METHOD_BODY_INDEX = 22071
PORT_CODE_OFFSET = 14859878  # In the completed tab-input stage.
PORT_CODE_BYTES = 340
PORT_METHOD_SOURCE_SHA256 = '9fe9976081f8219d53a7c006299e075bef757d7aba99327642d60293f388550d'
PORT_METHOD_PATCHED_SHA256 = '56e296c5ba6be7d543dfac70caf516fb2b1c24d3a3daf29191162b873923c733'
PORT_PREFIX = bytes.fromhex('609e1066b2ca0466cf1a2cd2d60614490000609e1066b2ca0446f01a00113a0000609e1066b2ca0466c81a122c0000d046e0160012230000d046803400d066e64513160000d046a817006689102cd8aa0714060000d04fd35d0047')
PORT_BODY_DELTA = 91
PORT_EDITS = (
    (3399686, bytes.fromhex('53391401'), bytes.fromhex('ae391401')),
    (14859876, bytes.fromhex('d402'), bytes.fromhex('af03')),
    (14859878, bytes.fromhex(''), PORT_PREFIX),
)


MASK_METHOD_ID = 30984
MASK_METHOD_BODY_INDEX = 30729
MASK_CODE_OFFSET = 15972499  # In the completed Cove Port stage.
MASK_CODE_BYTES = 38
MASK_METHOD_SOURCE_SHA256 = 'dbea3d48b40f44f89976090f88f9a19b555659b1657f5fdecba650510772b13a'
MASK_METHOD_PATCHED_SHA256 = '93c05075850239d70b85efc126df7ceb57125ddb7668156d08300094d55f60c0'
MASK_TAIL = bytes.fromhex('d16689102ca0a408ac12190000d12ccbc20846b961012ab21c120800002661dd271001000029')
MASK_BODY_DELTA = 38
MASK_EDITS = (
    (3399686, bytes.fromhex('ae391401'), bytes.fromhex('d4391401')),
    (15972498, bytes.fromhex('26'), bytes.fromhex('4c')),
    (15972536, bytes.fromhex(''), MASK_TAIL),
)


def _body(data):
    if len(data) < 8 or data[:4] != b'CWS\x0a':
        raise ValueError('Graphics compatibility requires the reviewed CWS10 client.')
    declared = struct.unpack_from('<I', data, 4)[0] - 8
    if declared not in (BASE_BODY_BYTES, IMAGE_BODY_BYTES, WIDGET_BODY_BYTES, PORT_BODY_BYTES, PATCHED_BODY_BYTES):
        raise ValueError('The graphics client length is invalid.')
    decoder = zlib.decompressobj()
    try:
        body = decoder.decompress(data[8:], PATCHED_BODY_BYTES + 1)
    except zlib.error as error:
        raise ValueError('The graphics client compressed body is invalid.') from error
    if (len(body) != declared or not decoder.eof
            or decoder.unused_data or decoder.unconsumed_tail):
        raise ValueError('The graphics client length is invalid or has trailing data.')
    return body


def patch_image_bytes(data):
    """Retain the accepted cache-completion stage as an exact composition input."""
    body = _body(data)
    digest = hashlib.sha256(body).hexdigest()
    if digest in (IMAGE_BODY_SHA256, WIDGET_BODY_SHA256, PORT_BODY_SHA256, PATCHED_BODY_SHA256):
        return data
    if digest != BASE_BODY_SHA256:
        raise ValueError('Refusing to modify unknown graphics game code.')
    code = body[METHOD_CODE_OFFSET:METHOD_CODE_OFFSET + METHOD_CODE_BYTES]
    if hashlib.sha256(code).hexdigest() != METHOD_SOURCE_SHA256:
        raise ValueError('The reviewed image-completion method changed.')
    for offset, old, new in reversed(EDITS):
        if body[offset:offset + len(old)] != old:
            raise ValueError('A reviewed graphics compatibility location changed.')
        body = body[:offset] + new + body[offset + len(old):]
    if hashlib.sha256(body).hexdigest() != IMAGE_BODY_SHA256:
        raise ValueError('Graphics compatibility did not produce the reviewed output.')
    return data[:4] + struct.pack('<I', len(body) + 8) + zlib.compress(body, 9)


def patch_widget_bytes(data):
    """Retain the exact accepted tab-input stage as a composition input."""
    data = patch_image_bytes(data)
    body = _body(data)
    if hashlib.sha256(body).hexdigest() in (WIDGET_BODY_SHA256, PORT_BODY_SHA256, PATCHED_BODY_SHA256):
        return data
    code = body[WIDGET_CODE_OFFSET:WIDGET_CODE_OFFSET + WIDGET_CODE_BYTES]
    if hashlib.sha256(code).hexdigest() != WIDGET_METHOD_SOURCE_SHA256:
        raise ValueError('The reviewed tab child-input method changed.')
    for offset, old, new in reversed(WIDGET_EDITS):
        if body[offset:offset + len(old)] != old:
            raise ValueError('A reviewed tab child-input location changed.')
        body = body[:offset] + new + body[offset + len(old):]
    if hashlib.sha256(body).hexdigest() != WIDGET_BODY_SHA256:
        raise ValueError('Tab input compatibility did not produce the reviewed output.')
    return data[:4] + struct.pack('<I', len(body) + 8) + zlib.compress(body, 9)


def patch_port_bytes(data):
    """Retain the accepted Port stage as an exact composition input."""
    data = patch_widget_bytes(data)
    body = _body(data)
    if hashlib.sha256(body).hexdigest() in (PORT_BODY_SHA256, PATCHED_BODY_SHA256):
        return data
    code = body[PORT_CODE_OFFSET:PORT_CODE_OFFSET + PORT_CODE_BYTES]
    if hashlib.sha256(code).hexdigest() != PORT_METHOD_SOURCE_SHA256:
        raise ValueError('The reviewed Cove Port click method changed.')
    for offset, old, new in reversed(PORT_EDITS):
        if body[offset:offset + len(old)] != old:
            raise ValueError('A reviewed Cove Port admission location changed.')
        body = body[:offset] + new + body[offset + len(old):]
    if hashlib.sha256(body).hexdigest() != PORT_BODY_SHA256:
        raise ValueError('Cove Port admission did not produce the reviewed output.')
    return data[:4] + struct.pack('<I', len(body) + 8) + zlib.compress(body, 9)


def patch_client_bytes(data):
    """Compose only pinned stages; the exact final body is idempotent."""
    data = patch_port_bytes(data)
    body = _body(data)
    if hashlib.sha256(body).hexdigest() == PATCHED_BODY_SHA256:
        return data
    code = body[MASK_CODE_OFFSET:MASK_CODE_OFFSET + MASK_CODE_BYTES]
    if hashlib.sha256(code).hexdigest() != MASK_METHOD_SOURCE_SHA256:
        raise ValueError('The reviewed Storage dropdown constructor changed.')
    for offset, old, new in reversed(MASK_EDITS):
        if body[offset:offset + len(old)] != old:
            raise ValueError('A reviewed Storage mask location changed.')
        body = body[:offset] + new + body[offset + len(old):]
    if hashlib.sha256(body).hexdigest() != PATCHED_BODY_SHA256:
        raise ValueError('Storage mask compatibility did not produce the reviewed output.')
    return data[:4] + struct.pack('<I', len(body) + 8) + zlib.compress(body, 9)


def prepared_client(source):
    """Compose raw, historical prepared, Meadows or already final source bytes."""
    data = Path(source).read_bytes()
    if len(data) >= 8 and struct.unpack_from('<I', data, 4)[0] in (
            BASE_BODY_BYTES + 8, IMAGE_BODY_BYTES + 8, WIDGET_BODY_BYTES + 8, PORT_BODY_BYTES + 8, PATCHED_BODY_BYTES + 8):
        return patch_client_bytes(data)
    import meadows_client
    return patch_client_bytes(meadows_client.prepared_client(source))
