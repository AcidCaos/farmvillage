#!/usr/bin/env python3
"""Index God Barn's catalog rows that no Market tab lists, with Home overlay status.

Reads pristine original item records and imports the reviewed, read-only
heritage_pricing module. Writes only the explicitly selected resource output.
The companion never imports game code: it reads this index and each row's own
archived marketEntries. Run after prepare_archive.py, and again whenever
heritage_pricing.py changes. No generated cache, player save or game server is used.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import re
import zlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from catalog_tools import UNTABBED_ORIGINS, has_market_entry  # noqa: E402

SOURCE = "xml/gz/v855038/items_opt.amf"


def _scalar(value):
    return value[0] if isinstance(value, list) and value else value


def _positive(value):
    value = _scalar(value)
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        amount = int(float(value))
    except (TypeError, ValueError, OverflowError):
        return None
    return amount if amount > 0 else None


def _world_names(record):
    """World requirement names, in record order, read before the overlay rehomes them."""
    names = []

    def visit(node):
        if isinstance(node, dict):
            name = node.get("name")
            if node.get("className") == "World" and isinstance(name, str) and name and name not in names:
                names.append(name)
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(record.get("requirements"))
    return names


def _home_price(record):
    market = _scalar(record.get("market")) or None
    if market == "cash":
        currency, amount = "cash", _positive(record.get("cash"))
    elif market in (None, "coins"):
        currency, amount = "coins", _positive(record.get("cost"))
    else:
        return None
    return {"currency": currency, "amount": amount} if amount else None


def first_indexes(records):
    """Map each name to its first record, the one God Barn and the game lookup use."""
    first = {}
    for index, record in enumerate(records):
        if isinstance(record, dict) and isinstance(record.get("name"), str):
            first.setdefault(record["name"], index)
    return first


def verify_against_catalog(records, first, catalog_path):
    """Refuse to index if God Barn's copied rows disagree with the game records."""
    copied = {}
    for item in json.loads(catalog_path.read_text(encoding="utf-8")):
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            copied.setdefault(item["name"], item)
    if set(copied) != set(first):
        raise SystemExit("God Barn's catalog and the FarmVillage records name different items. Run prepare_archive.py first.")
    for name, index in first.items():
        raw = (copied[name].get("archive") or {}).get("raw") or {}
        if has_market_entry(records[index]) != has_market_entry(raw, item_type=copied[name].get("type")):
            raise SystemExit("Market tab data disagrees for " + name + ". Run prepare_archive.py first.")
    return len(copied)


def classify(records, first, heritage, *, served=None):
    """Return the origin entry for every name that no Market tab lists.

    Worlds and recovered prices are read before the overlay rewrites the records.
    The overlay itself is applied in memory only; the records are not written back.
    """
    pristine = {}
    for name, index in first.items():
        record = records[index]
        if not has_market_entry(record):
            priced = _positive(record.get("cash")) or _positive(record.get("cost"))
            pristine[name] = (_world_names(record), bool(priced))
    derived = None
    if served is None:
        heritage.apply(records, server=True)
    else:
        patches = heritage.plan(records, served=served)[0] if heritage.ENABLED else {}
        derived = set(patches)
        for index, patch in patches.items():
            heritage._mutate(records[index], patch)
    origins = {}
    for name, (worlds, priced) in pristine.items():
        record = records[first[name]]
        overlaid = first[name] in derived if derived is not None else heritage.is_overlaid(record)
        if overlaid:
            entry = {"origin": "heritage"}
            home = _home_price(record)
            if home:
                entry["home"] = home
        elif not worlds and not priced:
            entry = {"origin": "exclusive"}
        else:
            entry = {"origin": "other"}
        if worlds:
            entry["worlds"] = worlds
        origins[name] = entry
    return origins


def generate(source, root=ROOT, *, policy_root=None):
    """Generate from pristine original AMF without caches, farms or server imports."""
    import pyamf
    source, root = Path(source).resolve(), Path(root).resolve()
    policy_root = Path(policy_root).resolve() if policy_root else ROOT.parent / "FarmVillage"
    for protected in (source, ROOT, policy_root):
        if root == protected or root in protected.parents or protected in root.parents:
            raise ValueError("Untabbed metadata output must remain separate from original and authored source")
    payload = (source / SOURCE).read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    raw = pyamf.get_decoder(pyamf.AMF3, zlib.decompress(payload)).readElement()
    records = raw["settings"]["items"]["item"]
    first = first_indexes(records)
    names = verify_against_catalog(records, first, root / "data/catalog.json")
    policy = policy_root / "heritage_pricing.py"
    spec = importlib.util.spec_from_file_location("bootstrap_heritage_pricing", policy)
    heritage = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(heritage)
    template = (policy_root / "templates/play.html").read_text(encoding="utf-8")
    served = {key: int(value) for key, value in re.findall(r'"(fv_[A-Za-z0-9_]+)":\s*(-?\d+)', template)}
    origins = classify(records, first, heritage, served=served)
    counts = {origin: sum(1 for entry in origins.values() if entry["origin"] == origin)
              for origin in UNTABBED_ORIGINS}
    document = {"schema": 1, "source": {"file": SOURCE, "sha256": digest,
                "records": len(records), "names": names},
                "heritage": {"enabled": bool(heritage.ENABLED), "digest": heritage.overlay_digest(),
                             "servedTemplateSHA256": hashlib.sha256(template.encode()).hexdigest()},
                "counts": dict(counts, untabbed=len(origins)), "items": dict(sorted(origins.items()))}
    target = root / "data/untabbed.json"
    target.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n")
    return document

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Read-only original game resource root")
    parser.add_argument("--root", type=Path, required=True, help="Generated companion resource directory")
    parser.add_argument("--policy-root", type=Path, help="Reviewed FarmVillage authored source")
    args = parser.parse_args(argv)
    document = generate(args.source, args.root, policy_root=args.policy_root)
    counts = document["counts"]
    print(f"Indexed {counts['untabbed']:,} untabbed items: {counts['heritage']:,} heritage, "
          f"{counts['exclusive']:,} original exclusive, {counts['other']:,} other.")


if __name__ == "__main__":
    main()
