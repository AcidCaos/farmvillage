"""Meadows-only restoration of original Inventory upgrade/shipping controls.

Applied after client_compatibility. Only five reviewed methods change. Each
wrapper selects the recovered original method when currentWorldType is
meadows and otherwise executes the already prepared refusal/hidden controls.
The two branches keep their original instructions and relative branch targets;
constant pools, object state, prices and all other methods remain unchanged.
"""
import base64
import hashlib
from pathlib import Path
import struct
import zlib

BASE_BODY_SHA256 = "51c484d32ac455abd3669fe1e96bd2cf17303fcfd18a4d265cb9b2eb661ed8f9"
PATCHED_BODY_SHA256 = "8f34e1533a4949e411bf75706e3010b74a3e805f1d7f02f10bc799295baa4066"
PATCHED_BODY_BYTES = 21_525_563
# Existing pool entries: Global2078/worldManager75058/currentWorldType3407/
# string meadows109509. The guard does not access this before constructor super.
WORLD_GUARD = bytes.fromhex("609e1066b2ca0466cf1a2cc5d706")
# id, body offset, original prepared length, prepared SHA, compressed raw code.
METHODS = (
    (12193, 13510220, 2711, '2981b637ccc6e6f750251ee179ec43a4c94711bbfb1f5764aea0bd18db39b985', 'eNqFVltMFFcYPmdmdhkuC4O2SaOJoSnBavbB+uyLLzbZpl1e2Kdydl3Syb43TfqIC8uK1Ava4mqE2LgiiHihanqz0tbYVFAHaKHBS1XEqhX2V7l43e1/zuyyZ4wND8zZ8/3ff/vOmX942PghnKDWmorYWEX9lFrnEk+3eBZU1Ot1eooOVJMzNEV3J3V6AdcrTZoygOvgPl29SaGPWh9BGYGTtHa8rDathYbKzLmoO9SxzHu7yJtI6huO/kwVX1pT/ONlFE5Ri/NqOG0+6vbV0FCHYfZd0MzLy0Iv1pgDN7WeDeNlSqgmHrnK4LREf/Ia+qBEv8bgW5tuV/F0oYp9Sd377APLTLMaystReTnoRkNpLR65zuA72e/Zgl971u/la/3+ZvCDVN5zUZ6wYjE3GJyhobHl5u4xraKnbfWSpYSsyu69A9XmbNTtpT1tHHaiMWM9IfCT8E284pt4rW9C8nURYpn/sFjsTzgr94TFmS+i7iFHAxMM+qlkDT2g5uVrLsvcEfS/jLoV+PlV6xC3bs9af3FYy83EMBq3Zo2/OoxLzO9H0NiaNZ6jljnBvO0TBf6+dymctyvt1HMu6ajbMrcFfZ26XWynHo/cZPCbU20z41D8FoPfbUK/aLm+IXuMoYF5zTu9S90vbqJl7gz6+jW19tK8tgH/iLg+/SjHEwYXaIDU66MwQCtJXSG/YF/f0qJ1RcZqQgrDReHCd2JjMEiHa6fUkXzwETuyb0pV/G3DLorua4sKywczGb1IL4Qhu6pqXtSmBuwsFvRV241VxyMpBsMoR4qZoytDb8dRx3vTGuesrCRV/t43XTDiNN/n5qa8edQOPxng8aM8fjzomwwoK0Vjk4F4BBiMYQz4/xR/Oc2vphin2dhmQ4N7yXK8n1eEQ+06Cfeto/49eJrX5ENozB2C90B2EljmLqF/1YLuTxlcp5a/MUjgFkVlvR2l0sF1lNrqVqG8KkwIQmuVRGityssPt4W95YYqEXAnMSYF4/Q2KjFwJzHuCEazIRGajbw94MKxqMFdu80ZlbcZ47JvDoY134yqipOdUeORSQb3UKdJVkn8I39QCg+wzU3Y5pT8ajYtSHRQGpb26fG3dJrBtJwrznNtCQZIFSbTFpLdYZCiFsAiCgZo5CGDR8h8vJjWM4Jwblp+jXAnU2YFpTOpSxTcyZQ5QTnkoBxyUAJa5BGDJ1jS08VKeiYIXY5gXblg4vCeC8ali/IFwJ10fGrkMYOXmC29WLaMIHQ7snU7stUri12mTYJx2BHjsCNGVDB6HIwemRFwRWYYNCq5r8kbP1KSonNRXYsrKXokqbs249qb1N3NuB5N6gVbFIhxeg3ZiA7QlHP1HkvqFRvxQwEtCh9ww3y0fUyzo018/+ELfENnWdhldr2FcgjyVk4uDuMgLDEqOLskXCzYbtiG7DmbHXbjY3/Wx6jGgQmtaH3E+H8RsFMxOjj0JUKPbegrxWjh0G6EZmwooRifc2gvQg9taJ9ifEKIsRGHznZF5Kjz8FcadihhzzI3IZXEeI8QLjvsykHUWIFQswFtOUQxSjAK/6UaCn/qnuV7Mhk1lMl8msk0ZTK4gXbeqCesR+tKjVV84peGPaLRAujAiublRsMF/FlJhELtytpST/lFHPilugf1WltSXD6azuglejFKzT8Ge9PiY2AksI8DipU7kLM3CviHOzLLIJlHjyd1gc4xOJhHT2TReQadefT8egHeZXAoD3Z/JsB7DLryYMtdVaD3GXTn0d6rdgX/MuiR7wkH8/9rLfVj3Udke94mFOjNR8w685KOKhZeCF7HMfsX5j6uWJWEp+tTLH8DTsNvcG3G9SSu6RUETinv/weIwlba'),
    (12394, 13543116, 65, '458852c5e5254a3790fa7719e436178c5bfc6fd4ce71493157c76e7a3d9e8772', 'eNr7eHwZxweJCwbvGdfYMkh8kLxw0e91NOMHqYSL/GVaQpwMDJo6J5ZxAHlbhAQYGD5IA1lpe1vYEhTb1RLvqn+QcwcAgykZZQ=='),
    (12402, 13544557, 197, 'd285d143485d051dd485533fc16233d5379ba547d6814c08e7423962915b616f', 'eNr7eGoZx4fQCwYKDRzJrO8Z70gzhL5nvLmMgxFInbnCyASkbi3jYA79YHkhlsOLgyFjbcIHjwuxjF6MDBmbEj4EQkW3JXwIj2vj17m9jCOjjf9DxAWdQ3wZ6xI+RF64lLEx4UP0RQURDQaG94xf77CzxHyISZgnkHYiNOEko9sjPUaQzR9ik1hVGNL2t7A1nGS8+iHxwsWMlQkfki8LSTEwfEhJMIzdcIfx4gUdoIuSWLyAbBY1//niTB/SL3gyfMhwBwDxs1Lz'),
    (12403, 13544764, 942, '0673ee146deb3ece8f10e43f28fe8cecd1093d4ba474e175240b76dc2264338e', 'eNpdks9PE0EUx+ct03UhwZZGLxgPxsIq6cF/oZeaQOKePJJMIZmbJkpSD5iIZhGIP0j8QSDyQ0MpKtYCQvSgEKqAFpVhKxqj+COaiMaEZ/yB8VKn3e5aOb35vO+bz+5M5ls6ruEBsWcNVluANK/B67gGrbAGyTZNGZa1c9FTkpQ12wN0FPCg2NfjJXiImV5+31T5A1NlFbzb8gie8BqzpqrgYSebczL2PWRHTU4070Y/CtER1l8p0+CbuBb8WBbsjmnGyi6KzQGyjEcFv8b8lYTgMdbv4y1pqhcqf7YzPBhQmpbxOBQEb21Bb0wL/qlb2g9S48ETTvrOTvvyaUESHgqQwlwr1FvU+cmHpir4XVZrUaXFos/xJFh8XA+mNkc6fNgGVrUxqwO2gyXdOen7uBa+OQNKJKVjBwg+zuSsFZk2VTxV7H20wXva9v5spznxGUd81hV/KBJ32mI5bJvPFZvTG8zn82Y29ztvvuCYL7rmwdg/c1fenBu2zT15FnyMcYnMonzhFY0syOQSsK8h7AXns49lr8+lJ5L6XXoqacClRUmXXRKSrri0ZKpGl+VRMQb16yFjPURwCIQxzQgOQ4C88HkJKcWrIDJGioHspUoygl9niRp/KSG7M+xLiHfXJSpeZrM4AqJ+kjlmy1RrJxlEJhjekIeaYIxy/EQFv8OMxFYFE/mmHlnRMQnOyxqo4hlTjdb4t0n5/02WLedT87RqddNgItpIcbR404zMJZlpGvw8oAXKwsntykijB8eggUZrKqi0NXii/nL5msdBVBu/QuDbIeEW5K46d/1b/BInQOjGlDznZG7onlzchr1/AVU3jKk='),
    (12423, 13552506, 475, '2fe3bdfe08cc453ebe02c47c218f3a1db417fd83bd630a84c21a8ada20a557a0', 'eNp9T79LQlEYvVff93y4JCIkiuBgQvGItqag6TY0OLkVXBTuPyA0OxjR1twPTYJeQSaE/4BQkBb0VNAlIiwNLfJaimJhXS2jpaYD5zvnO+c0s/sKL4M+4w5ncKmBj+ZQGRp4U1NwReC101AXEH81GRsCTyIGqSXwqmqCzte5C/wOdK+vSDGvAI1aWCQrqbWY4jGTpMsQKvLqkA1nJRabYP2IbHUgxB8gv2z/xacjMrHjuJDXQWeHdNCGP0LBbXMJ9dPwxblfZ0nKboT0dhrTDF4bqhqj1AI5GEekPYvIswuHNRyUeBMCElu3qFuaQmo5wB40Zhb/XgZ0yibSWsLsUO/N6ramqL3FvB+T4zQ2rgaBt0HP+U7FrM7PrF7HRBIuHArKvPtfpR4E5O9xZM+DdHJB0W5iympCaLJAPpbQinVe1Hgbhe8MwwOyGt1Q8n7DT4V3oCVnAOgZZlpG0tklVbHXlypJYHEKf//PMw/LC59i38Pi'),
 )


def _u30(value):
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def _abc_header(body):
    """Find the one DoABC containing every reviewed method offset."""
    bits = body[0] >> 3
    position = (5 + 4 * bits + 7) // 8 + 4
    while position < len(body):
        tag = struct.unpack_from("<H", body, position)[0]
        position += 2
        kind, length = tag >> 6, tag & 63
        length_at = position
        if length == 63:
            length = struct.unpack_from("<I", body, position)[0]
            position += 4
        if kind == 82 and all(position <= row[1] < position + length for row in METHODS):
            if (tag & 63) != 63:
                raise ValueError("The reviewed Meadows DoABC header changed.")
            return length_at, length
        position += length
        if kind == 0:
            break
    raise ValueError("The reviewed Meadows DoABC is unavailable.")


def patch_client_bytes(data):
    """Reject unknown clients; accept either exact reviewed body idempotently."""
    if len(data) < 8 or data[:4] != b"CWS\x0a":
        raise ValueError("The Meadows controls require the reviewed CWS10 client.")
    declared = struct.unpack_from("<I", data, 4)[0] - 8
    if declared not in (21_521_082, PATCHED_BODY_BYTES):
        raise ValueError("The Meadows client length is invalid.")
    decoder = zlib.decompressobj()
    try:
        body = decoder.decompress(data[8:], PATCHED_BODY_BYTES + 1)
    except zlib.error as error:
        raise ValueError("The Meadows client compressed body is invalid.") from error
    if (len(body) != declared or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail):
        raise ValueError("The Meadows client length is invalid or has trailing data.")
    digest = hashlib.sha256(body).hexdigest()
    if digest == PATCHED_BODY_SHA256:
        return data
    if digest != BASE_BODY_SHA256:
        raise ValueError("Refusing to modify unknown Meadows game code.")
    length_at, abc_length = _abc_header(body)
    changed = bytearray(body)
    growth = 0
    for ident, offset, length, expected, compressed in reversed(METHODS):
        before = body[offset:offset + length]
        if hashlib.sha256(before).hexdigest() != expected:
            raise ValueError("A reviewed Meadows control method changed.")
        original = zlib.decompress(base64.b64decode(compressed))
        # Guard stack: currentWorldType, 'meadows'; ifeq consumes both.
        # Both methods retain their original scope prologue and terminal return.
        prefix = WORLD_GUARD + b"\x13" + length.to_bytes(3, "little", signed=True)
        after = prefix + before + original
        old_length = _u30(length)
        if body[offset - len(old_length):offset] != old_length:
            raise ValueError("A Meadows method code-length header changed.")
        replacement = _u30(len(after)) + after
        changed[offset - len(old_length):offset + length] = replacement
        growth += len(replacement) - len(old_length) - length
    struct.pack_into("<I", changed, length_at, abc_length + growth)
    result_body = bytes(changed)
    if hashlib.sha256(result_body).hexdigest() != PATCHED_BODY_SHA256:
        raise ValueError("The Meadows controls did not produce the reviewed output.")
    return data[:4] + struct.pack("<I", len(result_body) + 8) + zlib.compress(result_body, 1)


def prepared_client(source):
    """Serve raw, the earlier prepared build, or this exact reviewed build."""
    data = Path(source).read_bytes()
    if len(data) >= 8 and struct.unpack_from("<I", data, 4)[0] == PATCHED_BODY_BYTES + 8:
        return patch_client_bytes(data)
    import client_compatibility
    return patch_client_bytes(client_compatibility.prepared_client(source))
