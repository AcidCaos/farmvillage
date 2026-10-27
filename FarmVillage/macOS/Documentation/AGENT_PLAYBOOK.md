> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../ACCEPTANCE.md), [current world scope](../../../WORLD_READINESS.md) and [the continuation backlog](<../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Agent playbook: themed worlds, browser acceptance and client inspection

Updated 2026-10-23. Read HANDOFF.md (`HANDOFF.md`; external/private historical reference, not included in this source export) for the current activation and
validation checkpoint and ../../BROWSER_ACCEPTANCE_2026-10-23.md (`../../BROWSER_ACCEPTANCE_2026-10-23.md`; external/private historical reference, not included in this source export)
for the evidence index.

## Ground rules (from the project owner)

- Follow the original game. Recover prices, timers, access rules and wire contracts from
  preserved data or the served client. Document deliberate deviations, including converted
  world currencies and the 15-coin plow in every themed world.
- Never fake success. Unsupported work must produce a visible rejection rather than vanish
  on reload. Charge once, apply atomically, make retries free and preserve durable state.
- Unit tests are not browser acceptance. Complete the real-client checks before source activation.
- Landscape only. Do not test portrait/phone widths.
- Never reset or advance Bakery timers or overwrite newer saves with backups.
- Never push or deploy without the owner's approval.
- **Ignore the retired port-45358 fixture.** The owner explicitly excluded it. Do not open,
  query, restart or modify it; its old log is not evidence for new acceptance.

## 1. Expose and accept a themed world

Shared code: `themed_worlds.py`, `world_currency_conversion.py`, hooks in
`world_travel.supported_worlds()`, `creative_worlds` creation/guards/candidates,
`server.py` farm visits/names and `instant_growth.py`. The dynamic supported-world
hooks are already installed. Rules/deviations live in `Worlds/THEMED_WORLDS.md` and
`Worlds/WORLD_CURRENCY_CONVERSION.md`.

1. Pick a world with a recovered scene-layout contract, a unique storage ID and compatible
   access rules. The current ordinary-farm path has a horizon plus 20 background variants.
   The fresh asset audit (`Worlds/ASSET_AVAILABILITY_2026-10-23.md`; external/private historical reference, not included in this source export) finds 23 complete ordinary
   scenes, 44 later worlds with fixed/large background assets, and three feature maps. The
   44 need layout assessment; their background art is not absent. Toyland/Sleepy Hollow
   need distinct experiment adapters. Currency worlds need a complete purchase conversion path.
2. Add/check its spec against `gameSettings` expansion records and `yimf.xml.gz`. Friendly
   names can be recovered from `en_US.swf`; preserve the owner's display-name decisions.
3. Run `test_themed_worlds.py`: its cases are generated for every SPECS entry. Verify free
   creation, travel/reload, allow-list, original classes, bounds, dates, balances, plow cost,
   rejection byte identity and incoming specialized-plot rejection.
4. Activate it in an isolated Runtime copy first. Copy current modules and both launch
   templates, preserve the synthetic save and restart the correct fixture. Source activation
   waits for browser acceptance.
5. Complete this browser sequence, reading the saved JSON after every material action:
   - `/farms`: Add farm · Free, unchanged balances, and repeat unlock without a new charge.
   - Visit: rendered world theme/HUD and the disclosed empty 50×50 starter.
   - Plow Tool: −15 coins and +1 XP. Plant a local seed: exactly one catalog charge and a
     server-owned plant clock. Market search and clicking a plowed plot to open Seeds work.
     For browser category tabs use a held click (`durationMs: 100`); Candy Seeds and Trees
     were verified with that input.
   - Apply Instant Grow from the crop's context: −4 FC for one growing ordinary crop,
     `grown` on the server, no airplane placement. Harvest its catalog coin yield and confirm
     `fallow`. Separate any ribbon/quest award from the crop's own yield.
   - Buy/place a local decoration using its actual catalog class, close Market to flush its
     held batch, then move it. Reload and inspect its position. Sell and verify the catalog
     credit and object removal. Storage requires an appropriate storage building; a local
     client warning alone is not proof of a server rejection.
   - Travel out and return, then reload. Confirm the crop, world and ledgers survive.
6. Save an acceptance JSON and screenshots outside the repository. Only then add its key to
   source `ACTIVE_WORLDS`. Do not label a partial run as accepted.

Rainforest, Mediterranean, Storybook, Candy, Oasis and Oz are browser accepted and active
in source. Candy passed the full sequence after its original plane was fixed, including
first-action-after-reload Instant Grow, decoration reload/sale and Home travel. The final
full suite passed 895 tests; the final all-six activation regression passed 144. Bifrost
remains unchanged. See HANDOFF and the browser evidence index for exact scope.

### Browser-discovered contracts that tests must preserve

- Decorations retain their catalog class (for example `RotateableDecoration`), not an
  invented per-type replacement.
- Re-plowing a harvested plot may retain its old item and a zero clock.
- The first world action after load can append `{firstWA: true}` to the options array.
- Temporary Instant Grow planes are chosen by
  `worldSettings.xml.gz` → `world/hudSkinConfig/instantGrowItemVisual`:

  | World | Original visual |
  | --- | --- |
  | Rainforest | `xrfbiplane` |
  | Mediterranean | `xmd_michelangelosornithopter` |
  | Storybook | `xsb_fairylandbiplane` |
  | Candy | `candybiplane` |
  | Oasis | `xoa_egyptianeaglebiplane` |
  | Oz | `xoz_emeraldbiplane` |

  Candy's visual has no World requirement; the narrow exception checks Candy, exact item,
  `fv_candy` and no other requirements. Never generalize this into an arbitrary-plane or
  licence bypass. Two new Instant Grow tests cover all six real carriers over AMF, 30
  foreign-world rejections, a single charge, retries/reload and licence negatives.

## 2. Disposable QA environments and restart procedure

| Root | Port | Cookie name |
| --- | --- | --- |
| `/private/tmp/fv-worlds-burke-20261023` | 45461 | `fv_qa_45461` |
| `/private/tmp/fv-worlds-burke-oasis-20261023` | 45463 | `fv_qa_45463` |

Both have `.disposable-features-fixture`, independent data and synthetic saves. Cookie
names must differ: browser cookies are host-scoped, so different ports alone do not
isolate Flask sessions. Each save must have only one live browser runtime. Parallel
agents use independent fixtures, never a shared player.

- Read `fixture.json`, verify the PID belongs to that fixture's `serve_fixture.py`, and
  snapshot the current synthetic save to a new evidence path. Never restore over newer work.
- Stop only that verified process. Launch `serve_fixture.py` with the existing runtime
  venv and `-B -u`/`PYTHONUNBUFFERED=1`, from its fixture root, into a new log. Binding a
  loopback server may require the normal sandbox escalation. Do not disable isolation.
- Wait for both READY and Running on; record the live PID/current log. Flask caches
  templates, so template updates require a restart.
- Use `http://127.0.0.1:<port>/__qa/start` to establish that fixture's session; `/farms`
  is the picker. Inspect `data/saves/<uid>.save.json` and the current server log directly.
- Preserve all accepted progress on restart. A client can display optimistic balances
  before a failed command; the saved JSON is authoritative.

The retired 45358 fixture is intentionally absent from restart instructions.

## 3. Inspection tools — `macOS/Scripts/client-inspection/`

- **abcdis.py:** read-only AVM2 disassembler. Work on a scratch copy of the exact served
  client because its parse cache is written beside the SWF. `find`, `dis` and `strings`
  expose source `debugline` values, literals, flags and wire calls. It recovered Market
  input, Instant Grow, Bakery claims/rushes, Hollow fields, currency exchange and travel.
- **evalconfig.py:** evaluates `FarmConfig.swf` into a scratch pickle for Market/type indexes.
- **Served catalog:** `<data>/cache/client-items-opt.json` contains
  `payload = base64(zlib(AMF3))`; decode with the venv's `pyamf.amf3.Decoder` and read
  `settings.items.item`. The server's source catalog cache stores the same list under
  `data.settings.items.item`. There are 111,206 entries. Inspect market/cost/cash, requirement
  classes, dates and catalog class; do not infer a price from display text.
- **World data:** `cove_rules._xml` reads zlib XML. `gameSettings.xml.gz` supplies expansion
  contracts; CMS supplies farming settings; `yimf.xml.gz` supplies themes; `worldSettings.xml.gz`
  supplies HUDs and original Instant Grow visuals.
- **Assets:** resolve logical names through the AMF assethash manifests before checking
  nonempty hashed files under LocalData/assets. Original-name filesystem searches are unreliable.
- **Telemetry:** server `[+] Stats:` rows show actual UI branches (`click_category`,
  `view_market`, world name). They are batched and may arrive late. Material actions must
  also have the expected service call and save transition.
- **Ruffle diagnostics:** use the browser's supported tools to apply logLevel warn for one
  disposable page load. Do not alter product files just to increase diagnostic logging.
- **Client A/B:** serve scratch variants from a dedicated QA embeds folder and select that
  URL in the disposable page. Preserve the normal client and remove QA variants afterwards.
- **Flags:** both `play.html` and `ruffle.html` must agree. The original paged travel window
  uses 2/0/1 for travel dialog/sorting preference/Sasha. Base asset supports slots1–4 and
  paging; V4 supports only slots4. See [TRAVEL_WINDOW_RECOVERY.md](TRAVEL_WINDOW_RECOVERY.md).
  Harvest & Replant stays hidden (`fv_instagrow_autoharvestreplant=0`) while unsupported.

## 4. Findings and remaining work

### Save/rejection behavior — completed

Each AMF call now has a savepoint. A rejected action restores only the farms and pending
writes it touched; valid calls in the same batch remain durable. Structural validation and
strict JSON serialization precede savepoint release. Unexpected/encoding/disk failures
still roll back the enclosing transaction. Command rejection is HTTP 200 with outer
errorType 0 and per-call errorType 29, preserving the original visible reload-error flow.
Malformed envelopes remain HTTP 400. See [AMF_BATCH_ISOLATION.md](AMF_BATCH_ISOLATION.md).

Candy's pre-fix real plane rejection showed that dialog. Server cash stayed 578/crop planted;
client 574 was optimistic. The final validation review passed 47 tests. The browser proof
shows visible rejection; the mixed-batch unit/wire cases prove neighboring accepted calls
are retained. These are distinct claims.

### Market category input — test interaction corrected

Candy's actual Market loaded Trees and then Seeds with browser clicks held for 100 ms;
Trees showed 74 pages and Seeds 121 pages/subtabs, with the selected category visible.
Use the documented `tab.click([x, y], {durationMs: 100})` input and inspect fresh state.
Both checks used the unchanged product client. This explains the prior automation symptom
for these categories; it does not claim individual acceptance of every Market category.

The successful native harness likewise moves first and holds mouse-down for 80 ms before
mouse-up. FarmTabButton changes its displayed children during those events, but no deeper
Ruffle mechanism is claimed without further evidence. No SWF fix is needed. Search remains
available. Parent evidence: `world-acceptance/market-trees-held-click.png`,
`market-seeds-held-click.png` and `market-input-review.json`. The 2026-10-22 A/B diagnosis
is historical; do not reopen its retired fixture.

### Original features still fenced

The client asks for roughly 45 all-access world unlocks on load. Handle only recovered,
accepted worlds. Unsupported actions (paint, alternative graphics, upgrades, slop, truffles,
grow-up, deprecation, withering and others) remain explicit rejections until their real
price/credit models are recovered; consult `CLIENT_ACTION_AUDIT.md`.

Player-facing gaps include organic fertilizer, irrigation, recipe bundles, sheep-pen free
patterns and growable contests. Other recurring unhandled services include lonely-animal
friend sets, leaderboards, automated messages and anniversary gifts. Do not restore a
feature by silently returning OK.

### World limits

- Every themed farm stays 50×50: original added construction-state objects (37 per world,
  widths 58 and above) are recorded but not restored.
- Asia/Hawaii: recovered rate 5 FC : 5000 jade/coconuts, still dormant. Converted served
  prices and authoritative server charges must be wired together; plows stay 15 coins.
- Toyland/Sleepy Hollow: support their distinct experiment names before considering activation.
- hlights/fforest have a storage ID collision. Haunted Hollow also needs placement rebasing
  on growth. Winter Wonderland's expired access period remains an owner decision.

### Release

No Bifrost deployment or GitHub push has happened. Publication scope and the separate
history/art-filtered candidate workflow are in GITHUB_PUBLICATION.md (`GITHUB_PUBLICATION.md`; external/private historical reference, not included in this source export).
Authenticate the owner-confirmed jannsenburke account and obtain approval before publishing.
The older iOS build/40-test checkpoint still has an unresolved NativeRuffle lock URL.
