> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../../ACCEPTANCE.md), [current world scope](../../../../WORLD_READINESS.md) and [the continuation backlog](<../../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Linear image-row selection — 24 October 2026

The original Market Stall has 3,383 image rows. In the active OptItemDataSource
configuration, `ZItemBase.getImageData` 6232 converts that whole image array once,
then calls `createImageObject` 6230 for each row. The latter method previously
called `getArray('image')` again before selecting its one index.
`OptItemDataSource.getArray` 13726 invokes `convertToDataSourceArray` 13723, which
allocates a new Array and a wrapper for every plain source row. Neither converter
caches nor mutates the source.

Market Stall image preparation therefore constructed 11,448,072 wrappers:
3,383 initial wrappers plus 3,383² repeated wrappers (11,444,689). These temporaries
are created within one script event. The pinned Ruffle player services GC debt
after its update/action closure; the parent's reproduced stack reached
ArrayStorage::push→RawVec growth→rust_oom. The allocation-trap identity and
mapping are retained in `RuntimeOOM20261024/`.

## Narrow correction

Only `ZItemBase.createImageObject` changes. For an OptItemDataSource whose raw
`image` member is an Array, it calls the existing `getAttributesHash()` getter,
selects the requested raw row, reuses an already wrapped Opt row, or constructs
one OptItemDataSource around that selected raw object. The getter 13731 returns
its internal Object without copying it. All source attributes and row identities
remain available to the unchanged metadata code.

Other data-source classes and singleton image Objects take the original
getArray/index/BaseDataSource-coerce fallback. The old XML branch is unchanged.
No array, image, artwork, export, symbol, field or catalog row is removed. No
converted array is cached globally or aliased into a new field. A changed raw
source array is read afresh by the next call.

The replacement fits the original 1,174-byte method by reusing two debug spans:

| Offset in method | Behavior |
| --- | --- |
| 29–77 | Initial jump skips out-of-line wrapper/fallback blocks and resumes ordinary initialization at 78 |
| 33 | Construct one selected Opt wrapper, then jump to 176 |
| 49 | Original getArray/index/coerce fallback, then jump to 176 |
| 118–175 | Opt/raw-Array guards, selected-row lookup and wrapper reuse/dispatch |
| 176 onward | Original metadata/URL/name/prefix/label/animation/raster handling, unchanged |

Every new branch stays within this method. Both backward targets (33 and 49)
start with an explicit Label opcode. The pinned Ruffle verifier requires Label
when a backward destination has not already been a seen jump target; valid
instruction alignment alone is insufficient. A briefly staged 58f4 draft lacked
these labels and failed real VM verification with #1021. The new static regression
reconstructs that exact rejected draft, detects its three missing-label branches,
and verifies all branch destinations and exception endpoints in 6230 and 23979.
The draft is recognized only for repair to the current valid stage.

The original header remains maxstack 5,
locals 11 and scope 4..5. Branch 118 is reached only by the existing data-source
experiment path; the original non-experiment branch still reaches 515. The
original caller 6232 and all other 68,491 method bodies are unchanged. Pools,
headers, exception data, source assets and compiled Ruffle runtime bytes remain
unchanged. Both original imageArray selection and the fast path use the sole
caller's valid row index; malformed, externally fabricated calls are outside the
recovered catalog contract.

For this 3,383-row item, wrappers now total 6,766: the unchanged initial conversion
plus one wrapper per selected raw row. Existing Opt rows require no new wrapper.
Other original terrain/pattern variants still generate their normal metadata;
there is no image-count cap or alternate model.

## Pins and validation

Input stage:
`8ca832debfa8404c3934f6859321937c546b1b9b398b0dc44fb030ef90e0b504`

Output stage:
`2912036e46cde068b13b8e302c0e8d11a3e02911b52629fcce8b32f414089f32`

Decompressed body remains 21,521,041 bytes. The predecessor and all earlier known
stages upgrade through the same reviewed chain; final compression variants remain
idempotent. Unknown bodies fail closed. Exact offsets, bytes, method hashes and
block boundaries are in `IMAGE_ROW_LINEAR_BYTE_REVIEW_2026-10-24.json`.

Six new tests decode the actual original items AMF, verify all 3,383 Market Stall
rows and fields, execute the actual old/new selection instructions, count wrapper
constructions, exercise existing-wrapper reuse/source replacement and XML/singleton
fallback, check maxstack and the unchanged metadata tail, and compare all 68,492
methods and pools. They also verify source identity, known-stage upgrade and
unknown-byte refusal. The surrounding 48 focused client/serving tests are separate
regressions. Original-client first-stall placement, Gift Box and durable quest
reward acceptance remain with the parent's fresh synthetic browser verification.
