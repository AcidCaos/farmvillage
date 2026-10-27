> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../../ACCEPTANCE.md), [current world scope](../../../../WORLD_READINESS.md) and [the continuation backlog](<../../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Actual Inventory widget visibility — 24 October 2026

Preserved fresh-browser screenshot22 (`WidgetStorageEvidence20261024/failure-b020-inventory-buttons.png`; external/private historical reference, not included in this source export) still showed Expand Storage and Shipping Licenses with
body `b0200b4…`. The earlier legacy-artwork test had exercised a different window.
`UI.displayInventoryDialog` 2899 constructs `Widgets.Windows.Storage.StorageWindow`
for type `inventory` (54–102); only the non-inventory branch constructs the legacy
`InventoryWithdrawal` (160–174). The actual screenshot's Storage title, List of
Farms, search and category icons match the widget window.

`StorageWindow.postLoadComplete` 12193 constructs each `FarmAnimatedTextButton`
and calls `addWidget(widget, visible)`. Its expansion visibility came from
`hasUpgradableStorage()` at 762–771; Shipping supplied true at 1146. The correction
replaces that nine-byte predicate with false plus NOPs, and the Shipping true with
false. Both widget objects and callbacks remain initialized for normal cleanup.

The existing `ZwAbstractWindow.addWidget` 998 forwards this boolean unchanged to
`ZwWidgetManager.addWidget` 4439. It writes widget.visible; setter 4361 writes the
complete element's visible property and disables its input. Later ordinary
`StorageWindow.setButtonEnable` 12218 calls enabled setters only; 4367 toggles input
without making the element visible.

Independent parsing verified both actual transfer assets. Each directly places
`shippingLicenses_bt` at root depth13 and `expand_bt` at depth172, containing the
checkbox and text. MainNav, SubNav, slot frame, search and farm controls are
separate root objects. The constructor selects original or v2 according to its
experiment, then runs this same setup. Asset identities and exact byte edits are
in the JSON review (`WIDGET_STORAGE_VISIBILITY_BYTE_REVIEW_2026-10-24.json`; external/private historical reference, not included in this source export).
Independent source evidence (`WidgetStorageEvidence20261024/storage-widget-entry-child.txt`; external/private historical reference, not included in this source export)
and both-layout proof (`WidgetStorageEvidence20261024/inventory-transfer-layout-child.txt`; external/private historical reference, not included in this source export)
are preserved locally.

Only method12193 changes. Its original 2,711-byte code length, maxstack11,
locals15, scopes12..13, all branches, empty exception table and pools remain
unchanged. The full body stays 21,521,041 bytes. Input b020 remains a recognized
intermediate; final output is:
`c5aaff1f2ef9d60d4d2606ecac81ad7190d3f120b1500fb6b4e1d98ea4bbf589`.

Four dedicated tests inspect the actual route and registration chain, execute
both emitted false arguments and the element-visible setter, compare all68,492
methods/pools/headers/branch boundaries, and verify prior-stage upgrade,
idempotence and rejection of unknown edits. Browser acceptance is recorded
separately by the parent.

`DecoratorModeStorage.postLoadComplete`53543 is a separate subclass that explicitly
restores its own Expand control after calling super. This narrow ordinary
Inventory correction does not claim acceptance or change that special flow.

The final combined client/serving/feature run passed **66 tests in 75.077 seconds**
on 24 October 2026. The scoped whitespace check and final-stage idempotence check
also passed. Actual browser acceptance remains separate.
