"""Original Sheep Pen breeding, recovered from the shipped AS3 and XML.

TAnimal{Begin,Finish,FinishNow}Breeding sends AnimalBreedingSession.serializeForPhp
as one map. AnimalBreedingManager.updateBreedingState consumes extraDataState;
processBreedResult consumes reward.itemName and reward.mutableState (JSON DNA).
Parents remain in the pen. Queued parents and their catalog cooldown are reserved
by exact metadata hash, and successful lambs are granted once into the gift box.

This bounded implementation supports the original Sheep Pen and ordinary HSV
sheep genes. The color-changing/experimental gene families, social adoption,
collection trades and paid animal/level purchases are deliberately rejected by
the integration layer, never acknowledged as successful. Mutations are detached;
the caller's existing save transaction handles durable publication and rollback.
"""
import copy
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import random
import re
import xml.etree.ElementTree as ET
import zlib

from bundle import XML_DIR
import engine
import items
import storage

FEATURE = 'xuk_sheep_pen_finished'
POTION_CODE = 'gk'
_PRESERVED = ('itemName', 'className', 'contents', 'storageMetadata', 'extraDataState',
              'state', 'isFullyBuilt', 'expansionLevel', 'capacity', 'expansionParts')


def _integer(value, label, minimum=0, maximum=2_147_483_647):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or int(value) != value
            or not minimum <= value <= maximum):
        raise ValueError(f'{label} must be a whole number from {minimum} to {maximum}.')
    return int(value)


def _catalog_int(value):
    return _integer(int(value), 'Catalog breeding quantity')


@lru_cache(maxsize=1)
def _config():
    root = ET.fromstring(zlib.decompress((Path(XML_DIR) / 'gz/v855098/AnimalBreeding.xml.gz').read_bytes()))
    feature = root.find(f"feature[@name='{FEATURE}']")
    config = {node.tag: node.text.strip() for node in feature.find('featureConfig')}
    config['times'] = [_catalog_int(n) * 3600 for n in config['defaultBreedTimes'].split(',')]
    config['patterns'] = {node.get('code'): node.get('value') for node in feature.findall('traits/trait/gene')}
    config['variants'] = {}
    for node in feature.findall('variants/variant'):
        def color(tag):
            return {key: [format(int(n), 'x') for n in node.find(tag).get(attr).split(',')]
                    for key, attr in (('H', 'hue'), ('S', 'saturation'), ('V', 'intensity'))}
        try:
            dna = {'N': node.get('name'), 'G': node.get('gender'), 'B': color('base'), 'P': color('pattern')}
        except ValueError:
            # Fractional/color-changing XML alleles belong to the excluded experiments.
            continue
        dna['P']['T'] = [node.find('pattern').get('type')]
        config['variants'].setdefault(node.get('itemName'), dna)
        # The client indexes variantsJSON by variant name. Stock Animal items
        # ask for the variant with the same name as the item.
        config['variants'][node.get('name')] = dna
    config['mutable'] = {n.get('name') for n in feature.findall('mutableAnimals/item')}
    config['limited'] = {n.get('name') for n in feature.findall('mutableAnimals/item') if n.get('limited') == 'true'}
    config['levels'] = {int(n.get('value')): n for n in feature.findall('levels/level')}
    config['milestone'] = feature.find('levels/milestone')
    return config


def manages(item):
    return bool(item and item.get('name') == FEATURE and item.get('className') == 'FeatureBuilding')


def _normalize_baby_contents(snapshot):
    # MutableAnimalBaby extends ConstructionBuilding -> StorageBuilding.
    # StorageBuilding.loadObject (AS3 line 1843) casts truthy contents to Array.
    # Flash serializes its empty associative contents as {}, which AMF keeps
    # an Object. Only this empty case can be repaired without losing contents.
    if snapshot.get('className') == 'MutableAnimalBaby' and snapshot.get('contents') == {}:
        snapshot['contents'] = []


def normalize_baby_contents(save):
    """Repair existing empty baby contents across all owned world snapshots."""
    import world_travel
    for world in world_travel.worlds(save):
        for snapshot in world['objectsArray']:
            _normalize_baby_contents(snapshot)


def _normalize_dna_pattern(dna):
    # MutableAnimalState.getStateKey indexes P.T[0]. AS3 String does not
    # expose numeric property 0; the original gene is a one-element Array.
    if (not isinstance(dna, dict) or not isinstance(dna.get('P'), dict)
            or not isinstance(dna['P'].get('T'), str)
            or len(dna['P']['T']) != 1
            or dna['P']['T'] not in _config()['patterns']):
        return False
    try:
        _dna(json.dumps(dna))
    except (ValueError, TypeError):
        return False
    dna['P']['T'] = [dna['P']['T']]
    return True


def normalize_legacy_dna(save):
    """Repair valid known one-character scalar genes without changing hashes."""
    import world_travel
    def packed(value):
        if not isinstance(value, str):
            return value
        try:
            dna = _dna(value)
        except (ValueError, TypeError):
            return value
        return json.dumps(dna, separators=(',', ':'), ensure_ascii=False) if _normalize_dna_pattern(dna) else value
    for world in world_travel.worlds(save):
        for obj in world['objectsArray']:
            item = items.get_item_by_name(obj.get('itemName'))
            if _mutable_item(item):
                state = obj.get('mutableAnimalState')
                if isinstance(state, dict):
                    _normalize_dna_pattern(state.get('dna'))
                if 'metadata' in obj:
                    obj['metadata'] = packed(obj['metadata'])
            if manages(item) and isinstance(obj.get('storageMetadata'), dict):
                for key, records in obj['storageMetadata'].items():
                    if isinstance(records, list) and _mutable_item(items.get_item_by_code(key.split(':')[0])):
                        records[:] = [packed(value) for value in records]
    for group in save['userInfo']['player'].get('storageData', {}).values():
        if not isinstance(group, dict):
            continue
        for key, entry in group.items():
            if (_mutable_item(items.get_item_by_code(key.split(':')[0]))
                    and isinstance(entry, list) and len(entry) >= 3 and isinstance(entry[2], list)):
                entry[2][:] = [packed(value) for value in entry[2]]


def preserve_fields(stored, incoming):
    """Ordinary world snapshots cannot replace server-owned breeding state."""
    result = copy.deepcopy(incoming)
    if manages(items.get_item_by_name((stored or {}).get('itemName'))):
        for key in _PRESERVED:
            if key in stored:
                result[key] = copy.deepcopy(stored[key])
            else:
                result.pop(key, None)
    elif stored and _mutable_item(items.get_item_by_name(stored.get('itemName'))):
        fields = ('itemName', 'className', 'mutableAnimalState', 'metadata', 'plantTime', 'state')
        if stored.get('className') == 'MutableAnimalBaby':
            fields += ('contents', 'isFullyBuilt', 'expansionLevel', 'expansionParts', 'capacity')
        for key in fields:
            if key in stored:
                result[key] = copy.deepcopy(stored[key])
            else:
                result.pop(key, None)
    elif manages(items.get_item_by_name(incoming.get('itemName'))):
        raise ValueError('A breeding pen snapshot cannot replace a different saved farm object.')
    _normalize_baby_contents(result)
    return result


def initialize_placement(snapshot):
    """Client placement cannot import a breeding queue, parents or metadata."""
    if not manages(items.get_item_by_name(snapshot.get('itemName'))):
        return snapshot
    result = copy.deepcopy(snapshot)
    item = items.get_item_by_name(snapshot.get('itemName'))
    result.update(contents=[], storageMetadata={}, extraDataState={'breedingQueue': [], 'breedHistory': {}},
                  expansionLevel=1, capacity=_catalog_int(item['capacity']))
    default = item.get('defaultItem')
    if isinstance(default, dict):
        adult = items.get_item_by_name(default.get('name'))
        dna = _config()['variants'].get(default.get('name'))
        if not adult or not _mutable_item(adult) or adult.get('className') == 'MutableAnimalBaby' or dna is None:
            raise ValueError('The original pen default adult has no supported catalog DNA.')
        amount = _catalog_int(default.get('amount', '1'))
        packed = json.dumps(dna, separators=(',', ':'), ensure_ascii=False)
        _dna(packed)
        result['contents'].append({'itemCode': adult['code'], 'numItem': amount})
        result['storageMetadata'][adult['code'] + ':' + dna_hash(dna)] = [packed] * amount
    return result


def _pen(save, ident):
    ident = _integer(ident, 'Breeding pen ID')
    matches = [obj for obj in save['world']['objectsArray'] if isinstance(obj, dict)
               and obj.get('id') == ident and not obj.get('deleted')]
    if len(matches) != 1 or not manages(items.get_item_by_name(matches[0].get('itemName'))):
        raise ValueError('The original Sheep Pen is not on this farm.')
    pen = matches[0]
    if pen.get('isFullyBuilt') is False or pen.get('state') in ('construction', 'constructing'):
        raise ValueError('Finish constructing the Sheep Pen before breeding.')
    return pen


def _dna(raw):
    if not isinstance(raw, str) or len(raw) > 4096:
        raise ValueError('Animal DNA must be a compact JSON string.')
    try:
        dna = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError('Animal DNA is malformed.') from exc
    if not isinstance(dna, dict) or dna.get('G') not in ('M', 'F') or not isinstance(dna.get('N'), str):
        raise ValueError('Animal DNA needs a name and a supported gender.')
    reserved_names = {variant['N'] for variant in _config()['variants'].values()}
    if len(dna['N']) > _catalog_int(_config()['maximumNameLength']) and dna['N'] not in reserved_names:
        raise ValueError('The animal name is too long.')
    for layer in ('B', 'P'):
        color = dna.get(layer)
        if not isinstance(color, dict):
            raise ValueError('Animal DNA needs both base and pattern colors.')
        for key, maximum in (('H', 239), ('S', 15), ('V', 15)):
            values = color.get(key)
            if (not isinstance(values, list) or len(values) != 2
                    or any(not isinstance(v, str) or not v or len(v) > 2
                           or any(c not in '0123456789abcdef' for c in v) for v in values)):
                raise ValueError('Animal color genes must contain two hexadecimal alleles.')
            if any(int(v, 16) > maximum for v in values):
                raise ValueError('Experimental or color-changing animal genes are not supported.')
    pattern = dna['P'].get('T')
    if isinstance(pattern, list) and len(pattern) == 1:
        pattern = pattern[0]
    if not isinstance(pattern, str) or pattern not in _config()['patterns']:
        raise ValueError('The animal pattern is not in the original Sheep Pen catalog.')
    return dna


def dna_hash(dna):
    """MutableAnimalState.getStateKey/getHashKey, including its delimiters."""
    key = dna['G']
    for layer in ('B', 'P'):
        for channel in ('H', 'S', 'V'):
            key += dna[layer][channel][0] + ',' + dna[layer][channel][1]
    key += dna['P']['T'][0]
    return hashlib.md5(key.encode('utf-8')).hexdigest()[:8]


def _counts(pen):
    result = {}
    rows = pen.get('contents', [])
    if not isinstance(rows, list):
        raise ValueError('Pen contents must be an array.')
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('itemCode'), str):
            raise ValueError('Pen contents contain an invalid animal.')
        code = row['itemCode']
        if code in result:
            raise ValueError('Pen content codes must be unique.')
        result[code] = _integer(row.get('numItem'), 'Contained animal quantity')
    return result


def _parent(save, pen, key):
    if not isinstance(key, str) or len(key) > 64 or key.count(':') != 1:
        raise ValueError('A parent must use its exact code:DNA hash.')
    code, identity = key.split(':')
    item = items.get_item_by_code(code)
    if not _mutable_item(item) or item.get('className') == 'MutableAnimalBaby':
        raise ValueError('This parent is not an adult sheep supported by the original pen.')
    count = _counts(pen).get(code, 0)
    ledger = save['userInfo']['player'].get('storageData', {}).get(str(pen['id']), {})
    if code in ledger and (not isinstance(ledger[code], list) or ledger[code][0] != count):
        raise ValueError('The parent inventory and pen contents disagree.')
    metadata = pen.get('storageMetadata') or {}
    if not isinstance(metadata, dict):
        raise ValueError('Pen animal metadata must be a map.')
    if identity:
        packed = metadata.get(key)
        if not isinstance(packed, list) or not packed or not isinstance(packed[0], str):
            raise ValueError('The selected parent DNA is not stored in this pen.')
        dna = _dna(packed[0])
        if dna_hash(dna) != identity:
            raise ValueError('The selected parent DNA does not match its saved identity.')
        # Each metadata key represents its own group, with one packed entry per unit.
        count = min(count, len(packed))
    else:
        dna = _config()['variants'].get(item['name'])
        if dna is None:
            raise ValueError('The selected animal has no recoverable breeding variant.')
        dna = _dna(json.dumps(dna))
        count -= sum(len(values) for hash_key, values in metadata.items()
                     if hash_key.startswith(code + ':') and isinstance(values, list))
    expected_gender = 'M' if item.get('keyword') == 'ram' else 'F' if item.get('keyword') == 'sheep' else None
    if expected_gender and dna['G'] != expected_gender:
        raise ValueError('The parent gender disagrees with its catalog animal.')
    if count <= 0:
        raise ValueError('The selected parent is not available in this pen.')
    return dna, count


def _state(pen):
    state = pen.setdefault('extraDataState', {})
    if not isinstance(state, dict):
        raise ValueError('Breeding state must be a map.')
    queue = state.setdefault('breedingQueue', [])
    if not isinstance(queue, list) or len(queue) > 3:
        raise ValueError('The saved breeding queue is malformed.')
    state.setdefault('breedHistory', {})
    return state


def _local(save, pen):
    return save.setdefault('_animalBreeding', {}).setdefault(str(pen['id']), {'jobs': {}, 'claims': {}, 'cooldowns': {}})


def _request(save, raw):
    if not isinstance(raw, dict):
        raise ValueError('Breeding needs one serialized session map.')
    pen = _pen(save, raw.get('buildingId'))
    slot = _integer(raw.get('suiteSlot'), 'Breeding suite', 0, 2)
    level = _integer(pen.get('expansionLevel', 1), 'Pen expansion level', 1, 3)
    if slot >= level:
        raise ValueError('This breeding suite has not been unlocked.')
    potions = _integer(raw.get('numPotions'), 'Love potions', 0, 5)
    parents = raw.get('breedObjs')
    # Original AMF sessions may serialize the array as an indexed map. Accept
    # only the complete two-element shape; sorting arbitrary keys would hide
    # missing positions or extra parents.
    if isinstance(parents, dict):
        if len(parents) == 2 and all(type(key) is int for key in parents) and set(parents) == {0, 1}:
            parents = [parents[0], parents[1]]
        elif len(parents) == 2 and all(type(key) is str for key in parents) and set(parents) == {'0', '1'}:
            parents = [parents['0'], parents['1']]
    if (not isinstance(parents, list) or len(parents) != 2
            or any(not isinstance(parent, dict) or set(parent) != {'hash'} for parent in parents)):
        raise ValueError('Breeding requires exactly two parent hashes.')
    keys = [parent['hash'] for parent in parents]
    if any(not isinstance(key, str) for key in keys):
        raise ValueError('Parent hashes must be strings.')
    if len(set(keys)) != 2:
        raise ValueError('A sheep cannot breed with itself.')
    if not isinstance(raw.get('patternGuarantee', False), bool):
        raise ValueError('The pattern guarantee must be a boolean.')
    return pen, slot, potions, keys, raw.get('patternGuarantee', False)


def _response(pen, reward=None):
    return {'extraDataState': copy.deepcopy(_state(pen)), 'reward': reward}


def _now(now):
    return _integer(engine.timestamp_now() if now is None else now, 'Breeding server time', 1)


def _available(save, pen, key, now):
    dna, count = _parent(save, pen, key)
    local = _local(save, pen)
    count -= sum(key in job['parents'] for job in local['jobs'].values())
    count -= sum(until > now for until in local['cooldowns'].get(key, []))
    return dna, count


def assert_can_remove(save, pen_id, key=None, quantity=1, now=None):
    """Guard pen selling/clearing and exact-parent withdrawals during reservations."""
    pen = _pen(save, pen_id)
    local = _local(save, pen)
    now = _now(now)
    if key is None:
        if local['jobs'] or any(until > now for rows in local['cooldowns'].values() for until in rows):
            raise ValueError('This pen has breeding parents reserved or cooling down.')
        return
    quantity = _integer(quantity, 'Parent withdrawal quantity', 1)
    _, available = _available(save, pen, key, now)
    if quantity > available:
        raise ValueError('The selected parent is breeding or cooling down.')


def _animal_count(save):
    limited = _config()['limited']
    count = sum(obj.get('itemName') in limited for obj in save['world']['objectsArray']
                if isinstance(obj, dict) and not obj.get('deleted'))
    data = save['userInfo']['player'].get('storageData', {})
    for group in data.values():
        for code, entry in group.items():
            item = items.get_item_by_code(code.split(':', 1)[0])
            if item and item['name'] in limited:
                count += _integer(entry[0], 'Animal inventory quantity')
    for obj in save['world']['objectsArray']:
        if isinstance(obj, dict) and not obj.get('deleted') and str(obj.get('id')) not in data:
            for code, amount in _counts(obj).items():
                item = items.get_item_by_code(code)
                if item and item['name'] in limited:
                    count += amount
    return count


def _begin(save, raw, now, rng):
    pen, slot, potions, keys, guarantee = _request(save, raw)
    state = _state(pen)
    local = _local(save, pen)
    old = local['jobs'].get(str(slot))
    if old:
        if old['parents'] == keys and old['potions'] == potions and old['guarantee'] == guarantee:
            return _response(pen)
        raise ValueError('This breeding suite is already occupied.')
    if any(row and row.get('suiteSlot') == slot for row in state['breedingQueue']):
        raise ValueError('This imported breeding session cannot be safely replaced.')
    if f'{slot}:{now}' in local['claims']:
        raise ValueError('Wait for the next server second before starting this suite again.')
    parents = []
    for key in keys:
        dna, count = _available(save, pen, key, now)
        if count <= 0:
            raise ValueError('A selected parent is breeding or cooling down.')
        parents.append(dna)
    if {dna['G'] for dna in parents} != {'M', 'F'}:
        raise ValueError('Sheep breeding requires one ram and one ewe.')
    skill = (save.get('breedingSkillStates') or {}).get(FEATURE, {})
    skill_level = _integer(skill.get('level', 1), 'Breeding level', 1, max(_config()['levels']))
    for dna in parents:
        trait = _config()['patterns'][_pattern(dna)]
        required = min((level for level, node in _config()['levels'].items()
                        for reward in node.findall('reward')
                        if reward.get('type') == 'pattern_unlock' and reward.get('value') == trait), default=1)
        if skill_level < required:
            raise ValueError('This parent pattern has not been unlocked at the current breeding skill level.')
    capacity_rewards = max((int(reward.get('value')) for level, node in _config()['levels'].items()
                            if level <= skill_level for reward in node.findall('reward')
                            if reward.get('type') == 'capacityIncrease'), default=0)
    max_animals = _catalog_int(_config()['maxAnimals']) + capacity_rewards * _catalog_int(_config()['maxIncreasePerRewardLevel'])
    queued = sum(len(p.get('jobs', {})) for p in save.get('_animalBreeding', {}).values())
    if _animal_count(save) + queued >= max_animals:
        raise ValueError('The original sheep breeding animal limit has been reached.')
    gifts = save['userInfo']['player'].setdefault('storageData', {}).setdefault('-1', {})
    entry = gifts.get(POTION_CODE, [0, [], []])
    if not isinstance(entry, list) or len(entry) < 3 or not isinstance(entry[2], list):
        raise ValueError('Love potion inventory metadata is malformed.')
    owned = min(_integer(entry[0], 'Stored love potions'), potions)
    package = items.get_item_by_name('pkg_xuk_animal_love_potion_1')
    if not package or package.get('itemPackage', {}).get('amount') != '1':
        raise ValueError('The original love potion purchase definition is unavailable.')
    cost = (potions - owned) * _catalog_int(package['cash']) + (5 if guarantee else 0)
    player = save['userInfo']['player']
    if _integer(player.get('cash'), 'Farm Cash') < cost:
        raise ValueError('There is not enough Farm Cash for the selected love potions and guarantee.')
    if owned and not storage.store_withdraw_item_by_code(save, POTION_CODE, owned, storage.GIFTBOX_ID):
        raise ValueError('The selected love potions are unavailable.')
    player['cash'] -= cost
    session = {'start_ts': now, 'finish_ts': now + _config()['times'][potions], 'numPotions': potions,
               'buildingId': pen['id'], 'suiteSlot': slot, 'breedObjs': [{'hash': key} for key in keys],
               'patternGuarantee': guarantee}
    while len(state['breedingQueue']) <= slot:
        state['breedingQueue'].append(None)
    state['breedingQueue'][slot] = session
    local['jobs'][str(slot)] = {'parents': keys, 'dna': copy.deepcopy(parents), 'potions': potions,
                              'guarantee': guarantee, 'start': now, 'finish': session['finish_ts'],
                              'randomSeed': rng.getrandbits(32)}
    return _response(pen)


def begin(save, raw, now=None, rng=None):
    detached = copy.deepcopy(save)
    result = _begin(detached, raw, _now(now), random if rng is None else rng)
    save.clear(); save.update(detached)
    return result


def _color(source, rng):
    result = {}
    for channel, maximum, variance in (('H', 239, 15), ('S', 15, 1), ('V', 15, 1)):
        value = int(source[channel][0], 16)
        # Original preview keeps an allele unchanged one fifth of the time.
        if math.floor(rng.random() * 5 + .5) != 3:
            change = math.floor(rng.random() * variance + .5)
            if math.floor(rng.random() * variance + .5) % 2:
                change = -change
            value += change
            value = value % (maximum + 1) if channel == 'H' else min(maximum, max(0, value))
        allele = format(value, 'x')
        result[channel] = [allele, allele]
    return result


def _offspring(save, job, history, rng):
    parents = job['dna']
    gender = 'F' if rng.random() < float(_config()['genderFemaleChance']) else 'M'
    genders = history.get('gender', '')
    if isinstance(genders, str) and len(genders) >= 3 and len(set(genders[-3:])) == 1:
        gender = 'M' if genders[-1] == 'F' else 'F'
    source = parents[math.floor(rng.random() + .5)]
    base = _color(source['B'], rng)
    source = parents[math.floor(rng.random() + .5)]
    pattern = _color(source['P'], rng)
    chance = float(_config()['patternChance'])
    if _pattern(parents[0]) == _pattern(parents[1]):
        chance *= float(_config()['samePatternMultiplier'])
    male = next(parent for parent in parents if parent['G'] == 'M')
    pattern['T'] = [_pattern(male) if job['guarantee'] or rng.random() <= chance else _config()['defaultPatternCode']]
    dna = {'N': '', 'G': gender, 'B': base, 'P': pattern}
    uid = save['userInfo']['player'].get('userId')
    if uid is not None:
        dna['U'] = str(uid)
    _dna(json.dumps(dna))
    return json.dumps(dna, separators=(',', ':'), ensure_ascii=False)


def _grant_rewards(save, rows):
    for node in rows:
        if node.get('type') == 'item_grant':
            item = items.get_item_by_code(node.get('value'))
            if not item:
                raise ValueError('A breeding progression reward is absent from the local catalog.')
            storage.store_deposit_item_by_name(save, item['name'], _catalog_int(node.get('quantity', '1')), storage.GIFTBOX_ID)
        elif node.get('type') not in ('pattern_unlock', 'capacityIncrease'):
            raise ValueError('This breeding progression reward is unsupported.')


def _grant_xp(save):
    levels = _config()['levels']
    milestone = _config()['milestone']
    quantity = _catalog_int(milestone.get('quantity', '0')) if milestone is not None else 0
    skill = save.setdefault('breedingSkillStates', {}).setdefault(FEATURE,
        {'featureName': FEATURE, 'xp': 0, 'level': 1, 'milestones': [False] * quantity})
    skill['xp'] = _integer(skill.get('xp', 0), 'Breeding XP') + _catalog_int(_config()['xpBreedSuccess'])
    level = _integer(skill.get('level', 1), 'Breeding level', 1)
    while level + 1 in levels and skill['xp'] >= _catalog_int(levels[level + 1].get('xp')):
        skill['xp'] -= _catalog_int(levels[level + 1].get('xp'))
        level += 1
        _grant_rewards(save, levels[level].findall('reward'))
        skill['milestones'] = [False] * quantity
    skill['level'] = level
    milestones = skill.setdefault('milestones', [False] * quantity)
    if not isinstance(milestones, list) or len(milestones) != quantity or any(type(v) is not bool for v in milestones):
        raise ValueError('Breeding milestone progress is malformed.')
    if level + 1 in levels:
        threshold = _catalog_int(levels[level + 1].get('xp'))
        for index in range(quantity):
            if not milestones[index] and skill['xp'] >= int(threshold / (quantity + 1) * (index + 1)):
                _grant_rewards(save, milestone.findall('reward'))
                milestones[index] = True


def _finish(save, raw, now, finish_now):
    pen, slot, potions, keys, guarantee = _request(save, raw)
    state = _state(pen)
    local = _local(save, pen)
    start = _integer(raw.get('start_ts'), 'Breeding session start', 1)
    claim_key = f'{slot}:{start}'
    if claim_key in local['claims']:
        if local['claims'][claim_key] != [keys, potions, guarantee]:
            raise ValueError('This completed breeding request does not match the saved parents.')
        return _response(pen)
    job = local['jobs'].get(str(slot))
    if not job or (job['start'], job['parents'], job['potions'], job['guarantee']) != (start, keys, potions, guarantee):
        raise ValueError('The breeding session does not match a pending session on this farm.')
    if now < job['finish']:
        if not finish_now:
            raise ValueError('This breeding session is not ready yet.')
        cost = _catalog_int(_config()['cashToFinishNow'])
        player = save['userInfo']['player']
        if _integer(player.get('cash'), 'Farm Cash') < cost:
            raise ValueError('There is not enough Farm Cash to finish breeding now.')
        player['cash'] -= cost
    for key, expected in zip(job['parents'], job['dna']):
        current, _ = _parent(save, pen, key)
        if current != expected:
            raise ValueError('A reserved parent no longer has its original DNA.')
    rng = random.Random(job['randomSeed'])
    chance = min(1., float(_config()['baseSuccessChance']) + potions * float(_config()['lovePotionBonusChance']))
    reward = None
    history = state['breedHistory']
    if not isinstance(history, dict):
        raise ValueError('Breeding history is malformed.')
    if rng.random() < chance:
        packed = _offspring(save, job, history, rng)
        name = _config()['defaultBreedItem']
        item = items.get_item_by_name(name)
        if not item or item.get('className') != 'MutableAnimalBaby':
            raise ValueError('The original offspring definition is unavailable.')
        storage.store_deposit_item_by_name(save, name, 1, storage.GIFTBOX_ID)
        save['userInfo']['player']['storageData']['-1'][item['code']][2].append(packed)
        reward = {'itemName': name, 'mutableState': packed}
        history['gender'] = (history.get('gender', '') + json.loads(packed)['G'])[-20:]
        _grant_xp(save)
    cooldown = max(0, float(_config()['penCooldownHrs']) - potions * float(_config()['lovePotionCooldownReductionHrs'])) * 3600
    for key in keys:
        local['cooldowns'].setdefault(key, []).append(int(job['start'] + cooldown))
    state['breedingQueue'][slot] = None
    del local['jobs'][str(slot)]
    local['claims'][claim_key] = [keys, potions, guarantee]
    return _response(pen, reward)


def finish(save, raw, now=None, finish_now=False):
    detached = copy.deepcopy(save)
    result = _finish(detached, raw, _now(now), finish_now)
    save.clear(); save.update(detached)
    return result


def _pattern(dna):
    value = dna['P']['T']
    return value[0] if isinstance(value, list) else value


def _mutable_item(item):
    return bool(item and item.get('name') in (set(_config()['variants']) | _config()['mutable'])
                and (item.get('className') or ('Animal' if item.get('type') == 'animal' else None)) in ('Animal', 'MutableAnimal', 'MutableAnimalBaby'))


def _metadata(value):
    # MutableAnimal.packStoreItemMetaData uses {type: JSON}; TBreedAnimalPlace
    # uses the packed JSON itself. Both represent the same complete DNA value.
    if isinstance(value, dict) and set(value) == {'type'}:
        value = value['type']
    return _dna(value) if isinstance(value, str) and value else None


def _source_dna(save, item, group, options, now):
    supplied = _metadata(options.get('metadata'))
    data = save['userInfo']['player'].get('storageData', {})
    code = item['code']
    if group == storage.GIFTBOX_ID:
        entry = data.get(str(group), {}).get(code)
        if not isinstance(entry, list) or len(entry) < 3 or not entry[0] or not isinstance(entry[2], list):
            raise ValueError('The selected breeding animal is missing from the gift box.')
        index = options.get('giftMetadataIndex', -1)
        if index is None:
            index = -1
        index = _integer(index, 'Animal gift metadata index', -1)
        if index >= len(entry[2]):
            raise ValueError('The selected animal gift metadata index is unavailable.')
        if index >= 0:
            dna = _metadata(entry[2][index])
            if dna is None or (supplied is not None and supplied != dna):
                raise ValueError('The placed animal DNA does not match the selected gift.')
            return dna, code, index
        for position, raw in enumerate(entry[2]):
            dna = _metadata(raw)
            if dna is not None and dna == supplied:
                return dna, code, position
        if supplied is not None or item.get('className') == 'MutableAnimalBaby':
            raise ValueError('The selected animal DNA is not owned in the gift box.')
        if _integer(entry[0], 'Animal gift quantity') <= len(entry[2]):
            raise ValueError('Select the exact DNA of the animal gift.')
        dna = _config()['variants'].get(item['name'])
        if dna is None:
            raise ValueError('This stock animal has no recovered DNA variant.')
        return copy.deepcopy(dna), code, -1
    if group > 0:
        pen = _pen(save, group)
        if supplied is None:
            supplied = copy.deepcopy(_config()['variants'].get(item['name']))
        if supplied is None:
            raise ValueError('Select the exact DNA of the stored breeding animal.')
        key = code + ':' + dna_hash(supplied)
        if key not in (pen.get('storageMetadata') or {}):
            key = code + ':'
        dna, available = _available(save, pen, key, now)
        if available < 1 or dna != supplied:
            raise ValueError('The selected stored parent is unavailable or has different DNA.')
        return dna, code, key
    if group < 0:
        if supplied is None:
            supplied = copy.deepcopy(_config()['variants'].get(item['name']))
        if supplied is None:
            raise ValueError('Select the exact DNA of the inventory animal.')
        variant = _config()['variants'].get(item['name'])
        key = code if variant and dna_hash(variant) == dna_hash(supplied) else code + ':' + dna_hash(supplied)
        entry = data.get(str(group), {}).get(key)
        if not isinstance(entry, list) or len(entry) < 3 or _integer(entry[0], 'Animal inventory quantity') < 1:
            raise ValueError('The exact breeding animal is missing from inventory.')
        candidates = [_metadata(raw) for raw in entry[2]]
        if candidates and supplied not in candidates:
            raise ValueError('The inventory animal DNA is unavailable.')
        if key != code and not candidates:
            raise ValueError('The inventory animal DNA is unavailable.')
        return supplied, key, None
    raise ValueError('Breed an offspring or own an animal before placing custom sheep DNA.')


def _withdraw_source(save, item, group, options, now):
    storage._ensure_building_storage(save, group)
    dna, code, identity = _source_dna(save, item, group, options, now)
    if group == storage.GIFTBOX_ID:
        if not storage.remove_gift_by_code(save, code, 1, identity):
            raise ValueError('The animal gift is unavailable.')
    else:
        entry = save['userInfo']['player']['storageData'][str(group)].get(code)
        if entry and isinstance(entry[2], list):
            for index, packed in enumerate(entry[2]):
                if _metadata(packed) == dna:
                    entry[2].pop(index)
                    break
        if not storage.store_withdraw_item_by_code(save, code, 1, group, trim_extra_data=False):
            raise ValueError('The stored breeding animal is unavailable.')
        if group > 0:
            pen = _pen(save, group)
            if identity != item['code'] + ':':
                records = pen['storageMetadata'][identity]
                records.pop(0)
                if not records:
                    del pen['storageMetadata'][identity]
            storage._sync_building_contents(save, group)
    return dna


def withdraw_for_placement(save, item_name, params, snapshot, now=None):
    """Consume an exact owned sheep/baby and install the loader's DNA shape.

    Return None for unrelated items. Call before the generic storage withdrawal;
    a True result means the item was consumed here, so no market charge applies.
    """
    item = items.get_item_by_name(item_name)
    if not _mutable_item(item):
        return None
    options = storage._given_options(params[0] if params else {})
    group = storage._storage_group(options.get('isStorageWithdrawal', 0))
    if options.get('isGift'):
        group = storage.GIFTBOX_ID
    elif options.get('isInventoryWithdrawal') and not group:
        world_type = save['userInfo'].get('currentWorldType') or 'farm'
        group = save['userInfo'].get('worldSummaryData', {}).get(world_type, {}).get('storageId', storage.HOME_INVENTORY_ID)
    if not group:
        if (item.get('className') == 'MutableAnimalBaby' or item.get('buyable') != 'true'
                or options.get('metadata') or snapshot.get('mutableAnimalState')):
            raise ValueError('Custom sheep DNA must come from an owned animal.')
        return None
    detached = copy.deepcopy(save)
    dna = _withdraw_source(detached, item, group, options, _now(now))
    _normalize_dna_pattern(dna)
    result = copy.deepcopy(snapshot)
    result.update(className=item.get('className') or 'Animal', mutableAnimalState={'dna': copy.deepcopy(dna)})
    if item.get('className') == 'MutableAnimalBaby':
        # ConstructionBuilding.onBuildComplete changes the optimistic baby to
        # construction after TBuildingPlace has captured its built snapshot.
        # Gift DNA owns identity; the placement packet cannot supply bottles.
        result.update(contents=[], isFullyBuilt=False, state='construction')
        for field in ('capacity', 'expansionLevel', 'expansionParts'):
            result.pop(field, None)
    _normalize_baby_contents(result)
    save.clear(); save.update(detached)
    snapshot.clear(); snapshot.update(result)
    return True


def start_session(save):
    state = save.get('_animalBreeding', {})
    state.pop('requests', None)
    state.pop('response', None)


def _dispatch(save, action, args, request_id, callback):
    """Original Flash sequences restart at login; retain same-session retries."""
    if request_id is None:
        return callback()
    import pyamf
    def encode(value):
        if isinstance(value, pyamf.UndefinedType):
            return None
        raise ValueError('Unsupported animal request value.')
    sequence = _integer(request_id, 'Animal request sequence')
    world = save['userInfo'].get('currentWorldType') or 'farm'
    signature = json.dumps([world, action, args], sort_keys=True, default=encode)
    requests = save.get('_animalBreeding', {}).get('requests', {})
    key = str(sequence)
    receipt = requests.get('receipts', {}).get(key)
    if receipt is not None:
        if receipt['signature'] != signature:
            raise ValueError('An animal request sequence was reused for another action.')
        save.setdefault('_animalBreeding', {})['response'] = copy.deepcopy(receipt['response'])
        return copy.deepcopy(receipt['result'])
    if sequence <= requests.get('highestSequence', -1):
        raise ValueError('This animal request is older than the retained retry history.')
    result = callback()
    requests = save.setdefault('_animalBreeding', {}).setdefault('requests', {})
    receipts = requests.setdefault('receipts', {})
    receipts[key] = {'signature': signature, 'result': copy.deepcopy(result),
                     'response': copy.deepcopy(save['_animalBreeding'].get('response', {}))}
    requests['highestSequence'] = sequence
    while len(receipts) > 256:
        del receipts[next(iter(receipts))]
    return result


def is_baby_request(save, action, snapshot, params=None):
    """Receipt lamb actions and exact-DNA transfers before snapshots merge.

    A stack can contain several animals with identical DNA. Retrying one
    store packet must not move another unit just because its source is still
    available. These transfers share the existing breeding request lifecycle.
    """
    if action not in ('store', 'TransformBuilding'):
        return False
    options = None
    if isinstance(params, (list, tuple)) and params:
        options = params[0]
    elif isinstance(params, dict):
        # AMF0 ECMA arrays preserve numeric keys. The late action path also
        # reads params[0], so recognize that same supported representation.
        options = params.get(0)
    if action == 'store' and isinstance(options, dict):
        options = storage._given_options(options)
        item = items.get_item_by_name(options.get('storedItemName') or snapshot.get('itemName'))
        if _mutable_item(item):
            return True
    ident = snapshot.get('id')
    if isinstance(ident, (int, float)) and engine.world_object_id_is_temporary(ident):
        # Match the same-session alias used before commands looks up the
        # stored object. Classification must see the identity later merged.
        alias = next((row for row in save['world']['objectsArray'] if row.get('tempId') == ident), None)
        ident = alias.get('id') if alias is not None else None
    owned = next((row for row in save['world']['objectsArray'] if row.get('id') == ident), {})
    if action == 'store' and _mutable_item(items.get_item_by_name(owned.get('itemName'))):
        # preserve_fields restores an owned animal's identity during the
        # later merge. Classify that authoritative identity here as well.
        return True
    return snapshot.get('itemName') == _config()['defaultBreedItem'] or owned.get('className') == 'MutableAnimalBaby'


def dispatch_world(save, action, snapshot, params, request_id, callback):
    return _dispatch(save, action, [snapshot, params], request_id, callback)


def take_response(save):
    return save.get('_animalBreeding', {}).pop('response', {})


def _owned_animal(save, ident):
    import world_travel
    ident = _integer(ident, 'Animal world ID', 1)
    world_travel.guard_action_object(save, ident)
    matches = [row for row in save['world']['objectsArray']
               if row.get('id') == ident and not row.get('deleted')]
    if len(matches) != 1 or not _mutable_item(items.get_item_by_name(matches[0].get('itemName'))):
        raise ValueError('The selected breeding animal is not on the active farm.')
    return matches[0]


def _owned_dna(obj):
    dna = (obj.get('mutableAnimalState') or {}).get('dna')
    if dna is None:
        dna = _config()['variants'].get(obj.get('itemName'))
    return _dna(json.dumps(dna))


def _rename_stored(save, item, identity, name, building):
    """Change only the first stored DNA record selected by the original client."""
    if not _mutable_item(item) or not isinstance(identity, str) or re.fullmatch(r'[0-9a-f]{8}', identity) is None:
        raise ValueError('Select the exact saved DNA of the breeding animal to rename.')
    data = save['userInfo']['player'].get('storageData', {})
    if building is not None:
        if not isinstance(building, dict):
            raise ValueError('The animal storage context must identify its saved Sheep Pen.')
        import world_travel
        ident = _integer(building.get('id'), 'Breeding pen ID', 1)
        world_travel.guard_action_object(save, ident)
        pen = _pen(save, ident)
        if building.get('itemName') not in (None, pen['itemName']):
            raise ValueError('The animal storage context does not match the saved Sheep Pen.')
        key = item['code'] + ':' + identity
        entry = data.get(str(pen['id']), {}).get(item['code'])
        if entry is not None and (not isinstance(entry, list) or len(entry) < 3
                or not isinstance(entry[2], list)):
            raise ValueError('The stored animal inventory metadata is malformed.')
        if entry is not None and len(entry[2]) > _integer(entry[0], 'Stored animal quantity'):
            raise ValueError('The stored animal quantity and DNA disagree.')
        dna, _ = _parent(save, pen, key)
        records = pen['storageMetadata'][key]
        if len(records) > _counts(pen)[item['code']]:
            raise ValueError('The stored animal count and pen DNA disagree.')
        # A ledger recovered from contents can have no extraData; a ledger
        # produced by store_for_game duplicates the exact packed DNA there.
        # Keep that duplicate in step, without importing the optimistic
        # building snapshot sent by TAnimalSetName.perform.
        extras = None
        position = None
        if entry is not None:
            extras = entry[2]
            for index, raw in enumerate(extras):
                if _metadata(raw) == dna:
                    position = index
                    break
            if extras and position is None:
                raise ValueError('The stored animal inventory and pen DNA disagree.')
        dna['N'] = name
        _normalize_dna_pattern(dna)
        packed = json.dumps(dna, separators=(',', ':'), ensure_ascii=False)
        records[0] = packed
        if position is not None:
            extras[position] = packed
        return
    entry = data.get(str(storage.GIFTBOX_ID), {}).get(item['code'])
    if (not isinstance(entry, list) or len(entry) < 3 or not isinstance(entry[2], list)
            or _integer(entry[0], 'Animal gift quantity') < 1 or len(entry[2]) > entry[0]):
        raise ValueError('The selected breeding animal is missing from the gift box.')
    for index, raw in enumerate(entry[2]):
        try:
            dna = _metadata(raw)
        except (ValueError, TypeError):
            continue
        if dna is not None and dna_hash(dna) == identity:
            dna['N'] = name
            _normalize_dna_pattern(dna)
            entry[2][index] = json.dumps(dna, separators=(',', ':'), ensure_ascii=False)
            return
    raise ValueError('The selected animal DNA is not owned in the gift box.')


def rename(save, code, identity, name, world_id, building=None, *, request_id=None):
    """TAnimalSetName's placed, gift and Sheep Pen branches; use owned DNA only."""
    def apply():
        maximum = max(20, _catalog_int(_config()['maximumNameLength']))
        if not isinstance(name, str) or len(name) > maximum or re.fullmatch(r'[A-Za-z0-9 ]*', name) is None:
            raise ValueError('Animal names use at most twenty letters, numbers and spaces.')
        detached = copy.deepcopy(save)
        import world_travel
        world_travel.guard_active_world(detached)
        ident = _integer(world_id, 'Animal world ID', -2_147_483_648)
        if building is not None or ident < 0:
            _rename_stored(detached, items.get_item_by_code(code), identity, name, building)
            save.clear(); save.update(detached)
            return {}
        obj = _owned_animal(detached, world_id)
        item = items.get_item_by_name(obj['itemName'])
        dna = _owned_dna(obj)
        if code != item['code'] or identity != dna_hash(dna):
            raise ValueError('The renamed animal does not match its saved code and DNA hash.')
        dna['N'] = name
        obj.setdefault('mutableAnimalState', {})['dna'] = dna
        if 'metadata' in obj:
            obj['metadata'] = json.dumps(dna, separators=(',', ':'), ensure_ascii=False)
        save.clear(); save.update(detached)
        return {}
    return _dispatch(save, 'onSetAnimalName', [code, identity, name, world_id, building], request_id, apply)


def _baby(save, snapshot):
    obj = _owned_animal(save, snapshot.get('id'))
    item = items.get_item_by_name(obj['itemName'])
    if (obj.get('className') != 'MutableAnimalBaby' or obj['itemName'] != _config()['defaultBreedItem']
            or snapshot.get('itemName') != obj['itemName'] or snapshot.get('className') != obj['className']):
        raise ValueError('Lamb raising requires the exact saved baby identity.')
    _owned_dna(obj)
    return obj, item


def _bottles(save, obj, item):
    import construction
    requirements = construction._initial_requirements(item)
    bottle = items.get_item_by_name('bottle')
    if set(requirements) != {bottle['code']}:
        raise ValueError('The original lamb bottle requirement is unavailable.')
    rows, ledger = construction._contents(save, obj)
    if any(code != bottle['code'] and row['numItem'] for code, row in rows.items()):
        raise ValueError('The lamb has unsupported saved materials.')
    count = ledger.get(bottle['code'], [0])[0]
    needed = requirements[bottle['code']][1]
    if count > needed:
        raise ValueError('The saved lamb has too many bottles.')
    return bottle, count, needed, rows, ledger


def _grow_baby(save, obj, now):
    baby = items.get_item_by_name(obj['itemName'])
    dna = _owned_dna(obj)
    config_key = 'maleItemName' if dna['G'] == 'M' else 'femaleItemName'
    adult = items.get_item_by_name(_config()[config_key])
    if not adult or adult.get('className') != 'MutableAnimal':
        raise ValueError('The original adult sheep definition is unavailable.')
    obj.update(itemName=adult['name'], className=adult['className'], state='bare',
               plantTime=_now(now) * 1000, mutableAnimalState={'dna': dna})
    for field in ('contents', 'isFullyBuilt', 'capacity', 'expansionLevel', 'expansionParts', 'buildTime'):
        obj.pop(field, None)
    save['userInfo']['player'].setdefault('storageData', {}).pop(str(obj['id']), None)
    # This runs only after validated bottle payment on the detached save. Both
    # raising paths share it; retry receipts never enter the transition twice.
    import quests
    quests.record_action(save, 'completeConstructionBuildingByCode', baby['code'])
    return {'finishedName': adult['name']}


def _bottle_source(save, obj, bottle, quantity, options):
    import construction
    group = _integer(options.get('cameFromLocation', options.get('origin', 0)),
                     'Bottle source storage ID', -2_147_483_647)
    flag = options.get('isGift', False)
    if flag not in (False, True, 0, 1):
        raise ValueError('The bottle gift flag is invalid.')
    if flag:
        group = storage.GIFTBOX_ID
    if not group:
        return construction._source(save, obj, bottle, quantity, options)
    inventory = storage.active_inventory_id(save)
    if group not in (storage.GIFTBOX_ID, inventory):
        raise ValueError('Bottles must come from Gift Box or the active farm inventory.')
    storage._ensure_building_storage(save, group)
    entry = save['userInfo']['player'].get('storageData', {}).get(str(group), {}).get(bottle['code'])
    if entry is None or construction._entry(entry)[0] < quantity:
        raise ValueError('There are not enough bottles in the selected source.')
    moved = copy.deepcopy(entry)
    moved[0] = quantity
    moved[1] = copy.deepcopy(entry[1] if entry[0] == quantity else entry[1][:1])
    moved[2] = copy.deepcopy(entry[2][:max(0, len(entry[2]) - (entry[0] - quantity))])
    index = _integer(options.get('giftMetadataIndex', -1), 'Bottle gift metadata index', -1)
    if index >= 0:
        if group != storage.GIFTBOX_ID or quantity != 1 or index >= len(entry[2]):
            raise ValueError('The selected bottle gift metadata is unavailable.')
        moved[2] = [copy.deepcopy(entry[2][index])]
    storage._require_withdrawal(save, bottle, quantity, group, index)
    return moved


def feed_bottles(save, snapshot, options, now=None):
    """Original TStoreItem bottle deposits, including catalog-priced purchase."""
    obj = next((row for row in save['world']['objectsArray'] if row.get('id') == snapshot.get('id')), {})
    if snapshot.get('itemName') != _config()['defaultBreedItem'] and obj.get('className') != 'MutableAnimalBaby':
        return None
    destination = options.get('target', snapshot.get('id'))
    if (options.get('storedItemName') == _config()['defaultBreedItem']
            and type(destination) in (int, float) and destination < 0):
        return None  # Original TInventoryStore; preserve the exact DNA source.
    detached = copy.deepcopy(save)
    obj, item = _baby(detached, snapshot)
    options = storage._given_options(options)
    bottle, count, needed, rows, ledger = _bottles(detached, obj, item)
    if (options.get('storedItemName') != bottle['name'] or options.get('storedItemCode', bottle['code']) != bottle['code']
            or options.get('target', obj['id']) != obj['id']):
        raise ValueError('Only bottles can be fed to the selected lamb.')
    quantity = _integer(options.get('numToStore', 1), 'Fed bottle quantity', 1, needed)
    if count + quantity > needed:
        raise ValueError('That many bottles would overfeed this lamb.')
    if options.get('currency') not in (None, '', bottle.get('market')):
        raise ValueError('Lamb bottles use their original catalog purchase currency.')
    moved = _bottle_source(detached, obj, bottle, quantity, options)
    entry = ledger.setdefault(bottle['code'], [0, [], []])
    entry[0] += quantity; entry[1].extend(moved[1]); entry[2].extend(moved[2])
    if bottle['code'] not in rows:
        obj['contents'].append({'itemCode': bottle['code'], 'numItem': entry[0]})
    else:
        rows[bottle['code']]['numItem'] = entry[0]
    obj.update(isFullyBuilt=False, state='construction')
    response = _grow_baby(detached, obj, now) if count + quantity == needed else {}
    detached.setdefault('_animalBreeding', {})['response'] = response
    save.clear(); save.update(detached)
    return response


def transform_baby(save, snapshot, params, now=None):
    """TTransformBuilding: catalog cash cost minus bottles already supplied."""
    if any(not isinstance(row, dict) or set(row) - {'firstWA'} for row in params):
        raise ValueError('Lamb completion does not accept client price or reward options.')
    detached = copy.deepcopy(save)
    obj, item = _baby(detached, snapshot)
    bottle, count, needed, _, _ = _bottles(detached, obj, item)
    # Player.tryBuy(lamb, false, lamb.item, lamb.count) subtracts count from
    # realCashCost. The original catalog is ten cash and ten one-cash bottles.
    price = engine.catalog_price(item, 'cash')
    if price != needed * engine.catalog_price(bottle, 'cash'):
        raise ValueError('The original lamb completion price is inconsistent.')
    cost = price - count
    player = detached['userInfo']['player']
    balance = _integer(player.get('cash'), 'Lamb completion cash balance')
    if balance < cost:
        raise ValueError('Not enough Farm Cash to complete this lamb.')
    player['cash'] = balance - cost
    response = _grow_baby(detached, obj, now)
    detached.setdefault('_animalBreeding', {})['response'] = response
    save.clear(); save.update(detached)
    return obj['id']


def store_for_game(save, snapshot, options, now=None):
    """Store one owned mutable sheep in its pen/inventory, retaining exact DNA.

    Return None for unrelated storage actions. Bred animal metadata is never
    accepted from a caller without a matching saved world/container/gift source.
    """
    options = storage._given_options(options)
    item = items.get_item_by_name(options.get('storedItemName') or snapshot.get('itemName'))
    if not _mutable_item(item):
        return None
    if _integer(options.get('numToStore', 1), 'Stored sheep quantity', 1) != 1:
        raise ValueError('Store breeding sheep one exact animal at a time.')
    destination = _integer(options.get('target', snapshot.get('id')), 'Sheep storage destination', -52)
    if destination == 0 or destination == storage.GIFTBOX_ID or destination == storage.CONSUME_ID:
        raise ValueError('This sheep storage destination is not supported.')
    detached = copy.deepcopy(save)
    target = _pen(detached, destination) if destination > 0 else None
    if target is not None and item.get('className') == 'MutableAnimalBaby':
        raise ValueError('Only adult sheep belong in the original Sheep Pen.')
    source_groups = [storage._storage_group(options[field]) for field in ('cameFromLocation', 'origin')
                     if field in options]
    if len({group for group in source_groups if group}) > 1:
        raise ValueError('The sheep storage source is ambiguous.')
    group = next((group for group in source_groups if group), 0)
    if options.get('isGift'):
        group = storage.GIFTBOX_ID
    if group == destination:
        raise ValueError('The sheep is already in this storage.')
    resource_id = _integer(options.get('resource', 0), 'Stored sheep resource ID')
    if target is None:
        storage._guard_inventory_deposit(detached, destination, 1,
                                         resource_id if not group else None)
    else:
        # This specialized DNA path runs before generic storage admission.
        # Reuse the authored expansion ladder rather than trusting capacity
        # carried by a world snapshot (20 / 30 / 40 in the original pen).
        if target.get('className') != 'FeatureBuilding':
            raise ValueError('The Sheep Pen must retain its original class.')
        if target.get('isFullyBuilt') is not None and target['isFullyBuilt'] is not True:
            raise ValueError('Finish constructing the Sheep Pen before storing an animal.')
        counts = _counts(target)
        ledger = detached['userInfo']['player'].get('storageData', {}).get(str(destination))
        if ledger is not None:
            if (not isinstance(ledger, dict) or any(
                    not isinstance(entry, list) or len(entry) < 3
                    or not isinstance(entry[1], list) or not isinstance(entry[2], list)
                    for entry in ledger.values())):
                raise ValueError('The Sheep Pen inventory metadata is malformed.')
            if {code: _integer(entry[0], 'Contained animal quantity') for code, entry in ledger.items()} != counts:
                raise ValueError('The Sheep Pen inventory and contents disagree.')
        if sum(counts.values()) + 1 > storage._container_capacity(target, items.get_item_by_name(FEATURE)):
            raise ValueError('The Sheep Pen does not have enough storage space.')
    if group:
        dna = _withdraw_source(detached, item, group, options, _now(now))
    else:
        sources = [obj for obj in detached['world']['objectsArray']
                   if obj.get('id') == resource_id and not obj.get('deleted')]
        source = sources[0] if len(sources) == 1 else None
        if source is None or source.get('itemName') != item['name']:
            raise ValueError('The stored sheep is not owned on this farm.')
        if source.get('className') == 'MutableAnimalBaby' and any(_counts(source).values()):
            raise ValueError('Finish raising this lamb before storing it; its bottle progress cannot be packed as DNA.')
        state = source.get('mutableAnimalState') or {}
        dna = state.get('dna')
        if dna is None:
            dna = _config()['variants'].get(item['name'])
        if dna is None:
            raise ValueError('The stored sheep has no recoverable DNA.')
        dna = _dna(json.dumps(dna))
        supplied = _metadata(options.get('metadata'))
        if supplied is not None and supplied != dna:
            raise ValueError('The stored sheep metadata does not match the owned animal.')
        detached['world']['objectsArray'].remove(source)
    packed = json.dumps(dna, separators=(',', ':'), ensure_ascii=False)
    storage._ensure_building_storage(detached, destination)
    variant = _config()['variants'].get(item['name'])
    key = item['code']
    if destination < 0 and (not variant or dna_hash(variant) != dna_hash(dna)):
        key += ':' + dna_hash(dna)
    data = detached['userInfo']['player']['storageData'].setdefault(str(destination), {})
    entry = data.setdefault(key, [0, [], []])
    entry[0] += 1
    entry[2].append(packed)
    if target is not None:
        target.setdefault('storageMetadata', {}).setdefault(item['code'] + ':' + dna_hash(dna), []).append(packed)
        storage._sync_building_contents(detached, destination)
    save.clear(); save.update(detached)
    return True


def guard_action(save, action, stored, incoming, now=None):
    """Keep unrelated world actions from replacing a pen or mutable sheep."""
    item = items.get_item_by_name((stored or incoming or {}).get('itemName'))
    incoming_item = items.get_item_by_name((incoming or {}).get('itemName'))
    if manages(item) or manages(incoming_item):
        if action not in ('place', 'move', 'store', 'sell', 'clear', 'harvest', 'neighborAct'):
            raise ValueError('This action cannot replace an original breeding pen.')
        if stored and action in ('sell', 'clear'):
            assert_can_remove(save, stored['id'], now=now)
    if _mutable_item(incoming_item) and stored and not _mutable_item(item):
        raise ValueError('A breeding animal cannot replace a different saved farm object.')
    if _mutable_item(item) or _mutable_item(incoming_item):
        if action not in ('place', 'move', 'store', 'sell', 'clear', 'harvest', 'neighborAct'):
            raise ValueError('This action cannot replace a breeding animal.')


def guard_storage(save, snapshot, options, now=None):
    """Reject unrelated animals/materials before a generic pen storage mutation."""
    options = storage._given_options(options)
    ident = options.get('target', snapshot.get('id'))
    target = next((obj for obj in save['world']['objectsArray'] if obj.get('id') == ident and not obj.get('deleted')), None)
    if target and manages(items.get_item_by_name(target.get('itemName'))):
        item = items.get_item_by_name(options.get('storedItemName'))
        if not _mutable_item(item) or item.get('className') == 'MutableAnimalBaby':
            raise ValueError('The original Sheep Pen only stores eligible adult sheep.')


def guard_storage_withdrawal(save, item, quantity, group):
    """A fallback generic withdrawal must never skip exact parent reservations."""
    if group > 0:
        pen = next((obj for obj in save['world']['objectsArray'] if obj.get('id') == group and not obj.get('deleted')), None)
        if pen and manages(items.get_item_by_name(pen.get('itemName'))):
            raise ValueError('Withdraw a Sheep Pen animal through its exact saved DNA.')
