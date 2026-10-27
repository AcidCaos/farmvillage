"""Approved retired-world decorations in Mistletoe Lane: exact admission, price, placement and refusals.

Eight Holiday Lights decorations are individually approved for Mistletoe Lane (retired_decor.py). The
retired world itself stays retired. Every test uses an in-memory disposable save and the recovered
catalog; nothing writes a real save and no server is started.
"""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence  # Establish disposable writable paths before bundle imports.
import creative_worlds
import heritage_pricing
import retired_decor
import themed_market_presentation as presentation
import themed_worlds as tw
import world_travel
from test_themed_worlds import ActivatedFarmHelpers, NOW, balance_key, catalog_item

WORLD = "htown"
SOURCE = "hlights"
EXPECTED = {
    "xhl_glowingflowerbox": ("cash", 5),
    "xhl_holidaylamppost": ("cash", 5),
    "xhl_twistylamppost": ("cash", 5),
    "xhl_lightedbench": ("cash", 4),
    "xhl_hollybrightgreetings": ("cash", 8),
    "xhl_puppysnowpile": ("cash", 10),
    "xhl_hollybrightlane": ("cash", 10),
    "xhl_hollybrightpath": ("coins", 40000),
}
# Reviewed and deliberately NOT approved: a reward item that passes the ordinary screen, a large
# attraction, a gnome, a moat, an Unwither ring, a promo sign, a baby animal and a tree.
HELD_BACK = ("beatholidaylightsstatue", "xhl_hollybrightcarousel", "gnome_xhl_illuminated",
             "moat_xhl_rainbow", "xlg_xpromo_sign")


def clear_caches():
    # catalog_rules and the Market admissions are cached for the process. Clear both before and after any
    # test that patches the approved table, so a patched result can neither be served stale nor leak.
    tw.catalog_rules.cache_clear()
    presentation._admissions.cache_clear()


class ApprovedTableTests(unittest.TestCase):
    def test_the_table_names_exactly_the_eight_reviewed_items(self):
        self.assertEqual(retired_decor.destinations(), {WORLD})
        entry = retired_decor.APPROVED[WORLD]
        self.assertEqual((entry["source"], entry["waivedGate"]), (SOURCE, "fv_hlights"))
        self.assertEqual(set(entry["items"].values()), set(EXPECTED))
        self.assertEqual(len(entry["items"]), 8)

    def test_each_record_still_has_the_shape_that_was_reviewed(self):
        for code, name in retired_decor.APPROVED[WORLD]["items"].items():
            with self.subTest(name):
                item = catalog_item(name)
                self.assertEqual(item["code"], code)
                self.assertEqual(item["type"], "decoration")
                self.assertIn(item.get("buyable"), ("true", True))
                self.assertFalse(item.get("limitedStart") or item.get("limitedEnd"), "an item with its own date window is never approved")
                self.assertEqual([f for f in heritage_pricing.BLOCKING_FIELDS if item.get(f) not in (None, "")], [])
                worlds = {n.get("name") for n in creative_worlds._nodes(item["requirements"]) if n.get("className") == "World"}
                self.assertEqual(worlds, {SOURCE})
                self.assertEqual(item.get("experimentGate"), "fv_hlights")
                self.assertTrue(retired_decor.allows(item, WORLD))

    def test_allows_is_exact_and_fails_closed(self):
        base = catalog_item("xhl_lightedbench")
        self.assertTrue(retired_decor.allows(base, WORLD))
        self.assertEqual(retired_decor.waived_gates(base, WORLD), {"fv_hlights"})
        self.assertFalse(retired_decor.allows(base, "storybook"), "only the approved destination")
        self.assertFalse(retired_decor.allows(base, SOURCE), "the retired world itself gains nothing")
        self.assertEqual(retired_decor.waived_gates(base, "storybook"), frozenset())
        for label, change in (
                ("different code", lambda i: i.update(code="zzz")),
                ("different name", lambda i: i.update(name="xhl_lightedbench2")),
                ("another world as well", lambda i: i.update(requirements={"compare": "any", "requirement": [
                    {"name": SOURCE, "className": "World"}, {"name": "storybook", "className": "World"}]})),
                ("only the destination", lambda i: i.update(requirements={"requirement": {"name": WORLD, "className": "World"}})),
                ("an extra requirement", lambda i: i.update(requirements={"compare": "all", "requirement": [
                    {"name": SOURCE, "className": "World"}, {"name": "q", "className": "Quest"}]})),
                ("a second gate", lambda i: i.update(experimentGate=["fv_hlights", "fv_other"])),
                ("a different gate", lambda i: i.update(experimentGate="fv_other"))):
            with self.subTest(label):
                changed = copy.deepcopy(base)
                change(changed)
                self.assertFalse(retired_decor.allows(changed, WORLD))
        for junk in (None, "xhl_lightedbench", [], 5):
            self.assertFalse(retired_decor.allows(junk, WORLD))

    def test_the_retired_world_stays_retired(self):
        self.assertNotIn(SOURCE, tw.ACTIVE_WORLDS)
        self.assertNotIn("glen", tw.ACTIVE_WORLDS)
        self.assertNotIn(SOURCE, world_travel.supported_worlds())
        self.assertNotIn(SOURCE, {entry["worldType"] for entry in creative_worlds.candidates()})
        for world in tw.SPECS:
            if world != WORLD:
                with self.subTest(world):
                    self.assertFalse(set(EXPECTED) & set(tw.catalog_rules(world)["items"]),
                                     "an approved item is admitted only to its destination")


class AdmissionTests(ActivatedFarmHelpers, unittest.TestCase):
    world = WORLD

    def setUp(self):
        super().setUp()
        clear_caches()
        self.addCleanup(clear_caches)

    def test_exactly_the_eight_are_added_at_their_own_prices_and_nothing_else_changes(self):
        with mock.patch.object(retired_decor, "APPROVED", {}):
            before = tw.catalog_rules(WORLD)
            seeds_before = tw.allowed_seeds(WORLD)
        clear_caches()  # the emptied-table result above is now cached; compute the real one afresh
        after = tw.catalog_rules(WORLD)
        self.assertEqual(set(after["items"]) - set(before["items"]), set(EXPECTED))
        self.assertEqual(set(before["items"]) - set(after["items"]), set())
        for name in before["items"]:
            self.assertEqual(after["items"][name], before["items"][name], name)
        for name, (currency, amount) in EXPECTED.items():
            with self.subTest(name):
                row = after["items"][name]
                self.assertEqual(row["price"], {"currency": currency, "amount": amount})
                self.assertEqual(row["type"], "decoration")
        self.assertEqual(after["unpriced"], before["unpriced"])
        self.assertEqual(after["expansions"], before["expansions"])
        self.assertEqual(tw.allowed_seeds(WORLD), seeds_before, "no seed is added")

    def test_held_back_items_stay_refused_even_though_they_come_from_the_same_world(self):
        admitted = tw.catalog_rules(WORLD)["items"]
        calf = next(i["name"] for i in tw.items.get_items() if str(i.get("name", "")).startswith("calf_"))
        ring = next(i["name"] for i in tw.items.get_items() if str(i.get("name", "")).startswith("xlgunwitherring"))
        for name in HELD_BACK + (calf, ring):
            with self.subTest(name):
                self.assertNotIn(name, admitted)
                if tw._catalog_item(name):
                    with self.assertRaisesRegex(ValueError, "not admitted"):
                        tw.guard_purchase(self.travelled(), catalog_item(name), now=NOW)

    def test_each_item_is_charged_its_own_price_once(self):
        for name, (currency, amount) in EXPECTED.items():
            with self.subTest(name):
                save = self.travelled()
                key = balance_key(currency)
                before = save["userInfo"]["player"][key]
                other = save["userInfo"]["player"]["cash" if key == "gold" else "gold"]
                charge = tw.charge_purchase(save, catalog_item(name), now=NOW)
                self.assertEqual(charge, {"currency": currency, "amount": amount})
                self.assertEqual(save["userInfo"]["player"][key], before - amount)
                self.assertEqual(save["userInfo"]["player"]["cash" if key == "gold" else "gold"], other)

    def test_a_short_balance_is_refused_without_debit(self):
        for name, (currency, amount) in EXPECTED.items():
            with self.subTest(name):
                save = self.travelled()
                key = balance_key(currency)
                save["userInfo"]["player"][key] = amount - 1
                before = copy.deepcopy(save)
                with self.assertRaisesRegex(ValueError, "Not enough currency"):
                    tw.charge_purchase(save, catalog_item(name), now=NOW)
                self.assertEqual(save, before)

    def test_placement_keeps_the_catalog_class_and_is_charged_once(self):
        for name, (currency, amount) in EXPECTED.items():
            with self.subTest(name):
                rule = tw.catalog_rules(WORLD)["items"][name]
                klass = rule["className"] or "Decoration"
                save = self.travelled()
                snapshot = {"tempId": -1, "position": {"x": 19, "y": 19, "z": 0}, "state": "horizontal",
                            "instanceDataStoreKey": None, "id": 63000, "deleted": False, "components": {},
                            "direction": 0, "itemName": name, "className": klass}
                before = copy.deepcopy(save)
                tw.guard_action(save, "place", snapshot, [{"currency": currency}], now=NOW)
                self.assertEqual(save, before, "the preflight never debits")
                wrong = "Decoration" if klass != "Decoration" else "RotateableDecoration"
                with self.assertRaisesRegex(ValueError, "recovered object class"):
                    tw.guard_action(before, "place", dict(snapshot, className=wrong), [{}], now=NOW)
                with self.assertRaisesRegex(ValueError, "outside"):
                    tw.guard_action(copy.deepcopy(before), "place", dict(snapshot, position={"x": 50, "y": 50, "z": 0}), [{}], now=NOW)

    def test_the_level_gate_still_applies(self):
        save = self.travelled()
        item = catalog_item("xhl_lightedbench")
        item["requiredLevel"] = "99"  # a raised level requirement must still be enforced
        with mock.patch.object(tw, "_catalog_item", return_value=item), \
                self.assertRaises(ValueError):
            tw.guard_purchase(save, item, now=NOW)


class ClientPresentationTests(unittest.TestCase):
    def setUp(self):
        clear_caches()
        self.addCleanup(clear_caches)

    def test_an_approved_item_is_offered_as_a_mistletoe_item_and_nothing_else_changes(self):
        for name in EXPECTED:
            with self.subTest(name):
                original = catalog_item(name)
                projected = presentation.item_projection(original)
                self.assertEqual(projected["requirements"], {"compare": "any", "requirement": [
                    {"className": "World", "name": WORLD, "strict": "true"}]})
                self.assertNotIn("experimentGate", projected)
                self.assertEqual(projected["buyable"], original["buyable"], "buyable is not rewritten")
                self.assertEqual(projected["archived"], original["archived"], "archived is not rewritten")
                rest = lambda i: {k: v for k, v in i.items() if k not in ("requirements", "experimentGate")}
                self.assertEqual(rest(projected), rest(original))
                self.assertIn("experimentGate", original, "the recovered record is never mutated")

    def test_every_other_retired_world_record_projects_exactly_as_before(self):
        records = [catalog_item(n) for n in HELD_BACK if tw._catalog_item(n)]
        records.append(next(copy.deepcopy(i) for i in tw.items.get_items() if str(i.get("name", "")).startswith("calf_")))
        with_table = [presentation.item_projection(r) for r in records]
        clear_caches()
        with mock.patch.object(retired_decor, "APPROVED", {}):
            without_table = [presentation.item_projection(r) for r in records]
        self.assertEqual(with_table, without_table)
        self.assertTrue(all(p["buyable"] in ("false", False) for p in with_table), "unapproved retired items stay unbuyable")

    def test_a_changed_record_is_not_projected(self):
        record = catalog_item("xhl_lightedbench")
        record["name"] = "xhl_lightedbench_changed"
        projected = presentation.item_projection(record)
        self.assertIn("experimentGate", projected, "an unapproved record keeps its gate")
        self.assertIn(projected["buyable"], ("false", False), "and stays unbuyable like any other retired-world item")

    def test_the_policy_digest_changes_when_the_approved_table_file_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            first, second = Path(temporary, "a.py"), Path(temporary, "b.py")
            first.write_text("APPROVED = {}\n")
            second.write_text("APPROVED = {'htown': {}}\n")
            digests = []
            for path in (first, second):
                with mock.patch.object(retired_decor, "__file__", str(path)):
                    digests.append(presentation.policy_digest())
            self.assertNotEqual(*digests)


if __name__ == "__main__":
    unittest.main()
