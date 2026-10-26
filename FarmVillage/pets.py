"""Original puppy purchase, feeding and training contracts from FarmGame.

Evidence: TPetsPlace, TUseTargetedConsumable/CPetsKibble, Pet.loadObject,
Pet.updateFedState/isAdult/updateLevel, TRescuePet and gameSettings.petData.
Times on each pet are milliseconds (Global.worldTime); the caller supplies
server seconds. Food is consumed from gifts only: the two single-food items
have no catalog sale price. Purchase their original packages first.

Fetch rewards, pet harvesting and generic storage are deliberately rejected
until their reward/identity contracts are recovered. Naming is the original
purchase customization, not an invented rename endpoint.
"""
import copy
from functools import lru_cache
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zlib

from bundle import XML_DIR
import engine
from game_settings import xp_to_level
import items
import storage

DAY_MS = 86_400_000
GROW_DAYS = 14  # Pet.PET_DAYS_TO_GROW
FOODS = ('consume_kibble', 'consume_treat')
FOOD_PACKAGES = {'pkg_kibble': 'consume_kibble', 'pkg_treat': 'consume_treat'}
ACTIONS = ('runaway', 'rescuePet', 'adulthoodReached', 'performTrick')
_FIELDS = ('itemName', 'className', 'plantTime', 'state', 'petName', 'petGender',
           'petLevel', 'lastFedTime', 'kibbleFedCount', 'isCash', 'isRunAway',
           'hasUserSeenAdult', 'wasLevelResetOnLoad', 'levelStartTime',
           '_petLastFeed', 'allowFollow')


def _integer(value, label, minimum=0, maximum=2**53 - 1):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or int(value) != value
            or not minimum <= value <= maximum):
        raise ValueError(f'{label} must be a whole number from {minimum} to {maximum}.')
    return int(value)


def _options(params):
    if isinstance(params, dict):
        if set(params) == set(range(len(params))):
            params = [params[n] for n in range(len(params))]
        elif set(params) == {str(n) for n in range(len(params))}:
            params = [params[str(n)] for n in range(len(params))]
    if (not isinstance(params, list) or len(params) > 2
            or (params and not isinstance(params[0], dict))
            or (len(params) == 2 and params[1] != {'firstWA': True})):
        raise ValueError('A pet action takes one parameter map.')
    return storage._given_options(params[0] if params else {})


@lru_cache(maxsize=1)
def _config():
    root = ET.fromstring(zlib.decompress((Path(XML_DIR) / 'gz/v855098/gameSettings.xml.gz').read_bytes()))
    data = root.find('.//petData')
    pets = {}
    for family in data.findall('pets/pet'):
        tricks = {int(t.get('level')): t.get('name') for t in family.findall('trick')}
        for variant in family.findall('item'):
            pets.setdefault(variant.get('name'), tricks)
    return {'pets': pets,
            'levels': {int(n.get('num')): int(n.get('treatsNeeded')) for n in data.findall('levels/level')},
            'animations': {n.get('name') for n in data.findall('tricks/trick') if n.get('isAnimationOnly') == 'true'}}


def manages(item):
    return bool(item and item.get('className') == 'Pet')


def _supported(item):
    if not manages(item) or item['name'] not in _config()['pets']:
        raise ValueError('This pet is not in the recovered original puppy catalog.')


def _is_pet(snapshot):
    return bool(snapshot and (snapshot.get('className') == 'Pet'
                or manages(items.get_item_by_name(snapshot.get('itemName')))))


def guard_action(action, stored, incoming):
    if not (_is_pet(stored) or _is_pet(incoming)):
        if action in ACTIONS:
            raise ValueError('This pet action requires an owned puppy.')
        return
    item = items.get_item_by_name((stored or incoming).get('itemName'))
    _supported(item)
    if stored:
        if any(incoming.get(key) != stored.get(key) for key in ('itemName', 'className')):
            raise ValueError('A pet action cannot replace its saved identity.')
        if not _is_pet(stored):
            raise ValueError('A pet cannot replace a different farm object.')
    elif action not in ('place', 'sell', 'clear'):
        raise ValueError('This pet is not on the active farm.')
    if action not in ('place', 'move', 'sell', 'clear') + ACTIONS:
        raise ValueError('This pet action has no supported original contract.')


def preserve_fields(stored, incoming):
    if not _is_pet(stored):
        return incoming
    result = copy.deepcopy(incoming)
    for key in _FIELDS:
        if key in stored:
            result[key] = copy.deepcopy(stored[key])
        else:
            result.pop(key, None)
    return result


def placement_retry(stored, incoming, params):
    if not _is_pet(stored):
        return False
    options = _options(params)
    item = items.get_item_by_name(stored['itemName'])
    if (incoming.get('position') != stored.get('position')
            or options.get('petType') != item['code']
            or options.get('petName') != stored.get('petName')
            or options.get('petGender') != stored.get('petGender')
            or options.get('isGift') or options.get('isStorageWithdrawal')):
        raise ValueError('A puppy placement retry must identify the same named puppy.')
    return True


def initialize_placement(save, incoming, params, *, now=None, neighbor_count=0):
    if not _is_pet(incoming):
        return incoming
    item = items.get_item_by_name(incoming.get('itemName'))
    _supported(item)
    if incoming.get('className') != 'Pet':
        raise ValueError('The puppy class must match the catalog.')
    options = _options(params)
    if (options.get('isGift') or options.get('isStorageWithdrawal')
            or options.get('isInventoryWithdrawal') or options.get('metadata')):
        raise ValueError('Original puppy placement is a named market purchase.')
    if options.get('petType') != item['code']:
        raise ValueError('The selected puppy variant must match its catalog code.')
    name = options.get('petName')
    # Display.CustomizePets: MESSAGE_BOX_CHAR_LIMIT=16, TF_RESTRICT=A-Z a-z.\-
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z .-]{1,16}', name) or not name.strip():
        raise ValueError('A puppy name needs 1–16 letters, spaces, dots or hyphens.')
    gender = _integer(options.get('petGender'), 'Pet gender', maximum=1)
    currency = item.get('market') or 'coins'
    if options.get('currency', currency) not in (currency, 'gold' if currency == 'coins' else currency):
        raise ValueError('A puppy must use its catalog purchase currency.')
    price = engine.catalog_price(item, 'cash' if currency == 'cash' else 'cost')
    if not price or price <= 0:
        raise ValueError('This puppy has no recovered purchase price.')
    if xp_to_level(save['userInfo']['player']['xp']) < int(item.get('requiredLevel', 1)):
        raise ValueError('This puppy requires a higher farm level.')
    if neighbor_count < int(item.get('minNeighbors', 0)):
        raise ValueError('This puppy requires more local neighbors.')
    if item.get('limit'):
        import world_travel
        owned = sum(obj.get('itemName') == item['name'] and not obj.get('deleted')
                    for world in world_travel.worlds(save) for obj in world.get('objectsArray', []))
        if owned >= int(item['limit']):
            raise ValueError('The catalog limit for this puppy has been reached.')
    now_ms = _integer(engine.timestamp_now() if now is None else now, 'Pet time', minimum=1) * 1000
    result = copy.deepcopy(incoming)
    # All development and feeding fields originate on the server.
    for key in _FIELDS:
        result.pop(key, None)
    result.update(itemName=item['name'], className='Pet', state='static', plantTime=now_ms,
                  petName=name, petGender=gender, petLevel=0, lastFedTime=0,
                  kibbleFedCount=0, isCash=currency == 'cash', isRunAway=False,
                  hasUserSeenAdult=False, wasLevelResetOnLoad=False, levelStartTime=0,
                  allowFollow=False)
    return result


def finish_purchase(save, snapshot):
    if _is_pet(snapshot):
        amount = int(items.get_item_by_name(snapshot['itemName']).get('kibbleBonus', 0))
        if amount:
            storage.store_deposit_item_by_name(save, 'consume_kibble', amount, storage.GIFTBOX_ID)


def buy_food_package(save, package_name, *, request_id=None):
    """Original food packages, with durable retry protection and catalog costs."""
    item = items.get_item_by_name(package_name)
    food = FOOD_PACKAGES.get(package_name)
    package = item.get('itemPackage') if item else None
    if (food is None or not isinstance(package, dict) or package.get('value') != food
            or not items.get_item_by_name(food)):
        raise ValueError('This is not a recovered pet food package.')
    amount = _integer(int(package.get('amount', '1')), 'Catalog pet food amount', minimum=1, maximum=100)
    if (engine.catalog_price(item, 'cash') or 0) <= 0:
        raise ValueError('The pet food package has no recovered cash price.')
    def purchase():
        detached = copy.deepcopy(save)
        engine.apply_item_cost(detached, item, currency='cash')
        storage.store_deposit_item_by_name(detached, food, amount, storage.GIFTBOX_ID)
        save.clear()
        save.update(detached)
        return {}
    if request_id is None:
        return purchase()
    return dispatch(save, 'buyFoodPackage', {'itemName': package_name}, [], request_id, purchase)


def _refresh(pet, now_ms):
    _supported(items.get_item_by_name(pet.get('itemName')))
    level = _integer(pet.get('petLevel'), 'Saved pet level', maximum=max(_config()['levels']))
    count = _integer(pet.get('kibbleFedCount'), 'Saved pet feed count', maximum=GROW_DAYS)
    planted = _integer(pet.get('plantTime'), 'Saved puppy purchase time', minimum=1)
    last_fed = _integer(pet.get('lastFedTime'), 'Saved pet feeding time')
    start = _integer(pet.get('levelStartTime'), 'Saved pet training start')
    if type(pet.get('isCash')) is not bool or type(pet.get('isRunAway')) is not bool:
        raise ValueError('Saved pet purchase and runaway states must be booleans.')
    # Pet.isAdult requires age for every puppy, plus all feeds for coin puppies.
    if level == 0 and now_ms - planted >= GROW_DAYS * DAY_MS and (pet['isCash'] or count >= GROW_DAYS):
        pet.update(petLevel=1, kibbleFedCount=0)
        level, count = 1, 0
    if level > 0:
        if level < max(_config()['levels']) and start:
            window = now_ms - (now_ms - start) % DAY_MS
            if count and last_fed < window - DAY_MS:
                pet.update(kibbleFedCount=0, levelStartTime=0, wasLevelResetOnLoad=True)
        return
    window = now_ms - (now_ms - planted) % DAY_MS
    if (not pet['isCash'] and count < GROW_DAYS and now_ms - planted >= 2 * DAY_MS
            and last_fed < window - DAY_MS):
        pet.update(isRunAway=True, allowFollow=False)


def refresh_world(save, *, now=None):
    now_ms = (engine.timestamp_now() if now is None else now) * 1000
    for pet in save['world']['objectsArray']:
        if _is_pet(pet):
            # Earlier builds saved ordinary Pet snapshots without any of the
            # Pet.loadObject fields. Recover a safe puppy baseline so that an
            # existing farm remains loadable; never infer feeds or training.
            if 'petLevel' not in pet:
                item = items.get_item_by_name(pet.get('itemName'))
                _supported(item)
                pet.update(petName='Puppy', petGender=0, petLevel=0,
                           plantTime=now_ms, lastFedTime=0, kibbleFedCount=0,
                           isCash=item.get('market') == 'cash', isRunAway=False,
                           hasUserSeenAdult=False, wasLevelResetOnLoad=False,
                           levelStartTime=0, allowFollow=False)
            _refresh(pet, now_ms)


def start_session(save, *, now=None):
    save.pop('_petRequests', None)
    refresh_world(save, now=now)


def is_request(action, incoming):
    return _is_pet(incoming) or action in ACTIONS or (action == 'use' and incoming.get('itemName') in FOODS)


def dispatch(save, action, incoming, params, request_id, callback):
    """Durable per-Flash receipts: restart retries cannot buy/feed twice."""
    sequence = _integer(request_id, 'Pet request sequence')
    key = str(sequence)
    import pyamf
    def encode(value):
        if isinstance(value, pyamf.UndefinedType):
            return None
        raise ValueError('Unsupported pet request value.')
    world = save['userInfo'].get('currentWorldType') or 'farm'
    signature = json.dumps([world, action, incoming, params], sort_keys=True, default=encode)
    state = save.get('_petRequests', {})
    receipts = state.get('receipts', {})
    if key in receipts:
        if receipts[key]['signature'] != signature:
            raise ValueError('A pet request sequence was reused for another action.')
        return receipts[key]['result']
    if sequence <= state.get('highestSequence', -1):
        raise ValueError('This pet request is older than the retained retry history.')
    result = callback()
    state = save.setdefault('_petRequests', {})
    receipts = state.setdefault('receipts', {})
    receipts[key] = {'signature': signature, 'result': result}
    state['highestSequence'] = sequence
    while len(receipts) > 256:
        del receipts[next(iter(receipts))]
    return result


def _owned(save, ident):
    # TUseTargetedConsumable casts the target ID to String.
    if isinstance(ident, str) and re.fullmatch(r'[0-9]+', ident):
        ident = int(ident)
    ident = _integer(ident, 'Pet object ID', minimum=1)
    pets = [obj for obj in save['world']['objectsArray'] if obj.get('id') == ident and not obj.get('deleted')]
    if len(pets) != 1 or not _is_pet(pets[0]):
        raise ValueError('The selected pet is not on the active farm.')
    return pets[0]


def feed(save, incoming, params, *, uid, now=None):
    """Handle the actual targeted-use packet, without inventing free pet food."""
    if incoming.get('itemName') not in FOODS:
        return False
    options = _options(params)
    if options.get('targetUser', '0') not in ('0', str(uid)):
        raise ValueError('Pet food can only target the current local farmer.')
    if options.get('isFree') or options.get('isGift') is not True:
        raise ValueError('Pet food must come from an owned Gift Box item.')
    if (_integer(options.get('itemCount', 1), 'Pet food quantity', minimum=1, maximum=1) != 1
            or options.get('storageId', -1) != -1):
        raise ValueError('One pet food item must come from the Gift Box.')
    now_ms = (engine.timestamp_now() if now is None else now) * 1000
    stored = _owned(save, options.get('targetObjectId'))
    pet = copy.deepcopy(stored)
    _refresh(pet, now_ms)
    food = incoming['itemName']
    # The last-food window also covers the feed that promoted a puppy/level.
    previous = pet.get('_petLastFeed', {})
    if (previous.get('item') == food and previous.get('until', 0) > now_ms):
        return True
    if pet['isRunAway']:
        raise ValueError('Rescue the runaway puppy before feeding it.')
    level, count = pet['petLevel'], pet['kibbleFedCount']
    expected = FOODS[bool(level)]
    if food != expected:
        raise ValueError('Puppies eat kibble; adult dogs train with treats.')
    if level == max(_config()['levels']) or (not level and count >= GROW_DAYS):
        raise ValueError('This pet has completed its current feeding stage.')
    anchor = pet['levelStartTime'] if level else pet['plantTime']
    if not anchor:
        anchor = now_ms
    window = now_ms - (now_ms - anchor) % DAY_MS
    if pet['lastFedTime'] >= window:
        return True
    if not storage.store_withdraw_item_by_name(save, food, 1, storage.GIFTBOX_ID):
        raise ValueError('There is no pet food in the Gift Box.')
    if level and count == 0:
        pet['levelStartTime'] = now_ms
        window = now_ms
    pet.update(lastFedTime=now_ms, kibbleFedCount=count + 1, wasLevelResetOnLoad=False,
               _petLastFeed={'item': food, 'until': window + DAY_MS})
    if level and pet['kibbleFedCount'] >= _config()['levels'][level + 1]:
        pet.update(petLevel=level + 1, kibbleFedCount=0)
    _refresh(pet, now_ms)
    engine.world_replace_object(save['world']['objectsArray'], pet)
    return True


def move_fields(snapshot, params):
    if not _is_pet(snapshot):
        return snapshot
    options = _options(params)
    if options.get('visiting') not in (None, 0, '0', ''):
        raise ValueError('A pet cannot be moved on a visited farm.')
    result = copy.deepcopy(snapshot)
    if 'allowFollow' in options:
        if type(options['allowFollow']) is not bool:
            raise ValueError('Pet follow preference must be a boolean.')
        result['allowFollow'] = options['allowFollow'] and not result.get('isRunAway')
    # Pet.syncPosition reports rounded x/y in TMove params, while its ordinary
    # inherited save object may still contain the previous position.
    if 'x' in options or 'y' in options:
        result['position'] = dict(result.get('position') or {})
        for axis in ('x', 'y'):
            result['position'][axis] = _integer(options.get(axis), 'Pet position', minimum=-10000, maximum=10000)
    if 'direction' in options:
        result['direction'] = _integer(options['direction'], 'Pet direction', maximum=7)
    return result


def perform_action(save, action, snapshot, params, *, now=None):
    if action not in ACTIONS:
        return False
    now_ms = (engine.timestamp_now() if now is None else now) * 1000
    pet = copy.deepcopy(_owned(save, snapshot['id']))
    _refresh(pet, now_ms)
    options = _options(params)
    if action == 'runaway':
        if not pet['isRunAway']:
            raise ValueError('This puppy is not eligible to run away.')
    elif action == 'rescuePet':
        if pet['isRunAway']:
            engine.apply_item_cost(save, items.get_item_by_name('pet_rescue'), currency='cash')
            pet.update(isRunAway=False, lastFedTime=now_ms, allowFollow=False)
    elif action == 'adulthoodReached':
        if pet['petLevel'] < 1:
            raise ValueError('This puppy has not reached adulthood.')
        pet['hasUserSeenAdult'] = True
    elif action == 'performTrick':
        trick = options.get('trickName')
        known = {'tickle'} | {name for level, name in _config()['pets'][pet['itemName']].items()
                              if level <= pet['petLevel']}
        if pet['isRunAway'] or trick not in known:
            raise ValueError('This pet has not learned the selected trick.')
        if trick not in _config()['animations'] or options.get('harvestObjectIds'):
            raise ValueError('Pet reward and harvesting tricks are not implemented.')
    engine.world_replace_object(save['world']['objectsArray'], pet)
    return True


def response_for_action(save, action, ident):
    if action == 'rescuePet':
        return {'lastFedTime': _owned(save, ident)['lastFedTime']}
    return {}


def guard_storage(save, snapshot, options):
    item = items.get_item_by_name(options.get('storedItemName') or snapshot.get('itemName'))
    resource = options.get('resource')
    if isinstance(resource, str) and resource.isdigit():
        resource = int(resource)
    source = next((obj for obj in save['world']['objectsArray'] if obj.get('id') == resource), None)
    if manages(item) or _is_pet(source):
        raise ValueError('Original pets cannot enter generic storage without their individual state.')
