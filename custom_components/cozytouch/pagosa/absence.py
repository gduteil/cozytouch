"""Absence handling for the Sauter/Atlantic Pagosa (Overkiz devices).

The Atlantic app stores the absence period (calendar) in the Cozytouch
setup (PUT /magellan/v2/setups/<id> with ``absence.startDate`` and
``absence.endDate``) and then sends two Overkiz commands:

    setCurrentOperatingMode({"relaunch": ..., "absence": "on"|"off"})
    setAwayModeDuration(days)            (0 to stop; 2 days minimum)

Only the Overkiz commands were sent before, which left the absence
half applied. This module replaces the two Pagosa absence methods of
``Hub`` and does not change any other device.
"""

from __future__ import annotations

import copy
import logging
import math
import time

from homeassistant import exceptions

from ..const import COZYTOUCH_ATLANTIC_API
from .hub import PagosaHub as Hub

_LOGGER = logging.getLogger(__name__)

PAGOSA_ABSENCE_MIN_DAYS = 2
PAGOSA_ABSENCE_MAX_DAYS = 90
ABSENCE_REFRESH_INTERVAL = 1800  # seconds

_SETUP_KEYS = (
    "address",
    "area",
    "currency",
    "mainHeatingEnergy",
    "mainDHWEnergy",
    "name",
    "numberOfPersons",
    "numberOfRooms",
    "setupBuildingDate",
    "type",
)


async def _ensure_atlantic_setup(self: Hub) -> None:
    """Make sure the Atlantic setup (id and description) is known."""
    if self._setup.get("id") is not None:
        return

    async with self._session.get(
        COZYTOUCH_ATLANTIC_API + "/magellan/cozytouch/setupviewv2",
        headers={
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        },
    ) as response:
        if response.status != 200:
            raise exceptions.HomeAssistantError(
                f"Atlantic setup unavailable (HTTP {response.status})"
            )
        data = await response.json(content_type=None)

    if not isinstance(data, list) or not data or "id" not in data[0]:
        raise exceptions.HomeAssistantError("Atlantic setup not found")

    for key in ("id", *_SETUP_KEYS):
        if key in data[0]:
            self._setup[key] = copy.deepcopy(data[0][key])


async def _put_atlantic_absence(
    self: Hub, start: int | None, end: int | None
) -> None:
    """Write (or clear) the absence period in the Atlantic setup."""
    if not await self._authenticate_atlantic():
        raise exceptions.HomeAssistantError("Atlantic authentication failed")

    await _ensure_atlantic_setup(self)

    body = {
        key: copy.deepcopy(self._setup[key])
        for key in _SETUP_KEYS
        if key in self._setup
    }
    body["absence"] = (
        {} if start is None else {"startDate": start, "endDate": end}
    )

    async with self._session.put(
        COZYTOUCH_ATLANTIC_API + "/magellan/v2/setups/" + str(self._setup["id"]),
        json=body,
        headers={
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        },
    ) as response:
        if response.status not in (200, 204):
            raise exceptions.HomeAssistantError(
                f"Atlantic absence update failed (HTTP {response.status})"
            )

    self._setup["absence"] = body["absence"]


def _planned_days(self: Hub) -> int | None:
    """Duration chosen in Home Assistant for the next Absence, if any."""
    return getattr(self, "_pagosa_planned_away_days", None)


def _is_absent(self: Hub) -> bool:
    return self._get_current_operating_mode().get("absence") == "on"


def _current_away_days(self: Hub) -> int:
    """Return the duration to use: the planned one, else the Pagosa's."""
    planned = _planned_days(self)
    if planned:
        return planned
    value = self.get_overkiz_state("io:AwayModeDurationState", "0")
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


async def async_set_pagosa_away(
    self: Hub,
    enabled: bool,
    days: int | None = None,
    start: int | None = None,
    end: int | None = None,
) -> None:
    """Start or stop the Pagosa Absence like the Atlantic app does."""
    current = self._get_current_operating_mode()
    current["absence"] = "on" if enabled else "off"

    if enabled:
        if days is None:
            days = _current_away_days(self)
        days = int(days)
        if days < PAGOSA_ABSENCE_MIN_DAYS:
            days = PAGOSA_ABSENCE_MIN_DAYS
        if days > PAGOSA_ABSENCE_MAX_DAYS:
            raise exceptions.HomeAssistantError(
                f"Absence duration must be at most {PAGOSA_ABSENCE_MAX_DAYS} days"
            )
    else:
        days = 0
        self._pagosa_planned_away_days = None

    async def operation():
        if enabled:
            window_start = start or int(time.time())
            window_end = end or window_start + days * 86400
            await _put_atlantic_absence(self, window_start, window_end)
        else:
            await _put_atlantic_absence(self, None, None)

        # Same order as the Atlantic app: mode first, then duration.
        await self._set_operating_mode_flag(
            "absence", "on" if enabled else "off"
        )
        await self.async_execute_overkiz_command(
            "setAwayModeDuration",
            [days],
            label="Set Pagosa Absence duration",
            refresh=False,
        )
        await self.async_execute_overkiz_command(
            "refreshCurrentOperatingMode", refresh=False
        )
        await self.async_execute_overkiz_command(
            "refreshAwayModeDuration", refresh=False
        )

    # No optimistic state: the Pagosa rejects setCurrentOperatingMode for the
    # Absence (ERRORCOMMAND, also from the official app). The Atlantic cloud
    # applies the period written in the setup by itself (about 1 h later), so
    # the switch must show the real state only.
    await self.async_run_pagosa_operation(operation, None, "Pagosa Absence")


async def set_overkiz_away_duration(self: Hub, value: int) -> None:
    """Set the Pagosa Absence duration in days (0 stops the Absence)."""
    value = int(value)

    if value and not PAGOSA_ABSENCE_MIN_DAYS <= value <= PAGOSA_ABSENCE_MAX_DAYS:
        raise exceptions.HomeAssistantError(
            "Absence duration must be 0 (stop) or between "
            f"{PAGOSA_ABSENCE_MIN_DAYS} and {PAGOSA_ABSENCE_MAX_DAYS} days"
        )

    if not _is_absent(self):
        # No Absence under way: only remember the duration, the switch
        # (or the calendar) starts it.
        self._pagosa_planned_away_days = value or None
        self.async_set_updated_data(self.data)
        return

    if value == 0:
        await async_set_pagosa_away(self, False)
    else:
        await async_set_pagosa_away(self, True, value)


async def pagosa_program_absence(self: Hub, start: int, end: int) -> None:
    """Program an Absence starting later: only the setup is written.

    This is what the Atlantic app does when the start is not "now".
    """

    async def operation():
        await _put_atlantic_absence(self, start, end)

    await self.async_run_pagosa_operation(operation, None, "Pagosa Absence program")
    self.async_set_updated_data(self.data)


async def pagosa_refresh_absence(self: Hub, force: bool = False) -> None:
    """Re-read the Absence window of the Atlantic setup (throttled)."""
    now = time.monotonic()
    last = getattr(self, "_pagosa_absence_checked", None)
    if not force and last is not None and now - last < ABSENCE_REFRESH_INTERVAL:
        return
    self._pagosa_absence_checked = now

    try:
        if not await self._authenticate_atlantic():
            return
        async with self._session.get(
            COZYTOUCH_ATLANTIC_API + "/magellan/cozytouch/setupviewv2",
            headers={
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
            },
        ) as response:
            if response.status != 200:
                return
            data = await response.json(content_type=None)
        if isinstance(data, list) and data and isinstance(data[0], dict):
            self._setup["absence"] = copy.deepcopy(data[0].get("absence") or {})
    except Exception:  # noqa: BLE001 - never break the integration
        _LOGGER.debug("Unable to refresh the Pagosa absence window", exc_info=True)


def pagosa_absence_window(self: Hub) -> tuple[int, int] | None:
    """Return the (start, end) timestamps of the Absence, if one is set."""
    absence = self._setup.get("absence") or {}
    try:
        start, end = int(absence.get("startDate")), int(absence.get("endDate"))
    except (TypeError, ValueError):
        return None
    return (start, end) if start > 0 and end > start else None


async def pagosa_set_absence_end(self: Hub, end: int) -> None:
    """Move the end of the Absence period (the Atlantic cloud applies it).

    An end in the past (or within 2 minutes) stops the Absence now.
    """
    await pagosa_refresh_absence(self, force=True)
    window = pagosa_absence_window(self)
    if window is None:
        raise exceptions.HomeAssistantError("No Absence is set.")
    start, end, now = window[0], int(end), int(time.time())
    if end <= now + 120:
        await async_set_pagosa_away(self, False)
        return
    if end - start < PAGOSA_ABSENCE_MIN_DAYS * 86400 - 60:
        raise exceptions.HomeAssistantError(
            "An Absence lasts at least 48 hours (2 days) minimum."
        )
    if end - start > PAGOSA_ABSENCE_MAX_DAYS * 86400:
        raise exceptions.HomeAssistantError(
            f"An Absence lasts at most {PAGOSA_ABSENCE_MAX_DAYS} days."
        )

    async def operation():
        await _put_atlantic_absence(self, start, end)

    await self.async_run_pagosa_operation(operation, None, "Pagosa Absence end")
    self.async_set_updated_data(self.data)


Hub._put_atlantic_absence = _put_atlantic_absence
Hub.pagosa_set_absence_end = pagosa_set_absence_end
Hub.async_set_pagosa_away = async_set_pagosa_away
Hub.set_overkiz_away_duration = set_overkiz_away_duration
Hub.pagosa_refresh_absence = pagosa_refresh_absence
Hub.pagosa_program_absence = pagosa_program_absence
Hub.pagosa_absence_window = pagosa_absence_window


def _patch_number() -> None:
    """Let the absence duration number go beyond the old 6 day limit."""
    from .number import OverkizPagosaAwayDurationNumber

    def _read_value(self) -> float:
        planned = getattr(self.coordinator, "_pagosa_planned_away_days", None)
        if planned and not _is_absent(self.coordinator):
            return planned
        value = self.coordinator.get_overkiz_state("io:AwayModeDurationState", 0)
        try:
            return max(0, min(PAGOSA_ABSENCE_MAX_DAYS, float(value)))
        except (TypeError, ValueError):
            pass
        # "always": Absence applied by the Atlantic cloud from the setup
        # period; show the days left until its end.
        window = self.coordinator.pagosa_absence_window()
        if window is not None and _is_absent(self.coordinator):
            left = (window[1] - time.time()) / 86400
            return max(0, min(PAGOSA_ABSENCE_MAX_DAYS, math.ceil(left)))
        return 0

    async def async_set_native_value(self, value: float) -> None:
        new_value = int(max(0, min(PAGOSA_ABSENCE_MAX_DAYS, value)))
        await self.coordinator.set_overkiz_away_duration(new_value)

    OverkizPagosaAwayDurationNumber._attr_native_max_value = PAGOSA_ABSENCE_MAX_DAYS
    OverkizPagosaAwayDurationNumber._read_value = _read_value
    OverkizPagosaAwayDurationNumber.async_set_native_value = async_set_native_value


try:
    _patch_number()
except Exception:  # pragma: no cover - never break the integration
    _LOGGER.exception("Unable to patch the Pagosa absence number")
