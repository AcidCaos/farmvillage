#!/usr/bin/env python3
"""Verify reconstructed resources; optional HTTP checks do not qualify gameplay."""
from __future__ import annotations
import argparse
import functools
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path, PurePosixPath
import re
import sys
import threading
from urllib.request import urlopen
import zlib

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import prepare_archive
from prepare_assets import number
from bootstrap_resources import REQUIRED as REQUIRED_INPUTS

EXPECTED_RECORDS = 111206
REQUIRED_METADATA = (
    "catalog", "rules", "provenance", "ui-assets", "localized-labels",
    "catalog-audit", "asset-map", "archive-provenance", "historical-prizes",
    "encyclopedia", "helpers", "progression", "untabbed",
)


def _read_json(root, name):
    return json.loads((root / name).read_text())


def _safe(root, name):
    relative = PurePosixPath(name.lstrip("/"))
    if relative.is_absolute() or ".." in relative.parts or "\\" in name or not relative.parts:
        raise ValueError("Unsafe resource reference: " + name)
    path = root
    for part in relative.parts:
        path /= part
        if path.is_symlink():
            raise ValueError("Linked resource refused: " + name)
    return path


def referenced_ui(source):
    refs = set()
    for name in ("style.css", "farmville.css"):
        path = source / "static" / name
        if not path.is_file():
            continue
        for ref in re.findall(r'url\(\s*[\'"]?([^\'"\)]+)', path.read_text()):
            ref = ref.strip()
            if ref.startswith("assets/"):
                refs.add("static/" + ref)
    for name in ("index.html", "error.html"):
        path = source / "static" / name
        if path.is_file():
            refs.update(re.findall(r'(?:src|href)=[\'"](static/assets/[^\'"?#]+)', path.read_text()))
    app = source / "static/app.js"
    if app.is_file():
        text = app.read_text()
        names = set(re.findall(r"img\('([A-Za-z0-9_-]+)'", text))
        for table in re.findall(r"\bconst\s+(?:nav|cards)\s*=\s*(\[.*?\]);", text, re.S):
            names.update(re.findall(r"\['[^']+','([A-Za-z0-9_-]+)','", table))
        names.update(re.findall(r"balanceCard\('[^']+','[^']+','([A-Za-z0-9_-]+)'", text))
        names.update(re.findall(r"\['(?:collection|mastery|ribbon|animals|trees)','[^']+','([A-Za-z0-9_-]+)'\]", text))
        refs.update("static/assets/ui/" + name + ".png" for name in names)
        refs.update(re.findall(r'/((?:static/brand/)[A-Za-z0-9_@./-]+)', text))
        refs.add("static/assets/ui/missing-art.svg")
    return refs


def _images(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"image", "url", "path"} and isinstance(item, str) and item.startswith("/static/"):
                yield item.lstrip("/")
            yield from _images(item)
    elif isinstance(value, list):
        for item in value:
            yield from _images(item)


def verify(resources, *, game_root=None, companion_source=None, expected_records=EXPECTED_RECORDS, http=False, metadata_only=False):
    resources = Path(resources).resolve()
    companion_source = Path(companion_source).resolve() if companion_source else SCRIPTS.parent
    receipt = _read_json(resources, "RESOURCE_BUILD.json")
    if receipt.get("kind") != "source-reconstructed-companion-resources" or receipt.get("containsPlayerState") is not False:
        raise ValueError("Not a clean reconstructed resource set")
    files = receipt["files"]
    if set(receipt.get("sourceInputs", {})) != set(REQUIRED_INPUTS):
        raise ValueError("Original source inventory is incomplete")
    required = {"data/" + name + ".json" for name in REQUIRED_METADATA}
    if receipt.get("skinPrepared"):
        required.update(("data/skin-assets.json", "data/brand-provenance.json",
                         "static/brand/god-barn-logo-v2@3x.png"))
    if required - set(files):
        raise ValueError("Required generated resources are absent: " + ", ".join(sorted(required - set(files))))
    for path in resources.rglob("*"):
        if path.is_symlink():
            raise ValueError("Linked generated resource refused")
    actual = {p.relative_to(resources).as_posix() for p in resources.rglob("*")
              if p.is_file() and p.name != ".DS_Store"}
    if actual != set(files) | {"RESOURCE_BUILD.json"}:
        raise ValueError("Resource inventory has missing or unexpected files")
    for name, seal in files.items():
        if name.startswith("/"):
            raise ValueError("Resource inventory paths must be relative")
        path = _safe(resources, name)
        if any(part in {"saves", "workspace", "snapshots", ".git"} for part in Path(name).parts):
            raise ValueError("Player/history path in generated resources: " + name)
        payload = path.read_bytes()
        if len(payload) != seal["bytes"] or hashlib.sha256(payload).hexdigest() != seal["sha256"]:
            raise ValueError("Generated resource differs: " + name)
    catalog = _read_json(resources, "data/catalog.json")
    if len(catalog) != receipt["catalogRecords"] or (expected_records is not None and len(catalog) != expected_records):
        raise ValueError("Original catalogue record count differs")
    if game_root is not None:
        import pyamf
        game_root = Path(game_root).resolve()
        for name, seal in receipt["sourceInputs"].items():
            source = _safe(game_root, name)
            payload = source.read_bytes()
            if len(payload) != seal["bytes"] or hashlib.sha256(payload).hexdigest() != seal["sha256"]:
                raise ValueError("Original resource differs from receipt: " + name)
        payload = _safe(game_root, "xml/gz/v855038/items_opt.amf").read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        expected_digest = receipt["sourceInputs"]["xml/gz/v855038/items_opt.amf"]["sha256"]
        if digest != expected_digest:
            raise ValueError("Original item source differs from resource receipt")
        records = pyamf.get_decoder(pyamf.AMF3, zlib.decompress(payload)).readElement()["settings"]["items"]["item"]
        if len(records) != len(catalog):
            raise ValueError("Original rows were lost or added")
        contexts = {}
        for index, original in enumerate(records):
            contexts.setdefault(original["name"], prepare_archive.context(original, index, digest))
        for row, original in zip(catalog, records):
            for key in ("name", "code", "type", "subtype", "className"):
                if row.get(key, "") != original.get(key, ""):
                    raise ValueError("Original row identity/order changed: " + str(original.get("name")))
            for key in ("cost", "cash", "growTime", "squares", "sizeX", "sizeY", "coinYield", "plantXp", "requiredLevel"):
                if row.get(key) != number(original.get(key)):
                    raise ValueError("Original numeric fact changed: " + str(original.get("name")) + "/" + key)
            if row.get("archive") != contexts[original["name"]]:
                raise ValueError("Normalized archive facts changed: " + str(original.get("name")))
    provenance = _read_json(resources, "data/provenance.json")
    if provenance.get("containsPlayerState") is not False or "save" in provenance or "sourceDirectory" in provenance:
        raise ValueError("Provenance contains previous player/workstation state")
    historical = _read_json(resources, "data/historical-prizes.json")
    encyclopedia = _read_json(resources, "data/encyclopedia.json")
    if len(historical.get("shelves", [])) != receipt["historicalPrizeShelves"] or len(encyclopedia.get("shelves", [])) != receipt["historicalPrizeShelves"]:
        raise ValueError("Historical prize shelf count differs")
    refs = set() if metadata_only else referenced_ui(companion_source)
    for name in ("catalog.json", "helpers.json", "progression.json", "ui-assets.json", "encyclopedia.json"):
        path = resources / "data" / name
        if path.is_file():
            refs.update(_images(json.loads(path.read_text())))
    for ref in refs:
        if not _safe(resources, ref).is_file():
            raise ValueError("UI resource is unavailable: " + ref)
    checked_http = 0
    if http:
        class Quiet(SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(resources)))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            origin = "http://127.0.0.1:" + str(server.server_address[1])
            for ref in sorted(refs):
                with urlopen(origin + "/" + ref, timeout=10) as response:
                    if response.status != 200:
                        raise ValueError("UI resource HTTP check failed: " + ref)
                    if hashlib.sha256(response.read()).hexdigest() != files[ref]["sha256"]:
                        raise ValueError("UI resource HTTP bytes differ: " + ref)
                checked_http += 1
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=10)
    return {"status": "reconstructed-resources-verified", "catalogRecords": len(catalog),
            "verifiedFiles": len(files), "uiReferences": len(refs), "http200": checked_http,
            "originalRowsCompared": len(catalog) if game_root is not None else 0,
            "historicalPrizeShelves": receipt["historicalPrizeShelves"],
            "uiReadiness": not metadata_only, "gameplayAcceptance": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resources", type=Path, required=True)
    parser.add_argument("--game-root", type=Path)
    parser.add_argument("--companion-source", type=Path)
    parser.add_argument("--expected-records", type=int, default=EXPECTED_RECORDS)
    parser.add_argument("--http", action="store_true")
    parser.add_argument("--metadata-only", action="store_true", help="Compare metadata without claiming authored UI artwork readiness")
    args = parser.parse_args()
    print(json.dumps(verify(args.resources, game_root=args.game_root, companion_source=args.companion_source,
                            expected_records=args.expected_records, http=args.http,
                            metadata_only=args.metadata_only), indent=2))


if __name__ == "__main__":
    main()
