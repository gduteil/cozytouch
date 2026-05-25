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


def _get_temperature_adjustment_max_fallback(capability: dict) -> float:
    """Return model-aware fallback max for temperature adjustment entities."""
    default_max = capability.get("highest_value", 60.0)

    if capability.get("modelId") != 2374:
        return default_max

    if capability.get("name") not in {"target_temperature", "target_temperature_dhw"}:
        return default_max

    return 62.0


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
        self._attr_native_max_value = _get_temperature_adjustment_max_fallback(
            capability
        )
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
        self._attr_native_step = capability.get("step", self._attr_native_step)
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._native_value = None
        self._conversion_min_value = float(capability.get("temperatureMin", 0.0))
        self._conversion_max_value = float(capability.get("temperatureMax", 60.0))
        self._attr_native_min_value = self._conversion_min_value
        self._attr_native_max_value = self._conversion_max_value

    @property
    def native_value(self) -> float | None:
        """Value of the sensor."""
        return self._native_value

    def _coerce_float(self, value) -> float | None:
        """Coerce a capability value to float."""
        if value is None or isinstance(value, bool):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _get_float_capability_value(
        self,
        capability_id: int | None,
        fallback: float,
    ) -> float:
        """Return a float capability value with a safe fallback."""
        if capability_id is None:
            return float(fallback)

        value = self._coerce_float(
            self.coordinator.get_capability_value(capability_id, None)
        )
        if value is None:
            return float(fallback)

        return value

    def _refresh_temperature_bounds(self) -> tuple[float, float]:
        """Refresh conversion and writable limits from companion capabilities."""
        fallback_min = float(self._capability.get("temperatureMin", 0.0))
        fallback_max = float(self._capability.get("temperatureMax", 60.0))

        conversion_min = self._get_float_capability_value(
            self._capability.get("temperatureMinCapabilityId"),
            fallback_min,
        )
        conversion_max = self._get_float_capability_value(
            self._capability.get("temperatureMaxCapabilityId"),
            fallback_max,
        )
        if conversion_max <= conversion_min:
            conversion_max = fallback_max
        if conversion_max <= conversion_min:
            conversion_max = conversion_min + 1.0

        native_min = self._get_float_capability_value(
            self._capability.get("lowestValueCapabilityId"),
            fallback_min,
        )
        native_max = self._get_float_capability_value(
            self._capability.get("highestValueCapabilityId"),
            fallback_max,
        )
        if native_max < native_min:
            native_min, native_max = native_max, native_min

        step = self._get_float_capability_value(
            self._capability.get("stepCapabilityId"),
            float(self._attr_native_step or 0.5),
        )
        if step > 0:
            self._attr_native_step = step

        self._conversion_min_value = conversion_min
        self._conversion_max_value = conversion_max
        self._attr_native_min_value = native_min
        self._attr_native_max_value = native_max

        return conversion_min, conversion_max

    def _round_to_native_step(self, value: float) -> float:
        """Round a converted temperature to the native step."""
        step = self._attr_native_step
        if not step or step <= 0:
            return value
        return round(value / step) * step

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update the value of the sensor from the hub."""
        # Get last seen value from controller
        valuePercent = self._coerce_float(
            self.coordinator.get_capability_value(
                self._capability["capabilityId"], None
            )
        )
        if valuePercent is None:
            self._native_value = None
            self.async_write_ha_state()
            return

        conversion_min, conversion_max = self._refresh_temperature_bounds()
        conversion_range = conversion_max - conversion_min
        value = conversion_min + (valuePercent * conversion_range / 100.0)
        value = self._round_to_native_step(value)

        if value < self._attr_native_min_value:
            value = self._attr_native_min_value
        elif value > self._attr_native_max_value:
            value = self._attr_native_max_value

        # Save value
        self._native_value = value
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        conversion_min, conversion_max = self._refresh_temperature_bounds()
        conversion_range = conversion_max - conversion_min
        new_value = value
        if new_value < self._attr_native_min_value:
            new_value = self._attr_native_min_value
        elif new_value > self._attr_native_max_value:
            new_value = self._attr_native_max_value

        valuePercent = (new_value - conversion_min) * 100 / conversion_range

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
