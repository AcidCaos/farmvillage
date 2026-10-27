# God Barn maintainer handoff

This guide describes the implementation included in the community source handoff. It replaces earlier workstation-specific launcher and deployment notes. Native macOS and browser/Ubuntu continue; iPad/iOS is abandoned. The active release has sixteen worlds and carries no previous farms or authentication. Use the root [takeover guide](../TAKEOVER.md), [acceptance](../ACCEPTANCE.md) and [world readiness](../WORLD_READINESS.md) for current release claims.

## Start with one mode and one synthetic farm

The standalone application and live adapter share transformation code but have different ownership and write boundaries. Reproducing a bug in one does not certify the other.

In standalone mode, `server.py` owns its workspace records and history. It reads copied metadata and applies transformations to detached imported JSON. It neither discovers a game process nor writes into a game profile. No old practice-save copy is shipped in this release.

In the integrated mode, `integration.py` mounts routes on the owned game server. The game is authoritative. The adapter must use the game's current selected farm and transaction APIs; it must never replace them with direct JSON writes. See [INTEGRATION_CONTRACTS.md](Documentation/INTEGRATION_CONTRACTS.md).

## Before changing an operation

Trace the HTTP route, detached engine operation and response rendering together. A preview must describe the exact mutation later applied. Check the negative cases: malformed state, unsupported class, stale preview, wrong farm, expired token, concurrent session and failed persistence. Keep unsupported actions visibly unavailable rather than charging or inventing a result.

Use the root external Python environment. The selected source-only tests can run without game inputs. Full regression and original-client checks need the resource set described in [RESOURCE_SETUP.md](../docs/RESOURCE_SETUP.md). Original resource files and generated catalogues remain outside the source upload.

## Maintain catalogue provenance

The item browser reads prepared local metadata; it does not import game modules at runtime. Recovery scripts decode local preservation inputs and write God Barn's generated data/artwork. Keep generation separate from serving and from play-state mutation.

When changing catalogue logic, preserve all recovered records, first-name lookup semantics, manifest precedence and honest missing-image labels. Do not substitute an unrelated item's image. The version-specific delta asset manifest wins over the master when it declares a path; a missing selected file stays missing. The [catalogue pipeline](Documentation/CATALOG_PIPELINE.md) explains tools, inputs and known reconstruction gaps.

For Not in Market, `prepare_untabbed.py` imports the selected FarmVillage source's read-only heritage pricing policy. Run it against the intended source revision and a source-identified pristine decoded item cache. Do not reuse a cache already changed by a policy overlay. A data regeneration needs new input/output identities and its own acceptance record.

## Useful independent contribution lanes

- Improve a detached engine contract with a failing synthetic example and a focused correction.
- Correct catalogue classification using an exact original record/client rule and verify the corresponding UI filter.
- Repair live preview/apply/return behavior with two independent synthetic sessions and an actual process restart.
- Extend one explicitly supported building or progression contract after recovering its original inputs; keep unknown mechanics unavailable.
- Finish the separately listed native and actual Ubuntu checks in the root acceptance record.

The next restoration work is [Wave 3.md](<../Wave 3.md>). A source or build pass is separate from browser graphics, native-window play, actual Ubuntu hosting and every-world feature acceptance. Do not use this guide to reopen the abandoned iPad or dropped worlds.

## Preserve the release boundary

The guided clean installer owns a narrowly identified managed installation. Preparing a package does not authorize remote deployment. Legacy deployment scripts remain source for audit/tests; they are not the current clean-install procedure. Use [BIFROST_SETUP.md](../BIFROST_SETUP.md).

Ship no old saves, snapshots, player history, credentials or sessions. New farms must still persist normally across save/reload and actual server restart. Preserve AcidCaos attribution, third-party notices and the [source/resource licence boundary](../SOURCE_NOTICE.md).
