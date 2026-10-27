"""Verify native gameplay artifacts offline, without importing or starting the game.

Run with the prepared runtime's Python and Py3AMF dependency:
    python -I -B macOS/Tests/verify_native_gameplay.py /absolute/artifact/folder

The native harness owns creation of the five input files. This verifier only
reads them and atomically writes verification.json in the same folder.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile


INPUT_FILES = (
    "save-before.json", "save-after.json", "save-reloaded.json",
    "gateway-before-reload.json", "gateway-wire.json",
)
STARTER_POSITIONS = {4: {"x": 19, "y": 9, "z": 0}, 5: {"x": 19, "y": 13, "z": 0}}
EGGPLANT_YIELD = 88


class VerificationError(ValueError):
    """An artifact does not establish the required real-client behavior."""


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def array(value, label):
    """Flash AMF0 arrays commonly decode to numeric-key MixedArray dictionaries."""
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, dict):
        try:
            keys = sorted(value, key=int)
            indexes = [int(key) for key in keys]
        except (ValueError, TypeError) as error:
            raise VerificationError(f"{label}: invalid AMF array keys") from error
        require(indexes == list(range(len(keys))), f"{label}: nonconsecutive AMF array")
        return [value[key] for key in keys]
    raise VerificationError(f"{label}: expected an array")


def number(value, label):
    try:
        finite = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        finite = False
    require(finite, f"{label}: expected a finite number")
    return value


def saved_state(value, label):
    try:
        uid = value["userInfo"]["player"]["userId"]
        gold = number(value["userInfo"]["player"]["gold"], f"{label}.gold")
        objects = array(value["world"]["objectsArray"], f"{label}.objectsArray")
        by_id = {}
        for obj in objects:
            require(isinstance(obj, dict), f"{label}: malformed world object")
            object_id = number(obj["id"], f"{label}.object.id")
            require(object_id not in by_id, f"{label}: duplicate object ID {object_id}")
            by_id[object_id] = obj
    except (KeyError, TypeError) as error:
        raise VerificationError(f"{label}: missing save fields: {error}") from error
    require(isinstance(uid, str) and bool(uid), f"{label}: missing player UID")
    return uid, gold, by_id


def decode_record(record, label, *, response):
    # Importing the server would load assets, farms, and network listeners.
    # Py3AMF alone can decode the already captured transport bytes.
    from pyamf import remoting

    require(isinstance(record, dict), f"{label}: expected a capture record")
    if response:
        require(record.get("status") == 200, f"{label}: HTTP {record.get('status')}, expected 200")
    try:
        contents = base64.b64decode(record["base64"], validate=True)
        envelope = remoting.decode(contents)
    except Exception as error:
        raise VerificationError(f"{label}: cannot decode captured AMF: {error}") from error
    require(len(envelope.bodies) == 1, f"{label}: expected one AMF message body")
    target, message = envelope.bodies[0]
    expected = remoting.Response if response else remoting.Request
    require(isinstance(message, expected), f"{label}: unexpected AMF message type")
    body = message.body
    if response:
        require(isinstance(body, dict) and body.get("errorType") == 0,
                f"{label}: unsuccessful AMF response envelope")
        commands = array(body.get("data"), f"{label}.data")
        sequence_key = "sequenceNumber"
    else:
        body = array(body, f"{label}.body")
        require(len(body) >= 2 and isinstance(body[0], dict), f"{label}: incomplete request header")
        require(isinstance(body[0].get("uid"), str), f"{label}: request has no player UID")
        commands = array(body[1], f"{label}.commands")
        sequence_key = "sequence"
    sequences = []
    for index, command in enumerate(commands):
        require(isinstance(command, dict) and sequence_key in command,
                f"{label}: command {index} has no {sequence_key}")
        sequence = number(command[sequence_key], f"{label}.{sequence_key}")
        require(sequence not in sequences, f"{label}: duplicate command sequence {sequence}")
        sequences.append(sequence)
        if response:
            require(command.get("errorType") == 0, f"{label}: command {sequence} returned an AMF error")
        else:
            require(isinstance(command.get("functionName"), str), f"{label}: missing functionName")
    return {"record": record, "target": target, "commands": commands,
            "sequences": tuple(sequences), "uid": None if response else body[0]["uid"], "label": label}


def record_document(record):
    value = record.get("documentId")
    require(value is None or isinstance(value, (str, int)) and not isinstance(value, bool),
            "Capture documentId must be a string or integer")
    return value


def capture_id(record):
    document = record_document(record)
    for key in ("requestId", "id"):
        if record.get(key) is not None:
            require(isinstance(record[key], (str, int)) and not isinstance(record[key], bool),
                    f"Capture {key} must be a string or integer")
            return document, record[key]
    return None


def capture(value, label):
    require(isinstance(value, dict), f"{label}: expected a wire capture object")
    require(isinstance(value.get("requests"), list) and isinstance(value.get("responses"), list),
            f"{label}: missing request/response arrays")
    requests = [decode_record(item, f"{label}.requests[{index}]", response=False)
                for index, item in enumerate(value["requests"])]
    responses = [decode_record(item, f"{label}.responses[{index}]", response=True)
                 for index, item in enumerate(value["responses"])]
    for name, records in (("requests", requests), ("responses", responses)):
        identities = [capture_id(item["record"]) for item in records if capture_id(item["record"]) is not None]
        require(len(set(identities)) == len(identities), f"{label}.{name}: duplicate capture exchange IDs")
    documents = {record_document(item["record"]) for item in requests + responses
                 if record_document(item["record"]) is not None}
    require(len(documents) <= 1, f"{label}: capture contains multiple documents")
    used = set()
    for request in requests:
        request_id = capture_id(request["record"])
        matches = []
        for index, response in enumerate(responses):
            if index in used:
                continue
            if request_id is not None and capture_id(response["record"]) != request_id:
                continue
            request_document = record_document(request["record"])
            response_document = record_document(response["record"])
            if (request_document is not None or response_document is not None) and request_document != response_document:
                continue
            if request["target"] == response["target"] and request["sequences"] == response["sequences"]:
                matches.append(index)
        require(len(matches) <= 1,
                f"{request['label']}: ambiguous response; capture documentId/requestId for each exchange")
        request["response"] = None
        if matches:
            index = matches[0]
            used.add(index)
            request["response"] = responses[index]
    return requests


def result_for(request, command):
    response = request["response"]
    require(response is not None, f"{request['label']}: no correlated successful response")
    return next(item for item in response["commands"] if item["sequenceNumber"] == command["sequence"])


def document_id(requests, label):
    documents = []
    for request in requests:
        value = record_document(request["record"])
        if value is not None:
            if value not in documents:
                documents.append(value)
    require(len(documents) <= 1, f"{label}: capture contains multiple documents")
    return documents[0] if documents else None


def require_fallow(objects, plot_id, position, label):
    plot = objects.get(plot_id)
    require(plot is not None and plot.get("state") == "fallow", f"{label}: plot {plot_id} is not fallow")
    require(plot.get("position") == position, f"{label}: plot {plot_id} moved")


def verify(artifacts):
    uid, gold_before, before = saved_state(artifacts["save-before.json"], "save-before")
    after_uid, gold_after, after = saved_state(artifacts["save-after.json"], "save-after")
    reload_uid, gold_reloaded, reloaded = saved_state(artifacts["save-reloaded.json"], "save-reloaded")
    require(uid == after_uid == reload_uid, "The three saved snapshots have different player UIDs")
    initial_capture = capture(artifacts["gateway-before-reload.json"], "gateway-before-reload")
    harvested = {}
    for request in initial_capture:
        require(request["uid"] == uid, f"{request['label']}: unexpected player UID")
        for command in request["commands"]:
            if command["functionName"] != "WorldService.performAction":
                continue
            params = array(command.get("params"), f"{request['label']}.performAction.params")
            if not params or params[0] != "harvest":
                continue
            require(len(params) >= 3 and isinstance(params[1], dict), "Malformed captured harvest command")
            plot_id = params[1].get("id")
            require(plot_id in STARTER_POSITIONS, f"Unexpected harvested plot {plot_id}; expected starter 4 or 5")
            require(plot_id not in harvested, f"Starter plot {plot_id} was harvested more than once")
            require(params[1].get("itemName") == "eggplant", f"Harvest {plot_id} is not eggplant")
            result = result_for(request, command)
            require(isinstance(result.get("data"), dict) and result["data"].get("id") == plot_id,
                    f"Harvest {plot_id}: response did not confirm the same object ID")
            if "id" in result:
                require(result["id"] == plot_id, f"Harvest {plot_id}: inconsistent response ID")
            harvested[plot_id] = command["sequence"]
    require(harvested, "No captured client-generated WorldService.performAction harvest for starter plot 4 or 5")
    for plot_id in harvested:
        plot = before.get(plot_id)
        require(plot is not None and plot.get("className") == "Plot"
                and plot.get("itemName") == "eggplant" and plot.get("state") == "grown",
                f"save-before: starter plot {plot_id} is not a grown eggplant")
        require(plot.get("position") == STARTER_POSITIONS[plot_id], f"save-before: unexpected position for plot {plot_id}")
        require(not plot.get("isJumbo") and not plot.get("isBigPlot"), f"save-before: plot {plot_id} has altered rewards")
        require_fallow(after, plot_id, plot["position"], "save-after")
        require_fallow(reloaded, plot_id, plot["position"], "save-reloaded")
    expected_delta = EGGPLANT_YIELD * len(harvested)
    require(gold_after - gold_before == expected_delta,
            f"Gold delta {gold_after - gold_before} does not match {expected_delta} for {len(harvested)} starter harvest(s)")
    require(gold_reloaded == gold_after, "Reload changed the persisted gold balance")
    reloaded_capture = capture(artifacts["gateway-wire.json"], "gateway-wire")
    before_document = document_id(initial_capture, "gateway-before-reload")
    reload_document = document_id(reloaded_capture, "gateway-wire")
    if before_document is not None and reload_document is not None:
        require(before_document != reload_document, "The reloaded wire capture belongs to the original document")
    reload_sequences = []
    for request in reloaded_capture:
        require(request["uid"] == uid, f"{request['label']}: unexpected player UID")
        for command in request["commands"]:
            if command["functionName"] != "UserService.initUser":
                continue
            result = result_for(request, command)
            init_uid, init_gold, objects = saved_state(result.get("data"), "reloaded initUser response")
            require(init_uid == uid, "Reloaded initUser response has a different player UID")
            require(init_gold == gold_after, "Reloaded initUser response has a different gold balance")
            for plot_id in harvested:
                require_fallow(objects, plot_id, before[plot_id]["position"], "reloaded initUser response")
            reload_sequences.append(command["sequence"])
    require(reload_sequences, "No correlated real initUser response was captured after reload")
    return {"schema": 1, "passed": True, "uid": uid, "harvested_plot_ids": sorted(harvested),
            "harvest_sequences": {str(key): value for key, value in harvested.items()},
            "gold_before": gold_before, "gold_after": gold_after, "gold_delta": expected_delta,
            "document_before": before_document, "document_reloaded": reload_document,
            "reload_init_sequences": reload_sequences,
            "checks": ["captured AMF harvest and successful response", "persisted grown-to-fallow",
                       "88 coins per starter harvest", "reloaded save retained state",
                       "reloaded AMF initUser retained UID, plots, and gold"]}


def write_report(directory, report):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                         prefix=".verification-", suffix=".json", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, directory / "verification.json")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path, help="absolute native gameplay artifact folder")
    args = parser.parse_args(argv)
    if not args.output_dir.is_absolute() or not args.output_dir.is_dir():
        parser.error("OUTPUT_DIR must be an existing absolute artifact folder")
    hashes = {}
    try:
        artifacts = {}
        for name in INPUT_FILES:
            contents = (args.output_dir / name).read_bytes()
            hashes[name] = hashlib.sha256(contents).hexdigest()
            artifacts[name] = json.loads(contents)
        report = verify(artifacts)
    except (VerificationError, OSError, ValueError, TypeError, OverflowError, ImportError) as error:
        report = {"schema": 1, "passed": False, "error": str(error)}
    report["input_sha256"] = hashes
    try:
        write_report(args.output_dir, report)
    except OSError as error:
        print(f"FAIL: Cannot write verification.json: {error}", file=sys.stderr)
        return 1
    if not report["passed"]:
        print(f"FAIL: {report['error']}", file=sys.stderr)
        return 1
    print(f"PASS: actual AMF harvest of {report['harvested_plot_ids']}, +{report['gold_delta']} coins, "
          f"and matching persisted/reloaded initUser state; report: {args.output_dir / 'verification.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
