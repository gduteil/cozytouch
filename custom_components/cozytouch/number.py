"""Number entities Atlantic Cozytouch integration."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberDeviceClass, NumberEntity
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
            "%s: can not init binaries sensors: failed to get the hub object",
            config_entry.title,
        )
        return

    # Init number entities
    numbers = []
    capabilities = hub.get_capabilities_for_device(config_entry.data["deviceId"])
    for capability in capabilities:
        if capability["type"] == "temperature_adjustment_number":
            numbers.append(
                TemperatureAdjustmentNumber(
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    hub=hub,
                )
            )

    # Add the entities to HA
    if len(numbers) > 0:
        async_add_entities(numbers, True)


class TemperatureAdjustmentNumber(NumberEntity, CozytouchSensor):
    """Temperature adjustment class."""

    def __init__(
        self,
        capability,
        config_title: str,
        config_uniq_id: str,
        hub: Hub,
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
            hub=hub,
            name=name,
            icon=icon,
        )
        self._attr_device_class = NumberDeviceClass.TEMPERATURE
        self._native_value = 0
        self._attr_native_step = 0.5
        self._attr_native_unit_of_measurement = "°C"
        self._attr_native_min_value = 0.0
        self._attr_native_max_value = 60.0

    @property
    def native_value(self) -> float | None:
        """Value of the sensor."""
        return self._native_value

    def update(self):
        """Update the value of the sensor from the hub."""
        # Get last seen value from controller
        value = float(self._get_capability_value(self._capability["capabilityId"]))

        if "lowestValueCapabilityId" in self._capability:
            lowestValue = self._get_capability_value(
                self._capability["lowestValueCapabilityId"]
            )
            if lowestValue:
                self._attr_native_min_value = float(lowestValue)

        if "highestValueCapabilityId" in self._capability:
            highestValue = self._get_capability_value(
                self._capability["highestValueCapabilityId"]
            )
            if highestValue:
                self._attr_native_max_value = float(highestValue)

        if value < self._attr_native_min_value:
            value = self._attr_native_min_value
        elif value > self._attr_native_max_value:
            value = self._attr_native_max_value

        # Save value
        self._native_value = value

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        new_value = value
        if new_value < self._attr_native_min_value:
            new_value = self._attr_native_min_value
        elif new_value > self._attr_native_max_value:
            new_value = self._attr_native_max_value

        await self._set_capability_value(
            self._capability["capabilityId"],
            str(new_value),
        )
