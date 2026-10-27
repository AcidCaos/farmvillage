"""Original ordinary inventory admission; real catalogs, disposable AMF saves."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures
import test_cove_cellar as cellar_fixtures
import items
import storage


class InventoryCapacityTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    def command(self, name, params=(), sequence=None):
        # Distinct UI actions have fresh Flash sequences. An explicit sequence
        # remains available for intentional retry/reuse tests.
        if sequence is None:
            self._inventory_sequence = getattr(self, '_inventory_sequence', 0) + 1
            sequence = self._inventory_sequence
        return fixtures.RuntimeFixtureTests.command(name, params, sequence)

    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway
    save = cellar_fixtures.CoveCellarTests.save
    prepare = cellar_fixtures.CoveCellarTests.prepare
    persist = cellar_fixtures.CoveCellarTests.persist
    send = cellar_fixtures.CoveCellarTests.send
    rejected = cellar_fixtures.CoveCellarTests.rejected

    @staticmethod
    def shed(ident=64001, name="toolshedpink", **extra):
        return {"id": ident, "className": "StorageBuilding", "itemName": name,
                "state": "built", "position": {"x": 4, "y": 4, "z": 0}, **extra}

    def prepare_inventory(self, world="fisherman"):
        self.prepare(world, gold=1000000)
        self.save["world"]["objectsArray"] = []
        self.save["userInfo"]["player"].update(cash=100)
        self.group = storage.active_inventory_id(self.save)
        self.save["userInfo"]["player"]["storageData"][str(self.group)] = {}
        self.persist()

    def options(self, **extra):
        return {"storedItemName": "haybale", "target": self.group,
                "origin": 0, "resource": 0, **extra}

    def market_snapshot(self):
        return {"id": self.group, "className": "StorageBuilding"}

    def test_archive_maximum_and_real_storage_capacities(self):
        limits = storage._inventory_limits()
        self.assertEqual({ident: limits[ident] for ident in (-2, -8, -9, -16, -26, -29, -32, -23,
                                                            -31, -28, -34, -33, -21, -24, -15,
                                                            -25, -19, -18)},
                         {ident: 1250 for ident in (-2, -8, -9, -16, -26, -29, -32, -23,
                                                    -31, -28, -34, -33, -21, -24, -15,
                                                    -25, -19, -18)})
        self.assertEqual(limits[-35], 1500)  # Avalon overrides its inherited ceiling.
        self.assertEqual(len(limits), 69)  # Base plus 68 original direct subclasses.
        self.assertEqual(items.get_item_by_name("toolshedpink")["capacity"], "15")
        self.assertEqual(items.get_item_by_name("toolshedpink2")["capacity"], "20")

    def test_empty_inventory_rejects_without_charge_withdrawal_or_source_removal_in_all_four_farms(self):
        for world in ("farm", "england", "meadows", "fisherman"):
            with self.subTest(world=world):
                self.prepare_inventory(world)
                self.rejected("store", self.market_snapshot(), [self.options()])
                hay = {"id": 900, "className": "Decoration", "itemName": "haybale",
                       "state": "static", "position": {"x": 10, "y": 10, "z": 0}}
                self.save["world"]["objectsArray"].append(hay)
                self.save["userInfo"]["player"]["storageData"]["-1"] = {"HB": [1, ["friend"], [{"keep": 1}]]}
                self.persist()
                self.rejected("store", hay, [self.options(resource=900)])
                self.rejected("store", self.market_snapshot(), [self.options(isGift=True)])

    def test_paid_pink_shed_gives_fifteen_slots_and_quantity_boundary_survives_reload_in_all_four_farms(self):
        for world in ("farm", "england", "meadows", "fisherman"):
            with self.subTest(world=world):
                self.prepare_inventory(world)
                balance = self.save["userInfo"]["player"]["cash"]
                self.send("place", self.shed())
                self.assertEqual(self.save["userInfo"]["player"]["cash"], balance - 22)
                # Existing stacks and variant keys both consume one slot per
                # unit, rather than one slot per dictionary entry.
                ledger = self.save["userInfo"]["player"]["storageData"][str(self.group)]
                ledger.update({"HB": [12, [], []], "HB:imported": [2, [], [{"keep": True}]]})
                self.persist()
                self.rejected("store", self.market_snapshot(), [self.options(numToStore=2)])
                self.send("store", self.market_snapshot(), [self.options()])
                self.assertEqual(self.save["userInfo"]["player"]["storageData"][str(self.group)]["HB"][0], 13)
                self.rejected("store", self.market_snapshot(), [self.options()])
                self.player.load_saves()
                stored = self.save["userInfo"]["player"]["storageData"][str(self.group)]
                self.assertEqual(stored["HB"], [13, [], []])
                self.assertEqual(stored["HB:imported"], [2, [], [{"keep": True}]])

    def test_ordinary_contributions_sum_and_clamp_to_original_world_maximum(self):
        self.prepare_inventory("farm")
        self.save["world"]["objectsArray"] = [self.shed(900), self.shed(901, "toolshed")]
        storage._guard_inventory_deposit(self.save, self.group, 17)
        with self.assertRaisesRegex(ValueError, "storage space"):
            storage._guard_inventory_deposit(self.save, self.group, 18)
        self.save["world"]["objectsArray"] = [self.shed(900 + n) for n in range(84)]
        storage._guard_inventory_deposit(self.save, self.group, 1250)
        with self.assertRaisesRegex(ValueError, "storage space"):
            storage._guard_inventory_deposit(self.save, self.group, 1251)

    def test_catalog_capacity_and_replacement_upgrades_ignore_imported_capacity_claims(self):
        self.prepare_inventory("farm")
        self.save["world"]["objectsArray"] = [self.shed(900, capacity=99999)]
        storage._guard_inventory_deposit(self.save, self.group, 15)
        with self.assertRaises(ValueError):
            storage._guard_inventory_deposit(self.save, self.group, 16)
        self.save["world"]["objectsArray"] = [self.shed(900, "toolshedpink2", expansionLevel=2, capacity=99999)]
        storage._guard_inventory_deposit(self.save, self.group, 20)
        with self.assertRaises(ValueError):
            storage._guard_inventory_deposit(self.save, self.group, 21)

    def test_incomplete_ambiguous_and_credit_cellar_imports_never_grant_slots_or_discard_data(self):
        self.prepare_inventory("farm")
        for obj in (self.shed(900, isFullyBuilt=False, state="construction"),
                    self.shed(900, state="unknown-imported-state"),
                    self.shed(900, className="Decoration"),
                    dict(cellar_fixtures.CoveCellarTests.cellar(900), capacity=1250)):
            with self.subTest(obj=obj):
                self.save["world"]["objectsArray"] = [obj]
                self.persist()
                self.rejected("store", self.market_snapshot(), [self.options()])
        # A special building's unimplemented credits do not invalidate slots
        # independently proved by an ordinary, fully built storage building.
        self.save["world"]["objectsArray"].append(self.shed(901))
        storage._guard_inventory_deposit(self.save, self.group, 15)

    def test_inactive_world_buildings_and_foreign_inventory_do_not_provide_space(self):
        self.prepare_inventory("fisherman")
        self.save["_ownedWorldTravel"]["inactive"]["farm"]["objectsArray"] = [self.shed(900)]
        self.persist()
        self.rejected("store", self.market_snapshot(), [self.options()])
        self.save["world"]["objectsArray"] = [self.shed(901)]
        self.persist()
        self.rejected("store", self.market_snapshot(), [self.options(target=-2)])

    def test_overfull_and_malformed_imported_quantities_are_preserved(self):
        self.prepare_inventory("farm")
        self.save["world"]["objectsArray"] = [self.shed(900)]
        for entry in ([16, ["friend"], [{"keep": 1}]], [-1, [], []], [True, [], []], [1.5, [], []], {"legacy": 1}):
            with self.subTest(entry=entry):
                self.save["userInfo"]["player"]["storageData"][str(self.group)] = {"HB": copy.deepcopy(entry)}
                before = copy.deepcopy(self.save)
                with self.assertRaises(ValueError):
                    storage.store_world_item(self.save, self.market_snapshot(), self.options())
                self.assertEqual(self.save, before)


if __name__ == "__main__":
    unittest.main()
