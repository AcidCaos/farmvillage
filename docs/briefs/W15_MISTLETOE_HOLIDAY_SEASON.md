# Brief W15: Mistletoe Lane for the holiday season

A pick-up-cold assignment for one contributor. It follows lane **W15 Mistletoe Lane** in [Wave 3](<../../Wave 3.md>) and uses that file's assignment rules. Read [AGENTS.md](../../AGENTS.md), [world readiness](../../WORLD_READINESS.md) and [current acceptance](../../ACCEPTANCE.md) first.

**Goal.** Make Mistletoe Lane (`htown`), the project's active Christmas-themed world, as ready as honestly possible for the holiday season, without inventing any price, timer, reward or feature. "Ready" here means a player can farm, decorate, store, craft and travel there, and every limit is disclosed.

**Not a goal.** Reactivating Holiday Lights, opening Yuletide or Winter Wonderland, adding travel to any retired world, or promising anything the original data does not support.

## Which Christmas world?

Several worlds in the catalogue have a winter or holiday flavor. Only one is a safe, active target.

| World | State in the repo | What it would take |
| --- | --- | --- |
| **Mistletoe Lane** (`htown`) | **Active.** Basic farming cycle accepted; 17 Patisserie recipes implemented; one recipe and skill levels to 3 have browser acceptance. | This brief. |
| Holiday Lights (`hlights`) | **Retired by the owner on 25 October 2026.** Its record shows a bounded ordinary activation and a failed later gift and loading follow-up. | An explicit owner instruction to reactivate, plus its own acceptance. Not part of this brief. |
| Yuletide (`yuletide`) | Never activated. Its experiment gate is served closed (`fv_xyt_master_for_all = 0`). | Owner decision and recovery work. A closed gate must not be bypassed. |
| Winter Wonderland (`winterwonderland`) | Never activated. General access ended on 18 February 2012; a new unlock would bypass that. | Owner decision and recovery work. |

If you want a different world than Mistletoe Lane, stop and ask the owner. Do not edit an allowlist.

## What is already true (verify before relying on it)

Facts from the source at the time of writing; re-audit against your baseline.

- Mistletoe admits only its original crafting cottage: `xhdcraftingcottage` / `xhdcrafttype` / `CraftingCottageBuilding`, code `7la`. Tier one is authored at 100,000 coins, 1,000 buy XP and level 15. Tiers two and three are authored at 80 cash. No later tier is guessed. See `FarmVillage/macOS/Documentation/Worlds/SESSION_B_HTOWN_CRAFTING_2026-10-24.md`.
- The 17 Patisserie recipe codes are in `FarmVillage/crafting.py`, `REGIONAL_RECIPES["xhdcrafttype"]`: `8WE 8WC 8WA ccL 8WG 8Wy 8Ww 8Ws 8Wo 8Wm caC 8Wk 8Wi 8Wg 8Wu 8We 8Wq`. Recipe availability dates are enforced by `_guard_recipe_dates`.
- World wiring is in `FarmVillage/themed_worlds.py` (`SPECS["htown"]`, storage id -15, `localThemeChoice`). The theme and starter are **local policy and are disclosed as such**; keep that disclosure.
- The catalogue audit counts 193 associated records for Mistletoe: 61 inside the current themed admission contract and 132 outside it. The 132 are **not** a broken-item count.
- Relevant tests: `FarmVillage/macOS/Tests/test_htown_crafting_admission.py`, `test_crafting_expansion.py`, `test_themed_worlds.py`.

**Answered from public originals (27 October 2026)** by `tools/review-originals.py`; see the [no-Mac review guide](ASSET_REVIEW_NO_MAC.md). The 17 recipes in the original data are exactly the 17 the repo admits. **None of the 17 recipes, and none of the 47 finished goods and ingredient bushels they use, carries a date window, and none is deprecated.** So the recipes are not a calendar problem; the work is acceptance testing. **Still unknown from public source:** which recipe is the one with browser acceptance.

## Steps

Each step is a separate small change with its own evidence. Return a shared-engine patch separately from any Mistletoe admission.

0. **Research table. Done.** Run `tools/review-originals.py` and read `mistletoe_patisserie.csv`: name, code, skill and recipe level, ingredients, cook minutes, rush cost, yield and dates for all 17. It needs no private inputs. Result: no date windows, so the season is realistic for the recipes. Keep the CSV out of the repository.
1. **Accept the other 16 recipes one at a time.** On a newly created synthetic farm: fund the cottage as setup only, craft one recipe, check the ingredients consumed, the original timer, the yield, the claim, then reload and restart. Setup funding is not earned progress. Record PASS, FAIL or UNRUN per recipe. Do not promote one recipe to all.
2. **Skill tiers above 3.** Only where the original data supplies the cost and effect. If it does not, record the missing artifact by name as `RECOVERY_BLOCKED`.
3. **Classify the 132 outside records.** Give each one primary disposition from the table in Wave 3 section 5. Changing admission only to shrink the number is not a valid goal.
4. **Native and browser loop for Mistletoe.** The native Mistletoe crop loop is one of the four listed UNRUN. Run it, with the settled scene judged separately from an early loading frame.
5. **Seasonal decor, candidates only.** On 27 October 2026 the maintainer approved *exploring* ordinary decorations from retired worlds for Mistletoe. Nothing is admitted without per-item approval from the world owner and the integration reviewer. Prices follow the item's own recovered price, and a deterministic derived price only where none exists. A date-window shelf (26 November 2026 to 6 January 2027, server clock) is approved but built second, after the always-available shelf is accepted. See [the roster and repurposing brief](WORLD_ROSTER_AND_REPURPOSING.md) for the decisions and the things never to do.

## Out of scope and why

Holiday Square, Cheer, treasures and growth are open or recovery-blocked. Do not build placeholders that look finished. No unsupported animal or tree claims. No score or Beat rules copied from another world.

## Done means

- Each accepted recipe has its own evidence: baseline commit, item code, world, actions taken, accounting, timers, reload and restart, and refusal behavior.
- Native macOS, browser and Ubuntu are reported separately. Ubuntu stays UNRUN unless you ran it.
- `WORLD_READINESS.md` is updated only for what you actually proved, with remaining limits stated.
- No private saves, raw traffic or evidence in the repository.

There is no hour estimate. The season is a reason to choose a small honest slice, not to skip a gate.
