"""Local presents using the recovered Flash transaction response contracts.

The inbox is durable and has no expiry, eviction or daily streak requirement.
Only writable local farms receive presents; archived neighbour templates do not.
"""

import copy

import engine
import player
import storage
from items import get_item_by_name, get_item_by_code


FREE_GIFTS = ("chicken", "cow", "sheep", "goat", "horse")


def send(uid, item_name, recipients, item_context="normal", *, free=False):
    sender = player.session(uid)
    item = get_item_by_name(item_name)
    if item is None or item.get("giftable") not in (True, "true", "1"):
        return {"complete": False, "numSent": 0, "totalCost": 0}
    if free and item_name not in FREE_GIFTS:
        raise ValueError("This item is not in the free gift basket.")
    if not isinstance(recipients, (list, tuple)) or not recipients:
        raise ValueError("Choose at least one local farmer to receive the gift.")
    recipient_ids = list(dict.fromkeys(str(value) for value in recipients))
    if any(value == uid or value not in player.neighbor_uids(uid)
           or player.session(value) is None for value in recipient_ids):
        return {"complete": False, "numSent": 0, "totalCost": 0}
    cost = 0 if free else max(0, engine.catalog_price(item, "cash") or 0) * len(recipient_ids)
    if sender["userInfo"]["player"]["cash"] < cost:
        return {"complete": False, "numSent": 0, "totalCost": 0}
    engine.apply_cash_diff(sender, -cost)
    engine.apply_xp_increment(sender, int(item.get("buyXp") or 0) * len(recipient_ids))
    # Unsupported campaign contexts would dereference missing event configs in
    # receipt dialogs. All local presents use the client's ordinary receipt.
    for recipient_id in recipient_ids:
        recipient = player.session(recipient_id)
        recipient.setdefault("localPresents", []).append({
            "complete": True,
            "itemName": item["name"],
            "senderUID": uid,
            "presentXp": 0,
            "regiftItemCode": item["code"],
            "itemContext": "normal",
        })
        player.save_session(recipient_id)
    return {"complete": True, "numSent": len(recipient_ids), "totalCost": cost}


def regift(uid, item_code, recipient, item_context="normal"):
    item = get_item_by_code(item_code)
    if item is None:
        return {"complete": False, "numSent": 0, "totalCost": 0}
    return send(uid, item["name"], [str(recipient)], item_context)


def receive(uid, *, all_presents=True):
    save = player.session(uid)
    inbox = save.setdefault("localPresents", [])
    received = copy.deepcopy(inbox if all_presents else inbox[:1])
    for present in received:
        item = get_item_by_name(present["itemName"])
        if item is None:
            raise ValueError("A saved present references an unknown item.")
        storage.store_deposit_item_by_name(save, item["name"], group=storage.GIFTBOX_ID,
                                         sender=str(present["senderUID"]))
        import progression
        progression.record_gift(save, item)
    del inbox[:len(received)]
    if all_presents:
        return {"presents": received}
    return received[0] if received else {"complete": False}
