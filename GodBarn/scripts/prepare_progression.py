#!/usr/bin/env python3
"""Recover the Barn's progression definitions from the local game archive.

Only source data is read; no running game modules or player saves are imported.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zlib

try:
    from .recover_catalog import resolve_from_manifests, raster_info, _write_verified
except ImportError:
    from recover_catalog import resolve_from_manifests, raster_info, _write_verified


ROOT = Path(__file__).resolve().parents[1]
LABELS = {
    "haveneighbors": "Neighbors", "helpfriends": "Helping friends",
    "coinsearned": "Coins earned", "coinsspent": "Coins spent",
    "harvestcrops": "Crops harvested", "harvesttrees": "Trees harvested",
    "harvestanimals": "Animals harvested", "boughtbuildings": "Buildings owned",
    "boughtdecorations": "Decorations owned", "adoptanimal": "Animals adopted",
    "harvestcroptype": "Crop varieties harvested", "harvesttreetype": "Tree varieties harvested",
    "harvestanimaltype": "Animal varieties harvested", "uniquegifts": "Gift varieties received",
    "fertilizecrop": "Crops fertilized for friends", "harvestflowers": "Flower Power",
    "placeflowerdecorations": "Flower decorations owned", "harvestfertilizedcrop": "King of Compost",
    "theyofmystery": "They of Mystery", "fencedin": "Fenced In", "baledout": "Baled Out",
    "lordoftheplow": "Lord of the Plow", "needforseed": "Need for Seed",
    "cracked": "Cracked", "catlady": "Cat Lady", "vegetablevirtuoso": "Vegetable Virtuoso",
    "foremostfruitfarmer": "Foremost Fruit Farmer", "eggcelentdiscovery": "Egg-cellent Discovery",
    "cunningcollector": "Cunning Collector", "horsepower": "Horse Power",
    "employeeofthemonth": "Employee of the Month", "fabulousforeman": "Fabulous Foreman",
    "bestoftherest": "Best of the Rest", "cunningcrafter": "Cunning Crafter",
    "supersales": "Super Sales", "bestbuy": "Best Buy", "gearhead": "Gearhead",
    "stylemaven": "Style Maven", "bountifulbeekeeper": "Bountiful Beekeeper",
    "lookingfresh": "Looking Fresh",
}
OWNED = {"haveneighbors", "boughtbuildings", "boughtdecorations", "placeflowerdecorations",
         "fencedin", "baledout", "catlady", "gearhead"}


def recover(source, *, root=ROOT, assets_root=None):
    import pyamf
    manifest_names = ("xml/gz/v855098/assethash.min.amf.gz", "assethash/v9/assethash.master.amf.gz")
    manifests = [(name, pyamf.get_decoder(pyamf.AMF3, zlib.decompress((source / name).read_bytes())).readElement())
                 for name in manifest_names]
    artwork = []

    def copy_art(logical, destination=None):
        original, reason, manifest, _ = resolve_from_manifests(source, manifests, logical, assets_root=assets_root)
        if reason:
            return None
        payload = original.read_bytes()
        raster_info(payload)
        digest = hashlib.sha256(payload).hexdigest()
        relative = destination or "static/assets/progression/" + digest + original.suffix.lower()
        _write_verified(root, relative, payload, digest)
        artwork.append({"path": "/" + relative, "logical": logical, "manifest": manifest,
                        "sha256": digest, "sourcePath": (original.relative_to(Path(assets_root).resolve()).as_posix()
                                       if assets_root else original.relative_to(source).as_posix())})
        return "/" + relative

    settings_path = source / "xml/gz/v855098/gameSettings.xml.gz"
    settings_bytes = settings_path.read_bytes()
    settings = ET.fromstring(zlib.decompress(settings_bytes))
    ribbons = []
    for achievement in settings.findall("./achievements/achievement"):
        if achievement.get("disabled") == "true":
            continue
        name = achievement.attrib["name"]
        images = {image.get("name"): image.get("url") for image in achievement.findall("image")}
        # The archived 130px exports contain transparent placeholders for some
        # ribbons. The original 100px category pictures are the usable artwork.
        icon = next((image for key in ("icon_100", "icon_48", "icon_130")
                     if images.get(key) and (image := copy_art(images[key]))), None)
        colors = ("yellow", "white", "red", "blue")
        tiers = [{key: int(level.get(key, "0")) for key in ("count", "xp", "coins")}
                 | ({"gift": level.get("gift")} if level.get("gift") else {})
                 for level in achievement.findall("level")]
        for index, level in enumerate(tiers):
            logical = images.get("icon_" + colors[index]) if index < len(colors) else None
            if logical and (image := copy_art(logical)):
                level["image"] = image
        if name == "haveneighbors" and images.get("icon_blue"):
            copy_art(images["icon_blue"], "static/assets/ui/ribbon.png")
        ribbons.append({"name": name, "code": achievement.attrib["code"],
                        "displayName": LABELS.get(name, name),
                        "image": icon,
                        "counterSource": "ownership" if name in OWNED else "cumulative",
                        "levels": tiers})
    catalog_path = source / "xml/gz/v855038/items_opt.amf"
    raw_bytes = catalog_path.read_bytes()
    wrapped = pyamf.get_decoder(pyamf.AMF3, zlib.decompress(raw_bytes)).readElement()
    items = wrapped["settings"]["items"]["item"]
    # The game's code lookup keeps the first record even when a later record
    # with the same code has different metadata.
    seen, masteries = set(), []
    for item in items:
        code = item.get("code")
        if code in seen:
            continue
        seen.add(code)
        if str(item.get("mastery")).lower() == "true" and item.get("masteryLevel"):
            masteries.append(item["name"])
    return {"schemaVersion": 1,
            "source": {"ribbons": "xml/gz/v855098/gameSettings.xml.gz",
                       "ribbonsSha256": hashlib.sha256(settings_bytes).hexdigest(),
                       "mastery": "xml/gz/v855038/items_opt.amf",
                       "itemSourceSha256": hashlib.sha256(raw_bytes).hexdigest()},
            "artwork": artwork,
            "ribbons": ribbons, "masteryItems": masteries}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    source = args.source.expanduser().resolve()
    if source == ROOT or ROOT in source.parents:
        raise SystemExit("The source must be outside GodBarn.")
    result = recover(source)
    destination = ROOT / "data/progression.json"
    destination.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"Recovered {len(result['ribbons'])} ribbons and {len(result['masteryItems']):,} mastery tracks.")


if __name__ == "__main__":
    main()
