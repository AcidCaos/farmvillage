> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../ACCEPTANCE.md), [current world scope](../../../WORLD_READINESS.md) and [the continuation backlog](<../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Original lamb naming and raising — 22 October 2026

Local source and disposable saves only. Browser acceptance is recorded by the
main mechanics pass. This work does not deploy to Bifrost or change the pending
six-hour Bakery queue.

The shipped `FarmGame.swf`, `AnimalBreeding.xml.gz`, item catalog and
`storageConfig.amf.gz` establish these contracts:

- `BreedingRenameWindow` restricts names to letters, numbers and spaces, with
  the Sheep Pen's twenty-character limit. `TAnimalSetName` sends
  `AnimalBreedingService.onSetAnimalName` with item code, DNA hash, name, world
  object ID and optional storage-building snapshot. The implemented branch
  renames an exact sheep or lamb on the active farm. Stored-animal and Gift Box
  naming reject explicitly. The hash excludes the name, so renaming keeps the
  original genes and breeding identity.
- The lamb is `sheeppen_lamb`, code `cy`, class `MutableAnimalBaby`. Its
  `StorageBuilding` filter requires ten `bottle` materials, code `B8`.
  **Feed Bottles** calls `onApplyMaxPossibleBuildingParts`, which uses as many
  owned Gift Box bottles as are still needed. With no bottles, the original
  mini market opens. The normal `TStoreItem` action stores the bottles in the
  lamb's durable contents and material ledger. Purchased bottles use their
  catalog price of one Farm Cash each.
- The tenth bottle triggers `ConstructionBuilding.onStoreComplete`; the
  response's `finishedName` transforms the baby in the running client.
  **Complete Now** uses `TTransformBuilding` and world action
  `TransformBuilding`. `Player.tryBuy(lamb, false, item, count)` subtracts the
  collected bottle count from the catalog ten-Farm-Cash cost. No client price,
  completion flag, gender or DNA is trusted.
- `MutableAnimalBaby.getFinishedItem` uses the saved DNA gender with the
  Sheep Pen's `maleItemName` / `femaleItemName`: `sheeppen_ram` or
  `sheeppen_ewe`. Transformation retains the original object ID, position,
  name and genes. It begins the normal adult harvest clock in milliseconds.
  There is no additional invented lamb-raising timer.

Ordinary placement and move packets cannot import bottles, completion or DNA.
Move packets also cannot reset the adult harvest clock. Feeding, naming and
completion use durable per-session request receipts; replay after a server
restart does not consume bottles or charge cash twice. Login resets only those
receipts because original Flash sequences restart then. Request signatures
include the active world. Inactive-world requests, reused sequences and
unsupported material/identity substitutions fail atomically. The existing
gateway transaction rolls back naming, materials, money, adult conversion and
receipts together when a later request in the batch fails.

A partly fed lamb cannot be packed into generic storage because the recovered
DNA-only storage metadata has no field for its consumed bottles. That transfer
rejects before removing the animal. The original social bottle requests,
shared feed rewards and unrelated animal-raising families remain outside this
bounded implementation.

Verification uses the existing `test_breeding.py` and `test_breeding_wire.py`
suites. They import `test_persistence` before product modules and use disposable
saves. Run from the FarmVillage directory:

```sh
LocalData/venv/bin/python -B -m unittest discover -s macOS/Tests -p 'test_breeding*.py' -v
```
