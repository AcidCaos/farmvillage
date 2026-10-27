import os
import zlib
import pyamf
from pyamf.amf3 import Decoder, TYPE_OBJECT

from bundle import XML_DIR, CACHE_DIR
from persistence import load_catalog_cache
import heritage_pricing
import mastery_signs

ITEMS_AMF = os.path.join(XML_DIR, "gz/v855038/items_opt.amf")
CACHE_ITEMS_JSON = os.path.join(CACHE_DIR, "gz_v855038_items_opt.json")

_cached_items: dict = None
_items_by_name = {}
_items_by_code = {}
_indexed_catalog = None

def _decode_items(obj: bytes) -> dict:
    # Decompress
    obj_decomp:bytes = zlib.decompress(obj)

    # Assert that it's an object
    assert obj_decomp[:1] == TYPE_OBJECT

    # Decode Object
    dec:Decoder = pyamf.get_decoder(pyamf.AMF3, obj_decomp)
    arr:dict = dec.readElement()

    return arr


def _valid_items(value) -> bool:
    if not isinstance(value, dict) or not isinstance(value.get("settings"), dict):
        return False
    items = value["settings"].get("items")
    return (isinstance(items, dict) and isinstance(items.get("item"), list)
            and all(isinstance(item, dict) and "name" in item and "code" in item
                    for item in items["item"]))

def load_items() -> None:
    print(" * Loading items cache...")
    global _cached_items
    _cached_items = load_catalog_cache(
        CACHE_ITEMS_JSON, source=ITEMS_AMF, decoder=__file__, schema=1,
        build=_decode_items, validate=_valid_items,
    )
    # Both overlays are in memory only; the cache stays the recovered catalog.
    # Sign eligibility needs the original World gates, before heritage rehomes them.
    mastery_signs.apply(get_items())
    heritage_pricing.apply(get_items(), server=True)
    _index_items()


def _index_items():
    # Keep the first match, as the original linear lookup did for historic
    # duplicate names/codes. Rebuild when a test or a catalog refresh replaces
    # the cache. Harvesting a large field must not scan 111,000 items per plot.
    global _indexed_catalog, _items_by_name, _items_by_code
    if _indexed_catalog is _cached_items and _indexed_catalog is not None:
        return
    names, codes = {}, {}
    for item in get_items():
        names.setdefault(item["name"], item)
        codes.setdefault(item["code"], item)
    _items_by_name, _items_by_code = names, codes
    _indexed_catalog = _cached_items

def get_items() -> list:
    global _cached_items
    return _cached_items["settings"]["items"]["item"]

def get_item_by_code(code:str) -> dict:
    _index_items()
    return _items_by_code.get(code)

def get_item_by_name(name:str) -> dict:
    _index_items()
    return _items_by_name.get(name)

def item_has_feature(item_data: dict, feature_name: str) -> bool:
    # A single-feature item decodes to a plain dict instead of a one-element list.
    features = (item_data.get("features") or {}).get("feature")
    if features is None:
        return False
    if isinstance(features, dict):
        features = [features]
    return any(feature.get("name") == feature_name for feature in features)
