"""Recover original labels from inert literal ABC/SWF fixtures, without Flash."""
import hashlib
import importlib.util
from pathlib import Path
import struct
import unittest
import zlib


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("god_barn_label_recovery", ROOT / "scripts/recover_labels.py")
labels = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(labels)


def uint(value):
    result = bytearray()
    while True:
        part = value & 127
        value >>= 7
        result.append(part | (128 if value else 0))
        if not value:
            return bytes(result)


def literal_fixture(properties, *, padding=0):
    strings = [""] + [f"unused {index}" for index in range(padding)]
    names = [""] + list(properties)

    def index(value):
        if value not in strings:
            strings.append(value)
        return strings.index(value)

    def value_code(value):
        if isinstance(value, str):
            return b"\x2c" + uint(index(value))
        if isinstance(value, dict):
            pairs = b"".join(value_code(key) + value_code(nested) for key, nested in value.items())
            return pairs + b"\x55" + uint(len(value))
        raise TypeError("Fixture literal supports only strings and objects.")

    code = b"\xd0\x30"  # getlocal0 / pushscope
    for name, value in properties.items():
        code += b"\xd0" + value_code(value) + b"\x68" + uint(names.index(name))
    code += b"\xd0\x49\x00\x47"  # inert super() / returnvoid
    return strings, names, code


def abc_fixture(text, *, class_name="Locale_en_US"):
    strings, names, code = literal_fixture({"text": text})
    # A complete minimal ABC with a QName, one class, one method and its body.
    for value in (class_name, "text"):
        if value not in strings:
            strings.append(value)
    result = struct.pack("<HH", 16, 46)
    result += uint(1) * 3  # int, uint and double constant pools
    result += uint(len(strings))
    for value in strings[1:]:
        encoded = value.encode("utf-8")
        result += uint(len(encoded)) + encoded
    result += uint(2) + b"\x16" + uint(0)  # package namespace
    result += uint(1)  # namespace sets
    result += uint(3)
    for name in (class_name, "text"):
        result += b"\x07" + uint(1) + uint(strings.index(name))  # QName
    result += uint(1) + uint(0) + uint(0) + uint(0) + b"\x00"  # method info
    result += uint(0)  # metadata
    result += uint(1)  # class count
    result += uint(1) + uint(0) + b"\x00" + uint(0) + uint(0) + uint(0)  # instance
    result += uint(0) + uint(0)  # class initializer, class traits
    result += uint(0)  # scripts
    result += uint(1) + uint(0) + uint(64) + uint(1) + uint(0) + uint(1)
    # The literal fixture uses name index 1; ABC's text QName is index 2.
    code = code.replace(b"\x68\x01", b"\x68\x02")
    result += uint(len(code)) + code + uint(0) + uint(0)
    return result, (strings, ["", class_name, "text"], code)


def swf_fixture(abc, *, compressed=False):
    do_abc = struct.pack("<I", 0) + b"locale\0" + abc
    tag = struct.pack("<H", (82 << 6) | 63) + struct.pack("<I", len(do_abc)) + do_abc
    body = b"\x00" + b"\x00\x18\x01\x00" + tag + b"\x00\x00"
    header = (b"CWS" if compressed else b"FWS") + b"\x0a" + struct.pack("<I", len(body) + 8)
    return header + (zlib.compress(body) if compressed else body)


class LiteralConstructorTests(unittest.TestCase):
    def test_unresolved_and_malformed_localization_keys_are_not_display_labels(self):
        abc, _ = abc_fixture({"Items": {"0": {
            "cow_friendlyName": {"original": "Cow", "variations": {"singular": "Cow"}},
            "missing_friendlyName": {"original": "missing_friendlyName"},
            "broken_friendlyName": {"original": "Pet Runbroken_friendlyName,object=invalid"}}}})
        result = labels.recover(swf_fixture(abc))
        self.assertEqual(list(result["items"]), ["cow"])
        self.assertEqual({row["name"] for row in result["unresolvedLabels"]}, {"missing", "broken"})
        self.assertEqual(result["recoveryVersion"], 2)

    def test_nested_objects_and_multibyte_string_indices_preserve_exact_strings(self):
        original = {"text": {"Items": {"0": {"cow_friendlyName": {
            "original": "Pink Cow", "variations": {"singular": "Pink Dairy Cow", "plural": "Pink Dairy Cows"}},
            "cow_description": {"original": "A farmer’s friend.\nMilk & more!"}}}}}
        strings, names, code = literal_fixture(original, padding=140)
        self.assertIn(b"\x2c\x8d\x01", code)  # first real string sits beyond a one-byte index
        self.assertEqual(labels.literal_properties(strings, names, code), original)

    def test_empty_objects_do_not_consume_the_owner_from_the_stack(self):
        fixture = literal_fixture({"text": {}})
        self.assertEqual(labels.literal_properties(*fixture), {"text": {}})

    def test_unknown_instructions_and_trailing_instructions_fail_closed(self):
        fixture = literal_fixture({"text": {}})
        for code in (b"\x24\x01\x47", fixture[2] + b"\x24\x01", b"\xd0\x30"):
            with self.subTest(code=code), self.assertRaises(ValueError):
                labels.literal_properties(fixture[0], fixture[1], code)

    def test_truncated_literals_invalid_indices_scope_and_owners_are_rejected(self):
        cases = (b"\x2c\x80", b"\x2c\x7f\x47", b"\x55\x01\x47", b"\x68\x7f\x47",
                 b"\x30\x47", b"\xd0\x47", b"\xd0\x49\x01\x47", b"\x68\x01\x47",
                 b"\x2c\x00\x2c\x00\x68\x01\x47")
        for code in cases:
            with self.subTest(code=code), self.assertRaises(ValueError):
                labels.literal_properties([""], ["", "text"], code)

    def test_reader_rejects_truncation_and_out_of_range_abc_integers(self):
        self.assertEqual(labels.Reader(b"\xff\xff\xff\xff\x0f").uint(), 0xffffffff)
        for value in (b"\x80", b"\xff\xff\xff\xff\x10", b"\xff\xff\xff\xff\xff\x00"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                labels.Reader(value).uint()


class LabelRecoveryTests(unittest.TestCase):
    def table(self):
        return {"Items": {"0": {"cow_friendlyName": {"original": "Cow", "variations": {"singular": "Dairy Cow"}}},
                          "1": {"cow_description": {"original": "A farmer’s friend.\nMilk & more!"},
                                "pinktree_friendlyName": {"original": "Pink Cherry Tree"}}, "length": "2"}}

    def test_minimal_abc_extracts_the_named_constructor_without_evaluating_it(self):
        abc, expected = abc_fixture(self.table())
        self.assertEqual(labels.locale_constructor(abc), expected)
        self.assertIsNone(labels.locale_constructor(abc_fixture(self.table(), class_name="OtherClass")[0]))

    def test_fws_and_cws_wrappers_recover_every_bucket_and_exact_names_descriptions(self):
        abc, _ = abc_fixture(self.table())
        for compressed in (False, True):
            with self.subTest(compressed=compressed):
                payload = swf_fixture(abc, compressed=compressed)
                self.assertEqual(list(labels.abc_blocks(payload)), [abc])
                result = labels.recover(payload)
                self.assertEqual(result["items"], {
                    "cow": {"displayName": "Dairy Cow", "labelSource": "localization",
                            "localizationKey": "Items.cow_friendlyName", "description": "A farmer’s friend.\nMilk & more!"},
                    "pinktree": {"displayName": "Pink Cherry Tree", "labelSource": "localization",
                                 "localizationKey": "Items.pinktree_friendlyName"}})
                self.assertEqual(result["source"]["sha256"], hashlib.sha256(payload).hexdigest())

    def test_flat_items_table_is_also_supported_and_identical_duplicates_are_safe(self):
        entry = {"original": "Cherry Tree"}
        self.assertEqual(labels.item_entries({"Items": {"cherry_friendlyName": entry}}), {"cherry_friendlyName": entry})
        self.assertEqual(labels.item_entries({"Items": {"0": {"cherry_friendlyName": entry},
                                                       "1": {"cherry_friendlyName": dict(entry)}}}), {"cherry_friendlyName": entry})

    def test_conflicting_buckets_malformed_tables_and_empty_labels_are_rejected(self):
        malformed = ("bad text", {"Items": "bad table"}, {"Items": {1: {}}}, {"Items": {"unexpected": {}}},
                     {"Items": {"0": {"cow_friendlyName": {"original": "Cow"}},
                                "1": {"cow_friendlyName": {"original": "Wrong Cow"}}}})
        for table in malformed:
            with self.subTest(table=table), self.assertRaises(ValueError):
                labels.item_entries(table)
        with self.assertRaisesRegex(ValueError, "no recoverable"):
            labels.recover(swf_fixture(abc_fixture({"Items": {"0": {"cow_friendlyName": {"original": " "}}}})[0]))

    def test_corrupt_swf_length_compression_and_missing_class_are_rejected(self):
        payload = swf_fixture(abc_fixture(self.table())[0])
        for malformed in (b"FWS", b"CWS\x0a\x00\x00\x00\x00invalid", payload[:-1],
                          swf_fixture(abc_fixture(self.table(), class_name="OtherClass")[0])):
            with self.subTest(payload=malformed[:12]), self.assertRaises(ValueError):
                labels.recover(malformed)


if __name__ == "__main__":
    unittest.main()
