"""The Sauter Pagosa, read and driven through Atlantic's Overkiz plane.

The Pagosa is not in the Cozytouch setup view the rest of the integration
reads. The same account opens an Overkiz session, whose setup lists the
heater and its energy meter. One PagosaHub per Pagosa subentry, with its own
session, polled on its own clock : nothing here touches the account's
coordinator. See docs/decisions.md, *The Pagosa through Overkiz*.
"""

from __future__ import annotations

import asyncio
import copy
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
import logging
import time
from urllib.parse import quote

from aiohttp import ClientError, ClientSession, FormData

from homeassistant import exceptions
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from ..const import COZYTOUCH_ATLANTIC_API, COZYTOUCH_CLIENT_ID

_LOGGER = logging.getLogger(__name__)

OVERKIZ_HOST = "https://ha110-1.overkiz.com"
OVERKIZ_API = "/enduser-mobile-web/enduserAPI"

PAGOSA_CONTROLLABLE_NAME = "io:AtlanticDomesticHotWaterProductionV3IOComponent"
PAGOSA_ENERGY_CONTROLLABLE_NAME = (
    "io:DHWCumulatedElectricalEnergyConsumptionIOSystemDeviceSensor"
)
PAGOSA_MODEL = "Sauter Pagosa 270L"

OVERKIZ_UPDATE_INTERVAL = 240  # see docs/decisions.md
OVERKIZ_MIN_REFRESH_INTERVAL = 30
OVERKIZ_DEFAULT_RETRY_DELAY = 300
OVERKIZ_MAX_RETRY_DELAY = 3600  # see docs/decisions.md
OVERKIZ_FULL_SETUP_INTERVAL = 3600  # see docs/decisions.md


def is_overkiz_device_id(deviceId) -> bool:
    """An Overkiz device URL (io://...), rather than a Cozytouch device id."""
    return isinstance(deviceId, str) and "://" in deviceId


# Overkiz refuses a programming without slot2, so a single slot is written
# with this second one ; see docs/decisions.md, *The Pagosa's time slots*.
NO_SLOT = {"start": "00:00", "end": "00:00"}


def programming_slots(slots: list[tuple[str, str]]) -> dict:
    """The setProgrammingSlots value for one or two (start, end) slots."""
    if not 1 <= len(slots) <= 2:
        raise ValueError("The Pagosa takes one or two time slots")

    value: dict = {}
    for number, (start, end) in enumerate(slots, start=1):
        if start == end:
            raise ValueError(f"Time slot {number} starts and ends at {start}")
        value[f"slot{number}"] = {"start": start, "end": end}

    value.setdefault("slot2", dict(NO_SLOT))
    return value


class CannotConnect(exceptions.HomeAssistantError):
    """The Overkiz plane could not be reached, or holds no Pagosa."""


class PagosaHub(DataUpdateCoordinator):
    """One Pagosa, through Overkiz."""

    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        password: str,
        deviceId: str | None = None,
        config_entry: ConfigEntry | None = None,
        subentry_id: str | None = None,
    ) -> None:
        """Initialize hub."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name="Cozytouch_" + str(subentry_id or deviceId),
            update_interval=timedelta(seconds=OVERKIZ_UPDATE_INTERVAL),
        )

        # Its own session, as on 1.4 : the Overkiz login sets a cookie that
        # must not leak into Home Assistant's shared one.
        self._session = ClientSession()
        self._hass = hass
        self._username = username
        self._password = password
        self._deviceId = deviceId
        self.subentry_id = subentry_id
        self._access_token = ""
        self._id = "cozytouch." + username.lower()
        # The Atlantic setup, read only for the Absence period it carries.
        self._setup: dict = {}

        self._overkiz_host = OVERKIZ_HOST
        self._overkiz_jwt = None
        self._overkiz_setup = None
        self._overkiz_devices = []
        self._overkiz_device = None
        self._overkiz_energy_device = None
        self._overkiz_states = {}
        self._overkiz_energy_states = {}
        self._overkiz_gateway = None
        self._is_overkiz = False

        self._overkiz_last_setup_refresh = 0.0
        self._overkiz_retry_after = 0.0
        self._overkiz_command_retry_after = 0.0
        self._overkiz_last_full_setup = 0.0
        self._overkiz_refresh_lock = asyncio.Lock()
        self._overkiz_auth_lock = asyncio.Lock()

        # Pagosa operations are serialized as complete transactions.
        self._pagosa_command_lock = asyncio.Lock()
        self._pagosa_optimistic_states = {}

        self.online = False

    @property
    def hub_id(self) -> str:
        """Return hub ID."""
        return self._id
    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def _authenticate_atlantic(self) -> bool:
        """Obtain a fresh Atlantic access token."""
        try:
            async with self._session.post(
                COZYTOUCH_ATLANTIC_API + "/users/token",
                data=FormData(
                    {
                        "grant_type": "password",
                        "scope": "openid",
                        "username": "GA-PRIVATEPERSON/" + self._username,
                        "password": self._password,
                    }
                ),
                headers={
                    "Authorization": f"Basic {COZYTOUCH_CLIENT_ID}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            ) as response:
                token = await response.json(content_type=None)

                if response.status != 200:
                    _LOGGER.error(
                        "Atlantic authentication failed: HTTP %s",
                        response.status,
                    )
                    return False

                if (
                    not isinstance(token, dict)
                    or token.get("error") == "invalid_grant"
                    or "access_token" not in token
                ):
                    _LOGGER.error("Atlantic did not return a valid access token")
                    return False

                self._access_token = token["access_token"]
                return True

        except Exception:
            _LOGGER.exception("Unable to authenticate with Atlantic")
            return False

    async def _login_overkiz(self) -> bool:
        """Obtain a fresh Overkiz JWT and establish a new Overkiz session."""
        async with self._overkiz_auth_lock:
            if not await self._authenticate_atlantic():
                self.online = False
                return False

            try:
                async with self._session.get(
                    COZYTOUCH_ATLANTIC_API + "/magellan/accounts/jwt",
                    headers={
                        "Authorization": f"Bearer {self._access_token}",
                        "Content-Type": "application/json",
                    },
                ) as response:
                    if response.status == 429:
                        self._record_overkiz_rate_limit(response, "JWT")
                        return False

                    if response.status != 200:
                        _LOGGER.error(
                            "Overkiz JWT request failed: HTTP %s",
                            response.status,
                        )
                        return False

                    jwt_data = await response.json(content_type=None)

                if isinstance(jwt_data, dict):
                    jwt = (
                        jwt_data.get("jwt")
                        or jwt_data.get("token")
                        or jwt_data.get("access_token")
                    )
                elif isinstance(jwt_data, str):
                    jwt = jwt_data
                else:
                    jwt = None

                if not jwt:
                    _LOGGER.error("Atlantic did not return an Overkiz JWT")
                    return False

                async with self._session.post(
                    self._overkiz_host + OVERKIZ_API + "/login",
                    data={"jwt": jwt},
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                ) as response:
                    if response.status == 429:
                        self._record_overkiz_rate_limit(response, "login")
                        return False

                    login_data = await response.json(content_type=None)

                    if response.status != 200 or not login_data.get("success"):
                        _LOGGER.error(
                            "Overkiz login failed: HTTP %s",
                            response.status,
                        )
                        return False

                self._overkiz_jwt = jwt
                _LOGGER.info("Overkiz authentication renewed successfully")
                return True

            except Exception:
                _LOGGER.exception("Unable to renew Overkiz authentication")
                return False

    async def connect(self) -> bool:
        """Open the Overkiz session, find the Pagosa, read the Absence period.

        The period lives in the Atlantic setup, which 1.4-pagosa read on
        connecting : without it the end of an Absence under way reads unknown
        until the next throttled refresh.
        """
        if self.online:
            return True
        if not await self._connect_overkiz():
            return False
        await self._read_atlantic_setup()
        return True

    async def _read_atlantic_setup(self) -> None:
        """Keep the Atlantic setup's description and Absence period."""
        try:
            async with self._session.get(
                COZYTOUCH_ATLANTIC_API + "/magellan/cozytouch/setupviewv2",
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Content-Type": "application/json",
                },
            ) as response:
                if response.status != 200:
                    _LOGGER.warning(
                        "Atlantic setup unavailable (HTTP %s)", response.status
                    )
                    return
                data = await response.json(content_type=None)
        except Exception:  # noqa: BLE001 - the Absence period is not vital
            _LOGGER.warning("Unable to read the Atlantic setup", exc_info=True)
            return

        if isinstance(data, list) and data and isinstance(data[0], dict):
            for key in (
                "absence",
                "address",
                "area",
                "currency",
                "id",
                "mainDHWEnergy",
                "mainHeatingEnergy",
                "name",
                "numberOfPersons",
                "numberOfRooms",
                "setupBuildingDate",
                "type",
            ):
                if key in data[0]:
                    self._setup[key] = copy.deepcopy(data[0][key])

    async def pagosa_summaries(self) -> list[dict]:
        """Every Pagosa the Overkiz setup lists, as the config flow offers them."""
        if not await self._login_overkiz():
            raise CannotConnect
        async with self._session.get(
            self._overkiz_host + OVERKIZ_API + "/setup",
        ) as response:
            if response.status != 200:
                raise CannotConnect
            setup_data = await response.json(content_type=None)

        return [
            {
                "deviceId": device["deviceURL"],
                "name": device.get("label")
                or device.get("deviceName")
                or "Sauter Pagosa",
                "model": PAGOSA_MODEL,
            }
            for device in self._extract_overkiz_devices(setup_data)
            if isinstance(device, dict)
            and device.get("controllableName") == PAGOSA_CONTROLLABLE_NAME
            and device.get("deviceURL")
        ]

    async def _connect_overkiz(self) -> bool:
        """Connect to Overkiz using a fresh Atlantic JWT."""
        try:
            if not await self._login_overkiz():
                return False

            async with self._session.get(
                self._overkiz_host + OVERKIZ_API + "/setup",
            ) as response:
                if response.status == 429:
                    self._record_overkiz_rate_limit(response, "initial setup")
                    return False

                if response.status != 200:
                    _LOGGER.error(
                        "Overkiz setup failed: HTTP %s",
                        response.status,
                    )
                    return False

                setup_data = await response.json(content_type=None)

            self._apply_overkiz_setup(setup_data)

            if self._overkiz_device is None:
                _LOGGER.error("Pagosa water heater not found in Overkiz setup")
                return False

            self._is_overkiz = True
            self._deviceId = self._overkiz_device.get("deviceURL")
            self._overkiz_last_setup_refresh = time.monotonic()
            self._overkiz_last_full_setup = self._overkiz_last_setup_refresh
            self._overkiz_retry_after = 0.0
            self._overkiz_command_retry_after = 0.0
            self.online = True

            _LOGGER.info(
                "Overkiz connected. Pagosa found: %s (%s). Energy device: %s",
                self._overkiz_device.get("label")
                or self._overkiz_device.get("deviceName"),
                self._deviceId,
                (
                    self._overkiz_energy_device.get("deviceURL")
                    if self._overkiz_energy_device
                    else "not found"
                ),
            )

            if self._overkiz_energy_device is None:
                _LOGGER.warning(
                    "Pagosa energy sensor device was not found in setup"
                )

            return True

        except Exception:
            _LOGGER.exception("Unable to connect to Overkiz")
            self.online = False
            return False

    # ------------------------------------------------------------------
    # Overkiz setup and state handling
    # ------------------------------------------------------------------

    def _apply_overkiz_setup(self, setup_data) -> None:
        """Store setup data and update selected devices and states."""
        self._overkiz_setup = setup_data
        self._overkiz_devices = self._extract_overkiz_devices(setup_data)
        self._overkiz_gateway = (
            setup_data.get("gateway")
            if isinstance(setup_data, dict)
            else None
        )
        self._select_overkiz_devices()
        self._read_overkiz_states_from_setup()

    @staticmethod
    def _extract_overkiz_devices(setup_data) -> list:
        """Extract devices from Overkiz setup response."""
        if isinstance(setup_data, dict):
            devices = setup_data.get("devices", [])
            return devices if isinstance(devices, list) else []

        if isinstance(setup_data, list):
            devices = []
            for item in setup_data:
                if isinstance(item, dict):
                    item_devices = item.get("devices", [])
                    if isinstance(item_devices, list):
                        devices.extend(item_devices)
            return devices

        return []

    def _select_overkiz_devices(self) -> None:
        """Select Pagosa heater and its energy sensor."""
        self._overkiz_device = None
        self._overkiz_energy_device = None

        for device in self._overkiz_devices:
            if not isinstance(device, dict):
                continue

            if device.get("deviceURL") == self._deviceId:
                self._overkiz_device = device

            if device.get("controllableName") == PAGOSA_CONTROLLABLE_NAME:
                self._overkiz_device = device

            if (
                device.get("controllableName")
                == PAGOSA_ENERGY_CONTROLLABLE_NAME
            ):
                self._overkiz_energy_device = device

        if self._overkiz_device is None:
            self._overkiz_device = next(
                (
                    device
                    for device in self._overkiz_devices
                    if isinstance(device, dict)
                    and device.get("controllableName")
                    == PAGOSA_CONTROLLABLE_NAME
                ),
                None,
            )

        if self._overkiz_energy_device is None and self._overkiz_device:
            heater_url = self._overkiz_device.get("deviceURL", "")
            base_url = heater_url.split("#", 1)[0]
            self._overkiz_energy_device = next(
                (
                    device
                    for device in self._overkiz_devices
                    if isinstance(device, dict)
                    and device.get("deviceURL", "").startswith(base_url + "#")
                    and device.get("controllableName")
                    == PAGOSA_ENERGY_CONTROLLABLE_NAME
                ),
                None,
            )

    def _read_overkiz_states_from_setup(self) -> None:
        """Read heater and energy states from setup response."""
        self._overkiz_states = {}
        self._overkiz_energy_states = {}

        if self._overkiz_device:
            for state in self._overkiz_device.get("states", []):
                if isinstance(state, dict) and "name" in state:
                    self._overkiz_states[state["name"]] = state.get("value")

        if self._overkiz_energy_device:
            for state in self._overkiz_energy_device.get("states", []):
                if isinstance(state, dict) and "name" in state:
                    self._overkiz_energy_states[state["name"]] = (
                        state.get("value")
                    )

    @staticmethod
    def _get_retry_delay(response) -> int:
        """Get retry delay from Retry-After header."""
        retry_after = response.headers.get("Retry-After")

        if retry_after:
            try:
                return max(1, int(retry_after))
            except ValueError:
                try:
                    retry_date = parsedate_to_datetime(retry_after)
                    now = datetime.now(retry_date.tzinfo)
                    return max(1, int((retry_date - now).total_seconds()))
                except (TypeError, ValueError, OverflowError):
                    pass

        return OVERKIZ_DEFAULT_RETRY_DELAY

    def _record_overkiz_rate_limit(
        self, response, context: str, command: bool = False
    ) -> int:
        """Record the server's rate-limit delay, capped, for one kind of request.

        A 429 on the setup only holds back the polls, and one on a command only
        the commands : Overkiz answers them separately (docs/decisions.md).
        """
        asked = self._get_retry_delay(response)
        delay = min(asked, OVERKIZ_MAX_RETRY_DELAY)
        attribute = (
            "_overkiz_command_retry_after" if command else "_overkiz_retry_after"
        )
        setattr(
            self,
            attribute,
            max(getattr(self, attribute, 0.0), time.monotonic() + delay),
        )
        _LOGGER.warning(
            "Overkiz rate limit reached during %s (HTTP 429, Retry-After %s s). "
            "Next request allowed in %s seconds",
            context,
            asked,
            delay,
        )
        return delay

    def _overkiz_rate_limit_remaining(self) -> int:
        """Return the remaining delay before the next setup poll, in seconds."""
        return max(0, int(self._overkiz_retry_after - time.monotonic()))

    def _overkiz_command_rate_limit_remaining(self) -> int:
        """Return the remaining delay before the next command, in seconds."""
        return max(
            0,
            int(getattr(self, "_overkiz_command_retry_after", 0.0) - time.monotonic()),
        )

    async def _refresh_overkiz_device_states(self) -> bool | None:
        """Read the heater's and the meter's states without the whole setup.

        Returns True when both were read, False when Overkiz refused (429, the
        poll backs off) and None when the full setup should be read instead.
        """
        devices = [self._overkiz_device, self._overkiz_energy_device]
        read: list[list] = []
        for device in devices:
            if not device or not device.get("deviceURL"):
                read.append([])
                continue
            url = (
                self._overkiz_host
                + OVERKIZ_API
                + "/setup/devices/"
                + quote(device["deviceURL"], safe="")
                + "/states"
            )
            async with self._session.get(url) as response:
                if response.status == 429:
                    self._record_overkiz_rate_limit(response, "states refresh")
                    return False
                if response.status != 200:
                    return None
                states = await response.json(content_type=None)
            if not isinstance(states, list):
                return None
            read.append(states)

        for device, states in zip(devices, read, strict=True):
            if device and states:
                device["states"] = states
        self._read_overkiz_states_from_setup()
        return True

    async def _refresh_overkiz_setup(
        self,
        force: bool = False,
    ) -> bool:
        """Refresh Overkiz setup with rate limiting and 401 recovery."""
        if not self._is_overkiz:
            return False

        async with self._overkiz_refresh_lock:
            remaining = self._overkiz_rate_limit_remaining()
            if remaining:
                _LOGGER.debug(
                    "Overkiz refresh postponed for %s seconds",
                    remaining,
                )
                return False

            elapsed = time.monotonic() - self._overkiz_last_setup_refresh
            if not force and elapsed < OVERKIZ_MIN_REFRESH_INTERVAL:
                _LOGGER.debug(
                    "Overkiz refresh skipped (last refresh %.1f seconds ago)",
                    elapsed,
                )
                return False

            if (
                self._overkiz_device
                and time.monotonic() - self._overkiz_last_full_setup
                < OVERKIZ_FULL_SETUP_INTERVAL
            ):
                try:
                    light = await self._refresh_overkiz_device_states()
                except (ClientError, TimeoutError, ValueError):
                    _LOGGER.debug(
                        "Overkiz states refresh failed; reading the setup",
                        exc_info=True,
                    )
                    light = None
                if light is not None:
                    if light:
                        self._overkiz_last_setup_refresh = time.monotonic()
                        self.online = True
                    return light

            for attempt in range(2):
                try:
                    async with self._session.get(
                        self._overkiz_host + OVERKIZ_API + "/setup",
                    ) as response:
                        if response.status == 401 and attempt == 0:
                            _LOGGER.warning(
                                "Overkiz session expired during setup refresh; "
                                "reauthenticating"
                            )
                            if not await self._login_overkiz():
                                self.online = False
                                return False
                            continue

                        if response.status == 429:
                            self._record_overkiz_rate_limit(
                                response, "setup refresh"
                            )
                            return False

                        if response.status != 200:
                            _LOGGER.warning(
                                "Overkiz setup refresh failed: HTTP %s",
                                response.status,
                            )
                            return False

                        setup_data = await response.json(content_type=None)

                    self._apply_overkiz_setup(setup_data)

                    if self._overkiz_device is None:
                        _LOGGER.warning(
                            "Pagosa device was not found during Overkiz refresh"
                        )
                        return False

                    self._overkiz_last_setup_refresh = time.monotonic()
                    self._overkiz_last_full_setup = self._overkiz_last_setup_refresh
                    self.online = True
                    return True

                except Exception:
                    _LOGGER.exception("Unable to refresh Overkiz setup")
                    return False

            return False

    def get_overkiz_state(self, state_name: str, default=None):
        """Return a Pagosa state, including a temporary optimistic state."""
        if state_name in self._pagosa_optimistic_states:
            return self._pagosa_optimistic_states[state_name]

        return self._overkiz_states.get(state_name, default)

    def get_overkiz_device(self):
        """Return the Pagosa heater device."""
        return self._overkiz_device

    def get_overkiz_states(self):
        """Return all Pagosa heater states."""
        return self._overkiz_states.copy()

    def get_overkiz_energy_device(self):
        """Return the Pagosa energy sensor device."""
        return self._overkiz_energy_device

    def get_overkiz_energy_state(self, state_name: str, default=None):
        """Return a Pagosa energy sensor state."""
        return self._overkiz_energy_states.get(state_name, default)

    def get_overkiz_energy_states(self):
        """Return all Pagosa energy sensor states."""
        return self._overkiz_energy_states.copy()

    def is_overkiz(self) -> bool:
        """Return whether the selected device uses Overkiz."""
        return self._is_overkiz

    def get_overkiz_commands(self) -> set[str]:
        """Return command names advertised by Pagosa."""
        if not self._overkiz_device:
            return set()

        commands = self._overkiz_device.get("availableCommands", [])
        result = set()

        for command in commands:
            if isinstance(command, str):
                result.add(command)
            elif isinstance(command, dict) and command.get("name"):
                result.add(command["name"])

        return result

    # ------------------------------------------------------------------
    # Overkiz commands
    # ------------------------------------------------------------------

    async def async_execute_overkiz_command(
        self,
        command: str,
        parameters: list | dict | None = None,
        label: str | None = None,
        refresh: bool = True,
    ) -> None:
        """Execute a Pagosa command, recovering once from HTTP 401."""
        if not self._is_overkiz or not self._overkiz_device:
            raise exceptions.HomeAssistantError(
                "The Pagosa Overkiz device is not connected"
            )

        remaining = self._overkiz_command_rate_limit_remaining()
        if remaining:
            raise exceptions.HomeAssistantError(
                f"Overkiz rate limit is active. Retry in {remaining} seconds"
            )

        device_url = self._overkiz_device.get("deviceURL")
        if not device_url:
            raise exceptions.HomeAssistantError(
                "The Pagosa device URL is missing"
            )

        available_commands = self.get_overkiz_commands()
        if available_commands and command not in available_commands:
            raise exceptions.HomeAssistantError(
                f"The Pagosa does not advertise the command {command}"
            )

        if parameters is None:
            parameters = []

        payload = {
            "label": label or f"Pagosa: {command}",
            "actions": [
                {
                    "deviceURL": device_url,
                    "commands": [
                        {
                            "name": command,
                            "parameters": parameters,
                        }
                    ],
                }
            ],
        }

        _LOGGER.info(
            "Sending Pagosa command %s with parameters %s",
            command,
            parameters,
        )

        for attempt in range(2):
            remaining = self._overkiz_command_rate_limit_remaining()
            if remaining:
                raise exceptions.HomeAssistantError(
                    f"Overkiz rate limit is active. Retry in {remaining} seconds"
                )

            try:
                async with self._session.post(
                    self._overkiz_host + OVERKIZ_API + "/exec/apply",
                    json=payload,
                ) as response:
                    response_text = await response.text()

                    if response.status == 401 and attempt == 0:
                        _LOGGER.warning(
                            "Overkiz rejected command %s with HTTP 401. "
                            "Renewing session and retrying once",
                            command,
                        )
                        if not await self._login_overkiz():
                            self.online = False
                            raise exceptions.HomeAssistantError(
                                "Overkiz authentication renewal failed. "
                                "Please check the Cozytouch credentials."
                            )
                        continue

                    if response.status == 429:
                        delay = self._record_overkiz_rate_limit(
                            response, f"command {command}", command=True
                        )
                        raise exceptions.HomeAssistantError(
                            f"Overkiz rate limit reached. Retry in {delay} seconds"
                        )

                    if response.status not in (200, 201, 202):
                        _LOGGER.error(
                            "Pagosa command %s failed: HTTP %s - %s",
                            command,
                            response.status,
                            response_text,
                        )
                        raise exceptions.HomeAssistantError(
                            f"Overkiz rejected command {command} "
                            f"(HTTP {response.status}): {response_text}"
                        )

                    break

            except exceptions.HomeAssistantError:
                raise
            except Exception as err:
                _LOGGER.exception(
                    "Error executing Pagosa command %s", command
                )
                raise exceptions.HomeAssistantError(
                    f"Unable to execute Pagosa command {command}: {err}"
                ) from err
        else:
            raise exceptions.HomeAssistantError(
                f"Overkiz authentication failed for command {command}"
            )

        if refresh:
            refreshed = await self._refresh_overkiz_setup(force=False)
            if refreshed:
                self.async_set_updated_data(self.data)

    # ------------------------------------------------------------------
    # Pagosa transaction handling
    # ------------------------------------------------------------------

    async def async_run_pagosa_operation(
        self,
        operation,
        optimistic_states: dict | None = None,
        label: str = "Pagosa operation",
    ) -> None:
        """Run a serialized Pagosa operation and confirm its state."""
        if self._pagosa_command_lock.locked():
            raise exceptions.HomeAssistantError(
                "Une commande Pagosa est déjà en cours. "
                "Réessaie dans quelques secondes."
            )

        async with self._pagosa_command_lock:
            if optimistic_states:
                self._pagosa_optimistic_states.update(optimistic_states)
                self.async_set_updated_data(self.data)

            try:
                await operation()

                # Allow the appliance to apply the command.
                await asyncio.sleep(3)

                # The lock remains held until the refresh attempt has finished.
                refreshed = await self._refresh_overkiz_setup(force=True)

                if refreshed:
                    _LOGGER.debug(
                        "%s: state confirmed by Overkiz",
                        label,
                    )
                else:
                    _LOGGER.warning(
                        "%s: Overkiz state could not be confirmed. "
                        "The next coordinator refresh will retrieve it.",
                        label,
                    )

            finally:
                self._pagosa_optimistic_states.clear()
                self.async_set_updated_data(self.data)

    async def async_set_pagosa_eco(self, enabled: bool) -> None:
        """Set Eco mode."""
        mode = "manualEcoActive" if enabled else "manualEcoInactive"

        async def operation():
            await self.async_execute_overkiz_command(
                "setDHWMode",
                [mode],
                label="Pagosa Eco",
                refresh=False,
            )
            await self.async_execute_overkiz_command(
                "refreshDHWMode",
                refresh=False,
            )
            await self.async_execute_overkiz_command(
                "refreshTargetTemperature",
                refresh=False,
            )

        await self.async_run_pagosa_operation(
            operation,
            {"io:DHWModeState": mode},
            "Pagosa Eco",
        )

    async def async_set_pagosa_boost(self, enabled: bool) -> None:
        """Set Boost without changing its configured duration."""
        current = self._get_current_operating_mode()
        current["relaunch"] = "on" if enabled else "off"

        async def operation():
            await self._set_operating_mode_flag(
                "relaunch",
                "on" if enabled else "off",
            )
            await self.async_execute_overkiz_command(
                "refreshBoostModeDuration",
                refresh=False,
            )

        await self.async_run_pagosa_operation(
            operation,
            {"core:OperatingModeState": current},
            "Pagosa Boost",
        )

    async def async_set_pagosa_away(self, enabled: bool) -> None:
        """Set Absence using the existing command format."""
        current = self._get_current_operating_mode()
        current["absence"] = "on" if enabled else "off"

        async def operation():
            await self._set_operating_mode_flag(
                "absence",
                "on" if enabled else "off",
            )
            await self.async_execute_overkiz_command(
                "refreshAwayModeDuration",
                refresh=False,
            )

        await self.async_run_pagosa_operation(
            operation,
            {"core:OperatingModeState": current},
            "Pagosa Absence",
        )

    async def set_overkiz_target_temperature(self, value: float) -> None:
        """Set Pagosa target temperature."""
        target = float(value)

        async def operation():
            await self.async_execute_overkiz_command(
                "setTargetTemperature",
                [target],
                label="Set Pagosa target temperature",
                refresh=False,
            )
            await self.async_execute_overkiz_command(
                "refreshTargetTemperature",
                refresh=False,
            )

        await self.async_run_pagosa_operation(
            operation,
            {"core:TargetTemperatureState": target},
            "Pagosa target temperature",
        )

    def _get_current_operating_mode(self) -> dict:
        """Return current operating mode without losing either flag."""
        current = self.get_overkiz_state(
            "core:OperatingModeState",
            {},
        )
        if not isinstance(current, dict):
            current = {}

        absence = str(current.get("absence", "off")).lower()
        # The flag stays "on" after an Absence ended ; the duration does not.
        # See docs/decisions.md, *Absence read as over*.
        if absence == "on" and str(
            self.get_overkiz_state("io:AwayModeDurationState", "")
        ) == "0":
            absence = "off"

        return {
            "relaunch": str(current.get("relaunch", "off")).lower(),
            "absence": absence,
        }

    async def _set_operating_mode_flag(
        self,
        flag: str,
        value: str,
    ) -> None:
        """Change one operating mode flag while preserving the other."""
        if flag not in ("relaunch", "absence"):
            raise exceptions.HomeAssistantError(
                f"Unsupported operating mode flag: {flag}"
            )

        operating_mode = self._get_current_operating_mode()
        operating_mode[flag] = value

        await self.async_execute_overkiz_command(
            "setCurrentOperatingMode",
            [operating_mode],
            refresh=False,
        )

    async def set_overkiz_boost_duration(self, value: int) -> None:
        """Set Boost duration only when a positive duration is requested."""
        value = int(value)

        if not 0 <= value <= 7:
            raise exceptions.HomeAssistantError(
                "Boost duration must be between 0 and 7 days"
            )

        # Zero means no change: do not alter the duration or Boost state.
        if value == 0:
            return

        async def operation():
            await self.async_execute_overkiz_command(
                "setBoostModeDuration",
                [value],
                label="Set Pagosa Boost duration",
                refresh=False,
            )
            await asyncio.sleep(1)
            await self._set_operating_mode_flag("relaunch", "on")
            await self.async_execute_overkiz_command(
                "refreshBoostModeDuration",
                refresh=False,
            )

        await self.async_run_pagosa_operation(
            operation,
            None,
            "Pagosa Boost duration",
        )

    async def set_overkiz_away_duration(self, value: int) -> None:
        """Set Absence duration using the existing command sequence."""
        value = int(value)

        if not 0 <= value <= 6:
            raise exceptions.HomeAssistantError(
                "Away duration must be between 0 and 6 days"
            )

        async def operation():
            await self.async_execute_overkiz_command(
                "setAwayModeDuration",
                [value],
                label="Set Pagosa Absence duration",
                refresh=False,
            )

            # This is the existing Absence activation command format.
            # Its payload still needs validation against a successful
            # Overkiz request before Absence can be considered fixed.
            await self._set_operating_mode_flag(
                "absence",
                "on" if value > 0 else "off",
            )

            await self.async_execute_overkiz_command(
                "refreshAwayModeDuration",
                refresh=False,
            )

        await self.async_run_pagosa_operation(
            operation,
            None,
            "Pagosa Absence duration",
        )

    async def async_set_programming_slots(
        self, slots: list[tuple[str, str]]
    ) -> None:
        """Write both time slots in one command."""
        value = programming_slots(slots)

        async def operation():
            await self.async_execute_overkiz_command(
                "setProgrammingSlots",
                [value],
                label="Pagosa programmation",
                refresh=False,
            )

        await self.async_run_pagosa_operation(
            operation,
            {"io:ProgrammingSlotsState": value},
            "Pagosa time slots",
        )

    # ------------------------------------------------------------------
    # Session handling
    # ------------------------------------------------------------------

    async def async_close(self) -> None:
        """Close the session this hub opened."""
        if not self._session.closed:
            await self._session.close()

    async def _async_update_data(self):
        """Refresh the Overkiz setup, reconnecting first if needed."""
        if not self.online:
            if not await self.connect():
                raise UpdateFailed("Cannot reach the Pagosa through Overkiz")
            return self.data

        await self._refresh_overkiz_setup()
        return self.data

    def get_model_infos(self) -> dict:
        """What the device is, for the entities that ask."""
        return {
            "name": PAGOSA_MODEL,
            "manufacturer": "Sauter",
            "model": "Pagosa 270L",
        }

    def get_serial_number(self) -> str:
        """The gateway's serial number, which is what Overkiz exposes."""
        device = self._overkiz_device or {}
        gateway = device.get("gateway", {})
        if isinstance(gateway, dict):
            return gateway.get("serialNumber", "Unknown")
        return "Unknown"
