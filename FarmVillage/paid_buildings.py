"""Paid original building actions, using saved progress and archived prices.

TCompleteNow, ExpandFManager and UpgradeManager optimistically mutate their
client object before sending. None of that incoming progress is authoritative.
Classic material construction is shared with construction.py; flower upgrades
retain the original UpgradeManager replacement and its individual cash price.
Unsupported harvest/reward systems are refused before a withdrawal.
"""
import copy
import json
import math

import pyamf

import construction
import engine
import items
import storage
import world_travel

ACTIONS = frozenset(("CompleteNow", "ExpandWithCurrency", "upgradeBuilding", "HarvestReadyNow"))
REQUESTS_KEY = "_paidBuildingRequests"
RESPONSE_KEY = "_paidBuildingResponse"
ORCHARD_REQUESTS_KEY = "_featureOrchardHarvestRequests"
_CLASSIC_TRANSFORMS = frozenset(("nurserybarn", "pigpen"))


def is_classic_transform(save, snapshot):
    """TTransformBuilding also carries these original cash completions."""
    if not isinstance(snapshot, dict):
        return False
    for obj in save.get("world", {}).get("objectsArray", []):
        if not isinstance(obj, dict) or obj.get("id") != snapshot.get("id"):
            continue
        if obj.get("itemName") in _CLASSIC_TRANSFORMS:
            return True
        # An identical durable retry still names the old construction site.
        if (snapshot.get("itemName") in _CLASSIC_TRANSFORMS
                and obj.get("itemName") == construction._CLASSIC[snapshot["itemName"]]):
            return True
    return False


def _whole(value, label, minimum=0):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or (isinstance(value, float) and not math.isfinite(value)) or int(value) != value
            or not minimum <= value <= 2_147_483_647):
        raise ValueError(f"{label} must be a whole number from {minimum} to 2147483647.")
    return int(value)


def _catalog_whole(value, label, minimum=0):
    if isinstance(value, str) and value.isascii() and value.isdigit():
        value = int(value)
    return _whole(value, label, minimum)


def _list(value):
    return value if isinstance(value, list) else [] if value is None else [value]


def _features(item, classname):
    return [feature for feature in _list((item.get("features") or {}).get("feature"))
            if isinstance(feature, dict) and feature.get("className") == classname]


def _bloom(item):
    return bool(item and item.get("type") == "bloom" and item.get("className") == "FeatureBuilding")


def client_item_projection(item):
    """Hide only the unrestored flower harvester in the derived client item."""
    if not _bloom(item):
        return item
    features = item.get("features")
    if not isinstance(features, dict):
        return item
    rows = _list(features.get("feature"))
    kept = [row for row in rows if not isinstance(row, dict) or row.get("className") != "HarvestFManager"]
    if len(kept) == len(rows):
        return item
    result = copy.deepcopy(item)
    result["features"]["feature"] = kept
    return result


def initialize_placement(snapshot, *, now):
    """Initialize catalog stages, real clocks and exact container defaults."""
    item = items.get_item_by_name(snapshot.get("itemName"))
    if storage.feature_container_class(item):
        # StorageBuilding.onBuilt -> addDefaultItems also runs for purchased
        # completed Gnome containers. The occupant belongs inside this object,
        # independently of unfinished construction's response.gift callback.
        result = construction.initialize_placement(snapshot)
        contents = []
        for row in _list(item.get("defaultItem")):
            if not isinstance(row, dict) or set(row) - {"name", "amount", "render"}:
                raise ValueError("The feature container default item requires review.")
            occupant = items.get_item_by_name(row.get("name"))
            if not occupant or not storage._feature_accepts(storage.feature_container_class(item), occupant):
                raise ValueError("The feature container default occupant is incompatible.")
            quantity = _catalog_whole(row.get("amount", "1"), "Default occupant quantity", 1)
            contents.append({"itemCode": occupant["code"], "numItem": quantity})
        if sum(row["numItem"] for row in contents) > storage._feature_capacity(result, item):
            raise ValueError("The feature container default occupants exceed capacity.")
        result.update(contents=contents, state="built")
        return result
    if storage.orchard_container_class(item):
        result = construction.initialize_placement(snapshot)
        result.update(state="bare", itemOrder=[],
                      plantTime=_whole(now, "Orchard placement time", 1) * 1000)
        return result
    if not _bloom(item):
        return snapshot
    result = copy.deepcopy(snapshot)
    result.update(className=item["className"], state="bare", isFullyBuilt=True,
                  expansionLevel=_catalog_whole(item.get("initialExpansionLevel", "1"),
                                                "Initial flower expansion level", 1),
                  expansionParts={}, capacity=_catalog_whole(item.get("capacity", "0"),
                                                             "Initial flower capacity"),
                  contents=[], plantTime=_whole(now, "Flower placement time", 1) * 1000)
    return result


def preserve_fields(stored, incoming, *, action=None):
    """A stale move must not undo a paid flower replacement or expansion."""
    old = items.get_item_by_name((stored or {}).get("itemName"))
    new = items.get_item_by_name(incoming.get("itemName"))
    if stored and not _bloom(old) and _bloom(new):
        raise ValueError("A flower snapshot cannot replace a different saved object.")
    result = copy.deepcopy(incoming)
    if _bloom(old):
        fields = ["itemName", "className", "expansionLevel", "expansionParts", "capacity", "isFullyBuilt", "contents",
                  "state", "plantTime", "buildTime"]
        for field in fields:
            if field in stored:
                result[field] = copy.deepcopy(stored[field])
            else:
                result.pop(field, None)
    return result


def guard_action(action, stored, incoming):
    """Reject plot mutations and missing harvest effects for feature buildings."""
    owned_item = items.get_item_by_name((stored or {}).get("itemName"))
    incoming_item = items.get_item_by_name((incoming or {}).get("itemName"))
    for item in (owned_item, incoming_item):
        if not item:
            continue
        if item.get("className") == "LootableFixedFeatureBuilding":
            if action == "harvest":
                raise ValueError("This building's original harvest loot table is unavailable.")
            if action in ("plow", "plant", "clearWithered", "use"):
                raise ValueError("This plot action cannot change a finite feature building.")
        if storage.orchard_container_class(item) and action in ("plow", "plant", "clearWithered", "use"):
            raise ValueError("This plot action cannot change an Orchard.")
        if (construction._giving_building(item) or storage.feature_container_class(item)) and action in (
                "harvest", "plow", "plant", "clearWithered", "use"):
            raise ValueError("This world action cannot change a feature container.")
    if not (_bloom(items.get_item_by_name((stored or {}).get("itemName")))
            or _bloom(items.get_item_by_name((incoming or {}).get("itemName")))):
        return
    if action == "harvest":
        raise ValueError("Flower harvest rewards are not restored on this server.")
    if action not in ("place", "move", "store", "sell", "clear", "getStorageInfo", "neighborAct"):
        raise ValueError("This world action is not supported for the flower.")


def _options(params):
    if isinstance(params, dict) and set(params) <= {0, 1, "0", "1"}:
        params = [params.get(0, params.get("0", {}))] + (
            [params.get(1, params.get("1"))] if 1 in params or "1" in params else [])
    if isinstance(params, (list, tuple)) and params and params[-1] == {"firstWA": True}:
        params = params[:-1]
    if not isinstance(params, (list, tuple)) or len(params) > 1:
        raise ValueError("Paid building actions require their original options map.")
    options = params[0] if params else {}
    if not isinstance(options, dict):
        raise ValueError("Paid building options must be a map.")
    return {key: value for key, value in options.items() if not isinstance(value, pyamf.UndefinedType)}


def _owned(save, action, snapshot):
    if not isinstance(snapshot, dict) or snapshot.get("deleted"):
        raise ValueError("A paid building action requires its saved building.")
    ident = _whole(snapshot.get("id"), "Building object ID")
    world_travel.guard_action_object(save, ident)
    objects = save.get("world", {}).get("objectsArray")
    if not isinstance(objects, list):
        raise ValueError("The saved building collection is invalid.")
    matches = [obj for obj in objects if isinstance(obj, dict) and obj.get("id") == ident and not obj.get("deleted")]
    if len(matches) != 1:
        raise ValueError("A paid building action requires one owned building with a unique ID.")
    obj = matches[0]
    item = items.get_item_by_name(obj.get("itemName"))
    if not item or obj.get("className") != item.get("className"):
        raise ValueError("The saved building's catalog identity is invalid.")
    names = {item["name"]}
    if action == "CompleteNow" and item["name"] in construction._CLASSIC:
        names.add(construction._CLASSIC[item["name"]])
    incoming = items.get_item_by_name(snapshot.get("itemName"))
    if snapshot.get("itemName") not in names or not incoming or snapshot.get("className") != incoming.get("className"):
        raise ValueError("The paid building request does not match its saved identity.")
    return obj, item


def _balance(value, label):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or (isinstance(value, float) and not math.isfinite(value)) or value < 0):
        raise ValueError(f"The saved {label} balance is invalid.")
    return value


def _charge(save, prices):
    player = save["userInfo"]["player"]
    # Validate every balance first, including mixed-currency material stages.
    for currency, cost in prices.items():
        _whole(cost, "Building purchase cost")
        if currency in ("cash", "coins"):
            balance = _balance(player.get("cash" if currency == "cash" else "gold"), currency)
        else:
            currencies = player.get("worldCurrencies")
            record = currencies.get(currency) if isinstance(currencies, dict) else None
            if not isinstance(record, dict):
                raise ValueError("The saved building material currency is unavailable.")
            balance = _balance(record.get("total"), currency)
        if balance < cost:
            raise ValueError(f"Not enough {currency} for this building action.")
    for currency, cost in prices.items():
        if currency == "cash":
            engine.apply_cash_diff(save, -cost)
        elif currency == "coins":
            engine.apply_coins_diff(save, -cost)
        else:
            player["worldCurrencies"][currency]["total"] -= cost


def _stage(save, obj, item):
    if _bloom(item):
        expand = _features(item, "ExpandFManager")
        if len(expand) != 1 or len(_features(item, "UpgradeManager")) != 1:
            raise ValueError("This flower's original feeding component is missing or ambiguous.")
        level = _whole(obj.get("expansionLevel", _catalog_whole(item.get("initialExpansionLevel", "1"),
                                                              "Initial flower expansion level", 1)),
                       "Saved flower expansion level", 1)
        upgrades = _list(expand[0].get("upgrade"))
        if len(upgrades) != 1 or not isinstance(upgrades[0], dict):
            raise ValueError("This flower has unsupported feeding stages.")
        upgrade = upgrades[0]
        if (set(upgrade) != {"level", "capacity", "matsNeeded", "part"}
                or _catalog_whole(upgrade.get("level"), "Flower feeding level", 1) != 2
                or _catalog_whole(upgrade.get("capacity"), "Flower feeding capacity") != 0):
            raise ValueError("This flower's feeding progression is not restored.")
        if level != 1:
            raise ValueError("This flower is already fully fed.")
        requirements = construction._requirements(upgrade.get("part"))
        if (len(requirements) != 1 or next(iter(requirements.values()))[0]["name"] != "part_flowerfood"
                or _catalog_whole(upgrade.get("matsNeeded"), "Flower food requirement", 1)
                   != sum(count for _, count in requirements.values())):
            raise ValueError("This flower does not use the recovered flower-food contract.")
        parts = obj.setdefault("expansionParts", {})
        if not isinstance(parts, dict):
            raise ValueError("The saved flower food must be a map.")
        counts = {code: _whole(parts.get(code, 0), "Saved flower food quantity") for code in requirements}
        if any(counts[code] > needed for code, (_, needed) in requirements.items()):
            raise ValueError("The saved flower food exceeds its authored requirement.")
        if obj.get("contents") not in (None, [], {}):
            raise ValueError("Unload unsupported contents before feeding this flower.")
        return False, (2, 0), requirements, counts
    if not construction.manages(item):
        raise ValueError("This building's construction and expansion rewards are not restored.")
    if construction._lootable_building(item) and not construction._built(obj, item):
        raise ValueError("This finite feature must have its original completed building state.")
    initial = not construction._built(obj, item)
    if initial:
        requirements = construction._initial_requirements(item)
        rows, ledger = construction._contents(save, obj)
        counts = {code: ledger.get(code, [0])[0] for code in requirements}
        if any(row["numItem"] > 0 and code not in requirements for code, row in rows.items()):
            raise ValueError("Unload unsupported contents before completing this construction site.")
        stage = (None, None)
    else:
        upgrade = construction._next_upgrade(obj, item)
        if upgrade is None:
            raise ValueError("This building has no further supported material expansion.")
        level, capacity, requirements = upgrade
        parts = obj.setdefault("expansionParts", {})
        if not isinstance(parts, dict):
            raise ValueError("Building expansion parts must be a map.")
        counts = {code: _whole(parts.get(code, 0), "Saved expansion material quantity") for code in requirements}
        stage = (level, capacity)
    for code, (_, needed) in requirements.items():
        counts[code] = _whole(counts[code], "Saved material quantity")
        if counts[code] > needed:
            raise ValueError("The saved material count exceeds this construction stage's requirement.")
    return initial, stage, requirements, counts


def _fill(save, obj, item, initial, stage, requirements, counts, selected, *, now):
    for code in selected:
        counts[code] = requirements[code][1]
    complete = all(counts[code] == needed for code, (_, needed) in requirements.items())
    response = {}
    if initial:
        rows, ledger = construction._contents(save, obj)
        for code in selected:
            if code not in rows:
                rows[code] = {"itemCode": code, "numItem": counts[code]}
                obj["contents"].append(rows[code])
            rows[code]["numItem"] = counts[code]
            ledger.setdefault(code, [0, [], []])[0] = counts[code]
        obj.update(isFullyBuilt=False, state="construction")
        if complete:
            for code in requirements:
                if code in rows:
                    rows[code]["numItem"] = 0
                ledger.pop(code, None)
            response = construction._finish_initial(save, obj, item, now=now)
    else:
        parts = obj["expansionParts"]
        for code in selected:
            parts[code] = counts[code]
        if complete:
            for code in requirements:
                parts.pop(code, None)
            response.update(construction._finish_expansion(save, obj, item, stage[0], stage[1]))
            if _bloom(item):
                witherers = _features(item, "WitherManager")
                if len(witherers) != 1 or witherers[0].get("prereq") != {
                        "contextBackend": "expansionLevel", "context": "expand.storageLevel",
                        "type": "compare", "value": "2"}:
                    raise ValueError("This flower's feeding clock is not restored.")
                # completeExpansionLevel45045 resets worldTime when its
                # level-2 prerequisite activates the WitherManager component.
                obj.update(plantTime=now * 1000, state="bare")
            if _bloom(item) and item.get("finishedName"):
                target = items.get_item_by_name(item["finishedName"])
                if not _bloom(target) or len(_features(target, "UpgradeManager")) != 1:
                    raise ValueError("The flower's authored fully fed replacement is unavailable.")
                # ExpandFManager.conditionallySwapOnFullyExpanded45054 and
                # FeatureBuilding.shouldCopyPlantTimeWhenReplacing22235.
                obj.update(itemName=target["name"], className=target["className"], state="bare",
                           expansionLevel=_catalog_whole(target.get("initialExpansionLevel"),
                                                         "Fully fed flower expansion level", 1),
                           contents=[])
                response["finishedName"] = target["name"]
    return response


def _complete(save, obj, item, options, *, with_currency=False, now):
    allowed = set() if with_currency else {"partName", "isGift", "currency"}
    if set(options) - allowed:
        raise ValueError("Unsupported building completion options.")
    if with_currency and not _bloom(item) and not construction._built(obj, item):
        raise ValueError("Paid expansion requires a completed saved building.")
    if not with_currency:
        if type(options.get("isGift", False)) is not bool:
            raise ValueError("The building completion gift flag must be Boolean.")
        if options.get("currency", "cash") != "cash":
            raise ValueError("Instant building completion requires the original cash currency.")
    initial, stage, requirements, counts = _stage(save, obj, item)
    part = options.get("partName")
    if part is not None and not isinstance(part, str):
        raise ValueError("The selected completion material name is invalid.")
    selected = [code for code, (material, needed) in requirements.items()
                if (part is None or material["name"] == part) and counts[code] < needed]
    if not selected:
        raise ValueError("There are no missing materials for this completion request.")
    if options.get("isGift", False):
        # Constructor44968 removes m_useGifts gifts for EVERY current part,
        # although its request includes only a Boolean and selected name. A
        # single-part flower stage proves the exact count from saved progress;
        # multi-part stages cannot identify that original count reliably.
        if not _bloom(item) or len(requirements) != 1 or part is None:
            raise ValueError("Combined gift completion is not restored: its material quantities are ambiguous.")
        code = selected[0]
        material, needed = requirements[code]
        quantity = needed - counts[code]
        if quantity <= 1 or "currency" in options:
            raise ValueError("Combined gift completion requires its original multi-gift request.")
        construction._source(save, obj, material, quantity, {"isGift": True})
        return _fill(save, obj, item, initial, stage, requirements, counts, selected, now=now)
    prices = {}
    for code in selected:
        material, needed = requirements[code]
        currency = material.get("market") if with_currency else "cash"
        if currency == "gold":
            currency = "coins"
        if not isinstance(currency, str) or not currency:
            raise ValueError("The construction material has no recovered purchase currency.")
        price = engine.catalog_price(material, "cash" if currency == "cash" else "cost")
        if price is None or price <= 0:
            raise ValueError("The construction material has no positive recovered purchase price.")
        prices[currency] = prices.get(currency, 0) + price * (needed - counts[code])
    _charge(save, prices)
    return _fill(save, obj, item, initial, stage, requirements, counts, selected, now=now)


def _upgrade(save, obj, item, options):
    if options:
        raise ValueError("Building upgrades do not accept client prices or replacement options.")
    upgrades = _features(item, "UpgradeManager")
    if not _bloom(item) or len(upgrades) != 1:
        raise ValueError("This building does not have a restored flower upgrade.")
    upgrade = upgrades[0]
    if set(upgrade) != {"name", "className", "upgradeItem", "upgradeCost"}:
        raise ValueError("This building upgrade has unsupported requirements.")
    expansions = _features(item, "ExpandFManager")
    if len(expansions) != 1:
        raise ValueError("The flower's original expansion component is missing or ambiguous.")
    levels = [_catalog_whole(row.get("level"), "Flower expansion level", 1)
              for row in _list(expansions[0].get("upgrade")) if isinstance(row, dict)]
    initial = _catalog_whole(item.get("initialExpansionLevel", "1"), "Initial flower expansion level", 1)
    if not levels or _whole(obj.get("expansionLevel", initial), "Saved flower expansion level", 1) < max(levels):
        raise ValueError("Feed this flower completely before upgrading it.")
    if obj.get("isFullyBuilt") is False or obj.get("state") in ("construction", "constructing"):
        raise ValueError("Complete this flower before upgrading it.")
    target = items.get_item_by_name(upgrade.get("upgradeItem"))
    if not _bloom(target) or target.get("subtype") != "fullbloom":
        raise ValueError("The authored flower upgrade target is unavailable.")
    cost = _catalog_whole(upgrade.get("upgradeCost"), "Flower upgrade cash price", 1)
    _charge(save, {"cash": cost})
    obj.update(itemName=target["name"], className=target["className"], state="bare")
    return {}


def start_session(save):
    """Flash sequences restart at login; server-restart retries remain durable."""
    save.pop(REQUESTS_KEY, None)
    save.pop(RESPONSE_KEY, None)
    save.pop(ORCHARD_REQUESTS_KEY, None)
    construction.start_session(save)


def harvest_orchard(save, stored, *, now, request_id=None):
    """Original deterministic base coins, without unrecovered random bonuses.

    HarvestFManager45345 sums quantity times each contained tree's coinYield.
    Return None for another item, 1 for a new harvest, 0 for a durable retry.
    """
    item = items.get_item_by_name(stored.get("itemName"))
    if not storage.orchard_container_class(item):
        return None
    detached = copy.deepcopy(save)
    obj, item = _owned(detached, "harvest", stored)
    storage._feature_owner(detached, obj["id"], stored)
    storage.orchard_capacity(obj, item)
    now = _whole(now, "Orchard harvest time", 1)
    history = detached.get(ORCHARD_REQUESTS_KEY, {})
    if not isinstance(history, dict):
        raise ValueError("The saved Orchard harvest receipts are malformed.")
    key = str(_whole(request_id, "Orchard harvest sequence")) if request_id is not None else None
    identity = {"id": obj["id"], "itemName": item["name"], "plantTime": obj.get("plantTime"),
                "world": world_travel.guard_active_world(detached)}
    if key is not None and key in history:
        if history[key] != identity:
            raise ValueError("An Orchard harvest sequence was reused for another action.")
        return 0
    import peaceful
    grow = peaceful.grow_seconds(item)
    planted = obj.get("plantTime")
    if (type(planted) not in (int, float) or not math.isfinite(planted) or planted < 0
            or grow is None or now - planted / 1000 < grow - 1):
        raise ValueError("This Orchard has not finished growing.")
    contents = obj.get("contents", [])
    if not isinstance(contents, list):
        raise ValueError("The saved Orchard contents must be an array.")
    counts = {}
    for row in contents:
        if not isinstance(row, dict) or not isinstance(row.get("itemCode"), str) or row["itemCode"] in counts:
            raise ValueError("The saved Orchard contents are ambiguous.")
        counts[row["itemCode"]] = _whole(row.get("numItem"), "Stored tree quantity")
    data = detached["userInfo"]["player"].get("storageData", {})
    if not isinstance(data, dict):
        raise ValueError("The saved Orchard inventory is invalid.")
    ledger = data.get(str(obj["id"]))
    if ledger is not None:
        if not isinstance(ledger, dict):
            raise ValueError("The saved Orchard ledger is invalid.")
        ledger_counts = {code: construction._entry(entry)[0] for code, entry in ledger.items()}
        if ledger_counts != counts:
            raise ValueError("The saved Orchard ledger disagrees with its contents.")
    rows, _ = construction._contents(detached, obj)
    coins, count = 0, 0
    for code, row in rows.items():
        quantity = row["numItem"]
        if not quantity:
            continue
        tree = items.get_item_by_code(code)
        if not storage.orchard_accepts(tree):
            raise ValueError("Remove incompatible imported contents before harvesting this Orchard.")
        coins = _whole(coins + quantity * _catalog_whole(tree.get("coinYield", "0"), "Tree harvest coin yield"),
                       "Orchard base coin reward")
        count += quantity
    if not count:
        raise ValueError("Store a tree before harvesting this Orchard.")
    _balance(detached["userInfo"]["player"].get("gold"), "coin")
    if key is not None and len(history) >= 2048:
        raise ValueError("Reload the farm before recording more Orchard harvests.")
    engine.apply_coins_diff(detached, coins)
    obj.update(state="bare", plantTime=now * 1000)
    if key is not None:
        history[key] = {**identity, "plantTime": now * 1000}
        detached[ORCHARD_REQUESTS_KEY] = history
    save.clear(); save.update(detached)
    return 1


def take_response(save):
    return save.pop(RESPONSE_KEY, {})


def perform(save, action, snapshot, params, *, request_id=None, now=None):
    """Atomically apply an original paid world action and cache its callback."""
    if action not in ACTIONS and action != "TransformBuilding":
        raise ValueError("This paid building action is not restored.")
    options = _options(params)
    if action == "TransformBuilding" and options:
        raise ValueError("Classic paid transformation does not accept completion options.")
    def encode(value):
        if isinstance(value, pyamf.UndefinedType):
            return None
        raise ValueError("Unsupported paid building request value.")
    signature = json.dumps([save.get("userInfo", {}).get("currentWorldType") or "farm",
                            action, snapshot, options], sort_keys=True, default=encode)
    key = str(_whole(request_id, "Paid building request sequence")) if request_id is not None else None
    state = save.get(REQUESTS_KEY, {})
    if not isinstance(state, dict) or not isinstance(state.get("receipts", {}), dict):
        raise ValueError("The saved paid building retry history is invalid.")
    receipt = state.get("receipts", {}).get(key)
    if key is not None and receipt is not None:
        if not isinstance(receipt, dict) or not isinstance(receipt.get("response"), dict):
            raise ValueError("The saved paid building receipt is invalid.")
        if receipt.get("signature") != signature:
            raise ValueError("A paid building sequence was reused for a different request.")
        save[RESPONSE_KEY] = copy.deepcopy(receipt["response"])
        return copy.deepcopy(receipt["response"])
    highest = _whole(state.get("highestSequence", -1), "Saved paid building request sequence", -1)
    if key is not None and int(key) <= highest:
        raise ValueError("This paid building request is older than the retained retry history.")
    detached = copy.deepcopy(save)
    obj, item = _owned(detached, action, snapshot)
    if action == "TransformBuilding" and item["name"] not in _CLASSIC_TRANSFORMS:
        raise ValueError("This building does not use the recovered classic paid completion.")
    if action == "upgradeBuilding":
        response = _upgrade(detached, obj, item, options)
    elif action in ("CompleteNow", "ExpandWithCurrency", "TransformBuilding"):
        response = _complete(detached, obj, item, options, with_currency=action == "ExpandWithCurrency",
                             now=_whole(engine.timestamp_now() if now is None else now, "Building action time", 1))
    else:
        import building_harvest
        if options:
            raise ValueError("Instant building harvest does not accept client prices or reward options.")
        if not building_harvest.manages(item):
            raise ValueError("Instant harvest is not restored for this building's harvest rewards; no cash was charged.")
        price = building_harvest.ready_now(detached, obj,
                                          now=engine.timestamp_now() if now is None else now)
        _charge(detached, {"cash": price})
        response = {}
    response = {"id": obj["id"], **response}
    detached[RESPONSE_KEY] = copy.deepcopy(response)
    if key is not None:
        state = detached.setdefault(REQUESTS_KEY, {})
        receipts = state.setdefault("receipts", {})
        receipts[key] = {"signature": signature, "response": copy.deepcopy(response)}
        state["highestSequence"] = int(key)
        while len(receipts) > 256:
            del receipts[next(iter(receipts))]
    save.clear(); save.update(detached)
    return response
