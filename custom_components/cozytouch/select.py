"""Switches for Atlantic Cozytouch integration."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SERVICE_VALUES, narrowed_modes
from .hub import (
    CozytouchConfigEntry,
    CozytouchDeviceEntity,
    Hub,
    add_capability_entities,
)
from .infos import CapabilityType
from .sensor import CozytouchSensor

_LOGGER = logging.getLogger(__name__)


def format_duration(minutes: int) -> str:
    """One option label, the way the app's picker shows it (00:15 … 05:00)."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def parse_duration(option: str) -> int:
    """The minutes an option label stands for."""
    hours, minutes = option.split(":")
    return int(hours) * 60 + int(minutes)


# The order the app lists the system's services in.
SYSTEM_SERVICE_ORDER = ("off", "heat", "cool", "auto", "dry", "fan")

SUPPORTED_MODES_CAPABILITY_ID = 100022


def duration_options(lowest: int, highest: int, step: int) -> list[str]:
    """Every whole step between the bounds, as option labels."""
    if step <= 0:
        return []
    return [format_duration(minutes) for minutes in range(lowest, highest + 1, step)]


# config flow setup
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: CozytouchConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entry."""
    add_capability_entities(
        config_entry,
        async_add_entities,
        {
            CapabilityType.SELECT: CozytouchSelect,
            CapabilityType.DURATION_SELECT: CozytouchDurationSelect,
            CapabilityType.SYSTEM_SERVICE: CozytouchSystemServiceSelect,
        },
    )


class CozytouchSelect(SelectEntity, CozytouchSensor):
    """Class for select entity."""

    def __init__(
        self,
        coordinator: Hub,
        capability,
        config_title: str,
        config_uniq_id: str,
        name: str | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialize a Select entity."""
        super().__init__(
            coordinator=coordinator,
            capability=capability,
            config_title=config_title,
            config_uniq_id=config_uniq_id,
            name=name,
            icon=icon,
        )
        modelInfos = self.coordinator.get_model_infos()
        if "modelList" in capability and capability.modelList in modelInfos:
            self._list = modelInfos.get(capability.modelList, None)
        else:
            self._list = {-1: "Undefined"}

        self.options = list(self._list.values())
        self.current_option = self.options[0]

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        for value in self._list:
            if self._list[value] == option:
                await self.coordinator.set_capability_value(
                    self._capability.capabilityId,
                    str(value),
                )
                await self.coordinator.async_request_refresh()
                break

    def get_value(self) -> str:
        """Retrieve value from hub."""
        try:
            value = int(
                self.coordinator.get_capability_value(self._capability.capabilityId)
            )
            if value in self._list:
                self.current_option = self._list[value]
        except ValueError:
            return


class CozytouchDurationSelect(SelectEntity, CozytouchSensor):
    """A duration in minutes, offered on the grid the device declares.

    A number entity cannot promise a step, which is why this is a select. See
    docs/decisions.md.
    """

    def __init__(
        self,
        coordinator: Hub,
        capability,
        config_title: str,
        config_uniq_id: str,
        name: str | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialize a Select entity."""
        capabilityId = capability.capabilityId
        super().__init__(
            coordinator=coordinator,
            capability=capability,
            config_title=config_title,
            config_uniq_id=config_uniq_id,
            attr_uniq_id=f"{DOMAIN}_{config_uniq_id}_select_{capabilityId!s}",
            name=name,
            icon=icon,
        )
        self._attr_options = []
        self._attr_current_option = None

    def _grid_value(self, idField: str, fallbackField: str) -> int:
        """One grid bound, from its sibling capability when the device has it."""
        if idField in self._capability:
            value = self.coordinator.get_capability_value(
                self._capability.get(idField), None
            )
            if value is not None:
                try:
                    return int(value)
                except ValueError:
                    pass
        return int(self._capability.get(fallbackField, 0))

    @callback
    def _handle_coordinator_update(self) -> None:
        """Rebuild the grid and place the current value on it."""
        self._attr_options = duration_options(
            self._grid_value("lowestValueCapabilityId", "lowest_value"),
            self._grid_value("highestValueCapabilityId", "highest_value"),
            self._grid_value("stepCapabilityId", "step"),
        )

        value = self.coordinator.get_capability_value(self._capability.capabilityId)
        try:
            current = format_duration(int(value))
        except (TypeError, ValueError):
            current = None

        # A value off the grid reads as unknown rather than as a guessed option.
        self._attr_current_option = (
            current if current in self._attr_options else None
        )
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Write the minutes the option stands for."""
        await self.coordinator.set_capability_value(
            self._capability.capabilityId,
            str(parse_duration(option)),
        )
        await self.coordinator.async_request_refresh()


class CozytouchSystemServiceSelect(CozytouchDeviceEntity, SelectEntity):
    """The service the whole system runs, general stop included.

    The app's own dropdown, shown on every room and moving all of them ; the
    room's climate entity switching off stays the room's alone. See
    docs/decisions.md.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:home-thermometer"

    def __init__(
        self,
        coordinator: Hub,
        capability,
        config_title: str,
        config_uniq_id: str,
    ) -> None:
        """Initialize a Select entity."""
        super().__init__(coordinator)

        capabilityId = capability.capabilityId
        self._capability = capability
        self._device_uniq_id = config_uniq_id
        self._attr_translation_key = capability.name
        self._attr_unique_id = f"{DOMAIN}_{config_uniq_id}_select_{capabilityId!s}"

        modes = narrowed_modes(
            coordinator.get_model_infos().get("HVACModes", {}),
            coordinator.get_capability_value(SUPPORTED_MODES_CAPABILITY_ID, None),
        )
        offered = {
            SERVICE_VALUES[str(value)]: str(value)
            for value in modes
            if str(value) in SERVICE_VALUES
        }
        self._values = {
            option: offered[option] for option in sorted(offered, key=_app_order)
        }
        self._attr_options = list(self._values)

    @property
    def current_option(self) -> str | None:
        """The service running, or unknown for one the list does not offer."""
        value = self.coordinator.get_capability_value(
            self._capability.capabilityId, None
        )
        option = SERVICE_VALUES.get(str(value))
        return option if option in self._values else None

    async def async_select_option(self, option: str) -> None:
        """Write the service ; every room of the system follows."""
        await self.coordinator.set_capability_value(
            self._capability.capabilityId, self._values[option]
        )
        await self.coordinator.async_request_refresh()


def _app_order(option: str) -> int:
    if option in SYSTEM_SERVICE_ORDER:
        return SYSTEM_SERVICE_ORDER.index(option)
    return len(SYSTEM_SERVICE_ORDER)
