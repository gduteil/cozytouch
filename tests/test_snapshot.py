"""Snapshot of everything the two tables answer.

The other test files pin the cases somebody thought about. This one pins the
rest, in three files. `models.json` is every model id the table maps.
`capabilities.json` is every capability id the chain claims, in full, against
one model of each device type -- the same probes as
scripts/dump_capability_map.py. `model_capabilities.json` is the other 2486
models, one digest per model rather than the whole answer, because a row that
says "this id means something else on that product" is exactly what a probe
cannot see. The point is to make a pure refactor provable: if the snapshot
files do not change, neither did a single answer.

Like every test here it is characterisation, not specification. Regenerate on
purpose, in the same commit as the change the diff shows:

    UPDATE_SNAPSHOTS=1 pytest tests/test_snapshot.py

Sets are stored sorted and dict keys as strings, because the snapshot lives as
JSON; the comparison happens on the JSON side of that round trip.
"""

import hashlib
import json
import os
import pathlib

import pytest

from custom_components.cozytouch.capability import get_capability_infos
from custom_components.cozytouch.model import CozytouchDeviceType, get_model_infos
from scripts.dump_capability_map import (
    EVERY_ID,
    EXTRA_MODELS,
    PROBES,
    VALUES,
    ZONE_PROBE_MODEL,
    ZONE_PROBE_NAME,
)

SNAPSHOT_DIR = pathlib.Path(__file__).parent / "snapshots"

# The whole span test_capability.py walks, so a model added inside it joins
# the snapshot on its own.
MODEL_ID_RANGE = range(1, 3700)

# Names change what the table answers: a zone is recognised by deviceName
# before any id, and the air conditioner branches print zoneName into the
# entity name. One case per naming path, plus the unknown fall-through.
NAMED_MODEL_CASES = (
    (999999, None, None),
    (1505, None, "THZONE_0"),
    (1505, "Salon", "THZONE_0"),
    (557, "Salon", None),
    (1734, "Salon", None),
    (562, "Salon", None),
)

# One model per device type plus the ids whose branch differs from their
# type's probe -- scripts/dump_capability_map.py explains each pick.
PROBE_MODELS = (*PROBES.values(), *EXTRA_MODELS)

# The climate branch is the only reader of availableCapabilityIds, wiring an
# optional feature only when the device reports the id backing it. The full
# sweep hands it every id; this hands it none, so both sides of every gate in
# that branch are pinned.
CLIMATE_IDS = (1, 2, 7, 8)

# Value-sensitive branches, pinned on the side the full sweep cannot reach.
EDGE_CASES = {"119 at the no-outside-probe sentinel": (56, 119, "-327.68")}


# Which ids the sweep below asks about. The probe snapshot already walks all
# 6400 ids, so an id the chain starts claiming shows up there and lands here
# when this list is regenerated beside it; asking every model about every id
# costs eighteen seconds and answers nothing the probes have not.
CLAIMED_IDS_FILE = "claimed_ids.json"


def _jsonable(data):
    """The snapshot as JSON stores it: sets sorted, dict keys as strings."""
    return json.loads(json.dumps(data, sort_keys=True, default=sorted))


def _assert_matches(filename, data):
    path = SNAPSHOT_DIR / filename
    dumped = json.dumps(_jsonable(data), indent=1, sort_keys=True) + "\n"

    if os.environ.get("UPDATE_SNAPSHOTS"):
        SNAPSHOT_DIR.mkdir(exist_ok=True)
        path.write_text(dumped)
        return

    if not path.exists():
        pytest.fail(
            f"{path} does not exist -- generate it with "
            "UPDATE_SNAPSHOTS=1 pytest tests/test_snapshot.py"
        )

    assert json.loads(dumped) == json.loads(path.read_text()), (
        f"the mapping no longer matches {path} -- if the change is meant, "
        "regenerate with UPDATE_SNAPSHOTS=1 pytest tests/test_snapshot.py "
        "in the same commit"
    )


def _model_infos(modelId):
    deviceName = ZONE_PROBE_NAME if modelId == ZONE_PROBE_MODEL else None
    return get_model_infos(modelId, None, deviceName)


def test_the_model_table_answers_what_it_answered():
    snapshot = {
        str(modelId): get_model_infos(modelId)
        for modelId in MODEL_ID_RANGE
        if get_model_infos(modelId)["type"] is not CozytouchDeviceType.UNKNOWN
    }
    for modelId, zoneName, deviceName in NAMED_MODEL_CASES:
        key = f"{modelId} zoneName={zoneName} deviceName={deviceName}"
        snapshot[key] = get_model_infos(modelId, zoneName, deviceName)

    _assert_matches("models.json", snapshot)


def test_the_capability_mapping_answers_what_it_answered():
    everyId = set(EVERY_ID)
    full = {
        str(modelId): {
            str(capabilityId): infos
            for capabilityId in EVERY_ID
            # None is the chain not claiming the id; left out so the file only
            # holds answers. A claim that disappears still fails the compare.
            if (
                infos := get_capability_infos(
                    _model_infos(modelId),
                    capabilityId,
                    VALUES.get(capabilityId, "0"),
                    everyId,
                )
            )
            is not None
        }
        for modelId in PROBE_MODELS
    }
    bare = {
        str(modelId): {
            str(capabilityId): get_capability_infos(
                _model_infos(modelId), capabilityId, "0", set()
            )
            for capabilityId in CLIMATE_IDS
        }
        for modelId in PROBE_MODELS
    }
    edges = {
        label: get_capability_infos(
            _model_infos(modelId), capabilityId, value, everyId
        )
        for label, (modelId, capabilityId, value) in EDGE_CASES.items()
    }

    _assert_matches(
        "capabilities.json",
        {"every id reported": full, "none reported": bare, "edge values": edges},
    )


def _digest(modelId, claimedIds):
    """Everything the chain answers for one model, as one line of the file."""
    answers = {}
    for capabilityId in claimedIds:
        infos = get_capability_infos(
            _model_infos(modelId),
            capabilityId,
            VALUES.get(capabilityId, "0"),
            set(claimedIds),
        )
        if infos:
            # modelId is the key of the line this digest goes on, and leaving
            # it in the hash would make every model differ from every other.
            answers[capabilityId] = {
                key: value for key, value in infos.items() if key != "modelId"
            }
    dumped = json.dumps(_jsonable(answers), sort_keys=True, default=str)
    return hashlib.sha256(dumped.encode()).hexdigest()[:16]


def test_every_model_answers_what_it_answered():
    """The probes cover one model per device type; this covers the other 2486.

    A row of the table that says "this id means something else on that
    product" is exactly what a probe cannot see, and exactly what a
    restructuring of the mapping gets wrong. One digest per model id, runs of
    equal digests collapsed, so a model whose answers change is one changed
    line.
    """
    path = SNAPSHOT_DIR / CLAIMED_IDS_FILE

    if os.environ.get("UPDATE_SNAPSHOTS"):
        claimed = sorted(
            capabilityId
            for capabilityId in EVERY_ID
            if any(
                get_capability_infos(
                    _model_infos(modelId),
                    capabilityId,
                    VALUES.get(capabilityId, "0"),
                    set(EVERY_ID),
                )
                is not None
                for modelId in PROBE_MODELS
            )
        )
        SNAPSHOT_DIR.mkdir(exist_ok=True)
        path.write_text(json.dumps(claimed, indent=1) + "\n")
    else:
        claimed = json.loads(path.read_text())

    runs = []
    for modelId in MODEL_ID_RANGE:
        digest = _digest(modelId, claimed)
        if runs and runs[-1][2] == digest:
            runs[-1][1] = modelId
        else:
            runs.append([modelId, modelId, digest])

    # A list, in model id order: a dict would be sorted as text, putting 1010
    # before 13, and this file is meant to be read down the page.
    _assert_matches(
        "model_capabilities.json",
        [
            f"{first}-{last} {digest}" if first != last else f"{first} {digest}"
            for first, last, digest in runs
        ],
    )
