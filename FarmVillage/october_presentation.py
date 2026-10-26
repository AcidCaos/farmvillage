"""Borrow England's original wood control skin for the authored October village.

The caller must authenticate the selected village and check its private October
preset marker before passing active=True. Inactive calls return the original
compressed bytes exactly. This module imports no game code and performs no I/O.

Only Home's hudSkinConfig/hudAssets subtree changes in the derived response.
World identity, actions, travel, inventory, currencies, XP, world scores and
Instant Grow configuration retain their original data. The borrowed skin is
assets/hud/hudSkin_Eng.swf, manifest name 9d85543951222254223bd86b7263e603,
SHA256 51b8be340f66cdd2a3a7b8d5da43fcfc350c231e894a771ff7c1f58dd312bd22.

Authored compatibility choice: the original England XML names its three zCache
button states with an _england suffix, but the original SWF exports those states
with _farm instead. Use those actual linkage names in the derived response. All
42 resulting linkage names, including both friend-slot borders, are exported by
the same original wood skin. Top currency/XP meters are separate client controls
and retain their original presentation. No original XML or artwork is modified.
The .xml.gz protocol uses zlib bytes, matching the other derived client
configuration helpers in this runtime.
"""
from __future__ import annotations

import copy
import hashlib
import xml.etree.ElementTree as ET
import zlib


WORLD_SETTINGS_SOURCE = "xml/gz/v855098/worldSettings.xml.gz"
WORLD_SETTINGS_SHA256 = "769db5f72b5586b036792332c9c9c89dac43ca6ae2fc6f5ddb761d829d1c014e"
HUD_DONOR_WORLD = "england"
HUD_ASSET_PATH = "assets/hud/hudSkin_Eng.swf"
HUD_ASSET_MANIFEST_HASH = "9d85543951222254223bd86b7263e603"
HUD_ASSET_SHA256 = "51b8be340f66cdd2a3a7b8d5da43fcfc350c231e894a771ff7c1f58dd312bd22"
ZCACHE_EXPORTED_LINKAGES = {
    state: "zcache_" + state + "_farm" for state in ("normal", "over", "down")}

_BUTTON_PREFIXES = {
    "friendBarSingleArrow": "singleArrow",
    "friendBarDoubleArrow": "doubleArrow",
    "friendBarArrowLine": "arrowLine",
    "messageSignButton": "messageSign",
    "zoomOutButton": "zoomOut",
    "zoomInButton": "zoomIn",
    "cameraButton": "camera",
    "zCacheButton": "zcache",
    "fullScreenButton": "fullScreen",
    "graphicsButton": "graphics",
    "sfxButton": "sfx",
    "musicButton": "music",
}


def _single(parent, tag):
    found = parent.findall(tag)
    if len(found) != 1:
        raise ValueError("The original October HUD configuration is unavailable.")
    return found[0]


def _checked_donor(donor):
    if donor.attrib != {"path": HUD_ASSET_PATH}:
        raise ValueError("The original England HUD asset configuration changed.")
    expected = {
        "friendBarBackground": {None: "neighborBackground_england"},
        "optionsBackground": {None: "optionsBackground_england"},
        "friendBarSlotBackground": {
            "normal": "friendBar_normal_england", "over": "friendBar_over_england",
            "border": "friendBar_chat_normal_england",
            "borderOver": "friendBar_chat_over_england"},
        **{tag: {state: prefix + "_" + state + "_england"
                 for state in ("normal", "over", "down")}
           for tag, prefix in _BUTTON_PREFIXES.items()},
    }
    if len(donor) != len(expected) or {child.tag for child in donor} != set(expected):
        raise ValueError("The original England HUD control schema changed.")
    for child in donor:
        fields = expected[child.tag]
        if child.attrib:
            raise ValueError("The original England HUD control schema changed.")
        if None in fields:
            if len(child) or (child.text or "").strip() != fields[None]:
                raise ValueError("An original England HUD linkage changed.")
        else:
            if (len(child) != len(fields) or {node.tag for node in child} != set(fields)
                    or any(node.attrib or len(node) or (node.text or "").strip() != fields[node.tag]
                           for node in child)):
                raise ValueError("An original England HUD linkage changed.")


def world_settings_payload(raw: bytes, *, active: bool = False) -> bytes:
    """Return zlib XML with only the authenticated October Home control skin.

    Availability and save ownership remain the caller's responsibilities. This
    function never enables a destination or edits a save. Malformed or changed
    source data refuses before a derived response can be returned.
    """
    if not isinstance(raw, bytes) or type(active) is not bool:
        raise ValueError("The October HUD projection requires bytes and an explicit projection flag.")
    if not active:
        return raw
    if hashlib.sha256(raw).hexdigest() != WORLD_SETTINGS_SHA256:
        raise ValueError("The original world-settings source changed; the October HUD requires review.")
    try:
        root = ET.fromstring(zlib.decompress(raw))
    except (ET.ParseError, zlib.error) as error:
        raise ValueError("The original world-settings source is malformed.") from error
    if root.tag != "worlds":
        raise ValueError("The original world-settings schema changed.")
    home = _single(root, "world[@name='farm']")
    england = _single(root, "world[@name='england']")
    home_hud = _single(home, "hudSkinConfig")
    donor_hud = _single(england, "hudSkinConfig")
    original = _single(home_hud, "hudAssets")
    donor = _single(donor_hud, "hudAssets")
    if original.attrib != {"path": "assets/hud/hudSkin_Chat.swf"}:
        raise ValueError("The original Home HUD asset configuration changed.")
    _checked_donor(donor)
    replacement = copy.deepcopy(donor)
    zcache = _single(replacement, "zCacheButton")
    for state, linkage in ZCACHE_EXPORTED_LINKAGES.items():
        _single(zcache, state).text = linkage
    replacement.tail = original.tail
    index = list(home_hud).index(original)
    home_hud.remove(original)
    home_hud.insert(index, replacement)
    return zlib.compress(ET.tostring(root, encoding="utf-8", xml_declaration=True))
