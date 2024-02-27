"""Binary sensors for Atlantic Cozytouch integration."""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .hub import Hub

_LOGGER = logging.getLogger(__name__)


# config flow setup
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entry."""
    # Retrieve the hub object
    try:
        hub = hass.data[DOMAIN][config_entry.entry_id]
    except KeyError:
        _LOGGER.error(
            "%s: can not init binaries sensors: failed to get the hub object",
            config_entry.title,
        )
        return

    async_add_entities(
        [
            CloudConnectivity(
                config_entry.data["deviceId"],
                config_entry.title,
                config_entry.entry_id,
                hub,
            )
        ],
        True,
    )


class CloudConnectivity(BinarySensorEntity):
    """Cloud connectivity to the Atlantic Cozytouch integration."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_name = "Cozytouch"
    _attr_should_poll = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self, deviceId: int, title: str, uniq_id: str | None, hub: Hub
    ) -> None:
        """Initialize the Cloud connectivity binary sensor."""
        self._deviceId = deviceId
        self._title = title
        self._attr_unique_id = f"{DOMAIN}_{uniq_id}_cloud_connectivity"
        self._hub = hub
        self._device_uniq_id = uniq_id if uniq_id is not None else "yaml_legacy"

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        modelInfos = self._hub.get_model_infos(self._deviceId)
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_uniq_id)},
            manufacturer="Atlantic",
            name=self._title,
            model=modelInfos["name"],
            serial_number=self._hub.get_serial_number(self._deviceId),
        )

    @property
    def is_on(self) -> bool:
        """Value of the sensor."""
        return self._hub.online

    async def async_update(self):
        """Request updates or reconnect if needed."""
        await self._hub.update(self._deviceId)
