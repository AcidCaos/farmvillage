"""Five reviewed classic baby-to-adult Farm Cash transformations.

GrowableBaby32891 reads breedingAdult (not the legacy ``adult`` attribute).
CashGrowableBaby33131 charges growPrice; TAnimalTransform33150 sends the
source baby's captured snapshot. GrowableBaby32898 retains ID, position and
metadata while constructing the adult with a fresh bare-state harvest clock.
Random babies, Nursery random births and the separate sheep DNA growth engine
are not inferred from this deterministic contract.
"""
import copy
import json
import math

import engine
import items
import world_travel

# Explicit reviewed identities;8799 archived CashGrowableBaby rows do not imply
# blanket admission. Further numeric rows can be reviewed independently.
TRANSFORMS = {
    "calf": ("CX", "cow", 1),
    "calf_brown": ("CY", "cow_brown", 5),
    "foal": ("F2", "horse", 1),
    "foal_black": ("JI", "horse_black", 5),
    "foal_gray": ("FF", "horse_gray", 5),
}
REQUESTS_KEY = "_englandAnimalRequests"
RESPONSE_KEY = "_englandAnimalResponse"


def _whole(value, label, minimum=0):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or int(value) != value
            or not minimum <= value <= 2_147_483_647):
        raise ValueError(f"{label} must be a whole number.")
    return int(value)


def _contract(name):
    if name not in TRANSFORMS:
        raise ValueError("This animal's growth contract has not been restored.")
    code, adult_name, cost = TRANSFORMS[name]
    baby, adult = items.get_item_by_name(name), items.get_item_by_name(adult_name)
    if (not baby or baby.get("code") != code or baby.get("type") != "animal"
            or baby.get("className") != "CashGrowableBaby"
            or baby.get("breedingAdult") != adult_name or baby.get("growPrice") != str(cost)
            or not adult or adult.get("type") != "animal"
            or adult.get("className") not in (None, "", "Animal")
            or any(baby.get(key) or adult.get(key) for key in ("requirements", "prereqs", "purchasePrereqs"))):
        raise ValueError("This animal's original deterministic growth contract requires review.")
    return adult, cost


def _options(params):
    if not isinstance(params, (list, tuple)) or len(params) > 2:
        raise ValueError("Animal growth requires the original empty options.")
    for options in params:
        if (not isinstance(options, dict) or set(options) - {"firstWA"}
                or ("firstWA" in options and options["firstWA"] is not True)):
            raise ValueError("Animal growth cannot accept a client price or adult choice.")


def perform(save, snapshot, params, *, request_id=None, now):
    """Apply a saved deterministic baby's original payment and transition."""
    current = world_travel.guard_active_world(save)
    if current not in ("farm", "england"):
        raise ValueError("Classic animal growth is restored on Home and England only.")
    _options(params)
    if not isinstance(snapshot, dict):
        raise ValueError("Animal growth requires the saved baby's identity.")
    ident = _whole(snapshot.get("id"), "Baby object ID", 1)
    moment = _whole(now, "Animal growth time", 1)
    sequence = _whole(request_id, "Animal growth request sequence") if request_id is not None else None
    def encode(value):
        import pyamf
        if isinstance(value, pyamf.UndefinedType):
            return None
        raise ValueError("The animal growth request contains an unsupported value.")
    signature = json.dumps([current, snapshot, params], sort_keys=True, default=encode)
    history = save.get(REQUESTS_KEY, {})
    if not isinstance(history, dict) or not isinstance(history.get("receipts", {}), dict):
        raise ValueError("The saved animal growth retry history is malformed.")
    receipts = history.get("receipts", {})
    key = str(sequence)
    if sequence is not None and key in receipts:
        receipt = receipts[key]
        if not isinstance(receipt, dict) or receipt.get("signature") != signature:
            raise ValueError("An animal growth sequence was reused for a different action.")
        save[RESPONSE_KEY] = copy.deepcopy(receipt["response"])
        return receipt["id"]
    if sequence is not None and sequence <= _whole(history.get("highestSequence", -1), "Saved animal growth sequence", -1):
        raise ValueError("This animal growth request predates the retained retry history.")
    world_travel.guard_action_object(save, ident)
    owners = [obj for obj in save["world"]["objectsArray"] if obj.get("id") == ident]
    if (len(owners) != 1 or owners[0].get("deleted")
            or owners[0].get("className") != "CashGrowableBaby"
            or any(snapshot.get(key) != owners[0].get(key) for key in ("itemName", "className"))):
        raise ValueError("Animal growth requires one owned baby with its exact saved identity.")
    baby = owners[0]
    adult, cost = _contract(baby.get("itemName"))
    cash = save["userInfo"]["player"].get("cash")
    if isinstance(cash, bool) or not isinstance(cash, (int, float)) or not math.isfinite(cash) or cash < cost:
        raise ValueError("Not enough Farm Cash to grow this animal.")
    working = copy.deepcopy(save)
    owned = next(obj for obj in working["world"]["objectsArray"] if obj["id"] == ident)
    engine.apply_cash_diff(working, -cost)
    owned.update(itemName=adult["name"], className=adult.get("className") or "Animal",
                 state="bare", plantTime=moment * 1000)
    response = {"adultId": ident, "rewardLink": None}
    if "metadata" in owned:
        response["adultMetadata"] = copy.deepcopy(owned["metadata"])
    working[RESPONSE_KEY] = response
    if sequence is not None:
        history = working.setdefault(REQUESTS_KEY, {})
        history.setdefault("receipts", {})[key] = {"signature": signature, "id": ident,
                                                    "response": copy.deepcopy(response)}
        history["highestSequence"] = sequence
        while len(history["receipts"]) > 256:
            del history["receipts"][next(iter(history["receipts"]))]
    save.clear()
    save.update(working)
    return ident


def take_response(save):
    return save.pop(RESPONSE_KEY, {})


def start_session(save):
    save.pop(REQUESTS_KEY, None)
    save.pop(RESPONSE_KEY, None)


def guard_harvest(save, stored):
    """Refuse unrecovered England offspring/truffle outputs before mutation."""
    if (save.get("userInfo", {}).get("currentWorldType") != "england"
            or not isinstance(stored, dict)):
        return
    name = stored.get("itemName")
    if name in ("nurserybarn_finished", "nurserybarn_finished_complete"):
        raise ValueError("This Nursery's original offspring selection and reward callback are not restored.")
    if name in ("pigpen_finished", "pigpenv2_finished"):
        raise ValueError("This Pigpen's original truffle and offspring harvest rewards are not restored.")
