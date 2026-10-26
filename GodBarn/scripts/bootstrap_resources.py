#!/usr/bin/env python3
"""Generate clean God Barn resources from original preservation files, never farms."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import zlib

SCRIPTS = Path(__file__).resolve().parent
BARN_SOURCE = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
import prepare_assets
import prepare_archive
import prepare_encyclopedia
import prepare_helpers
import prepare_progression
import prepare_skin
import prepare_untabbed
import recover_catalog
import recover_labels

REQUIRED = (
    "xml/gz/v855038/items_opt.amf", "xml/gz/v855098/gameSettings.xml.gz",
    "xml/gz/v855098/gameSettingsCMS.xml.gz", "xml/gz/v855098/collections.xml.gz",
    "xml/gz/v855098/questSettings_0.xml.gz", "xml/gz/v855098/en_US.swf",
    "xml/gz/v855098/assethash.min.amf.gz", "assethash/v9/assethash.master.amf.gz",
    "embeds/Flash/v855097-855094/FV_Preloader.swf", "embeds/Flash/v855097-855094/FarmGame.swf",
)
EMPTY_HISTORY = {"schema": 1, "sources": [], "shelves": [],
                 "policy": "No independently verified historical prize curation supplied; original item facts remain available."}
MISSING_ART = '''<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160" viewBox="0 0 160 160"><rect x="2" y="2" width="156" height="156" rx="14" fill="#f6edd3" stroke="#b8a67b"/><path d="M40 100l25-25 17 17 15-15 24 23" fill="none" stroke="#9e8a61" stroke-width="5"/><text x="80" y="128" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#776543">Image unavailable</text></svg>'''


def _json(root, relative, value):
    recover_catalog.atomic_json(root, relative, value, compact=True)


def _decode(payload):
    import pyamf
    return pyamf.get_decoder(pyamf.AMF3, zlib.decompress(payload)).readElement()


def _regular(root, relative):
    path = root
    for part in Path(relative).parts:
        path /= part
        if path.is_symlink():
            raise ValueError("Linked original resource refused: " + relative)
    if not path.is_file():
        raise ValueError("Missing original resource: " + relative)
    return path


def _source_inputs(game_root):
    return {name: {"bytes": (path := _regular(game_root, name)).stat().st_size,
                   "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for name in REQUIRED}


def render_wordmark(root):
    """Author the plain companion label locally; no private brand image needed."""
    from PIL import Image, ImageDraw, ImageFont
    font_path = root / "static/assets/skin/badaboom-bb.ttf"
    font = ImageFont.truetype(str(font_path), 100) if font_path.is_file() else ImageFont.load_default(size=76)
    canvas = Image.new("RGBA", (438, 162), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    bounds = draw.textbbox((0, 0), "God Barn", font=font, stroke_width=2)
    x = (438 - (bounds[2] - bounds[0])) / 2 - bounds[0]
    y = (162 - (bounds[3] - bounds[1])) / 2 - bounds[1]
    draw.text((x + 2, y + 4), "God Barn", font=font, fill="#604323", stroke_width=3, stroke_fill="#604323")
    draw.text((x, y), "God Barn", font=font, fill="#ffdb79", stroke_width=2, stroke_fill="#7b4b25")
    target = root / "static/brand/god-barn-logo-v2@3x.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target, format="PNG", optimize=False)
    return {"path": target.relative_to(root).as_posix(), "method": "Authored text rendered locally",
            "text": "God Barn", "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}


def generate(game_root, output, *, assets_root=None, policy_root=None, historical_prizes=None, include_skin=True):
    """Build into a new destination atomically; never reuse an existing tree."""
    raw_output = Path(output).expanduser().absolute()
    for path in (raw_output, *raw_output.parents):
        if path.is_symlink():
            raise ValueError("Linked output/ancestor refused")
    if raw_output.exists():
        raise ValueError("Choose a new resource output directory; existing files are preserved")
    game_root = Path(game_root).expanduser().resolve()
    policy_root = Path(policy_root).expanduser().resolve() if policy_root else BARN_SOURCE.parent / "FarmVillage"
    for protected in (game_root, BARN_SOURCE, policy_root):
        if raw_output == protected or raw_output in protected.parents or protected in raw_output.parents:
            raise ValueError("Keep generated resources separate from game and authored source")
    if assets_root is None:
        assets_root = game_root / "assets"
        if not assets_root.is_dir():
            assets_root = game_root / "LocalData/assets"
    assets_root = Path(assets_root).expanduser().absolute()
    if assets_root.is_symlink() or not assets_root.is_dir():
        raise ValueError("A regular extracted artwork directory is required")
    assets_root = assets_root.resolve()
    if raw_output == assets_root or raw_output in assets_root.parents or assets_root in raw_output.parents:
        raise ValueError("Keep generated resources separate from extracted artwork")
    inputs = _source_inputs(game_root)
    _regular(policy_root, "heritage_pricing.py")
    _regular(policy_root, "templates/play.html")
    curation = json.loads(Path(historical_prizes).read_text()) if historical_prizes else EMPTY_HISTORY
    prepare_encyclopedia.build_overlay([], curation, "0" * 64)
    raw_output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".god-barn-resources-", dir=raw_output.parent))
    try:
        prepare_assets.prepare(game_root, temporary, assets_root=assets_root, max_thumbnails=0)
        payload = _regular(game_root, "xml/gz/v855038/items_opt.amf").read_bytes()
        records = _decode(payload)["settings"]["items"]["item"]
        digest = hashlib.sha256(payload).hexdigest()
        manifests = [(name, _decode(_regular(game_root, name).read_bytes())) for name in
                     ("xml/gz/v855098/assethash.min.amf.gz", "assethash/v9/assethash.master.amf.gz")]
        names = recover_labels.recover(_regular(game_root, "xml/gz/v855098/en_US.swf").read_bytes())
        _json(temporary, "data/localized-labels.json", names)
        catalog = json.loads((temporary / "data/catalog.json").read_text())
        catalog, audit, assets = recover_catalog.recover(
            catalog, records, manifests, game_root, temporary, names=names, write_assets=True,
            assets_root=assets_root, portable_provenance=True,
            progress=lambda value: print(json.dumps({"stage": "catalogue", **value}), flush=True))
        contexts = {}
        for index, item in enumerate(records):
            contexts.setdefault(item["name"], prepare_archive.context(item, index, digest))
        for item in catalog:
            item["archive"] = contexts[item["name"]]
        _json(temporary, "data/catalog.json", catalog)
        _json(temporary, "data/catalog-audit.json", audit)
        provenance = json.loads((temporary / "data/provenance.json").read_text())
        retained = {row["path"]: row for row in provenance.get("assets", [])}
        retained.update({row["path"]: row for row in assets})
        provenance.update(assets=list(retained.values()), catalogueRecovery="data/catalog-audit.json",
                          illustratedItems=audit["exactRecords"], catalogItems=len(catalog), categoryFallbacks={})
        _json(temporary, "data/provenance.json", provenance)
        _json(temporary, "data/asset-map.json", {row["path"]: row["assetRelativePath"]
              for row in assets if row["path"].startswith("static/assets/items/")})
        _json(temporary, "data/archive-provenance.json", {
            "schema": 1, "source": "xml/gz/v855038/items_opt.amf", "source_sha256": digest,
            "records": len(records), "collections": prepare_archive.COLLECTIONS,
            "policy": "Recovered archive offer context; original release prices remain unverified."})
        _json(temporary, "data/historical-prizes.json", curation)
        overlay = prepare_encyclopedia.build_overlay(records, curation, digest)
        overlay["curationSha256"] = hashlib.sha256((temporary / "data/historical-prizes.json").read_bytes()).hexdigest()
        _json(temporary, "data/encyclopedia.json", overlay)
        helpers = prepare_helpers.recover(game_root)
        prepare_helpers.copy_artwork(game_root, helpers, root=temporary, manifests=manifests, assets_root=assets_root)
        _json(temporary, "data/helpers.json", helpers)
        _json(temporary, "data/progression.json", prepare_progression.recover(game_root, root=temporary, assets_root=assets_root))
        prepare_untabbed.generate(game_root, temporary, policy_root=policy_root)
        placeholder = temporary / "static/assets/ui/missing-art.svg"
        placeholder.parent.mkdir(parents=True, exist_ok=True)
        placeholder.write_text(MISSING_ART + "\n")
        if include_skin:
            prepare_skin.prepare(game_root, temporary, assets_root=assets_root)
            headers = temporary / "static/assets/skin/merkin.ttf"
            if headers.is_file():
                shutil.copyfile(headers, headers.with_name("farmville-headers.ttf"))
            _json(temporary, "data/brand-provenance.json", render_wordmark(temporary))
        files = {}
        for path in sorted(temporary.rglob("*")):
            if path.name == ".DS_Store":
                continue
            if path.is_symlink():
                raise ValueError("Generated resources contain a link")
            if path.is_file():
                payload = path.read_bytes()
                files[path.relative_to(temporary).as_posix()] = {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
        result = {"schema": 1, "kind": "source-reconstructed-companion-resources",
                  "containsPlayerState": False, "sourceInputs": inputs, "files": files,
                  "ignoredFilesystemMetadata": [".DS_Store"],
                  "catalogRecords": len(catalog), "exactArtworkRecords": audit["exactRecords"],
                  "missingUniqueArtwork": audit["missingUniqueItems"],
                  "historicalPrizeShelves": len(overlay["shelves"]), "skinPrepared": include_skin,
                  "qualification": "Generated local resources only; gameplay/platform acceptance is separate"}
        _json(temporary, "RESOURCE_BUILD.json", result)
        temporary.rename(raw_output)
        return result
    except BaseException:
        shutil.rmtree(temporary)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--assets-root", type=Path)
    parser.add_argument("--policy-root", type=Path)
    parser.add_argument("--historical-prizes", type=Path)
    args = parser.parse_args()
    result = generate(args.game_root, args.output, assets_root=args.assets_root,
                      policy_root=args.policy_root, historical_prizes=args.historical_prizes)
    print(json.dumps({key: value for key, value in result.items() if key not in {"files", "sourceInputs"}}, indent=2))


if __name__ == "__main__":
    main()
