"""Binary sensors for Atlantic Cozytouch integration."""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .hub import CozytouchConfigEntry, CozytouchDeviceEntity, Hub, device_info_for

_LOGGER = logging.getLogger(__name__)


# config flow setup
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: CozytouchConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up entry."""
    # Per device rather than per account : it is the device page it shows up
    # on. See docs/decisions.md.
    for subentry_id, subentry in config_entry.subentries.items():
        hub = config_entry.runtime_data.hubs[subentry_id]
        async_add_entities(
            [
                CloudConnectivity(hub, subentry.title, subentry_id),
                DeviceAvailability(hub, subentry_id),
            ],
            True,
            config_subentry_id=subentry_id,
        )


class CloudConnectivity(CozytouchDeviceEntity, BinarySensorEntity):
    """Cloud connectivity to the Atlantic Cozytouch integration."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_name = "Cozytouch"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: Hub, title: str, uniq_id: str) -> None:
        """Initialize the Cloud connectivity binary sensor."""
        super().__init__(coordinator)
        self._title = title
        self._attr_unique_id = f"{DOMAIN}_{uniq_id}_cloud_connectivity"
        self._device_uniq_id = uniq_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info, under the entry title rather than the model."""
        info = device_info_for(self.coordinator, self._device_uniq_id)
        info["name"] = self._title
        return info

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_is_on = self.coordinator.online
        self.async_write_ha_state()


class DeviceAvailability(CozytouchDeviceEntity, BinarySensorEntity):
    """Whether the cloud reports this device as reachable (`isAvailable`).

    The cloud's per-device flag, where CloudConnectivity is the account's
    session. Stays available itself when the session drops, and unknown when
    the field is absent. See docs/decisions.md.
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_name = "Available"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: Hub, uniq_id: str) -> None:
        """Initialize the device availability binary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{uniq_id}_device_availability"
        self._device_uniq_id = uniq_id

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_is_on = self.coordinator.get_is_available()
        self.async_write_ha_state()
