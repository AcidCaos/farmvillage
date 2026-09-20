import os
import zlib
import json
import math
import xmltodict

from bundle import XML_DIR, CACHE_DIR
from game_settings import get_farming_number

# client ref.: src/Init/AvatarSettingsInit.as (loads "avatar.xml"), src/Classes/Avatar/AvatarConfigSettings.as
# The same file the client parses into AvatarItem objects, so the item ids, prices and categories decoded
# here are by construction the ones the avatar editor is looking at.
AVATAR_XML = os.path.join(XML_DIR, "gz", "v855098", "avatar.xml.gz")
CACHE_AVATAR_JSON = os.path.join(CACHE_DIR, "gz_v855098_avatar.json")

# Bumped whenever the decoded shape below changes, so an existing cache from an older server build is
# rebuilt instead of silently missing fields. (cache/ is disposable - deleting it forces a re-decode too.)
CACHE_VERSION:int = 1

_cached_items: dict = None   # itemId -> appearance item definition
_xp_per_cash: int = 0

# client ref.: src/Classes/Avatar/AvatarConfigSettings.as (MARKET_FREE)
MARKET_FREE:str = "free"

def _cache_avatar() -> None:
    # Read .xml.gz file
    obj:bytes = open(AVATAR_XML, 'rb').read()

    # Decompress
    obj_decomp:bytes = zlib.decompress(obj)

    # Decode Object
    arr:dict = xmltodict.parse(obj_decomp)

    # client ref.: src/Classes/Avatar/AvatarItem.as (fromXML)
    # Only the fields the server has to decide a purchase with. Everything else in an <appearanceItem>
    # (assets, keywords, icons, limited-sale dates) is read client-side straight out of the same XML - the
    # dates included: canBuy() refuses an out-of-window item before it ever queues a transaction, and every
    # recovered window closed in 2020, so enforcing them here would only reject purchases twice.
    items = {}
    for item in arr["avatar"]["appearanceItems"]["appearanceItem"]:
        market = item.get("market") or {}
        items[item["@itemId"]] = {
            "itemId": item["@itemId"],
            "name": item.get("@name"),
            "category": item.get("@category"),
            # an item with no <market> node parses to an empty market type client-side, which matches no
            # case in AvatarManager.buyAvatarItem's switch - it simply cannot be bought
            "market": market.get("@type") or "",
            "cost": int(market.get("@cost") or 0),
            "buyable": item.get("@buyable") != "false",
        }

    # Save to cache as JSON
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
    json.dump({
        "version": CACHE_VERSION,
        "items": items,
        # client ref.: src/Classes/Avatar/AvatarConfigSettings.as (getXpPerCash)
        "xpPerCash": int(arr["avatar"]["featureConfig"]["xpPerCash"]),
    }, open(CACHE_AVATAR_JSON, 'w'))

def _load_avatar_cache() -> dict:
    try:
        cached = json.load(open(CACHE_AVATAR_JSON, 'r'))
        if cached.get("version") == CACHE_VERSION:
            return cached
        print(" * Avatar cache is from an older server build. Re-caching avatar config...")
    except (OSError, ValueError, KeyError, AttributeError):
        print(" * No usable avatar cache found. Caching avatar config...")
    _cache_avatar()
    return json.load(open(CACHE_AVATAR_JSON, 'r'))

def load_avatar() -> None:
    # Load cache, (re)building it if it is missing or was written by an older build
    print(" * Loading avatar cache...")
    cached = _load_avatar_cache()
    global _cached_items, _xp_per_cash
    _cached_items = cached["items"]
    _xp_per_cash = cached["xpPerCash"]

# client ref.: src/Classes/Avatar/AvatarConfigSettings.as (getItemById)
def get_item_by_id(item_id) -> dict:
    global _cached_items
    return (_cached_items or {}).get(str(item_id))

# client ref.: src/Classes/Avatar/AvatarItem.as (isFree)
def item_is_free(item: dict) -> bool:
    return item["market"] == MARKET_FREE

# client ref.: src/Classes/Avatar/AvatarItem.as (get xp)
def get_item_xp(item: dict) -> int:
    if item["market"] == "cash":
        xp = item["cost"] * _xp_per_cash
    else:
        xp = math.floor(item["cost"] * get_farming_number("buyXpGainRatio"))
    return int(max(xp, get_farming_number("buyXpGainMin")))
