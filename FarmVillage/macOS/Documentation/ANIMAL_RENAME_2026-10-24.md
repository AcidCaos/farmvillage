> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../ACCEPTANCE.md), [current world scope](../../../WORLD_READINESS.md) and [the continuation backlog](<../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Sheep and lamb naming — 2026-10-24

The original 2026-10-22 `MutableAnimalState.getStateKey` #1069 report was caused
by a scalar pattern gene (`P.T = "a"`). The current source already normalizes
valid legacy scalar genes to the original one-element array during init,
including owned worlds, gifts, inventory and Sheep Pen metadata. New offspring
and catalog variants already use arrays. This session retained that repair and
checked its existing regressions.

The remaining server refusal was naming an animal in storage. `breeding.rename`
now handles the original Sheep Pen and gift-box branches as well as placed
animals. It changes only the first saved DNA record selected by the client,
preserves the genotype/hash and quantity, synchronizes any duplicate pen ledger
metadata, and retains sender IDs and unknown DNA fields. The incoming pen
snapshot is optimistic client state; its contents and DNA are never imported.
Renaming has no currency or XP charge. Existing request receipts make retries
idempotent. Unsupported/malformed context or an unowned hash rejects atomically.

Ordinary world inventory naming is not added: the recovered negative-world-ID
client branch specifically accesses `Global.player.gifts`.

## Recovered client contract

Inspection used a copy of `embeds/Flash/v855097-855094/FarmGame.swf` in
`/private/tmp/fv-lamb-rename-20261024/`. Client SHA-256:
`1edea7cbecefcb1e1233da207164942f0088a83b87afc9254850f5fcde5034ae`.
No SWF bytes were changed.

`macOS/Scripts/client-inspection/abcdis.py` recovered:

- `MutableAnimalState.getStateKey`, method 16639, source lines 339–372:
  hashes gender and indexed base/pattern alleles, including `P.T[HSV_CHILD_INDEX]`.
  The personal name is excluded, so renaming must preserve the metadata hash.
- `BreedingRenameWindow.onOkayClick`, method 47026, source lines 151–152:
  obtains `getHashKey()` before passing code, hash, name, object ID and building
  to `AnimalBreedingManager.setAnimalName`.
- `AnimalBreedingManager.setAnimalName`, method 16489, source lines 464–481:
  the building branch selects `storageMetaData[code:hash][0]`, changes its name
  and replaces that first packed JSON record. Lines 485–495 select the first
  gift extraData record with the matching hash when the world ID is negative.
  Lines 501–503 update a placed world object otherwise.
- `TAnimalSetName.perform`, method 40701, source line 56: sends
  `AnimalBreedingService.onSetAnimalName(code, hash, name, worldId,
  building ? building.getSaveObject() : null)`.
- `TAnimalSetName.onComplete`, method 40702, source lines 61–62: invokes an
  optional callback with the response; it reads no additional response fields.
  The existing empty map response is preserved.

## Validation

Dedicated gateway coverage: `macOS/Tests/test_breeding_rename_storage.py`.
It checks pen and gift naming, first-record selection, ledger synchronization,
save/reload, free retries, snapshot forgery, malformed metadata, unsupported
worlds and rejection without a disk write. Existing `test_breeding.py` and
`test_breeding_wire.py` cover the legacy array repair and placed lamb naming.

Focused command (from `macOS/Tests`) passed 57 tests in 30.362 seconds:

```sh
PYTHONPATH=../.. ../../LocalData/venv/bin/python -m unittest \
  test_breeding_rename_storage test_breeding test_breeding_wire
```

Browser acceptance remains pending. Bytecode recovery and AMF/JSON tests are
not a real-client visual check.
