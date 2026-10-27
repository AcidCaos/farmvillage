#!/usr/bin/env python3
"""Export original archived FarmVille skin artwork without importing game code."""
import argparse
import hashlib
import io
import json
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / "FarmVillage"
DEST = ROOT / "static/assets/skin"
records = []
ASSETS = SOURCE / "LocalData/assets"
manifest = {}


def png(width, height, rgba):
    def chunk(kind, content):
        return struct.pack(">I", len(content)) + kind + content + struct.pack(">I", zlib.crc32(kind + content) & 0xffffffff)
    rows = b"".join(b"\0" + rgba[y*width*4:(y+1)*width*4] for y in range(height))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")


def tags(path):
    data = path.read_bytes()
    if data[:3] == b"CWS":
        data = data[:8] + zlib.decompress(data[8:])
    elif data[:3] != b"FWS":
        return
    off = 8 + (5 + 4 * (data[8] >> 3) + 7) // 8 + 4
    while off + 2 <= len(data):
        header = struct.unpack_from("<H", data, off)[0]
        off += 2
        kind, size = header >> 6, header & 63
        if size == 63:
            size = struct.unpack_from("<I", data, off)[0]
            off += 4
        yield kind, data[off:off+size]
        off += size


def extract(logical, filename_prefix):
    path = SOURCE / logical if logical.startswith("embeds/") else resolve(logical)
    if not path:
        return
    for kind, content in tags(path):
        if kind not in (20, 36, 35, 21):
            continue
        cid = struct.unpack_from("<H", content)[0]
        rgba = bytearray()
        if kind in (20, 36):
            fmt, width, height = struct.unpack_from("<BHH", content, 2)
            if fmt == 5:
                raw = zlib.decompress(content[7:])
                for pos in range(0, len(raw), 4):
                    a, r, g, b = raw[pos:pos+4]
                    if kind == 20:
                        a = 255
                    elif a and a < 255:
                        r, g, b = [min(255, round(c * 255 / a)) for c in (r, g, b)]
                    rgba.extend((r, g, b, a))
            elif fmt == 3:
                count = content[7] + 1
                raw = zlib.decompress(content[8:])
                size = 4 if kind == 36 else 3
                palette = raw[:count*size]
                pixels = raw[count*size:]
                stride = (width + 3) & ~3
                for y in range(height):
                    for x in range(width):
                        index = pixels[y*stride+x]
                        p = palette[index*size:(index+1)*size]
                        rgba.extend(p if size == 4 else p + b"\xff")
            else:
                continue
            name = f"{filename_prefix}-{cid}.png"
            data = png(width, height, rgba)
        else:
            # Preserve the exact archived JPEG stream. Optional SWF alpha is not
            # applied here; these are kept for inspection, not assumed cutouts.
            if kind == 35:
                size = struct.unpack_from("<I", content, 2)[0]
                data = content[6:6+size]
            else:
                data = content[2:]
            if data[:4] == b"\xff\xd9\xff\xd8":
                data = data[2:]
            if not data.startswith(b"\xff\xd8"):
                continue
            name = f"{filename_prefix}-{cid}.jpg"
            if kind == 35 and content[6+size:]:
                original = Image.open(io.BytesIO(data)).convert("RGBA")
                alpha = zlib.decompress(content[6+size:])
                if len(alpha) == original.width * original.height:
                    original.putalpha(Image.frombytes("L", original.size, alpha))
                    image_bytes = io.BytesIO()
                    original.save(image_bytes, "PNG")
                    data = image_bytes.getvalue()
                    name = f"{filename_prefix}-{cid}.png"
        (DEST / name).write_bytes(data)
        records.append({"path": "/static/assets/skin/"+name, "logical": logical,
                        "sourcePath": str(path), "swfCharacterId": cid,
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "method": "Original SWF raster symbol with original alpha exported to PNG" if name.endswith(".png") else "Original embedded JPEG bytes"})


def resolve(logical):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from recover_catalog import resolve_from_manifests
    path, reason, _, _ = resolve_from_manifests(SOURCE, manifest, logical, assets_root=ASSETS)
    return path if reason is None else None


def prepare(source, root=ROOT, *, assets_root=None):
    """Recover original skin from explicit game files; no import-time I/O."""
    global SOURCE, ROOT, DEST, ASSETS, manifest, records, Image
    from PIL import Image
    import pyamf
    SOURCE, ROOT = Path(source).resolve(), Path(root).resolve()
    ASSETS = Path(assets_root).resolve() if assets_root else SOURCE / "LocalData/assets"
    if SOURCE == ROOT or ROOT in SOURCE.parents or SOURCE in ROOT.parents:
        raise ValueError("Game resources and skin output must be separate.")
    DEST = ROOT / "static/assets/skin"
    DEST.mkdir(parents=True, exist_ok=True)
    (ROOT / "data").mkdir(exist_ok=True)
    records = []
    payload = (SOURCE / "assethash/v9/assethash.master.amf.gz").read_bytes()
    manifest = [("assethash/v9/assethash.master.amf.gz",
                 pyamf.get_decoder(pyamf.AMF3, zlib.decompress(payload)).readElement())]
    delta = SOURCE / "xml/gz/v855098/assethash.min.amf.gz"
    if delta.is_file():
        manifest.insert(0, (delta.relative_to(SOURCE).as_posix(),
                           pyamf.get_decoder(pyamf.AMF3, zlib.decompress(delta.read_bytes())).readElement()))
    copies = {
        "royal-sky.jpg": "dialogs/FV_Support/FV_RoyalWedding/royalWedding_skyBg.jpg",
        "blue-button.png": "dialogs/4d_elements/City_xPromo/xpromoCity_Button_Send.png",
        "blue-button-dim.png": "dialogs/4d_elements/City_xPromo/xpromoCity_Button_Send_dim.png",
        "blue-panel.png": "dialogs/4d_elements/City_xPromo/xpromoCity_Panel_Send.png",
        "underwater-button.png": "dialogs/underwater/Button.png",
        "animal-frame.png": "dialogs/midwest/AnimalFrame_big_noBG.png",
        "biodome-wood-frame.png": "dialogs/FV_Support/buildables/FV_Biodome2013_buildable_woodframe.png",
    }
    for name, logical in copies.items():
        path = resolve(logical)
        if path:
            data = path.read_bytes()
            (DEST / name).write_bytes(data)
            records.append({"path": "/static/assets/skin/"+name, "logical": logical,
                            "sourcePath": str(path), "sha256": hashlib.sha256(data).hexdigest(),
                            "method": "Exact file copy"})
    for logical, prefix in {
        "embeds/Flash/v855097-855094/FV_Preloader.swf": "original-preloader",
        "embeds/Flash/v855097-855094/FarmGame.swf": "game",
        "dialogs/FV_GenericPopUp.swf": "generic-popup",
        "dialogs/FV_GenericLrgPopUp.swf": "large-popup",
        "dialogs/FV_GenericMedPopUp.swf": "medium-popup",
        "dialogs/FV_GenericPopUp_GreenBlue_btns.swf": "greenblue-popup",
        "dialogs/FV_Tutorial_popUp.swf": "tutorial-popup",
        "preloader/FV_LoadBar.swf": "loadbar",
        "preloader/FV_Preloader_ZyngaBrand.swf": "preloader",
        "preloader/FV_Preload_Faster.swf": "preload-faster",
    }.items():
        extract(logical, prefix)
    aliases = {
        "sky.jpg": "royal-sky.jpg", "loading-frame.png": "original-preloader-32.png",
        "cream-cloud.png": "original-preloader-30.png", "dialog-panel.png": "large-popup-1.png",
        "header-wood.png": "loadbar-1.png", "cyan-meter.png": "game-659.png",
        "green-meter.png": "game-588.png", "crop-tile.png": "game-24.png",
        "cream-card.png": "game-519.png",
    }
    by_path = {record["path"]: record for record in records}
    for name, original in aliases.items():
        path = DEST / original
        if path.is_file():
            (DEST / name).write_bytes(path.read_bytes())
            record = dict(by_path["/static/assets/skin/" + original])
            record.update(path="/static/assets/skin/" + name, aliasOf="/static/assets/skin/" + original)
            records.append(record)
    for record in records:
        image = Image.open(ROOT / record["path"].lstrip("/"))
        record.update(width=image.width, height=image.height)
    for name, candidates in {"merkin.ttf": ("MERKIN__.ttf",),
                             "badaboom-bb.ttf": ("BADABB__.TTF", "badaboomprobb_reg.ttf")}.items():
        selected = next(((original, path) for original in candidates if (path := resolve("fonts/" + original))), None)
        if selected:
            original, path = selected
            data = path.read_bytes()
            (DEST / name).write_bytes(data)
            records.append({"path": "/static/assets/skin/" + name, "logical": "fonts/" + original,
                            "sourcePath": str(path), "sha256": hashlib.sha256(data).hexdigest(),
                            "method": "Exact original font file copy"})
    for record in records:
        original = Path(record["sourcePath"])
        record["sourceSha256"] = hashlib.sha256(original.read_bytes()).hexdigest()
        if original.is_relative_to(ASSETS):
            record["assetRelativePath"] = original.relative_to(ASSETS).as_posix()
            record.pop("sourcePath")
        else:
            record["sourcePath"] = original.relative_to(SOURCE).as_posix()
    (ROOT / "data/skin-assets.json").write_text(json.dumps(records, indent=2) + "\n")
    return {"files": len(records), "bytes": sum((ROOT / r["path"].lstrip("/")).stat().st_size for r in records)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--assets-root", type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.root, assets_root=args.assets_root), indent=2))


if __name__ == "__main__":
    main()
