"""The local crafting market's refresh contract for the recovered Flash client."""

from engine import timestamp_now


def view() -> dict:
    """Return an empty, current marketplace when no local stalls offer goods.

    TGetMarketView only runs its completion callback for a non-null result. Every
    array is required by MarketViewManager.updateViewFromResponse, even when the
    offline farm has no crafting stalls or goods to share with its neighbours.
    A null response strands the client's loading popup indefinitely.
    """
    return {
        "lastUpdated": timestamp_now(),
        "marketStalls": [],
        "craftedGoods": [],
        "craftingSkills": [],
        "ages": [],
    }
