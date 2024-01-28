"""Number entities Atlantic Cozytouch integration."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberDeviceClass, NumberEntity
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

    # Init number entities
    numbers = []
    capabilities = hub.get_capabilities_for_device(config_entry.data["deviceId"])
    for capability in capabilities:
        if capability["type"] == "temperature_adjustment":
            numbers.append(
                TemperatureAdjustmentNumber(
                    deviceId=capability["deviceId"],
                    capabilityId=capability["capabilityId"],
                    lowestValueCapabilityId=capability["lowestValueCapabilityId"],
                    highestValueCapabilityId=capability["highestValueCapabilityId"],
                    name=capability["name"],
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    hub=hub,
                )
            )

    # Add the entities to HA
    if len(numbers) > 0:
        async_add_entities(numbers, True)


class TemperatureAdjustmentNumber(NumberEntity):
    """Temperature adjustment class."""

    _attr_has_entity_name = True
    _attr_should_poll = True

    def __init__(
        self,
        deviceId: int,
        capabilityId: int,
        lowestValueCapabilityId: int,
        highestValueCapabilityId: int,
        name: str,
        config_title: str,
        config_uniq_id: str,
        hub: Hub,
    ) -> None:
        """Initialize a Number entity."""
        _LOGGER.debug("%s: initializing %s number", config_title, name)

        self._deviceId = deviceId
        self._capabilityId = capabilityId
        self._lowestValueCapabilityId = lowestValueCapabilityId
        self._highestValueCapabilityId = highestValueCapabilityId
        self._config_title = config_title
        self._config_uniq_id = config_uniq_id
        self._hub = hub
        self._native_value = 0

        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{config_uniq_id}_switch_{str(capabilityId)}"
        self._attr_device_class = NumberDeviceClass.TEMPERATURE
        self._attr_native_step = 0.5

        self._attr_native_unit_of_measurement = "°C"

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._config_uniq_id)},
        )

    @property
    def native_value(self) -> float | None:
        """Value of the sensor."""
        return self._native_value

    def update(self):
        """Update the value of the sensor from the hub."""
        # Get last seen value from controller
        value = float(
            self._hub.get_capability_value(self._deviceId, self._capabilityId)
        )

        self._attr_native_min_value = float(
            self._hub.get_capability_value(
                self._deviceId, self._lowestValueCapabilityId
            )
        )

        self._attr_native_max_value = float(
            self._hub.get_capability_value(
                self._deviceId, self._highestValueCapabilityId
            )
        )

        _LOGGER.debug(
            "%s: retrieved %s value from hub controller: %s",
            self._config_title,
            self._attr_name,
            repr(value),
        )
        # Handle entity availability
        if value is None:
            if self._attr_available:
                if not self._hub.online:
                    _LOGGER.debug(
                        "%s: marking the %s sensor as unavailable: Cozytouch connection lost",
                        self._config_title,
                        self._attr_name,
                    )
                    self._attr_available = False

            return
        elif not self._attr_available:
            _LOGGER.info(
                "%s: marking the %s sensor as available now !",
                self._config_title,
                self._attr_name,
            )
            self._attr_available = True

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

        await self._hub.set_capability_value(
            self._deviceId, self._capabilityId, str(new_value)
        )
