"""Config flow for Atlantic Cozytouch integration."""
from __future__ import annotations

import ast
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries, exceptions
from homeassistant.core import HomeAssistant
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
                hub.close()
                return self.async_show_form(
                    step_id="select_device",
                    data_schema=vol.Schema(
                        {
                            vol.Required("device"): selector.SelectSelector(
                                selector.SelectSelectorConfig(
                                    mode=selector.SelectSelectorMode.DROPDOWN,
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
                                        for device in devices
                                    ],
                                )
                            ),
                            vol.Required("create_unknown", default=False): bool,
                        }
                    ),
                    errors=errors,
                )

            except CannotConnect:
                errors["base"] = "invalid_auth"
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
            return self.async_create_entry(title=device_data["name"], data=device_data)

        return self.async_abort()


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate there is invalid auth."""
