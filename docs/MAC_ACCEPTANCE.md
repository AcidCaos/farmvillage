# Mac acceptance run sheet

This page is a form to fill in while finishing the remaining native Mac checks. **Whoever wrote it could not run the app:** it was prepared in a Linux container, so every statement about executing the Mac app is **UNRUN** until you record it here with evidence. What is owed is named in [world readiness](../WORLD_READINESS.md) and the [validation record](../ACCEPTANCE.md). The wider plan is in [Wave 3](<../Wave 3.md>), and the Ubuntu equivalent is the [Ubuntu run sheet](UBUNTU_ACCEPTANCE.md).

Keep the platforms separate. A native Mac window, a browser on the Mac and an Ubuntu host are three different results. Intel hardware, signing and notarization, and long-session stability are further separate gates and are not covered here.

## What is still owed

The record says twelve of sixteen native loops passed, then the Mac session locked. These seven items remain.

| ID | Check | World id | Result |
| --- | --- | --- | --- |
| N01 | Core crop loop in the native window | `oasis` (Oasis Gardens) | UNRUN |
| N02 | Core crop loop in the native window | `htown` (Mistletoe Lane) | UNRUN |
| N03 | Core crop loop in the native window | `oz` (Emerald Valley) | UNRUN |
| N04 | Core crop loop in the native window. Judge the settled scene separately from an early partial frame. | `sleepyhollow` (Horseman's Hollow) | UNRUN |
| N05 | Fresh visual after a real restart | `farm` (Home) | UNRUN |
| N06 | Fresh visual after a real restart | `fforest` (Mystical Groves) | UNRUN |
| N07 | Fresh visual after a real restart | "the last world" | UNRUN |

**N07 is ambiguous in the record.** Both documents say "last world" without naming it. The last name in the list of twelve passed worlds is Toy Town (`toyland`). Choose one, write the choice and your reason in the ledger, and do not leave it implied.

## What the repository contains for native testing

This is what was found by reading the tracked source. It is a finding, not a recommendation to rely on any of it.

| Item | What it is | What it does not do |
| --- | --- | --- |
| The app (`FarmVillage/macOS/Sources`) | SwiftUI and WebKit app that supervises a local Python server on `127.0.0.1:5501`. | |
| Smoke runners in `FarmVillage/macOS/Tests` (`run-native-smoke.sh`, `run-runtime-lifecycle-smoke.sh`, `run-native-heritage-smoke.sh`, `run-launcher-library-smoke.sh`) | Compile and run small Swift checks of launch arguments, the prepare, start and stop lifecycle, launcher artwork and God Barn. | None mentions a world, travel or Instant Grow. |
| `run-full-game-smoke.sh` with `NativeWebSmoke.swift --full-game` and `verify_native_gameplay.py` | Opens the production `GameWebView` in an owned window and replays a click plan you write into `actions.json`. It then checks one **harvest of the ripe starter crop** on a new fixture farm, the gold change, a client reload, and the saved files. | Home only. The expected yield is hard-coded. It does not travel, plow, plant, grow or restart anything, and it has no per-world logic. |

Two gaps, recorded and not filled in:

1. **No tracked driver for a themed-world loop.** A search of the native Swift tests and runner scripts for the world ids, travel and Instant Grow found nothing. The "private production-GameWebView/AppKit harness" named in the validation record, which is credited with twelve world loops and the restart comparison, is not identifiable in the repository: its scripts, click plans and receipts were not found. The loops below are therefore done by a person in the real app. Nothing here claims an automated equivalent exists.
2. **No locked-session detection anywhere.** The only mentions of a locked session are the two status documents. The harness would simply fail or hang on a locked screen. This page makes that a manual precondition.

`session_a_farming_fixture.py` is a browser fixture helper with its own `/private/tmp` rule. It is not part of the native checks.

## Before every sitting

- [ ] The Mac is **unlocked and awake** for the whole sitting. If a lock screen appears at any point, stop, record the world and the time, and mark that item **UNRUN, not FAIL**. Do not try to bypass the lock. An earlier sweep stopped for exactly this reason, and a locked session proves nothing about a world.
- [ ] Keep the display and system awake. In Terminal, leave `caffeinate -dimsu` running for the sitting. In System Settings, the Lock Screen options (names vary by macOS version) should not lock or sleep the display while you work. These were not run or checked while this page was written.
- [ ] Exactly one FarmVillage app is open, and no browser tab is open on the same farm. Only one client may write a farm.
- [ ] Port 5501 is free before you start: `lsof -nP -iTCP:5501 -sTCP:LISTEN` prints nothing.
- [ ] Screenshots and notes go in a folder **outside** the repository.

## Record before you start

| Field | Value |
| --- | --- |
| Date, time zone, operator | |
| `sw_vers`, `uname -m`, `xcodebuild -version` | |
| Source commit the app was built from (`git rev-parse HEAD`) | |
| App path (normally `PACK/macos-build/DerivedData/Build/Products/Release/FarmVillage.app`) | |
| `shasum -a 256` of `PREPARED_RUNTIME.json`, `PUBLIC_RUNTIME_BUILD.json` and `PUBLIC_INSTALL.json` inside the app's `Contents/Resources/Runtime` | |
| Data folder used | |

## Make a clean, synthetic farm

Use a folder that holds nothing you care about, so the test never touches a farm you play.

1. Quit any running FarmVillage (Command-Q). Opening the app while it runs will not pass new arguments.
2. Choose an empty folder, for example `QA="$HOME/farmvillage-qa-data"`, and open the app on it:

   ```sh
   open "/path/to/FarmVillage.app" --args --farmvillage-data-dir "$QA"
   ```

3. A new, empty folder needs its Python engine once: Tools menu, **Prepare Runtime**. This installs pinned Python packages from PyPI and downloads no artwork.
4. Farm menu, **Create Farm…**. Use a name that cannot be mistaken for a real farm, such as `QA-oasis-<date>-<4 hex>`. A new farm has the original starter. Nothing is granted.
5. Record the farm name and the farmer id (the file name under `$QA/saves`).

## Reaching a world

World access follows the original level and currency rules. Read the level and price the game shows and record them. There are two honest ways in, and they must be labeled:

- **Earned:** play to the level and balance the game requires.
- **Setup:** use Tools menu, **God Barn**, preview the change, then apply it explicitly. Everything done this way is **setup, not earned progress**. Write down each change.

Never edit a save file by hand, and never shorten a crop timer. A natural timer or the original paid Instant Grow are the only allowed ways to finish a crop.

## The core loop, defined

A world's loop is PASS only if you performed every step below in the native window and recorded the evidence. A step you did not do makes the loop UNRUN.

| Step | What to do | Record |
| --- | --- | --- |
| L1 Arrive and settle | Travel to the world through the game's own travel window. Wait until loading finishes and the scene and HUD stop changing. For N04 look again after a pause, because an early partial frame is not a settled scene. | Screenshot, time, HUD balances |
| L2 Plow | Plow an empty plot. | Price shown, balance before and after |
| L3 Plant | Plant a crop. | Crop, seed price, displayed grow time |
| L4 Grow | Wait the natural timer, **or** use the original paid Instant Grow. | Start and end clock times, or the price shown and the balance change |
| L5 Mature art | The crop shows its mature graphic, not a placeholder or a gap. | Screenshot |
| L6 Harvest | Harvest it. | Yield, experience and coin change |
| L7 Reload | Farm menu, **Reload Current View** (Command-R). | State identical to before |
| L8 Owned-process restart | Farm menu, **Stop Farm**. Quit the app. Reopen it on the same data folder and open the farm. A new server process must be listening: compare `lsof -nP -iTCP:5501 -sTCP:LISTEN` before and after. | Both process ids |
| L9 Compare the saved farm | Copy the farm's save before the restart and after it, then run the comparison below. | Output of the comparison |

Notes for L1 and L8: the Activity view (Show Activity…, or Settings, Activity) and Tools menu **Show Log File in Finder** show the start sequence. Attach the relevant lines instead of describing them. Flash buttons sometimes want a short press; an earlier note records that automated clicks needed a hold of about 80 to 100 milliseconds.

### Comparing the saved farm (L9)

The save is `saves/<farmer id>.save.json` under your data folder. Copy it first, because the app keeps writing:

```sh
cp "$QA/saves/<farmer id>.save.json" "$HOME/qa-evidence/before.json"
```

After the restart copy it again to `after.json`, then:

```sh save-compare
BEFORE="${BEFORE:?set BEFORE to the earlier copy}"; AFTER="${AFTER:?set AFTER to the later copy}"
python3 - "$BEFORE" "$AFTER" <<'PY'
import json, sys
MISSING = object()
def leaves(value, path=""):
    if isinstance(value, dict):
        for key in sorted(value):
            yield from leaves(value[key], path + "/" + str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from leaves(item, path + "[" + str(index) + "]")
    else:
        yield path, value
with open(sys.argv[1]) as first, open(sys.argv[2]) as second:
    before, after = dict(leaves(json.load(first))), dict(leaves(json.load(second)))
changed = sorted(key for key in before.keys() | after.keys() if before.get(key, MISSING) != after.get(key, MISSING))
if not changed:
    print("identical: %d values compared" % len(before))
    raise SystemExit(0)
print("%d differences (first 40):" % len(changed))
for key in changed[:40]:
    print("  %s: %r -> %r" % (key, before.get(key, "<absent>"), after.get(key, "<absent>")))
raise SystemExit(1)
PY
```

The earlier receipts recorded the world records, plot clocks, economy and inventories as identical across real restarts, so identical is the expectation. If anything differs, record each difference. Explain it or mark L9 FAIL. A reordered list shows up as many differences; say so rather than ignoring it. This compares two files and says nothing about what the game did in between.

## The three fresh visuals (N05 to N07)

After a real restart, open the farm so the game loads a **new document**, not a reload of the old one. Record that it reached a working farm, using the Activity lines or log lines for the start. Then screenshot the settled scene and HUD and compare balances and plots with what you recorded before the restart. Do this for Home, Mystical Groves and the world you chose for N07.

## Optional: the repository's Home harvest harness

`run-full-game-smoke.sh` automates one starter-crop harvest and its reload on a Home fixture. It needs a server already running on `127.0.0.1:5501` whose `/health` shows the same `wrapper_token` you pass (the server takes it from `FARMVILLAGE_INSTANCE_TOKEN`), a data folder inside this repository's `LocalData` or `macOS/.build`, and click steps that you append to `actions.json` while it waits. Its window ignores your real mouse by design. A search found no script in the repository that creates that fixture, and `session_a_farming_fixture.py` was written for a browser fixture, so whether it applies here is unclear. It was **not run** while this page was written. It covers none of N01 to N07.

## If something fails or locks

- Record the world, the step and the exact message or screenshot as FAIL. Record a lock as UNRUN.
- This release starts clean, so there is no old farm to restore. Make a new synthetic farm and try again.
- Do not hand-edit saves, do not shorten timers and do not count God Barn changes as earned.
- Record what a failure shows about the game separately from what it shows about your Mac.

## After the run

1. Fill the ledger. Keep screenshots and notes outside the repository.
2. Update [`WORLD_READINESS.md`](../WORLD_READINESS.md) and [`ACCEPTANCE.md`](../ACCEPTANCE.md) only for items you marked PASS, naming the source commit and the app's runtime hashes. Leave every other item UNRUN.
3. Do not generalize. One farm per world shows nothing about other farms, Intel hardware, long sessions or distribution signing.

## Results ledger

Copy this block, and one loop block per world, and fill them in.

```text
Host: ____________________  Date: ____________  Operator: ____________
Source commit: ____________  App runtime hashes: ____________________
N01 __  N02 __  N03 __  N04 __  N05 __  N06 __  N07 __
N07 world chosen and why: ______________________________________
Locked or interrupted (world, time): _________________________
FAIL details (world, step, exact message):
UNRUN items and why:

Loop block (one per world)
World: ________  Farm name/id: ____________  Reached by: earned / setup (list changes)
L1 __ L2 __ L3 __ L4 __ L5 __ L6 __ L7 __ L8 __ L9 __
Crop, prices, timers observed:
Process ids before / after restart:
Save comparison output:
Screenshots (files, outside the repo):
```
