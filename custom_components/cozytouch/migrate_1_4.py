"""Turn 1.4's entries, one per device, into one account entry.

Every entity and device keeps its entity id and its history : only the
config entry it hangs off and the id prefix of its unique id change. See
docs/decisions.md.
"""

from __future__ import annotations

import asyncio
from types import MappingProxyType

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .config_flow import SUBENTRY_TYPE
from .const import DOMAIN

_LOCK = f"{DOMAIN}_migrate_1_4"
_ABSORBED = f"{DOMAIN}_migrate_1_4_absorbed"


def account_unique_id(username: str) -> str:
    """What the config flow calls an account entry."""
    return "cozytouch_" + username.lower()


def rewrite(value: str, old_id: str, new_id: str) -> str:
    """1.4 keyed unique ids and device identifiers on the entry id."""
    return value.replace(old_id, new_id)


async def async_migrate_from_1_4(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool | None:
    """Fold every 1.4 entry of the same account into this one.

    True when this entry is now the account's, None when an earlier entry
    already took it in and it is about to be removed, False when the
    account already has a version 2 entry to fold it into.
    """
    async with hass.data.setdefault(_LOCK, asyncio.Lock()):
        absorbed: set[str] = hass.data.setdefault(_ABSORBED, set())
        if entry.entry_id in absorbed:
            return None

        username = entry.data["username"]
        if any(
            other.version == 2 and other.unique_id == account_unique_id(username)
            for other in hass.config_entries.async_entries(DOMAIN)
        ):
            return False

        # Read before the first write : this entry's own data is replaced below.
        group = [
            (other.entry_id, other.data["deviceId"], other.data["name"])
            for other in hass.config_entries.async_entries(DOMAIN)
            if other.version == 1
            and other.data.get("username", "").lower() == username.lower()
        ]

        hass.config_entries.async_update_entry(
            entry,
            version=2,
            minor_version=1,
            unique_id=account_unique_id(username),
            title=username,
            data={"username": username, "password": entry.data["password"]},
            options={
                "create_unknown": entry.data.get("create_unknown", False),
                "dump_json": entry.data.get("dump_json", False),
            },
        )

        entities = er.async_get(hass)
        devices = dr.async_get(hass)
        for old_id, deviceId, name in group:
            subentry = ConfigSubentry(
                data=MappingProxyType(
                    {"deviceId": deviceId, "name": name}
                ),
                subentry_type=SUBENTRY_TYPE,
                title=name,
                unique_id=f"cozytouch_{deviceId}",
            )
            hass.config_entries.async_add_subentry(entry, subentry)
            sub_id = subentry.subentry_id

            for entity in er.async_entries_for_config_entry(entities, old_id):
                entities.async_update_entity(
                    entity.entity_id,
                    config_entry_id=entry.entry_id,
                    config_subentry_id=sub_id,
                    new_unique_id=rewrite(entity.unique_id, old_id, sub_id),
                )

            for device in dr.async_entries_for_config_entry(devices, old_id):
                devices.async_update_device(
                    device.id,
                    add_config_entry_id=entry.entry_id,
                    add_config_subentry_id=sub_id,
                    new_identifiers={
                        (domain, rewrite(value, old_id, sub_id))
                        for domain, value in device.identifiers
                    },
                )
                devices.async_update_device(
                    device.id,
                    remove_config_entry_id=old_id,
                    remove_config_subentry_id=None,
                )

            if old_id != entry.entry_id:
                absorbed.add(old_id)
                # Not awaited : its own setup may be waiting on this lock.
                hass.async_create_task(hass.config_entries.async_remove(old_id))

    _drop_unclaimed_once_started(hass, entry.entry_id)
    return True


def _drop_unclaimed_once_started(hass: HomeAssistant, entry_id: str) -> None:
    """Remove the 1.4 entities this version builds no more.

    Once Home Assistant has started, so every platform has added what it
    builds : an entity nothing claimed by then shows as restored. A disabled
    one has no state either way and is left alone. See docs/decisions.md.
    """

    async def drop(_: Event) -> None:
        registry = er.async_get(hass)
        for entity in er.async_entries_for_config_entry(registry, entry_id):
            if entity.disabled_by is not None:
                continue
            state = hass.states.get(entity.entity_id)
            if state is None or state.attributes.get("restored"):
                registry.async_remove(entity.entity_id)

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, drop)
