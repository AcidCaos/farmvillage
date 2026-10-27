# Asset review without a Mac

For any contributor or helper agent with a normal computer: no Mac, no private inputs and no 19 GB download. It reviews two things from the public originals: the retired-world decor that could be considered for the active worlds, and the Mistletoe Lane Patisserie recipes. It is read-only. It admits, prices and places nothing. Enchanted Glen and Holiday Lights are retired worlds, and this review changes nothing about that: it only reads their records.

## Why the big archives are not needed

The "assets" come in two kinds:

- **Data:** the item catalogue, recipes, prices, gates and quests. All of it is in **44 small pinned files, about 48 MB**, from a public revision of AcidCaos/farmvillage. This is everything the review below uses.
- **Artwork:** pictures, audio and fonts, in four Internet Archive archives totalling **19.13 GB**. Only a check that a candidate's picture exists locally needs these. That check is not part of this review (see "Not covered").

## What you need

Python 3.10 or newer, `curl`, a normal internet connection and about 100 MB of free disk. Use a virtual environment **outside** the checkout.

```sh
git clone https://github.com/jannsenburke/FarmVillage-GodBarn.git
cd FarmVillage-GodBarn
python3 -m venv "$HOME/.local/share/fv-review-venv"
"$HOME/.local/share/fv-review-venv/bin/python" -m pip install -r FarmVillage/requirements.txt
```

## Run it

Choose two new folders **outside** the checkout, one for the downloaded originals and one for the results:

```sh
"$HOME/.local/share/fv-review-venv/bin/python" -I -B tools/review-originals.py \
  --originals "$HOME/fv-review/original" --fetch --out "$HOME/fv-review/results"
```

The tool downloads each pinned file, checks its size and Git blob id, and **stops if any file differs**. It refuses to write results inside the checkout. Run it again later without `--fetch` to reuse the verified folder.

## The numbers it should print

These were produced from upstream revision `2dc25ca24032041a8b68d299b861eb2d4d449653` on 27 October 2026. If yours differ, stop, report both sets of numbers, and do not adjust the tool to match.

| Check | Expected |
| --- | --- |
| Originals verified | 44 |
| Catalogue records | 111,206 |
| Catalogue SHA-256 | `14987fd4c07f9de35ff5092aeab58584802fd7fbeca1131ad1a5e3eee381a4d7` |
| Mistletoe recipes: original and repo agree | 17 and 17, `repo_set_equals_original` true |
| Recipes or related items with a date window | 0 recipes; 0 of 47 related items |
| Holiday Lights: associated, ordinary class | 591, 379 |
| Holiday Lights: gate-free candidates | 287 |
| Holiday Lights: already Mistletoe items | 52 |
| Holiday Lights: candidates with their own date window, marked not buyable | 45, 100 |
| Holiday Lights: candidates with no price of their own | 1 |
| Enchanted Glen: associated, ordinary class | 172, 91 |
| Enchanted Glen: gate-free candidates | 32 (none already in Fairytale Fields or Mystical Groves) |
| Enchanted Glen: with a date window, marked not buyable | 0, 17 |

The 591, 379, 172 and 91 reproduce the figures recorded in [Wave 3](<../../Wave 3.md>) exactly.

## Reading the results

The results folder holds `summary.json`, `candidates_hlights.csv`, `candidates_glen.csv` and `mistletoe_patisserie.csv`.

- **The screen is necessary, not sufficient.** A row marked `candidate` only passed the repo's ordinary-class and gate-field checks. `beatholidaylightsstatue` passes them, yet Wave 3 says it carries reward meaning and must stay reward-gated. Conversely `cobblestonebridge` and `fairybed`, which Wave 3 named as items to investigate, are **not** candidates: each has a gate field (`marketPrereqs`, `purchasePrereqs`). Read the names.
- **Shared items are already home.** A candidate whose `in_htown` is true already belongs to Mistletoe Lane. It needs no transplant.
- **Date windows and `buyable`.** A candidate with `limitedStart` or `limitedEnd` has its own original window, which a shelf must not get around. `archived` and `buyable` are carried through unchanged; what they mean for a shelf is a question for the per-item review, not an assumption.
- **Prices.** The tables show each item's own recovered price. An item with none needs the deterministic derived price later (decision recorded in the roster brief).
- **Recipes.** The table gives each recipe's skill level, initial recipe level, cook minutes, rush cost, yield and ingredients by name. All 17 have no date window and none is deprecated.

## What to report

Counts and named gaps: which expected numbers matched, which did not, and a short list of candidate names that look wrong for a shelf (reward items, buildings, anything needing a special system). Keep the CSVs with the helper. Do not commit them. Do not edit any allowlist, price list or world setting.

## Not covered

- **Artwork presence.** Whether each candidate's picture exists in the archives needs the four archives (19.13 GB). The repo's installer extracts them (see [resource setup](../RESOURCE_SETUP.md)), but it also builds the Ruffle player, which takes hours, and a lighter art-only check has not been written or tested. Do this only after the tables above are reviewed, and ask the maintainer for a narrow art-only step.
- **Gameplay.** No recipe or item is tested in the game. Per-recipe acceptance is step 1 of the [Mistletoe brief](W15_MISTLETOE_HOLIDAY_SEASON.md).
- **Approval.** A candidate is only a candidate. Admission follows the approval route in the [roster brief](WORLD_ROSTER_AND_REPURPOSING.md).

## Paste-ready assignment for a helper agent

> Work from a clone of FarmVillage-GodBarn on any computer; you need no Mac and no private files. Read `AGENTS.md`, then `docs/briefs/ASSET_REVIEW_NO_MAC.md` and follow it exactly. Create the virtual environment outside the checkout, run `tools/review-originals.py` with `--fetch`, and compare every number to the table in the guide. If anything differs, stop and report both sets of numbers. Otherwise read `candidates_hlights.csv`, `candidates_glen.csv` and `mistletoe_patisserie.csv` and report: which numbers matched; the candidate names that look wrong for a shelf (reward items, buildings, anything that needs a special system); candidates with their own date window or marked not buyable; and anything surprising in the recipes. Do not modify the repository, commit the results, edit any allowlist or price, start a game server, or touch any save. Candidates only. Retired worlds stay retired. Report PASS, FAIL and UNRUN, and say that artwork presence is UNRUN.
