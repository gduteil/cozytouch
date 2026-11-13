"""Pagosa operating mode select: both manual sub-modes read as "Manuel".

The select only knew ``manualEcoInactive`` for "Manuel", so the entity
became unknown when the manual Eco was active (``manualEcoActive``).
The command now goes through the shared locked operation too.
"""

from __future__ import annotations

import logging

from .hub import PagosaHub as Hub

_LOGGER = logging.getLogger(__name__)

MANUAL_MODES = ("manualEcoActive", "manualEcoInactive")


def _patch_select() -> None:
    from .select import PagosaSelect

    original_option = PagosaSelect.current_option
    original_select = PagosaSelect.async_select_option

    def current_option(self) -> str | None:
        if self._key != "dhw_mode":
            return original_option.fget(self)
        value = self._hub.get_overkiz_state("io:DHWModeState")
        if value == "autoMode":
            return "Automatique"
        if value in MANUAL_MODES:
            return "Manuel"
        return None

    async def async_select_option(self, option: str) -> None:
        if self._key != "dhw_mode":
            await original_select(self, option)
            return

        hub: Hub = self._hub
        current = hub.get_overkiz_state("io:DHWModeState")

        if option == "Automatique":
            mode = "autoMode"
        elif option == "Manuel":
            if current in MANUAL_MODES:
                return  # keep the current Eco choice
            mode = "manualEcoInactive"
        else:
            return

        if current == mode:
            return

        async def operation():
            await hub.async_execute_overkiz_command(
                "setDHWMode", [mode], label="Pagosa mode", refresh=False
            )
            await hub.async_execute_overkiz_command(
                "refreshDHWMode", refresh=False
            )
            await hub.async_execute_overkiz_command(
                "refreshTargetTemperature", refresh=False
            )

        await hub.async_run_pagosa_operation(
            operation, {"io:DHWModeState": mode}, "Pagosa mode"
        )

    PagosaSelect.current_option = property(current_option)
    PagosaSelect.async_select_option = async_select_option


try:
    _patch_select()
except Exception:  # pragma: no cover - never break the integration
    _LOGGER.exception("Unable to patch the Pagosa mode select")
