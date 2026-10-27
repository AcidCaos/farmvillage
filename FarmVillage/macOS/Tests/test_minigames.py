"""Original prize-game wire contracts; disposable saves and archived catalogs."""
from contextlib import redirect_stdout
import copy
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures  # Establish isolated paths before product imports.
import minigames
import storage
from game_settings import level_to_xp
from items import get_item_by_name


class MinigameTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway = fixtures.RuntimeFixtureTests.gateway
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload

    def prepare(self, cash=100):
        self.path = self.write_fixture()
        self.save = self.player.session("fixture-farmer")
        self.save["userInfo"]["player"].update(cash=cash, storageData={})
        self.save["userInfo"].setdefault("featureOptions", {}).pop(minigames.SLOT_FEATURE, None)
        self.save["userInfo"]["player"].setdefault("actionCounts", {})[minigames.PIGO_FREE_COUNTER] = 0
        self.save.pop("_localMinigames", None)
        self.save.pop("pigoState", None)
        self.save["preservedImportedState"] = {"unknown": [1, 2, {"keep": True}]}
        minigames.start_session(self.save)
        self.sequence = 0
        self.persist()

    def persist(self):
        with redirect_stdout(io.StringIO()):
            self.player.save_session("fixture-farmer")

    def reload(self):
        self.persist()
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.save = self.player.session("fixture-farmer")

    def call(self, method, params=(), sequence=None):
        if sequence is None:
            self.sequence += 1
            sequence = self.sequence
        with redirect_stdout(io.StringIO()):
            return minigames.dispatch(self.save, method, list(params), request_id=sequence)

    def count(self, name):
        return self.save["userInfo"]["player"]["storageData"].get("-1", {}).get(
            get_item_by_name(name)["code"], [0])[0]

    def cash(self):
        return self.save["userInfo"]["player"]["cash"]

    def reject(self, method, params=(), sequence=None):
        before = copy.deepcopy(self.save)
        with self.assertRaises(ValueError):
            self.call(method, params, sequence)
        self.assertEqual(self.save, before)

    def spin_losing(self, sequence=None):
        with mock.patch.object(minigames.random, "random", return_value=1):
            return self.call("SlotService.spin", sequence=sequence)

    def scratch(self, reward_index=0, won=True, unlock=True):
        chosen = minigames.SCRATCH_REWARDS[reward_index]
        first = True
        def pick(pool):
            nonlocal first
            if first:
                first = False
                return chosen
            return pool[0]
        with mock.patch.object(minigames, "_weighted", side_effect=pick), \
                mock.patch.object(minigames.random, "random", return_value=0 if won else 1):
            return self.call("ScratchCardService.getScratchCardData", [unlock])

    def test_slot_one_initial_free_spin_persists_and_then_exact_paid_cost(self):
        self.prepare()
        self.spin_losing()
        self.assertEqual(self.cash(), 100)
        self.reload()
        minigames.start_session(self.save)
        self.spin_losing()
        self.assertEqual(self.cash(), 97)
        self.assertEqual(self.save["userInfo"]["featureOptions"][minigames.SLOT_FEATURE][minigames.SLOT_FREE_OPTION], 0)
        self.assertEqual(self.save["preservedImportedState"], {"unknown": [1, 2, {"keep": True}]})

    def test_slot_free_spin_reward_and_receipt_survive_server_reload(self):
        self.prepare()
        with mock.patch.object(minigames.random, "random", return_value=0), \
                mock.patch.object(minigames, "_weighted", return_value=minigames.SLOT_REWARDS[2]):
            first = self.call("SlotService.spin", sequence=5)
        self.reload()
        snapshot = copy.deepcopy(self.save)
        self.assertEqual(self.call("SlotService.spin", sequence=5), first)
        self.assertEqual(self.save, snapshot)
        self.spin_losing(sequence=6)
        self.assertEqual(self.cash(), 100)

    def test_slots_refuse_unfunded_paid_spin_and_keep_full_state(self):
        self.prepare(cash=2)
        self.spin_losing()
        self.reject("SlotService.spin")

    def test_slot_losing_display_cannot_accidentally_match(self):
        self.prepare()
        with mock.patch.object(minigames.random, "random", return_value=1), \
                mock.patch.object(minigames.random, "choices", return_value=[minigames.SLOT_REWARDS[0]] * 3):
            result = self.call("SlotService.spin")
        self.assertIsNone(result["payOut"])
        self.assertNotEqual(result["slots"][0], result["slots"][2])

    def test_slot_gift_reward_is_server_owned_and_detached(self):
        self.prepare()
        with mock.patch.object(minigames.random, "random", return_value=0), \
                mock.patch.object(minigames, "_weighted", return_value=minigames.SLOT_REWARDS[5]):
            result = self.call("SlotService.spin", sequence=1)
        self.assertEqual(self.count("cow"), 1)
        result["payOut"]["quantity"] = 900
        replay = self.call("SlotService.spin", sequence=1)
        self.assertEqual(replay["payOut"]["quantity"], 1)
        self.assertEqual(minigames.SLOT_REWARDS[5]["quantity"], 1)

    def test_scratch_open_is_locked_without_payment_or_free_card(self):
        self.prepare(cash=0)
        result = self.call("ScratchCardService.getScratchCardData", [False])
        self.assertIsNone(result["card"])
        self.reject("ScratchCardService.getScratchCardData", [True])
        self.reject("ScratchCardService.getScratchCardData", [1])
        self.reject("ScratchCardService.getScratchCardData", ["false"])

    def test_scratch_paid_card_resumes_exact_tiles_and_claims_once(self):
        self.prepare()
        gold = self.save["userInfo"]["player"]["gold"]
        result = self.scratch()
        self.assertEqual(self.cash(), 96)
        self.assertEqual(self.save["userInfo"]["player"]["gold"], gold)
        self.reject("ScratchCardService.getScratchCardData", [True])
        self.reload()
        self.assertEqual(self.call("ScratchCardService.getScratchCardData", [False]), result)
        self.reject("ScratchCardService.clearCard")
        self.call("ScratchCardService.grantReward")
        self.call("ScratchCardService.grantReward")
        self.assertEqual(self.save["userInfo"]["player"]["gold"], gold + 500)
        self.assertIsNone(self.call("ScratchCardService.getScratchCardData", [False])["card"])

    def test_scratch_free_card_is_durable_and_not_repeated(self):
        self.prepare()
        self.scratch(reward_index=2)
        self.call("ScratchCardService.grantReward")
        self.reload()
        minigames.start_session(self.save)
        next_card = self.scratch(unlock=False, won=False)
        self.assertEqual(len(next_card["card"]), 9)
        self.assertEqual(self.cash(), 96)
        self.assertEqual(self.save["_localMinigames"]["scratchFreeCards"], 0)
        self.call("ScratchCardService.clearCard")
        self.assertIsNone(self.call("ScratchCardService.getScratchCardData", [False])["card"])

    def test_scratch_loss_always_has_completion_branch_and_no_triplet(self):
        self.prepare()
        result = self.scratch(won=False)
        self.assertIsNotNone(result["almostWon"])
        self.assertIsNone(result["winEntry"])
        self.assertTrue(all(result["card"].count(tile) <= 2 for tile in result["card"]))
        self.reject("ScratchCardService.grantReward")
        self.call("ScratchCardService.clearCard")
        self.call("ScratchCardService.clearCard")
        self.scratch(won=False)
        self.assertEqual(self.cash(), 92)

    def test_scratch_win_has_only_one_winning_triplet_and_real_gift_identity(self):
        self.prepare()
        result = self.scratch(reward_index=4)
        self.assertEqual(result["winEntry"]["value"], get_item_by_name("cow")["code"])
        self.assertEqual(result["card"].count(result["winEntry"]), 3)
        self.assertTrue(all(result["card"].count(tile) <= 2 for tile in result["card"] if tile != result["winEntry"]))
        self.call("ScratchCardService.grantReward")
        self.assertEqual(self.count("cow"), 1)

    def test_pigo_catalog_purchase_single_package_and_retry(self):
        self.prepare()
        self.call("PigoService.buyToken", [minigames.PIGO_GAME], sequence=1)
        self.call("PigoService.buyToken", [minigames.PIGO_GAME], sequence=1)
        self.call("PigoService.buyTokenPackage", [minigames.PIGO_GAME], sequence=2)
        self.assertEqual((self.cash(), self.count(minigames.PIGO_TOKEN)), (63, 4))
        self.reload()
        self.call("PigoService.buyTokenPackage", [minigames.PIGO_GAME], sequence=2)
        self.assertEqual((self.cash(), self.count(minigames.PIGO_TOKEN)), (63, 4))

    def test_pigo_unknown_game_missing_cash_token_and_forged_reward_rejected(self):
        self.prepare(cash=0)
        for method in ("PigoService.getGameSettings", "PigoService.buyToken", "PigoService.buyTokenPackage"):
            self.reject(method, ["not-a-game"])
        for method in ("PigoService.buyToken", "PigoService.buyTokenPackage"):
            self.reject(method, [minigames.PIGO_GAME])
        self.reject("PigoService.grantReward", [minigames.PIGO_GAME, "chicken"])
        self.reject("PigoService.grantReward", [minigames.PIGO_GAME, "cow"])
        self.reject("PigoService.grantReward", [minigames.PIGO_GAME, minigames.PIGO_SET_BONUS])

    def test_pigo_prize_consumes_one_token_and_retries_do_not_duplicate(self):
        self.prepare()
        self.call("PigoService.buyToken", [minigames.PIGO_GAME], sequence=1)
        result = self.call("PigoService.grantReward", [minigames.PIGO_GAME, "chicken"], sequence=2)
        self.assertEqual(result, {"complete": True})
        self.reload()
        self.call("PigoService.grantReward", [minigames.PIGO_GAME, "chicken"], sequence=2)
        self.assertEqual((self.count(minigames.PIGO_TOKEN), self.count("chicken")), (0, 1))
        self.reject("PigoService.grantReward", [minigames.PIGO_GAME, "chicken"], sequence=3)

    def test_pigo_complete_set_grants_exactly_one_bonus_and_preserves_unknown_counts(self):
        self.prepare(cash=200)
        self.save["pigoState"] = {minigames.PIGO_GAME: {"importedUnknownPrize": 5}}
        for name in minigames.PIGO_PRIZES:
            self.call("PigoService.buyToken", [minigames.PIGO_GAME])
            self.call("PigoService.grantReward", [minigames.PIGO_GAME, name])
        self.call("PigoService.buyToken", [minigames.PIGO_GAME])
        self.call("PigoService.grantReward", [minigames.PIGO_GAME, "chicken"])
        self.assertEqual(self.count("sheep"), 1)
        self.assertEqual(self.save["pigoState"][minigames.PIGO_GAME]["importedUnknownPrize"], 5)
        self.assertEqual(self.call("PigoService.getGameSettings", [minigames.PIGO_GAME])[-1]["winCount"], 1)

    def test_pigo_original_positive_free_allowance_is_consumed_once(self):
        self.prepare(cash=0)
        self.save.pop("_localMinigames")
        self.save["userInfo"]["player"]["xp"] = level_to_xp(10)
        self.save["userInfo"]["player"]["actionCounts"][minigames.PIGO_FREE_COUNTER] = 2
        minigames.start_session(self.save)
        self.call("PigoService.grantReward", [minigames.PIGO_GAME, "chicken"])
        self.assertEqual(self.save["userInfo"]["player"]["actionCounts"][minigames.PIGO_FREE_COUNTER], 0)
        self.reject("PigoService.grantReward", [minigames.PIGO_GAME, "duck"])
        self.reload()
        minigames.start_session(self.save)
        self.reject("PigoService.grantReward", [minigames.PIGO_GAME, "duck"])

    def test_pigo_free_allowance_honors_original_level_gate(self):
        self.prepare(cash=0)
        self.save["userInfo"]["player"]["xp"] = 0
        self.save["_localMinigames"]["pigoFreePlays"] = 1
        self.reject("PigoService.grantReward", [minigames.PIGO_GAME, "chicken"])

    def test_conflicting_or_evicted_receipt_is_rejected_without_mutation(self):
        self.prepare(cash=10000)
        self.spin_losing(sequence=1)
        self.reject("PigoService.buyToken", [minigames.PIGO_GAME], sequence=1)
        for sequence in range(2, 259):
            self.call("PigoService.getGameSettings", [minigames.PIGO_GAME], sequence=sequence)
        self.assertEqual(len(self.save["_localMinigames"]["requests"]), 256)
        self.reject("SlotService.spin", sequence=1)
        for bad in (True, -1, 1.5, float("nan"), "1"):
            self.reject("SlotService.spin", sequence=bad)

    def test_receipt_retry_cannot_bypass_original_parameter_types(self):
        self.prepare()
        self.call("ScratchCardService.getScratchCardData", [False], sequence=1)
        self.reject("ScratchCardService.getScratchCardData", [0], sequence=1)
        self.sequence = 1
        self.scratch(won=False)
        self.reject("ScratchCardService.getScratchCardData", [1], sequence=2)
        for method, params in (("PigoService.getGameSettings", [None]),
                               ("PigoService.buyToken", [[]]),
                               ("PigoService.buyTokenPackage", [{}]),
                               ("PigoService.grantReward", [minigames.PIGO_GAME, True])):
            self.reject(method, params)
        self.reject(["SlotService.spin"])

    def test_reward_storage_failure_rolls_back_payment_token_and_counts(self):
        self.prepare()
        self.call("PigoService.buyToken", [minigames.PIGO_GAME])
        before = copy.deepcopy(self.save)
        with mock.patch.object(storage, "store_deposit_item_by_name", side_effect=ValueError("gift storage failed")):
            self.reject("PigoService.grantReward", [minigames.PIGO_GAME, "chicken"])
        self.assertEqual(self.save, before)

    def test_wire_batch_retry_and_invalid_followup_keep_paid_token(self):
        self.prepare()
        self.persist()
        before = self.path.read_bytes()
        response = self.gateway([
            self.command("PigoService.buyToken", [minigames.PIGO_GAME], sequence=1),
            self.command("PigoService.grantReward", [minigames.PIGO_GAME, "cow"], sequence=2),
        ])
        fixtures.gateway_results(self, response, [0, 29])
        self.save = self.player.session("fixture-farmer")
        self.assertEqual((self.cash(), self.count(minigames.PIGO_TOKEN)), (90, 1))
        purchase = self.command("PigoService.buyTokenPackage", [minigames.PIGO_GAME], sequence=3)
        self.assertEqual(self.gateway([purchase]).status_code, 200)
        self.assertEqual(self.gateway([purchase]).status_code, 200)
        self.save = self.player.session("fixture-farmer")
        self.assertEqual((self.cash(), self.count(minigames.PIGO_TOKEN)), (63, 4))

    def test_wire_disk_failure_restores_free_spin_and_cash(self):
        self.prepare()
        before = self.path.read_bytes()
        old = copy.deepcopy(self.save)
        with mock.patch.object(self.player, "commit_json_batch", side_effect=OSError("disk failed")):
            with self.assertRaises(OSError):
                self.gateway([self.command("SlotService.spin", sequence=1)])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.player.session("fixture-farmer"), old)

    def test_wire_client_counter_writes_cannot_mint_free_plays(self):
        self.prepare(cash=0)
        for method, params in (("UserService.setActionCount", [minigames.PIGO_FREE_COUNTER, 999]),
                               ("UserService.incrementActionCount", [minigames.PIGO_FREE_COUNTER]),
                               ("UserService.resetActionCount", [minigames.PIGO_FREE_COUNTER])):
            self.sequence += 1
            self.assertEqual(self.gateway([self.command(method, params, sequence=self.sequence)]).status_code, 200)
        self.save = self.player.session("fixture-farmer")
        self.assertEqual(self.save["userInfo"]["player"]["actionCounts"][minigames.PIGO_FREE_COUNTER], 0)
        self.reject("PigoService.grantReward", [minigames.PIGO_GAME, "chicken"])

    def test_wire_unknown_minigame_mutation_keeps_earlier_paid_token(self):
        self.prepare()
        before = self.path.read_bytes()
        response = self.gateway([
            self.command("PigoService.buyToken", [minigames.PIGO_GAME], sequence=1),
            self.command("PigoService.inventedReward", ["cow", 999], sequence=2),
        ])
        fixtures.gateway_results(self, response, [0, 29])
        self.save = self.player.session("fixture-farmer")
        self.assertEqual((self.cash(), self.count(minigames.PIGO_TOKEN)), (90, 1))

    def test_wire_free_play_acknowledgment_does_not_consume_allowance_before_reward(self):
        self.prepare(cash=0)
        self.save["_localMinigames"]["pigoFreePlays"] = 1
        self.save["userInfo"]["player"]["actionCounts"][minigames.PIGO_FREE_COUNTER] = 1
        self.save["userInfo"]["player"]["xp"] = level_to_xp(10)
        response = self.gateway([
            self.command("UserService.setActionCount", [minigames.PIGO_FREE_COUNTER, 0], sequence=1),
            self.command("PigoService.grantReward", [minigames.PIGO_GAME, "chicken"], sequence=2),
        ])
        self.assertEqual(response.status_code, 200)
        self.save = self.player.session("fixture-farmer")
        self.assertEqual(self.count("chicken"), 1)
        self.assertEqual(self.save["_localMinigames"]["pigoFreePlays"], 0)

    def test_init_returns_persisted_free_spins_and_hides_request_receipts(self):
        self.prepare()
        self.spin_losing()
        with redirect_stdout(io.StringIO()):
            result = self.server.commands.init_user("fixture-farmer")
        self.assertEqual(result["userInfo"]["featureOptions"][minigames.SLOT_FEATURE][minigames.SLOT_FREE_OPTION], 0)
        self.assertNotIn("_localMinigames", result)
        self.assertEqual(self.save["_localMinigames"]["requests"], {})

    def test_original_game_tent_entry_is_surfaced_in_both_served_clients(self):
        self.prepare()
        with self.client.session_transaction() as browser:
            browser["UID"] = "fixture-farmer"
        # TPostInit calls CarnivalBoothQueuedIcon.showHUDIcon at variant >=2.
        # Exercise the actual rendered bootstraps, including the legacy route.
        with mock.patch.object(self.server, "NATIVE_WRAPPER", False), redirect_stdout(io.StringIO()):
            for route in ("/play.html", "/ruffle.html"):
                page = self.client.get(route)
                self.assertEqual(page.status_code, 200)
                self.assertRegex(page.get_data(as_text=True), r'"fv_carnival_booth_hud"\s*:\s*2\b')
                self.assertRegex(page.get_data(as_text=True), r'"fv_pigo"\s*:\s*2\b')
            post_init = self.server.commands.post_init_user("fixture-farmer")
        self.assertIn("carnivalBooth", post_init["hudIcons"])
        game = get_item_by_name(minigames.PIGO_GAME)
        self.assertEqual((game["isGameToken"], game["promoMode"], game["experiment"]),
                         ("true", "pigo", "fv_pigo"))
        self.assertFalse(game.get("limitedStart") or game.get("limitedEnd"))
        self.assertEqual(len(self.call("PigoService.getGameSettings", [game["name"]])), 7)
        self.assertEqual(self.cash(), 100)

    def test_payment_rejects_malformed_saved_cash_before_reward(self):
        self.prepare()
        for invalid in (True, -1, "100", 1.5):
            self.save["userInfo"]["player"]["cash"] = invalid
            self.reject("PigoService.buyToken", [minigames.PIGO_GAME])


class CarnivalRoutingContractTests(unittest.TestCase):
    def test_original_carnival_slot_three_selects_pigo_without_fortune_wheel_collision(self):
        import re
        import xml.etree.ElementTree as ET
        import zlib
        root = Path(__file__).resolve().parents[2]
        catalog = ET.fromstring(zlib.decompress((root / "xml/gz/v855098/MarketData.xml.gz").read_bytes()))
        slot = [entry for entry in catalog.findall(".//carnivalPage/promoItem")
                if entry.find("timer") is not None and entry.find("timer").get("slot") == "3"]
        self.assertEqual({entry.get("name") for entry in slot}, {"Carnival_Pigo", "Carnival_SlotMachine"})
        for template in ("play.html", "ruffle.html"):
            with self.subTest(template=template):
                source = (root / "templates" / template).read_text()
                selected = []
                for entry in slot:
                    requirement, = entry.findall("prereqs/prereq")
                    self.assertEqual(requirement.get("type"), "experiment")
                    configured = int(re.search(r'"' + re.escape(requirement.get("value")) + r'"\s*:\s*(\d+)', source).group(1))
                    required = int(requirement.get("variant"))
                    operator = requirement.get("op", "eq")
                    self.assertIn(operator, ("eq", "gt"))
                    eligible = configured == required if operator == "eq" else configured > required
                    if eligible:
                        selected.append((entry.get("name"), entry.find("click").get("action")))
                self.assertEqual(selected, [("Carnival_Pigo", "openPigoGame")])


if __name__ == "__main__":
    unittest.main()
