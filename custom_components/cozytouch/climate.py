"""Climate entities Atlantic Cozytouch integration."""
from __future__ import annotations

import logging

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.climate.const import SWING_ON
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .hub import Hub
from .sensor import CozytouchSensor

_LOGGER = logging.getLogger(__name__)

FAN_QUIET = "Quiet"


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
    """Climate class."""

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

        self._modelInfos = self._hub.get_model_infos(self._capability["deviceId"])

        self._native_value = 0
        self._current_value = None
        self._attr_native_step = 0.5
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_max_temp = 0
        self._attr_min_temp = 30
        self._attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE

        self._attr_hvac_modes = list(self._modelInfos["HVACModes"].values())
        self._attr_hvac_mode = HVACMode.OFF

        if "fanModes" in self._modelInfos:
            self._configure_fan_modes()

        if "swingModes" in self._modelInfos:
            self._configure_swing_modes()

    def _configure_fan_modes(self):
        self._attr_supported_features |= ClimateEntityFeature.FAN_MODE
        self._attr_fan_modes = list(self._modelInfos["fanModes"].values())

        if "quietModeCapabilityId" in self._capability:
            self._attr_fan_modes.append(FAN_QUIET)

        if len(self._attr_fan_modes) > 0:
            self._attr_fan_mode = self._attr_fan_modes[0]

    def _configure_swing_modes(self):
        self._attr_supported_features |= ClimateEntityFeature.SWING_MODE
        self._attr_swing_modes = list(self._modelInfos["swingModes"].values())

        if "swingOnCapabilityId" in self._capability:
            self._attr_swing_modes.append(SWING_ON)

        if len(self._attr_swing_modes) > 0:
            self._attr_swing_mode = self._attr_swing_modes[0]

    def update(self):
        """Update the values from the hub."""

        # HVAC Mode
        HVACModes = self._modelInfos["HVACModes"]
        currentMode = int(self._get_capability_value(self._capability["capabilityId"]))
        if currentMode in HVACModes:
            self._attr_hvac_mode = HVACModes[currentMode]

        # Target value
        if self._attr_hvac_mode in (
            HVACMode.OFF,
            HVACMode.DRY,
            HVACMode.FAN_ONLY,
        ):
            self._native_value = None
        elif (
            self._attr_hvac_mode == HVACMode.COOL
            and "targetCoolCapabilityId" in self._capability
        ):
            self._native_value = float(
                self._get_capability_value(self._capability["targetCoolCapabilityId"])
            )
        else:
            self._native_value = float(
                self._get_capability_value(self._capability["targetCapabilityId"])
            )

        # Current value
        currentValueId = self._capability.get("currentValueCapabilityId", None)
        if currentValueId:
            self._current_value = float(self._get_capability_value(currentValueId))

        # Lowest adjustment value
        if (
            self._attr_hvac_mode == HVACMode.COOL
            and "lowestCoolValueCapabilityId" in self._capability
        ):
            lowestValueId = self._capability.get("lowestCoolValueCapabilityId", None)
            self._attr_min_temp = float(self._get_capability_value(lowestValueId))
        elif "lowestValueCapabilityId" in self._capability:
            lowestValueId = self._capability.get("lowestValueCapabilityId", None)
            self._attr_min_temp = float(self._get_capability_value(lowestValueId))

        # Highest adjustment value
        if (
            self._attr_hvac_mode == HVACMode.COOL
            and "highestCoolValueCapabilityId" in self._capability
        ):
            highestValueId = self._capability["highestCoolValueCapabilityId"]
            self._attr_max_temp = float(self._get_capability_value(highestValueId))
        elif "highestValueCapabilityId" in self._capability:
            highestValueId = self._capability["highestValueCapabilityId"]
            self._attr_max_temp = float(self._get_capability_value(highestValueId))

        # FAN mode
        if "quietModeCapabilityId" in self._capability and int(
            self._get_capability_value(self._capability["quietModeCapabilityId"])
        ):
            self._attr_fan_mode = FAN_QUIET
        elif "fanModeCapabilityId" in self._capability:
            fanModes = self._modelInfos["fanModes"]
            fanModeValue = int(
                self._get_capability_value(self._capability["fanModeCapabilityId"])
            )
            if fanModeValue in fanModes:
                self._attr_fan_mode = fanModes[fanModeValue]

        # Swing mode
        if "swingOnCapabilityId" in self._capability and int(
            self._get_capability_value(self._capability["swingOnCapabilityId"])
        ):
            self._attr_swing_mode = SWING_ON
        elif "swingModeCapabilityId" in self._capability:
            swingModes = self._modelInfos["swingModes"]
            swingModeValue = int(
                self._get_capability_value(self._capability["swingModeCapabilityId"])
            )
            if swingModeValue in swingModes:
                self._attr_swing_mode = swingModes[swingModeValue]

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
            if (
                self._attr_hvac_mode == HVACMode.COOL
                and "targetCoolCapabilityId" in self._capability
            ):
                await self._hub.set_capability_value(
                    self._capability["deviceId"],
                    self._capability["targetCoolCapabilityId"],
                    str(temperature),
                )
            else:
                await self._hub.set_capability_value(
                    self._capability["deviceId"],
                    self._capability["targetCapabilityId"],
                    str(temperature),
                )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set hvac mode."""
        HVACModes = self._modelInfos["HVACModes"]
        for mode in HVACModes:
            if HVACModes[mode] == hvac_mode:
                await self._hub.set_capability_value(
                    self._capability["deviceId"],
                    self._capability["capabilityId"],
                    str(mode),
                )
                break

    async def async_set_fan_mode(self, fan_mode) -> None:
        """Set new target fan mode."""
        if fan_mode == FAN_QUIET and "quietModeCapabilityId" in self._capability:
            await self._hub.set_capability_value(
                self._capability["deviceId"],
                self._capability["quietModeCapabilityId"],
                "1",
            )
        elif "fanModeCapabilityId" in self._capability:
            if "quietModeCapabilityId" in self._capability:
                await self._hub.set_capability_value(
                    self._capability["deviceId"],
                    self._capability["quietModeCapabilityId"],
                    "0",
                )

            FANModes = self._modelInfos["fanModes"]
            for mode in FANModes:
                if FANModes[mode] == fan_mode:
                    await self._hub.set_capability_value(
                        self._capability["deviceId"],
                        self._capability["fanModeCapabilityId"],
                        str(mode),
                    )
                    break

    async def async_set_swing_mode(self, swing_mode):
        """Set new target swing operation."""
        if swing_mode == SWING_ON and "swingOnCapabilityId" in self._capability:
            await self._hub.set_capability_value(
                self._capability["deviceId"],
                self._capability["swingOnCapabilityId"],
                "1",
            )
        elif "swingModeCapabilityId" in self._capability:
            if "swingOnCapabilityId" in self._capability:
                await self._hub.set_capability_value(
                    self._capability["deviceId"],
                    self._capability["swingOnCapabilityId"],
                    "0",
                )

            SwingModes = self._modelInfos["swingModes"]
            for mode in SwingModes:
                if SwingModes[mode] == swing_mode:
                    await self._hub.set_capability_value(
                        self._capability["deviceId"],
                        self._capability["swingModeCapabilityId"],
                        str(mode),
                    )
                    break
