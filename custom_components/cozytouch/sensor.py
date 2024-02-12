"""Sensors for Atlantic Cozytouch integration."""
from __future__ import annotations

import datetime
import logging
import time

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPressure, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
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
        category = None
        if "category" in capability and capability["category"] == "diag":
            category = EntityCategory.DIAGNOSTIC

        icon = None
        if "icon" in capability:
            icon = capability["icon"]

        if capability["type"] in ("string", "int"):
            # Use a RegularStrSensor for integers
            sensors.append(
                RegularStrSensor(
                    deviceId=capability["deviceId"],
                    capabilityId=capability["capabilityId"],
                    name=capability["name"],
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    hub=hub,
                    icon=icon,
                    category=category,
                )
            )
        elif capability["type"] == "temperature":
            sensors.append(
                TemperatureOrPressureSensor(
                    deviceId=capability["deviceId"],
                    capabilityId=capability["capabilityId"],
                    name=capability["name"],
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    hub=hub,
                    icon=icon,
                    category=category,
                    device_class=SensorDeviceClass.TEMPERATURE,
                    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                )
            )
        elif capability["type"] == "pressure":
            sensors.append(
                TemperatureOrPressureSensor(
                    deviceId=capability["deviceId"],
                    capabilityId=capability["capabilityId"],
                    name=capability["name"],
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    hub=hub,
                    icon=icon,
                    category=category,
                    device_class=SensorDeviceClass.PRESSURE,
                    native_unit_of_measurement=UnitOfPressure.BAR,
                )
            )
        elif capability["type"] == "timestamp_2":
            icon_0 = None
            if "icon_0" in capability:
                icon_0 = capability["icon_0"]

            sensors.append(
                TimestampSensor(
                    deviceId=capability["deviceId"],
                    capabilityId=capability["capabilityId"],
                    name=capability["name_0"],
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    hub=hub,
                    icon=icon_0,
                    category=category,
                    separator=",",
                    timestamp_index=0,
                )
            )

            icon_1 = None
            if "icon_1" in capability:
                icon_1 = capability["icon_1"]

            sensors.append(
                TimestampSensor(
                    deviceId=capability["deviceId"],
                    capabilityId=capability["capabilityId"],
                    name=capability["name_1"],
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    hub=hub,
                    icon=icon_1,
                    category=category,
                    separator=",",
                    timestamp_index=1,
                )
            )
        elif capability["type"] in ("switch", "binary"):
            value_off = "0"
            if "value_off" in capability:
                value_off = capability["value_off"]

            value_on = "1"
            if "value_on" in capability:
                value_on = capability["value_on"]

            sensors.append(
                RegularBinarySensor(
                    deviceId=capability["deviceId"],
                    capabilityId=capability["capabilityId"],
                    name=capability["name"],
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    hub=hub,
                    icon=icon,
                    category=category,
                    value_off=value_off,
                    value_on=value_on,
                )
            )

    # Add the entities to HA
    if len(sensors) > 0:
        async_add_entities(sensors, True)


class RegularStrSensor(SensorEntity):
    """Common class for text sensor."""

    # Generic entity properties
    _attr_has_entity_name = True
    _attr_should_poll = True

    def __init__(
        self,
        deviceId: int,
        capabilityId: int,
        name: str,
        config_title: str,
        config_uniq_id: str,
        hub: Hub,
        icon: str | None = None,
        category: EntityCategory | None = None,
    ) -> None:
        """Initialize a Regular Str Sensor."""
        _LOGGER.debug("%s: initializing %s sensor", config_title, name)

        self._deviceId = deviceId
        self._capabilityId = capabilityId
        self._config_title = config_title
        self._config_uniq_id = config_uniq_id
        self._hub = hub
        self._last_value: str | None = None

        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{config_uniq_id}_{str(capabilityId)}"
        if icon:
            self._attr_icon = icon
        if category:
            self._attr_entity_category = category

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._config_uniq_id)},
        )

    @property
    def native_value(self) -> str | None:
        """Value of the sensor."""
        return self._last_value

    @callback
    def update(self):
        """Update the value of the sensor from the hub."""
        # Get last seen value from controller
        value = self.get_value()
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
        elif not self._attr_available:
            _LOGGER.info(
                "%s: marking the %s sensor as available now !",
                self._config_title,
                self._attr_name,
            )
            self._attr_available = True

        # Save value
        self._last_value = value

    def get_value(self) -> str:
        """Retrieve value from hub."""
        return self._hub.get_capability_value(self._deviceId, self._capabilityId)


class TimestampSensor(RegularStrSensor):
    """Class for timestamp sensor."""

    def __init__(
        self,
        deviceId: int,
        capabilityId: int,
        name: str,
        config_title: str,
        config_uniq_id: str,
        hub: Hub,
        icon: str | None = None,
        category: EntityCategory | None = None,
        separator: str | None = None,
        timestamp_index: int | None = None,
    ) -> None:
        """Initialize a Regular Str Sensor."""
        _LOGGER.debug("%s: initializing %s timetamp", config_title, name)

        super().__init__(
            deviceId=deviceId,
            capabilityId=capabilityId,
            name=name,
            config_title=config_title,
            config_uniq_id=config_uniq_id,
            hub=hub,
            icon=icon,
            category=category,
        )
        self._attr_unique_id = (
            f"{DOMAIN}_{config_uniq_id}_{str(capabilityId)}_{str(timestamp_index)}"
        )

        self._separator = separator
        self._timestamp_index = timestamp_index

    def get_value(self) -> str:
        """Retrieve value from hub."""
        value = self._hub.get_capability_value(self._deviceId, self._capabilityId)
        if value is not None:
            value = value.translate(str.maketrans("", "", "[]"))
            timestamps = value.split(self._separator, 2)
            if self._timestamp_index < len(timestamps):
                timestamp = int(timestamps[self._timestamp_index])
                if timestamp > 0:
                    now_timestamp = time.time()
                    offset = datetime.datetime.fromtimestamp(
                        now_timestamp
                    ) - datetime.datetime.fromtimestamp(now_timestamp, "utc")

                    ts = datetime.datetime.fromtimestamp(timestamp + offset.seconds)
                    return ts.strftime("%H:%M %d/%m/%Y")

                return "Undefined"

        return None


class RegularBinarySensor(BinarySensorEntity):
    """Common class for binary sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = True

    def __init__(
        self,
        deviceId: int,
        capabilityId: int,
        name: str,
        config_title: str,
        config_uniq_id: str,
        hub: Hub,
        value_off: str,
        value_on: str,
        icon: str | None = None,
        category: EntityCategory | None = None,
        device_class=BinarySensorDeviceClass.LIGHT,
    ) -> None:
        """Initialize a binary sensor."""
        _LOGGER.debug("%s: initializing %s binary sensor", config_title, name)

        self._deviceId = deviceId
        self._capabilityId = capabilityId
        self._config_title = config_title
        self._config_uniq_id = config_uniq_id
        self._hub = hub
        self._value_off = value_off
        self._value_on = value_on
        self._last_value: bool | None = None

        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{config_uniq_id}_{str(capabilityId)}"
        if icon:
            self._attr_icon = icon
        if category:
            self._attr_entity_category = category
        if device_class:
            self._attr_device_class = device_class

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._config_uniq_id)},
        )

    @property
    def is_on(self) -> bool:
        """Update the value of the sensor from the hub."""
        # Get last seen value from controller
        value = (
            self._hub.get_capability_value(self._deviceId, self._capabilityId)
            != self._value_off
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

        if not self._attr_available:
            _LOGGER.info(
                "%s: marking the %s sensor as available now !",
                self._config_title,
                self._attr_name,
            )
            self._attr_available = True

        return value


class TemperatureOrPressureSensor(SensorEntity):
    """Common class for temperature sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = True

    def __init__(
        self,
        deviceId: int,
        capabilityId: int,
        name: str,
        config_title: str,
        config_uniq_id: str,
        hub: Hub,
        icon: str | None = None,
        category: EntityCategory | None = None,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ) -> None:
        """Initialize a temperature Sensor."""
        _LOGGER.debug("%s: initializing %s sensor", config_title, name)

        self._deviceId = deviceId
        self._capabilityId = capabilityId
        self._config_title = config_title
        self._config_uniq_id = config_uniq_id
        self._hub = hub
        self._last_value: float | None = None

        self._attr_native_unit_of_measurement = native_unit_of_measurement
        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{config_uniq_id}_{str(capabilityId)}"
        if icon:
            self._attr_icon = icon
        if category:
            self._attr_entity_category = category
        if device_class:
            self._attr_device_class = device_class

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._config_uniq_id)},
        )

    @property
    def native_value(self) -> float | None:
        """Value of the sensor."""
        return self._last_value

    @callback
    def update(self):
        """Update the value of the sensor from the hub."""
        # Get last seen value from controller
        value = float(
            self._hub.get_capability_value(self._deviceId, self._capabilityId)
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

        # Save value
        self._last_value = value


class PressureSensor(SensorEntity):
    """Common class for pressure sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = True

    def __init__(
        self,
        deviceId: int,
        capabilityId: int,
        name: str,
        config_title: str,
        config_uniq_id: str,
        hub: Hub,
        icon: str | None = None,
        category: EntityCategory | None = None,
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.BAR,
    ) -> None:
        """Initialize a pressure Sensor."""
        _LOGGER.debug("%s: initializing %s sensor", config_title, name)

        self._deviceId = deviceId
        self._capabilityId = capabilityId
        self._config_title = config_title
        self._config_uniq_id = config_uniq_id
        self._hub = hub
        self._last_value: float | None = None

        self._attr_native_unit_of_measurement = native_unit_of_measurement
        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{config_uniq_id}_{str(capabilityId)}"
        if icon:
            self._attr_icon = icon
        if category:
            self._attr_entity_category = category
        if device_class:
            self._attr_device_class = device_class

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._config_uniq_id)},
        )

    @property
    def native_value(self) -> float | None:
        """Value of the sensor."""
        return self._last_value

    @callback
    def update(self):
        """Update the value of the sensor from the hub."""
        # Get last seen value from controller
        value = float(
            self._hub.get_capability_value(self._deviceId, self._capabilityId)
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

        # Save value
        self._last_value = value
