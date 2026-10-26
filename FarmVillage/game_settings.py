import os
import zlib
import xmltodict

from bundle import XML_DIR, CACHE_DIR
from persistence import load_catalog_cache

CONFIG_XML = os.path.join(XML_DIR, "gz", "v855098", "gameSettings.xml.gz")
CACHE_CONFIG_JSON = os.path.join(CACHE_DIR, "gz_v855098_gameSettings.json")

CONFIG_CMS_XML = os.path.join(XML_DIR, "gz", "v855098", "gameSettingsCMS.xml.gz")
CACHE_CONFIG_CMS_JSON = os.path.join(CACHE_DIR, "gz_v855098_gameSettingsCMS.json")

_cached_game_settings: dict = None
_cached_farming: dict = None
_xp_level_map: dict = None
_level_xp_map: dict = None

def _decode_game_settings(obj: bytes) -> dict:
    # Decompress
    obj_decomp:bytes = zlib.decompress(obj)

    # Decode Object
    arr:dict = xmltodict.parse(obj_decomp)

    return arr

def _decode_farming_entries(obj: bytes) -> dict:
    # client ref.: src/Managers/FarmGameSettingsManager.as (m_rawXml.farming.farmingEntry -> m_attributes)
    # The <farming> block the client turns into its getInt()/getString() attribute table does not live in
    # gameSettings.xml at all - it is in gameSettingsCMS.xml, which the client loads as a second settings
    # file (src/Init/ZGameSettingsInit.as). Flattened here to the same key -> value map getAttribute() reads.
    # Decompress
    obj_decomp: bytes = zlib.decompress(obj)

    # Decode Object
    arr: dict = xmltodict.parse(obj_decomp)

    # Flatten <farmingEntry key=.. value=../> into a plain dict
    entries = {}
    for settings in arr.values():
        for entry in (settings.get("farming") or {}).get("farmingEntry") or []:
            entries[entry["@key"]] = entry["@value"]

    return entries


def _valid_game_settings(value) -> bool:
    if not isinstance(value, dict) or not isinstance(value.get("settings"), dict):
        return False
    levels = value["settings"].get("levels")
    return (isinstance(levels, dict) and isinstance(levels.get("level"), list)
            and all(isinstance(level, dict) and "@requiredXP" in level and "@num" in level
                    for level in levels["level"]))


def _valid_farming_entries(value) -> bool:
    return isinstance(value, dict) and all(isinstance(key, str) and isinstance(entry, str)
                                          for key, entry in value.items())

def load_game_settings() -> None:
    print(" * Loading game settings cache...")
    global _cached_game_settings, _cached_farming
    _cached_game_settings = load_catalog_cache(
        CACHE_CONFIG_JSON, source=CONFIG_XML, decoder=__file__, schema=1,
        build=_decode_game_settings, validate=_valid_game_settings,
    )
    print(" * Loading farming settings cache...")
    _cached_farming = load_catalog_cache(
        CACHE_CONFIG_CMS_JSON, source=CONFIG_CMS_XML, decoder=__file__, schema=1,
        build=_decode_farming_entries, validate=_valid_farming_entries,
    )

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

# client ref.: src/Managers/FarmGameSettingsManager.as (getNumber/getAttribute)
# The same table as get_farming_int, for the entries that are not whole numbers (buyXpGainRatio is "0.01").
def get_farming_number(key: str, default: float = 0.0) -> float:
    global _cached_farming
    value = (_cached_farming or {}).get(key)
    return default if value is None else float(value)

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
    higher_xp = get_farming_int("higherLevelXp", 1500000)
    step = get_farming_int("higherLevelStep", 100000)
    if xp >= higher_xp and step > 0:
        return get_farming_int("higherLevelBegin", 101) + (xp - higher_xp) // step
    for x in sorted(_xp_level_map.keys(), key=int, reverse=True):
        if xp >= int(x):
            return int(_xp_level_map[str(x)])
    return None

def level_to_xp(level: int) -> int:
    level = int(level)
    global _level_xp_map
    if str(level) not in _level_xp_map:
        begin = get_farming_int("higherLevelBegin", 101)
        if level >= begin:
            return get_farming_int("higherLevelXp", 1500000) + (level - begin) * get_farming_int("higherLevelStep", 100000)
        return None
    return int(_level_xp_map[str(level)])
