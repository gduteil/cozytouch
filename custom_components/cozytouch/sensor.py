"""Sensors for Atlantic Cozytouch integration."""

from __future__ import annotations

import datetime
import json
import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfPressure,
    UnitOfSoundPressure,
    UnitOfTemperature,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CozytouchCapabilityVariableType
from .hub import Hub

_LOGGER = logging.getLogger(__name__)


# config flow setup
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Modern (thru config entry) sensors setup."""
    _LOGGER.debug("%s: setting up sensor plateform", config_entry.title)
    # Retrieve the serial reader object
    # Retrieve the hub object
    try:
        hub = hass.data[DOMAIN][config_entry.entry_id]
    except KeyError:
        _LOGGER.error(
            "%s: can not init sensors: failed to get the hub object",
            config_entry.title,
        )
        return

    # Init sensors
    sensors = []
    capabilities = hub.get_capabilities_for_device(config_entry.data["deviceId"])
    for capability in capabilities:
        if capability["type"] in ("string", "int"):
            # Use a CozytouchSensor for integers
            sensors.append(
                CozytouchSensor(
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    coordinator=hub,
                )
            )
        elif capability["type"] == "temperature":
            sensors.append(
                CozytouchUnitSensor(
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    coordinator=hub,
                    device_class=SensorDeviceClass.TEMPERATURE,
                    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                )
            )
        elif capability["type"] == "pressure":
            sensors.append(
                CozytouchUnitSensor(
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    coordinator=hub,
                    device_class=SensorDeviceClass.PRESSURE,
                    native_unit_of_measurement=UnitOfPressure.BAR,
                )
            )
        elif capability["type"] == "away_mode_timestamps":
            sensors.append(
                CozytouchAwayModeTimestampSensor(
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    attr_uniq_id=config_entry.entry_id + "_0",
                    coordinator=hub,
                    name=capability["name_0"],
                    icon=capability.get("icon_0", None),
                    separator=",",
                    timestamp_index=0,
                )
            )

            sensors.append(
                CozytouchAwayModeTimestampSensor(
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    attr_uniq_id=config_entry.entry_id + "_1",
                    coordinator=hub,
                    name=capability["name_1"],
                    icon=capability.get("icon_1", None),
                    separator=",",
                    timestamp_index=1,
                )
            )
        elif capability["type"] in ("switch", "binary"):
            sensors.append(
                CozytouchBinarySensor(
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    coordinator=hub,
                )
            )
        elif capability["type"] == "away_mode_switch":
            sensors.append(
                CozytouchAwayModeSensor(
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    coordinator=hub,
                )
            )
        elif capability["type"] == "signal":
            sensors.append(
                CozytouchUnitSensor(
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    coordinator=hub,
                    device_class=SensorDeviceClass.SIGNAL_STRENGTH,
                    native_unit_of_measurement=UnitOfSoundPressure.DECIBEL,
                )
            )
        elif capability["type"] == "power":
            native_unit_of_measurement = capability.get(
                "displayed_unit_of_measurement", UnitOfPower.WATT
            )

            display_factor = 1.0
            if native_unit_of_measurement == UnitOfPower.KILO_WATT:
                display_factor = 0.001

            sensors.append(
                CozytouchUnitSensor(
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    coordinator=hub,
                    device_class=SensorDeviceClass.POWER,
                    native_unit_of_measurement=capability.get(
                        "displayed_unit_of_measurement", UnitOfPower.WATT
                    ),
                    displayed_unit_of_measurement=capability.get(
                        "displayed_unit_of_measurement", None
                    ),
                )
            )
        elif capability["type"] == "energy":
            native_unit_of_measurement = capability.get(
                "displayed_unit_of_measurement", UnitOfEnergy.WATT_HOUR
            )

            display_factor = 1.0
            if native_unit_of_measurement == UnitOfEnergy.KILO_WATT_HOUR:
                display_factor = 0.001

            sensors.append(
                CozytouchUnitSensor(
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    coordinator=hub,
                    device_class=SensorDeviceClass.ENERGY,
                    state_class=SensorStateClass.TOTAL_INCREASING,
                    native_unit_of_measurement=native_unit_of_measurement,
                    display_factor=display_factor,
                )
            )
        elif capability["type"] == "volume":
            sensors.append(
                CozytouchUnitSensor(
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    coordinator=hub,
                    device_class=SensorDeviceClass.VOLUME,
                    native_unit_of_measurement=UnitOfVolume.LITERS,
                )
            )
        elif capability["type"] == "water_consumption":
            sensors.append(
                CozytouchUnitSensor(
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    coordinator=hub,
                    device_class=SensorDeviceClass.WATER,
                    native_unit_of_measurement=UnitOfVolume.LITERS,
                    state_class=SensorStateClass.TOTAL_INCREASING,
                )
            )
        elif capability["type"] == "percentage":
            sensors.append(
                CozytouchUnitSensor(
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    coordinator=hub,
                    device_class=SensorDeviceClass.BATTERY,
                    native_unit_of_measurement=PERCENTAGE,
                )
            )
        elif capability["type"] == "time":
            sensors.append(
                CozytouchTimeSensor(
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    coordinator=hub,
                )
            )

        elif capability["type"] == "timezone":
            sensors.append(
                CozytouchTimezoneSensor(
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    coordinator=hub,
                )
            )
        elif capability["type"] == "prog":
            sensors.append(
                CozytouchProgSensor(
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    coordinator=hub,
                )
            )
        elif capability["type"] == "progtime":
            sensors.append(
                CozytouchProgTimeSensor(
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    coordinator=hub,
                )
            )
        elif capability["type"] == "climate":
            sensors.append(
                CozytouchSensor(
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    coordinator=hub,
                )
            )

    # Add the entities to HA
    if len(sensors) > 0:
        async_add_entities(sensors, True)


class CozytouchSensor(SensorEntity, CoordinatorEntity):
    """Common class for sensors."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: Hub,
        capability,
        config_title: str,
        config_uniq_id: str,
        attr_uniq_id: str | None = None,
        name: str | None = None,
        translation_key: str | None = None,
        icon: str | None = None,
        value_type: CozytouchCapabilityVariableType | None = None,
    ) -> None:
        """Initialize a sensor."""
        super().__init__(coordinator)

        self._capability = capability
        self._config_title = config_title
        self._config_uniq_id = config_uniq_id
        self._last_value: str | None = None
        self._device_uniq_id = config_uniq_id

        if value_type:
            self._value_type = value_type
        elif "value_type" in self._capability:
            self._value_type = self._capability["value_type"]
        else:
            self._value_type = None

        if attr_uniq_id:
            self._attr_unique_id = attr_uniq_id
        else:
            capabilityId = self._capability["capabilityId"]
            self._attr_unique_id = f"{DOMAIN}_{config_uniq_id}_{str(capabilityId)}"

        self.entity_description = SensorEntityDescription(
            key="capability_" + str(capability["capabilityId"]),
            name=name if name else self._capability["name"],
        )

        self._attr_translation_key = (
            translation_key if translation_key else self.entity_description.name
        )

        if "category" in self._capability:
            if self._capability["category"] == "diag":
                self._attr_entity_category = EntityCategory.DIAGNOSTIC
            elif self._capability["category"] == "config":
                self._attr_entity_category = EntityCategory.CONFIG
            else:
                self._attr_entity_category = None

        if icon:
            self._attr_icon = icon
        elif "icon" in self._capability:
            self._attr_icon = self._capability["icon"]

    def get_value(self):
        """Retrieve value from hub."""
        if self._value_type == CozytouchCapabilityVariableType.ARRAY:
            return "array"

        try:
            value = self.coordinator.get_capability_value(
                self._capability["capabilityId"]
            )
            if value is None:
                return None
            if self._value_type == CozytouchCapabilityVariableType.BOOL:
                return bool(value)
            if self._value_type == CozytouchCapabilityVariableType.FLOAT:
                return float(value)
            if self._value_type == CozytouchCapabilityVariableType.INT:
                return int(value)
        except ValueError:
            return value

        return value

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        modelInfos = self.coordinator.get_model_infos()
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_uniq_id)},
            manufacturer="Atlantic",
            name=modelInfos["name"],
            model=modelInfos["name"],
            serial_number=self.coordinator.get_serial_number(),
        )

    @property
    def native_value(self):
        """Value of the sensor."""
        return self._last_value

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update the value of the sensor from the hub."""
        # Get last seen value from controller
        value = self.get_value()
        # _LOGGER.info("%s: update %s (%s)", self._config_title, self._attr_name, value)

        # Handle entity availability
        if value is None:
            if self._attr_available:
                if not self.coordinator.online:
                    _LOGGER.debug(
                        "%s: marking the %s sensor as unavailable: Cozytouch connection lost",
                        self._config_title,
                        self._attr_name,
                    )
                    self._attr_available = False
        elif not self._attr_available:
            _LOGGER.info(
                "%s: marking the %s sensor as available now !",
                self._config_title,
                self._attr_name,
            )
            self._attr_available = True

        # Save value
        self._last_value = value
        self.async_write_ha_state()


class CozytouchAwayModeTimestampSensor(CozytouchSensor):
    """Class for away mode timestamp sensor."""

    def __init__(
        self,
        capability,
        config_title: str,
        config_uniq_id: str,
        coordinator: Hub,
        name: str | None = None,
        icon: str | None = None,
        separator: str | None = None,
        timestamp_index: int | None = None,
        attr_uniq_id: str | None = None,
    ) -> None:
        """Initialize an away mode timestamp Sensor."""
        super().__init__(
            capability=capability,
            config_title=config_title,
            config_uniq_id=config_uniq_id,
            attr_uniq_id=attr_uniq_id,
            coordinator=coordinator,
            name=name,
            icon=icon,
            value_type=CozytouchCapabilityVariableType.STRING,
        )
        self._separator = separator
        self._timestamp_index = timestamp_index

    def get_value(self) -> str:
        """Retrieve value from hub."""
        value = self.coordinator.get_capability_value(self._capability["capabilityId"])
        if value is not None:
            value = value.translate(str.maketrans("", "", "[]"))
            timestamps = value.split(self._separator, 2)
            if len(timestamps) == 2:
                if timestamps[0] != "0" and timestamps[1] != "0":
                    timestamp = int(timestamps[self._timestamp_index])
                    timeOffset = int(
                        self.coordinator.get_capability_value(
                            self._capability["timezoneCapabilityId"]
                        )
                    )
                    ts = datetime.datetime.fromtimestamp(timestamp + timeOffset)

                    # Check if we need to init timestamps in coordinator
                    timestampStart = self.coordinator.get_away_mode_start()
                    timestampEnd = self.coordinator.get_away_mode_end()
                    if timestampStart is None or timestampEnd is None:
                        self.coordinator.away_mode_init(
                            int(timestamps[0]), int(timestamps[1])
                        )

                    return ts.strftime("%H:%M %d/%m/%Y")

                return "Undefined"

        return None


class CozytouchBinarySensor(BinarySensorEntity, CozytouchSensor):
    """Class for binary sensor."""

    def __init__(
        self,
        capability,
        config_title: str,
        config_uniq_id: str,
        coordinator: Hub,
        name: str | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialize a binary Sensor."""
        super().__init__(
            capability=capability,
            config_title=config_title,
            config_uniq_id=config_uniq_id,
            coordinator=coordinator,
            name=name,
            icon=icon,
        )
        self._last_value: False

    @property
    def is_on(self) -> bool:
        """Return last state value."""
        value_on = "1"
        if "value_on" in self._capability:
            value_on = self._capability["value_on"]

        return self._last_value == value_on


class CozytouchAwayModeSensor(CozytouchSensor):
    """Class for away mode sensor."""

    def __init__(
        self,
        capability,
        config_title: str,
        config_uniq_id: str,
        coordinator: Hub,
        name: str | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialize a binary Sensor."""
        super().__init__(
            capability=capability,
            config_title=config_title,
            config_uniq_id=config_uniq_id,
            coordinator=coordinator,
            name=name,
            icon=icon,
        )

    def get_value(self) -> str:
        """Retrieve value from hub."""
        value = self.coordinator.get_capability_value(self._capability["capabilityId"])
        if value is not None:
            strValue = "Unknown"
            if value == self._capability["value_off"]:
                strValue = "Off"
            elif value == self._capability["value_pending"]:
                strValue = "Pending"
            elif value == self._capability["value_on"]:
                strValue = "On"

            return strValue


class CozytouchUnitSensor(CozytouchSensor):
    """Class for unit sensor."""

    def __init__(
        self,
        capability,
        config_title: str,
        config_uniq_id: str,
        coordinator: Hub,
        device_class: SensorDeviceClass,
        native_unit_of_measurement,
        display_factor: float | None = 1.0,
        state_class: SensorStateClass | None = None,
        suggested_precision: int | None = None,
        name: str | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialize an unit Sensor."""
        super().__init__(
            capability=capability,
            config_title=config_title,
            config_uniq_id=config_uniq_id,
            coordinator=coordinator,
            name=name,
            icon=icon,
            value_type=CozytouchCapabilityVariableType.FLOAT,
        )
        self._attr_native_unit_of_measurement = native_unit_of_measurement
        self._attr_suggested_display_precision = suggested_precision
        if device_class:
            self._attr_device_class = device_class

        if state_class:
            self._attr_state_class = state_class

        self.displayed_unit_of_measurement = (
            capability.get("displayed_unit_of_measurement", None),
        )

        self._display_factor = display_factor

    def get_value(self):
        """Retrieve value from hub and convert it if needed."""
        value = super().get_value()
        if self._display_factor != 1.0:
            return float(value) * self._display_factor

        return value

    @property
    def native_value(self) -> float | None:
        """Value of the sensor."""
        if self._last_value:
            try:
                return float(self._last_value)
            except ValueError:
                return 0.0


class CozytouchTimeSensor(CozytouchSensor):
    """Class for time sensor (in minutes)."""

    def __init__(
        self,
        capability,
        config_title: str,
        config_uniq_id: str,
        coordinator: Hub,
        name: str | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialize a time Sensor."""
        super().__init__(
            capability=capability,
            config_title=config_title,
            config_uniq_id=config_uniq_id,
            coordinator=coordinator,
            name=name,
            icon=icon,
        )
        self._last_value: 0

    def get_value(self) -> str:
        """Retrieve value from hub."""
        value = self.coordinator.get_capability_value(self._capability["capabilityId"])
        if value is not None:
            strValue = ""
            days = 0
            remaining = int(value)
            if remaining >= (60 * 24):
                days = int(remaining / (60 * 24))
                remaining -= days * (60 * 24)

            hours = 0
            if remaining >= 60:
                hours = int(remaining / 60)
                remaining -= hours * 60

            minutes = int(remaining)

            if days > 0:
                strValue = str(days) + "d "

            strValue += "%02d:%02d" % (hours, minutes)
            return strValue

        return None


class CozytouchTimezoneSensor(CozytouchSensor):
    """Class for timezone sensor."""

    def __init__(
        self,
        capability,
        config_title: str,
        config_uniq_id: str,
        coordinator: Hub,
        name: str | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialize a time Sensor."""
        super().__init__(
            capability=capability,
            config_title=config_title,
            config_uniq_id=config_uniq_id,
            coordinator=coordinator,
            name=name,
            icon=icon,
        )
        self._last_value: 0

    def get_value(self) -> str:
        """Retrieve value from hub."""
        value = self.coordinator.get_capability_value(self._capability["capabilityId"])
        if value is not None:
            if float(value) > 0:
                strValue = "GMT+%d" % (int(value) / 3600)
            elif float(value) < 0:
                strValue = "GMT-%d" % (abs(int(value)) / 3600)
            else:
                strValue = "GMT"

            return strValue

        return None


class CozytouchProgSensor(CozytouchSensor):
    """Class for Prog sensor."""

    def __init__(
        self,
        capability,
        config_title: str,
        config_uniq_id: str,
        coordinator: Hub,
        name: str | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialize a prog Sensor."""
        super().__init__(
            capability=capability,
            config_title=config_title,
            config_uniq_id=config_uniq_id,
            coordinator=coordinator,
            name=name,
            icon=icon,
        )

    def get_value(self) -> str:
        """Retrieve value from hub."""
        value = self.coordinator.get_capability_value(self._capability["capabilityId"])
        if value is not None:
            progList = json.loads(value)

            strValue = ""
            for prog in progList:
                if len(prog) >= 2 and (prog[0] != 0 or prog[1] != 0):
                    hours = int(prog[0] / 60)
                    minutes = int(prog[0] % 60)

                    if strValue != "":
                        strValue += " / "
                    strValue += "%02d:%02d " % (hours, minutes)
                    strValue += " %g°C" % (prog[1])

            return strValue

        return None


class CozytouchProgTimeSensor(CozytouchSensor):
    """Class for ProgTime sensor."""

    def __init__(
        self,
        capability,
        config_title: str,
        config_uniq_id: str,
        coordinator: Hub,
        name: str | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialize a prog time Sensor."""
        super().__init__(
            capability=capability,
            config_title=config_title,
            config_uniq_id=config_uniq_id,
            coordinator=coordinator,
            name=name,
            icon=icon,
        )

    def get_value(self) -> str:
        """Retrieve value from hub."""
        value = self.coordinator.get_capability_value(self._capability["capabilityId"])
        if value is not None:
            progList = json.loads(value)

            strValue = ""
            for prog in progList:
                if len(prog) >= 2 and (prog[0] != 0 or prog[1] != 0):
                    hoursfrom = int(prog[0] / 60)
                    minutesfrom = int(prog[0] % 60)

                    hoursto = int(prog[1] / 60)
                    minutesto = int(prog[1] % 60)

                    if strValue != "":
                        strValue += " / "
                    strValue += "%02d:%02d-%02d:%02d" % (
                        hoursfrom,
                        minutesfrom,
                        hoursto,
                        minutesto,
                    )

            return strValue

        return None
