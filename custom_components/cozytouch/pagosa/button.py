"""Pagosa refresh and identify buttons.

Carried from the pagosa-1.4 branch unchanged but for the hub it talks to.
"""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN
from .hub import PagosaHub as Hub

_LOGGER = logging.getLogger(__name__)


_LOGGER = logging.getLogger(__name__)


PAGOSA_BUTTONS = [
    {
        "key": "refresh_temperature",
        "name": "Actualiser les températures",
        "command": "refreshTargetTemperature",
        "icon": "mdi:thermometer-refresh",
    },
    {
        "key": "refresh_mode",
        "name": "Actualiser le mode ECS",
        "command": "refreshDHWMode",
        "icon": "mdi:refresh",
    },
    {
        "key": "refresh_programming",
        "name": "Actualiser la programmation",
        "command": "refreshProgrammingSlots",
        "icon": "mdi:calendar-refresh",
    },
    {
        "key": "refresh_error",
        "name": "Actualiser les erreurs",
        "command": "refreshDHWError",
        "icon": "mdi:alert-refresh",
    },
    {
        "key": "refresh_consumption",
        "name": "Actualiser la consommation d'eau",
        "command": "refreshWaterConsumption",
        "icon": "mdi:water-sync",
    },
    {
        "key": "refresh_boost",
        "name": "Actualiser la durée Boost",
        "command": "refreshBoostModeDuration",
        "icon": "mdi:rocket-launch",
    },
    {
        "key": "refresh_away",
        "name": "Actualiser la durée Absence",
        "command": "refreshAwayModeDuration",
        "icon": "mdi:calendar-refresh",
    },
    {
        "key": "identify",
        "name": "Identifier le chauffe-eau",
        "command": "identify",
        "icon": "mdi:target",
    },
]


class PagosaButton(CoordinatorEntity, ButtonEntity):
    """Button for a Sauter Pagosa Overkiz device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: Hub,
        config_entry: ConfigEntry,
        description: dict,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)

        self._hub = coordinator
        self._description = description

        self._attr_name = description["name"]
        self._attr_icon = description.get("icon")
        self._attr_unique_id = (
            f"{DOMAIN}_{config_entry.entry_id}_pagosa_"
            f"{description['key']}"
        )

        device = coordinator.get_overkiz_device() or {}
        device_url = device.get("deviceURL", config_entry.entry_id)

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(device_url))},
            name=device.get("label") or "Sauter Pagosa 270L",
            manufacturer="Sauter",
            model="Pagosa 270L",
        )

    @property
    def available(self) -> bool:
        """Return whether the Pagosa is available."""
        return (
            self._hub.is_overkiz()
            and self._hub.last_update_success
            and self._hub.get_overkiz_device() is not None
        )

    async def async_press(self) -> None:
        """Execute the selected Pagosa command."""
        command = self._description["command"]

        _LOGGER.info("Pagosa button pressed: %s", command)

        await self._hub.async_execute_overkiz_command(
            command,
            [],
            label=f"Pagosa: {self._description['name']}",
        )

        await self._hub.async_request_refresh()


async def async_setup_pagosa(
    hub: Hub,
    config_entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add this platform's Pagosa entities ; config_entry is a PagosaContext."""
    async_add_entities(
        [
            PagosaButton(
                coordinator=hub,
                config_entry=config_entry,
                description=description,
            )
            for description in PAGOSA_BUTTONS
        ]
    )
