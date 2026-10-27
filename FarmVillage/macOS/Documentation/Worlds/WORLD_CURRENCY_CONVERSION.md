> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../../ACCEPTANCE.md), [current world scope](../../../../WORLD_READINESS.md) and [the continuation backlog](<../../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# World currency to Farm Cash conversion (dormant)

Checked 2026-10-23. This is a **deliberate deviation** from the original game, decided by the user for new themed worlds. It is implemented only as dormant pure functions. Nothing is wired into travel, the market, plowing, the served catalog, or `SUPPORTED_WORLDS`.

Sources: `items.py` catalog cache `LocalData/cache/gz_v855038_items_opt.json`; `gameSettings` expansion records for `asia`, `hawaii` and `village`; `SWF` methods checked with the read-only disassembler (`GameMode:GMMultiPlotAction.outOfWorldCurrencyHandler`, `Classes.util:CurrencyConversionUtil.isValidCurrencyExchangeItem`, `isValidJadeExchangeItem`, `<cinit>`).

## Rule

- An item whose only price is a world currency is charged **Farm Cash** = `ceil(price x packCash / packUnits)`, using the rate below. The arithmetic is exact integer math.
- Items already priced in coins or Farm Cash keep their original price. An item that has a `cash` field in its catalog record keeps that Farm Cash price (`converted: false`).
- Coins are never converted: no coin rate is recovered. No fallback rate was needed, because every recovered world currency has an archived rate.
- Unknown world currencies, and items with no recovered price, are refused. They are never charged silently.
- Original price, source currency, amount, pack and converted charge are recorded in the audit record, so the purchase can be audited.

## Recovered rates

Each rate is the smallest archived exchange pack for that currency. All packs at that price grant the same units, so the rate is unambiguous. The 2000-unit bulk packs were not used.

| Currency | Base pack (catalog name) | Cash : units | Farm Cash per unit | Client mini-market offers it? |
| --- | --- | --- | --- | --- |
| `jade` | `jade_exchange_variant_p1` | 5 : 5000 | 1 FC per 1000 jade | Yes (`isValidJadeExchangeItem`, prefix `jade_exchange_variant`) |
| `coconuts` | `coconuts_exchange_variant1_wallet1_p1` (the same 5 : 5000 at the base price in several variants) | 5 : 5000 | 1 FC per 1000 coconuts | Yes, by the `coconuts_exchange_variant` prefix (`isValidCoconutExchangeItem`; its wallet-tier logic was not fully traced) |
| `villageCoins` | `villageCoins_exchange1` | 10 : 1000 | 1 FC per 100 villageCoins | No: `isValidCurrencyExchangeItem` has no branch for it |
| `coins` | none | none | none | Not applicable: coins are never converted |

The archived larger packs give better rates (2000 units per FC for jade and coconuts, 120 per FC for villageCoins). They are not used, so the base rate is the conservative choice. Changing the base-pack rule would change every converted price.

## Affected worlds

| World | Currency | World-tied items with that market | Converted | Keeps its existing FC price | Unpriced (refused) | Plow |
| --- | --- | --- | --- | --- | --- | --- |
| `asia` (Jade Falls) | jade | 108 | 73 (56 seeds, 15 buildings, 2 decorations) | 34 | 1 crafting cottage (`xascraftingcottageteahouse`) | 15 jade, so 1 FC per plow |
| `hawaii` (Hawaiian Paradise) | coconuts | 97 | 49 (13 seeds, 18 buildings, 11 decorations, 5 change_farm, 2 vehicles) | 47 | 1 crafting cottage (`xhicraftingcottage`) | 15 coconuts, so 1 FC per plow |
| `village` (Farmer's Square) | villageCoins | 3 | 3 | 0 | 0 | Not applicable: its only plot-limit record is 0 squares / 0 plots |

Hawaii's existing dormant `hawaii_rules.py` (coconut plow debit) was not modified and is not changed by this conversion. Hawaii's decision needs its own review.

## Consequences to decide before activation

- **Seeds:** every converted seed costs **1 FC** (asia 56 seeds, hawaii 13 seeds). The original prices were up to 410 jade and 231 coconuts.
- **Plowing (superseded 2026-10-23):** this bullet proposed 1 FC per plow. The user decided plowing stays at Home's 15 coins in every themed world; see "Plow decision" below.
- **Large items:** the highest converted charge is 1000 FC (asia, 1,000,000 jade) and 2500 FC (hawaii, 2,500,000 coconuts).
- **Zero-cost items** stay free (asia 2, hawaii 6). These are items with a zero world-currency price, and their gates still apply.

## Client behavior (SWF)

- When world currency is short, `GMMultiPlotAction.outOfWorldCurrencyHandler` reads `worldManager.getCurrencyForWorld(currentWorldType)`, queries `aide/othercurrency_exchange` items, filters them with `isValidCurrencyExchangeItem(name, currentWorldCurrency)`, and calls `displayMiniMarketDialog`. So the handler responds to a shortfall by opening the archived exchange packs (Farm Cash to world currency). It does not itself send a world-currency purchase.
- A Farm Cash charge for a jade-priced item would not reach the server through that prompt. Serving the item with a Farm Cash price is required.
- `isValidCurrencyExchangeItem` does not handle `villageCoins`, so the Farmer's Square packs never appear there.
- The plow currency is exposed as the getter `Classes:FarmingAttributes.plowCurrency`. Its callers were not traced with the available disassembler, so whether plowing shows the same exchange prompt is **unverified**.

## Proposed least-invasive change (not implemented)

1. **Served catalog (server-side data, no SWF patch):** in `client_catalog.py` `_generate`, for an activated themed world only, serve converted items with `market: "cash"` and `cash: <amount>`. `world_currency_conversion.served_item` already does this on a copy. The client then uses its ordinary Farm Cash purchase path and never reaches the exchange prompt. Items that keep a Farm Cash price are unchanged.
2. **Server recomputes the charge** from the original catalog jade or coconut `cost`. It never trusts a client-sent price, because the served `cost` is hidden.
3. **Plowing:** not solved by step 1. It needs a served farming setting or a verified client check. Do not patch the SWF without the parent's decision.
4. **Purchase path (not implemented):** the charge must be applied once, atomically, in the same save transaction as the item. The audit record must hold source currency, source amount, pack, converted Farm Cash charge, world and timestamp. Unpriced items must be refused.

## Open questions

- A jade or coconut item with a `cash` field is treated as already priced in Farm Cash and kept. This is an interpretation, not a verified client behavior. Check one such item in the browser.
- The base-pack rule is a conservative choice. The user has accepted it, but it should be stated in any player-facing text.
- Crafting cottages are refused because the crafting queue is account-wide and is not supported in new worlds.

## Files

- `FarmVillage/world_currency_conversion.py`: rates, exact ceiling, pricing, audit, served-item copy, plow charge (dormant).
- `FarmVillage/macOS/Tests/test_world_currency_conversion.py`: 17 focused tests, all passing. Also listed in `macOS/Scripts/run-other-mechanics-regressions.py`.
- `macOS/Documentation/Worlds/STATUS.json`: `asia` entry gained `deliberate_deviations` and `implementation.dormant_currency_conversion`; `history` updated.

## Plow decision (2026-10-23, supersedes the plowing rule above)

- Plowing in every themed world, including Asia and Hawaii, costs **15 coins**, exactly Home's rate (`plowCost`). It is never converted to Farm Cash and never debited in a world currency. This is a **deliberate deviation** from the original client, which prices plowing in the world currency.
- `themed_worlds.plow_charge` encodes it: one debit of 15 coins for a new or cleared fallow plot; a retry on a saved plowed plot is free; insufficient coins raise without change. `macOS/Tests/test_themed_worlds.py` covers all three.
- `world_currency_conversion.plow_charge` still computes the converted Farm Cash amount. It must not be used for themed worlds, and its rates are unchanged.
