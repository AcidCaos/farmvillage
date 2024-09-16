import os
import zlib
import pyamf
from pyamf.amf3 import Decoder, TYPE_OBJECT
import json

from bundle import XML_DIR, CACHE_DIR

ITEMS_AMF = os.path.join(XML_DIR, "gz/v855038/items_opt.amf")
CACHE_ITEMS_JSON = os.path.join(CACHE_DIR, "gz_v855038_items_opt.json")

_cached_items: dict = None

def _cache_items() -> None:
    # Read .amf file
    obj:bytes = open(ITEMS_AMF, 'rb').read()

    # Decompress
    obj_decomp:bytes = zlib.decompress(obj)

    # Assert that it's an object
    assert obj_decomp[:1] == TYPE_OBJECT

    # Decode Object
    dec:Decoder = pyamf.get_decoder(pyamf.AMF3, obj_decomp)
    arr:dict = dec.readElement()

    # Save to cache as JSON
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
    json.dump(arr, open(CACHE_ITEMS_JSON, 'w'))

def load_items() -> None:
    # If cache doesn't exist, create it
    if not os.path.exists(CACHE_ITEMS_JSON):
        print(" * No items cache found. Caching items...")
        _cache_items()

    # Load cache
    print(" * Loading items cache...")
    global _cached_items
    _cached_items = json.load(open(CACHE_ITEMS_JSON, 'r'))

def get_items() -> list:
    global _cached_items
    return _cached_items["settings"]["items"]["item"]

def get_item_by_id(id:int) -> dict:
    # TODO
    # return get_items()[id]
    raise NotImplementedError

def get_item_by_name(name:str) -> dict:
    for item in get_items():
        if item["name"] == name:
            return item
    return None

def get_item_by_code(code:str) -> dict:
    for item in get_items():
        if item["code"] == code:
            return item
    return None