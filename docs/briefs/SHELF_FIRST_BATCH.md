# Shelf first batch: a proposal

**Status: eight items approved for exploration on 27 October 2026; an admission adapter exists in source (`FarmVillage/retired_decor.py`); acceptance in the game is UNRUN.** Every item below needs approval from the world owner and the integration reviewer before it enters Mistletoe Lane, as set out in the [roster brief](WORLD_ROSTER_AND_REPURPOSING.md). The items come from Holiday Lights and Enchanted Glen, both retired worlds; reading their records reactivates neither.

**Basis.** An independent run of the [no-Mac review](ASSET_REVIEW_NO_MAC.md) on 27 October 2026 matched every number in its guide, and a second check by the maintainer's assistant confirmed its main claims against the same data. Prices follow the recorded decision: an item's own recovered price, never a hand-picked one.

## What the review showed

The 287 Holiday Lights "candidates" are not 287 decorations. The screen checks only ordinary class and gate fields.

| Type | Count | Fit for a decor shelf |
| --- | --- | --- |
| Animals | 123 | No. They need the animal and breeding systems; 70 are marked not buyable. |
| Trees | 32 | No. Orchard trees; 18 are mature forms, all not buyable. |
| Seeds | 32 | No. Crops need the farming and harvest system. |
| Buildings | 18 | No. 8 are already Mistletoe items; the other 10 are town buildings needing their own systems. |
| Decorations | 82 | Some. See the tiers below. |

Enchanted Glen's 32 candidates are 12 seeds, 2 buildings and 18 decorations, 10 of which are the Unwither rings.

## Tier 1: proposed first batch (8 items, Mistletoe Lane)

Decorations that are buyable, have no date window, are not already Mistletoe items, and are neither large attractions, moats nor gnomes.

| Code | Name | Size | Own price |
| --- | --- | --- | --- |
| `o8q` | `xhl_glowingflowerbox` | 1x1 | 5 cash |
| `puh` | `xhl_holidaylamppost` | 1x1 | 5 cash |
| `pmx` | `xhl_twistylamppost` | 1x1 | 5 cash |
| `prk` | `xhl_lightedbench` | 1x3 | 4 cash |
| `p1p` | `xhl_hollybrightgreetings` | 2x1 | 8 cash |
| `pv5` | `xhl_puppysnowpile` | 2x2 | 10 cash |
| `pze` | `xhl_hollybrightlane` | 5x5 | 10 cash |
| `o7m` | `xhl_hollybrightpath` | 2x2 | 40000 coins (no market field, so coins; no cash price) |

Seven are sold for Farm Cash, because their `market` is `cash`; the coin value on those records is not what a player pays. `xhl_hollybrightpath` is the exception and the one to look at hardest.

## Tier 2: later, each needing a question answered first

- **Six large attractions** (`xhl_hollybrightcarousel`, `xhl_hollybrighttrain`, `xhl_hollyskatingrink`, `xhl_lanecarriage`, `xhl_litpickuptruck`, `xhl_twinklingwindmill`): confirm they are static pieces and not animated or interactive, and that their footprints (up to 9x3 and 6x6) suit the plots.
- **Six moats** (`moat_xhl_rainbow` and the numbered ones): confirm whether they rely on water tiles or adjacency. This is a guess from the names, not a finding.
- **Six gnomes** (`gnome_xhl_*`): confirm whether a gnome collection mechanic applies. One, `gnome_xhl_illuminated`, is priced 300000 coins with no cash price and no rare flag, unlike its siblings.
- **Three Glen decorations for Fairytale Fields or Mystical Groves** (`xegleafboatwithafairy`, `xegpebbles3`, `xegwaterfairy`): the only buyable ordinary Glen decor. Separate destination, separate approval.

## Not for the shelf

The 123 animals, 32 trees, 32 seeds and 18 buildings above; the 10 Holiday Lights and 10 Glen Unwither rings (not buyable, tied to a mechanic); `beatholidaylightsstatue` (a reward item that nevertheless passes the screen); `xlg_xpromo_sign` (a promo sign, not buyable); and the 45 date-windowed baby animals. `cobblestonebridge` and `fairybed` carry gate fields and are not candidates. The 52 items already in Mistletoe Lane need no transplant.

## Questions the review cannot answer

These are for the integrator, and I have not verified them:

0. **What was built (27 October 2026).** All eight carry `experimentGate = fv_hlights`, the retired world's master switch, which the game serves as off, so none could be admitted under the ordinary rule. With the maintainer's approval (decision 7 in the [roster brief](WORLD_ROSTER_AND_REPURPOSING.md)), `retired_decor.py` names the eight exact code and name pairs and, only for them and only in Mistletoe Lane, waives the World requirement and that one gate. It is wired into `creative_worlds.world_requirement_matches`, `themed_worlds.catalog_rules` and `_reasons`, and `themed_market_presentation` (which presents each item to the client as a Mistletoe Lane offer and mixes the table into the policy digest). Tests in `FarmVillage/macOS/Tests/test_retired_decor.py` prove the eight are admitted at their own prices and nothing else changes, every held-back and other-world case stays refused, and a placement keeps its catalog class. They were run against the recovered catalogue from the public originals, not in the game client.
1. **Admission and inventory identity.** How a non-native item is admitted to Mistletoe Lane and which inventory it lives in (Holiday Lights uses storage id -25, Mistletoe Lane -15). The catalogue audit calls this shape `ADMISSION_GAP_WITH_KNOWN_ENGINE`: an exact item allowlist through the themed-world guards, with both the allowed and the refused case tested. The adapter now exists (see item 0), but how a bought or placed item is stored under storage id -15 rather than -25, and whether it survives a reload and a world switch, is unproven in the game.
2. **`rareItem` and `archived`.** Most candidates are flagged rare and all are `archived = yes`. What either means for a shelf is not assumed here.
3. **Artwork.** Whether each picture exists locally is UNRUN. It needs the four archives.
4. **The client.** Whether the original client shows and places these items in Mistletoe Lane is unproven.

## Data quirks worth a per-item look

Most `xhl_*` records share template-looking coin values; outliers include `unicorn_xhl_brightmane` (500000 coins against 10000 for its siblings), `gnome_xhl_illuminated` and `xhl_hollybrightpath`. Two elk records store `requiredLevel` as a list rather than a number. None affects Tier 1 except the path.

## Recipe notes from the same review

The 17 Mistletoe recipes are very uniform: every one cooks for 360 minutes, rushes for 5 cash, has three ingredients and gives 50 player XP. `eggnog2` and `holidaycookies2` are not missing older variants: the un-numbered names already exist as a consumable and a tree, so the `2` marks the crafted good. `blackberrychampagne` is an alcohol-style name that is already admitted and authored; the project keeps authored names, so changing it would be a content decision for the maintainer.

## What acceptance would require, per item

On a newly created synthetic farm: buy at the item's own price, place, store, reload and restart, with the right coins or cash charged once. Also prove the refusals: an item outside the list stays refused. Report PASS, FAIL and UNRUN per target. None of this has been run.
