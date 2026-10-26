"""Full-archive discovery is consistent, honest about artwork, and read-only."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from catalog_tools import catalog_coverage, discover_catalog, exact_artwork


class CatalogDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.catalog = [
            {"name": "pinkcow", "displayName": "Pink Dairy Cow", "code": "C7", "type": "animal",
             "subtype": "cow", "className": "Animal", "image": "/static/assets/items/pink.png",
             "artwork": {"status": "exact", "logical": "assets/animals/pink_cow_icon.png"},
             "hasOriginalThumbnail": True, "grantable": True, "labelSource": "localization"},
            {"name": "archivedcow", "displayName": "Archive Cow", "code": "A1", "type": "animal",
             "subtype": "cow", "image": "/static/assets/ui/missing-art.svg",
             "artwork": {"status": "missing"}, "hasOriginalThumbnail": False, "grantable": True},
            {"name": "partyhat", "displayName": "Party Hat", "code": "H8", "type": "consumable",
             "subtype": "clothes", "className": "AvatarClothing", "grantable": False,
             "image": "/static/assets/items/hat.png", "hasOriginalThumbnail": True},
            {"name": "pinktree", "displayName": "Pink Cherry Tree", "code": "T9", "type": "tree",
             "subtype": "cherry", "grantable": True, "image": None, "hasOriginalThumbnail": True},
        ]

    def query(self, **params):
        return discover_catalog(self.catalog, {"calendarDate": "2026-10-21", **params})

    def test_search_matches_all_words_across_identity_and_archive_fields(self):
        for query in ("pink cow", "cow pink", "C7", "Animal c7", "pink animals icon", "AvatarClothing", "clothes H8"):
            with self.subTest(query=query):
                result = self.query(q=query)
                self.assertEqual(result["total"], 1)
        self.assertEqual(self.query(q="pink hat")["total"], 0)
        self.assertEqual(self.query(q="pink_cow_icon")["items"][0]["name"], "pinkcow")

    def test_full_category_and_subtype_facets_do_not_hide_ungrantable_records(self):
        result = self.query(type="animal", subtype="cow")
        self.assertEqual(result["types"], [{"type": "animal", "count": 2},
                                           {"type": "consumable", "count": 1}, {"type": "tree", "count": 1}])
        self.assertEqual(result["subtypes"], [{"subtype": "cow", "count": 2}])
        self.assertEqual(self.query(type="consumable")["items"][0]["name"], "partyhat")
        self.assertEqual(self.query(grantable="1")["total"], 3)

    def test_subtype_facet_counts_include_other_subtypes_in_the_selected_type(self):
        self.catalog.append({"name": "horse", "type": "animal", "subtype": "horse"})
        result = self.query(type="animal", subtype="cow")
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["subtypes"], [{"subtype": "cow", "count": 2}, {"subtype": "horse", "count": 1}])

    def test_global_and_result_coverage_are_distinct_and_missing_art_is_not_exact(self):
        result = self.query(type="animal", artwork="missing")
        self.assertEqual(result["coverage"], {"total": 4, "exactArt": 2, "missingArt": 2,
                                              "localizedNames": 1, "internalNames": 3})
        self.assertEqual(result["resultCoverage"], {"total": 1, "exactArt": 0, "missingArt": 1,
                                                    "localizedNames": 0, "internalNames": 1})
        self.assertEqual(result["items"][0]["name"], "archivedcow")
        self.assertEqual(self.query(artwork="exact")["total"], 2)
        self.assertFalse(exact_artwork({"artwork": {"status": "missing"}, "hasOriginalThumbnail": True, "image": "cow.png"}))

    def test_sorting_is_deterministic_and_applies_before_pagination(self):
        self.assertEqual([row["name"] for row in self.query(sort="name", limit="2")["items"]], ["archivedcow", "partyhat"])
        self.assertEqual([row["name"] for row in self.query(sort="name-desc", limit="2")["items"]], ["pinkcow", "pinktree"])
        self.assertEqual([row["code"] for row in self.query(sort="code")["items"]], ["A1", "C7", "H8", "T9"])
        self.assertEqual([row["name"] for row in self.query(sort="recommended")["items"]], [row["name"] for row in self.catalog])
        self.assertEqual(self.query(sort="type")["items"][0]["name"], "archivedcow")

    def test_filters_compose_with_favorites_collections_and_history(self):
        self.catalog[0]["archive"] = {"collections": ["winter"], "availability": {"start": "2010-12-01", "end": "2010-12-25"},
                                       "acquisition": "Market"}
        result = self.query(names="pinkcow,partyhat", collection="winter", year="2010", acquisition="Market",
                            q="pink", artwork="exact", grantable="yes", type="animal")
        self.assertEqual(result["total"], 1)
        self.assertEqual(self.query(names="")["total"], 0)

    def test_queries_never_mutate_catalog_or_facts(self):
        before = copy.deepcopy(self.catalog)
        self.query(q="pink", sort="name-desc", artwork="exact")
        self.query(type="animal", subtype="cow")
        self.assertEqual(self.catalog, before)

    def test_validation_and_empty_pages(self):
        for params in ({"artwork": "guessed"}, {"sort": "random"}, {"page": "no"}, {"limit": None}, {"year": "20"}):
            with self.subTest(params=params), self.assertRaises(ValueError):
                self.query(**params)
        result = self.query(q="doesnotexist", page="999")
        self.assertEqual((result["total"], result["page"], result["pages"]), (0, 1, 1))
        self.assertEqual(catalog_coverage([])["total"], 0)

    def test_expansion_sizes_include_every_match_before_pagination(self):
        self.catalog.extend([{"name": "expand24", "type": "change_farm", "subtype": "expand_farm", "squares": 24},
                             {"name": "expand48", "type": "change_farm", "subtype": "expand_farm", "squares": 48},
                             {"name": "bad", "type": "change_farm", "subtype": "expand_farm", "squares": "nan"}])
        self.assertEqual(self.query(type="expand_farm", limit="1")["expansionSizes"], [24, 48])


if __name__ == "__main__":
    unittest.main()
