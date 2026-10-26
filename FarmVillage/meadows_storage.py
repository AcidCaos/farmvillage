"""Recovered Meadows storage contracts; no synthetic licenses or cellar credits.

FarmGame methods 12220, 2735, 32313, 11935 and the original item/CMS
archives define these bounded paths. Social upgrade campaigns and shovel
interval rewards remain outside this module's admission.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zlib
import uuid

from bundle import XML_DIR, TEMPLATES_DIR

WORLD = 'meadows'
PACKAGE = 'pkg_meadowsXfer'
CONSUMABLE = 'consume_meadowsXfer'
STATE = '_meadowsStorage'
_ROOTS = ('toolshed', 'toolshedpink', 'barn', 'barnwhite', 'barnblack', 'barnblue', 'barnpink')


def _whole(value, label='Storage quantity'):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0 or int(value) != value:
        raise ValueError(label + ' must be a nonnegative whole number.')
    return int(value)


def _xml(name):
    return ET.fromstring(zlib.decompress(Path(XML_DIR, 'gz/v855098', name).read_bytes()))


def _experiment(name):
    text = Path(TEMPLATES_DIR, 'play.html').read_text()
    values = re.findall(r'"' + re.escape(name) + r'":\s*(-?\d+)', text)
    return len(values) == 1 and int(values[0]) == 1


def has_license(save, world):
    licenses = save['userInfo'].get('unlockedWorldContentLicenses', {})
    # Only an actual saved Boolean grant is authoritative. Strings/numbers from
    # malformed imports cannot authorize movement of inventory.
    return (isinstance(licenses, dict) and isinstance(licenses.get(world), dict)
            and licenses[world].get('world') is True)


def guard_shipping(save, group, item=None):
    """Original StorageWindow.isUseable requires both endpoint licenses."""
    import storage
    import world_travel
    active = world_travel.guard_active_world(save)
    source = {storage.HOME_INVENTORY_ID: 'farm', storage.MEADOWS_INVENTORY_ID: WORLD}.get(group)
    if source is None or {source, active} != {'farm', WORLD}:
        raise ValueError('Only licensed Home and Sunflower Meadows inventory shipping is restored.')
    state = save.get(world_travel.STATE_KEY, {})
    if (source not in state.get('inactive', {})
            or save['userInfo'].get('worldSummaryData', {}).get(source, {}).get('storageId') != group):
        raise ValueError('Shipping requires the original owned source world and inventory.')
    if not has_license(save, source) or not has_license(save, active):
        raise ValueError('Shipping requires saved shipping licenses for both farms.')
    if item is not None:
        allowed = {None, 'Animal', 'Tree', 'Building', 'Decoration', 'RotateableDecoration',
                   'MaskedDecoration', 'GateDecoration', 'StorageBuilding'}
        if item.get('type') not in {'animal', 'tree', 'building', 'decoration'} or item.get('className') not in allowed:
            raise ValueError('This special item is not supported by Meadows shipping.')
        import creative_worlds
        if not creative_worlds.world_requirement_matches(item, active):
            raise ValueError('The shipped item cannot be used on the destination farm.')
        creative_worlds._guard_land_terrain(item)


def _license_contract():
    from items import get_item_by_name
    package, consumable = get_item_by_name(PACKAGE), get_item_by_name(CONSUMABLE)
    if (not package or any(package.get(k) != v for k, v in {
            'code': 'brp', 'cash': '250', 'type': 'change_farm', 'subtype': 'consumable',
            'buyable': 'true', 'market': 'cash', 'experimentGate': 'fv_sunflowermeadow_purchase_shipping',
            'marketPrereqs': 'meadowsXfer_visible',
            'itemPackage': {'amount': '1', 'value': CONSUMABLE}}.items())
            or not consumable or any(consumable.get(k) != v for k, v in {
            'code': 'bpT', 'className': 'CRewardConsumable', 'useOnBuy': 'true',
            'rewards': {'reward': {'type': 'world_content_license', 'licenseType': 'world', 'value': WORLD}}}.items())):
        raise ValueError('The recovered Meadows shipping license contract is unavailable.')
    node = _xml('gameSettingsCMS.xml.gz').find(".//prereq[@name='meadowsXfer_visible']")
    expected = [{'type': 'no_world_license', 'value': WORLD, 'licenseType': 'world'},
                {'type': 'experiment', 'value': 'fv_sunflowermeadow_purchase_shipping', 'variant': '1'},
                {'type': 'has_unlocked_world', 'value': WORLD}]
    expansion = _xml('gameSettings.xml.gz').find("expansions/expansion[@name='meadows']")
    if (node is None or node.get('type') != 'AND' or [dict(e.attrib) for e in node] != expected
            or expansion is None or expansion.findtext('shippingLicenseItemName') != PACKAGE):
        raise ValueError('The recovered Meadows shipping prerequisite is unavailable.')
    return package


def _request_state(save):
    state = save.get(STATE, {})
    if (not isinstance(state, dict) or not isinstance(state.get('receipts', {}), dict)
            or not isinstance(state.get('highestSequences', {}), dict)
            or ('sessionID' in state and (not isinstance(state['sessionID'], str)
                                         or not state['sessionID']))):
        raise ValueError('The saved Meadows storage receipts are malformed.')
    return state


def start_session(save):
    """Issue the original sequenceId while retaining prior-session receipts.

    TransactionManager carries sequenceID separately from its numeric counter.
    The new client starts numeric sequencing again; cached older requests still
    identify their original namespace and cannot withdraw or charge twice.
    """
    state = _request_state(save)
    token = str(uuid.uuid4())
    state = {**state, 'sessionID': token, 'highestSequences': {}}
    state.setdefault('receipts', {})
    save[STATE] = state
    return token


def _receipt(save, category, request_id, signature):
    if request_id is None:
        return None, None
    client_id = None
    sequence = request_id
    if isinstance(request_id, tuple):
        if len(request_id) != 2:
            raise ValueError('A Meadows request needs its original sequenceID and sequence.')
        client_id, sequence = request_id
        if client_id is not None and (not isinstance(client_id, str) or not client_id or len(client_id) > 128):
            raise ValueError('The Meadows request sequenceID is invalid.')
    sequence = _whole(sequence, 'Request sequence')
    key = ((client_id + ':') if client_id is not None else '') + category + ':' + str(sequence)
    state = _request_state(save)
    old = state.get('receipts', {}).get(key)
    if old is not None:
        if (not isinstance(old, dict) or old.get('signature') != signature
                or 'response' not in old):
            raise ValueError('A Meadows storage sequence was reused for another request.')
        return key, copy.deepcopy(old['response'])
    current_id = state.get('sessionID')
    if client_id != current_id:
        raise ValueError('This Meadows storage sequenceID is stale or unknown.')
    # A numeric-only legacy request is accepted only before the first original
    # initUser establishes a sequenceID. Cached legacy receipts above remain
    # safe acknowledgements, but missing-ID new mutations never gain access.
    if current_id is not None and client_id is None:
        raise ValueError('This Meadows storage request is missing its sequenceID.')
    highest = state.get('highestSequences', {}).get(category, -1)
    if highest != -1:
        highest = _whole(highest, 'Highest retained Meadows sequence')
    if sequence <= highest:
        raise ValueError('This Meadows storage request is older than the retained retry history.')
    return key, None


def _record(save, key, signature, response):
    if key is None:
        return
    state = save.setdefault(STATE, {})
    ledger = state.setdefault('receipts', {})
    category, sequence = key.rsplit(':', 2)[-2:]
    state.setdefault('highestSequences', {})[category] = int(sequence)
    ledger[key] = {'signature': signature, 'response': copy.deepcopy(response)}
    while len(ledger) > 256:
        del ledger[next(iter(ledger))]


def _signature(value):
    import pyamf
    def encode(obj):
        if isinstance(obj, pyamf.UndefinedType):
            return None
        raise ValueError('Unsupported Meadows request metadata.')
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False, default=encode).encode()).hexdigest()


def buy_license_package(save, package_name, *, request_id=None):
    if package_name != PACKAGE:
        # Meadows' restored shipping tab can show other owned worlds. Their
        # packages must not fall through to generic charging without a grant.
        import world_travel
        if world_travel.guard_active_world(save) == WORLD:
            names = {node.findtext('shippingLicenseItemName') for node in
                     _xml('gameSettings.xml.gz').findall('expansions/expansion')}
            if isinstance(package_name, str) and package_name in names:
                raise ValueError('This other world shipping license is not restored on Sunflower Meadows.')
        return None
    working = copy.deepcopy(save)
    result = _buy_license_package(working, package_name, request_id=request_id)
    save.clear(); save.update(working)
    return result


def _buy_license_package(save, package_name, *, request_id=None):
    if package_name != PACKAGE:
        return None
    import storage
    import world_travel
    world_travel.guard_active_world(save)
    package = _license_contract()
    sig = _signature([package_name])
    key, old = _receipt(save, 'license', request_id, sig)
    if old is not None:
        return old
    if has_license(save, WORLD):
        return {}  # Durable owned entitlement; no repeat purchase/charge.
    if not _experiment('fv_sunflowermeadow_purchase_shipping'):
        raise ValueError('The Meadows shipping experiment is not enabled.')
    state = save.get(world_travel.STATE_KEY, {})
    if WORLD not in ({world_travel.guard_active_world(save)} | set(state.get('inactive', {}))):
        raise ValueError('Purchase Sunflower Meadows before its shipping license.')
    balance = save['userInfo']['player']['cash']
    if type(balance) not in (int, float) or not math.isfinite(balance) or balance < int(package['cash']):
        raise ValueError('The Meadows shipping license requires 250 Farm Cash.')
    # TBuyConsumables.perform calls useOnBuy -> CRewardConsumable.onUse.
    # That override grants UserRewardUtil rewards directly, with no second
    # transaction and no Gift Box item. Persist the same atomic entitlement.
    from world_scores import add_content_license
    add_content_license(save, WORLD, 'world')
    save['userInfo']['player']['cash'] -= int(package['cash'])
    _record(save, key, sig, {})
    return {}


def consume_license(save, item_name, count, group):
    if item_name != CONSUMABLE:
        return False
    working = copy.deepcopy(save)
    result = _consume_license(working, item_name, count, group)
    save.clear(); save.update(working)
    return result


def _consume_license(save, item_name, count, group):
    import storage
    import world_scores
    _license_contract()
    if count != 1 or isinstance(count, bool) or group != storage.GIFTBOX_ID:
        raise ValueError('Use one owned Meadows shipping license from the Gift Box.')
    if has_license(save, WORLD):
        return True
    licenses = save['userInfo'].get('unlockedWorldContentLicenses', {})
    if not isinstance(licenses, dict) or not isinstance(licenses.get(WORLD, {}), dict):
        raise ValueError('The imported world-content licenses are malformed.')
    entry = save['userInfo']['player']['storageData'].get(str(group), {}).get('bpT')
    if not entry or storage.positive_quantity(entry[0]) < count:
        raise ValueError('The Meadows shipping license is not in the Gift Box.')
    storage.store_withdraw_item_by_name(save, item_name, count, group)
    world_scores.add_content_license(save, WORLD, 'world')
    return True


def cellar_capacity(save, obj, item):
    """Read exact imported credit authority, without inventing shovel rewards."""
    if (save['userInfo'].get('currentWorldType') != WORLD or item.get('name') != 'hatchstorage'
            or obj.get('className') != 'InventoryCellar' or obj.get('state') not in ('built_0', 'built_1', 'built_2', 'built')):
        return None
    import cove_rules
    cove_rules.allows_cellar_market_prerequisite(item, WORLD)
    # InventoryCellar has neither globalStorage nor ignoreGlobalReceived: the
    # client's getTotalCreditsReceived uses the active world's `received`.
    credits = save['userInfo']['player'].get('featureCredits') or {}
    if not isinstance(credits, dict) or not isinstance(credits.get(WORLD, {}), dict):
        raise ValueError('The imported cellar credits are invalid.')
    row = credits.get(WORLD, {}).get('InventoryCellar', {})
    if not isinstance(row, dict):
        raise ValueError('The imported cellar credits are invalid.')
    return min(int(item['capacity']), _whole(row.get('received', 0), 'Cellar credits'))


def purchase_storage_upgrade(save, snapshot, params, *, request_id=None):
    """TUpgradeStorage(TYPE_PURCHASE), exact ordinary Meadows replacements."""
    working = copy.deepcopy(save)
    result = _purchase_storage_upgrade(working, snapshot, params, request_id=request_id)
    save.clear(); save.update(working)
    return result


def _purchase_storage_upgrade(save, snapshot, params, *, request_id=None):
    import storage
    import world_travel
    from items import get_item_by_name
    from game_settings import xp_to_level
    if world_travel.guard_active_world(save) != WORLD:
        raise ValueError('Paid storage growth is currently restored on Sunflower Meadows only.')
    if request_id is None:
        raise ValueError('Paid storage growth requires a signed request sequence.')
    options = storage.world_action_options(params)
    if options and not (set(options) == {'firstWA'} and options['firstWA'] is True):
        raise ValueError('A storage upgrade does not accept client prices, levels or materials.')
    sig = _signature([snapshot.get('id'), snapshot.get('itemName'), snapshot.get('className')])
    key, old = _receipt(save, 'upgrade', request_id, sig)
    if old is not None:
        return old
    owned = [row for row in save['world']['objectsArray'] if row.get('id') == snapshot.get('id')]
    if len(owned) != 1 or owned[0].get('deleted'):
        raise ValueError('Storage growth requires one owned active building.')
    obj = owned[0]
    if obj.get('className') != 'StorageBuilding' or snapshot.get('className') != 'StorageBuilding':
        raise ValueError('Only ordinary storage buildings have this recovered upgrade.')
    names = {name for root in _ROOTS for name in (root, root + '2', root + '3')}
    current = get_item_by_name(obj.get('itemName'))
    if not current or current.get('name') not in names or obj.get('state') not in ('built', 'built_0'):
        raise ValueError('This storage upgrade is not in the recovered Meadows ladder.')
    target = get_item_by_name(current.get('expansion'))
    if target is None:
        # The client also sends complete/getStorageInfo after optimistic upgrade;
        # identical sequence receipts above cover a true retry.
        raise ValueError('This storage building has reached its last recovered upgrade.')
    if (target.get('name') not in names or target.get('className') != 'StorageBuilding'
            or target.get('storageType') != {'itemClass': 'Inventory'}
            or current.get('storageType') != {'itemClass': 'Inventory'}
            or int(target.get('storageSize', 0)) != int(current.get('storageSize', 0)) + 1
            or snapshot.get('itemName') != current['name']):
        raise ValueError('The storage upgrade must follow its original replacement order.')
    if any(target.get(field) for field in ('experimentGate', 'marketPrereqs', 'purchasePrereqs', 'prereqs', 'requiredQuest', 'license')):
        raise ValueError('This storage upgrade has unsupported special prerequisites.')
    if (xp_to_level(save['userInfo']['player']['xp']) or 0) < int(target.get('requiredLevel', 1)):
        raise ValueError('The player level is too low for this storage upgrade.')
    status = save['userInfo']['player'].get('upgradeStatus', {})
    if not isinstance(status, dict) or status.get('isActive') or status.get('numHelped', 0) not in (0, None):
        raise ValueError('Imported social storage-upgrade campaigns are not restored.')
    cost = _whole(int(target['cash']), 'Storage upgrade price')
    player = save['userInfo']['player']
    balance = player['cash']
    if type(balance) not in (int, float) or not math.isfinite(balance) or balance < cost:
        raise ValueError('Not enough Farm Cash for this storage upgrade.')
    # TWorldState captures this source snapshot before client upgrade().
    # Only catalog identity and the saved expansionLevel change. Keep durable
    # contents, object ID, position, alt graphic and unknown imported fields.
    player['cash'] -= cost
    obj['itemName'] = target['name']
    obj['expansionLevel'] = int(target['storageSize'])
    player['upgradeStatus'] = {**status, 'isActive': False}
    import progression
    progression.refresh_owned(save)
    response = {'id': obj['id']}
    _record(save, key, sig, response)
    return response


def acknowledge_paid_storage_upgrade(save, snapshot, params, *, request_id=None):
    """Acknowledge the original post-purchase complete/cancel wire alias only.

    StorageBuilding.upgrade queues TUpgradeStorage(TYPE_COMPLETE), whose
    original constructor sends cancelStorageUpgrade. It cannot cancel, refund
    or grow anything here: a matching earlier paid receipt and saved canonical
    replacement are required. Other cancellation/social paths remain refused.
    """
    working = copy.deepcopy(save)
    result = _acknowledge_paid_storage_upgrade(working, snapshot, params, request_id=request_id)
    save.clear(); save.update(working)
    return result


def _acknowledge_paid_storage_upgrade(save, snapshot, params, *, request_id=None):
    import storage
    import world_travel
    from items import get_item_by_name
    refusal = 'Storage upgrade cancellation is not restored without its exact completed paid upgrade.'
    if world_travel.guard_active_world(save) != WORLD or request_id is None:
        raise ValueError(refusal)
    options = storage.world_action_options(params)
    if options and not (set(options) == {'firstWA'} and options['firstWA'] is True):
        raise ValueError(refusal)
    if (not isinstance(snapshot, dict) or snapshot.get('className') != 'StorageBuilding'
            or snapshot.get('state') not in ('built', 'built_0')):
        raise ValueError(refusal)
    ident = _whole(snapshot.get('id'), 'Storage identity')
    signature = _signature([snapshot.get('id'), snapshot.get('itemName'), snapshot.get('className')])
    key, old = _receipt(save, 'upgradeComplete', request_id, signature)
    if old is not None:
        return old
    source = get_item_by_name(snapshot.get('itemName'))
    names = {name for root in _ROOTS for name in (root, root + '2', root + '3')}
    target = get_item_by_name(source.get('expansion')) if source else None
    if (not source or not target or source.get('name') not in names or target.get('name') not in names
            or source.get('className') != 'StorageBuilding' or target.get('className') != 'StorageBuilding'
            or source.get('storageType') != {'itemClass': 'Inventory'}
            or target.get('storageType') != {'itemClass': 'Inventory'}
            or int(target.get('storageSize', 0)) != int(source.get('storageSize', 0)) + 1):
        raise ValueError(refusal)
    owned = [obj for obj in save['world']['objectsArray'] if obj.get('id') == ident]
    if (len(owned) != 1 or owned[0].get('deleted')
            or owned[0].get('className') != 'StorageBuilding'
            or owned[0].get('itemName') != target['name']
            or owned[0].get('state') not in ('built', 'built_0')
            or type(owned[0].get('expansionLevel')) is not int
            or owned[0]['expansionLevel'] != int(target['storageSize'])):
        raise ValueError(refusal)
    status = save['userInfo']['player'].get('upgradeStatus')
    if (not isinstance(status, dict) or status.get('isActive') is not False
            or status.get('numHelped', 0) not in (0, None)):
        raise ValueError(refusal)
    parts = key.rsplit(':', 2)
    namespace = parts[0] if len(parts) == 3 else None
    sequence = int(parts[-1])
    paid = []
    for paid_key, row in _request_state(save).get('receipts', {}).items():
        if not isinstance(paid_key, str) or not isinstance(row, dict):
            continue
        prior = paid_key.rsplit(':', 2)
        if len(prior) < 2 or prior[-2] != 'upgrade':
            continue
        prior_namespace = prior[0] if len(prior) == 3 else None
        number = prior[-1]
        if (prior_namespace == namespace and number.isdecimal() and str(int(number)) == number
                and int(number) < sequence and row.get('signature') == signature
                and row.get('response') == {'id': ident}):
            paid.append(row)
    if len(paid) != 1:
        raise ValueError(refusal)
    response = {'id': ident}
    _record(save, key, signature, response)
    return response
