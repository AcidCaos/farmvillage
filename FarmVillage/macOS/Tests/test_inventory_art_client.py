"""Inventory hides both transparent click overlays and their separate tab artwork."""
import hashlib
import struct
import unittest
import zlib

from test_turbo_client_refusal import PATCH, ROOT, ABC, read_abcs
import test_cottage_invitation_stage as invitation_tests
import test_image_row_client as image_tests


class InventoryArtworkClientTests(unittest.TestCase):
    execute = invitation_tests.CottageInvitationStageTests.execute
    branch_errors = image_tests.ImageRowClientTests.branch_errors

    @classmethod
    def setUpClass(cls):
        cls.original = (ROOT / "embeds/Flash/v855097-855094/FarmGame.swf").read_bytes()
        cls.previous = zlib.decompress(cls.original[8:])
        for edits in (PATCH.EDITS, PATCH.MARKET_EDITS, PATCH.TAB_EDITS, PATCH.SCRATCH_EDITS,
                      PATCH.EMPTY_WORLD_EDITS, PATCH.COTTAGE_EDITS, PATCH.COTTAGE_UPGRADE_EDITS,
                      PATCH.TURBO_EDITS, PATCH.STORAGE_EDITS, PATCH.INVITATION_EDITS,
                      PATCH.VIP_EDITS, PATCH.MARKET_WALKTHROUGH_EDITS, PATCH.QUEST_CLOSE_EDITS,
                      PATCH.IMAGE_ROW_EDITS):
            cls.previous = PATCH._apply_edits(cls.previous, edits)
        cls.prepared = PATCH.patch_client_bytes(cls.original)
        cls.body = PATCH._apply_edits(cls.previous, PATCH.INVENTORY_ART_EDITS)
        cls.final_body = zlib.decompress(cls.prepared[8:])
        cls.before, cls.after = read_abcs(cls.previous), read_abcs(cls.body)
        cls.abc, cls.maxstack = cls.after[0], {12403: 7}

    def test_original_generic_button_builds_overlay_sibling_not_the_visible_art(self):
        lines = ABC.disasm(self.abc, self.abc.bodies[4311])
        create = next(i for i, line in enumerate(lines) if "constructprop flash.display:MovieClip 0" in line)
        overlay = next(i for i, line in enumerate(lines) if "initproperty m_overlay" in line)
        self.assertLess(create, overlay)
        # Constructor269..286 adds m_overlay to m_target.parent; the original
        # target stays a separate artwork object, rather than a child of overlay.
        excerpt = "\n".join(line for line in lines if 269 <= int(line.split()[0]) < 286)
        self.assertIn("m_target", excerpt)
        self.assertIn("getproperty parent", excerpt)
        self.assertIn("getproperty m_overlay", excerpt)
        self.assertIn("callpropvoid addChild 1", excerpt)

    def test_actual_spans_hide_both_layers_and_retain_inventory_and_panels(self):
        for start, stop, name in ((401, 432, "expandStorage_bt"), (491, 522, "shippingLicenses_bt")):
            with self.subTest(tab=name):
                art = {"visible": True, "sentinel": "art"}
                overlay = {"visible": True, "sentinel": "hit"}
                inventory = {"visible": True, "sentinel": "inventory"}
                panel = {"visible": True, "contents": ["retain"]}
                wrapper = {"m_overlay": overlay, "m_target": art}
                globals_ = {"Display:Dialog:m_window": {"storage_mc": {name: art,
                            "inventory_bt": inventory, "storagePanel1": panel}}}
                # Historical code hid only the new transparent rectangle.
                old_abc = self.abc
                self.abc = self.before[0]
                self.execute(12403, start, start + 9, {2: wrapper}, globals_)
                self.assertFalse(overlay["visible"])
                self.assertTrue(art["visible"])
                self.abc = old_abc
                overlay["visible"] = True
                self.execute(12403, start, stop, {2: wrapper}, globals_)
                self.assertEqual(overlay, {"visible": False, "sentinel": "hit"})
                self.assertEqual(art, {"visible": False, "sentinel": "art"})
                self.assertEqual(inventory, {"visible": True, "sentinel": "inventory"})
                self.assertEqual(panel, {"visible": True, "contents": ["retain"]})

    def test_complete_delta_only_changes_two_label_spans_and_preserves_all_branches(self):
        self.assertEqual(hashlib.sha256(self.previous).hexdigest(), PATCH.IMAGE_ROW_BODY_SHA256)
        self.assertEqual(hashlib.sha256(self.body).hexdigest(), PATCH.INVENTORY_ART_BODY_SHA256)
        self.assertEqual(self.body, PATCH._apply_edits(self.previous, PATCH.INVENTORY_ART_EDITS))
        self.assertEqual(self.final_body, PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(PATCH._apply_edits(self.body, PATCH.MARKETSTALL_EXPANSION_EDITS), PATCH.WIDGET_STORAGE_EDITS), PATCH.REGIONAL_UPGRADE_EDITS), PATCH.OPTIONAL_BACKGROUND_EDITS), PATCH.COVE_UPGRADE_EDITS))
        total, changes = 0, []
        for index, (before, after) in enumerate(zip(self.before, self.after)):
            for field in ("ints", "uints", "strings", "mn", "ns", "nssets", "methods", "instances", "classes"):
                self.assertEqual(getattr(before, field), getattr(after, field))
            self.assertEqual([struct.pack("<d", x) for x in before.doubles],
                             [struct.pack("<d", x) for x in after.doubles])
            for ident, code in before.bodies.items():
                total += 1
                if code != after.bodies[ident]:
                    changes.append((index, ident)); self.assertEqual(len(code), len(after.bodies[ident]))
        self.assertEqual((total, changes), (68492, [(0, 12403)]))
        for _, start, size, old_sha, new_sha in PATCH.INVENTORY_ART_METHODS:
            self.assertEqual(hashlib.sha256(self.previous[start:start + size]).hexdigest(), old_sha)
            self.assertEqual(hashlib.sha256(self.body[start:start + size]).hexdigest(), new_sha)
            self.assertEqual(self.body[start - 8:start].hex(), "f36007060c0dae07")
            starts, invalid, missing_labels = self.branch_errors(self.abc.bodies[12403])
            self.assertEqual((invalid, missing_labels), ([], []))
            reader = ABC.R(self.body, start + size)
            for _ in range(reader.u30()):
                first, end, target, _, _ = [reader.u30() for _ in range(5)]
                self.assertIn(first, starts); self.assertIn(end, starts | {size}); self.assertIn(target, starts)
        before, after = self.before[0].bodies[12403], self.abc.bodies[12403]
        self.assertEqual(before[:401], after[:401])
        self.assertEqual(before[432:491], after[432:491])
        self.assertEqual(before[522:], after[522:])
        self.assertEqual(self.abc.bodies[12402], self.before[0].bodies[12402])  # Forced Inventory selection.
        self.assertEqual((ROOT / "embeds/Flash/v855097-855094/FarmGame.swf").read_bytes(), self.original)

    def test_known_image_stage_upgrades_and_unknown_art_code_rejects(self):
        previous = self.original[:4] + struct.pack("<I", len(self.previous) + 8) + zlib.compress(self.previous, 1)
        self.assertEqual(PATCH.patch_client_bytes(previous), self.prepared)
        self.assertEqual(PATCH.patch_client_bytes(self.prepared), self.prepared)
        alternative = self.prepared[:8] + zlib.compress(self.final_body, 1)
        self.assertEqual(PATCH.patch_client_bytes(alternative), alternative)
        changed = bytearray(self.previous); changed[PATCH.INVENTORY_ART_METHODS[0][1] + 401] ^= 1
        with self.assertRaisesRegex(ValueError, "refusing to modify unknown game code"):
            PATCH.patch_client_bytes(previous[:8] + zlib.compress(changed, 1))


if __name__ == "__main__":
    unittest.main()
