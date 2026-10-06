"""What a setpoint or preset change from Home Assistant writes, and when it reads back.

A setpoint typed while the room follows its programme has to leave the
programme first, so it is two writes : the override, then the setpoint. The
read-back comes once, after both. A read between them lands while the cloud
still holds the programme's setpoint, publishes it, and the debouncer holds
the second read back for its cooldown -- the dial jumps back to the old value
for about ten seconds before settling (Navizone room, 2026-10-03). The
entities are driven unbound against a stand-in, the way test_mode_writes.py
drives the fan and swing.
"""

import asyncio
from functools import partial
from types import SimpleNamespace

from custom_components.cozytouch.climate import (
    PRESET_BASIC,
    PRESET_OVERRIDE,
    PRESET_PROG,
    CozytouchClimate,
)
from custom_components.cozytouch.infos import CapabilityInfos
from homeassistant.components.climate import HVACMode

PROG = {
    "capabilityId": 7,
    "targetCapabilityId": 40,
    "targetCoolCapabilityId": 41,
    "progCapabilityId": 50,
    "progOverrideCapabilityId": 51,
    "progOverrideTimeCapabilityId": 52,
    "progOverrideTotalTimeCapabilityId": 53,
}


def climate(preset, hvac_mode=HVACMode.COOL):
    capability = CapabilityInfos()
    for key, value in PROG.items():
        capability[key] = value

    writes = []

    async def set_capability_value(capabilityId, value):
        writes.append((capabilityId, value))

    async def async_request_refresh():
        writes.append("refresh")

    fake = SimpleNamespace(
        _capability=capability,
        _attr_preset_mode=preset,
        _attr_hvac_mode=hvac_mode,
        coordinator=SimpleNamespace(
            set_capability_value=set_capability_value,
            async_request_refresh=async_request_refresh,
            get_capability_value=lambda capabilityId, default="0": "60",
        ),
    )
    fake._write_preset = partial(CozytouchClimate._write_preset, fake)
    fake.async_set_preset_mode = partial(
        CozytouchClimate.async_set_preset_mode, fake
    )
    return fake, writes


def run(coroutine):
    asyncio.run(coroutine)


def test_a_setpoint_under_the_programme_overrides_it_then_reads_back_once():
    fake, writes = climate(PRESET_PROG)

    run(CozytouchClimate.async_set_temperature(fake, temperature=23.0))

    assert writes == [(53, "60"), (51, "1"), (41, "23.0"), "refresh"]
    assert fake._attr_preset_mode == PRESET_OVERRIDE


def test_a_setpoint_already_overriding_writes_the_setpoint_alone():
    fake, writes = climate(PRESET_OVERRIDE)

    run(CozytouchClimate.async_set_temperature(fake, temperature=23.0))

    assert writes == [(41, "23.0"), "refresh"]


def test_a_heating_setpoint_goes_to_the_shared_target():
    fake, writes = climate(PRESET_BASIC, hvac_mode=HVACMode.HEAT)

    run(CozytouchClimate.async_set_temperature(fake, temperature=20.5))

    assert writes == [(40, "20.5"), "refresh"]


def test_choosing_the_override_preset_still_reads_back_on_its_own():
    fake, writes = climate(PRESET_PROG)

    run(CozytouchClimate.async_set_preset_mode(fake, PRESET_OVERRIDE))

    assert writes == [(53, "60"), (51, "1"), "refresh"]
    assert fake._attr_preset_mode == PRESET_OVERRIDE


def test_back_to_the_programme_clears_the_override():
    fake, writes = climate(PRESET_OVERRIDE)

    run(CozytouchClimate.async_set_preset_mode(fake, PRESET_PROG))

    assert writes == [(50, "1"), (52, "0"), (51, "0"), "refresh"]
    assert fake._attr_preset_mode == PRESET_PROG
