"""Isolation tests between the model table and the capability mapping.

Optional flags are declared per model and read by capability.py to decide which
entities a device gets. That makes them a blast radius: a flag added for a hub
reaches every model whose branch happens to set it, and a gate written to read
that flag reaches every model at once if its default slips.

test_model.py pins what each group declares, so a change in model.py shows up
there. These tests cover the other half -- who a flag reaches, and whether a
gate in capability.py still follows the flag it was written for. Flipping a
default from True to False leaves model.py untouched and every case in
test_model.py green, and would only be caught here.

Model ids come from walking the table rather than a hand-kept list, so a model
added later joins these tests on its own.
"""

import pytest

from custom_components.cozytouch.capability import (
    describe_capability_value,
    get_capability_infos,
)
from custom_components.cozytouch.infos import CapabilityType
from custom_components.cozytouch.model import CozytouchDeviceType, get_model_infos

AIR_CONDITIONERS = {557, 558, 559, 560, 561}
# The rooms a gateway numbers past its fifth, same branch and now the same
# eco gate : the household that has both ranges sees an eco mode on neither.
# ROOM runs to productId 111, which is modelId 1748 -- `ROOM_19`. The branch
# this replaced stopped at 1737 because that is where one household stopped.
SECOND_BLOCK_AIR_CONDITIONERS = set(range(1734, 1749))

# Every model id the table maps, as opposed to the ones it sends to UNKNOWN.
# The span reaches past the vendor's highest catalogued model (3652) rather
# than stopping at the 2500 a one-by-one sweep once reached: a branch added
# above the old bound would have been walked by nothing.
MAPPED_MODEL_IDS = frozenset(
    modelId
    for modelId in range(1, 3700)
    if get_model_infos(modelId)["type"] is not CozytouchDeviceType.UNKNOWN
)


# The two capabilities a THZONE was captured reporting, and nothing else.
THZONE_CAPABILITIES = {218, 100014}


def test_a_zone_gets_no_wifi_sensor():
    """218 reads "0" on a zone whose `isAvailable` is true, so any sensor would
    sit wrong for good and contradict the device it belongs to. The radio
    belongs to the gateway the zone hangs off, and a zone has nothing else to
    show either, so it gets no entity at all.
    """
    zone = get_capability_infos(
        get_model_infos(1505, None, "THZONE_0"), 218, "0", THZONE_CAPABILITIES
    )

    assert zone == {}


def test_218_is_a_connectivity_code_and_not_a_wifi_flag():
    """It was mapped as `wifiConnected`, a boolean that read "off" on working
    hardware because the value is never "1". Atlantic calls it
    ConnectivityDiagnosis and publishes the codes: the corpus's 0 and 4 are
    "no error" and "the Navilink interface is offline".
    """
    result = get_capability_infos(get_model_infos(418), 218, "0", {218})

    assert result["name"] == "connectivity_diagnosis"
    assert result["type"] == "string"
    assert result["enabled_by_default"] is False
    assert describe_capability_value(218, "0") == "ok"
    assert describe_capability_value(218, "4") == "interface_offline"


def test_a_zone_maps_to_nothing_at_all():
    """Which is the honest answer for it: a zone is a name and a place in the
    device tree, not a thing with readings. Naming the model is what stops it
    reading as an unknown product and asking for a report about itself.
    """
    zone = get_model_infos(1505, None, "THZONE_0")
    resolved = [
        get_capability_infos(zone, capabilityId, "0", THZONE_CAPABILITIES)
        for capabilityId in sorted(THZONE_CAPABILITIES)
    ]

    assert all(not infos for infos in resolved)


@pytest.mark.parametrize(
    ("flag", "owners"),
    [
        ("quietModeAvailable", AIR_CONDITIONERS | SECOND_BLOCK_AIR_CONDITIONERS),
        (
            "awayModeTemperatureAvailable",
            AIR_CONDITIONERS
            | SECOND_BLOCK_AIR_CONDITIONERS
            # The gateways, which report the away mode and hold no setpoint
            # for it. 1680 joins its sibling 1681 now that the productId the
            # vendor gives it is read rather than a hand-written id list.
            | {556, 1457, 1680, 1681, 1758, 2447, 2448, 2449, 2450},
        ),
        ("ecoModeAvailable", AIR_CONDITIONERS | SECOND_BLOCK_AIR_CONDITIONERS),
        ("overrideModeAvailable", {418}),
        ("currentTemperatureAvailableZ1", {76, 211, 219, 418}),
        ("currentTemperatureAvailableZ2", {76, 211, 219, 418}),
        ("exhaustTemperatureAvailable", {76, 211, 219, 418}),
        # Documented in model.py and read in capability.py, but no model has ever
        # declared it. It only ever resolves to its default.
        ("currentTemperatureAvailable", set()),
    ],
)
def test_a_flag_reaches_exactly_the_models_that_name_it(flag, owners):
    """Widening a branch to reach a hub must not drag other products in."""
    declared = {m for m in MAPPED_MODEL_IDS if flag in get_model_infos(m)}
    assert declared == owners


@pytest.mark.parametrize("capabilityId", [171, 172])
def test_the_absence_setpoint_appears_exactly_where_its_flag_allows_it(capabilityId):
    """Both halves of the setpoint follow awayModeTemperatureAvailable."""
    for modelId in sorted(MAPPED_MODEL_IDS):
        infos = get_model_infos(modelId)
        reported = {160, 161, 162, 163, capabilityId}
        mapped = bool(get_capability_infos(infos, capabilityId, "20.0", reported))
        assert mapped is infos.get("awayModeTemperatureAvailable", True), modelId


def test_the_cooling_absence_setpoint_is_read_only():
    """171 is named and typed, but nothing has been seen writing it."""
    infos = get_model_infos(1447)
    capability = get_capability_infos(infos, 171, "35.0", {162, 163, 171})

    assert capability is not None
    assert capability.name == "away_mode_cooling_temperature"
    assert capability.type is CapabilityType.TEMPERATURE
    assert capability.enabled_by_default is False


def test_the_eco_switch_appears_exactly_where_its_flag_allows_it():
    """Capability 100507 follows ecoModeAvailable, for every model."""
    for modelId in sorted(MAPPED_MODEL_IDS):
        infos = get_model_infos(modelId)
        mapped = bool(get_capability_infos(infos, 100507, "0", {100507}))
        assert mapped is infos.get("ecoModeAvailable", True), modelId


def test_the_eco_preset_is_wired_exactly_where_its_flag_allows_it():
    """The climate preset is a second door onto 100507, and needs the same gate."""
    for modelId in sorted(MAPPED_MODEL_IDS):
        infos = get_model_infos(modelId)
        climate = get_capability_infos(infos, 7, "3", {7, 100507}) or {}
        wired = "ecoCapabilityId" in climate

        if infos["type"] is CozytouchDeviceType.AC:
            assert wired is infos.get("ecoModeAvailable", True), modelId
        else:
            # Only the air conditioner branch ever reaches for the preset.
            assert not wired, modelId


@pytest.mark.parametrize(
    "hub", [556, 1457, 1681, 1758, 2447, 2448, 2449, 2450]
)
def test_a_hub_declares_nothing_that_reaches_a_heating_product(hub):
    """Touching a hub is the change that keeps happening. Bound what it can move."""
    hubFlags = set(get_model_infos(hub)) - {
        "modelId",
        "name",
        "type",
        "HVACModes",
        "HVACModesCapabilityId",
    }
    heating = {
        m
        for m in MAPPED_MODEL_IDS
        if get_model_infos(m)["type"]
        in (
            CozytouchDeviceType.GAZ_BOILER,
            CozytouchDeviceType.HEAT_PUMP,
            CozytouchDeviceType.WATER_HEATER,
            CozytouchDeviceType.TOWEL_RACK,
            CozytouchDeviceType.RADIATOR,
            CozytouchDeviceType.THERMOSTAT,
        )
    }
    for flag in hubFlags:
        assert not {m for m in heating if flag in get_model_infos(m)}, flag
