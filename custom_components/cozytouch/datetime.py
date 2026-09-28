"""Date/Time for Atlantic Cozytouch integration."""
from __future__ import annotations

from datetime import datetime
import logging

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import CozytouchCapabilityVariableType
from .hub import CozytouchConfigEntry, Hub, add_capability_entities
from .infos import CapabilityType
from .sensor import CozytouchSensor

_LOGGER = logging.getLogger(__name__)


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
        {CapabilityType.AWAY_MODE_TIMESTAMPS: _away_mode_datetimes},
    )


def _away_mode_datetimes(
    coordinator: Hub, capability, config_title: str, config_uniq_id: str
) -> list[CozytouchAwayModeDateTime]:
    """The two ends of the away window, which are one capability."""
    # The switch is what sends a window : a device reporting the pair without
    # one can be read, not set. See docs/decisions.md.
    if not coordinator.away_mode_switches():
        return []

    return [
        CozytouchAwayModeDateTime(
            capability=capability,
            config_title=config_title,
            config_uniq_id=config_uniq_id,
            attr_uniq_id=f"{config_uniq_id}_{index}",
            coordinator=coordinator,
            translation_key=timestamp.name,
            icon=timestamp.icon,
            timestamp_index=index,
        )
        for index, timestamp in enumerate(capability.timestamps)
    ]


class CozytouchAwayModeDateTime(DateTimeEntity, CozytouchSensor):
    """Class for away mode datetime entity."""

    def __init__(
        self,
        capability,
        config_title: str,
        config_uniq_id: str,
        coordinator: Hub,
        translation_key: str | None = None,
        icon: str | None = None,
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
            translation_key=translation_key,
            icon=icon,
            value_type=CozytouchCapabilityVariableType.STRING,
        )
        self._timestamp_index = timestamp_index

    async def async_set_value(self, value: datetime) -> None:
        """Update the current value."""
        timestamp = value.timestamp()
        if timestamp is not None and self._timestamp_index in (0, 1):
            await self.coordinator.set_away_mode_bound(
                self._timestamp_index, int(timestamp)
            )
            self.async_write_ha_state()

    @property
    def native_value(self) -> datetime | None:
        """Retrieve value from hub.

        While the absence is off, a start that is not set or already past
        reads as now, and an end already past as unknown : that is the window
        the switch would send. See docs/decisions.md.
        """
        value = None
        if self._timestamp_index == 0:
            value = self.coordinator.get_away_mode_start()
        elif self._timestamp_index == 1:
            value = self.coordinator.get_away_mode_end()

        if not self.coordinator.is_away():
            now = dt_util.now().replace(second=0, microsecond=0)
            if self._timestamp_index == 0 and (
                not value or value < now.timestamp()
            ):
                return now
            if self._timestamp_index == 1 and value and value <= now.timestamp():
                return None

        if value is not None and value > 0:
            return datetime.fromtimestamp(value, tz=dt_util.DEFAULT_TIME_ZONE)

        return None
