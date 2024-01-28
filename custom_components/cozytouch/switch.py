"""Switches for Atlantic Cozytouch integration."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .hub import Hub

_LOGGER = logging.getLogger(__name__)


# config flow setup
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entry."""
    # Retrieve the hub object
    try:
        hub = hass.data[DOMAIN][config_entry.entry_id]
    except KeyError:
        _LOGGER.error(
            "%s: can not init binaries sensors: failed to get the hub object",
            config_entry.title,
        )
        return

    # Init switches
    switches = []
    capabilities = hub.get_capabilities_for_device(config_entry.data["deviceId"])
    for capability in capabilities:
        if capability["type"] == "switch":
            value_off = "0"
            if "value_off" in capability:
                value_off = capability["value_off"]

            value_on = "1"
            if "value_on" in capability:
                value_on = capability["value_on"]

            switches.append(
                RegularSwitch(
                    deviceId=capability["deviceId"],
                    capabilityId=capability["capabilityId"],
                    name=capability["name"],
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    hub=hub,
                    value_off=value_off,
                    value_on=value_on,
                )
            )

    # Add the entities to HA
    if len(switches) > 0:
        async_add_entities(switches, True)


class RegularSwitch(SwitchEntity):
    """Common class for switches."""

    _attr_has_entity_name = True
    _attr_should_poll = True

    def __init__(
        self,
        deviceId: int,
        capabilityId: int,
        name: str,
        config_title: str,
        config_uniq_id: str,
        hub: Hub,
        value_off: str,
        value_on: str,
    ) -> None:
        """Initialize a Switch entity."""
        _LOGGER.debug("%s: initializing %s switch", config_title, name)

        self._deviceId = deviceId
        self._capabilityId = capabilityId
        self._config_title = config_title
        self._config_uniq_id = config_uniq_id
        self._hub = hub
        self._value_off = value_off
        self._value_on = value_on
        self._state = False

        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{config_uniq_id}_switch_{str(capabilityId)}"
        self._attr_device_class = SwitchDeviceClass.SWITCH

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._config_uniq_id)},
        )

    @property
    def is_on(self) -> bool:
        """Return the state."""
        self._state = (
            self._hub.get_capability_value(self._deviceId, self._capabilityId)
            != self._value_off
        )
        return self._state

    async def async_turn_on(self):
        """Turn On method."""
        await self._hub.set_capability_value(
            self._deviceId, self._capabilityId, self._value_on
        )

    async def async_turn_off(self):
        """Turn Off method."""
        await self._hub.set_capability_value(
            self._deviceId, self._capabilityId, self._value_off
        )

    async def async_toggle(self) -> None:
        """Toggle the power on the zone."""
        if self._state:
            await self.async_turn_off()
        else:
            await self.async_turn_on()
