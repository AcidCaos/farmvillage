"""Versioned recovery overlay for English Countryside Village Stage 1.

The shipped en_US.swf retains the original six quest IDs, titles and task
action/type keys. Two independent March 2011 player walkthroughs corroborate
their order, counts and rewards:
https://char.tw/blog/post/33584086
https://farmvillefreyashawk.blogspot.com/p/english-countryside-guide.html

The archived 2020 questSettings_0.xml no longer defines this chapter. Its
serialized prerequisites, memStoreIds, skip prices and UI settings have not
been recovered. The linear England gate, private story slot, local memStoreIds
and frontend wrapper are explicit emulator compatibility choices. The Garage
reward uses the construction-stage xukgarage (kn); the observed Garage reward
does not establish which catalog variant the original server granted. Paid skips
are disabled rather than assigning unverified prices. This is the complete
six-quest Sheep Pen chapter, not the whole eight-stage England Village story.

This module only constructs definitions; importing it never reads player data
or modifies source catalogs or saves.
"""

from copy import deepcopy


OVERLAY_VERSION = 1
STORY_ENABLED = False
WORLD = "england"
MAP_WRAPPER_NAME = "restoredEnglandMap-00-001"
QUEST_NAMES = (
    "england-02-001", "england-02-002", "england-02-003",
    "england-02-004", "england-02-005", "england-02-007",
)

# These local IDs are outside every memStoreId in the archived quest catalog.
# They are compatibility identities, never claimed to be the original IDs.
LOCAL_MEMSTORE_IDS = dict(zip(QUEST_NAMES, (9102001, 9102002, 9102003, 9102004, 9102005, 9102007)))

# March 23, 2011 screenshot guide: https://char.tw/blog/post/33584084
# The later shipped storageConfig zeroed these retired initial-site filters.
# Share the recovered counts with the derived client config and server.
SHEEP_PEN_INITIAL_MATERIALS = {"woodenboard": 10, "nail": 10, "brick": 10}

# The observed display name does not establish whether the 2011 server granted
# kn or its completed variant kv. Choose the construction stage explicitly.
RESTORATION_CHOICES = {"england-02-004": "Garage reward uses construction-stage xukgarage (kn); original variant unconfirmed."}
UNRESOLVED_REWARDS = {}

_FACTS = (
    ("Make It Your Own", (("useItemByCode", "kf", 6), ("plowPlot", "", 10)),
     100, 1500, (("kw", 1),)),
    ("Getting Started", (("completeConstructionBuildingByCode", "ko", 1),
                         ("harvestByCode", "qe", 25)),
     150, 1500, (("CC", 1),)),
    ("Et Tu, Brutus?", (("buyItemByCode", "ct", 1), ("visitNeighbor", "", 6),
                       ("simpleAction", "viewQuestMap", 1)),
     200, 1500, (("ng", 1),)),
    ("Please Fence Me In", (("completeConstructionBuildingByCode", "ct", 1),
                           ("buyItemByCode", "vj", 8), ("expandFarm", "xukfarm14", 1)),
     200, 1500, (("kn", 1),)),
    ("I'll Get Ewe", (("buyItemByCode", "SH", 1),), 250, 2000, (("gk", 5),)),
    ("On the Lamb", (("buyItemByCode", "cy", 1),
                     ("completeConstructionBuildingByCode", "cy", 1)),
     250, 1500, (("2n", 1), ("nh", 1))),
)


def is_restored_quest(quest):
    """Bound stricter completion rules to this explicitly marked overlay."""
    return bool(quest and quest.get("name") in QUEST_NAMES and quest.get("restoredWorld") == WORLD)


def map_wrapper_definition():
    """A local UI adapter, deliberately outside the six story definitions.

    Presenting the original map requires a completed, zero-reward viewDialog
    quest. It never occupies an active story slot or enters completed history.
    """
    return {
        "name": MAP_WRAPPER_NAME, "memStoreId": None, "category": "mapTriggerQuest",
        "priority": 0, "ignoreSlotLimit": True, "icon": "none", "restoredWorld": WORLD,
        "prereqs": [{"type": "location", "value": WORLD}],
        "tasks": [{"action": "viewDialog", "type": "", "total": 1, "cashValue": 0, "level": 0}],
        "rewards": [], "children": [],
    }


def quest_definitions():
    """Return independent canonical definitions for both server and client XML."""
    result = {}
    for index, (name, facts) in enumerate(zip(QUEST_NAMES, _FACTS)):
        title, objectives, xp, coins, gifts = facts
        prereqs = [{"type": "location", "value": WORLD}]
        if index:
            prereqs.append({"type": "quest_complete", "value": QUEST_NAMES[index - 1]})
        result[name] = {
            "name": name, "title": title, "memStoreId": LOCAL_MEMSTORE_IDS[name],
            "category": "story", "priority": index, "ignoreSlotLimit": False,
            # The caller supplies an available local frontend image when
            # generating the XML. Non-"none" preserves ordinary quest dialogs.
            "icon": "restored-england-stage1",
            "restoredWorld": WORLD, "restorationVersion": OVERLAY_VERSION,
            "allowPaidSkip": False,
            "kill": False,
            "prereqs": prereqs,
            "tasks": [{"action": action, "type": code, "total": total,
                       "cashValue": 0, "level": 0} for action, code, total in objectives],
            "rewards": [{"type": "xp", "value": str(xp), "quantity": 1},
                        {"type": "coins", "value": str(coins), "quantity": 1}]
                       + [{"type": "item_grant", "value": code, "quantity": count}
                          for code, count in gifts],
            "children": list(QUEST_NAMES[index + 1:index + 2]),
        }
        if name in UNRESOLVED_REWARDS:
            result[name]["unresolvedRewards"] = UNRESOLVED_REWARDS[name]
        if name in RESTORATION_CHOICES:
            result[name]["restorationChoices"] = RESTORATION_CHOICES[name]
    return deepcopy(result)
