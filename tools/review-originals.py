#!/usr/bin/env python3
"""Read-only review of the pinned public originals: retired-world decor and the Mistletoe Patisserie.

Needs no Mac, no private input and none of the 19 GB artwork archives. The catalogue, recipes and
gates are in 44 small pinned files (about 48 MB) from the public AcidCaos/farmvillage revision named
in tools/public-resources.json. The script can fetch them, verifies every size and Git blob id, and
refuses anything that does not match. It writes only CSV and JSON files to a folder outside this
checkout and changes nothing else.

    python3 -I -B tools/review-originals.py --originals /new/empty/folder --fetch --out /other/folder
    python3 -I -B tools/review-originals.py --originals /already/fetched   --out /other/folder

The catalogue decoder needs Py3AMF. Install FarmVillage/requirements.txt into a virtual environment
that lives outside this checkout.

What it does NOT do: check that artwork files exist (that needs the archives), admit or price anything,
or decide which candidate is acceptable. Its tables are inputs to the per-item approval route in
docs/briefs/WORLD_ROSTER_AND_REPURPOSING.md.
"""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zlib
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "FarmVillage"))
import heritage_pricing as hp  # noqa: E402  (pure module; reused so definitions cannot drift)

ITEMS_FILE = "xml/gz/v855038/items_opt.amf"
CRAFTING_FILE = "xml/gz/v855098/crafting.xml.gz"
RETIRED = ("hlights", "glen")
DESTINATIONS = ("htown", "storybook", "fforest")
CRAFT_TYPE = "xhdcrafttype"
CANDIDATE_COLUMNS = ["world", "code", "name", "type", "className", "subtype", "sizeX", "sizeY", "cost", "cash",
                     "market", "requiredLevel", "limitedStart", "limitedEnd", "archived", "buyable", "rareItem",
                     "worlds", "in_htown", "in_storybook", "in_fforest", "blocking_fields", "foreign_requirement",
                     "ordinary_class", "candidate", "has_own_price"]
RECIPE_COLUMNS = ["id", "name", "in_repo_set", "skill_level_required", "initial_recipe_level", "minutes_to_cook",
                  "rush_coins", "rush_cash", "deprecated", "limited_start", "limited_end", "windowed", "ingredients",
                  "sell_qty", "gift_qty", "player_xp", "recipe_xp", "mastery_sign"]


class ReviewError(ValueError):
    pass


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def load_pins() -> dict:
    return json.loads((ROOT / "tools/public-resources.json").read_text())["upstream"]


def verify_originals(directory: Path, spec: dict) -> list[str]:
    """Return a list of problems; an empty list means every pinned file is present and exact."""
    problems = []
    for entry in spec["files"]:
        path = Path(directory) / entry["path"]
        if path.is_symlink() or not path.is_file():
            problems.append("missing: " + entry["path"])
            continue
        data = path.read_bytes()
        if len(data) != entry["bytes"] or git_blob(data) != entry["gitBlob"]:
            problems.append("does not match its pin: " + entry["path"])
    return problems


def fetch_originals(directory: Path, spec: dict) -> None:
    directory = Path(directory)
    if directory.exists() and any(directory.iterdir()):
        raise ReviewError("Choose a new, empty folder for the originals.")
    directory.mkdir(parents=True, exist_ok=True)
    for entry in spec["files"]:
        target = directory / entry["path"]
        if Path(entry["path"]).is_absolute() or directory.resolve() not in target.resolve().parents:
            raise ReviewError("A pinned path leaves the destination folder: " + entry["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        url = "https://raw.githubusercontent.com/AcidCaos/farmvillage/%s/%s" % (spec["revision"], entry["path"])
        subprocess.run(["curl", "-fsSL", "--retry", "3", "-o", str(target), url], check=True)


def check_output_dir(out: Path) -> Path:
    """Evidence stays out of the checkout so it cannot be committed by accident."""
    out = Path(out).resolve()
    if out == ROOT or ROOT in out.parents:
        raise ReviewError("Write the results outside the repository checkout.")
    return out


def load_catalogue(directory: Path) -> list[dict]:
    try:
        import pyamf
    except ImportError as error:
        raise ReviewError("Install FarmVillage/requirements.txt into a virtual environment outside the checkout (Py3AMF is needed).") from error
    raw = zlib.decompress((Path(directory) / ITEMS_FILE).read_bytes())
    if raw[:1] != b"\x0a":
        raise ReviewError("The catalogue is not an AMF3 object.")
    return pyamf.get_decoder(pyamf.AMF3, raw).readElement()["settings"]["items"]["item"]


def worlds_of(item: dict) -> list[str]:
    return sorted({name for name in hp._world_names(item) if name})


def blocking_fields(item: dict) -> list[str]:
    # Same test as heritage_pricing.plan: a field blocks when it is neither absent nor empty.
    return [field for field in hp.BLOCKING_FIELDS if item.get(field) not in (None, "")]


def candidate_row(world: str, item: dict) -> dict:
    present = worlds_of(item)
    blocking = blocking_fields(item)
    foreign = hp._foreign_requirement(item)
    ordinary = (item.get("type"), item.get("className")) in hp.ORDINARY_CLASSES
    row = {"world": world, "worlds": " ".join(present), "blocking_fields": " ".join(blocking),
           "foreign_requirement": foreign, "ordinary_class": ordinary,
           "candidate": ordinary and not blocking and not foreign,
           "has_own_price": any(item.get(field) not in (None, "", "0", 0) for field in ("cost", "cash"))}
    for destination in DESTINATIONS:
        row["in_" + destination] = destination in present
    for column in CANDIDATE_COLUMNS:
        if column not in row:
            row[column] = item.get(column, "")
    return row


def screen_world(records: list[dict], world: str) -> tuple[list[dict], dict]:
    """Every record whose requirements name the world, plus the funnel of the ordinary-class screen."""
    rows = [candidate_row(world, item) for item in records if world in worlds_of(item)]
    funnel = {"associated": len(rows),
              "ordinary_class": sum(r["ordinary_class"] for r in rows),
              "ordinary_and_gate_free": sum(r["ordinary_class"] and not r["blocking_fields"] for r in rows),
              "candidates": sum(r["candidate"] for r in rows),
              "candidates_already_in": {d: sum(r["candidate"] and r["in_" + d] for r in rows) for d in DESTINATIONS},
              "candidates_not_yet_in": {d: sum(r["candidate"] and not r["in_" + d] for r in rows) for d in DESTINATIONS},
              "candidates_without_own_price": sum(r["candidate"] and not r["has_own_price"] for r in rows),
              "candidates_with_date_window": sum(r["candidate"] and bool(r["limitedStart"] or r["limitedEnd"]) for r in rows),
              "candidates_marked_not_buyable": sum(r["candidate"] and r["buyable"] == "false" for r in rows)}
    return rows, funnel


def repo_recipe_codes(craft: str = CRAFT_TYPE) -> set[str]:
    """The recipe codes the game server admits for a craft type, read from crafting.py without importing it."""
    tree = ast.parse((ROOT / "FarmVillage/crafting.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "REGIONAL_RECIPES" for t in node.targets):
            for key, value in zip(node.value.keys, node.value.values):
                # Each value is frozenset((...codes...)); read the tuple literal, never evaluate the call.
                if ast.literal_eval(key) == craft and isinstance(value, ast.Call) and value.args:
                    return set(ast.literal_eval(value.args[0]))
    raise ReviewError("REGIONAL_RECIPES[%r] was not found in crafting.py." % craft)


def recipe_rows(crafting_xml: bytes, names_by_code: dict, craft: str = CRAFT_TYPE, admitted: set | None = None) -> list[dict]:
    root = ET.fromstring(crafting_xml)
    rows = []
    for recipe in root.find("recipes"):
        if recipe.findtext("craft") != craft:
            continue
        ingredients = "; ".join("%s x%s" % (names_by_code.get(i.get("itemCode"), i.get("itemCode")), i.get("quantityRequired"))
                                for i in recipe.iter("Ingredient"))
        finish, make = recipe.find(".//OnFinish"), recipe.find(".//OnMake")
        start, end = recipe.findtext("limitedStart") or "", recipe.findtext("limitedEnd") or ""
        mastery = recipe.find("Mastery")
        rows.append({"id": recipe.get("id"), "name": recipe.findtext("name"),
                     "in_repo_set": "" if admitted is None else recipe.get("id") in admitted,
                     "skill_level_required": recipe.findtext("SkillLevelRequired"),
                     "initial_recipe_level": recipe.findtext("InitialRecipeLevel"),
                     "minutes_to_cook": recipe.findtext("MinutesToCook"),
                     "rush_coins": recipe.findtext("RushCostCoins"), "rush_cash": recipe.findtext("RushCostCash"),
                     "deprecated": recipe.findtext("Deprecated"), "limited_start": start, "limited_end": end,
                     "windowed": bool(start or end), "ingredients": ingredients,
                     "sell_qty": finish.get("sellQty") if finish is not None else "",
                     "gift_qty": finish.get("giftQty") if finish is not None else "",
                     "player_xp": make.get("playerXp") if make is not None else "",
                     "recipe_xp": make.get("recipeXp") if make is not None else "",
                     "mastery_sign": mastery.get("sign") if mastery is not None else ""})
    return rows


def recipe_item_codes(crafting_xml: bytes, craft: str = CRAFT_TYPE) -> set[str]:
    """Every finished-good code and ingredient code used by the recipes of one craft type."""
    codes = set()
    for recipe in ET.fromstring(crafting_xml).find("recipes"):
        if recipe.findtext("craft") == craft:
            codes.add(recipe.get("id"))
            codes.update(i.get("itemCode") for i in recipe.iter("Ingredient"))
    return codes


def windowed_items(records: list[dict], codes: set[str]) -> dict:
    """Which of the codes are missing from the catalogue or carry their own date window."""
    by_code = {}
    for item in records:
        if isinstance(item, dict):
            by_code.setdefault(item.get("code"), item)
    return {"checked": len(codes), "not_in_catalogue": sorted(c for c in codes if c not in by_code),
            "windowed": sorted(c for c in codes if c in by_code and (by_code[c].get("limitedStart") or by_code[c].get("limitedEnd")))}


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--originals", required=True, type=Path, help="folder holding (or to receive) the 44 pinned originals")
    parser.add_argument("--out", required=True, type=Path, help="new folder for the results, outside this checkout")
    parser.add_argument("--fetch", action="store_true", help="download the pinned originals into --originals first")
    options = parser.parse_args(argv)
    try:
        out = check_output_dir(options.out)
        spec = load_pins()
        if options.fetch:
            fetch_originals(options.originals, spec)
        problems = verify_originals(options.originals, spec)
        if problems:
            raise ReviewError("The originals are not the pinned set:\n  " + "\n  ".join(problems))
        records = load_catalogue(options.originals)
        names = {r.get("code"): r.get("name") for r in records if isinstance(r, dict)}
        summary = {"upstream_revision": spec["revision"], "originals_verified": len(spec["files"]),
                   "catalogue_records": len(records),
                   "catalogue_sha256": hashlib.sha256((Path(options.originals) / ITEMS_FILE).read_bytes()).hexdigest(),
                   "art_presence": "UNRUN: needs the four archives (19.13 GB), which this review does not download",
                   "worlds": {}}
        out.mkdir(parents=True, exist_ok=True)
        for world in RETIRED:
            rows, funnel = screen_world(records, world)
            write_csv(out / ("candidates_%s.csv" % world), CANDIDATE_COLUMNS, rows)
            summary["worlds"][world] = funnel
        crafting = zlib.decompress((Path(options.originals) / CRAFTING_FILE).read_bytes())
        admitted = repo_recipe_codes()
        recipes = recipe_rows(crafting, names, admitted=admitted)
        write_csv(out / "mistletoe_patisserie.csv", RECIPE_COLUMNS, recipes)
        found = {r["id"] for r in recipes}
        summary["mistletoe_patisserie"] = {"recipes_in_original": len(recipes), "admitted_by_repo": len(admitted),
                                           "repo_set_equals_original": found == admitted,
                                           "in_original_not_in_repo": sorted(found - admitted),
                                           "in_repo_not_in_original": sorted(admitted - found),
                                           "windowed": sum(r["windowed"] for r in recipes),
                                           "related_items": windowed_items(records, recipe_item_codes(crafting)),
                                           "deprecated": sum(r["deprecated"] not in (None, "", "0") for r in recipes)}
        (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    except (ReviewError, OSError, subprocess.CalledProcessError, ET.ParseError) as error:
        print("Review stopped: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
