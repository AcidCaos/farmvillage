#!/usr/bin/env python3
"""Prepare the reviewed Ruffle compatibility changes in a copied FarmVille client.

The XML style fix normalizes QName dictionary keys. Tab clicks use their stable
listener host when a label's display object changes during the click. Market changes retain the
complete raw catalog and buildtime indexes while lazily constructing dormant
items, preserve cash/sale, seeds, licenses and gifts, and avoid caching filtered
shop lists. Pure date parsing is memoized; current timezone/DST offsets are still
applied at each call. Empty owned farms run the normal initial world loader.
Cottage graphics use their original first-stage artwork while local craft
state is being created during placement.
Cottage upgrade controls are enabled only for the four Home crafts and the
restored Mistletoe Lane and Cove restaurant crafts.
Unsupported VIP, shipping, storage expansion and Turbo invitations stay hidden.
Automatic cottage reminders are suppressed without acknowledging a feature.
Turbo purchases and Inventory storage upgrades show a local refusal before
constructing an optimistic transaction.
Empty optional prize backgrounds are skipped while valid artwork still loads.
The original source assets are never modified.

Every byte edit and complete input/output body is pinned. Independent comparison
of all 68,492 method bodies reviewed the narrow changes. Java and FFDec were
isolated diagnostic tools; this build step needs only the Python standard library.
Unknown clients fail closed. Already prepared clients are verified idempotently.
"""

from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import struct
import tempfile
import zlib


@lru_cache(maxsize=1)
def _cove_patch():
    # A normal import also lets bundled-runtime dependency discovery include
    # this stage. Standalone staging scripts load us by filename, so resolve
    # the exact sibling when their module search path omits Runtime.
    try:
        import cove_client
        return cove_client
    except ModuleNotFoundError as error:
        if error.name != "cove_client":
            raise
    path = Path(__file__).with_name("cove_client.py")
    spec = importlib.util.spec_from_file_location("farmvillage_cove_client", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


COVE_UPGRADE_EDITS = _cove_patch().EDITS
COVE_UPGRADE_STRING_BYTES = 28
COVE_UPGRADE_BODY_SHA256 = _cove_patch().PATCHED_BODY_SHA256


SOURCE_SHA256 = "1edea7cbecefcb1e1233da207164942f0088a83b87afc9254850f5fcde5034ae"
SOURCE_BODY_SHA256 = "a9b719e6be4ceb40b9136880bfecf08399975f6babf7199db9af2d19a985794d"
STYLE_BODY_SHA256 = "29130263405a7bb27be44bb8abf5c09e0a5fa4e31563ad0abe3ba4823f61cee2"
MARKET_BODY_SHA256 = "edae6c3be651b9d9e4082d68267dd829cc8a8e620213824faee4d7caa4630b1c"
TAB_BODY_SHA256 = "9cb08381610e988c4d944b7ee06d0b7d0bbae2264bc5a988ee94597255afa5d4"
SCRATCH_BODY_SHA256 = "43d624db101b0f343761eca4087819d0fd7c203dcc1d5727a0f90347af299045"
EMPTY_WORLD_BODY_SHA256 = "68152f8c2f5cc22913ff6d3a80d5a4a0c2e054c3d1f80cd3457fbd056eb525de"
COTTAGE_GRAPHICS_BODY_SHA256 = "5b9b7811210904d86ccd672469b4608e55f271c91e0f20102cee39a5ac8a0acf"
COTTAGE_UPGRADE_BODY_SHA256 = "cbbc8d5fac34542697c722d37f7912f7f4a9155162bb09f5b7cd988eb8063f62"
TURBO_BODY_SHA256 = "3a957c0ae98e9f86af41af0f87b925e93aebc49a722feeaa31d252b576569862"
STORAGE_BODY_SHA256 = "4437fffbebb1737cfa3e68b5c2e9fc77e0d67056873378452834591d1fed0eb8"
INVITATION_BODY_SHA256 = "132d826e3f0fd5f55659b3019b4df5e753e30fd239a8b0822c8879e19999cfd5"
VIP_BODY_SHA256 = "2ebd48a123dac7089469d5f570137c6b67ea57094dc03626d70aa40efa0a159c"
MARKET_WALKTHROUGH_BODY_SHA256 = "87ce6267b37dc9dc7a0c2b2e5b8ca7c2be462fefbe2d16fab36bacd4ff64169a"
QUEST_CLOSE_BODY_SHA256 = "8ca832debfa8404c3934f6859321937c546b1b9b398b0dc44fb030ef90e0b504"
UNLABELED_IMAGE_ROW_BODY_SHA256 = "58f4d85146657d5c2ba7c9f6d503e71d22753f8165b8791e72fada9adf353f1c"
IMAGE_ROW_BODY_SHA256 = "2912036e46cde068b13b8e302c0e8d11a3e02911b52629fcce8b32f414089f32"
INVENTORY_ART_BODY_SHA256 = "bd837906218648bfd4edd0f3bf86ae242b6283222aa551d970b51fe444ffb145"
MARKETSTALL_EXPANSION_BODY_SHA256 = "b0200b4ae46a665fb910a329c0137678c74eacf9a0553a17f9cc4b7186e2ddea"
WIDGET_STORAGE_BODY_SHA256 = "c5aaff1f2ef9d60d4d2606ecac81ad7190d3f120b1500fb6b4e1d98ea4bbf589"
REGIONAL_UPGRADE_BODY_SHA256 = "0a1e5b2689cd203c40a8d9694740a0929a88b986172bdf3b0b670baaceb182ed"
PATCHED_BODY_SHA256 = "2200ebcdc58dfa2061ffaf20e58f8c83b1868449a6b8bae8f81395c27a0454c6"
SOURCE_BODY_BYTES = 21_520_483
STYLE_BODY_BYTES = SOURCE_BODY_BYTES + 1
PRE_TURBO_BODY_BYTES = 21_520_934
TURBO_BODY_BYTES = 21_520_991
WIDGET_STORAGE_BODY_BYTES = 21_521_041
PATCHED_BODY_BYTES = 21_521_054
SWF_VERSION = 10
METHOD_CODE_OFFSET = 13_192_476
METHOD_SOURCE_SHA256 = "44d653bb815a7538086e9dd0c1ce1a3b6720f1c54ab8bc6e26e7bc9e822d4595"
METHOD_PATCHED_SHA256 = "5c70f7d43ce3c5c6e577c1f0deb9f1779a9f9246499e1cc60be85e8395a3aee3"

# Offsets address the decompressed SWF body, after the eight-byte SWF header.
# Apply backwards so the inserted instruction cannot shift later edit positions.
EDITS = (
    (3_399_686, b"\x4c", b"\x4d"),  # DoABC tag payload length, +1.
    (13_192_474, b"\xba", b"\xbb"),  # parseStyles code length, 1210 -> 1211.
    (METHOD_CODE_OFFSET + 133, b"\x26", b"\x27"),  # Relocated forward branch.
    (METHOD_CODE_OFFSET + 1045, b"\x87", b"\x88"),
    (METHOD_CODE_OFFSET + 1124, b"\x1e", b"\x1f"),
    (METHOD_CODE_OFFSET + 1146, b"", b"\x70"),  # convert_s after XML.name().
    (METHOD_CODE_OFFSET + 1161, b"\xdb", b"\xda"),  # Relocated backward branch.
    (METHOD_CODE_OFFSET + 1202, b"\xd3", b"\xd2"),
)


# Apply to the verified style-patched body. Preserve the independently reviewed
# constant-pool additions, method operands/lengths, and enclosing DoABC length.
MARKET_EDITS = (
    (3399686, bytes.fromhex('4d25'),
     bytes.fromhex('0f27')),
    (3411801, bytes.fromhex('8f'),
     bytes.fromhex('91')),
    (9457030, bytes.fromhex(''),
     bytes.fromhex('164641524d56494c4c4147455f444154455f43414348451a4641524d56494c4c4147455f4441544554494d455f4341434845')),
    (9644636, bytes.fromhex('fc'),
     bytes.fromhex('ff')),
    (10381884, bytes.fromhex(''),
     bytes.fromhex('0701a1bd0807018ff20a070190f20a')),
    (12023933, bytes.fromhex('030303043cf181d107f0f602d030ef019bd10700f602ef019cd10701f702f0f7025db2d10446b2d10400609fd104a273d6f0f80260c40dd1264696c70402d2a0480000d50a09070304ed02f181d107f08403d030ef019dd107008403ef019cd107018503ef019ed107028703ef019fd107038803ef01a0d107048903ef01a1d107059203f085035db2d10446b2d10400609fd104a273d6'),
     bytes.fromhex('0503030457d030609e1066a3ca0466fdff078001d6d2110f00005500d6609e1066a3ca04d261fdff07d2d146e0d1050111100000d2d160c40dd1264696c7040261eed505d2d166eed505755db2d10446b2d10400609fd104a273a0480000d50a09080304b603f181d107f08403d030ef019dd107008403ef019cd107018503ef019ed107028703ef019fd107038803ef01a0d107048903ef01a1d107059203f085035db2d10446b2d10400609fd104a273d6609e1066a3ca0466feff078001630762071111000055006307609e1066a3ca04620761feff076207d146e0d10501120e00006207d166eed50575630610220100')),
    (12024365, bytes.fromhex(''),
     bytes.fromhex('6207d1620661eed505')),
    (12264816, bytes.fromhex('830af1b5de07f0dc0fd0302400d724007463042085630520856306208563072080a701630820856309208001630a2080dc01630b208037630c28630def019bf10100dc0fef01ade00701dc0ff0dd0fd066871d11aa'),
     bytes.fromhex('d70af1b5de07f0dc0fd0302400d724007463042085630520856306208563072080a701630820856309208001630a2080dc01630b208037630c28630def019bf10100dc0fef01ade00701dc0ff0dd0fd066871d11fe')),
    (12265384, bytes.fromhex('db0100f0fc0f60e81c46f3d90400129a0000f0fd0fd0668b1d66984b746304f0fe0fd0668d1d62040c7c0000106b000009ef01aae007098010f08010d0668b1dd0668d1d66d1da058001630af08110620a120d0000f08210d0202620620a4fdf1d04f08410d02a630e668d1dc0630f620e620f618d1d080f080ef08810d1962a120c0000295debd10546ebd10500d3b012070000f08910100d0000f0ff0fd0668d1d62041588'),
     bytes.fromhex('2f0200f0fc0f60e81c46f3d9040012ee0000f0fd0fd0668b1d66984b746304f0fe0fd0668d1d62040cd0000010bf000009ef01aae007098010f08010d0668b1dd0668d1d66d1da058001630af08110620a1261000060aa2866eadb0412490000620a66f4362cf2bf031a3c0000620a66ca3611330000620a66f91f2c9d0e19270000620a66cf372c8ae707191a0000620a66fcff0711100000620a66fa362cf52819040000100d0000f08210d0202620620a4fdf1d04f08410d02a630e668d1dc0630f620e620f618d1d080f080ef08810d1962a120c0000295debd10546ebd10500d3b012070000f08910100d0000f0ff0fd0668d1d62041534')),
    (12278406, bytes.fromhex('0b0506ad02'),
     bytes.fromhex('0f0506f603')),
    (12278546, bytes.fromhex('9d00'),
     bytes.fromhex('6601')),
    (12278673, bytes.fromhex('1e0000f0cb1a'),
     bytes.fromhex('e70000f0cb1a620512c3000056008008630b2400630c109a0000096206620c66beee0585630ed066891d620e66beee058001630d620d126f0000620d66f4362cf2bf031a620000620d66ca3611590000620d66f91f2c9d0e194d0000620d66cf372c8ae70719400000620d66fcff0711360000620d66fa362cf528192a0000d066891d620e2c9b8d03a066beee0511170000d066891d620e2c82da06a066beee051104000010090000620b620e4fa38d0201c20c620c620666984b155bffffd0620b2646ec1d0280086306101b0000')),
)

# FarmTabMenu.onItemClick receives the event synchronously from each tab's
# ZwButton listener. A label can be detached while its pressed/selected artwork
# changes, so event.target can lose the ancestry used to identify the tab.
# currentTarget remains the tab that registered the listener. Replacing the
# debugline with two NOPs accommodates the longer multiname operand without
# moving any instructions after this span, branches, or exception boundaries.
TAB_METHOD_CODE_OFFSET = 15_964_221
TAB_METHOD_CODE_BYTES = 188
TAB_METHOD_SOURCE_SHA256 = "198c73715b5a5210269a2336d45f8a484912ea44736a09d7b3fc307138e6a1f6"
TAB_METHOD_PATCHED_SHA256 = "886dd0e5eab8fb3be2305d0509afb1ec910cfffb401e729f10178f0657a33174"
TAB_EDITS = (
    (TAB_METHOD_CODE_OFFSET + 90,
     bytes.fromhex("f0b10260fb11d366d627601987d1668227"),
     bytes.fromhex("020260fb11d366d627601987d166aad205")),
)

# The original Scratch-Off coin artwork embeds million amounts. Preserve
# those two branches and use the existing amount-free HUD coin artwork for
# every other value, returning the actual quantity to the original labels.
# Only this coin block changes. The method's length, other reward branches,
# switch targets and exception table remain intact; ten NOPs fill the span.
SCRATCH_METHOD_CODE_OFFSET = 15_136_881
SCRATCH_METHOD_CODE_BYTES = 573
SCRATCH_METHOD_SOURCE_SHA256 = "62b2e720c51c5b066e8a5fb6bf66c5cc0b37040770a295ad6a5f6f0b271b773e"
SCRATCH_METHOD_PATCHED_SHA256 = "8e7ae5bb3b562df8773d54fac2934b44c4c18b0a4c1ce47ee0a75ed02decaee6"
SCRATCH_EDITS = (
    (SCRATCH_METHOD_CODE_OFFSET + 233,
     bytes.fromhex("09f0b7065d185d9ad205d22c9d0566baaf06469ad20501461801736304f0b906620460e98e0514110000f0ba06d160e88e054fe6e00201101a0000f0bb06620460eb8e05140d0000f0bc06d160ea8e054fe6e00201f0c00624016304f0c10610eb0000"),
     bytes.fromhex("095d9ad205d22c9d0566baaf06469ad20501736304620460e98e0513180000620460eb8e05131d0000d12c8884074fe6e002011017010009d160e88e054fe6e00201100b000009d160ea8e054fe6e002012401630410f5000002020202020202020202")),
)

# Original populated starts made objectsArray.length > 0 a valid initial-load
# assumption. Disclosed empty local England/Meadows starts need the same loader
# on login as on live travel. Keep both world/array presence checks and change
# only the length comparison to >= 0; no objects, unlocks or rules are invented.
EMPTY_WORLD_METHOD_CODE_OFFSET = 12_175_869
EMPTY_WORLD_METHOD_CODE_BYTES = 521
EMPTY_WORLD_METHOD_SOURCE_SHA256 = "b712b81b3e2d1350d54c8c2d3090200eb2cb2e53c5ed740ba45890fa649144f3"
EMPTY_WORLD_METHOD_PATCHED_SHA256 = "bd58dca86ebdc063802487331405eba2ef7deefceb114268ba09df567469fbae"
EMPTY_WORLD_EDITS = (
    (EMPTY_WORLD_METHOD_CODE_OFFSET + 340, b"\xaf", b"\xb0"),
)

# Building.build reloads its image before CraftingCottageBuilding.onBuilt
# starts the local CraftTypeState. The owner getter returns 0 in that brief
# interval, selecting nonexistent built_-1 artwork. Clamp only the rendering
# suffix to its first stage. Keep craft ownership, saved levels, recipes and
# production untouched. The original 32-byte method and maxstack=2 suffice;
# debug-variable/line entries make room for the forward-only clamp branch.
COTTAGE_METHOD_CODE_OFFSET = 14_892_734
COTTAGE_METHOD_CODE_BYTES = 32
COTTAGE_METHOD_SOURCE_SHA256 = "32ed6f91f7fc4a7a61bfd3a08ca4939629a597cab17f3b1de3c00a3f95d19f42"
COTTAGE_METHOD_PATCHED_SHA256 = "e1c7413d337634c3b55cd994beb3bc091b249dc3dabb3e8815d1c14cc1bddc7a"
COTTAGE_EDITS = (
    (COTTAGE_METHOD_CODE_OFFSET,
     bytes.fromhex("f18ce008f0a702d030ef01850300a802f0a802d0669b9e019373d5f0a902d148"),
     bytes.fromhex("f18ce008f0a702d030d0669b9e019373d5d1240018030000240048d148020202")),
)

# Original skill progress and prices remain intact. Only the two branches
# that show unsupported cash/coin upgrade buttons now hide them, matching
# the four existing false branches in updateUpgradeFrame. Replace a debug
# line with an archived empty-string assignment for upgrade-only text/tooltip.
# No service, saved
# craft level, recipe eligibility or reward state is implied by this UI gate.
COTTAGE_UPGRADE_METHOD_CODE_OFFSET = 16_464_646
COTTAGE_UPGRADE_METHOD_CODE_BYTES = 1155
COTTAGE_UPGRADE_METHOD_SOURCE_SHA256 = "e42e444a2c7ae2c489355cf747e42f47166dfa7d139bd666cb819b3e2e5ea46b"
COTTAGE_UPGRADE_METHOD_PATCHED_SHA256 = "300a7f4c2da1dcdde1ba8982e95556ca53e554bdb5ffbaf82748baef90945d98"
COTTAGE_UPGRADE_EDITS = (
    (COTTAGE_UPGRADE_METHOD_CODE_OFFSET + 683, b"\x26", b"\x27"),
    (COTTAGE_UPGRADE_METHOD_CODE_OFFSET + 796, b"\x26", b"\x27"),
    (COTTAGE_UPGRADE_METHOD_CODE_OFFSET + 989, b"\xf0\xcd\x06", b"\x2c\x01\xd5"),
)

# TurboItem.onBuy previously constructed TBuyTurboChargers before returning.
# That constructor optimistically grants turbo and subtracts cash/coins before
# its unsupported server call, whose FORCE_RELOAD proved silent in the browser.
# Show the existing TYPE_OK popup and return false before that construction.
# Keep its method length, header/maxstack, exception table and every other method
# byte-identical. Append one literal to the string pool without renumbering any
# existing entry; adjust only its count and the enclosing DoABC length.
TURBO_METHOD_CODE_OFFSET = 13_768_994  # Before the new string is inserted.
TURBO_METHOD_CODE_BYTES = 140
TURBO_METHOD_SOURCE_SHA256 = "244274d33fabe78bbf06ae0e9805ae6186720e1c249c1a8aa8f72c8306e60187"
TURBO_METHOD_PATCHED_SHA256 = "739bbdac93df25ff6516e9f3ee3c73e6ebd005aaf9dcd69063586e543a798ba3"
TURBO_MESSAGE = "Turbo charger purchases are not restored on this server."
TURBO_STRING_INDEX = 178_449
TURBO_STRING_BYTES = 57
TURBO_EDITS = (
    (3_399_686, bytes.fromhex("0f271401"), bytes.fromhex("48271401")),
    (3_411_801, bytes.fromhex("91f20a"), bytes.fromhex("92f20a")),
    (9_457_080, b"", bytes([len(TURBO_MESSAGE)]) + TURBO_MESSAGE.encode("ascii")),
    (TURBO_METHOD_CODE_OFFSET,
     bytes.fromhex("f1e9b508f021d030ef01a45e0021ef01ef570121ef0199de070222f02226d7f026609e1066c85546bf300020ab2a1213000029609e1066b2ca0466cf1a60fc3066cbe104ab122c0000f02760d71b609e1a2ce40a2cebb30846aec1010260c50166a5c904202c01264fb4d70405f02827d710130000f02a60315dd68a02d1274ad68a02024f9f1701f02cd348"),
     bytes.fromhex("f1e9b508f021d03060d71b2c91f20a60c50166a5c904202c01264fb4d704052748") + b"\x02" * 107),
)

# InventoryWithdrawal's free and paid expansion entry points previously opened
# confirmations that scheduled TUpgradeStorage; its paid callback also upgraded
# the local building before the refused reply. Reject before disabling buttons,
# creating a transaction, or changing the item/capacity. Only these two Inventory
# entry methods change; storage reads, withdrawals and material construction stay
# intact. Keep method lengths, headers, maxstack and exception tables unchanged.
STORAGE_MESSAGE = "Storage upgrades are not restored on this server."
STORAGE_STRING_INDEX = 178_450
STORAGE_STRING_BYTES = 50
STORAGE_METHODS = (
    (12421, 13_552_022, 253,
     "bca71d88c18856c95e0ae1e8726986fbd6f0cf9bc3eda1e7fee31340d657155e",
     "2876f92325489e2f5c9d7a45830929023b8d372ff63423be850aedf00026026e"),
    (12423, 13_552_415, 475,
     "4c8603f268482e9790db287fb200603c489919df0b806c67b7164e698453e51a",
     "2fe3bdfe08cc453ebe02c47c218f3a1db417fd83bd630a84c21a8ada20a557a0"),
)
STORAGE_EDITS = (
    (3_399_686, bytes.fromhex("48271401"),
     bytes.fromhex("7a271401")),
    (3_411_801, bytes.fromhex("92f20a"),
     bytes.fromhex("93f20a")),
    (9_457_137, bytes.fromhex(""),
     bytes.fromhex("3153746f7261676520757067726164657320617265206e6f7420726573746f726564206f6e2074686973207365727665722e")),
    (13_552_022, bytes.fromhex("f1caa608f0c205d030ef01ac3d00c205ef01b2840201c405ef01cfe60702c805ef01c4950803c905f0c305d0264fd66001f0c405609e1a2ce40a2c98a70846aec1010285d6f0c605d0d14fc46001f0c805609e106684ca042cfaf70746ad1d0173d7f0c905609e1066c855d066af6066de840646e02e0160c9018780c9016304f0cb05d3609e106680ca0446a32400d046cb6000a0ad2a1208000029620446ff5c007612380000f0cc05609e1a2ce40a2c99a7082cfa4bd3550146aec1010385d6f0cd0560d71bd260c50166a9c904d066c9602c01264fb4d70405101a0000f0cf0560d71bd260c50166a9c904d066c9602c01264fb4d70405f0d10547"),
     bytes.fromhex("f1caa608f0c205d03060d71b2c92f20a60c50166a5c904202c01264fb4d704054702020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202")),
    (13_552_415, bytes.fromhex("f1caa608f0e205d0302080c901d7ef01ac3d00e205ef019aa70801e505ef01dc1b02ea05ef01a1f30703ef05ef01b2840204f405ef01cfe60705f705ef01dc1b02f805f0e305d0264fd66001f0e505609e106684ca042ce99f08240a46af1d0273d6f0e605609e106680ca04669f2566fe8406121a0000f0e705d25d18609e106680ca04669f2566c18406461801a173d6f0ea05d066a96080c901d7f0eb05d320141d0000f0ec05609e1066c855d066af6066de840646e02e0160c9018780c901d7f0ef05609e106684ca04d346a8170046f5370046ee1d0180a7016304f0f10562046689102c9ba70846e9d1050124000f0a0000f0f205620466b41473d6f0f405609e1a2ce40a2c9ca7082cfa4bd2550146aec10103856305f0f505d0d14fc46001f0f705609e106684ca042cfaf70746ad1d01736306f0f805609e1066c855d066af6066de840646e02e0160c9018780c901d7f0fa056206609e106680ca0446a32400d046cb6000a0ad2a1207000029d346ff5c007612400000f0fb05609e1a2ce40a2c9da7082cfa4b62062c9e9008d2550246aec10103856305f0fc0560d71b620560c50166a7c904d066cc602c01264fb4d70405101b0000f0fe0560d71b620560c50166a7c904d066cc602c01264fb4d70405f0800647"),
     bytes.fromhex("f1caa608f0e205d03060d71b2c92f20a60c50166a5c904202c01264fb4d704054702020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202")),
)

# Restore paid upgrades only for bakery/winery/perfumery/pub. The star-loop
# counter local is no longer read after the loop, so its debug-variable span can
# hold the supported-type predicate. Use only archived strings/multinames;
# "pub" is the suffix of the original "xukcraftingpub" constant. Preserve the
# original prices, XP progress, level cap, prerequisites, tooltips and callbacks.
# Hide unsupported invitations at their rendering/entry points. Inventory opens
# on its original inventory section; its other two tabs and storage expansion
# menu entry stay hidden. Turbo onboarding and automatic cottage reminders return
# before action-count/seen-flag access. Manual free-cottage acquisition remains.
# All edits are within method code; pools, headers, maxstack, branches, exception
# boundaries, source assets and every unlisted method remain byte-identical.
INVITATION_METHODS = (
    (5911, 12_636_357, 99,
     "4146e7d7f1e4a038218f4e06d3b1ba2453d8dc15b10818a21844ca3d5a585065",
     "f8be7b1741dcd9499063291718af35abdb7425593c029e1a31e542c08743eb85"),
    (11244, 13_384_937, 208,
     "e53adf0a4d059cec5e4c57a8c964c6e3508a7e2d90a6d46ae46c21991c0d990c",
     "c2de58acd666c64681f22ee3620e1b93300b74ec33a174ca9b2b212a76069b93"),
    (11987, 13_480_015, 289,
     "acecf9e4cc2450335e862bdafe8f191fc374f01f922aec78d9e5fbbbe5ff0bbd",
     "0b0dfdf3f7cc24bdf9bdd9cd68615bb356029db57103720c9ecd8e868240df33"),
    (12394, 13_543_075, 65,
     "c9c654f24b60bc4086105f1c2cd3ad8049d913dcbe821e667761eedc7f61312c",
     "458852c5e5254a3790fa7719e436178c5bfc6fd4ce71493157c76e7a3d9e8772"),
    (12402, 13_544_516, 197,
     "fcac7307c94c7670e3f8d4f879aacad0a4122d643aeb87c0a074c13224ec3eb2",
     "d285d143485d051dd485533fc16233d5379ba547d6814c08e7423962915b616f"),
    (12403, 13_544_723, 942,
     "2abcb97e4a5956f99b5f992ab3ea6c64c221cfb7fd70808d5dcdf248e738c3f3",
     "f5ccf1701c096dbb91ba7b578a7431557b3d785ca8f011b09d7e8678a8d6d7ed"),
    (34693, 16_464_753, 1155,
     "300a7f4c2da1dcdde1ba8982e95556ca53e554bdb5ffbaf82748baef90945d98",
     "4716eef39fa36fd8f39173dd8dbd1085b655185ff403eeea71f4fdd1b3f6a53e"),
    (38972, 17_013_456, 95,
     "eb953483f7fb8587734b7afcd75f75e9b6bfff26ba1f9f0dbe3c19b774bf6be6",
     "8bf8b733e34d9c292eacad15fe86819065260fac1330697bf1def03eb30b356b"),
)
INVITATION_EDITS = (
    (12_636_366, bytes.fromhex("ef01b7f60700e21df0e21d609e1066b2ca0466cf1a60fc3066cbe104abd5f0e31dd1762a1206000029d066c331962a1209000029d046db32002400ab12160000f0e41dd02c939e0127264fd03203f0e51dd02668c331f0e71d47"),
     bytes.fromhex("470202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202")),
    (13_385_060, bytes.fromhex("26"),
     bytes.fromhex("27")),
    (13_480_227, bytes.fromhex("d1"),
     bytes.fromhex("27")),
    (13_543_133, bytes.fromhex("26"),
     bytes.fromhex("27")),
    (13_544_612, bytes.fromhex("d0d268b160f05b"),
     bytes.fromhex("d02cc20e68b160")),
    (13_545_124, bytes.fromhex("f08d01d2264fc52701"),
     bytes.fromhex("d266b2272761dd2702")),
    (13_545_214, bytes.fromhex("f09401d2264fc52701"),
     bytes.fromhex("d266b2272761dd2702")),
    (16_465_142, bytes.fromhex("ef01b6980807b106ef01c4b40908b206ef01c5b40909b306ef01c6b4090ab406ef01cbfd080bb506ef01c7b4090cb606"),
     bytes.fromhex("2cbd85072cbf85072cc185072ca89807240b46ead105015604d066f4ec0166cd3746e9d105012400b063060202020202")),
    (16_465_436, bytes.fromhex("2761aad306f0bc06"),
     bytes.fromhex("620661aad3060202")),
    (16_465_549, bytes.fromhex("2761aad306f0c206"),
     bytes.fromhex("620661aad3060202")),
    (16_465_742, bytes.fromhex("2c01d5"),
     bytes.fromhex("f0cd06")),
    (17_013_464, bytes.fromhex("ef0185030030ef01c7280131f03027d5f031609e106680ca046091ad05468a260173d6f032d26092ad050d160000f033609e106680ca046091ad05264f862602f034c202f036d26092ad0514040000f03726d5f039d148"),
     bytes.fromhex("274802020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202")),
)


# VIPFTUE artwork is visible by default even when VIPSalesManager.isEnabled()
# is false. The original outer gate then skipped both hide assignments. Preserve
# the artwork-presence branch, bypass only that sales-service condition, hide the
# existing clip and return before the seen-flag/tutorial code. Existing branch
# operands remain unchanged; the return replaces a debugline. No flags are set.
VIP_METHOD_ID = 11244
VIP_METHOD_CODE_OFFSET = 13384937
VIP_METHOD_CODE_BYTES = 208
VIP_METHOD_SOURCE_SHA256 = "c2de58acd666c64681f22ee3620e1b93300b74ec33a174ca9b2b212a76069b93"
VIP_METHOD_PATCHED_SHA256 = "229c9319c8ac2425198ec60c1ef2304ef431144cdfe5553e0b7494d729d0cf21"
VIP_EDITS = (
    (13_384_963, bytes.fromhex("609e106695ca0446ca2b0076"),
     bytes.fromhex("260202020202020202020202")),
    (13_385_018, bytes.fromhex("f0f022"),
     bytes.fromhex("470202")),
)


# The full Market3 walkthrough is a separate renderer from VIPFTUE_mc. Its
# ftueMedium_mc/ftueSmall_mc artwork also advertises VIP Friday sales. Keep the
# original market-size/clip-presence selection and hide, then return before any
# seen-state read, tutorial frame change or button construction. This replaces
# one debugline only; Market columns, tabs, search and purchase controls remain.
MARKET_WALKTHROUGH_METHODS = (
    (11246, 13_385_213, 318,
     "b259c0601c87fefe057ddf8b0137e12939d9df8c83335ed42cdbe737f19deb1a",
     "0c578664210e8b4fae6d914a83fd41beb5c3ac0c6d42d5bbf8bf689d7425aef0"),
)
MARKET_WALKTHROUGH_EDITS = (
    (13_385_354, bytes.fromhex("f08f23"),
     bytes.fromhex("470202")),
)


# questRewardView pins CloseButtonView on its unnamed outer Mask. Its named
# content Resize has no viewToPin, so the original setup silently skipped the
# local close/reward acknowledgment listener. Bind the existing close shortcut
# directly using DynamicDialog.setShortcutListener's null-guarded lookup/coerce/
# listen semantics. Inline them to retain setup's maxstack3 (calling the helper
# with receiver+three args would need4). Reuse local1; the original reward list,
# header/avatar/share setup and onCloseButtonPress transaction stay unchanged.
QUEST_CLOSE_METHODS = (
    (23979, 15_053_220, 156,
     "a91b2c37bd1ab3de89918cc8b223f3a7ccb2c30c362de5a93ef20e89dc1a3a19",
     "b9543885ede2a11b1f5f1d5e9edd49637651502abb807f5c21a6b241b6dbfaa3"),
)
QUEST_CLOSE_EDITS = (
    (15_053_315, bytes.fromhex("d02cfd3146c3510160a1dd026692b50546ad1d01808a03d5f0c501d12013180000f0c601d146ff4f0060b60166e8ee04d066fea6014f945102"),
     bytes.fromhex("d02cbfe90746c351018091032ad512270000d160b60166e8ee04d066fea6014f94510202020202020202020202020202020202020202020202")),
)


# createImageObject previously rebuilt the full Opt wrapper array for every
# selected image. For Opt array input, select the raw row via getAttributesHash,
# reuse an Opt wrapper or construct one selected wrapper. Non-Opt/singleton
# input retains the original getArray/index/coerce path. No data is removed,
# cached or mutated. Debug spans hold balanced out-of-line blocks. Every new
# backwards target begins with Label, as required by the pinned AVM2 verifier.
# Header/maxstack5/locals11, method length1174 and metadata/XML176+ are intact.
IMAGE_ROW_METHODS = (
    (6230, 12_683_818, 1174,
     "af263f5cc28d82f6f2e6bb46d2a99e3ac96dd384532fccd23d1881b73ff22269",
     "36984b5ed17ee328ee48fc2a1f4b43b1228a53899d57fc55c964dda5fd096db3"),
)
IMAGE_ROW_EDITS = (
    (12_683_847, bytes.fromhex("ef01f0930400eb06ef01ac1b01eb06ef01b41a02eb06ef01dfa40403eb06ef01def80704eb06ef01d2a80105ec06f0ec06"),
     bytes.fromhex("102d0000095d966962084a9669016308107f000009d066de342cd2a80146916901d2669ce90580dd016308106400000202")),
    (12_683_936, bytes.fromhex("ef01dff80706f306ef01e0f80707f406ef019de20708f606f0f306d066de342cd2a8014691690180086307f0f4066207d2669ce90580dd016308"),
     bytes.fromhex("d066de34609669b312afffffd066de344695690066de6e86082a6307129bffff6207d2669ce9052a6308609669b3110800001075ffff02020202")),
)

# Accept and repair the briefly staged, verifier-rejected unlabelled draft.
UNLABELED_IMAGE_ROW_METHOD_SHA256 = "a5a79e86aa6e0bf6400bda6526967b6038d566ff9e2041c5e0e9218e91b61387"
IMAGE_LABEL_EDITS = (
    (12_683_847, bytes.fromhex("102a00005d966962084a966901630810800000d066de342cd2a80146916901d2669ce90580dd0163081066000002f0ec06"),
     bytes.fromhex("102d0000095d966962084a9669016308107f000009d066de342cd2a80146916901d2669ce90580dd016308106400000202")),
    (12_683_936, bytes.fromhex("d066de34609669b312aeffffd066de344695690066de6e86082a6307129affff6207d2669ce9052a6308609669b3110800001075ffff02020202"),
     bytes.fromhex("d066de34609669b312afffffd066de344695690066de6e86082a6307129bffff6207d2669ce9052a6308609669b3110800001075ffff02020202")),
)


# GenericButton.m_overlay is a transparent hit rectangle added as a sibling
# of its target artwork. Hiding it alone prevented clicks but left the original
# Expand/Shipping invitation art visible. Hide both layers through the original
# public storage_mc button paths; use only their obsolete localization spans.
# The Inventory button/content, category mappings and forced Inventory section
# remain unchanged. Method942 bytes/header/maxstack/branches/pools are intact.
INVENTORY_ART_METHODS = (
    (12403, 13_544_723, 942,
     "f5ccf1701c096dbb91ba7b578a7431557b3d785ca8f011b09d7e8678a8d6d7ed",
     "0673ee146deb3ece8f10e43f28fe8cecd1093d4ba474e175240b76dc2264338e"),
)
INVENTORY_ART_EDITS = (
    (13_545_124, bytes.fromhex("d266b2272761dd2702f08e01d2609e1a2ce40a2ce3a60846aec1010261c227"),
     bytes.fromhex("d266b2272761dd270260840f66c3840666c984062761dd2702020202020202")),
    (13_545_214, bytes.fromhex("d266b2272761dd2702f09501d2609e1a2ce40a2ca3a40846aec1010261c227"),
     bytes.fromhex("d266b2272761dd270260840f66c3840666ca84062761dd2702020202020202")),
)


# MarketStall expansion has unaccepted material/social stages and the server
# rejects its complete-now transaction. Hide only this class's expansion
# invitation and refuse both direct expansion entries before callbacks,
# optimistic capacity changes, transactions or cash subtraction. Reuse the
# already reviewed Inventory storage refusal literal/UI call; pools, headers,
# scopes, method lengths, exception data and all stall management are intact.
MARKETSTALL_EXPANSION_METHODS = (
    (22845, 14_922_295, 327,
     "5baed6b410b5983855a43f8c42aa02f2f14cd1d0d2d8d15198f8dc1185954a12",
     "c8b0630b22d38ba4c26988e9919955308c50dfc408190a7890c99925d0e8cffd"),
    (22858, 14_923_428, 19,
     "62e492e4bce88cfd4f216c71ce13c590dea2113e9fb62c2925672eca3b273f85",
     "0044d0b3f45939ffeb87561bf88f79faae822da505c6f37c8d1a3aa892e11783"),
    (22903, 14_929_333, 205,
     "7c7eef19f0e2e9cd604d7361eeb615e3f922ea05ce3f6d13ae1cc357ea40bf9b",
     "3d15e8dca59e20210617b37e0d975c9e22d8536b533dab74c3828f68bf208ede"),
)
MARKETSTALL_EXPANSION_EDITS = (
    (14_922_295, bytes.fromhex("f1eee108f0a301d03020856305ef01b53c00a301ef0187c00401a301ef01efe10802a301ef01b4df0803a401f0a401d046b19f0100756304f0a501620424000e000100ef0196f60204a901f0a601d0d268a19f01f0a701d0d368a29f01f0a8016096182cf9e6022c97f5072c929b012c9794014f963804f0a9015dad1746ad1700856305f0aa01609e1a2ce40a2c8a94012c9409a05da91746a91700a046ced5040212580000f0ab0160d71bf0ab01609e1a2ce40a2c8a94012c9409f0ab01a05da91746a91700a02ca9ac08f0ac017062042cfa3a609e1a620546d9d50401550246aec1010360c50166a6c904d066a39f012c01264fb4d7040510450000f0ae0160d71bf0ae01609e1a2ce40a2c8a94012ca9ac08f0af017062042cfa3a609e1a620546d9d50401550246aec1010360c50166a6c904d066a39f012c01264fb4d70405f0b20147"),
     bytes.fromhex("f1eee108f0a301d03060d71b2c92f20a60c50166a5c904202c01264fb4d7040547020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202")),
    (14_923_428, bytes.fromhex("f1eee108f0bd02d030f0be02d046b05d009648"),
     bytes.fromhex("f1eee108f0bd02d030f0be0227480202020202")),
    (14_929_333, bytes.fromhex("f1eee108f0e307d030ef01ce910100e307ef01b4df0801e407f0e40760d98a0546b19f010075d6f0e507d224000e980000f0e607609e106680ca04d246f4250112850000f0e707d046ee5d002614780000f0e8075d9f175ddad602d020d14adad602034f9f1701f0e907609e106692ca04609f1066a7cd0446982a0124000e2e0000f0ea0760961824642cdda0072cb68e015da91746a9170060af5d4690d20500a02ceffa06d24690d205004f951006f0ec07609e106680ca04609e106680ca0466b414d2a161b414f0f00747"),
     bytes.fromhex("f1eee108f0e307d03060d71b2c92f20a60c50166a5c904202c01264fb4d704054702020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202")),
)


# Ordinary Inventory uses the newer Widgets StorageWindow, selected by
# UI.displayInventoryDialog's inventory branch. The legacy InventoryWithdrawal
# hides do not run there. Keep both original widget constructions but register
# their visibility=false via the existing addWidget(widget, visible) contract.
# This hides complete artwork and input, for both transfer asset variants.
# Only the two visibility argument expressions in postLoadComplete change;
# all market/storage data, categories, search, travel and withdrawal stay intact.
WIDGET_STORAGE_METHODS = (
    (12193, 13_510_179, 2711,
     "7517193c2acda5699b3967caa37bace13778916ae8bd5e0436a159d21f1cbf58",
     "2981b637ccc6e6f750251ee179ec43a4c94711bbfb1f5764aea0bd18db39b985"),
)
WIDGET_STORAGE_EDITS = (
    (13_510_941, bytes.fromhex("5dcef70446cef70400"), bytes.fromhex("270202020202020202")),
    (13_511_325, bytes.fromhex("26"), bytes.fromhex("27")),
)


# Regional stage: preserve all earlier pool indexes and offset-sensitive edits.
# Append only xhdcrafttype, then add that exact fifth entry to the existing
# updateUpgradeFrame predicate. Four of its five NOPs fit the pushstring;
# method length, branches, exception table and max_stack=13 stay unchanged.
# The predicate's peak remains five. No price, level, prerequisite or callback
# changes: the original upgrade paths consume this same supported-type result.
REGIONAL_UPGRADE_STRING_INDEX = 178_451
REGIONAL_UPGRADE_STRING_BYTES = 13
REGIONAL_UPGRADE_METHOD_CODE_OFFSET = 16_464_753  # Before this pool append.
REGIONAL_UPGRADE_METHOD_CODE_BYTES = 1155
REGIONAL_UPGRADE_METHOD_SOURCE_SHA256 = "4716eef39fa36fd8f39173dd8dbd1085b655185ff403eeea71f4fdd1b3f6a53e"
REGIONAL_UPGRADE_METHOD_PATCHED_SHA256 = "e76391ac236973e0aba013f1e1137c0f4f77a9d5a6a3fbf48656a5440bbb378e"
REGIONAL_UPGRADE_EDITS = (
    (3_399_686, bytes.fromhex("7a271401"), bytes.fromhex("87271401")),
    (3_411_801, bytes.fromhex("93f20a"), bytes.fromhex("94f20a")),
    (9_457_187, b"", bytes.fromhex("0c786864637261667474797065")),
    (REGIONAL_UPGRADE_METHOD_CODE_OFFSET + 389,
     bytes.fromhex("2cbd85072cbf85072cc185072ca89807240b46ead105015604d066f4ec0166cd3746e9d105012400b063060202020202"),
     bytes.fromhex("2cbd85072cbf85072cc185072ca89807240b46ead105012c93f20a5605d066f4ec0166cd3746e9d105012400b0630602")),
)


# PostBuildingCompleteWindow54167 accepts an optional String background. The
# original null-only branch also loads an absent catalog field converted to
# an empty String, which LoadingManager rejects before any network request.
# convert_b; iffalse skips null/empty while retaining every nonempty URL.
# Exactly two same-width opcodes change; the branch operand/target150, stack
# header, exception table, pools and all other methods remain unchanged.
OPTIONAL_BACKGROUND_METHOD_CODE_OFFSET = 19_292_662
OPTIONAL_BACKGROUND_METHOD_CODE_BYTES = 153
OPTIONAL_BACKGROUND_METHOD_SOURCE_SHA256 = "9728fe58078b1f8c3a43b173841726186039ad970b93d3ed77af41718d869cb9"
OPTIONAL_BACKGROUND_METHOD_PATCHED_SHA256 = "edf343bf48a2082c0dc596123cf842bc812d36255ac13feb65bf632eaec3880d"
OPTIONAL_BACKGROUND_EDITS = (
    (OPTIONAL_BACKGROUND_METHOD_CODE_OFFSET + 102, bytes.fromhex("2013"), bytes.fromhex("7612")),
)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_body(data: bytes) -> bytes:
    if len(data) < 8 or data[:3] != b"CWS" or data[3] != SWF_VERSION:
        raise ValueError("Expected the supported compressed SWF version 10 client.")
    declared_size = struct.unpack_from("<I", data, 4)[0] - 8
    if declared_size not in (SOURCE_BODY_BYTES, STYLE_BODY_BYTES, PRE_TURBO_BODY_BYTES,
                             TURBO_BODY_BYTES, WIDGET_STORAGE_BODY_BYTES, PATCHED_BODY_BYTES):
        raise ValueError("Unsupported FarmGame.swf size; refusing to modify unknown game code.")
    decoder = zlib.decompressobj()
    try:
        body = decoder.decompress(data[8:], PATCHED_BODY_BYTES + 1)
    except zlib.error as error:
        raise ValueError("FarmGame.swf has an invalid compressed body.") from error
    if (len(body) != declared_size or not decoder.eof
            or decoder.unused_data or decoder.unconsumed_tail):
        raise ValueError("FarmGame.swf has a truncated, oversized, or trailing compressed body.")
    return body


def _apply_edits(body: bytes, edits) -> bytes:
    for offset, expected, replacement in reversed(edits):
        if body[offset:offset + len(expected)] != expected:
            raise ValueError("A reviewed client patch location did not match its expected bytes.")
        body = body[:offset] + replacement + body[offset + len(expected):]
    return body


def patch_client_bytes(data: bytes) -> bytes:
    """Return the reviewed client, accepting known prior prepared builds."""
    cove_client = _cove_patch()
    if cove_client.is_prepared(data):
        return data
    body = _read_body(data)
    body_digest = _digest(body)
    if body_digest == PATCHED_BODY_SHA256:
        return cove_client.prepare(data)
    if body_digest == REGIONAL_UPGRADE_BODY_SHA256:
        return _finish_optional_background_patch(data, body)
    if body_digest == WIDGET_STORAGE_BODY_SHA256:
        return _finish_regional_upgrade_patch(data, body)
    if body_digest == MARKETSTALL_EXPANSION_BODY_SHA256:
        return _finish_widget_storage_patch(data, body)
    if body_digest == INVENTORY_ART_BODY_SHA256:
        return _finish_marketstall_expansion_patch(data, body)
    if body_digest == IMAGE_ROW_BODY_SHA256:
        return _finish_inventory_art_patch(data, body)
    if body_digest == UNLABELED_IMAGE_ROW_BODY_SHA256:
        return _finish_image_labels_patch(data, body)
    if body_digest == QUEST_CLOSE_BODY_SHA256:
        return _finish_image_row_patch(data, body)
    if body_digest == MARKET_WALKTHROUGH_BODY_SHA256:
        return _finish_quest_close_patch(data, body)
    if body_digest == VIP_BODY_SHA256:
        return _finish_market_walkthrough_patch(data, body)
    if body_digest == INVITATION_BODY_SHA256:
        return _finish_vip_patch(data, body)
    if body_digest == STORAGE_BODY_SHA256:
        return _finish_invitation_patch(data, body)
    if body_digest == TURBO_BODY_SHA256:
        return _finish_storage_patch(data, body)
    if body_digest == COTTAGE_UPGRADE_BODY_SHA256:
        return _finish_turbo_patch(data, body)
    if body_digest == COTTAGE_GRAPHICS_BODY_SHA256:
        return _finish_cottage_upgrade_patch(data, body)
    if body_digest == EMPTY_WORLD_BODY_SHA256:
        return _finish_cottage_graphics_patch(data, body)
    if body_digest == SCRATCH_BODY_SHA256:
        return _finish_empty_world_patch(data, body)
    if body_digest == TAB_BODY_SHA256:
        return _finish_scratch_patch(data, body)
    if body_digest == MARKET_BODY_SHA256:
        market = body
    else:
        if body_digest == STYLE_BODY_SHA256:
            styled = body
        else:
            if _digest(data) != SOURCE_SHA256 or body_digest != SOURCE_BODY_SHA256:
                raise ValueError("FarmGame.swf does not match the supported v855097-855094 source; "
                                 "refusing to modify unknown game code.")
            if _digest(body[METHOD_CODE_OFFSET:METHOD_CODE_OFFSET + 1210]) != METHOD_SOURCE_SHA256:
                raise ValueError("The XML style parser no longer matches the reviewed bytecode.")
            styled = _apply_edits(body, EDITS)
        if (len(styled) != STYLE_BODY_BYTES or _digest(styled) != STYLE_BODY_SHA256
                or _digest(styled[METHOD_CODE_OFFSET:METHOD_CODE_OFFSET + 1211]) != METHOD_PATCHED_SHA256):
            raise ValueError("The style patch did not produce the verified output; nothing was written.")
        market = _apply_edits(styled, MARKET_EDITS)
    if len(market) != PRE_TURBO_BODY_BYTES or _digest(market) != MARKET_BODY_SHA256:
        raise ValueError("The Market patch did not produce the verified output; nothing was written.")
    tab_method = slice(TAB_METHOD_CODE_OFFSET, TAB_METHOD_CODE_OFFSET + TAB_METHOD_CODE_BYTES)
    if _digest(market[tab_method]) != TAB_METHOD_SOURCE_SHA256:
        raise ValueError("The tab callback no longer matches the reviewed bytecode.")
    patched = _apply_edits(market, TAB_EDITS)
    if len(patched) != PRE_TURBO_BODY_BYTES or _digest(patched) != TAB_BODY_SHA256:
        raise ValueError("The tab patch did not produce the verified output; nothing was written.")
    if _digest(patched[tab_method]) != TAB_METHOD_PATCHED_SHA256:
        raise ValueError("The tab callback did not produce the reviewed bytecode.")
    return _finish_scratch_patch(data, patched)


def _finish_scratch_patch(data: bytes, body: bytes) -> bytes:
    method = slice(SCRATCH_METHOD_CODE_OFFSET, SCRATCH_METHOD_CODE_OFFSET + SCRATCH_METHOD_CODE_BYTES)
    if _digest(body[method]) != SCRATCH_METHOD_SOURCE_SHA256:
        raise ValueError("The Scratch-Off icon callback no longer matches the reviewed bytecode.")
    patched = _apply_edits(body, SCRATCH_EDITS)
    if (len(patched) != PRE_TURBO_BODY_BYTES or _digest(patched) != SCRATCH_BODY_SHA256
            or _digest(patched[method]) != SCRATCH_METHOD_PATCHED_SHA256):
        raise ValueError("The Scratch-Off icon patch did not produce the verified output; nothing was written.")
    return _finish_empty_world_patch(data, patched)


def _finish_empty_world_patch(data: bytes, body: bytes) -> bytes:
    method = slice(EMPTY_WORLD_METHOD_CODE_OFFSET,
                   EMPTY_WORLD_METHOD_CODE_OFFSET + EMPTY_WORLD_METHOD_CODE_BYTES)
    if _digest(body[method]) != EMPTY_WORLD_METHOD_SOURCE_SHA256:
        raise ValueError("The initial world loader no longer matches the reviewed bytecode.")
    patched = _apply_edits(body, EMPTY_WORLD_EDITS)
    if (len(patched) != PRE_TURBO_BODY_BYTES or _digest(patched) != EMPTY_WORLD_BODY_SHA256
            or _digest(patched[method]) != EMPTY_WORLD_METHOD_PATCHED_SHA256):
        raise ValueError("The empty-world patch did not produce the verified output; nothing was written.")
    return _finish_cottage_graphics_patch(data, patched)


def _finish_cottage_graphics_patch(data: bytes, body: bytes) -> bytes:
    method = slice(COTTAGE_METHOD_CODE_OFFSET,
                   COTTAGE_METHOD_CODE_OFFSET + COTTAGE_METHOD_CODE_BYTES)
    if _digest(body[method]) != COTTAGE_METHOD_SOURCE_SHA256:
        raise ValueError("The cottage image selector no longer matches the reviewed bytecode.")
    patched = _apply_edits(body, COTTAGE_EDITS)
    if (len(patched) != PRE_TURBO_BODY_BYTES or _digest(patched) != COTTAGE_GRAPHICS_BODY_SHA256
            or _digest(patched[method]) != COTTAGE_METHOD_PATCHED_SHA256):
        raise ValueError("The cottage graphics patch did not produce the verified output; nothing was written.")
    return _finish_cottage_upgrade_patch(data, patched)


def _finish_cottage_upgrade_patch(data: bytes, body: bytes) -> bytes:
    method = slice(COTTAGE_UPGRADE_METHOD_CODE_OFFSET,
                   COTTAGE_UPGRADE_METHOD_CODE_OFFSET + COTTAGE_UPGRADE_METHOD_CODE_BYTES)
    if _digest(body[method]) != COTTAGE_UPGRADE_METHOD_SOURCE_SHA256:
        raise ValueError("The cottage upgrade controls no longer match the reviewed bytecode.")
    patched = _apply_edits(body, COTTAGE_UPGRADE_EDITS)
    if (len(patched) != PRE_TURBO_BODY_BYTES or _digest(patched) != COTTAGE_UPGRADE_BODY_SHA256
            or _digest(patched[method]) != COTTAGE_UPGRADE_METHOD_PATCHED_SHA256):
        raise ValueError("The cottage upgrade gate did not produce the verified output; nothing was written.")
    return _finish_turbo_patch(data, patched)


def _finish_turbo_patch(data: bytes, body: bytes) -> bytes:
    method = slice(TURBO_METHOD_CODE_OFFSET,
                   TURBO_METHOD_CODE_OFFSET + TURBO_METHOD_CODE_BYTES)
    if _digest(body[method]) != TURBO_METHOD_SOURCE_SHA256:
        raise ValueError("The Turbo purchase callback no longer matches the reviewed bytecode.")
    patched = _apply_edits(body, TURBO_EDITS)
    shifted = slice(method.start + TURBO_STRING_BYTES, method.stop + TURBO_STRING_BYTES)
    if (len(patched) != TURBO_BODY_BYTES or _digest(patched) != TURBO_BODY_SHA256
            or _digest(patched[shifted]) != TURBO_METHOD_PATCHED_SHA256):
        raise ValueError("The Turbo purchase refusal did not produce the verified output; nothing was written.")
    return _finish_storage_patch(data, patched)


def _finish_storage_patch(data: bytes, body: bytes) -> bytes:
    for _, offset, length, source_sha, _ in STORAGE_METHODS:
        if _digest(body[offset:offset + length]) != source_sha:
            raise ValueError("An Inventory storage upgrade entry point no longer matches the reviewed bytecode.")
    patched = _apply_edits(body, STORAGE_EDITS)
    if len(patched) != WIDGET_STORAGE_BODY_BYTES or _digest(patched) != STORAGE_BODY_SHA256:
        raise ValueError("The storage upgrade refusal did not produce the verified output; nothing was written.")
    for _, offset, length, _, patched_sha in STORAGE_METHODS:
        shifted = offset + STORAGE_STRING_BYTES
        if _digest(patched[shifted:shifted + length]) != patched_sha:
            raise ValueError("An Inventory storage upgrade refusal did not produce the reviewed bytecode.")
    return _finish_invitation_patch(data, patched)


def _finish_invitation_patch(data: bytes, body: bytes) -> bytes:
    for _, offset, length, source_sha, _ in INVITATION_METHODS:
        if _digest(body[offset:offset + length]) != source_sha:
            raise ValueError("An invitation entry point no longer matches the reviewed bytecode.")
    patched = _apply_edits(body, INVITATION_EDITS)
    if len(patched) != WIDGET_STORAGE_BODY_BYTES or _digest(patched) != INVITATION_BODY_SHA256:
        raise ValueError("The invitation patch did not produce the verified output; nothing was written.")
    for _, offset, length, _, patched_sha in INVITATION_METHODS:
        if _digest(patched[offset:offset + length]) != patched_sha:
            raise ValueError("An invitation entry point did not produce the reviewed bytecode.")
    return _finish_vip_patch(data, patched)


def _finish_vip_patch(data: bytes, body: bytes) -> bytes:
    method = slice(VIP_METHOD_CODE_OFFSET, VIP_METHOD_CODE_OFFSET + VIP_METHOD_CODE_BYTES)
    if _digest(body[method]) != VIP_METHOD_SOURCE_SHA256:
        raise ValueError("The VIP invitation gate no longer matches the reviewed bytecode.")
    patched = _apply_edits(body, VIP_EDITS)
    if (len(patched) != WIDGET_STORAGE_BODY_BYTES or _digest(patched) != VIP_BODY_SHA256
            or _digest(patched[method]) != VIP_METHOD_PATCHED_SHA256):
        raise ValueError("The VIP invitation gate did not produce the verified output; nothing was written.")
    return _finish_market_walkthrough_patch(data, patched)


def _finish_market_walkthrough_patch(data: bytes, body: bytes) -> bytes:
    for _, offset, length, source_sha, _ in MARKET_WALKTHROUGH_METHODS:
        if _digest(body[offset:offset + length]) != source_sha:
            raise ValueError("The full Market walkthrough no longer matches the reviewed bytecode.")
    patched = _apply_edits(body, MARKET_WALKTHROUGH_EDITS)
    if len(patched) != WIDGET_STORAGE_BODY_BYTES or _digest(patched) != MARKET_WALKTHROUGH_BODY_SHA256:
        raise ValueError("The Market walkthrough gate did not produce the verified output; nothing was written.")
    for _, offset, length, _, patched_sha in MARKET_WALKTHROUGH_METHODS:
        if _digest(patched[offset:offset + length]) != patched_sha:
            raise ValueError("The Market walkthrough gate did not produce the reviewed bytecode.")
    return _finish_quest_close_patch(data, patched)


def _finish_quest_close_patch(data: bytes, body: bytes) -> bytes:
    for _, offset, length, source_sha, _ in QUEST_CLOSE_METHODS:
        if _digest(body[offset:offset + length]) != source_sha:
            raise ValueError("The quest reward close binding no longer matches the reviewed bytecode.")
    patched = _apply_edits(body, QUEST_CLOSE_EDITS)
    if len(patched) != WIDGET_STORAGE_BODY_BYTES or _digest(patched) != QUEST_CLOSE_BODY_SHA256:
        raise ValueError("The quest close binding did not produce the verified output; nothing was written.")
    for _, offset, length, _, patched_sha in QUEST_CLOSE_METHODS:
        if _digest(patched[offset:offset + length]) != patched_sha:
            raise ValueError("The quest close binding did not produce the reviewed bytecode.")
    return _finish_image_row_patch(data, patched)


def _finish_image_row_patch(data: bytes, body: bytes) -> bytes:
    for _, offset, length, source_sha, _ in IMAGE_ROW_METHODS:
        if _digest(body[offset:offset + length]) != source_sha:
            raise ValueError("The image-row selector no longer matches the reviewed bytecode.")
    patched = _apply_edits(body, IMAGE_ROW_EDITS)
    if len(patched) != WIDGET_STORAGE_BODY_BYTES or _digest(patched) != IMAGE_ROW_BODY_SHA256:
        raise ValueError("The image-row selector did not produce the verified output; nothing was written.")
    for _, offset, length, _, patched_sha in IMAGE_ROW_METHODS:
        if _digest(patched[offset:offset + length]) != patched_sha:
            raise ValueError("The image-row selector did not produce the reviewed bytecode.")
    return _finish_inventory_art_patch(data, patched)


def _finish_image_labels_patch(data: bytes, body: bytes) -> bytes:
    _, offset, length, _, expected_sha = IMAGE_ROW_METHODS[0]
    if _digest(body[offset:offset + length]) != UNLABELED_IMAGE_ROW_METHOD_SHA256:
        raise ValueError("The staged image draft no longer matches the reviewed bytecode.")
    patched = _apply_edits(body, IMAGE_LABEL_EDITS)
    if (len(patched) != WIDGET_STORAGE_BODY_BYTES or _digest(patched) != IMAGE_ROW_BODY_SHA256
            or _digest(patched[offset:offset + length]) != expected_sha):
        raise ValueError("The image labels did not produce the verified output; nothing was written.")
    return _finish_inventory_art_patch(data, patched)


def _finish_inventory_art_patch(data: bytes, body: bytes) -> bytes:
    for _, offset, length, source_sha, _ in INVENTORY_ART_METHODS:
        if _digest(body[offset:offset + length]) != source_sha:
            raise ValueError("The Inventory tab artwork no longer matches the reviewed bytecode.")
    patched = _apply_edits(body, INVENTORY_ART_EDITS)
    if len(patched) != WIDGET_STORAGE_BODY_BYTES or _digest(patched) != INVENTORY_ART_BODY_SHA256:
        raise ValueError("The Inventory tab artwork did not produce the verified output; nothing was written.")
    for _, offset, length, _, patched_sha in INVENTORY_ART_METHODS:
        if _digest(patched[offset:offset + length]) != patched_sha:
            raise ValueError("The Inventory tab artwork did not produce the reviewed bytecode.")
    return _finish_marketstall_expansion_patch(data, patched)


def _finish_marketstall_expansion_patch(data: bytes, body: bytes) -> bytes:
    for _, offset, length, source_sha, _ in MARKETSTALL_EXPANSION_METHODS:
        if _digest(body[offset:offset + length]) != source_sha:
            raise ValueError("The MarketStall expansion no longer matches the reviewed bytecode.")
    patched = _apply_edits(body, MARKETSTALL_EXPANSION_EDITS)
    if len(patched) != WIDGET_STORAGE_BODY_BYTES or _digest(patched) != MARKETSTALL_EXPANSION_BODY_SHA256:
        raise ValueError("The MarketStall expansion fence did not produce the verified output; nothing was written.")
    for _, offset, length, _, patched_sha in MARKETSTALL_EXPANSION_METHODS:
        if _digest(patched[offset:offset + length]) != patched_sha:
            raise ValueError("The MarketStall expansion fence did not produce the reviewed bytecode.")
    return _finish_widget_storage_patch(data, patched)


def _finish_widget_storage_patch(data: bytes, body: bytes) -> bytes:
    for _, offset, length, source_sha, _ in WIDGET_STORAGE_METHODS:
        if _digest(body[offset:offset + length]) != source_sha:
            raise ValueError("The widget Storage window no longer matches the reviewed bytecode.")
    patched = _apply_edits(body, WIDGET_STORAGE_EDITS)
    if len(patched) != WIDGET_STORAGE_BODY_BYTES or _digest(patched) != WIDGET_STORAGE_BODY_SHA256:
        raise ValueError("The widget Storage visibility gate did not produce the verified output; nothing was written.")
    for _, offset, length, _, patched_sha in WIDGET_STORAGE_METHODS:
        if _digest(patched[offset:offset + length]) != patched_sha:
            raise ValueError("The widget Storage visibility gate did not produce the reviewed bytecode.")
    return _finish_regional_upgrade_patch(data, patched)


def _finish_regional_upgrade_patch(data: bytes, body: bytes) -> bytes:
    method = slice(REGIONAL_UPGRADE_METHOD_CODE_OFFSET,
                   REGIONAL_UPGRADE_METHOD_CODE_OFFSET + REGIONAL_UPGRADE_METHOD_CODE_BYTES)
    if (len(body) != WIDGET_STORAGE_BODY_BYTES or _digest(body) != WIDGET_STORAGE_BODY_SHA256
            or _digest(body[method]) != REGIONAL_UPGRADE_METHOD_SOURCE_SHA256):
        raise ValueError("The regional upgrade gate no longer matches the reviewed bytecode.")
    patched = _apply_edits(body, REGIONAL_UPGRADE_EDITS)
    shifted = slice(method.start + REGIONAL_UPGRADE_STRING_BYTES,
                    method.stop + REGIONAL_UPGRADE_STRING_BYTES)
    if (len(patched) != PATCHED_BODY_BYTES or _digest(patched) != REGIONAL_UPGRADE_BODY_SHA256
            or _digest(patched[shifted]) != REGIONAL_UPGRADE_METHOD_PATCHED_SHA256):
        raise ValueError("The regional upgrade gate did not produce the verified output; nothing was written.")
    return _finish_optional_background_patch(data, patched)


def _finish_optional_background_patch(data: bytes, body: bytes) -> bytes:
    method = slice(OPTIONAL_BACKGROUND_METHOD_CODE_OFFSET,
                   OPTIONAL_BACKGROUND_METHOD_CODE_OFFSET + OPTIONAL_BACKGROUND_METHOD_CODE_BYTES)
    if (len(body) != PATCHED_BODY_BYTES or _digest(body) != REGIONAL_UPGRADE_BODY_SHA256
            or _digest(body[method]) != OPTIONAL_BACKGROUND_METHOD_SOURCE_SHA256):
        raise ValueError("The optional prize background guard no longer matches the reviewed bytecode.")
    patched = _apply_edits(body, OPTIONAL_BACKGROUND_EDITS)
    if (len(patched) != PATCHED_BODY_BYTES or _digest(patched) != PATCHED_BODY_SHA256
            or _digest(patched[method]) != OPTIONAL_BACKGROUND_METHOD_PATCHED_SHA256):
        raise ValueError("The optional prize background guard did not produce the verified output; nothing was written.")
    cove_client = _cove_patch()
    return cove_client.prepare(data[:4] + struct.pack("<I", len(patched) + 8) + zlib.compress(patched, 9))


def patch_client_file(source: Path, destination: Path) -> bool:
    """Atomically write a prepared copy, allowing an existing staging path."""
    original = source.read_bytes()
    patched = patch_client_bytes(original)
    if source == destination and patched == original:
        return False
    mode = stat.S_IMODE(source.stat().st_mode)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".farmvillage-client-", suffix=".swf",
                                         dir=destination.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(patched)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return patched != original


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Original or already patched staged client")
    parser.add_argument("output", type=Path, help="Prepared client path; may match input")
    arguments = parser.parse_args()
    try:
        changed = patch_client_file(arguments.input, arguments.output)
    except (OSError, ValueError) as error:
        parser.exit(1, f"FarmVillage client patch failed: {error}\n")
    print(f"{'Patched' if changed else 'Verified'} FarmGame.swf style, Market, tab, Scratch-Off, empty-world, cottage graphics, craft upgrades, Turbo/storage refusals and invitation compatibility: {arguments.output}")
    return 0


@lru_cache(maxsize=2)
def _prepared_bytes(data: bytes) -> bytes:
    return patch_client_bytes(data)


def prepared_client(source: Path) -> bytes:
    """Serve matching reviewed code without modifying archived source assets.

    Cache by complete content, so replacing a client cannot return stale code.
    The bundled source is already prepared; the source checkout is prepared in
    memory using exactly the same verified recipe as resource staging.
    """
    return _prepared_bytes(source.read_bytes())


if __name__ == "__main__":
    raise SystemExit(main())
