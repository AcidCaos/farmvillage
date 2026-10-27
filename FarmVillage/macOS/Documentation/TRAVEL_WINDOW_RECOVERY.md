> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../ACCEPTANCE.md), [current world scope](../../../WORLD_READINESS.md) and [the continuation backlog](<../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Original paged travel window recovery — 2026-10-23

The original HUD flyout creates a cell only when its current skin has a
corresponding button. With more owned farms than the skin's fixed button count,
destinations disappear. The original `TravelWindow` has paging and a compatible
archived asset; no client patch or new art is needed.

Both launch templates now select this original configuration:

| Experiment | Value | Recovered behavior |
| --- | --- | --- |
| `fv_xas_traveldialog` | 2 | Name bar and travel button open `TravelWindow`. Only variants 2 and 3 enable it; 0 and 1 use the fixed flyout. |
| `fv_travel_window_sorting_preference` | 0 | Constructor uses `assets/dialogs/FV_travelDialog.swf`, which has all four layout sizes and paging controls. Value 1 selects V4, whose only layout is `slots4_mc`. |
| `fv_sasha_the_grocer` | 1 | Travel starts from the player's `unlockedWorldTypes`. Values above 1 scan all worlds and can advertise unowned static worlds or early-access offers. |

The owned-only branch matters because the currently served `fv_fishing_derby=2`
passes Angler's static-world prerequisite. Angler is not supported by the
server. A bytecode search for `EXPERIMENT_FLASH_SASHA_THE_GROCER` finds only
`TravelWindow.setUpInitialFrameData` outside the constants initializer.

## Client evidence

Inspected the repository's served client
`embeds/Flash/v855097-855094/FarmGame.swf` with
`macOS/Scripts/client-inspection/abcdis.py`, using a scratch copy under
`/private/tmp/fv-travel-inspect`.

- `Display.HUD:TravelNameDisplay.showImprovedTravelDialog`, method 7860,
  source lines 243–259: variants 2/3 return true; variants 0/1 return false.
- `TravelNameDisplay.onAssetLoaded`, method 7863, source lines 109–138:
  installs the full-window click handler when that predicate is true.
- `TravelNameDisplay.updateFlyoutCells`, method 7871, source lines 298–304:
  skips any destination whose `getButtonElement(index)` is missing.
- `Widgets.Windows:TravelWindow.<init>`, method 15546, source lines 197–203:
  sorting variant 1 chooses `DIALOG_ASSET_V4`; all others choose `DIALOG_ASSET`.
- `TravelWindow.setUpInitialFrameData`, method 15563, source lines 714–778:
  Sasha variant <=1 copies `unlockedWorldTypes`; other variants scan all worlds.
  Removes the current world, chooses `min(destination count, 4)` for the layout,
  and retains the remaining destinations for small-icon paging.
- `TravelWindow.postLoadComplete`, method 15547, source lines 210–213 and
  400–408: looks up `slots<count>_mc`; enables paging arrows above three small
  icons. `refreshSlotImagesLeft`/`Right` (15555/15554) page by three.

## Local asset evidence

Resolved the two AMF assethash manifests, then inspected decompressed SWF tags
for the actual instance names. Every file below is present and nonempty under
`LocalData/assets/dialogs/`.

| Logical asset | Hash | Layout instances |
| --- | --- | --- |
| `FV_travelDialog.swf` | `3966b6cadfab9a1d49e25c376dce18d8` | `slots1_mc`, `slots2_mc`, `slots3_mc`, `slots4_mc` |
| `FV_travelDialog_v2.swf` | `02414d2f093af1f00d3938a404428c8a` | `slots4_mc` |
| `FV_travelDialog_v3.swf` | `c014dae2e4a8128f1bf261398adf8f80` | `slots4_mc` |
| `FV_travelDialog_v4.swf` | `d9e99cb6b94efc4eb0c17e2e7703291c` | `slots4_mc` |

All four assets contain `arrowLeft_bt`, `arrowRight_bt`, `smallFrame_mc` and
`largeFrame_mc`. V2–V4 additionally have the sorting controls. The first three
hashes come from `assethash/v9/assethash.master.amf.gz`; V4 comes from
`xml/gz/v855098/assethash.min.amf.gz`.

## Verification and acceptance

`macOS/Tests/test_world_travel.py` checks the coordinated values in the rendered
HTML from both launch routes. Browser acceptance must cover Home plus England
(one destination) and more than five owned farms, paging to every destination
and completing an ordinary unfrozen round trip. No browser acceptance is claimed
by this code inspection. `/farms` remains the complete farm-picker fallback.
