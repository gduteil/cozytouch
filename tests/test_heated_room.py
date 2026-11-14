"""A room slot that says an electric heater drives it gets no air conditioner.

557-561 is a room's index behind a gateway, and the room is given the air
conditioner's modes and controls because nothing else it reported told the
two apart. Capability 103026, `thermal_generator`, does : the room's own list
of what heats or cools it.

    radiators behind a CozyBox (gduteil/cozytouch#172)   128  panel heater, I2G
    Fujitsu splits behind a HUB Cozytouch (#61)            8  air-to-air split
    the Navizone rooms (scripts/test_ha/navizone.json)     8  air-to-air split
    Takao M3 behind a Naviclim (gduteil/cozytouch#1, #12)  absent

A room declaring electric heaters and nothing else loses what only an air
conditioner has : the cool, auto, fan and dry modes, the fan speed, the swing,
the quiet mode and the cooling setpoint. Everything else answers as before,
and so does every room that reports 8, a mix, or no 103026 at all.

The values below are the #172 capture's own, cut to the ids this reads. Issue
#190 (an OROSI 2) and its comments are the same report.
"""

import pytest

from custom_components.cozytouch.capability import get_capability_infos
from custom_components.cozytouch.model import (
    CozytouchDeviceType,
    get_device_model_infos,
)
from homeassistant.components.climate import HVACMode

# What the radiators of #172 report on the ids an air conditioner is built
# from. The Fujitsu splits of #61 read 197 on 100004 and 411 on 166, and
# report the same ids.
RADIATOR = {
    7: "4",
    100004: "1",
    100021: "201",
    100022: "415",
    166: "17",
    177: "20.0",
    100800: "2",
    100801: "1",
    100802: "0",
    100803: "1",
    100804: "0",
    103026: "128",
}

AC_ONLY = (
    "fanModeCapabilityId",
    "swingModeCapabilityId",
    "swingOnCapabilityId",
    "quietModeCapabilityId",
    "targetCoolCapabilityId",
)


def room(capabilities, gateway=2447, family="Connectivity_Box"):
    box = {
        "deviceId": 2,
        "modelId": gateway,
        "productId": 63,
        "modelFamily": family,
        "name": "",
    }
    slot = {
        "deviceId": 1,
        "modelId": 557,
        "productId": 26,
        "masterDeviceId": 2,
        "name": "ROOM_0",
        "capabilities": [
            {"capabilityId": capabilityId, "value": value}
            for capabilityId, value in capabilities.items()
        ],
    }
    return get_device_model_infos([box, slot], slot, "Salon"), set(capabilities)


def entity(infos, available, capabilityId, value="0"):
    return get_capability_infos(infos, capabilityId, value, available)


def test_a_room_driven_by_a_radiator_heats_and_stops():
    infos, _ = room(RADIATOR)

    assert infos.type is CozytouchDeviceType.ROOM
    assert infos.name == "Room (Salon)"
    assert infos.HVACModes == {0: HVACMode.OFF, 4: HVACMode.HEAT}
    assert "fanModes" not in infos
    assert "swingModes" not in infos


def test_its_climate_is_wired_to_none_of_the_air_conditioner_controls():
    infos, available = room(RADIATOR)

    climate = entity(infos, available, 7, "4")

    assert climate.name == "room"
    assert not [key for key in AC_ONLY if key in climate]


@pytest.mark.parametrize("capabilityId", [177, 100802, 100804])
def test_the_swing_quiet_and_cooling_entities_are_not_built(capabilityId):
    """The three a radiator showed on its device page : `swing_mode`,
    `quiet_mode` and `target_cool_temperature`.
    """
    infos, available = room(RADIATOR)

    assert not entity(infos, available, capabilityId).get("name")


@pytest.mark.parametrize(
    ("gateway", "family", "generator"),
    [
        # #61 : HUB Cozytouch and its Fujitsu splits.
        (1457, "Connectivity_Box", "8"),
        # The Navizone rooms.
        (1758, "Air_Conditioning", "8"),
        # gduteil/cozytouch#1 and #12 : a Naviclim's Takao M3, which reports
        # no 103026 and has a swing that works.
        (556, None, None),
        # A room in front of a split and a radiator both.
        (2447, "Connectivity_Box", "24"),
        # Nothing declared.
        (2447, "Connectivity_Box", "0"),
    ],
)
def test_a_room_that_does_not_say_heater_only_keeps_everything(
    gateway, family, generator
):
    capabilities = RADIATOR | {166: "411", 100004: "197"}
    if generator is None:
        del capabilities[103026]
    else:
        capabilities[103026] = generator
    infos, available = room(capabilities, gateway, family)

    assert set(infos.HVACModes.values()) == {
        HVACMode.OFF,
        HVACMode.AUTO,
        HVACMode.COOL,
        HVACMode.HEAT,
        HVACMode.FAN_ONLY,
        HVACMode.DRY,
    }
    climate = entity(infos, available, 7, "3")
    assert all(key in climate for key in AC_ONLY)
    for capabilityId in (177, 100802, 100804):
        assert entity(infos, available, capabilityId).get("name")


@pytest.mark.parametrize(
    ("generator", "what"),
    [
        ("16", "electric panel heater"),
        ("32", "electric towel dryer"),
        ("64", "electric floor heater"),
        ("128", "electric panel heater, I2G"),
        ("256", "electric towel dryer, I2G"),
        ("48", "panel heater and towel dryer"),
    ],
)
def test_every_electric_heater_reads_the_same(generator, what):
    """Only 128 has been seen on a room. The other four are the members the
    catalogue lists beside it, and a room in front of any of them has no
    compressor either.
    """
    infos, _ = room(RADIATOR | {103026: generator})

    assert infos.HVACModes == {0: HVACMode.OFF, 4: HVACMode.HEAT}, what


@pytest.mark.parametrize("generator", ["2", "4", "6"])
def test_a_room_in_front_of_a_heat_pump_or_a_boiler_is_left_alone(generator):
    """Air-to-water heat pumps and boilers are not air conditioners either, but
    no capture shows a room behind one reporting 103026, and what such a room
    offers is unknown. It keeps today's answer.
    """
    infos, _ = room(RADIATOR | {103026: generator})

    assert HVACMode.COOL in infos.HVACModes.values()
