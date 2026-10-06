"""Air circulation as a fan entity.

The hardware does one thing -- blow air, at a speed -- and the integration
exposed it as a switch and a dropdown sitting next to each other. Home
Assistant has a fan, with a card, a voice vocabulary and a percentage.

The cases here are about that percentage, since it is the whole translation
layer: the API speaks `1`, `2`, `3` and Home Assistant speaks 0 to 100, and
everything that can go wrong goes wrong in between. A fan that is off reading
its last speed rather than zero is the classic one -- the slider then
disagrees with the switch beside it.

One case pins a refusal: a model that names no speeds still gets a fan, and it
runs or does not rather than getting an invented three-speed scale.
"""

import asyncio
from types import SimpleNamespace

from custom_components.cozytouch.capability import get_capability_infos
from custom_components.cozytouch.fan import CozytouchFan
from custom_components.cozytouch.infos import CapabilityType
from custom_components.cozytouch.model import get_model_infos

# The air circulation of a room air conditioner, which is the one device type
# that reports it. The capability is read from the mapping rather than
# restated, so a row that stops describing a fan fails these.
AIR_CIRCULATION = 102024
AIR_CIRCULATION_SPEED = 102004
AC_MODEL = 557

SPEEDS = {1: "low", 2: "medium", 3: "high"}


def capability_infos(speeds):
    """What the mapping makes of 102024 on a model naming these speeds."""
    modelInfos = get_model_infos(AC_MODEL, None, None)
    modelInfos.AirCirculationSpeeds = dict(speeds)

    return modelInfos, get_capability_infos(
        modelInfos, AIR_CIRCULATION, "1", {AIR_CIRCULATION, AIR_CIRCULATION_SPEED}
    )


def make_fan(on=True, speed="2", speeds=SPEEDS):
    """A fan over a device reporting the given switch and speed."""
    written = []
    values = {AIR_CIRCULATION: "1" if on else "0", AIR_CIRCULATION_SPEED: speed}

    async def set_capability_value(capabilityId, value):
        written.append((capabilityId, value))
        values[capabilityId] = value

    async def async_request_refresh():
        return None

    modelInfos, capability = capability_infos(speeds)

    coordinator = SimpleNamespace(
        get_capability_value=lambda capabilityId, default="0": values.get(
            capabilityId, default
        ),
        get_model_infos=lambda: modelInfos,
        set_capability_value=set_capability_value,
        async_request_refresh=async_request_refresh,
        async_write_ha_state=lambda: None,
    )

    fan = CozytouchFan(
        coordinator=coordinator,
        capability=capability,
        config_title="Chambre",
        config_uniq_id="sub-1",
    )
    fan.written = written

    return fan


def test_the_mapping_is_what_says_this_capability_is_a_fan():
    """The ids live on the row, not in fan.py: the platform builds whatever
    the table hands it, so a second fan needs a row and no code.
    """
    _, capability = capability_infos(SPEEDS)

    assert capability.type is CapabilityType.FAN
    assert capability.speedCapabilityId == AIR_CIRCULATION_SPEED


def test_the_middle_of_three_speeds_is_two_thirds():
    """1/2/3 against 0-100: the API's middle speed is 66%, not 50%. Getting
    this wrong moves every speed by one notch and nothing raises.
    """
    assert make_fan(speed="2").percentage == 66


def test_the_speeds_run_from_a_third_to_everything():
    assert make_fan(speed="1").percentage == 33
    assert make_fan(speed="3").percentage == 100


def test_a_fan_that_is_off_reads_zero_rather_than_its_last_speed():
    assert make_fan(on=False, speed="3").percentage == 0


def test_a_speed_the_model_does_not_name_reads_as_unknown():
    """Not as zero, which would say "stopped" about a fan that is running."""
    assert make_fan(speed="7").percentage is None


def test_setting_a_percentage_writes_the_speed_the_api_speaks():
    fan = make_fan(on=True, speed="1")
    asyncio.run(fan.async_set_percentage(100))

    assert fan.written == [(AIR_CIRCULATION_SPEED, "3")]


def test_a_speed_asked_of_a_stopped_fan_starts_it():
    """Both writes, in that order: a speed set on a stopped fan that stays
    stopped is the kind of silence a dashboard never explains.
    """
    fan = make_fan(on=False, speed="1")
    asyncio.run(fan.async_set_percentage(66))

    assert fan.written == [(AIR_CIRCULATION_SPEED, "2"), (AIR_CIRCULATION, "1")]


def test_asking_for_no_speed_at_all_stops_the_fan():
    fan = make_fan(on=True)
    asyncio.run(fan.async_set_percentage(0))

    assert fan.written == [(AIR_CIRCULATION, "0")]


def test_turning_on_without_a_speed_leaves_the_speed_alone():
    fan = make_fan(on=False, speed="2")
    asyncio.run(fan.async_turn_on())

    assert fan.written == [(AIR_CIRCULATION, "1")]


def test_a_model_naming_no_speeds_still_runs_or_does_not():
    fan = make_fan(on=True, speeds={})

    assert fan.percentage == 100
    assert fan.speed_count == 1


def test_the_state_follows_the_switch_the_app_writes():
    assert make_fan(on=True).is_on is True
    assert make_fan(on=False).is_on is False
