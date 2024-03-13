"""Sensors for Atlantic Cozytouch integration."""
from __future__ import annotations

import datetime
import json
import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
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
        elif capability["type"] == "timestamp_2":
            sensors.append(
                CozytouchTimestampSensor(
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
                CozytouchTimestampSensor(
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
            sensors.append(
                CozytouchUnitSensor(
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    coordinator=hub,
                    device_class=SensorDeviceClass.POWER,
                    native_unit_of_measurement=UnitOfPower.WATT,
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

        elif capability["type"] == "prog":
            sensors.append(
                CozytouchProgSensor(
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

    # Create tariffs entities
    if hub.get_create_entities_for_tariffs():
        dhwEnergyId = hub.get_dhw_energy_id()
        if dhwEnergyId:
            sensors.append(
                CozytouchTariffSensor(
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    coordinator=hub,
                    name="DHW Tariff",
                    energyId=dhwEnergyId,
                )
            )

            sensors.append(
                CozytouchConsumptionSensor(
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    coordinator=hub,
                    name="DHW Daily Consumption",
                    index=1,
                )
            )

        heatingEnergyId = hub.get_heating_energy_id()
        if heatingEnergyId:
            sensors.append(
                CozytouchTariffSensor(
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    coordinator=hub,
                    name="Heating Tariff",
                    energyId=heatingEnergyId,
                )
            )

            sensors.append(
                CozytouchConsumptionSensor(
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                    coordinator=hub,
                    name="Heating Daily Consumption",
                    index=0,
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

        if name:
            self._attr_name = name
        else:
            self._attr_name = self._capability["name"]

        if translation_key:
            self._attr_translation_key = translation_key
        else:
            self._attr_translation_key = self._attr_name

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


class CozytouchTimestampSensor(CozytouchSensor):
    """Class for timestamp sensor."""

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
        """Initialize a timestamp Sensor."""
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
        """Initialize a time Sensor."""
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
                    strValue += " %d°C" % (prog[1])

            return strValue

        return None


class CozytouchTariffSensor(SensorEntity, CoordinatorEntity):
    """Class for tariffs."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: Hub,
        config_title: str,
        config_uniq_id: str,
        name: str,
        energyId: int,
    ) -> None:
        """Initialize a sensor."""
        super().__init__(coordinator)

        self._config_title = config_title
        self._config_uniq_id = config_uniq_id
        self._attr_unique_id = f"{DOMAIN}_{config_uniq_id}_{name.lower()}"
        self._attr_name = name
        self._attr_translation_key = self._attr_name

        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_unit_of_measurement = "EUR"
        self._attr_icon = "mdi:currency-eur"

        self._energyId = energyId
        self._last_value = 0.0

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
    def _handle_coordinator_update(self) -> None:
        """Update the value of the sensor from the hub."""
        # Get last seen value from controller
        self._last_value = self.coordinator.get_energy_tariff(self._energyId)
        self.async_write_ha_state()


class CozytouchConsumptionSensor(SensorEntity, CoordinatorEntity):
    """Class for tariffs."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: Hub,
        config_title: str,
        config_uniq_id: str,
        name: str,
        index: int,
    ) -> None:
        """Initialize a sensor."""
        super().__init__(coordinator)

        self._config_title = config_title
        self._config_uniq_id = config_uniq_id
        self._attr_unique_id = f"{DOMAIN}_{config_uniq_id}_{name.lower()}"
        self._attr_name = name
        self._attr_translation_key = self._attr_name

        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_suggested_display_precision = 2
        self._last_value = 0.0
        self._index = index

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
    def _handle_coordinator_update(self) -> None:
        """Update the value of the sensor from the hub."""
        # Get last seen value from controller
        self._last_value = self.coordinator.get_daily_consumption(self._index)
        self.async_write_ha_state()
