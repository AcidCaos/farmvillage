> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../ACCEPTANCE.md), [current world scope](../../../WORLD_READINESS.md) and [the continuation backlog](<../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Quest world score, world currency and content licenses

Implemented on 2026-10-24. Server/unit and signed-AMF checks are separate from
browser acceptance; this document does not claim browser verification.

`quests.py` now preserves reward `unit` and `licenseType` when decoding the
archive (cache schema 6), mirrors `world_score`, `world_currency` and
`world_content_license` rewards, and derives `reachWorldScoreLevel` tasks from
the saved level. `world_scores.py` reads the original score and currency data.

## Recovered client contract

Inspected a scratch copy of `embeds/Flash/v855097-855094/FarmGame.swf` with
`macOS/Scripts/client-inspection/abcdis.py`; the source SWF was not changed.

- `UserRewardUtil.grantUserReward` method 7125, source lines 348–353 calls
  `Global.player.addWorldScore(reward.unit, parseInt(reward.value), true)`.
  The reward's `quantity` is not a score multiplier. Currency source lines
  318–330 apply the configured inflow tuning and call `updateWorldCurrency`.
- `Player.addWorldScore` method 3867, source lines 1958–2005 requires the
  score's configured prerequisite, creates `{score: 0, level: 1}` if absent,
  adds the amount, applies every newly crossed level's rewards, and queues
  `TWorldScoreLevelUp`. It does not lower an imported saved level.
- `LevelData.applyRewards` method 15467 passes that level's original rewards
  to `UserRewardUtil`. `display_only` is a presentation record. In particular,
  older ladders such as Candy and Spook have display-only prize rows; newer
  ladders often pair these with a separate `item_grant`. Never convert a
  display-only row into another item award.
- `TWorldScoreLevelUp.perform` method 15370 sends
  `UserService.updateWorldScoreLevelUp(unit)` with one argument. Its
  `onComplete` method 15371 consumes no payload. This callback acknowledges
  the report and awards nothing: it can precede the quest completion in the
  same batch, and retries cannot double-grant points, items or currency.
- `WorldScoreSettingsManager.getLevelForScore` method 4926 scans to level
  999. Explicit thresholds are used first. `LevelData.getCalculatedLevelData`
  method 15460 calculates later thresholds with AS3 rounding: Spook uses
  `10.006*n² - 48.818*n + 16.945`; other tracks use
  `19.443*n² - 43.183*n - 175.87`. Calculated levels use `defaultLevel` rewards.
- `Player.getWorldLevel` method 3869 returns the saved level or -1 when
  absent. The corresponding derived quest task does not create a score.
- `Player.updateWorldCurrency` method 3862 updates
  `userInfo.player.worldCurrencies[unit].total`, retaining other record fields.
  `Player.loadObject` method 3780 reads the same map on reload.
- `WorldManager.addWorldContentLicense` method 2737 stores
  `unlockedWorldContentLicenses[world][licenseType] = true`.
  `WorldManager.onUserInit` method 2720 reads that map from `userInfo`.
  A license does not itself add a travel destination, starter farm or storage.

## Data and boundaries

The archived `worldScore.amf.gz` has 64 groups and **65 score units** because
Avalon contains two units. The quest archive contains 1,238 world-score reward
rows, 407 world-score-level tasks, two coconut currency rewards, and 126
world-content-license rows (63 Home licenses plus 63 other-world licenses).

Score prerequisites use the original CMS level/experiment predicates and the
variants served in `templates/play.html`. A disabled score stays unchanged,
matching the client. Season/feature-option predicates are left closed. This
does not enable dormant worlds or restore points for harvests, purchases,
construction, expansions or other ordinary world actions.

The server mirrors base-rate rewards. Imported permanent gain buffs affecting
the reward are explicitly refused because that buff lifecycle is not restored.
Unknown units, malformed balances and unsupported score ladders also fail
visibly. Gateway savepoints roll those failures back, including earlier reward
rows and quest retirement. No client report can supply an amount or level.

`test_world_score_quests.py` covers original thresholds and calculated levels,
derived progress and reload, item-grant/display-only separation, experiment
gates, inflow tuning, license maps, imported-field preservation, and signed AMF
completion/callback ordering, retries, forged reports and rollback.
