"""The full Market walkthrough is hidden before obsolete tutorial activation."""
import hashlib
import struct
import unittest
import zlib

from test_turbo_client_refusal import PATCH, ROOT, ABC, read_abcs
import test_cottage_invitation_stage as invitation_tests


class MarketWalkthroughClientTests(unittest.TestCase):
    execute = invitation_tests.CottageInvitationStageTests.execute

    @classmethod
    def setUpClass(cls):
        cls.original = (ROOT / "embeds/Flash/v855097-855094/FarmGame.swf").read_bytes()
        cls.previous = zlib.decompress(cls.original[8:])
        for edits in (PATCH.EDITS, PATCH.MARKET_EDITS, PATCH.TAB_EDITS,
                      PATCH.SCRATCH_EDITS, PATCH.EMPTY_WORLD_EDITS, PATCH.COTTAGE_EDITS,
                      PATCH.COTTAGE_UPGRADE_EDITS, PATCH.TURBO_EDITS, PATCH.STORAGE_EDITS,
                      PATCH.INVITATION_EDITS, PATCH.VIP_EDITS):
            cls.previous = PATCH._apply_edits(cls.previous, edits)
        cls.prepared = PATCH.patch_client_bytes(cls.original)
        cls.body = PATCH._apply_edits(cls.previous, PATCH.MARKET_WALKTHROUGH_EDITS)
        cls.final_body = zlib.decompress(cls.prepared[8:])
        cls.before, cls.after = read_abcs(cls.previous), read_abcs(cls.body)
        cls.abc, cls.maxstack = cls.after[0], {}
        for ident, offset, length, _, _ in PATCH.MARKET_WALKTHROUGH_METHODS:
            found = []
            for start in range(offset - 16, offset):
                reader = ABC.R(cls.previous, start)
                method, maxstack, locals_, initial_scope, max_scope, size = [reader.u30() for _ in range(6)]
                if reader.p == offset and method == ident and size == length:
                    found.append(maxstack)
            assert len(found) == 1
            cls.maxstack[ident] = found[0]

    def test_exact_three_byte_stage_changes_only_full_market_walkthrough(self):
        self.assertEqual(hashlib.sha256(self.previous).hexdigest(), PATCH.VIP_BODY_SHA256)
        self.assertEqual(hashlib.sha256(self.body).hexdigest(), PATCH.MARKET_WALKTHROUGH_BODY_SHA256)
        self.assertEqual(self.body, PATCH._apply_edits(self.previous, PATCH.MARKET_WALKTHROUGH_EDITS))
        self.assertEqual(self.final_body, PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(self.body, PATCH.QUEST_CLOSE_EDITS), PATCH.IMAGE_ROW_EDITS), PATCH.INVENTORY_ART_EDITS), PATCH.MARKETSTALL_EXPANSION_EDITS), PATCH.WIDGET_STORAGE_EDITS), PATCH.REGIONAL_UPGRADE_EDITS), PATCH.OPTIONAL_BACKGROUND_EDITS), PATCH.COVE_UPGRADE_EDITS))
        offset = PATCH.MARKET_WALKTHROUGH_METHODS[0][1]
        self.assertEqual([i for i, (a, b) in enumerate(zip(self.previous, self.body)) if a != b],
                         [offset + 141, offset + 142, offset + 143])
        total, changed = 0, []
        for index, (before, after) in enumerate(zip(self.before, self.after)):
            for field in ("ints", "uints", "strings", "mn", "ns", "nssets", "methods", "instances", "classes"):
                self.assertEqual(getattr(before, field), getattr(after, field))
            self.assertEqual([struct.pack("<d", x) for x in before.doubles],
                             [struct.pack("<d", x) for x in after.doubles])
            self.assertEqual(list(before.bodies), list(after.bodies))
            for ident, code in before.bodies.items():
                total += 1
                if code != after.bodies[ident]:
                    changed.append((index, ident))
                    self.assertEqual(len(code), len(after.bodies[ident]))
        self.assertEqual((total, changed), (68492, [(0, 11246)]))
        for _, start, size, before_sha, after_sha in PATCH.MARKET_WALKTHROUGH_METHODS:
            self.assertEqual(hashlib.sha256(self.previous[start:start + size]).hexdigest(), before_sha)
            self.assertEqual(hashlib.sha256(self.body[start:start + size]).hexdigest(), after_sha)
        # Complete composition proves headers, pools, branch operands, assets and
        # ordinary setupMarket3/columns/tabs/search/purchase methods are untouched.
        self.assertEqual(self.abc.bodies[11241], self.before[0].bodies[11241])
        self.assertEqual((ROOT / "embeds/Flash/v855097-855094/FarmGame.swf").read_bytes(), self.original)

    def test_real_medium_small_and_missing_clip_paths_hide_without_seen_or_tutorial_access(self):
        for size, clip in ((4, "ftueMedium_mc"), (3, "ftueSmall_mc"), (4, None), (3, None), (5, None)):
            with self.subTest(size=size, clip=clip):
                artwork = {"visible": True, "currentFrame": 1, "okay_bt": object()}
                window = {clip: artwork} if clip else {}
                instance = {"marketSize": size, "m_ftue": None}
                globals_ = {"Widgets.Core.Windows:ZwAbstractWindow:m_window": window,
                            "NUM_MED_MARKET_COLS": 4, "NUM_SMALL_MARKET_COLS": 3,
                            "flash.display:MovieClip": object()}
                self.assertIsNone(self.execute(11246, 0, None, {0: instance}, globals_))
                if clip:
                    self.assertIs(instance["m_ftue"], artwork)
                    self.assertFalse(artwork["visible"])
                    self.assertEqual(artwork["currentFrame"], 1)
                else:
                    self.assertIsNone(instance["m_ftue"])
                # No Global/player, getSeenFlag, gotoAndStop or button builder is
                # provided. Any attempt to activate/acknowledge a walkthrough fails.

    def test_known_vip_stage_upgrades_and_unknown_code_rejects(self):
        previous = self.original[:4] + struct.pack("<I", len(self.previous) + 8) + zlib.compress(self.previous, 1)
        self.assertEqual(PATCH.patch_client_bytes(previous), self.prepared)
        self.assertEqual(PATCH.patch_client_bytes(self.prepared), self.prepared)
        alternative = self.prepared[:8] + zlib.compress(self.final_body, 1)
        self.assertEqual(PATCH.patch_client_bytes(alternative), alternative)
        offset = PATCH.MARKET_WALKTHROUGH_METHODS[0][1]
        changed = bytearray(self.previous); changed[offset + 141] ^= 1
        with self.assertRaisesRegex(ValueError, "refusing to modify unknown game code"):
            PATCH.patch_client_bytes(previous[:8] + zlib.compress(changed, 1))


if __name__ == "__main__":
    unittest.main()
