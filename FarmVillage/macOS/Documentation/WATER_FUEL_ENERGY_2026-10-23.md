> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../ACCEPTANCE.md), [current world scope](../../../WORLD_READINESS.md) and [the continuation backlog](<../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Watering, fuel and energy (2026-10-23)

Evidence source: the served client `FarmGame.swf` v855097, disassembled read-only with
`macOS/Scripts/client-inspection/abcdis.py` (`find`, `dis`, `strings`). Method numbers are the
disassembler's. Source lines come from the client's `debugline` records. Nothing here was checked in a browser.

## Outcome

- **Watering restored.** `IrrigationService.onIrrigationAction` (per-plot watering) and
  `IrrigationService.consumeIrrigationPackages` (3YG gifts to water) are now handled. The four
  `pkg_consume_irrigation_water_*` purchases are no longer refused.
- **Fuel and energy: not charged.** The client does spend and refill energy, but several refills are client-only.
  Charging the spend would strand the player at zero, so the existing refusals stay and the code comment is corrected.
- **Turbo charger purchases: still refused.** The turbo spend is not mirrored either.

## Watering: bytecode evidence

Ledger. `Managers:IrrigationManager.<cinit>`: `FEATURE_NAME = "irrigation"`, `WATER_PLOTS = "waterPlots"`.
The ledger is `featureOptions.irrigation.irrigation.waterPlots[currentWorldType].amount`.

| Method (number) | What it does (source line) |
| --- | --- |
| `getFeatureData` (24640) | Reads `getFeatureOption("irrigation","irrigation")`. Default when null: `{waterPlots:{farm:{amount:20}}}`. |
| `getMaxWaterForActionType` (24631) | Constant `2000`. |
| `getWaterAmount` (24638) | `m_data[actionType][currentWorldType].amount` if present, else 0. |
| `getWaterCost(plots)` (24639, l.197-207) | Sum over the array: `SuperPlotManager.getMultiplier(plot)` for a `Plot`, `+1` for anything else. |
| `addWater` (24630, l.92-101) | Creates the world entry if missing, adds the amount, calls `hud.refreshWater`. Only acts when the action type is a key of `m_data`. |
| `useWater` (24636, l.154-161) | Subtracts the amount from the current world's entry. |
| `isFeatureEnabled` (24627) | `PrerequisiteUtility.checkPrereqByName('bldg_irrigationWell_base')`. |
| `consumeWaterPackages(amount)` (24637, l.169-173) | `TransactionWithCallBack('IrrigationService.consumeIrrigationPackages', null, WATER_PLOTS, amount)`, then `addWater(WATER_PLOTS, amount)`, then `Player.removeGiftWithKey('3YG', amount)`. |
| `getWaterSourcesConsumables` (24633) | `pkg_consume_irrigation_water_{100,500,1000,2000}`. |
| `getSingleWaterSourceConsumable` (24634) | `consume_irrigation_water`. |
| `getWaterSourcesForActionType` (24632) | `bldg_irrigationwell`, `bldg_irrigationwell_8hr`. |
| `init` (24629) | Builds `m_config` from the feature XML (unused for the cap). `m_data = getFeatureData()`. |

Gift box.
- `Widgets.Slots.GiftBox:GiftBoxSlot.onUseClick` (53161): for `consume_irrigation_water` it refuses unless
  `worldManager.currentWorldType == 'farm'` (`Irrigation_useWaterBadWorld`). Otherwise it opens a use-all window with
  quantity `min(quantity, getMaxWaterForActionType - getWaterAmount)`.
- `GiftBoxSlot.useMultiWater` (53164): calls `IrrigationManager.consumeWaterPackages(quantitySelected)` when the item is a `FarmItem` and the quantity is positive.
- Catalog: `consume_irrigation_water` (code `3YG`) is a `CRewardConsumable` whose reward is `irrigation`, `waterPlots`, value 1.
  `consume_irrigation_water_N` (N = 100/500/1000/2000) grants `item_grant` 3YG × N. `pkg_consume_irrigation_water_N`
  holds one `consume_irrigation_water_N` and costs cash 2/9/16/30. Its `purchasePrereqs` and `marketPrereqs` are `bldg_irrigationWell_base`.

Sprinkler.
- `GMIrrigationSprinkler.handleClick` (33839): collects the valid `Plot`s with `hasValidId()`. Then
  `amount = getWaterAmount(WATER_PLOTS)` and `cost = getWaterCost(plots)`. If `amount >= cost` it calls `useWater(WATER_PLOTS, cost)`
  and `addAvatarState`. Otherwise it opens `GetMoreWaterWindow`.
- `GMIrrigationSprinkler.isSelectable` (33840) → `Plot.isWaterable` (21774) = `state == STATE_PLANTED`.
- `AMIrrigationSprinkler.update` (53806): when the progress passes 1, it calls `executeServiceCall` and removes the state.
- `AMIrrigationSprinkler.executeServiceCall` (53807, l.42-49): for each plot pushes `{id: plot.getId()}` and calls
  `plot.waterHarvestableResource(0.5)`. Then `TIrrigationAction(WATER_PLOTS, plotsIds, onServiceCallCompletion)`.
- `AMIrrigationSprinkler.onServiceCallCompletion` (53808): no-op.
- `Transactions:TIrrigationAction.<cinit>` (62653): `SERVICE_CALL = 'IrrigationService.onIrrigationAction'`.
  `perform` (62655) signs `(SERVICE_CALL, action, actionItems, params)`. `params` is undefined.

Plot change. `Classes:HarvestableResource.waterHarvestableResource(f)` (8376, l.551-589):
- `growMs = item.xml.growTime × inGameDaySeconds×1000 × growMultiplier`. The non-experiment path is used.
- `reduction = (growMs − (worldTime − plantTime)) × f`.
- If `reduction > IRRIGATION_MINUTES_TO_INSTAGROW × NUM_MSECS_IN_MINUTE` (`HarvestableResource.<cinit>`: 15; `FarmGameUtil`: 60000),
  then `plantTime = worldTime − growMs + reduction`. The remaining grow time becomes `reduction`, which is half.
- Otherwise `setFullGrown()` (8375): `plantTime = worldTime − growMs`. The `state` field is not written.
- AOE bookkeeping (`AOEManager.isAOETarget`, which is true for seed plots) sets `m_aoePlantTime` and the static
  `MapResource.m_aoePlaceTime`. No save-object method writes `aoePlantTime` (the method-name search for it finds only `HarvestableResource` methods), and `loadObject` only reads it if present.
  So the server mirrors `plantTime` alone.

Super plots. `SuperPlotManager.<cinit>`: `SUPER_PLOT_MULTIPLIER = 5`. `getMultiplier(plot)` (24872) is 5 only when
`isFeatureEnabled` (the `EXPERIMENT_SUPERPLOTS` variant equals 2) and `isSuperPlot(plot)` (an extra-item flag on the world).
The server serves no experiment variants, so the multiplier is always 1 here.

Water-sourcing elsewhere (not mirrored; see below): `WaterHarvestFManager` (`canAcceptHarvestReward`,
`getWaterHarvestAmountForLevel` read quest/tech rewards of type `irrigation`/`waterPlots`), and
`Classes.util:UserRewardUtil.grantUserReward` (an `irrigation` reward calls `addWater(actionType, value)`).

## Watering: server implementation

- `engine.get_water_amount` / `engine.use_water` (`engine.py`, after `add_water`): the ledger read and spend, refusing when there is no store or the balance is short.
- `commands.irrigation_action` (`commands.py`, "Irrigation (watering)"): validates the action (`waterPlots`), the ids (unique integers), and each plot (a `Plot` on this farm, not deleted, `state == "planted"`, a grow time, a finite `plantTime`).
  It sums the costs, calls `use_water` (which refuses before any mutation), then sets `plantTime = floor(_plant_time_after_watering(...))` on each plot.
  The `_plant_time_after_watering` helper mirrors `waterHarvestableResource` / `setFullGrown`. The grow time is `peaceful.grow_seconds(item)` in ms.
- `commands.consume_water_packages`: requires `waterPlots`, a positive whole amount, the `farm` world, an existing water store, and a ledger that stays at or below 2000 after the add.
  It requires at least `amount` of `3YG` in the gift box. Then it removes those gifts (`storage.remove_gift_by_code`) and calls `engine.add_water`.
- `commands.buy_consumable_package`: the `_UNRESTORED_IRRIGATION_PACKAGES` refusal is removed. The four offers take the generic route (cash charged, `consume_irrigation_water_N` deposited to the gift box). `storage.consume_by_name` then unpacks it into 100-2000 `3YG` gifts (its `item_grant` path).
- `server.py` dispatch: `IrrigationService.onIrrigationAction` → `commands.irrigation_action(UID, params[0], params[1])`. The response data is `{}`, which the client ignores.
- `commands.UNRESTORED_SERVICE_CALLS`: the two irrigation entries are removed.

## Fuel and energy: bytecode evidence

Energy model (client).
- `Classes:Player.energy/get` and `energy/set` (3893, 3892) read and write `m_energy`. `energyMax` works the same way.
- `Classes:Equipment.getEnergyCost` (12683) returns the constant `1`. `EquipmentDataObject.energyCost/get` (38486) returns the catalog `m_energyCost` unless an experiment variant overrides it.
- `HarvestableResource.hasEnergy` (8372) and `useEnergy` (8373) switch on the energy source. `ENERGY_SOURCE_AVATAR = 0` is free.
  `ENERGY_SOURCE_FUEL = 1` subtracts the cost from `player.energy` unless `hasUnlimitedFuelOfferActivated()`, and shows a fuel toaster when `ceil(energy/energyMax)` is under the threshold.
  `ENERGY_SOURCE_SUPER_AVATAR = 2` spends a super-avatar action instead.
- `Player.hasEnergy(cost)` (4084) returns true when the fuel offer is unlimited. Otherwise it returns `energy − cost ≥ 0` and shows `NotEnoughEnergy`.
- `Player.hasUnlimitedFuelOfferActivated` (4085) = `LoyaltyProgramManager.isGoldenFarmer() || hasNoFuelDayActive()`.
- `Player.hasNoFuelDayActive` (4086) requires experiment `EXPERIMENT_FLASH_NO_FUEL_DAY` to be exactly 1 and the flash var `NO_FUEL_DAY_START_TIME`. With no experiments served it is false.

Spend sites (client, `useEnergy`/`hasEnergy` callers): `Plot.plow`, `plant`, `harvest`, `remove` (their `TPlow`/`TPlant`/`THarvest` carry `energyCost`);
vehicle loops `AMTractorPlow`, `AMSeeder`, `AMHarvester`, `AMCombine`, `AMPlotRemover`, `AMResourceHarvester.performAction` (which also subtracts `getEnergyCost`); `GM*All.performResourceCheck`;
`PphAction.takeAction` (power-hour automation); turbo mode (`TEquipmentAction.<init>`, `Player.turboChargers/set`).

Refill sites (client writes to `energy`):

| Source | Method | Server mirror |
| --- | --- | --- |
| Crafted good used | `CraftingUseGoodsWindow.onCraftedGoodUsed` → `getFuelRewardForGood` | Yes: `crafting._use` (`crafting.py`). |
| Fuel bought (coins/cash) or gifted with an owned vehicle | `Transactions:TBuyFuel.<init>` (36713): `energy += xml.count × energyMax`, then `gold`/`cash −= cost`. Gift: `removeGift`, same add. Items `fuel1coin`, `fuel5coin` via `FuelItem.onBuy`/`onUse`. Transaction `FarmService.buyFuel`. | No. Refused. Cost and count are not in `items.py`'s catalog. |
| Gift-box fuel canister | `Classes.consumables:CFuel.onUse` (28709): `energy += count × energyMax`. Example item: `uni_monsterfuel` (count 10). No transaction in `onUse`. | No. Client-only. |
| Avatar fuel feed | `AvatarMode:AMFertilize.update` (44583): on completion `energy += m_fuel × ENERGY_PER_FIFTHTANK`. | No. Client-only. |
| Reward-point fuel | `Managers.Crafting:CraftingManager.spendRewardPoints` → `performRewardFuel` (5888): `energy += getFuelRewardForRewardPoints`. | No. `craftingState.pendingRewards` is not handled. |
| Power-hour fuel buff | `Classes.buffs:BBonusFuelPowerHour.apply` (50985): `energy += FUEL_BUFF_AMOUNT × energyMax`. | No. Client-only. |
| Load | `TInitUser.onComplete` and `Player.loadObject` | Yes: `commands.py` init writes `energy` from the save. |

No level-up write to `energy` was found. `CropBonanzaV2MOTDHandler.acceptMOTD` only reads `energy` for analytics.

Turbo charges. `Transactions:TBuyTurboChargers.perform` sends `FarmService.buyTurboChargers` with the item name. Turbo spend happens client-side in turbo mode
(`TEquipmentAction.<init>`, `Player.turboChargers/set`, `CTurbo.onUse`). The server has `engine.apply_turbo_chargers_diff` (minigame rewards only).
Equipment passes do not mirror the turbo spend.

## Fuel and energy: decision

The earlier comment said nothing in the client refills energy. That is wrong. Crafted-good fuel is refilled and mirrored, and several other refills exist.
But the refills that could balance a spend are not mirrored: buying fuel, fuel canisters, the fuel feed, reward-point fuel and the power-hour buff.
Turbo spend is not mirrored either. The unlimited-fuel gates depend on client-only loyalty and flash-var state.
Charging vehicle fuel now would leave players stranded at zero, so no fuel behaviour was added.

Refusals kept: `FarmService.buyFuel`, `FarmService.buyTurboChargers` (`commands.UNRESTORED_SERVICE_CALLS`).
Comment corrected above `commands.equipment_use`.

What is missing to charge fuel safely:
1. Mirror every refill above with its exact amount and cost. Buy and canister amounts come from the farm item settings, which are not in `items.py`'s catalog. Locate that source first.
2. Mirror the spend exactly: one fuel per vehicle plot (`Equipment.getEnergyCost`), `hasEnergy` refusal when short, super-avatar counts, and power-hour automation (`PphAction`).
3. Mirror turbo mode (`energyManager.turboChargers`) and the turbo purchase, or refuse turbo mode.
4. Decide the no-fuel-day and Golden Farmer gates server-side. They are client-only today.

## Still refused, and why

- `FarmService.buyFuel`, `FarmService.buyTurboChargers`: see the fuel decision above.
- `IrrigationService.onIrrigationAction` with any action other than `waterPlots`, with no plots, a non-planted plot, or insufficient water.
- `IrrigationService.consumeIrrigationPackages` with any action other than `waterPlots`, off the home farm, with no store, past the 2000 cap, or with too few gifts.
- `storage.consume_by_name` on `consume_irrigation_water` (the 3YG item itself). Its `irrigation` reward kind is refused. The client never consumes 3YG this way (the gift box uses `consumeWaterPackages`).

## Water still not mirrored (silent divergence)

- Irrigation wells (`bldg_irrigationwell`, `_8hr`) and any harvest with an `irrigation` reward appear to grant water on the client only (`UserRewardUtil.grantUserReward` → `addWater`; the well's `+N Water` status comes from `WaterHarvestFManager.onPreHarvest`).
  The server has no `irrigation` reward handling. Water from these sources is lost on reload. Verify the harvest path before relying on it.
- Quest and gift rewards of type `irrigation` are the same gap.

## Residual risks (unverified)

- No browser test. The in-game sprinkler flow, the GetMoreWater popup, and the gift-box "use all" window are unverified.
- The server does not check `bldg_irrigationWell_base` on watering or on package purchase. Other consumable packages behave the same way.
- Watering does not enforce `IrrigationManager.isFeatureEnabled` server-side.
- The non-experiment `growTime` path is used. Data-source experiments are assumed off.
- AOE state (`m_aoePlantTime`, `MapResource.m_aoePlaceTime`) is client-only. After a reload the AOE timing comes from `plantTime`.
- `plantTime` is stored floored to whole milliseconds.
- The server computes plant time from `timestamp_now()` (whole seconds). The client uses its own synced `worldTime`.

## Tests

`macOS/Tests/test_irrigation_fuel.py` (new, 18 tests): halving, ripening threshold, multi-plot cost, refusals without change,
malformed input, super-plot experiment gate, package use (credit, cap, world, store, gift shortage), purchase and unpack, and the fuel/turbo refusal guards.
`test_action_ledger.py` and `test_minion_round3_commands.py` were updated to the restored behaviour. They include a gateway test that waters a planted plot end to end.
