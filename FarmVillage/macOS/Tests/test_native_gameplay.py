"""Offline acceptance-verifier regressions; synthetic AMF never leaves memory."""

import base64
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import pyamf
from pyamf import remoting


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("native_gameplay_verifier", Path(__file__).with_name("verify_native_gameplay.py"))
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


def wire_batch(commands, results, *, document="initial", exchange=1, uid="verifier-fixture"):
    request = remoting.Envelope(pyamf.AMF0)
    request["/1"] = remoting.Request("FarmService", body=[{"uid": uid}, commands, True])
    response = remoting.Envelope(pyamf.AMF0)
    response["/1"] = remoting.Response({"errorType": 0, "data": results})
    def record(message):
        return {"id": exchange, "documentId": document,
                "base64": base64.b64encode(remoting.encode(message).getvalue()).decode("ascii")}
    return {"requests": [record(request)], "responses": [dict(record(response), status=200)]}


def fixture(plot_ids=(4,)):
    before = json.loads((ROOT / "villages/initial.json").read_text())
    before["userInfo"]["player"]["userId"] = "verifier-fixture"
    after = copy.deepcopy(before)
    after["userInfo"]["player"]["gold"] += 88 * len(plot_ids)
    commands, results = [], []
    for sequence, plot_id in enumerate(plot_ids, start=3):
        plot = next(obj for obj in after["world"]["objectsArray"] if obj["id"] == plot_id)
        plot["state"] = "fallow"
        commands.append(pyamf.ASObject(functionName="WorldService.performAction", sequence=sequence,
            params=pyamf.MixedArray({0: "harvest", 1: copy.deepcopy(plot), 2: pyamf.MixedArray()})))
        results.append({"sequenceNumber": sequence, "errorType": 0, "id": plot_id, "data": {"id": plot_id}})
    initial = wire_batch(pyamf.MixedArray(dict(enumerate(commands))), results)
    reload_wire = wire_batch([{"functionName": "UserService.initUser", "sequence": 1, "params": []}],
        [{"sequenceNumber": 1, "errorType": 0, "data": copy.deepcopy(after)}], document="reloaded")
    return {"save-before.json": before, "save-after.json": after,
            "save-reloaded.json": copy.deepcopy(after), "gateway-before-reload.json": initial,
            "gateway-wire.json": reload_wire}


def rewrite_response(wire, mutate):
    record = wire["responses"][0]
    message = remoting.decode(base64.b64decode(record["base64"]))
    mutate(message.bodies[0][1].body)
    record["base64"] = base64.b64encode(remoting.encode(message).getvalue()).decode("ascii")


class NativeGameplayVerifierTests(unittest.TestCase):
    def test_actual_amf_roundtrip_with_numeric_key_arrays(self):
        report = verifier.verify(fixture())
        self.assertTrue(report["passed"])
        self.assertEqual(report["harvested_plot_ids"], [4])
        self.assertEqual(report["gold_delta"], 88)

    def test_both_starter_harvests_require_176_coins(self):
        report = verifier.verify(fixture((4, 5)))
        self.assertEqual(report["harvested_plot_ids"], [4, 5])
        self.assertEqual(report["gold_delta"], 176)

    def test_legacy_capture_without_exchange_ids_uses_amf_sequences(self):
        artifacts = fixture()
        for name in ("gateway-before-reload.json", "gateway-wire.json"):
            for kind in ("requests", "responses"):
                for record in artifacts[name][kind]:
                    record.pop("id")
                    record.pop("documentId")
        self.assertTrue(verifier.verify(artifacts)["passed"])

    def test_explicit_exchange_id_cannot_match_wrong_response(self):
        artifacts = fixture()
        artifacts["gateway-before-reload.json"]["responses"][0]["id"] = 999
        with self.assertRaisesRegex(verifier.VerificationError, "no correlated"):
            verifier.verify(artifacts)

    def test_document_identity_is_part_of_exchange_match(self):
        artifacts = fixture()
        artifacts["gateway-wire.json"]["responses"][0]["documentId"] = "old-document"
        with self.assertRaisesRegex(verifier.VerificationError, "multiple documents"):
            verifier.verify(artifacts)

    def test_explicit_document_identity_must_change_after_reload(self):
        artifacts = fixture()
        for kind in ("requests", "responses"):
            artifacts["gateway-wire.json"][kind][0]["documentId"] = "initial"
        with self.assertRaisesRegex(verifier.VerificationError, "original document"):
            verifier.verify(artifacts)

    def test_document_only_capture_cannot_mix_request_and_response_documents(self):
        artifacts = fixture()
        wire = artifacts["gateway-wire.json"]
        for kind in ("requests", "responses"):
            wire[kind][0].pop("id")
        wire["responses"][0]["documentId"] = "original-document"
        with self.assertRaisesRegex(verifier.VerificationError, "multiple documents"):
            verifier.verify(artifacts)

    def test_document_only_capture_requires_document_on_response(self):
        artifacts = fixture()
        wire = artifacts["gateway-wire.json"]
        for kind in ("requests", "responses"):
            wire[kind][0].pop("id")
        wire["responses"][0].pop("documentId")
        with self.assertRaisesRegex(verifier.VerificationError, "no correlated"):
            verifier.verify(artifacts)

    def test_successful_http_status_is_required(self):
        artifacts = fixture()
        artifacts["gateway-before-reload.json"]["responses"][0]["status"] = 400
        with self.assertRaisesRegex(verifier.VerificationError, "HTTP 400"):
            verifier.verify(artifacts)

    def test_amf_command_error_is_rejected_even_with_http_200(self):
        artifacts = fixture()
        rewrite_response(artifacts["gateway-before-reload.json"], lambda body: body["data"][0].update(errorType=1))
        with self.assertRaisesRegex(verifier.VerificationError, "AMF error"):
            verifier.verify(artifacts)

    def test_gold_mismatch_is_not_a_gameplay_pass(self):
        artifacts = fixture()
        artifacts["save-after.json"]["userInfo"]["player"]["gold"] += 1
        with self.assertRaisesRegex(verifier.VerificationError, "Gold delta"):
            verifier.verify(artifacts)

    def test_grown_disk_state_after_harvest_is_rejected(self):
        artifacts = fixture()
        artifacts["save-after.json"]["world"]["objectsArray"][3]["state"] = "grown"
        with self.assertRaisesRegex(verifier.VerificationError, "save-after: plot 4 is not fallow"):
            verifier.verify(artifacts)

    def test_reload_must_retain_disk_state(self):
        artifacts = fixture()
        artifacts["save-reloaded.json"]["world"]["objectsArray"][3]["state"] = "grown"
        with self.assertRaisesRegex(verifier.VerificationError, "save-reloaded: plot 4 is not fallow"):
            verifier.verify(artifacts)

    def test_reloaded_amf_must_contain_fallow_plot(self):
        artifacts = fixture()
        rewrite_response(artifacts["gateway-wire.json"],
            lambda body: body["data"][0]["data"]["world"]["objectsArray"][3].update(state="grown"))
        with self.assertRaisesRegex(verifier.VerificationError, "reloaded initUser response: plot 4 is not fallow"):
            verifier.verify(artifacts)

    def test_reloaded_amf_must_contain_original_player_uid(self):
        artifacts = fixture()
        rewrite_response(artifacts["gateway-wire.json"],
            lambda body: body["data"][0]["data"]["userInfo"]["player"].update(userId="different-farmer"))
        with self.assertRaisesRegex(verifier.VerificationError, "different player UID"):
            verifier.verify(artifacts)

    def test_harvest_response_must_confirm_same_plot_id(self):
        artifacts = fixture()
        rewrite_response(artifacts["gateway-before-reload.json"], lambda body: body["data"][0]["data"].update(id=5))
        with self.assertRaisesRegex(verifier.VerificationError, "same object ID"):
            verifier.verify(artifacts)

    def test_missing_harvest_response_is_rejected(self):
        artifacts = fixture()
        artifacts["gateway-before-reload.json"]["responses"].clear()
        with self.assertRaisesRegex(verifier.VerificationError, "no correlated"):
            verifier.verify(artifacts)

    def test_response_command_sequence_must_match(self):
        artifacts = fixture()
        rewrite_response(artifacts["gateway-wire.json"], lambda body: body["data"][0].update(sequenceNumber=99))
        with self.assertRaisesRegex(verifier.VerificationError, "no correlated"):
            verifier.verify(artifacts)

    def test_duplicate_exchange_ids_are_rejected(self):
        artifacts = fixture()
        wire = artifacts["gateway-before-reload.json"]
        wire["requests"].append(copy.deepcopy(wire["requests"][0]))
        with self.assertRaisesRegex(verifier.VerificationError, "duplicate capture exchange IDs"):
            verifier.verify(artifacts)

    def test_ambiguous_legacy_response_cannot_pass(self):
        artifacts = fixture()
        wire = artifacts["gateway-before-reload.json"]
        for kind in ("requests", "responses"):
            for record in wire[kind]:
                record.pop("id")
                record.pop("documentId")
        wire["responses"].append(copy.deepcopy(wire["responses"][0]))
        with self.assertRaisesRegex(verifier.VerificationError, "ambiguous response"):
            verifier.verify(artifacts)

    def test_extreme_json_integer_produces_failed_report(self):
        with tempfile.TemporaryDirectory(prefix="native-gameplay-verifier-") as directory:
            output = Path(directory)
            artifacts = fixture()
            artifacts["save-before.json"]["userInfo"]["player"]["gold"] = 10 ** 1000
            for name, value in artifacts.items():
                (output / name).write_text(json.dumps(value))
            (output / "verification.json").write_text('{"passed": true}')
            self.assertEqual(verifier.main([str(output)]), 1)
            report = json.loads((output / "verification.json").read_text())
            self.assertFalse(report["passed"])
            self.assertIn("finite number", report["error"])

    def test_cli_writes_compact_report_and_input_hashes(self):
        with tempfile.TemporaryDirectory(prefix="native-gameplay-verifier-") as directory:
            output = Path(directory)
            for name, value in fixture().items():
                (output / name).write_text(json.dumps(value))
            self.assertEqual(verifier.main([str(output)]), 0)
            report = json.loads((output / "verification.json").read_text())
            self.assertTrue(report["passed"])
            self.assertEqual(set(report["input_sha256"]), set(verifier.INPUT_FILES))


if __name__ == "__main__":
    unittest.main()
