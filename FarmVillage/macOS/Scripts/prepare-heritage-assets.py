#!/usr/bin/env python3
"""Reproduce the small native launcher pack from explicitly selected local assets.

Requires Pillow and FFDec 26.4.0 with Java 17. Explicit original/asset roots replace the old private LocalData dependency. The exporter downloads nothing and reads no player data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / "macOS/Resources/Heritage"
ART_NOTICE = "Original FarmVille artwork/audio, Zynga and its respective creators. Archive presence does not establish redistribution rights."
ERA = "Classic home-farm subject; exact first-use date has not been independently established."


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", type=Path, required=True)
    parser.add_argument("--assets-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tool-home", type=Path, required=True)
    parser.add_argument("--java", type=Path, required=True)
    parser.add_argument("--ffdec", type=Path, required=True)
    args = parser.parse_args()
    global ROOT, OUTPUT
    ROOT, OUTPUT = args.game_root.absolute(), args.output.absolute()
    asset_root = args.assets_root.absolute()
    if any(path == SOURCE_ROOT or SOURCE_ROOT in path.parents for path in (OUTPUT, args.tool_home.absolute())):
        raise ValueError("Generated native artwork and tool state must stay outside the source checkout")
    for path in (ROOT, OUTPUT, asset_root, args.java.absolute(), args.ffdec.absolute(), args.tool_home.absolute()):
        if '..' in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError("Linked input/output paths refused")
    if OUTPUT.exists() or ROOT in OUTPUT.parents or asset_root in OUTPUT.parents:
        raise ValueError("Choose new Heritage output separate from original inputs")
    def source_path(relative):
        if isinstance(relative, Path): return relative
        prefix = "LocalData/assets/"
        return asset_root / relative[len(prefix):] if relative.startswith(prefix) else ROOT / relative
    if OUTPUT.is_symlink():
        raise SystemExit("Heritage output must not be a symlink")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    args.tool_home.mkdir(parents=True, exist_ok=True)
    tool_tmp = args.tool_home / "tmp"
    tool_tmp.mkdir(exist_ok=True)
    records = []

    def publish(name, source, logical, *, image=None, operation="Unmodified file copy", era=ERA, notice=ART_NOTICE, **extra):
        source = source_path(source)
        target = OUTPUT / name
        if target.is_symlink():
            raise ValueError(f"Output must not be a symlink: {name}")
        if image is None:
            shutil.copyfile(source, target)
        else:
            image.save(target, format="PNG", optimize=True)
        item = dict(file=name, logical_name=logical, source=("assets/" + str(source.relative_to(asset_root))) if source.is_relative_to(asset_root) else ("original/" + str(source.relative_to(ROOT))) if source.is_relative_to(ROOT) else "public-archive-display-font",
                    source_sha256=digest(source), sha256=digest(target), bytes=target.stat().st_size,
                    operation=operation, era_confidence=era, notice=notice, **extra)
        if name.endswith(".png"):
            with Image.open(target) as im:
                item.update(format="PNG", pixels=list(im.size), color_mode=im.mode)
        records.append(item)

    simple = [
        ("wood-rail.png", "templates/img/game_bar/ecb8d4257f9af29b38f1a10c4ccb322c4ebb2e8c.png", "Original HTML game-bar wooden rail"),
        ("friend-frame.png", "LocalData/assets/hud/Friendbar/972b69e89a821faded67387b9514c006.png", "hud/Friendbar/FV_Main_FriendBar_Normal.png"),
        ("friend-frame-hover.png", "LocalData/assets/hud/Friendbar/64f6ef8d9785cccf0c5ae4e6a48e0487.png", "hud/Friendbar/FV_Main_FriendBar_Over.png"),
        ("strawberry.png", "LocalData/assets/crops/b7f664b2ec16d553616e5b294fd6ba27.png", "crops/crop_strawberry_icon_200.png"),
        ("wheat.png", "LocalData/assets/crops/8ddc0756b65de38170a111be0ef0fb7e.png", "crops/crop_wheat_icon_200.png"),
        ("eggplant.png", "LocalData/assets/crops/21280586ba1c6d6630657aeeba2a689c.png", "crops/crop_eggplant_icon_200.png"),
        ("red-barn-icon.png", "LocalData/assets/buildings/c0a6038b2c4d50670dfc7f6995090b1f.png", "buildings/building_barn_red_icon.png"),
        ("coins.png", "LocalData/assets/hud/619255c6685fa86755dfb70668671d2e.png", "hud/FV_coins_80x80.png"),
        ("xp-star.png", "LocalData/assets/hud/Friendbar/1654adc1cf991adaa8a5026fe6416741.png", "hud/Friendbar/FV_Main_FriendBar_XP_Star.png"),
        ("home-normal.png", "LocalData/assets/hud/Home_Button/0661239e9e9224de46cd11d9efb46d55.png", "hud/Home_Button (state identity not verified)"),
        ("click.mp3", "LocalData/assets/sounds/ui/b86e24e997073a5747a1bea9d42c2257.mp3", "sounds/ui/sfx_ui_click_1.mp3"),
        ("optional-barnyard.mp3", "LocalData/assets/sounds/457cee4afd3a547907c5eb9fc7061e3d.mp3", "sounds/Barnyard_02_44.mp3"),
    ]
    for name, source, logical in simple:
        publish(name, source, logical,
                era="Original archived audio; title verified by manifest, recording identity and first-use date unverified."
                if name == "optional-barnyard.mp3" else ERA)
    with Image.open(ROOT / "templates/img/logo.jpg") as logo:
        publish("farmville-logo.png", "templates/img/logo.jpg", "Original HTML FarmVille wordmark",
                image=logo.convert("RGBA"), operation="Lossless PNG encoding of decoded JPEG; original opaque white background retained")
    parchment_source = "LocalData/assets/dialogs/4d_elements/England/20bbf13feca9152136e18ba9a9f686b1.jpg"
    with Image.open(source_path(parchment_source)) as parchment:
        publish("parchment.png", parchment_source, "dialogs/4d_elements/England/parchmentTexture.jpg",
                image=parchment.convert("RGBA"), operation="Lossless PNG encoding of decoded original JPEG; no retouching",
                era="Original England dialog texture; exact first-use date unverified. Optional material, not proof of a 2009 UI.")
    button_source = "templates/img/game_bar/8bba081e4b32e771144af4a7404209007dff7756.png"
    with Image.open(ROOT / button_source) as strip:
        for name, y in [("play-normal.png", 0), ("play-hover.png", 54), ("play-pressed.png", 27)]:
            publish(name, button_source, "Original HTML game-bar Play tab", image=strip.crop((0, y, 36, y + 27)),
                    operation=f"Exact source-pixel crop [0,{y},36,{y + 27}]; semantic row names inferred; brown row is the selected Play state")
    publish("heading.ttf", "LocalData/assets/fonts/0eb3ba3e8af999051771bccbbe4d4a6b.ttf", "fonts/MERKIN__.ttf / Merkin",
            notice="© Apostrophic Labs. All rights reserved. apostrophe@home.com. No additional redistribution license is asserted.",
            postscript_name="Merkin", private_registration_only=True,
            companion_verification="SHA-256 matches GodBarn/static/assets/skin/merkin.ttf exactly: dfcf08440bbdb6631618c576fea5cff3e3d21fe3fff5e51b7c3edffa6eaf93d8")

    def export(directory: Path, source: str, options: list[str], kinds: str) -> None:
        command = [str(args.java), "-Djava.awt.headless=true", "-Duser.home=" + str(args.tool_home),
                   "-Djava.io.tmpdir=" + str(tool_tmp), "-jar", str(args.ffdec),
                   *options, "-export", kinds, str(directory), str(source_path(source))]
        environment = {k: v for k, v in os.environ.items() if k not in {"JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS"}}
        environment.update(HOME=str(args.tool_home), TMPDIR=str(tool_tmp))
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=environment)
        print(f"Native artwork export Java PID: {process.pid}", flush=True)
        try: output, _ = process.communicate(timeout=120)
        except BaseException:
            process.kill(); process.communicate(); raise
        if process.returncode or "FAIL:" in output: raise RuntimeError(output)

    with tempfile.TemporaryDirectory(prefix=".heritage-export-", dir=OUTPUT.parent) as scratch:
        scratch = Path(scratch)
        barn_source = "LocalData/assets/buildings/7a33d16789ef24303034271d87c81620.swf"
        export(scratch / "barn", barn_source, ["-format", "image:png", "-selectid", "1"], "image")
        with Image.open(scratch / "barn/1_barnred_vertical.png") as im:
            publish("red-barn.png", barn_source, "buildings/barnred.swf :: barnred_vertical (character 1)",
                    image=im.copy(), operation="FFDec 26.4.0 image:png export, character 1; original embedded raster, no enlargement",
                    intended_maximum_retina_points=[160, 148.5])
        for crop, source_hash in [
            ("strawberry", "4e1c8d0308fe46a8db7f6fc7ea75bcf8"),
            ("wheat", "5fa88f3d7842a8b125c4681ca767f3d4"),
            ("eggplant", "866c834d3838ca7db6d9a389cf114405"),
        ]:
            source = f"LocalData/assets/crops/{source_hash}.swf"
            out = scratch / f"crop-{crop}"
            export(out, source, ["-format", "image:png", "-selectid", "4"], "image")
            with Image.open(out / f"4_{crop}_grown.png") as im:
                publish(f"{crop}-grown.png", source, f"crops/crop_{crop}.swf :: {crop}_grown (character 4)",
                        image=im.copy(), operation="FFDec 26.4.0 image:png export, character 4; original grown crop raster and transparent canvas, no catalog frame or enlargement",
                        intended_maximum_retina_points=[100, 100])
        for animal, source_hash, frames in [
            ("cow", "35c1893509ca45e6b7bd354a3886100d", [1, 18, 35, 52]),
            ("chicken", "0fbbc9fb1badda550442c0f0f89d1a79", [1, 16, 31, 46]),
        ]:
            source = f"LocalData/assets/animals/{source_hash}.swf"
            out = scratch / animal
            export(out, source, ["-ignorebackground", "-zoom", "2", "-selectid", "32"], "sprite")
            folder = out / f"DefineSprite_32_{animal}_frt_idle"
            canvas_size = None
            for index, frame in enumerate(frames, 1):
                with Image.open(folder / f"{frame}.png") as im:
                    if canvas_size is None:
                        canvas_size = im.size
                    if im.size != canvas_size:
                        raise ValueError(f"{animal} idle frames have inconsistent canvas sizes")
                    name = f"{animal}-idle-{index:02d}.png"
                    publish(name, source, f"animals/{animal}.swf :: {animal}_frt_idle (character 32), frame {frame}",
                            image=im.copy(), operation=f"FFDec 26.4.0 sprite PNG, character 32, zoom 2, transparent background, original frame {frame}; shared full sprite canvas preserved",
                            vector_export_scale=2, sampling="Four selected original idle poses; launcher slideshow is not original animation timing")
                    if index == 1:
                        publish(f"{animal}.png", source, f"animals/{animal}.swf :: {animal}_frt_idle, frame {frame}",
                                image=im.copy(), operation="Identical static alias of idle frame 01", vector_export_scale=2)
        sunflower_source = "LocalData/assets/flowers/029abebf2dfee1e6c4e92d143fa25551.swf"
        export(scratch / "sunflowers", sunflower_source,
               ["-format", "image:png", "-selectid", "3"], "image")
        with Image.open(scratch / "sunflowers/3_sunflowers_grown.png") as im:
            publish("sunflowers-grown.png", sunflower_source,
                    "flowers/flower_sunflower.swf :: sunflowers_grown (character 3)",
                    image=im.copy(), operation="FFDec 26.4.0 image:png export, character 3; original grown flower raster and transparent canvas, no enlargement",
                    intended_maximum_retina_points=[100, 100])
        cherry_source = "LocalData/assets/decorations/84258ff3084810fa82e6a2165af7d4a5.swf"
        export(scratch / "cherry", cherry_source,
               ["-ignorebackground", "-zoom", "2", "-select", "1"], "frame")
        with Image.open(scratch / "cherry/1.png") as im:
            publish("cherry-blossom.png", cherry_source,
                    "decorations/deco_cherryblossom.swf :: original main-timeline frame 1",
                    image=im.copy(), operation="FFDec 26.4.0 transparent frame PNG, zoom 2, original vector geometry and full bounds retained",
                    vector_export_scale=2, intended_maximum_retina_points=[225, 239.5])
        grass_source = "LocalData/assets/Environment/df0a488eac94bee5d6eca26fd6114603.swf"
        export(scratch / "environment", grass_source,
               ["-format", "shape:png", "-zoom", "2", "-selectid", "2,11,36,43"], "shape")
        for name, character in [("hills.png", 2), ("river.png", 11), ("tree.png", 36), ("grass.png", 43)]:
            with Image.open(scratch / "environment" / f"{character}.png") as im:
                publish(name, grass_source, f"Environment/grass_themeBackground_12.swf :: shape {character}",
                        image=im.copy(), operation=f"FFDec 26.4.0 shape:png, character {character}, zoom 2; original geometry and transparent bounds retained",
                        vector_export_scale=2)

    manifest = {
        "schema": 1,
        "purpose": "Curated original FarmVille assets for the local native FarmVillage launcher",
        "source_manifest": "assethash/v9/assethash.master.amf.gz",
        "source_manifest_sha256": digest(ROOT / "assethash/v9/assethash.master.amf.gz"),
        "archive_context": "Archive captured in December 2020; it mixes classic and later-era assets. No blanket 2009–2011 date claim is made.",
        "export_tool": "JPEXS FFDec 26.4.0, Java 17; Pillow PNG encoding and exact rectangular sprite cropping",
        "source_preservation": "All original source files remain unchanged. No AI redraws or invented scene objects.",
        "audio_policy": "Disabled by default; user-controlled launcher-only playback, stopped before game handoff.",
        "font_policy": "Register original Merkin for this process. The display font uses the existing native system-rounded fallback. No private font is read. Book Antiqua is excluded; body text uses a system font.",
        "distribution_notice": "This local preservation pack does not grant rights to relicense or publicly redistribute Zynga artwork, audio, marks, or third-party fonts. Review source-specific terms before distribution.",
        "assets": records,
    }
    (OUTPUT / "NOTICES.md").write_text("# Native resource notices\n\n" + ART_NOTICE + "\n\nMerkin: © Apostrophic Labs. The display font uses a system fallback. No private font/player data is read.\n", encoding="utf-8")
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Prepared {len(records)} assets, {sum(r['bytes'] for r in records):,} bytes, in {OUTPUT}")


if __name__ == "__main__":
    main()
