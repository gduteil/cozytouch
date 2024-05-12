"""The Atlantic Cozytouch integration."""
from __future__ import annotations

from datetime import timedelta

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv

from . import hub
from .const import CONF_DUMPJSON, DOMAIN

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.DATETIME,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
]

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.Schema({vol.Optional(CONF_DUMPJSON): cv.boolean})},
    extra=vol.ALLOW_EXTRA,
)

SCAN_INTERVAL = timedelta(seconds=10)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Atlantic Cozytouch from a config entry."""
    theHub = hub.Hub(
        hass, entry.data["username"], entry.data["password"], entry.data["deviceId"]
    )

    if "dump_json" in entry.data:
        theHub.set_dump_json(entry.data["dump_json"])

    await theHub.connect()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = theHub

    theHub.set_create_entities_for_unknown_entities(entry.data["create_unknown"])
    await theHub.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
