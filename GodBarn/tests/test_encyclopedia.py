"""Historical claims enrich copied rows without changing price or source data."""
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


encyclopedia = module("encyclopedia_test_helper", ROOT / "encyclopedia.py")
prepare = module("encyclopedia_test_prepare", ROOT / "scripts/prepare_encyclopedia.py")
bundler = module("encyclopedia_test_bundle", ROOT / "scripts/bundle_companion.py")


class EncyclopediaTests(unittest.TestCase):
    def fixture(self):
        catalog = [{"name": "crow", "code": "YO", "displayName": "Old label", "image": None,
                    "cost": 500, "cash": 7, "market": "cash", "mastery": "true",
                    "archive": {"price": {"amount": 7, "currency": "cash"},
                                "raw": {"limitedStart": "1/1/2013"},
                                "availability": {"start": "2013-01-01", "end": "2013-02-01"},
                                "acquisition": "Recorded market offer", "collections": ["winter"]}},
                   {"name": "goose", "code": "YQ", "nested": {"keep": [1]}}]
        metadata = {"schema": 1, "sources": [{"id": "wiki", "url": "https://example.org/history", "title": "Community history"}],
                    "items": {"crow": {"code": "YO", "displayName": "Sneaky Crow",
                                         "facts": {"mastery": "false", "harvestYield": "12", "cost": 0, "cash": 0},
                                         "sourceIds": ["wiki"], "relatedItems": ["goose", "missing", "crow", "goose"],
                                         "releaseHistory": [{"date": "2009-12-23", "acquisition": "Possible Mystery Box prize"}],
                                         "thumbnail": {"image": "/static/assets/items/abc.png", "sha256": "a" * 64}}},
                    "shelves": [{"id": "box8", "name": "Box 8", "sourceId": "wiki", "items": ["crow", "crow", "missing"]}]}
        return catalog, metadata

    def test_enrichment_is_detached_and_never_replaces_identity_price_or_existing_facts(self):
        catalog, metadata = self.fixture()
        original, notes = copy.deepcopy(catalog), copy.deepcopy(metadata)
        rows, shelves = encyclopedia.enrich_catalog(catalog, metadata)
        item = rows[0]
        self.assertEqual((item["name"], item["code"], item["cost"], item["cash"], item["market"]), ("crow", "YO", 500, 7, "cash"))
        self.assertEqual(item["mastery"], "true")
        self.assertEqual(item["harvestYield"], "12")
        self.assertEqual(item["encyclopedia"]["facts"]["mastery"], "false")
        self.assertEqual(item["displayName"], "Sneaky Crow")
        self.assertEqual(item["archive"]["collections"], ["winter", "box8"])
        self.assertEqual(item["encyclopedia"]["relatedItems"], ["goose"])
        self.assertEqual(shelves[0]["items"], ["crow"])
        rows[1]["nested"]["keep"].append(2)
        item["archive"]["raw"]["limitedStart"] = "changed"
        item["encyclopedia"]["facts"]["harvestYield"] = "changed"
        shelves[0]["sources"][0]["title"] = "changed"
        self.assertEqual(catalog, original)
        self.assertEqual(metadata, notes)

    def test_code_mismatch_cannot_attach_a_historical_prize_or_label(self):
        catalog, metadata = self.fixture()
        metadata["items"]["crow"]["code"] = "different"
        rows, shelves = encyclopedia.enrich_catalog(catalog, metadata)
        self.assertNotIn("encyclopedia", rows[0])
        self.assertEqual(rows[0]["displayName"], "Old label")
        self.assertEqual(rows[0]["archive"]["collections"], ["winter"])
        self.assertEqual(shelves[0]["items"], [])

    def test_recovered_localization_and_artwork_take_priority_over_editorial_overlay(self):
        catalog, metadata = self.fixture()
        catalog[0].update(displayName="Original Crow", labelSource="localization",
                          image="/static/assets/items/recovered.png", hasOriginalThumbnail=True,
                          artwork={"status": "exact", "logical": "assets/crow_icon.png", "sha256": "b" * 64})
        rows, _ = encyclopedia.enrich_catalog(catalog, metadata)
        self.assertEqual(rows[0]["displayName"], "Original Crow")
        self.assertEqual(rows[0]["labelSource"], "localization")
        self.assertEqual(rows[0]["image"], "/static/assets/items/recovered.png")
        self.assertEqual(rows[0]["artwork"], catalog[0]["artwork"])
        self.assertEqual(rows[0]["encyclopedia"]["displayName"], "Sneaky Crow")
        catalog[0].update(image="/static/assets/ui/missing-art.svg", hasOriginalThumbnail=False,
                          artwork={"status": "missing"})
        rows, _ = encyclopedia.enrich_catalog(catalog, metadata)
        self.assertFalse(rows[0]["hasOriginalThumbnail"])
        self.assertEqual(rows[0]["image"], "/static/assets/ui/missing-art.svg")

    def test_verified_original_thumbnail_applies_and_unsafe_links_do_not(self):
        catalog, metadata = self.fixture()
        rows, _ = encyclopedia.enrich_catalog(catalog, metadata)
        self.assertEqual(rows[0]["image"], "/static/assets/items/abc.png")
        self.assertTrue(rows[0]["hasOriginalThumbnail"])
        metadata["items"]["crow"]["thumbnail"]["image"] = "/static/assets/items/../private.png"
        metadata["sources"][0]["url"] = "javascript:alert(1)"
        rows, _ = encyclopedia.enrich_catalog(catalog, metadata)
        self.assertIsNone(rows[0]["image"])
        self.assertNotIn("url", rows[0]["encyclopedia"]["sources"][0])

    def test_recorded_sale_year_and_prize_history_remain_separate_filter_evidence(self):
        catalog, metadata = self.fixture()
        rows, _ = encyclopedia.enrich_catalog(catalog, metadata)
        filters = encyclopedia.history_filters(iter(rows))
        self.assertEqual(filters["years"], ["2009", "2013"])
        self.assertEqual(len(encyclopedia.filter_history(rows, year="2009", acquisition="Possible Mystery Box prize")), 1)
        self.assertEqual(len(encyclopedia.filter_history(rows, year="2013", acquisition="Recorded market offer")), 1)
        self.assertEqual(encyclopedia.filter_history(rows, year="2010"), [])
        self.assertEqual(rows[0]["archive"]["availability"]["start"], "2013-01-01")
        for value in ("09", "2009-12-23", 2009):
            with self.assertRaises(ValueError):
                encyclopedia.filter_history(rows, year=value)

    def test_loads_plain_or_compressed_metadata_and_rejects_malformed_shapes(self):
        _, metadata = self.fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(encyclopedia.load_metadata(root)["items"], {})
            (root / "encyclopedia.json.gz").write_bytes(gzip.compress(json.dumps(metadata).encode(), mtime=0))
            self.assertEqual(encyclopedia.load_metadata(root), metadata)
            for value in ({"schema": 1, "items": []}, {"schema": True},
                          {"schema": 1, "items": {"crow": {"facts": []}}},
                          {"schema": 1, "shelves": [{"id": "x"}, {"id": "x"}]}):
                (root / "encyclopedia.json").write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    encyclopedia.load_metadata(root)
            (root / "encyclopedia.json").write_text('{"schema":1,"items":{"crow":{"facts":{"x":NaN}}}}')
            with self.assertRaises(ValueError):
                encyclopedia.load_metadata(root)

    def curation(self):
        return {"schema": 1, "sources": [{"id": "wiki"}], "shelves": [
            {"id": "box", "name": "Historic box", "releaseDate": "2009-12-23", "sourceId": "wiki",
             "prizes": [{"label": "Crow", "name": "crow", "code": "YO"},
                        {"label": "Fuel", "name": None, "code": None},
                        {"label": "Wrong identity", "name": "goose", "code": "WRONG"}]}]}

    def test_overlay_uses_first_identity_and_keeps_unmatched_history_out_of_grants(self):
        records = [{"name": "crow", "code": "YO", "mastery": "true", "nextLevel": "YQ"},
                   {"name": "crow", "code": "other", "mastery": "false"}, {"name": "goose", "code": "YQ"}]
        original = copy.deepcopy(records)
        overlay = prepare.build_overlay(records, self.curation(), "a" * 64)
        self.assertEqual(overlay["items"]["crow"]["recordIndex"], 0)
        self.assertEqual(overlay["items"]["crow"]["facts"]["mastery"], "true")
        self.assertEqual(overlay["items"]["crow"]["relatedItems"], ["goose"])
        self.assertEqual(overlay["shelves"][0]["items"], ["crow"])
        self.assertEqual(len(overlay["shelves"][0]["unmatchedItems"]), 2)
        self.assertEqual(records, original)

    def test_bad_shelf_date_or_unattributed_source_cannot_generate_claims(self):
        for field, value in (("releaseDate", "2009-02-30"), ("sourceId", "unknown")):
            curation = self.curation()
            curation["shelves"][0][field] = value
            with self.assertRaises(ValueError):
                prepare.build_overlay([], curation, "a" * 64)

    def test_thumbnail_copy_preserves_original_bytes_and_records_resolution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, destination = root / "source", root / "barn"
            original = source / "LocalData/assets/Decorations/crow" / ("a" * 32 + ".png")
            original.parent.mkdir(parents=True)
            original.write_bytes(b"original thumbnail bytes")
            records = [{"name": "crow", "image": [{"name": "icon", "url": "assets/Decorations/crow/icon.png"}]}]
            overlay = {"shelves": [{"items": ["crow"]}], "items": {"crow": {}}}
            provenance = {"assets": [{"path": "static/keep.png", "sha256": "unchanged"}]}
            with mock.patch.object(prepare, "ROOT", destination):
                prepare.copy_thumbnails(source, {"Decorations": {"crow/icon.png": "a" * 32}}, records, overlay, provenance)
            note = overlay["items"]["crow"]["thumbnail"]
            self.assertEqual((destination / note["image"].lstrip("/")).read_bytes(), original.read_bytes())
            self.assertEqual(note["sha256"], hashlib.sha256(original.read_bytes()).hexdigest())
            self.assertEqual(len(provenance["assets"]), 2)
            self.assertEqual(provenance["assets"][0]["sha256"], "unchanged")

    def test_shipped_shelves_have_exact_archived_identities_and_honest_unmatched_reward(self):
        overlay = encyclopedia.load_metadata(ROOT / "data")
        self.assertEqual(len(overlay["shelves"]), 4)
        self.assertEqual(sum(len(shelf["items"]) for shelf in overlay["shelves"]), 25)
        unmatched = [item for shelf in overlay["shelves"] for item in shelf["unmatchedItems"]]
        self.assertEqual([item["label"] for item in unmatched], ["50 Fuel Refills"])
        self.assertEqual(overlay["items"]["scarecrowed"]["displayName"], "Sneaky Crow")
        for shelf in overlay["shelves"]:
            for name in shelf["items"]:
                note = overlay["items"][name]
                self.assertTrue(note["code"])
                self.assertIn("thumbnail", note)
                self.assertNotIn("probability", note)

    def test_bundle_carries_lazy_metadata_and_maps_original_prize_thumbnails(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory) / "first", Path(directory) / "second"
            bundler.bundle_companion(ROOT, first)
            bundler.bundle_companion(ROOT, second)
            self.assertEqual((first / "data/encyclopedia.json.gz").read_bytes(), (second / "data/encyclopedia.json.gz").read_bytes())
            self.assertEqual(encyclopedia.load_metadata(first / "data")["curationSha256"], encyclopedia.load_metadata(ROOT / "data")["curationSha256"])
            for name in ("encyclopedia.py", "progression_tools.py", "data/progression.json", "data/historical-prizes.json"):
                self.assertTrue((first / name).is_file(), name)
            mapping = json.loads((first / "data/asset-map.json").read_text())
            overlay = encyclopedia.load_metadata(first / "data")
            archive = ROOT.parent / "FarmVillage/LocalData/assets"
            for shelf in overlay["shelves"]:
                for name in shelf["items"]:
                    thumbnail = overlay["items"][name]["thumbnail"]
                    key = thumbnail["image"].lstrip("/")
                    self.assertIn(key, mapping, name)
                    original = archive / mapping[key]
                    self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), thumbnail["sha256"], name)
            self.assertFalse((first / "workspace").exists())


if __name__ == "__main__":
    unittest.main()
