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

    # Init climate entities
    climates = []
    capabilities = hub.get_capabilities_for_device(config_entry.data["deviceId"])
    for capability in capabilities:
        if capability["type"] == "climate":
            climates.append(
                CozytouchClimate(
                    deviceId=capability["deviceId"],
                    capabilityId=capability["capabilityId"],
                    activeCapabilityId=capability["activeCapabilityId"],
                    currentValueCapabilityId=capability["currentValueCapabilityId"],
                    name=capability["name"],
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    hub=hub,
                )
            )

    # Add the entities to HA
    if len(climates) > 0:
        async_add_entities(climates, True)


class CozytouchClimate(ClimateEntity):
    """Temperature adjustment class."""

    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_hvac_modes = [HVACMode.DRY, HVACMode.FAN_ONLY, HVACMode.HEAT, HVACMode.COOL, HVACMode.AUTO, HVACMode.OFF]
    _attr_hvac_mode = HVACMode.OFF
    _attr_max_temp = 0
    _attr_min_temp = 30
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    _dict_hvac_modes = {
        "value_off" : HVACMode.OFF,
        "value_auto" : HVACMode.AUTO,
        "value_cool" : HVACMode.COOL,
        "value_heat" : HVACMode.HEAT,
        "value_fan" : HVACMode.FAN_ONLY,
        "value_dry" : HVACMode.DRY
    }

    def __init__(
        self,
        deviceId: int,
        capabilityId: int,
        activeCapabilityId: int,
        currentValueCapabilityId: int,
        name: str,
        config_title: str,
        config_uniq_id: str,
        hub: Hub,
    ) -> None:
        """Initialize a Number entity."""
        _LOGGER.debug("%s: initializing %s climate", config_title, name)

        self._deviceId = deviceId
        self._capabilityId = capabilityId
        self._activeCapabilityId = activeCapabilityId
        self._currentValueCapabilityId = currentValueCapabilityId
        self._config_title = config_title
        self._config_uniq_id = config_uniq_id
        self._hub = hub
        self._native_value = 0
        self._current_value = 0

        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{config_uniq_id}_climate_{str(capabilityId)}"
        self._attr_native_step = 0.5 # TODO : config 294

        self._attr_native_unit_of_measurement = "°C"

        self._modelId = self._hub.get_model_id(deviceId)

        self._activeCapabilityInfos = self._hub.get_capability_infos(
                    self._modelId, self._activeCapabilityId
                )

        self._attr_hvac_modes=[self._dict_hvac_modes[v] for v in self._activeCapabilityInfos.keys() if v[:6]=='value_']

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._config_uniq_id)},
        )

    @property
    def temperature_unit(self):
        """Return temperature unit used."""
        return UnitOfTemperature.CELSIUS

    def update(self):
        active = self._hub.get_capability_value(
            self._deviceId, self._activeCapabilityId
        )

        """Update the values from the hub."""
        if active in [self._activeCapabilityInfos[v] for v in self._activeCapabilityInfos.keys() if v in ("value_heat", "value_auto", "value_off")] :
            self._native_value = float(
                self._hub.get_capability_value(
                    self._deviceId, self._activeCapabilityInfos["targetHeatValueCapabilityId"]
                )
            )
        else :
            self._native_value = float(
                self._hub.get_capability_value(
                    self._deviceId, self._activeCapabilityInfos["targetValueCapabilityId"]
                )
            )

        if self._activeCapabilityInfos is not None:
            if active :
                self._attr_hvac_mode = [self._dict_hvac_modes[v] for v in self._activeCapabilityInfos.keys() if v[:6]=='value_'][[self._activeCapabilityInfos[v] for v in self._activeCapabilityInfos.keys() if v[:6]=='value_'].index(active)]

        self._current_value = float(
            self._hub.get_capability_value(
                self._deviceId, self._currentValueCapabilityId
            )
        )

        if active in [self._activeCapabilityInfos[v] for v in self._activeCapabilityInfos.keys() if v in ("value_heat", "value_off")] :
            self._attr_min_temp = float(
                self._hub.get_capability_value(
                    self._deviceId, self._activeCapabilityInfos["lowestHeatValueCapabilityId"]
                )
            )
            self._attr_max_temp = float(
                self._hub.get_capability_value(
                    self._deviceId, self._activeCapabilityInfos["highestHeatValueCapabilityId"]
                )
            )
        else:
            self._attr_min_temp = float(
                self._hub.get_capability_value(
                    self._deviceId, self._activeCapabilityInfos["lowestValueCapabilityId"]
                )
            )
            self._attr_max_temp = float(
                self._hub.get_capability_value(
                    self._deviceId, self._activeCapabilityInfos["highestValueCapabilityId"]
                )
            )

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
            if self._attr_hvac_mode in (HVACMode.HEAT, HVACMode.AUTO) :
                await self._hub.set_capability_value(
                    self._deviceId, self._activeCapabilityInfos["targetHeatValueCapabilityId"], str(temperature)
                )
            else :
                await self._hub.set_capability_value(
                    self._deviceId, self._activeCapabilityInfos["targetValueCapabilityId"], str(temperature)
                )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set hvac mode."""
        if self._activeCapabilityInfos is not None:
            await self._hub.set_capability_value(
                self._deviceId,
                self._activeCapabilityId,
                self._activeCapabilityInfos[list(self._dict_hvac_modes.keys())[list(self._dict_hvac_modes.values()).index(hvac_mode)]],
            )
