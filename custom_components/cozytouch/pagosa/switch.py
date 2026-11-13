"""Pagosa switches: Eco, Boost and Absence.

Carried from the pagosa-1.4 branch unchanged but for the hub it talks to.
"""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN
from .hub import PagosaHub as Hub

_LOGGER = logging.getLogger(__name__)


class PagosaBaseSwitch(CoordinatorEntity[Hub], SwitchEntity):
    """Base class for Pagosa switches."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: Hub,
        name: str,
        icon: str,
        config_title: str,
        config_device_id: str,
        config_uniq_id: str,
        unique_suffix: str,
    ) -> None:
        """Initialize a Pagosa switch."""
        super().__init__(coordinator)

        self._hub = coordinator
        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = (
            f"{config_uniq_id}_pagosa_{unique_suffix}"
        )

        device = coordinator.get_overkiz_device() or {}

        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_device_id)},
            "name": device.get("label") or config_title or "Sauter Pagosa 270L",
            "manufacturer": "Sauter",
            "model": "Pagosa 270L",
        }

    @property
    def available(self) -> bool:
        """Return entity availability."""
        return self._hub.online and self._hub.last_update_success


class PagosaEcoSwitch(PagosaBaseSwitch):
    """Switch for Pagosa Eco mode."""

    def __init__(
        self,
        coordinator: Hub,
        config_title: str,
        config_device_id: str,
        config_uniq_id: str,
    ) -> None:
        """Initialize Eco switch."""
        super().__init__(
            coordinator=coordinator,
            name="Mode Eco",
            icon="mdi:leaf",
            config_title=config_title,
            config_device_id=config_device_id,
            config_uniq_id=config_uniq_id,
            unique_suffix="eco",
        )

    @property
    def is_on(self) -> bool:
        """Return whether Eco mode is active."""
        return (
            self._hub.get_overkiz_state("io:DHWModeState")
            == "manualEcoActive"
        )

    async def async_turn_on(self) -> None:
        """Activate Eco mode."""
        await self._hub.async_set_pagosa_eco(True)

    async def async_turn_off(self) -> None:
        """Deactivate Eco mode."""
        await self._hub.async_set_pagosa_eco(False)


class PagosaBoostSwitch(PagosaBaseSwitch):
    """Switch for Pagosa Boost mode."""

    def __init__(
        self,
        coordinator: Hub,
        config_title: str,
        config_device_id: str,
        config_uniq_id: str,
    ) -> None:
        """Initialize Boost switch."""
        super().__init__(
            coordinator=coordinator,
            name="Boost ECS",
            icon="mdi:rocket-launch",
            config_title=config_title,
            config_device_id=config_device_id,
            config_uniq_id=config_uniq_id,
            unique_suffix="boost",
        )

    @property
    def is_on(self) -> bool:
        """Return whether Boost is active."""
        operating_mode = self._hub.get_overkiz_state(
            "core:OperatingModeState",
            {},
        )

        if not isinstance(operating_mode, dict):
            return False

        return (
            str(operating_mode.get("relaunch", "off")).lower() == "on"
        )

    async def async_turn_on(self) -> None:
        """Activate Boost without changing its duration."""
        await self._hub.async_set_pagosa_boost(True)

    async def async_turn_off(self) -> None:
        """Deactivate Boost without changing Absence."""
        await self._hub.async_set_pagosa_boost(False)


class PagosaOperatingModeSwitch(PagosaBaseSwitch):
    """Switch for Pagosa Absence mode."""

    def __init__(
        self,
        coordinator: Hub,
        mode_key: str,
        name: str,
        icon: str,
        config_title: str,
        config_device_id: str,
        config_uniq_id: str,
    ) -> None:
        """Initialize Absence switch."""
        super().__init__(
            coordinator=coordinator,
            name=name,
            icon=icon,
            config_title=config_title,
            config_device_id=config_device_id,
            config_uniq_id=config_uniq_id,
            unique_suffix=mode_key,
        )

        self._mode_key = mode_key

    @property
    def is_on(self) -> bool:
        """Return whether Absence mode is active."""
        operating_mode = self._hub._get_current_operating_mode()

        if not isinstance(operating_mode, dict):
            return False

        return (
            str(operating_mode.get(self._mode_key, "off")).lower()
            == "on"
        )

    async def async_turn_on(self) -> None:
        """Activate Absence."""
        await self._hub.async_set_pagosa_away(True)

    async def async_turn_off(self) -> None:
        """Deactivate Absence."""
        await self._hub.async_set_pagosa_away(False)




async def async_setup_pagosa(
    hub: Hub,
    config_entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add this platform's Pagosa entities ; config_entry is a PagosaContext."""
    switches = []
    device = hub.get_overkiz_device()
    if not device:
        _LOGGER.warning("Pagosa Overkiz device not found")
        return

    device_id = str(
        config_entry.data.get("deviceId", config_entry.entry_id)
    )

    common = {
        "coordinator": hub,
        "config_title": config_entry.title,
        "config_device_id": device_id,
        "config_uniq_id": config_entry.entry_id,
    }

    switches.extend(
        [
            PagosaEcoSwitch(**common),
            PagosaBoostSwitch(**common),
            PagosaOperatingModeSwitch(
                **common,
                mode_key="absence",
                name="Mode absence",
                icon="mdi:home-export-outline",
            ),
        ]
    )

    if switches:
        async_add_entities(switches, True)
