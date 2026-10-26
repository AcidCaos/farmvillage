#!/usr/bin/env python3
"""Recover every locally available item thumbnail into God Barn's own catalog.

The original item AMF and asset manifest are read-only evidence. No FarmVillage
modules are imported. This pass has no sampling or byte limits, never guesses
an asset by a similar filename, and preserves existing catalog/history fields.
Only third-party pyamf is required to read the archived snapshots.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]
MISSING_IMAGE = "/static/assets/ui/missing-art.svg"
RASTER_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_HASH = re.compile(r"[0-9a-fA-F]{32,64}\Z")
_ROLE_ORDER = {"icon": 0, "thumbnail": 1, "market": 2, "feed": 3}


def sha256(payload):
    return hashlib.sha256(payload).hexdigest()


def first_records(records):
    result = {}
    duplicates = []
    for index, record in enumerate(records):
        if not isinstance(record, dict) or not isinstance(record.get("name"), str):
            continue
        name = record["name"]
        if name in result:
            duplicates.append({"name": name, "code": record.get("code"), "recordIndex": index,
                               "lookupRecordIndex": result[name][0],
                               "lookupCode": result[name][1].get("code")})
        else:
            result[name] = (index, record)
    return result, duplicates


def raster_candidates(record):
    images = record.get("image") or []
    if isinstance(images, dict):
        images = [images]
    if not isinstance(images, list):
        return []
    candidates = []
    seen = set()
    for image in images:
        if not isinstance(image, dict) or not isinstance(image.get("url"), str):
            continue
        logical = image["url"]
        if PurePosixPath(logical).suffix.lower() not in RASTER_SUFFIXES or logical in seen:
            continue
        seen.add(logical)
        candidates.append({"logical": logical, "role": str(image.get("name") or "unspecified")})
    # Source order breaks ties. A feed is legitimate art for this exact item,
    # but an available market icon is the preferred preview.
    return sorted(candidates, key=lambda image: _ROLE_ORDER.get(image["role"], 4))


def resolve_asset(source, manifest, logical, *, assets_root=None):
    """Resolve only the exact declared URL through the original asset manifest."""
    if not isinstance(logical, str):
        return None, "invalid-logical-path"
    path = PurePosixPath(logical.removeprefix("assets/"))
    if (path.is_absolute() or ".." in path.parts or len(path.parts) < 2
            or "\\" in logical or ":" in logical):
        return None, "invalid-logical-path"
    group, relative = path.parts[0], PurePosixPath(*path.parts[1:])
    group_map = manifest.get(group, {})
    archive_hash = group_map.get(relative.as_posix()) if isinstance(group_map, dict) else None
    if not isinstance(archive_hash, str) or not _HASH.fullmatch(archive_hash):
        return None, "not-in-manifest"
    asset_root = Path(assets_root).resolve() if assets_root else (source / "LocalData/assets").resolve()
    original = asset_root / group / relative.parent / (archive_hash + relative.suffix)
    if original.is_symlink() or not original.resolve().is_relative_to(asset_root):
        return None, "unsafe-asset-path"
    if not original.is_file():
        return None, "local-file-missing"
    return original, None


def resolve_from_manifests(source, manifests, logical, *, assets_root=None):
    if isinstance(manifests, dict):
        manifests = [("assethash/v9/assethash.master.amf.gz", manifests)]
    attempts = []
    for name, manifest in manifests:
        path, reason = resolve_asset(source, manifest, logical, assets_root=assets_root)
        attempts.append({"file": name, "status": "missing" if reason else "exact",
                         **({"reason": reason} if reason else {})})
        if path:
            return path, None, name, attempts
        # The client chooses a hash by declaration before requesting the file.
        # A missing local delta file must not turn into another artwork revision.
        if reason != "not-in-manifest":
            return None, reason, name, attempts
    reasons = [attempt["reason"] for attempt in attempts]
    reason = next((value for value in reasons if value != "not-in-manifest"), "not-in-manifest")
    return None, reason, None, attempts


def manifest_overlap(manifests):
    seen, overlaps, conflicts = {}, 0, []
    for name, manifest in manifests:
        for group, values in manifest.items():
            if not isinstance(values, dict):
                continue
            for relative, digest in values.items():
                logical = "assets/" + str(group) + "/" + str(relative)
                if logical in seen:
                    overlaps += 1
                    earlier_name, earlier_digest = seen[logical]
                    if earlier_digest != digest:
                        conflicts.append({"logical": logical, "earlierManifest": earlier_name,
                                          "earlierHash": earlier_digest, "laterManifest": name,
                                          "laterHash": digest})
                else:
                    seen[logical] = (name, digest)
    return {"overlappingLogicalPaths": overlaps, "conflictingLogicalPaths": len(conflicts),
            "conflicts": conflicts}


def raster_info(payload):
    """Validate raster structure before presenting a file as exact artwork."""
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        offset, size, image_size, idat = 8, len(payload), None, False
        while offset + 12 <= size:
            length = struct.unpack_from(">I", payload, offset)[0]
            kind = payload[offset + 4:offset + 8]
            end = offset + 8 + length
            if end + 4 > size:
                raise ValueError("truncated PNG")
            content = payload[offset + 8:end]
            expected = struct.unpack_from(">I", payload, end)[0]
            if zlib.crc32(kind + content) & 0xffffffff != expected:
                raise ValueError("PNG checksum mismatch")
            if kind == b"IHDR":
                if image_size is not None or length != 13 or offset != 8:
                    raise ValueError("invalid PNG header")
                image_size = struct.unpack_from(">II", content)
            if kind == b"IDAT":
                idat = True
            offset = end + 4
            if kind == b"IEND":
                if length or not image_size or not all(image_size) or not idat:
                    raise ValueError("invalid PNG content")
                return {"format": "png", "width": image_size[0], "height": image_size[1]}
        raise ValueError("missing PNG end marker")
    if payload.startswith((b"GIF87a", b"GIF89a")) and len(payload) >= 14 and payload[-1:] == b";":
        width, height = struct.unpack_from("<HH", payload, 6)
        if width and height:
            return {"format": "gif", "width": width, "height": height}
    if payload.startswith(b"\xff\xd8") and payload[-2:] == b"\xff\xd9":
        offset = 2
        while offset + 4 < len(payload):
            if payload[offset] != 255:
                break
            while offset < len(payload) and payload[offset] == 255:
                offset += 1
            marker = payload[offset]
            offset += 1
            if marker in (1, *range(0xd0, 0xd9)):
                continue
            length = struct.unpack_from(">H", payload, offset)[0]
            if length < 2 or offset + length > len(payload):
                break
            if marker in (0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf) and length >= 7:
                height, width = struct.unpack_from(">HH", payload, offset + 3)
                if width and height:
                    return {"format": "jpg", "width": width, "height": height}
            offset += length
    if (payload.startswith(b"RIFF") and len(payload) >= 30 and payload[8:12] == b"WEBP"
            and struct.unpack_from("<I", payload, 4)[0] + 8 == len(payload)):
        kind, content = payload[12:16], payload[20:]
        if kind == b"VP8X" and len(content) >= 10:
            width, height = int.from_bytes(content[4:7], "little") + 1, int.from_bytes(content[7:10], "little") + 1
            return {"format": "webp", "width": width, "height": height}
        if kind == b"VP8 " and len(content) >= 10 and content[3:6] == b"\x9d\x01\x2a":
            width, height = struct.unpack_from("<HH", content, 6)
            if width & 0x3fff and height & 0x3fff:
                return {"format": "webp", "width": width & 0x3fff, "height": height & 0x3fff}
        if kind == b"VP8L" and len(content) >= 5 and content[0] == 0x2f:
            bits = int.from_bytes(content[1:5], "little")
            return {"format": "webp", "width": (bits & 0x3fff) + 1, "height": ((bits >> 14) & 0x3fff) + 1}
    raise ValueError("unrecognized or damaged raster")


def _destination(root, relative):
    root = root.resolve()
    path = root / relative
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError("Output must remain inside God Barn: " + relative)
    return path


def _write_verified(root, relative, payload, digest):
    target = _destination(root, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and sha256(target.read_bytes()) == digest:
        return
    temporary = target.with_name(target.name + ".recovering")
    if temporary.is_symlink():
        raise ValueError("Temporary output must not be a symlink")
    temporary.write_bytes(payload)
    if sha256(temporary.read_bytes()) != digest:
        temporary.unlink()
        raise ValueError("Copied artwork failed byte verification")
    temporary.replace(target)


def _labels(names):
    if not isinstance(names, dict):
        raise ValueError("Names must be an object keyed by internal item name")
    for field in ("items", "names"):
        if isinstance(names.get(field), dict):
            return names[field]
    return names


def apply_label(row, labels):
    """Apply attributed text only; never alter an item's internal identity."""
    name = row.get("name")
    label = labels.get(name)
    if isinstance(label, str):
        label = {"displayName": label}
    if isinstance(label, dict):
        for key in ("displayName", "description", "labelSource", "descriptionSource", "localizationKey"):
            value = label.get(key)
            if isinstance(value, (str, dict)) and value:
                row[key] = value
        return int(bool(label.get("displayName")))
    row["displayName"] = name
    row["labelSource"] = "internal-name"
    row.pop("localizationKey", None)
    return 0


def recover(catalog, records, manifest, source, root, *, names=None, write_assets=False, progress=None, assets_root=None, portable_provenance=False):
    """Return repaired rows, exhaustive audit and asset provenance.

    Existing rows, including duplicate source records, survive in their original
    order. Lookup/artwork uses the first source record for each internal name.
    The caller decides when to atomically publish the finished catalog.
    """
    source, root = Path(source).resolve(), Path(root).resolve()
    if source == root or source.is_relative_to(root) or root.is_relative_to(source):
        raise ValueError("The original archive and God Barn outputs must be separate")
    originals, duplicates = first_records(records)
    labels = _labels(names) if names is not None else {}
    by_type, reasons = defaultdict(Counter), Counter()
    recovered, missing, output_assets, cache = {}, [], {}, {}
    used_paths = {}
    processed_bytes = 0
    for count, (name, (index, record)) in enumerate(originals.items(), 1):
        candidates, attempts = raster_candidates(record), []
        selected = None
        for candidate in candidates:
            logical = candidate["logical"]
            if logical not in cache:
                original, failure, manifest_name, manifest_attempts = resolve_from_manifests(source, manifest, logical, assets_root=assets_root)
                if failure:
                    cache[logical] = (None, failure, manifest_attempts)
                else:
                    try:
                        payload = original.read_bytes()
                        info = raster_info(payload)
                        digest = sha256(payload)
                    except (OSError, ValueError, struct.error) as error:
                        cache[logical] = (None, "invalid-raster: " + str(error), manifest_attempts)
                    else:
                        suffix = "." + info["format"]
                        filename = original.name if original.suffix.lower() == suffix else digest + suffix
                        relative = "static/assets/items/" + filename
                        if relative in used_paths and used_paths[relative] != digest:
                            relative = "static/assets/items/" + digest + suffix
                        used_paths[relative] = digest
                        if write_assets:
                            _write_verified(root, relative, payload, digest)
                        entry = {"logical": logical, "originalPath": str(original), "path": relative,
                                 "bytes": len(payload), "sha256": digest,
                                 "width": info["width"], "height": info["height"], "manifest": manifest_name}
                        if portable_provenance:
                            archive = Path(assets_root).resolve() if assets_root else source / "LocalData/assets"
                            entry["assetRelativePath"] = original.relative_to(archive).as_posix()
                        cache[logical] = (entry, None, manifest_attempts)
                        if relative not in output_assets:
                            output_assets[relative] = entry
                            processed_bytes += len(payload)
            entry, failure, manifest_attempts = cache[logical]
            attempt = dict(candidate, status="missing" if failure else "exact")
            if failure:
                attempt["reason"] = failure
                attempt["manifestAttempts"] = manifest_attempts
            attempts.append(attempt)
            if not failure:
                selected = dict(entry)
                selected.update(status="exact", role=candidate["role"], sourceRecordIndex=index,
                                sourceFileHash=Path(entry["originalPath"]).stem)
                selected.pop("originalPath", None)
                selected["image"] = "/" + selected.pop("path")
                break
        if selected is None:
            reason = ("no-declared-raster" if not candidates else "declared-raster-unavailable")
            selected = {"status": "missing", "sourceRecordIndex": index, "reason": reason,
                        "image": MISSING_IMAGE, "candidates": attempts}
            missing.append({"name": name, "code": record.get("code"), "type": record.get("type", "unknown"),
                            "sourceRecordIndex": index, "reason": reason, "candidates": attempts})
            reasons[reason] += 1
        elif len(attempts) > 1:
            selected["candidates"] = attempts
        recovered[name] = selected
        kind = str(record.get("type") or "unknown")
        by_type[kind]["uniqueItems"] += 1
        by_type[kind][selected["status"]] += 1
        if progress and count % 10000 == 0:
            progress({"processed": count, "total": len(originals), "exact": count - len(missing),
                      "uniqueFiles": len(output_assets), "bytes": processed_bytes})

    rows, unmatched, applied_names, previous_exact, changes = [], [], 0, 0, 0
    seen_rows = set()
    for row_index, original_row in enumerate(catalog):
        row = dict(original_row)
        name = row.get("name")
        prior_exact = bool(row.get("hasOriginalThumbnail"))
        previous_exact += prior_exact
        artwork = recovered.get(name)
        if artwork is None:
            artwork = {"status": "missing", "reason": "no-source-record", "image": MISSING_IMAGE}
            unmatched.append({"name": name, "code": row.get("code"), "catalogRecordIndex": row_index})
        row["image"] = artwork["image"]
        row["hasOriginalThumbnail"] = artwork["status"] == "exact"
        row["artwork"] = {key: value for key, value in artwork.items() if key != "image"}
        if name in seen_rows:
            row["artwork"]["duplicateLookup"] = True
        seen_rows.add(name)
        if row["image"] != original_row.get("image") or row["hasOriginalThumbnail"] != prior_exact:
            changes += 1
        if names is not None:
            applied_names += apply_label(row, labels)
        rows.append(row)
        by_type[str(row.get("type") or "unknown")]["catalogRecords"] += 1

    audit = {"schema": 1, "preparedAt": datetime.now(timezone.utc).isoformat(),
             "sourceReadOnly": True, "networkUsed": False, "sourceModulesImported": False,
             "policy": "Only exact declared URLs resolved through the original manifest. First source record wins name lookup; all catalog rows are retained. Missing artwork uses a neutral placeholder. No sampling or byte cap.",
             "sourceRecords": len(records), "sourceUniqueItems": len(originals), "catalogRecords": len(rows),
             "catalogUniqueItems": len(seen_rows), "previousExactRecords": previous_exact,
             "exactRecords": sum(row["hasOriginalThumbnail"] for row in rows),
             "exactUniqueItems": len(recovered) - len(missing), "missingUniqueItems": len(missing),
             "uniqueArtworkFiles": len(output_assets), "artworkBytes": processed_bytes,
             "changedArtworkRecords": changes, "appliedNameRecords": applied_names,
             "byType": {kind: dict(counts) for kind, counts in sorted(by_type.items())},
             "missingReasons": dict(reasons), "duplicateSourceRecords": duplicates,
             "catalogWithoutSource": unmatched, "unresolved": missing}
    audit["unresolvedAssetReasons"] = dict(Counter(candidate["reason"]
        for entry in missing for candidate in entry["candidates"] if candidate.get("reason")))
    audit["artworkManifests"] = dict(Counter(entry["manifest"] for entry in recovered.values()
                                            if entry.get("manifest")))
    if isinstance(names, dict) and isinstance(names.get("source"), dict):
        audit["localizationSource"] = dict(names["source"])
        audit["labelRecoveryVersion"] = names.get("recoveryVersion")
        audit["unresolvedLabels"] = names.get("unresolvedLabels", [])
    if portable_provenance:
        audit.pop("preparedAt", None)
        for asset in output_assets.values():
            asset.pop("originalPath", None)
    return rows, audit, list(output_assets.values())


def atomic_json(root, relative, value, *, compact=False):
    path = _destination(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".recovering")
    if temporary.is_symlink():
        raise ValueError("Temporary output must not be a symlink")
    temporary.write_text(json.dumps(value, ensure_ascii=False,
                                    separators=(",", ":") if compact else None,
                                    indent=None if compact else 2) + "\n")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Read-only original FarmVillage archive")
    parser.add_argument("--root", type=Path, default=ROOT, help="God Barn output directory")
    parser.add_argument("--names", type=Path, help="Optional localized names JSON keyed by internal item name")
    parser.add_argument("--audit-only", action="store_true", help="Inspect all original artwork without writing any files")
    args = parser.parse_args()
    source, root = args.source.expanduser().resolve(), args.root.expanduser().resolve()
    import pyamf  # The archived AMF decoder only; never import original game modules.
    item_file = source / "xml/gz/v855038/items_opt.amf"
    # Original Init.AssetHashInit assigns min to deltaData, and the original
    # Managers.AssetHashManager.getAssetPath checks deltaData before masterData.
    manifest_files = [source / "xml/gz/v855098/assethash.min.amf.gz", source / "assethash/v9/assethash.master.amf.gz"]
    item_bytes = item_file.read_bytes()
    source_bytes = [(item_file, item_bytes)]
    records = pyamf.get_decoder(pyamf.AMF3, zlib.decompress(item_bytes)).readElement()["settings"]["items"]["item"]
    manifest = []
    for path in manifest_files:
        if not path.is_file():
            continue
        payload = path.read_bytes()
        source_bytes.append((path, payload))
        manifest.append((str(path.relative_to(source)), pyamf.get_decoder(pyamf.AMF3, zlib.decompress(payload)).readElement()))
    if not manifest:
        raise ValueError("No original asset manifests are available")
    overlap = manifest_overlap(manifest)
    print(json.dumps({key: value for key, value in overlap.items() if key != "conflicts"}), flush=True)
    catalog = json.loads((root / "data/catalog.json").read_text())
    names_file = args.names or root / "data/localized-labels.json"
    if args.names and not names_file.is_file():
        raise FileNotFoundError("The requested labels file is missing: " + str(names_file))
    names_bytes = names_file.read_bytes() if names_file.is_file() else None
    names = json.loads(names_bytes) if names_bytes is not None else None
    if not args.names:
        locale_file = source / "xml/gz/v855098/en_US.swf"
        locale_bytes = locale_file.read_bytes()
        locale_digest = sha256(locale_bytes)
        if (not isinstance(names, dict) or names.get("source", {}).get("sha256") != locale_digest
                or names.get("recoveryVersion", 0) < 2):
            from recover_labels import recover as recover_labels
            names = recover_labels(locale_bytes)
            names_bytes = (json.dumps(names, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
            if not args.audit_only:
                atomic_json(root, "data/localized-labels.json", names, compact=True)
    rows, audit, assets = recover(catalog, records, manifest, source, root, names=names,
                                  write_assets=not args.audit_only,
                                  progress=lambda value: print(json.dumps(value), flush=True))
    audit["sources"] = [{"file": str(path.relative_to(source)), "sha256": sha256(payload)}
                         for path, payload in source_bytes]
    audit["manifestOverlap"] = overlap
    audit["manifestPolicy"] = "Original client precedence: version min (deltaData) first, master only when no delta declaration exists. A missing selected local file stays missing; no different hash revision is substituted. Conflicting logical path hashes are recorded explicitly."
    audit["namesSource"] = {"file": names_file.name, "sha256": sha256(names_bytes)}
    if not args.audit_only:
        provenance_file = root / "data/provenance.json"
        provenance = json.loads(provenance_file.read_text())
        retained = {entry["path"]: entry for entry in provenance.get("assets", [])}
        retained.update({entry["path"]: entry for entry in assets})
        provenance.update(assets=list(retained.values()), illustratedItems=audit["exactRecords"],
                          catalogItems=len(rows), thumbnailBytes=audit["artworkBytes"],
                          categoryFallbacks={}, catalogRecovery="data/catalog-audit.json")
        # Publish evidence before rows; a partial interrupted pass can be rerun.
        atomic_json(root, "data/provenance.json", provenance)
        atomic_json(root, "data/catalog-audit.json", audit, compact=True)
        atomic_json(root, "data/catalog.json", rows, compact=True)
    print(json.dumps({key: value for key, value in audit.items()
                      if key not in ("unresolved", "policy", "sources")}, indent=2))


if __name__ == "__main__":
    main()
