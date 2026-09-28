"""Services for the Atlantic Cozytouch integration."""

from __future__ import annotations

from datetime import datetime, time, timedelta
import json
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.util import dt as dt_util

from .capability import read_setpoint
from .const import (
    DOMAIN,
    PROGRAM_BLOCKS,
    PROGRAM_DAYS,
    WRITABLE_PROGRAM_BLOCKS,
    stored_in,
)

_LOGGER = logging.getLogger(__name__)

SERVICE_SET_SCHEDULE = "set_schedule"
SERVICE_GET_SCHEDULE = "get_schedule"
SERVICE_SET_AWAY_MODE = "set_away_mode"
SERVICE_CLEAR_AWAY_MODE = "clear_away_mode"

# Shortcuts the day picker offers next to the seven days. Expanded here rather
# than in the frontend, so a YAML automation gets them too.
DAY_GROUPS = {
    "all": PROGRAM_DAYS,
    "weekdays": PROGRAM_DAYS[:5],
    "weekend": PROGRAM_DAYS[5:],
}

# The device always stores ten slots, unused ones being [0,0].
MAX_SLOTS = 10

# The device advertises how many slots a day may hold. Its encoding has never
# been confirmed against a capture, so it is only ever allowed to tighten the
# check, never to change the matrix that gets written.
SLOTS_PER_DAY_CAPABILITY = 306


def expand_days(days: list[str]) -> list[str]:
    """Turn the group shortcuts into the days they stand for.

    Public because llm.py merges a period into one day at a time, so it needs
    the days a shortcut stands for before it can read them.

    Runs as the last step of the validator so that everything downstream only
    ever sees a day name, and so "weekend" plus "sunday" -- or "monday" twice
    -- still writes each capability once.
    """
    named = {day for item in days for day in DAY_GROUPS.get(item, [item])}
    return [day for day in PROGRAM_DAYS if day in named]


SET_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_ids,
        vol.Required("program"): vol.In(WRITABLE_PROGRAM_BLOCKS),
        # vol.All is a pipeline, so the length check has to run before the
        # expansion -- afterwards a group has already become several days,
        # and an empty list is the only thing left that it could catch.
        vol.Required("days"): vol.All(
            cv.ensure_list,
            vol.Length(min=1),
            [vol.In([*PROGRAM_DAYS, *DAY_GROUPS])],
            expand_days,
        ),
        vol.Required("slots"): vol.All(
            cv.ensure_list,
            vol.Length(min=1, max=MAX_SLOTS),
            [
                vol.Schema(
                    {
                        vol.Required("time"): cv.time,
                        vol.Required("temperature"): vol.Coerce(float),
                    }
                )
            ],
        ),
    }
)

GET_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_ids,
        vol.Required("program"): vol.In(WRITABLE_PROGRAM_BLOCKS),
    }
)


SET_AWAY_MODE_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Required("entity_id"): cv.entity_ids,
            vol.Optional("start"): cv.datetime,
            vol.Exclusive("end", "return"): cv.datetime,
            vol.Exclusive("duration", "return"): cv.positive_time_period,
        }
    ),
    cv.has_at_least_one_key("end", "duration"),
)

CLEAR_AWAY_MODE_SCHEMA = vol.Schema({vol.Required("entity_id"): cv.entity_ids})

# Where a window with no start begins, as the switch does.
AWAY_MODE_LEAD = timedelta(minutes=1)


def away_window(data: dict, now: datetime) -> tuple[int, int]:
    """The two timestamps a set_away_mode call stands for.

    A naive date is the Home Assistant time zone's, which is what the date
    picker and a template both mean by one.
    """
    start = data.get("start", now + AWAY_MODE_LEAD)
    end = data["end"] if "end" in data else start + data["duration"]

    timestampStart = int(dt_util.as_timestamp(start))
    timestampEnd = int(dt_util.as_timestamp(end))

    if timestampEnd <= timestampStart:
        raise ServiceValidationError("The absence has to end after it starts")

    if timestampEnd <= now.timestamp():
        raise ServiceValidationError("That absence would already be over")

    return timestampStart, timestampEnd


def _away_hubs(hass: HomeAssistant, entity_ids: list[str]) -> list:
    """One hub per account among the targets, refusing a device with no switch.

    The window is the account's, so two targets on one account are one write.
    """
    hubs: dict[int, Any] = {}
    for entity_id in entity_ids:
        hub = _resolve_hub(hass, entity_id)
        if not hub.away_mode_switches():
            raise ServiceValidationError(
                f"{entity_id} is on a device that does not switch the absence; "
                "target the away mode switch of its gateway"
            )

        hubs.setdefault(id(hub.account), hub)

    return list(hubs.values())


def _as_time(value: time | str) -> time:
    """A slot time, however the caller holds it.

    `parse_slots` renders "HH:MM" because that is what a service response and
    the card speak; `build_matrix` and the calendar hold a `time`.
    """
    return value if isinstance(value, time) else time.fromisoformat(value)


def build_matrix(slots: list[dict]) -> str:
    """Turn slots into the [[minutes,temperature],...] string the device stores.

    Public because calendar.py writes programs through it too, so the two
    cannot disagree about what a day may hold.
    """
    entries = sorted(
        (
            (slot["time"].hour * 60 + slot["time"].minute, slot["temperature"])
            for slot in slots
        ),
        key=lambda entry: entry[0],
    )

    minutes = [entry[0] for entry in entries]
    # Unreachable through the service, which requires one slot, but reachable
    # from anything else that calls this: minutes[0] below is indexed blind.
    if not minutes:
        raise ServiceValidationError("A day program needs at least one slot")

    if len(set(minutes)) != len(minutes):
        raise ServiceValidationError("Two slots share the same time")

    if minutes[0] != 0:
        raise ServiceValidationError(
            "The first slot must start at 00:00, otherwise the beginning of the "
            "day would have no target temperature"
        )

    matrix = [
        [minute, int(temperature) if temperature == int(temperature) else temperature]
        for minute, temperature in entries
    ]
    matrix += [[0, 0]] * (MAX_SLOTS - len(matrix))

    return json.dumps(matrix, separators=(",", ":"))


def parse_slots(value: str | None, capabilityId: int | None = None) -> list[dict]:
    """Read a stored program back into the slots set_schedule takes.

    Public because calendar.py reads programs through it too, so the two cannot
    disagree about what a day holds. A pair of zeroes ends the day : a real
    midnight slot carries a target temperature, never 0 °C.
    """
    try:
        entries = json.loads(value)
    except (TypeError, ValueError):
        return []

    if not isinstance(entries, list):
        return []

    slots: list[dict] = []
    for entry in entries:
        if not isinstance(entry, list) or len(entry) < 2:
            continue

        minute, temperature = entry[0], read_setpoint(capabilityId, entry[1])
        if minute == 0 and temperature == 0:
            break

        hours, minutes = divmod(int(minute), 60)
        slots.append({"time": f"{hours:02d}:{minutes:02d}", "temperature": temperature})

    return slots


def in_charge_at(slots: list[dict], moment: time) -> float | None:
    """The setpoint a day holds at a time, which is the last slot before it."""
    held = None
    for slot in slots:
        if _as_time(slot["time"]) <= moment:
            held = slot["temperature"]

    return held


def apply_period(
    slots: list[dict],
    start: time | str,
    end: time | str,
    temperature: float,
) -> list[dict]:
    """Hold one temperature between two times, leaving the rest of the day.

    A device stores a whole day and a person asks about a stretch of one, so
    what this is really for is the slots *outside* the stretch : they have to
    survive being asked about the ones inside it. The slot that closes the
    stretch carries whatever was in charge there before, which is what makes
    "24 degrees until 17:00" leave 17:00 onwards alone.

    Midnight as an end means the end of the day, since a stretch that runs to
    00:00 is the last one and has nothing to put back after it.
    """
    started, ended = _as_time(start), _as_time(end)
    closes_the_day = ended == time(0, 0)
    if not closes_the_day and ended <= started:
        raise ServiceValidationError(
            f"A period has to end after it starts, and {ended:%H:%M} is not "
            f"after {started:%H:%M}"
        )

    # Read before the edit : it is what the day held where the period stops.
    held = in_charge_at(slots, ended)

    kept = [
        {"time": _as_time(slot["time"]), "temperature": slot["temperature"]}
        for slot in slots
        if not (
            _as_time(slot["time"]) >= started
            and (closes_the_day or _as_time(slot["time"]) < ended)
        )
    ]
    kept.append({"time": started, "temperature": temperature})
    # A day that already turns at the end of the period needs nothing put
    # back, and a second slot at that time is what build_matrix refuses.
    if (
        not closes_the_day
        and held is not None
        and not any(slot["time"] == ended for slot in kept)
    ):
        kept.append({"time": ended, "temperature": held})

    ordered = sorted(kept, key=lambda slot: slot["time"])

    # A day holds ten slots, so a slot asking for what is already running is
    # not free : it is one fewer left for a period that would change
    # something. The 00:00 slot is never the redundant one -- nothing runs
    # before it.
    return [
        slot
        for index, slot in enumerate(ordered)
        if index == 0 or slot["temperature"] != ordered[index - 1]["temperature"]
    ]


def slot_limit(hub) -> int:
    """How many slots a day may hold on this device.

    Public for the same reason as build_matrix above.

    Capability 306 is self-describing and its encoding is unverified, so it is
    trusted only when it reads as a plain count, and only to lower the ceiling.
    Anything else leaves the ten slots every working install writes today.
    """
    value = hub.get_capability_value(SLOTS_PER_DAY_CAPABILITY, None)

    try:
        limit = int(value)
    except (TypeError, ValueError):
        return MAX_SLOTS

    if limit < 2:
        return MAX_SLOTS

    return min(limit, MAX_SLOTS)


def _resolve_hub(hass: HomeAssistant, entity_id: str):
    """Find the hub behind an entity."""
    registry_entry = er.async_get(hass).async_get(entity_id)
    if registry_entry is None:
        raise ServiceValidationError(
            f"There is no entity called {entity_id}. Check the exact id in "
            "Developer tools > States -- renaming an entity does not change it."
        )

    # Two separate things to rule out, which the old hass.data lookup conflated:
    # an entity from another integration, and one of ours whose entry is not
    # loaded and therefore has no hub on it yet.
    entry = hass.config_entries.async_get_entry(registry_entry.config_entry_id or "")
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            f"{entity_id} is provided by {registry_entry.platform}, not by "
            "Cozytouch"
        )

    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            f"The Cozytouch entry behind {entity_id} is not loaded ({entry.state})"
        )

    # A device is a subentry of its account, and the hub that drives it is
    # keyed on that subentry. An entity with no subentry is one this
    # integration did not build under the shape it builds them today.
    hub = entry.runtime_data.hubs.get(registry_entry.config_subentry_id or "")
    if hub is None:
        raise ServiceValidationError(
            f"{entity_id} is not attached to a Cozytouch device this entry "
            "drives; remove it and add the device again"
        )

    return hub


def where_stored(hub, program: str) -> int | None:
    """Which run of seven this device holds a program in, or None."""
    return stored_in(
        program,
        lambda capabilityId: hub.get_capability_value(capabilityId, None) is not None,
    )


def _block_of(hub, entity_id: str, program: str) -> int:
    """Where this device stores a program, refusing one it does not hold."""
    first = where_stored(hub, program)
    if first is None:
        runs = " or ".join(str(candidate) for candidate in PROGRAM_BLOCKS[program])
        raise ServiceValidationError(
            f"{entity_id} reports no {program} program: it starts none of the "
            f"seven-day runs at {runs}"
        )

    return first


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Register the integration services, once for all config entries."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_SCHEDULE):
        return

    async def async_set_schedule(call: ServiceCall) -> None:
        """Write the same day program to every requested day."""
        slots = call.data["slots"]
        value = build_matrix(slots)
        program = call.data["program"]

        for entity_id in call.data["entity_id"]:
            hub = _resolve_hub(hass, entity_id)
            first = _block_of(hub, entity_id, program)

            limit = slot_limit(hub)
            if len(slots) > limit:
                raise ServiceValidationError(
                    f"{entity_id} holds {limit} slots a day at most, "
                    f"{len(slots)} were given"
                )

            for day in call.data["days"]:
                capabilityId = first + PROGRAM_DAYS.index(day)
                _LOGGER.debug(
                    "set_schedule %s %s %s -> capability %d = %s",
                    entity_id,
                    program,
                    day,
                    capabilityId,
                    value,
                )
                await hub.set_capability_value(capabilityId, value)

            await hub.async_request_refresh()

    async def async_get_schedule(call: ServiceCall) -> ServiceResponse:
        """Read a whole week back, in the shape set_schedule takes."""
        program = call.data["program"]

        response: dict[str, Any] = {}
        for entity_id in call.data["entity_id"]:
            hub = _resolve_hub(hass, entity_id)
            first = _block_of(hub, entity_id, program)

            days = {}
            for index, day in enumerate(PROGRAM_DAYS):
                # The default is the string "0", which parses as a number
                # rather than a matrix; None is what makes a device that does
                # not have this program tellable from one whose day is empty.
                value = hub.get_capability_value(first + index, None)
                if value is not None:
                    days[day] = parse_slots(value, first + index)

            response[entity_id] = {"program": program, "days": days}

        return response

    async def async_set_away_mode(call: ServiceCall) -> None:
        """Send the window and switch the absence on, as one action."""
        timestampStart, timestampEnd = away_window(
            call.data, dt_util.now()
        )

        for hub in _away_hubs(hass, call.data["entity_id"]):
            if not await hub.set_away_mode(timestampStart, timestampEnd):
                raise HomeAssistantError(
                    "Atlantic did not accept the absence; the log says why"
                )

    async def async_clear_away_mode(call: ServiceCall) -> None:
        """Switch the absence off, window included."""
        for hub in _away_hubs(hass, call.data["entity_id"]):
            if not await hub.set_away_mode(None, None):
                raise HomeAssistantError(
                    "Atlantic did not accept the end of the absence; the log "
                    "says why"
                )

    hass.services.async_register(
        DOMAIN, SERVICE_SET_SCHEDULE, async_set_schedule, schema=SET_SCHEDULE_SCHEMA
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_AWAY_MODE,
        async_set_away_mode,
        schema=SET_AWAY_MODE_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_AWAY_MODE,
        async_clear_away_mode,
        schema=CLEAR_AWAY_MODE_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_SCHEDULE,
        async_get_schedule,
        schema=GET_SCHEDULE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
