# Scope M02 / F03: wiring the prerequisite evaluator

`FarmVillage/prereq_eval.py` is a pure, three-valued evaluator (YES, NO, UNKNOWN; only YES grants). It is tested, hardened against malformed input, and **called by nothing**. This document scopes the work of putting it to use without changing what any player experiences by accident.

Read first: the evaluator's docstring, `tools/test_prerequisite_dispositions.py` (the gap list G1 to G7 and the behavior of the four older forms, pinned), and lanes F03 and M02 in [Wave 3](<../../Wave 3.md>).

## The principle

Nothing here may change a quest, a score or an admission until the owner has decided the two open policies below. The work is built so that a difference between old and new behavior is *seen and classified* before it can reach a player.

## Where prerequisites are decided today

Call sites found by search at the time of writing. Re-audit against your baseline.

| Form | Callers | Notes |
| --- | --- | --- |
| `quests._prereq_met` | `quests.py` at two places (quest availability and quest hand-out) | Flat list of 11 types. `end_time` is deliberately always true. Decoding keeps only `type` and `value`. |
| `world_scores._prereq_met` | `world_scores.py`, one place (score gain gate) | One level of AND or OR, named references, cycle-safe. Only `level_min`, `experiment` and `prereq_check` are decided; everything else is false. |
| `themed_worlds._prereq_leaves` | `themed_worlds.py` for admission | Flattens XML to leaves and raises on cycles. It collects; it does not evaluate. |
| `maple_contracts.prerequisite_status` | **No non-test caller found** | Nested, named, cycle-safe. Verify before treating it as live. |

## Open decisions (the owner's, not an implementer's)

- **G5, the unknown policy.** The old forms disagree about an empty AND (false in one, true in another), an OR with one true and one unknown leaf, and a nested AND. The evaluator picks one consistent rule (empty group is UNKNOWN; OR is YES on any YES; AND is NO on any NO). Confirm it, or name the exceptions.
- **G6, the `end_time` policy.** `quests` never enforces `end_time`, on purpose: 2,159 of 3,233 quests have an expired window and enforcing it would hide nearly every quest. Others are inclusive. The evaluator takes `ignore_end_time` as an explicit per-caller argument. Keep it per caller.

## Phases

Each phase is a separate change with its own evidence. Phases 0 to 2 change no behavior.

**Phase 0: confirm the operator attribute.** `OPERATOR_ATTRIBUTE = "operator"` in the evaluator is a documented guess, because the original configuration is a private input. With the private inputs imported, list the distinct attribute names that appear on prerequisite nodes and how often. Fix the constant if the real name differs. The Cove level-10 `lte` that Wave 3 mentions was not found in tracked source, so confirm it here too. A wrong guess fails safe (those nodes are UNKNOWN), but the point is to know.

**Phase 1: lossless decoding (G4).** `quests._decode_quests` keeps only `type` and `value` of each prerequisite, so authored attributes are lost before any evaluator can see them. Keep every attribute, and raise `CACHE_VERSION` (currently 7) so stale caches rebuild. `_prereq_met` keeps reading only `type` and `value`, so quest behavior is unchanged. Test the cache invalidation.

**Phase 2: shadow comparison.** In a private-data test, evaluate every real prerequisite tree with the old form and with `prereq_eval`, and write a disagreement table sorted by cause (G5, G6, unsupported type, unknown attribute). No production code calls the evaluator yet. Without private inputs the test reports UNRUN; it must not pass vacuously.

**Phase 3: a facts builder.** One function that turns a save into the evaluator's `facts` mapping: level, coins, cash, account age in days, current world, completed quests, seen flags, owned and placed codes, experiments, EOS variants and server time. It reads the save and mutates nothing.

The time fact needs care. The evaluator expects a **naive datetime in the original server's wall clock**. `quests._quest_time_to_timestamp` converts a wall-clock string to epoch seconds by adding `globalServerUTCOffsetHours` (default 4) plus one hour. The builder must apply the inverse. Prove it with a boundary test: for dates just before, at and after a `start_time` and an `end_time`, the old check and the new check must agree.

**Phase 4: migrate one consumer at a time**, smallest blast radius first, with the shadow table as the guard:

1. `world_scores` (one call site, narrow set of types).
2. Anything that adopts `maple_contracts.prerequisite_status`, only if a real caller exists.
3. `quests` last: two call sites, the largest data set and the `end_time` policy.

For each: switch, run the affected suites, rerun the shadow table, then play the affected path on a newly created synthetic farm. Setup funding is not earned progress.

## What counts as done

- The shadow table shows zero unexplained disagreements. Every explained one has an owner decision recorded.
- `tools/test_prerequisite_dispositions.py` is updated so each closed gap is reflected, since closing a gap is meant to make its pin fail.
- PASS, FAIL and UNRUN are reported per target. Native, browser and Ubuntu are not conflated.
- Nothing activates a quest, world or campaign.

There is no hour estimate. Phases 0 and 2 need the private inputs. Phases 1 and 3 can be built and unit-tested with synthetic data, but checking them against the real quest archive needs the private inputs too.
