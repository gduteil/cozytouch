"""Calendars for Atlantic Cozytouch integration."""

from __future__ import annotations

from datetime import datetime, time, timedelta
import logging
import re
from typing import Any

from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEntityFeature,
    CalendarEvent,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN, PROGRAM_BLOCKS, WRITABLE_PROGRAM_BLOCKS
from .hub import CozytouchConfigEntry, CozytouchDeviceEntity, Hub
from .services import build_matrix, in_charge_at, parse_slots, slot_limit, where_stored

_LOGGER = logging.getLogger(__name__)

# How far either side of now to look when answering "what is running", which
# is a day each way rather than from midnight. See docs/decisions.md.
CURRENT_EVENT_WINDOW = timedelta(days=1)


# config flow setup
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: CozytouchConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entry."""
    for subentry_id in config_entry.subentries:
        hub = config_entry.runtime_data.hubs[subentry_id]

        calendars = [
            CozytouchProgramCalendar(
                coordinator=hub,
                config_uniq_id=subentry_id,
                program=program,
                first=first,
            )
            for program, first in (
                (program, where_stored(hub, program))
                for program in PROGRAM_BLOCKS
            )
            if first is not None
        ]

        if calendars:
            async_add_entities(calendars, True, config_subentry_id=subentry_id)


def _temperature_of(summary: str | None) -> float:
    """The setpoint somebody typed as an event title, however they spelt it."""
    try:
        return float(re.sub(r"[^0-9.,-]", "", summary or "").replace(",", "."))
    except ValueError:
        raise HomeAssistantError(
            f"{summary!r} carries no temperature: name the event after the "
            "setpoint it holds, for instance '19 °C'"
        ) from None


class CozytouchProgramCalendar(CozytouchDeviceEntity, CalendarEntity):
    """A weekly program, as the week it actually is.

    Editable where the device lets it be written : an event is one slot, and
    every edit lands on that weekday for good, since the week repeats. See
    docs/decisions.md.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: Hub,
        config_uniq_id: str,
        program: str,
        first: int,
    ) -> None:
        """Initialize a program calendar."""
        super().__init__(coordinator)

        self._program = program
        self._first_capability = first
        self._device_uniq_id = config_uniq_id
        # The service's words for these blocks, so one vocabulary covers all
        # three. See docs/decisions.md.
        self._attr_translation_key = f"{program}_program"
        self._attr_unique_id = f"{DOMAIN}_{config_uniq_id}_{program}_program"

        if program in WRITABLE_PROGRAM_BLOCKS:
            self._attr_supported_features = (
                CalendarEntityFeature.CREATE_EVENT
                | CalendarEntityFeature.DELETE_EVENT
                | CalendarEntityFeature.UPDATE_EVENT
            )

    @property
    def event(self) -> CalendarEvent | None:
        """The setpoint the program is holding right now."""
        now = dt_util.now()
        window = self._events_between(
            now - CURRENT_EVENT_WINDOW, now + CURRENT_EVENT_WINDOW
        )
        for event in window:
            if event.start <= now < event.end:
                return event

        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Every setpoint the program holds between two dates."""
        return self._events_between(start_date, end_date)

    def _events_between(
        self, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Expand the seven stored days over a range of real dates.

        Each slot becomes an event running until the next one, or until
        midnight for the last of a day. Local time throughout. See
        docs/decisions.md.
        """
        zone = dt_util.DEFAULT_TIME_ZONE
        day = dt_util.as_local(start_date).date()
        last = dt_util.as_local(end_date).date()

        # Once, not once per date : a card can ask for a year.
        programs = [self._slots_for(weekday) for weekday in range(7)]

        events: list[CalendarEvent] = []
        while day <= last:
            slots = programs[day.weekday()]
            for index, slot in enumerate(slots):
                start = datetime.combine(day, slot["time"], tzinfo=zone)

                if index + 1 < len(slots):
                    end = datetime.combine(day, slots[index + 1]["time"], tzinfo=zone)
                else:
                    # Held until the day runs out. See docs/decisions.md.
                    end = datetime.combine(
                        day + timedelta(days=1), time(0, 0), tzinfo=zone
                    )

                # Overlapping, not contained. See docs/decisions.md.
                if end > start_date and start < end_date:
                    events.append(
                        CalendarEvent(
                            start=start,
                            end=end,
                            summary=f"{slot['temperature']:g} °C",
                            uid=self._uid(day.weekday(), slot["time"]),
                        )
                    )

            day += timedelta(days=1)

        return events

    def _slots_for(self, weekday: int) -> list[dict]:
        """One day's slots, in time order, as times rather than strings."""
        capabilityId = self._first_capability + weekday
        stored = self.coordinator.get_capability_value(capabilityId, None)

        slots = []
        for slot in parse_slots(stored, capabilityId):
            try:
                hours, minutes = (int(part) for part in slot["time"].split(":"))
                slots.append(
                    {
                        "time": time(hours, minutes),
                        # A float here so a string setpoint raises here and
                        # not in the summary. See docs/decisions.md.
                        "temperature": float(slot["temperature"]),
                    }
                )
            except (TypeError, ValueError):
                # Dropped, so the rest of the day still renders.
                _LOGGER.debug(
                    "Unusable slot in program %s: %s", self._program, slot
                )

        return sorted(slots, key=lambda slot: slot["time"])

    def _uid(self, weekday: int, start: time) -> str:
        """Which slot an event is, which is a weekday and a start time."""
        return f"{self._program}-{weekday}-{start.hour * 60 + start.minute}"

    def _slot_of(self, uid: str) -> tuple[int, time]:
        """Read a uid back, refusing one this calendar did not write."""
        try:
            program, weekday, minute = uid.rsplit("-", 2)
            if program != self._program:
                raise ValueError
            hours, minutes = divmod(int(minute), 60)
            return int(weekday), time(hours, minutes)
        except ValueError:
            raise HomeAssistantError(
                f"{uid} is not a slot of the {self._program} program"
            ) from None

    async def async_create_event(self, **kwargs: Any) -> None:
        """Add a slot, and restore what ran after it at the event's end."""
        start = dt_util.as_local(kwargs["dtstart"])
        end = dt_util.as_local(kwargs["dtend"])
        temperature = _temperature_of(kwargs.get("summary"))

        weekday = start.weekday()
        stored = self._slots_for(weekday)
        # Read before the edit : it is what the day held where this event
        # stops, and what the next slot has to put back.
        after = in_charge_at(stored, end.time())

        slots = [slot for slot in stored if slot["time"] != start.time()]
        slots.append({"time": start.time(), "temperature": temperature})

        # An event ending mid-day means the drawn block ends there; midnight
        # or the next day means it runs to the end of the day, which is what
        # the last slot already does.
        ends_today = end.date() == start.date() and end.time() != time(0, 0)
        if (
            ends_today
            and after is not None
            and end.time() > start.time()
            and not any(slot["time"] == end.time() for slot in slots)
        ):
            slots.append({"time": end.time(), "temperature": after})

        await self._write(weekday, slots)

    async def async_delete_event(
        self,
        uid: str,
        recurrence_id: str | None = None,
        recurrence_range: str | None = None,
    ) -> None:
        """Drop a slot. The day keeps the one at 00:00. See docs/decisions.md."""
        weekday, start = self._slot_of(uid)
        if start == time(0, 0):
            raise HomeAssistantError(
                "The slot at 00:00 is what gives the beginning of the day a "
                "setpoint; change its temperature rather than deleting it"
            )

        slots = [
            slot for slot in self._slots_for(weekday) if slot["time"] != start
        ]
        await self._write(weekday, slots)

    async def async_update_event(
        self,
        uid: str,
        event: dict[str, Any],
        recurrence_id: str | None = None,
        recurrence_range: str | None = None,
    ) -> None:
        """Rewrite a slot, moving it off its old day first when it moved."""
        weekday, start = self._slot_of(uid)
        moved = dt_util.as_local(event["dtstart"])

        if (moved.weekday(), moved.time().replace(second=0, microsecond=0)) != (
            weekday,
            start,
        ):
            await self.async_delete_event(uid)

        await self.async_create_event(**event)

    async def _write(self, weekday: int, slots: list[dict]) -> None:
        """Store one day, refusing what the device would not hold."""
        limit = slot_limit(self.coordinator)
        if len(slots) > limit:
            raise HomeAssistantError(
                f"This device holds {limit} slots a day at most, "
                f"{len(slots)} would be written"
            )

        capabilityId = self._first_capability + weekday
        # build_matrix is set_schedule's, checks included : a first slot at
        # 00:00, no two slots at the same time.
        await self.coordinator.set_capability_value(
            capabilityId, build_matrix(slots)
        )
        await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Publish the program the poll just brought back."""
        self.async_write_ha_state()
