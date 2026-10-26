#!/usr/bin/env python3
"""Recover collection and quest helper definitions without loading the game.

Only archived XML, locale, manifests and declared image assets are read. Outputs
stay in GodBarn; no saves, server modules or running services are accessed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import zlib

try:
    from .recover_labels import abc_blocks, locale_constructor, literal_properties
    from .recover_catalog import resolve_from_manifests, raster_info
except ImportError:
    from recover_labels import abc_blocks, locale_constructor, literal_properties
    from recover_catalog import resolve_from_manifests, raster_info


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    from helper_tools import collection_display_name
finally:
    sys.path.pop(0)


def _table(section):
    if not isinstance(section, dict):
        return {}
    result = {}
    for key, value in section.items():
        if key == "length":
            continue
        entries = value if key.isdigit() and isinstance(value, dict) else {key: value}
        for name, entry in entries.items():
            if name in result and result[name] != entry:
                raise ValueError("Conflicting locale helper entry: " + name)
            result[name] = entry
    return result


def _label(table, key, fallback=""):
    entry = table.get(key, {})
    if not isinstance(entry, dict):
        return fallback
    variations = entry.get("variations")
    value = variations.get("singular") if isinstance(variations, dict) else None
    value = value or entry.get("original")
    return value if isinstance(value, str) and value.strip() and not value.startswith("@") else fallback


def recover(source):
    filenames = {"collections": "xml/gz/v855098/collections.xml.gz",
                 "quests": "xml/gz/v855098/questSettings_0.xml.gz",
                 "locale": "xml/gz/v855098/en_US.swf"}
    payloads = {key: (source / name).read_bytes() for key, name in filenames.items()}
    text = None
    for abc in abc_blocks(payloads["locale"]):
        constructor = locale_constructor(abc)
        if constructor:
            text = literal_properties(*constructor).get("text")
            break
    if not isinstance(text, dict):
        raise ValueError("The original locale text table was not recovered.")
    collection_text, quest_text = _table(text.get("Collections")), _table(text.get("Quests"))
    collection_root = ET.fromstring(zlib.decompress(payloads["collections"]))
    quest_root = ET.fromstring(zlib.decompress(payloads["quests"]))
    collections, quests = [], []
    for node in collection_root.findall("collection"):
        name = node.attrib["name"]
        items = []
        for collectible in node.findall("collectable"):
            item = dict(collectible.attrib)
            if "numneeded" in item:
                item["numneeded"] = int(item["numneeded"])
            items.append(item)
        fallback = {"breeding": "Breeding collection", "fishing": "Fishing collection"}.get(node.get("type"), "Collection")
        collections.append({"name": name, "code": node.get("code"), "type": node.get("type"),
                            "displayName": collection_display_name(name, _label(collection_text, name + "_friendlyName", fallback)),
                            "description": _label(collection_text, name + "_tooltip"), "items": items,
                            "imageCandidates": [node.get("icon")] if node.get("icon") else []})
    for node in quest_root.findall("quest"):
        name = node.attrib["name"]
        bundle = node.findtext("frontend/textBundle") or name
        tasks = []
        for task in node.findall("tasks/task"):
            action, item_type = task.get("action"), task.get("type")
            # FarmTask.getSpecificLocalizationKey keys descriptions by the
            # quest name, even when its title shares another text bundle.
            label_key = f"{name}_{action}_{item_type or ''}_Description"
            label = _label(quest_text, label_key)
            if task.get("subtype"):
                subtype_key = f"{name}_{action}_{item_type or ''}_{task.get('subtype')}_Description"
                label = _label(quest_text, subtype_key, label)
            tasks.append({"action": action, "type": item_type, "total": int(task.get("total") or 0),
                          "level": int(task.get("level") or 0), "displayName": label})
        title = _label(quest_text, bundle + "_Title")
        icon = node.findtext("frontend/icon") or "none"
        ignore_slot = node.get("ignoreSlotLimit") == "true"
        reward_view = node.findtext("frontend/rewardView")
        background = icon == "none" and ((ignore_slot and reward_view == "none") or not title)
        quests.append({"name": name, "displayName": title or "Quest", "hasLocalizedTitle": bool(title),
                       "description": _label(quest_text, bundle + "_Body"),
                       "icon": icon, "tasks": tasks, "ignoreSlotLimit": ignore_slot,
                       "rewardView": reward_view, "category": node.get("category"), "background": background,
                       "imageCandidates": [value for value in
                           (node.findtext("frontend/icon"), node.findtext("frontend/avatarHeadImage"), node.findtext("frontend/avatarBodyImage"))
                           if value and value != "none"]})
    provenance = {key: name for key, name in filenames.items()}
    provenance.update({key + "Sha256": hashlib.sha256(data).hexdigest() for key, data in payloads.items()})
    provenance["semantics"] = {
        "collectionCounters": "Classes/Collections/Collectible.as:numOwned; player.collectionCounters[itemCode]",
        "requirements": "Classes/Collections/Collectible.as:numNeeded; positive numneeded or (3-rarity)*(collectionLevel+1)",
        "completion": "Classes/Collections/Collection.as:isCollectionComplete; LE/slotmachine require positive membership",
        "claimed": "Classes/Collections/Collection.as:isCollectionStored; nonpermanent storedCollections has collection.code key",
        "questProgress": "quests.py:_advance_task and quest_component; questState.active[name].progress[taskIndex]",
    }
    return {"schemaVersion": 1, "source": provenance, "collections": collections, "quests": quests}


def copy_artwork(source, metadata, root=ROOT, *, manifests=None, assets_root=None):
    """Copy only exact raster URLs declared by each collection/quest frontend."""
    source, root = source.resolve(), root.resolve()
    if manifests is None:
        import pyamf
        manifests = []
        provenance = []
        for relative in ("xml/gz/v855098/assethash.min.amf.gz", "assethash/v9/assethash.master.amf.gz"):
            path = source / relative
            if path.is_file():
                payload = path.read_bytes()
                manifests.append((relative, pyamf.get_decoder(pyamf.AMF3, zlib.decompress(payload)).readElement()))
                provenance.append({"path": relative, "sha256": hashlib.sha256(payload).hexdigest()})
        metadata["source"]["artworkManifests"] = provenance
    cache, assets = {}, {}
    for row in metadata["collections"] + metadata["quests"]:
        row["image"] = None
        row["imageStatus"] = "unavailable"
        row.pop("imageLogical", None)
        if row.get("background") is True:
            row["imageStatus"] = "hidden-background"
            continue
        for logical in row.get("imageCandidates", []):
            if Path(logical).suffix.lower() not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                continue
            if logical not in cache:
                original, reason, manifest, _ = resolve_from_manifests(source, manifests, logical, assets_root=assets_root)
                record = None
                if original:
                    payload = original.read_bytes()
                    try:
                        info = raster_info(payload)
                    except ValueError:
                        info = None
                    if info:
                        digest = hashlib.sha256(payload).hexdigest()
                        relative = "static/assets/helper-art/" + digest + "." + info["format"]
                        destination = root / relative
                        if destination.is_symlink() or not destination.resolve().is_relative_to(root.resolve()):
                            raise ValueError("Helper artwork must remain inside GodBarn.")
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes(payload)
                        record = {"path": "/" + relative, "logical": logical,
                                  "sourcePath": (original.relative_to(Path(assets_root).resolve()).as_posix()
                                                 if assets_root else original.relative_to(source).as_posix()),
                                  "sha256": digest, "sourceSha256": digest, "bytes": len(payload),
                                  "manifest": manifest, "width": info["width"], "height": info["height"],
                                  "method": "Exact original declared raster"}
                        assets[logical] = record
                cache[logical] = record
            record = cache[logical]
            if record:
                row.update(image=record["path"], imageStatus="exact", imageLogical=logical)
                break
    metadata["assets"] = list(assets.values())
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Read-only FarmVillage source directory")
    args = parser.parse_args()
    source = args.source.expanduser().resolve()
    if source == ROOT or ROOT in source.parents:
        raise SystemExit("The source must be outside GodBarn.")
    result = recover(source)
    copy_artwork(source, result)
    destination = ROOT / "data/helpers.json"
    if destination.is_symlink():
        raise SystemExit("Helper metadata destination must not be a symbolic link.")
    destination.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"Recovered {len(result['collections'])} collections and {len(result['quests']):,} quests.")


if __name__ == "__main__":
    main()
