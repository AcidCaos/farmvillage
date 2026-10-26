"""Exact recovered Meadows land contracts; no story or score activation."""
from pathlib import Path
import re
from bundle import TEMPLATES_DIR

EXPANSION_EXPERIMENTS = {"fv_meadows_1436FC": 1, "fv_meadows_38Coin": 1,
    "fv_meadows_3844FC": 1, "fv_expansion_mw_46": 1,
    "fv_expansion_mw_48": 1, "fv_expansion_mw_50": 1}
WIDTHS = tuple(range(50, 203, 8))
COIN_PRICES = (500000, 1000000, 1500000, 2000000, 3000000, 4000000,
    2000000, 4000000, 4000000, 5000000, 6000000, 7000000, 8000000)
RAW_CASH_PRICES = (30, 40, 50, 60, 80, 100, 120, 145, 170, 195, 200,
    205, 205, 205, 220, 220, 250, 260, 280)


def expansion_contract(item):
    match = re.fullmatch(r"xmwfarm(\d+)(_cash)?", item.get("name", ""))
    if not match:
        raise ValueError("Sunflower Meadows requires its own recovered land expansions.")
    size, cash = int(match[1]), bool(match[2])
    if size not in range(14, (50 if cash else 38) + 1, 2):
        raise ValueError("This Meadows expansion variant is not recovered.")
    expected = {"type": "change_farm", "subtype": "expand_farm", "code": "XX",
        "squares": str(size * 4 + 2), "size": str(size), "buyable": "true",
        "requirements": {"requirement": {"className": "World", "name": "meadows"}}}
    if cash:
        gate = ("fv_meadows_1436FC" if size <= 36 else "fv_meadows_3844FC"
            if size <= 44 else "fv_expansion_mw_" + str(size))
        expected.update(market="cash", cash=str(RAW_CASH_PRICES[(size - 14) // 2]), experimentGate=gate)
    else:
        expected["cost"] = str(COIN_PRICES[(size - 14) // 2])
        if size == 28:
            expected["minNeighbors"] = "45"
        if size == 38:
            expected["experimentGate"] = "fv_meadows_38Coin"
    for key in ("market", "cash", "cost", "experimentGate", "minNeighbors", "requiredLevel"):
        expected.setdefault(key, "1" if key == "requiredLevel" and size >= 46 else None)
    if any(item.get(key) != value for key, value in expected.items()):
        raise ValueError("The Meadows expansion's recovered contract changed.")
    return int(expected["squares"])


def experiment_enabled(gate):
    if EXPANSION_EXPERIMENTS.get(gate) != 1:
        return False
    for page in ("play.html", "ruffle.html"):
        text = Path(TEMPLATES_DIR, page).read_text(encoding="utf-8")
        if re.findall(r'"' + re.escape(gate) + r'":\s*(-?\d+)', text) != ["1"]:
            return False
    return True


def guard_item_experiment(item):
    """Match the original gate's optional integer variant list exactly."""
    gate = item.get("experimentGate")
    # ExperimentManager ignores an orphan variant when no gate is authored.
    if gate is None or gate == "":
        return
    if (not isinstance(gate, str) or item.get("features")
            or item.get("className") not in (None, "Animal", "Tree", "Building",
                "Decoration", "RotateableDecoration", "MaskedDecoration", "GateDecoration", "StorageBuilding")):
        raise ValueError("This item's special purchase prerequisites are not restored.")
    variants = item.get("experimentVariant", "")
    values = None
    if variants != "":
        if type(variants) is int:
            values = {variants}
        elif isinstance(variants, str):
            parts = variants.split(",")
            if any(not re.fullmatch(r"(?:0|-?[1-9][0-9]*)", part) for part in parts):
                raise ValueError("This item's experiment prerequisites are invalid.")
            values = {int(part) for part in parts}
        else:
            raise ValueError("This item's experiment prerequisites are invalid.")
    served = []
    for page in ("play.html", "ruffle.html"):
        text = Path(TEMPLATES_DIR, page).read_text(encoding="utf-8")
        matches = re.findall(r'"' + re.escape(gate) + r'":\s*(-?\d+)', text)
        if len(matches) != 1:
            raise ValueError("This item's experiment prerequisites are not enabled.")
        variant = int(matches[0])
        enabled = variant in values if values is not None else variant > 0
        if not enabled:
            raise ValueError("This item's experiment prerequisites are not enabled.")
        served.append(variant)
    if served[0] != served[1]:
        raise ValueError("This item's experiment prerequisites disagree between clients.")


def guard_new_object(save, snapshot, existing):
    """The original global ceiling applies; Meadows has no bespoke plot cap."""
    if existing is not None:
        return
    from game_settings import get_farming_int
    import world_travel
    world = save["world"]
    maximum = world.get("maxNumObjects") or get_farming_int("maxNumObjects", 5000)
    if not world_travel._integer(maximum) or maximum <= 0:
        raise ValueError("The imported Meadows object limit requires recovery.")
    objects = [obj for obj in world["objectsArray"] if not obj.get("deleted")]
    if len(objects) >= maximum:
        raise ValueError("Sunflower Meadows has reached its recovered object limit.")
