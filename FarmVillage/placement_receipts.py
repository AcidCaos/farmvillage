"""Durable transport retries around the existing world placement handler.

Snapshot tempIds deliberately do not survive disk serialization. A receipt
therefore records the successful original packet before replying, independently
of those temporary IDs. It grants nothing and skips no first-request guard.
Flash numeric sequences restart at initUser. Original sequenceID namespaces retain
exact receipts, so a delayed packet cannot become another purchase after reload.
"""
import json
import copy
import math
import pyamf

KEY = "_worldPlacementRequests"
EPOCHS_KEY = "_worldPlacementRequestEpochs"
NAMESPACE_LIMIT = 256


def start_session(save):
    # Keep original sequenceID receipts across initUser. Numeric-only legacy
    # callers retain their historical reset semantics; imported gameplay data
    # and unit metadata are never part of this bookkeeping.
    history = save.get(KEY, {})
    epochs = save.get(EPOCHS_KEY, {})
    if not isinstance(history, dict) or not isinstance(epochs, dict):
        raise ValueError("The saved placement retry history is invalid.")
    retained = {key: value for key, value in history.items()
                if isinstance(key, str) and ":" in key}
    if retained:
        save[KEY] = retained
        namespaces = {key.rsplit(":", 1)[0] for key in retained}
        save[EPOCHS_KEY] = {key: value for key, value in epochs.items() if key in namespaces}
    else:
        save.pop(KEY, None)
        save.pop(EPOCHS_KEY, None)


def dispatch(save, snapshot, params, request_id, perform):
    namespace = None
    if isinstance(request_id, tuple):
        if len(request_id) != 2:
            raise ValueError("A placement request needs its original sequenceID and sequence.")
        namespace, request_id = request_id
        if namespace is not None and (not isinstance(namespace, str) or not namespace or len(namespace) > 128):
            raise ValueError("The placement request sequenceID is invalid.")
    if (type(request_id) not in (int, float) or not math.isfinite(request_id)
            or int(request_id) != request_id or not 0 <= request_id <= 2_147_483_647):
        raise ValueError("The placement request sequence must be a nonnegative whole number.")
    sequence = int(request_id)
    key = (namespace + ":" if namespace is not None else "") + str(sequence)
    history = save.get(KEY, {})
    epochs = save.get(EPOCHS_KEY, {})
    if not isinstance(history, dict) or not isinstance(epochs, dict):
        raise ValueError("The saved placement retry history is invalid.")
    def encode(value):
        if isinstance(value, pyamf.UndefinedType):
            return None
        raise ValueError("The placement request contains an unsupported value.")
    signed_snapshot = copy.deepcopy(snapshot)
    # Ordinary original-client save objects use NaN for these optional clocks
    # and temporary-ID fields. Match the existing handler's null normalization
    # before JSON signing, while keeping invalid nonfinite gameplay values shut.
    for field in ("plantTime", "tempId", "buildTime"):
        value = signed_snapshot.get(field)
        if type(value) is float and math.isnan(value):
            signed_snapshot[field] = None
    signature = json.dumps([save["userInfo"].get("currentWorldType") or "farm", signed_snapshot, params],
                           sort_keys=True, allow_nan=False, default=encode)
    receipt = history.get(key)
    if receipt is not None:
        if (not isinstance(receipt, dict) or receipt.get("signature") != signature
                or type(receipt.get("id")) is not int):
            raise ValueError("A placement sequence was reused for another action.")
        return receipt["id"]
    if namespace is not None:
        state = save.get("_meadowsStorage", {})
        if not isinstance(state, dict) or namespace != state.get("sessionID"):
            raise ValueError("This placement sequenceID is stale or unknown.")
        highest = epochs.get(namespace, -1)
        if type(highest) is not int or not -1 <= highest <= 2_147_483_647:
            raise ValueError("The saved placement request sequence is invalid.")
        if sequence <= highest:
            raise ValueError("This placement request is older than the retained retry history.")
    elif sum(isinstance(key, str) and ":" not in key for key in history) >= 2048:
        raise ValueError("Reload the farm before recording more placements.")
    object_id = perform()
    ledger = save.setdefault(KEY, {})
    ledger[key] = {"signature": signature, "id": object_id}
    if namespace is not None:
        save.setdefault(EPOCHS_KEY, {})[namespace] = sequence
        namespaced = [key for key in ledger if isinstance(key, str) and ":" in key]
        for expired in namespaced[:-NAMESPACE_LIMIT]:
            del ledger[expired]
        retained = {key.rsplit(":", 1)[0] for key in ledger if isinstance(key, str) and ":" in key}
        save[EPOCHS_KEY] = {key: value for key, value in save[EPOCHS_KEY].items() if key in retained}
    return object_id
