"""Read-only discovery across the complete God Barn archive.

Both companion modes use this query path so catalog exploration does not depend
on whether a live farm is connected. No game rules or saved farms are changed.
"""
from __future__ import annotations

from collections import Counter
import math
import re

if __package__:
    from .encyclopedia import filter_history
    from .engine import grant_refusal
    from .seasonal import annotate_item, calendar_context, matches_season, seasonal_counts, validate_filter
else:
    from encyclopedia import filter_history
    from engine import grant_refusal
    from seasonal import annotate_item, calendar_context, matches_season, seasonal_counts, validate_filter


ARTWORK_FILTERS = frozenset(("all", "exact", "missing"))
SORT_ORDERS = frozenset(("recommended", "name", "name-desc", "code", "type"))
_SEPARATORS = re.compile(r"[_/\\.\-]+")


def exact_artwork(item):
    """An archive identity match is distinct from a category illustration."""
    artwork = item.get("artwork")
    if isinstance(artwork, dict) and artwork.get("status") in ("exact", "missing"):
        return artwork["status"] == "exact" and bool(item.get("image"))
    return item.get("hasOriginalThumbnail") is True and bool(item.get("image"))


def localized_name(item):
    return (item.get("labelSource") == "localization"
            or item.get("displayNameSource") in ("localized", "localization")
            or item.get("nameSource") in ("localized", "localization"))


def catalog_coverage(items):
    total = len(items)
    exact = sum(exact_artwork(item) for item in items)
    localized = sum(localized_name(item) for item in items)
    return {"total": total, "exactArt": exact, "missingArt": total - exact,
            "localizedNames": localized, "internalNames": total - localized}


def _text_values(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, nested in value.items():
            # Hashes and byte counts identify files, not discoverable objects.
            if key not in ("sha256", "digest", "bytes", "width", "height"):
                yield from _text_values(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            yield from _text_values(nested)


def search_text(item):
    values = [str(item.get(key) or "") for key in
              ("name", "displayName", "code", "type", "subtype", "className", "description")]
    for key in ("artwork", "imageSources", "imageSource", "imageLogical", "thumbnailSource", "aliases"):
        values.extend(_text_values(item.get(key)))
    text = " ".join(values).casefold()
    return text + " " + _SEPARATORS.sub(" ", text)


def _name_key(item):
    return (str(item.get("displayName") or item.get("name") or "").casefold(),
            str(item.get("name") or "").casefold(), str(item.get("code") or ""))


def _matches(item, tokens):
    text = search_text(item)
    return all(token in text for token in tokens)


def _sort(items, order):
    if order == "recommended":
        return items
    if order in ("name", "name-desc"):
        return sorted(items, key=_name_key, reverse=order == "name-desc")
    if order == "code":
        return sorted(items, key=lambda item: (str(item.get("code") or "").casefold(), _name_key(item)))
    return sorted(items, key=lambda item: (str(item.get("type") or "other").casefold(),
                                         str(item.get("subtype") or "").casefold(), _name_key(item)))


def discover_catalog(catalog, params):
    """Return an annotated page and facets; ``params`` contains string values.

    Global coverage always describes the full unique catalog. Result coverage
    describes the selected results before pagination. Type facets ignore the
    selected type/subtype; subtype facets respect type and ignore subtype.
    Seasonal counts retain the original before-text/category-filter contract.
    """
    day, calendar = calendar_context(params.get("calendarDate", ""))
    selected_season = validate_filter(params.get("seasonal", ""))
    try:
        page = max(1, int(params.get("page", "1")))
        limit = min(120, max(1, int(params.get("limit", "48"))))
    except (ValueError, TypeError):
        raise ValueError("Catalog page and limit must be integers.") from None
    artwork = params.get("artwork", "all") or "all"
    order = params.get("sort", "recommended") or "recommended"
    if artwork not in ARTWORK_FILTERS:
        raise ValueError("Artwork filter must be all, exact, or missing.")
    if order not in SORT_ORDERS:
        raise ValueError("Catalog sort must be recommended, name, name-desc, code, or type.")
    year, acquisition = params.get("year", ""), params.get("acquisition", "")
    items = filter_history(catalog, year=year, acquisition=acquisition) if year or acquisition else list(catalog)
    collection = params.get("collection", "").strip()
    if collection:
        items = [item for item in items if collection in item.get("archive", {}).get("collections", [])]
    if params.get("grantable", "").lower() in ("1", "true", "yes"):
        items = [item for item in items if item.get("grantable") is True]
    if "names" in params:
        names = set(params["names"].split(","))
        items = [item for item in items if item.get("name") in names]
    season_counts = seasonal_counts(items, day)
    if selected_season not in ("", "all"):
        items = [item for item in items if matches_season(item, day, selected_season)]
    if artwork != "all":
        items = [item for item in items if exact_artwork(item) == (artwork == "exact")]
    tokens = params.get("q", "").strip().casefold()[:200].split()
    if tokens:
        items = [item for item in items if _matches(item, tokens)]
    types = Counter(str(item.get("type") or "other") for item in items)
    category, subtype = params.get("type", "").strip(), params.get("subtype", "").strip()
    if category == "expand_farm":
        subtype = "expand_farm"
    elif category and category != "all":
        items = [item for item in items if str(item.get("type") or "other") == category]
    subtypes = Counter(str(item.get("subtype") or "") for item in items)
    if subtype:
        items = [item for item in items if item.get("subtype") == subtype]
    items = _sort(items, order)
    total = len(items)
    pages = max(1, math.ceil(total / limit))
    page = min(page, pages)
    result = {"items": [annotate_item(item, day) for item in items[(page - 1) * limit:page * limit]],
              "total": total, "page": page, "pages": pages, "limit": limit,
              "calendar": calendar, "seasonalCounts": season_counts,
              "types": [{"type": key, "count": count} for key, count in sorted(types.items())],
              "subtypes": [{"subtype": key, "count": count} for key, count in sorted(subtypes.items()) if key],
              "coverage": catalog_coverage(catalog), "resultCoverage": catalog_coverage(items),
              "artwork": artwork, "sort": order}
    if subtype == "expand_farm":
        sizes = set()
        for item in items:
            try:
                size = float(item.get("squares"))
                if math.isfinite(size) and size.is_integer() and size > 0:
                    sizes.add(int(size))
            except (ValueError, TypeError, OverflowError):
                pass
        result["expansionSizes"] = sorted(sizes)
    return result


UNTABBED_ORIGINS = ("heritage", "exclusive", "other")
UNTABBED_LABELS = {
    "heritage": "Heritage – no market tab",
    "exclusive": "Original exclusive – no market tab",
    "other": "Other – no market tab",
}
# A "hidden" marketEntries type names no Market tab, so it does not count as one.
TABLESS_ENTRY_TYPES = frozenset(("hidden",))


def _market_entries(value):
    """Flatten marketEntries; the recovered data nests single, list and wrapper forms."""
    if isinstance(value, dict):
        value = value.get("marketEntry")
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return []
    entries = []
    for entry in value:
        if isinstance(entry, dict) and "marketEntry" in entry:
            entries.extend(_market_entries(entry))
        elif isinstance(entry, dict):
            entries.append(entry)
    return entries


def has_market_entry(raw, *, item_type=None):
    """True for an explicit Market tab or the client's sold-crop fallback.

    ``raw`` is the record's copied source fields (archive.raw); a missing record
    proves nothing, so it is not treated as untabbed. Sold seeds without an
    explicit marketEntries field use their type/subtype in the original client
    (FarmItem.parseMarket3EntriesType, source lines 7463-7474 / 7507-7518).
    Keep that bounded fallback separate from explicit hidden-only entries.
    """
    if not isinstance(raw, dict):
        return False
    if ("marketEntries" not in raw and (item_type or raw.get("type")) == "seed"
            and raw.get("buyable") in (True, "true", "1")):
        return True
    for entry in _market_entries(raw.get("marketEntries")):
        kind = entry.get("type")
        if isinstance(kind, str) and kind and kind not in TABLESS_ENTRY_TYPES:
            return True
    return False


def validate_untabbed_origins(data):
    """Check the generated origin index. None means it has not been generated."""
    if data is None:
        return None
    if not isinstance(data, dict) or type(data.get("schema")) is not int or data["schema"] != 1:
        raise ValueError("Unsupported untabbed origin index.")
    if not isinstance(data.get("items"), dict):
        raise ValueError("The untabbed origin index needs an items object.")
    for name, record in data["items"].items():
        if not name or not isinstance(record, dict) or record.get("origin") not in UNTABBED_ORIGINS:
            raise ValueError("Each untabbed origin needs a name and a known origin.")
        worlds = record.get("worlds", [])
        if not isinstance(worlds, list) or not all(isinstance(world, str) and world for world in worlds):
            raise ValueError("Untabbed worlds must be a list of names.")
        home = record.get("home")
        if home is not None and (not isinstance(home, dict) or home.get("currency") not in ("cash", "coins")
                                 or type(home.get("amount")) is not int or home["amount"] <= 0):
            raise ValueError("A Home price needs a currency and a positive whole amount.")
    return data


class UntabbedCatalog:
    """Catalog rows that no Market tab lists, labelled by origin and gift status.

    Membership comes from each row's recovered marketEntries and the sold-crop
    fallback. The origin index is generated by scripts/prepare_untabbed.py.
    Rows it does not name, or every row
    when it is absent, are labelled "other" until it is regenerated.
    """

    def __init__(self, catalog, origins=None):
        index = (validate_untabbed_origins(origins) or {}).get("items", {})
        self.generated = origins is not None
        self.items = []
        for item in catalog:
            archive = item.get("archive")
            raw = archive.get("raw") if isinstance(archive, dict) else None
            if not isinstance(raw, dict) or has_market_entry(raw, item_type=item.get("type")):
                continue
            record = index.get(item.get("name"), {})
            origin = record.get("origin", "other")
            item["untabbed"] = {
                "origin": origin,
                "label": UNTABBED_LABELS[origin],
                "worlds": list(record.get("worlds", [])),
                "home": record.get("home") if origin == "heritage" else None,
                # A sale flag is context only; it does not establish current visibility.
                "recordedForSale": raw.get("buyable") in (True, "true", "1"),
                "giftRefusal": grant_refusal(item),
            }
            self.items.append(item)
        self.summary = self._summarize()

    def _summarize(self):
        origins = {origin: {"label": UNTABBED_LABELS[origin], "total": 0, "giftable": 0}
                   for origin in UNTABBED_ORIGINS}
        refusals = Counter()
        for item in self.items:
            meta = item["untabbed"]
            origins[meta["origin"]]["total"] += 1
            if meta["giftRefusal"] is None:
                origins[meta["origin"]]["giftable"] += 1
            else:
                refusals[meta["giftRefusal"]] += 1
        giftable = sum(row["giftable"] for row in origins.values())
        return {"total": len(self.items), "giftable": giftable, "refused": len(self.items) - giftable,
                "origins": origins, "refusals": [{"reason": reason, "count": count}
                                                 for reason, count in refusals.most_common()],
                "generated": self.generated}

    def page(self, params):
        """Return one discovery page; ``params`` maps names to single string values."""
        origin = params.get("origin", "") or "all"
        gift = params.get("gift", "") or "giftable"
        if origin != "all" and origin not in UNTABBED_ORIGINS:
            raise ValueError("Untabbed origin must be heritage, exclusive, other, or all.")
        if gift not in ("giftable", "all"):
            raise ValueError("Gift filter must be giftable or all.")
        pool = self.items
        if origin != "all":
            pool = [item for item in pool if item["untabbed"]["origin"] == origin]
        if gift == "giftable":
            pool = [item for item in pool if item["untabbed"]["giftRefusal"] is None]
        result = discover_catalog(pool, params)
        result["untabbed"] = {"origin": origin, "gift": gift, "summary": self.summary}
        return result
