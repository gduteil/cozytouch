"""Climate entities Atlantic Cozytouch integration."""

from __future__ import annotations

import logging

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.components.climate.const import (
    PRESET_ACTIVITY,
    PRESET_AWAY,
    PRESET_BOOST,
    PRESET_ECO,
    PRESET_NONE,
    SWING_ON,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SERVICE_OFF, narrowed_modes
from .hub import CozytouchConfigEntry, Hub, add_capability_entities
from .infos import CapabilityType
from .sensor import CozytouchSensor

_LOGGER = logging.getLogger(__name__)

FAN_QUIET = "quiet"

# `supportedSystemOperatingMode`, the bitmask of the HVAC modes the unit was
# built with. See docs/decisions.md.
SUPPORTED_HVAC_MODES_CAPABILITY_ID = 100022


def _bound(entity, coolKey, key) -> float | None:
    """The setpoint bound in force : the cooling one while cooling, if any."""
    if (
        entity._attr_hvac_mode in (HVACMode.COOL, HVACMode.DRY, HVACMode.AUTO)
        and coolKey in entity._capability
    ):
        key = coolKey
    elif key not in entity._capability:
        return None
    return float(
        entity.coordinator.get_capability_value(getattr(entity._capability, key))
    )


def _read_mode(entity, overrideKey, override, modeKey, tableKey) -> str | None:
    """The fan or swing mode reported, the on/off override winning."""
    capability = entity._capability
    get = entity.coordinator.get_capability_value
    if overrideKey in capability and int(get(getattr(capability, overrideKey))):
        return override
    if modeKey in capability:
        value = int(get(getattr(capability, modeKey)))
        return getattr(entity._modelInfos, tableKey).get(value)
    return None


PRESET_BASIC = "basic"
PRESET_PROG = "prog"
PRESET_OVERRIDE = "override"

# The effective mode capability uses the same value scale as the requested mode,
# so it is read through the model's HVACModes and then translated. HVACMode.AUTO
# has no HVACAction counterpart on purpose: a system in auto is really heating,
# cooling or idle, and guessing which would be worse than reporting nothing.
HVAC_ACTIONS = {
    HVACMode.OFF: HVACAction.OFF,
    HVACMode.COOL: HVACAction.COOLING,
    HVACMode.HEAT: HVACAction.HEATING,
    HVACMode.DRY: HVACAction.DRYING,
    HVACMode.FAN_ONLY: HVACAction.FAN,
}


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
        {CapabilityType.CLIMATE: CozytouchClimate},
    )


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
        capabilityId = capability.capabilityId
        super().__init__(
            coordinator=coordinator,
            capability=capability,
            config_title=config_title,
            config_uniq_id=config_uniq_id,
            attr_uniq_id=f"{DOMAIN}_{config_uniq_id}_climate_{capabilityId!s}",
            name=name,
            translation_key=name,
        )

        self._modelInfos = self.coordinator.get_model_infos()

        self._native_value = 0
        self._current_value = None
        self._attr_native_step = 0.5
        # The device states its own setpoint granularity, so prefer it over the
        # hardcoded half degree when it reports one
        stepId = self._capability.get("stepCapabilityId", None)
        if stepId:
            step = self.coordinator.get_capability_value(stepId)
            if step is not None and float(step) > 0:
                self._attr_native_step = float(step)

        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_min_temp = 0
        self._attr_max_temp = 30
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TURN_ON
        )

        self._attr_hvac_modes = list(
            narrowed_modes(
                self._modelInfos.HVACModes,
                self.coordinator.get_capability_value(
                    SUPPORTED_HVAC_MODES_CAPABILITY_ID, None
                ),
            ).values()
        )
        self._attr_hvac_mode = HVACMode.OFF

        # Fan modes
        if "fanModes" in self._modelInfos and "fanModeCapabilityId" in self._capability:
            self._attr_fan_modes = self._configure_modes(
                ClimateEntityFeature.FAN_MODE,
                self._modelInfos.fanModes,
                "quietModeCapabilityId",
                FAN_QUIET,
            )
            if self._attr_fan_modes:
                self._attr_fan_mode = self._attr_fan_modes[0]

        # Swing modes
        if (
            "swingModes" in self._modelInfos
            and "swingModeCapabilityId" in self._capability
        ):
            self._attr_swing_modes = self._configure_modes(
                ClimateEntityFeature.SWING_MODE,
                self._modelInfos.swingModes,
                "swingOnCapabilityId",
                SWING_ON,
            )
            if self._attr_swing_modes:
                self._attr_swing_mode = self._attr_swing_modes[0]

        # Presets
        self._configure_presets()

    def _configure_modes(self, feature, table, extraKey, extra) -> list[str]:
        self._attr_supported_features |= feature
        modes = list(table.values())
        if extraKey in self._capability:
            modes.append(extra)
        return modes

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

        # Away is shown, not chosen : it is listed while an absence is under
        # way, and the switch or the service sets it. See docs/decisions.md.
        self._presets_at_home = list(self._attr_preset_modes)
        if self.coordinator.reports_absence():
            self._attr_supported_features |= ClimateEntityFeature.PRESET_MODE
            if not self._presets_at_home:
                self._presets_at_home = [PRESET_NONE]
                self._attr_preset_modes = [PRESET_NONE]
                self._attr_preset_mode = PRESET_NONE

    @callback
    def _handle_coordinator_update(self) -> None:  # noqa: C901
        """Update the values from the hub.

        Over the complexity ceiling because a climate entity is the one place
        every capability the model wired up has to be read back: each block
        here is one optional feature, guarded by whether the device reported
        the id behind it.
        """
        # HVAC Mode
        HVACModes = self._modelInfos.HVACModes
        currentMode = int(
            self.coordinator.get_capability_value(self._capability.capabilityId)
        )
        if currentMode in HVACModes:
            self._attr_hvac_mode = HVACModes[currentMode]

        # Effective mode, which can differ from the requested one: on a zoned
        # install only the master picks the mode, so a slave keeps its own
        # request here while actually running whatever the master imposes.
        actionId = self._capability.get("hvacActionCapabilityId", None)
        if actionId:
            actionRaw = self.coordinator.get_capability_value(actionId)
            if actionRaw is not None:
                actionMode = HVACModes.get(int(actionRaw), None)
                self._attr_hvac_action = HVAC_ACTIONS.get(actionMode)

        # Which mode is running is not whether the element is drawing: a
        # radiator that has reached its setpoint stays on, and idles.
        activeId = self._capability.get("heatingActiveCapabilityId", None)
        if activeId and self._attr_hvac_action == HVACAction.HEATING:
            activeRaw = self.coordinator.get_capability_value(activeId)
            if activeRaw is not None and int(activeRaw) == 0:
                self._attr_hvac_action = HVACAction.IDLE

        # Air circulation reads back as mode 0 on the effective mode capability,
        # which would otherwise be reported as "off" while the unit blows air
        if self._air_circulation_active():
            self._attr_hvac_action = HVACAction.FAN

        # An absence stops an air conditioner and leaves its mode as it was,
        # so the mode alone would read as running. See docs/decisions.md.
        if (
            self._attr_hvac_action is not None
            and self.coordinator.absence_under_way()
            and self.coordinator.is_air_conditioning()
        ):
            self._attr_hvac_action = HVACAction.OFF

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
                    self._capability.targetCoolCapabilityId
                )
            )
        else:
            self._native_value = float(
                self.coordinator.get_capability_value(
                    self._capability.targetCapabilityId
                )
            )

        # Current value
        currentValueId = self._capability.get("currentValueCapabilityId", None)
        if currentValueId:
            self._current_value = (
                float(self.coordinator.get_capability_value(currentValueId))
                if self._ambient_temperature_is_available()
                else None
            )

        lowest = _bound(self, "lowestCoolValueCapabilityId", "lowestValueCapabilityId")
        if lowest is not None:
            self._attr_min_temp = lowest

        highest = _bound(
            self, "highestCoolValueCapabilityId", "highestValueCapabilityId"
        )
        if highest is not None:
            self._attr_max_temp = highest

        fanMode = _read_mode(
            self, "quietModeCapabilityId", FAN_QUIET, "fanModeCapabilityId", "fanModes"
        )
        if fanMode is not None:
            self._attr_fan_mode = fanMode

        swingMode = _read_mode(
            self, "swingOnCapabilityId", SWING_ON, "swingModeCapabilityId", "swingModes"
        )
        if swingMode is not None:
            self._attr_swing_mode = swingMode

        # Presets
        activityModeValue, ecoModeValue, boostModeValue = 0, 0, 0
        if "activityCapabilityId" in self._capability:
            activityModeValue = int(
                self.coordinator.get_capability_value(
                    self._capability.activityCapabilityId
                )
            )
            if activityModeValue == 1:
                self._attr_preset_mode = PRESET_ACTIVITY
            else:
                self._attr_preset_mode = PRESET_NONE

        if "ecoCapabilityId" in self._capability:
            ecoModeValue = int(
                self.coordinator.get_capability_value(
                    self._capability.ecoCapabilityId
                )
            )
            if ecoModeValue == 1:
                self._attr_preset_mode = PRESET_ECO
            elif activityModeValue == 0:
                self._attr_preset_mode = PRESET_NONE

        if "boostCapabilityId" in self._capability:
            boostModeValue = int(
                self.coordinator.get_capability_value(
                    self._capability.boostCapabilityId
                )
            )
            if boostModeValue == 1:
                self._attr_preset_mode = PRESET_BOOST
            elif activityModeValue == 0 and ecoModeValue == 0:
                self._attr_preset_mode = PRESET_NONE

        if "progCapabilityId" in self._capability:
            progModeValue = int(
                self.coordinator.get_capability_value(
                    self._capability.progCapabilityId
                )
            )
            if progModeValue == 0:
                if PRESET_NONE not in self._attr_preset_modes :
                    self._attr_preset_mode = PRESET_BASIC
            elif "progOverrideCapabilityId" in self._capability:
                # In prog mode we can also be in override mode
                progOverrideValue = int(
                    self.coordinator.get_capability_value(
                        self._capability.progOverrideCapabilityId
                    )
                )
                if progOverrideValue == 1:
                    self._attr_preset_mode = PRESET_OVERRIDE
                else:
                    self._attr_preset_mode = PRESET_PROG
            else:
                self._attr_preset_mode = PRESET_PROG

        if self._presets_at_home and self.coordinator.reports_absence():
            if self.coordinator.absence_under_way():
                self._attr_preset_modes = [*self._presets_at_home, PRESET_AWAY]
                self._attr_preset_mode = PRESET_AWAY
            else:
                self._attr_preset_modes = list(self._presets_at_home)
                if self._attr_preset_mode == PRESET_AWAY:
                    self._attr_preset_mode = self._presets_at_home[0]

        self.async_write_ha_state()

    async def _write_mode(self, mode, overrideKey, override, modeKey, tableKey):
        if mode == override and overrideKey in self._capability:
            await self.coordinator.set_capability_value(
                getattr(self._capability, overrideKey), "1"
            )
        elif modeKey in self._capability:
            if overrideKey in self._capability:
                await self.coordinator.set_capability_value(
                    getattr(self._capability, overrideKey), "0"
                )
            for value, name in getattr(self._modelInfos, tableKey).items():
                if name == mode:
                    await self.coordinator.set_capability_value(
                        getattr(self._capability, modeKey), str(value)
                    )
                    break

        await self.coordinator.async_request_refresh()

    def _ambient_temperature_is_available(self) -> bool:
        """Whether the ambient reading means anything right now.

        True where the device does not say, which is every device that does
        not report the capability. See docs/decisions.md.
        """
        availableId = self._capability.get("currentAvailableCapabilityId", None)
        if not availableId:
            return True

        value = self.coordinator.get_capability_value(availableId)
        return value is None or str(value) != "0"

    @property
    def current_temperature(self):
        """Return current temperature."""
        return self._current_value

    @property
    def target_temperature(self):
        """Return target temperature."""
        return self._native_value

    def _air_circulation_active(self) -> bool:
        """Tell whether air circulation is currently running."""
        capabilityId = self._capability.get("airCirculationCapabilityId", None)
        if not capabilityId:
            return False

        value = self.coordinator.get_capability_value(capabilityId)
        return value is not None and int(value) == 1

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        temperature = kwargs.get("temperature")
        if temperature is not None:
            # If we are in "Prog mode", we need to switch to override before
            # changing the temperature
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
                    self._capability.targetCoolCapabilityId,
                    str(temperature),
                )
            else:
                await self.coordinator.set_capability_value(
                    self._capability.targetCapabilityId,
                    str(temperature),
                )

            await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set hvac mode, on the room or on the system as the app does.

        A mode is the whole system's -- one outdoor unit runs one service --
        and off is the room's own. So a mode goes to 102020, which every room
        of the system then follows, and off goes to the room's own service.
        A room that was off is switched back on beside the mode, which the app
        needs two gestures for. See docs/decisions.md.
        """
        HVACModes = self._modelInfos.HVACModes
        for mode in HVACModes:
            if HVACModes[mode] != hvac_mode:
                continue

            room = self._capability.capabilityId
            system = self._capability.get("systemServiceCapabilityId")

            if system is None or hvac_mode == HVACMode.OFF:
                await self.coordinator.set_capability_value(room, str(mode))
            else:
                await self.coordinator.set_capability_value(system, str(mode))
                if self.coordinator.get_capability_value(room) == SERVICE_OFF:
                    await self.coordinator.set_capability_value(room, str(mode))

            await self.coordinator.async_request_refresh()
            break

    async def async_set_fan_mode(self, fan_mode) -> None:
        """Set new target fan mode."""
        await self._write_mode(
            fan_mode,
            "quietModeCapabilityId",
            FAN_QUIET,
            "fanModeCapabilityId",
            "fanModes",
        )

    async def async_set_swing_mode(self, swing_mode):
        """Set new target swing operation."""
        await self._write_mode(
            swing_mode,
            "swingOnCapabilityId",
            SWING_ON,
            "swingModeCapabilityId",
            "swingModes",
        )

    async def async_set_preset_mode(self, preset_mode):
        """Set new target preset mode."""
        if preset_mode == PRESET_AWAY:
            return

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
