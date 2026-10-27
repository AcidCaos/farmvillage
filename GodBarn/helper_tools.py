"""Recovered collection and quest helpers for detached save copies.

Collection ownership is player.collectionCounters[itemCode]. Collection levels
and storedCollections are trade-in ledgers, never altered by filling a set.
Quest completion changes one recorded progress value and leaves reward claiming
and quest-chain transitions to the game. No game, clock, I/O or network imports.
"""

from __future__ import annotations

import copy
import math


MAX_COUNTER = 2_147_483_647
COLLECTION_TYPES = frozenset({"permanent", "LE", "slotmachine"})
RARITIES = {"common": 3, "uncommon": 2, "rare": 1}
COLLECTION_LABELS = {
    "leset_vineyard_collection": "Vineyard Collection",
    "leset_fairygarden_collection": "Fairy Garden Collection",
    "leset_lighthousecove_collection": "Lighthouse Cove Collection",
    "leset_lighthousecove2_collection": "Lighthouse Cove Collection — Set 2",
    "leset_halloween_collection": "Halloween Collection",
    "leset_halloween2_collection": "Halloween Collection — Set 2",
    "leset_halloween3_collection": "Halloween Collection — Set 3",
    "leset_halloween4_collection": "Halloween Collection — Set 4",
    "leset_fairyhollow1_collection": "Fairy Hollow Collection — Set 1",
    "leset_fairyhollow2_collection": "Fairy Hollow Collection — Set 2",
    "leset_autumn_collection": "Autumn Collection",
    "leset_winterholiday_collection": "Winter Holiday Collection",
    "leset_winterholiday2_collection": "Winter Holiday Collection — Set 2",
    "leset_winterholiday3_collection": "Winter Holiday Collection — Set 3",
    "leset_winterholiday4_collection": "Winter Holiday Collection — Set 4",
    "leset_winterholiday5_collection": "Winter Holiday Collection — Set 5",
    "leset_newyear_collection": "New Year Collection",
    "leset_Vday_collection": "Valentine's Day Collection",
    "leset_Vday2_collection": "Valentine's Day Collection — Set 2",
}


def collection_display_name(name, label=None):
    """Readable theme labels for sets whose archived locale has no name."""
    if isinstance(label, str) and label.strip() and label != "Collection":
        return label
    return COLLECTION_LABELS.get(name, "Collection")


def _integer(value, label, *, minimum=0, maximum=MAX_COUNTER):
    try:
        valid = (not isinstance(value, bool) and isinstance(value, (int, float))
                 and math.isfinite(value) and value == int(value)
                 and minimum <= value <= maximum)
    except (ValueError, OverflowError):
        valid = False
    if not valid:
        raise ValueError(f"{label} must be a whole number from {minimum:,} to {maximum:,}.")
    return int(value)


class HelperTools:
    def __init__(self, catalog, definitions=None):
        self.catalog = catalog
        self.by_code = {}
        for item in catalog.values():
            if isinstance(item.get("code"), str):
                self.by_code.setdefault(item["code"], item)
        definitions = definitions if isinstance(definitions, dict) else {}
        self.source = copy.deepcopy(definitions.get("source", {}))
        self.collections, self.quests = {}, {}
        for target, key in ((self.collections, "collections"), (self.quests, "quests")):
            entries = definitions.get(key, [])
            if isinstance(entries, list):
                for entry in entries:
                    if isinstance(entry, dict) and isinstance(entry.get("name"), str) and entry["name"]:
                        target.setdefault(entry["name"], copy.deepcopy(entry))

    def _collection_row(self, save, definition):
        player = save["userInfo"]["player"]
        name = definition["name"]
        row = {"kind": "collection", "id": name, "name": name,
               "displayName": collection_display_name(name, definition.get("displayName")),
               "image": definition.get("image"),
               "description": definition.get("description") or "",
               "collectionType": definition.get("type"), "items": [],
               "supported": True, "reason": "", "level": 0, "claimed": False, "stored": False}
        try:
            if definition.get("type") not in COLLECTION_TYPES:
                raise ValueError("This collection uses breeding or fishing feature state; filling it is not supported.")
            counters = player.get("collectionCounters")
            levels = player.get("collectionLevels")
            if counters is not None and not isinstance(counters, dict):
                raise ValueError("The copied collection counters are malformed.")
            if levels is not None and not isinstance(levels, dict):
                raise ValueError("The copied collection levels are malformed.")
            stored = player.get("storedCollections")
            if definition["type"] != "permanent":
                if stored is not None and not isinstance(stored, dict):
                    raise ValueError("The copied stored collection ledger is malformed.")
                row["claimed"] = definition.get("code") in (stored or {})
                row["stored"] = row["claimed"]
            counters, levels = counters or {}, levels or {}
            row["level"] = _integer(levels.get(name, 0), "Collection level")
            entries = definition.get("items")
            if not isinstance(entries, list) or not entries:
                raise ValueError("No collectible requirements were recovered for this collection.")
            seen = set()
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get("code"), str) or not entry["code"]:
                    raise ValueError("This collection has no supported collectible item codes.")
                code = entry["code"]
                if code in seen:
                    raise ValueError("The recovered collection has duplicate collectible item codes.")
                seen.add(code)
                item = self.by_code.get(code, {})
                required = 1
                if definition["type"] == "permanent":
                    explicit = _integer(entry.get("numneeded", 0), "Collectible requirement")
                    if explicit:
                        required = explicit
                    else:
                        rarity = entry.get("rarity")
                        if rarity not in RARITIES:
                            raise ValueError("The recovered collectible rarity is unsupported.")
                        required = _integer(RARITIES[rarity] * (row["level"] + 1), "Collectible requirement")
                count = _integer(counters.get(code, 0), "Owned collectibles")
                row["items"].append({"code": code, "name": item.get("name") or code,
                                     "displayName": item.get("displayName") or entry.get("displayName") or "Collectible piece",
                                     "image": item.get("image"), "rarity": entry.get("rarity"),
                                     "count": count, "required": required,
                                     "missing": max(0, required - count), "completed": count >= required})
        except ValueError as error:
            row.update(supported=False, reason=str(error))
        row["itemCount"] = len(row["items"])
        row["total"] = sum(item["required"] for item in row["items"])
        row["missing"] = sum(item["missing"] for item in row["items"])
        row["missingItems"] = sum(not item["completed"] for item in row["items"])
        row["completed"] = row["supported"] and row["missing"] == 0
        if row["claimed"]:
            row.update(supported=False, completed=True,
                       reason="This limited collection is already recorded in the stored collection ledger.")
        return row

    def _quest_row(self, save, name, state):
        definition = self.quests.get(name)
        row = {"kind": "quest", "id": name, "name": name, "status": "active",
               "displayName": (definition or {}).get("displayName") or "Quest details unavailable",
               "image": (definition or {}).get("image"),
               "description": (definition or {}).get("description") or "",
               "tasks": [], "supported": True, "reason": "", "completed": False}
        try:
            if definition is None:
                raise ValueError("This active quest has no recovered definition; its saved state is kept unchanged.")
            tasks = definition.get("tasks")
            if not isinstance(tasks, list) or not tasks:
                raise ValueError("No task requirements were recovered for this active quest.")
            progress = state.get("progress") if isinstance(state, dict) else None
            if not isinstance(progress, list) or len(progress) != len(tasks):
                raise ValueError("The copied quest progress does not match its recovered tasks.")
            for index, (task, value) in enumerate(zip(tasks, progress)):
                if not isinstance(task, dict):
                    raise ValueError("The recovered quest task is malformed.")
                required = _integer(task.get("total"), "Quest task requirement")
                count = _integer(value, "Quest task progress")
                level = _integer(task.get("level", 0), "Quest mastery requirement")
                if task.get("action") == "getMasteryLevelByCode" and level > 0:
                    # The recovered server synchronizes this save-derived task
                    # from its zero-based mastery ledger on every quest response.
                    mastery = save["userInfo"]["player"].get("mastery")
                    if isinstance(mastery, dict):
                        tier = mastery.get(task.get("type"), -1)
                        try:
                            tier = _integer(tier, "Stored mastery tier", minimum=-1)
                            if tier + 1 >= level:
                                count = max(count, required)
                        except ValueError:
                            pass
                item = self.by_code.get(task.get("type"), {})
                row["tasks"].append({"id": index, "index": index,
                                     "displayName": task.get("displayName") or self._task_label(task, item),
                                     "action": task.get("action"), "type": task.get("type"),
                                     "image": item.get("image"), "count": count, "required": required,
                                     "remaining": max(0, required - count), "completed": count >= required,
                                     "supported": True, "reason": ""})
        except ValueError as error:
            row.update(supported=False, reason=str(error))
            for task in row["tasks"]:
                task.update(supported=False, reason=str(error))
        row["completed"] = row["supported"] and all(task["completed"] for task in row["tasks"])
        row["remaining"] = sum(task["remaining"] for task in row["tasks"])
        if row["completed"]:
            row["reason"] = "All tasks are ready. Return to the game to claim rewards and continue the quest chain."
        return row

    @staticmethod
    def _task_label(task, item):
        action = task.get("action")
        label = item.get("displayName")
        if action == "getMasteryLevelByCode" and isinstance(task.get("level"), int) and task["level"] > 0:
            return f"Master {label} to level {task['level']}" if label else f"Reach crop mastery level {task['level']}"
        if label:
            verb = {"plantCropByCode": "Plant", "harvestByCode": "Harvest", "buyItemByCode": "Buy",
                    "useItemByCode": "Use", "getMasteryLevelByCode": "Reach crop mastery for"}.get(action)
            if verb:
                return f"{verb} {label}"
        return {"plowPlot": "Plow plots", "plantCropByCode": "Plant crops", "harvestByCode": "Harvest crops",
                "buyItemByCode": "Buy farm items", "useItemByCode": "Collect the quest items",
                "viewDialog": "Read the quest dialog", "viewSeenFlag": "View the quest dialog",
                "viewseenflag": "View the quest dialog",
                "getMasteryLevelByCode": "Reach the required crop mastery",
                "getMasteryLevelByCategory": "Reach the required crop mastery",
                "makeRecipeByCode": "Craft the required recipe", "makeRecipeByCategory": "Craft the required recipes",
                "completeFeatureCraftingNPC": "Complete the crafting orders",
                "harvestFeatureCraftingStationByRecipe": "Complete the crafting recipe",
                "harvestByCategory": "Harvest the required crops",
                "harvestBySubtype": "Harvest the required crops"}.get(action, "Complete this quest task")

    def page(self, save, *, kind="all", q="", status="all", page=1, limit=30,
             include_background=False, include_unsupported=False):
        if kind not in ("all", "collection", "quest"):
            raise ValueError("Helper kind must be all, collection, or quest.")
        if status not in ("all", "incomplete", "complete"):
            raise ValueError("Helper status must be all, incomplete, or complete.")
        if not isinstance(q, str) or len(q) > 200:
            raise ValueError("Helper search must be text of at most 200 characters.")
        if not isinstance(include_background, bool):
            raise ValueError("Background quest visibility must be on or off.")
        if not isinstance(include_unsupported, bool):
            raise ValueError("Unsupported collection visibility must be on or off.")
        page = _integer(page, "Helper page", minimum=1)
        limit = _integer(limit, "Helper page size", minimum=1, maximum=100)
        hidden_collections = sum(definition.get("type") not in COLLECTION_TYPES for definition in self.collections.values())
        collections = [self._collection_row(save, definition) for definition in self.collections.values()
                       if include_unsupported or definition.get("type") in COLLECTION_TYPES]
        quest_state = save.get("questState")
        active = quest_state.get("active") if isinstance(quest_state, dict) else None
        quest_reason = ""
        if quest_state is not None and not isinstance(active, dict):
            quest_reason = "The copied active quest state is malformed."
        def is_background(name):
            definition = self.quests.get(name, {})
            if "background" in definition:
                return definition["background"] is True
            return definition.get("icon") == "none" and (
                (definition.get("ignoreSlotLimit") is True and definition.get("rewardView") == "none")
                or not definition.get("hasLocalizedTitle", bool(definition.get("displayName"))))
        background = {name for name in active or {} if is_background(name)} if isinstance(active, dict) else set()
        quests = [self._quest_row(save, name, state) for name, state in (active or {}).items()
                  if include_background or name not in background] if isinstance(active, dict) else []
        rows = collections + quests if kind == "all" else collections if kind == "collection" else quests
        totals = {"collections": len(collections), "quests": len(quests), "available": len(rows),
                  "complete": sum(row["completed"] for row in rows),
                  "incomplete": sum(not row["completed"] for row in rows),
                  "supportedIncomplete": sum(row["supported"] and not row["completed"] for row in rows),
                  "readonlyIncomplete": sum(not row["supported"] and not row["completed"] for row in rows),
                  "hiddenQuests": 0 if include_background else len(background),
                  "hiddenCollections": 0 if include_unsupported else hidden_collections,
                  "unsupported": sum(not row["supported"] for row in rows)}
        rows.sort(key=lambda row: (row["completed"], not row["supported"], row["displayName"].casefold(), row["id"]))
        needle = q.strip().casefold()
        if needle:
            rows = [row for row in rows if needle in " ".join(str(row.get(key, "")) for key in ("name", "displayName", "description")).casefold()
                    or any(needle in str(item.get("displayName", "")).casefold() for item in row.get("items", row.get("tasks", [])))]
        if status != "all":
            rows = [row for row in rows if row["completed"] == (status == "complete")]
        total = len(rows)
        pages = max(1, math.ceil(total / limit))
        page = min(page, pages)
        return {"items": rows[(page - 1) * limit:page * limit], "total": total,
                "page": page, "pages": pages, "limit": limit, "totals": totals,
                "counts": {"collection": len(collections), "quest": len(quests)},
                "available": bool(self.collections or self.quests), "reason": quest_reason,
                "source": copy.deepcopy(self.source)}

    def fill_collection(self, save, op, warnings):
        if op.get("action") != "fill":
            raise ValueError("Collection action must be fill.")
        name = op.get("name")
        if not isinstance(name, str) or name not in self.collections:
            raise ValueError("Choose a collection from the recovered collection list.")
        row = self._collection_row(save, self.collections[name])
        if not row["supported"]:
            raise ValueError(row["reason"])
        player = save["userInfo"]["player"]
        if row["missing"]:
            if player.get("collectionCounters") is None:
                player["collectionCounters"] = {}
            counters = player["collectionCounters"]
            for item in row["items"]:
                if item["missing"]:
                    counters[item["code"]] = item["required"]
        warnings.append("Only missing pieces are added. Collection levels, saved sets and reward balances are unchanged. Collection reward claiming is not implemented by this helper.")
        return f"Filled {row['missing']:,} missing collectible{'s' if row['missing'] != 1 else ''} in {row['displayName']}."

    def finish_quest_task(self, save, op, warnings):
        name = op.get("name")
        quest_state = save.get("questState")
        active = quest_state.get("active") if isinstance(quest_state, dict) else None
        if not isinstance(name, str) or not isinstance(active, dict) or name not in active:
            raise ValueError("Choose a task from an active quest in this copied save.")
        row = self._quest_row(save, name, active[name])
        if not row["supported"]:
            raise ValueError(row["reason"])
        index = _integer(op.get("task"), "Quest task index", maximum=len(row["tasks"]) - 1)
        task = row["tasks"][index]
        if not task["completed"]:
            active[name]["progress"][index] = task["required"]
        warnings.append("Only this task's progress is completed. No Farm Cash is charged and no quest rewards are granted; return to the game to claim the quest and continue its chain.")
        return f"Finished task {index + 1} of {row['displayName']}: {task['displayName']}."
