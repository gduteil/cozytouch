"""Pagosa programming slots.

Carried from the pagosa-1.4 branch unchanged but for the hub it talks to.
"""

from __future__ import annotations

from datetime import time as dt_time
import logging

from homeassistant.components.time import TimeEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN
from .hub import PagosaHub as Hub

_LOGGER = logging.getLogger(__name__)


class PagosaProgrammingTime(CoordinatorEntity[Hub], TimeEntity):
    """Time entity for a Pagosa programming slot."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:clock-outline"

    def __init__(
        self,
        coordinator: Hub,
        slot_key: str,
        boundary: str,
        config_title: str,
        config_uniq_id: str,
    ) -> None:
        """Initialize a programming time entity."""
        super().__init__(coordinator)

        self._hub = coordinator
        self._slot_key = slot_key
        self._boundary = boundary

        slot_number = slot_key[-1]
        boundary_name = "Début" if boundary == "start" else "Fin"

        self._attr_name = f"Programmation {slot_number} - {boundary_name}"
        self._attr_unique_id = (
            f"{config_uniq_id}_pagosa_{slot_key}_{boundary}"
        )

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
    def native_value(self) -> dt_time | None:
        """Return the configured time."""
        slots = self._hub.get_overkiz_state("io:ProgrammingSlotsState")

        if not isinstance(slots, dict):
            return None

        slot = slots.get(self._slot_key)

        if not isinstance(slot, dict):
            return None

        value = slot.get(self._boundary)

        if not isinstance(value, str):
            return None

        try:
            hour, minute = value.split(":", 1)
            return dt_time(int(hour), int(minute))
        except (ValueError, TypeError):
            _LOGGER.warning(
                "Invalid Pagosa programming time: %s",
                value,
            )
            return None

    async def async_set_value(self, value: dt_time) -> None:
        """Update one boundary of a programming slot."""
        slots = self._hub.get_overkiz_state("io:ProgrammingSlotsState")

        if not isinstance(slots, dict):
            raise RuntimeError("Pagosa programming slots are unavailable")

        updated_slots = {
            key: dict(slot) if isinstance(slot, dict) else slot
            for key, slot in slots.items()
        }

        if self._slot_key not in updated_slots:
            updated_slots[self._slot_key] = {
                "start": "00:00",
                "end": "00:00",
            }

        updated_slots[self._slot_key][self._boundary] = (
            f"{value.hour:02d}:{value.minute:02d}"
        )

        await self._hub.async_execute_overkiz_command(
            "setProgrammingSlots",
            [updated_slots],
            label=f"Pagosa programmation {self._slot_key}",
            refresh=False,
        )

        await self._hub._refresh_overkiz_setup()
        await self._hub.async_request_refresh()




async def async_setup_pagosa(
    hub: Hub,
    config_entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add this platform's Pagosa entities ; config_entry is a PagosaContext."""
    times = []
    device = hub.get_overkiz_device()

    if not device:
        _LOGGER.warning("Pagosa Overkiz device not found")
        return

    slots = hub.get_overkiz_state("io:ProgrammingSlotsState")

    if isinstance(slots, dict):
        for slot_key in ("slot1", "slot2"):
            slot = slots.get(slot_key)

            if not isinstance(slot, dict):
                continue

            for boundary in ("start", "end"):
                times.append(
                    PagosaProgrammingTime(
                        coordinator=hub,
                        slot_key=slot_key,
                        boundary=boundary,
                        config_title=config_entry.title,
                        config_uniq_id=config_entry.entry_id,
                    )
                )

    if times:
        async_add_entities(times, True)
