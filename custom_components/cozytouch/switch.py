"""Switches for Atlantic Cozytouch integration."""
from __future__ import annotations

from datetime import datetime
import logging

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .hub import (
    CozytouchConfigEntry,
    Hub,
    add_capability_entities,
    away_window_is_valid,
)
from .infos import CapabilityType
from .sensor import CozytouchSensor

_LOGGER = logging.getLogger(__name__)


# config flow setup
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: CozytouchConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up entry."""
    add_capability_entities(
        config_entry,
        async_add_entities,
        {
            CapabilityType.SWITCH: CozytouchSwitch,
            CapabilityType.AWAY_MODE_SWITCH: CozytouchAwayModeSwitch,
        },
    )


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
        capabilityId = capability.capabilityId
        super().__init__(
            coordinator=coordinator,
            capability=capability,
            config_title=config_title,
            config_uniq_id=config_uniq_id,
            attr_uniq_id=f"{DOMAIN}_{config_uniq_id}_switch_{capabilityId!s}",
            name=name,
        )
        self._state = False
        self._attr_device_class = SwitchDeviceClass.SWITCH

        self._value_off = capability.get("value_off", "0")
        self._value_on = capability.get("value_on", "1")

    @property
    def is_on(self) -> bool:
        """Return the state."""
        value = self.coordinator.get_capability_value(self._capability.capabilityId)
        self._state = value is not None and value == self._value_on
        return self._state

    async def async_turn_on(self):
        """Turn On method."""
        await self.coordinator.set_capability_value(
            self._capability.capabilityId,
            self._value_on,
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self):
        """Turn Off method."""
        await self.coordinator.set_capability_value(
            self._capability.capabilityId,
            self._value_off,
        )
        await self.coordinator.async_request_refresh()

    async def async_toggle(self) -> None:
        """Toggle the power on the zone."""
        if self._state:
            await self.async_turn_off()
        else:
            await self.async_turn_on()


class CozytouchAwayModeSwitch(CozytouchSwitch):
    """Class for away mode switch."""

    def __init__(
        self,
        coordinator: Hub,
        capability,
        config_title: str,
        config_uniq_id: str,
        name: str | None = None,
    ) -> None:
        """Initialize a Switch entity."""
        super().__init__(coordinator, capability, config_title, config_uniq_id, name)
        self._nb_ignore = 0
        self._value_pending = capability.get("value_pending", "2")

    @property
    def is_on(self) -> bool:
        """Return the state."""
        if self._nb_ignore > 0:
            self._nb_ignore = self._nb_ignore - 1
        else:
            value = self.coordinator.get_capability_value(
                self._capability.capabilityId
            )
            self._state = value is not None and value != self._value_off

        return self._state

    async def async_turn_on(self):
        """Turn On method."""
        timestampStart = self.coordinator.get_away_mode_start()
        timestampEnd = self.coordinator.get_away_mode_end()

        # What the pickers show while the absence is off : no start, or one
        # already past, is the next minute ; no end, or one not after the
        # start, is two days later.
        soon = datetime.now(tz=dt_util.DEFAULT_TIME_ZONE).timestamp() + 60
        if not timestampStart or timestampStart < soon:
            timestampStart = soon
        if not away_window_is_valid(timestampStart, timestampEnd):
            timestampEnd = timestampStart + (2 * 24 * 60 * 60)

        self._nb_ignore = 5
        self._state = True
        await self.coordinator.set_away_mode(int(timestampStart), int(timestampEnd))
        self._nb_ignore = 1

    async def async_turn_off(self):
        """Turn Off method."""
        self._nb_ignore = 5
        self._state = False
        await self.coordinator.set_away_mode(None, None)
        self._nb_ignore = 1
