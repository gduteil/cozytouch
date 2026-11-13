"""Pagosa selects: operating mode and operating range.

Carried from the pagosa-1.4 branch unchanged but for the hub it talks to.
"""

from __future__ import annotations

import asyncio
import logging

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN
from .hub import PagosaHub as Hub

_LOGGER = logging.getLogger(__name__)


PAGOSA_SELECTS = {
    "dhw_mode": {
        "name": "Mode de fonctionnement",
        "state": "io:DHWModeState",
        "command": "setDHWMode",
        "options": {
            "Automatique": "autoMode",
            "Manuel": "manualEcoInactive",
        },
        "icon": "mdi:water-boiler",
    },
    "operating_range": {
        "name": "Plage de fonctionnement",
        "state": "io:OperatingRangeState",
        "command": "setOperatingRange",
        "options": {
            "PAC et électrique programmés": "pacProg_elecProg",
            "PAC et électrique 24h/24": "pac24h_elec24h",
        },
        "icon": "mdi:calendar-clock",
    },
}


class PagosaSelect(CoordinatorEntity, SelectEntity):
    """Select entity for Pagosa Overkiz settings."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: Hub,
        key: str,
        description: dict,
        config_title: str,
        config_uniq_id: str,
    ) -> None:
        """Initialize Pagosa select."""
        super().__init__(coordinator)

        self._hub = coordinator
        self._key = key
        self._description = description
        self._options_map = description["options"]

        self._attr_name = description["name"]
        self._attr_icon = description.get("icon")
        self._attr_options = list(self._options_map.keys())
        self._attr_unique_id = f"{config_uniq_id}_{key}"

        device = coordinator.get_overkiz_device() or {}

        self._attr_device_info = {
            "identifiers": {
                (
                    DOMAIN,
                    str(device.get("deviceURL", config_uniq_id)),
                )
            },
            "name": device.get("label") or "Sauter Pagosa 270L",
            "manufacturer": "Sauter",
            "model": "Pagosa 270L",
        }

    @property
    def available(self) -> bool:
        """Return whether the Pagosa is available."""
        return (
            self._hub.last_update_success
            and self._hub.get_overkiz_device() is not None
        )

    @property
    def current_option(self) -> str | None:
        """Return the current option."""
        value = self._hub.get_overkiz_state(
            self._description["state"]
        )

        for label, command_value in self._options_map.items():
            if str(value) == str(command_value):
                return label

        return None

    async def async_select_option(self, option: str) -> None:
        """Send the selected option to Pagosa."""
        if option not in self._options_map:
            return

        value = self._options_map[option]
        command = self._description["command"]

        await self._hub.async_execute_overkiz_command(
            command,
            [value],
            label=f"Pagosa: {self._description['name']}",
            refresh=False,
        )

        if self._key == "dhw_mode":
            # Allow Pagosa time to apply the new operating mode.
            await asyncio.sleep(2)

            await self._hub.async_execute_overkiz_command(
                "refreshDHWMode",
                [],
                label="Pagosa: actualisation du mode ECS",
                refresh=False,
            )

            await self._hub.async_execute_overkiz_command(
                "refreshTargetTemperature",
                [],
                label="Pagosa: actualisation température cible",
                refresh=False,
            )

            refreshed = await self._hub._refresh_overkiz_setup(
                force=True
            )

            if refreshed:
                self._hub.async_set_updated_data(
                    self._hub.data
                )
            else:
                _LOGGER.warning(
                    "Pagosa state refresh did not complete after mode change"
                )
                await self._hub.async_request_refresh()
        else:
            await self._hub.async_request_refresh()




async def async_setup_pagosa(
    hub: Hub,
    config_entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add this platform's Pagosa entities ; config_entry is a PagosaContext."""
    selects = []
    for key, description in PAGOSA_SELECTS.items():
        selects.append(
            PagosaSelect(
                coordinator=hub,
                key=key,
                description=description,
                config_title=config_entry.title,
                config_uniq_id=config_entry.entry_id,
            )
        )

    if selects:
        async_add_entities(selects, True)
