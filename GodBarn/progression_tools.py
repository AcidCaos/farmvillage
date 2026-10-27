"""Read and advance recovered ribbon/mastery tracks on detached save copies.

The saved tier is the reward ledger, just as in FarmVillage.progression. Counts
may advance, but an already earned tier never pays a second time. No game,
filesystem, network, or clock dependencies are used here.
"""

from __future__ import annotations

import copy
import math


MAX_COUNTER = 2_147_483_647
RIBBON_COLORS = ("Yellow", "White", "Red", "Blue")


def _list(value):
    return value if isinstance(value, list) else ([] if value is None else [value])


def _integer(value, label, *, minimum=0, maximum=MAX_COUNTER):
    try:
        finite = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        finite = False
    if (not finite or value != int(value)
            or value < minimum or value > maximum):
        raise ValueError(f"{label} must be a whole number from {minimum:,} to {maximum:,}.")
    return int(value)


def _stored_integer(value, default):
    if value is None:
        return default, True
    if isinstance(value, bool):
        return default, False
    try:
        number = int(value)
        if str(number) != str(value) and number != value:
            return default, False
        return number, True
    except (TypeError, ValueError, OverflowError):
        return default, False


def _maps(save, kind):
    player = save["userInfo"]["player"]
    counter_key, level_key = (("masteryCounters", "mastery") if kind == "mastery"
                              else ("achCounters", "achievements"))
    return tuple(player.get(key) if isinstance(player.get(key), dict) else {} for key in (counter_key, level_key))


class ProgressionTools:
    def __init__(self, catalog, definitions=None):
        self.catalog = catalog
        definitions = definitions if isinstance(definitions, dict) else {}
        self.source = copy.deepcopy(definitions.get("source", {}))
        self.tracks = {"mastery": {}, "ribbon": {}}
        # Generated canonical names preserve the original first-by-code lookup.
        # A small custom/test catalog can omit the generated name list.
        names = definitions.get("masteryItems")
        masteries = (catalog.get(name) for name in names if isinstance(name, str)) if isinstance(names, list) else catalog.values()
        for item in masteries:
            if (not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item.get("masteryLevel")
                    or str(item.get("mastery", "true")).lower() != "true"):
                continue
            code = item.get("code")
            if not isinstance(code, str) or not code or code == "XX":
                continue
            self.tracks["mastery"].setdefault(code, {
                "kind": "mastery", "code": code, "name": item["name"],
                "displayName": item.get("displayName") or item["name"].replace("_", " ").title(),
                "itemType": item.get("type"), "type": item.get("type"), "image": item.get("image"),
                "labelSource": item.get("labelSource"), "artwork": copy.deepcopy(item.get("artwork")),
                "hasOriginalThumbnail": item.get("hasOriginalThumbnail"),
                "description": "Cumulative mastery points earned from harvests.",
                "counterSource": "cumulative", "levels": self._levels(item["masteryLevel"]),
            })
        for definition in _list(definitions.get("ribbons")):
            if not isinstance(definition, dict) or definition.get("disabled") is True:
                continue
            code, name = definition.get("code"), definition.get("name")
            if not isinstance(code, str) or not isinstance(name, str):
                continue
            self.tracks["ribbon"].setdefault(code, {
                "kind": "ribbon", "code": code, "name": name,
                "displayName": definition.get("displayName") or name,
                "itemType": "ribbon", "image": definition.get("image"),
                "description": definition.get("description") or "Recorded ribbon counter and original tier rewards.",
                "counterSource": definition.get("counterSource", "cumulative"),
                "levels": self._levels(definition.get("levels")),
            })
        for tracks in self.tracks.values():
            for code, track in list(tracks.items()):
                if not track["levels"]:
                    del tracks[code]
        self.ordered = sorted((track for tracks in self.tracks.values() for track in tracks.values()),
                              key=lambda track: (track["kind"] != "ribbon", track["displayName"].casefold(), track["code"]))

    def _levels(self, levels):
        result = []
        try:
            for index, raw in enumerate(_list(levels)):
                values = []
                for key in ("count", "xp", "coins"):
                    value = raw.get(key, 0)
                    if value is None or value == "":
                        value = 0
                    if isinstance(value, str):
                        value = int(value) if value.isdecimal() else None
                    values.append(_integer(value, "Recovered tier " + key))
                count, xp, coins = values
                if result and count < result[-1]["count"]:
                    return []
                gift = raw.get("gift")
                item = self.catalog.get(gift, {}) if isinstance(gift, str) else {}
                gift_code = item.get("code")
                available = (isinstance(gift_code, str) and bool(gift_code) and gift_code != "XX"
                             and ":" not in gift_code and len(gift_code) <= 128)
                result.append({"tier": index + 1, "count": count, "xp": xp, "coins": coins,
                               "image": raw.get("image"),
                               "gift": gift if isinstance(gift, str) else None,
                               "giftLabel": item.get("displayName") or gift,
                               "giftAvailable": available, "giftImage": item.get("image")})
        except (ValueError, TypeError, AttributeError, OverflowError):
            return []
        return result

    def _progress(self, save, track):
        counters, earned = _maps(save, track["kind"])
        code = track["code"]
        count, count_valid = _stored_integer(counters.get(code), 0)
        difficulty, difficulty_valid = _stored_integer(earned.get(code), -1)
        player = save["userInfo"]["player"]
        keys = ("masteryCounters", "mastery") if track["kind"] == "mastery" else ("achCounters", "achievements")
        maps_valid = all(isinstance(player.get(key), dict) or player.get(key) is None or player.get(key) == [] for key in keys)
        valid = (maps_valid and count_valid and difficulty_valid and 0 <= count <= MAX_COUNTER
                 and -1 <= difficulty < len(track["levels"]))
        return count, difficulty, valid

    def totals(self, save):
        result = {}
        for kind, tracks in self.tracks.items():
            counters, earned = _maps(save, kind)
            started = completed = tiers = 0
            for code in counters.keys() | earned.keys():
                track = tracks.get(code)
                if not track:
                    continue
                count, difficulty, valid = self._progress(save, track)
                if not valid:
                    continue
                started += count > 0 or difficulty >= 0
                completed += difficulty == len(track["levels"]) - 1
                tiers += difficulty + 1
            result[kind] = {"total": len(tracks), "started": started, "completed": completed, "earnedTiers": tiers}
        return result

    def _row(self, save, track):
        count, difficulty, valid = self._progress(save, track)
        reason = None
        if not valid:
            reason = "Imported progress is outside the recovered tier format; preserved for inspection."
        elif track["counterSource"] == "ownership":
            reason = "This counter follows actual farm ownership or neighbors and is recalculated by the game."
        tiers = [{**level, "earned": difficulty >= level["tier"] - 1,
                  "label": (RIBBON_COLORS[level["tier"] - 1] if track["kind"] == "ribbon" and level["tier"] <= 4
                            else f"Star {level['tier']}")}
                 for level in track["levels"]]
        next_tier = next((tier for tier in tiers if not tier["earned"]), None)
        return {key: copy.deepcopy(value) for key, value in track.items() if key != "levels"} | {
            "count": count, "earnedTier": max(0, difficulty + 1), "maxTier": len(tiers),
            "tiers": tiers, "nextTier": next_tier,
            "remaining": max(0, next_tier["count"] - count) if next_tier else 0,
            "completed": next_tier is None and valid, "supported": reason is None,
            "controlReason": reason,
        }

    def page(self, save, *, q="", kind="all", page=1, limit=30, status="all"):
        if kind not in ("all", "mastery", "ribbon"):
            raise ValueError("Progression kind must be all, mastery, or ribbon.")
        if status not in ("all", "started", "complete", "available"):
            raise ValueError("Progression status must be all, started, complete, or available.")
        page = _integer(page, "Page", minimum=1, maximum=MAX_COUNTER)
        limit = _integer(limit, "Page size", minimum=1, maximum=120)
        if not isinstance(q, str):
            raise ValueError("Progression search must be text.")
        query = q.strip().casefold()[:200]
        tracks = []
        for track in self.ordered:
            if kind != "all" and track["kind"] != kind:
                continue
            if query and query not in " ".join(str(track.get(key) or "") for key in
                                               ("code", "name", "displayName", "itemType")).casefold():
                continue
            count, difficulty, valid = self._progress(save, track)
            complete = valid and difficulty == len(track["levels"]) - 1
            if status == "started" and (not valid or not (count > 0 or difficulty >= 0)):
                continue
            if status == "complete" and not complete:
                continue
            if status == "available" and (not valid or complete or track["counterSource"] == "ownership"):
                continue
            tracks.append(track)
        pages = max(1, math.ceil(len(tracks) / limit))
        page = min(page, pages)
        return {"items": [self._row(save, track) for track in tracks[(page - 1) * limit:page * limit]],
                "total": len(tracks), "page": page, "pages": pages, "limit": limit,
                "totals": self.totals(save), "source": copy.deepcopy(self.source)}

    def validate_advance(self, save, operation):
        kind, code = operation.get("kind"), operation.get("code")
        if not isinstance(kind, str) or kind not in self.tracks or not isinstance(code, str) or code not in self.tracks[kind]:
            raise ValueError("Choose a recovered mastery or ribbon track.")
        track = self.tracks[kind][code]
        row = self._row(save, track)
        if not row["supported"]:
            raise ValueError(row["controlReason"])
        count = _integer(operation.get("count"), "Progress count")
        if count < row["count"]:
            raise ValueError("Progress can only advance. Earned tiers and rewards cannot be revoked.")
        return track, count, row["earnedTier"] - 1

    def advance(self, save, operation, engine, now, warnings):
        track, count, difficulty = self.validate_advance(save, operation)
        kind, code = track["kind"], track["code"]
        rewards = [level for level in track["levels"] if level["tier"] - 1 > difficulty and count >= level["count"]]
        player = save["userInfo"]["player"]
        # Original rewards are never silently truncated at the Flash limit.
        xp = player["xp"] + sum(level["xp"] for level in rewards)
        coins = player["gold"] + sum(level["coins"] for level in rewards)
        cash = player["cash"] + max(0, min(engine.level_for_xp(xp), engine.cash_level_cap)
                                     - min(engine.level_for_xp(player["xp"]), engine.cash_level_cap))
        if any(value > MAX_COUNTER for value in (xp, coins, cash)):
            raise ValueError("These progression rewards exceed the Flash balance limit. Lower the balance before advancing.")
        # Validate all gifts before touching the detached save. Repeated gifts in
        # skipped tiers accumulate against one Flash inventory limit.
        gift_counts = {}
        inventory = player.get("storageData", {}).get("-1", {})
        for level in rewards:
            if not level["giftAvailable"]:
                continue
            gift_code = self.catalog[level["gift"]]["code"]
            entry = inventory.get(gift_code, [0, [], []])
            if (not isinstance(entry, list) or len(entry) != 3
                    or not isinstance(entry[1], list) or not isinstance(entry[2], list)):
                raise ValueError("The reward item's existing inventory metadata is malformed.")
            current = _integer(entry[0], "Stored reward quantity")
            gift_counts[gift_code] = gift_counts.get(gift_code, current) + 1
            if gift_counts[gift_code] > MAX_COUNTER:
                raise ValueError("The reward's Gift Box quantity exceeds the Flash limit.")
        counter_key, tier_key = (("masteryCounters", "mastery") if kind == "mastery" else ("achCounters", "achievements"))
        for key in (counter_key, tier_key):
            if not isinstance(player.get(key), dict):
                player[key] = {}
        player[counter_key][code] = count
        for level in rewards:
            engine._balance(save, {"field": "xp", "mode": "add", "amount": level["xp"]}, now, warnings)
            engine._balance(save, {"field": "gold", "mode": "add", "amount": level["coins"]}, now, warnings)
            gift = self.catalog.get(level.get("gift")) if level["giftAvailable"] else None
            if gift:
                inventory = player.setdefault("storageData", {}).setdefault("-1", {})
                entry = inventory.setdefault(gift["code"], [0, [], []])
                entry[0] += 1
            player[tier_key][code] = level["tier"] - 1
        if any(level["gift"] and not level["giftAvailable"] for level in rewards):
            warnings.append("A recorded reward item is absent from this catalog; the game skips that gift and still awards its tier.")
        warnings.append("Only newly earned tiers pay rewards. Progress controls do not replay harvests, unique item records, or quests.")
        return (f"Advanced {track['displayName']} to {count:,} points; earned {len(rewards)} "
                f"new {'star' if kind == 'mastery' else 'ribbon tier'}{'s' if len(rewards) != 1 else ''}.")
