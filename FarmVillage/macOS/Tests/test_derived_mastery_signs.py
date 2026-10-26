"""Bounded missing crop mastery gifts, using recovered ladders and actual wire placement."""

from contextlib import redirect_stdout
import copy
from datetime import date
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import pyamf
import client_catalog
import heritage_pricing
import items
import mastery_signs
import persistence


ROOT = Path(__file__).resolve().parents[2]


def decode(raw):
    return pyamf.get_decoder(pyamf.AMF3, zlib.decompress(raw)).readElement()


class DerivedMasteryCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = Path(items.ITEMS_AMF).read_bytes()
        cls.original = decode(cls.raw)["settings"]["items"]["item"]
        cls.additions = mastery_signs.derive(cls.original)

    def test_only167_pinned_source_crop_gifts_gain_unique_local_definitions(self):
        names = {item["name"] for item in self.original}
        codes = {item["code"] for item in self.original}
        missing = {}
        for crop in self.original:
            if crop.get("type") != "seed":
                continue
            for level in crop.get("masteryLevel") or []:
                if ((level.get("gift"), crop.get("code")) in mastery_signs.DEFINITION_GIFTS
                        and level.get("gift") not in names):
                    missing[level["gift"]] = crop
        self.assertEqual(len(missing), 167)
        self.assertEqual({row["name"] for row in self.additions}, set(missing))
        self.assertEqual(len({row["code"] for row in self.additions}), 167)
        self.assertFalse(codes & {row["code"] for row in self.additions})
        for row in self.additions:
            with self.subTest(gift=row["name"]):
                self.assertTrue(row["code"].startswith("fvlocal_mastery_"))
                self.assertNotIn(":", row["code"])
                self.assertEqual(row["masteredItemCode"], missing[row["name"]]["code"])
                self.assertEqual((row["type"], row["className"], row["buyable"], row["giftable"]),
                                 ("decoration", "DynamicMasterySign", "false", "false"))
                self.assertNotIn("marketEntries", row)
                self.assertNotIn("requirements", row)
                self.assertNotIn("cost", row)
                self.assertNotIn("cash", row)

    def test_original_frame_and_each_crops_recovered_icon_are_used_without_new_art(self):
        hash_document = decode((ROOT / "assethash/v9/assethash.master.amf.gz").read_bytes())
        originals = {row["code"]: row for row in self.original}
        for row in self.additions:
            images = {image["name"]: image for image in row["image"]}
            crop_images = {image["name"]: image for image in originals[row["masteredItemCode"]]["image"]}
            self.assertEqual(images["static"], {"name": "static", "url": mastery_signs.FRAME_URL, "loadClass": "mc"})
            self.assertEqual(images["masteredItem"]["url"], crop_images["icon"]["url"])
            self.assertEqual(images["icon"]["url"], crop_images["icon"]["url"])
            self.assertEqual(row["overrideExportName"], "animalmastery")
            for image in images.values():
                _, group, filename = image["url"].split("/", 2)
                self.assertIn(filename, hash_document[group])

    def test_apply_is_append_only_idempotent_and_does_not_rewrite_source(self):
        working = copy.deepcopy(self.original)
        self.assertEqual(mastery_signs.apply(working), 167)
        self.assertEqual(working[:len(self.original)], self.original)
        self.assertEqual(working[len(self.original):], self.additions)
        self.assertEqual(mastery_signs.apply(working), 0)
        self.assertEqual(len(working), len(self.original) + 167)
        self.assertEqual(Path(items.ITEMS_AMF).read_bytes(), self.raw)

    def test_existing_rewards_and_ineligible_crops_are_preserved(self):
        # An original gift record always wins, even after its seed's Home
        # purchase closes. Unsupported seed classes do not enter the roster.
        crop = copy.deepcopy(next(row for row in self.original if row["name"] == "bubblebeans"))
        gift = next(level["gift"] for level in crop["masteryLevel"] if level.get("gift"))
        original_sign = {"name": gift, "code": "recovered-code", "className": "OriginalSign"}
        records = [crop, original_sign]
        self.assertEqual(mastery_signs.derive(records), [])
        self.assertEqual(records[1], original_sign)
        crop["className"] = "UnsupportedSeed"
        self.assertEqual(mastery_signs.derive([crop]), [])

    def test_cache_identity_changes_with_fallback_policy(self):
        with tempfile.TemporaryDirectory(prefix="fv-mastery-cache-") as directory:
            source = Path(directory) / "source.amf"
            source.write_bytes(zlib.compress(pyamf.encode(
                {"settings": {"items": {"item": [{"name": "plain", "code": "P"}]}}},
                encoding=pyamf.AMF3).getvalue()))
            cache = Path(directory) / "derived.json"
            now = 1_800_000_000
            with mock.patch.object(mastery_signs, "policy_digest", return_value="policy-one"):
                first = client_catalog.payload(source, now=now, cache_path=cache)
            with mock.patch.object(mastery_signs, "policy_digest", return_value="policy-two"), \
                    mock.patch.object(client_catalog, "_generate", wraps=client_catalog._generate) as generate:
                self.assertEqual(client_catalog.payload(source, now=now, cache_path=cache), first)
                self.assertEqual(generate.call_count, 1)
                client_catalog._cache.clear()
                self.assertEqual(client_catalog.payload(source, now=now, cache_path=cache), first)
                self.assertEqual(generate.call_count, 1)


class DerivedMasteryWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    def prepare(self):
        import game_settings
        self.path = self.write_fixture()
        save = self.player.session("fixture-farmer")
        player = save["userInfo"]["player"]
        player.update(xp=game_settings.level_to_xp(100), gold=1_000_000, cash=500,
                      mastery={}, masteryCounters={}, achievements={}, achCounters={}, storageData={})
        save["world"]["objectsArray"] = []
        crop = items.get_item_by_name("bubblebeans")
        gift = items.get_item_by_name("masterbubblebeans")
        self.assertIsNotNone(gift)
        # A sign definition survives either side of the separately owned
        # seed reservation. New reservations close purchase, not legacy gifts.
        reserved = "atlantis" in heritage_pricing.RESERVED_WORLDS
        self.assertEqual(heritage_pricing.is_overlaid(crop), not reserved)
        if reserved:
            import creative_worlds
            with self.assertRaises(ValueError):
                creative_worlds.guard_market_purchase(save, crop, "coins", neighbor_count=0)
        return save, crop, gift

    def send(self, name, params):
        return fixtures.gateway_results(self, self.gateway([self.command(name, params)]), [0])[0]

    def test_authored_final_mastery_gift_earns_once_then_places_and_reloads(self):
        import peaceful
        now = 2_000_000_000
        save, crop, gift = self.prepare()
        player = save["userInfo"]["player"]
        final_count = int(crop["masteryLevel"][-1]["count"])
        player["mastery"][crop["code"]] = 1
        player["masteryCounters"][crop["code"]] = final_count - int(crop["masteryYield"])
        plot = {"id": 101, "className": "Plot", "itemName": crop["name"], "state": "grown",
                "plantTime": (now - peaceful.grow_seconds(crop) - 1) * 1000,
                "position": {"x": 4, "y": 4, "z": 0}}
        save["world"]["objectsArray"] = [plot]
        with mock.patch("commands.timestamp_now", return_value=now):
            result = self.send("WorldService.performAction", ["harvest", dict(plot, state="fallow"), []])
            self.send("WorldService.performAction", ["harvest", dict(plot, state="fallow"), []])
        ledger = self.player.session("fixture-farmer")["userInfo"]["player"]["storageData"]["-1"]
        self.assertEqual(ledger[gift["code"]], [1, [], []])
        self.assertIn({"type": "Mastery", "code": crop["code"], "difficulty": 2,
                       "link": "", "updateHud": True}, result["goals"])
        balances = {key: player[key] for key in ("gold", "cash", "xp")}
        snapshot = {"id": -2, "tempId": -2, "className": "DynamicMasterySign",
                    "itemName": gift["name"], "state": "static",
                    "position": {"x": 12, "y": 4, "z": 0}}
        self.send("WorldService.performAction", ["place", snapshot, [{"isGift": True}]])
        current = self.player.session("fixture-farmer")
        self.assertEqual({key: current["userInfo"]["player"][key] for key in balances}, balances)
        self.assertNotIn(gift["code"], current["userInfo"]["player"]["storageData"].get("-1", {}))
        placed = next(obj for obj in current["world"]["objectsArray"] if obj.get("itemName") == gift["name"])
        self.assertEqual(placed["className"], "DynamicMasterySign")
        disk = persistence.read_json(self.path)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        restored = self.player.session("fixture-farmer")
        self.assertEqual(restored["world"]["objectsArray"], disk["world"]["objectsArray"])
        self.assertEqual(restored["userInfo"]["player"]["masteryCounters"][crop["code"]], final_count)
        self.assertEqual(items.get_item_by_code(gift["code"])["name"], gift["name"])

    def test_gift_only_sign_cannot_be_market_purchased(self):
        import creative_worlds
        save, _crop, gift = self.prepare()
        before = copy.deepcopy(save)
        with self.assertRaisesRegex(ValueError, "price is unavailable"):
            creative_worlds.guard_market_purchase(save, gift, "coins", neighbor_count=0)
        self.assertEqual(save, before)

    def test_client_and_server_append_exactly_the_same167_definitions(self):
        raw = Path(items.ITEMS_AMF).read_bytes()
        original = decode(raw)["settings"]["items"]["item"]
        expected = mastery_signs.derive(original)
        client = decode(client_catalog._generate(raw, date(2026, 10, 24)))["settings"]["items"]["item"]
        server = [row for row in items.get_items() if row["code"].startswith(mastery_signs.CODE_PREFIX)]
        self.assertEqual(client[len(original):], expected)
        self.assertEqual(server, expected)
        pristine_cache = persistence.read_json(items.CACHE_ITEMS_JSON)["data"]["settings"]["items"]["item"]
        self.assertEqual(pristine_cache, original)
        self.assertEqual(Path(items.ITEMS_AMF).read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
