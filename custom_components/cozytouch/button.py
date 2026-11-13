"""Button entities : only the Sauter Pagosa has any, see pagosa/."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import pagosa
from .hub import CozytouchConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: CozytouchConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Pagosas' button entities."""
    await pagosa.async_setup_platform("button", config_entry, async_add_entities)
