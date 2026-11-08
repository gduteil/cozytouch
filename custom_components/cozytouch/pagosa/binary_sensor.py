"""Pagosa cloud connectivity.

Carried from 1.4's binary sensor, which every device had : same unique id,
same device, so the entity keeps its id and its history.
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN
from .hub import PagosaHub


class PagosaCloudConnectivity(CoordinatorEntity[PagosaHub], BinarySensorEntity):
    """Whether the Overkiz session answers."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_name = "Cozytouch"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: PagosaHub, title: str, uniq_id: str) -> None:
        """Initialize the Cloud connectivity binary sensor."""
        super().__init__(coordinator)
        self._title = title
        self._attr_unique_id = f"{DOMAIN}_{uniq_id}_cloud_connectivity"
        self._device_uniq_id = uniq_id

    @property
    def device_info(self) -> DeviceInfo:
        """The heater's device, which every other Pagosa entity is on.

        1.4 put this one alone on a device of its own, keyed on the entry ;
        its unique id is unchanged, so moving it keeps its entity id.
        """
        device = self.coordinator.get_overkiz_device() or {}
        return DeviceInfo(
            identifiers={(DOMAIN, str(device.get("deviceURL", self._device_uniq_id)))},
            manufacturer="Sauter",
            name=device.get("label") or self._title,
            model="Pagosa 270L",
        )

    @property
    def is_on(self) -> bool:
        """Connected when the last Overkiz read succeeded."""
        return self.coordinator.online

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()


async def async_setup_pagosa(
    hub: PagosaHub,
    config_entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the connectivity sensor ; config_entry is a PagosaContext."""
    async_add_entities(
        [PagosaCloudConnectivity(hub, config_entry.title, config_entry.entry_id)],
        True,
    )
