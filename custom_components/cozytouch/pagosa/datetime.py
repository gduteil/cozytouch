"""Pagosa clock and end of the Absence.

Carried from the pagosa-1.4 branch unchanged but for the hub it talks to.
"""

from __future__ import annotations

from datetime import datetime
import logging

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from ..const import DOMAIN
from .hub import PagosaHub as Hub

_LOGGER = logging.getLogger(__name__)


class PagosaDateTime(CoordinatorEntity[Hub], DateTimeEntity):
    """Date and time entity for Pagosa."""

    _attr_has_entity_name = True
    _attr_name = "Date et heure de l'appareil"
    _attr_icon = "mdi:calendar-clock"

    def __init__(
        self,
        coordinator: Hub,
        config_title: str,
        config_uniq_id: str,
    ) -> None:
        """Initialize Pagosa datetime entity."""
        super().__init__(coordinator)

        self._hub = coordinator
        self._attr_unique_id = f"{config_uniq_id}_pagosa_datetime"

        device = coordinator.get_overkiz_device() or {}

        self._attr_device_info = DeviceInfo(
            identifiers={
                (DOMAIN, str(device.get("deviceURL", config_uniq_id)))
            },
            name=device.get("label") or config_title or "Sauter Pagosa 270L",
            manufacturer="Sauter",
            model="Pagosa 270L",
        )

    @property
    def available(self) -> bool:
        """Return entity availability."""
        return (
            self._hub.online
            and self._hub.last_update_success
        )

    @property
    def native_value(self) -> datetime | None:
        """Return the Pagosa date and time."""
        value = self._hub.get_overkiz_state("core:DateTimeState")

        if not isinstance(value, dict):
            return None

        try:
            return datetime(
                year=int(value["year"]),
                month=int(value["month"]),
                day=int(value["day"]),
                hour=int(value["hour"]),
                minute=int(value["minute"]),
                second=int(value.get("second", 0)),
                tzinfo=dt_util.DEFAULT_TIME_ZONE,
            )
        except (KeyError, TypeError, ValueError):
            _LOGGER.warning("Invalid Pagosa DateTimeState: %s", value)
            return None

    async def async_set_value(self, value: datetime) -> None:
        """Set the Pagosa date and time."""
        local_value = dt_util.as_local(value)

        parameters = {
            "year": local_value.year,
            "month": local_value.month,
            "day": local_value.day,
            "weekday": local_value.weekday(),
            "hour": local_value.hour,
            "minute": local_value.minute,
            "second": local_value.second,
        }

        await self._hub.async_execute_overkiz_command(
            "setDateTime",
            [parameters],
            label="Pagosa réglage date et heure",
            refresh=False,
        )

        await self._hub._refresh_overkiz_setup()
        await self._hub.async_request_refresh()


class PagosaAbsenceEndDateTime(CoordinatorEntity[Hub], DateTimeEntity):
    """End of the Pagosa Absence period (moved without stopping it)."""

    _attr_has_entity_name = True
    _attr_name = "Fin de l'absence"
    _attr_icon = "mdi:calendar-end"

    def __init__(
        self,
        coordinator: Hub,
        config_title: str,
        config_uniq_id: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._hub = coordinator
        self._attr_unique_id = f"{config_uniq_id}_pagosa_absence_end"
        device = coordinator.get_overkiz_device() or {}
        self._attr_device_info = DeviceInfo(
            identifiers={
                (DOMAIN, str(device.get("deviceURL", config_uniq_id)))
            },
            name=device.get("label") or config_title or "Sauter Pagosa 270L",
            manufacturer="Sauter",
            model="Pagosa 270L",
        )

    @property
    def available(self) -> bool:
        """Return entity availability."""
        return self._hub.online and self._hub.last_update_success

    @property
    def native_value(self) -> datetime | None:
        """Return the end of the Absence, if one is set."""
        window = self._hub.pagosa_absence_window()
        if window is None:
            return None
        end = datetime.fromtimestamp(window[1], tz=dt_util.DEFAULT_TIME_ZONE)
        return end if end > dt_util.now() else None

    async def async_set_value(self, value: datetime) -> None:
        """Move the end of the Absence (in the past = stop it now)."""
        await self._hub.pagosa_set_absence_end(int(value.timestamp()))
        self.async_write_ha_state()



async def async_setup_pagosa(
    hub: Hub,
    config_entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add this platform's Pagosa entities ; config_entry is a PagosaContext."""
    datetimes = []
    device = hub.get_overkiz_device()

    if device and hub.get_overkiz_state("core:DateTimeState") is not None:
        datetimes.append(
            PagosaDateTime(
                coordinator=hub,
                config_title=config_entry.title,
                config_uniq_id=config_entry.entry_id,
            )
        )
    if device and hasattr(hub, "pagosa_absence_window"):
        datetimes.append(
            PagosaAbsenceEndDateTime(
                coordinator=hub,
                config_title=config_entry.title,
                config_uniq_id=config_entry.entry_id,
            )
        )

    if datetimes:
        async_add_entities(datetimes, True)
