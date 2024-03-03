"""Switches for Atlantic Cozytouch integration."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .hub import Hub
from .sensor import CozytouchSensor

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
            "%s: can not init switches: failed to get the hub object",
            config_entry.title,
        )
        return

    # Init switches
    switches = []
    capabilities = hub.get_capabilities_for_device()
    for capability in capabilities:
        if capability["type"] == "switch":
            switches.append(
                CozytouchSwitch(
                    coordinator=hub,
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                )
            )

    # Add the entities to HA
    if len(switches) > 0:
        async_add_entities(switches, True)


class CozytouchSwitch(SwitchEntity, CozytouchSensor):
    """Class for switches."""

    def __init__(
        self,
        coordinator: Hub,
        capability,
        config_title: str,
        config_uniq_id: str,
        name: str | None = None,
    ) -> None:
        """Initialize a Switch entity."""
        capabilityId = capability["capabilityId"]
        super().__init__(
            coordinator=coordinator,
            capability=capability,
            config_title=config_title,
            config_uniq_id=config_uniq_id,
            attr_uniq_id=f"{DOMAIN}_{config_uniq_id}_switch_{str(capabilityId)}",
            name=name,
        )
        self._state = False
        self._attr_device_class = SwitchDeviceClass.SWITCH

        self._value_off = capability.get("value_off", "0")
        self._value_on = capability.get("value_on", "1")

    @property
    def is_on(self) -> bool:
        """Return the state."""
        self._state = (
            self.coordinator.get_capability_value(self._capability["capabilityId"])
            != self._value_off
        )
        return self._state

    async def async_turn_on(self):
        """Turn On method."""
        await self.coordinator.set_capability_value(
            self._capability["capabilityId"],
            self._value_on,
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self):
        """Turn Off method."""
        await self.coordinator.set_capability_value(
            self._capability["capabilityId"],
            self._value_off,
        )
        await self.coordinator.async_request_refresh()

    async def async_toggle(self) -> None:
        """Toggle the power on the zone."""
        if self._state:
            await self.async_turn_off()
        else:
            await self.async_turn_on()
