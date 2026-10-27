"""Durable mirrors of the original client's quest score/currency rewards.

UserRewardUtil and Player.addWorldScore already award these locally. Only the
server's trusted quest completion calls add_score; the level-up transaction is
an acknowledgement and cannot award anything. This does not restore earning
points from ordinary world actions, unlock worlds, or create their inventories.
"""
import math
from functools import lru_cache
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zlib

import pyamf

from bundle import XML_DIR, TEMPLATES_DIR
from game_settings import xp_to_level
from items import get_item_by_name

_MAX_INTEGER = 9_007_199_254_740_991
_MAX_LEVEL = 999  # WorldScoreSettingsManager.getLevelForScore's level < 1000.


def _list(value):
    return value if isinstance(value, list) else ([] if value is None else [value])


def _whole(value, label):
    if (type(value) not in (int, float) or not 0 <= value <= _MAX_INTEGER
            or not math.isfinite(value) or int(value) != value):
        raise ValueError(label + " must be a supported nonnegative whole number.")
    return int(value)


@lru_cache(maxsize=1)
def _archive():
    root = Path(XML_DIR, "gz/v855098")
    data = pyamf.get_decoder(pyamf.AMF3,
        zlib.decompress((root / "worldScore.amf.gz").read_bytes())).readElement()
    tracks = {}
    for group in data.values():
        for score in _list(group["scores"]["score"]):
            unit = score["id"]
            levels = {int(level["num"]): dict(level) for level in _list(score.get("level"))}
            if unit in tracks or (levels and sorted(levels) != list(range(max(levels) + 1))):
                raise ValueError("The recovered world-score catalog requires review.")
            tracks[unit] = {**score, "levels": levels}
    cms = ET.fromstring(zlib.decompress((root / "gameSettingsCMS.xml.gz").read_bytes()))
    settings = ET.fromstring(zlib.decompress((root / "gameSettings.xml.gz").read_bytes()))
    return tracks, {n.get("name"): n for n in cms.findall(".//prereq[@name]")}, {
        n.get("name"): n for n in settings.findall(".//currency[@name]")}


def _experiments():
    # Match the variants served to this client, as themed_worlds does. This is
    # server configuration; callers cannot supply a favorable variant.
    text = Path(TEMPLATES_DIR, "play.html").read_text(encoding="utf-8")
    return {name: int(value) for name, value in re.findall(
        r'"(fv_[A-Za-z0-9_]+)":\s*(-?\d+)', text)}


def _prereq_met(save, name, experiments, visiting=frozenset()):
    if name in visiting:
        return False
    node = _archive()[1].get(name)
    if node is None:
        return False

    def child_met(child):
        kind, value = child.get("type"), child.get("value")
        if kind == "level_min":
            return (xp_to_level(save["userInfo"]["player"]["xp"]) or 1) >= int(value)
        if kind == "experiment":
            return experiments.get(value, 0) == int(child.get("variant", "1"))
        if kind == "prereq_check":
            return _prereq_met(save, value, experiments, visiting | {name})
        # Season/feature-option predicates are deliberately not guessed.
        return False

    if node.get("type") == "AND":
        return all(child_met(child) for child in node)
    if node.get("type") == "OR":
        return any(child_met(child) for child in node)
    return False


def _guard_gain_buffs(save, subtypes):
    buffs = save["userInfo"]["player"].get("buffs", {})
    if not isinstance(buffs, dict):
        raise ValueError("The imported reward buff state is invalid.")
    for name in buffs:
        item = get_item_by_name(name)
        if item is None or (item.get("className") == "BPermanentTypeGain"
                            and item.get("subtype") in subtypes):
            raise ValueError("This imported reward-gain buff is not restored.")


def world_level(save, unit):
    """Player.getWorldLevel: -1 when absent, with no implicit score unlock."""
    scores = save.get("userInfo", {}).get("player", {}).get("worldScores")
    record = scores.get(unit) if isinstance(scores, dict) and isinstance(unit, str) else None
    value = record.get("level") if isinstance(record, dict) else None
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= _MAX_LEVEL:
        return -1
    return int(value)


def _level_data(unit, level):
    track = _archive()[0][unit]
    if level in track["levels"]:
        return track["levels"][level]
    if not track["levels"] or level <= max(track["levels"]):
        return None
    # LevelData.getCalculatedLevelData: AS3 Math.round is floor(x + .5).
    required = (10.006 * level ** 2 - 48.818 * level + 16.945 if unit == "spook"
                else 19.443 * level ** 2 - 43.183 * level - 175.87)
    return {**track.get("defaultLevel", {}), "num": level,
            "required": math.floor(required + .5)}


def _level_for_score(unit, score, old_level):
    # Start at the saved level unless its threshold exceeds the new score. The
    # client never lowers the saved level in addWorldScore, even in that case.
    start = old_level
    initial = _level_data(unit, start)
    if initial is None:
        raise ValueError("This world-score track has no recovered level ladder.")
    if int(initial["required"]) > score:
        start = 0
    result = 0
    for level in range(start, _MAX_LEVEL + 1):
        row = _level_data(unit, level)
        if row is None or score < int(row["required"]):
            break
        result = int(row["num"])
    return max(old_level, result)


def add_score(save, unit, amount):
    """Add an authored quest amount and return crossed-level reward records.

    Records contain score and level plus preserved imported fields. Level 1 is
    the client's initial record and is not paid as a newly crossed level. The
    caller applies returned rewards in the same save transaction.
    """
    track = _archive()[0].get(unit) if isinstance(unit, str) else None
    if track is None:
        raise ValueError("That world-score unit is not in the recovered catalog.")
    amount = _whole(amount, "World-score reward")
    prerequisite = track.get("prereq")
    if prerequisite and not _prereq_met(save, prerequisite, _experiments()):
        # Player.addWorldScore also leaves disabled tracks unchanged.
        return []
    _guard_gain_buffs(save, {unit + "_gain"})
    player = save["userInfo"]["player"]
    scores = player.get("worldScores", {})
    if not isinstance(scores, dict):
        raise ValueError("The imported world-score state is invalid.")
    record = scores.get(unit, {"score": 0, "level": 1})
    if not isinstance(record, dict):
        raise ValueError("The imported world-score record is invalid.")
    score = _whole(record.get("score"), "Imported world score")
    old_level = _whole(record.get("level"), "Imported world-score level")
    if old_level > _MAX_LEVEL:
        raise ValueError("The imported world-score level exceeds the client scan.")
    score = _whole(score + amount, "Awarded world score")
    new_level = _level_for_score(unit, score, old_level)
    rewards = []
    for level in range(old_level + 1, new_level + 1):
        for reward in _list((_level_data(unit, level).get("rewards") or {}).get("reward")):
            rewards.append({**reward, "quantity": int(reward.get("quantity", 1))})
    if any(reward.get("type") == "coins" for reward in rewards):
        _guard_gain_buffs(save, {"coin_gain"})
    player.setdefault("worldScores", {})[unit] = {**record, "score": score, "level": new_level}
    return rewards


def add_currency(save, unit, amount):
    """UserRewardUtil's inflow tuning, then Player's balance-total update."""
    currency = _archive()[2].get(unit) if isinstance(unit, str) else None
    if currency is None:
        raise ValueError("That world currency is not in the recovered catalog.")
    amount = _whole(amount, "World-currency reward")
    buffs = {n.text.strip() for n in currency.findall("buffs/buff") if n.text}
    _guard_gain_buffs(save, buffs)
    tuning = currency.find("inflow/tuningTest")
    multiplier = 1.0
    if tuning is not None:
        variant = _experiments().get(tuning.get("experimentName"), 0)
        row = tuning.find(f"variant[@number='{variant}']")
        if row is not None:
            multiplier = float(row.get("multiplier"))
    amount = _whole(math.floor(amount * multiplier), "Tuned world-currency reward")
    player = save["userInfo"]["player"]
    currencies = player.get("worldCurrencies", {})
    if not isinstance(currencies, dict):
        raise ValueError("The imported world-currency state is invalid.")
    record = currencies.get(unit, {"total": 0})
    if not isinstance(record, dict):
        raise ValueError("The imported world-currency record is invalid.")
    total = _whole(record.get("total"), "Imported world-currency total")
    total = _whole(total + amount, "Awarded world-currency total")
    player.setdefault("worldCurrencies", {})[unit] = {**record, "total": total}


def add_content_license(save, world, license_type):
    """WorldManager.addWorldContentLicense's nested Boolean map."""
    if not isinstance(world, str) or not world or not isinstance(license_type, str) or not license_type:
        raise ValueError("The quest's world-content license is invalid.")
    user = save["userInfo"]
    licenses = user.get("unlockedWorldContentLicenses", {})
    if not isinstance(licenses, dict) or not isinstance(licenses.get(world, {}), dict):
        raise ValueError("The imported world-content licenses are invalid.")
    user.setdefault("unlockedWorldContentLicenses", {}).setdefault(world, {})[license_type] = True


def acknowledge_level_up(unit):
    """Validate the report's one argument; never accept points or pay rewards."""
    if not isinstance(unit, str) or unit not in _archive()[0]:
        raise ValueError("That world-score report has an unknown unit.")
