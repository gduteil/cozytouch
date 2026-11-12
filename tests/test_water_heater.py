"""A tank as a water heater entity.

The tanks had a select for the mode, a number for the setpoint and a sensor
per probe, and nothing Home Assistant draws as a water heater. The entity
here is built from the same ids and writes through the same two capabilities
the select and the number write, so it adds no write of its own.

The readings are a LINEO CONNECTE VM 120L 2400W's (model 1959), from a
diagnostics dump of 2026-11-12, beside the app showing 55 °C and Manuel, with
PROG greyed out : 105011 = 7941 declares manual and auto, not prog.
"""

import asyncio
from types import SimpleNamespace

from custom_components.cozytouch.capability import get_capability_infos
from custom_components.cozytouch.model import get_model_infos
from custom_components.cozytouch.water_heater import (
    CozytouchWaterHeater,
    water_heater_for,
)

LINEO = 1959

READINGS = {
    87: "0",
    231: "55.0000000000000000000",
    252: "70.0000000000000000000",
    253: "50.0000000000000000000",
    264: "48.25",
    265: "56.35",
    105011: "7941",
}


def coordinator(modelId=LINEO, **overrides):
    values = {**READINGS, **overrides}
    written = []

    async def set_capability_value(capabilityId, value):
        written.append((capabilityId, value))

    async def async_request_refresh():
        return None

    modelInfos = get_model_infos(modelId, None, None)
    return SimpleNamespace(
        get_capability_value=lambda capabilityId, default="0": values.get(
            capabilityId, default
        ),
        get_model_infos=lambda: modelInfos,
        set_capability_value=set_capability_value,
        async_request_refresh=async_request_refresh,
        online=True,
        written=written,
        modelInfos=modelInfos,
    )


def build(hub, capabilityId=87):
    capability = get_capability_infos(
        hub.modelInfos,
        capabilityId,
        hub.get_capability_value(capabilityId),
        set(READINGS),
    )
    return water_heater_for(
        coordinator=hub,
        capability=capability,
        config_title="Ballon",
        config_uniq_id="sub-1",
    )


def updated(hub):
    entity = build(hub)
    entity.async_write_ha_state = lambda: None
    entity._handle_coordinator_update()
    return entity


def test_a_tank_gets_one_water_heater_beside_its_mode_select():
    assert isinstance(build(coordinator()), CozytouchWaterHeater)


def test_only_the_mode_capability_builds_it():
    assert build(coordinator(), capabilityId=165) == []


def test_the_ids_come_from_the_mode_row():
    """No id is written in water_heater.py: a tank wired differently needs a
    row, not code.
    """
    entity = build(coordinator())

    assert entity._capability.setpointCapabilityId == 231
    assert entity._capability.currentValueCapabilityId == 265


def test_prog_is_not_offered_to_a_tank_that_does_not_declare_it():
    """105011 = 7941 has no prog bit, and the app greys PROG out."""
    hub = coordinator()
    entity = updated(hub)

    asyncio.run(entity.async_set_operation_mode("prog"))

    assert "prog" not in entity.operation_list
    assert hub.written == []


def test_a_tank_without_a_setpoint_gets_none():
    """A tank that reports no 231 has nothing to set from the card."""
    hub = coordinator()
    hub.get_capability_value = lambda capabilityId, default="0": (
        default if capabilityId == 231 else READINGS.get(capabilityId, default)
    )
    assert build(hub) == []


def test_it_reads_the_tank_as_the_app_shows_it():
    entity = updated(coordinator())

    assert entity.target_temperature == 55.0
    assert entity.current_temperature == 56.35
    assert entity.current_operation == "manual"
    assert entity.operation_list == ["manual", "eco_plus"]
    assert (entity.min_temp, entity.max_temp) == (50.0, 70.0)


def test_a_setpoint_is_written_where_the_number_writes_it():
    hub = coordinator()
    entity = updated(hub)

    asyncio.run(entity.async_set_temperature(temperature=60))

    assert hub.written == [(231, "60.0")]


def test_a_setpoint_out_of_the_tanks_range_is_held_to_it():
    hub = coordinator()
    entity = updated(hub)

    asyncio.run(entity.async_set_temperature(temperature=80))

    assert hub.written == [(231, "70.0")]


def test_a_mode_is_written_where_the_select_writes_it():
    hub = coordinator()
    entity = updated(hub)

    asyncio.run(entity.async_set_operation_mode("eco_plus"))

    assert hub.written == [(87, "3")]


def test_a_mode_the_tank_does_not_have_writes_nothing():
    hub = coordinator()
    entity = updated(hub)

    asyncio.run(entity.async_set_operation_mode("vacation"))

    assert hub.written == []


def test_a_tanks_second_setpoint_slider_starts_off():
    """22 and 231 both read 55 on the Lineo ; the entity writes 231, and
    which one the app writes is #215's question. Existing installs keep 22.
    """
    hub = coordinator()
    capability = get_capability_infos(hub.modelInfos, 22, "55", set(READINGS) | {22})

    assert capability.enabled_by_default is False
