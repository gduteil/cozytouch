"""The Atlantic Cozytouch integration."""
from __future__ import annotations

from pathlib import Path

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, entity_registry as er
import homeassistant.helpers.config_validation as cv

from .account import CozytouchAccount
from .const import DOMAIN, PROGRAM_BLOCKS, program_block
from .hub import (
    AccountCoordinator,
    CozytouchConfigEntry,
    CozytouchRuntimeData,
    Hub,
    device_info_for,
)
from .services import async_register_services

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CALENDAR,
    Platform.CLIMATE,
    Platform.DATETIME,
    Platform.FAN,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

CARD_URL = f"/{DOMAIN}/cozytouch-schedule-card.js"
CARD_SERVED = f"{DOMAIN}_card_served"


CARD_PATH = Path(__file__).parent / "www" / "cozytouch-schedule-card.js"


class CozytouchCardView(HomeAssistantView):
    """Serve the schedule card, revalidated on every load.

    A static path cannot set a header, and without one a browser caches the
    file on its own guess and keeps an old card. See docs/decisions.md.
    """

    url = CARD_URL
    name = f"{DOMAIN}:schedule-card"
    requires_auth = False

    async def get(self, request: web.Request) -> web.FileResponse:
        """Answer with the card, telling the browser to check every time."""
        return web.FileResponse(CARD_PATH, headers={"Cache-Control": "no-cache"})


async def _async_serve_card(hass: HomeAssistant) -> None:
    """Serve the schedule card, once for all config entries.

    Served but not loaded : somebody who wants it adds CARD_URL as a
    dashboard resource. See docs/decisions.md.
    """
    if hass.data.get(CARD_SERVED):
        return

    hass.data[CARD_SERVED] = True
    hass.http.register_view(CozytouchCardView)


def _setting(entry: ConfigEntry, key: str) -> bool:
    """Read a setting, options first since that is where the options flow writes."""
    return entry.options.get(key, entry.data.get(key, False))


def _register_devices(
    device_registry: dr.DeviceRegistry,
    entry: CozytouchConfigEntry,
    hubs: dict[str, Hub],
) -> None:
    """Create every subentry's device before any platform needs it.

    Gateways first: the children's via_device points at them, and the registry
    only honours a link to a device it already holds.
    """
    for subentry_id, hub in sorted(
        hubs.items(), key=lambda item: item[1].get_via_device() is not None
    ):
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            config_subentry_id=subentry_id,
            **device_info_for(hub, subentry_id),
        )


def _covered_prog_unique_ids(
    subentry_ids, existing_unique_ids: set[str]
) -> set[str]:
    """The per-day program sensors whose whole block is in the registry.

    What is in the registry mirrors what the device reported, so the calendar's
    whole-block condition can be checked without the API. See
    docs/decisions.md.
    """
    covered: set[str] = set()
    firsts = [first for firsts in PROGRAM_BLOCKS.values() for first in firsts]
    for subentry_id in subentry_ids:
        for first in firsts:
            block = {
                f"{DOMAIN}_{subentry_id}_{capabilityId}"
                for capabilityId in program_block(first)
            }
            if block <= existing_unique_ids:
                covered |= block

    return covered


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Bring a stored entry up to the current minor version.

    A version 1 entry keeps landing in MIGRATION_ERROR, as it always has. 2.2
    disables the per-day program sensors a calendar makes redundant, once and
    not per start. 2.3 drops the number entity capability 312 used to build.
    2.4 drops the air-circulation switch and disables its speed select, both
    of which the fan now is. See docs/decisions.md.
    """
    if entry.version != 2:
        return False

    if entry.minor_version < 2:
        registry = er.async_get(hass)
        by_unique_id = {
            entity.unique_id: entity
            for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
        }
        for unique_id in _covered_prog_unique_ids(
            entry.subentries, set(by_unique_id)
        ):
            entity = by_unique_id[unique_id]
            if entity.disabled_by is None:
                registry.async_update_entity(
                    entity.entity_id,
                    disabled_by=er.RegistryEntryDisabler.INTEGRATION,
                )

        hass.config_entries.async_update_entry(entry, minor_version=2)

    if entry.minor_version < 3:
        # 312 is read-only and became a sensor. The registry is keyed on the
        # platform as well as the unique id, so the number it used to build is
        # not reused -- it stays behind, unavailable, forever.
        registry = er.async_get(hass)
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
            if entity.domain == "number" and entity.unique_id.endswith("_312"):
                registry.async_remove(entity.entity_id)

        hass.config_entries.async_update_entry(entry, minor_version=3)

    if entry.minor_version < 4:
        # The fan is the switch and the speed both. The switch is gone from
        # the platform, so its registry entry would sit unavailable forever.
        # See docs/decisions.md.
        registry = er.async_get(hass)
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
            if entity.domain == "switch" and entity.unique_id.endswith(
                "_switch_102024"
            ):
                registry.async_remove(entity.entity_id)

        hass.config_entries.async_update_entry(entry, minor_version=4)

    if entry.minor_version < 5:
        # The speed select is disabled rather than removed, once, so somebody
        # who turns it back on keeps it. 2.4 meant to do this and matched a
        # unique id no select carries.
        registry = er.async_get(hass)
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
            if (
                entity.domain == "select"
                and entity.unique_id.endswith("_102004")
                and entity.disabled_by is None
            ):
                registry.async_update_entity(
                    entity.entity_id,
                    disabled_by=er.RegistryEntryDisabler.INTEGRATION,
                )

        hass.config_entries.async_update_entry(entry, minor_version=5)

    return True


async def _async_entry_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload so new options -- or a device added or removed -- are picked up.

    HA fires these listeners for a subentry change too, which is what builds
    the hub for a device somebody just added.
    """
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: CozytouchConfigEntry) -> bool:
    """Set up Atlantic Cozytouch from a config entry."""
    account = CozytouchAccount(hass, entry.data["username"], entry.data["password"])
    account.set_dump_json(_setting(entry, "dump_json"))

    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))
    async_register_services(hass)
    await _async_serve_card(hass)

    # Retried with backoff until the network is back ; a refused password
    # comes out as ConfigEntryAuthFailed instead. See docs/decisions.md.
    if not await account.connect_or_auth_failed():
        raise ConfigEntryNotReady("Cannot connect to Atlantic Cozytouch API")

    create_unknown = _setting(entry, "create_unknown")
    hubs: dict[str, Hub] = {}
    for subentry_id, subentry in entry.subentries.items():
        hub = Hub(
            hass,
            account,
            subentry.data["deviceId"],
            config_entry=entry,
            subentry_id=subentry_id,
        )
        hub.set_create_entities_for_unknown_entities(create_unknown)
        hubs[subentry_id] = hub

    coordinator = AccountCoordinator(hass, account, entry, hubs)
    entry.runtime_data = CozytouchRuntimeData(account, hubs, coordinator)

    # async_refresh, not async_config_entry_first_refresh : connect() has
    # already read the capabilities, so a failing poll must not fail a setup
    # that has what it needs. See docs/decisions.md.
    await coordinator.async_refresh()

    # Before the platforms, not as a side effect of their first entity. See
    # docs/decisions.md.
    _register_devices(dr.async_get(hass), entry, hubs)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Only for a setup that got this far : a failed one is not worth a word.

    return True


async def async_unload_entry(hass: HomeAssistant, entry: CozytouchConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
