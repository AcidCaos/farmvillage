"""Original TSellStoredItem ordinary-inventory sale; no gift/container guesses.

The signed sender supplies {code}, sellAll, origin.toString(), quantity.
StorageSlot.onSellComplete needs qtySold; TSellStoredItem.onComplete applies
sellAmounts as currency deltas. StorageItem.adjustQuantity trims oldest unit
metadata only when its length exceeds the remaining quantity.
"""
import copy
import math

import engine
import items
import meadows_storage
import storage
import world_travel

METHOD = 'UserService.sellStoredItem'


def _arguments(params):
    if isinstance(params, dict):
        result = {}
        for key, value in params.items():
            if type(key) is int and key in range(4):
                index = key
            elif type(key) is str and key in ('0', '1', '2', '3'):
                index = int(key)
            else:
                raise ValueError('Stored sale needs four original positional arguments.')
            if index in result:
                raise ValueError('Stored sale arguments have duplicate positional indices.')
            result[index] = value
        if set(result) != set(range(4)):
            raise ValueError('Stored sale needs four original positional arguments.')
        params = [result[index] for index in range(4)]
    if not isinstance(params, (list, tuple)) or len(params) != 4:
        raise ValueError('Stored sale needs four original positional arguments.')
    data, sell_all, origin, quantity = params
    if (not isinstance(data, dict) or set(data) != {'code'}
            or not isinstance(data['code'], str) or not data['code']
            or len(data['code']) > 128):
        raise ValueError('Stored sale needs its original item code only.')
    # Expanded building and UGC keys need separate price/recycling contracts.
    # There is no metadata-index argument in this original transaction.
    if ':' in data['code']:
        raise ValueError('Selling expanded or custom inventory keys is not restored.')
    if sell_all is not False:
        raise ValueError('Sell-all and Gift Box sales are not restored by this ordinary sale.')
    if not isinstance(origin, str):
        raise ValueError('Stored sale requires the original inventory ID string.')
    group = storage._storage_group(origin)
    if str(group) != origin:
        raise ValueError('Stored sale inventory ID must be canonical.')
    quantity = storage.positive_quantity(quantity)
    if quantity > 2_147_483_647:
        raise ValueError('Stored sale quantity is too large.')
    return data['code'], group, quantity


def sell(save, params, *, request_id):
    """Commit a receipt and the complete sale together, or change nothing."""
    code, group, quantity = _arguments(params)
    if (not isinstance(request_id, tuple) or len(request_id) != 2
            or not isinstance(request_id[0], str) or not request_id[0]):
        raise ValueError('Stored sale requires its signed session sequence.')
    signature = meadows_storage._signature([code, False, group, quantity])
    key, old = meadows_storage._receipt(save, 'inventorySale', request_id, signature)
    if old is not None:
        return old
    working = copy.deepcopy(save)
    world = world_travel.guard_active_world(working)
    active = storage.active_inventory_id(working)
    # No special contents, Gift Box, inactive farm or shipping side effect.
    if (group >= 0 or group != active
            or group in (storage.GIFTBOX_ID, storage.CONSUME_ID)
            or working['userInfo']['worldSummaryData'].get(world, {}).get('storageId') != group):
        raise ValueError('Sell from the current owned farm ordinary inventory only.')
    item = items.get_item_by_code(code)
    classes = {None, 'Animal', 'Tree', 'Building', 'Decoration',
               'RotateableDecoration', 'MaskedDecoration', 'GateDecoration', 'StorageBuilding'}
    if (not item or item.get('type') not in {'animal', 'tree', 'building', 'decoration'}
            or item.get('className') not in classes):
        raise ValueError('This special inventory item sale is not restored.')
    if item.get('sellable') in (False, 'false') or item.get('disallowDelete') in (True, '1', 'true'):
        raise ValueError('This item cannot be sold.')
    # FarmItem.sellCurrency uses coins for ordinary coin/cash markets. World
    # currencies have their own tuning/ledger and must not become coin grants.
    if item.get('market') not in (None, '', 'coins', 'cash'):
        raise ValueError('World-currency inventory sales are not restored.')
    player = working['userInfo']['player']
    ledgers = player.get('storageData')
    ledger = ledgers.get(str(group)) if isinstance(ledgers, dict) else None
    entry = ledger.get(code) if isinstance(ledger, dict) else None
    if (not isinstance(entry, list) or len(entry) != 3
            or not isinstance(entry[1], list) or not isinstance(entry[2], list)):
        raise ValueError('The saved inventory sale metadata is unavailable or malformed.')
    owned = storage.positive_quantity(entry[0])
    if quantity > owned or len(entry[2]) > owned:
        raise ValueError('The saved inventory quantity or unit metadata is inconsistent.')
    balance = player.get('gold')
    if (type(balance) not in (int, float) or not math.isfinite(balance)
            or balance < 0 or int(balance) != balance):
        raise ValueError('The saved coin balance is invalid.')
    price = engine.item_sell_price(item)
    amount = price * quantity
    if amount > 9_007_199_254_740_991 or balance + amount > 9_007_199_254_740_991:
        raise ValueError('The inventory sale exceeds exact currency accounting.')
    # Player.removeInventoryItem uses adjustQuantity(true), with no Gift Box
    # shiftSenderId call. Reuse its exact trim rule without the generic gift
    # withdrawal helper's extra sender mutation.
    storage._adjust_quantity(entry, -quantity)
    if entry[0] == 0:
        del ledger[code]
    engine.apply_coins_diff(working, amount)
    response = {'sellable': True, 'qtySold': quantity, 'sellAmounts': {'coins': amount}}
    meadows_storage._record(working, key, signature, response)
    save.clear()
    save.update(working)
    return response
