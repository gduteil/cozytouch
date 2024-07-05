"""Atlantic Cozytouch Hub."""

from __future__ import annotations

import asyncio
import copy
from datetime import UTC, datetime, time as t, timedelta, timezone
import json
import logging

from aiohttp import ClientSession, ContentTypeError, FormData

from homeassistant import exceptions
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .capability import get_capability_infos
from .const import COZYTOUCH_ATLANTIC_API, COZYTOUCH_CLIENT_ID
from .model import get_model_infos

_LOGGER = logging.getLogger(__name__)


class Hub(DataUpdateCoordinator):
    """Atlantic Cozytouch Hub."""

    manufacturer = "Atlantic Group"
    _localization = {}
    _setup = {}
    _zones = {}

    _timestamp_away_mode_last_change = None
    _timestamp_away_mode_start = None
    _timestamp_away_mode_end = None

    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        password: str,
        deviceId: int | None = None,
    ) -> None:
        """Init hub."""
        super().__init__(
            hass,
            _LOGGER,
            name="Cozytouch_" + str(deviceId),
            update_interval=timedelta(seconds=10),
        )
        self._session = ClientSession()
        self._host = "none"
        self._hass = hass
        self._username = username
        self._password = password
        self._deviceId = deviceId
        self._zoneId = -1
        self._access_token = ""
        self._id = "cozytouch." + username.lower()
        self._create_unknown = False
        self._dump_json = False
        self._devices = []

        self.online = False

        modelInfos = self.get_model_infos()
        if "name" in modelInfos:
            self.device_info = DeviceInfo(
                entry_type=DeviceEntryType.SERVICE,
                identifiers={("cozytouch", "cozytouch" + str(deviceId))},
                manufacturer="Atlantic",
                name=modelInfos["name"],
            )

        self._timestamps_away_mode_capability_id = None

        # Load json for test during dev
        self._test_load = False
        if self._test_load:
            self._dump_json = False
            self.online = True
            with open(
                self._hass.config.config_dir + "/cozytouch_colas.json",
                encoding="utf-8",
            ) as json_file:
                file_contents = json_file.read()
                self.update_devices_from_json_data(json.loads(file_contents))

    @property
    def hub_id(self) -> str:
        """ID for hub."""
        return self._id

    async def test_connection(self) -> bool:
        """Test connection."""
        await self.connect()
        return self.online

    async def connect(self) -> bool:
        """Connect to Cozytouch server."""
        if self.online is False:
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
                    token = await response.json()

                    if "error" in token and token["error"] == "invalid_grant":
                        raise CannotConnect

                    if "token_type" not in token:
                        raise CannotConnect

                    if "access_token" not in token:
                        raise CannotConnect

                    self._access_token = token["access_token"]

                headers = {
                    "Authorization": f"Bearer {self._access_token}",
                    "Content-Type": "application/json",
                }
                async with self._session.get(
                    COZYTOUCH_ATLANTIC_API + "/magellan/cozytouch/setupview",
                    headers=headers,
                ) as response:
                    json_data = await response.json()

                    # Store setup
                    for key in (
                        "absence",
                        "address",
                        "area",
                        "id",
                        "mainDHWEnergy",
                        "mainHeatingEnergy",
                        "name",
                        "numberOfRooms",
                        "setupBuildingDate",
                        "timeZone",
                        "type",
                    ):
                        if key in json_data[0]:
                            self._setup[key] = copy.deepcopy(json_data[0][key])

                    # Update devices infos
                    self.update_devices_from_json_data(json_data)

                    # Store country to retrieve localization informations
                    if "address" in json_data[0]:
                        await self._update_localization(
                            json_data[0]["address"].get("country", None)
                        )

                    # Store zones informations
                    if "zones" in json_data[0]:
                        copy.deepcopy(json_data[0]["zones"])

                self.online = True

            except CannotConnect:
                self.online = False

        return self.online

    async def close(self) -> None:
        """Close session."""
        await self._session.close()

    def update_devices_from_json_data(self, json_data) -> None:
        """Update the devices list."""

        if self._dump_json:
            with open(
                self._hass.config.config_dir + "/Cozytouch.json", "w", encoding="utf-8"
            ) as outfile:
                json_object = json.dumps(json_data, indent=4)
                outfile.write(json_object)

        # Get zones
        if len(self._zones) == 0 and "zones" in json_data[0]:
            self._zones = copy.deepcopy(json_data[0]["zones"])

        # Start by removing old devices
        for local_device in self._devices[:]:
            bStillExists = False
            for remote_device in json_data[0]["devices"]:
                if remote_device["deviceId"] == local_device["deviceId"]:
                    bStillExists = True
                    break

            if bStillExists is False:
                self._devices.remove(local_device)

        # Create new devices
        deviceIndex = -1
        for remote_device in json_data[0]["devices"]:
            deviceIndex = -1
            for i, local_device in enumerate(self._devices):
                if remote_device["deviceId"] == local_device["deviceId"]:
                    deviceIndex = i
                    self._zoneId = remote_device["zoneId"]
                    break

            if deviceIndex == -1:
                device = {
                    "deviceId": remote_device["deviceId"],
                    "name": remote_device["name"],
                    "gatewaySerialNumber": remote_device["gatewaySerialNumber"],
                    "modelId": remote_device["modelId"],
                    "productId": remote_device["productId"],
                    "zoneId": remote_device["zoneId"],
                    "modelInfos": get_model_infos(remote_device["modelId"]),
                    "capabilities": [],
                    "tags": [],
                }
                if "tags" in remote_device:
                    device["tags"] = copy.deepcopy(remote_device["tags"])

                self._devices.append(device)
                deviceIndex = len(self._devices) - 1

            # Only retrieve capabilites from current device
            if self._deviceId == remote_device["deviceId"]:
                self._devices[deviceIndex]["capabilities"] = copy.deepcopy(
                    remote_device["capabilities"]
                )

    def set_create_entities_for_unknown_entities(self, create_unknown: bool) -> None:
        """Set option from config flow to create entities for unknown capabilities."""
        self._create_unknown = create_unknown

    def get_create_entities_for_unknown_entities(self) -> bool:
        """Get option from config flow to create entities for unknown capabilities."""
        return self._create_unknown

    def set_dump_json(self, dump_json: bool) -> None:
        """Set option from config flow to dump JSON from API."""
        self._dump_json = dump_json

    async def _async_update_data(self):
        _LOGGER.debug("_async_update_data %d", self._deviceId)
        if self._test_load:
            return

        if self.online:
            headers = {
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
            }
            async with self._session.get(
                COZYTOUCH_ATLANTIC_API
                + "/magellan/capabilities/?deviceId="
                + str(self._deviceId),
                headers=headers,
            ) as response:
                try:
                    json_data = await response.json()
                    for dev in self._devices:
                        if dev["deviceId"] == self._deviceId:
                            dev["capabilities"] = copy.deepcopy(json_data)
                            break

                    if (
                        self._timestamp_away_mode_last_change is not None
                        and self._timestamps_away_mode_capability_id is not None
                        and self._timestamp_away_mode_start is not None
                        and self._timestamp_away_mode_end is not None
                    ):
                        now = datetime.now(tz=dt_util.DEFAULT_TIME_ZONE).timestamp()
                        if now - self._timestamp_away_mode_last_change > 20:
                            await self.set_away_mode_timestamps(
                                None,
                                None,
                                self._timestamps_away_mode_capability_id,
                                self._timestamp_away_mode_start,
                                self._timestamp_away_mode_end,
                            )

                except ContentTypeError:
                    self.online = False

        else:
            await self.connect()

    def devices(self):
        """Get devices list."""
        devs = []
        for dev in self._devices:
            devs.append(
                {
                    "deviceId": dev["deviceId"],
                    "name": dev["name"],
                    "model": dev["modelInfos"]["name"],
                }
            )

        return devs

    def get_zone_name(self, zoneId: int | None = None) -> str:
        """Get zone infos."""
        if not zoneId:
            zoneId = self._zoneId

        for zone in self._zones:
            if "id" in zone and zone["id"] == zoneId:
                return zone["name"]

        return str(zoneId)

    def get_model_infos(self, deviceId: int | None = None) -> str:
        """Get model infos."""
        if not deviceId:
            deviceId = self._deviceId

        for dev in self._devices:
            if dev["deviceId"] == deviceId:
                zoneId = dev["zoneId"]

                # Special case for sub-devices, use master zone Id
                for masterDev in self._devices:
                    if "tags" in masterDev:
                        for tag in masterDev["tags"]:
                            if (
                                "label" in tag
                                and tag["label"] == "iothubChildrenIds"
                                and "value" in tag
                                and tag["value"] == dev["name"]
                            ):
                                zoneId = masterDev["zoneId"]
                                break

                return get_model_infos(dev["modelId"], self.get_zone_name(zoneId))

        return get_model_infos(-1)

    def get_serial_number(self, deviceId: int | None = None) -> str:
        """Get serial number."""
        if not deviceId:
            deviceId = self._deviceId

        for dev in self._devices:
            if dev["deviceId"] == deviceId:
                return dev["gatewaySerialNumber"]

        return "Unknown"

    def get_capabilities_for_device(self, deviceId: int | None = None):
        """Get capabilities for a device."""

        if not deviceId:
            deviceId = self._deviceId

        capabilities = []
        for dev in self._devices:
            if dev["deviceId"] == deviceId:
                modelInfos = get_model_infos(dev["modelId"])
                for capability in dev["capabilities"]:
                    capability_infos = get_capability_infos(
                        modelInfos,
                        capability["capabilityId"],
                        capability["value"],
                    )

                    if capability_infos is None and self._create_unknown:
                        capability_infos = {
                            "name": "Capability_" + str(capability["capabilityId"]),
                            "type": "string",
                            "category": "diag",
                        }

                    if capability_infos is not None and len(capability_infos) > 0:
                        capability_infos["deviceId"] = deviceId
                        capability_infos["capabilityId"] = capability["capabilityId"]

                        capabilities.append(capability_infos)

        return capabilities

    def get_capability_infos(
        self, modelId: int, capabilityId: int, capabilityValue: str
    ):
        """Get capability infos."""
        return get_capability_infos(modelId, capabilityId, capabilityValue)

    def get_capability_value(
        self, capabilityId: int, defaultIfNotExist: str | None = "0"
    ):
        """Get value for a device capability."""
        for dev in self._devices:
            if dev["deviceId"] == self._deviceId:
                for capability in dev["capabilities"]:
                    if capabilityId == capability["capabilityId"]:
                        return capability["value"]

                return defaultIfNotExist

        return None

    async def set_capability_value(self, capabilityId: int, value: str):
        """Set value for a device capability."""
        _LOGGER.debug(
            "Set_capability_value for %d : %d = %s", self._deviceId, capabilityId, value
        )
        if self.online:
            for dev in self._devices:
                if dev["deviceId"] == self._deviceId:
                    for capability in dev["capabilities"]:
                        if capabilityId == capability["capabilityId"]:
                            if self._test_load:
                                capability["value"] = value
                            else:
                                # Write capability value
                                async with self._session.post(
                                    COZYTOUCH_ATLANTIC_API
                                    + "/magellan/executions/writecapability",
                                    json={
                                        "capabilityId": capabilityId,
                                        "deviceId": self._deviceId,
                                        "value": value,
                                    },
                                    headers={
                                        "Authorization": f"Bearer {self._access_token}",
                                        "Content-Type": "application/json",
                                    },
                                ) as response:
                                    if response.status == 201:
                                        # Check completion
                                        executionId = await response.json()
                                        completed = False
                                        nbRetry = 0
                                        while not completed:
                                            async with self._session.get(
                                                COZYTOUCH_ATLANTIC_API
                                                + "/magellan/executions/"
                                                + str(executionId),
                                                headers={
                                                    "Authorization": f"Bearer {self._access_token}",
                                                    "Content-Type": "application/json",
                                                },
                                            ) as executionResponse:
                                                try:
                                                    execution_data = (
                                                        await executionResponse.json()
                                                    )
                                                    execution_state = (
                                                        execution_data.get(
                                                            "state", False
                                                        )
                                                    )
                                                    if execution_state == 1:
                                                        _LOGGER.info(
                                                            "Execution_state waiting execution"
                                                        )
                                                    if execution_state == 2:
                                                        _LOGGER.info(
                                                            "Execution_state in progress"
                                                        )
                                                    elif execution_state == 3:
                                                        _LOGGER.info(
                                                            "Execution_state completed"
                                                        )
                                                        completed = True
                                                        break
                                                    else:
                                                        _LOGGER.info(
                                                            "Execution_state error"
                                                        )
                                                        break

                                                except ContentTypeError:
                                                    self.online = False
                                                    break

                                            nbRetry += 1
                                            if nbRetry > 5:
                                                break

                                            await asyncio.sleep(1)

                                        if completed:
                                            capability["value"] = value
                            break

    def away_mode_init(self, timestampStart, timestampEnd):
        """Init away mode timestamps."""
        self._timestamp_away_mode_start = timestampStart
        self._timestamp_away_mode_end = timestampEnd

    async def set_away_mode_start(
        self,
        capabilityIdTimestamps: int,
        timestamp,
    ):
        """Set away mode start timestamp."""
        self._timestamp_away_mode_start = timestamp
        self._timestamps_away_mode_capability_id = capabilityIdTimestamps
        self._timestamp_away_mode_last_change = datetime.now(
            tz=dt_util.DEFAULT_TIME_ZONE
        ).timestamp()

    def get_away_mode_start(self):
        """Get away mode start timestamp."""
        return self._timestamp_away_mode_start

    async def set_away_mode_end(
        self,
        capabilityIdTimestamps: int,
        timestamp,
    ):
        """Set away mode end timestamp."""
        self._timestamp_away_mode_end = timestamp
        self._timestamps_away_mode_capability_id = capabilityIdTimestamps
        self._timestamp_away_mode_last_change = datetime.now(
            tz=dt_util.DEFAULT_TIME_ZONE
        ).timestamp()

    def get_away_mode_end(self):
        """Get away mode end timestamp."""
        return self._timestamp_away_mode_end

    async def set_away_mode_timestamps(
        self,
        capabilityIdMode,
        valueMode,
        capabilityIdTimestamps: int,
        timestampStart,
        timestampEnd,
    ):
        """Set away mode timestamps."""

        if self.online:
            # Update setup
            json_data = {}
            for key in (
                "address",
                "area",
                "id",
                "mainDHWEnergy",
                "mainHeatingEnergy",
                "name",
                "numberOfRooms",
                "setupBuildingDate",
                "timeZone",
                "type",
            ):
                if key in self._setup:
                    json_data[key] = copy.deepcopy(self._setup[key])

            json_data["absence"] = {}
            if timestampStart is not None and timestampEnd is not None:
                json_data["absence"]["startDate"] = timestampStart
                json_data["absence"]["endDate"] = timestampEnd
                _timestamp_away_mode_start = timestampStart
                _timestamp_away_mode_end = timestampEnd

            async with self._session.post(
                COZYTOUCH_ATLANTIC_API
                + "/magellan/cozytouch/setups/"
                + str(self._setup["id"])
                + "/update",
                json=json_data,
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Content-Type": "application/json",
                },
            ) as response:
                if response.status == 204:
                    if timestampStart is not None and timestampEnd is not None:
                        valueTimestamps = (
                            "[" + str(timestampStart) + "," + str(timestampEnd) + "]"
                        )
                        await self.set_capability_value(
                            capabilityIdTimestamps, valueTimestamps
                        )
                        _LOGGER.info(
                            "Away mode enabled %d -> %d", timestampStart, timestampEnd
                        )
                    else:
                        valueTimestamps = "[0,0]"
                        await self.set_capability_value(
                            capabilityIdTimestamps, valueTimestamps
                        )
                        _LOGGER.info("Away mode disabled")

                    if capabilityIdMode is not None and valueMode is not None:
                        await self.set_capability_value(capabilityIdMode, valueMode)

                    self._timestamp_away_mode_last_change = None

    async def _update_localization(self, country: str):
        if len(self._localization) == 0:
            headers = {
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
            }
            async with self._session.get(
                COZYTOUCH_ATLANTIC_API + "/magellan/refs/countries",
                headers=headers,
            ) as response:
                try:
                    json_data = await response.json()
                    for localization in json_data:
                        if localization.get("countryCode", "") == country:
                            self._localization = copy.deepcopy(localization)
                            break

                except ContentTypeError:
                    self._localization = {}


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""
