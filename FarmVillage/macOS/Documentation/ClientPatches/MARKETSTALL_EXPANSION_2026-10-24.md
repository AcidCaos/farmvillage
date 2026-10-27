> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../../ACCEPTANCE.md), [current world scope](../../../../WORLD_READINESS.md) and [the continuation backlog](<../../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# MarketStall expansion fence — 24 October 2026

Ordinary market stall placement, bushel configuration and management are restored.
The archived stall expansion economy has separate material/social stages that the
server rejects. Its original cash completion path changes local capacity before
constructing `TCompleteNow`, then subtracts cash optimistically. Newly reachable
expansion controls therefore needed a presentation gate and direct entry guard.

`MarketStallBuilding.readyToExpand` 22858 now returns false. Its existing callers
hide the owned stall context menu's Expand Now item and the Farmers Market main
and Expand tab controls. The original default-tab code checks visibility before
opening the Expand tab.

The gate alone is insufficient: `HomeMarketStallShopSlot.onExpandClicked` 62869
calls `beginCompleteExpansionFlow` 22845 directly. A separate
`GenericExpandSlot.onFrictionlessCompleteNowCallback` 62338 invokes
`IExpandComponent.frictionlessExpand`; the stall constructor binds that to 22903.
Both MarketStallBuilding entries now show the existing Inventory storage refusal:
“Storage upgrades are not restored on this server.” They return before reading or
writing building/player state, constructing a confirmation or transaction,
changing callbacks, expanding capacity or debiting cash.

No generic building or expansion base class changes. The two void entries retain
their original debug/scope prefix and reuse the exact already-reviewed
`UI.displayMessage(message, TYPE_OK, null, '', true)` bytes from Inventory's
refusal. Getter maxstack 1, flow maxstack 9 and completion maxstack 7 remain ample;
the popup call peaks at 6. All three original headers, code lengths, empty
exception tables, scopes and constant pools remain unchanged. Unreachable tails
are NOP padding, with no branch instructions or stale branch targets.

Input recognized intermediate:
`bd837906218648bfd4edd0f3bf86ae242b6283222aa551d970b51fe444ffb145`

Output decompressed body:
`b0200b4ae46a665fb910a329c0137678c74eacf9a0553a17f9cc4b7186e2ddea`

The body remains 21,521,041 bytes. The JSON review (`MARKETSTALL_EXPANSION_BYTE_REVIEW_2026-10-24.json`; external/private historical reference, not included in this source export)
records exact offsets, original/replacement bytes and complete/method hashes.
The original disassembly is preserved in
the expansion evidence (`../MarketStallEvidence20261024/stall-expand-and-found.txt`; external/private historical reference, not included in this source export)
and window evidence (`../MarketStallEvidence20261024/stall-expand-tab.txt`; external/private historical reference, not included in this source export).

Four dedicated tests inspect the actual original invitation/direct-call sites,
execute the emitted getter and both refusal entries with no building/player or
transaction globals available, compare all 68,492 methods and pools, validate
all instruction/branch boundaries and empty exception tables, and check recognized
stage upgrades, compression idempotence and refusal of unknown modified code.
Bytecode checks do not establish browser acceptance; the parent records that
separately in the fresh synthetic fixture.

The final combined client/serving/feature run passed **62 tests in 69.913 seconds**
on 24 October 2026. Scoped `git -c core.whitespace=cr-at-eol diff --check` passed.
