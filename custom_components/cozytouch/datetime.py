"""Date/Time for Atlantic Cozytouch integration."""
from __future__ import annotations

from datetime import datetime, time
import logging
import time

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN, CozytouchCapabilityVariableType
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
            "%s: can not init selects: failed to get the hub object",
            config_entry.title,
        )
        return

    # Init datetimes
    datetimes = []
    capabilities = hub.get_capabilities_for_device()
    for capability in capabilities:
        if capability["type"] == "away_mode_timestamps":
            datetimes.append(
                CozytouchAwayModeDateTime(
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
            datetimes.append(
                CozytouchAwayModeDateTime(
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

    # Add the entities to HA
    if len(datetimes) > 0:
        async_add_entities(datetimes, True)


class CozytouchDateTime(DateTimeEntity, CozytouchSensor):
    """Class for datetime entity."""

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
        """Initialize a datetime Sensor."""
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

    async def async_set_value(self, value: datetime) -> None:
        """Update the current value."""
        oldValue = self.coordinator.get_capability_value(
            self._capability["capabilityId"]
        )
        if oldValue is not None:
            oldValue = oldValue.translate(str.maketrans("", "", "[]"))
            oldTimestamps = oldValue.split(self._separator, 2)
            if self._timestamp_index < len(oldTimestamps):
                oldTimestamps[self._timestamp_index] = str(int(value.timestamp()))

            newValue = "[" + ",".join(oldTimestamps) + "]"
            await self.coordinator.set_capability_value(
                self._capability["capabilityId"], newValue
            )

    @property
    def value(self) -> datetime | None:
        """Retrieve value from hub."""
        value = self.coordinator.get_capability_value(self._capability["capabilityId"])
        if value is not None:
            value = value.translate(str.maketrans("", "", "[]"))
            timestamps = value.split(self._separator, 2)
            if self._timestamp_index < len(timestamps):
                timestamp = int(timestamps[self._timestamp_index])
                if timestamp > 0:
                    return datetime.fromtimestamp(
                        int(timestamp), tz=dt_util.DEFAULT_TIME_ZONE
                    )

                return None


class CozytouchAwayModeDateTime(DateTimeEntity, CozytouchSensor):
    """Class for away mode datetime entity."""

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
        """Initialize a datetime Sensor."""
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

    async def async_set_value(self, value: datetime) -> None:
        """Update the current value."""
        timestamp = value.timestamp()
        if timestamp is not None:
            if self._timestamp_index == 0:
                await self.coordinator.set_away_mode_start(
                    self._capability["capabilityId"], int(timestamp)
                )
            elif self._timestamp_index == 1:
                await self.coordinator.set_away_mode_end(
                    self._capability["capabilityId"], int(timestamp)
                )

    @property
    def native_value(self) -> datetime | None:
        """Retrieve value from hub."""
        value = None
        if self._timestamp_index == 0:
            value = self.coordinator.get_away_mode_start()
        elif self._timestamp_index == 1:
            value = self.coordinator.get_away_mode_end()

        if value is not None:
            if value > 0:
                return datetime.fromtimestamp(value, tz=dt_util.DEFAULT_TIME_ZONE)

        return None
