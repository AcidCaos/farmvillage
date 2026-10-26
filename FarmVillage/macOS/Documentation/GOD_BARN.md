> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../ACCEPTANCE.md), [current world scope](../../../WORLD_READINESS.md) and [the continuation backlog](<../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# God Barn in the native app

God Barn is a local cheat interface built from the original FarmVille archive. The native editor edits the village selected in this app's owned game server. The separate **Play God Barn.command** companion edits disposable save copies instead. Live actions are labeled as changes to the local farm; copy import and practice-farm creation are available only in standalone mode.

## Open and use it

God Barn is bundled in the normal native Release app. Open the repository's
**Play FarmVillage.command** to use the prepared `LocalData/` profile. Opening the
app directly uses `~/Library/Application Support/FarmVillage/` instead.

1. Open a farm using the launcher's native farm picker or return button.
2. Open **Tools → God Barn**. Check the farm name; its picker can choose another
   saved village in this profile.
3. Preview an action and review the exact changes. Apply commits the selected
   farm and creates a snapshot of its previous state.
4. Choose **Return to Farm** in the toolbar or editor to load the saved result
   into a fresh game page. Choosing another farm also releases this editing session.

Building or opening the app window does not stop or reload an already running game. Close the existing app yourself before starting another instance against the same profile or `127.0.0.1:5501`. The wrapper does not attach to an unrelated process occupying that port.

## Available controls and limits

- Add, set, or multiply coins, Farm Cash, XP, energy, and turbo charges. Balances stay within 0–2,147,483,647; level selection uses the original levels 1–100 and includes forward level Farm Cash rewards.
- Ripen, revive, or fertilize eligible planted crop plots, and advance selected or all known crop timers. The interface accepts jumps up to 8,760 hours, using the original 23-hour crop-day rules. It does not change the Mac clock or all game cooldowns. Protected jumps stop at readiness; saved crops keep aging with real time.
- Browse 111,206 archived item definitions, search, filter, save favorites, and grant ordinary animals, trees, decorations, buildings, seeds, vehicles, fuel, and turbo items. The interface accepts 1–10,000 items per action. Special placement, world, and feature requirements still apply.
- Explore recurring crop windows in **What’s in season?** under **Lost & Found** or **The archive**. The calendar follows the Mac’s local date and timezone, with a temporary **Browse a date** override and **Use today** reset. Recorded month/day windows repeat annually; missing dates stay unknown. This discovery view preserves year-round gifts and does not activate historical offers in the game’s Market.
- Expand the selected farm to a larger catalog-defined square size; shrinking is not supported.
- Download JSON backups and restore snapshots belonging to the same farm. Restore also preserves the previous state as a new snapshot.

Peaceful mode now provides permanent crop protection, and ribbons/mastery progress through the original game responses. Continuous multipliers, automatic farming routines, breeding outcomes, additional worlds, crafting, and full seasonal restoration still require corresponding game mechanics. An inventory entry does not implement a special item's mechanics. Fuel is already uncharged by the preservation server; editing saved energy does not establish an additional fuel effect.

## Storage and recovery

The native bridge uses the active profile's normal `saves/` directory through the game's save APIs. It retains imported filenames and player identity. Before-change snapshots are separate JSON records under:

```text
<active profile>/god-barn/snapshots/
```

The standalone companion stores its own copies and history in `GodBarn/workspace/`; they are not automatically installed into the game. Native exports are normal browser/WebKit downloads, with a native Save dialog in the app.

If saving reports a storage error, inspect **Activity** and refresh the farm state before retrying an additive action. A failure before commit rolls back; a durability error after the game's commit marker can mean the change is already present. Recovery journals belong to the game's persistence layer and must not be removed as routine cleanup. Back up the active profile's `saves/` and `god-barn/snapshots/` directories with the server stopped.

## Maintainer notes

The companion remains a sibling source package. `Scripts/bundle-runtime.sh` calls `GodBarn/scripts/bundle_companion.py` to stage its namespaced engine, live adapter, interface, compressed catalog, and thumbnail map into the native runtime. The build excludes companion workspace saves and copied thumbnail bulk. UI skin and fonts are bundled locally; catalog images resolve against the app's already extracted original asset archive. No remote UI assets are loaded.

The standard FarmVillage Xcode build stages the companion with the launcher. The sibling package also retains its own build helper for development. Neither build starts a server or game session.

`GodBarn.integration.register_god_barn` mounts `/god-barn/` on the owned Flask app. Native WebKit and the game share that origin and session. Opening the editor follows the currently playing village, removes the playing WebKit view, and parks the farm at the gateway. A page epoch prevents late AMF commands from a superseded game page from overwriting a Barn change. Returning resumes the selected village through a fresh Ruffle document.

The detached engine produces a full proposed save and JSON-pointer change list. Preview tokens bind the proposal to the farm, session, revision, and a 15-minute lifetime. Apply rechecks the revision under the game's `SAVE_LOCK`, saves a before-change snapshot, and updates through `village_transaction` and `save_session`. Ordinary failures roll back through that transaction; `CommittedSaveError` semantics retain already committed state and invalidate the previous game epoch. Snapshot restore uses the same boundary and verifies matching player identity.

Loopback Host/Origin checks and a session mutation token protect the adapter. Snapshot IDs are generated opaque IDs; mutation APIs do not accept save destination paths. Static resources and thumbnail mappings are constrained to their intended roots. The backend permits up to 100,000 granted items or 87,600 advanced hours per operation; the interface deliberately uses the smaller limits stated above.

The companion's isolated engine/integration suite and a separate real-backend
audit use disposable farms. The backend audit covers currency, crop ripening,
item grants, snapshots, export, restore, unchanged neighboring farms, editor
ownership, and actual AMF parking/epoch rejection. Native session evidence is
recorded in VALIDATION.md (`VALIDATION.md`; external/private historical reference, not included in this source export); backend checks alone do not establish
that every original game mechanic supports a granted item.

## Peaceful crops, gifts and archive history

Open **Unwither garden** to preview the per-farm Peaceful policy. Crops grow normally while away, then remain ripe; existing withered crops revive. Return to Farm loads the original client's no-withering flag in a fresh document. Turning protection off restores the prior per-world settings and gives ripe crops a full normal harvest window. Manual plowing, planting and harvesting stay available.

Open **The archive** for three initial collections with recovered original art. Historical prices are context for a God Barn gift, never a charge. Price selectors distinguish Farm Cash, coins, Village Coins and unknown prices, with original raw fields and record provenance retained in the copied catalog. Collection browsing does not restore the original event mechanics.

The native **Tools → Send Free Gifts** opens the local gift basket. Local player farms can exchange non-expiring presents; archived display neighbours remain read-only. The gift box, inventory, building storage, and supported reward packages use the game's existing transaction boundary.
