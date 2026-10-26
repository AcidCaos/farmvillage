"""Match ordinary themed Market offers to accepted basic-world purchases.

Reuse the original per-world class-lock UI. Only derived own-world offers and
32 admitted global storage records change; global crops/items, raw definitions,
imported gift/seed/license flows and all legacy-world HUDs remain available.
"""
from functools import lru_cache
import copy
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zlib

import pyamf
from bundle import XML_DIR, TEMPLATES_DIR

CATALOG_SOURCE = Path(XML_DIR) / 'gz/v855038/items_opt.amf'
WORLD_SETTINGS_SOURCE = Path(XML_DIR) / 'gz/v855098/worldSettings.xml.gz'
CATALOG_SHA256 = '14987fd4c07f9de35ff5092aeab58584802fd7fbeca1131ad1a5e3eee381a4d7'
WORLD_SETTINGS_SHA256 = '769db5f72b5586b036792332c9c9c89dac43ca6ae2fc6f5ddb761d829d1c014e'
LEGACY_WORLDS = frozenset(('farm','england','meadows','fisherman','hallow','hawaii'))
_DROP = object()
GLEN_SCORE_SEEDS = frozenset(('ambrosiatulip','boggartbulb','butterflyrose',
    'darkdahlia','dreamcotton','elfintea','fairyfoxglove','goblinvine',
    'gossamerivy','honeymelon','nectarkin','pixieberry'))


def _themed():
    import themed_worlds
    return themed_worlds


def _worlds(item):
    return {node.get('name') for node in _themed().creative_worlds._nodes(item.get('requirements'))
            if node.get('className') == 'World'}


def supported_worlds():
    return LEGACY_WORLDS | frozenset(_themed().SPECS)


def policy_digest():
    themed = _themed()
    digest = hashlib.sha256()
    for data in (Path(__file__).read_bytes(), Path(themed.__file__).read_bytes(),
                 json.dumps(themed.SPECS, sort_keys=True).encode(),
                 json.dumps(sorted(supported_worlds())).encode(),
                 CATALOG_SOURCE.read_bytes(), WORLD_SETTINGS_SOURCE.read_bytes(),
                 Path(TEMPLATES_DIR, 'play.html').read_bytes()):
        digest.update(len(data).to_bytes(8,'big')); digest.update(data)
    for source in themed.feature_policy_sources():
        data = source.read_bytes()
        digest.update(len(data).to_bytes(8,'big')); digest.update(data)
    return digest.hexdigest()


def _raw_items():
    raw = CATALOG_SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CATALOG_SHA256:
        raise ValueError('The themed Market catalog requires review.')
    return pyamf.get_decoder(pyamf.AMF3,zlib.decompress(raw)).readElement()['settings']['items']['item']


@lru_cache(maxsize=1)
def class_locks():
    names = set()
    for item in _raw_items():
        name = item.get('className')
        if name is None:name = ''
        if not isinstance(name,str):
            raise ValueError('A themed Market class name requires review.')
        names.add(name)
    if len(names) != 292 or '' not in names:
        raise ValueError('The themed Market class roster requires review.')
    return tuple(sorted(names))


@lru_cache(maxsize=1)
def _admissions():
    themed = _themed()
    return {world:frozenset(name for name,row in themed.catalog_rules(world)['items'].items()
                            if row['price'] is not None) for world in themed.SPECS}


def _is_land(item):
    return item.get('type') == 'change_farm' and item.get('subtype') == 'expand_farm'


def _trim_worlds(value, remove):
    if isinstance(value,dict):
        if value.get('className') == 'World' and value.get('name') in remove:
            return _DROP
        return {key:child for key,nested in value.items()
                if (child := _trim_worlds(nested,remove)) is not _DROP}
    if isinstance(value,list):
        return [child for nested in value if (child := _trim_worlds(nested,remove)) is not _DROP]
    return copy.deepcopy(value)


def _without_glen_harvest_score(item):
    """Fence the twelve original client pixie writers in derived seed records."""
    if 'glen' not in _themed().SPECS or 'glen' not in _worlds(item):
        return item
    name=item.get('name')
    if name not in GLEN_SCORE_SEEDS:
        return item
    if item.get('type')!='seed' or _worlds(item)!={'glen'}:
        raise ValueError('A Glen ordinary harvest-score owner requires review.')
    if 'harvestYield' not in item:
        return item  # Already projected; ordinary coin/XP yields are independent.
    expected={'className':'QuestRewardHarvestYield','type':'world_score',
              'unit':'pixie','value':'2','class':name,'phylum':'harvest'}
    if item['harvestYield']!=expected:
        raise ValueError('A Glen ordinary harvest-score reward requires review.')
    result=copy.deepcopy(item)
    result.pop('harvestYield')
    return result


def item_projection(item):
    """Return the original item or a copied, narrowly gated client record."""
    item=_without_glen_harvest_score(item)
    themed = _themed()
    owners = _worlds(item)
    worldless_features = {world for world in themed.SPECS
        if (themed._world_feature(item, world) or {}).get('worldless')}
    if not owners and worldless_features:
        result = copy.deepcopy(item)
        result['requirements'] = {'compare': 'any', 'requirement': [
            {'className': 'World', 'name': world, 'strict': 'true'}
            for world in sorted(LEGACY_WORLDS | worldless_features)]}
        return result
    themed_owners = owners & set(themed.SPECS)
    if themed_owners and not _is_land(item):
        admitted = {world for world in themed_owners if item.get('name') in _admissions()[world]}
        if admitted and admitted != themed_owners:
            raise ValueError('A mixed themed Market admission requires review.')
        if not admitted:
            result = copy.deepcopy(item)
            if owners <= set(themed.SPECS):
                result['buyable'] = 'false' if isinstance(item.get('buyable'),str) else False
            else:
                compare = next((node['compare'] for node in themed.creative_worlds._nodes(item.get('requirements')) if 'compare' in node),None)
                if compare != 'any':
                    raise ValueError('A legacy mixed-world Market requirement requires review.')
                result['requirements'] = _trim_worlds(item['requirements'],themed_owners)
            return result
    if (not owners and item.get('type') == 'building' and item.get('className') == 'StorageBuilding'
            and (item.get('storageType') or {}).get('itemClass') == 'Inventory'
            and item.get('requirements') in themed.NONE_VALUES
            and all(item.get('name') in names for names in _admissions().values())):
        result = copy.deepcopy(item)
        result['requirements'] = {'compare':'any','requirement':[
            {'className':'World','name':world,'strict':'true'} for world in sorted(supported_worlds())]}
        return result
    return item


def _without_htown_progress(node, source):
    """Remove only the unsupported Htown map invitation; retain Hallow."""
    original=source.findall("actionMenuConfig/button[@name='WorldProgress']")
    if len(original)!=1 or original[0].findtext('action/popupClass')!='Widgets.Windows.WorldProgressWindow':
        raise ValueError('The original Htown WorldProgress invitation requires review.')
    found=node.findall("actionMenuConfig/button[@name='WorldProgress']")
    if found:
        if len(found)!=1 or ET.tostring(found[0])!=ET.tostring(original[0]):
            raise ValueError('The Htown WorldProgress invitation changed.')
        node.find('actionMenuConfig').remove(found[0])
    expected=copy.deepcopy(source)
    expected.find('actionMenuConfig').remove(expected.find("actionMenuConfig/button[@name='WorldProgress']"))
    return expected


@lru_cache(maxsize=2)
def world_settings_payload(base_payload=None):
    """Compose after October's Home-only projection; alter only11 themed HUDs.

    All non-Home nodes must match the immutable original, except for an already
    identical class-lock node (idempotence). Home is preserved verbatim decoded.
    """
    raw = WORLD_SETTINGS_SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != WORLD_SETTINGS_SHA256:
        raise ValueError('The themed Market world settings require review.')
    original = ET.fromstring(zlib.decompress(raw))
    root = ET.fromstring(zlib.decompress(raw if base_payload is None else base_payload))
    if root.tag != original.tag or root.attrib != original.attrib or len(root) != len(original):
        raise ValueError('The themed Market world-settings schema changed.')
    themed_worlds = set(_themed().SPECS)
    seen = set()
    for node,source in zip(root,original):
        name = node.get('name')
        if name != source.get('name'):
            raise ValueError('The themed Market world roster changed.')
        if name == 'farm':continue  # Caller owns the existing October projection.
        if name in themed_worlds:
            hud = node.find('hudSkinConfig')
            if hud is None:raise ValueError('A themed Market HUD is missing.')
            locks = hud.findall('showOnlyWorldMarketClassLock')
            if locks:
                if len(locks)!=1 or [x.text or '' for x in locks[0]] != list(class_locks()):
                    raise ValueError('A themed Market class lock requires review.')
                hud.remove(locks[0])
            expected=_without_htown_progress(node,source) if name=='htown' else source
            if ET.tostring(node) != ET.tostring(expected):
                raise ValueError('An original themed Market world configuration changed.')
            lock = ET.SubElement(hud,'showOnlyWorldMarketClassLock')
            for class_name in class_locks():ET.SubElement(lock,'className').text=class_name
            seen.add(name)
        elif ET.tostring(node) != ET.tostring(source):
            raise ValueError('An unrelated legacy Market world configuration changed.')
    if seen != themed_worlds:raise ValueError('The themed Market HUD roster is incomplete.')
    return zlib.compress(ET.tostring(root,encoding='utf-8',xml_declaration=True))
