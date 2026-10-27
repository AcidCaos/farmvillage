#!/usr/bin/env python3
"""Author six detached saves and a checked, original-art resident neighbourhood.

This is an offline authoring utility, never a live-save update path. Deployment
must stop the owned server and back up its old saves before installing the world.
"""

from __future__ import annotations

import argparse
from collections import deque
import copy
import datetime as dt
from functools import lru_cache
import hashlib
import html
import io
import json
import math
from pathlib import Path
import struct
import tarfile
import uuid
import xml.etree.ElementTree as ET
import zlib


ROOT = Path(__file__).resolve().parents[2]
UPDATE_ID = "bifrost-fresh-neighborhood-20261021-v2"
RESIDENT_LEVEL = 70
RESIDENT_SIZE = 90  # Original Home Farm expansion farm22: squares=90.
NAMESPACE = uuid.UUID("815d9a77-6227-52e2-8afd-b46a3fc09151")
RELEASE = "farmvillage-portable-preparation-1acf91b47487"
ACCEPTED_ARCHIVE_SHA = "7275f4ca53199443894d47dacc3d3c9a06911420c7400a722cbf9afe390f3c6d"
RESIDENTS = (
    {"key": "poppy", "name": "Poppy", "theme": "Sunflower garden and pink blossom orchard", "gender": "female"},
    {"key": "hank", "name": "Hank", "theme": "Golden working fields and the famous hay-bale enclosure", "gender": "male"},
    {"key": "mabel", "name": "Mabel", "theme": "A generous animal sanctuary with airy paddocks", "gender": "female"},
    {"key": "hazel", "name": "Hazel", "theme": "October harvest cottage and an amber orchard", "gender": "female"},
    {"key": "ben", "name": "Ben", "theme": "A prosperous classic homestead and formal orchard estate", "gender": "male"},
)
# Authored from the original avatar.xml; every slot/category/gender was checked.
# The clothing loader reconstructs appearance metadata from these item IDs.
AVATAR_KITS = {
    "poppy": {"body": "1", "face": "900", "hair": "15335", "eyebrows": "700", "eyes": "100", "ears": "800", "nose": "400", "mouth": "200", "pants": "8016", "shirt": "8001", "shoes": "6009"},
    "hank": {"body": "8", "face": "901", "hair": "304", "eyebrows": "707", "eyes": "106", "ears": "800", "nose": "411", "mouth": "201", "pants": "7011", "shirt": "7008", "shoes": "7019", "facialhair": "604", "hat": "6011"},
    "mabel": {"body": "4", "face": "906", "hair": "15364", "eyebrows": "702", "eyes": "102", "ears": "800", "nose": "402", "mouth": "206", "pants": "8011", "shirt": "7008", "shoes": "7019"},
    "hazel": {"body": "5", "face": "907", "hair": "15267", "eyebrows": "709", "eyes": "101", "ears": "800", "nose": "404", "mouth": "15173", "pants": "8009", "shirt": "6023", "shoes": "6006"},
    "ben": {"body": "6", "face": "900", "hair": "301", "eyebrows": "701", "eyes": "104", "ears": "800", "nose": "401", "mouth": "209", "pants": "7009", "shirt": "6003", "shoes": "6009"},
}
# Original item artwork serves as a resident's theme badge, never as a claim
# that a real human is online. All URLs stay on the game's own asset server.
PROFILE_ICONS = {
    "poppy": "/assets/achievements/48x48/878ea778b150d7af12c9820283b691a6.png",
    "hank": "/assets/achievements/48x48/4e90c66f3e7095a0aba501262456c96b.png",
    "mabel": "/assets/achievements/48x48/3b945f39bafa3f8a8de3dfd4fe9bdf3e.png",
    "hazel": "/assets/achievements/48x48/49e9aa5602a6a846d4027d0defd5010d.png",
    "ben": "/assets/achievements/48x48/45642f4ed15629a975c789836bb7c0c6.png",
}
ALLOWED_CLASSES = {"Plot", "Building", "StorageBuilding", "Decoration", "RotateableDecoration", "MaskedDecoration", "FlowerDecoration", "Animal", "Tree", "Tractor"}
WALKABLE_PATHS = {"poppy": "steppingstonepath", "hank": "cementpath", "mabel": "woodenpath", "hazel": "leavespath", "ben": "tiledpath"}
PALETTE = {"Plot": "#bda16a", "Tree": "#769a5c", "Animal": "#dfcdb1", "Building": "#b97967", "StorageBuilding": "#b97967", "Decoration": "#d8b9a5", "FlowerDecoration": "#efbf5c", "RotateableDecoration": "#dccfb5", "Tractor": "#6d8b72"}


def uid(key):
    return str(uuid.uuid5(NAMESPACE, key))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()


def load_inputs(source=ROOT):
    archive_path = source / "macOS/.build/PortablePreparation" / (RELEASE + "-final.tar.gz")
    archive_bytes = archive_path.read_bytes()
    if sha(archive_bytes) != ACCEPTED_ARCHIVE_SHA:
        raise ValueError("The accepted portable release archive has changed.")
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        initial_bytes = archive.extractfile(RELEASE + "/Runtime/villages/initial.json").read()
    if initial_bytes != (source / "villages/initial.json").read_bytes():
        raise ValueError("Source initial.json differs from the accepted runtime template.")
    cache = json.loads((source / "LocalData/cache/gz_v855038_items_opt.json").read_text())
    catalog = {item["name"]: item for item in cache["data"]["settings"]["items"]["item"]}
    return json.loads(initial_bytes), initial_bytes, catalog


@lru_cache(maxsize=4)
def resident_xp(source=ROOT):
    settings = ET.fromstring(zlib.decompress((source / "xml/gz/v855098/gameSettings.xml.gz").read_bytes()))
    return int(next(row.get("requiredXP") for row in settings.findall(".//levels/level") if row.get("num") == str(RESIDENT_LEVEL)))


def item_size(item, state):
    # Recovered FarmItem.sizeX/sizeY use Math.max(dataSource.getInt(...),1).
    width = max(1, int(float(item.get("sizeX", 1))))
    height = max(1, int(float(item.get("sizeY", 1))))
    if state in ("vertical", "built_rotatable"):
        width, height = height, width
    return width, height


def boxes_intersect(a, b):
    # Half-open rectangles let adjoining path stones and crop edges touch.
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def footprint(obj, catalog, *, visual=False):
    name = obj.get("itemName")
    item = catalog.get(name)
    if obj["className"] == "Plot":
        width = height = 4
    elif item is None:
        raise ValueError(f"Unknown catalogue item: {name}")
    else:
        width, height = item_size(item, obj["state"])
    x, y = obj["position"]["x"], obj["position"]["y"]
    if not visual:
        return (x, y, x + width, y + height)
    # Tree crowns and picked flower sprites are larger than their 1x1 logical
    # collision footprints. Reserve 4x4 plus a tile of air, centred on the item.
    if obj["className"] in ("Tree", "FlowerDecoration"):
        visual_width, visual_height = max(4, width), max(4, height)
        pad_x, pad_y = (visual_width - width) / 2 + .5, (visual_height - height) / 2 + .5
    elif name in ("stonepath", "haybale", "fencewhite", "fencewood", "fencepicket") or obj["className"] in ("Plot", "MaskedDecoration"):
        pad_x = pad_y = 0
    else:
        pad_x = pad_y = .75
    return (x - pad_x, y - pad_y, x + width + pad_x, y + height + pad_y)


class Layout:
    def __init__(self, key, catalog, size=50):
        self.key, self.catalog = key, catalog
        self.size = size
        self.objects = []
        self.zones = []
        self.skipped = 0

    def add(self, name, x, y, *, state=None, strict=True):
        item = self.catalog[name]
        kind = item.get("type")
        default_class = {"seed": "Plot", "building": "Building", "animal": "Animal", "tree": "Tree", "decoration": "Decoration", "vehicle": "Tractor"}[kind]
        class_name = item.get("className") or default_class
        if class_name not in ALLOWED_CLASSES:
            raise ValueError(f"Unsupported special class {class_name}: {name}")
        if state is None:
            # SimpleHarvestableResource maps save state "ripe" to image name
            # "mature". "mature" itself is not a valid Tree save state.
            state = ("grown" if class_name == "Plot" else "ripe" if class_name in ("Tree", "Animal") else "built" if kind == "building" else "horizontal" if class_name in ("RotateableDecoration", "MaskedDecoration") else "live" if class_name == "FlowerDecoration" else "static")
        obj = {"id": len(self.objects) + 1, "className": class_name, "itemName": name,
               "position": {"x": x, "y": y, "z": 0}, "state": state, "direction": 0,
               "deleted": False, "components": {}, "instanceDataStoreKey": None, "plantTime": 0}
        if kind == "building":
            obj.update(contents=[], buildTime=0, expansionLevel=0)
        if class_name == "Plot":
            obj.update(isJumbo=False, isBigPlot=False, isProduceItem=False)
        box = footprint(obj, self.catalog, visual=True)
        conflict = next((old for old in self.objects if boxes_intersect(box, footprint(old, self.catalog, visual=True))), None)
        valid = box[0] >= 0 and box[1] >= 0 and box[2] <= self.size and box[3] <= self.size
        center = self.size // 2
        if boxes_intersect(box, (center - 1, center - 1, center + 1, center + 1)):
            valid = False
        if conflict or not valid:
            if strict:
                raise ValueError(f"{self.key}: {name}@({x},{y}) conflicts with {conflict.get('itemName') if conflict else 'farm bounds'}")
            self.skipped += 1
            return None
        self.objects.append(obj)
        return obj

    def grid(self, names, xs, ys):
        for row, y in enumerate(ys):
            for col, x in enumerate(xs):
                self.add(names[(row + col) % len(names)], x, y, strict=False)

    def path(self, *, x=None, y=None, start=3, end=47):
        for value in range(start, end):
            self.add("stonepath", value if y is not None else x, y if y is not None else value, strict=False)

    def pen(self, x, y, width, height, fence="fencewood"):
        for xx in range(x, x + width - 4, 6):
            self.add(fence, xx, y, strict=False)
            self.add(fence, xx, y + height, strict=False)
        for yy in range(y + 1, y + height - 4, 6):
            self.add(fence, x, yy, state="vertical", strict=False)
            self.add(fence, x + width, yy, state="vertical", strict=False)


def authored_layouts(catalog):
    layouts = {}
    p = layouts["poppy"] = Layout("poppy", catalog)
    p.zones = [("Sunflower parterre", 4, 5, 17, 17), ("Rose garden", 31, 5, 15, 18), ("Water garden", 19, 27, 12, 12), ("Tea lawn", 4, 32, 16, 10), ("Blossom cottage", 32, 33, 14, 10)]
    for name, x, y in [("cottagepink", 35, 36), ("gazebopink", 9, 35), ("pond", 21, 29), ("honeybeesflowerpatch", 35, 27), ("picnictable", 13, 35), ("well", 42, 27), ("beeinabox", 40, 32)]:
        p.add(name, x, y)
    p.grid(["sunflowers"], [5, 10, 15], [6, 11, 16])
    p.grid(["rosepink", "sunflowers"], [32, 37, 42], [6, 11, 16])
    p.grid(["dogwoodtreepink", "cherryblossomtree"], [6, 15, 25, 45], [45])
    p.grid(["dogwoodtreepink"], [5, 45], [26, 34])
    p.grid(["rosepink_deco", "tulipred_deco", "sunflowers_deco"], [6, 13, 20, 33, 40], [3])
    p.grid(["rosepink_deco", "daffodils_deco"], [6, 13, 20], [29])
    p.path(x=25, start=3, end=20); p.path(x=25, start=31, end=47)
    p.path(y=25, start=3, end=20); p.path(y=25, start=31, end=47)
    p.grid(["fencewhite"], [4, 10, 35, 41], [48])

    h = layouts["hank"] = Layout("hank", catalog)
    h.zones = [("West working fields", 3, 3, 21, 30), ("East working fields", 30, 3, 17, 28), ("Hank's hay-bale throne", 21, 21, 9, 9), ("Working farmstead", 3, 37, 44, 10)]
    for name, x, y in [("barn", 35, 39), ("farmhouse", 5, 39), ("tractor", 37, 31), ("windmill", 46, 40), ("wagonhay", 17, 39)]: h.add(name, x, y)
    # The client's Home Farm default avatar spawn is floor(size/2)=(25,25).
    # Ring collision cells surround a clear 5x5 interior including that point.
    for x in range(22, 29):
        h.add("haybale", x, 22); h.add("haybale", x, 28)
    for y in range(23, 28):
        h.add("haybale", 22, y); h.add("haybale", 28, y)
    h.grid(["wheat", "wheat", "corn"], [4, 8, 12, 16, 20], [4, 8, 12, 16, 20, 24, 28])
    h.grid(["corn", "soybeans"], [31, 35, 39, 43], [4, 8, 12, 16, 20, 24])
    h.path(y=35); h.path(x=27, start=3, end=20)
    h.grid(["apple", "orange"], [24, 30], [44])
    h.grid(["sunflowers_deco"], [4, 11, 18, 38, 45], [47])
    h.add("scarecrow", 29, 31)

    m = layouts["mabel"] = Layout("mabel", catalog)
    m.zones = [("Dairy meadow", 3, 4, 20, 15), ("Lambs and little friends", 3, 21, 20, 11), ("Duck pond", 30, 4, 17, 15), ("Horse paddock", 29, 20, 18, 13), ("Sanctuary yard", 3, 36, 44, 11)]
    for name, x, y in [("barn", 35, 38), ("cottage", 6, 38), ("pond", 33, 7), ("toolshed", 20, 39), ("well", 28, 40)]: m.add(name, x, y)
    m.pen(4, 5, 18, 12); m.pen(4, 22, 18, 9); m.pen(30, 21, 17, 11)
    # Rabbit-supper beds provide the same verified crop-help path as the other
    # farms, without depending on historical coop feeding mechanics.
    m.grid(["carrot"], [28], [4, 9])
    m.grid(["cow", "cow", "goat"], [8, 12, 16], [9, 13])
    m.grid(["sheep", "rabbit", "pig"], [8, 12, 16], [25, 28])
    m.grid(["horse"], [34, 40], [25])
    m.grid(["duck"], [31, 44], [8, 13, 18])
    m.grid(["chicken"], [7, 11, 15], [34])
    m.grid(["apple", "cherry"], [6, 15, 32, 44], [46])
    m.path(x=26); m.path(y=35)
    m.grid(["sunflowers_deco"], [3, 10, 17, 33, 40, 47], [3])

    a = layouts["hazel"] = Layout("hazel", catalog)
    a.zones = [("Pumpkin quilt", 3, 3, 20, 22), ("Golden harvest", 30, 3, 17, 22), ("Harvest fair", 3, 30, 24, 11), ("October cottage", 32, 32, 14, 12), ("Amber orchard", 3, 42, 27, 7)]
    for name, x, y in [("cottage_halloween2011", 35, 35), ("smallpond", 24, 19), ("wagonhay", 15, 34), ("picnictable", 5, 34), ("windmill", 28, 37), ("well", 44, 29), ("autumnscarecrow", 20, 20)]: a.add(name, x, y)
    a.grid(["pumpkin", "carrot"], [4, 9, 14, 19], [4, 9, 14])
    a.grid(["wheat", "corn"], [32, 37, 42], [4, 9, 14, 19])
    a.grid(["maple", "cherry"], [5, 13, 21, 29, 45], [46])
    a.grid(["maple"], [4, 45], [27])
    a.grid(["carvedpumpkins", "haybale"], [4, 10, 21, 28], [31])
    a.grid(["haybale"], [6, 10, 20], [40])
    a.grid(["sunflowers_deco"], [5, 12, 19], [24])
    a.path(x=26, start=3, end=20); a.path(x=25, start=27, end=46)
    a.path(y=29, start=5, end=44)
    a.grid(["fencewood"], [4, 10, 16, 33, 39, 45], [48])

    b = layouts["ben"] = Layout("ben", catalog)
    b.zones = [("Six familiar plots", 6, 5, 18, 13), ("Little orchard", 32, 5, 15, 17), ("Quiet barnyard", 4, 21, 18, 8), ("Starter cottage", 6, 33, 17, 11), ("Red barn and pond", 31, 21, 16, 23)]
    for name, x, y in [("barn", 34, 35), ("cottage", 8, 36), ("smallpond", 35, 23), ("well", 24, 34), ("mailbox", 24, 45), ("picnictable", 13, 43)]: b.add(name, x, y)
    b.grid(["strawberry", "eggplant", "wheat"], [8, 13, 18], [7, 12])
    b.grid(["apple", "cherry"], [35, 43], [8, 16])
    b.grid(["cow", "chicken", "sheep"], [7, 12, 17], [24])
    b.grid(["sunflowers_deco", "rosepink_deco"], [5, 20, 31, 45], [45])
    b.path(x=27, start=6, end=46); b.path(y=30, start=5, end=46)
    b.grid(["fencepicket"], [4, 10, 16, 33, 39, 45], [3])
    return layouts


def grand_layouts(catalog):
    """Keep each authored core and add full estate wings, rather than scale it.

    The original 50-tile composition sits at the heart of a legal 90-tile farm.
    New front fields, side gardens/pastures, grand houses and orchard avenues
    fill the surrounding estate. Original blocking stone chains are discarded.
    """
    if int(catalog["farm22"]["squares"]) != RESIDENT_SIZE:
        raise ValueError("The selected estate size must match original Home Farm expansion farm22.")
    originals = authored_layouts(catalog)
    layouts = {}
    grand_houses = {"poppy": ("manorpink", "chateaumansion"), "hank": ("estate", "ranchhouse"),
                    "mabel": ("villa", "ranchhouse"), "hazel": ("manorblack", "vineyardchateau"),
                    "ben": ("manorblue", "colonialfarmhouse")}
    for key, original in originals.items():
        farm = layouts[key] = Layout(key, catalog, RESIDENT_SIZE)
        farm.zones = [(label, x + 20, y + 20, width, height) for label, x, y, width, height in original.zones]
        farm.zones += [("Estate forecourt", 3, 3, 84, 17), ("West estate wing", 3, 23, 16, 54),
                       ("East estate wing", 72, 23, 15, 54), ("Orchard avenue", 20, 74, 50, 13)]
        for obj in original.objects:
            if obj["itemName"] == "stonepath": continue
            # Keep the famous hay-bale corral, with a two-tile visitor gate.
            # The real client can use the same centre spawn for a visitor.
            if (key == "hank" and obj["itemName"] == "haybale"
                    and obj["position"]["x"] == 28 and obj["position"]["y"] in (25, 26)):
                continue
            copied = copy.deepcopy(obj)
            copied["id"] = len(farm.objects) + 1
            copied["position"]["x"] += 20
            copied["position"]["y"] += 20
            farm.objects.append(copied)
        house, second = grand_houses[key]
        farm.add(house, 5, 64 if key != "ben" else 65)
        farm.add(second, 74 if key != "poppy" else 73, 65 if key != "hazel" else 67)
        for name, x, y in [("stonefountain", 42, 75), ("topiaryfancy", 35, 77), ("topiaryfancy", 51, 77),
                           ("conetopiary", 4, 21), ("conetopiary", 85, 21)]:
            farm.add(name, x, y, strict=False)
        if key == "poppy":
            farm.grid(["sunflowers", "rosepink", "rosered"], range(4, 65, 5), [4, 9, 14])
            farm.add("swanpond", 74, 5)
            farm.add("birdfountain", 76, 43)
            farm.grid(["dogwoodtreepink", "cherryblossomtree"], [5, 13, 77, 85], range(28, 62, 8))
            farm.grid(["dogwoodtreepink", "cherryblossomtree"], range(5, 88, 7), [84])
            farm.grid(["rosepink_deco", "sunflowers_deco", "tulipred_deco"], range(23, 70, 7), [76])
            farm.grid(["rosepink_deco", "daffodils_deco"], [5, 13, 77, 85], [24, 62])
        elif key == "hank":
            farm.grid(["wheat", "wheat", "corn"], range(4, 85, 4), [4, 8, 12, 16])
            farm.grid(["soybeans", "corn"], [4, 8, 12, 16, 74, 78, 82], range(28, 62, 4))
            farm.grid(["apple", "orange"], range(23, 71, 6), [76, 84])
            farm.grid(["sunflowers_deco"], [5, 13, 77, 85], [78, 85])
            farm.add("chateaubarn", 5, 52, strict=False)
        elif key == "mabel":
            farm.add("swanpond", 74, 5)
            farm.grid(["cow", "sheep", "goat", "chicken", "pig"], range(5, 36, 5), [5, 10, 15])
            farm.grid(["carrot", "corn"], [42, 47, 52, 57, 62], [5, 10, 15])
            farm.grid(["horse", "cow", "sheep", "rabbit"], [5, 12, 76, 83], range(28, 62, 7))
            farm.grid(["apple", "cherry"], range(5, 88, 7), [84])
            farm.grid(["duck", "chicken", "rabbit"], range(24, 70, 5), [76])
            farm.pen(4, 3, 31, 15); farm.pen(73, 25, 14, 35)
        elif key == "hazel":
            farm.add("autumnpond", 75, 7)
            farm.grid(["pumpkin", "wheat", "carrot"], range(4, 65, 5), [4, 9, 14])
            farm.grid(["maple", "cherry"], [5, 13, 77, 85], range(28, 62, 8))
            farm.grid(["maple", "cherry"], range(5, 88, 7), [84])
            farm.grid(["carvedpumpkins", "autumnscarecrow", "haybale"], range(23, 70, 5), [76, 84])
            farm.grid(["sunflowers_deco"], [5, 13, 77, 85], [24, 61])
        else:
            farm.add("waterfall", 75, 7)
            farm.grid(["strawberry", "wheat", "eggplant", "soybeans"], range(5, 66, 5), [5, 10, 15])
            farm.grid(["apple", "cherry", "orange", "plum"], [5, 13, 77, 85], range(28, 62, 8))
            farm.grid(["apple", "cherry", "orange", "plum"], range(5, 88, 7), [84])
            farm.grid(["sunflowers_deco", "rosepink_deco"], range(23, 70, 7), [76])
            farm.grid(["cow", "chicken", "sheep"], [5, 11, 77, 83], [22])
        # Ground tiles are presentation-only MaskedDecoration parts. Their
        # original 2x2 HH mask excludes avatar collisions, unlike stonepath.
        path_name = WALKABLE_PATHS[key]
        for x in (20, 70):
            for y in range(20, 82, 2): farm.add(path_name, x, y, strict=False)
        for y in ((20,) if key == "hank" else (20, 72)):
            for x in range(4, 88, 2): farm.add(path_name, x, y, strict=False)
        for y in range(24, 70, 2): farm.add(path_name, 45, y, strict=False)
        for x in range(24, 70, 2): farm.add(path_name, x, 45, strict=False)
    return layouts


def walkability(layout, catalog):
    """Audit unit-grid avatar movement; HH ground tiles remain traversable.

    This is a conservative ground proof, not a substitute for Ruffle pathing.
    Every non-path object's whole logical rectangle is treated as blocked.
    Hank's hay-bale corral has a discreet gate so visitors can leave and help.
    """
    blocked = set()
    for obj in layout.objects:
        if obj["className"] == "MaskedDecoration": continue
        x, y, xx, yy = footprint(obj, catalog)
        blocked.update((ix, iy) for ix in range(math.floor(x), math.ceil(xx))
                       for iy in range(math.floor(y), math.ceil(yy)))
    center = layout.size // 2
    start = (center, center)
    if start in blocked: raise ValueError(f"{layout.key}: default avatar spawn is blocked")
    visited, todo = set(), deque([start])
    while todo:
        point = todo.popleft()
        if point in visited or point in blocked: continue
        x, y = point
        if not 0 <= x < layout.size or not 0 <= y < layout.size: continue
        visited.add(point)
        todo.extend(((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)))
    corners = [(2, 2), (layout.size - 3, 2), (2, layout.size - 3), (layout.size - 3, layout.size - 3)]
    reaches_corners = all(point in visited for point in corners)
    if not reaches_corners:
        raise ValueError(f"{layout.key}: the default avatar cannot reach all four estate wings")
    return {"defaultSpawn": list(start), "reachableGroundCells": len(visited), "allFourEstateCornersReachable": reaches_corners,
            "hayCorralWithVisitorGate": layout.key == "hank", "pathCollisionRule": "Original HH masks exclude avatar collisions."}


def validate_layout(objects, catalog, *, size=50, visual=True):
    ids = set()
    rectangles = []
    errors = []
    for obj in objects:
        ident = obj.get("id")
        if isinstance(ident, bool) or not isinstance(ident, int) or not 0 < ident < 63000 or ident in ids:
            errors.append(f"invalid or duplicate object ID: {ident}")
        ids.add(ident)
        if obj.get("className") not in ALLOWED_CLASSES:
            errors.append(f"unsupported class: {obj.get('className')}")
        pos = obj.get("position", {})
        if (any(isinstance(pos.get(axis), bool) or not isinstance(pos.get(axis), (int, float))
                or not math.isfinite(pos.get(axis)) for axis in ("x", "y", "z")) or pos.get("z") != 0):
            errors.append(f"invalid ground position for {ident}"); continue
        if obj.get("itemName") not in catalog and not (obj.get("className") == "Plot" and obj.get("itemName") is None):
            errors.append(f"missing catalogue item for {ident}"); continue
        box = footprint(obj, catalog, visual=visual)
        if box[0] < 0 or box[1] < 0 or box[2] > size or box[3] > size:
            errors.append(f"out of bounds: {ident}")
        for other_id, other in rectangles:
            if boxes_intersect(box, other): errors.append(f"overlap: {other_id} and {ident}")
        rectangles.append((ident, box))
    if errors:
        raise ValueError("; ".join(errors))
    return {"objects": len(objects), "pairChecks": len(objects) * (len(objects) - 1) // 2,
            "overlaps": 0, "outOfBounds": 0, "uniqueIds": True, "allGroundLevel": True,
            "visualReservations": visual, "farmDimensions": [size, size]}


def make_save(initial, key, name, now, *, layout=None, gender="female", catalog=None):
    save = copy.deepcopy(initial)
    ident = uid(key)
    user, world = save["userInfo"], save["world"]
    user["attr"].update(name=name, profilePic="")
    user["player"]["userId"] = ident
    save["flashHotParams"]["ZYNGA_USER_ID"] = ident
    size = layout.size if layout is not None else 50
    world.update(id=1, uid=uid(key + ":world"), sizeX=size, sizeY=size)
    user["worldSummaryData"]["farm"].update(firstLoaded=now, lastLoaded=now)
    user.update(is_new=layout is None, firstDay=layout is None, firstDayTimestamp=now if layout is None else now - 30 * 86400)
    if layout is not None:
        world["objectsArray"] = copy.deepcopy(layout.objects)
        user["attr"]["profilePic"] = PROFILE_ICONS[key]
        user["player"].update(xp=resident_xp(), gold=20000000, cash=100000)
        user["avatar"] = {"version": "fv_1", "gender": gender,
                          "items": {slot: {"itemId": item_id} for slot, item_id in AVATAR_KITS[key].items()}}
        save["avatarState"]["unlocked"] = sorted(set(AVATAR_KITS[key].values()))
        save["localResident"] = {"schemaVersion": 1, "key": key, "fictional": True, "updateId": UPDATE_ID}
    for obj in world["objectsArray"]:
        if obj.get("className") in ("Plot", "Animal", "Tree") and obj.get("itemName"):
            grow_days = float(catalog[obj["itemName"]].get("growTime", 1))
            obj["plantTime"] = int((now - grow_days * 82800) * 1000)
    return save


def verify_assets(catalog, objects, source=ROOT):
    # Decode the original asset manifest only during authoring. The delivered
    # world needs no Python package or external service beyond the existing game.
    import pyamf
    manifest = pyamf.get_decoder(pyamf.AMF3, zlib.decompress((source / "assethash/v9/assethash.master.amf.gz").read_bytes())).readElement()
    assets = []
    for name in sorted({obj["itemName"] for obj in objects if obj.get("itemName")}):
        images = catalog[name].get("image", [])
        if isinstance(images, dict): images = [images]
        present = 0
        present_states = set()
        for image in images:
            logical = image.get("url", "")
            if not logical.startswith("assets/"): continue
            group, relative = logical[7:].split("/", 1)
            digest = manifest.get(group, {}).get(relative)
            if not isinstance(digest, str): continue
            path = source / "LocalData/assets" / group / Path(relative).parent / (digest + Path(relative).suffix)
            if path.is_file() and image.get("name") != "icon":
                present += 1
                present_states.add(image.get("name"))
        required_states = set()
        for obj in objects:
            if obj.get("itemName") != name: continue
            if obj["className"] == "Tree":
                if obj["state"] not in ("ripe", "bare"):
                    raise ValueError(f"Tree {name} uses an invalid save state {obj['state']}")
                image_state = "mature" if obj["state"] == "ripe" else "bare"
            else:
                image_state = "animation" if obj["className"] == "Animal" else "built_0" if obj["className"] == "StorageBuilding" else obj["state"]
            required_states.add(image_state)
            if obj["className"] == "MaskedDecoration":
                if catalog[name].get("collision") != {"r": ["HH", "HH"]} or catalog[name].get("numParts") != "2":
                    raise ValueError(f"Path {name} has an unreviewed avatar collision mask or part count")
                required_states.add(image_state + "_mask_part_1")
        if not required_states <= present_states:
            raise ValueError(f"Original world artwork missing for {name}: {sorted(required_states - present_states)}")
        assets.append({"item": name, "originalImageStatesFound": present, "requiredStatesVerified": sorted(required_states)})
    return assets


def preview_svg(layout, resident, output, catalog, *, isometric=False):
    # Architectural previews are labelled as plans, not screenshots of gameplay.
    scale = 600 / layout.size
    def project(x, y):
        return (420 + (x - y) * (350 / layout.size), 130 + (x + y) * (185 / layout.size)) if isometric else (75 + x * scale, 150 + y * scale)
    def polygon(box):
        x, y, xx, yy = box
        return " ".join(f"{px:.1f},{py:.1f}" for px, py in [project(x, y), project(xx, y), project(xx, yy), project(x, yy)])
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="850" height="880" viewBox="0 0 850 880">', '<rect width="850" height="880" fill="#f7f2e7"/>', f'<text x="60" y="65" font-family="Georgia,serif" font-size="36" fill="#364c36">{html.escape(resident["name"])}\u2019s Estate</text>', f'<text x="60" y="98" font-family="sans-serif" font-size="15" fill="#766f5e">{html.escape(resident["theme"])}</text>', f'<text x="60" y="122" font-family="sans-serif" font-size="12" fill="#766f5e">ARCHITECTURAL PLAN · original in-game art · level 70 · {layout.size} × {layout.size} tiles</text>', f'<polygon points="{polygon((0, 0, layout.size, layout.size))}" fill="#a9bc84" stroke="#6b805b" stroke-width="2"/>']
    for label, x, y, width, height in layout.zones:
        parts.append(f'<polygon points="{polygon((x,y,x+width,y+height))}" fill="#edf0cf" opacity=".22"/>')
    for obj in sorted(layout.objects, key=lambda item: item["position"]["x"] + item["position"]["y"]):
        box = footprint(obj, catalog)
        color = PALETTE.get(obj["className"], "#ddd7bd")
        name = obj["itemName"]
        if "pink" in name or "cherryblossom" in name: color = "#e9a5bf"
        if name == "stonepath" or obj["className"] == "MaskedDecoration": color = "#e7dfc8"
        if name == "haybale": color = "#dac66e"
        if "pond" in name: color = "#7aa7ad"
        if obj["className"] == "Plot":
            color = {"pumpkin": "#db9b59", "wheat": "#e3c979", "sunflowers": "#ecd06d", "rosepink": "#d9a0b4", "strawberry": "#ba6c6f", "carrot": "#b7be80", "corn": "#bec77b"}.get(name, "#a4ae72")
        parts.append(f'<polygon points="{polygon(box)}" fill="{color}" stroke="#7c7c60" stroke-width=".6"><title>{html.escape(name)} · ID {obj["id"]}</title></polygon>')
        if obj["className"] == "Tree":
            x,y=obj["position"]["x"],obj["position"]["y"]
            xx,yy=project(x+.5,y+.5)
            parts.append(f'<circle cx="{xx:.1f}" cy="{yy-7:.1f}" r="16" fill="{color}" stroke="#71825f" stroke-width="1"/>')
    if layout.key == "hank":
        center = layout.size // 2
        x,y=project(center,center); parts.append(f'<circle cx="{x}" cy="{y}" r="4" fill="#bc625c"/><title>Hank: default avatar spawn ({center},{center}) inside hay-bale enclosure</title>')
    parts.append('<text x="60" y="800" font-family="sans-serif" font-size="14" fill="#364c36">Checked: zero intersecting ground footprints and zero intersecting visual reservations.</text>')
    parts.append('<text x="60" y="825" font-family="sans-serif" font-size="12" fill="#766f5e">Trees/flowers reserve 4 × 4 tiles plus air. Tall-sprite appearance still needs in-game review.</text></svg>')
    output.write_text("\n".join(parts))


def build(output, source=ROOT, now=None):
    output = output.expanduser().resolve()
    source = source.resolve()
    if output == source or source / "LocalData" == output or source / "LocalData" in output.parents:
        raise ValueError("Output must be a detached delivery folder, outside LocalData.")
    initial, initial_bytes, catalog = load_inputs(source)
    now = int(dt.datetime.now(dt.timezone.utc).timestamp()) if now is None else now
    layouts = grand_layouts(catalog)
    root = output / "world"
    if root.exists():
        raise ValueError("The delivery world already exists; choose a new output folder rather than overwrite saves.")
    saves = {"player": make_save(initial, "player", "Farmer", now, catalog=catalog)}
    checks = {}
    for resident in RESIDENTS:
        key = resident["key"]
        layout = layouts[key]
        checks[key] = validate_layout(layout.objects, catalog, size=layout.size)
        checks[key]["ground"] = validate_layout(layout.objects, catalog, size=layout.size, visual=False)
        center = layout.size // 2
        checks[key]["defaultSpawnClear"] = not any(boxes_intersect((center-1, center-1, center+1, center+1), footprint(obj, catalog, visual=True)) for obj in layout.objects)
        checks[key]["plannedCandidatesSkippedForClearance"] = layout.skipped
        checks[key]["walkability"] = walkability(layout, catalog)
        saves[key] = make_save(initial, key, resident["name"], now, layout=layout, gender=resident["gender"], catalog=catalog)
    artwork = verify_assets(catalog, [obj for save in saves.values() for obj in save["world"]["objectsArray"]], source)
    for key, url in PROFILE_ICONS.items():
        icon = source / "LocalData" / url.removeprefix("/")
        image = icon.read_bytes()
        if not image.startswith(b"\x89PNG\r\n\x1a\n") or struct.unpack(">II", image[16:24]) != (48, 48):
            raise ValueError(f"Resident theme icon is missing or is not an original 48x48 PNG: {key}")
    (root / "saves").mkdir(parents=True)
    (root / "neighborhood/templates").mkdir(parents=True)
    (root / "neighborhood/templates/initial.json").write_bytes(initial_bytes)
    save_files, hashes = {}, {}
    for key, save in saves.items():
        filename = uid(key) + ".save.json"
        content = encoded(save)
        (root / "saves" / filename).write_bytes(content)
        save_files[uid(key)] = filename
        hashes[filename] = sha(content)
    manifest = {"schemaVersion": 1, "updateId": UPDATE_ID, "createdUTC": dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat(),
                "playerUid": uid("player"), "residents": [{"uid": uid(row["key"]), "name": row["name"], "theme": row["theme"], "level": RESIDENT_LEVEL, "worldSize": RESIDENT_SIZE} for row in RESIDENTS],
                "saveFiles": save_files, "saveSha256": hashes, "initialTemplateSha256": sha(initial_bytes),
                "layoutValidation": checks, "policy": "Five fictional persistent local residents; no scheduled rotations or simulated messages.",
                "acceptance": "Offline geometry/catalog/artwork verified; actual client rendering and visiting acceptance pending."}
    (root / "neighborhood/manifest.json").write_bytes(encoded(manifest))
    previews = output / "previews"; previews.mkdir(exist_ok=True)
    for resident in RESIDENTS:
        layout = layouts[resident["key"]]
        preview_svg(layout, resident, previews / (resident["key"] + "-plan.svg"), catalog)
        preview_svg(layout, resident, previews / (resident["key"] + "-isometric.svg"), catalog, isometric=True)
    report = {"status": "PASS", "updateId": UPDATE_ID, "farms": checks, "originalAssets": artwork,
              "originalThemeIcons": PROFILE_ICONS,
              "coordinateEvidence": {"dimensions": "Original Home Farm expansion farm22 sets squares=90; commands.expand_farm uses that value for both dimensions. Recovered FarmItem getters clamp item dimensions to at least 1; object depth end is position + size.", "rotations": "RotateableDecoration vertical and Building built_rotatable swap sizeX/sizeY.", "avatar": "Home Farm default avatar spawn floor(gridWidth/2), floor(gridHeight/2); the 2x2 region [44,44..46,46] around (45,45) is reserved clear on every 90x90 resident estate. Hank's hay-bale corral retains a two-tile visitor gate; all estates pass corner-reachability checks.", "treeState": "SimpleHarvestableResource renders save state ripe using catalogue image mature; mature is an image name, not a Tree save state.", "level": "Original gameSettings.xml level 70 threshold is 433000 XP; level 71 begins at 443500. Residents hold 20000000 coins and 100000 Farm Cash; the player retains 0 XP, 200 coins and 5 cash.", "paths": "Only original MaskedDecoration two-part paths with 2x2 HH masks are used; HH means COLLISION_ALL_EXCEPT_AVATAR. Continuous blocking stonepath chains are absent.", "elevation": "All objects use z=0; no artificial stacked decorations."},
              "limits": "Mathematical ground and conservative visual clearances are verified. These SVGs are architectural plans; actual Ruffle art, all five visits, and help/restart acceptance still require client tests."}
    (output / "collision-validation.json").write_bytes(encoded(report))
    archive_path = output / "farmvillage-fresh-world.tar.gz"
    with tarfile.open(archive_path, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file(): archive.add(path, arcname=str(path.relative_to(output)), recursive=False)
    (output / (archive_path.name + ".sha256")).write_text(sha(archive_path.read_bytes()) + "  " + archive_path.name + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=ROOT)
    args = parser.parse_args()
    manifest = build(args.output, args.source)
    print(f"Created six detached saves for {manifest['updateId']}; all five resident layouts have zero overlaps.")
    print(f"Delivery: {args.output.resolve()}")


if __name__ == "__main__":
    main()
