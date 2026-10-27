"""Exact W05 admissions over existing storage and Orchard engines.

Each name/code/class is pinned. Hidden Palace, Craftshop, habitats, cellars and
artifacts retain independent recovery fences. The Fountain is an owned visual
aura reward, never a free Market offer or a repeat-harvest reward source.
"""
from pathlib import Path
import copy
import construction
import storage

WORLD = "rainforest"
BUILDINGS = {
    "xrforchard_finished": ("ruh", "OrchardFeatureBuilding", "orchard"),
    "superorchard_featurebuilding": ("c0B", "OrchardFeatureBuilding", "orchard"),
    "xrf_gnomegarden_finished": ("ruc", "FeatureBuilding", "gnomegarden"),
    "xrf_fountainofyouth": ("rvi", "FeatureBuilding", "visual"),
}
GNOMES = {
    "gnome_xrf_ancienthelm": "r1c", "gnome_xrf_ballgame": "rak",
    "gnome_xrf_butterflymasktte": "rwg", "gnome_xrf_eaglehelmets": "qs9",
    "gnome_xrf_featherprincesstte": "rwo", "gnome_xrf_gildedstoic": "qr5",
    "gnome_xrf_headdresstte": "qvg",
}


def policy_sources():
    return (Path(__file__),)


def rule(item, world_type):
    """Return only a checked original identity's bounded action contract."""
    if world_type != WORLD or not isinstance(item, dict):
        return None
    name = item.get("name")
    if name in GNOMES:
        if (item.get("code") != GNOMES[name] or item.get("className") != "Gnome"
                or item.get("type") != "decoration" or item.get("features")):
            raise ValueError("The rainforest Gnome identity requires review.")
        return {"actions": ("place", "move", "store", "getStorageInfo", "sell", "clear")}
    if name not in BUILDINGS:
        return None
    code, cls, family = BUILDINGS[name]
    if (item.get("code") != code or item.get("className") != cls
            or item.get("type") != "building"):
        raise ValueError("The rainforest feature identity requires review.")
    if family == "visual":
        if (item.get("buyable") != "false" or item.get("cost") != "0"
                or item.get("limit") != "1" or item.get("growTime")
                or item.get("aoe", {}).get("bonuses", {}).get("bonus") != {
                    "type": "visualChange", "value": name}
                or item.get("features", {}).get("feature", {}).get("className") != "ContextMenuFManager"):
            raise ValueError("The Fountain of Youth visual contract requires review.")
        return {"ownedOnly": True, "actions": ("place", "move", "store", "getStorageInfo")}
    if family == "orchard":
        if not storage.orchard_container_class(item) or not construction.manages(item):
            raise ValueError("The Jungle Orchard engine contract requires review.")
    elif storage.feature_container_class(item) != family or not construction.manages(item):
        raise ValueError("The rainforest Gnome container contract requires review.")
    replacement = name == "superorchard_featurebuilding"
    return {"worldless": name == "xrforchard_finished",
            "container": True,
            "replacementOnly": replacement,
            "ownedOnly": replacement,
            "actions": (() if replacement else ("place",)) + ("move", "store", "getStorageInfo",
                        "CompleteNow", "ExpandWithCurrency") + (("harvest",) if family == "orchard" else ())
                        + (("setMultipleFeaturedItems",) if family == "gnomegarden" else ())}


def garden_featured_items(save, snapshot, params):
    """Authorize only the owned Garden's original six-slot display selection.

    FeaturedRenderFManager saves this entire map after a normal Gnome deposit.
    Its code:metadata key must describe actual positive-container contents;
    neither the incoming object snapshot nor Gift Box/ordinary stock is authority.
    This read-only preflight does not normalize or synthesize imported ledgers.
    """
    from items import get_item_by_code
    from world_travel import guard_active_world
    if guard_active_world(save) != WORLD:
        raise ValueError("Gnome display saves require the current Rainforest farm.")
    owned = storage._feature_owner(save, snapshot.get("id"), snapshot)
    if owned is None:
        raise ValueError("Gnome display saves require one owned Jungle Gnome Garden.")
    owner, catalog, family = owned
    if (catalog.get("name") != "xrf_gnomegarden_finished" or family != "gnomegarden"
            or not rule(catalog, WORLD)):
        raise ValueError("Gnome display saves require the admitted Jungle Gnome Garden.")
    renderers = [row for row in catalog.get("features", {}).get("feature", [])
                 if isinstance(row, dict) and row.get("name") == "renderer"]
    if (len(renderers) != 1 or any(renderers[0].get(key) != value for key, value in {
            "className": "FeaturedRenderFManager", "maxItems": "6",
            "insertionMode": "most_recent", "propPointPrefix": "gnome"}.items())):
        raise ValueError("The Jungle Gnome Garden display contract requires review.")
    options = storage.world_action_options(params)
    if set(options) != {"featuredItems"} or not isinstance(options["featuredItems"], dict):
        raise ValueError("A Garden display save requires its featured-item map.")
    selection = options["featuredItems"]
    if len(selection) > 6:
        raise ValueError("The Jungle Gnome Garden has six display slots.")

    contents = owner.get("contents", [])
    if not isinstance(contents, list):
        raise ValueError("The saved Garden contents must be an array.")
    counts = {}
    for row in contents:
        if (not isinstance(row, dict) or not isinstance(row.get("itemCode"), str)
                or row["itemCode"] in counts):
            raise ValueError("The saved Garden contents are ambiguous.")
        counts[row["itemCode"]] = storage._capacity_integer(row.get("numItem"))
    data = save["userInfo"]["player"].get("storageData", {})
    if not isinstance(data, dict):
        raise ValueError("The saved Garden inventory is invalid.")
    ledger = data.get(str(owner["id"]))
    extras = {code: [] for code in counts}
    if ledger is not None:
        if not isinstance(ledger, dict):
            raise ValueError("The saved Garden ledger is invalid.")
        actual = {}
        for code, entry in ledger.items():
            construction._entry(entry)
            actual[code] = storage._capacity_integer(entry[0])
            if len(entry[2]) > actual[code]:
                raise ValueError("The saved Garden unit metadata exceeds its quantity.")
            extras[code] = copy.deepcopy(entry[2])
        if actual != counts:
            raise ValueError("The saved Garden ledger disagrees with its contents.")

    # FeatureBuilding.loadObject reads this trusted map; buildMetaDataHash
    # concatenates code + ':' + suffix. Opaque inventory extras never authorize
    # a client-invented suffix. Existing imported mappings must match real units.
    metadata = owner.get("storageMetadata")
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise ValueError("The saved Garden display metadata is invalid.")
    available = {}
    for code, quantity in counts.items():
        remaining = copy.deepcopy(extras.get(code, []))
        mapped = 0
        for key, values in metadata.items():
            if not isinstance(key, str) or not key.startswith(code + ":"):
                continue
            if (not isinstance(values, list) or not values or len(key) > 128
                    or key == code + ":"):
                raise ValueError("The saved Garden metadata mapping is invalid.")
            if ledger is not None:
                for value in values:
                    if value not in remaining:
                        raise ValueError("The Garden display metadata is not owned by its contents.")
                    remaining.remove(value)
            mapped += len(values)
            available[(code, key)] = len(values)
        if mapped > quantity:
            raise ValueError("The Garden display metadata exceeds its owned contents.")
        available[(code, code + ":")] = quantity - mapped

    result, used = {}, {}
    for raw_slot, entry in selection.items():
        if type(raw_slot) is int:
            slot = raw_slot
        elif (isinstance(raw_slot, str) and raw_slot.isascii() and raw_slot.isdecimal()
                and str(int(raw_slot)) == raw_slot):
            slot = int(raw_slot)
        else:
            raise ValueError("A Garden display slot must be a canonical whole number.")
        if not 0 <= slot < 6 or str(slot) in result:
            raise ValueError("A Garden display slot is outside its original six-slot range.")
        if not isinstance(entry, dict) or set(entry) != {"itemCode", "metaHash"}:
            raise ValueError("A Garden display slot requires its item code and metadata hash.")
        code, meta = entry["itemCode"], entry["metaHash"]
        item = get_item_by_code(code) if isinstance(code, str) else None
        if (not item or not storage._feature_accepts(family, item)
                or not isinstance(meta, str) or len(meta) > 128
                or not (meta == code or meta.startswith(code + ":"))):
            raise ValueError("The Garden display item or metadata hash is invalid.")
        # findFeaturedItem also recognizes the historical code-only spelling.
        # Both anonymous spellings consume the same actual unit allowance.
        key = (code, code + ":" if meta == code else meta)
        used[key] = used.get(key, 0) + 1
        if used[key] > available.get(key, 0):
            raise ValueError("A Garden display item must be an actual contained unit.")
        result[str(slot)] = {"itemCode": code, "metaHash": meta}
    return owner, result
