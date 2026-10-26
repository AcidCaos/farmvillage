> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../../ACCEPTANCE.md), [current world scope](../../../../WORLD_READINESS.md) and [the continuation backlog](<../../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Inventory tab artwork visibility — 24 October 2026

`GenericButton` 4311 creates a new transparent MovieClip hit rectangle in
`m_overlay` and adds it to the original artwork’s parent. The target artwork and
click overlay are siblings. The previous invitation gate hid only `m_overlay`;
that prevented clicks while leaving the Expand/Shipping invitation artwork visible.
The original text setter 4318 also acts on `m_target`, confirming that separation.

The correction changes only `InventoryWithdrawal.onLoadComplete` 12403. After
each unsupported wrapper is constructed, it hides both the existing hit rectangle
and the original public clip:

- `m_window.storage_mc.expandStorage_bt`
- `m_window.storage_mc.shippingLicenses_bt`

Each replacement uses its existing overlay hide plus the exact public clip path
already used to construct that GenericButton. It replaces only the unused
unsupported-tab label/localization span (401:432 and 491:522). No private
GenericButton field access, new constant, branch or method-length change is needed.
The original 942-byte method remains maxstack 7/locals 6 with its existing scopes.
Category maps, the Inventory tab, content panels, storage data and withdrawals are
unchanged. The existing constructor gate still opens the Inventory section.
Storage expansion transactions retain their separate local refusal guard.

Input stage:
`2912036e46cde068b13b8e302c0e8d11a3e02911b52629fcce8b32f414089f32`

Output stage:
`bd837906218648bfd4edd0f3bf86ae242b6283222aa551d970b51fe444ffb145`

The body remains 21,521,041 bytes. All preceding recognized clients, including the
repaired unlabelled image draft, advance to this stage. Archived source assets and
compiled Ruffle files remain unchanged. The JSON companion records exact bytes,
offsets and hashes.

Four new tests inspect the actual GenericButton constructor, execute the old gate
to demonstrate that artwork remains visible, execute both corrected spans to hide
both layers, preserve ordinary Inventory artwork and content, compare all 68,492
methods/pools/non-code bytes and validate every branch/exception boundary in 12403.
They also cover prior-stage upgrades, compression idempotence and unknown-byte
refusal. Actual browser presentation acceptance belongs to the parent’s fresh
synthetic fixture; bytecode tests alone do not establish it.

## Other named invitation entries reviewed

The audit found no further concrete miss in the reviewed named entry points:
TurboPPHOnBoardingDialog.conditionalShow 38973 constructs its dialog only after the
patched shouldShow 38972 returns true; CraftingManager.checkAndShowCottageReminder
5777 calls the patched automatic reminder 5911; StorageBuilding.showMenu 11987 skips
its expansion-menu builder through the reviewed false condition. The generic
Market3 walkthrough is separately gated by 11246, alongside the dedicated VIP
renderer and mini-banner. These checks do not constitute an audit of every
hard-coded popup or unsupported feature in the archived client. The inventory
continues to distinguish its five hard-coded presentation gates from the 194
original HUD invitation names plus the three shared/retired renderers.

The later MarketStall expansion fence retains this output as a recognized intermediate. See [its review](MARKETSTALL_EXPANSION_2026-10-24.md).

Its four dedicated checks also passed in the final combined 62-test
client/serving/feature run (69.913 seconds) after the MarketStall fence was added.
