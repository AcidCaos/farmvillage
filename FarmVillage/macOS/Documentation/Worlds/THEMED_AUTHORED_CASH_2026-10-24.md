> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../../ACCEPTANCE.md), [current world scope](../../../../WORLD_READINESS.md) and [the continuation backlog](<../../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Authored themed cash alternatives — 24 October 2026

Present Box I (`xhdpresentbox`,9pH) advertises both 100 coins and 1 cash. The original
Market sends explicit Currency.CASH for the cash button and selects cashName/code
from the same authored record. There is no separate cash/sale companion. The
server previously accepted only its cached primary coin price, so the cash click
was rejected after an optimistic client debit.

`themed_worlds.guard_purchase` now selects a fresh cash price dictionary only for
an explicit cash request on an admitted coin-priced item, using the canonical
server record's matching code, original current-World ownership and positive
whole authored cash amount. The cached primary rule is never changed. Default,
coins and gold-alias purchases keep their original price. A cash-only record
cannot acquire a coin alternative; no fallback value or new price is invented.

The archive contains 21 admitted Htown coin-default/cash records. Twenty explicitly
use market=coins. `xhdbridgecedar`9pL omits market and uses the existing coin default
(cost50000,cash5); the guard also accepts its explicit authored cash5. This does
not assert that all 21 render two buttons. None has a cash/sale companion.

Every raw/client cash field and all legacy-world purchase implementations remain
unchanged. Source definitions, gift records, Home behavior and assets stay intact.
The review (`../ClientPatches/THEMED_DUAL_PRICE_REVIEW_2026-10-24.json`; external/private historical reference, not included in this source export) includes exact
records, authored prices and the guard function identity. Source protocol proof is
preserved in ThemedMarketEvidence20261024.

Four signed AMF tests passed in 15.507 seconds: cash/coin/default/gold purchases,
canonical price selection, wrong currencies, invalid price/identity, selected
wallet insufficiency, live placement retries and disk reload. Reload verifies
the acknowledged persistent object ID and balance; temporary IDs intentionally
expire at save/login and stale-session temporary requests are not claimed as
persistent replay support. All132 activated-world regression cases also passed
in 21.100 seconds. Actual browser acceptance belongs to the parent.
