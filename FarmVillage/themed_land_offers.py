"""Pure market-offer fence for the eleven basic themed farm contracts.

Their local empty starter is 50x50. Recovered widths 58 and above have not
passed expansion acceptance; widths adding original construction objects also
remain unsupported. Only the derived client catalog closes their buyable flag.
This module never mutates an item, an archived catalog, or a player's state.
"""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zlib

from bundle import XML_DIR

SETTINGS_SOURCE = Path(XML_DIR) / "gz/v855098/gameSettings.xml.gz"
FIRST_UNSUPPORTED_WIDTH = 58


def _specs():
    # Imported lazily: themed_worlds imports items while the catalog's derived
    # policy can itself be loading. The roster is the server's same SPECS table.
    from themed_worlds import SPECS
    return SPECS


def _world_nodes(value):
    if isinstance(value, dict):
        if value.get("className") == "World":
            yield value.get("name")
        for nested in value.values():
            yield from _world_nodes(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _world_nodes(nested)


def _width(value):
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        return int(value)
    return None


@lru_cache(maxsize=2)
def _added_widths(raw, worlds):
    settings = ET.fromstring(zlib.decompress(raw))
    result = {}
    for world in worlds:
        node = settings.find("farmExpansions/world[@name='%s']" % world)
        result[world] = frozenset(int(group.get("squares"))
            for group in (() if node is None else node.findall("farmExpansionAddedItems/addedItems"))
            if group.findall("addedItem"))
    return result


def blocked_offer(item):
    """Whether this exact themed land offer must stay absent from the Market.

    The caller changes only its derived buyable value. Base-size, Home, England,
    other world and non-land records retain their original availability.
    """
    if (not isinstance(item, dict) or item.get("type") != "change_farm"
            or item.get("subtype") != "expand_farm"):
        return False
    width = _width(item.get("squares"))
    name = item.get("name")
    if width is None or not isinstance(name, str):
        return False
    specs = _specs()
    owners = {world for world in _world_nodes(item.get("requirements"))
              if isinstance(world, str) and world in specs
              and name.startswith(specs[world]["prefix"] + "farm")}
    if not owners:
        return False
    if width >= FIRST_UNSUPPORTED_WIDTH:
        return True
    # Only the eleven base-size records normally reach this source-backed
    # check. Other archived worlds never trigger XML reads or broad policies.
    additions = _added_widths(SETTINGS_SOURCE.read_bytes(), tuple(sorted(specs)))
    return any(width in additions[world] for world in owners)


def policy_digest():
    """Cache identity binds policy code, the complete SPECS and settings bytes."""
    identity = {"specs": _specs(), "firstUnsupportedWidth": FIRST_UNSUPPORTED_WIDTH}
    digest = hashlib.sha256()
    for component in (Path(__file__).read_bytes(),
                      json.dumps(identity, sort_keys=True, separators=(",", ":")).encode(),
                      SETTINGS_SOURCE.read_bytes()):
        digest.update(len(component).to_bytes(8, "big"))
        digest.update(component)
    return digest.hexdigest()
