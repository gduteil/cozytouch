"""Sensors for Atlantic Cozytouch integration."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
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
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfPressure,
    UnitOfSoundPressure,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import consumption, faults
from .capability import describe_capability_value, read_setpoint
from .const import DOMAIN, CozytouchCapabilityVariableType
from .hub import (
    CozytouchConfigEntry,
    CozytouchDeviceEntity,
    Hub,
    add_capability_entities,
)
from .infos import CapabilityCategory, CapabilityType

_LOGGER = logging.getLogger(__name__)


def decode_error_code(raw: str | None) -> str | None:
    """Turn a fault-code matrix into the codes that are actually active.

    The raw string comes back unchanged when it does not parse. See
    docs/decisions.md.
    """
    if raw is None:
        return None

    rows = faults.active_rows(raw)
    if rows is None:
        return raw

    return ", ".join(faults.code_of(row) for row in rows) or faults.HEALTHY


# config flow setup
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: CozytouchConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Modern (thru config entry) sensors setup."""
    _LOGGER.debug("%s: setting up sensor plateform", config_entry.title)
    # SENSOR_BUILDERS is at the foot of this module, because it names the
    # classes below.
    add_capability_entities(config_entry, async_add_entities, SENSOR_BUILDERS)

    # The two dates are not built from a capability, so they are not in the
    # table above : one comes with every capability rather than being one of
    # them, the other belongs to the account. Each is created only when the
    # device reports it, the same rule the capability flags follow -- an entity
    # nobody's hardware backs is worse than no entity. The poll date is always
    # there in production, since connect() reads the setup view before any
    # platform loads.
    for subentry_id in config_entry.subentries:
        hub = config_entry.runtime_data.hubs[subentry_id]

        dates = []
        if hub.get_last_modification_date() is not None:
            dates.append(CozytouchLastUpdateSensor(hub, subentry_id))
        if hub.get_last_poll() is not None:
            dates.append(CozytouchLastPollSensor(hub, subentry_id))

        if dates:
            async_add_entities(dates, True, config_subentry_id=subentry_id)

    # The setup's, not a device's, so under no subentry.
    if consumed := consumption_sensors(config_entry):
        async_add_entities(consumed, False)


class CozytouchSensor(SensorEntity, CozytouchDeviceEntity):
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
        self._raw_value: str | None = None
        self._device_uniq_id = config_uniq_id

        # Only set _attr_name when there is a name to set. Assigning None here
        # would tell HA this entity *is* the device, which collapses every
        # entity to the device name and skips the translation key entirely.
        if name:
            self._attr_name = name

        if value_type:
            self._value_type = value_type
        elif "value_type" in self._capability:
            self._value_type = self._capability.value_type
        else:
            self._value_type = None

        if attr_uniq_id:
            self._attr_unique_id = attr_uniq_id
        else:
            capabilityId = self._capability.capabilityId
            self._attr_unique_id = f"{DOMAIN}_{config_uniq_id}_{capabilityId!s}"

        self.entity_description = SensorEntityDescription(
            key="capability_" + str(capability.capabilityId),
            name=name if name else self._capability.name,
        )

        self._attr_translation_key = (
            translation_key if translation_key else self.entity_description.name
        )

        # A capability can ask to arrive switched off. It is still mapped, named
        # and searchable in the entity registry, but it holds no state and costs
        # nothing in the recorder until someone turns it on. That is the right
        # default for the values the API reports about itself -- supported-mode
        # bitmasks, scheduling constants -- which are worth having available and
        # not worth showing to everybody.
        self._attr_entity_registry_enabled_default = self._capability.get(
            "enabled_by_default", True
        )

        if "category" in self._capability:
            if self._capability.category == CapabilityCategory.DIAG:
                self._attr_entity_category = EntityCategory.DIAGNOSTIC
            elif self._capability.category == CapabilityCategory.CONFIG:
                self._attr_entity_category = EntityCategory.CONFIG
            else:
                self._attr_entity_category = None

        if icon:
            self._attr_icon = icon
        elif "icon" in self._capability:
            self._attr_icon = self._capability.icon

    def get_value(self):
        """Retrieve value from hub."""
        if self._value_type == CozytouchCapabilityVariableType.ARRAY:
            return "array"

        try:
            value = self.coordinator.get_capability_value(
                self._capability.capabilityId
            )
            if value is None:
                self._raw_value = None
                return None
            described = describe_capability_value(
                self._capability.capabilityId, value
            )
            if described is not None:
                # The number stays available as an attribute: these entities are
                # here to investigate hardware, and a reader chasing a bit the
                # tables do not name needs what the device actually said.
                self._raw_value = value
                return described
            self._raw_value = None
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
    def native_value(self):
        """Value of the sensor."""
        return self._last_value

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """The value as the device sent it, when this sensor decoded one."""
        if self._raw_value is None:
            return None
        return {"raw": self._raw_value}

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update the value of the sensor from the hub."""
        # Get last seen value from controller
        value = self.get_value()
        # _LOGGER.info("%s: update %s (%s)", self._config_title, self._attr_name, value)

        # Handle entity availability
        if value is None:
            if self._attr_available and not self.coordinator.online:
                _LOGGER.debug(
                    "%s: marking the %s sensor as unavailable:"
                    " Cozytouch connection lost",
                    self._config_title,
                    self.name,
                )
                self._attr_available = False
        elif not self._attr_available:
            _LOGGER.info(
                "%s: marking the %s sensor as available now !",
                self._config_title,
                self.name,
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
        translation_key: str | None = None,
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
            translation_key=translation_key,
            icon=icon,
            value_type=CozytouchCapabilityVariableType.STRING,
        )
        self._separator = separator
        self._timestamp_index = timestamp_index

    def get_value(self) -> str:
        """Retrieve value from hub."""
        value = self.coordinator.get_capability_value(self._capability.capabilityId)
        if value is not None:
            value = value.translate(str.maketrans("", "", "[]"))
            timestamps = value.split(self._separator, 2)
            if len(timestamps) == 2:
                if timestamps[0] != "0" and timestamps[1] != "0":
                    timestamp = int(timestamps[self._timestamp_index])
                    timeOffset = int(
                        self.coordinator.get_capability_value(
                            self._capability.timezoneCapabilityId
                        )
                    )
                    # DTZ006 is silenced on purpose: the device's offset is
                    # already in the timestamp, so reading it naively applies
                    # that offset twice for anyone off UTC. Fixing it changes
                    # what the sensor displays and wants its own change, with
                    # a capture to check against -- docs/architecture.md.
                    ts = datetime.datetime.fromtimestamp(  # noqa: DTZ006
                        timestamp + timeOffset
                    )

                    # Check if we need to init timestamps in coordinator
                    timestampStart = self.coordinator.get_away_mode_start()
                    timestampEnd = self.coordinator.get_away_mode_end()
                    if timestampStart is None or timestampEnd is None:
                        self.coordinator.away_mode_init(
                            int(timestamps[0]), int(timestamps[1])
                        )

                    return ts.strftime("%H:%M %d/%m/%Y")

                # None rather than a word of our own: Home Assistant already
                # has one for a state it does not know, in every language it
                # ships. See docs/decisions.md.
                return None

        return None


class CozytouchBinarySensor(BinarySensorEntity, CozytouchSensor):
    """Class for binary sensor."""

    @property
    def is_on(self) -> bool:
        """Return last state value."""
        value_on = "1"
        if "value_on" in self._capability:
            value_on = self._capability.value_on

        return self._last_value == value_on


class CozytouchAwayModeSensor(CozytouchSensor):
    """Class for away mode sensor."""

    def get_value(self) -> str:
        """Retrieve value from hub."""
        value = self.coordinator.get_capability_value(self._capability.capabilityId)
        if value is not None:
            strValue = "Unknown"
            if value == self._capability.value_off:
                strValue = "Off"
            elif value == self._capability.value_pending:
                strValue = "Pending"
            elif value == self._capability.value_on:
                strValue = "On"

            return strValue

        return None


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

        self._display_factor = display_factor

    def get_value(self):
        """Retrieve value from hub and convert it if needed."""
        value = super().get_value()
        if value is not None and self._display_factor != 1.0:
            return float(value) * self._display_factor

        return value

    @property
    def native_value(self) -> float | None:
        """Value of the sensor."""
        # Against None and the empty string, not against falsiness: a reading
        # of zero is a reading. See docs/decisions.md.
        if self._last_value is None or self._last_value == "":
            return None

        try:
            return float(self._last_value)
        except ValueError:
            return 0.0


class CozytouchTimezoneSensor(CozytouchSensor):
    """Class for timezone sensor."""

    def get_value(self) -> str:
        """Retrieve value from hub."""
        value = self.coordinator.get_capability_value(self._capability.capabilityId)
        if value is not None:
            # Floor division rather than %d over a true division: the operand
            # is positive in both branches, so it truncates the same way.
            if float(value) > 0:
                strValue = f"GMT+{int(value) // 3600}"
            elif float(value) < 0:
                strValue = f"GMT-{abs(int(value)) // 3600}"
            else:
                strValue = "GMT"

            return strValue

        return None


class CozytouchProgSensor(CozytouchSensor):
    """Class for Prog sensor."""

    def get_value(self) -> str:
        """Retrieve value from hub."""
        capabilityId = self._capability.capabilityId
        value = self.coordinator.get_capability_value(capabilityId)
        if value is not None:
            progList = json.loads(value)

            strValue = ""
            for prog in progList:
                if len(prog) >= 2 and (prog[0] != 0 or prog[1] != 0):
                    hours = int(prog[0] / 60)
                    minutes = int(prog[0] % 60)

                    if strValue != "":
                        strValue += " / "
                    strValue += f"{hours:02d}:{minutes:02d} "
                    # int() rather than the value itself: the setpoint arrives
                    # from JSON and can be a float, which %d used to truncate.
                    strValue += (
                        f" {int(read_setpoint(capabilityId, prog[1]))}°C"
                    )

            return strValue

        return None


class CozytouchProgTimeSensor(CozytouchSensor):
    """Class for ProgTime sensor."""

    def get_value(self) -> str:
        """Retrieve value from hub."""
        value = self.coordinator.get_capability_value(self._capability.capabilityId)
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
                    strValue += (
                        f"{hoursfrom:02d}:{minutesfrom:02d}"
                        f"-{hoursto:02d}:{minutesto:02d}"
                    )

            return strValue

        return None


class CozytouchErrorCodeSensor(CozytouchSensor):
    """A fault-code capability, decoded to the codes that are active."""

    def get_value(self) -> str | None:
        """Retrieve value from hub and decode the fault matrix."""
        value = self.coordinator.get_capability_value(self._capability.capabilityId)
        return decode_error_code(value)

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """What the vendor's table says about the codes that are active.

        Attributes rather than the state, which stays the code : a label runs
        past what a state may hold, and the state is what automations already
        match on. See docs/decisions.md.
        """
        described = self.coordinator.get_faults().get(
            self._capability.capabilityId
        )
        if not described:
            return None

        return {
            "error_label": "\n".join(fault["label"] for fault in described),
            "probable_cause": "\n".join(
                fault["cause"] for fault in described if fault["cause"]
            ),
            "repair_instructions": "\n".join(
                fault["repair"] for fault in described if fault["repair"]
            ),
        }


class _CozytouchDeviceTimestampSensor(CozytouchDeviceEntity, SensorEntity):
    """A diagnostic timestamp that answers for the whole device."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: Hub, config_uniq_id: str) -> None:
        """Initialize the timestamp sensor."""
        super().__init__(coordinator)

        self._device_uniq_id = config_uniq_id
        # Not keyed on a capability id like every other entity here, because it
        # answers for all of them. The translation key is a name no capability
        # can take: capability.py only ever produces ids.
        self._attr_unique_id = (
            f"{DOMAIN}_{config_uniq_id}_{self._attr_translation_key}"
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Publish whatever the poll just brought back."""
        self.async_write_ha_state()


class CozytouchLastUpdateSensor(_CozytouchDeviceTimestampSensor):
    """When the device last changed any of the values it reports.

    Answers what a frozen reading cannot : is the hardware still reporting, or
    has it fallen off Atlantic's cloud ? A staleness threshold on top of this
    is deliberately not attempted. See docs/decisions.md.
    """

    _attr_translation_key = "last_device_update"

    @property
    def native_value(self) -> datetime.datetime | None:
        """The newest date the device reports, as an aware datetime.

        UTC, because an epoch is absolute -- which is what keeps this out of
        the double-offset trap the away-mode timestamp sensor is in.
        """
        epoch = self.coordinator.get_last_modification_date()
        if epoch is None:
            return None

        return datetime.datetime.fromtimestamp(epoch, tz=datetime.UTC)


class CozytouchLastPollSensor(_CozytouchDeviceTimestampSensor):
    """When the integration last fetched the account from the API.

    The other half of what `CozytouchLastUpdateSensor` answers : that one says
    when the hardware last changed a value, this one when anybody last asked.
    Per device though the date is the account's. See docs/decisions.md.
    """

    _attr_translation_key = "last_poll"

    @property
    def available(self) -> bool:
        """Available as long as a poll ever succeeded.

        Deliberately not the CoordinatorEntity reading. See docs/decisions.md.
        """
        return self.coordinator.get_last_poll() is not None

    @property
    def native_value(self) -> datetime.datetime | None:
        """When the account's setup view last answered, as an aware datetime."""
        return self.coordinator.get_last_poll()


@dataclass(frozen=True, kw_only=True)
class ConsumptionDescription(SensorEntityDescription):
    """One reading of the consumption endpoint : which series, which field.

    `mode` None is the whole day ; a tariff period otherwise.
    """

    series: int
    field: str = "quantity"
    mode: int | None = None


CONSUMPTION_SENSORS = (
    ConsumptionDescription(
        key="energy_today",
        translation_key="energy_today",
        series=consumption.ELECTRICITY,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
    ConsumptionDescription(
        key="energy_peak_today",
        translation_key="energy_peak_today",
        series=consumption.ELECTRICITY,
        mode=consumption.PEAK,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:weather-sunny",
    ),
    ConsumptionDescription(
        key="energy_offpeak_today",
        translation_key="energy_offpeak_today",
        series=consumption.ELECTRICITY,
        mode=consumption.OFFPEAK,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:weather-night",
    ),
    ConsumptionDescription(
        key="energy_cost_today",
        translation_key="energy_cost_today",
        series=consumption.ELECTRICITY,
        field="cost",
        device_class=SensorDeviceClass.MONETARY,
    ),
    ConsumptionDescription(
        key="water_today",
        translation_key="water_today",
        series=consumption.WATER,
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        suggested_display_precision=0,
    ),
)


def consumption_sensors(config_entry: CozytouchConfigEntry) -> list:
    """The daily readings the setup's first answer carries, and only those.

    A tariff split only where the series has used one, and a cost only in a
    currency somebody has seen. See docs/decisions.md.
    """
    runtime = config_entry.runtime_data
    days = consumption.latest_days(runtime.account.consumptions)

    sensors = []
    for description in CONSUMPTION_SENSORS:
        day = days.get(description.series)
        if day is None:
            continue
        if description.mode is not None and not (
            {consumption.PEAK, consumption.OFFPEAK} <= day.modes
        ):
            continue
        if description.field == "cost":
            if day.currency is None:
                continue
            description = dataclasses.replace(
                description, native_unit_of_measurement=day.currency
            )

        sensors.append(
            CozytouchConsumptionSensor(
                runtime.coordinator, runtime.account, config_entry, description
            )
        )

    return sensors


class CozytouchConsumptionSensor(CoordinatorEntity, SensorEntity):
    """The day so far on one consumption series, for the whole setup.

    TOTAL with the day's start as `last_reset`, which is what a daily bucket
    is ; the cost has no other state class it may take. See
    docs/decisions.md.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_state_class = SensorStateClass.TOTAL
    entity_description: ConsumptionDescription

    def __init__(
        self,
        coordinator,
        account,
        config_entry: CozytouchConfigEntry,
        description: ConsumptionDescription,
    ) -> None:
        """Initialize the consumption sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._account = account
        self._attr_unique_id = (
            f"{DOMAIN}_{config_entry.entry_id}_consumption_{description.key}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            manufacturer="Atlantic",
            name=account.setup.get("name") or "Cozytouch",
            model="Installation",
        )

    def _day(self) -> consumption.Day | None:
        return consumption.latest_days(self._account.consumptions).get(
            self.entity_description.series
        )

    @property
    def available(self) -> bool:
        """Only while the latest answer still carries this series."""
        return super().available and self._day() is not None

    @property
    def native_value(self) -> float | None:
        """The day so far, whole or for one tariff period."""
        day = self._day()
        if day is None:
            return None

        description = self.entity_description
        if description.mode is None:
            return day.total(description.field)

        return day.of_mode(description.field, description.mode)

    @property
    def last_reset(self) -> datetime.datetime | None:
        """The start of the day the reading is for, as the API dates it."""
        day = self._day()
        if day is None:
            return None

        return datetime.datetime.fromtimestamp(day.date, tz=datetime.UTC)


def _unit(device_class, state_class, unit):
    """A CozytouchUnitSensor builder for a type that has a usual unit.

    Usual, not fixed: a row may state its own with
    `displayed_unit_of_measurement`, the key `_energy` below already reads,
    because one device class covers several units and the vendor picks per
    capability -- kW on one power reading and W on the next. Home Assistant
    rejects a unit its device class does not cover, which is the check that
    keeps the override honest. See docs/decisions.md.
    """

    def build(coordinator, capability, config_title: str, config_uniq_id: str):
        return CozytouchUnitSensor(
            coordinator=coordinator,
            capability=capability,
            config_title=config_title,
            config_uniq_id=config_uniq_id,
            device_class=device_class,
            state_class=state_class,
            native_unit_of_measurement=capability.get(
                "displayed_unit_of_measurement", unit
            ),
        )

    return build


def _energy(coordinator, capability, config_title: str, config_uniq_id: str):
    """An energy counter, in whichever of the two units the mapping asked for."""
    unit = capability.get("displayed_unit_of_measurement", UnitOfEnergy.WATT_HOUR)
    return CozytouchUnitSensor(
        coordinator=coordinator,
        capability=capability,
        config_title=config_title,
        config_uniq_id=config_uniq_id,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=unit,
        display_factor=0.001 if unit == UnitOfEnergy.KILO_WATT_HOUR else 1.0,
    )


def _away_mode_timestamps(coordinator, capability, config_title, config_uniq_id):
    """The two ends of the away window, which are one capability."""
    return [
        CozytouchAwayModeTimestampSensor(
            capability=capability,
            config_title=config_title,
            config_uniq_id=config_uniq_id,
            attr_uniq_id=f"{config_uniq_id}_{index}",
            coordinator=coordinator,
            translation_key=timestamp.name,
            icon=timestamp.icon,
            separator=",",
            timestamp_index=index,
        )
        for index, timestamp in enumerate(capability.timestamps)
    ]


# MEASUREMENT on everything that reads an instant value, TOTAL_INCREASING on
# what counts; VOLUME_STORAGE and not VOLUME on a tank; no device class on a
# percentage. Each of those is a combination HA rejects or misreads otherwise
# -- see docs/decisions.md.
SENSOR_BUILDERS = {
    CapabilityType.STRING: CozytouchSensor,
    CapabilityType.INT: CozytouchSensor,
    CapabilityType.CLIMATE: CozytouchSensor,
    CapabilityType.SWITCH: CozytouchBinarySensor,
    CapabilityType.BINARY: CozytouchBinarySensor,
    CapabilityType.AWAY_MODE_SWITCH: CozytouchAwayModeSensor,
    CapabilityType.AWAY_MODE_TIMESTAMPS: _away_mode_timestamps,
    CapabilityType.TIME: _unit(
        SensorDeviceClass.DURATION,
        SensorStateClass.MEASUREMENT,
        UnitOfTime.MINUTES,
    ),
    CapabilityType.TIMEZONE: CozytouchTimezoneSensor,
    CapabilityType.ERROR_CODE: CozytouchErrorCodeSensor,
    CapabilityType.PROG: CozytouchProgSensor,
    CapabilityType.PROGTIME: CozytouchProgTimeSensor,
    CapabilityType.ENERGY: _energy,
    CapabilityType.TEMPERATURE: _unit(
        SensorDeviceClass.TEMPERATURE,
        SensorStateClass.MEASUREMENT,
        UnitOfTemperature.CELSIUS,
    ),
    CapabilityType.PRESSURE: _unit(
        SensorDeviceClass.PRESSURE,
        SensorStateClass.MEASUREMENT,
        UnitOfPressure.BAR,
    ),
    CapabilityType.SIGNAL: _unit(
        SensorDeviceClass.SIGNAL_STRENGTH,
        SensorStateClass.MEASUREMENT,
        UnitOfSoundPressure.DECIBEL,
    ),
    CapabilityType.VOLUME: _unit(
        SensorDeviceClass.VOLUME_STORAGE,
        SensorStateClass.MEASUREMENT,
        UnitOfVolume.LITERS,
    ),
    CapabilityType.WATER_CONSUMPTION: _unit(
        SensorDeviceClass.WATER,
        SensorStateClass.TOTAL_INCREASING,
        UnitOfVolume.LITERS,
    ),
    CapabilityType.POWER: _unit(
        SensorDeviceClass.POWER,
        SensorStateClass.MEASUREMENT,
        UnitOfPower.KILO_WATT,
    ),
    CapabilityType.FLOW_RATE: _unit(
        SensorDeviceClass.VOLUME_FLOW_RATE,
        SensorStateClass.MEASUREMENT,
        UnitOfVolumeFlowRate.LITERS_PER_MINUTE,
    ),
    CapabilityType.PERCENTAGE: _unit(
        None,
        SensorStateClass.MEASUREMENT,
        PERCENTAGE,
    ),
}
