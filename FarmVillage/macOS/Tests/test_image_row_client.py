"""Image metadata keeps every archived row while avoiding quadratic Opt wrappers."""
import hashlib
import struct
import unittest
import zlib

import pyamf
from test_turbo_client_refusal import PATCH, ROOT, ABC, read_abcs


class Source:
    def __init__(self, raw, stats):
        if raw is None:
            raise ValueError("Original Opt constructor rejects null")
        self.raw, self.stats = raw, stats
        stats["wrappers"] += 1

    def array(self, name):
        self.stats["arrays"] += 1
        rows = self.raw.get(name)
        if rows is None:
            rows = []
        elif not isinstance(rows, list):
            rows = [rows]
        return [row if isinstance(row, OptSource) else type(self)(row, self.stats) for row in rows]


class OptSource(Source):
    def attributes(self):
        self.stats["rawReads"] += 1
        return self.raw


class XMLSource(Source):
    def attributes(self):
        raise AssertionError("XML data must keep original getArray fallback")


class ImageRowClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = (ROOT / "embeds/Flash/v855097-855094/FarmGame.swf").read_bytes()
        cls.previous = zlib.decompress(cls.original[8:])
        for edits in (PATCH.EDITS, PATCH.MARKET_EDITS, PATCH.TAB_EDITS, PATCH.SCRATCH_EDITS,
                      PATCH.EMPTY_WORLD_EDITS, PATCH.COTTAGE_EDITS, PATCH.COTTAGE_UPGRADE_EDITS,
                      PATCH.TURBO_EDITS, PATCH.STORAGE_EDITS, PATCH.INVITATION_EDITS,
                      PATCH.VIP_EDITS, PATCH.MARKET_WALKTHROUGH_EDITS, PATCH.QUEST_CLOSE_EDITS):
            cls.previous = PATCH._apply_edits(cls.previous, edits)
        cls.prepared = PATCH.patch_client_bytes(cls.original)
        cls.body = PATCH._apply_edits(cls.previous, PATCH.IMAGE_ROW_EDITS)
        cls.final_body = zlib.decompress(cls.prepared[8:])
        cls.before, cls.after = read_abcs(cls.previous), read_abcs(cls.body)
        cls.abc = cls.after[0]
        original_catalog = (ROOT / "xml/gz/v855038/items_opt.amf").read_bytes()
        assert hashlib.sha256(original_catalog).hexdigest() == "14987fd4c07f9de35ff5092aeab58584802fd7fbeca1131ad1a5e3eee381a4d7"
        document = pyamf.get_decoder(pyamf.AMF3, zlib.decompress(original_catalog)).readElement()
        cls.images = next(item["image"] for item in document["settings"]["items"]["item"]
                          if item.get("name") == "marketstall")
        assert len(cls.images) == 3383

    @staticmethod
    def stats():
        return {"wrappers": 0, "arrays": 0, "rawReads": 0}

    def select(self, code, source, index, *, experiment=True, prefix=""):
        """Execute the actual method entry and selection through unchanged byte176."""
        instance = {"m_dataSource": source}
        locals_ = {0: instance, 1: "unused.swf", 2: index, 3: prefix, 4: "", 5: None}
        globals_ = {"Classes.DataSources:OptItemDataSource": OptSource,
                    "Managers:FarmGameSettingsManager": "settings"}
        stack, position, peak = [], 0, 0
        def u30():
            nonlocal position
            value = shift = 0
            while True:
                byte = code[position]; position += 1
                value |= (byte & 127) << shift
                if byte < 128:
                    return value
                shift += 7
        def truth(value):
            return True if isinstance(value, (list, dict, Source)) else bool(value)
        for _ in range(150):
            if position in (176, 515):
                self.assertEqual(stack, [])
                self.assertLessEqual(peak, 5)
                return locals_.get(8), locals_[3], position
            opcode = code[position]; position += 1
            if opcode in (0x02, 0x09):
                pass
            elif opcode in (0xf0, 0xf1):
                u30()
            elif opcode == 0xef:
                position += 1; u30(); position += 1; u30()
            elif opcode in (0xd0, 0xd1, 0xd2, 0xd3):
                stack.append(locals_[opcode - 0xd0])
            elif opcode == 0xd7:
                locals_[3] = stack.pop()
            elif opcode == 0x62:
                stack.append(locals_[u30()])
            elif opcode == 0x63:
                locals_[u30()] = stack.pop()
            elif opcode == 0x30:
                self.assertIs(stack.pop(), instance)
            elif opcode == 0x20:
                stack.append(None)
            elif opcode == 0x2c:
                stack.append(self.abc.strings[u30()])
            elif opcode == 0x55:
                self.assertEqual(u30(), 0); stack.append({})
            elif opcode == 0x80:
                name = self.abc.mname(u30())
                if name == "DataSources:BaseDataSource":
                    self.assertTrue(stack[-1] is None or isinstance(stack[-1], Source))
            elif opcode == 0x85:
                if stack[-1] is not None:
                    stack[-1] = str(stack[-1])
            elif opcode == 0x86:
                self.assertEqual(self.abc.mname(u30()), "Array")
                stack[-1] = stack[-1] if isinstance(stack[-1], list) else None
            elif opcode in (0x60, 0x5d):
                stack.append(globals_[self.abc.mname(u30())])
            elif opcode == 0x66:
                name = self.abc.short(u30())
                if name == "[late]":
                    key = stack.pop(); receiver = stack.pop()
                    stack.append(receiver[key] if 0 <= key < len(receiver) else None)
                else:
                    receiver = stack.pop(); stack.append(receiver.get(name))
            elif opcode == 0x2a:
                stack.append(stack[-1])
            elif opcode == 0xb3:
                kind = stack.pop(); stack.append(isinstance(stack.pop(), kind))
            elif opcode == 0xa0:
                right = stack.pop(); stack.append(stack.pop() + right)
            elif opcode in (0x10, 0x11, 0x12, 0x13):
                delta = int.from_bytes(code[position:position + 3], "little", signed=True); position += 3
                if opcode == 0x10:
                    take = True
                elif opcode == 0x13:
                    take = stack.pop() == stack.pop()
                else:
                    value = truth(stack.pop()); take = value if opcode == 0x11 else not value
                if take:
                    position += delta
            elif opcode in (0x46, 0x4a):
                name, count = self.abc.mname(u30()), u30()
                args = [stack.pop() for _ in range(count)][::-1]; receiver = stack.pop()
                if opcode == 0x4a:
                    self.assertIs(receiver, OptSource)
                    self.assertEqual(len(args), 1)
                    result = OptSource(args[0], source.stats)
                elif name == "isInDataSourceExperiment":
                    self.assertEqual((receiver, args), ("settings", [])); result = experiment
                elif name == "getArray":
                    self.assertEqual(args, ["image"]); result = receiver.array("image")
                elif name == "getAttributesHash":
                    self.assertEqual(args, []); result = receiver.attributes()
                else:
                    self.fail("Unexpected image selector call: " + name)
                stack.append(result)
            else:
                self.fail(f"Unexpected image opcode {opcode:#x} at {position - 1}")
            peak = max(peak, len(stack))
        self.fail("Image selector did not reach the original continuation")

    def test_complete_stage_changes_only_one_method_without_headers_pools_catalog_or_metadata(self):
        self.assertEqual(hashlib.sha256(self.previous).hexdigest(), PATCH.QUEST_CLOSE_BODY_SHA256)
        self.assertEqual(hashlib.sha256(self.body).hexdigest(), PATCH.IMAGE_ROW_BODY_SHA256)
        self.assertEqual(self.body, PATCH._apply_edits(self.previous, PATCH.IMAGE_ROW_EDITS))
        self.assertEqual(self.final_body, PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(self.body, PATCH.INVENTORY_ART_EDITS), PATCH.MARKETSTALL_EXPANSION_EDITS), PATCH.WIDGET_STORAGE_EDITS), PATCH.REGIONAL_UPGRADE_EDITS), PATCH.OPTIONAL_BACKGROUND_EDITS), PATCH.COVE_UPGRADE_EDITS))
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
                    changes.append((index, ident)); self.assertEqual(len(code), len(after.bodies[ident]))
        self.assertEqual((total, changes), (68492, [(0, 6230)]))
        for _, start, size, old_sha, new_sha in PATCH.IMAGE_ROW_METHODS:
            self.assertEqual(hashlib.sha256(self.previous[start:start + size]).hexdigest(), old_sha)
            self.assertEqual(hashlib.sha256(self.body[start:start + size]).hexdigest(), new_sha)
            self.assertEqual(self.body[start - 8:start].hex(), "d630050b04059609")
        before, after = self.before[0].bodies[6230], self.abc.bodies[6230]
        self.assertEqual(before[:29], after[:29])
        self.assertEqual(before[78:118], after[78:118])
        self.assertEqual(before[176:], after[176:])
        self.assertEqual(self.before[0].bodies[6232], self.abc.bodies[6232])
        self.assertEqual((ROOT / "embeds/Flash/v855097-855094/FarmGame.swf").read_bytes(), self.original)

    def branch_errors(self, code):
        reader = ABC.R(code)
        starts, targets = set(), []
        while reader.p < len(code):
            at = reader.p
            starts.add(at)
            opcode = reader.u8()
            self.assertIn(opcode, ABC.OPS, f"unknown opcode at {at}")
            _, kinds = ABC.OPS[opcode]
            if kinds == "X":
                targets.append((at, at + reader.s24()))
                count = reader.u30()
                targets.extend((at, at + reader.s24()) for _ in range(count + 1))
            else:
                for kind in kinds:
                    if kind == "o":
                        delta = reader.s24()
                        targets.append((at, reader.p + delta))
                    elif kind == "b":
                        reader.u8()
                    else:
                        reader.u30()
        self.assertEqual(reader.p, len(code))
        invalid = [(at, target) for at, target in targets if target not in starts]
        # The pinned verifier additionally requires a Label for a backward jump
        # into a target not seen before. Requiring it on every backward target
        # is stronger and covers these methods without traversal-order guesses.
        missing_labels = [(at, target) for at, target in targets
                          if target < at and target in starts and code[target] != 0x09]
        return starts, invalid, missing_labels

    def test_all_branches_and_exception_boundaries_match_pinned_verifier(self):
        for ident, start, size, _, _ in (*PATCH.IMAGE_ROW_METHODS, *PATCH.QUEST_CLOSE_METHODS):
            code = self.abc.bodies[ident]
            starts, invalid, missing_labels = self.branch_errors(code)
            self.assertEqual(invalid, [], ident)
            self.assertEqual(missing_labels, [], ident)
            # Exception entries follow code immediately; validate every from/to/
            # handler boundary, allowing code.length only for exclusive end.
            reader = ABC.R(self.body, start + size)
            for _ in range(reader.u30()):
                first, end, target, type_name, var_name = [reader.u30() for _ in range(5)]
                self.assertIn(first, starts)
                self.assertIn(end, starts | {size})
                self.assertIn(target, starts)
                self.assertLessEqual(first, end)
        # The browser-rejected draft had aligned instructions, but no Labels at
        # its backward targets. Preserve that exact failing case as a regression.
        rejected = self.body
        for offset, old, new in reversed(PATCH.IMAGE_LABEL_EDITS):
            self.assertEqual(rejected[offset:offset + len(new)], new)
            rejected = rejected[:offset] + old + rejected[offset + len(new):]
        self.assertEqual(hashlib.sha256(rejected).hexdigest(), PATCH.UNLABELED_IMAGE_ROW_BODY_SHA256)
        start, size = PATCH.IMAGE_ROW_METHODS[0][1:3]
        _, invalid, missing_labels = self.branch_errors(rejected[start:start + size])
        self.assertEqual(invalid, [])
        self.assertEqual(missing_labels, [(126, 48), (146, 48), (168, 33)])
        staged = self.original[:4] + struct.pack("<I", len(rejected) + 8) + zlib.compress(rejected, 1)
        self.assertEqual(PATCH.patch_client_bytes(staged), self.prepared)

    def test_all_3383_actual_rows_keep_all_attributes_with_linear_wrapper_count(self):
        self.assertTrue(all(isinstance(row, dict) for row in self.images))
        stats = self.stats(); source = OptSource({"image": self.images}, stats)
        stats.update(wrappers=0, arrays=0, rawReads=0)
        old, _, _ = self.select(self.before[0].bodies[6230], source, 0)
        self.assertIs(old.raw, self.images[0])
        self.assertEqual(stats["wrappers"], 3383)
        self.assertEqual(stats["arrays"], 1)
        stats.update(wrappers=0, arrays=0, rawReads=0)
        original_rows = [dict(row) for row in self.images]
        for index, raw in enumerate(self.images):
            selected, prefix, at = self.select(self.abc.bodies[6230], source, index)
            self.assertIs(selected.raw, raw)
            self.assertEqual(selected.raw, original_rows[index])
            self.assertEqual((prefix, at), ("", 176))
        self.assertEqual(stats, {"wrappers": 3383, "arrays": 0, "rawReads": 3383})
        self.assertEqual(self.images, original_rows)
        self.assertEqual(3383 * 3383, 11444689)  # Old per-row conversions, before caller's3383.

    def test_existing_opt_row_is_reused_without_mutating_or_caching_source_arrays(self):
        stats = self.stats(); row = OptSource({"name": "wrapped", "unknown": [1, 2]}, stats)
        source = OptSource({"image": [row]}, stats); stats.update(wrappers=0, arrays=0, rawReads=0)
        selected, prefix, at = self.select(self.abc.bodies[6230], source, 0, prefix="snow")
        self.assertIs(selected, row)
        self.assertEqual((prefix, at), ("snow_", 176))
        self.assertEqual(stats, {"wrappers": 0, "arrays": 0, "rawReads": 1})
        replacement = {"name": "replaced", "unknown": {"keep": True}}
        source.raw["image"][0] = replacement
        selected, _, _ = self.select(self.abc.bodies[6230], source, 0)
        self.assertIs(selected.raw, replacement)  # No stale global/local cache.
        self.assertEqual(stats["wrappers"], 1)

    def test_xml_data_source_singleton_and_legacy_xml_branch_keep_original_fallback(self):
        for kind, value in ((OptSource, {"name": "one", "url": "one.swf"}),
                            (XMLSource, [{"name": "a"}, {"name": "b"}])):
            stats = self.stats(); source = kind({"image": value}, stats)
            old, old_prefix, old_at = self.select(self.before[0].bodies[6230], source, 0, prefix="farm")
            stats.update(wrappers=0, arrays=0, rawReads=0)
            new, prefix, at = self.select(self.abc.bodies[6230], source, 0, prefix="farm")
            self.assertEqual((new.raw, prefix, at), (old.raw, old_prefix, old_at))
            self.assertEqual(stats["arrays"], 1)
        stats = self.stats(); source = XMLSource({"image": []}, stats)
        _, prefix, at = self.select(self.abc.bodies[6230], source, 0, experiment=False, prefix="water")
        self.assertEqual((prefix, at), ("water_", 515))
        self.assertEqual(stats["arrays"], 0)

    def test_known_quest_stage_upgrades_idempotently_and_unknown_image_code_rejects(self):
        previous = self.original[:4] + struct.pack("<I", len(self.previous) + 8) + zlib.compress(self.previous, 1)
        self.assertEqual(PATCH.patch_client_bytes(previous), self.prepared)
        self.assertEqual(PATCH.patch_client_bytes(self.prepared), self.prepared)
        changed = bytearray(self.previous); changed[PATCH.IMAGE_ROW_METHODS[0][1] + 118] ^= 1
        with self.assertRaisesRegex(ValueError, "refusing to modify unknown game code"):
            PATCH.patch_client_bytes(previous[:8] + zlib.compress(changed, 1))


if __name__ == "__main__":
    unittest.main()
