"""Hide archived feature invitations until their full entry path is accepted.

The original DynamicIconQueue and FeatureMessagingDefinition both consult
FEATURE_FLASHPARAM_HUD_ICON_BLACKLIST. Use that presentation gate rather than
writing seen flags or changing a player's progression. Core farming tools,
quests and the restored prize-game icons do not belong to this blacklist.
"""

from functools import lru_cache
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zlib

from bundle import XML_DIR


CMS_SOURCE = Path(XML_DIR) / "gz/v855098/gameSettingsCMS.xml.gz"
POST_INIT_SOURCE = Path(XML_DIR) / "gz/v855098/postInitSequence.xml.gz"

# Original presentation gates, recovered from FarmQuestManager's
# onPostTInitUserShowReward and WorldManager.swapFarm. Variant 2 defers
# zero-reward startup invitations into the existing per-icon queue; the world
# switch gate keeps travel from forcing that queue to display immediately.
# This does not acknowledge a dialog, alter a quest or change earned rewards.
QUEST_BUBBLE_SUPPRESSION_VARIANT = 2
SUPPRESS_WORLD_SWITCH_QUESTS_VARIANT = 1

# Reviewed terminal presentations for retired events. Missing feature options
# evaluate as zero in the original client, so these otherwise invite a player
# into old leaderboards, rewards and NPC windows on every fresh farm. These
# event economies are not restored; ordinary earned rewards stay untouched.
BLOCKED_POST_INIT_ACTIONS = frozenset((
    "forceGrantWhiteWinterRewards",
    "forceGrantTuscanyInnovationBonusReward",
    "forceGrantHalloween2019InnovationBonusReward",
    "forceGrantCanadaInnovationBonusReward",
    "forceGrantBoraboraInnovationBonusReward",
    "forceShowAnimalSAnctuaryV2FinalWindow",
    "forceGrantFarmersMarketInnovationBonusReward",
    "forceGrantFarmersMarketInnovationLeaderBoardReward",
    "forceGrantTropicalMarketInnovationBonusReward",
    "forceGrantTropicalMarketInnovationLeaderBoardReward",
    "forceGrantBoraboraInnovationLeaderBoardReward",
    "forceGrantGiftRacing2019BonusReward",
    "forceGrantBoatRacing2020BonusReward",
    "forceStopCoOpAndGrantGift",
    "forceGrantRussiaInnovationBonusReward",
    "forceGrantIsraelInnovationBonusReward",
    "forceGrantSouthindiaInnovationBonusReward",
    "forceGrantDec19InnovationBonusReward",
    "forceGrantIrelandInnovationWeeklyReward",
    "forceGrantWinternordInnovationCommunityReward",
    "forceGrantWinternordInnovationWeeklyReward",
    "forceGrantMadagascarInnovationCommunityReward",
    "forceGrantMadagascarInnovationWeeklyReward",
    "forceGrantAmsterdamInnovationBonusReward",
    "forceGrantWreathFestivalInnovationBonusReward",
    "forceGrantTwentiesInnovationWeeklyReward",
    "forceGrantPumpkinPartyInnovationWeeklyReward",
    "forceGrantWinternordInnovationChristmasReward",
    "forcePopupSpecialLEBundleWindowDay1",
    "forcePopupSpecialLEBundleWindowDay2",
    "forcePopupSpecialLEBundleWindowDay3",
    "forcePopupContingencyBuildableBonusRewardWindowDay1",
    "forcePopupContingencyBuildableBonusRewardWindowDay2",
    "forcePopupContingencyBuildableBonusRewardWindowDay3",
    "forcePopupContingencyBuildableBonusRewardWindowDay4",
    "forcePopupContingencyBuildableBonusRewardWindowDay5",
    "forcePopupContingencyBuildableBonusRewardWindowDay6",
    "forcePopupContingencyBuildableBonusRewardWindowDay7",
    # External email-program promotions, including the delayed fuel signup.
    "fuelBoost", "consumableCampaign", "consumableCampaignInactive",
))

# These invitations bypass the original HUD/feature gates. The pinned final
# client_compatibility stage suppresses their exact presentation methods instead.
# Keep them out of the FlashVar blacklist: these are review inventory identifiers,
# not DynamicIconQueue names. No seen flags or saved progress are written.
CLIENT_PRESENTATION_GATES = {
    "MarketVIPonlySale": (11244, 11246, 12394),
    "ShippingLicenses": (12193, 12402, 12403),
    "FarmwithOneClick3freeTurbo": (38972,),
    "ExpandStorage6to6": (11987, 12193, 12402, 12403),
    "AutomaticCottageChoiceReminder": (5911,),
    "MarketStallExpansion": (22845, 22858, 22903),
}

# Acceptance of a building or a basic world does not establish its archived
# marketing flow, social rewards, purchases or linked feature windows.
ACCEPTED_FEATURE_INVITATIONS = frozenset()

# These are shared invitation renderers, not the original cottage recipe UI.
UNACCEPTED_INVITATION_RENDERERS = frozenset((
    "FeatureCrafting", "GenericFeatureOfTheWeek",
))

# Pear Up calls TokenPlayFeatureService; that token/reward economy is not one
# of the restored scratch, slot or Pigo paths.
UNRESTORED_MINIGAME_ICONS = frozenset(("pearup",))

# Explicit preservation guard: these icons have independent restored paths.
PRESERVED_HUD_ICONS = frozenset((
    "scratchCard", "fcSlotMachine", "carnivalBooth", "QuestGenericIcon", "QuestManager",
))


@lru_cache(maxsize=2)
def _blocked_names(raw):
    root = ET.fromstring(zlib.decompress(raw))
    settings = root.find("featureMessagingManagerSettings")
    if settings is None:
        raise ValueError("The archived feature invitation settings are missing.")
    names = []
    for feature in settings.findall("feature"):
        name = feature.get("name")
        if not isinstance(name, str) or re.fullmatch(r"[A-Za-z0-9_]+", name) is None:
            raise ValueError("An archived feature invitation has an invalid name.")
        names.append(name)
    if not names or len(names) != len(set(names)):
        raise ValueError("The archived feature invitation names are empty or ambiguous.")
    blocked = ((set(names) - ACCEPTED_FEATURE_INVITATIONS)
               | UNACCEPTED_INVITATION_RENDERERS | UNRESTORED_MINIGAME_ICONS)
    if blocked & PRESERVED_HUD_ICONS:
        raise ValueError("An invitation gate would hide a restored HUD entry.")
    return tuple(sorted(blocked))


def blocked_hud_icons():
    """Return exact original-client icon/feature names, with no save changes."""
    return _blocked_names(CMS_SOURCE.read_bytes())


def hud_icon_blacklist():
    """Return the original client's comma-separated FlashVar value."""
    return ",".join(blocked_hud_icons())


@lru_cache(maxsize=2)
def _post_init_payload(raw):
    root = ET.fromstring(zlib.decompress(raw))
    if root.tag != "initActions" or root.find("userActionQueue") is None:
        raise ValueError("The archived post-init action settings are missing.")
    found = set()
    for queue in root:
        for action in list(queue):
            name = action.get("name")
            if name in BLOCKED_POST_INIT_ACTIONS:
                queue.remove(action)
                found.add(name)
    if found != BLOCKED_POST_INIT_ACTIONS:
        raise ValueError("The reviewed retired-event post-init actions have changed.")
    return zlib.compress(ET.tostring(root, encoding="utf-8", xml_declaration=True))


def post_init_payload():
    """Project retired-event presentations out of the served startup sequence."""
    return _post_init_payload(POST_INIT_SOURCE.read_bytes())
