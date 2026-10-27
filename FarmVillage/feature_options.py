"""Persist the client's feature preferences without granting game state.

FeatureOptionsManager.save sends the whole feature map; saveSingleFeature can
send only one option. Both therefore merge at the feature and option levels.
Values below an option remain opaque JSON and are replaced as a whole.
"""

import json
import math


MAX_DEPTH = 32
MAX_NODES = 32768
MAX_JSON_BYTES = 1024 * 1024
_SERVER_OWNED_FEATURES = frozenset(("irrigation", "UGCDeco", "slotMachine", "leslotmachine"))


def _validated_options(options):
    """Return detached JSON dictionaries, rejecting the entire invalid input."""
    if not isinstance(options, dict):
        raise ValueError("Feature options must be a feature map.")
    if any(not isinstance(value, dict) for value in options.values()):
        raise ValueError("Each feature must contain an option map.")
    ancestors = set()
    nodes = 0
    characters = 0

    def clone(value, depth):
        nonlocal nodes, characters
        nodes += 1
        if depth > MAX_DEPTH or nodes > MAX_NODES:
            raise ValueError("The feature options are too complex.")
        if value is None or isinstance(value, bool):
            return value
        if isinstance(value, str):
            characters += len(value)
            if characters > MAX_JSON_BYTES:
                raise ValueError("The feature options are too large.")
            return value
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError("Feature options must contain finite numbers.")
            return value
        if not isinstance(value, (dict, list)):
            raise ValueError("Feature options must contain JSON values.")
        identity = id(value)
        if identity in ancestors:
            raise ValueError("Feature options cannot contain circular values.")
        ancestors.add(identity)
        try:
            if isinstance(value, dict):
                result = {}
                for key, entry in value.items():
                    if not isinstance(key, str):
                        raise ValueError("Feature option names must be strings.")
                    clone(key, depth + 1)
                    result[key] = clone(entry, depth + 1)
                return result
            return [clone(entry, depth + 1) for entry in value]
        finally:
            ancestors.remove(identity)

    detached = clone(options, 0)
    # Count the actual JSON bytes as well as the traversal budget, since escaped
    # Unicode and short, numerous values cost more than their character counts.
    size = 0
    try:
        for chunk in json.JSONEncoder(allow_nan=False, separators=(",", ":")).iterencode(detached):
            size += len(chunk.encode("utf-8"))
            if size > MAX_JSON_BYTES:
                raise ValueError("The feature options are too large.")
    except (TypeError, OverflowError, RecursionError) as error:
        raise ValueError("Feature options must contain JSON values.") from error
    return detached


def apply(save, options):
    """Merge validated preferences in memory and return internal write counts.

    Server-managed ledgers and payout flags are ignored, including when present
    in a normal full-client snapshot. Unknown options are merely persisted;
    this function never interprets them or awards anything. No mutation occurs
    until both the incoming map and the complete merged result are validated.
    """
    incoming = _validated_options(options)
    if not isinstance(save, dict) or not isinstance(save.get("userInfo"), dict):
        raise ValueError("The saved feature options are invalid.")
    user_info = save["userInfo"]
    merged = _validated_options(user_info.get("featureOptions", {}))

    # Use the authoritative feature+option pairs rather than matching generic
    # names such as forceGranted, which are legitimate opaque options elsewhere.
    from commands import _FEATURE_END_GRANT_FLAGS
    protected_options = {(feature, option)
                         for (feature, _method), option in _FEATURE_END_GRANT_FLAGS.items()}
    saved = 0
    ignored = 0
    changed = False
    for feature, values in incoming.items():
        if feature in _SERVER_OWNED_FEATURES:
            ignored += len(values)
            continue
        accepted = {option: value for option, value in values.items()
                    if (feature, option) not in protected_options}
        ignored += len(values) - len(accepted)
        if accepted or not values:
            merged.setdefault(feature, {}).update(accepted)
            saved += len(accepted)
            changed = True

    # This also prevents many individually small calls from accumulating an
    # unbounded preference document. Assignment is the sole mutation point.
    merged = _validated_options(merged)
    if changed:
        user_info["featureOptions"] = merged
    return {"saved": saved, "ignored": ignored}
