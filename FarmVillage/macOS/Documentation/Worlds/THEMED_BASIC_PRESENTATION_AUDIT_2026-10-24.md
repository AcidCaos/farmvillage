> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../../ACCEPTANCE.md), [current world scope](../../../../WORLD_READINESS.md) and [the continuation backlog](<../../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Themed basic-mode presentation audit — 24 October 2026

Fresh-browser Toy Town acceptance exposed additional invitations. The derived
configuration corrections below are implemented; browser acceptance is separate.
The six previously accepted themed worlds have the same basic-mode limits.

The original client optimistically celebrates purchase of Toy Town `xtlfarm14`
(Play Patch 14x14, 10,000 coins) and awards local world score before receiving the
server's refusal. The server retained gold/cash/sizes unchanged. Larger land
expansions in these worlds are deliberately unsupported because their original
added objects and feature/score economies are not restored.

A derived item-catalog gate is narrower than a new generic purchase byte patch.
`ChangeFarmItem.isVisible`11370 ultimately calls its superclass isVisible at638;
`FarmItem.isVisible`6382 checks buyable. The current prepared Market name filter
also discards conclusively nonbuyable, nonlicensed/nongiftable offers without
sale/cash companions. A bounded projection should identify original
change_farm/expand_farm rows for the exact 11 SPECS worlds and their original 58+
expansions, validate associated added-object records and leave the raw catalog
unchanged. The implemented pure predicate closes 408 unique records; an initial 417 count
double-counted 9 Fforest cash records whose World requirement is repeated. All 11
base 50 records remain. `client_catalog` closes only derived buyable flags and
binds the land policy digest into both memory and disk cache identity.

The client's world score is separately optimistic. `Player.addWorldScore`3867
checks `WorldScoreSettingsManager.isEnabled`4940 and creates a missing saved track
when configuration enables it. Omitting `unlock_world_score` from the server's
all-access result alone does not stop local farming/instant-grow score, level
rewards or level-up popups. Toy Town was observed awarding +1 for plow, +4 for
Instant Grow, +50 for the refused expansion and showing a local level 3 Fuel reward.
No such track was stored by the server.

The source configuration exposes narrower hooks than a global score byte patch:

- `gameSettings.xml` expansion attributes `score`/`score2` feed
  `WorldManager.setCurrentWorldType`2649. Missing values set current score IDs to
  empty strings. `HUDSkin.applyWorldScoreMeter`29690 then skips the score meter;
  `WorldScoreManager.onTransactionAdded`8937 skips that world's task list.
- `WorldScoreManager`8937 always processes global transaction tasks, even with
  an empty current score ID. The implemented AMF projection removes only 37
  global task rows rewarding these 11 units:15category-purchase,10category-plant
  and 12 Htown mastery tasks. Every unit definition, level and authored quest
  reward remains identical, preserving trusted Home quest score rewards.
- `scoreFile` and all unit tracks remain unchanged. Ordinary basic items across
  the 11 current admission sets contain no direct or nested score writer fields;
  the actual derived catalog was exhaustively checked. Home quests continue
  addressing their original unit IDs directly.

All 11 original BeatTown invitation experiment gates are served as 0 by the
parent: Australia originally requires variant 1; the other 10 require 2. Their
master/all-access gates remain enabled for basic farming. NewGoals is shared
`QuestQueuedIcon.attachArrow`23923; its actual quest identity must be established
before any gate is changed. This correction does not globally hide Home quests.

`themed_client_presentation.game_settings_payload(raw)` removes only the 11
expansion `score`/`score2` identifiers. `world_score_payload(raw)` removes only
the 37 global task rows. Both are static across profiles and independent of
`ACTIVE_WORLDS`, pin original source identities, return derived zlib payloads and
leave archive files untouched. The parent owns server routes and browser
acceptance. `beat_experiment_overrides()` validates all original CMS contracts;
static template zero values use those exact gates.

The review JSON and preserved bytecode evidence (`ThemedPresentationEvidence20261024/review.json`; external/private historical reference, not included in this source export) record original and projected hashes, exact units, task actions and cache policy.

Validation passed on 24 October:

- 40 focused projection, land, catalog and original Home quest-score/wire tests
  in 121.571 seconds.
- Two strengthened catalog checks in 33.874 seconds: exact 408 closures and 11
  unchanged base records, plus land-policy invalidation of memory and disk cache.
- Two route/bootstrap checks in 16.324 seconds: exact static payloads with
  no-store headers across anonymous/authenticated requests, unchanged player
  saves, and all 11 original Beat gates at zero in both launch templates.
- Scoped whitespace checks passed. The SWF body remains the separately reviewed
  `c5aaff1f2ef9d60d4d2606ecac81ad7190d3f120b1500fb6b4e1d98ea4bbf589`.

These are automated acceptance results; the parent records actual browser flows.
