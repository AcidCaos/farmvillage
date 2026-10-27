# Current clean-start release checks

The active release contains **16 worlds**, including **12 themed worlds**.
Enchanted Glen (`glen`) and Holiday Lights (`hlights`) were dropped by the owner.
Their original source contracts and historical test cases remain available for
future research; they are not active game or release-test targets.

After restoring the matching private inputs and installing `requirements.txt`,
use the source-owned release runner with Python 3.10+ and Node.js available:

```sh
WAVE2_GODBARN_ROOT=/absolute/path/to/GodBarn \
  python -I -B -W error::ResourceWarning \
  macOS/Scripts/run-active-release-regressions.py \
  --report /absolute/path/to/new-active-release-result.json
```

The companion source is normally the sibling `GodBarn/` folder. The runner
establishes temporary farm/cache paths before loading game modules. It does not
open the normal player profile, start a browser or install a service. Individual
regression fixtures may start their own disposable local processes/listeners.
A source export needs its private inputs restored before running this complete
suite; the separate source-only CI checks require no original game files.

For an inventory without running test bodies, add `--list-only`. Existing report
files are never overwritten. The reviewed current selection is **1,909 cases**;
**51 exact retired-only cases** are excluded and enumerated in every receipt
(32 Glen, 19 Holiday Lights). They are not passed, skipped or xfailed cases.
All shared and active-world cases in the same modules remain selected.

`retired-world-test-cases.json` names every exclusion and locks its four source
files. New cases are selected automatically unless explicitly reviewed into this
manifest. A missing case, a changed source lock, a changed active-world roster,
or a test-import error fails before execution. Review the manifest deliberately
when changing those files; do not suppress an active failure by adding it to the
retired list. The exit status is nonzero for an active failure or changed source
inputs during the run.

Raw `unittest discover` also exercises retained dropped-world play contracts and
is not the active-release acceptance command. Earlier raw-discovery failures are
kept separately. This scope change does not remove a current-world failure or
claim that every original feature has been restored.

Receipts distinguish macOS, Linux and an actual Ubuntu distribution. Running
Linux/LAN adapter fixtures on a Mac is never an Ubuntu deployment/runtime pass.
Fresh farm creation, ordinary save/reload, authentication and restart still matter
for the clean-start release. No old farms, player history or credentials are
preloaded into a release.
