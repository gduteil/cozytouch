"""Fans for Atlantic Cozytouch integration.

Air circulation is one thing the hardware does and three entities the
integration used to expose : a switch, a speed, and a duration. Home Assistant
has a word for "runs, at a speed", and a card and a voice assistant that know
it. See docs/decisions.md.
"""

from __future__ import annotations

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)

from .const import DOMAIN
from .hub import (
    CozytouchConfigEntry,
    CozytouchDeviceEntity,
    Hub,
    add_capability_entities,
)
from .infos import CapabilityType


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
        {CapabilityType.FAN: CozytouchFan},
    )


class CozytouchFan(CozytouchDeviceEntity, FanEntity):
    """A capability that runs, at a speed the row beside it names."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: Hub,
        capability,
        config_title: str,
        config_uniq_id: str,
    ) -> None:
        """Initialize a fan entity."""
        super().__init__(coordinator)

        capabilityId = capability.capabilityId
        self._capability = capability
        self._device_uniq_id = config_uniq_id
        self._attr_translation_key = capability.name
        self._attr_unique_id = f"{DOMAIN}_{config_uniq_id}_fan_{capabilityId!s}"

        # The speeds this model names, in the order they climb. A model that
        # names none leaves a fan that only runs or does not.
        modelInfos = coordinator.get_model_infos()
        self._speeds: list[str] = [
            str(value)
            for value in sorted(modelInfos.get(capability.get("modelList"), {}))
        ]

        self._speed_capabilityId = capability.get("speedCapabilityId")
        self._value_off = capability.get("value_off", "0")
        self._value_on = capability.get("value_on", "1")

        self._attr_supported_features = (
            FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
        )
        if self._speeds and self._speed_capabilityId is not None:
            self._attr_supported_features |= FanEntityFeature.SET_SPEED

    @property
    def _has_speeds(self) -> bool:
        """Whether this device lets a speed be asked for at all."""
        return FanEntityFeature.SET_SPEED in self._attr_supported_features

    @property
    def is_on(self) -> bool:
        """Whether the fan is running."""
        value = self.coordinator.get_capability_value(
            self._capability.capabilityId
        )
        return value == self._value_on

    @property
    def speed_count(self) -> int:
        """How many speeds this model has, which HA turns into percentages."""
        return len(self._speeds) or 1

    @property
    def percentage(self) -> int | None:
        """The speed as a percentage, which is the only thing HA speaks.

        A fan that is off reads 0 rather than its last speed: that is what
        makes a card's slider agree with the switch beside it.
        """
        if not self.is_on:
            return 0

        if not self._has_speeds:
            return 100

        value = self.coordinator.get_capability_value(
            self._speed_capabilityId, None
        )
        if value not in self._speeds:
            return None

        return ordered_list_item_to_percentage(self._speeds, value)

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed, or stop when asked for none."""
        if percentage == 0:
            await self.async_turn_off()
            return

        if self._has_speeds:
            await self.coordinator.set_capability_value(
                self._speed_capabilityId,
                percentage_to_ordered_list_item(self._speeds, percentage),
            )

        if not self.is_on:
            await self.coordinator.set_capability_value(
                self._capability.capabilityId, self._value_on
            )

        await self.coordinator.async_request_refresh()

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs,
    ) -> None:
        """Start the fan, at a speed when one was asked for."""
        if percentage:
            await self.async_set_percentage(percentage)
            return

        await self.coordinator.set_capability_value(
            self._capability.capabilityId, self._value_on
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Stop the fan."""
        await self.coordinator.set_capability_value(
            self._capability.capabilityId, self._value_off
        )
        await self.coordinator.async_request_refresh()
