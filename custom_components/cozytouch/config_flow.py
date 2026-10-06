"""Config flow for Atlantic Cozytouch integration.

One entry per Atlantic account, one subentry per device on it. See
docs/decisions.md.
"""
from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow as BaseConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

# Both come from account.py, which is where they are raised. Declaring them
# here again would put two different classes under one name, either of which
# could shadow the other depending on import order.
from .account import CannotConnect, CozytouchAccount, InvalidAuth
from .const import DOMAIN
from .hub import (
    DEFAULT_POLL_INTERVAL,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
    POLL_INTERVAL_OPTION,
)

_LOGGER = logging.getLogger(__name__)

# The subentry type the devices are added as. One type: every device on a
# Cozytouch account is the same kind of thing to this integration, a numeric
# id whose capabilities have to be translated.
SUBENTRY_TYPE = "device"


async def validate_input(hass: HomeAssistant, data: dict) -> CozytouchAccount:
    """Validate the user input allows us to connect.

    InvalidAuth for a refused password, CannotConnect for an account that could
    not be asked ; the caller says something different for each.
    """
    account = CozytouchAccount(hass, data["username"], data["password"])
    if not await account.connect():
        raise CannotConnect

    return account


def _device_options(
    devices: list[dict], taken: set[int]
) -> list[selector.SelectOptionDict]:
    """The devices left to add, as a picker lists them.

    Only the device id travels in the option value. See docs/decisions.md.
    """
    return [
        selector.SelectOptionDict(
            label=f"{device['name']} ({device['model']})",
            value=str(device["deviceId"]),
        )
        for device in devices
        if device["deviceId"] not in taken
    ]


def _devices_taken(entry: ConfigEntry) -> set[int]:
    """The device ids this entry already has a subentry for."""
    return {
        subentry.data["deviceId"]
        for subentry in entry.subentries.values()
        if "deviceId" in subentry.data
    }


def _subentry_for(device: dict) -> dict[str, Any]:
    """One device, as a subentry.

    The unique id is the device's own : Home Assistant refuses a second
    subentry carrying it, so a device cannot be added twice even if two flows
    race for it.
    """
    return {
        "subentry_type": SUBENTRY_TYPE,
        "title": device["name"],
        "unique_id": f"cozytouch_{device['deviceId']}",
        "data": {"deviceId": device["deviceId"], "name": device["name"]},
    }


class ConfigFlow(BaseConfigFlow, domain=DOMAIN):
    """Handle a config flow for Atlantic Cozytouch."""

    # 2: one entry per account with a subentry per device. A version 1 entry
    # is one entry per device, whose data this no longer understands -- there
    # is no migration, so it lands in MIGRATION_ERROR and asks to be added
    # again, which is a sentence rather than a traceback.
    VERSION = 2
    # 2.2: the per-day program sensors of a calendar-covered block are
    # disabled by default, and async_migrate_entry disables the ones an
    # existing install already registered. See docs/decisions.md.
    MINOR_VERSION = 5

    def __init__(self) -> None:
        """Init the flow."""
        self._credentials: dict[str, str] = {}
        self._devices: list[dict] = []

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowHandler:
        """Return the options flow, without which HA shows no Configure button."""
        return OptionsFlowHandler()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Say that devices are added to an account, not alongside it."""
        return {SUBENTRY_TYPE: DeviceSubentryFlowHandler}

    async def async_step_user(self, user_input=None):
        """Handle the initial step: the account."""
        errors = {}
        if user_input is not None:
            try:
                account = await validate_input(self.hass, user_input)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                # Used to say invalid_auth too, so a timeout told people their
                # password was wrong and sent them off to reset it.
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # One entry per account, so a second attempt at the same
                # username stops here instead of doubling every poll.
                await self.async_set_unique_id(
                    "cozytouch_" + user_input["username"].lower()
                )
                self._abort_if_unique_id_configured()

                self._credentials = {
                    "username": user_input["username"],
                    "password": user_input["password"],
                }
                self._devices = account.device_summaries()

                return await self.async_step_devices()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required("username"): str, vol.Required("password"): str}
            ),
            errors=errors,
        )

    async def async_step_devices(self, user_input=None):
        """Pick which devices on the account get entities."""
        if user_input is not None:
            chosen = {int(deviceId) for deviceId in user_input["devices"]}

            return self.async_create_entry(
                title=self._credentials["username"],
                data=self._credentials,
                options={
                    "create_unknown": user_input["create_unknown"],
                    "dump_json": user_input["dump_json"],
                },
                subentries=[
                    _subentry_for(device)
                    for device in self._devices
                    if device["deviceId"] in chosen
                ],
            )

        options = _device_options(self._devices, taken=set())
        if not options:
            return self.async_abort(reason="no_devices")

        return self.async_show_form(
            step_id="devices",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "devices", default=[option["value"] for option in options]
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            mode=selector.SelectSelectorMode.LIST,
                            multiple=True,
                            options=options,
                        )
                    ),
                    vol.Required("create_unknown", default=False): bool,
                    vol.Required("dump_json", default=False): bool,
                }
            ),
        )


    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start over from a password Atlantic no longer accepts.

        Called when setup or a poll raises ConfigEntryAuthFailed.
        """
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the password again, and check it before storing it.

        One entry per account, so one dialog and one write. See
        docs/decisions.md.
        """
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            # The username is not asked for again. Changing it would point the
            # entry at a different account, where the deviceId of every
            # subentry means nothing or, worse, something else.
            try:
                await validate_input(
                    self.hass,
                    {
                        "username": entry.data["username"],
                        "password": user_input["password"],
                    },
                )
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={"password": user_input["password"]}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required("password"): str}),
            description_placeholders={"username": entry.data["username"]},
            errors=errors,
        )


class DeviceSubentryFlowHandler(ConfigSubentryFlow):
    """Add one more device of an account that is already set up."""

    def __init__(self) -> None:
        """Init the flow."""
        self._devices: list[dict] | None = None

    async def async_step_user(self, user_input=None) -> SubentryFlowResult:
        """Pick a device the account has and this entry does not."""
        entry = self._get_entry()

        # Read once and kept across the submit. See docs/decisions.md.
        if self._devices is None:
            try:
                account = await validate_input(self.hass, dict(entry.data))
            except InvalidAuth:
                # The stored password has gone stale. Saying so beats an empty
                # device list, and the reauth dialog is one poll away.
                return self.async_abort(reason="invalid_auth")
            except CannotConnect:
                return self.async_abort(reason="cannot_connect")

            self._devices = account.device_summaries()

        options = _device_options(self._devices, taken=_devices_taken(entry))
        if not options:
            return self.async_abort(reason="no_new_devices")

        if user_input is not None:
            deviceId = int(user_input["device"])
            device = next(
                device for device in self._devices
                if device["deviceId"] == deviceId
            )
            subentry = _subentry_for(device)

            return self.async_create_entry(
                title=subentry["title"],
                data=subentry["data"],
                unique_id=subentry["unique_id"],
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("device"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            mode=selector.SelectSelectorMode.LIST, options=options
                        )
                    )
                }
            ),
        )


class OptionsFlowHandler(OptionsFlow):
    """Handles the options of a Cozytouch account.

    All three are account-wide. See docs/decisions.md.
    """

    def _current(self, key: str, default: Any = False) -> Any:
        """Read an option, falling back to the value picked at setup time."""
        return self.config_entry.options.get(
            key, self.config_entry.data.get(key, default)
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "create_unknown", default=self._current("create_unknown")
                    ): bool,
                    vol.Required(
                        "dump_json", default=self._current("dump_json")
                    ): bool,
                    # Bounded by the selector rather than only by the code that
                    # reads it, so the floor is visible while somebody is
                    # typing instead of silently applied afterwards.
                    vol.Required(
                        POLL_INTERVAL_OPTION,
                        default=self._current(
                            POLL_INTERVAL_OPTION, DEFAULT_POLL_INTERVAL
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=MIN_POLL_INTERVAL,
                            max=MAX_POLL_INTERVAL,
                            step=5,
                            unit_of_measurement="s",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
        )
