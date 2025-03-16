"""Number entities Atlantic Cozytouch integration."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberDeviceClass, NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant, callback
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
            "%s: can not init binaries sensors: failed to get the hub object",
            config_entry.title,
        )
        return

    # Init number entities
    numbers = []
    capabilities = hub.get_capabilities_for_device()
    for capability in capabilities:
        if capability["type"] == "temperature_adjustment_number":
            numbers.append(
                TemperatureAdjustmentNumber(
                    coordinator=hub,
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                )
            )
        elif capability["type"] == "temperature_percent_adjustment_number":
            numbers.append(
                TemperaturePercentAdjustmentNumber(
                    coordinator=hub,
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                )
            )
        elif capability["type"] == "hours_adjustment_number":
            numbers.append(
                HoursAdjustmentNumber(
                    coordinator=hub,
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                )
            )
        elif capability["type"] == "minutes_adjustment_number":
            numbers.append(
                MinutesAdjustmentNumber(
                    coordinator=hub,
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                )
            )

    # Add the entities to HA
    if len(numbers) > 0:
        async_add_entities(numbers, True)


class TemperatureAdjustmentNumber(NumberEntity, CozytouchSensor):
    """Temperature adjustment class."""

    def __init__(
        self,
        coordinator: Hub,
        capability,
        config_title: str,
        config_uniq_id: str,
        name: str | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialize a Number entity."""
        capabilityId = capability["capabilityId"]
        super().__init__(
            coordinator=coordinator,
            capability=capability,
            config_title=config_title,
            config_uniq_id=config_uniq_id,
            attr_uniq_id=f"{DOMAIN}_{config_uniq_id}_number_{str(capabilityId)}",
            name=name,
            icon=icon,
        )
        self._attr_device_class = NumberDeviceClass.TEMPERATURE
        self._attr_mode = "auto"
        self._attr_native_step = capability.get("step", 0.5)
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_native_min_value = capability.get("lowest_value", 0)
        self._attr_native_max_value = capability.get("highest_value", 60.0)
        self._native_value = 0

    @property
    def native_value(self) -> float | None:
        """Value of the sensor."""
        return self._native_value

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update the value of the sensor from the hub."""
        # Get last seen value from controller
        value = float(
            self.coordinator.get_capability_value(self._capability["capabilityId"])
        )

        if "lowestValueCapabilityId" in self._capability:
            lowestValue = self.coordinator.get_capability_value(
                self._capability["lowestValueCapabilityId"], None
            )
            if lowestValue:
                self._attr_native_min_value = float(lowestValue)

        if "highestValueCapabilityId" in self._capability:
            highestValue = self.coordinator.get_capability_value(
                self._capability["highestValueCapabilityId"], None
            )
            if highestValue:
                self._attr_native_max_value = float(highestValue)

        if value < self._attr_native_min_value:
            value = self._attr_native_min_value
        elif value > self._attr_native_max_value:
            value = self._attr_native_max_value

        # Save value
        self._native_value = value
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        new_value = value
        if new_value < self._attr_native_min_value:
            new_value = self._attr_native_min_value
        elif new_value > self._attr_native_max_value:
            new_value = self._attr_native_max_value

        await self.coordinator.set_capability_value(
            self._capability["capabilityId"],
            str(new_value),
        )


class TemperaturePercentAdjustmentNumber(NumberEntity, CozytouchSensor):
    """Temperature percent adjustment class."""

    def __init__(
        self,
        coordinator: Hub,
        capability,
        config_title: str,
        config_uniq_id: str,
        name: str | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialize a Number entity."""
        capabilityId = capability["capabilityId"]
        super().__init__(
            coordinator=coordinator,
            capability=capability,
            config_title=config_title,
            config_uniq_id=config_uniq_id,
            attr_uniq_id=f"{DOMAIN}_{config_uniq_id}_number_{str(capabilityId)}",
            name=name,
            icon=icon,
        )
        self._attr_device_class = NumberDeviceClass.TEMPERATURE
        self._attr_mode = "auto"
        self._attr_native_step = 0.5
        self._attr_native_unit_of_measurement = "°C"
        self._native_value = 0

        self._attr_native_min_value = 0.0
        if "temperatureMin" in capability:
            self._attr_native_min_value = capability["temperatureMin"]

        self._attr_native_max_value = 60.0
        if "temperatureMax" in capability:
            self._attr_native_max_value = capability["temperatureMax"]

        self._range = self._attr_native_max_value - self._attr_native_min_value

    @property
    def native_value(self) -> float | None:
        """Value of the sensor."""
        return self._native_value

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update the value of the sensor from the hub."""
        # Get last seen value from controller
        valuePercent = float(
            self.coordinator.get_capability_value(self._capability["capabilityId"])
        )

        value = self._attr_native_min_value + (valuePercent * self._range / 100.0)

        if value < self._attr_native_min_value:
            value = self._attr_native_min_value
        elif value > self._attr_native_max_value:
            value = self._attr_native_max_value

        # Save value
        self._native_value = value
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        new_value = value
        if new_value < self._attr_native_min_value:
            new_value = self._attr_native_min_value
        elif new_value > self._attr_native_max_value:
            new_value = self._attr_native_max_value

        valuePercent = (new_value - self._attr_native_min_value) * 100 / self._range

        await self.coordinator.set_capability_value(
            self._capability["capabilityId"],
            str(valuePercent),
        )


class HoursAdjustmentNumber(NumberEntity, CozytouchSensor):
    """Hours adjustment number class."""

    def __init__(
        self,
        coordinator: Hub,
        capability,
        config_title: str,
        config_uniq_id: str,
        name: str | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialize a Number entity."""
        capabilityId = capability["capabilityId"]
        super().__init__(
            capability=capability,
            config_title=config_title,
            config_uniq_id=config_uniq_id,
            attr_uniq_id=f"{DOMAIN}_{config_uniq_id}_number_{str(capabilityId)}",
            coordinator=coordinator,
            name=name,
            icon=icon,
        )
        self._attr_device_class = None
        self._attr_mode = "auto"
        self._attr_native_unit_of_measurement = UnitOfTime.HOURS
        self._attr_native_step = capability.get("step", 1)
        self._attr_native_min_value = capability.get("lowest_value", 0)
        self._attr_native_max_value = capability.get("highest_value", 100)
        self._native_value = 0

    @property
    def native_value(self) -> float | None:
        """Value of the sensor."""
        return self._native_value

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update the value of the sensor from the hub."""
        # Get last seen value from controller
        value = (
            float(
                self.coordinator.get_capability_value(self._capability["capabilityId"])
            )
            / 60.0
        )

        if value < self._attr_native_min_value:
            value = self._attr_native_min_value
        elif value > self._attr_native_max_value:
            value = self._attr_native_max_value

        self._native_value = value
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        new_value = value
        if new_value < self._attr_native_min_value:
            new_value = self._attr_native_min_value
        elif new_value > self._attr_native_max_value:
            new_value = self._attr_native_max_value

        await self.coordinator.set_capability_value(
            self._capability["capabilityId"], str(int(new_value * 60))
        )

        await self.coordinator.async_request_refresh()

class MinutesAdjustmentNumber(NumberEntity, CozytouchSensor):
    """Minutes adjustment number class."""

    def __init__(
        self,
        coordinator: Hub,
        capability,
        config_title: str,
        config_uniq_id: str,
        name: str | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialize a Number entity."""
        capabilityId = capability["capabilityId"]
        super().__init__(
            capability=capability,
            config_title=config_title,
            config_uniq_id=config_uniq_id,
            attr_uniq_id=f"{DOMAIN}_{config_uniq_id}_number_{str(capabilityId)}",
            coordinator=coordinator,
            name=name,
            icon=icon,
        )
        self._attr_device_class = None
        self._attr_mode = "auto"
        self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
        self._attr_native_step = capability.get("step", 1)
        self._attr_native_min_value = capability.get("lowest_value", 0)
        self._attr_native_max_value = capability.get("highest_value", 60)
        self._native_value = 0

    @property
    def native_value(self) -> float | None:
        """Value of the sensor."""
        return self._native_value

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update the value of the sensor from the hub."""
        # Get last seen value from controller
        value = (
            float(
                self.coordinator.get_capability_value(self._capability["capabilityId"])
            )
        )

        if value < self._attr_native_min_value:
            value = self._attr_native_min_value
        elif value > self._attr_native_max_value:
            value = self._attr_native_max_value

        self._native_value = value
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        new_value = value
        if new_value < self._attr_native_min_value:
            new_value = self._attr_native_min_value
        elif new_value > self._attr_native_max_value:
            new_value = self._attr_native_max_value

        await self.coordinator.set_capability_value(
            self._capability["capabilityId"], str(int(new_value))
        )

        await self.coordinator.async_request_refresh()
