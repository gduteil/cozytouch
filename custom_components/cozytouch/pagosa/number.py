"""Pagosa numbers: target temperature, Boost and Absence durations.

Carried from the pagosa-1.4 branch unchanged but for the hub it talks to.
"""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberDeviceClass, NumberEntity
from homeassistant.const import UnitOfTemperature
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN
from .hub import PagosaHub as Hub

_LOGGER = logging.getLogger(__name__)


class OverkizPagosaNumberBase(CoordinatorEntity[Hub], NumberEntity):
    """Base class for Pagosa number entities."""

    _attr_has_entity_name = True
    _attr_mode = "slider"

    def __init__(
        self,
        coordinator: Hub,
        config_title: str,
        config_uniq_id: str,
        unique_suffix: str,
    ) -> None:
        """Initialize a Pagosa number entity."""
        super().__init__(coordinator)

        self._attr_unique_id = (
            f"{DOMAIN}_{config_uniq_id}_pagosa_{unique_suffix}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(coordinator._deviceId))},
            manufacturer="Sauter",
            model="Pagosa 270L",
            name=config_title,
        )

    @property
    def available(self) -> bool:
        """Return entity availability."""
        return (
            self.coordinator.online
            and self.coordinator.last_update_success
        )


class OverkizPagosaTargetTemperatureNumber(OverkizPagosaNumberBase):
    """Pagosa target temperature controlled through Overkiz."""

    _attr_name = "Température de consigne"
    _attr_icon = "mdi:thermometer-water"
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = 40
    _attr_native_max_value = 65
    _attr_native_step = 1

    def __init__(
        self,
        coordinator: Hub,
        config_title: str,
        config_uniq_id: str,
    ) -> None:
        """Initialize the Pagosa target temperature entity."""
        super().__init__(
            coordinator,
            config_title,
            config_uniq_id,
            "target_temperature",
        )
        self._attr_native_value = self._read_value()

    def _read_value(self) -> float:
        """Read the target temperature from Overkiz."""
        value = self.coordinator.get_overkiz_state(
            "core:TargetTemperatureState",
            50,
        )
        try:
            return float(value)
        except (TypeError, ValueError):
            return 50.0

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update the displayed target temperature."""
        self._attr_native_value = self._read_value()
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Send a new target temperature to the Pagosa."""
        new_value = max(40, min(65, value))
        await self.coordinator.set_overkiz_target_temperature(new_value)


class OverkizPagosaBoostDurationNumber(OverkizPagosaNumberBase):
    """Pagosa Boost duration."""

    _attr_name = "Durée Boost"
    _attr_icon = "mdi:rocket-launch"
    _attr_native_min_value = 0
    _attr_native_max_value = 7
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "d"

    def __init__(
        self,
        coordinator: Hub,
        config_title: str,
        config_uniq_id: str,
    ) -> None:
        """Initialize Boost duration."""
        super().__init__(
            coordinator,
            config_title,
            config_uniq_id,
            "boost_duration",
        )
        self._attr_native_value = self._read_value()

    def _read_value(self) -> float:
        """Read Boost duration."""
        value = self.coordinator.get_overkiz_state(
            "core:BoostModeDurationState",
            0,
        )
        try:
            return max(0, min(7, float(value)))
        except (TypeError, ValueError):
            return 0

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update Boost duration."""
        self._attr_native_value = self._read_value()
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Set Boost duration."""
        new_value = int(max(0, min(7, value)))
        await self.coordinator.set_overkiz_boost_duration(new_value)


class OverkizPagosaAwayDurationNumber(OverkizPagosaNumberBase):
    """Pagosa absence duration."""

    _attr_name = "Durée Absence"
    _attr_icon = "mdi:home-export-outline"
    _attr_native_min_value = 0
    _attr_native_max_value = 6
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "d"

    def __init__(
        self,
        coordinator: Hub,
        config_title: str,
        config_uniq_id: str,
    ) -> None:
        """Initialize absence duration."""
        super().__init__(
            coordinator,
            config_title,
            config_uniq_id,
            "away_duration",
        )
        self._attr_native_value = self._read_value()

    def _read_value(self) -> float:
        """Read absence duration."""
        value = self.coordinator.get_overkiz_state(
            "io:AwayModeDurationState",
            0,
        )
        try:
            return max(0, min(6, float(value)))
        except (TypeError, ValueError):
            return 0

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update absence duration."""
        self._attr_native_value = self._read_value()
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Set absence duration."""
        new_value = int(max(0, min(6, value)))
        await self.coordinator.set_overkiz_away_duration(new_value)




async def async_setup_pagosa(
    hub: Hub,
    config_entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add this platform's Pagosa entities ; config_entry is a PagosaContext."""
    numbers = []
    numbers.extend(
        [
            OverkizPagosaTargetTemperatureNumber(
                coordinator=hub,
                config_title=config_entry.title,
                config_uniq_id=config_entry.entry_id,
            ),
            OverkizPagosaBoostDurationNumber(
                coordinator=hub,
                config_title=config_entry.title,
                config_uniq_id=config_entry.entry_id,
            ),
            OverkizPagosaAwayDurationNumber(
                coordinator=hub,
                config_title=config_entry.title,
                config_uniq_id=config_entry.entry_id,
            ),
        ]
    )

    if numbers:
        async_add_entities(numbers, True)
