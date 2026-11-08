"""Pagosa Absence calendar (48 h minimum).

Carried from the pagosa-1.4 branch unchanged but for the hub it talks to.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
import math

from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEntityFeature,
    CalendarEvent,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from ..const import DOMAIN
from .hub import PagosaHub as Hub

_LOGGER = logging.getLogger(__name__)


_LOGGER = logging.getLogger(__name__)

EVENT_UID = "pagosa-absence"
MIN_DURATION = timedelta(hours=47, minutes=59)  # the app requires 48 h
START_TOLERANCE = timedelta(minutes=2)  # "now" for an immediate start


def _to_datetime(value: date | datetime) -> datetime:
    """Return a timezone aware datetime (a date means local midnight)."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return datetime(
        value.year, value.month, value.day, tzinfo=dt_util.DEFAULT_TIME_ZONE
    )


def absence_window_from_event(
    dtstart: date | datetime,
    dtend: date | datetime,
    now: datetime,
    max_days: int,
) -> tuple[datetime, datetime, bool]:
    """Validate an event and return (start, end, immediate)."""
    start = _to_datetime(dtstart)
    end = _to_datetime(dtend)

    if end <= now:
        raise HomeAssistantError("The Absence cannot end in the past.")

    immediate = start <= now + START_TOLERANCE
    if immediate:
        start = now

    if end - start < MIN_DURATION:
        raise HomeAssistantError("An Absence lasts at least 48 hours (2 days) minimum.")
    if end - start > timedelta(days=max_days):
        raise HomeAssistantError(f"An Absence lasts at most {max_days} days.")

    return start, end, immediate


class PagosaAbsenceCalendar(CoordinatorEntity[Hub], CalendarEntity):
    """The Pagosa Absence period."""

    _attr_has_entity_name = True
    _attr_name = "Absence (48 h minimum)"
    _attr_icon = "mdi:calendar-account"
    _attr_supported_features = (
        CalendarEntityFeature.CREATE_EVENT | CalendarEntityFeature.DELETE_EVENT
    )

    def __init__(self, coordinator: Hub, config_title: str, config_uniq_id: str) -> None:
        """Initialize the calendar."""
        super().__init__(coordinator)
        self._hub = coordinator
        self._attr_unique_id = f"{DOMAIN}_{config_uniq_id}_pagosa_absence_calendar"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(coordinator._deviceId))},
            manufacturer="Sauter",
            model="Pagosa 270L",
            name=config_title,
        )

    @property
    def available(self) -> bool:
        """Return entity availability."""
        return self._hub.online and self._hub.last_update_success

    def _window_event(self) -> CalendarEvent | None:
        window = self._hub.pagosa_absence_window()
        if window is None:
            return None
        start = datetime.fromtimestamp(window[0], tz=dt_util.DEFAULT_TIME_ZONE)
        end = datetime.fromtimestamp(window[1], tz=dt_util.DEFAULT_TIME_ZONE)
        days = max(1, round((end - start).total_seconds() / 86400))
        return CalendarEvent(
            start=start,
            end=end,
            summary="Absence",
            description=f"Absence du chauffe-eau ({days} j)",
            uid=EVENT_UID,
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Return the Absence under way or the next one."""
        event = self._window_event()
        if event is None or event.end <= dt_util.now():
            return None
        return event

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return the Absence if it overlaps the requested range."""
        await self._hub.pagosa_refresh_absence()
        event = self._window_event()
        if event is None or event.end <= start_date or event.start >= end_date:
            return []
        return [event]

    @callback
    def _handle_coordinator_update(self) -> None:
        """Re-read the Atlantic setup now and then, then update the state."""
        self.hass.async_create_task(self._async_refresh_and_write())

    async def _async_refresh_and_write(self) -> None:
        await self._hub.pagosa_refresh_absence()
        self.async_write_ha_state()

    async def async_create_event(self, **kwargs) -> None:
        """Start or program the Absence."""
        if kwargs.get("rrule"):
            raise HomeAssistantError("A repeating Absence is not supported.")
        if self._hub.pagosa_absence_window() is not None:
            existing = self._window_event()
            if existing is not None and existing.end > dt_util.now():
                raise HomeAssistantError(
                    "An Absence is already set. Delete it first."
                )

        from .pagosa_absence import PAGOSA_ABSENCE_MAX_DAYS

        start, end, immediate = absence_window_from_event(
            kwargs["dtstart"],
            kwargs["dtend"],
            dt_util.now(),
            PAGOSA_ABSENCE_MAX_DAYS,
        )

        if immediate:
            days = max(2, math.ceil((end - start).total_seconds() / 86400))
            await self._hub.async_set_pagosa_away(
                True,
                days=days,
                start=int(start.timestamp()),
                end=int(end.timestamp()),
            )
        else:
            await self._hub.pagosa_program_absence(
                int(start.timestamp()), int(end.timestamp())
            )
        self.async_write_ha_state()

    async def async_delete_event(
        self,
        uid: str,
        recurrence_id: str | None = None,
        recurrence_range: str | None = None,
    ) -> None:
        """Stop the Absence."""
        if uid != EVENT_UID:
            raise HomeAssistantError("Unknown event.")
        await self._hub.async_set_pagosa_away(False)
        self.async_write_ha_state()



async def async_setup_pagosa(
    hub: Hub,
    config_entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add this platform's Pagosa entities ; config_entry is a PagosaContext."""
    async_add_entities(
        [PagosaAbsenceCalendar(hub, config_entry.title, config_entry.entry_id)]
    )
