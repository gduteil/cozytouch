"""Device triggers for the Atlantic Cozytouch integration.

Two gaps Home Assistant's own device triggers leave : the weekly program, which
no entity groups, and the climate preset, which `climate.device_trigger` does
not offer. Nothing else, and no conditions or actions. See docs/decisions.md.
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.components.climate.const import ATTR_PRESET_MODE, ATTR_PRESET_MODES
from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.device_automation.exceptions import (
    InvalidDeviceAutomationConfig,
)
from homeassistant.components.homeassistant.triggers import state as state_trigger
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import (
    CONF_ATTRIBUTE,
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_ENTITY_ID,
    CONF_FOR,
    CONF_PLATFORM,
    CONF_TYPE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .climate import PRESET_BASIC, PRESET_OVERRIDE, PRESET_PROG
from .const import DOMAIN, WRITABLE_PROGRAM_BLOCKS, program_days

# One per program the schedule services know, so the two stay in step.
SCHEDULE_TRIGGER_TYPES = {
    f"{program}_schedule_changed": program for program in WRITABLE_PROGRAM_BLOCKS
}

# What the device is doing about its own program : following it, overriding
# it, or ignoring it. capability.py wires all three from 184 and 157.
PRESET_TRIGGER_TYPES = {
    "schedule_resumed": PRESET_PROG,
    "schedule_overridden": PRESET_OVERRIDE,
    "schedule_stopped": PRESET_BASIC,
}

# Unreachable is not reprogrammed, and ruling both ends out is also what keeps
# this a state-value trigger. See docs/decisions.md.
NOT_A_PROGRAM = [STATE_UNAVAILABLE, STATE_UNKNOWN]

_SCHEDULE_TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        # No entity_id : a program is seven sensors, and which seven is a
        # question about the device. See docs/decisions.md.
        vol.Required(CONF_TYPE): vol.In(SCHEDULE_TRIGGER_TYPES),
    }
)

_PRESET_TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_ENTITY_ID): cv.entity_id_or_uuid,
        vol.Required(CONF_TYPE): vol.In(PRESET_TRIGGER_TYPES),
        vol.Optional(CONF_FOR): cv.positive_time_period_dict,
    }
)

TRIGGER_SCHEMA = vol.Any(_SCHEDULE_TRIGGER_SCHEMA, _PRESET_TRIGGER_SCHEMA)


def _capability_id(unique_id: str | None) -> int | None:
    """The capability id a sensor's unique id ends with.

    See docs/decisions.md.
    """
    if not unique_id:
        return None

    try:
        return int(unique_id.rpartition("_")[2])
    except ValueError:
        return None


def _schedule_entity_ids(
    hass: HomeAssistant, device_id: str, program: str
) -> list[str]:
    """The registry ids of the seven day sensors of one program.

    Registry ids, so an automation survives a rename.
    """
    # Every run any firmware stores it in : a device holds exactly one of
    # them, so the union matches the sensors it actually has.
    block = program_days(program)

    registry = er.async_get(hass)
    return [
        entry.id
        for entry in er.async_entries_for_device(registry, device_id)
        if entry.domain == SENSOR_DOMAIN and _capability_id(entry.unique_id) in block
    ]


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, str]]:
    """List the triggers this device actually has.

    Only the ones the device reports what to read for. See docs/decisions.md.
    """
    registry = er.async_get(hass)
    base_trigger = {
        CONF_PLATFORM: "device",
        CONF_DEVICE_ID: device_id,
        CONF_DOMAIN: DOMAIN,
    }

    triggers: list[dict[str, str]] = []
    capabilityIds: set[int] = set()

    for entry in er.async_entries_for_device(registry, device_id):
        if entry.domain == SENSOR_DOMAIN:
            capabilityId = _capability_id(entry.unique_id)
            if capabilityId is not None:
                capabilityIds.add(capabilityId)
            continue

        if entry.domain != CLIMATE_DOMAIN:
            continue

        # On the entity, not in the registry. See docs/decisions.md.
        state = hass.states.get(entry.entity_id)
        presets = state.attributes.get(ATTR_PRESET_MODES) or () if state else ()

        triggers += [
            {**base_trigger, CONF_ENTITY_ID: entry.id, CONF_TYPE: trigger_type}
            for trigger_type, preset in PRESET_TRIGGER_TYPES.items()
            if preset in presets
        ]

    triggers += [
        {**base_trigger, CONF_TYPE: trigger_type}
        for trigger_type, program in SCHEDULE_TRIGGER_TYPES.items()
        if not capabilityIds.isdisjoint(program_days(program))
    ]

    return triggers


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a trigger, as a state trigger on the entities behind it."""
    trigger_type = config[CONF_TYPE]

    if trigger_type in PRESET_TRIGGER_TYPES:
        state_config = {
            CONF_PLATFORM: "state",
            CONF_ENTITY_ID: config[CONF_ENTITY_ID],
            # On the attribute, not the state, which is the HVAC mode.
            CONF_ATTRIBUTE: ATTR_PRESET_MODE,
            state_trigger.CONF_TO: PRESET_TRIGGER_TYPES[trigger_type],
        }

        if CONF_FOR in config:
            state_config[CONF_FOR] = config[CONF_FOR]
    else:
        entity_ids = _schedule_entity_ids(
            hass, config[CONF_DEVICE_ID], SCHEDULE_TRIGGER_TYPES[trigger_type]
        )
        if not entity_ids:
            # Reachable from a YAML automation naming a device that never had
            # the program, and from one whose device has been replaced since.
            raise InvalidDeviceAutomationConfig(
                f"Device {config[CONF_DEVICE_ID]} has no "
                f"{SCHEDULE_TRIGGER_TYPES[trigger_type]} program"
            )

        state_config = {
            CONF_PLATFORM: "state",
            CONF_ENTITY_ID: entity_ids,
            state_trigger.CONF_NOT_FROM: NOT_A_PROGRAM,
            state_trigger.CONF_NOT_TO: NOT_A_PROGRAM,
        }

    state_config = await state_trigger.async_validate_trigger_config(hass, state_config)
    return await state_trigger.async_attach_trigger(
        hass, state_config, action, trigger_info, platform_type="device"
    )


async def async_get_trigger_capabilities(
    hass: HomeAssistant, config: ConfigType
) -> dict[str, vol.Schema]:
    """Offer `for` on the preset triggers, and nothing on the others.

    A program that changed does not change back. See docs/decisions.md.
    """
    if config[CONF_TYPE] not in PRESET_TRIGGER_TYPES:
        return {}

    return {
        "extra_fields": vol.Schema(
            {vol.Optional(CONF_FOR): cv.positive_time_period_dict}
        )
    }
