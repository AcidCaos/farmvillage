# Catalogue and metadata preparation

The source includes the recovery algorithms. The original inputs and generated catalogues are separate local resources. Use [RESOURCE_SETUP.md](../../docs/RESOURCE_SETUP.md) for the exact import boundary and the parts of independent reconstruction still requiring work.

The current runtime reads prepared files in `data/` and original interface/artwork under `static/`. It does not fetch a replacement catalogue from a remote service. The generated data's presence does not establish gameplay support for every item it describes.

## Tool map

| Script | Reads | Writes / role |
| --- | --- | --- |
| `prepare_assets.py` | Original item cache, master manifest, original XML/artwork and a legacy save input | Initial catalogue/rules/provenance/UI data; also creates an old practice-save copy |
| `recover_catalog.py` | Existing catalogue/provenance, original item AMF, delta/master manifests, locale SWF and extracted artwork | Complete artwork/label recovery, catalogue audit and provenance; `--audit-only` suppresses output |
| `prepare_archive.py` | Original item AMF/master manifest and existing catalogue/provenance | Recovered source prices, dates, acquisition context and archive provenance |
| `prepare_untabbed.py` | Source-identified pristine item cache, prepared catalogue and current heritage policy | `data/untabbed.json` |
| `prepare_progression.py` | Recovered original progression definitions | `data/progression.json` |
| `prepare_helpers.py` | Original collections/quest XML, locale data and artwork | `data/helpers.json` and helper artwork |
| `prepare_encyclopedia.py` | Original item data, existing provenance and authored `historical-prizes.json` | Encyclopedia overlay and associated copied artwork |
| `prepare_skin.py` | Original SWF raster symbols and master manifest | Original skin images and skin provenance |
| `recover_labels.py` | Local `en_US.swf` literal data | Localized labels JSON without executing Flash |

Paths in this table are relative to `GodBarn/scripts/` unless stated otherwise. These tools are not one interchangeable command. Several expect previously prepared generated files, and `prepare_skin.py` is a fixed sibling-layout preparation utility rather than a general CLI.

`prepare_assets.py` belongs to the older bootstrap workflow. It copies a legacy farm into `data/bootstrap-save.json`; do not use that old save step for this clean-start release. A future independent bootstrap must produce only resource metadata and use newly authored synthetic QA state. The current source export and private-input manifest deliberately omit that practice-save copy.

## Item identity and image precedence

Keep all recovered item records, including duplicate names, while matching the game's first-record-by-name lookup. Do not silently deduplicate historical source rows or apply a pricing overlay to the supposedly pristine decode used by another generator.

The original client checks the version-specific min/delta manifest before the master. `recover_catalog.py` follows that precedence. If the selected declared image is absent locally, it remains unresolved; using an older master hash would display a different revision as if it were the original selected file. Exact unmatched images get the neutral unavailable marker. Preserve logical paths, source digests, selected manifest and copied-file identities.

The label decoder reads the locale constructor's literal values. It does not run arbitrary Flash code. Missing labels or artwork remain explicit gaps, not permission to invent historical facts.

## Not in Market

`catalog_tools.has_market_entry` includes the original client's sold-seed type/subtype fallback. An ordinary sold crop without explicit `marketEntries` therefore stays in the main catalogue rather than automatically becoming Not in Market. Explicit hidden-only seeds and crops without a recorded sale remain eligible for that archive view.

`prepare_untabbed.py` verifies catalogue membership against the pristine original records before importing `heritage_pricing`. It applies that policy only to an in-memory copy and records its digest. World requirements and original prices are read before the Home overlay can rewrite them.

Its result is archive classification, not a full audit of current world, date, licence, experiment or quest gates. Re-run when catalogue/pricing inputs change; record a new output digest and inspect the exact row delta. A byte-identical regeneration supports unchanged data, not new gameplay acceptance.

## History, calendar and progression boundaries

Recovered archive prices describe recorded offers. They are not automatically the original release price. The encyclopedia's sourced prize shelves rely on the separately supplied authored `historical-prizes.json`; the generator cannot recover that curation from the item file alone.

The recurring calendar replays valid recovered month/day windows. It is a browsing rule and does not modify the game's availability or economy. Invalid or unknown historical dates remain unknown.

Collection filling and quest progress helpers advance only the supported saved counters. They must not invent missing reward-claim services, activate unrelated quests or manufacture campaign completion. Mastery/ribbon rewards and live harvests retain their distinct authoritative paths.

## Reproduce deliberately

Use a disposable working clone after preserving its code-only source copy. Restore resources, record input identities and run only the generator whose preconditions you have satisfied. Keep generated catalogues/artwork ignored. The [resource guide](../../docs/RESOURCE_SETUP.md) gives checked CLI examples and names unresolved bootstrap dependencies.

Full God Barn tests need those prepared resources. Test filtering/membership separately from preview/apply/save behavior and real-client interaction. The current source and bounded results are recorded in [ACCEPTANCE.md](../../ACCEPTANCE.md); raw private receipts are intentionally not part of this source repository.
