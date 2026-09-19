import os
import zlib
import json
import xmltodict

from bundle import XML_DIR, CACHE_DIR

CONFIG_XML = os.path.join(XML_DIR, "gz", "v855098", "gameSettings.xml.gz")
CACHE_CONFIG_JSON = os.path.join(CACHE_DIR, "gz_v855098_gameSettings.json")

CONFIG_CMS_XML = os.path.join(XML_DIR, "gz", "v855098", "gameSettingsCMS.xml.gz")
CACHE_CONFIG_CMS_JSON = os.path.join(CACHE_DIR, "gz_v855098_gameSettingsCMS.json")

_cached_game_settings: dict = None
_cached_farming: dict = None
_xp_level_map: dict = None
_level_xp_map: dict = None

def _cache_game_settings() -> None:
    # Read .amf file
    obj:bytes = open(CONFIG_XML, 'rb').read()

    # Decompress
    obj_decomp:bytes = zlib.decompress(obj)

    # Decode Object
    arr:dict = xmltodict.parse(obj_decomp)

    # Save to cache as JSON
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
    json.dump(arr, open(CACHE_CONFIG_JSON, 'w'))

def _cache_farming_entries() -> None:
    # client ref.: src/Managers/FarmGameSettingsManager.as (m_rawXml.farming.farmingEntry -> m_attributes)
    # The <farming> block the client turns into its getInt()/getString() attribute table does not live in
    # gameSettings.xml at all - it is in gameSettingsCMS.xml, which the client loads as a second settings
    # file (src/Init/ZGameSettingsInit.as). Flattened here to the same key -> value map getAttribute() reads.
    obj: bytes = open(CONFIG_CMS_XML, 'rb').read()

    # Decompress
    obj_decomp: bytes = zlib.decompress(obj)

    # Decode Object
    arr: dict = xmltodict.parse(obj_decomp)

    # Flatten <farmingEntry key=.. value=../> into a plain dict
    entries = {}
    for settings in arr.values():
        for entry in (settings.get("farming") or {}).get("farmingEntry") or []:
            entries[entry["@key"]] = entry["@value"]

    # Save to cache as JSON
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
    json.dump(entries, open(CACHE_CONFIG_CMS_JSON, 'w'))

def load_game_settings() -> None:
    # If cache doesn't exist, create it
    if not os.path.exists(CACHE_CONFIG_JSON):
        print(" * No game settings cache found. Caching game config...")
        _cache_game_settings()

    # Load cache
    print(" * Loading game settings cache...")
    global _cached_game_settings
    _cached_game_settings = json.load(open(CACHE_CONFIG_JSON, 'r'))

    # If the farming attribute cache doesn't exist, create it
    if not os.path.exists(CACHE_CONFIG_CMS_JSON):
        print(" * No farming settings cache found. Caching farming config...")
        _cache_farming_entries()

    # Load farming attribute cache
    print(" * Loading farming settings cache...")
    global _cached_farming
    _cached_farming = json.load(open(CACHE_CONFIG_CMS_JSON, 'r'))

    # Initialize XP level mappings
    _xp_level_map_init()

def get_game_settings() -> list:
    global _cached_game_settings
    return _cached_game_settings["settings"]

# client ref.: src/Managers/FarmGameSettingsManager.as (getInt/getAttribute)
def get_farming_int(key: str, default: int = 0) -> int:
    global _cached_farming
    value = (_cached_farming or {}).get(key)
    return default if value is None else int(value)

# XP levels functions

def _xp_level_map_init() -> None:
    global _xp_level_map
    global _level_xp_map
    _xp_level_map = {}
    _level_xp_map = {}
    for level in get_game_settings()["levels"]["level"]:
        _xp_level_map[level["@requiredXP"]] = level["@num"]
        _level_xp_map[level["@num"]] = level["@requiredXP"]

def xp_to_level(xp: int) -> int:
    xp = int(xp)
    for x in sorted(_xp_level_map.keys(), key=int, reverse=True):
        if xp >= int(x):
            return int(_xp_level_map[str(x)])
    return None

def level_to_xp(level: int) -> int:
    level = int(level)
    global _level_xp_map
    if str(level) not in _level_xp_map:
        return None
    return int(_level_xp_map[str(level)])
