"""Dormant Farm Cash conversion for world-currency-only themed items.

Deliberate deviation, documented in macOS/Documentation/Worlds/WORLD_CURRENCY_CONVERSION.md:
an item whose only recovered price is a world currency is charged Farm Cash
instead, at the rate of that currency's smallest archived exchange pack. Items
already priced in coins or Farm Cash keep their original price. Coins have no
recovered rate, so coins are never converted. Nothing here is wired into
travel, the market, or the served catalog; world activation stays a parent
decision.
"""
import copy
import re

EXCHANGE_TYPE = "currency_exchange"
ORIGINAL_MARKETS = frozenset(("cash", "coins"))
# World-currency markets used by catalog items with a World requirement.
# Hawaii (coconuts) and Farmer's Square (villageCoins) are listed for audit
# only; their dormant rule modules and plot limits keep their own decisions.
WORLD_CURRENCY_WORLDS = {"asia": "jade", "hawaii": "coconuts", "village": "villageCoins"}
# Plowing is priced in the world currency in these expansions (gameSettings).
PLOW_PRICES = {"asia": {"plowCost": 15, "plowCurrency": "jade"},
               "hawaii": {"plowCost": 15, "plowCurrency": "coconuts"}}


def _whole(value, name="value"):
    text = str(value).strip() if value is not None else ""
    if not re.fullmatch(r"[0-9]+", text):
        raise ValueError(f"The recovered {name} is not a whole number.")
    return int(text)


def _world_names(requirements):
    names = []
    def walk(node):
        if isinstance(node, dict):
            if node.get("className") == "World" and node.get("name"):
                names.append(node["name"])
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)
    walk(requirements)
    return names


def recovered_rates(catalog):
    """Return {currency: {cash, units, pack}} from archived exchange packs.

    The smallest cash price of each currency is its base pack. Every pack at
    that price must grant the same units, or the rate is ambiguous and the
    whole derivation fails closed.
    """
    packs = {}
    for item in catalog:
        if item.get("type") != EXCHANGE_TYPE:
            continue
        currency = item.get("subtype")
        if not currency:
            raise ValueError("An exchange pack has no recovered currency.")
        cash = _whole(item.get("cash"), "pack cash")
        units = _whole(item.get("count"), "pack units")
        if cash <= 0 or units <= 0:
            raise ValueError("An exchange pack has a non-positive recovered amount.")
        packs.setdefault(currency, []).append((cash, units, item["name"]))
    rates = {}
    for currency, entries in packs.items():
        base_cash = min(cash for cash, _, _ in entries)
        base = [(units, name) for cash, units, name in entries if cash == base_cash]
        if len({units for units, _ in base}) != 1:
            raise ValueError(f"The {currency} base exchange rate is ambiguous.")
        rates[currency] = {"cash": base_cash, "units": base[0][0],
                           "pack": min(name for _, name in base)}
    return rates


def farm_cash_for(amount, rate):
    """Exact ceiling of amount * cash / units, without floating-point drift."""
    amount = _whole(amount, "price")
    return -(-amount * rate["cash"] // rate["units"])


def price_for_item(item, rates):
    """Return the charge, or None for items priced only in coins or not marketed.

    An item already carrying a Farm Cash price keeps it (converted False).
    Unknown market currencies raise, so they can never be charged silently.
    """
    market = item.get("market")
    if market is None or market in ORIGINAL_MARKETS:
        return None
    if market not in rates:
        raise ValueError(f"The {market} currency has no recovered conversion rate.")
    if item.get("cash") not in (None, ""):
        return {"currency": "cash", "amount": _whole(item["cash"], "cash price"),
                "converted": False}
    if item.get("cost") in (None, ""):
        raise ValueError("A world-currency item has no recovered price.")
    cost = _whole(item["cost"], "price")
    rate = rates[market]
    return {"currency": "cash", "amount": farm_cash_for(cost, rate), "converted": True,
            "source": {"currency": market, "amount": cost, "packCash": rate["cash"],
                       "packUnits": rate["units"], "pack": rate["pack"]}}


def world_items(catalog, world):
    """Items whose World requirement names exactly this world."""
    return [item for item in catalog if world in _world_names(item.get("requirements"))]


def conversion_audit(catalog, world, rates):
    """Audit records for one themed world; original prices stay in each record.

    Items that cannot be priced (no recovered price, or an unknown currency)
    are listed as unpriced so the caller can refuse them; they are never charged.
    """
    records = []
    for item in world_items(catalog, world):
        try:
            result = price_for_item(item, rates)
        except ValueError as error:
            records.append({"name": item["name"], "type": item.get("type"),
                            "unpriced": str(error)})
            continue
        if result is not None:
            records.append({"name": item["name"], "type": item.get("type"), **result})
    return records


def served_item(item, rates):
    """A copy that a themed world could serve with its Farm Cash price (dormant)."""
    charge = price_for_item(item, rates)
    if charge is None or not charge["converted"]:
        return item
    served = copy.deepcopy(item)
    served["market"] = "cash"
    served["cash"] = str(charge["amount"])
    return served


def plow_charge(world, rates):
    """Farm Cash for one plow in a themed world, if its plow currency is recovered."""
    price = PLOW_PRICES.get(world)
    if price is None:
        raise ValueError("This world's plow price is not recovered.")
    currency = price["plowCurrency"]
    if currency not in rates:
        raise ValueError(f"The {currency} currency has no recovered conversion rate.")
    return farm_cash_for(price["plowCost"], rates[currency])
