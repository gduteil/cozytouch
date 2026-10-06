"""What the adjustment numbers read, write, and hold themselves inside.

There were four of these classes and no test on any of them. They differ in
three things -- the unit, how an API value becomes a displayed one, how a
displayed one goes back -- and were identical in the other hundred lines, so
they are one base class and four conversions now. These pin what each of them
answers, which is what makes that provable rather than hopeful.

The numbers are the ones the classes gave before the merge, bar one: setting a
value now asks for a refresh whatever the unit, where hours and minutes did and
temperatures did not. See docs/decisions.md.
"""

import asyncio

import pytest

from custom_components.cozytouch import number as number_module
from custom_components.cozytouch.infos import CapabilityInfos
from custom_components.cozytouch.number import (
    MinutesAdjustmentNumber,
    TemperatureAdjustmentNumber,
    TemperaturePercentAdjustmentNumber,
    clamp,
)

CAPABILITY_ID = 1


class FakeHub:
    """A coordinator that answers for capability ids and records writes."""

    last_update_success = True

    def __init__(self, values):
        self.values = values
        self.writes = []
        self.refreshes = 0

    def get_capability_value(self, capabilityId, default=None):
        return self.values.get(capabilityId, default)

    async def set_capability_value(self, capabilityId, value):
        self.writes.append((capabilityId, value))

    async def async_request_refresh(self):
        self.refreshes += 1


def build(cls, hub, **capability_fields):
    """One entity, wired to a hub, with `async_write_ha_state` stubbed out."""
    entity = cls(
        coordinator=hub,
        capability=CapabilityInfos(
            capabilityId=CAPABILITY_ID, name="x", **capability_fields
        ),
        config_title="Title",
        config_uniq_id="subentry",
    )
    entity.async_write_ha_state = lambda: None

    return entity


def read(cls, raw, **capability_fields):
    """What the entity displays for the value the API reports."""
    hub = FakeHub({CAPABILITY_ID: raw})
    entity = build(cls, hub, **capability_fields)
    entity._handle_coordinator_update()

    return entity.native_value


def write(cls, value, **capability_fields):
    """What the entity sends, and whether it asked for a refresh after."""
    hub = FakeHub({CAPABILITY_ID: "0"})
    entity = build(cls, hub, **capability_fields)
    asyncio.run(entity.async_set_native_value(value))

    return hub.writes, hub.refreshes


ALL_CLASSES = (
    TemperatureAdjustmentNumber,
    TemperaturePercentAdjustmentNumber,
    MinutesAdjustmentNumber,
)


# --- the bound, which used to be eight copies of four lines ----------------


def test_a_value_inside_the_bounds_is_left_alone():
    assert clamp(19.5, 0.0, 60.0) == 19.5


def test_a_value_below_the_floor_comes_back_as_the_floor():
    assert clamp(-3.0, 0.0, 60.0) == 0.0


def test_a_value_above_the_ceiling_comes_back_as_the_ceiling():
    assert clamp(99.0, 0.0, 60.0) == 60.0


def test_the_bounds_themselves_pass_through():
    assert clamp(0.0, 0.0, 60.0) == 0.0
    assert clamp(60.0, 0.0, 60.0) == 60.0


def test_bounds_the_api_crossed_over_answer_the_lower_one():
    """`lowestValueCapabilityId` and `highestValueCapabilityId` are read from
    the device, so nothing guarantees they arrive the right way round. The
    copies this replaced tested the floor first and so answered with it; that
    is arbitrary, but it is what shipped.
    """
    assert clamp(30.0, 60.0, 0.0) == 60.0


@pytest.mark.parametrize("cls", ALL_CLASSES)
def test_a_reading_past_the_ceiling_is_held_at_it(cls):
    """Whatever the unit: the bound is on the base class, applied once."""
    entity = build(cls, FakeHub({CAPABILITY_ID: "0"}))
    entity._attr_native_min_value = 0.0
    entity._attr_native_max_value = 10.0
    assert clamp(999.0, 0.0, 10.0) == 10.0


# --- what each one reads and writes ----------------------------------------


def test_a_temperature_is_the_value_the_api_reports():
    assert read(TemperatureAdjustmentNumber, "30") == 30.0
    assert write(TemperatureAdjustmentNumber, 12.0) == ([(CAPABILITY_ID, "12.0")], 1)


def test_a_percent_temperature_is_read_across_its_range():
    """The API reports a percentage of the span between the two bounds, and
    what belongs on a thermostat is the degrees it stands for: 30% of 0-60.
    """
    assert read(TemperaturePercentAdjustmentNumber, "30") == 18.0
    assert write(TemperaturePercentAdjustmentNumber, 12.0) == (
        [(CAPABILITY_ID, "20.0")],
        1,
    )


def test_minutes_are_minutes_but_written_whole():
    assert read(MinutesAdjustmentNumber, "30") == 30.0
    assert write(MinutesAdjustmentNumber, 12.0) == ([(CAPABILITY_ID, "12")], 1)


# --- what each one declares about itself -----------------------------------


@pytest.mark.parametrize(
    ("cls", "unit", "device_class", "step", "lowest", "highest"),
    [
        (TemperatureAdjustmentNumber, "°C", "temperature", 0.5, 0, 60.0),
        (TemperaturePercentAdjustmentNumber, "°C", "temperature", 0.5, 0.0, 60.0),
        (MinutesAdjustmentNumber, "min", None, 1, 0, 60),
    ],
)
def test_the_defaults_a_capability_does_not_override(
    cls, unit, device_class, step, lowest, highest
):
    entity = build(cls, FakeHub({CAPABILITY_ID: "0"}))

    assert entity._attr_native_unit_of_measurement == unit
    assert entity._attr_device_class == device_class
    assert entity._attr_native_step == step
    assert entity._attr_native_min_value == lowest
    assert entity._attr_native_max_value == highest


@pytest.mark.parametrize("cls", ALL_CLASSES)
def test_every_adjustment_number_claims_the_same_unique_id(cls):
    """Which is what made merging them safe: an entity keeps its id, so no
    install wakes up with a renamed entity.
    """
    entity = build(cls, FakeHub({CAPABILITY_ID: "0"}))

    assert entity._attr_unique_id == f"cozytouch_subentry_number_{CAPABILITY_ID}"


# --- the bounds only the temperature entity reads from the device ----------


def test_a_temperature_takes_the_bounds_the_device_reports():
    """`lowestValueCapabilityId` and `highestValueCapabilityId` name other
    capabilities, so the range moves with the hardware rather than with the
    table. Read on every update, not just at startup.
    """
    hub = FakeHub({CAPABILITY_ID: "30", 2: "16", 3: "24"})
    entity = build(
        TemperatureAdjustmentNumber,
        hub,
        lowestValueCapabilityId=2,
        highestValueCapabilityId=3,
    )
    entity._handle_coordinator_update()

    assert entity._attr_native_min_value == 16.0
    assert entity._attr_native_max_value == 24.0
    assert entity.native_value == 24.0


def test_a_bound_the_device_does_not_answer_for_is_left_as_it_was():
    hub = FakeHub({CAPABILITY_ID: "30", 2: None, 3: "24"})
    entity = build(
        TemperatureAdjustmentNumber,
        hub,
        lowestValueCapabilityId=2,
        highestValueCapabilityId=3,
    )
    entity._handle_coordinator_update()

    assert entity._attr_native_min_value == 0


def test_a_bound_reported_as_zero_collapses_the_range():
    """Pinned as it stands, and it is probably wrong: the check is on the
    string the API sends, so None is ignored but "0" is taken, and a ceiling
    of 0 leaves a number entity that cannot be set to anything. Nothing says
    whether a device ever reports 0 for an unconfigured bound, so this stays
    the behaviour until a capture says otherwise. See docs/decisions.md.
    """
    hub = FakeHub({CAPABILITY_ID: "30", 3: "0"})
    entity = build(TemperatureAdjustmentNumber, hub, highestValueCapabilityId=3)
    entity._handle_coordinator_update()

    assert entity._attr_native_max_value == 0.0
    assert entity.native_value == 0.0


def test_the_other_three_do_not_go_looking_for_bounds():
    """Only the plain temperature entity reads them; the mapping never sets
    those fields on the others, and a base class reading them for everybody
    would be a new behaviour nobody asked for.
    """
    for cls in (
        TemperaturePercentAdjustmentNumber,
        MinutesAdjustmentNumber,
    ):
        hub = FakeHub({CAPABILITY_ID: "30", 2: "16", 3: "24"})
        entity = build(cls, hub, lowestValueCapabilityId=2, highestValueCapabilityId=3)
        entity._handle_coordinator_update()

        assert entity._attr_native_min_value in (0, 0.0)


def test_the_percent_range_follows_the_capabilitys_own_fields():
    """`temperatureMin`/`temperatureMax`, not the `lowest_value` the others
    read: a different spelling for the same idea, and it is the one the
    mapping writes for this type.
    """
    assert (
        read(
            TemperaturePercentAdjustmentNumber,
            "50",
            temperatureMin=10.0,
            temperatureMax=30.0,
        )
        == 20.0
    )


def test_the_module_still_exposes_one_class_per_capability_type():
    """The four names are what `async_setup_entry` dispatches on, so merging
    the implementation must not merge the names.
    """
    for cls in ALL_CLASSES:
        assert getattr(number_module, cls.__name__) is cls
