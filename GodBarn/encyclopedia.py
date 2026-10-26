"""Join attributed archive facts/history to detached catalog rows."""
from __future__ import annotations

import copy
from datetime import date
import gzip
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_THUMBNAIL = re.compile(r"/static/assets/items/[A-Za-z0-9_.-]+\.(?:png|gif|jpg|jpeg|webp)\Z")


def _strings(value):
    return list(dict.fromkeys(item for item in value if isinstance(item, str) and item)) if isinstance(value, list) else []


def _validate(data):
    if (not isinstance(data, dict) or type(data.get("schema")) is not int or data.get("schema") != 1
            or not isinstance(data.get("items", {}), dict)
            or not isinstance(data.get("shelves", []), list)
            or not isinstance(data.get("sources", []), list)):
        raise ValueError("Unsupported encyclopedia metadata.")
    for name, note in data.get("items", {}).items():
        if not isinstance(name, str) or not name or not isinstance(note, dict):
            raise ValueError("Encyclopedia items require named note objects.")
        for field, kind in (("facts", dict), ("releaseHistory", list), ("sourceIds", list), ("relatedItems", list)):
            if field in note and not isinstance(note[field], kind):
                raise ValueError("Invalid encyclopedia item field: " + field)
    seen = set()
    for shelf in data.get("shelves", []):
        if (not isinstance(shelf, dict) or not isinstance(shelf.get("id"), str) or not shelf["id"]
                or shelf["id"] in seen or not isinstance(shelf.get("items", []), list)):
            raise ValueError("Historical shelves require unique identities and item arrays.")
        seen.add(shelf["id"])
    return data


def load_metadata(directory):
    path = Path(directory) / "encyclopedia.json"
    compressed = Path(directory) / "encyclopedia.json.gz"
    if not path.is_file() and not compressed.is_file():
        return {"schema": 1, "items": {}, "shelves": [], "sources": []}
    def invalid_number(value):
        raise ValueError("Non-finite encyclopedia value.")
    contents = path.read_text() if path.is_file() else gzip.decompress(compressed.read_bytes()).decode("utf-8")
    return _validate(json.loads(contents, parse_constant=invalid_number))


def _sources(entries):
    result = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"]:
            continue
        item = copy.deepcopy(entry)
        url = item.get("url")
        try:
            parsed = urlsplit(url) if isinstance(url, str) else None
            if url and (parsed is None or parsed.scheme not in ("http", "https")
                        or not parsed.hostname or parsed.username or parsed.password):
                item.pop("url", None)
        except ValueError:
            item.pop("url", None)
        result.setdefault(item["id"], item)
    return result


def enrich_catalog(catalog, metadata):
    """Return detached rows/shelves, preserving identity and archive prices.

    Facts remain under encyclopedia.facts; missing gameplay fact keys are also
    exposed to existing consumers. Recorded codes must match the catalog.
    """
    _validate(metadata)
    sources = _sources(metadata.get("sources", []))
    notes = metadata.get("items", {})
    by_name = {}
    for item in catalog:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            by_name.setdefault(item["name"], item)
    shelves, memberships = [], {}
    for original in metadata.get("shelves", []):
        shelf = copy.deepcopy(original)
        shelf["items"] = [name for name in _strings(shelf.get("items", [])) if name in by_name
                          and (not notes.get(name, {}).get("code") or notes[name]["code"] == by_name[name].get("code"))]
        source_ids = _strings(shelf.get("sourceIds", [])) or ([shelf["sourceId"]] if isinstance(shelf.get("sourceId"), str) else [])
        shelf["sources"] = [copy.deepcopy(sources[key]) for key in source_ids if key in sources]
        shelf.setdefault("kind", "Sourced historical prize shelf")
        shelf.setdefault("note", shelf.get("description", ""))
        shelves.append(shelf)
        for name in shelf["items"]:
            memberships.setdefault(name, []).append(shelf["id"])
    enriched = []
    for original in catalog:
        if not isinstance(original, dict) or not isinstance(original.get("name"), str):
            continue
        item = copy.deepcopy(original)
        name = item.get("name")
        note = notes.get(name)
        matches = isinstance(note, dict) and (not note.get("code") or note["code"] == item.get("code"))
        if matches:
            detail = copy.deepcopy(note)
            detail["sources"] = [copy.deepcopy(sources[key]) for key in _strings(note.get("sourceIds", [])) if key in sources]
            detail["relatedItems"] = [related for related in _strings(note.get("relatedItems", [])) if related in by_name and related != name]
            item["encyclopedia"] = detail
            protected = {"name", "code", "cost", "cash", "market", "price", "archive", "image", "displayName"}
            for key, value in detail.get("facts", {}).items():
                if key not in protected and key not in item:
                    item[key] = copy.deepcopy(value)
            if (item.get("labelSource") != "localization"
                    and isinstance(note.get("displayName"), str) and note["displayName"].strip()):
                item["displayName"] = note["displayName"]
                item["labelSource"] = "historical-source"
            thumbnail = note.get("thumbnail")
            if (not isinstance(item.get("artwork"), dict)
                    and isinstance(thumbnail, dict) and isinstance(thumbnail.get("image"), str)
                    and _THUMBNAIL.fullmatch(thumbnail["image"])
                    and isinstance(thumbnail.get("sha256"), str) and _SHA256.fullmatch(thumbnail["sha256"])):
                item["image"] = thumbnail["image"]
                item["hasOriginalThumbnail"] = True
        if name in memberships and (matches or name not in notes):
            archive = item.get("archive")
            item["archive"] = archive if isinstance(archive, dict) else {}
            item["archive"]["collections"] = list(dict.fromkeys(_strings(item["archive"].get("collections", [])) + memberships[name]))
        enriched.append(item)
    return enriched, shelves


def history_years(item):
    detail = item.get("encyclopedia") if isinstance(item.get("encyclopedia"), dict) else {}
    history = detail.get("releaseHistory") if isinstance(detail.get("releaseHistory"), list) else []
    dates = [entry.get("date") for entry in history if isinstance(entry, dict)]
    archive = item.get("archive") if isinstance(item.get("archive"), dict) else {}
    availability = archive.get("availability") if isinstance(archive.get("availability"), dict) else {}
    dates.append(availability.get("start"))
    result = set()
    for value in dates:
        try:
            if isinstance(value, str) and len(value) == 10:
                result.add(str(date.fromisoformat(value).year))
        except ValueError:
            pass
    return result


def acquisition_methods(item):
    detail = item.get("encyclopedia") if isinstance(item.get("encyclopedia"), dict) else {}
    history = detail.get("releaseHistory") if isinstance(detail.get("releaseHistory"), list) else []
    methods = {entry["acquisition"] for entry in history if isinstance(entry, dict) and isinstance(entry.get("acquisition"), str) and entry["acquisition"]}
    archive = item.get("archive") if isinstance(item.get("archive"), dict) else {}
    original = archive.get("acquisition")
    if isinstance(original, str) and original and original != "Acquisition not recorded":
        methods.add(original)
    return methods


def history_filters(items):
    years, acquisitions = set(), set()
    for item in items:
        years.update(history_years(item))
        acquisitions.update(acquisition_methods(item))
    return {"years": sorted(years), "acquisitions": sorted(acquisitions)}


def filter_history(items, *, year="", acquisition=""):
    if not isinstance(year, str) or (year and (len(year) != 4 or not year.isdigit())):
        raise ValueError("History year must use four digits.")
    if not isinstance(acquisition, str):
        raise ValueError("Acquisition filter must be text.")
    return [item for item in items if (not year or year in history_years(item))
            and (not acquisition or acquisition in acquisition_methods(item))]
