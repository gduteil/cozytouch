"""Time for Atlantic Cozytouch integration."""
from __future__ import annotations

from datetime import datetime, time
import logging
import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
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

    # Init times
    times = []
    capabilities = hub.get_capabilities_for_device()
    for capability in capabilities:
        if capability["type"] == "time_adjustment":
            times.append(
                CozytouchTime(
                    coordinator=hub,
                    capability=capability,
                    config_title=config_entry.title,
                    config_uniq_id=config_entry.entry_id,
                )
            )

    # Add the entities to HA
    if len(times) > 0:
        async_add_entities(times, True)


class CozytouchTime(TimeEntity, CozytouchSensor):
    """Class for time entity."""

    def __init__(
        self,
        coordinator: Hub,
        capability,
        config_title: str,
        config_uniq_id: str,
        name: str | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialize a Time entity."""
        super().__init__(
            coordinator=coordinator,
            capability=capability,
            config_title=config_title,
            config_uniq_id=config_uniq_id,
            name=name,
            icon=icon,
        )

    async def async_set_value(self, value: time) -> None:
        """Update the current value."""
        minutes = (value.hour * 60) + value.minute
        await self.coordinator.set_capability_value(
            self._capability["capabilityId"],
            str(minutes),
        )

    @property
    def native_value(self) -> time | None:
        """Retrieve value from hub."""
        value = int(
            self.coordinator.get_capability_value(self._capability["capabilityId"])
        )
        hours = 0
        minutes = value
        if value >= 60:
            hours = int(minutes / 60)
            minutes -= hours * 60

        return datetime.time(hours, int(minutes), 0)
