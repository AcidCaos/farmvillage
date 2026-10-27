"""Home Farm heritage pricing: a derived overlay on the recovered item catalog.

Ordinary items from catalog-only worlds, exclusive items that never had a price,
and crops (seeds) from catalog-only worlds become buyable on the Home Farm. Every
derived record comes from one pure plan, so the served market (client_catalog)
and the server purchase path (items) charge the same amount.

Scope:
- Worlds in RESERVED_WORLDS have their own rule modules or themed admission and
  price rules (creative_worlds, cove_rules, hallow_rules, hawaii_rules,
  england_progression, themed_worlds.SPECS). Their items are left exactly as
  recovered, and so is any item priced in a world currency.

Rule, applied in order:
1. Eligibility. Only ORDINARY_CLASSES (type, className) pairs qualify. A record
   must carry no requirement other than World entries, and none of
   BLOCKING_FIELDS. Locked items name only non-Home Worlds, outside
   RESERVED_WORLDS. Multiple Worlds need compare "any". Exclusive items are
   priceless with no World requirement.
2. Crops. A seed (type "seed") is admitted only when its whole Home loop works
   with the existing server code: buy at its coin price, plant on a plowed Home
   plot, grow for growTime, then harvest for coinYield and mastery. Each
   CROP_BLOCKING field, each harvest or produce reward the server never pays,
   each non-land terrain, and each closed experiment gate excludes the crop with
   a named reason (see _crop_reason). A locked crop that is excluded is refused
   on Home with that reason (crop_refusal).
3. Currency. An item keeps its own recovered price in its own market: Farm Cash
   in cash, or coins in cost. A locked item with only a Farm Cash price gets
   market "cash". A locked crop with no coin price takes a coin price. Anything
   else unpriced is priced in Farm Cash.
4. Derived price. A crop without its own coin price takes the nearest priced
   crop sibling in record order with the same (subtype, growth band). With no
   sibling, the lower median coin price of Home-visible crops with the same
   subtype is used, then of all Home-visible crops. Any other locked item without
   its own price takes the nearest priced sibling in record order with the same
   (type, className, subtype, sizeX*sizeY), then the lower median Farm Cash price
   of Home-visible items in the same tier: (type, className, footprint), then
   (type, className), then type. Equal distance prefers the earlier record.
5. Rehoming. Each World requirement of a locked item is renamed to "farm" with
   strict "true", so the Meadows non-strict alias cannot admit it. Its
   experimentGate and its limited date window are removed, archived is set to
   "no", and buyable is set to "true". A crop keeps its experimentGate, because
   the gate was checked open against the served client configuration.

Set ENABLED to False to restore the recovered catalog exactly.
"""
import bisect
import hashlib
from pathlib import Path

ENABLED = True
HOME_WORLD = "farm"
FARM_CASH = "cash"
COINS = "coins"
CROP_TYPE = "seed"

# Worlds with their own rule modules or themed admission and price rules. Their
# items are never overlaid. Keep in step with themed_worlds.SPECS; a test checks it.
RESERVED_WORLDS = frozenset({
    "farm", "england", "meadows", "fisherman", "hallow", "hawaii",
    "rainforest", "mediterranean", "storybook", "candy", "oasis", "oz",
    "toyland", "sleepyhollow", "australia", "fforest", "htown", "atlantis", "glen", "hlights",
})

ORDINARY_CLASSES = frozenset({
    ("tree", None),
    ("animal", None),
    ("animal", "CashGrowableBaby"),
    ("animal", "ItemGrowableBaby"),
    ("decoration", None),
    ("decoration", "RotateableDecoration"),
    ("decoration", "Gnome"),
    ("building", None),
    (CROP_TYPE, None),
})
# Any non-empty value keeps an item out: each names a prerequisite, quest,
# licence, mastery, experiment, geo or neighbour gate that the Home server never
# enforces for purchase.
BLOCKING_FIELDS = ("purchasePrereqs", "prereqs", "requiredQuest", "requiredMastery", "license",
                   "marketPrereqs", "experiment", "geoip", "promoMode", "minNeighbors")
DATE_FIELDS = ("limitedStart", "limitedEnd")

# Land terrain codes of the Home farm. creative_worlds._land_terrain_names() reads
# the same settings; a test keeps the two equal.
LAND_TERRAINS = frozenset({"all", "amphibious", "land", "plowable"})
# growTime in days at which a crop moves to the next price band.
GROW_BANDS = (0.25, 0.5, 0.75, 1.0, 2.0)
# A crop's own gates, in the order they are reported. Each is a prerequisite the
# Home server does not check when it sells or plants a crop.
CROP_BLOCKING = (
    ("license", "crop: licence"),
    ("purchasePrereqs", "crop: purchase prerequisite"),
    ("prereqs", "crop: purchase prerequisite"),
    ("requiredQuest", "crop: purchase prerequisite"),
    ("requiredMastery", "crop: purchase prerequisite"),
    ("marketPrereqs", "crop: market prerequisite"),
    ("experiment", "crop: experiment prerequisite"),
    ("geoip", "crop: geo gate"),
    ("promoMode", "crop: promo"),
    ("minNeighbors", "crop: neighbour gate"),
)

_overlaid = frozenset()
_refused = {}


def _nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _nodes(child)


def _world_names(item):
    return [node.get("name") for node in _nodes(item.get("requirements"))
            if node.get("className") == "World"]


def _compare(item):
    for node in _nodes(item.get("requirements")):
        if "compare" in node:
            return node["compare"]
    return None


def _foreign_requirement(item):
    return any(node.get("className") not in (None, "World")
               for node in _nodes(item.get("requirements")) if "className" in node)


def _scalar(value):
    return value[0] if isinstance(value, list) and value else value


def _amount(item, field):
    """Return the positive whole price, None when absent or zero, or raise on junk."""
    value = _scalar(item.get(field))
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("malformed price")
    try:
        number = int(float(value))
    except (TypeError, ValueError, OverflowError):
        raise ValueError("malformed price") from None
    if number <= 0:
        return None
    return number


def _lenient_amount(item, field):
    try:
        return _amount(item, field)
    except ValueError:
        return None


def _prices(item):
    """Return (cash, cost, malformed) so each currency is judged on its own field."""
    values, bad = {}, set()
    for field in ("cash", "cost"):
        try:
            values[field] = _amount(item, field)
        except ValueError:
            values[field] = None
            bad.add(field)
    return values["cash"], values["cost"], bad


def _footprint(item):
    try:
        return int(float(item["sizeX"])) * int(float(item["sizeY"]))
    except (KeyError, TypeError, ValueError):
        return None


def _set(value):
    return value not in (None, "", [], {})


def _flag(item, field):
    return item.get(field) in ("true", True)


def _grow_band(item):
    """The growth band of a crop, or None when its growTime is not a positive number."""
    try:
        days = float(item["growTime"])
    except (KeyError, TypeError, ValueError):
        return None
    if days != days or days in (float("inf"), 0) or days < 0:
        return None
    return bisect.bisect_right(GROW_BANDS, days)


def _whole(value, *, blank_ok):
    """True when the server can read a catalog value with int(), as its reward code does."""
    if value is None or (value == "" and blank_ok):
        return True
    try:
        int(value)
    except (TypeError, ValueError):
        return False
    return True


def _level_conflict(item):
    """True when purchase_required_level would refuse this crop: junk or conflicting levels."""
    value = item.get("requiredLevel")
    if value in (None, ""):
        return False
    entries = value if isinstance(value, list) else [value]
    if not entries:
        return True
    levels = set()
    for entry in entries:
        if isinstance(entry, bool):
            return True
        if isinstance(entry, int) and entry >= 0:
            levels.add(entry)
        elif isinstance(entry, str) and entry.isascii() and entry.isdecimal():
            levels.add(int(entry))
        else:
            return True
    return len(levels) != 1


def _terrains(item):
    return {node["name"] for node in _nodes(item.get("terrainSet"))
            if isinstance(node.get("name"), str)}


def _variants(item):
    value = item.get("experimentVariant")
    if not _set(value):
        return []
    try:
        return [int(part) for part in str(value).split(",") if part.strip()]
    except ValueError:
        return [-1]


def _gate_open(item, served):
    """The client's checkExperimentGate: the served variant is positive and listed, if any are."""
    gate = item.get("experimentGate")
    if not isinstance(gate, str) or served.get(gate, 0) <= 0:
        return False
    variants = _variants(item)
    return not variants or served[gate] in variants


def _reward_values_read(item):
    """Every reward value the server reads with int(); a value it cannot read fails the harvest."""
    if not all(_whole(item.get(field), blank_ok=False) for field in ("coinYield", "plantXp", "largeCropXp")):
        return False
    if not _whole(item.get("masteryYield"), blank_ok=True):
        return False
    levels = item.get("masteryLevel")
    for level in (levels if isinstance(levels, list) else ([] if levels is None else [levels])):
        if not all(_whole(level.get(field), blank_ok=True) for field in ("coins", "count", "xp")):
            return False
    return True


def _crop_reason(item, served):
    """Why a crop cannot be sold and planted on the Home Farm, or None when its loop works.

    Ordered so each crop gets one reason: its own gates first, then rewards and
    terrain, then its experiment and market entry.
    """
    if _grow_band(item) is None:
        return "crop: grow time invalid"
    for field, reason in CROP_BLOCKING:
        if _set(item.get(field)):
            return reason
    if any(_set(item.get(field)) for field in ("unlock", "unlockCost", "donation", "friendReward")):
        return "crop: unlock or donation"
    if _set(item.get("harvestYield")):
        return "crop: harvest yield in world currency or score"
    if _set(item.get("harvestItem")):
        return "crop: harvest item drop"
    if _flag(item, "producesItem"):
        return "crop: produce item"
    if _flag(item, "organic") or _set(item.get("organicCert")):
        return "crop: organic certification"
    if _flag(item, "isHybrid"):
        return "crop: hybrid breeding"
    if _set(item.get("weatherData")):
        return "crop: weather modifier"
    if _flag(item, "present"):
        return "crop: present gift"
    if _set(item.get("seedpackage")):
        return "crop: seed package"
    if _set(item.get("terrainSet")) and not _terrains(item) & LAND_TERRAINS:
        return "crop: non-land terrain"
    if _set(item.get("experimentGate")) and not _gate_open(item, served):
        return "crop: experiment closed"
    if not item.get("marketEntries"):
        return "crop: no market entry"
    if _level_conflict(item):
        return "crop: level requirement"
    if not _reward_values_read(item):
        return "crop: reward value"
    return None


def _rehome(node):
    if isinstance(node, dict):
        if node.get("className") == "World":
            node["name"] = HOME_WORLD
            node["strict"] = "true"
        for child in node.values():
            _rehome(child)
    elif isinstance(node, list):
        for child in node:
            _rehome(child)


def _served_experiments():
    # Lazy: themed_worlds reaches this module through the items and world_travel imports.
    import themed_worlds
    return themed_worlds.served_experiments()


def plan(records, served=None):
    """Return (patches, report) for the catalog without touching any record.

    patches maps catalog index to {"group", "market", "cash", "coins", "source"}.
    A patch with no market, cash or coins keeps the recovered price. The report
    lists each crop excluded from a locked group under "refused" (catalog index to
    reason). The plan reads only the pristine records, so the client payload and
    the server copy agree. served maps experiment names to their served variant;
    None reads the served client configuration.
    """
    if served is None:
        served = _served_experiments()
    siblings, tiers = {}, {}
    crop_siblings, crop_tiers = {}, {}
    for index, item in enumerate(records):
        if not isinstance(item, dict):
            continue
        if item.get("type") == CROP_TYPE:
            coin = _lenient_amount(item, "cost")
            if coin is not None:
                key = (item.get("subtype"), _grow_band(item))
                crop_siblings.setdefault(key, []).append((index, coin))
                if all(name == HOME_WORLD for name in _world_names(item)):
                    for tier in ((item.get("subtype"),), ()):
                        crop_tiers.setdefault(tier, []).append(coin)
        cash = _lenient_amount(item, "cash")
        if cash is None:
            continue
        type_, class_name, footprint = item.get("type"), item.get("className"), _footprint(item)
        siblings.setdefault((type_, class_name, item.get("subtype"), footprint), []).append((index, cash))
        if all(name == HOME_WORLD for name in _world_names(item)):
            for tier in ((type_, class_name, footprint), (type_, class_name), (type_,)):
                tiers.setdefault(tier, []).append(cash)
    for values in tiers.values():
        values.sort()
    for values in crop_tiers.values():
        values.sort()
    sibling_indexes = {key: [index for index, _ in entries] for key, entries in siblings.items()}
    crop_indexes = {key: [index for index, _ in entries] for key, entries in crop_siblings.items()}

    def nearest(entries, indexes, index):
        position = bisect.bisect_left(indexes, index)
        candidates = [entries[other] for other in (position - 1, position) if 0 <= other < len(entries)]
        return min(candidates, key=lambda entry: (abs(entry[0] - index), entry[0]))

    def sibling_price(index, item):
        key = (item.get("type"), item.get("className"), item.get("subtype"), _footprint(item))
        indexes = sibling_indexes.get(key)
        if not indexes:
            return None, None
        nearest_index, value = nearest(siblings[key], indexes, index)
        return value, "sibling:%d" % nearest_index

    def tier_price(item):
        footprint = _footprint(item)
        type_, class_name = item.get("type"), item.get("className")
        for tier, label in (((type_, class_name, footprint), "tier:footprint"),
                            ((type_, class_name), "tier:class"), ((type_,), "tier:type")):
            values = tiers.get(tier)
            if values:
                return values[(len(values) - 1) // 2], label
        return None, None

    def crop_sibling_price(index, item):
        key = (item.get("subtype"), _grow_band(item))
        indexes = crop_indexes.get(key)
        if not indexes:
            return None, None
        nearest_index, value = nearest(crop_siblings[key], indexes, index)
        return value, "sibling:%d" % nearest_index

    def crop_tier_price(item):
        for tier, label in (((item.get("subtype"),), "tier:subtype"), ((), "tier:crop")):
            values = crop_tiers.get(tier)
            if values:
                return values[(len(values) - 1) // 2], label
        return None, None

    patches = {}
    report = _empty_report()

    def exclude(group, reason, index=None, item=None):
        bucket = report["excluded"].setdefault(group, {})
        bucket[reason] = bucket.get(reason, 0) + 1
        if index is not None and item is not None and group == "locked" and item.get("type") == CROP_TYPE:
            report["refused"][index] = reason

    for index, item in enumerate(records):
        if not isinstance(item, dict):
            continue
        class_key = (item.get("type"), item.get("className"))
        if class_key not in ORDINARY_CLASSES:
            continue
        crop = class_key[0] == CROP_TYPE
        worlds = _world_names(item)
        if HOME_WORLD in worlds:
            continue  # Already sold on the Home Farm; left exactly as recovered.
        if any(not name for name in worlds):
            exclude("locked" if worlds else "exclusive", "malformed requirement", index, item)
            continue
        group = "locked" if worlds else "exclusive"
        cash, cost, bad = _prices(item)
        if group == "exclusive" and (cash is not None or cost is not None):
            continue  # Priced Home items are left exactly as recovered.
        if group == "exclusive" and bad:
            exclude(group, "malformed price", index, item)
            continue
        report["considered"] += 1
        if _foreign_requirement(item):
            exclude(group, "crop: special requirement" if crop else "requirement", index, item)
            continue
        if crop:
            blocked = next((reason for field, reason in CROP_BLOCKING if _set(item.get(field))), None)
        else:
            blocked = "prerequisite" if any(item.get(field) not in (None, "") for field in BLOCKING_FIELDS) else None
        if blocked:
            exclude(group, blocked, index, item)
            continue
        if group == "locked" and len(set(worlds)) > 1 and _compare(item) != "any":
            exclude(group, "multiple worlds", index, item)
            continue
        if group == "locked" and RESERVED_WORLDS.intersection(worlds):
            exclude(group, "reserved world", index, item)
            continue
        market = item.get("market") or None
        if market not in (None, FARM_CASH, COINS):
            exclude(group, "world currency", index, item)
            continue
        if group == "exclusive" and item.get("experimentGate") not in (None, ""):
            exclude(group, "experiment gate", index, item)
            continue
        if crop:
            reason = _crop_reason(item, served)
            if reason:
                exclude(group, reason, index, item)
                continue
        patch = {"group": group, "market": None, "cash": None, "coins": None, "source": None}
        own_cash = market == FARM_CASH and cash is not None
        own_coin = market in (None, COINS) and cost is not None
        if group == "locked" and (own_cash or own_coin):
            patch["source"] = "own"
        elif group == "locked" and cash is not None:
            patch.update(market=FARM_CASH, source="own")
        elif group == "locked" and bad:
            exclude(group, "malformed price", index, item)
            continue
        elif crop:
            value, source = crop_sibling_price(index, item)
            if value is None:
                value, source = crop_tier_price(item)
            if value is None:
                exclude(group, "crop: no price basis", index, item)
                continue
            patch.update(coins=str(value), source=source)
        else:
            value, source = sibling_price(index, item)
            if value is None:
                value, source = tier_price(item)
            if value is None:
                exclude(group, "no price basis", index, item)
                continue
            patch.update(market=FARM_CASH, cash=str(value), source=source)
        patches[index] = patch
        report["overlaid"] += 1
        report["groups"][group] = report["groups"].get(group, 0) + 1
        bucket = patch["source"].split(":")[0]
        report["sources"][bucket] = report["sources"].get(bucket, 0) + 1
        label = "%s/%s" % class_key if class_key[1] else "%s/(none)" % class_key[0]
        report["classes"][label] = report["classes"].get(label, 0) + 1
    return patches, report


def _mutate(item, patch):
    item["buyable"] = "true"
    item["archived"] = "no"
    for field in DATE_FIELDS:
        item.pop(field, None)
    if patch["group"] == "locked":
        if item.get("type") != CROP_TYPE:
            item.pop("experimentGate", None)
        _rehome(item.get("requirements"))
    if patch.get("market") is not None:
        item["market"] = patch["market"]
    if patch.get("cash") is not None:
        item["cash"] = patch["cash"]
    if patch.get("coins") is not None:
        item["cost"] = patch["coins"]


def _empty_report():
    return {"considered": 0, "overlaid": 0, "excluded": {}, "groups": {}, "sources": {}, "classes": {},
            "refused": {}}


def apply(records, *, server=False):
    """Overlay records in place and return the report. server=True also records keys."""
    global _overlaid, _refused
    if not ENABLED:
        if server:
            _overlaid, _refused = frozenset(), {}
        return _empty_report()
    patches, report = plan(records)
    keys = set()
    for index, patch in patches.items():
        item = records[index]
        if server:
            keys.add((item.get("name"), item.get("code")))
        _mutate(item, patch)
    if server:
        _overlaid = frozenset(keys)
        _refused = {(records[index].get("name"), records[index].get("code")): reason
                    for index, reason in report["refused"].items()}
    return report


def is_overlaid(item):
    """True for a server catalog record that the Home overlay derived or rehomed."""
    return isinstance(item, dict) and (item.get("name"), item.get("code")) in _overlaid


def crop_refusal(item):
    """The Home Farm refusal for a locked crop the overlay excluded, or None."""
    if not isinstance(item, dict):
        return None
    reason = _refused.get((item.get("name"), item.get("code")))
    return None if reason is None else "This crop is not sold on the Home Farm (%s)." % reason


def overlay_digest():
    """Digest of the code that defines the overlay, for derived-cache identity."""
    return hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()
