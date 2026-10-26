> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../../ACCEPTANCE.md), [current world scope](../../../../WORLD_READINESS.md) and [the continuation backlog](<../../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Quest reward close acknowledgment — 24 October 2026

The original quest reward dialog displayed its reward preview but did not bind
its close acknowledgment. The preserved embedded widget XML (DefineBinaryData 668)
puts `viewToPin="CloseButtonView"` on the unnamed outer Mask of `questRewardView`.
The named inner `content` Resize has no `viewToPin` attribute. Original
`QuestRewardDialog.setup` 23979 looked up that missing inner attribute, received
null and skipped listening to its `onCloseButtonPress` callback. The generic
close controller could still dismiss and destroy the window without submitting
the local reward acknowledgment.

The patch binds `CloseButtonView` directly. It follows the existing
`DynamicDialog.setShortcutListener` 10083 lookup/coerce/null-guard/listen contract
inline, reusing the setup method’s unused local1. A direct helper call would
need four stack values while setup’s original maximum is three; the inline form
retains maxstack 3, locals 2, the original 156-byte method, scope bounds and all
constant pools. The reward-list, header, avatar and share-button setup before
byte 95 remains identical. The original outer quest-presence branch still reaches
the original return block at 152. The changed 57-byte tail contains one new forward
null guard and NOP padding; it does not move code or exception boundaries.

The existing `onCloseButtonPress` 23988 remains unchanged. It constructs
`TShareQuestLoot(questName, false, dialog)` and schedules it through the existing
TransactionManager. The false argument selects the local acknowledgment route;
this patch sends no social feed and pre-grants no reward or saved seen flag.
ButtonController 24062 dispatches BUTTON_PRESSED during the superclass mouse-up
handler before CloseButtonController 32819 dispatches CLOSE. The acknowledgment
therefore enters the normal transaction path before generic dialog destruction.
Server completion validation and duplicate-reward protections remain authoritative.

## Pins and checks

Input stage:
`87ce6267b37dc9dc7a0c2b2e5b8ca7c2be462fefbe2d16fab36bacd4ff64169a`

Output stage:
`8ca832debfa8404c3934f6859321937c546b1b9b398b0dc44fb030ef90e0b504`

Body size remains 21,521,041 bytes. Source assets are unchanged. The input stage
is accepted idempotently as a known predecessor; other known earlier builds
advance through the same pinned chain. The JSON companion records exact offsets,
method hashes, XML identity and replacement bytes. No client runtime files or
native WASM seals changed.

Five new tests read the actual embedded XML from the original SWF, prove the
missing attribute, execute both old and new emitted setup tails, verify the
null-shortcut path and maxstack 3 bound, and execute the unchanged callback with
stub globals to observe exactly one nonsharing local transaction. They also
check original button event ordering, all 68,492 methods/pools/non-code bytes,
prefix/header/callback identity, known-stage upgrade and unknown-body refusal.
Forty-three existing focused client, serving and availability tests cover the
surrounding compatibility chain. Browser persistence acceptance remains a
separate check in the parent’s fresh synthetic fixture.

This repair is separate from the allocation abort documented in
`RuntimeOOM20261024/README.md`. A dead WASM instance still cannot execute a valid
close handler. Fresh-VM checks must distinguish an acknowledged durable reward
from an optimistic popup preview and retain the allocation diagnostics.
