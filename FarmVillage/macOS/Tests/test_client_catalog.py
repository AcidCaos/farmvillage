"""Derived client catalog keeps every definition and the source immutable."""

import copy
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zlib

import pyamf


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence  # noqa: F401  Loads first so FARMVILLAGE_DATA_DIR is set before product modules resolve paths.
import client_catalog
import heritage_pricing


def encode(document):
    return zlib.compress(pyamf.encode(document, encoding=pyamf.AMF3).getvalue())


def decode(raw):
    return pyamf.get_decoder(pyamf.AMF3, zlib.decompress(raw)).readElement()


def heritage_expected(record, patch):
    """The Home overlay's own mutation, then the client's conflicting-level purchase closure."""
    expected = copy.deepcopy(record)
    heritage_pricing._mutate(expected, patch)
    if client_catalog._unresolved_level(expected):
        expected["buyable"] = "false" if isinstance(expected.get("buyable"), str) else False
    return expected


class ClientCatalogTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="farmvillage-client-catalog-")
        self.addCleanup(self.directory.cleanup)
        self.source = Path(self.directory.name) / "items.amf"
        self.now = datetime(2026, 10, 21, 12, tzinfo=timezone.utc).timestamp()

    def test_only_conclusively_expired_buyable_flag_changes(self):
        records = [
            {"name": "expired", "code": "old", "buyable": "true", "limitedEnd": "10/19/2026", "cash": "7", "cost": "12500", "unknown": {"retain": [1, 2]}},
            {"name": "boolean", "code": "bool", "buyable": True, "limitedEnd": "12/26/2010"},
            {"name": "today", "code": "today", "buyable": "true", "limitedEnd": "10/21/2026"},
            {"name": "yesterday", "code": "yesterday", "buyable": "true", "limitedEnd": "10/20/2026"},
            {"name": "future", "code": "future", "buyable": "true", "limitedEnd": "12/26/2027"},
            {"name": "invalid", "code": "invalid", "buyable": "true", "limitedEnd": "02/30/2010"},
            {"name": "sentinel", "code": "sentinel", "buyable": "true", "limitedEnd": "01/01/1970"},
            {"name": "missing", "code": "missing", "buyable": "true"},
            {"name": "nondate", "code": "nondate", "buyable": "true", "limitedEnd": ["12/26/2010"]},
            {"name": "gift_only", "code": "gift", "buyable": "false", "limitedEnd": "12/26/2010"},
        ]
        document = {"settings": {"items": {"item": records}}, "unknownTopLevel": {"source": "preserved"}}
        original = encode(document)
        self.source.write_bytes(original)
        result = decode(client_catalog.payload(self.source, now=self.now))
        self.assertEqual(len(result["settings"]["items"]["item"]), len(records))
        expected = decode(original)
        expected["settings"]["items"]["item"][0]["buyable"] = "false"
        expected["settings"]["items"]["item"][1]["buyable"] = False
        self.assertEqual(result, expected)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(list(Path(self.directory.name).iterdir()), [self.source])

    def test_source_and_current_day_invalidate_memory_cache(self):
        def document(name):
            return {"settings": {"items": {"item": [{"name": name, "code": "X", "buyable": "true", "limitedEnd": "10/20/2026"}]}}}
        self.source.write_bytes(encode(document("original")))
        first = client_catalog.payload(self.source, now=self.now)
        self.assertIs(client_catalog.payload(self.source, now=self.now), first)
        tomorrow = client_catalog.payload(self.source, now=self.now + 86400)
        self.assertEqual(decode(tomorrow)["settings"]["items"]["item"][0]["buyable"], "false")
        self.source.write_bytes(encode(document("updated")))
        updated = decode(client_catalog.payload(self.source, now=self.now))
        self.assertEqual(updated["settings"]["items"]["item"][0]["name"], "updated")

    def test_actual_archive_retains_every_record_and_every_other_field(self):
        source = ROOT / "xml/gz/v855038/items_opt.amf"
        original = source.read_bytes()
        before = decode(original)
        after = decode(client_catalog.payload(source, now=self.now))
        before_rows = before["settings"]["items"]["item"]
        after_rows = after["settings"]["items"]["item"]
        self.assertEqual(len(after_rows), len(before_rows) + 167)
        self.assertGreater(len(after_rows), 100000)
        heritage_patches, _ = heritage_pricing.plan(before_rows)
        changed = 0
        restored = 0
        paid_projection = client_catalog._paid_projection_policy()[0]
        for index, (expected, actual) in enumerate(zip(before_rows, after_rows)):
            expected = paid_projection(expected)
            expected = client_catalog.themed_market_presentation.item_projection(expected)
            if index in heritage_patches:
                self.assertEqual(actual, heritage_expected(expected, heritage_patches[index]))
                continue
            if expected != actual:
                replacement = dict(expected)
                if client_catalog._restored_puppy(expected):
                    import pets
                    pets._supported(expected)
                    self.assertFalse(expected.get("limitedStart"))
                    self.assertFalse(expected.get("limitedEnd"))
                    replacement.update(buyable="true", archived="no")
                    restored += 1
                elif (client_catalog._unsupported_cottage(expected) or client_catalog._unresolved_level(expected)
                      or client_catalog.themed_land_offers.blocked_offer(expected)):
                    replacement["buyable"] = "false" if isinstance(expected.get("buyable"), str) else False
                else:
                    self.assertIn(expected.get("buyable"), (True, "true"))
                    self.assertTrue(client_catalog._expired(expected.get("limitedEnd"), datetime(2026, 10, 21).date()))
                    replacement["buyable"] = "false" if isinstance(expected["buyable"], str) else False
                self.assertEqual(actual, replacement)
                changed += 1
        fenced_land = [(old, new) for old, new in zip(before_rows, after_rows)
                       if client_catalog.themed_land_offers.blocked_offer(old)]
        self.assertEqual(len(fenced_land), 522)
        for old, new in fenced_land:
            self.assertIn(new.get("buyable"), (False, "false"))
            self.assertEqual({k:v for k,v in new.items() if k != "buyable"},
                             {k:v for k,v in old.items() if k != "buyable"})
        bases = [(old, new) for old, new in zip(before_rows, after_rows)
                 if old.get("type") == "change_farm" and old.get("subtype") == "expand_farm"
                 and old.get("squares") == "50"
                 and set(client_catalog.themed_land_offers._world_nodes(old.get("requirements")))
                     & set(client_catalog.themed_land_offers._specs())]
        self.assertEqual(len(bases), 14)
        self.assertTrue(all(old == new for old,new in bases))
        flowers = [(old,new) for old,new in zip(before_rows,after_rows)
                   if old.get("type") == "bloom" and old.get("className") == "FeatureBuilding"]
        self.assertEqual(len(flowers), 258)
        for old,new in flowers:
            self.assertEqual({k:v for k,v in new.items() if k not in ("features", "buyable")},
                             {k:v for k,v in old.items() if k not in ("features", "buyable")})
            before_features = old["features"]["feature"]
            before_features = before_features if isinstance(before_features,list) else [before_features]
            expected_features = [f for f in before_features if f.get("className") != "HarvestFManager"]
            actual_features = new["features"]["feature"]
            actual_features = actual_features if isinstance(actual_features,list) else [actual_features]
            self.assertEqual(actual_features, expected_features)
        self.assertEqual(restored, 26)
        self.assertGreater(changed, 30000)
        self.assertEqual(len(heritage_patches), 4721)
        self.assertEqual(source.read_bytes(), original)

    def test_puppy_restore_requires_exact_paid_undated_pet_identity(self):
        puppy = {"name": "goldenretriever_puppy_cash", "code": "62", "className": "Pet",
                 "cash": "65", "cost": "300000", "market": "cash"}
        self.assertTrue(client_catalog._restored_puppy(puppy))
        for changes in ({"code": "fake"}, {"name": "unrecovered_puppy"},
                        {"className": "Animal"}, {"cash": "0"}, {"cash": "-1"},
                        {"market": "fake"}, {"limitedEnd": "10/13/2010"}):
            with self.subTest(changes=changes):
                self.assertFalse(client_catalog._restored_puppy(dict(puppy, **changes)))

    def test_restart_reuses_verified_disk_cache_without_decoding_archive_again(self):
        self.source.write_bytes(encode({"settings": {"items": {"item": [
            {"name": "gift", "code": "G", "buyable": "true", "limitedEnd": "12/26/2010"}
        ]}}}))
        cache = Path(self.directory.name) / "derived-cache.json"
        first = client_catalog.payload(self.source, now=self.now, cache_path=cache)
        client_catalog._cache.clear()
        with mock.patch.object(client_catalog, "_generate", side_effect=AssertionError("archive decoded again")):
            self.assertEqual(client_catalog.payload(self.source, now=self.now, cache_path=cache), first)

    def test_disk_cache_rebuilds_after_day_source_or_cache_corruption(self):
        def put(name):
            self.source.write_bytes(encode({"settings": {"items": {"item": [
                {"name": name, "code": "G", "buyable": "true", "limitedEnd": "10/20/2026"}
            ]}}}))
        put("original")
        cache = Path(self.directory.name) / "derived-cache.json"
        client_catalog.payload(self.source, now=self.now, cache_path=cache)
        client_catalog._cache.clear()
        result = decode(client_catalog.payload(self.source, now=self.now + 86400, cache_path=cache))
        self.assertEqual(result["settings"]["items"]["item"][0]["buyable"], "false")
        put("updated")
        client_catalog._cache.clear()
        result = decode(client_catalog.payload(self.source, now=self.now, cache_path=cache))
        self.assertEqual(result["settings"]["items"]["item"][0]["name"], "updated")
        cache.write_text("broken cache")
        client_catalog._cache.clear()
        self.assertEqual(decode(client_catalog.payload(self.source, now=self.now, cache_path=cache)), result)

    def test_cottage_policy_change_invalidates_both_memory_and_disk_cache(self):
        records = [{"name": "later_cottage", "code": "LC", "className": "CraftingCottageBuilding",
                    "buyable": "true", "cost": "100", "unknown": {"preserve": [7]}}]
        self.source.write_bytes(encode({"settings": {"items": {"item": records}}}))
        cache = Path(self.directory.name) / "derived-cache.json"
        with mock.patch.object(client_catalog, "_cottage_policy", return_value=(frozenset(), "old-source-hash")):
            first = decode(client_catalog.payload(self.source, now=self.now, cache_path=cache))
        self.assertEqual(first["settings"]["items"]["item"][0]["buyable"], "false")
        with mock.patch.object(client_catalog, "_cottage_policy", return_value=(frozenset(("later_cottage",)), "reviewed-source-hash")):
            updated = decode(client_catalog.payload(self.source, now=self.now, cache_path=cache))
            self.assertEqual(updated["settings"]["items"]["item"], records)
            client_catalog._cache.clear()
            with mock.patch.object(client_catalog, "_generate", side_effect=AssertionError("re-decoded valid cache")):
                self.assertEqual(decode(client_catalog.payload(self.source, now=self.now, cache_path=cache)), updated)

    def test_themed_land_policy_invalidates_memory_and_disk_cache(self):
        records = [{"name":"xtlfarm14", "code":"XX", "type":"change_farm",
                    "subtype":"expand_farm", "buyable":"true", "cost":"10000",
                    "squares":"58", "requirements":{"requirement":{"className":"World", "name":"toyland"}}}]
        self.source.write_bytes(encode({"settings":{"items":{"item":records}}}))
        cache = Path(self.directory.name) / "land-cache.json"
        with mock.patch.object(client_catalog.themed_land_offers, "policy_digest", return_value="old-land-policy"), \
                mock.patch.object(client_catalog.themed_land_offers, "blocked_offer", return_value=True):
            first = decode(client_catalog.payload(self.source, now=self.now, cache_path=cache))
        self.assertEqual(first["settings"]["items"]["item"][0]["buyable"], "false")
        with mock.patch.object(client_catalog.themed_land_offers, "policy_digest", return_value="new-land-policy"), \
                mock.patch.object(client_catalog.themed_land_offers, "blocked_offer", return_value=False):
            updated = client_catalog.payload(self.source, now=self.now, cache_path=cache)
            self.assertEqual(decode(updated)["settings"]["items"]["item"], records)
            client_catalog._cache.clear()
            with mock.patch.object(client_catalog, "_generate", side_effect=AssertionError("valid policy cache rebuilt")):
                self.assertEqual(client_catalog.payload(self.source, now=self.now, cache_path=cache), updated)

    def test_paid_projection_source_invalidates_memory_and_disk_cache(self):
        records = [{"name":"flower_fixture", "code":"FF", "type":"bloom",
                    "className":"FeatureBuilding", "buyable":"false", "features":{"feature":[
                        {"className":"HarvestFManager"}, {"className":"UpgradeManager","retain":True}]}}]
        self.source.write_bytes(encode({"settings":{"items":{"item":records}}}))
        cache = Path(self.directory.name) / "paid-cache.json"
        actual_projection = client_catalog._paid_projection_policy()[0]
        with mock.patch.object(client_catalog, "_paid_projection_policy", return_value=(actual_projection,"old-paid-policy")):
            first = decode(client_catalog.payload(self.source, now=self.now, cache_path=cache))
        self.assertEqual(first["settings"]["items"]["item"][0]["features"]["feature"],
                         [{"className":"UpgradeManager","retain":True}])
        with mock.patch.object(client_catalog, "_paid_projection_policy", return_value=(lambda item:item,"new-paid-policy")):
            updated = client_catalog.payload(self.source, now=self.now, cache_path=cache)
            self.assertEqual(decode(updated)["settings"]["items"]["item"], records)
            client_catalog._cache.clear()
            with mock.patch.object(client_catalog, "_generate", side_effect=AssertionError("valid paid policy cache rebuilt")):
                self.assertEqual(client_catalog.payload(self.source, now=self.now, cache_path=cache), updated)

    def test_themed_market_policy_invalidates_memory_and_disk_cache(self):
        records=[{"name":"market_fixture","code":"MF","type":"seed","buyable":"true"}]
        self.source.write_bytes(encode({"settings":{"items":{"item":records}}}))
        cache=Path(self.directory.name)/"market-cache.json"
        with mock.patch.object(client_catalog.themed_market_presentation,"policy_digest",return_value="old-market-policy"), \
                mock.patch.object(client_catalog.themed_market_presentation,"item_projection",side_effect=lambda item:dict(item,buyable="false")):
            first=decode(client_catalog.payload(self.source,now=self.now,cache_path=cache))
        self.assertEqual(first["settings"]["items"]["item"][0]["buyable"],"false")
        with mock.patch.object(client_catalog.themed_market_presentation,"policy_digest",return_value="new-market-policy"), \
                mock.patch.object(client_catalog.themed_market_presentation,"item_projection",side_effect=lambda item:item):
            updated=client_catalog.payload(self.source,now=self.now,cache_path=cache)
            self.assertEqual(decode(updated)["settings"]["items"]["item"],records)
            client_catalog._cache.clear()
            with mock.patch.object(client_catalog,"_generate",side_effect=AssertionError("valid Market policy cache rebuilt")):
                self.assertEqual(client_catalog.payload(self.source,now=self.now,cache_path=cache),updated)

    def test_cottage_policy_preserves_home_records_and_regional_admission_gates(self):
        import crafting
        source = ROOT / "xml/gz/v855038/items_opt.amf"
        original = source.read_bytes()
        before = decode(original)["settings"]["items"]["item"]
        after = decode(client_catalog.payload(source, now=self.now))["settings"]["items"]["item"]
        cottages = [(old, new) for old, new in zip(before, after) if old.get("className") == "CraftingCottageBuilding"]
        unsupported = [(old, new) for old, new in cottages if client_catalog._unsupported_cottage(old)]
        self.assertEqual((len(cottages), len(unsupported)), (70, 63))
        for old, new in unsupported:
            with self.subTest(cottage=old["name"]):
                expected = dict(old, buyable="false" if isinstance(old.get("buyable"), str) else False)
                self.assertEqual(new, expected)
        home = [(old, new) for old, new in cottages if old["name"] in crafting.HOME_COTTAGES.values()]
        self.assertEqual({old["name"] for old, _ in home}, set(crafting.HOME_COTTAGES.values()))
        self.assertTrue(all(old == new for old, new in home))
        regional = [(old, new) for old, new in cottages
                    if not client_catalog._unsupported_cottage(old)
                    and old["name"] not in crafting.HOME_COTTAGES.values()]
        self.assertEqual({old["name"] for old, _ in regional},
                         {"xhdcraftingcottage", "xcovecraftingcottage", "xrfcraftingcottage"})
        # Exact Cove/Herbal Hut projections have their own world contract suites.
        regional = [(old, new) for old, new in regional if old["name"] == "xhdcraftingcottage"]
        for old, new in regional:
            self.assertEqual(new, client_catalog.themed_market_presentation.item_projection(old))
            self.assertEqual(new, old)
            self.assertEqual((new["code"], new["craftType"], new["className"], new["buyable"]),
                             ("7la", "xhdcrafttype", "CraftingCottageBuilding", "true"))
            themed = client_catalog.themed_market_presentation._themed()
            worlds = {node.get("name") for node in themed.creative_worlds._nodes(new.get("requirements"))
                      if node.get("className") == "World"}
            self.assertEqual(worlds, {"htown"})
            preview = crafting.regional_catalog_item(new, "htown")
            self.assertEqual((preview["market"], preview["cost"], preview["buyXp"], preview["requiredLevel"]),
                             ("coins", "100000", "1000", "15"))
            self.assertEqual(themed.catalog_rules("htown")["items"][new["name"]]["price"],
                             {"currency": "coins", "amount": 100000})
            for world in ("farm", "england", "rainforest", "australia"):
                self.assertFalse(crafting.regional_cottage(world, new["name"], new["className"]))
            # A recognized recipe service must never override an unadmitted
            # world's purchase fence. Exercise the combined projection without
            # caching the deliberately missing world admission as real policy.
            empty = {world: frozenset() for world in client_catalog.themed_market_presentation._themed().SPECS}
            with mock.patch.object(client_catalog.themed_market_presentation, "_admissions", return_value=empty):
                raw = encode({"settings": {"items": {"item": [old]}}})
                masked = decode(client_catalog._generate(raw, datetime(2026, 10, 21).date()))
            projected = next(row for row in masked["settings"]["items"]["item"] if row["name"] == old["name"])
            self.assertEqual(projected, dict(old, buyable="false"))
        self.assertEqual(source.read_bytes(), original)

    def test_repeated_levels_preserve29_records_and_conflicting12_close_only_purchase(self):
        source = ROOT / "xml/gz/v855038/items_opt.amf"
        before = decode(source.read_bytes())["settings"]["items"]["item"]
        after = decode(client_catalog.payload(source, now=self.now))["settings"]["items"]["item"]
        arrays = [(old, new) for old, new in zip(before, after) if isinstance(old.get("requiredLevel"), list)]
        conflicting = [(old, new) for old, new in arrays if client_catalog._unresolved_level(old)]
        self.assertEqual((len(arrays), len(conflicting)), (41, 12))
        heritage_patches, _ = heritage_pricing.plan(before)
        overlaid = {id(before[index]) for index in heritage_patches}
        for index, (old, new) in enumerate(zip(before, after)):
            if index in heritage_patches:
                with self.subTest(item=old["name"]):
                    self.assertEqual(new, heritage_expected(old, heritage_patches[index]))
        for old, new in conflicting:
            if id(old) not in overlaid:
                with self.subTest(item=old["name"]):
                    self.assertEqual(new, dict(old, buyable="false"))
        for old, new in arrays:
            if id(old) in overlaid or client_catalog._unresolved_level(old):
                continue
            self.assertEqual(client_catalog.purchase_required_level(old), 1)
            expected = dict(old)
            if old.get("buyable") in (True, "true") and client_catalog._expired(old.get("limitedEnd"), datetime(2026, 10, 21).date()):
                expected["buyable"] = "false" if isinstance(old["buyable"], str) else False
            self.assertEqual(new, expected)

if __name__ == "__main__":
    unittest.main()
