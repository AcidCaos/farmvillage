"""Bounded feature preference merges; every persisted farm is temporary."""
import copy
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest
from unittest import mock

from pyamf import remoting

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures  # Set temporary runtime paths before product imports.
import feature_options


class FeatureOptionTests(unittest.TestCase):
    @staticmethod
    def farm():
        return {"userInfo": {"player": {"gold": 700, "cash": 9}, "featureOptions": {
            "existing": {"changed": 1, "untouched": {"old": [False, None, 0]}},
            "unknown": {"opaque": "keep"},
        }}}

    def test_single_option_merges_both_levels_and_replaces_only_that_value(self):
        save = self.farm()
        result = feature_options.apply(save, {"existing": {"changed": {"replacement": [0, False, None]}}})
        self.assertEqual(result, {"saved": 1, "ignored": 0})
        self.assertEqual(save["userInfo"]["featureOptions"], {
            "existing": {"changed": {"replacement": [0, False, None]},
                         "untouched": {"old": [False, None, 0]}},
            "unknown": {"opaque": "keep"},
        })
        self.assertEqual(save["userInfo"]["player"], {"gold": 700, "cash": 9})

    def test_false_zero_null_arrays_and_unknown_options_are_detached(self):
        save = self.farm()
        incoming = {"new": {"false": False, "zero": 0, "null": None,
                            "array": [0, False, None, {"nested": ["value"]}],
                            "forceGranted": 0}}
        expected = copy.deepcopy(incoming["new"])
        feature_options.apply(save, incoming)
        incoming["new"]["array"][3]["nested"].append("later client mutation")
        self.assertEqual(save["userInfo"]["featureOptions"]["new"], expected)

    def test_server_owned_snapshot_values_are_ignored_while_normal_options_save(self):
        from commands import _FEATURE_END_GRANT_FLAGS
        save = self.farm()
        saved = save["userInfo"]["featureOptions"]
        protected = {
            "irrigation": {"irrigation": {"waterPlots": {"farm": {"amount": 20}}}},
            "UGCDeco": {"UGCDeco": {"ugc_materials": {"wood": 7}, "ugc_completed": {"house": 1}}},
            "slotMachine": {"freeSpins": 3},
            "leslotmachine": {"freeSpins": 2},
        }
        saved.update(copy.deepcopy(protected))
        incoming = {feature: {"overwrite": {"amount": 999999}} for feature in protected}
        pairs = {(feature, option) for (feature, _method), option in _FEATURE_END_GRANT_FLAGS.items()}
        for feature, option in pairs:
            saved.setdefault(feature, {})[option] = 1
            incoming.setdefault(feature, {})[option] = 0
            incoming[feature]["ordinaryPreference"] = False
        incoming["new"] = {"forceGranted": False, "choice": 0}
        result = feature_options.apply(save, incoming)
        actual = save["userInfo"]["featureOptions"]
        for feature, value in protected.items():
            self.assertEqual(actual[feature], value)
        for feature, option in pairs:
            self.assertEqual(actual[feature][option], 1)
            self.assertIs(actual[feature]["ordinaryPreference"], False)
        self.assertEqual(actual["new"], {"forceGranted": False, "choice": 0})
        self.assertEqual(result["ignored"], len(protected) + len(pairs))

    def test_protected_namespaces_cannot_be_created_through_preferences(self):
        save = self.farm()
        before = copy.deepcopy(save)
        feature_options.apply(save, {"UGCDeco": {"UGCDeco": {"ugc_materials": {"wood": 900}}}})
        self.assertEqual(save, before)

    def test_invalid_later_value_rejects_whole_merge_without_mutating_any_save_field(self):
        for bad in (float("nan"), float("inf"), float("-inf"), b"bytes", {"set"}, (1, 2), object()):
            with self.subTest(bad=repr(bad)):
                save = self.farm()
                before = copy.deepcopy(save)
                with self.assertRaises(ValueError):
                    feature_options.apply(save, {"existing": {"changed": 9}, "later": {"bad": bad}})
                self.assertEqual(save, before)

    def test_invalid_map_shapes_and_nonstring_keys_are_atomic(self):
        bad_maps = (None, [], 0, {"feature": None}, {"feature": []}, {1: {}},
                    {"feature": {1: "bad"}}, {"feature": {"nested": {1: "bad"}}})
        for incoming in bad_maps:
            with self.subTest(incoming=incoming):
                save = self.farm()
                before = copy.deepcopy(save)
                with self.assertRaises(ValueError):
                    feature_options.apply(save, incoming)
                self.assertEqual(save, before)

    def test_invalid_protected_value_is_still_validated_before_ignoring_it(self):
        save = self.farm()
        before = copy.deepcopy(save)
        with self.assertRaises(ValueError):
            feature_options.apply(save, {"new": {"ok": True}, "irrigation": {"bad": float("nan")}})
        self.assertEqual(save, before)

    def test_circular_deep_numerous_and_large_values_are_rejected_before_mutation(self):
        circular = []
        circular.append(circular)
        deep = None
        for _ in range(feature_options.MAX_DEPTH + 1):
            deep = [deep]
        for bad in (circular, deep, [None] * feature_options.MAX_NODES,
                    "a" * (feature_options.MAX_JSON_BYTES + 1)):
            with self.subTest(kind=type(bad).__name__):
                save = self.farm()
                before = copy.deepcopy(save)
                with self.assertRaises(ValueError):
                    feature_options.apply(save, {"new": {"value": bad}})
                self.assertEqual(save, before)

    def test_encoded_json_size_and_accumulated_document_size_are_bounded(self):
        save = {"userInfo": {"featureOptions": {"old": {"value": "a" * 50}}}}
        before = copy.deepcopy(save)
        with mock.patch.object(feature_options, "MAX_JSON_BYTES", 128):
            with self.assertRaises(ValueError):
                feature_options.apply(save, {"new": {"value": "b" * 50}})
        self.assertEqual(save, before)
        with mock.patch.object(feature_options, "MAX_JSON_BYTES", 64):
            with self.assertRaises(ValueError):
                feature_options.apply({"userInfo": {}}, {"new": {"value": "\u00e9" * 12}})

    def test_missing_map_can_be_created_and_empty_feature_maps_preserve_siblings(self):
        save = {"userInfo": {}}
        feature_options.apply(save, {"new": {"option": None}, "empty": {}})
        feature_options.apply(save, {"new": {}})
        self.assertEqual(save, {"userInfo": {"featureOptions": {"new": {"option": None}, "empty": {}}}})

    def test_bad_existing_map_is_not_silently_replaced(self):
        for existing in (None, [], {"broken": 1}):
            save = {"userInfo": {"featureOptions": existing}}
            before = copy.deepcopy(save)
            with self.assertRaises(ValueError):
                feature_options.apply(save, {"new": {"option": 1}})
            self.assertEqual(save, before)


class FeatureOptionWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    def test_full_and_partial_saves_survive_gateway_and_reload_without_awards(self):
        path = self.write_fixture()
        save = self.player.session("fixture-farmer")
        player_before = copy.deepcopy(save["userInfo"]["player"])
        full = copy.deepcopy(save["userInfo"]["featureOptions"])
        irrigation_before = copy.deepcopy(full["irrigation"])
        full["irrigation"] = {"irrigation": {"waterPlots": {"farm": {"amount": 999999}}}}
        full["unimplementedFeature"] = {"zero": 0, "false": False, "null": None, "array": [False, None, 0]}
        response = self.gateway([
            self.command("UserService.saveFeatureOptions", [full], 1),
            self.command("UserService.saveFeatureOptions", [{"unimplementedFeature": {"zero": 2}}], 2),
        ])
        self.assertEqual(response.status_code, 200, response.data)
        results = remoting.decode(response.data).bodies[0][1].body["data"]
        self.assertEqual([result["data"] for result in results], [None, None])
        self.assertEqual(save["userInfo"]["featureOptions"]["irrigation"], irrigation_before)
        self.assertEqual(save["userInfo"]["player"], player_before)
        expected = {"zero": 2, "false": False, "null": None, "array": [False, None, 0]}
        self.assertEqual(json.loads(path.read_text())["userInfo"]["featureOptions"]["unimplementedFeature"], expected)
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.assertEqual(self.player.session("fixture-farmer")["userInfo"]["featureOptions"]["unimplementedFeature"], expected)

    def test_invalid_feature_options_preserve_earlier_commands_in_batch(self):
        path = self.write_fixture()
        before_memory = copy.deepcopy(self.player.session("fixture-farmer"))
        response = self.gateway([
            self.command("UserService.incrementActionCount", ["must-survive"], 1),
            self.command("UserService.saveFeatureOptions", [{"valid": {"setting": 1}, "invalid": []}], 2),
        ])
        fixtures.gateway_results(self, response, [0, 29])
        before_memory["userInfo"]["player"]["actionCounts"]["must-survive"] = 1
        self.assertEqual(json.loads(path.read_text()), before_memory)
        self.assertEqual(self.player.session("fixture-farmer"), before_memory)

    def test_valid_preference_merge_survives_following_command_rejection(self):
        path = self.write_fixture()
        before_memory = copy.deepcopy(self.player.session("fixture-farmer"))
        response = self.gateway([
            self.command("UserService.saveFeatureOptions", [{"new": {"setting": 1}}], 1),
            self.command("UserService.setActionCount", ["invalid", "not-a-number"], 2),
        ])
        fixtures.gateway_results(self, response, [0, 29])
        before_memory["userInfo"]["featureOptions"]["new"] = {"setting": 1}
        self.assertEqual(json.loads(path.read_text()), before_memory)
        self.assertEqual(self.player.session("fixture-farmer"), before_memory)

    def test_missing_or_extra_feature_option_arguments_do_not_mutate_the_farm(self):
        path = self.write_fixture()
        before = path.read_bytes()
        for params in ([], [{"new": {"setting": True}}, "extra"]):
            with self.subTest(params=params):
                response = self.gateway([self.command("UserService.saveFeatureOptions", params)])
                fixtures.assert_gateway_rejected(self, response)
                self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
