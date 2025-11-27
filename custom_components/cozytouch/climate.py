"""Climate entities Atlantic Cozytouch integration."""

from __future__ import annotations

import logging

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    HVACAction,
)
from homeassistant.components.climate.const import (
    PRESET_ACTIVITY,
    PRESET_BOOST,
    PRESET_ECO,
    PRESET_NONE,
    SWING_ON,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .hub import Hub
from .sensor import CozytouchSensor

_LOGGER = logging.getLogger(__name__)

FAN_QUIET = "quiet"

PRESET_BASIC = "basic"
PRESET_PROG = "prog"
PRESET_OVERRIDE = "override"


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
    capabilities = hub.get_capabilities_for_device()
    for capability in capabilities:
        if capability["type"] == "climate":
            climates.append(
                CozytouchClimate(
                    coordinator=hub,
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
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
        coordinator: Hub,
        name: str | None = None,
    ) -> None:
        """Initialize a climate entity."""
        capabilityId = capability["capabilityId"]
        super().__init__(
            coordinator=coordinator,
            capability=capability,
            config_title=config_title,
            config_uniq_id=config_uniq_id,
            attr_uniq_id=f"{DOMAIN}_{config_uniq_id}_climate_{str(capabilityId)}",
            name=name,
            translation_key=name,
        )

        self._modelInfos = self.coordinator.get_model_infos()

        self._native_value = 0
        self._current_value = None
        self._attr_native_step = 0.5
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_min_temp = 0
        self._attr_max_temp = 30
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TURN_ON
        )

        self._attr_hvac_modes = list(self._modelInfos["HVACModes"].values())
        self._attr_hvac_mode = HVACMode.OFF

        # Fan modes
        if "fanModes" in self._modelInfos and "fanModeCapabilityId" in self._capability:
            self._configure_fan_modes()

        # Swing modes
        if (
            "swingModes" in self._modelInfos
            and "swingModeCapabilityId" in self._capability
        ):
            self._configure_swing_modes()

        # Presets
        self._configure_presets()

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

    def _configure_presets(self):
        self._attr_preset_modes = []
        if (
            "progCapabilityId" in self._capability
            or "activityCapabilityId" in self._capability
            or "ecoCapabilityId" in self._capability
            or "boostCapabilityId" in self._capability
        ):
            self._attr_supported_features |= ClimateEntityFeature.PRESET_MODE

        if (
            "activityCapabilityId" in self._capability
            or "ecoCapabilityId" in self._capability
            or "boostCapabilityId" in self._capability
        ):
            self._attr_preset_modes.append(PRESET_NONE)
            self._attr_preset_mode = PRESET_NONE

        if "activityCapabilityId" in self._capability:
            self._attr_preset_modes.append(PRESET_ACTIVITY)

        if "ecoCapabilityId" in self._capability:
            self._attr_preset_modes.append(PRESET_ECO)

        if "boostCapabilityId" in self._capability:
            self._attr_preset_modes.append(PRESET_BOOST)

        if "progCapabilityId" in self._capability:
            self._attr_preset_modes.append(PRESET_BASIC)
            self._attr_preset_modes.append(PRESET_PROG)

            if "progOverrideCapabilityId" in self._capability:
                self._attr_preset_modes.append(PRESET_OVERRIDE)

            if PRESET_NONE not in self._attr_preset_modes :
                self._attr_preset_mode = PRESET_BASIC

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update the values from the hub."""

        # HVAC Mode
        HVACModes = self._modelInfos["HVACModes"]
        currentMode = int(
            self.coordinator.get_capability_value(self._capability["capabilityId"])
        )
        if currentMode in HVACModes:
            self._attr_hvac_mode = HVACModes[currentMode]

        # Target value
        if self._attr_hvac_mode in (
            HVACMode.OFF,
            HVACMode.FAN_ONLY
        ):
            self._native_value = None
        elif (
            self._attr_hvac_mode in (
                HVACMode.COOL,
                HVACMode.DRY )
            and "targetCoolCapabilityId" in self._capability
        ):
            self._native_value = float(
                self.coordinator.get_capability_value(
                    self._capability["targetCoolCapabilityId"]
                )
            )
        else:
            self._native_value = float(
                self.coordinator.get_capability_value(
                    self._capability["targetCapabilityId"]
                )
            )

        # Current value
        currentValueId = self._capability.get("currentValueCapabilityId", None)
        if currentValueId:
            self._current_value = float(
                self.coordinator.get_capability_value(currentValueId)
            )

        # Lowest adjustment value
        if (
            self._attr_hvac_mode in (
                HVACMode.COOL,
                HVACMode.DRY,
                HVACMode.AUTO )
            and "lowestCoolValueCapabilityId" in self._capability
        ):
            lowestValueId = self._capability.get("lowestCoolValueCapabilityId", None)
            self._attr_min_temp = float(
                self.coordinator.get_capability_value(lowestValueId)
            )
        elif "lowestValueCapabilityId" in self._capability:
            lowestValueId = self._capability.get("lowestValueCapabilityId", None)
            self._attr_min_temp = float(
                self.coordinator.get_capability_value(lowestValueId)
            )

        # Highest adjustment value
        if (
            self._attr_hvac_mode in (
                HVACMode.COOL,
                HVACMode.DRY,
                HVACMode.AUTO )
            and "highestCoolValueCapabilityId" in self._capability
        ):
            highestValueId = self._capability["highestCoolValueCapabilityId"]
            self._attr_max_temp = float(
                self.coordinator.get_capability_value(highestValueId)
            )
        elif "highestValueCapabilityId" in self._capability:
            highestValueId = self._capability["highestValueCapabilityId"]
            self._attr_max_temp = float(
                self.coordinator.get_capability_value(highestValueId)
            )

        # FAN mode
        if "quietModeCapabilityId" in self._capability and int(
            self.coordinator.get_capability_value(
                self._capability["quietModeCapabilityId"]
            )
        ):
            self._attr_fan_mode = FAN_QUIET
        elif "fanModeCapabilityId" in self._capability:
            fanModes = self._modelInfos["fanModes"]
            fanModeValue = int(
                self.coordinator.get_capability_value(
                    self._capability["fanModeCapabilityId"]
                )
            )
            if fanModeValue in fanModes:
                self._attr_fan_mode = fanModes[fanModeValue]

        # Swing mode
        if "swingOnCapabilityId" in self._capability and int(
            self.coordinator.get_capability_value(
                self._capability["swingOnCapabilityId"]
            )
        ):
            self._attr_swing_mode = SWING_ON
        elif "swingModeCapabilityId" in self._capability:
            swingModes = self._modelInfos["swingModes"]
            swingModeValue = int(
                self.coordinator.get_capability_value(
                    self._capability["swingModeCapabilityId"]
                )
            )
            if swingModeValue in swingModes:
                self._attr_swing_mode = swingModes[swingModeValue]

        # Presets
        activityModeValue, ecoModeValue, boostModeValue = 0, 0, 0
        if "activityCapabilityId" in self._capability:
            activityModeValue = int(
                self.coordinator.get_capability_value(
                    self._capability["activityCapabilityId"]
                )
            )
            if activityModeValue == 1:
                self._attr_preset_mode = PRESET_ACTIVITY
            else:
                self._attr_preset_mode = PRESET_NONE

        if "ecoCapabilityId" in self._capability:
            ecoModeValue = int(
                self.coordinator.get_capability_value(
                    self._capability["ecoCapabilityId"]
                )
            )
            if ecoModeValue == 1:
                self._attr_preset_mode = PRESET_ECO
            elif activityModeValue == 0:
                self._attr_preset_mode = PRESET_NONE

        if "boostCapabilityId" in self._capability:
            boostModeValue = int(
                self.coordinator.get_capability_value(
                    self._capability["boostCapabilityId"]
                )
            )
            if boostModeValue == 1:
                self._attr_preset_mode = PRESET_BOOST
            elif activityModeValue == 0 and ecoModeValue == 0:
                self._attr_preset_mode = PRESET_NONE

        if "progCapabilityId" in self._capability:
            progModeValue = int(
                self.coordinator.get_capability_value(
                    self._capability["progCapabilityId"]
                )
            )
            if progModeValue == 0:
                if PRESET_NONE not in self._attr_preset_modes :
                    self._attr_preset_mode = PRESET_BASIC
            elif "progOverrideCapabilityId" in self._capability:
                # In prog mode we can also be in override mode
                progOverrideValue = int(
                    self.coordinator.get_capability_value(
                        self._capability["progOverrideCapabilityId"]
                    )
                )
                if progOverrideValue == 1:
                    self._attr_preset_mode = PRESET_OVERRIDE
                else:
                    self._attr_preset_mode = PRESET_PROG
            else:
                self._attr_preset_mode = PRESET_PROG

        self.async_write_ha_state()

    @property
    def current_temperature(self):
        """Return current temperature."""
        return self._current_value

    @property
    def target_temperature(self):
        """Return target temperature."""
        return self._native_value
    
    @property
    def extra_state_attributes(self):
        """Return the computed target temperature."""
        if "setpointTemperatureId" in self._capability:
            effective_temp = self.coordinator.get_capability_value(
                self._capability["setpointTemperatureId"]
            )
            if effective_temp is not None:
                return {
                    "temperature_setpoint": float(effective_temp),
                }
        return None
        
    @property
    def hvac_action(self):
        """Return the current HVAC action."""
        if self._attr_hvac_mode == HVACMode.OFF:
            return HVACAction.OFF

        # Get effective target temperature
        setpoint_temp = None
        if "setpointTemperatureId" in self._capability:
            setpoint_temp_value = self.coordinator.get_capability_value(
                self._capability["setpointTemperatureId"]
            )
            if setpoint_temp_value is not None:
                setpoint_temp = float(setpoint_temp_value)
        
        # If no setpoint temp, fall back to target temperature
        if setpoint_temp is None:
            setpoint_temp = self._native_value
        
        # Determine action based on current vs target temperature
        if self._current_value is not None and setpoint_temp is not None:
            if self._current_value < setpoint_temp:
                return HVACAction.HEATING
        
        return HVACAction.IDLE
    
    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        temperature = kwargs.get("temperature")
        if temperature is not None:
            # If we are in "Prog mode", we need to switch to override before changing the temperature
            if (
                hasattr(self, "_attr_preset_mode")
                and self._attr_preset_mode == PRESET_PROG
            ):
                await self.async_set_preset_mode(PRESET_OVERRIDE)

            if (
                self._attr_hvac_mode in (
                    HVACMode.COOL,
                    HVACMode.DRY )
                and "targetCoolCapabilityId" in self._capability
            ):
                await self.coordinator.set_capability_value(
                    self._capability["targetCoolCapabilityId"],
                    str(temperature),
                )
            else:
                await self.coordinator.set_capability_value(
                    self._capability["targetCapabilityId"],
                    str(temperature),
                )

            await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set hvac mode."""
        HVACModes = self._modelInfos["HVACModes"]
        for mode in HVACModes:
            if HVACModes[mode] == hvac_mode:
                await self.coordinator.set_capability_value(
                    self._capability["capabilityId"],
                    str(mode),
                )
                await self.coordinator.async_request_refresh()
                break

    async def async_set_fan_mode(self, fan_mode) -> None:
        """Set new target fan mode."""
        if fan_mode == FAN_QUIET and "quietModeCapabilityId" in self._capability:
            await self.coordinator.set_capability_value(
                self._capability["quietModeCapabilityId"],
                "1",
            )
        elif "fanModeCapabilityId" in self._capability:
            if "quietModeCapabilityId" in self._capability:
                await self.coordinator.set_capability_value(
                    self._capability["quietModeCapabilityId"],
                    "0",
                )

            FANModes = self._modelInfos["fanModes"]
            for mode in FANModes:
                if FANModes[mode] == fan_mode:
                    await self.coordinator.set_capability_value(
                        self._capability["fanModeCapabilityId"],
                        str(mode),
                    )
                    break

        await self.coordinator.async_request_refresh()

    async def async_set_swing_mode(self, swing_mode):
        """Set new target swing operation."""
        if swing_mode == SWING_ON and "swingOnCapabilityId" in self._capability:
            await self.coordinator.set_capability_value(
                self._capability["swingOnCapabilityId"],
                "1",
            )
        elif "swingModeCapabilityId" in self._capability:
            if "swingOnCapabilityId" in self._capability:
                await self.coordinator.set_capability_value(
                    self._capability["swingOnCapabilityId"],
                    "0",
                )

            SwingModes = self._modelInfos["swingModes"]
            for mode in SwingModes:
                if SwingModes[mode] == swing_mode:
                    await self.coordinator.set_capability_value(
                        self._capability["swingModeCapabilityId"],
                        str(mode),
                    )
                    break

        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode):
        """Set new target preset mode."""
        activityCapabilityId = self._capability.get("activityCapabilityId", None)
        ecoCapabilityId = self._capability.get("ecoCapabilityId", None)
        boostCapabilityId = self._capability.get("boostCapabilityId", None)
        progCapabilityId = self._capability.get("progCapabilityId", None)
        progOverrideCapabilityId = self._capability.get(
            "progOverrideCapabilityId", None
        )

        if activityCapabilityId:
            if preset_mode == PRESET_ACTIVITY:
                await self.coordinator.set_capability_value(activityCapabilityId, "1")
            elif preset_mode == PRESET_NONE:
                await self.coordinator.set_capability_value(activityCapabilityId, "0")

        if ecoCapabilityId:
            if preset_mode == PRESET_ECO:
                await self.coordinator.set_capability_value(ecoCapabilityId, "1")
            elif preset_mode in (PRESET_ACTIVITY, PRESET_NONE):
                await self.coordinator.set_capability_value(ecoCapabilityId, "0")
                # NOTE: PRESET_BOOST mode automatically disable PRESET_ECO mode

        if boostCapabilityId:
            if preset_mode == PRESET_BOOST:
                await self.coordinator.set_capability_value(boostCapabilityId, "1")
            elif preset_mode in (PRESET_ACTIVITY, PRESET_NONE):
                await self.coordinator.set_capability_value(boostCapabilityId, "0")
                # NOTE: PRESET_ECO mode automatically disable PRESET_BOOST mode

        if progCapabilityId:
            if preset_mode == PRESET_BASIC:
                await self.coordinator.set_capability_value(progCapabilityId, "0")

            elif preset_mode == PRESET_PROG:
                await self.coordinator.set_capability_value(progCapabilityId, "1")

            if progOverrideCapabilityId:
                progOverrideTimeCapabilityId = self._capability.get(
                    "progOverrideTimeCapabilityId", None
                )
                progOverrideTotalTimeCapabilityId = self._capability.get(
                    "progOverrideTotalTimeCapabilityId", None
                )

                if preset_mode == PRESET_OVERRIDE:
                    if (
                        progOverrideTimeCapabilityId
                        and progOverrideTotalTimeCapabilityId
                    ):
                        totalTime = self.coordinator.get_capability_value(
                            progOverrideTotalTimeCapabilityId
                        )
                        await self.coordinator.set_capability_value(
                            progOverrideTotalTimeCapabilityId, totalTime
                        )

                    await self.coordinator.set_capability_value(
                        progOverrideCapabilityId, "1"
                    )

                else:
                    if progOverrideTimeCapabilityId:
                        await self.coordinator.set_capability_value(
                            progOverrideTimeCapabilityId, "0"
                        )

                    await self.coordinator.set_capability_value(
                        progOverrideCapabilityId, "0"
                    )
        self._attr_preset_mode = preset_mode
        await self.coordinator.async_request_refresh()
