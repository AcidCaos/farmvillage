"""Complete client definitions with reviewed purchase availability.

The archived catalog and God Barn history remain unchanged. Missing heritage
crop mastery gifts append through the same derived fallback as the server.
The Flash buyable getter parses offer dates repeatedly while filtering market
tabs. Giving conclusively expired offers a false buyable flag short-circuits
that work; every item definition remains available for farm and gift loading.
The supported, undated original puppies regain market availability only in
this derived client copy. Their prices, limits and other fields stay intact.
Unsupported cottage variants retain their complete definitions for owned farms
and gifts, with only their derived market buyable flag closed.
"""

from datetime import datetime, timedelta, timezone
import base64
import hashlib
from pathlib import Path
import re
import threading
import zlib

import pyamf

import heritage_pricing
import mastery_signs
import themed_land_offers
import themed_market_presentation


_cache = {}
_lock = threading.RLock()
_date_pattern = re.compile(r"\d{1,2}/\d{1,2}/\d{4}\Z")

# Reviewed against gameSettings.petData and the original items AMF. Three
# historical seasonal base puppies are omitted: their date gates stay intact.
# Exact name/code pairs prevent a similarly named unsupported item reopening.
RESTORED_PUPPIES = {
    "australiancattle_puppy_black_cash": "Ip",
    "australiancattle_puppy_brown_cash": "Iq",
    "australiancattle_puppy_cash": "Io",
    "bordercollie_puppy_cash": "68",
    "bordercollie_puppy_chocolate_cash": "70",
    "bordercollie_puppy_red": "71",
    "bordercollie_puppy_red_cash": "72",
    "dachshund_puppy_cream_cash": "yC",
    "dachshund_puppy_red_cash": "yB",
    "goldenretriever_puppy_cash": "62",
    "goldenretriever_puppy_cream_cash": "64",
    "goldenretriever_puppy_mahogany_cash": "66",
    "husky_puppy_brown_cash": "6x",
    "husky_puppy_grey_cash": "6w",
    "oldenglishsheepdog_puppy_black_cash": "76",
    "oldenglishsheepdog_puppy_gray_cash": "59",
    "oldenglishsheepdog_puppy_white_cash": "74",
    "shibainu_puppy_black_cash": "JW",
    "shibainu_puppy_cream_cash": "JX",
    "stbernard_puppy_blue_cash": "dN",
    "stbernard_puppy_cash": "dM",
    "stbernard_puppy_pink_cash": "dO",
    "terrier_puppy_black_cash": "JL",
    "terrier_puppy_cream_cash": "JM",
    "terrier_puppy_honey": "7D",
    "terrier_puppy_honey_cash": "0a",
}


def _restored_puppy(item):
    if (item.get("className") != "Pet"
            or item.get("name") not in RESTORED_PUPPIES
            or RESTORED_PUPPIES.get(item.get("name")) != item.get("code")
            or item.get("limitedStart") or item.get("limitedEnd")):
        return False
    currency = item.get("market") or "coins"
    if currency not in ("coins", "cash"):
        return False
    price = item.get("cash" if currency == "cash" else "cost")
    return isinstance(price, str) and price.isdecimal() and int(price) > 0


def _expired(value, day):
    # The source uses US calendar dates. A full extra UTC day keeps timezone
    # offsets and DST boundaries outside the optimization's decision window.
    if not isinstance(value, str) or not _date_pattern.fullmatch(value):
        return False
    try:
        end = datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        return False
    # Dates before FarmVille's existence can be unset/sentinel values.
    return 2009 <= end.year and end < day - timedelta(days=1)


def _cottage_policy():
    """Bind derived bytes to the same exact cottage roster as server purchase."""
    import crafting
    return (frozenset(crafting.COTTAGES.values()),
            hashlib.sha256(Path(crafting.__file__).read_bytes()).hexdigest())


def _unsupported_cottage(item, supported=None):
    if item.get("className") != "CraftingCottageBuilding":
        return False
    if supported is None:
        supported = _cottage_policy()[0]
    return item.get("name") not in supported


def purchase_required_level(item):
    """Read a scalar or repeated identical catalog level without guessing.

    The archive repeats level 1 in 29 records, but 12 lamb records conflict
    between 1 and 15. Keep those definitions while closing new purchases.
    """
    value = item.get("requiredLevel")
    if value is None or value == "":
        return 1
    entries = value if isinstance(value, list) else [value]
    if not entries or any(not (type(entry) is int and entry >= 0
            or isinstance(entry, str) and entry.isascii() and entry.isdecimal()) for entry in entries):
        raise ValueError("This item's recovered level requirement is invalid.")
    levels = {int(entry) for entry in entries}
    if len(levels) != 1:
        raise ValueError("This item's level requirement has conflicting catalog entries.")
    return max(1, levels.pop())


def _unresolved_level(item):
    try:
        purchase_required_level(item)
    except ValueError:
        return True
    return False


def _paid_projection_policy():
    # Import lazily: paid building logic imports items/engine during startup.
    import paid_buildings
    return (paid_buildings.client_item_projection,
            hashlib.sha256(Path(paid_buildings.__file__).read_bytes()).hexdigest())


def _generate(raw, day, supported_cottages=None):
    if supported_cottages is None:
        supported_cottages = _cottage_policy()[0]
    document = pyamf.get_decoder(pyamf.AMF3, zlib.decompress(raw)).readElement()
    records = document["settings"]["items"]["item"]
    if not isinstance(records, list):
        raise ValueError("The client item catalog has an invalid item array.")
    # Derive the same missing reward definitions as the server, while the
    # recovered World gates are still available for the heritage admission plan.
    mastery_signs.apply(records)
    heritage_pricing.apply(records)
    paid_projection = _paid_projection_policy()[0]
    for index, item in enumerate(records):
        item = paid_projection(item)
        item = themed_market_presentation.item_projection(item)
        records[index] = item
        buyable = item.get("buyable")
        if buyable in (True, "true") and _expired(item.get("limitedEnd"), day):
            item["buyable"] = "false" if isinstance(buyable, str) else False
        if (_unsupported_cottage(item, supported_cottages) or _unresolved_level(item)
                or themed_land_offers.blocked_offer(item)):
            item["buyable"] = "false" if isinstance(buyable, str) else False
        if _restored_puppy(item):
            item["buyable"] = "true"
            item["archived"] = "no"
    return zlib.compress(pyamf.encode(document, encoding=pyamf.AMF3).getvalue())


def _valid_cached(value):
    if not isinstance(value, dict) or not isinstance(value.get("payload"), str):
        return False
    try:
        return bool(base64.b64decode(value["payload"], validate=True))
    except ValueError:
        return False


def payload(source=None, *, now=None, cache_path=None):
    """Return zlib/AMF3; cache derived bytes without changing source or saves."""
    if source is None:
        from items import ITEMS_AMF
        from bundle import CACHE_DIR
        source = ITEMS_AMF
        if cache_path is None:
            cache_path = Path(CACHE_DIR) / "client-items-opt.json"
    raw = Path(source).read_bytes()
    day = datetime.fromtimestamp(now, timezone.utc).date() if now is not None else datetime.now(timezone.utc).date()
    source_digest = hashlib.sha256(raw).hexdigest()
    decoder_digest = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    supported_cottages, cottage_digest = _cottage_policy()
    overlay_digest = heritage_pricing.overlay_digest()
    mastery_digest = mastery_signs.policy_digest()
    themed_land_digest = themed_land_offers.policy_digest()
    _, paid_digest = _paid_projection_policy()
    themed_market_digest = themed_market_presentation.policy_digest()
    key = (source_digest, day.isoformat(), decoder_digest, cottage_digest, overlay_digest, mastery_digest, themed_land_digest, paid_digest, themed_market_digest, getattr(pyamf, "__version__", ""),
           str(cache_path) if cache_path is not None else None)
    with _lock:
        if key in _cache:
            return _cache[key]
        if cache_path is None:
            encoded = _generate(raw, day, supported_cottages)
        else:
            from persistence import load_catalog_cache
            cached = load_catalog_cache(
                cache_path, source=source, decoder=__file__,
                schema="client-amf-v7:" + day.isoformat() + ":" + str(getattr(pyamf, "__version__", "")) + ":" + cottage_digest + ":" + overlay_digest + ":" + mastery_digest + ":" + themed_land_digest + ":" + paid_digest + ":" + themed_market_digest,
                build=lambda contents: {"payload": base64.b64encode(_generate(contents, day, supported_cottages)).decode("ascii")},
                validate=_valid_cached,
            )
            encoded = base64.b64decode(cached["payload"], validate=True)
        # Retain at most the last two source/day combinations in memory.
        if len(_cache) >= 2:
            _cache.pop(next(iter(_cache)))
        _cache[key] = encoded
        return encoded
