"""Durable My Deco Studio state, recovered from the shipped AS3 client.

TCreateUGCDecoration expects the result fields directly, not a nested result.
UGCItemState/UGCItemLayerState use U/I/N/D/C compact keys. Prices and valid
parts come from the archived catalog; no client-supplied price is trusted.
"""
import copy
from functools import lru_cache
from pathlib import Path
import random
import uuid
import xml.etree.ElementTree as ET
import zlib

import engine
import game_settings
import items
import storage


def _rows(value):
    return value if isinstance(value, list) else [value] if isinstance(value, dict) else []


@lru_cache(maxsize=1)
def _config():
    root = ET.fromstring(zlib.decompress(Path(game_settings.CONFIG_CMS_XML).read_bytes()))
    feature = root.find("./featureConfig/feature[@name='UGCDeco']")
    if feature is None:
        raise ValueError("The Deco Studio configuration is unavailable.")
    materials = {entry.get('name'): int(entry.get('max'))
                 for entry in feature.findall('./materials/material')}
    blueprints = {entry.get('name') for entry in feature.findall('./blueprints/layer/items/item')}
    prerequisites = {entry.get('name'): entry.get('value')
                     for entry in root.iter('prereq')
                     if entry.get('type') == 'ugc_deco_completed'}
    return materials, blueprints, prerequisites


@lru_cache(maxsize=1)
def _recycle_config():
    root = ET.fromstring(zlib.decompress(Path(game_settings.CONFIG_CMS_XML).read_bytes()))
    feature = root.find("./featureConfig/feature[@name='UGCDeco']")
    weights = {entry.get('name'): [(loot.get('itemName'), int(loot.get('quantity')), int(loot.get('weight')))
                                  for loot in entry.findall('lootItem')]
               for entry in feature.findall('./dropTables/weights/weightTable')}
    tables = {entry.get('name'): [loot.get('name') for loot in entry.findall('lootTable')]
              for entry in feature.findall('./dropTables/dropTable')}
    blacklist = {entry.text for entry in feature.findall('./blacklistedItems/item')}
    return weights, tables, blacklist


def _integer(value, minimum=0, maximum=2**31 - 1):
    if isinstance(value, bool):
        raise ValueError("A whole number is required.")
    try:
        number = int(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError("A whole number is required.") from None
    if str(number) != str(value) and number != value:
        raise ValueError("A whole number is required.")
    if not minimum <= number <= maximum:
        raise ValueError("The number is out of range.")
    return number


def feature_data(save):
    """Return a detached, client-compatible snapshot without mutating a save."""
    data = copy.deepcopy(save['userInfo'].get('featureOptions', {}).get('UGCDeco', {}).get('UGCDeco') or {})
    if not isinstance(data, dict):
        raise ValueError("The Deco Studio material ledger is invalid.")
    data.setdefault('ugc_materials', {})
    data.setdefault('ugc_completed', {})
    if not isinstance(data['ugc_materials'], dict):
        raise ValueError("The Deco Studio material ledger is invalid.")
    # The original empty completed collection could be encoded as an array.
    if data['ugc_completed'] == []:
        data['ugc_completed'] = {}
    if not isinstance(data['ugc_completed'], dict):
        raise ValueError("The Deco Studio blueprint ledger is invalid.")
    return data


def _set_feature_data(save, data):
    save['userInfo'].setdefault('featureOptions', {}).setdefault('UGCDeco', {})['UGCDeco'] = data


def _state_map(save):
    states = save['userInfo'].get('ugcItemData')
    if states is None:
        states = {}
        save['userInfo']['ugcItemData'] = states
    if not isinstance(states, dict):
        raise ValueError("The custom decoration ledger is invalid.")
    return states


def _validate_state(raw):
    if not isinstance(raw, dict) or not isinstance(raw.get('I'), str):
        raise ValueError("The Deco Studio design is invalid.")
    base = items.get_item_by_code(raw['I'])
    if not base or base['name'] not in _config()[1] or base.get('className') != 'UGCDecoration':
        raise ValueError("The Deco Studio blueprint is unknown.")
    definition = next((entry for entry in _rows(game_settings.get_game_settings().get('ugcItems', {}).get('ugcItem'))
                       if entry.get('@itemName') == base['name']), None)
    if definition is None:
        raise ValueError("The Deco Studio blueprint definition is missing.")
    layer_defs = {entry['@layerKey']: entry for entry in
                  [definition['base']] + _rows(definition.get('layers', {}).get('layer'))}
    state = {'I': base['code']}
    if raw.get('N') is not None:
        if not isinstance(raw['N'], str) or len(raw['N'].encode('utf-16-le')) // 2 > 32:
            raise ValueError("The design name must be at most 32 characters.")
        if raw['N']:
            state['N'] = raw['N']
    layers = raw.get('D') or {}
    if not isinstance(layers, dict):
        raise ValueError("The Deco Studio layers are invalid.")
    chosen = []
    normalized = {}
    for key, layer in layers.items():
        rule = layer_defs.get(key)
        if rule is None or not isinstance(layer, dict):
            raise ValueError("The design contains an unknown layer.")
        allowed = {entry['@name'] for entry in _rows(rule.get('items', {}).get('item'))}
        entry = {}
        code = layer.get('I')
        if code:
            part = items.get_item_by_code(code) if isinstance(code, str) else None
            if not part or part['name'] not in allowed:
                raise ValueError("The selected part does not belong to this blueprint layer.")
            entry['I'] = part['code']
            chosen.append(part)
        elif allowed:
            raise ValueError("The design layer is missing its selected part.")
        if 'C' in layer:
            if rule.get('@colorize') != 'true':
                raise ValueError("This design layer cannot be painted.")
            entry['C'] = str(_integer(layer['C'], 0, 0xFFFFFF))
        normalized[key] = entry
    if normalized:
        state['D'] = normalized
    return state, base, chosen


def validate_owned_state(save, state_uuid, item_name):
    """Validate ownership and base item; return the persisted state read-only."""
    if not isinstance(state_uuid, str):
        raise ValueError("The custom decoration identity is invalid.")
    try:
        parsed = uuid.UUID(state_uuid)
    except (ValueError, AttributeError):
        raise ValueError("The custom decoration identity is invalid.") from None
    if parsed.version != 4 or str(parsed) != state_uuid:
        raise ValueError("The custom decoration identity is invalid.")
    state = (save['userInfo'].get('ugcItemData') or {}).get(state_uuid)
    item = items.get_item_by_name(item_name)
    if not isinstance(state, dict) or not item or state.get('U') != state_uuid or state.get('I') != item['code']:
        raise ValueError("This custom decoration does not belong to this farm and item.")
    return state


def _check_unlocked(data, item):
    prerequisite = _config()[2].get(item.get('purchasePrereqs'))
    if prerequisite and prerequisite not in data['ugc_completed']:
        raise ValueError("Build the preceding Deco Studio blueprint first.")


def _response(save, state, data, xp=0):
    # Deep copies prevent AMF reference aliases between saved state and envelopes.
    return {'ugcItemState': copy.deepcopy(state), 'xpGain': xp,
            'storageData': copy.deepcopy(save['userInfo']['player']['storageData']),
            'featureData': copy.deepcopy(data)}


def purchase_decoration(save, raw, modify_id=0):
    state, item, chosen = _validate_state(raw)
    data = feature_data(save)
    _check_unlocked(data, item)
    modify_id = _integer(modify_id)
    if modify_id:
        # The archived Deco callback always enters gift placement, unlike
        # TCreateUGCItem's customization path. Accepting modification would
        # update the old object then strand a second placement without a gift.
        raise ValueError("Editing a placed Deco Studio decoration is not supported by this client.")
    elif raw.get('U'):
        raise ValueError("A new decoration cannot reuse an existing identity.")

    # The original transaction has no purchase token. Keep the single pending
    # identical gift as the receipt until it is placed, preventing a network
    # retry from charging and granting twice. A second build after placement is
    # a separate purchase and gets a fresh UUID.
    if not modify_id:
        gift = save['userInfo']['player']['storageData'].get(str(storage.GIFTBOX_ID), {}).get(item['code'])
        for pending in gift[2] if gift else []:
            candidate = (save['userInfo'].get('ugcItemData') or {}).get(pending)
            if isinstance(candidate, dict) and {k: v for k, v in candidate.items() if k != 'U'} == state:
                return _response(save, candidate, data)

    price = {}
    for component in [item] + chosen:
        for material in _rows((component.get('materialPrice') or {}).get('material')):
            name, quantity = material['name'], _integer(material['quantity'], 1)
            if name not in _config()[0]:
                raise ValueError("The blueprint has an unsupported material.")
            price[name] = price.get(name, 0) + quantity
    if not price:
        raise ValueError("The blueprint has no recoverable material price.")
    for name, quantity in price.items():
        available = _integer(data['ugc_materials'].get(name, 0))
        if available < quantity:
            raise ValueError("There are not enough Deco Studio materials to build this design.")
        data['ugc_materials'][name] = available - quantity
    data['ugc_completed'][item['name']] = True
    state['U'] = str(uuid.uuid4())
    xp = _integer(item.get('buyXp') or 0)
    states = _state_map(save)
    states.pop(item['code'], None)
    states[state['U']] = state
    storage.store_deposit_item_by_name(save, item['name'], group=storage.GIFTBOX_ID)
    save['userInfo']['player']['storageData'][str(storage.GIFTBOX_ID)][item['code']][2].append(state['U'])
    _set_feature_data(save, data)
    engine.apply_xp_increment(save, xp)
    return _response(save, state, data, xp)


def purchase_part(save, name, quantity=1):
    caps = _config()[0]
    if name not in caps:
        raise ValueError("The Deco Studio material is unknown.")
    quantity = _integer(quantity, 1, caps[name])
    data = feature_data(save)
    amount = _integer(data['ugc_materials'].get(name, 0))
    if amount + quantity > caps[name]:
        raise ValueError("The Deco Studio material capacity would be exceeded.")
    item = items.get_item_by_name(name)
    cost = _integer(item.get('cash'), 1) * quantity
    if _integer(save['userInfo']['player'].get('cash', 0)) < cost:
        raise ValueError("There is not enough Farm Cash to buy this material.")
    engine.apply_cash_diff(save, -cost)
    data['ugc_materials'][name] = amount + quantity
    _set_feature_data(save, data)
    # The original purchase callback ignores the body; keep a useful snapshot.
    return {'featureData': copy.deepcopy(data)}


def save_temp_state(save, raw):
    state, item, _ = _validate_state(raw)
    if raw.get('U'):
        raise ValueError("A temporary design cannot overwrite a completed decoration.")
    _check_unlocked(feature_data(save), item)
    _state_map(save)[item['code']] = state


def set_last_blueprint(save, feature, name):
    if feature != 'UGCDeco' or name not in _config()[1]:
        raise ValueError("The Deco Studio blueprint is unknown.")
    data = feature_data(save)
    _check_unlocked(data, items.get_item_by_name(name))
    last = data.get('ugc_lastEdited') or {}
    if isinstance(last, str):
        last = {'UGCDeco': last}
    if not isinstance(last, dict):
        raise ValueError("The last blueprint state is invalid.")
    last[feature] = name
    data['ugc_lastEdited'] = last
    _set_feature_data(save, data)


def award_recycling(save, item):
    """Award the recovered salvage drops after one existing object is removed.

    GMSalvage uses the ordinary sell/clear actions, with no special request
    flag. TSell.onComplete consumes result.ugcdeco. The caller owns removal
    and must not call this when the source object has already disappeared.
    """
    kind = item.get('type') if isinstance(item, dict) else None
    if kind not in ('tree', 'building', 'decoration'):
        return None
    weights, tables, blacklist = _recycle_config()
    if item['name'] in blacklist or item.get('clearable') == 'false':
        return None
    cash = engine.catalog_price(item, 'cash') or 0
    coins = engine.catalog_price(item, 'cost') or 0
    # UGCDecoManager.m_minCoinCost's shipped slot default is 500. The current
    # local host does not override UGC_DECO_RECYCLE_MINCOIN in flashHotParams.
    if item.get('market') in ('cash', 'premium') and cash > 0:
        table = kind + '_premium'
    elif coins >= 500:
        table = kind
    elif cash > 0:
        table = kind + '_premium'
    else:
        return None
    data = feature_data(save)
    caps = _config()[0]
    for table_name in tables[table]:
        pool = weights[table_name]
        name, quantity, _ = random.choices(pool, weights=[entry[2] for entry in pool], k=1)[0]
        amount = _integer(data['ugc_materials'].get(name, 0))
        data['ugc_materials'][name] = min(caps[name], amount + quantity)
    _set_feature_data(save, data)
    return copy.deepcopy(data)
