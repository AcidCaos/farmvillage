"""Durable local prize games using the recovered Flash request contracts.

The reward pools and odds remain the documented local substitutes. Pigo's
physics chooses the prize in the client; the server can validate membership and
payment, but cannot authenticate that physics outcome from this wire format.
"""

import copy
import math
import random

import engine
from game_settings import get_farming_int, xp_to_level
from items import get_item_by_name
import storage


SLOT_REWARDS = [
    {"type": "coins", "quantity": 500, "classType": "1", "weight": 30},
    {"type": "coins", "quantity": 2000, "classType": "1", "weight": 20},
    {"type": "free_spin", "quantity": 1, "classType": "1", "weight": 20},
    {"type": "turbo_charger", "quantity": 1, "classType": "2", "weight": 15},
    {"type": "cash", "quantity": 1, "classType": "2", "weight": 8},
    {"type": "item_grant", "value": "cow", "quantity": 1, "classType": "2", "weight": 4},
    {"type": "item_grant", "value": "horse", "quantity": 1, "classType": "3", "weight": 2},
    {"type": "cash", "quantity": 3, "classType": "3", "weight": 1},
]
SLOT_MYSTERY_PRIZES = [{"value": name} for name in ("cow", "horse", "sheep", "goat")]
SLOT_COST = 3  # FCSlotMachineWindow.SPIN_COST
SLOT_INITIAL_FREE_SPINS = 1  # FCSlotMachineWindow.INITIAL_FREE_SPINS
SLOT_WIN_CHANCE = .35
SLOT_FEATURE = "slotMachine"
SLOT_FREE_OPTION = "slotMachine_freespins"

SCRATCH_PRICE = 4  # Local substitute; original server price is unrecovered.
SCRATCH_WIN_CHANCE = .15
SCRATCH_REWARDS = [
    {"type": "coins", "value": "500", "weight": 30},
    {"type": "coins", "value": "2000", "weight": 20},
    {"type": "scratch_card", "weight": 15},
    {"type": "cash_from_card", "value": "1", "weight": 10},
    {"type": "item_grant", "item_name": "cow", "quantity": "1", "weight": 4},
    {"type": "item_grant", "item_name": "horse", "quantity": "1", "weight": 2},
    {"type": "cash_from_card", "value": "3", "weight": 4},
]
SCRATCH_MYSTERY_PRIZES = ("cow", "horse", "sheep", "goat")
PIGO_GAME = "pigov2game"
PIGO_PRIZES = ("chicken", "duck", "goat", "goose", "pig", "rabbit")
PIGO_SET_BONUS = "sheep"
PIGO_TOKEN = "consume_pigo_game_token"
PIGO_FREE_COUNTER = "SECURE_pigoFreePlayCount"
METHODS = frozenset((
    "SlotService.spin", "ScratchCardService.getScratchCardData",
    "ScratchCardService.clearCard", "ScratchCardService.grantReward",
    "PigoService.getGameSettings", "PigoService.buyToken",
    "PigoService.buyTokenPackage", "PigoService.grantReward",
))


def _integer(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(name + " must be an integer.")
    if not math.isfinite(value) or int(value) != value or value < minimum:
        raise ValueError(name + " is invalid.")
    return int(value)


def _state(save):
    state = save.setdefault("_localMinigames", {})
    if not isinstance(state, dict):
        raise ValueError("The saved minigame state is invalid.")
    options = save["userInfo"].setdefault("featureOptions", {}).setdefault(SLOT_FEATURE, {})
    options.setdefault(SLOT_FREE_OPTION, SLOT_INITIAL_FREE_SPINS)
    _integer(options[SLOT_FREE_OPTION], "The saved free-spin count")
    # Import an existing original allowance once. Client counter writes are
    # acknowledgments only; they cannot create or consume this private balance.
    if "pigoFreePlays" not in state:
        state["pigoFreePlays"] = _integer(
            save["userInfo"]["player"].get("actionCounts", {}).get(PIGO_FREE_COUNTER, 0),
            "The saved Pigo free-play count")
    return state


def start_session(save):
    """Reset sequence receipts for Flash's new session, retaining all balances."""
    state = _state(save)
    state["requests"] = {}
    state["highestSequence"] = -1
    save["userInfo"]["player"].setdefault("actionCounts", {})[PIGO_FREE_COUNTER] = state["pigoFreePlays"]


def acknowledge_action_counter(save, action):
    """Return true for the server-owned Pigo allowance, ignoring client writes."""
    if action != PIGO_FREE_COUNTER:
        return False
    state = _state(save)
    save["userInfo"]["player"].setdefault("actionCounts", {})[action] = state["pigoFreePlays"]
    return True


def _charge(save, amount):
    balance = _integer(save["userInfo"]["player"]["cash"], "The saved cash balance")
    if balance < amount:
        raise ValueError("There is not enough Farm Cash for this game.")
    engine.apply_cash_diff(save, -amount)


def _weighted(pool):
    return random.choices(pool, weights=[entry["weight"] for entry in pool])[0]


def _slot(save):
    options = save["userInfo"]["featureOptions"][SLOT_FEATURE]
    free = _integer(options[SLOT_FREE_OPTION], "The saved free-spin count")
    if free:
        options[SLOT_FREE_OPTION] = free - 1
    else:
        _charge(save, SLOT_COST)
    if random.random() < SLOT_WIN_CHANCE:
        reward = _weighted(SLOT_REWARDS)
        quantity = reward["quantity"]
        if reward["type"] == "free_spin":
            options[SLOT_FREE_OPTION] += quantity
        elif reward["type"] == "cash":
            engine.apply_cash_diff(save, quantity)
        elif reward["type"] == "coins":
            engine.apply_coins_diff(save, quantity)
        elif reward["type"] == "turbo_charger":
            engine.apply_turbo_chargers_diff(save, quantity)
        else:
            storage.store_deposit_item_by_name(save, reward["value"], quantity, group=storage.GIFTBOX_ID)
        return {"slots": [copy.deepcopy(reward) for _ in range(3)], "payOut": copy.deepcopy(reward)}
    # Guarantee a losing display without an unbounded random retry loop.
    slots = random.choices(SLOT_REWARDS, k=3)
    if slots[0] == slots[1] == slots[2]:
        slots[2] = next(reward for reward in SLOT_REWARDS if reward != slots[0])
    return {"slots": copy.deepcopy(slots), "payOut": None}


def _scratch_tile(reward):
    tile = {"type": reward["type"]}
    if reward["type"] == "item_grant":
        tile.update(value=get_item_by_name(reward["item_name"])["code"], quantity=reward["quantity"])
    elif reward["type"] != "scratch_card":
        tile["value"] = reward["value"]
    return tile


def _scratch_shell():
    return {"mysteryGifts": [{"value": get_item_by_name(name)["code"]} for name in SCRATCH_MYSTERY_PRIZES],
            "price_per_card": SCRATCH_PRICE, "card": None, "almostWon": None, "winEntry": None}


def _scratch_get(save, state, unlock):
    if not isinstance(unlock, bool):
        raise ValueError("Scratch card unlock must be a boolean.")
    active = state.get("scratchCard")
    if active is not None:
        if unlock:
            raise ValueError("Finish the current scratch card before buying another.")
        return copy.deepcopy(active["data"])
    free = _integer(state.get("scratchFreeCards", 0), "The saved free-card count")
    if not unlock and not free:
        return _scratch_shell()
    if unlock:
        _charge(save, SCRATCH_PRICE)
    else:
        state["scratchFreeCards"] = free - 1
    data = _scratch_shell()
    reward = _weighted(SCRATCH_REWARDS)
    tile = _scratch_tile(reward)
    won = random.random() < SCRATCH_WIN_CHANCE
    # ScratchCardWindow.scratchAll has only winEntry and almostWon branches.
    # Every loss needs almostWon to show Try Again and send clearCard.
    data["winEntry" if won else "almostWon"] = tile
    tiles = [copy.deepcopy(tile) for _ in range(3 if won else 2)]
    while len(tiles) < 9:
        available = [entry for entry in SCRATCH_REWARDS if tiles.count(_scratch_tile(entry)) < 2]
        tiles.append(_scratch_tile(_weighted(available)))
    random.shuffle(tiles)
    data["card"] = tiles
    state["scratchCard"] = {"data": copy.deepcopy(data), "reward": copy.deepcopy(reward) if won else None}
    return data


def _scratch_finish(save, state, claim):
    active = state.get("scratchCard")
    if active is None:
        return None  # Repeated reveal/clear has no new payout.
    reward = active["reward"]
    if claim != (reward is not None):
        raise ValueError("The scratch result does not match this completion request.")
    if reward is not None:
        kind = reward["type"]
        if kind == "scratch_card":
            state["scratchFreeCards"] = _integer(state.get("scratchFreeCards", 0), "Free cards") + 1
        elif kind == "cash_from_card":
            engine.apply_cash_diff(save, int(reward["value"]))
        elif kind == "coins":
            engine.apply_coins_diff(save, int(reward["value"]))
        else:
            storage.store_deposit_item_by_name(save, reward["item_name"], int(reward["quantity"]), group=storage.GIFTBOX_ID)
    del state["scratchCard"]
    return None


def _pigo(save, state, method, game_name, item_name=None):
    if game_name != PIGO_GAME:
        raise ValueError("This Pigo game is not supported.")
    item = get_item_by_name(game_name)
    price = engine.catalog_price(item, "cash") if item else None
    if price is None or price <= 0:
        raise ValueError("The Pigo game has no valid catalog price.")
    counts = save.setdefault("pigoState", {}).setdefault(game_name, {})
    if not isinstance(counts, dict):
        raise ValueError("The saved Pigo prize counts are invalid.")
    validated_counts = [_integer(counts.get(name, 0), "Pigo win count") for name in PIGO_PRIZES]
    had_bonus = all(count > 0 for count in validated_counts)
    if method == "getGameSettings":
        return [{"mysteryId": number, "itemName": name, "winCount": counts.get(name, 0)}
                for number, name in enumerate(PIGO_PRIZES)] + [
            {"mysteryId": -1, "itemName": PIGO_SET_BONUS, "winCount": int(had_bonus)}]
    if method in ("buyToken", "buyTokenPackage"):
        count = 3 if method == "buyTokenPackage" else 1
        cost = price * 3 - math.ceil(price * 3 * .1) if count == 3 else price
        _charge(save, cost)
        storage.store_deposit_item_by_name(save, PIGO_TOKEN, count, group=storage.GIFTBOX_ID)
        return "success"
    if item_name not in PIGO_PRIZES:
        raise ValueError("The requested item is not a prize in this Pigo game.")
    free = _integer(state["pigoFreePlays"], "Pigo free plays")
    level = xp_to_level(save["userInfo"]["player"]["xp"])
    if free and level >= get_farming_int("pigoFreePlayMinLevel", 6):
        # onPlayButtonClick consumes the positive allowance by setting it to
        # zero; this is one free play, even if an imported counter exceeds one.
        state["pigoFreePlays"] = 0
        save["userInfo"]["player"].setdefault("actionCounts", {})[PIGO_FREE_COUNTER] = 0
    elif not storage.store_withdraw_item_by_name(save, PIGO_TOKEN, 1, group=storage.GIFTBOX_ID):
        raise ValueError("A Pigo token is required before claiming a prize.")
    counts[item_name] = _integer(counts.get(item_name, 0), "Pigo win count") + 1
    storage.store_deposit_item_by_name(save, item_name, 1, group=storage.GIFTBOX_ID)
    if not had_bonus and all(counts.get(name, 0) > 0 for name in PIGO_PRIZES):
        storage.store_deposit_item_by_name(save, PIGO_SET_BONUS, 1, group=storage.GIFTBOX_ID)
    return {"complete": True}


def dispatch(save, method, params, *, request_id=None):
    """Commit a validated game command once; save transaction handles disk I/O.

    Sequence receipts survive server restart and cover the last 256 commands
    in the current Flash session. Older evicted sequences are rejected rather
    than replayed. Flash restarts its sequence on initUser, so receipts reset
    there; the original protocol cannot distinguish cross-session replays.
    """
    if not isinstance(method, str) or method not in METHODS or not isinstance(params, (list, tuple)):
        raise ValueError("This minigame command is not supported.")
    expected = (0 if method in ("SlotService.spin", "ScratchCardService.clearCard", "ScratchCardService.grantReward")
                else 2 if method == "PigoService.grantReward" else 1)
    if len(params) != expected:
        raise ValueError("The minigame command has the wrong number of parameters.")
    # Validate before receipt lookup: Python considers True == 1, but the
    # original scratch request requires a Boolean, including on retries.
    if method == "ScratchCardService.getScratchCardData":
        if not isinstance(params[0], bool):
            raise ValueError("Scratch card unlock must be a boolean.")
    elif method.startswith("PigoService.") and not all(isinstance(value, str) for value in params):
        raise ValueError("Pigo game and prize names must be strings.")
    working = copy.deepcopy(save)
    state = _state(working)
    receipts = state.setdefault("requests", {})
    key = str(_integer(request_id, "Minigame request sequence")) if request_id is not None else None
    signature = [method, list(params)]
    if key is not None:
        if key in receipts:
            if receipts[key]["signature"] != signature:
                raise ValueError("A minigame sequence was reused for a different command.")
            return copy.deepcopy(receipts[key]["result"])
        if int(key) <= state.get("highestSequence", -1):
            raise ValueError("This minigame request sequence has expired.")
    if method == "SlotService.spin":
        result = _slot(working)
    elif method == "ScratchCardService.getScratchCardData":
        result = _scratch_get(working, state, params[0])
    elif method.startswith("ScratchCardService."):
        result = _scratch_finish(working, state, method.endswith("grantReward"))
    else:
        result = _pigo(working, state, method.split(".")[1], *params)
    if key is not None:
        receipts[key] = {"signature": copy.deepcopy(signature), "result": copy.deepcopy(result)}
        state["highestSequence"] = int(key)
        while len(receipts) > 256:
            del receipts[next(iter(receipts))]
    save.clear()
    save.update(working)
    return result
