"""The device triggers : what a device is offered, and what that then watches.

These are the two halves that can be wrong independently. Offering a trigger a
device cannot produce puts a line in the automation editor that never fires,
and there is nothing to see afterwards -- no error, no log, just an automation
that does not run. Attaching it to the wrong entity or the wrong attribute is
the same failure one step later.

So the offers are pinned against a device that reports one program and not the
other, and the state trigger config each one builds is pinned field by field.
`state_trigger` is faked rather than driven : what this module decides is the
config it hands over, and Home Assistant's own tests cover what the state
trigger does with it.
"""

import asyncio
import json
from types import SimpleNamespace

from _harness import TRANSLATIONS
import pytest

from custom_components.cozytouch import const, device_trigger
from homeassistant.components.device_automation.exceptions import (
    InvalidDeviceAutomationConfig,
)

DEVICE_ID = "device"
ENTRY_ID = "01JX8Z4QK2N7WQ3M5V6Y8T9ABC"

HEATING = range(196, 203)
COOLING = range(203, 210)

# A registry id is a uuid4 hex, and the trigger schema validates it as one, so
# a readable stand-in like "registry_climate" would pass every assertion here
# and be refused the moment an automation was saved.
CLIMATE_REGISTRY_ID = f"{0xC11:032x}"


def registry_id(seed):
    """A registry id shaped the way the registry actually writes them."""
    return f"{seed:032x}"


def sensor(capabilityId):
    """A registry entry shaped like one of our capability sensors."""
    return SimpleNamespace(
        domain="sensor",
        unique_id=f"cozytouch_{ENTRY_ID}_{capabilityId}",
        entity_id=f"sensor.prog_{capabilityId}",
        id=registry_id(capabilityId),
    )


def climate(entity_id="climate.salon"):
    """A registry entry for the climate entity."""
    return SimpleNamespace(
        domain="climate",
        unique_id=f"cozytouch_{ENTRY_ID}_climate_7",
        entity_id=entity_id,
        id=CLIMATE_REGISTRY_ID,
    )


def make_hass(monkeypatch, entries, presets=None):
    """A stand-in exposing only what async_get_triggers reads.

    The entity registry is patched on our own module rather than seeded into
    hass.data, the way the service tests do it : er.async_get caches a
    singleton on the hass object, so a fake cannot be reached through the real
    lookup at all.
    """
    monkeypatch.setattr(
        device_trigger,
        "er",
        SimpleNamespace(
            async_get=lambda hass: None,
            async_entries_for_device=lambda registry, device_id: list(entries),
        ),
    )

    states = {}
    if presets is not None:
        states["climate.salon"] = SimpleNamespace(
            attributes={"preset_modes": list(presets)}
        )

    return SimpleNamespace(states=SimpleNamespace(get=states.get))


def offered(hass):
    """The trigger types this device is offered, in the order they come."""
    triggers = asyncio.run(device_trigger.async_get_triggers(hass, DEVICE_ID))
    return [trigger["type"] for trigger in triggers]


def attached(monkeypatch, config, entries=()):
    """The state trigger config async_attach_trigger hands over."""
    captured = {}

    async def async_validate_trigger_config(hass, state_config):
        captured.update(state_config)
        return state_config

    async def async_attach_trigger(hass, state_config, action, trigger_info, **kwargs):
        return None

    monkeypatch.setattr(
        device_trigger,
        "state_trigger",
        SimpleNamespace(
            CONF_TO="to",
            CONF_NOT_TO="not_to",
            CONF_NOT_FROM="not_from",
            async_validate_trigger_config=async_validate_trigger_config,
            async_attach_trigger=async_attach_trigger,
        ),
    )

    hass = make_hass(monkeypatch, entries)
    asyncio.run(device_trigger.async_attach_trigger(hass, config, None, None))
    return captured


# --- what a device is offered -------------------------------------------


def test_a_device_that_stores_a_heating_program_is_offered_it(monkeypatch):
    """The seven heating days are 196 to 202, and the sensors carry the id."""
    hass = make_hass(monkeypatch, [sensor(capabilityId) for capabilityId in HEATING])

    assert offered(hass) == [
        "heating_schedule_changed"
    ]


def test_the_cooling_program_is_a_trigger_of_its_own(monkeypatch):
    """203 is the second block : on an air conditioner it is cooling.

    Offered separately because a device can report one block and not the
    other, and "the program changed" is not a useful thing to be woken for
    when it cannot say which program.
    """
    hass = make_hass(monkeypatch, [sensor(capabilityId) for capabilityId in COOLING])

    assert offered(hass) == [
        "cooling_schedule_changed"
    ]


def test_one_day_is_enough_for_the_program_to_be_offered(monkeypatch):
    """A device reporting part of a block still has a program to watch."""
    hass = make_hass(monkeypatch, [sensor(199)])

    assert offered(hass) == [
        "heating_schedule_changed"
    ]


def test_a_device_with_no_program_is_offered_nothing(monkeypatch):
    """Most of the account is water heaters and gateways, which have none."""
    hass = make_hass(monkeypatch, [sensor(117), sensor(271)])

    assert offered(hass) == []


def test_the_away_mode_sensors_are_not_read_as_a_program(monkeypatch):
    """They are the one pair keyed `{entry_id}_0` and `_1` rather than by
    capability, so the id at the tail of the unique id is 0 and 1 -- and both
    have to fall outside every block rather than be special-cased.
    """
    entries = [
        SimpleNamespace(
            domain="sensor",
            unique_id=f"{ENTRY_ID}_{index}",
            entity_id=f"sensor.away_{index}",
            id=registry_id(index),
        )
        for index in (0, 1)
    ]

    hass = make_hass(monkeypatch, entries)

    assert offered(hass) == []


def test_a_climate_entity_is_offered_the_presets_it_reports(monkeypatch):
    """A device with no override capability has prog and basic and no third."""
    hass = make_hass(monkeypatch, [climate()], presets=["none", "prog", "basic"])

    assert offered(hass) == [
        "schedule_resumed",
        "schedule_stopped",
    ]


def test_a_climate_entity_with_no_preset_at_all_is_offered_nothing(monkeypatch):
    """Presets are wired from capability 184, which most models never report."""
    hass = make_hass(monkeypatch, [climate()], presets=["none", "eco", "boost"])

    assert offered(hass) == []


def test_a_climate_entity_that_has_no_state_yet_is_offered_nothing(monkeypatch):
    """Which presets exist is on the entity, so before it has written a state
    there is nothing to read and guessing would offer triggers that never
    fire.
    """
    hass = make_hass(monkeypatch, [climate()], presets=None)

    assert offered(hass) == []


def test_the_preset_triggers_name_an_entity_and_the_program_ones_do_not(
    monkeypatch,
):
    """A program is seven sensors and no entity stands for it, so that trigger
    is keyed by device alone; a preset lives on one entity, and a device can
    hold more than one climate entity.
    """
    hass = make_hass(
        monkeypatch, [sensor(196), climate()], presets=["prog", "override"]
    )

    triggers = asyncio.run(device_trigger.async_get_triggers(hass, DEVICE_ID))
    by_type = {trigger["type"]: trigger for trigger in triggers}

    assert by_type["schedule_resumed"]["entity_id"] == CLIMATE_REGISTRY_ID
    assert "entity_id" not in by_type["heating_schedule_changed"]


def test_every_offer_passes_the_schema_that_validates_it(monkeypatch):
    """The editor stores what async_get_triggers returned : anything it hands
    back that TRIGGER_SCHEMA then rejects is an automation that cannot be
    saved.
    """
    hass = make_hass(
        monkeypatch, [sensor(196), sensor(203), climate()], presets=["prog", "override"]
    )

    for trigger in asyncio.run(device_trigger.async_get_triggers(hass, DEVICE_ID)):
        assert device_trigger.TRIGGER_SCHEMA(trigger)


# --- what a trigger then watches ----------------------------------------


def test_a_program_trigger_watches_the_seven_day_sensors(monkeypatch):
    """By registry id, not entity id : renaming an entity changes the second."""
    config = {
        "platform": "device",
        "domain": "cozytouch",
        "device_id": DEVICE_ID,
        "type": "heating_schedule_changed",
    }

    captured = attached(
        monkeypatch, config, [sensor(capabilityId) for capabilityId in HEATING]
    )

    assert captured["entity_id"] == [
        registry_id(capabilityId) for capabilityId in HEATING
    ]


def test_a_program_trigger_ignores_the_trip_through_unavailable(monkeypatch):
    """A device that dropped off the cloud and came back has not been
    reprogrammed. Naming both ends also stops the state trigger firing on an
    attribute change, which is what a rename is.
    """
    config = {
        "platform": "device",
        "domain": "cozytouch",
        "device_id": DEVICE_ID,
        "type": "cooling_schedule_changed",
    }

    captured = attached(monkeypatch, config, [sensor(203)])

    assert captured["not_from"] == ["unavailable", "unknown"]
    assert captured["not_to"] == ["unavailable", "unknown"]


def test_a_device_that_lost_its_program_is_refused_rather_than_left_silent(
    monkeypatch,
):
    """Reachable from a YAML automation naming a device that never had the
    program : without this the trigger attaches to no entity and never fires,
    which reads as a broken automation with nothing to look at.
    """
    config = {
        "platform": "device",
        "domain": "cozytouch",
        "device_id": DEVICE_ID,
        "type": "heating_schedule_changed",
    }

    with pytest.raises(InvalidDeviceAutomationConfig, match="heating"):
        attached(monkeypatch, config, [sensor(117)])


@pytest.mark.parametrize(
    ("trigger_type", "preset"),
    [
        ("schedule_resumed", "prog"),
        ("schedule_overridden", "override"),
        ("schedule_stopped", "basic"),
    ],
)
def test_a_preset_trigger_watches_the_attribute_and_not_the_state(
    monkeypatch, trigger_type, preset
):
    """The state of a climate entity is its HVAC mode, so a state trigger here
    would fire on heat/cool and never on the preset.
    """
    config = {
        "platform": "device",
        "domain": "cozytouch",
        "device_id": DEVICE_ID,
        "entity_id": CLIMATE_REGISTRY_ID,
        "type": trigger_type,
    }

    captured = attached(monkeypatch, config)

    assert captured["attribute"] == "preset_mode"
    assert captured["to"] == preset
    assert captured["entity_id"] == CLIMATE_REGISTRY_ID


def test_a_preset_trigger_carries_for_when_it_was_given_one(monkeypatch):
    """"Overridden for two hours" is the case `for` exists for."""
    config = {
        "platform": "device",
        "domain": "cozytouch",
        "device_id": DEVICE_ID,
        "entity_id": CLIMATE_REGISTRY_ID,
        "type": "schedule_overridden",
        "for": {"hours": 2},
    }

    assert attached(monkeypatch, config)["for"] == {"hours": 2}


def test_for_is_offered_on_the_presets_and_not_on_the_programs():
    """A program that changed does not change back, so waiting on it is a
    field that can only be filled in wrong.
    """
    preset = asyncio.run(
        device_trigger.async_get_trigger_capabilities(
            None, {"type": "schedule_overridden"}
        )
    )
    program = asyncio.run(
        device_trigger.async_get_trigger_capabilities(
            None, {"type": "heating_schedule_changed"}
        )
    )

    assert "for" in str(preset["extra_fields"].schema)
    assert program == {}


# --- staying in step with the rest --------------------------------------


def test_the_program_triggers_follow_the_programs_the_services_know():
    """A program the services cannot read back is not one to be woken for :
    the trigger would fire and get_schedule would then refuse the device.
    """
    assert set(device_trigger.SCHEDULE_TRIGGER_TYPES.values()) == set(
        const.WRITABLE_PROGRAM_BLOCKS
    )


def test_the_preset_triggers_name_presets_the_climate_entity_can_report():
    """These three are strings, and nothing but this test ties them to the
    ones climate.py assigns.
    """
    from custom_components.cozytouch.climate import (
        PRESET_BASIC,
        PRESET_OVERRIDE,
        PRESET_PROG,
    )

    assert set(device_trigger.PRESET_TRIGGER_TYPES.values()) == {
        PRESET_PROG,
        PRESET_OVERRIDE,
        PRESET_BASIC,
    }


@pytest.mark.parametrize("path", TRANSLATIONS)
def test_every_trigger_type_has_a_name_in_every_language(path):
    """An unnamed trigger shows its raw id in the automation editor, and
    hassfest does not check a custom integration's translations at all.
    """
    with open(path, encoding="utf-8") as handle:
        content = json.load(handle)

    assert set(content["device_automation"]["trigger_type"]) == set(
        device_trigger.SCHEDULE_TRIGGER_TYPES
    ) | set(device_trigger.PRESET_TRIGGER_TYPES)
