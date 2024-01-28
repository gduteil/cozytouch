"""Atlantic Cozytouch Hub."""
from __future__ import annotations

import copy

from aiohttp import ClientSession, ContentTypeError, FormData

from homeassistant import exceptions
from homeassistant.core import HomeAssistant

from .capability import get_capability_infos
from .const import COZYTOUCH_ATLANTIC_API, COZYTOUCH_CLIENT_ID
from .model import get_model_name_from_id


class Hub:
    """Atlantic Cozytouch Hub."""

    manufacturer = "Atlantic Group"

    def __init__(self, hass: HomeAssistant, username: str, password: str) -> None:
        """Init hub."""
        self._session = ClientSession()
        self._host = "none"
        self._hass = hass
        self.username = username
        self._password = password
        self._access_token = ""
        self._id = "cozytouch." + username.lower()
        self._create_unknown = False
        self._devices = []
        self.online = False

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
                            "username": "GA-PRIVATEPERSON/" + self.username,
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
                    self.update_devices_from_json_data(json_data)

                self.online = True

            except CannotConnect:
                self.online = False

        return self.online

    async def close(self) -> None:
        """Close session."""
        await self._session.close()

    def update_devices_from_json_data(self, json_data: {}) -> None:
        """Update the devices list."""

        # Start by removing old devices
        for local_device in self._devices[:]:
            bStillExists = False
            for remote_device in json_data[0]["devices"]:
                if remote_device["deviceId"] == local_device["deviceId"]:
                    bStillExists = True
                    break

            if bStillExists == False:
                self._devices.remove(local_device)

        # Create new devices
        deviceIndex = -1
        for remote_device in json_data[0]["devices"]:
            deviceIndex = -1
            for i, local_device in enumerate(self._devices):
                if remote_device["deviceId"] == local_device["deviceId"]:
                    deviceIndex = i
                    break

            if deviceIndex == -1:
                self._devices.append(
                    {
                        "deviceId": remote_device["deviceId"],
                        "name": remote_device["name"],
                        "gatewaySerialNumber": remote_device["gatewaySerialNumber"],
                        "modelId": remote_device["modelId"],
                        "productId": remote_device["productId"],
                        "capabilities": [],
                    }
                )
                deviceIndex = len(self._devices) - 1

            self._devices[deviceIndex]["capabilities"] = copy.deepcopy(
                remote_device["capabilities"]
            )

            self._devices[deviceIndex]["modelName"] = get_model_name_from_id(
                remote_device["modelId"]
            )

    def set_create_entities_for_unknown_entities(self, create_unknown: bool) -> None:
        """Set option from config flow to create entities for unknown capabilities."""
        self._create_unknown = create_unknown

    def get_create_entities_for_unknown_entities(self) -> bool:
        """Get option from config flow to create entities for unknown capabilities."""
        return self._create_unknown

    async def update(self, deviceId: int) -> None:
        """Update values from cloud."""
        if self.online:
            headers = {
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
            }
            async with self._session.get(
                COZYTOUCH_ATLANTIC_API
                + "/magellan/capabilities/?deviceId="
                + str(deviceId),
                headers=headers,
            ) as response:
                try:
                    json_data = await response.json()
                    for dev in self._devices:
                        if dev["deviceId"] == deviceId:
                            dev["capabilities"] = copy.deepcopy(json_data)
                            break
                except ContentTypeError:
                    self.online = False
        else:
            await self.connect()

    def devices(self) -> []:
        """Get devices list."""
        devs = []
        for dev in self._devices:
            devs.append({"deviceId": dev["deviceId"], "name": dev["name"]})

        return devs

    def get_model_name(self, deviceId: int) -> str:
        """Get model name."""
        for dev in self._devices:
            if dev["deviceId"] == deviceId:
                return dev["modelName"]

        return "Unknown"

    def get_serial_number(self, deviceId: int) -> str:
        """Get serial number."""
        for dev in self._devices:
            if dev["deviceId"] == deviceId:
                return dev["gatewaySerialNumber"]

        return "Unknown"

    def get_capabilities_for_device(self, deviceId: int) -> []:
        """Get capabilities for a device."""
        capabilities = []
        for dev in self._devices:
            if dev["deviceId"] == deviceId:
                for capability in dev["capabilities"]:
                    capability_infos = get_capability_infos(
                        dev["modelId"], capability["capabilityId"]
                    )

                    if len(capability_infos) == 0 and self._create_unknown:
                        capability_infos = {
                            "name": "Capability_" + str(capability["capabilityId"]),
                            "type": "string",
                            "category": "diag",
                        }

                    if len(capability_infos) > 0:
                        capability_infos["deviceId"] = deviceId
                        capability_infos["capabilityId"] = capability["capabilityId"]

                        capabilities.append(capability_infos)

        return capabilities

    def get_capability_value(self, deviceId: int, capabilityId: int):
        """Get value for a device capability."""
        for dev in self._devices:
            if dev["deviceId"] == deviceId:
                for capability in dev["capabilities"]:
                    if capabilityId == capability["capabilityId"]:
                        return capability["value"]

        return None

    async def set_capability_value(self, deviceId: int, capabilityId: int, value: str):
        """Set value for a device capability."""
        if self.online:
            for dev in self._devices:
                if dev["deviceId"] == deviceId:
                    for capability in dev["capabilities"]:
                        if capabilityId == capability["capabilityId"]:
                            # Write capability value
                            async with self._session.post(
                                COZYTOUCH_ATLANTIC_API
                                + "/magellan/executions/writecapability",
                                json={
                                    "capabilityId": capabilityId,
                                    "deviceId": deviceId,
                                    "value": value,
                                },
                                headers={
                                    "Authorization": f"Bearer {self._access_token}",
                                    "Content-Type": "application/json",
                                },
                            ) as response:
                                if response.status == 201:
                                    capability["value"] = value

                            break


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""
