> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../ACCEPTANCE.md), [current world scope](../../../WORLD_READINESS.md) and [the continuation backlog](<../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Prize games and unsupported mutations — 22 October 2026

This pass repairs the existing local slots, scratch card and Pigo implementations.
It does not recover original server reward tables or establish browser acceptance.
No live farm, Bifrost installation or native build was changed for this verification.

## Behavior contract

| Game | Durable server behavior | Limits |
|---|---|---|
| FC slots | One initial free spin, saved free-spin rewards, exact 3 FC paid cost, sufficient funds required, server-selected payout and matching reels. The original `slotMachine.slotMachine_freespins` feature option is returned on login, so the client displays the saved balance. | The old in-memory implementation granted another free spin on every login. Existing sessions cannot be migrated from that process-only counter; a save without the option receives its one initial spin. Reward pool and 35% win chance remain local substitutes. |
| Scratch card | Exact 4 FC local price, paid card and result saved before reveal, same card after reload, single reward claim, saved free-card awards and consumption. No charge or payout for reopening an active card. Paid replacement of an unfinished card is rejected. | The old implementation granted rewards while purchasing and did not save an active card; historical cards cannot be reconstructed. Price, rewards and 15% win chance remain local substitutes. Every loss now supplies `almostWon`, because the original reveal code requires that field to show Try Again and send `clearCard`. |
| Pigo | Only the supported `pigov2game` and its six configured prizes are accepted. Single/package cost comes from the catalog and recovered formula: 10 FC / 27 FC for three tokens. A validated original free-play allowance or gift-box token is consumed before awarding a prize. Set bonus is granted only on the first complete-set transition. Imported unknown prize counts are retained. | **The client still selects the prize through local physics.** The original request supplies only game and item name. Server checks restrict rewards and require payment; they cannot authenticate the peg outcome or enforce original odds. The six prizes and set bonus remain local substitutes. Other Pigo games are rejected. |

The original `SECURE_pigoFreePlayCount` is imported once as a server-owned
allowance and respects the recovered minimum-level gate. A positive count means
one free play: the original client consumes it by setting the counter to zero.
The generic action-count methods can acknowledge the value but cannot raise or
consume this allowance; successful prize completion consumes it. This prevents
the client's pre-animation acknowledgment from destroying an earned free play.

The derived client repairs the original scratch-card icon loader's unsupported
500/2,000 coin amounts with existing amount-free coin art and actual quantity
labels. Million rewards retain their original artwork. Payouts and matching
identities remain unchanged; see `ClientPatches/scratch-coin-byte-review.json`.

The archived Carnival catalog assigns both Pigo and Fortune Wheel to slot 3.
Enabling `fv_pigo=2` together with `fv_wheel_bundles_2>1` made the visible Pigo
tile open Fortune Wheel in the original browser. Both launch templates now
set the unsupported wheel experiment to 0, leaving the recovered Pigo action
`openPigoGame` as that slot's sole eligible entry. The focused catalog/bootstrap
contract passes. Browser verification opened Pigo, bought one token for ten
synthetic Farm Cash (724 to 714), dropped it and won a Duck. The saved state has
one Duck win and one DU Gift Box item; the token was consumed. Set-bonus/free-play
and a post-win full client reload remain unverified.

All eight game methods use one atomic dispatcher. It validates exact parameter
counts and original Boolean/string types before checking retry receipts,
rejects malformed or insufficient balances, and applies changes to a
detached copy before committing. The enclosing existing village transaction
rolls back the entire AMF batch and disk state on failure. Unknown operations
within `SlotService`, `ScratchCardService` and `PigoService` are rejected rather
than acknowledged as successful. Other unsupported service families have not
been changed by this pass.

## Retry boundary

The last 256 method/parameter/result receipts are persisted per Flash session.
An exact sequence retry returns the original result without charging or awarding
again. A changed request reusing a sequence is rejected. An older sequence whose
receipt has been evicted is rejected, so eviction does not reopen it for payment
or reward. All durable balances and pending cards survive `initUser`; only the
sequence receipts reset when Flash restarts its counter.

The recovered protocol provides no durable card identifier, spin identifier or
cross-session request token. Therefore it cannot distinguish a replay that uses
a new sequence or arrives after a new `initUser` session. Such a request still
requires an unconsumed card, original free allowance or payment; this pass does
not claim protection against all delayed cross-session client messages.

## Recovered evidence

Source client: `embeds/Flash/v855097-855094/FarmGame.swf`, SHA-256
`1edea7cbecefcb1e1233da207164942f0088a83b87afc9254850f5fcde5034ae`.
Contracts were inspected locally in its bytecode, including:

- `FCSlotMachineWindow.spin`, `getFreeSpins`, `setFreeSpins`, `grantReward`:
  parameterless spin request, server payout, feature-option balance.
- `ScratchCardWindow.postLoadComplete`, `onUnlock`, `onPlayAgain`,
  `scratchAll`: `[false]` open/free play, `[true]` paid play, parameterless
  `clearCard` and `grantReward`, and `almostWon`/`winEntry` completion branches.
- `PigoWindow.initTokenPricing`, `onPlayButtonClick`, `dropToken`,
  `grantReward`, `checkForFreePlay`, `checkForSetBonus`: catalog cost,
  three-token discount, local physics outcome, token/gift identities,
  original allowance consumption, and derived set bonus.

The documentation intentionally contains no extracted proprietary source or farm
payloads. No external server rules were invented to fill the missing reward tables.

## Original UI entry points and local assets

`postInitUser` supplies the original `scratchCard`, `fcSlotMachine` and
`carnivalBooth` HUD icons. The scratch icon is a tilted grey 3×3 grid with a
yellow starburst and a small green farmer; its original minimum level is five.
The slot icon is a small red/yellow/green slot machine, available from level one.
The Game Tent icon opens the original carnival promotion grid. Its recovered
promotion slots are scratch card at 0, Pigo at 3 and FC slots at 5.

The corresponding original dialogs are `assets/dialogs/FV_ScratchOff.swf`,
`assets/dialogs/FV_SlotMachine.swf`, `assets/dialogs/FV_Pigo2.swf` and
`assets/dialogs/FV_CarnivalMain.swf`; all are present in the local asset archive.
The Game Tent needs `CARNIVAL_PROMOS_ACTIVE=6` and its original Coming Soon
fallback. Pigo uses experiment `fv_pigo=2`, then chooses an in-experiment Pigo
game token whose date gate passes. The supported `pigov2game` has no date gate.
These settings and assets establish navigation evidence, not browser acceptance.
The earlier disposable browser session showed scratch-card and slot icons but
no Game Tent HUD icon. Both game pages now set `fv_carnival_booth_hud=2`, the
original `TPostInit.onComplete` threshold for calling
`CarnivalBoothQueuedIcon.showHUDIcon`. This uses the existing tent asset,
`MiniGamesIcon` class and `CarnivalBoothWindow` action. A served-page regression
checks both bootstraps and the supported Pigo data. The original browser now
shows the Carnival entry and promotion grid. Its HUD icon displays a random
prize animal inside the tent frame; the first verified instance showed a sheep.
The paid Pigo play and persisted reward acceptance is recorded above. A full
post-win client reload and set-bonus/free-play checks remain pending.

## Verification and remaining coverage

Run from the FarmVillage repository:

```sh
LocalData/venv/bin/python -B -m unittest discover -s macOS/Tests -p test_minigames.py -v
```

The suite imports `test_persistence` first, uses temporary saves and catalog
caches, and opens no server socket. It checks payment, exact costs, imported
state preservation, free allowance protection, generated card validity,
server-selected payouts, reload, retry, receipt eviction, malformed requests,
whole-batch rollback, and simulated disk failure. The original browser has
completed free/paid slot losses and a scratch loss, including scratch reopen
without a second charge. The coin patch visibly rendered ×500 and ×2,000 on
a subsequent card. Scratch wins/free replay and Pigo set-bonus acceptance
remain separate gaps. A protocol regression is not browser acceptance.

Recorded isolated result: **27 tests passed, zero failures/errors/skips**, in
33.937 seconds on 22 October 2026. These include real AMF gateway round trips,
the original Game Tent surfacing gate in both served clients, and rejection of
numeric scratch flags that compare equal to Boolean receipts;
the result must not be added to an integrated run that includes the same suite.

Broader gaps from the community audit remain separate: all original seasonal
events and rewards, experiment assignment, other crafting recipes/cottages,
construction and breeding families, social-network services, and most specialized
quest objectives. This change supplies no all-features-working percentage.
The generic unrelated unsupported-command fallback and its diagnostic logging
also require their own client-compatible review.
