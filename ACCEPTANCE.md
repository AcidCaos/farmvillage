# Historical validation — sixteen-world alpha

**Record scope: 25 October 2026, using prepared resources.** These results do not establish that a fresh clone can acquire its resources and play. See [current development status](HANDOVER_STATUS.md) for the unfinished public setup work.

The active targets are the native macOS desktop wrapper and the browser game on Ubuntu/Linux. iPad/iOS is abandoned. Enchanted Glen (`glen`) and Holiday Lights (`hlights`) are retired, with no active unlock/travel offers. This is a fresh-start release, with no old farms, snapshots, history, environments or authentication state shipped.

The reviewed source is FarmVillage `62809de497404588f133e38740242864717af0c0` and God Barn `31245bb8bc2848908667ae0cf95af8244531bff5`. Game behavior is frozen at `4958c48`; later commits add unbundled active-test tooling/goldens and two browser-neutral console strings. The source manifest records exact outgoing bytes and explicit cosmetic/resource exclusions.

## What passed

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
