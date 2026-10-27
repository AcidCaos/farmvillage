> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../ACCEPTANCE.md), [current world scope](../../../WORLD_READINESS.md) and [the continuation backlog](<../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# AMF batch rejection isolation

The gateway applies each decoded call inside a savepoint. A rejected call restores
every writable farm it touched, including pending neighbor writes. Structural
save validation and strict UTF-8 JSON serialization are checked before releasing
the call's savepoint, after its final mutation of any touched farm. Accepted calls
before and after it remain in the outer transaction. The outer transaction still
publishes all changed farms together; encoding, disk, and unexpected server failures
retain its complete rollback behavior. Malformed AMF envelopes remain HTTP 400 and
run no commands. A batch containing only rejections writes no saves.

Command rejections return HTTP 200 with outer `errorType: 0`, one result per original
call in order, the original `sequenceNumber`, and `errorType: 29` plus a readable
`errorData` only on rejected results. Rejected results contain no successful data or
quest rewards. Successful result data is copied before the next call runs, so a
later provisional mutation cannot escape through an earlier result.

## Original-client evidence

Recovered from the checked-in `embeds/Flash/v855097-855094/FarmGame.swf` with
`macOS/Scripts/client-inspection/abcdis.py`, using a scratch copy on 2026-10-23:

- `Engine.Transactions:Transaction.<cinit>` defines `NO_ERROR=0`,
  `RETRY_TRANSACTION=28`, `FORCE_RELOAD=29`, and `IGNORE_TRANSACTION=39`.
- `Engine.Managers:TransactionManager.onAmfBatchComplete` checks the outer error
  first and requires a result array matching the number of queued calls. It then
  inspects each result's `errorType`. At byte offsets 349–415, `FORCE_RELOAD`
  forces the retry count past its maximum and routes to batch fault handling.
- `Engine.Managers:TransactionManager.onAmfBatchFault` dispatches
  `TransactionFaultEvent.FAULT` for a faultable transaction after the retry limit.
  `FarmGame.onTransactionFault` calls `showOOSDialog` for this error.
- Arbitrary other nonzero per-call codes reach `Transaction.onAmfComplete`, then
  the base `Transaction.onFault`, whose body is a no-op. Using an arbitrary code
  would silently discard many rejected game actions. `IGNORE_TRANSACTION` would
  also hide the rejection. Neither is suitable.

The original client stops dispatching completion callbacks at `FORCE_RELOAD`.
Accepted calls later in that batch are already durable on the server and become
visible on reload. This preserves the existing visible save-error behavior while
preventing collateral loss of accepted actions. It does not attempt to continue an
optimistically edited client after rejection.

## Regression coverage

`test_persistence.py` checks ordered success/rejection/success results, restoration
of both farms after a partial neighbor mutation, removal of rejected pending writes,
no leaked provisional response state, and a retried mixed batch that charges two
plows once. Existing disk, journal, encoding, and concurrency regressions remain.

Wire tests now assert HTTP 200 plus the actual per-call rejection, rather than
HTTP 400. Mixed-batch tests assert that paid Instant Grow, breeding, construction,
quest progress, pet purchases, gifts, UGC designs, minigame tokens, recipe starts,
feature preferences, and world travel survive unrelated rejected followups.
Their existing action receipt and temporary-ID retry behavior is retained.
