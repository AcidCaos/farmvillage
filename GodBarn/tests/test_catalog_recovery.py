"""Full-catalog recovery uses exact archive identities and readable evidence."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("catalog_recovery", ROOT / "scripts/recover_catalog.py")
recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery)


def png(color):
    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\0" + bytes(color))) + chunk(b"IEND", b""))


class CatalogRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "original"
        self.root = Path(self.temp.name) / "barn"
        self.source.mkdir()
        self.root.mkdir()
        self.manifest = {}

    def asset(self, logical, payload, archive_hash=None):
        group, relative = logical.removeprefix("assets/").split("/", 1)
        relative = Path(relative)
        digest = archive_hash or hashlib.md5(payload).hexdigest()
        self.manifest.setdefault(group, {})[relative.as_posix()] = digest
        path = self.source / "LocalData/assets" / group / relative.parent / (digest + relative.suffix)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    def recover(self, rows, records, **kwargs):
        return recovery.recover(rows, records, self.manifest, self.source, self.root, **kwargs)

    def test_uncapped_pass_uses_every_exact_icon_and_preserves_archive_fields(self):
        payload = png((255, 30, 40, 255))
        path = self.asset("assets/animals/cow.png", payload)
        records = [{"name": "cow", "code": "CW", "type": "animal", "image": [
            {"name": "feed", "url": "assets/animals/cow-feed.png"},
            {"name": "icon", "url": "assets/animals/cow.png"}]}]
        history = {"price": {"amount": 300, "currency": "coins"}, "collections": ["old"]}
        rows = [{"name": "cow", "code": "CW", "type": "animal", "archive": history,
                 "hasOriginalThumbnail": False, "image": "/static/assets/ui/cow.png"}]
        before = copy.deepcopy((rows, records))
        result, audit, assets = self.recover(rows, records, write_assets=True)
        item = result[0]
        self.assertEqual(item["archive"], history)
        self.assertEqual(item["code"], "CW")
        self.assertEqual(item["artwork"]["role"], "icon")
        self.assertEqual(item["artwork"]["logical"], "assets/animals/cow.png")
        self.assertEqual(item["artwork"]["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual((self.root / item["image"].lstrip("/")).read_bytes(), payload)
        self.assertEqual(path.read_bytes(), payload)
        self.assertEqual((rows, records), before)
        self.assertEqual(audit["exactUniqueItems"], 1)
        self.assertEqual(audit["byType"]["animal"]["exact"], 1)
        self.assertEqual(assets[0]["originalPath"], str(path.resolve()))

    def test_missing_icon_can_use_declared_feed_but_never_similar_filename(self):
        self.asset("assets/trees/redtree-feed.png", png((20, 60, 80, 255)))
        self.asset("assets/trees/redtree-variant.png", png((100, 80, 60, 255)))
        records = [{"name": "red", "code": "R", "type": "tree", "image": [
            {"name": "icon", "url": "assets/trees/redtree.png"},
            {"name": "feed", "url": "assets/trees/redtree-feed.png"}]},
            {"name": "blue", "code": "B", "type": "tree", "image":
             {"name": "icon", "url": "assets/trees/bluetree.png"}}]
        result, audit, _ = self.recover([dict(item) for item in records], records)
        self.assertEqual(result[0]["artwork"]["role"], "feed")
        self.assertEqual(result[0]["artwork"]["candidates"][0]["reason"], "not-in-manifest")
        self.assertEqual(result[1]["image"], recovery.MISSING_IMAGE)
        self.assertFalse(result[1]["hasOriginalThumbnail"])
        self.assertEqual(audit["missingUniqueItems"], 1)
        self.assertEqual(audit["unresolved"][0]["name"], "blue")

    def test_source_first_record_wins_and_both_duplicate_catalog_rows_survive(self):
        self.asset("assets/items/first.png", png((10, 20, 30, 255)))
        self.asset("assets/items/second.png", png((30, 20, 10, 255)))
        records = [{"name": "duplicate", "code": code, "type": "decoration",
                    "image": {"name": "icon", "url": "assets/items/" + stem + ".png"}}
                   for code, stem in (("A", "first"), ("B", "second"))]
        rows = [{"name": "duplicate", "code": "A", "archive": {"record": 0}},
                {"name": "duplicate", "code": "B", "archive": {"record": 1}}]
        result, audit, _ = self.recover(rows, records)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[1]["code"], "B")
        self.assertEqual(result[1]["archive"], {"record": 1})
        self.assertEqual(result[0]["image"], result[1]["image"])
        self.assertTrue(result[1]["artwork"]["duplicateLookup"])
        self.assertEqual(audit["duplicateSourceRecords"][0]["lookupRecordIndex"], 0)
        self.assertEqual((audit["catalogRecords"], audit["catalogUniqueItems"]), (2, 1))

    def test_corrupted_local_file_is_unresolved_with_reason(self):
        payload = bytearray(png((255, 255, 255, 255)))
        payload[20] ^= 1
        self.asset("assets/items/broken.png", payload)
        records = [{"name": "broken", "code": "B", "image":
                    {"name": "icon", "url": "assets/items/broken.png"}}]
        result, audit, assets = self.recover(records, records, write_assets=True)
        self.assertEqual(result[0]["artwork"]["status"], "missing")
        self.assertIn("checksum", audit["unresolved"][0]["candidates"][0]["reason"])
        self.assertEqual(assets, [])
        self.assertFalse((self.root / "static").exists())

    def test_no_raster_and_missing_file_are_explicit_and_audit_only_writes_nothing(self):
        path = self.asset("assets/items/missing.png", png((40, 50, 60, 255)))
        path.unlink()
        records = [{"name": "vector", "image": {"name": "static", "url": "assets/items/vector.swf"}},
                   {"name": "missing", "image": {"name": "icon", "url": "assets/items/missing.png"}}]
        _, audit, _ = self.recover(records, records)
        self.assertEqual(audit["unresolved"][0]["reason"], "no-declared-raster")
        self.assertEqual(audit["unresolved"][1]["candidates"][0]["reason"], "local-file-missing")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_version_manifest_recovers_exact_declared_urls_absent_from_master(self):
        payload = png((24, 50, 80, 255))
        self.asset("assets/items/newer.png", payload)
        version = copy.deepcopy(self.manifest)
        records = [{"name": "newer", "code": "N", "type": "decoration", "image":
                    {"name": "icon", "url": "assets/items/newer.png"}}]
        result, audit, _ = recovery.recover(records, records,
            [("version.amf", version), ("master.amf", {})], self.source, self.root)
        self.assertTrue(result[0]["hasOriginalThumbnail"])
        self.assertEqual(result[0]["artwork"]["manifest"], "version.amf")
        self.assertEqual(audit["artworkManifests"], {"version.amf": 1})

    def test_original_delta_precedence_and_missing_selected_file_never_substitute_master(self):
        logical = "assets/items/revised.png"
        old = self.asset(logical, png((255, 0, 0, 255)))
        master = copy.deepcopy(self.manifest)
        current = self.asset(logical, png((0, 255, 0, 255)))
        delta = copy.deepcopy(self.manifest)
        record = {"name": "revised", "code": "R", "image": {"name": "icon", "url": logical}}
        manifests = [("delta.amf", delta), ("master.amf", master)]
        result, audit, _ = recovery.recover([record], [record], manifests, self.source, self.root)
        self.assertEqual(result[0]["artwork"]["sourceFileHash"], current.stem)
        self.assertEqual(result[0]["artwork"]["manifest"], "delta.amf")
        self.assertEqual(recovery.manifest_overlap(manifests)["conflictingLogicalPaths"], 1)
        current.unlink()
        result, audit, _ = recovery.recover([record], [record], manifests, self.source, self.root)
        self.assertFalse(result[0]["hasOriginalThumbnail"])
        self.assertEqual(audit["unresolved"][0]["candidates"][0]["reason"], "local-file-missing")
        self.assertTrue(old.is_file())

    def test_missing_localization_is_explicit_and_never_an_invented_display_label(self):
        record = {"name": "10thuntranslatedinternalid", "code": "X"}
        row = dict(record, displayName="10Thuntranslatedinternalid", localizationKey="old")
        result, audit, _ = self.recover([row], [record], names={"source": {"sha256": "digest"}, "items": {}})
        self.assertEqual(result[0]["displayName"], "10thuntranslatedinternalid")
        self.assertEqual(result[0]["labelSource"], "internal-name")
        self.assertNotIn("localizationKey", result[0])
        self.assertEqual(audit["localizationSource"], {"sha256": "digest"})

    def test_shared_source_icon_copies_once_and_localized_names_keep_internal_identity(self):
        self.asset("assets/items/shared.png", png((0, 0, 0, 255)))
        records = [{"name": name, "code": name.upper(), "image":
                    {"name": "icon", "url": "assets/items/shared.png"}} for name in ("one", "two")]
        labels = {"items": {"one": {"displayName": "First keepsake", "description": "Original words",
                                     "labelSource": {"file": "en_US.swf", "key": "one"}, "code": "BAD"}}}
        result, audit, assets = self.recover(records, records, names=labels, write_assets=True)
        self.assertEqual(result[0]["name"], "one")
        self.assertEqual(result[0]["code"], "ONE")
        self.assertEqual(result[0]["displayName"], "First keepsake")
        self.assertEqual(result[0]["description"], "Original words")
        self.assertEqual(result[0]["labelSource"]["key"], "one")
        self.assertEqual(audit["appliedNameRecords"], 1)
        self.assertEqual(audit["uniqueArtworkFiles"], 1)
        self.assertEqual(len(assets), 1)
        self.assertEqual(len(list((self.root / "static/assets/items").iterdir())), 1)

    def test_manifest_paths_and_output_symlinks_cannot_escape(self):
        for logical in ("assets/items/../../outside.png", "/assets/items/icon.png", "assets/items\\icon.png", "https://example.com/icon.png"):
            self.assertEqual(recovery.resolve_asset(self.source, self.manifest, logical)[1], "invalid-logical-path")
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (self.root / "data").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            recovery.atomic_json(self.root, "data/catalog.json", {})
        self.assertFalse((outside / "catalog.json").exists())

    def test_output_cannot_be_inside_original_archive(self):
        with self.assertRaises(ValueError):
            recovery.recover([], [], {}, self.source, self.source / "output")

    def test_png_requires_complete_valid_chunks_and_real_dimensions(self):
        payload = png((1, 2, 3, 255))
        self.assertEqual(recovery.raster_info(payload), {"format": "png", "width": 1, "height": 1})
        for broken in (b"not an image", payload[:-1], payload[:32], payload.replace(b"IEND", b"IENO")):
            with self.assertRaises(ValueError):
                recovery.raster_info(broken)


if __name__ == "__main__":
    unittest.main()
