"""The Sauter Pagosa, which Atlantic serves through Overkiz.

A Pagosa subentry carries the heater's Overkiz device URL (``io://...``) as
its deviceId, where every other subentry carries a Cozytouch device id. That
is what sends it here : a PagosaHub of its own instead of a Hub, and entities
built by the modules of this package instead of the capability tables.

The entities are 1.4-pagosa's, unchanged, so a 1.4 entry migrated by
migrate_1_4.py finds every one of them under the unique id it rewrote, and
keeps its entity id and its history. They are built with a PagosaContext in
place of 1.4's config entry : its ``entry_id`` is the subentry id, which is
exactly what the migration put where 1.4 had the entry id.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import partial
import logging
from types import ModuleType
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

# Imported for what they do to the classes below, in 1.4-pagosa's order : the
# Absence, Boost, Eco and temperature rules the Atlantic app follows.
from . import (  # noqa: F401
    absence,
    binary_sensor,
    button,
    calendar,
    controls,
    datetime,
    number,
    select,
    select_fix,
    sensor,
    sensor_fix,
    switch,
    time,
)
from .hub import CannotConnect, PagosaHub, is_overkiz_device_id

__all__ = ["CannotConnect", "PagosaHub", "async_setup_platform", "is_overkiz_device_id"]

_LOGGER = logging.getLogger(__name__)

_PLATFORMS: dict[str, ModuleType] = {
    "binary_sensor": binary_sensor,
    "button": button,
    "calendar": calendar,
    "datetime": datetime,
    "number": number,
    "select": select,
    "sensor": sensor,
    "switch": switch,
    "time": time,
}


@dataclass(frozen=True)
class PagosaContext:
    """What 1.4's Pagosa entities read off their config entry, per subentry."""

    entry_id: str
    title: str
    data: Mapping[str, Any]


async def async_setup_platform(
    platform: str,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add one platform's entities for every Pagosa of the entry."""
    module = _PLATFORMS[platform]
    # getattr : a runtime built without Pagosas (the tests' stand-in) has none.
    pagosa_hubs = getattr(config_entry.runtime_data, "pagosa_hubs", {})
    for subentry_id, hub in pagosa_hubs.items():
        subentry = config_entry.subentries[subentry_id]
        context = PagosaContext(subentry_id, subentry.title, subentry.data)
        await module.async_setup_pagosa(
            hub,
            context,
            partial(async_add_entities, config_subentry_id=subentry_id),
        )
