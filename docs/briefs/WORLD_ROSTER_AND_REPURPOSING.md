# World roster and repurposing

What is playing, what could return, what stays closed, and some careful ideas for giving the closed worlds a second life. Read this when you forget which world is which, or when you want to propose something fun without breaking the rules.

**Boundary.** This document reactivates nothing. Enchanted Glen (`glen`) and Holiday Lights (`hlights`) were retired by the owner on 25 October 2026 and must keep no unlock, travel or supported-play offers. Only a new explicit instruction from the owner changes that. Everything under "Ideas" is a proposal that needs approval, not a plan of record.

Sources: `FarmVillage/macOS/Documentation/Worlds/THEMED_WORLDS.md`, [world readiness](../../WORLD_READINESS.md), and [Wave 3](<../../Wave 3.md>) sections 5 and 7. Counts below use each source's own denominator and must not be added together.

## The roster in five buckets

| Bucket | Worlds | State |
| --- | --- | --- |
| **A. Active (16)** | Home / October, English Countryside, Sunflower Meadows, Lighthouse Cove, Fields of El Dorado, Mediterranean Riviera, Fairytale Fields, Sweet Acres, Oasis Gardens, Emerald Valley, Toy Town, Horseman's Hollow, Australia, Mystical Groves, Mistletoe Lane, Atlantis | Playable. Five are the strongest (Home, England, Meadows, Cove, El Dorado); eleven are in documented basic mode. None is a complete recreation. |
| **B. Retired by the owner (2)** | `glen`, `hlights` | Source contracts are retained as research. Glen's record keeps a failed fallback sign artwork check. Holiday Lights' record keeps a failed later gift and loading follow-up. |
| **C. Dormant, with their own rule modules** | `hallow` (Haunted Hollow), `asia`, `hawaii` | Rules exist in source but were never accepted for play. Asia and Hawaii use world currencies; their conversion proposals are explicitly "not activation approval". Hawaii has one crafting cottage (`xhicraftingcottage`). Haunted Hollow is owned by a dormant track and "not wired here". |
| **D. Closed by a gate** | `yuletide`, `avalon`, `winterwonderland`, `space`, `village`, `angler`, `garden` | Yuletide: experiment served closed. Avalon: feature option and closed experiment. Winter Wonderland: general access ended on 18 February 2012, so a new unlock would bypass it. Space: no recovered expansion storage id. Village: no admitted basic items. Angler and Garden: no basic farm. |
| **E. Fixed or large scene layouts** | 44 worlds (43 earlier-listed keys plus `japan`) | Background art is recovered for all of them and the horizon for 42; `wildwest` and `treasuretides` lack the horizon. The original scene sizing, renderer and terrain contract must be recovered before any exposure. |

The full 70-world asset audit is a private historical reference and is not in this repository.

## Resurfaced, resurrectable, and not retrievable

- **Resurfaced.** Bucket A. These are playing today, with limits listed per world in [world readiness](../../WORLD_READINESS.md).
- **Could come back with work.** Bucket B needs an owner decision first, then its own acceptance. Bucket C has code but needs the same bounded browser cycle the active worlds received. Bucket E needs the scene contract recovered first.
- **Not retrievable right now.** Anything blocked by a *named missing artifact*, for example reward timing for Pantheon Isle, Daydream Island and the Unicorn Bridge owner fallback, the Port repeat-harvest loot table, shoreline and terrain masks, authentic populated starters, the missing horizon art for two worlds, and Space's storage id. Bucket D is different: those worlds are closed by their own original configuration, so opening them would override the original design and is an owner decision, not a recovery task.

"Not retrievable" means not with what the repository and its private inputs hold today. A newly found artifact can change a row.

## What already merges assets from closed worlds into stable ones

This exists today. `FarmVillage/heritage_pricing.py` makes ordinary items from catalogue-only worlds buyable on the Home Farm: **13,017 records considered, 4,721 derived overlays** (4,421 locked-world and 300 exclusive).

The rules, in short:

- Only ordinary item classes qualify, with no requirement other than a World entry and none of the blocking fields.
- A crop is admitted only when its whole Home loop works with existing server code: buy, plant, grow for its time, harvest.
- An item keeps its own recovered price and currency. A missing price is derived deterministically from the nearest priced sibling, so the market and the server always charge the same amount.
- Each World requirement is renamed to Home; date windows are removed for the overlay; crops keep their experiment gate.

Both retired worlds are in `RESERVED_WORLDS`, so their items are **not** rehomed today; they stay exactly as recovered. Mistletoe Lane, Fairytale Fields and the other active worlds are reserved for the same reason. Heritage handling "does not authorize restoring Glen or Holiday travel or enabling their special systems".

## Ideas, ranked from safest to most work

None of these exist. Each needs the approval route at the end.

1. **A Museum of Lost Worlds in God Barn. Declined on 27 October 2026; do not build.** It was a read-only exhibit for each closed world: its name, its original art, notable items, original prices, and why it is closed. Nothing to buy, place or travel to. It carries no gameplay risk. God Barn already builds item history and acquisition data in `GodBarn/encyclopedia.py`; whether a world chapter fits that pipeline is not verified here.
2. **A winter shelf in Mistletoe Lane.** Ordinary decorations from Holiday Lights, offered in the active Christmas world. Wave 3 records **591 Holiday-associated raw records, of which 379 pass only an ordinary-class screen**. Those are candidates before any gate, not approved items. Reproduced on 27 October 2026 from the pinned originals with `tools/review-originals.py` ([guide](ASSET_REVIEW_NO_MAC.md)): applying the screen's gate fields leaves **287**, of which **52** are already Mistletoe Lane items (shared between the worlds), so about **235** would be new to it. Of the 287, 45 carry their own date window and 100 are marked not buyable. A reward-gated piece such as `beatholidaylightsstatue` stays reward-gated; note that it *passes* the screen, so the screen cannot replace reading the names.
3. **Fairy-tale decor from Glen.** Ordinary Glen-themed decorations for Fairytale Fields or Mystical Groves. Wave 3 records **172 Glen-associated raw records, of which 91 pass only the ordinary screen**, and names `cobblestonebridge` and `fairybed` as items to investigate. Applying the gate fields leaves **32**, none already in Fairytale Fields or Mystical Groves. `cobblestonebridge` and `fairybed` are **not** among them: each carries a gate field (`marketPrereqs`, `purchasePrereqs`).
4. **A seasonal window as disclosed local policy.** Show the winter shelf only in a holiday window, using the **server's clock** and never the player's device. The project already discloses local policy for the Mistletoe starter and theme, so this has a precedent. **Window approved on 27 October 2026:** it opens on Thanksgiving, 26 November 2026, and closes on 6 January 2027. Build the always-available shelf first, then add the window on top of it. The rules in "The window's safeguards" below apply.

## The window's safeguards

- **Server clock only.** Use the project's existing server-time convention for date windows (see `_guard_purchase_dates` in `FarmVillage/creative_worlds.py` and the offset handling in `quests._quest_time_to_timestamp`). A player's device clock must never open or close the shelf.
- **Closing hides new purchases only.** It must never remove, lock or alter anything a player already owns or has placed. A closed shelf is invisible, not destructive.
- **Boundaries are pinned by tests.** Follow the existing date-window boundary convention, and test the moment before opening, the opening, the last moment and the moment after closing.
- **No item is rushed to meet a date.** If the always-available shelf is not accepted by the opening date, the window simply does not open that year. An unaccepted item is never added to make the calendar.
- **Original gates still apply.** The window is in addition to each item's own date, level, prerequisite and terrain gates, never instead of them.

## Never, whichever idea you pick

- Do not move a retired world's special systems: buildings, gifts, community or reward mechanics.
- Do not turn a reward-gated item into a sale or a free grant.
- Do not use a new shelf to get around an item's original date, level, prerequisite, terrain or experiment gate. The one recorded exception is decision 7: the retired world's own master gate, waived for exactly the eight approved items.
- Do not merge or remap original item codes. Keep names and codes; reference art by its original identity.
- Do not reactivate travel to either retired world.
- Do not claim an item works because its name or picture suggests it does.

## How a proposal gets approved

Wave 3 section 5 sets the bar. A proposal delivers a machine-readable disposition table, a human summary, the candidate engine family, the exact blocked parameters and one accepted sample per proposed family. The world owner and the integration reviewer approve each new admission.

A sensible first slice: pick one destination (for example Mistletoe Lane), list its ordinary candidates with every original gate, run five of them through the destination's real purchase, placement, storage and reload path on a new synthetic farm, and report PASS, FAIL or UNRUN for each.

## Decisions recorded

Recorded on 27 October 2026 from the maintainer directing this work. Change them only on a new explicit instruction.

1. **Candidate exploration: yes.** Contributors may explore ordinary retired-world decor for Mistletoe Lane, Fairytale Fields and Mystical Groves, as **candidates only**. Nothing is admitted, sold or placed until the world owner and the integration reviewer approve it item by item (see the approval route above).
2. **Museum of Lost Worlds: no.** Do not build it.
3. **Prices: an item's own recovered price first.** Where an item has no recovered price, derive one by the deterministic heritage-style policy, never by hand. This follows what `heritage_pricing.py` already does. Confirmed by the maintainer on 27 October 2026.
4. **Christmas world for the coming season: Mistletoe Lane.** It is the only active holiday world with accepted play, so it is the best and most stable choice. This is not a reactivation of anything.
5. **Seasonal window: approved, built second.** It opens Thanksgiving, 26 November 2026, and closes 6 January 2027, on the server's clock. The always-available shelf is built and accepted first. Agreed by the maintainer on 27 October 2026. Whether the window repeats each year, and on which rule (the fourth Thursday of November or a fixed date), is not decided.
6. **Holiday Lights and Glen: still retired.** No answer above reactivates either. That needs its own explicit instruction and acceptance.
7. **Gate waiver for the eight approved items: yes.** All eight carry `experimentGate = fv_hlights`, the retired world's master switch, which the game serves as off, so they cannot be admitted under the ordinary rule. On 27 October 2026 the maintainer approved waiving that one gate, for exactly those eight codes and only in Mistletoe Lane. This follows how `heritage_pricing.py` already rehomes ordinary decorations from inactive worlds (it drops their experiment gate). Every other gate, level, date window, price and class rule still applies. The waiver lives in `FarmVillage/retired_decor.py` and is not a general precedent: any further item needs its own approval.
