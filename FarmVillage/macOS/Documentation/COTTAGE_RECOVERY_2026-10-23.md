> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../ACCEPTANCE.md), [current world scope](../../../WORLD_READINESS.md) and [the continuation backlog](<../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Home crafting cottage lifecycle recovery — 2026-10-23

The Winery placement error comes from a real missing server method, not a
browser runtime or corrupted farm. The archived client chooses the free cottage
using `CraftingService.onClaimFreeCottage`. Previously the server's crafting
catchall rejected that method with error 29. Winery and Spa were also missing
from the production initialization and snapshot-protection table.

This change restores the original free choice, first placement bonus, ordinary
skill-one production, sales-history acknowledgment and tutorial tractor.
The bounded recipe restoration now covers 53 original contracts, with 32
undated recipes currently available. See
the full recipe contract table (`COTTAGE_LEVEL_ONE_RECIPES_2026-10-23.md`; external/private historical reference, not included in this source export).
It does not claim support for all skill levels, prerequisite campaigns, public
trading, crew rewards, cottage upgrades, rushes or other worlds' crafting buildings.
The recipe XML's `ComingSoon` gate applies to unsupported recipes only. Cottage
upgrade invitations require the separate client compatibility gate described
below; they are not hidden by recipe configuration.

## Sources and reproducibility

Read-only disassembly used `macOS/Scripts/client-inspection/abcdis.py` against a
scratch copy of `embeds/Flash/v855097-855094/FarmGame.swf`. No cache was written
beside the canonical client. Scratch evidence is in
`/private/tmp/winery-contract.FABVIf/` (`cottage-dis.txt`, `state-dis.txt`,
`lifecycle-dis.txt`, `bonus-dis.txt`, `history-dis.txt`, `player-dis.txt`,
`tier-dis.txt`, `tier-more.txt`, `tier-number.txt`).

SHA-256:

- Client: `1edea7cbecefcb1e1233da207164942f0088a83b87afc9254850f5fcde5034ae`
- `crafting.xml.gz`: `6bd6aee81539c23ed9d3996a37f5c9298bf3dc1f1c4e588f0b656876e91d2431`

The archived AMF item catalog identifies `craftingwinery` / `L9`,
`craftingspa` / `L8` and `craftingbakery` / `LA` as
`CraftingCottageBuilding`, required level 25, limit one per item code,
9 × 7, Home-world requirement or licence. Their three tier purchase records
each specify zero coins and zero buy XP. Pub remains `xukcraftingpub` / `jm`
with its existing separate catalog contract; it is not a free Home choice.

## Recovered calls and state

| Client evidence (original source debug line) | Wire / behavior |
| --- | --- |
| `TClaimFreeCottage.perform` 37–39 | `CraftingService.onClaimFreeCottage(itemCode)`; one string parameter. Completion 42–48 requires a non-null response before invoking its callback. The callback only records onboarding telemetry. `{}` satisfies that observed contract. |
| `CraftingManager.canClaimFreeCottage` 3796–3800 | Player level at least `craftingCottageStartLevel` (fallback 25), Home world, and no `UnlockedCottage` seen flag. |
| `CraftingManager.claimFreeCottage` 3919–3944 | Checks gift-box capacity, locally adds one cottage gift, starts gifted `GMBuild`, then queues the claim RPC. The server must persist the gift before gifted placement consumes it. |
| `CraftingCottageBuilding.onBuilt` 332–351 | Starts craft skill, checks first-ever `placeCottage`, grants onboarding once, grants recipe states and increments the local placed count. |
| `CraftingManager.grantOnboardingGoodies` 3979–3989 | Adds default recipe ingredients to bushel inventory; inserts the already-started bonus recipe locally. It does not queue `TBeginRecipe`, consume those ingredients or award normal make XP. |
| `CraftConfigSettings.getBonusRecipe` 1127–1135 | Copies the default recipe, sets `MinutesToCook` to `0.1`, then `overrideStartState(1, floor(worldTime / 1000) + 5)`. Only this first-placement bonus uses the five-second clock. |
| `CraftingCottageBuilding.loadObject` 842–853 | Loads `recipeQueue`, `finishedRecipes`, `cottageName`, `craftLevel` and `foundingTS` from server snapshots. Existing queues and clocks must survive load and movement. |
| `TCottageHistorySeen.perform` 29–31 | `CraftingService.onMarkCottageHistorySeen(craftType)`; completion forwards `responseCode`. Both normal callers omit a callback. We return numeric zero; its numeric success meaning is conventional, not established by a client comparison. |
| `CraftingCottageHistory` 43–52 and 101–102 | Fresh report depends on unread coins or `historyXPGain`; coin rows are filtered by `historyLastViewedTS`, but XP is not. Acknowledgment records the viewed timestamp and clears only the unread report XP total, preserving transaction rows and actual player/recipe XP. |
| `TCompleteCottageTutorial.perform` 18–20 | `CraftingService.onCompleteCottageTutorial()`; no parameters. |
| `CraftingUseGoodsWindow.onCraftedGoodUsed` 201–206 | On Home, without available equipment, tutorial mode locally grants a tractor and queues tutorial completion. This branch does **not** consume the selected good or call `onUseCraftedGood`. |
| `FarmGameWorld.getEquipment` 2975–3024 | Searches placed equipment and garage contents. Catalog equipment is type `vehicle`, including `tractor` / `T1`. |
| `BuildingItem.calculateCurrentTier` 119–120; `Player.getGlobalItemInstances` 5236–5260 | Counts placed cottages and cottage gifts by class. Purchase cost, market and levelRequired getters use `getItemTier(offset=1)`, giving the next tier (`count + 1`). The special same-item-owned case selects tier 1; ordinary one-per-code guards still apply. |

The server uses durable `localFreeCottageCode` and
`localCottageTutorialCompleted` receipts to prevent repeated grants after a new
Flash session. They are local implementation state, not invented client flags.
Imported seen flags remain intact. Free choice sets the original
`UnlockedCottage` flag. A pending first-placement marker handles the original
`Player.setSeenFlag` RPC arriving before the placement RPC, including a first
Market placement; it cannot repeat
onboarding after its durable grant receipt is set.

Existing imported cottages are initialized for display without onboarding
grants, ingredient changes, timer resets or gifts. Movement protects identity,
production, founding date and history fields from stale or forged snapshots.
Removing a cottage with queued or public production remains a visible rejection.

## Reload contents shape discovered in browser acceptance

After an actual Winery bonus claim and a new six-hour recipe, reloading the
same synthetic farm stopped at `StorageBuilding.loadObject` with TypeError
1034, Object cannot convert to Array. The saved `contents` field was `{}`;
`recipeQueue` was already a list and `finishedRecipes` correctly remained an
object keyed by product code. This was a separate failure from the initial
placement graphics selector.

The client superclass reads truthy `contents` then coerces it to Array at source
lines 1842–1843 (method 11983, byte offset 110). Its save method can instead emit
an empty associative Object. The four managed cottages now normalize **only**
that proven empty `{}` to `[]` during placement and init/load. Movement retains
the server-owned contents, preventing a stale client snapshot from changing the
array back to an Object. Nonempty imported rows and other classes remain
untouched. Production timers, public goods and personal inventories are retained.

The new regression failed before the fix for all three Home choices. The real
AMF regression now places each cottage with the original empty Object snapshot,
starts a normal recipe, claims the independent bonus, moves with a stale empty
Object snapshot, saves/reloads and calls `UserService.initUser`. It checks actual
decoded AMF Array types, durable contents arrays, exact remaining recipe clock
and unchanged goods. A separate imported-data case checks that nonempty contents
are preserved.

## Starter recipes

The archived `craftSkills` and `recipes` entries supply the following. Normal
begin/claim/fuel processing uses the existing shared engine unchanged.

| Craft | Default recipe | Ingredients | Ordinary clock | Make reward | Finished output |
| --- | --- | --- | --- | --- | --- |
| Bakery | `b0` pumpkin bread | 4 `pu`, 4 `wh` | 360 minutes | 1 recipe XP, 50 player XP | 2 public, 1 personal |
| Winery | `w0` sweet sake | 5 `rc`, 3 `ci` | 360 minutes | 1 recipe XP, 50 player XP | 2 public, 1 personal |
| Perfumery | `p0` fresh sachet | 3 `pu`, 3 `ci`, 1 `sf` | 360 minutes | 1 recipe XP, 50 player XP | 2 public, 1 personal |
| Pub | `lq` default; `lj` tutorial | Existing recovered catalog entries | Existing catalog clock | Existing catalog rewards | Existing catalog output |

No Bakery timer was advanced, reset or backdated by this work. The special
first-placement bonus is separate from ordinary six-hour production.

## Cottage upgrade boundary

The original `CraftingMainWindow.updateUpgradeFrame` (method 34693, source
lines 817–836) displays a 15 Farm Cash upgrade at stage one, replacing it with
the 50,000-coin upgrade after six recipe-level gains. Making supported recipes
can reach that threshold; a recipe-level gain adds one craft experience, while
an ordinary make alone does not. The original configuration has no additional
prerequisite on this upgrade. A cottage level changes through the upgrade call,
not automatically when its experience reaches the threshold.

Both controls send `CraftingService.onBuyCraftUpgrade(craftType,
isRushUpgrade)`. That method remains unimplemented and returns error 29. The
archived client optimistically charges its local balance and increments its
cottage level before the RPC, making an exposed upgrade invitation an invalid
flow. The candidate's separate client compatibility gate now hides both `buyUpgrade_bt` and `coinUpgrade_bt` until this service has an accepted
implementation. No upgrade service or changed level/price contract is claimed.

## Validation

`test_cottage_lifecycle.py` exercises real AMF commands using archived catalogs
and temporary synthetic farms. Fourteen tests pass: free choice and invalid inputs,
level/world/capacity restrictions, same-session and reload retries, Winery and
Spa placement, gifted withdrawal, first bonus, ordinary six-hour production,
history/movement/startup reads, imported queue preservation and one-time tractor
grant including equipment rejection. Market regressions cover
first-placement seen-flag ordering, original Pub tier payment once without
repeated onboarding, and detached price views including gift counts. The shared
`purchase_catalog_item` view must be used before both market preflight and
payment so a cottage's tier price cannot disappear between those operations.
Existing `test_crafting.py`: 28 tests pass.
`test_cottage_recipes.py` additionally sweeps all 53 ordinary skill-one recipe
contracts and verifies the original availability gates, derived client locks
and timer/progress preservation. The existing locked-state negative uses the
original higher-level `b3`; restored level-one `b1` is now explicitly unlocked.

`test_free_choice_is_durable_once_only_and_does_not_charge` run with the pre-fix
crafting module fails its first actual Winery claim RPC: a red witness for the
original missing-service error. Baseline module SHA-256 is
`b6923e22e0af0364c9dcede3d2a2cc07c7317ec4073d90ce8ec8d7e026be4f28`.

## Isolated browser acceptance

The actual client placed and reloaded Winery, Spa and Bakery on the same
synthetic farm. Winery's five-second onboarding recipe was claimed. Each cottage
then started an ordinary six-hour queue: Winery `w0`, Spa `p0` and Bakery `b2`.
The actual reload retained exact recipe start/finish timestamps, contents,
finished goods, position, craft level and founding timestamps. Farm Cash stayed
at 1,026, coins at 1,001,876 and XP at 100,260. See the parent investigation's
all-three reload comparison (`../../../Progression Audit 2026-10-23/all-three-reload-comparison.json`; external/private historical reference, not included in this source export)
and its referenced browser screenshots.

The synthetic farm had no equipment, and the ordinary Use Goods interface
required a vehicle. This run therefore does not establish browser acceptance of
fuel consumption; automated AMF tests cover use, rewards, retries and persistence.
The corrected upgrade-control gate passed actual browser checks for Winery,
Spa and Bakery: both purchase controls and their instructions are absent,
while recipe controls, original queues, stars and slots remain usable. Final
Python discovery passed 943 tests in 266.555 seconds. No live Bifrost update
has been made, and these results do not claim full crafting restoration.
