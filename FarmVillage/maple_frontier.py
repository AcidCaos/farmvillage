"""Maple-specific boundaries while the original backend artifacts are absent.

Canada's archived access routes and storage-75 are recovered, but its genuine
starter/layout and section replacement rows are not.  TExpansionWorldAccess
perform11715 sends CanadaService.unlockCanadaWorld; acknowledging that unknown
service cannot stand in for the original unlock transaction.  The gateway's
existing savepoint turns these refusals into original-client errorType29.

This module never creates a farm, interprets imported state, charges currency,
enables a feature or changes another world's contract.
"""

UNLOCK_METHOD = "CanadaService.unlockCanadaWorld"

# Exact original CanadaInnovationManager TGenericTransaction senders, methods
# 19786/19791/19804/19846/19898/19906/19908/19914/19918/19920/19923/19939/
# 19941/19942/19943/19947/19948/19949/19957/19959/19961/19963/19965/19980/19993.
# These change tasks, currencies, ingredients, rewards or feature clocks. Their
# original backend is absent. Preserve featureEnd/startQuest's existing retired
# event startup compatibility; no prefix-wide rejection or new reward is used.
INNOVATION_MUTATIONS = frozenset("CanadaInnovationService." + method for method in (
    "resetDataAndSetNewWeek", "addInventoryTileUnlockCount", "grantRedeemPoints",
    "startNewDay", "addNormalCandiesToStation", "stationBuyBT", "collectSpecialCandy",
    "makeSpecialCandy", "tryBuyBT", "skipKidWaitTime", "resetSlot", "dumpTask",
    "skipDumpedTask", "skipTask", "getNewTask", "sinkGold", "sinkBushel",
    "redeemRewardPoints", "grantPointForNormalCandies", "grantPointForSpecialCandies",
    "updateKidsStatusByKidWithRetuenTime", "updateKidWaitTimer", "setNewTaskLayer",
    "harvestDecos", "updateTileUnlockCount"))


def refuse_unlock():
    """Refuse every access/option/replay without touching the player's save."""
    raise ValueError(
        "Maple Frontier is unavailable until its original starter, terrain and "
        "section replacement data are recovered and accepted.")


def guard_crafting_context(save):
    """Keep a legacy active Maple import out of globally keyed Home queues."""
    if save["userInfo"].get("currentWorldType") == "canada":
        raise ValueError("Crafting in Maple Frontier is not restored.")


def refuse_innovation_mutation():
    raise ValueError("Maple Frontier's CanadaInnovation transactions are not restored.")
