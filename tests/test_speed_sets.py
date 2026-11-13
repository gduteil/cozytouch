"""The fan and air-circulation speeds come from the set the device declares.

100800 declares the climate's fan speeds and 350 the air circulation's, each
as one value naming a whole set (`SPEED_SETS`). The tables in `model.py` stay
the vocabulary -- which value writes which speed -- and the device picks from
them ; a device reporting no set, or one outside 0-4, keeps the table whole.

Every capture that reports them reads 2 on 100800 and 0 on 350, which is the
tables exactly, so the other values here are the vendor's catalogue and the
Android app's, not a device anybody has seen (issue #208). The HUB Navizone
rooms report 350 but neither 100800 nor 100801 : no fan mode there at all.

Air circulation offers only low, medium and high : a set naming auto does not
add it as a choice until a capture shows one. What 102004 *reads* is wider --
quiet (4) and auto (5) -- so a unit running either shows it rather than
unknown.
"""

from types import SimpleNamespace

import pytest

from custom_components.cozytouch.capability import get_capability_infos
from custom_components.cozytouch.fan import CozytouchFan
from custom_components.cozytouch.model import get_device_model_infos
from custom_components.cozytouch.select import CozytouchSelect
from homeassistant.components.fan import FanEntityFeature

AIR_CIRCULATION = 102024
AIR_CIRCULATION_SPEED = 102004

# What an air conditioner's room reports on the ids these read, as the rooms
# behind a CozyBox or a HUB Cozytouch report them. A Navizone room reports
# the same without 100800 and 100801.
ROOM = {
    7: "3",
    100022: "411",
    166: "411",
    100800: "2",
    100801: "1",
    350: "0",
    AIR_CIRCULATION: "1",
    AIR_CIRCULATION_SPEED: "1",
}


def room(changes=None):
    """A room reporting ROOM with these changes, None removing an id."""
    capabilities = {**ROOM}
    for capabilityId, value in (changes or {}).items():
        if value is None:
            capabilities.pop(capabilityId)
        else:
            capabilities[capabilityId] = value

    box = {
        "deviceId": 2,
        "modelId": 1758,
        "productId": 63,
        "modelFamily": "Connectivity_Box",
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
    return get_device_model_infos([box, slot], slot, "Salon"), capabilities


def coordinator(modelInfos, values):
    return SimpleNamespace(
        get_capability_value=lambda capabilityId, default="0": values.get(
            capabilityId, default
        ),
        get_model_infos=lambda: modelInfos,
    )


def speed_select(changes=None):
    modelInfos, values = room(changes)
    capability = get_capability_infos(
        modelInfos, AIR_CIRCULATION_SPEED, values[AIR_CIRCULATION_SPEED], set(values)
    )
    return CozytouchSelect(
        coordinator=coordinator(modelInfos, values),
        capability=capability,
        config_title="Salon",
        config_uniq_id="sub-1",
    )


def fan(changes=None):
    modelInfos, values = room(changes)
    capability = get_capability_infos(
        modelInfos, AIR_CIRCULATION, values[AIR_CIRCULATION], set(values)
    )
    return CozytouchFan(
        coordinator=coordinator(modelInfos, values),
        capability=capability,
        config_title="Salon",
        config_uniq_id="sub-1",
    )


def test_the_captured_sets_are_the_tables():
    """2 and 0, the only values ever captured : nothing moves for them."""
    modelInfos, _ = room()

    assert modelInfos.fanModes == {1: "low", 2: "medium", 3: "high", 5: "auto"}
    assert modelInfos.AirCirculationSpeeds == {1: "low", 2: "medium", 3: "high"}


@pytest.mark.parametrize(
    ("speedSet", "fanModes"),
    [
        ("0", {1: "low", 2: "medium", 3: "high"}),
        ("1", {1: "low", 3: "high"}),
        ("2", {1: "low", 2: "medium", 3: "high", 5: "auto"}),
        ("3", {1: "low", 3: "high", 5: "auto"}),
        ("4", {5: "auto"}),
    ],
)
def test_the_fan_modes_are_the_set_100800_declares(speedSet, fanModes):
    modelInfos, _ = room({100800: speedSet})

    assert modelInfos.fanModes == fanModes


@pytest.mark.parametrize("speedSet", [None, "7", "", "auto"])
def test_without_a_set_it_knows_the_fan_modes_stay_whole(speedSet):
    """The app falls back to every speed for an unknown value ; so does this."""
    modelInfos, _ = room({100800: speedSet})

    assert modelInfos.fanModes == {1: "low", 2: "medium", 3: "high", 5: "auto"}


def test_a_navizone_room_has_no_fan_mode_to_narrow():
    """350 without 100800 or 100801, as the HUB Navizone's rooms report."""
    modelInfos, values = room({100800: None, 100801: None})
    capability = get_capability_infos(modelInfos, 7, values[7], set(values))

    assert "fanModeCapabilityId" not in capability
    assert modelInfos.AirCirculationSpeeds == {1: "low", 2: "medium", 3: "high"}


def test_the_climate_still_drives_the_fan_speed_on_a_narrower_set():
    modelInfos, values = room({100800: "1"})
    capability = get_capability_infos(modelInfos, 7, values[7], set(values))

    assert capability.fanModeCapabilityId == 100801


@pytest.mark.parametrize(
    ("speedSet", "speeds"),
    [
        ("0", {1: "low", 2: "medium", 3: "high"}),
        ("1", {1: "low", 3: "high"}),
        ("2", {1: "low", 2: "medium", 3: "high"}),
        ("3", {1: "low", 3: "high"}),
    ],
)
def test_the_air_circulation_speeds_are_the_set_350_declares(speedSet, speeds):
    """Auto in the set is not offered yet : see the module docstring."""
    modelInfos, _ = room({350: speedSet})

    assert modelInfos.AirCirculationSpeeds == speeds


@pytest.mark.parametrize("speedSet", [None, "7"])
def test_without_a_set_it_knows_the_air_circulation_speeds_stay_whole(speedSet):
    modelInfos, _ = room({350: speedSet})

    assert modelInfos.AirCirculationSpeeds == {1: "low", 2: "medium", 3: "high"}


def test_a_unit_declaring_two_speeds_gets_a_two_step_fan():
    entity = fan({350: "1", 102004: "3"})

    assert entity.speed_count == 2
    assert entity.percentage == 100


def test_a_unit_declaring_auto_alone_gets_a_fan_that_runs_or_does_not():
    modelInfos, _ = room({350: "4"})
    entity = fan({350: "4"})

    assert "AirCirculationSpeeds" not in modelInfos
    assert FanEntityFeature.SET_SPEED not in entity.supported_features
    assert entity.percentage == 100


def test_the_speed_select_offers_the_declared_set():
    assert speed_select({350: "1"}).options == ["low", "high"]


@pytest.mark.parametrize(("value", "option"), [("4", "quiet"), ("5", "auto")])
def test_a_speed_the_unit_runs_but_does_not_offer_reads_as_itself(value, option):
    """Home Assistant shows no option it does not list, hence the extra one."""
    entity = speed_select({102004: value})
    entity.get_value()

    assert entity.current_option == option
    assert entity.options == ["low", "medium", "high", option]


def test_the_extra_option_leaves_with_the_speed():
    modelInfos, values = room({102004: "4"})
    entity = speed_select({102004: "4"})
    entity.get_value()
    entity.coordinator = coordinator(modelInfos, {**values, AIR_CIRCULATION_SPEED: "2"})
    entity.get_value()

    assert entity.current_option == "medium"
    assert entity.options == ["low", "medium", "high"]


def test_a_value_nothing_names_still_reads_unknown():
    entity = speed_select({102004: "9"})
    entity.get_value()

    assert entity.current_option is None
    assert entity.options == ["low", "medium", "high"]
