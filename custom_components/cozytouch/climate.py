"""Climate entities Atlantic Cozytouch integration."""
from __future__ import annotations

import logging

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
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

    # Init climate entities
    climates = []
    capabilities = hub.get_capabilities_for_device(config_entry.data["deviceId"])
    for capability in capabilities:
        if capability["type"] == "temperature_adjustment":
            climates.append(
                CozytouchClimate(
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    hub=hub,
                )
            )

    # Add the entities to HA
    if len(climates) > 0:
        async_add_entities(climates, True)


class CozytouchClimate(ClimateEntity, CozytouchSensor):
    """Temperature adjustment climate class."""

    def __init__(
        self,
        capability,
        config_title: str,
        config_uniq_id: str,
        hub: Hub,
        name: str | None = None,
    ) -> None:
        """Initialize a climate entity."""
        capabilityId = capability["capabilityId"]
        super().__init__(
            capability=capability,
            config_title=config_title,
            config_uniq_id=config_uniq_id,
            attr_uniq_id=f"{DOMAIN}_{config_uniq_id}_climate_{str(capabilityId)}",
            hub=hub,
            name=name,
        )
        self._native_value = 0
        self._current_value = 0
        self._attr_native_step = 0.5
        self._attr_native_unit_of_measurement = "°C"

        self._attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_max_temp = 0
        self._attr_min_temp = 30
        self._attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS

        # Get sub capabilities
        self._capabilityActive = None
        if "activeCapabilityId" in capability:
            self._capabilityActive = self._hub.get_capability_infos(
                self._capability["deviceId"], self._capability["activeCapabilityId"]
            )

    def update(self):
        """Update the values from the hub."""
        self._native_value = float(
            self._get_capability_value(self._capability["capabilityId"])
        )

        if self._capabilityActive:
            active = self._get_capability_value(self._capability["activeCapabilityId"])
            if active == self._capabilityActive.get("value_off", 0):
                self._attr_hvac_mode = HVACMode.OFF
            elif active == self._capabilityActive.get("value_on", 1):
                self._attr_hvac_mode = HVACMode.HEAT

        currentValueId = self._capability["currentValueCapabilityId"]
        self._current_value = float(self._get_capability_value(currentValueId))

        lowestValueId = self._capability["lowestValueCapabilityId"]
        self._attr_min_temp = float(self._get_capability_value(lowestValueId))

        highestValueId = self._capability["highestValueCapabilityId"]
        self._attr_max_temp = float(self._get_capability_value(highestValueId))

    @property
    def current_temperature(self):
        """Return current temperature."""
        return self._current_value

    @property
    def target_temperature(self):
        """Return target temperature."""
        return self._native_value

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        temperature = kwargs.get("temperature")
        if temperature is not None:
            await self._hub.set_capability_value(
                self._capability["deviceId"],
                self._capability["capabilityId"],
                str(temperature),
            )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set hvac mode."""

        if self._capabilityActive:
            if hvac_mode == HVACMode.HEAT:
                await self._hub.set_capability_value(
                    self._capability["deviceId"],
                    self._capability["activeCapabilityId"],
                    self._capabilityActive.get("value_on", "1"),
                )
            elif hvac_mode == HVACMode.OFF:
                await self._hub.set_capability_value(
                    self._capability["deviceId"],
                    self._capability["activeCapabilityId"],
                    self._capabilityActive.get("value_off", "0"),
                )
