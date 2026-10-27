# Historical validation — sixteen-world alpha

**Record scope: 25 October 2026, using prepared resources.** A later, separate QA of published `main` on 26 October 2026 is recorded in the next section; it does not replace or relabel the results below. These results do not establish that a fresh clone can acquire its resources and play. See [current development status](HANDOVER_STATUS.md) for the unfinished public setup work.

The active targets are the native macOS desktop wrapper and the browser game on Ubuntu/Linux. iPad/iOS is abandoned. Enchanted Glen (`glen`) and Holiday Lights (`hlights`) are retired, with no active unlock/travel offers. This is a fresh-start release, with no old farms, snapshots, history, environments or authentication state shipped.

The reviewed source is FarmVillage `62809de497404588f133e38740242864717af0c0` and God Barn `31245bb8bc2848908667ae0cf95af8244531bff5`. Game behavior is frozen at `4958c48`; later commits add unbundled active-test tooling/goldens and two browser-neutral console strings. The source manifest records exact outgoing bytes and explicit cosmetic/resource exclusions.

## Published main QA, 26 October 2026

An owner-run QA of public `main` **6961f41c0712843cf0687f841b7a63cdfb92a5aa** (tree `66d10d1b906cc2540f2f67344711c171d82d469f`), using an isolated clone of the published source and existing local game resources. Host: macOS 27.2, Apple Silicon (arm64), Xcode 27.1, Python 3.12.14. No production source fix, push or deployment happened during the QA. Raw evidence (saves, screenshots, logs, compiled products) stays private and is not part of this repository.

Counts belong to their own suites and overlap. Do not add them together. A bounded Home smoke does not qualify every feature or all sixteen worlds graphically.

| Check | Result | Executed scope |
| --- | --- | --- |
| Source integrity and documentation | PASS | 539 sealed files, Python and Bash syntax, 326 local Markdown targets |
| Source and synthetic suite | PASS | 356 tests, zero failures, errors or skips in one complete run |
| Full active game suite | PASS | 1,910 tests, zero failures, errors or skips, 1,017.698 seconds; 51 retired-only cases excluded and not counted |
| Complete God Barn suite | PASS | 306 tests, including the wordmark record test |
| Portable Linux fixtures | PASS on macOS | 47 tests with mocked service commands; not an Ubuntu result |
| Default prepared player | PASS | 1,843 approved inputs; strict 21-file runtime verification with no overrides |
| Native universal Release build | PASS | Unsigned arm64 and x86_64 executable, verified with `lipo` |
| Native app launch and Quit | PASS | Two idle instances with isolated data, normal Quit |
| Production RuntimeController | PASS | Start, Stop, restart with a new token, shutdown callback, port released |
| Native GameWebView, Home smoke | PASS (bounded) | Trusted canvas harvest (200 to 288 coins), reload, backend restart; the saved farm was byte-identical before login |
| Browser Home farming | PASS | A new Classic farm opened Ruffle directly; original-priced harvest, plow and plant, reload and restart. Soybean showed its original one-day timer |
| Prepared browser package | PASS on macOS | 1,902 sealed staged files; hosting adapter, command-line credential setup and browser sign-in |
| Integrated God Barn UI | PASS | Preview left the save unchanged; an explicit one-coin editor action created a snapshot that survived an adapter restart; undo restored every value; return to farm opened a fresh document |
| Actual Ubuntu, systemd and LAN | **UNRUN** | No Ubuntu host, real service or network deployment |

**Preserved failed invocation.** The first complete game-suite run supplied a global artwork override that conflicts with synthetic runtime fixtures: 1,910 run, 5 failures, 5 errors, every traceback an external-asset configuration mismatch. It is not counted as a pass. A fresh complete rerun without those overrides passed all 1,910. Source and prepared-input hashes were unchanged across the runs.

**Finding raised.** `FarmVillage/prereq_eval.py` treated a present but falsy `children` value (`0`, `False`, an empty string or mapping) as no children and could answer YES for a malformed node. The module is called by no gameplay, so no farm was affected. It was fixed in commit `1fdb2e6` (merged in PR #11) and is covered by unit tests only. The QA ran on `6961f41`, which predates that fix, and the fix has not been re-probed independently.

**Behavior note.** A browser farm created through the Classic form now opens `/ruffle.html` directly (commit `32cc8af`). Its test needs private game data, so it can only run in the private-data game suites, never in the source-only suite.

**Still UNRUN, not established by anything above:** actual Ubuntu, systemd and private-LAN hosting; a complete public-download and source-built Ruffle installation; all sixteen worlds graphically on this revision; native plowing, planting and new-crop natural maturity; long-session stability; Intel execution; signing and notarization. No legacy migration, recovery or Mediterranean restoration was undertaken.

## What passed on 25 October 2026

| Gate | Observed scope |
| --- | --- |
| Active/shared regressions | 1,909 passed, zero failures/errors/skips, 1,131.352 seconds, measured source stable. Exactly 51 retired-only cases (32 Glen/19 Holiday) are listed separately and are not counted as passes. |
| God Barn regression | 275 passed in its separate suite. |
| Portable/hosting regression | 95 passed in its separate suite. The final two console wording changes also passed the 16 credential/LAN cases. |
| Source-only checks | Separate asset-free suites: 47 Linux hosting fixtures, 16 storage/journal, 24 God Barn engine, 8 calendar, and 33 handoff/wizard cases. These overlap broader suites and are not summed into a grand total. |
| Guided clean installer | 18 synthetic tests passed, including managed-target wipe, fresh environment/authentication, art staged before an inside-target wipe, active-lock refusal, canonical path/symlink/source/system refusal, loaded-service identity and private-address selection. Executed on macOS with synthetic service/process fixtures. |
| HTTP/protocol | Sixteen worlds, 112 request/response pairs across two server generations, with current state/accounting checks. This is protocol evidence, separate from rendered UI. |
| Browser graphics | All sixteen current worlds have fresh scene/HUD evidence. One genuine current Mystical Groves core farming loop, process restart/fresh-document continuity, God Barn preview/+1 synthetic editor apply/new-session snapshot restore and returned scenes passed. This is not sixteen new browser core loops or acceptance of every original feature. |
| Native macOS | Twelve worlds passed genuine core loops, scene/HUD and mature-art checks through a private production-GameWebView/AppKit harness, not a substitute browser screenshot. Four remaining native loops are explicitly unrun below. Compilation/package checks include a universal Release build; this is not execution on Intel hardware. |
| Native restart integrity | All sixteen serialized world records, plot clocks, economy and inventories remained identical across real owned process restarts; the production world validator passed sixteen. Fresh visible native init/postInit and post-restart documents remain separate unrun checks. |
| Source/privacy/build inputs | Code-only manifest/publication verification passed. Matching private inputs imported and a 1,900-file private browser runtime staged successfully, with pinned player verification. The original committed starter template is retained; no QA funding or pre-unlocked world grants are shipped. |

Counts belong to their own suites. An optional workflow template is retained at `.github/source-checks.yml.example` for asset-free checks on an Ubuntu runner. It is disabled by default; remote CI execution is not established by this validation record.

## Explicit unrun boundaries

Native loops for **Oasis Gardens, Mistletoe Lane, Emerald Valley and Horseman's Hollow** were not completed because the macOS host session was locked. The ordinary login HTML was also hidden, and CoreGraphics reported the locked session. No lock bypass was attempted. These four are unrun native checks, not established world defects. The three final fresh post-restart native visual checks (Home, Groves and last world) are also unrun. Repeat those checks on an unlocked host before expanding acceptance.

Actual Ubuntu-host installation, managed-service operation and gameplay are **UNRUN**. Linux/LAN fixtures on a Mac are not an Ubuntu runtime pass. The private clean-install bundle is prepared; no live Bifrost deployment or destructive install was performed here. Long-session reliability across hardware and public distribution signing/notarization remain outside this bounded acceptance.

## Handoff-specific differences and preserved failures

The code-only browser wrappers replace one exact 852-byte inline notification-background PNG apiece with authored CSS gradients. Geometry, counter DOM and all script bytes remain unchanged. The canonical private bundle/app retains its original media; this outgoing-only exclusion is recorded in the source manifest.

A separate exported-source rehearsal ran all 1,909 cases with 1,908 passes and one missing authored CSV resource. The initial error report is preserved. The exact feature-invitation CSV was added to the export, and the affected case passed on retest. That initial run is not relabeled as a clean full exported pass. A redundant final rerun was canceled by the coordinator to prioritize graphics resources and is not acceptance evidence.

One browser QA process disappearance interrupted the tour. The same newly created QA farm was recovered through normal server restart, and the sixteen-scene tour plus stated fresh-state checks completed. No existing released farm was used. All QA balances/unlocks were setup only, not earned progress or shipped starter data.

## What the next contributor should do

1. Repeat the four remaining native loops and final restart/visual checks on an unlocked Mac.
2. When the owner chooses to install on Ubuntu, follow BIFROST_SETUP.md and START_HERE.sh exactly; verify fresh authentication, farm creation, normal save/reload and restart on that actual host.
3. Use WORLD_READINESS.md for per-world limits. Rendering/core-loop evidence does not restore every historical story, production system, treasure, terrain rule, reward or campaign.
4. Continue the explicit unfinished plan in [Wave 3.md](<Wave 3.md>). No iPad reactivation, retired-world reactivation, deployment or automatic agent dispatch is authorized by that plan.

This is a bounded alpha validation record. Complete restoration, long-session stability and actual Ubuntu installation remain open qualification work.
