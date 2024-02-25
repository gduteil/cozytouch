"""Sensors for Atlantic Cozytouch integration."""
from __future__ import annotations

import datetime
from enum import IntEnum
import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfPower,
    UnitOfPressure,
    UnitOfSoundPressure,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .hub import Hub

_LOGGER = logging.getLogger(__name__)


class CozytouchCapabilityVariableType(IntEnum):
    """Capabilities types."""

    STRING = 0
    BOOL = 1
    FLOAT = 2
    INT = 3


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
                    hub=hub,
                )
            )
        elif capability["type"] == "temperature":
            sensors.append(
                CozytouchUnitSensor(
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    hub=hub,
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
                    hub=hub,
                    device_class=SensorDeviceClass.PRESSURE,
                    native_unit_of_measurement=UnitOfPressure.BAR,
                )
            )
        elif capability["type"] == "timestamp_2":
            sensors.append(
                CozytouchTimestampSensor(
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    attr_uniq_id=config_entry.entry_id + "_0",
                    hub=hub,
                    name=capability["name_0"],
                    icon=capability.get("icon_0", None),
                    separator=",",
                    timestamp_index=0,
                )
            )

            sensors.append(
                CozytouchTimestampSensor(
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    attr_uniq_id=config_entry.entry_id + "_1",
                    hub=hub,
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
                    hub=hub,
                )
            )
        elif capability["type"] == "signal":
            sensors.append(
                CozytouchUnitSensor(
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    hub=hub,
                    device_class=SensorDeviceClass.SIGNAL_STRENGTH,
                    native_unit_of_measurement=UnitOfSoundPressure.DECIBEL,
                )
            )
        elif capability["type"] == "power":
            sensors.append(
                CozytouchUnitSensor(
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    hub=hub,
                    device_class=SensorDeviceClass.POWER,
                    native_unit_of_measurement=UnitOfPower.WATT,
                )
            )

    # Add the entities to HA
    if len(sensors) > 0:
        async_add_entities(sensors, True)


class CozytouchSensor(SensorEntity):
    """Common class for sensors."""

    _attr_has_entity_name = True
    _attr_should_poll = True

    def __init__(
        self,
        capability,
        config_title: str,
        config_uniq_id: str,
        hub: Hub,
        attr_uniq_id: str | None = None,
        name: str | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialize a sensor."""
        self._capability = capability
        self._config_title = config_title
        self._config_uniq_id = config_uniq_id
        self._hub = hub
        self._last_value: str | None = None
        self._value_type: CozytouchCapabilityVariableType | None = None

        if attr_uniq_id:
            self._attr_unique_id = attr_uniq_id
        else:
            capabilityId = self._capability["capabilityId"]
            self._attr_unique_id = f"{DOMAIN}_{config_uniq_id}_{str(capabilityId)}"

        if name:
            self._attr_name = name
        else:
            self._attr_name = self._capability["name"]

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

    def _get_capability_value(self, capabilityId: int):
        return self._hub.get_capability_value(
            self._capability["deviceId"], capabilityId
        )

    def get_value(self):
        """Retrieve value from hub."""
        value = self._get_capability_value(self._capability["capabilityId"])
        if self._value_type == CozytouchCapabilityVariableType.BOOL:
            return bool(value)
        if self._value_type == CozytouchCapabilityVariableType.FLOAT:
            return float(value)
        if self._value_type == CozytouchCapabilityVariableType.INT:
            return int(value)

        return value

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._config_uniq_id)},
        )

    @property
    def native_value(self):
        """Value of the sensor."""
        return self._last_value

    @callback
    def update(self):
        """Update the value of the sensor from the hub."""
        # Get last seen value from controller
        value = self.get_value()

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
        elif not self._attr_available:
            _LOGGER.info(
                "%s: marking the %s sensor as available now !",
                self._config_title,
                self._attr_name,
            )
            self._attr_available = True

        # Save value
        self._last_value = value


class CozytouchTimestampSensor(CozytouchSensor):
    """Class for timestamp sensor."""

    def __init__(
        self,
        capability,
        config_title: str,
        config_uniq_id: str,
        hub: Hub,
        name: str | None = None,
        icon: str | None = None,
        separator: str | None = None,
        timestamp_index: int | None = None,
        attr_uniq_id: str | None = None,
    ) -> None:
        """Initialize a timestamp Sensor."""
        super().__init__(
            capability=capability,
            config_title=config_title,
            config_uniq_id=config_uniq_id,
            attr_uniq_id=attr_uniq_id,
            hub=hub,
            name=name,
            icon=icon,
        )
        self._value_type = CozytouchCapabilityVariableType.STRING
        self._separator = separator
        self._timestamp_index = timestamp_index

    def get_value(self) -> str:
        """Retrieve value from hub."""
        value = self._get_capability_value(self._capability["capabilityId"])
        if value is not None:
            value = value.translate(str.maketrans("", "", "[]"))
            timestamps = value.split(self._separator, 2)
            if self._timestamp_index < len(timestamps):
                timestamp = int(timestamps[self._timestamp_index])
                if timestamp > 0:
                    ts = datetime.datetime.fromtimestamp(timestamp)
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
        hub: Hub,
        name: str | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialize a binary Sensor."""
        super().__init__(
            capability=capability,
            config_title=config_title,
            config_uniq_id=config_uniq_id,
            hub=hub,
            name=name,
            icon=icon,
        )
        self._last_value: False

    @property
    def is_on(self) -> bool:
        """Return last state value."""
        value_on = "0"
        if "value_on" in self._capability:
            value_on = self._capability["value_on"]

        return self._last_value == value_on


class CozytouchUnitSensor(CozytouchSensor):
    """Class for unit sensor."""

    def __init__(
        self,
        capability,
        config_title: str,
        config_uniq_id: str,
        hub: Hub,
        device_class: SensorDeviceClass,
        native_unit_of_measurement,
        suggested_precision: int | None = None,
        name: str | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialize an unit Sensor."""
        super().__init__(
            capability=capability,
            config_title=config_title,
            config_uniq_id=config_uniq_id,
            hub=hub,
            name=name,
            icon=icon,
        )
        self._value_type = CozytouchCapabilityVariableType.FLOAT
        self._attr_native_unit_of_measurement = native_unit_of_measurement
        self._attr_suggested_display_precision = suggested_precision
        if device_class:
            self._attr_device_class = device_class

    @property
    def native_value(self) -> float | None:
        """Value of the sensor."""
        return float(self._last_value)
