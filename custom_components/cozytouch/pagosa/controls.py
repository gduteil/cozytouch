"""Pagosa controls: Boost, Eco, target temperature and state confirmation.

Behaviour validated against the Atlantic app (Overkiz execution history):

* Eco and the target temperature only work in manual mode; the Boost can
  also be started in auto mode. Absence overrides everything.
* Boost: ``setBoostModeDuration`` (1 to 7 days, 0 is rejected), then
  ``setCurrentOperatingMode`` with ``relaunch: on``. Stopping the Boost is
  only ``setCurrentOperatingMode`` with ``relaunch: off``.
* The Pagosa takes several minutes to report a change, so optimistic
  states are kept until the real state matches or a grace period ends,
  and one delayed refresh confirms the result.

Only the Pagosa methods of ``Hub`` are replaced.
"""

from __future__ import annotations

import asyncio
import logging
import time

from homeassistant import exceptions

from .hub import PagosaHub as Hub

_LOGGER = logging.getLogger(__name__)

MANUAL_MODES = ("manualEcoActive", "manualEcoInactive")
BOOST_MIN_DAYS = 1
BOOST_MAX_DAYS = 7
OPTIMISTIC_GRACE = 480  # seconds
CONFIRM_DELAYS = (180, 220)  # seconds, then seconds after the first one

MANUAL_MIN_TEMPERATURE = 50
MANUAL_ECO_MAX_TEMPERATURE = 55
MANUAL_MAX_TEMPERATURE = 62


def _is_manual(hub: Hub) -> bool:
    return hub.get_overkiz_state("io:DHWModeState") in MANUAL_MODES


def _is_absent(hub: Hub) -> bool:
    """The heater says absent and Atlantic still holds a period not yet over.

    The heater's own flag alone stayed "on" for hours after the period ended,
    and Eco was refused for it (docs/decisions.md, *Absence read as over*).
    """
    if hub._get_current_operating_mode().get("absence") != "on":
        return False
    absence = (getattr(hub, "_setup", None) or {}).get("absence") or {}
    try:
        end = int(absence.get("endDate"))
    except (TypeError, ValueError):
        return False
    return end > time.time()


def _require_manual(hub: Hub, what: str) -> None:
    if not _is_manual(hub):
        raise exceptions.HomeAssistantError(
            f"{what} is only available in manual mode. "
            "Switch the Pagosa to manual mode first."
        )


def _require_not_absent(hub: Hub) -> None:
    if _is_absent(hub):
        raise exceptions.HomeAssistantError(
            "Absence mode is active and overrides all other modes. "
            "Stop the Absence first."
        )


# ----------------------------------------------------------------------
# Optimistic states kept until confirmed
# ----------------------------------------------------------------------


def _expiry(self: Hub) -> dict:
    if not hasattr(self, "_pagosa_optimistic_expiry"):
        self._pagosa_optimistic_expiry = {}
    return self._pagosa_optimistic_expiry


def _drop_optimistic(self: Hub, name: str) -> None:
    self._pagosa_optimistic_states.pop(name, None)
    _expiry(self).pop(name, None)


def get_overkiz_state(self: Hub, state_name: str, default=None):
    """Return a Pagosa state, using an optimistic value until confirmed."""
    if state_name in self._pagosa_optimistic_states:
        optimistic = self._pagosa_optimistic_states[state_name]
        real = self._overkiz_states.get(state_name)
        expired = time.monotonic() >= _expiry(self).get(state_name, 0)
        confirmed = real is not None and str(real) == str(optimistic)
        if expired or confirmed:
            _drop_optimistic(self, state_name)
        else:
            return optimistic

    return self._overkiz_states.get(state_name, default)


async def _confirm_later(self: Hub) -> None:
    """Refresh the setup twice, late enough for the Pagosa to have reported."""
    try:
        for index, delay in enumerate(CONFIRM_DELAYS):
            await asyncio.sleep(delay)
            if not self._pagosa_optimistic_states:
                return
            if await self._refresh_overkiz_setup(force=True):
                self.async_set_updated_data(self.data)
            # Drop confirmed states (get_overkiz_state does it on read).
            for name in list(self._pagosa_optimistic_states):
                self.get_overkiz_state(name)
            if not self._pagosa_optimistic_states:
                self.async_set_updated_data(self.data)
                return
            _LOGGER.debug("Pagosa confirmation pass %d done", index + 1)
    except asyncio.CancelledError:
        raise
    except Exception:
        _LOGGER.exception("Pagosa delayed confirmation failed")


async def async_run_pagosa_operation(
    self: Hub,
    operation,
    optimistic_states: dict | None = None,
    label: str = "Pagosa operation",
) -> None:
    """Run a serialized Pagosa operation and keep its state until confirmed."""
    if self._pagosa_command_lock.locked():
        raise exceptions.HomeAssistantError(
            "A Pagosa command is already running. Try again in a few seconds."
        )

    async with self._pagosa_command_lock:
        if optimistic_states:
            until = time.monotonic() + OPTIMISTIC_GRACE
            for name, value in optimistic_states.items():
                self._pagosa_optimistic_states[name] = value
                _expiry(self)[name] = until
            self.async_set_updated_data(self.data)

        try:
            await operation()
        except Exception:
            for name in optimistic_states or {}:
                _drop_optimistic(self, name)
            self.async_set_updated_data(self.data)
            raise

    previous = getattr(self, "_pagosa_confirm_task", None)
    if previous is not None and not previous.done():
        previous.cancel()
    self._pagosa_confirm_task = self.hass.async_create_task(
        _confirm_later(self)
    )
    _LOGGER.debug("%s sent, waiting for confirmation", label)


# ----------------------------------------------------------------------
# Boost
# ----------------------------------------------------------------------


def _stored_boost_days(self: Hub) -> int:
    try:
        days = int(self.get_overkiz_state("core:BoostModeDurationState", 0))
    except (TypeError, ValueError):
        days = 0
    return days if BOOST_MIN_DAYS <= days <= BOOST_MAX_DAYS else BOOST_MIN_DAYS


async def async_set_pagosa_boost(
    self: Hub, enabled: bool, days: int | None = None
) -> None:
    """Start the Boost for N days (like the app) or stop it."""
    current = self._get_current_operating_mode()

    if enabled:
        _require_not_absent(self)
        days = _stored_boost_days(self) if days is None else int(days)
        if not BOOST_MIN_DAYS <= days <= BOOST_MAX_DAYS:
            raise exceptions.HomeAssistantError(
                f"Boost duration must be between {BOOST_MIN_DAYS} "
                f"and {BOOST_MAX_DAYS} days"
            )
        current["relaunch"] = "on"

        async def operation():
            await self.async_execute_overkiz_command(
                "setBoostModeDuration",
                [days],
                label="Set Pagosa Boost duration",
                refresh=False,
            )
            await self.async_execute_overkiz_command(
                "refreshBoostModeDuration", refresh=False
            )
            await self._set_operating_mode_flag("relaunch", "on")

        optimistic = {
            "core:OperatingModeState": current,
            "core:BoostModeDurationState": days,
        }
    else:
        current["relaunch"] = "off"

        async def operation():
            await self._set_operating_mode_flag("relaunch", "off")
            await self.async_execute_overkiz_command(
                "refreshBoostModeDuration", refresh=False
            )

        optimistic = {"core:OperatingModeState": current}

    await self.async_run_pagosa_operation(operation, optimistic, "Pagosa Boost")


async def set_overkiz_boost_duration(self: Hub, value: int) -> None:
    """Store the Boost duration (1 to 7 days); 0 means no change."""
    value = int(value)

    if not 0 <= value <= BOOST_MAX_DAYS:
        raise exceptions.HomeAssistantError(
            f"Boost duration must be between {BOOST_MIN_DAYS} "
            f"and {BOOST_MAX_DAYS} days"
        )

    if value == 0:
        return

    async def operation():
        await self.async_execute_overkiz_command(
            "setBoostModeDuration",
            [value],
            label="Set Pagosa Boost duration",
            refresh=False,
        )
        await self.async_execute_overkiz_command(
            "refreshBoostModeDuration", refresh=False
        )

    await self.async_run_pagosa_operation(
        operation,
        {"core:BoostModeDurationState": value},
        "Pagosa Boost duration",
    )


# ----------------------------------------------------------------------
# Eco and target temperature
# ----------------------------------------------------------------------


async def async_set_pagosa_eco(self: Hub, enabled: bool) -> None:
    """Set manual Eco (heat pump only) on or off."""
    _require_not_absent(self)
    _require_manual(self, "Eco")

    mode = "manualEcoActive" if enabled else "manualEcoInactive"

    async def operation():
        await self.async_execute_overkiz_command(
            "setDHWMode", [mode], label="Pagosa Eco", refresh=False
        )
        await self.async_execute_overkiz_command(
            "refreshDHWMode", refresh=False
        )
        await self.async_execute_overkiz_command(
            "refreshTargetTemperature", refresh=False
        )

    await self.async_run_pagosa_operation(
        operation, {"io:DHWModeState": mode}, "Pagosa Eco"
    )


def pagosa_temperature_limits(self: Hub) -> tuple[int, int]:
    """Return the target temperature range allowed in the current mode."""
    mode = self.get_overkiz_state("io:DHWModeState")
    maximum = (
        MANUAL_ECO_MAX_TEMPERATURE
        if mode == "manualEcoActive"
        else MANUAL_MAX_TEMPERATURE
    )
    return MANUAL_MIN_TEMPERATURE, maximum


async def set_overkiz_target_temperature(self: Hub, value: float) -> None:
    """Set the target temperature (whole degrees, manual mode only)."""
    _require_not_absent(self)
    _require_manual(self, "The target temperature")

    target = int(round(float(value)))
    low, high = pagosa_temperature_limits(self)
    if not low <= target <= high:
        raise exceptions.HomeAssistantError(
            f"Target temperature must be between {low} and {high} "
            "in the current mode"
        )

    async def operation():
        await self.async_execute_overkiz_command(
            "setTargetTemperature",
            [target],
            label="Set Pagosa target temperature",
            refresh=False,
        )
        await self.async_execute_overkiz_command(
            "refreshTargetTemperature", refresh=False
        )

    await self.async_run_pagosa_operation(
        operation,
        {"core:TargetTemperatureState": target},
        "Pagosa target temperature",
    )


Hub.get_overkiz_state = get_overkiz_state
Hub.async_run_pagosa_operation = async_run_pagosa_operation
Hub.async_set_pagosa_boost = async_set_pagosa_boost
Hub.set_overkiz_boost_duration = set_overkiz_boost_duration
Hub.async_set_pagosa_eco = async_set_pagosa_eco
Hub.pagosa_temperature_limits = pagosa_temperature_limits
Hub.set_overkiz_target_temperature = set_overkiz_target_temperature
