"""Config flow for Atlantic Cozytouch integration."""
from __future__ import annotations

import ast
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries, exceptions
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import DOMAIN
from .hub import Hub

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: HomeAssistant, data: dict) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from DATA_SCHEMA with values provided by the user.
    """

    hub = Hub(hass, data["username"], data["password"])
    result = await hub.test_connection()
    if not result:
        raise CannotConnect

    return hub


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Atlantic Cozytouch."""

    VERSION = 1
    # Pick one of the available connection classes in homeassistant/config_entries.py
    # This tells HA if it should be asking for updates, or it'll be notified of updates
    # automatically. This example uses PUSH, as the dummy hub will notify HA of
    # changes.
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""

        errors = {}
        if user_input is not None:
            try:
                hub = await validate_input(self.hass, user_input)
                devices = hub.devices()
                await hub.close()

                new_devices = []
                current_entries = self._async_current_entries()

                for device in devices:
                    existing_entry = next(
                        (
                            entry
                            for entry in current_entries
                            if entry.data.get("deviceId", "") == device["deviceId"]
                        ),
                        None,
                    )
                    if not existing_entry:
                        new_devices.append(device)

                if len(new_devices) == 0:
                    raise NoNewDevice()

                return self.async_show_form(
                    step_id="select_device",
                    data_schema=vol.Schema(
                        {
                            vol.Required("device"): selector.SelectSelector(
                                selector.SelectSelectorConfig(
                                    mode=selector.SelectSelectorMode.LIST,
                                    options=[
                                        selector.SelectOptionDict(
                                            label=device["name"],
                                            value=str(
                                                {
                                                    "deviceId": device["deviceId"],
                                                    "name": device["name"],
                                                    "username": user_input["username"],
                                                    "password": user_input["password"],
                                                }
                                            ),
                                        )
                                        for device in new_devices
                                    ],
                                )
                            ),
                            vol.Required("create_unknown", default=False): bool,
                            vol.Required("dump_json", default=False): bool,
                        }
                    ),
                    errors=errors,
                )

            except CannotConnect:
                errors["base"] = "invalid_auth"
            except NoNewDevice:
                errors["base"] = "No new device found"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        # If there is no user input or there were errors, show the form again, including any errors that were found with the input.
        user_schema = vol.Schema(
            {vol.Required("username"): str, vol.Required("password"): str}
        )

        return self.async_show_form(
            step_id="user", data_schema=user_schema, errors=errors
        )

    async def async_step_select_device(self, device_input=None):
        """Handle the device selection step."""
        if device_input is not None and "device" in device_input:
            device_data = ast.literal_eval(device_input["device"])
            device_data["create_unknown"] = device_input["create_unknown"]
            device_data["dump_json"] = device_input["dump_json"]

            await self.async_set_unique_id(
                "cozytouch_" + str(device_data["deviceId"]), raise_on_progress=False
            )
            return self.async_create_entry(
                title=device_data["name"],
                data=device_data,
            )

        return self.async_abort()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handles the options of a Cozytouch device."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

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
                        "create_unknown",
                        default=self.config_entry.data.get("create_unknown"),
                    ): bool,
                    vol.Required(
                        "dump_json", default=self.config_entry.data.get("dump_json")
                    ): bool,
                }
            ),
        )


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class NoNewDevice(exceptions.HomeAssistantError):
    """Error to indicate we didn't find new device."""


class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate there is invalid auth."""
