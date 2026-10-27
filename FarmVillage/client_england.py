"""Derived original-client configuration for the restored England chapter.

Only the six canonical Stage 1 definitions and a zero-reward map presentation
wrapper are appended. The bundled archives are never overwritten. Artwork,
localization keys, task dispatch and dialogs use the original client's APIs;
the frontend selection and map wrapper are local compatibility choices.
"""

from functools import lru_cache
from pathlib import Path
import xml.etree.ElementTree as ET
import zlib

import pyamf

from bundle import XML_DIR
import england_progression


MAP_WRAPPER_NAME = england_progression.MAP_WRAPPER_NAME
QUEST_SOURCE = Path(XML_DIR) / "gz/v855098/questSettings_0.xml.gz"
STORAGE_SOURCE = Path(XML_DIR) / "gz/v855098/storageConfig.amf.gz"
CMS_SOURCE = Path(XML_DIR) / "gz/v855098/gameSettingsCMS.xml.gz"

# All these logical images resolve to shipped assethash entries and recovered
# local pixels. Their selection is a compatibility frontend, not recovered XML.
HEAD_IMAGE = "assets/dialogs/4d_elements/Questing/NPC_circle_duke_aviator.png"
BODY_IMAGE = "assets/dialogs/4d_elements/Questing/NPC_standing_duke_aviator.png"
PEN_ICON = "assets/decorations/expansions/uk/xuk_deco_sheeppen_icon.png"
POSTCARD_ICON = "assets/newsfeed/postcard_feed.png"
COMBINE_ICON = "assets/equipment/xuk_combine_construct_icon.png"
MAP_ASSET = "assets/dialogs/FV_questMap_england_2.swf"


def _bytes(source, default):
    if source is None:
        return default.read_bytes()
    return bytes(source) if isinstance(source, (bytes, bytearray)) else Path(source).read_bytes()


def _child(parent, tag, text):
    ET.SubElement(parent, tag).text = str(text)


def _frontend(parent, *, text_bundle, icon, reward_view=None):
    frontend = ET.SubElement(parent, "frontend")
    for name, value in (("avatarHeadImage", HEAD_IMAGE), ("avatarBodyImage", BODY_IMAGE),
                        ("textBundle", text_bundle), ("icon", icon),
                        ("completeShareFeedIcon", icon)):
        _child(frontend, name, value)
    if reward_view:
        _child(frontend, "rewardView", reward_view)


def _helper(task):
    action = task["action"]
    if action == "useItemByCode":
        return "gift_box"
    if action == "buyItemByCode":
        return "open_market"
    if action == "harvestByCode":
        return "plant_seed"
    if action == "completeConstructionBuildingByCode" and task["type"] in ("ct", "ko"):
        return "pop_storage_building_dialog"
    return None


def _quest_node(definition):
    node = ET.Element("quest", {
        "name": definition["name"], "category": definition["category"],
        "priority": str(definition["priority"]), "memStoreId": str(definition["memStoreId"]),
        "skip": "false", "kill": "false", "replay": "false", "mapLocation": "1-8",
    })
    prereqs = ET.SubElement(node, "prereqs")
    for prereq in definition["prereqs"]:
        ET.SubElement(prereqs, "prereq", {"type": prereq["type"], "value": str(prereq["value"])})
    children = ET.SubElement(node, "children")
    for name in definition["children"]:
        ET.SubElement(children, "child", {"type": "Quest", "value": name})
    tasks = ET.SubElement(node, "tasks")
    for task in definition["tasks"]:
        attrs = {"action": task["action"], "type": task["type"] or "",
                 "total": str(task["total"]), "cashValue": "0"}
        helper = _helper(task)
        if helper:
            attrs["helper"] = helper
        ET.SubElement(tasks, "task", attrs)
    rewards = ET.SubElement(node, "rewards")
    for reward in definition["rewards"]:
        ET.SubElement(rewards, "reward", {"type": reward["type"], "value": str(reward["value"]),
                                          "quantity": str(reward["quantity"])})
    name = definition["name"]
    icon = POSTCARD_ICON if name.endswith("001") else COMBINE_ICON if name.endswith("002") else PEN_ICON
    _frontend(node, text_bundle=name, icon=icon)
    return node


def _map_node():
    # The original QuestMapWindow.close emits incrementGenericFarmTask with
    # viewQuestMap. A separate UI-only viewDialog wrapper preserves the ordinary
    # reward-dialog completion callback on all six story quests.
    node = ET.Element("quest", {"name": MAP_WRAPPER_NAME, "category": "mapTriggerQuest",
                               "skip": "false", "kill": "false", "replay": "false",
                               "ignoreSlotLimit": "true", "priority": "0"})
    ET.SubElement(node, "prereqs")
    tasks = ET.SubElement(node, "tasks")
    ET.SubElement(tasks, "task", {"action": "viewDialog", "total": "1", "cashValue": "0"})
    ET.SubElement(node, "rewards")
    _frontend(node, text_bundle="england-02-003", icon="none", reward_view="questMap")
    return node


@lru_cache(maxsize=2)
def _quest_payload(raw):
    root = ET.fromstring(zlib.decompress(raw))
    if root.tag != "questSettings":
        raise ValueError("The source quest settings root is invalid.")
    added_names = set(england_progression.QUEST_NAMES) | {MAP_WRAPPER_NAME}
    for node in list(root):
        if node.tag == "quest" and node.get("name") in added_names:
            root.remove(node)
    for definition in england_progression.quest_definitions().values():
        root.append(_quest_node(definition))
    root.append(_map_node())
    return zlib.compress(ET.tostring(root, encoding="utf-8", xml_declaration=True))


def quest_payload(source=None):
    """Return zlib XML; source may be compressed bytes or an archive path."""
    raw = _bytes(source, QUEST_SOURCE)
    return _quest_payload(raw) if england_progression.STORY_ENABLED else raw


@lru_cache(maxsize=2)
def _storage_payload(raw):
    document = pyamf.get_decoder(pyamf.AMF3, zlib.decompress(raw)).readElement()
    records = document["storage"]["StorageBuilding"]
    targets = {"xuk_sheep_pen_construct", "xuk_sheep_pen"}
    found = set()
    for record in records:
        if record.get("name") not in targets:
            continue
        found.add(record["name"])
        matched = set()
        rows = record.get("itemName", [])
        rows = rows if isinstance(rows, list) else [rows]
        for row in rows:
            name = row.get("value")
            if row.get("part") not in (True, "true") or name not in england_progression.SHEEP_PEN_INITIAL_MATERIALS:
                continue
            if name in matched:
                raise ValueError("The Sheep Pen has duplicate construction material rows.")
            matched.add(name)
            row["need"] = str(england_progression.SHEEP_PEN_INITIAL_MATERIALS[name])
        if matched != set(england_progression.SHEEP_PEN_INITIAL_MATERIALS):
            raise ValueError("The original Sheep Pen material filter is incomplete.")
    if found != targets:
        raise ValueError("The original Sheep Pen storage filters are missing.")
    return zlib.compress(pyamf.encode(document, encoding=pyamf.AMF3).getvalue())


def storage_payload(source=None):
    """Return derived zlib AMF3 with observed 10/10/10 initial Sheep Pen parts."""
    return _storage_payload(_bytes(source, STORAGE_SOURCE))


@lru_cache(maxsize=2)
def _cms_payload(raw):
    root = ET.fromstring(zlib.decompress(raw))
    farming = root.find("farming")
    if farming is None:
        raise ValueError("The farming CMS settings are missing.")
    key = "england_questMap_maxLocation"
    matches = [node for node in farming.findall("farmingEntry") if node.get("key") == key]
    if len(matches) > 1:
        raise ValueError("The England map location setting is ambiguous.")
    entry = matches[0] if matches else ET.SubElement(farming, "farmingEntry", {"key": key})
    # Only Stage 1 is restored. Other locations stay locked on the original
    # eight-location map; this does not announce a completed England campaign.
    entry.set("value", "1")
    return zlib.compress(ET.tostring(root, encoding="utf-8", xml_declaration=True))


def cms_payload(source=None):
    """Clamp the original map to the single restored Village location."""
    raw = _bytes(source, CMS_SOURCE)
    return _cms_payload(raw) if england_progression.STORY_ENABLED else raw
