"""Static derived presentation gates for the eleven basic themed farm contracts.

Keep all authored score-unit definitions and quest rewards. Only expansion
score IDs and ordinary global transaction tasks for these worlds are projected
out; trusted Home quest score rewards still address their original unit tracks.
The archive, saved farms, prices and activated-world roster are never changed.
"""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zlib

import pyamf
from bundle import XML_DIR

SETTINGS_SOURCE = Path(XML_DIR) / 'gz/v855098/gameSettings.xml.gz'
SCORE_SOURCE = Path(XML_DIR) / 'gz/v855098/worldScore.amf.gz'
CMS_SOURCE = Path(XML_DIR) / 'gz/v855098/gameSettingsCMS.xml.gz'
SETTINGS_SHA256 = 'c1fa55f130c4942ea978b07168b37285389d36e30fce30fc30647deff5e5e11b'
SCORE_SHA256 = '4a69109bc466f6881a0435d6f89f5089f6c99c9e801c6fc85cb75f0c9c2a5048'
WORLD_SCORE_UNITS = {
    'rainforest': 'rainforestPoints', 'mediterranean': 'rivieraPoints',
    'storybook': 'storybookPoints', 'candy': 'candyPoints', 'oasis': 'oasisPoints',
    'oz': 'rainbowPoints', 'toyland': 'toylandPoints',
    'sleepyhollow': 'sleepyhollowPoints', 'australia': 'aussie',
    'fforest': 'fforestPoints', 'htown': 'cheer', 'atlantis': 'shell', 'glen': 'pixie', 'hlights': 'lightPoints',
}
BEAT_GATES = {
    'rainforest': ('beatRainForest', 'fv_beat_rainforest', 2),
    'mediterranean': ('beatMediterranean', 'fv_beat_mediterranean', 2),
    'storybook': ('beatStorybook', 'fv_xsb_beat', 2),
    'candy': ('beatCandy', 'fv_beat_candy', 2),
    'oasis': ('beatOasis', 'fv_beat_oasis', 2),
    'oz': ('beatOz', 'fv_beat_oz', 2),
    'toyland': ('beatToyland', 'fv_xtl_beat', 2),
    'sleepyhollow': ('beatSleepyhollow', 'fv_xsh_beat', 2),
    'australia': ('beatAustralia', 'fv_beat_australia', 1),
    'fforest': ('beatFforest', 'fv_beat_fforest', 2),
    'htown': ('beatHolidayTown', 'fv_beat_holiday_town', 2),
    'atlantis': ('beatAtlantis', 'fv_beat_atlantis', 1),
    'glen': ('beatEnchantedGlen', 'fv_beat_enchanted_glen', 1),
    'hlights': ('beatHlights', 'fv_beat_hlights', 2),
}
BEAT_EXPERIMENTS = {gate: 0 for _, gate, _ in BEAT_GATES.values()}
GLOBAL_TASK_COUNT = 161
BLOCKED_GLOBAL_TASK_COUNT = 42


def _specs():
    from themed_worlds import SPECS
    if set(SPECS) != set(WORLD_SCORE_UNITS):
        raise ValueError('The themed basic presentation roster requires review.')
    return SPECS


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def policy_digest():
    digest = hashlib.sha256()
    for raw in (Path(__file__).read_bytes(), json.dumps(_specs(), sort_keys=True).encode(),
                SETTINGS_SOURCE.read_bytes(), SCORE_SOURCE.read_bytes(), CMS_SOURCE.read_bytes()):
        digest.update(len(raw).to_bytes(8, 'big')); digest.update(raw)
    return digest.hexdigest()


def beat_experiment_overrides():
    """Use each existing CMS invitation prerequisite, preserving master gates."""
    _specs()
    root = ET.fromstring(zlib.decompress(CMS_SOURCE.read_bytes()))
    for world, (name, experiment, variant) in BEAT_GATES.items():
        candidates = [node for node in root.iter('prereq') if node.get('name') == name]
        if len(candidates) != 1:
            raise ValueError('An original themed Beat invitation gate changed.')
        locations = {node.get('value') for node in candidates[0].iter('prereq') if node.get('type') == 'location'}
        experiments = {(node.get('value'), node.get('variant')) for node in candidates[0].iter('prereq') if node.get('type') == 'experiment'}
        if locations != {world} or experiments != {(experiment, str(variant))}:
            raise ValueError('The original themed Beat invitation conditions changed.')
    return dict(BEAT_EXPERIMENTS)


@lru_cache(maxsize=2)
def game_settings_payload(raw=None):
    """Omit only the eleven expansion score/score2 IDs, independently of session."""
    _specs()
    if raw is None:
        raw = SETTINGS_SOURCE.read_bytes()
    if _digest(raw) != SETTINGS_SHA256:
        raise ValueError('The original themed world settings require review.')
    root = ET.fromstring(zlib.decompress(raw))
    seen = set()
    for node in root.findall('expansions/expansion'):
        name = node.get('name')
        if name not in WORLD_SCORE_UNITS:
            continue
        if name in seen or node.get('score') != WORLD_SCORE_UNITS[name] or node.get('score2'):
            raise ValueError('A themed expansion score identity changed.')
        seen.add(name)
        node.attrib.pop('score', None); node.attrib.pop('score2', None)
    if seen != set(WORLD_SCORE_UNITS):
        raise ValueError('The themed expansion score roster is incomplete.')
    # scoreFile stays: legacy loaders and Home quest rewards retain every track.
    return zlib.compress(ET.tostring(root, encoding='utf-8', xml_declaration=True))


def blocked_global_task(task):
    """Only transaction task rows wholly rewarding one of the eleven units."""
    rewards = (task.get('rewards') or {}).get('reward', [])
    rewards = rewards if isinstance(rewards, list) else [rewards]
    units = frozenset(WORLD_SCORE_UNITS.values())
    matched = [r for r in rewards if isinstance(r, dict) and r.get('type') == 'world_score' and r.get('unit') in units]
    if not matched:
        return False
    if len(matched) != len(rewards) or task.get('action') not in (
            'buyItemByCategory', 'plantCropByCategory', 'getMasteryLevelByCategory'):
        raise ValueError('A themed global score task requires review.')
    return True


@lru_cache(maxsize=2)
def world_score_payload(raw=None):
    """Remove37 global automatic tasks; preserve all tracks/levels/quest rewards."""
    _specs()
    if raw is None:
        raw = SCORE_SOURCE.read_bytes()
    if _digest(raw) != SCORE_SHA256:
        raise ValueError('The original global world-score tasks require review.')
    document = pyamf.get_decoder(pyamf.AMF3, zlib.decompress(raw)).readElement()
    global_score = document['worldScoreGlobal']['scores']['score']
    tasks = global_score['task']
    if global_score.get('id') != 'global' or not isinstance(tasks, list) or len(tasks) != GLOBAL_TASK_COUNT:
        raise ValueError('The original global score task roster changed.')
    retained = [task for task in tasks if not blocked_global_task(task)]
    if len(tasks) - len(retained) != BLOCKED_GLOBAL_TASK_COUNT:
        raise ValueError('The themed automatic score task count changed.')
    global_score['task'] = retained
    return zlib.compress(pyamf.encode(document, encoding=pyamf.AMF3).getvalue())
