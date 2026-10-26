#!/usr/bin/env python3
"""Read an existing FarmVillage archive once; write a standalone God Barn dataset.

No FarmVillage Python modules are imported, and no server/game endpoints are used.
All writes remain under this companion's root. pyamf is needed only to decode the
archive manifest during preparation; the finished companion uses Python stdlib.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sys
import struct
import zlib
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
GRANT_TYPES = {"animal", "decoration", "tree", "building", "vehicle", "seed", "fuel", "turbo"}
CLASSICS = {
    "strawberry", "wheat", "corn", "soybeans", "eggplant", "rice", "pumpkin", "cotton",
    "carrot", "pineapple", "raspberry", "blueberry", "watermelon", "artichoke", "tomato",
    "barn", "cow", "chicken", "sheep", "pig", "horse", "goat", "rabbit", "duck",
    "tractor", "harvester", "seeder", "cherry", "apple", "orange", "lemon", "lime",
    "peach", "banana", "haybale", "whitefence", "windmill", "cottage", "well",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def number(value, default=0):
    try:
        value = float(value)
        return int(value) if value.is_integer() else value
    except (TypeError, ValueError):
        return default


def display_name(name: str) -> str:
    special = {"strawberry": "Strawberries", "soybeans": "Soybeans", "barn": "Red Barn",
               "cow": "Dairy Cow", "chicken": "White Chicken", "pineapple": "Pineapples",
               "raspberry": "Raspberries", "blueberry": "Blueberries", "whitefence": "White Fence"}
    if name in special:
        return special[name]
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
    text = re.sub(r"[_\-]+", " ", text)
    return text.title()


def prepare(source, root=ROOT, *, assets_root=None, max_thumbnails=10000, thumbnail_budget_mb=180):
    """Build metadata from original resource files without opening player data."""
    source, root = Path(source).resolve(), Path(root).resolve()
    assets_root = Path(assets_root).resolve() if assets_root else None
    if source == root or root in source.parents or source in root.parents:
        raise ValueError("Game resources and companion output must be separate.")
    for rel in ("data", "static/assets/ui", "static/assets/items", "static/assets/fonts"):
        (root / rel).mkdir(parents=True, exist_ok=True)

    # Import only the third-party decoder; never import source game modules.
    import pyamf
    manifest_path = source / "assethash/v9/assethash.master.amf.gz"
    manifest_bytes = manifest_path.read_bytes()
    manifest = pyamf.get_decoder(pyamf.AMF3, zlib.decompress(manifest_bytes)).readElement()
    manifests = []
    delta = source / "xml/gz/v855098/assethash.min.amf.gz"
    if delta.is_file():
        manifests.append((delta.relative_to(source).as_posix(),
                          pyamf.get_decoder(pyamf.AMF3, zlib.decompress(delta.read_bytes())).readElement()))
    manifests.append((manifest_path.relative_to(source).as_posix(), manifest))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from recover_catalog import resolve_from_manifests
    asset_root = assets_root or (source / "LocalData/assets")
    catalog_path = source / "xml/gz/v855038/items_opt.amf"
    catalog_bytes = catalog_path.read_bytes()
    wrapped = pyamf.get_decoder(pyamf.AMF3, zlib.decompress(catalog_bytes)).readElement()
    raw_items = wrapped["settings"]["items"]["item"]
    by_name = {}
    for item in raw_items:
        by_name.setdefault(item["name"], item)
    copied = []
    ui_manifest = {}

    def resolve_asset(logical: str):
        path, reason, _, _ = resolve_from_manifests(source, manifests, logical, assets_root=asset_root)
        return path if reason is None else None

    def copy_asset(logical: str, destination: str):
        src = resolve_asset(logical)
        if not src:
            return None
        dst = root / destination
        if not dst.is_relative_to(root):
            raise ValueError("Destination escaped the companion")
        data = src.read_bytes()
        dst.write_bytes(data)
        entry = {"logical": logical, "assetRelativePath": src.relative_to(asset_root).as_posix(), "path": destination,
                 "bytes": len(data), "sha256": digest(data)}
        if src.suffix.lower() == ".png" and data[:8] == b"\x89PNG\r\n\x1a\n":
            entry["width"], entry["height"] = struct.unpack(">II", data[16:24])
        copied.append(entry)
        return "/" + destination

    def item_icon(item):
        images = item.get("image") or []
        if isinstance(images, dict):
            images = [images]
        pngs = [im for im in images if isinstance(im, dict) and str(im.get("url", "")).lower().endswith(".png")]
        pngs.sort(key=lambda im: (im.get("name") != "icon", "200" in im.get("url", "")))
        for im in pngs:
            path = resolve_asset(im["url"])
            if path:
                return im["url"], path
        return None, None

    ui_sources = {
        "coin.png": "assets/consumables/consume_coins_icon.png",
        "cash.png": "assets/consumables/consume_cash_icon.png",
        "xp.png": "assets/consumables/consume_xp_icon_small.png",
        "gift.png": "assets/hud/Action_Menu/FV_Main_Gift_Icon.png",
        "board.png": "assets/hud/FV_Main_UI_Bttm_Board.png",
        "wood-frame.png": "assets/dialogs/FV_Support/frames/basic/buildable_woodframe.png",
        "wood-grain.png": "assets/dialogs/Wood_Grain.png",
        "wood-tile.jpg": "assets/dialogs/4d_elements/Standard/LighterWoodTile.jpg",
        "dark-wood-tile.jpg": "assets/dialogs/4d_elements/Questing/DarkerWoodTile.jpg",
        "market.png": "assets/hud/Action_Menu/FV_Main_Market_Icon.png",
        "shovel.png": "assets/hud/Action_Menu/FV_Main_Plow_Icon.png",
        "scythe.png": "assets/hud/Action_Menu/FV_Main_Scythe_Icon.png",
        "fertilizer.png": "assets/hud/FV_Main_Fertilizer_Icon.png",
        "fuel.png": "assets/hud/FV_Fuel_gift_Icon.png",
        "xp-star.png": "assets/hud/Friendbar/FV_Main_FriendBar_XP_Star.png",
        "farmer.png": "assets/dialogs/4d_elements/Questing/NPC_standing_farmerbob_happy.png",
        "farmer-portrait.png": "assets/dialogs/4d_elements/Questing/NPC_circle_farmer.png",
        "logo.png": "assets/dialogs/4d_elements/FTUE/ftue_welcome_logo.png",
        "barnyard.png": "assets/dialogs/4d_elements/MOTD/BigBarnyard_MOTD.png",
        "tractor-tool.png": "assets/hud/Action_Menu/FV_Main_Tractor_Icon.png",
        "harvester-tool.png": "assets/hud/Action_Menu/FV_Main_Harvester_Icon.png",
        "seeder-tool.png": "assets/hud/Action_Menu/FV_Main_Seeder_Icon.png",
        "collections.png": "assets/hud/Action_Menu/FV_Main_Collections_Icon.png",
        "silo.png": "assets/hud/Action_Menu/FV_Main_Storage_Icon.png",
    }
    for name, logical in ui_sources.items():
        url = copy_asset(logical, "static/assets/ui/" + name)
        if url:
            ui_manifest[name] = {"url": url, "logical": logical}
    ui_item_names = {"tractor.png": "tractor", "barn.png": "barn", "cow.png": "cow",
                     "chicken.png": "chicken", "sheep.png": "sheep", "pig.png": "pig",
                     "horse.png": "horse", "tree.png": "cherry", "strawberry.png": "strawberry",
                     "wheat.png": "wheat", "corn.png": "corn", "pumpkin.png": "pumpkin",
                     "seed.png": "wheat", "decoration.png": "haybale", "building.png": "barn"}
    for name, item_name in ui_item_names.items():
        item = by_name.get(item_name)
        if item:
            logical, path = item_icon(item)
            if path:
                url = copy_asset(logical, "static/assets/ui/" + name)
                ui_manifest[name] = {"url": url, "logical": logical}
    if "tree.png" not in ui_manifest:
        item = next((i for i in raw_items if i.get("type") == "tree" and item_icon(i)[1]), None)
        if item:
            logical, _ = item_icon(item)
            ui_manifest["tree.png"] = {"url": copy_asset(logical, "static/assets/ui/tree.png"), "logical": logical}

    fonts = {"badaboom.ttf": "badaboomprobb_reg.ttf", "caslon-bold.otf": "ACaslonPro-Bold.otf",
             "myriad-bold.otf": "MyriadPro-Bold.otf"}
    for name, original in fonts.items():
        url = copy_asset("assets/fonts/" + original, "static/assets/fonts/" + name)
        if url:
            ui_manifest[name] = {"url": url, "logical": "assets/fonts/" + original}

    # Always include recognizable classics, then draw equally across archive types.
    # Hash ordering makes the selection reproducible without alphabetic bias.
    buckets = collections.defaultdict(list)
    for item in raw_items:
        buckets[item.get("type", "unknown")].append(item)
    for values in buckets.values():
        values.sort(key=lambda i: hashlib.sha256(i["name"].encode()).hexdigest())
    candidates = [by_name[name] for name in sorted(CLASSICS) if name in by_name]
    maximum = max(map(len, buckets.values()), default=0)
    for index in range(maximum):
        for kind in sorted(buckets):
            if index < len(buckets[kind]):
                candidates.append(buckets[kind][index])
    image_by_name, seen, copied_thumbnails = {}, set(), set()
    thumbnail_bytes = 0
    budget = thumbnail_budget_mb * 1024 * 1024
    for item in candidates:
        if item["name"] in seen:
            continue
        seen.add(item["name"])
        logical, path = item_icon(item)
        if not path:
            continue
        if len(image_by_name) >= max_thumbnails:
            break
        size = path.stat().st_size
        if thumbnail_bytes + size > budget:
            continue
        target = "static/assets/items/" + path.name
        if target not in copied_thumbnails:
            image_by_name[item["name"]] = copy_asset(logical, target)
            thumbnail_bytes += size
            copied_thumbnails.add(target)
        else:
            image_by_name[item["name"]] = "/" + target

    fallback = {"animal": "cow.png", "tree": "tree.png", "seed": "strawberry.png",
                "building": "barn.png", "decoration": "decoration.png", "vehicle": "tractor.png",
                "fuel": "fuel.png", "turbo": "tractor-tool.png", "bushel": "wheat.png",
                "bloom": "strawberry.png", "blossom": "tree.png", "currency_exchange": "coin.png"}
    normalized = []
    for item in raw_items:
        kind = item.get("type", "unknown")
        code = str(item.get("code", ""))
        entry = {key: item.get(key, "") for key in ("name", "code", "type", "subtype", "className")}
        entry.update({key: number(item.get(key)) for key in
                      ("cost", "cash", "growTime", "squares", "sizeX", "sizeY", "coinYield", "plantXp", "requiredLevel")})
        entry["displayName"] = display_name(item["name"])
        entry["image"] = image_by_name.get(item["name"], "/static/assets/ui/" + fallback.get(kind, "gift.png"))
        entry["hasOriginalThumbnail"] = item["name"] in image_by_name
        entry["grantable"] = kind in GRANT_TYPES and bool(code) and code != "XX" and ":" not in code
        entry["placeable"] = item.get("placeable") == "true"
        entry["archived"] = item.get("archived") == "yes"
        if item.get("masteryLevel"):
            entry["masteryLevel"] = item["masteryLevel"]
        normalized.append(entry)
    (root / "data/catalog.json").write_text(json.dumps(normalized, ensure_ascii=False, separators=(",", ":")) + "\n")

    game_path = source / "xml/gz/v855098/gameSettings.xml.gz"
    cms_path = source / "xml/gz/v855098/gameSettingsCMS.xml.gz"
    settings = ET.fromstring(zlib.decompress(game_path.read_bytes()))
    cms = ET.fromstring(zlib.decompress(cms_path.read_bytes()))
    farming = {e.attrib["key"]: e.attrib["value"] for e in cms.findall(".//farming/farmingEntry")}
    rules = {"levels": [{"level": int(e.attrib["num"]), "xp": int(e.attrib["requiredXP"])}
                        for e in settings.findall("./levels/level")],
             "inGameDaySeconds": number(farming.get("inGameDaySeconds"), 82800),
             "growMultiplier": number(farming.get("growMultiplier"), 1),
             "witherMultiplier": number(farming.get("witherMultiplier"), 2.2),
             "higherLevelBegin": number(farming.get("higherLevelBegin"), 101),
             "higherLevelXp": number(farming.get("higherLevelXp"), 1500000),
             "higherLevelStep": number(farming.get("higherLevelStep"), 100000),
             "highestLevelForFCReward": number(farming.get("highestLevelForFCReward"), 250)}
    (root / "data/rules.json").write_text(json.dumps(rules, indent=2) + "\n")
    provenance = {"schema": 2, "sourceReadOnly": True,
                  "sourceModulesImported": False, "networkUsed": False,
                  "containsPlayerState": False,
                  "sources": [{"path": p.relative_to(source).as_posix(), "sha256": digest(p.read_bytes())}
                              for p in (manifest_path, catalog_path, game_path, cms_path)],
                  "catalogItems": len(normalized), "illustratedItems": len(image_by_name),
                  "thumbnailBytes": thumbnail_bytes,
                  "categoryFallbacks": fallback, "assets": copied}
    (root / "data/provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    (root / "data/ui-assets.json").write_text(json.dumps(ui_manifest, indent=2) + "\n")
    print(json.dumps({"catalogItems": len(normalized), "illustratedItems": len(image_by_name),
                      "thumbnailMiB": round(thumbnail_bytes / 1048576, 2),
                      "uiAssets": len(ui_manifest), "levels": len(rules["levels"]),
                      "containsPlayerState": False}, indent=2))
    return provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Original game resource root (read-only)")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--assets-root", type=Path)
    parser.add_argument("--max-thumbnails", type=int, default=10000)
    parser.add_argument("--thumbnail-budget-mb", type=int, default=180)
    args = parser.parse_args()
    prepare(args.source, args.root, assets_root=args.assets_root,
            max_thumbnails=args.max_thumbnails, thumbnail_budget_mb=args.thumbnail_budget_mb)


if __name__ == "__main__":
    main()
