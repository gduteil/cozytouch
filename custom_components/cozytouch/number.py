"""Number entities Atlantic Cozytouch integration."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberDeviceClass, NumberEntity
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .hub import CozytouchConfigEntry, Hub, add_capability_entities
from .infos import CapabilityType
from .sensor import CozytouchSensor

_LOGGER = logging.getLogger(__name__)


# config flow setup
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: CozytouchConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entry."""
    add_capability_entities(
        config_entry,
        async_add_entities,
        {
            CapabilityType.TEMPERATURE_ADJUSTMENT_NUMBER: TemperatureAdjustmentNumber,
            CapabilityType.TEMPERATURE_PERCENT_ADJUSTMENT_NUMBER: (
                TemperaturePercentAdjustmentNumber
            ),
            CapabilityType.MINUTES_ADJUSTMENT_NUMBER: MinutesAdjustmentNumber,
        },
    )



def clamp(value: float, lowest: float, highest: float) -> float:
    """`value` held between the two bounds, the lower one winning a tie."""
    return max(lowest, min(value, highest))


class CozytouchAdjustmentNumber(NumberEntity, CozytouchSensor):
    """A capability somebody can set, in whatever unit it is set in.

    The subclasses differ in three things and nothing else: what they declare
    about themselves, how an API value becomes a displayed one, and how a
    displayed one goes back. See docs/decisions.md.
    """

    _attr_mode = "auto"

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
        capabilityId = capability.capabilityId
        super().__init__(
            coordinator=coordinator,
            capability=capability,
            config_title=config_title,
            config_uniq_id=config_uniq_id,
            attr_uniq_id=f"{DOMAIN}_{config_uniq_id}_number_{capabilityId!s}",
            name=name,
            icon=icon,
        )
        self._native_value = 0

    @property
    def native_value(self) -> float | None:
        """Value of the sensor."""
        return self._native_value

    def _read_bounds(self) -> None:
        """Take the range from the device, for the entities that have one."""

    def _from_api(self, value: float) -> float:
        """The displayed value for what the API reports."""
        return value

    def _to_api(self, value: float) -> str:
        """What to send for the value somebody set."""
        return str(value)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update the value of the sensor from the hub."""
        value = float(
            self.coordinator.get_capability_value(self._capability.capabilityId)
        )
        self._read_bounds()

        self._native_value = clamp(
            self._from_api(value),
            self._attr_native_min_value,
            self._attr_native_max_value,
        )
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        new_value = clamp(
            value, self._attr_native_min_value, self._attr_native_max_value
        )

        await self.coordinator.set_capability_value(
            self._capability.capabilityId, self._to_api(new_value)
        )

        await self.coordinator.async_request_refresh()


class TemperatureAdjustmentNumber(CozytouchAdjustmentNumber):
    """Temperature adjustment class."""

    def __init__(self, coordinator: Hub, capability, **kwargs) -> None:
        """Initialize a Number entity."""
        super().__init__(coordinator=coordinator, capability=capability, **kwargs)
        self._attr_device_class = NumberDeviceClass.TEMPERATURE
        self._attr_native_step = capability.get("step", 0.5)
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_native_min_value = capability.get("lowest_value", 0)
        self._attr_native_max_value = capability.get("highest_value", 60.0)

    def _read_bounds(self) -> None:
        """The only one of these whose range moves with the hardware."""
        if "lowestValueCapabilityId" in self._capability:
            lowestValue = self.coordinator.get_capability_value(
                self._capability.lowestValueCapabilityId, None
            )
            if lowestValue:
                self._attr_native_min_value = float(lowestValue)

        if "highestValueCapabilityId" in self._capability:
            highestValue = self.coordinator.get_capability_value(
                self._capability.highestValueCapabilityId, None
            )
            if highestValue:
                self._attr_native_max_value = float(highestValue)


class TemperaturePercentAdjustmentNumber(CozytouchAdjustmentNumber):
    """Temperature percent adjustment class."""

    def __init__(self, coordinator: Hub, capability, **kwargs) -> None:
        """Initialize a Number entity."""
        super().__init__(coordinator=coordinator, capability=capability, **kwargs)
        self._attr_device_class = NumberDeviceClass.TEMPERATURE
        self._attr_native_step = 0.5
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

        self._attr_native_min_value = 0.0
        if "temperatureMin" in capability:
            self._attr_native_min_value = capability.temperatureMin

        self._attr_native_max_value = 60.0
        if "temperatureMax" in capability:
            self._attr_native_max_value = capability.temperatureMax

        self._range = self._attr_native_max_value - self._attr_native_min_value

    def _from_api(self, value: float) -> float:
        return self._attr_native_min_value + (value * self._range / 100.0)

    def _to_api(self, value: float) -> str:
        return str((value - self._attr_native_min_value) * 100 / self._range)


class MinutesAdjustmentNumber(CozytouchAdjustmentNumber):
    """Minutes adjustment number class."""

    def __init__(self, coordinator: Hub, capability, **kwargs) -> None:
        """Initialize a Number entity."""
        super().__init__(coordinator=coordinator, capability=capability, **kwargs)
        self._attr_device_class = None
        self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
        self._attr_native_step = capability.get("step", 1)
        self._attr_native_min_value = capability.get("lowest_value", 0)
        self._attr_native_max_value = capability.get("highest_value", 60)

    def _to_api(self, value: float) -> str:
        return str(int(value))
